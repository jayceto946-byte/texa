import json
import threading
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.learning_task import LearningTaskStore, interrupt_learning_task, resume_learning_task


class DummyChunk:
    def __init__(self, content: str):
        self.content = content


class DummyLLM:
    def stream(self, prompt: str):
        yield DummyChunk("answer")


def test_run_graph_stream_done_survives_feedback_failure(monkeypatch):
    import config
    import graph.feedback_node as feedback_module
    import graph.intent_classifier as intent_module
    import graph.planner as planner_module
    import graph.retrieval_node as retrieval_module
    from graph.main_graph import run_graph_stream

    monkeypatch.setattr(intent_module, "classify_intent_local", lambda text: {"intent": "qa", "hint": ""})
    monkeypatch.setattr(intent_module, "is_fast_path_eligible", lambda text, result: False)
    monkeypatch.setattr(planner_module, "plan_node", lambda state: {"intent": "qa", "target_chapters": ["chapter-1"]})
    monkeypatch.setattr(retrieval_module, "retrieve_node", lambda state: {"chapter_contents": {"chapter-1": ["context"]}})
    monkeypatch.setattr(config, "get_llm", lambda: DummyLLM())

    def fail_feedback(state):
        raise RuntimeError("feedback disk failure")

    monkeypatch.setattr(feedback_module, "feedback_node", fail_feedback)

    events = list(run_graph_stream("question", book_name="demo-book"))

    assert events[-1]["stage"] == "done"
    assert "error" not in [event["stage"] for event in events]
    content = ""
    for event in events:
        if event["stage"] != "generate":
            continue
        if event.get("replace"):
            content = event.get("chunk", "")
        else:
            content += event.get("chunk", "")
    assert content.startswith("answer")


def test_run_graph_stream_resume_reuses_retrieval_checkpoint(monkeypatch):
    import config
    import graph.feedback_node as feedback_module
    import graph.intent_classifier as intent_module
    import graph.planner as planner_module
    import graph.retrieval_node as retrieval_module
    from graph.main_graph import run_graph_stream

    monkeypatch.setattr(intent_module, "classify_intent_local", lambda text: {"intent": "qa", "hint": ""})
    monkeypatch.setattr(intent_module, "is_fast_path_eligible", lambda text, result: False)
    monkeypatch.setattr(planner_module, "plan_node", lambda state: (_ for _ in ()).throw(
        AssertionError("resume must not run planner")
    ))
    monkeypatch.setattr(retrieval_module, "retrieve_node", lambda state: (_ for _ in ()).throw(
        AssertionError("resume must not repeat retrieval")
    ))
    monkeypatch.setattr(feedback_module, "feedback_node", lambda state: {})
    monkeypatch.setattr(config, "get_llm", lambda *args, **kwargs: DummyLLM())

    events = list(run_graph_stream(
        "解释压阻效应",
        book_name="demo-book",
        resume_state={
            "intent": "qa",
            "target_chapters": ["chapter-1"],
            "chapter_contents": {"chapter-1": ["材料受力后电阻率变化"]},
            "evidence_items": [{"chunk_id": "chunk-1", "text": "材料受力后电阻率变化"}],
            "evidence_sources": [{"id": "E1", "chunk_id": "chunk-1", "text": "材料受力后电阻率变化"}],
            "retrieval_status": "ok",
            "evidence_support": {"status": "supported"},
        },
    ))

    assert events[0]["stage"] == "plan" and events[0]["resumed"] is True
    assert events[1]["stage"] == "retrieve" and events[1]["resumed"] is True
    assert events[-1]["stage"] == "done"


