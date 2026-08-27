# Docker deployment

This deployment keeps the Docker image disposable and keeps user learning data on the host machine.

## Data boundary

The image/container contains:

- FastAPI backend
- React production build
- Torch-free Python runtime dependencies
- Versioned BGE ONNX embedding runtime and tokenizer assets
- Startup script

The host `./data` directory contains:

- Textbook PDFs
- Chroma vector database
- Chapter split results
- Mistake book records
- Study memory and review records
- Knowledge graph and concept memory files
- Verified embedding repair overrides, when explicitly installed

Updating or deleting the container must not delete `./data`.

## First start

```powershell
Copy-Item .env.example .env
# Edit .env and fill DEEPSEEK_API_KEY or other LLM settings.
docker compose up -d --build
```

Open:

```text
http://127.0.0.1:8000
```

On a new computer, `./data` starts empty. The user imports textbooks and generates Chroma indexes and study records locally.

The versioned ONNX embedding model is part of the image and is verified with its manifest and SHA-256 hashes during docker build; first start does not download an embedding model.

## Update

For local source builds:

```powershell
.\scripts\update-docker.ps1
```

For a future remote image workflow:

```powershell
.\scripts\update-docker.ps1 -Pull
```

The update script backs up `./data` into `./backups`, then builds/pulls the image, restarts Compose, and checks `/health`.

## Manual backup

```powershell
.\scripts\backup-docker-data.ps1
```

## MinerU

MinerU is an optional external HTTP service and is not bundled into the main image. Deployment details are in `docs/mineru_deploy.md`. Mistake-image OCR uses Kimi Vision and is configured with `MOONSHOT_API_KEY`, not a separate OCR service URL.

```env
MINERU_API_URL=http://host.docker.internal:9001
MINERU_OUTPUT_PATH=./mineru_output
MINERU_TASK_TIMEOUT_SECONDS=3600
MINERU_TASK_POLL_SECONDS=2
```

If these MinerU variables are not configured, the main app can still start. Only MinerU-based scanned-document parsing is affected.

## Rollback

If an update fails:

```powershell
docker compose logs -f
docker compose down
```

The host `./data` directory is still available. You can run an older image or restore a zip from `./backups`.

## Continuation checklist

The current environment does not have Docker installed, so real Docker verification is still pending:

```powershell
docker compose config
docker compose build
docker compose up -d
Invoke-RestMethod http://127.0.0.1:8000/health
```
