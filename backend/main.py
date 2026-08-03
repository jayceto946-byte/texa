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

from backend.api import agent, chat, mistakes, books, kg, exercises, system, reports, assets, highlights, jobs, backups
from backend.security import LocalApiBoundaryMiddleware
from utils.version import APP_VERSION

logger = logging.getLogger(__name__)
_warmup_state = {"status": "pending", "error": ""}
_warmup_lock = threading.Lock()


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
    yield


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
        _warmup_state.update(status="starting", error="")
        threading.Thread(target=_warmup, name="backend-warmup", daemon=True).start()

app = FastAPI(
    title="考研智能辅助系统 API",
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

# ── 健康检查 ──────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "instance_id": os.getenv("KAOYAN_INSTANCE_ID", ""),
        "warmup": dict(_warmup_state),
    }

# ── 启动预热 ──────────────────────────────────────────────
def _warmup():
    """启动时预热：加载嵌入模型和向量库，避免首请求长时间等待。"""
    import time
    t0 = time.time()
    _warmup_state.update(status="running", error="")
    errors = []
    if os.getenv('SKIP_EMBEDDING_WARMUP', '0') == '1':
        logger.info("embedding warmup skipped")
    else:
        try:
            from config import get_embeddings
            get_embeddings()
            logger.info("embeddings loaded in %.1fs", time.time() - t0)
        except Exception as e:
            errors.append(str(e))
            logger.exception("embedding warmup failed")

    t1 = time.time()
    if os.getenv('SKIP_VECTOR_WARMUP', '0') == '1':
        logger.info("vector store warmup skipped")
    else:
        try:
            from ingestion.vector_store import get_vector_store
            get_vector_store()
            logger.info("vector store loaded in %.1fs", time.time() - t1)
        except Exception as e:
            errors.append(str(e))
            logger.exception("vector store warmup failed")

    logger.info("concept graph warmup skipped")

    _warmup_state.update(status="degraded" if errors else "ready", error="; ".join(errors))
    logger.info("startup warmup completed in %.1fs", time.time() - t0)


# ── 静态文件（前端 build 产物）─────────────────────────────
# 如果 frontend/dist 存在，挂载为静态文件服务
_dist_path = Path(__file__).parent.parent / "frontend" / "dist"
if _dist_path.exists():
    app.mount("/", SPAStaticFiles(directory=str(_dist_path), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
