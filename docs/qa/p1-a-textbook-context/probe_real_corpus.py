"""Read-only existing lexical anchors -> final model messages, zero model calls.
Run from repository root with DATA_DIR set to the existing desktop data root:
  ENV_PATH=/dev/null venv310/bin/python -m docs.qa.p1-a-textbook-context.probe_real_corpus
Alternatively use runpy.run_path with the repository root on sys.path.
No Chroma client, trace store, model, or index publisher is instantiated.
"""
import hashlib
import json
from pathlib import Path
import time

from ingestion.document_ir import canonical_paths
from ingestion.lexical_index import index_path, load_book_index, search_book
from ingestion.index_pipeline import manifest_path
from graph.generator import prepare_answer_generation
from graph.evidence_pack import build_evidence_pack

book = '传感器原理及应用'
paths = [canonical_paths(book)[0], manifest_path(book), index_path(book)]
before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
rows = load_book_index(book)
results = []
for query, intent in [('压电效应的定义和公式', 'definition'), ('应变片的工作原理和推导', 'derivation'), ('热敏电阻的工作原理', 'qa')]:
    anchors = [{**row, 'text': row.get('text') or row.get('content') or ''} for row in search_book(book, query, k=3)]
    baseline = build_evidence_pack(anchors, intent=intent)
    state = {'intent': intent, 'user_input': query, 'book_name': book, 'subject': '专业课',
             'answer_mode': 'textbook_grounded', 'use_textbook_context': True, 'evidence_items': anchors}
    start = time.perf_counter()
    messages = prepare_answer_generation(state)
    final = state['verification_evidence']
    results.append({'query': query, 'anchors': len(anchors), 'baseline_chars': baseline['char_count'],
                    'expanded_chars': sum(len(item['text']) for item in final),
                    'elapsed_ms': round((time.perf_counter()-start)*1000, 2),
                    'visible_text_bound': all(item['text'] in messages[-1].content for item in final),
                    'statuses': [item.get('learning_unit', {}).get('status', 'not_expanded') for item in final],
                    'reasons': [item.get('learning_unit', {}).get('reason', '') for item in final],
                    'block_counts': [len(item.get('source_block_ids', [])) for item in final],
                    'index_versions': sorted({item.get('index_version', '') for item in final}),
                    'canonical_hashes': sorted({item.get('canonical_hash', '') for item in final})})
after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
payload = {'kind': 'read_only_existing_lexical_anchors_to_final_messages', 'catalog_rows': len(rows),
           'model_calls': 0, 'dense_retrieval': 'NOT VERIFIED', 'model_answer_quality': 'NOT VERIFIED',
           'source_files_unchanged': before == after, 'results': results}
Path(__file__).with_name('real-corpus-probe.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(payload, ensure_ascii=False, indent=2))
