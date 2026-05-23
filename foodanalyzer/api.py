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
    
    @app.post("/analyze", response_model=AnalysisResult)
    async def analyze(file: UploadFile = File(...)) -> AnalysisResult:
        data = await file.read()
        try:
            image_path = save_upload_bytes(
                data,
                file.filename or "upload",
                settings.upload_dir,
                settings.max_image_bytes,
            )
        except ImageValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        analyzer = build_analyzer(settings, offline=settings.offline_mode)
        analyzer.repository = repo
        try:
            return await analyzer.analyze(image_path, save=True)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/analyses", response_model=list[AnalysisRecord])
    async def list_analyses(limit: int = 10) -> list[AnalysisRecord]:
        return await repo.list_recent(limit)

    @app.get("/analyses/{analysis_id}", response_model=AnalysisRecord)
    async def get_analysis(analysis_id: str) -> AnalysisRecord:
        record = await repo.get(analysis_id)
        if record is None:
            raise HTTPException(status_code=404, detail="analysis not found")
        return record

    return app


app = create_app()