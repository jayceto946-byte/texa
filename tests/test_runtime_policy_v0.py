import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.services.decision.policy_contracts import (
    PolicyObservationV0, PolicyDecisionV0, PolicyActionV0, PreviousResultV0,
    PolicyOutcomeV0, PolicyValidationV0, parse_decision,
)
from backend.services.decision.policy import (
    RulePolicyV0, PolicyValidator, PolicyRejected, select_decision,
)
from backend.services.decision.policy_projection import project_observation, runtime_identity, matched_tool_refs
from backend.services.agent_runtime.multi_step import BoundedAgentRunner
from backend.services.agent_runtime.contracts import RuntimeConflict
from evaluation.runtime_policy_v0 import fixture_runtime, run_baseline


def fixture(**changes):
    return {"id": "test", "request": "查询习题库和最近学习进度", "book_name": "fixture",
            "grounded": False, **changes}


def setup(tmp_path, **changes):
    return fixture_runtime(tmp_path, fixture(**changes))


def project(parts, **changes):
    store, registry, state, refs, context = parts
    snapshot = store.task_snapshot("rtask_fixture")
    return project_observation(request=state["user_input"], resolved_query=state["user_input"],
        registry=registry, context=context, identity=runtime_identity(snapshot), snapshot=snapshot,
        answer_state=state, candidate_tools=refs, **changes)


@pytest.mark.parametrize("raw", [
    '{"action_id":"a0","action_id":"a1"}', '{"action_id":"a0","args":{}}',
    '{"action_id":"a0","reason":"because"}', '{"action_id":"a0","confidence":1}',
    '{"action_id":1}', '{"action_id":true}', '{"action_id":null}', '{}', '[]',
    'prefix {"action_id":"a0"}', '{"action_id":"a0"} trailing',
    '```json\n{"action_id":"a0"}\n```', '{"action_id":"a0","answer":"text"}',
])
def test_decision_parser_is_strict(raw):
    with pytest.raises((ValueError, TypeError)):
        parse_decision(raw)


def test_contract_roundtrip_and_duplicate_candidates(tmp_path):
    frozen = project(setup(tmp_path))
    envelope = frozen.envelope
    assert envelope.canonical_json() == type(envelope).model_validate_json(envelope.canonical_json()).canonical_json()
    assert PolicyDecisionV0(action_id="a0").canonical_json() == '{"action_id":"a0"}'
    with pytest.raises(ValidationError):
        PolicyObservationV0.model_validate({**envelope.payload.model_dump(),
            "admissible_actions": [envelope.payload.admissible_actions[0]] * 2})
    for model, payload in ((PolicyActionV0, {"id": "a", "kind": "generate_answer", "args": {"tool_id": "x"}}),
        (PreviousResultV0, {"action_kind": "call_tool", "status": "succeeded", "summary": ""}),
        (PreviousResultV0, {"action_kind": "generate_answer", "tool_id": "x", "status": "succeeded", "summary": ""})):
        with pytest.raises(ValidationError):
            model.model_validate(payload)
    outcome = PolicyOutcomeV0(decision_ref="d", validation=PolicyValidationV0(status="rejected", code="invalid_format"),
        execution="not_started", continuation="next_observation", task_status="running")
    assert outcome == PolicyOutcomeV0.model_validate_json(outcome.canonical_json())
    with pytest.raises(ValidationError):
        PolicyOutcomeV0.model_validate({**outcome.model_dump(), "execution": "succeeded"})
    with pytest.raises(ValidationError):
        PolicyOutcomeV0.model_validate({**outcome.model_dump(), "decision_correct": True})


def test_deep_detachment_and_true_multicandidate_projection(tmp_path):
    parts = setup(tmp_path)
    frozen = project(parts)
    assert len(frozen.envelope.payload.admissible_actions) == 3
    assert project(parts) == frozen
    original = copy.deepcopy(frozen.bindings)
    def selector(observation):
        observation.admissible_actions[0].args.input["book_name"] = "injected"
        observation.context.constraints["subject"] = "injected"
        observation.admissible_actions.clear()
        return '{"action_id":"a0"}'
    binding, attempt, _ = select_decision(frozen, selector=selector, current=lambda: frozen, record=lambda _: None)
    assert binding == original["a0"]
    binding["args"]["input"]["book_name"] = "another injection"
    assert frozen.bindings == original
    assert attempt.validation.status == "accepted"
    decisions = [RulePolicyV0(frozen.envelope.payload) for _ in range(5)]
    assert all(item == decisions[0] for item in decisions)
    assert frozen.bindings[decisions[0].action_id]["args"]["tool_id"] == "search_exercises"


