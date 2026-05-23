from fastapi.testclient import TestClient

from foodanalyzer.api import create_app
from foodanalyzer.config import Settings
from foodanalyzer.storage.repository import InMemoryAnalysisRepository


def test_api_analyze_offline(tmp_path):
    settings = Settings(offline_mode=True, upload_dir=tmp_path, retry_attempts=1)
    app = create_app(settings=settings, repository=InMemoryAnalysisRepository())
    client = TestClient(app)

    with open("data/rice_chicken_broccoli.png", "rb") as f:
        response = client.post("/analyze", files={"file": ("rice_chicken_broccoli.png", f, "image/png")})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["totals"]["kcal"] > 0


def test_api_rejects_non_image(tmp_path):
    settings = Settings(offline_mode=True, upload_dir=tmp_path, retry_attempts=1)
    app = create_app(settings=settings, repository=InMemoryAnalysisRepository())
    client = TestClient(app)

    response = client.post("/analyze", files={"file": ("x.txt", b"hello", "text/plain")})

    assert response.status_code == 422


def test_api_health(tmp_path):
    settings = Settings(offline_mode=True, upload_dir=tmp_path)
    app = create_app(settings=settings, repository=InMemoryAnalysisRepository())
    client = TestClient(app)

    assert client.get("/health").json() == {"ok": True}
