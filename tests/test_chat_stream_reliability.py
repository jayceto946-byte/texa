import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.main import app


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
    assert "answer" == "".join(event.get("chunk", "") for event in events if event["stage"] == "generate")


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
