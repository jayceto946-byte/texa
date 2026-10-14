"""Acceptance probes copied unchanged from the 7617 review, plus repair guards."""
import pytest

from backend.services.agent_runtime import locator, chat_binding
from backend.services.agent_runtime.contracts import RuntimeConflict
from backend.services.goals.service import GoalService
from backend.services.goals.store import GoalStore
from backend.services.learning_state import LearningStateService
from memory.learning_events import LearningEventStore
from tests.test_checkpoint_remediation import goal_run


def test_pause_retry_after_projection_failure_does_not_pause_new_goal(tmp_path, monkeypatch):
    events = LearningEventStore(tmp_path / 'events.db')
    learning = LearningStateService(progress_root=tmp_path, event_store=events)
    goals = GoalService(GoalStore(tmp_path / 'goals.db'), events)
    first = goals.create(learner_id='local_default', title='A', objective='', scope={'book_name': 'book'})
    goals.activate(first['id'], expected_revision=1)
    append = events.append
    def fail_pause(event):
        if event.event_type == 'goal_paused':
            raise OSError('projection unavailable after Goal commit')
        return append(event)
    monkeypatch.setattr(events, 'append', fail_pause)
    with pytest.raises(OSError):
        learning.apply_operation({'operation': 'pause_learning'}, book_name='book', source_id='same-preparation')
    assert goals.store.get(first['id'])['status'] == 'paused'
    monkeypatch.setattr(events, 'append', append)
    second = goals.create(learner_id='local_default', title='B', objective='', scope={'book_name': 'book'})
    goals.activate(second['id'], expected_revision=1)
    learning.apply_operation({'operation': 'pause_learning'}, book_name='book', source_id='same-preparation')
    assert goals.store.get(second['id'])['status'] == 'active', 'Retry of the pause of A must not pause B'


@pytest.mark.parametrize('operation', ['update', 'complete'])
def test_admitted_receipt_remains_reconcilable_after_goal_change(tmp_path, monkeypatch, operation):
    from backend.services.agent_runtime.write_service import RuntimeWriteService
    from backend.services.agent_runtime.write_tools import register_receipt_backed_write_tools
    from backend.services.pending_actions import PendingActionStore
    from backend.tools.registry import ToolContext, ToolRegistry
    service, runtime, goal, task, _ = goal_run(tmp_path, monkeypatch)
    snapshot = runtime.task_snapshot(task['id'])
    registry = ToolRegistry()
    register_receipt_backed_write_tools(registry)
    pending = PendingActionStore(tmp_path / 'pending')
    writer = RuntimeWriteService(runtime, registry, pending)
    proposed = writer.propose(snapshot['run']['id'], snapshot['run']['owner_token'], tool_id='save_mistake',
        args={'book_name': 'math', 'question_text': '2+2?'}, operation_key='save', context=ToolContext(book_name='math'))
    call = proposed['tool_calls'][0]
    admit = runtime.start_approved_tool
    def interleave(*args, **kwargs):
        result = admit(*args, **kwargs)
        if operation == 'update':
            service.update(goal['id'], expected_revision=2, changes={'objective': 'new objective'})
        else:
            service.measure(goal['id'], expected_revision=2, evidence_by_criterion={}, user_confirms_completion=True)
        return result
    monkeypatch.setattr(runtime, 'start_approved_tool', interleave)
    with pytest.raises(RuntimeConflict):
        writer.confirm(task['id'], call['id'], actor_id='user', args_hash=call['args_hash'],
            scope={'book_name': 'math', 'subject': ''}, expected_revision=proposed['task_revision'],
            resume_request_key='approve', request_id='request', owner_token='owner2', turn_id='')
    # Real domain receipt: this was an admitted write and has actually committed.
    receipt = pending.domain_receipt(call['id'])
    assert receipt is not None
    assert runtime.task_snapshot(task['id'])['tool_calls'][0]['status'] == 'unknown'
    monkeypatch.setattr(runtime, 'start_approved_tool', admit)
    monkeypatch.setattr(chat_binding, 'runtime_store', lambda: runtime)
    monkeypatch.setattr(chat_binding, 'build_registry', lambda: registry)
    chat_binding.resolve_runtime_action(call['id'], 'confirm', pending)
    result = runtime.task_snapshot(task['id'])
    assert result['tool_calls'][0]['status'] == 'succeeded'
    assert result['run']['status'] != 'running'
    assert pending.domain_receipt(call['id']) == receipt