def test_chat_interrupt_acknowledges_checkpoint_before_resume(monkeypatch, tmp_path):
    import backend.api.chat as chat_api

    store = LearningTaskStore(tmp_path)
    task = store.create(
        task_type="qa", goal="解释压阻效应", conversation_id="cid", turn_id="turn-1",
        artifacts={"resume_stage": "retrieve", "active_run_id": "run-old"},
    )
    stale_stream_task = store.get(task.id)
    projected = []
    monkeypatch.setattr(chat_api, "get_learning_task_store", lambda: store)
    monkeypatch.setattr(chat_api, "update_learning_task_projection", lambda cid, task_id, value: projected.append(
        (cid, task_id, value["status"])
    ) or True)

    client = TestClient(app)
    response = client.post(
        f"/api/chat/tasks/{task.id}/interrupt",
        json={"stage": "user_stopped", "partial_output": "已生成一部分"},
    )
    repeated = client.post(f"/api/chat/tasks/{task.id}/interrupt", json={})

    assert response.status_code == 200
    assert response.json()["learning_task"]["status"] == "interrupted"
    assert repeated.status_code == 200
    assert store.get(task.id).artifacts["partial_output"] == "已生成一部分"
    assert projected[-1] == ("cid", task.id, "interrupted")

    store.checkpoint_for_run(
        stale_stream_task, "run-old", "generation_failed", status="failed", detail="late failure",
    )
    assert store.get(task.id).status == "interrupted"

    resumed = resume_learning_task(store, store.get(task.id), run_id="run-new")
    store.checkpoint_for_run(
        stale_stream_task, "run-old", "generation_failed", status="failed", detail="older run failure",
    )
    current = store.get(task.id)
    assert current.status == "running"
    assert current.artifacts["active_run_id"] == "run-new"
    assert resumed.checkpoints[-1]["stage"] == "resumed"

    interrupt_learning_task(
        store, stale_stream_task, stage="late_disconnect", expected_run_id="run-old",
    )
    current = store.get(task.id)
    assert current.status == "running"
    assert current.artifacts["active_run_id"] == "run-new"


def test_late_stream_failure_cannot_overwrite_acknowledged_interrupt(monkeypatch, tmp_path):
    import backend.api.chat as chat_api
    import graph.main_graph as main_graph

    store = LearningTaskStore(tmp_path)
    task = store.create(
        task_type="qa", goal="解释压阻效应", conversation_id="cid", turn_id="turn-1",
        artifacts={"resolved_query": "解释压阻效应"},
    )
    graph_started = threading.Event()
    release_graph = threading.Event()
    result = {}

    monkeypatch.setattr(chat_api, "get_learning_task_store", lambda: store)
    monkeypatch.setattr(chat_api, "_start_chat_learning_task", lambda **kwargs: task)
    monkeypatch.setattr(chat_api, "resolve_conversation_id_for_scope", lambda *args: "cid")
    monkeypatch.setattr(chat_api, "load_history", lambda conversation_id: [])
    monkeypatch.setattr(chat_api, "append_message", lambda *args, **kwargs: {"id": "message"})
    monkeypatch.setattr(chat_api, "_safe_subject_suggestion", lambda *args: None)
    monkeypatch.setattr(chat_api, "decide_answer_scope", lambda *args, **kwargs: SimpleNamespace(
        use_textbook_context=False, reason="requested_subject_general", answer_mode="subject_general",
    ))
    monkeypatch.setattr(chat_api, "update_learning_task_projection", lambda *args: True)

    def late_failure(**kwargs):
        yield {"stage": "plan", "intent": "qa", "chapters": [], "fast_path": False}
        graph_started.set()
        release_graph.wait(timeout=3)
        raise RuntimeError("old stream failed late")

    monkeypatch.setattr(main_graph, "run_graph_stream", late_failure)
    client = TestClient(app)

    def consume_stream():
        result["response"] = client.post("/api/chat/stream", json={
            "question": "解释压阻效应", "conversation_id": "cid", "subject": "数学/线代",
        })

    worker = threading.Thread(target=consume_stream)
    worker.start()
    assert graph_started.wait(timeout=3)
    interrupted = client.post(f"/api/chat/tasks/{task.id}/interrupt", json={"stage": "user_stopped"})
    release_graph.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert interrupted.status_code == 200
    assert store.get(task.id).status == "interrupted"
    assert "old stream failed late" not in result["response"].text


