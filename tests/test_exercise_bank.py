import sqlite3

import pytest

from fastapi.testclient import TestClient

from backend.api import exercises
from backend.main import app
from memory.exercise_bank import ExerciseBank, ExerciseRecord
from memory.mistake_book import MistakeBook, MistakeRecord


def test_exercise_bank_crud_practice_and_stats(tmp_path):
    bank = ExerciseBank(tmp_path / "exercises.db")
    rid = bank.add(
        ExerciseRecord(
            question_text="求导 $x^2$",
            answer="$2x$",
            explanation="幂函数求导",
            subject="数学",
            tags=["导数"],
            question_type="计算题",
            status="new",
        )
    )

    loaded = bank.get(rid)
    assert loaded is not None
    assert loaded.question_text == "求导 $x^2$"
    assert bank.list_all(tag="导数")[0].id == rid

    practiced = bank.record_practice(rid, user_answer="$2x$", quality=5)
    assert practiced is not None
    assert practiced.status == "mastered"
    assert practiced.practice_count == 1
    assert practiced.practice_history[0]["user_answer"] == "$2x$"
    assert bank.stats()["by_status"]["mastered"] == 1


def test_exercises_api_add_list_status_practice_and_import_mistake(monkeypatch, tmp_path):
    bank = ExerciseBank(tmp_path / "api_exercises.db")
    mistake_book = MistakeBook(tmp_path / "mistakes.db")
    mistake_id = mistake_book.add(
        MistakeRecord(
            question_text="错题：求 $x^2$ 的导数",
            correct_answer="$2x$",
            explanation="使用幂函数求导公式。",
            subject="数学",
            tags=["导数"],
            mistake_type=["计算错误"],
        )
    )

    monkeypatch.setattr(exercises, "_bank", lambda book_name="default": bank)
    monkeypatch.setattr(exercises, "get_mistake_book", lambda book_name="default", data_dir="": mistake_book)
    client = TestClient(app)

    add_res = client.post(
        "/api/exercises/add",
        json={
            "question_text": "手工题：求极限",
            "answer": "1",
            "subject": "数学",
            "tags": "极限",
            "question_type": "填空题",
        },
    ).json()
    assert add_res["success"] is True
    exercise_id = add_res["id"]

    list_res = client.post("/api/exercises/list", json={"search_kw": "极限"}).json()
    assert list_res["success"] is True
    assert list_res["data"][0]["id"] == exercise_id

    status_res = client.post("/api/exercises/status", json={"id": exercise_id, "status": "mastered"}).json()
    assert status_res["success"] is True
    assert status_res["data"]["status"] == "mastered"

    practice_res = client.post(
        "/api/exercises/practice",
        json={"id": exercise_id, "user_answer": "不会", "quality": 1, "add_to_mistake": True},
    ).json()
    assert practice_res["success"] is True
    assert practice_res["data"]["status"] == "needs_review"
    assert practice_res["data"]["practice_count"] == 1
    assert practice_res["mistake_id"]
    assert mistake_book.get(practice_res["mistake_id"]).user_answer == "不会"

    to_mistake_res = client.post(
        "/api/exercises/to-mistake",
        json={"id": exercise_id, "user_answer": "还是不会", "mistake_type": ["概念不清"]},
    ).json()
    assert to_mistake_res["success"] is True
    assert to_mistake_res["id"]

    import_res = client.post("/api/exercises/from-mistake", json={"mistake_id": mistake_id}).json()
    assert import_res["success"] is True
    assert import_res["data"]["origin_type"] == "mistake"
    assert import_res["data"]["origin_id"] == mistake_id

    duplicate_res = client.post("/api/exercises/from-mistake", json={"mistake_id": mistake_id}).json()
    assert duplicate_res["success"] is True
    assert duplicate_res["id"] == import_res["id"]


def test_exercise_subject_hierarchy_filters_and_stats(tmp_path):
    bank = ExerciseBank(tmp_path / "exercises.db")
    high_math = ExerciseRecord(question_text="q1", subject="\u6570\u5b66/\u9ad8\u6570", status="new")
    linear = ExerciseRecord(question_text="q2", subject="\u6570\u5b66/\u7ebf\u4ee3", status="needs_review")
    english = ExerciseRecord(question_text="q3", subject="\u82f1\u8bed/\u9605\u8bfb", status="new")
    for record in [high_math, linear, english]:
        bank.add(record)

    assert {r.id for r in bank.list_all(subject="\u6570\u5b66")} == {high_math.id, linear.id}
    assert {r.id for r in bank.list_all(subject="\u6570\u5b66/\u9ad8\u6570")} == {high_math.id}
    stats = bank.stats(subject="\u6570\u5b66")
    assert stats["total"] == 2
    assert stats["by_status"]["needs_review"] == 1


