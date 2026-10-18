"""Contract regressions; these do not prove real model compliance."""
import asyncio
import json
import pytest
from pydantic import ValidationError
from langchain_core.messages import ToolMessage, messages_from_dict
from backend.tools.math_tools import MathVerifyInput
from backend.tools.registry import ToolContext
from backend.services import exercise_knowledge as service
from knowledge.exercise_structure import validate_diagnosis
from test_exercise_knowledge_structure import attempt_record, catalog, error_payload, proposal
from test_native_math_loop import setup_run, call, SUCCESS


def test_derivative_missing_candidate_names_fields():
    with pytest.raises(ValidationError, match='original, candidate'):
        MathVerifyInput.model_validate({'kind':'derivative','original':'x^2','right':'2*x'})
    assert MathVerifyInput(kind='derivative',original='x^2',candidate='2*x').candidate=='2*x'


def test_unique_quote_locates_frozen_attempt_and_rejects_bad_spans(tmp_path):
    _,_,record,attempt,_=attempt_record(tmp_path)
    payload=error_payload(attempt['answer']);e=payload['errors'][0]
    expected=e.pop('start');end=e.pop('end')
    saved=validate_diagnosis(payload,record=record,attempt=attempt,catalog=catalog(record))
    assert saved['errors'][0]['start']==expected and saved['errors'][0]['end']==end
    e['start']=0;e['end']=end
    with pytest.raises(ValueError,match='span'):
        validate_diagnosis(payload,record=record,attempt=attempt,catalog=catalog(record))
    e.pop('start');e.pop('end')
    for answer in ('法向取反\n法向取反','法向取正'):
        with pytest.raises(ValueError,match='exactly once'):
            validate_diagnosis(payload,record=record,attempt={**attempt,'answer':answer},catalog=catalog(record))
    with pytest.raises(ValueError,match='revision'):
        validate_diagnosis(payload,record=record,attempt={**attempt,'question_revision':-1},catalog=catalog(record))


def test_metadata_envelope_status_and_bad_ids_are_isolated():
    from memory.exercise_bank import ExerciseRecord
    record=ExerciseRecord(question_text='Stokes',chapter='多元微积分')
    context={'catalog':catalog(record),'attempts':[]}
    data={'knowledge':proposal(),'diagnoses':[]}
    body,structure,_,status=service.parse_analysis('正文\n```json\n'+json.dumps(data)+'\n```',context)
    assert body=='正文' and status=='invalid_envelope' and structure['status']=='unclassified'
    for broken in ({**data,'knowledge':{k:v for k,v in proposal().items() if k!='status'}},
                   {**data,'knowledge':{**proposal(),'primary':{'concept_id':'made-up','basis':'fake'}}}):
        body,structure,ds,status=service.parse_analysis('正文'+service.OPEN+json.dumps(broken)+service.CLOSE,context)
        assert body=='正文' and status=='invalid' and not ds and structure['status']=='unclassified'
    body,structure,_,status=service.parse_analysis('正文'+service.OPEN+json.dumps(data)+service.CLOSE,context)
    assert status=='parsed' and structure['primary']['concept_id']=='c1'


def test_invalid_metadata_does_not_claim_saved_classification(tmp_path,monkeypatch):
    from memory.exercise_bank import ExerciseBank,ExerciseRecord
    from knowledge.exercise_structure import validate_classification
    bank=ExerciseBank(tmp_path/'bank.db');record=ExerciseRecord(question_text='Stokes',chapter='多元微积分')
    bank.add(record);record=bank.get(record.id)
    structure=validate_classification({},catalog(record));structure['metadata_status']='invalid'
    job={'status':'completed','exercise_id':record.id,'book_name':'book-a',
         'result':{'answer':'可用正文','knowledge_structure':structure}}
    saved,status=service.save_answer_with_knowledge(bank,record,answer='可用正文',explanation='',book_name='book-a',job=job)
    assert status=='metadata_invalid' and saved.answer=='可用正文' and saved.knowledge_structure=={}


def test_computed_receipt_is_explicitly_unverified(tmp_path):
    store,run,model,runner,state=setup_run(tmp_path,[SUCCESS[0],{'content':'结果是1024。'}])
    result=runner.run_bounded(run,'owner',context=ToolContext(),answer_state=state,answer_generator=lambda _:pytest.fail('no extra model'))
    assert result['task']['status']!='completed'
    assert '尚无通过的独立数学核验' in result['run']['output']['answer']
    assert any('不能称为局部' in str(m.content) for m in model.received[1])


@pytest.mark.parametrize('budget',[0,1])
def test_budget_failure_has_safe_delivery_and_closed_tool_messages(tmp_path,budget):
    store,run,model,runner,state=setup_run(tmp_path,[SUCCESS[0],SUCCESS[1]],budget_calls=budget)
    result=runner.run_bounded(run,'owner',context=ToolContext(),answer_state=state,answer_generator=lambda _:pytest.fail('no extra model'))
    assert result['run']['status']=='failed' and result['task']['status']=='failed'
    assert result['run']['error_code']=='tool_budget_exhausted'
    answer=result['run']['output']['answer']
    assert '任务未完成' in answer and '预算已用尽' in answer
    assert ('1024' in answer)==bool(budget)
    assert 'final_answer' not in result['task']['artifacts']
    messages=messages_from_dict(result['run']['checkpoint']['native_messages'])
    calls=[c['id'] for m in messages for c in getattr(m,'tool_calls',[])]
    assert set(calls)=={m.tool_call_id for m in messages if isinstance(m,ToolMessage)}
    assert len(model.received)==budget+1


def test_failure_sse_replaces_interim_then_emits_error(tmp_path):
    from backend.services.agent_runtime.chat_binding import stream_run
    store,run,model,runner,state=setup_run(tmp_path,[SUCCESS[0]],budget_calls=0)
    store.configure_chat(run,'owner',state=state,candidates=runner.candidate_tools,
        request_question='计算 2^10',book_name='',subject='数学')
    events=[]
    async def consume():
        response=stream_run(store,run,'owner',runner.registry,runner.adapter)
        async for chunk in response.body_iterator:events.append(json.loads(chunk[6:]))
        await response.aclose()
    asyncio.run(consume())
    canonical=[e['execution_event'] for e in events if 'execution_event' in e]
    assert canonical[-1]['type']=='error'
    delivery=next(e for e in canonical if e['type']=='output_delta' and e['payload'].get('replace'))
    assert '任务未完成' in delivery['payload']['text']
    assert delivery['seq']<canonical[-1]['seq']


def test_bad_arguments_at_budget_limit_still_publish_failure(tmp_path):
    response=call('verify_math_result',{'kind':'derivative','original':'x^2','right':'2*x'},'missing-candidate')
    store,run,model,runner,state=setup_run(tmp_path,[response],budget_calls=0)
    result=runner.run_bounded(run,'owner',context=ToolContext(),answer_state=state,answer_generator=lambda _:pytest.fail('no forced final request'))
    assert result['run']['error_code']=='tool_budget_exhausted'
    assert result['task']['status']=='failed' and '任务未完成' in result['run']['output']['answer']
    assert len(model.received)==1 and not result['tool_calls']
