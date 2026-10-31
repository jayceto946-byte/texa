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

POLICY_VERSION = 5
_CN = r'[零〇一二三四五六七八九十百千\d](?:\s*[零〇一二三四五六七八九十百千\d])*'
_NUMBERING = [
    ('part', rf'^第\s*{_CN}\s*[篇部](?:\s*\S|\s*$)', 1),
    ('chapter', rf'^第\s*{_CN}\s*章(?:\s*\S|\s*$)', 1),
    ('section', rf'^第\s*{_CN}\s*节(?:\s*\S|\s*$)', 2),
    ('part-en', r'^part\s+(?:\d+|[ivxlcdm]+)\b(?:\s*[:.\-]?\s*\S|\s*$)', 1),
    ('chapter-en', r'^chapter\s+(?:\d+|[ivxlcdm]+)\b(?:\s*[:.\-]?\s*\S|\s*$)', 1),
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
    line = re.sub(r'^\s*[-*+]\s+', '', line)
    # Leader dots/space + printed page. Also accept compact numbered entries.
    match = re.match(r'^(.*?)\s*(?:[.·…．]{2,}|\s)(\d{1,4}|[ivxlcdm]+)\s*$', line, re.I)
    if not match:
        match = re.match(r'^(.*?\D)(\d{1,4})\s*$', line) if family(line)[0] else None
    if not match or len(match[1].strip()) < 2:
        return None
    title = re.sub(r'[.·…．\s]+$', '', match[1]).strip()
    return dict(title=title, printed_page=int(match[2]) if match[2].isdigit() else None)


def _split_heading_titles(blocks):
    """Join label/title hints for navigation, retaining both source blocks verbatim."""
    labels = re.compile(rf'^(?:第\s*{_CN}\s*[章篇部节]|(?:chapter|part)\s+(?:\d+|[ivxlcdm]+))\s*$', re.I)
    toc_titles = {_key(entry['title']) for b in blocks for line in b.text.splitlines()
                  if (entry := _toc_line(line))}
    titles, continuations = {}, set()
    for i, block in enumerate(blocks[:-1]):
        if block.block_type not in {'heading', 'paragraph'} or not labels.fullmatch(block.text.strip()):
            continue
        following = blocks[i + 1]
        title = following.text.strip()
        if (following.block_type not in {'heading', 'paragraph'} or following.page_start != block.page_start
                or not 1 < len(title) <= 100 or '\n' in title or family(title)[0] or body_title(title)):
            continue
        combined = block.text.strip() + ' ' + title
        if following.block_type == 'heading' or _key(combined) in toc_titles:
            titles[i] = combined
            continuations.add(i + 1)
    return titles, continuations


def _toc_boundaries(blocks, entries, matches, toc_end):
    """Recover an omitted chapter label using TOC pages and matched sections.

    A TOC title is source evidence even when OCR missed its body occurrence.
    Require a consistent physical-page offset from at least two chapter anchors
    and a section anchor inside the omitted chapter; never guess from a section
    counter restarting or manufacture a source text block.
    """
    chapter_rows = [i for i, e in enumerate(entries) if family(e['title'])[0] in {'chapter', 'chapter-en'}]
    matched = {entries.index(entry): n for n, entry in matches}
    offsets = [blocks[matched[row]].page_start - entries[row]['printed_page'] for row in chapter_rows
               if row in matched and entries[row]['printed_page'] is not None
               and blocks[matched[row]].page_start is not None]
    if len(offsets) < 2:
        return {}
    offset, count = Counter(offsets).most_common(1)[0]
    if count < 2:
        return {}
    boundaries = {}
    for position, row in enumerate(chapter_rows):
        entry = entries[row]
        if row in matched or entry['printed_page'] is None:
            continue
        next_row = chapter_rows[position + 1] if position + 1 < len(chapter_rows) else len(entries)
        sections = [n for r, n in matched.items() if row < r < next_row
                    and entries[r]['printed_page'] is not None
                    and blocks[n].page_start is not None
                    and blocks[n].page_start - entries[r]['printed_page'] == offset]
        if not sections:
            continue
        left = max((matched[r] for r in chapter_rows if r < row and r in matched), default=toc_end)
        right = min((matched[r] for r in chapter_rows if r > row and r in matched), default=len(blocks))
        # A changed PDF/printed-page offset makes the chapter boundary unknown.
        if any(blocks[n].page_start - entries[r]['printed_page'] != offset for r, n in matched.items()
               if r in chapter_rows and n in {left, right} and entries[r]['printed_page'] is not None):
            continue
        target = entry['printed_page'] + offset
        candidates = [n for n in range(left + 1, min(right, min(sections) + 1))
                      if blocks[n].page_start == target]
        if not candidates or any(family(blocks[n].text)[0] in {'chapter', 'chapter-en'} for n in candidates):
            continue
        anchor = candidates[0]
        boundaries[anchor] = dict(title=entry['title'], source_index=entry['source_index'],
                                  toc_row=row, physical_page=target, printed_page=entry['printed_page'])
    return boundaries


def _toc_matches(blocks, toc_pages=None, heading_titles=None):
    """Find dense entry pages, then verify against ordered body occurrences."""
    entries_by_page, markers, source_rows = defaultdict(list), set(), {}
    body = defaultdict(list)
    for i, block in enumerate(blocks):
        if block.block_type not in {'heading', 'paragraph', 'example', 'exercise'}:
            continue
        page = block.page_start
        lines = [line.strip() for line in block.text.splitlines() if line.strip()]
        text = (heading_titles or {}).get(i, block.text)
        if len(text) <= 140:
            body[_key(text)].append(i)
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
    accepted, excluded, reports, boundaries = {}, set(), [], {}
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
        recovered = _toc_boundaries(blocks, entries, matches, end)
        boundaries.update(recovered)
        reports[-1]['recovered_chapters'] = [item['title'] for item in recovered.values()]
        for n, entry in matches:
            accepted[n] = entry
        excluded.update(e['source_index'] for e in entries if source_rows[e['source_index']])
        excluded.update(i for i, b in enumerate(blocks) if b.page_start in pages
                        and re.fullmatch(r'(?:总?目\s*录|table\s+of\s+contents|contents)', b.text, re.I))
    return accepted, excluded, reports, boundaries


def _restore_source_titles(book):
    """Restore numbered source titles previously retained only in metadata."""
    from ingestion.document_ir import DocumentBlock
    restored = 0
    for title in book.source_metadata.get('document_titles', []):
        text = title.get('text', '').strip()
        kind, _ = family(text)
        if kind not in {'chapter', 'chapter-en', 'part', 'part-en', 'section'} and not kind.startswith('decimal-'):
            continue
        page, source_index = title['page_idx'] + 1, title['source_block_index']
        if any(b.page_start == page and _key(b.text) == _key(text) for b in book.blocks):
            continue
        index = next((i for i, b in enumerate(book.blocks) if b.page_start == page
                      and b.attributes.get('source_block_index', -1) > source_index), None)
        if index is None:
            continue
        anchor = book.blocks[index]
        book.blocks.insert(index, DocumentBlock(
            block_id=f'source-title:{title["page_idx"]}:{source_index}', block_type='heading', text=text,
            section_path=[book.book_name], page_start=page, page_end=page,
            source_file=anchor.source_file, source_kind=anchor.source_kind,
            bbox=title.get('bbox'), attributes=dict(mineru_type='doc_title', source_page_idx=title['page_idx'],
                source_block_index=source_index, restored_source_title=True,
                bbox_space='page' if title.get('bbox') else 'unknown',
                bbox_format='xyxy' if title.get('bbox') else 'unknown',
                bbox_units='normalized' if title.get('bbox') else 'unknown')))
        restored += 1
    return restored


def recover_outline(book, examples=None, max_depth=None, *, force=False):
    """Return a derived candidate. Reading an active document never mutates it."""
    if not force and examples is None and book.source_metadata.get('outline_recovery', {}).get('version') == POLICY_VERSION:
        return book
    result = deepcopy(book)
    restored_titles = _restore_source_titles(result)
    previous = book.source_metadata.get('outline_recovery', {})
    examples = examples if examples is not None else previous.get('examples', [])
    max_depth = max_depth if max_depth is not None else previous.get('max_depth', 2)
    if type(max_depth) is not int or not 1 <= max_depth <= 6:
        raise ValueError('目录深度应为 1–6 级')
    blocks = result.blocks
    for b in blocks:
        original = b.attributes.setdefault('outline_source', dict(block_type=b.block_type,
            section_path=list(b.section_path), heading_level=b.attributes.get('heading_level')))
        b.block_type = original['block_type']
        b.section_path = list(original['section_path'])
        for k in ('outline_level', 'outline_role', 'outline_visible', 'outline_root_id', 'outline_parent_id', 'outline_method',
                  'outline_toc', 'outline_title', 'outline_boundary', 'learning_unit_id', 'example_id', 'exercise_id'):
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
    heading_titles, continuations = _split_heading_titles(blocks)
    toc, toc_blocks, toc_report, boundaries = _toc_matches(blocks, result.source_metadata.get('toc_pages'), heading_titles)
    bookmarks, after = {}, -1
    for entry in result.source_metadata.get('pdf_bookmarks', []):
        candidates = [i for i, b in enumerate(blocks) if i > after and i not in toc_blocks
                      and _key(heading_titles.get(i, b.text)) == _key(entry['title']) and b.page_start is not None
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
    has_chapter = families['chapter'] + families['chapter-en'] > 0 or bool(boundaries)
    stack, numeric_level, roots, heading_count = [], 1, 0, 0
    for i, b in enumerate(blocks):
        if i in toc_blocks:
            b.block_type = 'paragraph'
            b.attributes.update(outline_toc=True, outline_method='verified_toc')
            b.section_path = [result.book_name]
            continue
        if i in boundaries:
            boundary = boundaries[i]
            boundary_level = 2 if has_part else 1
            while stack and stack[-1][0] >= boundary_level:
                stack.pop()
            if not stack:
                roots += 1
            from ingestion.document_ir import canonical_chapter_title
            title = canonical_chapter_title(boundary['title']) or boundary['title']
            source_id = boundary.get('source_block_id') or blocks[boundary['source_index']].block_id
            root_id = f'toc:{source_id}:{boundary["toc_row"]}' if 'toc_row' in boundary else source_id
            stack.append((boundary_level, title, root_id, 'section'))
            numeric_level = boundary_level
            b.attributes['outline_boundary'] = {**boundary, 'source_block_id': source_id,
                                               'method': boundary.get('method', 'verified_toc_page')}
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
        elif i in continuations:
            level = 0
            method = 'heading_continuation'
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
                if has_chapter:
                    level = max(3, min(numeric_level + 1, 6)) if stack else 0
                else:
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
                level = 3 if families['section'] or families['decimal-2'] or has_chapter and i not in toc else 2
            elif name == 'paren-cn':
                level = (3 if families['section'] or families['decimal-2'] or has_chapter and i not in toc else 2) + 1
        if eligible:
            if level:
                while stack and stack[-1][0] >= level:
                    stack.pop()
                # Missing intermediate levels do not manufacture parent titles.
                actual_level = len(stack) + 1
                b.block_type = 'heading'
                b.attributes.update(heading_level=actual_level, outline_level=actual_level, outline_role=role,
                    outline_parent_id=stack[-1][2] if stack else '', outline_method=method,
                    outline_visible=level <= max_depth)
                if not stack:
                    roots += 1
                from ingestion.document_ir import canonical_chapter_title
                title = heading_titles.get(i, b.text)
                title = canonical_chapter_title(title) or title
                b.attributes['outline_title'] = title
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
        toc=toc_report, recovered_chapters=len(boundaries), restored_source_titles=sum(bool(b.attributes.get('restored_source_title')) for b in blocks), matched_bookmarks=len(bookmarks), examples=examples, max_depth=max_depth,
        stable_scope_ids=bool(boundaries) or bool(restored_titles) or previous.get('stable_scope_ids', False))
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
