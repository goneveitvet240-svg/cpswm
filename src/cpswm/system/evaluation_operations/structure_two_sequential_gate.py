"""Frozen mechanism gate for sequential particles and reversible consolidation."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from itertools import product
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import UUID

from cpswm.contracts import ProjectTwoDatasetSplit, ProjectTwoReplayStep
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ActionCaseMetric,
    ProjectTwoActionBenchmarkV02,
    _AMGOpenWorldMethod,
    _FullProjectTwoMethod,
    _Prediction,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_factorial_benchmark import _CIAVState
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (
    PROFILE_SCALE,
    MultiAxisBelief,
    _action_readout,
    _ActionParticle,
    _argmax_distribution,
    _blend_location,
    _cause_posterior,
    _FamilyFeedbackState,
    _file_sha256,
    _identity_probability,
    _joint_penalties,
    _MultiAxisActionState,
    _normalize,
    _particle_action_strength,
    _particle_prior_log_weight,
    _rank_distribution,
    _VisibleTransformState,
)
from cpswm.system.evaluation_operations.structure_two_rejuvenation_gate import (
    FROZEN_PARTICLE_BUDGET,
)
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.world_model.habits_transitions import ChangeCause

PROTOCOL_ID = "structure-two-sequential-consolidation-gate@0.1"
DEFAULT_MANIFEST = Path(
    "configs/project_two_experiments/structure_two_sequential_gate_manifest_v0_1.json"
)
DEFAULT_SEALED_SEEDS = Path(
    "configs/project_two_experiments/structure_two_sequential_gate_sealed_seeds_v0_1.json"
)
DEFAULT_PREREGISTRATION = Path(
    "docs/experiments/structure_two_sequential_consolidation_gate_preregistration_2026-08-29.md"
)


class SequentialGateArm(StrEnum):
    CORRECTED_AMG = "corrected_amg"
    OLD_FULL_MULTIAXIS = "old_full_multiaxis"
    PER_STEP_PARTICLE = "per_step_particle_projection"
    SEQUENTIAL_NO_CONSOLIDATION = "sequential_particle_no_consolidation"
    SEQUENTIAL_CONSOLIDATION = "sequential_particle_reversible_consolidation"


@dataclass(frozen=True, slots=True)
class SequentialGateFamily:
    family_id: str
    family_role: str
    guest_window: tuple[int, int]
    abrupt_day: int
    recurrence_day: int
    observation_coverage: float
    unknown_event_days: tuple[int, ...]
    actor_ambiguity_mix: float
    identity_confidence_scale: float
    feedback_flip_rate: float
    decoy_days: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SequentialGateDesign:
    validation_seeds: tuple[int, ...]
    holdout_seed_commitments: tuple[str, ...]
    sealed_holdout_seed_count: int
    sealed_seed_file_sha256: str
    max_steps: int
    particle_budget: int
    families: tuple[SequentialGateFamily, ...]
    search_spaces: Mapping[str, tuple[Any, ...]]
    required_family_gains: tuple[str, ...]
    guardrail_families: tuple[str, ...]
    guardrail_noninferiority_margin: float
    manifest_file_sha256: str


@dataclass(frozen=True, slots=True)
class PersistentParticle:
    hypothesis: _ActionParticle
    particle_id: UUID
    parent_particle_id: UUID | None
    revision_id: UUID
    posterior_probability: float
    run_length: int

    @property
    def signature(self) -> str:
        return str(self.hypothesis.key)


@dataclass(frozen=True, slots=True)
class ParticleLedgerRecord:
    operation: str
    revision_id: UUID
    superseded_revision_id: UUID | None
    hypothesis_signature: str
    location_distribution: Mapping[UUID, float]
    step_index: int
    previous_hash: str
    record_hash: str


@dataclass(frozen=True, slots=True)
class SequentialReading:
    metric: ActionCaseMetric
    verification_cost: float
    axis_trace_count: int
    ancestry_edge_count: int
    ledger_operation_counts: Mapping[str, int]
    duplicate_promotion_count: int
    operator_retention_receipt: Mapping[str, Any] | None
    consumed_visible_stream_hash: str

    @property
    def net_action_loss_per_step(self) -> float:
        return float(
            (self.metric.cumulative_action_regret + self.verification_cost)
            / max(1, self.metric.step_count)
        )


def load_frozen_sequential_gate_design(
    manifest_path: Path = DEFAULT_MANIFEST,
) -> SequentialGateDesign:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("sequential gate manifest protocol mismatch")
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
    design = SequentialGateDesign(
        validation_seeds=tuple(payload["validation_seeds"]),
        holdout_seed_commitments=tuple(payload["sealed_holdout_seed_commitments"]),
        sealed_holdout_seed_count=payload["sealed_holdout_seed_count"],
        sealed_seed_file_sha256=payload["sealed_seed_file_sha256"],
        max_steps=payload["max_steps"],
        particle_budget=payload["particle_budget"],
        families=families,
        search_spaces={key: tuple(value) for key, value in payload["search_spaces"].items()},
        required_family_gains=tuple(payload["required_family_gains"]),
        guardrail_families=tuple(payload["guardrail_families"]),
        guardrail_noninferiority_margin=float(payload["guardrail_noninferiority_margin"]),
        manifest_file_sha256=_file_sha256(manifest_path),
    )
    if len(families) != 4 or len({family.family_id for family in families}) != 4:
        raise ValueError("sequential gate requires four unique scenario families")
    if set(design.search_spaces) != {arm.value for arm in SequentialGateArm}:
        raise ValueError("sequential gate search spaces do not match frozen arms")
    if design.particle_budget != FROZEN_PARTICLE_BUDGET:
        raise ValueError("sequential gate freezes K=24")
    if set(design.required_family_gains) | set(design.guardrail_families) != {
        family.family_id for family in families
    }:
        raise ValueError("sequential gate family roles are incomplete")
    if len(design.holdout_seed_commitments) != design.sealed_holdout_seed_count:
        raise ValueError("sequential gate commitment count mismatch")
    return design


def _load_and_verify_holdout_seeds(
    design: SequentialGateDesign,
    sealed_seed_path: Path,
) -> tuple[int, ...]:
    if _file_sha256(sealed_seed_path) != design.sealed_seed_file_sha256:
        raise ValueError("sequential gate sealed seed file hash mismatch")
    payload = json.loads(sealed_seed_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("sequential gate sealed seed protocol mismatch")
    seeds = tuple(payload["holdout_seeds"])
    salt = payload["commitment_salt"]
    commitments = tuple(
        hashlib.sha256(f"{PROTOCOL_ID}:{seed}:{salt}".encode()).hexdigest() for seed in seeds
    )
    if commitments != design.holdout_seed_commitments:
        raise ValueError("sequential gate holdout commitments mismatch")
    if set(seeds) & set(design.validation_seeds):
        raise ValueError("sequential gate validation and holdout seeds overlap")
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


def _visible_transform(
    family: SequentialGateFamily,
    episode: Any,
) -> Any:
    step_days = {step.step_id: index + 1 for index, step in enumerate(episode.steps)}

    def transform(step: ProjectTwoReplayStep) -> ProjectTwoReplayStep:
        update: dict[str, Any] = {}
        if step.actor_evidence is not None:
            actor_evidence = step.actor_evidence
            posterior = {
                actor: (1.0 - family.actor_ambiguity_mix) * probability
                + family.actor_ambiguity_mix * actor_evidence.reference_actor_prior[actor]
                for actor, probability in actor_evidence.actor_posterior.items()
            }
            update["actor_evidence"] = actor_evidence.model_copy(
                update={"actor_posterior": posterior}
            )
        if step.ordered_role_evidence is not None:
            role_evidence = step.ordered_role_evidence
            posterior = {
                role: (1.0 - family.actor_ambiguity_mix) * probability
                + family.actor_ambiguity_mix * role_evidence.reference_ordered_role_prior[role]
                for role, probability in role_evidence.ordered_role_posterior.items()
            }
            update["ordered_role_evidence"] = role_evidence.model_copy(
                update={"ordered_role_posterior": posterior}
            )
        if step.detection_confidence is not None:
            update["detection_confidence"] = min(
                1.0,
                max(
                    0.0,
                    0.5 + family.identity_confidence_scale * (step.detection_confidence - 0.5),
                ),
            )
        day = step_days[step.step_id]
        if day in family.decoy_days and step.after is not None:
            decoy_id = content_uuid("sequential-gate-decoy", (episode.scene_id, day))
            after = step.after.model_copy(update={"detected_object_instance_id": decoy_id})
            update["after"] = after
            update["detection_confidence"] = 0.92
            if step.unified_evidence is not None:
                update["unified_evidence"] = step.unified_evidence.model_copy(
                    update={"detected_object_key": str(decoy_id)}
                )
        return step.model_copy(update=update)

    return transform


def _softmax(log_weights: list[float]) -> list[float]:
    maximum = max(log_weights)
    masses = [math.exp(value - maximum) for value in log_weights]
    total = sum(masses)
    return [value / total for value in masses]


def _transition_log_weight(
    parent: PersistentParticle,
    child: _ActionParticle,
    belief: MultiAxisBelief,
    *,
    persistence: float,
) -> float:
    same_actor = parent.hypothesis.actor_key == child.actor_key
    same_identity = parent.hypothesis.identity_target == child.identity_target
    same_cause = parent.hypothesis.cause is child.cause
    same_regime = parent.hypothesis.regime_change == child.regime_change
    stability = (
        0.55 * float(same_actor)
        + 1.20 * float(same_identity)
        + 0.80 * float(same_cause)
        + 0.55 * float(same_regime)
    )
    change_release = belief.regime_change_probability * (
        0.9 * float(not same_cause) + 0.6 * float(not same_regime)
    )
    return float(persistence * stability + change_release)


class SequentialParticleRuntime:
    """Deterministic K=24 SMC runtime with explicit temporal ancestry."""

    def __init__(self, *, profile: str, particle_budget: int = FROZEN_PARTICLE_BUDGET):
        if particle_budget != FROZEN_PARTICLE_BUDGET:
            raise ValueError("sequential particle runtime freezes K=24")
        self.profile = profile
        self.particle_budget = particle_budget
        self.particles: tuple[PersistentParticle, ...] = ()
        self.step_index = 0
        self.ancestry_trace: list[tuple[UUID, UUID]] = []
        self.resampling_receipts: list[str] = []

    def revise(self, belief: MultiAxisBelief) -> tuple[PersistentParticle, ...]:
        self.step_index += 1
        scale = PROFILE_SCALE[self.profile]
        persistence = {"conservative": 1.30, "balanced": 0.90, "responsive": 0.55}[self.profile]
        hypotheses = tuple(
            _ActionParticle(*values)
            for values in product(
                tuple(sorted(belief.actor_posterior)),
                (False, True),
                tuple(ChangeCause),
                (False, True),
            )
        )
        scored: list[tuple[float, _ActionParticle, PersistentParticle | None]] = []
        for hypothesis in hypotheses:
            structural = sum(
                item.log_potential for item in _joint_penalties(belief, hypothesis, strength=scale)
            )
            if not self.particles:
                scored.append(
                    (_particle_prior_log_weight(belief, hypothesis) + structural, hypothesis, None)
                )
                continue
            best_parent = max(
                self.particles,
                key=lambda item: (
                    math.log(max(item.posterior_probability, 1e-12))
                    + _transition_log_weight(item, hypothesis, belief, persistence=persistence),
                    item.signature,
                ),
            )
            score = (
                _particle_prior_log_weight(belief, hypothesis)
                + structural
                + math.log(max(best_parent.posterior_probability, 1e-12))
                + _transition_log_weight(best_parent, hypothesis, belief, persistence=persistence)
            )
            scored.append((score, hypothesis, best_parent))
        selected = sorted(scored, key=lambda item: (-item[0], item[1].key))[: self.particle_budget]
        weights = _softmax([item[0] for item in selected])
        snapshot_id = content_uuid("sequential-gate-snapshot", (self.step_index, asdict(belief)))
        revised = []
        for rank, ((_, hypothesis, candidate_parent), weight) in enumerate(
            zip(selected, weights, strict=True)
        ):
            particle_id = content_uuid(
                "sequential-gate-particle",
                (
                    snapshot_id,
                    rank,
                    hypothesis.key,
                    None if candidate_parent is None else candidate_parent.particle_id,
                ),
            )
            revision_id = content_uuid("sequential-gate-revision", (snapshot_id, hypothesis.key))
            revised.append(
                PersistentParticle(
                    hypothesis=hypothesis,
                    particle_id=particle_id,
                    parent_particle_id=(
                        None if candidate_parent is None else candidate_parent.particle_id
                    ),
                    revision_id=revision_id,
                    posterior_probability=weight,
                    run_length=(
                        0
                        if candidate_parent is None
                        or candidate_parent.hypothesis.key != hypothesis.key
                        else candidate_parent.run_length + 1
                    ),
                )
            )
            if candidate_parent is not None:
                self.ancestry_trace.append((candidate_parent.particle_id, particle_id))
        self.particles = tuple(revised)
        self.resampling_receipts.append(
            content_sha256(
                [
                    (
                        item.signature,
                        str(item.parent_particle_id),
                        item.posterior_probability,
                        item.run_length,
                    )
                    for item in self.particles
                ]
            )
        )
        return self.particles

    def action_distribution(self, belief: MultiAxisBelief) -> dict[UUID, float]:
        scale = PROFILE_SCALE[self.profile]
        trust = sum(
            particle.posterior_probability
            * (
                _particle_action_strength(particle.hypothesis, scale=scale)
                if particle.hypothesis.actor_key == belief.owner_actor_key
                else 0.0
            )
            for particle in self.particles
        )
        return dict(_blend_location(belief, trust=trust))


class ReversibleParticleConsolidationLedger:
    """Append-only particle ledger with exactly-once promotion and correction."""

    def __init__(self, *, stability_steps: int = 2, promotion_floor: float = 0.10):
        self.stability_steps = stability_steps
        self.promotion_floor = promotion_floor
        self.records: list[ParticleLedgerRecord] = []
        self.promoted_revision_ids: set[UUID] = set()
        self.active_revision_id: UUID | None = None
        self.active_signature: str | None = None
        self.active_distribution: dict[UUID, float] | None = None
        self.duplicate_promotion_count = 0

    @property
    def head_hash(self) -> str:
        return self.records[-1].record_hash if self.records else "GENESIS"

    def _append(
        self,
        operation: str,
        particle: PersistentParticle,
        distribution: Mapping[UUID, float],
        *,
        superseded_revision_id: UUID | None = None,
        step_index: int,
    ) -> None:
        payload = {
            "operation": operation,
            "revision_id": str(particle.revision_id),
            "superseded_revision_id": (
                None if superseded_revision_id is None else str(superseded_revision_id)
            ),
            "hypothesis_signature": particle.signature,
            "location_distribution": sorted(
                (str(key), value) for key, value in distribution.items()
            ),
            "step_index": step_index,
            "previous_hash": self.head_hash,
        }
        self.records.append(
            ParticleLedgerRecord(
                operation=operation,
                revision_id=particle.revision_id,
                superseded_revision_id=superseded_revision_id,
                hypothesis_signature=particle.signature,
                location_distribution=dict(distribution),
                step_index=step_index,
                previous_hash=self.head_hash,
                record_hash=content_sha256(payload),
            )
        )

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
        if dominant.posterior_probability < self.promotion_floor:
            return
        self._append("quarantine", dominant, distribution, step_index=step_index)
        if dominant.run_length < self.stability_steps:
            return
        if self.active_signature == dominant.signature:
            return
        if dominant.revision_id in self.promoted_revision_ids:
            self.duplicate_promotion_count += 1
            return
        if self.active_revision_id is None:
            operation = "promote"
            superseded = None
        else:
            superseded = self.active_revision_id
            self._append(
                "retract",
                dominant,
                distribution,
                superseded_revision_id=superseded,
                step_index=step_index,
            )
            operation = "corrected_revision"
        self._append(
            operation,
            dominant,
            distribution,
            superseded_revision_id=superseded,
            step_index=step_index,
        )
        self.promoted_revision_ids.add(dominant.revision_id)
        self.active_revision_id = dominant.revision_id
        self.active_signature = dominant.signature
        self.active_distribution = dict(distribution)

    def blend(self, distribution: Mapping[UUID, float]) -> dict[UUID, float]:
        if self.active_distribution is None:
            return dict(distribution)
        keys = set(distribution) | set(self.active_distribution)
        values = {
            key: 0.72 * distribution.get(key, 0.0) + 0.28 * self.active_distribution.get(key, 0.0)
            for key in keys
        }
        normalized = _normalize(values)
        return {key: float(value) for key, value in normalized.items()}

    @property
    def operation_counts(self) -> dict[str, int]:
        return {
            operation: sum(record.operation == operation for record in self.records)
            for operation in ("quarantine", "promote", "retract", "corrected_revision")
        }


class _DecoyAwareMultiAxisActionState(_MultiAxisActionState):
    """Route decoys to the target spine while retaining raw identity evidence."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._identity_overrides: dict[UUID, float] = {}

    def set_identity_probability_override(self, step_id: UUID, probability: float) -> None:
        self._identity_overrides[step_id] = probability

    def observe(self, step: ProjectTwoReplayStep) -> None:
        self._state.observe(step)
        transformed = self._state.evidence_transform(step)
        result = self._state.step_results.get(step.step_id)
        if result is None or transformed.after is None:
            return
        observed = transformed.after.detected_location_id
        if observed is None:
            return
        base = self._state.spine.action_location_distribution(
            self._state.spine.current_snapshot,
            readout=self._state.action_readout,
        )
        identity_probability = self._identity_overrides.pop(
            step.step_id,
            _identity_probability(
                transformed,
                target_object_id=transformed.object_instance_id,
            ),
        )
        self._belief = MultiAxisBelief(
            actor_posterior=_normalize(result.actor_posterior),
            owner_actor_key=self._episode.owner_actor_key,
            identity_target_probability=identity_probability,
            cause_posterior=_cause_posterior(self._state),
            regime_change_probability=result.decision.change_probability,
            active_regime=result.active_regime,
            observed_location_id=observed,
            base_location_distribution=base,
        )


