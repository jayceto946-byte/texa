"""Controlled online evaluation for the textbook Figure learning harness."""
from __future__ import annotations

from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
from pathlib import Path
import re
import time
from typing import Any, Callable, Iterable

from backend.services.answer_verification import derive_required_outputs, verify_answer
from backend.services.figure_learning import FigureLearningService, NormalizedBBox
from backend.services.multimodal_bridge import VisionModelBridge
from utils.citation_protocol import sanitize_citation_protocol


GOLD_SCHEMA_VERSION = "visual-learning-gold/v1"


@dataclass(frozen=True)
class OnlineVisualEvaluation:
    passed: bool
    report: dict[str, Any]


def load_visual_gold(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != GOLD_SCHEMA_VERSION:
        raise ValueError("unsupported visual-learning gold schema")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("visual-learning gold set has no cases")
    seen: set[str] = set()
    for case in cases:
        case_id = str(case.get("id") or "").strip()
        if not case_id or case_id in seen:
            raise ValueError(f"invalid or duplicate case id: {case_id!r}")
        seen.add(case_id)
        if not str(case.get("figure_id") or "").strip():
            raise ValueError(f"{case_id}: figure_id is required")
        if not str(case.get("question") or "").strip():
            raise ValueError(f"{case_id}: question is required")
    return payload


def evaluate_visual_learning_online(
    gold: dict[str, Any],
    *,
    progress_root: str | Path,
    bridge_factory: Callable[[], VisionModelBridge] = VisionModelBridge,
    case_ids: set[str] | None = None,
    on_case: Callable[[dict[str, Any]], None] | None = None,
    max_workers: int = 1,
) -> OnlineVisualEvaluation:
    """Run bounded real-model calls; never reads or writes credentials itself."""
    book_name = str(gold.get("book_name") or "").strip()
    selected = [
        case for case in gold.get("cases") or []
        if case_ids is None or str(case.get("id") or "") in case_ids
    ]
    if not selected:
        raise ValueError("no selected visual-learning cases")

    service = FigureLearningService(progress_root)
    bridge = bridge_factory()
    details: list[dict[str, Any]] = []

    def run_case(index: int, case: dict[str, Any], case_bridge: VisionModelBridge) -> dict[str, Any]:
        started = time.perf_counter()
        detail = _evaluate_case(service, case_bridge, book_name, case)
        detail["ordinal"] = index
        detail["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        if on_case:
            on_case(detail)
        return detail

    workers = min(4, max(1, int(max_workers or 1)))
    if workers == 1:
        for index, case in enumerate(selected, start=1):
            details.append(run_case(index, case, bridge))
    else:
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="visual-eval") as executor:
            futures = {
                executor.submit(run_case, index, case, bridge_factory()): index
                for index, case in enumerate(selected, start=1)
            }
            for future in as_completed(futures):
                details.append(future.result())
        details.sort(key=lambda item: int(item.get("ordinal") or 0))

    summary = _aggregate(details)
    thresholds = dict(gold.get("release_thresholds") or {})
    checks = {
        "minimum_cases": summary["cases"] >= int(thresholds.get("minimum_cases") or 1),
        "retrieval_top3_rate": summary["retrieval_top3_rate"] >= float(thresholds.get("minimum_retrieval_top3_rate") or 0),
        "model_completion_rate": summary["model_completion_rate"] >= float(thresholds.get("minimum_model_completion_rate") or 0),
        "source_citation_rate": summary["source_citation_rate"] >= float(thresholds.get("minimum_source_citation_rate") or 0),
        "verification_pass_rate": summary["verification_pass_rate"] >= float(thresholds.get("minimum_verification_pass_rate") or 0),
        "key_point_coverage": summary["key_point_coverage"] >= float(thresholds.get("minimum_key_point_coverage") or 0),
        "serious_unsupported_claims": summary["serious_unsupported_claims"] <= int(thresholds.get("maximum_serious_unsupported_claims") or 0),
    }
    report = {
        "schema_version": "visual-learning-online-eval/v1",
        "book_name": book_name,
        "model": {
            "provider": bridge.config.provider.provider_id,
            "model": bridge.model,
        },
        "gold_review": dict(gold.get("review") or {}),
        "review_gate": {
            "status": "passed" if bool((gold.get("review") or {}).get("human_signoff")) else "pending_human_signoff",
            "blocks_automated_harness": False,
        },
        "summary": summary,
        "thresholds": thresholds,
        "checks": checks,
        "failure_buckets": _failure_buckets(details),
        "details": details,
        "online_model_called": True,
        "passed": all(checks.values()),
    }
    return OnlineVisualEvaluation(passed=report["passed"], report=report)


def _evaluate_case(
    service: FigureLearningService,
    bridge: VisionModelBridge,
    book_name: str,
    case: dict[str, Any],
) -> dict[str, Any]:
    case_id = str(case.get("id") or "")
    expected_figure_id = str(case.get("figure_id") or "")
    result: dict[str, Any] = {
        "id": case_id,
        "category": case.get("category") or "",
        "figure_id": expected_figure_id,
        "page": case.get("page"),
        "retrieval_top3": False,
        "model_completed": False,
        "model_source_cited": False,
        "source_cited": False,
        "citation_autofilled": False,
        "verification_status": "not_run",
        "key_point_coverage": 0.0,
        "matched_points": [],
        "missing_points": [],
        "serious_unsupported_claim": False,
        "failure_bucket": "",
        "answer": "",
        "error": "",
    }
    try:
        retrieved = service.list_figures(
            book_name, query=str(case.get("query") or ""), limit=3,
        )["items"]
        result["retrieved_figure_ids"] = [item.get("figure_id") for item in retrieved]
        result["retrieval_top3"] = expected_figure_id in result["retrieved_figure_ids"]
        if not result["retrieval_top3"]:
            result["failure_bucket"] = "retrieval"
            return result

        context = service.build_context(book_name, expected_figure_id)
        sources = service.evidence_sources(context)
        full_image = service.asset_path(book_name, expected_figure_id)
        bbox_values = case.get("bbox")
        bbox = NormalizedBBox.from_values(bbox_values) if bbox_values is not None else None
        crop_manager = (
            service.cropped_region(book_name, expected_figure_id, bbox)
            if bbox is not None and not bbox.covers_almost_full_image()
            else nullcontext((None, None))
        )
        with crop_manager as crop_result:
            crop_path, crop_metadata = crop_result
            chunks = bridge.iter_figure_answer(
                full_image,
                user_question=str(case.get("question") or ""),
                figure_context={
                    **context.to_dict(),
                    "user_region": crop_metadata,
                    "evidence_sources": sources,
                },
                cropped_region_path=crop_path,
            )
            raw_answer = "".join(chunks).strip()
        if not raw_answer:
            result["failure_bucket"] = "model"
            result["error"] = "empty model answer"
            return result

        result["model_source_cited"] = bool(re.search(r"\[\[cite:E1\]\]", raw_answer, re.IGNORECASE))
        if not result["model_source_cited"]:
            figure = context.figure
            page_label = f"p.{int(figure['page'])}" if figure.get("page") else "未标页"
            raw_answer = (
                f"{raw_answer}\n\n来源：{book_name} · {page_label} · "
                f"Figure {expected_figure_id} [[cite:E1]]"
            )
            result["citation_autofilled"] = True
        answer, citation_trace = sanitize_citation_protocol(raw_answer, sources)
        result["answer"] = answer
        result["model_completed"] = True
        result["source_cited"] = bool(re.search(r"\[\[cite:E1\]\]", answer, re.IGNORECASE))
        verification = verify_answer(
            answer,
            required_outputs=derive_required_outputs(
                str(case.get("question") or ""),
                intent="application",
                answer_mode="visual_grounded",
            ),
            sources=sources,
            citation_trace=citation_trace,
            evidence_items=[{"id": source.get("id"), "text": source.get("text", "")} for source in sources],
        )
        result["verification_status"] = verification.get("status") or "unknown"
        result["verification"] = verification
        result.update(_score_points(case, answer))
        if case.get("consistency_mode") == "expect_conflict_disclosure":
            disclosed = _contains_any(answer, ["不一致", "不匹配", "冲突", "无法确认", "并非"])
            result["conflict_disclosed"] = disclosed
            result["serious_unsupported_claim"] = not disclosed

        if result["serious_unsupported_claim"]:
            result["failure_bucket"] = "model"
        elif not result["source_cited"] or result["verification_status"] != "passed":
            result["failure_bucket"] = "verification"
        elif result["key_point_coverage"] < 0.85:
            result["failure_bucket"] = "model"
    except (FileNotFoundError, KeyError, ValueError) as exc:
        result["failure_bucket"] = "ingestion"
        result["error"] = _safe_error(exc)
    except Exception as exc:  # Provider/runtime failures are reported without secrets.
        result["failure_bucket"] = "model"
        result["error"] = _safe_error(exc)
    return result


def _score_points(case: dict[str, Any], answer: str) -> dict[str, Any]:
    matched: list[str] = []
    missing: list[str] = []
    for point in case.get("expected_points") or []:
        label = str(point.get("label") or "")
        keywords = [str(value) for value in point.get("keywords") or [] if str(value)]
        (matched if _contains_any(answer, keywords) else missing).append(label)
    total = len(matched) + len(missing)
    return {
        "key_point_coverage": round(len(matched) / total, 6) if total else 1.0,
        "matched_points": matched,
        "missing_points": missing,
    }


def _contains_any(text: str, values: Iterable[str]) -> bool:
    normalized = _match_text(text)
    return any(_match_text(value) in normalized for value in values if value)


def _match_text(value: str) -> str:
    return "".join(character.casefold() for character in str(value or "") if character.isalnum())


def _aggregate(details: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(details)
    rate = lambda key: round(sum(bool(item.get(key)) for item in details) / count, 6) if count else 0.0
    verification_passed = sum(item.get("verification_status") == "passed" for item in details)
    return {
        "cases": count,
        "retrieval_top3_rate": rate("retrieval_top3"),
        "model_completion_rate": rate("model_completed"),
        "model_source_citation_rate": rate("model_source_cited"),
        "source_citation_rate": rate("source_cited"),
        "citation_autofill_count": sum(bool(item.get("citation_autofilled")) for item in details),
        "verification_pass_rate": round(verification_passed / count, 6) if count else 0.0,
        "key_point_coverage": round(sum(float(item.get("key_point_coverage") or 0) for item in details) / count, 6) if count else 0.0,
        "serious_unsupported_claims": sum(bool(item.get("serious_unsupported_claim")) for item in details),
    }


def _failure_buckets(details: list[dict[str, Any]]) -> dict[str, list[str]]:
    buckets = {"ingestion": [], "retrieval": [], "model": [], "verification": []}
    for item in details:
        bucket = str(item.get("failure_bucket") or "")
        if bucket in buckets:
            buckets[bucket].append(str(item.get("id") or ""))
    return buckets


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace("\r", " ").replace("\n", " ")[:800]
    message = re.sub(r"(?i)(api[-_ ]?key|authorization|bearer)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", message)
    return message


def rescore_visual_learning_report(
    gold: dict[str, Any],
    report: dict[str, Any],
    *,
    progress_root: str | Path,
) -> OnlineVisualEvaluation:
    """Re-run deterministic scoring over saved model answers without new calls."""
    book_name = str(gold.get("book_name") or "").strip()
    cases = {str(case.get("id") or ""): case for case in gold.get("cases") or []}
    service = FigureLearningService(progress_root)
    details = [dict(item) for item in report.get("details") or []]
    for detail in details:
        case = cases.get(str(detail.get("id") or ""))
        if not case:
            detail["failure_bucket"] = "ingestion"
            detail["error"] = "case no longer exists in the current gold set"
            continue
        answer = str(detail.get("answer") or "")
        detail.update(_score_points(case, answer))
        if not detail.get("retrieval_top3"):
            detail["failure_bucket"] = "retrieval"
            continue
        if not detail.get("model_completed") or not answer:
            detail["failure_bucket"] = "model"
            continue
        context = service.build_context(book_name, str(case.get("figure_id") or ""))
        sources = service.evidence_sources(context)
        sanitized, citation_trace = sanitize_citation_protocol(answer, sources)
        verification = verify_answer(
            sanitized,
            required_outputs=derive_required_outputs(
                str(case.get("question") or ""), intent="application", answer_mode="visual_grounded",
            ),
            sources=sources,
            citation_trace=citation_trace,
            evidence_items=[{"id": source.get("id"), "text": source.get("text", "")} for source in sources],
        )
        detail["answer"] = sanitized
        detail["source_cited"] = bool(re.search(r"\[\[cite:E1\]\]", sanitized, re.IGNORECASE))
        detail["verification_status"] = verification.get("status") or "unknown"
        detail["verification"] = verification
        detail["serious_unsupported_claim"] = False
        if case.get("consistency_mode") == "expect_conflict_disclosure":
            disclosed = _contains_any(sanitized, ["不一致", "不匹配", "冲突", "无法确认", "并非"])
            detail["conflict_disclosed"] = disclosed
            detail["serious_unsupported_claim"] = not disclosed
        if detail["serious_unsupported_claim"] or detail["key_point_coverage"] < 0.85:
            detail["failure_bucket"] = "model"
        elif not detail["source_cited"] or detail["verification_status"] != "passed":
            detail["failure_bucket"] = "verification"
        else:
            detail["failure_bucket"] = ""

    summary = _aggregate(details)
    thresholds = dict(gold.get("release_thresholds") or {})
    checks = {
        "minimum_cases": summary["cases"] >= int(thresholds.get("minimum_cases") or 1),
        "retrieval_top3_rate": summary["retrieval_top3_rate"] >= float(thresholds.get("minimum_retrieval_top3_rate") or 0),
        "model_completion_rate": summary["model_completion_rate"] >= float(thresholds.get("minimum_model_completion_rate") or 0),
        "source_citation_rate": summary["source_citation_rate"] >= float(thresholds.get("minimum_source_citation_rate") or 0),
        "verification_pass_rate": summary["verification_pass_rate"] >= float(thresholds.get("minimum_verification_pass_rate") or 0),
        "key_point_coverage": summary["key_point_coverage"] >= float(thresholds.get("minimum_key_point_coverage") or 0),
        "serious_unsupported_claims": summary["serious_unsupported_claims"] <= int(thresholds.get("maximum_serious_unsupported_claims") or 0),
    }
    rescored = {
        **report,
        "book_name": book_name,
        "gold_review": dict(gold.get("review") or {}),
        "review_gate": {
            "status": "passed" if bool((gold.get("review") or {}).get("human_signoff")) else "pending_human_signoff",
            "blocks_automated_harness": False,
        },
        "summary": summary,
        "thresholds": thresholds,
        "checks": checks,
        "failure_buckets": _failure_buckets(details),
        "details": details,
        "rescored_without_new_model_calls": True,
        "passed": all(checks.values()),
    }
    return OnlineVisualEvaluation(passed=rescored["passed"], report=rescored)
