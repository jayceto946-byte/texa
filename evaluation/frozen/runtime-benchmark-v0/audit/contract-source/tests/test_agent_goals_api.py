from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.goals import get_goal_service, router
from backend.services.goals.service import GoalService
from backend.services.goals.store import GoalStore


def test_goal_api_revision_gate_and_manual_measurement(tmp_path):
    service = GoalService(GoalStore(tmp_path / "goals.db"))
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_goal_service] = lambda: service
    client = TestClient(app)
    created = client.post("/api/goals", json={"title": "复习极限", "objective": "掌握极限",
        "success_criteria": [{"id": "c1", "target": 3}]}).json()["data"]
    path = f"/api/goals/{created['id']}"
    assert client.get("/api/goals").json()["data"][0]["id"] == created["id"]
    assert client.post(path + "/commands", json={"operation": "activate", "expected_revision": 1}).status_code == 200
    assert client.post(path + "/commands", json={"operation": "pause", "expected_revision": 1}).status_code == 409
    assert client.post(path + "/commands", json={"operation": "update", "expected_revision": 2,
        "changes": {"status": "completed"}}).status_code == 400
    measured = client.post(path + "/commands", json={"operation": "measure", "expected_revision": 2,
        "evidence_by_criterion": {"c1": ["event-1"]}}).json()["data"]
    assert measured["status"] == "active"
    assert measured["progress"]["criterion_results"][0]["status"] == "evidence_present_unverified"
    updated = client.post(path + "/commands", json={"operation": "update", "expected_revision": 3,
        "changes": {"objective": "新的学习目标"}}).json()["data"]
    assert updated["progress"]["evidence_refs"] == []
    assert client.get(path).json()["data"]["next_action"]["capability_id"] == "learning.inspect"
    assert client.post("/api/goals", json={"title": "x", "success_criteria": [{"id": "c"}, {"id": "c"}]}).status_code == 400
    assert client.get("/api/goals/missing").status_code == 404


def test_evidence_candidates_are_scoped_and_do_not_expose_event_payload(tmp_path):
    from memory.learning_events import LearningEvent, LearningEventStore
    events = LearningEventStore(tmp_path / "events.db")
    service = GoalService(GoalStore(tmp_path / "goals.db"), events)
    goal = service.create(title="复习", objective="", scope={"book_name": "数学教材"}, learner_id="local_default")
    events.append(LearningEvent(event_type="exercise_practiced", book_name="数学教材", payload={"user_answer": "private answer"}))
    events.append(LearningEvent(event_type="exercise_practiced", book_name="其他教材"))
    options = service.evidence_candidates(goal["id"])
    assert len(options) == 1
    assert options[0]["label"] == "习题作答"
    assert "private answer" not in str(options)
