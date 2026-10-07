import io
import json
from pathlib import Path
import pytest

from fastapi.testclient import TestClient

from backend.main import app
from backend.api import mistakes
from backend.services.execution_events import (
    EXECUTION_EVENT_TYPES,
    EXECUTION_SSE_FORBIDDEN_LIFECYCLE_FIELDS,
    validate_execution_event,
)
from backend.services.multimodal_bridge import VisualProblemIR
from backend.services.learning_task import LearningTaskStore
from memory.mistake_book import MistakeBook, MistakeRecord


def test_mistakes_api_add_persists_explanation(monkeypatch, tmp_path):
    book = MistakeBook(tmp_path / "api_mistakes.db")
    monkeypatch.setattr(mistakes, "_mb", lambda book_name="default": book)

    def fake_concepts(record, explanation="", book_name="default"):
        record.linked_concepts = [{"name": "limit", "concept_id": "c-limit", "confidence": 1.0, "source": "mistake_llm"}]
        return record.linked_concepts

    monkeypatch.setattr(mistakes, "_persist_mistake_concepts", fake_concepts)
    client = TestClient(app)

    payload = {
        "question_text": "题干 $x$",
        "subject": "数学",
        "tags": "极限",
        "mistake_type": ["概念不清"],
        "difficulty": 4,
        "ocr_text": "OCR 题干",
        "explanation": "保存的解答 $x+1$",
    }
    add_res = client.post("/api/mistakes/add", json=payload).json()
    assert add_res["success"] is True
    assert add_res["data"]["explanation"] == "保存的解答 $x+1$"

    list_res = client.post("/api/mistakes/list", json={"limit": 10}).json()
    assert list_res["success"] is True
    assert list_res["data"][0]["explanation"] == "保存的解答 $x+1$"


def _stream_events(response) -> list[dict]:
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def _configure_visual_stream(
    monkeypatch,
    tmp_path,
    *,
    visual_ir: VisualProblemIR,
    chunks: list[str] | None = None,
    verification: dict | None = None,
):
    store = mistakes.MistakeImageStore(
        images_path=tmp_path / "images",
        allowed_extensions=frozenset({".png"}),
        max_image_bytes=1024 * 1024,
        ocr_max_side=1600,
        ocr_jpeg_quality=86,
        pending_max_age_seconds=3600,
    )
    task_store = LearningTaskStore(tmp_path / "progress")
    monkeypatch.setattr(mistakes, "_image_store", store)
    monkeypatch.setattr(mistakes, "get_learning_task_store", lambda: task_store)
    monkeypatch.setattr(mistakes, "_ocr_image_with_kimi", lambda *_args, **_kwargs: visual_ir)
    monkeypatch.setattr(
        mistakes, "_iter_visual_solution_chunks",
        lambda *_args, **_kwargs: iter(chunks or ["正式", "讲解"]),
    )
    monkeypatch.setattr(mistakes, "_link_mistake_concepts", lambda *_args, **_kwargs: [])
    result = verification or {"status": "passed", "passed": True, "checks": []}
    monkeypatch.setattr(
        mistakes, "_verify_visual_answer",
        lambda answer, **_kwargs: (answer, dict(result)),
    )
    return store, task_store


def _assert_canonical_stream(events: list[dict], *, task_bound: bool = True) -> list[dict]:
    for envelope in events:
        assert set(envelope).isdisjoint(EXECUTION_SSE_FORBIDDEN_LIFECYCLE_FIELDS)
    execution_events = [event["execution_event"] for event in events]
    assert execution_events
    for event in execution_events:
        validate_execution_event(event)
        assert event["type"] in EXECUTION_EVENT_TYPES
    assert [event["seq"] for event in execution_events] == list(
        range(1, len(execution_events) + 1)
    )
    if task_bound:
        identities = {(event["task_id"], event["run_id"]) for event in execution_events}
        assert len(identities) == 1
        task_id, run_id = identities.pop()
        assert task_id
        assert run_id
        assert all(event["conversation_id"] for event in execution_events)
        assert all(event["turn_id"] for event in execution_events)
    for event in execution_events:
        if event["type"] == "output_delta":
            assert set(event["payload"]) == {"text", "replace"}
            assert isinstance(event["payload"]["text"], str)
            assert isinstance(event["payload"]["replace"], bool)
    terminal_indexes = [
        index for index, event in enumerate(execution_events)
        if event["type"] in {"final", "error"}
    ]
    assert len(terminal_indexes) <= 1
    if terminal_indexes:
        assert terminal_indexes == [len(execution_events) - 1]
    return execution_events


