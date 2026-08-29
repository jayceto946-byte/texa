import threading
import time


def test_concurrent_appends_do_not_lose_messages(monkeypatch, tmp_path):
    import backend.conversation_memory as memory

    monkeypatch.setattr(memory, "CONV_DIR", tmp_path)
    original_read = memory._read_legacy_payload

    def slow_read(conversation_id: str):
        payload = original_read(conversation_id)
        time.sleep(0.01)
        return payload

    monkeypatch.setattr(memory, "_read_legacy_payload", slow_read)
    threads = [
        threading.Thread(
            target=memory.append_message,
            args=("same-conversation", "user", f"message-{index}"),
        )
        for index in range(12)
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert all(not thread.is_alive() for thread in threads)
    history = memory.load_history("same-conversation")
    assert len(history) == 12
    assert {item["content"] for item in history} == {
        f"message-{index}" for index in range(12)
    }
