"""Deterministic crash points and interleavings for the complete execution boundary."""
import asyncio
import json
import threading

import pytest
from fastapi import HTTPException

from backend.api import chat
from backend.services.execution_events import ExecutionEventEmitter
from backend.services.learning_task import LearningTaskStore, interrupt_learning_task, resume_learning_task


@pytest.fixture
def harness(monkeypatch, tmp_path):
    import backend.rag_trace as trace
    store = LearningTaskStore(tmp_path)
    monkeypatch.setattr(chat, "get_learning_task_store", lambda: store)
    monkeypatch.setattr(chat, "_prepare_chat_turn", lambda *a, **kw: {
        "book_name": "", "subject": "", "conversation_id": "cid", "turn_id": "turn",
        "history": [], "rewritten_question": "question", "resolution_trace": {"resolution_action": "continue"},
        "target_chapters": [], "continuity_context": {}, "subject_suggestion": None,
        "use_textbook_context": False, "scope_reason": "explicit_global_mode",
        "answer_mode": "global_general", "context_versions": {},
    })
    monkeypatch.setattr(chat, "select_tool_calls", lambda *a: [])
    monkeypatch.setattr(chat, "_prepare_main_tool_context", lambda *a, **kw: {})
    monkeypatch.setattr(chat, "_safe_save_resolution_ledger", lambda *a: None)
    monkeypatch.setattr(chat, "_safe_record_assistant_ledger", lambda *a: None)
    monkeypatch.setattr(trace, "save_trace", lambda *a: None)
    messages = []
    monkeypatch.setattr(chat, "append_message", lambda cid, role, text, **kw:
                        messages.append((role, text)) or {"id": "message", **kw})
    return store, messages


def test_delayed_preflight_cannot_reclaim_resumed_run(harness):
    store, _ = harness
    task = store.create(task_type="qa", goal="q", conversation_id="cid", turn_id="turn",
                        artifacts={"active_run_id": "r1"})
    stale = resume_learning_task(store, interrupt_learning_task(store, task, stage="test"), run_id="r2")
    newest = resume_learning_task(store, interrupt_learning_task(store, stale, stage="test"), run_id="r3")
    with pytest.raises(ValueError, match="another run"):
        chat._prepared_chat_stream(chat.ChatRequest(question="q"), _learning_task=stale, _resume=True, _run_id="r2")
    assert store.run_is_active(newest.id, "r3")
    with pytest.raises(ValueError, match="ownership"):
        store.save(stale)
    assert store.checkpoint(stale, "late", status="completed").artifacts["active_run_id"] == "r3"
    with pytest.raises(HTTPException) as error:
        chat.interrupt_chat_task(task.id, {"run_id": "r2"})
    assert error.value.status_code == 409
    assert store.run_is_active(task.id, "r3")


def test_nonstream_late_answer_cannot_complete_new_run(harness, monkeypatch):
    import graph.main_graph as graph
    store, messages = harness
    def invoke(**kwargs):
        task = store.get(next(store.root.glob("*.json")).stem)
        resume_learning_task(store, interrupt_learning_task(store, task, stage="test"), run_id="new")
        return {"final_output": "late", "answer_verification": {"status": "passed", "passed": True}}
    monkeypatch.setattr(graph, "run_graph", invoke)
    with pytest.raises(HTTPException) as error:
        chat.chat_ask(chat.ChatRequest(question="q"))
    assert error.value.status_code == 409
    assert not any(role == "assistant" for role, _ in messages)
    assert store.get(next(store.root.glob("*.json")).stem).artifacts["active_run_id"] == "new"


def test_nonstream_exception_has_durable_terminal(harness, monkeypatch):
    import graph.main_graph as graph
    store, _ = harness
    monkeypatch.setattr(graph, "run_graph", lambda **kw: (_ for _ in ()).throw(RuntimeError("provider failed")))
    with pytest.raises(HTTPException):
        chat.chat_ask(chat.ChatRequest(question="q"))
    task = store.get(next(store.root.glob("*.json")).stem)
    assert task.status == "failed"
    assert [e["type"] for e in task.artifacts["execution_events"]] == ["error"]


