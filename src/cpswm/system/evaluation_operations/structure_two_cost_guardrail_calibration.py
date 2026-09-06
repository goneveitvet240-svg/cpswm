"""Development cost/guardrail calibration for Structure Two Route A.

This module does not choose paper-level costs or thresholds.  It converts the
v0.6 paired action rows into a break-even envelope and separately exercises the
existing Hybrid RGRC cache-versus-log-replay check on TRAIN episodes.  External
robot timing, energy, safety and user-cost measurements remain explicit open
bindings.
"""

from __future__ import annotations

import hashlib
import json
import random
from math import isclose
from pathlib import Path
from statistics import mean
from typing import Annotated, Any, Final, Literal
from uuid import UUID

from pydantic import Field, StrictBool, StrictFloat, StrictInt, model_validator

from cpswm.contracts import ContractModel, ProjectTwoDatasetSplit
from cpswm.system.continual.hybrid_event_to_task_loop import (
    HybridFullRerunEquivalenceReceipt,
)

from .project_two_action_benchmark import (
    ProjectTwoActionBenchmarkReport,
    ProjectTwoActionBenchmarkV02,
    ProjectTwoActionMethod,
    _FullProjectTwoMethod,
    _visible_hash,
)
from .project_two_dataset import ProjectTwoReplayDataset
from .project_two_experiment_config import D0SyntheticReplayExperimentConfig

PROTOCOL_ID: Final = "structure-two-cost-guardrail-calibration@0.1"
BOOTSTRAP_REPLICATES: Final = 10_000
BOOTSTRAP_SEED: Final = f"{PROTOCOL_ID}:paired-episode-bootstrap"
DEVELOPMENT_FULL_RERUN_ATOL: Final = 1e-10
PAIRING_REFERENCE: Final = ProjectTwoActionMethod.AMG_MATCHED
PAIRING_CANDIDATE: Final = ProjectTwoActionMethod.PROJECT_TWO
PAPER_BINDINGS_STILL_REQUIRED: Final = (
    "real_robot_put_back_failure_cost",
    "real_robot_container_inspection_cost",
    "real_robot_unfound_target_cost",
    "real_robot_time_energy_safety_privacy_costs",
    "primary_superiority_margin",
    "owner_contamination_upper_bound",
    "recovery_latency_upper_bound",
    "confirmatory_full_rerun_tolerance",
    "independent_custody",
    "faithful_external_baseline_reproduction",
)


class PairedCostGuardrailEpisode(ContractModel):
    episode_id: UUID
    step_count: StrictInt = Field(gt=0)
    reference_minus_candidate_put_back_regret: StrictFloat = Field(allow_inf_nan=False)
    reference_minus_candidate_search_regret: StrictFloat = Field(allow_inf_nan=False)
    reference_minus_candidate_inspected_container_count: StrictFloat = Field(allow_inf_nan=False)
    candidate_minus_reference_contamination_events: StrictFloat = Field(allow_inf_nan=False)
    candidate_minus_reference_recovery_latency: StrictFloat = Field(allow_inf_nan=False)


class BootstrapInterval(ContractModel):
    estimate: StrictFloat = Field(allow_inf_nan=False)
    confidence_interval_95: tuple[
        Annotated[StrictFloat, Field(allow_inf_nan=False)],
        Annotated[StrictFloat, Field(allow_inf_nan=False)],
    ]
    replicates: Literal[10000] = BOOTSTRAP_REPLICATES
    seed: Literal["structure-two-cost-guardrail-calibration@0.1:paired-episode-bootstrap"] = (
        "structure-two-cost-guardrail-calibration@0.1:paired-episode-bootstrap"
    )

    @model_validator(mode="after")
    def _ordered(self) -> BootstrapInterval:
        low, high = self.confidence_interval_95
        if low > high:
            raise ValueError("bootstrap interval is reversed")
        return self


