"""Conservative subject-scope suggestions for chat turns."""
from __future__ import annotations

import json
import re
import threading
import time
from collections import defaultdict
from pathlib import Path

from config import PROGRESS_PATH
from ingestion.lexical_index import index_path, search_book
from utils.json_io import atomic_write_json
from utils.subject_catalog import normalize_subject_value, read_subject_tree, subject_matches

FEEDBACK_PATH = Path(PROGRESS_PATH) / "subject_routing_feedback.json"
_feedback_lock = threading.RLock()

_PARENT_TERMS = {
    "\u6570\u5b66": {
        "\u6781\u9650", "\u5bfc\u6570", "\u5fae\u5206", "\u79ef\u5206", "\u51fd\u6570", "\u7ea7\u6570", "\u77e9\u9635", "\u884c\u5217\u5f0f", "\u7279\u5f81\u503c",
        "\u6982\u7387", "\u968f\u673a\u53d8\u91cf", "\u5fae\u79ef\u5206", "\u7ebf\u6027\u4ee3\u6570", "\u9ad8\u7b49\u6570\u5b66", "\u4e8c\u6b21\u578b",
    },
    "\u82f1\u8bed": {
        "\u82f1\u8bed", "english", "\u5355\u8bcd", "\u8bcd\u6c47", "\u8bed\u6cd5", "\u957f\u96be\u53e5", "\u9605\u8bfb\u7406\u89e3", "\u5b8c\u5f62\u586b\u7a7a",
        "\u4f5c\u6587", "\u5199\u4f5c", "\u7ffb\u8bd1", "\u8003\u7814\u82f1\u8bed", "vocabulary", "grammar", "translation",
    },
    "\u653f\u6cbb": {
        "\u653f\u6cbb", "\u9a6c\u539f", "\u6bdb\u4e2d\u7279", "\u53f2\u7eb2", "\u601d\u4fee", "\u9a6c\u514b\u601d\u4e3b\u4e49", "\u552f\u7269\u4e3b\u4e49", "\u8fa9\u8bc1\u6cd5",
        "\u4e2d\u56fd\u7279\u8272\u793e\u4f1a\u4e3b\u4e49", "\u8fd1\u4ee3\u53f2", "\u601d\u60f3\u9053\u5fb7", "\u65f6\u653f",
    },
}

_CHILD_TERMS = {
    ("\u6570\u5b66", "\u9ad8\u6570"): {"\u6781\u9650", "\u5bfc\u6570", "\u5fae\u5206", "\u79ef\u5206", "\u51fd\u6570", "\u7ea7\u6570", "\u5fae\u79ef\u5206", "\u9ad8\u7b49\u6570\u5b66"},
    ("\u6570\u5b66", "\u7ebf\u4ee3"): {"\u77e9\u9635", "\u884c\u5217\u5f0f", "\u7279\u5f81\u503c", "\u7279\u5f81\u5411\u91cf", "\u7ebf\u6027\u4ee3\u6570", "\u4e8c\u6b21\u578b", "\u79e9"},
    ("\u6570\u5b66", "\u6982\u7387\u8bba"): {"\u6982\u7387", "\u968f\u673a\u53d8\u91cf", "\u5206\u5e03", "\u671f\u671b", "\u65b9\u5dee", "\u5927\u6570\u5b9a\u5f8b"},
    ("\u82f1\u8bed", "\u9605\u8bfb"): {"\u9605\u8bfb", "\u9605\u8bfb\u7406\u89e3", "\u957f\u96be\u53e5", "\u5b8c\u5f62\u586b\u7a7a"},
    ("\u82f1\u8bed", "\u5199\u4f5c"): {"\u4f5c\u6587", "\u5199\u4f5c", "\u5c0f\u4f5c\u6587", "\u5927\u4f5c\u6587", "essay"},
    ("\u82f1\u8bed", "\u7ffb\u8bd1"): {"\u7ffb\u8bd1", "translation"},
    ("\u82f1\u8bed", "\u8bcd\u6c47"): {"\u5355\u8bcd", "\u8bcd\u6c47", "vocabulary"},
    ("\u653f\u6cbb", "\u9a6c\u539f"): {"\u9a6c\u539f", "\u9a6c\u514b\u601d\u4e3b\u4e49", "\u552f\u7269\u4e3b\u4e49", "\u8fa9\u8bc1\u6cd5"},
    ("\u653f\u6cbb", "\u6bdb\u4e2d\u7279"): {"\u6bdb\u4e2d\u7279", "\u4e2d\u56fd\u7279\u8272\u793e\u4f1a\u4e3b\u4e49", "\u6bdb\u6cfd\u4e1c\u601d\u60f3"},
    ("\u653f\u6cbb", "\u53f2\u7eb2"): {"\u53f2\u7eb2", "\u8fd1\u4ee3\u53f2"},
    ("\u653f\u6cbb", "\u601d\u4fee"): {"\u601d\u4fee", "\u601d\u60f3\u9053\u5fb7", "\u6cd5\u5f8b\u57fa\u7840"},
}


