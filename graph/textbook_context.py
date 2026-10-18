"""Deterministic, version-bound learning sections; no search or model calls.

Expansion is an ephemeral projection of Canonical IR. ``complete`` describes
an intact, bounded IR section, never a proof of OCR or mathematical correctness.
"""
from __future__ import annotations

import hashlib
import json
import re

from ingestion.document_ir import OCR_SOURCE_KINDS, PROVENANCE_SCHEMA_VERSION, canonical_retrieval_paths
from ingestion.index_snapshot import read_snapshot

CONTEXT_VERSION = "textbook-context/v1"
_MAX_BLOCKS = 128
_FIGURE_REF = re.compile(r"图\s*([0-9]+(?:[.．-][0-9]+)*)")
_CONTINUATION_HEADING = re.compile(r"^\s*(?:证明|推导|解答|分析|例题|例\s*\d|解\s*[:：])")


def _eligible(item: dict, intent: str) -> bool:
    return (intent in {"teach", "summarize", "derivation", "application"}
            or item.get("role") in {"definition", "derivation", "example", "algorithm", "formula", "property"}
            or item.get("block_type") in {"example", "exercise", "formula"}
            or bool(re.search(r"定理|定义|证明|推导|例\s*\d", str(item.get("text") or ""))))


def _unknown(item: dict, reason: str) -> dict:
    return {**item, "learning_unit": {"version": CONTEXT_VERSION, "status": "unknown",
            "text_status": "unknown", "source_status": "unknown", "reason": reason,
            "figures": [], "boundary": "unresolved"}}


def _section(book, positions: dict, source_ids: list[str]):
    first, last = min(positions[value] for value in source_ids), max(positions[value] for value in source_ids)
    target = book.blocks[first].section_path
    # Use the nearest enclosing content heading. A proof/solution subheading
    # is not a safe start: its hypotheses or stem may precede it.
    headings = [n for n in range(first + 1) if book.blocks[n].block_type == "heading"
                and book.blocks[n].section_path
                and target[:len(book.blocks[n].section_path)] == book.blocks[n].section_path
                and not _CONTINUATION_HEADING.match(book.blocks[n].text)]
    for start in reversed(headings):
        path = book.blocks[start].section_path
        end = next((n for n in range(start + 1, len(book.blocks))
                    if book.blocks[n].block_type == "heading"
                    and len(book.blocks[n].section_path) <= len(path)), len(book.blocks))
        if last < end:
            # MinerU preserves many numbered content titles as paragraph_title,
            # beneath the indexed heading. Use only that explicit source
            # structure (not arbitrary prose matches) to avoid expanding an
            # entire materials/classification section for one local derivation.
            titles = [n for n in range(start + 1, end)
                      if book.blocks[n].attributes.get("mineru_type") == "paragraph_title"
                      and book.blocks[n].block_type != "heading"
                      and re.match(r"^\s*(?:\d+[.．、]|[一二三四五六七八九十]+[、])", book.blocks[n].text)]
            local_start = max((n for n in titles if n <= first), default=start)
            local_end = next((n for n in titles if n > last), end)
            return local_start, local_end, "heading" if (local_start, local_end) == (start, end) else "source_title"
    # Old sources can have section paths without headings. Keep them useful,
    # but adjacency/path equality alone does not establish completeness.
    start, end = first, last + 1
    while start > 0 and book.blocks[start - 1].section_path == target:
        start -= 1
    while end < len(book.blocks) and book.blocks[end].section_path == target:
        end += 1
    return start, end, "path_only"


