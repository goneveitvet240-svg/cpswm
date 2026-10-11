"""Action changes and phase attribution from saved development/evaluation outputs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from score_task_readout_repair import read


def compare(joint, factor):
    pairs = [
        (a, b)
        for j, f in zip(joint, factor, strict=True)
        for a, b in zip(j["actions"], f["actions"], strict=True)
    ]
    return {
        "n": len(pairs),
        "put_disagreements": sum(a["put_back"] != b["put_back"] for a, b in pairs),
        "search_rank_disagreements": sum(a["search_order"] != b["search_order"] for a, b in pairs),
        "unknown_difference_above_1e_minus_12": sum(
            abs(a["unknown_probability"] - b["unknown_probability"]) > 1e-12 for a, b in pairs
        ),
        "max_unknown_difference": max(
            abs(a["unknown_probability"] - b["unknown_probability"]) for a, b in pairs
        ),
    }


def summarize(root):
    summary = {}
    for condition in ("complete32", "sparse32", "long64"):
        dev, ev = root / ("dev-" + condition), root / ("eval-" + condition)
        settings = read(ev / "summary.json")["settings"]
        baseline = read(dev / "dev-joint-v06.json")
        profiles = {}
        for profile in ("v06", "balanced", "slow"):
            j = read(dev / f"dev-joint-{profile}.json")
            f = read(dev / f"dev-factorized-{profile}.json")
            shifts = Counter()
            for i, (base, changed) in enumerate(zip(baseline, j, strict=True)):
                visible = read(dev / f"dev-visible-{i}.json")
                truth = read(dev / f"dev-evaluator-truth-{i}.json")["truth_by_step"]
                start = datetime.fromisoformat(visible["steps"][0]["timestamp"]).date()
                for a, b, step in zip(
                    base["actions"], changed["actions"], visible["steps"], strict=True
                ):
                    if a["put_back"] == b["put_back"]:
                        continue
                    day = (datetime.fromisoformat(step["timestamp"]).date() - start).days
                    phase = (
                        "recurrence"
                        if day >= settings["recurrence_day"]
                        else "new_habit"
                        if day >= settings["abrupt_day"]
                        else "post_guest"
                        if day > settings["guest_window"][1]
                        else "guest"
                        if day >= settings["guest_window"][0]
                        else "initial"
                    )
                    target = truth[a["step_id"]]["true_owner_habit_location"]
                    outcome = (
                        "rescued"
                        if b["put_back"] == target
                        else "broke_correct"
                        if a["put_back"] == target
                        else "both_wrong"
                    )
                    shifts[phase + ":" + outcome] += 1
            profiles[profile] = {
                "joint_factorized": compare(j, f),
                "changed_put_outcomes_vs_v06": shifts,
            }
        aliases = read(ev / "aliases.json")
        seeds = read(ev / "completion.json")["test_seeds"]
        joint = [read(ev / f"test-{i}-{aliases['selected_joint']}.json") for i in range(len(seeds))]
        factor = [
            read(ev / f"test-{i}-{aliases['matched_factorized']}.json") for i in range(len(seeds))
        ]
        summary[condition] = {
            "development": profiles,
            "evaluation_joint_factorized": compare(joint, factor),
        }
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(summarize(args.root), indent=2, sort_keys=True) + "\n")
