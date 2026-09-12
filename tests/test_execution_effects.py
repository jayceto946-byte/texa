"""Crash/restart acceptance for committed, receipt-backed learning writes."""
import io
import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.services import execution_effects as effects
from backend.services.execution_events import ExecutionEventEmitter
from backend.services.learning_task import LearningTaskStore, interrupt_learning_task, resume_learning_task
from knowledge.concept_memory import ConceptMemory
from memory.learning_events import LearningEventStore
from memory.mistake_book import MistakeBook, MistakeRecord, get_mistake_book
from memory.spaced_repetition import SpacedRepetition
from memory.study_memory import StudyMemory


class Crash(BaseException):
    pass


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    import config
    from backend import conversation_memory
    from backend.services import pending_actions
    from knowledge import concept_memory
    from memory import learning_events, spaced_repetition, study_memory
    import graph.feedback_node as feedback
    for module in (config, effects, pending_actions, concept_memory, learning_events, spaced_repetition, study_memory):
        monkeypatch.setattr(module, "PROGRESS_PATH", tmp_path)
    monkeypatch.setattr(conversation_memory, "CONV_DIR", tmp_path / "conversations")
    events = LearningEventStore(tmp_path / "events.db")
    monkeypatch.setattr(learning_events, "get_learning_event_store", lambda: events)
    monkeypatch.setattr(feedback, "_resolve_final_concepts", lambda *_a, **_k: [
        {"name": "极限", "confidence": 1, "source": "query_dictionary"}])
    monkeypatch.setattr(feedback, "_link_concepts_locally", lambda *_a: [
        {"name": "极限", "confidence": 1}, {"name": "导数", "confidence": .6}])
    return LearningTaskStore(tmp_path), events


def prepared_task(store, *, kind="chat_feedback", consent=True, status="completed", cid="conv"):
    task = store.create(task_type="qa" if kind == "chat_feedback" else "visual_qa", goal="极限是什么",
                        conversation_id=cid, turn_id="turn", artifacts={
                            "active_run_id": "run", "book_name": "default", "import_to_mistakes": consent})
    task.artifacts.update(final_output="answer", completed_derivation="answer")
    task.verification = {"status": "passed" if status == "completed" else "unverified"}
    final = ExecutionEventEmitter(request_id="req", task_id=task.id, run_id="run",
                                  conversation_id=cid, turn_id="turn").emit(
        "final", phase="final", status="completed", summary="answer saved", payload={"task_status": status})
    task = store.prepare_checkpoint_for_run(task, "run", "verified", status=status)
    if kind == "chat_feedback":
        proposal = {"kind": kind, "payload": {
            "user_input": "极限是什么", "final_output": "answer", "book_name": "default",
            "answer_mode": "textbook_grounded", "target_chapters": ["ch"],
            "user_feedback": {"rating": 4, "knowledge_point": "极限"},
        }}
    else:
        proposal = effects.visual_effect(MistakeRecord(question_text="极限是什么", linked_concepts=[
            {"name": "极限", "confidence": 1, "source": "mistake_linker"}]),
            book_name="default", import_to_mistakes=consent)
    return task, final, proposal


def commit(store, **kwargs):
    task, final, proposal = prepared_task(store, **kwargs)
    return store.commit_outcome(task, "run", final, effects=[proposal],
                                messages=[{"role": "assistant", "text": "answer"}])


def assert_chat_counts_once(events):
    progress = StudyMemory("default").get_chapter_progress("ch")
    assert progress["review_count"] == 1
    card = SpacedRepetition("default")._cards["ch::极限"]
    assert card["repetitions"] == 1 and card["interval"] == 1 and card["easiness"] == 2.5
    memory = ConceptMemory("default")
    assert memory._data["concepts"]["极限"]["exposure_count"] == 1
    assert memory._data["candidate_concepts"]["导数"]["seen_count"] == 1
    rows = events.list_recent(limit=100)
    assert sorted(e.event_type for e in rows) == ["chat_qa", "concept_candidates", "concept_exposure"]


