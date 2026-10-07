"""反馈闭环 — 用户反馈 → 更新策略 → 优化检索"""
from memory.study_memory import StudyMemory


class FeedbackLoop:
    """学习反馈闭环

    用户反馈 → 更新掌握度 → 调整检索策略 → 优化教学
    """

    def __init__(self, book_name: str):
        self.memory = StudyMemory(book_name)

    def process_feedback(self, chapter: str, rating: int,
                         comment: str = "",
                         knowledge_point: str = "") -> dict:
        """处理用户反馈

        Args:
            rating: 1-5 评分
            chapter: 关联章节
            comment: 文字反馈
            knowledge_point: 知识点评分

        Returns:
            更新后的掌握度信息
        """
        from memory.spaced_repetition import SpacedRepetition
        sr = SpacedRepetition(self.memory.book_name)

        quality = {
            5: 5, 4: 4, 3: 3, 2: 1, 1: 0,
        }.get(rating, 3)

        kp = knowledge_point or f"{chapter}_feedback_{rating}"
        card_id = f"{chapter}::{kp}"
        sr.add_knowledge_point(card_id, chapter, kp)
        sr.review(card_id, quality)

        self.memory.add_chat("feedback", f"rating={rating}, comment={comment}", chapter)

        return {
            "chapter": chapter,
            "rating": rating,
            "quality": quality,
            "due_reviews": len(sr.get_due_reviews()),
            "mastery": sr.get_stats().get("mastered", 0),
        }

    def get_study_summary(self) -> dict:
        return self.memory.get_stats()

    def get_review_schedule(self) -> list[dict]:
        return self.memory.get_due_reviews()
