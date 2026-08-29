"""Run the explicitly authorized online Figure-learning gold-set evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import PROGRESS_PATH
from evaluation.visual_learning_online_eval import (
    evaluate_visual_learning_online,
    load_visual_gold,
    rescore_visual_learning_report,
)


DEFAULT_GOLD = ROOT / "evaluation" / "datasets" / "visual_learning_sensor_gold.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--case", action="append", default=[], help="Run only one case id; repeatable")
    parser.add_argument("--workers", type=int, default=1, choices=range(1, 5))
    parser.add_argument("--reuse-report", type=Path, default=None, help="Rescore saved answers without model calls")
    args = parser.parse_args()

    gold = load_visual_gold(args.gold)

    def progress(item: dict) -> None:
        print(json.dumps({
            "ordinal": item.get("ordinal"),
            "id": item.get("id"),
            "failure_bucket": item.get("failure_bucket"),
            "coverage": item.get("key_point_coverage"),
            "verification": item.get("verification_status"),
            "error": item.get("error"),
        }, ensure_ascii=False), flush=True)

    if args.reuse_report:
        saved = json.loads(args.reuse_report.read_text(encoding="utf-8"))
        result = rescore_visual_learning_report(gold, saved, progress_root=PROGRESS_PATH)
    else:
        result = evaluate_visual_learning_online(
            gold,
            progress_root=PROGRESS_PATH,
            case_ids=set(args.case) if args.case else None,
            on_case=progress,
            max_workers=args.workers,
        )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(result.report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"summary": result.report["summary"], "passed": result.passed}, ensure_ascii=False))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
