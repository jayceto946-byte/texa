"""Synthetic integration contracts; no real model, textbook or learning data."""
import json
import pytest
from langchain_core.messages import HumanMessage, ToolMessage, messages_to_dict
from backend.tools.registry import ToolContext
from backend.services.agent_runtime.textbook_tool import register_textbook_search_runtime
from backend.services.exercise_knowledge import save_answer_with_knowledge
from knowledge.exercise_structure import question_digest, validate_classification
from memory.exercise_bank import ExerciseBank, ExerciseRecord
from test_exercise_candidate_contract import admission_fixture, content_hash
from test_exercise_knowledge_structure import catalog, proposal
from test_native_math_loop import setup_run, call
from test_textbook_context_expansion import corpus, state_for


def test_candidate_publishes_then_classifies_without_reusing_review_hash(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import exercises as api
    from backend.services import exercise_knowledge as knowledge
    service, item, _ = admission_fixture()
    bank = ExerciseBank(tmp_path / 'exercise.db')
    monkeypatch.setattr('backend.services.exercise_candidate_review.ExerciseCandidateReviewService', lambda: service)
    monkeypatch.setattr(api, '_bank', lambda _: bank)
    monkeypatch.setattr(api, '_log_learning_event', lambda *a, **kw: None)
    app = FastAPI(); app.include_router(api.router)
    response = TestClient(app).post('/exercises/candidates/batch-add', json={'candidate_contract_version': 1, 'exercises': [item]}).json()
    record = bank.get(response['data'][0]['id'])
    assert record.knowledge_structure == {}
    receipt = response['candidate_receipts'][0]
    assert receipt['body_hash'] == content_hash(item, include_projection=False)
    record.extra_fields['future_extension'] = {'keep': [1, 2]}
    bank.update(record)
    monkeypatch.setattr(knowledge, 'build_catalog', lambda record, book_name: catalog(record, book_name))
    structure = validate_classification(proposal(), catalog(record, 'toy'), analysis='2')
    job = {'status': 'completed', 'exercise_id': record.id, 'book_name': 'toy', 'result': {'answer': '2', 'knowledge_structure': structure}}
    updated, status = save_answer_with_knowledge(bank, record, answer='2', explanation='', book_name='toy', job=job)
    assert status == 'saved' and updated.knowledge_structure['primary']['concept_id'] == 'c1'
    assert bank.get(record.id).to_dict()['future_extension'] == {'keep': [1, 2]}
    assert bank.list_import_batches()[0]['candidate_receipts'][0] == receipt
    assert content_hash(updated.to_dict(), include_projection=False) != receipt['body_hash']
    updated, _ = save_answer_with_knowledge(bank, updated, answer='3', explanation='', book_name='toy', job=None)
    assert updated.knowledge_structure['status'] == 'stale'


def test_exercise_visual_extension_changes_question_version(tmp_path):
    bank = ExerciseBank(tmp_path / 'bank.db')
    record = ExerciseRecord.from_dict({'question_text': 'Stokes', 'visual_ir': {'figure': 'one'}})
    record.knowledge_structure = validate_classification(proposal(), catalog(record))
    bank.add(record)
    loaded = bank.get(record.id)
    before = question_digest(loaded)
    loaded.extra_fields['visual_ir'] = {'figure': 'two'}
    bank.update(loaded)
    loaded = bank.get(record.id)
    assert question_digest(loaded) != before
    assert loaded.knowledge_structure['status'] == 'stale'
    assert loaded.to_dict()['visual_ir'] == {'figure': 'two'}


@pytest.mark.parametrize('field', ['answer', 'explanation'])
def test_direct_record_update_invalidates_old_answer_classification(tmp_path, field):
    bank = ExerciseBank(tmp_path / 'bank.db')
    record = ExerciseRecord(question_text='Stokes', answer='old answer', explanation='old explanation')
    record.knowledge_structure = validate_classification(proposal(), catalog(record))
    bank.add(record)
    loaded = bank.get(record.id)
    setattr(loaded, field, 'changed reference')
    bank.update(loaded)
    assert bank.get(record.id).knowledge_structure['status'] == 'stale'


@pytest.mark.parametrize('mismatch', ['version', 'schema_hash', 'index'])
def test_resumed_old_textbook_tool_is_fenced_before_model(tmp_path, mismatch):
    store, run, model, runner, state = setup_run(tmp_path, [{'content': 'finish'}])
    frozen = {'id': 'scope', 'book_name': '', 'subject': '', 'resources': [], 'index_versions': {'toy': 'v1'}}
    register_textbook_search_runtime(runner.registry, frozen, versions=lambda _: 'changed' if mismatch == 'index' else 'v1')
    ref = runner.registry.runtime_tool('search_textbook').runtime_metadata()
    state.update(support_type='', use_textbook_context=True,
                 _native_preparation_ref={k: ref[k] for k in ('id', 'version', 'schema_hash')}, _runtime_textbook_scope=frozen)
    if mismatch != 'index':
        state['_native_preparation_ref'][mismatch] = '1' if mismatch == 'version' else 'old-schema'
    store.configure_chat(run, 'owner', state=state, candidates=runner.candidate_tools,
                         request_question='教材解释', book_name='', subject='')
    store.save_native_messages(run, 'owner', messages_to_dict([HumanMessage(content='旧教材上下文')]),
                               protocol_identity=runner.adapter.protocol_identity())
    store.close(run, 'owner', outcome='paused', error_code='interrupted')
    paused = store.snapshot(run)
    resumed = store.resume('rtask_math', expected_revision=paused['task_revision'], request_key='resume', request_id='resume', owner_token='new', turn_id='turn')
    result = runner.run_bounded(resumed['run']['id'], 'new', context=ToolContext(), answer_state=state, answer_generator=lambda _: pytest.fail('no extra model'))
    assert result['run']['error_code'] == 'answer_scope_changed'
    assert not model.received
    assert any('重新发起' in event['summary'] for event in store.events(resumed['run']['id']))
    assert store.snapshot(run)['run']['status'] == 'paused'


def test_textbook_context_and_math_receipt_survive_next_model_step(corpus, tmp_path):
    from graph.textbook_context import expand_textbook_context
    make, _, _, _ = corpus
    _, anchor = make()
    state = state_for(expand_textbook_context([anchor]))
    responses = [call('verify_math_result', {'kind': 'equivalence', 'left': '2+2', 'right': '4'}, 'verify'),
                 {'content': '闭区间连续，开区间可导。局部计算核验为4。'}]
    store, run, model, runner, _ = setup_run(tmp_path, responses)
    store.configure_chat(run, 'owner', state=state, candidates=runner.candidate_tools,
                         request_question='讲解中值定理并核验2+2', book_name='数学', subject='数学')
    result = runner.run_bounded(run, 'owner', context=ToolContext(book_name='数学', subject='数学'), answer_state=state, answer_generator=lambda _: pytest.fail('no extra model'))
    assert len(model.received) == 2
    messages = model.received[1]
    assert any('设函数在闭区间连续' in str(m.content) and '构造辅助函数' in str(m.content) for m in messages)
    receipt = json.loads(next(m.content for m in messages if isinstance(m, ToolMessage)))
    assert receipt['data']['status'] == 'verified'
    assert receipt['data'] == result['tool_calls'][0]['result']['data']
    assert result['task']['verification']['status'] != 'passed'
