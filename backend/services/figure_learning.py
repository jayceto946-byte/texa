"""Canonical Figure lookup, bounded context assembly, and deterministic crops."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any, Iterator
from urllib.parse import quote

from PIL import Image, ImageOps

from config import PROGRESS_PATH
from ingestion.chapter_splitter import ChapterSplitter
from ingestion.document_ir import CanonicalBook, DocumentBlock, canonical_paths, load_canonical_book


MAX_FIGURE_ASSET_BYTES = 25 * 1024 * 1024
MAX_FIGURE_PIXELS = 60_000_000
MIN_REGION_FRACTION = 0.005
MIN_REGION_PIXELS = 8


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


class FigureLearningService:
    def __init__(self, progress_root: str | Path = PROGRESS_PATH) -> None:
        self.progress_root = Path(progress_root)

    def load_book(self, book_name: str) -> CanonicalBook:
        name = str(book_name or "").strip()
        if not name:
            raise ValueError("book_name 不能为空")
        return load_canonical_book(name, progress_root=self.progress_root)

    def list_figures(
        self,
        book_name: str,
        *,
        offset: int = 0,
        limit: int = 50,
        query: str = "",
    ) -> dict[str, Any]:
        book = self.load_book(book_name)
        needle = str(query or "").strip().casefold()
        figures = [self._figure_payload(book, block) for block in book.blocks if block.block_type == "figure"]
        if needle:
            figures = [item for item in figures if needle in " ".join([
                str(item.get("caption") or ""),
                " ".join(item.get("section_path") or []),
                str(item.get("page") or ""),
            ]).casefold()]
        start = max(0, int(offset or 0))
        size = min(100, max(1, int(limit or 50)))
        return {"items": figures[start:start + size], "total": len(figures), "offset": start, "limit": size}

    def get_figure(self, book_name: str, figure_id: str) -> tuple[CanonicalBook, DocumentBlock, dict[str, Any]]:
        book = self.load_book(book_name)
        target = str(figure_id or "").strip()
        for block in book.blocks:
            if block.block_type == "figure" and block.block_id == target:
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
        book, figure, payload = self.get_figure(book_name, figure_id)
        figure_index = book.blocks.index(figure)
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
            })

        source_ids = {figure.block_id, *(item["block_id"] for item in nearby)}
        related_chunk_ids: list[str] = []
        for chunk in ChapterSplitter().split_canonical_book(book):
            if source_ids.intersection(str(value) for value in chunk.get("source_block_ids") or []):
                chunk_id = str(chunk.get("chunk_id") or "")
                if chunk_id and chunk_id not in related_chunk_ids:
                    related_chunk_ids.append(chunk_id)
        return FigureContextPackage(payload, nearby, related_chunk_ids)

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
