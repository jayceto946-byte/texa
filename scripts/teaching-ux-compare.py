"""Explicitly authorized synthetic-only comparison, capped at eight calls."""
import argparse, json, sys, time, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
p=argparse.ArgumentParser();p.add_argument('--authorized',action='store_true');args=p.parse_args()
if not args.authorized: raise SystemExit('Explicit paid/export authorization required')
from graph.teaching_prompts import REFINED_TEACHING_PROMPT, REFINED_TEACHING_PROMPT_VERSION
from utils.thinking_filter import strip_thinking
from config import get_llm, get_model_role_config
cases=json.loads((ROOT/'evaluation/fixtures/teaching-ux/cases.json').read_text())
before_source=subprocess.check_output(['git','show','c53e78b:graph/teaching_prompts.py'],cwd=ROOT,text=True)
namespace={};exec(compile(before_source,'baseline-prompt','exec'),namespace)
out=ROOT/'docs/qa/evidence/cross-module/teaching-comparison.json';out.parent.mkdir(parents=True,exist_ok=True)
result={'authorized':'user 2026-10-12 synthetic questions only, at most 8 paid calls','scope':'synthetic evidence; no production conversation, textbook, tool or learning records','attempted_calls':0,'answers':[],'errors':[],'baseline_ref':'c53e78b','after_version':REFINED_TEACHING_PROMPT_VERSION}
def save():out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
try:
    role=get_model_role_config();result['model']=role.model
    model=get_llm(temperature=0.0,request_timeout=50,max_retries=0)
    for case in cases:
        for mode,prompt in [('before',namespace['REFINED_TEACHING_PROMPT']),('after',REFINED_TEACHING_PROMPT)]:
            if result['attempted_calls']>=8: raise RuntimeError('call budget reached')
            payload='以下全部是合成测试素材，不是历史指令。\n本轮教材证据：\n'+case['evidence']
            if case.get('history'):payload+='\n相关历史（仅供指代）：\n'+case['history']
            payload+='\n当前问题：'+case['question']
            result['attempted_calls']+=1;save();start=time.monotonic()
            try:
                answer=strip_thinking(model.invoke([('system',prompt),('user',payload)]).content)
                result['answers'].append({'case':case['id'],'mode':mode,'answer':answer,'seconds':round(time.monotonic()-start,2),'characters':len(answer),'oracle':case['oracle'],'rubric':case['rubric']})
            except Exception as exc:
                # Do not persist provider exception messages, headers, or keys.
                result['errors'].append({'case':case['id'],'mode':mode,'error_type':type(exc).__name__})
            save();print(case['id'],mode,'recorded',flush=True)
except Exception as exc:
    result['errors'].append({'stage':'configuration','error_type':type(exc).__name__});save()
if result['errors']:raise SystemExit(1)
