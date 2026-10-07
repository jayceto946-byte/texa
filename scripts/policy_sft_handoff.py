#!/usr/bin/env python3
"""Offline, stdlib-only migration check. Never loads a model or scores Hidden."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / 'docs/validation/policy-sft-v0-20261007'
MANIFEST = EXP / 'HANDOFF-MANIFEST.json'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify():
    inventory = read(MANIFEST)
    tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0'))
    paths = inventory['sha256']
    for relative, expected in paths.items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT) or relative not in tracked:
            raise ValueError('untracked/outside repo: ' + relative)
        if digest(path) != expected:
            raise ValueError('handoff hash mismatch: ' + relative)
    for name in ('FREEZE.json', 'TRAIN-FREEZE.json', 'ACQUISITION-FREEZE.json'):
        base = ROOT if name == 'ACQUISITION-FREEZE.json' else EXP
        for relative, expected in read(EXP / name)['sha256'].items():
            path = (base / relative).resolve()
            assert path.is_relative_to(ROOT), relative
            assert digest(path) == expected, (name, relative)
            assert path.relative_to(ROOT).as_posix() in paths, relative
    bench = ROOT / 'evaluation/frozen/runtime-benchmark-v0'
    scope = read(ROOT / 'docs/runtime-benchmark-v0.1/case-scope-manifest.json')
    assert digest(bench / 'FREEZE.json') == scope['freeze_sha256']
    frozen = read(bench / 'FREEZE.json')['sha256']
    for relative, expected in frozen.items():
        path = (bench / relative).resolve()
        assert path.is_relative_to(bench), relative
        assert digest(path) == expected, relative
        assert path.relative_to(ROOT).as_posix() in paths, relative
    # Metadata-only accounting: no Hidden inference/scoring, no gold round-trip.
    counts, all_seeds, families = {}, set(), {}
    for split, filename, expected in [('train', 'train', (672, 2688)), ('dev', 'valid', (144, 576)), ('hidden', 'hidden', (144, 576))]:
        meta = [json.loads(x) for x in (EXP / (split+'-metadata.jsonl')).read_text(encoding='utf-8').splitlines()]
        ids = Counter(x['seed_id'] for x in meta)
        assert (len(ids), len(meta)) == expected and set(ids.values()) == {4}
        assert not all_seeds.intersection(ids)
        all_seeds.update(ids)
        for row in meta:
            assert row['split'] == split
            assert families.setdefault(row['family_id'], split) == split
        assert sum(1 for _ in (EXP / (filename+'.jsonl')).open(encoding='utf-8')) == expected[1]
        counts[split] = {'seeds': len(ids), 'instances': len(meta)}
    assert len(all_seeds) == 960
    assert sum(1 for _ in (EXP / 'seeds.jsonl').open(encoding='utf-8')) == 960
    assert len({x['id'] for x in scope['cases']}) == 300
    sizes = [(ROOT/p).stat().st_size for p in paths]
    assert max(sizes) < 50*1024*1024
    return {'status': 'passed', 'files': len(paths), 'total_bytes': sum(sizes), 'largest_file_bytes': max(sizes),
            'frozen_hashes': 'all three SFT freezes and 271 benchmark pins verified', 'splits': counts,
            'seeds': 960, 'instances': 3840, 'benchmark_cases': 300, 'hidden_inference_count': 0}

def materialize(args):
    verify()
    import yaml
    cfg = yaml.safe_load((EXP / 'train-config.yaml').read_text(encoding='utf-8'))
    # Path-only projection. This is NOT a CUDA implementation or translated config.
    cfg.update(model=str(args.model.resolve(strict=True)), data=str(EXP), adapter_path=str(args.adapter_dir.resolve()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as handle:
        yaml.safe_dump(cfg, handle, sort_keys=False, allow_unicode=True)
    print('Path-only config written; frozen MLX semantics retained; do not use as CUDA trainer config.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('verify')
    command = sub.add_parser('materialize-paths')
    command.add_argument('--model', type=Path, required=True)
    command.add_argument('--adapter-dir', type=Path, required=True)
    command.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'verify':
        print(json.dumps(verify(), indent=2))
    else:
        materialize(args)

if __name__ == '__main__':
    main()
