"""Canonical Figure lookup, bounded context assembly, and deterministic crops."""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import tempfile
import threading
from typing import Any, Iterator
import unicodedata
from urllib.parse import quote

from PIL import Image, ImageOps

from config import PROGRESS_PATH
from ingestion.document_ir import (
    CanonicalBook,
    DocumentBlock,
    PROVENANCE_SCHEMA_VERSION,
    canonical_book_fingerprint,
    canonical_paths,
    load_canonical_book,
)
from ingestion.index_pipeline import INDEX_SCHEMA_VERSION, load_index_manifest
from ingestion.lexical_index import load_book_index


MAX_FIGURE_ASSET_BYTES = 25 * 1024 * 1024
MAX_FIGURE_PIXELS = 60_000_000
MIN_REGION_FRACTION = 0.005
MIN_REGION_PIXELS = 8
MAX_CACHED_FIGURE_BOOKS = 8


class FigureIndexOutOfDateError(RuntimeError):
    """The active index cannot prove a mapping to the current Canonical IR."""


@dataclass(frozen=True)
class NormalizedBBox:
    """Image-relative xyxy coordinates in [0, 1]."""

    x1: float
    y1: float
    x2: float
    y2: float

    @classmethod
    def from_values(cls, values: list[float] | tuple[float, ...]) -> "NormalizedBBox":
        if len(values) != 4:
            raise ValueError("bbox 必须包含四个归一化坐标 [x1, y1, x2, y2]")
        try:
            bbox = cls(*(float(value) for value in values))
        except (TypeError, ValueError) as exc:
            raise ValueError("bbox 坐标必须是数字") from exc
        if not all(0.0 <= value <= 1.0 for value in (bbox.x1, bbox.y1, bbox.x2, bbox.y2)):
            raise ValueError("bbox 坐标必须位于 [0, 1]")
        if bbox.x2 <= bbox.x1 or bbox.y2 <= bbox.y1:
            raise ValueError("bbox 必须满足 x2 > x1 且 y2 > y1")
        if bbox.x2 - bbox.x1 < MIN_REGION_FRACTION or bbox.y2 - bbox.y1 < MIN_REGION_FRACTION:
            raise ValueError("选区过小，请扩大后重试")
        return bbox

    def to_list(self) -> list[float]:
        return [self.x1, self.y1, self.x2, self.y2]

    def covers_almost_full_image(self) -> bool:
        return self.x1 <= 0.005 and self.y1 <= 0.005 and self.x2 >= 0.995 and self.y2 >= 0.995


@dataclass(frozen=True)
class FigureContextPackage:
    figure: dict[str, Any]
    nearby_blocks: list[dict[str, Any]]
    related_chunk_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "figure": dict(self.figure),
            "nearby_blocks": [dict(item) for item in self.nearby_blocks],
            "related_chunk_ids": list(self.related_chunk_ids),
        }


@dataclass
class _FigureBookCacheEntry:
    signature: tuple[int, int, str]
    canonical_hash: str
    index_version: str
    book: CanonicalBook
    block_positions: dict[str, int]
    figures: list[tuple[int, DocumentBlock]]
    chunks: list[dict[str, Any]] | None = None
    chunks_by_id: dict[str, dict[str, Any]] | None = None
    block_chunk_ids: dict[str, list[str]] | None = None
    chunk_order: dict[str, int] | None = None


