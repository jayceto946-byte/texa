import hashlib
import json
from pathlib import Path
import threading
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from backend.main import app
from backend.services.execution_events import (
    EXECUTION_EVENT_TERMINAL_TYPES,
    EXECUTION_SSE_FORBIDDEN_LIFECYCLE_FIELDS,
    validate_execution_event_sequence,
)
from backend.services.figure_learning import (
    FigureIndexOutOfDateError,
    FigureLearningService,
    NormalizedBBox,
)
from backend.services.learning_task import LearningTaskStore, resume_learning_task
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


def _stream_payloads(response) -> list[dict]:
    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert payloads
    assert all(
        set(payload).isdisjoint(EXECUTION_SSE_FORBIDDEN_LIFECYCLE_FIELDS)
        for payload in payloads
    )
    return payloads


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
    from llm.configuration import resolve_model_role

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
    bridge.config = resolve_model_role("vision", {
        "LLM_VISION_PROVIDER": "qwen",
        "LLM_VISION_MODEL": "qwen3.7-plus",
        "LLM_VISION_API_KEY": "test-key",
    })
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
    store = LearningTaskStore(tmp_path / "tasks")
    monkeypatch.setattr(figures, "_service", lambda: service)
    monkeypatch.setattr(figures, "_task_store", lambda: store)
    monkeypatch.setattr(figures, "resolve_conversation_id_for_scope", lambda value, *_args: value or "conv-figure")
    monkeypatch.setattr(figures, "append_message", lambda *_args, **kwargs: {"id": "message-1", **kwargs})

    class FakeBridge:
        def iter_figure_answer(self, *_args, **_kwargs):
            yield "这是结构示意图。 [[cite:E1]]"

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
    payloads = _stream_payloads(response)
    assert any(item["execution_event"]["operation_id"] == "crop-region" for item in payloads)
    done = next(item for item in payloads if item["execution_event"]["type"] == "final")
    assert done["result"]["sources"][0]["figure_id"] == "figure-1"
    assert [item["id"] for item in done["result"]["sources"]] == ["E1", "E2", "E3"]
    assert done["result"]["sources"][1]["block_id"] == "before"
    assert "[[cite:E1]]" in done["result"]["explanation"]
    assert done["result"]["answer_verification"]["status"] == "passed"
    assert done["result"]["citation_provenance"]["status"] == "model_aligned"
    assert done["result"]["citation_provenance"]["automatic_citation_inserted"] is False
    assert done["result"]["learning_task"]["status"] == "completed"
    task = done["result"]["learning_task"]
    canonical = [
        item["execution_event"]
        for item in payloads
        if (item.get("execution_event") or {}).get("task_id") == task["id"]
    ]
    validate_execution_event_sequence(canonical)
    assert {event["type"] for event in canonical} <= {
        "progress", "state_transition", "tool_result", "output_delta", "final", "error",
    }
    assert [event["seq"] for event in canonical] == sorted(event["seq"] for event in canonical)
    terminals = [event for event in canonical if event["type"] in EXECUTION_EVENT_TERMINAL_TYPES]
    assert len(terminals) == 1 and terminals[0]["type"] == "final"
    assert canonical[-1] == terminals[0]
    assert terminals[0]["payload"]["task_status"] == task["status"]
    deltas = [event for event in canonical if event["type"] == "output_delta"]
    assert deltas
    assert all(set(event["payload"]) == {"text", "replace"} for event in deltas)
    stored = store.get(task["id"])
    assert [event["type"] for event in stored.artifacts["execution_events"]] == [
        "state_transition", "tool_result", "final",
    ]


