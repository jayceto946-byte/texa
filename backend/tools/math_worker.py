"""Killable SymPy process, bounded input/output and worker lifetime.

Only whitelisted AST math enters the process. No model code is evaluated.
Spawn works on Windows and macOS; no inherited databases or credentials.
"""
from __future__ import annotations
import json
import multiprocessing
import threading
import time
from backend.tools.registry import ToolContext, ToolResult

_SLOTS = threading.BoundedSemaphore(4)


def _worker(connection, tool: str, args: dict):
    try:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
            resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
        except (ImportError, ValueError, OSError):
            pass  # Windows uses parent wall-clock termination.
        from backend.tools.math_tools import (_symbolic_math, _verify_math_result,
            MathInput, MathVerifyInput, _ASSUMPTIONS)
        schema = MathInput if tool == "symbolic_math" else MathVerifyInput
        validated = schema.model_validate(args).model_dump()
        if any(key not in {"x", "y", "z", "t", "n", "a", "b", "c"} for key in validated["assumptions"]):
            raise ValueError("unsupported assumption symbol")
        _ASSUMPTIONS.set(validated["assumptions"])
        handler = _symbolic_math if tool == "symbolic_math" else _verify_math_result
        result = handler(ToolContext(), validated).to_dict()
        if not result["success"]:
            result["data"] = {"status": "error", "error_code": "invalid_expression", "error": result["message"]}
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
        if len(encoded) > 32000:
            raise ValueError("math result exceeds output budget")
        connection.send_bytes(encoded)
    except Exception:
        connection.send_bytes(json.dumps({"success": False, "message": "数学输入无效或计算失败",
            "data": {"status": "error", "error_code": "invalid_input"}}).encode())
    finally:
        connection.close()


def execute_math(tool: str, args: dict, context: ToolContext, *, worker_target=None) -> ToolResult:
    context = context or ToolContext()
    def failure(code):
        return ToolResult(False, data={"status": "error", "error_code": code}, message={
            "timeout": "计算超时", "cancelled": "计算已停止", "capacity": "计算资源繁忙",
            "worker_failed": "计算进程失败"}.get(code, "数学输入无效"))
    if len(json.dumps(args, default=str)) > 16000:
        return failure("invalid_input")
    if not _SLOTS.acquire(blocking=False):
        return failure("capacity")
    mp = multiprocessing.get_context("spawn")
    parent, child = mp.Pipe(duplex=False)
    process = mp.Process(target=worker_target or _worker, args=(child, tool, args), daemon=True)
    started = False
    try:
        if context.cancelled and context.cancelled():
            return failure("cancelled")
        deadline = time.monotonic() + min(5.0, max(.001, context.timeout_seconds))
        process.start()
        started = True
        child.close()
        while True:
            if context.cancelled and context.cancelled():
                return failure("cancelled")
            if time.monotonic() >= deadline:
                return failure("timeout")
            if parent.poll(.02):
                try:
                    result = json.loads(parent.recv_bytes(32000))
                    return ToolResult(**result)
                except (EOFError, OSError, ValueError, TypeError):
                    return failure("worker_failed")
            if not process.is_alive():
                return failure("worker_failed")
    finally:
        if started:
            if process.is_alive():
                process.terminate()
            process.join(.5)
            if process.is_alive():
                process.kill()
                process.join(.5)
            process.close()
        parent.close()
        child.close()
        _SLOTS.release()