@pytest.mark.parametrize("kind", ["chat_feedback", "visual_feedback"])
def test_uncommitted_interrupted_and_stale_runs_have_no_permission(isolated, monkeypatch, kind):
    store, events = isolated
    task, final, proposal = prepared_task(store, kind=kind)
    # In-memory final/proposal is not a write permit.
    effects.recover_task_effects(store, task.id)
    stopped = interrupt_learning_task(store, store.get(task.id), stage="test")
    resumed = resume_learning_task(store, stopped, run_id="new")
    with pytest.raises(ValueError, match="stale"):
        store.commit_outcome(task, "run", final, effects=[proposal])
    effects.ExecutionEffectsWorker(store).run_once()
    assert events.list_recent() == []
    assert store.get(task.id).artifacts["active_run_id"] == resumed.artifacts["active_run_id"]
    assert not (store.root.parent / "default" / "concept_memory.json").exists()


@pytest.mark.parametrize("target,method", [
    (StudyMemory, "mark_chapter_studied"), (SpacedRepetition, "add_knowledge_point"),
    (SpacedRepetition, "review"), (ConceptMemory, "log_exposure"),
    (ConceptMemory, "log_candidates"), (LearningEventStore, "append"),
])
def test_crash_after_each_chat_domain_write_replays_once(isolated, monkeypatch, target, method):
    store, events = isolated
    task = commit(store)
    original = getattr(target, method)
    with monkeypatch.context() as mp:
        def crash_after(*args, **kwargs):
            original(*args, **kwargs)
            raise Crash()
        mp.setattr(target, method, crash_after)
        with pytest.raises(Crash):
            effects.recover_task_effects(store, task.id)
    fresh = LearningTaskStore(store.root.parent)
    effects.recover_task_effects(fresh, task.id)
    effects.recover_task_effects(fresh, task.id)
    assert_chat_counts_once(events)
    assert fresh.outcome_effects(task.id)[0]["receipt"] == {"concept_count": 1}


