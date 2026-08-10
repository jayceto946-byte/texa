"""生成节点相关单元测试"""
from graph.generator import _build_generate_prompt, _has_example_marker
from graph.chapter_subgraph import TEACH_PROMPT
from knowledge.chapter_highlights import ChapterHighlightService, PROMPT_VERSION


def test_build_prompt_includes_longer_context():
    """教材 chunk 不应被截断到 500 字符，否则例题题干会丢失。"""
    long_content = "例4-4 " + "用梯度法求解例4-2无约束优化问题： " * 20 + "$$x_1^2 + 2x_2^2$$" + " 解：第一次迭代..." * 20
    state = {
        "intent": "definition",
        "user_input": "梯度下降法是什么",
        "chapter_contents": {"第四章 无约束优化方法": [long_content]},
        "concept_results": [],
        "history_results": [],
        "knowledge_graph_path": [],
        "teaching_content": "",
    }
    prompt = _build_generate_prompt(state)
    # 修复后：每个 doc 至少保留 1500 字符，因此完整题干和后续解题步骤都应进入 prompt
    assert "例4-2" in prompt
    assert "$$x_1^2 + 2x_2^2$$" in prompt
    assert " 解：第一次迭代..." * 10 in prompt  # 后半部分解题步骤也应保留


def test_build_prompt_includes_multiple_docs():
    """应使用同章节多个 doc，提升例题完整性。"""
    doc1 = "例4-4 题干部分..."
    doc2 = "...题干继续..."
    doc3 = "...解题步骤..."
    state = {
        "intent": "definition",
        "user_input": "梯度下降法是什么",
        "chapter_contents": {"第四章 无约束优化方法": [doc1, doc2, doc3]},
        "concept_results": [],
        "history_results": [],
        "knowledge_graph_path": [],
        "teaching_content": "",
    }
    prompt = _build_generate_prompt(state)
    assert doc1 in prompt
    assert doc2 in prompt
    assert doc3 in prompt


def test_build_prompt_records_bounded_context_budget_without_prompt_body():
    state = {
        "intent": "definition",
        "user_input": "什么是梯度下降法？",
        "chapter_contents": {"第四章": ["梯度下降法是一种迭代优化方法。"]},
        "evidence_items": [],
        "history_results": [],
        "teaching_content": "",
        "planner_trace": {"prompt_chars": 321},
    }

    prompt = _build_generate_prompt(state)
    budget = state["context_budget"]

    assert budget["budget_unit"] == "chars"
    assert budget["assembly_mode"] == "textbook_grounded"
    assert budget["assembled_prompt_chars"] == len(prompt)
    assert budget["evidence_used_chars"] > 0
    assert budget["evidence_included_count"] == 1
    assert budget["planner_prompt_chars"] == 321
    assert "prompt" not in budget


def test_build_prompt_warns_about_incomplete_examples():
    """prompt 应提醒 LLM 不要基于不完整的例题题干编造。"""
    state = {
        "intent": "definition",
        "user_input": "梯度下降法是什么",
        "chapter_contents": {"第四章 无约束优化方法": ["部分内容"]},
        "concept_results": [],
        "history_results": [],
        "knowledge_graph_path": [],
        "teaching_content": "",
    }
    prompt = _build_generate_prompt(state)
    assert "完整" in prompt or "题干" in prompt or "编造" in prompt or "缺失" in prompt


def test_has_example_marker_detects_examples():
    """_has_example_marker 应能识别各种例题标记格式。"""
    assert _has_example_marker("例4-2 用梯度法求解...") is True
    assert _has_example_marker("例 3.1 证明...") is True
    assert _has_example_marker("例5 求函数极小值...") is True
    assert _has_example_marker("定义：梯度下降法是指...") is False
    assert _has_example_marker("定理1（最优性条件）...") is False
    assert _has_example_marker("") is False


