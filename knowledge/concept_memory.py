"""ConceptMemory — 概念记忆系统

核心能力：
1. 概念提取：每次回答后自动提取涉及的关键概念
2. 接触记录：记录概念出现的时间、频率、上下文
3. 遗忘检测：找出高频但久未接触的概念
4. 学习提醒：在回答末尾附加遗忘提醒

可扩展性（预留接口）：
- weak_points: 关联错题/弱项标记
- review_queue: 周期性复习队列
- mastery_level: 概念掌握度评估

存储结构（JSON）:
{
  "concepts": {
    "概念名": {
      "aliases": ["别名1"],
      "definition": "定义文本",
      "first_seen": "2026-06-04",
      "exposure_count": 3,
      "last_exposed_at": "2026-06-04T15:30:00",
      "mastery_level": 2,        // 1-5，预留
      "weak_flag": false,        // 是否标记为弱项，预留
      "related_concepts": ["相关概念1"],
      "source_chapters": ["第1章"]
    }
  },
  "exposures": [
    {"concept": "概念名", "question": "问题", "intent": "definition", "timestamp": "..."}
  ],
  "review_queue": []  // 预留：周期性复习队列
}
"""
import json
import re
from functools import wraps
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from config import get_llm, PROGRESS_PATH
from utils.json_io import atomic_write_json
from utils.path_safety import safe_book_name, safe_child_path
from utils.state_locks import get_state_lock
from utils.subject_catalog import normalize_subject_value


_CONCEPT_EXTRACT_PROMPT = """从以下考研/学习问答中，提取用户问题明确涉及的关键概念。

你在做穷尽式概念识别（exhaustive concept identification），不是做摘要或重要性排序。

## 回答范围
{scope}

## 问题
{question}

## 回答（前1000字）
{answer}

请输出 JSON 数组（不要其他内容）：
[
  {{
    "name": "概念名",
    "type": "算法/定理/公式/概念/方法",
    "confidence": 0.9,
    "explicit_span": "问题原文中对应的连续文本"
  }}
]
要求：
1. 识别问题中明确提到的每一个独立成立的教材/学习概念。
2. 如果问题并列列出多个概念（如 A、B、C，或“比较 A 和 B”），必须逐项独立判断，
   不要把“最重要的那个”之外的项删掉。每个明确提到的有效学习概念都优先保留。
3. 只提取真正的专业概念，过滤常见词（如"我们""可以""这个"）
4. 优先提取教材中的专有名词
5. 概念名或有效别名必须直接出现在问题原文中，不得只从回答推测概念
6. 不要因为“定义、区别、特点、优点、缺点、应用、原因、总结、比较”等任务词
   出现在并列结构中，就把它们当作概念。
7. 置信度低于 0.5 的不要输出
8. 最多输出 12 个概念
"""



_GENERIC_ALIAS_TERMS = {
    "\u65b9\u6cd5", "\u6b65\u9aa4", "\u8fed\u4ee3", "\u8fed\u4ee3\u6b65\u9aa4", "\u7a0b\u5e8f\u6846\u56fe", "\u539f\u7406", "\u8fc7\u7a0b", "\u7b97\u6cd5", "\u7ea6\u675f", "\u4f18\u5316", "\u4f18\u5316\u65b9\u6cd5", "\u6700\u4f18\u5316\u65b9\u6cd5", "\u95ee\u9898", "\u6761\u4ef6",
    "method", "step", "steps", "algorithm",
}


def _is_strict_confidence(value) -> bool:
    try:
        return float(value) >= 0.85
    except (TypeError, ValueError):
        return False


def _is_direct_question_concept(concept: dict, question: str) -> bool:
    if str(concept.get("source", "")).startswith("mistake_"):
        return True
    question_text = (question or "").lower()
    if not question_text:
        return False
    name = str(concept.get("name", "")).strip()
    aliases = [str(a).strip() for a in concept.get("aliases", []) if str(a).strip()]
    direct_terms = [name, *[a for a in aliases if a not in _GENERIC_ALIAS_TERMS]]
    return any(term and term.lower() in question_text for term in direct_terms)


