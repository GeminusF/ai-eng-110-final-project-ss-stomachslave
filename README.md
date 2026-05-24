# StomachSlave Food Analyzer

> A Topic 2 AI food analyzer that reads a meal photo, identifies ingredients, looks up nutrition facts, computes calories and macros, and exposes the workflow through a CLI, FastAPI API, and HTMX web UI.

**Team:** StomachSlave | **Topic:** 2 | **Course:** AI-ENG-110 Software Engineering, AI Academy

**Due:** **May 23, 2026 at 23:59 (UTC+4)**

---

## Quick Start

```powershell
# 1. Clone and install
git clone https://github.com/your-team/topic-2-food-analyzer
cd topic-2-food-analyzer
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure
copy .env.example .env
# For a no-key local demo, set OFFLINE_MODE=true in .env.
# Do not commit .env.

# 3. Run the required smoke tests and full offline suite
pytest tests/test_ai_smoke.py -v -p no:cacheprovider
pytest -p no:cacheprovider

# 4. Run the offline CLI demo
python -m foodanalyzer analyze data/rice_chicken_broccoli.png --offline
```

## Run with Docker

Build and run the app in offline demo mode:

```powershell
docker build -t foodanalyzer .
docker run --env OFFLINE_MODE=true -p 8000:8000 foodanalyzer
```

Run the app with the PostgreSQL service from Compose:

```powershell
docker compose up --build app
```

Docker Compose sets `OFFLINE_MODE=true` for the app by default, so the API and HTMX UI can run without provider keys. Open:

```text
http://localhost:8000/ui
```

To run only PostgreSQL for local online mode:

```powershell
docker compose up -d db
```

The default local database is:

```text
postgresql://postgres:dev@localhost:5432/foodanalyzer
```

## Environment Variables

The full list is in `.env.example`. Do not commit a real `.env`.

| Variable | Required? | Default | What it controls |
|---|---|---|---|
| `APP_NAME` | no | `AI Food Analyzer` | FastAPI application title |
| `OFFLINE_MODE` | no | `false` | Uses fake local providers when `true` |
| `LOG_LEVEL` | no | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `DATABASE_URL` | online, yes | `postgresql://postgres:dev@localhost:5432/foodanalyzer` | PostgreSQL history and nutrition cache connection |
| `NUTRITION_CACHE_TTL_SECONDS` | no | `86400` | TTL for repeated nutrition lookups |
| `MAX_IMAGE_SIZE_MB` | no | `5` | Maximum upload/image size |
| `MAX_CONCURRENCY` | no | `10` | Bounded parallel nutrition lookup limit |
| `RETRY_ATTEMPTS` | no | `3` | Retry attempts around AI and nutrition calls |
| `HTTP_PORT` | no | `8000` | Intended HTTP port |
| `UPLOAD_DIR` | no | `uploads` | Directory for saved uploaded images |
| `LLM_PROVIDER` | online, yes | `anthropic` | `anthropic`, `openai`, `gemini`, or app-layer `openrouter` |
| `LLM_MODEL` | online, yes | `claude-sonnet-4-6` | Vision-language model id |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_API_KEY` | provider-dependent | empty | API key for the selected built-in provider |
| `OPENROUTER_API_KEY` | OpenRouter, yes | empty | API key for OpenRouter vision models |
| `OPENROUTER_BASE_URL` | OpenRouter, no | `https://openrouter.ai/api/v1` | OpenRouter API base URL |
| `OPENROUTER_REASONING_ENABLED` | OpenRouter, no | `true` | Include OpenRouter reasoning settings |
| `OPENROUTER_REASONING_EXCLUDE` | OpenRouter, no | `true` | Ask OpenRouter to exclude reasoning from output |
| `NUTRITION_PROVIDER` | online, yes | `usda` | Nutrition provider; app layer supports `usda` |
| `USDA_API_KEY` | online, yes | empty | USDA FoodData Central key |

Offline demo mode only needs:

