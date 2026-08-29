import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backend.main import app
from backend.services.figure_learning import (
    FigureIndexOutOfDateError,
    FigureLearningService,
    NormalizedBBox,
)
from backend.services.learning_task import LearningTaskStore
from backend.services.multimodal_bridge import VisionModelBridge
from evaluation.visual_learning_eval import evaluate_visual_learning_corpus
from ingestion.chapter_splitter import ChapterSplitter
from ingestion.document_ir import (
    CanonicalBook,
    DocumentBlock,
    canonical_book_fingerprint,
    persist_canonical_book,
)


_ACTIVE_FIGURE_INDEXES: dict[str, dict] = {}


@pytest.fixture(autouse=True)
def _active_figure_index(monkeypatch):
    import backend.services.figure_learning as module

    _ACTIVE_FIGURE_INDEXES.clear()
    FigureLearningService._book_cache.clear()
    monkeypatch.setattr(
        module,
        "load_index_manifest",
        lambda book_name: dict((_ACTIVE_FIGURE_INDEXES.get(book_name) or {}).get("manifest") or {}),
    )
    monkeypatch.setattr(
        module,
        "load_book_index",
        lambda book_name: [dict(row) for row in ((_ACTIVE_FIGURE_INDEXES.get(book_name) or {}).get("rows") or [])],
    )
    yield
    FigureLearningService._book_cache.clear()
    _ACTIVE_FIGURE_INDEXES.clear()


def _activate_figure_index(book: CanonicalBook, *, version: str = "figure-index-v1", rows=None) -> list[dict]:
    active_rows = [dict(row) for row in (rows or ChapterSplitter().split_canonical_book(book))]
    canonical_hash = canonical_book_fingerprint(book)
    for row in active_rows:
        row.update({
            "index_version": version,
            "canonical_hash": canonical_hash,
        })
    _ACTIVE_FIGURE_INDEXES[book.book_name] = {
        "manifest": {
            "schema_version": 6,
            "provenance_schema": "texa.provenance/v1",
            "index_version": version,
            "canonical_hash": canonical_hash,
        },
        "rows": active_rows,
    }
    return active_rows


def _figure_book(progress_root: Path, book_name: str = "视觉教材") -> tuple[CanonicalBook, Path]:
    figure_dir = progress_root / book_name / "figures"
    figure_dir.mkdir(parents=True)
    image_path = figure_dir / "figure-1.png"
    Image.new("RGB", (200, 100), (240, 240, 240)).save(image_path)
    content_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
    book = CanonicalBook(
        book_name=book_name,
        source_kind="mineru",
        parser_version="mineru-content-list-v1",
        source_page_count=3,
        blocks=[
            DocumentBlock("h1", "heading", "第一章", ["第一章"], 1, 1, source_kind="mineru"),
            DocumentBlock("before", "paragraph", "图前正文说明。", ["第一章", "结构"], 2, 2, source_kind="mineru"),
            DocumentBlock(
                "figure-1", "figure", "图 1 结构示意图", ["第一章", "结构"], 2, 2,
                bbox=[10, 20, 300, 400], source_file="book_content_list.json", source_kind="mineru",
                attributes={
                    "figure_id": "figure-1", "caption": "图 1 结构示意图",
                    "page_idx": 1, "page_bbox": [10, 20, 300, 400],
                    "bbox_space": "page", "bbox_format": "xyxy", "bbox_units": "mineru_source_units",
                    "asset_relpath": "figures/figure-1.png", "asset_status": "ready",
                    "image_width": 200, "image_height": 100, "content_hash": content_hash,
                },
            ),
            DocumentBlock("after", "paragraph", "图后正文解释连接关系。", ["第一章", "结构"], 2, 2, source_kind="mineru"),
            DocumentBlock("other", "paragraph", "另一章正文。", ["第二章"], 3, 3, source_kind="mineru"),
        ],
    )
    assert persist_canonical_book(book, progress_root=progress_root).valid
    _activate_figure_index(book)
    return book, image_path


