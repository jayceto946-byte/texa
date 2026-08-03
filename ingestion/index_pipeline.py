"""Crash-safe, versioned activation of textbook vector and lexical indexes."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

from config import VECTOR_DB_PATH
from ingestion.lexical_index import index_path
from utils.json_io import atomic_write_json
from utils.path_safety import safe_book_name

INDEX_SCHEMA_VERSION = 4
_BUILD_LOCK = threading.RLock()
_LEXICAL_KEYS = (
    "chapter", "section_title", "section_path", "chunk_index", "chunk_id",
    "parent_id", "prev_chunk_id", "next_chunk_id", "page_idx", "role",
    "content", "retrieval_text", "parent_content", "subject", "book_role",
    "rag_priority", "bbox", "equations", "block_type", "source_markdown",
    "review_status",
)


def manifest_path(book_name: str) -> Path:
    return Path(VECTOR_DB_PATH) / "_index_manifests" / f"{safe_book_name(book_name)}.json"


def load_index_manifest(book_name: str) -> dict:
    path = manifest_path(book_name)
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _fingerprint(chunks: list[dict]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(str(chunk.get("chunk_id") or "").encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(chunk.get("content") or "").encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _metadata(chunk: dict, book_name: str, chapter: str) -> dict:
    return {
        "raw_content": str(chunk.get("content") or ""),
        "section_path": json.dumps(chunk.get("section_path") or [], ensure_ascii=False),
        "parent_id": str(chunk.get("parent_id") or ""),
        "prev_chunk_id": str(chunk.get("prev_chunk_id") or ""),
        "next_chunk_id": str(chunk.get("next_chunk_id") or ""),
        "chapter": str(chunk.get("chapter") or chapter),
        "book_name": book_name,
        "chunk_index": int(chunk.get("chunk_index", 0) or 0),
        "chunk_id": str(chunk.get("chunk_id") or ""),
        "section_title": str(chunk.get("section_title") or chunk.get("chapter") or chapter),
        "page_idx": int(chunk.get("page_idx", -1) or -1),
        "role": str(chunk.get("role") or "reference"),
        "subject": str(chunk.get("subject") or ""),
        "book_role": str(chunk.get("book_role") or ""),
        "rag_priority": float(chunk.get("rag_priority", 1.0) or 1.0),
        "review_status": str(chunk.get("review_status") or ""),
        "source_markdown": str(chunk.get("source_markdown") or ""),
        "bbox": json.dumps(chunk.get("bbox") or [], ensure_ascii=False),
        "equations": json.dumps(chunk.get("equations") or [], ensure_ascii=False),
        "block_type": str(chunk.get("block_type") or "text"),
        "collection_schema": INDEX_SCHEMA_VERSION,
    }


def _add_collection(vs, name: str, book_name: str, chapter: str, chunks: list[dict]) -> int:
    try:
        vs._client.delete_collection(name)
    except Exception:
        pass
    collection = vs._client.get_or_create_collection(name)
    rows = [chunk for chunk in chunks if str(chunk.get("content") or "").strip()]
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


def build_and_activate_book_index(vs, book_name: str, chapter_groups: list[tuple[str, list[dict]]], chunks: list[dict]) -> dict:
    """Build new assets off to the side, validate them, then switch active mappings."""
    normalized = safe_book_name(book_name)
    if not normalized or not chunks:
        raise ValueError("book index requires a book name and non-empty chunks")
    fingerprint = _fingerprint(chunks)
    version = fingerprint[:16]
    build_id = f"{version[:10]}{uuid.uuid4().hex[:6]}"
    staged_entries: dict[str, dict] = {}
    staged_names: list[str] = []
    lexical_target = index_path(normalized)
    lexical_stage = lexical_target.with_name(f".{lexical_target.name}.{build_id}.staging")
    old_lexical = lexical_target.read_bytes() if lexical_target.exists() else None

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
            probe_text = str(chunks[0].get("content") or "")[:500]
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
            probe_tokens = tokenize(str(chunks[0].get("content") or chunks[0].get("section_title") or ""))
            lexical_probe = probe_tokens[0] if probe_tokens else ""
            if not lexical_probe or not search_rows(lexical_rows, lexical_probe, k=1):
                raise RuntimeError("BM25 query validation failed")

            old_map = dict(vs._map)
            old_names = [name for name, entry in old_map.items() if entry.get("book_name") == normalized]
            new_map = {name: entry for name, entry in old_map.items() if entry.get("book_name") != normalized}
            new_map.update(staged_entries)
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
                    "content_fingerprint": fingerprint,
                    "status": "ready",
                    "vector_ready": True,
                    "lexical_ready": True,
                    "source_fallback_active": False,
                    "chunk_count": len(chunks),
                    "lexical_chunk_count": len(lexical_rows),
                    "chapter_collection_count": len(chapter_groups),
                    "aggregate_collection": aggregate_name,
                    "activated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
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
            for name in old_names:
                if name not in staged_entries:
                    try:
                        vs._client.delete_collection(name)
                    except Exception:
                        pass
            return manifest
        except Exception:
            lexical_stage.unlink(missing_ok=True)
            active = set(getattr(vs, "_map", {}))
            for name in staged_names:
                if name not in active:
                    try:
                        vs._client.delete_collection(name)
                    except Exception:
                        pass
            raise
