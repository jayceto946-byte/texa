"""Read-only audit of the single authorized S1; never calls a model."""
import hashlib,json,re,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/qa/evidence/deepseek-remediation/paid'
receipts=json.loads((OUT/'REQUEST-RECEIPTS.json').read_text());assert len(receipts)==1
receipt=receipts[0];assert receipt['case']=='S1' and receipt['status']=='returned'
ui=json.loads((OUT/'electron/results.json').read_text())
stream=next(x['text'] for x in ui['sse'] if 'text' in x)
sse=[json.loads(line[6:]) for line in stream.splitlines() if line.startswith('data: ')]
run_id=next(x['execution_event']['run_id'] for x in sse if x.get('execution_event',{}).get('run_id'))
conn=sqlite3.connect('file:/private/tmp/texa-deepseek-production-paid/progress/agent_runtime.db?mode=ro',uri=True);conn.row_factory=sqlite3.Row
run=dict(conn.execute('SELECT * FROM agent_runs WHERE id=?',(run_id,)).fetchone())
task=json.loads(conn.execute('SELECT snapshot_json FROM runtime_tasks WHERE id=?',(run['task_id'],)).fetchone()[0])
checkpoint=json.loads(run['checkpoint_json']);outcome=json.loads(run['output_json']);answer=outcome['answer']
events=[json.loads(x[0]) for x in conn.execute('SELECT event_json FROM execution_events WHERE run_id=? ORDER BY seq',(run_id,))]
outbox=json.loads(conn.execute("SELECT payload_json FROM runtime_outbox WHERE run_id=? AND kind='assistant_message'",(run_id,)).fetchone()[0])
sse_replace=next(e['execution_event']['payload']['text'] for e in reversed(sse) if e.get('execution_event',{}).get('payload',{}).get('replace'))
final_sse=next(e for e in reversed(sse) if e.get('execution_event',{}).get('type')=='final')
raw=checkpoint['native_messages'][-1]['data']['content']
checks={'raw_equals_sql':raw==answer,'task_equals_sql':task['artifacts']['final_answer']==answer,'outbox_equals_sql':outbox['answer']==answer,'sse_equals_sql':sse_replace==answer,'sse_task_equals_sql':final_sse['learning_task']['artifacts']['final_answer']==answer,'verification_sidecar_equal':final_sse['learning_task']['verification']==task['verification'],'ui_discloses_unverified':'部分内容尚未验证，需要核对' in ui['cases'][0]['ui_text'][0],'no_disclosure_in_body':'部分内容尚未验证，需要核对' not in answer,'ui_meaningful_final_answer':'不矛盾' in ui['cases'][0]['answers'][0][0] and '金属加工切削力测量' in ui['cases'][0]['answers'][0][0]}
assert all(checks.values()),checks
public='';first_meaningful=None
for frame in sse:
 e=frame.get('execution_event',{})
 if e.get('type')!='output_delta' or e.get('payload',{}).get('replace'):continue
 public+=e.get('payload',{}).get('text','')
 if len(public.strip())>=6 and re.search('[。！？；\n]',public):first_meaningful=e['elapsed_ms'];break
human=next(m['data']['content'] for m in checkpoint['native_messages'] if m['type']=='human')
visible=human.split('## 教材证据\n',1)[1].split('\n## ',1)[0]
(OUT/'FINAL-VISIBLE-EVIDENCE.md').write_text(visible+'\n')
(OUT/'S1-FINAL-ANSWER.md').write_text(answer+'\n')
(OUT/'VERIFICATION.json').write_text(json.dumps(task['verification'],ensure_ascii=False,indent=2)+'\n')
source_manifest=json.loads((OUT.parent/'SOURCE-MANIFEST.json').read_text())
unchanged=all(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in source_manifest['files'].items())
assert unchanged
summary={'case':'S1','acceptance':'LIVE-VERIFIED','run_id':run_id,'conversation_id':run['conversation_id'],'run_status':run['status'],'task_status':task['status'],'verification_status':task['verification']['status'],'verification_failures':task['verification']['failures'],'requests':{'deepseek':1,'qwen':0,'retries':0},'metrics':{'input_tokens':receipt['usage']['input_tokens'],'reasoning_tokens':receipt['usage']['reasoning_tokens'],'final_content_tokens':receipt['usage']['final_content_tokens'],'total_output_tokens':receipt['usage']['output_tokens'],'all_tokens':receipt['usage']['total_tokens'],'finish_reason':receipt['finish_reason'],'wire_output_limit':receipt['output_cap'],'first_meaningful_output_ms_from_sql_run':first_meaningful,'first_public_ms_from_provider':receipt['first_public_ms'],'provider_elapsed_ms':receipt['elapsed_ms'],'total_run_time_ms':events[-1]['elapsed_ms']},'cost':{'tariff_band':receipt['tariff_band'],'estimated_usd':receipt['estimated_cost'],'hard_cap_usd':.03,'reserved_usd':receipt['reserved_cost'],'supplier_invoice':False},'consistency':checks,'effective_source_unchanged':unchanged,'ui_diagnostics':{'page_or_network_errors':[x for x in ui['errors'] if not isinstance(x,dict) or 'abort_stack' not in x],'cleanup_abort_callsite_count':sum(isinstance(x,dict) and 'abort_stack' in x for x in ui['errors']),'explanation':'Harness records every AbortController cleanup call during profile/scope/navigation. No requestfailed/pageerror, stream completed, SQL terminal completed.'},'limitations':['One frozen sample does not establish statistical output budget stability.','488 final_content_tokens is completion minus reasoning, possible protocol overhead included.','Runtime semantic obligations remain unverified; independent release evidence review does not upgrade task verification.','UI raw bytes asserted at SSE boundary; desktop renders Markdown, LaTeX and citation markers.']}
(OUT/'FINAL-ACCEPTANCE.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
