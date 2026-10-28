"""Deterministic source representations and character-range provenance.

Text/formula spans address the original Unicode string. Table spans address a
versioned rendering of the canonical cells plus readable source annotations;
the original table bytes remain in Canonical and are bound by a separate hash.
"""
import hashlib
from html.parser import HTMLParser
import re

SPAN_SCHEMA = 'texa.index-source-spans/v1'
TEXT_REPRESENTATION = 'verbatim/v1'
TABLE_REPRESENTATION = 'canonical-table/v1'


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def table_parts(title, header, rows):
    lines = [str(title).strip()] if str(title or '').strip() else []
    if header:
        lines += ['| ' + ' | '.join(map(str, header)) + ' |', '| ' + ' | '.join('---' for _ in header) + ' |']
    lines += ['| ' + ' | '.join(map(str, row)) + ' |' for row in rows]
    return '\n'.join(lines).strip()


class _ReadableTable(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def table_annotations(block, rendered):
    """Retain captions/footnotes/other readable text not already in the cells.

    This is a deterministic projection, not a claim about OCR correctness.
    Unknown readable source content is retained rather than guessed away.
    """
    raw = block.text
    if re.search(r'<(?:table|tr|td|th)\b', raw, re.I):
        parser = _ReadableTable()
        parser.feed(raw)
        candidates = parser.parts
    else:
        candidates = raw.splitlines()
    compact = re.sub(r'\s+', '', rendered)
    result = []
    for value in candidates:
        value = value.strip()
        key = re.sub(r'\s+', '', value)
        if key and key not in compact:
            result.append(value)
            compact += key
    return '\n'.join(result)


def table_render(block):
    if not block.table_header and not block.table_rows:
        return block.text
    rendered = table_parts(block.retrieval_table_title, block.table_header, block.table_rows)
    notes = table_annotations(block, rendered)
    return '\n'.join(part for part in (rendered, notes) if part)


def source_representation(block):
    if block.block_type == 'table' and (block.table_header or block.table_rows):
        return TABLE_REPRESENTATION, table_render(block)
    return TEXT_REPRESENTATION, block.text


def source_span(block, source_start, source_end, content_start, content_end):
    representation = TABLE_REPRESENTATION if block.block_type == 'table' and (block.table_header or block.table_rows) else TEXT_REPRESENTATION
    return dict(block_id=block.block_id, representation=representation,
                source_sha256=text_hash(block.text), source_start=source_start, source_end=source_end,
                content_start=content_start, content_end=content_end)


def uncovered_ranges(length, ranges):
    cursor = 0
    gaps = []
    for start, end in sorted(ranges):
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < length:
        gaps.append((cursor, length))
    return gaps
