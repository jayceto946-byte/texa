"""章节专家Agent - 基于RAG的章节问答 + 多模态支持"""
import base64
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from config import get_llm, get_llm_client, get_model_role_config, MULTIMODAL_ENABLED
from ingestion.vector_store import ChapterVectorStore

CHAPTER_QA_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是一个考研辅导专家，精通以下章节的内容。\n\n"
        "## 章节：{chapter_title}\n\n"
        "## 参考资料\n{context}\n\n"
        "## 回答要求\n"
        "1. 基于参考资料回答问题，如果资料不足以回答，请明确说明\n"
        "2. 用中文回答，保持清晰准确\n"
        "3. 对于数学/公式问题，使用LaTeX格式（$$...$$）展示公式\n"
        "4. 适当引用参考内容中的关键信息\n"
        "5. 如果用户的问题涉及解题步骤，给出详细推导过程",
    ),
    ("human", "{question}"),
])


class ChapterAgent:
    """单个章节的专家Agent"""

    def __init__(self, chapter_title: str, vector_store: ChapterVectorStore):
        self.chapter_title = chapter_title
        self.vector_store = vector_store
        self.llm = get_llm()
        self.chain = self._build_chain()

    def _build_chain(self):
        def retrieve(q: dict) -> str:
            outcome = self.vector_store.search_chapter(
                self.chapter_title, q["question"], k=6
            )
            if outcome.status == "failed":
                return f"（章节「{self.chapter_title}」检索失败）"
            docs = outcome.items
            if not docs:
                return f"（章节「{self.chapter_title}」中没有找到相关信息）"
            return "\n\n".join(
                f"[片段{i+1}] {d.page_content}" for i, d in enumerate(docs)
            )

        chain = (
            RunnablePassthrough.assign(context=retrieve)
            | CHAPTER_QA_PROMPT
            | self.llm
            | StrOutputParser()
        )
        return chain

    def ask(self, question: str) -> str:
        return self.chain.invoke({
            "question": question,
            "chapter_title": self.chapter_title,
        })

    def retrieve_context(self, question: str, k: int = 6) -> str:
        outcome = self.vector_store.search_chapter(self.chapter_title, question, k=k)
        if outcome.status == "failed":
            return ""
        docs = outcome.items
        if not docs:
            return ""
        return "\n\n".join(
            f"[片段{i+1}] {d.page_content}" for i, d in enumerate(docs)
        )

    def ask_with_images(self, question: str, image_paths: list[str],
                        additional_chapters: list[str] = None) -> str:
        """多模态问答：文本 + 图片 + 多章节上下文"""
        if not MULTIMODAL_ENABLED:
            return self.ask(question)

        client = get_llm_client("vision")
        if client is None:
            return self.ask(question)

        model = get_model_role_config("vision").model

        context = self.retrieve_context(question)

        if additional_chapters:
            for ch in additional_chapters:
                if ch != self.chapter_title:
                    outcome = self.vector_store.search_chapter(ch, question, k=3)
                    docs = outcome.items if outcome.status != "failed" else []
                    if docs:
                        context += "\n\n## 关联章节「" + ch + "」\n"
                        context += "\n\n".join(d.page_content for d in docs)

        content = [
            {"type": "text", "text": (
                f"你是一个考研辅导专家。\n\n"
                f"## 当前章节：{self.chapter_title}\n\n"
                f"## 参考资料\n{context}\n\n"
                f"## 用户问题\n{question}\n\n"
                f"请结合上下文和图片给出详细解答。公式用LaTeX格式。"
            )},
        ]

        for img_path in image_paths:
            ext = Path(img_path).suffix.lower().replace(".", "")
            if ext == "jpg":
                ext = "jpeg"
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/{ext};base64,{b64}"}
            })

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
        )
        return resp.choices[0].message.content
