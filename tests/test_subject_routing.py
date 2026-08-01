import json


def test_subject_router_suggests_english_reading_from_math(monkeypatch):
    import backend.services.subject_routing as routing

    monkeypatch.setattr(routing, "_book_records", lambda: [])
    monkeypatch.setattr(routing, "_feedback_payload", lambda: {"routes": {}})

    result = routing.suggest_subject_scope(
        "\u8fd9\u7bc7\u9605\u8bfb\u7406\u89e3\u7684\u957f\u96be\u53e5\u600e\u4e48\u5206\u6790\uff1f",
        "\u6570\u5b66/\u9ad8\u6570",
        "",
    )

    assert result is not None
    assert result["target_subject"] == "\u82f1\u8bed/\u9605\u8bfb"
    assert result["confidence"] >= 0.8


def test_subject_router_treats_parent_and_child_hits_as_one_route(monkeypatch):
    import backend.services.subject_routing as routing

    monkeypatch.setattr(routing, "_book_records", lambda: [])
    monkeypatch.setattr(routing, "_feedback_payload", lambda: {"routes": {}})

    result = routing.suggest_subject_scope(
        "\u4ecb\u7ecd\u51e0\u4e2a\u82f1\u8bed\u5199\u4f5c\u4e2d\u5e38\u7528\u7684\u5173\u8054\u8bcd\u3002",
        "\u4e13\u4e1a\u8bfe/\u4f20\u611f\u5668",
        "\u4f20\u611f\u5668\u957f\u4e66",
    )

    assert result is not None
    assert result["target_subject"] == "\u82f1\u8bed/\u5199\u4f5c"
    assert result["current_subject"] == "\u4e13\u4e1a\u8bfe/\u4f20\u611f\u5668"


def test_subject_router_does_not_suggest_current_parent(monkeypatch):
    import backend.services.subject_routing as routing

    monkeypatch.setattr(routing, "_book_records", lambda: [])
    monkeypatch.setattr(routing, "_feedback_payload", lambda: {"routes": {}})

    result = routing.suggest_subject_scope(
        "\u8fd9\u7bc7\u9605\u8bfb\u7406\u89e3\u7684\u957f\u96be\u53e5\u600e\u4e48\u5206\u6790\uff1f",
        "\u82f1\u8bed/\u9605\u8bfb",
        "",
    )

    assert result is None


def test_subject_routing_feedback_persists_counts(monkeypatch, tmp_path):
    import backend.services.subject_routing as routing

    feedback_path = tmp_path / "routing-feedback.json"
    monkeypatch.setattr(routing, "FEEDBACK_PATH", feedback_path)

    routing.record_subject_routing_feedback("\u6570\u5b66", "\u82f1\u8bed", "dismissed")
    routing.record_subject_routing_feedback("\u6570\u5b66", "\u82f1\u8bed", "accepted")

    payload = json.loads(feedback_path.read_text(encoding="utf-8"))
    route = payload["routes"]["\u6570\u5b66->\u82f1\u8bed"]
    assert route["dismissed"] == 1
    assert route["accepted"] == 1


def test_conversation_can_reclassify_and_split_one_turn(monkeypatch, tmp_path):
    import backend.conversation_memory as memory

    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    conversation_id = "conv-test"
    first_turn = "turn-math"
    second_turn = "turn-english"
    memory.append_message(
        conversation_id,
        "user",
        "math question",
        subject="\u6570\u5b66/\u9ad8\u6570",
        turn_id=first_turn,
    )
    memory.append_message(
        conversation_id,
        "assistant",
        "math answer",
        subject="\u6570\u5b66/\u9ad8\u6570",
        turn_id=first_turn,
    )
    memory.append_message(
        conversation_id,
        "user",
        "english question",
        subject="\u6570\u5b66/\u9ad8\u6570",
        turn_id=second_turn,
    )
    memory.append_message(
        conversation_id,
        "assistant",
        "english answer",
        subject="\u6570\u5b66/\u9ad8\u6570",
        turn_id=second_turn,
    )

    before = memory.get_conversation(conversation_id)
    assert len({item["id"] for item in before["messages"]}) == 4

    source, target = memory.split_turn_to_conversation(
        conversation_id,
        second_turn,
        "\u82f1\u8bed/\u9605\u8bfb",
    )
    assert {item["turn_id"] for item in source["messages"]} == {first_turn}
    assert {item["turn_id"] for item in target["messages"]} == {second_turn}
    assert target["subject"] == "\u82f1\u8bed/\u9605\u8bfb"
    assert [item["content"] for item in target["messages"]] == ["english question", "english answer"]

    relabeled = memory.reclassify_conversation(source["id"], "\u6570\u5b66/\u7ebf\u4ee3")
    assert relabeled["subject"] == "\u6570\u5b66/\u7ebf\u4ee3"
    assert [item["content"] for item in relabeled["messages"]] == ["math question", "math answer"]


