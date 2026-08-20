"""System diagnostics for the local study workspace."""
from __future__ import annotations

import sqlite3
import asyncio
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request

from config import PROGRESS_PATH, VECTOR_DB_PATH
from backend.rag_trace import TRACE_DB_PATH, list_traces

router = APIRouter(prefix="/system", tags=["system"])

ComponentStatus = Literal["healthy", "degraded", "error"]


def _component(status: ComponentStatus, message: str, **details) -> dict:
    return {"status": status, "message": message, "details": details}


def _check_vector_store() -> dict:
    db_path = Path(VECTOR_DB_PATH) / "chroma.sqlite3"
    try:
        import ingestion.vector_store as vector_store_module

        if not db_path.exists():
            return _component(
                "degraded",
                "向量库尚未初始化",
                collection_count=0,
                path=str(db_path),
            )
        with sqlite3.connect(str(db_path), timeout=1) as conn:
            integrity = conn.execute("PRAGMA quick_check").fetchone()
            collection_count = conn.execute("SELECT COUNT(*) FROM collections").fetchone()[0]
        if not integrity or integrity[0] != "ok":
            return _component(
                "error",
                "向量库完整性检查失败",
                collection_count=collection_count,
                path=str(db_path),
            )
        runtime_store = getattr(vector_store_module, "_chapter_vs_instance", None)
        if getattr(runtime_store, "available", True) is False:
            return _component(
                "degraded",
                "向量库运行时已进入降级模式，建议重启后端后复查",
                collection_count=collection_count,
                path=str(db_path),
            )
        if collection_count == 0:
            return _component(
                "degraded",
                "向量库可访问，但当前没有已索引章节",
                collection_count=0,
                path=str(db_path),
            )
        return _component(
            "healthy",
            f"向量检索正常，共 {collection_count} 个章节索引",
            collection_count=collection_count,
            path=str(db_path),
        )
    except sqlite3.OperationalError as exc:
        if 'locked' in str(exc).lower():
            return _component('degraded', f'Vector database is locked by another process: {exc}', path=str(db_path))
        return _component('error', f'Vector database is unavailable: {exc}', path=str(db_path))
    except Exception as exc:
        return _component('error', f'Vector database is unavailable: {exc}', path=str(db_path))


def _check_sqlite(path: Path, table_name: str, label: str) -> dict:
    try:
        if not path.exists():
            return _component(
                "degraded",
                f"{label}尚未初始化，将在首次使用时创建",
                path=str(path),
                record_count=0,
            )
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5) as conn:
            integrity = conn.execute("PRAGMA quick_check").fetchone()
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
            count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0] if table else 0
        if not integrity or integrity[0] != "ok":
            return _component("error", f"{label}完整性检查失败", path=str(path), record_count=count)
        if not table:
            return _component(
                "degraded",
                f"{label}尚未初始化，将在首次使用时创建",
                path=str(path),
                record_count=0,
            )
        return _component(
            "healthy",
            f"{label}正常，共 {count} 条记录",
            path=str(path),
            record_count=count,
        )
    except Exception as exc:
        return _component("error", f"{label}不可用：{exc}", path=str(path), record_count=0)


def _check_runtime_config() -> dict:
    import config
    from llm.configuration import resolve_model_role

    reasoning = resolve_model_role("reasoning")
    vision = resolve_model_role("vision")
    configured = reasoning.credential_configured
    return _component(
        "healthy" if configured else "degraded",
        "LLM configuration is ready" if configured else f"{reasoning.provider.label} API Key 尚未配置",
        provider=reasoning.provider.provider_id,
        model=reasoning.model,
        vision_provider=vision.provider.provider_id,
        vision_model=vision.model,
        embedding_model=getattr(config, "EMBEDDING_MODEL_NAME", ""),
        embedding_backend=getattr(config, "embedding_backend_name", lambda: "unknown")(),
    )


