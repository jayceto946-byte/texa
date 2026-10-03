from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

import pytest

import backend.conversation_memory as memory
from backend.services.conversation_management import ConversationManagementError, ConversationManagementService
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.agent_runtime.contracts import RunCommand
from backend.services.learning_task import LearningTaskStore


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, 'CONV_DIR', tmp_path / 'conversations')
    monkeypatch.setattr('backend.services.runtime_events.observe_execution_event', lambda event: None)
    return ConversationManagementService(progress_root=tmp_path)


def seed(cid='c1', book='Book'):
    return memory.append_message(cid, 'user', 'Original question', book_name=book, turn_id='t1')


def change(service, action, revision, cid='c1', op=None):
    return service.change(cid, action=action, expected_revision=revision, operation_id=op or f'{cid}-{action}-{revision}')


def test_legacy_defaults_receipts_cas_restore_and_no_content_mutation(service):
    seed()
    before = memory.get_conversation('c1')['messages']
    with sqlite3.connect(service.db_path) as conn:
        events = conn.execute('SELECT COUNT(*) FROM conversation_events').fetchone()[0]
        version = conn.execute('PRAGMA user_version').fetchone()[0]
    assert service.get('new-unsaved')['revision'] == 0
    assert change(service, 'pin', 0)['pinned']
    assert change(service, 'pin', 0)['revision'] == 1  # identical receipt
    with pytest.raises(ConversationManagementError, match='操作标识'):
        change(service, 'unpin', 1, op='c1-pin-0')
    with pytest.raises(ConversationManagementError, match='状态已变化'):
        change(service, 'archive', 0)
    assert change(service, 'archive', 1)['state'] == 'archived'
    assert not service.page()['items']
    assert change(service, 'trash', 2)['previous_state'] == 'archived'
    assert change(service, 'restore', 3)['state'] == 'archived'
    assert change(service, 'restore', 4)['state'] == 'active'
    assert memory.get_conversation('c1')['messages'] == before
    with sqlite3.connect(service.db_path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM conversation_events').fetchone()[0] == events
        assert conn.execute('PRAGMA user_version').fetchone()[0] == version
    reopened = ConversationManagementService(progress_root=service.progress_root)
    assert reopened.get('c1')['revision'] == 5


def test_complete_pinned_filtered_pagination_and_invalid_scope(service):
    for index in range(91):
        seed(f'c{index:03}', 'A' if index % 2 else 'B')
    change(service, 'pin', 0, 'c001')
    cursor = ''
    ids = []
    while True:
        page = service.page(book_names=['A'], limit=7, cursor=cursor)
        ids.extend(row['id'] for row in page['items'])
        if not page['has_more']:
            break
        cursor = page['next_cursor']
    assert ids[0] == 'c001'
    assert len(ids) == len(set(ids)) == 45
    cursor = service.page(book_names=['A'], limit=7)['next_cursor']
    with pytest.raises(ConversationManagementError):
        service.page(book_names=['B'], cursor=cursor)
    with pytest.raises(ConversationManagementError):
        service.page(cursor='invalid')


def test_legacy_busy_cancel_then_trash_and_write_gate(service):
    seed()
    store = LearningTaskStore(service.progress_root)
    task = store.create(task_type='qa', goal='Question', conversation_id='c1', turn_id='t1',
                        artifacts={'active_run_id': 'run1', 'partial_output': 'kept'}, status='interrupted')
    with pytest.raises(ConversationManagementError) as caught:
        change(service, 'archive', 0)
    assert caught.value.code == 'conversation_busy'
    assert caught.value.details['tasks'][0]['can_cancel']
    result = service.cancel_task(task.id, operation_id='cancel1', expected_run_id='run1')
    assert result['status'] == 'cancelled'
    assert store.get(task.id).artifacts['partial_output'] == 'kept'
    assert service.cancel_task(task.id, operation_id='cancel1', expected_run_id='run1') == result
    change(service, 'trash', 0)
    for attempt in (lambda: seed(), lambda: store.create(task_type='qa', goal='new', conversation_id='c1'),
                    lambda: memory.resolve_conversation_id_for_scope('c1', book_name='AnotherBook')):
        with pytest.raises(ConversationManagementError) as caught:
            attempt()
        assert caught.value.code == 'conversation_trashed'
    assert memory.get_conversation('c1')['message_count'] == 1
    change(service, 'restore', 1)
    assert store.create(task_type='qa', goal='new', conversation_id='c1').status == 'running'


def runtime_command(key='key', tid='rtask_1'):
    return RunCommand(key, key, tid, 'c1', 't1', 'Question', 'owner')


def test_runtime_busy_cancel_fences_owner_and_unknown_write(service):
    seed()
    store = RuntimeStore(service.progress_root / 'agent_runtime.db')
    snapshot = store.create(runtime_command())
    run_id = snapshot['run']['id']
    with pytest.raises(ConversationManagementError):
        change(service, 'trash', 0)
    with pytest.raises(ConversationManagementError, match='先停止'):
        service.cancel_task('rtask_1', operation_id='running', expected_run_id=run_id, expected_revision=1)
    paused = store.close(run_id, 'owner', outcome='paused')
    revision = paused['task_revision']
    result = service.cancel_task('rtask_1', operation_id='cancel', expected_run_id=run_id, expected_revision=revision)
    assert result['status'] == 'cancelled' and not result['resumable']
    assert service.cancel_task('rtask_1', operation_id='cancel', expected_run_id=run_id, expected_revision=revision) == result
    assert store.snapshot(run_id)['run']['owner_token'] == ''
    change(service, 'trash', 0)
    with pytest.raises(ConversationManagementError):
        store.create(runtime_command('new', 'rtask_2'))
    change(service, 'restore', 1)
    snapshot = store.create(runtime_command('new', 'rtask_2'))
    run_id = snapshot['run']['id']
    store.request_tool(run_id, 'owner', tool_id='write', version='1', schema_hash='schema', args={}, args_hash='hash', operation_key='write', permission='LOCAL_WRITE')
    store.close(run_id, 'owner', outcome='paused')
    with sqlite3.connect(store.db_path) as conn:
        conn.execute("UPDATE tool_calls SET status='unknown' WHERE task_id='rtask_2'")
    with pytest.raises(ConversationManagementError) as caught:
        change(service, 'archive', 2)
    assert caught.value.details['tasks'][0]['unknown_write']
    with pytest.raises(ConversationManagementError, match='尚未核对'):
        service.cancel_task('rtask_2', operation_id='cancel2', expected_run_id=run_id, expected_revision=store.snapshot(run_id)['task_revision'])


def test_shared_admission_fence_serializes_management_and_task_creation(service):
    seed()
    store = LearningTaskStore(service.progress_root)
    def trash():
        try:
            change(service, 'trash', 0)
            return 'trashed'
        except ConversationManagementError as exc:
            return exc.code
    def start():
        try:
            store.create(task_type='qa', goal='new', conversation_id='c1')
            return 'started'
        except ConversationManagementError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [pool.submit(action) for action in (trash, start)]
        outcomes = {future.result() for future in outcomes}
    assert outcomes in ({'trashed', 'conversation_trashed'}, {'started', 'conversation_busy'})


def test_cursor_invalidation_on_concurrent_navigation_changes(service):
    for cid in ('c1', 'c2', 'c3'):
        seed(cid)
    cursor = service.page(limit=1)['next_cursor']
    change(service, 'pin', 0, 'c1')
    with pytest.raises(ConversationManagementError) as caught:
        service.page(limit=1, cursor=cursor)
    assert caught.value.code == 'invalid_cursor'
    assert service.page(limit=1)['items'][0]['id'] == 'c1'


def test_runtime_admission_race_and_resume_gate(service):
    seed()
    store = RuntimeStore(service.progress_root / 'agent_runtime.db')
    def start():
        try:
            return store.create(runtime_command())['task']['status']
        except ConversationManagementError as exc:
            return exc.code
    def trash():
        try:
            return change(service, 'trash', 0)['state']
        except ConversationManagementError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(action) for action in (start, trash)]
        results = {future.result() for future in futures}
    assert results in ({'running', 'conversation_busy'}, {'conversation_trashed', 'trashed'})
    if service.get('c1')['state'] == 'trashed':
        change(service, 'restore', 1)
        snapshot = store.create(runtime_command())
    else:
        snapshot = store.task_snapshot('rtask_1')
    snapshot = store.close(snapshot['run']['id'], 'owner', outcome='paused')
    # Simulate a restored old snapshot containing a paused task in the trash.
    with sqlite3.connect(service.db_path) as conn:
        conn.execute("INSERT INTO conversation_management VALUES ('c1',0,'trashed',8,'now','active') ON CONFLICT(conversation_id) DO UPDATE SET state='trashed'")
    with pytest.raises(ConversationManagementError) as caught:
        store.resume('rtask_1', expected_revision=snapshot['task_revision'], request_key='resume',
                     request_id='resume', owner_token='other', turn_id='t1')
    assert caught.value.code == 'conversation_trashed'


