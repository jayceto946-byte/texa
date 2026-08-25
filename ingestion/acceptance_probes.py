"""Deterministic structural acceptance probes derived from Canonical Document IR.

Generated probes are release checks for ingestion/retrieval preservation. They
are not human goldens and must not be used to claim OCR or textbook truth.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from typing import Any

from ingestion.document_ir import CanonicalBook, DocumentBlock, canonical_paths


PROBE_SCHEMA_VERSION = 1
SPECIALTIES = ("formula", "list", "example", "table")
GENERATED_PROBES_FILENAME = "acceptance_probes.generated.jsonl"
GENERATED_PROBES_REPORT_FILENAME = "acceptance_probes.generated.report.json"
DEFAULT_MAX_PROBES_PER_TYPE = 8


def generate_acceptance_probes(
    book: CanonicalBook,
    *,
    max_per_type: int = DEFAULT_MAX_PROBES_PER_TYPE,
) -> dict[str, Any]:
    """Generate bounded, deterministic probes and a source-unit inventory."""
    limit = max(1, int(max_per_type))
    candidates: dict[str, list[dict]] = {name: [] for name in SPECIALTIES}
    inventory = {name: 0 for name in SPECIALTIES}
    seen: set[tuple[str, str, tuple[str, ...]]] = set()

    for block in book.blocks:
        for specialty, question, points in _block_probes(block):
            usable_points = _unique([point for point in points if _usable_anchor(point, block.text)])
            if not question or not usable_points:
                continue
            key = (specialty, question, tuple(usable_points))
            if key in seen:
                continue
            seen.add(key)
            inventory[specialty] += 1
            case_id = _probe_id(book.book_name, block.block_id, specialty, question, usable_points)
            candidates[specialty].append({
                "schema_version": PROBE_SCHEMA_VERSION,
                "id": case_id,
                "status": "generated_structural",
                "book_name": book.book_name,
                "question": question,
                "intent": _intent(specialty),
                "required_points": usable_points[:3 if specialty == "list" else 6],
                "answerable": True,
                "target_chapters": list(block.section_path[:1]),
                "specialty": specialty,
                "tags": ["generated_probe", "structural_gate", specialty],
                "provenance": {
                    "source": "canonical_document_ir",
                    "block_id": block.block_id,
                    "block_type": block.block_type,
                    "section_path": list(block.section_path),
                    "page_start": block.page_start,
                    "page_end": block.page_end,
                    "review_status": block.review_status,
                    "human_approved": False,
                },
            })

    # OCR/Markdown chapters often place each numbered item and its explanation
    # in separate paragraphs. Reassemble the item labels by section so list
    # coverage does not depend on parser paragraph boundaries.
    by_section: dict[tuple[str, ...], list[DocumentBlock]] = {}
    for block in book.blocks:
        if block.block_type == "paragraph" and str(block.text or "").strip():
            by_section.setdefault(tuple(block.section_path), []).append(block)
    for section_path, blocks in by_section.items():
        combined_text = "\n".join(str(block.text or "") for block in blocks)
        if not _has_list_context(combined_text) or any(
            marker in (section_path[-1] if section_path else "") for marker in ("习题", "练习题", "例题")
        ):
            continue
        points = _unique([
            anchor for block in blocks
            if (anchor := _numbered_item_anchor(str(block.text or "")))
        ])
        if len(points) < 2:
            continue
        section_label = section_path[-1] if section_path else "本节"
        question = f"{section_label} {' '.join(points[:2])}"[:160]
        key = ("list", question, tuple(points[:6]))
        if key in seen:
            continue
        seen.add(key)
        inventory["list"] += 1
        first = blocks[0]
        block_ids = [block.block_id for block in blocks if _numbered_item_anchor(str(block.text or ""))]
        candidates["list"].append({
            "schema_version": PROBE_SCHEMA_VERSION,
            "id": _probe_id(book.book_name, "|".join(block_ids), "list", question, points[:6]),
            "status": "generated_structural",
            "book_name": book.book_name,
            "question": question,
            "intent": "factual_recall",
            "required_points": points[:3],
            "answerable": True,
            "target_chapters": list(section_path[:1]),
            "specialty": "list",
            "tags": ["generated_probe", "structural_gate", "list"],
            "provenance": {
                "source": "canonical_document_ir",
                "block_id": first.block_id,
                "source_block_ids": block_ids,
                "block_type": "paragraph_group",
                "section_path": list(section_path),
                "page_start": min((block.page_start for block in blocks if block.page_start is not None), default=None),
                "page_end": max((block.page_end for block in blocks if block.page_end is not None), default=None),
                "review_status": "",
                "human_approved": False,
            },
        })

    cases = [
        case
        for specialty in SPECIALTIES
        for case in _spread(candidates[specialty], limit)
    ]
    return {
        "schema_version": PROBE_SCHEMA_VERSION,
        "book_name": book.book_name,
        "generator": "canonical-ir-structural-v1",
        "cases": cases,
        "inventory": inventory,
        "generated": {
            specialty: sum(case["specialty"] == specialty for case in cases)
            for specialty in SPECIALTIES
        },
        "limitations": [
            "Generated probes verify structural retrieval preservation, not OCR correctness.",
            "Generated probes are not human-approved semantic goldens.",
        ],
    }


def persist_acceptance_probes(
    book: CanonicalBook,
    *,
    progress_root: str | Path,
    max_per_type: int = DEFAULT_MAX_PROBES_PER_TYPE,
) -> dict[str, Any]:
    result = generate_acceptance_probes(book, max_per_type=max_per_type)
    directory = canonical_paths(book.book_name, progress_root=progress_root)[0].parent
    directory.mkdir(parents=True, exist_ok=True)
    cases_path = directory / GENERATED_PROBES_FILENAME
    report_path = directory / GENERATED_PROBES_REPORT_FILENAME
    _atomic_write(
        cases_path,
        "".join(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n" for case in result["cases"]),
    )
    _atomic_write(
        report_path,
        json.dumps({key: value for key, value in result.items() if key != "cases"}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return {**result, "cases_path": str(cases_path), "report_path": str(report_path)}


def _block_probes(block: DocumentBlock):
    text = str(block.text or "").strip()
    if not text:
        return
    section = _section_label(block)

    formulas = _formula_anchors(block, text)
    if formulas:
        # Structural probes deliberately include a bounded source fragment.
        # Their job is to catch loss across parsing/indexing/EvidencePack, not
        # to act as automatically generated semantic examination questions.
        yield "formula", formulas[0][:120], formulas[:3]

    list_items = _list_items(text)
    if len(list_items) >= 2 and _has_list_context(text):
        yield "list", f"{section} {' '.join(list_items[:2])}"[:160], list_items[:3]

    if block.block_type == "example" or re.match(r"^(?:例题|例\s*\d+|示例)", text):
        label = _first_match(r"(?:例题\s*[\d.-]*|例\s*\d+(?:[.-]\d+)*|示例\s*\d*)", text)
        anchors = _example_anchors(text, label)
        # Use the source stem itself: generic wording such as “解题要点” can
        # be rejected by the production literal-support gate before the
        # structurally correct example reaches EvidencePack.
        query = " ".join(anchors[:2]).strip() or label or section
        yield "example", query[:160], anchors

    table = _table_anchors(block, text)
    if table:
        title = block.table_title.strip() or section
        yield "table", f"{title}中列出了哪些字段或数据？", table


def _formula_anchors(block: DocumentBlock, text: str) -> list[str]:
    display = [match.strip() for match in re.findall(r"\$\$(.*?)\$\$", text, flags=re.DOTALL) if match.strip()]
    bracketed = [match.strip() for match in re.findall(r"\\\[(.*?)\\\]", text, flags=re.DOTALL) if match.strip()]
    candidates = display + bracketed + [str(item).strip().strip("$") for item in block.equations]
    anchors = []
    for candidate in candidates:
        anchor = _source_anchor(text, candidate)
        if anchor and anchor not in anchors:
            anchors.append(anchor)
    if block.block_type == "formula" and not anchors:
        fallback = _source_anchor(text, text.strip("$\n "))
        if fallback:
            anchors.append(fallback)
    return anchors


def _formula_symbol(formula: str) -> str:
    left = formula.split("=", 1)[0]
    tokens = re.findall(r"\\[A-Za-z]+|[A-Za-z][A-Za-z0-9_]*|[\u4e00-\u9fff]{2,8}", left)
    return " ".join(tokens[:2])[:24]


def _list_items(text: str) -> list[str]:
    items = []
    for line in text.splitlines():
        match = re.match(
            r"^\s*(?:[-*•]|[（(]?\d+\s*[）).、]|[（(]?[一二三四五六七八九十]+[）)、.])\s*(.+?)\s*$",
            line,
        )
        if match:
            anchor = _source_anchor(text, match.group(1))
            if anchor:
                items.append(anchor)
    if len(items) >= 2:
        return _unique(items)
    compact = re.sub(r"\s+", " ", text)
    match = re.search(r"(?:包括|分为|分别为|有以下)(.{4,180}?)(?:[。；;]|$)", compact)
    if match:
        parts = [part.strip(" ：:,，、;；") for part in re.split(r"[、，,；;]", match.group(1))]
        items.extend(_source_anchor(text, part) for part in parts if len(part.strip()) >= 2)
    return _unique([item for item in items if item and _semantic_list_item(item)])


def _numbered_item_anchor(text: str) -> str:
    first_line = next((line.strip() for line in str(text or "").splitlines() if line.strip()), "")
    match = re.match(
        r"^(?:[-*•]|[（(]?\d+\s*[）).、]|[（(]?[一二三四五六七八九十]+[）)、.])\s*(.+?)\s*$",
        first_line,
    )
    anchor = match.group(1).strip()[:96] if match and len(match.group(1).strip()) >= 2 else ""
    return anchor if _semantic_list_item(anchor) else ""


def _has_list_context(text: str) -> bool:
    compact = re.sub(r"\s+", "", str(text or ""))
    return bool(re.search(r"(?:包括|分为|分别为|主要有|有以下|如下(?:几|各)?(?:项|点|种|类|方面|步骤)|(?:几|多)个(?:方面|步骤|特点))", compact))


def _semantic_list_item(value: str) -> bool:
    text = str(value or "").strip()
    if not 2 <= len(text) <= 48 or len(re.findall(r"[\u4e00-\u9fff]", text)) < 2:
        return False
    if "$" in text or "\\" in text:
        return False
    if any(marker in text for marker in ("试求", "求解", "计算下列", "证明下列", "测出距离")):
        return False
    return True


def _example_anchors(text: str, label: str) -> list[str]:
    anchors = []
    if label:
        anchors.append(label)
    stem = re.split(r"(?:\n|解\s*[：:]|答案\s*[：:]|证明\s*[：:])", text, maxsplit=1)[0]
    stem = re.sub(r"^(?:例题|例\s*\d+(?:[.-]\d+)*|示例)\s*[\d.-]*\s*", "", stem).strip(" ：:")
    if stem:
        anchors.append(_source_anchor(text, stem))
    solution = re.search(r"(?:解|答案|证明)\s*[：:]\s*(.{4,100})", text, flags=re.DOTALL)
    if solution:
        anchors.append(_source_anchor(text, solution.group(1)))
    return _unique([anchor for anchor in anchors if anchor])


def _table_anchors(block: DocumentBlock, text: str) -> list[str]:
    structured = [block.table_title, *block.table_header]
    if block.table_rows:
        structured.extend(block.table_rows[0])
    anchors = [_source_anchor(text, str(value)) for value in structured if str(value).strip()]
    if len([item for item in anchors if item]) >= 2:
        return _unique([item for item in anchors if item])[:6]
    lines = [line.strip() for line in text.splitlines() if "|" in line]
    if len(lines) >= 2 and re.search(r"\|?\s*:?-{3,}", lines[1]):
        cells = []
        for line in (lines[0], *lines[2:3]):
            cells.extend(cell.strip() for cell in line.strip("|").split("|") if cell.strip())
        return _unique([_source_anchor(text, cell) for cell in cells if _source_anchor(text, cell)])[:6]
    return []


def _source_anchor(source: str, value: str, *, limit: int = 96) -> str:
    candidate = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(candidate) < 2:
        return ""
    if candidate in source:
        return candidate[:limit]
    raw = str(value or "").strip()
    if raw in source:
        return raw[:limit]
    for part in sorted(re.findall(r"[\u4e00-\u9fffA-Za-z0-9_\\{}^+-]{3,}", raw), key=len, reverse=True):
        if part in source:
            return part[:limit]
    return ""


def _usable_anchor(anchor: str, source: str) -> bool:
    return bool(anchor and len(anchor.strip()) >= 2 and anchor in source)


def _section_label(block: DocumentBlock) -> str:
    parts = [str(item).strip() for item in block.section_path if str(item).strip()]
    return parts[-1] if parts else "本节"


def _first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    return match.group(0).strip() if match else ""


def _intent(specialty: str) -> str:
    return {"formula": "formula", "list": "factual_recall", "example": "application", "table": "factual_recall"}[specialty]


def _probe_id(book_name: str, block_id: str, specialty: str, question: str, points: list[str]) -> str:
    digest = hashlib.sha1(
        "\0".join([book_name, block_id, specialty, question, *points]).encode("utf-8")
    ).hexdigest()[:16]
    return f"auto_{specialty}_{digest}"


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in result:
            result.append(item)
    return result


def _spread(cases: list[dict], limit: int) -> list[dict]:
    if len(cases) <= limit:
        return cases
    if limit == 1:
        return cases[:1]
    indexes = {round(offset * (len(cases) - 1) / (limit - 1)) for offset in range(limit)}
    return [cases[index] for index in sorted(indexes)]


def _atomic_write(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
