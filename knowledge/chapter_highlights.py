"""Persistent chapter highlight generation from MinerU OCR output."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from config import MINERU_OUTPUT_PATH, PROGRESS_PATH
from utils.json_io import atomic_write_json
from utils.path_safety import safe_book_name, safe_child_path

from .chapter_highlight_artifacts import ChapterHighlightArtifactMixin
from .chapter_highlight_generation import ChapterHighlightGenerationMixin
from .chapter_highlight_jobs import HIGHLIGHT_JOB_TYPE, HighlightJobStore
from .chapter_highlight_latex import ChapterHighlightLatexMixin
from .chapter_highlight_source import ChapterHighlightSourceMixin
from .chapter_highlight_types import (
    PROMPT_VERSION,
    ChapterHighlightError,
    ChapterRef,
    ProgressCallback,
    SectionRef,
    _now,
)


class ChapterHighlightService(ChapterHighlightSourceMixin, ChapterHighlightGenerationMixin, ChapterHighlightLatexMixin, ChapterHighlightArtifactMixin):
    """Build source packages, run LLM generation, and store generated notes."""

    def __init__(
        self,
        progress_path: str | Path = PROGRESS_PATH,
        mineru_output_path: str | Path = MINERU_OUTPUT_PATH,
    ) -> None:
        self.progress_path = Path(progress_path)
        self.mineru_output_path = Path(mineru_output_path)

    # ------------------------------------------------------------------
    # Public paths and metadata
    # ------------------------------------------------------------------

    def book_dir(self, book_name: str) -> Path:
        return safe_child_path(self.progress_path, safe_book_name(book_name))

    def chapter_dir(self, book_name: str, chapter_id: str) -> Path:
        return safe_child_path(self.book_dir(book_name), "chapter_highlights", safe_book_name(chapter_id, "chapter"))

    def scope_dir(self, book_name: str, chapter_id: str, section_id: str | None = None) -> Path:
        base = self.chapter_dir(book_name, chapter_id)
        scope_id = self._scope_id(section_id)
        return base if scope_id == "all" else safe_child_path(base, safe_book_name(scope_id, "section"))

    @staticmethod
    def _scope_id(section_id: str | None = None) -> str:
        value = str(section_id or "").strip()
        return value if value and value != "all" else "all"

    def list_chapters(self, book_name: str) -> list[dict]:
        chapters = self._load_chapter_refs(book_name)
        return [self._chapter_status_dict(book_name, chapter) for chapter in chapters]

    def validate_scope(self, book_name: str, chapter_id: str, section_id: str | None = None) -> dict:
        chapter = self._find_chapter_ref(book_name, chapter_id)
        if not chapter:
            raise ChapterHighlightError(f"未找到章节: {chapter_id}")
        scope_id = self._scope_id(section_id)
        if scope_id != "all":
            sections = self._load_section_refs(book_name, chapter)
            if not self._find_section_ref(sections, scope_id):
                raise ChapterHighlightError(f"未找到小节: {section_id}")
        return {"chapter_id": chapter.id, "section_id": scope_id}

    def delete_highlight(self, book_name: str, chapter_id: str, section_id: str | None = None) -> dict:
        chapter = self._find_chapter_ref(book_name, chapter_id)
        resolved_chapter_id = chapter.id if chapter else chapter_id
        base = self.scope_dir(book_name, resolved_chapter_id, section_id)
        removed: list[str] = []
        for filename in ("highlight.md", "highlight.html", "highlight.json", "metadata.json", "source_package.json", "generation_checkpoint.json"):
            path = base / filename
            if path.exists() and path.is_file():
                path.unlink()
                removed.append(filename)
        return {"book_name": book_name, "chapter_id": resolved_chapter_id, "section_id": self._scope_id(section_id), "removed": removed}

    def get_highlight(self, book_name: str, chapter_id: str, section_id: str | None = None) -> dict | None:
        chapter = self._find_chapter_ref(book_name, chapter_id)
        resolved_chapter_id = chapter.id if chapter else chapter_id
        base = self.scope_dir(book_name, resolved_chapter_id, section_id)
        metadata = self._read_json(base / "metadata.json")
        highlight = self._read_json(base / "highlight.json")
        markdown_path = base / "highlight.md"
        html_path = base / "highlight.html"
        if not metadata and not highlight and not markdown_path.exists() and not html_path.exists():
            return None
        markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
        artifacts = {
            "markdown_path": str(markdown_path) if markdown_path.exists() else "",
            "html_path": str(html_path) if html_path.exists() else "",
            "html_url": self._html_url(book_name, resolved_chapter_id, section_id) if html_path.exists() else "",
        }
        return {
            "metadata": metadata or {},
            "highlight": highlight or {},
            "markdown": markdown,
            "html_path": artifacts["html_path"],
            "html_url": artifacts["html_url"],
            "artifacts": artifacts,
        }

    def mark_generation_terminal(
        self,
        book_name: str,
        chapter_id: str,
        section_id: str | None,
        *,
        status: str,
        message: str,
        create_if_missing: bool = True,
        only_if_transient: bool = False,
    ) -> dict | None:
        """Persist a failed/cancelled/interrupted generation beside its artifacts."""
        if status not in {"failed", "cancelled", "interrupted"}:
            raise ValueError(f"unsupported highlight terminal status: {status}")

        chapter = self._find_chapter_ref(book_name, chapter_id)
        resolved_chapter_id = chapter.id if chapter else chapter_id
        scope_id = self._scope_id(section_id)
        base = self.scope_dir(book_name, resolved_chapter_id, scope_id)
        metadata_path = base / "metadata.json"
        existing = self._read_json(metadata_path) or {}
        if not existing and not create_if_missing:
            return None
        if only_if_transient and existing.get("status") not in {"queued", "running", "cancelling"}:
            return existing or None

        section = None
        if chapter and scope_id != "all":
            section = self._find_section_ref(self._load_section_refs(book_name, chapter), scope_id)
        now = _now()
        metadata = {
            **existing,
            "status": status,
            "book_name": book_name,
            "chapter_id": resolved_chapter_id,
            "chapter_title": existing.get("chapter_title") or (chapter.title if chapter else ""),
            "scope_id": scope_id,
            "scope_type": existing.get("scope_type") or ("section" if scope_id != "all" else "chapter"),
            "scope_title": existing.get("scope_title") or (section.title if section else (chapter.title if chapter else "")),
            "section_id": scope_id if scope_id != "all" else "",
            "message": message,
            "error": message,
            "completed_at": now,
            "updated_at": now,
        }
        self._write_json(metadata_path, metadata)
        return metadata

    def find_latest_highlight_for_question(self, book_name: str, question: str, chapters: list[str] | None = None) -> dict | None:
        refs = self._load_chapter_refs(book_name)
        if not refs:
            return None

        candidates: list[ChapterRef] = []
        for title in chapters or []:
            matched = self._find_chapter_ref(book_name, title)
            if matched:
                candidates.append(matched)

        if not candidates:
            candidates = [chapter for chapter in refs if chapter.title and chapter.title in question]

        if not candidates:
            chapter_match = re.search(r"第\s*([一二三四五六七八九十百千万\d]+)\s*章", question)
            if chapter_match:
                needle = f"第{chapter_match.group(1)}章"
                candidates = [chapter for chapter in refs if needle in chapter.title.replace(" ", "")]

        for chapter in candidates:
            item = self.get_highlight(book_name, chapter.id)
            if item and item.get("markdown", "").strip():
                item["chapter"] = self._chapter_status_dict(book_name, chapter)
                return item
        return None


    def generate_highlight(
        self,
        book_name: str,
        chapter_id: str,
        section_id: str | None = None,
        force: bool = False,
        on_progress: ProgressCallback | None = None,
    ) -> dict:
        def progress(stage: str, message: str, percent: int | None = None) -> None:
            if on_progress:
                on_progress(stage, message, percent)

        source = self.build_source_package(book_name, chapter_id, section_id=section_id)
        chapter = source["chapter"]
        scope = source["scope"]
        base = self.scope_dir(book_name, chapter["id"], scope.get("id"))
        base.mkdir(parents=True, exist_ok=True)

        scope_label = "本节" if scope.get("type") == "section" else "本章"
        existing_meta = self._read_json(base / "metadata.json")
        if (
            not force
            and existing_meta
            and existing_meta.get("status") == "succeeded"
            and existing_meta.get("source_hash") == source["source_hash"]
            and existing_meta.get("prompt_version") == PROMPT_VERSION
            and (base / "highlight.md").exists()
            and (base / "highlight.html").exists()
        ):
            progress("cached", f"{scope_label}重点已是最新", 100)
            return self.get_highlight(book_name, chapter["id"], scope.get("id")) or {}

        progress("source", f"整理{scope_label} OCR 正文", 12)
        atomic_write_json(base / "source_package.json", source)

        self._write_json(base / "metadata.json", {
            "status": "running",
            "book_name": book_name,
            "chapter_id": chapter["id"],
            "chapter_title": chapter["title"],
            "scope_id": scope.get("id", "all"),
            "scope_type": scope.get("type", "chapter"),
            "scope_title": scope.get("title") or chapter["title"],
            "section_id": scope.get("section_id", ""),
            "source_hash": source["source_hash"],
            "prompt_version": PROMPT_VERSION,
            "started_at": _now(),
            "updated_at": _now(),
        })

        progress("sections", "按目录小节拆分生成重点", 24)
        checkpoint_path = base / "generation_checkpoint.json"
        checkpoint = self._read_json(checkpoint_path) or {}
        resumable_notes = checkpoint.get("section_notes", []) if (
            not force and checkpoint.get("source_hash") == source["source_hash"] and checkpoint.get("prompt_version") == PROMPT_VERSION
        ) else []

        def save_checkpoint(notes: list[dict]) -> None:
            self._write_json(checkpoint_path, {"source_hash": source["source_hash"], "prompt_version": PROMPT_VERSION, "section_notes": notes, "updated_at": _now()})

        section_notes = self._generate_section_notes(source, progress, resumable_notes, save_checkpoint)

        progress("combine", f"合成{scope_label}重点", 82)
        markdown = self._generate_final_markdown(source, section_notes)
        markdown = self._finalize_markdown(book_name, markdown, source)

        highlight = {
            "schema_version": 2,
            "book_name": book_name,
            "chapter": chapter,
            "scope": scope,
            "source_hash": source["source_hash"],
            "prompt_version": PROMPT_VERSION,
            "section_notes": section_notes,
            "reference_sections": source.get("reference_sections", []),
            "practice_sections": source.get("practice_sections", []),
            "image_refs": source.get("image_refs", []),
            "markdown": markdown,
            "html_path": str(base / "highlight.html"),
            "html_url": self._html_url(book_name, chapter["id"], scope.get("id")),
        }
        metadata = {
            "status": "succeeded",
            "book_name": book_name,
            "chapter_id": chapter["id"],
            "chapter_title": chapter["title"],
            "scope_id": scope.get("id", "all"),
            "scope_type": scope.get("type", "chapter"),
            "scope_title": scope.get("title") or chapter["title"],
            "section_id": scope.get("section_id", ""),
            "source_hash": source["source_hash"],
            "prompt_version": PROMPT_VERSION,
            "model": self._model_name(),
            "started_at": existing_meta.get("started_at") if existing_meta else _now(),
            "completed_at": _now(),
            "updated_at": _now(),
            "html_path": str(base / "highlight.html"),
            "html_url": self._html_url(book_name, chapter["id"], scope.get("id")),
        }

        self._write_highlight_artifacts(base, book_name, markdown, source, metadata, highlight)
        if checkpoint_path.exists():
            checkpoint_path.unlink()
        progress("completed", f"{scope_label}重点生成完成", 100)
        return {"metadata": metadata, "highlight": highlight, "markdown": markdown}




    def _read_json(self, path: Path) -> Any:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, payload)

    def _model_name(self) -> str:
        try:
            import config

            return getattr(config, "DEEPSEEK_MODEL_NAME", "") or getattr(config, "LLM_MODEL_NAME", "")
        except Exception:
            return ""