def test_exercise_answer_job_runs_after_request_returns(monkeypatch, tmp_path):
    import time
    from backend.job_manager import JobManager
    from backend.schemas import ExerciseAnswerGenerateRequest

    bank = ExerciseBank(tmp_path / "answer_jobs_exercises.db")
    exercise_id = bank.add(ExerciseRecord(question_text="解释霍尔效应", subject="专业课/传感器"))
    jobs = JobManager(tmp_path / "answer_jobs.sqlite3")
    monkeypatch.setattr(exercises, "_bank", lambda book_name="default": bank)
    monkeypatch.setattr(exercises, "get_job_manager", lambda: jobs)
    monkeypatch.setattr(
        exercises,
        "generate_exercise_answer",
        lambda req, book_name="default": {
            "success": True,
            "message": "draft ready",
            "data": {"answer": "教材答案", "evidence_count": 2},
        },
    )

    created = exercises.create_exercise_answer_job(
        ExerciseAnswerGenerateRequest(id=exercise_id),
        book_name="传感器短书",
    )
    assert created["success"] is True
    job_id = created["job_id"]

    deadline = time.time() + 3
    job = jobs.get_job(job_id)
    while job and job["status"] not in {"completed", "failed"} and time.time() < deadline:
        time.sleep(0.02)
        job = jobs.get_job(job_id)

    assert job is not None
    assert job["status"] == "completed"
    assert job["result"]["answer"] == "教材答案"
    assert exercises.latest_exercise_answer_job(exercise_id, "传感器短书")["data"]["id"] == job_id


def test_import_batch_skips_duplicates_and_can_rollback(tmp_path):
    bank = ExerciseBank(tmp_path / "batch_exercises.db")
    existing = ExerciseRecord(question_text="求函数 x^2 的导数", subject="数学")
    bank.add(existing)

    duplicate = ExerciseRecord(question_text=" 求函数  x^2 的导数 ", subject="数学", origin_id="c1")
    fresh = ExerciseRecord(question_text="计算矩阵 A 的行列式", subject="数学", origin_id="c2")
    batch = bank.add_batch([duplicate, fresh], source_label="测试导入")

    assert batch["exercise_ids"] == [fresh.id]
    assert batch["skipped"] == [{"origin_id": "c1", "duplicate_of": existing.id}]
    assert bank.get(fresh.id) is not None
    assert bank.list_import_batches()[0]["source_label"] == "测试导入"

    rolled_back = bank.rollback_import_batch(batch["id"])
    assert rolled_back is not None
    assert rolled_back["status"] == "rolled_back"
    assert bank.get(fresh.id) is None
    assert bank.get(existing.id) is not None


def test_practice_session_persists_progress_pause_resume_and_summary(tmp_path):
    db_path = tmp_path / "session_exercises.db"
    bank = ExerciseBank(db_path)
    first = ExerciseRecord(question_text="题目一", subject="数学", status="needs_review")
    second = ExerciseRecord(question_text="题目二", subject="数学", status="new")
    bank.add(first)
    bank.add(second)

    session = bank.create_practice_session(subject="数学", limit=2)
    assert session.exercise_ids == [first.id, second.id]
    assert bank.current_session_record(session).id == first.id

    paused = bank.set_practice_session_status(session.id, "paused")
    assert paused.status == "paused"
    resumed = bank.set_practice_session_status(session.id, "active")
    assert resumed.status == "active"

    progressed, practiced = bank.record_session_answer(
        session.id,
        exercise_id=first.id,
        user_answer="不会",
        quality=1,
    )
    assert practiced.status == "needs_review"
    assert progressed.current_index == 1
    assert bank.current_session_record(progressed).id == second.id

    completed, _ = bank.record_session_answer(
        session.id,
        exercise_id=second.id,
        user_answer="会",
        quality=5,
    )
    assert completed.status == "completed"
    assert completed.summary()["answered"] == 2
    assert completed.summary()["struggling"] == 1

    reloaded = ExerciseBank(db_path).get_practice_session(session.id)
    assert reloaded is not None
    assert reloaded.status == "completed"
    assert reloaded.current_index == 2


def test_practice_session_api_advances_and_import_batch_api_rolls_back(monkeypatch, tmp_path):
    bank = ExerciseBank(tmp_path / "session_api.db")
    mistake_book = MistakeBook(tmp_path / "session_mistakes.db")
    exercise = ExerciseRecord(question_text="会话题目", subject="数学")
    bank.add(exercise)
    monkeypatch.setattr(exercises, "_bank", lambda book_name="default": bank)
    monkeypatch.setattr(exercises, "get_mistake_book", lambda book_name="default", data_dir="": mistake_book)
    client = TestClient(app)

    created = client.post(
        "/api/exercises/practice-sessions",
        json={"subject": "数学", "limit": 1, "shuffle": False},
    ).json()
    assert created["success"] is True
    session_id = created["data"]["id"]
    assert created["data"]["current_exercise"]["id"] == exercise.id

    answered = client.post(
        f"/api/exercises/practice-sessions/{session_id}/answer",
        json={"exercise_id": exercise.id, "user_answer": "不会", "quality": 1, "add_to_mistake": True},
    ).json()
    assert answered["success"] is True
    assert answered["data"]["status"] == "completed"
    assert answered["data"]["summary"]["answered"] == 1
    assert answered["mistake_id"]

    imported = client.post(
        "/api/exercises/batch-add",
        json={"source_label": "API 批次", "exercises": [{"question_text": "新导入题"}]},
    ).json()
    assert imported["success"] is True
    assert imported["batch_id"]
    rolled_back = client.post(
        "/api/exercises/import-batches/rollback",
        json={"batch_id": imported["batch_id"]},
    ).json()
    assert rolled_back["success"] is True
    assert rolled_back["data"]["status"] == "rolled_back"


