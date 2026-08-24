"""Counterfactual four-strata diagnostic for Project One and Project Two.

This module is deliberately evaluation-only.  It freezes the existing methods,
action policies, parameters, truth stores, and scorers, then changes one visible
data factor at a time.  The strata therefore diagnose *where* a ranking changes;
they do not constitute a new method or an external-validity claim.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import timedelta
from typing import Any

from cpswm.contracts import OcclusionState, ProjectTwoDatasetSplit
from cpswm.system.reproducibility import content_sha256

from .fair_ablation import ProjectOneAblationArmId
from .online_shift_attribution import (
    OnlineShiftFamily,
    OnlineShiftGeneratedCase,
    OnlineShiftSplit,
    OnlineShiftSuiteConfig,
    OnlineShiftSuiteGenerator,
)
from .project_one_shift_action_death_test import (
    FrozenActionPolicy,
    _evaluate_arm,
    _paired_intervals_for_artifacts,
)
from .project_two_action_benchmark import (
    FIDELITY,
    ProjectTwoActionBenchmarkV02,
    ProjectTwoActionMethod,
)
from .project_two_dataset_adapters import D0SyntheticOracleReplayAdapter
from .structure_two_action_death_test import StructureTwoActionScenarioGenerator

PROTOCOL_VERSION = "cross-structure-four-strata-diagnostic@0.1"

STRATA = {
    "s1_known_actor_complete_evidence": {
        "changed_factor": "none; upper-bound actor evidence and complete observations",
        "purpose": "check the structures' synthetic upper bound",
    },
    "s2_actor_confusion_missing_evidence": {
        "changed_factor": "actor evidence only: half missing, half uninformative",
        "purpose": "test whether multi-actor attribution adds value",
    },
    "s3_wrong_then_late_correct_evidence": {
        "changed_factor": "actor evidence timing only: confidently wrong first, correct later",
        "purpose": "test reversible attribution and recovery",
    },
    "s4_observation_policy_plus_habit_change": {
        "changed_factor": "observation process only: coverage drops when the habit changes",
        "purpose": "test cause separation and long-term memory protection",
    },
}

PROJECT_ONE_PARAMS: dict[ProjectOneAblationArmId, dict[str, int | float]] = {
    ProjectOneAblationArmId.ORDINARY_BOCPD: {
        "warmup_days": 2,
        "hazard_probability": 0.05,
        "detection_threshold": 0.5,
    },
    ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD: {
        "warmup_days": 2,
        "hazard_probability": 0.1,
        "detection_threshold": 0.35,
    },
    ProjectOneAblationArmId.JOINT_CAUSE_FACTORIZED_BOCPD: {
        "warmup_days": 2,
        "hazard_probability": 0.01,
        "detection_threshold": 0.2,
        "beam_width": 24,
        "maximum_simultaneous_causes": 2,
        "simultaneous_hazard_scale": 0.25,
    },
}

PROJECT_TWO_PARAMS: dict[ProjectTwoActionMethod, dict[str, float]] = {
    ProjectTwoActionMethod.FREQUENCY: {"parameter": 0.0},
    ProjectTwoActionMethod.RECENCY: {"parameter": 0.5},
    ProjectTwoActionMethod.MARKOV: {"parameter": 0.1},
    ProjectTwoActionMethod.AMG_MATCHED: {"parameter": 0.2},
    ProjectTwoActionMethod.O_STAR: {"parameter": 0.7},
    ProjectTwoActionMethod.DYNAMEM: {"parameter": 0.5},
    ProjectTwoActionMethod.STAR: {"parameter": 0.8},
    ProjectTwoActionMethod.FULL_RERUN: {"parameter": 0.0},
    ProjectTwoActionMethod.PROJECT_TWO: {"owner_threshold": 0.4},
}

FROZEN_DECISION_RULES = {
    "core_technical_failure": (
        "candidate is significantly worse in S1, where actor evidence and observations are complete"
    ),
    "data_activation_supported": (
        "candidate is not worse in S1 and gains relative advantage in S2-S4"
    ),
    "domain_gap": (
        "candidate passes the four synthetic strata but fails under the same evaluator on "
        "real replay"
    ),
    "insufficient_evidence": ("paired intervals cross zero or truth/stratum coverage gates fail"),
}


def _posterior(evidence: Any, target: str | None) -> Any:
    if evidence is None:
        return None
    keys = tuple(evidence.actor_posterior)
    if target is None:
        values = {key: 1.0 / len(keys) for key in keys}
    else:
        if target not in keys:
            raise ValueError(f"actor evidence does not contain target {target!r}")
        remainder = 0.02 / max(1, len(keys) - 1)
        values = {key: (0.98 if key == target else remainder) for key in keys}
    return evidence.model_copy(update={"actor_posterior": values})


def _wrong_target(keys: Sequence[str], correct: str) -> str:
    return next(key for key in keys if key != correct and key != "unknown_actor")


def _project_one_evidence_transform(
    case: OnlineShiftGeneratedCase, *, mode: str
) -> OnlineShiftGeneratedCase:
    owner = str(case.model_input.target_person_id)
    change_time = case.evaluator_truth.change_time
    transformed = []
    for index, evidence in enumerate(case.model_input.actor_evidence):
        if mode == "confused_missing":
            if index % 2 == 0:
                continue
            transformed.append(_posterior(evidence, None))
        elif mode == "wrong_then_correct":
            target = owner
            if evidence.evidence_time < change_time + timedelta(days=2):
                target = _wrong_target(tuple(evidence.actor_posterior), owner)
            transformed.append(_posterior(evidence, target))
        else:
            transformed.append(_posterior(evidence, owner))
    return case.model_copy(
        update={
            "model_input": case.model_input.model_copy(
                update={"actor_evidence": tuple(transformed)}
            ),
            "evaluator_truth": case.evaluator_truth.model_copy(
                update={
                    "split": OnlineShiftSplit.TEST,
                    "intervention_available": True,
                }
            ),
        }
    )


def _project_one_strata(seed_count: int) -> dict[str, tuple[OnlineShiftGeneratedCase, ...]]:
    seeds = tuple(range(25001, 25001 + seed_count))
    suite = OnlineShiftSuiteGenerator().generate(
        OnlineShiftSuiteConfig(
            seeds=seeds,
            duration_days=10,
            case_id_salt="cross-structure-four-strata-project-one@0.1",
            shuffle_seed=20260825,
        )
    )
    by_family: dict[OnlineShiftFamily, dict[int, OnlineShiftGeneratedCase]] = {
        family: {} for family in OnlineShiftFamily
    }
    for case in suite.cases:
        by_family[case.evaluator_truth.family][case.evaluator_truth.scenario_seed] = case
    habit = tuple(by_family[OnlineShiftFamily.HABIT][seed] for seed in seeds)
    simultaneous = tuple(by_family[OnlineShiftFamily.OBSERVATION_HABIT][seed] for seed in seeds)
    return {
        "s1_known_actor_complete_evidence": tuple(
            _project_one_evidence_transform(case, mode="complete") for case in habit
        ),
        "s2_actor_confusion_missing_evidence": tuple(
            _project_one_evidence_transform(case, mode="confused_missing") for case in habit
        ),
        "s3_wrong_then_late_correct_evidence": tuple(
            _project_one_evidence_transform(case, mode="wrong_then_correct") for case in habit
        ),
        "s4_observation_policy_plus_habit_change": tuple(
            _project_one_evidence_transform(case, mode="complete") for case in simultaneous
        ),
    }


def _run_project_one(seed_count: int, bootstrap_samples: int) -> dict[str, Any]:
    policy = FrozenActionPolicy(
        policy_id="habit-reset-consolidation-policy@6",
        active_verification_enabled=True,
        multi_label_consolidation=True,
    )
    output = {}
    for stratum, cases in _project_one_strata(seed_count).items():
        artifacts = {
            arm: _evaluate_arm(arm, PROJECT_ONE_PARAMS[arm], cases, policy, "test")
            for arm in PROJECT_ONE_PARAMS
        }
        intervals = _paired_intervals_for_artifacts(artifacts, bootstrap_samples)
        output[stratum] = {
            "case_count": len(cases),
            "input_sha256": content_sha256(tuple(case.model_input for case in cases)),
            "metrics_by_arm": {
                arm.value: {
                    "mechanism": artifact.mechanism_metrics.model_dump(mode="json"),
                    "action": artifact.metrics.model_dump(mode="json"),
                }
                for arm, artifact in artifacts.items()
            },
            "paired_joint_minus_reference": [item.model_dump(mode="json") for item in intervals],
        }
    return output


def _transform_project_two_episode(dataset: Any, episode: Any, *, mode: str) -> Any:
    truth = dataset.truth_for(episode.episode_id)
    ordered_truth = tuple(truth.truth_by_step[step.step_id] for step in episode.steps)
    initial_habit = ordered_truth[0].true_owner_habit_location
    habit_change_index = next(
        index
        for index, item in enumerate(ordered_truth)
        if item.true_owner_habit_location != initial_habit
    )
    steps = []
    for index, step in enumerate(episode.steps):
        target = truth.truth_by_step[step.step_id]
        evidence = step.actor_evidence
        if mode == "confused_missing":
            actor_evidence = None if index % 2 == 0 else _posterior(evidence, None)
        elif mode == "wrong_then_correct":
            correct = target.true_actor
            selected = correct
            if index < (2 * len(episode.steps)) // 3:
                selected = _wrong_target(tuple(evidence.actor_posterior), correct)
            actor_evidence = _posterior(evidence, selected)
        else:
            actor_evidence = _posterior(evidence, target.true_actor)

        update: dict[str, Any] = {"actor_evidence": actor_evidence}
        if (
            mode == "observation_plus_habit"
            and index >= habit_change_index
            and (index - habit_change_index) % 2 == 1
        ):
            update.update(
                {
                    "before": None,
                    "after": None,
                    "source_location_id": None,
                    "actor_evidence": None,
                    "mechanism_evidence": None,
                    "ordered_role_evidence": None,
                    "visibility_probability": 0.25,
                    "occlusion_state": OcclusionState.UNKNOWN,
                    "detection_confidence": None,
                }
            )
        steps.append(step.model_copy(update=update))
    return episode.model_copy(update={"steps": tuple(steps)})


def _project_two_dataset(seed_count: int) -> Any:
    adapter = D0SyntheticOracleReplayAdapter(
        validation_seeds=tuple(range(26001, 26021)),
        test_seeds=tuple(range(27001, 27001 + seed_count)),
        max_steps_per_episode=32,
        dataset_version="cross-structure-four-strata-project-two@0.1",
        object_family_bucket_count=10,
        sealed_secret="cross-structure-four-strata-project-two-seal@0.1",
    )
    adapter.generator = _VariableUpperBoundGenerator()
    return adapter.build()


class _VariableUpperBoundGenerator:
    """Full-observation multi-actor trajectories with seed-varying change timing.

    Actor identity is made known by the evidence transform, not by deleting
    guest events.  For each outer seed we deterministically search an inner
    seed whose guest transitions are all observed, so S1 has both real guest
    events and complete observations.  Varying abrupt-change and recurrence
    days prevents UUID-only pseudo-replication while S2-S4 remain paired
    transforms of the same generated case.
    """

    def generate(self, seed: int) -> Any:
        abrupt_day = 14 + seed % 5
        recurrence_day = abrupt_day + 5 + (seed // 5) % 6
        for attempt in range(1000):
            inner_seed = seed * 1000 + attempt
            case = StructureTwoActionScenarioGenerator(
                duration_days=32,
                guest_window=(6, 11),
                abrupt_day=abrupt_day,
                recurrence_day=recurrence_day,
                observation_coverage=1.0,
                sealed_secret="cross-structure-four-strata-project-two-seal@0.1",
                include_open_world_unknown_events=False,
            ).generate(inner_seed)
            if all(day.after is not None for day in case.visible.days):
                return case
        raise RuntimeError("failed to materialize a complete-observation guest trajectory")


def _run_project_two(seed_count: int) -> dict[str, Any]:
    dataset = _project_two_dataset(seed_count)
    benchmark = ProjectTwoActionBenchmarkV02()
    episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
    modes = {
        "s1_known_actor_complete_evidence": "complete",
        "s2_actor_confusion_missing_evidence": "confused_missing",
        "s3_wrong_then_late_correct_evidence": "wrong_then_correct",
        "s4_observation_policy_plus_habit_change": "observation_plus_habit",
    }
    output = {}
    for stratum, mode in modes.items():
        transformed = tuple(
            _transform_project_two_episode(dataset, episode, mode=mode) for episode in episodes
        )
        case_metrics = tuple(
            benchmark._evaluate_episode(dataset, episode, method, params)
            for episode in transformed
            for method, params in PROJECT_TWO_PARAMS.items()
        )
        aggregates = benchmark._aggregate(case_metrics)
        output[stratum] = {
            "case_count": len(transformed),
            "input_sha256": content_sha256(transformed),
            "aggregate_metrics": [item.model_dump(mode="json") for item in aggregates],
            "revision_totals": {
                "calls": sum(
                    item.full_feedback_revision_calls
                    for item in case_metrics
                    if item.method is ProjectTwoActionMethod.PROJECT_TWO
                ),
                "requests": sum(
                    item.project_one_stat_requests
                    for item in case_metrics
                    if item.method is ProjectTwoActionMethod.PROJECT_TWO
                ),
                "applications": sum(
                    item.project_one_stat_applications
                    for item in case_metrics
                    if item.method is ProjectTwoActionMethod.PROJECT_TWO
                ),
            },
        }
    return output


def _project_two_primary_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    metrics = report["aggregate_metrics"]
    names = {
        "put_back_error_rate",
        "cumulative_action_regret",
        "owner_habit_contamination",
        "late_feedback_recovery_latency",
    }
    return {
        item["method"]: {
            metric["metric"]: metric["value"]
            for metric in metrics
            if metric["method"] == item["method"] and metric["metric"] in names
        }
        for item in metrics
    }


def _automatic_diagnosis(project_one: Mapping[str, Any], project_two: Mapping[str, Any]) -> dict:
    p1_s1 = project_one["s1_known_actor_complete_evidence"]
    p1_intervals = [
        item
        for item in p1_s1["paired_joint_minus_reference"]
        if item["endpoint_id"].startswith("downstream-action-regret")
    ]
    p1_technical = bool(p1_intervals) and all(item["lower_95"] > 0 for item in p1_intervals)

    p2_s1 = _project_two_primary_summary(project_two["s1_known_actor_complete_evidence"])
    candidate = p2_s1[ProjectTwoActionMethod.PROJECT_TWO.value]["cumulative_action_regret"]
    faithful = [
        values["cumulative_action_regret"]
        for method, values in p2_s1.items()
        if method != ProjectTwoActionMethod.PROJECT_TWO.value
        and FIDELITY[ProjectTwoActionMethod(method)].value
        in {"faithful_matched", "full_rerun_control"}
    ]
    p2_technical = candidate > min(faithful)
    return {
        "project_one": ("core_technical_failure" if p1_technical else "insufficient_evidence"),
        "project_two": (
            "core_technical_failure_on_current_action_objective"
            if p2_technical
            else "data_activation_supported_or_insufficient_evidence"
        ),
        "external_validity": "not_tested; real replay remains required",
    }


def run_cross_structure_strata_diagnostic(
    *, seed_count: int = 50, bootstrap_samples: int = 2000
) -> dict[str, Any]:
    if not 25 <= seed_count <= 75:
        raise ValueError("seed_count must keep the four-strata package within 100-300 episodes")
    if bootstrap_samples < 500:
        raise ValueError("bootstrap_samples must be at least 500")
    project_one = _run_project_one(seed_count, bootstrap_samples)
    project_two = _run_project_two(seed_count)
    payload: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "design": {
            "strata": STRATA,
            "seed_count_per_stratum": seed_count,
            "episode_equivalents_per_structure": seed_count * len(STRATA),
            "frozen_decision_rules": FROZEN_DECISION_RULES,
            "single_variable_assertion": (
                "S2-S4 are derived from S1 with truth and evaluator unchanged"
            ),
        },
        "frozen_parameters": {
            "project_one": {key.value: value for key, value in PROJECT_ONE_PARAMS.items()},
            "project_two": {key.value: value for key, value in PROJECT_TWO_PARAMS.items()},
        },
        "project_one": project_one,
        "project_two": project_two,
    }
    payload["diagnosis"] = _automatic_diagnosis(project_one, project_two)
    payload["report_sha256"] = content_sha256(payload)
    return payload


__all__ = [
    "FROZEN_DECISION_RULES",
    "PROJECT_ONE_PARAMS",
    "PROJECT_TWO_PARAMS",
    "PROTOCOL_VERSION",
    "STRATA",
    "run_cross_structure_strata_diagnostic",
]
