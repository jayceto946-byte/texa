"""Compare Texa teaching-prompt presets with Qwen 3.7 Plus on A/B/G.

The fixture is rebuilt once from production state, then copied into all prompt
presets. Previous Minimal results are reused only when every message hash is an
exact match. Raw answers and request telemetry remain in the JSON artifact.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graph.generator import _build_generate_messages
from graph.teaching_prompts import (
    LEGACY_TEACHING_PROMPT_VERSION,
    MINIMAL_TEACHING_PROMPT_VERSION,
    REFINED_TEACHING_PROMPT,
    REFINED_TEACHING_PROMPT_VERSION,
    active_teaching_prompt_version,
)
from scripts.benchmark_qwen37_vs_deepseek_v4pro import (
    OUTPUT as PREVIOUS_OUTPUT,
    _first_secret,
    _hash_messages,
    _invoke,
    _score,
)

OUTPUT = ROOT / "benchmark_results" / "qwen37_prompt_presets_abg_20260825.json"
FIXTURE_OUTPUT = ROOT / "benchmark_results" / "qwen37_prompt_presets_abg_fixture_20260825.json"
PRESETS = ("legacy", "refined", "minimal")
MODEL = "qwen3.7-plus"


def _messages_for(state: dict[str, Any], preset: str) -> tuple[list[dict[str, str]], dict[str, Any], str]:
    previous = os.environ.get("TEXA_TEACHING_PROMPT_MODE")
    os.environ["TEXA_TEACHING_PROMPT_MODE"] = preset
    try:
        working = copy.deepcopy(state)
        messages = [
            {"role": "system" if index == 0 else "user", "content": str(item.content)}
            for index, item in enumerate(_build_generate_messages(working))
        ]
        return messages, dict(working.get("context_budget") or {}), active_teaching_prompt_version()
    finally:
        if previous is None:
            os.environ.pop("TEXA_TEACHING_PROMPT_MODE", None)
        else:
            os.environ["TEXA_TEACHING_PROMPT_MODE"] = previous


def build_fixture() -> dict[str, Any]:
    if not PREVIOUS_OUTPUT.exists():
        raise RuntimeError(f"frozen source fixture is missing: {PREVIOUS_OUTPUT}")
    previous = json.loads(PREVIOUS_OUTPUT.read_text(encoding="utf-8"))
    rows = []
    for source in (previous.get("fixture") or {}).get("cases") or []:
        if source.get("group") not in {"A_textbook_rag", "B_conversation", "G_session"}:
            continue
        if not source.get("model_call"):
            continue
        frozen_messages = copy.deepcopy(source["messages"])
        common_human = frozen_messages[1]["content"]
        intent_match = __import__("re").search(r"## 用户意图\n([^\n]+)", common_human)
        intent = intent_match.group(1).strip() if intent_match else "qa"
        frozen_evidence = str((source.get("evidence_pack") or {}).get("text") or "")
        synthetic_state = {
            "intent": intent,
            "user_input": str(source.get("resolved_query") or source["id"]),
            "answer_mode": "textbook_grounded",
            "use_textbook_context": True,
            "evidence_items": [{
                "chunk_id": "frozen-evidence", "chapter": "frozen",
                "text": frozen_evidence,
            }],
            "chapter_contents": {}, "history_results": [], "teaching_content": "",
            "evidence_support": {"status": source.get("support_status") or "supported"},
        }
        legacy_messages, legacy_budget, _version = _messages_for(synthetic_state, "legacy")
        preset_messages = {
            "legacy": [
                {"role": "system", "content": legacy_messages[0]["content"]},
                {"role": "user", "content": common_human},
            ],
            "refined": [
                {"role": "system", "content": REFINED_TEACHING_PROMPT},
                {"role": "user", "content": common_human},
            ],
            "minimal": frozen_messages,
        }
        versions = {
            "legacy": LEGACY_TEACHING_PROMPT_VERSION,
            "refined": REFINED_TEACHING_PROMPT_VERSION,
            "minimal": MINIMAL_TEACHING_PROMPT_VERSION,
        }
        presets = {}
        for preset, messages in preset_messages.items():
            presets[preset] = {
                "prompt_version": versions[preset],
                "messages": messages,
                "message_sha256": _hash_messages(messages),
                "context_budget": (
                    legacy_budget if preset == "legacy"
                    else dict(source.get("context_budget") or {})
                ),
                "system_chars": len(messages[0]["content"]),
                "human_chars": len(messages[1]["content"]),
            }
        rows.append({
            **{key: copy.deepcopy(value) for key, value in source.items() if key not in {"messages", "message_sha256", "context_budget"}},
            "presets": presets,
        })
    return {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(),
        "model": MODEL,
        "controls": {
            "temperature": 0.1, "thinking": "enabled", "max_tokens": 4096,
            "repeats": 3, "same_frozen_human_payload_across_presets": True,
            "frozen_source": str(PREVIOUS_OUTPUT),
        },
        "cases": rows,
    }


def _key(group: str, case_id: str, preset: str, repeat: int) -> tuple[str, str, str, int]:
    return group, case_id, preset, repeat


def reuse_minimal_results(fixture: dict[str, Any], repeats: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    audit = {"source": str(PREVIOUS_OUTPUT), "eligible": False, "reason": "", "reused": 0}
    if not PREVIOUS_OUTPUT.exists():
        audit["reason"] = "previous artifact missing"
        return [], audit
    previous = json.loads(PREVIOUS_OUTPUT.read_text(encoding="utf-8"))
    old_cases = {
        (row.get("group"), row.get("id")): row
        for row in (previous.get("fixture") or {}).get("cases") or []
    }
    mismatches = []
    for row in fixture["cases"]:
        old = old_cases.get((row["group"], row["id"])) or {}
        if old.get("message_sha256") != row["presets"]["minimal"]["message_sha256"]:
            mismatches.append(f"{row['group']}/{row['id']}")
    if mismatches:
        audit["reason"] = "message hash mismatch"
        audit["mismatches"] = mismatches
        return [], audit
    results = []
    for item in previous.get("results") or []:
        if (
            item.get("model") == MODEL
            and item.get("group") in {"A_textbook_rag", "B_conversation", "G_session"}
            and 1 <= int(item.get("repeat") or 0) <= repeats
        ):
            copied = copy.deepcopy(item)
            copied["preset"] = "minimal"
            copied["reused_from"] = str(PREVIOUS_OUTPUT)
            results.append(copied)
    expected = len(fixture["cases"]) * repeats
    if len(results) != expected:
        audit["reason"] = f"expected {expected} previous Minimal results, found {len(results)}"
        return [], audit
    audit.update({"eligible": True, "reason": "all message hashes matched", "reused": len(results)})
    return results, audit


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _append_log(path: Path, item: dict[str, Any]) -> None:
    log_path = path.with_suffix(path.suffix + ".results.jsonl")
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")


def _load_logged(path: Path) -> list[dict[str, Any]]:
    log_path = path.with_suffix(path.suffix + ".results.jsonl")
    if not log_path.exists():
        return []
    rows = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def _summaries(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for preset in PRESETS:
        rows = [item for item in results if item.get("preset") == preset and not item.get("error")]
        elapsed = [float(item["elapsed_seconds"]) for item in rows if item.get("elapsed_seconds") is not None]
        ttft = [float(item["ttft_seconds"]) for item in rows if item.get("ttft_seconds") is not None]
        usage = {
            key: sum(int((item.get("usage") or {}).get(key) or 0) for item in rows)
            for key in ("input_tokens", "output_tokens", "total_tokens", "reasoning_tokens")
        }
        summary[preset] = {
            "samples": len(rows),
            "errors": len([item for item in results if item.get("preset") == preset and item.get("error")]),
            "median_elapsed_seconds": statistics.median(elapsed) if elapsed else None,
            "median_ttft_seconds": statistics.median(ttft) if ttft else None,
            "median_answer_chars": statistics.median([
                int((item.get("score") or {}).get("answer_chars") or 0) for item in rows
            ]) if rows else None,
            "usage": usage,
            "estimated_cost_cny": round(sum(float((item.get("cost") or {}).get("estimated_amount") or 0) for item in rows), 8),
        }
    return summary


def run_online(fixture: dict[str, Any], output: Path, repeats: int, workers: int) -> dict[str, Any]:
    if not _first_secret(("LLM_CREDENTIAL_QWEN_API_KEY", "DASHSCOPE_API_KEY")):
        raise RuntimeError("missing Qwen credential")
    reused, reuse_audit = reuse_minimal_results(fixture, repeats)
    existing = {_key(item["group"], item["case_id"], item["preset"], int(item["repeat"])): item for item in reused}
    for item in _load_logged(output):
        existing[_key(item["group"], item["case_id"], item["preset"], int(item["repeat"]))] = item
    jobs = []
    for row in fixture["cases"]:
        for preset in PRESETS:
            for repeat in range(1, repeats + 1):
                if _key(row["group"], row["id"], preset, repeat) not in existing:
                    jobs.append((row, preset, repeat))
    results = list(existing.values())
    payload = {
        "schema_version": 1, "status": "running",
        "run_at": datetime.now().astimezone().isoformat(),
        "fixture": fixture, "minimal_reuse_audit": reuse_audit,
        "results": results,
    }
    _write(output, payload)
    total = len(results) + len(jobs)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 6))) as pool:
        futures = {
            pool.submit(_invoke, MODEL, row["presets"][preset]["messages"], repeat): (row, preset, repeat)
            for row, preset, repeat in jobs
        }
        for future in as_completed(futures):
            row, preset, repeat = futures[future]
            try:
                result = future.result()
                result.update({
                    "case_id": row["id"], "group": row["group"], "preset": preset,
                    "score": _score(row, result),
                    "message_sha256": row["presets"][preset]["message_sha256"],
                })
            except Exception as exc:
                result = {
                    "case_id": row["id"], "group": row["group"], "preset": preset,
                    "model": MODEL, "repeat": repeat,
                    "error": f"{type(exc).__name__}: {str(exc)[:1000]}",
                }
            results.append(result)
            _append_log(output, result)
            payload["results"] = results
            payload["progress"] = {"completed": len(results), "total": total}
            _write(output, payload)
            print(
                f"PROMPT_PROGRESS {len(results)}/{total} group={row['group']} "
                f"case={row['id']} preset={preset} repeat={repeat} error={bool(result.get('error'))}",
                flush=True,
            )
    payload.update({"status": "complete", "results": results, "summaries": _summaries(results)})
    _write(output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--fixture-output", type=Path, default=FIXTURE_OUTPUT)
    args = parser.parse_args()
    fixture = build_fixture()
    _write(args.fixture_output, fixture)
    reused, audit = reuse_minimal_results(fixture, args.repeats)
    print(json.dumps({
        "cases": len(fixture["cases"]),
        "calls_per_preset": len(fixture["cases"]) * args.repeats,
        "minimal_reuse_audit": audit,
        "prompt_chars": {
            preset: {
                "median_system": statistics.median(row["presets"][preset]["system_chars"] for row in fixture["cases"]),
                "median_total": statistics.median(
                    row["presets"][preset]["system_chars"] + row["presets"][preset]["human_chars"]
                    for row in fixture["cases"]
                ),
            }
            for preset in PRESETS
        },
    }, ensure_ascii=False, indent=2))
    if args.online:
        report = run_online(fixture, args.output, args.repeats, args.workers)
        print(json.dumps(report["summaries"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
