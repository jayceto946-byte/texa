"""QA-only real textbook import job/API with isolated data and no LLM/OCR."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
work = Path(os.environ['TEXA_INDEX_QA_WORK']).resolve()
os.environ.update({key: str(path) for key, path in dict(DATA_DIR=work/'data', VECTOR_DB_PATH=work/'data/vector_db',
    PROGRESS_PATH=work/'data/progress', BOOKS_PATH=work/'data/books', CHAPTERS_PATH=work/'data/chapters',
    IMAGES_PATH=work/'data/images', MINERU_OUTPUT_PATH=work/'mineru', ENV_PATH=work/'absent.env').items()})
os.environ.update(TEXA_EMBEDDING_BACKEND='onnx', HF_HUB_OFFLINE='1', ANONYMIZED_TELEMETRY='False',
    RERANKER_MODEL_PATH='', MINERU_API_URL='', MINERU_CLI_COMMAND='',
    TEXA_EMBEDDING_ASSET_DIR=str(ROOT/'assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1'))
import config


def no_model(*args, **kwargs):
    raise AssertionError('QA forbids LLM/OCR calls')


config.get_llm = config.get_llm_client = no_model
from graph import retrieval_node
from graph.safe_retrieval import SafeKG
retrieval_node.get_safe_kg = lambda _: (SafeKG(), '')
retrieval_node._load_history = lambda *_: []
from ingestion import mineru_importer
mineru_importer.load_kg_chunk_roles = lambda _: {}
from backend.api import books
from fastapi import FastAPI
import uvicorn

app = FastAPI()
app.include_router(books.router, prefix='/api')
uvicorn.run(app, host='127.0.0.1', port=18862, log_level='warning')