def test_backup_restore_includes_metadata_receipts_and_independent_assets(service, monkeypatch, tmp_path):
    import backend.data_backup as backup
    data_root = tmp_path / 'data'
    progress = data_root / 'progress'
    monkeypatch.setattr(memory, 'CONV_DIR', progress / 'conversations')
    service = ConversationManagementService(progress_root=progress)
    seed()
    note = progress / 'session_notes.db'
    from memory.session_notes import SessionNoteStore
    SessionNoteStore(note)
    with sqlite3.connect(note) as conn:
        conn.execute('CREATE TABLE frozen_sources (body TEXT)')
        conn.execute("INSERT INTO frozen_sources VALUES ('unchanged frozen source')")
    change(service, 'trash', 0)
    paths = {'DATA_ROOT': data_root, 'MINERU_ROOT': tmp_path / 'mineru',
             'BACKUP_ROOT': tmp_path / 'backups',
             'PENDING_RESTORE_PATH': tmp_path / 'backups/pending_restore.json',
             'RESTORE_RESULT_PATH': tmp_path / 'backups/last_restore.json'}
    for key, value in paths.items():
        monkeypatch.setattr(backup, key, value)
    saved = backup.create_backup()
    change(service, 'restore', 1)
    backup.schedule_restore(saved['name'])
    assert backup.apply_pending_restore()['status'] == 'completed'
    assert service.get('c1')['state'] == 'trashed'
    assert change(service, 'trash', 0)['revision'] == 1  # backed-up receipt
    assert memory.get_conversation('c1')['messages'][0]['content'] == 'Original question'
    with sqlite3.connect(note) as conn:
        assert conn.execute('SELECT body FROM frozen_sources').fetchone()[0] == 'unchanged frozen source'


