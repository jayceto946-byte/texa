"""Main-chat Runtime binding for scoped, canonical read-only capabilities."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid

from backend.services.agent_runtime.contracts import RunCommand, RuntimeConflict
from backend.services.agent_runtime.locator import public_task, runtime_store
from backend.services.agent_runtime.multi_step import BoundedAgentRunner
from backend.services.agent_runtime.outbox import RuntimeOutboxProjector
from backend.services.execution_events import execution_sse_payload
from backend.services.owned_stream import OwnedStreamingResponse
from backend.tools.registry import ToolContext, ToolRegistry

logger = logging.getLogger(__name__)


def build_registry() -> ToolRegistry:
    from backend.services.agent_runtime.progress_tool import register_recent_progress_runtime
    from backend.services.agent_runtime.exercise_tool import register_search_exercises_runtime
    from memory.learning_events import get_learning_event_store
    registry = ToolRegistry()
    register_recent_progress_runtime(registry, get_learning_event_store())
    register_search_exercises_runtime(registry, None)
    from backend.services.agent_runtime.write_tools import register_receipt_backed_write_tools
    register_receipt_backed_write_tools(registry)
    return registry


def build_adapter(registry):
    from config import get_model_role_config
    from llm.agent_adapter import NativeToolAdapter
    return NativeToolAdapter(get_model_role_config(), registry)


def generate_answer(messages):
    from config import get_llm
    return get_llm(temperature=1, request_timeout=30, max_retries=0).invoke(messages).content


def project_outcomes(store):
    from backend.conversation_memory import append_message, update_learning_task_projection
    def append(conversation_id, role, answer, **kwargs):
        task_id = kwargs["message_id"].removeprefix("msg_")
        snapshot = store.task_snapshot(task_id)
        task = public_task(store, snapshot)
        artifacts = task["artifacts"]
        message = append_message(conversation_id, role, answer, **kwargs,
            book_name=artifacts.get("book_name", ""), subject=artifacts.get("subject", ""),
            learning_task=task, answer_mode=task.get("answer_mode", ""), sources=artifacts.get("evidence_sources", []), context_versions=artifacts.get("context_versions", {}))
        update_learning_task_projection(conversation_id, task_id, task)
        return message
    projected = RuntimeOutboxProjector(store, append).drain_once()
    for item in store.pending_outbox():
        if item["kind"] != "chat_learning_event":
            continue
        try:
            from memory.learning_events import LearningEvent, get_learning_event_store
            payload = item["payload"]
            event = LearningEvent(id=f"evt_{item['id']}", event_type="chat_qa",
                book_name=payload["book_name"], subject=payload["subject"], conversation_id=payload["conversation_id"],
                source_type="conversation", source_id=payload["request_id"], payload={"storage_backend": "sqlite-runtime"})
            get_learning_event_store(store.db_path.parent).append(event)
            store.complete_outbox(item["id"], {"event_id": event.id})
            projected += 1
        except Exception as exc:
            store.fail_outbox(item["id"], exc)
    return projected


def resolve_runtime_action(action_id: str, decision: str, pending):
    from backend.services.agent_runtime.write_service import RuntimeWriteService
    action = pending.get(action_id)
    if action is None:
        raise KeyError(action_id)
    task_id = action["context"]["learning_task_id"]
    store = runtime_store()
    snapshot = store.task_snapshot(task_id) if store else None
    if snapshot is None:
        raise RuntimeConflict("Runtime action has no SQL task")
    call = next((item for item in snapshot["tool_calls"] if item["id"] == action_id), None)
    approval = next((item for item in snapshot["approvals"] if item["call_id"] == action_id), None)
    if call is None or approval is None:
        raise RuntimeConflict("Runtime action has no frozen approval")
    if decision == "reject":
        if pending.domain_receipt(action_id) is not None:
            raise RuntimeConflict("executed action cannot be rejected")
        store.reject_approval(action_id, actor_id="local_user")
        action = pending.reject(action_id)
    else:
        stable = uuid.uuid5(uuid.NAMESPACE_URL, f"texa-approval:{action_id}").hex
        if call["status"] == "unknown":
            if pending.domain_receipt(action_id) is None:
                raise RuntimeConflict("unknown write has no receipt; it cannot be retried automatically")
            stable += f"_{snapshot['task_revision']}"
        result = RuntimeWriteService(store, build_registry(), pending).confirm(task_id, action_id,
            actor_id="local_user", args_hash=call["args_hash"], scope=json.loads(approval["scope_json"]),
            expected_revision=snapshot["task_revision"], resume_request_key=f"approval_{stable}",
            request_id=f"req_{stable}", owner_token=f"owner_{stable}", turn_id=snapshot["task"]["turn_id"])
        if call["status"] != "unknown" and result["run"]["status"] == "running" and result["run"]["owner_token"] == f"owner_{stable}":
            store.close(result["run"]["id"], f"owner_{stable}", outcome="paused", error_code="approval_confirmed")
        action = pending.get(action_id)
    snapshot = store.task_snapshot(task_id)
    return {"success": True, "action": action, "learning_task": public_task(store, snapshot)}


def try_chat_response(req, prepared: dict, request_id: str):
    if os.getenv("TEXA_AGENT_RUNTIME_READ", "0") != "1":
        return None
    # Preserve the existing visual, textbook, clarification and required-input gates.
    allow_textbook = os.getenv("TEXA_AGENT_RUNTIME_TEXTBOOK", "0") == "1"
    if prepared["answer_mode"] not in {"global_general", "subject_general", "textbook_grounded"} or (prepared["use_textbook_context"] and not allow_textbook):
        return None
    if prepared["resolution_trace"].get("resolution_action") in {"clarify", "respond"}:
        return None
    from backend.services.decision.contracts import DecisionContext
    from backend.services.decision.router import DecisionRouter
    from backend.services.decision.resolver import resolve_candidate_tools
    decision = DecisionRouter(shadow=False).route(DecisionContext(request_id=request_id, text=req.question,
        resolved_query=prepared["rewritten_question"], answer_mode=prepared["answer_mode"]))
    writes = {"exercise.create_set", "mistake.manage", "exercise.record_result"}
    allow_write = os.getenv("TEXA_AGENT_RUNTIME_WRITE", "0") == "1"
    if decision.selected_capability not in {"learning.inspect", "exercise.inspect"} | (writes if allow_write else set()) | ({"textbook.search"} if allow_textbook else set()):
        return None
    if decision.selected_capability in writes and not prepared["book_name"]:
        return None
    if decision.selected_capability == "exercise.inspect" and not prepared["book_name"]:
        return None
    registry = build_registry()
    scope = None
    if decision.selected_capability == "textbook.search":
        from graph.intent_classifier import classify_intent_local
        if classify_intent_local(prepared["rewritten_question"]).get("intent") in {"teach", "summarize"}:
            return None
        from backend.services.agent_runtime.textbook_tool import freeze_textbook_scope, register_textbook_search_runtime
        scope = freeze_textbook_scope(prepared["book_name"], prepared["subject"])
        register_textbook_search_runtime(registry, scope)
    baseline = os.getenv("TEXA_RUNTIME_POLICY_V0", "0") == "1" and decision.selected_capability not in writes
    adapter = None if baseline else build_adapter(registry)
    if not baseline and adapter.capabilities().tool_calling != "supported":
        return None  # No task has been claimed by SQL yet.
    candidates = resolve_candidate_tools(decision, registry,
        allowed_permissions=frozenset({"READ", "LOCAL_WRITE"}) if allow_write else frozenset({"READ"})).tool_refs
    if baseline:
        from backend.services.decision.policy_projection import matched_tool_refs
        candidates, _ = matched_tool_refs(prepared["rewritten_question"], registry,
            grounded=prepared["answer_mode"] == "textbook_grounded")
    if not candidates:
        return None
    from graph.main_graph import build_initial_state
    from backend.services.answer_verification import derive_required_outputs
    state = build_initial_state(prepared["rewritten_question"], book_name=prepared["book_name"],
        subject=prepared["subject"], conversation_id=prepared["conversation_id"],
        use_textbook_context=prepared["use_textbook_context"], answer_mode=prepared["answer_mode"],
        scope_reason=prepared["scope_reason"], continuity_context=prepared["continuity_context"])
    state["intent"] = "qa"
    state["context_versions"] = prepared.get("context_versions") or {}
    if scope:
        state["_runtime_textbook_scope"] = scope
    store = runtime_store(create=True)
    owner = uuid.uuid4().hex
    command = RunCommand(request_id, request_id, f"rtask_{uuid.uuid4().hex}",
        prepared["conversation_id"], prepared["turn_id"], prepared["rewritten_question"], owner,
        budget_calls=3, budget_model_calls=5,
        required_outputs=derive_required_outputs(req.question, intent="qa", answer_mode=prepared["answer_mode"]))
    snapshot = store.create(command)
    run_id = snapshot["run"]["id"]
    from backend.services.runtime_events import emit_best_effort as emit_runtime_event, text_fingerprint
    audit = {"session_id": prepared["conversation_id"], "turn_id": prepared["turn_id"],
             "request_id": request_id, "task_id": command.task_id, "run_id": run_id}
    emit_runtime_event("user_input", **audit,
                       payload={**text_fingerprint(req.question), "answer_mode": prepared["answer_mode"]})
    emit_runtime_event("active_goal", **audit,
                       payload={"goal_ref": command.task_id, "goal_status": "running",
                                "required_output_count": len(command.required_outputs)})
    emit_runtime_event("decision", **audit,
                       payload={"route": "bounded_runtime", "decision_mode": decision.mode,
                                "capability": decision.selected_capability or "direct_answer",
                                "shadow_only": decision.shadow_only})
    store.configure_chat(run_id, owner, state=state, candidates=candidates,
        request_question=req.question, book_name=prepared["book_name"], subject=prepared["subject"], policy_baseline=baseline)
    return stream_run(store, run_id, owner, registry, adapter)


def stream_run(store, run_id: str, owner: str, registry=None, adapter=None):
    registry = registry or build_registry()
    initial = store.snapshot(run_id)
    checkpoint = initial["run"]["checkpoint"]
    baseline = checkpoint.get("policy_baseline") == "texa.runtime-policy/v0"
    if not baseline:
        adapter = adapter or build_adapter(registry)
    if checkpoint.get("answer_state", {}).get("_runtime_textbook_scope"):
        from backend.services.agent_runtime.textbook_tool import register_textbook_search_runtime
        try:
            registry.runtime_tool("search_textbook")
        except KeyError:
            register_textbook_search_runtime(registry, checkpoint["answer_state"]["_runtime_textbook_scope"])
    task = initial["task"]
    def pause():
        current = store.snapshot(run_id)
        if current["run"]["status"] == "running":
            try:
                store.close(run_id, owner, outcome="paused", error_code="transport_closed")
            except RuntimeConflict:
                pass
    def work():
        try:
            from backend.conversation_memory import append_message
            append_message(task["conversation_id"], "user", task["artifacts"]["request_question"],
                turn_id=task["turn_id"], request_id=initial["run"]["request_id"],
                book_name=task["artifacts"].get("book_name", ""), subject=task["artifacts"].get("subject", ""))
            from backend.services.pending_actions import get_pending_action_store
            from backend.services.agent_runtime.write_service import RuntimeWriteService
            from backend.services.decision.policy import RulePolicyV0
            BoundedAgentRunner(store, registry, adapter, tuple(checkpoint["candidates"]),
                policy_selector=RulePolicyV0 if baseline else None).run_bounded(
                run_id, owner, context=ToolContext(book_name=task["artifacts"].get("book_name", ""),
                    subject=task["artifacts"].get("subject", ""), conversation_id=task["conversation_id"]),
                answer_state=checkpoint["answer_state"], answer_generator=generate_answer,
                write_service=RuntimeWriteService(store, registry, get_pending_action_store()))
        except RuntimeConflict:
            pass  # A user stop or another run owns the task now.
        except Exception:
            logger.exception("Runtime chat failed")
            current = store.snapshot(run_id)
            if current["run"]["status"] == "running":
                store.close(run_id, owner, outcome="failed", error_code="runtime_failed")
        try:
            project_outcomes(store)
        except Exception:
            logger.exception("Runtime answer projection deferred to recovery")
    async def events():
        worker = threading.Thread(target=work, name="texa-runtime-chat", daemon=True)
        worker.start()
        cursor = 0
        while True:
            snapshot, batch = store.stream_snapshot(run_id, after_seq=cursor)
            for event in batch:
                sidecar = {"learning_task": public_task(store, snapshot),
                    "book_name": task["artifacts"].get("book_name", ""),
                    "answer_mode": task.get("answer_mode", "")}
                # The delta sequence was reserved in the outcome transaction.
                if event["type"] == "final":
                    delta = {**event, "seq": event["seq"] - 1, "type": "output_delta",
                        "phase": "generate", "kind": "generation", "status": "running",
                        "payload": {"text": snapshot["run"]["output"]["answer"], "replace": True}}
                    yield f"data: {json.dumps(execution_sse_payload(delta), ensure_ascii=False)}\n\n"
                    sidecar["message_id"] = f"msg_{task['id']}"
                    sidecar["state"] = {"evidence_sources": snapshot["task"]["artifacts"].get("evidence_sources", [])}
                yield f"data: {json.dumps(execution_sse_payload(event, sidecar=sidecar), ensure_ascii=False)}\n\n"
                cursor = event["seq"]
            if snapshot["run"]["status"] != "running" and len(batch) < 100:
                break
            await asyncio.sleep(.03)
    return OwnedStreamingResponse(events(), on_close=pause, media_type="text/event-stream")
