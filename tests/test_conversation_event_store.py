import json
import sqlite3


def test_append_only_store_keeps_full_history_and_pages(monkeypatch, tmp_path):
    import backend.conversation_memory as memory

    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    conversation_id = "long-session"
    legacy_messages = [{
        "id": f"message-id-{index}",
        "turn_id": f"turn-{index // 2}",
        "role": "user" if index % 2 == 0 else "assistant",
        "content": f"message-{index}",
        "subject": "数学",
    } for index in range(260)]
    (tmp_path / f"{conversation_id}.json").write_text(json.dumps({
        "id": conversation_id,
        "subject": "数学",
        "messages": legacy_messages,
    }, ensure_ascii=False), encoding="utf-8")
    memory.append_message(
        conversation_id, "user", "message-260", subject="数学",
        turn_id="turn-130", message_id="message-id-260",
    )

    projection = json.loads((tmp_path / f"{conversation_id}.json").read_text(encoding="utf-8"))
    assert projection["message_count"] == 261
    assert len(projection["messages"]) == memory.RECENT_MESSAGE_LIMIT
    assert len(memory.load_history(conversation_id)) == memory.RESOLVER_HISTORY_LIMIT
    assert len(memory.load_full_history(conversation_id)) == 261
    assert [
        item["content"] for item in memory.load_turn_messages(
            conversation_id, ["turn-1"], max_turns=2,
        )
    ] == ["message-2", "message-3"]

    first_page = memory.get_conversation(conversation_id, limit=40)
    second_page = memory.get_conversation(
        conversation_id,
        limit=40,
        before_seq=first_page["page"]["next_before_seq"],
    )
    assert first_page["messages"][0]["content"] == "message-221"
    assert second_page["messages"][0]["content"] == "message-181"
    assert first_page["page"] == {
        "has_more": True,
        "next_before_seq": 222,
        "limit": 40,
        "total": 261,
    }
    assert {item["id"] for item in first_page["messages"]}.isdisjoint(
        item["id"] for item in second_page["messages"]
    )

    with sqlite3.connect(tmp_path / "_conversation_events.db") as conn:
        event_count = conn.execute(
            "SELECT COUNT(*) FROM conversation_events WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()[0]
    assert event_count == 261

    (tmp_path / f"{conversation_id}.json").unlink()
    recovered = memory.get_conversation(conversation_id, limit=40)
    assert recovered["subject"] == "数学"
    assert recovered["message_count"] == 261
    assert [item["id"] for item in memory.list_conversations()] == [conversation_id]


def test_legacy_json_is_imported_once_without_duplicates(monkeypatch, tmp_path):
    import backend.conversation_memory as memory

    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    conversation_id = "legacy-session"
    (tmp_path / f"{conversation_id}.json").write_text(json.dumps({
        "id": conversation_id,
        "subject": "数学",
        "messages": [
            {"id": "legacy-1", "turn_id": "turn-1", "role": "user", "content": "问题", "subject": "数学"},
            {"id": "legacy-2", "turn_id": "turn-1", "role": "assistant", "content": "回答", "subject": "数学"},
        ],
    }, ensure_ascii=False), encoding="utf-8")

    assert len(memory.load_full_history(conversation_id)) == 2
    memory.append_message(
        conversation_id, "user", "追问", subject="数学",
        turn_id="turn-2", message_id="legacy-3",
    )
    assert [item["id"] for item in memory.load_full_history(conversation_id)] == [
        "legacy-1", "legacy-2", "legacy-3",
    ]

    with sqlite3.connect(tmp_path / "_conversation_events.db") as conn:
        imported = conn.execute(
            "SELECT COUNT(*) FROM conversation_events "
            "WHERE conversation_id = ? AND event_type = 'legacy_message_imported'",
            (conversation_id,),
        ).fetchone()[0]
    assert imported == 2


def test_turn_retry_is_idempotent_and_completed_answer_replaces_partial(monkeypatch, tmp_path):
    import backend.conversation_memory as memory

    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    first_user = memory.append_message(
        "retry-session", "user", "问题", subject="数学",
        turn_id="turn-1", message_id="user-1",
    )
    retried_user = memory.append_message(
        "retry-session", "user", "问题", subject="数学",
        turn_id="turn-1", message_id="user-2",
    )
    partial = memory.append_message(
        "retry-session", "assistant", "部分回答", subject="数学",
        turn_id="turn-1", message_id="assistant-1", delivery_status="partial",
    )
    completed = memory.append_message(
        "retry-session", "assistant", "完整回答", subject="数学",
        turn_id="turn-1", message_id="assistant-2", delivery_status="complete",
    )

    history = memory.load_full_history("retry-session")
    assert first_user["id"] == retried_user["id"] == "user-1"
    assert partial["id"] == completed["id"] == "assistant-1"
    assert [(item["role"], item["content"]) for item in history] == [
        ("user", "问题"),
        ("assistant", "完整回答"),
    ]
    assert history[-1]["delivery_status"] == "complete"


def test_sqlite_remains_canonical_when_json_projection_write_fails(monkeypatch, tmp_path):
    import backend.conversation_memory as memory

    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    monkeypatch.setattr(
        memory,
        "atomic_write_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    item = memory.append_message(
        "projection-failure", "user", "仍应成功", subject="数学",
        turn_id="turn-1", message_id="message-1",
    )

    assert item["id"] == "message-1"
    assert not (tmp_path / "projection-failure.json").exists()
    assert [entry["content"] for entry in memory.load_full_history("projection-failure")] == ["仍应成功"]


def test_split_succeeds_when_compatibility_projection_cannot_be_written(monkeypatch, tmp_path):
    import backend.conversation_memory as memory

    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    memory.append_message(
        "source", "user", "需要移动的问题", subject="数学",
        turn_id="turn-1", message_id="user-1",
    )
    memory.append_message(
        "source", "assistant", "需要移动的回答", subject="数学",
        turn_id="turn-1", message_id="assistant-1",
    )
    monkeypatch.setattr(
        memory,
        "atomic_write_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    source, target = memory.split_turn_to_conversation(
        "source", "turn-1", "专业课/传感器", "sensor-book",
    )

    assert source["message_count"] == 0
    assert [item["content"] for item in target["messages"]] == ["需要移动的问题", "需要移动的回答"]


def test_session_ledger_resolves_first_topic_after_eighty_turns(monkeypatch, tmp_path):
    import backend.conversation_memory as memory
    from backend.services.session_context import build_resolution_trace
    from backend.services.session_ledger import get_or_rebuild_session_ledger

    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    conversation_id = "eighty-turn-session"
    messages = []
    for index in range(1, 81):
        turn_id = f"turn-{index}"
        messages.extend([
            {
                "id": f"user-{index}", "turn_id": turn_id, "role": "user",
                "content": f"解释概念{index}。", "subject": "数学",
            },
            {
                "id": f"assistant-{index}", "turn_id": turn_id, "role": "assistant",
                "content": f"这是概念{index}的回答。", "subject": "数学",
            },
        ])
    (tmp_path / f"{conversation_id}.json").write_text(json.dumps({
        "id": conversation_id,
        "subject": "数学",
        "messages": messages,
    }, ensure_ascii=False), encoding="utf-8")
    memory.append_message(
        conversation_id, "assistant", "会话状态检查点。", subject="数学",
        turn_id="checkpoint", message_id="checkpoint",
    )

    recent = memory.load_history(conversation_id)
    assert len(recent) == 48
    assert not any(item["content"] == "解释概念1。" for item in recent)

    ledger = get_or_rebuild_session_ledger(conversation_id, recent)
    trace = build_resolution_trace(
        "回到第一个，它适合什么场景？",
        recent,
        initial_state=ledger["state"],
    )

    assert ledger["state"]["entities"][0] == "概念1"
    assert ledger["state"]["entities"][-1] == "概念80"
    assert trace["resolved_query"] == "概念1适合什么场景？"
    assert trace["speech_act"] == "return"
    assert trace["state_operations"] == [
        {"operation": "return_to_topic", "value": "概念1"},
    ]
