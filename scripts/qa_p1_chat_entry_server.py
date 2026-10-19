"""Render existing isolated chat-entry receipts; no startup/model execution."""
import os
from pathlib import Path

root = Path('/private/tmp/texa-p1-chat-entry-20261019')
assert Path(os.environ['PROGRESS_PATH']).resolve() == root / 'progress'
assert Path(os.environ['DATA_DIR']).resolve() == root / 'data'
from backend.main import app, _update_warmup

_update_warmup(status='ready', stage='ready', message='Saved chat-entry acceptance; startup not tested')