def test_stream_teach_refuses_when_evidence_gate_is_insufficient(monkeypatch):
    import graph.feedback_node as feedback_module
    import graph.intent_classifier as intent_module
    import graph.planner as planner_module
    import graph.retrieval_node as retrieval_module
    from graph.main_graph import run_graph_stream

    monkeypatch.setattr(intent_module, "classify_intent_local", lambda text: {"intent": "teach", "hint": ""})
    monkeypatch.setattr(intent_module, "is_fast_path_eligible", lambda text, result: False)
    monkeypatch.setattr(planner_module, "plan_node", lambda state: {"intent": "teach", "target_chapters": ["chapter-1"]})
    monkeypatch.setattr(retrieval_module, "retrieve_node", lambda state: {
        "chapter_contents": {"chapter-1": ["旁路内容"]},
        "evidence_items": [],
        "evidence_gate_applied": True,
        "evidence_support": {"status": "insufficient", "reason": "question_focus_missing"},
    })
    monkeypatch.setattr(feedback_module, "feedback_node", lambda state: {})

    events = list(run_graph_stream("讲解这一章", book_name="demo-book"))
    generated = "".join(str(event.get("chunk") or "") for event in events if event["stage"] == "generate")

    assert "未检索到足够的直接证据" in generated
    assert "旁路内容" not in generated
    assert not any(event.get("stage") == "chapter" and event.get("has_teaching") for event in events)


def test_chat_stream_done_survives_assistant_persistence_failure(monkeypatch):
    import backend.api.chat as chat_api
    import graph.main_graph as main_graph

    monkeypatch.setattr(chat_api, "ensure_conversation_id", lambda value="": "cid")
    monkeypatch.setattr(chat_api, "load_history", lambda conversation_id: [])
    monkeypatch.setattr(chat_api, "rewrite_followup", lambda question, history, book_name="default", subject="": question)

    def fake_append_message(conversation_id, role, content, book_name="default", subject="", **kwargs):
        if role == "assistant":
            raise RuntimeError("conversation write failed")

    monkeypatch.setattr(chat_api, "append_message", fake_append_message)

    def fake_run_graph_stream(**kwargs):
        yield {"stage": "plan", "intent": "qa", "chapters": [], "fast_path": False}
        yield {"stage": "generate", "chunk": "answer", "done": False}
        yield {"stage": "generate", "chunk": "", "done": True}
        yield {"stage": "done", "state": {}, "enriched": False}

    monkeypatch.setattr(main_graph, "run_graph_stream", fake_run_graph_stream)

    client = TestClient(app)
    response = client.post("/api/chat/stream", json={"question": "question", "book_name": "demo-book"})

    assert response.status_code == 200
    events = []
    for block in response.text.strip().split("\n\n"):
        if not block.startswith("data: "):
            continue
        events.append(json.loads(block[6:]))

    stages = [event["stage"] for event in events]
    assert "done" in stages
    assert "error" not in stages
    done_event = next(event for event in events if event["stage"] == "done")
    assert done_event["persistence_error"] == "conversation write failed"


def test_chat_stream_persists_context_trace_v2(monkeypatch):
    import backend.api.chat as chat_api
    import backend.rag_trace as rag_trace
    import graph.main_graph as main_graph

    history = [
        {"role": "user", "content": "讲一下拉格朗日中值定理。", "turn_id": "turn-1"},
        {"role": "assistant", "content": "回答", "turn_id": "turn-1"},
    ]
    captured = {}
    monkeypatch.setattr(chat_api, "resolve_conversation_id_for_scope", lambda *args: "cid")
    monkeypatch.setattr(chat_api, "load_history", lambda conversation_id: history)
    monkeypatch.setattr(chat_api, "append_message", lambda *args, **kwargs: {"id": "message"})
    monkeypatch.setattr(chat_api, "_safe_subject_suggestion", lambda *args: None)
    monkeypatch.setattr(chat_api, "decide_answer_scope", lambda *args, **kwargs: SimpleNamespace(
        use_textbook_context=True,
        reason="book_concept_match",
        answer_mode="textbook_grounded",
    ))
    monkeypatch.setattr(rag_trace, "save_trace", lambda payload: captured.update(payload))

    def fake_run_graph_stream(**kwargs):
        yield {"stage": "plan", "intent": "condition", "chapters": [], "fast_path": True}
        yield {"stage": "generate", "chunk": "answer", "done": False}
        yield {"stage": "generate", "chunk": "", "done": True}
        yield {"stage": "done", "state": {
            "retrieval_action": "full",
            "retrieval_query": "拉格朗日中值定理的成立条件是什么？",
            "reused_evidence_ids": [],
            "new_evidence_ids": ["chunk-1", "chunk-2"],
            "dropped_evidence_ids": [],
            "evidence_sources": [{"chunk_id": "chunk-1"}],
            "retrieval_status": "ok",
            "retrieval_error": "",
            "evidence_support": {"status": "supported"},
            "context_budget": {"budget_unit": "chars", "assembled_prompt_chars": 3000},
        }, "enriched": False}

    monkeypatch.setattr(main_graph, "run_graph_stream", fake_run_graph_stream)

    response = TestClient(app).post("/api/chat/stream", json={
        "question": "条件呢？", "book_name": "demo",
    })

    assert response.status_code == 200
    context = captured["context"]
    assert context["resolution"]["raw_query"] == "条件呢？"
    assert context["resolution"]["resolved_query"] == "拉格朗日中值定理的成立条件是什么？"
    assert context["resolution"]["state_before"]["topic"] == "拉格朗日中值定理"
    assert context["retrieval"]["action"] == "full"
    assert context["retrieval"]["new_evidence_ids"] == ["chunk-1"]
    assert context["retrieval"]["dropped_evidence_ids"] == ["chunk-2"]
    assert context["context_budget"]["assembled_prompt_chars"] == 3000