def _block_payload(block) -> dict:
    text = block.text
    # Equations are first-class IR fields; some sources omit them from text.
    for equation in block.equations:
        if equation.strip() and equation.strip() not in text:
            text += "\n\n" + equation
    if block.block_type == "table" and block.table_rows:
        rendered = "\n".join(" | ".join(row) for row in [block.table_header, *block.table_rows] if row)
        if rendered and rendered not in text:
            text += "\n\n" + rendered
    return {"block_id": block.block_id, "block_type": block.block_type, "text": text,
            "equations": list(block.equations), "review_status": block.review_status,
            "section_path": list(block.section_path),
            "source_location": {"block_id": block.block_id, "source_kind": block.source_kind,
                "source_file": block.source_file, "page_start": block.page_start, "page_end": block.page_end,
                "bbox": list(block.bbox or []),
                **{key: str(block.attributes.get(key) or "unknown")
                   for key in ("bbox_space", "bbox_format", "bbox_units")}}}


def _figures(service, book, blocks: list, query: str, paths: dict) -> list[dict]:
    from llm.configuration import model_settings_payload
    from PIL import Image
    book_name = book.book_name
    mode = model_settings_payload()["multimodal_mode"]
    refs = set(_FIGURE_REF.findall("\n".join(block.text for block in blocks if block.block_type != "figure")))
    figures = []
    selected = list(blocks)
    selected_ids = {block.block_id for block in selected}
    chapter = paths[blocks[0].block_id][:1] if blocks else []
    # Resolve an explicit figure reference against the *same version*, without
    # broadening chapter scope. A resource elsewhere is not a missing image.
    unresolved = {}
    for ref in refs:
        matches = [block for block in book.blocks if block.block_type == "figure"
                   and ref in _FIGURE_REF.findall(block.text)]
        if len(matches) == 1 and paths[matches[0].block_id][:1] == chapter:
            if matches[0].block_id not in selected_ids:
                selected.append(matches[0])
                selected_ids.add(matches[0].block_id)
        elif matches:
            unresolved[ref] = "ambiguous_or_outside_chapter"
    candidates = [block for block in selected if block.block_type == "figure"]
    found = {label for block in candidates for label in _FIGURE_REF.findall(block.text)}
    for block in candidates[:8]:
        labels = set(_FIGURE_REF.findall(block.text))
        required = bool(refs & labels) or bool(re.search(r"图|figure|diagram", query, re.I))
        attributes = block.attributes
        status = "missing"
        try:
            path = service.asset_path(book_name, block.block_id)
            expected = str(attributes.get("content_hash") or "")
            status = "available" if expected and hashlib.sha256(path.read_bytes()).hexdigest() == expected else "unknown"
            if status == "available":
                status = "unknown"
                with Image.open(path) as image:
                    if image.width * image.height > 60_000_000:
                        raise ValueError("figure pixel budget exceeded")
                    image.verify()
                status = "available"
        except (OSError, ValueError, KeyError, Image.DecompressionBombError):
            pass
        figures.append({"figure_id": block.block_id, "source_block_ids": [block.block_id], "references": sorted(labels),
            "asset_relpath": str(attributes.get("asset_relpath") or ""),
            "content_hash": str(attributes.get("content_hash") or ""),
            "page_start": block.page_start, "page_end": block.page_end,
            "required": required, "availability": status,
            "model_input": "not_read" if required else "not_required", "multimodal_mode": mode,
            "reading_role": "vision" if mode == "split" else "reasoning"})
    missing_labels = sorted(refs - found)
    for label in missing_labels[:max(0, 8 - len(figures))]:
        figures.append({"figure_id": "", "reference": "图" + label, "required": True,
                        "availability": "unknown" if label in unresolved else "missing",
                        "reason": unresolved.get(label, "resource_missing_in_canonical"),
                        "model_input": "not_read", "multimodal_mode": mode,
                        "reading_role": "vision" if mode == "split" else "reasoning"})
    if len(candidates) + len(missing_labels) > 8:
        figures.append({"figure_id": candidates[8].block_id if len(candidates) > 8 else "",
            "required": True, "availability": "unknown", "model_input": "not_read",
            "reason": "figure_resource_budget", "multimodal_mode": mode,
            "reading_role": "vision" if mode == "split" else "reasoning"})
    return figures


