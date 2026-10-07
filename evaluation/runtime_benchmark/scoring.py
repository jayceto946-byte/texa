"""Read-only frozen scorer integration. Model libraries are deliberately absent."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / 'docs/runtime-benchmark-v0.1/case-scope-manifest.json'
DEFAULT_BENCHMARK = Path(__file__).resolve().parents[1] / 'frozen/runtime-benchmark-v0'
SCOPES = ('primary_semantic', 'secondary_semantic', 'semantic_all', 'all')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


class Benchmark:
    def __init__(self, benchmark=None, manifest=DEFAULT_MANIFEST):
        self.manifest = read_json(manifest)
        # Keep frozen manifest bytes (and historical replay identity) unchanged.
        # The shipped default resolves locally; custom manifests remain configurable.
        source = DEFAULT_BENCHMARK if Path(manifest).resolve() == DEFAULT_MANIFEST.resolve() else self.manifest['source_release']
        self.root = Path(benchmark or source).resolve()
        self.freeze_hash = hashlib.sha256((self.root / 'FREEZE.json').read_bytes()).hexdigest()
        if self.freeze_hash != self.manifest['freeze_sha256']:
            raise ValueError('FREEZE identity mismatch')
        # Verify every pinned file BEFORE importing executable frozen code.
        freeze = read_json(self.root / 'FREEZE.json')
        for relative, expected in freeze['sha256'].items():
            path = (self.root / relative).resolve()
            if not path.is_relative_to(self.root):
                raise ValueError('invalid frozen path')
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError('freeze_mismatch:' + relative)
        spec = importlib.util.spec_from_file_location('texa_frozen_score', self.root / 'tools/score.py')
        self.scorer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.scorer)
        self.rows = self.scorer.verify_freeze()
        self.by_id = {row['id']: row for row in self.rows}
        cases = self.manifest['cases']
        self.scope_by_id = {item['id']: item for item in cases}
        if len(self.by_id) != len(self.rows) or len(self.scope_by_id) != len(cases) or set(self.by_id) != set(self.scope_by_id):
            raise ValueError('duplicate or mismatched case IDs')
        for row in self.rows:
            item = self.scope_by_id[row['id']]
            if any(item[key] != row[key] for key in ('task', 'split', 'case_hash')):
                raise ValueError('scope case identity mismatch:' + row['id'])
        if Counter(item['tier'] for item in cases) != {'primary_semantic': 161, 'secondary_semantic': 39, 'deterministic_control': 100}:
            raise ValueError('unexpected V0.1 scope counts')

    def select(self, scope, split='all'):
        if scope not in SCOPES:
            raise ValueError('unknown scope:' + scope)
        if split not in ('all', 'train', 'dev', 'test', 'hidden_test'):
            raise ValueError('unknown split')
        return [row for row in self.rows if
                (scope == 'all' or self.scope_by_id[row['id']]['tier'] == scope or
                 scope == 'semantic_all' and self.scope_by_id[row['id']]['tier'] != 'deterministic_control')
                and (split == 'all' or row['split'] == split)]

    def predictions(self, records, rows):
        ids = {row['id'] for row in rows}
        result = {}
        for item in records:
            if set(item) != {'id', 'raw_output'} or type(item['raw_output']) is not str:
                raise ValueError('predictions require id/raw_output string only')
            if item['id'] not in ids or item['id'] in result:
                raise ValueError('duplicate/unknown/unplanned prediction:' + item['id'])
            result[item['id']] = item['raw_output']
        return result

    def score(self, rows, records):
        return self.scorer.score(rows, self.predictions(records, rows))

    def sanity(self):
        result = subprocess.run([sys.executable, str(self.root / 'tools/check_release.py')],
                                check=True, text=True, capture_output=True)
        report = json.loads(result.stdout)
        # Check wrapper against original CLI on COMPLETE splits, including controls.
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            for split in ('train', 'dev', 'test', 'hidden_test', 'all'):
                rows = self.select('all', split)
                preds = [{'id': r['id'], 'raw_output': self.scorer.canonical(r['gold'])} for r in rows]
                path = Path(folder) / 'predictions.jsonl'
                path.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in preds))
                output = Path(folder) / 'report.json'
                subprocess.run([sys.executable, str(self.root / 'tools/score.py'), str(path), '--split', split,
                                '--output', str(output)], check=True, capture_output=True, text=True)
                cli = read_json(output)
                cli.pop('split'); cli.pop('missing_predictions')
                if cli != self.score(rows, preds):
                    raise ValueError('frozen CLI/API mismatch:' + split)
        return {**report, 'purpose': 'self-test, not model accuracy', 'freeze_sha256': self.freeze_hash,
                'scope_counts': dict(Counter(x['tier'] for x in self.scope_by_id.values())),
                'cli_api_consistency': 'all four complete splits and all'}