def test_figure_service_lists_context_and_controlled_asset(tmp_path):
    _book, image_path = _figure_book(tmp_path)
    service = FigureLearningService(tmp_path)

    listed = service.list_figures("视觉教材")
    assert listed["total"] == 1
    assert listed["items"][0]["caption"] == "图 1 结构示意图"
    assert listed["items"][0]["page"] == 2
    assert service.asset_path("视觉教材", "figure-1") == image_path.resolve()

    context = service.build_context("视觉教材", "figure-1")
    assert [item["block_id"] for item in context.nearby_blocks] == ["before", "after"]
    assert context.related_chunk_ids
    assert all(item["chunk_ids"] for item in context.nearby_blocks)
    assert context.figure["section_path"] == ["第一章", "结构"]
    sources = service.evidence_sources(context)
    assert [item["id"] for item in sources] == ["E1", "E2", "E3"]
    assert sources[0]["figure_id"] == "figure-1"
    assert sources[1]["block_id"] == "before"
    assert sources[1]["text"] == "图前正文说明。"


def test_figure_search_matches_caption_section_and_nearby_text(tmp_path):
    _figure_book(tmp_path)
    service = FigureLearningService(tmp_path)

    assert service.list_figures("视觉教材", query="结构示意")['total'] == 1
    assert service.list_figures("视觉教材", query="第一章 结构")['total'] == 1
    nearby = service.list_figures("视觉教材", query="连接关系")
    assert nearby["total"] == 1
    assert nearby["items"][0]["match_scope"] == "nearby_text"
    assert service.list_figures("视觉教材", query="另一章正文")['total'] == 0


def test_figure_caption_does_not_fall_back_to_image_footnote_text(tmp_path):
    book, _image_path = _figure_book(tmp_path)
    figure = next(block for block in book.blocks if block.block_type == "figure")
    figure.text = "图脚说明，不是图注。"
    figure.attributes["caption"] = ""
    persist_canonical_book(book, progress_root=tmp_path)

    payload = FigureLearningService(tmp_path).list_figures("视觉教材")["items"][0]
    assert payload["caption"] == ""
    assert payload["source_text"] == "图脚说明，不是图注。"


def test_normalized_bbox_crop_uses_image_pixels_and_cleans_temp_file(tmp_path):
    _figure_book(tmp_path)
    service = FigureLearningService(tmp_path)
    bbox = NormalizedBBox.from_values([0.25, 0.2, 0.75, 0.8])

    with service.cropped_region("视觉教材", "figure-1", bbox) as (crop_path, metadata):
        assert crop_path.exists()
        assert Image.open(crop_path).size == (100, 60)
        assert metadata["pixel_bbox"] == [50, 20, 150, 80]
    assert not crop_path.exists()


def test_normalized_bbox_rejects_out_of_range_or_tiny_regions():
    for values in ([-0.1, 0, 0.5, 0.5], [0.5, 0.5, 0.4, 0.8], [0.1, 0.1, 0.101, 0.5]):
        try:
            NormalizedBBox.from_values(values)
        except ValueError:
            pass
        else:
            raise AssertionError(f"bbox should be rejected: {values}")


def test_figure_asset_path_cannot_escape_book_asset_directory(tmp_path):
    book, _image_path = _figure_book(tmp_path)
    outside = tmp_path / "视觉教材" / "outside.png"
    Image.new("RGB", (12, 12)).save(outside)
    figure = next(block for block in book.blocks if block.block_type == "figure")
    figure.attributes["asset_relpath"] = "figures/../outside.png"
    persist_canonical_book(book, progress_root=tmp_path)

    with pytest.raises(FileNotFoundError, match="受控资产"):
        FigureLearningService(tmp_path).asset_path("视觉教材", "figure-1")


