# New user / clean machine deployment

This guide is for a clean deployment where the new user starts with no textbooks, no Chroma index, and no study history.

## What should be included

Include source code and deployment files:

- `backend/`
- `frontend/`
- `agents/`, `graph/`, `ingestion/`, `knowledge/`, `memory/`, `ui/`, `utils/`
- `scripts/`
- `docs/`
- `tests/`
- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `.env.example`
- `requirements.txt`
- `package.json` / `package-lock.json` under `frontend/`

Do not include local user data or secrets:

- `.env`
- `deepseek-api.txt`
- `data/`
- `venv/`, `venv310/`, `venv312/`
- `frontend/node_modules/`
- `frontend/dist/`
- `__pycache__/`
- `.pytest_cache/`
- local scratch files such as `_test_*.py`, `_benchmark*.py`, `session_*.zip`

## First start with Docker

```powershell
Copy-Item .env.example .env
# Edit .env and fill DEEPSEEK_API_KEY or another LLM config.
docker compose up -d --build
```

Open:

```text
http://127.0.0.1:8000
```

The container will create an empty local `data/` directory on first start. The user then imports textbooks and generates indexes locally.

## Data model

The Docker image contains only application code and fixed dependencies.

The host `./data` directory contains user-owned local data:

- textbook PDFs
- Chroma vector database
- chapter split/cache files
- mistake book records
- learning memory
- knowledge graph data
- embedding model cache

Updating or deleting the container must not delete `./data`.

## MinerU

MinerU is an optional external HTTP service and is not part of the main image. See `docs/mineru_deploy.md` for local GPU and rented-GPU setup. Mistake-image OCR uses Kimi Vision and is configured with `MOONSHOT_API_KEY`, not a separate OCR service URL.

```env
MINERU_API_URL=http://host.docker.internal:9001
MINERU_OUTPUT_PATH=./mineru_output
MINERU_TASK_TIMEOUT_SECONDS=3600
MINERU_TASK_POLL_SECONDS=2
```

If these MinerU variables are not configured, the app can still start. Only MinerU-based scanned-PDF parsing is affected.

## Export a clean source package

From the project root:

```powershell
.\scripts\export-new-user-package.ps1
```

The output is written to `exports/texa-new-user-<timestamp>/texa`.

The export script includes tracked files plus untracked source files that are not ignored by `.gitignore`. It excludes local data, secrets, virtual environments, dependency folders, and generated build artifacts.

## Verification checklist after copying to a new machine

```powershell
Copy-Item .env.example .env
# edit .env
docker compose config
docker compose build
docker compose up -d
Invoke-RestMethod http://127.0.0.1:8000/health
```

Then open `http://127.0.0.1:8000`, import a small PDF, and confirm the book appears in the UI.
