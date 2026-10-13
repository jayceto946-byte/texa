"""Export synthetic QA Runtime evidence, never the user's production databases."""
import argparse
import json
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qa-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/qa/evidence/native-tool-loop/runtime-traces.json"))
    args = parser.parse_args()
    root = args.qa_root.resolve()
    if not root.is_relative_to(Path("/private/tmp")):
        parser.error("only isolated /private/tmp QA data can be exported")
    with sqlite3.connect(f"file:{root}/progress/agent_runtime.db?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        runs = []
        for row in conn.execute("SELECT * FROM agent_runs ORDER BY created_at"):
            task = conn.execute("SELECT * FROM runtime_tasks WHERE id=?", (row["task_id"],)).fetchone()
            calls = []
            for call in conn.execute("SELECT * FROM tool_calls WHERE task_id=? ORDER BY step_index", (row["task_id"],)):
                calls.append({key: call[key] for key in ("id", "requested_run_id", "executed_run_id", "tool_id", "operation_key", "status", "error_code")} |
                    {"args": json.loads(call["args_json"]), "result": json.loads(call["result_json"]) if call["result_json"] else None})
            checkpoint = json.loads(row["checkpoint_json"])
            snapshot = json.loads(task["snapshot_json"])
            runs.append({"run_id": row["id"], "task_id": row["task_id"], "session_id": row["conversation_id"],
                "turn_id": row["turn_id"], "question": snapshot["goal"], "run_status": row["status"], "task_status": task["status"],
                "model_calls": task["consumed_model_calls"], "tool_calls": calls,
                "native_messages": checkpoint.get("native_messages", []),
                "answer": json.loads(row["output_json"]) if row["output_json"] else None,
                "events": [json.loads(event[0]) for event in conn.execute("SELECT event_json FROM execution_events WHERE run_id=? ORDER BY seq", (row["id"],))]})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"model": "controlled LangChain interface; no remote calls", "math": "real isolated SymPy", "runs": runs}, ensure_ascii=False, indent=2))
    print(json.dumps([{"question": run["question"], "run_id": run["run_id"], "models": run["model_calls"], "tools": len(run["tool_calls"]), "status": run["task_status"]} for run in runs], ensure_ascii=False))


if __name__ == "__main__":
    main()
