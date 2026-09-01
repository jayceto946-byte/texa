"""Provider-neutral connectivity checks for unsaved model settings."""

from __future__ import annotations

import base64
import binascii
import os
import struct
import zlib
from collections.abc import Callable, Mapping

from llm.configuration import model_settings_env_values, resolve_model_role
from llm.factory import build_chat_model, build_openai_client, create_vision_completion
from llm.types import ResolvedModelRole


ConnectionTester = Callable[[ResolvedModelRole], None]
_testers: dict[str, ConnectionTester] = {}


def register_connection_tester(transport: str, tester: ConnectionTester) -> None:
    _testers[transport] = tester


def _validate_completion_response(response, *, label: str) -> None:
    choices = getattr(response, "choices", None) or []
    message = getattr(choices[0], "message", None) if choices else None
    if message is None:
        raise RuntimeError(f"{label}未返回 completion message")


def _test_openai_compatible(resolved: ResolvedModelRole) -> None:
    client = build_openai_client(resolved, timeout=20, max_retries=0)
    extra_body = dict(resolved.options.get("extra_body") or {})
    response = client.chat.completions.create(
        model=resolved.model,
        messages=[{"role": "user", "content": "Reply with OK."}],
        max_tokens=128,
        stream=False,
        extra_body=extra_body or None,
    )
    _validate_completion_response(response, label="文本模型")


def _test_ollama(resolved: ResolvedModelRole) -> None:
    response = build_chat_model(
        resolved,
        0,
        request_timeout=20,
        max_retries=0,
    ).invoke("Reply with OK.")
    if response is None or not hasattr(response, "content"):
        raise RuntimeError("文本模型未返回 completion message")


def _png_data_url(size: int = 32) -> str:
    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = binascii.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    rows = b"".join(b"\x00" + (b"\xff\xff\xff" * size) for _ in range(size))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _test_vision(resolved: ResolvedModelRole) -> None:
    response = create_vision_completion(
        resolved,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe the image in one word."},
                {"type": "image_url", "image_url": {"url": _png_data_url()}},
            ],
        }],
        max_tokens=128,
        timeout=30,
        stream=False,
    )
    _validate_completion_response(response, label="识图模型")


register_connection_tester("openai_compatible", _test_openai_compatible)
register_connection_tester("ollama", _test_ollama)


def test_model_settings_connection(payload: Mapping[str, object], role: str) -> ResolvedModelRole:
    if role not in {"reasoning", "vision"}:
        raise ValueError("role 必须是 reasoning 或 vision")
    values = dict(os.environ)
    values.update(model_settings_env_values(payload))
    resolved = resolve_model_role(role, values)
    if resolved.provider.requires_api_key and not resolved.api_key:
        raise ValueError("请先填写 API Key")
    try:
        if role == "vision":
            _test_vision(resolved)
        else:
            try:
                tester = _testers[resolved.provider.transport]
            except KeyError as exc:
                raise ValueError(f"{resolved.provider.label} 暂不支持文本连接测试") from exc
            tester(resolved)
    except Exception as exc:
        kind = "图片" if role == "vision" else "文本"
        detail = str(exc).strip() or exc.__class__.__name__
        raise RuntimeError(f"{kind}实际请求失败：{detail}") from exc
    return resolved
