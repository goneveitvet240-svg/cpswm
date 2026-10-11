"""Bounded artifact attacks, independent development choice and adapter equivalence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from score_current_location import digest, read, score_run, verify


def check(main, repeat, repository):
    scores = {name: verify(main / name) for name in ("dev", "test", "integrate")}
    repeat_score = verify(repeat)
    manifest = read(main / "dev/source.json")["files"]
    for folder in (main / "test", main / "integrate", repeat):
        assert read(folder / "source.json")["files"] == manifest
    for name, sha in manifest.items():
        assert hashlib.sha256((repository / name).read_bytes()).hexdigest() == sha, name
    freeze = read(main / "dev/freeze.json")
    dev_totals = defaultdict(Counter)
    dev_configs = {}
    for item in scores["dev"]["episodes"]:
        dev_totals[item["view"]][item["arm"]] += item["counts"]["checks"]
        dev_configs[item["arm"]] = read(main / "dev" / item["file"])["config"]
    assert dict(dev_totals) == freeze["dev_totals"]
    for view, configs in freeze["selected"].items():
        for kind in ("markov", "joint", "factor"):
            winner = min(
                (key for key in dev_totals[view] if key.startswith(kind + "-")),
                key=lambda key: (
                    dev_totals[view][key],
                    dev_configs[key]["alpha"],
                    dev_configs[key]["decay"],
                ),
            )
            assert configs[kind] == dev_configs[winner]
        assert configs["matched_factor"] == {**configs["joint"], "kind": "factor"}
    actual_test = {
        i["file"]: read(main / "test" / i["file"]) for i in read(main / "test/index.json")
    }
    repeated = 0
    for item in read(repeat / "index.json"):
        left, right = copy.deepcopy(actual_test[item["file"]]), read(repeat / item["file"])
        left.pop("wall_seconds")
        right.pop("wall_seconds")
        assert left == right
        assert read(repeat / item["visible"]) == read(main / "test" / item["visible"])
        assert read(repeat / item["truth"]) == read(main / "test" / item["truth"])
        repeated += 1
    integrated, groups = 0, defaultdict(list)
    for item in read(main / "integrate/index.json"):
        run = read(main / "integrate" / item["file"])
        assert run["actions"] == actual_test[item["file"]]["actions"]
        groups[item["condition"], item["episode"]].append(run)
        integrated += 1
    for runs in groups.values():
        for run in runs[1:]:
            assert [a["put_back"] for a in run["framework_actions"]] == [
                a["put_back"] for a in runs[0]["framework_actions"]
            ]
            for key in ("final_state_sha256", "rgrc_ledger_head_sha256"):
                assert run["runtime_audit"][key] == runs[0]["runtime_audit"][key]
    item = next(
        i
        for i in read(main / "test/index.json")
        if i["view"] == "cue_only" and i["arm"] == "joint" and i["condition"] == "sparse32"
    )
    base = actual_test[item["file"]]
    visible, truth = read(main / "test" / item["visible"]), read(main / "test" / item["truth"])
    attacks = (
        "paid_count",
        "input_actor",
        "input_location",
        "prior",
        "posterior",
        "learned_hash",
        "previous",
        "plan",
        "ordinal",
        "rehashed_false_detector",
        "duplicate_action",
        "future_terminal",
        "remove_step",
        "input_source_hash",
    )
    rejected = []
    for attack in attacks:
        run = copy.deepcopy(base)
        row = run["actions"][0]
        if attack == "paid_count":
            row["paid_checks"] = 0
        elif attack == "input_actor":
            missing = next(r for r in run["actions"] if r["input"]["actor_cue"] is None)
            missing["input"]["actor_cue"] = dict.fromkeys(run["actors"], 1 / len(run["actors"]))
            missing["input_sha256"] = digest(missing["input"])
        elif attack == "input_location":
            row["input"]["visible_location"] = row["found"]
            row["input_sha256"] = digest(row["input"])
        elif attack == "prior":
            row["prior_joint"][run["actors"][0]][run["locations"][0]] += 0.1
        elif attack == "posterior":
            row["updates"][0]["posterior_joint"][run["actors"][0]][run["locations"][0]] += 0.1
        elif attack == "learned_hash":
            row["history_after_sha256"] = "0" * 64
        elif attack == "previous":
            run["actions"][1]["previous"] = None
        elif attack == "plan":
            row["planned_order"][0], row["planned_order"][1] = (
                row["planned_order"][1],
                row["planned_order"][0],
            )
        elif attack == "ordinal":
            row["updates"][0]["receipt"]["ordinal"] += 1
        elif attack == "rehashed_false_detector":
            receipt = row["updates"][0]["receipt"]
            receipt["found"] = not receipt["found"]
            receipt["receipt_sha256"] = digest(
                {k: v for k, v in receipt.items() if k != "receipt_sha256"}
            )
        elif attack == "duplicate_action":
            receipt = run["actions"][1]["updates"][0]["receipt"]
            receipt["request"]["action_id"] = row["updates"][0]["receipt"]["request"]["action_id"]
            receipt["receipt_sha256"] = digest(
                {k: v for k, v in receipt.items() if k != "receipt_sha256"}
            )
        elif attack == "future_terminal":
            row["found"] = next(loc for loc in run["locations"] if loc != row["found"])
        elif attack == "remove_step":
            run["actions"].pop()
        elif attack == "input_source_hash":
            run["visible_sha256"] = "0" * 64
        try:
            score_run(run, visible, truth)
        except (AssertionError, ValueError, KeyError, TypeError):
            rejected.append(attack)
        else:
            raise AssertionError(f"tamper accepted: {attack}")
    return {
        "independent_development_selection": True,
        "tamper_rejections": rejected,
        "fresh_repeat_runs_exact_except_wall_seconds": repeated,
        "full_adapter_runs_equal_to_isolated_search": integrated,
        "full_adapter_put_habit_ledger_equal_groups": len(groups),
        "source_files_checked": len(manifest),
        "actual_runs": {
            **{key: value["actual_runs"] for key, value in scores.items()},
            "repeat": repeat_score["actual_runs"],
        },
        "scope": (
            "local bounded checks; not B acceptance, malicious-process isolation, "
            "or full native joint-location inference"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--repeat", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.main, args.repeat, args.repository)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
