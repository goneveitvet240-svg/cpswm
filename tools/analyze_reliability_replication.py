"""Independent scalar readout checks and seed-clustered descriptive outcomes."""

import argparse
import gzip
import hashlib
import io
import itertools
import json
import math
import random
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

from cpswm.system.reproducibility import content_sha256

CANDIDATE = "native_joint/owner_missing"


def pick(d):
    return min(d, key=lambda k: (-d[k], k))


def normalized(d):
    assert d and all(math.isfinite(v) and v >= 0 for v in d.values())
    total = math.fsum(d.values())
    return {k: v / total if total else 1 / len(d) for k, v in d.items()}


def cell_distribution(raw, locations):
    d = normalized(dict(zip(locations, raw["location_alpha"], strict=True)))
    ridge = normalized(
        {
            k: n / p
            for k, n, p in zip(locations, raw["ridge_natural"], raw["ridge_precision"], strict=True)
        }
    )
    confidence = min(1, raw["information_natural"] / raw["information_precision"])
    return normalized(
        {k: confidence * (d[k] + ridge[k]) / 2 + (1 - confidence) / len(d) for k in d}
    )


def verify_row(row):
    assert content_sha256(row["input"]) == row["input_sha256"]
    assert (
        content_sha256({k: row[k] for k in ("actions", "readouts", "distributions", "traces")})
        == row["pre_truth_commitment"]
    )
    error = 0.0
    for name, receipt in row["readouts"].items():
        assert (
            content_sha256({k: v for k, v in receipt.items() if k != "sha256"}) == receipt["sha256"]
        )
        trace = row["traces"][name]
        locations = trace["locations"]
        cells = {}
        for p in trace["particles"]:
            for c in p["cells"]:
                assert content_sha256(c["cell"]) == c["cell_sha256"]
                expected = cell_distribution(c["cell"], locations)
                assert max(abs(expected[k] - c["distribution"][k]) for k in locations) < 1e-12
                if c["active"] and c["cell"]["observation_count"]:
                    cells[p["particle"]] = (p, c)
        assert set(cells) == {c["particle"] for c in receipt["components"]}
        for c in receipt["components"]:
            p, cell = cells[c["particle"]]
            assert c["weight"] == p["weight"] and c["cell_sha256"] == cell["cell_sha256"]
            assert c["distribution"] == cell["distribution"] and c["regime"] == p["active_regime"]
        mass = math.fsum(p["weight"] for p, _ in cells.values())
        assert abs(mass - receipt["consumed_mass"]) < 1e-12
        assert abs(receipt["fallback_mass"] - max(0, 1 - mass)) < 1e-12
        d = normalized(
            {
                k: math.fsum(p["weight"] * c["distribution"][k] for p, c in cells.values())
                + receipt["fallback_mass"] * receipt["base"][k]
                for k in locations
            }
        )
        error = max(error, max(abs(d[k] - receipt["distribution"][k]) for k in locations))
        assert error < 1e-12
        actual = row["distributions"][name]
        assert abs(sum(actual.values()) - 1) < 1e-12
        assert row["actions"][name]["put_back"] == pick(actual)
        if name.endswith("owner_missing"):
            assert max(abs(actual[k] - d[k]) for k in locations) < 1e-12
    truth = row["truth"]
    for name, a in row["actions"].items():
        s = row["scores"][name]
        assert s["put_error"] == int(a["put_back"] != truth["true_owner_habit_location"])
        assert s["rank_checks"] == a["search_order"].index(truth["true_location"]) + 1
        assert s["search_error"] == int(a["search_order"][0] != truth["true_location"])
    for arm in ("native_joint", "native_six_potential_ablation"):
        a, b = (row["budgets"][arm + "/" + mode] for mode in ("parent_only", "owner_missing"))
        for k in ("target_evaluations", "particles", "extra_ciav_queries", "paid_location_sources"):
            assert a[k] == b[k]
    return error


def verify_sources(manifest):
    assert not manifest["status"] and not manifest["smoke"]
    sha = manifest["sha"]
    assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)
    names = list(manifest["files"])
    blobs = io.BytesIO(
        subprocess.check_output(
            ["git", "cat-file", "--batch"], input="".join(f"{sha}:{n}\n" for n in names).encode()
        )
    )
    for n in names:
        h = blobs.readline().split()
        assert len(h) == 3 and h[1] == b"blob"
        b = blobs.read(int(h[2]))
        assert blobs.read(1) == b"\n"
        assert hashlib.sha256(b).hexdigest() == manifest["files"][n], n
    return len(names)


