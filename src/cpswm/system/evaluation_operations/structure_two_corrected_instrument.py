"""Corrected validation-only evaluation instrument for Structure Two.

This module is deliberately additive.  It does not edit or reinterpret the
sealed v0.1 strongest-neighbor artifact.  It repairs four measurement faults:

* search and put-back use separate action readouts;
* physical verification is a Bayesian likelihood update, not a hard reset;
* internal ledger revisions are not priced as environmental rollbacks;
* action-distinguishability and verification-saturation are validity gates.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from statistics import mean
from typing import Any, cast
from uuid import UUID

from cpswm.contracts import ProjectTwoDatasetSplit, ProjectTwoReplayEpisode, ProjectTwoReplayStep
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ActionCaseMetric,
    ProjectTwoActionBenchmarkV02,
    _FullProjectTwoMethod,
    _Prediction,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import _normalize
from cpswm.system.evaluation_operations.structure_two_sequential_gate import (  # type: ignore[attr-defined]
    _action_readout,
)
from cpswm.system.evaluation_operations.structure_two_strongest_neighbor_gate import (
    PROTOCOL_ID as LEGACY_PROTOCOL_ID,
)
from cpswm.system.evaluation_operations.structure_two_strongest_neighbor_gate import (  # type: ignore[attr-defined]
    PUBLISHED_NEIGHBOR_ARMS,
    NeighborArm,
    NeighborFamily,
    _dataset,
    _file_sha256,
    _NeighborMemoryState,
    _rank_distribution,
    _wrap_visible_family,
    load_frozen_neighbor_design,
)
from cpswm.system.evaluation_operations.structure_two_strongest_neighbor_gate import (
    _state_for_arm as _legacy_state_for_arm,
)
from cpswm.system.reproducibility import content_sha256

LEGACY_CORRECTED_PROTOCOL_ID = "structure-two-corrected-evaluation-instrument@0.2"
PROTOCOL_ID = "structure-two-corrected-evaluation-instrument@0.3"
LEGACY_MANIFEST = Path(
    "configs/project_two_experiments/structure_two_corrected_instrument_manifest_v0_2.json"
)
DEFAULT_MANIFEST = Path(
    "configs/project_two_experiments/structure_two_corrected_instrument_manifest_v0_3.json"
)
DEFAULT_OUTPUT = Path(
    "artifacts/project_two_v04_development/structure_two_corrected_instrument_v0_3.json"
)


@dataclass(frozen=True, slots=True)
class CorrectedInstrumentDesign:
    source_manifest_path: Path
    source_report_path: Path
    source_manifest_file_sha256: str
    source_report_file_sha256: str
    source_report_content_sha256: str
    source_gate_file_sha256: str
    validation_seeds: tuple[int, ...]
    max_steps: int
    max_physical_verifications_per_episode: int
    selected_parameters: Mapping[NeighborArm, Any]
    prior_floor: float
    minimum_mean_pairwise_disagreement: float
    minimum_differentiated_episode_fraction: float
    maximum_care_budget_saturation_rate: float
    eligible_overall_comparators: tuple[NeighborArm, ...]
    manifest_file_sha256: str


@dataclass(frozen=True, slots=True)
class ExternalActionExecutionReceipt:
    """Evidence that a model-selected environmental action was actually executed."""

    action_execution_id: str
    consumed_revision_id: str
    externally_executed: bool
    rollback_required: bool


@dataclass(frozen=True, slots=True)
class ExternalRepairPricing:
    charged_unique_rollback_count: int
    external_repair_cost: float
    ignored_internal_or_nonexecuted_count: int
    invalid_receipt_count: int


def audit_legacy_corrected_instrument_v0_2(repository_root: Path) -> dict[str, object]:
    """Report the unrecoverable legacy-source binding without rewriting v0.2."""

    manifest_path = repository_root / LEGACY_MANIFEST
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != LEGACY_CORRECTED_PROTOCOL_ID:
        raise ValueError("legacy corrected-instrument manifest protocol mismatch")
    source_manifest = repository_root / str(payload["source_manifest_path"])
    source_report = repository_root / str(payload["source_report_path"])
    source_gate = repository_root / (
        "src/cpswm/system/evaluation_operations/structure_two_strongest_neighbor_gate.py"
    )
    report_payload = json.loads(source_report.read_text(encoding="utf-8"))
    immutable_artifacts_match = (
        _file_sha256(source_manifest) == payload["source_manifest_file_sha256"]
        and _file_sha256(source_report) == payload["source_report_file_sha256"]
        and report_payload.get("content_sha256") == payload["source_report_content_sha256"]
    )
    expected_source = str(payload["source_gate_file_sha256"])
    current_source = _file_sha256(source_gate)
    source_recoverable = current_source == expected_source
    return {
        "protocol": "structure-two-corrected-instrument-legacy-audit@0.1",
        "audited_protocol": LEGACY_CORRECTED_PROTOCOL_ID,
        "status": (
            "LEGACY_SOURCE_VERIFIED"
            if source_recoverable
            else "BLOCKED_LEGACY_SOURCE_UNRECOVERABLE"
        ),
        "immutable_manifest_and_report_match": immutable_artifacts_match,
        "legacy_source_expected_sha256": expected_source,
        "current_source_sha256": current_source,
        "legacy_source_recoverable": source_recoverable,
        "historical_result_recomputed": False,
        "historical_evidence_rewritten": False,
    }


@dataclass(slots=True)
class CorrectedReading:
    family_id: str
    episode_id: str
    arm: NeighborArm
    metric: ActionCaseMetric
    information_cost: float
    external_repair_pricing: ExternalRepairPricing
    internal_operation_counts: Mapping[str, int]
    axis_consumption_counts: Mapping[str, int]
    verification_count: int
    bayesian_verification_receipts: tuple[Mapping[str, Any], ...]
    action_trace: tuple[tuple[str, str], ...]
    search_pin_check_count: int
    search_pin_violation_count: int
    search_pin_change_count: int
    truth_isolation: bool
    consumed_visible_stream_hash: str
    actual_action_cost: float

    @property
    def raw_action_regret_per_step(self) -> float:
        return float(self.metric.cumulative_action_regret / max(1, self.metric.step_count))

    @property
    def net_environment_regret_per_step(self) -> float:
        numerator = (
            self.actual_action_cost * self.metric.cumulative_action_regret
            + self.information_cost
            + self.external_repair_pricing.external_repair_cost
        )
        return float(numerator / max(1, self.metric.step_count))


def bayesian_categorical_update(
    prior: Mapping[UUID, float],
    *,
    observed: UUID,
    reliability: float,
    prior_floor: float,
) -> dict[UUID, float]:
    """Apply a categorical observation likelihood to the incoming prior."""

    if not 0.0 < reliability <= 1.0:
        raise ValueError("verification reliability must be in (0, 1]")
    if prior_floor <= 0.0:
        raise ValueError("prior floor must be positive")
    keys = set(prior) | {observed}
    if len(keys) == 1:
        return {observed: 1.0}
    residual_likelihood = (1.0 - reliability) / (len(keys) - 1)
    unnormalized = {
        key: max(prior_floor, float(prior.get(key, 0.0)))
        * (reliability if key == observed else residual_likelihood)
        for key in keys
    }
    return {key: float(value) for key, value in _normalize(unnormalized).items()}


def price_external_repairs(
    receipts: Iterable[ExternalActionExecutionReceipt | Mapping[str, Any]],
    *,
    repair_cost: float,
) -> ExternalRepairPricing:
    """Price only unique, externally executed actions that require rollback."""

    charged: set[str] = set()
    ignored = 0
    invalid = 0
    for raw in receipts:
        if isinstance(raw, ExternalActionExecutionReceipt):
            receipt = raw
        else:
            try:
                receipt = ExternalActionExecutionReceipt(
                    action_execution_id=str(raw["action_execution_id"]),
                    consumed_revision_id=str(raw["consumed_revision_id"]),
                    externally_executed=bool(raw["externally_executed"]),
                    rollback_required=bool(raw["rollback_required"]),
                )
            except (KeyError, TypeError, ValueError):
                invalid += 1
                continue
        if not receipt.action_execution_id or not receipt.consumed_revision_id:
            invalid += 1
            continue
        if not receipt.externally_executed or not receipt.rollback_required:
            ignored += 1
            continue
        charged.add(receipt.action_execution_id)
    return ExternalRepairPricing(
        charged_unique_rollback_count=len(charged),
        external_repair_cost=float(repair_cost * len(charged)),
        ignored_internal_or_nonexecuted_count=ignored,
        invalid_receipt_count=invalid,
    )


class _BayesianNeighborMemoryState(_NeighborMemoryState):
    """The legacy memory policy with only the verifier update law corrected."""

    def __init__(self, *args: Any, prior_floor: float, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._prior_floor = prior_floor
        self.bayesian_verification_receipts: list[dict[str, Any]] = []

    def _physical_verification_distribution(
        self,
        distribution: Mapping[UUID, float],
        step: ProjectTwoReplayStep,
    ) -> dict[UUID, float]:
        # Truth is read only after the visible policy selected VERIFY, matching
        # the legacy intervention boundary.  The deterministic draw token stays
        # unchanged so only the update law differs.
        truth = self._dataset.truth_for(self._episode.episode_id).truth_by_step[step.step_id]
        target = truth.true_owner_habit_location
        alternatives = tuple(
            location for location in _rank_distribution(distribution) if location != target
        )
        token = f"{LEGACY_PROTOCOL_ID}:{self._episode.episode_id}:{step.step_id}:physical-verify"
        draw = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big") / 2**64
        observed = (
            target
            if draw <= self._family.physical_verification_reliability or not alternatives
            else alternatives[0]
        )
        posterior = bayesian_categorical_update(
            distribution,
            observed=observed,
            reliability=self._family.physical_verification_reliability,
            prior_floor=self._prior_floor,
        )
        keys = set(distribution) | {observed}
        likelihood_only = _normalize(
            {
                key: (
                    self._family.physical_verification_reliability
                    if key == observed
                    else (1.0 - self._family.physical_verification_reliability)
                    / max(1, len(keys) - 1)
                )
                for key in keys
            }
        )
        self.bayesian_verification_receipts.append(
            {
                "step_id_hash": content_sha256(str(step.step_id)),
                "prior_hash": content_sha256(
                    sorted((str(key), float(value)) for key, value in distribution.items())
                ),
                "observed_location_hash": content_sha256(str(observed)),
                "posterior_hash": content_sha256(
                    sorted((str(key), float(value)) for key, value in posterior.items())
                ),
                "normalized": abs(sum(posterior.values()) - 1.0) <= 1e-9,
                "prior_used": True,
                "posterior_differs_from_likelihood_only": any(
                    abs(posterior.get(key, 0.0) - likelihood_only.get(key, 0.0)) > 1e-9
                    for key in keys
                ),
                "truth_read_before_action_selection": False,
                "truth_read_after_action_selection": True,
            }
        )
        return posterior


class _LastObservedSearchPinState:
    """Pin search to visible recency while leaving put-back untouched."""

    def __init__(self, state: Any) -> None:
        self._state = state
        self._last_observed_location: UUID | None = None
        self.action_trace: list[tuple[str, str]] = []
        self.search_pin_check_count = 0
        self.search_pin_violation_count = 0
        self.search_pin_change_count = 0

    def observe(self, step: ProjectTwoReplayStep) -> None:
        if step.after is not None and step.after.detected_location_id is not None:
            self._last_observed_location = step.after.detected_location_id
        self._state.observe(step)

    def predict(self) -> _Prediction:
        native = cast(_Prediction, self._state.predict())
        if self._last_observed_location is None:
            corrected = native
        else:
            last = self._last_observed_location
            order = (last, *tuple(item for item in native.search_order if item != last))
            corrected = _Prediction(
                put_back=native.put_back,
                search_order=order,
                unknown_probability=native.unknown_probability,
            )
            self.search_pin_check_count += 1
            self.search_pin_violation_count += corrected.search_order[0] != last
            self.search_pin_change_count += native.search_order[0] != last
        self.action_trace.append((str(corrected.put_back), str(corrected.search_order[0])))
        return corrected

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        self._state.feedback(step)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._state, name)


def load_corrected_instrument_design(
    manifest_path: Path,
    *,
    repository_root: Path,
) -> CorrectedInstrumentDesign:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("corrected-instrument manifest protocol mismatch")
    if payload.get("sealed_holdout_opened") is not False:
        raise ValueError("corrected instrument must remain validation-only")
    if payload.get("current_source_rebound") is not True:
        raise ValueError("corrected instrument current-source rebound is not declared")
    if payload.get("legacy_v0_1_source_preservation_claim") is not False:
        raise ValueError("corrected instrument must not claim unavailable legacy-source custody")
    source_manifest_path = Path(str(payload["source_manifest_path"]))
    source_report_path = Path(str(payload["source_report_path"]))
    source_manifest = repository_root / source_manifest_path
    source_report = repository_root / source_report_path
    source_gate = repository_root / (
        "src/cpswm/system/evaluation_operations/structure_two_strongest_neighbor_gate.py"
    )
    expected_files = {
        source_manifest: str(payload["source_manifest_file_sha256"]),
        source_report: str(payload["source_report_file_sha256"]),
        source_gate: str(payload["source_gate_file_sha256"]),
    }
    for path, expected in expected_files.items():
        if _file_sha256(path) != expected:
            raise ValueError(f"corrected-instrument v0.3 source binding mismatch: {path}")
    source_report_payload = json.loads(source_report.read_text(encoding="utf-8"))
    if source_report_payload.get("content_sha256") != payload["source_report_content_sha256"]:
        raise ValueError("legacy v0.1 report content binding mismatch")
    source_design = load_frozen_neighbor_design(source_manifest)
    validation_seeds = tuple(int(seed) for seed in payload["validation_seeds"])
    if validation_seeds != source_design.validation_seeds:
        raise ValueError("corrected instrument must reuse frozen validation seeds")
    selected = {NeighborArm(key): value for key, value in payload["selected_parameters"].items()}
    if set(selected) != set(NeighborArm):
        raise ValueError("corrected instrument requires one frozen parameter per arm")
    thresholds = payload["validity_thresholds"]
    verification = payload["physical_verification_update"]
    return CorrectedInstrumentDesign(
        source_manifest_path=source_manifest_path,
        source_report_path=source_report_path,
        source_manifest_file_sha256=str(payload["source_manifest_file_sha256"]),
        source_report_file_sha256=str(payload["source_report_file_sha256"]),
        source_report_content_sha256=str(payload["source_report_content_sha256"]),
        source_gate_file_sha256=str(payload["source_gate_file_sha256"]),
        validation_seeds=validation_seeds,
        max_steps=int(payload["max_steps"]),
        max_physical_verifications_per_episode=int(
            payload["max_physical_verifications_per_episode"]
        ),
        selected_parameters=selected,
        prior_floor=float(verification["prior_floor"]),
        minimum_mean_pairwise_disagreement=float(
            thresholds["minimum_mean_published_pairwise_action_disagreement"]
        ),
        minimum_differentiated_episode_fraction=float(
            thresholds["minimum_differentiated_episode_fraction"]
        ),
        maximum_care_budget_saturation_rate=float(
            thresholds["maximum_care_full_verification_budget_saturation_rate"]
        ),
        eligible_overall_comparators=tuple(
            NeighborArm(item) for item in payload["eligible_overall_comparators"]
        ),
        manifest_file_sha256=_file_sha256(manifest_path),
    )


def _corrected_state_for_arm(
    dataset: ProjectTwoReplayDataset,
    episode: ProjectTwoReplayEpisode,
    family: NeighborFamily,
    arm: NeighborArm,
    parameter: Any,
    *,
    max_physical_verifications: int,
    prior_floor: float,
) -> Any:
    memory_arms = {
        NeighborArm.ACTIVE_DREAMING,
        NeighborArm.AUTO_DREAMER,
        NeighborArm.TRUSTMEM,
        NeighborArm.BRAINCTL,
        NeighborArm.CARE_NO_ACTION_REGRET,
        NeighborArm.CARE_WM,
    }
    if arm in memory_arms:
        base = _FullProjectTwoMethod(
            episode,
            owner_threshold=0.4,
            action_readout=_action_readout(),
        )
        state = _BayesianNeighborMemoryState(
            base,
            episode,
            dataset,
            family=family,
            arm=arm,
            parameter=parameter,
            max_physical_verifications=max_physical_verifications,
            prior_floor=prior_floor,
        )
        state = _wrap_visible_family(state, episode, family)
    else:
        state = _legacy_state_for_arm(
            dataset,
            episode,
            family,
            arm,
            parameter,
            max_physical_verifications=max_physical_verifications,
        )
    # The oracle remains a truth upper bound.  Applying a visible recency rule
    # to it would stop it from being an oracle and corrupt the guardrail.
    return state if arm is NeighborArm.ORACLE else _LastObservedSearchPinState(state)


def _evaluate(
    evaluator: ProjectTwoActionBenchmarkV02,
    dataset: ProjectTwoReplayDataset,
    episode: ProjectTwoReplayEpisode,
    family: NeighborFamily,
    arm: NeighborArm,
    parameter: Any,
    *,
    design: CorrectedInstrumentDesign,
) -> CorrectedReading:
    state = _corrected_state_for_arm(
        dataset,
        episode,
        family,
        arm,
        parameter,
        max_physical_verifications=design.max_physical_verifications_per_episode,
        prior_floor=design.prior_floor,
    )
    metric = evaluator.evaluate_custom_state(
        dataset,
        episode,
        state,
        prediction_location_scope=(
            "oracle_evaluator_truth" if arm is NeighborArm.ORACLE else "model_visible"
        ),
    )
    pricing = price_external_repairs(
        cast(Iterable[Mapping[str, Any]], getattr(state, "external_action_execution_receipts", ())),
        repair_cost=family.repair_cost,
    )
    decision_receipts = tuple(getattr(state, "decision_receipts", ()))
    truth_isolation = all(
        receipt.get("truth_read_before_action_selection") is False for receipt in decision_receipts
    )
    if arm not in {NeighborArm.CARE_WM, NeighborArm.ORACLE}:
        truth_isolation = truth_isolation and all(
            receipt.get("truth_read_after_action_selection") is False
            for receipt in decision_receipts
        )
    if arm is NeighborArm.ORACLE:
        action_trace: tuple[tuple[str, str], ...] = ()
    else:
        action_trace = tuple(getattr(state, "action_trace", ()))
    return CorrectedReading(
        family_id=family.family_id,
        episode_id=str(episode.episode_id),
        arm=arm,
        metric=metric,
        information_cost=float(getattr(state, "verification_cost", 0.0)),
        external_repair_pricing=pricing,
        internal_operation_counts=dict(getattr(state, "ledger_operation_counts", {})),
        axis_consumption_counts=dict(getattr(state, "axis_consumption_counts", {})),
        verification_count=int(getattr(state, "verification_count", 0)),
        bayesian_verification_receipts=tuple(getattr(state, "bayesian_verification_receipts", ())),
        action_trace=action_trace,
        search_pin_check_count=int(getattr(state, "search_pin_check_count", 0)),
        search_pin_violation_count=int(getattr(state, "search_pin_violation_count", 0)),
        search_pin_change_count=int(getattr(state, "search_pin_change_count", 0)),
        truth_isolation=truth_isolation,
        consumed_visible_stream_hash=str(getattr(state, "consumed_visible_stream_hash", "")),
        actual_action_cost=family.actual_action_cost,
    )


def _reading_summary(readings: Sequence[CorrectedReading]) -> dict[str, float]:
    return {
        "raw_action_regret_per_step": mean(item.raw_action_regret_per_step for item in readings),
        "net_environment_regret_per_step": mean(
            item.net_environment_regret_per_step for item in readings
        ),
        "put_back_error_rate": mean(item.metric.put_back_error_rate for item in readings),
        "search_success_rate": mean(item.metric.search_success_rate for item in readings),
        "mean_search_path_length": mean(item.metric.mean_search_path_length for item in readings),
        "information_cost_per_episode": mean(item.information_cost for item in readings),
        "external_repair_cost_per_episode": mean(
            item.external_repair_pricing.external_repair_cost for item in readings
        ),
        "internal_retract_count": float(
            sum(item.internal_operation_counts.get("retract", 0) for item in readings)
        ),
        "internal_corrected_revision_count": float(
            sum(item.internal_operation_counts.get("corrected_revision", 0) for item in readings)
        ),
        "physical_verification_count": float(sum(item.verification_count for item in readings)),
        "search_pin_change_count": float(sum(item.search_pin_change_count for item in readings)),
    }


def published_action_distinguishability(
    readings_by_arm: Mapping[NeighborArm, Sequence[CorrectedReading]],
) -> dict[str, Any]:
    published = tuple(sorted(PUBLISHED_NEIGHBOR_ARMS, key=lambda item: item.value))
    pairwise: dict[str, float] = {}
    peer_nonzero = dict.fromkeys((arm.value for arm in published), False)
    for left, right in combinations(published, 2):
        differences = total = 0
        for left_reading, right_reading in zip(
            readings_by_arm[left], readings_by_arm[right], strict=True
        ):
            if len(left_reading.action_trace) != len(right_reading.action_trace):
                raise ValueError("published action traces have unequal lengths")
            total += len(left_reading.action_trace)
            differences += sum(
                left_action != right_action
                for left_action, right_action in zip(
                    left_reading.action_trace,
                    right_reading.action_trace,
                    strict=True,
                )
            )
        rate = float(differences / max(1, total))
        pairwise[f"{left.value}__vs__{right.value}"] = rate
        if rate > 0.0:
            peer_nonzero[left.value] = True
            peer_nonzero[right.value] = True
    differentiated = 0
    unique_counts: list[int] = []
    for index in range(len(readings_by_arm[published[0]])):
        unique_count = len({readings_by_arm[arm][index].action_trace for arm in published})
        unique_counts.append(unique_count)
        differentiated += unique_count > 1
    return {
        "pairwise_action_disagreement_rates": pairwise,
        "mean_pairwise_action_disagreement": mean(pairwise.values()),
        "differentiated_episode_fraction": float(differentiated / max(1, len(unique_counts))),
        "mean_unique_published_action_traces_per_episode": mean(unique_counts),
        "every_published_arm_differs_from_at_least_one_peer": all(peer_nonzero.values()),
        "per_arm_has_nonzero_peer_disagreement": peer_nonzero,
    }


def run_structure_two_corrected_instrument(*, repository_root: Path) -> dict[str, Any]:
    manifest_path = repository_root / DEFAULT_MANIFEST
    design = load_corrected_instrument_design(
        manifest_path,
        repository_root=repository_root,
    )
    source_design = load_frozen_neighbor_design(repository_root / design.source_manifest_path)
    evaluator = ProjectTwoActionBenchmarkV02()
    readings: dict[NeighborArm, list[CorrectedReading]] = {arm: [] for arm in NeighborArm}
    family_reports: dict[str, Any] = {}
    for family_index, family in enumerate(source_design.families):
        # The non-overlapping test seed is required by the dataset constructor,
        # but the corrected instrument scores validation episodes only.
        dataset = _dataset(
            family,
            validation_seeds=design.validation_seeds,
            test_seeds=(870001 + family_index,),
            max_steps=design.max_steps,
            split_label="corrected-instrument-validation-only",
        )
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
        family_readings: dict[NeighborArm, list[CorrectedReading]] = {}
        for arm in NeighborArm:
            values = [
                _evaluate(
                    evaluator,
                    dataset,
                    episode,
                    family,
                    arm,
                    design.selected_parameters[arm],
                    design=design,
                )
                for episode in episodes
            ]
            readings[arm].extend(values)
            family_readings[arm] = values
        family_reports[family.family_id] = {
            "episode_count": len(episodes),
            "summaries": {
                arm.value: _reading_summary(values) for arm, values in family_readings.items()
            },
        }

    summaries = {arm.value: _reading_summary(values) for arm, values in readings.items()}
    distinguishability = published_action_distinguishability(readings)
    care = readings[NeighborArm.CARE_WM]
    care_verification_total = sum(item.verification_count for item in care)
    care_bayesian_receipts = [
        receipt for item in care for receipt in item.bayesian_verification_receipts
    ]
    saturation_rate = mean(
        item.verification_count >= design.max_physical_verifications_per_episode for item in care
    )
    eligible = design.eligible_overall_comparators
    strongest_overall = min(
        eligible,
        key=lambda arm: (
            summaries[arm.value]["net_environment_regret_per_step"],
            arm.value,
        ),
    )
    strongest_published = min(
        PUBLISHED_NEIGHBOR_ARMS,
        key=lambda arm: (
            summaries[arm.value]["net_environment_regret_per_step"],
            arm.value,
        ),
    )

    nonoracle = [
        item for arm, values in readings.items() if arm is not NeighborArm.ORACLE for item in values
    ]
    care_axis_totals = {
        axis: sum(item.axis_consumption_counts.get(axis, 0) for item in care)
        for axis in ("actor", "identity", "cause", "regime")
    }
    instrument_integrity_criteria = {
        "current_v0_3_manifest_and_sources_bound": True,
        "validation_only_and_no_sealed_holdout_opened": True,
        "dual_task_search_pin_has_zero_violations": all(
            item.search_pin_violation_count == 0 for item in nonoracle
        ),
        "external_repair_pricing_has_no_invalid_receipts": all(
            item.external_repair_pricing.invalid_receipt_count == 0 for item in nonoracle
        ),
        "internal_ledger_operations_not_priced_as_external_repairs": all(
            item.external_repair_pricing.external_repair_cost == 0.0 for item in nonoracle
        ),
        "bayesian_receipt_count_matches_physical_verifications": (
            len(care_bayesian_receipts) == care_verification_total
        ),
        "all_bayesian_posteriors_normalized": all(
            receipt.get("normalized") is True for receipt in care_bayesian_receipts
        ),
        "bayesian_update_demonstrably_uses_prior": bool(care_bayesian_receipts)
        and all(receipt.get("prior_used") is True for receipt in care_bayesian_receipts)
        and any(
            receipt.get("posterior_differs_from_likelihood_only") is True
            for receipt in care_bayesian_receipts
        ),
        "all_nonoracle_decisions_respect_truth_boundary": all(
            item.truth_isolation for item in nonoracle
        ),
        "complete_structure_two_axes_still_consumed": all(
            value > 0 for value in care_axis_totals.values()
        ),
    }
    comparison_validity_criteria = {
        "published_mean_pairwise_action_disagreement_above_floor": (
            distinguishability["mean_pairwise_action_disagreement"]
            >= design.minimum_mean_pairwise_disagreement
        ),
        "published_differentiated_episode_fraction_above_floor": (
            distinguishability["differentiated_episode_fraction"]
            >= design.minimum_differentiated_episode_fraction
        ),
        "every_published_arm_differs_from_at_least_one_peer": distinguishability[
            "every_published_arm_differs_from_at_least_one_peer"
        ],
        "care_verification_budget_not_saturated": (
            saturation_rate <= design.maximum_care_budget_saturation_rate
        ),
    }
    instrument_integrity_passed = all(instrument_integrity_criteria.values())
    comparison_validity_passed = instrument_integrity_passed and all(
        comparison_validity_criteria.values()
    )
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": (
            "post-hoc D0 validation-only corrected-instrument diagnostic; "
            "not a sealed-holdout, official-code, real-data, or robot claim"
        ),
        "complete_project_two_scope_preserved": True,
        "legacy_v0_1_result_used_as_parameter_reference": True,
        "legacy_v0_1_source_preservation_verified": False,
        "legacy_v0_2_status": "BLOCKED_LEGACY_SOURCE_UNRECOVERABLE",
        "sealed_holdout_opened": False,
        "retuning_performed": False,
        "validation_seeds": list(design.validation_seeds),
        "selected_parameters_reused_from_v0_1": {
            arm.value: value for arm, value in design.selected_parameters.items()
        },
        "corrections": {
            "dual_task_readout": (
                "search starts at last visible observation; put-back remains owner-habit posterior"
            ),
            "verification_update": "Bayesian categorical likelihood update",
            "repair_cost_boundary": "external execution receipts only",
            "validity_gates": "published action distinguishability and CARE budget saturation",
        },
        "overall_summaries": summaries,
        "families": family_reports,
        "published_action_distinguishability": distinguishability,
        "care_verification_budget": {
            "episode_count": len(care),
            "budget_per_episode": design.max_physical_verifications_per_episode,
            "total_physical_verifications": care_verification_total,
            "full_budget_saturation_rate": saturation_rate,
            "maximum_valid_saturation_rate": design.maximum_care_budget_saturation_rate,
        },
        "care_axis_consumption_totals": care_axis_totals,
        "internal_ledger_operations_are_unpriced_audit_events": {
            "retract": sum(item.internal_operation_counts.get("retract", 0) for item in care),
            "corrected_revision": sum(
                item.internal_operation_counts.get("corrected_revision", 0) for item in care
            ),
        },
        "external_execution_receipt_totals": {
            "charged_unique_rollbacks": sum(
                item.external_repair_pricing.charged_unique_rollback_count for item in care
            ),
            "external_repair_cost": sum(
                item.external_repair_pricing.external_repair_cost for item in care
            ),
        },
        "selected_strongest_overall_eligible_comparator": strongest_overall.value,
        "selected_strongest_published_comparator": strongest_published.value,
        "care_minus_strongest_overall_net_environment_regret_per_step": (
            summaries[NeighborArm.CARE_WM.value]["net_environment_regret_per_step"]
            - summaries[strongest_overall.value]["net_environment_regret_per_step"]
        ),
        "care_minus_strongest_published_net_environment_regret_per_step": (
            summaries[NeighborArm.CARE_WM.value]["net_environment_regret_per_step"]
            - summaries[strongest_published.value]["net_environment_regret_per_step"]
        ),
        "instrument_integrity_criteria": instrument_integrity_criteria,
        "comparison_validity_criteria": comparison_validity_criteria,
        "instrument_integrity_passed": instrument_integrity_passed,
        "comparison_validity_passed": comparison_validity_passed,
        "scientific_conclusion": (
            "comparison_valid_on_validation_only"
            if comparison_validity_passed
            else "comparison_invalid_do_not_claim_method_superiority"
        ),
        "provenance": {
            "corrected_instrument_source_sha256": _file_sha256(Path(__file__).resolve()),
            "corrected_manifest_sha256": design.manifest_file_sha256,
            "legacy_source_manifest_sha256": design.source_manifest_file_sha256,
            "legacy_source_report_file_sha256": design.source_report_file_sha256,
            "legacy_source_report_content_sha256": design.source_report_content_sha256,
            "current_gate_source_sha256": design.source_gate_file_sha256,
            "action_evaluator_source_sha256": _file_sha256(
                repository_root
                / "src/cpswm/system/evaluation_operations/project_two_action_benchmark.py"
            ),
        },
        "limitations": [
            "This is a post-hoc repair run on the already used validation seeds.",
            "The v0.2 legacy gate source is unavailable; this v0.3 run binds current source.",
            "No sealed holdout was opened or scored by this protocol.",
            "Published-neighbor adapters remain matched semantic adapters, not official code.",
            (
                "No model-selected action was externally executed, so environmental "
                "repair cost is zero."
            ),
            "D0 synthetic evidence cannot establish real embodied performance.",
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_structure_two_corrected_instrument_report(
    report: Mapping[str, Any],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_structure_two_corrected_instrument_report(
    report_path: Path,
    *,
    repository_root: Path,
    recompute: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    stored_hash = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored_hash, str) or content_sha256(unsigned) != stored_hash:
        raise ValueError("corrected-instrument report content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("corrected-instrument report protocol mismatch")
    if report.get("legacy_v0_2_status") != "BLOCKED_LEGACY_SOURCE_UNRECOVERABLE":
        raise ValueError("corrected-instrument legacy v0.2 blocker was removed")
    if report.get("legacy_v0_1_source_preservation_verified") is not False:
        raise ValueError("corrected-instrument cannot claim legacy source preservation")
    if report.get("legacy_v0_1_result_used_as_parameter_reference") is not True:
        raise ValueError("corrected-instrument legacy parameter-reference boundary mismatch")
    if report.get("sealed_holdout_opened") is not False:
        raise ValueError("corrected-instrument cannot claim a sealed-holdout result")
    design = load_corrected_instrument_design(
        repository_root / DEFAULT_MANIFEST,
        repository_root=repository_root,
    )
    expected_provenance = {
        "corrected_instrument_source_sha256": _file_sha256(Path(__file__).resolve()),
        "corrected_manifest_sha256": design.manifest_file_sha256,
        "legacy_source_manifest_sha256": design.source_manifest_file_sha256,
        "legacy_source_report_file_sha256": design.source_report_file_sha256,
        "legacy_source_report_content_sha256": design.source_report_content_sha256,
        "current_gate_source_sha256": design.source_gate_file_sha256,
        "action_evaluator_source_sha256": _file_sha256(
            repository_root
            / "src/cpswm/system/evaluation_operations/project_two_action_benchmark.py"
        ),
    }
    if report.get("provenance") != expected_provenance:
        raise ValueError("corrected-instrument provenance mismatch")
    integrity = report.get("instrument_integrity_criteria")
    validity = report.get("comparison_validity_criteria")
    if report.get("instrument_integrity_passed") != all(
        value is True for value in cast(dict[str, bool], integrity).values()
    ):
        raise ValueError("corrected-instrument integrity decision mismatch")
    expected_validity = bool(report["instrument_integrity_passed"]) and all(
        value is True for value in cast(dict[str, bool], validity).values()
    )
    if report.get("comparison_validity_passed") != expected_validity:
        raise ValueError("corrected-instrument comparison-validity mismatch")
    expected_conclusion = (
        "comparison_valid_on_validation_only"
        if expected_validity
        else "comparison_invalid_do_not_claim_method_superiority"
    )
    if report.get("scientific_conclusion") != expected_conclusion:
        raise ValueError("corrected-instrument scientific conclusion mismatch")
    if expected_validity and not recompute:
        raise ValueError("positive comparison validity requires deterministic recomputation")
    if recompute:
        expected = run_structure_two_corrected_instrument(repository_root=repository_root)
        if expected["content_sha256"] != report["content_sha256"]:
            raise ValueError("corrected-instrument deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_MANIFEST",
    "DEFAULT_OUTPUT",
    "LEGACY_CORRECTED_PROTOCOL_ID",
    "LEGACY_MANIFEST",
    "PROTOCOL_ID",
    "CorrectedInstrumentDesign",
    "ExternalActionExecutionReceipt",
    "ExternalRepairPricing",
    "audit_legacy_corrected_instrument_v0_2",
    "bayesian_categorical_update",
    "load_corrected_instrument_design",
    "price_external_repairs",
    "published_action_distinguishability",
    "run_structure_two_corrected_instrument",
    "verify_structure_two_corrected_instrument_report",
    "write_structure_two_corrected_instrument_report",
]