def test_subject_router_can_discover_professional_course_from_lexical_evidence(monkeypatch, tmp_path):
    import backend.services.subject_routing as routing

    lexical_path = tmp_path / "sensor.json"
    lexical_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(routing, "_feedback_payload", lambda: {"routes": {}})
    monkeypatch.setattr(routing, "_book_records", lambda: [{
        "name": "sensor-book",
        "display_name": "Sensor Book",
        "subject": "\u4e13\u4e1a\u8bfe/\u4f20\u611f\u5668",
    }])
    monkeypatch.setattr(routing, "index_path", lambda book_name: lexical_path)
    monkeypatch.setattr(routing, "search_book", lambda book_name, question, k=2: [
        {"bm25_score": 12.0},
        {"bm25_score": 9.0},
    ])

    result = routing.suggest_subject_scope(
        "\u970d\u5c14\u6548\u5e94\u662f\u4ec0\u4e48\uff1f",
        "\u6570\u5b66/\u9ad8\u6570",
        "",
    )

    assert result is not None
    assert result["target_subject"] == "\u4e13\u4e1a\u8bfe/\u4f20\u611f\u5668"
    assert result["target_book_name"] == "sensor-book"


def test_subject_router_keeps_error_theory_questions_in_current_scope(monkeypatch, tmp_path):
    import backend.services.subject_routing as routing

    lexical_path = tmp_path / "lexical.json"
    lexical_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(routing, "_feedback_payload", lambda: {"routes": {}})
    monkeypatch.setattr(routing, "_book_records", lambda: [
        {"name": "sensor-book", "display_name": "\u4f20\u611f\u5668", "subject": "\u4e13\u4e1a\u8bfe/\u4f20\u611f\u5668"},
        {"name": "error-book", "display_name": "\u8bef\u5dee\u7406\u8bba", "subject": "\u4e13\u4e1a\u8bfe/\u8bef\u5dee\u7406\u8bba"},
    ])
    monkeypatch.setattr(routing, "index_path", lambda book_name: lexical_path)

    def search(book_name, question, k=2):
        scores = (14.0, 10.0) if book_name == "error-book" else (8.0, 5.0)
        return [{"bm25_score": score} for score in scores]

    monkeypatch.setattr(routing, "search_book", search)

    assert routing.suggest_subject_scope(
        "\u7edd\u5bf9\u8bef\u5dee\u548c\u76f8\u5bf9\u8bef\u5dee\u7684\u533a\u522b", "\u4e13\u4e1a\u8bfe/\u8bef\u5dee\u7406\u8bba", "error-book"
    ) is None
    assert routing.suggest_subject_scope(
        "\u968f\u673a\u8bef\u5dee\u4e0e\u7cfb\u7edf\u8bef\u5dee\u5206\u522b\u6709\u4ec0\u4e48\u7279\u70b9\uff1f", "\u4e13\u4e1a\u8bfe/\u8bef\u5dee\u7406\u8bba", "error-book"
    ) is None


def test_conversation_id_is_replaced_when_scope_changes(monkeypatch, tmp_path):
    import backend.conversation_memory as memory

    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    conversation_id = "conv-sensor"
    memory.append_message(
        conversation_id, "user", "sensor question",
        subject="\u4e13\u4e1a\u8bfe/\u4f20\u611f\u5668", book_name="sensor-book",
    )

    assert memory.resolve_conversation_id_for_scope(
        conversation_id, "\u4e13\u4e1a\u8bfe/\u4f20\u611f\u5668", "sensor-book"
    ) == conversation_id
    assert memory.resolve_conversation_id_for_scope(
        conversation_id, "\u4e13\u4e1a\u8bfe/\u8bef\u5dee\u7406\u8bba", "error-book"
    ) != conversation_id


def test_legacy_mixed_conversation_only_exposes_current_scope(monkeypatch, tmp_path):
    import backend.conversation_memory as memory

    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    conversation_id = "conv-mixed"
    memory.append_message(
        conversation_id, "user", "sensor question",
        subject="\u4e13\u4e1a\u8bfe/\u4f20\u611f\u5668", book_name="sensor-book",
    )
    memory.append_message(
        conversation_id, "user", "error question",
        subject="\u4e13\u4e1a\u8bfe/\u8bef\u5dee\u7406\u8bba", book_name="error-book",
    )

    conversation = memory.get_conversation(conversation_id)
    assert conversation["subject"] == "\u4e13\u4e1a\u8bfe/\u8bef\u5dee\u7406\u8bba"
    assert [item["content"] for item in conversation["messages"]] == ["error question"]
    assert [item["content"] for item in memory.load_history(conversation_id)] == ["error question"]