def test_figure_api_attaches_sources_without_inventing_inline_citation(monkeypatch, tmp_path):
    _figure_book(tmp_path)
    from backend.api import figures

    service = FigureLearningService(tmp_path)
    store = LearningTaskStore(tmp_path / "tasks")
    monkeypatch.setattr(figures, "_service", lambda: service)
    monkeypatch.setattr(figures, "_task_store", lambda: store)
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
    payloads = _stream_payloads(response)
    done = next(item for item in payloads if item["execution_event"]["type"] == "final")
    explanation = done["result"]["explanation"]
    assert "[[cite:E1]]" not in explanation
    assert done["result"]["citation_provenance"]["status"] == "sources_attached"
    assert done["result"]["answer_verification"]["status"] == "failed"
    assert done["result"]["learning_task"]["status"] == "degraded"
    assert done["result"]["learning_task"]["terminal"] is True
    assert done["result"]["learning_task"]["interruptible"] is False
    assert done["result"]["learning_task"]["resumable"] is False
    assert saved[-1]["evidence_support_status"] == "degraded"
    assert saved[-1]["citation_provenance"]["source_attachment_origin"] == "system"
    task = done["result"]["learning_task"]
    canonical = [
        item["execution_event"]
        for item in payloads
        if (item.get("execution_event") or {}).get("task_id") == task["id"]
    ]
    validate_execution_event_sequence(canonical)
    terminals = [event for event in canonical if event["type"] in EXECUTION_EVENT_TERMINAL_TYPES]
    assert len(terminals) == 1 and terminals[0]["type"] == "final"
    assert terminals[0]["payload"]["task_status"] == "degraded"
    assert store.get(task["id"]).status == "degraded"


def test_figure_output_delta_uses_exact_append_and_replace_payload(monkeypatch, tmp_path):
    _figure_book(tmp_path)
    from backend.api import figures

    store = LearningTaskStore(tmp_path / "tasks")
    monkeypatch.setattr(figures, "_service", lambda: FigureLearningService(tmp_path))
    monkeypatch.setattr(figures, "_task_store", lambda: store)
    monkeypatch.setattr(figures, "append_message", lambda *_args, **kwargs: {"id": "message-1"})
    monkeypatch.setattr(figures, "sanitize_latex", lambda _answer: "normalized answer")
    monkeypatch.setattr(figures, "verify_answer", lambda *_args, **_kwargs: {
        "status": "passed", "passed": True, "checks": [],
    })

    class FakeBridge:
        def iter_figure_answer(self, *_args, **_kwargs):
            yield "raw "
            yield "answer"

    monkeypatch.setattr(figures, "VisionModelBridge", FakeBridge)

    response = TestClient(app).post("/api/visual-learning/figure-stream", json={
        "book_name": "视觉教材", "figure_id": "figure-1", "question": "解释这幅图",
        "conversation_id": "conv-delta", "turn_id": "turn-delta",
    })
    payloads = _stream_payloads(response)
    deltas = [
        item["execution_event"]["payload"]
        for item in payloads
        if (item.get("execution_event") or {}).get("type") == "output_delta"
    ]

    assert response.status_code == 200
    assert deltas == [
        {"text": "raw ", "replace": False},
        {"text": "answer", "replace": False},
        {"text": "normalized answer", "replace": True},
    ]
    done = next(item for item in payloads if item["execution_event"]["type"] == "final")
    assert done["result"]["explanation"] == "normalized answer"


def test_figure_terminal_survives_conversation_projection_failure(monkeypatch, tmp_path):
    _figure_book(tmp_path)
    from backend.api import figures

    store = LearningTaskStore(tmp_path / "tasks")
    monkeypatch.setattr(figures, "_service", lambda: FigureLearningService(tmp_path))
    monkeypatch.setattr(figures, "_task_store", lambda: store)
    monkeypatch.setattr(
        figures, "append_message",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("conversation write failed")),
    )
    monkeypatch.setattr(figures, "verify_answer", lambda *_args, **_kwargs: {
        "status": "passed", "passed": True, "checks": [],
    })

    class FakeBridge:
        def iter_figure_answer(self, *_args, **_kwargs):
            yield "grounded answer [[cite:E1]]"

    monkeypatch.setattr(figures, "VisionModelBridge", FakeBridge)

    response = TestClient(app).post("/api/visual-learning/figure-stream", json={
        "book_name": "视觉教材", "figure_id": "figure-1", "question": "解释这幅图",
        "conversation_id": "conv-persist", "turn_id": "turn-persist",
    })
    payloads = _stream_payloads(response)
    done = next(item for item in payloads if item["execution_event"]["type"] == "final")
    task = done["result"]["learning_task"]

    assert done["persistence_error"] == "conversation write failed"
    assert done["execution_event"]["type"] == "final"
    assert done["execution_event"]["payload"]["task_status"] == "completed"
    assert store.get(task["id"]).status == "completed"


