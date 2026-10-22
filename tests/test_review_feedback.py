import io
import json
from functools import partial

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from backend.services.learning_task import LearningTaskStore
from backend.services.multimodal_bridge import VisualProblemIR
from backend.services.review_feedback import grade_review, generate_feedback, parse_feedback, public_review_session
from memory.mistake_book import MistakeBook, MistakeRecord
from memory.mistake_lifecycle import MistakeLifecycleStore


@pytest.fixture
def setup(tmp_path):
    book = MistakeBook(tmp_path / 'mistakes.db')
    record = MistakeRecord(question_text='求 1+1', correct_answer='2', subject='数学')
    book.add(record)
    store = MistakeLifecycleStore(book.store)
    session = store.create_review_session([record.id], scope='default')
    submission = {'original_path': '/private/photo.png', 'work_path': '/private/work.jpg', 'filename': '解答.png'}
    session = store.update_review_image(session['id'], expected_revision=1, submission=submission)
    return book, store, record, session, LearningTaskStore(tmp_path / 'tasks')


FEEDBACK = {'verdict': 'wrong', 'summary': '计算结果需要修改。', 'issues': ['相加得到 2，不能得到 3。'], 'suggestions': ['改为 $1+1=2$。']}


def test_grade_keeps_private_ocr_and_requires_explicit_result(setup):
    book, store, record, session, tasks = setup
    sm2 = book.get(record.id).sm2.copy()
    raw_ir = {'schema_version': 'visual-problem-ir/v2', 'handwritten_work': ['PRIVATE_RAW_WORK'], 'entities': []}
    updated = grade_review(store, session['id'], 2, task_store=tasks, generate=lambda *args: (FEEDBACK, raw_ir))
    assert updated['revealed']
    assert updated['current_submission']['visual_ir'] == raw_ir
    public = json.dumps(public_review_session(updated, '高等数学'), ensure_ascii=False)
    assert not any(value in public for value in ['PRIVATE_RAW_WORK', 'original_path', 'work_path', 'schema_version', '/private/'])
    assert 'wrong' in public
    assert book.get(record.id).sm2 == sm2
    assert store.list_attempts(record.id) == []
    task = tasks.get(updated['feedback']['task_id'])
    assert task.status == 'degraded' and task.verification['status'] == 'unverified'
    assert not task.conversation_id and not task.turn_id
    receipt = store.submit_review_result(session['id'], expected_revision=updated['revision'], operation_id='confirm', result='wrong', hint_used=False, judgement_source='user_confirmed')
    assert store.submit_review_result(session['id'], expected_revision=updated['revision'], operation_id='confirm', result='wrong', hint_used=False, judgement_source='user_confirmed') == receipt
    attempt = store.list_attempts(record.id)[0]
    assert attempt['answer'] == '图片作答'
    assert attempt['submission_ref']['index'] == 0
    assert 'PRIVATE_RAW_WORK' not in json.dumps(attempt)
    restored = store.get_review_session(session['id'])
    assert restored['submissions']['0']['visual_ir'] == raw_ir
    assert not restored.get('current_submission')
    assert 'submissions' not in public_review_session(restored, 'default')


def test_claim_blocks_duplicate_grading_edits_and_stale_result(setup):
    _, store, record, session, _ = setup
    claimed = store.claim_review_feedback(session['id'], expected_revision=2)
    for action in [lambda: store.claim_review_feedback(session['id'], expected_revision=2),
                   lambda: store.claim_review_feedback(session['id'], expected_revision=3),
                   lambda: store.update_review_draft(session['id'], expected_revision=3, answer='late', revealed=False),
                   lambda: store.update_review_image(session['id'], expected_revision=3, submission=None)]:
        with pytest.raises(ValueError):
            action()
    with pytest.raises(ValueError, match='revision changed'):
        store.finish_review_feedback(session['id'], expected_revision=3, run_id='another-run', feedback=FEEDBACK, question_revision=record.content_revision)
    assert store.get_review_session(session['id'])['revision'] == claimed['revision']


def test_failed_provider_releases_lease_retains_photo_and_safe_error(setup):
    _, store, _, session, tasks = setup
    def fail(*args):
        raise ValueError('secret-provider-key')
    with pytest.raises(RuntimeError, match='图片批改暂不可用') as caught:
        grade_review(store, session['id'], 2, task_store=tasks, generate=fail)
    assert 'secret-provider-key' not in str(caught.value)
    restored = store.get_review_session(session['id'])
    assert restored['revision'] == 4 and not restored.get('grading') and not restored['revealed']
    assert restored['current_submission']['filename'] == '解答.png'
    assert store.claim_review_feedback(session['id'], expected_revision=4)['grading']


def test_expired_run_can_be_retried_without_accepting_late_feedback(setup, monkeypatch):
    import memory.mistake_lifecycle as module
    _, store, record, session, _ = setup
    old = store.claim_review_feedback(session['id'], expected_revision=2)
    monkeypatch.setattr(module.time, 'time', lambda: old['grading']['expires_at'] + 1)
    assert not public_review_session(store.get_review_session(session['id']), 'default')['grading']
    new = store.claim_review_feedback(session['id'], expected_revision=3)
    assert new['grading']['run_id'] != old['grading']['run_id']
    with pytest.raises(ValueError, match='revision changed'):
        store.finish_review_feedback(session['id'], expected_revision=3, run_id=old['grading']['run_id'], feedback=FEEDBACK, question_revision=record.content_revision)
    saved = store.finish_review_feedback(session['id'], expected_revision=4, run_id=new['grading']['run_id'], feedback=FEEDBACK, question_revision=record.content_revision)
    assert saved['revealed'] and saved['revision'] == 5


