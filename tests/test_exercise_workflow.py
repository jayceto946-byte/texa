"""User-authorized import and independent solving, without models or real data."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from test_exercise_candidate_contract import admission_fixture, CASES
from backend.services.exercise_candidate_review import CandidateAdmissionError
from memory.exercise_bank import ExerciseRecord


def test_batch_confirmation_accepts_unresolved_content_and_edits():
    service, item, _ = admission_fixture(CASES[4])
    item['candidate_context']['import_confirmed'] = True
    receipt = service.prepare('toy', [item])[0]
    assert receipt['review_kind'] == 'user_imported'
    assert receipt['import_review']['status'] == 'pending'
    item['question_text'] += '（用户补充的条件）'
    item['candidate_context']['projection']['method'] = 'user_edited'
    assert service.prepare('toy', [item])[0]['review_kind'] == 'user_imported'
    # Import consent permits imperfect content; it cannot forge source membership.
    item['candidate_context']['projection']['parts']['question'][0]['block_id'] = 'foreign'
    with pytest.raises(CandidateAdmissionError):
        service.prepare('toy', [item])


def test_missing_figure_can_be_stored_for_later_editing():
    service, item, _ = admission_fixture(CASES[10])
    item['candidate_context']['import_confirmed'] = True
    receipt = service.prepare('toy', [item])[0]
    assert any(i['code'] == 'missing_required_input' for i in receipt['import_review']['issues'])
    from backend.services.exercise_answers import _missing_inputs
    assert _missing_inputs(item['question_text'], [])


def test_removed_figure_is_not_frozen_and_source_is_preserved(tmp_path):
    from backend.services.exercise_assets import freeze_attachments
    projection = dict(parts={'question': [dict(block_id='figure')], 'answer': []}, excluded_figure_ids=['figure'])
    blocks = [dict(block_id='figure', block_type='figure', text='误带入的手写笔记', attributes={'asset_id': 'a' * 64})]
    extracted = SimpleNamespace(source_blocks=deepcopy(blocks))
    assert freeze_attachments(projection, extracted, book_name='toy', progress_root=tmp_path) == []
    assert extracted.source_blocks == blocks
    service, item, _ = admission_fixture()
    item['candidate_context'].update(import_confirmed=True)
    item['candidate_context']['projection']['excluded_figure_ids'] = ['b0']
    with pytest.raises(CandidateAdmissionError, match='只能移除'):
        service.prepare('toy', [item])


def test_solver_without_textbook_evidence_still_generates(monkeypatch):
    from backend.services import exercise_answers as answers, exercise_knowledge
    monkeypatch.setattr(answers, 'retrieve_node', lambda _: dict(evidence_items=[], evidence_support={'status': 'insufficient'}))
    monkeypatch.setattr(exercise_knowledge, 'prepare_analysis', lambda *_a, **_k: {})
    monkeypatch.setattr(exercise_knowledge, 'analysis_instruction', lambda _: 'metadata')
    monkeypatch.setattr(exercise_knowledge, 'parse_analysis', lambda draft, _: (draft, {}, None, 'missing'))
    seen = []
    def invoke(messages):
        seen.extend(messages)
        return SimpleNamespace(content='两数相加，结果为5。')
    monkeypatch.setattr('config.get_llm', lambda **_: SimpleNamespace(invoke=invoke))
    def finalize(state, draft):
        assert state['answer_mode'] == 'subject_general'
        assert not state['evidence_gate_applied']
        state['answer_verification'] = {'status': 'unverified'}
        return draft
    monkeypatch.setattr(answers, 'finalize_generated_answer', finalize)
    record = ExerciseRecord(question_text='求2与3之和。', subject='数学')
    result = answers._generate_draft(record, dict(book_name='default', required_outputs=[]))
    assert result['success'] and result['data']['answer'] == '两数相加，结果为5。'
    assert seen
    # Missing problem conditions still stop before any model invocation.
    seen.clear()
    record.question_text = '根据下图求电流。'
    result = answers._generate_draft(record, dict(book_name='default', required_outputs=[]))
    assert result['delivery_status'] == 'waiting_for_input' and not seen


def test_edit_saved_exercise_keeps_identity_history_and_source(tmp_path):
    from backend.services.exercise_editing import edit_exercise
    from memory.exercise_bank import ExerciseBank
    bank = ExerciseBank(tmp_path / 'exercises.db')
    record = ExerciseRecord(question_text='旧题干', origin_id='source-unit', practice_count=2,
                            extra_fields={'source_attachments': [dict(asset_id='owned', role='question')],
                                          'source_structure': {'original_number': '1.9'}})
    bank.add(record)
    result = edit_exercise(bank, record.id, question_text='已修正题干', answer='用户答案', explanation='',
                           removed_asset_ids=['owned'], reviewed=True)
    saved = bank.get(record.id)
    assert result.id == record.id and saved.practice_count == 2 and saved.origin_id == 'source-unit'
    assert saved.extra_fields['source_attachments'] == []
    assert saved.extra_fields['source_structure']['original_number'] == '1.9'
    assert saved.extra_fields['import_review']['status'] == 'reviewed'
