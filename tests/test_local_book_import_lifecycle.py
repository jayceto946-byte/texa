from io import BytesIO
from types import SimpleNamespace

from fastapi import UploadFile


def _configure_import(monkeypatch, tmp_path):
    import backend.api.books as books

    monkeypatch.setattr(books, "BOOKS_PATH", tmp_path / "books")
    monkeypatch.setattr(books, "BOOK_UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(books, "_known_book_names", lambda **_kwargs: [])
    monkeypatch.setattr(books, "_save_chapters", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(books, "_write_book_meta", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(books, "_book_subject", lambda _name: "数学")
    monkeypatch.setattr(books, "_start_optional_concept_extraction", lambda *_args, **_kwargs: (None, ""))
    monkeypatch.setattr(books, "import_textbook_local", lambda path, name, **_kwargs: SimpleNamespace(
        chapters=[{"title": "第一章"}],
        used_mineru=False,
        message="ok",
        output_dir=str(tmp_path / "output" / name),
    ))
    return books


def test_local_import_promotes_pdf_before_exposing_book(monkeypatch, tmp_path):
    books = _configure_import(monkeypatch, tmp_path)
    current = {}
    monkeypatch.setattr(
        books,
        "_set_current_book",
        lambda name, chapters, pdf: current.update(name=name, chapters=chapters, pdf=pdf),
    )
    upload = UploadFile(filename="demo.pdf", file=BytesIO(b"pdf"))

    result = books.import_book_local(upload, subject="数学")

    final_pdf = tmp_path / "books" / "demo.pdf"
    assert result["success"] is True
    assert final_pdf.read_bytes() == b"pdf"
    assert not (tmp_path / "uploads" / "demo.pdf").exists()
    assert current["pdf"] == final_pdf


def test_local_import_invokes_compensation_with_promoted_pdf(monkeypatch, tmp_path):
    books = _configure_import(monkeypatch, tmp_path)
    cleanup = {}
    monkeypatch.setattr(books, "_save_chapters", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))
    monkeypatch.setattr(
        books,
        "_cleanup_new_book_import",
        lambda name, staged, final: cleanup.update(name=name, staged=staged, final=final),
    )
    upload = UploadFile(filename="demo.pdf", file=BytesIO(b"pdf"))

    result = books.import_book_local(upload, subject="数学")

    assert result["success"] is False
    assert cleanup["name"] == "demo"
    assert cleanup["final"] == tmp_path / "books" / "demo.pdf"