def _check_embedding_runtime() -> dict:
    from ingestion.embedding_assets import embedding_asset_status

    status = embedding_asset_status(full_hash=False)
    if status.get("status") == "ready":
        details = {key: value for key, value in status.items() if key != "status"}
        return _component(
            "healthy",
            "ONNX embedding runtime is ready",
            backend="onnxruntime_fp32",
            **details,
        )
    failure = status.get("failure") or {}
    return _component(
        "error",
        failure.get("message") or "ONNX embedding runtime is unavailable",
        backend="onnxruntime_fp32",
        failure=failure,
    )


@router.get("/rag-traces")
def rag_traces(limit: int = 50):
    return {"success": True, "data": list_traces(limit)}


@router.post("/vector-store/reload")
def reload_vector_store():
    try:
        from ingestion.vector_store import reset_vector_store

        reset_vector_store()
        status = _check_vector_store()
        return {
            "success": status.get("status") != "error",
            "message": status.get("message", "向量库已重置，下一次检索会重新连接"),
            "data": status,
        }
    except Exception as exc:
        return {"success": False, "message": f"向量库重载失败：{exc}", "data": _component("error", str(exc))}


@router.get("/health")
def system_health(book_name: str = ""):
    safe_book_name = Path(book_name or "default").name
    components = {
        "embedding_runtime": _check_embedding_runtime(),
        "vector_store": _check_vector_store(),
        "mistake_book": _check_sqlite(
            Path(PROGRESS_PATH) / f"mistake_book_{safe_book_name}.db", "mistakes", "错题库"
        ),
        "rag_trace": _check_sqlite(TRACE_DB_PATH, "rag_traces", "RAG trace"),
        "runtime_config": _check_runtime_config(),
        "exercise_bank": _check_sqlite(
            Path(PROGRESS_PATH) / f"exercise_bank_{safe_book_name}.db", "exercises", "习题库"
        ),
    }
    statuses = {item["status"] for item in components.values()}
    overall = "error" if "error" in statuses else "degraded" if "degraded" in statuses else "healthy"
    return {"status": overall, "book_name": book_name, "components": components}


@router.post("/shutdown")
async def graceful_shutdown(request: Request):
    """Ask the packaged Uvicorn server to drain requests and exit cleanly."""
    server = getattr(request.app.state, "desktop_server", None)
    if server is None:
        return {
            "success": False,
            "message": "当前启动方式不支持远程停机，请在启动终端中停止服务。",
        }

    cancelling = 0
    try:
        from backend.job_manager import RUNNING_STATUSES, get_job_manager

        manager = get_job_manager()
        for job in manager.list_jobs(limit=500):
            if job.get("status") in RUNNING_STATUSES:
                manager.request_cancel(str(job["id"]), "应用正在退出，任务已请求取消")
                cancelling += 1
    except Exception:
        cancelling = 0

    async def stop_after_response() -> None:
        await asyncio.sleep(0.2)
        server.should_exit = True

    asyncio.create_task(stop_after_response())
    return {
        "success": True,
        "message": "后端正在完成当前请求并安全退出",
        "cancelling_jobs": cancelling,
    }

# ---- Settings center -----------------------------------------------------
import json
import os
import subprocess
from datetime import datetime

from config import BASE_DIR
from llm.configuration import model_settings_env_values, model_settings_payload
from llm.factory import clear_model_cache
from utils.version import APP_VERSION
from utils.subject_catalog import DEFAULT_SUBJECT_TREE, clean_subject_tree, read_subject_tree, write_subject_tree

ENV_PATH = Path(os.getenv("ENV_PATH", str(BASE_DIR / ".env")))

ENV_KEYS = [
    "MINERU_API_URL",
    "MINERU_CLI_COMMAND",
]


def _read_env_lines() -> list[str]:
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def _write_env_values(values: dict[str, str]) -> None:
    for key, value in values.items():
        if "\n" in key or "\r" in key or "=" in key or "\n" in value or "\r" in value:
            raise ValueError("配置项不能包含换行符")
    lines = _read_env_lines()
    seen: set[str] = set()
    next_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            next_lines.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in values:
            next_lines.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            next_lines.append(line)
    for key, value in values.items():
        if key not in seen:
            next_lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")


