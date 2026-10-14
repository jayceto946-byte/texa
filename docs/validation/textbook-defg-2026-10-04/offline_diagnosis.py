"""Read-only D02/F01/F03 probes. No model calls or production database writes.

Pass --snapshot-dir containing stable local copies of the four diagnostic DBs.
Only metadata, identifiers and support results are exported, never source bodies.
"""
import argparse
import json
from pathlib import Path
import re
import sqlite3
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from graph.retrieval_node import retrieve_node, _extract_query_focus, _supports_query_literals
from graph.safe_retrieval import SafeKG
from graph.evidence_pack import build_evidence_pack
from ingestion.lexical_index import search_rows, expand_neighbors_rows
from ingestion.vector_store import RetrievalOutcome
from backend.services.session_notes.generation import generate

parser = argparse.ArgumentParser()
parser.add_argument('--snapshot-dir', type=Path, required=True)
args = parser.parse_args()
data = Path.home() / 'Library/Application Support/kaoyan-assistant-desktop/data'
book = '传感器原理及应用'
version = 'c8b6947edb7858f2'
rows = json.loads((data / f'vector_db/_lexical_versions/{book}/{version}.json').read_text())

class EmptyVectors:
    def search_all(self, *a, **kw):
        return RetrievalOutcome(items={})
    def search_chapter(self, *a, **kw):
        return RetrievalOutcome(items=[])

def probe(name, query, intent, chapters):
    state = dict(user_input=query, book_name=book, subject='专业课', intent=intent,
                 target_chapters=chapters, answer_mode='textbook_grounded', use_textbook_context=True)
    with patch('graph.retrieval_node.get_safe_kg', return_value=(SafeKG(), '')), patch('graph.retrieval_node._load_history', return_value=[]):
        result = retrieve_node(state, vector_store=EmptyVectors(),
            lexical_search=lambda b, q, **kw: search_rows(rows, q, **kw),
            neighbor_expander=lambda b, ids, **kw: expand_neighbors_rows(rows, ids, **kw),
            index_stats_override={book: {'healthy': True}},
            retrieval_resources_override=[dict(book_name=book, is_primary=True, is_selected=True, role='core', priority=1)])
    pack = build_evidence_pack(result['evidence_items'], intent=intent)
    return dict(name=name, support=result['evidence_support'], error=result['retrieval_error'],
        candidate_count=len(result['retrieval_debug_items']), evidence_count=len(pack['items']),
        evidence=[{k: item.get(k) for k in ('chunk_id', 'section_title', 'page_start')} for item in pack['items']])

conn = sqlite3.connect(args.snapshot_dir / f'exercise_bank_{book}.db')
record = json.loads(conn.execute('SELECT data FROM exercises WHERE id=?', ('f51865b2',)).fetchone()[0])
conn.close()
q = record['question_text']
without_number = re.sub(r'^\s*\d+[.、．]\s*', '', q)
result = dict(corpus_version=version, lexical_rows=len(rows), boundary='Actual lexical snapshot; production retrieve_node and EvidencePack; empty vectors, disabled KG/history, fixed chapters; no planner or model calls. Not historical exact replay or answer quality evaluation.',
    focus_probes=[dict(form='prefix_definition', result=_extract_query_focus('什么是电阻式传感器？', [])),
                  dict(form='suffix_definition', result=_extract_query_focus('电阻式传感器是什么？', [])),
                  dict(form='named_topic', result=_extract_query_focus('什么是电阻式传感器？', ['电阻式传感器']))],
    literal_probe=dict(numbered=_supports_query_literals(q, '二阶测量系统的动态响应'),
                       unnumbered=_supports_query_literals(without_number, '二阶测量系统的动态响应')),
    retrieval_probes=[probe('definition_prefix', '什么是电阻式传感器？', 'definition', []),
                      probe('definition_suffix', '电阻式传感器是什么？', 'definition', []),
                      probe('exercise_original', q, 'application', [record['chapter']]),
                      probe('exercise_number_removed', without_number, 'application', [record['chapter']])])

conn = sqlite3.connect(args.snapshot_dir / 'session_notes.db')
snapshot = json.loads(conn.execute('SELECT document_json FROM note_source_snapshots WHERE id=?', ('snapshot_47c3f95f858b42119764da7c401fa613',)).fetchone()[0])
conn.close()
# Inspect the first call's plan without sending any input to a provider.
class Captured(Exception):
    pass
def capture(payload, **kw):
    result['note_input_plan'] = dict(sources=len(snapshot['sources']), turns=len({s['turn_id'] for s in snapshot['sources']}),
        evidence=len(snapshot['evidence']), chapters=len(snapshot['chapter_refs']),
        included_messages=len(payload['messages']), input_bytes=len(json.dumps(payload, ensure_ascii=False).encode()),
        phase=payload['phase'], timeout=kw['timeout'], max_tokens=kw['max_tokens'])
    raise Captured()
try:
    generate(snapshot, call=capture, config=dict(context_tokens=32000, output_tokens=8000, extraction_output_tokens=2400, max_batches=8, max_seconds=600))
except Captured:
    pass
conn = sqlite3.connect(args.snapshot_dir / 'jobs.sqlite3')
result['note_attempts'] = [dict(id=r[0], status=r[1], stage=r[2], error_code=r[3]) for r in conn.execute("SELECT id,status,stage,error FROM jobs WHERE type='session_note_generate' AND json_extract(input_json,'$.snapshot_id')=? ORDER BY created_at", (snapshot['id'],))]
conn.close()
output = Path(__file__).with_name('offline_diagnosis.json')
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False, indent=2))
