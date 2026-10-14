import backend.data_backup as backup
from backend.services.agent_runtime.contracts import RunCommand
from backend.services.agent_runtime.lifecycle import RuntimeRecoveryWorker
from backend.services.agent_runtime.store import RuntimeStore
from backend.services.goals.store import GoalStore


def test_desktop_restore_recovers_sql_authority_and_goal_without_replay(tmp_path, monkeypatch):
    data = tmp_path / "data"
    archives = tmp_path / "backups"
    monkeypatch.setattr(backup, "DATA_ROOT", data)
    monkeypatch.setattr(backup, "BACKUP_ROOT", archives)
    monkeypatch.setattr(backup, "MINERU_ROOT", tmp_path / "mineru")
    monkeypatch.setattr(backup, "PENDING_RESTORE_PATH", archives / "pending.json")
    monkeypatch.setattr(backup, "RESTORE_RESULT_PATH", archives / "result.json")
    runtime_path = data / "progress" / "agent_runtime.db"
    runtime = RuntimeStore(runtime_path)
    run_id = runtime.create(RunCommand("key", "req", "rtask_test", "conv", "turn", "Inspect", "owner"))["run"]["id"]
    goals_path = data / "progress" / "goals.db"
    goals = GoalStore(goals_path)
    goal = goals.create(learner_id="local_default", title="复习极限", objective="核对定义")
    saved = backup.create_backup()
    runtime.close(run_id, "owner", outcome="failed", error_code="later")
    goals.update(goal["id"], expected_revision=1, changes={"title": "改变了的标题"})
    backup.schedule_restore(saved["name"])
    assert backup.apply_pending_restore()["status"] == "completed"
    restored = RuntimeStore(runtime_path)
    assert restored.snapshot(run_id)["task"]["status"] == "running"
    worker = RuntimeRecoveryWorker(restored, lambda store: 0)
    assert worker.recover() == 1
    assert restored.snapshot(run_id)["task"]["status"] == "interrupted"
    assert restored.snapshot(run_id)["tool_calls"] == []
    assert GoalStore(goals_path).get(goal["id"])["title"] == "复习极限"
    assert worker.recover() == 0
