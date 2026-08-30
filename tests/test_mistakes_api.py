from fastapi.testclient import TestClient

from backend.main import app
from backend.api import mistakes
from memory.mistake_book import MistakeBook
from backend.services.multimodal_bridge import VisualProblemIR
from backend.services.learning_task import LearningTaskStore


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


def test_image_solution_stream_reports_real_activity_steps(monkeypatch, tmp_path):
    store = mistakes.MistakeImageStore(
        images_path=tmp_path / "images",
        allowed_extensions=frozenset({".png"}),
        max_image_bytes=1024 * 1024,
        ocr_max_side=1600,
        ocr_jpeg_quality=86,
        pending_max_age_seconds=3600,
    )
    monkeypatch.setattr(mistakes, "_image_store", store)
    monkeypatch.setattr(
        mistakes, "_ocr_image_with_kimi",
        lambda *_args, **_kwargs: VisualProblemIR(
            problem_text="分析电路", visual_type="circuit",
            entities=[{"id": "R1"}], relations=[{"type": "connected_to"}],
            uncertainties=["Vo 标签较模糊"],
        ),
    )
    monkeypatch.setattr(mistakes, "_iter_visual_solution_chunks", lambda *_args, **_kwargs: iter(["正式", "讲解"]))
    monkeypatch.setattr(mistakes, "_link_mistake_concepts", lambda *_args, **_kwargs: [])

    client = TestClient(app)
    response = client.post(
        "/api/mistakes/solve-image-stream",
        files={"file": ("problem.png", b"image", "image/png")},
        data={"question": "为什么？", "subject": "电路"},
    )

    assert response.status_code == 200
    events = [
        __import__("json").loads(line[6:])
        for line in response.text.splitlines() if line.startswith("data: ")
    ]
    labels = [event.get("activity", {}).get("label") for event in events]
    assert "读取题目图片" in labels
    assert "识图模型解析图片" in labels
    assert "综合题干与视觉关系" in labels
    assert "生成答案" in labels
    generate_events = [event for event in events if event["stage"] == "generate"]
    assert [event.get("chunk") for event in generate_events[:2]] == ["正式", "讲解"]
    assert generate_events[-1]["done"] is True
    assert events[-1]["stage"] == "done"
    assert events[-1]["result"]["explanation"] == "正式讲解"


def test_image_solution_waits_for_blocking_required_input(monkeypatch, tmp_path):
    store = mistakes.MistakeImageStore(
        images_path=tmp_path / "images", allowed_extensions=frozenset({".png"}),
        max_image_bytes=1024 * 1024, ocr_max_side=1600, ocr_jpeg_quality=86,
        pending_max_age_seconds=3600,
    )
    task_store = LearningTaskStore(tmp_path / "progress")
    monkeypatch.setattr(mistakes, "_image_store", store)
    monkeypatch.setattr(mistakes, "get_learning_task_store", lambda: task_store)
    monkeypatch.setattr(mistakes, "_ocr_image_with_kimi", lambda *_args, **_kwargs: VisualProblemIR(
        problem_text="第 4 问反查温度",
        required_inputs=[{
            "type": "reference_table", "name": "E 型热电偶分度表",
            "reason": "第 4 问需要反查温度", "affects": ["final_numeric_answer"], "blocking": True,
        }],
    ))
    monkeypatch.setattr(mistakes, "_iter_visual_solution_chunks", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("reasoning must not run")))

    response = TestClient(app).post(
        "/api/mistakes/solve-image-stream",
        files={"file": ("problem.png", b"image", "image/png")},
        data={"question": "计算第 4 问", "conversation_id": "conv-gate", "turn_id": "turn-gate"},
    )
    events = [
        __import__("json").loads(line[6:])
        for line in response.text.splitlines() if line.startswith("data: ")
    ]

    assert events[-1]["stage"] == "waiting_for_input"
    task = events[-1]["result"]["learning_task"]
    assert task["status"] == "waiting_for_input"
    assert task["terminal"] is False
    assert task["interruptible"] is False
    assert task["resumable"] is False
    assert task["input_action_required"] is True
    assert task["conversation_id"] == "conv-gate"
    assert task["required_inputs"][0]["name"] == "E 型热电偶分度表"


def test_visual_task_resume_parses_only_supplement_and_completes(monkeypatch, tmp_path):
    store = mistakes.MistakeImageStore(
        images_path=tmp_path / "images", allowed_extensions=frozenset({".png"}),
        max_image_bytes=1024 * 1024, ocr_max_side=1600, ocr_jpeg_quality=86,
        pending_max_age_seconds=3600,
    )
    task_store = LearningTaskStore(tmp_path / "progress")
    original_path = store.save_upload(type("Upload", (), {
        "filename": "original.png", "content_type": "image/png",
        "file": __import__("io").BytesIO(b"original"),
    })())
    task = task_store.create(
        task_type="visual_qa", goal="完成温度反查", status="waiting_for_input",
        required_inputs=[{
            "type": "reference_table", "name": "E 型热电偶分度表", "reason": "反查温度",
            "affects": ["final_numeric_answer"], "blocking": True,
        }],
        artifacts={
            "image_path": str(original_path),
            "visual_ir": VisualProblemIR(problem_text="原题").to_dict(),
            "supplemental_visual_irs": [], "question": "求温度", "book_name": "default",
        },
    )
    calls = []
    monkeypatch.setattr(mistakes, "_image_store", store)
    monkeypatch.setattr(mistakes, "get_learning_task_store", lambda: task_store)
    monkeypatch.setattr(mistakes, "_ocr_image_with_kimi", lambda path, **_kwargs: calls.append(path) or VisualProblemIR(
        problem_text="E 型热电偶分度表：5mV 对应 120°C", visual_type="chart",
    ))
    monkeypatch.setattr(mistakes, "_iter_visual_solution_chunks", lambda *_args, **_kwargs: iter(["精确答案 120°C"]))
    monkeypatch.setattr(mistakes, "_link_mistake_concepts", lambda *_args, **_kwargs: [])

    response = TestClient(app).post(
        f"/api/mistakes/visual-tasks/{task.id}/resume-stream",
        files={"file": ("table.png", b"table", "image/png")},
        data={"action": "provide_input"},
    )
    events = [
        __import__("json").loads(line[6:])
        for line in response.text.splitlines() if line.startswith("data: ")
    ]

    assert len(calls) == 1
    assert calls[0].name != original_path.name
    assert events[-1]["stage"] == "done"
    assert events[-1]["result"]["learning_task"]["status"] == "completed"
    assert events[-1]["result"]["explanation"] == "精确答案 120°C"