def test_prompt_includes_example_check_when_example_found():
    """检索到例题标记时，prompt 应包含例题完整性自检说明。"""
    state = {
        "intent": "definition",
        "user_input": "梯度下降法是什么",
        "chapter_contents": {"第四章": ["例4-2 用梯度法求解无约束优化问题..."]},
        "concept_results": [],
        "history_results": [],
        "knowledge_graph_path": [],
        "teaching_content": "",
    }
    prompt = _build_generate_prompt(state)
    assert "例题完整性自检" in prompt
    assert "完整题干" in prompt


def test_prompt_uses_fallback_when_no_example():
    """未检索到例题标记时，prompt 应使用允许补充例题的 fallback 约束。"""
    state = {
        "intent": "definition",
        "user_input": "梯度下降法是什么",
        "chapter_contents": {"第四章": ["梯度下降法是一种迭代算法..."]},
        "concept_results": [],
        "history_results": [],
        "knowledge_graph_path": [],
        "teaching_content": "",
    }
    prompt = _build_generate_prompt(state)
    assert "补充例题" in prompt


def test_prompt_adds_intuitive_examples_without_losing_problem_spine():
    """陌生概念应有直观例子，但回答仍要围绕以题讲知识点组织。"""
    state = {
        "intent": "definition",
        "user_input": "什么是拉格朗日乘子法",
        "chapter_contents": {"第三章": ["拉格朗日乘子法是处理等式约束优化问题的方法。"]},
        "concept_results": [],
        "history_results": [],
        "knowledge_graph_path": [],
        "teaching_content": "",
    }
    prompt = _build_generate_prompt(state)
    assert "直观例子" in prompt
    assert "生活化类比" in prompt
    assert "以题讲知识点" in prompt
    assert "概念清单" in prompt


def test_teach_prompt_adds_intuitive_examples_and_keeps_examples_primary():
    """章节讲解路径也应避免退化成概念罗列。"""
    assert "直观例子" in TEACH_PROMPT
    assert "生活化类比" in TEACH_PROMPT
    assert "以例题为主线" in TEACH_PROMPT
    assert "不要把讲解写成概念清单" in TEACH_PROMPT


def test_chapter_highlight_prompt_uses_v5_and_textbook_evidence_only(tmp_path):
    """章节重点页必须严格依赖教材证据，不能用模型知识补齐。"""
    service = ChapterHighlightService(progress_path=tmp_path / "progress", mineru_output_path=tmp_path / "mineru")
    source = {
        "book_name": "demo-book",
        "chapter": {"title": "第一章 测试章节", "page": 1, "end_page": 2},
        "scope": {"title": "第一节 测试小节", "type": "section", "page": 1, "end_page": 2},
        "image_refs": [],
    }
    sections = [
        {
            "title": "第一节 测试小节",
            "page": 1,
            "end_page": 2,
            "chunks": [
                {
                    "text": "定义 抽象概念是测试用内容。\n例题 说明这个概念如何用于解题。",
                    "source_ref": "p1",
                    "chunk_id": "chunk_1",
                    "role": "definition",
                    "page": 1,
                    "equations": [],
                }
            ],
        }
    ]

    prompt = service._section_prompt(source, sections)

    assert PROMPT_VERSION == "chapter_highlights_v6_review_friendly"
    assert "不得使用模型记忆补充教材外知识" in prompt
    assert "每条事实必须能在给定材料中找到依据" in prompt
    assert "禁止自拟题" in prompt
    assert "不要输出 chunk_id" in prompt
    assert "控制篇幅" in prompt

def test_general_qa_prompt_uses_subject_without_textbook_context():
    state = {
        "intent": "qa",
        "user_input": "解释一下二次型并举个例子",
        "subject": "\u6570\u5b66",
        "use_textbook_context": False,
        "chapter_contents": {"should-not-appear": ["textbook context"]},
        "concept_results": [],
        "history_results": [],
        "knowledge_graph_path": [],
        "teaching_content": "",
    }

    prompt = _build_generate_prompt(state)

    assert "Current subject: 数学" in prompt
    assert "without textbook RAG context" in prompt
    assert "life-like example" in prompt
    assert "problem-led" in prompt
    assert "step by step" in prompt
    assert "textbook context" not in prompt
