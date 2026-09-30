"""Checkpoint failure regressions with temporary storage and deterministic faults."""
import json
import threading
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest

from backend.services.agent_runtime import locator, chat_binding
from backend.services.agent_runtime.contracts import RunCommand, RuntimeConflict, RuntimeDenied, FixedAction
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.agent_runtime.outbox import RuntimeOutboxProjector
from backend.services.goals import execution
from backend.services.goals.service import GoalService
from backend.services.goals.store import GoalStore
from backend.services.answer_verification import verify_answer, derive_required_outputs
from backend.tools.registry import ToolRegistry
from memory.learning_events import LearningEvent, LearningEventStore
from tests.test_goal_execution import setup

REAL_LAUNCH_WORKER = execution.launch_worker


@pytest.mark.parametrize('support', [
    {'tool_context_pack': {'outputs': [{'tool': 'verify_math_result', 'verification': {'passed': True}}]}},
    {'evidence_items': [{'text': '输入为 2'}]},
])
def test_wrong_numeric_conclusion_never_passes(support):
    assert verify_answer('已知 2，2+2=999。', required_outputs=derive_required_outputs('计算 2+2'), **support)['status'] == 'unverified'


def goal_run(tmp_path, monkeypatch):
    service, runtime, launches = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(locator, 'runtime_store', lambda **kw: runtime)
    goal = service.create(learner_id='local_default', title='学习', objective='计算 2+2')
    task = execution.start_goal(service, goal['id'], expected_revision=1, request_key='first')
    return service, runtime, goal, task, launches


@pytest.mark.parametrize('operation', ['pause', 'update', 'complete'])
def test_lifecycle_fences_old_owner_and_resume(tmp_path, monkeypatch, operation):
    service, runtime, goal, task, _ = goal_run(tmp_path, monkeypatch)
    old = runtime.task_snapshot(task['id'])
    if operation == 'pause':
        service.pause(goal['id'], expected_revision=2)
    elif operation == 'update':
        service.update(goal['id'], expected_revision=2, changes={'objective': '新目标'})
    else:
        service.measure(goal['id'], expected_revision=2, evidence_by_criterion={}, user_confirms_completion=True)
    assert runtime.task_snapshot(task['id'])['task']['status'] == 'interrupted'
    with pytest.raises(RuntimeConflict):
        runtime.start_model_step(old['run']['id'], old['run']['owner_token'])
    with pytest.raises((RuntimeConflict, RuntimeDenied)):
        runtime.resume(task['id'], expected_revision=runtime.task_snapshot(task['id'])['task_revision'],
                       request_key='resume', request_id='r', owner_token='o', turn_id='')


def test_title_and_pause_reactivate_preserve_contract(tmp_path, monkeypatch):
    service, runtime, goal, task, _ = goal_run(tmp_path, monkeypatch)
    service.update(goal['id'], expected_revision=2, changes={'title': '新标题'})
    assert runtime.task_snapshot(task['id'])['run']['status'] == 'running'
    service.pause(goal['id'], expected_revision=3)
    service.activate(goal['id'], expected_revision=4)
    resumed = execution.resume_goal(service, goal['id'], task_id=task['id'], expected_revision=5, request_key='resume')
    assert resumed['active_run_id'] != task['active_run_id']
    assert runtime.task_snapshot(task['id'])['task']['required_outputs']


def test_chat_cannot_resume_goal_origin(tmp_path, monkeypatch):
    from backend.api.chat import resume_chat_task_stream
    from fastapi import HTTPException
    service, runtime, goal, task, _ = goal_run(tmp_path, monkeypatch)
    service.pause(goal['id'], expected_revision=2)
    with pytest.raises(HTTPException) as denied:
        resume_chat_task_stream(task['id'])
    assert denied.value.status_code == 409


def test_goal_save_failure_leaves_safe_interruption(tmp_path, monkeypatch):
    service, runtime, goal, task, _ = goal_run(tmp_path, monkeypatch)
    monkeypatch.setattr(service.store, 'update', lambda *a, **kw: (_ for _ in ()).throw(OSError('save failed')))
    with pytest.raises(OSError):
        service.pause(goal['id'], expected_revision=2)
    assert service.store.get(goal['id'])['status'] == 'active'
    assert runtime.task_snapshot(task['id'])['task']['status'] == 'interrupted'


