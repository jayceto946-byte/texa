from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from backend.main import app
from backend.api.chat import _scope_from_learning_context
from backend.services.learning_state import LearningStateService
from backend.services.learning_state_bridge import (
    bridge_learning_request,
    classify_learning_speech_act,
)
from backend.services.learning_state_reducer import reduce_learning_events
from backend.services.session_context import build_resolution_trace
from memory.learning_events import LearningEvent, LearningEventStore


def test_learning_event_store_migrates_v1_without_losing_rows(tmp_path):
    path = tmp_path / "learning_events.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE learning_events (id TEXT PRIMARY KEY, event_type TEXT NOT NULL, "
            "timestamp TEXT NOT NULL, book_name TEXT, subject TEXT, conversation_id TEXT, "
            "source_type TEXT, source_id TEXT, concept_names TEXT NOT NULL, payload TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO learning_events VALUES "
            "('evt_old', 'concept_exposure', '2026-08-01T10:00:00', 'demo', '数学', "
            "'conv-old', 'conversation', 'conv-old', '[\"导数\"]', '{}')"
        )
        conn.execute("PRAGMA user_version = 1")
        conn.commit()

    store = LearningEventStore(path)
    events = store.list_for_state(learner_id="local_default", book_name="demo")

    assert len(events) == 1
    assert events[0].id == "evt_old"
    assert events[0].learner_id == "local_default"
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2


def test_reducer_does_not_treat_chat_exposure_as_mastery():
    events = [
        LearningEvent(
            id="evt_exposure",
            event_type="concept_exposure",
            book_name="demo",
            concept_names=["压阻效应"],
        ),
    ]

    state = reduce_learning_events(events, learner_id="local_default", book_name="demo")
    concept = state["concept_states"]["压阻效应"]

    assert concept["status"] == "exposed"
    assert concept["mastery_band"] == "unknown"
    assert concept["graded_attempt_count"] == 0


def test_reducer_uses_scored_evidence_and_can_rebuild():
    events = [
        LearningEvent(
            id="evt_goal", event_type="goal_created", book_name="demo",
            chapter_id="chapter_004", conversation_id="conv-a",
            payload={"goal_id": "goal-1", "target_id": "chapter_004", "chapter_name": "第四章"},
        ),
        LearningEvent(
            id="evt_unit", event_type="unit_started", book_name="demo",
            chapter_id="chapter_004", unit_id="concept_transverse",
            conversation_id="conv-a", payload={"unit_name": "横向效应"},
        ),
        LearningEvent(
            id="evt_attempt_1", event_type="exercise_practiced", book_name="demo",
            concept_names=["横向效应"], payload={"quality": 4},
        ),
        LearningEvent(
            id="evt_attempt_2", event_type="exercise_practiced", book_name="demo",
            concept_names=["横向效应"], payload={"quality": 5},
        ),
    ]

    first = reduce_learning_events(events, learner_id="local_default", book_name="demo")
    rebuilt = reduce_learning_events(events, learner_id="local_default", book_name="demo")

    assert rebuilt == first
    assert rebuilt["guided_progress"]["current_unit_name"] == "横向效应"
    assert rebuilt["concept_states"]["横向效应"]["mastery_band"] == "stable"
    assert rebuilt["next_action"]["type"] == "resume_current_unit"


def test_learning_state_service_persists_events_and_rebuilds_projection(tmp_path):
    store = LearningEventStore(tmp_path / "learning_events.db")
    service = LearningStateService(progress_root=tmp_path, event_store=store)

    state = service.apply_operation(
        {
            "operation": "create_goal",
            "goal_id": "goal-1",
            "target_type": "chapter",
            "target_id": "chapter_004",
            "target_name": "第四章 力敏传感器",
            "chapter_id": "chapter_004",
            "chapter_name": "第四章 力敏传感器",
        },
        book_name="传感器教材",
        subject="专业课",
        conversation_id="conv-a",
    )
    state = service.apply_operation(
        {
            "operation": "start_unit",
            "chapter_id": "chapter_004",
            "chapter_name": "第四章 力敏传感器",
            "unit_id": "concept_transverse",
            "unit_name": "横向效应",
        },
        book_name="传感器教材",
        subject="专业课",
        conversation_id="conv-a",
    )

    projection = next((tmp_path / "learning_states" / "local_default").glob("*.json"))
    assert projection.exists()
    projection.unlink()
    rebuilt = service.get_state(book_name="传感器教材", subject="专业课")
    assert rebuilt == state
    assert rebuilt["active_goal"]["goal_id"] == "goal-1"


