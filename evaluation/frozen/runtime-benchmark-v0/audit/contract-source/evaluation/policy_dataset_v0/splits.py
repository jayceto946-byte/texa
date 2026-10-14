"""Explicit family grouping, incremental deterministic assignment and lock checks."""
from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal
import re
from backend.services.decision.policy_contracts import StrictV0, canonical_json
from backend.services.decision.policy_projection import digest
from .contracts import Split
from .serialization import action_hash
from .labels import label_hash


class SplitManifestV0(StrictV0):
    version: Literal["family-split/v0"] = "family-split/v0"
    seed: str
    ratios: list[float]
    assignments: dict[str, Split]
    sample_fingerprints: dict[str, str]
    near_duplicate_resolutions: dict[str, str]
    locked: bool = False


def sample_fingerprint(sample):
    return digest([sample.observation_hash, label_hash(sample), sample.source.model_dump(), sample.scenario_tags, sample.hard_tags])


def groups(samples):
    families = {s.source.source_family_id for s in samples}
    parent = {family: family for family in families}
    def find(family):
        while parent[family] != family:
            family = parent[family]
        return family
    refs = {}
    for sample in sorted(samples, key=lambda s: s.sample_id):
        family = sample.source.source_family_id
        for ref in [sample.source.ref, *sample.source.related_refs]:
            if ref in refs:
                roots = sorted([find(family), find(refs[ref])])
                parent[roots[1]] = roots[0]
            refs[ref] = family
    return {family: find(family) for family in sorted(families)}


def assign_splits(samples, *, seed="dataset-v0", ratios=(0.5, 0.25, 0.25), previous=None, overrides=None):
    if len({s.sample_id for s in samples}) != len(samples):
        raise ValueError("duplicate sample_id")
    if len(ratios) != 3 or any(r <= 0 for r in ratios) or abs(sum(ratios) - 1) > 1e-9:
        raise ValueError("invalid split ratios")
    if previous and (previous.seed != seed or previous.ratios != list(ratios)):
        raise ValueError("split configuration changed")
    fingerprints = {s.sample_id: sample_fingerprint(s) for s in samples}
    if previous:
        for sample_id, fingerprint in previous.sample_fingerprints.items():
            if sample_id in fingerprints and fingerprints[sample_id] != fingerprint:
                raise ValueError("frozen sample changed; create a new version")
        fingerprints = {**previous.sample_fingerprints, **fingerprints}
    assignments = dict(previous.assignments) if previous else {}
    overrides = overrides or {}
    grouped = groups(samples)
    split_names = ("development", "validation", "locked_test")
    for root in sorted(set(grouped.values())):
        members = [f for f, group in grouped.items() if group == root]
        pinned = {assignments[f] for f in members if f in assignments}
        pinned.update(overrides[f] for f in members if f in overrides)
        if len(pinned) > 1:
            raise ValueError("related family split conflict")
        tuned = any(s.source.used_for_tuning for s in samples if s.source.source_family_id in members)
        if tuned and pinned and pinned != {"development"}:
            raise ValueError("tuned family outside development")
        fraction = int(digest(["family-split/v0", seed, root]), 16) / (1 << 256)
        chosen = next(iter(pinned)) if pinned else "development" if tuned else split_names[
            0 if fraction < ratios[0] else 1 if fraction < ratios[0] + ratios[1] else 2]
        for family in members:
            assignments[family] = chosen
    return SplitManifestV0(seed=seed, ratios=list(ratios), assignments=assignments,
        sample_fingerprints=fingerprints,
        near_duplicate_resolutions=dict(previous.near_duplicate_resolutions) if previous else {}, locked=False)


def _identity(sample):
    data = sample.observation.model_dump(exclude_none=True)
    data["admissible_actions"] = sorted(action_hash(a) for a in sample.observation.admissible_actions)
    return digest(data)


def _template(sample):
    value = sample.observation.request + " " + sample.observation.context.resolved_query
    return re.sub(r"[\W\d_]+", "", value.casefold())


def leakage_checks(samples, manifest):
    blockers, pending = [], []
    grouped = groups(samples)
    for sample in samples:
        if manifest.sample_fingerprints.get(sample.sample_id) != sample_fingerprint(sample):
            blockers.append({"code": "sample_manifest_mismatch", "samples": [sample.sample_id]})
        if sample.source.source_family_id not in manifest.assignments:
            blockers.append({"code": "unassigned_family", "samples": [sample.sample_id]})
    for root in sorted(set(grouped.values())):
        values = {manifest.assignments.get(f) for f, group in grouped.items() if group == root}
        if len(values) > 1:
            blockers.append({"code": "related_family_leakage", "family": root})
    ordered = sorted(samples, key=lambda s: s.sample_id)
    for i, left in enumerate(ordered):
        for right in ordered[i + 1:]:
            if manifest.assignments.get(left.source.source_family_id) == manifest.assignments.get(right.source.source_family_id):
                continue
            pair = digest(sorted([left.sample_id, right.sample_id]))
            if _identity(left) == _identity(right):
                blockers.append({"code": "cross_split_exact_duplicate", "pair": pair})
            elif SequenceMatcher(None, _template(left), _template(right), autojunk=False).ratio() >= 0.88:
                # Only explicit independent-review reason may resolve a false positive.
                if not manifest.near_duplicate_resolutions.get(pair, "").strip():
                    pending.append({"code": "near_duplicate_review", "pair": pair})
    return {"blockers": blockers, "pending": pending}


def lock_manifest(samples, manifest, qualities):
    leakage = leakage_checks(samples, manifest)
    if leakage["blockers"] or leakage["pending"]:
        raise ValueError("unresolved split leakage")
    if any(not qualities[s.sample_id].locked_checked or not (
            qualities[s.sample_id].selection_eligible or qualities[s.sample_id].diagnostic_eligible) for s in samples):
        raise ValueError("quality gate not satisfied")
    return manifest.model_copy(update={"locked": True})


def write_manifest(path, manifest):
    with Path(path).open("x", encoding="utf-8") as output:
        output.write(canonical_json(manifest.model_dump()) + "\n")
