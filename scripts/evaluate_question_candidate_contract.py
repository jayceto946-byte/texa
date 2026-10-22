"""Frozen D-01 v1 differential; read-only sources, writes only reports and temporary DB.
Run from repository root with venv310/bin/python. No OCR/model calls.
"""
import sys, tempfile
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
import json,hashlib
from pathlib import Path
import memory.textbook_exercise_importer as imp
from memory.exercise_bank import ExerciseBank,question_fingerprint
base=Path('artifacts/question-extraction-quality-2026-10-17')
imp.PROGRESS_PATH=base/'data/progress'
protected = [p for p in (base/'data').rglob('*') if p.is_file()]
protected += list(Path('docs/qa/question-extraction-quality-2026-10-17').glob('*.json'))
protected += [Path('docs/qa/question-extraction-quality-2026-10-17/candidate-audit.jsonl')]
before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
manifest=json.loads(Path('docs/qa/question-extraction-quality-2026-10-17/dataset-manifest.json').read_text())
for name in ['ingestion/document_workflows.py','ingestion/document_ir.py','ingestion/document_adapters.py','ingestion/mineru_structured.py','frontend/src/utils/mathText.ts','frontend/src/features/reading/readingMath.ts']:
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==manifest['source_file_hashes'][name]
assert before[str(base/'data/progress/传感器原理及应用/canonical_document.jsonl')]==manifest['source_file_sha256']['canonical_document.jsonl']
def no_model(*args,**kwargs): raise AssertionError('No model or OCR allowed')
imp._text_from_kimi_pdf_pages=no_model
import config
config.get_llm=no_model
e=imp.extract_textbook_exercise_text('传感器原理及应用',candidate_contract_version=1)
scope=dict(chapter='',page_start=None,page_end=None,source_mode='exercise_sections')
c=imp.analyze_learning_unit_candidates(e.units,book_name='传感器原理及应用',subject='传感器原理及应用',limit=200,source_blocks=e.source_blocks,canonical_hash=e.canonical_hash,scope=scope)
old=json.loads((base/'candidates.private.json').read_text())
# Read existing SQLite through read-only URI, do not initialize/mutate frozen bank.
import sqlite3
conn=sqlite3.connect(f'file:{base}/data/progress/exercise_bank_传感器原理及应用.db?mode=ro',uri=True)
source_bank_hash=hashlib.sha256('\n'.join(conn.iterdump()).encode()).hexdigest()
assert source_bank_hash==manifest['source_bank_logical_sha256']
existing={question_fingerprint((r:=json.loads(row[0]))['question_text']):r['id'] for row in conn.execute('select data from exercises')};conn.close()
ledger=[json.loads(l) for l in Path('docs/qa/question-extraction-quality-2026-10-17/candidate-audit.jsonl').read_text().splitlines()]
report=[]
for prev, audit, new in zip(old,ledger,c):
 p=new.projection
 assert p['unit_ids']==[audit['source']['unit_id']]
 assert new.review is None
 roles={r:[s['block_id'] for s in spans] for r,spans in p['parts'].items()}
 assert set(audit['source']['block_ids']) <= {bid for ids in roles.values() for bid in ids}
 oldbody=prev['candidate'];newbody=new.to_dict()
 dup=existing.get(question_fingerprint(new.question_text),'')
 report.append(dict(audit_id=audit['audit_id'],unit_ids=p['unit_ids'],canonical_hash=e.canonical_hash,source_text_hash=audit['original_text']['sha256'],bodies={k:dict(before_hash=hashlib.sha256(oldbody[k].encode()).hexdigest(),after_hash=hashlib.sha256(newbody[k].encode()).hexdigest(),before_chars=len(oldbody[k]),after_chars=len(newbody[k])) for k in ('question_text','answer','explanation')},roles=roles,dependencies=p['dependencies'],issues=new.issues,review=None,method=p['method'],admissible=not any(i['category']=='content' for i in new.issues),duplicate_of=dup,old_duplicate_of=oldbody.get('duplicate_of',''),previously_ready=audit['review']['stem_ready_for_independent_practice']))
assert e.canonical_hash==manifest['canonical_logical_sha256']
assert len(c)==108
assert all(not n.answer and not n.explanation for u,n in zip(e.units,c) if u['kind']=='exercise')
assert all(r['admissible'] for r in report if r['previously_ready'])
assert all(r['duplicate_of']==r['old_duplicate_of'] for r in report if r['old_duplicate_of'])
out=Path('docs/validation/question-candidate-contract-2026-10-18');out.mkdir(exist_ok=True,parents=True)
(out/'candidate-diff.json').write_text(json.dumps(dict(canonical_hash=e.canonical_hash,rows=report),ensure_ascii=False,indent=2)+'\n')
from backend.services.exercise_candidate_review import ExerciseCandidateReviewService
service=ExerciseCandidateReviewService()
selected=[x for x,r in zip(c,report) if r['admissible']]
items=[dict(origin_id=x.id,question_text=x.question_text,answer=x.answer,explanation=x.explanation,
            candidate_context=dict(projection=x.projection,review=x.review)) for x in selected]
receipts=service.prepare('传感器原理及应用',items)
from memory.exercise_bank import ExerciseRecord
with tempfile.TemporaryDirectory(prefix='texa-v1-batch-') as work:
    db=Path(work)/'bank.db'
    with sqlite3.connect(f'file:{base}/data/progress/exercise_bank_传感器原理及应用.db?mode=ro',uri=True) as src, sqlite3.connect(db) as dst:
        src.backup(dst)
    bank=ExerciseBank(db)
    batch=bank.add_batch([ExerciseRecord(question_text=x.question_text,answer=x.answer,explanation=x.explanation,origin_id=x.id) for x in selected],candidate_receipts=receipts)
    assert len(batch['skipped'])==16
    assert len(batch['candidate_receipts'])==len(selected)-16
    assert all(s['duplicate_of']==existing[question_fingerprint(next(x for x in selected if x.id==s['origin_id']).question_text)] for s in batch['skipped'])
    assert bank.list_import_batches()[0]['candidate_receipts']==batch['candidate_receipts']
    imported=len(batch['exercise_ids'])
assert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
(out/'integrity.json').write_text(json.dumps(dict(input_hashes=before,unchanged=True,canonical_logical_hash=e.canonical_hash,source_bank_logical_hash=source_bank_hash,coverage=108,empty_source_answers=94,ready_preserved=92,duplicate_maps=16,isolated_batch=dict(submitted=len(selected),saved=imported,skipped=16,receipt_count=imported),model_ocr_calls=0),ensure_ascii=False,indent=2)+'\n')
print('108 coverage, 94 empty answers, 92 ready preserved, 16 duplicate maps identical')
print('methods',{m:sum(r['method']==m for r in report) for m in {r['method'] for r in report}})
print('ready',sum(r['admissible'] for r in report))
Path('artifacts/question-candidate-contract').mkdir(parents=True,exist_ok=True)
Path('artifacts/question-candidate-contract/candidates.private.json').write_text(json.dumps(dict(data=[x.to_dict() for x in c],extract=e.to_dict()),ensure_ascii=False))
