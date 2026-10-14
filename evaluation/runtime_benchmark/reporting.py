"""Official output stays unmodified; all V0.1 aggregations are separate."""
from collections import Counter
from .diagnostics import PARSER_VERSION, diagnose, summarize, performance
from .scoring import write_json
import json


def jsonl(path, records):
    with open(path, 'w', encoding='utf-8') as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')
            handle.flush()


def publish(benchmark, rows, outputs, out, run):
    predictions = [{'id': item['case_id'], 'raw_output': item['raw_output']}
                   for item in outputs if item.get('raw_output') is not None]
    official = benchmark.score(rows, predictions)
    jsonl(out / 'predictions.jsonl', predictions)
    write_json(out / 'official-report.json', official)
    write_json(out / 'official-scope.json', {'scope': run['scope'], 'N': len(rows),
                                           'missing_predictions': len(rows) - len(predictions)})
    by_id = {item['case_id']: item for item in outputs}
    results = {item['id']: item for item in official['results']}
    details = [diagnose(row, by_id.get(row['id'], {}).get('raw_output'), results[row['id']], benchmark.scorer)
               for row in rows]
    screening = {}
    for tier in ('primary_semantic', 'secondary_semantic', 'semantic_all'):
        selected = [row for row in rows if
                    (tier == 'semantic_all' and benchmark.scope_by_id[row['id']]['tier'] != 'deterministic_control')
                    or benchmark.scope_by_id[row['id']]['tier'] == tier]
        if not selected:
            continue
        summary = summarize(selected, details, official)
        summary['by_task'] = {task: summarize([r for r in selected if r['task'] == task], details, official)
                              for task in sorted({r['task'] for r in selected})}
        summary['task_macro_strict'] = sum(x['official_strict_accuracy'] for x in summary['by_task'].values()) / len(summary['by_task'])
        summary['by_split'] = {split: summarize([r for r in selected if r['split'] == split], details, official)
                               for split in ('train', 'dev', 'test', 'hidden_test')}
        screening[tier] = summary
    primary = screening.get('primary_semantic')
    qualified = run.get('purpose') == 'foundation_screening' and run['status'] == 'complete'
    if not primary or not qualified or primary['U'] / primary['N'] >= .2:
        judgment = 'insufficient_evidence'
    elif primary['official_strict_accuracy'] >= .8 and primary['task_macro_strict'] >= .8:
        judgment = 'promising_for_task_specific_training'
    else:
        judgment = 'weak_on_measured_boundaries'
    diagnostics = {'parser_version': PARSER_VERSION, 'human_adjudicated': False, 'semantic_test_locked': False,
                   'screening': screening, 'taxonomy': dict(Counter(tag for d in details for tag in d['tags'])),
                   'performance': performance(outputs), 'cases': details,
                   'training_value': {'judgment': judgment, 'basis': 'primary strict/task macro, U and official critical counts; exploratory 80% reference',
                                      'primary_evidence': {key: primary[key] for key in ('N', 'S', 'F', 'T', 'U', 'official_strict_accuracy', 'recoverable_semantic_accuracy', 'task_macro_strict', 'critical_count')} if primary else None,
                                      'limitations': 'Author-frozen synthetic closed profiles; no primary textbook tool or historical-reference coverage; no training/production permission.'}}
    write_json(out / 'diagnostics.json', diagnostics)
    failures = []
    for row, detail in zip(rows, details):
        output = by_id.get(row['id'], {})
        # S1 matches are successes. Operational errors stay visible even if raw matched.
        if detail['bucket'] == 'S' and output.get('status') == 'ok':
            continue
        failures.append({'case_id': row['id'], 'input': row['input'], 'gold': row['gold'],
                         'raw_output': output.get('raw_output'), 'official': results[row['id']],
                         **detail, 'task': row['task'], 'tier': benchmark.scope_by_id[row['id']]['tier'],
                         'scope_reason': benchmark.scope_by_id[row['id']]['reason'],
                         'split': row['split'], 'family': row['family'], 'pair_id': row['pair_id'],
                         'group': row['split_group'], 'operational_status': output.get('status', 'not_requested'),
                         'case_tags': row.get('tags', []),
                         'operational_error': output.get('error'),
                         'run_id': output.get('source_run_id', run['run_id']), 'run_path': str(out)})
    jsonl(out / 'failures.jsonl', failures)
    lines = ['# Runtime Benchmark V0.1', '',
             f"Purpose: {run['purpose']}; status: {run['status']}; scope: {run['scope']}; planned N={len(rows)}.",
             f"Untouched: {run.get('untouched')}; tuned_on_v0: {run.get('config', {}).get('tuned_on_v0')}; author-frozen gold, human_adjudicated=false, semantic_test_locked=false.",
             'This is internal foundation screening, not held-out accuracy or production acceptance.', '']
    def line(label, value):
        def percentage(key):
            rate = value[key]
            return f'{rate:.1%}' if rate is not None else '—'
        lines.append(f"| {label} | {value['S']}/{value['N']} | {percentage('official_strict_accuracy')} | {percentage('official_exact_accuracy')} | {percentage('recoverable_semantic_accuracy')} | {value['F']} | {value['T']} | {value['U']} | {value['format_failures']} / {value['schema_failures']} | {value['critical_count']} |")
    for tier, summary in screening.items():
        lines += ['| Set / task | S / N | Strict | Exact | Recoverable | F | T | U | Format / schema | Critical |',
                  '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
        for task, value in summary['by_task'].items():
            line(tier + ' / ' + task, value)
        line(tier, summary)
        for split, value in summary['by_split'].items():
            line(tier + ' / ' + split, value)
        lines += ['', f"{tier} task macro strict: {summary['task_macro_strict']:.1%}; severity: {summary['severity']}", '']
    lines += ['', 'S/F/T/U are mutually exclusive; U is unresolved, not proven semantic error. S1 may be successful.',
              '', 'Official severity/taxonomy: ' + json.dumps(diagnostics['taxonomy'], ensure_ascii=False),
              '', 'Performance (warmup excluded; request includes prefill):',
              '```json', json.dumps(diagnostics['performance'], ensure_ascii=False, indent=2), '```',
              'Load / peak memory / device: see run.json; RSS and MLX peaks include warmup and must not be added.',
              'Offline single-model measurement does not establish Electron/Chroma/embedding concurrent feasibility.',
              '', 'Training value: ' + judgment + '.', diagnostics['training_value']['limitations'],
              'Failures remain analysis-only; no training pairs or automatic training are produced.']
    measurements = run.get('source_runs') or [run]
    lines += ['', 'Original run load, device and memory measurements:', '```json',
              json.dumps([{'run_id': source['run_id'], 'model_load_ms': source.get('model', {}).get('load_ms'),
                           'device': source.get('model', {}).get('device'), 'memory': source.get('memory')}
                          for source in measurements], ensure_ascii=False, indent=2), '```']
    (out / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return diagnostics
