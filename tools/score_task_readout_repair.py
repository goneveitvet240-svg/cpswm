"""Independent standard-library action, tuning, alias and feedback receipt audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from score_full_mechanism_value import paired_interval

LABELS = (
    "legacy_joint",
    "split_v06",
    "selected_joint",
    "matched_factorized",
    "selected_factorized",
    "latest",
    "amg",
)
GRIDS = {
    "joint": ["v06", "balanced", "slow"],
    "factorized": ["v06", "balanced", "slow"],
    "shared_spine_latest": [0.3, 0.5, 0.7],
    "matched_amg": [0.2, 0.33, 0.5],
}


def read(path):
    return json.loads(path.read_text())


def action_counts(result, visible, truth, settings):
    counts, coverage, phases = Counter(), Counter(), defaultdict(Counter)
    support = set(visible["known_location_ids"]) or {
        step[key]
        for step in visible["steps"]
        for key in (
            "source_location_id",
            "attempted_location_id",
            "observed_destination_location_id",
        )
        if step[key] is not None
    }
    assert len(result["actions"]) == len(visible["steps"]) == result["metric"]["step_count"]
    start = datetime.fromisoformat(visible["steps"][0]["timestamp"]).date()
    for row, step in zip(result["actions"], visible["steps"], strict=True):
        assert row["step_id"] == step["step_id"]
        rank = row["search_order"]
        assert len(rank) == len(support) and set(rank) == support and row["put_back"] in support
        target = truth["truth_by_step"][row["step_id"]]
        put = row["put_back"] != target["true_owner_habit_location"]
        search = rank[0] != target["true_location"]
        regret = int(put) + (
            rank.index(target["true_location"]) / max(1, len(support) - 1)
            if target["true_location"] in rank
            else 1.0
        )
        measure = {
            "n": 1,
            "put_errors": int(put),
            "search_errors": int(search),
            "action_regret": regret,
        }
        counts.update(measure)
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
        phases[phase].update(measure)
        coverage["targets_require_distinct_actions"] += (
            target["true_owner_habit_location"] != target["true_location"]
        )
        coverage["same_put_and_search_head"] += row["put_back"] == rank[0]
        coverage["long_term_nonempty_steps"] += row.get("committed", 0) > 0
        coverage["put_differs_latest"] += (
            "latest_choice" in row and row["put_back"] != row["latest_choice"]
        )
        if "task_readout" in row:
            receipt = row["task_readout"]
            assert receipt["search_order"] == rank == receipt["native_search_order"]
            assert receipt["put_back"] == row["put_back"]
            distribution = receipt["habit_distribution"]
            assert set(distribution) == support and all(
                math.isfinite(v) and v >= 0 for v in distribution.values()
            )
            assert math.isclose(sum(distribution.values()), 1.0, abs_tol=1e-9)
            if not receipt["joint_cold_start"]:
                assert min(distribution, key=lambda k: (-distribution[k], k)) == row["put_back"]
            coverage["joint_cold_start"] += receipt["joint_cold_start"]
    n = counts["n"]
    for key, value in (
        ("put_back_error_rate", counts["put_errors"] / n),
        ("search_error_rate", counts["search_errors"] / n),
        ("cumulative_action_regret", counts["action_regret"]),
    ):
        assert math.isclose(result["metric"][key], value, abs_tol=1e-10), (key, value)
    for trace in result["metric"]["revision_action_traces"]:
        index = trace["planner_prediction_index"]
        if index is not None:
            output = trace["next_action_distribution"]
            put = [r["location_id"] for r in output if r["action"] == "put_back"]
            search = [
                r["location_id"]
                for r in sorted(output, key=lambda r: -r["probability"])
                if r["action"] == "search"
            ]
            assert put == [result["actions"][index]["put_back"]]
            assert search == result["actions"][index]["search_order"]
            coverage["bound_feedback_actions"] += 1
        if trace["project_one_request"]:
            coverage["request_" + trace["project_one_request"]["kind"]] += 1
            coverage["request_status_" + trace["request_application_status"]] += 1
    for k, v in result.get("ledger_operations", {}).items():
        coverage["ledger_" + k] += v
    for k, v in result.get("operator_changes", {}).items():
        coverage["changed_" + k] += v
    return counts, coverage, phases


def verify(folder, development, root):
    complete = read(folder / "completion.json")
    assert complete["source_unchanged"] and complete["phase"] == "eval"
    sources = read(folder / "source.json")["files"]
    assert sources == read(development / "source.json")["files"]
    for name, digest in sources.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
    selection = read(folder / "selection.json")
    assert (
        selection == read(development / "selection.json") and selection["source_files"] == sources
    )
    digest = hashlib.sha256((folder / "selection.json").read_bytes()).hexdigest()
    assert (
        digest
        == complete["selection_sha256"]
        == read(folder / "evaluation_start.json")["selection_sha256"]
    )
    summary = read(folder / "summary.json")
    settings = summary["settings"]
    dev_metrics = {}
    for engine, grid in GRIDS.items():
        assert [r["parameter"] for r in selection["trials"][engine]] == grid
        trials = []
        for parameter in grid:
            records = read(development / f"dev-{engine}-{parameter}.json")
            assert len(records) == 3
            counts = Counter()
            for i, record in enumerate(records):
                assert record["engine"] == engine and record["parameter"] == parameter
                c, _, _ = action_counts(
                    record,
                    read(development / f"dev-visible-{i}.json"),
                    read(development / f"dev-evaluator-truth-{i}.json"),
                    settings,
                )
                counts.update(c)
            regret = counts["action_regret"] / counts["n"]
            expected = next(r for r in selection["trials"][engine] if r["parameter"] == parameter)
            assert math.isclose(
                regret, expected["cumulative_action_regret_per_step"], abs_tol=1e-10
            )
            trials.append({"parameter": parameter, "regret": regret, **counts})
        chosen = min(trials, key=lambda r: r["regret"])["parameter"]
        assert chosen == selection["selected"][engine] == summary["selection"][engine]
        dev_metrics[engine] = trials
    chosen = selection["selected"]
    expected_configs = dict(
        zip(
            LABELS,
            [
                ["legacy", "v06"],
                ["joint", "v06"],
                ["joint", chosen["joint"]],
                ["factorized", chosen["joint"]],
                ["factorized", chosen["factorized"]],
                ["shared_spine_latest", chosen["shared_spine_latest"]],
                ["matched_amg", chosen["matched_amg"]],
            ],
            strict=True,
        )
    )
    assert read(folder / "configurations.json") == expected_configs
    aliases = read(folder / "aliases.json")
    assert set(aliases) == set(LABELS)
    assert len(set(aliases.values())) == len({tuple(c) for c in expected_configs.values()})
    aggregates, coverage, phases = (
        {m: Counter() for m in LABELS},
        {m: Counter() for m in LABELS},
        {m: defaultdict(Counter) for m in LABELS},
    )
    per_episode = {m: [] for m in LABELS}
    paired = Counter()
    for i in range(len(complete["test_seeds"])):
        visible, truth = (
            read(folder / f"visible-{i}.json"),
            read(folder / f"evaluator-truth-{i}.json"),
        )
        results = {label: read(folder / f"test-{i}-{aliases[label]}.json") for label in LABELS}
        assert len({r["visible_input_sha256"] for r in results.values()}) == 1
        assert len({r["metric"]["visible_input_hash"] for r in results.values()}) == 1
        for label, result in results.items():
            assert (
                [result["engine"], result["parameter"]]
                == expected_configs[label]
                == expected_configs[aliases[label]]
            )
            c, cov, ph = action_counts(result, visible, truth, settings)
            aggregates[label].update(c)
            coverage[label].update(cov)
            for name, counts in ph.items():
                phases[label][name].update(counts)
            per_episode[label].append({k: v / c["n"] for k, v in c.items() if k != "n"})
        joint, factor = (results[k] for k in ("selected_joint", "matched_factorized"))
        jf, ff = (r["runtime_audit"]["fairness_receipts"] for r in (joint, factor))
        assert len(jf) == len(ff) > 0
        for a, b in zip(jf, ff, strict=True):
            assert {k: v for k, v in a.items() if k not in ("arm", "proposal_support_sha256")} == {
                k: v for k, v in b.items() if k not in ("arm", "proposal_support_sha256")
            }
            paired["matched_fairness_receipts"] += 1
        old, split = results["legacy_joint"], results["split_v06"]
        assert [r["put_back"] for r in old["actions"]] == [r["put_back"] for r in split["actions"]]
        for a, b in zip(joint["actions"], factor["actions"], strict=True):
            paired["joint_factor_put_disagreements"] += a["put_back"] != b["put_back"]
            paired["joint_factor_search_disagreements"] += a["search_order"] != b["search_order"]
        for a, b in zip(joint["actions"], split["actions"], strict=True):
            paired["selected_vs_v06_put_disagreements"] += a["put_back"] != b["put_back"]
    assert complete["actual_runs"] == len(set(aliases.values())) * len(complete["test_seeds"])
    assert complete["logical_runs"] == len(LABELS) * len(complete["test_seeds"])
    for label, counts in aggregates.items():
        for key, metric in (
            ("put_errors", "put_back_error_rate"),
            ("search_errors", "search_error_rate"),
            ("action_regret", "cumulative_action_regret_per_step"),
        ):
            assert math.isclose(
                counts[key] / counts["n"], summary["metrics"][label][metric], abs_tol=1e-10
            )
    differences = {
        label: {
            key: paired_interval(
                [a[key] - b[key] for a, b in zip(per_episode["selected_joint"], rows, strict=True)]
            )
            for key in ("put_errors", "search_errors", "action_regret")
        }
        for label, rows in per_episode.items()
        if label != "selected_joint"
    }
    return {
        "condition": complete["condition"],
        "counts": aggregates,
        "coverage": coverage,
        "phases": phases,
        "development": dev_metrics,
        "paired": paired,
        "joint_minus_control_lower_is_better": differences,
        "actual_test_runs": complete["actual_runs"],
        "logical_test_runs": complete["logical_runs"],
        "boundary": (
            "D0 development diagnostic; intervals descriptive; "
            "natural sensors and robot execution untested"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.folder, args.development, args.root)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "condition": result["condition"],
                "counts": result["counts"],
                "paired": result["paired"],
            }
        )
    )
