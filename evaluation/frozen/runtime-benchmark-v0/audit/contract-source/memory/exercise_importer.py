"""Low-cost exercise candidate analysis and optional LLM repair.

The default path is deterministic: split imported text, score candidate blocks,
and attach heuristic labels. LLM repair is opt-in and only targets low-confidence
blocks after OCR/text extraction has already happened.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


@dataclass
class CandidateBlock:
    text: str
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    start_index: int = 0
    end_index: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExerciseCandidate:
    id: str
    question_text: str
    answer: str = ""
    explanation: str = ""
    source: str = ""
    subject: str = ""
    chapter: str = ""
    suggested_type: str = ""
    difficulty: int = 3
    tags: list[str] = field(default_factory=list)
    linked_concepts: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)
    needs_llm: bool = False
    needs_review: bool = True
    refined_by_llm: bool = False
    split_confidence: float = 0.0
    split_reasons: list[str] = field(default_factory=list)
    validation_issues: list[str] = field(default_factory=list)
    duplicate_of: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


CONCEPT_KEYWORDS: dict[str, list[str]] = {
    "\u6781\u9650": ["\u6781\u9650", "lim", "\u8d8b\u4e8e", "\u65e0\u7a77\u5c0f", "\u65e0\u7a77\u5927"],
    "\u5bfc\u6570": ["\u5bfc\u6570", "\u6c42\u5bfc", "\u5fae\u5206", "derivative", "\u5207\u7ebf", "\u6cd5\u7ebf"],
    "\u79ef\u5206": ["\u79ef\u5206", "\u5b9a\u79ef\u5206", "\u4e0d\u5b9a\u79ef\u5206", "\u539f\u51fd\u6570", "\u6362\u5143", "\u5206\u90e8\u79ef\u5206"],
    "\u77e9\u9635": ["\u77e9\u9635", "\u884c\u5217\u5f0f", "\u7279\u5f81\u503c", "\u7279\u5f81\u5411\u91cf", "\u79e9", "\u9006\u77e9\u9635"],
    "\u6982\u7387": ["\u6982\u7387", "\u968f\u673a\u53d8\u91cf", "\u5206\u5e03", "\u671f\u671b", "\u65b9\u5dee", "\u5bc6\u5ea6\u51fd\u6570"],
    "\u4f18\u5316": ["\u4f18\u5316", "\u6700\u4f18", "\u76ee\u6807\u51fd\u6570", "\u7ea6\u675f", "\u89c4\u5212", "\u6781\u503c", "\u62c9\u683c\u6717\u65e5"],
    "\u7ebf\u6027\u89c4\u5212": ["\u7ebf\u6027\u89c4\u5212", "\u5355\u7eaf\u5f62", "\u53ef\u884c\u57df", "\u57fa\u53d8\u91cf", "\u975e\u57fa\u53d8\u91cf"],
    "\u52a8\u6001\u89c4\u5212": ["\u52a8\u6001\u89c4\u5212", "\u72b6\u6001\u8f6c\u79fb", "\u6700\u4f18\u5b50\u7ed3\u6784", "\u9636\u6bb5", "\u9012\u63a8"],
    "\u56fe\u8bba": ["\u56fe", "\u8def\u5f84", "\u6700\u77ed\u8def", "\u751f\u6210\u6811", "\u7f51\u7edc", "\u8282\u70b9", "\u8fb9"],
    "\u6392\u961f\u8bba": ["\u6392\u961f", "\u5230\u8fbe\u7387", "\u670d\u52a1\u7387", "\u6cca\u677e", "\u7b49\u5f85\u65f6\u95f4"],
}

TYPE_RULES: list[tuple[str, list[str]]] = [
    ("\u5224\u65ad\u9898", ["\u5224\u65ad", "\u6b63\u786e", "\u9519\u8bef", "\u5bf9\u9519", "\u221a", "\u00d7"]),
    ("\u8bc1\u660e\u9898", ["\u8bc1\u660e", "\u8bc1\uff1a", "\u8bd5\u8bc1", "show that", "prove"]),
    ("\u7b80\u7b54\u9898", ["\u7b80\u8ff0", "\u8bf4\u660e", "\u89e3\u91ca", "\u5206\u6790", "\u4e3a\u4ec0\u4e48", "\u542b\u4e49"]),
    ("\u8ba1\u7b97\u9898", ["\u8ba1\u7b97", "\u6c42", "\u89e3", "\u786e\u5b9a", "\u6700\u4f18\u89e3", "\u6700\u5c0f", "\u6700\u5927"]),
]

QUESTION_START_RE = re.compile(
    "(?m)^\\s*(?:\u7b2c\\s*\\d+\\s*\u9898|\\d+\\s*[\\.\u3001\uff0e\\)]|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+\\s*[\u3001\uff0e\\.])\\s*"
)
OPTION_RE = re.compile("(?:^|\\s|[\uff08(])[A-D]\\s*[\\.\u3001\uff0e\\)]", re.IGNORECASE)
SUBQUESTION_RE = re.compile("(?:\\(\\s*\\d+\\s*\\)|\uff08\\s*\\d+\\s*\uff09)")
MATH_RE = re.compile("(\\\\frac|\\\\sum|\\\\int|\\\\lim|[=<>\u2264\u2265\u2248]|\\$|\\^|_)")

S_CHOICE = "\u9009\u62e9\u9898"
S_COMPOSITE = "\u7efc\u5408\u9898"
S_UNKNOWN = "\u672a\u786e\u5b9a"
NUMBERED_ENTRY_RE = re.compile(r"(?m)^\s*(?:第\s*(\d+)\s*题|(\d+)\s*[\.、．\)])\s*")


def _normalize_import_text(raw_text: str) -> str:
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text


def _score_split_block(text: str, *, numbered: bool, fallback_blank: bool) -> tuple[float, list[str]]:
    clean = text.strip()
    reasons: list[str] = []
    confidence = 0.25

    if numbered:
        confidence += 0.35
        reasons.append("detected question-number boundary")
    elif fallback_blank:
        confidence += 0.15
        reasons.append("no stable numbering; split by blank lines")

    if len(clean) >= 30:
        confidence += 0.1
    else:
        confidence -= 0.12
        reasons.append("short block; may be incomplete")

    option_count = len(OPTION_RE.findall(clean))
    if option_count >= 3:
        confidence += 0.12
        reasons.append("detected multiple choice options")

    if SUBQUESTION_RE.search(clean):
        confidence += 0.05

    if len(QUESTION_START_RE.findall(clean)) > 1:
        confidence -= 0.18
        reasons.append("multiple question numbers remain in one block")

    if len(clean) > 2500:
        confidence -= 0.18
        reasons.append("long block; may contain multiple questions")

    if not re.search("[\u3002\uff1f?\uff1b;]|[A-D]\\s*[\\.\u3001\uff0e\\)]|=|\u6c42|\u8bc1|\u8ba1\u7b97|\u5224\u65ad|\u8bf4\u660e", clean):
        confidence -= 0.08
        reasons.append("missing obvious exercise markers")

    confidence = round(max(0.05, min(0.98, confidence)), 2)
    return confidence, reasons


def split_candidate_blocks(raw_text: str, limit: int = 200) -> list[CandidateBlock]:
    """Split imported text into question-like blocks and score split confidence."""
    text = _normalize_import_text(raw_text)
    if not text:
        return []

    blocks: list[CandidateBlock] = []
    starts = [m.start() for m in QUESTION_START_RE.finditer(text)]
    if starts:
        starts.append(len(text))
        for index in range(len(starts) - 1):
            start = starts[index]
            end = starts[index + 1]
            chunk = text[start:end].strip()
            if len(chunk) < 4:
                continue
            confidence, reasons = _score_split_block(chunk, numbered=True, fallback_blank=False)
            blocks.append(CandidateBlock(chunk, confidence, reasons, start, end))
            if len(blocks) >= limit:
                return blocks
        if blocks:
            return blocks

    cursor = 0
    for part in re.split(r"\n\s*\n", text):
        chunk = part.strip()
        if not chunk:
            cursor += len(part) + 2
            continue
        start = text.find(chunk, cursor)
        end = start + len(chunk) if start >= 0 else cursor + len(chunk)
        confidence, reasons = _score_split_block(chunk, numbered=False, fallback_blank=True)
        blocks.append(CandidateBlock(chunk, confidence, reasons, max(start, 0), max(end, 0)))
        cursor = end
        if len(blocks) >= limit:
            break

    return blocks


def split_candidate_text(raw_text: str, limit: int = 200) -> list[str]:
    """Split pasted/imported text into question-like chunks using numbering cues."""
    return [block.text for block in split_candidate_blocks(raw_text, limit=limit)]


def _coerce_block(value: str | CandidateBlock) -> tuple[str, float, list[str]]:
    if isinstance(value, CandidateBlock):
        return value.text, value.confidence, list(value.reasons)
    return str(value), 0.0, []


def _concept_links_from_tags(tags: Iterable[str], *, source: str = "heuristic", confidence: float = 0.72) -> list[dict]:
    links: list[dict] = []
    for tag in tags:
        clean = str(tag).strip()
        if not clean:
            continue
        links.append({
            "name": clean,
            "confidence": max(0.05, min(0.99, confidence)),
            "source": source,
            "evidence": "exercise import candidate",
        })
    return links


def analyze_candidate(
    question_text: str,
    *,
    source: str = "",
    subject: str = "",
    chapter: str = "",
    known_concepts: Iterable[str] | None = None,
    split_confidence: float = 0.0,
    split_reasons: Iterable[str] | None = None,
) -> ExerciseCandidate:
    text = question_text.strip()
    lowered = text.lower()
    reasons: list[str] = []
    tags: list[str] = []
    linked_concepts: list[dict] = []

    suggested_type = ""
    if len(OPTION_RE.findall(text)) >= 3:
        suggested_type = S_CHOICE
        reasons.append("detected A/B/C/D options")
    else:
        for qtype, keywords in TYPE_RULES:
            if any(keyword.lower() in lowered for keyword in keywords):
                suggested_type = qtype
                reasons.append(f"matched question type: {qtype}")
                break
    if not suggested_type:
        suggested_type = S_COMPOSITE if len(SUBQUESTION_RE.findall(text)) >= 2 else S_UNKNOWN
        if suggested_type == S_COMPOSITE:
            reasons.append("detected multiple subquestions")

    concept_scores: dict[str, int] = {}
    for concept, keywords in CONCEPT_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword.lower() in lowered)
        if score:
            concept_scores[concept] = score

    for concept in known_concepts or []:
        clean = concept.strip()
        if clean and clean.lower() in lowered:
            concept_scores[clean] = max(concept_scores.get(clean, 0), 2)

    for concept, score in sorted(concept_scores.items(), key=lambda item: item[1], reverse=True)[:5]:
        tags.append(concept)
        linked_concepts.append({
            "name": concept,
            "confidence": min(0.95, 0.55 + score * 0.12),
            "source": "heuristic",
            "evidence": "keyword match in question text",
        })
    if tags:
        reasons.append("inferred concept tags from keywords")

    difficulty = 2
    if len(text) > 180:
        difficulty += 1
    if len(SUBQUESTION_RE.findall(text)) >= 2:
        difficulty += 1
    if MATH_RE.search(text):
        difficulty += 1
    if any(word in lowered for word in ["\u8bc1\u660e", "\u6700\u4f18", "\u7ea6\u675f", "\u7279\u5f81\u503c", "\u52a8\u6001\u89c4\u5212"]):
        difficulty += 1
    difficulty = max(1, min(5, difficulty))

    confidence = 0.25
    if suggested_type != S_UNKNOWN:
        confidence += 0.25
    if tags:
        confidence += min(0.3, 0.12 * len(tags))
    if len(text) >= 30:
        confidence += 0.1
    if chapter:
        confidence += 0.05
    if split_confidence:
        confidence = confidence * 0.75 + split_confidence * 0.25
        reasons.extend(split_reasons or [])
    confidence = round(min(0.95, max(0.05, confidence)), 2)

    low_split_confidence = bool(split_confidence and split_confidence < 0.55)
    needs_llm = confidence < 0.65 or not tags or suggested_type == S_UNKNOWN or low_split_confidence
    if needs_llm:
        reasons.append("low confidence; recommend LLM repair or manual review")
    else:
        reasons.append("rule confidence is acceptable for quick review")

    validation_issues: list[str] = []
    option_count = len(OPTION_RE.findall(text))
    if len(text) < 12:
        validation_issues.append("题干过短，可能切分不完整")
    if suggested_type == S_CHOICE and option_count < 3:
        validation_issues.append("选择题选项不足")
    if len(QUESTION_START_RE.findall(text)) > 1:
        validation_issues.append("一个候选块中可能包含多道题")
    if split_confidence and split_confidence < 0.55:
        validation_issues.append("切题边界置信度较低")
    if not tags:
        validation_issues.append("未识别知识点")

    return ExerciseCandidate(
        id=str(uuid.uuid4())[:8],
        question_text=text,
        source=source,
        subject=subject,
        chapter=chapter,
        suggested_type=suggested_type,
        difficulty=difficulty,
        tags=tags,
        linked_concepts=linked_concepts,
        confidence=confidence,
        reasons=reasons,
        needs_llm=needs_llm,
        split_confidence=split_confidence,
        split_reasons=list(split_reasons or []),
        validation_issues=validation_issues,
    )


def analyze_candidates(
    candidates: Iterable[str | CandidateBlock],
    *,
    source: str = "",
    subject: str = "",
    chapter: str = "",
    known_concepts: Iterable[str] | None = None,
    limit: int = 200,
) -> list[ExerciseCandidate]:
    results: list[ExerciseCandidate] = []
    for item in candidates:
        text, split_confidence, split_reasons = _coerce_block(item)
        if text and text.strip():
            results.append(
                analyze_candidate(
                    text,
                    source=source,
                    subject=subject,
                    chapter=chapter,
                    known_concepts=known_concepts,
                    split_confidence=split_confidence,
                    split_reasons=split_reasons,
                )
            )
        if len(results) >= limit:
            break
    return results


def attach_answers_by_number(candidates: list[ExerciseCandidate], raw_answer_text: str) -> int:
    """Attach a separate answer sheet by explicit question numbers only."""
    text = _normalize_import_text(raw_answer_text)
    matches = list(NUMBERED_ENTRY_RE.finditer(text))
    answers: dict[str, str] = {}
    for index, match in enumerate(matches):
        number = match.group(1) or match.group(2) or ""
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = text[match.end():end].strip()
        value = re.sub(r"^\s*(?:答案|答)\s*[:：]?\s*", "", value).strip()
        if number and value:
            answers[number] = value

    paired = 0
    for candidate in candidates:
        match = NUMBERED_ENTRY_RE.match(candidate.question_text)
        number = (match.group(1) or match.group(2) or "") if match else ""
        answer = answers.get(number, "")
        if answer:
            candidate.answer = answer
            candidate.validation_issues = [issue for issue in candidate.validation_issues if issue != "答案文件中未找到匹配答案"]
            paired += 1
        elif "答案文件中未找到匹配答案" not in candidate.validation_issues:
            candidate.validation_issues.append("答案文件中未找到匹配答案")
    return paired


def _clean_json_payload(raw: str) -> Any:
    from utils.thinking_filter import strip_thinking

    text = strip_thinking(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,??;?]", value) if item.strip()]
    return []


def _clamp_difficulty(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = fallback
    return max(1, min(5, parsed))


def _candidate_from_llm_item(item: dict, base: ExerciseCandidate, index: int, known_concepts: Iterable[str] | None) -> ExerciseCandidate | None:
    text = str(item.get("question_text") or item.get("question") or "").strip()
    if len(text) < 4:
        return None

    refined = analyze_candidate(
        text,
        source=base.source,
        subject=base.subject,
        chapter=base.chapter,
        known_concepts=known_concepts,
        split_confidence=max(base.split_confidence, 0.72),
        split_reasons=["LLM checked block boundary"],
    )
    refined.id = base.id if index == 0 else f"{base.id}-{index + 1}"
    refined.answer = str(item.get("answer") or "").strip()
    refined.explanation = str(item.get("explanation") or "").strip()
    refined.suggested_type = str(item.get("suggested_type") or item.get("question_type") or refined.suggested_type).strip() or refined.suggested_type
    refined.difficulty = _clamp_difficulty(item.get("difficulty"), refined.difficulty)

    llm_tags = _as_string_list(item.get("tags") or item.get("concepts"))
    if llm_tags:
        refined.tags = llm_tags[:8]
        refined.linked_concepts = _concept_links_from_tags(refined.tags, source="llm_import_repair", confidence=0.78)

    llm_confidence = item.get("confidence")
    try:
        confidence = float(llm_confidence)
    except Exception:
        confidence = max(refined.confidence, 0.72)
    refined.confidence = round(max(refined.confidence, min(0.95, confidence)), 2)
    refined.needs_llm = refined.confidence < 0.65 or not refined.tags
    refined.needs_review = True
    refined.refined_by_llm = True
    refined.reasons = [
        *base.reasons[:4],
        "LLM repaired low-confidence import block",
        str(item.get("reason") or "").strip(),
    ]
    refined.reasons = [reason for reason in refined.reasons if reason]
    if refined.needs_llm:
        refined.reasons.append("LLM repair still needs manual review")
    return refined


def _build_repair_prompt(targets: list[ExerciseCandidate], *, known_concepts: Iterable[str] | None = None) -> str:
    blocks = [
        {
            "id": candidate.id,
            "subject": candidate.subject,
            "chapter": candidate.chapter,
            "confidence": candidate.confidence,
            "reasons": candidate.reasons[:5],
            "text": candidate.question_text[:3000],
        }
        for candidate in targets
    ]
    known = [str(item).strip() for item in (known_concepts or []) if str(item).strip()]
    return f"""
