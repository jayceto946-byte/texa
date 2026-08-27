import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backend.main import app
from backend.services.figure_learning import FigureLearningService, NormalizedBBox
from backend.services.multimodal_bridge import VisionModelBridge
from ingestion.document_ir import CanonicalBook, DocumentBlock, persist_canonical_book


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
    assert context.figure["section_path"] == ["第一章", "结构"]


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
        figure_context={"figure": {"figure_id": "f1"}, "nearby_blocks": [{"text": "教材原文"}]},
        cropped_region_path=crop,
    ))

    content = captured["messages"][0]["content"]
    assert answer == "回答 [[cite:E1]]"
    assert captured["stream"] is True
    assert [item["type"] for item in content].count("image_url") == 2
    assert "同一 Figure 中用户选区" in content[-2]["text"]
    assert "nearby_blocks" in content[0]["text"]


def test_figure_api_lists_serves_and_streams_grounded_source(monkeypatch, tmp_path):
    _figure_book(tmp_path)
    from backend.api import figures

    service = FigureLearningService(tmp_path)
    monkeypatch.setattr(figures, "_service", lambda: service)
    monkeypatch.setattr(figures, "resolve_conversation_id_for_scope", lambda value, *_args: value or "conv-figure")
    monkeypatch.setattr(figures, "append_message", lambda *_args, **kwargs: {"id": "message-1", **kwargs})

    class FakeBridge:
        def iter_figure_answer(self, *_args, **_kwargs):
            yield "这是局部结构。"

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
    assert "[[cite:E1]]" in done["result"]["explanation"]
