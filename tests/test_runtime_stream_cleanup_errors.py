"""Offline fault regressions for stream ownership and safe diagnostics."""
import asyncio
import json

import pytest

from backend.services.owned_stream import OwnedStreamingResponse


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("cleanup_error", [None, ValueError("producer failure"), OSError("producer IO failure")])
def test_fence_failure_still_closes_producer_and_remains_primary(asynchronous, cleanup_error):
    calls = []
    fence_error = OSError("task checkpoint write failure")

    class SyncProducer:
        def __iter__(self):
            return iter(())

        def close(self):
            calls.append("producer")
            if cleanup_error:
                raise cleanup_error

    class AsyncProducer:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

        async def aclose(self):
            calls.append("producer")
            if cleanup_error:
                raise cleanup_error

    def fence():
        calls.append("fence")
        raise fence_error

    async def check():
        response = OwnedStreamingResponse(AsyncProducer() if asynchronous else SyncProducer(), on_close=fence)
        with pytest.raises(OSError) as caught:
            await response.aclose()
        assert caught.value is fence_error
        if cleanup_error:
            assert caught.value.__cause__ is cleanup_error
        await response.aclose()
        assert calls == ["fence", "producer"]

    asyncio.run(check())


def test_successful_fence_does_not_mask_producer_error():
    producer_error = OSError("producer failure")

    class Producer:
        def __iter__(self):
            return iter(())

        def close(self):
            raise producer_error

    async def check():
        response = OwnedStreamingResponse(Producer(), on_close=lambda: None)
        with pytest.raises(OSError) as caught:
            await response.aclose()
        assert caught.value is producer_error

    asyncio.run(check())


CANARY = "sk-SYNTHETIC-AUDIT-CANARY-NOT-A-REAL-KEY"


def test_preflight_error_has_safe_summary_and_structured_code(monkeypatch):
    from backend.api import chat

    def fail(*args):
        raise RuntimeError(f"provider refused api_key={CANARY}")

    monkeypatch.setattr(chat, "_prepared_chat_stream", fail)
    monkeypatch.setattr("backend.services.runtime_events.observe_execution_event", lambda event: None)

    async def check():
        response = chat._chat_stream(chat.ChatRequest(question="offline fault injection"))
        output = "".join([chunk async for chunk in response.body_iterator])
        assert CANARY not in output
        events = [json.loads(line[6:])["execution_event"] for line in output.splitlines() if line.startswith("data: ")]
        assert events[-1]["type"] == "error"
        assert events[-1]["summary"].startswith("provider refused")
        assert "[credential]" in events[-1]["summary"]
        assert events[-1]["payload"] == {"error_code": "context_preparation_failed", "error_type": "RuntimeError"}

    asyncio.run(check())


@pytest.mark.parametrize("streaming", [False, True])
def test_generation_error_is_redacted_before_task_persistence(monkeypatch, tmp_path, caplog, streaming):
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from backend.api import chat
    from backend.main import app
    from backend.services.learning_task import LearningTaskStore
    import graph.main_graph as graph

    store = LearningTaskStore(tmp_path)
    prepared = {"book_name": "", "subject": "", "conversation_id": "cid", "turn_id": "turn-1",
        "history": [], "rewritten_question": "question", "resolution_trace": {"resolution_action": "continue"},
        "target_chapters": [], "continuity_context": {}, "subject_suggestion": None,
        "use_textbook_context": False, "scope_reason": "explicit_global_mode", "answer_mode": "global_general",
        "context_versions": {}}
    monkeypatch.setattr(chat, "get_learning_task_store", lambda: store)
    monkeypatch.setattr(chat, "_prepare_chat_turn", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(chat, "select_tool_calls", lambda request: [])
    monkeypatch.setattr(chat, "append_message", lambda *args, **kwargs: {"id": "message"})
    monkeypatch.setattr(chat, "_safe_save_resolution_ledger", lambda *args: None)
    monkeypatch.setattr(chat, "_safe_record_assistant_ledger", lambda *args: None)
    monkeypatch.setattr(chat, "_prepare_main_tool_context", lambda *args, **kwargs: {})
    monkeypatch.setattr("backend.rag_trace.save_trace", lambda payload: None)
    monkeypatch.setattr("backend.services.runtime_events.observe_execution_event", lambda event: None)
    monkeypatch.setattr(chat, "emit_runtime_event", lambda *args, **kwargs: None)
    monkeypatch.setenv("TEXA_AGENT_RUNTIME_READ", "0")

    def fail(**kwargs):
        raise RuntimeError(f"generation refused api_key={CANARY}")

    def fail_stream(**kwargs):
        yield {"stage": "generate", "chunk": "partial", "done": False}
        fail()

    monkeypatch.setattr(graph, "run_graph", fail)
    monkeypatch.setattr(graph, "run_graph_stream", fail_stream)
    if streaming:
        response = TestClient(app).post("/api/chat/stream", json={"question": "question"})
        assert response.status_code == 200
        assert CANARY not in response.text
        assert "generation refused" in response.text
    else:
        with pytest.raises(HTTPException) as caught:
            chat.chat_ask(chat.ChatRequest(question="question"))
        assert caught.value.status_code == 502
    paths = list(store.root.glob("*.json"))
    assert len(paths) == 1
    persisted = paths[0].read_text()
    assert CANARY not in persisted
    assert "generation refused" in persisted
    assert "[credential]" in persisted
    assert CANARY not in caplog.text
