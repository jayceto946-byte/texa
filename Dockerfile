# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.10-slim AS app
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data \
    SKIP_VECTOR_WARMUP=1 \
    EMBEDDING_LOCAL_FILES_ONLY=1 \
    TEXA_EMBEDDING_BACKEND=onnx \
    TEXA_EMBEDDING_ASSET_DIR=/app/assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-release.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements-release.txt

COPY agents/ ./agents/
COPY backend/ ./backend/
COPY graph/ ./graph/
COPY ingestion/ ./ingestion/
COPY knowledge/ ./knowledge/
COPY memory/ ./memory/
COPY ui/ ./ui/
COPY utils/ ./utils/
COPY config.py main.py __init__.py ./
COPY assets/embedding-runtime/ ./assets/embedding-runtime/
COPY scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN python -B -c "from ingestion.embedding_assets import validate_asset_dir; validate_asset_dir('/app/assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1', full_hash=True)"

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"

CMD ["sh", "scripts/docker-entrypoint.sh"]