def _create_waiting_visual_task(task_store, image_store, *, active_run_id: str = "run-old"):
    original_path = image_store.save_upload(type("Upload", (), {
        "filename": "original.png",
        "content_type": "image/png",
        "file": io.BytesIO(b"original"),
    })())
    return task_store.create(
        task_type="visual_qa",
        goal="完成温度反查",
        status="waiting_for_input",
        conversation_id="conv-mistake-resume",
        turn_id="turn-mistake-resume",
        required_inputs=[{
            "type": "reference_table",
            "name": "E 型热电偶分度表",
            "reason": "反查温度",
            "affects": ["final_numeric_answer"],
            "blocking": True,
        }],
        artifacts={
            "image_path": str(original_path),
            "visual_ir": VisualProblemIR(problem_text="原题").to_dict(),
            "supplemental_visual_irs": [],
            "question": "求温度",
            "book_name": "default",
            "active_run_id": active_run_id,
        },
    )


def test_image_solution_stream_uses_canonical_events_and_completes(monkeypatch, tmp_path):
    _image_store, task_store = _configure_visual_stream(
        monkeypatch,
        tmp_path,
        visual_ir=VisualProblemIR(
            problem_text="分析电路",
            visual_type="circuit",
            entities=[{"id": "R1"}],
            relations=[{"type": "connected_to"}],
            uncertainties=["Vo 标签较模糊"],
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/api/mistakes/solve-image-stream",
        files={"file": ("problem.png", b"image", "image/png")},
        data={
            "question": "为什么？",
            "subject": "电路",
            "conversation_id": "conv-mistake",
            "turn_id": "turn-mistake",
        },
    )

    assert response.status_code == 200
    events = _stream_events(response)
    execution_events = _assert_canonical_stream(events)
    labels = [event["execution_event"]["label"] for event in events]
    assert "读取题目图片" in labels
    assert "识图模型解析图片" in labels
    assert "综合题干与视觉关系" in labels
    assert "生成答案" in labels
    generate_events = [
        event["execution_event"] for event in events
        if event["execution_event"]["type"] == "output_delta"
    ]
    assert [event["payload"]["text"] for event in generate_events[:2]] == ["正式", "讲解"]
    assert events[-1]["execution_event"]["type"] == "final"
    assert events[-1]["result"]["explanation"] == "正式讲解"
    task = events[-1]["result"]["learning_task"]
    assert task["status"] == "completed"
    assert execution_events[-1]["type"] == "final"
    assert execution_events[-1]["payload"]["task_status"] == task["status"]
    assert task_store.get(task["id"]).status == "completed"


def test_image_solution_waits_for_blocking_required_input(monkeypatch, tmp_path):
    _store, task_store = _configure_visual_stream(
        monkeypatch,
        tmp_path,
        visual_ir=VisualProblemIR(
            problem_text="第 4 问反查温度",
            required_inputs=[{
                "type": "reference_table",
                "name": "E 型热电偶分度表",
                "reason": "第 4 问需要反查温度",
                "affects": ["final_numeric_answer"],
                "blocking": True,
            }],
        ),
    )
    monkeypatch.setattr(mistakes, "_iter_visual_solution_chunks", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("reasoning must not run")))

    response = TestClient(app).post(
        "/api/mistakes/solve-image-stream",
        files={"file": ("problem.png", b"image", "image/png")},
        data={"question": "计算第 4 问", "conversation_id": "conv-gate", "turn_id": "turn-gate"},
    )
    events = _stream_events(response)
    execution_events = _assert_canonical_stream(events)

    assert events[-1]["execution_event"]["type"] == "state_transition"
    assert execution_events[-1]["type"] == "state_transition"
    assert not any(event["type"] in {"final", "error"} for event in execution_events)
    assert execution_events[-1]["payload"] == {
        "task_status_before": "running",
        "task_status_after": "waiting_for_input",
    }
    task = events[-1]["result"]["learning_task"]
    assert task["status"] == "waiting_for_input"
    assert task["terminal"] is False
    assert task["interruptible"] is False
    assert task["resumable"] is False
    assert task["input_action_required"] is True
    assert task["conversation_id"] == "conv-gate"
    assert task["required_inputs"][0]["name"] == "E 型热电偶分度表"
    assert task_store.get(task["id"]).status == "waiting_for_input"


