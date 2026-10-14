"""Deterministic textbook-vs-general routing before Planner execution."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from config import PROGRESS_PATH
from graph.safe_retrieval import get_safe_kg
from ingestion.lexical_index import index_path, search_book
from utils.subject_catalog import normalize_subject_value, subject_matches


_EXPLICIT_TEXTBOOK_SIGNALS = (
    "根据教材", "按照教材", "依据教材", "教材中", "教材里", "教材有没有",
    "本书", "这本书", "书中", "课本中", "课本里", "原文",
)
_LATIN_LITERAL_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_.+\-]{2,})(?![A-Za-z0-9_])")
_DEFINITION_PATTERNS = (
    re.compile(r"^(?:请|帮我|再)?(?:解释(?:一下)?|说明(?:一下)?|介绍(?:一下)?|讲(?:一下)?|什么是)\s*(.+?)[？?。！!]*$"),
    re.compile(r"^(.+?)\s*(?:是什么|是什么意思|的定义是什么)[？?。！!]*$"),
)
ANSWER_MODES = {
    "auto",
    "textbook_grounded",
    "subject_general",
    "global_general",
}


@dataclass(frozen=True)
class AnswerScopeDecision:
    answer_mode: str
    use_textbook_context: bool
    reason: str

    @property
    def requires_scope_confirmation(self) -> bool:
        return self.answer_mode == "subject_mismatch"


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _lexical_index_available(book_name: str) -> bool:
    try:
        return index_path(book_name).exists()
    except OSError:
        return False


def _literals_supported_by_book(book_name: str, literals: list[str]) -> bool | None:
    if not _lexical_index_available(book_name):
        return None
    try:
        hits = search_book(book_name, " ".join(literals), k=4)
    except Exception:
        return None
    evidence = "\n".join(
        str(item.get("content") or item.get("retrieval_text") or "").lower()
        for item in hits
    )
    return any(literal.lower() in evidence for literal in literals)


def _book_concept_match(book_name: str, question: str) -> bool:
    kg, error = get_safe_kg(book_name)
    if error or not getattr(kg, "_is_local", False):
        return False
    try:
        matches = kg.search_concept(question, k=5)
    except Exception:
        return False
    return any(float(score) >= 65 for score, _concept in matches)


def _definition_anchor(question: str) -> str:
    compact = re.sub(r"\s+", "", str(question or "").strip())
    for pattern in _DEFINITION_PATTERNS:
        match = pattern.match(compact)
        if match:
            return match.group(1).strip("，,。！？?：:；;（）()\"'“”")
    return ""


def _anchor_supported_by_book(book_name: str, anchor: str) -> bool | None:
    if not anchor or len(anchor) < 2 or not _lexical_index_available(book_name):
        return None
    try:
        hits = search_book(book_name, anchor, k=3)
    except Exception:
        return None
    normalized_anchor = _normalized(anchor)
    return any(
        normalized_anchor in _normalized(item.get("content") or item.get("retrieval_text") or "")
        for item in hits
    )


def _subject_books(subject: str) -> list[str]:
    selected = normalize_subject_value(subject)
    if not selected:
        return []
    root = Path(PROGRESS_PATH)
    if not root.exists():
        return []
    result: list[str] = []
    for child in root.iterdir():
        metadata_path = child / "metadata.json"
        if not child.is_dir() or not metadata_path.exists():
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(metadata, dict) or metadata.get("status") == "archived":
            continue
        if subject_matches(str(metadata.get("subject") or ""), selected):
            result.append(str(metadata.get("storage_name") or metadata.get("book_name") or child.name))
    return list(dict.fromkeys(result))


def _subject_anchor_support(subject: str, question: str) -> bool | None:
    """Validate only strong explicit anchors against all local books in a subject.

    ``False`` means at least one healthy subject index was checked and none
    contained the literal/definition anchor. ``None`` means the question or
    local resources are insufficient for a deterministic boundary decision.
    """
    books = _subject_books(subject)
    if not books:
        return None

    literals = list(dict.fromkeys(match.group(1) for match in _LATIN_LITERAL_RE.finditer(question)))
    if literals:
        checks = [_literals_supported_by_book(book, literals) for book in books]
        if any(value is True for value in checks):
            return True
        if any(value is False for value in checks):
            return False

    anchor = _definition_anchor(question)
    if anchor:
        checks = [_anchor_supported_by_book(book, anchor) for book in books]
        if any(value is True for value in checks):
            return True
        if any(value is False for value in checks):
            return False
    return None


def _decide_textbook_context(
    question: str,
    resolved_question: str,
    *,
    book_name: str,
    subject_suggestion: dict | None = None,
) -> tuple[bool, str]:
    """Return a conservative scope decision and a trace-safe reason.

    The selected book remains the default for ambiguous Chinese questions. Only
    strong deterministic evidence may bypass it: an accepted subject mismatch,
    or distinctive literals/definition anchors that are absent from a healthy
    local lexical index. Explicit textbook requests and resolved follow-ups win.
    """
    original = str(question or "").strip()
    resolved = str(resolved_question or original).strip()
    if not book_name:
        return False, "no_selected_book"
    if subject_suggestion is not None:
        return False, "subject_mismatch"
    if any(signal in original or signal in resolved for signal in _EXPLICIT_TEXTBOOK_SIGNALS):
        return True, "explicit_textbook_request"
    if resolved != original:
        return True, "resolved_session_followup"
    if _book_concept_match(book_name, resolved):
        return True, "book_concept_match"

    literals = list(dict.fromkeys(match.group(1) for match in _LATIN_LITERAL_RE.finditer(resolved)))
    if literals:
        supported = _literals_supported_by_book(book_name, literals)
        if supported is True:
            return True, "book_literal_match"
        if supported is False:
            return False, "external_literal_absent"

    anchor = _definition_anchor(resolved)
    if anchor:
        supported = _anchor_supported_by_book(book_name, anchor)
        if supported is True:
            return True, "book_definition_match"
        if supported is False:
            return False, "definition_anchor_absent"

    return True, "selected_book_default"


def decide_answer_scope(
    question: str,
    resolved_question: str,
    *,
    book_name: str,
    subject: str = "",
    subject_suggestion: dict | None = None,
    requested_mode: str = "auto",
) -> AnswerScopeDecision:
    """Resolve grounding source and subject boundary as independent semantics."""
    requested = str(requested_mode or "auto").strip().lower()
    if requested not in ANSWER_MODES:
        requested = "auto"
    if requested == "global_general":
        return AnswerScopeDecision("global_general", False, "requested_global_general")
    if requested == "subject_general":
        mode = "subject_general" if str(subject or "").strip() else "global_general"
        return AnswerScopeDecision(mode, False, "requested_subject_general")
    if requested == "textbook_grounded":
        if book_name:
            return AnswerScopeDecision("textbook_grounded", True, "requested_textbook_grounded")
        mode = "subject_general" if str(subject or "").strip() else "global_general"
        return AnswerScopeDecision(mode, False, "requested_textbook_without_book")

    if subject_suggestion is not None:
        return AnswerScopeDecision("subject_mismatch", False, "known_subject_mismatch")

    original = str(question or "").strip()
    resolved = str(resolved_question or original).strip()
    if not book_name:
        if subject:
            support = _subject_anchor_support(subject, resolved)
            if support is False:
                return AnswerScopeDecision("subject_mismatch", False, "subject_anchor_absent")
            return AnswerScopeDecision("subject_general", False, "no_selected_book")
        return AnswerScopeDecision("global_general", False, "no_subject_or_book")

    use_textbook, reason = _decide_textbook_context(
        original,
        resolved,
        book_name=book_name,
        subject_suggestion=None,
    )
    if use_textbook and reason != "selected_book_default":
        return AnswerScopeDecision("textbook_grounded", True, reason)

    if subject:
        support = _subject_anchor_support(subject, resolved)
        if support is False:
            return AnswerScopeDecision("subject_mismatch", False, "subject_anchor_absent")
        if support is True and reason == "selected_book_default":
            return AnswerScopeDecision("subject_general", False, "subject_match_without_book_evidence")
        if use_textbook:
            return AnswerScopeDecision("textbook_grounded", True, reason)
        return AnswerScopeDecision("subject_general", False, "book_miss_subject_general")
    if use_textbook:
        return AnswerScopeDecision("textbook_grounded", True, reason)
    return AnswerScopeDecision("global_general", False, reason)
