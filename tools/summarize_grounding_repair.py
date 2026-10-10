"""Independent arithmetic summary; no policy selection or parameter fitting."""

from __future__ import annotations

import argparse
from pathlib import Path

from run_matched_transition_death_test import digest, load, save


def summarize(directory, output):
    manifest = load(directory / "comparison.json")
    totals = {}
    checked = 0
    for case in manifest["cases"]:
        stem = f"{case['seed']}-{case['actor_mode']}-{case['policy']}"
        path = directory / (stem + ".json")
        full = load(path)
        assert full["metrics"] == case["metrics"]
        key = f"{case['actor_mode']}/{case['policy']}"
        group = totals.setdefault(
            key,
            dict(
                n=0,
                runtime=0,
                soft_full_history=0,
                soft_half_life_1=0,
                soft_half_life_3=0,
                soft_half_life_7=0,
                actor_preservation_max_difference=0,
                committed_final=[],
                recovery_passed=0,
                seconds=0,
                stages={},
                paired_choices=[],
            ),
        )
        methods = {
            "runtime": lambda r: r["command"],
            "soft_full_history": lambda r: r["soft_full_history"],
            "soft_half_life_1": lambda r: r["soft_recency"]["1.0"],
            "soft_half_life_3": lambda r: r["soft_recency"]["3.0"],
            "soft_half_life_7": lambda r: r["soft_recency"]["7.0"],
        }
        for row in full["rows"]:
            group["n"] += 1
            for method, get in methods.items():
                group[method] += int(get(row) == row["true_habit"])
            if row["ciav_actor"] is not None:
                group["actor_preservation_max_difference"] = max(
                    group["actor_preservation_max_difference"],
                    *(abs(row["primary_actor"][a] - v) for a, v in row["ciav_actor"].items()),
                )
            assert row["command"] == row["command_location"]
            checked += 1
        group["committed_final"].append(full["rows"][-1]["committed"])
        group["recovery_passed"] += int(full["recovery_equal"])
        group["seconds"] += full["seconds"]
        for stage, value in case["metrics"].items():
            g = group["stages"].setdefault(stage, dict(n=0, correct=0))
            g["n"] += value["n"]
            g["correct"] += value["correct"]["runtime"]
    save(
        output,
        dict(
            totals=totals,
            checked_commands=checked,
            original_manifest_sha256=digest(directory / "comparison.json"),
            scope="POST_OBSERVATION_HABIT_PUT_BACK_CHOICES_SEMANTIC_ORACLE_NOT_REAL_LONG_HORIZON_EXECUTION",
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    summarize(a.directory, a.output)
