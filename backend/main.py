"""FastAPI 后端入口

运行方式:
    uvicorn backend.main:app --reload --port 8000

前端开发时 CORS 允许 localhost:5173 (Vite 默认端口)。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pathlib import Path
from contextlib import asynccontextmanager
import logging
import os
import threading

from backend.api import agent, chat, mistakes, books, kg, exercises, system, reports, assets, figures, highlights, jobs, backups, learning_state
from backend.security import LocalApiBoundaryMiddleware
from utils.version import APP_VERSION

logger = logging.getLogger(__name__)
_warmup_state = {
    "status": "pending",
    "stage": "runtime_check",
    "message": "Preparing Texa runtime",
    "error": "",
    "failure": None,
    "stages_ms": {},
}
_warmup_lock = threading.Lock()


def _update_warmup(**values) -> None:
    with _warmup_lock:
        _warmup_state.update(values)


class SPAStaticFiles(StaticFiles):
    """Serve the React entry point for client-side routes, but never for APIs/assets."""

    @staticmethod
    def _should_fallback(path: str, scope) -> bool:
        raw_path = scope.get("raw_path", b"")
        request_path = raw_path.decode("latin-1") if isinstance(raw_path, bytes) else str(raw_path)
        normalized = (request_path or path).split("?", 1)[0].lstrip("/")
        reserved = normalized == "api" or normalized.startswith(("api/", "assets/"))
        return not reserved and not Path(normalized).suffix

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not self._should_fallback(path, scope):
                raise
            return await super().get_response("index.html", scope)

        if response.status_code == 404 and self._should_fallback(path, scope):
            return await super().get_response("index.html", scope)
        return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from backend.data_backup import apply_pending_restore
    from utils.storage_manifest import ensure_storage_manifest

    apply_pending_restore()
    ensure_storage_manifest()
    books.migrate_book_identities()
    _recover_jobs()
    _start_warmup()
    try:
        yield
    finally:
        try:
            from ingestion.vector_store import reset_vector_store

            reset_vector_store()
        except Exception:
            logger.exception("vector store shutdown cleanup failed")


def _recover_jobs() -> None:
    try:
        from backend.job_manager import get_job_manager

        interrupted = get_job_manager().mark_running_interrupted()
        if interrupted:
            logger.info("marked %s unfinished jobs interrupted", interrupted)
    except Exception:
        logger.exception("startup job recovery failed")


def _start_warmup() -> None:
    with _warmup_lock:
        if _warmup_state["status"] != "pending":
            return
        _warmup_state.update(status="starting", stage="runtime_check", message="Preparing Texa runtime", error="", failure=None)
        threading.Thread(target=_warmup, name="backend-warmup", daemon=True).start()

app = FastAPI(
    title="Texa API",
    description="FastAPI + React 架构后端",
    version=APP_VERSION,
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────
# 允许前端开发服务器跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite 默认
        "http://localhost:3000",   # React 默认
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Deprecation"],
)
app.add_middleware(LocalApiBoundaryMiddleware)

# ── API 路由 ──────────────────────────────────────────────
app.include_router(chat.router, prefix="/api")
app.include_router(agent.router, prefix="/api")
app.include_router(mistakes.router, prefix="/api")
app.include_router(books.router, prefix="/api")
app.include_router(kg.router, prefix="/api")
app.include_router(exercises.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(assets.router, prefix="/api/system")
app.include_router(highlights.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(backups.router, prefix="/api")
app.include_router(learning_state.router, prefix="/api")
app.include_router(figures.router, prefix="/api")

# ── 健康检查 ──────────────────────────────────────────────
@app.get("/health")
def health():
    with _warmup_lock:
        warmup = dict(_warmup_state)
        warmup["stages_ms"] = dict(_warmup_state.get("stages_ms") or {})
    return {
        "status": "ok",
        "version": APP_VERSION,
        "instance_id": os.getenv("KAOYAN_INSTANCE_ID", ""),
        "process_alive": True,
        "embedding_ready": warmup.get("stage") in {"index_discovery", "ready"} and warmup.get("status") != "error",
        "retrieval_ready": warmup.get("status") == "ready",
        "warmup": warmup,
    }

# ── 启动预热 ──────────────────────────────────────────────
def _warmup():
    """启动时预热：加载嵌入模型和向量库，避免首请求长时间等待。"""
    import time
    from ingestion.embedding_errors import EmbeddingRuntimeError, classify_embedding_error

    t0 = time.perf_counter()
    stage_started = t0
    stages_ms = {}
    _update_warmup(status="running", stage="runtime_check", message="Checking runtime", error="", failure=None, stages_ms={})
    try:
        from ingestion.embedding_assets import ensure_supported_architecture

        ensure_supported_architecture()
    except Exception as exc:
        failure = classify_embedding_error(exc, stage="runtime_check")
        stages_ms["runtime_check"] = round((time.perf_counter() - stage_started) * 1000, 2)
        _update_warmup(status="error", stage="runtime_check", message="Runtime is unavailable", error=failure.code, failure=failure.as_dict(), stages_ms=stages_ms)
        logger.exception("runtime check failed code=%s diagnostic_id=%s", failure.code, failure.failure.diagnostic_id)
        return

    stages_ms["runtime_check"] = round((time.perf_counter() - stage_started) * 1000, 2)
    stage_started = time.perf_counter()
    _update_warmup(stage="asset_verify", message="Verifying ONNX assets", stages_ms=dict(stages_ms))
    try:
        from ingestion.embedding_assets import resolve_embedding_assets

        resolve_embedding_assets(full_hash=os.getenv("TEXA_EMBEDDING_FULL_VERIFY", "0") == "1")
    except Exception as exc:
        failure = classify_embedding_error(exc, stage="asset_verify")
        stages_ms["asset_verify"] = round((time.perf_counter() - stage_started) * 1000, 2)
        _update_warmup(status="error", stage="asset_verify", message="ONNX assets need repair", error=failure.code, failure=failure.as_dict(), stages_ms=stages_ms)
        logger.exception("asset verification failed code=%s diagnostic_id=%s", failure.code, failure.failure.diagnostic_id)
        return

    stages_ms["asset_verify"] = round((time.perf_counter() - stage_started) * 1000, 2)
    stage_started = time.perf_counter()
    _update_warmup(stage="embedding_load", message="Loading ONNX embedding runtime", stages_ms=dict(stages_ms))
    if os.getenv('SKIP_EMBEDDING_WARMUP', '0') == '1':
        logger.info("embedding warmup skipped")
    else:
        try:
            from config import get_embeddings
            get_embeddings()
            logger.info("embeddings loaded in %.1fms", (time.perf_counter() - stage_started) * 1000)
        except Exception as exc:
            failure = classify_embedding_error(exc, stage="embedding_load")
            stages_ms["embedding_load"] = round((time.perf_counter() - stage_started) * 1000, 2)
            _update_warmup(status="error", stage="embedding_load", message="ONNX embedding runtime needs repair", error=failure.code, failure=failure.as_dict(), stages_ms=stages_ms)
            logger.exception("embedding warmup failed code=%s diagnostic_id=%s", failure.code, failure.failure.diagnostic_id)
            return

    stages_ms["embedding_load"] = round((time.perf_counter() - stage_started) * 1000, 2)
    stage_started = time.perf_counter()
    _update_warmup(stage="index_discovery", message="Discovering textbook indexes", stages_ms=dict(stages_ms))
    if os.getenv('SKIP_VECTOR_WARMUP', '0') == '1':
        logger.info("vector store warmup skipped")
    else:
        try:
            from ingestion.vector_store import get_vector_store
            get_vector_store()
            logger.info("vector store loaded in %.1fms", (time.perf_counter() - stage_started) * 1000)
        except Exception as exc:
            failure = EmbeddingRuntimeError(
                "CHROMA_LOAD_FAILURE",
                str(exc) or type(exc).__name__,
                stage="index_discovery",
                repair_action="inspect_vector_store_diagnostics",
            )
            stages_ms["index_discovery"] = round((time.perf_counter() - stage_started) * 1000, 2)
            _update_warmup(status="degraded", stage="index_discovery", message="Textbook indexes are degraded", error=failure.code, failure=failure.as_dict(), stages_ms=stages_ms)
            logger.exception("vector store warmup failed")
            return

    logger.info("concept graph warmup skipped")
    stages_ms["index_discovery"] = round((time.perf_counter() - stage_started) * 1000, 2)
    stages_ms["total"] = round((time.perf_counter() - t0) * 1000, 2)
    _update_warmup(status="ready", stage="ready", message="Texa is ready", error="", failure=None, stages_ms=stages_ms)
    logger.info("startup warmup completed in %.1fms stages=%s", stages_ms["total"], stages_ms)


# ── 静态文件（前端 build 产物）─────────────────────────────
# 如果 frontend/dist 存在，挂载为静态文件服务
_dist_path = Path(__file__).parent.parent / "frontend" / "dist"
if _dist_path.exists():
    app.mount("/", SPAStaticFiles(directory=str(_dist_path), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