def test_api_compatibility_and_management_errors(service):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api.chat import router
    app = FastAPI()
    app.include_router(router)
    seed()
    with TestClient(app) as client:
        assert isinstance(client.get('/chat/conversations').json()['data'], list)
        page = client.get('/chat/conversations?view=active&book_names=Book&limit=1').json()['data']
        assert page['items'][0]['management']['revision'] == 0
        assert client.get('/chat/conversations/unsaved/management').json()['data']['state'] == 'active'
        body = {'action': 'trash', 'operation_id': 'api-op', 'expected_revision': 0}
        assert client.post('/chat/conversations/c1/management', json=body).status_code == 200
        assert client.get('/chat/conversations/c1').json()['data']['management']['state'] == 'trashed'
        response = client.post('/chat/stream', json={'question': 'new', 'conversation_id': 'c1'})
        assert response.status_code == 409 and response.json()['code'] == 'conversation_trashed'
        response = client.post('/chat/conversations/c1/management', json={**body, 'operation_id': 'stale', 'action': 'restore'})
        assert response.status_code == 409 and response.json()['code'] == 'revision_conflict'


@pytest.mark.parametrize('backend', ['legacy', 'runtime'])
def test_api_cancel_replay_get_and_old_message_projection(service, backend):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import backend.api.chat as chat
    from backend.services.agent_runtime import locator
    seed()
    if backend == 'legacy':
        store = LearningTaskStore(service.progress_root)
        task = store.create(task_type='qa', goal='Question', conversation_id='c1', turn_id='t1',
                            artifacts={'active_run_id': 'run1', 'partial_output': 'keep'}, status='interrupted')
        task_id, run_id, revision = task.id, 'run1', None
        public = task.to_dict(public=True)
        # Bound default API accessor to the isolated test authority.
    else:
        store = RuntimeStore(service.progress_root / 'agent_runtime.db')
        snapshot = store.create(runtime_command())
        snapshot = store.close(snapshot['run']['id'], 'owner', outcome='paused')
        task_id, run_id, revision = 'rtask_1', snapshot['run']['id'], snapshot['task_revision']
        public = locator.public_task(store, snapshot)
    memory.append_message('c1', 'assistant', 'Partial body retained', turn_id='t1', book_name='Book', learning_task=public)
    for index in range(25):
        memory.append_message('c1', 'user', 'later', turn_id=f'later{index}', book_name='Book')
    app = FastAPI()
    app.include_router(chat.router)
    # monkeypatch context restores each API binding even on failures.
    with pytest.MonkeyPatch.context() as patch:
        if backend == 'legacy':
            patch.setattr(chat, 'get_learning_task_store', lambda: store)
        else:
            patch.setattr(locator, 'runtime_store', lambda **kwargs: store)
        with TestClient(app) as client:
            body = {'operation_id': 'api-cancel', 'expected_run_id': run_id, 'expected_revision': revision}
            result = client.post(f'/chat/tasks/{task_id}/cancel', json=body)
            assert result.status_code == 200
            assert result.json()['learning_task']['status'] == 'cancelled'
            assert client.get(f'/chat/tasks/{task_id}').json()['learning_task']['status'] == 'cancelled'
            # Repeated receipt reprojects safely without a held SQLite transaction.
            assert client.post(f'/chat/tasks/{task_id}/cancel', json=body).json()['data'] == result.json()['data']
            reopened = client.get('/chat/conversations/c1?limit=40').json()['data']
            answer = next(message for message in reopened['messages'] if message['role'] == 'assistant')
            assert answer['learning_task']['status'] == 'cancelled'
            assert answer['content'] == 'Partial body retained'
            assert reopened['message_count'] == 27


