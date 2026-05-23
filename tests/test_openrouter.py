import json

import pytest
from ai.providers.base import ProviderError
from ai.schemas import INGREDIENTS_SCHEMA

from foodanalyzer.cli import build_analyzer, build_vlm
from foodanalyzer.config import Settings
from foodanalyzer.providers.openrouter import OpenRouterVLM
from foodanalyzer.services.nutrition_cache import InMemoryNutritionCache, PostgresNutritionCache


class FakeMessage:
    def __init__(
        self,
        content: str,
        *,
        reasoning: str | None = None,
        reasoning_content: str | None = None,
    ) -> None:
        self.content = content
        self.reasoning = reasoning
        self.reasoning_content = reasoning_content


class FakeChoice:
    def __init__(self, content, *, finish_reason: str | None = None) -> None:
        if isinstance(content, FakeMessage):
            self.message = content
        else:
            self.message = FakeMessage(content)
        self.finish_reason = finish_reason


class FakeResponse:
    def __init__(self, content, *, finish_reason: str | None = None) -> None:
        self.choices = [FakeChoice(content, finish_reason=finish_reason)]


class FakeCompletions:
    def __init__(self, responses=None) -> None:
        self.kwargs = None
        self.calls = []
        self.responses = list(responses or [])

    def create(self, **kwargs):
        self.kwargs = kwargs
        self.calls.append(kwargs)
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, FakeResponse):
                return response
            return FakeResponse(response)
        return FakeResponse(
            json.dumps(
                {
                    "meal_recognized": True,
                    "ingredients": [
                        {
                            "name": "broccoli",
                            "estimated_grams": 80,
                            "confidence": 0.9,
                        }
                    ],
                }
            )
        )


class FakeChat:
    def __init__(self, responses=None) -> None:
        self.completions = FakeCompletions(responses)


class FakeClient:
    def __init__(self, responses=None) -> None:
        self.chat = FakeChat(responses)


def test_openrouter_vlm_sends_image_schema_and_reasoning(sample_image):
    client = FakeClient()
    provider = OpenRouterVLM(
        model="test-model",
        client=client,
        reasoning_enabled=True,
        reasoning_exclude=True,
    )

    content = provider.describe(
        sample_image,
        "Identify ingredients.",
        json_schema=INGREDIENTS_SCHEMA,
    )

    kwargs = client.chat.completions.kwargs
    assert json.loads(content)["meal_recognized"] is True
    assert kwargs["model"] == "test-model"
    assert kwargs["extra_body"] == {"reasoning": {"enabled": True, "exclude": True}}
    text_part = kwargs["messages"][0]["content"][0]
    image_part = kwargs["messages"][0]["content"][1]
    assert "Return ONLY valid JSON" in text_part["text"]
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


def test_openrouter_vlm_can_disable_reasoning(sample_image):
    client = FakeClient()
    provider = OpenRouterVLM(model="test-model", client=client, reasoning_enabled=False)

    provider.describe(sample_image, "Identify ingredients.")

    assert "extra_body" not in client.chat.completions.kwargs


def test_openrouter_vlm_retries_empty_reasoning_response_without_model_change(sample_image):
    expected = json.dumps({"meal_recognized": False, "ingredients": []})
    client = FakeClient(responses=["", expected])
    provider = OpenRouterVLM(
        model="test-model",
        client=client,
        reasoning_enabled=True,
        reasoning_exclude=True,
    )

    content = provider.describe(sample_image, "Identify ingredients.", json_schema=INGREDIENTS_SCHEMA)

    calls = client.chat.completions.calls
    assert content == expected
    assert len(calls) == 2
    assert calls[0]["model"] == "test-model"
    assert calls[1]["model"] == "test-model"
    assert "extra_body" in calls[0]
    assert "extra_body" not in calls[1]


def test_openrouter_vlm_raises_clear_error_for_empty_response(sample_image):
    client = FakeClient(responses=[FakeResponse("", finish_reason="stop"), FakeResponse("", finish_reason="stop")])
    provider = OpenRouterVLM(model="test-model", client=client, reasoning_enabled=True)

    with pytest.raises(ProviderError, match="empty response.*finish_reason=stop"):
        provider.describe(sample_image, "Identify ingredients.", json_schema=INGREDIENTS_SCHEMA)


