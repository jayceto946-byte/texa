"""Small local entry point. Reads supplied offline files; writes one new directory."""
from __future__ import annotations

import argparse
from pathlib import Path
from backend.services.decision.policy_contracts import canonical_json
from .serialization import read_samples, write_samples, strict_loads
from .labels import AdjudicationRecordV0
from .validation import validate_sample, validate_manifest
from .splits import assign_splits, SplitManifestV0, lock_manifest, write_manifest
from .evaluator import evaluate_views
from .report import generate_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("validate", "split", "evaluate", "report"))
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/fixtures/policy_dataset_v0"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", default="dataset-v0")
    parser.add_argument("--previous-split", type=Path)
    parser.add_argument("--control-family", action="append", default=[])
    parser.add_argument("--lock", action="store_true")
    args = parser.parse_args(argv)
    manifest, errors = validate_manifest(strict_loads((args.dataset / "manifest.json").read_text()))
    if errors:
        raise ValueError(",".join(errors))
    samples = read_samples(args.dataset / "samples.jsonl")
    records = [AdjudicationRecordV0.model_validate(strict_loads(line)) for line in
               (args.dataset / "adjudications.jsonl").read_text().splitlines() if line.strip()]
    # Explicit ref -> content file map. Confinement prevents private arbitrary reads.
    evidence_files = strict_loads((args.dataset / "evidence-files.json").read_text())
    evidence = {}
    root = args.dataset.resolve()
    for ref, relative in evidence_files.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError("evidence file outside dataset")
        evidence[ref] = path.read_bytes()
    qualities = {s.sample_id: validate_sample(s, manifest=manifest, records=records, evidence=evidence, locked=args.lock) for s in samples}
    previous = SplitManifestV0.model_validate(strict_loads(args.previous_split.read_text())) if args.previous_split else None
    splits = assign_splits(samples, seed=args.seed, previous=previous)
    if args.lock:
        splits = lock_manifest(samples, splits, qualities)
    # Complete validation first; existing output directory is never overwritten.
    args.output.mkdir(parents=True, exist_ok=False)
    write_samples(args.output / "samples.jsonl", samples)
    (args.output / "quality.json").write_text(canonical_json({sid: q.to_dict() for sid, q in qualities.items()}) + "\n")
    write_manifest(args.output / "split.json", splits)
    if args.operation in {"evaluate", "report"}:
        results = evaluate_views(samples, seed=args.seed, control_families=args.control_family)
        (args.output / "predictions.jsonl").write_text("".join(canonical_json(p.model_dump()) + "\n" for p in results))
        transforms = [p.transform.model_dump() for p in results if p.selector == "rule" and p.transform]
        (args.output / "transforms.jsonl").write_text("".join(canonical_json(t) + "\n" for t in transforms))
        if args.operation == "report":
            report = generate_report(samples, results, qualities, splits)
            (args.output / "report.json").write_text(canonical_json(report) + "\n")
    print(canonical_json({"operation": args.operation, "samples": len(samples),
                          "locked": splits.locked, "real_model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