def test_empty_selector_and_singleton_forced(tmp_path):
    parts = setup(tmp_path, request="说明学习方法", book_name="")
    frozen = project(parts)
    called = []
    binding, attempt, _ = select_decision(frozen, selector=lambda _: called.append(True),
        current=lambda: frozen, record=lambda _: None)
    assert binding["kind"] == "generate_answer" and attempt.source == "forced" and called == []
    empty = frozen.envelope.payload.model_copy(update={"admissible_actions": []})
    with pytest.raises(ValueError, match="empty candidate"):
        RulePolicyV0(empty)


def test_blocking_inputs_only_gate_and_approval_is_not_input(tmp_path, monkeypatch):
    parts = setup(tmp_path)
    missing = [{"type": "image", "name": "附表", "blocking": True, "status": "missing"}]
    gate = project(parts, missing_inputs=missing, gate=True)
    assert [a.kind for a in gate.envelope.payload.admissible_actions] == ["request_input"]
    sql = project(parts, missing_inputs=missing)
    assert sql.envelope.payload.admissible_actions == []
    assert sql.exclusions == [{"reason": "sql_input_gate_unsupported"}]
    from backend.services.learning_task import LearningTaskStore
    from backend.api.chat import _finish_chat_learning_task
    # Integration at the existing checkpoint; no SQL row/run is invented.
    store = LearningTaskStore(tmp_path / "legacy")
    task = store.create(task_type="qa", goal="用户澄清", conversation_id="conv", turn_id="turn")
    monkeypatch.setenv("TEXA_RUNTIME_POLICY_V0", "1")
    monkeypatch.setattr("backend.api.chat.get_learning_task_store", lambda: store)
    task = _finish_chat_learning_task(task, {}, waiting_reason="需要附表", policy_request_id="req_gate")
    assert task.status == "waiting_for_input"
    assert task.artifacts["policy_gate"]["source"] == "forced"
    assert task.artifacts["policy_gate"]["outcome"]["continuation"] == "waiting"
    snap = parts[0].task_snapshot("rtask_fixture")
    snap["task"]["status"] = "waiting_for_confirmation"
    approval = project_observation(request="x", resolved_query="x", registry=parts[1], context=parts[4],
        identity=runtime_identity(snap), snapshot=snap, answer_state=parts[2], candidate_tools=parts[3])
    assert approval.envelope.payload.admissible_actions == []


def test_admission_excludes_duplicate_write_unknown_version_and_unbound(tmp_path):
    parts = setup(tmp_path)
    store, registry, state, refs, context = parts
    snap = store.task_snapshot("rtask_fixture")
    repeated = project_observation(request=state["user_input"], resolved_query=state["user_input"], registry=registry,
        context=context, identity=runtime_identity(snap), snapshot=snap, answer_state=state, candidate_tools=refs+refs)
    assert len(repeated.envelope.payload.admissible_actions) == 3
    assert any(item["reason"] == "duplicate_or_retry" for item in repeated.exclusions)
    registry.get("search_exercises").permission = "LOCAL_WRITE"
    registry.get("get_recent_progress").version = "changed"
    frozen = project(parts)
    assert [a.kind for a in frozen.envelope.payload.admissible_actions] == ["generate_answer"]
    assert {e["reason"] for e in frozen.exclusions} == {"permission_or_source", "version_or_schema_changed"}
    with pytest.raises(PolicyRejected, match="stale_observation"):
        PolicyValidator.validate(repeated, '{"action_id":"a0"}', frozen)
    absent = {"id": "absent", "version": "1", "schema_hash": "not_present"}
    unbound = project_observation(request="x", resolved_query="x", registry=registry,
        context=context, identity={"request_id": "req", "position": "gate"}, candidate_tools=(absent,))
    assert unbound.exclusions[0]["tool_id"] == "absent"
    registry.get("search_exercises").permission = "READ"
    context.book_name = ""
    frozen = project(parts)
    assert any(e["reason"] == "parameters_not_bindable" for e in frozen.exclusions)