def test_vision_bridge_sends_full_figure_crop_and_text_context_in_one_request(tmp_path):
    full = tmp_path / "full.png"
    crop = tmp_path / "crop.png"
    Image.new("RGB", (20, 10)).save(full)
    Image.new("RGB", (8, 8)).save(crop)
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return [SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="回答 [[cite:E1]]"))])]

    bridge = VisionModelBridge.__new__(VisionModelBridge)
    bridge.config = SimpleNamespace(
        credential_configured=True,
        provider=SimpleNamespace(label="测试视觉模型"),
        options={},
    )
    bridge.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    bridge.model = "vision-test"

    answer = "".join(bridge.iter_figure_answer(
        full,
        user_question="局部结构是什么？",
        figure_context={
            "figure": {"figure_id": "f1"},
            "nearby_blocks": [{"text": "教材原文"}],
            "evidence_sources": [{"id": "E1"}, {"id": "E2", "text": "教材原文"}],
        },
        cropped_region_path=crop,
    ))

    content = captured["messages"][0]["content"]
    assert answer == "回答 [[cite:E1]]"
    assert captured["stream"] is True
    assert [item["type"] for item in content].count("image_url") == 2
    assert "同一 Figure 中用户选区" in content[-2]["text"]
    assert "nearby_blocks" in content[0]["text"]
    assert '"evidence_id": "E2"' in content[0]["text"]
    assert "视觉观察引用 E1" in content[0]["text"]
    assert "不要输出 [E1]" in content[0]["text"]


def test_figure_api_lists_serves_and_streams_grounded_source(monkeypatch, tmp_path):
    _figure_book(tmp_path)
    from backend.api import figures

    service = FigureLearningService(tmp_path)
    monkeypatch.setattr(figures, "_service", lambda: service)
    monkeypatch.setattr(figures, "_task_store", lambda: LearningTaskStore(tmp_path / "tasks"))
    monkeypatch.setattr(figures, "resolve_conversation_id_for_scope", lambda value, *_args: value or "conv-figure")
    monkeypatch.setattr(figures, "append_message", lambda *_args, **kwargs: {"id": "message-1", **kwargs})

    class FakeBridge:
        def iter_figure_answer(self, *_args, **_kwargs):
            yield "这是局部结构。 [[cite:E1]]"

    monkeypatch.setattr(figures, "VisionModelBridge", FakeBridge)
    client = TestClient(app)

    listed = client.get("/api/books/%E8%A7%86%E8%A7%89%E6%95%99%E6%9D%90/figures").json()
    assert listed["data"]["total"] == 1
    assert client.get("/api/books/%E8%A7%86%E8%A7%89%E6%95%99%E6%9D%90/figures/figure-1/image").status_code == 200

    response = client.post("/api/visual-learning/figure-stream", json={
        "book_name": "视觉教材",
        "figure_id": "figure-1",
        "question": "这里是什么？",
        "bbox": [0.1, 0.1, 0.6, 0.8],
        "conversation_id": "conv-figure",
        "turn_id": "turn-figure",
    })
    assert response.status_code == 200
    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert any(item.get("activity", {}).get("id") == "crop-region" for item in payloads)
    done = next(item for item in payloads if item["stage"] == "done")
    assert done["result"]["sources"][0]["figure_id"] == "figure-1"
    assert [item["id"] for item in done["result"]["sources"]] == ["E1", "E2", "E3"]
    assert done["result"]["sources"][1]["block_id"] == "before"
    assert "[[cite:E1]]" in done["result"]["explanation"]
    assert done["result"]["answer_verification"]["status"] == "passed"
    assert done["result"]["citation_provenance"]["status"] == "model_aligned"
    assert done["result"]["citation_provenance"]["automatic_citation_inserted"] is False
    assert done["result"]["learning_task"]["status"] == "completed"


