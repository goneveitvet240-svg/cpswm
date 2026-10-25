"""Recompute descriptive tie and paired win/loss counts from delivered raw records."""

import argparse
import gzip
import json
from pathlib import Path


def derive(directory):
    points = json.loads(gzip.decompress((directory / "points.json.gz").read_bytes()))
    q1 = json.loads((directory / "q1/scored.json").read_text())
    result = {"tie_tolerance": 1e-10, "q1": {}, "q23": {}, "paired_joint_vs_ablation": {}}
    for row in q1:
        key = row["arm"] + "/" + row["method"]
        report = result["q1"].setdefault(
            key,
            {
                "points": 0,
                "argmax_errors": 0,
                "ties": 0,
                "truth_outside_max_set": 0,
                "true_probability_sum": 0,
            },
        )
        dist = row["actor_distribution"]
        top = [name for name, value in dist.items() if max(dist.values()) - value <= 1e-10]
        report["points"] += 1
        report["argmax_errors"] += min(dist, key=lambda x: (-dist[x], x)) != row["true_actor"]
        report["ties"] += len(top) > 1
        report["truth_outside_max_set"] += row["true_actor"] not in top
        report["true_probability_sum"] += dist.get(row["true_actor"], 0)
    for name in points[0]["variants"]:
        arm = name.split("/")[0]
        counter = {
            "points": 0,
            "errors": 0,
            "fixed": 0,
            "harmed": 0,
            "changed": 0,
            "recurrence_errors": 0,
        }
        for point in points:
            old = point["controls"][arm]["put_back"]
            new = point["variants"][name]["action"]["put_back"]
            truth = point["truth"]
            counter["points"] += 1
            counter["errors"] += new != truth
            counter["fixed"] += old != truth and new == truth
            counter["harmed"] += old == truth and new != truth
            counter["changed"] += old != new
            counter["recurrence_errors"] += (
                point["old_error_class"] == "recurrence" and new != truth
            )
        result["q23"][name] = counter
    for policy in ["actor_read", "history_read"]:
        counter = {"joint_wins": 0, "joint_losses": 0, "same_correctness": 0}
        for p in points:
            joint = p["variants"]["native_joint/" + policy]["action"]["put_back"] == p["truth"]
            ablated = (
                p["variants"]["native_six_potential_ablation/" + policy]["action"]["put_back"]
                == p["truth"]
            )
            counter["joint_wins"] += joint and not ablated
            counter["joint_losses"] += ablated and not joint
            counter["same_correctness"] += joint == ablated
        result["paired_joint_vs_ablation"][policy] = counter
    result["joint_read_components"] = {}
    for policy in ["actor_read", "history_read"]:
        guaranteed = 0
        recurrence = []
        for p in points:
            v = p["variants"]["native_joint/" + policy]
            raw = v["raw"]
            total = sum(raw["base"].values())
            base = {k: x / total for k, x in raw["base"].items()}
            ledger = raw["ledger"]
            w = 1 if ledger is None else 0.75
            mass = v["scalar"]["analytic_mass"]
            fixed = {k: w * (1 - mass) * base[k] + (1 - w) * (ledger or {}).get(k, 0) for k in base}
            winner = v["action"]["put_back"]
            guaranteed += (
                min(fixed[winner] - fixed[k] - w * mass for k in fixed if k != winner) > 1e-10
            )
            if p["old_error_class"] != "recurrence":
                continue
            # Below 1e-12, subtraction and division are ill-conditioned.
            # Do not report a fabricated component.
            analytic = None
            if mass >= 1e-12:
                final = v["raw"]["actual"]
                pre = (
                    final
                    if ledger is None
                    else {k: (x - 0.25 * ledger.get(k, 0)) / 0.75 for k, x in final.items()}
                )
                analytic = {k: (pre[k] - (1 - mass) * base[k]) / mass for k in base}
            recurrence.append(
                {
                    "episode_id": p["episode_id"],
                    "step": p["step"],
                    "analytic_mass": mass,
                    "analytic_truth_probability": None
                    if analytic is None
                    else analytic[p["truth"]],
                    "analytic_top_is_truth": None
                    if analytic is None
                    else min(analytic, key=lambda k: (-analytic[k], k)) == p["truth"],
                }
            )
        result["joint_read_components"][policy] = {
            "guaranteed_unchanged_at_fixed_mass": guaranteed,
            "recurrence": recurrence,
        }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(derive(args.directory), indent=2))
