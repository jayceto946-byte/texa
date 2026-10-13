"""Offline timeline from existing SQL milestones, Provider receipts and SSE capture.

Never opens credentials, production databases or a model connection. Missing
wire/chunk/UI timestamps stay null; model envelopes include network and SDK work.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path


def profile(root):
    load = lambda name: json.loads((root / name).read_text())
    calls = load('provider-receipts.json')['calls']
    browser = load('electron-results.json')['cases']
    result = []
    for run in load('runtime-traces.json')['runs']:
        start, end = (datetime.fromisoformat(run[k]) for k in ('created_at', 'updated_at'))
        events = run['events']
        sse = next((c for c in browser if any(x.get('execution_event', {}).get('run_id') == run['run_id'] for x in c.get('events', []))), {})
        stream = [x['execution_event'] for x in sse.get('events', []) if x.get('execution_event', {}).get('run_id') == run['run_id']]
        model = []
        run_model_starts = [e['elapsed_ms'] for e in events if e['payload'].get('lifecycle') == 'model.started']
        for r in calls:
            at = datetime.fromisoformat(r['started_at'])
            if not start <= at <= end:
                continue
            model.append({'request_start_ms': round((at-start).total_seconds()*1000, 2),
                'request_end_ms': round((datetime.fromisoformat(r['ended_at'])-start).total_seconds()*1000, 2) if r.get('ended_at') else None,
                'first_chunk_ms': None, 'first_public_ms': None, 'usage': r.get('usage'),
                'finish_reason': r.get('finish_reason')})
        for index, request in enumerate(model):
            if index >= len(run_model_starts):
                continue
            lo = run_model_starts[index]
            hi = run_model_starts[index+1] if index+1 < len(run_model_starts) else (end-start).total_seconds()*1000
            public = [e['elapsed_ms'] for e in stream if e['type'] == 'output_delta' and not e['payload'].get('replace') and e['payload'].get('text', '').strip() and lo <= e['elapsed_ms'] <= hi]
            request['first_public_server_elapsed_ms'] = min(public) if public else None
        starts = {e['operation_id']: e['elapsed_ms'] for e in events if e['status'] == 'started'}
        model_ms = sum(e['elapsed_ms'] - starts[e['operation_id']] for e in events if e['payload'].get('lifecycle') == 'model.completed')
        completed_models = {e['operation_id'] for e in events if e['payload'].get('lifecycle') == 'model.completed'}
        censored = [e for e in events if e['payload'].get('lifecycle') == 'model.started' and e['operation_id'] not in completed_models]
        model_ms += sum((end-start).total_seconds()*1000 - e['elapsed_ms'] for e in censored)
        tool_ms = sum(e['elapsed_ms'] - starts[e['operation_id']] for e in events if e['payload'].get('lifecycle') in {'tool.completed', 'tool.failed'})
        delta = [e['elapsed_ms'] for e in stream if e['type'] == 'output_delta' and not e['payload'].get('replace') and e['payload'].get('text', '').strip()]
        total = (end-start).total_seconds()*1000
        updates = sorted({0, total, *[e['elapsed_ms'] for e in stream if e['type'] != 'output_delta' or e['payload'].get('text', '').strip()]})
        result.append({'run_id': run['run_id'], 'question': run['question'], 'total_ms': round(total, 2),
            'model_envelope_ms': round(model_ms, 2), 'model_envelope_censored': bool(censored), 'tool_ms': round(tool_ms, 2),
            'other_application_ms': round(total-model_ms-tool_ms, 2),
            'first_public_run_ms': min(delta) if delta else None,
            'first_progress_run_ms': min((e['elapsed_ms'] for e in stream if e['type'] != 'output_delta'), default=None),
            'longest_server_event_gap_ms': round(max((b-a for a,b in zip(updates, updates[1:])), default=0), 2),
            'ui_wall_seconds': sse.get('wall_seconds'), 'model_requests': model,
            'milestones': [{'elapsed_ms': e['elapsed_ms'], 'lifecycle': e['payload'].get('lifecycle'), 'performance': e['payload'].get('performance')} for e in events],
            'limitations': ['server event creation times, not browser receive/paint times',
                'model envelope includes provider wait, network, SDK and callback processing',
                'first chunk and individual network phases absent in historical captures',
                'post-terminal outbox persistence not measured by run total']})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = [item for root in args.evidence for item in profile(root)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    for r in result:
        print({k: v for k,v in r.items() if k not in {'question', 'model_requests', 'milestones', 'limitations'}})


if __name__ == '__main__':
    main()
