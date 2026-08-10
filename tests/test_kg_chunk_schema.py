import json


def test_knowledge_graph_reads_current_content_chunk_schema(monkeypatch, tmp_path):
    from knowledge.knowledge_graph import KnowledgeGraph

    book = "schema-demo"
    (tmp_path / f"{book}_knowledge_graph.json").write_text(json.dumps({
        "meta": {},
        "concepts": [{"concept_id": "c1", "canonical_name": "定义", "aliases": [], "roles": ["definition"]}],
        "formulas": [],
        "occurrences": [{"concept_id": "c1", "chunk_id": "chunk-1", "role": "definition"}],
        "relations": [],
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / f"{book}_middle_chunks.json").write_text(json.dumps([{
        "chunk_id": "chunk-1",
        "content": "当前摄取格式中的教材正文",
        "section_title": "第一章",
        "page_idx": 0,
    }], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(KnowledgeGraph, "_resolve_local_dir", staticmethod(lambda _book: tmp_path))

    graph = KnowledgeGraph(book)

    assert graph.get_chunk_text("chunk-1") == "当前摄取格式中的教材正文"
    assert graph.get_concept_chunks("定义", window=0)[0]["text"] == "当前摄取格式中的教材正文"
