"""Evidence-backed KG enhancement for any imported textbook."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable

from config import MINERU_OUTPUT_PATH, PROGRESS_PATH, get_llm
from utils.json_io import atomic_write_json
from utils.path_safety import safe_book_name, safe_child_path
from utils.thinking_filter import strip_thinking

HIGH_VALUE_ROLES = {"definition", "theorem", "property", "formula", "derivation", "proof", "algorithm", "example", "exercise"}

SYSTEM_PROMPT = """Extract a traceable concept index from the supplied textbook excerpt only.
Return strict JSON: {"concepts":[{"name":"term","aliases":[],"definition":"verbatim definition or empty","formulas":[]}]}
Every concept name must occur verbatim in the excerpt. Definitions must be verbatim excerpts.
Do not infer prerequisites, extensions, dependencies, misconceptions, or any directional relation."""


def load_book_chunks(book_name: str) -> list[dict[str, Any]]:
    safe = safe_book_name(book_name)
    candidates: list[Path] = []
    metadata = safe_child_path(PROGRESS_PATH, safe, "metadata.json")
    try:
        meta = json.loads(metadata.read_text(encoding="utf-8")) if metadata.exists() else {}
    except Exception:
        meta = {}
    output_dir = str(meta.get("mineru_output_dir") or "").strip()
    if output_dir:
        root = Path(output_dir)
        candidates.extend(root.rglob(f"{safe}_middle_chunks.json"))
        candidates.extend(root.rglob("*_middle_chunks.json"))
    candidates.extend((Path(MINERU_OUTPUT_PATH) / safe).rglob(f"{safe}_middle_chunks.json") if (Path(MINERU_OUTPUT_PATH) / safe).exists() else [])
    progress_dir = safe_child_path(PROGRESS_PATH, safe)
    candidates.extend(progress_dir.rglob(f"{safe}_middle_chunks.json") if progress_dir.exists() else [])
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(rows, list) and rows:
            return [dict(row) for row in rows if isinstance(row, dict) and str(row.get("content") or row.get("text") or "").strip()]
    return []


def estimate_enhancement(book_name: str) -> dict[str, Any]:
    chunks = load_book_chunks(book_name)
    selected = _select_chunks(chunks)
    return {
        "book_name": safe_book_name(book_name),
        "total_chunks": len(chunks),
        "selected_chunks": len(selected),
        "selected_characters": sum(len(_text(row)) for row in selected),
        "sends_text_to_external_llm": True,
    }


def enhance_book(
    book_name: str,
    *,
    progress: Callable[[str, str, int], None] | None = None,
    check_cancelled: Callable[[], None] | None = None,
) -> dict[str, Any]:
    safe = safe_book_name(book_name)
    chunks = load_book_chunks(safe)
    if not chunks:
        raise RuntimeError("No textbook chunks are available for knowledge enhancement")
    selected = _select_chunks(chunks)
    if not selected:
        selected = chunks[: min(len(chunks), 200)]
    work_dir = safe_child_path(PROGRESS_PATH, safe, "kg_enhancement")
    candidates_path = work_dir / "candidates.json"
    existing = _read_list(candidates_path)
    by_chunk = {str(row.get("chunk_id") or ""): row for row in existing if row.get("chunk_id")}
    llm = get_llm(temperature=0.1)
    total = len(selected)
    for index, chunk in enumerate(selected, 1):
        if check_cancelled:
            check_cancelled()
        chunk_id = str(chunk.get("chunk_id") or "")
        content_hash = hashlib.sha256(_text(chunk).encode("utf-8")).hexdigest()
        if chunk_id and chunk_id in by_chunk and by_chunk[chunk_id].get("content_hash") == content_hash:
            continue
        prompt = (
            f"{SYSTEM_PROMPT}\n\nTextbook: {safe}\nChapter: {chunk.get('chapter') or chunk.get('section_title') or ''}"
            f"\nSemantic role: {chunk.get('role') or 'reference'}\nExcerpt:\n{_text(chunk)[:5000]}"
        )
        raw = strip_thinking(str(llm.invoke(prompt).content or ""))
        payload = _parse_object(raw)
        row = {
            "chunk_id": chunk_id,
            "chapter": chunk.get("chapter") or "",
            "section_title": chunk.get("section_title") or "",
            "page_idx": chunk.get("page_idx", -1),
            "role": chunk.get("role") or "reference",
            "content_hash": content_hash,
            "concepts": _validated_concepts(payload.get("concepts"), _text(chunk)),
        }
        by_chunk[chunk_id or f"row_{index}"] = row
        if index % 5 == 0 or index == total:
            atomic_write_json(candidates_path, list(by_chunk.values()))
        if progress:
            percent = 10 + int(index / max(total, 1) * 78)
            progress("extract", f"Extracting concepts {index}/{total}", percent)
    candidate_rows = list(by_chunk.values())
    atomic_write_json(candidates_path, candidate_rows)
    if progress:
        progress("assemble", "Assembling traceable concept index", 92)
    graph = build_evidence_graph(safe, chunks, candidate_rows)
    # Activate only a complete graph. Candidate checkpoints remain outside the
    # active directory, so users can keep using the previous graph while this runs.
    graph_dir = safe_child_path(PROGRESS_PATH, safe, "kg_enhancement", "active")
    graph_path = graph_dir / f"{safe}_knowledge_graph.json"
    chunks_path = graph_dir / f"{safe}_middle_chunks.json"
    atomic_write_json(graph_path, graph)
    atomic_write_json(chunks_path, chunks)
    try:
        from knowledge import knowledge_graph
        knowledge_graph._kg_cache.pop(safe, None)
    except Exception:
        pass
    return {
        "book_name": safe,
        "graph_path": str(graph_path),
        "concept_count": len(graph["concepts"]),
        "occurrence_count": len(graph["occurrences"]),
        "formula_count": len(graph["formulas"]),
        "processed_chunks": len(candidate_rows),
    }


def build_evidence_graph(book_name: str, chunks: list[dict], candidate_rows: list[dict]) -> dict[str, Any]:
    concepts_by_name: dict[str, dict[str, Any]] = {}
    occurrences: list[dict[str, Any]] = []
    formulas: list[dict[str, Any]] = []
    for row in candidate_rows:
        for concept in row.get("concepts") or []:
            name = _normalize_name(concept.get("name"))
            if not name:
                continue
            item = concepts_by_name.setdefault(name, {"aliases": set(), "definition": "", "rows": []})
            item["aliases"].update(_normalize_name(value) for value in concept.get("aliases") or [] if _normalize_name(value))
            item["definition"] = item["definition"] or str(concept.get("definition") or "").strip()
            item["rows"].append(row)
            for formula in concept.get("formulas") or []:
                latex = str(formula or "").strip()
                if latex:
                    formulas.append({"concept_name": name, "formula_latex": latex, "chunk_id": row.get("chunk_id", "")})
    concepts = []
    name_to_id = {name: _stable_id("CONCEPT", name) for name in concepts_by_name}
    for name, item in sorted(concepts_by_name.items()):
        cid = name_to_id[name]
        own = []
        seen = set()
        for row in item["rows"]:
            chunk_id = str(row.get("chunk_id") or "")
            if not chunk_id or chunk_id in seen:
                continue
            seen.add(chunk_id)
            occ = {
                "occurrence_id": _stable_id("OCC", f"{cid}|{chunk_id}"), "concept_id": cid,
                "concept_name": name, "context_id": chunk_id, "chunk_id": chunk_id,
                "page_idx": row.get("page_idx", -1), "bbox": [], "role": row.get("role") or "reference",
                "section_title": row.get("section_title") or row.get("chapter") or "",
            }
            own.append(occ)
            occurrences.append(occ)
        concepts.append({
            "concept_id": cid, "canonical_name": name, "aliases": sorted({name, *item["aliases"]}),
            "definition": item["definition"], "source_context": "; ".join(f"[{row.get('section_title') or row.get('chapter') or ''}] {name} ({row.get('chunk_id')})" for row in item["rows"][:8]),
            "confidence": 0.85, "occurrence_count": len(own), "occurrences": own,
            "roles": sorted({str(row.get("role") or "reference") for row in item["rows"]}),
        })
    formula_rows = []
    seen_formulas = set()
    for formula in formulas:
        key = (formula["concept_name"], formula["formula_latex"])
        if key in seen_formulas:
            continue
        seen_formulas.add(key)
        formula_rows.append({
            "formula_id": _stable_id("FORMULA", "|".join(key)), "formula_latex": formula["formula_latex"],
            "variables": [], "source_contexts": [{"chunk_id": formula["chunk_id"]}],
            "related_concepts": [name_to_id[formula["concept_name"]]],
        })
    return {
        "meta": {"source": "user_textbook_kg_enhancement", "book_name": book_name, "generated_at": datetime.now().isoformat(), "total_chunks": len(chunks), "total_concepts": len(concepts), "total_occurrences": len(occurrences), "total_formulas": len(formula_rows), "total_relations": 0},
        "concepts": concepts, "formulas": formula_rows, "occurrences": occurrences, "relations": [],
    }


def _select_chunks(chunks: list[dict]) -> list[dict]:
    selected = [row for row in chunks if str(row.get("role") or "reference").lower() in HIGH_VALUE_ROLES]
    return selected or chunks[: min(len(chunks), 200)]


def _text(row: dict) -> str:
    return str(row.get("content") or row.get("text") or "").strip()


def _read_list(path: Path) -> list[dict]:
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _parse_object(raw: str) -> dict:
    text = raw.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _validated_concepts(value: Any, source_text: str) -> list[dict]:
    result = []
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        name = _normalize_name(raw.get("name"))
        if len(name) < 2 or name not in source_text:
            continue
        definition = str(raw.get("definition") or "").strip()
        if definition and definition not in source_text:
            definition = ""
        aliases = raw.get("aliases") if isinstance(raw.get("aliases"), list) else []
        formulas = raw.get("formulas") if isinstance(raw.get("formulas"), list) else []
        result.append({
            "name": name,
            "aliases": [str(alias).strip() for alias in aliases if str(alias).strip() in source_text],
            "definition": definition,
            "formulas": [str(formula).strip() for formula in formulas if str(formula).strip() and str(formula).strip() in source_text],
        })
    return result[:20]


def _normalize_name(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).rstrip("\uFF0C\u3002\uFF1B\uFF1A\u3001,.;:")


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha1(value.lower().encode('utf-8')).hexdigest()[:16]}"