def test_changed_question_cannot_receive_old_feedback(setup):
    book, store, record, session, tasks = setup
    def changed(*args):
        fresh = book.get(record.id)
        fresh.content_revision += 1
        book.store.update(fresh)
        return FEEDBACK, {}
    with pytest.raises(ValueError, match='题目已修改'):
        grade_review(store, session['id'], 2, task_store=tasks, generate=changed)
    assert not store.get_review_session(session['id'])['revealed']
    assert not store.get_review_session(session['id']).get('grading')


def test_unreadable_photo_does_not_reveal_reference_and_can_be_replaced(setup):
    _, store, record, session, tasks = setup
    visual = VisualProblemIR(required_inputs=[{'blocking': True, 'reason': 'missing page'}])
    def no_reasoning(*args):
        pytest.fail('uncertain input must not invoke answer model')
    generated = partial(generate_feedback, analyze=lambda *args, **kwargs: visual, invoke=no_reasoning)
    updated = grade_review(store, session['id'], 2, task_store=tasks, generate=generated)
    assert updated['feedback']['verdict'] == 'unreadable'
    assert not updated['revealed']
    updated = store.update_review_image(session['id'], expected_revision=updated['revision'], submission=None)
    assert not updated.get('feedback')


@pytest.mark.parametrize('raw', ['{}', '{"verdict":"correct","summary":{},"issues":[],"suggestions":[]}',
    '{"verdict":"wrong","summary":"修改","issues":[],"suggestions":[]}',
    json.dumps({**FEEDBACK, 'summary': '{"schema_version":"visual-problem-ir/v2"}'})])
def test_feedback_rejects_missing_or_internal_payload(raw):
    with pytest.raises(ValueError):
        parse_feedback(raw)


def test_feedback_filters_thinking_and_preserves_math():
    result = parse_feedback('<think>private reasoning</think>' + json.dumps(FEEDBACK))
    assert result['suggestions'] == [r'改为 $1+1=2$。']
    assert 'private' not in json.dumps(result)
    raw = r'{"verdict":"partial","summary":"检查 $\frac12+\theta$。","issues":["符号错误"],"suggestions":["重新计算"]}'
    assert parse_feedback(raw)['summary'] == r'检查 $\frac12+\theta$。'


def test_review_image_api_private_projection_recovery_and_result(monkeypatch, tmp_path):
    from backend.api import mistake_lifecycle as api
    from backend.services.mistake_images import MistakeImageStore
    book = MistakeBook(tmp_path / 'api.db')
    record = MistakeRecord(question_text='1+1', correct_answer='2')
    book.add(record)
    store = MistakeLifecycleStore(book.store)
    session = store.create_review_session([record.id], scope='default')
    images = MistakeImageStore(tmp_path / 'images', frozenset({'.png'}), 200000, 1600, 86, 86400)
    tasks = LearningTaskStore(tmp_path / 'tasks')
    monkeypatch.setattr(api, '_store', lambda _: store)
    monkeypatch.setattr(api, '_mb', lambda _: book)
    monkeypatch.setattr(api, '_image_store', images)
    monkeypatch.setattr(api, 'grade_review', partial(grade_review, task_store=tasks, generate=lambda *args: (FEEDBACK, {'handwritten_work': ['PRIVATE']})))
    app = FastAPI(); app.include_router(api.review_router)
    client = TestClient(app)
    image = io.BytesIO(); Image.new('RGB', (80, 80), 'white').save(image, format='PNG')
    url = f'/review/sessions/{session["id"]}'
    upload = client.post(url + '/image', data={'expected_revision': 1}, files={'file': ('work.png', image.getvalue(), 'image/png')})
    assert upload.status_code == 200
    assert 'original_path' not in upload.text and 'work_path' not in upload.text
    assert client.get(url + '/image').status_code == 200
    assert client.get(url + '/image?preview=true').status_code == 200
    assert client.post(url + '/image', data={'expected_revision': 1}, files={'file': ('work.png', image.getvalue(), 'image/png')}).status_code == 409
    graded = client.post(url + '/feedback', json={'expected_revision': 2})
    assert graded.status_code == 200, graded.text
    assert 'PRIVATE' not in graded.text
    restored = client.get(url).json()['data']
    assert restored['feedback']['verdict'] == 'wrong' and restored['revealed']
    assert restored['current_item']['correct_answer'] == '2'
    assert 'PRIVATE' not in json.dumps(restored)
    assert client.post(url + '/image/remove', json={'expected_revision': restored['revision']}).status_code == 422
    assert len(store.list_attempts(record.id)) == 0
    assert client.post(url + '/results', json={'expected_revision': restored['revision'], 'operation_id': 'confirm', 'result': 'independent_correct'}).status_code == 200
    assert len(store.list_attempts(record.id)) == 1
