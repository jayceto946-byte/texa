"""Question/solution continuity through review, saved sources and local rebuild."""
import json
from copy import deepcopy

import fitz
import pytest

from backend.services.exercise_file_analysis import ExerciseFileAnalysisStore
from backend.services.exercise_review_coverage import candidate_coverage
from backend.services.exercise_visual_review import page_packages
from backend.services.import_semantic_review import _edits, _prepare_roles, _structure, run_semantic_review
from ingestion.document_ir import CanonicalBook, DocumentBlock
from memory.exercise_candidate_projection import project_units
from memory.exercise_file_importer import ExtractedExerciseText


def block(bid, text, kind='paragraph', page=1, **attributes):
    return DocumentBlock(bid, kind, text, ['第一章'], page_start=page, page_end=page,
                         source_kind='mineru', attributes=attributes)


def book(*blocks):
    return CanonicalBook('fixture', 'mineru', list(blocks), 'fixture',
                         source_page_count=max(b.page_start for b in blocks))


def project(store, source):
    extracted, sid, _ = store.create(ExtractedExerciseText('', 'zip', canonical_book=source), book_name=source.book_name)
    return project_units(extracted.units, extracted.source_blocks, extracted.canonical_hash,
                         dict(source_mode='file', chapter='', page_start=None, page_end=None), source_id=sid), sid


def bodies(proposals):
    return [(p['question_text'], p['answer'], p['explanation']) for p in proposals]


def test_sparse_solution_roles_survive_annotations_formulas_and_local_rebuild(tmp_path):
    source = book(
        block('q', '【例1】求函数的导数，并说明理由。', 'example', learning_unit_id='q',
              structure_role='exercise', structure_unit_start=True, structure_unit_role='question'),
        block('start', '解（方法一） 直接法', structure_role='solution', structure_unit_id='q', structure_unit_role='explanation'),
        block('proof', '根据导数定义，得到以下结果。'),
        block('note', '旁边的手写批注', structure_role='annotation'),
        block('formula', r'f^{\prime}(x)=2x', 'formula', page=2),
        block('tail', '因此原点的导数等于零。', 'example', page=2, learning_unit_id='q'),
        block('next', '【例2】求另一个函数的积分。', 'example', page=2, learning_unit_id='next'),
    )
    source.source_metadata['exercise_scope_policy'] = 'all'
    store = ExerciseFileAnalysisStore(tmp_path)
    proposals, sid = project(store, source)
    assert len(proposals) == 2
    first = proposals[0]
    assert first['question_text'] == source.blocks[0].text
    assert all(s in first['explanation'] for s in ('直接法', '根据导数定义', '2x', '原点的导数等于零'))
    assert '手写批注' not in ''.join(bodies(proposals)[0])
    rebuilt = store.load(store.rebuild(sid, source.book_name), source.book_name)
    replay = project_units(rebuilt.units, rebuilt.source_blocks, rebuilt.canonical_hash, first['projection']['scope'])
    assert bodies(replay) == bodies(proposals)
    assert store.load(sid, source.book_name).canonical_hash == first['projection']['canonical_hash']


