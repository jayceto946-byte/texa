"""Source-based exercise structure shared by textbook and file imports.

This module never rewrites the reading/RAG IR and never generates solutions.
Learned markers are literal, reviewed examples, not executable adapters.
"""
from __future__ import annotations

import re

CATALOG = re.compile(r'^\s*[#＃]\s*(\d{1,8})(?!\d)\s*')
EXAM = re.compile(r'(?:19|20)\d{2}\s*年?\s*(?:数[一二三123]|数学[一二三123])\s*$')
ORIGINAL = re.compile(r'^\s*(?:[（(](\d+)[）)]|(\d+)[.、．)])\s*')
SECTION = re.compile(r'^\s*(?:第[\d一二三四五六七八九十]+[章节]|[一二三四五六七八九十]+[、．.]|\d+(?:\.\d+)+\s+)')
TOPIC = re.compile(r'^\s*(?P<kind>考点|题型|专题)\s*[\d一二三四五六七八九十]+(?:[、.：:\s]|$)')
LABEL_ROLES = {'答案': 'answer', '参考答案': 'answer', '答': 'answer',
               '解': 'explanation', '解答': 'explanation', '解析': 'explanation',
               '详解': 'explanation', '证明': 'explanation', '证': 'explanation',
               '解法': 'explanation'}
FOCUS = re.compile(r'^\s*(?:考点|知识点|考查内容|题型|方法归纳)[：:]\s*(\S[^\n]*)$')


def solution_markers(text, learned=()):
    """Find explicit labels; a request to prove/solve is not a solution label.

    A single-word label needs a colon, a bracket pair, or its own line.
    Unknown/unlabelled prose stays unassigned rather than guessed as a solution.
    """
    labels = {**LABEL_ROLES, **{r['label']: r['role'] for r in learned}}
    names = '|'.join(re.escape(s) for s in sorted(labels, key=len, reverse=True))
    pattern = re.compile(r'(?:^|(?<=[\n。；;]))[ \t]*(?:'
                         r'[【\[]\s*(?P<bracket>' + names + r')\s*[】\]][：:]?'
                         r'|(?P<colon>' + names + r')[ \t]*[：:]'
                         r'|(?P<line>' + names + r')[ \t]*(?=\n))')
    matches = []
    for match in pattern.finditer(text):
        label = next(v for v in match.groupdict().values() if v is not None)
        matches.append(dict(start=match.start(), end=match.end(), role=labels[label],
                            label=label, learned=label not in LABEL_ROLES))
    return matches


def split_roles(block, *, first=False, learned=()):
    text = block['text']
    marks = solution_markers(text, learned)
    # An initial "证明：" on a question is a question instruction.
    if first:
        marks = [m for m in marks if text[:m['start']].strip()]
    if not marks:
        return [], False
    spans = []
    if marks[0]['start']:
        spans.append(('prefix', dict(block_id=block['block_id'], start=0, end=marks[0]['start'])))
    for index, mark in enumerate(marks):
        end = marks[index + 1]['start'] if index + 1 < len(marks) else None
        spans.append((mark['role'], dict(block_id=block['block_id'], start=mark['start'], end=end)))
    return spans, any(m['learned'] for m in marks)


def header_metadata(text):
    match = CATALOG.match(text)
    if not match:
        return None
    tail = text[match.end():].strip()
    exam = EXAM.search(tail)
    return dict(catalog_number='#' + match[1], authored_focus=tail[:exam.start()].strip() if exam else tail,
                exam_source=exam.group().strip() if exam else '')


def header_continuation(active, block):
    if (not active or not active['header_ids'] or len(active['blocks']) > 3
            or any(b.block_id not in active['header_ids'] for b in active['blocks'])
            or block.block_type in ('formula', 'table', 'figure')):
        return False
    text = block.text.strip()
    if not text or len(text) > 120 or ORIGINAL.match(text) or solution_markers(text):
        return False
    if EXAM.fullmatch(text) or '→' in text or re.match(r'^(?:考点|题型)[：:]', text):
        return True
    header = active['blocks'][0]
    a, b = header.bbox, block.bbox
    # Line projections retain their parent's coarse box; it is not a line box.
    if (a and b and len(a) == len(b) == 4 and header.page_start == block.page_start
            and (not header.attributes.get('source_parent_id') or header.attributes.get('source_parent_id') != block.attributes.get('source_parent_id'))
            and min(a[3], b[3]) - max(a[1], b[1]) > 0.5 * min(a[3] - a[1], b[3] - b[1])):
        return True
    return False


def topic_level(text, ancestors):
    """Repeated labels of the same role are peers, not ever-deeper headings."""
    kind = TOPIC.match(text)['kind']
    return next((i + 1 for i, title in enumerate(ancestors) if (m := TOPIC.match(title)) and m['kind'] == kind), len(ancestors) + 1)


