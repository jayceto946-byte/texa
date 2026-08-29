from datetime import datetime, timedelta
from types import SimpleNamespace

from ingestion.vector_store import RetrievalOutcome
import time

from backend.api import agent as agent_api
from backend.api.agent import ReadOnlyAgentRequest, _select_tool_calls
from backend.tools import learning_tools
from backend.tools.registry import ToolContext, ToolResult, get_tool_registry
from memory.exercise_bank import ExerciseRecord


def test_tool_registry_exposes_read_only_learning_tools():
    registry = get_tool_registry()
    names = {tool["name"] for tool in registry.list_tools()}

    assert "search_textbook" in names
    assert "search_concepts" in names
    assert "find_textbook_examples" in names
    assert "get_due_mistakes" in names
    assert "get_mistake_stats" in names
    assert "get_weak_concepts" in names
    assert "search_exercises" in names
    assert "get_recent_progress" in names
    assert "propose_add_mistake" in names
    assert "propose_practice_session" in names


def test_propose_add_mistake_returns_pending_action_without_write():
    registry = get_tool_registry()
    result = registry.call(
        "propose_add_mistake",
        {"question_text": "test question", "user_answer": "A"},
        ToolContext(book_name="default", subject="math"),
    )

    assert result.success is True
    assert result.pending_action is not None
    assert result.pending_action["type"] == "add_mistake"
    assert result.pending_action["payload"]["question_text"] == "test question"


def test_read_only_agent_selects_review_tools_for_review_question():
    req = ReadOnlyAgentRequest(question="我最近有哪些错题到期复习？", book_name="default", subject="math")
    selected = _select_tool_calls(req)
    names = [call["tool"] for call in selected]

    assert names == ["build_review_plan", "get_weak_concepts"]


def test_find_textbook_examples_filters_and_deduplicates(monkeypatch):
    example = SimpleNamespace(
        page_content="例1 求函数在给定区间上的极值。\n解：先求导。",
        metadata={
            "chunk_id": "example-1",
            "role": "example",
            "section_title": "例题",
            "page_idx": 12,
        },
    )
    reference = SimpleNamespace(
        page_content="这是普通说明文字。",
        metadata={"chunk_id": "reference-1", "role": "reference"},
    )

    class DummyVectorStore:
        def search_all(self, *_args, **_kwargs):
            return RetrievalOutcome(items={"第一章": [example, reference]})

    monkeypatch.setattr(
        learning_tools,
        "get_safe_vector_store",
        lambda: (DummyVectorStore(), ""),
    )
    result = learning_tools.find_textbook_examples(
        ToolContext(book_name="math"),
        {"query": "极值", "limit": 5},
    )

    assert result.success is True
    assert [item["chunk_id"] for item in result.data["examples"]] == ["example-1"]


def test_get_weak_concepts_merges_memory_and_mistakes(monkeypatch):
    class DummyConceptMemory:
        def get_weak_points(self):
            return [{
                "name": "极限",
                "weak_reason": "review",
                "exposure_count": 4,
                "mastery_level": 2,
                "subjects": ["math"],
                "source_chapters": ["第一章"],
            }]

    mistake = SimpleNamespace(
        id="mistake-1",
        linked_concepts=[{"name": "极限"}, {"name": "连续"}],
        tags=["极限"],
        chapter="第一章",
    )
    monkeypatch.setattr(learning_tools, "ConceptMemory", lambda _book: DummyConceptMemory())
    monkeypatch.setattr(
        learning_tools,
        "get_mistake_book",
        lambda *_args, **_kwargs: SimpleNamespace(list_all=lambda **_filters: [mistake]),
    )

    result = learning_tools.get_weak_concepts(
        ToolContext(book_name="math", subject="math"),
        {"limit": 5},
    )

    assert result.success is True
    by_name = {item["name"]: item for item in result.data["weak_concepts"]}
    assert by_name["极限"]["explicit_weak"] is True
    assert by_name["极限"]["mistake_count"] == 1
    assert by_name["连续"]["mistake_ids"] == ["mistake-1"]


def test_search_exercises_uses_natural_language_core_and_hides_solution(monkeypatch):
    records = [
        ExerciseRecord(
            id="exercise-limit",
            question_text="求数列的极限",
            answer="1",
            explanation="使用夹逼定理",
            subject="math",
            tags=["极限"],
            linked_concepts=[{"name": "数列极限"}],
            status="needs_review",
        ),
        ExerciseRecord(
            id="exercise-matrix",
            question_text="计算矩阵的秩",
            subject="math",
            tags=["矩阵"],
        ),
    ]
    monkeypatch.setattr(
        learning_tools,
        "get_exercise_bank",
        lambda *_args, **_kwargs: SimpleNamespace(list_all=lambda **_filters: records),
    )

    result = learning_tools.search_exercises(
        ToolContext(book_name="math", subject="math"),
        {"query": "给我安排练习，做几道极限题", "limit": 5},
    )

    assert result.success is True
    assert [item["id"] for item in result.data["exercises"]] == ["exercise-limit"]
    assert "answer" not in result.data["exercises"][0]
    assert result.data["exercises"][0]["answer_available"] is True