@pytest.mark.parametrize("field,value", [("source", "plugin"), ("read_only", False), ("side_effect", "write")])
def test_permission_and_source_leaks_excluded(tmp_path, field, value):
    parts = setup(tmp_path)
    setattr(parts[1].get("search_exercises"), field, value)
    assert not any(a.kind == "call_tool" and a.args.tool_id == "search_exercises"
                   for a in project(parts).envelope.payload.admissible_actions)


def test_illegal_id_single_fallback_preserves_primary(tmp_path):
    parts = setup(tmp_path, request="最近学习进度如何", book_name="")
    store, registry, state, refs, context = parts
    captures, calls = [], []
    def invalid(obs):
        calls.append(obs)
        return '{"action_id":"forged"}'
    result = BoundedAgentRunner(store, registry, None, refs, policy_selector=invalid,
        policy_source="model_stub", policy_capture=lambda *args: captures.append(args)).run_bounded(
            store.task_snapshot("rtask_fixture")["run"]["id"], "owner", context=context,
            answer_state=state, answer_generator=lambda _: "查询覆盖有限记录。")
    assert result["task"]["status"] == "completed"
    assert len(calls) == 1 and len(captures) == 3
    rejected, fallback, forced = [item[1] for item in captures]
    assert rejected.source == "model_stub" and rejected.validation.code == "unknown_action_id"
    assert captures[0][2].execution == "not_started"
    assert fallback.fallback_of == rejected.decision_ref and fallback.source == "rules"
    assert captures[1][2].execution == "succeeded" and forced.source == "forced"
    assert result["consumed_model_calls"] == 1  # Actual shared answer stub only.
    events = result["execution_events"]
    persisted = [e["payload"]["policy_outcome"] for e in events if "policy_outcome" in e["payload"]]
    assert len(persisted) == 3
    assert persisted[0]["validation"]["status"] == "rejected"
    assert all(o["user_feedback"] == o["goal_completion"] == "unknown" for o in persisted)
    assert all("admissible_actions" not in str(e["payload"]) for e in events)


def test_stop_stale_no_fallback_or_old_trace_and_resume(tmp_path):
    parts = setup(tmp_path, request="最近学习进度如何", book_name="")
    store, registry, state, refs, context = parts
    run = store.task_snapshot("rtask_fixture")["run"]["id"]
    def stop(obs):
        store.close(run, "owner", outcome="paused", error_code="interrupted")
        return '{"action_id":"forged"}'
    runner = BoundedAgentRunner(store, registry, None, refs, policy_selector=stop, policy_source="model_stub")
    with pytest.raises(RuntimeConflict, match="stale"):
        runner.run_bounded(run, "owner", context=context, answer_state=state, answer_generator=lambda _: "说明")
    snap = store.snapshot(run)
    assert snap["consumed_calls"] == snap["consumed_model_calls"] == 0
    assert not any("policy_decision" in event["payload"] for event in snap["execution_events"])
    resumed = store.resume("rtask_fixture", expected_revision=snap["task_revision"], request_key="resume",
        request_id="req_resume", owner_token="new_owner", turn_id="turn")
    assert resumed["run"]["checkpoint"]["policy_baseline"] == "texa.runtime-policy/v0"
    runner.policy_selector = RulePolicyV0
    result = runner.run_bounded(resumed["run"]["id"], "new_owner", context=context,
        answer_state=state, answer_generator=lambda _: "查询覆盖有限记录。")
    assert result["task"]["status"] == "completed" and result["consumed_calls"] == 1


def test_scope_and_index_change_before_selection_cannot_execute(tmp_path):
    parts = setup(tmp_path, request="教材定义", grounded=True)
    store, registry, state, refs, context = parts
    before = project(parts)
    assert [a.kind for a in before.envelope.payload.admissible_actions] == ["call_tool"]
    registry.get("search_textbook").runtime_scope_check = lambda *args: (_ for _ in ()).throw(ValueError("index changed"))
    after = project(parts)
    assert after.envelope.payload.admissible_actions == []
    with pytest.raises(PolicyRejected, match="stale"):
        PolicyValidator.validate(before, '{"action_id":"a0"}', after)
    assert store.task_snapshot("rtask_fixture")["consumed_calls"] == 0


