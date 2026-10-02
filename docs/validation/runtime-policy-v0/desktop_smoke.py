"""Isolated native Electron backend startup/recovery smoke; no model calls."""
from pathlib import Path
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
ELECTRON = ROOT / "desktop/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron"
OUTPUT = ROOT / "docs/validation/runtime-policy-v0/desktop-smoke.json"


def main():
    report = {"scope": "native Electron development entry, temporary userData, no real model or user records", "launches": []}
    with tempfile.TemporaryDirectory(prefix="texa-policy-desktop-") as directory:
        user_data = Path(directory)
        (user_data / ".env").write_text("")
        # Deliberately exclude provider, path, proxy and credential environment.
        env = {key: value for key, value in os.environ.items() if key in {
            "HOME", "PATH", "TMPDIR", "LANG", "USER", "LOGNAME", "SHELL"}}
        env.update({"KAOYAN_USER_DATA_DIR": str(user_data), "DATA_DIR": str(user_data / "data"),
            "ENV_PATH": str(user_data / ".env"), "KAOYAN_PYTHON": str(ROOT / "venv310/bin/python"),
            "KAOYAN_API_TOKEN": "isolated-policy-smoke-token", "KAOYAN_INSTANCE_ID": "policy-smoke",
            "SKIP_EMBEDDING_WARMUP": "1", "SKIP_VECTOR_WARMUP": "1",
            "TEXA_EMBEDDING_ASSET_DIR": str(ROOT / "assets/embedding-runtime/bge-small-zh-v1.5/onnx-fp32-v1"),
            "TEXA_RUNTIME_POLICY_V0": "1", "TEXA_AGENT_RUNTIME_READ": "1"})
        seed = '''from backend.services.agent_runtime.store import RuntimeStore, DEFAULT_RUNTIME_DB_PATH
from backend.services.agent_runtime.contracts import RunCommand
store=RuntimeStore(DEFAULT_RUNTIME_DB_PATH)
snapshot=store.create(RunCommand("desktop-seed", "req_seed", "rtask_desktop_seed", "conv_fixture", "turn_fixture", "最近学习进度如何", "seed_owner", budget_calls=3, budget_model_calls=2))
store.configure_chat(snapshot["run"]["id"], "seed_owner", state={"user_input":"最近学习进度如何", "answer_mode":"global_general", "use_textbook_context":False}, candidates=(), request_question="最近学习进度如何", book_name="", subject="", policy_baseline=True)
'''
        subprocess.run([str(ROOT / "venv310/bin/python"), "-c", seed], env=env, cwd=ROOT, check=True, capture_output=True)
        for index in range(2):
            with socket.socket() as server:
                server.bind(("127.0.0.1", 0))
                port = server.getsockname()[1]
            env["KAOYAN_BACKEND_PORT"] = str(port)
            console = user_data / f"electron-{index}.log"
            with console.open("w") as log:
                app = subprocess.Popen([str(ELECTRON), str(ROOT / "desktop")], cwd=ROOT, env=env, stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 40
                    health = None
                    while time.monotonic() < deadline:
                        if app.poll() is not None:
                            raise RuntimeError(f"Electron exited before backend health: {app.returncode}")
                        try:
                            request = urllib.request.Request(f"http://127.0.0.1:{port}/health", headers={"X-Kaoyan-Token": env["KAOYAN_API_TOKEN"]})
                            health = json.load(urllib.request.urlopen(request, timeout=1))
                            break
                        except (OSError, ValueError):
                            time.sleep(.2)
                    if health is None:
                        raise RuntimeError("backend startup deadline exceeded")
                    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/chat/tasks/rtask_desktop_seed", headers={"X-Kaoyan-Token": env["KAOYAN_API_TOKEN"]})
                    task = json.load(urllib.request.urlopen(request, timeout=2))["learning_task"]
                    assert task["status"] == "interrupted" and task["resumable"] is True
                    # Read only the isolated database, through the existing snapshot API.
                    inspect = '''import json
from backend.services.agent_runtime.store import RuntimeStore, DEFAULT_RUNTIME_DB_PATH
s=RuntimeStore(DEFAULT_RUNTIME_DB_PATH).task_snapshot("rtask_desktop_seed")
print(json.dumps({"baseline":s["run"]["checkpoint"].get("policy_baseline"), "tools":s["consumed_calls"], "models":s["consumed_model_calls"], "events":len(s["execution_events"])}))'''
                    snapshot = json.loads(subprocess.check_output([str(ROOT / "venv310/bin/python"), "-c", inspect], env=env, cwd=ROOT, text=True))
                    assert snapshot["baseline"] == "texa.runtime-policy/v0" and snapshot["tools"] == snapshot["models"] == 0
                    report["launches"].append({"launch": index + 1, "backend_health": health["status"], "instance_matches": health.get("instance_id") == "policy-smoke",
                        "task_status": task["status"], "resumable": task["resumable"], **snapshot})
                finally:
                    if app.poll() is None:
                        app.send_signal(signal.SIGTERM)
                        try:
                            app.wait(timeout=12)
                        except subprocess.TimeoutExpired:
                            app.kill()
                            app.wait(timeout=3)
                    # The app owns this backend. Shut down only this authenticated
                    # isolated instance if SIGTERM did not already close it.
                    try:
                        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/system/shutdown", method="POST", headers={"X-Kaoyan-Token": env["KAOYAN_API_TOKEN"]})
                        urllib.request.urlopen(request, timeout=2).close()
                    except OSError:
                        pass
    report["passed"] = len(report["launches"]) == 2 and all(item["instance_matches"] for item in report["launches"])
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
