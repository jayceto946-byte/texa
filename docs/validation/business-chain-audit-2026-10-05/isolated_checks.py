"""Run existing offline contracts in fresh data roots; deny network connections.

Usage: venv310/bin/python .../isolated_checks.py core|assets|runtime|policy
Logs/results live beside this script. No live models or production DBs are used.
"""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
GROUPS = {
    "core": ["sensor_refusal_regressions", "answer_verification", "evidence_pack", "citation_pipeline",
             "session_notes", "exercise_bank", "context_eval_v3", "question_understanding"],
    "assets": ["textbook_workflow_repairs", "canonical_index_publication", "acceptance_probes",
               "book_chapter_service", "figure_learning", "textbook_exercise_importer"],
    "runtime": ["chat_stream_reliability", "chat_execution_parity", "learning_task_state_machine",
                "agent_runtime_chat_binding", "agent_runtime_p2_write_service", "agent_runtime_p2_recovery",
                "goal_execution", "agent_goals_p3", "mistake_lifecycle", "overview_endpoints",
                "agent_runtime_backup", "backup_manifest_validation"],
    "policy": ["policy_dataset_v0"],
}


def main():
    group = sys.argv[1]
    assert group in GROUPS and sys.version_info[:2] == (3, 10)
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    with tempfile.TemporaryDirectory(prefix="texa-audit-checks-") as temporary:
        root = Path(temporary)
        for key, suffix in {"DATA_DIR": "data", "PROGRESS_PATH": "progress", "VECTOR_DB_PATH": "vectors",
                            "BOOKS_PATH": "books", "CHAPTERS_PATH": "chapters", "IMAGES_PATH": "images",
                            "MINERU_OUTPUT_PATH": "mineru", "ENV_PATH": "empty.env"}.items():
            os.environ[key] = str(root / suffix)
        (root / "empty.env").touch()
        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", ANONYMIZED_TELEMETRY="False",
                          QUESTION_UNDERSTANDING_MODE="off")
        import pytest
        with patch.object(socket.socket, "connect", side_effect=AssertionError("audit network forbidden")):
            status = pytest.main(["-q", "--tb=short", *[f"tests/test_{name}.py" for name in GROUPS[group]]])
    Path(__file__).with_name(f"{group}-exit.json").write_text(json.dumps({"group": group, "exit_code": int(status), "python": sys.version.split()[0], "network": "connect denied", "data": "ephemeral isolated root"}, indent=2) + "\n")
    raise SystemExit(status)


if __name__ == "__main__":
    main()
