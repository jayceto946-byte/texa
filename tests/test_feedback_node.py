def test_automatic_feedback_never_calls_llm_concept_extractor(monkeypatch):
    import graph.feedback_node as feedback
    import knowledge.concept_memory as concept_memory
    import memory.learning_events as learning_events

    extractor_calls = []

    class DummyMemory:
        def __init__(self, book_name: str):
            self.book_name = book_name

        def extract_concepts(self, question: str, answer: str):
            extractor_calls.append((question, answer))
            return []

    class DummyStore:
        def append(self, event):
            return event.id

    monkeypatch.setattr(feedback, "_link_concepts_locally", lambda state: [])
    monkeypatch.setattr(concept_memory, "ConceptMemory", DummyMemory)
    monkeypatch.setattr(learning_events, "get_learning_event_store", lambda: DummyStore())

    result = feedback._record_concept_memory(
        {
            "book_name": "demo",
            "user_input": "question",
            "final_output": "answer",
            "intent": "qa",
        }
    )

    assert result == []
    assert extractor_calls == []


def test_response_concept_linking_is_local_and_strict(monkeypatch):
    import graph.feedback_node as feedback

    monkeypatch.setattr(
        feedback,
        "_link_concepts_locally",
        lambda state: [
            {"name": "梯度", "confidence": 1.0, "aliases": []},
            {"name": "直接命中", "confidence": 0.88, "aliases": []},
            {"name": "候选词", "confidence": 0.8, "aliases": []},
        ],
    )

    assert feedback.link_concepts_for_response({"user_input": "什么是梯度和直接命中"}) == [
        {"name": "梯度", "confidence": 1.0, "aliases": []},
        {"name": "直接命中", "confidence": 0.88, "aliases": []},
    ]

def test_feedback_node_survives_learning_storage_failure(monkeypatch):
    import graph.feedback_node as feedback

    def fail_feedback(state):
        raise RuntimeError("disk failure")

    monkeypatch.setattr(feedback, "_feedback_node_impl", fail_feedback)
    monkeypatch.setattr(feedback, "link_concepts_for_response", lambda state: [])

    result = feedback.feedback_node({"final_output": "answer"})

    assert result["linked_concepts"] == []
    assert result["mastery_update"] == {}


def test_chapter_progress_requires_verified_task(monkeypatch):
    import graph.feedback_node as feedback

    calls = []

    class DummyStudyMemory:
        def __init__(self, _book_name):
            pass

        def mark_chapter_studied(self, chapter):
            calls.append(chapter)

        def get_chapter_progress(self, chapter):
            return {"chapter": chapter}

    class DummySR:
        def __init__(self, _book_name):
            pass

    monkeypatch.setattr(feedback, "StudyMemory", DummyStudyMemory)
    monkeypatch.setattr(feedback, "SpacedRepetition", DummySR)
    monkeypatch.setattr(feedback, "_record_concept_memory", lambda _state: [])

    unverified = feedback._feedback_node_impl({
        "book_name": "demo", "target_chapters": ["第一章"],
        "answer_verification": {"status": "unverified"},
    })
    verified = feedback._feedback_node_impl({
        "book_name": "demo", "target_chapters": ["第一章"],
        "answer_verification": {"status": "passed"},
    })

    assert unverified["learning_update_status"] == "exposure_only"
    assert verified["learning_update_status"] == "verified_task"
    assert calls == ["第一章"]

