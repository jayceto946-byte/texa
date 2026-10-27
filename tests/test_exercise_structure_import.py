"""Structural fixtures using the #047 image's layout/metadata and synthetic stems.

These prove source handling, not OCR accuracy or mathematical answer accuracy.
"""
from copy import deepcopy
import io
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
from backend.services.exercise_candidate_review import ExerciseCandidateReviewService, CandidateAdmissionError
from ingestion.document_ir import CanonicalBook, DocumentBlock, canonical_book_fingerprint
from memory.exercise_candidate_projection import content_hash, project_units, serialize_parts, source_registry
from memory.exercise_file_importer import ExtractedExerciseText
from memory.exercise_importer import analyze_candidate, attach_answers_by_number
from memory.exercise_structure import exercise_units
from memory.exercise_structure_examples import StructureExampleStore

SCOPE = dict(chapter='', page_start=None, page_end=None, source_mode='file')


def analyze(tmp_path, text, answer=None):
    store = ExerciseFileAnalysisStore(tmp_path)
    extracted, source_id, paired = store.create(ExtractedExerciseText(text, 'docx'), book_name='讲义',
        answer=ExtractedExerciseText(answer, 'docx') if answer else None)
    proposals = project_units(extracted.units, extracted.source_blocks, extracted.canonical_hash, SCOPE,
        learned=extracted.solution_markers, profile_version=extracted.profile_version, source_id=source_id)
    return store, extracted, proposals, paired


def item(proposal):
    return dict(origin_id='candidate', question_text=proposal['question_text'], answer=proposal['answer'],
                explanation=proposal['explanation'], candidate_context=dict(projection=deepcopy(proposal['projection']), review=None))


@pytest.mark.parametrize('label,role', [('解：', 'explanation'), ('解答:', 'explanation'), ('【解析】', 'explanation'),
    ('答案：', 'answer'), ('[答案]', 'answer'), ('参考答案：', 'answer'), ('解\n', 'explanation')])
def test_same_block_source_solution_has_exact_span_coverage(tmp_path, label, role):
    raw = '【例1】设函数满足给定条件，求其导数。\n' + label + '结果来自原文。'
    book = CanonicalBook('b', 'b', [DocumentBlock('u', 'paragraph', raw, ['第一章'], page_start=1, page_end=1)], 'v1')
    units = exercise_units(book)
    registry = source_registry(book, units, {'u'})
    proposal = project_units(units, registry, canonical_book_fingerprint(book), {**SCOPE, 'source_mode': 'examples'})[0]
    assert '结果来自原文' not in proposal['question_text']
    assert '结果来自原文' in proposal[role]
    p = proposal['projection']
    spans = sorted([span for values in p['parts'].values() for span in values], key=lambda s: s['start'])
    assert spans[0]['start'] == 0 and spans[0]['end'] == spans[1]['start'] and spans[-1]['end'] is None
    registry_map = {b['block_id']: b for b in registry}
    assert serialize_parts(p['parts']['question'], registry_map) == proposal['question_text']
    assert raw == book.blocks[0].text


def test_catalog_wins_over_repeated_exam_numbers_and_keeps_focus(tmp_path):
    _, extracted, proposals, _ = analyze(tmp_path, '二、矩阵\n#047 矩阵 → 伴随等于转置/本身 2005数三\n(12) 设矩阵满足给定条件，求参数。\n答案：A\n解析：由给定矩阵性质可得。\n#048 矩阵 → 不可逆的判定与证明 2006数三\n(12) 证明给定矩阵不可逆。\n解：这是原文的证明。')
    assert len(proposals) == 2
    assert [p['projection']['structure']['catalog_number'] for p in proposals] == ['#047', '#048']
    assert [p['projection']['structure']['original_number'] for p in proposals] == ['(12)', '(12)']
    assert proposals[0]['projection']['structure']['authored_focus'] == '矩阵 → 伴随等于转置/本身'
    assert proposals[0]['projection']['structure']['exam_source'] == '2005数三'
    assert '二、矩阵' in proposals[0]['projection']['structure']['classification_path']
    assert '#047' not in proposals[0]['question_text']
    assert proposals[0]['answer'] == '答案：A' and proposals[1]['explanation'] == '解：这是原文的证明。'
    service = ExerciseCandidateReviewService(file_provider=lambda sid, _: extracted)
    assert service.prepare('讲义', [item(proposals[0])])[0]['projection']['structure']['catalog_number'] == '#047'