@read_snapshot
def expand_textbook_context(items: list[dict], *, intent: str = "qa", query: str = "", service=None) -> list[dict]:
    """Expand only retrieved anchors, within the same book/version/section.

    The original chunk ID remains an *anchor*, while source_block_ids and
    locations describe the expanded projection. No new indexed chunk is created.
    """
    from ingestion.index_pipeline import load_index_manifest
    loaded, seen_units, result = {}, {}, []
    for item in items:
        if item.get("learning_unit", {}).get("version") == CONTEXT_VERSION or not _eligible(item, intent):
            result.append(item)
            continue
        name = str(item.get("book_name") or "")
        ids = item.get("source_block_ids") or []
        if not (name and ids and item.get("index_version") and item.get("canonical_hash")
                and item.get("provenance_schema") == PROVENANCE_SCHEMA_VERSION):
            result.append(_unknown(item, "missing_versioned_anchor"))
            continue
        if name not in loaded:
            try:
                if service is None:
                    from backend.services.figure_learning import FigureLearningService
                    service = FigureLearningService()
                book = service.load_book(name)
                metadata = service.cache_metadata(name)
                manifest = load_index_manifest(name)
                loaded[name] = (book, metadata, manifest, {block.block_id: n for n, block in enumerate(book.blocks)},
                                canonical_retrieval_paths(book.blocks))
            except (OSError, ValueError, RuntimeError):
                loaded[name] = None
        if loaded[name] is None:
            result.append(_unknown(item, "canonical_unavailable"))
            continue
        book, metadata, manifest, positions, paths = loaded[name]
        if (metadata["canonical_hash"] != item["canonical_hash"]
                or manifest.get("canonical_hash") != item["canonical_hash"]
                or manifest.get("index_version") != item["index_version"]):
            result.append(_unknown(item, "source_version_mismatch"))
            continue
        if any(block_id not in positions for block_id in ids):
            result.append(_unknown(item, "source_blocks_missing"))
            continue
        start, end, boundary = _section(book, positions, ids)
        chapter = paths[ids[0]][:1]
        if not chapter or any(paths[value][:1] != chapter for value in ids):
            result.append(_unknown(item, "ambiguous_chapter_scope"))
            continue
        # MinerU may retain book-root paths. Derived numbered chapters are
        # authoritative for retrieval and must also fence contextual expansion.
        first, last = min(positions[value] for value in ids), max(positions[value] for value in ids)
        chapter_start, chapter_end = first, last + 1
        while chapter_start > 0 and paths[book.blocks[chapter_start - 1].block_id][:1] == chapter:
            chapter_start -= 1
        while chapter_end < len(book.blocks) and paths[book.blocks[chapter_end].block_id][:1] == chapter:
            chapter_end += 1
        if start < chapter_start or end > chapter_end:
            start, end, boundary = max(start, chapter_start), min(end, chapter_end), "chapter_path"
        key = (name, item["index_version"], item["canonical_hash"], start, end)
        if key in seen_units:
            unit = seen_units[key]["learning_unit"]
            unit["anchor_chunk_ids"] = list(dict.fromkeys([*unit["anchor_chunk_ids"], item["chunk_id"]]))
            unit["anchor_source_block_ids"] = list(dict.fromkeys([*unit["anchor_source_block_ids"], *ids]))
            seen_units[key]["expansion_anchors"].append(item)
            continue
        # Bound work as well as prompt size. Never call a capped scan complete.
        blocks = book.blocks[start:min(end, start + _MAX_BLOCKS)]
        payloads = [_block_payload(block) for block in blocks]
        source_status = "unknown" if (book.warnings or any(
            block.review_status or str(block.source_kind or book.source_kind).lower() in OCR_SOURCE_KINDS
            or (block.block_type not in {"figure", "heading"} and not payload["text"].strip())
            for block, payload in zip(blocks, payloads))) else "available"
        figures = _figures(service, book, blocks, query, paths)
        text_status = "partial" if len(blocks) < end - start else ("complete" if boundary == "heading" else "unknown")
        status = text_status
        if status == "complete" and (source_status == "unknown" or any(f["required"] for f in figures)):
            status = "unknown" if source_status == "unknown" else "partial"
        unit = {"version": CONTEXT_VERSION, "status": status, "text_status": text_status,
                "source_status": source_status, "boundary": boundary, "reason": "canonical_section",
                "unit_id": book.blocks[start].block_id, "anchor_chunk_ids": [item["chunk_id"]],
                "anchor_source_block_ids": list(ids), "total_blocks": end - start, "figures": figures,
                "continuation": ({"block_id": book.blocks[start + len(blocks)].block_id,
                    "index_version": item["index_version"], "canonical_hash": item["canonical_hash"],
                    "book_name": name, "unit_id": book.blocks[start].block_id, "anchor_chunk_id": item["chunk_id"],
                    "anchor_content_fingerprint": hashlib.sha256(re.sub(r"\s+", " ", str(item.get("text") or "")).strip().encode()).hexdigest()[:24]}
                    if len(blocks) < end - start else None)}
        anchor_fingerprint = hashlib.sha256(re.sub(r"\s+", " ", str(item.get("text") or "")).strip().encode()).hexdigest()[:24]
        expanded = {**item, "anchor_content_fingerprint": anchor_fingerprint, "text": "\n\n".join(p["text"] for p in payloads if p["text"]),
                    "source_block_ids": [p["block_id"] for p in payloads],
                    "source_locations": [p["source_location"] for p in payloads],
                    "context_blocks": payloads, "learning_unit": unit, "expansion_anchors": [item]}
        seen_units[key] = expanded
        result.append(expanded)
    return result


