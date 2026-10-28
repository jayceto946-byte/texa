"""Temporary real exercise API for ZIP/Electron QA; no production data or models."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
work = Path(os.environ['TEXA_QC_QA_WORK']).resolve()
os.environ.update(DATA_DIR=str(work / 'data'), ENV_PATH='/dev/null', MINERU_OUTPUT_PATH=str(work / 'no-ocr'))

import config


def no_model(*args, **kwargs):
    raise AssertionError('QA forbids models/OCR')


config.get_llm = no_model
from memory import exercise_file_importer
exercise_file_importer.MINERU_API_URL = ''
exercise_file_importer._extract_pdf_text_with_mineru = no_model
from backend.api import exercises
exercises.refine_low_confidence_candidates = no_model
from fastapi import FastAPI
import uvicorn

app = FastAPI()
app.include_router(exercises.router, prefix='/api')
uvicorn.run(app, host='127.0.0.1', port=18062, log_level='warning')
