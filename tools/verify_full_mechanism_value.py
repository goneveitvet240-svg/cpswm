"""Source-bound D0 diagnostic; no production authorization or scientific gate change.

Runs the existing complete Route-C runtime against its full-state factorization,
a shared-spine latest-owner readout and the repository's matched AMG adapter.
Truth scoring uses the existing evaluator after actions are recorded. The existing
D0 CIAV environment also opens truth inside its post-selection observation realizer;
this is simulated actor evidence, never empirical sensor calibration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionBenchmarkV02,
    ProjectTwoActionMethod,
    _FullProjectTwoMethod,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_factorial_benchmark import _CIAVState
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
    _fairness_comparison_payload,
    _metric_summary_from_rows,
    _runtime_audit_payload,
    build_stateful_full_joint_state,
)
from cpswm.system.prototype_spine import ActionReadout, ActionReadoutConfig
from cpswm.system.reproducibility import content_sha256
from cpswm.system.runtime_readout import current_action_readout

ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = {
    "complete32": dict(
        scenario_duration_days=32,
        observation_coverage=1.0,
        guest_window=(7, 14),
        abrupt_day=17,
        recurrence_day=26,
        unknown_event_days=(1,),
    ),
    "sparse32": dict(
        scenario_duration_days=32,
        observation_coverage=0.35,
        guest_window=(7, 14),
        abrupt_day=17,
        recurrence_day=26,
        unknown_event_days=(1,),
    ),
    "long64": dict(
        scenario_duration_days=64,
        observation_coverage=0.7,
        guest_window=(14, 28),
        abrupt_day=34,
        recurrence_day=52,
        unknown_event_days=(1, 20, 40),
    ),
}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def pick(values):
    return max(sorted(values, key=str), key=values.__getitem__)


def dominance_certificate(config):
    """Sufficient condition only; no claim when no eligible fast event exists."""
    weights = config.component_weights
    effective_fast = weights["fast_action"] * config.unconfirmed_fast_discount
    other = sum(v for k, v in weights.items() if k != "fast_action")
    return {
        "config": {**asdict(config), "readout": config.readout.value},
        "fast_minimum_weight": effective_fast,
        "other_maximum_weight": other,
        "strict_argmax_dominance": (
            effective_fast > other and config.pending_correction_discount == 1.0
        ),
        "conditions": "nonempty eligible one-hot fast component; normalized nonnegative components",
        "excluded": "no eligible fast event; changed fast mass after feedback; changed discounts",
    }


class RecordedState:
    """Observe actions without substituting the method or feeding evaluator truth."""

    def __init__(self, state):
        self.state = state
        self.rows = []
        self.step = None

    def observe(self, step):
        self.step = step
        self.state.observe(step)

    def predict(self):
        result = self.state.predict()
        row = {
            "step_id": str(self.step.step_id),
            "put_back": str(result.put_back),
            "search_order": list(map(str, result.search_order)),
            "unknown_probability": result.unknown_probability,
        }
        core = getattr(self.state, "spine", None)
        if core is not None:
            configured = core.action_location_distribution(
                core.current_snapshot, readout=current_action_readout()
            )
            latest = core.action_location_distribution(
                core.current_snapshot,
                readout=ActionReadoutConfig(readout=ActionReadout.LATEST_OWNER_EVENT),
            )
            row.update(
                committed=len(core._committed_events),
                observed=len(core._observed_events),
                regime=core.active_regime,
                eligible_fast=sum(e.owner_mass >= 0.5 for e in core._fast_action_events.values()),
                current_readout_choice=str(pick(configured)),
                latest_choice=str(pick(latest)),
                current_readout_distribution={str(k): v for k, v in configured.items()},
            )
        self.rows.append(row)
        return result

    def feedback(self, step):
        self.state.feedback(step)
        core = getattr(self.state, "spine", None)
        if core is not None:
            self.rows[-1]["committed_after_feedback"] = len(core._committed_events)
            self.rows[-1]["observed_after_feedback"] = len(core._observed_events)

    def __getattr__(self, name):
        return getattr(self.state, name)


def make_state(dataset, episode, method, parameter=None):
    if method in tuple(a.value for a in FullJointArm):
        return build_stateful_full_joint_state(
            repository_root=ROOT, dataset=dataset, episode=episode, arm=FullJointArm(method)
        )
    if method == "shared_spine_latest":
        base = _FullProjectTwoMethod(
            episode,
            owner_threshold=0.4,
            action_readout=ActionReadoutConfig(
                readout=ActionReadout.LATEST_OWNER_EVENT, fast_owner_mass_floor=parameter
            ),
        )
        return _CIAVState(base, dataset, episode, enabled=True, cost_multiplier=1.0)
    return ProjectTwoActionBenchmarkV02()._method(
        episode, ProjectTwoActionMethod.AMG_MATCHED, {"parameter": parameter}
    )


def evaluate(dataset, episode, method, parameter=None):
    state = RecordedState(make_state(dataset, episode, method, parameter))
    started = perf_counter()
    metric = ProjectTwoActionBenchmarkV02().evaluate_custom_state(dataset, episode, state)
    result = {
        "method": method,
        "parameter": parameter,
        "metric": metric.model_dump(mode="json"),
        "visible_input_sha256": content_sha256(episode),
        "actions": state.rows,
        "wall_seconds": perf_counter() - started,
    }
    if method in tuple(a.value for a in FullJointArm):
        runtime = state.runtime
        result["runtime_audit"] = _runtime_audit_payload(runtime, episode_id=episode.episode_id)
        result["ledger_operations"] = dict(
            Counter(r.operation for r in runtime.rgrc_ledger.records)
        )
        result["operator_changes"] = dict(
            Counter(r.operator.value for r in runtime.operator_flow_receipts if r.changed_state)
        )
        result["particle_count"] = len(runtime.particles)
    return result


def run(output, conditions, test_seeds):
    output.mkdir(parents=True, exist_ok=False)
    paths = [
        *sorted((ROOT / "src").rglob("*.py")),
        Path(__file__),
        *sorted((ROOT / "configs/project_two_experiments").glob("*.json")),
        ROOT
        / "artifacts/project_two_v04_development/structure_two_neural_amortized_model_v0_1.json",
    ]
    sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    save(output / "source.json", {"files": sources, "python": sys.version})
    save(output / "dominance.json", dominance_certificate(current_action_readout()))
    summaries = {}
    for condition in conditions:
        settings = CONDITIONS[condition]
        dataset = D0SyntheticOracleReplayAdapter(
            validation_seeds=(7, 8, 9),
            test_seeds=tuple(test_seeds),
            max_steps_per_episode=settings["scenario_duration_days"],
            dataset_version="mechanism-value-development-20261011:" + condition,
            sealed_secret="mechanism-value-development-20261011:" + condition,
            **settings,
        ).build()
        selected = {}
        tuning = {}
        for method, grid in (
            ("matched_amg", (0.2, 0.33, 0.5)),
            ("shared_spine_latest", (0.3, 0.5, 0.7)),
        ):
            trials = []
            for parameter in grid:
                results = [
                    evaluate(dataset, e, method, parameter)
                    for e in dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
                ]
                save(output / condition / f"dev-{method}-{parameter}.json", results)
                metrics = _metric_summary_from_rows([r["metric"] for r in results])
                trials.append({"parameter": parameter, **metrics})
            selected[method] = min(
                trials, key=lambda r: (r["cumulative_action_regret_per_step"], r["parameter"])
            )["parameter"]
            tuning[method] = trials
        save(output / condition / "selection.json", {"selected": selected, "trials": tuning})
        methods = [a.value for a in FullJointArm] + list(selected)
        aggregate = {m: [] for m in methods}
        comparisons = []
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        for index, episode in enumerate(episodes):
            results = {}
            save(output / condition / f"visible-{index}.json", episode.model_dump(mode="json"))
            for method in methods:
                result = evaluate(dataset, episode, method, selected.get(method))
                save(output / condition / f"test-{index}-{method}.json", result)
                results[method] = result
                aggregate[method].append(result["metric"])
            joint, factor = (results[a.value] for a in FullJointArm)
            # Evaluation-only copy: written after every arm committed its actions.
            save(
                output / condition / f"evaluator-truth-{index}.json",
                dataset.truth_for(episode.episode_id).model_dump(mode="json"),
            )
            jf, ff = (r["runtime_audit"]["fairness_receipts"] for r in (joint, factor))
            fairness = len(jf) == len(ff) and all(
                _fairness_comparison_payload(a) == _fairness_comparison_payload(b)
                for a, b in zip(jf, ff, strict=True)
            )
            if not fairness:
                raise AssertionError("full-state paired-arm fairness mismatch")
            comparisons.append(
                {
                    "episode_id": str(episode.episode_id),
                    "matched_fairness": fairness,
                    "put_back_disagreements": sum(
                        a["put_back"] != b["put_back"]
                        for a, b in zip(joint["actions"], factor["actions"], strict=True)
                    ),
                    "search_disagreements": sum(
                        a["search_order"] != b["search_order"]
                        for a, b in zip(joint["actions"], factor["actions"], strict=True)
                    ),
                }
            )
            print(condition, index + 1, "/", len(episodes), comparisons[-1], flush=True)
        summaries[condition] = {
            "settings": settings,
            "selection": selected,
            "tuning": tuning,
            "metrics": {m: _metric_summary_from_rows(rows) for m, rows in aggregate.items()},
            "paired": comparisons,
        }
        save(output / "summary.json", summaries)
    assert all(hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == h for n, h in sources.items())
    save(
        output / "completion.json",
        {
            "source_unchanged": True,
            "conditions": conditions,
            "test_seeds": test_seeds,
            "claim": "D0_DEVELOPMENT_DIAGNOSTIC_NOT_PAPER_SUPERIORITY",
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--conditions", nargs="+", choices=list(CONDITIONS), default=list(CONDITIONS)
    )
    parser.add_argument("--test-seeds", nargs="+", type=int, default=list(range(31, 41)))
    args = parser.parse_args()
    run(args.output, args.conditions, args.test_seeds)
