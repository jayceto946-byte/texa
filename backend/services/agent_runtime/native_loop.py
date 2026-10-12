"""LangChain drives the loop; SQL Runtime owns execution and publication.

No LangChain checkpointer, second run store, autonomous writes or tool handlers.
Only validated wrappers delegate to the existing FixedRunner.
"""
from __future__ import annotations
import hashlib
import json
import time
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage, messages_to_dict, messages_from_dict
from langchain_core.tools import StructuredTool
from langchain_core.callbacks import BaseCallbackHandler
from backend.services.agent_runtime.contracts import FixedAction, RuntimeConflict, RuntimeDenied
from backend.services.agent_runtime.runner import FixedRunner
from backend.services.agent_runtime.multi_step import _bounded_model_call
from backend.services.tool_orchestration import build_tool_context_pack
from graph.generator import prepare_answer_generation, finalize_generated_answer, has_textbook_evidence
from backend.services.answer_verification import verification_notice
from utils.thinking_filter import strip_thinking, ThinkingFilter


def _protocol(messages):
    """Save public text and native IDs/arguments, excluding private provider metadata."""
    clean = []
    for message in messages:
        if isinstance(message, AIMessage):
            message = AIMessage(content=strip_thinking(message.content) if isinstance(message.content, str) else "",
                tool_calls=message.tool_calls, id=message.id)
        clean.append(message)
    return messages_to_dict(clean)


