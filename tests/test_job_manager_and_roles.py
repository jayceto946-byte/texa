import json

import pytest

from backend.job_manager import JobCancelled, JobManager
from ingestion.chunk_roles import assign_chunk_roles, classify_chunk_role


def test_job_manager_lifecycle_and_restart_recovery(tmp_path):
    manager = JobManager(tmp_path / "jobs.sqlite3")
    job = manager.create_job(
        "textbook_import",
        {"book_name": "linear_algebra", "file_path": "book.pdf"},
        status="running",
        message="queued",
    )

    assert job["book_name"] == "linear_algebra"
    updated = manager.update_job(job["id"], stage="indexing", progress=42, message="working")
    assert updated["progress"] == 42
    assert updated["stage"] == "indexing"

    cancelling = manager.request_cancel(job["id"])
    assert cancelling["status"] == "cancelling"
    with pytest.raises(JobCancelled):
        manager.raise_if_cancelled(job["id"])

    manager.update_job(job["id"], status="cancelled", stage="cancelled", progress=100)
    assert manager.mark_running_interrupted() == 0

    running = manager.create_job("chapter_highlight", {"chapter_id": "c1"}, status="running")
    assert manager.mark_running_interrupted() == 1
    assert manager.get_job(running["id"])["status"] == "interrupted"


def test_job_manager_imports_legacy_json_jobs(tmp_path):
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    (legacy_dir / "abc.json").write_text(
        json.dumps(
            {
                "id": "abc",
                "status": "completed",
                "stage": "completed",
                "progress": 100,
                "message": "done",
                "book_name": "math",
                "result": {"indexed_chunks": 3},
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:01:00",
            }
        ),
        encoding="utf-8",
    )

    manager = JobManager(tmp_path / "jobs.sqlite3")
    assert manager.import_legacy_json_jobs("textbook_import", legacy_dir, input_keys=("book_name",)) == 1
    imported = manager.get_job("abc")
    assert imported["book_name"] == "math"
    assert imported["result"] == {"indexed_chunks": 3}


def test_chunk_role_classifier_and_kg_precedence():
    chunks = [
        {"chunk_id": "d1", "content": "定义 设 V 是向量空间，称满足条件的映射为线性变换。"},
        {"chunk_id": "e1", "content": "例题 计算矩阵 A 的特征值。\n解：令 |A-lambda I|=0。"},
        {"chunk_id": "k1", "content": "普通背景文字，没有明显角色。"},
    ]

    assert classify_chunk_role(chunks[0]["content"]) == "definition"
    assert classify_chunk_role(chunks[1]["content"]) == "example"

    roles = assign_chunk_roles(chunks, {"k1": "theorem"})
    assert roles == {"d1": "definition", "e1": "example", "k1": "theorem"}


def test_build_index_from_chapters_writes_role_metadata(monkeypatch, tmp_path):
    from ingestion import mineru_importer

    captured = []

    class FakeSplitter:
        def split_chapter(self, title, text):
            return [
                {"chapter": title, "chunk_index": 0, "content": "定义 群是满足运算封闭性的集合。", "chunk_id": "c_def"},
                {"chapter": title, "chunk_index": 1, "content": "例题 判断整数加法是否构成群。", "chunk_id": "c_ex"},
            ]

    class FakeVectorStore:
        def build_chapter_store(self, title, chunks, chunk_roles=None, book_name=""):
            captured.append((title, list(chunks), dict(chunk_roles or {}), book_name))

    monkeypatch.setattr(mineru_importer, "ChapterSplitter", FakeSplitter)
    monkeypatch.setattr(mineru_importer, "get_vector_store", lambda: FakeVectorStore())
    monkeypatch.setattr(mineru_importer, "load_kg_chunk_roles", lambda book_name: {"c_def": "theorem"})

    count = mineru_importer.build_index_from_chapters(
        "book",
        [{"title": "chapter 1", "text": "content", "page_number": 2}],
        tmp_path,
    )

    assert count == 2
    assert captured[0][2] == {"c_def": "theorem", "c_ex": "example"}
    assert captured[0][3] == "book"
    saved = json.loads((tmp_path / "book_middle_chunks.json").read_text(encoding="utf-8"))
    assert [chunk["role"] for chunk in saved] == ["theorem", "example"]
    assert saved[0]["page_idx"] == 1

