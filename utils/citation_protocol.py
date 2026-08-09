"""Normalize and validate the internal EvidencePack citation protocol."""
from __future__ import annotations

import re
from typing import Any


_CITATION_GROUP_RE = re.compile(
    r"[\[［]{2}\s*cite\s*:\s*E[\w-]+\s*[\]］]"
    r"(?:\s*[\[［]\s*cite\s*:\s*E[\w-]+\s*[\]］])*"
    r"\s*[\]］]",
    re.IGNORECASE,
)
_CITATION_ID_RE = re.compile(r"cite\s*:\s*(E[\w-]+)", re.IGNORECASE)


def sanitize_citation_protocol(text: str, sources: list[dict[str, Any]] | None) -> tuple[str, dict[str, int]]:
    """Canonicalize citation brackets and drop IDs absent from this turn.

    The model occasionally emits mixed full-width tokens such as
    ``［[cite:E7]］``.  Evidence IDs are scoped to one answer, so validation is
    deliberately performed against that answer's structured sources.
    """
    valid_ids = {
        str(item.get("id") or "").strip().upper()
        for item in (sources or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    normalized_count = 0
    invalid_count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal normalized_count, invalid_count
        token = match.group(0)
        ids = [value.upper() for value in _CITATION_ID_RE.findall(token)]
        canonical: list[str] = []
        for evidence_id in ids:
            if evidence_id not in valid_ids:
                invalid_count += 1
                continue
            canonical.append(f"[[cite:{evidence_id}]]")
        replacement = "".join(canonical)
        if replacement != token:
            normalized_count += 1
        return replacement

    cleaned = _CITATION_GROUP_RE.sub(replace, str(text or ""))
    return cleaned, {
        "normalized_tokens": normalized_count,
        "invalid_ids_removed": invalid_count,
        "valid_source_count": len(valid_ids),
    }