def test_learning_state_rejects_unvalidated_mastery_write(tmp_path):
    service = LearningStateService(
        progress_root=tmp_path,
        event_store=LearningEventStore(tmp_path / "learning_events.db"),
    )

    try:
        service.apply_operation(
            {"operation": "record_attempt", "concept_names": ["导数"], "quality": 9},
            book_name="demo",
        )
    except ValueError as exc:
        assert "quality 0-5" in str(exc)
    else:
        raise AssertionError("invalid mastery evidence was accepted")


def test_resolver_classifies_learning_speech_acts_without_old_topic_inheritance():
    assert classify_learning_speech_act("继续上次的学习") == "resume_learning"
    assert classify_learning_speech_act("复习一下我上次不会的内容") == "review_request"
    assert classify_learning_speech_act("今天先学到这里") == "pause_learning"
    assert classify_learning_speech_act("这个概念我还是不会") == "self_report_weakness"

    trace = build_resolution_trace("什么是极限？", [], initial_state={})
    assert trace["speech_act"] == "ask"
    assert trace["state_before"]["topic"] == ""
    assert trace["resolved_query"] == "什么是极限？"

    resume = build_resolution_trace(
        "继续上次的学习", [], initial_state={"topic": "压阻效应", "intent": "definition"},
    )
    assert resume["speech_act"] == "resume_learning"
    assert resume["state_after"] == resume["state_before"]


def test_bridge_resumes_unique_goal_and_clarifies_multiple_goals(tmp_path):
    store = LearningEventStore(tmp_path / "learning_events.db")
    service = LearningStateService(progress_root=tmp_path, event_store=store)
    for book in ["传感器", "控制工程"]:
        service.apply_operation(
            {
                "operation": "create_goal", "goal_id": f"goal-{book}",
                "target_id": "chapter_001", "target_name": "第一章",
                "chapter_id": "chapter_001", "chapter_name": "第一章",
            },
            book_name=book,
        )

    unique = bridge_learning_request(
        "继续上次的学习", "resume_learning", book_name="传感器", subject="",
        conversation_id="conv-new", service=service,
    )
    multiple = bridge_learning_request(
        "继续上次的学习", "resume_learning", book_name="", subject="",
        conversation_id="conv-new", service=service,
    )

    assert unique.action == "resume"
    assert unique.learning_context["book_name"] == "传感器"
    assert multiple.action == "clarify"
    assert "多个" in multiple.clarification_message


def test_bridge_storage_failure_degrades_without_blocking_ordinary_qa():
    class BrokenService:
        def list_resumable(self, **_kwargs):
            raise OSError("disk unavailable")

    result = bridge_learning_request(
        "继续上次的学习", "resume_learning", book_name="demo", subject="",
        conversation_id="conv-new", service=BrokenService(),
    )

    assert result.action == "none"
    assert "OSError" in result.error


def test_learning_state_api_applies_validated_operation(monkeypatch, tmp_path):
    import backend.api.learning_state as api_module

    store = LearningEventStore(tmp_path / "learning_events.db")
    service = LearningStateService(progress_root=tmp_path, event_store=store)
    monkeypatch.setattr(api_module, "LearningStateService", lambda: service)

    response = TestClient(app).post("/api/learning-state/operations", json={
        "operation": "create_goal",
        "book_name": "demo",
        "subject": "专业课",
        "conversation_id": "conv-api",
        "goal_id": "goal-api",
        "target_type": "chapter",
        "target_id": "chapter_001",
        "target_name": "第一章",
        "chapter_id": "chapter_001",
        "chapter_name": "第一章",
    })

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["active_goal"]["goal_id"] == "goal-api"
    assert data["guided_progress"]["chapter_id"] == "chapter_001"


def test_learning_state_api_rejects_arbitrary_state_write(monkeypatch, tmp_path):
    import backend.api.learning_state as api_module

    service = LearningStateService(
        progress_root=tmp_path,
        event_store=LearningEventStore(tmp_path / "learning_events.db"),
    )
    monkeypatch.setattr(api_module, "LearningStateService", lambda: service)

    response = TestClient(app).post("/api/learning-state/operations", json={
        "operation": "set_mastery",
        "book_name": "demo",
        "concept_names": ["导数"],
        "quality": 5,
    })

    assert response.status_code == 400
    assert "unsupported learning operation" in response.json()["detail"]


def test_recovered_learning_scope_overrides_new_chat_placeholder_scope():
    trace = {
        "learning_bridge": {
            "learning_context": {"book_name": "传感器教材", "subject": "专业课"},
        },
    }

    assert _scope_from_learning_context("", "数学", trace) == ("传感器教材", "专业课")
