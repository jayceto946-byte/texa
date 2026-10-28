from langchain_core.documents import Document

from test_vector_store_fallback import _store
from test_embedding_input_contract import contract
import pytest


class Windows:
    def __init__(self):
        self.calls = []
        self.docs = [Document(page_content=f'window-{i}', metadata=dict(book_name='book', index_version='v1',
            chapter='chapter-0', chunk_id='source-a', raw_content='A 的完整公式与条件')) for i in range(4)]
        self.docs.append(Document(page_content='different-source', metadata=dict(book_name='book', index_version='v1',
            chapter='chapter-0', chunk_id='source-b', raw_content='B 的完整来源')))

    def similarity_search_by_vector_with_relevance_scores(self, _query, **kwargs):
        self.calls.append(kwargs['k'])
        return [(doc, float(i)) for i, doc in enumerate(self.docs[:kwargs['k']])]

    def similarity_search(self, query, **kwargs):
        return [doc for doc, _ in self.similarity_search_by_vector_with_relevance_scores(query, **kwargs)]


def setup(aggregate):
    store = _store(chapter_count=1, aggregate=aggregate)
    backends = []
    for name, entry in store._map.items():
        entry.update(chunk_count=2, vector_count=5)
        backend = Windows()
        store._stores[store._store_key(entry['chapter'], 'book')] = backend
        backends.append(backend)
    return store, backends


def test_windows_do_not_consume_distinct_chapter_source_slots():
    for aggregate in (False, True):
        store, backends = setup(aggregate)
        result = store.search_all('query', book_name='book', k=2, top_n=1)
        assert result.status == 'ok'
        assert [d.metadata['chunk_id'] for d in result.items['chapter-0']] == ['source-a', 'source-b']
        if not aggregate:
            assert backends[0].calls == [8]
            assert [d.metadata['chunk_id'] for d in store.search_chapter('chapter-0', 'query', k=2, book_name='book').items] == ['source-a', 'source-b']


def test_new_index_model_mismatch_is_a_failure_not_a_vector_hit():
    store, backends = setup(False)
    store.embeddings.input_contract = contract()
    store._map['c0']['embedding_contract_id'] = 'wrong-runtime'
    result = store.search_all('query', book_name='book', k=2, top_n=1)
    assert result.status == 'failed' and not result.items
    assert backends[0].calls == []
    assert '模型身份不一致' in result.failures[0].message


def test_legacy_direct_writer_rejects_overflow_before_deleting_a_collection():
    from ingestion.embedding_contract import EmbeddingInputError
    store, backends = setup(False)
    store.embeddings.input_contract = contract()
    store._delete_collection_if_exists = lambda _: pytest.fail('must not delete a collection before input validation')
    before = dict(store._stores)
    with pytest.raises(EmbeddingInputError, match='拒绝静默截断'):
        store.build_chapter_store('chapter-0', [dict(content='甲'*100)], book_name='book')
    assert store._stores == before