def test_visual_task_resume_parses_only_supplement_and_completes(monkeypatch, tmp_path):
    store = mistakes.MistakeImageStore(
        images_path=tmp_path / "images", allowed_extensions=frozenset({".png"}),
        max_image_bytes=1024 * 1024, ocr_max_side=1600, ocr_jpeg_quality=86,
        pending_max_age_seconds=3600,
    )
    task_store = LearningTaskStore(tmp_path / "progress")
    task = _create_waiting_visual_task(task_store, store)
    original_path = task.artifacts["image_path"]
    calls = []
    monkeypatch.setattr(mistakes, "_image_store", store)
    monkeypatch.setattr(mistakes, "get_learning_task_store", lambda: task_store)
    monkeypatch.setattr(mistakes, "_ocr_image_with_kimi", lambda path, **_kwargs: calls.append(path) or VisualProblemIR(
        problem_text="E 型热电偶分度表：5mV 对应 120°C", visual_type="chart",
    ))
    monkeypatch.setattr(mistakes, "_iter_visual_solution_chunks", lambda *_args, **_kwargs: iter(["精确答案 120°C"]))
    monkeypatch.setattr(mistakes, "_link_mistake_concepts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        mistakes,
        "_verify_visual_answer",
        lambda answer, **_kwargs: (answer, {"status": "passed", "passed": True, "checks": []}),
    )

    response = TestClient(app).post(
        f"/api/mistakes/visual-tasks/{task.id}/resume-stream",
        files={"file": ("table.png", b"table", "image/png")},
        data={"action": "provide_input"},
    )
    events = _stream_events(response)
    execution_events = _assert_canonical_stream(events)

    assert len(calls) == 1
    assert calls[0].name != __import__("pathlib").Path(original_path).name
    assert events[-1]["execution_event"]["type"] == "final"
    assert events[-1]["result"]["learning_task"]["status"] == "completed"
    assert events[-1]["result"]["explanation"] == "精确答案 120°C"
    run_id = execution_events[0]["run_id"]
    assert run_id
    assert run_id != "run-old"
    assert task_store.get(task.id).artifacts["active_run_id"] == run_id
    assert execution_events[0]["type"] == "state_transition"
    assert execution_events[0]["payload"] == {
        "task_status_before": "waiting_for_input",
        "task_status_after": "running",
    }
    assert execution_events[-1]["payload"]["task_status"] == "completed"


def test_visual_task_method_only_resume_finishes_degraded(monkeypatch, tmp_path):
    store, task_store = _configure_visual_stream(
        monkeypatch,
        tmp_path,
        visual_ir=VisualProblemIR(problem_text="unused"),
        chunks=["只讲方法"],
        verification={"status": "unsupported", "passed": False, "checks": []},
    )
    task = _create_waiting_visual_task(task_store, store)

    response = TestClient(app).post(
        f"/api/mistakes/visual-tasks/{task.id}/resume-stream",
        data={"action": "method_only"},
    )
    events = _stream_events(response)
    execution_events = _assert_canonical_stream(events)

    assert events[-1]["execution_event"]["type"] == "final"
    assert events[-1]["result"]["learning_task"]["status"] == "degraded"
    assert execution_events[-1]["type"] == "final"
    assert execution_events[-1]["payload"]["task_status"] == "degraded"
    assert task_store.get(task.id).status == "degraded"


