"""Sequential first-answer run and inference-free replay."""
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from .adapter import MLXAdapter, ProcessAdapter
from .prompting import BUDGETS, PROMPT_VERSION, PromptBuilder, smoke_case
from .reporting import publish
from .scoring import read_json, write_json


def validate_config(config):
    allowed = {'model_path', 'model_id', 'inference_python', 'seed', 'template', 'max_new_tokens',
               'tuned_on_v0', 'v0_failure_exposed', 'texa_trained', 'running_alone', 'required_versions', 'adapter_path'}
    if set(config) - allowed:
        raise ValueError('unsupported config fields: ' + repr(set(config) - allowed))
    for key in ('model_path', 'model_id'):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError('config requires ' + key)
    if 'adapter_path' in config and (not isinstance(config['adapter_path'], str) or not config['adapter_path']):
        raise ValueError('adapter_path must be a nonempty local path')
    for key in ('tuned_on_v0', 'v0_failure_exposed', 'texa_trained', 'running_alone'):
        if type(config.get(key)) is not bool:
            raise ValueError('explicit boolean required: ' + key)
    budgets = {**BUDGETS, **config.get('max_new_tokens', {})}
    if set(budgets) != set(BUDGETS) or any(type(x) is not int or x <= 0 for x in budgets.values()):
        raise ValueError('invalid task token budgets')
    if config.get('seed', 0) is not None and type(config.get('seed', 0)) is not int:
        raise ValueError('seed must be integer or null')
    return {**config, 'max_new_tokens': budgets, 'seed': config.get('seed', 0),
            'template': config.get('template', {'enable_thinking': False})}


def fingerprint(benchmark, config, builder):
    frozen_prompts = {'tasks': builder.tasks, 'schemas': builder.schemas, 'version': PROMPT_VERSION}
    prompt_hash = hashlib.sha256(benchmark.scorer.canonical(frozen_prompts).encode()).hexdigest()
    return {'freeze_sha256': benchmark.freeze_hash, 'scope_manifest_sha256': benchmark.scorer.digest(benchmark.manifest),
            'prompt_version': PROMPT_VERSION, 'prompt_sha256': prompt_hash,
            'config': config, 'generation': {'temperature': 0, 'sampler': 'greedy', 'batch_size': 1,
                                           'max_new_tokens': config['max_new_tokens'], 'seed': config['seed'],
                                           'top_p': 'inactive', 'top_k': 'inactive', 'min_p': 'inactive'}}


def append(handle, value):
    handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
    handle.flush()


