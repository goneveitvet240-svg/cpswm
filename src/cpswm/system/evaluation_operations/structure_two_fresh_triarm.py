"""Fresh-family three-arm action comparison for Structure Two.

The two complete-system arms retain all seven operators.  They share a planner
surface that consumes actor, identity, cause, and regime belief.  Only the
joint arm adds bounded typed-particle consolidation over those axes.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from itertools import product
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import UUID

from cpswm.contracts import ProjectTwoDatasetSplit, ProjectTwoReplayStep, RobotActionOutcome
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
from cpswm.system.evaluation_operations.structure_two_rejuvenation_gate import (
    FROZEN_PARTICLE_BUDGET,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    NeuralParticleProposal,
    OrderedActorRole,
    ParticleChangeCause,
    ParticleProposalOperation,
    ParticleRegimeDecision,
    ParticleRevisionReceipt,
    StructuredConstraint,
    StructuredWeightFactor,
    TypedParticleState,
    normalize_particle_revisions,
)
from cpswm.system.prototype_spine import ActionReadout, ActionReadoutConfig
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.world_model.habits_transitions import ChangeCause

PROTOCOL_ID = "structure-two-fresh-multiaxis-triarm@0.1"
DEFAULT_MANIFEST = Path(
    "configs/project_two_experiments/structure_two_fresh_triarm_manifest_v0_1.json"
)
DEFAULT_SEALED_SEEDS = Path(
    "configs/project_two_experiments/structure_two_fresh_triarm_sealed_seeds_v0_1.json"
)


class TriarmMethod(StrEnum):
    CORRECTED_AMG = "corrected_amg"
    OLD_FULL_MULTIAXIS = "old_full_multiaxis"
    JOINT_REVISION_MULTIAXIS = "joint_revision_multiaxis"


@dataclass(frozen=True, slots=True)
class FreshScenarioFamily:
    family_id: str
    guest_window: tuple[int, int]
    abrupt_day: int
    recurrence_day: int
    observation_coverage: float
    unknown_event_days: tuple[int, ...]
    actor_ambiguity_mix: float
    identity_confidence_scale: float
    feedback_flip_rate: float


@dataclass(frozen=True, slots=True)
class FrozenTriarmDesign:
    validation_seeds: tuple[int, ...]
    holdout_seed_commitments: tuple[str, ...]
    sealed_holdout_seed_count: int
    sealed_seed_file_sha256: str
    max_steps: int
    particle_budget: int
    families: tuple[FreshScenarioFamily, ...]
    search_spaces: Mapping[str, tuple[Any, ...]]
    manifest_file_sha256: str


@dataclass(frozen=True, slots=True)
class MultiAxisBelief:
    actor_posterior: Mapping[str, float]
    owner_actor_key: str
    identity_target_probability: float
    cause_posterior: Mapping[ChangeCause, float]
    regime_change_probability: float
    active_regime: str
    observed_location_id: UUID
    base_location_distribution: Mapping[UUID, float]


@dataclass(frozen=True, slots=True)
class _ActionParticle:
    actor_key: str
    identity_target: bool
    cause: ChangeCause
    regime_change: bool

    @property
    def key(self) -> str:
        return "|".join(
            (
                self.actor_key,
                "target" if self.identity_target else "mismatch",
                self.cause.value,
                "change" if self.regime_change else "stay",
            )
        )


@dataclass(frozen=True, slots=True)
class _CaseReading:
    metric: ActionCaseMetric
    verification_cost: float
    axis_trace_count: int
    operator_retention_receipt: Mapping[str, Any] | None = None
    consumed_visible_stream_hash: str = ""

    @property
    def net_action_loss_per_step(self) -> float:
        return float(
            (self.metric.cumulative_action_regret + self.verification_cost)
            / max(1, self.metric.step_count)
        )


PROFILE_SCALE = {
    "conservative": 0.65,
    "balanced": 1.0,
    "responsive": 1.35,
}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize(values: Mapping[Any, float]) -> dict[Any, float]:
    clipped = {key: max(0.0, float(value)) for key, value in values.items()}
    total = sum(clipped.values())
    if total <= 0.0:
        return {key: 1.0 / len(clipped) for key in clipped}
    return {key: value / total for key, value in clipped.items()}


def _rank_distribution(values: Mapping[UUID, float]) -> tuple[UUID, ...]:
    return tuple(sorted(values, key=lambda key: (-values[key], str(key))))


def _argmax_distribution(values: Mapping[UUID, float]) -> UUID:
    return _rank_distribution(values)[0]


def load_frozen_triarm_design(
    manifest_path: Path = DEFAULT_MANIFEST,
) -> FrozenTriarmDesign:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("fresh triarm manifest protocol mismatch")
    families = tuple(
        FreshScenarioFamily(
            family_id=item["family_id"],
            guest_window=tuple(item["guest_window"]),
            abrupt_day=item["abrupt_day"],
            recurrence_day=item["recurrence_day"],
            observation_coverage=item["observation_coverage"],
            unknown_event_days=tuple(item["unknown_event_days"]),
            actor_ambiguity_mix=item["actor_ambiguity_mix"],
            identity_confidence_scale=item["identity_confidence_scale"],
            feedback_flip_rate=item["feedback_flip_rate"],
        )
        for item in payload["scenario_families"]
    )
    design = FrozenTriarmDesign(
        validation_seeds=tuple(payload["validation_seeds"]),
        holdout_seed_commitments=tuple(payload["sealed_holdout_seed_commitments"]),
        sealed_holdout_seed_count=payload["sealed_holdout_seed_count"],
        sealed_seed_file_sha256=payload["sealed_seed_file_sha256"],
        max_steps=payload["max_steps"],
        particle_budget=payload["particle_budget"],
        families=families,
        search_spaces={key: tuple(value) for key, value in payload["search_spaces"].items()},
        manifest_file_sha256=_file_sha256(manifest_path),
    )
    if len(design.families) != 4 or len({item.family_id for item in families}) != 4:
        raise ValueError("fresh triarm design requires four unique scenario families")
    if design.particle_budget != FROZEN_PARTICLE_BUDGET:
        raise ValueError("fresh triarm particle budget must match frozen v0.2 K=24")
    if len(set(design.validation_seeds)) != len(design.validation_seeds):
        raise ValueError("validation seeds must be unique")
    if len(design.holdout_seed_commitments) != design.sealed_holdout_seed_count:
        raise ValueError("holdout commitment count mismatch")
    return design


def _load_and_verify_holdout_seeds(
    design: FrozenTriarmDesign,
    sealed_seed_path: Path,
) -> tuple[int, ...]:
    if _file_sha256(sealed_seed_path) != design.sealed_seed_file_sha256:
        raise ValueError("sealed holdout seed file hash mismatch")
    payload = json.loads(sealed_seed_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("sealed seed protocol mismatch")
    seeds = tuple(payload["holdout_seeds"])
    salt = payload["commitment_salt"]
    commitments = tuple(
        hashlib.sha256(f"{PROTOCOL_ID}:{seed}:{salt}".encode()).hexdigest() for seed in seeds
    )
    if commitments != design.holdout_seed_commitments:
        raise ValueError("sealed holdout seeds do not match public commitments")
    if len(seeds) != design.sealed_holdout_seed_count:
        raise ValueError("sealed holdout seed count mismatch")
    if set(seeds) & set(design.validation_seeds):
        raise ValueError("validation and holdout seeds must be disjoint")
    return seeds


def _dataset(
    family: FreshScenarioFamily,
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
    family: FreshScenarioFamily,
) -> Callable[[ProjectTwoReplayStep], ProjectTwoReplayStep]:
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
        confidence = step.detection_confidence
        if confidence is not None:
            update["detection_confidence"] = 0.5 + family.identity_confidence_scale * (
                confidence - 0.5
            )
        return step.model_copy(update=update)

    return transform


class _FamilyFeedbackState:
    def __init__(self, state: Any, family: FreshScenarioFamily, episode: Any) -> None:
        self._state = state
        self._family = family
        self._episode = episode
        self._queue: list[ProjectTwoReplayStep] = []

    def observe(self, step: ProjectTwoReplayStep) -> None:
        self._state.observe(step)

    def predict(self) -> Any:
        return self._state.predict()

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        transformed = []
        for item in step.execution_feedback:
            token = f"{self._episode.scene_id}|{step.timestamp.isoformat()}|fresh-feedback"
            draw = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big") / 2**64
            if draw >= self._family.feedback_flip_rate:
                transformed.append(item)
                continue
            distribution = dict.fromkeys(item.outcome_distribution, 0.0)
            success = item.outcome_distribution.get(RobotActionOutcome.SUCCESS, 0.0)
            distribution[RobotActionOutcome.SUCCESS] = 1.0 - success
            distribution[RobotActionOutcome.NOT_FOUND] = success
            transformed.append(item.model_copy(update={"outcome_distribution": distribution}))
        queued = step.model_copy(update={"execution_feedback": tuple(transformed)})
        self._queue.append(queued)
        if len(self._queue) > 1:
            self._state.feedback(self._queue.pop(0))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._state, name)


def _cause_posterior(state: _FullProjectTwoMethod) -> dict[ChangeCause, float]:
    snapshot = state.spine.current_cause_snapshot
    if snapshot is None:
        return dict.fromkeys(ChangeCause, 1.0 / len(ChangeCause))
    complete = dict.fromkeys(ChangeCause, 0.0)
    complete.update(snapshot.active_regime_cause_posterior)
    return _normalize(complete)


def _identity_probability(
    step: ProjectTwoReplayStep,
    *,
    target_object_id: UUID,
) -> float:
    confidence = step.detection_confidence if step.detection_confidence is not None else 0.5
    if step.after is None or step.after.detected_object_instance_id is None:
        return 0.5
    return (
        confidence
        if step.after.detected_object_instance_id == target_object_id
        else 1.0 - confidence
    )


def _particle_action_strength(particle: _ActionParticle, *, scale: float) -> float:
    if not particle.identity_target:
        return 0.0
    cause_strength = {
        ChangeCause.OBSERVATION: 0.22,
        ChangeCause.ACTOR: 0.12,
        ChangeCause.HABIT: 0.72,
        ChangeCause.NOISE: 0.04,
    }[particle.cause]
    regime_bonus = 0.18 if particle.regime_change else 0.0
    return min(1.0, scale * (cause_strength + regime_bonus))


def _blend_location(
    belief: MultiAxisBelief,
    *,
    trust: float,
) -> dict[UUID, float]:
    base = _normalize(belief.base_location_distribution)
    return _normalize(
        {
            location: (1.0 - trust) * probability
            + (trust if location == belief.observed_location_id else 0.0)
            for location, probability in base.items()
        }
    )


def factorized_multiaxis_distribution(
    belief: MultiAxisBelief,
    *,
    profile: str,
) -> dict[UUID, float]:
    scale = PROFILE_SCALE[profile]
    expected_strength = 0.0
    for cause, cause_probability in belief.cause_posterior.items():
        for regime_change in (False, True):
            regime_probability = (
                belief.regime_change_probability
                if regime_change
                else 1.0 - belief.regime_change_probability
            )
            expected_strength += (
                cause_probability
                * regime_probability
                * _particle_action_strength(
                    _ActionParticle(
                        actor_key=belief.owner_actor_key,
                        identity_target=True,
                        cause=cause,
                        regime_change=regime_change,
                    ),
                    scale=scale,
                )
            )
    trust = (
        belief.actor_posterior.get(belief.owner_actor_key, 0.0)
        * belief.identity_target_probability
        * expected_strength
    )
    return _blend_location(belief, trust=trust)


def _particle_prior_log_weight(belief: MultiAxisBelief, particle: _ActionParticle) -> float:
    epsilon = 1e-12
    return sum(
        math.log(max(epsilon, value))
        for value in (
            belief.actor_posterior.get(particle.actor_key, epsilon),
            (
                belief.identity_target_probability
                if particle.identity_target
                else 1.0 - belief.identity_target_probability
            ),
            belief.cause_posterior[particle.cause],
            (
                belief.regime_change_probability
                if particle.regime_change
                else 1.0 - belief.regime_change_probability
            ),
        )
    )


def _joint_penalties(
    belief: MultiAxisBelief,
    particle: _ActionParticle,
    *,
    strength: float,
) -> tuple[StructuredConstraint, ...]:
    owner = particle.actor_key == belief.owner_actor_key
    actor_compatible = (owner and particle.cause is not ChangeCause.ACTOR) or (
        not owner and particle.cause is ChangeCause.ACTOR
    )
    identity_compatible = (
        particle.identity_target and particle.cause in {ChangeCause.ACTOR, ChangeCause.HABIT}
    ) or (
        not particle.identity_target
        and particle.cause in {ChangeCause.OBSERVATION, ChangeCause.NOISE}
    )
    regime_compatible = (particle.regime_change and particle.cause is ChangeCause.HABIT) or (
        not particle.regime_change and particle.cause is not ChangeCause.HABIT
    )
    potentials = {
        StructuredWeightFactor.PHYSICAL_EVENT_CONSTRAINT: (
            0.0 if actor_compatible else -0.70 * strength
        ),
        StructuredWeightFactor.ORDERED_ROLE_CONSTRAINT: 0.0,
        StructuredWeightFactor.IDENTITY_CONSTRAINT: (
            0.0 if identity_compatible else -0.50 * strength
        ),
        StructuredWeightFactor.PROVENANCE_CONSTRAINT: (
            0.0 if regime_compatible else -0.60 * strength
        ),
    }
    return tuple(
        StructuredConstraint(factor=factor, accepted=True, log_potential=potential)
        for factor, potential in potentials.items()
    )


def joint_particle_multiaxis_distribution(
    belief: MultiAxisBelief,
    *,
    profile: str,
    particle_budget: int = FROZEN_PARTICLE_BUDGET,
) -> tuple[dict[UUID, float], int]:
    if particle_budget != FROZEN_PARTICLE_BUDGET:
        raise ValueError("joint multi-axis readout freezes K=24")
    scale = PROFILE_SCALE[profile]
    particles = tuple(
        _ActionParticle(*values)
        for values in product(
            tuple(sorted(belief.actor_posterior)),
            (False, True),
            tuple(ChangeCause),
            (False, True),
        )
    )
    selected = tuple(
        sorted(
            particles,
            key=lambda particle: (
                -(
                    _particle_prior_log_weight(belief, particle)
                    + sum(
                        item.log_potential
                        for item in _joint_penalties(belief, particle, strength=scale)
                    )
                ),
                particle.key,
            ),
        )[:particle_budget]
    )
    snapshot_id = content_uuid("fresh-triarm-axis-snapshot", asdict(belief))
    cluster_id = content_uuid("fresh-triarm-axis-cluster", asdict(belief))
    receipts = []
    for particle in selected:
        parent_id = content_uuid("fresh-triarm-axis-parent", particle.actor_key)
        particle_id = content_uuid("fresh-triarm-axis-particle", (snapshot_id, particle.key))
        habit_change = particle.cause is ChangeCause.HABIT and particle.regime_change
        typed_state = TypedParticleState(
            particle_id=particle_id,
            parent_particle_id=parent_id,
            source_snapshot_id=snapshot_id,
            event_hypothesis_id=content_uuid("fresh-triarm-axis-event", particle.key),
            revision_id=content_uuid("fresh-triarm-axis-revision", (snapshot_id, particle.key)),
            parent_revision_id=content_uuid("fresh-triarm-axis-parent-revision", particle.key),
            ordered_actor_roles=(
                OrderedActorRole(role="responsible_actor", actor_key=particle.actor_key),
            ),
            instance_association_key=(
                "target_instance" if particle.identity_target else "identity_mismatch"
            ),
            change_cause=ParticleChangeCause(particle.cause.value),
            regime_decision=(
                ParticleRegimeDecision.CREATE if habit_change else ParticleRegimeDecision.STAY
            ),
            regime_id=(
                f"{belief.active_regime}:change"
                if particle.regime_change
                else f"{belief.active_regime}:stay"
            ),
            run_length=(0 if particle.regime_change else 1),
            statistic_state_ref=f"rao-blackwellized-location:{belief.active_regime}",
            ledger_lineage_ref=f"action-only:{snapshot_id}",
        )
        proposal = NeuralParticleProposal(
            proposal_id=content_uuid("fresh-triarm-axis-proposal", (snapshot_id, particle.key)),
            evidence_cluster_id=cluster_id,
            operation=ParticleProposalOperation.REJUVENATE,
            source_particle_id=parent_id,
            source_snapshot_id=snapshot_id,
            proposed_state=typed_state,
            proposal_log_probability=-math.log(len(selected)),
            proposer_model_version="deterministic-structured-joint-action-proposal@0.1",
            proposer_code_version=PROTOCOL_ID,
        )
        receipts.append(
            ParticleRevisionReceipt(
                proposal=proposal,
                prior_log_weight=_particle_prior_log_weight(belief, particle),
                transition_log_probability=0.0,
                observation_log_likelihood=0.0,
                constraints=_joint_penalties(belief, particle, strength=scale),
            )
        )
    batch = normalize_particle_revisions(
        tuple(receipts),
        unresolved_log_weight=math.log(0.02) + math.log(len(selected)),
    )
    trust = sum(
        weight.posterior_probability
        * (
            _particle_action_strength(particle, scale=scale)
            if particle.actor_key == belief.owner_actor_key
            else 0.0
        )
        for particle, weight in zip(selected, batch.particle_weights, strict=True)
    )
    return _blend_location(belief, trust=trust), len(selected)


class _MultiAxisActionState:
    def __init__(
        self,
        state: _FullProjectTwoMethod,
        episode: Any,
        *,
        profile: str,
        joint_revision: bool,
    ) -> None:
        self._state = state
        self._episode = episode
        self._profile = profile
        self._joint_revision = joint_revision
        self._belief: MultiAxisBelief | None = None
        self.axis_trace_count = 0
        self.axis_consumption_counts = {
            axis: 0 for axis in ("actor", "identity", "cause", "regime")
        }
        self.axis_trace_hashes: list[str] = []
        self.operator_retention_receipt = {
            "opceu": self._state.propensity_correction_mode.value,
            "orrer": self._state.revision_strategy,
            "pchmp": type(self._state.spine._message_passing).__name__,
            "cf_bocpd": self._state.loop_config.cause_factorized_bocpd_enabled,
            "rgrc": self._state.rgrc_gate_enabled,
            "ccrr": (
                self._state.loop_config.ccrr_enabled
                and self._state.loop_config.regime_reactivation_enabled
            ),
            "ciav": False,
        }

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
        self._belief = MultiAxisBelief(
            actor_posterior=_normalize(result.actor_posterior),
            owner_actor_key=self._episode.owner_actor_key,
            identity_target_probability=_identity_probability(
                transformed,
                target_object_id=transformed.object_instance_id,
            ),
            cause_posterior=_cause_posterior(self._state),
            regime_change_probability=result.decision.change_probability,
            active_regime=result.active_regime,
            observed_location_id=observed,
            base_location_distribution=base,
        )

    def predict(self) -> _Prediction:
        native = self._state.predict()
        if self._belief is None:
            return native
        # CIAV runs after ``observe`` and may update the fast-action store.
        # Consume the latest snapshot here rather than the pre-verification
        # distribution cached when the axes were assembled.
        belief = replace(
            self._belief,
            base_location_distribution=self._state.spine.action_location_distribution(
                self._state.spine.current_snapshot,
                readout=self._state.action_readout,
            ),
        )
        if self._joint_revision:
            distribution, particle_count = joint_particle_multiaxis_distribution(
                belief,
                profile=self._profile,
            )
        else:
            distribution = factorized_multiaxis_distribution(
                belief,
                profile=self._profile,
            )
            particle_count = 0
        trace = {
            "actor_posterior": sorted(belief.actor_posterior.items()),
            "identity_target_probability": belief.identity_target_probability,
            "cause_posterior": sorted(
                (key.value, value) for key, value in belief.cause_posterior.items()
            ),
            "regime_change_probability": belief.regime_change_probability,
            "active_regime": belief.active_regime,
            "particle_count": particle_count,
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

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        self._state.feedback(step)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._state, name)


def _action_readout() -> ActionReadoutConfig:
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


def _state_for_arm(
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    family: FreshScenarioFamily,
    arm: TriarmMethod,
    parameter: Any,
) -> Any:
    transform = _visible_transform(family)
    if arm is TriarmMethod.CORRECTED_AMG:
        state: Any = _AMGOpenWorldMethod(episode, mode="amg", parameter=float(parameter))
        state = _VisibleTransformState(state, transform)
        return _FamilyFeedbackState(state, family, episode)
    base = _FullProjectTwoMethod(
        episode,
        owner_threshold=0.4,
        action_readout=_action_readout(),
    )
    state = _MultiAxisActionState(
        base,
        episode,
        profile=str(parameter),
        joint_revision=arm is TriarmMethod.JOINT_REVISION_MULTIAXIS,
    )
    state = _CIAVState(state, dataset, episode, enabled=True, cost_multiplier=1.0)
    state.operator_retention_receipt = {
        **state.operator_retention_receipt,
        "ciav": bool(state._enabled),
    }
    state = _VisibleTransformState(state, transform)
    return _FamilyFeedbackState(state, family, episode)


class _VisibleTransformState:
    def __init__(
        self,
        state: Any,
        transform: Callable[[ProjectTwoReplayStep], ProjectTwoReplayStep],
    ) -> None:
        self._state = state
        self._transform = transform
        self._consumed_visible_step_hashes: list[str] = []

    def observe(self, step: ProjectTwoReplayStep) -> None:
        transformed = self._transform(step)
        self._consumed_visible_step_hashes.append(content_sha256(transformed))
        self._state.observe(transformed)

    def predict(self) -> Any:
        return self._state.predict()

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        self._state.feedback(self._transform(step))

    def __getattr__(self, name: str) -> Any:
        return getattr(self._state, name)

    @property
    def consumed_visible_stream_hash(self) -> str:
        return str(content_sha256(self._consumed_visible_step_hashes))


def _evaluate(
    evaluator: ProjectTwoActionBenchmarkV02,
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    family: FreshScenarioFamily,
    arm: TriarmMethod,
    parameter: Any,
) -> _CaseReading:
    state = _state_for_arm(dataset, episode, family, arm, parameter)
    metric = evaluator.evaluate_custom_state(dataset, episode, state)
    return _CaseReading(
        metric=metric,
        verification_cost=float(getattr(state, "verification_cost", 0.0)),
        axis_trace_count=int(getattr(state, "axis_trace_count", 0)),
        operator_retention_receipt=getattr(state, "operator_retention_receipt", None),
        consumed_visible_stream_hash=str(getattr(state, "consumed_visible_stream_hash", "")),
    )


def _search_space(design: FrozenTriarmDesign, arm: TriarmMethod) -> tuple[Any, ...]:
    return design.search_spaces[arm.value]


def _summary(readings: list[_CaseReading]) -> dict[str, float]:
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
    }


def _bootstrap_ci(values: list[float], *, draws: int = 4000) -> tuple[float, float]:
    rng = random.Random(f"{PROTOCOL_ID}:paired-cluster-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


def multiaxis_sensitivity_audit() -> dict[str, bool]:
    locations = (
        content_uuid("fresh-triarm-sensitivity-location", "a"),
        content_uuid("fresh-triarm-sensitivity-location", "b"),
    )
    baseline = MultiAxisBelief(
        actor_posterior={"owner": 0.7, "guest": 0.3},
        owner_actor_key="owner",
        identity_target_probability=0.75,
        cause_posterior={
            ChangeCause.OBSERVATION: 0.15,
            ChangeCause.ACTOR: 0.15,
            ChangeCause.HABIT: 0.55,
            ChangeCause.NOISE: 0.15,
        },
        regime_change_probability=0.65,
        active_regime="audit-regime",
        observed_location_id=locations[1],
        base_location_distribution={locations[0]: 0.65, locations[1]: 0.35},
    )

    def output(belief: MultiAxisBelief, joint: bool) -> dict[UUID, float]:
        if joint:
            return joint_particle_multiaxis_distribution(belief, profile="balanced")[0]
        return factorized_multiaxis_distribution(belief, profile="balanced")

    perturbations = {
        "actor": MultiAxisBelief(
            **{
                **asdict(baseline),
                "actor_posterior": {"owner": 0.2, "guest": 0.8},
            }
        ),
        "identity": MultiAxisBelief(**{**asdict(baseline), "identity_target_probability": 0.2}),
        "cause": MultiAxisBelief(
            **{
                **asdict(baseline),
                "cause_posterior": {
                    ChangeCause.OBSERVATION: 0.1,
                    ChangeCause.ACTOR: 0.1,
                    ChangeCause.HABIT: 0.1,
                    ChangeCause.NOISE: 0.7,
                },
            }
        ),
        "regime": MultiAxisBelief(**{**asdict(baseline), "regime_change_probability": 0.1}),
    }
    result = {}
    for joint in (False, True):
        reference = output(baseline, joint)
        prefix = "joint" if joint else "old_full"
        for axis, perturbed in perturbations.items():
            changed = sum(abs(reference[key] - output(perturbed, joint)[key]) for key in reference)
            result[f"{prefix}_{axis}_changes_action_distribution"] = changed > 1e-9
    return result


def run_fresh_multiaxis_triarm(
    *,
    repository_root: Path,
    manifest_path: Path | None = None,
    sealed_seed_path: Path | None = None,
) -> dict[str, Any]:
    manifest = manifest_path or repository_root / DEFAULT_MANIFEST
    sealed = sealed_seed_path or repository_root / DEFAULT_SEALED_SEEDS
    design = load_frozen_triarm_design(manifest)
    evaluator = ProjectTwoActionBenchmarkV02()
    phase_audit: list[str] = ["validation_tuning_started"]

    # Phase 1 is deliberately completed before the sealed file is opened.
    selected: dict[str, dict[TriarmMethod, Any]] = {}
    validation_reports: dict[str, Any] = {}
    for family_index, family in enumerate(design.families):
        tuning_dataset = _dataset(
            family,
            validation_seeds=design.validation_seeds,
            test_seeds=(52991 + family_index,),
            max_steps=design.max_steps,
            split_label="validation-only",
        )
        episodes = tuning_dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
        selected[family.family_id] = {}
        validation_reports[family.family_id] = {}
        for arm in TriarmMethod:
            candidates = []
            rows = []
            for parameter in _search_space(design, arm):
                validation_readings = [
                    _evaluate(evaluator, tuning_dataset, episode, family, arm, parameter)
                    for episode in episodes
                ]
                score = mean(item.net_action_loss_per_step for item in validation_readings)
                rows.append({"parameter": parameter, "net_action_loss_per_step": score})
                candidates.append((score, str(parameter), parameter))
            chosen = min(candidates, key=lambda item: (item[0], item[1]))[2]
            selected[family.family_id][arm] = chosen
            validation_reports[family.family_id][arm.value] = {
                "candidates": rows,
                "selected_parameter": chosen,
                "validation_episode_count": len(episodes),
                "holdout_episode_ids_seen": [],
            }

    phase_audit.append("validation_tuning_completed")
    phase_audit.append("sealed_seed_file_open_requested")
    holdout_seeds = _load_and_verify_holdout_seeds(design, sealed)
    phase_audit.append("sealed_seed_file_verified")
    family_reports: dict[str, Any] = {}
    expected_operator_receipt = {
        "opceu": "inverse",
        "orrer": "orrer",
        "pchmp": "ProvenanceConstrainedMessagePassing",
        "cf_bocpd": True,
        "rgrc": True,
        "ccrr": True,
        "ciav": True,
    }
    runtime_operator_retention: dict[str, bool] = {}
    paired_by_commitment: dict[str, dict[str, list[float]]] = {
        commitment: {
            name: []
            for name in (
                "joint_revision_minus_old_full",
                "joint_revision_minus_corrected_amg",
                "old_full_minus_corrected_amg",
            )
        }
        for commitment in design.holdout_seed_commitments
    }
    for family_index, family in enumerate(design.families):
        holdout_dataset = _dataset(
            family,
            validation_seeds=(62991 + family_index,),
            test_seeds=holdout_seeds,
            max_steps=design.max_steps,
            split_label="sealed-holdout",
        )
        episodes = holdout_dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        holdout_readings = {
            arm: [
                _evaluate(
                    evaluator,
                    holdout_dataset,
                    episode,
                    family,
                    arm,
                    selected[family.family_id][arm],
                )
                for episode in episodes
            ]
            for arm in TriarmMethod
        }
        summaries = {arm.value: _summary(values) for arm, values in holdout_readings.items()}
        for arm in (
            TriarmMethod.OLD_FULL_MULTIAXIS,
            TriarmMethod.JOINT_REVISION_MULTIAXIS,
        ):
            runtime_operator_retention[f"{family.family_id}:{arm.value}"] = all(
                reading.operator_retention_receipt == expected_operator_receipt
                for reading in holdout_readings[arm]
            )
        paired_rows = []
        for index, commitment in enumerate(design.holdout_seed_commitments):
            visible_hashes = {
                arm: holdout_readings[arm][index].metric.visible_input_hash for arm in TriarmMethod
            }
            if len(set(visible_hashes.values())) != 1:
                raise ValueError("three-arm visible replay hash mismatch")
            consumed_hashes = {
                arm: holdout_readings[arm][index].consumed_visible_stream_hash
                for arm in TriarmMethod
            }
            if len(set(consumed_hashes.values())) != 1:
                raise ValueError("three-arm consumed visible stream hash mismatch")
            losses = {
                arm: holdout_readings[arm][index].net_action_loss_per_step for arm in TriarmMethod
            }
            differences = {
                "joint_revision_minus_old_full": (
                    losses[TriarmMethod.JOINT_REVISION_MULTIAXIS]
                    - losses[TriarmMethod.OLD_FULL_MULTIAXIS]
                ),
                "joint_revision_minus_corrected_amg": (
                    losses[TriarmMethod.JOINT_REVISION_MULTIAXIS]
                    - losses[TriarmMethod.CORRECTED_AMG]
                ),
                "old_full_minus_corrected_amg": (
                    losses[TriarmMethod.OLD_FULL_MULTIAXIS] - losses[TriarmMethod.CORRECTED_AMG]
                ),
            }
            for name, value in differences.items():
                paired_by_commitment[commitment][name].append(value)
            paired_rows.append(
                {
                    "holdout_seed_commitment": commitment,
                    "visible_input_hash": next(iter(visible_hashes.values())),
                    "visible_input_hash_by_arm": {
                        arm.value: value for arm, value in visible_hashes.items()
                    },
                    "same_visible_input_hash_across_arms": True,
                    "consumed_visible_stream_hash": next(iter(consumed_hashes.values())),
                    "consumed_visible_stream_hash_by_arm": {
                        arm.value: value for arm, value in consumed_hashes.items()
                    },
                    "same_consumed_visible_stream_hash_across_arms": True,
                    "net_action_loss_per_step": {arm.value: value for arm, value in losses.items()},
                    "paired_differences": differences,
                }
            )
        family_reports[family.family_id] = {
            "family_parameters": asdict(family),
            "selected_parameters": {
                arm.value: value for arm, value in selected[family.family_id].items()
            },
            "holdout_episode_count": len(episodes),
            "summaries": summaries,
            "paired_holdout_rows": paired_rows,
        }

    clustered = {
        name: [mean(paired_by_commitment[key][name]) for key in design.holdout_seed_commitments]
        for name in next(iter(paired_by_commitment.values()))
    }
    comparisons = {
        name: {
            "mean": mean(values),
            "confidence_interval_95": _bootstrap_ci(values),
            "cluster_count": len(values),
            "benefit_if_negative": True,
        }
        for name, values in clustered.items()
    }
    sensitivity = multiaxis_sensitivity_audit()
    axis_trace_coverage = {
        f"{family_id}:{arm.value}": (
            family_report["summaries"][arm.value]["mean_axis_trace_count"] > 0.0
        )
        for family_id, family_report in family_reports.items()
        for arm in (
            TriarmMethod.OLD_FULL_MULTIAXIS,
            TriarmMethod.JOINT_REVISION_MULTIAXIS,
        )
    }
    repository_paths = {
        "benchmark_source_sha256": Path(__file__).resolve(),
        "action_benchmark_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/project_two_action_benchmark.py",
        "selected_method_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_selected_method.py",
        "v0_2_rejuvenation_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_rejuvenation_gate.py",
        "manifest_file_sha256": manifest,
        "sealed_seed_file_sha256": sealed,
        "protocol_document_sha256": repository_root
        / "docs/experiments/structure_two_fresh_multiaxis_triarm_protocol_2026-08-28.md",
    }
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": "D0 synthetic fresh-family development evidence; not paper evidence",
        "registration_status": "repository_local_freeze_without_independent_timestamp",
        "neural_proposer_status": "not_run_deterministic_structured_proposal_only",
        "amg_fidelity": "matched_replay_adapter_not_faithful_original_reproduction",
        "joint_method_integration_status": (
            "per_step_typed_particle_action_projection_only; no_temporal_particle_"
            "persistence_or_particle_ledger_consolidation"
        ),
        "all_seven_operators_retained_in_both_full_system_arms": True,
        "expected_operator_retention_receipt": expected_operator_receipt,
        "runtime_operator_retention_gates": runtime_operator_retention,
        "all_runtime_operator_retention_gates_passed": all(runtime_operator_retention.values()),
        "primary_endpoint": "net_action_loss_per_step",
        "particle_budget": design.particle_budget,
        "validation_seed_count": len(design.validation_seeds),
        "holdout_seed_count": design.sealed_holdout_seed_count,
        "holdout_seed_commitments": list(design.holdout_seed_commitments),
        "raw_holdout_seeds_disclosed": False,
        "scenario_family_count": len(design.families),
        "same_visible_replay_within_family_seed": True,
        "same_action_evaluator": True,
        "search_budget_per_arm_per_family": 3,
        "tuning_completed_before_sealed_seed_file_open": True,
        "phase_audit": phase_audit,
        "phase_audit_sha256": content_sha256(phase_audit),
        "validation": validation_reports,
        "families": family_reports,
        "paired_cluster_comparisons": comparisons,
        "multiaxis_sensitivity_gates": sensitivity,
        "all_multiaxis_sensitivity_gates_passed": all(sensitivity.values()),
        "axis_trace_coverage_gates": axis_trace_coverage,
        "all_axis_trace_coverage_gates_passed": all(axis_trace_coverage.values()),
        "provenance": {key: _file_sha256(path) for key, path in repository_paths.items()},
        "limitations": [
            "D0 synthetic fresh scenario families only",
            "corrected AMG remains a matched replay adapter",
            "joint proposer is deterministic rather than neural amortized",
            (
                "typed action particles are regenerated per step and do not yet form a "
                "sequential persistent particle runtime"
            ),
            (
                "identity-occlusion family attenuates confidence and observation coverage; "
                "it does not inject decoy instance swaps"
            ),
            (
                "sealed seeds are process-isolated but stored locally, not held by an "
                "external custodian"
            ),
            "no RGB-D household or robot execution evidence",
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_fresh_multiaxis_triarm_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_fresh_multiaxis_triarm_report(
    report_path: Path,
    *,
    repository_root: Path,
    recompute: bool = False,
) -> dict[str, Any]:
    """Verify hashes, sealed commitments, paired statistics, and optionally rerun."""

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("fresh triarm report is unreadable") from error
    if not isinstance(report, dict):
        raise ValueError("fresh triarm report must be a JSON object")
    stored_hash = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored_hash, str) or content_sha256(unsigned) != stored_hash:
        raise ValueError("fresh triarm report content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("fresh triarm report protocol mismatch")

    design = load_frozen_triarm_design(repository_root / DEFAULT_MANIFEST)
    holdout_seeds = _load_and_verify_holdout_seeds(
        design,
        repository_root / DEFAULT_SEALED_SEEDS,
    )
    if tuple(report.get("holdout_seed_commitments", ())) != design.holdout_seed_commitments:
        raise ValueError("fresh triarm report commitment mismatch")

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
        raise ValueError("fresh triarm report discloses raw holdout seeds")

    expected_provenance_paths = {
        "benchmark_source_sha256": Path(__file__).resolve(),
        "action_benchmark_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/project_two_action_benchmark.py",
        "selected_method_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_selected_method.py",
        "v0_2_rejuvenation_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_rejuvenation_gate.py",
        "manifest_file_sha256": repository_root / DEFAULT_MANIFEST,
        "sealed_seed_file_sha256": repository_root / DEFAULT_SEALED_SEEDS,
        "protocol_document_sha256": repository_root
        / "docs/experiments/structure_two_fresh_multiaxis_triarm_protocol_2026-08-28.md",
    }
    expected_provenance = {
        key: _file_sha256(path) for key, path in expected_provenance_paths.items()
    }
    if report.get("provenance") != expected_provenance:
        raise ValueError("fresh triarm report provenance mismatch")

    clustered: dict[str, dict[str, list[float]]] = {
        commitment: {
            name: []
            for name in (
                "joint_revision_minus_old_full",
                "joint_revision_minus_corrected_amg",
                "old_full_minus_corrected_amg",
            )
        }
        for commitment in design.holdout_seed_commitments
    }
    expected_family_ids = {family.family_id for family in design.families}
    if set(report.get("families", {})) != expected_family_ids:
        raise ValueError("fresh triarm scenario family set mismatch")
    expected_difference_names = {
        "joint_revision_minus_old_full",
        "joint_revision_minus_corrected_amg",
        "old_full_minus_corrected_amg",
    }
    for family in report["families"].values():
        rows = family["paired_holdout_rows"]
        row_commitments = tuple(row.get("holdout_seed_commitment") for row in rows)
        if row_commitments != design.holdout_seed_commitments:
            raise ValueError("fresh triarm paired row commitment sequence mismatch")
        for arm in TriarmMethod:
            row_mean = mean(row["net_action_loss_per_step"][arm.value] for row in rows)
            if not math.isclose(
                row_mean,
                family["summaries"][arm.value]["net_action_loss_per_step"],
                abs_tol=1e-12,
            ):
                raise ValueError("fresh triarm family summary mismatch")
        for row in rows:
            commitment = row["holdout_seed_commitment"]
            expected_arm_names = {arm.value for arm in TriarmMethod}
            visible_by_arm = row.get("visible_input_hash_by_arm", {})
            if (
                not row.get("same_visible_input_hash_across_arms")
                or not isinstance(row.get("visible_input_hash"), str)
                or len(row["visible_input_hash"]) != 64
                or set(visible_by_arm) != expected_arm_names
                or set(visible_by_arm.values()) != {row["visible_input_hash"]}
            ):
                raise ValueError("fresh triarm visible replay receipt is invalid")
            consumed_by_arm = row.get("consumed_visible_stream_hash_by_arm", {})
            if (
                not row.get("same_consumed_visible_stream_hash_across_arms")
                or not isinstance(row.get("consumed_visible_stream_hash"), str)
                or len(row["consumed_visible_stream_hash"]) != 64
                or set(consumed_by_arm) != expected_arm_names
                or set(consumed_by_arm.values()) != {row["consumed_visible_stream_hash"]}
            ):
                raise ValueError("fresh triarm consumed visible stream receipt is invalid")
            losses = row["net_action_loss_per_step"]
            expected_differences = {
                "joint_revision_minus_old_full": (
                    losses[TriarmMethod.JOINT_REVISION_MULTIAXIS.value]
                    - losses[TriarmMethod.OLD_FULL_MULTIAXIS.value]
                ),
                "joint_revision_minus_corrected_amg": (
                    losses[TriarmMethod.JOINT_REVISION_MULTIAXIS.value]
                    - losses[TriarmMethod.CORRECTED_AMG.value]
                ),
                "old_full_minus_corrected_amg": (
                    losses[TriarmMethod.OLD_FULL_MULTIAXIS.value]
                    - losses[TriarmMethod.CORRECTED_AMG.value]
                ),
            }
            recorded_differences = row.get("paired_differences", {})
            if set(recorded_differences) != expected_difference_names or any(
                not math.isclose(
                    recorded_differences[name], expected_differences[name], abs_tol=1e-12
                )
                for name in expected_difference_names
            ):
                raise ValueError("fresh triarm paired difference receipt mismatch")
            for name, value in expected_differences.items():
                clustered[commitment][name].append(value)
    if set(report.get("paired_cluster_comparisons", {})) != expected_difference_names:
        raise ValueError("fresh triarm paired comparison set mismatch")
    for name, recorded in report["paired_cluster_comparisons"].items():
        values = [mean(clustered[key][name]) for key in design.holdout_seed_commitments]
        if not math.isclose(recorded["mean"], mean(values), abs_tol=1e-12):
            raise ValueError("fresh triarm paired mean mismatch")
        expected_interval = _bootstrap_ci(values)
        if any(
            not math.isclose(left, right, abs_tol=1e-12)
            for left, right in zip(
                recorded["confidence_interval_95"], expected_interval, strict=True
            )
        ):
            raise ValueError("fresh triarm paired interval mismatch")
    sensitivity_gates = report.get("multiaxis_sensitivity_gates", {})
    if not sensitivity_gates or not all(sensitivity_gates.values()):
        raise ValueError("fresh triarm multi-axis sensitivity gate failed")
    if report.get("all_multiaxis_sensitivity_gates_passed") is not all(sensitivity_gates.values()):
        raise ValueError("fresh triarm multi-axis sensitivity summary mismatch")
    axis_trace_gates = report.get("axis_trace_coverage_gates", {})
    if not axis_trace_gates or not all(axis_trace_gates.values()):
        raise ValueError("fresh triarm axis trace coverage gate failed")
    if report.get("all_axis_trace_coverage_gates_passed") is not all(axis_trace_gates.values()):
        raise ValueError("fresh triarm axis trace coverage summary mismatch")
    retention_gates = report.get("runtime_operator_retention_gates", {})
    if not retention_gates or not all(retention_gates.values()):
        raise ValueError("fresh triarm runtime operator retention gate failed")
    if report.get("all_runtime_operator_retention_gates_passed") is not all(
        retention_gates.values()
    ):
        raise ValueError("fresh triarm operator retention summary mismatch")
    expected_phase_audit = [
        "validation_tuning_started",
        "validation_tuning_completed",
        "sealed_seed_file_open_requested",
        "sealed_seed_file_verified",
    ]
    if report.get("phase_audit") != expected_phase_audit or report.get(
        "phase_audit_sha256"
    ) != content_sha256(expected_phase_audit):
        raise ValueError("fresh triarm tuning/sealed phase audit mismatch")
    if recompute:
        expected = run_fresh_multiaxis_triarm(repository_root=repository_root)
        # JSON round-tripping turns tuples into lists; compare the canonical
        # content identity rather than Python container classes.
        if report["content_sha256"] != expected["content_sha256"]:
            raise ValueError("fresh triarm report differs from deterministic recomputation")
    return report


__all__ = [
    "DEFAULT_MANIFEST",
    "DEFAULT_SEALED_SEEDS",
    "PROTOCOL_ID",
    "FreshScenarioFamily",
    "FrozenTriarmDesign",
    "MultiAxisBelief",
    "TriarmMethod",
    "factorized_multiaxis_distribution",
    "joint_particle_multiaxis_distribution",
    "load_frozen_triarm_design",
    "multiaxis_sensitivity_audit",
    "run_fresh_multiaxis_triarm",
    "verify_fresh_multiaxis_triarm_report",
    "write_fresh_multiaxis_triarm_report",
]
