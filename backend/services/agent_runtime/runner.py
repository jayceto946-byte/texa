"""Fixed zero/one READ tool driver for P0 service tests."""
from __future__ import annotations

import hashlib
import json
import queue
import threading
from typing import Any

from backend.services.agent_runtime.contracts import FixedAction, RunCommand, RuntimeDenied
from backend.services.agent_runtime.store import RuntimeStore
from backend.tools.registry import ToolContext, ToolRegistry, ToolResult


_TOOL_SLOTS = threading.BoundedSemaphore(2)


class FixedRunner:
    def __init__(self, store: RuntimeStore, registry: ToolRegistry, *,
                 allowlist: frozenset[str] = frozenset({"get_recent_progress"}),
                 allowed_sources: frozenset[str] = frozenset({"builtin"}),
                 max_inflight: int = 2):
        self.store = store
        self.registry = registry
        self.allowlist = allowlist
        self.allowed_sources = allowed_sources
        self._slots = threading.BoundedSemaphore(max_inflight)

    def start(self, command: RunCommand) -> dict[str, Any]:
        return self.store.create(command)

    def _validated_tool(self, action: FixedAction):
        if action.tool_id not in self.allowlist:
            raise RuntimeDenied("tool is not in the P0 allowlist")
        try:
            spec = self.registry.runtime_tool(action.tool_id)
        except KeyError as exc:
            raise RuntimeDenied("unknown tool") from exc
        metadata = spec.runtime_metadata()
        if not spec.read_only or metadata["permission"] != "READ" or metadata["side_effect"] not in {"none", "derived_cache"} or metadata["source"] not in self.allowed_sources:
            raise RuntimeDenied("read tool permission or source is not authorized")
        args = spec.runtime_input.model_validate(action.args).model_dump()
        return spec, metadata, args

    def execute(self, run_id: str, owner: str, action: FixedAction,
                *, context: ToolContext | None = None) -> dict[str, Any]:
        if action.kind == "finish":
            return self.store.close(run_id, owner, outcome="completed", answer=action.answer)
        if action.kind != "call":
            raise RuntimeDenied("unsupported P0 action")
        spec, metadata, args = self._validated_tool(action)
        if context is not None:
            for field in ("book_name", "subject"):
                if args.get(field) and args[field] != getattr(context, field):
                    raise RuntimeDenied("tool scope differs from the selected learning scope")
        operation_key = action.operation_key.strip()
        if not operation_key or len(operation_key) > 160:
            raise RuntimeDenied("stable operation key required")
        args_hash = hashlib.sha256(json.dumps(args, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        # Check the bounded worker quota before reserving the operation or launching work.
        if not self._slots.acquire(blocking=False):
            raise RuntimeDenied("tool execution capacity exhausted")
        if not _TOOL_SLOTS.acquire(blocking=False):
            self._slots.release()
            raise RuntimeDenied("process tool execution capacity exhausted")
        started = False
        try:
            snapshot = self.store.request_tool(
                run_id, owner, tool_id=spec.name, version=spec.version,
                schema_hash=metadata["schema_hash"], args=args,
                args_hash=args_hash, operation_key=operation_key)
            matching = [call for call in snapshot["tool_calls"] if call["operation_key"] == operation_key]
            if not matching or matching[0]["requested_run_id"] != run_id or matching[0]["status"] != "requested":
                raise RuntimeDenied("operation was already executed")
            call_id = matching[0]["id"]
            self.store.start_tool(run_id, owner, call_id)
            results: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)

            def invoke() -> None:
                try:
                    results.put(("ok", spec.handler(context or ToolContext(), args)))
                except BaseException as exc:
                    results.put(("error", exc))
                finally:
                    self._slots.release()
                    _TOOL_SLOTS.release()

            thread = threading.Thread(target=invoke, name="texa-p0-read-tool", daemon=True)
            thread.start()
            started = True
            try:
                kind, value = results.get(timeout=spec.timeout_seconds)
            except queue.Empty:
                return self.store.finish_tool(run_id, owner, call_id,
                                              {"success": False, "message": "tool timed out"},
                                              error_code="timeout")
            if kind == "error":
                return self.store.finish_tool(run_id, owner, call_id,
                                              {"success": False, "message": "tool failed"},
                                              error_code="handler_error")
            result: ToolResult = value
            if not result.success:
                return self.store.finish_tool(run_id, owner, call_id, result.to_dict(),
                                              error_code="tool_failed")
            try:
                output = spec.runtime_output.model_validate(result.data).model_dump()
            except Exception:
                return self.store.finish_tool(run_id, owner, call_id,
                                              {"success": False, "message": "invalid tool output"},
                                              error_code="output_schema")
            payload = {**result.to_dict(), "data": output}
            return self.store.finish_tool(run_id, owner, call_id, payload)
        finally:
            if not started:
                self._slots.release()
                _TOOL_SLOTS.release()

    def pause(self, run_id: str, owner: str) -> dict[str, Any]:
        return self.store.close(run_id, owner, outcome="paused", error_code="interrupted")
