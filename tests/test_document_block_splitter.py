import zipfile

from ingestion.chapter_splitter import ChapterSplitter
from ingestion.document_adapters import DocxAdapter, MinerUAdapter, OcrAdapter, PdfTextAdapter
from ingestion.document_ir import DocumentBlock


def _block(block_id: str, block_type: str, text: str, **kwargs) -> DocumentBlock:
    return DocumentBlock(
        block_id=block_id,
        block_type=block_type,
        text=text,
        section_path=kwargs.pop("section_path", ["第一章", "第一节"]),
        source_file=kwargs.pop("source_file", "book.source"),
        source_kind=kwargs.pop("source_kind", "fixture"),
        **kwargs,
    )


def _assert_closed_neighbors(chunks: list[dict]) -> None:
    for index, chunk in enumerate(chunks):
        assert chunk["chunk_index"] == index
        assert chunk["prev_chunk_id"] == (chunks[index - 1]["chunk_id"] if index else "")
        assert chunk["next_chunk_id"] == (chunks[index + 1]["chunk_id"] if index + 1 < len(chunks) else "")


def test_formula_is_atomic_and_source_metadata_is_inherited():
    formula = "$$" + "x_1+x_2=" + "a" * 180 + "$$"
    block = _block(
        "formula-1", "formula", formula,
        page_start=4, page_end=4, bbox=[1, 2, 30, 40], equations=["x_1+x_2"],
        review_status="checked", source_kind="mineru", source_file="content_list.json",
    )

    chunks = ChapterSplitter(chunk_size=60, chunk_overlap=10).split_blocks([block], book_name="误差理论")

    assert len(chunks) == 1
    assert chunks[0]["content"] == formula
    assert chunks[0]["block_type"] == "formula"
    assert chunks[0]["page_idx"] == 3
    assert chunks[0]["page_start"] == 4
    assert chunks[0]["bbox"] == [1.0, 2.0, 30.0, 40.0]
    assert chunks[0]["source_kind"] == "mineru"
    assert "x_1+x_2" in chunks[0]["equations"]


def test_oversized_table_splits_only_by_row_and_repeats_title_and_header():
    rows = [[f"测点 {index}", "v" * 24] for index in range(8)]
    block = _block(
        "table-1", "table", "source table",
        table_title="表 1 测量值", table_header=["测点", "结果"], table_rows=rows,
    )

    chunks = ChapterSplitter(chunk_size=100, chunk_overlap=10).split_blocks([block], book_name="误差理论")

    assert len(chunks) > 1
    assert all("表 1 测量值" in chunk["content"] for chunk in chunks)
    assert all("| 测点 | 结果 |" in chunk["content"] for chunk in chunks)
    assert all(chunk["parent_id"] == chunks[0]["parent_id"] for chunk in chunks)
    assert [row for chunk in chunks for row in chunk["table_rows"]] == rows
    _assert_closed_neighbors(chunks)


def test_example_parts_share_parent_and_paragraphs_accumulate_with_traceability():
    blocks = [
        _block("p1", "paragraph", "第一段。", page_start=2, page_end=2),
        _block("p2", "paragraph", "第二段。", page_start=3, page_end=3),
        _block("e1", "example", "题干：求测量结果。", attributes={"group_id": "example-7"}),
        _block("e2", "example", "条件：已知三次测量值。", attributes={"group_id": "example-7"}),
        _block("e3", "example", "答案：取算术平均值。", attributes={"group_id": "example-7"}),
    ]

    chunks = ChapterSplitter(chunk_size=200, chunk_overlap=20).split_blocks(blocks, book_name="误差理论")

    prose = [chunk for chunk in chunks if chunk["block_type"] == "paragraph"]
    examples = [chunk for chunk in chunks if chunk["block_type"] == "example"]
    assert len(prose) == 1
    assert "第一段。\n\n第二段。" == prose[0]["content"]
    assert prose[0]["page_start"] == 2 and prose[0]["page_end"] == 3
    assert prose[0]["source_block_ids"] == ["p1", "p2"]
    assert examples
    assert len({chunk["parent_id"] for chunk in examples}) == 1
    assert all("题干" in chunk["parent_content"] and "答案" in chunk["parent_content"] for chunk in examples)
    _assert_closed_neighbors(chunks)


