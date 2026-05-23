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
    
    @app.get("/ui/history/{analysis_id}", response_class=HTMLResponse)
    async def ui_get_history_item(request: Request, analysis_id: str) -> HTMLResponse:
        record = await repository.get(analysis_id)
        if record is None:
            return HTMLResponse(
                render_message("Not Found", "Analysis record not found", kind="error"),
                status_code=404,
            )
        return HTMLResponse(render_result(record, settings=settings))

def normalize_source_mode(mode: str | None) -> str:
    return "online" if mode == "online" else "offline"


def is_offline_mode(mode: str | None) -> bool:
    return normalize_source_mode(mode) == "offline"


def default_source_mode(settings: Settings) -> str:
    return "offline" if settings.offline_mode else "online"

def extract_meal_name(image_path: str) -> str:
    stem = Path(image_path).stem
    if len(stem) > 32 and re.match(r"^[0-9a-fA-F]{32}_", stem):
        name = stem[33:]
    else:
        name = stem
    return name.replace("_", " ").title()


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%b %d, %H:%M")


def safe_upload_image_path(filename: str, settings: Settings) -> Path | None:
    if "/" in filename or "\\" in filename or filename in {"", ".", ".."}:
        return None
    image_path = (settings.upload_dir / filename).resolve()
    upload_root = settings.upload_dir.resolve()
    if upload_root != image_path.parent:
        return None
    if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return None
    if not image_path.is_file():
        return None
    return image_path


def image_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return "image/jpeg"

def upload_image_url(image_path: str, settings: Settings | None) -> str | None:
    if settings is None:
        return None
    path = Path(image_path)
    try:
        resolved = path.resolve()
        upload_root = settings.upload_dir.resolve()
    except OSError:
        return None
    if resolved.parent != upload_root:
        return None
    if resolved.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return None
    if not resolved.is_file():
        return None
    return f"/ui/uploads/{quote(resolved.name)}"


def _ui_response(
    request: Request,
    fragment: str,
    *,
    default_mode: str = "offline",
    status_code: int = 200,
) -> HTMLResponse:
    if request.headers.get("HX-Request") == "true":
        return HTMLResponse(fragment, status_code=200)
    return HTMLResponse(
        render_page(fragment, default_mode=default_mode),
        status_code=status_code,
    )

