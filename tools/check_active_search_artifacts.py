"""Bounded artifact attacks and exact fresh-process repeat for active search."""

from __future__ import annotations

import argparse
import copy
import json
import tempfile
from pathlib import Path

from score_active_location_search import ARMS, digest, read, score_run, verify


def check(folder, repeat, root):
    result = read(folder / "run-0-joint_habit.json")
    visible, truth = read(folder / "visible-0.json"), read(folder / "truth-0.json")
    score_run(result, visible, truth)
    rejected = []
    for kind in (
        "complete_false_found_with_recomputed_hash",
        "wrong_location_with_recomputed_hash",
        "removed_paid_inspection",
        "wrong_emitted_search",
        "wrong_feedback_distribution",
    ):
        bad = copy.deepcopy(result)
        queried = next(a for a in bad["actions"] if a["active_search"]["inspections"])
        receipt = queried["active_search"]["inspections"][0]
        if kind == "complete_false_found_with_recomputed_hash":
            receipt["found"] = not receipt["found"]
        elif kind == "wrong_location_with_recomputed_hash":
            receipt["request"]["location_id"] = next(
                loc for loc in queried["search_order"] if loc != receipt["request"]["location_id"]
            )
        elif kind == "removed_paid_inspection":
            queried["active_search"]["inspections"].pop(0)
        elif kind == "wrong_emitted_search":
            bad["actions"][0]["search_order"].reverse()
        else:
            trace = next(
                t
                for t in bad["metric_post_query_uncharged"]["revision_action_traces"]
                if t["planner_prediction_index"] is not None
            )
            next(p for p in trace["next_action_distribution"] if p["action"] == "put_back")[
                "location_id"
            ] = "forged"
        if kind.endswith("recomputed_hash"):
            receipt["receipt_sha256"] = digest(
                {k: receipt[k] for k in ("request", "ordinal", "found")}
            )
        try:
            score_run(bad, visible, truth)
        except AssertionError:
            rejected.append(kind)
        else:
            raise AssertionError(f"tamper accepted: {kind}")
    for kind in ("factorized_laundered_as_joint", "wrong_input_hash", "changed_habit_ledger"):
        with tempfile.TemporaryDirectory(prefix="active-search-tamper-") as name:
            temp = Path(name)
            for source in folder.iterdir():
                (temp / source.name).symlink_to(source)
            if kind == "factorized_laundered_as_joint":
                name = "run-0-factor_habit.json"
                bad = copy.deepcopy(result)
                bad["arm"], bad["engine"] = "factor_habit", "factorized"
            else:
                name = "run-0-joint_habit.json"
                bad = copy.deepcopy(result)
                if kind == "wrong_input_hash":
                    bad["visible_input_sha256"] = "forged"
                else:
                    bad["runtime_audit"]["rgrc_ledger_head_sha256"] = "forged"
            (temp / name).unlink()
            (temp / name).write_text(json.dumps(bad))
            try:
                verify(temp, root)
            except AssertionError:
                rejected.append(kind)
            else:
                raise AssertionError(f"tamper accepted: {kind}")
    assert read(folder / "source.json")["files"] == read(repeat / "source.json")["files"]
    assert read(repeat / "completion.json")["seeds"] == [
        read(folder / "completion.json")["seeds"][0]
    ]
    assert read(repeat / "visible-0.json") == visible
    assert read(repeat / "truth-0.json") == truth
    for arm in ARMS:
        a, b = (read(p / f"run-0-{arm}.json") for p in (folder, repeat))
        a.pop("wall_seconds")
        b.pop("wall_seconds")
        assert a == b, arm
    return {
        "positive_action_trace_verified": True,
        "tamper_rejections": rejected,
        "fresh_repeat_actual_runs": len(ARMS),
        "repeat_all_outputs_identical_except_wall_seconds": True,
        "scope": "Local partial artifact audit; no hostile-process or full acceptance claim",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder", type=Path)
    p.add_argument("--repeat", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    value = check(args.folder, args.repeat, Path(__file__).resolve().parents[1])
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    print(json.dumps(value))
