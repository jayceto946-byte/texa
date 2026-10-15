"""Offline Phase 1 audit. No credentials, resolved user profile, or API calls."""
import argparse
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--evidence-root', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from llm.configuration import resolve_model_role
from llm.factory import build_chat_model
from langchain_core.messages import AIMessage, HumanMessage

role = resolve_model_role('reasoning', env={})  # explicitly avoids saved secrets/environment
model = build_chat_model(role, 0, max_retries=0, stream_usage=True)
request = model._get_request_payload([HumanMessage(content='offline audit')], max_tokens=4096,
                                     parallel_tool_calls=False)
assert request['max_completion_tokens'] == 4096 and 'max_tokens' not in request
assert request['extra_body']['enable_thinking'] is True and request['stream'] is True
assistant = AIMessage(content='', tool_calls=[{'id': 'audit_call', 'name': 'symbolic_math',
    'args': {'operation': 'calculate', 'expression': '1+1'}}],
    additional_kwargs={'reasoning_content': 'synthetic audit marker'})
serialized = model._get_request_payload([HumanMessage(content='offline audit'), assistant])['messages'][-1]
assert 'reasoning_content' not in serialized
paths = [
    'TEXA-AGENT-LOOP-PERFORMANCE-REPORT.md',
    'docs/qa/REAL-NATIVE-MATH-ACCEPTANCE-2026-10-13.md',
    'docs/qa/evidence/agent-loop-performance/paired-2026-10-13/manifest.json',
    'docs/qa/evidence/agent-loop-performance/paired-2026-10-13/provider-receipts.json',
    'llm/agent_adapter.py', 'backend/services/agent_runtime/native_loop.py', 'backend/tools/math_tools.py',
]
hashes = {p: hashlib.sha256((args.evidence_root / p).read_bytes()).hexdigest() for p in paths}
ledger = json.loads((args.evidence_root / paths[3]).read_text())
requests = ledger['requests']
b_returns = [r for r in requests if r.get('case', '').endswith('-B') and r.get('usage')]
reasoning = [r['usage'].get('output_token_details', {}).get('reasoning') for r in b_returns]
assert all(isinstance(n, int) and n < 4096 for n in reasoning)
print(json.dumps({
    'python': platform.python_version(),
    'packages': {p: version(p) for p in ['langchain', 'langchain-openai', 'langchain-core', 'openai']},
    'network_calls': 0, 'baseline': 'f91633673c40cf9c353e49804e2584b64f3131cc',
    'payload': {k: request[k] for k in ['model', 'temperature', 'stream', 'max_completion_tokens',
                                       'parallel_tool_calls', 'extra_body']},
    'assistant_wire_fields': list(serialized),
    'historical_runs': len(ledger['runs_started']), 'historical_requests': len(requests),
    'B_returned_reasoning_tokens': reasoning,
    'evidence_root': str(args.evidence_root.resolve()), 'source_sha256': hashes,
}, ensure_ascii=False, indent=2))
