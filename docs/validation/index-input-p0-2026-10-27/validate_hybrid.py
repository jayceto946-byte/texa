"""Synthetic source, real isolated ONNX/Chroma/production EvidencePack gate.

Never opens the user's active data directories or calls OCR/LLM services.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def payload(long=False):
    body = ('测量响应由输入参数决定，' * 52 + '尾端校验常数为四十二。') if long else '旧版定义：响应由输入与参数共同决定。'
    formula = '$$F=' + '+'.join(f'c_{{{i}}}x_{{{i}}}' for i in range(1, 81)) + '$$' if long else '$$F=kx$$'
    blocks = [dict(type='paragraph_title', content='第1章 通用建库'),
              dict(type='paragraph_title', content='1.1 响应定义'), dict(type='text', content=body),
              dict(type='equation', content=formula)]
    if long:
        header = ['参数'+n for n in '甲乙丙丁戊己庚辛']
        cells = ['原文数值说明' * 18 + str(i) for i in range(8)]
        table = '| ' + ' | '.join(header) + ' |\n| ' + ' | '.join('---' for _ in header) + ' |\n| ' + ' | '.join(cells) + ' |'
        blocks += [dict(type='paragraph_title', content='1.2 参数'),
                   dict(type='table', content=table, captions=[dict(content='表1 通用参数')], footnotes=[dict(content='注：以上均为合成来源。')])]
    return dict(metadata=dict(producer=dict(name='mineru', version='4.0.12'), document=dict(page_count=1)),
                pages=[dict(page_idx=0, blocks=blocks)])


def run():
    with tempfile.TemporaryDirectory(prefix='texa-input-contract-') as temporary:
        root = Path(temporary)
        os.environ.update({key: str(value) for key, value in dict(DATA_DIR=root/'data',
            VECTOR_DB_PATH=root/'data/vector_db', PROGRESS_PATH=root/'data/progress', BOOKS_PATH=root/'data/books',
            CHAPTERS_PATH=root/'data/chapters', IMAGES_PATH=root/'data/images', MINERU_OUTPUT_PATH=root/'mineru',
            ENV_PATH=root/'absent.env').items()})
        os.environ.update(TEXA_EMBEDDING_BACKEND='onnx', HF_HUB_OFFLINE='1', ANONYMIZED_TELEMETRY='False',
            RERANKER_MODEL_PATH='', TEXA_EMBEDDING_ASSET_DIR=str(ROOT/'assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1'))
        from ingestion import mineru_importer, index_pipeline, lexical_index
        from ingestion.vector_store import get_vector_store
        from ingestion.document_ir import load_canonical_book, canonical_book_fingerprint
        from ingestion.structure_quality import validate_index_structure
        from ingestion.embedding_contract import validate_embedding_views
        from graph import retrieval_node
        from graph.safe_retrieval import SafeKG

        source = root/'input'
        source.mkdir()
        book_name = 'P0 通用合成验收'
        path = source/'structured_content.json'
        with patch.object(retrieval_node, 'get_safe_kg', lambda _: (SafeKG(), '')), \
             patch.object(retrieval_node, '_load_history', lambda *_: []), \
             patch.object(mineru_importer, 'load_kg_chunk_roles', lambda _: {}):
            path.write_text(json.dumps(payload(), ensure_ascii=False))
            mineru_importer.import_textbook_from_mineru_output(source, book_name)
            first = index_pipeline.load_index_manifest(book_name)
            path.write_text(json.dumps(payload(True), ensure_ascii=False))
            imported = mineru_importer.import_textbook_from_mineru_output(source, book_name)
            manifest = index_pipeline.load_index_manifest(book_name)
            store = get_vector_store()
            c = store.embeddings.input_contract
            book = load_canonical_book(book_name, progress_root=root/'data/progress')
            rows = json.loads(lexical_index.index_path(book_name).read_text())
            assert canonical_book_fingerprint(book) == manifest['canonical_hash']
            assert validate_index_structure(book, rows)['span_errors'] == 0
            assert validate_embedding_views(rows, c)['silent_truncations'] == 0
            assert max(v['token_count'] for r in rows for v in r['embedding_views']) <= c.max_length
            collection = store._client.get_collection(manifest['aggregate_collection'])
            values = collection.get(include=['documents', 'metadatas'])
            assert all(c.count(text) <= c.max_length for text in values['documents'])
            assert any('尾端校验常数为四十二' in text for text in values['documents'])
            formula_source = next(b.text for b in book.blocks if b.block_type == 'formula')
            assert any(meta['raw_content'] == formula_source for meta in values['metadatas'])
            query = store.search_all('尾端校验常数为四十二', book_name=book_name, k=4, top_n=2)
            assert query.status != 'failed'
            items = [retrieval_node._doc_to_item(d, chapter, 'vector') for chapter, docs in query.items.items() for d in docs]
            assert any('尾端校验常数为四十二' in item['text'] for item in items)
            assert manifest['release_quality']['status'] == 'passed'
            assert manifest['release_quality']['recall_at_k'] == manifest['release_quality']['point_recall'] == 1.0
            before_manifest = index_pipeline.manifest_path(book_name).read_bytes()
            before_lexical = lexical_index.index_path(book_name).read_bytes()
            before_map = dict(store._map)
            damaged = payload(True)
            damaged['pages'][0]['blocks'][2]['content'] += '这是应被拒绝发布的候选。'
            path.write_text(json.dumps(damaged, ensure_ascii=False))
            with patch.object(index_pipeline, '_validate_staged_production_retrieval', side_effect=RuntimeError('injected rejection')):
                try:
                    mineru_importer.import_textbook_from_mineru_output(source, book_name)
                    raise AssertionError('candidate should be rejected')
                except RuntimeError as exc:
                    assert 'injected rejection' in str(exc)
            assert index_pipeline.manifest_path(book_name).read_bytes() == before_manifest
            assert lexical_index.index_path(book_name).read_bytes() == before_lexical and store._map == before_map
            rollback = index_pipeline.activate_retained_index_version(store, book_name, first['index_version'])
            assert rollback['canonical_hash'] == first['canonical_hash']
            assert rollback['embedding_contract']['id'] == first['embedding_contract']['id']
            return dict(scope='synthetic; real local ONNX FP32/Chroma + production retrieval/Final EvidencePack; not customer-book or OCR accuracy',
                chunks=imported.indexed_chunks, aggregate_vectors=manifest['vector_count'],
                embedding_integrity=manifest['embedding_integrity'], source_integrity=manifest['source_integrity'],
                max_window_tokens=max(v['token_count'] for r in rows for v in r['embedding_views']),
                release_quality=manifest['release_quality'], dense_tail_retrieved=True,
                full_formula_hydrated=True, failed_candidate_keeps_active=True, rollback_contract_restored=True,
                embedding_contract=manifest['embedding_contract'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
