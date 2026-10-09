"""Compare approved decision modules with the candidate without approving a baseline.

Only synthetic runtime fixtures and isolated temporary stores; no real models.
Output contains hashes, action kinds and counts rather than request/answer text.
"""
import hashlib
import importlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
MODULES = ("router", "policy_projection", "policy")


def capture(approved=False):
    if approved:
        pins = json.loads((ROOT / "docs/validation/runtime-policy-evaluation-dataset-v0/source-manifest.json").read_text())
        for name in MODULES:
            path = f"backend/services/decision/{name}.py"
            source = subprocess.check_output(["git", "show", f"HEAD:{path}"], cwd=ROOT)
            assert hashlib.sha256(source).hexdigest() == pins[path], "HEAD is not the approved source"
            module = importlib.import_module(f"backend.services.decision.{name}")
            exec(compile(source, path, "exec"), module.__dict__)
    from evaluation.runtime_policy_v0 import fixture_runtime
    from backend.services.decision.policy import RulePolicyV0
    from backend.services.decision.policy_projection import project_observation, matched_tool_refs, runtime_identity
    from graph.question_understanding import VERSION
    fixtures = json.loads((ROOT / "evaluation/fixtures/runtime_policy_v0.json").read_text())
    rows = []
    for fixture in fixtures:
        for mode in ("off", "shadow", "fallback"):
            with tempfile.TemporaryDirectory(prefix="texa-policy-compare-") as temporary:
                store, registry, state, refs, context = fixture_runtime(Path(temporary), fixture)
                hint = {"version": VERSION, "accepted": mode == "fallback", "action": "continue",
                        "intent": "quiz", "dimensions": ["exercises"]} if mode != "off" else {}
                state["question_understanding"] = hint
                if not approved:
                    refs, _ = matched_tool_refs(state["user_input"], registry, grounded=fixture["grounded"], understanding=hint)
                snapshot = store.task_snapshot("rtask_fixture")
                frozen = project_observation(request=state["user_input"], resolved_query=state["user_input"], registry=registry,
                    context=context, identity=runtime_identity(snapshot), snapshot=snapshot, answer_state=state, candidate_tools=refs)
                payload = frozen.envelope.payload.model_dump()
                decision = RulePolicyV0(frozen.envelope.payload)
                binding = frozen.bindings[decision.action_id]
                actions = [{"kind": a["kind"], "tool": (a.get("args") or {}).get("tool_id", "")} for a in payload["admissible_actions"]]
                rows.append({"case": fixture["id"], "mode": mode, "actions": actions,
                    "selected_kind": binding["kind"], "selected_tool": (binding.get("args") or {}).get("tool_id", ""),
                    "payload_hash": fingerprint(payload), "bindings_hash": fingerprint(frozen.bindings),
                    "hint_present": "question_understanding" in payload["context"]["constraints"]})
    return rows


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def main():
    sys.path.insert(0, str(ROOT))
    if len(sys.argv) > 1:
        with tempfile.TemporaryDirectory(prefix="texa-policy-compare-env-") as temporary:
            run = Path(temporary)
            for key, suffix in {"DATA_DIR": "data", "PROGRESS_PATH": "progress", "VECTOR_DB_PATH": "vectors", "BOOKS_PATH": "books",
                                "CHAPTERS_PATH": "chapters", "IMAGES_PATH": "images", "MINERU_OUTPUT_PATH": "mineru", "ENV_PATH": "empty.env"}.items():
                os.environ[key] = str(run / suffix)
            (run / "empty.env").touch()
            os.environ.update(QUESTION_UNDERSTANDING_MODE="off", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
            with patch.object(socket.socket, "connect", side_effect=AssertionError("comparison network forbidden")):
                rows = capture(approved=sys.argv[1] == "approved")
            print(json.dumps(rows))
        return
    old, new = [json.loads(subprocess.check_output([sys.executable, __file__, variant], cwd=ROOT)) for variant in ("approved", "candidate")]
    comparisons = [{"case": before["case"], "mode": before["mode"], "payload_equal": before["payload_hash"] == after["payload_hash"],
                    "bindings_equal": before["bindings_hash"] == after["bindings_hash"], "approved": before, "candidate": after}
                   for before, after in zip(old, new)]
    assert all(row["payload_equal"] and row["bindings_equal"] for row in comparisons if row["mode"] in {"off", "shadow"})
    report = {"status": "candidate_not_approved", "boundary": "initial Observation/candidates/decision only; synthetic accepted read hints; not a complete lifecycle or model eval",
              "cases": len(comparisons), "real_model_calls": 0,
              "source_sha256": {f"backend/services/decision/{name}.py": hashlib.sha256((ROOT / f"backend/services/decision/{name}.py").read_bytes()).hexdigest() for name in MODULES},
              "comparisons": comparisons}
    Path(__file__).with_name("policy-comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"cases": len(comparisons), "off_shadow_equal": True, "fallback_payload_changes": sum(not row["payload_equal"] for row in comparisons if row["mode"] == "fallback"), "status": report["status"]}))


if __name__ == "__main__":
    main()