def classification_paths(book, excluded_ids=()):
    """Candidate-only heading interpretation, with the source nodes retained."""
    current, result = [], {}
    for block in book.blocks:
        text = block.text.strip()
        title = (block.block_type == 'heading' or block.attributes.get('mineru_type') == 'paragraph_title'
                 or bool(SECTION.match(text)) or bool(TOPIC.match(text)))
        if (title and block.block_id not in excluded_ids and not CATALOG.match(text) and len(text) <= 120
                and not re.match(r'^\s*(?:【?例|例题|[（(]\d+[）)])', text)
                and not (ORIGINAL.match(text) and not SECTION.match(text))
                and not solution_markers(text) and not re.search(r'[=。？?]', text)):
            raw_level = block.attributes.get('raw_level')
            numbered = re.match(r'^(\d+(?:\.\d+)+)', text)
            level = len(numbered[1].split('.')) if numbered else (topic_level(text, [title for title, _ in current]) if TOPIC.match(text) else (raw_level if type(raw_level) is int and 1 <= raw_level <= 8 else 1))
            current = current[:level - 1] + [(text, block.block_id)]
        result[block.block_id] = list(current)
    return result


def exercise_units(book, *, unrestricted=False, allowed_context_ids=None):
    """Reuse normal learning units; catalog bars form additional source units.

    Catalog IDs take precedence over original exam numbering until the next bar
    or section. The raw book, headings and global learning_units stay unchanged.
    """
    from ingestion.document_workflows import learning_units
    from ingestion.document_ir import canonical_retrieval_paths
    paths = canonical_retrieval_paths(book.blocks)
    normal = learning_units(book) if not unrestricted else []
    rows = []
    occupied = set()
    active = None
    for block in ([] if unrestricted else book.blocks):
        catalog = header_metadata(block.text)
        if catalog:
            active = dict(unit_id=block.block_id, kind='exercise', blocks=[block],
                          section_path=paths.get(block.block_id) or [book.book_name], truncated=False,
                          header_ids=[block.block_id])
            rows.append(active)
            occupied.add(block.block_id)
            continue
        if active:
            if header_continuation(active, block):
                active['blocks'].append(block)
                active['header_ids'].append(block.block_id)
                occupied.add(block.block_id)
                continue
            # Some OCR exports assign every catalog bar a heading path. Its child
            # paragraphs still belong to that entry; a real new heading ends it.
            if block.block_type == 'heading':
                active = None
            elif len(active['blocks']) >= 80 or ((block.page_start or 0) - (active['blocks'][0].page_start or 0)) > 8:
                active['truncated'] = True
                active = None
            else:
                active['blocks'].append(block)
                occupied.add(block.block_id)
                continue
    # In unrestricted files, build numbered units independently of catalog runs.
    if unrestricted:
        rows = _file_units(book, paths)
    else:
        for unit in normal:
            if not any(b.block_id in occupied for b in unit.blocks):
                rows.append(dict(unit_id=unit.unit_id, kind=unit.kind, blocks=unit.blocks,
                                 section_path=unit.section_path, truncated=unit.truncated, header_ids=[]))
    order = {b.block_id: i for i, b in enumerate(book.blocks)}
    result = []
    classifications = classification_paths(book, {bid for row in rows for bid in row['header_ids']})
    by_id = {b.block_id: b for b in book.blocks}
    for row in sorted(rows, key=lambda r: order[r['unit_id']]):
        blocks = row.pop('blocks')
        row['header_ids'].extend(b.block_id for b in blocks if FOCUS.match(b.text) and b.block_id not in row['header_ids'])
        path = classifications.get(row['unit_id'], [])
        # Keep the canonical scope for page/chapter selection; the recovered
        # classification is a separate source-backed interpretation.
        row['classification_path'] = [title for title, _ in path] or [p for p in row['section_path'] if not CATALOG.match(p)]
        if row['header_ids']:
            for _, bid in path:
                if allowed_context_ids is not None and bid not in allowed_context_ids:
                    continue
                if bid not in row['header_ids']:
                    row['header_ids'].append(bid)
                if bid not in {b.block_id for b in blocks}:
                    blocks.append(by_id[bid])
        result.append({**row, 'text': '\n\n'.join(b.text for b in blocks if b.text.strip()),
                       'chapter': row['section_path'][0], 'page_start': blocks[0].page_start,
                       'page_end': max((b.page_end or b.page_start or 0 for b in blocks), default=0),
                       'source_block_ids': [b.block_id for b in blocks]})
    return result


def _file_units(book, paths):
    rows, active = [], None
    for block in book.blocks:
        catalog = header_metadata(block.text)
        is_heading = block.block_type == 'heading' and not catalog
        numbered = bool(ORIGINAL.match(block.text))
        example = bool(re.match(r'^\s*(?:【?例\s*\d|例题)', block.text))
        catalog_active = bool(active and active['header_ids'])
        if header_continuation(active, block):
            active['blocks'].append(block)
            active['header_ids'].append(block.block_id)
            continue
        if is_heading:
            active = None
            continue
        if catalog or example or (numbered and not catalog_active and not re.match(r'^\s*[（(]', block.text)):
            active = dict(unit_id=block.block_id, kind='example' if example else 'exercise', blocks=[],
                          section_path=paths.get(block.block_id) or [book.book_name], truncated=False,
                          header_ids=[block.block_id] if catalog else [])
            rows.append(active)
        if active:
            if len(active['blocks']) >= 80 or (active['blocks'] and (block.page_start or 0) - (active['blocks'][0].page_start or 0) > 8):
                active['truncated'] = True
                active = None
            else:
                active['blocks'].append(block)
    return rows
