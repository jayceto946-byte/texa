"""Synthetic, isolated navigation benchmark; never opens user storage."""
import ast
import subprocess
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from contextlib import closing
from backend import conversation_memory as memory
from backend.services.conversation_management import ConversationManagementService

root = Path(tempfile.mkdtemp(prefix='texa-history-bench-'))
memory.CONV_DIR = root / 'conversations'
with closing(memory._connect_events()) as conn:
    for i in range(500):
        cid = f'bench-{i}'
        conn.execute('INSERT INTO conversation_imports VALUES (?,?)', (cid, '2026-10-01'))
        (memory.CONV_DIR / f'{cid}.json').write_text('{}')
        for j in range(40):
            memory._insert_projection_message(conn, cid, {'id': f'm{j}', 'turn_id': f't{j//2}', 'role': 'user' if j % 2 == 0 else 'assistant', 'subject': '数学/高数', 'book_name': 'Book', 'created_at': f'2026-10-01T00:{j:02}:00', 'content': '合成问题' if j % 2 == 0 else '合成解答' * 100}, seq=j+1)
    conn.commit()
service = ConversationManagementService(progress_root=root)
# Replay the committed implementation against the very same temporary DB.
# AST extraction does not import a second config or open user data directories.
revision = 'd69a4b3'
def baseline_function(path, name, namespace, class_name=None):
    source = subprocess.check_output(['git', 'show', f'{revision}:{path}'], text=True)
    tree = ast.parse(source)
    body = tree.body if class_name is None else next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name).body
    function = next(n for n in body if isinstance(n, ast.FunctionDef) and n.name == name)
    local = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), path, 'exec'), namespace, local)
    return local[name]
from backend.services import conversation_management as management
old_catalog = baseline_function('backend/conversation_memory.py', 'conversation_catalog', memory.__dict__)
old_page = baseline_function('backend/services/conversation_management.py', 'page', management.__dict__, 'ConversationManagementService')
new_catalog = memory.conversation_catalog
new_page = type(service).page
samples = {'before': [], 'after': []}
reference = None
for cycle in range(10):
    for label in (['before', 'after'] if cycle % 2 == 0 else ['after', 'before']):
        memory.conversation_catalog = old_catalog if label == 'before' else new_catalog
        method = old_page if label == 'before' else new_page
        started = time.perf_counter()
        page = method(service, subject='数学', limit=40)
        elapsed = (time.perf_counter() - started) * 1000
        if reference is None: reference = page
        assert page == reference, 'navigation behavior changed'
        if cycle: samples[label].append(elapsed)
memory.conversation_catalog = new_catalog
medians = {label: statistics.median(values) for label, values in samples.items()}
print(json.dumps({'baseline_revision': revision, 'conversations': 500, 'messages': 20000,
    'paired_alternating_runs': 9, 'identical_page_and_cursor': True, 'samples_ms': samples,
    'median_ms': medians, 'reduction_percent': (1-medians['after']/medians['before'])*100}, indent=2))