```text
OFFLINE_MODE=true
```

Online provider mode needs at least:

```text
OFFLINE_MODE=false
LLM_PROVIDER=openrouter
LLM_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
OPENROUTER_API_KEY=<your-openrouter-key>
USDA_API_KEY=<your-usda-key>
DATABASE_URL=postgresql+asyncpg://postgres:dev@localhost:5432/foodanalyzer
```

## How to Run the Demo

### CLI

Offline demo:

```powershell
python -m foodanalyzer analyze data/rice_chicken_broccoli.png --offline
python -m foodanalyzer analyze data/rice_chicken_broccoli.png --offline --json
python -m foodanalyzer analyze data/no_meal_blue.png --offline
```

Online mode uses `.env` provider settings:

```powershell
python -m foodanalyzer analyze data/rice_chicken_broccoli.png
```

Analysis history:

```powershell
python -m foodanalyzer history --limit 10
```

### HTTP API

Start the FastAPI app:

```powershell
uvicorn foodanalyzer.api:app --host 0.0.0.0 --port 8000
```

Analyze an image:

```powershell
curl.exe -X POST http://localhost:8000/analyze -F "file=@data/rice_chicken_broccoli.png"
```

Expected response shape:

```json
{
  "id": "analysis-id",
  "status": "completed",
  "image_path": "uploads/example.png",
  "ingredients": [
    {
      "name": "white rice (cooked)",
      "grams": 180.0,
      "confidence": 0.95,
      "nutrition": {
        "kcal": 234.0,
        "protein_g": 4.86,
        "carbs_g": 50.4,
        "fat_g": 0.54
      },
      "source": "offline"
    }
  ],
  "totals": {
    "kcal": 509.0,
    "protein_g": 53.56,
    "carbs_g": 56.0,
    "fat_g": 6.27
  },
  "warnings": [],
  "error_message": null,
  "created_at": "2026-05-24T00:00:00Z"
}
```

Other endpoints:

```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/analyses
curl.exe http://localhost:8000/analyses/<analysis_id>
```

### Web UI

The HTMX UI is served by the same FastAPI app:

```text
http://localhost:8000/ui
```

The UI includes a `StomachSlave` home page, drag-and-drop upload, offline/online mode switcher, result cards with uploaded thumbnails, and history loading through `GET /ui/history/{analysis_id}`.

## Sequential vs Concurrent Benchmark

The benchmark compares sequential nutrition lookup with bounded concurrent lookup using the same ingredients and a cleared local cache.

| Workload | N | Sequential | Concurrent (sem=10) | Speedup |
|---|---:|---:|---:|---:|
| Offline nutrition lookup for `data/rice_chicken_broccoli.png` | 3 | 0.0009 s | 0.0004 s | 2.25x |

Reproduce:

```powershell
python scripts\bench.py --image data\rice_chicken_broccoli.png
```

The offline benchmark uses fake local providers, so the absolute timings are tiny. In online mode, the expected bottlenecks after parallelization are provider latency, USDA API latency, rate limits, and PostgreSQL writes/cache hits.

## Testing

Run the required smoke tests:

```powershell
pytest tests/test_ai_smoke.py -v -p no:cacheprovider
```

Run all tests:

```powershell
pytest -p no:cacheprovider
```

Run coverage with the project threshold when `pytest-cov` is installed in the active environment:

```powershell
pytest --cov=foodanalyzer --cov-fail-under=60 --cov-report=term-missing -p no:cacheprovider
```

The tests are designed to run offline with fake or mocked AI/provider behavior. The provided `tests/test_ai_smoke.py` remains enabled for grading.

## Project Layout

