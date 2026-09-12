"""Revision, snapshot and confirmation crash regressions."""
import threading

import pytest


def test_reclassification_and_ledger_refresh_share_one_lock_order(tmp_path, monkeypatch):
    from backend import conversation_memory as cm
    from backend.services import session_ledger as ledger
    monkeypatch.setattr(cm, "CONV_DIR", tmp_path / "conversations")
    cm.append_message("cid", "user", "question", turn_id="t")
    lock = cm._conversation_lock("cid")
    waiting, finished = threading.Event(), threading.Event()
    errors = []
    class ObservedLock:
        def __enter__(self):
            if threading.current_thread().name == "ledger-refresh":
                waiting.set()
            lock.acquire()
        def __exit__(self, *_args):
            lock.release()
    monkeypatch.setattr(cm, "_conversation_lock", lambda _cid: ObservedLock())
    def refresh():
        try:
            ledger.get_or_rebuild_session_ledger("cid")
        except Exception as exc:
            errors.append(exc)
    reader = threading.Thread(target=refresh, name="ledger-refresh", daemon=True)
    def reclassify():
        try:
            with lock:
                reader.start()
                assert waiting.wait(3)
                cm.reclassify_conversation("cid", "数学")
        except Exception as exc:
            errors.append(exc)
        finally:
            finished.set()
    writer = threading.Thread(target=reclassify, daemon=True)
    writer.start()
    assert finished.wait(5), "conversation mutation and ledger refresh must not deadlock"
    reader.join(3)
    writer.join(3)
    assert not errors and not reader.is_alive() and not writer.is_alive()
    assert ledger.get_or_rebuild_session_ledger("cid")["last_seq"] == cm.latest_message_marker("cid")[0]


def test_partial_completion_invalidates_ledger(tmp_path, monkeypatch):
    from backend import conversation_memory as cm
    from backend.services import session_ledger as ledger
    monkeypatch.setattr(cm, "CONV_DIR", tmp_path / "conversations")
    cm.append_message("cid", "user", "q", turn_id="t")
    cm.append_message("cid", "assistant", "partial", turn_id="t", delivery_status="partial", sources=[{"chunk_id": "old"}])
    before = ledger.get_or_rebuild_session_ledger("cid")
    cm.append_message("cid", "assistant", "answer", turn_id="t", delivery_status="complete", sources=[{"chunk_id": "new"}])
    after = ledger.get_or_rebuild_session_ledger("cid")
    assert after["last_message_id"] == before["last_message_id"]
    assert after["last_seq"] > before["last_seq"]
    assert after["active_evidence"]["ids"] == ["new"]


def test_stale_parallel_resolution_cannot_be_stamped_current(tmp_path, monkeypatch):
    from backend import conversation_memory as cm
    from backend.services import session_ledger as ledger
    from backend.services.session_context import build_resolution_trace
    monkeypatch.setattr(cm, "CONV_DIR", tmp_path / "conversations")
    base = ledger.get_or_rebuild_session_ledger("cid")
    a = build_resolution_trace("解释压阻效应", [], initial_state=base["state"])
    b = build_resolution_trace("解释霍尔效应", [], initial_state=base["state"])
    a["ledger_base_revision"] = b["ledger_base_revision"] = base["last_seq"]
    ma = cm.append_message("cid", "user", "解释压阻效应", turn_id="a")
    mb = cm.append_message("cid", "user", "解释霍尔效应", turn_id="b")
    ledger.save_resolution_to_ledger("cid", a, ma)
    ledger.save_resolution_to_ledger("cid", b, mb)
    result = ledger.get_or_rebuild_session_ledger("cid")
    ledger.invalidate_session_ledger("cid")
    rebuilt = ledger.get_or_rebuild_session_ledger("cid")
    assert result["state"] == rebuilt["state"]
    assert not cm.save_session_ledger_projection("cid", {**result, "last_seq": 0})