def test_goal_scope_projection_does_not_inherit_other_goal_location(tmp_path):
    events = LearningEventStore(tmp_path / 'events.db')
    goals = GoalService(GoalStore(tmp_path / 'goals.db'), events)
    a = goals.create(learner_id='local_default', title='A', objective='',
        scope={'book_name':'book', 'chapter_name':'Chapter A', 'target_id':'a'})
    goals.activate(a['id'], expected_revision=1)
    b = goals.create(learner_id='local_default', title='B', objective='',
        scope={'book_name':'book', 'chapter_name':'Chapter B', 'target_id':'b'})
    goals.activate(b['id'], expected_revision=1)
    goals.pause(b['id'], expected_revision=2)
    state = LearningStateService(progress_root=tmp_path, event_store=events).get_state(book_name='book')
    assert state['active_goal']['goal_id'] == a['id']
    assert state['active_goal']['chapter_name'] == 'Chapter A'


def test_pause_after_approval_before_resume_does_not_leave_fake_unknown(tmp_path, monkeypatch):
    from backend.services.agent_runtime.write_service import RuntimeWriteService
    from backend.services.agent_runtime.write_tools import register_receipt_backed_write_tools
    from backend.services.pending_actions import PendingActionStore
    from backend.tools.registry import ToolContext, ToolRegistry
    service, runtime, goal, task, _ = goal_run(tmp_path, monkeypatch)
    snapshot = runtime.task_snapshot(task['id'])
    registry = ToolRegistry()
    register_receipt_backed_write_tools(registry)
    pending = PendingActionStore(tmp_path / 'pending')
    writer = RuntimeWriteService(runtime, registry, pending)
    proposed = writer.propose(snapshot['run']['id'], snapshot['run']['owner_token'], tool_id='save_mistake',
        args={'book_name': 'math', 'question_text': '2+2?'}, operation_key='save', context=ToolContext(book_name='math'))
    call = proposed['tool_calls'][0]
    confirm = runtime.confirm_approval
    def interleave(*args, **kwargs):
        result = confirm(*args, **kwargs)
        service.pause(goal['id'], expected_revision=2)
        return result
    monkeypatch.setattr(runtime, 'confirm_approval', interleave)
    with pytest.raises(RuntimeConflict):
        writer.confirm(task['id'], call['id'], actor_id='user', args_hash=call['args_hash'],
            scope={'book_name': 'math', 'subject': ''}, expected_revision=proposed['task_revision'],
            resume_request_key='approve', request_id='request', owner_token='owner2', turn_id='')
    assert pending.domain_receipt(call['id']) is None
    public = locator.public_task(runtime, runtime.task_snapshot(task['id']))
    from backend.services.goals import execution
    service.activate(goal['id'], expected_revision=3)
    restarted = execution.start_goal(service, goal['id'], expected_revision=4, request_key='start-after-reactivate')
    assert restarted['id'] == task['id']
    assert restarted['status'] == public['status']
    assert public['artifacts']['pending_actions'][0]['status'] != 'unknown', 'No write was admitted; this is not an uncertain write'
    assert public['status'] in {'interrupted', 'cancelled'}, 'Pause must leave a usable stopped state'