```text
.
|-- ai/                         # Provided AI module, kept unchanged
|   |-- calculator.py
|   |-- nutrition.py
|   |-- schemas.py
|   |-- vlm.py
|   `-- providers/
|-- foodanalyzer/
|   |-- api.py                  # FastAPI HTTP API and web UI registration
|   |-- cli.py                  # Typer CLI
|   |-- config.py               # Pydantic settings from environment
|   |-- models.py               # Pydantic response/storage models
|   |-- web_ui.py               # HTMX pages and fragments
|   |-- concurrency/            # Bounded async nutrition lookup
|   |-- core/                   # Analyzer business workflow
|   |-- providers/              # App-layer OpenRouter VLM support
|   |-- services/               # AI wrapper, retries, rate limiting, cache
|   |-- storage/                # PostgreSQL and in-memory repositories
|   `-- utils/                  # Image validation and upload helpers
|-- tests/                      # Offline tests plus required AI smoke tests
|-- data/                       # Synthetic sample meal images
|-- scripts/
|   `-- bench.py                # Sequential vs concurrent benchmark
|-- docker-compose.yml
|-- Dockerfile
|-- pyproject.toml
|-- requirements.txt
|-- .env.example
|-- STUDENT_README_TEMPLATE.md
`-- README.md
```

## Architecture in One Diagram

```text
+-----------+   +-------------+   +----------+
|    CLI    |   | FastAPI API  |   | HTMX UI  |
+-----+-----+   +------+------+   +----+-----+
      |                |               |
      +----------------+---------------+
                       |
                       v
              +-----------------+
              | AnalyzerService |
              +--------+--------+
                       |
                       v
              +-----------------+
              |    AIService    |
              | retries/logging |
              +---+---------+---+
                  |         |
                  v         v
          +-----------+  +----------------+
          | ai/ VLM   |  | Nutrition      |
          | provided  |  | provider/cache |
          +-----------+  +--------+-------+
                                |
                                v
                       +------------------+
                       | PostgreSQL /     |
                       | in-memory store  |
                       +------------------+
```

## Implementation Notes

- The provided `ai/` package is copied unchanged.
- Application code goes through `foodanalyzer.services.ai_service.AIService` instead of calling provider SDKs directly from routes or UI code.
- Offline mode uses `OfflineVLM`, `OfflineNutritionProvider`, in-memory history, and in-memory TTL nutrition cache.
- Online mode uses the configured VLM, USDA nutrition provider, PostgreSQL analysis history, and PostgreSQL-backed nutrition cache.
- Nutrition lookups run in parallel with bounded concurrency through `foodanalyzer.concurrency.pipeline`.
- Image validation rejects unsupported file types and oversized uploads.
- The `unknown_meal` result is treated as normal control flow and returns structured output.

## OpenRouter Notes

OpenRouter support is implemented in the application layer and does not modify the provided `ai/` package.

Example `.env` values:

```text
LLM_PROVIDER=openrouter
LLM_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free
OPENROUTER_API_KEY=<your-key>
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_REASONING_ENABLED=false
OPENROUTER_REASONING_EXCLUDE=false
```

Topic 2 requires a model that can read images. If OpenRouter returns an image-input error or empty/non-JSON response, keep the configured model unchanged unless the project owner chooses a different teacher-approved vision model.

If USDA lookup fails with a proxy error pointing at `127.0.0.1:9`, clear `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY` before starting the server, or add `api.nal.usda.gov` to `NO_PROXY`.

## Limitations

- Offline benchmark timings prove orchestration behavior, not real provider speed.
- Online mode depends on external VLM and USDA availability, credentials, and rate limits.
- There is no multi-provider failover if the selected VLM provider fails.
- Uploaded files and local PostgreSQL data are runtime artifacts and are not intended to be committed.
- Nutrition matching depends on USDA search quality and the ingredient names returned by the vision model.

## Tools & Acknowledgements

This project uses the provided course `ai/` package for vision-language ingredient identification, USDA nutrition lookup, and totals calculation. The software-engineering layer adds configuration, storage, retries, caching, concurrency, validation, CLI, HTTP API, HTMX UI, Docker, and offline tests around that provided module.

AI coding assistants were used during development for implementation support and README preparation.

## License

This is academic coursework for AI-ENG-110 Software Engineering. It is not published as a production library.
