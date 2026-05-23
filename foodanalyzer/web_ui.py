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

