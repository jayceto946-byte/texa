"""Synthetic-only extension of existing P1-C Electron fixture."""
from scripts.qa_p1c_server import app, fixture
from backend.api import exercises
from memory import textbook_exercise_importer as importer
from ingestion.document_ir import CanonicalBook, DocumentBlock, canonical_book_fingerprint
from ingestion.document_workflows import learning_units
from memory.exercise_candidate_projection import source_registry
from backend.services.exercise_candidate_review import ExerciseCandidateReviewService

blocks = [DocumentBlock('h','heading','习题',['第一章','习题'],page_start=1,page_end=1),
          DocumentBlock('q','paragraph','1. 计算 $2+3$。',['第一章','习题'],page_start=1,page_end=1),
          DocumentBlock('e','example','【例1】计算 $3+4$。',['第一章','例题'],page_start=2,page_end=2),
          DocumentBlock('s','paragraph','解：相加得7。',['第一章','例题'],page_start=2,page_end=2),
          DocumentBlock('f','paragraph','2. 根据图1.1求输出。',['第一章','习题'],page_start=3,page_end=3)]
book = CanonicalBook('integration-toy','pdf',blocks,'integration-synthetic-v1')
units = [dict(unit_id=u.unit_id,kind=u.kind,text=u.text,chapter=u.section_path[0],page_start=u.blocks[0].page_start,
              page_end=max(b.page_end for b in u.blocks),source_block_ids=[b.block_id for b in u.blocks],truncated=u.truncated) for u in learning_units(book)]
registry = source_registry(book,units,{b.block_id for b in blocks})

def extract(book_name, **kwargs):
    assert book_name == book.book_name
    return importer.ExtractedTextbookExerciseText(text='\n\n'.join(u['text'] for u in units),provider='canonical-learning-units',book_name=book_name,
              units=units,source_blocks=registry,canonical_hash=canonical_book_fingerprint(book))
exercises.extract_textbook_exercise_text = extract
importer.extract_textbook_exercise_text = extract

@app.get('/p1abc-fixture')
def candidate_fixture():
    return {'book':'integration-toy','units':len(units),'synthetic':True}
app.router.routes.insert(0,app.router.routes.pop())