class FigureLearningService:
    _cache_lock = threading.RLock()
    _book_cache: "OrderedDict[tuple[str, str], _FigureBookCacheEntry]" = OrderedDict()

    def __init__(self, progress_root: str | Path = PROGRESS_PATH) -> None:
        self.progress_root = Path(progress_root)

    def _cache_key(self, book_name: str) -> tuple[str, str]:
        return str(self.progress_root.resolve()), book_name

    def _source_signature(self, book_name: str) -> tuple[int, int, str]:
        document_path, _report_path = canonical_paths(book_name, progress_root=self.progress_root)
        stat = document_path.stat()
        index_version = str(load_index_manifest(book_name).get("index_version") or "")
        return stat.st_mtime_ns, stat.st_size, index_version

    def _cache_entry(self, book_name: str) -> _FigureBookCacheEntry:
        name = str(book_name or "").strip()
        if not name:
            raise ValueError("book_name 不能为空")
        key = self._cache_key(name)
        signature = self._source_signature(name)
        with self._cache_lock:
            cached = self._book_cache.get(key)
            if cached is not None and cached.signature == signature:
                self._book_cache.move_to_end(key)
                return cached

            document_path, _report_path = canonical_paths(name, progress_root=self.progress_root)
            book = load_canonical_book(name, progress_root=self.progress_root)
            canonical_hash = canonical_book_fingerprint(book)
            block_positions = {
                block.block_id: index for index, block in enumerate(book.blocks) if block.block_id
            }
            figures = [
                (index, block) for index, block in enumerate(book.blocks) if block.block_type == "figure"
            ]
            entry = _FigureBookCacheEntry(
                signature=signature,
                canonical_hash=canonical_hash,
                index_version=signature[2],
                book=book,
                block_positions=block_positions,
                figures=figures,
            )
            self._book_cache[key] = entry
            self._book_cache.move_to_end(key)
            while len(self._book_cache) > MAX_CACHED_FIGURE_BOOKS:
                self._book_cache.popitem(last=False)
            return entry

    def _ensure_chunk_index(self, entry: _FigureBookCacheEntry) -> None:
        if entry.chunks is not None:
            return
        with self._cache_lock:
            if entry.chunks is not None:
                return
            manifest = load_index_manifest(entry.book.book_name)
            active_version = str(manifest.get("index_version") or "")
            if (
                int(manifest.get("schema_version", 0) or 0) != INDEX_SCHEMA_VERSION
                or str(manifest.get("provenance_schema") or "") != PROVENANCE_SCHEMA_VERSION
                or not active_version
            ):
                raise FigureIndexOutOfDateError(
                    "figure_index_out_of_date: active schema-6 provenance index required"
                )
            if str(manifest.get("canonical_hash") or "") != entry.canonical_hash:
                raise FigureIndexOutOfDateError(
                    "figure_index_out_of_date: Canonical IR differs from the active index"
                )
            chunks = load_book_index(entry.book.book_name)
            if not chunks:
                raise FigureIndexOutOfDateError(
                    "figure_index_out_of_date: active lexical catalog is unavailable"
                )
            block_chunk_ids: dict[str, list[str]] = {}
            chunk_order: dict[str, int] = {}
            chunks_by_id: dict[str, dict[str, Any]] = {}
            for chunk_index, chunk in enumerate(chunks):
                chunk_id = str(chunk.get("chunk_id") or "")
                if not chunk_id:
                    raise FigureIndexOutOfDateError(
                        "figure_index_out_of_date: active catalog contains an anonymous chunk"
                    )
                if (
                    str(chunk.get("provenance_schema") or "") != PROVENANCE_SCHEMA_VERSION
                    or str(chunk.get("index_version") or "") != active_version
                    or str(chunk.get("canonical_hash") or "") != entry.canonical_hash
                ):
                    raise FigureIndexOutOfDateError(
                        "figure_index_out_of_date: active catalog provenance mismatch"
                    )
                chunk_order[chunk_id] = chunk_index
                chunks_by_id[chunk_id] = chunk
                for block_id in chunk.get("source_block_ids") or []:
                    block_key = str(block_id or "")
                    if block_key and chunk_id not in block_chunk_ids.setdefault(block_key, []):
                        block_chunk_ids[block_key].append(chunk_id)
            missing_figures = [
                block.block_id for _position, block in entry.figures
                if block.block_id not in block_chunk_ids
            ]
            if missing_figures:
                raise FigureIndexOutOfDateError(
                    f"figure_index_out_of_date: active catalog is missing Figure blocks {missing_figures[:3]}"
                )
            entry.chunks = chunks
            entry.chunks_by_id = chunks_by_id
            entry.block_chunk_ids = block_chunk_ids
            entry.chunk_order = chunk_order

    def load_book(self, book_name: str) -> CanonicalBook:
        return self._cache_entry(book_name).book

    def cache_metadata(self, book_name: str) -> dict[str, Any]:
        entry = self._cache_entry(book_name)
        return {
            "canonical_hash": entry.canonical_hash,
            "index_version": entry.index_version,
            "figure_count": len(entry.figures),
            "chunk_count": len(entry.chunks or []),
            "chunk_index_ready": entry.chunks is not None,
        }

    def list_figures(
        self,
        book_name: str,
        *,
        offset: int = 0,
        limit: int = 50,
        query: str = "",
    ) -> dict[str, Any]:
        entry = self._cache_entry(book_name)
        book = entry.book
        needle = self._normalize_search_text(query)
        terms = [term for term in needle.split() if term]
        ranked: list[tuple[int, int, dict[str, Any]]] = []
        for index, block in entry.figures:
            payload = self._figure_payload(book, block)
            if not needle:
                ranked.append((0, index, payload))
                continue
            caption_text = self._normalize_search_text(" ".join([
                str(payload.get("caption") or ""), str(payload.get("source_text") or ""),
            ]))
            section_text = self._normalize_search_text(" ".join(payload.get("section_path") or []))
            nearby_text = self._normalize_search_text(self._search_context(book, index))
            combined = " ".join([caption_text, section_text, nearby_text, str(payload.get("page") or "")])
            required = terms or [needle]
            if not all(term in combined for term in required):
                continue
            score = sum(4 for term in required if term in caption_text)
            score += sum(3 for term in required if term in section_text)
            score += sum(1 for term in required if term in nearby_text)
            if needle in caption_text:
                score += 8
                payload["match_scope"] = "caption"
            elif needle in section_text:
                score += 6
                payload["match_scope"] = "section"
            else:
                payload["match_scope"] = "nearby_text"
            ranked.append((score, index, payload))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        figures = [item[2] for item in ranked]
        start = max(0, int(offset or 0))
        size = min(100, max(1, int(limit or 50)))
        return {"items": figures[start:start + size], "total": len(figures), "offset": start, "limit": size}

    def get_figure(self, book_name: str, figure_id: str) -> tuple[CanonicalBook, DocumentBlock, dict[str, Any]]:
        entry = self._cache_entry(book_name)
        book = entry.book
        target = str(figure_id or "").strip()
        position = entry.block_positions.get(target)
        if position is not None:
            block = book.blocks[position]
            if block.block_type == "figure":
                return book, block, self._figure_payload(book, block)
        raise KeyError(f"Figure not found: {target}")

    def asset_path(self, book_name: str, figure_id: str) -> Path:
        _book, _block, payload = self.get_figure(book_name, figure_id)
        relpath = str(payload.get("asset_relpath") or "").replace("\\", "/").strip()
        rel = PurePosixPath(relpath)
        if not relpath or rel.is_absolute() or ".." in rel.parts or not relpath.startswith("figures/"):
            raise FileNotFoundError("Figure 没有可用的受控资产")
        document_path, _report_path = canonical_paths(book_name, progress_root=self.progress_root)
        book_root = document_path.parent.resolve()
        path = (book_root / Path(*rel.parts)).resolve()
        try:
            path.relative_to(book_root)
        except ValueError as exc:
            raise PermissionError("Figure 资产路径越界") from exc
        if not path.is_file():
            raise FileNotFoundError("Figure 资产文件不存在")
        if path.stat().st_size > MAX_FIGURE_ASSET_BYTES:
            raise ValueError("Figure 资产超过允许大小")
        return path

    def build_context(
        self,
        book_name: str,
        figure_id: str,
        *,
        neighbor_count: int = 3,
        max_text_chars: int = 6000,
    ) -> FigureContextPackage:
        entry = self._cache_entry(book_name)
        self._ensure_chunk_index(entry)
        book, figure, payload = self.get_figure(book_name, figure_id)
        figure_chunk_ids = list((entry.block_chunk_ids or {}).get(figure.block_id) or [])
        figure_row = (entry.chunks_by_id or {}).get(figure_chunk_ids[0], {}) if figure_chunk_ids else {}
        payload = {
            **payload,
            "provenance_schema": PROVENANCE_SCHEMA_VERSION,
            "index_version": entry.index_version,
            "canonical_hash": entry.canonical_hash,
            "chunk_ids": figure_chunk_ids,
            "source_block_ids": list(figure_row.get("source_block_ids") or [figure.block_id]),
            "source_locations": list(figure_row.get("source_locations") or []),
        }
        figure_index = entry.block_positions[figure.block_id]
        before: list[DocumentBlock] = []
        after: list[DocumentBlock] = []
        for block in reversed(book.blocks[:figure_index]):
            if self._nearby_text_candidate(block, figure):
                before.append(block)
            if len(before) >= neighbor_count:
                break
        before.reverse()
        for block in book.blocks[figure_index + 1:]:
            if self._nearby_text_candidate(block, figure):
                after.append(block)
            if len(after) >= neighbor_count:
                break
        selected = before + after
        remaining = max(500, int(max_text_chars))
        nearby: list[dict[str, Any]] = []
        for block in selected:
            text = str(block.text or "").strip()
            if not text or remaining <= 0:
                continue
            bounded = text[:remaining]
            remaining -= len(bounded)
            nearby.append({
                "block_id": block.block_id,
                "block_type": block.block_type,
                "text": bounded,
                "page": block.page_start,
                "page_idx": block.page_start - 1 if block.page_start is not None else None,
                "section_path": list(block.section_path),
                "chunk_ids": list((entry.block_chunk_ids or {}).get(block.block_id) or []),
            })
            chunk_ids = nearby[-1]["chunk_ids"]
            source_row = (entry.chunks_by_id or {}).get(chunk_ids[0], {}) if chunk_ids else {}
            nearby[-1].update({
                "provenance_schema": source_row.get("provenance_schema", ""),
                "index_version": source_row.get("index_version", ""),
                "canonical_hash": source_row.get("canonical_hash", ""),
                "source_block_ids": list(source_row.get("source_block_ids") or [block.block_id]),
                "source_locations": list(source_row.get("source_locations") or []),
                "source_kind": source_row.get("source_kind", block.source_kind),
                "source_file": source_row.get("source_file", block.source_file),
                "bbox": list(source_row.get("bbox") or []),
            })

        source_ids = {figure.block_id, *(item["block_id"] for item in nearby)}
        related_chunk_ids = sorted(
            {
                chunk_id
                for block_id in source_ids
                for chunk_id in (entry.block_chunk_ids or {}).get(block_id, [])
            },
            key=lambda chunk_id: (entry.chunk_order or {}).get(chunk_id, len(entry.chunk_order or {})),
        )
        return FigureContextPackage(payload, nearby, related_chunk_ids)

    @staticmethod
    def evidence_sources(context: FigureContextPackage) -> list[dict[str, Any]]:
        """Expose the Figure and its nearby text as distinct citation targets."""
        figure = context.figure
        section_path = list(figure.get("section_path") or [])
        sources: list[dict[str, Any]] = [{
            "id": "E1",
            "chunk_id": (figure.get("chunk_ids") or [""])[0],
            "figure_id": figure.get("figure_id") or "",
            "book_name": figure.get("book_name") or "",
            "chapter": section_path[0] if section_path else figure.get("book_name") or "",
            "section_title": section_path[-1] if section_path else figure.get("book_name") or "",
            "section_path": section_path,
            "page_idx": figure.get("page_idx"),
            "caption": figure.get("caption") or "",
            "label": f"Figure {figure.get('figure_id') or ''}".strip(),
            "asset_url": figure.get("image_url") or "",
            "pdf_url": figure.get("pdf_url") or "",
            "provenance_schema": figure.get("provenance_schema") or "",
            "index_version": figure.get("index_version") or "",
            "canonical_hash": figure.get("canonical_hash") or "",
            "source_block_ids": list(figure.get("source_block_ids") or []),
            "source_locations": list(figure.get("source_locations") or []),
            "source_kind": figure.get("source_kind") or "",
            "source_file": figure.get("source_file") or "",
            "bbox": list(figure.get("page_bbox") or []),
        }]
        for index, block in enumerate(context.nearby_blocks, start=2):
            block_path = list(block.get("section_path") or section_path)
            chunk_ids = list(block.get("chunk_ids") or [])
            sources.append({
                "id": f"E{index}",
                "chunk_id": chunk_ids[0] if chunk_ids else "",
                "block_id": block.get("block_id") or "",
                "book_name": figure.get("book_name") or "",
                "chapter": block_path[0] if block_path else figure.get("book_name") or "",
                "section_title": block_path[-1] if block_path else figure.get("book_name") or "",
                "section_path": block_path,
                "page_idx": block.get("page_idx"),
                "label": "Figure 邻近正文",
                "text": block.get("text") or "",
                "provenance_schema": block.get("provenance_schema") or "",
                "index_version": block.get("index_version") or "",
                "canonical_hash": block.get("canonical_hash") or "",
                "source_block_ids": list(block.get("source_block_ids") or []),
                "source_locations": list(block.get("source_locations") or []),
                "source_kind": block.get("source_kind") or "",
                "source_file": block.get("source_file") or "",
                "bbox": list(block.get("bbox") or []),
            })
        return sources

    @contextmanager
    def cropped_region(
        self,
        book_name: str,
        figure_id: str,
        bbox: NormalizedBBox,
    ) -> Iterator[tuple[Path, dict[str, Any]]]:
        source = self.asset_path(book_name, figure_id)
        temp_path: Path | None = None
        try:
            with Image.open(source) as opened:
                if opened.width * opened.height > MAX_FIGURE_PIXELS:
                    raise ValueError("Figure 像素数量超过安全限制")
                image = ImageOps.exif_transpose(opened).convert("RGB")
                width, height = image.size
                left = max(0, min(width - 1, round(bbox.x1 * width)))
                top = max(0, min(height - 1, round(bbox.y1 * height)))
                right = max(left + 1, min(width, round(bbox.x2 * width)))
                bottom = max(top + 1, min(height, round(bbox.y2 * height)))
                if right - left < MIN_REGION_PIXELS or bottom - top < MIN_REGION_PIXELS:
                    raise ValueError("选区像素尺寸过小，请扩大后重试")
                crop = image.crop((left, top, right, bottom))
                with tempfile.NamedTemporaryFile(prefix="texa-figure-region-", suffix=".png", delete=False) as temp:
                    temp_path = Path(temp.name)
                crop.save(temp_path, format="PNG", optimize=True)
            yield temp_path, {
                "normalized_bbox": bbox.to_list(),
                "pixel_bbox": [left, top, right, bottom],
                "image_width": width,
                "image_height": height,
            }
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    @staticmethod
    def _nearby_text_candidate(block: DocumentBlock, figure: DocumentBlock) -> bool:
        if block.block_type in {"heading", "figure"} or not str(block.text or "").strip():
            return False
        figure_root = (figure.section_path or [""])[0]
        block_root = (block.section_path or [""])[0]
        return not figure_root or not block_root or figure_root == block_root

    def _search_context(self, book: CanonicalBook, figure_index: int, *, neighbor_count: int = 2) -> str:
        figure = book.blocks[figure_index]
        before: list[str] = []
        after: list[str] = []
        for block in reversed(book.blocks[:figure_index]):
            if self._nearby_text_candidate(block, figure):
                before.append(str(block.text or ""))
            if len(before) >= neighbor_count:
                break
        for block in book.blocks[figure_index + 1:]:
            if self._nearby_text_candidate(block, figure):
                after.append(str(block.text or ""))
            if len(after) >= neighbor_count:
                break
        return " ".join([*reversed(before), *after])[:4000]

    @staticmethod
    def _normalize_search_text(value: Any) -> str:
        return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())

    def _figure_payload(self, book: CanonicalBook, block: DocumentBlock) -> dict[str, Any]:
        attributes = block.attributes or {}
        caption = attributes.get("caption") if "caption" in attributes else block.text
        return {
            "figure_id": block.block_id,
            "book_name": book.book_name,
            "caption": str(caption or "").strip(),
            "source_text": str(block.text or "").strip(),
            "page": block.page_start,
            "page_idx": block.page_start - 1 if block.page_start is not None else None,
            "page_bbox": list(attributes.get("page_bbox") or block.bbox or []),
            "bbox_space": str(attributes.get("bbox_space") or "page"),
            "bbox_format": str(attributes.get("bbox_format") or "xyxy"),
            "bbox_units": str(attributes.get("bbox_units") or "mineru_source_units"),
            "section_path": list(block.section_path),
            "source_file": block.source_file,
            "source_kind": block.source_kind,
            "asset_relpath": str(attributes.get("asset_relpath") or ""),
            "asset_status": str(attributes.get("asset_status") or "missing"),
            "image_width": int(attributes.get("image_width") or 0),
            "image_height": int(attributes.get("image_height") or 0),
            "content_hash": str(attributes.get("content_hash") or ""),
            "image_url": f"/api/books/{quote(book.book_name, safe='')}/figures/{quote(block.block_id, safe='')}/image",
            "pdf_url": f"/api/books/{quote(book.book_name, safe='')}/source-pdf",
        }
