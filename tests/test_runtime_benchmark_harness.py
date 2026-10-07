"""Regression tests for measurement integrity, not synthetic model accuracy."""
import copy
import json
from pathlib import Path

import pytest

from evaluation.runtime_benchmark.adapter import FakeAdapter, snapshot_identity
from evaluation.runtime_benchmark.diagnostics import extract, diagnose, performance
from evaluation.runtime_benchmark.prompting import PromptBuilder, smoke_case
from evaluation.runtime_benchmark.runner import run, replay, validate_config
from evaluation.runtime_benchmark.scoring import Benchmark, read_json


@pytest.fixture(scope='module')
def benchmark():
    from evaluation.runtime_benchmark.scoring import DEFAULT_MANIFEST, DEFAULT_BENCHMARK
    manifest = read_json(DEFAULT_MANIFEST)
    if not DEFAULT_BENCHMARK.exists():
        pytest.skip('external author-frozen V0 release unavailable; supply local release for integration tests')
    return Benchmark()


@pytest.fixture
def config():
    return {'model_path': '/local/self-test', 'model_id': 'fake', 'seed': 0,
            'tuned_on_v0': False, 'v0_failure_exposed': False, 'texa_trained': False, 'running_alone': False}


def test_scope_and_all_split_denominators(benchmark):
    expected = {'primary_semantic': [77, 32, 36, 16], 'secondary_semantic': [21, 8, 6, 4],
                'semantic_all': [98, 40, 42, 20], 'all': [150, 60, 60, 30]}
    for scope, counts in expected.items():
        assert [len(benchmark.select(scope, split)) for split in ('train', 'dev', 'test', 'hidden_test')] == counts
        assert len(benchmark.select(scope)) == sum(counts)
    assert all(r['track'] == 'semantic' for r in benchmark.select('semantic_all'))


def test_missing_duplicate_unknown_wrong_scope(benchmark):
    rows = benchmark.select('primary_semantic')
    report = benchmark.score(rows, [])
    assert len(report['results']) == 161
    assert all(r['reason'] == 'missing_prediction' for r in report['results'])
    item = {'id': rows[0]['id'], 'raw_output': '{}'}
    for records in ([item, item], [{'id': 'unknown', 'raw_output': '{}'}],
                    [{'id': benchmark.select('secondary_semantic')[0]['id'], 'raw_output': '{}'}]):
        with pytest.raises(ValueError):
            benchmark.score(rows, records)


def test_prompt_boundary(benchmark):
    builder = PromptBuilder(benchmark)
    row = benchmark.rows[0]
    limited = {key: row[key] for key in ('id', 'task', 'input')}
    messages = builder.build(limited)
    assert builder.build({**limited, 'id': 'not-in-text'}) == messages
    assert messages[1]['content'] == benchmark.scorer.canonical(row['input'])
    with pytest.raises(ValueError):
        builder.build(row)
    assert messages[0]['content'].startswith(builder.tasks['wire'])
    assert 'output schema:' in messages[0]['content']


@pytest.mark.parametrize('wrapper,bucket', [('{}', 'S'), ('说明\n```json\n{}\n```', 'F'),
                                         ('<think>思考 {{"action_id":"a1"}}</think>\n{}', 'F')])
def test_strict_never_replaced_by_recovery(benchmark, wrapper, bucket):
    row = benchmark.rows[0]
    raw = wrapper.format(benchmark.scorer.canonical(row['gold']))
    official = benchmark.scorer.evaluate(row, raw)
    detail = diagnose(row, raw, official, benchmark.scorer)
    assert detail['bucket'] == bucket
    assert official['structured_match'] == (bucket == 'S')
    assert raw == wrapper.format(benchmark.scorer.canonical(row['gold']))


@pytest.mark.parametrize('raw', [
    '{"action_id":"a0"} {"action_id":"a1"}',
    '{"outer":{"action_id":"a0"}}', '[{"action_id":"a0"}]',
    '{"action_id":"a0","action_id":"a1"}', '{"action_id":NaN}',
    '<think>unfinished {"action_id":"a0"}', '{"action_id":"a0"',
    '{"action_id":"a0","extra":1}', "{'action_id':'a0'}",
    'prose {"action_id":"a0"} {', '"{\\"action_id\\":\\"a0\\"}"',
    '<think><think>x</think></think>{"action_id":"a0"}',
    '</think>{"action_id":"a0"}',
])
def test_no_inner_selection_or_repair(benchmark, raw):
    row = benchmark.rows[0]
    official = benchmark.scorer.evaluate(row, raw)
    assert diagnose(row, raw, official, benchmark.scorer)['bucket'] == 'U'