class BreakEvenEnvelope(ContractModel):
    formula: Literal[
        "reference_minus_candidate_net = put_back_cost*put_back_advantage + "
        "inspection_cost*inspected_container_advantage - "
        "contamination_event_cost*contamination_excess"
    ]
    put_back_casewise_equal: StrictBool
    recovery_latency_casewise_equal: StrictBool
    search_strictly_better_episode_count: StrictInt = Field(ge=0)
    search_equal_episode_count: StrictInt = Field(ge=0)
    search_worse_episode_count: StrictInt = Field(ge=0)
    contamination_excess_episode_count: StrictInt = Field(ge=0)
    primary_advantage: BootstrapInterval
    normalized_search_regret_advantage: BootstrapInterval
    inspected_container_advantage: BootstrapInterval
    contamination_excess_events: BootstrapInterval
    maximum_contamination_cost_per_event_in_normalized_search_regret_units: StrictFloat | None = (
        Field(default=None, ge=0.0, allow_inf_nan=False)
    )
    maximum_contamination_cost_per_event_in_inspection_cost_units: StrictFloat | None = Field(
        default=None, ge=0.0, allow_inf_nan=False
    )
    inspection_cost_break_even_ratio: BootstrapInterval | None = None
    conservative_inspection_cost_ratio_from_marginal_intervals: StrictFloat | None = Field(
        default=None, ge=0.0, allow_inf_nan=False
    )
    interpretation: Literal[
        "sensitivity envelope only; no real-world cost or hard threshold selected"
    ] = "sensitivity envelope only; no real-world cost or hard threshold selected"


class TrainFullRerunObservation(ContractModel):
    episode_id: UUID
    registered_location_ids: tuple[UUID, ...] = Field(min_length=2)
    receipt: HybridFullRerunEquivalenceReceipt

    @model_validator(mode="after")
    def _receipt_covers_registered_locations(self) -> TrainFullRerunObservation:
        if len(set(self.registered_location_ids)) != len(self.registered_location_ids):
            raise ValueError("training location catalogue contains duplicates")
        expected = tuple(sorted(self.registered_location_ids, key=str))
        observed = tuple(item.location_id for item in self.receipt.location_checks)
        if observed != expected:
            raise ValueError("full-rerun receipt does not cover the registered locations exactly")
        return self


class CostGuardrailCalibrationReport(ContractModel):
    protocol_id: Literal["structure-two-cost-guardrail-calibration@0.1"] = PROTOCOL_ID
    source_action_report_path: str = Field(min_length=1)
    source_action_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_config_path: str = Field(min_length=1)
    dataset_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_method: Literal["project_two_full_feedback_loop"] = PAIRING_CANDIDATE.value
    reference_method: Literal["damen_hogg_amg_matched_open_world"] = PAIRING_REFERENCE.value
    selected_candidate_parameters: dict[str, float | str]
    paired_holdout_rows: tuple[PairedCostGuardrailEpisode, ...] = Field(min_length=2)
    break_even_envelope: BreakEvenEnvelope
    train_full_rerun_observations: tuple[TrainFullRerunObservation, ...] = Field(min_length=1)
    development_full_rerun_all_equivalent: StrictBool
    development_full_rerun_absolute_tolerance: StrictFloat = Field(
        default=DEVELOPMENT_FULL_RERUN_ATOL,
        ge=DEVELOPMENT_FULL_RERUN_ATOL,
        le=DEVELOPMENT_FULL_RERUN_ATOL,
        allow_inf_nan=False,
    )
    full_rerun_scope: Literal["hybrid_rgrc_cached_sufficient_statistics_vs_append_log_replay"] = (
        "hybrid_rgrc_cached_sufficient_statistics_vs_append_log_replay"
    )
    full_rerun_guardrail_status: Literal["development_train_only_not_confirmatory"] = (
        "development_train_only_not_confirmatory"
    )
    unresolved_paper_bindings: tuple[str, ...] = PAPER_BINDINGS_STILL_REQUIRED
    paper_claim_allowed: Literal[False] = False
    independent_custody_verified: Literal[False] = False

    @model_validator(mode="after")
    def _all_outputs_are_derived(self) -> CostGuardrailCalibrationReport:
        if len({item.episode_id for item in self.paired_holdout_rows}) != len(
            self.paired_holdout_rows
        ):
            raise ValueError("paired holdout rows repeat an episode")
        if len({item.episode_id for item in self.train_full_rerun_observations}) != len(
            self.train_full_rerun_observations
        ):
            raise ValueError("full-rerun observations repeat a training episode")
        if {item.episode_id for item in self.paired_holdout_rows} & {
            item.episode_id for item in self.train_full_rerun_observations
        }:
            raise ValueError("training equivalence and holdout cost rows overlap")
        expected_envelope = _break_even_envelope(self.paired_holdout_rows)
        if self.break_even_envelope != expected_envelope:
            raise ValueError("break-even envelope is not derived from paired holdout rows")
        expected_equivalence = all(
            item.receipt.equivalent for item in self.train_full_rerun_observations
        )
        if self.development_full_rerun_all_equivalent != expected_equivalence:
            raise ValueError("full-rerun summary is not derived from training receipts")
        if any(
            item.receipt.absolute_tolerance != self.development_full_rerun_absolute_tolerance
            for item in self.train_full_rerun_observations
        ):
            raise ValueError("training receipts substituted the development replay tolerance")
        if self.unresolved_paper_bindings != PAPER_BINDINGS_STILL_REQUIRED:
            raise ValueError("paper-level cost or guardrail bindings were erased or substituted")
        return self


