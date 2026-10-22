"""Audit-only collector; copies inputs, calls existing deterministic code, never publishes.

Private text stays under ignored artifacts/. No OCR, model calls or production writes.
Usage: venv310/bin/python .../collect_baseline.py --source DESKTOP_DATA --work artifacts/NEW_DIR
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import zipfile

ROOT = next(p for p in Path(__file__).resolve().parents if (p / 'AGENTS.md').is_file())
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--work', type=Path, required=True)
args = parser.parse_args()
source, work = args.source.resolve(), args.work.resolve()
assert work.is_relative_to(ROOT / 'artifacts') and not work.exists(), 'use a fresh ignored audit directory'
work.mkdir(parents=True)
previous = ROOT / 'artifacts/r1-r2-post-approval/real-copy-verified'
context = json.loads((previous / 'private-context.json').read_text())
book_name = context['book']
progress = work / 'data/progress'
book_dir = progress / book_name
book_dir.mkdir(parents=True)
sha = lambda data: hashlib.sha256(data).hexdigest()
source_paths = [source / 'progress' / book_name / n for n in ['canonical_document.jsonl', '_chapters.json', 'ingestion_report.json', 'metadata.json']]
before = {p.name: sha(p.read_bytes()) for p in source_paths}
for p in source_paths:
    shutil.copy2(p, book_dir / p.name)
registry = source / 'progress/book_registry.json'
if registry.exists():
    shutil.copy2(registry, progress / registry.name)
database = source / 'progress' / f'exercise_bank_{book_name}.db'
with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(progress / database.name) as dst:
    database_before = sha('\n'.join(src.iterdump()).encode())
    src.backup(dst)
archive = next((source / 'uploads/mineru_outputs').glob('*.zip'))
with zipfile.ZipFile(archive) as z:
    archive_identity = {'file_sha256': sha(archive.read_bytes()), 'members': {}}
    for suffix, destination in [('structured_content.json', 'structured_content.json'), ('markdown.md', 'source-markdown.md')]:
        member = next(n for n in z.namelist() if n.endswith('/' + suffix))
        data = z.read(member)
        (work / destination).write_bytes(data)
        archive_identity['members'][member] = sha(data)
for key in list(os.environ):
    if key.endswith(('_API_KEY', '_API_TOKEN')) or key in {'PROGRESS_PATH', 'BOOKS_PATH', 'VECTOR_DB_PATH', 'IMAGES_PATH'}:
        os.environ.pop(key)
os.environ.update(ENV_PATH='/dev/null', DATA_DIR=str(work / 'data'), MINERU_OUTPUT_PATH=str(work / 'no-ocr'))
import config
def no_model(*_args, **_kwargs):
    raise AssertionError('Audit forbids model/OCR calls')
config.get_llm = no_model
from memory import textbook_exercise_importer as importer
importer._text_from_kimi_pdf_pages = no_model
from backend.api import exercises
exercises.refine_low_confidence_candidates = no_model
from backend.schemas import TextbookExerciseAnalyzeRequest
from ingestion.document_ir import load_canonical_book, canonical_book_fingerprint
from ingestion.document_workflows import learning_units
from memory.exercise_bank import question_fingerprint
from ingestion.document_adapters import _nested_text

params = dict(book_name=book_name, chapter='', page_start=None, page_end=None, source_mode='exercise_sections', limit=200, subject='', use_llm=False)
response = exercises.analyze_textbook_exercises(TextbookExerciseAnalyzeRequest(**params), book_name=book_name)
assert response.get('success'), response.get('message')
values = [item.model_dump() if hasattr(item, 'model_dump') else dict(item) for item in response['data']]
canonical = load_canonical_book(book_name, progress_root=progress)
units = learning_units(canonical)
assert len(units) == len(values)
raw = json.loads((work / 'structured_content.json').read_text())
pages = {p['page_idx']: p for p in raw['pages']}
block_index = {b.block_id: i for i, b in enumerate(canonical.blocks)}
records = []
bank_rows = {r.id: r.to_dict() for r in exercises._bank(book_name).list_all(limit=100000)}
for i, (candidate, unit) in enumerate(zip(values, units), 1):
    source_blocks = []
    for block in unit.blocks:
        page = pages.get(block.attributes.get('source_page_idx'), {})
        index = block.attributes.get('source_block_index')
        original = page.get('blocks', [])[index] if type(index) is int and index < len(page.get('blocks', [])) else None
        source_blocks.append({'canonical': block.to_dict(), 'mineru': original,
                              'mineru_text': _nested_text(original.get('content')) if original else ''})
    start, end = block_index[unit.blocks[0].block_id], block_index[unit.blocks[-1].block_id]
    following = [b.to_dict() for b in canonical.blocks[end+1:end+4]]
    row = {'audit_id': f'C{i:03d}', 'candidate': candidate,
           'unit': {'id': unit.unit_id, 'kind': unit.kind, 'label': unit.label, 'section_path': unit.section_path, 'truncated': unit.truncated},
           'page_start': min(b.page_start or 0 for b in unit.blocks), 'page_end': max(b.page_end or b.page_start or 0 for b in unit.blocks),
           'source_blocks': source_blocks, 'preceding_blocks': [b.to_dict() for b in canonical.blocks[max(0,start-2):start]], 'following_blocks': following,
           'question_sha256': sha(candidate['question_text'].encode()), 'unit_text_sha256': sha(unit.text.encode()),
           'question_equals_unit_text': candidate['question_text'] == unit.text.strip(),
           'duplicate_record': bank_rows.get(candidate['duplicate_of']),
           'automatic': {'block_types': dict(Counter(b.block_type for b in unit.blocks)),
                         'mineru_types': dict(Counter(b.attributes.get('mineru_type') for b in unit.blocks)),
                         'solution_marked_blocks': [b.block_id for b in unit.blocks if __import__('re').match(r'^\s*(?:解|解答|答案|分析|证明)\s*[：:]', b.text)],
                         'reference_figure': bool(__import__('re').search(r'如图|图\s*\d|下图|附图', candidate['question_text'])),
                         'reference_table': bool(__import__('re').search(r'表\s*\d|下表|附表', candidate['question_text']))}}
    records.append(row)
(work / 'candidates.private.json').write_text(json.dumps(records, ensure_ascii=False, indent=2))
issues = {r['audit_id'] for r in records if r['candidate']['validation_issues']}
dupes = {r['audit_id'] for r in records if r['candidate']['duplicate_of']}
warning_counts = Counter(w for r in records for w in r['candidate']['validation_issues'])
identity = {'code_head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'source_database_logical_sha256': database_before,
            'collector_sha256': sha(Path(__file__).read_bytes()),
            'python': sys.version.split()[0], 'book_alias': 'TEXA-D01-01', 'book_name': book_name,
            'source_hashes': before, 'previous_ir_sha256': sha((previous / 'data/progress' / book_name / 'canonical_document.jsonl').read_bytes()),
            'canonical_logical_sha256': canonical_book_fingerprint(canonical), 'parser_version': canonical.parser_version,
            'producer': canonical.source_metadata.get('producer'), 'pages': canonical.source_page_count,
            'source_archive': archive_identity, 'parameters': params, 'provider': response['extract']['provider'],
            'counts': {'candidates':len(records), 'warning_candidates':len(issues),'warning_instances':sum(warning_counts.values()),'duplicate_candidates':len(dupes),
                       'warning_duplicate_intersection':len(issues & dupes),'union':len(issues | dupes),'neither':len(records)-len(issues | dupes),
                       'warning_reasons':dict(warning_counts),'unit_kinds':dict(Counter(r['unit']['kind'] for r in records)),
                       'needs_llm':sum(r['candidate']['needs_llm'] for r in records),'needs_review':sum(r['candidate']['needs_review'] for r in records),
                       'bank_records':len(bank_rows), 'candidate_text_chars':sum(len(r['candidate']['question_text']) for r in records)},
            'dataset_sha256_excluding_random_candidate_id':sha(json.dumps([{k:v for k,v in r['candidate'].items() if k!='id'} for r in records],sort_keys=True,ensure_ascii=False).encode())}
identity['source_files_unchanged'] = before == {p.name:sha(p.read_bytes()) for p in source_paths}
with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as src:
    identity['source_database_unchanged'] = database_before == sha('\n'.join(src.iterdump()).encode())
(work / 'identity.json').write_text(json.dumps(identity,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(identity['counts'],ensure_ascii=False,indent=2))