def test_strings_brackets_and_source_offsets(benchmark):
    raw = '<think>ignored [ { </think>说明\n```json\n{"s":"brace } [ and \\\" quote"}\n```'
    got = extract(raw, benchmark.scorer.json_strict)
    assert got['status'] == 'unique_payload'
    assert raw[slice(*got['source_range'])] == got['extracted_text']
    assert benchmark.scorer.json_strict(got['extracted_text'])['s'].startswith('brace')


def test_t_and_profile_limited_u(benchmark):
    row = benchmark.rows[0]
    raw = '{"action_id":"a1"}'
    assert diagnose(row, raw, benchmark.scorer.evaluate(row, raw), benchmark.scorer)['bucket'] == 'T'
    goal = next(r for r in benchmark.rows if r['task'] == 'goal_summary')
    prediction = copy.deepcopy(goal['gold'])
    prediction['objective'] += '；用另一种说法表达目标'
    raw = benchmark.scorer.canonical(prediction)
    detail = diagnose(goal, raw, benchmark.scorer.evaluate(goal, raw), benchmark.scorer)
    assert detail['bucket'] == 'U' and 'profile_limited' in detail['tags']
    prediction = copy.deepcopy(goal['gold'])
    prediction['objective'] = '；'.join(goal['metadata']['objective_atoms'][:-1])
    raw = benchmark.scorer.canonical(prediction)
    assert diagnose(goal, raw, benchmark.scorer.evaluate(goal, raw), benchmark.scorer)['bucket'] == 'T'


def test_percentiles_same_token_time_population():
    outputs = [{'case_id': str(i), 'status': 'ok', 'request_ms': i, 'generated_tokens': 2} for i in range(1, 21)]
    outputs.append({'case_id': 'bad', 'status': 'error', 'request_ms': 9999, 'generated_tokens': 9999})
    outputs.append({'case_id': 'unknown-token', 'status': 'ok', 'request_ms': 21, 'generated_tokens': None})
    perf = performance(outputs)
    assert perf['p50_ms'] == 11 and perf['p95_ms'] == 20
    assert perf['token_rate_n'] == 20
    assert perf['generated_tokens_per_request_second'] == pytest.approx(40 / .210)
    assert len(perf['failed_requests']) == 1
    assert performance([])['p95_ms'] is None
    assert performance(outputs[:2])['tail_sample_insufficient']


def test_config_rejects_unrecorded_generation(config):
    assert validate_config(config)['max_new_tokens']['policy_select'] == 128
    with pytest.raises(ValueError):
        validate_config({**config, 'temperature': .5})
    with pytest.raises(ValueError):
        validate_config({**config, 'v0_failure_exposed': None})


def test_first_answer_raw_saved_before_scoring_and_no_retry(benchmark, config, tmp_path, monkeypatch):
    rows = benchmark.select('primary_semantic')
    raws = [benchmark.scorer.canonical(row['gold']) for row in rows]
    raws[0] = '说明\n```json\n' + raws[0] + '\n```'
    adapter = FakeAdapter(['{"action_id":"warm-answer"}', *raws])
    out = tmp_path / 'primary'
    original = benchmark.score
    def check_saved(selected, predictions):
        saved = (out / 'outputs.jsonl').read_text().splitlines()
        assert len(saved) == 161
        assert json.loads(saved[0])['raw_output'] == raws[0]
        return original(selected, predictions)
    monkeypatch.setattr(benchmark, 'score', check_saved)
    state = run(benchmark, 'primary_semantic', config, out, adapter)
    assert state['status'] == 'complete'
    assert state['purpose'] == 'fake_adapter_self_test'
    assert len(adapter.calls) == 162
    summary = read_json(out / 'diagnostics.json')['screening']['primary_semantic']
    assert summary['N'] == 161 and sum(summary[k] for k in 'SFTU') == 161
    assert summary['S'] == 160 and summary['F'] == 1
    assert read_json(out / 'official-report.json')['results'][0]['structured_match'] is False
    with pytest.raises(FileExistsError):
        run(benchmark, 'primary_semantic', config, out, adapter)


def test_incomplete_keeps_remaining_in_denominator(benchmark, config, tmp_path):
    adapter = FakeAdapter(['{"action_id":"warm-answer"}', RuntimeError('OOM')])
    state = run(benchmark, 'primary_semantic', config, tmp_path / 'incomplete', adapter)
    assert state['status'] == 'incomplete'
    assert len(adapter.calls) == 2
    report = read_json(tmp_path / 'incomplete/diagnostics.json')
    assert report['screening']['primary_semantic']['N'] == 161
    assert report['screening']['primary_semantic']['U'] == 161
    assert len(state['unrequested_case_ids']) == 160


