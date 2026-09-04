import json

from ingestion.acceptance_probes import generate_acceptance_probes, persist_acceptance_probes
from ingestion.document_ir import CanonicalBook, DocumentBlock


def _book():
    return CanonicalBook(
        book_name="结构教材",
        source_kind="mineru",
        parser_version="test-v1",
        blocks=[
            DocumentBlock(
                block_id="formula-1", block_type="formula",
                text="标准差公式：$$\\sigma = \\sqrt{\\sum v_i^2/(n-1)}$$",
                equations=["\\sigma = \\sqrt{\\sum v_i^2/(n-1)}"],
                section_path=["第二章", "标准差"], source_kind="mineru",
            ),
            DocumentBlock(
                block_id="list-1", block_type="paragraph",
                text="误差分为：\n1. 系统误差\n2. 随机误差\n3. 粗大误差",
                section_path=["第一章", "误差分类"], source_kind="mineru",
            ),
            DocumentBlock(
                block_id="example-1", block_type="example",
                text="例题 2-1 已知五次测量值，求算术平均值。\n解：先求五次测量值之和。",
                section_path=["第二章", "算术平均值"], source_kind="mineru",
            ),
            DocumentBlock(
                block_id="table-1", block_type="table",
                text="表2-1 测量数据\n| 测次 | 结果 |\n|---|---|\n| 1 | 10.2 |",
                section_path=["第二章", "测量数据"], source_kind="mineru",
                table_title="表2-1 测量数据", table_header=["测次", "结果"],
                table_rows=[["1", "10.2"]],
            ),
        ],
    )


def test_generator_builds_four_deterministic_structural_probe_types():
    first = generate_acceptance_probes(_book())
    second = generate_acceptance_probes(_book())

    assert first == second
    assert {case["specialty"] for case in first["cases"]} == {"formula", "list", "example", "table"}
    assert first["inventory"] == {"formula": 1, "list": 1, "example": 1, "table": 1}
    assert all(case["status"] == "generated_structural" for case in first["cases"])
    assert all(case["provenance"]["human_approved"] is False for case in first["cases"])
    assert all(case["required_points"] for case in first["cases"])


def test_generated_probes_and_inventory_report_are_persisted(tmp_path):
    result = persist_acceptance_probes(_book(), progress_root=tmp_path)

    cases_path = tmp_path / "结构教材" / "acceptance_probes.generated.jsonl"
    report_path = tmp_path / "结构教材" / "acceptance_probes.generated.report.json"
    rows = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines()]
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert len(rows) == 4
    assert report["inventory"] == result["inventory"]
    assert "cases" not in report
    assert report["limitations"]


def test_generated_probes_pass_the_real_staged_lexical_retrieval_path():
    from ingestion.chapter_splitter import ChapterSplitter
    from ingestion.index_pipeline import _validate_staged_production_retrieval
    from ingestion.vector_store import RetrievalOutcome

    book = _book()
    probes = generate_acceptance_probes(book)
    chunks = ChapterSplitter(chunk_size=300, chunk_overlap=20).split_canonical_book(book)

    class LexicalOnlyStagedStore:
        _map = {}
        _stores = {}
        _broken_aggregates = set()

        def search_chapter(self, *_args, **_kwargs):
            return RetrievalOutcome(items=[])

        def search_all(self, *_args, **_kwargs):
            return RetrievalOutcome(items={})

    summary = _validate_staged_production_retrieval(
        LexicalOnlyStagedStore(),
        book.book_name,
        {"staged": {"book_name": book.book_name, "kind": "book_aggregate", "active": True}},
        chunks,
        acceptance_probes=probes["cases"],
        specialty_inventory=probes["inventory"],
    )

    assert summary["generated_probe_cases"] == 4
    assert all(gate["passed"] for gate in summary["specialty_gates"].values())


def _table(block_id, text, *, title="", section="表格节"):
    return DocumentBlock(
        block_id=block_id,
        block_type="table",
        text=text,
        section_path=["第一章", section],
        source_kind="mineru",
        table_title=title,
        table_header=["字段", "数据"],
        table_rows=[[block_id, "1"]],
    )


