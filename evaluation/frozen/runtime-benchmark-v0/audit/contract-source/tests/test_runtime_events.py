from __future__ import annotations

import json

import pytest

from backend.services.runtime_events import (
    RuntimeEventStore, RuntimeEventWriter, make_event, observe_execution_event,
    replay, text_fingerprint,
)


def test_runtime_event_schema_rejects_content_and_paths(tmp_path):
    question = "我的 API key 是 secret；教材正文很长"
    event = make_event("user_input", session_id="s1", turn_id="t1",
                       payload=text_fingerprint(question))
    encoded = json.dumps(event, ensure_ascii=False)
    assert question not in encoded and "secret" not in encoded
    assert event["app_version"] and event["runtime_version"] and event["router_version"]
    for payload in ({"question": question}, {"source_refs": ["/Users/private/book.pdf"]},
                    {"model_id": "my key is secret"}):
        if "source_refs" in payload:
            assert make_event("retrieval", session_id="s1", payload=payload)["payload"]["source_refs"] == []
        else:
            with pytest.raises(ValueError):
                make_event("user_input", session_id="s1", payload=payload)


def test_runtime_event_async_replay_state_chain_and_session(tmp_path):
    store = RuntimeEventStore(tmp_path / "events.db")
    writer = RuntimeEventWriter(store)
    first = make_event("state", session_id="s1", turn_id="t1", payload={"task_status": "running"})
    decision = make_event("decision", session_id="s1", turn_id="t1",
                          parent_event_id=first["event_id"], payload={"route": "legacy_chat"})
    result = make_event("execution_result", session_id="s1", turn_id="t1",
                        parent_event_id=decision["event_id"], payload={"task_status": "completed"})
    second_turn = make_event("user_input", session_id="s1", turn_id="t2", payload={"input_chars": 3})
    for event in (first, decision, result, second_turn):
        writer.submit(event)
    writer.flush()
    turn = replay(session_id="s1", turn_id="t1", store=store)
    assert [item["type"] for item in turn["events"]] == ["state", "decision", "execution_result"]
    assert turn["state"]["task_status"] == "completed"
    assert all(item["parent_present"] for item in turn["chain"])
    assert len(replay(session_id="s1", store=store)["events"]) == 4
    first_page = replay(session_id="s1", limit=2, store=store)
    assert first_page["truncated"] is True
    second_page = replay(session_id="s1", after_event_id=first_page["next_cursor"], limit=2, store=store)
    assert [item["type"] for item in second_page["events"]] == ["execution_result", "user_input"]
    writer.stop()


def test_execution_projection_keeps_only_refs(monkeypatch):
    captured = []
    monkeypatch.setattr("backend.services.runtime_events.emit", lambda *args, **kwargs: captured.append((args, kwargs)))
    observe_execution_event({"type": "tool_result", "phase": "tool", "kind": "tool",
                             "status": "completed", "operation_id": "tool:math",
                             "conversation_id": "s1", "turn_id": "t1", "request_id": "r1",
                             "payload": {"tool_id": "math.verify", "tool_status": "succeeded",
                                         "answer": "sensitive result", "args": {"api_key": "secret"}}})
    assert captured[0][0] == ("tool_call",)
    assert captured[0][1]["payload"] == {"phase": "tool", "status": "completed",
                                           "tool_id": "math.verify", "result_status": "succeeded",
                                           "operation_id": "tool:math"}


def test_agent_runtime_audit_only_after_commit(tmp_path, monkeypatch):
    from backend.services.agent_runtime.contracts import RunCommand
    from backend.services.agent_runtime.store import RuntimeStore

    runtime = RuntimeStore(tmp_path / "agent.db")
    snapshot = runtime.create(RunCommand("key", "request", "task", "session", "turn",
                                         "goal", "owner"))
    observed = []
    monkeypatch.setattr("backend.services.runtime_events.observe_execution_event", observed.append)
    with pytest.raises(RuntimeError, match="rollback"):
        with runtime._write() as conn:
            row = conn.execute("SELECT * FROM agent_runs WHERE id=?", (snapshot["run"]["id"],)).fetchone()
            runtime._event(conn, row, lifecycle="tool.started", status="started")
            raise RuntimeError("rollback")
    assert observed == []
    assert [event["payload"]["lifecycle"] for event in runtime.events(snapshot["run"]["id"])] == ["run.created"]


def test_rotation_keeps_unfinished_turn_and_storage_validates_schema(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.services.runtime_events._MAX_ROWS", 3)
    store = RuntimeEventStore(tmp_path / "events.db")
    old = make_event("user_input", session_id="s", turn_id="old")
    finished = make_event("execution_result", session_id="s", turn_id="old",
                          parent_event_id=old["event_id"])
    active = make_event("state", session_id="s", turn_id="active")
    next_event = make_event("decision", session_id="s", turn_id="active")
    store.append_many([old, finished, active, next_event])
    assert [event["type"] for event in store.list(session_id="s")] == ["state", "decision"]
    with pytest.raises(ValueError, match="unapproved"):
        store.append_many([{**active, "payload": {"api_key": "secret"}}])


def test_legacy_diagnostic_trace_redacts_secrets(monkeypatch, tmp_path):
    import backend.rag_trace as rag_trace

    monkeypatch.setattr(rag_trace, "TRACE_DB_PATH", tmp_path / "rag.db")
    rag_trace.save_trace({"request_id": "req", "conversation_id": "s",
                          "question": "key sk-abcdefghijklmnop from alice@example.com /Users/alice/book.pdf",
                          "error": "token=verysecret123 at /home/alice/data.txt",
                          "context": {"retrieval": {"query": "alice@example.com"}}})
    encoded = json.dumps(rag_trace.list_traces(), ensure_ascii=False)
    assert "abcdefghijklmnop" not in encoded
    assert "alice@example.com" not in encoded
    assert "/Users/alice" not in encoded
    assert "/home/alice" not in encoded
    assert "verysecret123" not in encoded
