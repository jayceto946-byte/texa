"""Page work packages and local source additions for the shared exercise review.

The inventory is model observation, never an independent completeness verdict.
All accepted text/figures return to Canonical IR and the existing projection.
"""
from copy import deepcopy
import json
import math
import re

from ingestion.document_ir import DocumentBlock
from ingestion.document_structure import block_role
from ingestion.heading_policy import PROBLEM_START, numeric_data_row
from ingestion.source_page_coverage import mark_page_coverage


PAGE_PROMPT = '''
本次按原页审阅，而非仅编辑旧候选。先阅读完整页面和阅读顺序，检查未被OCR识别的整题、选项、子问、公式、表格和附图。
题号跳跃只是疑点，不要求连续编号。被误标目录/章节/批注的来源仍可恢复为题目。没有原书答案也保留题目，不解题。
同一次返回已有edits/blocks/splits/metadata和下面两个字段；不要重抄已正确的来源：
"additions":[{"local_id":"n1","page":1,"image_ref":"original-page:1","type":"paragraph|formula|table|figure",
"text":"原页明确可见而OCR完全缺失的局部内容","after_id":"本页已有块或本批新增块ID",
"unit_start":true,"unit_id":"已有或新增题干起点ID","unit_role":"question|answer|explanation|context",
"bbox":[0.1,0.2,0.8,0.6],"reason":"漏识内容"}],
"page_inventory":[{"page":1,"status":"reviewed|blank|unreadable","questions":[
{"start_id":"题干起点ID","number":"原页题号，可空","source_ids":["本页属于该题的来源ID"],
"parts":{"stem":"present|missing|unknown|not_applicable","options":"present|missing|unknown|not_applicable",
"subquestions":"present|missing|unknown|not_applicable","figures_tables":"present|missing|unknown|not_applicable",
"original_solution":"present|missing|unknown|not_applicable"}}]}]。
local_id只在本批有效。只有实际提供original-page原图的页可新增内容；裁片不等于完整原页。
after_id也可换为before_id，二者只选一个。跨页续文unit_id指向上下文中的原题。新增内容应分为题干、选项/子问、公式、图表、原解，不将整页塞入一个替换。
bbox仅在能确定真实原页区域时填写，为整页归一化xyxy；定位不足可省略，程序保留整页来源待人工定位，不能猜框。
figure保留真实图像范围，不能用描述文字代替原图。新增整题unit_start=true；题内补录unit_start=false且指定unit_id。
page_inventory列出原页上的题目（包括旧候选里不存在的题）及其来源；未确定的部分写unknown。不属于题目的原页可questions=[]。
原书没有提供答案时original_solution=not_applicable，不视为题干缺失。需要恢复已有误分类题时同时返回blocks修正角色/题目起点，清单本身不修改结构。
blank仅用于原页确实空白。该清单是审阅观察，不是无漏题证明；无法确认之处写unresolved。上下文只可引用归属，不可修改。
'''

PARTS = ('stem', 'options', 'subquestions', 'figures_tables', 'original_solution')
PART_STATES = {'present', 'missing', 'unknown', 'not_applicable'}


def page_packages(book):
    """Each selected page is editable once; join known continuations up to two pages."""
    prepared = mark_page_coverage(deepcopy(book))
    pages = sorted({r['page'] for r in prepared.source_metadata.get('source_page_coverage', [])}
                   or {b.page_start for b in prepared.blocks if b.page_start})
    from memory.exercise_structure import exercise_units
    from ingestion.document_workflows import EXAMPLE_START
    source = deepcopy(book)
    source.blocks = [b for b in source.blocks if not b.attributes.get('missing_source_page')]
    spans = [(u.get('page_start'), u.get('page_end')) for u in exercise_units(source, unrestricted=True)]
    packages = []
    for page in pages:
        crossing = any(start and end and start < page <= end for start, end in spans)
        first = next((b for b in prepared.blocks if b.page_start == page and not b.attributes.get('missing_source_page')), None)
        continuation = first and not first.attributes.get('structure_unit_start') and first.block_type != 'heading' and not EXAMPLE_START.match(first.text) and not (
            PROBLEM_START.match(first.text) and not numeric_data_row(first.text))
        if packages and len(packages[-1]) < 2 and page == packages[-1][-1]+1 and (crossing or continuation):
            packages[-1].append(page)
        else:
            packages.append([page])
    return packages


