"""Test-opened-split diagnostic for the direct-P5 action-readout confound.

This module does not amend the retained v0.1 death test.  It replays the same
A1+B1 stream after two disclosed post-hoc repairs: the previously selected v0.6
action readout and the sequential primary-PCHMP-to-CIAV actor-prior handoff.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, cast

from cpswm.contracts import ProjectTwoDatasetSplit, ProjectTwoReplayEpisode
from cpswm.system.evaluation_operations.project_two_action_benchmark import _locations
from cpswm.system.evaluation_operations.project_two_dataset import enforce_project_two_replay_gate
from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_contract import (
    P5ComparisonArm,
    TypedLocationPosterior,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    CLAIM_BOUNDARY as RETAINED_CLAIM_BOUNDARY,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    PROTOCOL_ID as RETAINED_PROTOCOL_ID,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    AMGLocationAdapter,
    DirectP5LocationAdapter,
    LearnedTrainingMaterial,
    LearnedTwoStageLocationAdapter,
    _decode_and_score,
    _episode_schedule_commitment,
    _EpisodeMetric,
    _learned_training_material,
    _packet_for_step,
    _pairwise_signal,
    _summaries,
    _validation_selection,
    verify_matched_consumption,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    _load_config as _load_retained_config,
)
from cpswm.system.prototype_spine import ActionReadout, ActionReadoutConfig
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_adaptive_runtime import AdaptiveAuthorizationPolicy
from cpswm.system.structure_two_production_system import (
    StructureTwoProductionSystem,
    build_production_assembly_manifest,
)

SCHEMA_VERSION: Final = "0.1.0"
PROTOCOL_ID: Final = "structure-two-p5-readout-posthoc-diagnostic@0.1-development"
DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_p5_readout_posthoc_diagnostic_v0_1.json"
)
DEFAULT_OUTPUT: Final = Path(
    "benchmarks/structure_two/structure_two_p5_readout_posthoc_diagnostic_v0_1.json"
)
CLAIM_BOUNDARY: Final = (
    "This test-opened-split post-hoc diagnostic can determine whether wiring the "
    "previously validation-selected v0.6 action readout and repairing the sequential "
    "PCHMP-to-CIAV actor-prior handoff removes the v0.1 uniform owner-habit posterior "
    "and changes typed actions. It cannot overwrite v0.1, constitute a fresh "
    "preregistered death test, issue a positive scientific receipt, pass Task 7/8/9, "
    "validate adaptive routing, establish external validity, authorize ablation, "
    "aggregate SEARCH and PUT_BACK, or narrow Structure Two."
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_SEMANTIC_METRIC_FIELDS: Final = (
    "episode_id",
    "arm",
    "step_count",
    "search_errors",
    "search_error_rate",
    "put_back_errors",
    "put_back_error_rate",
    "normalized_search_regret",
    "schedule_commitment_sha256",
    "full_p5_transition_count",
    "negative_ciav_opceu_closure_count",
    "transition_dependent_no_new_transition_count",
    "all_seven_primary_trace_count",
)


def _semantic_metric(metric: _EpisodeMetric | Mapping[str, Any]) -> dict[str, Any]:
    values = metric.to_dict() if isinstance(metric, _EpisodeMetric) else metric
    return {field: values[field] for field in _SEMANTIC_METRIC_FIELDS}


def selected_v0_6_action_readout() -> ActionReadoutConfig:
    """Return the exact validation-selected v0.6 readout already frozen in the repo."""

    return ActionReadoutConfig(
        readout=ActionReadout.DUAL_TIMESCALE_REVERSIBLE,
        hybrid_alpha_weight=0.0,
        fast_action_weight=0.7,
        surviving_revision_weight=0.2,
        regime_local_weight=0.1,
        fast_owner_mass_floor=0.5,
        owner_mass_floor=0.5,
        recency_half_life=1.0,
    )


class ReadoutCorrectedDirectP5LocationAdapter(DirectP5LocationAdapter):
    """Direct P5 with the previously selected dual-timescale reversible readout."""

    def __init__(self, episode: ProjectTwoReplayEpisode) -> None:
        self.episode = episode
        self.locations = _locations(episode)
        self.system = StructureTwoProductionSystem(
            owner_key=episode.owner_actor_key,
            object_instance_id=episode.steps[0].object_instance_id,
            locations=self.locations,
            authorization_scope_id=content_uuid(
                PROTOCOL_ID,
                {"episode_id": str(episode.episode_id), "scope": "readout-corrected-P5"},
            ),
            action_readout=selected_v0_6_action_readout(),
            adaptive_authorization_policy=AdaptiveAuthorizationPolicy(
                policy_id="structure-two-p5-readout-posthoc-evaluation-only",
                memory_transition_authorized=True,
                privacy_policy_satisfied=True,
                safety_context_authorized=True,
            ),
        )
        self._current = {location: 1.0 / len(self.locations) for location in self.locations}
        self.full_p5_transition_count = 0
        self.negative_ciav_opceu_closure_count = 0
        self.transition_dependent_no_new_transition_count = 0
        self.all_seven_primary_trace_count = 0
        self.owner_habit_posterior_step_count = 0
        self.owner_habit_posterior_nonuniform_step_count = 0
        self.uniform_tie_location = min(self.locations, key=str)
        self.owner_habit_top1_not_uniform_tie_location_step_count = 0
        self._owner_habit_distribution_hashes: set[str] = set()

    def predict_location_posteriors(self, packet: Any) -> TypedLocationPosterior:
        posterior = super().predict_location_posteriors(packet)
        probabilities = tuple(
            item.probability for item in posterior.owner_habit_location_distribution
        )
        self.owner_habit_posterior_step_count += 1
        if max(probabilities) - min(probabilities) > 1e-12:
            self.owner_habit_posterior_nonuniform_step_count += 1
        probability_by_location = {
            item.location_id: item.probability
            for item in posterior.owner_habit_location_distribution
        }
        top_location = min(
            posterior.location_support,
            key=lambda location: (-probability_by_location[location], str(location)),
        )
        if top_location != self.uniform_tie_location:
            self.owner_habit_top1_not_uniform_tie_location_step_count += 1
        self._owner_habit_distribution_hashes.add(content_sha256(probabilities))
        return posterior

    @property
    def owner_habit_unique_distribution_count(self) -> int:
        return len(self._owner_habit_distribution_hashes)


def _evaluate_posthoc_episode(
    dataset: Any,
    episode: ProjectTwoReplayEpisode,
    *,
    learned_model: Any,
    material: LearnedTrainingMaterial,
    learned_smoothing: float,
    amg_parameter: float,
) -> tuple[tuple[_EpisodeMetric, ...], dict[str, Any]]:
    """Run corrected P5 with the unchanged learned and AMG comparison arms."""

    schedule = _episode_schedule_commitment(episode)
    corrected = ReadoutCorrectedDirectP5LocationAdapter(episode)
    learned = LearnedTwoStageLocationAdapter(
        episode,
        model=learned_model,
        location_successes=material.location_successes,
        location_totals=material.location_totals,
        smoothing=learned_smoothing,
    )
    amg = AMGLocationAdapter(episode, parameter=amg_parameter)
    states: tuple[
        ReadoutCorrectedDirectP5LocationAdapter,
        LearnedTwoStageLocationAdapter,
        AMGLocationAdapter,
    ] = (corrected, learned, amg)
    run_id = content_uuid(RETAINED_PROTOCOL_ID, {"episode_id": str(episode.episode_id)})
    truth_envelope = dataset.truth_for(episode.episode_id)
    counters = {arm: {"search": 0, "put_back": 0, "regret": 0.0} for arm in P5ComparisonArm}
    actions: dict[P5ComparisonArm, list[dict[str, Any]]] = {arm: [] for arm in P5ComparisonArm}
    receipts: dict[P5ComparisonArm, list[dict[str, Any]]] = {arm: [] for arm in P5ComparisonArm}
    corrected_put_back_choice_changes_from_v0_1 = 0

    for index, step in enumerate(episode.steps):
        packet = _packet_for_step(episode, step, schedule_commitment_sha256=schedule)
        matched_receipts = tuple(
            state.consume_matched_ciav_packet(packet, step, step_index=index) for state in states
        )
        verify_matched_consumption(matched_receipts)
        truth = truth_envelope.truth_by_step[step.step_id]
        for state, receipt in zip(states, matched_receipts, strict=True):
            posterior = cast(Any, state).predict_location_posteriors(packet)
            search_error, put_back_error, regret, action = _decode_and_score(
                posterior,
                episode=episode,
                step=step,
                step_index=index,
                run_execution_id=run_id,
                truth=truth,
            )
            counters[receipt.arm]["search"] += search_error
            counters[receipt.arm]["put_back"] += put_back_error
            counters[receipt.arm]["regret"] += regret
            actions[receipt.arm].append(action)
            receipts[receipt.arm].append(receipt.model_dump(mode="json"))
            if receipt.arm is P5ComparisonArm.DIRECT_P5:
                # The retained v0.1 posterior was uniform at every step, so
                # the frozen decoder selected the lexicographically smallest
                # location UUID throughout.
                corrected_put_back_choice_changes_from_v0_1 += int(
                    action["put_back_location_id"] != str(corrected.uniform_tie_location)
                )

    output: list[_EpisodeMetric] = []
    for state in states:
        values = counters[state.arm]
        output.append(
            _EpisodeMetric(
                episode_id=episode.episode_id,
                arm=state.arm,
                step_count=len(episode.steps),
                search_errors=int(values["search"]),
                put_back_errors=int(values["put_back"]),
                normalized_search_regret=float(values["regret"]) / len(episode.steps),
                typed_action_chain_sha256=content_sha256(actions[state.arm]),
                ciav_receipt_chain_sha256=content_sha256(receipts[state.arm]),
                schedule_commitment_sha256=schedule,
                full_p5_transition_count=(
                    corrected.full_p5_transition_count
                    if state.arm is P5ComparisonArm.DIRECT_P5
                    else 0
                ),
                negative_ciav_opceu_closure_count=(
                    corrected.negative_ciav_opceu_closure_count
                    if state.arm is P5ComparisonArm.DIRECT_P5
                    else 0
                ),
                transition_dependent_no_new_transition_count=(
                    corrected.transition_dependent_no_new_transition_count
                    if state.arm is P5ComparisonArm.DIRECT_P5
                    else 0
                ),
                all_seven_primary_trace_count=(
                    corrected.all_seven_primary_trace_count
                    if state.arm is P5ComparisonArm.DIRECT_P5
                    else 0
                ),
            )
        )

    diagnostic = {
        "episode_id": str(episode.episode_id),
        "owner_habit_posterior_step_count": corrected.owner_habit_posterior_step_count,
        "owner_habit_posterior_nonuniform_step_count": (
            corrected.owner_habit_posterior_nonuniform_step_count
        ),
        "owner_habit_top1_not_uniform_tie_location_step_count": (
            corrected.owner_habit_top1_not_uniform_tie_location_step_count
        ),
        "owner_habit_unique_distribution_count": (corrected.owner_habit_unique_distribution_count),
        "corrected_put_back_choice_changes_from_v0_1_uniform_tie": (
            corrected_put_back_choice_changes_from_v0_1
        ),
    }
    return tuple(output), diagnostic


def _load_posthoc_config(root: Path) -> dict[str, Any]:
    config = json.loads((root / DEFAULT_CONFIG).read_text(encoding="utf-8"))
    trigger = cast(Mapping[str, Any], config.get("trigger"))
    corrections = cast(Mapping[str, Any], config.get("posthoc_corrections"))
    action_readout = cast(Mapping[str, Any], corrections.get("action_readout"))
    sequential_handoff = cast(Mapping[str, Any], corrections.get("sequential_actor_prior_handoff"))
    disclosure = cast(Mapping[str, Any], config.get("test_reuse_disclosure"))
    if (
        config.get("schema_version") != SCHEMA_VERSION
        or config.get("protocol_id") != PROTOCOL_ID
        or config.get("status")
        != "FROZEN_AFTER_TWO_PREFLIGHT_DIAGNOSES_BEFORE_FULL_POSTHOC_EXECUTION"
        or config.get("claim_boundary") != CLAIM_BOUNDARY
        or trigger.get("discovered_after_test_open") is not True
        or action_readout.get("to") != "dual_timescale_fast_0.7_surviving_0.2_regime_0.1"
        or sequential_handoff.get("from") != "original_transition_actor_prior"
        or sequential_handoff.get("to") != "primary_pchmp_actor_posterior"
        or disclosure.get("same_test_split_reused") is not True
        or disclosure.get("test_split_previously_opened") is not True
        or disclosure.get("confirmatory") is not False
        or disclosure.get("fresh_preregistered_death_test") is not False
        or disclosure.get("may_issue_positive_scientific_receipt") is not False
    ):
        raise ValueError("P5 post-hoc readout diagnostic configuration drifted")
    baseline_path = root / Path(str(trigger["retained_failed_result_path"]))
    if _file_sha256(baseline_path) != trigger.get("retained_failed_result_file_sha256"):
        raise ValueError("retained v0.1 result file hash drifted")
    readout_path = root / Path(str(action_readout["readout_preregistration_path"]))
    if _file_sha256(readout_path) != action_readout.get("readout_preregistration_file_sha256"):
        raise ValueError("v0.6 action-readout preregistration hash drifted")
    return cast(dict[str, Any], config)


def _source_binding(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    trigger = cast(Mapping[str, Any], config["trigger"])
    corrections = cast(Mapping[str, Any], config["posthoc_corrections"])
    action_readout = cast(Mapping[str, Any], corrections["action_readout"])
    paths = {
        "configuration": DEFAULT_CONFIG,
        "execution_module": Path(__file__).resolve().relative_to(root),
        "retained_v0_1_result": Path(str(trigger["retained_failed_result_path"])),
        "retained_v0_1_execution_module": Path(
            "src/cpswm/system/evaluation_operations/structure_two_p5_three_arm_death_test.py"
        ),
        "v0_6_action_readout_preregistration": Path(
            str(action_readout["readout_preregistration_path"])
        ),
    }
    binding: dict[str, Any] = {
        name: {"path": path.as_posix(), "sha256": _file_sha256(root / path)}
        for name, path in paths.items()
    }
    binding["production_assembly_manifest_sha256"] = build_production_assembly_manifest(root)[
        "content_sha256"
    ]
    return binding


def run_p5_readout_posthoc_diagnostic(*, repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    config = _load_posthoc_config(root)
    trigger = cast(Mapping[str, Any], config["trigger"])
    baseline = json.loads(
        (root / Path(str(trigger["retained_failed_result_path"]))).read_text(encoding="utf-8")
    )
    if (
        baseline.get("content_sha256") != trigger["retained_failed_result_content_sha256"]
        or baseline.get("status") != trigger["retained_failed_result_status"]
        or baseline.get("claim_boundary") != RETAINED_CLAIM_BOUNDARY
        or baseline.get("content_sha256") != content_sha256(_unsigned(baseline))
    ):
        raise ValueError("retained v0.1 failure identity drifted")

    retained_config = _load_retained_config(root)
    dataset_config = D0SyntheticReplayExperimentConfig.load(
        root / Path(str(retained_config["dataset_source"]))
    )
    if dataset_config.confirmatory:
        raise ValueError("post-hoc readout diagnostic cannot open confirmatory data")
    dataset = dataset_config.build_adapter().build()
    enforce_project_two_replay_gate(dataset)
    material = _learned_training_material(dataset)
    selection, learned_model, smoothing, amg_parameter = _validation_selection(
        dataset, retained_config, material
    )
    if selection != baseline.get("validation_only_selection"):
        raise RuntimeError("unchanged validation-only selection drifted from retained v0.1")

    metrics: list[_EpisodeMetric] = []
    diagnostics: list[dict[str, Any]] = []
    test = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
    for episode in test:
        episode_metrics, episode_diagnostic = _evaluate_posthoc_episode(
            dataset,
            episode,
            learned_model=learned_model,
            material=material,
            learned_smoothing=smoothing,
            amg_parameter=amg_parameter,
        )
        metrics.extend(episode_metrics)
        diagnostics.append(episode_diagnostic)

    corrected_summaries = _summaries(metrics)
    descriptive_pairwise, descriptive_signal = _pairwise_signal(metrics, retained_config)
    baseline_p5 = cast(Mapping[str, Any], baseline["test_arm_summaries"])[
        P5ComparisonArm.DIRECT_P5.value
    ]
    corrected_p5 = corrected_summaries[P5ComparisonArm.DIRECT_P5.value]
    nonuniform = sum(
        int(item["owner_habit_posterior_nonuniform_step_count"]) for item in diagnostics
    )
    put_back_changes = sum(
        int(item["corrected_put_back_choice_changes_from_v0_1_uniform_tie"]) for item in diagnostics
    )
    posterior_steps = sum(int(item["owner_habit_posterior_step_count"]) for item in diagnostics)
    top1_not_uniform_tie = sum(
        int(item["owner_habit_top1_not_uniform_tie_location_step_count"]) for item in diagnostics
    )
    unique_distributions = sum(
        int(item["owner_habit_unique_distribution_count"]) for item in diagnostics
    )
    p5_metrics = [item for item in metrics if item.arm is P5ComparisonArm.DIRECT_P5]
    readout_degeneracy_removed = nonuniform > 0 and put_back_changes > 0
    status = (
        "POSTHOC_READOUT_DEGENERACY_REMOVED"
        if readout_degeneracy_removed
        else "POSTHOC_READOUT_REMAINS_DEGENERATE"
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "status": status,
        "source_binding": _source_binding(root, config),
        "retained_v0_1": {
            "path": trigger["retained_failed_result_path"],
            "status": baseline["status"],
            "content_sha256": baseline["content_sha256"],
            "overwritten": False,
            "historical_file_and_content_hash_verified": True,
            "live_replay_after_production_fix_claimed": False,
        },
        "test_reuse_disclosure": config["test_reuse_disclosure"],
        "preflight_diagnoses": config["preflight_diagnoses"],
        "posthoc_corrections": config["posthoc_corrections"],
        "held_fixed": config["held_fixed"],
        "data_scope": {
            "dataset_version": dataset.manifest.dataset_version,
            "test_episode_count": len(test),
            "test_step_count": sum(len(episode.steps) for episode in test),
            "confirmatory": False,
            "test_split_previously_opened": True,
        },
        "validation_only_selection": selection,
        "corrected_test_episode_semantic_metrics": [_semantic_metric(item) for item in metrics],
        "corrected_test_arm_summaries": corrected_summaries,
        "corrected_vs_retained_v0_1": {
            "search_error_rate_change": (
                float(corrected_p5["search_error_rate"]) - float(baseline_p5["search_error_rate"])
            ),
            "normalized_search_regret_change": (
                float(corrected_p5["normalized_search_regret"])
                - float(baseline_p5["normalized_search_regret"])
            ),
            "put_back_error_rate_change": (
                float(corrected_p5["put_back_error_rate"])
                - float(baseline_p5["put_back_error_rate"])
            ),
            "search_choice_change_count": 0,
            "put_back_choice_change_count": put_back_changes,
        },
        "readout_diagnostic": {
            "owner_habit_posterior_step_count": posterior_steps,
            "owner_habit_posterior_nonuniform_step_count": nonuniform,
            "owner_habit_top1_not_uniform_tie_location_step_count": top1_not_uniform_tie,
            "sum_of_per_episode_unique_distribution_counts": unique_distributions,
            "readout_degeneracy_removed": readout_degeneracy_removed,
            "per_episode": diagnostics,
        },
        "descriptive_reapplication_of_v0_1_signal_rule": {
            "registered_for_posthoc_run": False,
            "pairwise_episode_results": descriptive_pairwise,
            "signal_gate": descriptive_signal,
        },
        "execution_audit": {
            "exact_three_arm_ciav_receipt_match_established": True,
            "direct_p5_full_transition_count": sum(
                item.full_p5_transition_count for item in p5_metrics
            ),
            "direct_p5_all_seven_primary_trace_count": sum(
                item.all_seven_primary_trace_count for item in p5_metrics
            ),
            "direct_p5_negative_ciav_opceu_closure_count": sum(
                item.negative_ciav_opceu_closure_count for item in p5_metrics
            ),
            "negative_transition_fabrication_count": 0,
            "transition_dependent_explicit_no_new_transition_count": sum(
                item.transition_dependent_no_new_transition_count for item in p5_metrics
            ),
            "truth_visible_to_arms_before_typed_action_commit": False,
        },
        "combined_utility_evaluated": False,
        "fresh_preregistered_death_test": False,
        "positive_scientific_receipt_issued": False,
        "task_7_8_9_passed": False,
        "adaptive_router_validated": False,
        "scientific_superiority_established": False,
        "external_validity_established": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {**payload, "content_sha256": content_sha256(payload)}


def _unsigned(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in payload.items() if key != "content_sha256"}


def verify_p5_readout_posthoc_diagnostic(
    payload: Mapping[str, Any],
    *,
    repository_root: Path,
    fresh_recompute: bool = True,
) -> None:
    if not fresh_recompute:
        raise ValueError("P5 post-hoc artifact verification requires fresh recomputation")
    root = repository_root.resolve()
    config = _load_posthoc_config(root)
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("protocol_id") != PROTOCOL_ID
        or payload.get("status")
        not in {
            "POSTHOC_READOUT_DEGENERACY_REMOVED",
            "POSTHOC_READOUT_REMAINS_DEGENERATE",
        }
        or payload.get("claim_boundary") != CLAIM_BOUNDARY
        or payload.get("content_sha256") != content_sha256(_unsigned(payload))
        or payload.get("source_binding") != _source_binding(root, config)
    ):
        raise ValueError("P5 post-hoc readout result identity, hash, or binding drifted")
    for field in (
        "combined_utility_evaluated",
        "fresh_preregistered_death_test",
        "positive_scientific_receipt_issued",
        "task_7_8_9_passed",
        "adaptive_router_validated",
        "scientific_superiority_established",
        "external_validity_established",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"post-hoc diagnostic promoted unauthorized claim: {field}")
    disclosure = cast(Mapping[str, Any], payload.get("test_reuse_disclosure"))
    retained = cast(Mapping[str, Any], payload.get("retained_v0_1"))
    diagnostic = cast(Mapping[str, Any], payload.get("readout_diagnostic"))
    audit = cast(Mapping[str, Any], payload.get("execution_audit"))
    if (
        disclosure.get("test_split_previously_opened") is not True
        or disclosure.get("fresh_preregistered_death_test") is not False
        or retained.get("overwritten") is not False
        or retained.get("historical_file_and_content_hash_verified") is not True
        or retained.get("live_replay_after_production_fix_claimed") is not False
        or audit.get("exact_three_arm_ciav_receipt_match_established") is not True
        or audit.get("truth_visible_to_arms_before_typed_action_commit") is not False
        or audit.get("negative_transition_fabrication_count") != 0
        or audit.get("direct_p5_full_transition_count")
        != audit.get("direct_p5_all_seven_primary_trace_count")
    ):
        raise ValueError("P5 post-hoc result contains an unsupported execution claim")
    expected_removed = (
        int(diagnostic.get("owner_habit_posterior_nonuniform_step_count", 0)) > 0
        and int(
            cast(Mapping[str, Any], payload["corrected_vs_retained_v0_1"]).get(
                "put_back_choice_change_count", 0
            )
        )
        > 0
    )
    expected_status = (
        "POSTHOC_READOUT_DEGENERACY_REMOVED"
        if expected_removed
        else "POSTHOC_READOUT_REMAINS_DEGENERATE"
    )
    if payload.get("status") != expected_status:
        raise ValueError("P5 post-hoc status differs from retained diagnostics")
    expected = run_p5_readout_posthoc_diagnostic(repository_root=root)
    if dict(payload) != expected:
        raise ValueError("fresh P5 post-hoc readout recomputation disagrees")


__all__ = [
    "CLAIM_BOUNDARY",
    "DEFAULT_CONFIG",
    "DEFAULT_OUTPUT",
    "ReadoutCorrectedDirectP5LocationAdapter",
    "run_p5_readout_posthoc_diagnostic",
    "selected_v0_6_action_readout",
    "verify_p5_readout_posthoc_diagnostic",
]
