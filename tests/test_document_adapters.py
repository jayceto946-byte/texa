import zipfile

from ingestion.document_adapters import DocxAdapter, MinerUAdapter, OcrAdapter, PdfTextAdapter
from ingestion.document_ir import validate_canonical_book


def test_pdf_chapter_adapter_preserves_chapter_pages_and_provenance():
    book = PdfTextAdapter.from_chapters(
        [{"title": "第一章 绪论", "page_number": 3, "end_page": 8, "text": "误差是测得值与真值之差。"}],
        book_name="误差理论",
        source_file="error.pdf",
        source_page_count=120,
    )

    assert [block.block_type for block in book.blocks] == ["heading", "paragraph"]
    assert book.blocks[1].section_path == ["第一章 绪论"]
    assert book.blocks[1].page_start == 3
    assert book.blocks[1].page_end == 8
    assert book.blocks[1].source_file == "error.pdf"
    assert validate_canonical_book(book).valid is True


def test_mineru_content_list_adapter_preserves_formula_table_and_zero_based_page():
    book = MinerUAdapter.from_content_list(
        [
            {"type": "text", "text_level": 1, "text": "第一章" , "page_idx": 0},
            {"type": "equation", "latex": "x = y", "page_idx": 0, "bbox": [1, 2, 3, 4]},
            {
                "type": "table", "table_caption": "表 1 数据", "table_body": "| A | B |\n|---|---|\n| 1 | 2 |",
                "page_idx": 1,
            },
        ],
        book_name="传感器",
        source_file="content_list.json",
        source_page_count=2,
    )

    formula = next(block for block in book.blocks if block.block_type == "formula")
    table = next(block for block in book.blocks if block.block_type == "table")
    assert formula.page_start == 1
    assert formula.equations == ["x = y"]
    assert formula.bbox == [1.0, 2.0, 3.0, 4.0]
    assert table.table_title == "表 1 数据"
    assert table.table_header == ["A", "B"]
    assert table.table_rows == [["1", "2"]]
    assert validate_canonical_book(book).valid is True


def test_mineru_markdown_adapter_outputs_structured_blocks(tmp_path):
    output = tmp_path / "mineru"
    output.mkdir()
    (output / "book.md").write_text(
        "# 第一章\n\n正文。\n\n$$\nx = y\n$$\n\n| 项 | 值 |\n|---|---|\n| a | 1 |",
        encoding="utf-8",
    )

    book = MinerUAdapter.from_output_dir(output, book_name="测试教材")

    assert {block.block_type for block in book.blocks} >= {"heading", "paragraph", "formula", "table"}
    table = next(block for block in book.blocks if block.block_type == "table")
    assert table.table_header == ["项", "值"]
    assert table.table_rows == [["a", "1"]]


def test_ocr_layout_adapter_maps_heading_regions_and_confidence():
    book = OcrAdapter.from_layout_pages(
        [{
            "page_idx": 0,
            "regions": [
                {"type": "title", "text": "第一章", "confidence": 0.98, "bbox": [0, 0, 10, 10]},
                {"type": "text", "text": "正文内容足够用于索引。", "confidence": 0.91, "bbox": [0, 11, 10, 30]},
            ],
        }],
        book_name="OCR 教材",
        source_file="page_001.png",
        source_page_count=1,
    )

    body = next(block for block in book.blocks if block.block_type == "paragraph")
    assert body.page_start == 1
    assert body.section_path == ["第一章"]
    assert body.ocr_confidence == 0.91
    assert validate_canonical_book(book).valid is True


def test_docx_adapter_reads_headings_paragraphs_and_tables(tmp_path):
    docx_path = tmp_path / "book.docx"
    document_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>第一章</w:t></w:r></w:p>
        <w:p><w:r><w:t>正文内容。</w:t></w:r></w:p>
        <w:tbl>
          <w:tr><w:tc><w:p><w:r><w:t>名称</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>数值</w:t></w:r></w:p></w:tc></w:tr>
          <w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc></w:tr>
        </w:tbl>
      </w:body>
    </w:document>"""
    with zipfile.ZipFile(docx_path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    book = DocxAdapter.from_docx(docx_path, book_name="Word 教材")

    assert [block.block_type for block in book.blocks] == ["heading", "paragraph", "table"]
    assert book.blocks[2].table_header == ["名称", "数值"]
    assert book.blocks[2].table_rows == [["A", "1"]]
    assert validate_canonical_book(book).valid is True
