"""细粒度意图分类器 — 本地关键词匹配 + LLM 辅助验证

设计原则：
1. 简单意图（definition/formula/property）走 Fast Path，跳过 plan LLM
2. 复杂意图仍走 plan_node，但传入本地分类结果作为 hint
3. 分类结果直接影响后续 prompt 策略和检索策略

为后续扩展预留：
- 可依据意图类型触发不同的 ConceptMemory 查询策略
- 可依据意图类型决定是否需要跨章节检索
"""
import re
from typing import Optional

# ── 意图定义 ──────────────────────────────────────────────

INTENT_META = {
    "factual_recall": {
        "keywords": ["\u4e3a\u4ec0\u4e48", "\u539f\u56e0", "\u662f\u5426\u9002\u5408", "\u6709\u54ea\u4e9b", "\u54ea\u51e0", "\u5217\u51fa", "\u7b80\u8ff0", "\u8bf4\u660e", "\u4f18\u70b9", "\u7f3a\u70b9"],
        "anti_keywords": ["\u8ba1\u7b97", "\u6c42\u89e3", "\u8bc1\u660e", "\u63a8\u5bfc"],
        "description": "textbook factual recall",
        "is_simple": True,
    },
    # === 简单意图 → Fast Path（跳过 plan LLM）===
    "definition": {
        "keywords": ["什么是", "定义", "含义", "意思", "概念", "名词解释"],
        "anti_keywords": ["区别", "联系", "比较", "推导", "证明", "计算", "求解"],
        "description": "概念定义",
        "is_simple": True,
    },
    "formula": {
        "keywords": ["公式", "表达式", "计算式", "式子", "方程"],
        "anti_keywords": ["推导", "证明", "由来"],
        "description": "公式/表达式",
        "is_simple": True,
    },
    "property": {
        "keywords": ["性质", "特点", "特征", "定理", "引理", "推论", "条件"],
        "anti_keywords": ["证明", "推导", "计算"],
        "description": "性质/定理",
        "is_simple": True,
    },
    "calculation": {
        "keywords": ["怎么算", "如何计算", "怎么计算", "计算方法", "如何算", "怎么求", "求法", "计算"],
        "anti_keywords": ["推导", "证明"],
        "description": "公式计算/计算方法",
        "is_simple": False,
    },

    # === 复杂意图 → 走完整 graph（plan + generate）===
    "derivation": {
        "keywords": ["推导", "证明", "怎么来的", "由来", "过程", "步骤"],
        "anti_keywords": [],
        "description": "推导/证明",
        "is_simple": False,
    },
    "comparison": {
        "keywords": ["区别", "联系", "比较", "vs", "versus", "差异", "优劣"],
        "anti_keywords": [],
        "description": "比较/区别",
        "is_simple": False,
    },
    "application": {
        "keywords": ["求解", "这道题", "例题", "应用", "怎么做", "求"],
        "anti_keywords": [],
        "description": "应用/计算",
        "is_simple": False,
    },
    "teach": {
        "keywords": ["讲解", "教我", "讲一讲", "系统讲", "教一下", "给我讲", "详细讲", "介绍一下", "系统学习"],
        "anti_keywords": ["步骤", "推导", "证明", "计算", "求解", "怎么做这道题"],
        "description": "系统讲解",
        "is_simple": False,
    },
    "summarize": {
        "keywords": ["总结", "概括", "梳理", "归纳", "小结", "概要", "提纲", "框架"],
        "anti_keywords": [],
        "description": "总结",
        "is_simple": False,
    },
    "quiz": {
        "keywords": ["出题", "测验", "练习", "考我", "测试", "题目"],
        "anti_keywords": [],
        "description": "出题测验",
        "is_simple": False,
    },
    "plan": {
        "keywords": ["规划", "计划", "安排", "进度", "怎么学", "建议"],
        "anti_keywords": [],
        "description": "学习规划",
        "is_simple": False,
    },
    "cross_chapter": {
        "keywords": ["关联", "联系", "跨章节", "综合运用", "结合"],
        "anti_keywords": [],
        "description": "跨章节关联",
        "is_simple": False,
    },
}

# 简单意图的最大问题长度（含标点）
_SIMPLE_MAX_LEN = 35

_SIMPLE_COMPARISON_RE = re.compile(
    r"^.{2,14}?(?:和|与|跟|同).{2,14}?(?:有什么|有何|的)?(?:区别|不同|差异|异同|联系)[？?。！!]*$"
)
_SIMPLE_CALCULATION_RE = re.compile(
    r"^.{2,24}?(?:怎么算|怎么计算|如何算|如何计算|的计算方法(?:是什么)?)[？?。！!]*$"
)
_SIMPLE_EXPLANATION_RE = re.compile(
    r"^(?:根据教材|按照教材|依据教材)?(?:请|帮我|再)?(?:解释|说明|介绍)(?:一下)?[^，,；;]{2,24}[？?。！!]*$"
)
_EXPLANATION_COMPLEX_SIGNALS = (
    "为什么", "推导", "证明", "计算", "比较", "区别", "联系", "并说明", "分别", "系统", "详细",
)


