"""Summarize, archive, and independently rescore extracted current-event runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from check_current_event import check
from score_current_event import read, verify


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def summarize(main):
    score = read(main / "test-score.json")
    totals = defaultdict(Counter)
    for key, value in score["totals"].items():
        totals[key.split("/")[1]].update(value)
    diagnostic = Counter()
    paths = defaultdict(set)
    for item in read(main / "test/index.json"):
        if item["label"] != "joint":
            continue
        run = read(main / "test" / item["file"])
        truth = read(main / "test" / item["truth"])
        names = {}
        path = []
        for row, n in zip(run["actions"], run["native_evidence"], strict=True):
            target = truth["truth_by_step"][row["step_id"]]["true_location"]
            if target not in names:
                names[target] = len(names)
            path.append(names[target])
            if row["location_source_id"]:
                likelihood = dict(n["observation"]["location_likelihood"])
                present = set(n["placement_actors"])
                applied = [likelihood[a] for a in present]
                diagnostic["new_location_events"] += 1
                diagnostic["single_actor_sample_support"] += len(present) == 1
                diagnostic["constant_likelihood_on_sampled_support"] += (
                    max(applied) - min(applied) < 1e-10
                )
                diagnostic["actor_informative_likelihood"] += (
                    max(likelihood.values()) - min(likelihood.values()) > 1e-10
                )
        paths[item["condition"]].add(tuple(path))
    interactions = {}
    for cond in paths:
        j = score["comparisons"][cond + "/joint_new_evidence_effect"]["put_error_difference"]
        f = score["comparisons"][cond + "/matched_factor_new_evidence_effect"][
            "put_error_difference"
        ]
        interactions[cond] = {
            "joint_new_minus_no_new_put_errors": j,
            "factor_new_minus_no_new_put_errors": f,
            "joint_minus_factor_evidence_effect": j - f,
        }
    return {
        "totals": {k: dict(v) for k, v in sorted(totals.items())},
        "diagnostics": dict(diagnostic),
        "evidence_interaction": interactions,
        "distinct_true_location_paths_up_to_renaming": {k: len(v) for k, v in paths.items()},
        "scope": (
            "D0 fixed-policy search then native habit decisions; descriptive, "
            "not a natural robot task or independent worlds"
        ),
    }


def package(main, repeat, output, repository):
    output.mkdir(parents=True, exist_ok=False)
    summary = summarize(main)
    save(main / "summary.json", summary)
    checks = check(main, repeat, repository)
    assert checks == read(main / "checks.json")
    manifest = {}
    for label, root in [("main", main), ("repeat", repeat)]:
        members = {}
        archive = output / f"raw-{label}.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            for file in sorted(root.rglob("*")):
                if not file.is_file():
                    continue
                rel = str(file.relative_to(root))
                members[rel] = {
                    "size": file.stat().st_size,
                    "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                }
                tar.add(file, arcname=f"{label}/{rel}", recursive=False)
        manifest[archive.name] = {
            "size": archive.stat().st_size,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "members": members,
        }
    count = 0
    with tempfile.TemporaryDirectory(prefix="current-event-extracted-") as temp:
        target = Path(temp)
        for name, facts in manifest.items():
            with tarfile.open(output / name, "r:gz") as tar:
                tar.extractall(target, filter="data")
            label = name.removeprefix("raw-").removesuffix(".tar.gz")
            for path, value in facts["members"].items():
                file = target / label / path
                assert (
                    file.stat().st_size == value["size"]
                    and hashlib.sha256(file.read_bytes()).hexdigest() == value["sha256"]
                )
                count += 1
        for phase in ["dev", "test"]:
            computed = json.dumps(verify(target / "main" / phase), indent=2, sort_keys=True) + "\n"
            assert computed.encode() == (target / "main" / (phase + "-score.json")).read_bytes()
        assert check(target / "main", target / "repeat", repository) == checks
        assert summarize(target / "main") == summary
    for name in [
        "dev-score.json",
        "test-score.json",
        "summary.json",
        "checks.json",
        "revisions.json",
    ]:
        shutil.copy2(main / name, output / name)
    save(output / "MANIFEST.json", manifest)
    receipt = {
        "verified_members": count,
        "exact_rescored_json": ["dev-score.json", "test-score.json"],
        "checks_and_summary_exact": True,
        "scope": (
            "local archive integrity and independent implementation rescoring, not B acceptance"
        ),
    }
    save(output / "ARCHIVE_VERIFY.json", receipt)
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--main", type=Path, required=True)
    p.add_argument("--repeat", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    a = p.parse_args()
    package(a.main, a.repeat, a.output, a.repository)