def test_chat_stream_clarifies_unresolved_reference_without_running_graph(monkeypatch):
    import backend.api.chat as chat_api
    import graph.main_graph as main_graph

    history = [
        {"role": "user", "content": "解释采样定理。", "turn_id": "turn-1"},
        {"role": "assistant", "content": "采样定理描述采样频率要求。", "turn_id": "turn-1"},
    ]
    saved = []
    monkeypatch.setattr(chat_api, "resolve_conversation_id_for_scope", lambda *args: "cid")
    monkeypatch.setattr(chat_api, "load_history", lambda conversation_id: history)
    monkeypatch.setattr(chat_api, "append_message", lambda cid, role, content, **kwargs: saved.append(
        (role, content)
    ) or {"id": f"message-{role}"})
    monkeypatch.setattr(chat_api, "_safe_subject_suggestion", lambda *args: None)
    monkeypatch.setattr(chat_api, "decide_answer_scope", lambda *args, **kwargs: SimpleNamespace(
        use_textbook_context=True, reason="book_concept_match", answer_mode="textbook_grounded",
    ))
    monkeypatch.setattr(main_graph, "run_graph_stream", lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("clarification must bypass graph execution")
    ))

    response = TestClient(app).post("/api/chat/stream", json={
        "question": "第二个呢？", "book_name": "demo",
    })
    events = [
        json.loads(block[6:])
        for block in response.text.strip().split("\n\n")
        if block.startswith("data: ")
    ]

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    assert [event["stage"] for event in events] == ["execution", "context", "generate", "generate", "done"]
    assert events[0]["execution_event"]["type"] == "progress"
    assert events[1]["resolution_action"] == "clarify"
    assert events[-1]["state"]["retrieval_action"] == "none"
    assert events[-1]["state"]["conversation_context_pack"]["turn_ids"] == ["turn-1"]
    assert "text" not in events[-1]["state"]["conversation_context_pack"]
    assert saved[0] == ("user", "第二个呢？")
    assert saved[1][0] == "assistant"
    assert "不能确定" in saved[1][1]


