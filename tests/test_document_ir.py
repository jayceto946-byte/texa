import json

from ingestion.document_ir import (
    CanonicalBook,
    DocumentBlock,
    canonical_paths,
    load_canonical_book,
    persist_canonical_book,
    validate_canonical_book,
)


def _book(*, blocks=None):
    return CanonicalBook(
        book_name="测试教材",
        source_kind="markdown",
        parser_version="markdown-adapter-v1",
        warnings=["page 8 image-only"],
        blocks=blocks or [
            DocumentBlock(
                block_id="b1",
                block_type="formula",
                text="误差公式：$$\\Delta = x - x_0$$",
                section_path=["第一章", "误差定义"],
                page_start=3,
                page_end=3,
                bbox=[10.0, 20.0, 200.0, 80.0],
                equations=["\\Delta = x - x_0"],
                source_file="chapter_01.md",
                source_kind="markdown",
                attributes={"source_block_index": 7},
            ),
        ],
    )


def test_persisted_document_ir_round_trips_with_report(tmp_path):
    report = persist_canonical_book(_book(), progress_root=tmp_path)
    document_path, report_path = canonical_paths("测试教材", progress_root=tmp_path)

    assert report.valid is True
    assert document_path.exists()
    assert report_path.exists()
    lines = document_path.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["record_type"] == "canonical_book"
    assert json.loads(lines[1])["record_type"] == "document_block"
    assert json.loads(report_path.read_text(encoding="utf-8"))["summary"] == {"errors": 0, "warnings": 0}

    loaded = load_canonical_book("测试教材", progress_root=tmp_path)
    assert loaded.book_name == "测试教材"
    assert loaded.blocks[0].equations == ["\\Delta = x - x_0"]
    assert loaded.blocks[0].attributes == {"source_block_index": 7}


def test_invalid_ir_is_reported_and_persisted_for_diagnosis(tmp_path):
    invalid = _book(blocks=[
        DocumentBlock(
            block_id="duplicate",
            block_type="paragraph",
            text="正文",
            section_path=[],
            page_start=8,
            page_end=7,
            source_kind="ocr",
            ocr_confidence=1.2,
        ),
        DocumentBlock(
            block_id="duplicate",
            block_type="unknown",
            text="另一段",
            section_path=["第一章"],
            source_kind="",
        ),
    ])

    report = persist_canonical_book(invalid, progress_root=tmp_path)
    codes = {issue.code for issue in report.issues}

    assert report.valid is False
    assert {"missing_section_path", "invalid_page_range", "invalid_ocr_confidence"} <= codes
    assert {"duplicate_block_id", "unsupported_block_type", "missing_block_source_kind"} <= codes
    assert load_canonical_book("测试教材", progress_root=tmp_path).blocks[1].block_type == "unknown"


def test_validation_requires_book_level_provenance():
    report = validate_canonical_book(CanonicalBook(
        book_name="",
        source_kind="",
        parser_version="",
        blocks=[],
    ))

    assert report.valid is False
    assert {issue.code for issue in report.issues} >= {
        "missing_book_name", "missing_source_kind", "missing_parser_version", "empty_book",
    }


def test_intake_quality_warnings_mark_formula_and_do_not_block_usable_book():
    book = CanonicalBook(
        book_name="扫描教材",
        source_kind="ocr",
        parser_version="ocr-adapter-v1",
        source_page_count=3,
        blocks=[
            DocumentBlock(
                block_id="h1",
                block_type="heading",
                text="第一章",
                section_path=["第一章"],
                page_start=1,
                page_end=1,
                source_kind="ocr",
                ocr_confidence=0.99,
            ),
            DocumentBlock(
                block_id="formula",
                block_type="formula",
                text="推导 $$ x = y",
                section_path=["第一章", "1.1"],
                page_start=2,
                page_end=2,
                source_kind="ocr",
                ocr_confidence=0.99,
            ),
            DocumentBlock(
                block_id="table",
                block_type="table",
                text="数据表",
                section_path=["第一章", "1.2"],
                page_start=4,
                page_end=4,
                source_kind="ocr",
                ocr_confidence=0.99,
            ),
            DocumentBlock(
                block_id="jump",
                block_type="heading",
                text="过深标题",
                section_path=["第一章", "1.2", "第一章", "i"],
                page_start=3,
                page_end=3,
                source_kind="ocr",
                ocr_confidence=0.99,
            ),
        ],
    )

    report = validate_canonical_book(book)
    codes = {issue.code for issue in report.issues}

    assert report.valid is True
    assert "needs_formula_review" in book.blocks[1].review_status
    assert {
        "unbalanced_formula_delimiters", "table_without_title", "table_without_header",
        "table_without_rows", "page_outside_source", "heading_depth_jump", "heading_cycle",
        "ocr_page_without_body",
    } <= codes


def test_book_with_no_usable_body_is_blocked():
    report = validate_canonical_book(CanonicalBook(
        book_name="空教材",
        source_kind="ocr",
        parser_version="ocr-adapter-v1",
        blocks=[DocumentBlock(
            block_id="cover",
            block_type="figure",
            text="封面图片",
            section_path=["封面"],
            source_kind="ocr",
        )],
    ))

    assert report.valid is False
    assert "no_usable_body" in {issue.code for issue in report.issues}
