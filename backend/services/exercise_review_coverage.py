"""Account for source questions before replacing a candidate batch."""
from collections import Counter,defaultdict
from copy import deepcopy
from difflib import SequenceMatcher
import re

from backend.services.exercise_file_analysis import file_book
from ingestion.document_structure import NON_PRACTICE
from memory.exercise_file_importer import ExtractedExerciseText
from memory.exercise_structure import exercise_units, metadata_only, ORIGINAL
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
        return [(root(blocks[p['projection']['unit_ids'][0]]),p) for p in proposals],covered,normalized
    (before,_,before_book),(after,used,after_book)=units(original),units(reviewed)
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
    integrity = _question_integrity(original, reviewed, before_book, after_book, before, after, removed)
    return dict(before=len(before),after=len(after),removed=sum(v['count'] for v in removed),
                unaccounted=max(sum(v['count'] for v in removed if v['reason']=='unaccounted'),len(integrity['conflicts'])),
                changes=removed,question_integrity=integrity)


def _source_spans(book, normalized, original):
    """Map projected line/segment ranges to their original Unicode spans."""
    raw = {b.block_id:b for b in book.blocks}
    originals = {b.block_id:b for b in original.blocks}
    blocks = {b.block_id:b for b in normalized.blocks}
    extents, alignments = {}, {}

    def extent(bid):
        if bid in extents:return extents[bid]
        if bid in originals:
            value = (bid,0,len(originals[bid].text))
        else:
            block = raw.get(bid)
            attrs = block.attributes if block else {}
            parent = attrs.get('source_parent_id')
            if parent:
                left,right=attrs.get('source_start',0),attrs.get('source_end',len(block.text))
            elif '@' in bid:
                parent,span=bid.rsplit('@',1);left,right=map(int,span.split(':'))
            else:
                return (bid,0,len(block.text) if block else 0)
            root,start,_=extent(parent);value=(root,start+left,start+right)
        extents[bid]=value
        return value

    def spans(proposal, roles):
        result=[]
        for role in roles:
            for span in proposal['projection']['parts'][role]:
                block=blocks[span['block_id']]
                parent=block.attributes.get('source_parent_id')
                if parent not in raw:parent=block.block_id.removeprefix('q-')
                source=raw[parent]
                root,base,end=extent(parent)
                start=block.attributes.get('source_start',0) if block.block_type not in {'formula','table','figure'} else 0
                left=start+span['start'];right=start+(len(block.text) if span['end'] is None else span['end'])
                old=originals[root].text[base:end] if root in originals else source.text
                if old==source.text:
                    result.append((root,base+left,base+right))
                else:
                    if parent not in alignments:
                        alignments[parent]=SequenceMatcher(None,old,source.text,autojunk=False).get_opcodes()
                    for tag,a,b,c,d in alignments[parent]:
                        if tag=='equal' and max(left,c)<min(right,d):
                            result.append((root,base+a+max(left,c)-c,base+a+min(right,d)-c))
                        elif tag!='equal' and (max(left,c)<min(right,d) or c==d and left<=c<=right):
                            result.append((root,base+a,base+b))
                if not source.text:result.append((root,base,base))
        return result
    return spans


