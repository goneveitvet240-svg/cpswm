"""Independent per-arm tuning with an equal search budget (阶段 7).

    PYTHONPATH=src python apps/evaluation_runner/tune_project_one.py \
        --output artifacts/project_one/tuning

Three rules, all of them the point of the exercise:

* **Every arm searches its own grid.**  Comparing a tuned method against a
  baseline running the method's thresholds is not a comparison.
* **Every arm gets the same budget.**  Each grid has exactly ``--budget``
  points, so no arm wins by being allowed to look harder.
* **Selection happens on validation only; TEST is run once.**  The split is by
  *scenario*, not by event, because scenarios are the entities here — splitting
  events would leak a regime's own history into its test half.

The selection rule is stated in the output and settable on the command line
rather than hidden in a weighted score.  It has four terms, because a rule with
only change-confirmation in it silently declares that the short-disturbance
capability does not matter:

.. code-block:: text

    utility =  w_confirm  * habit-change confirmation rate
             + w_anomaly  * anomaly detection rate
             - w_switch   * false switch rate
             - w_alarm    * false candidate rate

The full **three-dimensional** frontier over
``(false switch rate down, confirmation up, anomaly detection up)`` is saved
alongside, so a different weighting can be applied afterwards without re-running
the search.  v0.2 selected on confirmation alone and reported a two-dimensional
frontier, which is why every arm's disturbance behaviour was invisible to it.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from cpswm.system.evaluation_operations.project_one_matched_baselines import (
    BOCPDMSConfig,
    BOCPDMSMethod,
    CUSUMConfig,
    CUSUMMethod,
    EWMAConfig,
    EWMAMethod,
    OrdinaryBOCPDMethod,
    RLSFixedThresholdConfig,
    RLSFixedThresholdMethod,
)
from cpswm.system.evaluation_operations.project_one_methods import (
    CategoricalBOCPDMethod,
    ContextFrequencyMethod,
    CoreHabitChainMethod,
    PersistenceMethod,
    ProjectOneMethod,
)
from cpswm.system.evaluation_operations.project_one_protocol import (
    DEFAULT_RESIDUAL_CALIBRATION_NAME,
    CategoricalBOCPDConfig,
    ContextFrequencyConfig,
    DecisionChainAblation,
    PersistenceConfig,
    ProjectOneProtocolConfig,
    ResidualCalibration,
    SignalAblation,
)
from cpswm.system.evaluation_operations.project_one_runner import ProjectOneRunner
from cpswm.system.evaluation_operations.project_one_runtime_parameters import (
    build_project_one_runtime_parameter_receipt,
)
from cpswm.system.evaluation_operations.project_one_scenarios import (
    LOCATIONS,
    build_all_scenarios,
)

OWNER = "owner"
HOUSEHOLD = "household-1"
OBJECT = "cup-17"

#: Split by scenario, not by event.  The five validation scenarios cover both
#: false-alarm and true-change families so that selection is not made on one
#: kind of stream alone.
VALIDATION = (
    "stable_habit",
    "short_disturbance",
    "permanent_change",
    "context_change",
    "gradual_drift",
)
TEST = (
    "periodic_habit",
    "recurring_regime",
    "missing_observations",
    "biased_observation",
    "abrupt_change",
)

Builder = Callable[[], ProjectOneMethod]


def _configured(
    method_type: Callable[[Sequence[str], object], ProjectOneMethod], config: object
) -> Builder:
    return lambda: method_type(LOCATIONS, config)


def _chain_grid(
    name: str,
    ablation: SignalAblation,
    calibration: ResidualCalibration,
    budget: int,
    decision_chain_ablation: DecisionChainAblation = DecisionChainAblation.FULL,
) -> list[tuple[dict[str, object], Builder]]:
    base = replace(
        ProjectOneProtocolConfig(),
        ablation=ablation,
        residual_calibration=calibration,
        decision_chain_ablation=decision_chain_ablation,
    )
    points: list[tuple[dict[str, object], Builder]] = []
    for threshold in (0.4, 0.5, 0.6):
        for window in (2, 3):
            for forgetting in (1.0, 0.99):
                config = replace(
                    base,
                    habit_change_probability_threshold=threshold,
                    confirmation_window=window,
                    forgetting_factor=forgetting,
                )
                points.append(
                    (
                        {
                            "habit_change_probability_threshold": threshold,
                            "confirmation_window": window,
                            "forgetting_factor": forgetting,
                        },
                        lambda config=config, name=name: CoreHabitChainMethod(
                            name=name,
                            locations=LOCATIONS,
                            owner_id=OWNER,
                            household_id=HOUSEHOLD,
                            object_id=OBJECT,
                            config=config,
                        ),
                    )
                )
    return points[:budget]


def _bocpd_grid(budget: int) -> list[tuple[dict[str, object], Builder]]:
    points: list[tuple[dict[str, object], Builder]] = []
    for run_length in (20.0, 50.0, 100.0):
        for threshold in (0.05, 0.1, 0.2, 0.4):
            config = CategoricalBOCPDConfig(
                expected_run_length=run_length, change_threshold=threshold
            )
            points.append(
                (
                    {"expected_run_length": run_length, "change_threshold": threshold},
                    lambda config=config: CategoricalBOCPDMethod(LOCATIONS, config),
                )
            )
    return points[:budget]


def _ordinary_bocpd_grid(budget: int) -> list[tuple[dict[str, object], Builder]]:
    points: list[tuple[dict[str, object], Builder]] = []
    for run_length in (20.0, 50.0, 100.0):
        for threshold in (0.05, 0.1, 0.2, 0.4):
            config = CategoricalBOCPDConfig(
                expected_run_length=run_length,
                change_threshold=threshold,
                context_conditioned=False,
            )
            points.append(
                (
                    {"expected_run_length": run_length, "change_threshold": threshold},
                    lambda config=config: OrdinaryBOCPDMethod(LOCATIONS, config),
                )
            )
    return points[:budget]


def _ewma_grid(budget: int) -> list[tuple[dict[str, object], Builder]]:
    return [
        (
            {"smoothing": smoothing, "threshold": threshold},
            _configured(EWMAMethod, EWMAConfig(smoothing=smoothing, threshold=threshold)),
        )
        for smoothing in (0.1, 0.3, 0.5)
        for threshold in (0.2, 0.4, 0.6, 0.8)
    ][:budget]


def _cusum_grid(budget: int) -> list[tuple[dict[str, object], Builder]]:
    return [
        (
            {"reference": reference, "threshold": threshold},
            _configured(CUSUMMethod, CUSUMConfig(reference=reference, threshold=threshold)),
        )
        for reference in (0.1, 0.25, 0.4)
        for threshold in (0.5, 1.0, 1.5, 2.0)
    ][:budget]


def _rls_fixed_grid(budget: int) -> list[tuple[dict[str, object], Builder]]:
    return [
        (
            {"forgetting_factor": forgetting, "threshold": threshold},
            _configured(
                RLSFixedThresholdMethod,
                RLSFixedThresholdConfig(forgetting_factor=forgetting, threshold=threshold),
            ),
        )
        for forgetting in (0.95, 0.99, 1.0)
        for threshold in (0.2, 0.4, 0.6, 0.8)
    ][:budget]


def _bocpdms_grid(budget: int) -> list[tuple[dict[str, object], Builder]]:
    return [
        (
            {
                "expected_run_length": run_length,
                "model_switch_probability": switch,
                "change_threshold": threshold,
            },
            _configured(
                BOCPDMSMethod,
                BOCPDMSConfig(
                    expected_run_length=run_length,
                    model_switch_probability=switch,
                    change_threshold=threshold,
                ),
            ),
        )
        for run_length in (20.0, 50.0, 100.0)
        for switch in (0.01, 0.1)
        for threshold in (0.1, 0.3)
    ][:budget]


def _frequency_grid(budget: int) -> list[tuple[dict[str, object], Builder]]:
    points: list[tuple[dict[str, object], Builder]] = []
    for alpha in (0.5, 1.0, 2.0):
        for threshold in (0.3, 0.5, 0.7, 0.9):
            config = ContextFrequencyConfig(alpha=alpha, change_threshold=threshold)
            points.append(
                (
                    {"alpha": alpha, "change_threshold": threshold},
                    lambda config=config: ContextFrequencyMethod(LOCATIONS, config),
                )
            )
    return points[:budget]


def _persistence_grid(budget: int) -> list[tuple[dict[str, object], Builder]]:
    values = [0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]
    return [
        (
            {"confidence": value},
            lambda value=value: PersistenceMethod(LOCATIONS, PersistenceConfig(confidence=value)),
        )
        for value in values
    ][:budget]


def _score(builder: Builder, scenarios: Sequence[str]) -> dict[str, float]:
    """Average the metric table over one split."""

    runner = ProjectOneRunner()
    rows = []
    for stream, truth in build_all_scenarios(list(scenarios)):
        result = runner.run_arm(builder(), stream, truth)
        if result.metrics is None:
            continue
        rows.append(result.metrics)
    if not rows:
        return {}
    count = len(rows)
    delays = [row.mean_detection_delay for row in rows if row.mean_detection_delay is not None]
    return {
        "false_candidate_rate": sum(r.expected_false_candidate_rate for r in rows) / count,
        "false_switch_rate": sum(r.false_switch_rate for r in rows) / count,
        "anomaly_detection_rate": sum(r.anomaly_detection_rate for r in rows) / count,
        "confirmation_rate": sum(r.habit_change_confirmation_rate for r in rows) / count,
        "mean_detection_delay": (sum(delays) / len(delays)) if delays else float("nan"),
        "false_regime_count": float(sum(r.false_regime_count for r in rows)),
        "paired_margin": sum(r.paired_margin for r in rows) / count,
        "log_loss": sum(r.log_loss for r in rows) / count,
    }


#: (metric name, +1 if larger is better) for the frontier's axes.
_FRONTIER_AXES = (
    ("false_switch_rate", -1.0),
    ("confirmation_rate", +1.0),
    ("anomaly_detection_rate", +1.0),
)


def _objective(metrics: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """The stated utility.  Every term is visible; none is hidden in a default."""

    return (
        weights["confirm"] * float(metrics["confirmation_rate"])
        + weights["anomaly"] * float(metrics["anomaly_detection_rate"])
        - weights["switch"] * float(metrics["false_switch_rate"])
        - weights["alarm"] * float(metrics["false_candidate_rate"])
    )


def _pareto(trials: list[dict[str, object]]) -> list[dict[str, object]]:
    """Non-dominated points over the three frontier axes.

    Three axes, not two: a point that confirms fewer real changes but catches
    the transient disturbances is not dominated, and dropping that axis is how
    an entire capability disappears from the search.
    """

    def coordinates(trial: dict[str, object]) -> tuple[float, ...]:
        metrics = trial["validation"]  # type: ignore[index]
        return tuple(sign * float(metrics[name]) for name, sign in _FRONTIER_AXES)  # type: ignore[index]

    frontier: list[dict[str, object]] = []
    for candidate in trials:
        here = coordinates(candidate)
        dominated = any(
            all(theirs >= mine for theirs, mine in zip(coordinates(other), here, strict=True))
            and any(theirs > mine for theirs, mine in zip(coordinates(other), here, strict=True))
            for other in trials
        )
        if not dominated:
            frontier.append(candidate)
    return frontier


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/project_one/tuning"))
    parser.add_argument("--w-confirm", type=float, default=1.0, help="weight on confirmation rate")
    parser.add_argument(
        "--w-anomaly",
        type=float,
        default=1.0,
        help="weight on anomaly detection rate (the disturbance capability)",
    )
    parser.add_argument("--w-switch", type=float, default=1.0, help="penalty on false switches")
    parser.add_argument("--w-alarm", type=float, default=1.0, help="penalty on false candidates")
    parser.add_argument("--budget", type=int, default=12, help="grid points per arm")
    parser.add_argument(
        "--calibration",
        choices=[item.value for item in ResidualCalibration],
        default=DEFAULT_RESIDUAL_CALIBRATION_NAME,
    )
    arguments = parser.parse_args()

    calibration = ResidualCalibration(arguments.calibration)
    budget: int = arguments.budget
    weights = {
        "confirm": float(arguments.w_confirm),
        "anomaly": float(arguments.w_anomaly),
        "switch": float(arguments.w_switch),
        "alarm": float(arguments.w_alarm),
    }

    grids: dict[str, list[tuple[dict[str, object], Builder]]] = {
        "full": _chain_grid("full", SignalAblation.FULL, calibration, budget),
        "no_rls": _chain_grid("no_rls", SignalAblation.NO_RLS, calibration, budget),
        "shuffled_rls": _chain_grid(
            "shuffled_rls", SignalAblation.SHUFFLED_RLS, calibration, budget
        ),
        "rls_only": _chain_grid("rls_only", SignalAblation.RLS_ONLY, calibration, budget),
        "no_cf_bocpd": _chain_grid(
            "no_cf_bocpd",
            SignalAblation.FULL,
            calibration,
            budget,
            DecisionChainAblation.NO_CF_BOCPD,
        ),
        "no_ccrr": _chain_grid(
            "no_ccrr",
            SignalAblation.FULL,
            calibration,
            budget,
            DecisionChainAblation.NO_CCRR,
        ),
        "no_regime_reactivation": _chain_grid(
            "no_regime_reactivation",
            SignalAblation.FULL,
            calibration,
            budget,
            DecisionChainAblation.NO_REGIME_REACTIVATION,
        ),
        "categorical_bocpd": _bocpd_grid(budget),
        "ewma": _ewma_grid(budget),
        "cusum": _cusum_grid(budget),
        "rls_fixed_threshold": _rls_fixed_grid(budget),
        "ordinary_bocpd": _ordinary_bocpd_grid(budget),
        "bocpdms": _bocpdms_grid(budget),
        "context_frequency": _frequency_grid(budget),
        "persistence": _persistence_grid(budget),
    }

    report: dict[str, object] = {
        "residual_calibration": calibration.value,
        "budget_per_arm": budget,
        "validation_scenarios": list(VALIDATION),
        "test_scenarios": list(TEST),
        "selection_rule": (
            "maximize w_confirm*confirmation + w_anomaly*anomaly_detection "
            "- w_switch*false_switch - w_alarm*false_candidate; "
            "tie-break on lower mean detection delay"
        ),
        "selection_weights": weights,
        "frontier_axes": [name for name, _ in _FRONTIER_AXES],
        "arms": {},
    }

    for arm, grid in grids.items():
        if len({len(grid)} | {budget}) != 1:
            raise RuntimeError(f"{arm} received {len(grid)} points, not the shared budget {budget}")
        trials: list[dict[str, object]] = []
        for params, builder in grid:
            runtime_receipt = build_project_one_runtime_parameter_receipt(builder(), params)
            validation = _score(builder, VALIDATION)
            trials.append(
                {
                    "params": params,
                    "runtime_parameter_receipt": {
                        "method": runtime_receipt.method,
                        "method_config_hash": runtime_receipt.method_config_hash,
                        "bindings": [
                            {
                                "parameter": item.parameter,
                                "target_path": item.target_path,
                                "configured_value": item.configured_value,
                                "runtime_value": item.runtime_value,
                                "runtime_binding_sha256": item.runtime_binding_sha256,
                            }
                            for item in runtime_receipt.bindings
                        ],
                        "receipt_sha256": runtime_receipt.receipt_sha256,
                    },
                    "validation": validation,
                }
            )

        def rank(trial: dict[str, object]) -> tuple[float, float]:
            metrics = trial["validation"]  # type: ignore[index]
            delay = float(metrics["mean_detection_delay"])  # type: ignore[index]
            return (
                -_objective(metrics, weights),  # type: ignore[arg-type]
                delay if delay == delay else 1e9,
            )

        selected = min(trials, key=rank)
        selected_builder = next(builder for params, builder in grid if params == selected["params"])
        test_metrics = _score(selected_builder, TEST)
        report["arms"][arm] = {  # type: ignore[index]
            "selected_params": selected["params"],
            "selected_utility": _objective(selected["validation"], weights),  # type: ignore[arg-type]
            "validation": selected["validation"],
            "test": test_metrics,
            "test_utility": _objective(test_metrics, weights) if test_metrics else None,
            "trials": trials,
            "pareto_frontier": [dict(point) for point in _pareto(trials)],
        }
        print(
            f"{arm:<20} util={_objective(selected['validation'], weights):+.3f}  "  # type: ignore[arg-type]
            f"test_conf={test_metrics.get('confirmation_rate', float('nan')):.3f} "
            f"test_det={test_metrics.get('anomaly_detection_rate', float('nan')):.3f} "
            f"test_fsw={test_metrics.get('false_switch_rate', float('nan')):.3f} "
            f"pareto={len(report['arms'][arm]['pareto_frontier'])}"  # type: ignore[index]
        )

    output: Path = arguments.output
    output.mkdir(parents=True, exist_ok=True)
    (output / "tuning.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    print(f"wrote {output}/tuning.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