@pytest.mark.parametrize("stream", [False, True])
def test_chat_commits_feedback_proposal_and_returns_pending_status(harness, monkeypatch, stream):
    import graph.main_graph as graph
    import graph.feedback_node as feedback
    store, _ = harness
    monkeypatch.setattr(feedback, "link_concepts_for_response", lambda *_: [])
    def answer(**kwargs):
        state = {"learning_task": kwargs["continuity_context"]["learning_task"], "final_output": "answer",
                 "answer_verification": {"status": "passed", "passed": True}, "user_input": "question"}
        state.update(feedback.feedback_node(state))
        return state
    if stream:
        monkeypatch.setattr(graph, "run_graph_stream", lambda **kw: iter([
            {"stage": "generate", "chunk": "answer"}, {"stage": "done", "state": answer(**kw)},
        ]))
        rows = [json.loads(line[6:]) for line in chat._prepared_chat_stream(chat.ChatRequest(question="q")).producer]
        public_task = rows[-1]["state"]["learning_task"]
    else:
        monkeypatch.setattr(graph, "run_graph", answer)
        public_task = chat.chat_ask(chat.ChatRequest(question="q"))["learning_task"]
    assert public_task["artifacts"]["effects"][0]["status"] == "pending"
    effect = store.outcome_effects(public_task["id"])[0]
    assert effect["kind"] == "chat_feedback" and effect["prepared"] is None and effect["receipt"] is None


def test_clarification_continuation_rebinds_turn_before_emitting(harness, monkeypatch):
    import graph.main_graph as graph
    store, _ = harness
    task = store.create(task_type="qa", goal="q", conversation_id="cid", turn_id="old", status="waiting_for_input")
    prepare = chat._prepare_chat_turn
    def continued(*a, **kw):
        value = prepare(*a, **kw)
        value["history"] = [{"learning_task": task.to_dict(public=True)}]
        return value
    monkeypatch.setattr(chat, "_prepare_chat_turn", continued)
    monkeypatch.setattr(graph, "run_graph_stream", lambda **kw: iter([
        {"stage": "generate", "chunk": "answer"},
        {"stage": "done", "state": {"final_output": "answer", "answer_verification": {"status": "passed", "passed": True}}},
    ]))
    response = chat._prepared_chat_stream(chat.ChatRequest(question="clarification"))
    events = [json.loads(line[6:])["execution_event"] for line in response.producer]
    assert events[-1]["type"] == "final"
    assert {e["turn_id"] for e in events} == {"turn"}
    assert store.get(task.id).turn_id == "turn"


def test_real_graph_filters_every_token_before_delivery(monkeypatch):
    import graph.main_graph as graph
    import graph.generator as generator
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    monkeypatch.setattr(graph, "plan_node", lambda state: {"intent": "qa", "target_chapters": []})
    monkeypatch.setattr(graph, "retrieve_node", lambda state: {"retrieval_status": "ordinary_qa"})
    monkeypatch.setattr(graph, "feedback_node", lambda state: {})
    monkeypatch.setattr(graph, "_main_graph", None)
    monkeypatch.setattr(generator, "get_llm", lambda *a, **kw: FakeListChatModel(responses=["<think>SYNTHETIC_INTERNAL</think>Visible answer"]))
    events = list(graph.run_graph_stream("q", use_textbook_context=False, answer_mode="global_general"))
    delivered = "".join(e.get("chunk", "") for e in events)
    assert "SYNTHETIC_INTERNAL" not in delivered and "<think>" not in delivered
    assert "Visible answer" in delivered


