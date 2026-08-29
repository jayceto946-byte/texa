"""协调器Agent - 路由用户问题 + 跨章节关联问答"""
from typing import Optional

from config import get_llm
from ingestion.vector_store import ChapterVectorStore
from agents.chapter_agent import ChapterAgent

ROUTER_PROMPT = """你是一个考研学科导航专家。用户的问题涉及以下章节之一：

{chapters_list}

请分析用户的问题，判断最相关的章节（只返回章节完整名称，不要额外内容）。
如果问题不涉及任何特定章节，请返回"general"。
如果问题**涉及多个章节的关联知识**，请返回"cross"。

用户问题：{question}
"""

CROSS_CHAPTER_PROMPT = """你是一个考研学科导航专家。用户的问题涉及以下章节：

{chapters_list}

请分析用户的问题，返回**所有相关章节**的名称（每行一个，按相关度从高到低）。
最多返回5个章节。

用户问题：{question}

只返回章节列表，不要额外内容。"""


class CoordinatorAgent:
    """协调器 - 路由 + 跨章节问答"""

    def __init__(self, vector_store: ChapterVectorStore):
        self.vector_store = vector_store
        self.llm = get_llm()
        self._chapter_agents: dict[str, ChapterAgent] = {}

    def _get_chapter_names(self) -> list[str]:
        return self.vector_store.get_chapter_names()

    def _route(self, question: str) -> Optional[str]:
        chapters = self._get_chapter_names()
        if not chapters:
            return None

        chapters_str = "\n".join(f"- {ch}" for ch in chapters)
        prompt = ROUTER_PROMPT.format(chapters_list=chapters_str, question=question)
        result = self.llm.invoke(prompt).content.strip()
        return result

    def _get_related_chapters(self, question: str, max_chapters: int = 5) -> list[str]:
        chapters = self._get_chapter_names()
        if not chapters:
            return []

        chapters_str = "\n".join(f"- {ch}" for ch in chapters)
        prompt = CROSS_CHAPTER_PROMPT.format(chapters_list=chapters_str, question=question)
        result = self.llm.invoke(prompt).content.strip()
        return [line.strip("- ").strip() for line in result.split("\n")
                if line.strip() and not line.strip().startswith("只")]

    def ask(self, question: str) -> dict:
        route = self._route(question)
        chapters = self._get_chapter_names()

        if route is None or route == "general":
            llm = get_llm()
            resp = llm.invoke(
                f"你是一个考研辅导助手。回答以下问题：\n\n{question}\n\n"
                f"如果涉及具体知识点，请建议用户先导入相关教材。"
            )
            return {"answer": resp.content, "chapter": "general", "chapters": []}

        if route == "cross" or route not in chapters:
            return self._cross_chapter_ask(question)

        if route not in self._chapter_agents:
            self._chapter_agents[route] = ChapterAgent(route, self.vector_store)
        answer = self._chapter_agents[route].ask(question)
        return {"answer": answer, "chapter": route, "chapters": [route]}

    def _cross_chapter_ask(self, question: str) -> dict:
        """跨章节问答：检索多个相关章节并综合回答"""
        related = self._get_related_chapters(question)
        if not related:
            llm = get_llm()
            resp = llm.invoke(f"你是一个考研辅导助手。回答以下问题：\n\n{question}")
            return {"answer": resp.content, "chapter": "general", "chapters": []}

        context_parts = []
        for ch in related[:5]:
            if ch not in self._chapter_agents:
                self._chapter_agents[ch] = ChapterAgent(ch, self.vector_store)
            ctx = self._chapter_agents[ch].retrieve_context(question, k=4)
            if ctx:
                context_parts.append(f"## 章节「{ch}」\n{ctx}")

        if not context_parts:
            return self.ask(question)

        combined = "\n\n".join(context_parts)
        llm = get_llm()
        prompt = (
            f"你是一个考研辅导专家。以下是从多个章节中检索到的参考资料：\n\n"
            f"{combined}\n\n"
            f"## 用户问题\n{question}\n\n"
            f"请综合以上多个章节的知识，给出完整、连贯的解答。"
            f"注意章节间的知识点关联和递进关系。公式用LaTeX格式。"
        )
        answer = llm.invoke(prompt).content
        return {"answer": answer, "chapter": "cross", "chapters": related[:5]}

    def multimodal_ask(self, question: str, image_paths: list[str]) -> dict:
        """多模态问答：支持图片输入"""
        route = self._route(question)
        if route is None or route == "general":
            from ingestion.ocr import FormulaOCR
            ocr = FormulaOCR()
            answer = ocr.multimodal_ask(question, image_paths)
            return {"answer": answer, "chapter": "general", "chapters": []}

        if route == "cross":
            related = self._get_related_chapters(question)
            primary = related[0] if related else self._get_chapter_names()[0]
        else:
            primary = route
            related = self._get_related_chapters(question)[:4]

        if primary not in self._chapter_agents:
            self._chapter_agents[primary] = ChapterAgent(primary, self.vector_store)

        answer = self._chapter_agents[primary].ask_with_images(
            question, image_paths, additional_chapters=related
        )
        return {"answer": answer, "chapter": primary, "chapters": [primary] + related}

    def search_all_chapters(self, question: str) -> dict[str, list]:
        outcome = self.vector_store.search_all(question)
        if outcome.status == "failed":
            raise RuntimeError(f"chapter retrieval failed: {outcome.failures}")
        return outcome.items
