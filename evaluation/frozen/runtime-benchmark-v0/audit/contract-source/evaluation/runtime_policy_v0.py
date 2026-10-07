"""Small human-authored baseline harness. Temporary stores, zero real models.

Run: venv310/bin/python -m evaluation.runtime_policy_v0 --output <artifact.json>
This artifact captures test trajectories; it is neither execution authority nor
an answer-quality evaluation or production data collection pipeline.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from time import perf_counter

from backend.services.agent_runtime.contracts import RunCommand
from backend.services.agent_runtime.multi_step import BoundedAgentRunner
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.agent_runtime.progress_tool import register_recent_progress_runtime
from backend.services.agent_runtime.exercise_tool import register_search_exercises_runtime
from backend.services.agent_runtime.textbook_tool import register_textbook_search_runtime
from backend.services.decision.policy import RulePolicyV0
from backend.services.decision.policy_projection import matched_tool_refs, project_observation, runtime_identity
from backend.tools.registry import ToolRegistry, ToolContext, ToolResult
from memory.learning_events import LearningEventStore

FIXTURES = Path(__file__).parent / "fixtures" / "runtime_policy_v0.json"


def action_key(action):
    return "tool:" + action.args.tool_id if action.kind == "call_tool" else action.kind


def fixture_runtime(root, fixture):
    """Real Runtime / canonical schemas with deterministic fixture-only handlers."""
    registry = ToolRegistry()
    register_recent_progress_runtime(registry, LearningEventStore(root / "learning.db"))
    register_search_exercises_runtime(registry, None)
    registry.get("get_recent_progress").handler = lambda context, args: ToolResult(
        not fixture.get("failed"), message="fixture failure" if fixture.get("failed") else "fixture",
        data={"book_name": args["book_name"], "subject": args["subject"], "range_days": args["days"],
            "summary": {}, "top_concepts": [], "recent_events": [], "queried_event_limit": 200,
            "window_complete": False, "coverage_note": "fixture bounded coverage"})
    registry.get("search_exercises").handler = lambda context, args: ToolResult(True,
        data={"book_name": args["book_name"], "query": args["query"], "filters": {},
            "exercises": [] if fixture.get("empty") else [{"id": "exercise_fixture", "question": "说明连续的定义"}],
            "solution_fields_omitted": True, "searched_record_limit": 2000, "results_may_be_incomplete": True})
    scope = {"id": "fixture_scope", "book_name": "fixture", "subject": "数学",
             "resources": [{"book_name": "fixture", "is_primary": True, "is_selected": True}],
             "index_versions": {"fixture": "fixture_v1"}, "scope_policy": "ui-resource-group/v1"}
    register_textbook_search_runtime(registry, scope, versions=lambda _: "fixture_v1",
        retrieve=lambda *a, **kw: {"evidence_items": [] if fixture.get("empty") else [
            {"book_name": "fixture", "chunk_id": "definition_fixture", "text": "函数在一点连续，意味着函数值等于该点的极限。", "source": "fixture", "chapter": "连续"}],
            "evidence_support": {"status": "insufficient" if fixture.get("empty") else "sufficient"},
            "retrieval_status": "ok"})
    from graph.main_graph import build_initial_state
    state = build_initial_state(fixture["request"], book_name=fixture["book_name"], subject="数学",
        use_textbook_context=fixture["grounded"], answer_mode="textbook_grounded" if fixture["grounded"] else "global_general")
    state["intent"] = "qa"
    if fixture["grounded"]:
        state["_runtime_textbook_scope"] = scope
    refs, exclusions = matched_tool_refs(fixture["request"], registry, grounded=fixture["grounded"])
    from backend.services.answer_verification import derive_required_outputs
    store = RuntimeStore(root / "runtime.db")
    snapshot = store.create(RunCommand("key", "req", "rtask_fixture", "conv", "turn", fixture["request"],
        "owner", budget_calls=3, budget_model_calls=2,
        required_outputs=derive_required_outputs(fixture["request"], intent="qa", answer_mode=state["answer_mode"])))
    store.configure_chat(snapshot["run"]["id"], "owner", state=state, candidates=refs,
        request_question=fixture["request"], book_name=fixture["book_name"], subject="数学", policy_baseline=True)
    return store, registry, state, refs, ToolContext(book_name=fixture["book_name"], subject="数学", conversation_id="conv")


def run_baseline():
    fixtures = json.loads(FIXTURES.read_text())
    trajectories = []
    metrics = {"candidate_generation": {"observations": 0, "gold_covered": 0, "forbidden_leaks": 0,
                "binding_checks": 0, "binding_errors": 0, "exclusion_reasons": {}},
        "selection": {"eligible": 0, "correct": 0, "forced": 0, "forced_correct": 0, "candidate_failures": 0},
        "decision_validity": {"invalid_format": 0, "unknown_action_id": 0, "stale_or_environment_changed": 0},
        "fallback": {"primary_rejections": 0, "attempts": 0, "accepted": 0, "execution_succeeded": 0},
        "task_execution": {"fixtures": len(fixtures) + 2, "passed": 0},
        "overhead": {"policy_calls": 0, "primary_policy_calls": 0, "fallback_policy_calls": 0, "rule_ms": 0.0, "tool_calls": 0, "answer_stub_calls": 0, "real_model_calls": 0}}
    for fixture in fixtures:
        captured, selected, observations, calls, elapsed, stub_calls = [], [], [], 0, 0.0, 0
        def selector(observation):
            nonlocal calls, elapsed
            calls += 1
            if fixture.get("invalid") and calls == 1:
                return '{"action_id":"forged","reason":"not allowed"}'
            start = perf_counter()
            result = RulePolicyV0(observation)
            elapsed += (perf_counter() - start) * 1000
            return result
        def answer(_):
            nonlocal stub_calls
            stub_calls += 1
            return "函数在一点连续，意味着函数值等于该点的极限。[[cite:E1]]" if fixture["grounded"] else "本次查询覆盖有限记录，结果仅用于当前学习参考。"
        def capture(frozen, attempt, outcome):
            captured.append({"observation": frozen.envelope.model_dump(exclude_none=True),
                "decision": attempt.decision.model_dump() if attempt.decision else None, "decision_output": attempt.raw_output,
                "trace": attempt.metadata(), "outcome": outcome.model_dump(), "exclusions": frozen.exclusions})
        with tempfile.TemporaryDirectory(prefix="texa-policy-v0-") as temp:
            store, registry, state, refs, context = fixture_runtime(Path(temp), fixture)
            run = store.task_snapshot("rtask_fixture")["run"]["id"]
            runner = BoundedAgentRunner(store, registry, None, refs, policy_selector=selector,
                policy_source="model_stub" if fixture.get("invalid") else "rules", policy_capture=capture, policy_observe=observations.append)
            result = runner.run_bounded(run, "owner", context=context, answer_state=state, answer_generator=answer)
            position = 0
            observed_ids = set()
            for item in captured:
                observation = item["observation"]
                actions = observation["payload"]["admissible_actions"]
                from backend.services.decision.policy_contracts import PolicyActionV0
                keys = {a["id"]: action_key(PolicyActionV0.model_validate(a)) for a in actions}
                expected = fixture["sequence"][position] if position < len(fixture["sequence"]) else None
                if observation["observation_id"] not in observed_ids:
                    observed_ids.add(observation["observation_id"])
                    candidate = metrics["candidate_generation"]
                    candidate["observations"] += 1
                    candidate["gold_covered"] += int(expected in keys.values())
                    remaining = set(fixture["sequence"][position:])
                    if not fixture["grounded"]:
                        remaining.add("generate_answer")
                    candidate["forbidden_leaks"] += len(set(keys.values()) - remaining)
                    for action in actions:
                        if action["kind"] == "call_tool":
                            candidate["binding_checks"] += 1
                            tool, args = action["args"]["tool_id"], action["args"]["input"]
                            bound = registry.runtime_tool(tool).runtime_input.model_validate(args).model_dump()
                            expected_args = {"get_recent_progress": {"book_name": context.book_name, "subject": context.subject, "days": 7, "limit": 12},
                                "search_exercises": {"book_name": context.book_name, "subject": context.subject, "query": fixture["request"], "chapter": "", "tag": "", "status": "", "limit": 8},
                                "search_textbook": {"query": fixture["request"], "chapter": ""}}[tool]
                            candidate["binding_errors"] += int(bound != expected_args)
                    for excluded in item["exclusions"]:
                        reason = excluded["reason"]
                        candidate["exclusion_reasons"][reason] = candidate["exclusion_reasons"].get(reason, 0) + 1
                validation = item["outcome"]["validation"]
                if validation["status"] == "rejected":
                    metrics["fallback"]["primary_rejections"] += 1
                    metrics["decision_validity"][validation["code"]] += 1
                    continue
                key = keys[item["decision"]["action_id"]]
                selected.append(key)
                selection = metrics["selection"]
                if expected not in keys.values():
                    selection["candidate_failures"] += 1
                elif item["trace"]["source"] == "forced":
                    selection["forced"] += 1
                    selection["forced_correct"] += int(key == expected)
                else:
                    selection["eligible"] += 1
                    selection["correct"] += int(key == expected)
                if item["trace"]["fallback_of"]:
                    metrics["fallback"]["attempts"] += 1
                    metrics["overhead"]["fallback_policy_calls"] += 1
                    metrics["overhead"]["policy_calls"] += 1
                    metrics["fallback"]["accepted"] += 1
                    metrics["fallback"]["execution_succeeded"] += int(item["outcome"]["execution"] == "succeeded")
                position += 1
            for frozen in observations:
                if frozen.envelope.observation_id in observed_ids:
                    continue
                candidate = metrics["candidate_generation"]
                candidate["observations"] += 1
                # The textbook-empty gold permits no further action, never ungrounded generation.
                candidate["gold_covered"] += int(not frozen.envelope.payload.admissible_actions and position == len(fixture["sequence"]))
                for exclusion in frozen.exclusions:
                    reason = exclusion["reason"]
                    candidate["exclusion_reasons"][reason] = candidate["exclusion_reasons"].get(reason, 0) + 1
            passed = result["task"]["status"] == fixture["task_status"] and selected == fixture["sequence"]
            metrics["task_execution"]["passed"] += int(passed)
            metrics["overhead"]["tool_calls"] += result["consumed_calls"]
            metrics["overhead"]["answer_stub_calls"] += stub_calls
            metrics["overhead"]["policy_calls"] += calls
            metrics["overhead"]["primary_policy_calls"] += calls
            metrics["overhead"]["rule_ms"] += sum(item["trace"]["duration_ms"] for item in captured if item["trace"]["source"] == "rules")
            trajectories.append({"fixture": fixture["id"], "passed": passed, "task_status": result["task"]["status"],
                "policy_calls": calls + sum(bool(item["trace"]["fallback_of"]) for item in captured),
                "fallback_used": any(item["trace"]["fallback_of"] is not None for item in captured),
                "tool_calls": result["consumed_calls"], "model_budget_consumed": result["consumed_model_calls"],
                "observations": [{"envelope": o.envelope.model_dump(exclude_none=True), "exclusions": o.exclusions} for o in observations],
                "trajectory": captured})
    # The third action executes only at the real pre-SQL checkpoint boundary.
    from backend.services.learning_task import LearningTaskStore
    from backend.services.decision.policy_gate import input_gate_trace, input_gate_observation
    with tempfile.TemporaryDirectory(prefix="texa-policy-gate-") as temp:
        store = LearningTaskStore(Path(temp))
        task = store.create(task_type="qa", goal="说明附表数据", artifacts={"request_question": "说明附表数据"})
        task.required_inputs = [{"name": "附表", "type": "clarification", "blocking": True, "status": "missing"}]
        gate_observation = input_gate_observation(task, "req_gate_fixture")
        task.artifacts["policy_gate"] = input_gate_trace(task, "req_gate_fixture")
        task = store.checkpoint(task, "waiting_for_input", status="waiting_for_input")
        passed = task.status == "waiting_for_input" and task.artifacts["policy_gate"]["outcome"]["continuation"] == "waiting"
        metrics["task_execution"]["passed"] += int(passed)
        metrics["candidate_generation"]["observations"] += 1
        metrics["candidate_generation"]["gold_covered"] += int([a.kind for a in gate_observation.envelope.payload.admissible_actions] == ["request_input"])
        metrics["selection"]["forced"] += 1
        metrics["selection"]["forced_correct"] += 1
        trajectories.append({"fixture": "blocking_input", "passed": passed, "task_status": task.status,
                             "observation": gate_observation.envelope.model_dump(exclude_none=True),
                             "decision": {"action_id": task.artifacts["policy_gate"]["action_id"]},
                             "trace": task.artifacts["policy_gate"], "policy_calls": 0})
    # A stale primary must never write an old-run rejection or invoke fallback.
    from backend.services.agent_runtime.contracts import RuntimeConflict
    with tempfile.TemporaryDirectory(prefix="texa-policy-resume-") as temp:
        scenario = {"request": "最近学习进度如何", "book_name": "", "grounded": False}
        store, registry, state, refs, context = fixture_runtime(Path(temp), scenario)
        run_id = store.task_snapshot("rtask_fixture")["run"]["id"]
        extra_calls = 0
        def stop_selector(_):
            nonlocal extra_calls
            extra_calls += 1
            store.close(run_id, "owner", outcome="paused", error_code="fixture_stop")
            return '{"action_id":"forged"}'
        stale = False
        try:
            BoundedAgentRunner(store, registry, None, refs, policy_selector=stop_selector).run_bounded(
                run_id, "owner", context=context, answer_state=state, answer_generator=lambda _: "never")
        except RuntimeConflict:
            stale = True
        stopped = store.snapshot(run_id)
        no_old_trace = not any("policy_decision" in event["payload"] for event in stopped["execution_events"])
        resumed = store.resume("rtask_fixture", expected_revision=stopped["task_revision"], request_key="resume",
            request_id="req_resume", owner_token="resumed_owner", turn_id="turn")
        resumed_trace = []
        def resumed_selector(observation):
            nonlocal extra_calls
            extra_calls += 1
            return RulePolicyV0(observation)
        final = BoundedAgentRunner(store, registry, None, refs, policy_selector=resumed_selector,
            policy_capture=lambda frozen, attempt, outcome: resumed_trace.append({
                "observation": frozen.envelope.model_dump(exclude_none=True),
                "decision": attempt.decision.model_dump(), "decision_output": attempt.raw_output, "trace": attempt.metadata(), "outcome": outcome.model_dump(), "exclusions": frozen.exclusions})).run_bounded(
                resumed["run"]["id"], "resumed_owner", context=context, answer_state=state,
                answer_generator=lambda _: "本次查询覆盖有限记录。")
        passed = stale and no_old_trace and stopped["consumed_calls"] == 0 and final["task"]["status"] == "completed"
        metrics["task_execution"]["passed"] += int(passed)
        metrics["decision_validity"]["stale_or_environment_changed"] += int(stale)
        metrics["overhead"]["tool_calls"] += final["consumed_calls"]
        metrics["overhead"]["answer_stub_calls"] += final["consumed_model_calls"]
        metrics["overhead"]["policy_calls"] += extra_calls
        metrics["overhead"]["primary_policy_calls"] += extra_calls
        metrics["overhead"]["rule_ms"] += sum(item["trace"]["duration_ms"] for item in resumed_trace if item["trace"]["source"] == "rules")
        from backend.services.decision.policy_contracts import PolicyObservationV0
        for index, item in enumerate(resumed_trace):
            obs = PolicyObservationV0.model_validate(item["observation"]["payload"])
            expected = ["tool:get_recent_progress", "generate_answer"][index]
            keys = {a.id: action_key(a) for a in obs.admissible_actions}
            metrics["candidate_generation"]["observations"] += 1
            metrics["candidate_generation"]["gold_covered"] += int(expected in keys.values())
            for action in obs.admissible_actions:
                if action.kind == "call_tool":
                    metrics["candidate_generation"]["binding_checks"] += 1
                    metrics["candidate_generation"]["binding_errors"] += int(action.args.input != {
                        "book_name": "", "subject": "数学", "days": 7, "limit": 12})
            for exclusion in item["exclusions"]:
                reason = exclusion["reason"]
                counts = metrics["candidate_generation"]["exclusion_reasons"]
                counts[reason] = counts.get(reason, 0) + 1
            bucket = "forced" if item["trace"]["source"] == "forced" else "eligible"
            correct_bucket = "forced_correct" if bucket == "forced" else "correct"
            metrics["selection"][bucket] += 1
            metrics["selection"][correct_bucket] += int(keys[item["decision"]["action_id"]] == expected)
        trajectories.append({"fixture": "stale_stop_resume", "passed": passed,
            "old_run_policy_writes": 0 if no_old_trace else 1, "fallback_attempts": 0,
            "task_status": final["task"]["status"], "trajectory": resumed_trace})
    for group, numerator, denominator in (("selection", "correct", "eligible"),
                                         ("task_execution", "passed", "fixtures")):
        metrics[group]["accuracy" if group == "selection" else "success_rate"] = metrics[group][numerator] / metrics[group][denominator] if metrics[group][denominator] else None
    return {"contract": "texa.runtime-policy/v0", "scope": "finite deterministic fixtures; no online answer quality claim",
            "metrics": metrics, "fixtures": trajectories}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run_baseline()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report["metrics"], ensure_ascii=False))
    return 0 if all(item["passed"] for item in report["fixtures"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