def test_outcome_commit_failure_is_atomic_and_projection_is_recoverable(tmp_path, monkeypatch):
    from backend import conversation_memory as cm
    monkeypatch.setattr(cm, "CONV_DIR", tmp_path / "conversations")
    store = LearningTaskStore(tmp_path)
    task = store.create(task_type="qa", goal="q", conversation_id="cid", turn_id="turn", artifacts={"active_run_id": "r"})
    prepared = store.prepare_checkpoint_for_run(task, "r", "verified", status="completed")
    final = ExecutionEventEmitter(request_id="req", task_id=task.id, run_id="r", conversation_id="cid", turn_id="turn").emit(
        "final", phase="final", status="completed", summary="done", payload={"task_status": "completed"})
    messages = [{"role": "assistant", "text": "answer", "delivery_status": "complete"}]
    with monkeypatch.context() as mp:
        mp.setattr(store, "_persist", lambda task: (_ for _ in ()).throw(OSError("crash before replace")))
        with pytest.raises(OSError):
            store.commit_outcome(prepared, "r", final, messages=messages)
    assert store.get(task.id).status == "running"
    assert not store.get(task.id).artifacts.get("execution_events")
    store.commit_outcome(prepared, "r", final, messages=messages)
    assert store.get(task.id).status == "completed"
    assert store.project_outcome(task.id, run_id="stale", append=lambda *a, **kw: pytest.fail("stale projection")) == []
    with pytest.raises(OSError):
        store.project_outcome(task.id, append=lambda *a, **kw: (_ for _ in ()).throw(OSError("SQLite unavailable")))
    assert store.get(task.id).artifacts["execution_outcome"]["projected"] is False
    # Crash after SQLite commit, before receipt; a new process retries without duplicating the answer.
    with monkeypatch.context() as mp:
        mp.setattr(store, "_persist", lambda task: (_ for _ in ()).throw(OSError("receipt crash")))
        with pytest.raises(OSError):
            store.project_outcome(task.id)
    restarted = LearningTaskStore(tmp_path)
    restarted.recover_unfinished()
    assert len(cm.load_full_history("cid")) == 1
    assert restarted.get(task.id).artifacts["execution_outcome"]["projected"] is True
    restarted.commit_outcome(prepared, "r", final, messages=messages)
    assert len(restarted.get(task.id).artifacts["execution_events"]) == 1


@pytest.mark.parametrize("spec", ["2.3", "2.4"])
def test_real_asgi_disconnect_closes_chat_child(harness, monkeypatch, spec):
    import graph.main_graph as graph
    store, _ = harness
    closed = threading.Event()
    def stream(**kw):
        try:
            while True:
                yield {"stage": "generate", "chunk": "x", "done": False}
        finally:
            closed.set()
    monkeypatch.setattr(graph, "run_graph_stream", stream)
    response = chat._chat_stream(chat.ChatRequest(question="q"))
    async def drive():
        disconnected = asyncio.Event()
        async def send(message):
            if b'"type": "output_delta"' in message.get("body", b""):
                disconnected.set()
                if spec == "2.4":
                    raise OSError("socket gone")
        async def receive():
            await disconnected.wait()
            return {"type": "http.disconnect"}
        try:
            await response({"type": "http", "asgi": {"spec_version": spec}}, receive, send)
        except Exception as exc:
            assert spec == "2.4" and type(exc).__name__ == "ClientDisconnect"
        # Assert before asyncio.run shuts down async generators; GC is not ownership.
        task = store.get(next(store.root.glob("*.json")).stem)
        assert task.status == "interrupted"
        assert closed.is_set()
    asyncio.run(drive())
    task = store.get(next(store.root.glob("*.json")).stem)
    assert task.status == "interrupted"
    assert closed.is_set()


def test_disconnect_before_resume_preflight_releases_claim(harness):
    store, _ = harness
    task = store.create(task_type="qa", goal="q", conversation_id="cid", turn_id="turn", status="interrupted")
    task = resume_learning_task(store, task, run_id="resumed")
    response = chat._chat_stream(chat.ChatRequest(question="q"), _learning_task=task, _resume=True, _run_id="resumed")
    async def drive():
        async def send(message):
            if message.get("body"):
                raise OSError("disconnected at accepted event")
        async def receive():
            return {"type": "http.disconnect"}
        with pytest.raises(Exception) as error:
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
        assert type(error.value).__name__ == "ClientDisconnect"
        assert store.get(task.id).status == "interrupted"
    asyncio.run(drive())