@pytest.mark.parametrize('boundary', ['configure_chat', 'link'])
def test_partial_initialization_repairs_once_even_with_old_revision(tmp_path, monkeypatch, boundary):
    service, runtime, launches = setup(tmp_path, monkeypatch)
    goal = service.create(learner_id='local_default', title='目标', objective='查看进度')
    target = runtime if boundary == 'configure_chat' else service.store
    original = getattr(target, boundary)
    monkeypatch.setattr(target, boundary, lambda *a, **kw: (_ for _ in ()).throw(OSError('injected')))
    with pytest.raises(OSError):
        execution.start_goal(service, goal['id'], expected_revision=1, request_key='same')
    monkeypatch.setattr(target, boundary, original)
    result = execution.start_goal(service, goal['id'], expected_revision=1, request_key='same')
    assert len(launches) == 1
    assert len(service.store.links(goal['id'])) == 1
    assert runtime.task_snapshot(result['id'])['run']['checkpoint']['answer_state']
    execution.start_goal(service, goal['id'], expected_revision=1, request_key='same')
    assert len(launches) == 1


def test_unlinked_initialized_task_is_fenced_by_pause(tmp_path, monkeypatch):
    service, runtime, _ = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(locator, 'runtime_store', lambda **kw: runtime)
    goal = service.create(learner_id='local_default', title='目标', objective='查看进度')
    monkeypatch.setattr(service.store, 'link', lambda *a, **kw: (_ for _ in ()).throw(OSError()))
    with pytest.raises(OSError):
        execution.start_goal(service, goal['id'], expected_revision=1, request_key='same')
    service.pause(goal['id'], expected_revision=2)
    task_id = runtime.goal_tasks(goal['id'])[0]
    assert runtime.task_snapshot(task_id)['task']['status'] == 'interrupted'


def test_thread_start_failure_cleans_worker_registration(tmp_path, monkeypatch):
    service, runtime, goal, task, _ = goal_run(tmp_path, monkeypatch)
    snapshot = runtime.task_snapshot(task['id'])
    monkeypatch.setattr(threading.Thread, 'start', lambda self: (_ for _ in ()).throw(RuntimeError('start failed')))
    with pytest.raises(RuntimeError):
        REAL_LAUNCH_WORKER(runtime, snapshot['run']['id'], snapshot['run']['owner_token'], ToolRegistry(), None)
    assert snapshot['run']['id'] not in execution._workers
    assert runtime.task_snapshot(task['id'])['task']['status'] == 'interrupted'


def test_outbox_poison_record_isolated_and_fair(tmp_path):
    store = RuntimeStore(tmp_path / 'runtime.db')
    for n in range(4):
        run = store.create(RunCommand(f'k{n}', f'r{n}', f't{n}', 'conv', f'turn{n}', 'question', 'o'))
        store.close(run['run']['id'], 'o', outcome='completed', answer='answer')
    messages = {}
    def append(conv, role, answer, **kw):
        if kw['message_id'] == 'msg_t0':
            raise OSError('poison')
        messages.setdefault(kw['message_id'], {'id': kw['message_id']})
        return messages[kw['message_id']]
    projector = RuntimeOutboxProjector(store, append)
    assert projector.drain_once(limit=2) == 1
    assert projector.drain_once(limit=2) == 2
    assert len(messages) == 3
    pending = store.pending_outbox()
    assert len(pending) == 1 and pending[0]['attempts'] == 1
    assert pending[0]['status'] == 'pending' and 'OSError' in pending[0]['receipt_json']


def test_goal_events_do_not_change_other_goal():
    from backend.services.learning_state_reducer import reduce_learning_events
    events = [LearningEvent(id='b', event_type='goal_created', payload={'goal_id': 'B'}),
              LearningEvent(id='a', event_type='goal_paused', payload={'goal_id': 'A'}),
              LearningEvent(id='legacy', event_type='goal_completed')]
    state = reduce_learning_events(events, learner_id='local_default', book_id='', book_name='', subject='')
    assert state['active_goal']['goal_id'] == 'B' and state['active_goal']['status'] == 'active'
    assert state['guided_progress']['status'] == 'in_progress'


