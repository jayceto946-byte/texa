"""Isolated deterministic fixture for P1-C Electron/API smoke (no model/OCR).

Run with DATA_DIR/MINERU_OUTPUT_PATH set to an empty disposable directory and
uvicorn --lifespan off. Readiness is a fixture; backend startup is not under test.
"""
import json
import os
from pathlib import Path

if not os.getenv('TEXA_P1C_QA') or not os.getenv('DATA_DIR') or not os.getenv('MINERU_OUTPUT_PATH'):
    raise RuntimeError('P1-C QA requires explicit isolated data paths')

# The QA harness must never be redirected at an existing user library.
import tempfile
qa_root = Path(os.environ.get('TEXA_P1C_QA_ROOT', '')).resolve()
if (not qa_root.name.startswith('texa-p1c-electron-')
        or not qa_root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        or Path(os.environ['DATA_DIR']).resolve() != qa_root / 'data'
        or Path(os.environ['MINERU_OUTPUT_PATH']).resolve() != qa_root / 'mineru'):
    raise RuntimeError('P1-C QA paths must belong to its disposable temporary root')

from backend.main import app, _update_warmup
from backend.api import exercises, mistakes
from backend.job_manager import get_job_manager
from knowledge.exercise_structure import build_catalog, validate_classification
from memory.exercise_bank import ExerciseRecord
from memory.mistake_lifecycle import MistakeLifecycleStore

book = 'default'
kg_dir = Path(os.environ['MINERU_OUTPUT_PATH']) / book / 'hybrid_auto'
kg_dir.mkdir(parents=True, exist_ok=True)
(kg_dir / f'{book}_knowledge_graph.json').write_text(json.dumps({
    'meta': {'version': 1}, 'concepts': [
        {'concept_id': 'c1', 'canonical_name': 'Stokes', 'aliases': [], 'roles': ['theorem']},
        {'concept_id': 'c2', 'canonical_name': '曲面方向', 'aliases': [], 'roles': ['property']}],
    'occurrences': [], 'relations': [], 'formulas': []}))
record = ExerciseRecord(id='p1c-exercise', question_text='用 Stokes 公式计算曲线积分。', subject='数学/高数')
bank = exercises._bank(book)
if not bank.get(record.id):
    bank.add(record)
record = bank.get(record.id)
structure = validate_classification({'status': 'proposed', 'primary': {'concept_id': 'c1', 'basis': '题干 Stokes'},
    'related': [{'concept_id': 'c2', 'basis': '方向条件'}], 'basis': '考查公式与方向'}, build_catalog(record, book_name=book))
job = get_job_manager().create_job(exercises.EXERCISE_ANSWER_JOB_TYPE, {'exercise_id': record.id, 'book_name': book},
    status='running')
get_job_manager().update_job(job['id'], status='completed', result={'answer': '参考结果 2', 'knowledge_structure': structure})
mb = mistakes._mb(book)
if not mb.get('p1c-mistake'):
    mb.add(exercises._mistake_from_exercise(record, user_answer='先取曲面\n法向取反\n积分为2', mistake_id='p1c-mistake'))
lifecycle = MistakeLifecycleStore(mb.store)
aid = lifecycle.append_occurrence_once('p1c-mistake', 'fixture-attempt', answer='先取曲面\n法向取反\n积分为2', source_ref={'type': 'exercise_attempt', 'exercise_id': record.id})
_update_warmup(status='ready', stage='ready', message='P1-C fixture (warmup not tested)')

@app.get('/p1c-fixture')
def fixture():
    return {'book': book, 'exercise_id': record.id, 'mistake_id': 'p1c-mistake', 'attempt_id': aid, 'job_id': job['id']}

# Register before the existing catch-all SPA mount.
app.router.routes.insert(0, app.router.routes.pop())
