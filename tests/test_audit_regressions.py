"""Offline witnesses for the October 23 engineering audit."""
import sqlite3
import os

import pytest

from memory.exercise_bank import ExerciseBankStore
from memory.mistake_book import MistakeBookStore
from backend.services.tool_orchestration import (
    _required_outputs, _validate_required_outputs,
    ToolOrchestrationRequest, execute_read_only_tools,
)
from backend.tools.registry import ToolResult


@pytest.mark.skipif(os.name == "nt", reason="POSIX getrusage unit contract")
@pytest.mark.parametrize("platform, expected", [("darwin", 2048), ("linux", 2097152)])
def test_embedding_benchmark_rss_platform_units(monkeypatch, platform, expected):
    import resource
    from types import SimpleNamespace
    from evaluation.embedding_backend import phase1_worker

    monkeypatch.setattr(phase1_worker.sys, "platform", platform)
    monkeypatch.setattr(resource, "getrusage", lambda _who: SimpleNamespace(ru_maxrss=2048))
    assert phase1_worker.rss_bytes() == expected


@pytest.mark.parametrize("store_type", [ExerciseBankStore, MistakeBookStore])
def test_store_connection_closes_after_commit_and_rollback(tmp_path, store_type):
    store = store_type(tmp_path / "store.db")
    with store._connect() as connection:
        connection.execute("CREATE TABLE audit_witness (value INTEGER)")
        connection.execute("INSERT INTO audit_witness VALUES (1)")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
    with pytest.raises(RuntimeError, match="rollback witness"):
        with store._connect() as failed_connection:
            failed_connection.execute("INSERT INTO audit_witness VALUES (2)")
            raise RuntimeError("rollback witness")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        failed_connection.execute("SELECT 1")
    with store._connect() as reopened:
        assert reopened.execute("SELECT value FROM audit_witness").fetchall() == [(1,)]


def test_failed_math_verification_is_an_unsatisfied_required_output():
    class Registry:
        def call(self, name, args, context, **kwargs):
            if name == "symbolic_math":
                return ToolResult(True, data={"result": {"exact": "5"}, "verification_request": {"operation": "calculate"}})
            return ToolResult(False, verification={"passed": False}, message="incorrect result")

    result = execute_read_only_tools(ToolOrchestrationRequest(question="计算 2+2"), registry=Registry())
    assert result["tool_context_pack"]["sufficient"] is False
    assert result["tool_outputs"][-1]["missing_required_outputs"] == ["verified_math"]


def test_numeric_zero_remains_a_valid_output():
    assert _validate_required_outputs({"data": {"result": 0}}, _required_outputs("symbolic_math")) == (["computed_result"], [])
    assert _validate_required_outputs({"success": False}, _required_outputs("unknown")) == ([], ["successful_result"])


def test_runtime_stream_reads_off_event_loop_without_reordering(tmp_path, monkeypatch):
    import asyncio
    import json
    import threading
    from backend.services.agent_runtime import chat_binding as binding
    from backend.services.agent_runtime.store import RuntimeStore
    from backend.services.agent_runtime.contracts import RunCommand

    store = RuntimeStore(tmp_path / "runtime.db")
    run_id = store.create(RunCommand("r", "r", "t", "s", "turn", "test", "owner"))["run"]["id"]
    store.configure_chat(run_id, "owner", state={}, candidates=[], request_question="test", book_name="", subject="数学")
    main_thread = threading.get_ident()
    original = store.stream_snapshot
    reads = []

    def read(*args, **kwargs):
        reads.append(threading.get_ident())
        assert threading.get_ident() != main_thread
        return original(*args, **kwargs)

    def work(_store, _run, _owner, *_args, on_output):
        on_output("first")
        on_output("second")
        store.close(run_id, "owner", outcome="paused", error_code="fixture_end")

    monkeypatch.setattr(store, "stream_snapshot", read)
    monkeypatch.setattr(binding, "execute_run", work)

    async def consume():
        response = binding.stream_run(store, run_id, "owner", registry=binding.build_math_registry(), adapter=object())
        chunks = [chunk async for chunk in response.body_iterator]
        await response.aclose()
        return [json.loads(chunk[6:])["execution_event"] for chunk in chunks]

    events = asyncio.run(consume())
    assert reads
    assert [event["seq"] for event in events] == sorted(set(event["seq"] for event in events))
    assert "".join(event["payload"]["text"] for event in events if event["type"] == "output_delta") == "firstsecond"