def _contains(text: str, term: str) -> bool:
    if re.fullmatch(r"[a-z0-9_.+-]+", term, flags=re.I):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text, flags=re.I))
    return term in text


def _catalog_paths() -> list[str]:
    paths: list[str] = []
    for node in read_subject_tree():
        parent = str(node.get("name") or "").strip()
        if not parent:
            continue
        paths.append(parent)
        paths.extend(f"{parent}/{str(child).strip()}" for child in node.get("children", []) if str(child).strip())
    return paths


def _book_records() -> list[dict]:
    root = Path(PROGRESS_PATH)
    if not root.exists():
        return []
    records: list[dict] = []
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
        subject = normalize_subject_value(str(metadata.get("subject") or ""))
        if not subject:
            continue
        records.append({
            "name": child.name,
            "display_name": str(metadata.get("display_name") or child.name),
            "subject": subject,
        })
    return records


def _feedback_payload() -> dict:
    try:
        data = json.loads(FEEDBACK_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"routes": {}}
    except Exception:
        return {"routes": {}}


def _route_key(source: str, target: str) -> str:
    normalized_source = normalize_subject_value(source) or "\u672a\u5206\u7c7b"
    return f"{normalized_source}->{normalize_subject_value(target)}"


def _threshold(source: str, target: str) -> float:
    with _feedback_lock:
        route = (_feedback_payload().get("routes") or {}).get(_route_key(source, target), {})
    accepted = int(route.get("accepted") or 0)
    dismissed = int(route.get("dismissed") or 0)
    total = accepted + dismissed
    threshold = 5.0
    if total >= 3 and accepted / total >= 0.7:
        threshold -= 0.5
    if total >= 3 and dismissed / total >= 0.5:
        threshold += 1.0
    return threshold


