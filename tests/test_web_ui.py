from pathlib import Path

from fastapi.testclient import TestClient

from foodanalyzer import web_ui
from foodanalyzer.api import create_app
from foodanalyzer.config import Settings
from foodanalyzer.models import AnalysisResult, AnalysisStatus, IngredientResult, NutritionTotals
from foodanalyzer.storage.repository import InMemoryAnalysisRepository


def test_ui_home_has_htmx_upload_form(tmp_path):
    settings = Settings(offline_mode=True, upload_dir=tmp_path, retry_attempts=1)
    app = create_app(settings=settings, repository=InMemoryAnalysisRepository())
    client = TestClient(app)

    response = client.get("/ui")

    assert response.status_code == 200
    assert "StomachSlave" in response.text
    assert "See What's in Your Meal." in response.text
    assert "Fuel Your Goals." in response.text
    assert "How it works" in response.text
    assert 'class="how-card how-reveal"' in response.text
    assert 'tabindex="0"' in response.text
    assert "1. Upload" in response.text
    assert "2. Detect" in response.text
    assert "3. Calculate" in response.text
    assert "4. Save" in response.text
    assert "Analyze a Meal" in response.text
    assert "View History" in response.text
    assert "photo-1498837167922-ddd27525d352" in response.text
    assert "photo-1519708227418-c8fd9a32b7a2" not in response.text
    assert "VISION-LANGUAGE AI ENGINE" not in response.text
    assert "Powered by SE Integration" not in response.text
    assert "USDA Data" not in response.text
    assert "Start Analysis" not in response.text
    assert 'hx-post="/ui/analyze"' in response.text
    assert 'hx-target="#result"' in response.text
    assert 'hx-swap="innerHTML"' in response.text
    assert 'hx-encoding="multipart/form-data"' in response.text
    assert 'hx-indicator="#analyzing"' in response.text
    assert 'type="file"' in response.text
    assert 'action="/ui/analyze"' in response.text
    assert 'name="mode"' in response.text
    assert 'value="offline"' in response.text
    assert 'value="online"' in response.text
    assert 'value="offline" checked' in response.text
    assert 'hx-disabled-elt="#analyze-button"' in response.text
    assert 'id="analyze-button"' in response.text
    assert "Drag &amp; drop a meal photo here" in response.text
    assert "or click to browse your device" in response.text
    assert "JPG, PNG, WebP &bull; Max 10MB" in response.text
    assert "Run analysis" in response.text
    assert "Analyzing meal" in response.text
    assert "Identifying ingredients and calculating nutrition..." in response.text
    assert "42%" not in response.text
    assert "Image uploaded" not in response.text
    assert "Detecting ingredients" not in response.text
    assert "Calculating nutrition" not in response.text
    assert "Preparing results" not in response.text
    assert "Offline demo" in response.text
    assert "Online providers" in response.text


def test_ui_home_defaults_to_online_when_app_is_not_offline(tmp_path):
    settings = Settings(offline_mode=False, upload_dir=tmp_path, retry_attempts=1)
    app = create_app(settings=settings, repository=InMemoryAnalysisRepository())
    client = TestClient(app)

    response = client.get("/ui")

    assert response.status_code == 200
    assert 'value="online" checked' in response.text


def test_ui_analyze_offline_happy_path(tmp_path):
    settings = Settings(offline_mode=True, upload_dir=tmp_path, retry_attempts=1)
    app = create_app(settings=settings, repository=InMemoryAnalysisRepository())
    client = TestClient(app)

    with open("data/rice_chicken_broccoli.png", "rb") as f:
        response = client.post(
            "/ui/analyze",
            data={"mode": "offline"},
            files={"file": ("rice_chicken_broccoli.png", f, "image/png")},
            headers={"HX-Request": "true"},
        )

    assert response.status_code == 200
    assert "Analysis complete" in response.text
    assert "Calories" in response.text
    assert "Macronutrient Balance" in response.text
    assert "Confidence" in response.text
    assert "<table>" in response.text
    assert "broccoli" in response.text
    assert "offline" in response.text


