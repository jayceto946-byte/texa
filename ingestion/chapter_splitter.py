"""章节分割器 - 将提取的章节文本切分为适合embedding的块"""
import json
import hashlib
import re
from dataclasses import replace
from pathlib import Path

from ingestion.source_spans import SPAN_SCHEMA, source_span, table_parts, table_render, table_annotations

from ingestion.document_ir import (
    CanonicalBook,
    DocumentBlock,
    PROVENANCE_SCHEMA_VERSION,
    canonical_book_fingerprint,
    canonical_retrieval_paths,
)



class ChapterSplitter:
    """章节文本分割器"""

    def __init__(self, chunk_size: int = 700, chunk_overlap: int = 80):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_chapter(self, title: str, text: str, *, book_name: str = "") -> list[dict]:
        """将单个章节切分为块
        
        Returns:
            [{"chapter": title, "chunk_index": i, "content": text}, ...]
        """
        rows: list[dict] = []
        for section_index, (section_path, section_text) in enumerate(self._sections(title, text)):
            parent_id = hashlib.md5(
                f"{book_name}|{title}|{' > '.join(section_path)}|{section_index}".encode("utf-8")
            ).hexdigest()[:16]
            for section_chunk_index, child in enumerate(self._split_preserving_equations(section_text)):
                content = child.strip()
                if not content:
                    continue
                idx = len(rows)
                chunk_id = hashlib.md5(
                    f"{book_name}|{title}|{parent_id}|{idx}|{content[:120]}".encode("utf-8")
                ).hexdigest()[:16]
                context = " > ".join(section_path)
                prefix = f"\u6559\u6750\uff1a{book_name}\n\u7ae0\u8282\u8def\u5f84\uff1a{context}\n" if book_name else f"\u7ae0\u8282\u8def\u5f84\uff1a{context}\n"
                rows.append({
                    "chapter": title,
                    "section_title": section_path[-1],
                    "section_path": section_path,
                    "chunk_index": idx,
                    "section_chunk_index": section_chunk_index,
                    "content": content,
                    "retrieval_text": f"{prefix}\u6b63\u6587\uff1a{content}",
                    "chunk_id": chunk_id,
                    "parent_id": parent_id,
                    "parent_content": section_text[:2000],
                    "equations": self._extract_equations(content),
                    "block_type": "formula" if self._extract_equations(content) else "text",
                    "review_status": "needs_formula_review" if self._formula_needs_review(content) else "",
                })
        for idx, row in enumerate(rows):
            row["prev_chunk_id"] = rows[idx - 1]["chunk_id"] if idx else ""
            row["next_chunk_id"] = rows[idx + 1]["chunk_id"] if idx + 1 < len(rows) else ""
        return rows

    def split_blocks(self, blocks: list[DocumentBlock], *, book_name: str = "") -> list[dict]:
        """Split source-neutral document blocks into retrieval chunks.

        The block boundary is authoritative for formulas and tables.  Prose is
        accumulated within one section before splitting, while examples and
        exercises retain a stable logical parent across all of their children.
        """
        rows: list[dict] = []
        prose: list[DocumentBlock] = []
        structured: list[DocumentBlock] = []
        structured_key = ""

        def flush_prose() -> None:
            nonlocal prose
            if prose:
                self._emit_block_group(rows, prose, book_name=book_name, block_type="paragraph")
                prose = []

        def flush_structured() -> None:
            nonlocal structured, structured_key
            if structured:
                self._emit_block_group(
                    rows, structured, book_name=book_name,
                    block_type=structured[0].block_type,
                )
                structured = []
                structured_key = ""

        for block in blocks:
            if not isinstance(block, DocumentBlock):
                raise TypeError("split_blocks expects DocumentBlock instances")
            if block.attributes.get('outline_toc'):
                flush_prose()
                flush_structured()
                continue
            if block.block_type == "heading" or (
                block.block_type != "figure" and not str(block.text or "").strip()
            ):
                flush_prose()
                flush_structured()
                continue

            if block.block_type == "paragraph":
                flush_structured()
                if prose and not self._can_accumulate_prose(prose[-1], block):
                    flush_prose()
                prose.append(block)
                if sum(len(item.text) for item in prose) >= self.chunk_size:
                    flush_prose()
                continue

            flush_prose()
            if block.block_type in {"example", "exercise"}:
                key = self._logical_parent_key(block)
                if structured and (structured_key != key or structured[0].block_type != block.block_type):
                    flush_structured()
                structured.append(block)
                structured_key = key
                # Blocks without an explicit grouping key are complete logical
                # examples by themselves; do not merge neighboring examples.
                if not self._explicit_parent_key(block):
                    flush_structured()
                continue

            flush_structured()
            if block.block_type == "table":
                self._emit_table(rows, block, book_name=book_name)
            else:
                # Formula and figure blocks are atomic even when they exceed
                # the configured prose chunk size.
                self._emit_atomic(rows, block, book_name=book_name)

        flush_prose()
        flush_structured()
        self._link_and_number(rows)
        return rows

    def split_canonical_book(self, book: CanonicalBook) -> list[dict]:
        """Convenience entry point for the canonical ingestion contract."""
        retrieval_paths = canonical_retrieval_paths(book.blocks)
        retrieval_blocks = [
            # A bounded unnumbered OCR title is only a producer hint. Keep its
            # text searchable even if the hint later proves to be body prose.
            replace(block, section_path=retrieval_paths.get(block.block_id, list(block.section_path)),
                    block_type='paragraph' if block.block_type == 'heading'
                    and block.attributes.get('heading_rule') == 'bounded_unnumbered' else block.block_type)
            for block in book.blocks
        ]
        rows = self.split_blocks(retrieval_blocks, book_name=book.book_name)
        canonical_hash = canonical_book_fingerprint(book)
        for row in rows:
            row["canonical_hash"] = canonical_hash
        return rows

    def _emit_block_group(
        self,
        rows: list[dict],
        blocks: list[DocumentBlock],
        *,
        book_name: str,
        block_type: str,
    ) -> None:
        text, locations = '', []
        for block in blocks:
            if not block.text:
                continue
            if text:
                text += '\n\n'
            locations.append((block, len(text), len(text) + len(block.text)))
            text += block.text
        if not text.strip():
            return
        parent_id = self._stable_id(book_name, block_type, self._logical_parent_key(blocks[0]))
        for child_index, (start, end) in enumerate(self._split_text_ranges(text)):
            spans, members = [], []
            for block, left, right in locations:
                lo, hi = max(start, left), min(end, right)
                if lo < hi:
                    members.append(block)
                    spans.append(source_span(block, lo-left, hi-left, lo-start, hi-start))
            self._append_chunk(rows, members, text[start:end], book_name=book_name, block_type=block_type,
                parent_id=parent_id, parent_content=text, child_index=child_index,
                extra={'source_span_schema': SPAN_SCHEMA, 'source_spans': spans})

    def _emit_atomic(self, rows: list[dict], block: DocumentBlock, *, book_name: str) -> None:
        content = str(block.text or "")
        if not content and block.block_type != "figure":
            return
        figure_attributes = block.attributes or {}
        extra = {'source_span_schema': SPAN_SCHEMA, 'source_spans': [source_span(block, 0, len(content), 0, len(content))]}
        if block.block_type == "figure":
            content = content or "[教材图片：无图注]"
            extra = {
                "figure_id": str(figure_attributes.get("figure_id") or block.block_id),
                "asset_relpath": str(figure_attributes.get("asset_relpath") or ""),
                "artifact_only": not bool(str(block.text or "").strip()),
                "retrieval_excluded": True,
            }
        unit_kind = 'example' if figure_attributes.get('example_id') else ('exercise' if figure_attributes.get('exercise_id') else block.block_type)
        parent_id = self._stable_id(book_name, unit_kind, self._logical_parent_key(block))
        self._append_chunk(
            rows, [block], content, book_name=book_name, block_type=block.block_type,
            parent_id=parent_id, parent_content=content, child_index=0,
            extra=extra,
        )

    def _emit_table(self, rows: list[dict], block: DocumentBlock, *, book_name: str) -> None:
        rendered = self._render_table(block)
        unit_kind = 'example' if block.attributes.get('example_id') else ('exercise' if block.attributes.get('exercise_id') else 'table')
        parent_id = self._stable_id(book_name, unit_kind, self._logical_parent_key(block))
        segments = self._split_table_rows(block, rendered)
        prefix = table_parts(block.retrieval_table_title, block.table_header, [])
        notes = table_annotations(block, table_parts(block.retrieval_table_title, block.table_header, block.table_rows)) if block.table_rows else ''
        source_cursor = len(prefix)
        for child_index, (content, table_rows) in enumerate(segments):
            spans = []
            if len(segments) == 1:
                content = rendered
                spans = [source_span(block, 0, len(rendered), 0, len(rendered))]
            else:
                if child_index == len(segments)-1 and notes:
                    content += '\n' + notes
                if prefix:
                    spans.append(source_span(block, 0, len(prefix), 0, len(prefix)))
                content_cursor = len(prefix)
                for part in [table_parts('', [], [row]) for row in table_rows] + ([notes] if child_index == len(segments)-1 and notes else []):
                    left = rendered.find(part, source_cursor)
                    at = content.find(part, content_cursor)
                    if left < 0 or at < 0:
                        raise ValueError('table source projection does not match its canonical rendering')
                    spans.append(source_span(block, left, left+len(part), at, at+len(part)))
                    source_cursor, content_cursor = left+len(part), at+len(part)
            self._append_chunk(rows, [block], content, book_name=book_name, block_type='table',
                parent_id=parent_id, parent_content=rendered, child_index=child_index,
                extra={'table_title': block.retrieval_table_title, 'table_header': list(block.table_header),
                       'table_rows': table_rows, 'source_span_schema': SPAN_SCHEMA, 'source_spans': spans})

    def _append_chunk(
        self,
        rows: list[dict],
        blocks: list[DocumentBlock],
        content: str,
        *,
        book_name: str,
        block_type: str,
        parent_id: str,
        parent_content: str,
        child_index: int,
        extra: dict | None = None,
    ) -> None:
        content = str(content or "")
        if not content.strip():
            return
        first = blocks[0]
        section_path = list(first.section_path or ([book_name] if book_name else []))
        chapter = section_path[0] if section_path else (book_name or "未命名章节")
        section_title = section_path[-1] if section_path else chapter
        source_ids = [block.block_id for block in blocks]
        chunk_id = self._stable_id(parent_id, str(child_index), "|".join(source_ids), content[:240])
        equations = self._unique_strings([
            equation for block in blocks for equation in block.equations
        ] + self._extract_equations(content))
        page_starts = [block.page_start for block in blocks if block.page_start is not None]
        page_ends = [block.page_end for block in blocks if block.page_end is not None]
        page_start = min(page_starts) if page_starts else None
        page_end = max(page_ends) if page_ends else page_start
        bbox = self._merged_bbox(blocks)
        source_kinds = self._unique_strings([block.source_kind for block in blocks])
        source_files = self._unique_strings([block.source_file for block in blocks])
        confidences = [block.ocr_confidence for block in blocks if block.ocr_confidence is not None]
        statuses = self._unique_strings([block.review_status for block in blocks])
        semantic_roles = self._unique_strings([
            str((block.attributes or {}).get("semantic_role") or "") for block in blocks
        ])
        source_markdowns = self._unique_strings([
            str((block.attributes or {}).get("source_markdown") or "") for block in blocks
        ])
        if self._formula_needs_review(content) and "needs_formula_review" not in statuses:
            statuses.append("needs_formula_review")
        path = " > ".join(section_path)
        prefix = f"教材：{book_name}\n章节路径：{path}\n" if book_name else f"章节路径：{path}\n"
        row = {
            "provenance_schema": PROVENANCE_SCHEMA_VERSION,
            "book_name": book_name,
            "chapter": chapter,
            "section_title": section_title,
            "section_path": section_path,
            "chunk_index": len(rows),
            "section_chunk_index": child_index,
            "content": content,
            "retrieval_text": f"{prefix}正文：{content}",
            "chunk_id": chunk_id,
            "parent_id": parent_id,
            "parent_content": parent_content[:4000],
            "equations": equations,
            "block_type": block_type,
            "review_status": ",".join(statuses),
            "role": semantic_roles[0] if len(semantic_roles) == 1 else "",
            "source_markdown": source_markdowns[0] if len(source_markdowns) == 1 else "",
            "page_start": page_start,
            "page_end": page_end,
            "page_idx": page_start - 1 if page_start is not None else -1,
            "bbox": bbox,
            "source_kind": source_kinds[0] if len(source_kinds) == 1 else ",".join(source_kinds),
            "source_file": source_files[0] if len(source_files) == 1 else ",".join(source_files),
            "ocr_confidence": min(confidences) if confidences else None,
            "source_block_ids": source_ids,
            "source_locations": [
                {
                    "block_id": block.block_id,
                    "source_kind": block.source_kind,
                    "source_file": block.source_file,
                    "page_start": block.page_start,
                    "page_end": block.page_end,
                    "bbox": list(block.bbox) if block.bbox else [],
                    "bbox_space": str((block.attributes or {}).get("bbox_space") or "unknown"),
                    "bbox_format": str((block.attributes or {}).get("bbox_format") or "unknown"),
                    "bbox_units": str((block.attributes or {}).get("bbox_units") or "unknown"),
                }
                for block in blocks
            ],
        }
        if extra:
            row.update(extra)
        rows.append(row)

    def _split_table_rows(self, block: DocumentBlock, rendered: str) -> list[tuple[str, list[list[str]]]]:
        if len(rendered) <= self.chunk_size or not block.table_rows:
            return [(rendered, [list(row) for row in block.table_rows])]
        title = block.retrieval_table_title
        prefix = self._render_table_parts(title, block.table_header, [])
        result: list[tuple[str, list[list[str]]]] = []
        current: list[list[str]] = []
        for row in block.table_rows:
            candidate = current + [list(row)]
            candidate_text = self._render_table_parts(title, block.table_header, candidate)
            if current and len(candidate_text) > self.chunk_size:
                result.append((self._render_table_parts(title, block.table_header, current), current))
                current = [list(row)]
            else:
                current = candidate
        if current:
            result.append((self._render_table_parts(title, block.table_header, current), current))
        return result or [(prefix or rendered, [])]

    @classmethod
    def _render_table(cls, block: DocumentBlock) -> str:
        return table_render(block)

    @staticmethod
    def _render_table_parts(title: str, header: list[str], rows: list[list[str]]) -> str:
        return table_parts(title, header, rows)

    @staticmethod
    def _explicit_parent_key(block: DocumentBlock) -> str:
        attributes = block.attributes or {}
        for name in ("parent_id", "group_id", "example_id", "exercise_id"):
            value = str(attributes.get(name) or "").strip()
            if value:
                return value
        return ""

    @classmethod
    def _logical_parent_key(cls, block: DocumentBlock) -> str:
        return cls._explicit_parent_key(block) or block.block_id

    @staticmethod
    def _can_accumulate_prose(left: DocumentBlock, right: DocumentBlock) -> bool:
        return (
            left.section_path == right.section_path
            and left.source_kind == right.source_kind
            and left.source_file == right.source_file
        )

    @staticmethod
    def _merged_bbox(blocks: list[DocumentBlock]) -> list[float]:
        boxes = [block.bbox for block in blocks if isinstance(block.bbox, list) and len(block.bbox) == 4]
        pages = {(block.page_start, block.page_end) for block in blocks}
        if not boxes or len(boxes) != len(blocks) or len(pages) != 1:
            return []
        return [
            min(float(box[0]) for box in boxes),
            min(float(box[1]) for box in boxes),
            max(float(box[2]) for box in boxes),
            max(float(box[3]) for box in boxes),
        ]

    @staticmethod
    def _stable_id(*parts: str) -> str:
        return hashlib.sha1("\0".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _unique_strings(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _link_and_number(rows: list[dict]) -> None:
        section_counts: dict[tuple[str, ...], int] = {}
        for index, row in enumerate(rows):
            row["chunk_index"] = index
            section_key = tuple(str(part) for part in row.get("section_path") or [row.get("chapter") or ""])
            row["section_chunk_index"] = section_counts.get(section_key, 0)
            section_counts[section_key] = row["section_chunk_index"] + 1
            row["prev_chunk_id"] = rows[index - 1]["chunk_id"] if index else ""
            row["next_chunk_id"] = rows[index + 1]["chunk_id"] if index + 1 < len(rows) else ""

    def _split_text_ranges(self, text: str) -> list[tuple[int, int]]:
        """Exact Unicode slices; math stays whole in source/evidence chunks.

        Dense inputs may later have several bounded views of one source chunk.
        Those views never replace the complete formula or the canonical body.
        """
        protected = [(m.start(), m.end()) for m in re.finditer(
            r'\$\$.*?\$\$|\\\[.*?\\\]|\\\(.*?\\\)|(?<!\\)\$(?!\$)[^$\n]+?(?<!\\)\$(?!\$)', text, re.S)]
        ranges, start = [], 0
        size = max(1, self.chunk_size)
        overlap = max(0, min(self.chunk_overlap, size // 2))
        while start < len(text):
            end = min(len(text), start + size)
            for left, right in protected:
                if left < end < right:
                    end = left if left > start else right
                    break
            if end < len(text) and not any(right == end for _, right in protected):
                lower = start + max(1, (end-start)//2)
                for separator in ('\n\n', '\n', '。', '；', '，', ' '):
                    cut = text.rfind(separator, lower, end)
                    candidate = cut + len(separator)
                    if cut >= lower and not any(left < candidate < right for left, right in protected):
                        end = candidate
                        break
            while end < len(text) and text[end].isspace():
                end += 1
            if not text[start:end].strip() and end < len(text):
                end += 1
            ranges.append((start, end))
            if end == len(text):
                break
            following = max(start + 1, end - overlap)
            for left, right in protected:
                if left < following < right:
                    following = left if left > start else right
                    break
            start = min(end, following)
        return ranges

    def _split_preserving_equations(self, text: str) -> list[str]:
        return [text[start:end] for start, end in self._split_text_ranges(text or '') if text[start:end].strip()]

    @staticmethod
    def _extract_equations(text: str) -> list[str]:
        return [match.strip() for match in re.findall(r"\$\$(.*?)\$\$", text or "", flags=re.DOTALL) if match.strip()]

    @staticmethod
    def _formula_needs_review(text: str) -> bool:
        if "$$" not in (text or ""):
            return False
        suspicious = (r"\operatorname { E } { \operatorname { H }", r"\ddagger", r"\sharp", "\ufffd")
        return any(marker in text for marker in suspicious)

    @staticmethod
    def _sections(title: str, text: str) -> list[tuple[list[str], str]]:
        heading = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
        path, current, result = [title], [], []

        def flush() -> None:
            body = "\n".join(current).strip()
            toc_lines = sum(
                bool(re.search(r"(?:…{2,}|\.{4,})\s*\d*\s*$", line))
                for line in body.splitlines()
            )
            if body and not (toc_lines >= 5 and len(path) == 1):
                result.append((list(path), body))
            current.clear()

        for line in (text or "").splitlines():
            match = heading.match(line)
            if not match:
                current.append(line)
                continue
            flush()
            depth = max(1, len(match.group(1)) - 1)
            path[:] = path[:depth]
            path.append(match.group(2).strip())
        flush()
        return result or [([title], (text or "").strip())]

    def split_book(self, chapters: list[dict]) -> list[dict]:
        """将整本书的所有章节切分"""
        all_chunks = []
        for ch in chapters:
            chunks = self.split_chapter(ch["title"], ch["text"])
            all_chunks.extend(chunks)
        return all_chunks

    def save_chunks(self, chunks: list[dict], output_dir: str | Path):
        """保存分割后的块到文件"""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 按章节分组保存
        by_chapter = {}
        for chunk in chunks:
            ch_name = chunk["chapter"]
            if ch_name not in by_chapter:
                by_chapter[ch_name] = []
            by_chapter[ch_name].append(chunk)

        for ch_name, ch_chunks in by_chapter.items():
            safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in ch_name)
            filepath = output_dir / f"{safe_name}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(ch_chunks, f, ensure_ascii=False, indent=2)

        # 保存完整索引
        with open(output_dir / "_all_chunks.json", "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)

        return len(chunks)
