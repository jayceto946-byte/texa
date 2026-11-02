"""Shared source roles and source-backed structural corrections, never OCR text rewriting."""
from copy import deepcopy
import re

from ingestion.heading_policy import exercise_heading, solution_heading

NON_PRACTICE = {'front_matter', 'toc', 'overview', 'reference', 'annotation'}
ROLES = NON_PRACTICE | {'body', 'exercise', 'solution', 'unknown'}
_OVERVIEW = re.compile(r'^(?:本章(?:主要内容|内容提要|小结)|内容提要|知识要点|chapter\s+(?:overview|summary))$', re.I)


def block_role(block):
    reviewed = block.attributes.get('structure_role') or block.attributes.get('structure_page_role')
    if reviewed and reviewed != 'unknown':
        return reviewed
    if block.attributes.get('outline_toc'):
        return 'toc'
    for title in reversed(block.section_path):
        if _OVERVIEW.fullmatch(title.strip()):
            return 'overview'
        if solution_heading(title):
            return 'solution'
        if exercise_heading(title):
            return 'exercise'
    return block.attributes.get('document_region', 'body')


def has_exercise_scopes(book):
    # A named answer section does not imply that earlier unlabelled questions
    # are outside the exercise source.
    return any(b.block_type != 'figure' and block_role(b) == 'exercise' for b in book.blocks)


def annotate_regions(book):
    """Keep front matter available as source, without proposing it as practice."""
    toc_end = max((b.page_end or b.page_start or 0 for b in book.blocks if b.attributes.get('outline_toc')), default=0)
    for block in book.blocks:
        block.attributes['document_region'] = ('front_matter' if toc_end and (block.page_start or 0) < toc_end
                                                and not block.attributes.get('outline_toc') else 'body')
    return book


def _checked_segments(by_id, bid, decision):
    segments = decision.get('segments') or [decision]
    cursor = 0
    for segment in segments:
        role = segment.get('role', 'unknown')
        level = segment.get('heading_level')
        start, end = segment.get('start', 0), segment.get('end', len(by_id[bid].text))
        if (type(start) is not int or type(end) is not int or start != cursor
                or end < start or end > len(by_id[bid].text)):
            raise ValueError('结构审阅的原文边界不完整或重叠')
        cursor = end
        if role not in ROLES or (level is not None and (type(level) is not int or not 0 <= level <= 6)):
            raise ValueError('结构审阅的角色或层级无效')
        unit = segment.get('unit_id')
        if unit and (unit not in by_id or abs((by_id[unit].page_start or 0) - (by_id[bid].page_start or 0)) > 8):
            raise ValueError('结构审阅的题目关联超出来源范围')
        if segment.get('unit_role', 'question') not in {'question', 'answer', 'explanation', 'context'}:
            raise ValueError('结构审阅的题内角色无效')
        members = segment.get('group_members') or []
        if members and (by_id[bid].block_type != 'figure' or bid not in members
                or any(m not in by_id or by_id[m].block_type != 'figure'
                       or by_id[m].page_start != by_id[bid].page_start for m in members)):
            raise ValueError('结构审阅的子图来源无效')
    if cursor != len(by_id[bid].text):
        raise ValueError('结构审阅遗漏了来源正文')
    return segments


def apply_structure_review(book, decisions, *, report=None, recover=True, issues=None):
    """Validate and apply model proposals to a copy; models only select existing sources.

    Optional source spans split a coarse OCR paragraph. They must partition its
    original text completely; no replacement body, page or asset path is accepted.
    """
    result = deepcopy(book)
    # Sparse review decisions are edits, not a declaration that every omitted
    # source block is outside the exercise scope. Freeze the original policy.
    result.source_metadata.setdefault('exercise_scope_policy','regions' if has_exercise_scopes(book) else 'all')
    by_id = {b.block_id: b for b in result.blocks}
    assignments = {}
    for decision in decisions:
        bid = decision['block_id']
        try:
            if bid not in by_id or bid in assignments:
                raise ValueError('结构审阅引用了未知或重复来源块')
            segments = _checked_segments(by_id, bid, decision)
            assignments[bid] = segments
        except ValueError as exc:
            if issues is None:
                raise
            issues.append(dict(block_id=bid, reason=str(exc)+'；已保留原文'))

    blocks = []
    for block in result.blocks:
        segments = assignments.get(block.block_id)
        if not segments:
            blocks.append(block); continue
        for segment in segments:
            child = deepcopy(block)
            if len(segments) > 1:
                start, end = segment['start'], segment['end']
                child.block_id = f'{block.block_id}@{start}:{end}'
                child.text = block.text[start:end]
                child.attributes.update(source_parent_id=block.block_id, source_start=start, source_end=end)
            child.attributes['structure_role'] = segment.get('role', child.attributes.get('structure_role', 'unknown'))
            if segment.get('reason'):child.attributes['structure_review_reason']=str(segment['reason'])
            for key in ('unit_id', 'unit_role', 'unit_start', 'group_members', 'heading_level'):
                if key in segment:
                    child.attributes['structure_' + key] = deepcopy(segment[key])
            if len(segments)>1 and segment.get('unit_start'):
                child.attributes.pop('structure_unit_id',None)
            if child.attributes['structure_role'] == 'toc':
                child.attributes['outline_toc'] = True
            blocks.append(child)
    first_children = {}
    for block in blocks:
        first_children.setdefault(block.attributes.get('source_parent_id', block.block_id), block.block_id)
    for block in blocks:
        target = block.attributes.get('structure_unit_id')
        if target in first_children:
            block.attributes['structure_unit_id'] = first_children[target]
    result.blocks = blocks
    result.source_metadata['structure_review'] = report or {'status': 'reviewed'}
    if recover and any('heading_level' in s or s.get('role') in NON_PRACTICE for segments in assignments.values() for s in segments):
        from ingestion.outline_recovery import recover_outline
        return recover_outline(result, force=True)
    return result