def test_split_catalog_bar_uses_adjacent_focus_and_source(tmp_path):
    _, _, proposals, _ = analyze(tmp_path, '二、矩阵\n#047\n矩阵 → 伴随等于转置/本身\n2005数三\n(12) 设矩阵满足条件，求参数。\n答案：A')
    assert len(proposals) == 1
    assert proposals[0]['projection']['structure']['authored_focus'] == '矩阵 → 伴随等于转置/本身'
    assert proposals[0]['projection']['structure']['exam_source'] == '2005数三'
    assert proposals[0]['question_text'].startswith('(12)')


def test_explicit_focus_and_topic_hierarchy_are_source_metadata(tmp_path):
    _, _, proposals, _ = analyze(tmp_path, '二、矩阵\n2.1 可逆矩阵\n题型一 不可逆的判定与证明\n#045\n(12) 证明题目给定的矩阵不可逆。\n考点：不可逆的判定与证明\n解：这是资料提供的证明。\n题型二 伴随矩阵与转置\n#046\n(12) 根据给定条件，求矩阵的参数。')
    structure = proposals[0]['projection']['structure']
    assert structure['classification_path'] == ['二、矩阵', '2.1 可逆矩阵', '题型一 不可逆的判定与证明']
    assert '不可逆的判定与证明' in structure['authored_focus']
    assert '考点：' not in proposals[0]['question_text'] and '考点：' not in proposals[0]['explanation']
    assert proposals[1]['projection']['structure']['classification_path'] == ['二、矩阵', '2.1 可逆矩阵', '题型二 伴随矩阵与转置']


def test_partial_solution_proposal_remains_blocked_when_later_boundary_is_uncertain():
    blocks = [DocumentBlock('q', 'paragraph', '【例1】求给定函数在指定点的导数。', ['第一章']),
              DocumentBlock('s', 'paragraph', '解：根据定义可得所求结果。', ['第一章']),
              DocumentBlock('h', 'paragraph', '(1) 状态方程', ['第一章'], attributes={'mineru_type': 'paragraph_title'})]
    book = CanonicalBook('b', 'b', blocks, 'v1')
    units = exercise_units(book)
    registry = source_registry(book, units, {b.block_id for b in blocks})
    p = project_units(units, registry, canonical_book_fingerprint(book), {**SCOPE, 'source_mode': 'examples'})[0]
    assert p['explanation'].startswith('解：') and '解：' not in p['question_text']
    assert p['projection']['method'] == 'unresolved'
    assert any(i['code'] == 'boundary_uncertain' for i in p['issues'])


def test_separate_answers_use_scoped_identity_and_repeated_numbers_stay_unknown(tmp_path):
    _, _, proposals, paired = analyze(tmp_path, '一、矩阵\n1. 求给定矩阵的秩。\n二、积分\n1. 求给定函数的积分。',
        '一、矩阵\n1. 答案：2\n二、积分\n1. 答案：常数加原函数')
    assert paired == 2
    assert proposals[0]['answer'] == '答案：2'
    assert proposals[1]['answer'] == '答案：常数加原函数'
    _, _, ambiguous, paired = analyze(tmp_path, '1. 求第一个函数的值。\n1. 求第二个函数的值。', '1. 答案：2\n1. 答案：3')
    assert paired == 0 and all(not p['answer'] for p in ambiguous)
    assert all(any(i['code'] == 'answer_pairing_uncertain' for i in p['issues']) for p in ambiguous)


def test_end_of_document_answer_section_is_not_imported_as_new_questions(tmp_path):
    _, _, proposals, paired = analyze(tmp_path, '1. 求给定函数的导数。\n2. 求给定矩阵的秩。\n参考答案\n1. 答案：2x\n2. 答案：3')
    assert paired == 2 and len(proposals) == 2
    assert [p['answer'] for p in proposals] == ['答案：2x', '答案：3']


def test_no_label_solution_stays_uncertain_and_proof_instruction_stays_question(tmp_path):
    _, _, proposals, _ = analyze(tmp_path, '例题1 求函数在给定点的导数。\n由定义代入可得所求结果。')
    assert proposals[0]['projection']['method'] == 'unresolved'
    assert proposals[0]['explanation'] == ''
    ordinary = analyze_candidate('1. 请证明：给定矩阵满足所述等式。')
    assert ordinary.question_text.endswith('等式。') and not ordinary.explanation
    solved = analyze_candidate('1. 求函数的导数。\n解：由定义得结果。')
    assert solved.question_text == '1. 求函数的导数。' and solved.explanation == '解：由定义得结果。'
    instruction = analyze_candidate('1. 阅读材料并回答给定问题。\n分析：比较两个条件的差异。')
    assert '分析：' in instruction.question_text and instruction.explanation == ''