def test_figure_stream_maps_active_index_mismatch_to_canonical_error(monkeypatch, tmp_path):
    _figure_book(tmp_path)
    _ACTIVE_FIGURE_INDEXES["视觉教材"]["manifest"]["schema_version"] = 5
    from backend.api import figures

    store = LearningTaskStore(tmp_path / "tasks")
    monkeypatch.setattr(figures, "_service", lambda: FigureLearningService(tmp_path))
    monkeypatch.setattr(figures, "_task_store", lambda: store)
    monkeypatch.setattr(figures, "append_message", lambda *_args, **kwargs: {"id": "message-error"})

    class UnexpectedBridge:
        def __init__(self):
            raise AssertionError("vision model must not run after provenance failure")

    monkeypatch.setattr(figures, "VisionModelBridge", UnexpectedBridge)

    response = TestClient(app).post("/api/visual-learning/figure-stream", json={
        "book_name": "视觉教材", "figure_id": "figure-1", "question": "解释这幅图",
        "conversation_id": "conv-stale-index", "turn_id": "turn-stale-index",
    })
    payloads = _stream_payloads(response)
    error = next(item for item in payloads if item["execution_event"]["type"] == "error")
    task = error["learning_task"]
    canonical = [
        item["execution_event"]
        for item in payloads
        if (item.get("execution_event") or {}).get("task_id") == task["id"]
    ]

    assert response.status_code == 200
    validate_execution_event_sequence(canonical)
    terminals = [event for event in canonical if event["type"] in EXECUTION_EVENT_TERMINAL_TYPES]
    assert len(terminals) == 1 and terminals[0]["type"] == "error"
    assert canonical[-1] == terminals[0]
    assert terminals[0]["payload"]["http_status"] == 409
    assert terminals[0]["payload"]["error_code"] == "figure_index_out_of_date"
    assert terminals[0]["payload"]["task_status"] == "failed"
    assert task["status"] == "failed"
    assert store.get(task["id"]).status == "failed"
    assert not any(item["execution_event"]["type"] == "final" for item in payloads)


