"""Shared textbook outline recovery from source text, TOC anchors and examples.

No model calls or book-specific rules. Source IDs/text stay unchanged; only
derived heading roles/paths change. A user example teaches a numbering family
or an observed layout style, rather than requiring an entry for every chapter.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from statistics import median
import re
import unicodedata

from ingestion.heading_policy import body_title, exercise_heading

POLICY_VERSION = 1
_CN = r'[零〇一二三四五六七八九十百千\d]+'
_NUMBERING = [
    ('part', rf'^第\s*{_CN}\s*[篇部]\s*\S', 1),
    ('chapter', rf'^第\s*{_CN}\s*章\s*\S', 1),
    ('section', rf'^第\s*{_CN}\s*节\s*\S', 2),
    ('part-en', r'^part\s+(?:\d+|[ivxlcdm]+)\b\s*[:.\-]?\s*\S', 1),
    ('chapter-en', r'^chapter\s+(?:\d+|[ivxlcdm]+)\b\s*[:.\-]?\s*\S', 1),
    ('cn-list', rf'^{_CN}\s*[、．]\s*\S', 3),
    ('paren-cn', rf'^[（(]\s*{_CN}\s*[）)]\s*\S', 4),
    ('number-list', r'^\d+\s*[、.)．]\s*\S', 3),
]


def family(text):
    value = unicodedata.normalize('NFKC', text).strip()
    if exercise_heading(value) or re.fullmatch(r'(?:review\s+)?(?:exercises|problems|questions)', value, re.I):
        return 'exercise', 2
    decimal = re.match(r'^\d+(?:\s*\.\s*\d+){1,5}(?:\s+|(?=[^\d.]))\S', value)
    if decimal:
        depth = re.match(r'^\d+(?:\s*\.\s*\d+)+', value)[0].count('.') + 1
        return f'decimal-{depth}', depth
    for name, pattern, level in _NUMBERING:
        if re.match(pattern, value, re.I):
            if name == 'paren-cn' and re.match(r'^\(\s*\d', value):
                name = 'paren-number'
            return name, level
    if re.match(r'^\d+\s+[^\d\s]', value):
        return 'number-space', 1
    return '', 0


def _key(text):
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', text)).casefold()


def _prose(text):
    name, _ = family(text)
    # A colon in "Chapter 1: Foundations" is normal heading punctuation.
    numbered_title = name in {'part', 'part-en', 'chapter', 'chapter-en', 'section'}
    return body_title(text) and not (numbered_title and not re.search(r'[，,。！？?=]', text))


def _style(block):
    """Only use producer-supplied styles, never infer a font from box height."""
    attrs = block.attributes
    values = [attrs.get(k) for k in ('font_size', 'font_name', 'bold', 'style_name')]
    return tuple(values) if any(v is not None for v in values) else None


def _toc_line(line):
    # Leader dots/space + printed page. Also accept compact numbered entries.
    match = re.match(r'^(.*?)\s*(?:[.·…．]{2,}|\s)(\d{1,4}|[ivxlcdm]+)\s*$', line, re.I)
    if not match:
        match = re.match(r'^(.*?\D)(\d{1,4})\s*$', line) if family(line)[0] else None
    if not match or len(match[1].strip()) < 2:
        return None
    title = re.sub(r'[.·…．\s]+$', '', match[1]).strip()
    return dict(title=title, printed_page=int(match[2]) if match[2].isdigit() else None)


def _toc_matches(blocks, toc_pages=None):
    """Find dense entry pages, then verify against ordered body occurrences."""
    entries_by_page, markers, source_rows = defaultdict(list), set(), {}
    body = defaultdict(list)
    for i, block in enumerate(blocks):
        if block.block_type not in {'heading', 'paragraph', 'example', 'exercise'}:
            continue
        page = block.page_start
        lines = [line.strip() for line in block.text.splitlines() if line.strip()]
        if len(lines) == 1 and len(block.text) <= 140:
            body[_key(block.text)].append(i)
        if toc_pages and page not in toc_pages:
            continue
        parsed = [(line, _toc_line(line)) for line in lines]
        marker = any(re.fullmatch(r'(?:总?目\s*录|table\s+of\s+contents|contents)', line, re.I) for line in lines)
        explicit = block.attributes.get('mineru_type') in {'index', 'toc', 'table_of_contents'}
        if marker or explicit:
            markers.add(page)
        # A mixed TOC/body block is retained; never discard its unparsed prose.
        clean = all(entry or re.fullmatch(r'(?:总?目\s*录|table\s+of\s+contents|contents|\d+)', line, re.I)
                    for line, entry in parsed)
        source_rows[i] = clean
        for _, entry in parsed:
            if entry:
                entries_by_page[page].append(dict(entry, source_index=i))
    pages = sorted(p for p, entries in entries_by_page.items() if p is not None
                   and (len(entries) >= 3 or p in markers and len(entries) >= 2))
    groups = []
    for page in pages:
        if groups and page == groups[-1][-1] + 1:
            groups[-1].append(page)
        else:
            groups.append([page])
    accepted, excluded, reports = {}, set(), []
    for pages in groups:
        entries = [e for p in pages for e in entries_by_page[p]]
        end = max(e['source_index'] for e in entries)
        offsets = []
        for e in entries:
            candidates = [n for n in body.get(_key(e['title']), []) if n > end]
            if len(candidates) == 1 and e['printed_page'] is not None and blocks[candidates[0]].page_start is not None:
                offsets.append(blocks[candidates[0]].page_start - e['printed_page'])
        offset = median(offsets) if offsets else None
        matches, after = [], end
        for entry in entries:
            candidates = [n for n in body.get(_key(entry['title']), []) if n > after]
            if not candidates:
                continue
            if offset is not None and entry['printed_page'] is not None:
                target = entry['printed_page'] + offset
                n = min(candidates, key=lambda n: abs((blocks[n].page_start or target) - target))
            else:
                n = candidates[0]
            matches.append((n, entry))
            after = n
        valid = len(matches) >= 2 and len(matches) / len(entries) >= .6
        reports.append(dict(pages=pages, entries=len(entries), matched=len(matches), accepted=valid,
                            explicit=any(p in markers for p in pages),
                            unmatched=[e['title'] for e in entries if e not in [m[1] for m in matches]]))
        if not valid:
            continue
        for n, entry in matches:
            accepted[n] = entry
        excluded.update(e['source_index'] for e in entries if source_rows[e['source_index']])
        excluded.update(i for i, b in enumerate(blocks) if b.page_start in pages
                        and re.fullmatch(r'(?:总?目\s*录|table\s+of\s+contents|contents)', b.text, re.I))
    return accepted, excluded, reports


def recover_outline(book, examples=None, max_depth=None, *, force=False):
    """Return a derived candidate. Reading an active document never mutates it."""
    if not force and examples is None and book.source_metadata.get('outline_recovery', {}).get('version') == POLICY_VERSION:
        return book
    result = deepcopy(book)
    previous = book.source_metadata.get('outline_recovery', {})
    examples = examples if examples is not None else previous.get('examples', [])
    max_depth = max_depth if max_depth is not None else previous.get('max_depth', 6)
    if type(max_depth) is not int or not 1 <= max_depth <= 6:
        raise ValueError('目录深度应为 1–6 级')
    blocks = result.blocks
    for b in blocks:
        original = b.attributes.setdefault('outline_source', dict(block_type=b.block_type,
            section_path=list(b.section_path), heading_level=b.attributes.get('heading_level')))
        b.block_type = original['block_type']
        b.section_path = list(original['section_path'])
        for k in ('outline_level', 'outline_role', 'outline_visible', 'outline_root_id', 'outline_parent_id', 'outline_method',
                  'outline_toc', 'learning_unit_id', 'example_id', 'exercise_id'):
            b.attributes.pop(k, None)
        if b.attributes.get('semantic_role') in {'exercise', 'example'} and b.block_type == 'paragraph':
            b.attributes.pop('semantic_role', None)
    by_id = {b.block_id: b for b in blocks}
    taught, styles, exact = {}, {}, {}
    for example in examples:
        bid, level, role = example['block_id'], example['level'], example.get('role', 'section')
        if bid not in by_id or by_id[bid].block_type not in {'heading', 'paragraph', 'example', 'exercise'}:
            raise ValueError('校准项必须来自当前教材的文字块')
        if type(level) is not int or not 0 <= level <= 6 or role not in {'section', 'exercise'}:
            raise ValueError('请选择正文或 1–6 级标题，并指定用途')
        b = by_id[bid]
        name, _ = family(b.text)
        signature = ('family', name) if name else ('text', _key(b.text))
        value = (level, role)
        if signature in taught and taught[signature] != value:
            raise ValueError('同一种编号格式设置了不同层级，请统一示例')
        taught[signature] = value
        if not name and _style(b):
            styles[_style(b)] = value
        exact[bid] = value
    toc, toc_blocks, toc_report = _toc_matches(blocks, result.source_metadata.get('toc_pages'))
    bookmarks, after = {}, -1
    for entry in result.source_metadata.get('pdf_bookmarks', []):
        candidates = [i for i, b in enumerate(blocks) if i > after and i not in toc_blocks
                      and _key(b.text) == _key(entry['title']) and b.page_start is not None
                      and abs(b.page_start - entry['page']) <= 1]
        if candidates:
            after = min(candidates, key=lambda i: abs(blocks[i].page_start - entry['page']))
            bookmarks[after] = entry['level']
    families = Counter(family(b.text)[0] for i, b in enumerate(blocks) if i not in toc_blocks
                       and len(b.text) <= 100 and not _prose(b.text))
    font_mass, title_fonts = Counter(), Counter()
    for i, b in enumerate(blocks):
        size = b.attributes.get('font_size')
        if i not in toc_blocks and b.block_type in {'paragraph', 'heading'} and isinstance(size, (int, float)):
            font_mass[size] += len(b.text)
            if len(b.text) <= 100 and not _prose(b.text) and not _key(b.text).isnumeric():
                title_fonts[size] += 1
    body_font = font_mass.most_common(1)[0][0] if font_mass else 0
    font_levels = {size: i + 1 for i, size in enumerate(sorted(
        (s for s, count in title_fonts.items() if count >= 2 and s >= body_font * 1.15), reverse=True))}
    has_part = families['part'] + families['part-en'] > 0
    has_chapter = families['chapter'] + families['chapter-en'] > 0
    stack, numeric_level, roots, heading_count = [], 1, 0, 0
    for i, b in enumerate(blocks):
        if i in toc_blocks:
            b.block_type = 'paragraph'
            b.attributes.update(outline_toc=True, outline_method='verified_toc')
            b.section_path = [result.book_name]
            continue
        eligible = b.block_type in {'heading', 'paragraph', 'example', 'exercise'}
        name, level = family(b.text) if eligible and len(b.text) <= 140 else ('', 0)
        role, method = ('exercise' if name == 'exercise' else 'section'), ''
        signature = ('family', name) if name else ('text', _key(b.text))
        style_hint = (styles.get(_style(b)) if eligible and len(b.text) <= 100 and not body_title(b.text)
                      and (b.attributes['outline_source']['block_type'] == 'heading'
                           or isinstance(b.attributes.get('font_size'), (int, float))
                           and b.attributes['font_size'] >= body_font * 1.15 and body_font > 0) else None)
        taught_value = exact.get(b.block_id) or taught.get(signature) or style_hint
        if taught_value is not None and eligible:
            level, role = taught_value
            method = 'user_example'
        elif i in bookmarks:
            level = bookmarks[i]
            method = 'pdf_bookmark'
        elif i in toc:
            level = level or 2
            method = 'toc_body_match'
        elif eligible and not _prose(b.text):
            source = b.attributes['outline_source']
            source_heading = source['block_type'] == 'heading'
            in_exercises = bool(stack and stack[-1][3] == 'exercise')
            if name in {'part', 'part-en', 'chapter', 'chapter-en', 'section'}:
                method = 'numbering'
            elif name.startswith('decimal-') and not in_exercises and (source_heading or families[name] >= 2):
                method = 'numbering'
            elif name in {'cn-list', 'paren-cn'} and source_heading and not in_exercises:
                method = 'numbering'
            elif (name == 'number-space' and families[name] >= 2 and not has_chapter and not in_exercises
                  and (source_heading or families['decimal-2'] >= 2)):
                method = 'numbering'
            elif name == 'number-list' and source_heading and not has_chapter and not in_exercises:
                level = 1
                method = 'numbering'
            elif name == 'exercise' and stack:
                level = 2 + int(has_part and has_chapter)
                method = 'learning_section'
            elif not name and len(b.text) <= 100 and b.attributes.get('font_size') in font_levels:
                level = font_levels[b.attributes['font_size']]
                method = 'document_style'
            elif (source_heading and not name and len(b.text) <= 100
                  and not re.match(r'^(?:【?\s*例|解答|答案|证明|[#＃]\s*\d|【\s*\d)', b.text)):
                # Producer headings remain hints. Do not turn consecutive weak
                # labels into a staircase of ever-deeper descendants.
                level = (min(numeric_level + 1, 6) if b.attributes.get('heading_rule') == 'bounded_unnumbered'
                         else source.get('heading_level') or min(numeric_level + 1, 6))
                method = 'source_heading'
            else:
                level = 0
        else:
            level = 0
        if level and method not in {'user_example', 'pdf_bookmark'}:
            if name in {'chapter', 'chapter-en'} and has_part:
                level = 2
            elif name == 'section' and has_part and has_chapter:
                level = 3
            elif name == 'cn-list':
                level = 3 if families['section'] else 2
            elif name == 'paren-cn':
                level = (3 if families['section'] else 2) + 1
        if eligible:
            if level:
                while stack and stack[-1][0] >= level:
                    stack.pop()
                # Missing intermediate levels do not manufacture parent titles.
                actual_level = len(stack) + 1
                b.block_type = 'heading'
                b.attributes.update(heading_level=actual_level, outline_level=actual_level, outline_role=role,
                    outline_parent_id=stack[-1][2] if stack else '', outline_method=method,
                    outline_visible=actual_level <= max_depth)
                if not stack:
                    roots += 1
                from ingestion.document_ir import canonical_chapter_title
                title = canonical_chapter_title(b.text) or b.text
                stack.append((level, title, b.block_id, role))
                heading_count += 1
                if name not in {'exercise', ''}:
                    numeric_level = level
            else:
                if b.block_type == 'heading':
                    b.block_type = 'paragraph'
                b.attributes.update(outline_level=0, outline_method=method or 'body')
        b.section_path = [item[1] for item in stack] or [result.book_name]
        b.attributes['outline_root_id'] = stack[0][2] if stack else ''
    result.source_metadata['outline_recovery'] = dict(version=POLICY_VERSION, headings=heading_count, roots=roots,
        toc=toc_report, matched_bookmarks=len(bookmarks), examples=examples, max_depth=max_depth)
    from ingestion.document_workflows import annotate_learning_units
    annotate_learning_units(result)
    return result


def attach_pdf_bookmarks(book, pdf_path):
    """Reuse physical bookmark destinations when the original PDF is available."""
    import fitz
    with fitz.open(pdf_path) as doc:
        entries = [dict(level=level, title=title, page=page) for level, title, page in doc.get_toc()
                   if 1 <= page <= len(doc)]
    if not entries:
        return book
    result = deepcopy(book)
    result.source_metadata['pdf_bookmarks'] = entries
    return recover_outline(result, force=True)