PAGE_CSS = """
:root {
  --bg-color: #f7f9f8;
  --card-bg: #ffffff;
  --text-main: #17212b;
  --text-muted: #607080;
  --green-primary: #2f8f3a;
  --green-dark: #24752d;
  --green-light: #edf8ef;
  --border-color: #e6ece8;
  --orange-primary: #f59e0b;
  --fat-orange: #f97316;
  --danger: #d94848;
  --danger-light: #fff1f1;
  --shadow-sm: 0 3px 12px rgba(23, 33, 43, 0.05);
  --shadow-md: 0 14px 42px rgba(23, 33, 43, 0.08);
  --radius-sm: 10px;
  --radius-md: 16px;
  --radius-lg: 24px;
  --page-max: 1220px;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: var(--text-main);
  background: radial-gradient(circle at top right, rgba(47, 143, 58, 0.07), transparent 28rem), var(--bg-color);
  line-height: 1.5;
}

button,
input {
  font: inherit;
}

.site-header {
  position: sticky;
  top: 0;
  z-index: 20;
  background: rgba(255, 255, 255, 0.94);
  border-bottom: 1px solid var(--border-color);
  box-shadow: 0 4px 20px rgba(23, 33, 43, 0.04);
  backdrop-filter: blur(12px);
}

.header-inner {
  max-width: var(--page-max);
  margin: 0 auto;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
  color: var(--text-main);
}

.brand-mark {
  width: 42px;
  height: 42px;
  color: var(--green-primary);
  flex: 0 0 auto;
}

.brand-name {
  font-size: 23px;
  line-height: 1;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.brand-accent {
  color: var(--green-primary);
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 34px;
}

.nav-tab {
  border: 0;
  background: transparent;
  color: #465464;
  font-weight: 700;
  padding: 10px 0;
  cursor: pointer;
  position: relative;
}

.nav-tab.active {
  color: var(--green-primary);
}

.nav-tab.active::after {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  bottom: 1px;
  height: 3px;
  border-radius: 999px;
  background: var(--green-primary);
}

.page-shell {
  max-width: var(--page-max);
  margin: 0 auto;
  padding: 54px 24px 64px;
}

.section-view {
  display: none;
}

.section-view.active {
  display: block;
}

.hero-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.88fr) minmax(480px, 1.12fr);
  gap: 70px;
  align-items: center;
}

.hero-copy {
  padding-left: 10px;
}

.hero-title {
  margin: 0;
  font-size: clamp(42px, 5vw, 66px);
  line-height: 1.12;
  letter-spacing: -0.045em;
  font-weight: 850;
}

.hero-title .green-line {
  display: block;
  color: var(--green-primary);
}

.hero-subtitle {
  margin: 24px 0 0;
  max-width: 520px;
  color: var(--text-muted);
  font-size: 18px;
  line-height: 1.7;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 22px;
  margin-top: 40px;
  flex-wrap: wrap;
}

.btn {
  border: 1px solid transparent;
  border-radius: 9px;
  min-height: 52px;
  padding: 0 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-weight: 800;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.btn svg {
  width: 20px;
  height: 20px;
}

.btn-primary {
  background: linear-gradient(180deg, #39a344, var(--green-primary));
  color: #ffffff;
  box-shadow: 0 12px 26px rgba(47, 143, 58, 0.22);
}

.btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 16px 30px rgba(47, 143, 58, 0.26);
}

.btn-secondary {
  background: #ffffff;
  color: #344253;
  border-color: #d7dfdb;
  box-shadow: var(--shadow-sm);
}

.hero-visual {
  position: relative;
  min-height: 430px;
}

.hero-image-card {
  position: relative;
  padding: 28px;
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.88);
  box-shadow: var(--shadow-md);
}

.hero-image-card::before {
  content: "";
  position: absolute;
  inset: 12px;
  border-radius: 20px;
  border: 1px solid rgba(230, 236, 232, 0.8);
  pointer-events: none;
}

.hero-image {
  width: 100%;
  height: 360px;
  object-fit: cover;
  display: block;
  border-radius: 999px;
}

.floating-card {
  position: absolute;
  min-width: 132px;
  display: grid;
  grid-template-columns: 34px 1fr;
  gap: 12px;
  align-items: center;
  padding: 14px 16px;
  border-radius: 15px;
  background: #ffffff;
  box-shadow: 0 18px 34px rgba(23, 33, 43, 0.12);
  border: 1px solid rgba(230, 236, 232, 0.8);
}

.floating-card svg,
.work-icon svg,
.metric-icon svg {
  width: 28px;
  height: 28px;
  color: var(--green-primary);
}

.floating-card span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}

.floating-card strong {
  display: block;
  margin-top: 1px;
  font-size: 17px;
}

.card-calories {
  top: 48px;
  left: 22px;
}

.card-protein {
  top: 160px;
  right: -34px;
}

.card-carbs {
  bottom: 88px;
  left: 18px;
}

.card-fats {
  right: 56px;
  bottom: 28px;
}

.how-card {
  margin: 44px auto 0;
  padding: 18px 32px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(230, 236, 232, 0.9);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  outline: none;
}

.how-card h2 {
  margin: 0;
  text-align: center;
  font-size: 21px;
  cursor: default;
}

.work-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 28px;
  max-height: 0;
  margin-top: 0;
  opacity: 0;
  overflow: hidden;
  pointer-events: none;
  transform: translateY(-8px);
  transition: max-height 0.28s ease, margin-top 0.28s ease, opacity 0.2s ease, transform 0.28s ease;
}

.how-card:hover .work-grid,
.how-card:focus .work-grid,
.how-card:focus-within .work-grid {
  max-height: 280px;
  margin-top: 18px;
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.work-step {
  position: relative;
  min-height: 150px;
  padding: 26px 22px;
  text-align: center;
  background: #ffffff;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  box-shadow: var(--shadow-sm);
}

.work-step:not(:last-child)::after {
  content: ">";
  position: absolute;
  right: -20px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--green-primary);
  font-size: 28px;
  font-weight: 400;
}

.work-icon {
  width: 54px;
  height: 54px;
  margin: 0 auto 14px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: var(--green-light);
}

.work-step h3 {
  margin: 0 0 8px;
  font-size: 17px;
}

.work-step p {
  margin: 0;
  color: var(--text-muted);
  font-size: 14px;
}

.analyze-stack {
  max-width: 1040px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
}

.upload-card {
  padding: 20px;
}

.dropzone {
  min-height: 165px;
  border: 1.5px dashed rgba(47, 143, 58, 0.55);
  border-radius: 13px;
  background: linear-gradient(180deg, #ffffff, #fbfdfb);
  display: grid;
  place-items: center;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.18s ease, background 0.18s ease, transform 0.18s ease;
  overflow: hidden;
}

.dropzone.dragover {
  border-color: var(--green-primary);
  background: var(--green-light);
  transform: scale(1.01);
}

.dropzone-content svg {
  width: 36px;
  height: 36px;
  color: var(--green-primary);
}

.dropzone-title {
  margin: 10px 0 2px;
  font-size: 17px;
  font-weight: 800;
}

.dropzone-subtitle {
  margin: 0;
  color: var(--text-muted);
  font-size: 14px;
}

.dropzone-hint {
  margin: 12px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  letter-spacing: 0.04em;
}

.hidden-file-input,
.hidden {
  display: none !important;
}

.dropzone-preview {
  position: relative;
  width: 100%;
  max-height: 210px;
}

.dropzone-preview img {
  width: 100%;
  height: 210px;
  object-fit: cover;
  display: block;
}

.preview-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(23, 33, 43, 0.36);
  opacity: 0;
  transition: opacity 0.18s ease;
}

.dropzone-preview:hover .preview-overlay {
  opacity: 1;
}

.btn-change-image {
  border: 1px solid var(--border-color);
  border-radius: 999px;
  background: #ffffff;
  color: var(--text-main);
  padding: 9px 16px;
  font-weight: 800;
  cursor: pointer;
}

.analyze-controls {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

.source-options {
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(170px, 1fr));
  gap: 10px;
  padding: 0;
  margin: 0;
  border: 0;
}

.source-option {
  border: 1px solid #dfe7e2;
  border-radius: 999px;
  padding: 9px 16px;
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #566575;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
  background: #ffffff;
}

.source-option:has(input:checked) {
  border-color: var(--green-primary);
  background: var(--green-light);
  color: var(--green-primary);
  box-shadow: inset 0 0 0 1px rgba(47, 143, 58, 0.12);
}

.source-option input {
  width: 1px;
  height: 1px;
  opacity: 0;
  position: absolute;
}

.source-option svg {
  width: 16px;
  height: 16px;
}

.run-button {
  width: min(260px, 100%);
}

.image-warning {
  margin: 10px auto 0;
  max-width: 430px;
  padding: 10px 12px;
  border-radius: 10px;
  color: #9a3412;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  text-align: center;
  font-size: 13px;
  font-weight: 700;
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20%, 60% { transform: translateX(-6px); }
  40%, 80% { transform: translateX(6px); }
}

.shake {
  animation: shake 0.42s ease-in-out;
  border-color: var(--orange-primary) !important;
  box-shadow: 0 0 0 5px rgba(245, 158, 11, 0.11);
}

.loading-card {
  display: none;
  padding: 16px 20px;
  align-items: center;
  gap: 14px;
}

.loading-card.htmx-request,
.htmx-request .loading-card {
  display: flex;
}

.loading-pulse {
  width: 34px;
  height: 34px;
  border-radius: 999px;
  border: 3px solid var(--green-light);
  border-top-color: var(--green-primary);
  animation: loading-spin 0.8s linear infinite;
  flex: 0 0 auto;
}

@keyframes loading-spin {
  to { transform: rotate(360deg); }
}

.loading-copy {
  min-width: 0;
}

.loading-copy h3 {
  margin: 0 0 3px;
  font-size: 15px;
}

.loading-copy p {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}

.result-pane {
  min-height: 0;
}

.empty-state {
  padding: 42px 24px;
  text-align: center;
  color: var(--text-muted);
}

.empty-state h3 {
  margin: 0 0 6px;
  color: var(--text-main);
}

.result-card {
  padding: 18px 18px 16px;
}

.result-top {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(520px, 1.55fr);
  gap: 22px;
  align-items: stretch;
}

.meal-summary {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 16px;
  align-items: center;
}

.meal-thumb {
  width: 110px;
  height: 86px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  overflow: hidden;
  color: #ffffff;
  background:
    radial-gradient(circle at 32% 34%, #f59e0b 0 14%, transparent 15%),
    radial-gradient(circle at 60% 44%, #2f8f3a 0 19%, transparent 20%),
    linear-gradient(135deg, #f7c66a, #2f8f3a);
  box-shadow: var(--shadow-sm);
}

.meal-thumb svg {
  width: 40px;
  height: 40px;
  filter: drop-shadow(0 2px 6px rgba(0, 0, 0, 0.18));
}

.meal-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.meal-title {
  margin: 0 0 5px;
  font-size: 20px;
  font-weight: 850;
  letter-spacing: -0.02em;
}

.meal-weight {
  margin: 0 0 10px;
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 700;
}

.result-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--green-primary);
  font-size: 12px;
  font-weight: 800;
}

.result-status::before {
  content: "";
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: var(--green-primary);
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.metric-card {
  min-height: 86px;
  padding: 15px 16px;
  border: 1px solid var(--border-color);
  border-radius: 13px;
  background: #ffffff;
  box-shadow: var(--shadow-sm);
  display: grid;
  grid-template-columns: 34px 1fr;
  gap: 11px;
  align-items: center;
}

.metric-card span {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
}

.metric-card strong {
  display: block;
  margin-top: 2px;
  font-size: 22px;
  line-height: 1.05;
}

.metric-card small {
  color: var(--text-muted);
  font-weight: 700;
}

.macro-section {
  margin-top: 18px;
}

.macro-section h4 {
  margin: 0 0 10px;
  font-size: 13px;
}

.macro-bar {
  height: 10px;
  border-radius: 999px;
  overflow: hidden;
  display: flex;
  background: #f0f4f1;
}

.macro-segment.protein {
  background: var(--green-primary);
}

.macro-segment.carbs {
  background: #facc15;
}

.macro-segment.fat {
  background: var(--fat-orange);
}

.macro-legend {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 26px;
  margin-top: 10px;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
}

.legend-dot.protein {
  background: var(--green-primary);
}

.legend-dot.carbs {
  background: #facc15;
}

.legend-dot.fat {
  background: var(--fat-orange);
}

.table-responsive {
  margin-top: 16px;
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

th,
td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--border-color);
  text-align: left;
  white-space: nowrap;
}

th {
  color: #526171;
  font-size: 11px;
  font-weight: 800;
}

.ingredient-name {
  font-weight: 800;
}

.confidence-cell {
  min-width: 118px;
}

.confidence-label {
  color: var(--green-primary);
  font-weight: 800;
  margin-right: 8px;
}

.confidence-track {
  display: inline-block;
  width: 74px;
  height: 5px;
  border-radius: 999px;
  vertical-align: middle;
  background: #e7efe9;
  overflow: hidden;
}

.confidence-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--green-primary);
}

.row-total {
  font-weight: 850;
  background: #fbfdfb;
}

.history-card {
  padding: 18px;
}

.history-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
}

.history-heading h2 {
  margin: 0;
  font-size: 18px;
}

.view-all {
  border: 1px solid #d8e6dc;
  border-radius: 999px;
  background: #ffffff;
  color: var(--green-primary);
  padding: 8px 13px;
  font-size: 12px;
  font-weight: 850;
  cursor: pointer;
}

.history-list {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding: 2px 4px 8px;
  scroll-snap-type: x proximity;
}

.history-list::-webkit-scrollbar {
  height: 6px;
}

.history-list::-webkit-scrollbar-thumb {
  background: #dce6e0;
  border-radius: 999px;
}

.history-item {
  flex: 0 0 246px;
  border: 1px solid var(--border-color);
  border-radius: 14px;
  background: #ffffff;
  padding: 10px;
  display: grid;
  grid-template-columns: 58px 1fr 46px;
  gap: 10px;
  align-items: center;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
  scroll-snap-align: start;
  transition: border-color 0.18s ease, transform 0.18s ease;
}

.history-item:hover {
  border-color: rgba(47, 143, 58, 0.5);
  transform: translateY(-2px);
}

.history-thumb {
  width: 58px;
  height: 58px;
  border-radius: 12px;
  background:
    radial-gradient(circle at 35% 35%, #f97316 0 18%, transparent 19%),
    radial-gradient(circle at 64% 58%, #2f8f3a 0 20%, transparent 21%),
    #f5faf6;
  border: 1px solid var(--border-color);
  overflow: hidden;
}

.history-thumb-img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.history-name {
  display: block;
  color: var(--text-main);
  font-size: 12px;
  font-weight: 850;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 118px;
}

.history-date {
  display: block;
  margin-top: 3px;
  color: var(--text-muted);
  font-size: 11px;
}

.history-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 5px;
  color: var(--green-primary);
  font-size: 11px;
  font-weight: 800;
}

.history-status::before {
  content: "";
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--green-primary);
}

.history-kcal {
  justify-self: end;
  text-align: right;
  font-weight: 850;
  font-size: 14px;
}

.history-kcal span {
  display: block;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 700;
}

.history-empty {
  width: 100%;
  margin: 0;
  color: var(--text-muted);
  padding: 14px 0;
  text-align: center;
}

.message-box {
  display: flex;
  gap: 14px;
  padding: 18px 20px;
  border-radius: var(--radius-md);
  border: 1px solid #f0caca;
  background: var(--danger-light);
  color: var(--text-main);
}

.message-box.warning {
  border-color: #f1d390;
  background: #fff9eb;
}

.message-box.error {
  border-color: #efb0b0;
  background: #fff1f1;
}

.message-box-icon {
  width: 28px;
  height: 28px;
  flex: 0 0 auto;
  color: var(--danger);
}

.message-box.warning .message-box-icon {
  color: var(--orange-primary);
}

.message-box h4 {
  margin: 0 0 4px;
  font-size: 16px;
}

.message-box p,
.message-box ul {
  margin: 0;
  color: #4c5967;
}

.message-box ul {
  padding-left: 20px;
}

@media (max-width: 1020px) {
  .hero-grid {
    grid-template-columns: 1fr;
    gap: 34px;
  }

  .hero-copy {
    padding-left: 0;
    text-align: center;
  }

  .hero-subtitle {
    margin-left: auto;
    margin-right: auto;
  }

  .hero-actions {
    justify-content: center;
  }

  .hero-visual {
    min-height: 0;
  }

  .work-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .work-step::after {
    display: none;
  }

  .result-top {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .header-inner {
    padding: 14px 16px;
  }

  .brand-name {
    font-size: 20px;
  }

  .nav-links {
    gap: 18px;
  }

  .page-shell {
    padding: 32px 14px 48px;
  }

  .hero-image {
    height: 300px;
  }

  .floating-card {
    position: static;
    margin-top: 10px;
  }

  .hero-image-card {
    display: grid;
    gap: 10px;
  }

  .work-grid,
  .metrics-row,
  .source-options {
    grid-template-columns: 1fr;
  }

  .how-card:hover .work-grid,
  .how-card:focus .work-grid,
  .how-card:focus-within .work-grid {
    max-height: 900px;
  }

  .loading-card {
    align-items: flex-start;
    flex-direction: column;
  }

  .meal-summary {
    grid-template-columns: 1fr;
  }

  .meal-thumb {
    width: 100%;
    height: 120px;
  }
}
"""


