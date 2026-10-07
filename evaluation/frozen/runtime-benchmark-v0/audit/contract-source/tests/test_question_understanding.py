"""Rules-first interpretation contracts, with fake adapters and no paid calls."""
import json

import pytest

from backend.services.question_understanding import build_request, understand_question
from backend.services.session_context import SessionContextState, build_resolution_trace
from graph.question_understanding import VERSION, validate_interpretation


def output(intent="qa", dimensions=(), spans=(), reference="", action="continue"):
    return {"action": action, "intent": intent, "dimensions": list(dimensions),
            "entity_spans": list(spans), "reference_id": reference}


def span(question, entity):
    start = question.index(entity)
    return {"start": start, "end": start + len(entity)}


def runner(payload, calls=None):
    def run(prompt):
        if calls is not None:
            calls.append(prompt)
        return "<think>private</think>" + json.dumps(payload, ensure_ascii=False)
    return run


@pytest.mark.parametrize("question", [
    "电阻式传感器可以分成哪两种类型", "比较压阻效应和压电效应", "教我电容式传感器",
    "抽几道习题", "它有什么特点", "第九个是什么意思",
])
def test_off_preserves_existing_rule_decision_and_never_calls(question):
    initial = {"topic": "压阻效应", "entities": ["压阻效应"]}
    baseline = build_resolution_trace(question, [], initial_state=initial, understanding_mode="off")
    calls = []
    disabled = build_resolution_trace(question, [], initial_state=initial, understanding_mode="off",
                                      understanding_model_runner=runner(output(), calls))
    assert disabled == baseline
    assert calls == []


@pytest.mark.parametrize("question", ["比较压阻效应和压电效应", "推导欧拉公式", "矩阵的秩怎么算？", "电阻式传感器，它有两种材料"])
def test_deterministic_intent_keeps_priority(question):
    calls = []
    trace = build_resolution_trace(question, [], understanding_mode="fallback",
                                   understanding_model_runner=runner(output("quiz"), calls))
    assert calls == [] and trace["question_understanding"] == {}


def test_deterministic_reference_keeps_priority_even_with_unclear_intent():
    calls = []
    trace = build_resolution_trace("它呢？", [], initial_state={"topic": "压阻效应"},
                                   understanding_mode="fallback",
                                   understanding_model_runner=runner(output("quiz"), calls))
    assert not calls and trace["method"].startswith("deterministic")


@pytest.mark.parametrize("question,intent,dimensions,entities", [
    ("呃电阻式传感器它有两种材料，两种各自好在哪里，用在什么地方", "comparison", ["classification", "features", "scenarios"], ["电阻式传感器"]),
    ("嗯压阻效应跟压电效应，放一块说说呗", "comparison", ["comparison"], ["压阻效应", "压电效应"]),
    ("呃电容式传感器这块我没弄懂，从头带我过一遍", "teach", ["principle"], ["电容式传感器"]),
    ("给我捞几道积分的题做做吧", "quiz", ["exercises"], ["积分"]),
])
def test_colloquial_understanding_keeps_original_and_uses_literal_objects(question, intent, dimensions, entities):
    calls = []
    payload = output(intent, dimensions, [span(question, entity) for entity in entities])
    trace = build_resolution_trace(question, [], understanding_mode="fallback",
                                   understanding_model_runner=runner(payload, calls))
    assert len(calls) == 1
    assert trace["resolution_action"] == "continue"
    assert trace["resolved_query"] == question
    assert trace["state_after"]["topic"] == "和".join(entities)
    assert trace["question_understanding"]["intent"] == intent
    assert "private" not in str(trace)


def test_unresolved_history_reference_uses_only_bounded_id():
    calls = []
    trace = build_resolution_trace("第九个是什么意思？", [], initial_state={"topic": "压阻效应", "entities": ["压阻效应"]},
                                   understanding_mode="fallback", semantic_enabled=True,
                                   semantic_model_runner=lambda _: pytest.fail("second model call"),
                                   understanding_model_runner=runner(output("definition", reference="r0"), calls))
    assert len(calls) == 1 and trace["method"] == "understanding_reference"
    assert "压阻效应" in trace["resolved_query"]


def test_clarification_never_advances_state():
    initial = {"topic": "压阻效应", "entities": ["压阻效应"]}
    trace = build_resolution_trace("第九个是什么意思？", [], initial_state=initial,
                                   understanding_mode="fallback",
                                   understanding_model_runner=runner(output(action="clarify")))
    assert trace["resolution_action"] == "clarify"
    assert trace["state_before"] == trace["state_after"]