def test_figure_stale_run_cannot_emit_after_interrupt_and_new_run(monkeypatch, tmp_path):
    _figure_book(tmp_path)
    from backend.api import figures

    stream_paused = threading.Event()
    release_stream = threading.Event()

    class TrackingStore(LearningTaskStore):
        task_id = ""

        def create(self, **kwargs):
            task = super().create(**kwargs)
            self.task_id = task.id
            return task

    store = TrackingStore(tmp_path / "tasks")
    monkeypatch.setattr(figures, "_service", lambda: FigureLearningService(tmp_path))
    monkeypatch.setattr(figures, "_task_store", lambda: store)
    monkeypatch.setattr(figures, "append_message", lambda *_args, **kwargs: {"id": "message-partial"})

    class BlockingBridge:
        def iter_figure_answer(self, *_args, **_kwargs):
            yield "partial"
            stream_paused.set()
            release_stream.wait(timeout=3)
            yield "late"

    monkeypatch.setattr(figures, "VisionModelBridge", BlockingBridge)
    client = TestClient(app)
    result = {}

    def consume_stream():
        result["response"] = client.post("/api/visual-learning/figure-stream", json={
            "book_name": "视觉教材", "figure_id": "figure-1", "question": "解释这幅图",
            "conversation_id": "conv-interrupt", "turn_id": "turn-interrupt",
        })

    worker = threading.Thread(target=consume_stream)
    worker.start()
    assert stream_paused.wait(timeout=3)

    interrupted = client.post(
        f"/api/visual-learning/tasks/{store.task_id}/interrupt",
        json={"stage": "user_stopped", "partial_output": "partial", "run_id": store.get(store.task_id).artifacts["active_run_id"]},
    ).json()["learning_task"]
    assert interrupted["status"] == "interrupted"
    resumed = resume_learning_task(store, store.get(store.task_id), run_id="run-new")
    assert resumed.status == "running"

    release_stream.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    payloads = _stream_payloads(result["response"])
    old_run_events = [
        item["execution_event"]
        for item in payloads
        if (item.get("execution_event") or {}).get("run_id") != "run-new"
    ]
    validate_execution_event_sequence(old_run_events)
    assert not any(event["type"] in EXECUTION_EVENT_TERMINAL_TYPES for event in old_run_events)
    assert not any(
        event["type"] == "output_delta" and event["payload"]["text"] == "late"
        for event in old_run_events
    )
    current = store.get(store.task_id)
    assert current.status == "running"
    assert current.artifacts["active_run_id"] == "run-new"


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
            yield "恢复后显示结构示意图。 [[cite:E1]]"

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
        json={"stage": "user_stopped", "partial_output": "部分回答", "run_id": "run-initial"},
    ).json()["learning_task"]
    assert stopped["status"] == "interrupted"
    assert stopped["artifacts"]["partial_output"] == "部分回答"
    assert stopped["artifacts"]["resume_available"] is True

    response = client.post(f"/api/visual-learning/tasks/{task.id}/resume-stream")
    payloads = _stream_payloads(response)
    done = next(item for item in payloads if item["execution_event"]["type"] == "final")
    assert done["result"]["learning_task"]["status"] == "completed"
    assert done["result"]["region"] == [0.1, 0.1, 0.6, 0.8]
    assert "[[cite:E1]]" in done["result"]["explanation"]
    canonical = [
        item["execution_event"]
        for item in payloads
        if (item.get("execution_event") or {}).get("task_id") == task.id
    ]
    validate_execution_event_sequence(canonical)
    assert len({event["run_id"] for event in canonical}) == 1
    assert canonical[0]["run_id"] != "run-initial"
    terminals = [event for event in canonical if event["type"] in EXECUTION_EVENT_TERMINAL_TYPES]
    assert len(terminals) == 1 and terminals[0]["type"] == "final"
    assert terminals[0]["payload"]["task_status"] == "completed"


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


def _grouped_figure_book(tmp_path):
    book, image_path = _figure_book(tmp_path)
    first = book.blocks[2]
    first.text = '(a)'
    first.bbox = [.1, .1, .45, .3]
    first.attributes.update(caption='(a)', page_bbox=first.bbox, bbox_units='normalized')
    second = DocumentBlock('figure-2', 'figure', '(b)\n图 1.21 频率响应', list(first.section_path), 2, 2,
        bbox=[.5, .1, .9, .3], source_kind='mineru', source_file=first.source_file,
        attributes={**first.attributes, 'figure_id': 'figure-2', 'caption': '(b)\n图 1.21 频率响应', 'asset_relpath': 'figures/figure-2.png'})
    Image.new('RGB', (150, 80), 'blue').save(image_path.parent / 'figure-2.png')
    book.blocks.insert(3, second)
    persist_canonical_book(book, progress_root=tmp_path)
    _activate_figure_index(book)
    return book


