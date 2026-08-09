"""Deterministic structured session context for follow-up resolution."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SessionContextState:
    topic: str = ""
    entities: list[str] = field(default_factory=list)
    frame: dict[str, Any] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    intent: str = "qa"
    last_resolved_query: str = ""


_ANAPHORA_WORDS = (
    "它们", "这些", "那些", "上述", "前者", "后者", "这个", "那个",
    "它", "其", "上面", "刚才", "前面", "这里", "这一步",
)
_TOPIC_SWITCH_LEADINS = (
    "回到刚才的", "回到前面的", "刚才说的", "刚才提到的", "前面说的",
    "上面说的", "回到刚才", "回到前面", "刚才的", "还是", "继续讲",
    "继续说", "再说一下",
)
_INTENT_PATTERNS = (
    ("example", r"举(?:个|一?个)?例|例子|例题"),
    ("calculation", r"怎么算|如何计算|怎么计算|计算方法|求法|求解"),
    ("derivation", r"推导|怎么推出|如何推出"),
    ("proof", r"证明|如何证|怎么证"),
    ("comparison", r"比较|对比|区别|异同|哪个更|哪一个更"),
    ("definition", r"定义|什么是|何谓|是什么意思"),
    ("property", r"性质|特征|特点"),
    ("condition", r"条件|前提"),
    ("formula", r"公式|表达式"),
    ("principle", r"原理|机理"),
    ("application", r"应用|用途|用在哪|适合什么场景"),
    ("reason", r"原因|为什么"),
    ("explanation", r"解释|说明|介绍|讲一下|讲讲"),
)
_INTENT_TASK_WORDS = {
    "定义", "性质", "特征", "特点", "条件", "前提", "公式", "表达式", "原理",
    "机理", "应用", "用途", "作用", "原因", "推导", "证明", "计算", "怎么算",
    "例子", "举例", "例题", "解释", "说明", "比较", "对比",
}
_ORDINAL_VALUES = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}
_SHARED_ENTITY_SUFFIXES = (
    "传感器", "效应", "定理", "算法", "模型", "电路", "方法", "公式",
)


def _infer_intent(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    for intent, pattern in _INTENT_PATTERNS:
        if re.search(pattern, compact):
            return intent
    return "qa"


def _strip_internal_references(text: str) -> str:
    text = re.sub(r"\s*/\s*[a-f0-9]{12,64}(?=\s*\])", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _strip_topic_switch(text: str) -> str:
    result = text.strip()
    for lead in _TOPIC_SWITCH_LEADINS:
        if result.startswith(lead):
            return result[len(lead):].lstrip(" 　，,")
    return result


def _clean_query(question: str) -> str:
    result = _strip_topic_switch(question)
    result = re.sub(r"^再(?=解释|说明|介绍|讲|分析|求|计算|推导|证明)", "", result)
    return result.strip()


def _has_anaphora(question: str) -> bool:
    compact = re.sub(r"\s+", "", question)
    return any(word in compact for word in _ANAPHORA_WORDS)


def _extract_topic(text: str) -> str:
    """Extract a standalone entity/topic; task-only fragments return empty."""
    cleaned = _clean_query(text)
    if _has_anaphora(cleaned):
        return ""
    try:
        from knowledge.query_concepts import _strip_leading_noise, _strip_trailing_noise, is_task_word

        cleaned = _strip_leading_noise(cleaned)
    except Exception:
        def is_task_word(value: str) -> bool:
            return value in _INTENT_TASK_WORDS
    cleaned = re.split(
        r"(?:为什么|怎么样|怎么|如何|有什么|有哪些|是否|是不是|能否|通常|一般|"
        r"适合|用于|用在|会不会|会导致|的定义|的性质|的特征|的特点|的条件|"
        r"的公式|的原理|的应用)",
        cleaned,
        maxsplit=1,
    )[0]
    try:
        cleaned = _strip_trailing_noise(cleaned)
    except NameError:
        pass
    cleaned = cleaned.strip(" 　 、，,；:()（）\"'“”呢吗吧啊呀？?。！!")
    if (
        not cleaned
        or len(cleaned) < 2
        or len(cleaned) > 40
        or cleaned in _INTENT_TASK_WORDS
        or is_task_word(cleaned)
    ):
        return ""
    return cleaned


def _append_entity(state: SessionContextState, entity: str) -> None:
    entity = entity.strip()
    if not entity:
        return
    if entity in state.entities:
        return
    state.entities.append(entity)
    if len(state.entities) > 12:
        del state.entities[:-12]


def _expand_shared_entity_suffixes(entities: list[str]) -> list[str]:
    """Restore an omitted shared noun suffix in Chinese coordinate phrases.

    For example, ``压阻式和压电式传感器`` denotes two sensors, not the
    unrelated pair ``压阻式`` and ``压电式传感器``.
    """
    cleaned = [value.strip("，,、。？?!！") for value in entities if value.strip("，,、。？?!！")]
    if len(cleaned) < 2:
        return cleaned
    shared_suffix = next(
        (suffix for suffix in _SHARED_ENTITY_SUFFIXES if cleaned[-1].endswith(suffix)),
        "",
    )
    if not shared_suffix:
        return cleaned
    return [
        value if value.endswith(shared_suffix) else f"{value}{shared_suffix}"
        for value in cleaned
    ]


def _comparison_frame(text: str, state: SessionContextState) -> dict[str, Any] | None:
    compact = re.sub(r"\s+", "", _clean_query(text)).strip("。？?!！")
    explicit = re.match(r"^(?:请)?(?:比较|对比)(?:一下)?(?P<body>.+)$", compact)
    if explicit:
        body = explicit.group("body")
        # A trailing instruction describes comparison dimensions, not another entity.
        entity_clause = re.split(
            r"(?:，|,)?(?:并|再)?(?:分别)?(?:说明|分析|比较|讨论)",
            body,
            maxsplit=1,
        )[0]
        parts = re.split(r"[、]|(?:和|与|跟|同)", entity_clause)
        entities = _expand_shared_entity_suffixes(parts)
        if 2 <= len(entities) <= 6:
            return {
                "kind": "comparison",
                "entities": entities,
                "goal": "有什么区别",
                "constraints": [],
            }

    match = re.search(
        r"(?P<a>[^，,。？?；;]{1,28}?)(?:和|与|跟|同)"
        r"(?P<b>[^，,。？?；;]{2,28}?)"
        r"(?P<tail>有什么区别|有何区别|有什么联系|有何联系|有什么关系|有何关系|"
        r"有什么异同|有何异同|哪个.*|哪一个.*|谁.*|孰.*|的区别.*|的联系.*|的关系.*)$",
        compact,
    )
    if not match:
        return None
    a = match.group("a").strip("，,、")
    b = match.group("b").strip("，,、")
    if a in _ANAPHORA_WORDS and state.topic:
        a = state.topic
    if b in _ANAPHORA_WORDS and state.topic:
        b = state.topic
    if not a or not b:
        return None
    a, b = _expand_shared_entity_suffixes([a, b])
    tail = match.group("tail")
    goal = tail
    constraints: list[str] = []
    fit = re.match(r"(?:哪个|哪一个)更适合(?P<constraint>.*)", tail)
    if fit:
        goal = "哪个更适合"
        constraint = fit.group("constraint").strip("，,、。？?!！")
        if constraint:
            constraints.append(constraint)
    elif "区别" in tail or "异同" in tail:
        goal = "有什么区别"
    elif "联系" in tail:
        goal = "有什么联系"
    elif "关系" in tail:
        goal = "有什么关系"
    return {"kind": "comparison", "entities": [a, b], "goal": goal, "constraints": constraints}


def _render_intent(topic: str, intent: str, previous_intent: str) -> str:
    if intent == "example":
        if previous_intent == "calculation":
            return f"举一个计算{topic}的例子。"
        return f"举一个关于{topic}的例子。"
    templates = {
        "definition": "{topic}的定义是什么？",
        "property": "{topic}有什么性质？",
        "condition": "{topic}的成立条件是什么？",
        "formula": "{topic}的公式是什么？",
        "principle": "{topic}的原理是什么？",
        "application": "{topic}有哪些应用？",
        "reason": "{topic}的原因是什么？",
        "calculation": "{topic}怎么算？",
        "derivation": "{topic}是怎么推导的？",
        "proof": "{topic}如何证明？",
        "explanation": "解释{topic}。",
    }
    template = templates.get(intent)
    return template.format(topic=topic) if template else ""


def _is_intent_fragment(text: str, intent: str) -> bool:
    compact = re.sub(r"\s+", "", text).strip("。？?!！呢吗吧啊呀")
    compact = re.sub(r"^(?:那|那么|再|继续|请)(?:说说|讲讲|讲一下|解释一下)?", "", compact)
    if compact in _INTENT_TASK_WORDS:
        return True
    if intent == "calculation" and len(compact) <= 8:
        return True
    if intent == "example" and len(compact) <= 10:
        return True
    return False


def _ordinal_target(question: str, state: SessionContextState) -> tuple[str, str] | None:
    match = re.search(r"第(?P<value>[一二三四五六七八九十\d]+)个", question)
    if not match:
        return None
    raw_value = match.group("value")
    try:
        ordinal = int(raw_value)
    except ValueError:
        ordinal = _ORDINAL_VALUES.get(raw_value, 0)
    if ordinal <= 0 or ordinal > len(state.entities):
        return None
    target = state.entities[ordinal - 1]
    remainder = re.sub(
        r"^(?:那|那么)?(?:回到|再看|说回)?第[一二三四五六七八九十\d]+个[，,]?",
        "",
        question,
    ).strip()
    return target, remainder


def _replace_anaphora(question: str, target: str) -> str:
    stripped = _strip_topic_switch(question)
    direct = re.search(r"([\u4e00-\u9fffA-Za-z0-9]{2,24})[，,]\s*(?:它|其|这个|那个)", stripped)
    explicit_target = direct.group(1) if direct else ""
    replacement = explicit_target or target
    if not replacement:
        return question
    result = stripped
    for word in sorted(_ANAPHORA_WORDS, key=len, reverse=True):
        if word not in ("前者", "后者"):
            result = result.replace(word, replacement)
    if direct:
        result = re.sub(
            rf"{re.escape(explicit_target)}[，,]\s*{re.escape(explicit_target)}",
            explicit_target,
            result,
        )
    return _clean_query(result)


def _condition_update(question: str, state: SessionContextState) -> str:
    if state.frame.get("kind") != "comparison":
        return ""
    compact = re.sub(r"\s+", "", question).strip("。？?!！")
    match = re.fullmatch(
        r"(?:那|那么)?(?:如果|若|假如)(?:考虑|是|在)?(?P<constraint>.+?)(?:的话|呢)?",
        compact,
    )
    if not match:
        return ""
    constraint = match.group("constraint").strip("，,、呢")
    if not constraint:
        return ""
    constraints = list(state.constraints)
    if constraint not in constraints:
        constraints.append(constraint)
    state.constraints = constraints
    entities = list(state.frame.get("entities") or [])
    if len(entities) != 2:
        return ""
    goal = str(state.frame.get("goal") or "有什么区别")
    return f"在{'、'.join(constraints)}条件下，{entities[0]}和{entities[1]}{goal}？"


def _resolve_with_state(question: str, state: SessionContextState) -> str:
    question = question.strip()
    ordinal = _ordinal_target(question, state)
    if ordinal:
        target, remainder = ordinal
        return _replace_anaphora(remainder or target, target)

    if "前者" in question or "后者" in question:
        pair = list(state.frame.get("entities") or [])
        if len(pair) < 2:
            pair = state.entities[-2:]
        if len(pair) >= 2:
            target = pair[0] if "前者" in question else pair[1]
            remainder = re.sub(
                r"^(?:那|那么)?(?:前者|后者)[，,]?(?:呢)?[。？?!！]*$",
                "",
                re.sub(r"\s+", "", question),
            )
            if not remainder and state.last_resolved_query:
                previous = state.last_resolved_query
                for entity in pair:
                    if entity in previous:
                        return previous.replace(entity, target, 1)
            replaced = question.replace("前者", pair[0]).replace("后者", pair[1])
            replaced = re.sub(r"^(?:那|那么)[，,]?", "", replaced)
            return _clean_query(replaced)

    updated = _condition_update(question, state)
    if updated:
        return updated

    intent = _infer_intent(question)
    if state.topic and _is_intent_fragment(question, intent):
        rendered = _render_intent(state.topic, intent, state.intent)
        if rendered:
            return rendered

    if _has_anaphora(question) and state.topic:
        return _replace_anaphora(question, state.topic)
    return _clean_query(question)


def _advance_state(state: SessionContextState, resolved: str) -> None:
    frame = _comparison_frame(resolved, state)
    if frame:
        state.frame = {key: value for key, value in frame.items() if key != "constraints"}
        state.constraints = list(frame.get("constraints") or state.constraints)
        for entity in frame["entities"]:
            _append_entity(state, entity)
        if not state.topic:
            state.topic = frame["entities"][0]
        state.intent = "comparison"
    else:
        topic = _extract_topic(resolved)
        if topic:
            if state.frame and topic not in (state.frame.get("entities") or []):
                state.frame = {}
                state.constraints = []
            state.topic = topic
            _append_entity(state, topic)
        state.intent = _infer_intent(resolved)
    state.last_resolved_query = resolved


def rebuild_session_state(history: list[dict], limit: int = 24) -> SessionContextState:
    state = SessionContextState()
    user_turns = [
        _strip_internal_references(str(item.get("content", "")))
        for item in history
        if item.get("role") == "user" and str(item.get("content", "")).strip()
    ][-limit:]
    for raw_question in user_turns:
        resolved = _resolve_with_state(raw_question, state)
        _advance_state(state, resolved)
    return state


def build_session_context(history: list[dict]) -> dict[str, Any]:
    """Return the observable structured state used by the resolver."""
    return asdict(rebuild_session_state(history))


def resolve_followup(question: str, history: list[dict]) -> str:
    question = question.strip()
    if not question or not history:
        return question
    return _resolve_with_state(question, rebuild_session_state(history))
