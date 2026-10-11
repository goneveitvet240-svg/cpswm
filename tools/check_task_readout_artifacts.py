"""Bounded tamper rejection and fresh-repeat checks for task-readout artifacts."""

from __future__ import annotations

import argparse
import copy
import json
import tempfile
from pathlib import Path
from uuid import UUID

from score_task_readout_repair import action_counts, read, verify


def check(folder, development, root, repeat):
    summary = read(folder / "summary.json")
    aliases = read(folder / "aliases.json")
    result = read(folder / f"test-0-{aliases['selected_joint']}.json")
    visible, truth = read(folder / "visible-0.json"), read(folder / "evaluator-truth-0.json")
    action_counts(result, visible, truth, summary["settings"])
    rejected = []
    for kind in ("wrong_action", "wrong_search_receipt", "wrong_feedback_distribution"):
        bad = copy.deepcopy(result)
        if kind == "wrong_action":
            row = bad["actions"][0]
            row["put_back"] = next(k for k in row["search_order"] if k != row["put_back"])
        elif kind == "wrong_search_receipt":
            bad["actions"][0]["task_readout"]["native_search_order"].reverse()
        else:
            trace = next(
                r
                for r in bad["metric"]["revision_action_traces"]
                if r["planner_prediction_index"] is not None
            )
            put = next(r for r in trace["next_action_distribution"] if r["action"] == "put_back")
            put["location_id"] = "forged-location"
        try:
            action_counts(bad, visible, truth, summary["settings"])
        except AssertionError:
            rejected.append(kind)
        else:
            raise AssertionError(f"tamper accepted: {kind}")
    with tempfile.TemporaryDirectory(prefix="task-readout-tamper-") as name:
        temp = Path(name)
        for source in folder.iterdir():
            (temp / source.name).symlink_to(source)
        target = temp / "aliases.json"
        target.unlink()
        forged = dict(aliases)
        forged["matched_factorized"] = aliases["selected_joint"]
        target.write_text(json.dumps(forged))
        try:
            verify(temp, development, root)
        except AssertionError:
            rejected.append("factorized_alias_laundered_as_joint")
        else:
            raise AssertionError("forged alias accepted")
    original_selection = read(folder / "selection.json")
    assert original_selection == read(repeat / "selection.json")
    assert read(folder / "source.json")["files"] == read(repeat / "source.json")["files"]
    assert read(repeat / "completion.json")["test_seeds"] == [
        read(folder / "completion.json")["test_seeds"][0]
    ]
    assert read(repeat / "visible-0.json") == visible
    repeat_aliases = read(repeat / "aliases.json")
    snapshot_differences = {}
    for label, original in aliases.items():
        a = read(folder / f"test-0-{original}.json")
        b = read(repeat / f"test-0-{repeat_aliases[label]}.json")
        # Existing belief metadata uses per-execution UUID4 record IDs. Compare
        # every action/probability/receipt value, excluding only that raw pointer;
        # keep the original pointers in both archives and report their differences.
        left, right = copy.deepcopy(a["actions"]), copy.deepcopy(b["actions"])
        changed_ids = 0
        for x, y in zip(left, right, strict=True):
            if "task_readout" in x:
                old_id = x["task_readout"].pop("source_snapshot_id")
                new_id = y["task_readout"].pop("source_snapshot_id")
                UUID(old_id)
                UUID(new_id)
                changed_ids += old_id != new_id
        snapshot_differences[original] = changed_ids
        assert left == right, label
        for key in (
            "put_back_error_rate",
            "search_error_rate",
            "cumulative_action_regret",
            "revision_action_traces",
        ):
            assert a["metric"][key] == b["metric"][key], (label, key)
        if "runtime_audit" in a:
            assert a["runtime_audit"] == b["runtime_audit"], label
    return {
        "positive_action_trace_verified": True,
        "tamper_rejections": rejected,
        "fresh_repeat_logical_arms": len(aliases),
        "fresh_repeat_actual_runs": len(set(aliases.values())),
        "repeat_actions_metrics_and_runtime_audits_identical": True,
        "excluded_cross_run_field": "actions[*].task_readout.source_snapshot_id",
        "raw_snapshot_id_differences_by_actual_arm": snapshot_differences,
        "scope": "bounded artifact and replay audit; not complete forged-path acceptance",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder", type=Path)
    p.add_argument("--development", type=Path, required=True)
    p.add_argument("--repeat", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    value = check(args.folder, args.development, Path(__file__).resolve().parents[1], args.repeat)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps(value))