def test_figure_api_attaches_sources_without_inventing_inline_citation(monkeypatch, tmp_path):
    _figure_book(tmp_path)
    from backend.api import figures

    service = FigureLearningService(tmp_path)
    monkeypatch.setattr(figures, "_service", lambda: service)
    monkeypatch.setattr(figures, "_task_store", lambda: LearningTaskStore(tmp_path / "tasks"))
    monkeypatch.setattr(figures, "resolve_conversation_id_for_scope", lambda value, *_args: value or "conv-figure")
    saved: list[dict] = []
    monkeypatch.setattr(figures, "append_message", lambda *_args, **kwargs: saved.append(kwargs) or {"id": "message-1", **kwargs})

    class FakeBridge:
        def iter_figure_answer(self, *_args, **_kwargs):
            yield "模型只给出了观察结论。"

    monkeypatch.setattr(figures, "VisionModelBridge", FakeBridge)
    response = TestClient(app).post("/api/visual-learning/figure-stream", json={
        "book_name": "视觉教材", "figure_id": "figure-1", "question": "这里是什么？",
        "conversation_id": "conv-figure", "turn_id": "turn-unaligned",
    })
    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines() if line.startswith("data: ")
    ]
    done = next(item for item in payloads if item["stage"] == "done")
    explanation = done["result"]["explanation"]
    assert "[[cite:E1]]" not in explanation
    assert done["result"]["citation_provenance"]["status"] == "sources_attached"
    assert done["result"]["answer_verification"]["status"] == "failed"
    assert done["result"]["learning_task"]["status"] == "degraded"
    assert saved[-1]["evidence_support_status"] == "degraded"
    assert saved[-1]["citation_provenance"]["source_attachment_origin"] == "system"


def test_figure_context_uses_active_index_and_rejects_canonical_drift(tmp_path):
    book, _image_path = _figure_book(tmp_path)
    service = FigureLearningService(tmp_path)
    first = service.build_context("视觉教材", "figure-1")
    second = FigureLearningService(tmp_path).build_context("视觉教材", "figure-1")
    assert first.related_chunk_ids == second.related_chunk_ids
    first_metadata = service.cache_metadata("视觉教材")

    book.blocks[1].text = "更新后的图前正文。"
    persist_canonical_book(book, progress_root=tmp_path)
    with pytest.raises(FigureIndexOutOfDateError, match="Canonical IR differs"):
        service.build_context("视觉教材", "figure-1")

    _activate_figure_index(book, version="figure-index-v2")
    refreshed = service.build_context("视觉教材", "figure-1")
    assert refreshed.nearby_blocks[0]["text"] == "更新后的图前正文。"
    assert service.cache_metadata("视觉教材")["canonical_hash"] != first_metadata["canonical_hash"]


def test_figure_mapping_tracks_active_version_and_retained_reactivation(tmp_path):
    book, _image_path = _figure_book(tmp_path)
    v1_rows = [dict(row) for row in _ACTIVE_FIGURE_INDEXES[book.book_name]["rows"]]
    service = FigureLearningService(tmp_path)
    v1_ids = service.build_context("视觉教材", "figure-1").related_chunk_ids

    v2_rows = [{**row, "chunk_id": f"v2-{row['chunk_id']}"} for row in v1_rows]
    _activate_figure_index(book, version="figure-index-v2", rows=v2_rows)
    v2_ids = service.build_context("视觉教材", "figure-1").related_chunk_ids
    assert v2_ids and v2_ids != v1_ids

    _activate_figure_index(book, version="figure-index-v1", rows=v1_rows)
    reactivated_ids = service.build_context("视觉教材", "figure-1").related_chunk_ids
    assert reactivated_ids == v1_ids


def test_figure_context_explicitly_rejects_legacy_index(tmp_path):
    _figure_book(tmp_path)
    _ACTIVE_FIGURE_INDEXES["视觉教材"]["manifest"]["schema_version"] = 5

    with pytest.raises(FigureIndexOutOfDateError, match="schema-6"):
        FigureLearningService(tmp_path).build_context("视觉教材", "figure-1")


def test_figure_api_returns_conflict_for_legacy_index(monkeypatch, tmp_path):
    _figure_book(tmp_path)
    _ACTIVE_FIGURE_INDEXES["视觉教材"]["manifest"]["schema_version"] = 5
    from backend.api import figures

    monkeypatch.setattr(figures, "_service", lambda: FigureLearningService(tmp_path))
    response = TestClient(app).get(
        "/api/books/%E8%A7%86%E8%A7%89%E6%95%99%E6%9D%90/figures/figure-1"
    )

    assert response.status_code == 409
    assert response.json()["detail"].startswith("figure_index_out_of_date:")


