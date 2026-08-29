"""Run the offline Figure-learning acceptance standard over a MinerU corpus."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.visual_learning_eval import evaluate_visual_learning_corpus, load_sensor_standard


DEFAULT_STANDARD = ROOT / "evaluation" / "datasets" / "visual_learning_sensor.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="MinerU output directory")
    parser.add_argument("--standard", type=Path, default=DEFAULT_STANDARD)
    parser.add_argument("--book-name", default="传感器视觉验收")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    standard = load_sensor_standard(args.standard)
    with tempfile.TemporaryDirectory(prefix="texa-visual-learning-eval-") as temporary:
        result = evaluate_visual_learning_corpus(
            args.output_dir,
            progress_root=Path(temporary),
            standard=standard,
            book_name=args.book_name,
        )
    rendered = json.dumps(result.report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
