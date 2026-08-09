"""综合生成 Agent — 信息整合 + 推理生成 + 格式化输出"""
from config import get_llm
from graph.evidence_pack import build_evidence_pack
from utils.latex_sanitizer import sanitize_latex
from utils.citation_protocol import sanitize_citation_protocol
from utils.thinking_filter import strip_thinking

_EXAMPLE_CHECK_PROMPT = """
【例题完整性自检】
在引用教材例题前，请先检查检索到的内容中是否有以"例X.X"或"例X"开头的完整题干。
- 如果有完整题干：完整复述题干，然后逐步拆解解题过程。
- 如果只有解题步骤但没有完整题干，或完全没有例题相关内容：
  允许你基于检索到的概念定义和公式，自行构造一道等效例题来辅助讲解。
  自行构造的例题必须满足以下条件：
  ① 涉及的核心概念与检索内容一致，不得引入未检索到的概念；
  ② 难度和计算复杂度与教材例题相当，不得过于简单或过于复杂；
  ③ 使用的公式、符号体系与教材一致（如教材用 x^(k)，你的例题也用 x^(k)）；
  ④ 在例题开头明确标注"[补充例题]"，并在题后简要说明构造理由。
"""

GENERATE_PROMPT = """请基于以下信息回答用户问题。直接开始，不要寒暄。

## 用户意图：{intent}
## 用户问题：{user_input}

## Selected textbook evidence
{evidence_content}

## 学习者历史
{history_results}

## 章节教学产出
{teaching_content}

## 要求
1. 概念定义请使用教材原文表述，如"某某概念是指……"、"某某概念是……"
0. Every factual claim must be supported by the selected textbook evidence. Do not use model memory to fill gaps.
0. For list/reason/feature questions, exhaustively extract every parallel point in the evidence before answering.
0. 引用协议：证据块以 [E1]、[E2]… 编号开头。若某一句具体结论来自某个证据块，在句末紧跟输出 [[cite:E1]]（例如“热敏电阻具有灵敏度高、响应快等特点。[[cite:E1]]”），编号必须是证据块的真实编号，同一证据块的多处引用都用同一个编号，不要编造不存在的编号。正文中不要出现任何人类可读的教材路径（如“《教材名》·章节”“章节 / 小节”）、不要输出 ¹²³ 等上标字符、不要输出 [E1] 或 (教材名…) 这类路径。禁止暴露 chunk_id、collection、UUID、哈希等内部标识。
0. 强调要克制：粗体（**…**）只用于核心结论、必须记忆的概念名、以及重要因果/对比中的关键字；不要给大量普通名词、分类名、列表项加粗；不要加粗完整句子；标题内不要堆叠粗体；列表优先依靠排版结构而不是逐项加粗。
0. If evidence is insufficient, state that the imported textbook does not provide enough evidence.
2. 遇到用户可能第一次接触、或本身比较抽象陌生的概念时，请在正式定义后补一个简短的“直观例子”或“生活化类比”，用日常场景说明它具体怎么体现；例子只用于帮助理解，不能替代教材定义、适用条件、公式推导或例题解法。
3. 讲解结构要保留“以题讲知识点”的主线：概念只列必要项，每个核心概念尽量落回题目、公式、步骤或易错点，不要把回答写成概念清单。
4. {example_check}
5. 公式使用LaTeX：行内$...$，块级$$...$$；所有 $ / $$ 必须成对闭合，不能把中文文字或标点包在数学模式内
6. {output_instruction}
"""

SUBJECT_GENERAL_QA_PROMPT = """You are a postgraduate-study assistant answering in Chinese without textbook RAG context, using model knowledge within one subject.
Current subject: {subject}
User intent: {intent}
User question: {user_input}

Recent study memory:
{history_results}

Requirements:
1. Answer only within the current subject scope. Do not silently switch to another discipline. If the question is outside that scope, say so briefly and ask the user to use cross-subject general mode.
2. Answer directly in Chinese. This is a subject-general explanation, not a claim about wording in any selected textbook.
3. For unfamiliar or abstract concepts, give the formal explanation first, then add one short life-like example that makes the idea concrete.
4. Keep a problem-led structure: use definitions only as needed, then connect the concept back to the question, formulas, steps, or common mistakes.
5. For calculation or proof questions, solve step by step and explain why each step is used.
6. Use LaTeX for formulas: inline $...$ and display $$...$$. Every delimiter must be balanced.
7. {output_instruction}
"""

GLOBAL_GENERAL_QA_PROMPT = """You are a postgraduate-study assistant answering in Chinese with general model knowledge.
User intent: {intent}
User question: {user_input}

Recent study memory:
{history_results}

Requirements:
1. Answer directly in Chinese. The user explicitly selected cross-subject general mode, so do not claim the answer comes from a selected textbook or subject corpus.
2. For unfamiliar or abstract concepts, give the formal explanation first, then add one short life-like example that makes the idea concrete.
3. Keep a problem-led structure: use definitions only as needed, then connect the concept back to the question, formulas, steps, or common mistakes.
4. For calculation or proof questions, solve step by step and explain why each step is used.
5. Use LaTeX for formulas: inline $...$ and display $$...$$. Every delimiter must be balanced.
6. {output_instruction}
"""