def run(benchmark, scope, config, out, adapter=None, smoke=False):
    config = validate_config(config)
    if scope not in ('primary_semantic', 'secondary_semantic'):
        raise ValueError('inference only runs primary or secondary; use replay for semantic_all')
    rows = [] if smoke else benchmark.select(scope)
    builder = PromptBuilder(benchmark)
    out = Path(out).resolve()
    if out.is_relative_to(benchmark.root):
        raise ValueError('cannot write into frozen release')
    out.mkdir(parents=True, exist_ok=False)
    now = datetime.now(timezone.utc).isoformat()
    state = {'run_id': out.name + '-' + now, 'created_at': now, 'status': 'running',
             'purpose': 'synthetic_smoke' if smoke else 'foundation_screening',
             'scope': scope, 'planned_case_ids': [r['id'] for r in rows], 'config': config,
             'benchmark_version': benchmark.manifest['benchmark_version'],
             'scorer_version': 'runtime-benchmark-v0/1', 'scope_manifest_version': benchmark.manifest['version'],
             'identity': fingerprint(benchmark, config, builder),
             'untouched': not any(config[k] for k in ('tuned_on_v0', 'v0_failure_exposed', 'texa_trained')),
             'human_adjudicated': False, 'semantic_test_locked': False}
    if adapter is not None:
        from .adapter import FakeAdapter
        state['purpose'] = 'fake_adapter_self_test' if isinstance(adapter, FakeAdapter) else 'downstream_validation'
        state['untouched'] = False
    write_json(out / 'run.json', state)  # lock config before ANY inference
    adapter = adapter or (ProcessAdapter(config['inference_python']) if config.get('inference_python') else MLXAdapter())
    outputs, fatal = [], None
    with open(out / 'requests.jsonl', 'w', encoding='utf-8') as requests, open(out / 'outputs.jsonl', 'w', encoding='utf-8') as results:
        try:
            state['model'] = adapter.load({**config, '_stderr_path': str(out / 'inference-stderr.log')})
            write_json(out / 'run.json', state)
            synthetic = smoke_case()
            messages = builder.build(synthetic)
            warmup = adapter.generate(messages, {'temperature': 0, 'max_new_tokens': config['max_new_tokens']['policy_select']})
            state['warmup'] = warmup
            state['warmup']['messages'] = messages
            # Same schema/strict scorer, independent synthetic row; not a model benchmark score.
            warmrow = {**synthetic, 'gold': {'action_id': 'warm-answer'}, 'track': 'semantic',
                       'pair_id': 'synthetic-warmup', 'metadata': {}}
            state['warmup']['strict_self_test'] = benchmark.scorer.evaluate(warmrow, warmup.get('raw_output'))
            write_json(out / 'run.json', state)
            if warmup['status'] != 'ok':
                raise RuntimeError('synthetic warmup operational failure: ' + str(warmup.get('error')))
            for row in rows:
                case = {key: row[key] for key in ('id', 'task', 'input')}
                messages = builder.build(case)
                started = time.perf_counter()
                try:
                    output = adapter.generate(messages, {'temperature': 0, 'max_new_tokens': config['max_new_tokens'][row['task']]})
                except Exception as error:
                    output = {'raw_output': None, 'status': 'error', 'error': type(error).__name__ + ': ' + str(error),
                              'finish_reason': None, 'generated_tokens': None, 'token_count_reason': 'adapter failed',
                              'request_ms': (time.perf_counter() - started) * 1000, 'rendered_prompt': None,
                              'template_settings': None}
                output = {**output, 'case_id': row['id'], 'source_run_id': state['run_id']}
                # Raw first, flushed before any scoring. Never sanitize or strip continuation.
                append(results, output)
                outputs.append(output)
                append(requests, {'case_id': row['id'], 'messages': messages,
                                  'rendered_prompt': output.get('rendered_prompt'),
                                  'template_settings': output.get('template_settings'),
                                  'generation_config': {'temperature': 0, 'max_new_tokens': config['max_new_tokens'][row['task']]}})
                if output['status'] != 'ok':
                    raise RuntimeError('operational failure: ' + str(output.get('error')))
        except (Exception, KeyboardInterrupt) as error:
            fatal = type(error).__name__ + ': ' + str(error)
        finally:
            try:
                state['memory'] = adapter.close()
            except Exception as error:
                state['memory'] = {'reason': type(error).__name__ + ': ' + str(error)}
    state.update(status='incomplete' if fatal else 'complete', finished_at=datetime.now(timezone.utc).isoformat(),
                 error=fatal, completed_requests=len(outputs), unrequested_case_ids=[r['id'] for r in rows[len(outputs):]])
    write_json(out / 'run.json', state)
    publish(benchmark, rows, outputs, out, state)
    return state


def read_jsonl(path, strict):
    # No crash-tail truncation. Invalid lines are errors, including blank lines.
    return [strict(line) for line in Path(path).read_text(encoding='utf-8').splitlines()]