@pytest.mark.parametrize('operation, event_type', [
    ('pause_learning', 'goal_paused'), ('complete_goal', 'goal_completed'),
])
@pytest.mark.parametrize('already_stopped', [False, True])
def test_preparation_binding_survives_restart_and_later_goal_revision(tmp_path, monkeypatch, operation, event_type, already_stopped):
    events = LearningEventStore(tmp_path / 'events.db')
    goals = GoalService(GoalStore(tmp_path / 'goals.db'), events)
    a = goals.create(learner_id='local_default', title='A', objective='', scope={'book_name': 'book'})
    goals.activate(a['id'], expected_revision=1)
    learning = LearningStateService(progress_root=tmp_path, event_store=events)
    if already_stopped:
        learning.apply_operation({'operation': operation}, book_name='book')
    append = events.append
    def fail_projection(event):
        if event.event_type == event_type:
            raise OSError('projection failed after commit')
        return append(event)
    monkeypatch.setattr(events, 'append', fail_projection)
    with pytest.raises(OSError):
        learning.apply_operation({'operation': operation}, book_name='book', source_id='preparation')
    committed = goals.store.projected_operation(learner_id='local_default', source_id='preparation')
    assert committed['id'] == a['id']
    # Subsequent updates must not inherit the earlier operation identity.
    goals.update(a['id'], expected_revision=committed['revision'], changes={'title': 'A renamed'})
    assert '_projection_source_id' not in goals.store.get(a['id'])
    assert '_projection_source_id' not in goals.store.revisions(a['id'])[-1]
    b = goals.create(learner_id='local_default', title='B', objective='', scope={'book_name': 'book'})
    goals.activate(b['id'], expected_revision=1)
    restarted_events = LearningEventStore(tmp_path / 'events.db')
    restarted = LearningStateService(progress_root=tmp_path, event_store=restarted_events)
    for _ in range(2):
        restarted.apply_operation({'operation': operation}, book_name='book', source_id='preparation')
    assert goals.store.get(b['id'])['status'] == 'active'
    assert goals.store.get(b['id'])['revision'] == 2
    projected = [event for event in restarted_events.list_recent() if event.source_id == 'preparation']
    assert len(projected) == 1
    assert projected[0].id == f"evt_{a['id']}_{committed['revision']}"


def _write_proposal(tmp_path, monkeypatch):
    from backend.services.agent_runtime.write_service import RuntimeWriteService
    from backend.services.agent_runtime.write_tools import register_receipt_backed_write_tools
    from backend.services.pending_actions import PendingActionStore
    from backend.tools.registry import ToolContext, ToolRegistry
    service, runtime, goal, task, _ = goal_run(tmp_path, monkeypatch)
    snapshot = runtime.task_snapshot(task['id'])
    registry = ToolRegistry()
    register_receipt_backed_write_tools(registry)
    pending = PendingActionStore(tmp_path / 'pending')
    writer = RuntimeWriteService(runtime, registry, pending)
    proposed = writer.propose(snapshot['run']['id'], snapshot['run']['owner_token'], tool_id='save_mistake',
        args={'book_name': 'math', 'question_text': '2+2?'}, operation_key='save', context=ToolContext(book_name='math'))
    call = proposed['tool_calls'][0]
    confirm_args = dict(actor_id='user', args_hash=call['args_hash'], scope={'book_name': 'math', 'subject': ''},
        expected_revision=proposed['task_revision'], resume_request_key='approve', request_id='request', owner_token='owner2', turn_id='')
    return service, runtime, goal, task, registry, pending, writer, call, confirm_args


def test_receipt_reconciliation_preserves_owner_and_closed_events_after_restart(tmp_path, monkeypatch):
    from backend.services.agent_runtime.store import RuntimeStore
    from backend.services.execution_events import validate_execution_event_sequence
    service, runtime, goal, task, registry, pending, writer, call, kwargs = _write_proposal(tmp_path, monkeypatch)
    admit = runtime.start_approved_tool
    def fence(*args, **kw):
        result = admit(*args, **kw)
        service.update(goal['id'], expected_revision=2, changes={'objective': 'changed'})
        return result
    monkeypatch.setattr(runtime, 'start_approved_tool', fence)
    with pytest.raises(RuntimeConflict):
        writer.confirm(task['id'], call['id'], **kwargs)
    receipt = pending.domain_receipt(call['id'])
    fenced = runtime.task_snapshot(task['id'])
    assert fenced['tool_calls'][0]['attempt_count'] == 1
    restarted = RuntimeStore(runtime.db_path)
    monkeypatch.setattr(chat_binding, 'runtime_store', lambda: restarted)
    monkeypatch.setattr(chat_binding, 'build_registry', lambda: registry)
    monkeypatch.setattr(pending, 'confirm', lambda _: pytest.fail('receipt accounting must not execute'))
    monkeypatch.setattr(registry, 'runtime_tool', lambda _: pytest.fail('receipt accounting must not re-admit a contract'))
    for _ in range(2):
        chat_binding.resolve_runtime_action(call['id'], 'confirm', pending)
    current = restarted.task_snapshot(task['id'])
    assert current['run']['id'] == fenced['run']['id']
    assert current['run']['owner_token'] == fenced['run']['owner_token']
    assert current['run']['status'] == 'paused'
    assert current['run']['output'] == fenced['run']['output']
    assert current['task_revision'] == fenced['task_revision']
    assert current['tool_calls'][0]['executed_run_id'] == fenced['tool_calls'][0]['executed_run_id']
    assert current['tool_calls'][0]['attempt_count'] == 1
    assert current['tool_calls'][0]['result']['domain_receipt'] == receipt
    assert current['execution_events'] == fenced['execution_events']
    validate_execution_event_sequence(current['execution_events'])


