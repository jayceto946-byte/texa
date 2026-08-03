import json
import zipfile

import pytest


def test_import_textbook_from_markdown_output(monkeypatch, tmp_path):
    from ingestion import mineru_importer

    output_dir = tmp_path / "mineru_out"
    output_dir.mkdir()
    (output_dir / "book.md").write_text(
        "# 第一章 绪论\n定义：线性规划研究目标函数和约束。\n\n# 第二章 单纯形法\n例题：求最优解。",
        encoding="utf-8",
    )
    captured = []

    class FakeSplitter:
        def split_chapter(self, title, text):
            return [{"chapter": title, "chunk_index": 0, "content": text, "chunk_id": title}]

    class FakeVectorStore:
        def build_chapter_store(self, title, chunks, chunk_roles=None, book_name=""):
            captured.append((title, list(chunks), dict(chunk_roles or {}), book_name))

    monkeypatch.setattr(mineru_importer, "ChapterSplitter", FakeSplitter)
    monkeypatch.setattr(mineru_importer, "get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr(mineru_importer, "load_kg_chunk_roles", lambda book_name: {})

    result = mineru_importer.import_textbook_from_mineru_output(output_dir, "demo")

    assert result.used_mineru is True
    assert result.indexed_chunks == 2
    assert [chapter["title"] for chapter in result.chapters] == ["第一章 绪论", "第二章 单纯形法"]
    assert [item[0] for item in captured] == ["第一章 绪论", "第二章 单纯形法"]
    assert {item[3] for item in captured} == {"demo"}
    saved = json.loads((output_dir / "demo_middle_chunks.json").read_text(encoding="utf-8"))
    assert len(saved) == 2


def test_external_output_zip_rejects_path_traversal(tmp_path):
    from backend.api import books

    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../evil.md", "oops")

    with pytest.raises(ValueError):
        books._extract_zip_safe(archive, tmp_path / "target")


def test_import_textbook_routes_to_runtime_api_config(monkeypatch, tmp_path):
    from ingestion import mineru_importer

    monkeypatch.setattr(mineru_importer.config, "MINERU_API_URL", "http://mineru.test")
    monkeypatch.setattr(mineru_importer.config, "MINERU_CLI_COMMAND", "mineru {input}")
    monkeypatch.setattr(mineru_importer, "_import_with_mineru", lambda *args: "api")
    monkeypatch.setattr(mineru_importer, "_import_with_mineru_cli", lambda *args: "cli")

    assert mineru_importer.import_textbook(tmp_path / "book.pdf", "book") == "api"


def test_import_textbook_routes_to_runtime_cli_config(monkeypatch, tmp_path):
    from ingestion import mineru_importer

    monkeypatch.setattr(mineru_importer.config, "MINERU_API_URL", "")
    monkeypatch.setattr(mineru_importer.config, "MINERU_CLI_COMMAND", "mineru -p {input} -o {output}")
    monkeypatch.setattr(mineru_importer, "_import_with_mineru_cli", lambda *args: "cli")

    assert mineru_importer.import_textbook(tmp_path / "book.pdf", "book") == "cli"


def test_import_textbook_requires_configured_mineru_backend(monkeypatch, tmp_path):
    from ingestion import mineru_importer

    monkeypatch.setattr(mineru_importer.config, "MINERU_API_URL", "")
    monkeypatch.setattr(mineru_importer.config, "MINERU_CLI_COMMAND", "")

    with pytest.raises(RuntimeError, match="MINERU_API_URL.*MINERU_CLI_COMMAND"):
        mineru_importer.import_textbook(tmp_path / "book.pdf", "book", require_mineru=True)


def test_explicit_local_parse_bypasses_configured_mineru(monkeypatch, tmp_path):
    from ingestion import mineru_importer

    monkeypatch.setattr(mineru_importer.config, "MINERU_API_URL", "http://mineru.test")
    monkeypatch.setattr(
        mineru_importer,
        "_import_with_mineru",
        lambda *args: pytest.fail("explicit local parsing must not call MinerU"),
    )
    monkeypatch.setattr(mineru_importer, "import_textbook_local", lambda *args: "local")

    assert mineru_importer.import_textbook(tmp_path / "book.pdf", "book", parse_method="local") == "local"


def test_auto_parse_falls_back_to_local_without_mineru(monkeypatch, tmp_path):
    from ingestion import mineru_importer

    monkeypatch.setattr(mineru_importer.config, "MINERU_API_URL", "")
    monkeypatch.setattr(mineru_importer.config, "MINERU_CLI_COMMAND", "")
    monkeypatch.setattr(mineru_importer, "import_textbook_local", lambda *args: "local")

    assert mineru_importer.import_textbook(tmp_path / "book.pdf", "book", parse_method="auto") == "local"
