"""P1-C deterministic contracts, not a model classification accuracy benchmark."""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from knowledge.exercise_structure import (
    catalog_from_kg, validate_classification, validate_diagnosis, digest, weak_summary,
)
from backend.services import exercise_knowledge as service
from memory.exercise_bank import ExerciseBank, ExerciseRecord
from memory.mistake_book import MistakeBook, MistakeRecord
from memory.mistake_lifecycle import MistakeLifecycleStore


def graph():
    return SimpleNamespace(_is_local=True, meta={"version": 1}, concepts=[
        {"concept_id": "c1", "canonical_name": "斯托克斯公式", "aliases": ["Stokes"], "roles": ["theorem"]},
        {"concept_id": "c2", "canonical_name": "曲面方向", "aliases": [], "roles": ["property"]},
        {"concept_id": "c3", "canonical_name": "曲线积分", "aliases": [], "roles": ["concept"]},
    ], occurrences=[{"concept_id": f"c{i}", "chunk_id": f"chunk{i}"} for i in range(1, 4)],
       _chunk_to_chapter={f"chunk{i}": "多元微积分" for i in range(1, 4)})


def catalog(record, book="book-a", kg=None):
    return catalog_from_kg(kg or graph(), record, book_name=book)


def proposal():
    return {"status": "proposed", "primary": {"concept_id": "c1", "basis": "题干使用 Stokes"},
            "related": [{"concept_id": "c2", "basis": "曲面方向"}, {"concept_id": "c3", "basis": "计算曲线积分"}],
            "theorems": [{"concept_id": "c1", "basis": "化为曲面积分"}],
            "properties": [{"statement": "边界方向与法向相容", "basis": "给定方向", "concept_id": "c2"}],
            "domain": "多元函数微积分", "question_type": "曲线积分计算", "basis": "题干要求 Stokes 计算"}


def attempt_record(tmp_path, answer="第一步：选取曲面\n第三步：法向取反\n最终积分值为2"):
    book = MistakeBook(tmp_path / 'mistakes.db')
    record = MistakeRecord(question_text="用 Stokes 计算曲线积分", chapter="多元微积分", tags=["斯托克斯公式", "曲面方向"])
    book.add(record)
    lifecycle = MistakeLifecycleStore(book.store)
    aid = lifecycle.append_occurrence_once(record.id, 'attempt-1', answer=answer, source_ref={"type": "exercise_attempt", "operation_id": "op1"})
    return book, lifecycle, book.get(record.id), lifecycle.list_attempts(record.id)[0], aid


def error_payload(answer, concepts=None):
    quote = "法向取反"
    start = answer.index(quote)
    return {"errors": [{"error_type": "orientation", "concept_ids": concepts or ["c1"], "start": start,
                        "end": start + len(quote), "quote": quote, "step": 2, "explanation": "方向与题干相反"}]}


def test_semantic_dimensions_canonical_ids_and_pending_new_concepts():
    record = ExerciseRecord(question_text="用 Stokes 计算曲线积分", chapter="多元微积分")
    raw = proposal()
    raw["new_concepts"] = [{"name": "模型新名词", "basis": "待人工检查"}]
    kg = graph()
    saved = validate_classification(raw, catalog(record, kg=kg))
    assert saved["primary"]["name"] == "斯托克斯公式"
    assert {c["concept_id"] for c in saved["related"]} == {"c2", "c3"}
    assert saved["theorems"][0]["concept_id"] == "c1"
    assert saved["properties"][0]["statement"] == "边界方向与法向相容"
    assert saved["verification"] == "unverified"
    assert saved["new_concepts_status"] == "pending_review"
    assert len(kg.concepts) == 3


def test_single_primary_unknown_bad_id_and_bounded_scope():
    record = ExerciseRecord(question_text="Stokes", chapter="多元微积分")
    c = catalog(record)
    saved = validate_classification({"status": "proposed", "primary": {"concept_id": "c1", "basis": "Stokes"}, "basis": "题干"}, c)
    assert saved["related"] == []
    assert validate_classification({}, c)["status"] == "unclassified"
    assert validate_classification({"status": "unknown", "uncertainty": "无法判断主次"}, c)["primary"] is None
    with pytest.raises(ValueError):
        validate_classification({**proposal(), "primary": {"concept_id": "nonexistent", "basis": "自由生成"}}, c)
    with pytest.raises(ValueError):
        validate_classification({**proposal(), "status": "unknown"}, c)
    record.chapter = "其他章节"
    assert catalog(record)["candidates"] == []
    assert len(catalog_from_kg(graph(), record, book_name="book-a", limit=999)["candidates"]) <= 40


