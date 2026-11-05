"""Account for source questions before replacing a candidate batch."""
from collections import Counter,defaultdict

from backend.services.exercise_file_analysis import file_book
from ingestion.document_structure import NON_PRACTICE
from memory.exercise_file_importer import ExtractedExerciseText
from memory.exercise_structure import exercise_units
from memory.exercise_candidate_projection import project_units, source_registry


def candidate_coverage(original,reviewed):
    original_ids={b.block_id for b in original.blocks}
    def root(block):
        bid=block.attributes.get('source_parent_id',block.block_id)
        while True:
            if bid in original_ids:return bid
            if bid.startswith('q-') and bid[2:] in original_ids:return bid[2:]
            if '@' not in bid:break
            bid=bid.rsplit('@',1)[0]
        return bid
    def units(book):
        normalized=file_book(ExtractedExerciseText('', 'zip',canonical_book=book),name=original.book_name)
        rows=exercise_units(normalized,unrestricted=True)
        if book.source_metadata.get('review_source_mode')=='examples':rows=[u for u in rows if u['kind']=='example']
        blocks={b.block_id:b for b in normalized.blocks}
        proposals=project_units(rows,source_registry(normalized,rows,set(blocks)),'coverage',{})
        used={span['block_id'] for p in proposals for spans in p['projection']['parts'].values() for span in spans}
        raw_ids={b.block_id for b in book.blocks}
        parent_lines=defaultdict(set)
        for b in normalized.blocks:
            parent=b.attributes.get('source_parent_id')
            parent=parent if parent in raw_ids else b.block_id.removeprefix('q-')
            parent_lines[parent].add(b.block_id)
        covered={parent for parent,lines in parent_lines.items() if lines<=used}
        return [(root(blocks[p['projection']['unit_ids'][0]]),p) for p in proposals],covered
    (before,_),(after,used)=units(original),units(reviewed)
    before_count,after_count=Counter(k for k,u in before),Counter(k for k,u in after)
    by_origin=defaultdict(list)
    for block in reviewed.blocks:
        origin=block.block_id if block.block_id in original_ids else root(block)
        by_origin[origin].append(block)
    removed=[]
    for origin,count in before_count.items():
        missing=max(0,count-after_count[origin])
        if not missing:continue
        blocks=by_origin[origin]
        duplicate=any(b.attributes.get('structure_duplicate_of') for b in blocks) and all(
            b.attributes.get('structure_duplicate_of') or b.attributes.get('structure_unit_id') and b.attributes.get('structure_unit_role') in {'answer','explanation','context'} for b in blocks)
        excluded=bool(blocks) and all(b.attributes.get('structure_role') in NON_PRACTICE and b.attributes.get('structure_review_reason') for b in blocks)
        demoted=bool(blocks) and all(b.attributes.get('structure_role')=='body' and b.attributes.get('structure_unit_start') is False
            and not b.attributes.get('structure_unit_id') and b.attributes.get('structure_review_reason') for b in blocks)
        reassembled=bool(blocks) and all(b.block_id in used for b in blocks) and any(b.attributes.get('structure_review_reason') for b in blocks)
        removed.append(dict(block_id=origin,count=missing,reason='verified_duplicate' if duplicate else 'excluded_source' if excluded or demoted else 'reassembled_source' if reassembled else 'unaccounted'))
    return dict(before=len(before),after=len(after),removed=sum(v['count'] for v in removed),
                unaccounted=sum(v['count'] for v in removed if v['reason']=='unaccounted'),changes=removed)