def test_restore_validation_legacy_and_future_version(service):
    from backend.services.conversation_management import validate_management_database
    seed()
    validate_management_database(service.db_path)  # old archive has no management table
    change(service, 'pin', 0)
    validate_management_database(service.db_path)
    with sqlite3.connect(service.db_path) as conn:
        conn.execute("UPDATE conversation_management_schema SET version=2")
    with pytest.raises(ValueError, match='unsupported'):
        validate_management_database(service.db_path)


def test_cancel_legacy_pending_action_is_fenced(service):
    from backend.services.pending_actions import PendingActionStore
    seed()
    store = LearningTaskStore(service.progress_root)
    task = store.create(task_type='qa', goal='Question', conversation_id='c1', turn_id='t1',
                        artifacts={'active_run_id': 'run'}, status='waiting_for_confirmation')
    actions = PendingActionStore(service.progress_root)
    action = actions.create({'type': 'add_mistake', 'payload': {}},
                            context={'conversation_id': 'c1', 'learning_task_id': task.id})
    service.cancel_task(task.id, operation_id='cancel', expected_run_id='run')
    assert actions.get(action['action_id'])['status'] == 'rejected'
    with pytest.raises(ValueError):
        actions.confirm(action['action_id'])


def test_frozen_note_source_hash_and_watermark_survive_management(service):
    seed()
    memory.append_message('c1', 'assistant', 'Verified source', book_name='Book', turn_id='t1',
                          sources=[{'id': 'E1', 'text': 'Original evidence'}])
    capture = memory.capture_note_selection('c1')
    for action, rev in [('pin', 0), ('archive', 1), ('trash', 2), ('restore', 3)]:
        change(service, action, rev)
        after = memory.capture_note_selection('c1')
        assert after['input_hash'] == capture['input_hash']
        assert after['watermark'] == capture['watermark']
        assert after['messages'] == capture['messages']