def record_subject_routing_feedback(source: str, target: str, action: str) -> dict:
    if action not in {"accepted", "dismissed"}:
        raise ValueError("action must be accepted or dismissed")
    key = _route_key(source, target)
    with _feedback_lock:
        payload = _feedback_payload()
        routes = payload.setdefault("routes", {})
        route = routes.setdefault(key, {"accepted": 0, "dismissed": 0})
        route[action] = int(route.get(action) or 0) + 1
        route["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        atomic_write_json(FEEDBACK_PATH, payload)
        return dict(route)


def suggest_subject_scope(question: str, current_subject: str = "", current_book: str = "") -> dict | None:
    """Return a suggestion only when multiple independent signals agree."""
    text = re.sub(r"\s+", " ", str(question or "").strip().lower())
    if len(text) < 2:
        return None
    current_subject = normalize_subject_value(current_subject)
    scores: dict[str, float] = defaultdict(float)
    reasons: dict[str, list[str]] = defaultdict(list)
    paths = _catalog_paths()

    for path in paths:
        parent, _, child = path.partition("/")
        label = child or parent
        if len(label) >= 2 and _contains(text, label.lower()):
            scores[path] += 4.0 if child else 3.0
            reasons[path].append(f"\u95ee\u9898\u4e2d\u51fa\u73b0\u201c{label}\u201d")

    parents = {path.split("/", 1)[0] for path in paths}
    for parent, terms in _PARENT_TERMS.items():
        if parent not in parents:
            continue
        hits = [term for term in terms if _contains(text, term.lower())]
        if hits:
            scores[parent] += min(5.0, 2.2 + 1.1 * len(hits))
            hit_labels = "\u3001".join(sorted(hits)[:3])
            reasons[parent].append(f"\u547d\u4e2d{parent}\u7279\u5f81\u8bcd\uff1a{hit_labels}")

    for (parent, child), terms in _CHILD_TERMS.items():
        path = f"{parent}/{child}"
        if path not in paths:
            continue
        hits = [term for term in terms if _contains(text, term.lower())]
        if hits:
            scores[path] += min(6.0, 2.5 + 1.2 * len(hits))
            hit_labels = "\u3001".join(sorted(hits)[:3])
            reasons[path].append(f"\u66f4\u63a5\u8fd1{child}\uff1a{hit_labels}")

    books = _book_records()
    exact_book = ""
    for book in books:
        names = {book["name"].lower(), book["display_name"].lower()}
        matched = next((name for name in names if len(name) >= 2 and name in text), "")
        if matched:
            scores[book["subject"]] += 6.0
            reasons[book["subject"]].append(f"\u63d0\u5230\u4e86\u6559\u6750\u201c{book['display_name']}\u201d")
            exact_book = book["name"]

    # If explicit terms found nothing, compare a bounded set of local lexical indexes.
    # Requiring two strong hits keeps a single accidental chunk from rerouting a chat.
    if not scores:
        best_by_subject: dict[str, tuple[float, dict]] = {}
        for book in books[:6]:
            if book["subject"] == current_subject:
                continue
            lexical_path = index_path(book["name"])
            try:
                if not lexical_path.exists() or lexical_path.stat().st_size > 8_000_000:
                    continue
            except OSError:
                continue
            hits = search_book(book["name"], question, k=2)
            top_score = float(hits[0].get("bm25_score") or 0) if len(hits) >= 2 else 0.0
            second_score = float(hits[1].get("bm25_score") or 0) if len(hits) >= 2 else 0.0
            if top_score < 6.0 or second_score < top_score * 0.45:
                continue
            previous = best_by_subject.get(book["subject"])
            if previous is None or top_score > previous[0]:
                best_by_subject[book["subject"]] = (top_score, book)
        inferred = sorted(best_by_subject.items(), key=lambda item: item[1][0], reverse=True)
        if inferred and (len(inferred) == 1 or inferred[0][1][0] - inferred[1][1][0] >= 2.0):
            inferred_subject, (inferred_score, inferred_book) = inferred[0]
            scores[inferred_subject] = min(8.0, 3.0 + inferred_score / 2)
            reasons[inferred_subject].append(f"\u6559\u6750\u68c0\u7d22\u66f4\u63a5\u8fd1\u201c{inferred_book['display_name']}\u201d")
            exact_book = inferred_book["name"]

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ranked = [
        (path, score)
        for path, score in ranked
        if path != current_subject and not ("/" not in path and current_subject.startswith(f"{path}/"))
    ]
    if not ranked:
        return None
    target, score = ranked[0]

    # A lightweight local retrieval check validates keyword routing without opening Chroma.
    matching_books = [book for book in books if subject_matches(book["subject"], target)]
    retrieval_hits: list[tuple[float, dict]] = []
    for book in matching_books[:8]:
        lexical_path = index_path(book["name"])
        try:
            if not lexical_path.exists() or lexical_path.stat().st_size > 8_000_000:
                continue
        except OSError:
            continue
        hits = search_book(book["name"], question, k=2)
        if hits:
            retrieval_hits.append((float(hits[0].get("bm25_score") or 0), book))
    retrieval_hits.sort(key=lambda item: item[0], reverse=True)
    if retrieval_hits and retrieval_hits[0][0] >= 1.5:
        score += min(2.0, retrieval_hits[0][0] / 4)
        reasons[target].append(f"\u6559\u6750\u68c0\u7d22\u547d\u4e2d\u201c{retrieval_hits[0][1]['display_name']}\u201d")

    runner_up = max((value for path, value in ranked[1:] if path != target), default=0.0)
    if score < _threshold(current_subject, target) or score - runner_up < 1.5:
        return None

    target_book = exact_book
    if not target_book and len(matching_books) == 1:
        target_book = matching_books[0]["name"]
    elif not target_book and retrieval_hits:
        target_book = retrieval_hits[0][1]["name"]
    confidence = round(min(0.97, 0.55 + score / 20 + min(0.15, (score - runner_up) / 20)), 2)
    return {
        "target_subject": target,
        "target_book_name": target_book,
        "current_subject": current_subject,
        "current_book_name": current_book,
        "confidence": confidence,
        "reason": "\uff1b".join(dict.fromkeys(reasons[target]))[:180],
    }

