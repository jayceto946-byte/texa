"""Fresh authored note per Electron run, exclusively in the disposable QA store."""
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
evidence = Path(sys.argv[1]).resolve()
ids = json.loads((evidence / 'notes-fixture-ids.json').read_text())
qa = Path(ids['qa_root']).resolve()
if not qa.is_relative_to(Path('/private/tmp')) or not qa.name.startswith('texa-notes-audit-fixes-'):
    raise SystemExit('QA storage only')
os.environ.update(DATA_DIR=str(qa/'data'), PROGRESS_PATH=str(qa/'progress'),
                  BOOKS_PATH=str(qa/'books'), VECTOR_DB_PATH=str(qa/'vector'))
from memory.session_notes import SessionNoteStore, now
from backend.services.session_notes.service import SessionNoteService
from backend.services.session_notes.validation import validate_document
store = SessionNoteStore(qa/'progress/session_notes.db')
snapshot = store.get('note_source_snapshots', 'review-snapshot')
document, quality = validate_document(json.loads((evidence/'note-content.json').read_text()), snapshot)
draft_id = 'audit-seed-' + uuid.uuid4().hex
stamp = now()
draft = {**store.get('note_drafts', 'review-preview'), 'id': draft_id,
         'content': {**document, 'quality': quality}, 'draft_revision': 1,
         'status': 'editable', 'base_note_id': None, 'base_note_revision': None,
         'created_at': stamp, 'updated_at': stamp}
with store.transaction() as conn:
    store.put_draft(conn, draft)
receipt = SessionNoteService(store).save(draft_id, {
    'operation_id': draft_id, 'expected_draft_revision': 1, 'base_note_revision': None})
(evidence/(draft_id+'.json')).write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt))
