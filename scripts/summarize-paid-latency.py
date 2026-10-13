"""Read-only paired evidence summary; no model grading or provider connections."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'docs/qa/evidence/agent-loop-performance/paired-2026-10-13'

def main():
    manifest=json.loads((ROOT/'manifest.json').read_text())
    ledger=json.loads((ROOT/'provider-receipts.json').read_text())
    reviews=json.loads((ROOT/'independent-review.json').read_text())
    stopped=json.loads((ROOT/'stopped-arms.json').read_text()) if (ROOT/'stopped-arms.json').exists() else {}
    cases=[]
    for spec in manifest['cases']:
        p=ROOT/(spec['id']+'.json')
        if not p.exists():
            cases.append({'id':spec['id'],'status':'skipped_quality' if spec['arm'] in stopped else 'not_run'})
            continue
        r=json.loads(p.read_text());calls=[c for c in ledger['requests'] if c['case']==spec['id']]
        usage_complete=bool(calls) and all('usage' in c and c['usage'].get('total_tokens') is not None for c in calls)
        usage={k:sum(c['usage'].get(k,0) for c in calls) for k in ('input_tokens','output_tokens','total_tokens')} if usage_complete else None
        reasoning=sum(c['usage'].get('output_token_details',{}).get('reasoning',0) for c in calls) if usage_complete else None
        step_final=[m for m in (r['native_messages'] or []) if m['type']=='ai' and not m['data'].get('tool_calls')]
        # First visible interim differs from first final answer.
        final_start=next((e['elapsed_ms'] for e in r['events'] if e['payload'].get('lifecycle')=='model.started' and e['payload'].get('model_call_id','').endswith(':'+str(r['model_calls']))),None)
        deltas=[(e,t) for e,t in zip(r['events'],r['received']) if e['type']=='output_delta' and not e['payload'].get('replace') and e['payload'].get('text','').strip()]
        final_deltas=[t['received_ms'] for e,t in deltas if final_start is not None and e['elapsed_ms']>=final_start]
        if not r.get('output') or not step_final:
            final_deltas=[]
        starts={e['operation_id']:e['elapsed_ms'] for e in r['events'] if e['status']=='started'}
        model_ms=sum(e['elapsed_ms']-starts[e['operation_id']] for e in r['events'] if e['payload'].get('lifecycle')=='model.completed')
        tool_ms=sum(e['elapsed_ms']-starts[e['operation_id']] for e in r['events'] if e['payload'].get('lifecycle') in {'tool.completed','tool.failed'})
        public_interim=sum(1 for m in (r['native_messages'] or []) if m['type']=='ai' and m['data'].get('tool_calls') and str(m['data'].get('content','')).strip())
        cases.append({'id':spec['id'],'status':r['task_status'],'error':r['error_code'],
            'model_envelope_seconds':model_ms/1000,'tool_seconds':tool_ms/1000,
            'runtime_profile':[e['payload']['performance'] for e in r['events'] if e['payload'].get('lifecycle')=='runtime.profile'],
            'prompt_hash':r['prompt_hash'],'total_seconds':r['total_ms']/1000,
            'first_public_seconds':min((t['received_ms'] for e,t in deltas),default=None)/1000 if deltas else None,
            'first_final_seconds':min(final_deltas)/1000 if final_deltas else None,
            'model_calls':r['model_calls'],'tool_calls':len(r['tool_calls']),
            'failed_tools':sum(c['status']!='succeeded' for c in r['tool_calls']),
            'usage':usage,'reasoning_tokens':reasoning,'public_tool_preambles':public_interim,
            'review':reviews.get(spec['id']),
            'max_receive_gap_seconds':max((b['received_ms']-a['received_ms'] for a,b in zip(r['received'],r['received'][1:])),default=0)/1000,
            'tools':[{'tool':c['tool_id'],'args':c['args'],'status':c['status']} for c in r['tool_calls']]})
    for q in {'concept','integral','stokes','proof'}:
        hashes={c['prompt_hash'] for c in cases if c['id'].startswith(q+'-') and 'prompt_hash' in c}
        if len(hashes)>1:raise RuntimeError('paired prompt mismatch '+q)
    result={'cases':cases,'requests':len(ledger['requests']),'attempted_runs':len(ledger['runs_started']),
        'actual_receipt_cost_cny':sum(c.get('estimated_cost_cny',0) for c in ledger['requests']),
        'unknown_usage_reserved_cny':sum(c['reserved_cny'] for c in ledger['requests'] if 'estimated_cost_cny' not in c),
        'reserved_or_used_cny':ledger['reserved_or_used_cny'],'input_bytes':ledger['input_bytes'],
        'actual_tokens_returned':sum(c.get('usage',{}).get('total_tokens',0) for c in ledger['requests']),
        'limitations':['one sample per question/condition; missing network cases and safety-stopped arms retained',
            'stream_run consumer timing, not browser rendering; no API routing/retrieval experiment',
            'review is independent offline mathematics, not another model call or Runtime verified flag']}
    (ROOT/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='cases'},ensure_ascii=False))
    for c in cases:
        print({k:c[k] for k in ['id','status','total_seconds','first_public_seconds','first_final_seconds','model_calls','tool_calls','usage'] if k in c})

if __name__=='__main__':main()
