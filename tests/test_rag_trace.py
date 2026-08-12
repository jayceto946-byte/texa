import backend.rag_trace as trace
import sqlite3


def test_rag_trace_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr(trace, "TRACE_DB_PATH", tmp_path / "traces.db")
    trace.save_trace({
        "request_id": "req-1",
        "book_name": "demo",
        "question": "what is x",
        "intent": "definition",
        "fast_path": True,
        "status": "done",
        "ttft_ms": 120.5,
        "total_ms": 300.0,
        "timings": {"retrieve": 50.0},
        "evidence": [{"chunk_id": "c1", "chapter": "one", "text": "must not persist"}],
    })

    rows = trace.list_traces()
    assert rows[0]["request_id"] == "req-1"
    assert rows[0]["fast_path"] is True
    assert rows[0]["timings"]["retrieve"] == 50.0
    assert rows[0]["evidence"] == [{
        "chunk_id": "c1", "chapter": "one", "section_title": "", "source": "", "score": None,
    }]


def test_resolver_method_runtime_stats_do_not_claim_accuracy(monkeypatch, tmp_path):
    monkeypatch.setattr(trace, "TRACE_DB_PATH", tmp_path / "traces.db")
    trace.save_trace({
        "request_id": "req-method", "status": "done", "timings": {}, "evidence": [],
        "context": {"resolution": {
            "method": "unresolved_reference", "resolution_action": "clarify",
        }},
    })
    result = trace.resolver_method_runtime_stats()
    assert result["metric_kind"] == "runtime_outcomes_not_accuracy"
    assert result["methods"][0]["clarification_rate"] == 1.0


def test_context_trace_v2_round_trip_is_bounded(monkeypatch, tmp_path):
    monkeypatch.setattr(trace, "TRACE_DB_PATH", tmp_path / "traces.db")
    trace.save_trace({
        "request_id": "req-context",
        "question": "它的条件呢？",
        "intent": "condition",
        "status": "done",
        "timings": {},
        "evidence": [],
        "context": {
            "resolution": {
                "raw_query": "它的条件呢？",
                "resolved_query": "拉格朗日中值定理的成立条件是什么？",
                "is_followup": True,
                "resolution_changed": True,
                "method": "deterministic_anaphora",
                "confidence": 0.94,
                "confidence_kind": "rule_strength",
                "speech_act": "followup",
                "state_operations": [{"operation": "set_topic", "value": "拉格朗日中值定理"}],
                "referenced_entity": "拉格朗日中值定理",
                "referenced_entities": ["拉格朗日中值定理"],
                "referenced_turn_ids": ["turn-1"],
                "semantic_resolver": {"attempted": True, "error": "timeout"},
                "state_before": {"topic": "拉格朗日中值定理", "entities": ["拉格朗日中值定理"]},
                "state_after": {"topic": "拉格朗日中值定理", "intent": "condition"},
            },
            "retrieval": {
                "action": "full",
                "query": "拉格朗日中值定理的成立条件是什么？",
                "reused_evidence_ids": [],
                "new_evidence_ids": ["chunk-1"],
                "support_status": "supported",
                "status": "ok",
            },
            "conversation_context": {
                "budget": 2800,
                "char_count": 620,
                "state_chars": 240,
                "recent_turns_chars": 380,
                "current_topic": "拉格朗日中值定理",
                "question_dimension": "condition",
                "speech_act": "followup",
                "constraints": [],
                "turn_ids": ["turn-1"],
                "artifact_targets": [],
                "summary_used": False,
                "evidence_action": "full",
                "reused_evidence_refs": [],
                "new_evidence_refs": ["E1"],
                "text": "must not persist",
            },
            "context_budget": {
                "budget_unit": "chars",
                "assembly_mode": "textbook_grounded",
                "assembled_prompt_chars": 4200,
                "prompt_body": "must not persist",
            },
            "versions": {
                "model_name": "deepseek-v4-pro",
                "prompt_version": "prompt-v3",
                "corpus_version": "book-v1",
            },
        },
    })

    row = trace.list_traces()[0]
    context = row["context"]
    assert context["version"] == 2
    assert context["resolution"]["resolved_query"] == "拉格朗日中值定理的成立条件是什么？"
    assert context["resolution"]["resolution_action"] == "continue"
    assert context["resolution"]["speech_act"] == "followup"
    assert context["resolution"]["state_operations"] == [
        {"operation": "set_topic", "value": "拉格朗日中值定理"},
    ]
    assert context["resolution"]["state_before"]["topic"] == "拉格朗日中值定理"
    assert context["resolution"]["semantic_attempted"] is True
    assert context["resolution"]["semantic_error"] == "timeout"
    assert context["retrieval"]["new_evidence_ids"] == ["chunk-1"]
    assert context["conversation_context"]["turn_ids"] == ["turn-1"]
    assert context["conversation_context"]["new_evidence_refs"] == ["E1"]
    assert "text" not in context["conversation_context"]
    assert context["context_budget"]["assembled_prompt_chars"] == 4200
    assert "prompt_body" not in context["context_budget"]
    assert context["versions"]["prompt_version"] == "prompt-v3"
    assert context["versions"]["corpus_version"] == "book-v1"


def test_context_trace_v2_migrates_v1_database(monkeypatch, tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE rag_traces (request_id TEXT PRIMARY KEY, created_at REAL NOT NULL, conversation_id TEXT, book_name TEXT, question TEXT, intent TEXT, fast_path INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, ttft_ms REAL, total_ms REAL, timings_json TEXT NOT NULL, evidence_json TEXT NOT NULL, error TEXT)")
        conn.execute("PRAGMA user_version = 1")
        conn.execute("INSERT INTO rag_traces VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
            "legacy", 1.0, "", "", "q", "qa", 0, "done", None, 1.0, "{}", "[]", "",
        ))
    monkeypatch.setattr(trace, "TRACE_DB_PATH", path)

    rows = trace.list_traces()

    assert rows[0]["request_id"] == "legacy"
    assert rows[0]["context"] == {}
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        columns = {row[1] for row in conn.execute("PRAGMA table_info(rag_traces)")}
    assert "context_json" in columns
