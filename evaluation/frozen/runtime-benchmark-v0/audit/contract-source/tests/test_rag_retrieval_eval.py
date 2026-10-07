from graph.retrieval_node import _kg_precise_retrieval, _merge_and_rerank


class DummyKG:
    _is_local = True

    def search_concept(self, query, k=5):
        return [
            (90, {"canonical_name": "design variable dimension", "aliases": [], "roles": ["definition"], "occurrence_count": 1}),
            (80, {"canonical_name": "design variable", "aliases": [], "roles": ["definition"], "occurrence_count": 3}),
        ]

    def get_concept_chunks(self, name, window=1, max_hits=3):
        if name == "design variable":
            return [
                {"chapter": "chapter 1", "chunk_id": "toc", "text": "chapter 1 1 chapter 2 2 chapter 3 3", "section_title": "table of contents", "is_direct_hit": False, "role": ""},
                {"chapter": "chapter 1", "chunk_id": "def", "text": "A design variable is an adjustable independent parameter.", "section_title": "2. design variable", "is_direct_hit": True, "role": "definition"},
            ]
        return [{"chapter": "chapter 1", "chunk_id": "long", "text": "Design variable dimension is the number of variables.", "section_title": "dimension", "is_direct_hit": True, "role": "definition"}]


def test_kg_precise_prefers_short_exact_concept_and_filters_toc():
    items, matched = _kg_precise_retrieval(DummyKG(), "what is design variable?", intent="definition")
    assert matched[0] == "design variable"
    assert items[0]["chunk_id"] == "def"
    assert all(item["chunk_id"] != "toc" for item in items)


def test_merge_and_rerank_can_return_final_metadata():
    chapter_contents, debug = _merge_and_rerank(
        [{"chapter": "c", "chunk_id": "a", "text": "A", "is_direct_hit": True, "source": "kg_precise", "role": "definition", "book_name": "Book A"}],
        [{"chapter": "c", "chunk_id": "b", "text": "B", "is_direct_hit": False, "source": "vector", "role": "reference"}],
        include_metadata=True,
    )
    assert chapter_contents == {"c": ["A", "B"]}
    assert [item["chunk_id"] for item in debug] == ["a", "b"]
    assert debug[0]["book_name"] == "Book A"
