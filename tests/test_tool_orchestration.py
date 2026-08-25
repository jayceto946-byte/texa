from backend.services.tool_orchestration import (
    ToolOrchestrationRequest,
    execute_read_only_tools,
    select_tool_calls,
)
from backend.tools.math_tools import parse_restricted_expression
from backend.tools import learning_tools
from backend.tools.registry import ToolContext, get_tool_registry
from evaluation.tool_calling_eval import evaluate
from graph.generator import _build_generate_prompt
from graph.retrieval_node import retrieve_node
from backend.api import chat as chat_api


def test_registry_exposes_machine_readable_tool_contracts():
    specs = {item["name"]: item for item in get_tool_registry().list_tools()}
    symbolic = specs["symbolic_math"]

    assert symbolic["parameters"]["type"] == "object"
    assert "symbolic_algebra" in symbolic["capabilities"]
    assert symbolic["risk_level"] == "low"
    assert symbolic["timeout_seconds"] == 5.0
    assert symbolic["provenance"].startswith("sympy-")


def test_restricted_math_parser_rejects_python_execution_surface():
    for expression in (
        "__import__('os')",
        "x.__class__",
        "open('secret')",
        "[x for x in range(3)]",
    ):
        try:
            parse_restricted_expression(expression)
        except ValueError:
            pass
        else:  # pragma: no cover - explicit security assertion
            raise AssertionError(f"unsafe expression accepted: {expression}")


def test_math_orchestration_runs_postcondition_verifier():
    result = execute_read_only_tools(ToolOrchestrationRequest(
        question="解方程 x^2-5*x+6=0",
    ))

    assert [item["tool"] for item in result["tool_outputs"]] == [
        "symbolic_math", "verify_math_result",
    ]
    assert result["tool_outputs"][0]["result"]["data"]["result"]["exact"] == ["2", "3"]
    assert result["tool_outputs"][1]["result"]["verification"]["passed"] is True
    assert result["tool_context_pack"]["sufficient"] is True


def test_main_router_keeps_textbook_retrieval_in_production_graph():
    calls = select_tool_calls(ToolOrchestrationRequest(
        question="教材中给出了哪些粗大误差判别方法？",
        book_name="误差理论与数据处理",
        subject="专业课",
        include_textbook_tool=False,
    ))
    assert calls == []


def test_restricted_math_does_not_trigger_cross_subject_guess(monkeypatch):
    monkeypatch.setattr(
        chat_api,
        "suggest_subject_scope",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not guess")),
    )

    assert chat_api._safe_subject_suggestion(
        "计算 2^10 + 3*7", "数学/线代", "",
    ) is None


def test_state_tool_context_skips_unrelated_textbook_retrieval():
    result = retrieve_node({
        "tool_context_pack": {"skip_textbook_retrieval": True},
        "user_input": "我最近的学习进度",
    })

    assert result["retrieval_status"] == "tool_context"
    assert result["evidence_support"]["reason"] == "authoritative_local_tool_context"


def test_textbook_tool_returns_final_production_evidence_pack(monkeypatch):
    import graph.retrieval_node as retrieval_module

    monkeypatch.setattr(retrieval_module, "retrieve_node", lambda _state: {
        "evidence_items": [{
            "chunk_id": "chunk-1", "book_name": "误差理论与数据处理",
            "chapter": "第一章", "section_title": "随机误差",
            "section_path": ["第一章", "随机误差"], "page_idx": 4,
            "role": "definition", "text": "随机误差在相同条件下重复测量时具有随机性。",
        }],
        "chapter_contents": {},
        "evidence_support": {"status": "supported", "reason": "direct"},
        "retrieval_status": "ok", "retrieval_error": "",
    })

    result = learning_tools.search_textbook(
        ToolContext(book_name="误差理论与数据处理", subject="专业课"),
        {"query": "什么是随机误差？", "limit": 3},
    )

    assert result.success is True
    assert result.data["snippets"][0]["id"] == "E1"
    assert result.data["snippets"][0]["chunk_id"] == "chunk-1"
    assert result.evidence[0]["label"].startswith("误差理论与数据处理")


def test_generator_treats_tool_context_as_bounded_quoted_data():
    prompt = _build_generate_prompt({
        "intent": "calculation",
        "user_input": "计算 2^10",
        "answer_mode": "global_general",
        "use_textbook_context": False,
        "history_results": [],
        "conversation_context_seed": {},
        "conversation_context_pack": {},
        "tool_context_pack": {
            "text": '[{"tool":"symbolic_math","data":{"result":{"exact":"1024"}}}]',
        },
    })

    assert "symbolic_math" in prompt
    assert "1024" in prompt
    assert "never claim a pending action was executed" in prompt


def test_tool_calling_offline_release_gate():
    report = evaluate()

    assert report["metrics"]["case_count"] == 40
    assert report["release_pass"] is True
    assert report["metrics"]["route_accuracy"] >= 0.90
    assert report["metrics"]["math_verification"] == 1.0
