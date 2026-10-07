"""venv310/bin/python -m evaluation.runtime_benchmark sanity|run|replay"""
import argparse
import json
from pathlib import Path
from .runner import run, replay
from .scoring import Benchmark, DEFAULT_MANIFEST, read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('sanity', 'run', 'replay'):
        command = commands.add_parser(name)
        command.add_argument('--benchmark', type=Path)
        command.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
        if name == 'sanity':
            command.add_argument('--out', type=Path)
        else:
            command.add_argument('--out', type=Path, required=True)
            command.add_argument('--scope', choices=('primary_semantic', 'secondary_semantic', 'semantic_all'), required=True)
        if name == 'run':
            command.add_argument('--config', type=Path, required=True)
            command.add_argument('--smoke', action='store_true', help='independent synthetic P1 only, no benchmark cases')
        if name == 'replay':
            command.add_argument('--runs', type=Path, nargs='+', required=True)
            command.add_argument('--split', choices=('all', 'train', 'dev', 'test', 'hidden_test'), default='all')
    args = parser.parse_args()
    benchmark = Benchmark(args.benchmark, args.manifest)
    if args.command == 'sanity':
        report = benchmark.sanity()
        if args.out:
            if args.out.exists() or args.out.resolve().is_relative_to(benchmark.root):
                raise ValueError('sanity output must be new and outside frozen release')
            write_json(args.out, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        state = run(benchmark, args.scope, read_json(args.config), args.out, smoke=args.smoke) if args.command == 'run' else replay(benchmark, args.runs, args.scope, args.out, args.split)
        print(json.dumps({key: state.get(key) for key in ('run_id', 'purpose', 'status', 'error', 'completed_requests')}, ensure_ascii=False))
        return 0 if state['status'] == 'complete' else 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
