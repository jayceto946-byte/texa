"""Inspect only the isolated Electron QA data, including real dense retrieval."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
work, name = Path(sys.argv[1]), sys.argv[2]
result_stream = sys.stdout
sys.stdout = sys.stderr
os.environ.update(DATA_DIR=str(work/'data'), PROGRESS_PATH=str(work/'data/progress'),
    VECTOR_DB_PATH=str(work/'data/vector_db'), BOOKS_PATH=str(work/'data/books'),
    MINERU_OUTPUT_PATH=str(work/'mineru'), ENV_PATH=str(work/'absent.env'), TEXA_EMBEDDING_BACKEND='onnx',
    HF_HUB_OFFLINE='1', ANONYMIZED_TELEMETRY='False',
    TEXA_EMBEDDING_ASSET_DIR=str(ROOT/'assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1'))
from ingestion.document_ir import load_canonical_book
from ingestion.document_workflows import canonical_outline, learning_units
from ingestion.index_pipeline import load_index_manifest
from ingestion.lexical_index import load_book_index
from ingestion.vector_store import get_vector_store
from memory.textbook_exercise_importer import extract_textbook_exercise_text

book = load_canonical_book(name)
outline = canonical_outline(book)
rows = load_book_index(name)
store = get_vector_store()
for chapter in outline:
    docs = store.search_chapter(chapter['title'], '条件与函数', book_name=name)
    assert docs.status != 'failed' and docs.items
    assert all(d.metadata['chapter'] == chapter['title'] for d in docs.items)
extracted = extract_textbook_exercise_text(name, source_mode='exercise_sections', candidate_contract_version=1)
assert len(extracted.units) == 2
second = extract_textbook_exercise_text(name, chapter='第二章 映射', source_mode='exercise_sections', candidate_contract_version=1)
assert len(second.units) == 1 and '条件乙' in second.text and '条件甲' not in second.text
demoted = [b for b in book.blocks if b.text == '一、附加说明']
print(json.dumps(dict(chapters=len(outline), exercise_units=len(extracted.units),
    scoped_exercise_units=len(second.units), dense_scope_preserved=True,
    body_retained=len(demoted) == 2 and all(any(b.text in r['content'] for r in rows) for b in demoted),
    release_passed=load_index_manifest(name)['release_quality']['status'] == 'passed',
    recovery=book.source_metadata['outline_recovery']), ensure_ascii=False), file=result_stream)