PAGE_JS = """
document.addEventListener("DOMContentLoaded", () => {
  const fileInput = document.getElementById("file");
  const dropzone = document.getElementById("dropzone");
  const dropzoneDefault = document.getElementById("dropzone-default");
  const dropzonePreview = document.getElementById("dropzone-preview");
  const previewImg = document.getElementById("preview-image");
  const changeBtn = document.getElementById("change-image-btn");
  const analyzeForm = document.getElementById("analyze-form");
  const imageWarning = document.getElementById("image-warning");
  const tabHome = document.getElementById("tab-home");
  const tabAnalyze = document.getElementById("tab-analyze");
  const btnStart = document.getElementById("btn-hero-start");
  const btnHistory = document.getElementById("btn-hero-history");
  const heroPage = document.getElementById("hero-page");
  const analyzePage = document.getElementById("analyze-page");
  const historyCard = document.getElementById("history-card");

  function showHome() {
    if (tabHome) tabHome.classList.add("active");
    if (tabAnalyze) tabAnalyze.classList.remove("active");
    if (heroPage) heroPage.classList.add("active");
    if (analyzePage) analyzePage.classList.remove("active");
  }

  function showAnalyze() {
    if (tabHome) tabHome.classList.remove("active");
    if (tabAnalyze) tabAnalyze.classList.add("active");
    if (heroPage) heroPage.classList.remove("active");
    if (analyzePage) analyzePage.classList.add("active");
  }

  function clearWarning() {
    if (imageWarning) imageWarning.classList.add("hidden");
  }

  function showWarning() {
    if (dropzone) {
      dropzone.classList.remove("shake");
      void dropzone.offsetWidth;
      dropzone.classList.add("shake");
      setTimeout(() => dropzone.classList.remove("shake"), 430);
    }
    if (imageWarning) imageWarning.classList.remove("hidden");
  }

  if (tabHome) tabHome.addEventListener("click", showHome);
  if (tabAnalyze) tabAnalyze.addEventListener("click", showAnalyze);
  if (btnStart) btnStart.addEventListener("click", showAnalyze);
  if (btnHistory) {
    btnHistory.addEventListener("click", () => {
      showAnalyze();
      if (historyCard) historyCard.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  if (analyzeForm) {
    analyzeForm.addEventListener("submit", (e) => {
      if (!fileInput || fileInput.files.length === 0) {
        e.preventDefault();
        e.stopPropagation();
        showWarning();
      }
    });
  }

  document.body.addEventListener("htmx:beforeRequest", (evt) => {
    if (evt.detail && evt.detail.target && evt.detail.target.id === "result") {
      showAnalyze();
    }
  });

  if (dropzone) {
    dropzone.addEventListener("click", (e) => {
      if (!changeBtn || (e.target !== changeBtn && !changeBtn.contains(e.target))) {
        fileInput.click();
      }
    });

    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", () => {
      dropzone.classList.remove("dragover");
    });

    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        showPreview(e.dataTransfer.files[0]);
        clearWarning();
      }
    });
  }

  if (fileInput) {
    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) {
        showPreview(fileInput.files[0]);
        clearWarning();
      }
    });
  }

  if (changeBtn) {
    changeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      fileInput.value = "";
      previewImg.src = "";
      dropzonePreview.classList.add("hidden");
      dropzoneDefault.classList.remove("hidden");
    });
  }

  function showPreview(file) {
    if (file && file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = (e) => {
        previewImg.src = e.target.result;
        dropzoneDefault.classList.add("hidden");
        dropzonePreview.classList.remove("hidden");
      };
      reader.readAsDataURL(file);
    }
  }

  document.body.addEventListener("htmx:afterRequest", (evt) => {
    if (evt.detail.successful && evt.detail.elt.tagName === "FORM") {
      if (fileInput) fileInput.value = "";
      if (previewImg) previewImg.src = "";
      if (dropzonePreview) dropzonePreview.classList.add("hidden");
      if (dropzoneDefault) dropzoneDefault.classList.remove("hidden");
    }
  });
});
"""


