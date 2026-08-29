"""出题Agent — 保留原生成逻辑，新增对 LangGraph state 的适配"""
import json
from config import get_llm
from ingestion.vector_store import ChapterVectorStore


def generate_quiz_from_state(state: dict, count: int = 5) -> list[dict]:
    """从 graph state 生成题目"""
    chapter = state.get("target_chapters", [None])[0]
    teaching = state.get("teaching_content", "")
    if not chapter and not teaching:
        return [{"question": "请先选择章节", "type": "text", "error": True}]

    vs = ChapterVectorStore()
    outcome = vs.search_chapter(chapter, "重点 概念 例题", k=8) if chapter else None
    docs = outcome.items if outcome is not None and outcome.status != "failed" else []
    content = "\n\n".join(d.page_content for d in docs) if docs else teaching[:4000]

    llm = get_llm()
    prompt = f"""基于以下内容生成 {count} 道考研练习题（混合题型）。

## 内容
{content[:5000]}

输出 JSON 数组：
[
  {{"question": "...", "type": "选择题|填空题|解答题", "options": ["A.","B.","C.","D."], "answer": "...", "explanation": "...", "knowledge_point": "...", "difficulty": "基础|中等|提高"}}
]
只输出 JSON，不要其他。
"""
    resp = llm.invoke(prompt).content.strip()
    if resp.startswith("```"):
        resp = resp.split("\n", 1)[-1].rsplit("\n", 1)[0]
    try:
        return json.loads(resp)
    except json.JSONDecodeError:
        return [{"question": "出题失败", "type": "text", "error": True}]


def check_answer(question: dict, user_answer: str) -> dict:
    """检查答案"""
    llm = get_llm()
    prompt = f"题目：{question.get('question','')}\n正确答案：{question.get('answer','')}\n用户答案：{user_answer}\n判断对错，JSON: {{\"correct\": bool, \"score\": int, \"feedback\": \"\"}}"
    resp = llm.invoke(prompt).content.strip()
    if resp.startswith("```"):
        resp = resp.split("\n", 1)[-1].rsplit("\n", 1)[0]
    try:
        return json.loads(resp)
    except json.JSONDecodeError:
        return {"correct": False, "score": 0, "feedback": "判断失败"}
