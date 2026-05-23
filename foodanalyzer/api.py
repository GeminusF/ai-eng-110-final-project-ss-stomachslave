"""FastAPI HTTP server."""

from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, UploadFile

from foodanalyzer.cli import build_analyzer
from foodanalyzer.config import Settings, get_settings
from foodanalyzer.logging_config import configure_logging
from foodanalyzer.models import AnalysisRecord, AnalysisResult
from foodanalyzer.storage.repository import AnalysisRepository, InMemoryAnalysisRepository, PostgresAnalysisRepository
from foodanalyzer.utils.images import ImageValidationError, save_upload_bytes
from foodanalyzer.web_ui import register_web_ui


def create_app(
    *,
    settings: Settings | None = None,
    repository: AnalysisRepository | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    repo = repository or (
        InMemoryAnalysisRepository()
        if settings.offline_mode
        else PostgresAnalysisRepository(settings.database_url)
    )
    app = FastAPI(title=settings.app_name)
    app.state.repository = repo
    app.state.settings = settings
    register_web_ui(app, settings, repo)

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {"ok": await repo.health()}