def test_bounded_queue_cancellation_does_not_start_another_provider_read():
    from graph.main_graph import _iterate_stream_with_progress
    saturated, closed = threading.Event(), threading.Event()
    class Provider:
        count = 0
        def __iter__(self):
            return self
        def __next__(self):
            self.count += 1
            if self.count == 34:
                saturated.set()
            return self.count
        def close(self):
            closed.set()
    provider = Provider()
    stream = _iterate_stream_with_progress(lambda: provider, phase="test", operation_id="test", label="test", summary="test")
    assert next(stream) == ("item", 1)
    assert saturated.wait(3)
    stream.close()
    assert closed.wait(3)
    assert provider.count == 34


def test_disconnect_during_preflight_does_not_abandon_created_task(harness, monkeypatch):
    store, _ = harness
    entered, release = threading.Event(), threading.Event()
    prepare = chat._prepare_chat_turn
    def slow_prepare(*a, **kw):
        entered.set()
        assert release.wait(3)
        return prepare(*a, **kw)
    monkeypatch.setattr(chat, "_prepare_chat_turn", slow_prepare)
    response = chat._chat_stream(chat.ChatRequest(question="q"))
    async def drive():
        disconnected = asyncio.Event()
        async def send(message):
            pass
        async def receive():
            await disconnected.wait()
            return {"type": "http.disconnect"}
        request = asyncio.create_task(response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send))
        assert await asyncio.to_thread(entered.wait, 3)
        disconnected.set()
        await asyncio.sleep(0.01)
        release.set()
        await asyncio.wait_for(request, 3)
        task = store.get(next(store.root.glob("*.json")).stem)
        assert task.status == "interrupted"
    asyncio.run(drive())


def test_resume_repairs_user_message_missing_at_crash_without_duplication(harness, monkeypatch, tmp_path):
    from backend import conversation_memory as cm
    import graph.main_graph as graph
    store, _ = harness
    monkeypatch.setattr(cm, "CONV_DIR", tmp_path / "conversations")
    monkeypatch.setattr(chat, "append_message", cm.append_message)
    # The task is durable, but the producer has not written the user's message.
    chat._prepared_chat_stream(chat.ChatRequest(question="original question"))
    store.recover_unfinished()
    task = store.get(next(store.root.glob("*.json")).stem)
    assert task.artifacts["request_question"] == "original question"
    task = resume_learning_task(store, task, run_id="new")
    monkeypatch.setattr(graph, "run_graph_stream", lambda **kw: iter([
        {"stage": "generate", "chunk": "answer"},
        {"stage": "done", "state": {"final_output": "answer", "answer_verification": {"status": "passed", "passed": True}}},
    ]))
    response = chat._prepared_chat_stream(chat.ChatRequest(question="resolved question"),
                                          _learning_task=task, _resume=True, _run_id="new")
    list(response.producer)
    store.project_outcome(task.id)
    messages = cm.load_full_history("cid")
    assert [(m["role"], m["content"]) for m in messages] == [("user", "original question"), ("assistant", "answer")]


def test_cancelled_blocking_providers_cannot_accumulate_unbounded_workers(monkeypatch):
    import graph.main_graph as graph
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(graph, "_STREAM_WORKER_SLOTS", slots)
    release, closed = threading.Event(), threading.Event()
    called = []
    class Blocking:
        def __iter__(self):
            return self
        def __next__(self):
            release.wait(3)
            raise StopIteration
        def close(self):
            closed.set()
    params = dict(phase="test", operation_id="test", label="test", summary="waiting", interval_seconds=.01)
    first = graph._iterate_stream_with_progress(Blocking, **params)
    assert next(first)[0] == "progress"
    first.close()
    second = graph._iterate_stream_with_progress(lambda: called.append(True) or iter([]), **params)
    assert next(second)[0] == "progress"
    second.close()
    assert called == []
    release.set()
    assert closed.wait(3)
    assert slots.acquire(timeout=3)
    slots.release()
