"""Stable failure contract for the Texa embedding runtime."""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingFailure:
    code: str
    stage: str
    recoverable: bool
    message: str
    repair_action: str
    diagnostic_id: str

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "stage": self.stage,
            "recoverable": self.recoverable,
            "message": self.message,
            "repair_action": self.repair_action,
            "diagnostic_id": self.diagnostic_id,
        }


class EmbeddingRuntimeError(RuntimeError):
    """A user-safe, machine-readable Standard runtime failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        stage: str = "embedding_load",
        recoverable: bool = True,
        repair_action: str = "repair_embedding_runtime",
        diagnostic_id: str | None = None,
    ) -> None:
        self.failure = EmbeddingFailure(
            code=code,
            stage=stage,
            recoverable=recoverable,
            message=message,
            repair_action=repair_action,
            diagnostic_id=diagnostic_id or uuid.uuid4().hex[:12],
        )
        super().__init__(f"{code}: {message} (diagnostic_id={self.failure.diagnostic_id})")

    @property
    def code(self) -> str:
        return self.failure.code

    def as_dict(self) -> dict:
        return self.failure.as_dict()


def classify_embedding_error(exc: Exception, *, stage: str = "embedding_load") -> EmbeddingRuntimeError:
    if isinstance(exc, EmbeddingRuntimeError):
        return exc
    text = str(exc) or type(exc).__name__
    lowered = text.lower()
    if "tokenizer" in lowered or "normalizer" in lowered:
        code = "TOKENIZER_MISMATCH"
    elif (
        isinstance(exc, ImportError)
        or "dll load failed" in lowered
        or "no module named 'onnxruntime" in lowered
        or "onnxruntime_pybind11_state" in lowered
    ):
        code = "ORT_IMPORT_FAILURE"
    elif isinstance(exc, FileNotFoundError) or "not found" in lowered or "missing" in lowered:
        code = "MODEL_MISSING"
    elif "architecture" in lowered or "unsupported" in lowered or "win32" in lowered:
        code = "UNSUPPORTED_ARCHITECTURE"
    else:
        code = "MODEL_CORRUPT_OR_INCOMPATIBLE"
    recoverable = code != "UNSUPPORTED_ARCHITECTURE"
    action = "repair_embedding_runtime" if recoverable else "install_supported_windows_x64_release"
    return EmbeddingRuntimeError(
        code,
        text,
        stage=stage,
        recoverable=recoverable,
        repair_action=action,
    )
