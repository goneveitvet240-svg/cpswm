"""Cross-sampler fairness, fresh replay, source checks and bounded tamper tests."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from score_current_event import read
from score_particle_support import score, verify_sampling


def check(main, repeat, repository):
    sources = None
    scores = {}
    for phase in ["dev", "test"]:
        for method in ["systematic", "stratified"]:
            root = main / phase / method
            result = score(root)
            assert result == read(root / "score.json")
            files = read(root / "source.json")["files"]
            if sources is None:
                sources = files
            assert files == sources
            scores[phase + "/" + method] = result
    assert sources == read(repeat / "source.json")["files"]
    for rel, expected in sources.items():
        assert hashlib.sha256((repository / rel).read_bytes()).hexdigest() == expected
    cross = {}
    total = {}
    paths = defaultdict(set)
    for method in ["systematic", "stratified"]:
        root = main / "test" / method
        totals = defaultdict(Counter)
        for key, value in scores["test/" + method]["totals"].items():
            totals[key.split("/")[1]].update(value)
        total[method] = {k: dict(v) for k, v in totals.items()}
        for item in read(root / "index.json"):
            run = read(root / item["file"])
            totals[item["label"]]["retained_event_enumerated_candidates"] += sum(
                r["support_size"] for r in run["sampling_receipts"]
            )
            if method == "stratified":
                old = read(main / "test/systematic" / item["file"])
                assert [r["search"] for r in run["actions"]] == [
                    r["search"] for r in old["actions"]
                ]
                key = item["condition"] + "/" + item["label"]
                c = cross.setdefault(key, Counter())
                c["put_error_change"] += run["put_errors"] - old["put_errors"]
                c["put_action_changes"] += sum(
                    a["put_back"] != b["put_back"]
                    for a, b in zip(run["actions"], old["actions"], strict=True)
                )
                assert all(
                    a["fairness"]["particle_budget"] == b["fairness"]["particle_budget"] == 24
                    for a, b in zip(run["native_evidence"], old["native_evidence"], strict=True)
                )
                if item["label"] == "joint":
                    truth = read(root / item["truth"])["truth_by_step"]
                    names = {}
                    path = []
                    for action in run["actions"]:
                        location = truth[action["step_id"]]["true_location"]
                        names.setdefault(location, len(names))
                        path.append(names[location])
                    paths[item["condition"]].add(tuple(path))
        total[method] = {k: dict(v) for k, v in totals.items()}
    score(repeat)
    count = 0
    for file in repeat.glob("run-*.json"):
        a = read(file)
        b = read(main / "test/stratified" / file.name)
        a.pop("wall_seconds")
        b.pop("wall_seconds")
        assert a == b
        count += 1
    sample = read(main / "test/stratified/run-sparse32-0-joint.json")
    attacks = [
        "method",
        "offset",
        "seed",
        "count",
        "index",
        "probability",
        "interval",
        "duplicate_receipt",
        "importance",
    ]
    for attack in attacks:
        run = copy.deepcopy(sample)
        r = run["sampling_receipts"][0]
        if attack == "method":
            r["method"] = "systematic"
        elif attack == "offset":
            r["offsets"][0] = 0.999
        elif attack == "seed":
            r["seed_sha256"] = "f" * 64
        elif attack == "count":
            r["count"] = 48
        elif attack == "index":
            r["indices"][0] = r["support_size"]
        elif attack == "probability":
            r["selected_probabilities"][0] *= 2
        elif attack == "interval":
            r["cdf_intervals"][0] = [0.9, 1.0]
        elif attack == "duplicate_receipt":
            run["sampling_receipts"].append(copy.deepcopy(r))
        elif attack == "importance":
            run["native_evidence"][0]["receipts"][0]["proposal"][
                "proposal_log_probability"
            ] = -100.0
        try:
            verify_sampling(run)
        except (AssertionError, ValueError, KeyError):
            pass
        else:
            raise AssertionError("tamper passed: " + attack)
    revisions = read(main / "revisions.json")
    assert revisions["actual_step_executions"] == 42
    revision_checks = []
    for case in revisions["cases"]:
        branches = case["branches"]
        a, b = branches["control"], branches["restore"]
        assert a["final_state"] == b["final_state"] and a["next_action"] == b["next_action"]
        revision_checks.append({"arm": case["arm"], "restore_exact": True})
    return {
        "actual_runs": {k: v["actual_runs"] for k, v in scores.items()},
        "repeat_exact_except_wall_runs": count,
        "source_files_checked": len(sources),
        "revision_continuations": revision_checks,
        "additional_revision_step_executions": 42,
        "all_cross_sampler_paid_searches_identical": True,
        "cross_sampler_repaired_minus_old": {k: dict(v) for k, v in sorted(cross.items())},
        "heldout_totals": total,
        "distinct_true_paths_up_to_relabeling": {k: len(v) for k, v in paths.items()},
        "sampling_tamper_rejections": attacks,
        "scope": (
            "Local paired diagnostic; not B acceptance, fully enumerated native posterior, "
            "or natural robot evidence"
        ),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--main", type=Path, required=True)
    p.add_argument("--repeat", type=Path, required=True)
    p.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = check(a.main, a.repeat, a.repository)
    a.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
