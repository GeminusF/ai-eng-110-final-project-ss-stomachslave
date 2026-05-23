"""OpenRouter VLM adapter using the OpenAI-compatible client."""

from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
from typing import Any

from ai.providers.base import ProviderError, VLMProvider


class OpenRouterVLM(VLMProvider):
    """Vision-language adapter for OpenRouter.

    The class implements the provided `VLMProvider` interface, so the rest of
    the app can keep calling `ai.identify_ingredients(..., vlm=provider)`.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        reasoning_enabled: bool = True,
        reasoning_exclude: bool = True,
        client: Any | None = None,
    ) -> None:
        self.model = model or os.getenv("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
        self.reasoning_enabled = reasoning_enabled
        self.reasoning_exclude = reasoning_exclude
        self._client = client or self._make_client(api_key, base_url)

    @staticmethod
    def _make_client(api_key: str | None, base_url: str):
        key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise ProviderError("OPENROUTER_API_KEY is not set.")
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:
            raise ProviderError("The `openai` package is required for OpenRouter.") from exc
        return OpenAI(base_url=base_url, api_key=key)

    def describe(
        self,
        image_path: str,
        prompt: str,
        *,
        json_schema: dict | None = None,
    ) -> str:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(image_path)

        media_type = _guess_media_type(path)
        encoded = base64.standard_b64encode(path.read_bytes()).decode("ascii")
        data_url = f"data:{media_type};base64,{encoded}"

        full_prompt = prompt
        if json_schema is not None:
            full_prompt = (
                prompt
                + "\n\nReturn ONLY valid JSON matching this schema "
                "(no prose, no markdown fences):\n"
                + json.dumps(json_schema, indent=2)
            )

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": full_prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "max_tokens": 1024,
        }
        if self.reasoning_enabled:
            kwargs["extra_body"] = {
                "reasoning": {
                    "enabled": True,
                    "exclude": self.reasoning_exclude,
                }
            }

        response = self._create_completion(kwargs)
        content = _response_text(response, json_expected=json_schema is not None)
        if not content and self.reasoning_enabled:
            retry_kwargs = dict(kwargs)
            retry_kwargs.pop("extra_body", None)
            response = self._create_completion(retry_kwargs)
            content = _response_text(response, json_expected=json_schema is not None)
        if not content:
            details = _response_details(response)
            suffix = f" Details: {details}." if details else ""
            raise ProviderError(
                "OpenRouter returned an empty response. The configured model did not return JSON content."
                + suffix
            )
        if json_schema is not None:
            normalized = _normalize_json_response(content)
            if normalized:
                return normalized
            retry_kwargs = _strict_json_retry_kwargs(kwargs)
            response = self._create_completion(retry_kwargs)
            content = _response_text(response, json_expected=True)
            normalized = _normalize_json_response(content)
            if normalized:
                return normalized
            raise ProviderError(f"OpenRouter returned a non-JSON response. Raw: {content[:300]!r}")
        return content

    def _create_completion(self, kwargs: dict[str, Any]):
        try:
            return self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # pragma: no cover - network path
            detail = str(exc)
            if "support image input" in detail:
                detail += " The configured OpenRouter model must support image input."
            raise ProviderError(f"OpenRouter call failed: {detail}") from exc


def _guess_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    raise ProviderError(f"Unsupported image type: {suffix}")


def _response_text(response: Any, *, json_expected: bool) -> str:
    content = _message_content(response)
    if content:
        return _json_candidate(content) if json_expected else content

    reasoning = _message_reasoning(response)
    if reasoning and json_expected:
        return _json_candidate(reasoning)
    return reasoning


def _message_content(response: Any) -> str:
    content = response.choices[0].message.content or ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(str(part.get("text") or ""))
        return "\n".join(text_parts).strip()
    return str(content).strip()


def _message_reasoning(response: Any) -> str:
    message = response.choices[0].message
    for attr in ("reasoning_content", "reasoning"):
        value = getattr(message, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    details = getattr(message, "reasoning_details", None)
    if isinstance(details, list):
        text_parts = []
        for part in details:
            if isinstance(part, dict):
                text_parts.append(str(part.get("text") or part.get("content") or ""))
        return "\n".join(part for part in text_parts if part).strip()
    return ""


def _json_candidate(text: str) -> str:
    stripped = _strip_json_fence(text.strip())
    if not stripped:
        return ""
    if stripped.startswith("```") or stripped.startswith("{"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        return stripped[start : end + 1].strip()
    return stripped


def _normalize_json_response(text: str) -> str:
    payload = _parse_recoverable_json(text)
    if payload is None:
        return ""
    if isinstance(payload, list):
        payload = {"meal_recognized": bool(payload), "ingredients": payload}
    if isinstance(payload, dict) and "ingredients" in payload and "meal_recognized" not in payload:
        payload = {**payload, "meal_recognized": bool(payload.get("ingredients"))}
    return json.dumps(payload)


def _strict_json_retry_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    retry_kwargs = copy.deepcopy(kwargs)
    retry_kwargs.pop("extra_body", None)
    retry_kwargs["max_tokens"] = max(int(retry_kwargs.get("max_tokens", 0)), 2048)
    content = retry_kwargs["messages"][0]["content"]
    text_part = content[0]
    text_part["text"] = (
        text_part["text"]
        + "\n\nYour previous response was invalid. Output a complete JSON object only. "
        "The first character must be { and the last character must be }. "
        "Include top-level meal_recognized and ingredients fields."
    )
    return retry_kwargs


def _parse_recoverable_json(text: str) -> Any | None:
    stripped = _strip_json_fence(text.strip())
    candidates = [stripped]
    if '"ingredients"' in stripped and "[" in stripped and "]" not in stripped:
        last_brace = stripped.rfind("}")
        if last_brace != -1:
            candidates.append(stripped[:last_brace] + "]" + stripped[last_brace:])
    for candidate in dict.fromkeys(candidates):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines[1:]).strip()


def _response_details(response: Any) -> str:
    choice = response.choices[0] if getattr(response, "choices", None) else None
    if choice is None:
        return ""
    pairs = []
    for attr in ("finish_reason", "native_finish_reason"):
        value = getattr(choice, attr, None)
        if value:
            pairs.append(f"{attr}={value}")
    provider = getattr(response, "provider", None)
    if provider:
        pairs.append(f"provider={provider}")
    return ", ".join(pairs)