def test_visual_task_execution_failure_emits_matching_error(monkeypatch, tmp_path):
    store, task_store = _configure_visual_stream(
        monkeypatch,
        tmp_path,
        visual_ir=VisualProblemIR(problem_text="unused"),
    )
    task = _create_waiting_visual_task(task_store, store)
    monkeypatch.setattr(
        mistakes,
        "_iter_visual_solution_chunks",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("generation failed")),
    )

    response = TestClient(app).post(
        f"/api/mistakes/visual-tasks/{task.id}/resume-stream",
        data={"action": "method_only"},
    )
    events = _stream_events(response)
    execution_events = _assert_canonical_stream(events)

    assert events[-1]["execution_event"]["type"] == "error"
    assert execution_events[-1]["type"] == "error"
    assert execution_events[-1]["payload"]["task_status"] == "failed"
    assert task_store.get(task.id).status == "failed"


def test_visual_task_input_parse_failure_returns_to_waiting_without_terminal_event(monkeypatch, tmp_path):
    store = mistakes.MistakeImageStore(
        images_path=tmp_path / "images",
        allowed_extensions=frozenset({".png"}),
        max_image_bytes=1024 * 1024,
        ocr_max_side=1600,
        ocr_jpeg_quality=86,
        pending_max_age_seconds=3600,
    )
    task_store = LearningTaskStore(tmp_path / "progress")
    task = _create_waiting_visual_task(task_store, store)
    monkeypatch.setattr(mistakes, "_image_store", store)
    monkeypatch.setattr(mistakes, "get_learning_task_store", lambda: task_store)
    monkeypatch.setattr(
        mistakes,
        "_ocr_image_with_kimi",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("补充图片不可读")),
    )

    response = TestClient(app).post(
        f"/api/mistakes/visual-tasks/{task.id}/resume-stream",
        files={"file": ("table.png", b"table", "image/png")},
        data={"action": "provide_input"},
    )
    events = _stream_events(response)
    execution_events = _assert_canonical_stream(events)

    assert events[-1]["execution_event"]["type"] == "state_transition"
    assert execution_events[-1]["type"] == "state_transition"
    assert not any(event["type"] in {"final", "error"} for event in execution_events)
    assert task_store.get(task.id).status == "waiting_for_input"


def test_image_solution_failure_emits_matching_error_terminal(monkeypatch, tmp_path):
    _store, task_store = _configure_visual_stream(
        monkeypatch,
        tmp_path,
        visual_ir=VisualProblemIR(problem_text="unused"),
    )
    monkeypatch.setattr(
        mistakes,
        "_ocr_image_with_kimi",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("vision failed")),
    )

    response = TestClient(app).post(
        "/api/mistakes/solve-image-stream",
        files={"file": ("problem.png", b"image", "image/png")},
        data={"conversation_id": "conv-failed", "turn_id": "turn-failed"},
    )
    events = _stream_events(response)
    execution_events = _assert_canonical_stream(events)

    assert events[-1]["execution_event"]["type"] == "error"
    assert execution_events[-1]["type"] == "error"
    assert execution_events[-1]["payload"]["task_status"] == "failed"
    task = events[-1]["learning_task"]
    assert task["status"] == "failed"
    assert task_store.get(task["id"]).status == "failed"