def test_vector_store_collection_names_are_scoped_by_book():
    from ingestion.vector_store import ChapterVectorStore

    vs = ChapterVectorStore.__new__(ChapterVectorStore)
    chapter = "测试 章节"

    scoped_a = vs._chapter_collection_name(chapter, "book-a")
    scoped_b = vs._chapter_collection_name(chapter, "book-b")
    legacy = vs._chapter_collection_name(chapter, "")

    assert scoped_a.startswith("bk")
    assert scoped_b.startswith("bk")
    assert scoped_a != scoped_b
    assert legacy != scoped_a

    vs._map = {
        "legacy_col": {"chapter": chapter, "book_name": "", "schema_version": "1"},
        "scoped_col": {"chapter": chapter, "book_name": "book-a", "schema_version": "2"},
    }
    assert vs._title_to_collection(chapter, "book-a") == "scoped_col"
    assert vs._title_to_collection(chapter, "book-b") == "legacy_col"



def test_highlight_source_uses_external_chunks_without_page_numbers(tmp_path):
    from knowledge.chapter_highlights import ChapterHighlightService

    progress = tmp_path / "progress"
    output = tmp_path / "mineru"
    book_dir = progress / "sensor"
    external = output / "sensor" / "hybrid_auto_external"
    book_dir.mkdir(parents=True)
    external.mkdir(parents=True)
    (book_dir / "_chapters.json").write_text(
        json.dumps(
            [{
                "title": "第一章 测试",
                "page_number": 7,
                "end_page": 20,
                "subsections": [
                    {"title": "第一节 静态特性", "page": 7},
                    {"title": "第二节 动态特性", "page": 11},
                ],
            }],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (external / "sensor_middle_chunks.json").write_text(
        json.dumps(
            [
                {"chunk_id": "c0", "content": "第一章正文", "section_title": "第一章 测试", "page_idx": -1, "role": "reference"},
                {"chunk_id": "c1", "content": "静态特性定义", "section_title": "第一节 静态特性", "page_idx": -1, "role": "definition"},
                {"chunk_id": "c2", "content": "静态特性公式", "section_title": "线性度", "page_idx": -1, "role": "formula"},
                {"chunk_id": "c3", "content": "动态特性定义", "section_title": "第二节 动态特性", "page_idx": -1, "role": "definition"},
                {"chunk_id": "c4", "content": "下一章", "section_title": "第二章 其他", "page_idx": -1, "role": "reference"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service = ChapterHighlightService(progress_path=progress, mineru_output_path=output)

    chapter = service.build_source_package("sensor", "chapter_001", "all")
    section = service.build_source_package("sensor", "chapter_001", "section_001")

    assert service._find_mineru_output_dir("sensor") == external
    assert sum(len(item["chunks"]) for item in chapter["sections"]) == 4
    assert [item["text"] for item in section["sections"][0]["chunks"]] == ["第一章正文", "静态特性定义", "静态特性公式"]


def test_job_completion_and_cancellation_are_atomic(tmp_path):
    manager = JobManager(tmp_path / "jobs.sqlite3")

    cancelling = manager.create_job("textbook_import", {}, status="running")
    manager.request_cancel(cancelling["id"])
    with pytest.raises(JobCancelled):
        manager.complete_job(cancelling["id"], result={"ok": True})
    assert manager.get_job(cancelling["id"])["status"] == "cancelling"

    completed = manager.create_job("textbook_import", {}, status="running")
    manager.complete_job(completed["id"], result={"ok": True})
    assert manager.request_cancel(completed["id"])["status"] == "completed"

def test_highlight_terminal_status_replaces_running_metadata(tmp_path):
    from knowledge.chapter_highlights import ChapterHighlightService

    service = ChapterHighlightService(
        progress_path=tmp_path / "progress",
        mineru_output_path=tmp_path / "mineru",
    )
    metadata_path = service.scope_dir("sensor", "chapter_001", "all") / "metadata.json"
    service._write_json(metadata_path, {"status": "running", "source_hash": "abc"})

    service.mark_generation_terminal(
        "sensor",
        "chapter_001",
        "all",
        status="failed",
        message="model unavailable",
    )

    metadata = service._read_json(metadata_path)
    assert metadata["status"] == "failed"
    assert metadata["message"] == "model unavailable"
    assert metadata["source_hash"] == "abc"
    assert metadata["completed_at"]


def test_highlight_job_reconciles_restart_interruption(tmp_path):
    from knowledge.chapter_highlight_jobs import HIGHLIGHT_JOB_TYPE, HighlightJobStore
    from knowledge.chapter_highlights import ChapterHighlightService

    service = ChapterHighlightService(
        progress_path=tmp_path / "progress",
        mineru_output_path=tmp_path / "mineru",
    )
    metadata_path = service.scope_dir("sensor", "chapter_001", "all") / "metadata.json"
    service._write_json(metadata_path, {"status": "running"})
    manager = JobManager(tmp_path / "jobs.sqlite3")
    manager.create_job(
        HIGHLIGHT_JOB_TYPE,
        {"book_name": "sensor", "chapter_id": "chapter_001", "section_id": "all"},
        status="running",
    )
    manager.mark_running_interrupted("backend restarted")

    store = HighlightJobStore(service, job_manager=manager)
    store.reconcile_book("sensor")

    metadata = service._read_json(metadata_path)
    assert metadata["status"] == "interrupted"
    assert metadata["message"] == "backend restarted"


def test_highlight_worker_failure_and_preflight_cancel_are_terminal(tmp_path):
    from knowledge.chapter_highlight_jobs import HIGHLIGHT_JOB_TYPE, HighlightJobStore

    class FailingService:
        progress_path = tmp_path / "progress"

        @staticmethod
        def _scope_id(section_id=None):
            return section_id if section_id and section_id != "all" else "all"

        def __init__(self):
            self.generate_calls = 0
            self.terminals = []
            self.fail_terminal_write = False

        def generate_highlight(self, *args, **kwargs):
            self.generate_calls += 1
            raise RuntimeError("provider failed")

        def mark_generation_terminal(self, *args, **kwargs):
            self.terminals.append(kwargs["status"])
            if self.fail_terminal_write:
                raise OSError("metadata is read-only")

    service = FailingService()
    manager = JobManager(tmp_path / "jobs.sqlite3")
    store = HighlightJobStore(service, job_manager=manager)
    failed = manager.create_job(
        HIGHLIGHT_JOB_TYPE,
        {"book_name": "sensor", "chapter_id": "chapter_001", "section_id": "all", "force": False},
    )
    store._run_job(failed["id"])
    assert manager.get_job(failed["id"])["status"] == "failed"
    assert service.terminals == ["failed"]

    cancelled = manager.create_job(
        HIGHLIGHT_JOB_TYPE,
        {"book_name": "sensor", "chapter_id": "chapter_002", "section_id": "all", "force": False},
    )
    manager.request_cancel(cancelled["id"])
    service.fail_terminal_write = True
    store._run_job(cancelled["id"])
    assert manager.get_job(cancelled["id"])["status"] == "cancelled"
    assert service.generate_calls == 1
    assert service.terminals == ["failed", "cancelled"]

    # Metadata repair is best-effort and cannot break chapter-list requests.
    store.reconcile_book("sensor")
