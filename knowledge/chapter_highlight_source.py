"""Source package assembly for chapter highlight generation."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from config import MINERU_OUTPUT_PATH
from utils.path_safety import safe_book_name
from .chapter_highlight_types import ChapterHighlightError, ChapterRef, SectionRef, PROMPT_VERSION


class ChapterHighlightSourceMixin:
    """Loads OCR output, chapter metadata, sections, images, and source hashes."""

    def _workflow_chapters(self, book_name: str) -> list[dict]:
        from ingestion.document_workflows import enrich_chapters, load_workflow_book
        data = self._read_json(self.book_dir(book_name) / '_chapters.json')
        return enrich_chapters(data if isinstance(data, list) else [],
                               load_workflow_book(book_name, progress_root=self.progress_path))

    def _sections_from_canonical(self, book_name: str, chapter: ChapterRef) -> list[dict]:
        from ingestion.document_workflows import load_workflow_book
        from ingestion.document_ir import canonical_retrieval_paths, canonical_chapter_title
        book = load_workflow_book(book_name, progress_root=self.progress_path)
        if book is None:
            return []
        paths = canonical_retrieval_paths(book.blocks)
        target = canonical_chapter_title(chapter.title) or chapter.title
        chunks = []
        for block in book.blocks:
            path = paths.get(block.block_id) or [book_name]
            if path[0] != target or block.block_type in {'heading', 'figure'} or not block.text.strip():
                continue
            chunks.append(dict(chunk_id=f'canonical:{block.block_id}', block_id=block.block_id,
                               text=block.text, page=block.page_start,
                               role=block.attributes.get('semantic_role', ''),
                               source_ref=f'{block.source_file} / p{block.page_start}',
                               source_section_title=path[-1]))
        return [dict(title=chapter.title, chunks=chunks)] if chunks else []

    def build_source_package(self, book_name: str, chapter_id: str, section_id: str | None = None) -> dict:
        chapter = self._find_chapter_ref(book_name, chapter_id)
        if not chapter:
            raise ChapterHighlightError(f"未找到章节: {chapter_id}")

        subsection_refs = self._load_section_refs(book_name, chapter)
        output_dir = self._find_mineru_output_dir(book_name)
        content_items = self._load_first_json(output_dir, ["*content_list*.json", "*content-list*.json"]) if output_dir else None
        native_chunks = self._load_first_json(output_dir, ["*middle_chunks*.json"]) if output_dir else None

        raw_sections = self._sections_from_canonical(book_name, chapter)
        if not raw_sections:
            raw_sections = self._sections_from_chunks(native_chunks, chapter, subsection_refs)
        if not raw_sections:
            raw_sections = self._sections_from_saved_chapters(book_name, chapter)
        if not raw_sections and isinstance(content_items, list):
            raw_sections = self._sections_from_content_list(content_items, chapter)
        if not raw_sections:
            raise ChapterHighlightError("未找到可用于生成重点的 OCR 正文")

        sections, reference_sections, scope = self._apply_scope(raw_sections, subsection_refs, chapter, section_id)
        if not sections:
            raise ChapterHighlightError("所选章节范围内没有可用于生成重点的 OCR 正文")

        image_refs = self._image_refs_from_content_list(content_items, chapter, output_dir)
        image_refs = self._filter_image_refs_for_sections(image_refs, sections + reference_sections)
        practice_sections = []
        if self._scope_id(section_id) == "all":
            practice_sections = [
                self._section_from_page_range(raw_sections, section)
                for section in subsection_refs
                if section.is_auxiliary and self._is_exercise_section(section.title)
            ]
            practice_sections = [section for section in practice_sections if section.get("chunks")]

        source = {
            "schema_version": 2,
            "prompt_version": PROMPT_VERSION,
            "book_name": book_name,
            "chapter": self._chapter_to_dict(chapter, subsection_refs),
            "scope": scope,
            "mineru_output_dir": str(output_dir) if output_dir else "",
            "sections": sections,
            "reference_sections": reference_sections,
            "practice_sections": practice_sections,
            "image_refs": image_refs,
        }
        source["source_hash"] = self._source_hash(source)
        return source

    def _load_chapter_refs(self, book_name: str) -> list[ChapterRef]:
        data = self._workflow_chapters(book_name)
        if not isinstance(data, list):
            return []
        refs: list[ChapterRef] = []
        for index, item in enumerate(data):
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            page = int(item.get("page_number", item.get("page", 1)) or 1)
            end_page = item.get("end_page")
            refs.append(ChapterRef(id=f"chapter_{index + 1:03d}", index=index, title=title, page=page, end_page=int(end_page) if end_page else None))
        return refs

    def _load_chapter_record(self, book_name: str, chapter: ChapterRef) -> dict:
        data = self._workflow_chapters(book_name)
        if isinstance(data, list) and 0 <= chapter.index < len(data) and isinstance(data[chapter.index], dict):
            return data[chapter.index]
        return {}

    def _load_section_refs(self, book_name: str, chapter: ChapterRef) -> list[SectionRef]:
        record = self._load_chapter_record(book_name, chapter)
        raw_sections = record.get("subsections") if isinstance(record, dict) else None
        if not isinstance(raw_sections, list):
            return []
        refs: list[SectionRef] = []
        cleaned: list[tuple[str, int, dict]] = []
        for item in raw_sections:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            try:
                page = int(item.get("page", item.get("page_number", chapter.page)) or chapter.page)
            except Exception:
                page = chapter.page
            cleaned.append((title, page, item))

        for index, (title, page, item) in enumerate(cleaned):
            next_page = cleaned[index + 1][1] if index + 1 < len(cleaned) else None
            end_page = item.get('end_page') or chapter.end_page or page
            if not item.get('end_page') and next_page and next_page > page:
                end_page = next_page - 1
            refs.append(SectionRef(
                id=f"heading_{item['heading_block_id']}" if item.get('heading_block_id') else f"section_{index + 1:03d}",
                index=index,
                title=title,
                page=page,
                end_page=end_page,
                is_auxiliary=self._is_auxiliary_section(title),
                heading_block_id=item.get('heading_block_id', ''), level=item.get('level', 2),
                source_block_ids=list(item.get('source_block_ids') or []),
            ))
        return refs

    def _find_chapter_ref(self, book_name: str, key: str) -> ChapterRef | None:
        refs = self._load_chapter_refs(book_name)
        key = str(key or "").strip()
        if not key:
            return refs[0] if refs else None
        for chapter in refs:
            if key in {chapter.id, chapter.title, str(chapter.index), str(chapter.index + 1)}:
                return chapter
        compact_key = re.sub(r"\s+", "", key)
        for chapter in refs:
            if compact_key and compact_key in re.sub(r"\s+", "", chapter.title):
                return chapter
        return None

    def _find_section_ref(self, refs: list[SectionRef], key: str | None) -> SectionRef | None:
        scope_id = self._scope_id(key)
        if scope_id == "all":
            return None
        compact_key = self._normalize_title(scope_id)
        for section in refs:
            if scope_id in {section.id, section.title, str(section.index), str(section.index + 1)}:
                return section
        for section in refs:
            if compact_key and compact_key in self._normalize_title(section.title):
                return section
        return None

    def _chapter_status_dict(self, book_name: str, chapter: ChapterRef) -> dict:
        subsections = self._load_section_refs(book_name, chapter)
        status = self._scope_status_dict(book_name, chapter.id, None)
        return {
            "id": chapter.id,
            "index": chapter.index,
            "title": chapter.title,
            "page": chapter.page,
            "end_page": chapter.end_page,
            "highlight_status": status["highlight_status"],
            "generated_at": status["generated_at"],
            "message": status["message"],
            "html_url": status.get("html_url", ""),
            "html_path": status.get("html_path", ""),
            "markdown_path": status.get("markdown_path", ""),
            "storage_dir": status.get("storage_dir", ""),
            "subsections": [self._section_status_dict(book_name, chapter, section) for section in subsections],
        }

    def _scope_status_dict(self, book_name: str, chapter_id: str, section_id: str | None = None) -> dict:
        base = self.scope_dir(book_name, chapter_id, section_id)
        metadata = self._read_json(base / "metadata.json") or {}
        source_package = self._read_json(base / "source_package.json") or {}
        markdown_path = base / "highlight.md"
        html_path = base / "highlight.html"
        current_hash = source_package.get("source_hash")
        status = metadata.get("status") or "not_generated"
        stale = bool(current_hash and metadata.get("source_hash") and current_hash != metadata.get("source_hash"))
        if status == "succeeded" and metadata.get("prompt_version") != PROMPT_VERSION:
            stale = True
        if status == "succeeded" and not html_path.exists():
            stale = True
        return {
            "highlight_status": "stale" if stale else status,
            "generated_at": metadata.get("completed_at") or metadata.get("updated_at") or "",
            "message": metadata.get("message", ""),
            "html_url": self._html_url(book_name, chapter_id, section_id) if html_path.exists() else "",
            "html_path": str(html_path) if html_path.exists() else "",
            "markdown_path": str(markdown_path) if markdown_path.exists() else "",
            "storage_dir": str(base) if base.exists() else "",
        }

    def _section_status_dict(self, book_name: str, chapter: ChapterRef, section: SectionRef) -> dict:
        status = self._scope_status_dict(book_name, chapter.id, section.id)
        payload = self._section_to_dict(section)
        payload.update(status)
        return payload

    def _chapter_to_dict(self, chapter: ChapterRef, subsections: list[SectionRef]) -> dict:
        return {
            "id": chapter.id,
            "index": chapter.index,
            "title": chapter.title,
            "page": chapter.page,
            "end_page": chapter.end_page,
            "subsections": [self._section_to_dict(section) for section in subsections],
        }

    def _section_to_dict(self, section: SectionRef) -> dict:
        return {
            "id": section.id,
            "index": section.index,
            "title": section.title,
            "page": section.page,
            "end_page": section.end_page,
            "is_auxiliary": section.is_auxiliary,
            "level": section.level,
            "heading_block_id": section.heading_block_id,
        }

    def _apply_scope(
        self,
        raw_sections: list[dict],
        subsection_refs: list[SectionRef],
        chapter: ChapterRef,
        section_id: str | None = None,
    ) -> tuple[list[dict], list[dict], dict]:
        scope_id = self._scope_id(section_id)
        if scope_id != "all":
            selected = self._find_section_ref(subsection_refs, scope_id)
            if not selected:
                raise ChapterHighlightError(f"未找到小节: {section_id}")
            section = self._section_from_page_range(raw_sections, selected)
            if not section.get("chunks"):
                raise ChapterHighlightError(f"所选小节没有可用于生成重点的 OCR 正文: {selected.title}")
            scope = {
                "id": selected.id,
                "type": "section",
                "chapter_id": chapter.id,
                "chapter_title": chapter.title,
                "section_id": selected.id,
                "title": selected.title,
                "page": selected.page,
                "end_page": selected.end_page,
            }
            return [section], [], scope

        content_refs = [section for section in subsection_refs if not section.is_auxiliary]
        if content_refs and any(section.heading_block_id for section in content_refs):
            level = min(section.level for section in content_refs)
            content_refs = [section for section in content_refs if section.level == level]
        if content_refs:
            scoped_sections = [self._section_from_page_range(raw_sections, section) for section in content_refs]
            scoped_sections = [section for section in scoped_sections if section.get("chunks")]
            reference_sections = [
                self._section_from_page_range(raw_sections, section)
                for section in subsection_refs
                if section.is_auxiliary and self._is_study_points_section(section.title)
            ]
            reference_sections = [section for section in reference_sections if section.get("chunks")]
            if scoped_sections:
                scope = {
                    "id": "all",
                    "type": "chapter",
                    "chapter_id": chapter.id,
                    "chapter_title": chapter.title,
                    "title": chapter.title,
                    "page": chapter.page,
                    "end_page": chapter.end_page,
                    "section_count": len(scoped_sections),
                }
                return scoped_sections, reference_sections, scope

        fallback_sections = []
        for index, section in enumerate(raw_sections):
            copied = dict(section)
            copied.setdefault("id", f"auto_{index + 1:03d}")
            copied.setdefault("index", index)
            copied.setdefault("page", self._first_chunk_page(copied))
            copied.setdefault("end_page", self._last_chunk_page(copied))
            copied.setdefault("is_auxiliary", False)
            fallback_sections.append(copied)
        scope = {
            "id": "all",
            "type": "chapter",
            "chapter_id": chapter.id,
            "chapter_title": chapter.title,
            "title": chapter.title,
            "page": chapter.page,
            "end_page": chapter.end_page,
            "section_count": len(fallback_sections),
        }
        return fallback_sections, [], scope

    def _section_from_page_range(self, raw_sections: list[dict], section_ref: SectionRef) -> dict:
        chunks: list[dict] = []
        end_page = section_ref.end_page or section_ref.page
        for source_section in raw_sections:
            for chunk in source_section.get("chunks", []):
                try:
                    page = int(chunk.get("page") or 0)
                except Exception:
                    page = 0
                in_scope = (chunk.get('block_id') in section_ref.source_block_ids
                            if section_ref.source_block_ids else section_ref.page <= page <= end_page)
                if in_scope:
                    copied = dict(chunk)
                    copied.setdefault("source_section_title", source_section.get("title", ""))
                    chunks.append(copied)
        return {
            "id": section_ref.id,
            "index": section_ref.index,
            "title": section_ref.title,
            "page": section_ref.page,
            "end_page": end_page,
            "is_auxiliary": section_ref.is_auxiliary,
            "chunks": chunks,
        }

    def _filter_image_refs_for_sections(self, images: list[dict], sections: list[dict]) -> list[dict]:
        if not images:
            return []
        pages = {
            int(chunk.get("page"))
            for section in sections
            for chunk in section.get("chunks", [])
            if str(chunk.get("page", "")).isdigit()
        }
        ranges: list[tuple[int, int]] = []
        for section in sections:
            try:
                start = int(section.get("page") or 0)
                end = int(section.get("end_page") or start or 0)
            except Exception:
                continue
            if start:
                ranges.append((start, max(start, end)))
        if not pages and not ranges:
            return images

        result = []
        for image in images:
            try:
                page = int(image.get("page") or 0)
            except Exception:
                page = 0
            if page in pages or any(start <= page <= end for start, end in ranges):
                result.append(image)
        return result

    def _normalize_title(self, value: str) -> str:
        return re.sub(r"\s+", "", str(value or "")).replace("?", "").replace("?", "")

    def _is_auxiliary_section(self, title: str) -> bool:
        compact = self._normalize_title(title)
        return any(token in compact for token in ("本章学习要点", "学习要点", "习题", "复习题", "思考题"))

    def _is_study_points_section(self, title: str) -> bool:
        compact = self._normalize_title(title)
        return "学习要点" in compact or "本章要点" in compact

    def _is_exercise_section(self, title: str) -> bool:
        compact = self._normalize_title(title)
        return any(token in compact for token in ("习题", "练习题", "复习题", "思考题", "例题"))

    def _first_chunk_page(self, section: dict) -> int | None:
        pages = [chunk.get("page") for chunk in section.get("chunks", []) if chunk.get("page")]
        return int(pages[0]) if pages else None

    def _last_chunk_page(self, section: dict) -> int | None:
        pages = [chunk.get("page") for chunk in section.get("chunks", []) if chunk.get("page")]
        return int(pages[-1]) if pages else None

    def _find_mineru_output_dir(self, book_name: str) -> Path | None:
        safe_name = safe_book_name(book_name)
        candidates = [
            self.mineru_output_path / safe_name / "hybrid_auto_external",
            self.mineru_output_path / safe_name / "hybrid_auto",
            self.mineru_output_path / safe_name,
            self.mineru_output_path / "hybrid_auto_external" / safe_name,
            self.progress_path.parent.parent / "mineru_output" / safe_name / "hybrid_auto_external",
            self.progress_path.parent.parent / "mineru_output" / safe_name / "hybrid_auto",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        if self.mineru_output_path.exists():
            for candidate in list(self.mineru_output_path.glob(f"*/hybrid_auto_external")) + list(self.mineru_output_path.glob(f"*/hybrid_auto")):
                if candidate.parent.name in {book_name, safe_name}:
                    return candidate
        return None

    def _sections_from_chunks(
        self,
        chunks: Any,
        chapter: ChapterRef,
        subsection_refs: list[SectionRef] | None = None,
    ) -> list[dict]:
        if not isinstance(chunks, list):
            return []
        result: list[dict] = []
        current: dict | None = None
        target_chapter = self._normalize_title(chapter.title)
        section_pages = [
            (self._normalize_title(section.title), section.page)
            for section in (subsection_refs or [])
            if self._normalize_title(section.title)
        ]
        inside_page_less_chapter = False
        inferred_page = chapter.page

        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            title = str(chunk.get("section_title") or "").strip()
            normalized_title = self._normalize_title(title)
            page = self._page_from_record(chunk)

            if page <= 0:
                is_chapter_heading = bool(re.match(r"^第[一二三四五六七八九十百千0-9]+章", normalized_title))
                if is_chapter_heading:
                    matches_target = normalized_title == target_chapter or normalized_title in target_chapter or target_chapter in normalized_title
                    if matches_target:
                        inside_page_less_chapter = True
                        inferred_page = chapter.page
                    elif inside_page_less_chapter:
                        break
                    else:
                        continue
                elif not inside_page_less_chapter:
                    continue

                for section_title, section_page in section_pages:
                    if normalized_title == section_title or normalized_title in section_title or section_title in normalized_title:
                        inferred_page = section_page
                        break
                page = inferred_page
            elif not self._page_in_chapter(page, chapter):
                continue

            text = str(chunk.get("text") or chunk.get("content") or "").strip()
            if not text:
                continue
            if not title or title == "(no title)":
                title = chapter.title
            if current is None or current["title"] != title:
                current = {"title": title, "chunks": []}
                result.append(current)
            current["chunks"].append({
                "chunk_id": str(chunk.get("chunk_id") or f"p{page}_c{len(current['chunks'])}"),
                "text": text,
                "page": page,
                "bbox": chunk.get("bbox"),
                "has_equation": bool(chunk.get("has_equation")),
                "equations": chunk.get("equations") or [],
                "role": self._infer_chunk_role(text, str(chunk.get("role") or "")),
                "source_ref": self._source_ref(chunk, page),
            })
        return result
    def _sections_from_saved_chapters(self, book_name: str, chapter: ChapterRef) -> list[dict]:
        data = self._read_json(self.book_dir(book_name) / "_chapters.json")
        if not isinstance(data, list) or chapter.index >= len(data):
            return []
        text = str(data[chapter.index].get("text") or "").strip()
        if not text:
            return []
        chunks = self._split_text_for_source(text, 2500)
        return [{
            "title": chapter.title,
            "chunks": [
                {
                    "chunk_id": f"{chapter.id}_part_{idx + 1}",
                    "text": chunk,
                    "page": chapter.page,
                    "bbox": None,
                    "has_equation": "$" in chunk,
                    "equations": [],
                    "role": self._infer_chunk_role(chunk),
                    "source_ref": f"{chapter.title} p{chapter.page}",
                }
                for idx, chunk in enumerate(chunks)
            ],
        }]

    def _sections_from_content_list(self, items: Any, chapter: ChapterRef) -> list[dict]:
        if not isinstance(items, list):
            return []
        sections: list[dict] = []
        current = {"title": chapter.title, "chunks": []}
        sections.append(current)
        for item in items:
            if not isinstance(item, dict):
                continue
            page = self._page_from_record(item)
            if not self._page_in_chapter(page, chapter):
                continue
            text = self._item_text(item)
            if not text:
                continue
            if item.get("type") == "text" and isinstance(item.get("text_level"), int) and len(text) <= 80:
                current = {"title": text, "chunks": []}
                sections.append(current)
                continue
            current["chunks"].append({
                "chunk_id": f"p{page}_i{len(current['chunks'])}",
                "text": text,
                "page": page,
                "bbox": item.get("bbox"),
                "has_equation": "$" in text,
                "equations": [],
                "role": self._infer_chunk_role(text, str(item.get("type") or "")),
                "source_ref": f"p{page}",
            })
        return [section for section in sections if section["chunks"]]

    def _image_refs_from_content_list(self, items: Any, chapter: ChapterRef, output_dir: Path | None = None) -> list[dict]:
        if not isinstance(items, list):
            return []
        images: list[dict] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_path = self._image_path_from_item(item)
            if not raw_path:
                continue
            page = self._page_from_record(item)
            if not self._page_in_chapter(page, chapter):
                continue
            asset_path = self._normalize_asset_path(raw_path, output_dir)
            if not asset_path or asset_path in seen:
                continue
            seen.add(asset_path)
            caption = self._caption_text(item) or self._nearby_caption_text(items, item)
            images.append({
                "id": f"img_{len(images) + 1:03d}",
                "path": asset_path,
                "page": page,
                "bbox": item.get("bbox"),
                "caption": caption,
                "source_type": item.get("type", ""),
            })
        return images

    def _image_path_from_item(self, item: dict) -> str:
        for key in ("img_path", "image_path", "path", "src", "file_path", "image", "resized_path"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                suffix = Path(value).suffix.lower()
                if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
                    return value.strip()
        return ""

    def _normalize_asset_path(self, raw_path: str, output_dir: Path | None) -> str:
        value = str(raw_path or "").strip().replace("\\", "/")
        if not value:
            return ""
        try:
            path = Path(value)
            if path.is_absolute() and output_dir:
                return path.resolve().relative_to(output_dir.resolve()).as_posix()
        except Exception:
            pass
        return value.lstrip("./")

    def _nearby_caption_text(self, items: list[dict], target: dict) -> str:
        try:
            idx = items.index(target)
        except ValueError:
            return ""
        page = self._page_from_record(target)
        candidates: list[str] = []
        for item in items[max(0, idx - 2): idx + 3]:
            if not isinstance(item, dict) or item is target:
                continue
            if self._page_from_record(item) != page:
                continue
            text = self._caption_text(item) or str(item.get("text") or "").strip()
            if text and any(token in text for token in ("图", "表", "Figure", "Table")):
                candidates.append(text)
        return " ".join(candidates[:2])

    def _image_in_section(self, image: dict, section: dict) -> bool:
        try:
            page = int(image.get("page") or 0)
        except Exception:
            return False
        start = int(section.get("page") or 0)
        end = int(section.get("end_page") or start or 0)
        if start and start <= page <= end:
            return True
        return self._page_in_section(page, section)

    def _looks_like_problem(self, text: str) -> bool:
        return bool(re.search(r"(^|\n)\s*(例\s*\d*|例题|习题|练习|思考题|证明|求解|计算|判断|设\s)", text))

    def _infer_chunk_role(self, text: str, explicit: str = "") -> str:
        role = explicit.strip().lower()
        if role in {"definition", "theorem", "proof", "derivation", "algorithm", "example", "exercise", "formula", "property", "reference"}:
            return role
        stripped = str(text or "").strip()
        if self._looks_like_problem(stripped):
            if re.search(r"(^|\n)\s*(习题|练习|思考题)", stripped):
                return "exercise"
            return "example"
        if re.search(r"定义|称为|叫做", stripped[:120]):
            return "definition"
        if re.search(r"定理|性质|命题|推论", stripped[:120]):
            return "theorem"
        if re.search(r"证明|证：|证:|推导", stripped[:160]):
            return "proof"
        if re.search(r"步骤|算法|流程|迭代", stripped[:160]):
            return "algorithm"
        if "$" in stripped or "公式" in stripped[:120]:
            return "formula"
        return "reference"

    def _source_hash(self, source: dict) -> str:
        payload = json.dumps(
            {
                "prompt_version": PROMPT_VERSION,
                "book_name": source.get("book_name"),
                "chapter": source.get("chapter"),
                "scope": source.get("scope"),
                "sections": source.get("sections"),
                "reference_sections": source.get("reference_sections"),
                "practice_sections": source.get("practice_sections"),
                "image_refs": source.get("image_refs"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _page_in_section(self, page: Any, section: dict) -> bool:
        try:
            page_int = int(page)
        except Exception:
            return False
        pages = [chunk.get("page") for chunk in section.get("chunks", [])]
        return page_int in pages

    def _page_in_chapter(self, page: int, chapter: ChapterRef) -> bool:
        end_page = chapter.end_page or chapter.page
        return chapter.page <= page <= end_page

    def _page_from_record(self, record: dict) -> int:
        try:
            if "page_idx" in record:
                return int(record.get("page_idx") or 0) + 1
            return max(1, int(record.get("page", 1) or 1))
        except Exception:
            return 1

    def _source_ref(self, chunk: dict, page: int) -> str:
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        return f"{chunk_id or 'chunk'} / p{page}"

    def _item_text(self, item: dict) -> str:
        parts: list[str] = []
        for key in ("text", "code_body", "latex"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        for key in ("table_caption", "table_footnote", "image_caption", "image_footnote"):
            value = item.get(key)
            if isinstance(value, list):
                parts.extend(str(v).strip() for v in value if str(v).strip())
            elif isinstance(value, str) and value.strip():
                parts.append(value.strip())
        return "\n".join(parts)

    def _caption_text(self, item: dict) -> str:
        parts: list[str] = []
        for key in ("image_caption", "image_footnote"):
            value = item.get(key)
            if isinstance(value, list):
                parts.extend(str(v).strip() for v in value if str(v).strip())
            elif isinstance(value, str) and value.strip():
                parts.append(value.strip())
        return " ".join(parts)

    def _split_text_for_source(self, text: str, max_chars: int) -> list[str]:
        paragraphs = re.split(r"\n{2,}", text)
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if current and len(current) + len(paragraph) + 2 > max_chars:
                chunks.append(current.strip())
                current = ""
            current += ("\n\n" if current else "") + paragraph
        if current.strip():
            chunks.append(current.strip())
        return chunks

    def _load_first_json(self, output_dir: Path | None, patterns: list[str]) -> Any:
        if not output_dir or not output_dir.exists():
            return None
        for pattern in patterns:
            for path in output_dir.rglob(pattern):
                try:
                    return json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
        return None
