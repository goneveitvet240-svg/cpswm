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

The selection rule is stated in the output rather than hidden in a weighted
score: ``maximize (confirmation rate - false switch rate)``, ties broken by
lower mean detection delay.  The full frontier over
``(false switch rate, confirmation rate)`` is saved alongside, so a different
utility weighting can be applied afterwards without re-running the search.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

from cpswm.system.evaluation_operations.project_one_methods import (
    CategoricalBOCPDMethod,
    ContextFrequencyMethod,
    CoreHabitChainMethod,
    PersistenceMethod,
    ProjectOneMethod,
)
from cpswm.system.evaluation_operations.project_one_protocol import (
    CategoricalBOCPDConfig,
    ContextFrequencyConfig,
    PersistenceConfig,
    ProjectOneProtocolConfig,
    ResidualCalibration,
    SignalAblation,
)
from cpswm.system.evaluation_operations.project_one_runner import ProjectOneRunner
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


def _chain_grid(
    name: str, ablation: SignalAblation, calibration: ResidualCalibration, budget: int
) -> list[tuple[dict[str, object], Builder]]:
    base = replace(ProjectOneProtocolConfig(), ablation=ablation, residual_calibration=calibration)
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


def _pareto(trials: list[dict[str, object]]) -> list[dict[str, object]]:
    """Non-dominated points over (false switch rate down, confirmation up)."""

    frontier: list[dict[str, object]] = []
    for candidate in trials:
        c_switch = float(candidate["validation"]["false_switch_rate"])  # type: ignore[index]
        c_confirm = float(candidate["validation"]["confirmation_rate"])  # type: ignore[index]
        dominated = any(
            float(other["validation"]["false_switch_rate"]) <= c_switch  # type: ignore[index]
            and float(other["validation"]["confirmation_rate"]) >= c_confirm  # type: ignore[index]
            and (
                float(other["validation"]["false_switch_rate"]) < c_switch  # type: ignore[index]
                or float(other["validation"]["confirmation_rate"]) > c_confirm  # type: ignore[index]
            )
            for other in trials
        )
        if not dominated:
            frontier.append(candidate)
    return frontier


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/project_one/tuning"))
    parser.add_argument("--budget", type=int, default=12, help="grid points per arm")
    parser.add_argument(
        "--calibration",
        choices=[item.value for item in ResidualCalibration],
        default=ResidualCalibration.RAW_CLIP.value,
    )
    arguments = parser.parse_args()

    calibration = ResidualCalibration(arguments.calibration)
    budget: int = arguments.budget

    grids: dict[str, list[tuple[dict[str, object], Builder]]] = {
        "full": _chain_grid("full", SignalAblation.FULL, calibration, budget),
        "no_rls": _chain_grid("no_rls", SignalAblation.NO_RLS, calibration, budget),
        "shuffled_rls": _chain_grid(
            "shuffled_rls", SignalAblation.SHUFFLED_RLS, calibration, budget
        ),
        "rls_only": _chain_grid("rls_only", SignalAblation.RLS_ONLY, calibration, budget),
        "categorical_bocpd": _bocpd_grid(budget),
        "context_frequency": _frequency_grid(budget),
        "persistence": _persistence_grid(budget),
    }

    report: dict[str, object] = {
        "residual_calibration": calibration.value,
        "budget_per_arm": budget,
        "validation_scenarios": list(VALIDATION),
        "test_scenarios": list(TEST),
        "selection_rule": (
            "maximize (confirmation_rate - false_switch_rate); tie-break on lower delay"
        ),
        "arms": {},
    }

    for arm, grid in grids.items():
        if len({len(grid)} | {budget}) != 1:
            raise RuntimeError(f"{arm} received {len(grid)} points, not the shared budget {budget}")
        trials: list[dict[str, object]] = []
        for params, builder in grid:
            validation = _score(builder, VALIDATION)
            trials.append({"params": params, "validation": validation})

        def rank(trial: dict[str, object]) -> tuple[float, float]:
            metrics = trial["validation"]  # type: ignore[index]
            delay = float(metrics["mean_detection_delay"])  # type: ignore[index]
            return (
                -(float(metrics["confirmation_rate"]) - float(metrics["false_switch_rate"])),  # type: ignore[index]
                delay if delay == delay else 1e9,
            )

        selected = min(trials, key=rank)
        selected_builder = next(builder for params, builder in grid if params == selected["params"])
        test_metrics = _score(selected_builder, TEST)
        report["arms"][arm] = {  # type: ignore[index]
            "selected_params": selected["params"],
            "validation": selected["validation"],
            "test": test_metrics,
            "trials": trials,
            "pareto_frontier": [dict(point) for point in _pareto(trials)],
        }
        print(
            f"{arm:<20} selected={selected['params']} "
            f"val_conf={selected['validation']['confirmation_rate']:.3f} "  # type: ignore[index]
            f"test_conf={test_metrics.get('confirmation_rate', float('nan')):.3f} "
            f"test_fsw={test_metrics.get('false_switch_rate', float('nan')):.3f}"
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