def _apply_runtime_env(values: dict[str, str]) -> None:
    import config as config_module

    for key, value in values.items():
        os.environ[key] = value
        if hasattr(config_module, key):
            setattr(config_module, key, value)


def _redact_public_value(value: str) -> str:
    import re
    if not value:
        return ""
    redacted = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***", value)
    redacted = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s]+", r"\1***", redacted)
    return redacted


def _env_status() -> dict:
    result = {}
    for key in ENV_KEYS:
        value = os.getenv(key, "")
        result[key] = {"configured": bool(value), "value": _redact_public_value(value)}
    return result


def _read_subject_tree() -> list[dict]:
    return read_subject_tree()


def _write_subject_tree(tree: list[dict]) -> list[dict]:
    return write_subject_tree(tree)


@router.get("/settings")
def get_settings():
    return {
        "success": True,
        "data": {
            "env": _env_status(),
            "models": model_settings_payload(),
            "subjects": _read_subject_tree(),
        },
    }


@router.post("/settings/env")
def save_env_settings(payload: dict):
    values = {}
    for key in ENV_KEYS:
        if key not in payload:
            continue
        value = str(payload.get(key) or "").strip()
        values[key] = value
    if not values:
        return {"success": False, "message": "没有可保存的配置"}
    _write_env_values(values)
    _apply_runtime_env(values)
    return {"success": True, "message": "配置已写入 .env。API Key 不会在界面回显。", "data": _env_status()}


@router.post("/settings/models")
def save_model_settings(payload: dict):
    """Persist role-oriented model settings without returning credentials."""
    try:
        values = model_settings_env_values(payload)
        _write_env_values(values)
        _apply_runtime_env(values)
        clear_model_cache()
        return {
            "success": True,
            "message": "模型配置已保存。API Key 不会在界面回显。",
            "data": model_settings_payload(),
        }
    except ValueError as exc:
        return {"success": False, "message": str(exc)}


@router.get("/settings/subjects")
def get_subjects():
    return {"success": True, "data": _read_subject_tree()}


def _subject_values_in_use() -> list[str]:
    """Read textbook assignments without changing textbook metadata or indexes."""
    from backend.api.books import _book_subject, _known_book_names

    return sorted({value for name in _known_book_names() if (value := _book_subject(name))})


def _catalog_values(tree: list[dict]) -> set[str]:
    values: set[str] = set()
    for node in tree:
        parent = str(node.get("name", "")).strip()
        if not parent:
            continue
        values.add(parent)
        for child in node.get("children", []) or []:
            child_name = str(child).strip()
            if child_name:
                values.add(child_name)  # Backward-compatible legacy assignment.
                values.add(f"{parent}/{child_name}")
    return values


@router.post("/settings/subjects")
def save_subjects(payload: dict):
    tree = payload.get("subjects", [])
    if not isinstance(tree, list):
        return {"success": False, "message": "subjects 必须是列表"}
    cleaned = clean_subject_tree(tree)
    valid_values = _catalog_values(cleaned)
    orphaned = [value for value in _subject_values_in_use() if value not in valid_values]
    if orphaned:
        preview = "、".join(orphaned[:4])
        return {"success": False, "message": f"目录未保存：以下教材归属仍在使用，请先移动对应教材：{preview}"}
    saved = _write_subject_tree(cleaned)
    return {"success": True, "message": "资料库目录已保存", "data": saved}


@router.get("/version")
def version_info():
    commit = ""
    branch = ""
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(BASE_DIR), text=True, stderr=subprocess.DEVNULL).strip()
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(BASE_DIR), text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        pass
    return {
        "success": True,
        "data": {
            "version": APP_VERSION,
            "branch": branch,
            "commit": commit,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "update_available": False,
            "message": "当前为本地开发版；自动更新通道尚未配置。",
        },
    }


@router.post("/update")
def run_update():
    return {
        "success": False,
        "message": "自动更新通道尚未启用。桌面打包完成后可接入安装包更新或 git 更新策略。",
    }
