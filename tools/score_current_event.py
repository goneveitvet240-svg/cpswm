"""Standard-library independent scoring of paid searches and native factor weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from score_shared_location import score_run


def read(path):
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def uid(kind, payload):
    return str(uuid5(NAMESPACE_URL, f"cpswm:{kind}:{digest(payload)}"))


def close(a, b):
    assert math.isclose(a, b, abs_tol=1e-10, rel_tol=1e-8), (a, b)


def pick(dist):
    return min(dist, key=lambda key: (-dist[key], key))


def verify_run(run, visible, truth):
    locations = sorted(run["actions"][0]["search"]["prior_location"])
    actors = sorted(run["actions"][0]["search"]["prior_joint"])
    head = {
        "actions": [r["search"] for r in run["actions"]],
        "locations": locations,
        "actors": actors,
        "config": {
            "kind": "joint",
            "alpha": 0.25,
            "decay": 0.9,
            "sharing": 2.0,
            "persistence": 2.0,
        },
        "view": "native",
        "integrated": False,
        "visible_sha256": run["episode_sha256"],
    }
    counts, _ = score_run(head, visible, truth)
    counts = Counter(counts)
    assert len(run["task_readout_actions"]) == len(run["actions"])
    assert len(run["actions"]) == len(visible["steps"]) == len(run["native_evidence"])
    applied = []
    event_ids = []
    for i, (row, step, native) in enumerate(
        zip(run["actions"], visible["steps"], run["native_evidence"], strict=True)
    ):
        assert row["step_id"] == step["step_id"] and row["native_step_index"] == i + 1
        assert run["task_readout_actions"][i] == {
            "prediction_index": i,
            "put_back": row["put_back"],
            "search_order": row["search"]["planned_order"],
        }
        o = native["observation"]
        event_ids.append(row["event_id"])
        assert row["event_id"] == o["source_update_id"]
        missing = (
            step["before"] is None
            or step["after"] is None
            or step["observation_opportunity"] is None
        )
        if missing:
            assert row["event_id"] == uid(
                "current-event-prediction",
                [visible["episode_id"], step["step_id"], step["object_instance_id"]],
            )
        source_id = row["location_source_id"]
        expected_new = run["consume_new"] and missing and row["search"]["found"] is not None
        assert (source_id is not None) == expected_new
        if expected_new:
            source = run["location_sources"][source_id]
            p = source["payload"]
            assert source["sha256"] == digest(p) and source_id == uid("paid-current-location", p)
            assert p["episode_id"] == visible["episode_id"] and p["step_id"] == step["step_id"]
            assert p["object_id"] == step["object_instance_id"] and p["event_id"] == row["event_id"]
            assert p["paid_updates"] == row["search"]["updates"]
            assert source["updated"] == o and source["original"]["observed_location_id"] is None
            assert o["observed_location_id"] == row["search"]["found"]
            assert o["position_source_id"] == source_id and not o["prediction_only"]
            assert p["location_likelihood"] == o["location_likelihood"]
            # The search prior uses the same conditional table at missing steps;
            # actor cue replaces only its marginal, so conditional is recoverable.
            likelihood = dict(o["location_likelihood"])
            prior = row["search"]["prior_joint"]
            loc = row["search"]["found"]
            for actor in actors:
                mass = sum(prior[actor].values())
                if mass > 0:
                    close(likelihood[actor], prior[actor][loc] / mass)
            applied.append(source_id)
            counts["native_location_updates"] += 1
            counts["new_evidence_multiple_actor_particles"] += (
                len(set(native["placement_actors"])) > 1
            )
            counts["new_evidence_actor_likelihood_differs"] += (
                max(likelihood.values()) - min(likelihood.values()) > 1e-10
            )
        elif missing:
            assert o["observed_location_id"] is None and o["prediction_only"]
        else:
            assert o["observed_location_id"] == step["after"]["detected_location_id"]
        assert row["event_observed_location"] == o["observed_location_id"]
        assert row["put_back"] == pick(row["after"])
        target = truth["truth_by_step"][step["step_id"]]["true_owner_habit_location"]
        counts["put_errors"] += row["put_back"] != target
        counts["within_step_action_changes"] += pick(row["before"]) != row["put_back"]
        counts["within_step_actor_changes"] += any(
            abs(row["actor_before"][a] - row["actor_after"][a]) > 1e-10 for a in actors
        )
        counts["native_score_evaluations"] += len(native["receipts"]) * (1 + int(expected_new))
        f = native["fairness"]
        assert f["step_index"] == i + 1 and f["particle_budget"] == 24
        assert (
            f["target_score_evaluations"] == 24
            and len(native["weights"]) == len(native["receipts"]) == 24
        )
        values = []
        for receipt in native["receipts"]:
            likelihood = receipt["observation_log_likelihood"]
            if expected_new:
                assert (
                    receipt["evidence_semantics"]
                    == "posterior_projection_with_independent_likelihood"
                )
                assert receipt["independent_observation_source_id"] == source_id
                assert receipt["source_posterior_snapshot_id"] == row["event_id"] != source_id
                roles = receipt["proposal"]["proposed_state"]["ordered_actor_roles"]
                actor = next(
                    (
                        r["actor_key"]
                        for r in roles
                        if r["role"] in ("placement_actor", "handoff_receiver", "responsible_actor")
                    ),
                    None,
                )
                close(likelihood, math.log(dict(o["location_likelihood"])[actor]))
            else:
                assert (
                    likelihood == 0
                    and receipt["evidence_semantics"] == "posterior_projection_not_likelihood"
                )
            values.append(
                receipt["prior_log_weight"]
                + receipt["transition_log_probability"]
                + likelihood
                + receipt["posterior_projection_log_factor"]
                + receipt["integration_log_weight"]
                + sum(c["log_potential"] for c in receipt["constraints"])
                - receipt["proposal"]["proposal_log_probability"]
            )
        mx = max(values)
        weights = [math.exp(v - mx) for v in values]
        total = sum(weights)
        close(sum(native["weights"]) + native["unresolved"], 1.0)
        for w, actual in zip(weights, native["weights"], strict=True):
            close(w / total * (1 - native["unresolved"]), actual)
        distribution = dict.fromkeys(actors, 0.0)
        for a, w in zip(native["placement_actors"], native["weights"], strict=True):
            distribution[a] += w
        distribution["unknown_actor"] += native["unresolved"]
        for a in actors:
            close(distribution[a], row["actor_after"][a])
    assert len(event_ids) == len(set(event_ids))
    assert set(applied) == set(run["location_sources"])
    assert counts["put_errors"] == run["put_errors"]
    assert len(run["native_audit"]["fairness_receipts"]) == len(event_ids)
    previous = None
    for r in run["location_revisions"]:
        assert r["operation"] == "apply" and r["previous_receipt"] == previous
        assert r["sha256"] == digest({k: v for k, v in r.items() if k != "sha256"})
        previous = r["sha256"]
    assert len(applied) == len(run["location_revisions"])
    return dict(counts)


def verify(root):
    totals = defaultdict(Counter)
    groups = defaultdict(dict)
    cache = {}
    for item in read(root / "index.json"):
        run = read(root / item["file"])
        if item["file"] not in cache:
            cache[item["file"]] = verify_run(
                run, read(root / item["visible"]), read(root / item["truth"])
            )
        totals[item["condition"] + "/" + item["label"]].update(cache[item["file"]])
        groups[item["condition"], item["episode"]][item["label"]] = run
    comparisons = defaultdict(Counter)
    for (condition, _), group in groups.items():
        values = list(group.values())
        reference = values[0]
        for other in values[1:]:
            assert [r["search"] for r in reference["actions"]] == [
                r["search"] for r in other["actions"]
            ]
        if "joint" not in group:
            continue
        joint = group["joint"]
        for label, control in group.items():
            if label == "joint":
                continue
            c = comparisons[condition + "/joint_vs_" + label]
            c["put_error_difference"] += joint["put_errors"] - control["put_errors"]
            for a, b in zip(joint["actions"], control["actions"], strict=True):
                c["action_disagreements"] += a["put_back"] != b["put_back"]
                c["pre_search_disagreements"] += pick(a["before"]) != pick(b["before"])
            if label == "matched_factor":
                for a, b in zip(joint["native_evidence"], control["native_evidence"], strict=True):
                    for key in [
                        "particle_budget",
                        "proposal_draws",
                        "target_score_evaluations",
                        "proposal_model_hash",
                        "common_random_number_sha256",
                    ]:
                        assert a["fairness"][key] == b["fairness"][key]
        for arm, baseline in [
            ("joint", "joint_no_new"),
            ("matched_factor", "matched_factor_no_new"),
        ]:
            c = comparisons[condition + "/" + arm + "_new_evidence_effect"]
            c["put_error_difference"] += group[arm]["put_errors"] - group[baseline]["put_errors"]
            for a, b in zip(group[arm]["actions"], group[baseline]["actions"], strict=True):
                c["action_disagreements"] += a["put_back"] != b["put_back"]
                c["pre_search_disagreements"] += pick(a["before"]) != pick(b["before"])
    return {
        "actual_runs": len(cache),
        "logical_rows": sum(len(g) for g in groups.values()),
        "totals": {k: dict(v) for k, v in sorted(totals.items())},
        "comparisons": {k: dict(v) for k, v in sorted(comparisons.items())},
        "all_groups_identical_paid_search": True,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    result = verify(a.root)
    a.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
