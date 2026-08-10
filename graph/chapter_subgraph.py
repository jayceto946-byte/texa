"""参数化章节教学 Subgraph — 一个通用图，按 chapter_name 注入不同内容

Pipeline: 获取内容 → 【并行】提炼重点 / 出题 / 生成讲解+总结
优化后关键路径仅 1 次 LLM 调用（讲解+总结合并），非关键任务后台并行。
"""
import json
from concurrent.futures import ThreadPoolExecutor
from config import get_llm
from graph.conversation_context import prepare_conversation_context
from graph.safe_retrieval import get_safe_vector_store
from knowledge.summary_store import SummaryStore
from utils.latex_sanitizer import sanitize_latex
from utils.thinking_filter import strip_thinking

EXTRACT_KEYPOINTS_PROMPT = """基于以下章节内容，提取考研重点：

## 章节内容
{content}

输出 JSON（不要其他）：
{{
  "key_concepts": ["概念1", "概念2"],
  "key_formulas": ["公式1", "公式2"],
  "key_theorems": ["定理1"],
  "common_mistakes": ["易错点1"],
  "exam_frequency": "高/中/低"
}}
"""

TEACH_PROMPT = """请基于以下教材内容，讲解"{chapter}"。直接开始，不要寒暄。

## 教材内容
{content}

{conversation_context}

## 要求
0. 教材证据以 [E1]、[E2]… 标识。每个来自教材的事实结论都必须在句末使用 [[cite:E1]] 引用真实证据编号；不得编造编号，也不得用模型记忆补足证据缺口。
1. 概念定义请使用教材原文表述，如"单纯形法是指……"、"某某概念是……"
2. 遇到学习者可能第一次接触、或本身比较抽象陌生的概念时，在正式定义后补一个简短的“直观例子”或“生活化类比”，用日常场景说明它具体怎么体现；例子只用于帮助理解，不能替代教材定义、适用条件、公式推导或例题解法。
3. 以例题为主线展开讲解，逐步拆解解题过程，每步都要有具体步骤和说明；若例题题干不完整，必须如实说明，不得编造缺失的题干。
4. 不要把讲解写成概念清单；每个核心概念都尽量回到题目、公式、步骤或易错点。
5. 公式使用LaTeX：行内$...$，块级$$...$$；所有 $ / $$ 必须成对闭合，不能把中文文字或标点包在数学模式内
6. 强调要克制：粗体（**…**）只用于核心结论、必须记忆的概念名、以及重要因果/对比中的关键字；不要给大量普通名词、列表项加粗；不要加粗完整句子；标题内不要堆叠粗体。
"""


def _extract_keypoints(content: str, llm) -> str:
    """同步提取重点，用于后台线程。"""
    resp = llm.invoke(EXTRACT_KEYPOINTS_PROMPT.format(content=content[:4000]))
    raw = strip_thinking(resp.content)
    try:
        kp = json.loads(_clean_json(raw))
        return "\n".join(kp.get("key_concepts", []))
    except json.JSONDecodeError:
        return ""


def _generate_quiz(chapter: str, content: str, llm) -> list[dict]:
    """同步出题，用于后台线程。"""
    prompt = f"""基于以下章节内容，生成 3 道选择题和 2 道填空题。

## 章节：{chapter}
## 内容
{content[:4000]}

输出 JSON 数组（不要其他）：
[
  {{"question": "...", "type": "选择题", "options": ["A.","B.","C.","D."], "answer": "A", "explanation": "...", "knowledge_point": "..."}},
  ...
]
"""
    resp = llm.invoke(prompt)
    raw = strip_thinking(resp.content)
    try:
        return json.loads(_clean_json(raw))
    except json.JSONDecodeError:
        return [{"question": "出题失败", "type": "text", "error": True}]


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("\n", 1)[0]
    return text


def _future_result_if_done(futures: dict, name: str, default=None):
    """Return a background result only if it is already ready; otherwise cancel it."""
    fut = futures.get(name)
    if not fut:
        return default
    if not fut.done():
        fut.cancel()
        return default
    try:
        return fut.result()
    except Exception:
        return default

def prepare_chapter_subgraph(state: dict):
    """Prepare bounded teaching material from the retrieval EvidencePack.

    Returns:
        (content, chapter, book_name, executor, futures)
    """
    from graph.evidence_pack import build_evidence_pack
    from graph.generator import has_textbook_evidence

    if state.get("use_textbook_context", True) and not has_textbook_evidence(state):
        return "（无内容）", "", str(state.get("book_name") or ""), None, {}

    target = state.get("target_chapters", [])
    chapter = str(target[0]) if target else ""
    intent = state.get("intent", "teach")
    book_name = state.get("book_name", "default")
    evidence_pack = build_evidence_pack(
        state.get("evidence_items") or [],
        state.get("chapter_contents") or {},
        intent=intent,
    )
    state["evidence_sources"] = evidence_pack["items"]
    content = str(evidence_pack.get("text") or "")
    if not chapter and evidence_pack["items"]:
        chapter = str(evidence_pack["items"][0].get("chapter") or "")
    return content or "（无内容）", chapter, book_name, None, {}


def chapter_subgraph_run(state: dict) -> dict:
    """参数化章节教学流水线（同步版，供非流式场景使用）。

    关键路径：1 次 LLM 调用（讲解+总结合并）
    后台并行：提取重点、出题（不阻塞关键路径）
    """
    content, chapter, book_name, executor, futures = prepare_chapter_subgraph(state)
    intent = state.get("intent", "teach")

    if content == "（无内容）":
        # 返回空字符串，让 generate_node fallback 到正常 QA 生成流程
        return {"teaching_content": "", "error": "no_chapter"}

    llm = get_llm()
    ss = SummaryStore(book_name)
    cached = ss.get(chapter)

    # Step 4: 一次 LLM 调用生成讲解 + 总结
    if intent in ("teach", "summarize"):
        conversation_text, _conversation_pack = prepare_conversation_context(state)
        teach_prompt = TEACH_PROMPT.format(
            chapter=chapter,
            content=content[:6000],
            conversation_context=conversation_text,
        )
        from graph.generator import _record_context_budget

        _record_context_budget(
            state,
            teach_prompt,
            assembly_mode="teach",
            query_text=str(state.get("user_input") or ""),
            teaching_text=content[:6000],
        )
        resp = llm.invoke(teach_prompt)
        full_output = resp.content
        teaching = sanitize_latex(full_output)
        summary = ""
    else:
        teaching = sanitize_latex(f"## {chapter}\n\n{content[:3000]}")
        summary = ""

    # Step 5: 收集后台任务结果。后台任务不阻塞主讲解；没完成就跳过。
    key_points_str = _future_result_if_done(futures, "keypoints", "")
    if not key_points_str and cached:
        key_points_str = "\n".join(cached.get("key_points", []))

    quiz_questions = _future_result_if_done(futures, "quiz", [])

    if executor:
        executor.shutdown(wait=False, cancel_futures=True)

    # Step 6: 缓存结果
    if intent in ("teach", "summarize"):
        ss.set(chapter, {
            "summary": summary,
            "key_points": key_points_str.split("\n") if key_points_str else [],
            "teaching": teaching[:2000],
        })

    return {
        "teaching_content": teaching,
        "key_points": key_points_str.split("\n") if key_points_str else [],
        "extracted_examples": [],
        "quiz_questions": quiz_questions,
        "chapter_summary": summary,
        "conversation_context_seed": {},
        "conversation_context_pack": state.get("conversation_context_pack") or {},
        "context_budget": state.get("context_budget") or {},
    }
