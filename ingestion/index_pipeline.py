"""Crash-safe, versioned activation of textbook vector and lexical indexes."""
from __future__ import annotations

import hashlib
import json
import os
import copy
import threading
import time
import uuid
from pathlib import Path

from config import VECTOR_DB_PATH
from ingestion.document_ir import (
    PROVENANCE_SCHEMA_VERSION,
    chunk_provenance_errors,
)
from ingestion.lexical_index import index_path
from utils.json_io import atomic_write_json
from utils.path_safety import safe_book_name

INDEX_SCHEMA_VERSION = 6
RELEASE_MIN_RECALL = 1.0
RELEASE_MIN_POINT_RECALL = 1.0
MAX_RETAINED_INDEX_VERSIONS = 2
SPECIALTY_RELEASE_THRESHOLDS = {
    "formula": {"min_recall": 1.0, "min_point_recall": 1.0, "max_required_cases": 3},
    "list": {"min_recall": 1.0, "min_point_recall": 1.0, "max_required_cases": 3},
    "example": {"min_recall": 1.0, "min_point_recall": 1.0, "max_required_cases": 3},
    "table": {"min_recall": 1.0, "min_point_recall": 1.0, "max_required_cases": 3},
}
_BUILD_LOCK = threading.RLock()
_LEXICAL_KEYS = (
    "provenance_schema", "index_version", "book_name",
    "chapter", "section_title", "section_path", "chunk_index", "section_chunk_index", "chunk_id",
    "parent_id", "prev_chunk_id", "next_chunk_id", "page_idx", "role",
    "content", "retrieval_text", "parent_content", "subject", "book_role",
    "rag_priority", "bbox", "equations", "block_type", "source_markdown",
    "review_status", "page_start", "page_end", "source_kind", "source_file",
    "ocr_confidence", "source_block_ids", "source_locations", "table_title",
    "table_header", "table_rows", "figure_id", "retrieval_excluded",
)


def manifest_path(book_name: str) -> Path:
    return Path(VECTOR_DB_PATH) / "_index_manifests" / f"{safe_book_name(book_name)}.json"


def versioned_lexical_path(book_name: str, version: str) -> Path:
    safe_version = "".join(character for character in str(version or "legacy") if character.isalnum())[:32] or "legacy"
    return Path(VECTOR_DB_PATH) / "_lexical_versions" / safe_book_name(book_name) / f"{safe_version}.json"


def _manifest_asset_path(path: Path) -> str:
    """Keep version manifests portable with the vector DB directory."""
    try:
        return str(path.relative_to(Path(VECTOR_DB_PATH)))
    except ValueError:
        return str(path)