def test_fake_metadata_does_not_change_quality_and_replay_preserves_time(benchmark, config, tmp_path):
    paths = []
    for tier in ('primary_semantic', 'secondary_semantic'):
        raws = [benchmark.scorer.canonical(row['gold']) for row in benchmark.select(tier)]
        path = tmp_path / tier
        run(benchmark, tier, config, path, FakeAdapter(['{"action_id":"warm-answer"}', *raws]))
        paths.append(path)
    state = replay(benchmark, paths, 'semantic_all', tmp_path / 'combined')
    assert state['status'] == 'complete'
    assert state['completed_requests'] == 200
    combined = read_json(tmp_path / 'combined/diagnostics.json')
    assert combined['screening']['semantic_all']['S'] == 200
    assert read_json(tmp_path / 'combined/official-report.json')['primary_semantic_without_upstream_conflicts']['n'] == 198
    assert combined['screening']['primary_semantic']['N'] == 161
    assert combined['performance']['successful_latency_n'] == 200
    assert combined['performance']['p95_ms'] == 1
    with pytest.raises(ValueError, match='overlap'):
        replay(benchmark, [paths[0], paths[0]], 'semantic_all', tmp_path / 'bad')
    with pytest.raises(ValueError, match='union'):
        replay(benchmark, [paths[0]], 'semantic_all', tmp_path / 'bad2')
    # Different metadata for identical raw has identical quality (no adapter score input).
    raws = [benchmark.scorer.canonical(row['gold']) for row in benchmark.select('secondary_semantic')]
    run(benchmark, 'secondary_semantic', config, tmp_path / 'metadata',
        FakeAdapter(['{"action_id":"warm-answer"}', *raws], {'load_ms': 99, 'device': 'different'}))
    assert read_json(tmp_path / 'metadata/diagnostics.json')['screening'] == read_json(paths[1] / 'diagnostics.json')['screening']
    # Corrupt JSONL must error; no silent truncation.
    with (paths[1] / 'outputs.jsonl').open('a') as handle:
        handle.write('{broken')
    with pytest.raises(ValueError):
        replay(benchmark, paths, 'semantic_all', tmp_path / 'corrupt')


def test_quantization_not_directory_name(tmp_path):
    path = tmp_path / 'Qwen3.5-0.8B-MLX-8bit'
    path.mkdir()
    (path / 'model.safetensors').write_bytes(b'test')
    config = {'model_type': 'qwen3_5', 'text_config': {'hidden_size': 1024, 'num_hidden_layers': 24},
              'quantization': {'bits': 4, 'group_size': 64}}
    (path / 'config.json').write_text(json.dumps(config))
    with pytest.raises(ValueError, match='8bit'):
        snapshot_identity(path)
    config['quantization']['bits'] = 8
    (path / 'config.json').write_text(json.dumps(config))
    assert snapshot_identity(path)['quantization']['bits'] == 8


def test_replay_rejects_changed_config_and_messages(benchmark, config, tmp_path):
    paths = []
    for tier in ('primary_semantic', 'secondary_semantic'):
        path = tmp_path / tier
        raws = [benchmark.scorer.canonical(r['gold']) for r in benchmark.select(tier)]
        run(benchmark, tier, config, path, FakeAdapter(['{"action_id":"warm-answer"}', *raws]))
        paths.append(path)
    state_path = paths[1] / 'run.json'
    original = state_path.read_text()
    state = json.loads(original)
    state['identity']['config']['seed'] = 42
    state_path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match='differs'):
        replay(benchmark, paths, 'semantic_all', tmp_path / 'config-changed')
    state_path.write_text(original)
    requests_path = paths[1] / 'requests.jsonl'
    records = [json.loads(line) for line in requests_path.read_text().splitlines()]
    records[0]['messages'][1]['content'] += '\nextra instruction'
    requests_path.write_text(''.join(json.dumps(x) + '\n' for x in records))
    with pytest.raises(ValueError, match='messages'):
        replay(benchmark, paths, 'semantic_all', tmp_path / 'prompt-changed')


def test_operational_failure_retains_valid_raw_official_success(benchmark, config, tmp_path):
    class PartialFailure(FakeAdapter):
        def generate(self, messages, generation_config):
            result = super().generate(messages, generation_config)
            if len(self.calls) == 2:
                result.update(status='error', error='device failed after raw was available')
            return result
    raw = benchmark.scorer.canonical(benchmark.rows[0]['gold'])
    adapter = PartialFailure(['{"action_id":"warm-answer"}', raw])
    out = tmp_path / 'partial'
    assert run(benchmark, 'primary_semantic', config, out, adapter)['status'] == 'incomplete'
    official = read_json(out / 'official-report.json')['results'][0]
    assert official['structured_match'] and official['severity'] == 'S0'
    failures = [json.loads(line) for line in (out / 'failures.jsonl').read_text().splitlines()]
    assert failures[0]['raw_output'] == raw
    assert failures[0]['bucket'] == 'S' and failures[0]['operational_status'] == 'error'


