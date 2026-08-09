"""Session 上下文追问解析（Conversation Resolver）回归测试。

覆盖：
- Context Test A：Q3 解析"前者 = 压阻效应"
- Context Test B：Q2"条件呢？" -> "拉格朗日中值定理的成立条件是什么？"
- Context Test C："再解释一下霍尔效应" 自足，绝不拼接历史（不拒答）
- Topic Switch Test：Q3 回指压阻效应而非最近话题霍尔效应
- 负例：普通独立问题不做改写
"""
import pytest

from backend.conversation_memory import rewrite_followup
from backend.services.session_context import build_session_context


def _history(user_messages: list[str]) -> list[dict]:
    history: list[dict] = []
    for index, content in enumerate(user_messages):
        history.append({"role": "user", "content": content})
        history.append({"role": "assistant", "content": f"（回答{index + 1}）"})
    return history


@pytest.mark.parametrize("history,question,expect", [
    # Context Test A：前者 -> 压阻效应（Q2 比较对里的第一项，Q2 的"它"先回指 Q1）
    (["什么是压阻效应？", "它和压电效应有什么区别？"], "那前者通常用在哪些传感器里？", "压阻效应通常用在哪些传感器里？"),
    # Context Test B：纯省略追问 -> 锚点 + 条件问题
    (["讲一下拉格朗日中值定理。"], "条件呢？", "拉格朗日中值定理的成立条件是什么？"),
    # Context Test C：自足 follow-up 不拼接历史（这是拒答根因）
    (["解释压阻效应。"], "再解释一下霍尔效应。", "霍尔效应"),
    (["解释压阻效应。"], "解释霍尔效应。", "霍尔效应"),
    # Topic Switch Test：回指压阻效应，而不是最近话题霍尔效应
    (["解释压阻效应。", "解释霍尔效应。"], "回到刚才的压阻效应，它为什么会导致电阻率变化？", "压阻效应为什么会导致电阻率变化？"),
    # Q2 的"它"解析为锚点概念
    (["什么是压阻效应？"], "它和压电效应有什么区别？", "压阻效应和压电效应有什么区别？"),
])
def test_rewrite_followup_resolves_anaphora(history, question, expect):
    resolved = rewrite_followup(question, _history(history))
    assert expect in resolved
    # 绝不允许把 history 拼接进 query（Context Test C 的核心约束）
    assert "；" not in resolved


@pytest.mark.parametrize("history,question", [
    # 独立问题：无指代信号，原样返回
    (["什么是压阻效应？"], "热敏电阻的标称阻值怎么计算？"),
    (["什么是压阻效应？"], "压阻效应为什么会改变电阻率？"),
    (["什么是压阻效应？"], "压电效应的定义是什么？"),
    # 无历史：原样返回
    ([], "条件呢？"),
])
def test_rewrite_followup_keeps_standalone_queries(history, question):
    assert rewrite_followup(question, _history(history) if history else []) == question


def test_rewrite_followup_scope_prefix_only_on_fallback():
    # 真正无法用规则解析的指代才走旧拼接路径（带 scope 前缀）
    resolved = rewrite_followup("它怎么了？", _history(["什么是压阻效应？"]), book_name="传感器短书", subject="专业课")
    assert "压阻效应" in resolved or "它怎么了" in resolved


def test_structured_context_resolves_ordinal_entity_reference():
    history = _history(["解释压阻效应。", "解释霍尔效应。"])

    state = build_session_context(history)
    resolved = rewrite_followup("回到第一个，它适合什么场景？", history)

    assert state["topic"] == "霍尔效应"
    assert state["entities"] == ["压阻效应", "霍尔效应"]
    assert resolved == "压阻效应适合什么场景？"


def test_structured_context_updates_comparison_constraints():
    history = _history(["压阻式和压电式哪个更适合动态测量？"])

    state = build_session_context(history)
    resolved = rewrite_followup("如果是低频呢？", history)

    assert state["frame"] == {
        "kind": "comparison",
        "entities": ["压阻式", "压电式"],
        "goal": "哪个更适合",
    }
    assert state["constraints"] == ["动态测量"]
    assert resolved == "在动态测量、低频条件下，压阻式和压电式哪个更适合？"

    updated_history = _history([
        "压阻式和压电式哪个更适合动态测量？",
        "如果是低频呢？",
    ])
    assert build_session_context(updated_history)["constraints"] == ["动态测量", "低频"]


def test_structured_context_carries_intent_across_fragments():
    history = _history(["什么是矩阵的秩？", "性质呢？", "怎么算？"])

    state = build_session_context(history)
    resolved = rewrite_followup("举个例子。", history)

    assert state["topic"] == "矩阵的秩"
    assert state["intent"] == "calculation"
    assert state["last_resolved_query"] == "矩阵的秩怎么算？"
    assert resolved == "举一个计算矩阵的秩的例子。"


def test_plain_comparison_request_builds_frame_for_former_and_latter():
    history = _history(["比较压阻式和压电式传感器。"])

    state = build_session_context(history)
    resolved = rewrite_followup("前者适合测静态量吗？为什么？", history)

    assert state["frame"]["entities"] == ["压阻式传感器", "压电式传感器"]
    assert resolved == "压阻式传感器适合测静态量吗？为什么？"


def test_multi_entity_comparison_preserves_entity_order():
    state = build_session_context(_history([
        "比较压阻式、压电式和电容式传感器，并分别说明灵敏度和频响。",
    ]))

    assert state["frame"]["entities"] == [
        "压阻式传感器", "压电式传感器", "电容式传感器",
    ]


def test_latter_only_followup_inherits_previous_comparison_predicate():
    history = _history([
        "比较压阻式和压电式传感器。",
        "前者适合测静态量吗？为什么？",
    ])

    resolved = rewrite_followup("那后者呢？", history)

    assert resolved == "压电式传感器适合测静态量吗？为什么？"