def carry_boundary_proposals(book, response, aliases, editable, previous, request_key):
    """Carry read-only structural suggestions to their owning page, never apply them."""
    by_id = {b.block_id: b for b in book.blocks}
    confirmed = {aliases.get(v.get('block_id')) for key in ('blocks', 'splits') for v in response.get(key, [])
                 if aliases.get(v.get('block_id')) in editable}
    remaining = {p['block_id']: p for p in previous if p['block_id'] not in confirmed}
    for item in response.get('blocks', []):
        bid = aliases.get(item.get('block_id'))
        if bid not in by_id or bid in editable:
            continue
        decision = {k:deepcopy(item[k]) for k in ('unit_start', 'unit_role', 'unit_starts_with', 'reason') if k in item}
        if item.get('unit_id') in aliases:
            decision['unit_id'] = aliases[item['unit_id']]
        if decision:
            remaining[bid] = dict(block_id=bid, page=by_id[bid].page_start, request_key=request_key, decision=decision)
    return list(remaining.values())


def page_input(book, pages, *, asset_root=None, pdf_path=None, evidence=None, boundary_proposals=()):
    from backend.services.document_structure_review import review_input
    from memory.exercise_structure import ORIGINAL, question_metadata, solution_markers
    neighbours = {p+d for p in pages for d in (-1, 1)} - set(pages)
    editable = [b for b in book.blocks if b.page_start in pages]
    context = [b for b in book.blocks if b.page_start in neighbours]
    aliases = {f'b{i}': b.block_id for i, b in enumerate(book.blocks) if b in editable or b in context}
    short = {v:k for k,v in aliases.items()}
    def row(b):
        number = ORIGINAL.match(b.text)
        return dict(id=short[b.block_id], text=b.text, page=b.page_start, type=b.block_type,
            role=block_role(b), path=b.section_path, bbox=b.bbox,
            geometry={k:b.attributes[k] for k in ('bbox_units', 'bbox_space', 'bbox_format', 'source_block_index') if k in b.attributes},
            current_unit=short.get(b.attributes.get('structure_unit_id')),
            signals=dict(number=(number.group(1) or number.group(2)) if number else '',
                solution_markers=solution_markers(b.text), metadata=question_metadata(b.text,b.section_path),
                options=[dict(label=m.group(1),start=m.start()) for m in re.finditer(r'(?:^|[\s（(])([A-D])[.、．)）]',b.text)],
                subquestions=[dict(label=m.group(1),start=m.start()) for m in re.finditer(r'[（(](\d+)[）)]',b.text)]),
            proposed_question_start=bool(PROBLEM_START.match(b.text)) and not numeric_data_row(b.text))
    observations = [o for o in (evidence.observations if evidence else [])
                    if not o.get('text_ref') and o.get('producer_type') != 'bookmark'
                    and any(r['physical_page'] in pages for r in o['refs'])]
    preview = deepcopy(book)
    preview.blocks = editable
    visual, _, coverage = review_input(preview, pages, asset_root=asset_root, pdf_path=pdf_path, include_formula_crops=True)
    images = [dict(id=f'original-page:{p}', page=p) for p in coverage['full_page_images']]
    boundary_hints = []
    for proposal in boundary_proposals:
        if proposal['page'] not in pages or proposal['block_id'] not in short:
            continue
        decision = deepcopy(proposal['decision'])
        if 'unit_id' in decision:
            if decision['unit_id'] not in short:
                continue
            decision['unit_id'] = short[decision['unit_id']]
        boundary_hints.append(dict(block_id=short[proposal['block_id']], **decision))
    payload = dict(review_pages=pages, blocks=[row(b) for b in editable], context_blocks=[row(b) for b in context],
        boundary_proposals=boundary_hints,
        excluded_observations=observations, original_images=images,
        source_completeness='unknown', omitted_image_blocks=[short.get(b,b) for b in coverage['omitted_image_blocks']])
    content = [dict(type='text', text=json.dumps(payload, ensure_ascii=False, separators=(',', ':'))), *visual[1:]]
    for part in content[1:]:
        if part['type'] == 'text':
            for bid, alias in sorted(short.items(), key=lambda p:len(p[0]), reverse=True):
                part['text'] = part['text'].replace('区域裁片 '+bid+'，', '区域裁片 '+alias+'，')
    visual_ids = {b.block_id for b in editable if b.page_start in coverage['full_page_images']} | set(coverage['image_block_ids'])
    return content, aliases, visual_ids, coverage


def valid_bbox(value):
    return (isinstance(value, list) and len(value) == 4 and all(type(x) in (int, float) and math.isfinite(x) for x in value)
            and 0 <= value[0] < value[2] <= 1 and 0 <= value[1] < value[3] <= 1)