def test_practice_session_answer_replay_is_idempotent(tmp_path):
    bank = ExerciseBank(tmp_path / "idempotent_session.db")
    exercise = ExerciseRecord(question_text="\u5e42\u51fd\u6570\u6c42\u5bfc", subject="\u6570\u5b66")
    bank.add(exercise)
    session = bank.create_practice_session(subject="\u6570\u5b66", limit=1)

    first_session, first_record = bank.record_session_answer(
        session.id, exercise_id=exercise.id, user_answer="2x", quality=5
    )
    replayed_session, replayed_record = bank.record_session_answer(
        session.id, exercise_id=exercise.id, user_answer="different retry", quality=0
    )

    assert first_session.status == "completed"
    assert replayed_session.results == first_session.results
    assert first_record.practice_count == 1
    assert replayed_record.practice_count == 1
    assert bank.get(exercise.id).practice_count == 1


def test_practice_session_rolls_back_exercise_when_session_update_fails(tmp_path):
    bank = ExerciseBank(tmp_path / "atomic_session.db")
    exercise = ExerciseRecord(question_text="\u539f\u5b50\u6027\u6d4b\u8bd5", subject="\u6570\u5b66")
    bank.add(exercise)
    session = bank.create_practice_session(subject="\u6570\u5b66", limit=1)
    with bank.store._connect() as conn:
        conn.execute(
            """
            CREATE TRIGGER fail_session_progress
            BEFORE UPDATE ON exercise_practice_sessions
            BEGIN
                SELECT RAISE(ABORT, 'session write failed');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="session write failed"):
        bank.record_session_answer(session.id, exercise_id=exercise.id, quality=5)

    assert bank.get(exercise.id).practice_count == 0
    persisted = bank.get_practice_session(session.id)
    assert persisted.current_index == 0
    assert persisted.results == {}


def test_practice_session_api_retry_reuses_same_mistake(monkeypatch, tmp_path):
    bank = ExerciseBank(tmp_path / "retry_session.db")
    mistake_book = MistakeBook(tmp_path / "retry_mistakes.db")
    exercise = ExerciseRecord(question_text="\u91cd\u8bd5\u9898\u76ee", subject="\u6570\u5b66")
    bank.add(exercise)
    monkeypatch.setattr(exercises, "_bank", lambda book_name="default": bank)
    monkeypatch.setattr(exercises, "get_mistake_book", lambda book_name="default", data_dir="": mistake_book)
    client = TestClient(app)
    session = bank.create_practice_session(subject="\u6570\u5b66", limit=1)
    payload = {
        "exercise_id": exercise.id,
        "user_answer": "\u4e0d\u4f1a",
        "quality": 1,
        "add_to_mistake": True,
    }

    first = client.post(f"/api/exercises/practice-sessions/{session.id}/answer", json=payload).json()
    replayed = client.post(f"/api/exercises/practice-sessions/{session.id}/answer", json=payload).json()

    assert first["success"] is True
    assert replayed["success"] is True
    assert replayed["mistake_id"] == first["mistake_id"]
    assert bank.get(exercise.id).practice_count == 1
    assert len(mistake_book.list_all(limit=10)) == 1


def test_practice_answer_without_mistake_does_not_initialize_mistake_book(monkeypatch, tmp_path):
    bank = ExerciseBank(tmp_path / "lazy_provider.db")
    exercise = ExerciseRecord(question_text="普通作答不依赖错题库", subject="数学")
    bank.add(exercise)
    session = bank.create_practice_session(subject="数学", limit=1)
    monkeypatch.setattr(exercises, "_bank", lambda book_name="default": bank)

    def fail_provider(*args, **kwargs):
        raise RuntimeError("mistake database unavailable")

    monkeypatch.setattr(exercises, "get_mistake_book", fail_provider)
    response = TestClient(app).post(
        f"/api/exercises/practice-sessions/{session.id}/answer",
        json={
            "exercise_id": exercise.id,
            "user_answer": "已完成",
            "quality": 4,
            "add_to_mistake": False,
        },
    ).json()

    assert response["success"] is True
    assert response["data"]["status"] == "completed"
    assert response["mistake_id"] == ""
