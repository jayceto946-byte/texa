from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from ingestion.embedding_contract import (EmbeddingInputContract, EmbeddingInputError,
    prepare_embedding_views, validate_embedding_views, onnx_contract)


def contract(limit=64, model='test-v1'):
    return EmbeddingInputContract(dict(backend='fixture', model=model, max_length=limit), lambda text: len(text)+2)


@pytest.mark.parametrize('text', [
    '甲乙丙丁' * 160, '中文😀 a b\n' * 120,
    '$$\\begin{matrix}' + 'x&y\\\\' * 150 + '\\end{matrix}$$',
    '| 参数 | 数值 |\n' + '| R | 123456 |\n' * 100,
    'metadata-' * 120 + '\n正文：完整尾部条件不能消失',
])
def test_dense_windows_cover_every_input_character_and_fit_actual_counter(text):
    c = contract()
    rows = prepare_embedding_views([dict(content=text, retrieval_text=text)], c)
    validate_embedding_views(rows, c)
    covered = set()
    for view in rows[0]['embedding_views']:
        assert c.count(text[view['start']:view['end']]) <= c.max_length
        covered.update(range(view['start'], view['end']))
    assert covered == set(range(len(text)))
    assert rows[0]['content'] == rows[0]['retrieval_text'] == text


@pytest.mark.parametrize('corruption', ['hole', 'input', 'view_hash', 'count', 'model'])
def test_corrupted_views_or_model_contract_cannot_pass(corruption):
    c = contract()
    rows = prepare_embedding_views([dict(content='甲乙丙丁'*100)], c)
    row = rows[0]
    if corruption == 'hole':
        row['embedding_views'].pop()
    elif corruption == 'input':
        row['content'] += '新条件'
    elif corruption == 'view_hash':
        row['embedding_views'][0]['sha256'] = '0'*64
    elif corruption == 'count':
        row['embedding_views'][0]['token_count'] = 1
    else:
        c = contract(model='different-weights')
    with pytest.raises(EmbeddingInputError):
        validate_embedding_views(rows, c)


def test_document_guard_rejects_overflow_before_model_inference():
    from ingestion.onnx_embeddings import TexaONNXEmbeddings
    provider = TexaONNXEmbeddings.__new__(TexaONNXEmbeddings)
    provider._input_contract = contract()
    provider._get_ingestion_provider = lambda: pytest.fail('overflow must not reach inference')
    with pytest.raises(EmbeddingInputError, match='拒绝静默截断'):
        provider.embed_documents(['甲'*100])


def test_lazy_document_session_cannot_load_assets_with_a_different_identity(monkeypatch):
    import threading
    from ingestion import embedding_assets, onnx_embeddings
    provider = onnx_embeddings.TexaONNXEmbeddings.__new__(onnx_embeddings.TexaONNXEmbeddings)
    provider._ingestion_provider = None
    provider._ingestion_lock = threading.Lock()
    provider.asset_dir = 'fixture-assets'
    provider._asset_manifest = {'identity': 'loaded-for-queries'}
    monkeypatch.setattr(embedding_assets, 'validate_asset_dir', lambda *a, **k: {'identity': 'replaced'})
    monkeypatch.setattr(onnx_embeddings, 'ONNXEmbeddingProvider', lambda *a, **k: pytest.fail('must reject before loading'))
    with pytest.raises(EmbeddingInputError, match='运行期间已改变'):
        provider._get_ingestion_provider()


