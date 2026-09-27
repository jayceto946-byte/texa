import sqlite3

from backend.job_manager import JobManager
from memory.exercise_bank import ExerciseBankStore
from memory.learning_events import LearningEventStore
from memory.mistake_book import MistakeBookStore
from utils.sqlite_migrations import apply_sqlite_migrations


def _user_version(path) -> int:
    with sqlite3.connect(path) as conn:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])


def test_core_sqlite_stores_have_explicit_schema_versions(tmp_path):
    exercise_path = tmp_path / "exercise.db"
    mistake_path = tmp_path / "mistake.db"
    event_path = tmp_path / "events.db"
    job_path = tmp_path / "jobs.db"

    ExerciseBankStore(exercise_path)
    MistakeBookStore(mistake_path)
    LearningEventStore(event_path)
    JobManager(job_path)

    assert _user_version(exercise_path) == 1
    assert _user_version(mistake_path) == 2
    assert _user_version(event_path) == 2
    assert _user_version(job_path) == 1


def test_sqlite_migration_runner_applies_steps_once(tmp_path):
    path = tmp_path / "component.db"
    calls = []
    with sqlite3.connect(path) as conn:
        apply_sqlite_migrations(
            conn,
            component="component",
            current_version=2,
            migrations={
                1: lambda db: calls.append(1),
                2: lambda db: (db.execute("CREATE TABLE sample (id TEXT)"), calls.append(2)),
            },
        )
        apply_sqlite_migrations(
            conn,
            component="component",
            current_version=2,
            migrations={1: lambda db: calls.append(1), 2: lambda db: calls.append(2)},
        )
    assert calls == [1, 2]
    assert _user_version(path) == 2


def test_sqlite_migration_runner_rejects_newer_database(tmp_path):
    path = tmp_path / "future.db"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 9")
        try:
            apply_sqlite_migrations(conn, component="future", current_version=1)
        except RuntimeError as exc:
            assert "newer" in str(exc)
        else:
            raise AssertionError("newer database schemas must not be opened silently")


def _database_dump(path):
    with sqlite3.connect(path) as conn:
        return list(conn.iterdump())


def test_runtime_v1_upgrade_and_reopen_preserve_rows(tmp_path):
    from backend.services.agent_runtime.store import RuntimeStore, _schema
    path = tmp_path / 'runtime-v1.db'
    with sqlite3.connect(path) as conn:
        _schema(conn)
        conn.execute("INSERT INTO runtime_tasks VALUES ('legacy', '{}', 'completed', NULL, 1, 2, 1, 'before', 'before')")
        conn.execute('PRAGMA user_version=1')
    RuntimeStore(path)
    assert _user_version(path) == 3
    upgraded = _database_dump(path)
    for _ in range(3):
        RuntimeStore(path)
        assert _database_dump(path) == upgraded
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT consumed_calls, budget_model_calls FROM runtime_tasks WHERE id='legacy'").fetchone() == (1, 0)


def test_runtime_v2_upgrade_repeats_without_duplicate_columns(tmp_path):
    from backend.services.agent_runtime.store import RuntimeStore, _schema, _migrate_v2
    path = tmp_path / 'runtime-v2.db'
    with sqlite3.connect(path) as conn:
        _schema(conn)
        _migrate_v2(conn)
        conn.execute('PRAGMA user_version=2')
    RuntimeStore(path)
    before = _database_dump(path)
    RuntimeStore(path)
    assert _user_version(path) == 3
    assert _database_dump(path) == before


def test_all_component_reopens_are_noop(tmp_path):
    from backend.services.agent_runtime.store import RuntimeStore
    from backend.services.goals.store import GoalStore
    from backend.services.decision.trace import RoutingTraceStore
    for index, (factory, version) in enumerate([
        (RuntimeStore, 3), (GoalStore, 1), (RoutingTraceStore, 2),
        (ExerciseBankStore, 1), (MistakeBookStore, 2), (LearningEventStore, 2), (JobManager, 1),
    ]):
        path = tmp_path / f'component-{index}.db'
        factory(path)
        before = _database_dump(path)
        for _ in range(3):
            factory(path)
            assert _database_dump(path) == before
        assert _user_version(path) == version
