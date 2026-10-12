"""Independent selection, same-budget controls, tamper and fresh-repeat checks."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from score_current_event import read, verify, verify_run


def check(main, repeat, repository):
    scores = {phase: verify(main / phase) for phase in ("dev", "test")}
    for phase in scores:
        assert scores[phase] == read(main / (phase + "-score.json"))
    source = read(main / "dev/source.json")["files"]
    assert (
        source == read(main / "test/source.json")["files"] == read(repeat / "source.json")["files"]
    )
    for file, value in source.items():
        assert hashlib.sha256((repository / file).read_bytes()).hexdigest() == value
    selection = read(main / "dev/freeze.json")["selected"]
    independent = {}
    for arm in selection:
        errors = {
            p: sum(
                v["put_errors"]
                for k, v in scores["dev"]["totals"].items()
                if k.endswith("/" + arm + "-" + p)
            )
            for p in ("v06", "balanced")
        }
        independent[arm] = min(errors, key=lambda p: (errors[p], ("v06", "balanced").index(p)))
    assert selection == independent
    for item in read(main / "test/index.json"):
        label = item["label"]
        config = item["config"]
        arm = config["arm"]
        expected_profile = (
            selection[arm] if label in ("joint", "factor") else selection["stateful_full_joint"]
        )
        assert config["profile"] == expected_profile
        assert config["consume_new"] == ("no_new" not in label)
    verify(repeat)
    repeat_count = 0
    for f in sorted(repeat.glob("run-*.json")):
        a = read(f)
        b = read(main / "test" / f.name)
        a.pop("wall_seconds")
        b.pop("wall_seconds")
        assert a == b, f.name
        repeat_count += 1
    index = next(i for i in read(main / "test/index.json") if i["label"] == "joint")
    root = main / "test"
    original = read(root / index["file"])
    visible = read(root / index["visible"])
    truth = read(root / index["truth"])
    changed = next(i for i, a in enumerate(original["actions"]) if a["location_source_id"])
    attacks = [
        "current_event",
        "step_count",
        "put",
        "paid_cost",
        "receipt",
        "actor_likelihood",
        "native_weight",
        "mixed_source",
        "remove_native_write",
        "duplicate_event",
        "task_readout",
    ]
    for attack in attacks:
        run = copy.deepcopy(original)
        row = run["actions"][changed]
        n = run["native_evidence"][changed]
        if attack == "current_event":
            row["event_id"] = "old-event"
        elif attack == "step_count":
            row["native_step_index"] += 1
        elif attack == "put":
            row["put_back"] = "nonexistent"
        elif attack == "paid_cost":
            row["search"]["paid_checks"] += 1
        elif attack == "receipt":
            row["search"]["updates"][-1]["receipt"]["found"] = False
        elif attack == "actor_likelihood":
            n["observation"]["location_likelihood"][0][1] *= 0.8
        elif attack == "native_weight":
            n["weights"][0] += 0.1
        elif attack == "mixed_source":
            n["receipts"][0]["independent_observation_source_id"] = row["event_id"]
        elif attack == "remove_native_write":
            row["location_source_id"] = None
        elif attack == "duplicate_event":
            run["actions"][-1]["event_id"] = run["actions"][0]["event_id"]
        elif attack == "task_readout":
            run["task_readout_actions"][changed]["search_order"] = []
        try:
            verify_run(run, visible, truth)
        except (AssertionError, ValueError, KeyError):
            pass
        else:
            raise AssertionError("tamper passed: " + attack)
    revisions = read(main / "revisions.json")
    assert revisions["actual_step_executions"] == 42
    revision_results = []
    for case in revisions["cases"]:
        branches = case["branches"]
        control = branches["control"]
        restored = branches["restore"]
        withdrawn = branches["withdraw"]
        assert (
            control["next_action"] == restored["next_action"]
            and control["final_state"] == restored["final_state"]
        )
        assert withdrawn["before"] != withdrawn["after_revision"]
        revision_results.append(
            {
                "arm": case["arm"],
                "restore_exact": True,
                "withdraw_changes_next_action": control["next_action"]["put_back"]
                != withdrawn["next_action"]["put_back"],
            }
        )
    return {
        "actual_runs": {p: s["actual_runs"] for p, s in scores.items()},
        "repeat_runs_exact_except_wall_seconds": repeat_count,
        "source_files_checked": len(source),
        "independent_profile_selection": independent,
        "tamper_rejections": attacks,
        "revision_continuations": revision_results,
        "additional_revision_step_executions": 42,
        "scope": "local bounded checks, not B acceptance or malicious-process isolation",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--main", type=Path, required=True)
    p.add_argument("--repeat", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    a = p.parse_args()
    r = check(a.main, a.repeat, a.repository)
    a.output.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
    print(json.dumps(r, sort_keys=True))
