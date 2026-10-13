"""Summarize paid acceptance receipts; scores are explicit independent review data."""
import argparse
import json
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    root = args.evidence
    load = lambda name: json.loads((root/name).read_text())
    runs = load('runtime-traces.json')['runs']
    receipts = load('provider-receipts.json')
    browser = {c['id']: c for c in load('electron-results.json')['cases']}
    scores = load('independent-review.json')
    cases = []
    for question, run in zip(load('questions.json'), runs):
        start, end = map(datetime.fromisoformat, [run['created_at'], run['updated_at']])
        calls = [r for r in receipts['calls'] if start <= datetime.fromisoformat(r['started_at']) <= end]
        usages = [r['usage'] for r in calls if r.get('usage')]
        complete_usage = len(usages) == len(calls) and len(calls) > 0
        tokens = {key: sum(u.get(key, 0) for u in usages) for key in ('input_tokens', 'output_tokens', 'total_tokens')} if complete_usage else None
        grade = scores[question['id']]
        answer = (run.get('answer') or {}).get('answer', '')
        (root/(question['id']+'-answer.md')).write_text(answer)
        cases.append({'id': question['id'], 'topic': question['topic'],
            'run_id': run['run_id'], 'runtime_seconds': round((end-start).total_seconds(),3),
            'ui_wall_seconds': browser[question['id']].get('wall_seconds'),
            'model_calls': run['model_calls'], 'remote_attempts': len(calls),
            'tool_calls': len(run['tool_calls']), 'tool_statuses': [c['status'] for c in run['tool_calls']],
            'tokens': tokens, 'token_measurement': 'provider usage including reasoning' if complete_usage else 'missing receipt; unknown',
            'estimated_cost_cny': round(sum(c.get('estimated_cost_cny', c['reserved_cny']) for c in calls),6),
            'runtime_task_status': run['task_status'],
            'runtime_verification': (run.get('answer') or {}).get('verification',{}).get('status'),
            'review_points': grade['points'], 'review_max_points': grade['max_points'],
            'review_percent': 100*grade['points']/grade['max_points'],
            'mathematically_correct_complete': grade['correct_complete'],
            'review_method': 'independent mathematical checks, not Runtime verified flag',
            'screenshots': browser[question['id']]['screenshots']})
    result = {'cases': cases, 'cost_cny_including_first_failed_batch': round(receipts['prior_reserved_or_used_cny']+receipts['reserved_or_used_cny'],6),
        'remote_attempts_including_first_failed_batch': receipts['prior_attempts']+receipts['remote_attempts'],
        'limitations': ['3 tool-enabled items versus 1 different no-tool item; not a paired causal study',
            'first 35-second batch retained separately, individual late usage attribution unavailable',
            'prices omit cache discounts; estimated cost is not an invoice']}
    (root/'metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
