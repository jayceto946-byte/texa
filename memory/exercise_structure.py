"""Source-based exercise structure shared by textbook and file imports.

This module never rewrites the reading/RAG IR and never generates solutions.
Learned markers are literal, reviewed examples, not executable adapters.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

CATALOG = re.compile(r'^\s*[#＃]\s*(\d{1,8})(?!\d)\s*')
EXAM = re.compile(r'(?:19|20)\d{2}\s*年?\s*(?:数[一二三123]|数学[一二三123])\s*$')
ORIGINAL = re.compile(r'^\s*(?:[（(](\d+)[）)]|(?:[A-Za-z]\s*)?(\d+(?:[.．\-－—]\d+)+|\d+(?=[.、．)]|\s))(?:[.、．)](?!\d)|\s+|(?=[\u4e00-\u9fff])))\s*')
SECTION = re.compile(r'^\s*(?:第[\d一二三四五六七八九十]+[章节]|[一二三四五六七八九十]+[、．.]|\d+(?:\.\d+)+\s+)')
TOPIC = re.compile(r'^\s*(?P<kind>考点|题型|专题)\s*[\d一二三四五六七八九十]+(?:[、.：:\s]|$)')
LABEL_ROLES = {'答案': 'answer', '参考答案': 'answer', '答': 'answer',
               '解': 'explanation', '解答': 'explanation', '解析': 'explanation',
               '详解': 'explanation', '证明': 'explanation', '证': 'explanation',
               '解法': 'explanation'}
FOCUS = re.compile(r'^\s*(?:考点|知识点|考查内容|题型|方法归纳)[：:]\s*(\S[^\n]*)$')
SOURCE_INFO = re.compile(r'^\s*(?:原稿第\s*\d+\s*页|(?:题目|试题)?来源[：:]|(?:19|20)\d{2}\s*年?\s*(?:数[一二三123]|数学[一二三123]))')
SOURCE_GUIDE = re.compile(r'(?:使用说明|学习计划|刷题计划|考点速查|题号索引|这本书怎么用|每天怎么做|今日复盘|间隔回顾)')


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


def split_roles(block, *, first=False, learned=(), choice_prefix=''):
    text = block['text']
    marks = solution_markers(text, learned)
    # An initial "证明：" on a question is a question instruction.
    if first:
        marks = [m for m in marks if text[:m['start']].strip()]
    if not marks:
        # A final bare choice after all four options is source answer text,
        # not a fifth option. Preserve its exact span rather than deleting it.
        choice_text = choice_prefix + text
        choices = list(re.finditer(r'[（(]([A-D])[）)]', choice_text))
        if (len(choices) == 5 and choices[-1].start() >= len(choice_prefix) and not choice_text[choices[-1].end():].strip()
                and [m[1] for m in choices[:4]] == list('ABCD')
                and choice_text[choices[-2].end():choices[-1].start()].strip(' .。\n')):
            start = choices[-1].start() - len(choice_prefix)
            prefix = [('prefix', dict(block_id=block['block_id'], start=0, end=start))] if start else []
            return [*prefix, ('answer', dict(block_id=block['block_id'], start=start, end=None))], False
        return [], False
    spans = []
    if marks[0]['start']:
        spans.append(('prefix', dict(block_id=block['block_id'], start=0, end=marks[0]['start'])))
    for index, mark in enumerate(marks):
        end = marks[index + 1]['start'] if index + 1 < len(marks) else None
        spans.append((mark['role'], dict(block_id=block['block_id'], start=mark['start'], end=end)))
    return spans, any(m['learned'] for m in marks)


def clean_focus(text):
    """Keep the printed focus apart from page/source/difficulty footer fields."""
    return re.split(r'原稿第\s*\d+\s*页|(?:题目|试题)?来源[：:]|(?:19|20)\d{2}\s*年?\s*(?:数[一二三123]|数学[一二三123])|难度\s*[:：\d]|建议\s*\d', text, maxsplit=1)[0].strip(' \n·•|；;')


def header_metadata(text):
    match = CATALOG.match(text)
    # MinerU can serialize a printed catalogue bar as an equation. Decode the
    # identity for assembly only; keep its original OCR/LaTeX as source evidence.
    equation = None if match else re.match(r'^\s*\\#\s*((?:\d\s*){1,8})(?=\\(?:quad|qquad)|$)', text)
    if equation:
        number = ''.join(equation[1].split())
        tail = re.sub(r'^\\(?:qquad|quad)\s*', '', text[equation.end():]).strip()
    elif match:
        number, tail = match[1], text[match.end():].strip()
    else:
        return None
    exam = EXAM.search(tail)
    return dict(catalog_number='#' + number, authored_focus=clean_focus(tail[:exam.start()] if exam else tail),
                exam_source=exam.group().strip() if exam else '')


def question_metadata(text, path=()):
    """Read explicit exam labels beyond catalog bars; never infer a year from filenames."""
    header = '\n'.join([*path, text[:600]])
    exam = re.search(r'(?:19|20)\d{2}\s*年?\s*(?:考研)?\s*(?:数[一二三123]|数学[一二三123])', header)
    labelled = re.search(r'(?:题目来源|试题来源|出处|来源)[：:]\s*([^\n。]{1,100})', header)
    source = labelled[1].strip() if labelled else (exam.group().strip() if exam else '')
    year = re.search(r'(?:19|20)\d{2}', source)
    kind = re.search(r'(?:单项选择题|多项选择题|选择题|填空题|判断题|证明题|计算题|解答题|简答题|综合题)', header)
    return dict(exam_year=year.group() if year else '', exam_source=source, question_type=kind.group() if kind else '')


def metadata_only(text, quotes=()):
    """Recognize source headers, never infer that arbitrary context is disposable."""
    value = text.strip()
    number = ORIGINAL.match(value)
    if number:
        value = value[number.end():].strip()
    labelled = re.sub(r'^(?:题目来源|试题来源|出处|来源)[：:]\s*', '', value)
    if header_metadata(value) or EXAM.fullmatch(labelled) or FOCUS.fullmatch(value):
        return True
    compact = ''.join(value.split())
    return bool(compact and any(compact == ''.join(quote.split()) for quote in quotes))


def removes_source_content(old, new):
    """Structural removal needs a source role, rather than a destructive edit."""
    old_compact, new_compact = ''.join(old.split()), ''.join(new.split())
    return not metadata_only(new) and any(tag == 'delete' and old_compact[start:end].strip('$\\{}')
        for tag, start, end, _, _ in SequenceMatcher(None, old_compact, new_compact, autojunk=False).get_opcodes())


def header_continuation(active, block):
    if active and active['header_ids'] and block.block_type not in {'formula','table','figure'} and SOURCE_INFO.match(block.text):
        return True
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
    if book.source_metadata.get('outline_recovery'):
        result = {}
        headings = {b.block_id: b for b in book.blocks if b.block_type == 'heading'}
        excluded_titles={b.text for b in book.blocks if b.block_id in excluded_ids}
        for block in book.blocks:
            ancestors, node = [], block
            seen = set()
            if node.block_type == 'heading' and node.block_id not in excluded_ids:
                ancestors.append((node.attributes.get('outline_title', node.text), node.block_id))
            while (parent := node.attributes.get('outline_parent_id')) in headings and parent not in seen:
                seen.add(parent); node = headings[parent]
                if parent not in excluded_ids:
                    ancestors.append((node.attributes.get('outline_title', node.text), parent))
            # Paragraphs retain the canonical path even without a parent ID.
            result[block.block_id] = list(reversed(ancestors)) if ancestors else [(p, '') for p in block.section_path if p not in excluded_titles]
        return result
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
        if block.attributes.get('outline_toc'):
            active = None
            continue
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
    classifications = classification_paths(book, {bid for row in rows for bid in row['header_ids']} |
        {b.block_id for b in book.blocks if b.attributes.get('structure_unit_start') or b.attributes.get('structure_unit_id')})
    if unrestricted:
        from memory.exercise_chapters import chapter_paths
        classifications = chapter_paths(book)
    by_id = {b.block_id: b for b in book.blocks}
    for row in sorted(rows, key=lambda r: order[r['unit_id']]):
        blocks = row.pop('blocks')
        row['header_ids'].extend(b.block_id for b in blocks if FOCUS.match(b.text) and b.block_id not in row['header_ids'])
        path = classifications.get(row['unit_id'], [])
        # Keep the canonical scope for page/chapter selection; the recovered
        # classification is a separate source-backed interpretation.
        row['classification_path'] = [title for title, _ in path if title] or ([] if unrestricted else [p for p in row['section_path'] if not CATALOG.match(p)])
        if row['header_ids']:
            for _, bid in path:
                if allowed_context_ids is not None and bid not in allowed_context_ids:
                    continue
                if not bid:
                    continue
                if bid not in row['header_ids']:
                    row['header_ids'].append(bid)
                if bid not in {b.block_id for b in blocks}:
                    blocks.append(by_id[bid])
        result.append({**row, 'text': '\n\n'.join(b.text for b in blocks if b.text.strip()),
                       'pairing_reviewed': bool(by_id[row['unit_id']].attributes.get('structure_pairing_reviewed')),
                       'chapter': (row['classification_path'][0] if row['classification_path'] else '未分章') if unrestricted else row['section_path'][0], 'page_start': blocks[0].page_start,
                       'page_end': max((b.page_end or b.page_start or 0 for b in blocks), default=0),
                       'source_block_ids': [b.block_id for b in blocks]})
    return result


def _file_units(book, paths):
    rows, active, in_guide = [], None, False
    catalogued=any(header_metadata(b.text) for b in book.blocks)
    from ingestion.document_structure import block_role, has_exercise_scopes
    from ingestion.heading_policy import numeric_data_row
    policy=book.source_metadata.get('exercise_scope_policy')
    scoped = (policy=='regions' if policy else has_exercise_scopes(book)) and book.source_metadata.get('review_source_mode') != 'examples'
    # Source catalogue identities survive role cleanup. Ownership changes are
    # allowed within a question; a normal block classification cannot merge two
    # different printed catalogue entries.
    catalog_scope, anchor = {}, None
    for block in book.blocks:
        catalog = header_metadata(block.text)
        if catalog and not block.attributes.get('structure_duplicate_of'):
            anchor = block.block_id
        elif (block.block_type == 'heading' or SOURCE_GUIDE.search(block.text.strip())
              and len(block.text) < 120 and not re.search(r'\$|=', block.text)):
            anchor = None
        if anchor:
            catalog_scope[block.block_id] = anchor
    aliases = {}
    for block in book.blocks:
        role = block_role(block)
        text=block.text.strip()
        catalog = header_metadata(block.text) if not block.attributes.get('structure_duplicate_of') else None
        if catalog:
            in_guide = False
            active = dict(unit_id=block.block_id, kind='exercise', blocks=[block],
                          section_path=paths.get(block.block_id) or [book.book_name], truncated=False,
                          header_ids=[block.block_id], native_unit=None)
            rows.append(active)
            aliases[block.block_id] = active
            continue
        context_only=block.attributes.get('structure_unit_role')=='context'
        declared_start=bool(block.attributes.get('structure_unit_start')) and not context_only
        owner=block.attributes.get('structure_unit_id')
        assigned=declared_start or bool(owner and not (context_only and owner==block.block_id))
        guide_heading=(block.block_type=='heading' or block.attributes.get('mineru_type')=='paragraph_title'
                       or re.search(r'(?:刷题|学习)计划[：:\s]*$',text) or re.match(r'^(?:今日复盘|间隔回顾)',text))
        if catalogued and not assigned and guide_heading and len(text)<120 and not re.search(r'\$|=',text) and SOURCE_GUIDE.search(text):
            in_guide=True;active=None
        if active and active['header_ids'] and header_continuation(active, block):
            active['blocks'].append(block)
            active['header_ids'].append(block.block_id)
            continue
        # Marginal handwriting can interrupt a printed solution without ending
        # the question. A real heading/non-practice section still closes it.
        if role == 'annotation':
            continue
        if block.attributes.get('outline_toc') and not declared_start or role in {'front_matter', 'toc', 'overview', 'reference'}:
            active = None
            continue
        if (block.attributes.get('structure_unit_id') and block.attributes['structure_unit_id'] != block.block_id
                and block.block_id not in catalog_scope):
            continue
        if scoped and role not in {'exercise', 'solution'} and not assigned:
            active = None
            continue
        labelled_example=bool(re.match(r'^\s*(?:【?例\s*\d|例题)', block.text))
        if catalog or labelled_example or declared_start:in_guide=False
        if in_guide:continue
        is_heading = block.block_type == 'heading' and not catalog and not declared_start
        numbered = bool(ORIGINAL.match(block.text)) and not numeric_data_row(block.text) and block.attributes.get('structure_unit_start') is not False and not context_only
        catalog_active = bool(active and active['header_ids'])
        if (declared_start and catalog_active and catalog_scope.get(block.block_id) == active['unit_id']
                and not any(b.block_id not in active['header_ids'] and not metadata_only(b.text)
                            for b in active['blocks'])):
            # A reviewed stem start gives the catalogue question a body, rather
            # than creating a second, header-only candidate.
            declared_start = False
            aliases[block.block_id] = active
        inherited_unit=block.attributes.get('learning_unit_id') or block.attributes.get('group_id')
        native_start=block.block_type=='example' and (not active or not inherited_unit or inherited_unit!=active.get('native_unit'))
        example=(labelled_example or native_start) and not catalog_active
        if not declared_start and header_continuation(active, block):
            active['blocks'].append(block)
            active['header_ids'].append(block.block_id)
            continue
        if is_heading:
            active = None
            continue
        if declared_start or catalog or (example and not context_only) or (numbered and not catalog_active and not re.match(r'^\s*[（(]', block.text)):
            active = dict(unit_id=block.block_id, kind='example' if example else 'exercise', blocks=[],
                          section_path=paths.get(block.block_id) or [book.book_name], truncated=False,
                          header_ids=[block.block_id] if catalog else [],native_unit=inherited_unit)
            rows.append(active)
            aliases[block.block_id] = active
        if active:
            if len(active['blocks']) >= 80 or (active['blocks'] and (block.page_start or 0) - (active['blocks'][0].page_start or 0) > 8):
                active['truncated'] = True
                active = None
            else:
                active['blocks'].append(block)
    # The model's explicit ownership wins over linear OCR reading order.
    owners = {**{row['unit_id']: row for row in rows}, **aliases}
    for block in book.blocks:
        target = block.attributes.get('structure_unit_id')
        source_catalog = catalog_scope.get(block.block_id)
        target_catalog = catalog_scope.get(target)
        if source_catalog and target_catalog != source_catalog:
            continue
        if header_metadata(block.text):
            continue  # the metadata may point at its stem without moving the boundary
        if target not in owners or block_role(block) in {'reference','annotation','front_matter','toc','overview'}:
            continue
        for row in rows:
            row['blocks'] = [b for b in row['blocks'] if b.block_id != block.block_id]
        owners[target]['blocks'].append(block)
    order = {b.block_id: i for i, b in enumerate(book.blocks)}
    for row in rows:
        row['blocks'].sort(key=lambda b: order[b.block_id])
        row.pop('native_unit',None)
    return [row for row in rows if row['blocks'] and (row['header_ids'] or any(b.attributes.get('structure_unit_role')!='context' for b in row['blocks']))]
