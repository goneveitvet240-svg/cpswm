import argparse
import collections
import json
import pathlib

parser = argparse.ArgumentParser()
parser.add_argument("--input", type=pathlib.Path, required=True)
parser.add_argument("--output", type=pathlib.Path, required=True)
args = parser.parse_args()
p = args.input
assert json.loads((p / "completion.json").read_text())["source_unchanged"]
s = json.loads((p / "summary.json").read_text())
summary = {"conditions": {}, "aggregate": {}, "native_distributions": {}, "e2": {}}
aggregate = collections.defaultdict(collections.Counter)
changed = 0
max_tv = 0.0
joint_rank_disagreements = 0
latest_rank_disagreements = 0
operators = collections.Counter()
scores = collections.Counter()
refs = 0
checked = 0
for condition, data in s.items():
    summary["conditions"][condition] = {
        "totals": data["totals"],
        "champion": data["selection"]["simple_champion"],
        "selected": {
            k: v["trials"][v["selected_index"]]["parameter"]
            for k, v in data["selection"]["methods"].items()
        },
        "paired": data["paired_vs_joint"],
        "method_seconds": data["method_seconds"],
    }
    for method, values in data["totals"].items():
        aggregate[method].update(values)
    for f in (p / condition).glob("evaluation-*.json"):
        d = json.loads(f.read_text())
        truth = json.loads((f.parent / f.name.replace("evaluation-", "truth-")).read_text())[
            "truth_by_step"
        ]
        visible = json.loads((f.parent / f.name.replace("evaluation-", "visible-")).read_text())
        expected_steps = [x["step_id"] for x in visible["steps"]]
        for rows in d["rows"].values():
            assert [x["step_id"] for x in rows] == expected_steps
            for row in rows:
                t = truth[row["step_id"]]
                a = row["action"]
                order = a["search_order"]
                recomputed = {
                    "put_error": int(a["put_back"] != t["true_owner_habit_location"]),
                    "search_error": int(order[0] != t["true_location"]),
                    "rank_checks": order.index(t["true_location"]) + 1,
                }
                assert row["score"] == recomputed
                checked += 1
        for a, b, c in zip(
            d["rows"]["native_joint"],
            d["rows"]["native_six_potential_ablation"],
            d["rows"]["latest_owner"],
            strict=True,
        ):
            da, db = a["habit_distribution"], b["habit_distribution"]
            tv = sum(abs(da[k] - db[k]) for k in da) / 2
            changed += tv > 1e-12
            max_tv = max(max_tv, tv)
            joint_rank_disagreements += a["action"]["search_order"] != b["action"]["search_order"]
            latest_rank_disagreements += a["action"]["search_order"] != c["action"]["search_order"]
        for method, a in d["final_audits"].items():
            if a["native"]:
                scores[method] += a["target_evaluations"]
                assert a["extra_ciav_queries"] == a["paid_location_sources"] == 0
                if method == "native_joint":
                    operators.update(a["operator_executions"])
        assert all(x["equivalent"] and x["reference"] == x["actual"] for x in d["full_rerun"])
        refs += len(d["full_rerun"])
summary["aggregate"] = dict(aggregate)
summary["native_distributions"] = {
    "differing_habit_distributions_tv_gt_1e-12": changed,
    "max_tv": max_tv,
    "joint_ablation_search_order_disagreements": joint_rank_disagreements,
    "joint_latest_owner_search_order_disagreements": latest_rank_disagreements,
}
summary["checks"] = {
    "rescored_method_steps": checked,
    "full_prefix_replay_checks": refs,
    "joint_operator_executions": dict(operators),
    "target_score_evaluations": dict(scores),
}
if (p / "e2.json").exists():
    e = json.loads((p / "e2.json").read_text())
    summary["e2"]["followup_errors"] = {
        r["condition"] + "/" + r["trajectory"]: r["followup_errors"] for r in e["rows"]
    }
    summary["e2"]["method_input_checkpoints"] = sum(
        len(points) for r in e["rows"] for points in r["rows"].values()
    )
    summary["e2"]["trajectories"] = len(e["rows"])
    summary["e2"]["methods"] = len(e["configs"])
    for row in e["rows"]:
        hashes = [[x["input_sha256"] for x in pts] for pts in row["rows"].values()]
        assert all(h == hashes[0] for h in hashes)
        assert len(hashes[0]) == len(row["inputs"])
args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
print(json.dumps({k: v for k, v in summary.items() if k != "conditions"}, indent=2))