def test_stale_input_resume_cannot_write_or_emit_terminal(monkeypatch, tmp_path):
    store = mistakes.MistakeImageStore(
        images_path=tmp_path / "images",
        allowed_extensions=frozenset({".png"}),
        max_image_bytes=1024 * 1024,
        ocr_max_side=1600,
        ocr_jpeg_quality=86,
        pending_max_age_seconds=3600,
    )
    task_store = LearningTaskStore(tmp_path / "progress")
    task = _create_waiting_visual_task(task_store, store)
    monkeypatch.setattr(mistakes, "_image_store", store)
    monkeypatch.setattr(mistakes, "get_learning_task_store", lambda: task_store)

    def supersede_run(*_args, **_kwargs):
        current = task_store.get(task.id)
        from backend.services.learning_task import interrupt_learning_task, resume_learning_task
        current = interrupt_learning_task(task_store, current, stage="test")
        resume_learning_task(task_store, current, run_id="run-new-owner")
        return VisualProblemIR(problem_text="迟到的补充材料")

    monkeypatch.setattr(mistakes, "_ocr_image_with_kimi", supersede_run)

    response = TestClient(app).post(
        f"/api/mistakes/visual-tasks/{task.id}/resume-stream",
        files={"file": ("table.png", b"table", "image/png")},
        data={"action": "provide_input"},
    )
    events = _stream_events(response)
    execution_events = _assert_canonical_stream(events)
    current = task_store.get(task.id)

    assert current.status == "running"
    assert current.artifacts["active_run_id"] == "run-new-owner"
    assert current.artifacts.get("supplemental_visual_irs") == []
    assert not any(event["type"] in {"final", "error"} for event in execution_events)
    assert all(event["run_id"] != "run-new-owner" for event in execution_events)


def test_superseded_image_run_cannot_import_generated_mistake(monkeypatch, tmp_path):
    _store, task_store = _configure_visual_stream(
        monkeypatch,
        tmp_path,
        visual_ir=VisualProblemIR(problem_text="分析电路"),
        chunks=["答案"],
    )
    imports: list[MistakeRecord] = []

    def supersede_before_write(*_args, **_kwargs):
        task_id = next(task_store.root.glob("task_*.json")).stem
        current = task_store.get(task_id)
        from backend.services.learning_task import interrupt_learning_task, resume_learning_task
        current = interrupt_learning_task(task_store, current, stage="test")
        resume_learning_task(task_store, current, run_id="run-new-owner")
        return []

    monkeypatch.setattr(mistakes, "_link_mistake_concepts", supersede_before_write)
    monkeypatch.setattr(
        mistakes,
        "_mb",
        lambda _book_name="default": type("Book", (), {"add": lambda _self, record: imports.append(record)})(),
    )

    response = TestClient(app).post(
        "/api/mistakes/solve-image-stream",
        files={"file": ("problem.png", b"image", "image/png")},
        data={
            "question": "为什么？",
            "import_to_mistakes": "true",
            "conversation_id": "conv-stale-write",
            "turn_id": "turn-stale-write",
        },
    )
    events = _stream_events(response)
    execution_events = _assert_canonical_stream(events)
    current = task_store.get(execution_events[0]["task_id"])

    assert imports == []
    assert current.artifacts["active_run_id"] == "run-new-owner"
    assert not any(event["type"] in {"final", "error"} for event in execution_events)


def test_resume_rejects_missing_execution_identity(monkeypatch, tmp_path):
    task_store = LearningTaskStore(tmp_path / "progress")
    task = task_store.create(
        task_type="visual_qa",
        goal="legacy",
        status="waiting_for_input",
        required_inputs=[{"blocking": True}],
    )
    monkeypatch.setattr(mistakes, "get_learning_task_store", lambda: task_store)

    response = TestClient(app).post(
        f"/api/mistakes/visual-tasks/{task.id}/resume-stream",
        data={"action": "method_only"},
    )

    assert response.status_code == 409
    assert "execution identity" in response.json()["detail"]
    assert task_store.get(task.id).status == "waiting_for_input"


