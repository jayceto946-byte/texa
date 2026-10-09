from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.services.mistake_chat_sources import MistakeChatSourceService
from memory.mistake_book import MistakeBookStore, MistakeRecord
from memory.mistake_lifecycle import MistakeLifecycleStore


def service(tmp_path, scope='default'):
    store = MistakeBookStore(tmp_path / f'mistake_book_{scope}.db')
    return MistakeChatSourceService(MistakeLifecycleStore(store), message_reader=lambda conv, mid: {
        "id": mid, "role": "user", "turn_id": "turn", "content": "求极限"
    })


def test_concurrent_capture_reuses_one_draft_and_formal_record_after_review(tmp_path):
    source = service(tmp_path)
    def capture(_):
        return source.capture('conversation', 'message', 'turn', {'question_text': '求极限', 'content_complete': False})
    with ThreadPoolExecutor(max_workers=4) as executor:
        receipts = list(executor.map(capture, range(8)))
    assert all(r == receipts[0] for r in receipts)
    assert source.lookup('conversation', ['message'])[0]['status'] == 'draft'
    draft = source.lifecycle.get_draft(receipts[0]['draft_id'])
    assert draft['stable_source_key'].startswith('chat:')
    with pytest.raises(ValueError, match='correction'):
        candidate = source.lifecycle.create_candidate('manual:' + draft['id'], {k: v for k, v in draft.items() if k not in {'id', 'revision', 'updated_at'}})
        source.lifecycle.resolve_candidate(candidate['id'], accept=True, expected_revision=1, operation_id='incomplete')
    source.lifecycle.update_candidate(candidate['id'], expected_revision=1, changes={'content_complete': True})
    accepted = source.lifecycle.resolve_candidate(candidate['id'], accept=True, expected_revision=2, operation_id='save')
    linked = source.lookup('conversation', ['message'])[0]
    assert linked['status'] == 'recorded'
    assert linked['mistake_id'] == accepted['mistake_id']
    assert capture(0)['status'] == 'recorded'
    with source.lifecycle.store._connect() as conn:
        assert conn.execute('SELECT mistake_id FROM mistake_sources WHERE source_key=?', (draft['stable_source_key'],)).fetchone()[0] == accepted['mistake_id']
        assert conn.execute('SELECT COUNT(*) FROM mistake_drafts').fetchone()[0] == 1
    reopened = service(tmp_path)
    assert reopened.lookup('conversation', ['message'])[0] == linked


def test_complete_legacy_lookup_is_not_limited_to_last_100_and_scopes_do_not_mix(tmp_path):
    source = service(tmp_path, 'bookA')
    ref = source.reference('conversation', 'message')
    first = source.lifecycle.create_draft({'question_text': '历史草稿', 'source_ref': ref})
    for i in range(125):
        source.lifecycle.create_draft({'question_text': f'其他 {i}'})
    assert source.lookup('conversation', ['message'])[0]['draft_id'] == first['id']
    assert source.capture('conversation', 'message', '', {'question_text': '新版'})['draft_id'] == first['id']
    other = service(tmp_path, 'bookB')
    assert other.lookup('conversation', ['message'])[0]['status'] == 'unrecorded'
    other_draft = other.capture('conversation', 'message', '', {'question_text': '其他教材'})
    assert other_draft['draft_id'] != first['id']
    source.lifecycle.store.add(MistakeRecord(id='legacy_record', question_text='旧正式记录', source_ref=ref, visibility='archived'))
    assert source.lookup('conversation', ['message'])[0] == {'message_id': 'message', 'status': 'recorded', 'mistake_id': 'legacy_record', 'visibility': 'archived'}


def test_unpersisted_turn_waits_then_resolves_actual_user_message(monkeypatch, tmp_path):
    from backend import conversation_memory
    source = service(tmp_path)
    monkeypatch.setattr(conversation_memory, 'load_turn_messages', lambda *_, **kwargs: [])
    assert source.lookup('conv', [], ['turn'])[0] == {'turn_id': 'turn', 'message_id': '', 'status': 'pending'}
    monkeypatch.setattr(conversation_memory, 'load_turn_messages', lambda *_, **kwargs: [{'id': 'actual_user_id', 'role': 'user', 'turn_id': 'turn'}, {'id': 'actual_answer_id', 'role': 'assistant', 'turn_id': 'turn'}])
    state = source.lookup('conv', [], ['turn'])[0]
    assert state['message_id'] == 'actual_user_id'
    assert state['status'] == 'unrecorded'
    assert state['turn_id'] == 'turn'


def test_turn_lookup_resolves_all_fresh_questions_from_authoritative_storage(tmp_path, monkeypatch):
    from backend import conversation_memory as cm
    monkeypatch.setattr(cm, 'CONV_DIR', tmp_path / 'conversations')
    expected = {}
    for i in range(7):
        tid = f'turn-{i}'
        user = cm.append_message('conversation', 'user', f'问题 {i}', turn_id=tid)
        cm.append_message('conversation', 'assistant', f'回答 {i}', turn_id=tid)
        expected[tid] = user['id']
    source = service(tmp_path)
    source.message_reader = cm.get_message
    states = source.lookup('conversation', [], [*expected, 'not-persisted'])
    assert {s['turn_id']: s['message_id'] for s in states if s['status'] == 'unrecorded'} == expected
    assert states[-1] == {'turn_id': 'not-persisted', 'message_id': '', 'status': 'pending'}
    capture = source.capture('conversation', expected['turn-6'], 'turn-6', {'question_text': '问题 6'})
    assert source.lookup('conversation', [], list(expected))[-1]['draft_id'] == capture['draft_id']


def test_incomplete_review_lookup_excludes_finished_and_other_subjects(tmp_path):
    source = service(tmp_path)
    source.lifecycle.store.add(MistakeRecord(id='math', question_text='数学题', subject='数学', content_status='ready'))
    review = source.lifecycle.create_review_session(['math'], scope='default')
    assert source.lifecycle.find_incomplete_review_session(subject='数学')['id'] == review['id']
    assert source.lifecycle.find_incomplete_review_session(subject='计算机') is None
    shown = source.lifecycle.update_review_draft(review['id'], expected_revision=1, answer='', revealed=True)
    source.lifecycle.submit_review_result(review['id'], expected_revision=shown['revision'], operation_id='finish-review', result='wrong', hint_used=False, judgement_source='user_confirmed')
    assert source.lifecycle.find_incomplete_review_session(subject='数学') is None
    assert service(tmp_path).lifecycle.find_incomplete_review_session() is None
