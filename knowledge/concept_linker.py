"""Concept linking helpers.

This module maps question/answer/chunk/tag text to canonical concepts in the
prebuilt knowledge graph. It is intentionally lightweight: KG matches and
alias mentions come first, and LLM extraction can remain an optional fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from knowledge.knowledge_graph import get_kg


@dataclass
class ConceptCandidate:
    name: str
    concept_id: str = ""
    type: str = "concept"
    confidence: float = 0.0
    source: str = ""
    evidence: str = ""
    aliases: list[str] | None = None
    roles: list[str] | None = None
    definition: str = ""
    related_concepts: list[str] | None = None
    source_chapters: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "concept_id": self.concept_id,
            "type": self.type,
            "confidence": round(float(self.confidence), 3),
            "confidence_kind": "heuristic_association",
            "evidence_kind": "question_association",
            "source": self.source,
            "evidence": self.evidence,
            "aliases": self.aliases or [],
            "roles": self.roles or [],
            "definition": self.definition,
            "related_concepts": self.related_concepts or [],
            "source_chapters": self.source_chapters or [],
        }


class ConceptLinker:
    """Resolve raw learning text to canonical KG concepts."""

    _WEAK_INTENTS = {
        "definition",
        "formula",
        "property",
        "derivation",
        "comparison",
        "application",
    }

    def __init__(self, book_name: str):
        self.book_name = book_name
        self.kg = get_kg(book_name)

    def link(
        self,
        *,
        question: str = "",
        answer: str = "",
        chunks: Iterable[str] | None = None,
        matched_concepts: Iterable[str] | None = None,
        tags: Iterable[str] | None = None,
        intent: str = "qa",
        limit: int = 8,
    ) -> list[dict]:
        if not getattr(self.kg, "_is_local", False):
            return []

        candidates: dict[str, ConceptCandidate] = {}

        for name in matched_concepts or []:
            self._add_resolved(candidates, name, 1.0, "kg_matched", question)

        for name in tags or []:
            self._add_search(candidates, name, 0.86, "tag", name)

        if question:
            self._add_search(candidates, question, 0.9, "question", question)
            self._add_mentions(candidates, question, 0.78, "question_mention")

        chunk_text = "\n".join(chunks or [])
        if chunk_text:
            self._add_mentions(candidates, chunk_text[:6000], 0.68, "chunk_mention")

        if answer:
            self._add_mentions(candidates, answer[:3000], 0.58, "answer_mention")

        if intent in self._WEAK_INTENTS:
            for item in candidates.values():
                if item.source in {"kg_matched", "question", "question_mention"}:
                    item.confidence = min(1.0, item.confidence + 0.05)

        ranked = sorted(
            candidates.values(),
            key=lambda c: (c.confidence, len(c.evidence or ""), c.name),
            reverse=True,
        )
        return [c.to_dict() for c in ranked[:limit]]

    def _add_search(
        self,
        candidates: dict[str, ConceptCandidate],
        query: str,
        base_confidence: float,
        source: str,
        evidence: str,
    ) -> None:
        for score, concept in self.kg.search_concept(query, k=5):
            confidence = min(1.0, base_confidence * (float(score) / 100.0))
            if confidence < 0.45:
                continue
            self._add_concept(candidates, concept, confidence, source, evidence)

    def _add_resolved(
        self,
        candidates: dict[str, ConceptCandidate],
        name: str,
        confidence: float,
        source: str,
        evidence: str,
    ) -> None:
        detail = self.kg.get_concept_detail(name)
        if detail:
            self._add_concept(candidates, detail["concept"], confidence, source, evidence)

    def _add_mentions(
        self,
        candidates: dict[str, ConceptCandidate],
        text: str,
        confidence: float,
        source: str,
    ) -> None:
        if not text:
            return
        lowered = text.lower()
        hit_count = 0
        for concept in self.kg.concepts:
            terms = [concept.get("canonical_name", ""), *concept.get("aliases", [])]
            terms = sorted({t.strip() for t in terms if len(t.strip()) >= 2}, key=len, reverse=True)
            hit = next((t for t in terms if t.lower() in lowered), "")
            if not hit:
                continue
            boost = min(0.12, len(hit) / 80)
            self._add_concept(
                candidates,
                concept,
                min(1.0, confidence + boost),
                source,
                self._evidence_window(text, hit),
            )
            hit_count += 1
            if hit_count >= 20:
                break

    def _add_concept(
        self,
        candidates: dict[str, ConceptCandidate],
        concept: dict,
        confidence: float,
        source: str,
        evidence: str,
    ) -> None:
        cid = concept.get("concept_id", "")
        name = concept.get("canonical_name", "")
        if not cid or not name:
            return

        wiki = self.kg.get_concept_wiki(name, max_chunks=1, max_related=6)
        existing = candidates.get(cid)
        if existing and existing.confidence >= confidence:
            return

        candidates[cid] = ConceptCandidate(
            name=name,
            concept_id=cid,
            type=self._infer_type(concept),
            confidence=confidence,
            source=source,
            evidence=(evidence or "")[:240],
            aliases=concept.get("aliases", []),
            roles=concept.get("roles", []),
            definition=wiki.get("definition", ""),
            # Exclude unverified directional edges from learning records.
            related_concepts=[],
            source_chapters=wiki.get("source_chapters", []),
        )

    def _infer_type(self, concept: dict) -> str:
        roles = set(concept.get("roles", []))
        if "theorem" in roles:
            return "theorem"
        if "formula" in roles:
            return "formula"
        if "algorithm" in roles:
            return "algorithm"
        if "definition" in roles:
            return "concept"
        return "concept"

    def _evidence_window(self, text: str, term: str, radius: int = 80) -> str:
        idx = text.lower().find(term.lower())
        if idx < 0:
            return term
        start = max(0, idx - radius)
        end = min(len(text), idx + len(term) + radius)
        return text[start:end].strip()
