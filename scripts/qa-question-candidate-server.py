"""Local QA-only server: real exercise router, frozen IR copy, temporary SQLite.
No app lifespan, OCR, models, vector store or production writes.
"""
import os, sys, json, sqlite3, shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
work=Path(os.environ['TEXA_QC_QA_WORK']).resolve()
source=Path('artifacts/question-extraction-quality-2026-10-17/data/progress')
progress=work/'data/progress';progress.mkdir(parents=True,exist_ok=True)
book='传感器原理及应用'
shutil.copytree(source/book,progress/book,dirs_exist_ok=True)
shutil.copy2(source/'book_registry.json',progress/'book_registry.json')
with sqlite3.connect(f'file:{source}/exercise_bank_{book}.db?mode=ro',uri=True) as src, sqlite3.connect(progress/f'exercise_bank_{book}.db') as dst: src.backup(dst)
os.environ.update(DATA_DIR=str(work/'data'),ENV_PATH='/dev/null',MINERU_OUTPUT_PATH=str(work/'no-ocr'))
import config

def no_model(*args,**kwargs):raise AssertionError('QA forbids models/OCR')
config.get_llm=no_model
from memory import textbook_exercise_importer
textbook_exercise_importer._text_from_kimi_pdf_pages=no_model
from backend.api import exercises
exercises.refine_low_confidence_candidates=no_model
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
app=FastAPI();app.include_router(exercises.router,prefix='/api')
uvicorn.run(app,host='127.0.0.1',port=18062,log_level='warning')
