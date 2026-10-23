"""Paired audit microbenchmarks using a fixed Git baseline and synthetic data."""
import gc
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = "140255ad180b8076c830e5600ca4297942eee105"
OUT = ROOT / "docs/qa/performance-reliability-2026-10-23/local-benchmark.json"


def baseline(path):
    source = subprocess.check_output(["git", "show", f"{BASE}:{path}"], cwd=ROOT).decode()
    module = types.ModuleType("audit_before_" + Path(path).stem)
    sys.modules[module.__name__] = module
    exec(compile(source, f"{BASE}:{path}", "exec"), module.__dict__)
    return module


def summary(samples):
    ordered = sorted(samples)
    return {"median_ms": statistics.median(samples), "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * .95))], "samples_ms": samples}


def corpus(count):
    topics = ["导数定义", "误差分类", "积分原理", "矩阵特征值", "传感器比较", "中值定理", "算法应用"]
    return [{"chunk_id": f"chunk-{i}", "chapter": f"第{i % 7}章", "section_title": f"{topics[i % 7]} 第{i % 84}节",
             "section_chunk_index": i % 5, "content": f"{topics[i % 7]}包括三种方法，分别讨论定义、公式和应用。\\(f'(x)=2x\\)。数值示例{i}。" * 5,
             "block_type": "table" if i % 19 == 0 else "paragraph", "table_title": "表1 传感器比较" if i % 19 == 0 else "",
             "retrieval_excluded": i % 97 == 0} for i in range(count)]


def main():
    with tempfile.TemporaryDirectory(prefix="texa-audit-benchmark-") as directory:
        os.environ.update(DATA_DIR=directory, ENV_PATH=str(Path(directory) / "empty.env"))
        Path(os.environ["ENV_PATH"]).touch()
        from ingestion import lexical_index as after
        before = baseline("ingestion/lexical_index.py")
        report = {"baseline_commit": BASE, "kind": "synthetic offline paired microbenchmark; not model or end-to-end latency", "lexical": [], "connections": []}
        queries = ["导数定义是什么", "误差有哪三种方法", "比较传感器和矩阵", "解释积分原理", "推导中值定理", "算法如何应用", "跨章比较导数与积分", "表1 传感器比较"]
        for count in (600, 3000):
            rows = corpus(count)
            for query in queries:
                for chapters in (None, ["第0章", "第2章"]):
                    assert before.search_rows(rows, query, chapters=chapters) == after.search_rows(rows, query, chapters=chapters)
            for query in (queries[0], queries[1]):
                samples = {"before": [], "after": []}
                for round_number in range(9):
                    for label, module in (("before", before), ("after", after)) if round_number % 2 == 0 else (("after", after), ("before", before)):
                        at = time.perf_counter()
                        output = module.search_rows(rows, query)
                        samples[label].append((time.perf_counter() - at) * 1000)
                report["lexical"].append({"rows": count, "query": query, **{label: summary(values) for label, values in samples.items()},
                                          "output_sha256": hashlib.sha256(json.dumps(output, ensure_ascii=False, sort_keys=True).encode()).hexdigest(), "exact_parity_cases": 16})
        from memory.exercise_bank import ExerciseBankStore
        from memory.mistake_book import MistakeBookStore
        for path, current in (("memory/exercise_bank.py", ExerciseBankStore), ("memory/mistake_book.py", MistakeBookStore)):
            old = getattr(baseline(path), current.__name__)
            for label, cls in (("before", old), ("after", current)):
                store = cls(Path(directory) / f"{cls.__name__}-{label}.db")
                connections = []
                gc.collect()
                gc.disable()
                try:
                    started = time.perf_counter()
                    for _ in range(100):
                        with store._connect() as connection:
                            connection.execute("SELECT 1").fetchone()
                            connections.append(connection)
                    duration = (time.perf_counter() - started) * 1000
                    still_open = 0
                    for connection in connections:
                        try:
                            connection.execute("SELECT 1")
                            still_open += 1
                        except Exception:
                            pass
                        finally:
                            connection.close()
                finally:
                    gc.enable()
                report["connections"].append({"store": cls.__name__, "phase": label, "exited_contexts": 100, "connections_still_open": still_open, "total_ms": duration,
                                               "method": "retain connection references, GC disabled to expose deterministic close; not an unbounded production leak claim"})
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