def test_current_sentence_reference_can_override_stale_topic_without_inheriting_constraints():
    question = "呃电阻式传感器它有两种材料，各自好在哪里"
    initial = {"topic": "压阻效应", "entities": ["压阻效应"],
               "frame": {"entities": ["压阻效应", "压电效应"]}, "constraints": ["只比较温度"]}
    trace = build_resolution_trace(question, [], initial_state=initial, understanding_mode="fallback",
                                   understanding_model_runner=runner(output("comparison", ["features"], [span(question, "电阻式传感器")])))
    assert trace["resolution_action"] == "continue"
    assert trace["resolved_query"] == question
    assert trace["state_after"]["topic"] == "电阻式传感器"
    assert trace["state_after"]["constraints"] == [] and trace["state_after"]["frame"] == {}


def test_colloquial_comparison_preserves_pair_for_next_rule_reference():
    question = "嗯压阻效应跟压电效应，放一块说说呗"
    trace = build_resolution_trace(question, [], understanding_mode="fallback", understanding_model_runner=runner(
        output("comparison", ["comparison"], [span(question, "压阻效应"), span(question, "压电效应")]),
    ))
    followup = build_resolution_trace("这两个呢？", [], initial_state=trace["state_after"], understanding_mode="off")
    assert followup["referenced_entities"] == ["压阻效应", "压电效应"]


def test_locked_intent_is_preserved_when_model_only_needed_for_reference():
    request = build_request("比较第九个和第十个", SessionContextState(topic="压阻效应"), {"method": "unresolved_reference"})
    interpreted = validate_interpretation(output("quiz", reference="r0"), request)
    assert interpreted["intent"] == "comparison"


def test_shadow_leaves_resolution_and_ledger_unchanged():
    question = "呃电阻式传感器它有两种材料，两种各自好在哪里"
    off = build_resolution_trace(question, [], understanding_mode="off")
    shadow = build_resolution_trace(question, [], understanding_mode="shadow",
                                    understanding_model_runner=runner(output("comparison", spans=[span(question, "电阻式传感器")])))
    for key in ("resolved_query", "resolution_action", "method", "state_operations", "state_after", "speech_act"):
        assert shadow[key] == off[key]
    assert shadow["question_understanding"] == {}
    assert shadow["question_understanding_trace"]["accepted"]


@pytest.mark.parametrize("mutation", [
    {"reference_id": "invented"}, {"resolved_query": "我是新问题"}, {"tool": "delete_book"},
    {"intent": "exercise.create_set"}, {"dimensions": ["new_subject"]},
    {"entity_spans": [{"start": -1, "end": 4}]},
    {"entity_spans": [{"start": True, "end": 4}]},
    {"entity_spans": [{"start": 0, "end": 999}]},
    {"reference_id": "r0", "entity_spans": [{"start": 0, "end": 4}]},
    {"dimensions": ["features"] * 5},
])
def test_untrusted_output_cannot_invent_objects_conditions_or_actions(mutation):
    request = build_request("压阻效应是什么意思", SessionContextState(topic="压电效应"), {"method": "unresolved_reference"})
    with pytest.raises((ValueError, TypeError)):
        validate_interpretation({**output(), **mutation}, request)


def test_model_cannot_demand_clarification_of_an_independent_question():
    request = build_request("谈谈压阻效应", SessionContextState(), {"method": "identity_no_history"})
    with pytest.raises(ValueError):
        validate_interpretation(output(action="clarify"), request)


def test_model_error_is_redacted_and_original_gate_is_preserved():
    def fail(_):
        raise TimeoutError("secret-api-key private-user-text endpoint")
    trace = build_resolution_trace("第九个是什么意思？", [], understanding_mode="fallback", understanding_model_runner=fail)
    assert trace["resolution_action"] == "clarify"
    assert trace["question_understanding_trace"]["reason"] == "invalid_output_or_model_error"
    assert "secret-api" not in str(trace) and "endpoint" not in str(trace)


def test_default_or_unconfigured_never_uses_answer_model(monkeypatch):
    import config
    monkeypatch.delenv("QUESTION_UNDERSTANDING_MODE", raising=False)
    monkeypatch.delenv("LLM_UNDERSTANDING_MODEL", raising=False)
    monkeypatch.setattr(config, "get_llm", lambda **_: pytest.fail("answer model constructed"))
    question = "第九个是什么意思？"
    for mode in (None, "fallback"):
        trace = build_resolution_trace(question, [], understanding_mode=mode)
        assert not trace["question_understanding_trace"]["attempted"]


def test_independent_small_model_config_supports_arbitrary_compatible_names():
    from llm.configuration import resolve_understanding_model
    assert resolve_understanding_model({"LLM_REASONING_MODEL": "answer", "DASHSCOPE_API_KEY": "do-not-reuse"}) is None
    model = resolve_understanding_model({"LLM_UNDERSTANDING_PROVIDER": "openai_compatible",
                                         "LLM_UNDERSTANDING_MODEL": "future-small-model",
                                         "LLM_UNDERSTANDING_BASE_URL": "http://127.0.0.1:8001/v1"})
    assert model.model == "future-small-model" and model.api_key == ""
    local = resolve_understanding_model({"LLM_UNDERSTANDING_PROVIDER": "ollama",
                                         "LLM_UNDERSTANDING_MODEL": "future-qwen:0.8b"})
    assert local.credential_configured


