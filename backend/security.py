"""Local API boundary with desktop tokens and cross-site write protection."""
from __future__ import annotations

import hmac
import ipaddress
import os

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from utils.resource_limits import (
    MAX_BOOK_PDF_BYTES,
    MAX_EXERCISE_UPLOAD_BYTES,
    MAX_OUTPUT_ZIP_BYTES,
    MIB,
)


TOKEN_HEADER = "X-Kaoyan-Token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
READ_ONLY_POST_PATHS = {
    "/api/exercises/list",
    "/api/exercises/overview",
    "/api/mistakes/list",
    "/api/mistakes/overview",
}
CAPTURE_API_PATHS = {
    "/api/mistakes/recognize-image",
    "/api/mistakes/add",
    "/api/exercises/add",
}
DEFAULT_TRUSTED_ORIGINS = {
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8000",
}


def is_loopback_client(host: str) -> bool:
    if host in {"testclient", "localhost"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_trusted_origin(origin: str, request_origin: str = "") -> bool:
    if not origin:
        return True
    configured = {
        item.strip().rstrip("/")
        for item in os.getenv("KAOYAN_TRUSTED_ORIGINS", "").split(",")
        if item.strip()
    }
    # Never trust the request Host as an allow-list entry. Host is
    # attacker-controlled during DNS rebinding and must not authorize writes.
    return origin.rstrip("/") in DEFAULT_TRUSTED_ORIGINS | configured


def is_write_request(method: str, path: str) -> bool:
    normalized_method = method.upper()
    normalized_path = path.rstrip("/") or "/"
    return (
        normalized_method in UNSAFE_METHODS
        and not (
            normalized_method == "POST"
            and normalized_path in READ_ONLY_POST_PATHS
        )
    )


def upload_body_limit(path: str) -> int | None:
    limits = {
        "/api/mistakes/recognize-image": 24 * MIB,
        "/api/mistakes/solve-image": 24 * MIB,
        "/api/books/import": MAX_BOOK_PDF_BYTES + 4 * MIB,
        "/api/books/import-job": MAX_BOOK_PDF_BYTES + 4 * MIB,
        "/api/books/import-local": MAX_BOOK_PDF_BYTES + 4 * MIB,
        "/api/books/import-mineru-output": MAX_OUTPUT_ZIP_BYTES + 4 * MIB,
        # The exercise endpoint may contain a question file and an answer file.
        "/api/exercises/upload-analyze": 2 * MAX_EXERCISE_UPLOAD_BYTES + 4 * MIB,
    }
    return limits.get(path.rstrip("/"))



def authorize_api_client(host: str, supplied_token: str, configured_token: str, require_token: bool = False) -> tuple[bool, str]:
    local = is_loopback_client(host)
    if configured_token and supplied_token and hmac.compare_digest(supplied_token, configured_token):
        return True, "token"
    if local and not require_token:
        return True, "local"
    if not configured_token:
        return False, "remote_disabled"
    if not supplied_token or not hmac.compare_digest(supplied_token, configured_token):
        return False, "invalid_token"
    return True, "token"


def authorize_capture_client(path: str, supplied_token: str, configured_token: str) -> tuple[bool, str]:
    if not configured_token or not supplied_token or not hmac.compare_digest(supplied_token, configured_token):
        return False, "invalid_capture_token"
    if path.rstrip("/") not in CAPTURE_API_PATHS:
        return False, "capture_scope_denied"
    return True, "capture"


class LocalApiBoundaryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api"):
            return await call_next(request)
        host = request.client.host if request.client else ""
        if os.getenv("KAOYAN_ALLOW_PRIVATE_CLIENTS", "0") == "1":
            try:
                if ipaddress.ip_address(host).is_private:
                    host = "127.0.0.1"
            except ValueError:
                pass
        configured = os.getenv("KAOYAN_API_TOKEN", "").strip()
        capture_token = os.getenv("KAOYAN_CAPTURE_TOKEN", "").strip()
        require_token = os.getenv("KAOYAN_REQUIRE_API_TOKEN", "0") == "1"
        supplied = request.headers.get(TOKEN_HEADER, "").strip()
        capture_allowed, capture_reason = authorize_capture_client(request.url.path, supplied, capture_token)
        if capture_allowed:
            body_limit = upload_body_limit(request.url.path)
            if body_limit is not None:
                raw_length = request.headers.get("content-length", "").strip()
                try:
                    content_length = int(raw_length)
                except ValueError:
                    content_length = -1
                if content_length < 0:
                    return JSONResponse(
                        status_code=411,
                        content={"success": False, "error_code": "CONTENT_LENGTH_REQUIRED", "message": "Upload Content-Length is required."},
                    )
                if content_length > body_limit:
                    return JSONResponse(
                        status_code=413,
                        content={"success": False, "error_code": "UPLOAD_TOO_LARGE", "message": "Upload request exceeds the configured size limit."},
                    )
            return await call_next(request)
        if capture_reason == "capture_scope_denied":
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error_code": "CAPTURE_SCOPE_DENIED",
                    "message": "The mobile capture token can only upload and save captured questions.",
                },
            )
        allowed, reason = authorize_api_client(host, supplied, configured, require_token)
        if allowed:
            if reason == "local" and is_write_request(
                request.method,
                request.url.path,
            ):
                origin = request.headers.get("Origin", "").strip()
                if not is_trusted_origin(origin):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "success": False,
                            "error_code": "UNTRUSTED_ORIGIN",
                            "message": "Untrusted web origin cannot write to the local API.",
                        },
                    )
            body_limit = upload_body_limit(request.url.path)
            if body_limit is not None:
                raw_length = request.headers.get("content-length", "").strip()
                try:
                    content_length = int(raw_length)
                except ValueError:
                    content_length = -1
                if content_length < 0:
                    return JSONResponse(
                        status_code=411,
                        content={"success": False, "error_code": "CONTENT_LENGTH_REQUIRED", "message": "Upload Content-Length is required."},
                    )
                if content_length > body_limit:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "success": False,
                            "error_code": "UPLOAD_TOO_LARGE",
                            "message": "Upload request exceeds the configured size limit.",
                        },
                    )
            return await call_next(request)
        if reason == "remote_disabled":
            return JSONResponse(
                status_code=403,
                content={"success": False, "error_code": "REMOTE_ACCESS_DISABLED", "message": "远程 API 默认关闭；请在服务端配置 KAOYAN_API_TOKEN。"},
            )
        return JSONResponse(
            status_code=401,
            headers={"WWW-Authenticate": "KaoyanToken"},
            content={"success": False, "error_code": "INVALID_API_TOKEN", "message": "访问令牌无效或缺失。"},
        )
