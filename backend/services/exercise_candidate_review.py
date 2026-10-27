"""Authoritative v1 candidate admission; no FastAPI DTOs or eager IO."""
from copy import deepcopy

from memory.exercise_candidate_projection import (
    ROLES, INLINE_SOLUTION, PRIOR_CONTEXT, canonical_json, content_hash, figure_labels, project_units,
)


class CandidateAdmissionError(ValueError):
    def __init__(self, origin_id, message, *, status=422, issues=None):
        super().__init__(message)
        self.detail = {'origin_id': origin_id, 'message': message, 'issues': issues or []}
        self.status = status


def _validate_spans(projection, registry, expected_ids, origin):
    intervals = {}
    for role in ROLES:
        for span in projection['parts'][role]:
            bid, start, end = span['block_id'], span['start'], span['end']
            if bid not in expected_ids or bid not in registry:
                raise CandidateAdmissionError(origin, '来源块不属于本候选或所选教材范围')
            length = len(registry[bid]['text'])
            end = length if end is None else end
            if start > end or end > length or (start == end and length):
                raise CandidateAdmissionError(origin, '来源span无效（下标须为Unicode码点）')
            intervals.setdefault(bid, []).append((start, end))
    if set(intervals) != expected_ids:
        raise CandidateAdmissionError(origin, '来源覆盖不完整，不得删除原块')
    for bid, spans in intervals.items():
        if not registry[bid]['text'] and len(spans) != 1:
            raise CandidateAdmissionError(origin, '空资源块必须只映射一次')
        cursor = 0
        for start, end in sorted(spans):
            if start != cursor:
                raise CandidateAdmissionError(origin, '来源span重叠或遗漏')
            cursor = end
        if cursor != len(registry[bid]['text']):
            raise CandidateAdmissionError(origin, '来源span未覆盖原文')


def validate_candidate(item, proposals, registry):
    origin = item['origin_id']
    context = item.get('candidate_context')
    if item.get('image_path'):
        raise CandidateAdmissionError(origin, '此合同不接受题库图片附件路径')
    if not context or not origin or not item['question_text'].strip():
        raise CandidateAdmissionError(origin, 'v1候选需要非空题干、origin_id及candidate_context')
    p, review = context['projection'], context.get('review')
    ids = p['unit_ids']
    if len(ids) != len(set(ids)):
        raise CandidateAdmissionError(origin, '来源单元重复')
    matched = [v for v in proposals if set(v['projection']['unit_ids']).intersection(ids)]
    ordered = [uid for v in matched for uid in v['projection']['unit_ids']]
    positions = [proposals.index(v) for v in matched]
    if ordered != ids or any(n != positions[0] + i for i, n in enumerate(positions)):
        raise CandidateAdmissionError(origin, '只能使用同范围相邻且完整的来源单元')
    if not matched:
        raise CandidateAdmissionError(origin, '来源单元不存在')
    if any(p.get(key) != matched[0]['projection'].get(key) for key in ('structure', 'profile_version', 'source_id')):
        raise CandidateAdmissionError(origin, '编排信息或结构样例版本与来源不一致，请重新分析')
    catalogs = {v['projection']['structure']['catalog_number'] for v in matched if v['projection'].get('structure', {}).get('catalog_number')}
    if len(catalogs) > 1:
        raise CandidateAdmissionError(origin, '不同编排号的题目不能合并，请分别保留来源与考点')
    focuses = {v['projection']['structure']['authored_focus'] for v in matched if v['projection'].get('structure', {}).get('authored_focus')}
    if len(focuses) > 1:
        raise CandidateAdmissionError(origin, '不同编者考点的题目不能合并，请分别保留来源')
    expected_ids = {s['block_id'] for v in matched for spans in v['projection']['parts'].values() for s in spans}
    _validate_spans(p, registry, expected_ids, origin)
    value = {**item, 'projection': p}
    if review and review['content_hash'] != content_hash(value):
        raise CandidateAdmissionError(origin, '确认版本已失效，请重新核对当前正文', status=409)
    base_issues = [i for v in matched for i in v['issues'] if i['category'] == 'content']
    issues = {i['key']: i for i in base_issues}
    edited = p['method'] == 'user_edited'
    if edited:
        issues['edited_content:'] = dict(key='edited_content:',code='edited_content',category='content',block_ids=[],dependency_id=None)
    else:
        if len(matched) != 1 or p != matched[0]['projection']:
            raise CandidateAdmissionError(origin, '自动提案映射已改变，请按人工编辑合同校对')
        if any(item[key] != matched[0][key] for key in ('question_text','answer','explanation')):
            raise CandidateAdmissionError(origin, '正文与来源投影不一致，请明确校对编辑后的版本')
    resolutions = {r['issue_key']:r['decision'] for r in (review or {}).get('resolutions', [])}
    if len(resolutions) != len((review or {}).get('resolutions', [])) or set(resolutions) - set(issues):
        raise CandidateAdmissionError(origin, '确认引用了未知或重复问题')
    if edited and (not review or resolutions.get('edited_content:') != 'corrected'):
        raise CandidateAdmissionError(origin, '编辑、拆分或合并后需确认本题当前结构')
    if edited:
        from memory.exercise_structure import split_roles
        if split_roles(dict(block_id='edited', text=item['question_text']), first=True)[0]:
            raise CandidateAdmissionError(origin, '题干仍含明确解答标记，请先分离到答案或解析')
    # Resource identities are replayed from IR, never accepted from client paths or flags.
    base_deps = {d['id']:d for v in matched for d in v['projection']['dependencies']}
    deps = {d['id']:d for d in p['dependencies']}
    if len(deps) != len(p['dependencies']) or set(deps) != set(base_deps):
        raise CandidateAdmissionError(origin, '资源依赖缺失或未知')
    for did, base in base_deps.items():
        dep = deps[did]
        if any(dep[k] != base[k] for k in ('kind','label','block_ids','asset_ids')):
            raise CandidateAdmissionError(origin, '资源身份不匹配')
        if base['requirement'] == 'required' and base['kind'] in ('figure','prior_context'):
            key = 'missing_required_input:' + did
            decision = resolutions.get(key)
            if not edited or not review:
                raise CandidateAdmissionError(origin, '必要输入尚不可用于独立练习', issues=[issues.get(key, {})])
            if base['kind'] == 'figure':
                # F3 has no exercise attachment contract. A client cannot assert embedded pixels.
                if base['label'] in figure_labels(item['question_text']) or dep['requirement'] != 'reference' or decision != 'not_applicable':
                    raise CandidateAdmissionError(origin, '必要图片尚无正式题库读图合同，不能确认绕过')
            elif (PRIOR_CONTEXT.search(item['question_text'])
                  or dep['resolution'] != 'embedded' or decision != 'corrected'):
                raise CandidateAdmissionError(origin, '请把前文必要条件补入独立题干')
    # Newly introduced references cannot be smuggled into an edited question.
    if figure_labels(item['question_text']):
        raise CandidateAdmissionError(origin, '题干仍引用独立练习无法交付的图片')
    original_body = {key: '\n\n'.join(v[key] for v in matched if v[key]) for key in ('question_text','answer','explanation')}
    body_changed = any(item[key] != original_body[key] for key in original_body)
    unresolved = []
    for key, signal in issues.items():
        code, decision = signal['code'], resolutions.get(key)
        if code == 'missing_required_input':
            continue  # checked independently above, cannot be cleared by generic review
        if not review or not decision:
            unresolved.append(signal)
        elif code == 'edited_content':
            continue
        elif decision == 'corrected':
            if not edited or not body_changed or (code == 'solution_in_stem' and INLINE_SOLUTION.search(item['question_text'])):
                unresolved.append(signal)
        elif decision not in ('not_applicable','source_checked') or code not in ('solution_in_stem','boundary_uncertain','dependency_uncertain','formula_review','learned_boundary'):
            unresolved.append(signal)
    if p['method'] == 'unresolved':
        unresolved.append(dict(code='boundary_uncertain',key='unresolved_projection'))
    if unresolved:
        raise CandidateAdmissionError(origin, '仍有内容问题待核对', issues=unresolved)
    return dict(origin_id=origin, projection={k:deepcopy(p[k]) for k in ('version','canonical_hash','unit_ids','method','parts','structure','profile_version','source_id')},
                body_hash=content_hash(item, include_projection=False), review_kind='user_confirmed' if review else 'system_proposed')


