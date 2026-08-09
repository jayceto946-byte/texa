"""参数化章节教学 Subgraph — 一个通用图，按 chapter_name 注入不同内容

Pipeline: 获取内容 → 【并行】提炼重点 / 出题 / 生成讲解+总结
优化后关键路径仅 1 次 LLM 调用（讲解+总结合并），非关键任务后台并行。
"""
import json
from concurrent.futures import ThreadPoolExecutor
from config import get_llm
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

## 要求
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
    """准备章节教学内容：获取内容、启动后台任务。

    Returns:
        (content, chapter, book_name, executor, futures)
    """
    target = state.get("target_chapters", [])
    if not target:
        return "（无内容）", "", "", None, {}

    chapter = target[0]
    user_input = state.get("user_input", "")
    intent = state.get("intent", "teach")
    book_name = state.get("book_name", "default")

    vs, vector_error = get_safe_vector_store()
    if vector_error:
        return "（无内容）", chapter, book_name, None, {}
    llm = get_llm()

    # Step 1: 获取内容（向量检索，毫秒级）
    docs = vs.search_chapter(chapter, user_input + " 重点 概念 定义", k=8, book_name=book_name)
    if not docs:
        docs = vs.search_chapter(chapter, "全部内容", k=10, book_name=book_name)

    # 【模糊匹配 fallback】如果按章节名精确匹配不到（plan_node 可能返回了小节标题），
    # 用全库语义搜索找最相关的章节
    if not docs:
        all_results = vs.search_all(user_input, k=5, top_n=1, book_name=book_name)
        if all_results:
            chapter = list(all_results.keys())[0]
            docs = vs.search_chapter(chapter, user_input + " 重点 概念 定义", k=8, book_name=book_name)
            if not docs:
                docs = vs.search_chapter(chapter, "全部内容", k=10, book_name=book_name)

    content = "\n\n".join(d.page_content for d in docs) if docs else "（无内容）"
    if content == "（无内容）":
        return content, chapter, book_name, None, {}

    # Step 2: 尝试从缓存获取摘要
    ss = SummaryStore(book_name)
    cached = ss.get(chapter)

    # Step 3: 启动后台并行任务（提取重点、出题）
    executor = ThreadPoolExecutor(max_workers=2)
    futures = {}

    if not cached:
        futures["keypoints"] = executor.submit(_extract_keypoints, content[:4000], llm)

    if intent == "teach":
        futures["quiz"] = executor.submit(_generate_quiz, chapter, content, llm)

    return content, chapter, book_name, executor, futures


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
        teach_prompt = TEACH_PROMPT.format(
            chapter=chapter,
            content=content[:6000],
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
    }