def _question_integrity(original, reviewed, before_book, after_book, before, after, changes):
    before_spans=_source_spans(original,before_book,original)
    after_spans=_source_spans(reviewed,after_book,original)
    original_blocks={b.block_id:b for b in original.blocks}
    dispositions={v['block_id']:v['reason'] for v in changes}
    shown=[]
    by_source=defaultdict(dict)
    visible_by_role=dict(question=defaultdict(list),solution=defaultdict(list))
    for _,proposal in after:
        owner=len(shown)
        value=dict(question=after_spans(proposal,('question','unassigned')),
                   solution=after_spans(proposal,('answer','explanation')))
        shown.append(value)
        for role,spans in value.items():
            for span in spans:
                visible_by_role[role][span[0]].append(span)
                by_source[span[0]].setdefault(owner,dict(question=[],solution=[]))[role].append(span)

    def covers(required, actual):
        bid,left,right=required
        values=sorted((a,b) for root,a,b in actual if root==bid)
        if left==right:return any(a<=left<=b for a,b in values)
        cursor=left
        text=original_blocks[bid].text if bid in original_blocks else ''
        for a,b in values:
            if b<=cursor:continue
            if a>cursor and text[cursor:min(a,right)].strip(' \t\r\n$\\{}'):return False
            cursor=max(cursor,b)
            if cursor>=right:return True
        return cursor>=right or not text[cursor:right].strip(' \t\r\n$\\{}')

    rows=[];owners=defaultdict(list);required_parts=[]
    for index,(origin,proposal) in enumerate(before):
        question=before_spans(proposal,('question','unassigned'))
        solution=before_spans(proposal,('answer','explanation'))
        raw_text=proposal['question_text'].strip()
        number=ORIGINAL.match(raw_text)
        body=raw_text[number.end():].strip() if number else raw_text
        catalog=proposal['projection']['structure'].get('catalog_number')
        disposition=dispositions.get(origin)
        # Rejoining an explicit continuation or a misread metadata/formula
        # fragment remains legal. Distinct complete questions need own owners.
        fragment=(metadata_only(raw_text) or bool(re.match(r'^(?:并|再|接上|续|由此|进一步)',body)))
        first_kind=next((b.block_type for b in before_book.blocks if b.block_id==proposal['projection']['unit_ids'][0]),'')
        exempt=(not catalog and (disposition in {'excluded_source','verified_duplicate'}
                or disposition=='reassembled_source' and (fragment or first_kind=='formula')))
        if disposition=='verified_duplicate':exempt=True
        primary=next((s for s in question if s[1]!=s[2]),question[0] if question else None)
        matched=[i for i,value in by_source.get(primary[0],{}).items() if covers(primary,value['question'])] if primary else []
        missing=[];role_changes=[]
        if not exempt:
            for role,required in [('question',question),('solution',solution)]:
                for span in required:
                    if covers(span,visible_by_role[role].get(span[0],[])):continue
                    other='solution' if role=='question' else 'question'
                    # AI can separate an original solution from the same
                    # question. Retaining that span under its own owner is a
                    # role correction, not a missing question or an implicit merge.
                    if matched and covers(span,[s for owner in matched for s in shown[owner][other]]):
                        role_changes.append(dict(block_id=span[0],role=other))
                    else:
                        missing.append(dict(role=role,block_id=span[0],start=span[1],end=span[2]))
        row=dict(unit_id=proposal['projection']['unit_ids'][0],block_id=origin,catalog_number=catalog or '',
                 owners=matched,missing_parts=missing,role_changes=role_changes,exempt=exempt)
        rows.append(row)
        required_parts.append(question+solution)
        if not exempt:
            for owner in matched:owners[owner].append(index)
    mixed=[dict(candidate=after[owner][1]['projection']['unit_ids'][0],unit_ids=[rows[i]['unit_id'] for i in indices])
           for owner,indices in owners.items() if len(indices)>1]
    for index,row in enumerate(rows):
        if row['exempt'] or not row['owners']:continue
        for span in required_parts[index]:
            received=[owner for owner,value in by_source.get(span[0],{}).items() if covers(span,value['question']+value['solution'])]
            if (received and not set(received).intersection(row['owners'])
                    and any(any(other!=index for other in owners[owner]) for owner in received)):
                row['missing_parts'].append(dict(block_id=span[0],start=span[1],end=span[2],
                                                 reason='题内来源被挂到另一道独立题'))
    mixed_ids={uid for group in mixed for uid in group['unit_ids']}
    conflicts=[row for row in rows if not row['exempt'] and (row['missing_parts'] or row['unit_id'] in mixed_ids)]
    return dict(conflicts=conflicts,mixed_candidates=mixed,tracked_questions=len(rows),
                role_changes=[dict(unit_id=row['unit_id'],parts=row['role_changes']) for row in rows if row['role_changes']])


def restore_question_structure(original,reviewed):
    """Restore only conflicted source ownership, retaining text corrections."""
    coverage=candidate_coverage(original,reviewed)
    conflicts=coverage['question_integrity']['conflicts']
    if not conflicts:return reviewed,dict(restored_questions=[],coverage=coverage)
    normalized=file_book(ExtractedExerciseText('','zip',canonical_book=original),name=original.book_name)
    units=exercise_units(normalized,unrestricted=True)
    blocks={b.block_id:b for b in normalized.blocks}
    affected={v['unit_id'] for v in conflicts}
    originals={b.block_id:b for b in original.blocks}
    shared={bid for unit in units if unit['unit_id'] not in affected for bid in unit['source_block_ids']}
    roots=set()
    for unit in units:
        if unit['unit_id'] not in affected:continue
        for bid in unit['source_block_ids']:
            if bid in shared and bid in unit.get('header_ids',[]):continue
            parent=blocks[bid].attributes.get('source_parent_id')
            roots.add(parent if parent in originals else bid.removeprefix('q-'))
    result=deepcopy(reviewed)
    keys=('structure_role','structure_unit_id','structure_unit_start','structure_unit_role',
          'structure_heading_level','structure_group_members','outline_toc')
    restored=[]
    for block in result.blocks:
        root=block.block_id
        while root not in originals and '@' in root:root=root.rsplit('@',1)[0]
        if root not in roots or root not in originals:continue
        old=originals[root]
        rejected=block.attributes.get('structure_review_receipt')
        for key in keys:
            block.attributes.pop(key,None)
            if key in old.attributes:block.attributes[key]=deepcopy(old.attributes[key])
        if block.block_id!=root and block.attributes.get('source_start',0):
            block.attributes['structure_unit_start']=False
        block.attributes['exercise_structure_restored']=dict(source_block_id=root,
            reason='题目来源遗漏或不同题被合并，已恢复本题原结构并保留文字修订',rejected_decision=rejected)
        restored.append(block.block_id)
    final=candidate_coverage(original,result)
    return result,dict(restored_questions=[v['unit_id'] for v in conflicts],restored_blocks=restored,
                       rejected_integrity=coverage['question_integrity'],coverage=final)
