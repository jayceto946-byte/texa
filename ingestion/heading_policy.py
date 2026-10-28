"""Conservative structural signals shared by native intake and learning scopes.

OCR title labels and raw levels are hints. Explicit numbering establishes the
hierarchy; sentence fragments stay readable body instead of disappearing as
index-only headings. These rules do not claim semantic/OCR correctness.
"""
import re

_CN = r'[零〇一二三四五六七八九十百千0-9]+'
SECTION = re.compile(r'^第\s*' + _CN + r'\s*节\s*\S')
ENUMERATION = re.compile(r'^' + _CN + r'\s*[、．.]\s*\S')
SUBSECTION = re.compile(r'^[（(]\s*' + _CN + r'\s*[）)]\s*\S')
DECIMAL = re.compile(r'^(\d+(?:\s*\.\s*\d+){1,5})(?:\s+|(?=[^\d.]))(.+)$')
_EXERCISE = re.compile(r'^(?:本章|章末|课后)?(?:习题|练习题?|复习题|思考题)'
                       r'(?:(?:与|及|和)(?:习题|练习题?|复习题|思考题))?'
                       r'(?:[一二三四五六七八九十\d]+(?:[.．-]\d+)*)?$')
PROBLEM_START = re.compile(r'^\s*\d+(?:\s*[-－—]\s*\d+)+(?:\s*[.．、)]|\s+|(?=[\u4e00-\u9fff]))|^\s*\d+\s*[.．、)]')


def exercise_heading(text):
    return bool(_EXERCISE.fullmatch(re.sub(r'\s+', '', str(text or ''))))


def body_title(text):
    """Reject explicit prose/continuations, not arbitrary unrecognized nouns."""
    text = str(text or '').strip()
    return bool(re.search(r'[，,。！？:：$\\=]', text)
                or re.match(r'^(?:为了|由于|因此|从而|以便|并且|的|地)', text)
                or re.search(r'(?:常采用|的措施为|并兼得|如下|所示)$', text))


def native_heading(text, numbered_path):
    """Return (level, rule); empty rule keeps the producer title in the body."""
    from ingestion.document_ir import canonical_chapter_title
    text = str(text or '').strip()
    if canonical_chapter_title(text):
        return 1, 'numbered_chapter'
    decimal = DECIMAL.match(text)
    if decimal and not body_title(text) and not any(exercise_heading(p) for p in numbered_path):
        return min(decimal[1].count('.') + 1, 6), 'numbered_section'
    if not numbered_path:
        return 0, ''
    if exercise_heading(text) or text == '参考文献':
        return 2, 'chapter_end_section'
    if body_title(text):
        return 0, ''
    if PROBLEM_START.match(text):
        return 0, ''
    if SECTION.match(text):
        return 2, 'chinese_section'
    if ENUMERATION.match(text) and not re.match(r'^\d', text):
        return (3 if len(numbered_path) > 1 and SECTION.match(numbered_path[1]) else 2), 'chinese_enumeration'
    if SUBSECTION.match(text) and not re.match(r'^[（(]\s*\d', text):
        parent = next((i + 1 for i, part in enumerate(numbered_path) if ENUMERATION.match(part)), 2)
        return parent + 1, 'chinese_subsection'
    if (2 <= len(text) <= 24 and not re.match(r'^(?:【|\[)?\s*(?:例题?|解答|答案|证明)', text)
            and not re.match(r'^[（(]\s*\d', text)):
        return min(len(numbered_path) + 1, 6), 'bounded_unnumbered'
    return 0, ''