def render_skeleton() -> str:
    return render_loading_card()


def render_page(
    result_html: str = "",
    *,
    default_mode: str = "offline",
    history: Sequence[AnalysisResult] | None = None,
    settings: Settings | None = None,
) -> str:
    offline_checked = " checked" if normalize_source_mode(default_mode) == "offline" else ""
    online_checked = " checked" if normalize_source_mode(default_mode) == "online" else ""
    history = history or []
    history_sidebar_html = render_history_sidebar(history, settings=settings)

    if not result_html:
        result_html = """
        <div class="card empty-state">
          <h3>Ready when your plate is.</h3>
          <p>Upload a clear meal photo above or open a previous analysis from history.</p>
        </div>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>StomachSlave</title>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <style>{PAGE_CSS}</style>
</head>
<body>
  <header class="site-header">
    <div class="header-inner">
      <a class="brand" href="#" aria-label="StomachSlave" id="brand-home">
        {logo_svg()}
        <span class="brand-name"><span>Stomach</span><span class="brand-accent">Slave</span></span>
      </a>
      <nav class="nav-links" aria-label="Primary">
        <button type="button" class="nav-tab active" id="tab-home">Home</button>
        <button type="button" class="nav-tab" id="tab-analyze">Analyze</button>
      </nav>
    </div>
  </header>

  <main class="page-shell">
    <section id="hero-page" class="section-view active">
      <div class="hero-grid">
        <div class="hero-copy">
          <h1 class="hero-title">See What's in Your Meal.<span class="green-line">Fuel Your Goals.</span></h1>
          <p class="hero-subtitle">Upload a meal photo. We'll identify ingredients, calculate nutrition, and give you clear insights in seconds.</p>
          <div class="hero-actions">
            <button type="button" class="btn btn-primary" id="btn-hero-start">
              {upload_svg()} Analyze a Meal
            </button>
            <button type="button" class="btn btn-secondary" id="btn-hero-history">
              {clock_svg()} View History
            </button>
          </div>
        </div>
        <div class="hero-visual">
          <div class="hero-image-card">
            <img class="hero-image" src="https://images.unsplash.com/photo-1498837167922-ddd27525d352?w=900&auto=format&fit=crop&q=85" alt="Healthy meal plate with greens and vegetables">
            {floating_metric("Calories", "482 kcal", "card-calories", drop_svg())}
            {floating_metric("Protein", "32.7 g", "card-protein", leaf_svg())}
            {floating_metric("Carbs", "41.2 g", "card-carbs", pie_svg())}
            {floating_metric("Fats", "21.6 g", "card-fats", drop_svg())}
          </div>
        </div>
      </div>
      <section class="how-card how-reveal" aria-labelledby="how-title" tabindex="0">
        <h2 id="how-title">How it works</h2>
        <div class="work-grid">
          {work_step("1. Upload", "Upload a clear photo of your meal.", image_svg())}
          {work_step("2. Detect", "Our AI identifies ingredients instantly.", search_svg())}
          {work_step("3. Calculate", "We calculate nutrition in seconds.", chart_svg())}
          {work_step("4. Save", "View and track your meal history.", history_svg())}
        </div>
      </section>
    </section>

    <section id="analyze-page" class="section-view">
      <div class="analyze-stack">
        <section class="card upload-card" aria-label="Analyze meal">
          <form id="analyze-form" action="/ui/analyze" method="post" enctype="multipart/form-data"
            hx-post="/ui/analyze" hx-target="#result" hx-swap="innerHTML"
            hx-encoding="multipart/form-data" hx-indicator="#analyzing"
            hx-disabled-elt="#analyze-button">
            <div class="dropzone" id="dropzone">
              <div class="dropzone-content" id="dropzone-default">
                {cloud_svg()}
                <p class="dropzone-title">Drag &amp; drop a meal photo here</p>
                <p class="dropzone-subtitle">or click to browse your device</p>
                <p class="dropzone-hint">JPG, PNG, WebP &bull; Max 10MB</p>
              </div>
              <div class="dropzone-preview hidden" id="dropzone-preview">
                <img id="preview-image" src="" alt="Meal preview">
                <div class="preview-overlay">
                  <button type="button" class="btn-change-image" id="change-image-btn">Change image</button>
                </div>
              </div>
              <input id="file" name="file" type="file" accept="image/png,image/jpeg" class="hidden-file-input">
            </div>
            <div id="image-warning" class="image-warning hidden">Please choose a meal photo before running analysis.</div>
            <div class="analyze-controls">
              <fieldset class="source-options" aria-label="Analysis source">
                <label class="source-option">
                  <input type="radio" name="mode" value="offline"{offline_checked}>
                  {chart_svg()} Offline demo
                </label>
                <label class="source-option">
                  <input type="radio" name="mode" value="online"{online_checked}>
                  {cloud_small_svg()} Online providers
                </label>
              </fieldset>
              <button id="analyze-button" class="btn btn-primary run-button" type="submit">
                {sparkle_svg()} Run analysis
              </button>
            </div>
          </form>
        </section>

        {render_loading_card()}

        <section id="result" class="result-pane" aria-live="polite">
          {result_html}
        </section>

        <section class="card history-card" id="history-card">
          <div class="history-heading">
            <h2>Analysis History</h2>
            <button class="view-all" type="button">View all history &gt;</button>
          </div>
          {history_sidebar_html}
        </section>
      </div>
    </section>
  </main>

  <script>{PAGE_JS}</script>
</body>
</html>"""