def test_grouped_subfigures_share_display_vision_crop_and_provenance(tmp_path):
    book = _grouped_figure_book(tmp_path)
    service = FigureLearningService(tmp_path)
    listed = service.list_figures(book.book_name)
    assert listed['total'] == 1
    item = listed['items'][0]
    assert item['figure_id'] == 'figure-2' and item['image_url'].endswith('/group-image')
    assert item['page_bbox'] == [] and len(item['members']) == 2
    context = service.build_context(book.book_name, 'figure-2')
    assert set(context.figure['source_block_ids']) >= {'figure-1', 'figure-2'}
    with service.complete_figure_asset(book.book_name, 'figure-2') as path:
        with Image.open(path) as image:
            size = image.size
            assert size[0] > 350 and image.getpixel((232, 40)) == (0, 0, 255)
        composite_path = path
    assert not composite_path.exists()
    with service.cropped_region(book.book_name, 'figure-2', NormalizedBBox.from_values([.5, 0, 1, 1])) as (path, metadata):
        assert metadata['image_width'] == size[0] and metadata['image_height'] == size[1]
    # Existing links continue to return the original member asset.
    assert service.asset_path(book.book_name, 'figure-2').name == 'figure-2.png'


def test_different_pages_are_not_grouped_and_missing_member_requires_input(tmp_path):
    from backend.services.figure_learning import FigureInputRequiredError
    book = _grouped_figure_book(tmp_path)
    book.blocks[3].page_start = book.blocks[3].page_end = 3
    persist_canonical_book(book, progress_root=tmp_path)
    _activate_figure_index(book)
    service = FigureLearningService(tmp_path)
    assert service.list_figures(book.book_name)['total'] == 2
    with pytest.raises(FigureInputRequiredError, match='全部子图'):
        with service.complete_figure_asset(book.book_name, 'figure-2'):
            pytest.fail('An isolated b crop must not masquerade as the whole figure')


def test_missing_group_asset_gates_stream_before_any_model(monkeypatch, tmp_path):
    from backend.api import figures
    book = _grouped_figure_book(tmp_path)
    (tmp_path / book.book_name / 'figures' / 'figure-2.png').unlink()
    store = LearningTaskStore(tmp_path / 'tasks')
    monkeypatch.setattr(figures, '_service', lambda: FigureLearningService(tmp_path))
    monkeypatch.setattr(figures, '_task_store', lambda: store)
    monkeypatch.setattr(figures, 'append_message', lambda *_a, **_k: {'id': 'missing-input-message'})
    monkeypatch.setattr(figures, 'VisionModelBridge', lambda: pytest.fail('No model call with missing figure input'))
    response = TestClient(app).post('/api/visual-learning/figure-stream', json={
        'book_name': book.book_name, 'figure_id': 'figure-2', 'question': '解释整张频率响应图',
        'conversation_id': 'conv-missing-figure', 'turn_id': 'turn-missing-figure',
    })
    payloads = _stream_payloads(response)
    terminal = next(item for item in payloads if item['execution_event']['type'] == 'error')
    assert terminal['execution_event']['payload']['error_code'] == 'figure_input_required'
    assert terminal['learning_task']['status'] == 'waiting_for_input'
    assert terminal['learning_task']['required_inputs'][0]['status'] == 'missing'


def _geometry_book(tmp_path, boxes, nodes):
    from ingestion.figure_layout import LAYOUT_SCHEMA, LAYOUT_FILENAME
    book, image_path = _figure_book(tmp_path)
    prototype = book.blocks[2]
    colors = ['red', 'blue', 'green', 'yellow']
    members = []
    for index, bbox in enumerate(boxes):
        bid = f'panel-{index}'
        path = image_path.parent / f'{bid}.png'
        Image.new('RGB', (160, 100), colors[index % len(colors)]).save(path)
        members.append(DocumentBlock(bid, 'figure', '', list(prototype.section_path), 2, 2,
                                     bbox=bbox, source_kind='mineru', source_file='source.json',
                                     attributes={**prototype.attributes, 'figure_id': bid,
                                                 'caption': '', 'bbox_units': 'normalized', 'page_bbox': bbox,
                                                 'asset_relpath': f'figures/{bid}.png',
                                                 'content_hash': hashlib.sha256(path.read_bytes()).hexdigest()}))
    book.blocks[2:3] = members
    persist_canonical_book(book, progress_root=tmp_path)
    _activate_figure_index(book)
    projection = dict(schema=LAYOUT_SCHEMA, book_name=book.book_name,
                      canonical_hash=canonical_book_fingerprint(book), caption_nodes=nodes)
    (tmp_path / book.book_name / LAYOUT_FILENAME).write_text(json.dumps(projection))
    return book, projection


