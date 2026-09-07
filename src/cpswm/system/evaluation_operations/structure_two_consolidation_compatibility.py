"""Fresh-seed gate for revision-compatible reversible consolidation."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import UUID

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ActionCaseMetric,
    ProjectTwoActionBenchmarkV02,
    _FullProjectTwoMethod,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_factorial_benchmark import _CIAVState
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (
    _action_readout,
    _FamilyFeedbackState,
    _file_sha256,
    _normalize,
    _VisibleTransformState,
)
from cpswm.system.evaluation_operations.structure_two_rejuvenation_gate import (
    FROZEN_PARTICLE_BUDGET,
)
from cpswm.system.evaluation_operations.structure_two_sequential_gate import (
    PersistentParticle,
    ReversibleParticleConsolidationLedger,
    SequentialGateArm,
    SequentialGateFamily,
    _SequentialMultiAxisActionState,
    _TargetObjectRoutingState,
    _visible_transform,
)
from cpswm.system.evaluation_operations.structure_two_sequential_gate import (
    _state_for_arm as _previous_state_for_arm,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-consolidation-compatibility-gate@0.1"
DEFAULT_MANIFEST = Path(
    "configs/project_two_experiments/structure_two_consolidation_compatibility_manifest_v0_1.json"
)
DEFAULT_SEALED_SEEDS = Path(
    "configs/project_two_experiments/"
    "structure_two_consolidation_compatibility_sealed_seeds_v0_1.json"
)
DEFAULT_PREREGISTRATION = Path(
    "docs/experiments/structure_two_consolidation_compatibility_gate_preregistration_2026-08-29.md"
)


class CompatibilityArm(StrEnum):
    CORRECTED_AMG = "corrected_amg"
    PER_STEP_PARTICLE = "per_step_particle_projection"
    SEQUENTIAL_NO_CONSOLIDATION = "sequential_particle_no_consolidation"
    FIXED_STALE_BLEND = "fixed_stale_blend"
    REVISION_COMPATIBILITY = "revision_compatibility_gate"
    UNCERTAINTY_DECAY = "uncertainty_decayed_influence"
    IMMEDIATE_QUARANTINE = "immediate_conflict_quarantine"
    ADAPTIVE_COMBINED = "adaptive_combined_consolidation"


class ConsolidationStrategy(StrEnum):
    COMPATIBILITY = "compatibility"
    UNCERTAINTY_DECAY = "uncertainty_decay"
    IMMEDIATE_QUARANTINE = "immediate_quarantine"
    ADAPTIVE_COMBINED = "adaptive_combined"


@dataclass(frozen=True, slots=True)
class CompatibilityDesign:
    validation_seeds: tuple[int, ...]
    holdout_seed_commitments: tuple[str, ...]
    sealed_holdout_seed_count: int
    sealed_seed_file_sha256: str
    max_steps: int
    particle_budget: int
    families: tuple[SequentialGateFamily, ...]
    search_spaces: Mapping[str, tuple[Any, ...]]
    required_mitigation_families: tuple[str, ...]
    guardrail_families: tuple[str, ...]
    noninferiority_margin: float
    manifest_file_sha256: str


@dataclass(frozen=True, slots=True)
class CompatibilityReading:
    metric: ActionCaseMetric
    verification_cost: float
    axis_trace_count: int
    ancestry_edge_count: int
    ledger_operation_counts: Mapping[str, int]
    duplicate_promotion_count: int
    operator_retention_receipt: Mapping[str, Any] | None
    consumed_visible_stream_hash: str
    strategy_receipt: Mapping[str, Any]

    @property
    def net_action_loss_per_step(self) -> float:
        return float(
            (self.metric.cumulative_action_regret + self.verification_cost)
            / max(1, self.metric.step_count)
        )


def load_frozen_compatibility_design(
    manifest_path: Path = DEFAULT_MANIFEST,
) -> CompatibilityDesign:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("compatibility manifest protocol mismatch")
    families = tuple(
        SequentialGateFamily(
            family_id=item["family_id"],
            family_role=item["family_role"],
            guest_window=tuple(item["guest_window"]),
            abrupt_day=item["abrupt_day"],
            recurrence_day=item["recurrence_day"],
            observation_coverage=item["observation_coverage"],
            unknown_event_days=tuple(item["unknown_event_days"]),
            actor_ambiguity_mix=item["actor_ambiguity_mix"],
            identity_confidence_scale=item["identity_confidence_scale"],
            feedback_flip_rate=item["feedback_flip_rate"],
            decoy_days=tuple(item["decoy_days"]),
        )
        for item in payload["scenario_families"]
    )
    design = CompatibilityDesign(
        validation_seeds=tuple(payload["validation_seeds"]),
        holdout_seed_commitments=tuple(payload["sealed_holdout_seed_commitments"]),
        sealed_holdout_seed_count=payload["sealed_holdout_seed_count"],
        sealed_seed_file_sha256=payload["sealed_seed_file_sha256"],
        max_steps=payload["max_steps"],
        particle_budget=payload["particle_budget"],
        families=families,
        search_spaces={key: tuple(value) for key, value in payload["search_spaces"].items()},
        required_mitigation_families=tuple(payload["required_mitigation_families"]),
        guardrail_families=tuple(payload["guardrail_families"]),
        noninferiority_margin=float(payload["noninferiority_margin"]),
        manifest_file_sha256=_file_sha256(manifest_path),
    )
    if len(families) != 4 or len({family.family_id for family in families}) != 4:
        raise ValueError("compatibility gate requires four unique families")
    if set(design.search_spaces) != {arm.value for arm in CompatibilityArm}:
        raise ValueError("compatibility search spaces do not match frozen arms")
    if design.particle_budget != FROZEN_PARTICLE_BUDGET:
        raise ValueError("compatibility gate freezes K=24")
    if set(design.required_mitigation_families) | set(design.guardrail_families) != {
        family.family_id for family in families
    }:
        raise ValueError("compatibility family roles are incomplete")
    if len(design.holdout_seed_commitments) != design.sealed_holdout_seed_count:
        raise ValueError("compatibility commitment count mismatch")
    return design


def _load_and_verify_holdout_seeds(
    design: CompatibilityDesign,
    sealed_seed_path: Path,
) -> tuple[int, ...]:
    if _file_sha256(sealed_seed_path) != design.sealed_seed_file_sha256:
        raise ValueError("compatibility sealed seed file hash mismatch")
    payload = json.loads(sealed_seed_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("compatibility sealed seed protocol mismatch")
    seeds = tuple(payload["holdout_seeds"])
    salt = payload["commitment_salt"]
    commitments = tuple(
        hashlib.sha256(f"{PROTOCOL_ID}:{seed}:{salt}".encode()).hexdigest() for seed in seeds
    )
    if commitments != design.holdout_seed_commitments:
        raise ValueError("compatibility holdout commitments mismatch")
    if set(seeds) & set(design.validation_seeds):
        raise ValueError("compatibility validation and holdout seeds overlap")
    return seeds


def _dataset(
    family: SequentialGateFamily,
    *,
    validation_seeds: tuple[int, ...],
    test_seeds: tuple[int, ...],
    max_steps: int,
    split_label: str,
) -> ProjectTwoReplayDataset:
    return D0SyntheticOracleReplayAdapter(
        validation_seeds=validation_seeds,
        test_seeds=test_seeds,
        max_steps_per_episode=max_steps,
        dataset_version=f"{PROTOCOL_ID}:{family.family_id}:{split_label}",
        sealed_secret=f"{PROTOCOL_ID}:{family.family_id}:scenario-seal",
        scenario_duration_days=max_steps,
        guest_window=family.guest_window,
        abrupt_day=family.abrupt_day,
        recurrence_day=family.recurrence_day,
        observation_coverage=family.observation_coverage,
        unknown_event_days=family.unknown_event_days,
    ).build()


def _signature_parts(signature: str) -> tuple[str, str, str, str]:
    actor, identity, cause, regime = signature.split("|")
    return actor, identity, cause, regime


def _compatibility_score(left: str, right: str) -> float:
    left_parts = _signature_parts(left)
    right_parts = _signature_parts(right)
    weights = (0.30, 0.25, 0.25, 0.20)
    return sum(
        weight * float(left_item == right_item)
        for weight, left_item, right_item in zip(weights, left_parts, right_parts, strict=True)
    )


def _hard_conflict(left: str, right: str) -> bool:
    left_actor, _, left_cause, left_regime = _signature_parts(left)
    right_actor, _, right_cause, right_regime = _signature_parts(right)
    return left_actor != right_actor or left_cause != right_cause or left_regime != right_regime


class AdaptiveParticleConsolidationLedger(ReversibleParticleConsolidationLedger):
    """The same reversible ledger with strategy-specific action influence gates."""

    def __init__(self, *, strategy: ConsolidationStrategy) -> None:
        super().__init__()
        self.strategy = strategy
        self.current_dominant: PersistentParticle | None = None
        self.current_compatibility = 0.0
        self.current_influence_weight = 0.0
        self.compatibility_suppression_count = 0
        self.uncertainty_decay_count = 0
        self.immediate_quarantine_count = 0
        self._suspended = False

    def update(
        self,
        particles: tuple[PersistentParticle, ...],
        distribution: Mapping[UUID, float],
        *,
        step_index: int,
    ) -> None:
        dominant = max(
            particles,
            key=lambda item: (item.posterior_probability, item.signature),
        )
        old_active_revision = self.active_revision_id
        old_active_signature = self.active_signature
        hard_conflict = bool(
            old_active_signature is not None
            and _hard_conflict(old_active_signature, dominant.signature)
        )
        if (
            self.strategy
            in {
                ConsolidationStrategy.IMMEDIATE_QUARANTINE,
                ConsolidationStrategy.ADAPTIVE_COMBINED,
            }
            and hard_conflict
        ):
            self._suspended = True
            self.immediate_quarantine_count += 1
        super().update(particles, distribution, step_index=step_index)
        if self.active_revision_id != old_active_revision:
            self._suspended = False
        self.current_dominant = dominant
        self.current_compatibility = (
            0.0
            if self.active_signature is None
            else _compatibility_score(self.active_signature, dominant.signature)
        )

    def blend(self, distribution: Mapping[UUID, float]) -> dict[UUID, float]:
        if self.active_distribution is None or self.current_dominant is None:
            self.current_influence_weight = 0.0
            return dict(distribution)
        compatibility = self.current_compatibility
        confidence = min(
            1.0,
            max(0.0, self.current_dominant.posterior_probability / 0.18),
        )
        weight = 0.28
        if self.strategy is ConsolidationStrategy.COMPATIBILITY:
            if compatibility < 0.80:
                weight = 0.0
                self.compatibility_suppression_count += 1
        elif self.strategy is ConsolidationStrategy.UNCERTAINTY_DECAY:
            weight *= compatibility * confidence
            if weight < 0.28 - 1e-12:
                self.uncertainty_decay_count += 1
        elif self.strategy is ConsolidationStrategy.IMMEDIATE_QUARANTINE:
            if self._suspended:
                weight = 0.0
        else:
            if compatibility < 0.80 or self._suspended:
                weight = 0.0
                self.compatibility_suppression_count += 1
            else:
                weight *= compatibility * confidence
                if weight < 0.28 - 1e-12:
                    self.uncertainty_decay_count += 1
        self.current_influence_weight = weight
        if weight <= 0.0:
            return dict(distribution)
        keys = set(distribution) | set(self.active_distribution)
        values = {
            key: (1.0 - weight) * distribution.get(key, 0.0)
            + weight * self.active_distribution.get(key, 0.0)
            for key in keys
        }
        normalized = _normalize(values)
        return {key: float(value) for key, value in normalized.items()}

    @property
    def strategy_receipt(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "compatibility_suppression_count": self.compatibility_suppression_count,
            "uncertainty_decay_count": self.uncertainty_decay_count,
            "immediate_quarantine_count": self.immediate_quarantine_count,
            "current_compatibility": self.current_compatibility,
            "current_influence_weight": self.current_influence_weight,
        }


class _AdaptiveSequentialState(_SequentialMultiAxisActionState):
    def __init__(
        self,
        state: _FullProjectTwoMethod,
        episode: Any,
        *,
        profile: str,
        strategy: ConsolidationStrategy,
    ) -> None:
        super().__init__(
            state,
            episode,
            profile=profile,
            consolidation=False,
        )
        self._adaptive_particle_ledger = AdaptiveParticleConsolidationLedger(strategy=strategy)
        self._particle_ledger = self._adaptive_particle_ledger

    @property
    def consolidation_strategy_receipt(self) -> dict[str, Any]:
        return self._adaptive_particle_ledger.strategy_receipt


STRATEGY_BY_ARM = {
    CompatibilityArm.REVISION_COMPATIBILITY: ConsolidationStrategy.COMPATIBILITY,
    CompatibilityArm.UNCERTAINTY_DECAY: ConsolidationStrategy.UNCERTAINTY_DECAY,
    CompatibilityArm.IMMEDIATE_QUARANTINE: ConsolidationStrategy.IMMEDIATE_QUARANTINE,
    CompatibilityArm.ADAPTIVE_COMBINED: ConsolidationStrategy.ADAPTIVE_COMBINED,
}


def _state_for_arm(
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    family: SequentialGateFamily,
    arm: CompatibilityArm,
    parameter: Any,
) -> Any:
    previous_arm = {
        CompatibilityArm.CORRECTED_AMG: SequentialGateArm.CORRECTED_AMG,
        CompatibilityArm.PER_STEP_PARTICLE: SequentialGateArm.PER_STEP_PARTICLE,
        CompatibilityArm.SEQUENTIAL_NO_CONSOLIDATION: (
            SequentialGateArm.SEQUENTIAL_NO_CONSOLIDATION
        ),
        CompatibilityArm.FIXED_STALE_BLEND: SequentialGateArm.SEQUENTIAL_CONSOLIDATION,
    }.get(arm)
    if previous_arm is not None:
        return _previous_state_for_arm(
            dataset,
            episode,
            family,
            previous_arm,
            parameter,
        )
    base = _FullProjectTwoMethod(
        episode,
        owner_threshold=0.4,
        action_readout=_action_readout(),
    )
    state: Any = _AdaptiveSequentialState(
        base,
        episode,
        profile=str(parameter),
        strategy=STRATEGY_BY_ARM[arm],
    )
    state = _CIAVState(state, dataset, episode, enabled=True, cost_multiplier=1.0)
    state.operator_retention_receipt = {
        **state.operator_retention_receipt,
        "ciav": bool(state._enabled),
    }
    state = _TargetObjectRoutingState(state)
    state = _VisibleTransformState(state, _visible_transform(family, episode))
    return _FamilyFeedbackState(state, family, episode)


def _evaluate(
    evaluator: ProjectTwoActionBenchmarkV02,
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    family: SequentialGateFamily,
    arm: CompatibilityArm,
    parameter: Any,
) -> CompatibilityReading:
    state = _state_for_arm(dataset, episode, family, arm, parameter)
    metric = evaluator.evaluate_custom_state(dataset, episode, state)
    return CompatibilityReading(
        metric=metric,
        verification_cost=float(getattr(state, "verification_cost", 0.0)),
        axis_trace_count=int(getattr(state, "axis_trace_count", 0)),
        ancestry_edge_count=int(getattr(state, "ancestry_edge_count", 0)),
        ledger_operation_counts=dict(getattr(state, "ledger_operation_counts", {})),
        duplicate_promotion_count=int(getattr(state, "duplicate_promotion_count", 0)),
        operator_retention_receipt=getattr(state, "operator_retention_receipt", None),
        consumed_visible_stream_hash=str(getattr(state, "consumed_visible_stream_hash", "")),
        strategy_receipt=dict(getattr(state, "consolidation_strategy_receipt", {})),
    )


def _summary(readings: list[CompatibilityReading]) -> dict[str, float]:
    return {
        "net_action_loss_per_step": mean(reading.net_action_loss_per_step for reading in readings),
        "put_back_error_rate": mean(reading.metric.put_back_error_rate for reading in readings),
        "persistent_owner_mode_error_rate": mean(
            reading.metric.persistent_owner_mode_error_rate for reading in readings
        ),
        "verification_cost": mean(reading.verification_cost for reading in readings),
        "mean_ancestry_edge_count": mean(reading.ancestry_edge_count for reading in readings),
        "mean_promote_count": mean(
            reading.ledger_operation_counts.get("promote", 0) for reading in readings
        ),
        "compatibility_suppression_count": sum(
            int(reading.strategy_receipt.get("compatibility_suppression_count", 0))
            for reading in readings
        ),
        "uncertainty_decay_count": sum(
            int(reading.strategy_receipt.get("uncertainty_decay_count", 0)) for reading in readings
        ),
        "immediate_quarantine_count": sum(
            int(reading.strategy_receipt.get("immediate_quarantine_count", 0))
            for reading in readings
        ),
        "duplicate_promotion_count": sum(reading.duplicate_promotion_count for reading in readings),
    }


def _bootstrap_ci(values: list[float], *, draws: int = 4000) -> tuple[float, float]:
    rng = random.Random(f"{PROTOCOL_ID}:paired-cluster-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


COMPARISONS = {
    "adaptive_combined_minus_fixed_blend": (
        CompatibilityArm.ADAPTIVE_COMBINED,
        CompatibilityArm.FIXED_STALE_BLEND,
    ),
    "compatibility_gate_minus_fixed_blend": (
        CompatibilityArm.REVISION_COMPATIBILITY,
        CompatibilityArm.FIXED_STALE_BLEND,
    ),
    "uncertainty_decay_minus_fixed_blend": (
        CompatibilityArm.UNCERTAINTY_DECAY,
        CompatibilityArm.FIXED_STALE_BLEND,
    ),
    "immediate_quarantine_minus_fixed_blend": (
        CompatibilityArm.IMMEDIATE_QUARANTINE,
        CompatibilityArm.FIXED_STALE_BLEND,
    ),
    "adaptive_combined_minus_per_step": (
        CompatibilityArm.ADAPTIVE_COMBINED,
        CompatibilityArm.PER_STEP_PARTICLE,
    ),
    "adaptive_combined_minus_no_consolidation": (
        CompatibilityArm.ADAPTIVE_COMBINED,
        CompatibilityArm.SEQUENTIAL_NO_CONSOLIDATION,
    ),
    "adaptive_combined_minus_corrected_amg": (
        CompatibilityArm.ADAPTIVE_COMBINED,
        CompatibilityArm.CORRECTED_AMG,
    ),
    "fixed_blend_minus_per_step": (
        CompatibilityArm.FIXED_STALE_BLEND,
        CompatibilityArm.PER_STEP_PARTICLE,
    ),
}


def run_consolidation_compatibility_gate(
    *,
    repository_root: Path,
    manifest_path: Path | None = None,
    sealed_seed_path: Path | None = None,
) -> dict[str, Any]:
    manifest = manifest_path or repository_root / DEFAULT_MANIFEST
    sealed = sealed_seed_path or repository_root / DEFAULT_SEALED_SEEDS
    design = load_frozen_compatibility_design(manifest)
    evaluator = ProjectTwoActionBenchmarkV02()
    phase_audit = ["validation_tuning_started"]
    selected: dict[str, dict[CompatibilityArm, Any]] = {}
    validation_reports: dict[str, Any] = {}
    for family in design.families:
        dataset = _dataset(
            family,
            validation_seeds=design.validation_seeds,
            test_seeds=(95991,),
            max_steps=design.max_steps,
            split_label="validation",
        )
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
        selected[family.family_id] = {}
        validation_reports[family.family_id] = {}
        for arm in CompatibilityArm:
            candidates: list[dict[str, Any]] = []
            for parameter in design.search_spaces[arm.value]:
                readings = [
                    _evaluate(evaluator, dataset, episode, family, arm, parameter)
                    for episode in episodes
                ]
                candidates.append(
                    {
                        "parameter": parameter,
                        "mean_net_action_loss_per_step": mean(
                            reading.net_action_loss_per_step for reading in readings
                        ),
                    }
                )
            winner = min(
                candidates,
                key=lambda item: (
                    item["mean_net_action_loss_per_step"],
                    json.dumps(item["parameter"], sort_keys=True),
                ),
            )
            selected[family.family_id][arm] = winner["parameter"]
            validation_reports[family.family_id][arm.value] = {
                "candidates": candidates,
                "selected_parameter": winner["parameter"],
            }
    phase_audit.extend(("validation_tuning_completed", "sealed_seed_file_open_requested"))
    holdout_seeds = _load_and_verify_holdout_seeds(design, sealed)
    phase_audit.append("sealed_seed_file_verified")

    expected_operator_receipt = {
        "opceu": "inverse",
        "orrer": "orrer",
        "pchmp": "ProvenanceConstrainedMessagePassing",
        "cf_bocpd": True,
        "rgrc": True,
        "ccrr": True,
        "ciav": True,
    }
    family_reports: dict[str, Any] = {}
    paired_by_commitment: dict[str, dict[str, list[float]]] = {
        commitment: {name: [] for name in COMPARISONS}
        for commitment in design.holdout_seed_commitments
    }
    operator_gates: dict[str, bool] = {}
    ancestry_gates: dict[str, bool] = {}
    ledger_gates: dict[str, bool] = {}
    strategy_runtime_gates: dict[str, bool] = {}
    for family_index, family in enumerate(design.families):
        dataset = _dataset(
            family,
            validation_seeds=(95991 + family_index,),
            test_seeds=holdout_seeds,
            max_steps=design.max_steps,
            split_label="sealed-holdout",
        )
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        holdout_readings: dict[CompatibilityArm, list[CompatibilityReading]] = {
            arm: [
                _evaluate(
                    evaluator,
                    dataset,
                    episode,
                    family,
                    arm,
                    selected[family.family_id][arm],
                )
                for episode in episodes
            ]
            for arm in CompatibilityArm
        }
        for arm in CompatibilityArm:
            if arm is CompatibilityArm.CORRECTED_AMG:
                continue
            operator_gates[f"{family.family_id}:{arm.value}"] = all(
                reading.operator_retention_receipt == expected_operator_receipt
                for reading in holdout_readings[arm]
            )
        for arm in CompatibilityArm:
            if arm in {
                CompatibilityArm.CORRECTED_AMG,
                CompatibilityArm.PER_STEP_PARTICLE,
            }:
                continue
            ancestry_gates[f"{family.family_id}:{arm.value}"] = all(
                reading.ancestry_edge_count > 0 for reading in holdout_readings[arm]
            )
        for arm in (
            CompatibilityArm.FIXED_STALE_BLEND,
            *tuple(STRATEGY_BY_ARM),
        ):
            ledger_gates[f"{family.family_id}:{arm.value}"] = all(
                reading.ledger_operation_counts.get("promote", 0) > 0
                and reading.duplicate_promotion_count == 0
                for reading in holdout_readings[arm]
            )
        strategy_runtime_gates[f"{family.family_id}:compatibility"] = any(
            int(reading.strategy_receipt.get("compatibility_suppression_count", 0)) > 0
            for reading in holdout_readings[CompatibilityArm.REVISION_COMPATIBILITY]
        )
        strategy_runtime_gates[f"{family.family_id}:uncertainty"] = any(
            int(reading.strategy_receipt.get("uncertainty_decay_count", 0)) > 0
            for reading in holdout_readings[CompatibilityArm.UNCERTAINTY_DECAY]
        )
        strategy_runtime_gates[f"{family.family_id}:quarantine"] = any(
            int(reading.strategy_receipt.get("immediate_quarantine_count", 0)) > 0
            for reading in holdout_readings[CompatibilityArm.IMMEDIATE_QUARANTINE]
        )
        strategy_runtime_gates[f"{family.family_id}:combined"] = any(
            int(reading.strategy_receipt.get("compatibility_suppression_count", 0)) > 0
            and int(reading.strategy_receipt.get("uncertainty_decay_count", 0)) > 0
            and int(reading.strategy_receipt.get("immediate_quarantine_count", 0)) > 0
            for reading in holdout_readings[CompatibilityArm.ADAPTIVE_COMBINED]
        )
        paired_rows = []
        for index, commitment in enumerate(design.holdout_seed_commitments):
            consumed_hashes = {
                arm.value: holdout_readings[arm][index].consumed_visible_stream_hash
                for arm in CompatibilityArm
            }
            if len(set(consumed_hashes.values())) != 1:
                raise ValueError("compatibility consumed stream mismatch")
            losses = {
                arm.value: holdout_readings[arm][index].net_action_loss_per_step
                for arm in CompatibilityArm
            }
            differences = {
                name: losses[left.value] - losses[right.value]
                for name, (left, right) in COMPARISONS.items()
            }
            for name, value in differences.items():
                paired_by_commitment[commitment][name].append(value)
            paired_rows.append(
                {
                    "holdout_seed_commitment": commitment,
                    "consumed_visible_stream_hash": next(iter(consumed_hashes.values())),
                    "consumed_visible_stream_hash_by_arm": consumed_hashes,
                    "net_action_loss_per_step": losses,
                    "paired_differences": differences,
                }
            )
        family_reports[family.family_id] = {
            "family_parameters": asdict(family),
            "selected_parameters": {
                arm.value: value for arm, value in selected[family.family_id].items()
            },
            "summaries": {arm.value: _summary(values) for arm, values in holdout_readings.items()},
            "paired_holdout_rows": paired_rows,
        }

    clustered: dict[str, list[float]] = {
        name: [
            mean(paired_by_commitment[commitment][name])
            for commitment in design.holdout_seed_commitments
        ]
        for name in COMPARISONS
    }
    comparisons: dict[str, dict[str, Any]] = {
        name: {
            "mean": mean(values),
            "confidence_interval_95": _bootstrap_ci(values),
            "cluster_count": len(values),
            "benefit_if_negative": True,
        }
        for name, values in clustered.items()
    }
    primary = "adaptive_combined_minus_fixed_blend"
    noninferiority = "adaptive_combined_minus_per_step"
    family_primary = {
        family_id: mean(
            row["paired_differences"][primary] for row in family_report["paired_holdout_rows"]
        )
        for family_id, family_report in family_reports.items()
    }
    family_noninferiority = {
        family_id: mean(
            row["paired_differences"][noninferiority]
            for row in family_report["paired_holdout_rows"]
        )
        for family_id, family_report in family_reports.items()
    }
    gate_criteria = {
        "primary_mitigation_ci_upper_below_zero": comparisons[primary]["confidence_interval_95"][1]
        < 0.0,
        "required_identity_mitigation": family_primary[design.required_mitigation_families[0]]
        < 0.0,
        "required_recurrence_mitigation": family_primary[design.required_mitigation_families[1]]
        < 0.0,
        "adaptive_noninferior_to_per_step": comparisons[noninferiority]["confidence_interval_95"][1]
        <= design.noninferiority_margin,
        "role_guardrail": family_noninferiority[design.guardrail_families[0]]
        <= design.noninferiority_margin,
        "cause_guardrail": family_noninferiority[design.guardrail_families[1]]
        <= design.noninferiority_margin,
        "all_runtime_operator_gates": all(operator_gates.values()),
        "all_ancestry_gates": all(ancestry_gates.values()),
        "all_ledger_gates": all(ledger_gates.values()),
        "all_strategy_runtime_gates": all(strategy_runtime_gates.values()),
    }
    positive_contribution_candidate = comparisons[noninferiority]["confidence_interval_95"][1] < 0.0
    provenance_paths = {
        "benchmark_source_sha256": Path(__file__).resolve(),
        "sequential_backend_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_sequential_gate.py",
        "action_evaluator_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/project_two_action_benchmark.py",
        "manifest_file_sha256": manifest,
        "sealed_seed_file_sha256": sealed,
        "preregistration_sha256": repository_root / DEFAULT_PREREGISTRATION,
    }
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": "D0 synthetic mitigation evidence; not paper evidence",
        "neural_proposer_status": "not_run_by_preregistered_design",
        "amg_fidelity": "matched_replay_adapter_not_faithful_original_reproduction",
        "particle_budget": design.particle_budget,
        "holdout_seed_commitments": list(design.holdout_seed_commitments),
        "raw_holdout_seeds_disclosed": False,
        "phase_audit": phase_audit,
        "validation": validation_reports,
        "families": family_reports,
        "paired_cluster_comparisons": comparisons,
        "family_primary_mitigation_differences": family_primary,
        "family_adaptive_minus_per_step_differences": family_noninferiority,
        "runtime_operator_gates": operator_gates,
        "ancestry_gates": ancestry_gates,
        "ledger_gates": ledger_gates,
        "strategy_runtime_gates": strategy_runtime_gates,
        "gate_criteria": gate_criteria,
        "mitigation_gate_passed": all(gate_criteria.values()),
        "positive_contribution_candidate": positive_contribution_candidate,
        "provenance": {key: _file_sha256(path) for key, path in provenance_paths.items()},
        "limitations": [
            "D0 synthetic mitigation evidence only",
            "neural proposer intentionally not run",
            "sealed seeds are repository-local rather than independently held",
            "corrected AMG remains a matched adapter",
            "passing mitigation would not by itself prove positive consolidation value",
            "no RGB-D household or robot execution evidence",
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_consolidation_compatibility_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_consolidation_compatibility_report(
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
        raise ValueError("compatibility report content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("compatibility report protocol mismatch")
    design = load_frozen_compatibility_design(repository_root / DEFAULT_MANIFEST)
    holdout_seeds = _load_and_verify_holdout_seeds(design, repository_root / DEFAULT_SEALED_SEEDS)
    if tuple(report.get("holdout_seed_commitments", ())) != design.holdout_seed_commitments:
        raise ValueError("compatibility report commitment mismatch")

    def integer_values(value: Any) -> set[int]:
        if isinstance(value, bool):
            return set()
        if isinstance(value, int):
            return {value}
        if isinstance(value, dict):
            return set().union(*(integer_values(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(integer_values(item) for item in value))
        return set()

    if set(holdout_seeds) & integer_values(report):
        raise ValueError("compatibility report discloses raw holdout seeds")
    expected_arms = {arm.value for arm in CompatibilityArm}
    clustered: dict[str, dict[str, list[float]]] = {
        commitment: {name: [] for name in COMPARISONS}
        for commitment in design.holdout_seed_commitments
    }
    if set(report.get("families", {})) != {family.family_id for family in design.families}:
        raise ValueError("compatibility report family set mismatch")
    for family in report["families"].values():
        rows = family["paired_holdout_rows"]
        if tuple(row["holdout_seed_commitment"] for row in rows) != (
            design.holdout_seed_commitments
        ):
            raise ValueError("compatibility row commitment sequence mismatch")
        for row in rows:
            hashes = row.get("consumed_visible_stream_hash_by_arm", {})
            if set(hashes) != expected_arms or set(hashes.values()) != {
                row.get("consumed_visible_stream_hash")
            }:
                raise ValueError("compatibility consumed stream receipt mismatch")
            losses = row["net_action_loss_per_step"]
            expected = {
                name: losses[left.value] - losses[right.value]
                for name, (left, right) in COMPARISONS.items()
            }
            if set(row["paired_differences"]) != set(COMPARISONS) or any(
                not math.isclose(row["paired_differences"][name], value, abs_tol=1e-12)
                for name, value in expected.items()
            ):
                raise ValueError("compatibility paired difference mismatch")
            commitment = row["holdout_seed_commitment"]
            for name, value in expected.items():
                clustered[commitment][name].append(value)
    for name, recorded in report["paired_cluster_comparisons"].items():
        values = [
            mean(clustered[commitment][name]) for commitment in design.holdout_seed_commitments
        ]
        interval = _bootstrap_ci(values)
        if not math.isclose(recorded["mean"], mean(values), abs_tol=1e-12) or any(
            not math.isclose(left, right, abs_tol=1e-12)
            for left, right in zip(recorded["confidence_interval_95"], interval, strict=True)
        ):
            raise ValueError("compatibility paired comparison mismatch")
    provenance_paths = {
        "benchmark_source_sha256": Path(__file__).resolve(),
        "sequential_backend_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_sequential_gate.py",
        "action_evaluator_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/project_two_action_benchmark.py",
        "manifest_file_sha256": repository_root / DEFAULT_MANIFEST,
        "sealed_seed_file_sha256": repository_root / DEFAULT_SEALED_SEEDS,
        "preregistration_sha256": repository_root / DEFAULT_PREREGISTRATION,
    }
    if report.get("provenance") != {
        key: _file_sha256(path) for key, path in provenance_paths.items()
    }:
        raise ValueError("compatibility provenance mismatch")
    if recompute:
        expected = run_consolidation_compatibility_gate(repository_root=repository_root)
        if expected["content_sha256"] != report["content_sha256"]:
            raise ValueError("compatibility deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_MANIFEST",
    "DEFAULT_PREREGISTRATION",
    "DEFAULT_SEALED_SEEDS",
    "PROTOCOL_ID",
    "AdaptiveParticleConsolidationLedger",
    "CompatibilityArm",
    "CompatibilityDesign",
    "ConsolidationStrategy",
    "load_frozen_compatibility_design",
    "run_consolidation_compatibility_gate",
    "verify_consolidation_compatibility_report",
    "write_consolidation_compatibility_report",
]