def replay(benchmark, runs, scope, out, split='all'):
    rows = benchmark.select(scope)
    expected = {r['id'] for r in rows}
    seen, outputs, states = set(), [], []
    for folder in runs:
        folder = Path(folder).resolve()
        state = read_json(folder / 'run.json')
        if state['purpose'] == 'synthetic_smoke':
            raise ValueError('smoke runs are not baseline records')
        if states and state['identity'] != states[0]['identity']:
            raise ValueError('model/config/prompt/benchmark differs across runs')
        builder = PromptBuilder(benchmark)
        if state['identity'] != fingerprint(benchmark, state['config'], builder):
            raise ValueError('replay benchmark/prompt/config identity mismatch')
        planned = state['planned_case_ids']
        if len(planned) != len(set(planned)) or seen.intersection(planned):
            raise ValueError('duplicate/overlapping planned case IDs')
        if set(planned) != {r['id'] for r in benchmark.select(state['scope'])}:
            raise ValueError('source run does not match its predeclared scope')
        if states:
            for key in ('model_id', 'local_path', 'quantization', 'weight_dtypes', 'libraries', 'template_settings', 'adapter_files_sha256'):
                if state.get('model', {}).get(key) != states[0].get('model', {}).get(key):
                    raise ValueError('loaded model/environment differs:' + key)
        seen.update(planned)
        records = read_jsonl(folder / 'outputs.jsonl', benchmark.scorer.json_strict)
        ids = [x['case_id'] for x in records]
        if len(ids) != len(set(ids)) or ids != planned[:len(ids)]:
            raise ValueError('source outputs are duplicate/unplanned/out of order')
        if state['status'] == 'complete' and (len(ids) != len(planned) or any(x['status'] != 'ok' for x in records)):
            raise ValueError('complete source run has missing/failed requests')
        requests = read_jsonl(folder / 'requests.jsonl', benchmark.scorer.json_strict)
        if [x['case_id'] for x in requests] != ids:
            raise ValueError('request/output IDs differ')
        for request, output in zip(requests, records):
            row = benchmark.by_id[request['case_id']]
            if request['messages'] != builder.build({key: row[key] for key in ('id', 'task', 'input')}):
                raise ValueError('saved messages differ from locked prompt')
            if request['rendered_prompt'] != output.get('rendered_prompt'):
                raise ValueError('saved rendered prompt differs from adapter record')
        predictions = read_jsonl(folder / 'predictions.jsonl', benchmark.scorer.json_strict)
        if predictions != [{'id': x['case_id'], 'raw_output': x['raw_output']} for x in records if x.get('raw_output') is not None]:
            raise ValueError('predictions differ from saved raw outputs')
        outputs.extend(records)
        states.append(state)
    if not states or seen != expected:
        raise ValueError('planned run union must exactly match requested scope')
    selected = benchmark.select(scope, split)
    ids = {r['id'] for r in selected}
    outputs = [x for x in outputs if x['case_id'] in ids]
    out = Path(out).resolve()
    if out.is_relative_to(benchmark.root):
        raise ValueError('cannot write into frozen release')
    out.mkdir(parents=True, exist_ok=False)
    replay_time = datetime.now(timezone.utc).isoformat()
    state = {**states[0], 'run_id': out.name, 'scope': scope, 'split': split,
             'created_at': replay_time, 'finished_at': replay_time,
             'completed_requests': len(outputs),
             'unrequested_case_ids': [row['id'] for row in selected if row['id'] not in {x['case_id'] for x in outputs}],
             'status': 'complete' if all(s['status'] == 'complete' for s in states) else 'incomplete',
             'planned_case_ids': [r['id'] for r in selected], 'replay': True,
            'source_runs': [{'path': str(Path(path).resolve()), 'run_id': s['run_id'],
                              'model': s.get('model'), 'memory': s.get('memory'), 'warmup': s.get('warmup'),
                              'status': s['status']} for path, s in zip(runs, states)]}
    write_json(out / 'run.json', state)
    # Performance remains copied from original requests, never replaced with replay timing.
    from .reporting import jsonl
    jsonl(out / 'outputs.jsonl', outputs)
    publish(benchmark, selected, outputs, out, state)
    return state
