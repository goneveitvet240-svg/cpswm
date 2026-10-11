"""Standard-library independent replay of projection, prediction, learning and fees."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def close(actual, expected):
    if isinstance(expected, dict):
        assert set(actual) == set(expected)
        for key, value in expected.items():
            close(actual[key], value)
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected, strict=True):
            close(a, b)
    elif isinstance(expected, float):
        assert math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-11)
    else:
        assert actual == expected


def unit(matrix):
    total = sum(sum(row) for row in matrix)
    assert total > 0
    return [[v / total for v in row] for row in matrix]


def predict(history, previous, locations, actors, config, cue, visible):
    """Rebuild a dense contingency table independently of production helpers."""
    parents = [None, *locations]
    width, count = len(locations), len(actors)
    table = [
        [[config["alpha"] / (width * count) for _ in locations] for _ in actors] for _ in parents
    ]
    for index, record in enumerate(history):
        if record["found"] is None:
            continue
        p, loc = parents.index(record["previous"]), locations.index(record["found"])
        cue_weights = record["actor_cue"] or {a: 1 / count for a in actors}
        for ai, actor in enumerate(actors):
            table[p][ai][loc] += config["decay"] ** (len(history) - 1 - index) * cue_weights[actor]
    row = table[parents.index(previous)]
    by_location = [sum(row[ai][li] for ai in range(count)) for li in range(width)]
    actor_location = [
        [sum(table[pi][ai][li] for pi in range(len(parents))) for li in range(width)]
        for ai in range(count)
    ]
    kind = config["kind"]
    if kind == "joint":
        result = [list(r) for r in row]
    elif kind == "factor":
        result = [
            [
                by_location[li]
                * actor_location[ai][li]
                / sum(actor_location[aj][li] for aj in range(count))
                for li in range(width)
            ]
            for ai in range(count)
        ]
    elif kind == "markov":
        result = [[v / count for v in by_location] for _ in actors]
    else:
        result = [[1 / count for _ in locations] for _ in actors]
    result = unit(result)
    if cue is not None and kind in ("joint", "factor"):
        result = [
            [cue[actors[ai]] * v / sum(result[ai]) for v in result[ai]] for ai in range(count)
        ]
    if visible is not None:
        result = unit(
            [[v if locations[li] == visible else 0.0 for li, v in enumerate(row)] for row in result]
        )
    return {a: dict(zip(locations, result[ai], strict=True)) for ai, a in enumerate(actors)}


def marginal(joint, locations):
    return {loc: sum(row[loc] for row in joint.values()) for loc in locations}


def score_run(run, visible, truth):
    locations = sorted(
        set(visible["known_location_ids"])
        or {
            step[key]
            for step in visible["steps"]
            for key in (
                "source_location_id",
                "attempted_location_id",
                "observed_destination_location_id",
            )
            if step[key] is not None
        }
    )
    actors = sorted(visible["resident_actor_keys"])
    assert locations and locations == run["locations"] and actors == run["actors"]
    assert run["visible_sha256"] == digest(visible)
    config = run["config"]
    assert config["kind"] in ("recent", "markov", "joint", "factor")
    assert math.isfinite(config["alpha"]) and config["alpha"] > 0
    assert math.isfinite(config["decay"]) and 0 < config["decay"] <= 1
    assert run["view"] in ("native", "cue_only")
    assert len(run["actions"]) == len(visible["steps"]) > 0
    history, previous, rows = [], None, []
    ids = set()
    counts = Counter()
    for index, (row, step) in enumerate(zip(run["actions"], visible["steps"], strict=True)):
        loc = step["after"]["detected_location_id"] if step["after"] is not None else None
        counts["original_location_missing"] += loc is None
        counts["missing_location_with_actor_cue"] += (
            loc is None and step["actor_evidence"] is not None
        )
        cue = None
        if step["actor_evidence"] is not None:
            raw = step["actor_evidence"]["actor_posterior"]
            total = sum(raw.get(a, 0) for a in actors)
            cue = {a: raw.get(a, 0) / total for a in actors}
        public_location = loc if run["view"] == "native" else None
        projection = {
            "step_id": step["step_id"],
            "object_id": step["object_instance_id"],
            "view": run["view"],
            "visible_location": public_location,
            "actor_cue": cue,
        }
        close(row["input"], projection)
        assert row["input_sha256"] == digest(projection)
        assert row["previous"] == previous and row["history_before_sha256"] == digest(history)
        prior = predict(history, previous, locations, actors, config, cue, public_location)
        close(row["prior_joint"], prior)
        probs = marginal(prior, locations)
        close(row["prior_location"], probs)
        first = (public_location or previous) if config["kind"] == "recent" else None
        order = sorted(locations, key=lambda key: (key != first, -round(probs[key], 14), key))
        assert row["planned_order"] == order
        target = truth["truth_by_step"][step["step_id"]]["true_location"]
        expected_sequence = order[: order.index(target) + 1] if target in order else order
        assert len(row["updates"]) == len(expected_sequence)
        posterior = prior
        actor_before = {a: sum(prior[a].values()) for a in actors}
        for ordinal, (update, location) in enumerate(
            zip(row["updates"], expected_sequence, strict=True), start=1
        ):
            receipt = update["receipt"]
            request = receipt["request"]
            assert set(request) == {
                "action_id",
                "episode_id",
                "step_id",
                "object_id",
                "location_id",
            }
            assert request["action_id"] not in ids
            ids.add(request["action_id"])
            assert request["episode_id"] == visible["episode_id"]
            assert (
                request["step_id"] == step["step_id"]
                and request["object_id"] == step["object_instance_id"]
            )
            assert request["location_id"] == location and receipt["ordinal"] == ordinal
            assert type(receipt["found"]) is bool and receipt["found"] == (location == target)
            assert receipt["receipt_sha256"] == digest(
                {"request": request, "ordinal": ordinal, "found": receipt["found"]}
            )
            unscaled = {
                a: {
                    key: value if (key == location) == receipt["found"] else 0.0
                    for key, value in posterior[a].items()
                }
                for a in actors
            }
            total = sum(sum(v.values()) for v in unscaled.values())
            if total == 0:
                assert target not in locations and ordinal == len(locations)
                posterior = unscaled
            else:
                posterior = {
                    a: {key: value / total for key, value in values.items()}
                    for a, values in unscaled.items()
                }
            close(update["posterior_joint"], posterior)
        found = target if target in locations else None
        assert row["found"] == found and row["paid_checks"] == len(expected_sequence)
        assert row["status"] == ("found" if found is not None else "support_exhausted")
        history.append(
            {"step_id": step["step_id"], "previous": previous, "actor_cue": cue, "found": found}
        )
        assert row["history_after_sha256"] == digest(history)
        if run["integrated"]:
            action = run["framework_actions"][index]
            assert action["step_id"] == step["step_id"] and action["search_order"] == order
            counts["put_errors"] += (
                action["put_back"]
                != truth["truth_by_step"][step["step_id"]]["true_owner_habit_location"]
            )
        actor_after = {a: sum(posterior[a].values()) for a in actors}
        actor_tv = sum(abs(actor_before[a] - actor_after[a]) for a in actors) / 2
        counts["actor_posterior_changed_steps"] += actor_tv > 1e-10
        counts["checks"] += len(expected_sequence)
        counts["retrieval_failures"] += found is None
        counts["first_position_errors"] += order[0] != target
        counts["n"] += 1
        rows.append(
            {
                "step_id": step["step_id"],
                "checks": len(expected_sequence),
                "order": order,
                "sequence": expected_sequence,
                "actor_tv": actor_tv,
                "original_location_missing": loc is None,
                "actor_cue_present": cue is not None,
            }
        )
        previous = found
    if run["integrated"]:
        assert run["runtime_audit"]["arm"] == "stateful_full_joint"
        assert run["runtime_audit"]["episode_id"] == visible["episode_id"]
        for trace in run["framework_metric_pre_execution"]["revision_action_traces"]:
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
            assert search == run["framework_actions"][index]["search_order"]
            assert put == [run["framework_actions"][index]["put_back"]]
            counts["bound_feedback_actions"] += 1
    return dict(counts), rows


def verify(root):
    index = read(root / "index.json")
    completion = read(root / "completion.json")
    assert completion["source_unchanged"] is True
    assert completion["actual_runs"] == len(index)
    assert len({item["file"] for item in index}) == len(index)
    totals, episode_rows, actions = defaultdict(Counter), [], {}
    freeze = read(root / "freeze.json")
    assert digest(read(root / "source.json")["files"]) == freeze["source_files_sha256"]
    for item in index:
        run = read(root / item["file"])
        assert run["view"] == item["view"]
        if completion["phase"] != "dev":
            assert run["config"] == freeze["selected"][item["view"]][item["arm"]]
        counts, rows = score_run(run, read(root / item["visible"]), read(root / item["truth"]))
        key = f"{item['view']}/{item['condition']}/{item['arm']}"
        totals[key].update(counts)
        episode_rows.append({**item, "counts": counts})
        actions[item["view"], item["condition"], item["episode"], item["arm"]] = rows
    comparisons = defaultdict(Counter)
    if completion["phase"] != "dev":
        for (view, condition, episode, arm), rows in actions.items():
            if arm != "joint":
                continue
            for control in ("recent", "markov", "factor", "matched_factor"):
                other = actions[view, condition, episode, control]
                key = f"{view}/{condition}/joint_vs_{control}"
                for a, b in zip(rows, other, strict=True):
                    comparisons[key]["joint_minus_control_checks"] += a["checks"] - b["checks"]
                    comparisons[key]["sequence_disagreements"] += a["sequence"] != b["sequence"]
                    comparisons[key]["joint_better_steps"] += a["checks"] < b["checks"]
                    comparisons[key]["joint_worse_steps"] += a["checks"] > b["checks"]
    return {
        "actual_runs": len(index),
        "totals": {k: dict(v) for k, v in sorted(totals.items())},
        "comparisons": {k: dict(v) for k, v in sorted(comparisons.items())},
        "episodes": episode_rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.root)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "episodes"}, sort_keys=True))
