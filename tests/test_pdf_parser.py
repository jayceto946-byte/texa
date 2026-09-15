from pathlib import Path

from ingestion.pdf_parser import PDFParser


def test_fallback_single_chapter_keeps_complete_text_and_page_range():
    parser = PDFParser.__new__(PDFParser)
    parser.pdf_path = Path("demo.pdf")
    parser.total_pages = 12
    parser.extract_text = lambda: "x" * 12_345

    chapters = parser._fallback_single_chapter()

    assert chapters == [{
        "title": "demo (全文)",
        "text": "x" * 12_345,
        "page_number": 1,
        "end_page": 12,
    }]
