#!/usr/bin/env python3
"""Layered offline QA; disposable roots, no .env credentials or production data.
Usage: venv310/bin/python scripts/qa-check.py smoke|backend|frontend|desktop|build|all
Browser evidence: scripts/qa-pages.mjs (loopback socket permission needed).
"""
from pathlib import Path
import os, shutil, subprocess, sys, tempfile
ROOT = Path(__file__).resolve().parents[1]
if sys.version_info[:2] != (3, 10):
    raise SystemExit('Use venv310 Python 3.10')
layer = sys.argv[1] if len(sys.argv) > 1 else 'smoke'
node = os.environ.get('TEXA_QA_NODE') or shutil.which('node')
if not node:
    bundled = Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
    if bundled.exists(): node = str(bundled)
if layer not in {'smoke','backend','frontend','desktop','build','all'}:
    raise SystemExit('Unknown layer')
logs = ROOT/'docs/qa/evidence/latest'/layer
logs.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(prefix='texa-qa-') as temp:
    env = dict(os.environ)
    for key in list(env):
        if any(part in key.upper() for part in ('API_KEY','API_SECRET','CREDENTIAL','ACCESS_TOKEN')):
            env[key]=''
    empty = Path(temp)/'empty.env';empty.touch()
    env.update(ENV_PATH=str(empty),DATA_DIR=f'{temp}/data',PROGRESS_PATH=f'{temp}/progress',VECTOR_DB_PATH=f'{temp}/vector',BOOKS_PATH=f'{temp}/books',MINERU_OUTPUT_PATH=f'{temp}/mineru',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    if node: env['PATH']=str(Path(node).parent)+os.pathsep+env.get('PATH','')
    selected = ['backend','frontend','desktop','build'] if layer=='all' else [layer]
    commands=[]
    if 'smoke' in selected or 'backend' in selected:
        tests = ['tests/test_runtime_stream_cleanup_errors.py','tests/test_weekly_report_regressions.py','tests/test_legacy_practice_partial_result.py','tests/test_conversation_management.py','tests/test_session_notes.py','tests/test_mistake_lifecycle.py','tests/test_exercise_bank.py','tests/test_mobile_remote_s0.py'] if layer=='smoke' else []
        commands.append(('backend',[sys.executable,'-m','pytest','-q',f'--basetemp={temp}/pytest',*tests],ROOT))
    if 'frontend' in selected:
        commands.append(('frontend',[node or 'node','node_modules/vitest/vitest.mjs','run'],ROOT/'frontend'))
    if 'desktop' in selected:
        commands.append(('desktop',[node or 'node','--test',*[p.name for p in sorted((ROOT/'desktop').glob('*.test.cjs'))]],ROOT/'desktop'))
    if 'build' in selected:
        commands += [('types',[node or 'node','node_modules/typescript/bin/tsc','-b'],ROOT/'frontend'),('lint',[node or 'node','node_modules/eslint/bin/eslint.js','.'],ROOT/'frontend'),('build',[node or 'node','node_modules/vite/bin/vite.js','build','--outDir',f'{temp}/dist'],ROOT/'frontend')]
    failures=[]
    for label,cmd,cwd in commands:
        with (logs/f'{label}.log').open('w') as stream:
            run=subprocess.run(cmd,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT)
        print(f'{label}: {"PASS" if run.returncode==0 else "FAIL"} — {logs/label}.log',flush=True)
        if run.returncode:failures.append(label)
    raise SystemExit(bool(failures))