def _paragraph(block_id, text, *, section="表格节"):
    return DocumentBlock(
        block_id=block_id,
        block_type="paragraph",
        text=text,
        section_path=["第一章", section],
        source_kind="mineru",
    )


def _table_book(blocks):
    return CanonicalBook(
        book_name="表格教材",
        source_kind="mineru",
        parser_version="test-v1",
        blocks=blocks,
    )


def test_captioned_table_probe_uses_real_caption_and_source_points():
    table = _table(
        "table-captioned",
        "表1-1 参数表\n| 字段 | 数据 |\n|---|---|\n| table-captioned | 1 |",
        title="表1-1 参数表",
    )

    result = generate_acceptance_probes(_table_book([table]))
    case = next(case for case in result["cases"] if case["specialty"] == "table")

    assert case["question"].startswith("表1-1 参数表")
    assert case["provenance"]["target_grounding"] == "caption"
    assert case["hard_gate"] is True
    assert all(point in table.text for point in case["required_points"])


def test_untitled_single_table_probe_is_grounded_by_its_section():
    table = _table(
        "table-only",
        "| 字段 | 数据 |\n|---|---|\n| table-only | 1 |",
        section="唯一表格节",
    )

    result = generate_acceptance_probes(_table_book([table]))
    case = next(case for case in result["cases"] if case["specialty"] == "table")

    assert case["question"] == "唯一表格节中的表格列出了哪些字段或数据？"
    assert case["provenance"]["target_grounding"] == "single_table_section"
    assert result["manual"]["table"] == 0


def test_untitled_multi_table_probes_require_unique_adjacent_source_text():
    first_context = _paragraph("context-1", "（1）构造初始单纯形表如下：")
    first = _table("table-1", "| 字段 | 数据 |\n|---|---|\n| table-1 | 1 |")
    second_context = _paragraph("context-2", "（2）经变换得到下列检验表：")
    second = _table("table-2", "| 字段 | 数据 |\n|---|---|\n| table-2 | 1 |")

    result = generate_acceptance_probes(_table_book([first_context, first, second_context, second]))
    cases = [case for case in result["cases"] if case["specialty"] == "table"]

    assert len(cases) == 2
    assert len({case["question"] for case in cases}) == 2
    assert {case["provenance"]["block_id"] for case in cases} == {"table-1", "table-2"}
    assert all(case["provenance"]["target_grounding"] == "adjacent_source_text" for case in cases)
    assert all(len(case["provenance"]["source_block_ids"]) == 2 for case in cases)
    tables = {"table-1": first, "table-2": second}
    assert all(
        point in tables[case["provenance"]["block_id"]].text
        for case in cases for point in case["required_points"]
    )


def test_ambiguous_untitled_multi_table_targets_are_manual_and_not_hard_gate():
    first_context = _paragraph("context-1", "构造单纯形表如下：")
    first = _table("table-1", "| 字段 | 数据 |\n|---|---|\n| table-1 | 1 |")
    second_context = _paragraph("context-2", "构造单纯形表如下：")
    second = _table("table-2", "| 字段 | 数据 |\n|---|---|\n| table-2 | 1 |")

    result = generate_acceptance_probes(_table_book([first_context, first, second_context, second]))
    cases = [case for case in result["cases"] if case["specialty"] == "table"]

    assert cases == []
    assert result["inventory"]["table"] == 0
    assert result["source_inventory"]["table"] == 2
    assert result["manual"]["table"] == 2
    assert all(item["status"] == "manual_review" for item in result["manual_review"])
    assert all(item["hard_gate"] is False for item in result["manual_review"])
    assert all(item["reason"] == "ambiguous_untitled_table_in_multi_table_section" for item in result["manual_review"])
    assert all(item["source_evidence"]["table_text"] for item in result["manual_review"])
    assert all(item["source_evidence"]["adjacent_context"] for item in result["manual_review"])