def _percentile_interval(values: list[float]) -> tuple[float, float]:
    ordered = sorted(values)
    return (
        ordered[int(0.025 * len(ordered))],
        ordered[min(len(ordered) - 1, int(0.975 * len(ordered)))],
    )


def _bootstrap_summaries(
    rows: tuple[PairedCostGuardrailEpisode, ...],
) -> tuple[
    BootstrapInterval,
    BootstrapInterval,
    BootstrapInterval,
    BootstrapInterval,
    BootstrapInterval | None,
]:
    rng = random.Random(BOOTSTRAP_SEED)
    primary_draws: list[float] = []
    search_draws: list[float] = []
    inspection_draws: list[float] = []
    contamination_draws: list[float] = []
    ratio_draws: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = rng.choices(rows, k=len(rows))
        put_back = mean(item.reference_minus_candidate_put_back_regret for item in sample)
        sampled_search = mean(item.reference_minus_candidate_search_regret for item in sample)
        sampled_inspections = mean(
            item.reference_minus_candidate_inspected_container_count for item in sample
        )
        sampled_contamination = mean(
            item.candidate_minus_reference_contamination_events for item in sample
        )
        primary_draws.append(put_back + sampled_search)
        search_draws.append(sampled_search)
        inspection_draws.append(sampled_inspections)
        contamination_draws.append(sampled_contamination)
        if sampled_contamination > 0.0:
            ratio_draws.append(sampled_inspections / sampled_contamination)

    primary_values = [
        item.reference_minus_candidate_put_back_regret
        + item.reference_minus_candidate_search_regret
        for item in rows
    ]
    search_values = [item.reference_minus_candidate_search_regret for item in rows]
    inspection_values = [item.reference_minus_candidate_inspected_container_count for item in rows]
    contamination_values = [item.candidate_minus_reference_contamination_events for item in rows]
    primary = BootstrapInterval(
        estimate=mean(primary_values),
        confidence_interval_95=_percentile_interval(primary_draws),
    )
    search = BootstrapInterval(
        estimate=mean(search_values),
        confidence_interval_95=_percentile_interval(search_draws),
    )
    inspections = BootstrapInterval(
        estimate=mean(inspection_values),
        confidence_interval_95=_percentile_interval(inspection_draws),
    )
    contamination = BootstrapInterval(
        estimate=mean(contamination_values),
        confidence_interval_95=_percentile_interval(contamination_draws),
    )
    ratio = None
    if ratio_draws and contamination.estimate > 0.0 and inspections.estimate > 0.0:
        ratio = BootstrapInterval(
            estimate=inspections.estimate / contamination.estimate,
            confidence_interval_95=_percentile_interval(ratio_draws),
        )
    return primary, search, inspections, contamination, ratio


