"""Query-first concept candidate extraction + coverage gate + targeted repair.

动机
----
教材激活时，最终概念集几乎完全由 KG 驱动（ConceptLinker 只返回能精确/别名
命中 KG 概念的结果），LLM fallback 仅在 ``not book_name and not concepts``
时运行。结果：用户问题中明确并列列出的多个独立概念，只要其中任何一个不是
KG 中的独立概念（例如 "横向效应"、"压电效应" 的裸形式），就会在最终 concept
set 中丢失。

本模块实现三段式修复（只读、无副作用、不依赖 FastAPI/LangGraph）：
1. extract_query_candidates —— 确定性并列结构切分 + KG 字典/别名扫描，
   回答 "用户问题里明确提到了哪些可能独立成立的学习概念"。
   正常情况下不调用 LLM（字典精确命中视为已确认）。
2. coverage_gate —— 比较 query 显式候选与 final concepts，按 canonical
   identity / 归一化名称判断覆盖，绝不使用宽泛 embedding/fuzzy 相似度。
3. targeted repair（validate_missing_candidates）—— 仅对缺失的启发式候选
   做一次受限的逐项验证（constrained classification），不重新自由生成。
   字典已确认的缺失候选直接补回，不需要 LLM。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 候选数据结构与来源标记
# ---------------------------------------------------------------------------

@dataclass
class QueryCandidate:
    name: str                       # 问题中的原词
    source: str                     # query_dictionary | query_parallel
    concept_id: str = ""            # 命中 KG 时的 concept_id
    canonical_name: str = ""        # 命中 KG 时的标准名
    confidence: float = 0.0
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source": self.source,
            "concept_id": self.concept_id,
            "canonical_name": self.canonical_name,
            "confidence": round(float(self.confidence), 3),
        }


# ---------------------------------------------------------------------------
# 任务词 / 通用噪声 / 分隔符
# ---------------------------------------------------------------------------

# 任务维度词：即使出现在并列结构中，也不是用户询问的教材实体概念。
TASK_WORDS = {
    "定义", "区别", "联系", "关系", "差异", "异同", "异同点", "相同点", "不同点", "共同点",
    "特点", "特征", "性质", "优缺点", "优点", "缺点", "优势", "劣势", "利弊",
    "应用", "用途", "作用", "原因", "过程", "方法", "步骤", "公式", "例子", "举例",
    "例题", "总结", "概括", "比较", "对比", "解释", "说明", "分析", "介绍", "简述",
    "谈谈", "讲讲", "分别", "内容", "部分", "方面", "意义", "含义", "原理", "思路",
    "技巧", "规律", "前提", "条件", "分类", "类型", "种类", "指标", "参数",
    "定义和区别", "区别与联系", "区别和联系", "定义和应用", "区别与区别", "相同与不同",
}

# 通用词 / 疑问词 / 功能词：不可能是独立教材概念。
GENERIC_NOISE = {
    "什么", "为什么", "怎么", "怎样", "如何", "哪些", "哪些方面", "有什么", "是什么",
    "怎么样", "是否", "是不是", "可不可以", "可以", "需要", "应该", "必须", "请", "帮",
    "一下", "呢", "吗", "吧", "啊", "呀", "么", "的", "了", "我", "你", "他", "她", "它",
    "我们", "你们", "他们", "这", "那", "这个", "那个", "这些", "那些", "某", "有的",
    "一些", "一种", "一个", "表示", "指的是", "是指", "指", "是", "有", "包含", "包括",
    "属于", "关于", "对于", "至于", "所谓", "比如", "例如", "相当于", "等同于", "还有",
    "另外", "其次", "然后", "以及", "和", "与", "或", "及",
    "受力", "以后", "之后", "变化", "增加", "减少", "变大", "变小", "影响", "导致",
    "为什么", "what", "when", "where", "which", "how", "why",
}

# 硬分隔符：出现才算并列结构。
_HARD_SEPARATORS = ("、", "，", ",", "/", "和", "与", "以及", "及", "或", "vs", "VS")

# 首部需要剥离的开场白 / 疑问动词（长词在前，避免部分剥离）。
_LEADING_NOISE = (
    "请解释一下", "请说明一下", "请帮我", "请比较", "请总结", "请问", "请你", "请解释",
    "请说明", "请",
    "解释一下", "说明一下", "介绍一下", "总结一下", "比较一下", "对比一下", "分析一下",
    "讨论一下", "讲一下", "谈一下", "说一说", "讲讲", "谈谈", "简述",
    "解释", "说明", "介绍", "总结", "概括", "比较", "对比", "分析", "讨论", "区分",
    "辨别", "判断", "列举", "列出", "列", "求", "求出", "计算", "推导", "证明",
    "什么是", "什么叫", "为什么", "有哪些", "有什么", "是什么", "怎么样", "怎样", "如何",
    "帮我", "帮", "一下",
)

# 尾部需要剥离的任务词 / 疑问短语（长词在前）。
_TASK_SUFFIXES = (
    "定义和区别", "区别和联系", "区别与联系", "定义和应用", "有什么不同", "有什么区别",
    "有何区别", "有什么差别", "有何不同", "是什么意思", "有哪些", "有什么", "是什么",
    "分别表示什么", "分别是什么", "表示什么", "是指什么",
    "的区别", "的联系", "的关系", "的异同", "之间的区别", "之间的关系", "之间的联系",
    "优缺点", "定义", "区别", "联系", "关系", "差异", "异同", "异同点", "相同点", "不同点",
    "共同点", "特点", "特征", "性质", "优点", "缺点", "优势", "劣势", "应用", "用途",
    "作用", "原因", "过程", "方法", "步骤", "公式", "例子", "举例", "例题", "总结",
    "比较", "对比", "差别", "意义", "含义", "原理", "思路", "类型", "分类", "分别",
    "之间", "方面", "之区别",
    "什么区别", "有什么区别", "有什么区别", "什么联系", "有什么联系", "什么不同",
    "有什么不同", "什么关系", "有什么特点", "有什么性质", "有什么作用", "什么含义",
    "有何不同", "有何差别", "有什么差别",
    "怎么样", "怎么求", "怎么算", "怎么理解", "怎么推导", "怎么证明", "怎么区分",
    "怎么计算", "怎么", "怎样", "如何", "是否", "是不是", "为什么", "哪个好", "哪个更好",
    "更适用", "更常用", "表示", "指的是", "是指",
)

# 尾部连接词：允许在任务词/疑问短语前出现。
# 注意：不把 "什么/有什么/有何" 当作连接词，否则 "拉格朗日插值有什么区别"
# 会被拆成 "拉格朗日插值有"（残留 "有"）。完整短语直接放入 _TASK_SUFFIXES。
_SUFFIX_CONNECTORS = ("以及", "和", "与", "及", "之间", "方面",
                      "的", "分别", "中", "上", "之", "、", "，", ",")


def normalize_full(value: str) -> str:
    """归一化概念名/候选名：去空白、全半角统一、转小写。"""
    if not value:
        return ""
    text = str(value).strip().lower()
    # 全角转半角（仅标点与字母数字）
    text = text.replace("\u3000", " ")
    text = text.replace("\uff0c", ",").replace("\u3001", ",").replace("\uff1f", "?")
    text = text.replace("\uff01", "!").replace("\uff1b", ";").replace("\uff1a", ":")
    text = text.replace("\uff08", "(").replace("\uff09", ")")
    text = re.sub(r"\s+", "", text)
    return text.strip()


def is_task_word(value: str) -> bool:
    norm = normalize_full(value)
    return bool(norm) and (norm in TASK_WORDS or norm in GENERIC_NOISE)


# ---------------------------------------------------------------------------
# 噪声剥离
# ---------------------------------------------------------------------------

def _strip_leading_noise(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        for noise in _LEADING_NOISE:
            if text.startswith(noise):
                text = text[len(noise):]
                break
        text = text.lstrip(" \u3000、，,；:()（）\"'“”")
    return text


def _strip_trailing_noise(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"[呢吗吧啊呀么的了？?。！!\s]+$", "", text)
        matched = False
        for connector in _SUFFIX_CONNECTORS:
            for suffix in _TASK_SUFFIXES:
                target = connector + suffix
                if text.endswith(target):
                    text = text[:-len(target)]
                    matched = True
                    break
            if matched:
                break
        if not matched:
            # 无连接词时，允许裸任务词结尾
            for suffix in _TASK_SUFFIXES:
                if text.endswith(suffix):
                    text = text[:-len(suffix)]
                    matched = True
                    break
        text = text.rstrip(" \u3000、，,；:()（）\"'“”")
    return text


# 从句引导词：出现在段首时，该段是新的指令从句而非并列概念。
_CLAUSE_INTROS = (
    "再说明", "然后再", "然后", "还有", "另外", "并且", "同时", "接着", "最后", "首先",
    "其次", "再", "请", "再说", "再谈", "分别", "再分别", "再指出", "注意",
)


def _drop_segment(cleaned: str) -> bool:
    """过滤明显不是并列概念的分段。"""
    if not cleaned or len(cleaned) < 2:
        return True
    if cleaned.startswith(_CLAUSE_INTROS):
        return True
    # 含通用噪声词（如 它们/以后/变化）的分段不是独立教材概念
    if any(g in cleaned for g in GENERIC_NOISE if len(g) >= 2):
        return True
    return False


def _clean_segment(segment: str) -> str:
    segment = segment.strip(" \u3000、，,；:()（）\"'“”")
    segment = _strip_leading_noise(segment)
    segment = _strip_trailing_noise(segment)
    return segment.strip(" \u3000、，,；:()（）\"'“”")


def split_parallel_phrases(query: str) -> list[str]:
    """从用户问题中切分并列候选短语。

    只在原始问题（剥离开场白后）存在明确并列分隔符（、，,/ 和 与 以及 及 或 vs）
    时才返回并列结构；若切分后坍缩为单个名词（如 "热敏电阻的定义、特点、优点、
    缺点和应用" -> "热敏电阻"），仍作为候选返回。
    任务词、疑问词、通用词、从句引导词在返回前被过滤。
    不负责最终判定候选是否成立 —— 那是 Coverage Gate + repair 的职责。
    """
    if not query:
        return []
    text = _strip_leading_noise(query)
    # 用剥离开场白后的原文判断是否真的有并列结构（避免预剥离把分隔符清空）
    has_separator = any(sep in text for sep in _HARD_SEPARATORS)
    text = _strip_trailing_noise(text)
    if not has_separator:
        return []
    parts = re.split(r"[、，,/]|(?:和|与|以及|及|或|vs|VS)", text)
    result: list[str] = []
    for part in parts:
        cleaned = _clean_segment(part)
        if _drop_segment(cleaned):
            continue
        if is_task_word(cleaned):
            continue
        if cleaned not in result:
            result.append(cleaned)
    return result


# ---------------------------------------------------------------------------
# Query-first candidate extraction
# ---------------------------------------------------------------------------

def _dictionary_candidates(query: str, kg: Any) -> list[QueryCandidate]:
    """KG 字典/别名扫描：整句范围内 exact canonical/alias substring 命中。

    命中即视为 "已确认" 的 query candidate（优先级最高，不依赖 LLM 判断）。
    命中后被更长匹配项完全包含、且从未独立出现的候选会被剔除：
    例如 "随机误差、系统误差和粗大误差" 中 "误差" 只作为更长匹配项的一部分，
    不应把 "误差/绝对误差(别名 误差)" 当作独立候选；
    而 "什么是误差和随机误差的区别" 中 "误差" 有独立出现，应保留。
    """
    if kg is None or not getattr(kg, "_is_local", False):
        return []
    lowered = normalize_full(query)
    if not lowered:
        return []
    found: dict[str, tuple[QueryCandidate, str]] = {}  # key -> (candidate, matched_term)
    try:
        concepts = list(getattr(kg, "concepts", []) or [])
    except Exception:
        return []
    for concept in concepts:
        if not isinstance(concept, dict):
            continue
        canonical = str(concept.get("canonical_name") or "").strip()
        if len(canonical) < 2:
            continue
        terms = [canonical, *[str(a).strip() for a in concept.get("aliases", []) or []]]
        terms = sorted({t for t in terms if len(t) >= 2}, key=len, reverse=True)
        hit = next((t for t in terms if normalize_full(t) and normalize_full(t) in lowered), "")
        if not hit:
            continue
        cid = str(concept.get("concept_id") or "")
        if cid and cid in found:
            continue
        found[cid or canonical] = (
            QueryCandidate(
                name=canonical,
                source="query_dictionary",
                concept_id=cid,
                canonical_name=canonical,
                confidence=1.0,
                aliases=[str(a) for a in concept.get("aliases", []) or [] if str(a).strip()],
            ),
            normalize_full(hit),
        )
    return [cand for cand, _ in _prefer_canonical_over_alias(_filter_subsumed(list(found.values()), lowered))]


def _filter_subsumed(entries: list[tuple[QueryCandidate, str]], lowered_q: str) -> list[tuple[QueryCandidate, str]]:
    """剔除被更长匹配项完全包含、且从未独立出现的字典候选。"""
    if len(entries) <= 1:
        return entries
    spans: list[tuple[str, int, int]] = []  # (term, start, end)
    for _, term in entries:
        start = 0
        while True:
            idx = lowered_q.find(term, start)
            if idx < 0:
                break
            spans.append((term, idx, idx + len(term)))
            start = idx + len(term)
    result: list[tuple[QueryCandidate, str]] = []
    for cand, term in entries:
        own = [(s, e) for t, s, e in spans if t == term]
        longer_spans = [(s, e) for t, s, e in spans if len(t) > len(term)]
        if not longer_spans:
            result.append((cand, term))
            continue
        # 存在某个独立出现（不被任何更长匹配项包含）才保留
        standalone = any(
            not any(sl <= s and el >= e for sl, el in longer_spans)
            for s, e in own
        )
        if standalone:
            result.append((cand, term))
    return result


def _prefer_canonical_over_alias(entries: list[tuple[QueryCandidate, str]]) -> list[tuple[QueryCandidate, str]]:
    """同一匹配 term 命中多个概念时，精确 canonical 命中优先，丢弃仅靠别名命中的项。

    例如 "什么是误差和随机误差的区别" 中 "误差" 同时命中 canonical "误差" 和
    别名 "误差"（绝对误差 的数据别名），只保留 canonical "误差"。
    """
    by_term: dict[str, list[tuple[QueryCandidate, str]]] = {}
    for cand, term in entries:
        by_term.setdefault(term, []).append((cand, term))
    result: list[tuple[QueryCandidate, str]] = []
    for group in by_term.values():
        if len(group) <= 1:
            result.extend(group)
            continue
        canonicals = [(c, t) for c, t in group if normalize_full(c.canonical_name) == t]
        if canonicals:
            result.extend(canonicals)
        else:
            result.extend(group)
    return result


def extract_query_candidates(query: str, kg: Any = None) -> list[QueryCandidate]:
    """Query-first 候选抽取（确定性 + 字典，正常情况不调用 LLM）。

    优先级：KG 精确 canonical/alias 命中 > 并列结构切分出的 noun phrase。
    任务词 / 通用词已在切分阶段过滤。
    """
    if not query or not str(query).strip():
        return []
    candidates: list[QueryCandidate] = []
    seen: set[str] = set()

    for cand in _dictionary_candidates(query, kg):
        key = normalize_full(cand.canonical_name or cand.name)
        if not key or key in seen:
            continue
        seen.add(key)
        candidates.append(cand)

    for name in split_parallel_phrases(query):
        key = normalize_full(name)
        if not key or key in seen:
            continue
        seen.add(key)
        candidates.append(QueryCandidate(name=name, source="query_parallel"))

    return candidates


# ---------------------------------------------------------------------------
# 合并 / 覆盖判定
# ---------------------------------------------------------------------------

def _concept_key(item: dict) -> tuple[str, str]:
    cid = str(item.get("concept_id") or "").strip()
    if cid:
        return ("id", cid)
    name = normalize_full(str(item.get("name") or ""))
    return ("name", name)


def append_concepts(existing: list[dict], extra: list[dict]) -> list[dict]:
    """按 canonical identity（concept_id 优先，其次归一化 name）去重合并。

    不做字符串相似度去重 —— 压阻效应 / 压电效应 这类不同概念绝不会被合并。
    """
    result = list(existing or [])
    keys = {_concept_key(item) for item in result}
    for item in extra or []:
        if not isinstance(item, dict):
            continue
        key = _concept_key(item)
        if key in keys:
            continue
        result.append(item)
        keys.add(key)
    return result


def coverage_gate(query_candidates: list[QueryCandidate],
                  final_concepts: list[dict]) -> tuple[list[QueryCandidate], list[QueryCandidate]]:
    """比较 query 显式候选与 final concepts。

    返回 (auto_missing, validate_missing)：
    - auto_missing: 字典已确认（query_dictionary）但未进入 final —— 直接补回。
    - validate_missing: 启发式候选（query_parallel）未进入 final —— 需要验证。

    覆盖判定按 concept_id / 归一化名称，绝不使用宽泛 embedding/fuzzy 相似度，
    避免 压阻效应 与 压电效应 被错误视为同一概念。
    """
    final_ids = {str(c.get("concept_id") or "") for c in final_concepts or [] if c.get("concept_id")}
    final_names = {normalize_full(str(c.get("name") or "")) for c in final_concepts or [] if c.get("name")}
    final_aliases = set()
    for c in final_concepts or []:
        for alias in c.get("aliases", []) or []:
            norm = normalize_full(str(alias))
            if norm:
                final_aliases.add(norm)

    auto_missing: list[QueryCandidate] = []
    validate_missing: list[QueryCandidate] = []
    for cand in query_candidates or []:
        if cand.source == "query_dictionary":
            covered = (cand.concept_id in final_ids) or (
                normalize_full(cand.canonical_name or cand.name) in final_names
            )
            if not covered:
                auto_missing.append(cand)
        else:
            name_norm = normalize_full(cand.name)
            covered = name_norm in final_names or name_norm in final_aliases
            if not covered:
                validate_missing.append(cand)
    return auto_missing, validate_missing


# ---------------------------------------------------------------------------
# Targeted repair
# ---------------------------------------------------------------------------

_VALIDATION_PROMPT = """你是一个学习概念验证器。用户问题中明确提到了下面这些候选短语。
请逐项判断它们是否是一个独立成立的教材/学习概念（数学概念、定理、物理效应、专业术语、算法、公式、器件等）。