def render_loading_card() -> str:
    return """
    <section id="analyzing" class="card loading-card" role="status" aria-live="polite">
      <span class="loading-pulse" aria-hidden="true"></span>
      <div class="loading-copy">
        <h3>Analyzing meal</h3>
        <p>Identifying ingredients and calculating nutrition...</p>
      </div>
    </section>
    """

def render_history_sidebar(
    history: Sequence[AnalysisResult],
    *,
    settings: Settings | None = None,
) -> str:
    if not history:
        return """
        <div class="history-list" id="history-list" hx-swap-oob="true">
          <p class="history-empty">No past analyses recorded</p>
        </div>
        """

    items = []
    for record in history:
        status_label = record.status.value.replace("_", " ").title()
        status_class = record.status.value.lower()
        formatted_date = format_datetime(record.created_at)
        meal_name = extract_meal_name(record.image_path)
        kcal_val = record.totals.kcal
        image_url = upload_image_url(record.image_path, settings)
        if image_url:
            thumbnail_html = (
                f'<span class="history-thumb">'
                f'<img class="history-thumb-img" src="{escape(image_url)}" '
                f'alt="{escape(meal_name)} thumbnail"></span>'
            )
        else:
            thumbnail_html = '<span class="history-thumb" aria-hidden="true"></span>'
        item_html = f"""
        <button type="button" class="history-item"
          hx-get="/ui/history/{escape(record.id)}"
          hx-target="#result"
          hx-swap="innerHTML"
          hx-indicator="#analyzing">
          {thumbnail_html}
          <span>
            <span class="history-name">{escape(meal_name)}</span>
            <span class="history-date">{escape(formatted_date)}</span>
            <span class="history-status {escape(status_class)}">{escape(status_label)}</span>
          </span>
          <span class="history-kcal">{kcal_val:.0f}<span>kcal</span></span>
        </button>
        """
        items.append(item_html)

    return f"""
    <div class="history-list" id="history-list" hx-swap-oob="true">
      {"".join(items)}
    </div>
    """