def test_native_file_blocks_keep_formula_table_and_required_figure(tmp_path):
    book = CanonicalBook('b', 'b', [
        DocumentBlock('h', 'heading', '二、矩阵', ['二、矩阵'], page_start=1, page_end=1),
        DocumentBlock('bar', 'heading', '#047 矩阵 → 参数判断 2005数三', ['二、矩阵'], page_start=1, page_end=1),
        DocumentBlock('q', 'paragraph', '(12) 根据图A和下表，计算给定矩阵的参数。', ['二、矩阵'], page_start=1, page_end=1),
        DocumentBlock('f', 'formula', r'\frac{1}{2}x=1', ['二、矩阵'], page_start=1, page_end=1),
        DocumentBlock('t', 'table', '| 参数 | 数值 |\n|---|---|\n| a | 2 |', ['二、矩阵'], page_start=1, page_end=1),
        DocumentBlock('fig', 'figure', '图A', ['二、矩阵'], page_start=1, page_end=1, attributes={'asset_id': 'asset-a'}),
        DocumentBlock('s', 'paragraph', '解：这是来源中的过程。', ['二、矩阵'], page_start=2, page_end=2),
    ], 'native-fixture')
    store = ExerciseFileAnalysisStore(tmp_path)
    e, sid, _ = store.create(ExtractedExerciseText('source', 'pdf', canonical_book=book), book_name='讲义')
    p = project_units(e.units, e.source_blocks, e.canonical_hash, SCOPE, source_id=sid)[0]
    assert '$$\n' in p['question_text'] and '| 参数 | 数值 |' in p['question_text']
    assert p['explanation'].startswith('解：')
    dep = next(d for d in p['projection']['dependencies'] if d['kind'] == 'figure')
    assert dep['asset_ids'] == ['asset-a'] and dep['requirement'] == 'required'
    assert next(b for b in e.source_blocks if b['block_id'] == 'q-s-0')['page_start'] == 2
    with pytest.raises(CandidateAdmissionError, match='必要输入'):
        ExerciseCandidateReviewService(file_provider=store.load).prepare('讲义', [item(p)])


def test_legacy_answer_pairing_never_last_wins_or_overwrites_source_solution():
    candidates = [analyze_candidate('1. 求第一个结果。'), analyze_candidate('1. 求另一个结果。')]
    assert attach_answers_by_number(candidates, '1. 答案：A\n1. 答案：B') == 0
    solved = analyze_candidate('1. 求给定结果。\n答案：C')
    assert attach_answers_by_number([solved], '1. 答案：D') == 0 and solved.answer == '答案：C'


def test_file_snapshot_is_scoped_and_replays_after_later_sample_changes(tmp_path):
    store, extracted, proposals, _ = analyze(tmp_path, '1. 求给定函数的导数。\n解：由定义得到结果。')
    candidate = item(proposals[0])
    with pytest.raises(ValueError, match='范围'):
        store.load(candidate['candidate_context']['projection']['source_id'], '另一教材')
    service = ExerciseCandidateReviewService(file_provider=store.load)
    assert service.prepare('讲义', [candidate])
    candidate['candidate_context']['projection']['structure']['catalog_number'] = '#999'
    with pytest.raises(CandidateAdmissionError, match='编排'):
        service.prepare('讲义', [candidate])
    import json
    source_id = proposals[0]['projection']['source_id']
    path = store.root / f'{source_id}.json'
    corrupted = json.loads(path.read_text())
    corrupted['source_blocks'][0]['text'] += '篡改'
    path.write_text(json.dumps(corrupted))
    with pytest.raises(ValueError, match='快照校验'):
        store.load(source_id, '讲义')