def test_cross_book_and_kg_versions_never_merge(monkeypatch):
    record = ExerciseRecord(question_text="Stokes", chapter="多元微积分")
    saved = validate_classification(proposal(), catalog(record))
    monkeypatch.setattr(service, 'build_catalog', lambda record, book_name: catalog(record, book_name))
    with pytest.raises(ValueError, match='scope'):
        service.restore_saved_structure(saved, record, book_name='book-b')
    changed = graph()
    changed.meta['version'] = 2
    monkeypatch.setattr(service, 'build_catalog', lambda record, book_name: catalog(record, book_name, changed))
    with pytest.raises(ValueError, match='version'):
        service.restore_saved_structure(saved, record, book_name='book-a')


@pytest.mark.parametrize('kind', ['exercise', 'mistake'])
def test_json_roundtrip_unknown_fields_and_edit_compatibility(tmp_path, kind):
    cls = ExerciseRecord if kind == 'exercise' else MistakeRecord
    owner = ExerciseBank(tmp_path / 'exercise.db') if kind == 'exercise' else MistakeBook(tmp_path / 'mistake.db')
    record = cls.from_dict({'question_text': 'Stokes', 'chapter': '多元微积分', 'future_extension': {'keep': [1, 2]}, 'extra_fields': 'legacy opaque value'})
    record.knowledge_structure = validate_classification(proposal(), catalog(record))
    owner.add(record)
    loaded = owner.get(record.id)
    loaded.notes = 'metadata edit'
    owner.update(loaded)
    again = owner.get(record.id)
    assert again.knowledge_structure == record.knowledge_structure
    assert again.to_dict()['future_extension'] == {'keep': [1, 2]}
    assert again.to_dict()['extra_fields'] == 'legacy opaque value'
    assert cls.from_dict({'question_text': 'old'}).knowledge_structure == {}
    again.question_text = 'corrected different question'
    owner.update(again)
    assert owner.get(record.id).knowledge_structure['status'] == 'stale'


def test_final_answer_does_not_support_specific_cause(tmp_path):
    _, _, record, attempt, _ = attempt_record(tmp_path, answer='2')
    c = catalog(record)
    error = {'error_type': 'orientation', 'concept_ids': ['c1'], 'start': 0, 'end': 1, 'quote': '2', 'step': None}
    with pytest.raises(ValueError, match='working step'):
        validate_diagnosis({'errors': [error]}, record=record, attempt=attempt, catalog=c)
    error.update(error_type='final_answer_incorrect', concept_ids=[])
    saved = validate_diagnosis({'errors': [error]}, record=record, attempt=attempt, catalog=c)
    assert saved['status'] == 'suggested'
    error['concept_ids'] = ['c1']
    with pytest.raises(ValueError, match='weak concepts'):
        validate_diagnosis({'errors': [error]}, record=record, attempt=attempt, catalog=c)


def test_attempt_evidence_confirmation_idempotency_and_no_multitag_count(tmp_path):
    book, store, record, attempt, aid = attempt_record(tmp_path)
    before_sm2 = dict(record.sm2)
    record.knowledge_structure = validate_classification(proposal(), catalog(record))
    book.update(record)
    assert book.get_weak_points() == []
    assert book.get(record.id).sm2 == before_sm2
    record = book.get(record.id)
    raw = error_payload(attempt['answer'], ['c1', 'c2', 'c3'])
    raw['errors'].append(dict(raw['errors'][0]))  # two claims, one underlying attempt
    result = store.set_attempt_diagnosis(record.id, aid, expected_revision=record.revision,
        operation_id='suggest', catalog=catalog(record), proposal=raw)
    assert book.get_weak_points() == []
    confirmed = store.set_attempt_diagnosis(record.id, aid, expected_revision=result['revision'], operation_id='confirm',
        catalog=catalog(record), confirm=True, expected_diagnosis_digest=result['diagnosis_digest'])
    replay = store.set_attempt_diagnosis(record.id, aid, expected_revision=result['revision'], operation_id='confirm',
        catalog=catalog(record), confirm=True, expected_diagnosis_digest=result['diagnosis_digest'])
    assert replay == confirmed
    assert book.get(record.id).sm2 == before_sm2  # diagnosis itself never schedules
    summary = book.evidence_summary()
    assert summary['confirmed_error_attempts'] == 1
    assert [c['count'] for c in summary['concepts']] == [1, 1, 1]
    assert summary['reasons'][0]['count'] == 1
    loaded = store.list_attempts(record.id)[0]
    assert loaded['diagnosis']['errors'][0]['quote'] == '法向取反'
    assert loaded['diagnosis']['attempt_id'] == aid
    with pytest.raises(ValueError, match='replaced'):
        store.set_attempt_diagnosis(record.id, aid, expected_revision=confirmed['revision'], operation_id='overwrite', catalog=catalog(record), proposal={})


