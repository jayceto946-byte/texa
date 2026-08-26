import json

from PIL import Image

from ingestion.chapter_splitter import ChapterSplitter
from ingestion.document_adapters import MinerUAdapter, materialize_figure_assets
from ingestion.document_ir import load_canonical_book, persist_canonical_book, validate_canonical_book


def _image(path, *, size=(24, 12), color=(10, 20, 30)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_content_list_v1_figures_are_deterministic_durable_and_idempotent(tmp_path):
    output = tmp_path / "mineru"
    output.mkdir()
    _image(output / "images" / "captioned.png", size=(31, 17))
    _image(output / "images" / "uncaptioned.png", size=(19, 11))
    _write_json(output / "z_content_list.json", [
        {"type": "text", "text_level": 1, "text": "第一章", "page_idx": 0},
        {"type": "text", "text": "正文内容足够用于索引。", "page_idx": 0},
        {
            "type": "image", "img_path": "images/captioned.png",
            "image_caption": ["图 1 稳定图注"], "page_idx": 1, "bbox": [10, 20, 110, 220],
        },
        {
            "type": "image", "img_path": "images/uncaptioned.png",
            "image_caption": [], "page_idx": 2, "bbox": [1, 2, 30, 40],
        },
    ])
    # A lexically earlier v2 file must not win over the established v1 contract.
    _write_json(output / "a_content_list.json", [[{
        "type": "text", "content": {"content": "不应选择的 v2 正文"}, "bbox": [0, 0, 1, 1],
    }]])
    (output / "0_content_list.json").write_text("{", encoding="utf-8")

    book = MinerUAdapter.from_output_dir(output, book_name="Figure V1")
    assert book.parser_version == "mineru-content-list-v1"
    figures = [block for block in book.blocks if block.block_type == "figure"]
    assert len(figures) == 2
    first, second = figures
    assert first.text == "图 1 稳定图注"
    assert first.section_path == ["第一章"]
    assert first.page_start == 2 and first.attributes["page_idx"] == 1
    assert first.bbox == [10.0, 20.0, 110.0, 220.0]
    assert first.attributes["page_bbox"] == [10.0, 20.0, 110.0, 220.0]
    assert first.attributes["bbox_space"] == "page"
    assert first.attributes["bbox_units"] == "mineru_source_units"
    assert first.attributes["source_asset_relpath"] == "images/captioned.png"
    assert second.text == ""

    progress = tmp_path / "progress"
    materialize_figure_assets(book, source_root=output, progress_root=progress)
    first_ids = [block.block_id for block in figures]
    first_assets = [block.attributes["asset_relpath"] for block in figures]
    first_hashes = [block.attributes["content_hash"] for block in figures]
    assert all(path.startswith("figures/") for path in first_assets)
    assert all((progress / "Figure V1" / path).is_file() for path in first_assets)
    assert first.attributes["image_width"] == 31 and first.attributes["image_height"] == 17
    assert validate_canonical_book(book).valid is True

    persist_canonical_book(book, progress_root=progress)
    loaded = load_canonical_book("Figure V1", progress_root=progress)
    loaded_figures = [block for block in loaded.blocks if block.block_type == "figure"]
    assert [block.attributes["figure_id"] for block in loaded_figures] == first_ids
    assert [block.attributes["asset_relpath"] for block in loaded_figures] == first_assets

    repeated = MinerUAdapter.from_output_dir(output, book_name="Figure V1")
    materialize_figure_assets(repeated, source_root=output, progress_root=progress)
    repeated_figures = [block for block in repeated.blocks if block.block_type == "figure"]
    assert [block.block_id for block in repeated_figures] == first_ids
    assert [block.attributes["asset_relpath"] for block in repeated_figures] == first_assets
    assert [block.attributes["content_hash"] for block in repeated_figures] == first_hashes
    assert len(list((progress / "Figure V1" / "figures").iterdir())) == 2


def test_content_list_v2_and_middle_figures_preserve_native_fields(tmp_path):
    v2 = tmp_path / "v2"
    v2.mkdir()
    _image(v2 / "images" / "v2.jpg")
    _write_json(v2 / "book_content_list.json", [
        [{"type": "title", "content": {"level": 1, "title_content": [{"type": "text", "content": "第二章"}]}}],
        [{
            "type": "image", "bbox": [2, 4, 100, 120],
            "content": {
                "image_source": {"path": "images/v2.jpg"},
                "image_caption": [{"type": "text", "content": "图 2 v2 图注"}],
                "image_footnote": [],
            },
        }],
    ])
    v2_book = MinerUAdapter.from_output_dir(v2, book_name="V2")
    v2_figure = next(block for block in v2_book.blocks if block.block_type == "figure")
    assert v2_book.parser_version == "mineru-content-list-v2"
    assert v2_figure.text == "图 2 v2 图注"
    assert v2_figure.page_start == 2
    assert v2_figure.section_path == ["第二章"]
    assert v2_figure.attributes["source_asset_relpath"] == "images/v2.jpg"

    middle = tmp_path / "middle"
    middle.mkdir()
    _image(middle / "images" / "middle.png")
    _write_json(middle / "book_middle.json", {"pdf_info": [{
        "page_idx": 4,
        "para_blocks": [
            {"type": "title", "bbox": [0, 0, 50, 10], "lines": [{"spans": [{"content": "第三章"}]}]},
            {"type": "text", "bbox": [0, 11, 50, 20], "lines": [{"spans": [{"content": "正文内容足够用于索引。"}]}]},
            {
                "type": "image", "bbox": [5, 25, 95, 115],
                "lines": [{"spans": [{"type": "image", "image_path": "images/middle.png"}]}],
                "blocks": [{"type": "image_caption", "lines": [{"spans": [{"content": "图 3 middle 图注"}]}]}],
            },
        ],
    }]})
    middle_book = MinerUAdapter.from_output_dir(middle, book_name="Middle")
    middle_figure = next(block for block in middle_book.blocks if block.block_type == "figure")
    assert middle_book.parser_version == "mineru-middle-v1"
    assert middle_figure.text == "图 3 middle 图注"
    assert middle_figure.page_start == 5
    assert middle_figure.section_path == ["第三章"]
    assert middle_figure.attributes["source_asset_relpath"] == "images/middle.png"


def test_missing_figure_asset_is_explicit_and_empty_caption_reaches_provenance(tmp_path):
    output = tmp_path / "missing"
    output.mkdir()
    _write_json(output / "book_content_list.json", [
        {"type": "text", "text_level": 1, "text": "第一章", "page_idx": 0},
        {"type": "text", "text": "正文内容足够用于索引。", "page_idx": 0},
        {"type": "image", "img_path": "images/not-found.png", "page_idx": 0, "bbox": [1, 2, 3, 4]},
    ])
    book = MinerUAdapter.from_output_dir(output, book_name="Missing")
    figure = next(block for block in book.blocks if block.block_type == "figure")
    materialize_figure_assets(book, source_root=output, progress_root=tmp_path / "progress")

    assert figure.attributes["asset_status"] == "missing"
    assert figure.attributes["asset_relpath"] == ""
    assert "missing_figure_asset" in figure.review_status
    assert any("Figure asset missing" in warning for warning in book.warnings)
    assert "figure_asset_missing" in {issue.code for issue in validate_canonical_book(book).issues}

    chunks = ChapterSplitter().split_canonical_book(book)
    figure_chunk = next(chunk for chunk in chunks if chunk["block_type"] == "figure")
    assert figure_chunk["content"] == "[教材图片：无图注]"
    assert figure_chunk["source_block_ids"] == [figure.block_id]
    assert figure_chunk["figure_id"] == figure.block_id
    assert figure_chunk["artifact_only"] is True
    assert figure_chunk["retrieval_excluded"] is True


def test_empty_caption_figure_is_persisted_but_not_forced_into_text_index(monkeypatch, tmp_path):
    from ingestion import mineru_importer

    output = tmp_path / "output"
    output.mkdir()
    _image(output / "images" / "figure.png")
    book = MinerUAdapter.from_content_list(
        [
            {"type": "text", "text_level": 1, "text": "第一章", "page_idx": 0},
            {"type": "text", "text": "正文内容足够用于索引。", "page_idx": 0},
            {"type": "image", "img_path": "images/figure.png", "page_idx": 0, "bbox": [1, 2, 3, 4]},
        ],
        book_name="Index Boundary", source_file="content_list.json",
        source_root=output, source_base=output,
    )
    captured = []

    class FakeVectorStore:
        def build_chapter_store(self, _title, chunks, chunk_roles=None, book_name=""):
            captured.extend(chunks)

    monkeypatch.setattr(mineru_importer, "get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr(mineru_importer, "load_kg_chunk_roles", lambda _book_name: {})

    count = mineru_importer.build_index_from_chapters(
        "Index Boundary", [], output, canonical_book=book,
        canonical_progress_root=tmp_path / "progress",
    )

    assert count == 1
    assert len(captured) == 1 and captured[0]["block_type"] == "paragraph"
    saved = json.loads((output / "Index Boundary_middle_chunks.json").read_text(encoding="utf-8"))
    saved_figure = next(chunk for chunk in saved if chunk["block_type"] == "figure")
    assert saved_figure["retrieval_excluded"] is True
    persisted = load_canonical_book("Index Boundary", progress_root=tmp_path / "progress")
    persisted_figure = next(block for block in persisted.blocks if block.block_type == "figure")
    assert persisted_figure.attributes["asset_status"] == "ready"