def test_explicit_sample_reused_on_unseen_document_requires_review_and_has_version(tmp_path):
    store, extracted, proposals, _ = analyze(tmp_path, '例题1 求给定函数的导数。\n演算过程：由定义得到结果。')
    p = proposals[0]['projection']
    solution = next(b for b in extracted.source_blocks if b['text'].startswith('演算过程'))
    # Equivalent to the source role UI: preserve all source spans and move this block.
    for spans in p['parts'].values():
        spans[:] = [s for s in spans if s['block_id'] != solution['block_id']]
    p['parts']['question'] = [s for s in p['parts']['unassigned']]
    p['parts']['unassigned'] = []
    p['parts']['explanation'] = [dict(block_id=solution['block_id'], start=0, end=None)]
    saved = StructureExampleStore(tmp_path).save(projection=p, registry={b['block_id']: b for b in extracted.source_blocks})
    assert saved['labels'] == ['演算过程']
    assert StructureExampleStore(tmp_path).save(projection=p, registry={b['block_id']: b for b in extracted.source_blocks}) == saved
    _, new, proposals, _ = analyze(tmp_path, '1. 求另一本资料的矩阵秩。\n演算过程：这是另一道题的原解。')
    assert proposals[0]['explanation'].startswith('演算过程')
    assert any(i['code'] == 'learned_boundary' for i in proposals[0]['issues'])
    assert proposals[0]['projection']['profile_version'] == saved['profile_version']
    with pytest.raises(CandidateAdmissionError, match='待核对'):
        ExerciseCandidateReviewService(file_provider=lambda *args: new).prepare('讲义', [item(proposals[0])])
    assert store.load(p['source_id'], '讲义').profile_version == ''  # old analysis is frozen


def docx(text):
    from xml.sax.saxutils import escape
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + ''.join('<w:p><w:r><w:t>' + escape(line) + '</w:t></w:r></w:p>' for line in text.splitlines()) + '</w:body></w:document>')
    return buf.getvalue()


def test_file_api_source_contract_persistence_and_confirmation_sample(tmp_path, monkeypatch):
    from backend.api import exercises as api
    from memory.exercise_bank import ExerciseBank
    import config
    monkeypatch.setattr(api, 'PROGRESS_PATH', tmp_path)
    monkeypatch.setattr(config, 'PROGRESS_PATH', tmp_path)
    monkeypatch.setattr(api, 'UPLOAD_DIR', tmp_path / 'uploads')
    bank = ExerciseBank(tmp_path / 'bank.db')
    monkeypatch.setattr(api, '_bank', lambda _: bank)
    monkeypatch.setattr(api, '_log_learning_event', lambda *args, **kwargs: None)
    app = FastAPI(); app.include_router(api.router)
    client = TestClient(app)
    response = client.post('/exercises/upload-analyze?book_name=讲义', data={'candidate_contract_version': '1'},
        files={'file': ('test.docx', docx('二、矩阵\n#047 矩阵 → 不可逆的判定与证明 2005数三\n(12) 证明给定矩阵不可逆。\n解：这是源文中的证明。'))}).json()
    assert response['success'], response
    candidate = response['data'][0]
    request = dict(question_text=candidate['question_text'], answer=candidate['answer'], explanation=candidate['explanation'],
        origin_id=candidate['id'], candidate_context=dict(projection=candidate['projection'], review=None))
    assert client.post('/exercises/structure-examples?book_name=讲义', json=request).status_code == 422
    request['candidate_context']['review'] = dict(content_hash=content_hash({**request, 'projection': candidate['projection']}), resolutions=[])
    assert client.post('/exercises/structure-examples?book_name=讲义', json=request).status_code == 200
    committed = client.post('/exercises/candidates/batch-add?book_name=讲义', json=dict(candidate_contract_version=1, exercises=[request])).json()
    assert committed['success'] and committed['data'][0]['source_structure']['catalog_number'] == '#047'
    assert committed['data'][0]['explanation'].startswith('解：')
    assert bank.get(committed['data'][0]['id']).extra_fields['source_structure']['exam_source'] == '2005数三'
    assert len(bank.list_all(search_kw='不可逆的判定与证明')) == 1
    assert len(bank.list_all(search_kw='#047')) == 1
    repeated = client.post('/exercises/candidates/batch-add?book_name=讲义', json=dict(candidate_contract_version=1, exercises=[request])).json()
    assert repeated['count'] == 0 and repeated['candidate_receipts'] == []
    assert repeated['skipped_candidate_receipts'][0]['projection']['structure']['catalog_number'] == '#047'
    assert repeated['skipped_candidate_receipts'][0]['exercise_id'] == committed['data'][0]['id']
    monkeypatch.setattr(api, 'extract_exercise_text', lambda _: ExtractedExerciseText(
        '1. 求第一个给定函数的导数。\n2. 求另一个给定函数的导数。', 'pdf', warnings=['部分扫描页未提取到正文']))
    limited = client.post('/exercises/upload-analyze?book_name=讲义', data={'candidate_contract_version': '1', 'limit': '1'},
        files={'file': ('limited.docx', docx('placeholder'))}).json()
    assert limited['success'] and limited['summary']['total'] == 1 and limited['summary']['source_units'] == 2
    assert '部分扫描页未提取到正文' in limited['extract']['warnings']
    assert any('本次上限 1' in warning for warning in limited['extract']['warnings'])