_EXPLICIT_WEAK_TERMS = {
    "\u4e0d\u4f1a", "\u4e0d\u61c2", "\u6ca1\u61c2", "\u4e0d\u7406\u89e3", "\u6ca1\u7406\u89e3", "\u4e0d\u660e\u767d", "\u6ca1\u660e\u767d",
    "\u641e\u4e0d\u61c2", "\u770b\u4e0d\u61c2", "\u4e0d\u719f", "\u4e0d\u592a\u719f", "\u638c\u63e1\u4e0d\u597d", "\u5bb9\u6613\u9519",
    "\u603b\u662f\u9519", "\u8001\u662f\u9519", "\u8bb0\u4e0d\u4f4f", "\u5fd8\u4e86", "\u8584\u5f31",
}

def has_explicit_weak_signal(question: str) -> bool:
    """Return whether the learner explicitly says they are struggling."""
    text = (question or "").strip().lower()
    return bool(text) and any(term in text for term in _EXPLICIT_WEAK_TERMS)

def _merge_list(old: list, new: list, limit: int = 20) -> list:
    result = []
    for item in list(old or []) + list(new or []):
        if item and item not in result:
            result.append(item)
        if len(result) >= limit:
            break
    return result

def _with_fresh_state(method):
    """Serialize access and refresh snapshots shared by multiple instances."""
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._state_lock:
            self._data = self._load()
            return method(self, *args, **kwargs)
    return wrapped


