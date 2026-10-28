"""Read-only source/span and actual tokenizer audit; no inference/index writes."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def run(path):
    from tokenizers import Tokenizer, normalizers
    from ingestion.document_adapters import MinerUAdapter
    from ingestion.chapter_splitter import ChapterSplitter
    from ingestion.structure_quality import validate_index_structure
    from ingestion.embedding_contract import onnx_contract, prepare_embedding_views, validate_embedding_views

    payload = json.loads(path.read_text(encoding='utf-8'))
    book = MinerUAdapter.from_structured_content(payload, book_name='本地351页回归材料')
    rows = ChapterSplitter().split_canonical_book(book)
    integrity = validate_index_structure(book, rows)
    assets = ROOT/'assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1'
    tokenizer = Tokenizer.from_file(str(assets/'tokenizer.json'))
    tokenizer.normalizer = normalizers.Sequence([normalizers.Lowercase(), tokenizer.normalizer])
    contract = onnx_contract(assets, tokenizer)
    prepared = prepare_embedding_views(rows, contract)
    result = validate_embedding_views(prepared, contract)
    return dict(result, scope='local regression source, not customer screenshot; mechanical preservation only',
        pages=book.source_page_count, source_blocks=len(book.blocks), catalog_chunks=len(rows),
        indexable_chunks=sum(not r.get('retrieval_excluded') for r in rows), source=integrity,
        overlong_original_inputs=sum(contract.count(r['retrieval_text']) > contract.max_length
                                     for r in rows if not r.get('retrieval_excluded')),
        max_window_tokens=max(v['token_count'] for r in prepared for v in r['embedding_views']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'artifacts/question-extraction-quality-2026-10-17/structured_content.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
