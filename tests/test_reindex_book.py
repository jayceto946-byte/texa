from scripts.reindex_book import hydrate_chapters


def test_hydrate_chapters_uses_exact_section_headings_when_bodies_are_empty():
    chapters = [
        {"title": "第一章 基础", "text": ""},
        {"title": "第二章 应用", "text": ""},
    ]
    rows = [
        {"chunk_id": "preface", "section_title": "前言", "content": "preface"},
        {"chunk_id": "c1", "section_title": "第一章 基础", "content": "chapter one"},
        {"chunk_id": "c1b", "section_title": "第一节", "content": "detail"},
        {"chunk_id": "c2", "section_title": "第二章 应用", "content": "chapter two"},
    ]

    hydrated, unmatched = hydrate_chapters(chapters, rows)

    assert unmatched == 0
    assert [item["title"] for item in hydrated] == ["第一章 基础", "第二章 应用"]
    assert [row["chunk_id"] for row in hydrated[0]["chunks"]] == ["preface", "c1", "c1b"]
    assert [row["chunk_id"] for row in hydrated[1]["chunks"]] == ["c2"]


def test_hydrate_chapters_does_not_guess_when_a_heading_is_missing():
    chapters = [{"title": "第一章", "text": ""}, {"title": "第二章", "text": ""}]
    rows = [{"chunk_id": "c1", "section_title": "第一章", "content": "body"}]

    _hydrated, unmatched = hydrate_chapters(chapters, rows)

    assert unmatched == 1