class _SequentialMultiAxisActionState(_DecoyAwareMultiAxisActionState):
    def __init__(
        self,
        state: _FullProjectTwoMethod,
        episode: Any,
        *,
        profile: str,
        consolidation: bool,
    ) -> None:
        super().__init__(
            state,
            episode,
            profile=profile,
            joint_revision=False,
        )
        self._runtime = SequentialParticleRuntime(profile=profile)
        self._particle_ledger = ReversibleParticleConsolidationLedger() if consolidation else None

    def observe(self, step: ProjectTwoReplayStep) -> None:
        super().observe(step)
        if self._belief is not None:
            self._runtime.revise(self._belief)

    def predict(self) -> _Prediction:
        native = self._state.predict()
        if self._belief is None or not self._runtime.particles:
            return native
        belief = replace(
            self._belief,
            base_location_distribution=self._state.spine.action_location_distribution(
                self._state.spine.current_snapshot,
                readout=self._state.action_readout,
            ),
        )
        distribution = self._runtime.action_distribution(belief)
        if self._particle_ledger is not None:
            self._particle_ledger.update(
                self._runtime.particles,
                distribution,
                step_index=self._runtime.step_index,
            )
            distribution = self._particle_ledger.blend(distribution)
        trace = {
            "actor_posterior": sorted(belief.actor_posterior.items()),
            "identity_target_probability": belief.identity_target_probability,
            "cause_posterior": sorted(
                (key.value, value) for key, value in belief.cause_posterior.items()
            ),
            "regime_change_probability": belief.regime_change_probability,
            "active_regime": belief.active_regime,
            "particle_ids": [str(item.particle_id) for item in self._runtime.particles],
            "parent_particle_ids": [
                None if item.parent_particle_id is None else str(item.parent_particle_id)
                for item in self._runtime.particles
            ],
            "ledger_head": (
                None if self._particle_ledger is None else self._particle_ledger.head_hash
            ),
            "action_distribution": sorted((str(key), value) for key, value in distribution.items()),
        }
        self.axis_trace_hashes.append(content_sha256(trace))
        self.axis_trace_count += 1
        for axis in self.axis_consumption_counts:
            self.axis_consumption_counts[axis] += 1
        return _Prediction(
            put_back=_argmax_distribution(distribution),
            search_order=_rank_distribution(distribution),
            unknown_probability=native.unknown_probability,
        )

    @property
    def ancestry_edge_count(self) -> int:
        return len(self._runtime.ancestry_trace)

    @property
    def ledger_operation_counts(self) -> dict[str, int]:
        if self._particle_ledger is None:
            return dict.fromkeys(("quarantine", "promote", "retract", "corrected_revision"), 0)
        return self._particle_ledger.operation_counts

    @property
    def duplicate_promotion_count(self) -> int:
        return (
            0 if self._particle_ledger is None else self._particle_ledger.duplicate_promotion_count
        )