def test_cached_mistake_stream_projects_only_from_canonical_events(monkeypatch, tmp_path):
    book = MistakeBook(tmp_path / "mistakes.db")
    record = MistakeRecord(
        question_text="求极限",
        subject="数学",
        visual_ir=VisualProblemIR(problem_text="求极限", visual_type="text_only").to_dict(),
    )
    mistake_id = book.add(record)
    monkeypatch.setattr(mistakes, "_mb", lambda book_name="default": book)
    monkeypatch.setattr(mistakes, "_iter_visual_solution_chunks", lambda *_args, **_kwargs: iter(["答案", "完成"]))
    monkeypatch.setattr(mistakes, "_link_mistake_concepts", lambda *_args, **_kwargs: [])

    response = TestClient(app).post(
        "/api/mistakes/solve-cached-stream",
        json={"id": mistake_id, "question": "重新讲解"},
    )
    events = _stream_events(response)
    execution_events = _assert_canonical_stream(events, task_bound=False)

    assert all(event["task_id"] == event["run_id"] == "" for event in execution_events)
    assert events[-1]["execution_event"]["type"] == "final"
    assert events[-1]["result"]["explanation"] == "答案完成"
    assert execution_events[-1]["type"] == "final"
    assert "result" not in execution_events[-1]
    assert "stage" not in execution_events[-1]
    assert "activity" not in execution_events[-1]


@pytest.mark.parametrize("policy,missing", [("exact", False), ("method_only", False), ("exact", True)])
def test_interrupted_visual_resume_preserves_policy_and_input_gate(monkeypatch, tmp_path, policy, missing):
    from backend.services.learning_task import resume_learning_task, interrupt_learning_task
    image_store, task_store = _configure_visual_stream(monkeypatch, tmp_path, visual_ir=VisualProblemIR(problem_text="原题"))
    task = _create_waiting_visual_task(task_store, image_store)
    task = resume_learning_task(task_store, task, run_id="run-before-stop")
    task.artifacts["answer_policy"] = policy
    if not missing:
        task.required_inputs[0]["status"] = "waived" if policy == "method_only" else "provided"
    task_store.save_for_run(task, "run-before-stop")
    interrupt_learning_task(task_store, task, stage="disconnected", expected_run_id="run-before-stop")
    calls = []
    def chunks(_ir, **kwargs):
        calls.append(kwargs["answer_policy"])
        return iter(["继续讲解"])
    monkeypatch.setattr(mistakes, "_iter_visual_solution_chunks", chunks)
    monkeypatch.setattr(mistakes, "_ocr_image_with_kimi", lambda *_a, **_k: pytest.fail("saved IR must be reused"))
    response = TestClient(app).post(f"/api/mistakes/visual-tasks/{task.id}/resume-stream", data={"action": "resume"})
    assert response.status_code == 200
    events = _assert_canonical_stream(_stream_events(response))
    current = task_store.get(task.id)
    assert current.turn_id == task.turn_id
    assert current.artifacts["active_run_id"] != "run-before-stop"
    if missing:
        assert current.status == "waiting_for_input"
        assert calls == []
        assert events[-1]["type"] == "state_transition"
    else:
        assert events[-1]["type"] == "final"
        assert calls == [policy]
        assert current.verification["input_gate"] == ("passed" if policy == "exact" else "degraded_method_only")


