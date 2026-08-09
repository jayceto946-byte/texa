"""Citation protocol + sources persistence 回归测试。

覆盖：
- TEST 1: 真实 generation prompt 只含证据编号 [E1]，不含 human-readable 教材路径。
- TEST 3: assistant message 持久化 sources，get_conversation 重新加载后仍在（跨 reload 回归）。
- 旧消息（无 sources）仍可正常加载（历史兼容）。
"""
import pytest

from graph.evidence_pack import build_evidence_pack
from graph.generator import _build_generate_prompt
from backend import conversation_memory as memory
from utils.citation_protocol import sanitize_citation_protocol


def _item(chunk_id: str, chapter: str, text: str, *, book_name: str = "传感器短书", section: str = "一、热敏电阻的工作原理") -> dict:
    return {
        "chunk_id": chunk_id,
        "book_name": book_name,
        "book_role": "core",
        "chapter": chapter,
        "section_title": section,
        "page_idx": 5,
        "text": text,
    }


def _state(items: list[dict], question: str, intent: str = "factual_recall") -> dict:
    return {
        "intent": intent,
        "user_input": question,
        "use_textbook_context": True,
        "chapter_contents": {},
        "evidence_items": items,
        "history_results": [],
        "teaching_content": "",
    }


def test_generate_prompt_uses_evidence_ids_not_human_labels():
    items = [
        _item("c1", "第八章 热电式传感器", "热敏电阻具有灵敏度高、响应快等特点。"),
        _item("c2", "第八章 热电式传感器", "热敏电阻的标称阻值是其主要参数。", section="二、热敏电阻的主要参数"),
    ]
    state = _state(items, "热敏电阻的主要特点有哪些？")
    prompt = _build_generate_prompt(state)

    evidence_section = prompt[prompt.find("## Selected textbook evidence"):prompt.find("## 学习者历史")]

    # LLM 输入：证据编号，而非 human-readable 路径
    assert "[E1]" in evidence_section
    assert "[E2]" in evidence_section
    assert "传感器短书" not in evidence_section
    assert "第八章 热电式传感器" not in evidence_section
    # 引用协议指令存在
    assert "[[cite:E1]]" in prompt

    # state 挂载了带 id 的结构化 sources
    sources = state["evidence_sources"]
    assert [src["id"] for src in sources] == ["E1", "E2"]
    assert sources[0]["label"].startswith("传感器短书")


def test_citation_protocol_normalizes_fullwidth_and_folded_tokens():
    text = "甲［[cite:E7]］乙［［cite:E1］］丙[[cite:E1][cite:E7]]"

    cleaned, trace = sanitize_citation_protocol(text, [{"id": "E1"}, {"id": "E7"}])

    assert cleaned == "甲[[cite:E7]]乙[[cite:E1]]丙[[cite:E1]][[cite:E7]]"
    assert trace == {
        "normalized_tokens": 3,
        "invalid_ids_removed": 0,
        "valid_source_count": 2,
    }


def test_citation_protocol_removes_ids_outside_current_evidence_pack():
    cleaned, trace = sanitize_citation_protocol(
        "正文[[cite:E1]]错误[[cite:E99]]",
        [{"id": "E1"}],
    )

    assert cleaned == "正文[[cite:E1]]错误"
    assert trace["invalid_ids_removed"] == 1


def test_append_message_persists_sources_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    conv_id = memory.ensure_conversation_id()

    sources = [
        {"id": "E1", "book_name": "传感器短书", "chapter": "第八章 热电式传感器",
         "section_title": "一、热敏电阻的工作原理", "page_idx": 5,
         "label": "传感器短书·第八章 热电式传感器 / 一、热敏电阻的工作原理 / p.6"},
    ]
    memory.append_message(conv_id, "assistant", "热敏电阻具有灵敏度高、响应快等特点。[[cite:E1]]", sources=sources)
    memory.append_message(conv_id, "user", "那参数呢？")

    messages = memory.get_conversation(conv_id)["messages"]
    assistant = next(m for m in messages if m["role"] == "assistant")
    assert assistant["sources"] == sources
    assert assistant["content"] == "热敏电阻具有灵敏度高、响应快等特点。[[cite:E1]]"


def test_old_message_without_sources_still_loads(monkeypatch, tmp_path):
    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    conv_id = memory.ensure_conversation_id()

    memory.append_message(conv_id, "assistant", "旧消息，没有 sources 字段。")

    messages = memory.get_conversation(conv_id)["messages"]
    assert len(messages) == 1
    assert "sources" not in messages[0]
    assert messages[0]["content"] == "旧消息，没有 sources 字段。"


def test_append_message_persists_linked_concepts_roundtrip(monkeypatch, tmp_path):
    """概念 chips 必须随 assistant 消息持久化，重新加载历史会话时直接读取，不重新抽取。"""
    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    conv_id = memory.ensure_conversation_id()

    concepts = [
        {"name": "霍尔效应", "concept_id": "C1", "confidence": 1.0, "source": "kg_matched", "aliases": []},
        {"name": "压阻效应", "concept_id": "C2", "confidence": 1.0, "source": "kg_matched", "aliases": []},
    ]
    memory.append_message(conv_id, "assistant", "正文。[[cite:E1]]", sources=[{"id": "E1", "label": "L"}], linked_concepts=concepts)

    messages = memory.get_conversation(conv_id)["messages"]
    assistant = next(m for m in messages if m["role"] == "assistant")
    assert assistant["linked_concepts"] == concepts
    # sources 与 concepts 可以同时持久化
    assert assistant["sources"] == [{"id": "E1", "label": "L"}]


def test_update_message_linked_concepts_attaches_to_existing_message(monkeypatch, tmp_path):
    """流式回答：主消息已写入后，done 阶段把概念快照补写回原消息，不新增消息。"""
    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    conv_id = memory.ensure_conversation_id()

    item = memory.append_message(conv_id, "assistant", "正文内容")
    assert item["id"]

    ok = memory.update_message_linked_concepts(conv_id, item["id"], [{"name": "传感器", "confidence": 1.0}])
    assert ok is True

    messages = memory.get_conversation(conv_id)["messages"]
    assert len(messages) == 1  # 不新增消息
    assert messages[0]["linked_concepts"] == [{"name": "传感器", "confidence": 1.0}]

    # 不存在的 message_id -> False，不抛错
    assert memory.update_message_linked_concepts(conv_id, "missing", [{"name": "x"}]) is False
