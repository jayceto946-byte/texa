"""MinerU 4 structured_content -> source-neutral Canonical IR, without a bridge."""
from __future__ import annotations

from collections import Counter
from pathlib import Path, PurePosixPath
import re
from typing import Any

from ingestion.document_ir import CanonicalBook, canonical_chapter_title

ADAPTER_VERSION = 'mineru-structured-content-v1'
_EXCLUDED = {'header', 'footer', 'page_number', 'index', 'doc_title'}
_KNOWN = {'text', 'paragraph_title', 'equation', 'table', 'image', 'chart', 'ref_text', *_EXCLUDED}
_SECTION = re.compile(r'^(\d+(?:\s*\.\s*\d+){1,5})(?:\s+|(?=[^\d.]))(.+)$')
_ENUMERATION = re.compile(r'^(?:\d+\s*[.．、](?!\d)|[（(]\s*\d+\s*[）)])')


def validate_structured(payload: Any) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get('pages'), list):
        raise ValueError('MinerU structured_content requires a pages array')
    metadata = payload.get('metadata')
    producer = metadata.get('producer') if isinstance(metadata, dict) else None
    if not isinstance(producer, dict) or str(producer.get('name', '')).lower() != 'mineru':
        raise ValueError('structured_content producer must identify MinerU')
    if not re.fullmatch(r'4\.\d+(?:\.\d+)?(?:[-+].*)?', str(producer.get('version', ''))):
        raise ValueError(f"unsupported MinerU structured producer version: {producer.get('version')}")
    page_count = (metadata.get('document') or {}).get('page_count')
    if page_count is not None and (type(page_count) is not int or page_count < 1):
        raise ValueError('structured_content physical page_count must be a positive integer')
    seen = set()
    previous = -1
    for page in payload['pages']:
        if not isinstance(page, dict) or not isinstance(page.get('blocks'), list):
            raise ValueError('structured_content page requires blocks array')
        index = page.get('page_idx')
        if type(index) is not int or index < 0 or index in seen or index <= previous:
            raise ValueError('structured_content page_idx must be unique, ordered, non-negative integers')
        seen.add(index)
        previous = index
        for block in page['blocks']:
            if not isinstance(block, dict) or not isinstance(block.get('type'), str):
                raise ValueError(f'structured_content malformed block on physical page {index + 1}')
            if 'content' in block and not isinstance(block['content'], (str, list, dict)):
                raise ValueError(f'structured_content unreadable content on physical page {index + 1}')


