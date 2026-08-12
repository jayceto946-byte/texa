"""Deterministic structured session context for follow-up resolution."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.services.assistant_artifacts import (
    extract_assistant_artifacts,
    match_assistant_artifact,
    rewrite_artifact_reference,
)
from backend.services.resolver_reference import (
    ReferenceResolverHooks,
    observe_reference_resolution,
)
from backend.services.resolver_state_operations import derive_state_operations
from backend.services.resolver_speech_act import apply_learning_speech_act
from backend.services.semantic_resolver import (
    run_semantic_resolver,
    should_attempt_semantic_resolution,
)


@dataclass
class SessionContextState:
    topic: str = ""
    entities: list[str] = field(default_factory=list)
    frame: dict[str, Any] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    intent: str = "qa"
    last_resolved_query: str = ""
    assistant_artifacts: list[dict[str, Any]] = field(default_factory=list)
    topic_stack: list[str] = field(default_factory=list)
    entity_records: list[dict[str, Any]] = field(default_factory=list)
    entity_groups: list[dict[str, Any]] = field(default_factory=list)


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
    "看看", "帮我看看", "请帮我看看",
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
    result = re.sub(r"^解释一下", "解释", result)
    return result.strip()


def _has_anaphora(question: str) -> bool:
    compact = re.sub(r"\s+", "", question)
    return any(word in compact for word in _ANAPHORA_WORDS)


def _extract_topic(text: str) -> str:
    """Extract a standalone entity/topic; task-only fragments return empty."""
    cleaned = _clean_query(text)
    if _has_anaphora(cleaned):
        return ""
    explicit = re.sub(
        r"^(?:请)?(?:(?:简要|简单|重新)?(?:解释|介绍|讲解|讲一下|讲讲|说明)|换一种说法解释|什么是|何谓)",
        "",
        cleaned,
    ).strip()
    has_explicit_topic_leadin = explicit != cleaned and bool(explicit)
    if has_explicit_topic_leadin:
        cleaned = explicit
    try:
        from knowledge.query_concepts import _strip_leading_noise, _strip_trailing_noise, is_task_word

        if not has_explicit_topic_leadin:
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
    if not has_explicit_topic_leadin:
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


def _append_entity(state: SessionContextState, entity: str, turn_id: str = "") -> None:
    entity = entity.strip()
    if not entity:
        return
    if entity not in state.entities:
        state.entities.append(entity)
        if len(state.entities) > 100:
            del state.entities[:-100]
    record = next((item for item in state.entity_records if item.get("name") == entity), None)
    if record is None:
        state.entity_records.append({
            "name": entity,
            "first_turn_id": turn_id,
            "last_turn_id": turn_id,
            "mentions": 1,
        })
    else:
        record["last_turn_id"] = turn_id or record.get("last_turn_id", "")
        record["mentions"] = int(record.get("mentions") or 0) + 1
    state.entity_records = state.entity_records[-100:]


def _push_topic(state: SessionContextState, topic: str) -> None:
    topic = topic.strip()
    if not topic:
        return
    if not state.topic_stack or state.topic_stack[-1] != topic:
        state.topic_stack.append(topic)
    state.topic_stack = state.topic_stack[-100:]


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
    conditioned = re.match(
        r"^在(?P<constraints>.+?)条件下[，,](?P<a>[^，,。？?；;]{1,28}?)"
        r"(?:和|与|跟|同)(?P<b>[^，,。？?；;]{2,28}?)(?P<goal>哪个.*|哪一个.*|有什么.*|有何.*)$",
        compact,
    )
    if conditioned:
        constraints = [
            value for value in re.split(r"[、]", conditioned.group("constraints")) if value
        ]
        a, b = _expand_shared_entity_suffixes([
            conditioned.group("a"), conditioned.group("b"),
        ])
        return {
            "kind": "comparison",
            "entities": [a, b],
            "goal": conditioned.group("goal"),
            "constraints": constraints,
        }
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
    fragment_patterns = {
        "reason": r"^(?:为什么|什么原因|原因是什么)$",
        "proof": r"^(?:怎么|如何)?证明$",
        "derivation": r"^(?:怎么|如何)?推导(?:出来)?的?$",
        "application": r"^(?:有什么|有哪些)?(?:应用|用途|作用)$",
        "condition": r"^(?:成立)?条件(?:是什么)?$",
        "property": r"^(?:有什么|有哪些)?(?:性质|特点|特征)$",
        "formula": r"^(?:什么|哪个)?公式(?:是什么)?$",
        "explanation": r"^(?:继续)?(?:解释|讲|说明)$",
    }
    if intent in fragment_patterns and re.fullmatch(fragment_patterns[intent], compact):
        return True
    if intent == "calculation" and len(compact) <= 8:
        return True
    if intent == "example" and len(compact) <= 10:
        return True
    return False


def _parse_ordinal_value(raw_value: str) -> int:
    try:
        return int(raw_value)
    except ValueError:
        pass
    if raw_value in _ORDINAL_VALUES:
        return _ORDINAL_VALUES[raw_value]
    if "十" not in raw_value:
        return 0
    before, after = raw_value.split("十", 1)
    tens = _ORDINAL_VALUES.get(before, 1 if before == "" else 0)
    ones = _ORDINAL_VALUES.get(after, 0) if after else 0
    return tens * 10 + ones if tens else 0


def _ordinal_target(question: str, state: SessionContextState) -> tuple[str, str] | None:
    match = re.search(r"第(?P<value>[一二三四五六七八九十\d]+)个", question)
    if not match:
        return None
    raw_value = match.group("value")
    ordinal = _parse_ordinal_value(raw_value)
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
    for suffix in _SHARED_ENTITY_SUFFIXES:
        if replacement.endswith(suffix):
            result = result.replace(f"这个{suffix}", replacement)
            result = result.replace(f"那个{suffix}", replacement)
    result = re.sub(r"^(其)(?=[\u4e00-\u9fffA-Za-z0-9])", f"{replacement}的", result)
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


def _render_comparison(state: SessionContextState, constraints: list[str]) -> str:
    entities = list(state.frame.get("entities") or [])
    if len(entities) != 2:
        return ""
    goal = str(state.frame.get("goal") or "有什么区别")
    prefix = f"在{'、'.join(constraints)}条件下，" if constraints else ""
    return f"{prefix}{entities[0]}和{entities[1]}{goal}？"


def _normalize_replacement_constraint(old: str, new: str, constraints: list[str]) -> tuple[str, str]:
    old = old.strip("，,。？?!！呢 ")
    new = new.strip("，,。？?!！呢 ")
    matched_old = next((item for item in constraints if old and old in item), old)
    if matched_old.endswith("测量") and new and not new.endswith("测量"):
        new = f"{new}测量"
    return matched_old, new


def _constraint_replacement(question: str, state: SessionContextState) -> dict[str, str] | None:
    if state.frame.get("kind") != "comparison" or not state.constraints:
        return None
    compact = re.sub(r"\s+", "", question).strip("。？?!！")
    match = re.fullmatch(r"(?:那|那么)?把(?P<old>.+?)改成(?P<new>.+?)(?:呢)?", compact)
    if not match:
        match = re.fullmatch(
            r"(?:不对[，,]?)?不是(?P<old>.+?)[，,](?:我)?说的是(?P<new>.+)", compact,
        )
    if not match:
        return None
    old, new = _normalize_replacement_constraint(
        match.group("old"), match.group("new"), list(state.constraints),
    )
    if not old or not new:
        return None
    constraints = [new if item == old else item for item in state.constraints]
    return {"old": old, "new": new, "resolved": _render_comparison(state, constraints)}


def _topic_correction(question: str, state: SessionContextState) -> dict[str, Any] | None:
    compact = re.sub(r"\s+", "", question).strip("。？?!！")
    facet_match = re.fullmatch(
        r"(?:我)?问的是(?P<new>.+?)[，,](?:而)?不是(?P<old>.+)", compact,
    )
    if facet_match and state.topic:
        new = facet_match.group("new").strip("，,。？?!！")
        previous = str(state.last_resolved_query or "")
        if new and "测量" in new:
            resolved = re.sub(
                r"(?:高频|低频)?动态测量", new, previous, count=1,
            ) if "动态测量" in previous else f"{state.topic}是否适合{new}？"
            return {
                "topic": state.topic,
                "keep_intent": True,
                "resolved": _clean_query(resolved),
            }
    reset_match = re.fullmatch(
        r"(?:(?:我说错了|不对)[，,]?)?(?:我)?(?:想问|问的是)(?P<topic>.+)", compact,
    )
    keep_match = re.fullmatch(r"(?:我)?说的是(?P<topic>.+)", compact)
    match = reset_match or keep_match
    if not match:
        return None
    topic = match.group("topic").strip("，,。？?!！")
    if not topic or len(topic) > 40 or topic == state.topic:
        return None
    keep_intent = keep_match is not None and reset_match is None
    intent = state.intent if keep_intent and state.intent != "qa" else "explanation"
    resolved = _render_intent(topic, intent, state.intent) or f"解释{topic}。"
    return {
        "topic": topic,
        "keep_intent": keep_intent,
        "resolved": resolved,
    }


def _topic_return_resolution(question: str, state: SessionContextState) -> dict[str, str] | None:
    compact = re.sub(r"\s+", "", question)
    has_return_marker = bool(re.match(r"^(?:还是)?(?:回到|说回)", compact))
    has_explicit_continue = compact.startswith(("继续讲", "继续说", "继续解释"))
    if not has_return_marker and not has_explicit_continue:
        return None
    target = next(
        (entity for entity in sorted(state.entities, key=len, reverse=True) if entity in compact),
        "",
    )
    if not target and has_return_marker:
        ordinal = _ordinal_target(question, state)
        target = ordinal[0] if ordinal else ""
    if not target:
        return None
    if "，" in question or "," in question:
        tail = re.split(r"[，,]", question, maxsplit=1)[1].strip()
        if tail.startswith(("继续讲", "继续说", "继续解释")):
            resolved = tail.replace("它", target).replace("这个", target).replace("那个", target)
        else:
            resolved = _replace_anaphora(tail, target)
    elif has_return_marker:
        resolved = re.sub(r"^(?:还是)?(?:回到|说回)(?:刚才的|前面的)?", "", question).strip()
        resolved = _replace_anaphora(resolved, target)
    else:
        resolved = question.strip()
        resolved = _replace_anaphora(resolved, target)
    return {"target": target, "resolved": resolved}


def _plural_reference(question: str, state: SessionContextState) -> dict[str, Any] | None:
    if not any(token in question for token in ("它们", "这两个", "上述方法", "上述两个", "这些方法")):
        return None
    entities = list(state.frame.get("entities") or [])
    if len(entities) < 2 and state.entity_groups:
        entities = list(state.entity_groups[-1].get("entities") or [])
    if len(entities) < 2:
        return None
    target = "和".join(entities)
    resolved = question
    for token in ("它们", "这两个", "上述方法", "上述两个", "这些方法"):
        resolved = resolved.replace(token, target)
    return {"entities": entities, "resolved": _clean_query(resolved)}


def _assistant_topic_correction(content: str) -> str:
    match = re.search(
        r"(?:其实是|应当是|应该是|指的是)\s*([\u4e00-\u9fffA-Za-z0-9_]{2,30}?(?:效应|定理|方法|算法|模型|公式|传感器))",
        content,
    )
    return match.group(1) if match else ""


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
    constraint = re.sub(r"^(?:改成|换成)", "", match.group("constraint")).strip("，,、呢")
    if not constraint:
        return ""
    constraints = list(state.constraints)
    if constraint not in constraints:
        constraints.append(constraint)
    return _render_comparison(state, constraints)


def _rephrase_followup(question: str, state: SessionContextState) -> str:
    if not state.topic:
        return ""
    compact = re.sub(r"\s+", "", question).strip("。？?!！")
    def render(style: str) -> str:
        facets = {
            "definition": f"{state.topic}的定义",
            "property": f"{state.topic}的性质",
            "condition": f"{state.topic}的成立条件",
            "formula": f"{state.topic}的公式",
            "principle": f"{state.topic}的原理",
            "application": f"{state.topic}的应用",
            "reason": f"{state.topic}的原因",
            "calculation": f"{state.topic}的计算方法",
            "derivation": f"{state.topic}的推导过程",
            "proof": f"{state.topic}的证明过程",
        }
        target = facets.get(state.intent)
        return (
            f"请{style}说明{target}。" if target
            else f"请{style}解释{state.topic}。"
        )

    if re.fullmatch(
        r"(?:再|重新)?(?:简要|简单)?(?:解释一下|解释|说明一下|说明|讲一下|讲讲)",
        compact,
    ):
        prefix = "简要" if any(token in compact for token in ("简要", "简单")) else "重新"
        return render(prefix)
    if re.fullmatch(r"(?:再)?换(?:个|一种)?说法(?:解释|说明)?(?:一下)?", compact):
        return render("换一种说法")
    return ""


def _resolve_with_state(question: str, state: SessionContextState) -> str:
    question = question.strip()
    rephrased = _rephrase_followup(question, state)
    if rephrased:
        return rephrased
    artifact = match_assistant_artifact(question, state.assistant_artifacts)
    if artifact:
        return rewrite_artifact_reference(question, artifact)

    correction = _topic_correction(question, state)
    if correction:
        return str(correction["resolved"])

    constraint_replacement = _constraint_replacement(question, state)
    if constraint_replacement:
        return constraint_replacement["resolved"]

    topic_return = _topic_return_resolution(question, state)
    if topic_return:
        return topic_return["resolved"]

    explicit_pronoun_topic = re.match(
        r"^这个(?P<topic>[\u4e00-\u9fffA-Za-z0-9_]{2,30}?(?:效应|定理|方法|算法|模型|公式|传感器))(?P<tail>.*)$",
        question,
    )
    if explicit_pronoun_topic:
        return f"{explicit_pronoun_topic.group('topic')}{explicit_pronoun_topic.group('tail')}"

    ordinal = _ordinal_target(question, state)
    if ordinal:
        target, remainder = ordinal
        if not remainder or remainder.strip("。？?!！呢 ") == "":
            previous = state.last_resolved_query
            if previous:
                for entity in reversed(state.entities):
                    if entity in previous:
                        return previous.replace(entity, target, 1)
            return target
        if _has_anaphora(remainder):
            return _replace_anaphora(remainder, target)
        return f"{target}{remainder.lstrip('，, ')}"

    plural = _plural_reference(question, state)
    if plural:
        return str(plural["resolved"])

    if "前者" in question or "后者" in question:
        pair = list(state.frame.get("entities") or [])
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

    previous_pair = re.fullmatch(r"它和前面那个(?P<tail>.+)", re.sub(r"\s+", "", question))
    if previous_pair and len(state.entities) >= 2:
        return f"{state.entities[-1]}和{state.entities[-2]}{previous_pair.group('tail')}"

    updated = _condition_update(question, state)
    if updated:
        return updated

    compact = re.sub(r"\s+", "", question).strip("。？?!！")
    if state.topic and compact in {"继续讲", "继续说", "继续解释", "接着讲", "接着说"}:
        return f"继续解释{state.topic}。"

    intent = _infer_intent(question)
    if state.topic and _is_intent_fragment(question, intent):
        rendered = _render_intent(state.topic, intent, state.intent)
        if rendered:
            return rendered

    if _has_anaphora(question) and state.topic:
        return _replace_anaphora(question, state.topic)
    return _clean_query(question)


def _advance_state(state: SessionContextState, resolved: str, turn_id: str = "") -> None:
    frame = _comparison_frame(resolved, state)
    if frame:
        state.frame = {key: value for key, value in frame.items() if key != "constraints"}
        state.constraints = list(frame.get("constraints") or [])
        for entity in frame["entities"]:
            _append_entity(state, entity, turn_id)
        group = {
            "kind": "comparison",
            "entities": list(frame["entities"]),
            "turn_id": turn_id,
        }
        if not state.entity_groups or state.entity_groups[-1] != group:
            state.entity_groups.append(group)
            state.entity_groups = state.entity_groups[-50:]
        if not state.topic:
            state.topic = frame["entities"][0]
            _push_topic(state, state.topic)
        state.intent = "comparison"
    else:
        topic = _extract_topic(resolved)
        if topic:
            if state.frame and topic not in (state.frame.get("entities") or []):
                state.frame = {}
                state.constraints = []
            state.topic = topic
            _append_entity(state, topic, turn_id)
            _push_topic(state, topic)
        state.intent = _infer_intent(resolved)
    state.last_resolved_query = resolved


def session_state_from_dict(value: dict[str, Any] | None) -> SessionContextState:
    raw = value if isinstance(value, dict) else {}
    allowed = SessionContextState.__dataclass_fields__
    return SessionContextState(**{
        key: raw[key] for key in allowed if key in raw
    })


def rebuild_session_state(
    history: list[dict],
    limit: int = 100,
    initial_state: dict[str, Any] | SessionContextState | None = None,
) -> SessionContextState:
    if isinstance(initial_state, SessionContextState):
        state = session_state_from_dict(asdict(initial_state))
    else:
        state = session_state_from_dict(initial_state)
    user_positions = [
        index for index, item in enumerate(history)
        if item.get("role") == "user" and str(item.get("content", "")).strip()
    ]
    start = user_positions[-limit] if len(user_positions) > limit else 0
    for item in history[start:]:
        role = str(item.get("role") or "")
        raw_content = str(item.get("content", ""))
        content = raw_content if role == "assistant" else _strip_internal_references(raw_content)
        if not content:
            continue
        if role == "user":
            resolved = _resolve_with_state(content, state)
            _advance_state(
                state, resolved,
                str(item.get("turn_id") or item.get("id") or ""),
            )
        elif role == "assistant":
            corrected_topic = _assistant_topic_correction(content)
            if corrected_topic:
                state.topic = corrected_topic
                _append_entity(
                    state, corrected_topic,
                    str(item.get("turn_id") or item.get("id") or ""),
                )
                _push_topic(state, corrected_topic)
            artifacts = extract_assistant_artifacts(
                content,
                user_query=state.last_resolved_query,
                turn_id=str(item.get("turn_id") or item.get("id") or ""),
            )
            if artifacts:
                state.assistant_artifacts = [*state.assistant_artifacts, *artifacts][-48:]
    return state


def build_session_context(history: list[dict]) -> dict[str, Any]:
    """Return the observable structured state used by the resolver."""
    return asdict(rebuild_session_state(history))


def _referenced_turn_ids(history: list[dict], entities: list[str]) -> list[str]:
    """Locate the newest user turns that introduced the referenced entities."""
    result: list[str] = []
    for entity in entities:
        if not entity:
            continue
        for item in reversed(history):
            if item.get("role") != "user":
                continue
            content = _strip_internal_references(str(item.get("content", "")))
            # Coordinate phrases may omit the shared suffix from the first item.
            aliases = [entity]
            for suffix in _SHARED_ENTITY_SUFFIXES:
                if entity.endswith(suffix) and len(entity) > len(suffix):
                    aliases.append(entity[:-len(suffix)])
            if any(alias and alias in content for alias in aliases):
                turn_id = str(item.get("turn_id") or item.get("id") or "").strip()
                if turn_id and turn_id not in result:
                    result.append(turn_id)
                break
    return result


def _resolution_observation(
    question: str,
    history: list[dict],
    state: SessionContextState,
    resolved: str,
) -> dict[str, Any]:
    hooks = ReferenceResolverHooks(
        match_artifact=match_assistant_artifact,
        rephrase_followup=_rephrase_followup,
        topic_correction=_topic_correction,
        constraint_replacement=_constraint_replacement,
        topic_return=_topic_return_resolution,
        plural_reference=_plural_reference,
        ordinal_target=_ordinal_target,
        infer_intent=_infer_intent,
        is_intent_fragment=_is_intent_fragment,
        has_anaphora=_has_anaphora,
        referenced_turn_ids=_referenced_turn_ids,
    )
    return observe_reference_resolution(question, history, state, resolved, hooks)


def _state_operations(
    question: str,
    before: SessionContextState,
    after: SessionContextState,
    observation: dict[str, Any],
    *,
    should_clarify: bool,
) -> tuple[str, list[dict[str, Any]]]:
    return derive_state_operations(
        question, before, after, observation,
        should_clarify=should_clarify,
        topic_correction=_topic_correction,
        constraint_replacement=_constraint_replacement,
        topic_return_resolution=_topic_return_resolution,
    )


def build_resolution_trace(
    question: str,
    history: list[dict],
    resolved_query: str | None = None,
    initial_state: dict[str, Any] | SessionContextState | None = None,
    semantic_model_runner: Any | None = None,
    semantic_enabled: bool | None = None,
) -> dict[str, Any]:
    """Build bounded resolver telemetry without changing the resolution path."""
    raw_query = question.strip()
    state_before = (
        session_state_from_dict(asdict(initial_state) if isinstance(initial_state, SessionContextState) else initial_state)
        if initial_state is not None
        else rebuild_session_state(history)
    )
    has_context = bool(
        history or state_before.topic or state_before.entities or state_before.assistant_artifacts
    )
    if resolved_query is None:
        if not raw_query or not has_context:
            resolved = raw_query
        else:
            resolved = _resolve_with_state(raw_query, state_before)
    else:
        resolved = str(resolved_query).strip()

    observation = _resolution_observation(raw_query, history, state_before, resolved)
    if not has_context and raw_query and not observation.get("is_followup"):
        observation.update({
            "method": "identity_no_history",
            "confidence": 1.0,
            "is_followup": False,
        })

    semantic_error = ""
    semantic_operation: dict[str, str] | None = None
    if should_attempt_semantic_resolution(observation, enabled=semantic_enabled):
        try:
            semantic = run_semantic_resolver(
                raw_query, state_before, model_runner=semantic_model_runner,
            )
            semantic_operation = semantic.operation
            observation.update({
                "method": semantic.method,
                "confidence": semantic.confidence,
                "confidence_kind": "rule_strength",
            })
            if semantic_operation.get("operation") == "resolve_reference":
                target = str(semantic_operation.get("value") or "")
                referenced_turn_ids = _referenced_turn_ids(history, [target])
                record = next((
                    item for item in reversed(state_before.entity_records)
                    if item.get("name") == target
                ), None)
                record_turn_id = str((record or {}).get("last_turn_id") or "")
                observation.update({
                    "is_followup": True,
                    "referenced_entity": target,
                    "referenced_entities": [target],
                    "referenced_turn_ids": (
                        [record_turn_id] if record_turn_id else referenced_turn_ids
                    ),
                })
                resolved = _replace_anaphora(raw_query, target)
                if resolved == raw_query:
                    resolved = f"关于{target}，{raw_query}"
        except Exception as exc:
            semantic_error = f"{type(exc).__name__}: {str(exc)[:300]}"

    should_clarify = observation.get("method") in {
        "unresolved_reference", "incomplete_ordinal_resolution", "semantic_clarification",
    }
    learning_speech_act = apply_learning_speech_act(raw_query, "")
    state_after = session_state_from_dict(asdict(state_before))
    if resolved and not should_clarify and not learning_speech_act:
        _advance_state(state_after, resolved)
    clarification_message = (
        "我还不能确定你指的是哪个对象。请补充对象名称，或说明你指的是上一条回答中的哪一项。"
        if should_clarify else ""
    )
    speech_act, operations = _state_operations(
        raw_query, state_before, state_after, observation,
        should_clarify=should_clarify,
    )
    speech_act = learning_speech_act or speech_act
    if semantic_operation and semantic_operation.get("operation") == "resolve_reference":
        operations.insert(0, semantic_operation)
    trace = {
        "raw_query": raw_query,
        "resolved_query": resolved,
        "resolution_action": "clarify" if should_clarify else "continue",
        "clarification_message": clarification_message,
        "speech_act": speech_act,
        "state_operations": operations,
        "state_before": asdict(state_before),
        "state_after": asdict(state_after),
        "semantic_resolver": {
            "attempted": bool(semantic_operation or semantic_error),
            "error": semantic_error,
        },
        **observation,
    }
    return trace


def resolve_followup_with_trace(question: str, history: list[dict]) -> tuple[str, dict[str, Any]]:
    """Resolve a query and return bounded before/after state for Context Trace v2."""
    trace = build_resolution_trace(question, history)
    return str(trace["resolved_query"]), trace


def resolve_followup(question: str, history: list[dict]) -> str:
    resolved, _trace = resolve_followup_with_trace(question, history)
    return resolved
