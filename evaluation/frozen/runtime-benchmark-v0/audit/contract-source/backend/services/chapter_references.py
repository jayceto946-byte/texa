"""Read-only version anchors; never rebinding by chapter number or similar title."""
from memory.session_notes import fingerprint


class ChapterReferenceResolver:
    def __init__(self, registry=None, canonical_loader=None):
        if registry is None:
            from utils.book_registry import BookRegistry
            registry = BookRegistry()
        self.registry = registry
        self.canonical_loader = canonical_loader

    def options(self, book_id=""):
        """Current version anchors for explicit classification, with isolated failures."""
        from ingestion.document_ir import load_canonical_book, canonical_book_fingerprint
        books = self.registry.list(include_archived=False)
        result, errors = [], []
        for record in books:
            if book_id and record["book_id"] != book_id:
                continue
            try:
                book = (self.canonical_loader or load_canonical_book)(record["storage_name"])
                version = canonical_book_fingerprint(book)
                for block in book.blocks:
                    if block.block_type != "heading":
                        continue
                    anchor = {"book_id": record["book_id"], "canonical_hash": version, "heading_block_id": block.block_id}
                    result.append({**anchor, "chapter_ref_id": "chapterref_" + fingerprint(anchor),
                                   "book_name_snapshot": record["display_name"], "title_snapshot": block.text,
                                   "section_path_snapshot": block.section_path, "page_start": block.page_start,
                                   "page_end": block.page_end, "resolution": "exact"})
            except (OSError, ValueError, RuntimeError):
                errors.append({"book_id": record["book_id"], "code": "chapter_unavailable"})
        return {"items": result, "errors": errors}

    def validate_classification(self, refs):
        """Accept only an exact current server anchor, never a client-invented locator."""
        book_ids = {ref.get("book_id") for ref in refs}
        known = {}
        for book_id in book_ids:
            if not book_id:
                continue
            known.update({ref["chapter_ref_id"]: ref for ref in self.options(book_id)["items"]})
        from memory.session_notes import NoteError
        if any(ref.get("chapter_ref_id") not in known for ref in refs):
            raise NoteError("invalid_document", "新增章节必须来自当前教材的可定位版本")
        return [known[ref["chapter_ref_id"]] for ref in refs]

    def resolve(self, evidence: dict) -> dict:
        record = self.registry.resolve(evidence.get("book_id") or evidence.get("book_name", ""))
        base = {"book_id": record["book_id"] if record else None,
                "book_name_snapshot": evidence.get("book_name", ""),
                "canonical_hash": evidence.get("canonical_hash"),
                "heading_block_id": None,
                "title_snapshot": evidence.get("chapter") or evidence.get("chapter_title") or "未定位章节",
                "section_path_snapshot": evidence.get("section_path") or [],
                "page_start": evidence.get("page_start") or evidence.get("page"),
                "page_end": evidence.get("page_end"), "resolution": "unresolved"}
        metadata = {k: evidence.get(k) for k in ("book_id", "book_name", "canonical_hash", "index_version", "chunk_id", "section_path", "chapter", "section_title", "page_start", "page_end", "source_block_ids")}
        if record:
            try:
                if self.canonical_loader is None:
                    from ingestion.document_ir import load_canonical_book
                    loader = load_canonical_book
                else:
                    loader = self.canonical_loader
                from ingestion.document_ir import canonical_book_fingerprint
                book = loader(record["storage_name"])
                if canonical_book_fingerprint(book) == base["canonical_hash"]:
                    path = base["section_path_snapshot"]
                    source_ids = evidence.get("source_block_ids") or []
                    source = next((b for b in book.blocks if b.block_id in source_ids), None)
                    if not path and source:
                        path = source.section_path
                    headings = [b for b in book.blocks if b.block_type == "heading" and b.section_path == path]
                    if len(headings) == 1:
                        h = headings[0]
                        base.update(heading_block_id=h.block_id, section_path_snapshot=h.section_path,
                                    title_snapshot=h.text, page_start=h.page_start, page_end=h.page_end, resolution="exact")
            except (OSError, ValueError, RuntimeError):
                pass
            if base["resolution"] != "exact":
                base.update(resolution="legacy", legacy_locator={"metadata_hash": fingerprint(metadata), "section_path": base["section_path_snapshot"], "page_start": base["page_start"]})
        anchor = {k: base[k] for k in ("book_id", "canonical_hash", "heading_block_id")}
        if base["resolution"] != "exact":
            anchor["legacy"] = base.get("legacy_locator") or fingerprint(metadata)
        base["chapter_ref_id"] = "chapterref_" + fingerprint(anchor)
        return base

    def availability(self, ref):
        record = self.registry.resolve(ref.get("book_id") or "")
        if not record:
            return "unavailable"
        try:
            from ingestion.document_ir import load_canonical_book, canonical_book_fingerprint
            book = (self.canonical_loader or load_canonical_book)(record["storage_name"])
            return "current" if canonical_book_fingerprint(book) == ref.get("canonical_hash") else "historical"
        except (OSError, ValueError, RuntimeError):
            return "unavailable"