@pytest.mark.parametrize('task_type', ['visual_qa', 'figure_qa'])
def test_cancel_visual_waiting_task_keeps_attachment_and_partial(service, task_type):
    seed()
    attachment = service.progress_root / 'retained-image.png'
    attachment.write_bytes(b'retained fixture attachment')
    store = LearningTaskStore(service.progress_root)
    task = store.create(task_type=task_type, goal='image', conversation_id='c1', turn_id='t1',
                        status='waiting_for_input', artifacts={'active_run_id': 'visual-run',
                            'image_path': str(attachment), 'partial_output': 'partial', 'visual_ir': {'problem_text': 'original'}})
    assert service.blocking_tasks('c1')[0]['can_cancel']
    result = service.cancel_task(task.id, operation_id='visual-cancel', expected_run_id='visual-run')
    assert result['status'] == 'cancelled'
    assert store.get(task.id).artifacts['partial_output'] == 'partial'
    assert attachment.read_bytes() == b'retained fixture attachment'
    assert change(service, 'trash', 0)['state'] == 'trashed'
    independent = store.create(task_type='qa', goal='independent', status='interrupted', artifacts={'active_run_id': 'independent'})
    with pytest.raises(ConversationManagementError):
        service.cancel_task(independent.id, operation_id='invalid', expected_run_id='independent')


def test_cancel_runtime_rejects_pending_approval_and_prevents_execution(service):
    from backend.services.agent_runtime.contracts import RuntimeConflict
    seed()
    store = RuntimeStore(service.progress_root / 'agent_runtime.db')
    run = store.create(runtime_command())
    snapshot = store.request_tool(run['run']['id'], 'owner', tool_id='save_mistake', version='1',
        schema_hash='schema', args={}, args_hash='hash', operation_key='write', permission='LOCAL_WRITE')
    call_id = snapshot['tool_calls'][0]['id']
    snapshot = store.await_approval(run['run']['id'], 'owner', call_id, scope={'conversation_id': 'c1'}, expires_at='2099-01-01')
    result = service.cancel_task('rtask_1', operation_id='cancel-approved', expected_run_id=run['run']['id'],
                                 expected_revision=snapshot['task_revision'])
    assert result['status'] == 'cancelled'
    assert result['artifacts']['pending_actions'][0]['allowed_actions'] == []
    with pytest.raises(RuntimeConflict):
        store.confirm_approval(call_id, actor_id='user', args_hash='hash', scope={'conversation_id': 'c1'})
    assert store.snapshot(run['run']['id'])['tool_calls'][0]['attempt_count'] == 0
    assert change(service, 'trash', 0)['state'] == 'trashed'