def test_chat_ask_clarifies_unresolved_reference_without_running_graph(monkeypatch):
    import backend.api.chat as chat_api
    import backend.rag_trace as rag_trace
    import graph.main_graph as main_graph

    history = [
        {"role": "user", "content": "解释采样定理。", "turn_id": "turn-1"},
        {"role": "assistant", "content": "采样定理描述采样频率要求。", "turn_id": "turn-1"},
    ]
    monkeypatch.setattr(chat_api, "resolve_conversation_id_for_scope", lambda *args: "cid")
    monkeypatch.setattr(chat_api, "load_history", lambda conversation_id: history)
    monkeypatch.setattr(chat_api, "append_message", lambda *args, **kwargs: {"id": "message"})
    monkeypatch.setattr(chat_api, "_safe_subject_suggestion", lambda *args: None)
    monkeypatch.setattr(chat_api, "decide_answer_scope", lambda *args, **kwargs: SimpleNamespace(
        use_textbook_context=True, reason="book_concept_match", answer_mode="textbook_grounded",
    ))
    monkeypatch.setattr(rag_trace, "save_trace", lambda payload: None)
    monkeypatch.setattr(main_graph, "run_graph", lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("clarification must bypass graph execution")
    ))

    response = TestClient(app).post("/api/chat/ask", json={
        "question": "第二个呢？", "book_name": "demo",
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["resolution_action"] == "clarify"
    assert "不能确定" in payload["content"]
    assert payload["sources"] == []


def test_chat_stream_disables_wrong_textbook_context_for_subject_suggestion(monkeypatch):
    import backend.api.chat as chat_api
    import graph.main_graph as main_graph

    suggestion = {
        "target_subject": "\u82f1\u8bed/\u5199\u4f5c",
        "target_book_name": "",
        "current_subject": "\u4e13\u4e1a\u8bfe/\u4f20\u611f\u5668",
        "current_book_name": "sensor-book",
        "confidence": 0.9,
        "reason": "english writing terms",
    }
    monkeypatch.setattr(chat_api, "ensure_conversation_id", lambda value="": "cid")
    monkeypatch.setattr(chat_api, "load_history", lambda conversation_id: [])
    monkeypatch.setattr(chat_api, "rewrite_followup", lambda question, history, book_name="default", subject="": question)
    monkeypatch.setattr(chat_api, "append_message", lambda *args, **kwargs: None)
    monkeypatch.setattr(chat_api, "_safe_subject_suggestion", lambda *args: suggestion)

    captured = {}

    def fake_run_graph_stream(**kwargs):
        captured.update(kwargs)
        yield {"stage": "generate", "chunk": "answer", "done": False}
        yield {"stage": "done", "state": {}, "enriched": False}

    monkeypatch.setattr(main_graph, "run_graph_stream", fake_run_graph_stream)

    client = TestClient(app)
    response = client.post("/api/chat/stream", json={
        "question": "\u4ecb\u7ecd\u51e0\u4e2a\u82f1\u8bed\u5199\u4f5c\u4e2d\u5e38\u7528\u7684\u5173\u8054\u8bcd\u3002",
        "book_name": "sensor-book",
        "subject": "\u4e13\u4e1a\u8bfe/\u4f20\u611f\u5668",
    })

    events = [
        json.loads(block[6:])
        for block in response.text.strip().split("\n\n")
        if block.startswith("data: ")
    ]
    assert response.status_code == 200
    assert captured["use_textbook_context"] is False
    assert captured["answer_mode"] == "subject_mismatch"
    assert events[-1]["subject_suggestion"] == suggestion


def test_chat_ask_explicit_global_mode_bypasses_subject_boundary(monkeypatch):
    import backend.api.chat as chat_api
    import graph.main_graph as main_graph

    monkeypatch.setattr(chat_api, "load_history", lambda conversation_id: [])
    monkeypatch.setattr(chat_api, "rewrite_followup", lambda question, history, book_name="default", subject="": question)
    monkeypatch.setattr(chat_api, "append_message", lambda *args, **kwargs: None)

    captured = {}

    def fake_run_graph(**kwargs):
        captured.update(kwargs)
        return {
            "final_output": "QKV answer",
            "intent": "definition",
            "target_chapters": [],
            "linked_concepts": [],
            "chapter_contents": {},
        }

    monkeypatch.setattr(main_graph, "run_graph", fake_run_graph)

    client = TestClient(app)
    response = client.post("/api/chat/ask", json={
        "question": "Transformer 的 QKV 是什么？",
        "book_name": "传感器短书",
        "subject": "专业课/传感器",
        "answer_mode": "global_general",
    })

    assert response.status_code == 200
    assert captured["answer_mode"] == "global_general"
    assert captured["use_textbook_context"] is False
    assert response.json()["answer_mode"] == "global_general"


def test_chat_ask_passes_target_chapters(monkeypatch):
    import backend.api.chat as chat_api
    import graph.main_graph as main_graph

    monkeypatch.setattr(chat_api, "ensure_conversation_id", lambda value="": "cid")
    monkeypatch.setattr(chat_api, "load_history", lambda conversation_id: [])
    monkeypatch.setattr(chat_api, "rewrite_followup", lambda question, history, book_name="default", subject="": question)
    monkeypatch.setattr(chat_api, "append_message", lambda *args, **kwargs: None)

    captured = {}

    def fake_run_graph(**kwargs):
        captured.update(kwargs)
        return {
            "final_output": "answer",
            "intent": "qa",
            "target_chapters": kwargs.get("target_chapters", []),
            "linked_concepts": [],
            "chapter_contents": {},
        }

    monkeypatch.setattr(main_graph, "run_graph", fake_run_graph)

    client = TestClient(app)
    response = client.post(
        "/api/chat/ask",
        json={"question": "question", "book_name": "demo-book", "target_chapters": ["chapter-1"]},
    )

    assert response.status_code == 200
    assert captured["target_chapters"] == ["chapter-1"]
    assert response.json()["chapters"] == ["chapter-1"]

def test_chat_stream_replace_event_overwrites_persisted_assistant_content(monkeypatch):
    import backend.api.chat as chat_api
    import graph.main_graph as main_graph

    monkeypatch.setattr(chat_api, "ensure_conversation_id", lambda value="": "cid")
    monkeypatch.setattr(chat_api, "load_history", lambda conversation_id: [])
    monkeypatch.setattr(chat_api, "rewrite_followup", lambda question, history, book_name="default", subject="": question)

    saved: list[tuple[str, str]] = []

    def fake_append_message(conversation_id, role, content, book_name="default", subject="", **kwargs):
        saved.append((role, content))

    monkeypatch.setattr(chat_api, "append_message", fake_append_message)

    def fake_run_graph_stream(**kwargs):
        yield {"stage": "generate", "chunk": "gradient $\\nabla f", "done": False}
        yield {"stage": "generate", "chunk": "gradient $\\nabla f$", "replace": True, "done": False}
        yield {"stage": "generate", "chunk": "", "done": True}
        yield {"stage": "done", "state": {}, "enriched": False}

    monkeypatch.setattr(main_graph, "run_graph_stream", fake_run_graph_stream)

    client = TestClient(app)
    response = client.post("/api/chat/stream", json={"question": "question", "book_name": "demo-book"})

    assert response.status_code == 200
    assistant_contents = [content for role, content in saved if role == "assistant"]
    assert assistant_contents == ["gradient $\\nabla f$"]


def test_chat_stream_exposes_and_persists_explicit_grounding_fallback(monkeypatch):
    import backend.api.chat as chat_api
    import graph.main_graph as main_graph

    monkeypatch.setattr(chat_api, "load_history", lambda conversation_id: [])
    monkeypatch.setattr(chat_api, "rewrite_followup", lambda question, history, book_name="", subject="": question)
    monkeypatch.setattr(chat_api, "decide_answer_scope", lambda *args, **kwargs: SimpleNamespace(
        answer_mode="textbook_grounded", use_textbook_context=True, reason="book_concept_match",
    ))
    saved = []
    monkeypatch.setattr(chat_api, "append_message", lambda *args, **kwargs: saved.append(kwargs) or {"id": "message"})

    def fake_run_graph_stream(**kwargs):
        yield {"stage": "generate", "chunk": "教材证据不足。", "done": False, "suggested_answer_mode": "subject_general"}
        yield {"stage": "generate", "chunk": "", "done": True, "suggested_answer_mode": "subject_general"}
        yield {"stage": "done", "state": {"suggested_answer_mode": "subject_general"}, "enriched": False}

    monkeypatch.setattr(main_graph, "run_graph_stream", fake_run_graph_stream)

    response = TestClient(app).post("/api/chat/stream", json={
        "question": "复杂教材问题", "book_name": "demo", "subject": "专业课/传感器",
    })
    events = [
        json.loads(block[6:])
        for block in response.text.strip().split("\n\n")
        if block.startswith("data: ")
    ]

    assert events[-1]["suggested_answer_mode"] == "subject_general"
    assistant_save = next(item for item in saved if item.get("answer_mode"))
    assert assistant_save["suggested_answer_mode"] == "subject_general"
