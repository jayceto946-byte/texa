"""Deterministic Figure-learning acceptance checks over a real MinerU corpus."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from PIL import Image

from backend.services.answer_verification import derive_required_outputs, verify_answer
from backend.services.figure_learning import FigureLearningService, NormalizedBBox
from ingestion.document_adapters import MinerUAdapter, materialize_figure_assets
from ingestion.document_ir import persist_canonical_book, validate_canonical_book
from utils.citation_protocol import sanitize_citation_protocol


REQUIRED_FIGURE_FIELDS = (
    "figure_id", "asset_relpath", "caption", "page_idx", "page_bbox",
    "bbox_space", "image_width", "image_height", "content_hash",
)


@dataclass(frozen=True)
class VisualLearningEvaluation:
    passed: bool
    report: dict[str, Any]


def load_sensor_standard(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("schema_version") != "visual-learning-sensor/v1":
        raise ValueError("unsupported visual-learning sensor standard")
    return value


def evaluate_visual_learning_corpus(
    output_dir: str | Path,
    *,
    progress_root: str | Path,
    standard: dict[str, Any],
    book_name: str = "传感器视觉验收",
) -> VisualLearningEvaluation:
    """Exercise steps 1-4 without a network or paid multimodal call."""
    source_root = Path(output_dir)
    book = MinerUAdapter.from_output_dir(source_root, book_name=book_name)
    figures = [block for block in book.blocks if block.block_type == "figure"]
    materialize_figure_assets(book, source_root=source_root, progress_root=progress_root)
    validation = validate_canonical_book(book)
    persist_canonical_book(book, progress_root=progress_root)

    ready = [block for block in figures if block.attributes.get("asset_status") == "ready"]
    captioned = [block for block in figures if str(block.attributes.get("caption") or "").strip()]
    complete = [block for block in ready if _has_required_figure_fields(block)]
    figure_count = len(figures)
    step1 = {
        "figure_count": figure_count,
        "caption_rate": _rate(len(captioned), figure_count),
        "ready_asset_rate": _rate(len(ready), figure_count),
        "required_field_rate": _rate(len(complete), len(ready)),
        "canonical_valid": validation.valid,
        "errors": sum(issue.severity == "error" for issue in validation.issues),
        "warnings": sum(issue.severity == "warning" for issue in validation.issues),
    }

    service = FigureLearningService(progress_root)
    query_results = []
    for case in standard.get("queries") or []:
        result = service.list_figures(book_name, query=str(case.get("query") or ""), limit=3)
        expected_terms = [str(term) for term in case.get("expected_caption_terms") or []]
        expected_page = case.get("expected_page")
        matched = any(
            all(term in str(item.get("caption") or "") for term in expected_terms)
            and (expected_page is None or item.get("page") == expected_page)
            for item in result["items"]
        )
        query_results.append({
            "query": case.get("query") or "",
            "matched_top3": matched,
            "returned": len(result["items"]),
            "top_figure_id": result["items"][0].get("figure_id") if result["items"] else "",
        })
    step2 = {
        "query_top3_rate": _rate(sum(item["matched_top3"] for item in query_results), len(query_results)),
        "cases": query_results,
    }

    region_case = dict(standard.get("region") or {})
    region_results = service.list_figures(book_name, query=str(region_case.get("query") or ""), limit=1)
    if not region_results["items"]:
        step3 = {"passed": False, "reason": "region target figure was not found"}
        step4 = {"passed": False, "reason": "region target figure was not found"}
    else:
        figure = region_results["items"][0]
        bbox = NormalizedBBox.from_values(region_case.get("bbox") or [0.2, 0.2, 0.8, 0.8])
        with service.cropped_region(book_name, figure["figure_id"], bbox) as (crop_path, crop_meta):
            with Image.open(crop_path) as cropped:
                crop_width, crop_height = cropped.size
        step3 = {
            "passed": (
                crop_width >= int(region_case.get("minimum_crop_width") or 8)
                and crop_height >= int(region_case.get("minimum_crop_height") or 8)
                and crop_meta["normalized_bbox"] == bbox.to_list()
            ),
            "figure_id": figure["figure_id"],
            "normalized_bbox": crop_meta["normalized_bbox"],
            "pixel_bbox": crop_meta["pixel_bbox"],
            "crop_size": [crop_width, crop_height],
        }

        context = service.build_context(book_name, figure["figure_id"])
        sources = service.evidence_sources(context)
        answer = "选区来自指定教材 Figure。[[cite:E1]]"
        if len(sources) > 1:
            excerpt = str(sources[1].get("text") or "")[:120]
            answer += f" 教材邻近正文写道：{excerpt} [[cite:{sources[1]['id']}]]"
        sanitized, trace = sanitize_citation_protocol(answer, sources)
        verification = verify_answer(
            sanitized,
            required_outputs=derive_required_outputs(
                "说明该图及其教材语境", intent="application", answer_mode="visual_grounded",
            ),
            sources=sources,
            citation_trace=trace,
        )
        step4 = {
            "passed": bool(
                sources
                and sources[0].get("figure_id") == figure["figure_id"]
                and sources[0].get("page_idx") is not None
                and any(source.get("block_id") and source.get("text") for source in sources[1:])
                and any(source.get("chunk_id") for source in sources[1:])
                and verification.get("status") == "passed"
            ),
            "source_count": len(sources),
            "nearby_text_source_count": sum(bool(source.get("text")) for source in sources[1:]),
            "related_chunk_count": len(context.related_chunk_ids),
            "citation_status": verification.get("status"),
        }

    thresholds = standard.get("thresholds") or {}
    checks = {
        "step1_figure_count": step1["figure_count"] >= int(thresholds.get("minimum_figures") or 1),
        "step1_caption_rate": step1["caption_rate"] >= float(thresholds.get("minimum_caption_rate") or 0),
        "step1_asset_rate": step1["ready_asset_rate"] >= float(thresholds.get("minimum_ready_asset_rate") or 0),
        "step1_required_fields": step1["required_field_rate"] >= float(thresholds.get("minimum_required_field_rate") or 0),
        "step1_canonical_valid": bool(step1["canonical_valid"]),
        "step2_query_top3": step2["query_top3_rate"] >= float(thresholds.get("minimum_query_top3_rate") or 0),
        "step3_region_crop": bool(step3.get("passed")),
        "step4_provenance": bool(step4.get("passed")),
    }
    report = {
        "schema_version": "visual-learning-eval/v1",
        "book_name": book_name,
        "parser_version": book.parser_version,
        "step1_ingestion": step1,
        "step2_search_open": step2,
        "step3_region_question_contract": step3,
        "step4_answer_provenance": step4,
        "checks": checks,
        "passed": all(checks.values()),
        "online_model_called": False,
    }
    return VisualLearningEvaluation(passed=report["passed"], report=report)


def _has_required_figure_fields(block: Any) -> bool:
    attributes = block.attributes or {}
    values = {
        "figure_id": attributes.get("figure_id"),
        "asset_relpath": attributes.get("asset_relpath"),
        "caption": attributes.get("caption") if "caption" in attributes else "",
        "page_idx": attributes.get("page_idx"),
        "page_bbox": attributes.get("page_bbox"),
        "bbox_space": attributes.get("bbox_space"),
        "image_width": attributes.get("image_width"),
        "image_height": attributes.get("image_height"),
        "content_hash": attributes.get("content_hash"),
    }
    for field in REQUIRED_FIGURE_FIELDS:
        value = values[field]
        if field == "caption":
            continue  # Empty-caption Figure is valid and must remain preserved.
        if field == "page_bbox":
            if not isinstance(value, list):
                return False
        elif field == "page_idx":
            if value is None:
                return False
        elif not value:
            return False
    return True


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0
