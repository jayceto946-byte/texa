"""Offline bounded P2a driver over the same SQL authority and tool executor.

Production chat binding waits for scoped evidence, outbox projection, and desktop
recovery gates. This driver deliberately has no HTTP entry point.
"""
from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
from typing import Callable, Protocol

from backend.services.agent_runtime.contracts import FixedAction, ModelCapabilities, RuntimeDenied, RuntimeConflict
from backend.services.agent_runtime.runner import FixedRunner
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.answer_verification import verify_answer, verification_notice
from backend.tools.registry import ToolContext, ToolRegistry
from utils.thinking_filter import strip_thinking

_MODEL_SLOTS = threading.BoundedSemaphore(2)


def _bounded_model_call(action: Callable, timeout: float):
    if not _MODEL_SLOTS.acquire(blocking=False):
        raise RuntimeDenied("model worker capacity exhausted")
    results = queue.Queue(maxsize=1)
    def invoke():
        try:
            results.put((True, action()))
        except BaseException as exc:
            results.put((False, exc))
        finally:
            _MODEL_SLOTS.release()
    worker = threading.Thread(target=invoke, name="texa-runtime-model", daemon=True)
    try:
        worker.start()
    except BaseException:
        _MODEL_SLOTS.release()
        raise
    try:
        ok, result = results.get(timeout=timeout)
    except queue.Empty as exc:
        raise RuntimeDenied("model response deadline exceeded") from exc
    if not ok:
        raise RuntimeDenied("model adapter failed") from result
    return result


class ActionAdapter(Protocol):
    def capabilities(self) -> ModelCapabilities: ...
    def next_action(self, transcript: list[dict], candidate_tools: tuple[dict, ...]) -> FixedAction: ...


