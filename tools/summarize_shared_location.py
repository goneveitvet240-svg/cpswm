"""Descriptive decomposition; does not select models or change heldout actions."""

from __future__ import annotations

from collections import Counter, defaultdict

from score_shared_location import read


def summarize(root):
    scores = read(root / "test-score.json")
    totals = defaultdict(Counter)
    for key, value in scores["totals"].items():
        view, _, arm = key.split("/")
        totals[view + "/" + arm].update(value)
    diagnostics, examples = Counter(), []
    paths = defaultdict(set)
    for item in read(root / "test/index.json"):
        if item["arm"] != "joint":
            continue
        folder = root / "test"
        joint = read(folder / item["file"])
        markov = read(folder / item["file"].replace("-joint.json", "-markov.json"))
        factor = read(folder / item["file"].replace("-joint.json", "-factor.json"))
        history = []
        truth_path, names = [], {}
        for index, (a, b, c) in enumerate(
            zip(joint["actions"], markov["actions"], factor["actions"], strict=True)
        ):
            view = item["view"]
            prob_tv = (
                sum(
                    abs(a["prior_location"][loc] - b["prior_location"][loc])
                    for loc in joint["locations"]
                )
                / 2
            )
            diagnostics[view + "/joint_markov_probability_different"] += prob_tv > 1e-10
            diagnostics[view + "/joint_markov_order_different"] += (
                a["planned_order"] != b["planned_order"]
            )
            group = (
                "first"
                if a["previous"] is None
                else "persist"
                if a["previous"] == a["found"]
                else "move"
            )
            cue = "cue" if a["input"]["actor_cue"] is not None else "no_cue"
            saved = a["paid_checks"] - c["paid_checks"]
            diagnostics[view + "/factor_saved/" + group] += saved
            diagnostics[view + "/factor_saved/" + cue] += saved
            if a["found"] not in names:
                names[a["found"]] = len(names)
            truth_path.append(names[a["found"]])
            if saved > 0 and cue == "cue" and len(examples) < 3:
                actor = max(a["input"]["actor_cue"], key=a["input"]["actor_cue"].get)
                context, globally = 0.0, 0.0
                for tick, past in enumerate(history):
                    weights = past["input"]["actor_cue"] or dict.fromkeys(
                        joint["actors"], 1 / len(joint["actors"])
                    )
                    value = joint["config"]["decay"] ** (index - tick - 1) * weights[actor]
                    globally += value
                    if past["previous"] == a["previous"]:
                        context += value
                examples.append(
                    {
                        "file": item["file"],
                        "step_index": index,
                        "step_id": a["input"]["step_id"],
                        "actor": actor,
                        "previous_context_actor_effective_count": context,
                        "all_context_actor_effective_count": globally,
                        "joint_checks": a["paid_checks"],
                        "factor_checks": c["paid_checks"],
                        "joint_prior": a["prior_location"],
                        "factor_prior": c["prior_location"],
                    }
                )
            history.append(a)
        paths[item["condition"]].add(tuple(truth_path))
    native_cases = {}
    for item in read(root / "integrate/index.json"):
        run = read(root / "integrate" / item["file"])
        for audit in run["native_time_audits"]:
            key = (item["condition"], item["episode"], audit["step_id"])
            projected = {
                k: v
                for k, v in audit.items()
                if k not in {"native_source_update_id", "current_transition_revision_id"}
            }
            if key in native_cases:
                assert native_cases[key] == projected
            native_cases[key] = projected
    native_counts = Counter(row["status"] for row in native_cases.values())
    return {
        "totals": {k: dict(v) for k, v in sorted(totals.items())},
        "diagnostics": dict(sorted(diagnostics.items())),
        "native_unique_time_status_counts": dict(native_counts),
        "native_unique_time_audits": list(native_cases.values()),
        "posthoc_examples": examples,
        "unique_location_paths_up_to_renaming": {k: len(v) for k, v in sorted(paths.items())},
        "scope": (
            "descriptive decomposition; same scheduled D0 regimes, "
            "not independent behavioral worlds"
        ),
    }