def run_native_loop(runner, model, run_id, owner, *, context, answer_state=None, write_service=None):
    store, registry = runner.store, runner.registry
    refs = {ref["id"]: ref for ref in runner.candidate_tools}
    if not set(refs) <= {"symbolic_math", "verify_math_result"}:
        raise RuntimeDenied("native loop is restricted to mathematics")
    executor = FixedRunner(store, registry, allowlist=frozenset(refs))
    state = dict(answer_state or {"user_input": store.snapshot(run_id)["task"]["goal"],
        "use_textbook_context": False, "answer_mode": "global_general", "intent": "qa"})
    initial = store.snapshot(run_id)
    state["required_outputs"] = initial["task"].get("required_outputs") or []
    pure_math = state.get("support_type") == "explicit_math_only"
    if pure_math and not any(item.get("kind") == "math_support" for item in state["required_outputs"]):
        state["required_outputs"].append({"id": "math_support", "kind": "math_support", "required": True})
    if initial["task"].get("required_inputs") or state.get("missing_inputs") or state.get("required_inputs"):
        return store.close(run_id, owner, outcome="failed", error_code="required_input_missing")
    if state.get("use_textbook_context", True) and not pure_math and not has_textbook_evidence(state) and "search_textbook" not in refs:
        return store.close(run_id, owner, outcome="failed", error_code="answer_evidence_missing")
    messages = messages_from_dict(initial["run"]["checkpoint"].get("native_messages") or [])
    if not messages:
        messages = prepare_answer_generation(state)
    # Restore authoritative receipts first; unresolved calls receive interruption data.
    completed_ids = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    for message in list(messages):
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                if call["id"] not in completed_ids:
                    receipt = next((c for c in reversed(initial["tool_calls"]) if c["tool_id"] == call["name"]
                        and c["operation_key"].endswith("-" + call["id"])), None)
                    if receipt and receipt["result"] and receipt["status"] in {"succeeded", "failed"}:
                        result = {**receipt["result"], "runtime_call_id": receipt["id"], "error_code": receipt["error_code"]}
                    else:
                        result = {"success": False, "message": "上次执行已中断，请重新计算", "error_code": "interrupted"}
                    messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=False),
                        tool_call_id=call["id"], name=call["name"], status="success" if result.get("success") else "error"))
                    completed_ids.add(call["id"])
    store.save_native_messages(run_id, owner, _protocol(messages))
    latest_messages = list(messages)
    tool_failed = any(c["status"] in {"failed", "unknown"} for c in initial["tool_calls"])
    deadline = time.monotonic() + 120.0

    def active():
        snapshot = store.snapshot(run_id)
        if snapshot["run"]["status"] != "running" or snapshot["run"]["owner_token"] != owner:
            raise RuntimeConflict("run stopped")
        if time.monotonic() >= deadline:
            raise RuntimeDenied("run_deadline_exceeded")
        return snapshot

    class RunFenceCallback(BaseCallbackHandler):
        raise_error = True

        def on_llm_new_token(self, token, **kwargs):
            active()  # Abort provider iteration at the next actual chunk after stop.

        def on_chat_model_start(self, serialized, messages, **kwargs):
            active()

    class RuntimeMiddleware(AgentMiddleware):
        def wrap_model_call(self, request, handler):
            nonlocal latest_messages
            active()
            try:
                step = store.start_model_step(run_id, owner)
            except RuntimeConflict as exc:
                active()
                raise RuntimeDenied("model_budget_exhausted") from exc
            settings = {**request.model_settings, "parallel_tool_calls": False, "max_tokens": 4096}
            request = request.override(model=request.model.with_config(callbacks=[RunFenceCallback()]), model_settings=settings)
            response = _bounded_model_call(lambda: handler(request),
                                           min(runner.model_timeout_seconds, max(.001, deadline - time.monotonic())))
            active()
            ai = response.result[-1]
            if not isinstance(ai, AIMessage) or ai.invalid_tool_calls or len(ai.tool_calls) > 1:
                raise RuntimeDenied("invalid_native_response")
            if any(not call.get("id") or len(call["id"]) > 160 or call["name"] not in refs for call in ai.tool_calls):
                raise RuntimeDenied("unauthorized_native_call")
            if any(call["id"] in completed_ids for call in ai.tool_calls):
                raise RuntimeDenied("duplicate_native_call_id")
            latest_messages = [*request.messages, ai]
            store.save_native_messages(run_id, owner, _protocol(latest_messages))
            store.complete_model_step(run_id, owner, action_kind="call" if ai.tool_calls else "finish", transcript=[])
            return response

        def wrap_tool_call(self, request, handler):
            nonlocal latest_messages, tool_failed
            snapshot = active()
            call = request.tool_call
            spec = registry.runtime_tool(call["name"])
            metadata = spec.runtime_metadata()
            ref = refs.get(call["name"], {})
            if metadata["permission"] != "READ" or (metadata["version"], metadata["schema_hash"]) != (ref.get("version"), ref.get("schema_hash")):
                raise RuntimeDenied("tool_step_denied")
            key = f"native-{snapshot['consumed_model_calls']}-{call['id']}"
            try:
                outcome = executor.execute(run_id, owner, FixedAction("call", tool_id=call["name"],
                    args=call["args"], operation_key=key, model_tool_call_id=call["id"]), context=context)
            except RuntimeConflict as exc:
                active()
                raise RuntimeDenied("tool_budget_exhausted") from exc
            except (ValueError, TypeError):
                # Invalid arguments are a failed, budgeted tool receipt, not a model crash.
                args = call["args"]
                outcome = store.request_tool(run_id, owner, tool_id=spec.name, version=metadata["version"],
                    schema_hash=metadata["schema_hash"], args=args,
                    args_hash=hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest(), operation_key=key, model_tool_call_id=call["id"])
                reserved = next(c for c in outcome["tool_calls"] if c["operation_key"] == key)
                store.start_tool(run_id, owner, reserved["id"])
                outcome = store.finish_tool(run_id, owner, reserved["id"],
                    {"success": False, "message": "工具参数不符合输入合同", "error_code": "invalid_arguments"},
                    error_code="input_schema")
            receipt = next(c for c in outcome["tool_calls"] if c["operation_key"] == key)
            result = receipt["result"]
            tool_failed |= receipt["status"] != "succeeded"
            result = {**result, "runtime_call_id": receipt["id"], "error_code": receipt["error_code"]}
            message = ToolMessage(content=json.dumps(result, ensure_ascii=False, allow_nan=False),
                tool_call_id=call["id"], name=spec.name, status="success" if result.get("success") else "error")
            latest_messages.append(message)
            completed_ids.add(call["id"])
            store.save_native_messages(run_id, owner, _protocol(latest_messages))
            return message

    tools = []
    for name in refs:
        spec = registry.runtime_tool(name)
        # Actual invocation is intercepted by middleware, through FixedRunner only.
        def forbidden(**kwargs):
            raise RuntimeDenied("tools must execute through SQL Runtime")
        tools.append(StructuredTool.from_function(forbidden, name=name, description=spec.description,
            args_schema=spec.runtime_input))
    agent = create_agent(model, tools=tools, middleware=[RuntimeMiddleware()])
    filter_ = ThinkingFilter()
    public_chars = 0
    try:
        for mode, payload in agent.stream({"messages": messages},
                config={"recursion_limit": 32}, stream_mode=["messages", "updates"]):
            active()
            if mode == "messages":
                chunk, metadata = payload
                if isinstance(chunk, AIMessage) and isinstance(chunk.content, str):
                    text = filter_.filter(chunk.content)
                    public_chars += len(text)
                    if public_chars > 64000:
                        raise RuntimeDenied("output_budget_exhausted")
                    if text and runner.on_output:
                        runner.on_output(text, False)
            elif mode == "updates":
                # Clear intermediate model text once it chooses a tool.
                for update in payload.values():
                    if isinstance(update, dict):
                        for message in update.get("messages", []):
                            if isinstance(message, AIMessage) and message.tool_calls:
                                filter_ = ThinkingFilter()
                                if runner.on_output:
                                    runner.on_output("", True)
        active()
        snapshot = store.snapshot(run_id)
        last = latest_messages[-1]
        if not isinstance(last, AIMessage) or last.tool_calls or not isinstance(last.content, str):
            raise RuntimeDenied("missing_final_answer")
        if state.get("use_textbook_context", True) and not pure_math and not has_textbook_evidence(state):
            raise RuntimeDenied("answer_evidence_missing")
        outputs = [{"tool": c["tool_id"], "args": c["args"], "result": c["result"] or {}}
                   for c in snapshot["tool_calls"]]
        state["tool_context_pack"] = build_tool_context_pack(outputs)
        answer = finalize_generated_answer(state, strip_thinking(last.content))
        verification = state["answer_verification"]
        if tool_failed:
            if verification["status"] == "passed":
                verification["status"] = "unverified"
            verification["passed"] = False
            verification["unverified"].append({"id": "tool_execution", "reason": "本轮有计算失败，最终结论需核实"})
            notice = verification_notice(verification)
            if notice not in answer:
                answer += "\n\n" + notice
        return store.close(run_id, owner, outcome="completed" if verification["status"] == "passed" else "degraded",
            answer=answer, verification=verification, sources=state.get("evidence_sources") or [])
    except Exception as exc:
        snapshot = store.snapshot(run_id)
        if snapshot["run"]["status"] != "running":
            return snapshot
        code = str(exc) if isinstance(exc, RuntimeDenied) else "native_loop_failed"
        if code not in {"model_budget_exhausted", "tool_budget_exhausted", "invalid_native_response",
                "unauthorized_native_call", "duplicate_native_call_id", "answer_evidence_missing", "tool_step_denied",
                "answer_scope_changed", "missing_final_answer", "run_deadline_exceeded", "output_budget_exhausted"}:
            code = "native_loop_failed"
        return store.close(run_id, owner, outcome="failed", error_code=code)
