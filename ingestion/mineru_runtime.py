"""Bounded MinerU availability checks for the textbook import UI."""
from __future__ import annotations

from pathlib import Path
import shlex
import shutil

import httpx


def inspect_mineru_runtime(
    api_url: str = "",
    cli_command: str = "",
    *,
    timeout_seconds: float = 1.5,
) -> dict:
    """Probe the same API-first runtime choice used by textbook import."""
    normalized_api = str(api_url or "").strip().rstrip("/")
    normalized_cli = str(cli_command or "").strip()

    if normalized_api:
        try:
            with httpx.Client(timeout=timeout_seconds, trust_env=False) as client:
                response = client.get(normalized_api)
            available = response.status_code < 500
            return {
                "configured": True,
                "available": available,
                "mode": "api",
                "reason": "ready" if available else "api_error",
            }
        except httpx.HTTPError:
            return {
                "configured": True,
                "available": False,
                "mode": "api",
                "reason": "api_unreachable",
            }

    if normalized_cli:
        try:
            executable = shlex.split(normalized_cli, posix=False)[0].strip('"')
        except (ValueError, IndexError):
            executable = ""
        path_ready = bool(executable) and Path(executable).is_file()
        command_ready = bool(executable) and shutil.which(executable) is not None
        available = path_ready or command_ready
        return {
            "configured": True,
            "available": available,
            "mode": "cli",
            "reason": "ready" if available else "cli_missing",
        }

    return {
        "configured": False,
        "available": False,
        "mode": "none",
        "reason": "not_configured",
    }