def test_generic_qa_extracts_only_direct_high_confidence_concepts(monkeypatch):
    import graph.feedback_node as feedback
    import knowledge.concept_memory as concept_memory
    import memory.learning_events as learning_events

    captured = {"events": [], "exposures": [], "candidates": [], "books": []}

    class DummyMemory:
        def __init__(self, book_name: str):
            captured["books"].append(book_name)

        def extract_concepts(self, question: str, answer: str):
            return [
                {"name": "导数", "confidence": 0.95, "aliases": []},
                {"name": "极限", "confidence": 0.99, "aliases": []},
                {"name": "求导", "confidence": 0.7, "aliases": []},
            ]

        def log_exposure(self, concepts, question, intent, **kwargs):
            captured["exposures"].append((concepts, question, intent, kwargs))

        def log_candidates(self, concepts, question, intent, **kwargs):
            captured["candidates"].append((concepts, question, intent, kwargs))

    class DummyStore:
        def append(self, event):
            captured["events"].append(event)
            return event.id

    monkeypatch.setattr(feedback, "_link_concepts_locally", lambda state: [])
    monkeypatch.setattr(concept_memory, "ConceptMemory", DummyMemory)
    monkeypatch.setattr(learning_events, "get_learning_event_store", lambda: DummyStore())

    result = feedback._record_concept_memory(
        {
            "book_name": "",
            "subject": "数学/高数",
            "conversation_id": "conv-generic",
            "user_input": "导数怎么求",
            "final_output": "可以先用导数定义，再选择求导法则。",
            "intent": "qa",
        }
    )

    assert captured["books"] == ["default"]
    assert [item["name"] for item in result] == ["导数"]
    assert [item["name"] for item in captured["exposures"][0][0]] == ["导数"]
    assert {item["name"] for item in captured["candidates"][0][0]} == {"极限", "求导"}
    chat_event = next(event for event in captured["events"] if event.event_type == "chat_qa")
    assert chat_event.book_name == "default"
    assert chat_event.payload["question"] == "导数怎么求"
    assert chat_event.concept_names == ["导数"]


def test_subject_general_with_selected_book_uses_generic_llm_fallback(monkeypatch):
    import graph.feedback_node as feedback
    import knowledge.concept_memory as concept_memory
    import memory.learning_events as learning_events

    captured = {"extract": [], "exposures": [], "events": []}

    class DummyMemory:
        def __init__(self, book_name: str):
            self.book_name = book_name

        def extract_concepts(self, question, answer, **kwargs):
            captured["extract"].append((question, kwargs))
            return [{"name": "压阻效应", "confidence": 0.96, "aliases": []}]

        def log_exposure(self, concepts, question, intent, **kwargs):
            captured["exposures"].append((concepts, kwargs))

        def log_candidates(self, *args, **kwargs):
            return []

    class DummyStore:
        def append(self, event):
            captured["events"].append(event)
            return event.id

    monkeypatch.setattr(feedback, "_link_concepts_locally", lambda state: [])
    monkeypatch.setattr(concept_memory, "ConceptMemory", DummyMemory)
    monkeypatch.setattr(learning_events, "get_learning_event_store", lambda: DummyStore())

    concepts = feedback._record_concept_memory({
        "book_name": "传感器短书",
        "subject": "专业课/传感器",
        "answer_mode": "subject_general",
        "use_textbook_context": False,
        "conversation_id": "conv-subject-general",
        "user_input": "压阻效应有什么应用？",
        "final_output": "压阻效应可用于应变测量。",
        "intent": "application",
    })

    assert [item["name"] for item in concepts] == ["压阻效应"]
    assert captured["extract"][0][1] == {
        "subject": "专业课/传感器",
        "answer_mode": "subject_general",
    }
    assert captured["exposures"][0][1]["source"] == "qa_subject_general"
    chat_event = next(event for event in captured["events"] if event.event_type == "chat_qa")
    assert chat_event.payload["answer_mode"] == "subject_general"


def test_subject_mismatch_never_writes_concept_memory(monkeypatch):
    import graph.feedback_node as feedback

    monkeypatch.setattr(
        feedback,
        "_link_concepts_locally",
        lambda state: (_ for _ in ()).throw(AssertionError("linker should not run")),
    )
    assert feedback._record_concept_memory({
        "answer_mode": "subject_mismatch",
        "user_input": "Transformer 的 QKV 是什么？",
    }) == []


def test_grounding_refusal_never_writes_concept_memory(monkeypatch):
    import graph.feedback_node as feedback

    monkeypatch.setattr(
        feedback,
        "_link_concepts_locally",
        lambda state: (_ for _ in ()).throw(AssertionError("linker should not run")),
    )
    assert feedback._record_concept_memory({
        "answer_mode": "textbook_grounded",
        "use_textbook_context": True,
        "evidence_support": {"status": "insufficient"},
        "user_input": "教材没有覆盖的问题",
    }) == []
