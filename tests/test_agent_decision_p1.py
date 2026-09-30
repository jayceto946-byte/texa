from __future__ import annotations

from backend.services.decision.contracts import DecisionContext, SemanticCandidate, SemanticRanking
from backend.services.decision.router import DecisionRouter, CalibrationProfile
from backend.services.decision.resolver import resolve_candidate_tools
from backend.services.decision.trace import RoutingTraceStore
from backend.services.agent_runtime.progress_tool import register_recent_progress_runtime
from backend.tools.registry import ToolRegistry
from memory.learning_events import LearningEventStore


def context(text="解释极限", mode="global_general", **kwargs):
    return DecisionContext("req", text, text, mode, **kwargs)


class FakeSemantic:
    def __init__(self):
        self.called = 0
    def rank(self, context, candidates):
        self.called += 1
        return SemanticRanking((SemanticCandidate("learning.inspect", .9, 1),
                                SemanticCandidate("textbook.search", .1, 2)), "fake", "1")


def test_explicit_and_gate_bypass_semantic():
    semantic = FakeSemantic()
    router = DecisionRouter(semantic=semantic)
    assert router.route(context(explicit_action="inspect_learning")).selected_capability == "learning.inspect"
    assert router.route(context(current_task_status="waiting_for_input")).mode == "clarify"
    assert semantic.called == 0


def test_scope_and_negative_matrix():
    router = DecisionRouter()
    assert router.route(context()).mode == "direct_answer"
    assert router.route(context(mode="textbook_grounded", book_ids=("book",))).selected_capability == "textbook.search"
    assert router.route(context("按教材解释极限")).selected_capability == "textbook.search"
    assert router.route(context("我极限部分掌握得怎样")).selected_capability == "learning.inspect"
    assert router.route(context("把这道错题加入错题本")).selected_capability == "mistake.manage"
    assert router.route(context("计算 2+3")).selected_capability == "math.verify"
    assert router.route(context(attachments=("image",))).mode == "unsupported"
    assert router.route(context(mode="subject_mismatch")).mode == "clarify"


def test_shadow_does_not_override_and_calibrated_live_route():
    semantic = FakeSemantic()
    shadow = DecisionRouter(semantic=semantic)
    result = shadow.route(context())
    assert result.mode == "direct_answer" and result.shadow_only
    profile = CalibrationProfile("fake", "1", {"learning.inspect": .8},
                                 {"learning.inspect": .5}, 40, "test")
    live = DecisionRouter(semantic=semantic, calibration=profile, shadow=False)
    assert live.route(context("xyz", mode="auto")).selected_capability == "learning.inspect"
    too_high = CalibrationProfile("fake", "1", {"learning.inspect": .95},
                                  {"learning.inspect": .5}, 40, "test")
    assert DecisionRouter(semantic=semantic, calibration=too_high, shadow=False).route(context("xyz", mode="auto")).mode == "unsupported"


def test_resolver_only_canonical_and_trace_is_redacted(tmp_path):
    events = LearningEventStore(tmp_path / "learning.db")
    registry = ToolRegistry()
    register_recent_progress_runtime(registry, events)
    result = DecisionRouter().route(context("最近学习活动"))
    candidates = resolve_candidate_tools(result, registry)
    assert [item["id"] for item in candidates.tool_refs] == ["get_recent_progress"]
    trace = RoutingTraceStore(tmp_path / "trace.db")
    trace_id = trace.record(context("最近学习活动"), result)
    with trace._connect() as conn:
        row = conn.execute("SELECT input_hash,decision_json FROM routing_traces").fetchone()
        assert row[0] != "最近学习活动"
        assert "最近学习活动" not in row[1]


def test_human_review_group_split_and_holdout_do_not_enable_takeover(tmp_path):
    store = RoutingTraceStore(tmp_path / "routing.db")
    router = DecisionRouter()
    for question in ("解释学习方法", "解释学习方法的步骤"):
        request = context(question)
        trace_id = store.record(request, router.route(request))
        store.review(trace_id, reviewer_id="human", expected_capability="direct_answer", holdout_group="conversation-1:week-1")
    with store._connect() as conn:
        assert len({row[0] for row in conn.execute("SELECT split FROM routing_reviews")}) == 1
    report = store.review_report()
    assert sum(group["samples"] for group in report["groups"].values()) == 2
    assert report["automatic_takeover_allowed"] is False
    assert len(store.list(limit=1)) == 1