class _TargetObjectRoutingState:
    """Auditable adapter from multi-object detections to a target-object spine."""

    def __init__(self, state: Any) -> None:
        self._state = state
        self.decoy_route_count = 0
        self.decoy_route_receipts: list[str] = []

    def observe(self, step: ProjectTwoReplayStep) -> None:
        routed = step
        if (
            step.after is not None
            and step.after.detected_object_instance_id is not None
            and step.after.detected_object_instance_id != step.object_instance_id
        ):
            confidence = step.detection_confidence if step.detection_confidence is not None else 0.5
            if hasattr(self._state, "set_identity_probability_override"):
                self._state.set_identity_probability_override(step.step_id, 1.0 - confidence)
            after = step.after.model_copy(
                update={"detected_object_instance_id": step.object_instance_id}
            )
            update: dict[str, Any] = {"after": after}
            if step.unified_evidence is not None:
                update["unified_evidence"] = step.unified_evidence.model_copy(
                    update={"detected_object_key": str(step.object_instance_id)}
                )
            routed = step.model_copy(update=update)
            self.decoy_route_count += 1
            self.decoy_route_receipts.append(
                content_sha256(
                    {
                        "step_id": str(step.step_id),
                        "raw_detected_object": str(step.after.detected_object_instance_id),
                        "routed_object": str(step.object_instance_id),
                        "target_probability": 1.0 - confidence,
                    }
                )
            )
        self._state.observe(routed)

    def predict(self) -> Any:
        return self._state.predict()

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        routed = step
        if (
            step.after is not None
            and step.after.detected_object_instance_id is not None
            and step.after.detected_object_instance_id != step.object_instance_id
        ):
            after = step.after.model_copy(
                update={"detected_object_instance_id": step.object_instance_id}
            )
            update: dict[str, Any] = {"after": after}
            if step.unified_evidence is not None:
                update["unified_evidence"] = step.unified_evidence.model_copy(
                    update={"detected_object_key": str(step.object_instance_id)}
                )
            routed = step.model_copy(update=update)
        self._state.feedback(routed)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._state, name)