@pytest.mark.parametrize('answer', ['A', 'C'])
def test_printed_choice_answer_is_moved_without_accepting_a_deletion(tmp_path, answer):
    text = f'1. 以下哪个结论成立？\n(A) 条件甲。 (B) 条件乙。\n(C) 条件丙。 (D) 条件丁。 ({answer})'
    source = book(block('q', text, structure_unit_start=True, structure_unit_role='question'))
    pending = []
    assert _edits(source, [dict(block_id='b0', find=f'(D) 条件丁。 ({answer})', replace='(D) 条件丁。',
                                reason='删除OCR误识的答案标记', evidence='image')],
                  {'b0': 'q'}, pending=pending, visual_ids={'q'}) == []
    assert pending and source.blocks[0].text == text
    store = ExerciseFileAnalysisStore(tmp_path)
    proposals, sid = project(store, source)
    assert proposals[0]['answer'] == f'({answer})'
    assert proposals[0]['question_text'].rstrip().endswith('(D) 条件丁。')
    registry = {b['block_id']:b for b in store.load(sid, source.book_name).source_blocks}
    for bid, raw in registry.items():
        spans = [s for values in proposals[0]['projection']['parts'].values() for s in values if s['block_id'] == bid]
        assert ''.join(raw['text'][s['start']:s['end']] for s in sorted(spans, key=lambda s:s['start'])) == raw['text']
    # Ordinary OCR corrections and wrapped source metadata remain editable.
    assert _edits(source, [dict(block_id='b0', find='条件甲', replace='条件钾')], {'b0': 'q'}, pending=[]) != []
    source.blocks[0].text = '$\\frac{2024年}{数学一}$'
    assert _edits(source, [dict(block_id='b0', find=source.blocks[0].text, replace='2024年数学一')], {'b0': 'q'}, pending=[]) != []


def test_question_context_keeps_conditions_and_required_tables_but_not_metadata(tmp_path):
    source = book(
        block('q', '12. （1）仪器在20℃环境下校准，求灵敏度。', structure_unit_start=True, structure_unit_role='question',
              exercise_metadata=dict(exam_year='2024', evidence=[dict(block_id='meta', quote='2024·数二·测量')])) ,
        block('meta', '2024·数二·测量', structure_unit_id='q', structure_unit_role='context'),
        block('t1', '| x | y |\n| --- | --- |\n| 1 | 2 |', 'table', structure_unit_id='q', structure_unit_role='context'),
        block('condition', '(2) 当仪器在50℃环境温度下使用时，特性变成下表。', structure_unit_id='q', structure_unit_role='context'),
        block('t2', '| x | y |\n| --- | --- |\n| 1 | 3 |', 'table', structure_unit_id='q', structure_unit_role='context'),
        block('ask', '试确定此时新的灵敏度。', structure_unit_id='q', structure_unit_role='question'),
    )
    proposals, _ = project(ExerciseFileAnalysisStore(tmp_path), _prepare_roles(source))
    p = proposals[0]
    assert '50℃' in p['question_text'] and '新的灵敏度' in p['question_text']
    assert '2024' not in p['question_text']
    assert len(p['projection']['dependencies']) == 2
    assert all(d['requirement'] == 'required' and d['resolution'] == 'embedded' for d in p['projection']['dependencies'])
    assert any('condition' in i['key'] and i['code'] == 'boundary_uncertain' for i in p['issues'])
    assert p['projection']['method'] == 'unresolved'


def test_rebuild_restores_recorded_legacy_deletions_and_keeps_real_corrections(tmp_path):
    original = '1. 判断镍格的材料。 (A) 甲。 (B) 乙。 (C) 丙。 (D) 丁。 (C)'
    corrections = [dict(find='镍格', replace='镍铬'), dict(find='(D) 丁。 (C)', replace='(D) 丁。')]
    text = original
    for edit in corrections:text = text.replace(edit['find'], edit['replace'])
    source = book(block('q', text, structure_unit_start=True, structure_unit_role='question',
                        original_ocr_text=original, text_corrections=corrections))
    source.source_metadata['exercise_scope_policy'] = 'all'
    store = ExerciseFileAnalysisStore(tmp_path)
    before, sid = project(store, source)
    assert not before[0]['answer']
    rebuilt = store.load(store.rebuild(sid, source.book_name), source.book_name)
    after = project_units(rebuilt.units, rebuilt.source_blocks, rebuilt.canonical_hash, before[0]['projection']['scope'])
    assert '镍铬' in after[0]['question_text'] and after[0]['answer'] == '(C)'
    assert any(i['code'] == 'boundary_uncertain' for i in after[0]['issues'])
    assert store.load(sid, source.book_name).units[0]['text'] == before[0]['unit']['text']


