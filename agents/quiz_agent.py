"""出题Agent - 根据章节内容生成练习题"""
import json
from typing import Optional
from config import get_llm
from ingestion.vector_store import ChapterVectorStore

QUIZ_PROMPT = """你是一个考研出题专家。基于以下章节内容，生成{question_count}道{question_type}题目。

## 章节内容
{context}

## 出题要求
1. 题目必须基于给定内容，贴合考研难度
2. 题型：{question_type}
3. 每道题需包含：题目、正确答案、详细解析
4. 包含干扰选项（选择题）
5. 考察重点、难点和易错点
6. 标注每题考察的知识点

## 输出格式（JSON数组）
[
  {{
    "question": "题目内容",
    "type": "选择题|填空题|解答题",
    "options": ["A. xxx", "B. xxx", "C. xxx", "D. xxx"],  // 选择题才有
    "answer": "正确答案",
    "explanation": "详细解析",
    "knowledge_point": "考察的知识点"
  }}
]

只输出JSON数组，不要其他内容。
"""


class QuizAgent:
    """出题Agent"""

    def __init__(self, vector_store: ChapterVectorStore):
        self.vector_store = vector_store
        self.llm = get_llm()

    def generate_quiz(
        self,
        chapter: str,
        question_count: int = 5,
        question_type: str = "选择题",
    ) -> list[dict]:
        """为指定章节生成练习题"""
        outcome = self.vector_store.search_chapter(chapter, "重点概念 公式 定理 例题", k=10)
        docs = outcome.items if outcome.status != "failed" else []
        context = "\n\n".join(d.page_content for d in docs)

        if not context:
            return [{"error": f"章节「{chapter}」中没有找到足够内容来出题"}]

        prompt = QUIZ_PROMPT.format(
            chapter_title=chapter,
            context=context,
            question_count=question_count,
            question_type=question_type,
        )

        result = self.llm.invoke(prompt).content.strip()

        # 清理markdown代码块
        if result.startswith("```"):
            result = result.split("\n", 1)[-1]
            result = result.rsplit("\n", 1)[0]
            if result.endswith("```"):
                result = result[:-3]

        try:
            questions = json.loads(result)
            return questions if isinstance(questions, list) else [questions]
        except json.JSONDecodeError:
            return [{
                "question": "出题失败，请重试",
                "answer": "",
                "explanation": f"解析错误：{result[:200]}",
            }]

    def check_answer(self, question: dict, user_answer: str) -> dict:
        """检查用户答案是否正确并给出反馈"""
        llm = get_llm()
        prompt = (
            f"题目：{question['question']}\n"
            f"正确答案：{question.get('answer', '')}\n"
            f"解析：{question.get('explanation', '')}\n"
            f"\n"
            f"用户答案：{user_answer}\n\n"
            f"请判断用户答案是否正确（严格判断），给出评分（满分100）和改进建议。"
            f"以JSON格式输出：{{\"correct\": bool, \"score\": int, \"feedback\": \"建议\"}}"
        )
        result = llm.invoke(prompt).content.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[-1].rsplit("\n", 1)[0]
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"correct": False, "score": 0, "feedback": "判断失败"}
