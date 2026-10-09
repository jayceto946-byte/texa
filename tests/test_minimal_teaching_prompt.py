import pytest

from langchain_core.messages import HumanMessage, SystemMessage

from graph.generator import _build_generate_messages
from graph.teaching_prompts import (
    MINIMAL_TEACHING_PROMPT,
    REFINED_TEACHING_PROMPT,
    active_teaching_prompt_version,
    teaching_prompt_mode,
)


def _state() -> dict:
    return {
        "intent": "comparison",
        "user_input": "标准差和随机误差有什么联系？",
        "book_name": "误差理论与数据处理",
        "subject": "专业课/误差理论",
        "answer_mode": "textbook_grounded",
        "use_textbook_context": True,
        "evidence_items": [{
            "chunk_id": "std-random",
            "chapter": "第二章",
            "text": "标准差用于评定随机误差的分散程度。",
        }],
        "chapter_contents": {},
        "history_results": [],
        "teaching_content": "",
    }


def test_minimal_prompt_is_opt_in_and_keeps_the_same_bounded_payload(monkeypatch):
    monkeypatch.setenv("TEXA_TEACHING_PROMPT_MODE", "minimal")
    state = _state()

    messages = _build_generate_messages(state)

    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert messages[0].content == MINIMAL_TEACHING_PROMPT
    assert "标准差用于评定随机误差" in messages[1].content
    assert "[[cite:E1]]" in messages[1].content
    assert "例题完整性自检" not in "\n".join(item.content for item in messages)
    assert "Explain the relationship" not in "\n".join(item.content for item in messages)
    assert state["context_budget"]["assembly_mode"] == "textbook_grounded_minimal"
    assert active_teaching_prompt_version().startswith("minimal-teaching-v2")


def test_refined_prompt_is_the_default(monkeypatch):
    monkeypatch.delenv("TEXA_TEACHING_PROMPT_MODE", raising=False)

    messages = _build_generate_messages(_state())

    assert messages[0].content == REFINED_TEACHING_PROMPT
    assert "Explain the relationship" not in messages[0].content
    assert active_teaching_prompt_version().startswith("refined-teaching-v2")


def test_legacy_prompt_remains_available_for_rollback(monkeypatch):
    monkeypatch.setenv("TEXA_TEACHING_PROMPT_MODE", "legacy")

    messages = _build_generate_messages(_state())

    assert "教材事实只能来自本轮选定证据" in messages[0].content
    assert "Explain the relationship" in messages[0].content
    assert active_teaching_prompt_version().startswith("generator-teaching-units-v1")


def test_refined_prompt_keeps_contracts_without_legacy_recipes(monkeypatch):
    monkeypatch.setenv("TEXA_TEACHING_PROMPT_MODE", "refined")
    state = _state()

    messages = _build_generate_messages(state)
    combined = "\n".join(item.content for item in messages)

    assert messages[0].content == REFINED_TEACHING_PROMPT
    assert "标准差用于评定随机误差" in messages[1].content
    assert "[[cite:E1]]" in messages[0].content
    assert "例题完整性自检" not in combined
    assert "Explain the relationship" not in combined
    assert state["context_budget"]["assembly_mode"] == "textbook_grounded_refined"
    assert active_teaching_prompt_version().startswith("refined-teaching-v2")


def test_fine_tune_alias_selects_refined_prompt(monkeypatch):
    monkeypatch.setenv("TEXA_TEACHING_PROMPT_MODE", "fine-tune")
    assert teaching_prompt_mode() == "refined"


@pytest.mark.parametrize("preset", ["minimal", "refined", "legacy"])
@pytest.mark.parametrize("mode", ["subject_general", "global_general"])
def test_explicit_general_mode_allows_model_knowledge_without_textbook_evidence(monkeypatch, preset, mode):
    monkeypatch.setenv("TEXA_TEACHING_PROMPT_MODE", preset)
    state = {**_state(), "answer_mode": mode, "use_textbook_context": False, "evidence_items": []}
    messages = _build_generate_messages(state)
    system = messages[0].content
    assert "不用模型记忆补齐" not in system
    assert "现有证据中的概念和公式" not in system
    assert "模型知识" in system or "model knowledge" in system
    assert "标准差用于评定随机误差" not in messages[1].content
    assert state["context_budget"]["evidence_included_count"] == 0
    if mode == "subject_general":
        assert "专业课/误差理论" in messages[1].content
        assert "学科范围" in system or "subject scope" in system
    else:
        assert "跨学科" in system or "cross-subject" in system