def test_coverage_uses_displayed_groups_and_accounts_for_body_demotion(tmp_path):
    source = book(block('body', '4. 有界性'), block('q', '【例1】求给定函数的定义域。', 'example'),
                  block('f', '1 \\leqslant x + 1 \\leqslant a + 1', 'formula'))
    reviewed = _structure(source, dict(blocks=[dict(block_id='body', role='body', unit_start=False),
        dict(block_id='f', role='solution', unit_id='q', unit_role='answer')]),
        {b.block_id:b.block_id for b in source.blocks}, recover=False)
    coverage = candidate_coverage(source, reviewed)
    assert (coverage['before'], coverage['after'], coverage['removed'], coverage['unaccounted']) == (2, 1, 1, 0)
    assert coverage['changes'] == [dict(block_id='body', count=1, reason='excluded_source')]
    assert len(project(ExerciseFileAnalysisStore(tmp_path), source)[0]) == coverage['before']
    # A formula that was independently displayed must also map back to its raw ID.
    isolated = book(deepcopy(source.blocks[2]), deepcopy(source.blocks[1]))
    reassigned = _structure(isolated, dict(blocks=[dict(block_id='f', role='solution', unit_id='q', unit_role='answer')]),
                            {'f':'f', 'q':'q'}, recover=False)
    assert candidate_coverage(isolated, reassigned)['changes'] == [dict(block_id='f', count=1, reason='reassembled_source')]


def test_page_packages_do_not_pair_a_new_example_with_the_previous_page():
    source = book(block('q1', '【例1】第一页的独立题。', 'example', learning_unit_id='q1'),
                  block('q2', '【例2】第二页的新题。', 'example', page=2, learning_unit_id='q2'),
                  block('tail', '此题在第三页继续证明。', 'example', page=3, learning_unit_id='q2'))
    assert page_packages(source) == [[1], [2, 3]]


@pytest.mark.parametrize('fail_last_page', [False, True])
def test_read_only_boundary_proposals_require_confirmation_on_their_page(tmp_path, fail_last_page):
    source = book(block('q1', '【例1】第一道题。', 'example', learning_unit_id='q1'),
                  block('tail1', '第一道题的续文。', 'example', page=2, learning_unit_id='q1'),
                  block('q2', '【例2】第二道题。', 'example', page=2, learning_unit_id='q2'),
                  block('tail2', '解 由题设可得结论。', 'example', page=3, learning_unit_id='q2'))
    pdf = tmp_path/'original.pdf'
    with fitz.open() as doc:
        for _ in range(3):doc.new_page()
        doc.save(pdf)
    calls = []
    class Session:
        def call(self, key, system, content, **kwargs):
            data = json.loads(content[0]['text']); calls.append(data)
            aliases = {b['text']:b['id'] for b in data['blocks'] + data['context_blocks']}
            target, owner = aliases[source.blocks[-1].text], aliases[source.blocks[-2].text]
            if data['review_pages'] == [1, 2]:
                return dict(blocks=[dict(block_id=target, unit_id=owner, unit_role='explanation')])
            assert data['review_pages'] == [3] and data['original_images'] == [dict(id='original-page:3', page=3)]
            assert data['boundary_proposals'] == [dict(block_id=target, unit_id=owner, unit_role='explanation')]
            assert next(b for b in data['blocks'] if b['id']==target)['role'] == 'body'
            if fail_last_page:raise ValueError('响应失败')
            return dict(blocks=[dict(block_id=target, unit_id=owner, unit_role='explanation')])
        def report(self):return dict(calls=len(calls))
    reviewed, report = run_semantic_review(source, directory=tmp_path/'review', resolved=None, purpose='exercises', session=Session(), pdf_path=pdf)
    assert len(calls) == 2
    assert bool(report['unapplied_boundary_proposals']) == fail_last_page
    assert report['needs_retry'] == fail_last_page
    assert (reviewed.blocks[-1].attributes.get('structure_unit_role') == 'explanation') != fail_last_page
    assert 'structure_unit_role' not in source.blocks[-1].attributes
