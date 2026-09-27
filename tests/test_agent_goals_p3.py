from __future__ import annotations

import pytest

from backend.services.goals.service import GoalService
from backend.services.goals.store import GoalConflict, GoalStore, legacy_goal_id, legacy_goal_projection
from memory.learning_events import LearningEvent, LearningEventStore


def test_goal_revisions_measurement_and_projection_replay(tmp_path):
    store = GoalStore(tmp_path / "goals.db")
    events = LearningEventStore(tmp_path / "events.db")
    service = GoalService(store, events)
    goal = service.create(learner_id="local_default", title="复习极限", objective="掌握极限题",
                          scope={"subject": "数学", "book_name": "math"},
                          success_criteria=[{"id": "c1", "metric": "review", "target": 3}])
    assert goal["status"] == "draft" and goal["target_date"] is None
    active = service.activate(goal["id"], expected_revision=1)
    assert active["status"] == "active"
    assert service.get_next_action(goal["id"])["reason_codes"] == ["measurement_unknown"]
    measured = service.measure(goal["id"], expected_revision=2,
                               evidence_by_criterion={"c1": ["event-1"]})
    assert measured["status"] == "active"
    assert measured["progress"]["criterion_results"][0]["status"] == "evidence_present_unverified"
    with pytest.raises(GoalConflict):
        service.pause(goal["id"], expected_revision=2)
    service.pause(goal["id"], expected_revision=3)
    service.reconcile_projections(goal["id"])
    service.reconcile_projections(goal["id"])
    records = events.list_recent(book_name="math", limit=20)
    assert sum(item.event_type == "goal_created" for item in records) == 1
    assert sum(item.event_type == "goal_paused" for item in records) == 1
    store.link(goal["id"], task_id="task-1", run_id="run-1")
    assert store.links(goal["id"])[0]["task_id"] == "task-1"
    assert GoalStore(tmp_path / "goals.db").get(goal["id"])["revision"] == 4


def test_legacy_mapping_does_not_invent_objective_or_criteria():
    event = LearningEvent(id="old-event", event_type="goal_created", book_name="math")
    one = legacy_goal_projection(event)
    assert one["id"] == legacy_goal_id("old-event")
    assert one["objective"] is None and one["success_criteria"] is None
    assert "objective" in one["progress"]["unknowns"]