## 用户问题
{question}

## 候选列表
{candidates}

对每个候选，返回 JSON 数组，每项：
{{"candidate": "原词", "valid_concept": true/false, "canonical_name": "标准写法(无效则为空)", "reason": "一句话原因"}}

规则：
1. 不要比较重要性，不要只保留"最重要"的一个。每个候选都独立判断。
2. 任务词或指令词（定义、区别、特点、优点、缺点、应用、原因、总结、比较、解释、分析等）必须返回 valid_concept=false。
3. 通用词或疑问词（什么、怎么、为什么、是否、可以、需要、我们、这个、变化、以后 等）返回 false。
4. 只要候选是独立成立的教材专业概念，即使教材里对它着墨很少，也返回 true。
5. canonical_name 使用教材/学科中的标准写法，若与原词相同则填原词。

只输出 JSON 数组，不要输出其他内容。"""


def _parse_validation_response(raw: str) -> list[dict]:
    if not raw:
        return []
    text = str(raw).strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    start, end = text.find("["), text.rfind("]")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        value = json_loads(text)
        return value if isinstance(value, list) else []
    except Exception:
        return []


def json_loads(text: str) -> Any:
    import json
    return json.loads(text)


def build_validation_prompt(question: str, missing: list[QueryCandidate]) -> str:
    lines = "\n".join(f"- {cand.name}" for cand in missing)
    return _VALIDATION_PROMPT.format(question=question, candidates=lines)


def validate_missing_candidates(question: str, missing: list[QueryCandidate], llm: Any) -> list[dict]:
    """对缺失的启发式候选做一次受限逐项验证。

    返回补入 final concepts 的 dict 列表（仅 valid_concept=true 的项）。
    这不是重新自由生成，而是 constrained classification，成本与随机性都低。
    """
    if not missing:
        return []
    try:
        from utils.thinking_filter import strip_thinking
        prompt = build_validation_prompt(question, missing)
        raw = strip_thinking(str(llm.invoke(prompt).content or ""))
        verdicts = _parse_validation_response(raw)
    except Exception as exc:
        print(f"[ConceptMemory] repair validation failed: {exc}", flush=True)
        return []

    by_name = {normalize_full(str(v.get("candidate") or "")): v for v in verdicts if isinstance(v, dict)}
    result: list[dict] = []
    for cand in missing:
        verdict = by_name.get(normalize_full(cand.name))
        if not verdict:
            continue
        if not verdict.get("valid_concept"):
            continue
        canonical = str(verdict.get("canonical_name") or cand.name).strip() or cand.name
        result.append({
            "name": canonical,
            "concept_id": cand.concept_id or "",
            "type": "concept",
            "confidence": 0.9,
            "source": "query_repair",
            "evidence": cand.name,
            "aliases": [cand.name] if canonical != cand.name else [],
        })
    return result


# ---------------------------------------------------------------------------
# 可观测性
# ---------------------------------------------------------------------------

def debug_log_concepts(question: str, query_candidates: list[QueryCandidate],
                       final_concepts: list[dict], auto_missing: list[QueryCandidate],
                       validate_missing: list[QueryCandidate], repaired: list[dict]) -> None:
    """调试日志：只记录概念名 / ID / 来源，不输出教材正文，不进入用户 UI。"""
    if not query_candidates and not auto_missing and not validate_missing:
        return
    print(
        "[ConceptMemory] query_candidates=%s auto_missing=%s validate_missing=%s "
        "repair_added=%s final_concepts=%s"
        % (
            [c.to_dict() for c in query_candidates],
            [c.to_dict() for c in auto_missing],
            [c.to_dict() for c in validate_missing],
            [(c.get("name"), c.get("source")) for c in repaired],
            [(c.get("name"), c.get("source")) for c in final_concepts],
        ),
        flush=True,
    )