def test_geometry_repairs_misassigned_labels_preserves_grid_and_region(tmp_path):
    boxes = [[.1,.1,.35,.25], [.55,.1,.8,.25], [.1,.4,.35,.55], [.55,.4,.8,.55]]
    nodes = [dict(source_block_id='panel-3', page=2, text=f'({label})', bbox=bbox)
             for label, bbox in zip('abcd', [[.2,.26,.23,.28], [.65,.26,.68,.28],
                                            [.2,.56,.23,.58], [.65,.56,.68,.58]])]
    nodes.append(dict(source_block_id='panel-3', page=2, text='图 11.27 四格电路', bbox=[.2,.6,.7,.62]))
    book, _projection = _geometry_book(tmp_path, boxes, nodes)
    service = FigureLearningService(tmp_path)
    items = service.list_figures(book.book_name)['items']
    assert len(items) == 1 and len(items[0]['members']) == 4
    assert [m['caption'] for m in items[0]['members']] == ['(a)', '(b)', '(c)', '(d)']
    assert items[0]['layout_status'] == 'assembled'
    assert '(a)\n(b)\n(c)\n(d)' in items[0]['caption']
    context = service.build_context(book.book_name, 'panel-1')
    assert context.figure['image_source_block_ids'] == ['panel-0', 'panel-1', 'panel-2', 'panel-3']
    with service.complete_figure_asset(book.book_name, 'panel-1') as path:
        with Image.open(path) as image:
            width, height = image.size
            assert image.getpixel((50,50)) == (255,0,0)
            assert image.getpixel((width-50,50)) == (0,0,255)
            assert image.getpixel((50,height-70)) == (0,128,0)
            assert image.getpixel((width-50,height-70)) == (255,255,0)
    with service.cropped_region(book.book_name, 'panel-1', NormalizedBBox.from_values([.5,.5,1,1])) as (path, _meta):
        with Image.open(path) as region:
            assert region.getpixel((region.width//2,region.height//2)) == (255,255,0)


def test_nearby_numbered_diagrams_separate_with_caption_source_provenance(tmp_path):
    boxes = [[.05,.1,.2,.25], [.25,.1,.4,.25], [.65,.1,.85,.25]]
    # Both public captions were erroneously attached to the right-hand crop.
    nodes = [dict(source_block_id='panel-2', page=2, text='图 5.17 左侧组合', bbox=[.05,.28,.4,.3]),
             dict(source_block_id='panel-2', page=2, text='图 5.18 右侧独立', bbox=[.65,.28,.9,.3])]
    book, _projection = _geometry_book(tmp_path, boxes, nodes)
    service = FigureLearningService(tmp_path)
    listed = service.list_figures(book.book_name)
    assert listed['total'] == 2
    left = service.get_figure(book.book_name, 'panel-0')[2]
    right = service.get_figure(book.book_name, 'panel-2')[2]
    assert left['figure_number'] == '5.17' and len(left['members']) == 2
    assert right['figure_number'] == '5.18' and 'members' not in right
    context = service.build_context(book.book_name, 'panel-0')
    assert context.figure['image_source_block_ids'] == ['panel-0','panel-1']
    assert set(context.figure['source_block_ids']) == {'panel-0','panel-1','panel-2'}
    assert context.figure['caption_source_block_ids'] == ['panel-2']


def test_caption_projection_cache_refresh_and_stale_hash_fail_closed(tmp_path):
    from ingestion.figure_layout import LAYOUT_FILENAME
    boxes = [[.1,.1,.4,.25], [.6,.1,.9,.25]]
    nodes = [dict(source_block_id='panel-1', page=2, text='图 1.1 组合', bbox=[.3,.28,.7,.3])]
    book, projection = _geometry_book(tmp_path, boxes, nodes)
    service = FigureLearningService(tmp_path)
    assert service.list_figures(book.book_name)['total'] == 1
    target = tmp_path / book.book_name / LAYOUT_FILENAME
    projection['caption_nodes'] = [dict(source_block_id='panel-1', page=2, text='图 1.1 左图', bbox=[.1,.28,.4,.3]),
                                  dict(source_block_id='panel-1', page=2, text='图 1.2 右图', bbox=[.6,.28,.9,.3])]
    target.write_text(json.dumps(projection))
    assert service.list_figures(book.book_name)['total'] == 2
    projection['canonical_hash'] = '0'*64
    target.write_text(json.dumps(projection))
    with pytest.raises(FigureIndexOutOfDateError, match='Canonical'):
        service.list_figures(book.book_name)


def test_caption_tie_requires_input_without_hiding_independent_image(tmp_path):
    from backend.services.figure_learning import FigureInputRequiredError
    boxes = [[.4,.1,.6,.25]]
    nodes = [dict(source_block_id='panel-0', page=2, text='图 1.1 左图题', bbox=[.1,.28,.4,.3]),
             dict(source_block_id='panel-0', page=2, text='图 1.2 右图题', bbox=[.6,.28,.9,.3])]
    book, _projection = _geometry_book(tmp_path, boxes, nodes)
    service = FigureLearningService(tmp_path)
    assert service.list_figures(book.book_name)['items'][0]['layout_status'] == 'ambiguous'
    with pytest.raises(FigureInputRequiredError, match='组合关系'):
        with service.complete_figure_asset(book.book_name, 'panel-0'):
            pytest.fail('No model image can be fabricated across ambiguous anchors')


def test_new_canonical_coordinates_take_precedence_over_old_projection(tmp_path):
    boxes = [[.1,.1,.4,.25], [.6,.1,.9,.25]]
    nodes = [dict(source_block_id='panel-1', page=2, text='图 1.1 旧组合', bbox=[.3,.28,.7,.3])]
    book, _projection = _geometry_book(tmp_path, boxes, nodes)
    # Reimport persists a new source-neutral Canonical, while the optional
    # old sidecar can remain for rollback. It cannot override the new source.
    members = [b for b in book.blocks if b.block_type == 'figure']
    for member, number in zip(members, ['1.2','1.3']):
        member.attributes['visual_captions'] = [dict(text=f'图 {number} 新独立图',
                                                     bbox=[member.bbox[0],.28,member.bbox[2],.3])]
    persist_canonical_book(book, progress_root=tmp_path)
    _activate_figure_index(book, version='new-coordinate-index')
    items = FigureLearningService(tmp_path).list_figures(book.book_name)['items']
    assert len(items) == 2 and {i['figure_number'] for i in items} == {'1.2','1.3'}


def test_source_annotation_outside_crop_is_kept_in_caption_and_composite(tmp_path):
    boxes = [[.1,.1,.35,.25], [.55,.1,.8,.25]]
    nodes = [dict(source_block_id='panel-1', page=2, text='图 2.15 工艺', bbox=[.2,.3,.7,.32]),
             dict(source_block_id='panel-1', page=2, text='mask', bbox=[.8,.12,.9,.14])]
    book, _projection = _geometry_book(tmp_path, boxes, nodes)
    service = FigureLearningService(tmp_path)
    figure = service.get_figure(book.book_name, 'panel-1')[2]
    assert figure['caption'] == '图 2.15 工艺\nmask'
    assert any(node['text']=='mask' for node in figure['caption_sources'])
    with service.complete_figure_asset(book.book_name, 'panel-1') as path:
        with Image.open(path) as image:
            # Native crop pixels end at x=.8; known annotation extends to .9.
            assert image.width > 480
