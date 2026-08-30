import pytest

from backend.services.learning_task import (
    LEARNING_TASK_STATE_CONTRACT,
    LEARNING_TASK_STATUSES,
    LEARNING_TASK_TRANSITIONS,
    TERMINAL_TASK_STATUSES,
    LearningTaskStore,
    interrupt_learning_task,
    resume_learning_task,
)


def test_learning_task_transition_table_is_the_single_status_contract(tmp_path):
    for current in sorted(LEARNING_TASK_STATUSES):
        for target in sorted(LEARNING_TASK_STATUSES):
            store = LearningTaskStore(tmp_path / f"{current}-{target}")
            task = store.create(task_type="qa", goal="test", status=current)
            if target in LEARNING_TASK_TRANSITIONS[current]:
                transitioned = store.checkpoint(task, "transition", status=target)
                assert transitioned.status == target
                assert store.get(task.id).status == target
            else:
                with pytest.raises(
                    ValueError,
                    match=f"invalid learning task transition: {current} -> {target}",
                ):
                    store.checkpoint(task, "transition", status=target)
                assert store.get(task.id).status == current


def test_transition_table_and_public_capabilities_are_derived_from_state_contract(tmp_path):
    assert LEARNING_TASK_STATUSES == frozenset(LEARNING_TASK_STATE_CONTRACT)
    for status, contract in LEARNING_TASK_STATE_CONTRACT.items():
        assert LEARNING_TASK_TRANSITIONS[status] is contract["transitions"]
        public = LearningTaskStore(tmp_path / status).create(
            task_type="qa", goal="test", status=status,
        ).to_dict(public=True)
        assert public["terminal"] is contract["terminal"]
        assert public["interruptible"] is contract["interruptible"]
        assert public["resumable"] is contract["resumable"]
        assert public["input_action_required"] is contract["input_action_required"]
        assert public["confirmation_required"] is contract["confirmation_required"]


def test_degraded_is_terminal_and_cannot_be_interrupted(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(task_type="qa", goal="test", status="degraded")

    public = task.to_dict(public=True)
    assert public["terminal"] is True
    assert public["interruptible"] is False
    assert public["resumable"] is False
    assert public["artifacts"]["resume_available"] is False

    unchanged = interrupt_learning_task(store, task, stage="late_stop", partial_output="late")
    assert unchanged.status == "degraded"
    assert store.get(task.id).status == "degraded"
    assert "partial_output" not in store.get(task.id).artifacts


@pytest.mark.parametrize("terminal_status", sorted(TERMINAL_TASK_STATUSES))
def test_terminal_task_cannot_return_to_running(tmp_path, terminal_status):
    store = LearningTaskStore(tmp_path / terminal_status)
    task = store.create(task_type="qa", goal="test", status=terminal_status)

    with pytest.raises(ValueError, match=f"{terminal_status} -> running"):
        store.checkpoint(task, "invalid_resume", status="running")
    assert store.get(task.id).status == terminal_status


def test_direct_save_cannot_bypass_transition_validation(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(task_type="qa", goal="test")
    task.status = "completed"

    with pytest.raises(ValueError, match="status changes must use checkpoint"):
        store.save(task)
    assert store.get(task.id).status == "running"


def test_interrupt_and_resume_operations_are_idempotent_for_the_same_run(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(
        task_type="qa",
        goal="test",
        artifacts={"active_run_id": "run-old"},
    )

    interrupted = interrupt_learning_task(
        store, task, stage="generate", partial_output="partial", expected_run_id="run-old",
    )
    repeated_interrupt = interrupt_learning_task(
        store, interrupted, stage="generate", expected_run_id="run-old",
    )
    assert interrupted.status == repeated_interrupt.status == "interrupted"
    assert repeated_interrupt.artifacts["partial_output"] == "partial"

    resumed = resume_learning_task(store, repeated_interrupt, run_id="run-new")
    checkpoint_count = len(resumed.checkpoints)
    repeated_resume = resume_learning_task(store, resumed, run_id="run-new")
    assert repeated_resume.status == "running"
    assert repeated_resume.artifacts["active_run_id"] == "run-new"
    assert len(repeated_resume.checkpoints) == checkpoint_count

    with pytest.raises(ValueError, match="already running under another run"):
        resume_learning_task(store, repeated_resume, run_id="run-other")


def test_stale_run_cannot_checkpoint_or_save_over_current_run(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(
        task_type="qa",
        goal="test",
        artifacts={"active_run_id": "run-old"},
    )
    stale = store.get(task.id)
    interrupted = interrupt_learning_task(
        store, task, stage="stopped", expected_run_id="run-old",
    )
    resume_learning_task(store, interrupted, run_id="run-new")

    checkpoint_result = store.checkpoint_for_run(
        stale, "run-old", "late_failure", status="failed",
    )
    stale.artifacts["partial_output"] = "late output"
    save_result = store.save_for_run(stale, "run-old")

    current = store.get(task.id)
    assert checkpoint_result.status == save_result.status == current.status == "running"
    assert current.artifacts["active_run_id"] == "run-new"
    assert current.artifacts.get("partial_output") != "late output"


def test_empty_run_id_cannot_write_run_owned_state(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(task_type="qa", goal="test")
    candidate = store.get(task.id)
    candidate.artifacts["partial_output"] = "must not persist"

    assert store.run_is_active(task.id, "") is False
    store.save_for_run(candidate, "")
    store.checkpoint_for_run(candidate, "", "late", status="failed")
    store.append_execution_event_for_run(task.id, "", {"type": "progress"})

    current = store.get(task.id)
    assert current.status == "running"
    assert "partial_output" not in current.artifacts
    assert "execution_events" not in current.artifacts


def test_empty_run_id_cannot_resume_or_claim_idempotency(tmp_path):
    store = LearningTaskStore(tmp_path)
    task = store.create(
        task_type="qa", goal="test", artifacts={"active_run_id": "run-old"},
    )
    interrupted = interrupt_learning_task(
        store, task, stage="generate", expected_run_id="run-old",
    )

    with pytest.raises(ValueError, match="run_id is required"):
        resume_learning_task(store, interrupted)
    assert store.get(task.id).status == "interrupted"

    resumed = resume_learning_task(store, interrupted, run_id="run-new")
    with pytest.raises(ValueError, match="run_id is required"):
        resume_learning_task(store, resumed)
    current = store.get(task.id)
    assert current.status == "running"
    assert current.artifacts["active_run_id"] == "run-new"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("running", (False, True, False, False, False)),
        ("interrupted", (False, False, True, False, False)),
        ("waiting_for_input", (False, False, False, True, False)),
        ("waiting_for_confirmation", (False, False, False, False, True)),
        ("completed", (True, False, False, False, False)),
        ("degraded", (True, False, False, False, False)),
        ("failed", (True, False, False, False, False)),
        ("cancelled", (True, False, False, False, False)),
    ],
)
def test_public_task_capabilities_follow_the_shared_status_contract(tmp_path, status, expected):
    task = LearningTaskStore(tmp_path / status).create(task_type="qa", goal="test", status=status)
    public = task.to_dict(public=True)

    assert (
        public["terminal"],
        public["interruptible"],
        public["resumable"],
        public["input_action_required"],
        public["confirmation_required"],
    ) == expected