def test_onnx_contract_counts_untruncated_effective_normalizer_and_hashes_assets(tmp_path):
    from tokenizers import Tokenizer, models, normalizers, pre_tokenizers, processors
    from test_embedding_assets import make_assets
    assets = make_assets(tmp_path / 'assets')
    vocab = {'[UNK]': 0, '[CLS]': 1, '[SEP]': 2, '[PAD]': 3, 'a': 4, '甲': 5}
    tokenizer = Tokenizer(models.WordPiece(vocab=vocab, unk_token='[UNK]'))
    tokenizer.normalizer = normalizers.BertNormalizer(lowercase=True)
    tokenizer.pre_tokenizer = pre_tokenizers.BertPreTokenizer()
    tokenizer.post_processor = processors.TemplateProcessing(single='[CLS] $A [SEP]', special_tokens=[('[CLS]', 1), ('[SEP]', 2)])
    tokenizer.save(str(assets / 'tokenizer.json'))
    manifest = json.loads((assets / 'embedding-runtime.json').read_text())
    for item in manifest['expected_files']:
        raw = (assets / item['path']).read_bytes()
        item.update(size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    (assets / 'embedding-runtime.json').write_text(json.dumps(manifest))
    tokenizer.enable_truncation(max_length=512)
    tokenizer.enable_padding()
    c = onnx_contract(assets, tokenizer)
    assert c.count('甲'*600) == 602
    assert c.count('A') == c.count('a') == 3
    assert len(tokenizer.encode('甲'*600).ids) == 512
    c.require_fitting(['甲'*510])
    with pytest.raises(EmbeddingInputError):
        c.require_fitting(['甲'*511])
    rows = prepare_embedding_views([dict(content='甲'*600)], c)
    assert len(rows[0]['embedding_views']) > 1
    (assets / 'model.onnx').write_bytes(b'X' * (assets / 'model.onnx').stat().st_size)
    with pytest.raises(Exception, match='SHA-256'):
        onnx_contract(assets, tokenizer)


def test_windows_hydrate_complete_original_and_versions_bind_actual_inputs(monkeypatch, tmp_path):
    from ingestion import index_pipeline, lexical_index
    from graph.retrieval_node import _doc_to_item
    from test_index_pipeline import FakeStore, _chunk
    monkeypatch.setattr(index_pipeline, 'VECTOR_DB_PATH', tmp_path / 'vector')
    monkeypatch.setattr(lexical_index, 'VECTOR_DB_PATH', tmp_path / 'vector')
    store = FakeStore(tmp_path / 'vector')
    class Embeddings:
        input_contract = contract()
        calls = []
        def embed_documents(self, texts):
            self.input_contract.require_fitting(texts)
            self.calls.extend(texts)
            return [[float(len(t)), 1.] for t in texts]
        def embed_query(self, text):
            return [float(len(text)), 1.]
    store.embeddings = Embeddings()
    text = '完整条件。' * 100 + '尾部特殊条件必须能参与检索。'
    chunks = [_chunk('long', text, retrieval_text='章节：第一章\n正文：' + text)]
    manifest = index_pipeline.build_and_activate_book_index(store, 'demo', [('chapter-one', chunks)], chunks)
    records = list(store._client.get_collection(manifest['aggregate_collection']).rows.values())
    assert manifest['chunk_count'] == 1 and manifest['vector_count'] == len(records) > 1
    assert any('尾部特殊条件' in document for document, _, _ in records)
    assert all(_doc_to_item(SimpleNamespace(page_content=document, metadata=meta), 'chapter-one', 'vector')['text'] == text
               for document, _, meta in records)
    assert len(store.embeddings.calls) == len(set(store.embeddings.calls))  # chapter/aggregate reuse exact views
    saved = json.loads(lexical_index.index_path('demo').read_text())
    validate_embedding_views(saved, store.embeddings.input_contract)
    previous = manifest['index_version']
    changed = deepcopy(chunks)
    changed[0]['retrieval_text'] = '不同上下文\n' + changed[0]['retrieval_text']
    next_manifest = index_pipeline.build_and_activate_book_index(store, 'demo', [('chapter-one', changed)], changed)
    assert next_manifest['index_version'] != previous
    assert index_pipeline.activate_retained_index_version(store, 'demo', previous)['embedding_contract'] == manifest['embedding_contract']
    store.embeddings.input_contract = contract(model='different-weights')
    with pytest.raises(RuntimeError, match='embedding contract'):
        index_pipeline.activate_retained_index_version(store, 'demo', next_manifest['index_version'])


def test_embedding_contract_failure_never_mutates_active_collections(monkeypatch, tmp_path):
    from ingestion import index_pipeline
    from test_index_pipeline import FakeStore, _chunks
    monkeypatch.setattr(index_pipeline, 'VECTOR_DB_PATH', tmp_path / 'vector')
    store = FakeStore(tmp_path / 'vector')
    before = store._map_file.read_bytes()
    store.embeddings = object()
    with pytest.raises(EmbeddingInputError, match='输入长度合同'):
        index_pipeline.build_and_activate_book_index(store, 'demo', [('chapter-one', _chunks())], _chunks())
    assert store._map_file.read_bytes() == before
    assert set(store._client.collections) == {'old'}


def test_reference_contract_accounts_for_prompt_and_lowercase_without_model_calls():
    from ingestion.embedding_contract import torch_contract
    seen = []
    class Tokenizer:
        def get_vocab(self):
            return {'a': 1}
        def encode(self, text, **kwargs):
            seen.append((text, kwargs))
            return list(range(len(text)+2))
    model = SimpleNamespace(tokenizer=Tokenizer(), state_dict=lambda: {}, max_seq_length=64,
        _modules={}, _first_module=lambda: SimpleNamespace(do_lower_case=True),
        prompts={'document': 'PREFIX '}, default_prompt_name='document')
    c = torch_contract(model)
    assert c.count('  AbC  ') == len('prefix   abc') + 2
    assert seen[-1] == ('prefix   abc', dict(add_special_tokens=True, truncation=False))
    model.prompts['document'] = 'different prefix '
    assert torch_contract(model).contract_id != c.contract_id
