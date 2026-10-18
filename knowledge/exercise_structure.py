"""P1-C contracts: question associations and attempt evidence are separate facts.

No graph writes, model calls, mastery updates or scheduling occur here.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def question_digest(record) -> str:
    # Exact text, including corrected OCR/figures, defines this asset version.
    return digest({key: getattr(record, key, {} if key == "visual_ir" else None) for key in
                   ("question_text", "book_id", "subject", "chapter", "image_path", "visual_ir")})


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Selection(Contract):
    concept_id: str = Field(min_length=1, max_length=160)
    basis: str = Field(min_length=1, max_length=600)


class Property(Contract):
    statement: str = Field(min_length=1, max_length=300)
    basis: str = Field(min_length=1, max_length=600)
    concept_id: str | None = None


class NewConcept(Contract):
    name: str = Field(min_length=1, max_length=120)
    basis: str = Field(min_length=1, max_length=600)


class ClassificationProposal(Contract):
    status: Literal["proposed", "unknown", "unclassified"] = "unclassified"
    primary: Selection | None = None
    related: list[Selection] = Field(default_factory=list, max_length=12)
    theorems: list[Selection] = Field(default_factory=list, max_length=8)
    properties: list[Property] = Field(default_factory=list, max_length=8)
    domain: str = Field(default="", max_length=160)
    question_type: str = Field(default="", max_length=120)
    basis: str = Field(default="", max_length=1000)
    uncertainty: str = Field(default="", max_length=1000)
    new_concepts: list[NewConcept] = Field(default_factory=list, max_length=8)


class ErrorEvidence(Contract):
    error_type: Literal["arithmetic", "orientation", "concept", "theorem_application", "procedure", "final_answer_incorrect", "unknown"]
    concept_ids: list[str] = Field(default_factory=list, max_length=8)
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=2000)
    # One-based line in the stored answer. Null means only a final answer.
    step: int | None = Field(default=None, ge=1)
    explanation: str = Field(default="", max_length=1000)


class DiagnosisProposal(Contract):
    errors: list[ErrorEvidence] = Field(default_factory=list, max_length=8)
    uncertainty: str = Field(default="", max_length=1000)


def catalog_from_kg(kg, record, *, book_name: str, limit: int = 40) -> dict:
    """Bound candidates to this graph and exact chapter when available.

    Hash the actual graph projection, rather than trusting model-supplied versions
    or a process cache. Same names/IDs in different books remain separate.
    """
    concepts = getattr(kg, "concepts", []) if getattr(kg, "_is_local", False) else []
    chapters = getattr(kg, "_chunk_to_chapter", {})
    occurrences = getattr(kg, "occurrences", [])
    by_concept: dict[str, set[str]] = {}
    for occurrence in occurrences:
        chapter = chapters.get(occurrence.get("chunk_id"), "")
        if chapter:
            by_concept.setdefault(occurrence.get("concept_id"), set()).add(chapter)
    snapshot = {"concepts": concepts, "occurrences": occurrences, "chapters": chapters,
                "meta": getattr(kg, "meta", {})}
    scope = {"book_name": book_name, "book_id": getattr(record, "book_id", ""),
             "kg_version": digest(snapshot), "chapter": record.chapter or ""}
    query = (record.question_text + " " + " ".join(record.tags)).lower()
    ranked = []
    for concept in concepts:
        cid, name = concept.get("concept_id"), concept.get("canonical_name")
        if not cid or not name:
            continue
        locations = sorted(by_concept.get(cid, set()))
        if record.chapter and record.chapter not in locations:
            continue  # Missing chapter provenance is unknown, never widened.
        terms = [name, *concept.get("aliases", [])]
        score = sum(len(term) for term in terms if term and term.lower() in query)
        ranked.append((score, cid, {"concept_id": cid, "name": name,
                                   "aliases": concept.get("aliases", [])[:8],
                                   "roles": concept.get("roles", []), "chapters": locations}))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return {"scope": scope, "question_digest": question_digest(record),
            "candidates": [item[2] for item in ranked[:max(0, min(limit, 40))]]}


def build_catalog(record, *, book_name: str) -> dict:
    from knowledge.knowledge_graph import KnowledgeGraph
    # Fresh snapshot prevents a replaced active graph from retaining stale IDs.
    directory = KnowledgeGraph._resolve_local_dir(book_name)
    if (directory / f"{book_name}_knowledge_graph.json").is_file():
        kg = KnowledgeGraph(book_name)
    else:
        kg = None
    return catalog_from_kg(kg, record, book_name=book_name)


def validate_classification(payload: dict, catalog: dict, *, analysis: str = "") -> dict:
    proposal = ClassificationProposal.model_validate(payload)
    allowed = {item["concept_id"]: item for item in catalog["candidates"]}
    selected = ([proposal.primary] if proposal.primary else []) + proposal.related + proposal.theorems
    if proposal.status != "proposed" and (selected or proposal.properties):
        raise ValueError("unclassified result cannot assert classifications")
    if proposal.status == "proposed" and not proposal.basis.strip():
        raise ValueError("classification requires basis")
    if proposal.primary and proposal.primary.concept_id in {item.concept_id for item in proposal.related}:
        raise ValueError("primary and related concepts must be distinct")
    for group in (proposal.related, proposal.theorems):
        if len({item.concept_id for item in group}) != len(group):
            raise ValueError("duplicate classification IDs")
    for item in selected + [item for item in proposal.properties if item.concept_id]:
        if item.concept_id not in allowed:
            raise ValueError("concept ID outside candidate scope")
    data = proposal.model_dump()
    for item in ([data["primary"]] if data["primary"] else []) + data["related"] + data["theorems"]:
        item["name"] = allowed[item["concept_id"]]["name"]
    return {"schema_version": 1, **data, "scope": catalog["scope"],
            "question_digest": catalog["question_digest"], "analysis_digest": digest(analysis),
            "verification": "unverified", "new_concepts_status": "pending_review"}


def classification_ids(structure: dict) -> set[str]:
    if structure.get("schema_version") != 1 or structure.get("status") != "proposed":
        return set()
    items = ([structure["primary"]] if structure.get("primary") else []) + structure.get("related", []) + structure.get("theorems", [])
    return {item["concept_id"] for item in items}


def invalidate_structure(record) -> None:
    if record.knowledge_structure and record.knowledge_structure.get("question_digest") != question_digest(record):
        record.knowledge_structure = {**record.knowledge_structure, "status": "stale"}


def validate_diagnosis(payload: dict, *, record, attempt: dict, catalog: dict) -> dict:
    proposal = DiagnosisProposal.model_validate(payload)
    if attempt.get("question_revision") != record.content_revision:
        raise ValueError("attempt question revision changed")
    if attempt.get("result") not in {"wrong", "partial"} or attempt.get("judgement_source") not in {"user_confirmed", "deterministic"}:
        raise ValueError("diagnosis requires a confirmed unsuccessful attempt")
    answer = attempt.get("answer", "")
    allowed = {item["concept_id"]: item for item in catalog["candidates"]}
    lines = answer.splitlines(keepends=True)
    for error in proposal.errors:
        if answer[error.start:error.end] != error.quote or error.end > len(answer):
            raise ValueError("diagnosis evidence must match stored answer span")
        if set(error.concept_ids) - allowed.keys():
            raise ValueError("diagnosis concept outside candidate scope")
        if len(error.concept_ids) != len(set(error.concept_ids)):
            raise ValueError("duplicate diagnosis concept IDs")
        if error.error_type in {"final_answer_incorrect", "unknown"}:
            if error.concept_ids:
                raise ValueError("unknown cause cannot identify weak concepts")
        else:
            if error.step is None or len(lines) < 2 or error.step > len(lines):
                raise ValueError("specific cause requires an evidenced working step")
            line_start = sum(len(line) for line in lines[:error.step - 1])
            if not (line_start <= error.start < error.end <= line_start + len(lines[error.step - 1])):
                raise ValueError("step does not contain evidence span")
    return {"schema_version": 1, **proposal.model_dump(), "attempt_id": attempt["id"],
            "question_revision": record.content_revision, "question_digest": question_digest(record),
            "answer_digest": digest(answer), "scope": catalog["scope"], "status": "suggested",
            "concept_names": {cid: allowed[cid]["name"] for error in proposal.errors for cid in error.concept_ids}}


def confirmed_diagnoses(record, attempts: list[dict]) -> list[tuple[dict, dict]]:
    """Historical/manual tags are retained but cannot become evidence facts."""
    facts = []
    seen = set()
    for attempt in attempts:
        diagnosis = attempt.get("diagnosis") or {}
        aid = attempt.get("id")
        if (aid and aid not in seen and diagnosis.get("schema_version") == 1
                and diagnosis.get("confirmed_by") == "user" and diagnosis.get("status") == "confirmed"
                and diagnosis.get("attempt_id") == aid
                and diagnosis.get("question_digest") == question_digest(record)
                and diagnosis.get("answer_digest") == digest(attempt.get("answer", ""))
                and diagnosis.get("question_revision") == attempt.get("question_revision") == record.content_revision
                and attempt.get("result") in {"wrong", "partial"}
                and attempt.get("judgement_source") in {"user_confirmed", "deterministic"}):
            facts.append((attempt, diagnosis))
            seen.add(aid)
    return facts


ERROR_LABELS = {
    "arithmetic": "算术计算错误", "orientation": "方向判断错误", "concept": "概念理解错误",
    "theorem_application": "定理应用错误", "procedure": "解题步骤错误",
    "final_answer_incorrect": "最终答案错误", "unknown": "错因未知",
}


def diagnosis_search_terms(record, attempts: list[dict]) -> list[str]:
    terms = []
    for _, diagnosis in confirmed_diagnoses(record, attempts):
        terms.extend(diagnosis.get("concept_names", {}).values())
        for error in diagnosis["errors"]:
            terms.extend([error["error_type"], ERROR_LABELS[error["error_type"]], *error["concept_ids"]])
    return terms


def weak_summary(records_and_attempts) -> dict:
    concepts, reasons, attempts_seen = {}, {}, set()
    for record, attempts in records_and_attempts:
        if record.visibility != "active" or record.content_status == "needs_correction":
            continue
        for attempt, diagnosis in confirmed_diagnoses(record, attempts):
            key = (record.id, attempt["id"])
            if key in attempts_seen:
                continue
            attempts_seen.add(key)
            scope = diagnosis["scope"]
            ids = {cid for error in diagnosis["errors"] for cid in error["concept_ids"]}
            for cid in ids:
                group_key = (scope["book_name"], scope["book_id"], scope["kg_version"], cid)
                group = concepts.setdefault(group_key, {"type": "知识点", "name": diagnosis["concept_names"][cid],
                    "concept_id": cid, "scope": scope, "count": 0, "attempt_ids": [], "mistake_ids": []})
                group["count"] += 1
                group["attempt_ids"].append(attempt["id"])
                if record.id not in group["mistake_ids"]:
                    group["mistake_ids"].append(record.id)
            for reason in {error["error_type"] for error in diagnosis["errors"] if error["error_type"] != "unknown"}:
                group = reasons.setdefault(reason, {"type": "错因", "name": ERROR_LABELS[reason], "error_type": reason, "example": next(error["quote"] for error in diagnosis["errors"] if error["error_type"] == reason)[:180], "count": 0, "attempt_ids": [], "mistake_ids": []})
                group["count"] += 1
                group["attempt_ids"].append(attempt["id"])
                if record.id not in group["mistake_ids"]:
                    group["mistake_ids"].append(record.id)
    return {"concepts": list(concepts.values()), "reasons": list(reasons.values()),
            "confirmed_error_attempts": len(attempts_seen), "basis": "confirmed_attempt_evidence"}
