"""Independent standard-library fee, truth, action, memory and receipt audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from score_full_mechanism_value import paired_interval

ARMS = ("passive", "current_rank", "joint_habit", "factor_habit", "recent_id")


def read(path):
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def completion_cost(order, negatives, found, query_count, target):
    """Include paid queries; never charge again for an already found object."""
    tail = [k for k in order if k not in negatives]
    retrieved = found is not None or target in tail
    remaining = 0 if found is not None else tail.index(target) + 1 if target in tail else len(tail)
    total = query_count + remaining
    extra = max(0, total - 1) / max(1, len(order) - 1) if retrieved else 1.0
    return total, remaining, retrieved, extra


def score_run(result, visible, truth):
    support = set(visible["known_location_ids"]) or {
        s[k]
        for s in visible["steps"]
        for k in ("source_location_id", "attempted_location_id", "observed_destination_location_id")
        if s[k] is not None
    }
    counts = Counter()
    memory = None
    seen_ids = set()
    rows = []
    assert len(result["actions"]) == len(visible["steps"]) > 0
    for row, step in zip(result["actions"], visible["steps"], strict=True):
        assert row["step_id"] == step["step_id"]
        target = truth["truth_by_step"][row["step_id"]]["true_location"]
        habit_target = truth["truth_by_step"][row["step_id"]]["true_owner_habit_location"]
        receipt = row["active_search"]
        policy = receipt["policy"]
        assert policy == result["policy"] and receipt["budget"] == result["budget"] == 2
        assert set(row["search_order"]) == support and len(row["search_order"]) == len(support)
        assert row["put_back"] == receipt["native_put_back"] and row["put_back"] in support
        assert receipt["location_query_changed_habit_state"] is False
        native = receipt["native_search_order"]
        assert set(native) == support and len(native) == len(support)
        after = step["after"]
        missing = after is None or after["detected_location_id"] is None
        assert missing == receipt["missing_passive_location"]
        if not missing:
            memory = after["detected_location_id"]
        current = list(native)
        if memory is not None:
            current.remove(memory)
            current.insert(0, memory)
        proposal = receipt["habit_proposal"]
        assert set(proposal) == support and all(
            math.isfinite(p) and p >= 0 for p in proposal.values()
        )
        assert math.isclose(sum(proposal.values()), 1.0, abs_tol=1e-9)
        if policy == "habit_rank":
            order = sorted(proposal, key=lambda k: (-proposal[k], k))
        elif policy == "recent_id":
            order = sorted(support)
            if memory is not None:
                order.remove(memory)
                order.insert(0, memory)
        else:
            order = current
        assert order == receipt["query_order"]
        inspections = receipt["inspections"]
        negatives = []
        found = None
        assert len(inspections) <= min(2, len(support))
        if not missing or policy == "passive":
            assert not inspections
        for i, entry in enumerate(inspections):
            req = entry["request"]
            assert set(req) == {"action_id", "episode_id", "step_id", "object_id", "location_id"}
            assert req["episode_id"] == visible["episode_id"] and req["step_id"] == step["step_id"]
            assert req["object_id"] == step["object_instance_id"]
            assert req["location_id"] == order[i] and req["action_id"] not in seen_ids
            seen_ids.add(req["action_id"])
            assert entry["ordinal"] == i + 1 and type(entry["found"]) is bool
            assert entry["found"] == (req["location_id"] == target)
            assert entry["receipt_sha256"] == digest(
                {"request": req, "ordinal": i + 1, "found": entry["found"]}
            )
            if entry["found"]:
                assert i == len(inspections) - 1
                found = req["location_id"]
                memory = found
            else:
                negatives.append(req["location_id"])
        if missing and policy != "passive" and found is None:
            assert len(inspections) == min(2, len(support))
        expected = [k for k in current if k not in negatives]
        if found is not None:
            expected.remove(found)
            expected.insert(0, found)
        expected.extend(k for k in current if k in negatives)
        assert expected == row["search_order"] == receipt["final_search_order"]
        assert found == receipt["found_location"] and memory == receipt["search_memory_location"]
        total, remaining, retrieved, extra = completion_cost(
            expected, negatives, found, len(inspections), target
        )
        put = int(row["put_back"] != habit_target)
        err = int(expected[0] != target)
        post = (expected.index(target) / max(1, len(support) - 1)) if target in expected else 1.0
        measurements = {
            "n": 1,
            "missing_steps": int(missing),
            "queries": len(inspections),
            "query_found": int(found is not None),
            "negative_queries": len(negatives),
            "put_errors": put,
            "post_query_search_errors": err,
            "charged_completion_inspections": total,
            "implied_remaining_inspections": remaining,
            "retrieval_failures": int(not retrieved),
            "charged_action_regret": put + extra,
            "uncharged_post_query_regret": put + post,
        }
        counts.update(measurements)
        rows.append({"step_id": step["step_id"], **measurements})
    metric = result["metric_post_query_uncharged"]
    n = counts["n"]
    assert metric["step_count"] == n
    for key, value in [
        ("put_back_error_rate", counts["put_errors"] / n),
        ("search_error_rate", counts["post_query_search_errors"] / n),
        ("cumulative_action_regret", counts["uncharged_post_query_regret"]),
    ]:
        assert math.isclose(metric[key], value, abs_tol=1e-9)
    for trace in metric["revision_action_traces"]:
        index = trace["planner_prediction_index"]
        if index is None:
            continue
        output = trace["next_action_distribution"]
        search = [
            p["location_id"]
            for p in sorted(output, key=lambda p: -p["probability"])
            if p["action"] == "search"
        ]
        put = [p["location_id"] for p in output if p["action"] == "put_back"]
        assert search == result["actions"][index]["search_order"]
        assert put == [result["actions"][index]["put_back"]]
        counts["bound_feedback_actions"] += 1
    return counts, rows


def verify(folder, root):
    completed = read(folder / "completion.json")
    assert completed["source_unchanged"]
    for name, h in read(folder / "source.json")["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == h, name
    totals = {a: Counter() for a in ARMS}
    per_episode = {a: [] for a in ARMS}
    paired = Counter()
    case_rows = []
    for i in range(completed["episode_count"]):
        visible, truth = read(folder / f"visible-{i}.json"), read(folder / f"truth-{i}.json")
        results = {a: read(folder / f"run-{i}-{a}.json") for a in ARMS}
        assert len({r["visible_input_sha256"] for r in results.values()}) == 1
        scored = {}
        for arm, r in results.items():
            assert r["arm"] == arm
            counts, rows = score_run(r, visible, truth)
            totals[arm].update(counts)
            scored[arm] = rows
            per_episode[arm].append(
                {
                    k: v / counts["n"]
                    for k, v in counts.items()
                    if k
                    in (
                        "charged_action_regret",
                        "charged_completion_inspections",
                        "post_query_search_errors",
                    )
                }
            )
        j, f = (results[a] for a in ("joint_habit", "factor_habit"))
        jr, fr = (r["runtime_audit"]["fairness_receipts"] for r in (j, f))
        assert len(jr) == len(fr) > 0
        for a, b in zip(jr, fr, strict=True):
            assert {k: v for k, v in a.items() if k not in ("arm", "proposal_support_sha256")} == {
                k: v for k, v in b.items() if k not in ("arm", "proposal_support_sha256")
            }
            paired["matched_fairness_receipts"] += 1
        for a, b in zip(j["actions"], f["actions"], strict=True):
            paired["joint_factor_query_disagreements"] += (
                a["active_search"]["inspections"] != b["active_search"]["inspections"]
            )
            paired["joint_factor_search_disagreements"] += a["search_order"] != b["search_order"]
        for arm in ARMS:
            if arm == "factor_habit":
                continue
            assert [a["put_back"] for a in results[arm]["actions"]] == [
                a["put_back"] for a in results["passive"]["actions"]
            ]
            for key in ("final_state_sha256", "rgrc_ledger_head_sha256"):
                assert (
                    results[arm]["runtime_audit"][key] == results["passive"]["runtime_audit"][key]
                ), (arm, key)
        for jrow, brow in zip(scored["joint_habit"], scored["current_rank"], strict=True):
            paired["joint_more_completion_inspections_steps"] += (
                jrow["charged_completion_inspections"] > brow["charged_completion_inspections"]
            )
            paired["joint_fewer_completion_inspections_steps"] += (
                jrow["charged_completion_inspections"] < brow["charged_completion_inspections"]
            )
        case_rows.append(
            {
                "index": i,
                "metrics": {
                    a: {
                        k: sum(row[k] for row in scored[a])
                        for k in (
                            "queries",
                            "post_query_search_errors",
                            "charged_completion_inspections",
                            "charged_action_regret",
                        )
                    }
                    for a in ARMS
                },
            }
        )
    assert completed["actual_runs"] == completed["episode_count"] * len(ARMS)
    deltas = {
        a: {
            key: paired_interval(
                [j[key] - b[key] for j, b in zip(per_episode["joint_habit"], rows, strict=True)]
            )
            for key in (
                "charged_action_regret",
                "charged_completion_inspections",
                "post_query_search_errors",
            )
        }
        for a, rows in per_episode.items()
        if a != "joint_habit"
    }
    return {
        "condition": completed["condition"],
        "phase": completed["phase"],
        "counts": totals,
        "paired": paired,
        "per_episode": case_rows,
        "joint_minus_control_lower_is_better": deltas,
        "boundary": (
            "Ideal D0 detector; completion cost includes evaluator-implied continuation; "
            "not physical runtime or calibrated current-location belief."
        ),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folder", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = verify(args.folder, Path(__file__).resolve().parents[1])
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