def test_receipt_accounting_does_not_stop_a_later_owner(tmp_path, monkeypatch):
    service, runtime, goal, task, registry, pending, writer, call, kwargs = _write_proposal(tmp_path, monkeypatch)
    admit = runtime.start_approved_tool
    def fence(*args, **kw):
        result = admit(*args, **kw)
        service.pause(goal['id'], expected_revision=2)
        return result
    monkeypatch.setattr(runtime, 'start_approved_tool', fence)
    with pytest.raises(RuntimeConflict):
        writer.confirm(task['id'], call['id'], **kwargs)
    service.activate(goal['id'], expected_revision=3)
    current = runtime.task_snapshot(task['id'])
    newer = runtime.resume(task['id'], expected_revision=current['task_revision'], request_key='later',
        request_id='later-request', owner_token='later-owner', turn_id='')
    monkeypatch.setattr(chat_binding, 'runtime_store', lambda: runtime)
    monkeypatch.setattr(chat_binding, 'build_registry', lambda: registry)
    monkeypatch.setattr(pending, 'confirm', lambda _: pytest.fail('must not execute'))
    chat_binding.resolve_runtime_action(call['id'], 'confirm', pending)
    after = runtime.task_snapshot(task['id'])
    assert after['run'] == newer['run']
    assert after['task_revision'] == newer['task_revision']
    assert after['tool_calls'][0]['executed_run_id'] != newer['run']['id']


@pytest.mark.parametrize('boundary', ['confirm_approval', 'resume'])
def test_unadmitted_confirmation_is_revoked_but_task_can_continue(tmp_path, monkeypatch, boundary):
    from backend.services.goals import execution
    service, runtime, goal, task, _, pending, writer, call, kwargs = _write_proposal(tmp_path, monkeypatch)
    original = getattr(runtime, boundary)
    def fence(*args, **kw):
        result = original(*args, **kw)
        service.pause(goal['id'], expected_revision=2)
        return result
    monkeypatch.setattr(runtime, boundary, fence)
    with pytest.raises(RuntimeConflict):
        writer.confirm(task['id'], call['id'], **kwargs)
    monkeypatch.setattr(runtime, boundary, original)
    current = runtime.task_snapshot(task['id'])
    assert current['task']['status'] == 'interrupted'
    assert current['approvals'][0]['status'] == 'rejected'
    assert current['tool_calls'][0]['status'] == 'denied'
    assert current['tool_calls'][0]['attempt_count'] == 0
    assert current['tool_calls'][0]['executed_run_id'] is None
    assert pending.domain_receipt(call['id']) is None
    public = locator.public_task(runtime, current)
    assert public['resumable']
    assert public['artifacts']['pending_actions'][0]['status'] == 'rejected'
    service.activate(goal['id'], expected_revision=3)
    assert execution.start_goal(service, goal['id'], expected_revision=4, request_key='after-pause')['id'] == task['id']
    assert execution.resume_goal(service, goal['id'], task_id=task['id'], expected_revision=4, request_key='continue')['status'] == 'running'
    with pytest.raises(RuntimeConflict):
        writer.confirm(task['id'], call['id'], **kwargs)
    assert pending.domain_receipt(call['id']) is None