@dataclass
class BoundedAgentRunner:
    store: RuntimeStore
    registry: ToolRegistry
    adapter: ActionAdapter
    candidate_tools: tuple[dict, ...]
    model_timeout_seconds: float = 35.0

    def run_offline(self, run_id: str, owner: str, *, context: ToolContext | None = None,
                    answer_state: dict | None = None,
                    answer_generator: Callable | None = None, write_service=None) -> dict:
        if (answer_state is None) != (answer_generator is None):
            raise ValueError("shared answer state and generator must be supplied together")
        if not 0 < self.model_timeout_seconds <= 35:
            raise ValueError("invalid model deadline")
        capabilities = self.adapter.capabilities()
        if capabilities.tool_calling != "supported":
            raise RuntimeDenied("model adapter has no verified tool-calling capability")
        allowed = frozenset(str(item["id"]) for item in self.candidate_tools)
        tool_runner = FixedRunner(self.store, self.registry, allowlist=allowed)
        while True:
            snapshot = self.store.snapshot(run_id)
            if snapshot["run"]["status"] != "running":
                return snapshot
            transcript = list(snapshot["run"]["checkpoint"].get("transcript") or [])
            if not transcript:
                transcript = [{"role": "user", "content": snapshot["task"]["goal"]}]
                if context is not None:
                    transcript[0]["learning_scope"] = {"book_name": context.book_name, "subject": context.subject}
            try:
                started = self.store.start_model_step(run_id, owner)
            except RuntimeConflict:
                return self.store.close(run_id, owner, outcome="failed", error_code="model_budget_exhausted")
            try:
                action = _bounded_model_call(lambda: self.adapter.next_action(transcript, self.candidate_tools),
                                             self.model_timeout_seconds)
                if not isinstance(action, FixedAction):
                    raise RuntimeDenied("adapter returned an invalid action")
            except Exception:
                return self.store.close(run_id, owner, outcome="failed", error_code="model_action_failed")
            # The adapter's text is a protocol response, not an answer until finish.
            self.store.complete_model_step(run_id, owner, action_kind=action.kind,
                transcript=transcript + [{"role": "assistant_action", "kind": action.kind,
                                          "tool_id": action.tool_id if action.kind == "call" else "",
                                          "arguments": action.args if action.kind == "call" else {}}])
            if action.kind == "finish":
                answer = strip_thinking(action.answer).strip()
                answer_sources = []
                required = snapshot["task"].get("required_outputs") or []
                from backend.services.tool_orchestration import build_tool_context_pack
                tool_outputs = []
                for item in snapshot["tool_calls"]:
                    if item["status"] not in {"succeeded", "failed", "unknown"}:
                        continue
                    result = dict(item["result"] or {})
                    if result.get("domain_receipt"):
                        result["data"] = result["domain_receipt"]
                    tool_outputs.append({"tool": item["tool_id"], "result": result})
                tool_pack = build_tool_context_pack(tool_outputs)
                if answer_state is not None:
                    from graph.generator import (prepare_answer_generation,
                                                 finalize_generated_answer,
                                                 has_textbook_evidence)
                    state = {**answer_state, "required_outputs": required,
                             "tool_context_pack": tool_pack}
                    textbook_results = [item["result"]["data"] for item in tool_outputs
                        if item["tool"] == "search_textbook" and item["result"].get("success") and item["result"].get("data")]
                    if textbook_results:
                        latest = textbook_results[-1]
                        if latest["query_scope"] != state.get("_runtime_textbook_scope"):
                            return self.store.close(run_id, owner, outcome="failed", error_code="answer_scope_changed")
                        state["evidence_items"] = latest["evidence_items"]
                        state["evidence_support"] = latest["evidence_support"]
                    # Grounded tasks need the retrieval/EvidencePack boundary first.
                    if state.get("use_textbook_context", True) and not has_textbook_evidence(state):
                        return self.store.close(run_id, owner, outcome="failed",
                                                error_code="answer_evidence_missing")
                    try:
                        self.store.start_model_step(run_id, owner)
                        messages = prepare_answer_generation(state)
                        generated = _bounded_model_call(lambda: answer_generator(messages), self.model_timeout_seconds)
                        if not isinstance(generated, str):
                            raise RuntimeDenied("answer generator returned non-text output")
                        answer = finalize_generated_answer(state, generated)
                        verification = state["answer_verification"]
                        answer_sources = state.get("evidence_sources") or []
                        self.store.complete_model_step(run_id, owner, action_kind="answer",
                            transcript=transcript + [{"role": "assistant_action", "kind": "answer"}])
                    except Exception:
                        return self.store.close(run_id, owner, outcome="failed",
                                                error_code="answer_generation_failed")
                else:
                    verification = verify_answer(answer, required_outputs=required,
                        tool_context_pack=tool_pack)
                outcome = "completed" if verification["status"] == "passed" else "degraded"
                if outcome == "degraded" and verification_notice(verification) not in answer:
                    answer = f"{answer}\n\n{verification_notice(verification)}".strip()
                return self.store.close(run_id, owner, outcome=outcome,
                                        answer=answer, verification=verification, sources=answer_sources)
            if action.kind != "call" or action.tool_id not in allowed:
                return self.store.close(run_id, owner, outcome="failed", error_code="tool_not_authorized")
            action = FixedAction("call", tool_id=action.tool_id, args=action.args,
                                 operation_key=f"step-{started['consumed_model_calls']}")
            try:
                metadata = self.registry.runtime_tool(action.tool_id).runtime_metadata()
                ref = next(item for item in self.candidate_tools if item["id"] == action.tool_id)
                if (metadata["schema_hash"], metadata["version"]) != (ref["schema_hash"], ref["version"]):
                    raise RuntimeDenied("candidate schema or version changed")
                if metadata["permission"] == "LOCAL_WRITE":
                    if write_service is None or context is None:
                        raise RuntimeDenied("write proposal service is unavailable")
                    return write_service.propose(run_id, owner, tool_id=action.tool_id,
                        args=action.args, operation_key=action.operation_key, context=context)
                tool_runner.execute(run_id, owner, action, context=context)
            except (RuntimeDenied, RuntimeConflict, ValueError):
                return self.store.close(run_id, owner, outcome="failed", error_code="tool_step_denied")