def test_bridge_parses_without_writes_and_operations_reuse_ids(tmp_path, monkeypatch):
    from backend.services.learning_state import LearningStateService
    from backend.services.learning_state_bridge import bridge_learning_request
    import backend.services.learning_state_bridge as bridge
    events = LearningEventStore(tmp_path / 'events.db')
    service = LearningStateService(progress_root=tmp_path, event_store=events)
    monkeypatch.setattr(bridge, 'resolve_chapter_identity', lambda *a, **kw: {'chapter_id': 'c1', 'chapter_name': '第一章'})
    proposal = bridge_learning_request('我要学会第一章', 'set_learning_goal', book_name='book', subject='', conversation_id='conv', service=service)
    assert not (tmp_path / 'goals.db').exists()
    assert events.list_recent() == []
    for _ in range(2):
        service.apply_operation(proposal.state_operations[0], book_name='book', conversation_id='conv', source_id='stable-operation')
    assert len(GoalStore(tmp_path / 'goals.db').list(learner_id='local_default')) == 1
    for _ in range(2):
        service.apply_operation({'operation':'record_weakness', 'concept_names':['函数']}, book_name='book', source_id='stable-weakness')
    assert len(events.list_recent(event_type='weakness_reported')) == 1


def test_retention_preserves_tool_error_and_active_other_run(tmp_path, monkeypatch):
    from backend.services import runtime_events as events
    monkeypatch.setattr(events, '_MAX_ROWS', 2)
    store = events.RuntimeEventStore(tmp_path / 'events.db')
    def event(kind, run, **payload):
        return events.make_event(kind, session_id='s', turn_id='same', run_id=run, payload=payload)
    store.append_many([event('state', 'live', task_status='running'), event('error', 'live'),
                       event('execution_result', 'old', task_status='completed'), event('state', 'new', task_status='running')])
    assert {e['run_id'] for e in store.list(session_id='s')} == {'live', 'new'}


def test_final_adapter_never_fakes_user_outcome_and_keeps_tool_version(monkeypatch):
    from backend.services import runtime_events as events
    observed = []
    monkeypatch.setattr(events, 'emit', lambda kind, **kw: observed.append((kind,kw)))
    events.observe_execution_event({'type':'final', 'conversation_id':'s', 'task_id':'t', 'payload':{'task_status':'completed'}})
    events.observe_execution_event({'type':'tool_result', 'kind':'tool', 'conversation_id':'s', 'payload':{'tool_id':'x','tool_version':'v1'}})
    assert [kind for kind, _ in observed] == ['execution_result', 'tool_call']
    assert observed[-1][1]['payload']['tool_version'] == 'v1'


