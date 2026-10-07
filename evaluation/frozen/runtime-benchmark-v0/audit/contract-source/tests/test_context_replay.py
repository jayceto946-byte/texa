import json

from evaluation.context_replay import (
    collect_candidates_from_messages,
    load_approved_cases,
    redact_text,
    write_jsonl,
)


def test_context_replay_candidates_are_redacted_and_not_goldens(tmp_path):
    messages = [
        {"role": "user", "content": "解释压阻效应"},
        {"role": "assistant", "content": "第一步说明定义。"},
        {"role": "user", "content": "不是低频，改成高频条件下比较，邮箱 a@example.com"},
    ]
    candidates = collect_candidates_from_messages(messages, source_key="conv-secret")
    assert len(candidates) == 1
    item = candidates[0]
    assert item["status"] == "candidate"
    assert "user_correction" in item["tags"]
    assert "constraint" in item["tags"]
    assert "conv-secret" not in json.dumps(item, ensure_ascii=False)
    assert "[REDACTED_EMAIL]" in item["query"]

    path = tmp_path / "replay.jsonl"
    write_jsonl(path, candidates)
    assert load_approved_cases(path) == []


def test_context_replay_loader_requires_approved_schema(tmp_path):
    path = tmp_path / "approved.jsonl"
    path.write_text(json.dumps({
        "schema_version": 1,
        "id": "approved-1",
        "status": "approved",
        "history": [],
        "query": "什么是导数？",
        "book_name": "高等数学",
        "expected": {"required_evidence_points": ["变化率"]},
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    assert [item["id"] for item in load_approved_cases(path)] == ["approved-1"]


def test_context_replay_redacts_tokens_and_paths():
    redacted = redact_text("sk-abcdefghijklmnop C:\\Users\\Jayce\\secret.txt 13800138000")
    assert "sk-" not in redacted
    assert "Jayce" not in redacted
    assert "13800138000" not in redacted
