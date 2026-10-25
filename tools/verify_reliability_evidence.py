"""Regenerate all evaluation inputs/truth and reject self-consistent source forgery."""

import argparse
import gzip
import json
import zlib
from collections import Counter
from pathlib import Path

from analyze_reliability_replication import (
    CANDIDATE,
    record_digest,
    verify_repeat,
    verify_row,
    verify_sources,
)
from run_reliability_replication import Split, build_dataset

from cpswm.system.reproducibility import content_sha256


def validate_source(row, expected_input, expected_truth):
    assert row["input_sha256"] == expected_input, "public input differs from regenerated source"
    assert row["truth"] == expected_truth, "evaluator truth differs from regenerated source"


def validate_summary(totals, paired, summary):
    assert dict(totals) == summary["errors"], "aggregate errors differ from raw evidence"
    assert paired == summary["paired"], "paired outcome counts differ from raw evidence"


def verify(path, analysis, prefix, interrupted):
    manifest = json.loads((path / "source.json").read_text())
    source_files = verify_sources(manifest)
    expected = {}
    for condition in manifest["frozen"]["conditions"]:
        dataset = build_dataset(condition, manifest["frozen"]["test_seeds"])
        for seed, episode in zip(
            manifest["frozen"]["test_seeds"], dataset.visible_episodes(Split.TEST), strict=True
        ):
            truth = dataset.truth_for(episode.episode_id)
            for index, step in enumerate(episode.steps):
                expected[(condition, seed, index + 1)] = (
                    str(episode.episode_id),
                    content_sha256(step),
                    truth.truth_by_step[step.step_id].model_dump(mode="json"),
                )
    seen = set()
    hashes = {}
    totals = Counter()
    pairs = {}
    max_error = 0.0
    with gzip.open(path / "points.jsonl.gz", "rt") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["condition"], row["seed"], row["step"])
            assert key in expected and key not in seen
            episode, public, truth = expected[key]
            assert row["episode"] == episode
            validate_source(row, public, truth)
            max_error = max(max_error, verify_row(row))
            seen.add(key)
            hashes[key] = record_digest(row)
            candidate = row["actions"][CANDIDATE]["put_back"] != truth["true_owner_habit_location"]
            for name, action in row["actions"].items():
                wrong = action["put_back"] != truth["true_owner_habit_location"]
                totals[name] += wrong
                if name == CANDIDATE:
                    continue
                count = pairs.setdefault(name, Counter())
                count.update(
                    points=1,
                    candidate_errors=int(candidate),
                    baseline_errors=int(wrong),
                    fixed=int(wrong and not candidate),
                    harmed=int(candidate and not wrong),
                    net_fewer_errors=int(wrong) - int(candidate),
                )
    assert seen == set(expected) and len(seen) == 768
    summary = json.loads((analysis / "summary.json").read_text())
    validate_summary(totals, {k: dict(v) for k, v in pairs.items()}, summary)
    repeat = verify_repeat(prefix, analysis)
    raw = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(
        (interrupted / "points.jsonl.gz").read_bytes()
    )
    partial = 0
    for line in raw.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            break
        key = (row["condition"], row["seed"], row["step"])
        assert record_digest(row) == hashes[key]
        partial += 1
    result = {
        "source_files_verified": source_files,
        "all_768_public_inputs_and_evaluator_truth_regenerated": True,
        "independent_aggregate_counts_verified": True,
        "max_scalar_error": max_error,
        "prefix_repeat": repeat,
        "interrupted_serial_points_identical_to_parallel": partial,
        "scope": (
            "all input/truth and arithmetic; 36 prefix and retained serial state repeats; "
            "not second complete state run"
        ),
    }
    (analysis / "source_and_repeat_verification.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("path", type=Path)
    p.add_argument("--analysis", type=Path, required=True)
    p.add_argument("--prefix", type=Path, required=True)
    p.add_argument("--interrupted", type=Path, required=True)
    a = p.parse_args()
    verify(a.path, a.analysis, a.prefix, a.interrupted)