def test_span_revision_and_confirmation_scope_fail_closed(tmp_path):
    book, store, record, attempt, aid = attempt_record(tmp_path)
    raw = error_payload(attempt['answer'])
    raw['errors'][0]['start'] += 1
    with pytest.raises(ValueError, match='span'):
        validate_diagnosis(raw, record=record, attempt=attempt, catalog=catalog(record))
    raw = error_payload(attempt['answer'])
    raw['errors'][0]['step'] = 3
    with pytest.raises(ValueError, match='step'):
        validate_diagnosis(raw, record=record, attempt=attempt, catalog=catalog(record))
    result = store.set_attempt_diagnosis(record.id, aid, expected_revision=record.revision, operation_id='s', catalog=catalog(record), proposal=error_payload(attempt['answer']))
    with pytest.raises(ValueError, match='scope'):
        store.set_attempt_diagnosis(record.id, aid, expected_revision=result['revision'], operation_id='c',
            catalog=catalog(record, 'book-b'), confirm=True, expected_diagnosis_digest=result['diagnosis_digest'])
    assert book.get_weak_points() == []
    store.change_record(record.id, expected_revision=result['revision'], operation_id='edit', changes={'question_text': 'new'}, meaning_changed=False)
    assert book.get(record.id).content_revision == 2
    assert book.get_weak_points() == []
    with pytest.raises(ValueError, match='revision'):
        validate_diagnosis(error_payload(attempt['answer']), record=book.get(record.id), attempt=attempt, catalog=catalog(book.get(record.id)))


def test_classifier_never_calls_concept_memory_and_keeps_real_score(monkeypatch):
    from backend.api import mistakes
    from knowledge import concept_linker
    fake = SimpleNamespace(kg=SimpleNamespace(_is_local=True), link=lambda **_: [
        {'name': 'Stokes', 'concept_id': 'c1', 'confidence': .61, 'source': 'question'}])
    monkeypatch.setattr(concept_linker, 'ConceptLinker', lambda _: fake)
    monkeypatch.setattr('config.get_llm', lambda *_a, **_kw: pytest.fail('extra classification request'))
    record = MistakeRecord(question_text='Stokes')
    linked = mistakes._persist_mistake_concepts(record)
    assert linked[0]['confidence'] == .61
    assert linked[0]['evidence_kind'] == 'question_association'


def test_single_explanation_call_saves_structure_and_only_suggests_diagnosis(tmp_path, monkeypatch):
    book, store, record, attempt, aid = attempt_record(tmp_path)
    monkeypatch.setattr(service, 'build_catalog', lambda record, book_name: catalog(record, book_name))
    calls = []
    payload = {'knowledge': proposal(), 'diagnoses': [{'attempt_id': aid, **error_payload(attempt['answer'])}]}
    def invoke(prompt):
        calls.append(prompt)
        assert aid in prompt and 'c1' in prompt
        return '正常讲解\n' + service.OPEN + json.dumps(payload, ensure_ascii=False) + service.CLOSE
    response = service.explain_mistake(book, record.id, book_name='book-a', invoke=invoke)
    assert len(calls) == 1
    assert response['explanation'] == '正常讲解'
    assert response['record'].knowledge_structure['primary']['concept_id'] == 'c1'
    assert store.list_attempts(record.id)[0]['diagnosis']['status'] == 'suggested'
    assert book.get_weak_points() == []