def test_same_decision_cannot_be_reserved_twice(tmp_path):
    parts = setup(tmp_path)
    store = parts[0]
    frozen = project(parts)
    snapshot = store.task_snapshot("rtask_fixture")
    def record(attempt):
        store.record_policy_attempt(snapshot["run"]["id"], "owner", attempt.metadata(),
            expected_task_revision=snapshot["task_revision"], expected_run_revision=snapshot["run"]["revision"])
    select_decision(frozen, current=lambda: project(parts), record=record)
    with pytest.raises(RuntimeConflict, match="already submitted"):
        select_decision(frozen, current=lambda: project(parts), record=record)
    assert store.task_snapshot("rtask_fixture")["consumed_calls"] == 0


def test_fallback_is_bounded_even_when_rules_fail(tmp_path, monkeypatch):
    import backend.services.decision.policy as policy
    frozen = project(setup(tmp_path))
    attempts = []
    monkeypatch.setattr(policy, "RulePolicyV0", lambda _: '{"action_id":"forged"}')
    with pytest.raises(PolicyRejected, match="fallback_rejected"):
        select_decision(frozen, selector=lambda _: '{"action_id":"forged"}', current=lambda: frozen,
                        record=attempts.append)
    assert len(attempts) == 2 and attempts[1].fallback_of == attempts[0].decision_ref


def test_finite_offline_baseline():
    report = run_baseline()
    assert all(item["passed"] for item in report["fixtures"])
    assert report["metrics"]["overhead"]["real_model_calls"] == 0
    assert report["metrics"]["candidate_generation"]["forbidden_leaks"] == 0
    assert report["metrics"]["candidate_generation"]["binding_errors"] == 0
    assert report["metrics"]["fallback"]["primary_rejections"] == 1
    assert report["metrics"]["fallback"]["execution_succeeded"] == 1


@pytest.mark.parametrize("degraded", [False, True])
def test_answer_verification_and_execution_are_distinct(tmp_path, degraded):
    parts = setup(tmp_path, request="计算2+2" if degraded else "说明学习方法", book_name="")
    store, registry, state, refs, context = parts
    captured = []
    # Unsupported arithmetic tools stay on the existing control path; the
    # deterministic publication verifier must not accept an unsupported number.
    result = BoundedAgentRunner(store, registry, None, refs, policy_selector=RulePolicyV0,
        policy_capture=lambda *args: captured.append(args)).run_bounded(
            store.task_snapshot("rtask_fixture")["run"]["id"], "owner", context=context,
            answer_state=state, answer_generator=lambda _: "结果为4。" if degraded else "学习需要复习。")
    assert result["task"]["status"] == ("degraded" if degraded else "completed")
    assert captured[-1][2].execution == "succeeded"
    assert captured[-1][2].goal_completion == "unknown"
    assert (result["task"]["verification"]["status"] == "passed") is not degraded


def test_no_candidates_never_calls_policy(tmp_path):
    parts = setup(tmp_path, request="教材定义", grounded=True)
    store, registry, state, refs, context = parts
    registry.get("search_textbook").permission = "LOCAL_WRITE"
    seen, called = [], []
    result = BoundedAgentRunner(store, registry, None, refs, policy_selector=lambda _: called.append(True),
        policy_observe=seen.append).run_bounded(store.task_snapshot("rtask_fixture")["run"]["id"], "owner",
        context=context, answer_state=state, answer_generator=lambda _: "never")
    assert result["task"]["status"] == "failed" and called == []
    assert len(seen) == 1 and seen[0].envelope.payload.admissible_actions == []
    assert result["consumed_calls"] == result["consumed_model_calls"] == 0


def test_answer_budget_is_not_spent_by_rules(tmp_path):
    parts = setup(tmp_path, request="最近学习进度如何", book_name="")
    store, registry, state, refs, context = parts
    run = store.task_snapshot("rtask_fixture")["run"]["id"]
    store.start_model_step(run, "owner")
    store.start_model_step(run, "owner")
    result = BoundedAgentRunner(store, registry, None, refs, policy_selector=RulePolicyV0).run_bounded(run, "owner",
        context=context, answer_state=state, answer_generator=lambda _: (_ for _ in ()).throw(AssertionError("budget")))
    assert result["consumed_model_calls"] == 2 and result["consumed_calls"] == 1
    assert result["task"]["status"] == "failed"


