"""Bounded public projections of observable work; never serialize raw model data."""
from __future__ import annotations

from typing import Any


def _text(value: Any, limit: int = 420) -> str:
    from utils.thinking_filter import strip_thinking
    return strip_thinking(str(value if value is not None else ""))[:limit].strip()


def evidence_details(state: dict, *, final: bool = False) -> dict:
    items = [item for item in state.get("evidence_items") or [] if isinstance(item, dict)]
    sources = [item for item in state.get("evidence_sources") or [] if isinstance(item, dict)]
    selected = sources if final else items
    by_chunk = {(str(item.get("book_name") or ""), str(item.get("chunk_id"))): item
                for item in items if item.get("chunk_id")}
    previews = []
    for item in selected[:12]:
        original = by_chunk.get((str(item.get("book_name") or ""), str(item.get("chunk_id"))), item)
        text = str(original.get("text") or "")
        if final and isinstance(item.get("chars"), int):
            text = text[:max(0, item["chars"])]
        previews.append({
            **{key: _text(item.get(key), 160) for key in (
                "id", "chunk_id", "book_name", "chapter", "section_title", "index_version",
            ) if item.get(key)},
            "section_path": [_text(part, 120) for part in (item.get("section_path") or [])[:6]],
            "page_idx": item.get("page_idx") if isinstance(item.get("page_idx"), int) else -1,
            "preview": _text(text),
            "truncated": len(text) > 420,
        })
    return {"evidence_previews": previews, "evidence_count": len(selected),
            "evidence_scope": "answer" if final else "retrieved"}


_INPUT_FIELDS = ("query", "book_name", "subject", "chapter", "tag", "status", "days", "limit",
                 "operation", "expression", "variable", "lower", "upper", "kind", "original",
                 "candidate", "left", "right")


def tool_details(args: dict | None, result: dict | None = None, *, provenance: str = "") -> dict:
    """Only known public input/result fields enter execution events."""
    inputs = {key: _text(args[key], 300) for key in _INPUT_FIELDS
              if args and key in args and isinstance(args[key], (str, int, float, bool))}
    output = {"input_preview": inputs}
    if provenance:
        output["provenance"] = _text(provenance, 120)
    if result is None:
        return output
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    rows = []
    for key in ("result", "passed", "equivalent", "coverage_note"):
        value = data.get(key)
        if isinstance(value, (str, int, float, bool)):
            rows.append(f"{key}: {_text(value)}")
        elif key == "result" and isinstance(value, list):
            rows.append(f"result: {', '.join(_text(v, 80) for v in value[:8] if isinstance(v, (str, int, float)))}")
    for key in ("exercises", "concepts", "snippets", "examples", "recent_events", "top_concepts"):
        values = data.get(key)
        if not isinstance(values, list):
            continue
        rows.append(f"{key}: {len(values)} 项")
        for item in values[:3]:
            if isinstance(item, dict):
                title = item.get("name") or item.get("question_text") or item.get("title")
                if title:
                    rows.append(_text(title, 160))
    output["result_preview"] = _text("\n".join(rows) or result.get("message"), 1200)
    verification = result.get("verification") or {}
    if isinstance(verification, dict) and isinstance(verification.get("passed"), bool):
        output["verification_passed"] = verification["passed"]
    output["warnings"] = [_text(warning, 160) for warning in (result.get("warnings") or [])[:5]]
    if isinstance(data.get("evidence_items"), list):
        output.update(evidence_details({"evidence_items": data["evidence_items"],
                                        "evidence_sources": result.get("evidence") or []},
                                       final=bool(result.get("evidence"))))
    return output