@pytest.mark.parametrize('tail', ['', '<texa_structure>{bad}', '<texa_structure>{"knowledge":{"primary":{"concept_id":"bad","basis":"x"}}}</texa_structure>'])
def test_bad_metadata_preserves_teaching_answer_and_unclassified(tail):
    record = ExerciseRecord(question_text='Stokes', chapter='多元微积分')
    body, structure, _, status = service.parse_analysis('answer\n'+tail, {'catalog': catalog(record), 'attempts': []})
    assert body == 'answer'
    assert structure['status'] == 'unclassified'
    assert status in {'missing', 'invalid'}


def test_answer_job_save_roundtrip_stale_and_edited(tmp_path, monkeypatch):
    bank = ExerciseBank(tmp_path / 'exercises.db')
    record = ExerciseRecord(question_text='Stokes', chapter='多元微积分')
    bank.add(record)
    monkeypatch.setattr(service, 'build_catalog', lambda record, book_name: catalog(record, book_name))
    structure = validate_classification(proposal(), catalog(record))
    job = {'status': 'completed', 'exercise_id': record.id, 'book_name': 'book-a',
           'result': {'answer': 'result', 'knowledge_structure': structure}}
    saved, status = service.save_answer_with_knowledge(bank, record, answer='result', explanation='', book_name='book-a', job=job)
    assert status == 'saved'
    assert bank.get(record.id).knowledge_structure['primary']['concept_id'] == 'c1'
    _, status = service.save_answer_with_knowledge(bank, saved, answer='edited', explanation='', book_name='book-a', job=job)
    assert status == 'edited_answer_requires_review'
    changed = bank.get(record.id)
    changed.question_text = 'new'
    bank.update(changed)
    _, status = service.save_answer_with_knowledge(bank, changed, answer='result', explanation='', book_name='book-a', job=job)
    assert status == 'stale_or_invalid'


def test_same_concept_query_excludes_other_book_and_stale_version(tmp_path, monkeypatch):
    from knowledge.knowledge_graph import KnowledgeGraph
    kg = graph()
    data = {'meta': kg.meta, 'concepts': kg.concepts, 'occurrences': kg.occurrences}
    directory = tmp_path / 'kg'
    directory.mkdir()
    # Real loader obtains chapter anchors from middle chunks.
    (directory / 'book-a_knowledge_graph.json').write_text(json.dumps(data))
    chunks = [{'chunk_id': f'chunk{i}', 'section_title': '第1章 多元微积分', 'text': 'Stokes'} for i in range(1,4)]
    (directory / 'book-a_middle_chunks.json').write_text(json.dumps(chunks))
    monkeypatch.setattr(KnowledgeGraph, '_resolve_local_dir', staticmethod(lambda _: directory))
    bank = ExerciseBank(tmp_path / 'bank.db')
    record = ExerciseRecord(question_text='Stokes')
    current = service.build_catalog(record, book_name='book-a')
    record.knowledge_structure = validate_classification(proposal(), current)
    bank.add(record)
    assert [r.id for r in service.find_exercises_by_concept(bank, book_name='book-a', concept_id='c1')] == [record.id]
    assert service.find_exercises_by_concept(bank, book_name='book-b', concept_id='c1') == []
    data['meta']['version'] = 2
    (directory / 'book-a_knowledge_graph.json').write_text(json.dumps(data))
    assert service.find_exercises_by_concept(bank, book_name='book-a', concept_id='c1') == []


def test_api_attempt_diagnosis_confirmation_and_legacy_confirm_blocked(tmp_path, monkeypatch):
    from backend.main import app
    from backend.api import mistake_lifecycle as api
    book, store, record, attempt, aid = attempt_record(tmp_path)
    monkeypatch.setattr(api, '_mb', lambda _: book)
    monkeypatch.setattr(service, 'build_catalog', lambda record, book_name: catalog(record, book_name))
    client = TestClient(app)
    url = f'/api/mistakes/{record.id}/attempts/{aid}/diagnosis'
    result = client.post(url, json={'expected_revision': record.revision, 'operation_id': 'api-s', 'proposal': error_payload(attempt['answer'])}).json()['data']
    assert result['diagnosis']['status'] == 'suggested'
    res = client.post(url, json={'expected_revision': result['revision'], 'operation_id': 'api-c', 'confirm': True, 'expected_diagnosis_digest': result['diagnosis_digest']})
    assert res.status_code == 200
    assert book.get_weak_points()[0]['count'] == 1
    assert client.get('/api/mistakes/diagnosis').json()['data']['confirmed_error_attempts'] == 1
    assert client.post('/api/mistakes/query', json={'search': '方向判断错误'}).json()['data']['items'][0]['id'] == record.id
    assert client.get('/api/mistakes/counts?search=方向判断错误').json()['data']['all'] == 1
    other = MistakeRecord(question_text='final only', mistake_type=['orientation'])
    book.add(other)
    response = client.post(f'/api/mistakes/{other.id}/actions', json={'expected_revision': 1, 'operation_id': 'unsafe-confirm', 'action': 'confirm_diagnosis'})
    assert response.status_code == 422