def apply_additions(book, response, aliases, pages, full_pages, *, asset_root=None, pdf_path=None):
    """Apply local insertions without replacing OCR or accepting model filesystem paths."""
    from backend.services.exercise_page_recovery import page_figure_asset
    pending, receipts = [], []
    by_id = {b.block_id:b for b in book.blocks}
    # Reserve IDs first so a figure/continuation may refer to a later new stem.
    additions = response.get('additions', [])
    local_ids = [v.get('local_id') for v in additions]
    for item in additions:
        local, page = item.get('local_id'), item.get('page')
        if (not isinstance(local, str) or not re.fullmatch(r'n[\w-]{0,63}', local) or local_ids.count(local) != 1
                or local in aliases or type(page) is not int or page not in pages or page not in full_pages
                or item.get('image_ref') != f'original-page:{page}'):
            pending.append(dict(reason='补录缺少本批原页依据或本地标识冲突，未采用')); continue
        aliases[local] = f'visual-p{page}-{local}'
    reserved = {item['local_id'] for item in additions if item.get('local_id') in aliases and aliases[item['local_id']].startswith('visual-p')}
    accepted, after_tail = set(), {}
    for item in additions:
        local = item.get('local_id')
        if local not in reserved: continue
        bid, page = aliases[local], item['page']
        kind, text = item.get('type'), item.get('text')
        role, owner = item.get('unit_role', 'question'), aliases.get(item.get('unit_id'))
        start = item.get('unit_start', False)
        bbox = item.get('bbox')
        after, before = item.get('after_id'), item.get('before_id')
        anchor = by_id.get(aliases.get(after or before))
        if (kind not in {'paragraph','formula','table','figure'} or not isinstance(text, str) or (not text.strip() and kind != 'figure')
                or role not in {'question','answer','explanation','context'} or type(start) is not bool
                or start and role != 'question' or not start and (not owner or owner==bid)
                or bbox is not None and not valid_bbox(bbox)
                or after and before or (after or before) and (anchor is None or anchor.page_start != page)):
            pending.append(dict(page=page, reason='补录内容、归属或页内位置无法对齐，未采用')); continue
        if bid in by_id:
            pending.append(dict(page=page, reason='补录来源标识已存在，未重复插入')); continue
        path = list(anchor.section_path) if anchor else next((list(b.section_path) for b in book.blocks if b.page_start==page), [book.book_name])
        attrs = dict(structure_role='exercise' if role=='question' else 'solution' if role in {'answer','explanation'} else 'body',
            structure_unit_start=start, structure_unit_role=role,
            visual_source=dict(image_ref=item['image_ref'], page=page, bbox=bbox, location='region' if bbox else 'page'),
            original_ocr_text='[OCR未识别此片段]',
            text_corrections=[dict(find='', replace=text, reason=item.get('reason') or '原页局部补录')])
        if owner and not start: attrs['structure_unit_id'] = owner
        if not bbox:
            pending.append(dict(page=page, block_id=bid, reason='已按原页补录，具体区域待人工定位'))
        if anchor is None:
            pending.append(dict(page=page, block_id=bid, reason='已保留原页来源，页内阅读顺序待人工核对'))
        if kind == 'figure':
            attrs.update(page_figure_asset(pdf_path, page, bbox, asset_root) if bbox and asset_root else dict(asset_status='missing'))
            if attrs['asset_status'] != 'ready': pending.append(dict(page=page, block_id=bid, reason='补录附图尚无可用原页裁片'))
        block = DocumentBlock(bid, kind, text, path, page_start=page, page_end=page, bbox=bbox,
            source_kind='vision_transcription', review_status='source_review_pending',
            attributes={**attrs, 'bbox_units':'normalized', 'bbox_format':'xyxy', 'bbox_space':'page'})
        insertion_anchor = after_tail.get(anchor.block_id, anchor) if after else anchor
        position = book.blocks.index(insertion_anchor) + bool(after) if anchor else next((i for i,b in enumerate(book.blocks) if (b.page_start or 0)>page),len(book.blocks))
        book.blocks.insert(position, block); by_id[bid]=block; accepted.add(local)
        if after: after_tail[anchor.block_id]=block
        receipts.append(dict(block_id=bid, page=page, image_ref=item['image_ref'], bbox=bbox, reason=item.get('reason') or '原页局部补录'))
    # Reject only additions whose owner was itself rejected; retain other pages/questions.
    invalid = {aliases[k] for k in reserved-accepted}
    while invalid:
        affected = [b for b in book.blocks if b.block_id in {r['block_id'] for r in receipts} and b.attributes.get('structure_unit_id') in invalid]
        if not affected: break
        invalid.update(b.block_id for b in affected)
        book.blocks = [b for b in book.blocks if b not in affected]
        for b in affected: pending.append(dict(page=b.page_start, block_id=b.block_id, reason='所属新增题干未采用，补录保留在请求回执中'))
    receipts = [r for r in receipts if r['block_id'] not in invalid]
    for key in reserved:
        if aliases[key] not in {r['block_id'] for r in receipts}: aliases.pop(key, None)
    return receipts, pending