def from_structured_content(payload: dict, *, book_name: str, source_file: str = 'structured_content.json',
                            source_root: Path | None = None, source_base: Path | None = None) -> CanonicalBook:
    from ingestion.document_adapters import (
        _BlockBuilder, _bbox, _float_or_none, _nested_text,
        _table_parts, _append_mineru_item,
    )
    validate_structured(payload)
    builder = _BlockBuilder(book_name, source_kind='mineru', source_file=source_file)
    excluded = Counter()
    counts = Counter()
    warnings = []
    numbered_path: list[str] = []
    chapter_seen = False
    document_titles = []
    for source_page_index, page in enumerate(payload['pages']):
        page_idx = page['page_idx']
        for source_block_index, raw in enumerate(page['blocks']):
            typ = raw['type']
            counts[typ] += 1
            text = _nested_text(raw.get('content'))
            if typ in _EXCLUDED:
                excluded[typ] += 1
                if typ == 'doc_title':
                    document_titles.append(dict(text=text, page_idx=page_idx, source_block_index=source_block_index))
                continue
            attrs = dict(
                mineru_type=typ, raw_level=raw.get('level'), source_page_index=source_page_index,
                source_page_idx=page_idx, source_block_index=source_block_index,
                producer=payload['metadata']['producer'], adapter_version=ADAPTER_VERSION,
                bbox_space='page', bbox_format='xyxy', bbox_units='normalized',
            )
            if 'page_number' in page:
                attrs['printed_page_number'] = page['page_number']
            bbox = _bbox(raw.get('bbox'))
            confidence = _float_or_none(raw.get('confidence'))
            chapter = canonical_chapter_title(text) if typ == 'paragraph_title' else ''
            section = _SECTION.match(text) if typ == 'paragraph_title' else None
            if chapter:
                chapter_seen = True
                builder.path = []
                builder.heading(text, level=1, page_start=page_idx+1, page_end=page_idx+1,
                                bbox=bbox, confidence=confidence, attributes={**attrs, 'heading_rule': 'numbered_chapter'})
                numbered_path = list(builder.path)
                continue
            if section:
                level = min(section.group(1).count('.') + 1, 6)
                builder.path = list(numbered_path)
                builder.heading(text, level=level, page_start=page_idx+1, page_end=page_idx+1,
                                bbox=bbox, confidence=confidence, attributes={**attrs, 'heading_rule': 'numbered_section'})
                numbered_path = list(builder.path)
                continue
            bounded_title = (2 <= len(text.strip()) <= 24 and not re.search(r'[。！？:：$\\]|\d\s*\.\s*\d', text))
            if typ == 'paragraph_title' and chapter_seen and bounded_title and not _ENUMERATION.match(text):
                # Unnumbered titles are peers under the last numbered scope, never
                # a succession of deeper headings inferred from raw level=2.
                builder.path = list(numbered_path)
                level = min(len(numbered_path)+1, 4) if chapter_seen else 1
                if text.strip() in {'习题', '练习', '参考文献'} and chapter_seen:
                    builder.path = numbered_path[:1]
                    level = 2
                builder.heading(text, level=level, page_start=page_idx+1, page_end=page_idx+1,
                                bbox=bbox, confidence=confidence, attributes={**attrs, 'heading_rule': 'bounded_unnumbered'})
                continue
            captions = [_nested_text(v) for v in raw.get('captions', [])]
            footnotes = [_nested_text(v) for v in raw.get('footnotes', [])]
            image_source = raw.get('image_source', '')
            if isinstance(image_source, dict):
                image_source = image_source.get('path') or image_source.get('image_path') or ''
            source_relpath = _native_asset_path(str(image_source), source_root, source_base)
            attrs.update(captions=captions, footnotes=footnotes)
            if typ in {'image', 'chart'}:
                _append_mineru_item(builder, dict(type='image', image_caption=captions, image_footnote=footnotes,
                    img_path=image_source, page_idx=page_idx, bbox=bbox, confidence=confidence),
                    source_index=source_block_index, source_root=source_root, source_base=source_base)
                builder.blocks[-1].attributes.update(attrs)
                builder.blocks[-1].attributes['source_asset_relpath'] = source_relpath
                builder.blocks[-1].ocr_confidence = confidence
                continue
            block_type = {'equation': 'formula', 'table': 'table'}.get(typ, 'paragraph')
            equations = []
            table_header, table_rows = [], []
            table_title = '\n'.join(captions)
            if typ == 'equation':
                # Equivalent aliases are alternatives, never concatenated bodies.
                text = str(raw.get('latex') or text or raw.get('text') or '').strip()
                equations = [text] if text else []
            if typ == 'table':
                attrs['source_markdown'] = text
                _, table_header, table_rows = _table_parts(dict(table_body=text))
                text = '\n'.join(v for v in [table_title, text, *footnotes] if v)
            if typ == 'ref_text':
                attrs['semantic_role'] = 'reference'
            if typ not in _KNOWN:
                warnings.append(f'Unknown readable structured block: {typ} at page_idx={page_idx}, block={source_block_index}')
            block = builder.add(block_type, text, page_start=page_idx+1, page_end=page_idx+1,
                                bbox=bbox, confidence=confidence, equations=equations,
                                table_title=table_title if typ == 'table' else '',
                                table_header=table_header, table_rows=table_rows, attributes=attrs)
            if typ in {'equation', 'table'}:
                block.attributes['original_visual_asset'] = dict(
                    schema='texa.original-visual-asset', version=1, role='original_crop',
                    source_relpath=source_relpath, asset_relpath='', status='pending' if source_relpath else 'missing',
                    sha256='', image_format='', width=0, height=0, block_id=block.block_id,
                    page_start=block.page_start, bbox=block.bbox or [],
                    bbox_space='page', bbox_format='xyxy', bbox_units='normalized',
                )
    metadata = payload['metadata']
    source_count = (metadata.get('document') or {}).get('page_count')
    max_page = max((pg['page_idx']+1 for pg in payload['pages']), default=0)
    book = builder.book(parser_version=ADAPTER_VERSION, source_page_count=max(max_page, source_count or 0) or None,
                        warnings=warnings)
    book.source_metadata = dict(producer=metadata['producer'], adapter_version=ADAPTER_VERSION,
                                input_format='structured_content', input_counts=dict(counts),
                                excluded_counts=dict(excluded), document_titles=document_titles,
                                heading_policy='numbered-first; local enumeration remains paragraph; unnumbered bounded to numbered parent')
    return book


def _native_asset_path(value: str, root: Path | None, base: Path | None) -> str:
    raw = value.replace('\\', '/')
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or '..' in path.parts or ':' in raw:
        return ''
    if root is None:
        return path.as_posix()
    try:
        candidate = ((base or root) / raw).resolve()
        return candidate.relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return ''
