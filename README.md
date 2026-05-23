# StomachSlave Food Analyzer

Topic 2 implementation for the AI-ENG-110 Software Engineering final project.

StomachSlave analyzes a meal photo, identifies ingredients, fetches nutrition
facts, computes totals, stores analysis history, and exposes the same business
logic through a CLI, FastAPI HTTP API, and HTMX web UI.

## Project Rules

- The provided `ai/` package is copied unchanged.
- Application code goes through the service layer instead of calling providers
  directly from UI or routes.
- Tests run offline without real API keys.
- `.env`, API keys, uploads, virtual environments, logs, and local databases are
  not committed.
- `tests/test_ai_smoke.py` stays enabled as the required integration smoke test.

## Setup

```powershell
cd "<PROJECT_ROOT>\foodanalyzer"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

For no-key local demos, set this in `.env`:

```text
OFFLINE_MODE=true
```

For online mode, configure at least:

```text
OFFLINE_MODE=false
LLM_PROVIDER=openrouter
LLM_MODEL=<teacher-approved-vision-model>
OPENROUTER_API_KEY=<your-openrouter-key>
USDA_API_KEY=<your-usda-key>
DATABASE_URL=postgresql+asyncpg://postgres:dev@localhost:5432/foodanalyzer
```

## Web UI

The HTMX UI is served by the same FastAPI app as the HTTP API.

```powershell
uvicorn foodanalyzer.api:app --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000/ui
```

The UI includes:

- A minimal `StomachSlave` home page.
- An analyze page with drag-and-drop upload.
- `Offline demo` and `Online providers` mode switcher.
- Real uploaded meal thumbnails in result and history cards.
- HTMX result updates through `POST /ui/analyze`.
- History loading through `GET /ui/history/{analysis_id}`.

`Offline demo` uses local fake providers and needs no keys. `Online providers`
uses the configured VLM, USDA, and PostgreSQL nutrition cache. If some nutrition
lookups fail, the UI can still show partial results plus warnings.

## PostgreSQL

Online mode uses PostgreSQL for:

- Analysis history.
- Persistent nutrition cache.

Start PostgreSQL with Docker Desktop running:

```powershell
docker compose up -d db
```

The default local compose database is:

```text
postgresql://postgres:dev@localhost:5432/foodanalyzer
```

If using asyncpg directly from `.env`, this project also accepts:

```text
postgresql+asyncpg://postgres:dev@localhost:5432/foodanalyzer
```

## CLI

Offline demo:

```powershell
python -m foodanalyzer analyze data/rice_chicken_broccoli.png --offline
python -m foodanalyzer analyze data/rice_chicken_broccoli.png --offline --json
```

Online mode uses `.env` provider settings:

```powershell
python -m foodanalyzer analyze data/rice_chicken_broccoli.png
```

## HTTP API

Start the server:

```powershell
uvicorn foodanalyzer.api:app --host 0.0.0.0 --port 8000
```

Analyze an image:

```powershell
curl -X POST http://localhost:8000/analyze -F "file=@data/rice_chicken_broccoli.png"
```

Other endpoints:

```powershell
curl http://localhost:8000/health
curl http://localhost:8000/analyses
curl http://localhost:8000/analyses/<analysis_id>
```

## Docker

Offline app demo:

```powershell
docker build -t foodanalyzer .
docker run --env OFFLINE_MODE=true -p 8000:8000 foodanalyzer
```

Compose app plus PostgreSQL:

```powershell
docker compose up --build app
```

Docker Compose sets `OFFLINE_MODE=true` for the app by default, so the API and
HTMX UI demo can run without provider keys. To try `Online providers` in Docker,
pass the required LLM and USDA environment variables and select `Online
providers` in the UI.

## Nutrition Cache

Offline mode uses an in-memory TTL nutrition cache. Online mode uses a
PostgreSQL-backed cache in the `nutrition_cache` table, so repeated USDA lookups
for the same normalized ingredient string are reused across process restarts and
app instances.

`NUTRITION_CACHE_TTL_SECONDS` controls both cache backends.

Nutrition lookups are also parallelized with bounded concurrency. The default
limit is controlled by:

```text
MAX_CONCURRENCY=10
```

## Tests

Run the required smoke test:

```powershell
pytest tests/test_ai_smoke.py -v -p no:cacheprovider
```

Run all tests:

```powershell
pytest -p no:cacheprovider
```

Run coverage with the project threshold:

```powershell
pytest --cov=foodanalyzer --cov-fail-under=60 --cov-report=term-missing -p no:cacheprovider
```

## GitHub Actions CI

Bonus 3 is implemented in `.github/workflows/ci.yml`.

CI runs on pull requests to `main` and includes:

- `Lint`: Ruff checks `foodanalyzer` and `tests`.
- `Type check`: mypy checks application code.
- `Tests and coverage`: pytest with `--cov-fail-under=60`.
- `Docker build`: builds the project image.

## Benchmark

```powershell
python scripts/bench.py --image data/rice_chicken_broccoli.png
```

The benchmark compares sequential nutrition lookup with bounded concurrent
lookup using the same ingredients and a cleared local cache.

## Environment Variables

Common settings:

- `DATABASE_URL`
- `OFFLINE_MODE`
- `LOG_LEVEL`
- `NUTRITION_CACHE_TTL_SECONDS`
- `MAX_IMAGE_SIZE_MB`
- `MAX_CONCURRENCY`
- `RETRY_ATTEMPTS`
- `UPLOAD_DIR`
- `USDA_API_KEY`
- `LLM_PROVIDER`
- `LLM_MODEL`
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `OPENROUTER_REASONING_ENABLED`
- `OPENROUTER_REASONING_EXCLUDE`

## OpenRouter Notes

OpenRouter support is implemented in the application layer and does not modify
the provided `ai/` package.

Example `.env` values:

```text
LLM_PROVIDER=openrouter
LLM_MODEL=<teacher-approved-vision-model>
OPENROUTER_API_KEY=<your-key>
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_REASONING_ENABLED=false
OPENROUTER_REASONING_EXCLUDE=false
```

Topic 2 requires a model that can read images. If OpenRouter returns an image
input error or empty/non-JSON response, keep the configured model unchanged
unless the project owner chooses a different teacher-approved vision model.

If USDA lookup fails with a proxy error pointing at `127.0.0.1:9`, clear
`HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY` before starting the server, or add
`api.nal.usda.gov` to `NO_PROXY`.

## Student Notes

The code is intentionally straightforward. The AI wrapper, analyzer, cache,
storage, CLI, API, and HTMX UI are separated so each teammate can explain their
part during the defense.