def render_message(title: str, detail: str, *, kind: str) -> str:
    safe_kind = "error" if kind == "error" else "warning"
    return f"""
    <div class="message-box {safe_kind}">
      {alert_svg()}
      <div>
        <h4>{escape(title)}</h4>
        <p>{escape(detail)}</p>
      </div>
    </div>
    """

def floating_metric(label: str, value: str, class_name: str, icon: str) -> str:
    return f"""
    <div class="floating-card {escape(class_name)}">
      {icon}
      <div><span>{escape(label)}</span><strong>{escape(value)}</strong></div>
    </div>
    """


def work_step(title: str, detail: str, icon: str) -> str:
    return f"""
    <div class="work-step">
      <div class="work-icon">{icon}</div>
      <h3>{escape(title)}</h3>
      <p>{escape(detail)}</p>
    </div>
    """


def metric_card(label: str, value: str, unit: str, icon: str) -> str:
    return f"""
    <div class="metric-card">
      <span class="metric-icon">{icon}</span>
      <div>
        <span>{escape(label)}</span>
        <strong>{escape(value)}</strong>
        <small>{escape(unit)}</small>
      </div>
    </div>
    """


def icon_svg(path: str, *, extra: str = "") -> str:
    return (
        f'<svg {extra} viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{path}</svg>'
    )