def test_ui_analyze_rejects_invalid_upload(tmp_path):
    settings = Settings(offline_mode=True, upload_dir=tmp_path, retry_attempts=1)
    app = create_app(settings=settings, repository=InMemoryAnalysisRepository())
    client = TestClient(app)

    response = client.post(
        "/ui/analyze",
        files={"file": ("x.txt", b"hello", "text/plain")},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "Invalid image" in response.text


def test_ui_non_htmx_invalid_upload_keeps_error_status(tmp_path):
    settings = Settings(offline_mode=True, upload_dir=tmp_path, retry_attempts=1)
    app = create_app(settings=settings, repository=InMemoryAnalysisRepository())
    client = TestClient(app)

    response = client.post(
        "/ui/analyze",
        files={"file": ("x.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 422
    assert "Invalid image" in response.text


def test_ui_route_uses_service_layer_in_offline_mode(monkeypatch, tmp_path):
    settings = Settings(offline_mode=True, upload_dir=tmp_path, max_image_size_mb=1, retry_attempts=1)
    repository = InMemoryAnalysisRepository()
    app = create_app(settings=settings, repository=repository)
    client = TestClient(app)
    calls = {}

    class DummyAnalyzer:
        repository = None

        async def analyze(self, image_path: Path, *, save: bool = True):
            calls["image_path"] = image_path
            calls["save"] = save
            calls["repository"] = self.repository
            return AnalysisResult(status=AnalysisStatus.unknown_meal, image_path=str(image_path))

    def fake_save_upload_bytes(data, original_name, upload_dir, max_bytes):
        calls["data"] = data
        calls["original_name"] = original_name
        calls["upload_dir"] = upload_dir
        calls["max_bytes"] = max_bytes
        return tmp_path / "saved.png"

    def fake_build_web_analyzer(received_settings, *, offline):
        calls["settings"] = received_settings
        calls["offline"] = offline
        return DummyAnalyzer()

    monkeypatch.setattr(web_ui, "save_upload_bytes", fake_save_upload_bytes)
    monkeypatch.setattr(web_ui, "build_web_analyzer", fake_build_web_analyzer)

    response = client.post(
        "/ui/analyze",
        data={"mode": "offline"},
        files={"file": ("meal.png", b"fake image", "image/png")},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert "No meal was recognized" in response.text
    assert calls["data"] == b"fake image"
    assert calls["original_name"] == "meal.png"
    assert calls["upload_dir"] == tmp_path
    assert calls["max_bytes"] == 1024 * 1024
    assert calls["settings"] is settings
    assert calls["offline"] is True
    assert calls["image_path"] == tmp_path / "saved.png"
    assert calls["save"] is False
    assert calls["repository"] is repository


def test_ui_route_uses_service_layer_in_online_mode(monkeypatch, tmp_path):
    settings = Settings(offline_mode=True, upload_dir=tmp_path, max_image_size_mb=1, retry_attempts=1)
    repository = InMemoryAnalysisRepository()
    app = create_app(settings=settings, repository=repository)
    client = TestClient(app)
    calls = {}

    class DummyAnalyzer:
        repository = None

        async def analyze(self, image_path: Path, *, save: bool = True):
            calls["image_path"] = image_path
            calls["save"] = save
            calls["repository"] = self.repository
            return AnalysisResult(status=AnalysisStatus.unknown_meal, image_path=str(image_path))

    def fake_save_upload_bytes(data, original_name, upload_dir, max_bytes):
        calls["data"] = data
        calls["original_name"] = original_name
        calls["upload_dir"] = upload_dir
        calls["max_bytes"] = max_bytes
        return tmp_path / "saved.png"

    def fake_build_web_analyzer(received_settings, *, offline):
        calls["settings"] = received_settings
        calls["offline"] = offline
        return DummyAnalyzer()

    monkeypatch.setattr(web_ui, "save_upload_bytes", fake_save_upload_bytes)
    monkeypatch.setattr(web_ui, "build_web_analyzer", fake_build_web_analyzer)

    response = client.post(
        "/ui/analyze",
        data={"mode": "online"},
        files={"file": ("meal.png", b"fake image", "image/png")},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert calls["offline"] is False
    assert calls["settings"] is settings
    assert calls["save"] is False
    assert calls["repository"] is repository


def test_source_mode_defaults_safely_to_offline():
    assert web_ui.normalize_source_mode(None) == "offline"
    assert web_ui.normalize_source_mode("") == "offline"
    assert web_ui.normalize_source_mode("unexpected") == "offline"
    assert web_ui.is_offline_mode(None) is True
    assert web_ui.is_offline_mode("online") is False

def test_uploaded_image_route_serves_only_safe_uploads(tmp_path):
    image_path = tmp_path / "meal.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nimage")
    settings = Settings(offline_mode=True, upload_dir=tmp_path, retry_attempts=1)
    app = create_app(settings=settings, repository=InMemoryAnalysisRepository())
    client = TestClient(app)

    response = client.get("/ui/uploads/meal.png")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content == b"\x89PNG\r\n\x1a\nimage"


def test_uploaded_image_route_rejects_missing_and_traversal(tmp_path):
    settings = Settings(offline_mode=True, upload_dir=tmp_path, retry_attempts=1)
    app = create_app(settings=settings, repository=InMemoryAnalysisRepository())
    client = TestClient(app)

    assert client.get("/ui/uploads/missing.png").status_code == 404
    assert client.get("/ui/uploads/..%2Fsecret.png").status_code == 404