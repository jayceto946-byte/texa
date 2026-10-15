"""Adjacent correctness checks for the C1/C2/C3 delta only."""
import pytest

from backend.services.agent_runtime import chat_binding
from backend.services.agent_runtime.contracts import RuntimeConflict
from tests.test_checkpoint_acceptance_edges import _write_proposal


def admitted_then_fenced(tmp_path, monkeypatch):
    parts = _write_proposal(tmp_path, monkeypatch)
    service, runtime, goal, task, registry, pending, writer, call, kwargs = parts
    original = runtime.start_approved_tool
    def interleave(*args, **kw):
        result = original(*args, **kw)
        service.pause(goal['id'], expected_revision=2)
        return result
    monkeypatch.setattr(runtime, 'start_approved_tool', interleave)
    with pytest.raises(RuntimeConflict):
        writer.confirm(task['id'], call['id'], **kwargs)
    monkeypatch.setattr(runtime, 'start_approved_tool', original)
    assert pending.domain_receipt(call['id']) is not None
    assert runtime.task_snapshot(task['id'])['tool_calls'][0]['status'] == 'unknown'
    return parts


@pytest.mark.parametrize('mismatch', ['args_hash', 'scope', 'task_id', 'proposal'])
def test_receipt_accounting_rejects_mismatched_frozen_identity(tmp_path, monkeypatch, mismatch):
    service, runtime, goal, task, registry, pending, writer, call, kwargs = admitted_then_fenced(tmp_path, monkeypatch)
    before = runtime.task_snapshot(task['id'])
    task_id = task['id']
    if mismatch == 'args_hash':
        kwargs['args_hash'] = 'incorrect'
    elif mismatch == 'scope':
        kwargs['scope'] = {'book_name': 'different', 'subject': ''}
    elif mismatch == 'task_id':
        task_id = 'rtask_unrelated'
    else:
        action = pending.get(call['id'])
        action['payload']['question_text'] = 'different question'
        pending.save(action)
    monkeypatch.setattr(pending, 'confirm', lambda _: pytest.fail('must not execute a write'))
    with pytest.raises(RuntimeConflict):
        writer.confirm(task_id, call['id'], **kwargs)
    assert runtime.task_snapshot(task['id']) == before


def test_unknown_without_receipt_stays_fenced(tmp_path, monkeypatch):
    service, runtime, goal, task, registry, pending, writer, call, kwargs = _write_proposal(tmp_path, monkeypatch)
    def fail_without_receipt(_):
        raise OSError('domain write unavailable')
    monkeypatch.setattr(pending, 'confirm', fail_without_receipt)
    result = writer.confirm(task['id'], call['id'], **kwargs)
    assert result['tool_calls'][0]['status'] == 'unknown'
    assert pending.domain_receipt(call['id']) is None
    monkeypatch.setattr(pending, 'confirm', lambda _: pytest.fail('unknown may not be retried'))
    monkeypatch.setattr(chat_binding, 'runtime_store', lambda: runtime)
    monkeypatch.setattr(chat_binding, 'build_registry', lambda: registry)
    before = runtime.task_snapshot(task['id'])
    with pytest.raises(RuntimeConflict):
        chat_binding.resolve_runtime_action(call['id'], 'confirm', pending)
    assert runtime.task_snapshot(task['id']) == before


@pytest.mark.parametrize('stage', ['running', 'unknown'])
def test_reject_never_revokes_admitted_write(tmp_path, monkeypatch, stage):
    service, runtime, goal, task, registry, pending, writer, call, kwargs = _write_proposal(tmp_path, monkeypatch)
    runtime.confirm_approval(call['id'], actor_id='user', args_hash=call['args_hash'], scope=kwargs['scope'])
    snap = runtime.task_snapshot(task['id'])
    resumed = runtime.resume(task['id'], expected_revision=snap['task_revision'], request_key='admission', request_id='admission', owner_token='admitter', turn_id='')
    runtime.start_approved_tool(resumed['run']['id'], 'admitter', call['id'])
    if stage == 'unknown':
        service.pause(goal['id'], expected_revision=2)
    before = runtime.task_snapshot(task['id'])
    assert before['tool_calls'][0]['status'] == stage
    with pytest.raises(RuntimeConflict):
        runtime.reject_approval(call['id'], actor_id='user', interrupt_task=True)
    assert runtime.task_snapshot(task['id']) == before


def test_committed_pause_retry_does_not_pause_reactivated_same_goal(tmp_path, monkeypatch):
    from backend.services.goals.service import GoalService
    from backend.services.goals.store import GoalStore
    from backend.services.learning_state import LearningStateService
    from memory.learning_events import LearningEventStore
    events = LearningEventStore(tmp_path / 'events.db')
    service = GoalService(GoalStore(tmp_path / 'goals.db'), events)
    goal = service.create(learner_id='local_default', title='goal', objective='', scope={'book_name':'book'})
    service.activate(goal['id'], expected_revision=1)
    learning = LearningStateService(progress_root=tmp_path, event_store=events)
    append = events.append
    def fail(event):
        if event.event_type == 'goal_paused':
            raise OSError('projection failed')
        return append(event)
    monkeypatch.setattr(events, 'append', fail)
    with pytest.raises(OSError):
        learning.apply_operation({'operation':'pause_learning'}, book_name='book', source_id='pause-once')
    monkeypatch.setattr(events, 'append', append)
    reactivated = service.activate(goal['id'], expected_revision=3)
    result = learning.apply_operation({'operation':'pause_learning'}, book_name='book', source_id='pause-once')
    assert service.store.get(goal['id']) == reactivated
    assert result['active_goal']['status'] == 'active'
