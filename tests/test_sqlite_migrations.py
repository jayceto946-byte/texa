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
    assert _user_version(mistake_path) == 1
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