def logo_svg() -> str:
    return icon_svg(
        '<circle cx="12" cy="12" r="9.5"></circle>'
        '<path d="M7.5 12.5c1.2 1.4 2.7 2.1 4.5 2.1s3.3-.7 4.5-2.1"></path>'
        '<path d="M8.4 8.4h7.2"></path>'
        '<path d="M12 4.9v5.1"></path>'
        '<path d="M9.4 6.9h5.2"></path>',
        extra='class="brand-mark" aria-hidden="true"',
    )


def upload_svg() -> str:
    return icon_svg('<path d="M12 16V4"></path><path d="m7 9 5-5 5 5"></path><path d="M5 20h14"></path>')


def clock_svg() -> str:
    return icon_svg('<circle cx="12" cy="12" r="8"></circle><path d="M12 8v5l3 2"></path>')


def cloud_svg() -> str:
    return icon_svg(
        '<path d="M16 16.5h1.5a3.5 3.5 0 0 0 .3-7 5.5 5.5 0 0 0-10.6-1.7A4.3 4.3 0 0 0 6.8 16.5H8"></path>'
        '<path d="M12 18V10"></path><path d="m8.7 13.3 3.3-3.3 3.3 3.3"></path>'
    )


def cloud_small_svg() -> str:
    return icon_svg('<path d="M17 17h.5a3.5 3.5 0 0 0 .2-7 5.5 5.5 0 0 0-10.6-1.7A4.3 4.3 0 0 0 6.8 17H8"></path><path d="m9 14 3-3 3 3"></path>')


