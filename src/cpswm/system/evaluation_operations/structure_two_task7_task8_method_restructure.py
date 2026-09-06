"""Failure-driven method restructuring for Structure-Two Tasks 7 and 8.

This module does not rewrite either failed v0.4 result.  Task 7 receives a
support-aware correction router: use the exact likelihood-ratio correction
only while its pre-resampling effective sample size remains adequate, otherwise
execute the already-defined full-replay fallback.  Task 8 receives an explicit
identifiability audit because an exact two-stage factorization can reconstruct
the same joint posterior and therefore cannot establish a representation-level
joint advantage from the current matched-information experiment.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

from . import structure_two_task8_matched_confirmatory as task8
from .structure_two_backbone_falsifier import (
    TASK7_ACTION_DISTRIBUTION_TV_TOLERANCE,
    TASK7_BELIEF_AXIS_TV_TOLERANCE,
    ArmName,
    CorrectionTreatment,
    _task7_bayes_action_key,
    action_posterior_distance,
    build_scenario,
    marginal_distance,
    owner_contamination,
    repair_observation,
    result_embodied_action_posterior,
    run_late_correction,
    task7_belief_marginals,
)

TASK7_GUARDED_RESTRUCTURE_PROTOCOL_ID: Final = (
    "structure-two-support-guarded-late-correction@0.1-development"
)
TASK7_GUARDED_REWEIGHT_ESS_RATIO: Final = 0.30
TASK8_IDENTIFIABILITY_PROTOCOL_ID: Final = (
    "structure-two-joint-two-stage-identifiability@0.1-development"
)


def _factor_cells(seed: int) -> tuple[dict[str, bool | int], ...]:
    return tuple(
        {
            "seed": seed,
            "high_attribution_ambiguity": ambiguity,
            "adverse_delayed_feedback": delayed,
            "open_world_actor": open_world,
            "short_regime": short_regime,
        }
        for ambiguity in (False, True)
        for delayed in (False, True)
        for open_world in (False, True)
        for short_regime in (False, True)
    )


def run_task7_guarded_restructure_study(
    *,
    scenario_seeds: Sequence[int],
    replicate_seeds: Sequence[int],
    gaps: int = 12,
    correction_index: int = 2,
    budget: int = 384,
    ess_ratio_threshold: float = TASK7_GUARDED_REWEIGHT_ESS_RATIO,
) -> dict[str, Any]:
    """Evaluate the support-aware repair router without relabeling v0.4.

    The route is selected before window MH.  Adequate corrected importance
    support keeps the exact reweight-only posterior; inadequate support invokes
    full replay.  The latter is deliberately visible in every row and in cost
    accounting, so a trivial all-fallback system cannot masquerade as a local
    correction win.
    """

    if not scenario_seeds or not replicate_seeds:
        raise ValueError("Task-7 guarded study requires non-empty seed sets")
    if len(set(scenario_seeds)) != len(scenario_seeds):
        raise ValueError("Task-7 guarded scenario seeds must be unique")
    if len(set(replicate_seeds)) != len(replicate_seeds):
        raise ValueError("Task-7 guarded replicate seeds must be unique")
    if not 0.0 < ess_ratio_threshold <= 1.0:
        raise ValueError("Task-7 guarded ESS threshold must lie in (0, 1]")

    rows: list[dict[str, Any]] = []
    for scenario_seed in scenario_seeds:
        for factors in _factor_cells(int(scenario_seed)):
            scenario = build_scenario(
                gaps=gaps,
                seed=int(factors["seed"]),
                high_attribution_ambiguity=bool(factors["high_attribution_ambiguity"]),
                adverse_delayed_feedback=bool(factors["adverse_delayed_feedback"]),
                open_world_actor=bool(factors["open_world_actor"]),
                short_regime=bool(factors["short_regime"]),
                corrupt_index=correction_index,
            )
            corrected = repair_observation(scenario, correction_index)
            for replicate_seed in replicate_seeds:
                reference = run_late_correction(
                    scenario,
                    treatment=CorrectionTreatment.FULL_RERUN,
                    correction_index=correction_index,
                    arm=ArmName.ADAPTIVE_TYPED_RBPF,
                    budget=budget,
                    seed=int(replicate_seed),
                )
                guarded = run_late_correction(
                    scenario,
                    treatment=CorrectionTreatment.LOCAL_REJUVENATION,
                    correction_index=correction_index,
                    arm=ArmName.ADAPTIVE_TYPED_RBPF,
                    budget=budget,
                    seed=int(replicate_seed),
                    guarded_reweight_ess_ratio=ess_ratio_threshold,
                )
                reference_beliefs = task7_belief_marginals(reference, correction_index)
                guarded_beliefs = task7_belief_marginals(guarded, correction_index)
                belief_distances = {
                    axis: marginal_distance(reference_beliefs[axis], guarded_beliefs[axis])
                    for axis in reference_beliefs
                }
                reference_actions = result_embodied_action_posterior(
                    reference, corrected.observations
                )
                guarded_actions = result_embodied_action_posterior(guarded, corrected.observations)
                reference_action = _task7_bayes_action_key(reference_actions)
                guarded_action = _task7_bayes_action_key(guarded_actions)
                rows.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "scenario_factors": {
                            key: bool(value) for key, value in factors.items() if key != "seed"
                        },
                        "replicate_seed": int(replicate_seed),
                        "route": guarded.cost["repair_mode"],
                        "fallback_required": bool(guarded.cost["fallback_required"]),
                        "fallback_reasons": guarded.cost["fallback_reasons"],
                        "pre_rejuvenation_ess_ratio": guarded.cost["pre_rejuvenation_ess_ratio"],
                        "belief_axis_distances_to_full_rerun": belief_distances,
                        "max_belief_axis_distance_to_full_rerun": max(belief_distances.values()),
                        "action_distribution_distance_to_full_rerun": (
                            action_posterior_distance(reference_actions, guarded_actions)
                        ),
                        "selected_action_matches_full_rerun": (
                            reference_action is not None and reference_action == guarded_action
                        ),
                        "guarded_owner_contamination": owner_contamination(
                            guarded, scenario.truth, correction_index
                        ),
                        "full_rerun_owner_contamination": owner_contamination(
                            reference, scenario.truth, correction_index
                        ),
                        "guarded_marginal_elementary_evaluations": int(
                            guarded.cost["marginal_elementary_likelihood_evaluations"]
                        ),
                        "full_rerun_marginal_elementary_evaluations": int(
                            reference.cost["marginal_elementary_likelihood_evaluations"]
                        ),
                    }
                )

    row_count = len(rows)
    route_counts = {
        route: sum(1 for row in rows if row["route"] == route)
        for route in ("guarded_reweight", "guarded_full_replay")
    }
    belief_guardrail = all(
        float(row["max_belief_axis_distance_to_full_rerun"]) <= TASK7_BELIEF_AXIS_TV_TOLERANCE
        for row in rows
    )
    action_guardrail = all(
        float(row["action_distribution_distance_to_full_rerun"])
        <= TASK7_ACTION_DISTRIBUTION_TV_TOLERANCE
        and bool(row["selected_action_matches_full_rerun"])
        for row in rows
    )
    guarded_contamination = sum(float(row["guarded_owner_contamination"]) for row in rows)
    full_contamination = sum(float(row["full_rerun_owner_contamination"]) for row in rows)
    contamination_guardrail = guarded_contamination <= full_contamination
    guarded_work = sum(int(row["guarded_marginal_elementary_evaluations"]) for row in rows)
    full_work = sum(int(row["full_rerun_marginal_elementary_evaluations"]) for row in rows)
    mixed_route_nontriviality = all(count > 0 for count in route_counts.values())
    failed_guard_rows = [
        {
            "scenario_id": row["scenario_id"],
            "replicate_seed": row["replicate_seed"],
            "route": row["route"],
            "pre_rejuvenation_ess_ratio": row["pre_rejuvenation_ess_ratio"],
            "max_belief_axis_distance_to_full_rerun": row["max_belief_axis_distance_to_full_rerun"],
            "action_distribution_distance_to_full_rerun": row[
                "action_distribution_distance_to_full_rerun"
            ],
            "guarded_owner_contamination": row["guarded_owner_contamination"],
            "full_rerun_owner_contamination": row["full_rerun_owner_contamination"],
        }
        for row in rows
        if float(row["max_belief_axis_distance_to_full_rerun"]) > TASK7_BELIEF_AXIS_TV_TOLERANCE
        or float(row["action_distribution_distance_to_full_rerun"])
        > TASK7_ACTION_DISTRIBUTION_TV_TOLERANCE
        or not bool(row["selected_action_matches_full_rerun"])
        or float(row["guarded_owner_contamination"]) > float(row["full_rerun_owner_contamination"])
    ]
    candidate_passed = (
        belief_guardrail
        and action_guardrail
        and contamination_guardrail
        and guarded_work < full_work
        and mixed_route_nontriviality
    )
    return {
        "protocol_id": TASK7_GUARDED_RESTRUCTURE_PROTOCOL_ID,
        "evidence_status": (
            "D0 failure-driven development candidate; not independent custody and not a "
            "replacement for the immutable Task-7 v0.4 failure"
        ),
        "design": {
            "gaps": gaps,
            "correction_index": correction_index,
            "scenario_seeds": [int(seed) for seed in scenario_seeds],
            "replicate_seeds": [int(seed) for seed in replicate_seeds],
            "factor_cells_per_scenario_seed": 16,
            "particle_budget": budget,
            "guarded_reweight_ess_ratio": ess_ratio_threshold,
            "threshold_origin": (
                "frozen after diagnosing v0.4 and before evaluating the new holdout seeds"
            ),
        },
        "method": {
            "name": "support-aware reversible correction router",
            "adequate_support_route": "exact observation likelihood-ratio reweighting",
            "support_collapse_route": "explicit full replay",
            "window_mh_after_support_collapse_forbidden": True,
            "fallback_visible_and_fully_costed": True,
        },
        "route_counts": route_counts,
        "belief_guardrail_passed": belief_guardrail,
        "action_guardrail_passed": action_guardrail,
        "contamination_guardrail_passed": contamination_guardrail,
        "mean_guarded_owner_contamination": guarded_contamination / row_count,
        "mean_full_rerun_owner_contamination": full_contamination / row_count,
        "mean_guarded_marginal_elementary_evaluations": guarded_work / row_count,
        "mean_full_rerun_marginal_elementary_evaluations": full_work / row_count,
        "mixed_route_nontriviality_passed": mixed_route_nontriviality,
        "candidate_passed": candidate_passed,
        "failed_guard_rows": failed_guard_rows,
        "failure_diagnosis": (
            None
            if candidate_passed
            else (
                "An ESS gate detects weight variance but cannot detect historical support that "
                "was already deleted by earlier forward resampling. The next method revision "
                "must change retained inference state, for example a correction-ready ancestry "
                "reservoir or a backward-message checkpoint; more fixed-window MH sweeps cannot "
                "recreate absent outside-window trajectories."
            )
        ),
        "required_next_state_change": (
            None
            if candidate_passed
            else "correction-ready ancestry reservoir or backward-message checkpoint"
        ),
        "claim_boundary": (
            "A positive candidate result supports only this support-aware routing rule on the "
            "declared synthetic seeds. It does not rescue pure fixed-window equivalence, select "
            "the Task-12 kernel, or authorize the seven-operator ablation."
        ),
        "rows": rows,
    }


def run_task8_identifiability_audit(*, seeds: Sequence[int]) -> dict[str, Any]:
    """Show whether the current matched design identifies a joint-form benefit."""

    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Task-8 identifiability seeds must be non-empty and unique")
    posterior_l1: list[float] = []
    policy_l1: list[float] = []
    expected_cost_differences: list[float] = []
    unit_rows: list[dict[str, Any]] = []
    for cluster_seed, scenario in task8._scenario_set(1, tuple(int(seed) for seed in seeds)):
        unit = task8._prepare_unit(
            scenario,
            task8.TASK8_REGISTERED_STATE_BUDGET,
            cluster_seed=cluster_seed,
        )
        joint = task8._evaluate_candidate(unit, "joint", 1.0)
        matched = task8._evaluate_candidate(unit, "matched_two_stage", 1.0)
        joint_belief = task8._arm_belief("joint", unit.exact, unit.rows, 1.0)
        matched_belief = task8._arm_belief("matched_two_stage", unit.exact, unit.rows, 1.0)
        keys = set(joint_belief) | set(matched_belief)
        belief_l1 = sum(
            abs(joint_belief.get(key, 0.0) - matched_belief.get(key, 0.0)) for key in keys
        )
        joint_policy = joint["consequential_action_policy"]
        matched_policy = matched["consequential_action_policy"]
        assert isinstance(joint_policy, Mapping) and isinstance(matched_policy, Mapping)
        actions = set(joint_policy) | set(matched_policy)
        action_l1 = sum(
            abs(float(joint_policy.get(key, 0.0)) - float(matched_policy.get(key, 0.0)))
            for key in actions
        )
        cost_difference = float(matched["consequential_expected_cost"]) - float(
            joint["consequential_expected_cost"]
        )
        posterior_l1.append(belief_l1)
        policy_l1.append(action_l1)
        expected_cost_differences.append(cost_difference)
        unit_rows.append(
            {
                "unit_id": unit.unit_id,
                "cluster_seed": cluster_seed,
                "posterior_l1": belief_l1,
                "policy_l1": action_l1,
                "matched_two_stage_cost_minus_joint_cost": cost_difference,
            }
        )

    tolerance = 1e-12
    representation_equivalent = (
        max(posterior_l1) <= tolerance
        and max(policy_l1) <= tolerance
        and max(abs(value) for value in expected_cost_differences) <= tolerance
    )
    return {
        "protocol_id": TASK8_IDENTIFIABILITY_PROTOCOL_ID,
        "evidence_status": (
            "algebraic identifiability audit on D0 exact posterior tables; no external validity"
        ),
        "seeds": [int(seed) for seed in seeds],
        "factor_units": len(unit_rows),
        "identity_temperature": 1.0,
        "max_posterior_l1": max(posterior_l1),
        "max_policy_l1": max(policy_l1),
        "max_absolute_expected_cost_difference": max(
            abs(value) for value in expected_cost_differences
        ),
        "matched_two_stage_representation_equivalent": representation_equivalent,
        "joint_representation_superiority_identifiable": not representation_equivalent,
        "diagnosis": (
            "The matched two-stage arm is a chain-rule factorization of the same joint table. "
            "Any v0.4 difference away from identity is a calibration-parameterization effect, "
            "not identified evidence for joint representation superiority."
        ),
        "redesign_options_requiring_owner_choice": [
            {
                "axis": "online_compute",
                "comparison": (
                    "learned joint and learned two-stage inference under equal data, parameter, "
                    "latency, and state-access budgets"
                ),
            },
            {
                "axis": "distribution_shift",
                "comparison": (
                    "same-capacity joint and modular two-stage models under frozen cross-cell shift"
                ),
            },
            {
                "axis": "information_restriction",
                "comparison": (
                    "joint model versus a factorized arm that cannot observe cross-cell structure; "
                    "this answers necessity of the interaction, not superiority to exact two-stage"
                ),
            },
        ],
        "seven_operator_efficacy_authorized": False,
        "rows": unit_rows,
    }


__all__ = [
    "TASK7_GUARDED_RESTRUCTURE_PROTOCOL_ID",
    "TASK7_GUARDED_REWEIGHT_ESS_RATIO",
    "TASK8_IDENTIFIABILITY_PROTOCOL_ID",
    "run_task7_guarded_restructure_study",
    "run_task8_identifiability_audit",
]
