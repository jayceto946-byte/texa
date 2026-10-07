"""Bounded SQL runtime driver used by Chat and Goal workers."""
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
    policy_selector: Callable | None = None
    policy_source: str = "rules"
    policy_capture: Callable | None = None
    policy_observe: Callable | None = None

    def run_bounded(self, run_id: str, owner: str, *, context: ToolContext | None = None,
                    answer_state: dict | None = None,
                    answer_generator: Callable | None = None, write_service=None) -> dict:
        if (answer_state is None) != (answer_generator is None):
            raise ValueError("shared answer state and generator must be supplied together")
        if not 0 < self.model_timeout_seconds <= 35:
            raise ValueError("invalid model deadline")
        if self.policy_selector is not None:
            if answer_state is None:
                raise ValueError("Policy baseline requires the shared answer chain")
            return self._run_policy(run_id, owner, context=context or ToolContext(),
                answer_state=answer_state, answer_generator=answer_generator)
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
                return self._generate_answer(run_id, owner, snapshot, action, transcript,
                    answer_state, answer_generator)
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

    def _generate_answer(self, run_id, owner, snapshot, action, transcript,
                         answer_state, answer_generator, policy_attempt=None, policy_fence=None, policy_context=None):
        if snapshot["task"].get("required_inputs") or (answer_state or {}).get("required_inputs") or (answer_state or {}).get("missing_inputs"):
            return self._close_answer(policy_attempt, run_id, owner, outcome="failed", error_code="required_input_missing")
        if policy_context is not None and not self._policy_scope_valid(answer_state, policy_context):
            return self._close_answer(policy_attempt, run_id, owner, outcome="failed", error_code="answer_scope_changed")
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
                    return self._close_answer(policy_attempt, run_id, owner, outcome="failed", error_code="answer_scope_changed")
                state["evidence_items"] = latest["evidence_items"]
                state["evidence_support"] = latest["evidence_support"]
            # Grounded tasks need the retrieval/EvidencePack boundary first.
            if state.get("use_textbook_context", True) and not has_textbook_evidence(state):
                return self._close_answer(policy_attempt, run_id, owner, outcome="failed",
                                        error_code="answer_evidence_missing")
            try:
                self.store.start_model_step(run_id, owner, expected_revisions=policy_fence)
                messages = prepare_answer_generation(state)
                generated = _bounded_model_call(lambda: answer_generator(messages), self.model_timeout_seconds)
                if not isinstance(generated, str):
                    raise RuntimeDenied("answer generator returned non-text output")
                answer = finalize_generated_answer(state, generated)
                verification = state["answer_verification"]
                answer_sources = state.get("evidence_sources") or []
                self.store.complete_model_step(run_id, owner, action_kind="answer",
                    transcript=transcript + [{"role": "assistant_action", "kind": "answer"}])
            except RuntimeConflict:
                if policy_attempt is not None:
                    raise
                return self._close_answer(policy_attempt, run_id, owner, outcome="failed",
                                          error_code="answer_generation_failed")
            except Exception:
                return self._close_answer(policy_attempt, run_id, owner, outcome="failed",
                                        error_code="answer_generation_failed")
        else:
            verification = verify_answer(answer, required_outputs=required,
                tool_context_pack=tool_pack)
        if policy_context is not None and not self._policy_scope_valid(answer_state, policy_context):
            return self._close_answer(policy_attempt, run_id, owner, outcome="failed", error_code="answer_scope_changed")
        outcome = "completed" if verification["status"] == "passed" else "degraded"
        if outcome == "degraded" and verification_notice(verification) not in answer:
            answer = f"{answer}\n\n{verification_notice(verification)}".strip()
        return self._close_answer(policy_attempt, run_id, owner, outcome=outcome,
                                answer=answer, verification=verification, sources=answer_sources)

    def _policy_scope_valid(self, state, context):
        if not state.get("_runtime_textbook_scope"):
            return True
        try:
            spec = self.registry.runtime_tool("search_textbook")
            if spec.runtime_scope_check:
                spec.runtime_scope_check(context, {"query": state.get("user_input", ""), "chapter": ""})
        except (KeyError, ValueError):
            return False
        return True

    def _close_answer(self, attempt, run_id, owner, **kwargs):
        if attempt is not None:
            from backend.services.decision.policy import project_outcome
            status = kwargs["outcome"]
            kwargs["policy_outcome"] = project_outcome(attempt, task_status=status,
                execution="succeeded" if status in {"completed", "degraded"} else "failed",
                result_refs=[f"answer:{run_id}"] if kwargs.get("answer") else []).model_dump()
        return self.store.close(run_id, owner, **kwargs)

    def _run_policy(self, run_id, owner, *, context, answer_state, answer_generator):
        from backend.services.decision.policy import select_decision, project_outcome, PolicyRejected
        from backend.services.decision.policy_projection import project_observation, runtime_identity
        allowed = frozenset(item["id"] for item in self.candidate_tools)
        tool_runner = FixedRunner(self.store, self.registry, allowlist=allowed)
        def project():
            snapshot = self.store.snapshot(run_id)
            return project_observation(request=snapshot["task"]["artifacts"].get("request_question", snapshot["task"]["goal"]),
                resolved_query=answer_state.get("user_input", snapshot["task"]["goal"]),
                goal=snapshot["task"]["goal"], registry=self.registry, context=context,
                identity=runtime_identity(snapshot), candidate_tools=self.candidate_tools,
                snapshot=snapshot, answer_state=answer_state,
                missing_inputs=snapshot["task"].get("required_inputs") or answer_state.get("missing_inputs") or answer_state.get("required_inputs") or [])
        while True:
            snapshot = self.store.snapshot(run_id)
            if snapshot["run"]["status"] != "running":
                return snapshot
            frozen = project()
            if self.policy_observe:
                self.policy_observe(frozen)
            if not frozen.envelope.payload.admissible_actions:
                # Runtime handles the gap through the original input/evidence/
                # generation-budget checks; zero candidates never enter selection.
                return self._generate_answer(run_id, owner, snapshot, FixedAction("finish"),
                    list(snapshot["run"]["checkpoint"].get("transcript") or []), answer_state, answer_generator,
                    policy_fence=(snapshot["task_revision"], snapshot["run"]["revision"]), policy_context=context)
            def record(attempt):
                outcome = project_outcome(attempt, task_status=snapshot["task"]["status"]) if attempt.validation.status == "rejected" else None
                self.store.record_policy_attempt(run_id, owner, attempt.metadata(),
                    expected_task_revision=snapshot["task_revision"], expected_run_revision=snapshot["run"]["revision"],
                    outcome=outcome.model_dump() if outcome else None)
                if outcome is not None and self.policy_capture:
                    self.policy_capture(frozen, attempt, outcome)
            try:
                binding, attempt, _ = select_decision(frozen, selector=self.policy_selector,
                    source=self.policy_source, current=project, record=record)
            except PolicyRejected as exc:
                if exc.code == "stale_observation":
                    raise RuntimeConflict("Policy observation is stale") from exc
                return self.store.close(run_id, owner, outcome="failed", error_code=exc.code)
            if binding["kind"] == "generate_answer":
                result = self._generate_answer(run_id, owner, snapshot, FixedAction("finish"),
                    list(snapshot["run"]["checkpoint"].get("transcript") or []), answer_state, answer_generator, attempt,
                    (snapshot["task_revision"], snapshot["run"]["revision"]), context)
                from backend.services.decision.policy_contracts import PolicyOutcomeV0
                outcome = PolicyOutcomeV0.model_validate(result["execution_events"][-1]["payload"]["policy_outcome"])
                if self.policy_capture:
                    self.policy_capture(frozen, attempt, outcome)
                return result
            args = binding["args"]
            action = FixedAction("call", tool_id=args["tool_id"], args=args["input"],
                operation_key="policy-" + attempt.decision_ref)
            try:
                result = tool_runner.execute(run_id, owner, action, context=context,
                    expected_revisions=(snapshot["task_revision"], snapshot["run"]["revision"]))
            except RuntimeConflict:
                raise
            except (RuntimeDenied, ValueError):
                outcome = project_outcome(attempt, task_status="failed", execution="not_started")
                result = self.store.close(run_id, owner, outcome="failed", error_code="tool_step_denied",
                                          policy_outcome=outcome.model_dump())
                if self.policy_capture:
                    self.policy_capture(frozen, attempt, outcome)
                return result
            call = next(item for item in result["tool_calls"] if item["operation_key"] == action.operation_key)
            outcome = project_outcome(attempt, task_status=result["task"]["status"],
                                      execution=call["status"], result_refs=[call["id"]])
            self.store.record_policy_outcome(run_id, owner, outcome.model_dump())
            if self.policy_capture:
                self.policy_capture(frozen, attempt, outcome)