def paired(rows, candidate, baseline):
    ca = [r["scores"][candidate]["put_error"] for r in rows]
    ba = [r["scores"][baseline]["put_error"] for r in rows]
    return {
        "points": len(rows),
        "candidate_errors": sum(ca),
        "baseline_errors": sum(ba),
        "fixed": sum(b == 1 and c == 0 for b, c in zip(ba, ca, strict=True)),
        "harmed": sum(b == 0 and c == 1 for b, c in zip(ba, ca, strict=True)),
        "net_fewer_errors": sum(ba) - sum(ca),
    }


def cluster_uncertainty(rows, baseline, draws=10000, seed=864250):
    groups = defaultdict(list)
    for r in rows:
        groups[r["seed"]].append(r)
    delta = {k: paired(v, CANDIDATE, baseline)["net_fewer_errors"] for k, v in groups.items()}
    assert len({len(v) for v in groups.values()}) == 1
    values = list(delta.values())
    rng = random.Random(seed)
    boot = sorted(sum(rng.choices(values, k=len(values))) for _ in range(draws))
    observed = sum(values)
    flips = [
        sum(s * v for s, v in zip(signs, values, strict=True))
        for signs in itertools.product((-1, 1), repeat=len(values))
    ]
    return {
        "seed_net_fewer_errors": delta,
        "descriptive_bootstrap_total_95pct": [
            boot[int(0.025 * draws)],
            boot[int(0.975 * draws) - 1],
        ],
        "two_sided_cluster_sign_flip_fraction": sum(abs(v) >= abs(observed) for v in flips)
        / len(flips),
        "independent_seed_groups": len(values),
        "assumptions": "seed groups exchangeable; same generator; not formal scientific acceptance",
    }


def reliability(rows, name, bins):
    values = [r["reliability"][name] for r in rows]
    histogram = []
    for low, high in itertools.pairwise(bins):
        selected = [v for v in values if low <= v["confidence"] < high]
        histogram.append(
            {
                "lower": low,
                "upper": min(high, 1),
                "n": len(selected),
                "mean_confidence": statistics.mean(v["confidence"] for v in selected)
                if selected
                else None,
                "accuracy": statistics.mean(v["correct"] for v in selected) if selected else None,
            }
        )
    return {
        "n": len(values),
        "accuracy": statistics.mean(v["correct"] for v in values),
        "brier": statistics.mean(v["brier"] for v in values),
        "nll": statistics.mean(v["nll"] for v in values),
        "mean_true_probability": statistics.mean(v["true_probability"] for v in values),
        "actor_accuracy": statistics.mean(v["actor_correct"] for v in values),
        "confidence_bins": histogram,
    }


def reduce_row(row, history):
    truth = row["truth"]["true_owner_habit_location"]
    key = row["episode"]
    h = history.setdefault(key, {"previous": None, "seen": set(), "age": 0, "kind": "initial"})
    if truth != h["previous"]:
        h["kind"] = "return_habit" if truth in h["seen"] else "new_habit"
        h["age"] = 0
        h["seen"].add(truth)
    else:
        h["age"] += 1
    phase = "cold_start" if h["previous"] is None else h["kind"] if h["age"] < 3 else "stable"
    h["previous"] = truth
    result = {
        k: row[k]
        for k in ("seed", "condition", "episode", "step", "input_sha256", "scores", "actions")
    }
    result.update(phase=phase, regime_age=h["age"], reliability={}, diagnostics={})
    for name, d in row["distributions"].items():
        confidence = max(d.values())
        trace = row["traces"][name]
        actors = defaultdict(float)
        for p in trace["particles"]:
            actors[p["actor"]] += p["weight"]
        result["reliability"][name] = {
            "confidence": confidence,
            "correct": int(pick(d) == truth),
            "true_probability": d[truth],
            "nll": -math.log(max(d[truth], 1e-300)),
            "brier": sum((v - int(k == truth)) ** 2 for k, v in d.items()),
            "actor_correct": int(pick(actors) == row["truth"]["true_actor"]),
        }
        receipt = row["readouts"][name]
        active_right = sum(
            c["weight"] for c in receipt["components"] if pick(c["distribution"]) == truth
        )
        any_right = sum(
            p["weight"]
            for p in trace["particles"]
            if any(
                c["cell"]["observation_count"] and pick(c["distribution"]) == truth
                for c in p["cells"]
            )
        )
        result["diagnostics"][name] = {
            "consumed_mass": receipt["consumed_mass"],
            "active_cell_correct_top1_mass": active_right,
            "any_owner_cell_correct_top1_mass_oracle": any_right,
            "base_correct": int(pick(receipt["base"]) == truth),
            "owner_actor_true": row["truth"]["true_actor"] == trace["owner"],
            "missing_regime_evidence": trace["regime_evidence_available"] is False,
        }
    return result