def load_index_manifest(book_name: str) -> dict:
    path = manifest_path(book_name)
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _fingerprint(chunks: list[dict]) -> str:
    digest = hashlib.sha256()
    digest.update(f"index:{INDEX_SCHEMA_VERSION}|{PROVENANCE_SCHEMA_VERSION}".encode("utf-8"))
    digest.update(b"\0")
    for chunk in chunks:
        digest.update(str(chunk.get("chunk_id") or "").encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(chunk.get("content") or "").encode("utf-8"))
        digest.update(b"\0")
        digest.update(json.dumps({
            "source_block_ids": chunk.get("source_block_ids") or [],
            "source_locations": chunk.get("source_locations") or [],
            "figure_id": chunk.get("figure_id") or "",
            "retrieval_excluded": bool(chunk.get("retrieval_excluded")),
        }, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _metadata(chunk: dict, book_name: str, chapter: str) -> dict:
    return {
        "provenance_schema": str(chunk.get("provenance_schema") or ""),
        "index_version": str(chunk.get("index_version") or ""),
        "raw_content": str(chunk.get("content") or ""),
        "section_path": json.dumps(chunk.get("section_path") or [], ensure_ascii=False),
        "parent_id": str(chunk.get("parent_id") or ""),
        "prev_chunk_id": str(chunk.get("prev_chunk_id") or ""),
        "next_chunk_id": str(chunk.get("next_chunk_id") or ""),
        "chapter": str(chunk.get("chapter") or chapter),
        "book_name": book_name,
        "chunk_index": int(chunk.get("chunk_index", 0) or 0),
        "section_chunk_index": int(chunk.get("section_chunk_index", 0) or 0),
        "chunk_id": str(chunk.get("chunk_id") or ""),
        "section_title": str(chunk.get("section_title") or chunk.get("chapter") or chapter),
        "page_idx": _int_or(chunk.get("page_idx"), -1),
        "page_start": _int_or(chunk.get("page_start"), -1),
        "page_end": _int_or(chunk.get("page_end"), -1),
        "role": str(chunk.get("role") or "reference"),
        "subject": str(chunk.get("subject") or ""),
        "book_role": str(chunk.get("book_role") or ""),
        "rag_priority": float(chunk.get("rag_priority", 1.0) or 1.0),
        "review_status": str(chunk.get("review_status") or ""),
        "source_markdown": str(chunk.get("source_markdown") or ""),
        "bbox": json.dumps(chunk.get("bbox") or [], ensure_ascii=False),
        "equations": json.dumps(chunk.get("equations") or [], ensure_ascii=False),
        "block_type": str(chunk.get("block_type") or "text"),
        "source_kind": str(chunk.get("source_kind") or ""),
        "source_file": str(chunk.get("source_file") or ""),
        "ocr_confidence": _float_or(chunk.get("ocr_confidence"), -1.0),
        "source_block_ids": json.dumps(chunk.get("source_block_ids") or [], ensure_ascii=False),
        "source_locations": json.dumps(chunk.get("source_locations") or [], ensure_ascii=False),
        "table_title": str(chunk.get("table_title") or ""),
        "table_header": json.dumps(chunk.get("table_header") or [], ensure_ascii=False),
        "table_rows": json.dumps(chunk.get("table_rows") or [], ensure_ascii=False),
        "figure_id": str(chunk.get("figure_id") or ""),
        "retrieval_excluded": bool(chunk.get("retrieval_excluded")),
        "collection_schema": INDEX_SCHEMA_VERSION,
    }


def _int_or(value, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _float_or(value, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _add_collection(vs, name: str, book_name: str, chapter: str, chunks: list[dict]) -> int:
    try:
        vs._client.delete_collection(name)
    except Exception:
        pass
    collection = vs._client.get_or_create_collection(name)
    rows = [
        chunk for chunk in chunks
        if str(chunk.get("content") or "").strip()
        and not bool(chunk.get("retrieval_excluded"))
    ]
    for start in range(0, len(rows), 64):
        batch = rows[start:start + 64]
        texts = [str(item.get("retrieval_text") or item.get("content") or "") for item in batch]
        ids = [
            hashlib.sha1(f"{item.get('chunk_id')}|{start + offset}|{text}".encode("utf-8")).hexdigest()
            for offset, (item, text) in enumerate(zip(batch, texts))
        ]
        collection.add(
            ids=ids,
            documents=texts,
            embeddings=vs.embeddings.embed_documents(texts),
            metadatas=[_metadata(item, book_name, chapter) for item in batch],
        )
    actual = int(collection.count())
    if actual != len(rows):
        raise RuntimeError(f"vector count validation failed for {chapter}: expected={len(rows)}, actual={actual}")
    return actual


def _validate_staged_production_retrieval(
    vs,
    book_name: str,
    staged_entries: dict[str, dict],
    lexical_rows: list[dict],
    *,
    acceptance_probes: list[dict] | None = None,
    specialty_inventory: dict[str, int] | None = None,
) -> dict:
    """Run golden cases through the production hybrid retrieval implementation.

    The staged vector and lexical assets are exposed through isolated read-only
    bindings. The process-wide active map, lexical file and caches are never
    swapped during validation, so concurrent chat requests cannot observe the
    candidate index.
    """
    from evaluation.rag_eval import aggregate, load_cases, score_case
    from graph.retrieval_node import retrieve_node
    from graph.evidence_pack import build_evidence_pack
    from ingestion.lexical_index import (
        expand_neighbors,
        expand_neighbors_rows,
        search_book,
        search_rows,
    )

    dataset_root = Path(__file__).resolve().parents[1] / "evaluation" / "datasets"
    cases: list[dict] = []
    for path in sorted(dataset_root.glob("*_recall.jsonl")):
        cases.extend(
            case for case in load_cases(path)
            if case.get("book_name") == book_name
        )
    existing_ids = {str(case.get("id") or "") for case in cases}
    for case in acceptance_probes or []:
        case_id = str(case.get("id") or "")
        if case_id and case_id not in existing_ids and case.get("book_name") == book_name:
            cases.append(dict(case))
            existing_ids.add(case_id)
    if not cases:
        return {
            "cases": 0,
            "status": "not_configured",
            "specialty_gates": _specialty_gates([], [], specialty_inventory or {}),
        }

    staged_vs = copy.copy(vs)
    staged_vs._map = {
        **{
            name: dict(entry)
            for name, entry in getattr(vs, "_map", {}).items()
            if entry.get("book_name") != book_name and bool(entry.get("active", True))
        },
        **{name: {**entry, "active": True} for name, entry in staged_entries.items()},
    }
    staged_vs._stores = {}
    staged_vs._broken_aggregates = set()

    def staged_search(candidate_book: str, query: str, *, k: int = 20, chapters=None):
        if safe_book_name(candidate_book) == book_name:
            return search_rows(lexical_rows, query, k=k, chapters=chapters)
        return search_book(candidate_book, query, k=k, chapters=chapters)

    def staged_neighbors(candidate_book: str, chunk_ids: list[str], window: int = 1):
        if safe_book_name(candidate_book) == book_name:
            return expand_neighbors_rows(lexical_rows, chunk_ids, window=window)
        return expand_neighbors(candidate_book, chunk_ids, window=window)

    details = []
    for case in cases:
        state = {
            "user_input": str(case.get("question") or ""),
            "book_name": book_name,
            "intent": str(case.get("intent") or "factual_recall"),
            "target_chapters": list(case.get("target_chapters") or []),
            "use_textbook_context": True,
            "retrieval_error": "",
        }
        result = retrieve_node(
            state,
            vector_store=staged_vs,
            lexical_search=staged_search,
            neighbor_expander=staged_neighbors,
            index_stats_override={book_name: {
                "book_name": book_name,
                "collection_count": len(staged_entries),
                "chunk_count": sum(not bool(row.get("retrieval_excluded")) for row in lexical_rows),
                "catalog_chunk_count": len(lexical_rows),
                "lexical_chunk_count": sum(not bool(row.get("retrieval_excluded")) for row in lexical_rows),
                "vector_ready": True,
                "lexical_ready": True,
                "healthy": True,
                "status": "ready",
            }},
        )
        if not case.get("answerable", True):
            support = str((result.get("evidence_support") or {}).get("status") or "")
            items = [] if support == "insufficient" else list(result.get("evidence_items") or [])
        else:
            pack = build_evidence_pack(
                result.get("evidence_items") or [],
                result.get("chapter_contents") or {},
                intent=str(case.get("intent") or "factual_recall"),
            )
            items = [{"chunk_id": "final-evidence-pack", "text": str(pack.get("text") or "")}]
        details.append(score_case(case, items, k=20))
    summary = aggregate(details)
    summary["specialty_gates"] = _specialty_gates(cases, details, specialty_inventory or {})
    summary["generated_probe_cases"] = sum(
        "generated_probe" in (case.get("tags") or []) for case in cases
    )
    summary["status"] = "passed"
    failed_specialties = [
        name for name, gate in summary["specialty_gates"].items()
        if not gate.get("passed", False)
    ]
    if (
        summary["recall_at_k"] < RELEASE_MIN_RECALL
        or summary["point_recall"] < RELEASE_MIN_POINT_RECALL
        or failed_specialties
    ):
        failed = [
            item["id"] for item in details
            if item["recall_at_k"] < 1 or item["point_recall"] < RELEASE_MIN_POINT_RECALL
        ]
        raise RuntimeError(
            "staged production retrieval release gate failed: "
            f"recall={summary['recall_at_k']:.3f}, point_recall={summary['point_recall']:.3f}, "
            f"failed={failed}, specialty_gates={failed_specialties}"
        )
    return summary


def _case_specialty(case: dict) -> str:
    explicit = str(case.get("specialty") or "").strip().lower()
    if explicit in {"formula", "list", "example", "table"}:
        return explicit
    if str(case.get("intent") or "").strip().lower() == "formula":
        return "formula"
    tags = {str(tag).strip().lower() for tag in case.get("tags") or []}
    return next((name for name in ("formula", "list", "example", "table") if name in tags), "")


def _specialty_gates(
    cases: list[dict],
    details: list[dict],
    inventory: dict[str, int],
) -> dict[str, dict]:
    """Score four independent structural gates without hiding sparse coverage."""
    from evaluation.rag_eval import aggregate

    detail_by_id = {str(item.get("id") or ""): item for item in details}
    result: dict[str, dict] = {}
    for specialty in ("formula", "list", "example", "table"):
        thresholds = SPECIALTY_RELEASE_THRESHOLDS[specialty]
        specialty_cases = [case for case in cases if _case_specialty(case) == specialty]
        specialty_details = [
            detail_by_id[str(case.get("id") or "")]
            for case in specialty_cases if str(case.get("id") or "") in detail_by_id
        ]
        source_units = max(0, int(inventory.get(specialty, 0) or 0))
        applicable_units = max(source_units, len(specialty_cases))
        if applicable_units == 0:
            result[specialty] = {
                "status": "not_applicable", "passed": True, "source_units": 0,
                "required_cases": 0, "cases": 0, "recall_at_k": 1.0, "point_recall": 1.0,
                "thresholds": dict(thresholds),
            }
            continue
        required_cases = min(int(thresholds["max_required_cases"]), applicable_units)
        quality = aggregate(specialty_details)
        coverage_passed = len(specialty_details) >= required_cases
        quality_passed = bool(specialty_details) and (
            quality["recall_at_k"] >= float(thresholds["min_recall"])
            and quality["point_recall"] >= float(thresholds["min_point_recall"])
        )
        result[specialty] = {
            "status": "passed" if coverage_passed and quality_passed else "failed",
            "passed": coverage_passed and quality_passed,
            "source_units": source_units,
            "required_cases": required_cases,
            "cases": len(specialty_details),
            "coverage_passed": coverage_passed,
            "recall_at_k": quality["recall_at_k"],
            "point_recall": quality["point_recall"],
            "mrr": quality["mrr"],
            "thresholds": dict(thresholds),
        }
    return result


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def activate_retained_index_version(vs, book_name: str, version: str) -> dict:
    """Atomically reactivate a retained vector and lexical index version."""
    normalized = safe_book_name(book_name)
    requested = str(version or "").strip()
    if not normalized or not requested:
        raise ValueError("book_name and version are required")

    with _BUILD_LOCK:
        current_manifest = load_index_manifest(normalized)
        records = [item for item in current_manifest.get("versions", []) if isinstance(item, dict)]
        target = next((item for item in records if str(item.get("index_version") or "") == requested), None)
        if target is None:
            raise KeyError(f"retained index version not found: {requested}")

        target_names = [str(name) for name in target.get("collections", []) if str(name)]
        if not target_names:
            raise RuntimeError(f"retained index version has no collections: {requested}")
        missing = [name for name in target_names if name not in vs._map]
        if missing:
            raise RuntimeError(f"retained collections missing from chapter map: {missing[:3]}")
        for name in target_names:
            try:
                vs._client.get_collection(name)
            except Exception as exc:
                raise RuntimeError(f"retained collection unavailable: {name}") from exc

        raw_lexical = Path(str(target.get("lexical_path") or ""))
        target_lexical = raw_lexical if raw_lexical.is_absolute() else Path(VECTOR_DB_PATH) / raw_lexical
        if not target_lexical.exists():
            raise RuntimeError(f"retained lexical index unavailable: {target_lexical}")

        lexical_target = index_path(normalized)
        old_lexical = lexical_target.read_bytes() if lexical_target.exists() else None
        old_map = copy.deepcopy(vs._map)
        old_manifest = copy.deepcopy(current_manifest)
        new_map = copy.deepcopy(old_map)
        for name, entry in list(new_map.items()):
            if str(entry.get("book_name") or "") == normalized:
                new_map[name] = {**entry, "active": name in target_names}

        target_entries = [new_map[name] for name in target_names]
        schema_values = [int(entry.get("schema_version", 0) or 0) for entry in target_entries]
        aggregate_name = next(
            (
                name for name in target_names
                if str(new_map[name].get("kind") or "") in {"book", "book_aggregate", "aggregate"}
            ),
            "",
        )
        activated_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        ordered_versions = [target] + [
            item for item in records if str(item.get("index_version") or "") != requested
        ]
        new_manifest = {
            **current_manifest,
            "schema_version": max(schema_values, default=0),
            "index_version": requested,
            "content_fingerprint": requested,
            "status": "ready",
            "vector_ready": True,
            "lexical_ready": True,
            "source_fallback_active": False,
            "chunk_count": int(target.get("chunk_count", 0) or 0),
            "catalog_chunk_count": int(target.get("catalog_chunk_count", target.get("chunk_count", 0)) or 0),
            "lexical_chunk_count": int(target.get("chunk_count", 0) or 0),
            "chapter_collection_count": sum(
                1 for entry in target_entries if str(entry.get("kind") or "chapter") == "chapter"
            ),
            "aggregate_collection": aggregate_name,
            "release_quality": {
                "status": "retained_version_reactivated",
                "passed": True,
                "previous_active_version": str(current_manifest.get("index_version") or ""),
            },
            "release_gate_mode": "retained_version_rollback",
            "activated_at": activated_at,
            "versions": ordered_versions,
        }

        try:
            _atomic_write_bytes(lexical_target, target_lexical.read_bytes())
            atomic_write_json(vs._map_file, new_map)
            vs._map = new_map
            atomic_write_json(manifest_path(normalized), new_manifest)
        except Exception:
            atomic_write_json(vs._map_file, old_map)
            vs._map = old_map
            atomic_write_json(manifest_path(normalized), old_manifest)
            if old_lexical is None:
                lexical_target.unlink(missing_ok=True)
            else:
                _atomic_write_bytes(lexical_target, old_lexical)
            raise

        for key in [key for key in vs._stores if key.startswith(f"{normalized}\0")]:
            vs._stores.pop(key, None)
        try:
            from ingestion import lexical_index
            with lexical_index._lock:
                lexical_index._cache.pop(normalized, None)
        except Exception:
            pass
        return new_manifest


def build_and_activate_book_index(
    vs,
    book_name: str,
    chapter_groups: list[tuple[str, list[dict]]],
    chunks: list[dict],
    *,
    acceptance_probes: list[dict] | None = None,
    specialty_inventory: dict[str, int] | None = None,
) -> dict:
    """Build new assets off to the side, validate them, then switch active mappings."""
    normalized = safe_book_name(book_name)
    if not normalized or not chunks:
        raise ValueError("book index requires a book name and non-empty chunks")
    fingerprint = _fingerprint(chunks)
    version = fingerprint[:16]
    catalog_chunks: list[dict] = []
    seen_chunk_ids: set[str] = set()
    for chunk in chunks:
        prepared = {**chunk, "book_name": normalized, "index_version": version}
        errors = chunk_provenance_errors(prepared, require_index_version=True)
        if errors:
            raise ValueError(
                f"chunk provenance contract failed for {prepared.get('chunk_id') or '<missing>'}: {errors}"
            )
        chunk_id = str(prepared["chunk_id"])
        if chunk_id in seen_chunk_ids:
            raise ValueError(f"duplicate chunk_id in index catalog: {chunk_id}")
        seen_chunk_ids.add(chunk_id)
        catalog_chunks.append(prepared)
    prepared_by_id = {str(chunk["chunk_id"]): chunk for chunk in catalog_chunks}
    prepared_groups: list[tuple[str, list[dict]]] = []
    grouped_chunk_ids: set[str] = set()
    for title, group in chapter_groups:
        unknown_ids = [
            str(chunk.get("chunk_id") or "")
            for chunk in group
            if str(chunk.get("chunk_id") or "") not in prepared_by_id
        ]
        if unknown_ids:
            raise ValueError(f"chapter group references unknown chunks: {unknown_ids[:3]}")
        prepared_group = [
            prepared_by_id[str(chunk.get("chunk_id") or "")]
            for chunk in group
            if str(chunk.get("chunk_id") or "") in prepared_by_id
            and not bool(prepared_by_id[str(chunk.get("chunk_id") or "")].get("retrieval_excluded"))
        ]
        if prepared_group:
            prepared_groups.append((title, prepared_group))
            grouped_chunk_ids.update(str(chunk["chunk_id"]) for chunk in prepared_group)
    retrieval_chunks = [
        chunk for chunk in catalog_chunks if not bool(chunk.get("retrieval_excluded"))
    ]
    if not retrieval_chunks:
        raise ValueError("book index requires at least one retrieval-enabled chunk")
    ungrouped_ids = [
        str(chunk["chunk_id"]) for chunk in retrieval_chunks
        if str(chunk["chunk_id"]) not in grouped_chunk_ids
    ]
    if ungrouped_ids:
        raise ValueError(f"retrieval chunks missing chapter group: {ungrouped_ids[:3]}")
    chunks = catalog_chunks
    chapter_groups = prepared_groups
    build_id = f"{version[:10]}{uuid.uuid4().hex[:6]}"
    staged_entries: dict[str, dict] = {}
    staged_names: list[str] = []
    lexical_target = index_path(normalized)
    lexical_stage = lexical_target.with_name(f".{lexical_target.name}.{build_id}.staging")
    old_lexical = lexical_target.read_bytes() if lexical_target.exists() else None
    old_manifest = load_index_manifest(normalized)
    new_version_lexical = versioned_lexical_path(normalized, version)
    new_version_lexical_existed = new_version_lexical.exists()

    with _BUILD_LOCK:
        try:
            for title, group in chapter_groups:
                chapter_hash = hashlib.md5(f"{normalized}\0{title}".encode("utf-8")).hexdigest()[:14]
                name = f"bk{chapter_hash}{build_id[:14]}"
                staged_names.append(name)
                count = _add_collection(vs, name, normalized, title, group)
                staged_entries[name] = {
                    "chapter": title, "book_name": normalized, "schema_version": str(INDEX_SCHEMA_VERSION),
                    "kind": "chapter", "chunk_count": count, "index_version": version,
                }

            aggregate_name = f"book{hashlib.md5(normalized.encode('utf-8')).hexdigest()[:12]}{build_id[:14]}"
            staged_names.append(aggregate_name)
            aggregate_count = _add_collection(vs, aggregate_name, normalized, f"{normalized} (aggregate)", chunks)
            staged_entries[aggregate_name] = {
                "chapter": f"{normalized} (aggregate)", "book_name": normalized,
                "schema_version": str(INDEX_SCHEMA_VERSION), "kind": "book_aggregate",
                "chunk_count": aggregate_count, "index_version": version,
            }
            probe_text = str(retrieval_chunks[0].get("content") or "")[:500]
            probe = vs._client.get_collection(aggregate_name).query(
                query_embeddings=[vs.embeddings.embed_query(probe_text)], n_results=1,
            )
            if not probe.get("ids") or not probe["ids"][0]:
                raise RuntimeError("dense query validation failed")

            lexical_stage.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(
                lexical_stage,
                [{key: chunk.get(key) for key in _LEXICAL_KEYS} for chunk in chunks],
            )
            lexical_rows = json.loads(lexical_stage.read_text(encoding="utf-8"))
            if len(lexical_rows) != len(chunks):
                raise RuntimeError("lexical index validation failed")
            from ingestion.lexical_index import search_rows, tokenize
            probe_tokens = tokenize(str(
                retrieval_chunks[0].get("content")
                or retrieval_chunks[0].get("section_title")
                or ""
            ))
            lexical_probe = probe_tokens[0] if probe_tokens else ""
            if not lexical_probe or not search_rows(lexical_rows, lexical_probe, k=1):
                raise RuntimeError("BM25 query validation failed")
            release_quality = _validate_staged_production_retrieval(
                vs,
                normalized,
                staged_entries,
                lexical_rows,
                acceptance_probes=acceptance_probes,
                specialty_inventory=specialty_inventory,
            )

            old_map = dict(vs._map)
            old_names = [name for name, entry in old_map.items() if entry.get("book_name") == normalized]
            old_active_names = [
                name for name in old_names if bool(old_map[name].get("active", True))
            ]
            old_version = str(old_manifest.get("index_version") or "")
            if not old_version and old_active_names:
                old_version = hashlib.sha256(old_lexical or b"legacy-index").hexdigest()[:16]

            activated_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            _atomic_write_bytes(new_version_lexical, lexical_stage.read_bytes())
            previous_record = None
            if old_active_names:
                old_version_lexical = versioned_lexical_path(normalized, old_version)
                if old_lexical is not None and not old_version_lexical.exists():
                    _atomic_write_bytes(old_version_lexical, old_lexical)
                previous_record = {
                    "index_version": old_version,
                    "collections": old_active_names,
                    "lexical_path": _manifest_asset_path(old_version_lexical),
                    "activated_at": str(old_manifest.get("activated_at") or ""),
                    "chunk_count": int(old_manifest.get("chunk_count", 0) or 0),
                    "catalog_chunk_count": int(
                        old_manifest.get("catalog_chunk_count", old_manifest.get("lexical_chunk_count", 0)) or 0
                    ),
                }

            candidate_records = [{
                "index_version": version,
                "provenance_schema": PROVENANCE_SCHEMA_VERSION,
                "collections": list(staged_entries),
                "lexical_path": _manifest_asset_path(new_version_lexical),
                "activated_at": activated_at,
                "chunk_count": len(retrieval_chunks),
                "catalog_chunk_count": len(chunks),
            }]
            if previous_record is not None:
                candidate_records.append(previous_record)
            candidate_records.extend(
                item for item in old_manifest.get("versions", []) if isinstance(item, dict)
            )
            versions = []
            seen_versions: set[str] = set()
            for item in candidate_records:
                item_version = str(item.get("index_version") or "")
                if not item_version or item_version in seen_versions:
                    continue
                seen_versions.add(item_version)
                versions.append(item)
                if len(versions) >= MAX_RETAINED_INDEX_VERSIONS + 1:
                    break
            retained_names = {
                str(name)
                for item in versions
                for name in item.get("collections", [])
                if str(name)
            }

            new_map = {
                name: dict(entry)
                for name, entry in old_map.items()
                if entry.get("book_name") != normalized
            }
            for name in old_names:
                if name in retained_names:
                    new_map[name] = {**old_map[name], "active": False}
            new_map.update({name: {**entry, "active": True} for name, entry in staged_entries.items()})
            pruned_names = [name for name in old_names if name not in retained_names]
            try:
                os.replace(lexical_stage, lexical_target)
                atomic_write_json(vs._map_file, new_map)
                vs._map = new_map
                for key in [key for key in vs._stores if key.startswith(f"{normalized}\0")]:
                    vs._stores.pop(key, None)
                manifest = {
                    "book_name": normalized,
                    "schema_version": INDEX_SCHEMA_VERSION,
                    "index_version": version,
                    "provenance_schema": PROVENANCE_SCHEMA_VERSION,
                    "content_fingerprint": fingerprint,
                    "status": "ready",
                    "vector_ready": True,
                    "lexical_ready": True,
                    "source_fallback_active": False,
                    "chunk_count": len(retrieval_chunks),
                    "catalog_chunk_count": len(chunks),
                    "lexical_chunk_count": len(retrieval_chunks),
                    "chapter_collection_count": len(chapter_groups),
                    "aggregate_collection": aggregate_name,
                    "release_quality": release_quality,
                    "release_gate_mode": "production_hybrid_retrieval_and_evidence_pack",
                    "activated_at": activated_at,
                    "versions": versions,
                }
                atomic_write_json(manifest_path(normalized), manifest)
            except Exception:
                atomic_write_json(vs._map_file, old_map)
                vs._map = old_map
                if old_lexical is None:
                    lexical_target.unlink(missing_ok=True)
                else:
                    restore = lexical_target.with_suffix(lexical_target.suffix + ".restore")
                    restore.write_bytes(old_lexical)
                    os.replace(restore, lexical_target)
                raise

            try:
                from ingestion import lexical_index
                with lexical_index._lock:
                    lexical_index._cache.pop(normalized, None)
            except Exception:
                pass
            for name in pruned_names:
                try:
                    vs._client.delete_collection(name)
                except Exception:
                    pass
            return manifest
        except BaseException:
            lexical_stage.unlink(missing_ok=True)
            active = set(getattr(vs, "_map", {}))
            for name in staged_names:
                if name not in active:
                    try:
                        vs._client.delete_collection(name)
                    except Exception:
                        pass
            if not new_version_lexical_existed and all(name not in active for name in staged_names):
                new_version_lexical.unlink(missing_ok=True)
            raise
