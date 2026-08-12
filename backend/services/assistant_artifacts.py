"""Bounded deterministic index for objects introduced by assistant answers."""
from __future__ import annotations

import hashlib
import re
from typing import Any


_ORDINAL_VALUES = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}
_FORMULA_ALIASES = {
    "MSE": "均方误差公式",
    "MAE": "平均绝对误差公式",
}


def _clean(value: str, *, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = text.strip(" \t\r\n，,；;。！？?!：:")
    return text[:limit]


def _canonical_formula(value: str) -> str:
    text = _clean(value)
    alias = _FORMULA_ALIASES.get(text.upper())
    if alias:
        return alias
    return text if text.endswith("公式") else f"{text}公式"


def _topic_hint(user_query: str) -> str:
    query = _clean(user_query)
    patterns = (
        r"写出(?P<topic>.+?公式)",
        r"(?:解释|介绍|讲解|讲一下|讲讲)(?P<topic>[^，,。？?!！]{2,40})",
        r"分(?:成|为)?[^，,。？?!！]{0,10}(?:部分)?(?:解释|说明)(?P<topic>[^，,。？?!！]{2,40})",
        r"举(?:出)?(?:一|二|两|三|四|五|六|七|八|九|十|\d+)?(?:个|道)?(?P<topic>[^，,。？?!！]{2,30}?)(?:例题|例子)",
    )
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            return _clean(match.group("topic"))
    match = re.search(
        r"(?P<topic>[\u4e00-\u9fffA-Za-z0-9_]{2,30}?(?:定理|公式|方法|算法|效应|传感器|法则))",
        query,
    )
    return _clean(match.group("topic")) if match else ""


def _artifact(
    target: str,
    kind: str,
    ordinal: int,
    turn_id: str,
    group_id: str,
) -> dict[str, Any] | None:
    target = _clean(target)
    if not target or target in {"回答", "答案", "内容", "如下"}:
        return None
    return {
        "target": target,
        "kind": kind,
        "ordinal": int(ordinal),
        "turn_id": str(turn_id or "")[:100],
        "group_id": str(group_id or "")[:100],
    }


def extract_assistant_artifacts(
    content: str,
    *,
    user_query: str = "",
    turn_id: str = "",
) -> list[dict[str, Any]]:
    """Extract only answer objects that support deterministic later references."""
    text = str(content or "").strip()
    if not text or len(text) > 50_000:
        return []
    stable_digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    group_id = str(turn_id or f"assistant-{stable_digest}")[:100]
    topic = _topic_hint(user_query)
    result: list[dict[str, Any]] = []

    def add(target: str, kind: str, ordinal: int) -> None:
        item = _artifact(target, kind, ordinal, turn_id, group_id)
        if item and not any(
            old["target"] == item["target"] and old["kind"] == item["kind"]
            for old in result
        ):
            result.append(item)

    # Markdown tables: the header and separator are not user-addressable rows.
    table_rows = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [_clean(cell) for cell in line.strip().strip("|").split("|")]
        if not cells or all(re.fullmatch(r":?-{2,}:?", cell or "") for cell in cells):
            continue
        table_rows.append(cells)
    if len(table_rows) >= 2:
        suffix = "传感器" if "传感器" in user_query else ""
        for index, cells in enumerate(table_rows[1:], 1):
            target = cells[0]
            if suffix and target and not target.endswith(suffix):
                target += suffix
            add(target, "table_row", index)

    # Markdown headings become named parts of the answer.
    headings = re.findall(r"(?m)^#{1,6}\s+([^\r\n#]+)", text)
    if headings:
        base = topic or ("定理" if "定理" in user_query else "")
        for index, heading in enumerate(headings, 1):
            label = _clean(heading)
            add(f"{base}{label}" if base and base not in label else label, "heading", index)

    # Numbered Markdown/inline lists.
    numbered = re.findall(
        r"(?:^|[；;\n])\s*(\d{1,2})[.、]\s*(.+?)(?=(?:[；;\n]\s*\d{1,2}[.、])|$)",
        text,
        flags=re.S,
    )
    for raw_index, value in numbered:
        add(_clean(re.split(r"[。\n]", value, maxsplit=1)[0]), "list_item", int(raw_index))

    # Labelled formula/example sequences such as ``公式1：MSE；公式2：MAE``.
    labelled = re.findall(
        r"(公式|例题)\s*(\d{1,2})\s*[：:]\s*(.+?)(?=(?:公式|例题)\s*\d{1,2}\s*[：:]|$)",
        text,
        flags=re.S,
    )
    for label, raw_index, value in labelled:
        target = _clean(re.split(r"[；;。\n]", value, maxsplit=1)[0])
        if label == "公式":
            target = _canonical_formula(target)
        add(target, "formula" if label == "公式" else "example", int(raw_index))

    # Chinese step sequences.
    steps = re.findall(
        r"第([一二三四五六七八九十])步\s*(.+?)(?=第[一二三四五六七八九十]步|$)",
        text,
        flags=re.S,
    )
    for raw_index, value in steps:
        target = _clean(re.split(r"[，,；;。\n]", value, maxsplit=1)[0])
        add(target, "step", _ORDINAL_VALUES.get(raw_index, 0))

    bullets = [
        _clean(match)
        for match in re.findall(r"(?m)^\s*[-*+]\s+([^\r\n]+)", text)
    ]
    if len(bullets) >= 2:
        for index, value in enumerate(bullets, 1):
            add(value, "list_item", index)

    # Single addressable objects.
    counterexample = re.search(r"反例\s*[：:]\s*([^。！？?!\n]{2,160})", text)
    if counterexample:
        add(counterexample.group(1), "counterexample", 1)
    example = re.search(r"例题\s*[：:]\s*([^。！？?!\n]{2,160})", text)
    if example and not labelled:
        add(example.group(1), "example", 1)
    conclusion = re.search(r"结论\s*[：:]\s*([^。！？?!\n]{2,160})", text)
    if conclusion:
        add(conclusion.group(1), "conclusion", 1)
    recommendation = re.search(
        r"推荐(?:使用|采用)?\s*([\u4e00-\u9fffA-Za-z0-9_]{2,40}?(?:法|算法|方法|模型))(?=[。；;，,\n]|$)",
        text,
    )
    if recommendation:
        add(recommendation.group(1), "named_entity", 1)
    if re.search(r"\$[^$]+\$|\\\(|\\\[", text) and topic:
        add(topic if topic.endswith("公式") else f"{topic}公式", "formula", 1)

    # A short procedural sentence can be referred to as “这一步”.
    if not steps and len(_clean(text)) <= 80 and re.match(r"^(?:先|首先).+(?:再|然后).+", _clean(text)):
        procedure = re.sub(r"^(?:先|首先)", "", _clean(text))
        procedure = re.sub(r"[，,；;。]\s*(?:再|然后)", "再", procedure)
        add(procedure, "step", 1)

    return result[:32]


def _ordinal_value(question: str) -> int:
    match = re.search(r"第([一二三四五六七八九十\d]+)(?:个|点|道题|部分|行|步)", question)
    if not match:
        return 0
    raw = match.group(1)
    try:
        return int(raw)
    except ValueError:
        return _ORDINAL_VALUES.get(raw, 0)


def _compatible_kinds(question: str) -> set[str]:
    if "公式" in question or "式子" in question:
        return {"formula"}
    if "反例" in question:
        return {"counterexample"}
    if "道题" in question or "例题" in question:
        return {"example"}
    if "部分" in question:
        return {"heading"}
    if "行" in question:
        return {"table_row"}
    if "步" in question:
        return {"step"}
    if "结论" in question:
        return {"conclusion"}
    return {"list_item", "table_row", "heading", "example", "formula", "step", "named_entity"}


def match_assistant_artifact(question: str, artifacts: list[dict]) -> dict[str, Any] | None:
    """Return the newest compatible artifact referenced by the question."""
    if not artifacts:
        return None
    kinds = _compatible_kinds(question)
    compatible = [item for item in artifacts if item.get("kind") in kinds]
    if not compatible:
        return None

    # Prefer the newest compatible answer group while preserving item order.
    newest_group = str(compatible[-1].get("group_id") or "")
    group = [item for item in compatible if str(item.get("group_id") or "") == newest_group]
    ordinal = _ordinal_value(question)
    if ordinal:
        return next((item for item in group if int(item.get("ordinal") or 0) == ordinal), None)
    if "前者" in question:
        return group[0] if len(group) >= 2 else None
    if "后者" in question:
        return group[1] if len(group) >= 2 else None
    if any(token in question for token in ("这一步", "刚才那道题", "那道题", "这个反例", "这个式子", "这个结论")):
        return group[-1]
    if re.search(r"(?:它|其)的", question) and len(group) == 1:
        return group[0]
    return None


def rewrite_artifact_reference(question: str, artifact: dict[str, Any]) -> str:
    target = _clean(str(artifact.get("target") or ""))
    kind = str(artifact.get("kind") or "")
    if not target:
        return question.strip()
    result = question.strip()

    if "这个结论" in result:
        result = result.replace("是这个结论", target).replace("这个结论", target)
    elif "刚才那道题" in result:
        result = result.replace("刚才那道题", f"刚才{target}那道题")
    elif "那道题" in result:
        result = result.replace("那道题", f"{target}那道题")
    elif "这个反例" in result:
        result = result.replace("这个反例", f"{target}这个反例")
    elif "这个式子" in result:
        result = result.replace("这个式子", target)
    elif "这一步" in result:
        result = result.replace("这一步", f"{target}这一步")
    elif "前者" in result or "后者" in result:
        result = result.replace("前者", target).replace("后者", target)
    else:
        ordinal_pattern = r"第[一二三四五六七八九十\d]+(?:个公式|个|点|道题|部分|行|步)"
        suffix = ""
        if kind == "example" and "道题" in result:
            suffix = "这道题"
        elif kind == "step" and "步" in result:
            suffix = "这一步"
        result = re.sub(ordinal_pattern, f"{target}{suffix}", result, count=1)

    result = result.replace("它", target).replace("其", target)
    result = re.sub(r"适合动态(?=[？?。！!]|$)", "适合动态测量", result)
    if re.fullmatch(rf"{re.escape(target)}的收敛条件呢?[？?。！!]*", result):
        result = f"{target}的收敛条件是什么？"
    return _clean(result, limit=1000) + ("？" if result.rstrip().endswith(("?", "？")) else "")