def pack(intent="quiz", dimensions=("exercises",)):
    return {"version": VERSION, "accepted": True, "action": "continue", "intent": intent, "dimensions": list(dimensions)}


def test_upstream_candidates_include_read_exercise_without_enabling_writes():
    from backend.services.decision.contracts import DecisionContext
    from backend.services.decision.router import DecisionRouter, matching_capabilities
    from backend.services.tool_orchestration import ToolOrchestrationRequest, select_tool_calls
    question = "给我捞几道积分的题做做吧"
    assert matching_capabilities(question) == (("math.verify", "math"),)
    assert matching_capabilities(question, understanding=pack()) == (("exercise.inspect", "understanding_read_hint"), ("math.verify", "math"))
    context = DecisionContext("r", question, question, "subject_general", question_understanding=pack())
    assert DecisionRouter(shadow=False).route(context).selected_capability == "exercise.inspect"
    assert DecisionRouter().route(DecisionContext(**{**context.__dict__, "required_inputs": ("missing page",)})).mode == "clarify"
    calls = select_tool_calls(ToolOrchestrationRequest(question, book_name="book", question_understanding=pack()))
    assert [item["tool"] for item in calls] == ["search_exercises"]
    assert select_tool_calls(ToolOrchestrationRequest(question, question_understanding=pack())) == []
    # An explicit rule retains its route even if a hint disagrees.
    assert matching_capabilities("查询最近学习进度", understanding=pack())[0][0] == "learning.inspect"


def test_policy_receives_interpretation_before_candidate_projection(tmp_path):
    from evaluation.runtime_policy_v0 import fixture_runtime
    from backend.services.decision.policy_projection import matched_tool_refs, project_observation, runtime_identity
    from backend.services.decision.policy import RulePolicyV0
    store, registry, state, _, context = fixture_runtime(tmp_path, {
        "id": "understanding", "request": "给我捞几道积分的题做做吧", "book_name": "fixture", "grounded": False,
    })
    state["question_understanding"] = pack()
    refs, _ = matched_tool_refs(state["user_input"], registry, understanding=pack())
    assert [item["id"] for item in refs] == ["search_exercises"]
    snapshot = store.task_snapshot("rtask_fixture")
    frozen = project_observation(request=state["user_input"], resolved_query=state["user_input"], registry=registry,
                                 context=context, identity=runtime_identity(snapshot), snapshot=snapshot,
                                 answer_state=state, candidate_tools=refs)
    decision = RulePolicyV0(frozen.envelope.payload)
    assert frozen.bindings[decision.action_id]["args"]["tool_id"] == "search_exercises"
    blocked = project_observation(request=state["user_input"], resolved_query=state["user_input"], registry=registry,
                                  context=context, identity=runtime_identity(snapshot), snapshot=snapshot,
                                  answer_state=state, candidate_tools=refs,
                                  missing_inputs=[{"name": "missing page", "blocking": True}])
    assert not blocked.envelope.payload.admissible_actions


def test_graph_preserves_input_and_planner_keeps_strong_rules():
    from graph.main_graph import build_initial_state
    from graph.planner import plan_node
    question = "电容式传感器这块我没弄懂，从头带我过一遍"
    state = build_initial_state(question, use_textbook_context=False,
                                continuity_context={"question_understanding": pack("teach", ("principle",))})
    assert state["user_input"] == question
    assert plan_node(state)["intent"] == "teach"
    result = plan_node(build_initial_state("比较压阻效应和压电效应", use_textbook_context=False,
                                           continuity_context={"question_understanding": pack("quiz")}))
    assert result["intent"] == "comparison"


def test_api_bridge_failure_does_not_repeat_understanding(monkeypatch):
    import backend.api.chat as api
    import backend.services.question_understanding as adapter
    calls = []
    monkeypatch.setenv("QUESTION_UNDERSTANDING_MODE", "fallback")
    monkeypatch.setattr(adapter, "configured_runner", lambda: runner(output("quiz", ["exercises"]), calls))
    monkeypatch.setattr(api, "get_or_rebuild_session_ledger", lambda *_: {"state": {}, "last_seq": 2})
    monkeypatch.setattr(api, "bridge_learning_request", lambda *_, **__: (_ for _ in ()).throw(RuntimeError("bridge failed")))
    query, trace = api._resolve_request_question("给我捞几道题做做吧", [], "c", book_name="book", subject="math")
    assert len(calls) == 1 and query == "给我捞几道题做做吧"
    assert trace["question_understanding"]["intent"] == "quiz"
    assert trace["learning_bridge"]["error"] == "bridge_unavailable"


