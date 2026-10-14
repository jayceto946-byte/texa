"""Minimal offline production/adjudication CLI. No teacher transport is enabled."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from .baseline import DEFAULT_DATASET
from backend.services.decision.policy_contracts import canonical_json
from .serialization import strict_loads, read_samples
from .seed_production import load_dataset, produce, write_bundle, verify_trace
from .seed_calibration import calibrate
from .seed_reviews import HumanReviewV0, review_packet, finalize_sample, confirm_candidates, review_statistics
from .seed_report import formal_qualities, compare_seed, assert_public_artifact
from .splits import SplitManifestV0, assign_splits, lock_manifest, leakage_checks, groups
from .teacher_batch import prepare_batch, write_prepared
from .contracts import PredictionV0
from .validation import validate_sample
from .evaluator import evaluate_views


def _json_lines(path, model=None):
    values = [strict_loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    return [model.model_validate(v) for v in values] if model else values


def _optional_json(root, name):
    path = Path(root) / name
    return strict_loads(path.read_text()) if path.exists() else {}


def _read_split(root, samples):
    path = Path(root) / "split.json"
    return SplitManifestV0.model_validate(strict_loads(path.read_text())) if path.exists() else calibration_safe_splits(samples)


def calibration_safe_splits(samples, *, seed="seed-v0", previous=None):
    baseline = read_samples(DEFAULT_DATASET / "samples.jsonl")
    families = {s.source.source_family_id for s in baseline}
    refs = {ref for s in baseline for ref in [s.source.ref, *s.source.related_refs]}
    pinned = {s.source.source_family_id: "development" for s in samples if s.source.source_family_id in families or
              refs.intersection([s.source.ref, *s.source.related_refs])}
    return assign_splits(samples, seed=seed, previous=previous, overrides=pinned)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("calibrate", "generate", "blind-review", "review-candidates", "finalize", "prepare-teachers", "release", "report"))
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recipes", type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--finalizations", type=Path)
    parser.add_argument("--teacher-config", type=Path)
    parser.add_argument("--teacher-run", type=Path)
    parser.add_argument("--include", action="append", default=[])
    args = parser.parse_args(argv)
    if args.output.exists():
        raise ValueError("output already exists; use a new artifact directory")
    if args.operation == "calibrate":
        summary = calibrate(args.dataset, args.output)
        print(canonical_json(summary))
        return 0
    samples, manifest, records, evidence = load_dataset(args.dataset)
    if args.operation == "generate":
        if not args.recipes:
            raise ValueError("--recipes required")
        recipes = _json_lines(args.recipes)
        assert_public_artifact(recipes)
        produced = produce(recipes, manifest, args.output)
        print(canonical_json({"samples": len(produced), "formal_gold": 0, "real_model_calls": 0}))
        return 0
    traces = _optional_json(args.dataset, "projections.json")
    bindings = _optional_json(args.dataset, "review-bindings.json")
    splits = _read_split(args.dataset, samples)
    reviews = _json_lines(args.reviews, HumanReviewV0) if args.reviews else []
    if args.operation == "blind-review":
        packets = [review_packet(s) for s in samples]
        assert_public_artifact(packets)
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "blind-packets.jsonl").write_text("".join(canonical_json(p) + "\n" for p in packets))
        (args.output / "INSTRUCTIONS.txt").write_text(
            "Give separate copies to two actual human reviewers. Keep predictions and proposal labels hidden until each initial review is saved.\n"
            "Templates are blank and are not completed human reviews. Review every candidate and frozen source evidence.\n"
            "Human identities/independence are accountable declarations; this CLI cannot authenticate them.\n")
    elif args.operation in {"review-candidates", "finalize"}:
        if not args.reviews or not args.finalizations:
            raise ValueError("--reviews and --finalizations required")
        instructions = strict_loads(args.finalizations.read_text())
        assert_public_artifact(instructions)
        assert_public_artifact([r.model_dump() for r in reviews])
        stats = review_statistics(samples, reviews)
        by_id = {s.sample_id: s for s in samples}
        for instruction in instructions:
            sample = by_id[instruction["base_sample_id"]]
            new_id = instruction["new_sample_id"]
            if new_id in by_id:
                raise ValueError("new sample version already exists")
            relevant = [r for r in reviews if r.sample_id == sample.sample_id]
            if args.operation == "review-candidates":
                reviewer_id = instruction["reviewer_id"]
                matching = [r for r in relevant if r.reviewer_id == reviewer_id and r.round == "initial"]
                if len(matching) != 1:
                    raise ValueError("one initial candidate review must be selected")
                new, manifest, evidence, trace = confirm_candidates(sample, matching[0], new_sample_id=new_id,
                    manifest=manifest, evidence=evidence, trace=traces[sample.sample_id])
            else:
                final = HumanReviewV0.model_validate(instruction["final"])
                new, manifest, evidence, record, trace, binding = finalize_sample(sample, relevant, final,
                    new_sample_id=new_id, manifest=manifest, evidence=evidence, trace=traces[sample.sample_id])
                records.append(record)
                bindings[new.sample_id] = binding
            samples.append(new)
            by_id[new.sample_id] = new
            traces[new.sample_id] = trace
        new_splits = calibration_safe_splits(samples, seed=splits.seed, previous=splits)
        write_bundle(args.output, samples, manifest, evidence, records=records, traces=traces, splits=new_splits)
        (args.output / "review-bindings.json").write_text(canonical_json(bindings) + "\n")
        (args.output / "review-statistics.json").write_text(canonical_json(stats) + "\n")
    elif args.operation == "prepare-teachers":
        configs = strict_loads(args.teacher_config.read_text()) if args.teacher_config else []
        assert_public_artifact(configs)
        qualities = {s.sample_id: validate_sample(s, manifest=manifest, records=records, evidence=evidence, locked=True) for s in samples}
        plan, inputs = prepare_batch(samples, manifest, splits, traces, qualities, seed=splits.seed, configs=configs)
        write_prepared(args.output, plan, inputs)
    elif args.operation == "release":
        if not args.include or len(set(args.include)) != len(args.include):
            raise ValueError("explicit, unique --include sample versions required")
        selected = [s for s in samples if s.sample_id in args.include]
        if len(selected) != len(args.include):
            raise ValueError("unknown release sample")
        # Enforce fixture-family development exclusion even when an input manifest is edited.
        calibration_safe_splits(samples, seed=splits.seed, previous=splits)
        qualities = formal_qualities(selected, manifest, records, evidence, traces, bindings)
        locked = lock_manifest(selected, splits, qualities)
        write_bundle(args.output, selected, manifest, evidence, records=records, traces=traces, splits=locked)
        (args.output / "review-bindings.json").write_text(canonical_json(bindings) + "\n")
        stats = _optional_json(args.dataset, "review-statistics.json")
        (args.output / "review-statistics.json").write_text(canonical_json(stats) + "\n")
        (args.output / "release-tracks.json").write_text(canonical_json({
            "selection": [s.sample_id for s in selected if qualities[s.sample_id].selection_eligible],
            "diagnostics": [s.sample_id for s in selected if qualities[s.sample_id].diagnostic_eligible],
            "excluded_from_this_release": [s.sample_id for s in samples if s not in selected],
            "split_manifest_hash": hashlib.sha256(canonical_json(locked.model_dump()).encode()).hexdigest()}) + "\n")
    elif args.operation == "report":
        qualities = formal_qualities(samples, manifest, records, evidence, traces, bindings)
        # One main view; original and controls remain unweighted diagnostics.
        predictions = [p for p in evaluate_views(samples, seed=splits.seed) if p.selector == "rule"]
        run, logs = None, []
        if args.teacher_run:
            run = strict_loads((args.teacher_run / "run-manifest.json").read_text())
            external = _json_lines(args.teacher_run / "predictions.jsonl", PredictionV0)
            predictions += [p for p in external if p.selector in {"sol", "luna"}]
            logs = _json_lines(args.teacher_run / "responses.jsonl")
        report = compare_seed(samples, predictions, qualities, splits, manifest=manifest, traces=traces,
            review_bindings=bindings, teacher_run=run, response_logs=logs,
            review_stats=_optional_json(args.dataset, "review-statistics.json"), evidence=evidence)
        assert_public_artifact(report)
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / "report.json").write_text(canonical_json(report) + "\n")
        (args.output / "quality.json").write_text(canonical_json({sid: q.to_dict() for sid, q in qualities.items()}) + "\n")
        (args.output / "predictions.jsonl").write_text("".join(canonical_json(p.model_dump()) + "\n" for p in predictions))
        print(canonical_json(report["decision"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