def test_figure_task_interrupt_and_resume_reuses_saved_figure_context(monkeypatch, tmp_path):
    _figure_book(tmp_path)
    from backend.api import figures

    service = FigureLearningService(tmp_path)
    store = LearningTaskStore(tmp_path / "tasks")
    monkeypatch.setattr(figures, "_service", lambda: service)
    monkeypatch.setattr(figures, "_task_store", lambda: store)
    monkeypatch.setattr(figures, "append_message", lambda *_args, **kwargs: {"id": "message-resumed", **kwargs})

    class FakeBridge:
        def iter_figure_answer(self, *_args, **_kwargs):
            yield "恢复后回答 [[cite:E1]]"

    monkeypatch.setattr(figures, "VisionModelBridge", FakeBridge)
    task = store.create(
        task_type="figure_qa", goal="请解释这幅图",
        conversation_id="conv-resume", turn_id="turn-resume", answer_mode="visual_grounded",
        artifacts={
            "book_name": "视觉教材", "figure_id": "figure-1", "subject": "传感器",
            "page": 2, "region": [0.1, 0.1, 0.6, 0.8], "active_run_id": "run-initial",
        },
    )
    client = TestClient(app)
    stopped = client.post(
        f"/api/visual-learning/tasks/{task.id}/interrupt",
        json={"stage": "user_stopped", "partial_output": "部分回答"},
    ).json()["learning_task"]
    assert stopped["status"] == "interrupted"
    assert stopped["artifacts"]["partial_output"] == "部分回答"
    assert stopped["artifacts"]["resume_available"] is True

    response = client.post(f"/api/visual-learning/tasks/{task.id}/resume-stream")
    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines() if line.startswith("data: ")
    ]
    done = next(item for item in payloads if item["stage"] == "done")
    assert done["result"]["learning_task"]["status"] == "completed"
    assert done["result"]["region"] == [0.1, 0.1, 0.6, 0.8]
    assert "[[cite:E1]]" in done["result"]["explanation"]


def test_visual_learning_acceptance_requires_active_index_for_provenance_step(tmp_path):
    output = tmp_path / "mineru"
    (output / "images").mkdir(parents=True)
    Image.new("RGB", (120, 80), (245, 245, 245)).save(output / "images" / "sensor.png")
    (output / "sensor_content_list.json").write_text(json.dumps([
        {"type": "text", "text_level": 1, "text": "第二章 传感器", "page_idx": 0},
        {"type": "text", "text": "厚膜压力传感器先印刷电阻浆料，再烧结形成敏感结构。", "page_idx": 1},
        {
            "type": "image", "img_path": "images/sensor.png", "page_idx": 1,
            "bbox": [10, 20, 110, 70],
            "image_caption": ["图2.13 厚膜压力传感器的制作工艺流程示意图"],
        },
        {"type": "text", "text": "图中箭头表示制作工序的先后关系。", "page_idx": 1},
    ], ensure_ascii=False), encoding="utf-8")
    standard = {
        "schema_version": "visual-learning-sensor/v1",
        "thresholds": {
            "minimum_figures": 1, "minimum_caption_rate": 1,
            "minimum_ready_asset_rate": 1, "minimum_required_field_rate": 1,
            "minimum_query_top3_rate": 1,
        },
        "queries": [{
            "query": "厚膜压力 制作工艺",
            "expected_caption_terms": ["厚膜压力传感器", "制作工艺流程"],
            "expected_page": 2,
        }],
        "region": {"query": "厚膜压力 制作工艺", "bbox": [0.2, 0.2, 0.8, 0.8]},
    }

    result = evaluate_visual_learning_corpus(
        output, progress_root=tmp_path / "progress", standard=standard, book_name="传感器验收小样",
    )

    assert result.passed is False
    assert result.report["step1_ingestion"]["ready_asset_rate"] == 1
    assert result.report["step2_search_open"]["query_top3_rate"] == 1
    assert result.report["step3_region_question_contract"]["passed"] is True
    assert result.report["step4_answer_provenance"] == {
        "passed": False,
        "status": "active_index_required",
        "reason": "figure_index_out_of_date: active schema-6 provenance index required",
    }
    assert result.report["online_model_called"] is False