def test_generation_contract_uses_existing_call_and_verifies_only_visible_answer(monkeypatch):
    from backend.services import exercise_answers as answers
    record = ExerciseRecord(question_text='Stokes')
    context = {'catalog': catalog(record), 'attempts': []}
    monkeypatch.setattr(service, 'prepare_analysis', lambda *_a, **_kw: context)
    monkeypatch.setattr(answers, 'retrieve_node', lambda _: {})
    monkeypatch.setattr(answers, 'has_textbook_evidence', lambda _: True)
    monkeypatch.setattr(answers, 'prepare_answer_generation', lambda _: [])
    calls = []
    raw = '正确推导\n'+service.OPEN+json.dumps({'knowledge': proposal()})+service.CLOSE
    def invoke(messages):
        calls.append(messages)
        return SimpleNamespace(content=raw)
    monkeypatch.setattr('config.get_llm', lambda **_: SimpleNamespace(invoke=invoke))
    def finalize(state, text):
        assert service.OPEN not in text
        assert text == '正确推导'
        state['answer_verification'] = {'status': 'unverified'}
        return text
    monkeypatch.setattr(answers, 'finalize_generated_answer', finalize)
    result = answers._generate_draft(record, {'book_name': 'book-a', 'required_outputs': []})
    assert len(calls) == 1
    assert result['data']['knowledge_structure']['primary']['concept_id'] == 'c1'
    assert result['data']['verification']['status'] == 'unverified'


def test_old_direct_json_rows_do_not_lose_extensions_or_confirmed_status(tmp_path):
    book = MistakeBook(tmp_path / 'legacy.db')
    record = MistakeRecord(question_text='old')
    book.add(record)
    raw = {'id': record.id, 'question': 'old', 'diagnosis_status': 'confirmed', 'future_field': {'a': 1}}
    with book.store._connect() as conn:
        conn.execute('UPDATE mistakes SET data=? WHERE id=?', (json.dumps(raw), record.id))
    loaded = book.get(record.id)
    loaded.notes = 'edited'
    book.update(loaded)
    again = book.get(record.id)
    assert again.content_revision == 1
    assert again.diagnosis_status == 'confirmed'  # retained as history; not counted as evidence
    assert again.to_dict()['future_field'] == {'a': 1}
    assert book.get_weak_points() == []


def test_concept_memory_rejects_mistake_associations_and_ignores_legacy_flags(monkeypatch, tmp_path):
    from knowledge import concept_memory as cm_module
    monkeypatch.setattr(cm_module, 'PROGRESS_PATH', tmp_path)
    cm = cm_module.ConceptMemory('p1c')
    cm.log_weakness([{'name': 'Stokes', 'concept_id': 'c1', 'confidence': 1.0}], 'Stokes')
    assert cm.get_weak_points() == []
    assert cm._data['concepts'] == {}
    cm._data['concepts']['Stokes'] = {'weak_flag': True, 'weak_reason': 'mistake'}
    cm._save()
    assert cm_module.ConceptMemory('p1c').get_weak_points() == []
    cm.mark_weak('Stokes', 'manual')
    assert cm_module.ConceptMemory('p1c').get_weak_points()[0]['name'] == 'Stokes'


def test_corrupt_optional_kg_does_not_discard_explanation(tmp_path, monkeypatch):
    book, _, record, _, _ = attempt_record(tmp_path)
    def broken(*_a, **_kw):
        raise ValueError('corrupt optional graph')
    monkeypatch.setattr(service, 'build_catalog', broken)
    result = service.explain_mistake(book, record.id, book_name='book-a', invoke=lambda _: '可保留的讲解')
    assert result['explanation'] == '可保留的讲解'
    assert book.get(record.id).explanation == '可保留的讲解'
    assert result['metadata_status'] == 'scope_unavailable'
    assert book.get_weak_points() == []