def test_openrouter_vlm_uses_reasoning_json_when_content_is_empty(sample_image):
    expected = json.dumps({"meal_recognized": False, "ingredients": []})
    client = FakeClient(
        responses=[
            FakeResponse(
                FakeMessage(
                    "",
                    reasoning=f"Reasoning text.\nFinal answer:\n{expected}",
                )
            )
        ]
    )
    provider = OpenRouterVLM(model="test-model", client=client, reasoning_enabled=False)

    content = provider.describe(sample_image, "Identify ingredients.", json_schema=INGREDIENTS_SCHEMA)

    assert content == expected


def test_openrouter_vlm_repairs_missing_meal_flag_and_open_ingredients_array(sample_image):
    raw = """{
  "ingredients": [
    {
      "name": "bread",
      "estimated_grams": 30,
      "confidence": 0.95
    }
}"""
    client = FakeClient(responses=[raw])
    provider = OpenRouterVLM(model="test-model", client=client, reasoning_enabled=False)

    content = provider.describe(sample_image, "Identify ingredients.", json_schema=INGREDIENTS_SCHEMA)
    payload = json.loads(content)

    assert payload == {
        "meal_recognized": True,
        "ingredients": [
            {
                "name": "bread",
                "estimated_grams": 30,
                "confidence": 0.95,
            }
        ],
    }


def test_openrouter_vlm_retries_non_json_with_stricter_prompt(sample_image):
    expected = json.dumps({"meal_recognized": False, "ingredients": []})
    client = FakeClient(responses=["So", expected])
    provider = OpenRouterVLM(model="test-model", client=client, reasoning_enabled=False)

    content = provider.describe(sample_image, "Identify ingredients.", json_schema=INGREDIENTS_SCHEMA)

    calls = client.chat.completions.calls
    assert content == expected
    assert len(calls) == 2
    assert calls[0]["model"] == "test-model"
    assert calls[1]["model"] == "test-model"
    assert calls[1]["max_tokens"] == 2048
    assert "Output a complete JSON object only" in calls[1]["messages"][0]["content"][0]["text"]


def test_openrouter_vlm_raises_clear_error_for_non_json_after_retry(sample_image):
    client = FakeClient(responses=["So", "Still not JSON"])
    provider = OpenRouterVLM(model="test-model", client=client, reasoning_enabled=False)

    with pytest.raises(ProviderError, match="non-JSON response.*Still not JSON"):
        provider.describe(sample_image, "Identify ingredients.", json_schema=INGREDIENTS_SCHEMA)


def test_build_vlm_uses_openrouter_when_configured():
    settings = Settings(
        llm_provider="openrouter",
        llm_model="test-model",
        openrouter_api_key="test-key",
    )

    provider = build_vlm(settings, offline=False)

    assert isinstance(provider, OpenRouterVLM)
    assert provider.model == "test-model"


def test_build_analyzer_passes_settings_key_to_usda(monkeypatch):
    calls = {}

    class FakeUSDA:
        def __init__(self, api_key):
            calls["api_key"] = api_key

    monkeypatch.setattr("foodanalyzer.cli.USDAProvider", FakeUSDA)
    settings = Settings(
        llm_provider="openrouter",
        llm_model="test-model",
        openrouter_api_key="test-key",
        usda_api_key="usda-from-settings",
        database_url="postgresql://postgres:dev@localhost:5432/foodanalyzer",
    )

    analyzer = build_analyzer(settings, offline=False)

    assert calls["api_key"] == "usda-from-settings"
    assert analyzer.ai_service._nutrition_provider.__class__ is FakeUSDA
    assert isinstance(analyzer.ai_service.cache, PostgresNutritionCache)


def test_build_analyzer_uses_memory_cache_offline():
    settings = Settings(offline_mode=True)

    analyzer = build_analyzer(settings, offline=True)

    assert isinstance(analyzer.ai_service.cache, InMemoryNutritionCache)