def test_freeze_verified_before_import(tmp_path):
    import hashlib
    root = tmp_path / 'release'
    root.mkdir()
    (root / 'pinned').write_text('changed')
    freeze = root / 'FREEZE.json'
    freeze.write_text(json.dumps({'sha256': {'pinned': 'bad hash'}}))
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'freeze_sha256': hashlib.sha256(freeze.read_bytes()).hexdigest(),
                                    'source_release': str(root)}))
    with pytest.raises(ValueError, match='freeze_mismatch'):
        Benchmark(manifest=manifest)


def test_control_never_in_screening_even_in_full_self_test(benchmark, tmp_path):
    from evaluation.runtime_benchmark.reporting import publish
    outputs = [{'case_id': r['id'], 'raw_output': benchmark.scorer.canonical(r['gold']),
                'status': 'ok', 'request_ms': 1, 'generated_tokens': None} for r in benchmark.rows]
    report = publish(benchmark, benchmark.rows, outputs, tmp_path,
                     {'run_id': 'self-test-all', 'scope': 'all', 'purpose': 'fake_adapter_self_test', 'status': 'complete'})
    assert report['screening']['semantic_all']['N'] == 200
    assert set(report['screening']['semantic_all']['by_task']) == {
        'policy_select', 'goal_summary', 'question_understanding', 'reference_resolve'}
    assert len(read_json(tmp_path / 'official-report.json')['results']) == 300


def test_gemma_identity_uses_architecture_and_quantization(tmp_path):
    path = tmp_path / 'arbitrary-cache-directory'
    path.mkdir()
    (path / 'model.safetensors').write_bytes(b'identity-only fixture')
    config = {'model_type': 'gemma3_text', 'architectures': ['Gemma3ForCausalLM'],
              'hidden_size': 1152, 'num_hidden_layers': 26, 'vocab_size': 262144,
              'quantization': {'bits': 8, 'group_size': 64}}
    (path / 'config.json').write_text(json.dumps(config))
    assert snapshot_identity(path)['model_type'] == 'gemma3_text'
    config['quantization']['bits'] = 4
    (path / 'config.json').write_text(json.dumps(config))
    with pytest.raises(ValueError, match='8bit'):
        snapshot_identity(path)
    config['quantization']['bits'] = 8
    config['hidden_size'] = 2560
    (path / 'config.json').write_text(json.dumps(config))
    with pytest.raises(ValueError, match='architecture'):
        snapshot_identity(path)


def test_qwen3_06b_identity_rejects_wrong_scale_and_quantization(tmp_path):
    path = tmp_path / 'snapshot'
    path.mkdir()
    (path / 'model.safetensors').write_bytes(b'identity-only fixture')
    config = {'model_type': 'qwen3', 'architectures': ['Qwen3ForCausalLM'],
              'hidden_size': 1024, 'num_hidden_layers': 28, 'vocab_size': 151936,
              'intermediate_size': 3072, 'quantization': {'bits': 8, 'group_size': 64}}
    (path / 'config.json').write_text(json.dumps(config))
    assert snapshot_identity(path)['model_type'] == 'qwen3'
    config['quantization']['bits'] = 4
    (path / 'config.json').write_text(json.dumps(config))
    with pytest.raises(ValueError, match='8bit'):
        snapshot_identity(path)
    config['quantization']['bits'] = 8
    config['num_hidden_layers'] = 36
    (path / 'config.json').write_text(json.dumps(config))
    with pytest.raises(ValueError, match='architecture'):
        snapshot_identity(path)


def test_offline_harness_import_does_not_require_resource():
    import subprocess
    import sys
    code = '''
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'resource' or name.startswith('mlx'):
        raise ImportError('unavailable on Windows/offline')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from evaluation.runtime_benchmark.runner import replay, run
from evaluation.runtime_benchmark.scoring import Benchmark
assert len(Benchmark().rows) == 300
'''
    subprocess.run([sys.executable, '-X', 'utf8', '-c', code], check=True)


def test_final_adapter_path_is_explicit_config_only(config):
    final = validate_config({**config, 'adapter_path': 'policy-sft-runs/final/adapter', 'texa_trained': True})
    assert final['adapter_path'] == 'policy-sft-runs/final/adapter'
    assert 'adapter_path' not in validate_config(config)