def _state_for_arm(
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    family: SequentialGateFamily,
    arm: SequentialGateArm,
    parameter: Any,
) -> Any:
    transform = _visible_transform(family, episode)
    if arm is SequentialGateArm.CORRECTED_AMG:
        state: Any = _AMGOpenWorldMethod(episode, mode="amg", parameter=float(parameter))
        state = _TargetObjectRoutingState(state)
        state = _VisibleTransformState(state, transform)
        return _FamilyFeedbackState(state, family, episode)
    base = _FullProjectTwoMethod(
        episode,
        owner_threshold=0.4,
        action_readout=_action_readout(),
    )
    if arm is SequentialGateArm.OLD_FULL_MULTIAXIS:
        state = _DecoyAwareMultiAxisActionState(
            base,
            episode,
            profile=str(parameter),
            joint_revision=False,
        )
    elif arm is SequentialGateArm.PER_STEP_PARTICLE:
        state = _DecoyAwareMultiAxisActionState(
            base,
            episode,
            profile=str(parameter),
            joint_revision=True,
        )
    else:
        state = _SequentialMultiAxisActionState(
            base,
            episode,
            profile=str(parameter),
            consolidation=arm is SequentialGateArm.SEQUENTIAL_CONSOLIDATION,
        )
    state = _CIAVState(state, dataset, episode, enabled=True, cost_multiplier=1.0)
    state.operator_retention_receipt = {
        **state.operator_retention_receipt,
        "ciav": bool(state._enabled),
    }
    state = _TargetObjectRoutingState(state)
    state = _VisibleTransformState(state, transform)
    return _FamilyFeedbackState(state, family, episode)


