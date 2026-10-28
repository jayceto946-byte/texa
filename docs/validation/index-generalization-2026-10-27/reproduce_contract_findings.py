"""Read-only, book-independent reproductions used by the indexing investigation.

No index construction, network, OCR, model inference or production writes.
The output records current behavior; it does not assert that bugs must remain.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def run():
    from tokenizers import Tokenizer
    from tokenizers.normalizers import Lowercase, Sequence
    from ingestion.chapter_splitter import ChapterSplitter
    from ingestion.document_adapters import MinerUAdapter, _BlockBuilder
    from ingestion.document_ir import CanonicalBook, DocumentBlock, validate_canonical_book
    from ingestion.document_workflows import canonical_outline
    from ingestion.index_pipeline import _fingerprint
    from ingestion.structure_quality import validate_index_structure

    book = CanonicalBook('合成教材', 'pdf_text', [DocumentBlock('b1', 'paragraph', '甲乙丙丁' * 160,
        ['第一章 合成正文'], source_kind='pdf_text', page_start=1, page_end=1)], 'synthetic')
    rows = ChapterSplitter().split_canonical_book(book)
    tokenizer = Tokenizer.from_file(str(ROOT / 'assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1/tokenizer.json'))
    tokenizer.normalizer = Sequence([Lowercase(), tokenizer.normalizer])
    tokenizer.no_padding()
    tokenizer.no_truncation()
    full_lengths = [len(tokenizer.encode(row['retrieval_text']).ids) for row in rows]
    tokenizer.enable_truncation(max_length=512, direction='right')
    visible_lengths = [len(tokenizer.encode(row['retrieval_text']).ids) for row in rows]
    changed = [dict(row, retrieval_text='不同的嵌入输入：' + row['retrieval_text']) for row in rows]
    corrupted = [dict(row, content='正文已丢失', retrieval_text='正文已丢失') for row in rows]
    try:
        validate_index_structure(book, corrupted)
        membership_check_detects_text_loss = False
    except RuntimeError:
        membership_check_detects_text_loss = True
    identities = []
    for kind in ('paragraph', 'heading'):
        builder = _BlockBuilder('合成教材', source_kind='mineru', source_file='source.json')
        identities.append(builder.add(kind, '同一来源文字', page_start=1, page_end=1,
            attributes=dict(source_page_idx=0, source_block_index=0)).block_id)
    payload = dict(metadata=dict(producer=dict(name='mineru', version='4.0.12'), document=dict(page_count=1)),
        is_full_document=False, pages=[dict(page_idx=0, blocks=[
            dict(type='text', content='第一章 通用示例'), dict(type='text', content='1.1 工作原理'),
            dict(type='text', content='这是可读正文，源布局模型未把前两块标为标题。')])])
    source = MinerUAdapter.from_structured_content(payload, book_name='合成教材')
    report = validate_canonical_book(source)
    return dict(scope='synthetic, read-only current-code investigation; not customer-book accuracy',
        synthetic_body_chars=640, chunks=len(rows), full_embedding_input_tokens=full_lengths,
        provider_limit_visible_tokens=visible_lengths,
        retrieval_text_only_change_has_same_index_fingerprint=_fingerprint(rows) == _fingerprint(changed),
        source_membership_check_detects_text_loss=membership_check_detects_text_loss,
        same_source_locator_type_change_changes_block_id=identities[0] != identities[1],
        partial_source_flag_retained='is_full_document' in source.source_metadata,
        numbered_chapters_detected=sum(ch['title'].startswith('第') for ch in canonical_outline(source)),
        ir_valid_despite_unresolved_source_scope=report.valid)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