def test_visual_interrupt_fences_old_run_and_resume_retries_unfinished_vision(monkeypatch, tmp_path):
    image_store, task_store = _configure_visual_stream(monkeypatch, tmp_path, visual_ir=VisualProblemIR(problem_text="原题"))
    image_path = image_store.save_upload(type("Upload", (), {
        "filename": "original.png", "content_type": "image/png", "file": io.BytesIO(b"original"),
    })())
    task = mistakes._create_visual_learning_task(
        store=task_store, visual_ir=VisualProblemIR(problem_text="用户问题"), image_path=image_path,
        question="用户问题", user_answer="", subject="", tags="", book_name="default", import_to_mistakes=False,
        conversation_id="conv-vision-crash", turn_id="turn-vision-crash", run_id="run-vision", vision_pending=True,
    )
    client = TestClient(app)
    path = f"/api/mistakes/visual-tasks/{task.id}"
    assert client.post(path + "/interrupt", json={"run_id": "stale"}).status_code == 409
    assert task_store.get(task.id).status == "running"
    assert client.post(path + "/interrupt", json={"run_id": "run-vision"}).json()["learning_task"]["resumable"]
    calls = []
    def ocr(path, **_kwargs):
        calls.append(path)
        return VisualProblemIR(problem_text="识别后的完整题目", required_inputs=[{"name": "附表", "blocking": True}])
    monkeypatch.setattr(mistakes, "_ocr_image_with_kimi", ocr)
    response = client.post(path + "/resume-stream", data={"action": "resume"})
    _assert_canonical_stream(_stream_events(response))
    current = task_store.get(task.id)
    assert current.status == "waiting_for_input"
    assert calls == [Path(task.artifacts["image_path"])]
    assert image_path.read_bytes() == calls[0].read_bytes()
    assert current.artifacts["vision_pending"] is False
    assert current.artifacts["visual_ir"]["problem_text"] == "识别后的完整题目"
    assert client.post(path + "/interrupt", json={"run_id": "run-vision"}).status_code == 409


def test_visual_answer_survives_lost_client_and_projection_receipt(monkeypatch, tmp_path):
    from backend import conversation_memory as cm
    monkeypatch.setattr(cm, "CONV_DIR", tmp_path / "conversations")
    _, task_store = _configure_visual_stream(monkeypatch, tmp_path, visual_ir=VisualProblemIR(problem_text="原题"))
    project = task_store.project_outcome
    monkeypatch.setattr(task_store, "project_outcome", lambda *_a, **_k: (_ for _ in ()).throw(OSError("SQLite unavailable")))
    response = TestClient(app).post("/api/mistakes/solve-image-stream",
        files={"file": ("problem.png", b"image", "image/png")},
        data={"question": "讲解原题", "conversation_id": "recover-visual", "turn_id": "turn"})
    events = _stream_events(response)
    assert events[-1]["result"]["persistence_error"]
    task = task_store.get(events[-1]["execution_event"]["task_id"])
    assert task.status == "completed"
    assert task.artifacts["execution_outcome"]["projected"] is False
    monkeypatch.setattr(task_store, "project_outcome", project)
    task_store.recover_unfinished()
    project(task.id)
    messages = cm.load_full_history("recover-visual")
    assert [(m["role"], m["content"]) for m in messages] == [("user", "讲解原题"), ("assistant", "正式讲解")]
    assert messages[-1]["learning_task"]["status"] == "completed"


def test_visual_gate_and_resume_share_one_durable_assistant_message(monkeypatch, tmp_path):
    from backend import conversation_memory as cm
    monkeypatch.setattr(cm, "CONV_DIR", tmp_path / "conversations")
    _, task_store = _configure_visual_stream(monkeypatch, tmp_path,
        visual_ir=VisualProblemIR(problem_text="原题", required_inputs=[{"name": "附表", "blocking": True}]))
    client = TestClient(app)
    response = client.post("/api/mistakes/solve-image-stream",
        files={"file": ("problem.png", b"image", "image/png")},
        data={"conversation_id": "visual-gate", "turn_id": "turn", "question": "原题"})
    task_id = _stream_events(response)[-1]["execution_event"]["task_id"]
    before = cm.load_full_history("visual-gate")
    assert before[-1]["delivery_status"] == "waiting"
    resumed = client.post(f"/api/mistakes/visual-tasks/{task_id}/resume-stream", data={"action": "method_only"})
    assert _stream_events(resumed)[-1]["execution_event"]["type"] == "final"
    task_store.recover_unfinished()
    after = cm.load_full_history("visual-gate")
    assert len(after) == 2 and after[-1]["id"] == before[-1]["id"]
    assert after[-1]["delivery_status"] == "complete"