def test_get_recent_progress_summarizes_bounded_event_log(monkeypatch):
    now = datetime.now()
    events = [
        SimpleNamespace(
            id="event-1",
            event_type="chat_qa",
            timestamp=now.isoformat(),
            source_type="conversation",
            source_id="conversation-1",
            concept_names=["极限"],
            payload={"question": "什么是数列极限？"},
        ),
        SimpleNamespace(
            id="event-2",
            event_type="exercise_practiced",
            timestamp=(now - timedelta(days=1)).isoformat(),
            source_type="exercise",
            source_id="exercise-1",
            concept_names=["极限"],
            payload={"quality": 4, "status": "mastered"},
        ),
        SimpleNamespace(
            id="old-event",
            event_type="mistake_added",
            timestamp=(now - timedelta(days=40)).isoformat(),
            source_type="mistake",
            source_id="mistake-1",
            concept_names=["矩阵"],
            payload={},
        ),
    ]
    monkeypatch.setattr(
        learning_tools,
        "get_learning_event_store",
        lambda: SimpleNamespace(list_recent=lambda **_filters: events),
    )

    result = learning_tools.get_recent_progress(
        ToolContext(book_name="math", subject="math"),
        {"days": 7},
    )

    assert result.success is True
    assert result.data["summary"]["total_events"] == 2
    assert result.data["summary"]["qa_count"] == 1
    assert result.data["summary"]["exercises_practiced"] == 1
    assert result.data["top_concepts"] == [{"name": "极限", "count": 2}]


def test_propose_practice_session_returns_confirmation_without_write(monkeypatch):
    record = ExerciseRecord(
        id="exercise-1",
        question_text="求函数极限",
        subject="math",
        tags=["极限"],
    )
    bank = SimpleNamespace(list_all=lambda **_filters: [record])
    monkeypatch.setattr(learning_tools, "get_exercise_bank", lambda *_args, **_kwargs: bank)

    result = learning_tools.propose_practice_session(
        ToolContext(book_name="math", subject="math"),
        {"query": "极限", "limit": 3},
    )

    assert result.success is True
    assert result.pending_action["type"] == "create_practice_session"
    assert result.pending_action["payload"]["exercise_ids"] == ["exercise-1"]
    assert result.data["preview"]["exercise_count"] == 1


def test_read_only_agent_selects_new_tools_for_matching_requests():
    examples = _select_tool_calls(ReadOnlyAgentRequest(
        question="找一道教材里的极限例题",
        book_name="math",
        subject="math",
    ))
    progress = _select_tool_calls(ReadOnlyAgentRequest(
        question="总结一下我最近的学习进度",
        book_name="math",
        subject="math",
    ))
    practice = _select_tool_calls(ReadOnlyAgentRequest(
        question="给我安排练习，做几道极限题",
        book_name="math",
        subject="math",
    ))

    assert "find_textbook_examples" in [item["tool"] for item in examples]
    assert "get_recent_progress" in [item["tool"] for item in progress]
    practice_names = [item["tool"] for item in practice]
    assert "search_exercises" in practice_names
    assert "propose_practice_session" in practice_names


def test_read_only_agent_records_tool_and_synthesis_timings(monkeypatch):
    class DummyRegistry:
        def call(self, *_args, **_kwargs):
            return ToolResult(True, data={"plan": []})

    monkeypatch.setattr(agent_api, "get_tool_registry", lambda: DummyRegistry())
    monkeypatch.setattr(
        agent_api,
        "_select_tool_calls",
        lambda _req: [{"tool": "build_review_plan", "args": {"limit": 3}}],
    )
    monkeypatch.setattr(agent_api, "_synthesize_answer", lambda *_args, **_kwargs: "今日复习建议")

    response = agent_api.run_read_only_agent(ReadOnlyAgentRequest(
        question="我今天复习什么",
        book_name="math",
        subject="math",
    ))

    assert response["success"] is True
    assert response["answer"] == "今日复习建议"
    assert response["tool_outputs"][0]["timing"]["status"] == "complete"
    assert response["execution_trace"]["synthesis"]["status"] == "complete"
    assert response["execution_trace"]["total_elapsed_ms"] >= 0


def test_read_only_agent_returns_when_synthesis_exceeds_budget(monkeypatch):
    class DummyRegistry:
        def call(self, *_args, **_kwargs):
            return ToolResult(True, data={"plan": []})

    def slow_synthesis(*_args, **_kwargs):
        time.sleep(0.08)
        return "too late"

    monkeypatch.setattr(agent_api, "get_tool_registry", lambda: DummyRegistry())
    monkeypatch.setattr(
        agent_api,
        "_select_tool_calls",
        lambda _req: [{"tool": "build_review_plan", "args": {}}],
    )
    monkeypatch.setattr(agent_api, "_synthesize_answer", slow_synthesis)
    monkeypatch.setattr(agent_api, "AGENT_SYNTHESIS_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(agent_api, "AGENT_TOTAL_TIMEOUT_SECONDS", 0.05)

    started = time.perf_counter()
    response = agent_api.run_read_only_agent(ReadOnlyAgentRequest(
        question="我今天复习什么",
        book_name="math",
    ))

    assert time.perf_counter() - started < 0.07
    assert response["success"] is True
    assert response["execution_trace"]["synthesis"]["status"] == "timeout"
    assert "总结超时" in response["answer"]


def test_read_only_agent_marks_slow_tool_unavailable(monkeypatch):
    class SlowRegistry:
        def call(self, *_args, **_kwargs):
            time.sleep(0.08)
            return ToolResult(True, data={})

    monkeypatch.setattr(agent_api, "get_tool_registry", lambda: SlowRegistry())
    monkeypatch.setattr(
        agent_api,
        "_select_tool_calls",
        lambda _req: [{"tool": "get_due_mistakes", "args": {}}],
    )
    monkeypatch.setattr(agent_api, "AGENT_TOOL_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(agent_api, "AGENT_TOTAL_TIMEOUT_SECONDS", 0.05)

    response = agent_api.run_read_only_agent(ReadOnlyAgentRequest(
        question="到期错题",
        book_name="math",
        synthesize=False,
    ))

    assert response["success"] is False
    assert response["tool_outputs"][0]["timing"]["status"] == "timeout"
    assert "timed out" in response["tool_outputs"][0]["result"]["message"]
