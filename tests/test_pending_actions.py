from backend.services.pending_actions import PendingActionStore


def test_pending_action_confirm_is_idempotent(tmp_path, monkeypatch):
    import backend.services.pending_actions as actions_module

    monkeypatch.setattr(actions_module, "PROGRESS_PATH", tmp_path)
    store = PendingActionStore(tmp_path)
    action = store.create({
        "type": "add_mistake",
        "payload": {"question_text": "为什么这里求导错了？", "subject": "数学"},
    }, context={"book_name": "default", "subject": "数学", "conversation_id": "conv-1"})

    first = store.confirm(action["action_id"])
    second = store.confirm(action["action_id"])

    assert first["status"] == "confirmed"
    assert second["result"] == first["result"]
    assert second["result"]["mistake_id"]


def test_rejected_action_cannot_be_confirmed(tmp_path):
    store = PendingActionStore(tmp_path)
    action = store.create({
        "type": "mark_concept_reviewed",
        "payload": {"name": "极限"},
    }, context={"book_name": "default", "subject": "数学", "conversation_id": "conv-2"})

    rejected = store.reject(action["action_id"])
    assert rejected["status"] == "rejected"
    try:
        store.confirm(action["action_id"])
    except ValueError as exc:
        assert "rejected" in str(exc)
    else:
        raise AssertionError("rejected action was executed")
