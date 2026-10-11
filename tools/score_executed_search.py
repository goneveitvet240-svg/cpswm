"""Independent standard-library fee, truth, action, memory and receipt audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from score_full_mechanism_value import paired_interval

ARMS = (
    "terminal_only",
    "current_rank",
    "joint_habit",
    "factor_habit",
    "recent_id",
    "current_no_carry",
)


def read(path):
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


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
        execution = row["search_execution"]
        assert execution["step_id"] == step["step_id"]
        carry = result["arm"] != "current_no_carry"
        assert result["carry_terminal_memory"] is carry
        assert execution["carry_terminal_memory"] is carry
        assert execution["probe_budget"] == 2 and execution["total_budget"] == len(support)
        assert execution["submitted_search_order"] == expected
        assert execution["search_memory_before_completion"] == memory
        assert execution["location_execution_changed_habit_state"] is False
        staged = execution["staged_receipts"]
        assert 1 <= len(staged) <= len(support)
        assert len(staged) == execution["paid_checks"]
        assert [r["receipt"] for r in staged if r["phase"] == "probe"] == inspections
        locations = []
        terminal_order = [
            k for k in expected if k not in {r["request"]["location_id"] for r in inspections}
        ]
        terminal_index = 0
        terminal_found = None
        for ordinal, stage in enumerate(staged, 1):
            entry = stage["receipt"]
            phase = "probe" if ordinal <= len(inspections) else "completion"
            assert stage["phase"] == phase
            assert stage["stage_sha256"] == digest({"phase": phase, "receipt": entry})
            req = entry["request"]
            assert set(req) == {"action_id", "episode_id", "step_id", "object_id", "location_id"}
            assert req["episode_id"] == visible["episode_id"] and req["step_id"] == step["step_id"]
            assert req["object_id"] == step["object_instance_id"]
            loc = req["location_id"]
            assert loc in support and loc not in locations
            assert terminal_found is None
            locations.append(loc)
            assert entry["ordinal"] == ordinal and type(entry["found"]) is bool
            assert entry["found"] == (loc == target)
            assert entry["receipt_sha256"] == digest(
                {"request": req, "ordinal": ordinal, "found": entry["found"]}
            )
            if phase == "completion":
                assert found is None and loc == terminal_order[terminal_index]
                terminal_index += 1
                assert req["action_id"] not in seen_ids
                seen_ids.add(req["action_id"])
            if entry["found"]:
                terminal_found = loc
                assert ordinal == len(staged)
        retrieved = terminal_found is not None
        if not retrieved:
            assert set(locations) == support
        assert execution["found_location"] == terminal_found
        assert execution["status"] == ("found" if retrieved else "support_exhausted")
        if carry:
            memory = terminal_found
        assert execution["search_memory_after_completion"] == memory
        total = len(staged)
        remaining = terminal_index
        extra = max(0, total - 1) / max(1, len(support) - 1) if retrieved else 1.0
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
            "pre_completion_search_errors": err,
            "executed_checks": total,
            "terminal_checks": remaining,
            "retrieval_failures": int(not retrieved),
            "charged_action_regret": put + extra,
            "uncharged_pre_completion_regret": put + post,
        }
        counts.update(measurements)
        rows.append({"step_id": step["step_id"], **measurements})
    metric = result["metric_pre_completion_uncharged"]
    n = counts["n"]
    assert metric["step_count"] == n
    for key, value in [
        ("put_back_error_rate", counts["put_errors"] / n),
        ("search_error_rate", counts["pre_completion_search_errors"] / n),
        ("cumulative_action_regret", counts["uncharged_pre_completion_regret"]),
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
        assert {r["visible_input_sha256"] for r in results.values()} == {digest(visible)}
        assert truth["episode_id"] == visible["episode_id"]
        scored = {}
        for arm, r in results.items():
            assert r["arm"] == arm
            expected_engine = "factorized" if arm == "factor_habit" else "joint"
            expected_policy = {
                "terminal_only": "passive",
                "current_no_carry": "current_rank",
                "joint_habit": "habit_rank",
                "factor_habit": "habit_rank",
            }.get(arm, arm)
            assert r["engine"] == expected_engine and r["policy"] == expected_policy
            expected_runtime_arm = (
                "matched_full_state_factorized" if arm == "factor_habit" else "stateful_full_joint"
            )
            assert r["runtime_audit"]["arm"] == expected_runtime_arm
            assert r["runtime_audit"]["episode_id"] == visible["episode_id"]
            assert all(
                receipt["arm"] == expected_runtime_arm
                for receipt in r["runtime_audit"]["fairness_receipts"]
            )
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
                        "executed_checks",
                        "pre_completion_search_errors",
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
                a["put_back"] for a in results["terminal_only"]["actions"]
            ]
            for key in ("final_state_sha256", "rgrc_ledger_head_sha256"):
                assert (
                    results[arm]["runtime_audit"][key]
                    == results["terminal_only"]["runtime_audit"][key]
                ), (arm, key)
        for arm in ("factor_habit", "current_rank", "current_no_carry"):
            control = (
                "joint_habit"
                if arm == "factor_habit"
                else "terminal_only"
                if arm == "current_rank"
                else "current_rank"
            )
            for left, right in zip(
                results[arm]["actions"], results[control]["actions"], strict=True
            ):

                def sequence(row):
                    return [
                        p["receipt"]["request"]["location_id"]
                        for p in row["search_execution"]["staged_receipts"]
                    ]

                paired[arm + "_vs_" + control + "_executed_sequence_disagreements"] += sequence(
                    left
                ) != sequence(right)
        for jrow, brow in zip(scored["joint_habit"], scored["current_rank"], strict=True):
            paired["joint_more_completion_inspections_steps"] += (
                jrow["executed_checks"] > brow["executed_checks"]
            )
            paired["joint_fewer_completion_inspections_steps"] += (
                jrow["executed_checks"] < brow["executed_checks"]
            )
        case_rows.append(
            {
                "index": i,
                "metrics": {
                    a: {
                        k: sum(row[k] for row in scored[a])
                        for k in (
                            "queries",
                            "pre_completion_search_errors",
                            "executed_checks",
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
                "executed_checks",
                "pre_completion_search_errors",
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
            "Every retrieval check executed against ideal D0 detector; "
            "world remains exogenous, not physical runtime or joint current-location belief."
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