def _deterministic_simple_shape(query: str) -> tuple[str, str] | None:
    """Recognize bounded query shapes whose routing adds no value via an LLM."""
    compact = re.sub(r"\s+", "", query).strip()
    if len(compact) > _SIMPLE_MAX_LEN:
        return None
    if _SIMPLE_COMPARISON_RE.match(compact):
        return "comparison", "simple_comparison"
    if _SIMPLE_CALCULATION_RE.match(compact):
        return "calculation", "simple_calculation"
    if _SIMPLE_EXPLANATION_RE.match(compact) and not any(signal in compact for signal in _EXPLANATION_COMPLEX_SIGNALS):
        return "definition", "simple_explanation"
    return None


def classify_intent_local(user_input: str) -> dict:
    """本地毫秒级意图分类。

    Returns:
        {
            "intent": str,
            "confidence": float,   # 0.0-1.0
            "is_simple": bool,     # 是否可走 Fast Path
            "hint": str,           # 给 plan_node 的提示语
        }
    """
    q = user_input.lower().strip()
    if not q:
        return {"intent": "qa", "confidence": 1.0, "is_simple": True, "hint": "空输入"}

    deterministic = _deterministic_simple_shape(q)
    if deterministic:
        intent, shape = deterministic
        return {
            "intent": intent,
            "confidence": 0.9,
            "is_simple": True,
            "intent_locked": True,
            "deterministic_shape": shape,
            "hint": f"确定性短查询路由：{shape}",
        }

    # An explicit leading task verb is more reliable than keyword-score ties
    # such as "比较……并说明……", where "说明" previously won by insertion order.
    if re.match(r"^(?:请)?(?:比较|对比)", q):
        return {
            "intent": "comparison",
            "confidence": 0.95,
            "is_simple": False,
            "intent_locked": True,
            "hint": "显式比较任务（确定性意图，复杂约束仍交给 Planner 定位章节）",
        }

    scores = {}
    for intent, meta in INTENT_META.items():
        score = 0
        matched_kw = []
        for kw in meta["keywords"]:
            if kw in q:
                score += 1
                matched_kw.append(kw)
        for anti in meta.get("anti_keywords", []):
            if anti in q:
                score -= 2  # anti keyword 权重更高
        scores[intent] = (score, matched_kw)

    # 选出最高分
    best_intent = max(scores, key=lambda k: scores[k][0])
    best_score, best_kw = scores[best_intent]
    meta = INTENT_META[best_intent]

    # 置信度计算
    if best_score <= 0:
        # 没有匹配到任何关键词，降级为通用 qa
        return {"intent": "qa", "confidence": 0.3, "is_simple": False, "hint": "未匹配到明确意图"}

    confidence = min(0.5 + best_score * 0.15, 0.95)

    # Fast Path 判断：必须是 simple intent + 问题不长 + 没有 anti keyword
    is_simple = meta["is_simple"]
    if is_simple and len(user_input) > _SIMPLE_MAX_LEN:
        is_simple = False  # 太长，可能隐含复杂需求
    if is_simple and any(anti in q for anti in meta.get("anti_keywords", [])):
        is_simple = False

    hint = f"本地分类器判断意图为「{meta['description']}」(confidence={confidence:.2f})"
    if best_kw:
        hint += f"，匹配关键词：{', '.join(best_kw)}"

    return {
        "intent": best_intent,
        "confidence": confidence,
        "is_simple": is_simple,
        "intent_locked": bool(
            (best_intent == "comparison" and re.search(r"(?:^|请)(?:比较|对比)", q))
            or (best_intent in {"calculation", "derivation"} and best_kw)
        ),
        "hint": hint,
    }


def is_fast_path_eligible(user_input: str, local_result: dict) -> bool:
    """判断是否可以走 Fast Path（跳过 plan LLM）。

    Fast Path 条件（全部满足）：
    1. 本地分类器置信度 >= 0.6
    2. 属于 simple intent
    3. 问题不包含 "为什么"/"怎么推导"/"证明" 等复杂词
    4. 问题长度 <= 35 字
    """
    if local_result["confidence"] < 0.6:
        return False
    if not local_result["is_simple"]:
        return False
    if len(user_input) > _SIMPLE_MAX_LEN:
        return False

    q = user_input.lower()
    shape = local_result.get("deterministic_shape")
    if shape in {"simple_comparison", "simple_calculation", "simple_explanation"}:
        complex_signals = ["为什么", "怎么推导", "证明", "推导过程", "并说明", "分别", "系统", "详细"]
    else:
        complex_signals = ["为什么", "怎么推导", "证明", "比较", "区别", "联系", "计算", "求解"]
    if local_result.get("intent") == "factual_recall":
        complex_signals = ["\u600e\u4e48\u63a8\u5bfc", "\u8bc1\u660e", "\u6bd4\u8f83", "\u533a\u522b", "\u8054\u7cfb", "\u8ba1\u7b97", "\u6c42\u89e3"]
    if any(s in q for s in complex_signals):
        return False

    return True


def build_plan_hint(local_result: dict) -> str:
    """为 plan_node 构建 hint，减少 LLM 的猜测空间。"""
    return local_result.get("hint", "")
