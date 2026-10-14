"""Audit reproductions: temporary stores, fake models, no user data or API calls.

Run from repository root using venv310/bin/python. A True result means the
reported defect was reproduced, not that desired behavior passed a test.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path.cwd()))
root = Path(tempfile.mkdtemp(prefix="texa-policy-probes-"))
os.environ["ENV_PATH"] = "/dev/null"
os.environ["DATA_DIR"] = str(root / "data")
os.environ["PROGRESS_PATH"] = str(root / "data/progress")
from backend.services import runtime_events as audit
from backend.services.agent_runtime import chat_binding, locator
from backend.services.agent_runtime.contracts import RunCommand, ModelCapabilities
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.goals import execution
from backend.services.goals.service import GoalService
from backend.services.goals.store import GoalStore
from backend.services.answer_verification import verify_answer, derive_required_outputs
from backend.tools.registry import ToolRegistry

results = {}

def record(name, defect, **details):
    results[name] = {"reproduced": bool(defect), **details}

class Adapter:
    def capabilities(self):
        return ModelCapabilities(tool_calling="supported")

from backend.services.decision.router import DecisionRouter
from backend.services.decision.contracts import DecisionContext
shadow = DecisionRouter(shadow=True).route(DecisionContext("req", "最近学习进度", "最近学习进度", "global_general"))
record("shadow_rule_is_labeled_nonshadow", shadow.shadow_only is False, selected=shadow.selected_capability, shadow_only=shadow.shadow_only)

def goal_setup(directory):
    service = GoalService(GoalStore(directory / "goals.db"))
    runtime = RuntimeStore(directory / "runtime.db")
    goal = service.create(learner_id="local_default", title="audit", objective="旧目标：查看学习进度",
                          success_criteria=[{"id": "c1", "description": "提供进度证据"}])
    return service, runtime, goal

def create_goal_run(service, goal):
    return execution.start_goal(service, goal["id"], expected_revision=1, request_key="first")

with patch.object(audit, "observe_execution_event", lambda event: None):
    required = derive_required_outputs("计算 2 + 2")
    verification = verify_answer("计算结果为 999。", required_outputs=required,
        tool_context_pack={"outputs": [{"tool": "verify_math_result", "verification": {"passed": True}}]})
    record("unrelated_math_verifies_wrong_answer", verification["status"] == "passed", verification=verification)
    verification = verify_answer("已知 2，计算结果为 999。", required_outputs=required,
                                  evidence_items=[{"text": "输入为 2。"}])
    record("input_number_verifies_wrong_conclusion", verification["status"] == "passed", verification=verification)
    verification = verify_answer("", required_outputs=[])
    record("empty_contract_empty_answer_passes", verification["status"] == "passed", verification=verification)

    service, runtime, goal = goal_setup(root / "goals")
    registry = ToolRegistry()
    with patch.object(execution, "runtime_store", lambda **kw: runtime), \
         patch.object(locator, "runtime_store", lambda **kw: runtime), \
         patch.object(execution, "prepare_registry", lambda goal: (registry, (), None)), \
         patch.object(execution, "build_adapter", lambda registry: Adapter()), \
         patch.object(execution, "launch_worker", lambda *args: None):
        task = create_goal_run(service, goal)
        initial = runtime.task_snapshot(task["id"])
        record("goal_criteria_not_in_required_outputs", not initial["task"]["required_outputs"],
               goal_criteria=goal["success_criteria"], required_outputs=initial["task"]["required_outputs"])
        updated = service.update(goal["id"], expected_revision=2, changes={"objective": "新目标：学习完全不同内容"})
        resumed = execution.resume_goal(service, goal["id"], task_id=task["id"], expected_revision=3, request_key="resume-new")
        frozen = runtime.task_snapshot(task["id"])
        record("changed_goal_resumes_old_contract", frozen["task"]["goal"].startswith("旧目标"),
               current_objective=updated["objective"], executed_goal=frozen["task"]["goal"])
        service.pause(goal["id"], expected_revision=3)
        from backend.api import chat
        with patch.object(chat_binding, "stream_run", lambda *args, **kw: {"dispatched": True}):
            response = chat.resume_chat_task_stream(task["id"])
        record("chat_resume_bypasses_paused_goal", response["dispatched"] and runtime.task_snapshot(task["id"])["task"]["status"] == "running",
               goal_status=service.store.get(goal["id"])["status"])
        service.activate(goal["id"], expected_revision=4)
        service.measure(goal["id"], expected_revision=5, evidence_by_criterion={}, user_confirms_completion=True)
        record("completed_goal_leaves_run_running", runtime.task_snapshot(task["id"])["task"]["status"] == "running",
               goal_status=service.store.get(goal["id"])["status"])

    service, runtime, goal = goal_setup(root / "crash")
    with patch.object(execution, "runtime_store", lambda **kw: runtime), \
         patch.object(execution, "prepare_registry", lambda goal: (registry, (), None)), \
         patch.object(execution, "build_adapter", lambda registry: Adapter()), \
         patch.object(execution, "launch_worker", lambda *args: None):
        with patch.object(service.store, "link", side_effect=OSError("injected link failure")):
            try:
                create_goal_run(service, goal)
            except OSError:
                pass
        retry = execution.start_goal(service, goal["id"], expected_revision=2, request_key="first")
        record("goal_link_failure_orphans_retry", not service.store.links(goal["id"]),
               task_status=retry["status"], links=service.store.links(goal["id"]))

    runtime = RuntimeStore(root / "sse.db")
    snap = runtime.create(RunCommand("sse", "req", "rtask_sse", "session", "turn", "question", "owner"))
    run_id = snap["run"]["id"]
    runtime.configure_chat(run_id, "owner", state={}, candidates=(), request_question="question", book_name="", subject="")
    original_events = runtime.events
    def events_with_commit(*args, **kwargs):
        if runtime.snapshot(run_id)["run"]["status"] == "running":
            runtime.close(run_id, "owner", outcome="completed", answer="answer")
        return original_events(*args, **kwargs)
    async def collect(response):
        collected = []
        try:
            async for event in response.body_iterator:
                collected.append(event)
        except Exception as exc:
            return type(exc).__name__, str(exc), collected
        return "", "", collected
    with patch.object(runtime, "events", events_with_commit), patch.object(chat_binding.threading, "Thread"):
        response = chat_binding.stream_run(runtime, run_id, "owner", registry=registry, adapter=Adapter())
        kind, message, streamed = asyncio.run(collect(response))
    record("sse_snapshot_final_commit_race", kind == "TypeError", error=message,
           durable_status=runtime.snapshot(run_id)["task"]["status"], emitted_count=len(streamed))

    from backend.services.agent_runtime.outbox import RuntimeOutboxProjector
    runtime = RuntimeStore(root / "outbox.db")
    for n in range(2):
        snap = runtime.create(RunCommand(f"key{n}", f"req{n}", f"task{n}", f"session{n}", f"turn{n}", "q", "owner"))
        runtime.close(snap["run"]["id"], "owner", outcome="completed", answer="answer")
    seen = []
    def append(conversation_id, *args, **kwargs):
        seen.append(conversation_id)
        if conversation_id == "session0":
            raise OSError("poisoned first projection")
        return {"id": kwargs["message_id"]}
    projector = RuntimeOutboxProjector(runtime, append)
    for _ in range(2):
        try:
            projector.drain_once()
        except OSError:
            pass
    record("outbox_failure_starves_other_sessions", "session1" not in seen, seen=seen, pending=len(runtime.pending_outbox()))

event_store = audit.RuntimeEventStore(root / "events.db")
from memory.learning_events import LearningEventStore
from backend.services.learning_state import LearningStateService
memory_root = root / "memory"
learning_events = LearningEventStore(memory_root / "learning_events.db")
goal_service = GoalService(GoalStore(memory_root / "goals.db"), learning_events)
for goal_id in ("goal_A", "goal_B"):
    item = goal_service.create(learner_id="local_default", goal_id=goal_id, title=goal_id,
                              objective="learn", scope={"book_name": "audit-book"})
    goal_service.activate(goal_id, expected_revision=1)
with patch.object(locator, "runtime_store", lambda **kw: None):
    goal_service.pause("goal_A", expected_revision=2)
state = LearningStateService(progress_root=memory_root, event_store=learning_events).get_state(book_name="audit-book")
record("pausing_goal_A_marks_goal_B_paused", state["active_goal"].get("goal_id") == "goal_B" and state["active_goal"].get("status") == "paused",
       projection=state["active_goal"], sql_goal_B_status=goal_service.store.get("goal_B")["status"])

from backend.services.learning_state_bridge import bridge_learning_request
bridge_root = root / "bridge"
bridge_events = LearningEventStore(bridge_root / "learning_events.db")
bridge_service = LearningStateService(progress_root=bridge_root, event_store=bridge_events)
for _ in range(2):
    bridge_learning_request("我想学完第一章", "set_learning_goal", book_name="audit-book",
                            subject="", conversation_id="same-session", service=bridge_service)
created = GoalStore(bridge_root / "goals.db").list(learner_id="local_default")
record("preflight_goal_write_has_no_operation_identity", len(created) == 2,
       goal_count=len(created), statuses=[item["status"] for item in created])

events = [
    audit.make_event("state", session_id="origin:goal:g", run_id="run1"),
    audit.make_event("execution_result", session_id="origin:goal:g", run_id="run1"),
    audit.make_event("state", session_id="origin:goal:g", run_id="run2", payload={"task_status": "running"}),
    audit.make_event("state", session_id="other", turn_id="active"),
]
with patch.object(audit, "_MAX_ROWS", 3):
    event_store.append_many(events)
remaining = event_store.list(session_id="origin:goal:g")
record("rotation_deletes_active_goal_run", not remaining, retained_goal_events=len(remaining))

event_store = audit.RuntimeEventStore(root / "lost.db")
with patch.object(event_store, "append_many", side_effect=OSError("injected disk failure")):
    writer = audit.RuntimeEventWriter(event_store)
    writer.submit(audit.make_event("execution_result", session_id="s", turn_id="t"))
    writer.flush()
    writer.stop()
record("failed_audit_flush_reports_no_failure", not event_store.list(session_id="s"))

print(json.dumps(results, ensure_ascii=False, indent=2))
assert all(item["reproduced"] for item in results.values()), "A reproduction no longer matches; inspect before using the report"