def test_pdf_mineru_and_ocr_adapters_share_the_block_splitter_contract():
    pdf = PdfTextAdapter.from_chapters(
        [{"title": "第一章", "page_number": 3, "end_page": 4, "text": "正文内容。"}],
        book_name="文本 PDF", source_file="book.pdf",
    )
    mineru = MinerUAdapter.from_content_list(
        [
            {"type": "text", "text_level": 1, "text": "第一章", "page_idx": 0},
            {"type": "equation", "latex": "y=ax+b", "page_idx": 0},
            {
                "type": "table", "table_caption": "表 1", "page_idx": 1,
                "table_body": "| 名称 | 值 |\n|---|---|\n| A | 1 |",
            },
        ],
        book_name="MinerU 教材", source_file="content_list.json",
    )
    ocr = OcrAdapter.from_layout_pages(
        [{
            "page_idx": 0,
            "regions": [
                {"type": "title", "text": "第一章", "confidence": 0.99},
                {"type": "text", "text": "扫描正文内容足够用于索引。", "confidence": 0.92},
            ],
        }],
        book_name="OCR 教材", source_file="page.png", source_page_count=1,
    )

    splitter = ChapterSplitter(chunk_size=80, chunk_overlap=10)
    for book in (pdf, mineru, ocr):
        chunks = splitter.split_canonical_book(book)
        assert chunks
        assert all(chunk["section_path"] for chunk in chunks)
        assert all(chunk["source_kind"] for chunk in chunks)
        assert all(chunk["source_file"] for chunk in chunks)
        _assert_closed_neighbors(chunks)

    mineru_chunks = splitter.split_canonical_book(mineru)
    assert len([chunk for chunk in mineru_chunks if chunk["block_type"] == "formula"]) == 1
    assert next(chunk for chunk in mineru_chunks if chunk["block_type"] == "table")["table_header"] == ["名称", "值"]


def test_docx_heading_table_and_example_fixture_reaches_uniform_chunks(tmp_path):
    docx_path = tmp_path / "fixture.docx"
    document_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>第一章</w:t></w:r></w:p>
        <w:p><w:r><w:t>例题 1：计算平均值。</w:t></w:r></w:p>
        <w:p><w:r><w:t>条件：有三次测量结果。</w:t></w:r></w:p>
        <w:p><w:r><w:t>答案：取三次测量的算术平均。</w:t></w:r></w:p>
        <w:tbl>
          <w:tr><w:tc><w:p><w:r><w:t>测次</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>结果</w:t></w:r></w:p></w:tc></w:tr>
          <w:tr><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>10</w:t></w:r></w:p></w:tc></w:tr>
        </w:tbl>
      </w:body>
    </w:document>"""
    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    book = DocxAdapter.from_docx(docx_path, book_name="Word 教材")
    chunks = ChapterSplitter(chunk_size=100, chunk_overlap=10).split_canonical_book(book)

    assert all(chunk["section_path"] == ["第一章"] for chunk in chunks)
    table = next(chunk for chunk in chunks if chunk["block_type"] == "table")
    assert table["table_header"] == ["测次", "结果"]
    assert table["table_rows"] == [["1", "10"]]
    assert all(chunk["source_kind"] == "docx" for chunk in chunks)
    examples = [chunk for chunk in chunks if chunk["block_type"] == "example"]
    assert examples and len({chunk["parent_id"] for chunk in examples}) == 1
    assert "例题 1" in examples[0]["parent_content"] and "答案" in examples[0]["parent_content"]
    _assert_closed_neighbors(chunks)


def test_index_builder_prefers_canonical_blocks_and_persists_provenance(monkeypatch, tmp_path):
    from ingestion import mineru_importer

    book = MinerUAdapter.from_content_list(
        [
            {"type": "text", "text_level": 1, "text": "第一章", "page_idx": 0},
            {"type": "equation", "latex": "u=\u0305x", "page_idx": 2, "bbox": [1, 2, 3, 4]},
        ],
        book_name="统一索引", source_file="content_list.json", source_page_count=3,
    )
    captured: list[dict] = []

    class FakeVectorStore:
        def build_chapter_store(self, _title, chunks, chunk_roles=None, book_name=""):
            captured.extend(chunks)

    monkeypatch.setattr(mineru_importer, "get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr(mineru_importer, "load_kg_chunk_roles", lambda _book_name: {})

    count = mineru_importer.build_index_from_chapters(
        "统一索引",
        [{"title": "错误的旧章节", "text": "不应进入新索引"}],
        tmp_path,
        canonical_book=book,
        canonical_progress_root=tmp_path / "progress",
    )

    assert count == 1
    assert len(captured) == 1
    assert captured[0]["chapter"] == "第一章"
    assert captured[0]["block_type"] == "formula"
    assert captured[0]["page_start"] == 3
    assert captured[0]["source_file"] == "content_list.json"
    assert "不应进入新索引" not in captured[0]["content"]
    assert (tmp_path / "progress" / "统一索引" / "canonical_document.jsonl").exists()