You are cleaning imported exam exercise text blocks. The text has already gone through Word/PDF/OCR extraction and a first rule-based split.
Only repair low-confidence blocks: fix line breaks, split clearly merged questions, and label type, difficulty, and concepts.
Do not invent questions or solve them. Fill answer/explanation only when they already appear in the input text; otherwise leave them empty.

Known concept candidates: {json.dumps(known, ensure_ascii=False)}
Blocks JSON:
{json.dumps(blocks, ensure_ascii=False, indent=2)}

Return only a JSON array. Each item must be:
{{
  "source_id": "original block id",
  "question_text": "complete cleaned question text",
  "answer": "optional",
  "explanation": "optional",
  "suggested_type": "选择题/判断题/计算题/证明题/简答题/综合题/未确定",
  "difficulty": 1,
  "tags": ["concept"],
  "confidence": 0.0,
  "reason": "brief repair note"
}}
""".strip()


def refine_low_confidence_candidates(
    candidates: Iterable[ExerciseCandidate],
    *,
    known_concepts: Iterable[str] | None = None,
    max_items: int = 20,
) -> list[ExerciseCandidate]:
    """Use the text LLM to repair only low-confidence imported candidates."""
    items = list(candidates)
    targets = [candidate for candidate in items if candidate.needs_llm][:max(0, max_items)]
    if not targets:
        return items

    try:
        from config import get_llm

        prompt = _build_repair_prompt(targets, known_concepts=known_concepts)
        raw = get_llm(temperature=0.2).invoke(prompt).content
        payload = _clean_json_payload(raw)
        if not isinstance(payload, list):
            raise ValueError("LLM did not return a JSON array")
    except Exception as exc:
        for candidate in targets:
            candidate.reasons.append(f"LLM repair failed: {exc}")
        return items

    by_id = {candidate.id: candidate for candidate in targets}
    grouped: dict[str, list[ExerciseCandidate]] = {}
    for raw_item in payload:
        if not isinstance(raw_item, dict):
            continue
        source_id = str(raw_item.get("source_id") or raw_item.get("id") or "").strip()
        base = by_id.get(source_id)
        if not base:
            continue
        index = len(grouped.get(source_id, []))
        refined = _candidate_from_llm_item(raw_item, base, index, known_concepts)
        if refined:
            grouped.setdefault(source_id, []).append(refined)

    if not grouped:
        for candidate in targets:
            candidate.reasons.append("LLM returned no usable repair result; kept rule candidate")
        return items

    output: list[ExerciseCandidate] = []
    for candidate in items:
        replacements = grouped.get(candidate.id)
        if replacements:
            output.extend(replacements)
        else:
            output.append(candidate)
    return output
