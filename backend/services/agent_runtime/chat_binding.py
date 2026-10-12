"""Main-chat Runtime binding for scoped, canonical read-only capabilities."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid
import queue

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
    from backend.tools.math_tools import register_math_tools
    register_math_tools(registry)
    return registry


def build_math_registry():
    from backend.tools.math_tools import register_math_tools
    registry = ToolRegistry()
    register_math_tools(registry)
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
        try:
            from backend.services.session_ledger import record_assistant_in_ledger
            record_assistant_in_ledger(conversation_id, message)
        except Exception:
            logger.exception("Runtime assistant ledger projection deferred")
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


def try_chat_response(req, prepared: dict, request_id: str, *, streaming=True):
    from backend.services.agent_runtime.math_support import explicit_math_only
    pure_math = explicit_math_only(req.question, prepared["rewritten_question"],
        scope_reason=prepared.get("scope_reason", ""), attachments=bool(getattr(req, "images", None)))
    # Preserve the existing visual, textbook, clarification and required-input gates.
    allow_textbook = os.getenv("TEXA_AGENT_RUNTIME_TEXTBOOK", "0") == "1"
    if prepared["answer_mode"] not in {"global_general", "subject_general", "textbook_grounded"} or (prepared["use_textbook_context"] and not allow_textbook and not pure_math):
        return None
    if prepared["resolution_trace"].get("resolution_action") in {"clarify", "respond"}:
        return None
    from backend.services.decision.contracts import DecisionContext
    from backend.services.decision.router import DecisionRouter
    from backend.services.decision.resolver import resolve_candidate_tools
    decision = DecisionRouter(shadow=False).route(DecisionContext(request_id=request_id, text=req.question,
        resolved_query=prepared["rewritten_question"], answer_mode=prepared["answer_mode"],
        question_understanding=prepared["resolution_trace"].get("question_understanding") or {}))
    if pure_math:
        from backend.services.decision.contracts import DecisionResult
        decision = DecisionResult("capability", selected_capability="math.verify", rule_match="explicit_math_only")
    math_route = decision.selected_capability == "math.verify"
    if math_route and os.getenv("TEXA_AGENT_RUNTIME_MATH", "1") != "1":
        return None
    if not math_route and os.getenv("TEXA_AGENT_RUNTIME_READ", "0") != "1":
        return None
    writes = {"exercise.create_set", "mistake.manage", "exercise.record_result"}
    allow_write = os.getenv("TEXA_AGENT_RUNTIME_WRITE", "0") == "1"
    if decision.selected_capability not in {"learning.inspect", "exercise.inspect", "math.verify"} | (writes if allow_write else set()) | ({"textbook.search"} if allow_textbook else set()):
        return None
    if decision.selected_capability in writes and not prepared["book_name"]:
        return None
    if decision.selected_capability == "exercise.inspect" and not prepared["book_name"]:
        return None
    registry = build_math_registry() if math_route else build_registry()
    scope = None
    if decision.selected_capability == "textbook.search":
        from graph.intent_classifier import classify_intent_local
        from graph.question_understanding import interpretation_hint
        hint = interpretation_hint(prepared["resolution_trace"].get("question_understanding"))
        if classify_intent_local(prepared["rewritten_question"]).get("intent") in {"teach", "summarize"} or hint.get("intent") in {"teach", "summarize"}:
            return None
        from backend.services.agent_runtime.textbook_tool import freeze_textbook_scope, register_textbook_search_runtime
        scope = freeze_textbook_scope(prepared["book_name"], prepared["subject"])
        register_textbook_search_runtime(registry, scope)
    baseline = os.getenv("TEXA_RUNTIME_POLICY_V0", "0") == "1" and decision.selected_capability not in writes and not math_route
    adapter = None if baseline else build_adapter(registry)
    if math_route and hasattr(adapter, "allow_native_attempt"):
        adapter.allow_native_attempt = True
    if not baseline and adapter.capabilities().tool_calling != "supported":
        return None  # No task has been claimed by SQL yet.
    candidates = resolve_candidate_tools(decision, registry,
        allowed_permissions=frozenset({"READ", "LOCAL_WRITE"}) if allow_write else frozenset({"READ"})).tool_refs
    if baseline:
        from backend.services.decision.policy_projection import matched_tool_refs
        candidates, _ = matched_tool_refs(prepared["rewritten_question"], registry,
            grounded=prepared["answer_mode"] == "textbook_grounded",
            understanding=prepared["resolution_trace"].get("question_understanding"))
    if not candidates:
        return None
    from graph.main_graph import build_initial_state
    from backend.services.answer_verification import derive_required_outputs
    state = build_initial_state(prepared["rewritten_question"], book_name=prepared["book_name"],
        subject=prepared["subject"], conversation_id=prepared["conversation_id"],
        use_textbook_context=prepared["use_textbook_context"], answer_mode=prepared["answer_mode"],
        scope_reason=prepared["scope_reason"], continuity_context=prepared["continuity_context"])
    state["intent"] = "qa"
    state["native_loop"] = math_route and hasattr(adapter, "run_native")
    if pure_math:
        state.update(support_type="explicit_math_only", evidence_support={"status": "not_applicable", "reason": "explicit_math_only"})
    state["context_versions"] = prepared.get("context_versions") or {}
    state["_resolution_trace"] = prepared["resolution_trace"]
    if scope:
        state["_runtime_textbook_scope"] = scope
    store = runtime_store(create=True)
    owner = uuid.uuid4().hex
    required = derive_required_outputs(req.question, intent="qa", answer_mode=prepared["answer_mode"])
    if pure_math:
        required = [output for output in required if output["kind"] != "citation"]
        required.append({"id": "math_support", "kind": "math_support", "label": "与题目及最终结论绑定的计算核验", "required": True})
    command = RunCommand(request_id, request_id, f"rtask_{uuid.uuid4().hex}",
        prepared["conversation_id"], prepared["turn_id"], prepared["rewritten_question"], owner,
        budget_calls=3, budget_model_calls=5,
        required_outputs=required)
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
    if streaming:
        return stream_run(store, run_id, owner, registry, adapter)
    execute_run(store, run_id, owner, registry, adapter)
    result = store.snapshot(run_id)
    task = public_task(store, result)
    return {"request_id": request_id, "message_id": f"msg_{task['id']}",
        "content": (result["run"]["output"] or {}).get("answer", ""),
        "learning_task": task, "answer_verification": task.get("verification") or {},
        "answer_mode": prepared["answer_mode"], "scope_reason": prepared["scope_reason"],
        "conversation_id": prepared["conversation_id"], "book_name": prepared["book_name"],
        "sources": task["artifacts"].get("evidence_sources", []),
        "execution_events": store.events(run_id, limit=500), "context_versions": state["context_versions"]}


def stream_run(store, run_id: str, owner: str, registry=None, adapter=None):
    initial = store.snapshot(run_id)
    checkpoint = initial["run"]["checkpoint"]
    registry = registry or (build_math_registry() if all(ref["id"] in {"symbolic_math", "verify_math_result"} for ref in checkpoint["candidates"]) else build_registry())
    baseline = checkpoint.get("policy_baseline") == "texa.runtime-policy/v0"
    if not baseline:
        adapter = adapter or build_adapter(registry)
        if hasattr(adapter, "allow_native_attempt") and any(ref["id"] == "symbolic_math" for ref in checkpoint["candidates"]):
            adapter.allow_native_attempt = True
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
    output_queue = queue.Queue()
    stream_lock = threading.Lock()
    def on_output(text, replace=False):
        # Lock snapshot reads with reservation+enqueue, preventing skipped deltas.
        with stream_lock:
            for offset in range(0, max(1, len(text)), 400):
                output_queue.put(store.output_delta(run_id, owner, text[offset:offset+400], replace=replace and offset == 0))
    def work():
        execute_run(store, run_id, owner, registry, adapter, on_output=on_output)
    async def events():
        worker = threading.Thread(target=work, name="texa-runtime-chat", daemon=True)
        worker.start()
        cursor = 0
        while True:
            with stream_lock:
                snapshot, batch = store.stream_snapshot(run_id, after_seq=cursor)
                while not output_queue.empty():
                    delta = output_queue.get_nowait()
                    if delta["seq"] > cursor:
                        batch.append(delta)
            batch.sort(key=lambda event: event["seq"])
            for event in batch:
                sidecar = {"learning_task": public_task(store, snapshot),
                    "book_name": task["artifacts"].get("book_name", ""),
                    "answer_mode": task.get("answer_mode", "")}
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


def execute_run(store, run_id, owner, registry, adapter, *, on_output=None):
    initial = store.snapshot(run_id)
    checkpoint, task = initial["run"]["checkpoint"], initial["task"]
    baseline = checkpoint.get("policy_baseline") == "texa.runtime-policy/v0"
    try:
        from backend.conversation_memory import append_message
        user_message = append_message(task["conversation_id"], "user", task["artifacts"]["request_question"],
            turn_id=task["turn_id"], request_id=initial["run"]["request_id"],
            book_name=task["artifacts"].get("book_name", ""), subject=task["artifacts"].get("subject", ""))
        try:
            from backend.services.session_ledger import save_resolution_to_ledger
            save_resolution_to_ledger(task["conversation_id"], checkpoint["answer_state"].get("_resolution_trace") or {}, user_message)
        except Exception:
            logger.exception("Runtime resolution ledger projection deferred")
        from backend.services.pending_actions import get_pending_action_store
        from backend.services.agent_runtime.write_service import RuntimeWriteService
        from backend.services.decision.policy import RulePolicyV0
        BoundedAgentRunner(store, registry, adapter, tuple(checkpoint["candidates"]),
            policy_selector=RulePolicyV0 if baseline else None, on_output=on_output).run_bounded(
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
