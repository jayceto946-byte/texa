"""HTTP pre-network reservation, not a model or paid acceptance test."""
import hashlib,importlib.util,json
from pathlib import Path
import httpx,pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('paid_acceptance',ROOT/'scripts/qa-deepseek-production-paid.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

def setup(tmp_path):
    plan=ROOT/'docs/qa/evidence/deepseek-production/PAID-ACCEPTANCE-PLAN.json'
    approval={'approved':True,'plan_sha256':hashlib.sha256(plan.read_bytes()).hexdigest()}
    return mod.Budget(plan,approval,tmp_path/'receipts.json')

def test_gate_reserves_before_http_and_denies_retry(tmp_path):
    budget=setup(tmp_path);budget.select('S1');sent=[]
    def transport(request):
        assert len(budget.rows)==1
        sent.append(True);return httpx.Response(200,json={})
    client=httpx.Client(event_hooks={'request':[budget.before]},transport=httpx.MockTransport(transport))
    body={'model':'deepseek-flash','max_tokens':4096,'messages':[{'role':'user','content':'test'}]}
    client.post('https://api.deepseek.com/chat/completions',json=body)
    with pytest.raises(PermissionError):client.post('https://api.deepseek.com/chat/completions',json=body)
    assert len(sent)==1
    row=budget.rows[0]
    assert row['input_cap']==32768 and row['output_cap']==4096
    assert 'test' not in json.dumps(row)

@pytest.mark.parametrize('host,changes',[('api.deepseek.com',{'max_tokens':9000}),('api.deepseek.com',{'messages':[{'role':'user','content':'x'*32768}]}),('example.invalid',{}),('api.deepseek.com',{'model':'deepseek-v4-pro'})])
def test_bad_request_never_reaches_transport(tmp_path,host,changes):
    budget=setup(tmp_path);budget.select('S1')
    client=httpx.Client(event_hooks={'request':[budget.before]},transport=httpx.MockTransport(lambda _:pytest.fail('network reached')))
    body={'model':'deepseek-flash','max_tokens':4096,'messages':[{'role':'user','content':'x'}],**changes}
    with pytest.raises(PermissionError):client.post('https://'+host+'/chat/completions',json=body)
    assert not budget.rows

def test_global_request_fence_and_approval(tmp_path):
    budget=setup(tmp_path);budget.select('S5')
    body={'model':'deepseek-flash','max_tokens':4096,'messages':[{'role':'user','content':'x'}]}
    for _ in range(5):
        budget.before(httpx.Request('POST','https://api.deepseek.com/chat/completions',json=body))
        budget.rows[-1]['status']='returned'
    with pytest.raises(PermissionError):budget.before(httpx.Request('POST','https://api.deepseek.com/chat/completions',json=body))
    assert len(budget.rows)==5
    with pytest.raises(PermissionError):mod.Budget(mod.PLAN,{'approved':False},tmp_path/'bad.json')


def test_qa_profile_writer_keeps_inherited_credential_only_in_ram(tmp_path, monkeypatch):
    import os
    from backend.api import system
    path = tmp_path / 'local.env'
    monkeypatch.setattr(system, 'ENV_PATH', path)
    monkeypatch.setenv('LLM_CREDENTIAL_DEEPSEEK_API_KEY', 'private-fixture-key')
    mod.persist_qa_config(system._write_env_values, {
        'LLM_CREDENTIAL_DEEPSEEK_API_KEY': 'private-fixture-key',
        'LLM_REASONING_MODEL': 'deepseek-flash',
    })
    assert path.read_text() == 'LLM_REASONING_MODEL=deepseek-flash\n'
    assert os.environ['LLM_CREDENTIAL_DEEPSEEK_API_KEY'] == 'private-fixture-key'


def test_qa_full_profile_save_path_never_persists_credentials(tmp_path, monkeypatch):
    from backend.api import system
    from llm import profiles
    from llm.configuration import model_settings_payload
    monkeypatch.setattr(system, 'ENV_PATH', tmp_path / 'local.env')
    monkeypatch.setattr(profiles, 'PROFILE_PATH', tmp_path / 'model_profiles.json')
    monkeypatch.setenv('LLM_REASONING_PROVIDER', 'deepseek')
    monkeypatch.setenv('LLM_REASONING_MODEL', 'deepseek-flash')
    monkeypatch.setenv('LLM_REASONING_CREDENTIAL_ID', 'deepseek')
    monkeypatch.setenv('LLM_CREDENTIAL_DEEPSEEK_API_KEY', 'private-full-path-fixture')
    original = system._write_env_values
    monkeypatch.setattr(system, '_write_env_values', lambda values: mod.persist_qa_config(original, values))
    payload = model_settings_payload({})
    payload.update(id='qa-remediation', name='QA', multimodal_mode='native')
    for role in ('reasoning', 'vision'):
        payload['roles'][role].update(provider='deepseek', model='deepseek-flash', credential_id='deepseek')
        payload['credentials'][role]['api_key'] = 'private-full-path-fixture'
    result = system.save_model_profile({'profile': payload, 'activate': True})
    assert result['success']
    assert 'private-full-path-fixture' not in (tmp_path / 'local.env').read_text()
    assert 'private-full-path-fixture' not in (tmp_path / 'model_profiles.json').read_text()
    assert 'private-full-path-fixture' not in json.dumps(result)


def test_new_s1_plan_enforces_one_request_and_new_budget(tmp_path):
    plan = ROOT / 'docs/qa/evidence/deepseek-remediation/PAID-S1-PLAN.json'
    budget = mod.Budget(plan, {'approved': True, 'plan_sha256': hashlib.sha256(plan.read_bytes()).hexdigest()}, tmp_path / 'receipts.json')
    budget.select('S1')
    request = httpx.Request('POST', 'https://api.deepseek.com/chat/completions', json={'model': 'deepseek-flash', 'max_tokens': 8192, 'messages': []})
    budget.before(request)
    assert budget.rows[0]['reserved_cost'] < .03
    assert budget.rows[0]['output_cap'] == 8192
    budget.rows[0]['status'] = 'returned'
    with pytest.raises(PermissionError):
        budget.before(request)
    with pytest.raises(ValueError):
        budget.select('S5')
    wrong_hash = {'approved': True, 'plan_sha256': 'not-the-new-plan'}
    with pytest.raises(PermissionError):
        mod.Budget(plan, wrong_hash, tmp_path / 'bad.json')
