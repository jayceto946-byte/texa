"""向量存储模块 - 为每个教材章节创建独立的向量数据库"""
import hashlib
import json
import threading
import time
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from config import VECTOR_DB_PATH, get_embeddings
from utils.json_io import atomic_write_json
from utils.path_safety import safe_book_name

# ── 全局单例缓存 ──────────────────────────────────────────
_chapter_vs_instance = None
_chapter_vs_lock = threading.RLock()
MAX_CHAPTER_FANOUT = 12


def get_vector_store() -> "ChapterVectorStore":
    """获取全局 ChapterVectorStore 单例实例（避免每次请求重复初始化）"""
    global _chapter_vs_instance
    if _chapter_vs_instance is not None:
        return _chapter_vs_instance
    with _chapter_vs_lock:
        if _chapter_vs_instance is None:
            _chapter_vs_instance = ChapterVectorStore()
        return _chapter_vs_instance


def reset_vector_store() -> None:
    """Clear cached Chroma handles after vector DB replacement/rebuild."""
    global _chapter_vs_instance
    with _chapter_vs_lock:
        _chapter_vs_instance = None


class ChapterVectorStore:
    """每个教材章节独立的向量存储管理器。"""

    def __init__(self):
        print("  [向量库] 初始化中...", flush=True)
        self.embeddings = get_embeddings()
        self.db_path = Path(VECTOR_DB_PATH)
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._stores: dict[str, Chroma] = {}
        self._broken_aggregates: set[str] = set()
        self._write_lock = threading.RLock()
        self._map_file = self.db_path / "_chapter_map.json"
        self._map: dict[str, dict[str, str]] = self._load_map()
        self.available = True
        # Chroma clients for one path share an underlying System. Keep one
        # owner alive so temporary health checks cannot tear down HNSW readers
        # still used by the LangChain wrappers.
        import chromadb

        self._client = chromadb.PersistentClient(path=str(self.db_path))
        # Recover mapping from existing collection metadata when Chroma is healthy.
        try:
            self._recover_map_from_collections()
        except Exception as e:
            self.available = False
            print(f"  [vector_store] Chroma unavailable, retrieval will degrade: {e}", flush=True)
        # Preload only when Chroma can be opened successfully.
        if self.available:
            self._preload_all_stores()
        print("  [向量库] 就绪（已缓存，后续请求复用）", flush=True)

    def _preload_all_stores(self):
        """Preload only book-level aggregate stores; chapter stores are lazy-loaded."""
        try:
            cols = [c for c in self._client.list_collections() if self._is_book_collection(c.name)]
            for col in cols:
                title = self._collection_to_title(col.name)
                book_name = self._collection_to_book(col.name)
                store_key = self._store_key(title, book_name)
                if store_key not in self._stores:
                    try:
                        store = Chroma(
                            collection_name=col.name,
                            embedding_function=self.embeddings,
                            persist_directory=str(self.db_path),
                            client=self._client,
                        )
                        self._stores[store_key] = store
                    except Exception:
                        pass
            if self._stores:
                print(f"  [vector_store] preloaded {len(self._stores)} aggregate stores", flush=True)
        except Exception:
            pass
    # === 章节名 ↔ collection 名 映射 ===

    def _load_map(self) -> dict[str, dict[str, str]]:
        """加载映射: {collection_name: {chapter, book_name, schema_version}}.

        兼容旧格式 {collection_name: chapter_title}，但不在加载时写回，
        避免仅初始化就改动用户现有向量库元数据。
        """
        if self._map_file.exists():
            with open(self._map_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            result: dict[str, dict[str, str]] = {}
            if isinstance(raw, dict):
                for collection_name, value in raw.items():
                    if isinstance(value, dict):
                        result[collection_name] = {
                            "chapter": str(value.get("chapter") or value.get("title") or collection_name),
                            "book_name": str(value.get("book_name") or ""),
                            "schema_version": str(value.get("schema_version") or "2"),
                            "kind": str(value.get("kind") or "chapter"),
                        }
                    else:
                        result[collection_name] = {
                            "chapter": str(value or collection_name),
                            "book_name": "",
                            "schema_version": "1",
                            "kind": "chapter",
                        }
            return result
        return {}

    def _save_map(self):
        atomic_write_json(self._map_file, self._map)

    def _recover_map_from_collections(self):
        """从已有 collection 的 metadata 恢复章节标题映射。"""
        changed = False
        for col in self._client.list_collections():
            if col.name in self._map or col.name == "_chapter_map.json":
                continue
            try:
                peek = col.peek(limit=1)
                metas = peek.get("metadatas", []) if peek else []
                if metas and metas[0]:
                    title = metas[0].get("chapter", "")
                    if title:
                        self._map[col.name] = {
                            "chapter": title,
                            "book_name": str(metas[0].get("book_name") or ""),
                            "schema_version": str(metas[0].get("collection_schema") or "2"),
                        }
                        changed = True
            except Exception:
                pass
        if changed:
            self._save_map()

    def _chapter_collection_name(self, chapter_title: str, book_name: str = "") -> str:
        """为章节生成合法的 collection 名。

        旧索引未记录教材名时继续使用历史规则；新索引传入 book_name 后
        使用 book+chapter 哈希，避免多教材同名章节互相覆盖或混检。
        """
        normalized_book = safe_book_name(book_name) if book_name else ""
        if normalized_book:
            h = hashlib.md5(f"{normalized_book}\0{chapter_title}".encode("utf-8")).hexdigest()[:24]
            return f"bk{h}"
        safe = "".join(c if c.isascii() and c.isalnum() or c in "_-" else "" for c in chapter_title)
        if len(safe) >= 3 and safe[0].isalnum() and safe[-1].isalnum():
            return safe[:63]
        h = hashlib.md5(chapter_title.encode()).hexdigest()[:16]
        return f"ch{h}"

    def _book_collection_name(self, book_name: str) -> str:
        normalized_book = safe_book_name(book_name) if book_name else "all"
        h = hashlib.md5(normalized_book.encode("utf-8")).hexdigest()[:24]
        return f"book{h}"

    def _is_book_collection(self, collection_name: str) -> bool:
        entry = self._map.get(collection_name) or {}
        return entry.get("kind") == "book_aggregate" or str(collection_name).startswith("book")
    def _collection_to_title(self, collection_name: str) -> str:
        """collection 名 -> 中文标题。"""
        entry = self._map.get(collection_name)
        return entry.get("chapter", collection_name) if entry else collection_name

    def _collection_to_book(self, collection_name: str) -> str:
        entry = self._map.get(collection_name)
        return entry.get("book_name", "") if entry else ""

    @staticmethod
    def _store_key(chapter_title: str, book_name: str = "") -> str:
        return f"{safe_book_name(book_name) if book_name else ''}\0{chapter_title}"

    def _title_to_collection(self, chapter_title: str, book_name: str = "") -> str:
        """中文标题 -> collection 名（反向查）。"""
        normalized_book = safe_book_name(book_name) if book_name else ""
        for col, entry in self._map.items():
            if entry.get("chapter") == chapter_title and entry.get("book_name", "") == normalized_book:
                return col
        if normalized_book:
            for col, entry in self._map.items():
                if entry.get("chapter") == chapter_title and not entry.get("book_name"):
                    return col
        return self._chapter_collection_name(chapter_title, normalized_book)

    def _iter_collections_for_book(self, collections, book_name: str = ""):
        normalized_book = safe_book_name(book_name) if book_name else ""
        scoped = []
        legacy = []
        for col in collections:
            if col.name == "_chapter_map.json" or self._is_book_collection(col.name):
                continue
            entry_book = self._collection_to_book(col.name)
            if normalized_book:
                if entry_book == normalized_book:
                    scoped.append(col)
                elif not entry_book:
                    legacy.append(col)
            else:
                scoped.append(col)
        return scoped or legacy

    def _delete_collection_if_exists(self, collection_name: str) -> None:
        try:
            self._client.delete_collection(collection_name)
        except Exception:
            pass

    # === 核心 API ===

    def build_chapter_store(
        self,
        chapter_title: str,
        chunks: list[dict],
        chunk_roles: dict[str, str] | None = None,
        book_name: str = "",
    ):
        """为单个章节创建向量存储。

        Args:
            chunk_roles: {chunk_id: role} 映射，用于写入 metadata
            book_name: 教材名，用于隔离同名章节索引
        """
        normalized_book = safe_book_name(book_name) if book_name else ""
        collection_name = self._chapter_collection_name(chapter_title, normalized_book)
        chunk_roles = chunk_roles or {}
        store_key = self._store_key(chapter_title, normalized_book)
        self._stores.pop(store_key, None)
        self._delete_collection_if_exists(collection_name)

        documents = [
            Document(
                page_content=chunk.get("retrieval_text") or chunk["content"],
                metadata={
                    "raw_content": chunk.get("content", ""),
                    "section_path": json.dumps(chunk.get("section_path", []), ensure_ascii=False),
                    "parent_id": chunk.get("parent_id", ""),
                    "prev_chunk_id": chunk.get("prev_chunk_id", ""),
                    "next_chunk_id": chunk.get("next_chunk_id", ""),
                    "chapter": chunk.get("chapter", chapter_title),
                    "book_name": normalized_book,
                    "chunk_index": chunk.get("chunk_index", 0),
                    "chunk_id": chunk.get("chunk_id", ""),
                    "section_title": chunk.get("section_title", chunk.get("chapter", chapter_title)),
                    "page_idx": chunk.get("page_idx", -1),
                    "role": chunk_roles.get(chunk.get("chunk_id", ""), "reference"),
                    "subject": chunk.get("subject", ""),
                    "book_role": chunk.get("book_role", ""),
                    "rag_priority": float(chunk.get("rag_priority", 1.0) or 1.0),
                    "review_status": chunk.get("review_status", ""),
                    "source_markdown": chunk.get("source_markdown", ""),
                    "bbox": json.dumps(chunk.get("bbox", []), ensure_ascii=False),
                    "equations": json.dumps(chunk.get("equations", []), ensure_ascii=False),
                    "block_type": chunk.get("block_type", "text"),
                    "collection_schema": 2,
                },
            )
            for chunk in chunks
        ]

        store = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            collection_name=collection_name,
            persist_directory=str(self.db_path),
            client=self._client,
        )
        self._stores[store_key] = store
        self._map[collection_name] = {
            "chapter": chapter_title,
            "book_name": normalized_book,
            "schema_version": "2",
        }
        self._save_map()
        return store

    def build_book_aggregate_store(self, book_name: str, chunks: list[dict]) -> Chroma | None:
        """Build a versioned whole-book collection and switch the map after success."""
        normalized_book = safe_book_name(book_name) if book_name else ""
        if not normalized_book or not chunks:
            return None
        fingerprint = hashlib.sha1()
        fingerprint.update(normalized_book.encode("utf-8"))
        for chunk in chunks:
            fingerprint.update(str(chunk.get("chunk_id") or "").encode("utf-8"))
            fingerprint.update(str(chunk.get("content") or "").encode("utf-8"))
        book_hash = hashlib.md5(normalized_book.encode("utf-8")).hexdigest()[:12]
        collection_name = f"book{book_hash}{fingerprint.hexdigest()[:12]}"
        documents = [
            Document(
                page_content=chunk.get("retrieval_text") or chunk.get("content", ""),
                metadata={
                    "raw_content": chunk.get("content", ""),
                    "section_path": json.dumps(chunk.get("section_path", []), ensure_ascii=False),
                    "parent_id": chunk.get("parent_id", ""),
                    "prev_chunk_id": chunk.get("prev_chunk_id", ""),
                    "next_chunk_id": chunk.get("next_chunk_id", ""),
                    "chapter": chunk.get("chapter", ""),
                    "book_name": normalized_book,
                    "chunk_index": chunk.get("chunk_index", 0),
                    "chunk_id": chunk.get("chunk_id", ""),
                    "section_title": chunk.get("section_title", chunk.get("chapter", "")),
                    "page_idx": chunk.get("page_idx", -1),
                    "role": chunk.get("role", "reference"),
                    "subject": chunk.get("subject", ""),
                    "book_role": chunk.get("book_role", ""),
                    "rag_priority": float(chunk.get("rag_priority", 1.0) or 1.0),
                    "review_status": chunk.get("review_status", ""),
                    "source_markdown": chunk.get("source_markdown", ""),
                    "bbox": json.dumps(chunk.get("bbox", []), ensure_ascii=False),
                    "equations": json.dumps(chunk.get("equations", []), ensure_ascii=False),
                    "block_type": chunk.get("block_type", "text"),
                    "collection_schema": 3,
                },
            )
            for chunk in chunks
            if str(chunk.get("content") or "").strip()
        ]
        if not documents:
            return None
        existing = self._map.get(collection_name)
        if not existing:
            try:
                store = Chroma.from_documents(
                    documents=documents,
                    embedding=self.embeddings,
                    collection_name=collection_name,
                    persist_directory=str(self.db_path),
                    client=self._client,
                )
            except Exception:
                self._delete_collection_if_exists(collection_name)
                raise
        else:
            store = Chroma(
                collection_name=collection_name,
                embedding_function=self.embeddings,
                persist_directory=str(self.db_path),
                client=self._client,
            )
        old_names = [
            name for name, entry in self._map.items()
            if entry.get("kind") == "book_aggregate" and entry.get("book_name") == normalized_book and name != collection_name
        ]
        for old_name in old_names:
            self._map.pop(old_name, None)
        self._map[collection_name] = {
            "chapter": f"{normalized_book} (aggregate)",
            "book_name": normalized_book,
            "schema_version": "3",
            "kind": "book_aggregate",
            "chunk_count": len(documents),
        }
        self._save_map()
        for old_name in old_names:
            self._delete_collection_if_exists(old_name)
        return store

    def get_chapter_store(self, chapter_title: str, book_name: str = "") -> Chroma | None:
        """获取章节的向量存储（支持中文标题或 collection 名）。"""
        if not self.available:
            return None
        normalized_book = safe_book_name(book_name) if book_name else ""
        store_key = self._store_key(chapter_title, normalized_book)
        if store_key in self._stores:
            return self._stores[store_key]

        collection_name = self._title_to_collection(chapter_title, normalized_book)
        try:
            # LangChain's Chroma wrapper uses get-or-create semantics. A read
            # miss must be checked first, otherwise querying an unknown planner
            # subsection leaves an empty collection with no HNSW files.
            self._client.get_collection(collection_name)
            store = Chroma(
                collection_name=collection_name,
                embedding_function=self.embeddings,
                persist_directory=str(self.db_path),
                client=self._client,
            )
            self._stores[store_key] = store
            return store
        except Exception:
            return None

    def get_chapter_names(self, book_name: str = "") -> list[str]:
        """获取所有已索引的章节名（返回中文标题）。"""
        normalized_book = safe_book_name(book_name) if book_name else ""

        def mapped_names() -> list[str]:
            return [
                entry.get("chapter", "")
                for entry in self._map.values()
                if entry.get("chapter") and (not normalized_book or entry.get("book_name") in {normalized_book, ""})
            ]

        if not self.available:
            return mapped_names()
        try:
            collections = self._client.list_collections()
        except Exception as e:
            self.available = False
            print(f"  [vector_store] list_collections failed, using chapter map only: {e}", flush=True)
            return mapped_names()
        names = []
        for col in self._iter_collections_for_book(collections, normalized_book):
            names.append(self._collection_to_title(col.name))
        return names

    def get_book_index_stats(self, book_name: str) -> dict:
        """Return safe per-book health without opening every HNSW segment."""
        normalized_book = safe_book_name(book_name) if book_name else ""
        stats = {"book_name": normalized_book, "collection_count": 0, "chunk_count": 0, "healthy": False}
        if not normalized_book:
            return stats
        try:
            stats["collection_count"] = sum(
                1
                for collection in self._client.list_collections()
                if not self._is_book_collection(collection.name)
                and self._collection_to_book(collection.name) == normalized_book
            )
        except Exception as exc:
            stats["error"] = str(exc)
            return stats
        try:
            from ingestion.index_pipeline import load_index_manifest
            from ingestion.lexical_index import index_path, load_book_index
            stats["lexical_chunk_count"] = len(load_book_index(normalized_book))
            stats["lexical_ready"] = index_path(normalized_book).exists() and stats["lexical_chunk_count"] > 0
            stats["source_fallback_active"] = not stats["lexical_ready"] and stats["lexical_chunk_count"] > 0
            manifest = load_index_manifest(normalized_book)
            stats["index_version"] = str(manifest.get("index_version") or "")
            stats["index_schema"] = int(manifest.get("schema_version", 0) or 0)
        except Exception:
            stats["lexical_chunk_count"] = 0
            stats["lexical_ready"] = False
            stats["source_fallback_active"] = False
            stats["index_version"] = ""
            stats["index_schema"] = 0
        # Avoid count() across all HNSW segments; the activated map and lexical
        # corpus are independent, safe readiness signals.
        stats["chunk_count"] = stats["lexical_chunk_count"]
        stats["vector_ready"] = stats["collection_count"] > 0
        stats["healthy"] = stats["vector_ready"] or stats["lexical_ready"] or stats["source_fallback_active"]
        stats["status"] = "ready" if stats["vector_ready"] and stats["lexical_ready"] else ("degraded" if stats["healthy"] else "missing")
        return stats

    def search_chapter(
        self,
        chapter_title: str,
        query: str,
        k: int = 5,
        filter: dict | None = None,
        book_name: str = "",
    ) -> list[Document]:
        """在指定章节中检索相关内容。"""
        store = self.get_chapter_store(chapter_title, book_name=book_name)
        if store is None:
            return []
        kwargs = {"k": k}
        if filter:
            kwargs["filter"] = filter
        try:
            return store.similarity_search(query, **kwargs)
        except Exception as e:
            self._stores.pop(self._store_key(chapter_title, book_name), None)
            print(f"  [向量库] 章节检索失败，已跳过 {chapter_title}: {e}", flush=True)
            return []

    def _aggregate_collections(self, collections, book_name: str = ""):
        normalized_book = safe_book_name(book_name) if book_name else ""
        result = []
        for col in collections:
            if not self._is_book_collection(col.name):
                continue
            entry_book = self._collection_to_book(col.name)
            if not normalized_book or entry_book == normalized_book:
                result.append(col)
        return result

    def _search_aggregate_collections(
        self,
        collections,
        query_vec,
        k: int,
        top_n: int,
        filter: dict | None = None,
    ) -> tuple[dict[str, list[Document]], int] | None:
        scored_docs: list[tuple[float, Document]] = []
        searched = 0
        for col in collections:
            if col.name in self._broken_aggregates:
                continue
            try:
                title = self._collection_to_title(col.name)
                store_key = self._store_key(title, self._collection_to_book(col.name))
                store = self._stores.get(store_key)
                if store is None:
                    store = Chroma(
                        collection_name=col.name,
                        embedding_function=self.embeddings,
                        persist_directory=str(self.db_path),
                        client=self._client,
                    )
                    self._stores[store_key] = store
                kwargs = {"k": max(k * top_n * 4, k)}
                if filter:
                    kwargs["filter"] = filter
                try:
                    docs_with_scores = store.similarity_search_by_vector_with_relevance_scores(query_vec, **kwargs)
                except Exception:
                    docs = store.similarity_search_by_vector(query_vec, **kwargs)
                    docs_with_scores = [(d, float(i)) for i, d in enumerate(docs)]
                for doc, score in docs_with_scores:
                    meta = getattr(doc, "metadata", {}) or {}
                    priority = float(meta.get("rag_priority") or 1.0)
                    # Existing search_all treats smaller score as better; high-priority sources get a mild boost.
                    adjusted = float(score) - (priority * 0.03)
                    scored_docs.append((adjusted, doc))
                searched += 1
            except Exception as exc:
                self._broken_aggregates.add(col.name)
                title = self._collection_to_title(col.name)
                self._stores.pop(self._store_key(title, self._collection_to_book(col.name)), None)
                print(f"  [向量库] aggregate 检索失败，已隔离 {col.name}: {exc}", flush=True)
        if not searched:
            return None

        scored_docs.sort(key=lambda item: item[0])
        chapter_docs: dict[str, list[Document]] = {}
        for _, doc in scored_docs:
            meta = getattr(doc, "metadata", {}) or {}
            chapter = str(meta.get("chapter") or meta.get("section_title") or "相关章节")
            chapter_docs.setdefault(chapter, [])
            if len(chapter_docs[chapter]) >= k:
                continue
            chapter_docs[chapter].append(doc)
            if len(chapter_docs) >= top_n and all(len(docs) >= k for docs in chapter_docs.values()):
                break
        return dict(list(chapter_docs.items())[:top_n]), searched
    def search_all(
        self,
        query: str,
        k: int = 3,
        top_n: int = 3,
        filter: dict | None = None,
        book_name: str = "",
        fallback_chapters: list[str] | None = None,
    ) -> dict[str, list[Document]]:
        """在所有章节中检索。

        query 只 embed 一次，按相似度排序，只返回最相关的 top_n 章。
        传入 book_name 后只检索该教材索引；若该教材没有新格式索引，则兼容旧索引。
        """
        if not self.available:
            return {}
        t0 = time.time()
        query_vec = self.embeddings.embed_query(query)
        dt_embed = time.time() - t0

        scored_results: list[tuple[str, list[Document], float]] = []
        try:
            collections = self._client.list_collections()
        except Exception as e:
            self.available = False
            print(f"  [vector_store] search_all skipped because Chroma is unavailable: {e}", flush=True)
            return {}
        aggregate_cols = self._aggregate_collections(collections, book_name)
        if aggregate_cols:
            aggregate_result = self._search_aggregate_collections(aggregate_cols, query_vec, k, top_n, filter=filter)
            if aggregate_result is not None:
                results, searched = aggregate_result
                dt_total = time.time() - t0
                print(f"  [检索] aggregate embed={dt_embed:.2f}s total={dt_total:.2f}s ({searched}书→取top{len(results)})", flush=True)
                return results

        chapter_collections = list(self._iter_collections_for_book(collections, book_name))
        if fallback_chapters:
            chapter_rank = {str(title): rank for rank, title in enumerate(fallback_chapters[:MAX_CHAPTER_FANOUT])}
            chapter_collections = [
                col for col in chapter_collections if self._collection_to_title(col.name) in chapter_rank
            ]
            chapter_collections.sort(key=lambda col: chapter_rank[self._collection_to_title(col.name)])
        elif len(chapter_collections) > MAX_CHAPTER_FANOUT:
            print(
                f"  [向量库] aggregate 不可用且无章节 shortlist，已阻止扫描 {len(chapter_collections)} 个 collection",
                flush=True,
            )
            return {}

        searched = 0
        for col in chapter_collections:
            title = self._collection_to_title(col.name)
            try:
                store_key = self._store_key(title, self._collection_to_book(col.name))
                store = self._stores.get(store_key)
                if store is None:
                    store = Chroma(
                        collection_name=col.name,
                        embedding_function=self.embeddings,
                        persist_directory=str(self.db_path),
                        client=self._client,
                    )
                    self._stores[store_key] = store
                try:
                    kwargs = {"k": k}
                    if filter:
                        kwargs["filter"] = filter
                    docs_with_scores = store.similarity_search_by_vector_with_relevance_scores(query_vec, **kwargs)
                except Exception:
                    kwargs = {"k": k}
                    if filter:
                        kwargs["filter"] = filter
                    docs = store.similarity_search_by_vector(query_vec, **kwargs)
                    docs_with_scores = [(d, 1.0) for d in docs]
                if docs_with_scores:
                    docs = [d for d, _ in docs_with_scores]
                    best_score = min(score for _, score in docs_with_scores)
                    scored_results.append((title, docs, best_score))
                searched += 1
            except Exception:
                pass

        scored_results.sort(key=lambda item: item[2])
        top_results = scored_results[:top_n]
        results = {title: docs for title, docs, _ in top_results}

        dt_total = time.time() - t0
        print(f"  [检索] embed={dt_embed:.2f}s total={dt_total:.2f}s ({searched}章→取top{len(top_results)})", flush=True)
        return results