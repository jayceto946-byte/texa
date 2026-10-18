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
        figures.append({"figure_id": block.block_id, "source_block_ids": [block.block_id],
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
                    "index_version": item["index_version"], "canonical_hash": item["canonical_hash"]}
                    if len(blocks) < end - start else None)}
        expanded = {**item, "text": "\n\n".join(p["text"] for p in payloads if p["text"]),
                    "source_block_ids": [p["block_id"] for p in payloads],
                    "source_locations": [p["source_location"] for p in payloads],
                    "context_blocks": payloads, "learning_unit": unit, "expansion_anchors": [item]}
        seen_units[key] = expanded
        result.append(expanded)
    return result


def pack_learning_unit(item: dict, limit: int, *, metadata_limit: int = 8000) -> tuple[str, dict, list[dict], str, int]:
    """Spend a section's allocation on whole blocks, never half a formula.

    The visible notice is budgeted and repeated on the final generation path.
    Internal identities, locations and resource URLs stay in metadata.
    """
    unit = dict(item["learning_unit"])
    blocks = item.get("context_blocks")
    notice = ("教材学习单元：status={status}; text={text_status}; source={source_status}。"
              "complete仅指所存IR结构完整，不证明OCR正确。partial/unknown不得补造前提、证明或原题。"
              "正文不复述内部状态或来源标记，只在缺口影响本题时自然说明限制。")
    if unit.get("figures"):
        states = sorted({(f["availability"], f["model_input"]) for f in unit["figures"]})
        notice += "配图状态：" + "; ".join(
            f"availability={available}, model_input={model_input}" for available, model_input in states)
        notice += "。URL和图注不是原图；未读取时不得描述图中细节。"
    # All status spellings have bounded length; reserve for the longest one.
    reserve = len(notice.format(status="complete", text_status="complete", source_status="available")) + 2
    remaining = max(0, limit - reserve)
    selected = []
    locations = {location["block_id"]: location for location in item.get("source_locations", [])}
    # Runtime checkpoints also have a fixed envelope limit. Account for the
    # block/location metadata, not just visible prose, before selecting a block.
    metadata_used = len(json.dumps(unit, ensure_ascii=False))
    if blocks is not None:
        for source in blocks:
            block = {**source, "source_location": source.get("source_location") or locations[source["block_id"]]}
            cost = len(block["text"]) + (2 if selected else 0)
            metadata_cost = (len(json.dumps({key: value for key, value in block.items()
                if key not in {"text", "source_location", "equations", "section_path"}}, ensure_ascii=False))
                + len(json.dumps(block["source_location"], ensure_ascii=False)))
            if cost > remaining or metadata_used + metadata_cost > metadata_limit:
                unit.update(status="partial", text_status="partial",
                    reason="context_budget" if cost > remaining else "provenance_budget",
                    continuation={"block_id": block["block_id"], "index_version": item["index_version"],
                                  "canonical_hash": item["canonical_hash"]})
                break
            selected.append(block)
            remaining -= cost
            metadata_used += metadata_cost
        body = "\n\n".join(block["text"] for block in selected)
    else:
        raw = str(item.get("context_source_text", item.get("text")) or "")
        body = raw[:min(1800, remaining)]
        if len(body) < len(raw):
            unit.update(status="partial", text_status="partial", reason="context_budget")
    return notice.format(**unit) + "\n\n" + body, unit, selected, body, metadata_used
