"""Four-arm matched comparison for the CF-BOCPD direct-baseline gate.

The innovation ledger lists ``CF-BOCPD`` at ``implementation complete`` with
"BOCPDMS 匹配对照未实现" as the single blocker to ``direct baseline passed``.
This module is that comparison and nothing else: it does not tune, gate, sign, or
publish; it runs four arms over one frozen suite and reports whether the joint
arm actually beats the strongest matched control.

Fairness rules enforced here, all of them the project's own:

* every arm sees the identical generated suite and the identical evidence frames;
* every arm gets the identical tuning budget (18 trials) and the identical
  selection key, computed on validation only;
* every arm is tuned over *its own* meaningful hyper-parameter ranges -- a
  baseline squeezed onto another arm's threshold scale until it never fires is a
  weakened baseline, and a weakened baseline is not evidence;
* the resampling unit for every interval is the **scenario seed**, not the case.
  Cases generated from one seed share a stream, a change time, and a family;
  bootstrapping cases would shrink every interval by roughly the square root of
  the family count and manufacture significance out of correlation.  This is the
  same unit the project-one v0.3 power module settled on.

The verdict is deliberately hard to pass: the joint arm must beat *every*
faithful control on the primary metric with a paired interval excluding zero,
and must not lose to any of them on the owner-habit false-positive guardrail.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import mean

from .fair_ablation import ProjectOneAblationArmId
from .online_shift_attribution import (
    OnlineShiftEvaluator,
    OnlineShiftGeneratedCase,
    OnlineShiftReport,
    OnlineShiftSplit,
)
from .project_one_shift_gates import (
    _SEARCH_SPACES,
    SHIFT_FOUR_ARMS,
    FrozenShiftSuiteConfig,
    _model_factory,
    generate_frozen_shift_suite,
)

#: The arm whose novelty claim is on trial.
CANDIDATE_ARM = ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD

#: Arms that may falsify the candidate.  All four are faithful or faithful
#: adaptations; none is a reduced-skill proxy.
CONTROL_ARMS: tuple[ProjectOneAblationArmId, ...] = tuple(
    arm for arm in SHIFT_FOUR_ARMS if arm is not CANDIDATE_ARM
)

#: Higher is better for these; lower is better for everything else reported.
_HIGHER_IS_BETTER = frozenset(
    {
        "cause_micro_f1",
        "cause_micro_precision",
        "cause_micro_recall",
        "exact_cause_set_accuracy",
        "change_detection_rate",
    }
)

PRIMARY_METRIC = "cause_micro_f1"
GUARDRAIL_METRIC = "false_owner_habit_change_rate"

REPORTED_METRICS: tuple[str, ...] = (
    "cause_micro_f1",
    "exact_cause_set_accuracy",
    "false_owner_habit_change_rate",
    "cause_brier_score",
    "cause_negative_log_likelihood",
    "cause_ece",
    "change_detection_rate",
    "mean_absolute_change_time_error_hours",
)


def scaled_seed_partition(
    seeds_per_split: int, *, base: int = 1_000_003, stride: int = 7919
) -> FrozenShiftSuiteConfig:
    """Disjoint train/validation/test seeds far from the frozen nine.

    ``base`` sits well above every seed any existing artifact pins, so a scaled
    run can never silently reuse a frozen test seed.
    """

    if seeds_per_split < 2:
        raise ValueError("each split needs at least two independent seeds")
    total = 3 * seeds_per_split
    seeds = tuple(base + stride * index for index in range(total))
    from .online_shift_attribution import OnlineShiftSuiteConfig

    return FrozenShiftSuiteConfig(
        train_seeds=seeds[:seeds_per_split],
        validation_seeds=seeds[seeds_per_split : 2 * seeds_per_split],
        test_seeds=seeds[2 * seeds_per_split :],
        base=OnlineShiftSuiteConfig(seeds=seeds),
    )


def _selection_key(report: OnlineShiftReport) -> tuple[float, ...]:
    return (
        report.cause_micro_f1,
        report.exact_cause_set_accuracy,
        -report.false_owner_habit_change_rate,
        -report.cause_brier_score,
        -report.cause_negative_log_likelihood,
    )


def _evaluate(model: object, cases: Sequence[OnlineShiftGeneratedCase]) -> OnlineShiftReport:
    from .online_shift_attribution import OnlineShiftAttributionCase

    bound = [
        OnlineShiftAttributionCase(
            truth=case.evaluator_truth,
            prediction=model.predict(case.model_input),  # type: ignore[attr-defined]
        )
        for case in cases
    ]
    return OnlineShiftEvaluator().evaluate(bound)


def _per_seed_metric(
    model: object, cases: Sequence[OnlineShiftGeneratedCase], metric: str
) -> dict[int, float]:
    by_seed: dict[int, list[OnlineShiftGeneratedCase]] = {}
    for case in cases:
        by_seed.setdefault(case.evaluator_truth.scenario_seed, []).append(case)
    return {
        seed: getattr(_evaluate(model, seed_cases), metric)
        for seed, seed_cases in sorted(by_seed.items())
    }


def _paired_bootstrap(
    differences: Sequence[float], *, draws: int = 4000
) -> tuple[float, float, float]:
    """Deterministic paired bootstrap over seeds.  Returns (mean, low, high)."""

    if not differences:
        return 0.0, 0.0, 0.0
    count = len(differences)
    # A fixed linear-congruential stream keeps this reproducible without pulling
    # in a global RNG whose state another caller could have moved.
    state = 88_172_645_463_325_252
    resampled: list[float] = []
    for _draw in range(draws):
        total = 0.0
        for _index in range(count):
            state ^= (state << 13) & 0xFFFFFFFFFFFFFFFF
            state ^= state >> 7
            state ^= (state << 17) & 0xFFFFFFFFFFFFFFFF
            total += differences[state % count]
        resampled.append(total / count)
    resampled.sort()
    low = resampled[int(0.025 * draws)]
    high = resampled[min(draws - 1, int(0.975 * draws))]
    return mean(differences), low, high


@dataclass(frozen=True, slots=True)
class ArmOutcome:
    arm: str
    selected_parameters: dict[str, float | int]
    validation: dict[str, float]
    test: dict[str, float]
    per_seed_primary: dict[int, float]
    per_seed_guardrail: dict[int, float]


def run_four_arm_comparison(
    config: FrozenShiftSuiteConfig | None = None,
) -> dict[str, object]:
    suite_config = config or FrozenShiftSuiteConfig()
    suite = generate_frozen_shift_suite(suite_config)
    validation = [
        case for case in suite.cases if case.evaluator_truth.split is OnlineShiftSplit.VALIDATION
    ]
    test = [case for case in suite.cases if case.evaluator_truth.split is OnlineShiftSplit.TEST]
    if not validation or not test:
        raise ValueError("four-arm comparison requires non-empty validation and test splits")

    outcomes: dict[str, ArmOutcome] = {}
    budgets = {len(_SEARCH_SPACES[arm]) for arm in SHIFT_FOUR_ARMS}
    if len(budgets) != 1:
        raise ValueError(f"tuning budgets are not matched across arms: {budgets}")
    for arm in SHIFT_FOUR_ARMS:
        trials = []
        for params in _SEARCH_SPACES[arm]:
            report = _evaluate(_model_factory(arm, dict(params)), validation)
            trials.append(
                (_selection_key(report), json.dumps(params, sort_keys=True), params, report)
            )
        # Ties break on the serialized parameters, never on iteration order.
        best_key, _serialized, best_params, best_validation = max(
            trials, key=lambda item: (item[0], item[1])
        )
        del best_key
        model = _model_factory(arm, dict(best_params))
        test_report = _evaluate(model, test)
        outcomes[arm.value] = ArmOutcome(
            arm=arm.value,
            selected_parameters=dict(best_params),
            validation={name: getattr(best_validation, name) for name in REPORTED_METRICS},
            test={name: getattr(test_report, name) for name in REPORTED_METRICS},
            per_seed_primary=_per_seed_metric(model, test, PRIMARY_METRIC),
            per_seed_guardrail=_per_seed_metric(model, test, GUARDRAIL_METRIC),
        )

    candidate = outcomes[CANDIDATE_ARM.value]
    comparisons: dict[str, dict[str, object]] = {}
    for arm in CONTROL_ARMS:
        control = outcomes[arm.value]
        seeds = sorted(set(candidate.per_seed_primary) & set(control.per_seed_primary))
        primary_differences = [
            candidate.per_seed_primary[seed] - control.per_seed_primary[seed] for seed in seeds
        ]
        guardrail_differences = [
            control.per_seed_guardrail[seed] - candidate.per_seed_guardrail[seed] for seed in seeds
        ]
        primary = _paired_bootstrap(primary_differences)
        guardrail = _paired_bootstrap(guardrail_differences)
        comparisons[arm.value] = {
            "paired_seeds": len(seeds),
            "primary_metric": PRIMARY_METRIC,
            "primary_paired_mean_candidate_minus_control": primary[0],
            "primary_ci95": [primary[1], primary[2]],
            "primary_candidate_wins": primary[1] > 0.0,
            "guardrail_metric": GUARDRAIL_METRIC,
            "guardrail_paired_mean_control_minus_candidate": guardrail[0],
            "guardrail_ci95": [guardrail[1], guardrail[2]],
            "guardrail_candidate_loses": guardrail[2] < 0.0,
        }

    wins = all(item["primary_candidate_wins"] for item in comparisons.values())
    loses_guardrail = any(item["guardrail_candidate_loses"] for item in comparisons.values())
    passed = bool(wins and not loses_guardrail)
    blocking = [
        f"{arm}: primary CI {item['primary_ci95']} does not exclude zero"
        for arm, item in comparisons.items()
        if not item["primary_candidate_wins"]
    ] + [
        f"{arm}: candidate loses the {GUARDRAIL_METRIC} guardrail, CI {item['guardrail_ci95']}"
        for arm, item in comparisons.items()
        if item["guardrail_candidate_loses"]
    ]
    return {
        "comparison_version": "project-one-shift-four-arm@0.1",
        "suite": {
            "train_seeds": list(suite_config.train_seeds),
            "validation_seeds": list(suite_config.validation_seeds),
            "test_seeds": list(suite_config.test_seeds),
            "validation_cases": len(validation),
            "test_cases": len(test),
        },
        "tuning_budget_per_arm": budgets.pop(),
        "candidate_arm": CANDIDATE_ARM.value,
        "arms": {
            name: {
                "selected_parameters": outcome.selected_parameters,
                "validation": outcome.validation,
                "test": outcome.test,
                "per_seed_primary": outcome.per_seed_primary,
                # The shared evaluator averages timing error over *detected*
                # cases only, so an arm that never fires reports 0.0 hours -- a
                # perfect score for abstaining.  Flag it rather than let a table
                # reader mistake it for accuracy.
                "timing_metric_is_vacuous": outcome.test["change_detection_rate"] == 0.0,
            }
            for name, outcome in outcomes.items()
        },
        "comparisons_vs_candidate": comparisons,
        "ledger_transition": (
            "direct baseline passed" if passed else "implementation complete (unchanged)"
        ),
        "direct_baseline_passed": passed,
        "blocking_findings": blocking,
        "vacuous_timing_arms": [
            name
            for name, outcome in outcomes.items()
            if outcome.test["change_detection_rate"] == 0.0
        ],
        "limitations": (
            "synthetic online shift suite only; no real perception, no embodied utility",
            "the model universe for the BOCPDMS adaptation is the four cause channels, "
            "which is a matched adaptation to this interface, not a port of the authors' code",
            "a passing verdict here would still be one synthetic benchmark, not external validity",
        ),
    }


def format_four_arm_table(payload: Mapping[str, object]) -> str:
    arms: Mapping[str, Mapping[str, Mapping[str, float]]] = payload["arms"]  # type: ignore[assignment]
    header = f"{'arm':<32}" + "".join(f"{name[:13]:>15}" for name in REPORTED_METRICS)
    lines = [header, "-" * len(header)]
    for name, outcome in arms.items():
        lines.append(
            f"{name:<32}"
            + "".join(f"{outcome['test'][metric]:>15.4f}" for metric in REPORTED_METRICS)
        )
    return "\n".join(lines)
