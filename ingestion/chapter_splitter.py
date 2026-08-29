"""章节分割器 - 将提取的章节文本切分为适合embedding的块"""
import json
import hashlib
import re
from pathlib import Path

from ingestion.document_ir import CanonicalBook, DocumentBlock, PROVENANCE_SCHEMA_VERSION


def _get_splitter(chunk_size: int, chunk_overlap: int):
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "；", "，", " ", ""],
        )
    except ImportError:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "；", "，", " ", ""],
        )


class ChapterSplitter:
    """章节文本分割器"""

    def __init__(self, chunk_size: int = 700, chunk_overlap: int = 80):
        self.splitter = _get_splitter(chunk_size, chunk_overlap)
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
        return self.split_blocks(book.blocks, book_name=book.book_name)

    def _emit_block_group(
        self,
        rows: list[dict],
        blocks: list[DocumentBlock],
        *,
        book_name: str,
        block_type: str,
    ) -> None:
        text = "\n\n".join(str(block.text or "").strip() for block in blocks if str(block.text or "").strip())
        if not text:
            return
        parent_key = self._logical_parent_key(blocks[0])
        parent_id = self._stable_id(book_name, block_type, parent_key)
        for child_index, content in enumerate(self._split_preserving_equations(text)):
            self._append_chunk(
                rows, blocks, content, book_name=book_name, block_type=block_type,
                parent_id=parent_id, parent_content=text, child_index=child_index,
            )

    def _emit_atomic(self, rows: list[dict], block: DocumentBlock, *, book_name: str) -> None:
        content = str(block.text or "").strip()
        if not content and block.block_type != "figure":
            return
        figure_attributes = block.attributes or {}
        extra = None
        if block.block_type == "figure":
            content = content or "[教材图片：无图注]"
            extra = {
                "figure_id": str(figure_attributes.get("figure_id") or block.block_id),
                "asset_relpath": str(figure_attributes.get("asset_relpath") or ""),
                "artifact_only": not bool(str(block.text or "").strip()),
                "retrieval_excluded": True,
            }
        parent_id = self._stable_id(book_name, block.block_type, self._logical_parent_key(block))
        self._append_chunk(
            rows, [block], content, book_name=book_name, block_type=block.block_type,
            parent_id=parent_id, parent_content=content, child_index=0,
            extra=extra,
        )

    def _emit_table(self, rows: list[dict], block: DocumentBlock, *, book_name: str) -> None:
        rendered = self._render_table(block)
        parent_id = self._stable_id(book_name, "table", self._logical_parent_key(block))
        segments = self._split_table_rows(block, rendered)
        for child_index, (content, table_rows) in enumerate(segments):
            self._append_chunk(
                rows, [block], content, book_name=book_name, block_type="table",
                parent_id=parent_id, parent_content=rendered, child_index=child_index,
                extra={
                    "table_title": block.table_title,
                    "table_header": list(block.table_header),
                    "table_rows": table_rows,
                },
            )

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
        content = str(content or "").strip()
        if not content:
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
        prefix = self._render_table_parts(block.table_title, block.table_header, [])
        result: list[tuple[str, list[list[str]]]] = []
        current: list[list[str]] = []
        for row in block.table_rows:
            candidate = current + [list(row)]
            candidate_text = self._render_table_parts(block.table_title, block.table_header, candidate)
            if current and len(candidate_text) > self.chunk_size:
                result.append((self._render_table_parts(block.table_title, block.table_header, current), current))
                current = [list(row)]
            else:
                current = candidate
        if current:
            result.append((self._render_table_parts(block.table_title, block.table_header, current), current))
        return result or [(prefix or rendered, [])]

    @classmethod
    def _render_table(cls, block: DocumentBlock) -> str:
        if block.table_header or block.table_rows:
            return cls._render_table_parts(block.table_title, block.table_header, block.table_rows)
        return str(block.text or "").strip()

    @staticmethod
    def _render_table_parts(title: str, header: list[str], rows: list[list[str]]) -> str:
        lines = [str(title).strip()] if str(title or "").strip() else []
        if header:
            lines.append("| " + " | ".join(str(cell) for cell in header) + " |")
            lines.append("| " + " | ".join("---" for _ in header) + " |")
        lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
        return "\n".join(lines).strip()

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

    def _split_preserving_equations(self, text: str) -> list[str]:
        """Keep display-math blocks atomic while retaining normal prose splitting."""
        formulas: list[str] = []

        def protect(match: re.Match) -> str:
            formulas.append(match.group(0))
            return f"\n@@TEXA_FORMULA_{len(formulas) - 1}@@\n"

        protected = re.sub(r"\$\$.*?\$\$", protect, text or "", flags=re.DOTALL)
        chunks = self.splitter.split_text(protected)
        restored = []
        for chunk in chunks:
            for index, formula in enumerate(formulas):
                chunk = chunk.replace(f"@@TEXA_FORMULA_{index}@@", formula)
            if chunk.strip():
                restored.extend(self._bound_restored_chunk(chunk.strip()))
        return restored

    def _bound_restored_chunk(self, text: str) -> list[str]:
        """Rebound placeholder-expanded text without cutting through a formula."""
        if len(text) <= max(self.chunk_size * 2, 1200):
            return [text]
        pieces = [piece for piece in re.split(r"(\$\$.*?\$\$)", text, flags=re.DOTALL) if piece and piece.strip()]
        target = max(self.chunk_size, 700)
        result: list[str] = []
        current = ""

        def flush() -> None:
            nonlocal current
            if current.strip():
                result.append(current.strip())
            current = ""

        for piece in pieces:
            if piece.lstrip().startswith("$$"):
                if current and len(current) + len(piece) + 2 > target:
                    flush()
                current = f"{current}\n\n{piece}" if current else piece
                if len(current) >= target:
                    flush()
                continue
            prose_parts = self.splitter.split_text(piece) if len(piece) > target else [piece]
            for prose in prose_parts:
                prose = prose.strip()
                if not prose:
                    continue
                if current and len(current) + len(prose) + 2 > target:
                    flush()
                current = f"{current}\n\n{prose}" if current else prose
        flush()
        return result

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