def test_visual_http_admission_returns_409_before_images_or_models(service, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import figures, mistakes, mistake_lifecycle
    seed()
    change(service, 'trash', 0)
    app = FastAPI()
    app.include_router(figures.router)
    app.include_router(mistakes.router)
    app.include_router(mistake_lifecycle.router)
    monkeypatch.setattr(figures, '_service', lambda: pytest.fail('should not read figure or call model'))
    monkeypatch.setattr(mistakes, '_ocr_image_with_kimi', lambda *args, **kwargs: pytest.fail('should not call OCR'))
    with TestClient(app) as client:
        response = client.post('/visual-learning/figure-stream', json={
            'conversation_id': 'c1', 'book_name': 'Book', 'figure_id': 'fig', 'question': 'explain'})
        assert response.status_code == 409 and response.json()['code'] == 'conversation_trashed'
        for path in ('/mistakes/solve-image', '/mistakes/solve-image-stream'):
            response = client.post(path, data={'conversation_id': 'c1'}, files={'file': ('fixture.png', b'fixture', 'image/png')})
            assert response.status_code == 409 and response.json()['code'] == 'conversation_trashed'


def test_cancel_reconciles_committed_domain_receipt_in_pending_json(service):
    from backend.services.pending_actions import PendingActionStore, _execute
    seed()
    store = LearningTaskStore(service.progress_root)
    task = store.create(task_type='qa', goal='Question', conversation_id='c1', turn_id='t1',
        artifacts={'active_run_id': 'run'}, status='waiting_for_confirmation')
    actions = PendingActionStore(service.progress_root)
    action = actions.create({'type': 'add_mistake', 'payload': {'question_text': 'Committed question'}},
        context={'conversation_id': 'c1', 'learning_task_id': task.id, 'book_name': 'Book'})
    # Commit the existing domain use case, then simulate a crash before JSON acknowledgement.
    committed = _execute(action, service.progress_root)
    assert actions.get(action['action_id'])['status'] == 'pending'
    task.artifacts['pending_actions'] = [{'action_id': action['action_id'], 'status': 'pending'}]
    store.save(task)
    result = service.cancel_task(task.id, operation_id='cancel-after-write', expected_run_id='run')
    assert result['status'] == 'cancelled'
    recovered = actions.get(action['action_id'])
    assert recovered['status'] == 'confirmed' and recovered['result'] == committed
    assert store.get(task.id).artifacts['pending_actions'][0]['status'] == 'executed'
    # Even after task cancellation, recovery may acknowledge an already committed receipt.
    recovered.update(status='pending', result=None)
    actions.save(recovered)
    assert actions.confirm(action['action_id'])['result'] == committed
    with sqlite3.connect(service.progress_root / 'mistake_book_Book.db') as conn:
        assert conn.execute('SELECT COUNT(*) FROM mistakes').fetchone()[0] == 1


def test_cancel_unknown_domain_receipt_fails_closed(service, monkeypatch):
    from backend.services.pending_actions import PendingActionStore
    seed()
    store = LearningTaskStore(service.progress_root)
    task = store.create(task_type='qa', goal='Question', conversation_id='c1', turn_id='t1',
        artifacts={'active_run_id': 'run'}, status='interrupted')
    actions = PendingActionStore(service.progress_root)
    actions.create({'type': 'add_mistake', 'payload': {'question_text': 'Question'}},
        context={'conversation_id': 'c1', 'learning_task_id': task.id})
    def unavailable(*args):
        raise sqlite3.DatabaseError('unavailable')
    monkeypatch.setattr(PendingActionStore, 'domain_receipt', unavailable)
    with pytest.raises(ConversationManagementError) as caught:
        service.cancel_task(task.id, operation_id='cannot-cancel', expected_run_id='run')
    assert caught.value.code == 'unknown_write'
    assert store.get(task.id).status == 'interrupted'
    with pytest.raises(ConversationManagementError):
        change(service, 'trash', 0)



def test_figure_admission_race_emits_only_canonical_error_boundary(service, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import figures
    from backend.services.execution_events import validate_execution_event, EXECUTION_SSE_FORBIDDEN_LIFECYCLE_FIELDS
    seed()
    def before_admission():
        change(service, 'trash', 0)
        return None
    monkeypatch.setattr(figures, '_service', before_admission)
    app = FastAPI()
    app.include_router(figures.router)
    with TestClient(app) as client:
        response = client.post('/visual-learning/figure-stream', json={
            'conversation_id': 'c1', 'book_name': 'Book', 'figure_id': 'fig', 'question': 'explain'})
    assert response.status_code == 200  # initial preflight won; admission then raced
    envelopes = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert len(envelopes) == 1
    payload = envelopes[0]
    assert not EXECUTION_SSE_FORBIDDEN_LIFECYCLE_FIELDS.intersection(payload)
    event = payload['execution_event']
    validate_execution_event(event)
    assert event['type'] == 'error' and event['status'] == 'failed'
    assert event['payload']['error_code'] == 'conversation_trashed'
    assert event['task_id'] == event['run_id'] == ''
    assert not list((service.progress_root / 'learning_tasks').glob('*.json'))



def test_runtime_cancel_receipt_crash_replays_only_same_operation(service):
    seed()
    store = RuntimeStore(service.progress_root / 'agent_runtime.db')
    snapshot = store.create(runtime_command())
    snapshot = store.close(snapshot['run']['id'], 'owner', outcome='paused')
    # Simulate a committed Runtime cancellation before conversation receipt commit.
    first = store.cancel_task('rtask_1', expected_revision=snapshot['task_revision'],
                             expected_run_id=snapshot['run']['id'], operation_id='crashed-op')
    with pytest.raises(ConversationManagementError) as caught:
        service.cancel_task('rtask_1', expected_revision=snapshot['task_revision'],
            expected_run_id=snapshot['run']['id'], operation_id='other-op')
    assert caught.value.code == 'revision_conflict'
    recovered = service.cancel_task('rtask_1', expected_revision=snapshot['task_revision'],
        expected_run_id=snapshot['run']['id'], operation_id='crashed-op')
    assert recovered == first