def _answer_mode(state: dict) -> str:
    mode = str(state.get("answer_mode") or "").strip()
    if mode:
        return mode
    if state.get("use_textbook_context", True):
        return "textbook_grounded"
    return "subject_general" if state.get("subject") else "global_general"

def _has_example_marker(text: str) -> bool:
    """检测文本中是否包含教材例题标记（如'例4-2'、'例3'等）。"""
    import re
    return bool(re.search(r'例\s*\d+([\-\.]\d+)?', text))


def has_textbook_evidence(state: dict) -> bool:
    if not state.get("use_textbook_context", True):
        return True
    support_status = str((state.get("evidence_support") or {}).get("status") or "")
    if support_status in {"insufficient", "unavailable"}:
        return False
    if state.get("evidence_gate_applied"):
        return bool(state.get("evidence_items"))
    return bool(state.get("evidence_items") or state.get("chapter_contents"))


def grounded_failure_message(state: dict) -> str:
    support = state.get("evidence_support") or {}
    if support.get("reason") == "topic_matched_but_question_focus_missing":
        return "当前教材中只检索到与问题主题相关的内容，但没有找到能够直接支持所问事实的证据，因此不使用模型自身知识补齐答案。你可以缩小问题范围，或选择“学科通用回答”补充教材未覆盖的部分。"
    if state.get("retrieval_error") == "book_index_empty":
        return "\u5f53\u524d\u6559\u6750\u5c1a\u672a\u5efa\u7acb\u53ef\u7528\u7d22\u5f15\uff0c\u5df2\u505c\u6b62\u4f7f\u7528\u6a21\u578b\u81ea\u8eab\u77e5\u8bc6\u4f5c\u7b54\u3002\u8bf7\u5148\u91cd\u5efa\u8be5\u6559\u6750\u7d22\u5f15\u3002"
    return "当前导入教材中未检索到足够的直接证据，因此不使用模型自身知识补齐答案。你可以改用“学科通用回答”，或换一种更具体的问法。"


def suggested_fallback_mode(state: dict) -> str:
    """Return an explicit opt-in fallback; never silently widen grounding."""
    support_status = str((state.get("evidence_support") or {}).get("status") or "")
    if _answer_mode(state) != "textbook_grounded" or support_status not in {"insufficient", "unavailable"}:
        return ""
    return "subject_general" if str(state.get("subject") or "").strip() else "global_general"


def scope_boundary_message(state: dict) -> str:
    current_subject = str(state.get("subject") or "当前学科").strip()
    reason = str(state.get("scope_reason") or "")
    if reason == "known_subject_mismatch":
        return f"这个问题更可能属于其他学科，而不是当前的“{current_subject}”。为避免把跨学科内容混入当前学习记录，本轮暂不直接作答；你可以切换学科，或选择“跨学科通用回答”。"
    return f"当前本地资料无法确认这个问题属于“{current_subject}”。为避免把可能的跨学科内容混入当前学习记录，本轮暂不直接作答；如需继续，可以选择“跨学科通用回答”。"


