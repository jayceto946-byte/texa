"""Lazy local prototype ranking, isolated from textbook vector collections."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from backend.services.decision.contracts import DecisionContext, SemanticCandidate, SemanticRanking

_PROTOTYPES = {
    "textbook.search": ("按教材解释这个定义", "查教材中相关例题"),
    "textbook.read": ("读取教材指定章节", "查看教材这一页"),
    "mistake.search_related": ("找相似错题", "查看这道错题的详情"),
    "mistake.manage": ("把这道题加入错题本", "修改错题记录"),
    "learning.inspect": ("查看近期学习活动", "我对这个概念掌握得怎样"),
    "exercise.inspect": ("查找现有习题", "查看练习结果"),
    "exercise.create_set": ("从题库创建练习", "开始一组练习"),
    "exercise.record_result": ("记录练习作答", "保存这道练习结果"),
    "review.manage": ("查看复习队列", "安排复习"),
    "math.verify": ("验证计算结果", "求导并校验"),
}


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


@dataclass
class LocalPrototypeBackend:
    embeddings_factory: Callable
    backend_version: str
    backend_id: str = "local_prototypes"

    def __post_init__(self):
        self._vectors: dict[str, list[list[float]]] | None = None

    def _embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = self.embeddings_factory()
        return embeddings.embed_documents(texts)

    def rank(self, context: DecisionContext, candidates: tuple[str, ...]) -> SemanticRanking:
        if self._vectors is None:
            examples = [(capability, text) for capability in candidates
                        for text in _PROTOTYPES.get(capability, ())]
            vectors = self._embed([text for _, text in examples])
            self._vectors = {}
            for (capability, _), vector in zip(examples, vectors):
                self._vectors.setdefault(capability, []).append(vector)
        question = (context.resolved_query or context.text)[-1200:]
        query = self.embeddings_factory().embed_query(question)
        scored = sorted(((capability, max((_cosine(query, vector) for vector in self._vectors.get(capability, [])), default=0.0))
                         for capability in candidates), key=lambda item: item[1], reverse=True)
        return SemanticRanking(tuple(SemanticCandidate(capability, score, index + 1)
                                     for index, (capability, score) in enumerate(scored)),
                               self.backend_id, self.backend_version)