def test_schedule_covers_beyond_100_and_bad_record_does_not_abort(tmp_path, monkeypatch):
    service = GoalService(GoalStore(tmp_path / 'goals.db'))
    past = (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    for i in range(103):
        goal = service.create(learner_id='local_default', title='goal', objective='inspect', goal_id=f'g{i:03}')
        goal = service.activate(goal['id'], expected_revision=1)
        service.store.update(goal['id'], expected_revision=2, changes={'next_action':{'kind':'schedule','due_at':'invalid' if i==102 else past}})
    visited = []
    monkeypatch.setattr(execution, 'start_goal', lambda svc, gid, **kw: visited.append(gid) or {'status':'completed'})
    execution.GoalScheduleWorker().tick(service)
    assert len(visited) == 102 and 'g000' in visited
    bad = service.store.get('g102')['next_action']
    assert bad['due_at'] == 'invalid' and bad['blocked_reason'] == 'ValueError'


def test_schedule_denied_preserves_due_and_reports_block(tmp_path, monkeypatch):
    service = GoalService(GoalStore(tmp_path / 'goals.db'))
    goal = service.create(learner_id='local_default', title='goal', objective='inspect')
    service.activate(goal['id'], expected_revision=1)
    due = (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    service.store.update(goal['id'], expected_revision=2, changes={'next_action':{'kind':'schedule','due_at':due}})
    monkeypatch.setattr(execution, 'start_goal', lambda *a, **kw: (_ for _ in ()).throw(RuntimeDenied('no model')))
    execution.GoalScheduleWorker().tick(service)
    action = service.store.get(goal['id'])['next_action']
    assert action['due_at'] == due and action['blocked_reason'] == 'RuntimeDenied'


def test_legacy_timeout_capacity_held_until_physical_completion(monkeypatch):
    from backend.services import tool_orchestration as tools
    release = threading.Event()
    finished = threading.Event()
    monkeypatch.setattr(tools, '_TOOL_SLOTS', threading.BoundedSemaphore(1))
    def blocked():
        try:
            release.wait(2)
        finally:
            finished.set()
        return 'late'
    try:
        assert tools._run_bounded(blocked, .005)['status'] == 'timeout'
        rejected = tools._run_bounded(lambda: 'must not start', .005)
        assert rejected['status'] == 'error' and 'capacity' in rejected['message']
    finally:
        release.set()
    assert finished.wait(2)
    assert tools._run_bounded(lambda: 'ok', .5)['value'] == 'ok'


def test_known_missing_input_never_completes(tmp_path):
    from backend.services.agent_runtime.multi_step import BoundedAgentRunner
    from backend.services.agent_runtime.contracts import ModelCapabilities
    store = RuntimeStore(tmp_path / 'runtime.db')
    run = store.create(RunCommand('k','r','t','s','turn','question','o', budget_calls=0,budget_model_calls=1))
    adapter = SimpleNamespace(capabilities=lambda: ModelCapabilities(tool_calling='supported'),
                              next_action=lambda *a: FixedAction('finish',answer='exact 999'))
    result = BoundedAgentRunner(store,ToolRegistry(),adapter,()).run_bounded(run['run']['id'],'o',answer_state={'missing_inputs':['table']},answer_generator=lambda _: 'exact 999')
    assert result['task']['status'] == 'failed' and result['run']['error_code'] == 'required_input_missing'


def test_snapshot_and_final_events_share_one_sql_read_version(tmp_path, monkeypatch):
    store = RuntimeStore(tmp_path / 'runtime.db')
    run = store.create(RunCommand('key','req','task','conv','turn','question','owner'))
    original = store._snapshot
    committed = False
    def interleave(conn, run_id):
        nonlocal committed
        snapshot = original(conn, run_id)
        if not committed:
            committed = True
            store.close(run_id,'owner',outcome='completed',answer='已提交答案')
        return snapshot
    monkeypatch.setattr(store, '_snapshot', interleave)
    snapshot, batch = store.stream_snapshot(run['run']['id'])
    assert snapshot['run']['output'] is None and all(e['type'] != 'final' for e in batch)
    snapshot, batch = store.stream_snapshot(run['run']['id'])
    assert batch[-1]['type'] == 'final' and snapshot['run']['output']['answer'] == '已提交答案'


@pytest.mark.parametrize('status', ['pending', 'expired', 'unknown', 'executed'])
def test_approval_projection_exposes_only_real_actions(tmp_path, status):
    store = RuntimeStore(tmp_path / 'runtime.db')
    run = store.create(RunCommand('key','req','task','conv','turn','question','owner'))
    rid = run['run']['id']
    call = store.request_tool(rid, 'owner', tool_id='save_mistake', version='1',schema_hash='s',args={},args_hash='h',operation_key='o',permission='LOCAL_WRITE')['tool_calls'][0]
    expires = (datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()
    store.await_approval(rid,'owner',call['id'],scope={},expires_at=expires)
    with store._write() as conn:
        if status == 'expired':
            conn.execute("UPDATE runtime_approvals SET expires_at='2000-01-01' WHERE call_id=?", (call['id'],))
        elif status in {'unknown','executed'}:
            conn.execute("UPDATE tool_calls SET status=? WHERE id=?", ('unknown' if status=='unknown' else 'succeeded',call['id']))
    task = locator.public_task(store,store.task_snapshot('task'))
    action = task['artifacts']['pending_actions'][0]
    assert action['status'] == status
    assert action['allowed_actions'] == (['confirm','reject'] if status=='pending' else ['reject'] if status=='expired' else [])
    assert task['confirmation_required'] == (status=='pending')
    if status == 'expired':
        with pytest.raises(RuntimeConflict):
            store.confirm_approval(call['id'],actor_id='user',args_hash='h',scope={})


@pytest.mark.parametrize('pause_boundary', ['after_confirm', 'after_resume', 'after_admit'])
def test_pause_approval_interleavings_allow_only_admitted_write(tmp_path, monkeypatch, pause_boundary):
    from backend.services.agent_runtime.write_service import RuntimeWriteService
    from backend.services.agent_runtime.write_tools import register_receipt_backed_write_tools
    from backend.tools.registry import ToolContext
    from backend.services.pending_actions import PendingActionStore
    service, runtime, goal, task, _ = goal_run(tmp_path, monkeypatch)
    snapshot = runtime.task_snapshot(task['id'])
    registry = ToolRegistry()
    register_receipt_backed_write_tools(registry)
    pending = PendingActionStore(tmp_path / 'pending')
    writes = []
    receipt = {}
    def confirm(cid):
        writes.append(cid)
        receipt.update(mistake_id=cid)
        return {'result':dict(receipt)}
    monkeypatch.setattr(pending, 'confirm', confirm)
    monkeypatch.setattr(pending, 'domain_receipt', lambda _: dict(receipt) or None)
    writer = RuntimeWriteService(runtime,registry,pending)
    paused = writer.propose(snapshot['run']['id'],snapshot['run']['owner_token'],tool_id='save_mistake',
                            args={'book_name':'math','question_text':'2+2?'},operation_key='save',context=ToolContext(book_name='math'))
    cid = paused['tool_calls'][0]['id']
    method = {'after_confirm':'confirm_approval','after_resume':'resume','after_admit':'start_approved_tool'}[pause_boundary]
    original = getattr(runtime, method)
    def interleave(*a,**kw):
        result = original(*a,**kw)
        service.pause(goal['id'],expected_revision=2)
        return result
    monkeypatch.setattr(runtime,method,interleave)
    with pytest.raises(RuntimeConflict):
        writer.confirm(task['id'],cid,actor_id='u',args_hash=paused['tool_calls'][0]['args_hash'],scope={'book_name':'math','subject':''},
                       expected_revision=paused['task_revision'],resume_request_key='approval',request_id='r2',owner_token='owner2',turn_id='')
    assert len(writes) == (1 if pause_boundary=='after_admit' else 0)
    assert service.store.get(goal['id'])['status'] == 'paused'
    if pause_boundary == 'after_admit':
        # The domain fact persists, while the old run cannot publish its late result.
        assert runtime.task_snapshot(task['id'])['tool_calls'][0]['status'] == 'unknown'
        monkeypatch.setattr(runtime,method,original)
        service.activate(goal['id'],expected_revision=3)
        current = runtime.task_snapshot(task['id'])
        reconciled = writer.confirm(task['id'],cid,actor_id='u',args_hash=current['tool_calls'][0]['args_hash'],scope={'book_name':'math','subject':''},
                                   expected_revision=current['task_revision'],resume_request_key='reconcile',request_id='r3',owner_token='owner3',turn_id='')
        assert reconciled['tool_calls'][0]['status'] == 'succeeded' and len(writes)==1


def test_fixed_runner_capacity_is_shared_across_instances(tmp_path, monkeypatch):
    from backend.services.agent_runtime import runner as module
    from backend.tools.registry import ToolSpec, ToolResult
    from pydantic import BaseModel
    class Input(BaseModel):
        pass
    class Output(BaseModel):
        pass
    release = threading.Event()
    exited = threading.Event()
    monkeypatch.setattr(module, '_TOOL_SLOTS', threading.BoundedSemaphore(1))
    def handler(*args):
        try:
            release.wait(2)
            return ToolResult(True,data={})
        finally:
            exited.set()
    registry = ToolRegistry()
    registry.register(ToolSpec(name='blocked',description='read',parameters={},read_only=True,handler=handler,
                              runtime_input=Input,runtime_output=Output,permission='READ',side_effect='none',source='builtin',timeout_seconds=.005))
    store = RuntimeStore(tmp_path / 'runtime.db')
    ids = [store.create(RunCommand(f'k{i}',f'r{i}',f't{i}','s',f'turn{i}','q','o'))['run']['id'] for i in range(2)]
    try:
        first = module.FixedRunner(store,registry,allowlist=frozenset({'blocked'})).execute(ids[0],'o',FixedAction('call',tool_id='blocked',operation_key='op'))
        assert first['tool_calls'][0]['error_code']=='timeout'
        with pytest.raises(RuntimeDenied,match='capacity'):
            module.FixedRunner(store,registry,allowlist=frozenset({'blocked'})).execute(ids[1],'o',FixedAction('call',tool_id='blocked',operation_key='op'))
        assert store.snapshot(ids[1])['consumed_calls']==0
    finally:
        release.set()
    assert exited.wait(2)


def test_model_type_error_does_not_invoke_again(monkeypatch):
    from graph import planner
    calls = []
    class Model:
        def invoke(self,*args,**kw):
            calls.append(1)
            raise TypeError('inside model')
    monkeypatch.setattr(planner,'get_llm',lambda **kw: Model())
    # Keep the model fault independent of any real textbook/vector store.
    monkeypatch.setattr('graph.safe_retrieval.get_safe_vector_store', lambda: (SimpleNamespace(get_chapter_names=lambda **kw: ['第一章']), ''))
    with pytest.raises(TypeError):
        planner.plan_node({'user_input':'请比较这几章的关系','target_chapters':['第一章'],'_local_intent_locked':False})
    assert calls == [1]


def test_retried_pause_does_not_pause_later_goal_in_same_scope(tmp_path):
    from backend.services.learning_state import LearningStateService
    events = LearningEventStore(tmp_path / 'events.db')
    learning = LearningStateService(progress_root=tmp_path,event_store=events)
    goals = GoalService(GoalStore(tmp_path / 'goals.db'),events)
    first = goals.create(learner_id='local_default', title='first',objective='',scope={'book_name':'book'})
    goals.activate(first['id'],expected_revision=1)
    learning.apply_operation({'operation':'pause_learning'},book_name='book',source_id='pause-once')
    second = goals.create(learner_id='local_default', title='second',objective='',scope={'book_name':'book'})
    goals.activate(second['id'],expected_revision=1)
    learning.apply_operation({'operation':'pause_learning'},book_name='book',source_id='pause-once')
    assert goals.store.get(second['id'])['status']=='active'
    assert len([e for e in events.list_recent() if e.event_type=='goal_paused'])==1


def test_existing_goal_run_without_digest_can_be_fenced_but_not_resumed(tmp_path,monkeypatch):
    service,runtime,goal,task,_=goal_run(tmp_path,monkeypatch)
    snapshot=runtime.task_snapshot(task['id'])
    checkpoint=snapshot['run']['checkpoint']
    checkpoint.pop('goal_contract')
    checkpoint['answer_state'].pop('_goal_contract')
    with runtime._write() as conn:
        conn.execute('UPDATE agent_runs SET checkpoint_json=? WHERE id=?',(json.dumps(checkpoint),snapshot['run']['id']))
    service.pause(goal['id'],expected_revision=2)
    assert runtime.task_snapshot(task['id'])['task']['status']=='interrupted'
    service.activate(goal['id'],expected_revision=3)
    with pytest.raises(RuntimeConflict):
        execution.resume_goal(service,goal['id'],task_id=task['id'],expected_revision=4,request_key='resume-legacy')


def test_missing_worker_after_model_call_requires_explicit_resume(tmp_path,monkeypatch):
    service,runtime,goal,task,launches=goal_run(tmp_path,monkeypatch)
    run=runtime.task_snapshot(task['id'])
    runtime.start_model_step(run['run']['id'],run['run']['owner_token'])
    repeat=execution.start_goal(service,goal['id'],expected_revision=1,request_key='first')
    assert repeat['status']=='interrupted' and len(launches)==1
    assert runtime.task_snapshot(task['id'])['consumed_model_calls']==1


def test_schedule_worker_survives_storage_initialization_failure(tmp_path,monkeypatch):
    import backend.services.goals.store as module
    path=tmp_path/'exists.db';path.touch()
    monkeypatch.setattr(module,'DEFAULT_GOAL_DB_PATH',path)
    monkeypatch.setattr(module,'GoalStore',lambda *a: (_ for _ in ()).throw(OSError('unavailable')))
    worker=execution.GoalScheduleWorker()
    waits=[]
    def wait(timeout):
        waits.append(timeout)
        if len(waits)==2:worker.stop_event.set()
        return worker.stop_event.is_set()
    monkeypatch.setattr(worker.stop_event,'wait',wait)
    worker.start()
    worker.thread.join(timeout=2)
    assert waits==[30,30] and not worker.thread.is_alive()


def test_resume_preparation_skips_original_bridge(monkeypatch):
    from backend.api import chat
    from backend.schemas import ChatRequest
    task=SimpleNamespace(artifacts={'resolved_query':'原问题','resolution_trace':{'learning_bridge':{'action':'recorded','state_operations':[{'operation':'create_goal'}]}}})
    monkeypatch.setattr(chat,'_resolve_request_question',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('must not parse/apply again')))
    monkeypatch.setattr(chat,'resolve_conversation_id_for_scope',lambda *a: 'conv')
    monkeypatch.setattr(chat,'load_history',lambda *a: [])
    prepared=chat._prepare_chat_turn(ChatRequest(question='原问题',conversation_id='conv',turn_id='turn',use_textbook_context=False),resume_task=task,resume=True)
    assert prepared['rewritten_question']=='原问题' and prepared['context_versions']=={}