def _build_generate_prompt(state: dict) -> str:
    intent = state.get("intent", "qa")
    user_input = state.get("user_input", "")
    mode = _answer_mode(state)
    history_text = "\n".join(f"- [{item.get('type', '')}] {item.get('chapter', '')}: {item.get('question', '')}" for item in state.get("history_results", [])[:3])
    if mode == "textbook_grounded":
        output_instruction = {
            "factual_recall": "Answer in Chinese. Give the conclusion first, then exhaustively list all textbook points. Add no external facts.",
            "definition": "Use the textbook definition first.",
            "formula": "Give the formula, variables and stated conditions.",
            "calculation": "State whether the target has one unique calculation method. Then give the relevant formula chain, variables, conditions and calculation order; do not replace the method with a list of device examples.",
            "derivation": "Show the derivation in evidence order.",
            "application": "Give complete solution steps and mark common mistakes.",
            "comparison": "Compare only dimensions supported by the evidence.",
        }.get(intent, "Answer clearly in Chinese and stay grounded in the supplied material.")
    else:
        output_instruction = {
            "factual_recall": "Give the conclusion first, followed by the essential supporting points.",
            "definition": "Give a standard formal definition first.",
            "formula": "Give the formula, variables and applicable conditions.",
            "calculation": "State whether the target has one unique calculation method. Then give the relevant formula chain, variables, conditions and calculation order; do not replace the method with a list of examples.",
            "derivation": "Show the derivation in a logically complete order.",
            "application": "Give complete solution steps and mark common mistakes.",
            "comparison": "Compare the same explicit dimensions on both sides.",
        }.get(intent, "Answer clearly and concisely in Chinese.")
    if (state.get("evidence_support") or {}).get("status") == "partial":
        output_instruction += " The textbook evidence supports only part of the question. State that limitation explicitly and answer only the supported part."
    if mode == "subject_mismatch":
        return scope_boundary_message(state)
    if mode == "global_general":
        return GLOBAL_GENERAL_QA_PROMPT.format(intent=intent, user_input=user_input, history_results=history_text or "(none)", output_instruction=output_instruction)
    if mode == "subject_general" or not state.get("use_textbook_context", True):
        return SUBJECT_GENERAL_QA_PROMPT.format(subject=state.get("subject") or "unspecified", intent=intent, user_input=user_input, history_results=history_text or "(none)", output_instruction=output_instruction)
    evidence_pack = build_evidence_pack(
        state.get("evidence_items") or [],
        state.get("chapter_contents") or {},
        intent=intent,
    )
    state["evidence_sources"] = evidence_pack["items"]
    evidence_text = evidence_pack["text"]
    example_check = _EXAMPLE_CHECK_PROMPT if _has_example_marker(evidence_text) else (
        "\u82e5\u68c0\u7d22\u5185\u5bb9\u7f3a\u5c11\u5b8c\u6574\u9898\u5e72\uff0c\u5fc5\u987b\u660e\u786e\u8bf4\u660e\u9898\u5e72\u7f3a\u5931\uff0c\u4e0d\u80fd\u7f16\u9020\u6216\u5192\u5145\u6559\u6750\u539f\u9898\u3002"
        "\u975e\u4e8b\u5b9e\u80cc\u8bf5\u95ee\u9898\u53ef\u4ee5\u7ed9\u51fa[\u8865\u5145\u4f8b\u9898]\uff0c\u4f46\u53ea\u80fd\u4f7f\u7528\u5df2\u9009\u6559\u6750\u8bc1\u636e\u4e2d\u7684\u6982\u5ff5\u548c\u516c\u5f0f\uff1b"
        "\u4e8b\u5b9e\u80cc\u8bf5\u95ee\u9898\u4e0d\u5f97\u589e\u52a0\u8865\u5145\u4f8b\u9898\u3002"
    )
    return GENERATE_PROMPT.format(
        intent=intent, user_input=user_input,
        evidence_content=evidence_text or "(no selected evidence)",
        history_results=history_text or "(none)",
        teaching_content=state.get("teaching_content") or "(none)", example_check=example_check,
        output_instruction=output_instruction,
    )


def _format_quiz_appendix(state: dict) -> str:
    """如果 intent 是 quiz 且已生成题目，返回附加 HTML。"""
    intent = state.get("intent", "")
    quiz_questions = state.get("quiz_questions", [])
    if intent != "quiz" or not quiz_questions:
        return ""
    quiz_text = "\n\n## 练习题\n"
    for i, q in enumerate(quiz_questions[:5], 1):
        quiz_text += f"\n**{i}. {q.get('question', '')}**\n"
        if q.get("options"):
            for opt in q["options"]:
                quiz_text += f"  {opt}\n"
        quiz_text += f"\n<details><summary>答案</summary>{q.get('answer', '')}</details>\n"
    return quiz_text


def generate_node(state: dict) -> dict:
    """Integrate retrieved evidence and generate the final output."""
    intent = state.get("intent", "qa")
    output_type = state.get("output_type", "text")
    teaching_content = state.get("teaching_content", "")
    if _answer_mode(state) == "subject_mismatch":
        return {"final_output": scope_boundary_message(state), "output_type": output_type}
    if state.get("use_textbook_context", True) and not has_textbook_evidence(state):
        return {
            "final_output": grounded_failure_message(state),
            "output_type": output_type,
            "suggested_answer_mode": suggested_fallback_mode(state),
        }
    if intent in ("teach", "summarize") and teaching_content:
        final = teaching_content
        chapter_summary = state.get("chapter_summary", "")
        if chapter_summary and intent == "summarize":
            final = chapter_summary
        elif chapter_summary:
            final += f"\n\n---\n\n## \u7ae0\u8282\u603b\u7ed3\n{chapter_summary}"
    else:
        try:
            llm = get_llm(temperature=0.1 if state.get("use_textbook_context", True) else 1)
        except TypeError:
            llm = get_llm()
        final = llm.invoke(_build_generate_prompt(state)).content
    final += _format_quiz_appendix(state)
    final = sanitize_latex(strip_thinking(final))
    final, citation_trace = sanitize_citation_protocol(final, state.get("evidence_sources") or [])
    state["citation_trace"] = citation_trace
    return {"final_output": final, "output_type": output_type}
