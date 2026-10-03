import json

from backend.services.execution_details import evidence_details, tool_details
from backend.services.execution_events import ExecutionEventEmitter
from backend.services.agent_runtime.contracts import RunCommand
from backend.services.agent_runtime.store import RuntimeStore


def test_retrieved_and_answer_evidence_remain_distinct_and_bounded():
    items = [{"chunk_id": f"chunk-{i}", "book_name": "教材", "text": "原段落" * 300,
              "page_idx": i, "thinking": "private"} for i in range(16)]
    state = {"evidence_items": items, "evidence_sources": [{**items[1], "id": "E1", "chars": 12}]}
    retrieved = evidence_details(state)
    final = evidence_details(state, final=True)
    assert retrieved["evidence_count"] == 16 and len(retrieved["evidence_previews"]) == 12
    assert len(retrieved["evidence_previews"][0]["preview"]) == 420
    assert retrieved["evidence_scope"] == "retrieved"
    assert final["evidence_scope"] == "answer" and final["evidence_count"] == 1
    assert final["evidence_previews"][0]["id"] == "E1"
    assert final["evidence_previews"][0]["preview"] == items[1]["text"][:12]
    assert "private" not in json.dumps(final)
    ExecutionEventEmitter(request_id="r", audit=False).emit("state_transition", phase="evidence",
        status="completed", summary="retrieved", payload=retrieved)


def test_tool_projection_excludes_unknown_fields_and_hidden_thinking():
    projected = tool_details({"expression": "x^2", "api_key": "secret", "thinking": "private"},
        {"data": {"result": "<think>private</think>2*x", "api_key": "secret", "reasoning": "private"},
         "message": "done", "verification": {"passed": False}}, provenance="sympy")
    assert projected["input_preview"] == {"expression": "x^2"}
    assert projected["result_preview"] == "result: 2*x"
    assert projected["verification_passed"] is False
    assert "private" not in json.dumps(projected) and "secret" not in json.dumps(projected)


def test_preview_does_not_rebind_same_chunk_id_from_another_book():
    state = {"evidence_items": [{"book_name": "A", "chunk_id": "c", "text": "A段落"},
                                {"book_name": "B", "chunk_id": "c", "text": "B段落"}],
             "evidence_sources": [{"book_name": "A", "chunk_id": "c", "id": "E1"}]}
    assert evidence_details(state, final=True)["evidence_previews"][0]["preview"] == "A段落"


def test_runtime_tool_events_replay_one_operation_with_real_elapsed_time(tmp_path):
    store = RuntimeStore(tmp_path / "runtime.db")
    run = store.create(RunCommand("k", "r", "task", "conversation", "turn", "test", "owner"))
    run_id = run["run"]["id"]
    call = store.request_tool(run_id, "owner", tool_id="search_exercises", version="1", schema_hash="hash",
        args={"query": "极限", "api_key": "secret"}, args_hash="args-hash", operation_key="op", permission="READ")
    call_id = call["tool_calls"][0]["id"]
    store.start_tool(run_id, "owner", call_id)
    store.finish_tool(run_id, "owner", call_id, {"success": True, "message": "已找到习题",
        "data": {"exercises": [{"question_text": "求极限"}], "thinking": "private"}})
    events = [e for e in store.events(run_id) if e["phase"] == "tool"]
    assert len({e["operation_id"] for e in events}) == 1
    assert events[-1]["elapsed_ms"] >= events[0]["elapsed_ms"] > 0
    assert events[-1]["payload"]["input_preview"] == {"query": "极限"}
    assert "求极限" in events[-1]["payload"]["result_preview"]
    assert "secret" not in json.dumps(events) and "private" not in json.dumps(events)