def source_locations(item: dict) -> list[dict]:
    """Resolve the lossless common-field projection used in bounded receipts."""
    common = item.get("source_location_defaults") or {}
    return [{**common, **location} for location in item.get("source_locations", [])]


def compact_locations(locations: list[dict]) -> tuple[dict, list[dict]]:
    # Keep block identity, page and bbox directly readable by existing consumers.
    keys = {"source_kind", "source_file", "bbox_space", "bbox_format", "bbox_units"}
    common = {key: locations[0][key] for key in keys if locations and key in locations[0]
              and all(location.get(key) == locations[0][key] for location in locations)}
    return common, [{key: value for key, value in location.items() if key not in common}
                    for location in locations]


def continuation_anchor(item: dict, block_id: str) -> dict:
    unit = item["learning_unit"]
    return {"block_id": block_id, "index_version": item["index_version"],
            "canonical_hash": item["canonical_hash"], "book_name": item["book_name"],
            "unit_id": unit["unit_id"], "anchor_chunk_id": item["chunk_id"],
            "anchor_content_fingerprint": str(item.get("anchor_content_fingerprint") or "")}


def provenance_size(item: dict, unit: dict, blocks: list[dict]) -> int:
    """Actual UTF-8 bytes, including identity and all per-block metadata."""
    common, locations = compact_locations([block["source_location"] for block in blocks])
    if item.get("context_blocks") is None:
        common, locations = compact_locations(source_locations(item))
    visible = {**item, "learning_unit": unit, "source_location_defaults": common, "source_locations": locations,
               "source_block_ids": ([b["block_id"] for b in blocks] if item.get("context_blocks") is not None
                                    else list(item.get("source_block_ids") or []))}
    from graph.evidence_pack import evidence_source_metadata
    # Reserve the longest E-id and character count in this bounded pack. The
    # source projection is shared with the emitted receipt, not a second estimate.
    metadata = evidence_source_metadata(item, visible, "E9999", "x" * 20000)
    metadata["context_blocks"] = [{k: v for k, v in b.items() if k not in
                                   {"text", "source_location", "equations", "section_path"}} for b in blocks]
    return len(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


@read_snapshot
def read_textbook_continuation(pointer: dict, *, service=None) -> list[dict]:
    """Read the same bounded IR unit; never search, rebind a version or write IO."""
    from ingestion.index_pipeline import load_index_manifest
    if service is None:
        from backend.services.figure_learning import FigureLearningService
        service = FigureLearningService()
    name = pointer["book_name"]
    manifest = load_index_manifest(name)
    metadata = service.cache_metadata(name)
    if (manifest.get("index_version") != pointer["index_version"]
            or manifest.get("canonical_hash") != pointer["canonical_hash"]
            or metadata["canonical_hash"] != pointer["canonical_hash"]):
        raise ValueError("textbook continuation version mismatch")
    book = service.load_book(name)
    positions = {b.block_id: n for n, b in enumerate(book.blocks)}
    if pointer["unit_id"] not in positions or pointer["block_id"] not in positions:
        raise ValueError("textbook continuation block missing")
    start, end, _ = _section(book, positions, [pointer["unit_id"]])
    position = positions[pointer["block_id"]]
    paths = canonical_retrieval_paths(book.blocks)
    chapter = paths[pointer["unit_id"]][:1]
    chapter_end = start
    while chapter_end < len(book.blocks) and paths[book.blocks[chapter_end].block_id][:1] == chapter:
        chapter_end += 1
    end = min(end, chapter_end)
    if not chapter:
        raise ValueError("textbook continuation chapter missing")
    if book.blocks[start].block_id != pointer["unit_id"] or not start <= position < end:
        raise ValueError("textbook continuation escaped unit")
    # Anchor at the requested block so the existing bounded scan begins there.
    item = {"book_name": name, "chunk_id": pointer["anchor_chunk_id"],
            "index_version": pointer["index_version"], "canonical_hash": pointer["canonical_hash"],
            "provenance_schema": PROVENANCE_SCHEMA_VERSION,
            "source_block_ids": [pointer["block_id"]], "text": book.blocks[position].text,
            "role": "derivation"}
    expanded = expand_textbook_context([item], intent="teach", service=service)[0]
    if expanded["learning_unit"].get("unit_id") != pointer["unit_id"]:
        raise ValueError("textbook continuation boundary mismatch")
    # Rebuild only this page of the unit, even beyond expansion's initial cap.
    blocks = book.blocks[position:min(end, position + _MAX_BLOCKS)]
    payloads = [_block_payload(b) for b in blocks]
    expanded["anchor_content_fingerprint"] = str(pointer.get("anchor_content_fingerprint") or "")
    unit = expanded["learning_unit"]
    if book.warnings or any(b.review_status or str(b.source_kind or book.source_kind).lower() in OCR_SOURCE_KINDS
                            for b in blocks):
        unit["source_status"] = "unknown"
    # Include resource states for this segment even when it is beyond the first scan.
    unit["figures"] = _figures(service, book, blocks, "", paths)
    unit.update(status="partial", text_status="partial", reason="continuation",
                continuation=continuation_anchor(expanded, book.blocks[position + len(blocks)].block_id)
                if position + len(blocks) < end else None)
    if position > start:
        unit["preceding"] = continuation_anchor(expanded, book.blocks[start].block_id)
    expanded.update(context_blocks=payloads, source_locations=[p["source_location"] for p in payloads],
                    source_block_ids=[p["block_id"] for p in payloads],
                    text="\n\n".join(p["text"] for p in payloads if p["text"]), expansion_anchors=[])
    return [expanded]


def pack_learning_unit(item: dict, limit: int, *, metadata_limit: int = 8000) -> tuple[str, dict, list[dict], str, int]:
    """Pack whole blocks, preferring a continuous anchor window over eviction."""
    original = dict(item["learning_unit"])
    notice = ("教材学习单元：status={status}; text={text_status}; source={source_status}。"
              "complete仅指所存IR结构完整，不证明OCR正确。partial/unknown不得补造前提、证明或原题。"
              "正文不复述内部状态或来源标记，只在缺口影响本题时自然说明限制。")
    def formatted(unit):
        rendered = notice.format(**unit)
        if unit.get("figures"):
            states = sorted({(f["availability"], f["model_input"]) for f in unit["figures"]})
            rendered += "配图状态：" + "; ".join(
                f"availability={available}, model_input={model_input}" for available, model_input in states)
            rendered += "。URL和图注不是原图；未读取时不得描述图中细节。"
        return rendered
    reserve = len(formatted({**original, "status": "complete", "text_status": "complete", "source_status": "available"})) + 2
    remaining = max(0, limit - reserve)
    locations = {location["block_id"]: location for location in source_locations(item)}
    sources = item.get("context_blocks")
    if sources is None:
        raw = str(item.get("context_source_text", item.get("text")) or "")
        body = raw[:min(1800, remaining)]
        unit = dict(original)
        if len(body) < len(raw):
            unit.update(status="partial", text_status="partial", reason="context_budget")
        size = provenance_size(item, unit, [])
        if size > metadata_limit:
            return "", unit, [], "", 0
        return formatted(unit) + "\n\n" + body, unit, [], body, size
    blocks = [{**b, "source_location": b.get("source_location") or locations[b["block_id"]]} for b in sources]

    def projection(start, stop, reason):
        unit = dict(original)
        if start or stop < len(blocks):
            unit.update(status="partial", text_status="partial", reason=reason)
        if start:
            unit["preceding"] = continuation_anchor(item, blocks[0]["block_id"])
        if stop < len(blocks):
            unit["continuation"] = continuation_anchor(item, blocks[stop]["block_id"])
        # Only resources belonging to the delivered segment or its explicit
        # references consume this page's provenance. Omitted pages retain their
        # images through the versioned preceding/continuation reader.
        if start or stop < len(blocks):
            ids = {b["block_id"] for b in blocks[start:stop]}
            refs = set(_FIGURE_REF.findall("\n".join(b["text"] for b in blocks[start:stop])))
            figures = [f for f in original.get("figures", []) if f.get("figure_id") in ids
                       or set(f.get("references", [])) & refs
                       or any(label in refs for label in _FIGURE_REF.findall(f.get("reference", "")))
                       or ("references" not in f and not _FIGURE_REF.search(f.get("reference", "")))]
            unit.update(figures=figures, figures_scope="visible_blocks_and_references",
                        omitted_figures=len(original.get("figures", [])) - len(figures))
        return unit

    def window(start):
        stop, reason = start, "context_budget"
        while stop < len(blocks):
            unit = projection(start, stop + 1, reason)
            candidate = blocks[start:stop + 1]
            body = "\n\n".join(b["text"] for b in candidate)
            if len(body) > remaining:
                reason = "context_budget"
                break
            if provenance_size(item, unit, candidate) > metadata_limit:
                reason = "provenance_budget"
                break
            stop += 1
        if stop == len(blocks) and start:
            reason = "anchor_window"
        # A partial notice/pointer also consumes bytes. Recheck the final form.
        while stop > start:
            unit = projection(start, stop, reason)
            if provenance_size(item, unit, blocks[start:stop]) <= metadata_limit:
                return stop, unit
            stop -= 1
        return stop, projection(start, stop, reason)

    start = 0
    stop, unit = window(start)
    anchors = item.get("expansion_anchors") or []
    primary = set((anchors[0].get("source_block_ids") or []) if anchors else [])
    indices = [n for n, b in enumerate(blocks) if b["block_id"] in primary]
    # The prefix may be useful background, but must not consume the allocation
    # ahead of the retrieved teaching content. No semantic search is added.
    if stop < len(blocks) and indices and min(indices) > 0:
        focused_start = min(indices)
        focused_stop, focused_unit = window(focused_start)
        if focused_stop > max(indices) and (focused_stop > stop or min(indices) >= stop):
            start, stop, unit = focused_start, focused_stop, focused_unit
    selected = blocks[start:stop]
    body = "\n\n".join(b["text"] for b in selected)
    size = provenance_size(item, unit, selected)
    if not selected or size > metadata_limit:
        return "", unit, [], "", 0
    return formatted(unit) + "\n\n" + body, unit, selected, body, size