def record_inventory(book, response, aliases, pages, full_pages):
    """Track model page observations separately from independent source accounting."""
    from backend.services.import_semantic_review import _review_parts
    pending, rows = [], []
    inventory = response.get('page_inventory', [])
    for page in pages:
        matches = [r for r in inventory if r.get('page') == page]
        status = matches[0].get('status') if len(matches)==1 else 'unknown'
        if not isinstance(status,str) or status not in {'reviewed','blank','unreadable'}: status='unknown'
        if page not in full_pages: status='unknown'
        questions, assigned = [], set()
        for item in (matches[0].get('questions', []) if len(matches)==1 else []):
            targets = _review_parts(book, aliases.get(item.get('start_id')))
            if len(targets)>1: targets=[b for b in targets if b.attributes.get('structure_unit_start')]
            sources = [b for key in item.get('source_ids', []) for b in _review_parts(book, aliases.get(key))]
            if len(targets)!=1 or not sources or any(b.page_start!=page for b in sources):
                pending.append(dict(page=page, reason='页面题目清单不能对齐来源，保留待核对')); continue
            target = targets[0]
            parts = {k:item.get('parts', {}).get(k, 'unknown') for k in PARTS}
            parts = {k:v if isinstance(v,str) and v in PART_STATES else 'unknown' for k,v in parts.items()}
            target.attributes.setdefault('exercise_visual_inventory', []).append(dict(page=page, parts=parts))
            assigned.update(b.block_id for b in sources)
            questions.append(dict(block_id=target.block_id, number=str(item.get('number') or ''), parts=parts, source_block_ids=[b.block_id for b in sources]))
            if any(v in {'unknown','missing'} for v in parts.values()):
                pending.append(dict(page=page, block_id=target.block_id, reason='本题仍有缺失或未确定的组成部分'))
        body = [b for b in book.blocks if b.page_start==page and not b.attributes.get('missing_source_page')]
        if status=='blank' and any(b.text.strip() for b in body):
            status='unknown'; pending.append(dict(page=page, reason='页面判空与保留来源冲突'))
        if status in {'unknown','unreadable'}:
            pending.append(dict(page=page, reason='原页内容审阅尚未完成'))
        # A parsed/recovered page only has source text. It has no completeness guarantee.
        coverage = next((r for r in book.source_metadata.get('source_page_coverage',[]) if r['page']==page), None)
        if coverage and (body or status=='blank'):
            if status=='blank': coverage['status']='blank'
            elif coverage['status'] in {'missing','unreadable'}: coverage['status']='recovered'
            for b in book.blocks:
                if b.page_start==page and b.attributes.get('missing_source_page'):
                    b.attributes.update(structure_role='reference', structure_review_reason='已转录原页或原页为空', ocr_quality_confirmed=True)
        elif coverage:
            coverage['status']='unreadable'; pending.append(dict(page=page, reason='本页仍无可用正文'))
        unexplained = [b.block_id for b in body if block_role(b) not in {'toc','front_matter','annotation','reference','overview'}
                       and b.block_type!='heading' and b.block_id not in assigned]
        if unexplained: pending.append(dict(page=page, reason='页面仍有来源未对应到题目清单'))
        rows.append(dict(page=page, status=status, questions=questions, unexplained_source_ids=unexplained,
            completeness_verified=False, basis='model_page_observation'))
    return rows, pending


def inventory_projection_coverage(book, rows):
    """Independently check whether observed questions actually enter the shared projection."""
    from backend.services.exercise_file_analysis import file_book, ANSWER_HEADING
    from memory.exercise_file_importer import ExtractedExerciseText
    from memory.exercise_structure import exercise_units
    normalized = file_book(ExtractedExerciseText('', 'zip', canonical_book=book), name=book.book_name)
    units = exercise_units(normalized, unrestricted=True)
    if book.source_metadata.get('review_source_mode')=='examples': units=[u for u in units if u['kind']=='example']
    units = [u for u in units if not any(ANSWER_HEADING.match(p) for p in u['section_path'])]
    normalized_ids = {bid for u in units for bid in u['source_block_ids']}
    projected = {b.attributes.get('source_parent_id',b.block_id) for b in normalized.blocks if b.block_id in normalized_ids}
    blocks = {b.block_id:b for b in book.blocks}
    pending = []
    for row in rows:
        for item in row['questions']:
            bid = item['block_id']
            anchor = blocks.get(bid)
            owner = anchor.attributes.get('structure_duplicate_of') if anchor else None
            # Independent answer units remain separate unless actually paired.
            linked = anchor.attributes.get('structure_unit_id') if anchor else None
            if bid not in projected and owner not in projected and linked not in projected:
                pending.append(dict(page=row['page'],block_id=bid,reason='原页清单中的题目尚未生成候选，请核对题目边界或归属'))
    return dict(observed_questions=len({q['block_id'] for r in rows for q in r['questions']}),
        projected_questions=len(units),unprojected=pending,completeness_verified=False)