def test_preparation_carries_hints_and_resume_does_not_reinterpret(monkeypatch):
    import backend.api.chat as api
    from types import SimpleNamespace

    question = "给我捞几道题做做吧"
    trace = {"resolved_query": question, "resolution_action": "continue", "question_understanding": pack(),
             "state_before": {}, "state_after": {}}
    calls = []
    monkeypatch.setattr(api, "resolve_conversation_id_for_scope", lambda *_: "c")
    monkeypatch.setattr(api, "load_history", lambda *_: [])
    monkeypatch.setattr(api, "_resolve_request_question", lambda *_, **__: (calls.append(True) or question, trace))
    monkeypatch.setattr(api, "_safe_record_evidence_invalidation", lambda *_: None)
    monkeypatch.setattr(api, "_conversation_context_seed", lambda *_: {})
    monkeypatch.setattr(api, "_safe_subject_suggestion", lambda *_: None)
    monkeypatch.setattr(api, "current_context_versions", lambda *_: {})
    req = api.ChatRequest(question=question, subject="math", book_name="book", conversation_id="c", answer_mode="subject_general")
    prepared = api._prepare_chat_turn(req)
    assert prepared["continuity_context"]["question_understanding"] == pack()
    assert len(calls) == 1
    task = SimpleNamespace(artifacts={"resolved_query": question, "resolution_trace": trace, "context_versions": {}})
    resumed = api._prepare_chat_turn(req, resume=True, resume_task=task)
    assert resumed["continuity_context"]["question_understanding"] == pack()
    assert len(calls) == 1


def test_colloquial_dimensions_reach_final_evidence_without_expanding_scope(monkeypatch):
    from graph import retrieval_node as retrieval
    from graph.safe_retrieval import SafeKG
    from graph.evidence_pack import build_evidence_pack
    from ingestion.lexical_index import search_rows, expand_neighbors_rows
    from ingestion.vector_store import RetrievalOutcome

    class EmptyVectors:
        def search_all(self, *_, **__):
            return RetrievalOutcome(items={})
        def search_chapter(self, *_, **__):
            return RetrievalOutcome(items=[])

    parent = ["第四章", "4.1 应变式电阻传感器"]
    rows = [{"chunk_id": key, "chunk_index": index, "section_chunk_index": 0,
             "book_name": "demo", "chapter": "第四章", "section_title": title,
             "section_path": [*parent, title], "content": text, "block_type": "paragraph", "role": "definition"}
            for key, index, title, text in [
                ("types", 10, "4.1.1 电阻应变片的种类", "按材料分类，电阻应变片可分为金属应变片和半导体应变片两大类。"),
                ("metal", 11, "4.1.2 金属电阻应变片", "金属应变片的特点是性能稳定，适用于静态测量。"),
                ("semi", 70, "4.1.3 半导体应变片", "半导体应变片的特点是灵敏度高，温度稳定性差。"),
            ]]
    query = "呃电阻式传感器它有两种材料，各自好在哪里，用在什么地方"
    trace = build_resolution_trace(query, [], understanding_mode="fallback", understanding_model_runner=runner(
        output("comparison", ["classification", "features", "scenarios"], [span(query, "电阻式传感器")]),
    ))
    monkeypatch.setattr(retrieval, "get_safe_kg", lambda _: (SafeKG(), ""))
    monkeypatch.setattr(retrieval, "_load_history", lambda *_: [])
    calls = []
    def lexical(book, question, **kwargs):
        calls.append((book, question, kwargs))
        assert book == "demo" and kwargs["chapters"] == ["第四章"]
        return search_rows(rows, question, **kwargs)
    result = retrieval.retrieve_node({"user_input": query, "book_name": "demo", "intent": "comparison",
                                      "target_chapters": ["第四章"], "use_textbook_context": True,
                                      "question_understanding": trace["question_understanding"]},
                                     vector_store=EmptyVectors(), lexical_search=lexical,
                                     neighbor_expander=lambda _, ids, **kw: expand_neighbors_rows(rows, ids, **kw),
                                     index_stats_override={"demo": {"healthy": True}},
                                     retrieval_resources_override=[{"book_name": "demo", "is_primary": True, "is_selected": True, "role": "core", "priority": 1}])
    evidence = build_evidence_pack(result["evidence_items"], intent="comparison")
    assert evidence["items"][0]["chunk_id"] == "types"
    assert "性能稳定" in evidence["text"] and "温度稳定性差" in evidence["text"]
    assert len([call for call in calls if call[1] == "电阻式传感器 分类 种类 材料"]) == 1