class ConceptMemory:
    """概念记忆系统"""

    def __init__(self, book_name: str):
        self.book_name = book_name
        self._file = safe_child_path(PROGRESS_PATH, safe_book_name(book_name), "concept_memory.json")
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._state_lock = get_state_lock(self._file)
        with self._state_lock:
            self._data = self._load()

    # ── 存储 ──────────────────────────────────────────────

    def _load(self) -> dict:
        if self._file.exists():
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    return self._normalize_data(json.load(f))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        return self._normalize_data({
            "concepts": {},
            "exposures": [],
            "review_queue": [],
        })

    def _normalize_data(self, data: dict) -> dict:
        if not isinstance(data, dict):
            data = {}
        data.setdefault("concepts", {})
        data.setdefault("exposures", [])
        data.setdefault("review_queue", [])
        data.setdefault("candidate_concepts", {})
        data.setdefault("candidate_exposures", [])
        return data

    def _save(self):
        atomic_write_json(self._file, self._data)

    # ── 概念提取 ──────────────────────────────────────────

    def extract_concepts(
        self,
        question: str,
        answer: str,
        *,
        subject: str = "",
        answer_mode: str = "",
    ) -> list[dict]:
        """用 LLM 从问答中提取概念。返回 [{name, type, confidence}]。"""
        llm = get_llm()
        prompt = _CONCEPT_EXTRACT_PROMPT.format(
            scope=(subject or "跨学科通用") + (f"；模式：{answer_mode}" if answer_mode else ""),
            question=question,
            answer=answer[:1000],
        )
        try:
            resp = llm.invoke(prompt).content.strip()
            if resp.startswith("```"):
                resp = resp.split("\n", 1)[-1].rsplit("\n", 1)[0]
            concepts = json.loads(resp)
            if not isinstance(concepts, list):
                return []
            return [c for c in concepts if isinstance(c, dict) and c.get("confidence", 0) >= 0.5]
        except Exception as e:
            print(f"[ConceptMemory] 提取概念失败: {e}", flush=True)
            return []

    def _extract_concepts_local(self, question: str, answer: str, target_chapters: list[str]) -> list[dict]:
        """本地轻量提取：从检索到的章节名和问题中提取候选概念。
        作为 LLM 提取失败时的 fallback。
        """
        candidates = []
        # 从问题中提取引号内的术语
        quoted = re.findall(r'["""]([^"""]+)["""]', question)
        candidates.extend(quoted)
        # 从章节名中提取
        for ch in target_chapters:
            # 去掉 "第X章" 前缀
            clean = re.sub(r'^第[一二三四五六七八九十\d]+章\s*', '', ch)
            if clean and len(clean) > 1:
                candidates.append(clean)
        # 简单去重
        seen = set()
        result = []
        for c in candidates:
            c = c.strip()
            if c and c not in seen and len(c) >= 2:
                seen.add(c)
                result.append({"name": c, "type": "concept", "confidence": 0.6})
        return result[:5]

    # ── 接触记录 ──────────────────────────────────────────

    @_with_fresh_state
    def log_exposure(
        self,
        concepts: list[dict],
        question: str,
        intent: str = "qa",
        *,
        source: str = "qa",
        weak: bool = False,
        subject: str = "",
        conversation_id: str = "",
        weak_reason: str = "",
    ):
        """记录一次概念接触。"""
        subject = normalize_subject_value(subject)
        concepts = [
            c for c in concepts
            if _is_strict_confidence(c.get("confidence"))
            and _is_direct_question_concept(c, question)
        ]
        if not concepts:
            return

        now = datetime.now().isoformat()
        for c in concepts:
            name = c.get("name", "").strip()
            if not name:
                continue

            # 更新概念库
            if name not in self._data["concepts"]:
                self._data["concepts"][name] = {
                    "aliases": [],
                    "definition": "",
                    "first_seen": now[:10],
                    "exposure_count": 0,
                    "last_exposed_at": now,
                    "mastery_level": 0,
                    "weak_flag": False,
                    "related_concepts": [],
                    "source_chapters": [],
                }

            concept = self._data["concepts"][name]
            concept["concept_id"] = c.get("concept_id", concept.get("concept_id", ""))
            concept["aliases"] = _merge_list(concept.get("aliases", []), c.get("aliases", []))
            if c.get("definition") and not concept.get("definition"):
                concept["definition"] = c.get("definition", "")
            concept["related_concepts"] = _merge_list(
                concept.get("related_concepts", []),
                c.get("related_concepts", []),
            )
            concept["source_chapters"] = _merge_list(
                concept.get("source_chapters", []),
                c.get("source_chapters", []),
            )
            if subject:
                concept["subjects"] = _merge_list(concept.get("subjects", []), [subject])
                concept["last_subject"] = subject
            if weak:
                concept["weak_flag"] = True
                concept["weak_reason"] = weak_reason or source
                concept["last_weak_at"] = now
            concept["exposure_count"] += 1
            concept["last_exposed_at"] = now

            # 记录 exposure 日志
            self._data["exposures"].append({
                "concept": name,
                "concept_id": c.get("concept_id", ""),
                "question": question[:200],
                "intent": intent,
                "source": source,
                "book_name": self.book_name,
                "subject": subject,
                "conversation_id": conversation_id,
                "link_source": c.get("source", ""),
                "weak": weak,
                "confidence": c.get("confidence", 0),
                "evidence": c.get("evidence", "")[:200],
                "timestamp": now,
            })

        # 控制日志大小
        if len(self._data["exposures"]) > 500:
            self._data["exposures"] = self._data["exposures"][-300:]

        self._save()

    @_with_fresh_state
    def log_candidates(
        self,
        concepts: list[dict],
        question: str,
        intent: str = "qa",
        *,
        source: str = "qa_candidate",
        subject: str = "",
        conversation_id: str = "",
        answer: str = "",
        limit: int = 12,
    ):
        """Store low-confidence concept candidates without affecting strict stats."""
        subject = normalize_subject_value(subject)
        now = datetime.now().isoformat()
        saved = 0
        for c in concepts or []:
            if not isinstance(c, dict):
                continue
            name = str(c.get("name", "")).strip()
            if len(name) < 2 or name in _GENERIC_ALIAS_TERMS:
                continue
            item = self._data["candidate_concepts"].setdefault(name, {
                "name": name,
                "type": c.get("type", "concept"),
                "first_seen": now[:10],
                "seen_count": 0,
                "max_confidence": 0,
                "subjects": [],
                "sources": [],
            })
            confidence = c.get("confidence", 0)
            try:
                item["max_confidence"] = max(float(item.get("max_confidence", 0) or 0), float(confidence or 0))
            except (TypeError, ValueError):
                pass
            item["seen_count"] = int(item.get("seen_count", 0) or 0) + 1
            item["last_seen_at"] = now
            item["last_question"] = question[:200]
            item["last_evidence"] = str(c.get("evidence", ""))[:200]
            item["sources"] = _merge_list(item.get("sources", []), [source])
            if subject:
                item["subjects"] = _merge_list(item.get("subjects", []), [subject])

            self._data["candidate_exposures"].append({
                "concept": name,
                "question": question[:200],
                "answer_preview": answer[:300],
                "intent": intent,
                "source": source,
                "book_name": self.book_name,
                "subject": subject,
                "conversation_id": conversation_id,
                "confidence": confidence,
                "evidence": str(c.get("evidence", ""))[:200],
                "timestamp": now,
            })
            saved += 1
            if saved >= limit:
                break

        if not saved:
            return []
        if len(self._data["candidate_exposures"]) > 500:
            self._data["candidate_exposures"] = self._data["candidate_exposures"][-300:]
        self._save()
        return list(self._data["candidate_concepts"].values())

    def log_weakness(self, concepts: list[dict], question: str, intent: str = "qa", source: str = "mistake", subject: str = "", conversation_id: str = ""):
        """记录概念弱项；错题和主动提问定义都进入同一份记忆。"""
        self.log_exposure(concepts, question, intent, source=source, weak=True, subject=subject, conversation_id=conversation_id)

    # ── 遗忘检测 ──────────────────────────────────────────

    @_with_fresh_state
    def get_forgotten(self, days_threshold: int = 7, min_exposures: int = 2, limit: int = 3) -> list[dict]:
        """获取高频但久未接触的概念（疑似遗忘点）。

        Returns:
            [{"name": str, "exposure_count": int, "last_exposed_days_ago": int, "suggestion": str}]
        """
        now = datetime.now()
        results = []

        for name, info in self._data["concepts"].items():
            count = info.get("exposure_count", 0)
            if count < min_exposures:
                continue

            last_str = info.get("last_exposed_at", "")
            try:
                last = datetime.fromisoformat(last_str)
            except (ValueError, TypeError):
                continue

            days_ago = (now - last).days
            if days_ago >= days_threshold:
                results.append({
                    "name": name,
                    "exposure_count": count,
                    "last_exposed_days_ago": days_ago,
                    "suggestion": f"上次接触于 {days_ago} 天前，建议回顾",
                })

        # 按遗忘天数降序
        results.sort(key=lambda x: x["last_exposed_days_ago"], reverse=True)
        return results[:limit]

    # ── 高频概念 ──────────────────────────────────────────

    @_with_fresh_state
    def get_frequent(self, limit: int = 5) -> list[dict]:
        """获取接触频率最高的概念。"""
        items = [
            {"name": name, "exposure_count": info["exposure_count"]}
            for name, info in self._data["concepts"].items()
        ]
        items.sort(key=lambda x: x["exposure_count"], reverse=True)
        return items[:limit]

    # ── 学习提醒 ──────────────────────────────────────────

    @_with_fresh_state
    def enrich_answer(self, answer: str, current_concepts: list[str]) -> str:
        """在回答末尾附加学习提醒。

        策略：
        1. 如果当前涉及的概念中有高频遗忘点，提醒
        2. 如果当前是全新概念，标记为"首次接触"
        """
        reminders = []

        # 检查当前概念中是否有遗忘点
        forgotten = self.get_forgotten(days_threshold=5, limit=3)
        forgotten_names = {f["name"] for f in forgotten}
        overlap = [c for c in current_concepts if c in forgotten_names]
        if overlap:
            reminders.append(f"💡 你最近较少接触：{', '.join(overlap)}，建议抽空回顾")

        # 检查是否有全新概念
        new_concepts = []
        for c in current_concepts:
            if c in self._data["concepts"]:
                if self._data["concepts"][c]["exposure_count"] <= 2:
                    new_concepts.append(c)
        if new_concepts:
            reminders.append(f"🌱 新概念关注：{', '.join(new_concepts)}")

        if not reminders:
            return answer

        return answer + "\n\n---\n\n**📚 学习提醒**\n" + "\n".join(f"- {r}" for r in reminders)

    # ── 可扩展接口（预留）────────────────────────────────

    @_with_fresh_state
    def mark_weak(self, concept_name: str, reason: str = ""):
        """标记概念为弱项（供错题本调用）。"""
        if concept_name in self._data["concepts"]:
            self._data["concepts"][concept_name]["weak_flag"] = True
            self._data["concepts"][concept_name]["weak_reason"] = reason or "manual"
            self._data["concepts"][concept_name]["last_weak_at"] = datetime.now().isoformat()
            self._save()

    def _is_effective_weak(self, concept_name: str, info: dict) -> bool:
        """Ignore legacy QA weak flags created solely from broad intent types."""
        if not info.get("weak_flag"):
            return False
        reason = str(info.get("weak_reason", ""))
        if reason != "qa":
            return True
        return any(
            exposure.get("concept") == concept_name
            and exposure.get("weak")
            and has_explicit_weak_signal(str(exposure.get("question", "")))
            for exposure in self._data.get("exposures", [])
        )

    @staticmethod
    def _reviewed_today(info: dict) -> bool:
        value = str(info.get("last_reviewed_at", ""))
        return bool(value) and value[:10] == datetime.now().date().isoformat()

    @_with_fresh_state
    def get_weak_points(self) -> list[dict]:
        """获取所有标记为弱项的概念（供周期性复习调用）。"""
        return [
            {"name": name, **info}
            for name, info in self._data["concepts"].items()
            if self._is_effective_weak(name, info)
        ]

    @_with_fresh_state
    def mark_reviewed(self, concept_name: str, quality: int = 4, note: str = "") -> dict:
        """记录一次概念复习，供学习页的复习动作调用。"""
        name = concept_name.strip()
        if not name:
            raise ValueError("concept_name is required")
        now = datetime.now().isoformat()
        concept = self._data["concepts"].setdefault(name, {
            "aliases": [],
            "definition": "",
            "first_seen": now[:10],
            "exposure_count": 0,
            "last_exposed_at": now,
            "mastery_level": 0,
            "weak_flag": False,
            "related_concepts": [],
            "source_chapters": [],
        })
        quality = max(0, min(5, int(quality)))
        concept["last_reviewed_at"] = now
        concept["last_review_quality"] = quality
        concept["review_count"] = int(concept.get("review_count", 0) or 0) + 1
        if quality >= 4:
            concept["mastery_level"] = min(5, max(int(concept.get("mastery_level", 0) or 0), quality))
            if concept.get("weak_flag") and quality >= 5:
                concept["weak_flag"] = False
        elif quality <= 2:
            concept["weak_flag"] = True
            concept["weak_reason"] = "review"
            concept["last_weak_at"] = now
        self._data.setdefault("review_events", []).append({
            "concept": name,
            "quality": quality,
            "note": note[:200],
            "timestamp": now,
        })
        if len(self._data["review_events"]) > 300:
            self._data["review_events"] = self._data["review_events"][-200:]
        self._save()
        return {"name": name, **concept}
    @_with_fresh_state
    def get_review_queue(self, limit: int = 5) -> list[dict]:
        """获取复习队列：弱项 + 遗忘点（供周期性回顾调用）。"""
        weak = self.get_weak_points()
        forgotten = self.get_forgotten(days_threshold=3, limit=limit)

        # 合并去重
        seen = set()
        queue = []
        for item in weak + forgotten:
            name = item["name"] if isinstance(item, dict) else item
            info = self._data["concepts"].get(name, {})
            if self._reviewed_today(info):
                continue
            if name not in seen:
                seen.add(name)
                queue.append({"name": name, "reason": "weak" if item in weak else "forgotten"})
        return queue[:limit]

    @_with_fresh_state
    def get_stats(self) -> dict:
        """获取概念记忆统计（供 UI 展示）。"""
        concepts = self._data["concepts"]
        return {
            "total_concepts": len(concepts),
            "total_exposures": len(self._data["exposures"]),
            "weak_count": sum(1 for name, c in concepts.items() if self._is_effective_weak(name, c)),
            "forgotten_count": len(self.get_forgotten(days_threshold=7)),
            "frequent_top3": self.get_frequent(3),
        }
