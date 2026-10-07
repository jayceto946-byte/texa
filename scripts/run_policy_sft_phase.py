#!/usr/bin/env python3
"""Parent monitor preserves RSS/time/exit status even after a Metal abort."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/validation/policy-sft-v0-20261007'
PYTHON='/Users/jichengqian/.lmstudio/extensions/backends/vendor/_amphibian/app-mlx-generate-mac14-arm64@34/bin/python'
phase=sys.argv[1]
assert phase in ('smoke','train')
path=OUT/(phase+'-process-monitor.json')
assert not path.exists(), 'phase may only run once, no automatic retry'
env={**os.environ,'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false'}
started=time.time()
with (OUT/(phase+'-console.log')).open('x') as log:
    process=subprocess.Popen([PYTHON,str(ROOT/'scripts/policy_sft_v0.py'),phase],cwd=ROOT,env=env,
                            stdout=log,stderr=subprocess.STDOUT)
    state={'phase':phase,'pid':process.pid,'started_at':started,'status':'running',
           'sampling_interval_seconds':.25,'rss_peak_bytes':0,'samples':0}
    last_write=0
    while process.poll() is None:
        try:
            value=int(subprocess.check_output(['ps','-o','rss=','-p',str(process.pid)],text=True,
                       stderr=subprocess.DEVNULL).strip())*1024
            state['rss_peak_bytes']=max(state['rss_peak_bytes'],value)
            state['last_rss_bytes']=value;state['samples']+=1
        except (ValueError,subprocess.CalledProcessError):pass
        if time.time()-last_write>=1:
            path.write_text(json.dumps(state,indent=2)+'\n');last_write=time.time()
        time.sleep(.25)
    state.update(status='complete' if process.returncode==0 else 'failed',exit_code=process.returncode,
                 elapsed_seconds=time.time()-started,ended_at=time.time())
    path.write_text(json.dumps(state,indent=2)+'\n')
    if process.returncode!=0:
        result=OUT/('memory-smoke.json' if phase=='smoke' else 'formal-state.json')
        if result.exists():
            data=json.loads(result.read_text())
            data.update(status='failed',process_exit_code=process.returncode,
                        process_monitor=state,no_retry=True)
            if 'error' not in data:data['error']='child process aborted; see console log; MLX peak unavailable after hard abort'
            result.write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(state,indent=2),flush=True)
sys.exit(0 if process.returncode==0 else 1)