def _evaluate(
    evaluator: ProjectTwoActionBenchmarkV02,
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    family: SequentialGateFamily,
    arm: SequentialGateArm,
    parameter: Any,
) -> SequentialReading:
    state = _state_for_arm(dataset, episode, family, arm, parameter)
    metric = evaluator.evaluate_custom_state(dataset, episode, state)
    return SequentialReading(
        metric=metric,
        verification_cost=float(getattr(state, "verification_cost", 0.0)),
        axis_trace_count=int(getattr(state, "axis_trace_count", 0)),
        ancestry_edge_count=int(getattr(state, "ancestry_edge_count", 0)),
        ledger_operation_counts=dict(getattr(state, "ledger_operation_counts", {})),
        duplicate_promotion_count=int(getattr(state, "duplicate_promotion_count", 0)),
        operator_retention_receipt=getattr(state, "operator_retention_receipt", None),
        consumed_visible_stream_hash=str(getattr(state, "consumed_visible_stream_hash", "")),
    )


def _summary(readings: list[SequentialReading]) -> dict[str, float]:
    return {
        "net_action_loss_per_step": mean(item.net_action_loss_per_step for item in readings),
        "put_back_error_rate": mean(item.metric.put_back_error_rate for item in readings),
        "persistent_owner_mode_error_rate": mean(
            item.metric.persistent_owner_mode_error_rate for item in readings
        ),
        "owner_habit_contamination": mean(
            item.metric.owner_habit_contamination for item in readings
        ),
        "unknown_calibration_brier": mean(
            item.metric.unknown_calibration_brier for item in readings
        ),
        "verification_cost": mean(item.verification_cost for item in readings),
        "mean_axis_trace_count": mean(item.axis_trace_count for item in readings),
        "mean_ancestry_edge_count": mean(item.ancestry_edge_count for item in readings),
        "mean_promote_count": mean(
            item.ledger_operation_counts.get("promote", 0) for item in readings
        ),
        "mean_retract_count": mean(
            item.ledger_operation_counts.get("retract", 0) for item in readings
        ),
        "mean_corrected_revision_count": mean(
            item.ledger_operation_counts.get("corrected_revision", 0) for item in readings
        ),
        "duplicate_promotion_count": sum(item.duplicate_promotion_count for item in readings),
    }