@pytest.mark.parametrize("kind", ["chat_feedback", "visual_feedback"])
def test_effect_receipt_crash_and_duplicate_workers(isolated, monkeypatch, kind):
    store, events = isolated
    task = commit(store, kind=kind)
    original = store.update_outcome_effect
    with monkeypatch.context() as mp:
        def crash_receipt(*args, **kwargs):
            if "receipt" in kwargs:
                raise Crash()
            return original(*args, **kwargs)
        mp.setattr(store, "update_outcome_effect", crash_receipt)
        with pytest.raises(Crash):
            effects.recover_task_effects(store, task.id)
    threads = [threading.Thread(target=effects.recover_task_effects,
                                args=(LearningTaskStore(store.root.parent), task.id)) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(3)
        assert not thread.is_alive()
    assert store.outcome_effects(task.id)[0]["receipt"] is not None
    if kind == "chat_feedback":
        assert_chat_counts_once(events)
    else:
        assert len(get_mistake_book("default", str(store.root.parent)).list_all()) == 1
        assert len(events.list_recent(event_type="mistake_added")) == 1
        assert ConceptMemory("default")._data["concepts"]["极限"]["exposure_count"] == 1


def test_frozen_concepts_survive_restart_without_provider(isolated, monkeypatch):
    store, events = isolated
    task = commit(store)
    with monkeypatch.context() as mp:
        mp.setattr(effects, "_apply", lambda *_: (_ for _ in ()).throw(Crash()))
        with pytest.raises(Crash):
            effects.recover_task_effects(store, task.id)
    import graph.feedback_node as feedback
    monkeypatch.setattr(feedback, "_resolve_final_concepts", lambda *_: pytest.fail("must use frozen concepts"))
    monkeypatch.setattr(feedback, "_link_concepts_locally", lambda *_: pytest.fail("must use frozen candidates"))
    effects.recover_task_effects(LearningTaskStore(store.root.parent), task.id)
    assert_chat_counts_once(events)


def test_blocked_provider_does_not_hold_task_lock_and_shutdown_fences_writes(isolated, monkeypatch):
    store, events = isolated
    task = commit(store)
    entered, release = threading.Event(), threading.Event()
    prepare = effects._prepare
    def blocked(effect):
        entered.set()
        release.wait(3)
        return prepare(effect)
    monkeypatch.setattr(effects, "_prepare", blocked)
    worker = effects.ExecutionEffectsWorker(store, interval=.05)
    worker.start()
    try:
        assert entered.wait(2)
        other = store.create(task_type="qa", goal="other", artifacts={"active_run_id": "other"})
        assert interrupt_learning_task(store, other, stage="stop").status == "interrupted"
        assert not worker.stop(timeout=.01)
    finally:
        release.set()
        assert worker.stop(timeout=2)
    assert events.list_recent() == []
    assert store.outcome_effects(task.id)[0]["prepared"] is None
    assert store.get(task.id).status == "completed"


def test_only_new_explicit_effects_recover_and_retry_is_bounded(isolated, monkeypatch):
    store, events = isolated
    legacy, final, _ = prepared_task(store)
    store.commit_outcome(legacy, "run", final)
    task = commit(store, cid="new")
    calls = []
    with monkeypatch.context() as mp:
        def unavailable(_):
            calls.append(1)
            raise OSError("synthetic provider secret must not be stored")
        mp.setattr(effects, "_prepare", unavailable)
        effects.ExecutionEffectsWorker(store).run_once()
        effects.ExecutionEffectsWorker(store).run_once()
    item = store.outcome_effects(task.id)[0]
    assert calls == [1] and item["attempts"] == 1
    assert "secret" not in json.dumps(item)
    store.update_outcome_effect(task.id, "run", item["id"], retry_at=0)
    effects.recover_task_effects(store, task.id)
    assert store.outcome_effects(legacy.id) == []
    assert_chat_counts_once(events)


def test_concurrent_conversations_preserve_both_counts(isolated):
    store, events = isolated
    tasks = [commit(store, cid=cid) for cid in ("one", "two")]
    threads = [threading.Thread(target=effects.recover_task_effects, args=(store, task.id)) for task in tasks]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(3)
    effects.ExecutionEffectsWorker(store).run_once()
    assert StudyMemory("default").get_chapter_progress("ch")["review_count"] == 2
    assert SpacedRepetition("default")._cards["ch::极限"]["repetitions"] == 2
    assert ConceptMemory("default")._data["concepts"]["极限"]["exposure_count"] == 2
    assert len(events.list_recent()) == 6


def test_import_is_request_selected_and_degraded_answer_can_record_exposure(isolated):
    store, events = isolated
    task, final, proposal = prepared_task(store, kind="visual_feedback", consent=False, status="degraded")
    proposal["payload"]["import_to_mistakes"] = True
    with pytest.raises(ValueError, match="selection"):
        store.commit_outcome(task, "run", final, effects=[proposal])
    proposal["payload"]["import_to_mistakes"] = False
    store.commit_outcome(task, "run", final, effects=[proposal])
    effects.recover_task_effects(store, task.id)
    assert effects.visual_effect_result(store, task.id, "run")["mistake_id"] == ""
    assert events.list_recent() == []
    assert ConceptMemory("default")._data["concepts"]["极限"]["exposure_count"] == 1


@pytest.mark.parametrize("kind", ["add_mistake", "mark_concept_reviewed", "create_practice_session"])
def test_reject_after_domain_commit_repairs_confirmation(isolated, monkeypatch, kind):
    from backend.services.pending_actions import PendingActionStore
    from memory.exercise_bank import ExerciseRecord, get_exercise_bank
    store, _ = isolated
    bank = get_exercise_bank("default", str(store.root.parent))
    record = ExerciseRecord(question_text="q")
    bank.add(record)
    actions = PendingActionStore(store.root.parent)
    action = actions.create({"type": kind, "payload": {
        "name": "极限", "question_text": "q", "exercise_ids": [record.id]}}, context={})
    with monkeypatch.context() as mp:
        mp.setattr(actions, "save", lambda *_: (_ for _ in ()).throw(Crash()))
        with pytest.raises(Crash):
            actions.confirm(action["action_id"])
    with pytest.raises(ValueError, match="executed"):
        actions.reject(action["action_id"])
    repaired = actions.confirm(action["action_id"])
    assert repaired["status"] == "confirmed"
    assert actions.get(action["action_id"])["result"] == repaired["result"]


def test_task_graph_returns_proposal_without_starting_feedback_thread(monkeypatch):
    import graph.feedback_node as feedback
    monkeypatch.setattr(feedback, "link_concepts_for_response", lambda *_: [])
    monkeypatch.setattr(feedback.threading, "Thread", lambda **_: pytest.fail("task graph must not write"))
    result = feedback.feedback_node({"learning_task": {"id": "task"}, "final_output": "answer"})
    assert result["feedback_proposal"]["final_output"] == "answer"


@pytest.mark.parametrize("when", ["before", "after"])
def test_image_atomic_copy_never_loses_the_input(isolated, monkeypatch, when):
    from backend.services.mistake_images import MistakeImageStore
    import backend.services.mistake_images as images
    store, _ = isolated
    image_store = MistakeImageStore(store.root.parent / "images", frozenset({".png"}), 1000, 1600, 86, 1)
    source = image_store.save_upload(type("Upload", (), {"filename": "a.png", "file": io.BytesIO(b"readable")})())
    replace = images.os.replace
    with monkeypatch.context() as mp:
        def interrupted(src, dst):
            if when == "after":
                replace(src, dst)
            raise OSError("power loss")
        mp.setattr(images.os, "replace", interrupted)
        with pytest.raises(OSError):
            image_store.retain_for_task(source, "task_stable")
    assert source.read_bytes() == b"readable"
    first = image_store.retain_for_task(source, "task_stable")
    assert first == image_store.retain_for_task(source, "task_stable")
    assert first.read_bytes() == source.read_bytes()
    image_store.delete(source)
    assert image_store.retain_for_task(source, "task_stable") == first
    with pytest.raises(ValueError):
        image_store.retain_for_task(first, "../outside")


def test_visual_terminal_stays_delivered_when_domain_write_fails(isolated, monkeypatch):
    from backend.api import mistakes
    from backend.main import app
    from backend.services.mistake_images import MistakeImageStore
    from backend.services.multimodal_bridge import VisualProblemIR
    store, _ = isolated
    images = MistakeImageStore(store.root.parent / "images", frozenset({".png"}), 1000, 1600, 86, 3600)
    monkeypatch.setattr(mistakes, "_image_store", images)
    monkeypatch.setattr(mistakes, "get_learning_task_store", lambda: store)
    monkeypatch.setattr(mistakes, "_ocr_image_with_kimi", lambda *_a, **_k: VisualProblemIR(problem_text="极限"))
    monkeypatch.setattr(mistakes, "_iter_visual_solution_chunks", lambda *_a, **_k: iter(["answer"]))
    monkeypatch.setattr(mistakes, "_link_mistake_concepts", lambda *_a, **_k: [])
    monkeypatch.setattr(mistakes, "_verify_visual_answer", lambda answer, **_: (answer, {"passed": True, "status": "passed"}))
    with monkeypatch.context() as mp:
        mp.setattr(effects, "_apply", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
        response = TestClient(app).post("/api/mistakes/solve-image-stream",
                    files={"file": ("image.png", b"test", "image/png")}, data={"import_to_mistakes": "true"})
    rows = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    final = rows[-1]
    assert final["execution_event"]["type"] == "final"
    assert final["result"]["mistake_id"] == "" and final["result"]["effects_status"] == "pending"
    task_id = final["execution_event"]["task_id"]
    item = store.outcome_effects(task_id)[0]
    store.update_outcome_effect(task_id, item["run_id"], item["id"], retry_at=0)
    effects.recover_task_effects(store, task_id)
    assert store.get(task_id).status == "completed"
    assert store.outcome_effects(task_id)[0]["receipt"]["mistake_id"]
    assert len([e for e in store.get(task_id).artifacts["execution_events"] if e["type"] == "final"]) == 1


@pytest.mark.parametrize("target,method", [(MistakeBook, "add_if_absent"),
                                         (LearningEventStore, "append"), (ConceptMemory, "log_exposure")])
def test_crash_after_each_visual_write_replays_once(isolated, monkeypatch, target, method):
    store, events = isolated
    task = commit(store, kind="visual_feedback")
    original = getattr(target, method)
    with monkeypatch.context() as mp:
        def crash_after(*args, **kwargs):
            original(*args, **kwargs)
            raise Crash()
        mp.setattr(target, method, crash_after)
        with pytest.raises(Crash):
            effects.recover_task_effects(store, task.id)
    effects.recover_task_effects(LearningTaskStore(store.root.parent), task.id)
    assert len(get_mistake_book("default", str(store.root.parent)).list_all()) == 1
    assert len(events.list_recent(event_type="mistake_added")) == 1
    assert ConceptMemory("default")._data["concepts"]["极限"]["exposure_count"] == 1


def test_receipts_survive_display_log_trimming_and_unrelated_writes(isolated):
    store, events = isolated
    task = commit(store)
    effects.recover_task_effects(store, task.id)
    item = store.outcome_effects(task.id)[0]
    memory = ConceptMemory("default")
    # Simulate old display history reaching the existing retention threshold.
    memory._data["exposures"] *= 510
    memory._data["candidate_exposures"] *= 510
    memory._save()
    memory.log_exposure([{"name": "另外概念", "confidence": 1}], "另外概念", operation_id="other")
    memory.log_candidates([{"name": "另外候选", "confidence": .6}], "q", operation_id="other")
    StudyMemory("default").mark_chapter_studied("ch")
    # Replay bypassing the queue receipt exercises the permanent domain receipts.
    effects._apply(item)
    fresh = ConceptMemory("default")
    assert len(fresh._data["exposures"]) == 300
    assert len(fresh._data["candidate_exposures"]) == 300
    assert fresh._data["concepts"]["极限"]["exposure_count"] == 1
    assert fresh._data["candidate_concepts"]["导数"]["seen_count"] == 1
    assert StudyMemory("default").get_chapter_progress("ch")["review_count"] == 2
    assert len(events.list_recent()) == 3


def test_recovery_updates_old_message_without_generating_another_answer(isolated):
    from backend import conversation_memory as cm
    store, _ = isolated
    task = commit(store)
    store.project_outcome(task.id)
    for ordinal in range(25):
        cm.append_message("conv", "assistant", f"following {ordinal}", turn_id=f"later_{ordinal}")
    worker = effects.ExecutionEffectsWorker(store)
    store.recover_unfinished()
    worker.run_once()
    worker.run_once()
    history = cm.load_full_history("conv")
    answer = next(m for m in history if m.get("content") == "answer")
    assert len(history) == 26
    assert answer["learning_task"]["artifacts"]["effects"][0]["status"] == "completed"
    assert len(store.get(task.id).artifacts["execution_events"]) == 1


@pytest.mark.parametrize("field,value", [("run_id", "stale"), ("id", "invented"), ("schema", "old")])
def test_corrupt_effect_identity_is_not_replayed(isolated, field, value):
    store, events = isolated
    task = commit(store)
    task.artifacts["execution_outcome"]["effects"][0][field] = value
    store._persist(task)  # Simulate an externally corrupted disk record.
    effects.ExecutionEffectsWorker(store).run_once()
    assert events.list_recent() == []
    assert not (store.root.parent / "default" / "progress.json").exists()


def test_shutdown_between_domain_steps_leaves_recoverable_receipts(isolated, monkeypatch):
    store, events = isolated
    task = commit(store)
    stop = threading.Event()
    mark = StudyMemory.mark_chapter_studied
    with monkeypatch.context() as mp:
        def stop_after_first(*args, **kwargs):
            mark(*args, **kwargs)
            stop.set()
        mp.setattr(StudyMemory, "mark_chapter_studied", stop_after_first)
        effects.recover_task_effects(store, task.id, stop=stop)
    assert events.list_recent() == []
    assert store.outcome_effects(task.id)[0]["receipt"] is None
    effects.recover_task_effects(store, task.id)
    assert_chat_counts_once(events)


def test_read_task_status_never_executes_pending_effects(isolated, monkeypatch):
    from backend.api import chat
    from backend.main import app
    store, events = isolated
    task = commit(store)
    monkeypatch.setattr(chat, "get_learning_task_store", lambda: store)
    response = TestClient(app).get(f"/api/chat/tasks/{task.id}")
    assert response.status_code == 200
    assert response.json()["learning_task"]["artifacts"]["effects"][0]["status"] == "pending"
    assert events.list_recent() == []


def test_lifespan_starts_and_stops_one_recovery_worker(isolated, monkeypatch):
    import asyncio
    from backend import main, data_backup
    from backend.services import learning_task
    from utils import storage_manifest
    store, _ = isolated
    monkeypatch.setattr(learning_task, "get_learning_task_store", lambda: store)
    monkeypatch.setattr(data_backup, "apply_pending_restore", lambda: None)
    monkeypatch.setattr(storage_manifest, "ensure_storage_manifest", lambda: None)
    monkeypatch.setattr(main.books, "migrate_book_identities", lambda: None)
    monkeypatch.setattr(main, "_recover_jobs", lambda: None)
    monkeypatch.setattr(main, "_start_warmup", lambda: None)
    async def lifecycle():
        async with main.lifespan(main.app):
            worker = main.app.state.execution_effects_worker
            assert worker.thread.is_alive()
        assert not worker.thread.is_alive()
    asyncio.run(lifecycle())


def test_late_terminal_snapshot_cannot_erase_frozen_results_or_receipts(isolated):
    store, events = isolated
    task = commit(store)
    effects.recover_task_effects(store, task.id)
    receipt = store.outcome_effects(task.id)[0]
    task.artifacts["unrelated_projection"] = True
    store.save(task)
    store.checkpoint(task, "late_projection", status="completed")
    assert store.outcome_effects(task.id)[0] == receipt
    effects.recover_task_effects(store, task.id)
    assert_chat_counts_once(events)


@pytest.mark.parametrize("missing", [False, True])
def test_synchronous_image_route_uses_the_same_commit_boundary(isolated, monkeypatch, missing):
    from backend.api import mistakes
    from backend.main import app
    from backend.services.mistake_images import MistakeImageStore
    from backend.services.multimodal_bridge import VisualProblemIR
    store, events = isolated
    images = MistakeImageStore(store.root.parent / "images", frozenset({".png"}), 1000, 1600, 86, 3600)
    monkeypatch.setattr(mistakes, "_image_store", images)
    monkeypatch.setattr(mistakes, "get_learning_task_store", lambda: store)
    visual = VisualProblemIR(problem_text="极限", required_inputs=[{"name": "附表", "blocking": True}] if missing else [])
    monkeypatch.setattr(mistakes, "_ocr_image_with_kimi", lambda *_a, **_k: visual)
    monkeypatch.setattr(mistakes, "_solve_visual_ir", lambda *_a, **_k: "answer")
    monkeypatch.setattr(mistakes, "_link_mistake_concepts", lambda *_a, **_k: [])
    monkeypatch.setattr(mistakes, "_verify_visual_answer", lambda answer, **_: (answer, {"passed": True, "status": "passed"}))
    result = TestClient(app).post("/api/mistakes/solve-image",
             files={"file": ("image.png", b"test", "image/png")}, data={"import_to_mistakes": "true"}).json()
    assert result["success"]
    task = store.get(result["learning_task"]["id"])
    assert task.status == ("waiting_for_input" if missing else "completed")
    assert len(events.list_recent()) == (0 if missing else 1)
    assert bool(store.outcome_effects(task.id)) is not missing
