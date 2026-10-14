import json
from datetime import datetime, timezone, timedelta
import pytest
from backend.services.goals import execution
from backend.services.goals.service import GoalService
from backend.services.goals.store import GoalStore
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.agent_runtime.contracts import ModelCapabilities, RuntimeDenied
from backend.tools.registry import ToolRegistry
from backend.services.agent_runtime.progress_tool import register_recent_progress_runtime
from memory.learning_events import LearningEventStore


def test_summary_validates_model_output_without_inventing_scope():
    summary = execution.summarize_goal('整理薄弱点', generator=lambda messages: json.dumps({
        'title': '复习薄弱点', 'objective': '根据已有学习记录整理薄弱点', 'success_criteria': [{'description': '列出需复习的概念'}]}))
    assert summary['success_criteria'][0]['id'] == 'criterion-1'
    assert 'scope' not in summary
    with pytest.raises(ValueError):
        execution.summarize_goal('目标', generator=lambda messages: '{"title":"x","objective":"x","success_criteria":[],"code":"bad"}')


def setup(tmp_path, monkeypatch, supported=True):
    service = GoalService(GoalStore(tmp_path / 'goals.db'))
    runtime = RuntimeStore(tmp_path / 'runtime.db')
    registry = ToolRegistry()
    register_recent_progress_runtime(registry, LearningEventStore(tmp_path / 'events.db'))
    monkeypatch.setattr(execution, 'prepare_registry', lambda goal: (registry, (registry.runtime_tool('get_recent_progress').runtime_metadata(),), None))
    monkeypatch.setattr(execution, 'build_adapter', lambda registry: type('Adapter', (), {'capabilities': lambda self: ModelCapabilities(tool_calling='supported' if supported else 'unknown')})())
    monkeypatch.setattr(execution, 'runtime_store', lambda **kwargs: runtime)
    launches = []
    monkeypatch.setattr(execution, 'launch_worker', lambda *args: launches.append(args))
    return service, runtime, launches


def test_explicit_goal_starts_same_sql_runtime_and_fences_duplicate(tmp_path, monkeypatch):
    service, runtime, launches = setup(tmp_path, monkeypatch)
    goal = service.create(learner_id='local_default', title='学习进度', objective='查看学习进度')
    result = execution.start_goal(service, goal['id'], expected_revision=1, request_key='click')
    assert result['conversation_id'] == '' and result['turn_id'] == ''
    run = runtime.snapshot(result['active_run_id'])
    assert run['run']['trigger_kind'] == 'goal'
    assert runtime.events(result['active_run_id'])[0]['origin'] == {'kind':'goal', 'id':goal['id']}
    assert run['run']['checkpoint']['delivery'] == 'goal'
    assert service.store.links(goal['id'])[0]['task_id'] == result['id']
    repeat = execution.start_goal(service, goal['id'], expected_revision=2, request_key='new-click')
    assert repeat['id'] == result['id'] and len(launches) == 1
    from backend.services.agent_runtime import locator
    monkeypatch.setattr(locator, 'runtime_store', lambda: runtime)
    service.pause(goal['id'], expected_revision=2)
    assert runtime.task_snapshot(result['id'])['task']['status'] == 'interrupted'


def test_unverified_configuration_does_not_claim_or_activate_goal(tmp_path, monkeypatch):
    service, runtime, launches = setup(tmp_path, monkeypatch, supported=False)
    goal = service.create(learner_id='local_default', title='学习', objective='复习')
    with pytest.raises(RuntimeDenied):
        execution.start_goal(service, goal['id'], expected_revision=1, request_key='click')
    assert service.store.get(goal['id'])['status'] == 'draft'
    assert not service.store.links(goal['id']) and not launches


def test_schedule_is_explicit_future_time_and_paused_goal_does_not_dispatch(tmp_path, monkeypatch):
    service, runtime, launches = setup(tmp_path, monkeypatch)
    goal = service.create(learner_id='local_default', title='学习', objective='复习')
    service.activate(goal['id'], expected_revision=1)
    due = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    scheduled = execution.schedule_goal(service, goal['id'], expected_revision=2, due_at=due, interval_hours=24)
    assert scheduled['next_action']['interval_hours'] == 24
    with pytest.raises(ValueError):
        execution.schedule_goal(service, goal['id'], expected_revision=3, due_at='2026-01-01T10:00:00', interval_hours=24)
    from backend.services.agent_runtime import locator
    monkeypatch.setattr(locator, 'runtime_store', lambda: runtime)
    service.pause(goal['id'], expected_revision=3)
    execution.GoalScheduleWorker().tick(service)
    assert not launches


def test_goal_background_worker_advances_tools_and_publishes_verified_outcome(tmp_path, monkeypatch):
    import threading
    from backend.services.agent_runtime.contracts import FixedAction
    from backend.services.pending_actions import PendingActionStore
    service = GoalService(GoalStore(tmp_path / 'goals.db'))
    runtime = RuntimeStore(tmp_path / 'runtime.db')
    registry = ToolRegistry()
    register_recent_progress_runtime(registry, LearningEventStore(tmp_path / 'events.db'))
    monkeypatch.setattr(execution, 'runtime_store', lambda **kwargs: runtime)
    monkeypatch.setattr(execution, 'prepare_registry', lambda goal: (registry, (registry.runtime_tool('get_recent_progress').runtime_metadata(),), None))
    class Adapter:
        def capabilities(self):
            return ModelCapabilities(tool_calling='supported')
        def next_action(self, transcript, candidates):
            return FixedAction('call', tool_id='get_recent_progress', args={}) if len(transcript) == 1 else FixedAction('finish', answer='protocol')
    monkeypatch.setattr(execution, 'build_adapter', lambda _: Adapter())
    monkeypatch.setattr(execution, 'generate_answer', lambda _: '近期没有足够的学习记录，请先完成一次练习。')
    import backend.services.pending_actions as actions
    monkeypatch.setattr(actions, 'get_pending_action_store', lambda: PendingActionStore(tmp_path / 'actions'))
    finished = threading.Event()
    original_close = runtime.close
    def close(*args, **kwargs):
        result = original_close(*args, **kwargs)
        finished.set()
        return result
    monkeypatch.setattr(runtime, 'close', close)
    goal = service.create(learner_id='local_default', title='查看学习记录', objective='查看近期进度')
    result = execution.start_goal(service, goal['id'], expected_revision=1, request_key='background')
    assert finished.wait(3)
    snapshot = runtime.task_snapshot(result['id'])
    assert snapshot['task']['status'] in {'completed', 'degraded'}
    assert snapshot['consumed_calls'] == 1 and snapshot['consumed_model_calls'] == 3
    assert snapshot['tool_calls'][0]['status'] == 'succeeded'
    assert service.store.get(goal['id'])['status'] == 'active'
    assert snapshot['run']['output']['answer'] != 'protocol'
    assert not runtime.pending_outbox()
