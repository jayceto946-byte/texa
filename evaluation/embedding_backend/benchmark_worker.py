"""Fresh-process cold/warm/RAM worker for embedding backends."""
from __future__ import annotations

import argparse
import gc
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _windows_memory_info() -> tuple[int, int]:
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)


def rss_bytes() -> int:
    if os.name != "nt":
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    return _windows_memory_info()[0]


def peak_rss_bytes() -> int:
    if os.name != "nt":
        return rss_bytes()
    return _windows_memory_info()[1]


def load_provider(backend: str, onnx_path: Path):
    from evaluation.embedding_backend.providers import ONNXEmbeddingProvider, TorchEmbeddingProvider

    if backend == "torch":
        return TorchEmbeddingProvider(batch_size=32)
    if backend == "onnx":
        return ONNXEmbeddingProvider(onnx_path, batch_size=32)
    raise ValueError(backend)


def representative_batch(entries: list[dict], size: int) -> list[str]:
    """Use a short query for batch=1 and realistic textbook chunks otherwise."""
    if size == 1:
        short = next(item for item in entries if item["category"] == "short_concept")
        return [short["text"]]
    # Current corpus median is about 535 Chinese characters. Normal paragraphs
    # cover shorter rows; formula chunks supply the common 300-900 char range.
    groups = {
        "textbook_paragraph": [item["text"] for item in entries if item["category"] == "textbook_paragraph"],
        "formula_symbol_mix": [
            item["text"] for item in entries
            if item["category"] == "formula_symbol_mix" and len(item["text"]) <= 900
        ],
    }
    values = []
    formula_index = 0
    paragraph_index = 0
    while len(values) < size:
        # 75% medium/formula chunks and 25% normal paragraphs approximate the
        # current indexed corpus without making every row hit 512-token truncation.
        if len(values) % 4 == 3:
            group, index = groups["textbook_paragraph"], paragraph_index
            paragraph_index += 1
        else:
            group, index = groups["formula_symbol_mix"], formula_index
            formula_index += 1
        values.append(group[index % len(group)])
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("torch", "onnx"), required=True)
    parser.add_argument("--mode", choices=("cold", "warm"), required=True)
    parser.add_argument("--onnx-path", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=7)
    args = parser.parse_args()

    process_start = time.perf_counter()
    before_rss = rss_bytes()
    load_start = time.perf_counter()
    provider = load_provider(args.backend, args.onnx_path)
    load_ms = (time.perf_counter() - load_start) * 1000
    after_load_rss = rss_bytes()
    peak_after_load = peak_rss_bytes()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    entries = fixture["texts"]
    texts = [item["text"] for item in entries]

    if args.mode == "cold":
        first_start = time.perf_counter()
        vector = provider.encode(texts[0])
        first_ms = (time.perf_counter() - first_start) * 1000
        peak_after_inference = peak_rss_bytes()
        del vector
        gc.collect()
        stable_rss = rss_bytes()
        payload = {
            "backend": args.backend,
            "load_ms": load_ms,
            "first_embedding_ms": first_ms,
            "internal_total_ms": (time.perf_counter() - process_start) * 1000,
            "rss_before_runtime": before_rss,
            "rss_after_model_load": after_load_rss,
            "peak_rss_after_model_load": peak_after_load,
            "peak_rss_after_embedding": peak_after_inference,
            "rss_stable_after_embedding": stable_rss,
        }
    else:
        provider.encode(representative_batch(entries, 32))
        batches = {}
        for size in (1, 8, 32, 100):
            values = representative_batch(entries, size)
            samples = []
            for _ in range(args.repeats):
                started = time.perf_counter()
                provider.encode(values)
                samples.append((time.perf_counter() - started) * 1000)
            ordered = sorted(samples)
            p95_index = max(0, min(len(ordered) - 1, int(0.95 * (len(ordered) - 1) + 0.999999)))
            median = statistics.median(samples)
            batches[str(size)] = {
                "samples_ms": samples,
                "median_ms": median,
                "p95_ms": ordered[p95_index],
                "median_texts_per_second": size / (median / 1000),
            }
        payload = {
            "backend": args.backend, "repeats": args.repeats,
            "input_profile": "batch=1 short query; batch=8/32/100 fixed 75% <=900-char formula/medium chunks + 25% 50-300-char paragraphs",
            "batches": batches,
        }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
