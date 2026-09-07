"""Fresh-seed gate for conflict-aware transitions and ledger reactivation."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
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
from cpswm.system.evaluation_operations.structure_two_consolidation_compatibility import (
    AdaptiveParticleConsolidationLedger,
    CompatibilityArm,
    ConsolidationStrategy,
)
from cpswm.system.evaluation_operations.structure_two_consolidation_compatibility import (
    _state_for_arm as _compatibility_state_for_arm,
)
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (
    MultiAxisBelief,
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
    SequentialGateFamily,
    SequentialParticleRuntime,
    _SequentialMultiAxisActionState,
    _TargetObjectRoutingState,
    _visible_transform,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.world_model.habits_transitions import ChangeCause

PROTOCOL_ID = "structure-two-transition-reactivation-gate@0.1"
DEFAULT_MANIFEST = Path(
    "configs/project_two_experiments/structure_two_transition_reactivation_manifest_v0_1.json"
)
DEFAULT_SEALED_SEEDS = Path(
    "configs/project_two_experiments/structure_two_transition_reactivation_sealed_seeds_v0_1.json"
)
DEFAULT_PREREGISTRATION = Path(
    "docs/experiments/structure_two_transition_reactivation_gate_preregistration_2026-08-29.md"
)


class TransitionReactivationArm(StrEnum):
    CORRECTED_AMG = "corrected_amg"
    PER_STEP_PARTICLE = "per_step_particle_projection"
    SEQUENTIAL_NO_CONSOLIDATION = "sequential_particle_no_consolidation"
    IMMEDIATE_QUARANTINE = "immediate_conflict_quarantine"
    CONFLICT_TRANSITION_NO_CONSOLIDATION = "conflict_aware_transition_no_consolidation"
    HISTORICAL_REACTIVATION = "historical_regime_reactivation"
    JOINT_TRANSITION_REACTIVATION = "joint_transition_reactivation"


@dataclass(frozen=True, slots=True)
class TransitionReactivationDesign:
    validation_seeds: tuple[int, ...]
    holdout_seed_commitments: tuple[str, ...]
    sealed_holdout_seed_count: int
    sealed_seed_file_sha256: str
    max_steps: int
    particle_budget: int
    families: tuple[SequentialGateFamily, ...]
    search_spaces: Mapping[str, tuple[Any, ...]]
    required_gain_families: tuple[str, ...]
    guardrail_families: tuple[str, ...]
    guardrail_noninferiority_margin: float
    manifest_file_sha256: str


@dataclass(frozen=True, slots=True)
class GateReading:
    metric: ActionCaseMetric
    verification_cost: float
    ancestry_edge_count: int
    operator_retention_receipt: Mapping[str, Any] | None
    consumed_visible_stream_hash: str
    conflict_transition_count: int
    reactivation_count: int
    duplicate_promotion_count: int

    @property
    def net_action_loss_per_step(self) -> float:
        return float(
            (self.metric.cumulative_action_regret + self.verification_cost)
            / max(1, self.metric.step_count)
        )


def load_frozen_transition_reactivation_design(
    manifest_path: Path = DEFAULT_MANIFEST,
) -> TransitionReactivationDesign:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("transition reactivation manifest protocol mismatch")
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
    design = TransitionReactivationDesign(
        validation_seeds=tuple(payload["validation_seeds"]),
        holdout_seed_commitments=tuple(payload["sealed_holdout_seed_commitments"]),
        sealed_holdout_seed_count=payload["sealed_holdout_seed_count"],
        sealed_seed_file_sha256=payload["sealed_seed_file_sha256"],
        max_steps=payload["max_steps"],
        particle_budget=payload["particle_budget"],
        families=families,
        search_spaces={key: tuple(value) for key, value in payload["search_spaces"].items()},
        required_gain_families=tuple(payload["required_gain_families"]),
        guardrail_families=tuple(payload["guardrail_families"]),
        guardrail_noninferiority_margin=float(payload["guardrail_noninferiority_margin"]),
        manifest_file_sha256=_file_sha256(manifest_path),
    )
    if len(families) != 4 or len({family.family_id for family in families}) != 4:
        raise ValueError("transition reactivation gate requires four families")
    if set(design.search_spaces) != {arm.value for arm in TransitionReactivationArm}:
        raise ValueError("transition reactivation search spaces mismatch")
    if design.particle_budget != FROZEN_PARTICLE_BUDGET:
        raise ValueError("transition reactivation gate freezes K=24")
    if set(design.required_gain_families) | set(design.guardrail_families) != {
        family.family_id for family in families
    }:
        raise ValueError("transition reactivation family roles are incomplete")
    return design


def _load_and_verify_holdout_seeds(
    design: TransitionReactivationDesign,
    sealed_seed_path: Path,
) -> tuple[int, ...]:
    if _file_sha256(sealed_seed_path) != design.sealed_seed_file_sha256:
        raise ValueError("transition reactivation sealed seed hash mismatch")
    payload = json.loads(sealed_seed_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("transition reactivation sealed protocol mismatch")
    seeds = tuple(payload["holdout_seeds"])
    salt = payload["commitment_salt"]
    commitments = tuple(
        hashlib.sha256(f"{PROTOCOL_ID}:{seed}:{salt}".encode()).hexdigest() for seed in seeds
    )
    if commitments != design.holdout_seed_commitments:
        raise ValueError("transition reactivation commitments mismatch")
    if set(seeds) & set(design.validation_seeds):
        raise ValueError("transition reactivation validation/holdout overlap")
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


class ConflictAwareSequentialParticleRuntime(SequentialParticleRuntime):
    """Use a sharpened proposal only when current cause/regime conflicts with ancestry."""

    def __init__(self, *, profile: str) -> None:
        super().__init__(profile=profile)
        self.particles: tuple[PersistentParticle, ...] = tuple(getattr(self, "particles", ()))
        self.step_index = int(getattr(self, "step_index", 0))
        self.conflict_transition_receipts: list[str] = []

    def revise(self, belief: MultiAxisBelief) -> tuple[PersistentParticle, ...]:
        proposal_belief = belief
        if self.particles:
            dominant = max(
                self.particles,
                key=lambda item: (item.posterior_probability, item.signature),
            )
            modal_cause = max(
                belief.cause_posterior,
                key=lambda cause: (belief.cause_posterior[cause], cause.value),
            )
            proposed_regime_change = belief.regime_change_probability >= 0.5
            cause_conflict = (
                dominant.hypothesis.cause is not modal_cause
                and belief.cause_posterior[modal_cause] >= 0.35
            )
            regime_conflict = (
                dominant.hypothesis.regime_change != proposed_regime_change
                and abs(belief.regime_change_probability - 0.5) >= 0.15
            )
            if cause_conflict or regime_conflict:
                remaining = 0.15 / (len(ChangeCause) - 1)
                sharpened_cause = {
                    cause: (0.85 if cause is modal_cause else remaining) for cause in ChangeCause
                }
                proposal_belief = replace(
                    belief,
                    cause_posterior=sharpened_cause,
                    regime_change_probability=(0.85 if proposed_regime_change else 0.15),
                )
                uniform = 1.0 / len(self.particles)
                self.particles = tuple(
                    replace(particle, posterior_probability=uniform) for particle in self.particles
                )
                self.conflict_transition_receipts.append(
                    content_sha256(
                        {
                            "step_index": self.step_index + 1,
                            "parent_signature": dominant.signature,
                            "modal_cause": modal_cause.value,
                            "proposed_regime_change": proposed_regime_change,
                            "cause_conflict": cause_conflict,
                            "regime_conflict": regime_conflict,
                        }
                    )
                )
        return tuple(super().revise(proposal_belief))


class ReactivatingParticleLedger(AdaptiveParticleConsolidationLedger):
    """Immediate quarantine plus reversible reuse of a previously promoted regime."""

    def __init__(self) -> None:
        super().__init__(strategy=ConsolidationStrategy.IMMEDIATE_QUARANTINE)
        self.archived_distributions: dict[str, dict[UUID, float]] = {}
        self.reactivation_count = 0

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
        old_signature = self.active_signature
        active_distribution: Mapping[UUID, float] | None = getattr(
            self, "active_distribution", None
        )
        old_distribution = None if active_distribution is None else dict(active_distribution)
        archived = self.archived_distributions.get(dominant.signature)
        old_revision = self.active_revision_id
        super().update(particles, distribution, step_index=step_index)
        if old_signature is not None and old_distribution is not None:
            self.archived_distributions[old_signature] = old_distribution
        if (
            archived is not None
            and dominant.run_length >= self.stability_steps
            and self.active_revision_id != old_revision
            and self.active_signature == dominant.signature
        ):
            keys = set(archived) | set(distribution)
            values = {
                key: 0.55 * archived.get(key, 0.0) + 0.45 * distribution.get(key, 0.0)
                for key in keys
            }
            self.active_distribution = {
                key: float(value) for key, value in _normalize(values).items()
            }
            self._append(
                "reactivate",
                dominant,
                self.active_distribution,
                superseded_revision_id=old_revision,
                step_index=step_index,
            )
            self.reactivation_count += 1

    @property
    def operation_counts(self) -> dict[str, int]:
        return {**super().operation_counts, "reactivate": self.reactivation_count}


class _TransitionReactivationState(_SequentialMultiAxisActionState):
    def __init__(
        self,
        state: _FullProjectTwoMethod,
        episode: Any,
        *,
        profile: str,
        conflict_transition: bool,
        reactivation: bool,
    ) -> None:
        super().__init__(
            state,
            episode,
            profile=profile,
            consolidation=False,
        )
        if conflict_transition:
            self._runtime = ConflictAwareSequentialParticleRuntime(profile=profile)
        if reactivation:
            self._particle_ledger = ReactivatingParticleLedger()

    @property
    def conflict_transition_count(self) -> int:
        return len(getattr(self._runtime, "conflict_transition_receipts", ()))

    @property
    def reactivation_count(self) -> int:
        return int(getattr(self._particle_ledger, "reactivation_count", 0))


def _state_for_arm(
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    family: SequentialGateFamily,
    arm: TransitionReactivationArm,
    parameter: Any,
) -> Any:
    compatibility_arm = {
        TransitionReactivationArm.CORRECTED_AMG: CompatibilityArm.CORRECTED_AMG,
        TransitionReactivationArm.PER_STEP_PARTICLE: CompatibilityArm.PER_STEP_PARTICLE,
        TransitionReactivationArm.SEQUENTIAL_NO_CONSOLIDATION: (
            CompatibilityArm.SEQUENTIAL_NO_CONSOLIDATION
        ),
        TransitionReactivationArm.IMMEDIATE_QUARANTINE: (CompatibilityArm.IMMEDIATE_QUARANTINE),
    }.get(arm)
    if compatibility_arm is not None:
        return _compatibility_state_for_arm(
            dataset,
            episode,
            family,
            compatibility_arm,
            parameter,
        )
    base = _FullProjectTwoMethod(
        episode,
        owner_threshold=0.4,
        action_readout=_action_readout(),
    )
    state: Any = _TransitionReactivationState(
        base,
        episode,
        profile=str(parameter),
        conflict_transition=arm
        in {
            TransitionReactivationArm.CONFLICT_TRANSITION_NO_CONSOLIDATION,
            TransitionReactivationArm.JOINT_TRANSITION_REACTIVATION,
        },
        reactivation=arm
        in {
            TransitionReactivationArm.HISTORICAL_REACTIVATION,
            TransitionReactivationArm.JOINT_TRANSITION_REACTIVATION,
        },
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
    arm: TransitionReactivationArm,
    parameter: Any,
) -> GateReading:
    state = _state_for_arm(dataset, episode, family, arm, parameter)
    metric = evaluator.evaluate_custom_state(dataset, episode, state)
    return GateReading(
        metric=metric,
        verification_cost=float(getattr(state, "verification_cost", 0.0)),
        ancestry_edge_count=int(getattr(state, "ancestry_edge_count", 0)),
        operator_retention_receipt=getattr(state, "operator_retention_receipt", None),
        consumed_visible_stream_hash=str(getattr(state, "consumed_visible_stream_hash", "")),
        conflict_transition_count=int(getattr(state, "conflict_transition_count", 0)),
        reactivation_count=int(getattr(state, "reactivation_count", 0)),
        duplicate_promotion_count=int(getattr(state, "duplicate_promotion_count", 0)),
    )


def _summary(readings: list[GateReading]) -> dict[str, float]:
    return {
        "net_action_loss_per_step": mean(reading.net_action_loss_per_step for reading in readings),
        "put_back_error_rate": mean(reading.metric.put_back_error_rate for reading in readings),
        "persistent_owner_mode_error_rate": mean(
            reading.metric.persistent_owner_mode_error_rate for reading in readings
        ),
        "verification_cost": mean(reading.verification_cost for reading in readings),
        "mean_ancestry_edge_count": mean(reading.ancestry_edge_count for reading in readings),
        "conflict_transition_count": sum(reading.conflict_transition_count for reading in readings),
        "reactivation_count": sum(reading.reactivation_count for reading in readings),
        "duplicate_promotion_count": sum(reading.duplicate_promotion_count for reading in readings),
    }


def _bootstrap_ci(values: list[float], *, draws: int = 4000) -> tuple[float, float]:
    rng = random.Random(f"{PROTOCOL_ID}:paired-cluster-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


COMPARISONS = {
    "joint_minus_sequential_no_consolidation": (
        TransitionReactivationArm.JOINT_TRANSITION_REACTIVATION,
        TransitionReactivationArm.SEQUENTIAL_NO_CONSOLIDATION,
    ),
    "joint_minus_immediate_quarantine": (
        TransitionReactivationArm.JOINT_TRANSITION_REACTIVATION,
        TransitionReactivationArm.IMMEDIATE_QUARANTINE,
    ),
    "transition_no_consolidation_minus_sequential_no_consolidation": (
        TransitionReactivationArm.CONFLICT_TRANSITION_NO_CONSOLIDATION,
        TransitionReactivationArm.SEQUENTIAL_NO_CONSOLIDATION,
    ),
    "reactivation_minus_immediate_quarantine": (
        TransitionReactivationArm.HISTORICAL_REACTIVATION,
        TransitionReactivationArm.IMMEDIATE_QUARANTINE,
    ),
    "joint_minus_per_step": (
        TransitionReactivationArm.JOINT_TRANSITION_REACTIVATION,
        TransitionReactivationArm.PER_STEP_PARTICLE,
    ),
    "joint_minus_corrected_amg": (
        TransitionReactivationArm.JOINT_TRANSITION_REACTIVATION,
        TransitionReactivationArm.CORRECTED_AMG,
    ),
}


def run_transition_reactivation_gate(
    *,
    repository_root: Path,
) -> dict[str, Any]:
    manifest = repository_root / DEFAULT_MANIFEST
    sealed = repository_root / DEFAULT_SEALED_SEEDS
    design = load_frozen_transition_reactivation_design(manifest)
    evaluator = ProjectTwoActionBenchmarkV02()
    phase_audit = ["validation_tuning_started"]
    selected: dict[str, dict[TransitionReactivationArm, Any]] = {}
    validation_reports: dict[str, Any] = {}
    for family in design.families:
        dataset = _dataset(
            family,
            validation_seeds=design.validation_seeds,
            test_seeds=(107991,),
            max_steps=design.max_steps,
            split_label="validation",
        )
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
        selected[family.family_id] = {}
        validation_reports[family.family_id] = {}
        for arm in TransitionReactivationArm:
            candidates: list[dict[str, Any]] = []
            for parameter in design.search_spaces[arm.value]:
                validation_readings = [
                    _evaluate(evaluator, dataset, episode, family, arm, parameter)
                    for episode in episodes
                ]
                candidates.append(
                    {
                        "parameter": parameter,
                        "mean_net_action_loss_per_step": mean(
                            reading.net_action_loss_per_step for reading in validation_readings
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
    paired: dict[str, dict[str, list[float]]] = {
        commitment: {name: [] for name in COMPARISONS}
        for commitment in design.holdout_seed_commitments
    }
    operator_gates: dict[str, bool] = {}
    ancestry_gates: dict[str, bool] = {}
    transition_gates: dict[str, bool] = {}
    reactivation_gates: dict[str, bool] = {}
    exactly_once_gates: dict[str, bool] = {}
    for family_index, family in enumerate(design.families):
        dataset = _dataset(
            family,
            validation_seeds=(107991 + family_index,),
            test_seeds=holdout_seeds,
            max_steps=design.max_steps,
            split_label="sealed-holdout",
        )
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        holdout_readings: dict[TransitionReactivationArm, list[GateReading]] = {
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
            for arm in TransitionReactivationArm
        }
        for arm in TransitionReactivationArm:
            if arm is TransitionReactivationArm.CORRECTED_AMG:
                continue
            operator_gates[f"{family.family_id}:{arm.value}"] = all(
                reading.operator_retention_receipt == expected_operator_receipt
                for reading in holdout_readings[arm]
            )
            if arm is not TransitionReactivationArm.PER_STEP_PARTICLE:
                ancestry_gates[f"{family.family_id}:{arm.value}"] = all(
                    reading.ancestry_edge_count > 0 for reading in holdout_readings[arm]
                )
        for arm in (
            TransitionReactivationArm.CONFLICT_TRANSITION_NO_CONSOLIDATION,
            TransitionReactivationArm.JOINT_TRANSITION_REACTIVATION,
        ):
            transition_gates[f"{family.family_id}:{arm.value}"] = any(
                reading.conflict_transition_count > 0 for reading in holdout_readings[arm]
            )
        for arm in (
            TransitionReactivationArm.HISTORICAL_REACTIVATION,
            TransitionReactivationArm.JOINT_TRANSITION_REACTIVATION,
        ):
            reactivation_gates[f"{family.family_id}:{arm.value}"] = any(
                reading.reactivation_count > 0 for reading in holdout_readings[arm]
            )
            exactly_once_gates[f"{family.family_id}:{arm.value}"] = all(
                reading.duplicate_promotion_count == 0 for reading in holdout_readings[arm]
            )
        rows = []
        for index, commitment in enumerate(design.holdout_seed_commitments):
            hashes = {
                arm.value: holdout_readings[arm][index].consumed_visible_stream_hash
                for arm in TransitionReactivationArm
            }
            if len(set(hashes.values())) != 1:
                raise ValueError("transition reactivation consumed stream mismatch")
            losses = {
                arm.value: holdout_readings[arm][index].net_action_loss_per_step
                for arm in TransitionReactivationArm
            }
            differences = {
                name: losses[left.value] - losses[right.value]
                for name, (left, right) in COMPARISONS.items()
            }
            for name, value in differences.items():
                paired[commitment][name].append(value)
            rows.append(
                {
                    "holdout_seed_commitment": commitment,
                    "consumed_visible_stream_hash": next(iter(hashes.values())),
                    "consumed_visible_stream_hash_by_arm": hashes,
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
            "paired_holdout_rows": rows,
        }
    clustered = {
        name: [mean(paired[commitment][name]) for commitment in design.holdout_seed_commitments]
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
    primary = "joint_minus_sequential_no_consolidation"
    family_primary = {
        family_id: mean(row["paired_differences"][primary] for row in report["paired_holdout_rows"])
        for family_id, report in family_reports.items()
    }
    gate_criteria = {
        "primary_ci_upper_below_zero": comparisons[primary]["confidence_interval_95"][1] < 0.0,
        "required_cause_gain": family_primary[design.required_gain_families[0]] < 0.0,
        "required_reactivation_gain": family_primary[design.required_gain_families[1]] < 0.0,
        "identity_guardrail": family_primary[design.guardrail_families[0]]
        <= design.guardrail_noninferiority_margin,
        "role_guardrail": family_primary[design.guardrail_families[1]]
        <= design.guardrail_noninferiority_margin,
        "all_operator_gates": all(operator_gates.values()),
        "all_ancestry_gates": all(ancestry_gates.values()),
        "all_transition_gates": all(transition_gates.values()),
        "all_reactivation_gates": all(reactivation_gates.values()),
        "all_exactly_once_gates": all(exactly_once_gates.values()),
    }
    provenance_paths = {
        "benchmark_source_sha256": Path(__file__).resolve(),
        "sequential_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_sequential_gate.py",
        "compatibility_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_consolidation_compatibility.py",
        "action_evaluator_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/project_two_action_benchmark.py",
        "manifest_file_sha256": manifest,
        "sealed_seed_file_sha256": sealed,
        "preregistration_sha256": repository_root / DEFAULT_PREREGISTRATION,
    }
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": "D0 synthetic mechanism evidence; not paper evidence",
        "neural_proposer_status": "not_run_by_preregistered_design",
        "particle_budget": design.particle_budget,
        "holdout_seed_commitments": list(design.holdout_seed_commitments),
        "raw_holdout_seeds_disclosed": False,
        "phase_audit": phase_audit,
        "validation": validation_reports,
        "families": family_reports,
        "paired_cluster_comparisons": comparisons,
        "family_primary_differences": family_primary,
        "runtime_operator_gates": operator_gates,
        "ancestry_gates": ancestry_gates,
        "transition_gates": transition_gates,
        "reactivation_gates": reactivation_gates,
        "exactly_once_gates": exactly_once_gates,
        "gate_criteria": gate_criteria,
        "mechanism_gate_passed": all(gate_criteria.values()),
        "provenance": {key: _file_sha256(path) for key, path in provenance_paths.items()},
        "limitations": [
            "D0 synthetic mechanism evidence only",
            "deterministic conflict-aware proposal rather than neural proposer",
            "repository-local sealed seeds",
            "corrected AMG remains a matched adapter",
            "no RGB-D or robot execution evidence",
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_transition_reactivation_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_transition_reactivation_report(
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
        raise ValueError("transition reactivation content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("transition reactivation protocol mismatch")
    design = load_frozen_transition_reactivation_design(repository_root / DEFAULT_MANIFEST)
    seeds = _load_and_verify_holdout_seeds(design, repository_root / DEFAULT_SEALED_SEEDS)
    if tuple(report.get("holdout_seed_commitments", ())) != design.holdout_seed_commitments:
        raise ValueError("transition reactivation commitment mismatch")
    if any(seed in json.dumps(report) for seed in map(str, seeds)):
        raise ValueError("transition reactivation raw seed disclosure")
    if recompute:
        expected = run_transition_reactivation_gate(repository_root=repository_root)
        if expected["content_sha256"] != report["content_sha256"]:
            raise ValueError("transition reactivation deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_MANIFEST",
    "DEFAULT_PREREGISTRATION",
    "DEFAULT_SEALED_SEEDS",
    "PROTOCOL_ID",
    "ConflictAwareSequentialParticleRuntime",
    "ReactivatingParticleLedger",
    "TransitionReactivationArm",
    "TransitionReactivationDesign",
    "load_frozen_transition_reactivation_design",
    "run_transition_reactivation_gate",
    "verify_transition_reactivation_report",
    "write_transition_reactivation_report",
]