def _bootstrap_ci(values: list[float], *, draws: int = 4000) -> tuple[float, float]:
    rng = random.Random(f"{PROTOCOL_ID}:paired-cluster-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


COMPARISONS = {
    "sequential_consolidation_minus_per_step": (
        SequentialGateArm.SEQUENTIAL_CONSOLIDATION,
        SequentialGateArm.PER_STEP_PARTICLE,
    ),
    "sequential_no_consolidation_minus_per_step": (
        SequentialGateArm.SEQUENTIAL_NO_CONSOLIDATION,
        SequentialGateArm.PER_STEP_PARTICLE,
    ),
    "sequential_consolidation_minus_no_consolidation": (
        SequentialGateArm.SEQUENTIAL_CONSOLIDATION,
        SequentialGateArm.SEQUENTIAL_NO_CONSOLIDATION,
    ),
    "sequential_consolidation_minus_corrected_amg": (
        SequentialGateArm.SEQUENTIAL_CONSOLIDATION,
        SequentialGateArm.CORRECTED_AMG,
    ),
    "old_full_minus_corrected_amg": (
        SequentialGateArm.OLD_FULL_MULTIAXIS,
        SequentialGateArm.CORRECTED_AMG,
    ),
}


def run_sequential_consolidation_gate(
    *,
    repository_root: Path,
    manifest_path: Path | None = None,
    sealed_seed_path: Path | None = None,
) -> dict[str, Any]:
    manifest = manifest_path or repository_root / DEFAULT_MANIFEST
    sealed = sealed_seed_path or repository_root / DEFAULT_SEALED_SEEDS
    design = load_frozen_sequential_gate_design(manifest)
    evaluator = ProjectTwoActionBenchmarkV02()
    phase_audit = ["validation_tuning_started"]
    selected: dict[str, dict[SequentialGateArm, Any]] = {}
    validation_reports: dict[str, Any] = {}
    for family in design.families:
        dataset = _dataset(
            family,
            validation_seeds=design.validation_seeds,
            test_seeds=(83991,),
            max_steps=design.max_steps,
            split_label="validation",
        )
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
        selected[family.family_id] = {}
        validation_reports[family.family_id] = {}
        for arm in SequentialGateArm:
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
                            item.net_action_loss_per_step for item in validation_readings
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
    phase_audit.extend(
        (
            "validation_tuning_completed",
            "sealed_seed_file_open_requested",
        )
    )
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
    full_arms = tuple(
        arm for arm in SequentialGateArm if arm is not SequentialGateArm.CORRECTED_AMG
    )
    family_reports: dict[str, Any] = {}
    paired_by_commitment: dict[str, dict[str, list[float]]] = {
        commitment: {name: [] for name in COMPARISONS}
        for commitment in design.holdout_seed_commitments
    }
    operator_gates: dict[str, bool] = {}
    ancestry_gates: dict[str, bool] = {}
    ledger_gates: dict[str, bool] = {}
    for family_index, family in enumerate(design.families):
        dataset = _dataset(
            family,
            validation_seeds=(83991 + family_index,),
            test_seeds=holdout_seeds,
            max_steps=design.max_steps,
            split_label="sealed-holdout",
        )
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        holdout_readings: dict[SequentialGateArm, list[SequentialReading]] = {
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
            for arm in SequentialGateArm
        }
        for arm in full_arms:
            operator_gates[f"{family.family_id}:{arm.value}"] = all(
                item.operator_retention_receipt == expected_operator_receipt
                for item in holdout_readings[arm]
            )
        for arm in (
            SequentialGateArm.SEQUENTIAL_NO_CONSOLIDATION,
            SequentialGateArm.SEQUENTIAL_CONSOLIDATION,
        ):
            ancestry_gates[f"{family.family_id}:{arm.value}"] = all(
                item.ancestry_edge_count > 0 for item in holdout_readings[arm]
            )
        ledger_gates[family.family_id] = all(
            item.ledger_operation_counts.get("promote", 0) > 0
            and item.duplicate_promotion_count == 0
            for item in holdout_readings[SequentialGateArm.SEQUENTIAL_CONSOLIDATION]
        )
        paired_rows = []
        for index, commitment in enumerate(design.holdout_seed_commitments):
            consumed_hashes = {
                arm.value: holdout_readings[arm][index].consumed_visible_stream_hash
                for arm in SequentialGateArm
            }
            if len(set(consumed_hashes.values())) != 1:
                raise ValueError("sequential gate consumed stream mismatch")
            losses = {
                arm.value: holdout_readings[arm][index].net_action_loss_per_step
                for arm in SequentialGateArm
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
    primary_name = "sequential_consolidation_minus_per_step"
    family_primary: dict[str, float] = {
        family_id: mean(
            row["paired_differences"][primary_name] for row in family_report["paired_holdout_rows"]
        )
        for family_id, family_report in family_reports.items()
    }
    gate_criteria = {
        "primary_ci_upper_below_zero": comparisons[primary_name]["confidence_interval_95"][1] < 0.0,
        "required_identity_gain": family_primary[design.required_family_gains[0]] < 0.0,
        "required_long_recurrence_gain": family_primary[design.required_family_gains[1]] < 0.0,
        "role_guardrail": family_primary[design.guardrail_families[0]]
        <= design.guardrail_noninferiority_margin,
        "cause_guardrail": family_primary[design.guardrail_families[1]]
        <= design.guardrail_noninferiority_margin,
        "all_runtime_operator_gates": all(operator_gates.values()),
        "all_ancestry_gates": all(ancestry_gates.values()),
        "all_ledger_gates": all(ledger_gates.values()),
    }
    provenance_paths = {
        "benchmark_source_sha256": Path(__file__).resolve(),
        "fresh_readout_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_fresh_triarm.py",
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
        "amg_fidelity": "matched_replay_adapter_not_faithful_original_reproduction",
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
        "ledger_gates": ledger_gates,
        "gate_criteria": gate_criteria,
        "mechanism_gate_passed": all(gate_criteria.values()),
        "provenance": {key: _file_sha256(path) for key, path in provenance_paths.items()},
        "limitations": [
            "D0 synthetic mechanism evidence only",
            "deterministic structured proposal only; neural proposer intentionally not run",
            "sealed seeds are repository-local rather than independently held",
            "corrected AMG is a matched adapter rather than a faithful reproduction",
            "no RGB-D household or robot execution evidence",
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_sequential_consolidation_gate_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_sequential_consolidation_gate_report(
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
        raise ValueError("sequential gate report content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("sequential gate report protocol mismatch")
    design = load_frozen_sequential_gate_design(repository_root / DEFAULT_MANIFEST)
    seeds = _load_and_verify_holdout_seeds(design, repository_root / DEFAULT_SEALED_SEEDS)
    if tuple(report.get("holdout_seed_commitments", ())) != design.holdout_seed_commitments:
        raise ValueError("sequential gate report commitment mismatch")

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

    if set(seeds) & integer_values(report):
        raise ValueError("sequential gate report discloses raw holdout seeds")
    expected_arms = {arm.value for arm in SequentialGateArm}
    clustered: dict[str, dict[str, list[float]]] = {
        commitment: {name: [] for name in COMPARISONS}
        for commitment in design.holdout_seed_commitments
    }
    if set(report.get("families", {})) != {family.family_id for family in design.families}:
        raise ValueError("sequential gate family set mismatch")
    for family in report["families"].values():
        rows = family["paired_holdout_rows"]
        if tuple(row["holdout_seed_commitment"] for row in rows) != (
            design.holdout_seed_commitments
        ):
            raise ValueError("sequential gate row commitment sequence mismatch")
        for row in rows:
            hashes = row.get("consumed_visible_stream_hash_by_arm", {})
            if set(hashes) != expected_arms or set(hashes.values()) != {
                row.get("consumed_visible_stream_hash")
            }:
                raise ValueError("sequential gate consumed stream receipt mismatch")
            losses = row["net_action_loss_per_step"]
            expected = {
                name: losses[left.value] - losses[right.value]
                for name, (left, right) in COMPARISONS.items()
            }
            if set(row["paired_differences"]) != set(COMPARISONS) or any(
                not math.isclose(row["paired_differences"][name], value, abs_tol=1e-12)
                for name, value in expected.items()
            ):
                raise ValueError("sequential gate paired difference mismatch")
            commitment = row["holdout_seed_commitment"]
            for name, value in expected.items():
                clustered[commitment][name].append(value)
    for name, recorded in report["paired_cluster_comparisons"].items():
        values = [
            mean(clustered[commitment][name]) for commitment in design.holdout_seed_commitments
        ]
        expected_interval = _bootstrap_ci(values)
        if not math.isclose(recorded["mean"], mean(values), abs_tol=1e-12) or any(
            not math.isclose(left, right, abs_tol=1e-12)
            for left, right in zip(
                recorded["confidence_interval_95"], expected_interval, strict=True
            )
        ):
            raise ValueError("sequential gate comparison mismatch")
    expected_provenance_paths = {
        "benchmark_source_sha256": Path(__file__).resolve(),
        "fresh_readout_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_fresh_triarm.py",
        "action_evaluator_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/project_two_action_benchmark.py",
        "manifest_file_sha256": repository_root / DEFAULT_MANIFEST,
        "sealed_seed_file_sha256": repository_root / DEFAULT_SEALED_SEEDS,
        "preregistration_sha256": repository_root / DEFAULT_PREREGISTRATION,
    }
    if report.get("provenance") != {
        key: _file_sha256(path) for key, path in expected_provenance_paths.items()
    }:
        raise ValueError("sequential gate provenance mismatch")
    if recompute:
        expected = run_sequential_consolidation_gate(repository_root=repository_root)
        if report["content_sha256"] != expected["content_sha256"]:
            raise ValueError("sequential gate deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_MANIFEST",
    "DEFAULT_SEALED_SEEDS",
    "PROTOCOL_ID",
    "PersistentParticle",
    "ReversibleParticleConsolidationLedger",
    "SequentialGateArm",
    "SequentialGateDesign",
    "SequentialGateFamily",
    "SequentialParticleRuntime",
    "load_frozen_sequential_gate_design",
    "run_sequential_consolidation_gate",
    "verify_sequential_consolidation_gate_report",
    "write_sequential_consolidation_gate_report",
]
