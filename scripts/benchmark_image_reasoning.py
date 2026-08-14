"""Benchmark image reasoning policies against one fixed Kimi Visual IR."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from backend.services.multimodal_bridge import KimiVisionBridge, VisualProblemIR, build_solution_prompt
from backend.services.mistake_images import MistakeImageStore
from config import DEEPSEEK_API_BASE, DEEPSEEK_API_KEY, DEEPSEEK_MODEL_NAME, _get_chat_model
from utils.latex_sanitizer import sanitize_latex
from utils.thinking_filter import ThinkingFilter


def _stream_answer(prompt: str, effort: str, *, model_name: str | None = None) -> tuple[str, dict]:
    started = time.perf_counter()
    first_visible_ms: float | None = None
    last_progress = started
    chunks: list[str] = []
    thinking_filter = ThinkingFilter()
    effective_model = model_name or DEEPSEEK_MODEL_NAME
    model = _get_chat_model(
        effective_model,
        1,
        DEEPSEEK_API_KEY,
        DEEPSEEK_API_BASE,
        extra_body={
            "reasoning_effort": effort,
            "thinking": {"type": "enabled"},
        },
        request_timeout=420,
        max_retries=0,
    )
    progress_label = f"{effective_model}/{effort}"
    print(f"[{progress_label}] request started", flush=True)
    for chunk in model.stream(prompt):
        now = time.perf_counter()
        clean = thinking_filter.filter(str(getattr(chunk, "content", "") or ""))
        if clean:
            if first_visible_ms is None:
                first_visible_ms = round((now - started) * 1000, 2)
                print(f"[{progress_label}] first visible answer: {first_visible_ms / 1000:.2f}s", flush=True)
            chunks.append(clean)
        if now - last_progress >= 20:
            print(f"[{progress_label}] still running: {now - started:.1f}s", flush=True)
            last_progress = now
    tail = thinking_filter.flush()
    if tail:
        if first_visible_ms is None:
            first_visible_ms = round((time.perf_counter() - started) * 1000, 2)
        chunks.append(tail)
    total_ms = round((time.perf_counter() - started) * 1000, 2)
    answer = sanitize_latex("".join(chunks).strip())
    metrics = {
        "reasoning_effort": effort,
        "thinking_enabled": True,
        "model": effective_model,
        "first_visible_ms": first_visible_ms,
        "total_ms": total_ms,
        "answer_chars": len(answer),
    }
    print(f"[{progress_label}] completed: {total_ms / 1000:.2f}s, {len(answer)} chars", flush=True)
    return answer, metrics


def _write_report(output_dir: Path, benchmark: dict, answers: dict[str, str]) -> None:
    report_lines = [
        "# 图片推理强度基准",
        "",
        f"- 图片：`{benchmark['image_path']}`",
        f"- Kimi：`{benchmark['kimi']['model']}`，关闭 thinking，仅抽取 Visual IR",
        f"- Kimi 视觉抽取：{benchmark['kimi']['total_ms'] / 1000:.2f} 秒",
        "- 所有 DeepSeek 运行均使用同一 Visual IR 与同一 prompt",
        "",
        "| 模式 | 首段可见答案 | 完整生成 | 答案字符数 |",
        "|---|---:|---:|---:|",
    ]
    run_order = [
        ("medium", "V4 Pro medium + thinking"),
        ("high", "V4 Pro high + thinking"),
        ("flash_high", "V4 Flash high + thinking（第 1 次）"),
        ("flash_high_retry", "V4 Flash high + thinking（第 2 次）"),
    ]
    available_runs = [(key, label) for key, label in run_order if key in benchmark["runs"]]
    for key, label in available_runs:
        item = benchmark["runs"][key]
        first = item["first_visible_ms"]
        report_lines.append(
            f"| {label} | {first / 1000:.2f} 秒 | "
            f"{item['total_ms'] / 1000:.2f} 秒 | {item['answer_chars']} |"
        )
    comparison = benchmark.get("comparison")
    if comparison:
        report_lines.extend(["", "## 对比结论", ""])
        report_lines.extend(f"- {item}" for item in comparison.get("summary", []))
        report_lines.extend(
            [
                "",
                "| 维度 | Pro medium | Pro high | Flash high #1 | Flash high #2 |",
                "|---|---|---|---|---|",
            ]
        )
        for item in comparison.get("quality", []):
            report_lines.append(
                f"| {item['dimension']} | {item['medium']} | {item['high']} | "
                f"{item['flash_high']} | {item.get('flash_high_retry', '—')} |"
            )
        if comparison.get("caveat"):
            report_lines.extend(["", f"> {comparison['caveat']}"])
    for key, label in available_runs:
        report_lines.extend(["", f"## {label} 解答", "", answers[key]])
    (output_dir / "report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path, nargs="?")
    parser.add_argument("--subject", default="传感器")
    parser.add_argument("--question", default="请完整解答图中四个小问，给出必要公式、计算过程和最终结果。")
    parser.add_argument("--output-root", type=Path, default=Path("data/eval"))
    parser.add_argument("--rebuild-dir", type=Path)
    parser.add_argument("--append-model")
    parser.add_argument("--append-key", default="flash_high")
    parser.add_argument("--append-effort", default="high")
    args = parser.parse_args()

    if args.rebuild_dir:
        output_dir = args.rebuild_dir.resolve()
        benchmark = json.loads((output_dir / "benchmark.json").read_text(encoding="utf-8"))
        answers = {}
        for key in benchmark["runs"]:
            answer_path = output_dir / f"answer_{key}.md"
            if not answer_path.is_file():
                continue
            answer = sanitize_latex(answer_path.read_text(encoding="utf-8")).strip()
            answer_path.write_text(answer + "\n", encoding="utf-8")
            answers[key] = answer
        if args.append_model:
            visual_ir = VisualProblemIR.from_dict(
                json.loads((output_dir / "visual_ir.json").read_text(encoding="utf-8"))
            )
            prompt = build_solution_prompt(
                visual_ir,
                user_question=benchmark["question"],
                subject=benchmark["subject"],
            )
            answer, metrics = _stream_answer(
                prompt,
                args.append_effort,
                model_name=args.append_model,
            )
            answers[args.append_key] = answer
            benchmark["runs"][args.append_key] = metrics
            (output_dir / f"answer_{args.append_key}.md").write_text(answer + "\n", encoding="utf-8")
            (output_dir / "benchmark.json").write_text(
                json.dumps(benchmark, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        _write_report(output_dir, benchmark, answers)
        print(f"REPORT_REBUILT={output_dir}", flush=True)
        return

    if args.image is None:
        parser.error("image is required unless --rebuild-dir is used")

    image_path = args.image.resolve()
    if not image_path.is_file():
        raise FileNotFoundError(image_path)
    run_id = datetime.now().strftime("image_reasoning_%Y%m%d_%H%M%S")
    output_dir = (args.output_root / run_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)

    raw_copy = output_dir / f"source_raw{image_path.suffix.lower()}"
    shutil.copy2(image_path, raw_copy)
    image_store = MistakeImageStore(
        images_path=output_dir,
        allowed_extensions=frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp"}),
        max_image_bytes=20 * 1024 * 1024,
        ocr_max_side=int(os.getenv("MISTAKE_OCR_MAX_SIDE", "1600")),
        ocr_jpeg_quality=int(os.getenv("MISTAKE_OCR_JPEG_QUALITY", "86")),
        pending_max_age_seconds=24 * 60 * 60,
    )
    prepared_image = image_store.optimize_for_ocr(raw_copy)
    print(
        f"[image] production preprocessing: {image_path.stat().st_size} -> "
        f"{prepared_image.stat().st_size} bytes",
        flush=True,
    )

    vision_started = time.perf_counter()
    visual_ir = KimiVisionBridge().analyze(
        prepared_image,
        user_question=args.question,
        subject=args.subject,
    )
    vision_ms = round((time.perf_counter() - vision_started) * 1000, 2)
    print(f"[kimi] visual extraction completed: {vision_ms / 1000:.2f}s", flush=True)
    visual_ir_path = output_dir / "visual_ir.json"
    visual_ir_path.write_text(
        json.dumps(visual_ir.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    prompt = build_solution_prompt(
        visual_ir,
        user_question=args.question,
        subject=args.subject,
    )
    results: dict[str, dict] = {}
    answers: dict[str, str] = {}
    for effort in ("medium", "high"):
        answer, metrics = _stream_answer(prompt, effort)
        answers[effort] = answer
        results[effort] = metrics
        (output_dir / f"answer_{effort}.md").write_text(answer + "\n", encoding="utf-8")

    benchmark = {
        "created_at": datetime.now().astimezone().isoformat(),
        "image_path": str(image_path),
        "prepared_image_path": str(prepared_image),
        "subject": args.subject,
        "question": args.question,
        "kimi": {
            "model": KimiVisionBridge().model,
            "thinking_enabled": False,
            "visual_ir_max_tokens": 3000,
            "total_ms": vision_ms,
            "visual_type": visual_ir.visual_type,
            "entity_count": len(visual_ir.entities),
            "relation_count": len(visual_ir.relations),
            "uncertainty_count": len(visual_ir.uncertainties),
        },
        "deepseek_model": DEEPSEEK_MODEL_NAME,
        "runs": results,
    }
    (output_dir / "benchmark.json").write_text(
        json.dumps(benchmark, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _write_report(output_dir, benchmark, answers)
    print(f"RESULT_DIR={output_dir}", flush=True)


if __name__ == "__main__":
    main()
