from fastapi.testclient import TestClient

from backend.main import app
from backend.api import mistakes
from memory.mistake_book import MistakeBook
from backend.services.multimodal_bridge import VisualProblemIR


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
