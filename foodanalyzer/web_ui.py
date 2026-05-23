"""HTMX web UI routes with a minimal StomachSlave interface."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from html import escape
from pathlib import Path
import re
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from foodanalyzer.cli import build_analyzer
from foodanalyzer.config import Settings
from foodanalyzer.models import AnalysisResult, AnalysisStatus
from foodanalyzer.storage.repository import AnalysisRepository
from foodanalyzer.utils.images import ImageValidationError, save_upload_bytes


def build_web_analyzer(settings: Settings, *, offline: bool):
    """Build the analyzer through the same service-layer factory as CLI/API."""
    return build_analyzer(settings, offline=offline)


async def analyze_upload(
    image_bytes: bytes,
    original_name: str,
    settings: Settings,
    repository: AnalysisRepository,
    mode: str | None,
) -> AnalysisResult:
    image_path = save_upload_bytes(
        image_bytes,
        original_name,
        settings.upload_dir,
        settings.max_image_bytes,
    )
    analyzer = build_web_analyzer(settings, offline=is_offline_mode(mode))
    analyzer.repository = repository
    result = await analyzer.analyze(image_path, save=False)
    return await repository.save(result)


def register_web_ui(app: FastAPI, settings: Settings, repository: AnalysisRepository) -> None:
    @app.get("/ui", response_class=HTMLResponse)
    async def ui_home() -> HTMLResponse:
        history_records = await repository.list_recent(10)
        return HTMLResponse(
            render_page(
                default_mode=default_source_mode(settings),
                history=history_records,
                settings=settings,
            )
        )

    @app.get("/ui/uploads/{filename}")
    async def ui_uploaded_image(filename: str):
        image_path = safe_upload_image_path(filename, settings)
        if image_path is None:
            return HTMLResponse("Not found", status_code=404)
        return FileResponse(image_path, media_type=image_media_type(image_path))

    @app.post("/ui/analyze", response_class=HTMLResponse)
    async def ui_analyze(
        request: Request,
        file: UploadFile = File(...),
        mode: str = Form("offline"),
    ) -> HTMLResponse:
        data = await file.read()
        source_mode = normalize_source_mode(mode)
        try:
            result = await analyze_upload(
                data,
                file.filename or "upload",
                settings,
                repository,
                source_mode,
            )
        except ImageValidationError as exc:
            return _ui_response(
                request,
                render_message("Invalid image", str(exc), kind="error"),
                default_mode=source_mode,
                status_code=422,
            )
        except Exception as exc:
            title = "Online analysis failed" if source_mode == "online" else "Analysis failed"
            return _ui_response(
                request,
                render_message(title, str(exc), kind="error"),
                default_mode=source_mode,
                status_code=503,
            )

        history_records = await repository.list_recent(10)
        history_html = render_history_sidebar(history_records, settings=settings)
        result_html = render_result(result, settings=settings) + history_html
        return _ui_response(request, result_html, default_mode=source_mode)