"""Read printed chapter/section labels and explicit catalogue ranges, without AI."""
import re
from html import unescape
from collections import Counter

NUM = r'[零〇一二三四五六七八九十百\d]+'
LABEL = re.compile(rf'^\s*(?:#{{1,6}}\s*)?(?P<label>第\s*{NUM}\s*(?P<kind>[章节])|{NUM}[、．.·])\s*(?P<title>[^\n]{{0,70}})$')
ENTRY = re.compile(rf'(?P<label>第\s*{NUM}\s*章|{NUM}[、．.·])\s*(?P<title>[^|+\n\d]{{1,60}}?)\s+(?P<start>\d{{1,6}})\s*[-－—–~～]\s*(?P<end>\d{{1,6}})(?!\d)')
DECIMAL = re.compile(r'^\s*(?:#{1,6}\s*)?(\d+(?:[.．]\d+)+)\s+([^\n]{1,70})$')


def heading(text, *, native=False):
    decimal = DECIMAL.fullmatch(text.strip())
    if decimal:
        return (len(re.split(r'[.．]',decimal[1])), text.strip()) if native else None
    match = LABEL.fullmatch(text.strip())
    if not match or re.search(r'[=。？?$]|原稿|难度|建议', match['title']):
        return None
    if not match['kind'] and match['label'][0].isdigit() and not native:
        return None  # Ordinary numbered question stems are not chapter headings.
    return (2 if match['kind'] == '节' else 1, re.sub(r'^\s*#{1,6}\s*', '', text).strip())


def _key(title):
    return re.sub(r'[第章节\s、．.·]', '', title)


def chapter_paths(book):
    """Ranges classify only their stated question numbers; TOCs never set body state."""
    from memory.exercise_structure import header_metadata, ORIGINAL, TOPIC, FOCUS
    titles = {b.block_id: heading(b.text, native=b.block_type == 'heading' or b.attributes.get('mineru_type') == 'paragraph_title') for b in book.blocks}
    chapter_counts = Counter(b.page_start for b in book.blocks if titles[b.block_id] and titles[b.block_id][0] == 1)
    question_pages = {b.page_start for b in book.blocks if header_metadata(b.text) or (ORIGINAL.match(b.text) and not titles[b.block_id])}
    toc_pages = {page for page, count in chapter_counts.items() if count >= 3 and page not in question_pages}
    names = {_key(value[1]): (value[1], b.block_id) for b in book.blocks if (value := titles[b.block_id])}
    ranges = []
    for block in book.blocks:
        if block.block_type != 'table' or not re.search(r'题号|编排号', block.text):
            continue
        text = unescape(re.sub(r'<[^>]+>', ' ', block.text))
        for match in ENTRY.finditer(text):
            start, end = int(match['start']), int(match['end'])
            if start <= end:
                title = (match['label'] + match['title']).strip()
                ranges.append((start, end, names.get(_key(title), (title, block.block_id)), block.block_id))
    current, result, focus = [], {}, None
    for block in book.blocks:
        label = titles[block.block_id]
        if label and block.page_start not in toc_pages:
            level, title = label
            current = current[:level-1] + [(title, block.block_id)]
            focus = None
        if TOPIC.match(block.text) or FOCUS.match(block.text):
            focus = block.block_id
        catalog = header_metadata(block.text)
        path = list(current)
        if catalog:
            number = int(catalog['catalog_number'].lstrip('#'))
            matches = {(title, bid) for start, end, (title, bid), _ in ranges if start <= number <= end}
            if len(matches) == 1:
                title, bid = next(iter(matches))
                path = [(title, bid)]
                # The table is also retained as context evidence for the assignment.
                evidence = next(e for start, end, value, e in ranges if start <= number <= end and value == (title, bid))
                path.append(('', evidence))
        if focus:
            path.append(('', focus))
        result[block.block_id] = path
    return result
