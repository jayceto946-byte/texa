"""Isolated real SQLite writer contention + production SSE delivery witness."""
import asyncio
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true", help="Load only the SSE binding from the fixed audit Git baseline")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="texa-audit-contention-") as directory:
        os.environ.update(DATA_DIR=directory, ENV_PATH=str(Path(directory) / "empty.env"))
        Path(os.environ["ENV_PATH"]).touch()
        from backend.services.agent_runtime import chat_binding as binding
        if args.baseline:
            source = subprocess.check_output([
                "git", "show", "140255ad180b8076c830e5600ca4297942eee105:backend/services/agent_runtime/chat_binding.py",
            ], cwd=Path(__file__).resolve().parents[1]).decode()
            binding = types.ModuleType("backend.services.agent_runtime._audit_before_binding")
            sys.modules[binding.__name__] = binding
            exec(compile(source, "audit-baseline-chat-binding", "exec"), binding.__dict__)
        from backend.services.agent_runtime.store import RuntimeStore
        from backend.services.agent_runtime.contracts import RunCommand
        store = RuntimeStore(Path(directory) / "runtime.db")
        run_id = store.create(RunCommand("r", "r", "t", "s", "turn", "test", "owner"))["run"]["id"]
        store.configure_chat(run_id, "owner", state={}, candidates=[], request_question="test", book_name="", subject="数学")
        registry = binding.build_math_registry()
        locked = threading.Event()
        writing = threading.Event()
        failures = []

        def blocker():
            with sqlite3.connect(store.db_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                locked.set()
                writing.wait(2)
                time.sleep(.3)

        original_delta = store.output_delta

        def output_delta(*args, **kwargs):
            writing.set()  # called under stream_run's delivery lock
            return original_delta(*args, **kwargs)

        store.output_delta = output_delta

        def work(_store, _run, _owner, *_args, on_output):
            try:
                on_output("fixture")
                store.close(run_id, "owner", outcome="paused", error_code="fixture_end")
            except BaseException as error:
                failures.append(str(error))

        binding.execute_run = work
        thread = threading.Thread(target=blocker)
        thread.start()
        locked.wait(2)

        async def measure():
            gaps = []
            done = False

            async def heartbeat():
                while not done:
                    at = time.perf_counter()
                    await asyncio.sleep(.005)
                    gaps.append((time.perf_counter() - at) * 1000)

            ticker = asyncio.create_task(heartbeat())
            await asyncio.sleep(.01)
            response = binding.stream_run(store, run_id, "owner", registry=registry, adapter=object())
            count = 0
            async for _ in response.body_iterator:
                count += 1
            await response.aclose()
            done = True
            await ticker
            return {"max_heartbeat_gap_ms": max(gaps), "heartbeat_gaps_ms": gaps, "requested_heartbeat_ms": 5, "writer_hold_ms": 300, "sse_chunks": count, "worker_errors": failures,
                    "scope": "real isolated SQLite lock + production SSE; execution stub only emits fixture; not a live user latency benchmark"}

        print(json.dumps(asyncio.run(measure()), indent=2))
        thread.join()


if __name__ == "__main__":
    main()