def sparkle_svg() -> str:
    return icon_svg('<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6L12 3Z"></path><path d="M19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8L19 14Z"></path>')


def drop_svg() -> str:
    return icon_svg('<path d="M12 3s6 6.2 6 10.3A6 6 0 1 1 6 13.3C6 9.2 12 3 12 3Z"></path>')


def leaf_svg() -> str:
    return icon_svg('<path d="M20 4C11 4 5 9.8 5 17a3 3 0 0 0 3 3c7.2 0 12-7 12-16Z"></path><path d="M5 19c3.5-5.5 7.2-8.2 12-10"></path>')


def pie_svg() -> str:
    return icon_svg('<path d="M12 3v9h9"></path><path d="M20.5 15A9 9 0 1 1 9 3.5"></path>')


def image_svg() -> str:
    return icon_svg('<rect x="4" y="5" width="16" height="14" rx="2"></rect><circle cx="9" cy="10" r="1.5"></circle><path d="m20 15-4-4-7 7"></path>')


def search_svg() -> str:
    return icon_svg('<circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path>')


def chart_svg() -> str:
    return icon_svg('<path d="M5 19V9"></path><path d="M12 19V5"></path><path d="M19 19v-7"></path><path d="M4 19h16"></path>')


def history_svg() -> str:
    return icon_svg('<path d="M4 12a8 8 0 1 0 2.3-5.7"></path><path d="M4 5v4h4"></path><path d="M12 8v5l3 2"></path>')


def check_svg() -> str:
    return icon_svg('<path d="m7 12 3 3 7-7"></path>')


def clipboard_svg() -> str:
    return icon_svg('<rect x="6" y="5" width="12" height="15" rx="2"></rect><path d="M9 5a3 3 0 0 1 6 0"></path><path d="M9 12h6"></path><path d="M9 16h4"></path>')


def wheat_svg() -> str:
    return icon_svg('<path d="M12 20V4"></path><path d="M8 8c0-2.2 1.5-4 4-4 0 2.5-1.8 4-4 4Z"></path><path d="M16 8c0-2.2-1.5-4-4-4 0 2.5 1.8 4 4 4Z"></path><path d="M8 14c0-2.2 1.5-4 4-4 0 2.5-1.8 4-4 4Z"></path><path d="M16 14c0-2.2-1.5-4-4-4 0 2.5 1.8 4 4 4Z"></path>')


def plate_svg() -> str:
    return icon_svg('<circle cx="12" cy="12" r="8"></circle><circle cx="12" cy="12" r="4"></circle>')


def alert_svg() -> str:
    return icon_svg('<path d="M12 8v5"></path><path d="M12 17h.01"></path><path d="M10.3 4.3 2.8 17.2A2 2 0 0 0 4.5 20h15a2 2 0 0 0 1.7-2.8L13.7 4.3a2 2 0 0 0-3.4 0Z"></path>', extra='class="message-box-icon" aria-hidden="true"')