class ExerciseCandidateReviewService:
    def __init__(self, *, extract_provider=None, file_provider=None):
        if extract_provider is None:
            from memory.textbook_exercise_importer import extract_textbook_exercise_text
            extract_provider = extract_textbook_exercise_text
        self.extract_provider = extract_provider
        self.file_provider = file_provider

    def replay(self, book_name, projection):
        if projection.get('source_id'):
            if projection['scope']['source_mode'] != 'file':
                raise ValueError('文件来源模式不一致')
            if self.file_provider is None:
                from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
                from config import PROGRESS_PATH
                extracted = ExerciseFileAnalysisStore(PROGRESS_PATH).load(projection['source_id'], book_name)
            else:
                extracted = self.file_provider(projection['source_id'], book_name)
        else:
            if projection['scope']['source_mode'] == 'file':
                raise ValueError('文件来源身份缺失')
            extracted = self.extract_provider(book_name, **projection['scope'], candidate_contract_version=1,
                                             structure_profile_version=projection.get('profile_version', ''))
        proposals = project_units(extracted.units, extracted.source_blocks, extracted.canonical_hash, projection['scope'],
                                 learned=extracted.solution_markers, profile_version=extracted.profile_version,
                                 source_id=projection.get('source_id'))
        return extracted, proposals

    def prepare(self, book_name, items):
        if not items or len(items) > 500:
            raise CandidateAdmissionError('', '请选择1至500道候选')
        cache, receipts, origins = {}, [], set()
        if len({canonical_json(item.get('candidate_context', {}).get('projection', {}).get('scope')) for item in items if item.get('candidate_context')}) > 1:
            raise CandidateAdmissionError('', '一次提交必须保持同一教材分析范围')
        for item in items:
            origin = item.get('origin_id','')
            context = item.get('candidate_context')
            if not context or not origin or origin in origins:
                raise CandidateAdmissionError(origin, '候选身份缺失或重复')
            origins.add(origin)
            projection = context['projection']
            if type(projection.get('version')) is not int or projection['version'] != 1:
                raise CandidateAdmissionError(origin, '未知候选合同版本')
            scope = projection['scope']
            key = canonical_json([scope, projection.get('source_id'), projection.get('profile_version', '')])
            if key not in cache:
                try:
                    extracted, proposals = self.replay(book_name, projection)
                except (ValueError, FileNotFoundError) as exc:
                    raise CandidateAdmissionError(origin, str(exc), status=409) from exc
                cache[key] = (extracted, proposals)
            extracted, proposals = cache[key]
            if extracted.canonical_hash != projection['canonical_hash']:
                raise CandidateAdmissionError(origin, '教材版本已变化，请重新分析', status=409)
            receipts.append(validate_candidate(item, proposals, {b['block_id']:b for b in extracted.source_blocks}))
        return receipts