def test_resume_checks_every_book_and_retains_version_for_second_resume(monkeypatch):
    from graph.main_graph import _validated_resume_state, RESUME_CHECKPOINT_VERSION
    import ingestion.index_pipeline as pipeline
    monkeypatch.setattr(pipeline, "load_index_manifest", lambda book: {"index_version": {"A": "a1", "B": "b2"}[book]})
    checkpoint = {"resume_checkpoint_version": RESUME_CHECKPOINT_VERSION, "intent": "qa", "target_chapters": [],
                  "chapter_contents": {}, "evidence_items": [{"book_name": "B", "index_version": "b1"}],
                  "evidence_sources": [], "retrieval_status": "ok", "evidence_support": {},
                  "evidence_gate_applied": True, "index_version": "a1"}
    assert not _validated_resume_state(checkpoint, "A", use_textbook_context=True)
    checkpoint["evidence_items"][0]["index_version"] = "b2"
    resumed = _validated_resume_state(checkpoint, "A", use_textbook_context=True)
    assert resumed and _validated_resume_state(resumed, "A", use_textbook_context=True) == resumed


def test_retrieval_rejects_mixed_versions_even_with_same_scope(monkeypatch):
    import graph.retrieval_node as retrieval
    monkeypatch.setattr(retrieval, "_retrieve_node", lambda *a, **kw: {
        "evidence_items": [{"book_name": "A", "index_version": "v1"}, {"book_name": "A", "index_version": "v2"}],
        "chapter_contents": {"ch": ["mixed"]}, "retrieval_status": "ok",
    })
    result = retrieval.retrieve_node({}, vector_store=object())
    assert result["retrieval_status"] == "unavailable"
    assert result["evidence_items"] == [] and result["chapter_contents"] == {}


def test_publication_waits_for_whole_read_without_serializing_readers():
    from ingestion.index_snapshot import index_publication, index_read_snapshot
    reading, release, published = threading.Event(), threading.Event(), threading.Event()
    def reader():
        with index_read_snapshot():
            reading.set()
            release.wait(3)
    def writer():
        with index_publication():
            published.set()
    thread = threading.Thread(target=reader)
    thread.start()
    assert reading.wait(3)
    with index_read_snapshot():
        worker = threading.Thread(target=writer)
        worker.start()
        assert not published.wait(0.05)
    release.set()
    thread.join(3)
    worker.join(3)
    assert published.is_set() and not thread.is_alive() and not worker.is_alive()


@pytest.mark.parametrize("kind", ["add_mistake", "mark_concept_reviewed", "create_practice_session"])
def test_confirmation_receipt_failure_replays_domain_operation_once(tmp_path, monkeypatch, kind):
    from backend.services import pending_actions as actions
    from knowledge import concept_memory
    from memory.mistake_book import get_mistake_book
    from memory.exercise_bank import get_exercise_bank, ExerciseRecord
    monkeypatch.setattr(actions, "PROGRESS_PATH", tmp_path)
    monkeypatch.setattr(concept_memory, "PROGRESS_PATH", tmp_path)
    bank = get_exercise_bank("default", str(tmp_path))
    exercise = ExerciseRecord(question_text="q")
    bank.add(exercise)
    store = actions.PendingActionStore(tmp_path)
    action = store.create({"type": kind, "payload": {"question_text": "q", "name": "极限", "exercise_ids": [exercise.id]}}, context={})
    with monkeypatch.context() as mp:
        mp.setattr(store, "save", lambda value: (_ for _ in ()).throw(OSError("receipt failure")))
        with pytest.raises(OSError):
            store.confirm(action["action_id"])
    assert store.get(action["action_id"])["status"] == "pending"
    outcome = store.confirm(action["action_id"])
    assert store.confirm(action["action_id"])["result"] == outcome["result"]
    if kind == "add_mistake":
        assert len(get_mistake_book("default", str(tmp_path)).list_all()) == 1
    elif kind == "mark_concept_reviewed":
        memory = concept_memory.ConceptMemory("default")
        assert memory._data["concepts"]["极限"]["review_count"] == 1
    else:
        assert bank.get_active_practice_session().id == action["action_id"]
