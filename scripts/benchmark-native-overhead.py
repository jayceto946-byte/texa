"""Local paired microbenchmark; never interpret as remote model latency gain."""
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.agent_runtime.contracts import RunCommand
from backend.tools import math_tools as math
from backend.tools.registry import ToolContext


def measure(function, count=100, rounds=7):
    samples = []
    for _ in range(rounds):
        at = time.perf_counter()
        for _ in range(count):
            function()
        samples.append((time.perf_counter()-at)*1000/count)
    return {'median_ms_per_operation': statistics.median(samples), 'rounds_ms': samples, 'iterations_per_round': count}


def main():
    with tempfile.TemporaryDirectory(prefix='texa-perf-') as root:
        store = RuntimeStore(Path(root)/'runtime.db')
        run = store.create(RunCommand('req', 'req', 'task', 'session', 'turn', '计算积分', 'owner'))['run']['id']
        # Same real SQL task with public message payload, not a mocked storage call.
        store.save_native_messages(run, 'owner', [{'type':'ai', 'data':{'content': '公开教材上下文。'*2000}}])
        snapshot = measure(lambda: store.snapshot(run))
        fence = measure(lambda: store.assert_run_active(run, 'owner'))
        args = {'operation': 'calculate', 'expression': 'pi*(2/5)*(2/sqrt(5))'}
        serializer = math._serialized_result
        def old_serializer(value, **kwargs):
            # Before: calculate simplifies, serializer simplifies again.
            return serializer(value, simplified=False)
        math._serialized_result = old_serializer
        before = measure(lambda: math._symbolic_math(ToolContext(), args), count=20)
        math._serialized_result = serializer
        after = measure(lambda: math._symbolic_math(ToolContext(), args), count=20)
    result = {'measurement': 'offline paired microbenchmark; no provider requests; not end-to-end speedup',
              'snapshot_before':snapshot, 'fence_after':fence,
              'calculate_before':before, 'calculate_after':after,
              'limits':'snapshot fixture contains ~32KB public content; math timing excludes worker spawn and validation'}
    out = Path('docs/qa/evidence/agent-loop-performance/local-overhead.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
