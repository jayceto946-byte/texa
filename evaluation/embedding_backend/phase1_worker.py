"""Isolated worker for ONNX FP32 Phase 1 throughput experiments.

This module is benchmark-only. It never imports or mutates the production
embedding singleton, Chroma, BM25, the KG, or the reranker.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import statistics
import sys
import threading
import time
from collections import defaultdict
from ctypes import wintypes
from pathlib import Path
from typing import Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.embedding_backend.providers import ONNXEmbeddingProvider, TorchEmbeddingProvider

PARITY_PATH = ROOT / "evaluation" / "datasets" / "embedding_parity.json"
RETRIEVAL_PATH = ROOT / "evaluation" / "datasets" / "embedding_retrieval.json"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return float(ordered[index])


def physical_core_count() -> int:
    """Count Windows processor-core relationship records without WMI/psutil."""
    if os.name != "nt":
        return max(1, (os.cpu_count() or 1) // 2)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_info = kernel32.GetLogicalProcessorInformationEx
    get_info.argtypes = [wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    get_info.restype = wintypes.BOOL
    needed = wintypes.DWORD(0)
    relation_all = 0xFFFF
    get_info(relation_all, None, ctypes.byref(needed))
    if not needed.value:
        return max(1, (os.cpu_count() or 1) // 2)
    buffer = ctypes.create_string_buffer(needed.value)
    if not get_info(relation_all, buffer, ctypes.byref(needed)):
        return max(1, (os.cpu_count() or 1) // 2)
    offset = 0
    cores = 0
    while offset + 8 <= needed.value:
        relationship = ctypes.c_uint32.from_buffer(buffer, offset).value
        size = ctypes.c_uint32.from_buffer(buffer, offset + 4).value
        if not size:
            break
        if relationship == 0:  # RelationProcessorCore
            cores += 1
        offset += size
    return cores or max(1, (os.cpu_count() or 1) // 2)


if os.name == "nt":
    class _ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    class _ThreadEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD), ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG), ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]


def rss_bytes() -> int:
    if os.name != "nt":
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(_ProcessMemoryCounters), wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    if not psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(counters.WorkingSetSize)


def native_thread_count() -> int:
    if os.name != "nt":
        return threading.active_count()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32)]
    kernel32.Thread32First.restype = wintypes.BOOL
    kernel32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ThreadEntry32)]
    kernel32.Thread32Next.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000004, 0)
    invalid = ctypes.c_void_p(-1).value
    if snapshot == invalid:
        return 0
    entry = _ThreadEntry32()
    entry.dwSize = ctypes.sizeof(entry)
    count = 0
    pid = os.getpid()
    try:
        ok = kernel32.Thread32First(snapshot, ctypes.byref(entry))
        while ok:
            if entry.th32OwnerProcessID == pid:
                count += 1
            ok = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return count


def _filetime_value(value) -> int:
    return (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)


def system_cpu_times() -> tuple[int, int]:
    """Return total and idle 100-ns ticks aggregated across logical CPUs."""
    if os.name != "nt":
        return 0, 0
    idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    ctypes.WinDLL("kernel32").GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
    )
    idle_value = _filetime_value(idle)
    return _filetime_value(kernel) + _filetime_value(user), idle_value


class ResourceSampler:
    def __init__(self, interval: float = 0.025):
        self.interval = interval
        self.peak_rss = 0
        self.max_threads = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self):
        self.peak_rss = rss_bytes()
        self.max_threads = native_thread_count()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self):
        while not self._stop.wait(self.interval):
            self.peak_rss = max(self.peak_rss, rss_bytes())

    def __exit__(self, exc_type, exc, tb):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        self.peak_rss = max(self.peak_rss, rss_bytes())
        self.max_threads = max(self.max_threads, native_thread_count())


def measure(call: Callable[[], object]) -> tuple[object, dict]:
    with ResourceSampler() as sampler:
        process_start = time.process_time()
        system_start, idle_start = system_cpu_times()
        started = time.perf_counter()
        result = call()
        wall = time.perf_counter() - started
        process_cpu = time.process_time() - process_start
        system_end, idle_end = system_cpu_times()
    logical = max(1, os.cpu_count() or 1)
    system_delta = system_end - system_start
    system_busy = system_delta - (idle_end - idle_start)
    cpu_sample_reliable = wall >= 0.02 and process_cpu > 0
    telemetry = {
        "latency_ms": wall * 1000,
        "process_cpu_ms": process_cpu * 1000,
        "effective_cpu_cores": process_cpu / wall if cpu_sample_reliable else None,
        "process_cpu_percent_of_machine": process_cpu / wall / logical * 100 if cpu_sample_reliable else None,
        "system_cpu_percent": system_busy / system_delta * 100 if system_delta > 0 and wall >= 0.02 else None,
        "cpu_sample_reliable": cpu_sample_reliable,
        "peak_rss_bytes": sampler.peak_rss,
        "max_native_threads": sampler.max_threads,
    }
    return result, telemetry


def summarize_samples(samples: list[dict], text_count: int) -> dict:
    latencies = [item["latency_ms"] for item in samples]
    median_ms = statistics.median(latencies)
    fields = (
        "effective_cpu_cores", "process_cpu_percent_of_machine", "system_cpu_percent",
        "peak_rss_bytes", "max_native_threads",
    )
    result = {
        "warm_runs": len(samples),
        "samples": samples,
        "median_ms": median_ms,
        "p95_ms": percentile(latencies, 0.95),
        "texts_per_second": text_count / (median_ms / 1000),
    }
    for field in fields:
        values = [float(item[field]) for item in samples if item.get(field) is not None]
        result[f"{field}_median"] = statistics.median(values) if values else None
        result[f"{field}_p95"] = percentile(values, 0.95) if values else None
    return result


def load_fixture(path: Path, key: str) -> tuple[list[dict], list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload[key]
    return entries, [str(item["text"]) for item in entries]


def representative_batch(entries: list[dict], size: int) -> list[str]:
    if size == 1:
        return [next(item["text"] for item in entries if item["category"] == "short_concept")]
    groups = {
        "textbook_paragraph": [item["text"] for item in entries if item["category"] == "textbook_paragraph"],
        "formula_symbol_mix": [
            item["text"] for item in entries
            if item["category"] == "formula_symbol_mix" and len(item["text"]) <= 900
        ],
    }
    values: list[str] = []
    formula_index = paragraph_index = 0
    while len(values) < size:
        if len(values) % 4 == 3:
            group, index = groups["textbook_paragraph"], paragraph_index
            paragraph_index += 1
        else:
            group, index = groups["formula_symbol_mix"], formula_index
            formula_index += 1
        values.append(group[index % len(group)])
    return values


def cycle_to_size(values: list[str], size: int) -> list[str]:
    if not values:
        raise RuntimeError("Input profile has no matching texts")
    return [values[index % len(values)] for index in range(size)]


def build_provider(args):
    if args.backend == "torch":
        return TorchEmbeddingProvider(batch_size=args.batch_size, num_threads=args.torch_threads)
    return ONNXEmbeddingProvider(
        args.onnx_path,
        batch_size=args.batch_size,
        intra_op_threads=args.intra,
        inter_op_threads=args.inter,
        execution_mode=args.execution_mode,
        graph_optimization_level=args.graph_optimization,
    )


def token_lengths(provider, texts: list[str]) -> list[int]:
    if isinstance(provider, ONNXEmbeddingProvider):
        encoded = provider.tokenizer.encode_batch(texts)
        return [int(sum(item.attention_mask)) for item in encoded]
    encoded = provider.model.tokenizer(
        texts, padding=True, truncation=True, max_length=512, return_tensors="np"
    )
    return [int(value) for value in np.sum(encoded["attention_mask"], axis=1)]


def plan_padding(lengths: list[int], plan: list[list[int]]) -> dict:
    actual = sum(lengths)
    padded = sum(max(lengths[index] for index in batch) * len(batch) for batch in plan if batch)
    return {
        "min_token_length": min(lengths),
        "median_token_length": statistics.median(lengths),
        "max_token_length": max(lengths),
        "total_real_tokens": actual,
        "total_padded_tokens": padded,
        "padding_ratio": padded / actual if actual else 0.0,
        "padding_waste_fraction": (padded - actual) / padded if padded else 0.0,
    }


def contiguous_plan(count: int, batch_size: int) -> list[list[int]]:
    return [list(range(start, min(count, start + batch_size))) for start in range(0, count, batch_size)]


def sorted_plan(lengths: list[int], batch_size: int) -> list[list[int]]:
    ordered = sorted(range(len(lengths)), key=lambda index: lengths[index])
    return [ordered[start : start + batch_size] for start in range(0, len(ordered), batch_size)]


def bucket_plan(lengths: list[int], batch_size: int) -> list[list[int]]:
    buckets: dict[int, list[int]] = defaultdict(list)
    for index, length in enumerate(lengths):
        bucket = 64 if length <= 64 else 128 if length <= 128 else 256 if length <= 256 else 512
        buckets[bucket].append(index)
    plan: list[list[int]] = []
    for bucket in (64, 128, 256, 512):
        values = buckets[bucket]
        plan.extend(values[start : start + batch_size] for start in range(0, len(values), batch_size))
    return plan


def execute_plan(provider, texts: list[str], plan: list[list[int]]) -> np.ndarray:
    output = np.empty((len(texts), 512), dtype=np.float32)
    for indices in plan:
        batch = [texts[index] for index in indices]
        if isinstance(provider, ONNXEmbeddingProvider):
            values = provider._encode_batch(batch)
        else:
            values = provider.model.encode(
                batch,
                batch_size=len(batch),
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            ).astype(np.float32, copy=False)
        output[indices] = values
    return output


def benchmark_case(provider, texts: list[str], plan: list[list[int]], repeats: int) -> dict:
    execute_plan(provider, texts, plan)  # one untimed warm-up before warm runs
    samples: list[dict] = []
    for _ in range(repeats):
        _, telemetry = measure(lambda: execute_plan(provider, texts, plan))
        samples.append(telemetry)
    result = summarize_samples(samples, len(texts))
    result["tokens"] = plan_padding(token_lengths(provider, texts), plan)
    result["batch_sizes"] = [len(batch) for batch in plan]
    return result


def task_scaling(args, provider) -> dict:
    entries, _ = load_fixture(PARITY_PATH, "texts")
    cases = {}
    for size in args.sizes:
        texts = representative_batch(entries, size)
        cases[str(size)] = benchmark_case(provider, texts, [list(range(size))], args.repeats)
        print(f"progress scaling {args.backend} batch={size}", file=sys.stderr, flush=True)
    return {"task": "scaling", "backend": args.backend, "cases": cases}


def task_profiles(args, provider) -> dict:
    parity_entries, parity_texts = load_fixture(PARITY_PATH, "texts")
    _, corpus_texts = load_fixture(RETRIEVAL_PATH, "corpus")
    profile_sources = {
        "short": [text for text in parity_texts + corpus_texts if 10 <= len(text) <= 50],
        "normal": [text for text in corpus_texts if 50 <= len(text) <= 300],
        "long": [text for text in corpus_texts if len(text) >= 1000],
    }
    cases = {}
    for profile, source in profile_sources.items():
        cases[profile] = {}
        for size in args.profile_sizes:
            texts = cycle_to_size(source, size)
            cases[profile][str(size)] = benchmark_case(provider, texts, [list(range(size))], args.repeats)
            print(f"progress profile {args.backend} {profile} batch={size}", file=sys.stderr, flush=True)
    return {
        "task": "profiles", "backend": args.backend,
        "profile_definition": {"short": "10-50 chars", "normal": "50-300 chars", "long": ">=1000 chars"},
        "source_counts": {key: len(value) for key, value in profile_sources.items()},
        "cases": cases,
    }


def task_micro(args, provider) -> dict:
    entries, _ = load_fixture(PARITY_PATH, "texts")
    texts = representative_batch(entries, 100)
    named_sizes = {
        "100": [100], "64+36": [64, 36], "50+50": [50, 50],
        "32+32+32+4": [32, 32, 32, 4], "25x4": [25, 25, 25, 25],
        "16x6+4": [16, 16, 16, 16, 16, 16, 4],
        "8x12+4": [8] * 12 + [4],
    }
    cases = {}
    for name, sizes in named_sizes.items():
        plan: list[list[int]] = []
        start = 0
        for size in sizes:
            plan.append(list(range(start, start + size)))
            start += size
        cases[name] = benchmark_case(provider, texts, plan, args.repeats)
        print(f"progress micro {name}", file=sys.stderr, flush=True)
    return {"task": "micro", "backend": args.backend, "same_texts_same_order": True, "cases": cases}


def task_strategies(args, provider) -> dict:
    fixture = json.loads(RETRIEVAL_PATH.read_text(encoding="utf-8"))
    texts = [item["text"] for item in fixture["corpus"]]
    lengths = token_lengths(provider, texts)
    plans = {
        "naive": contiguous_plan(len(texts), args.batch_size),
        "length_sorted": sorted_plan(lengths, args.batch_size),
        "length_bucket": bucket_plan(lengths, args.batch_size),
    }
    cases = {}
    reference: np.ndarray | None = None
    for name, plan in plans.items():
        values = execute_plan(provider, texts, plan)
        if reference is None:
            reference = values
        order_cosine = np.sum(reference * values, axis=1) / (
            np.linalg.norm(reference, axis=1) * np.linalg.norm(values, axis=1)
        )
        result = benchmark_case(provider, texts, plan, args.repeats)
        result["output_order_cosine_min"] = float(np.min(order_cosine))
        cases[name] = result
        print(f"progress strategy {name}", file=sys.stderr, flush=True)
    return {
        "task": "strategies", "backend": args.backend,
        "corpus_count": len(texts), "corpus_source": fixture.get("corpus_source"),
        "batch_size": args.batch_size, "cases": cases,
    }


def task_breakdown(args, provider) -> dict:
    if not isinstance(provider, ONNXEmbeddingProvider):
        raise RuntimeError("Breakdown is defined for the ONNX provider")
    entries, _ = load_fixture(PARITY_PATH, "texts")
    cases = {}
    for size in args.breakdown_sizes:
        texts = representative_batch(entries, size)
        # One complete untimed warm-up.
        provider._encode_batch(texts)
        samples = []
        for _ in range(args.repeats):
            started_total = time.perf_counter()
            started = time.perf_counter()
            encoded = provider.tokenizer.encode_batch(texts)
            tokenization_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            inputs = {
                "input_ids": np.asarray([item.ids for item in encoded], dtype=np.int64),
                "attention_mask": np.asarray([item.attention_mask for item in encoded], dtype=np.int64),
                "token_type_ids": np.asarray([item.type_ids for item in encoded], dtype=np.int64),
            }
            numpy_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            raw = provider.session.run(["sentence_embedding"], inputs)[0]
            session_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            output = raw.astype(np.float32, copy=False)
            result_ms = (time.perf_counter() - started) * 1000
            samples.append({
                "tokenization_ms": tokenization_ms,
                "numpy_input_ms": numpy_ms,
                "ort_session_ms": session_ms,
                "pooling_normalization_outside_graph_ms": 0.0,
                "result_conversion_ms": result_ms,
                "total_ms": (time.perf_counter() - started_total) * 1000,
                "shape": list(output.shape),
            })
        summary = {}
        for field in (
            "tokenization_ms", "numpy_input_ms", "ort_session_ms",
            "pooling_normalization_outside_graph_ms", "result_conversion_ms", "total_ms",
        ):
            values = [item[field] for item in samples]
            summary[field] = {"median": statistics.median(values), "p95": percentile(values, 0.95)}
        cases[str(size)] = {"warm_runs": args.repeats, "samples": samples, "summary": summary}
        print(f"progress breakdown batch={size}", file=sys.stderr, flush=True)
    return {"task": "breakdown", "backend": args.backend, "cases": cases}


def task_ingestion(args, provider) -> dict:
    fixture = json.loads(RETRIEVAL_PATH.read_text(encoding="utf-8"))
    texts = [item["text"] for item in fixture["corpus"]]
    lengths = token_lengths(provider, texts)
    if args.strategy == "naive":
        plan = contiguous_plan(len(texts), args.batch_size)
    elif args.strategy == "length_sorted":
        plan = sorted_plan(lengths, args.batch_size)
    elif args.strategy == "length_bucket":
        plan = bucket_plan(lengths, args.batch_size)
    else:
        raise ValueError(args.strategy)
    result = benchmark_case(provider, texts, plan, args.repeats)
    return {
        "task": "ingestion", "backend": args.backend, "strategy": args.strategy,
        "batch_size": args.batch_size, "corpus_count": len(texts),
        "corpus_source": fixture.get("corpus_source"), "result": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=("scaling", "profiles", "micro", "strategies", "breakdown", "ingestion"), required=True)
    parser.add_argument("--backend", choices=("torch", "onnx"), required=True)
    parser.add_argument("--onnx-path", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--torch-threads", type=int, default=2)
    parser.add_argument("--intra", type=int, default=2)
    parser.add_argument("--inter", type=int, default=1)
    parser.add_argument("--execution-mode", choices=("sequential", "parallel"), default="sequential")
    parser.add_argument("--graph-optimization", choices=("disable", "basic", "extended", "all"), default="all")
    parser.add_argument("--strategy", choices=("naive", "length_sorted", "length_bucket"), default="naive")
    parser.add_argument("--sizes", type=int, nargs="+", default=[1, 4, 8, 16, 24, 32, 48, 64, 96, 100, 128])
    parser.add_argument("--profile-sizes", type=int, nargs="+", default=[8, 16, 32, 64, 100])
    parser.add_argument("--breakdown-sizes", type=int, nargs="+", default=[1, 32, 100])
    args = parser.parse_args()
    args.onnx_path = args.onnx_path.resolve()
    provider = build_provider(args)
    tasks = {
        "scaling": task_scaling,
        "profiles": task_profiles,
        "micro": task_micro,
        "strategies": task_strategies,
        "breakdown": task_breakdown,
        "ingestion": task_ingestion,
    }
    result = tasks[args.task](args, provider)
    result["environment"] = {
        "logical_cpu_count": os.cpu_count(),
        "physical_cpu_core_count": physical_core_count(),
        "provider": getattr(provider, "backend_name", args.backend),
        "session_options": getattr(provider, "session_options", None),
        "torch_threads": args.torch_threads if args.backend == "torch" else None,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
