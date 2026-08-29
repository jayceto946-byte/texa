"""检索Agent层 — 包装三个检索器供LangGraph调用（保持向后兼容）"""
from ingestion.vector_store import get_vector_store
from knowledge.knowledge_graph import get_kg
from memory.study_memory import StudyMemory


class RetrievalAgents:
    """三个检索Agent的联合访问"""

    def __init__(self, book_name: str):
        self.vector_store = get_vector_store()
        self.kg = get_kg(book_name)
        self.memory = StudyMemory(book_name)

    def search_chapter(self, chapter: str, query: str, k: int = 6) -> list[str]:
        outcome = self.vector_store.search_chapter(chapter, query, k=k)
        if outcome.status == "failed":
            raise RuntimeError(f"chapter retrieval failed: {outcome.failures}")
        return [d.page_content for d in outcome.items]

    def search_concepts(self, query: str, k: int = 5) -> list[dict]:
        outcome = self.vector_store.search_all(query, k=2)
        if outcome.status == "failed":
            raise RuntimeError(f"concept retrieval failed: {outcome.failures}")
        results = []
        for ch, docs in outcome.items.items():
            for d in docs:
                results.append({
                    "chapter": ch,
                    "content": d.page_content[:300],
                    "chunk_id": d.metadata.get("chunk_id", ""),
                })
        return results[:k]

    def search_history(self, chapter: str = "", limit: int = 10) -> list[dict]:
        return self.memory.get_chapter_chat(chapter, limit=limit) if chapter else []

    def get_weakness(self) -> list[str]:
        return self.memory.get_weakness()

    def find_knowledge_path(self, concept: str) -> list[str]:
        return self.kg.find_path(concept)

    def find_related_concepts(self, concept: str) -> list[str]:
        return self.kg.find_related(concept)
