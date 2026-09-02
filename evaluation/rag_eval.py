"""Offline textbook retrieval evaluation over the final EvidencePack.

The release check scores the bounded evidence delivered to the generator,
rather than the larger debug candidate pool. This catches losses introduced
by reranking, evidence budgeting, and per-item clipping.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_cases(path: str | Path) -> list[dict]:
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def score_case(case: dict, items: list[dict], k: int = 20) -> dict:
    selected = items[:k]
    required = [str(point) for point in case.get("required_points", [])]
    texts = [
        "\n".join(filter(None, [
            str(item.get("section_title") or ""),
            str(item.get("text") or item.get("preview") or ""),
        ]))
        for item in selected
    ]
    joined = "\n".join(texts)
    matched = [point for point in required if point in joined]
    first_complete_rank = 0
    for rank, text in enumerate(texts, 1):
        if required and all(point in text for point in required):
            first_complete_rank = rank
            break
    answerable = bool(case.get("answerable", True))
    retrieved_any = bool(selected)
    return {
        "id": case.get("id", ""),
        "answerable": answerable,
        "point_recall": len(matched) / len(required) if required else float(not retrieved_any),
        "recall_at_k": float(len(matched) == len(required)) if answerable else float(not retrieved_any),
        "reciprocal_rank": 1.0 / first_complete_rank if first_complete_rank else 0.0,
        "matched_points": matched,
        "missing_points": [point for point in required if point not in matched],
    }


def aggregate(results: list[dict]) -> dict:
    if not results:
        return {"cases": 0, "recall_at_k": 0.0, "mrr": 0.0, "point_recall": 0.0}
    n = len(results)
    return {
        "cases": n,
        "recall_at_k": sum(item["recall_at_k"] for item in results) / n,
        "mrr": sum(item["reciprocal_rank"] for item in results) / n,
        "point_recall": sum(item["point_recall"] for item in results) / n,
    }


def retrieve_case(case: dict) -> list[dict]:
    from graph.retrieval_node import retrieve_node
    from graph.evidence_pack import build_evidence_pack
    state = {
        "user_input": case["question"],
        "book_name": case["book_name"],
        "intent": case.get("intent", "factual_recall"),
        "target_chapters": case.get("target_chapters", []),
        "use_textbook_context": True,
        "retrieval_error": "",
    }
    result = retrieve_node(state)
    if not case.get("answerable", True):
        support = str((result.get("evidence_support") or {}).get("status") or "")
        return [] if support == "insufficient" else result.get("evidence_items", [])
    pack = build_evidence_pack(
        result.get("evidence_items") or [],
        intent=str(case.get("intent") or "factual_recall"),
    )
    return [{"chunk_id": "final-evidence-pack", "text": str(pack.get("text") or "")}]


def evaluate(path: str | Path, k: int = 20) -> dict:
    cases = load_cases(path)
    details = [score_case(case, retrieve_case(case), k=k) for case in cases]
    return {"summary": aggregate(details), "details": details}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset")
    parser.add_argument("--k", type=int, default=20)
    parser.add_argument("--output", default="")
    parser.add_argument("--min-recall", type=float, default=1.0)
    parser.add_argument("--min-point-recall", type=float, default=1.0)
    args = parser.parse_args()
    report = evaluate(args.dataset, k=args.k)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    summary = report["summary"]
    failed = (
        summary["recall_at_k"] < args.min_recall
        or summary["point_recall"] < args.min_point_recall
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