def analyze(path, output):
    manifest = json.loads((path / "source.json").read_text())
    files = verify_sources(manifest)
    assert not manifest["prefix_only"]
    completion = json.loads((path / "completion.json").read_text())
    rows, history, prefix, max_error, inputs = [], {}, {}, 0.0, []
    with gzip.open(path / "points.jsonl.gz", "rt") as f:
        for line in f:
            row = json.loads(line)
            max_error = max(max_error, verify_row(row))
            inputs.append(row["input_sha256"])
            if row["step"] <= 2:
                prefix[(row["condition"], row["seed"], row["step"])] = content_sha256(
                    {k: v for k, v in row.items() if k != "elapsed_seconds"}
                )
            rows.append(reduce_row(row, history))
    assert len(rows) == completion["points"] == 768
    assert len({(r["condition"], r["seed"], r["step"]) for r in rows}) == 768
    assert (
        completion["input_sequence_sha256"] == content_sha256(inputs)
        and completion["source_unchanged"]
    )
    assert set(r["seed"] for r in rows) == set(manifest["frozen"]["test_seeds"])
    assert len({r["episode"] for r in rows}) == 18
    methods = list(rows[0]["actions"])
    baselines = [n for n in methods if n != CANDIDATE]
    result = {
        "source_sha": manifest["sha"],
        "verified_source_files": files,
        "points": len(rows),
        "max_scalar_error": max_error,
        "errors": {n: sum(r["scores"][n]["put_error"] for r in rows) for n in methods},
        "search_rank_checks": {
            n: sum(r["scores"][n]["rank_checks"] for r in rows) for n in methods
        },
        "paired": {b: paired(rows, CANDIDATE, b) for b in baselines},
        "uncertainty": {
            b: cluster_uncertainty(
                rows, b, manifest["frozen"]["bootstrap_draws"], manifest["frozen"]["bootstrap_seed"]
            )
            for b in baselines
        },
        "reliability": {
            n: reliability(rows, n, manifest["frozen"]["confidence_bins"])
            for n in rows[0]["reliability"]
        },
        "by_condition": {},
        "by_phase": {},
        "episodes": [],
        "failure_diagnostics": {},
    }
    for field, target in [("condition", "by_condition"), ("phase", "by_phase")]:
        for value in sorted({r[field] for r in rows}):
            subset = [r for r in rows if r[field] == value]
            result[target][value] = {b: paired(subset, CANDIDATE, b) for b in baselines}
    for episode in sorted({r["episode"] for r in rows}):
        subset = [r for r in rows if r["episode"] == episode]
        result["episodes"].append(
            {
                "episode": episode,
                "seed": subset[0]["seed"],
                "condition": subset[0]["condition"],
                "versus_latest": paired(subset, CANDIDATE, "latest_owner"),
            }
        )
    for label, selected in [
        ("wrong", [r for r in rows if r["scores"][CANDIDATE]["put_error"]]),
        (
            "harmed",
            [
                r
                for r in rows
                if r["scores"][CANDIDATE]["put_error"]
                and not r["scores"]["latest_owner"]["put_error"]
            ],
        ),
    ]:
        result["failure_diagnostics"][label] = {
            "n": len(selected),
            **{
                k: statistics.mean(float(r["diagnostics"][CANDIDATE][k]) for r in selected)
                if selected
                else None
                for k in rows[0]["diagnostics"][CANDIDATE]
            },
        }
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    (output / "audit_points.json").write_text(json.dumps(rows, indent=2) + "\n")
    (output / "prefix_hashes.json").write_text(
        json.dumps(
            [
                {"condition": k[0], "seed": k[1], "step": k[2], "sha256": v}
                for k, v in prefix.items()
            ],
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("source_sha", "points", "errors", "search_rank_checks", "paired")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("path", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    analyze(a.path, a.output)


def record_digest(row):
    return content_sha256({k: v for k, v in row.items() if k != "elapsed_seconds"})


def match_replay(row, expected):
    assert record_digest(row) == expected, "fresh replay differs from committed trajectory"


def verify_repeat(path, analysis):
    source = json.loads((path / "source.json").read_text())
    assert source["prefix_only"] and not source["smoke"]
    verify_sources(source)
    expected = {
        (r["condition"], r["seed"], r["step"]): r["sha256"]
        for r in json.loads((analysis / "prefix_hashes.json").read_text())
    }
    seen = set()
    with gzip.open(path / "points.jsonl.gz", "rt") as f:
        for line in f:
            row = json.loads(line)
            key = (row["condition"], row["seed"], row["step"])
            assert key in expected and key not in seen
            verify_row(row)
            match_replay(row, expected[key])
            seen.add(key)
    assert seen == set(expected) and len(seen) == 36
    result = {
        "fresh_prefix_points": len(seen),
        "complete_records_identical_except_timing": True,
        "source_sha": source["sha"],
        "scope": "second process, same implementation; not PC-B independent review",
    }
    (analysis / "repeat_verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