def _break_even_envelope(
    rows: tuple[PairedCostGuardrailEpisode, ...],
) -> BreakEvenEnvelope:
    primary, search, inspections, contamination, ratio = _bootstrap_summaries(rows)
    normalized_maximum = (
        max(0.0, search.estimate / contamination.estimate) if contamination.estimate > 0.0 else None
    )
    inspection_maximum = (
        max(0.0, inspections.estimate / contamination.estimate)
        if contamination.estimate > 0.0
        else None
    )
    conservative = None
    contamination_high = contamination.confidence_interval_95[1]
    if contamination_high > 0.0:
        conservative = max(0.0, inspections.confidence_interval_95[0] / contamination_high)
    return BreakEvenEnvelope(
        formula=(
            "reference_minus_candidate_net = put_back_cost*put_back_advantage + "
            "inspection_cost*inspected_container_advantage - "
            "contamination_event_cost*contamination_excess"
        ),
        put_back_casewise_equal=all(
            isclose(
                item.reference_minus_candidate_put_back_regret,
                0.0,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            for item in rows
        ),
        recovery_latency_casewise_equal=all(
            isclose(
                item.candidate_minus_reference_recovery_latency,
                0.0,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            for item in rows
        ),
        search_strictly_better_episode_count=sum(
            item.reference_minus_candidate_inspected_container_count > 1e-12 for item in rows
        ),
        search_equal_episode_count=sum(
            abs(item.reference_minus_candidate_inspected_container_count) <= 1e-12 for item in rows
        ),
        search_worse_episode_count=sum(
            item.reference_minus_candidate_inspected_container_count < -1e-12 for item in rows
        ),
        contamination_excess_episode_count=sum(
            item.candidate_minus_reference_contamination_events > 1e-12 for item in rows
        ),
        primary_advantage=primary,
        normalized_search_regret_advantage=search,
        inspected_container_advantage=inspections,
        contamination_excess_events=contamination,
        maximum_contamination_cost_per_event_in_normalized_search_regret_units=(normalized_maximum),
        maximum_contamination_cost_per_event_in_inspection_cost_units=inspection_maximum,
        inspection_cost_break_even_ratio=ratio,
        conservative_inspection_cost_ratio_from_marginal_intervals=conservative,
    )


def _paired_rows(
    report: ProjectTwoActionBenchmarkReport,
) -> tuple[PairedCostGuardrailEpisode, ...]:
    cases = {(item.episode_id, item.method): item for item in report.case_metrics}
    rows = []
    for episode_id in report.sealed_test_episode_ids:
        candidate = cases[(episode_id, PAIRING_CANDIDATE)]
        reference = cases[(episode_id, PAIRING_REFERENCE)]
        if candidate.step_count != reference.step_count:
            raise ValueError("paired methods have different step counts")
        rows.append(
            PairedCostGuardrailEpisode(
                episode_id=episode_id,
                step_count=candidate.step_count,
                reference_minus_candidate_put_back_regret=(
                    reference.cumulative_put_back_regret - candidate.cumulative_put_back_regret
                ),
                reference_minus_candidate_search_regret=(
                    reference.cumulative_search_regret - candidate.cumulative_search_regret
                ),
                reference_minus_candidate_inspected_container_count=(
                    reference.mean_search_path_length - candidate.mean_search_path_length
                )
                * candidate.step_count,
                candidate_minus_reference_contamination_events=(
                    candidate.owner_habit_contamination - reference.owner_habit_contamination
                )
                * candidate.step_count,
                candidate_minus_reference_recovery_latency=(
                    candidate.late_feedback_recovery_latency
                    - reference.late_feedback_recovery_latency
                ),
            )
        )
    return tuple(rows)


def _train_full_rerun_observations(
    dataset: ProjectTwoReplayDataset,
    selected_parameters: dict[str, float | str],
) -> tuple[TrainFullRerunObservation, ...]:
    evaluator = ProjectTwoActionBenchmarkV02()
    readout = evaluator._readout_from_params(selected_parameters)
    observations = []
    for episode in dataset.visible_episodes(ProjectTwoDatasetSplit.TRAIN):
        state = _FullProjectTwoMethod(
            episode,
            owner_threshold=float(selected_parameters["owner_threshold"]),
            action_readout=readout,
        )
        for step in episode.steps:
            state.observe(step)
            state.predict()
            state.feedback(step)
        observations.append(
            TrainFullRerunObservation(
                episode_id=episode.episode_id,
                registered_location_ids=state.locations,
                receipt=state.spine.verify_hybrid_full_rerun_equivalence(),
            )
        )
    if not observations:
        raise ValueError("cost/guardrail calibration requires a training split")
    return tuple(observations)


def build_cost_guardrail_calibration(
    *, source_action_report_path: Path, dataset_config_path: Path
) -> CostGuardrailCalibrationReport:
    """Derive the sensitivity envelope and TRAIN-only replay receipts."""

    action_path = source_action_report_path.resolve()
    config_path = dataset_config_path.resolve()
    action_bytes = action_path.read_bytes()
    action_sha256 = hashlib.sha256(action_bytes).hexdigest()
    payload: dict[str, Any] = json.loads(action_bytes)
    benchmark_payload = payload.get("benchmark")
    if not isinstance(benchmark_payload, dict):
        raise ValueError("source action artifact does not contain a benchmark report")
    action_report = ProjectTwoActionBenchmarkReport.model_validate(benchmark_payload)
    config_bytes = config_path.read_bytes()
    config_sha256 = hashlib.sha256(config_bytes).hexdigest()
    config = D0SyntheticReplayExperimentConfig.model_validate(json.loads(config_bytes))
    experiment_config = payload.get("experiment_config")
    if not isinstance(experiment_config, dict):
        raise ValueError("source action artifact does not bind its experiment config")
    if experiment_config.get("sha256") != config_sha256:
        raise ValueError("supplied dataset config is not the action artifact's bound config")
    registered_path = experiment_config.get("path")
    if not isinstance(registered_path, str) or Path(registered_path).resolve() != config_path:
        raise ValueError("supplied dataset config path differs from the action artifact binding")
    if experiment_config.get("confirmatory") != config.confirmatory:
        raise ValueError("action artifact confirmatory status disagrees with its dataset config")
    if experiment_config.get("evidence_stage") != config.evidence_stage:
        raise ValueError("action artifact evidence stage disagrees with its dataset config")
    if action_report.dataset_version != config.dataset_version:
        raise ValueError("action report and dataset config versions disagree")
    dataset = config.build_adapter().build()
    split_ids = {
        split: tuple(item.episode_id for item in dataset.visible_episodes(split))
        for split in ProjectTwoDatasetSplit
    }
    if split_ids[ProjectTwoDatasetSplit.TRAIN] != action_report.train_episode_ids:
        raise ValueError("dataset config does not reproduce the report's training episodes")
    if split_ids[ProjectTwoDatasetSplit.VALIDATION] != action_report.validation_episode_ids:
        raise ValueError("dataset config does not reproduce the report's validation episodes")
    if split_ids[ProjectTwoDatasetSplit.TEST] != action_report.sealed_test_episode_ids:
        raise ValueError("dataset config does not reproduce the report's holdout episodes")
    evaluated = (
        *dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION),
        *dataset.visible_episodes(ProjectTwoDatasetSplit.TEST),
    )
    if {
        episode.episode_id: _visible_hash(episode) for episode in evaluated
    } != action_report.fairness_visible_hashes:
        raise ValueError("dataset config does not reproduce the report's visible episode hashes")
    selection = next(item for item in action_report.tuning if item.method is PAIRING_CANDIDATE)
    selected = dict(selection.selected_parameters)
    train_observations = _train_full_rerun_observations(dataset, selected)
    if tuple(item.episode_id for item in train_observations) != action_report.train_episode_ids:
        raise ValueError("full-rerun observations do not cover the report's training split")
    rows = _paired_rows(action_report)
    return CostGuardrailCalibrationReport(
        source_action_report_path=str(action_path),
        source_action_report_sha256=action_sha256,
        dataset_config_path=str(config_path),
        dataset_config_sha256=config_sha256,
        selected_candidate_parameters=selected,
        paired_holdout_rows=rows,
        break_even_envelope=_break_even_envelope(rows),
        train_full_rerun_observations=train_observations,
        development_full_rerun_all_equivalent=all(
            item.receipt.equivalent for item in train_observations
        ),
    )


def verify_cost_guardrail_calibration_artifact(
    artifact_path: Path,
) -> CostGuardrailCalibrationReport:
    """Recompute results from bound dependencies and reject substitutions.

    Verification reruns only the TRAIN Hybrid RGRC checks. Paired holdout rows
    are re-derived from the source action artifact; the holdout is not rerun.
    """

    payload: dict[str, Any] = json.loads(artifact_path.resolve().read_text(encoding="utf-8"))
    calibration_payload = payload.get("calibration")
    if not isinstance(calibration_payload, dict):
        raise ValueError("cost/guardrail artifact does not contain a calibration report")
    reported = CostGuardrailCalibrationReport.model_validate(calibration_payload)
    expected = build_cost_guardrail_calibration(
        source_action_report_path=Path(reported.source_action_report_path),
        dataset_config_path=Path(reported.dataset_config_path),
    )
    if reported != expected:
        raise ValueError("cost/guardrail artifact differs from dependency-derived recomputation")
    return reported


__all__ = [
    "BOOTSTRAP_REPLICATES",
    "BOOTSTRAP_SEED",
    "DEVELOPMENT_FULL_RERUN_ATOL",
    "PAPER_BINDINGS_STILL_REQUIRED",
    "PROTOCOL_ID",
    "BootstrapInterval",
    "BreakEvenEnvelope",
    "CostGuardrailCalibrationReport",
    "PairedCostGuardrailEpisode",
    "TrainFullRerunObservation",
    "build_cost_guardrail_calibration",
    "verify_cost_guardrail_calibration_artifact",
]
