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

    book = _book()
    probes = generate_acceptance_probes(book)
    chunks = ChapterSplitter(chunk_size=300, chunk_overlap=20).split_canonical_book(book)

    class LexicalOnlyStagedStore:
        _map = {}
        _stores = {}
        _broken_aggregates = set()

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