@pytest.mark.parametrize("kind", ["tool", "answer"])
def test_atomic_execution_revision_fence(tmp_path, kind):
    from backend.services.agent_runtime.runner import FixedRunner
    from backend.services.agent_runtime.contracts import FixedAction
    parts = setup(tmp_path)
    store, registry, state, refs, context = parts
    snapshot = store.task_snapshot("rtask_fixture")
    run = snapshot["run"]["id"]
    revisions = (snapshot["task_revision"], snapshot["run"]["revision"])
    store.start_model_step(run, "owner")
    with pytest.raises(RuntimeConflict, match="snapshot changed"):
        if kind == "tool":
            FixedRunner(store, registry).execute(run, "owner", FixedAction("call", tool_id="get_recent_progress", args={},
                operation_key="revision-test"), context=context, expected_revisions=revisions)
        else:
            store.start_model_step(run, "owner", expected_revisions=revisions)
    assert store.snapshot(run)["consumed_calls"] == 0
    assert store.snapshot(run)["consumed_model_calls"] == 1


def test_prior_failed_tool_is_not_retried_after_recovery(tmp_path):
    from backend.services.agent_runtime.runner import FixedRunner
    from backend.services.agent_runtime.contracts import FixedAction
    parts = setup(tmp_path, request="最近学习进度如何", book_name="", failed=True)
    store, registry, state, refs, context = parts
    run = store.task_snapshot("rtask_fixture")["run"]["id"]
    FixedRunner(store, registry).execute(run, "owner", FixedAction("call", tool_id="get_recent_progress", args={},
        operation_key="prior-read"), context=context)
    store.close(run, "owner", outcome="paused")
    recovered = type(store)(store.db_path)
    stopped = recovered.snapshot(run)
    resumed = recovered.resume("rtask_fixture", expected_revision=stopped["task_revision"], request_key="again",
        request_id="req_again", owner_token="again_owner", turn_id="turn")
    result = BoundedAgentRunner(recovered, registry, None, refs, policy_selector=RulePolicyV0).run_bounded(
        resumed["run"]["id"], "again_owner", context=context, answer_state=state, answer_generator=lambda _: "查询未成功。")
    assert result["task"]["status"] == "completed" and result["consumed_calls"] == 1
    assert result["tool_calls"][0]["attempt_count"] == 1


@pytest.mark.parametrize("change", ["version", "scope"])
def test_changed_environment_stops_before_execution_without_fallback(tmp_path, change):
    parts = setup(tmp_path, request="最近学习进度如何", book_name="")
    store, registry, state, refs, context = parts
    run = store.task_snapshot("rtask_fixture")["run"]["id"]
    def stale_selector(observation):
        if change == "version":
            registry.get("get_recent_progress").version = "new"
        else:
            context.subject = "changed"
        return '{"action_id":"a0"}'
    with pytest.raises(RuntimeConflict, match="stale"):
        BoundedAgentRunner(store, registry, None, refs, policy_selector=stale_selector).run_bounded(
            run, "owner", context=context, answer_state=state, answer_generator=lambda _: "never")
    snapshot = store.snapshot(run)
    assert snapshot["consumed_calls"] == snapshot["consumed_model_calls"] == 0
    assert not any("policy_decision" in event["payload"] for event in snapshot["execution_events"])


def test_textbook_index_change_during_answer_prevents_publication(tmp_path):
    parts = setup(tmp_path, request="教材中的连续定义", grounded=True)
    store, registry, state, refs, context = parts
    def answer(_):
        registry.get("search_textbook").runtime_scope_check = lambda *args: (_ for _ in ()).throw(ValueError("index changed"))
        return "函数在一点连续，意味着函数值等于该点的极限。[[cite:E1]]"
    result = BoundedAgentRunner(store, registry, None, refs, policy_selector=RulePolicyV0).run_bounded(
        store.task_snapshot("rtask_fixture")["run"]["id"], "owner", context=context,
        answer_state=state, answer_generator=answer)
    assert result["task"]["status"] == "failed" and result["run"]["output"] is None
    assert result["run"]["error_code"] == "answer_scope_changed"
    assert result["execution_events"][-1]["payload"]["policy_outcome"]["execution"] == "failed"
    assert store.pending_outbox() == []
