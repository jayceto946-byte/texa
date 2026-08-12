"""Collect privacy-bounded Context Engineering replay candidates from local chats.

Candidates are deliberately not golden cases.  A human must review the redacted
window and add explicit expectations before a case can enter release evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "eval" / "context_replay_candidates.jsonl"
REPLAY_SCHEMA_VERSION = 1

_SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("user_correction", re.compile(r"不是|改成|改为|我说的是|你理解错|纠正|应当是"), 3),
    ("topic_return", re.compile(r"回到|刚才|前面|之前|第一个话题|继续讲"), 2),
    ("constraint", re.compile(r"条件下|只考虑|不要|仅限|限定|换成|低频|高频"), 2),
    ("assistant_artifact", re.compile(r"第[一二三四五六七八九十\d]+(?:个|步|项|题|行|部分)|前者|后者|这个(?:公式|结论|反例|方法)"), 3),
    ("multi_step", re.compile(r"这一步|上一步|下一步|为什么这里|怎么推出|继续推导"), 2),
    ("ambiguous_reference", re.compile(r"^(?:它|这个|那个|前者|后者|这一步|继续)[呢？?，,。\s]*$"), 3),
)

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:sk|api)[-_][A-Za-z0-9_-]{12,}\b", re.I), "[REDACTED_TOKEN]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[REDACTED_PHONE]"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[REDACTED_ID]"),
    (re.compile(r"https?://\S+", re.I), "[REDACTED_URL]"),
    (re.compile(r"(?:[A-Za-z]:\\|/Users/|/home/)[^\s\]\[()<>\"']+", re.I), "[REDACTED_PATH]"),
)


def redact_text(value: Any, *, limit: int = 4000) -> str:
    text = str(value or "")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.I | re.S)
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip()
    return text[:limit]


def _signal_tags(question: str, *, history_turns: int) -> tuple[list[str], int]:
    tags: list[str] = []
    score = 0
    for tag, pattern, weight in _SIGNAL_PATTERNS:
        if pattern.search(question):
            tags.append(tag)
            score += weight
    if history_turns >= 20:
        tags.append("long_20")
        score += 2
    if history_turns >= 40:
        tags.append("long_40")
        score += 1
    if history_turns >= 80:
        tags.append("long_80")
        score += 1
    return tags, score


def _bounded_history(messages: list[dict], before_index: int, *, max_messages: int) -> list[dict]:
    selected = messages[max(0, before_index - max_messages):before_index]
    return [
        {
            "role": "assistant" if item.get("role") == "assistant" else "user",
            "content": redact_text(item.get("content")),
            "turn_id": f"replay-{offset + 1}",
        }
        for offset, item in enumerate(selected)
        if isinstance(item, dict) and str(item.get("content") or "").strip()
    ]


def collect_candidates_from_messages(
    messages: list[dict],
    *,
    source_key: str,
    subject: str = "",
    book_name: str = "",
    min_score: int = 2,
    max_history_messages: int = 16,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    user_turns = 0
    source_hash = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:16]
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        question = redact_text(message.get("content"), limit=2000)
        if not question:
            continue
        tags, score = _signal_tags(question, history_turns=user_turns)
        if user_turns and score >= min_score:
            candidate_key = f"{source_hash}:{index}:{question}"
            candidates.append({
                "schema_version": REPLAY_SCHEMA_VERSION,
                "id": f"candidate_{hashlib.sha256(candidate_key.encode('utf-8')).hexdigest()[:16]}",
                "status": "candidate",
                "source_hash": source_hash,
                "subject": redact_text(subject, limit=80),
                "book_name": redact_text(book_name, limit=160),
                "history": _bounded_history(
                    messages, index, max_messages=max_history_messages,
                ),
                "query": question,
                "tags": tags,
                "candidate_score": score,
                "expected": {},
                "review_note": "人工确认指代对象、约束、检索要点和禁止漂移项后，将 status 改为 approved。",
            })
        user_turns += 1
    return candidates


def collect_feedback_candidates(*, limit: int = 500) -> list[dict[str, Any]]:
    from backend.conversation_memory import load_full_history
    from backend.services.answer_feedback import list_answer_feedback

    results: list[dict[str, Any]] = []
    for feedback in list_answer_feedback(rating="unhelpful", limit=limit):
        conversation_id = str(feedback.get("conversation_id") or "")
        message_id = str(feedback.get("message_id") or "")
        messages = load_full_history(conversation_id)
        assistant_index = next((
            index for index, item in enumerate(messages)
            if str(item.get("id") or "") == message_id and item.get("role") == "assistant"
        ), -1)
        if assistant_index < 1:
            continue
        user_index = next((
            index for index in range(assistant_index - 1, -1, -1)
            if messages[index].get("role") == "user"
        ), -1)
        if user_index < 0:
            continue
        reasons = [str(value) for value in feedback.get("reasons") or []]
        candidate_key = f"feedback:{feedback.get('feedback_id')}"
        results.append({
            "schema_version": REPLAY_SCHEMA_VERSION,
            "id": f"candidate_{hashlib.sha256(candidate_key.encode('utf-8')).hexdigest()[:16]}",
            "status": "candidate",
            "source_hash": hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:16],
            "subject": redact_text(feedback.get("subject"), limit=80),
            "book_name": redact_text(feedback.get("book_name"), limit=160),
            "history": _bounded_history(messages, user_index, max_messages=16),
            "query": redact_text(messages[user_index].get("content"), limit=2000),
            "observed_answer": redact_text(messages[assistant_index].get("content"), limit=4000),
            "tags": ["answer_feedback", *reasons],
            "candidate_score": 5,
            "feedback_versions": feedback.get("versions") or {},
            "expected": {},
            "review_note": "来自未解决回答反馈；人工补全正确对象、约束和证据要点后方可批准。",
        })
    return results


def collect_local_candidates(
    *, min_score: int = 2, limit: int = 200, include_feedback: bool = True,
) -> list[dict[str, Any]]:
    from backend.conversation_memory import list_conversations, load_full_history

    results: list[dict[str, Any]] = []
    for conversation in list_conversations(limit=limit):
        conversation_id = str(conversation.get("id") or "")
        if not conversation_id:
            continue
        results.extend(collect_candidates_from_messages(
            load_full_history(conversation_id),
            source_key=conversation_id,
            subject=str(conversation.get("subject") or ""),
            book_name=str(conversation.get("book_name") or ""),
            min_score=min_score,
        ))
    if include_feedback:
        results.extend(collect_feedback_candidates(limit=limit))
    by_id = {str(item.get("id") or ""): item for item in results}
    ordered = list(by_id.values())
    ordered.sort(key=lambda item: (-int(item.get("candidate_score") or 0), item["id"]))
    return ordered


def write_jsonl(path: str | Path, items: Iterable[dict[str, Any]]) -> int:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = list(items)
    target.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows),
        encoding="utf-8",
    )
    return len(rows)


def load_approved_cases(path: str | Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = json.loads(line)
        if item.get("status") != "approved":
            continue
        if int(item.get("schema_version") or 0) != REPLAY_SCHEMA_VERSION:
            raise ValueError(f"unsupported replay schema at line {line_number}")
        if not item.get("id") or not item.get("query") or not isinstance(item.get("expected"), dict):
            raise ValueError(f"invalid approved replay case at line {line_number}")
        cases.append(item)
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect redacted context replay candidates.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--min-score", type=int, default=2)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--without-feedback", action="store_true")
    args = parser.parse_args()
    count = write_jsonl(
        args.output,
        collect_local_candidates(
            min_score=max(1, args.min_score),
            limit=max(1, args.limit),
            include_feedback=not args.without_feedback,
        ),
    )
    print(json.dumps({"candidates": count, "output": str(Path(args.output).resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
