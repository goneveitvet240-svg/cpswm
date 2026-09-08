"""Route-C stateful full-joint inference for Structure Two.

This module is the executable development implementation selected by the project
owner on 2026-09-07.  Unlike the historical Task-8 nine-cell proxy, every live
particle carries the complete discrete revision state

``(event chain, ordered actor roles, instance association, change cause,
habit regime, run length, revision lineage)``

plus particle-local Rao-Blackwellized location/RLS/information-form statistics.
The joint and matched-factorized arms use the same robot-visible inputs, neural
proposal, candidate-evaluation schedule, particle budget, resampling draws,
feedback, RGRC policy, and action readout.  The only intended difference is the
presence of explicit cross-axis potentials in the joint target density.

This is a development runtime, not paper evidence.  It composes the existing
seven-operator spine; it does not claim that a passing unit test establishes
superiority or external validity.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from statistics import mean
from typing import Any, Final, cast
from uuid import UUID

from cpswm.contracts import (
    EventMechanism,
    ProjectTwoDatasetSplit,
    ProjectTwoReplayEpisode,
    ProjectTwoReplayStep,
)
from cpswm.contracts.hidden_event_evidence import ordered_role_key, parse_ordered_role_key
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    PARAMETER_SPACE,
    ProjectTwoActionBenchmarkV02,
    ProjectTwoActionMethod,
    _FullProjectTwoMethod,
    _Prediction,
)
from cpswm.system.evaluation_operations.project_two_dataset import (
    audit_project_two_replay,
    summarize_project_two_evidence_coverage,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_factorial_benchmark import _CIAVState
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (
    _action_readout,
    _cause_posterior,
    _identity_probability,
)
from cpswm.system.evaluation_operations.structure_two_neural_amortized import (
    FEATURE_NAMES,
    NeuralModelConfig,
    NeuralProposalModel,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    NeuralParticleProposal,
    OrderedActorRole,
    ParticleChangeCause,
    ParticleProposalOperation,
    ParticleRegimeDecision,
    ParticleRevisionBatch,
    ParticleRevisionReceipt,
    StructuredConstraint,
    StructuredWeightFactor,
    StructureTwoOperator,
    TypedParticleState,
    normalize_particle_revisions,
)
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.world_model.habits_transitions import ChangeCause

PROTOCOL_ID: Final = "structure-two-stateful-full-joint@0.1-development"
DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_stateful_full_joint_v0_1.json"
)
COMPLETE_STATE_AXES: Final = (
    "event_chain",
    "ordered_actor_roles",
    "instance_association",
    "change_cause",
    "habit_regime",
    "run_length",
    "revision_lineage",
)
RB_BLOCKS: Final = (
    "dirichlet_location",
    "ridge_rls_natural_statistics",
    "information_form_belief",
)
SCORE_OPERATIONS_PER_CANDIDATE: Final = 32
D0_LIMITATION: Final = (
    "six synthetic D0 episodes with declared missing real sensor calibration, "
    "robot pose covariance, and post-action destination observation"
)
LATENCY_EVIDENCE_STATUS: Final = "DESCRIPTIVE_UNCONTROLLED_LOCAL_ORDERED_RUN_ONLY"
NEXT_GATE: Final = (
    "pre_registered_multi_family_fresh_seed_comparison_with_measured_latency_"
    "and_external_state_access_frontier"
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FullJointArm(StrEnum):
    STATEFUL_FULL_JOINT = "stateful_full_joint"
    MATCHED_FULL_STATE_FACTORIZED = "matched_full_state_factorized"


@dataclass(frozen=True, slots=True)
class StatefulFullJointConfig:
    particle_budget: int
    proposal_support_policy: str
    maximum_retired_regimes: int
    neural_proposal_mix: float
    unresolved_prior: float
    rgrc_owner_target_admission_floor: float
    rgrc_stability_steps: int
    joint_interaction_strength: float
    neural_proposal_model_path: Path


def load_stateful_full_joint_config(
    repository_root: Path,
    path: Path = DEFAULT_CONFIG,
) -> StatefulFullJointConfig:
    payload = json.loads((repository_root / path).read_text(encoding="utf-8"))
    expected_fields = {
        "schema_version",
        "protocol_id",
        "decision_source",
        "selected_route",
        "evidence_status",
        "particle_budget",
        "proposal_support_policy",
        "maximum_retired_regimes",
        "neural_proposal_model",
        "neural_proposal_mix",
        "unresolved_prior",
        "rgrc_owner_target_admission_floor",
        "rgrc_stability_steps",
        "joint_interaction_strength",
        "development_evaluation",
        "arms",
        "complete_state_axes",
        "rao_blackwellized_blocks",
        "retained_operators",
        "fairness_contract",
        "claim_boundary",
    }
    if set(payload) != expected_fields:
        raise ValueError("stateful full-joint configuration schema drift or extra claim field")
    if payload.get("schema_version") != "0.1.0":
        raise ValueError("stateful full-joint configuration schema version mismatch")
    if payload.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("stateful full-joint protocol mismatch")
    if payload.get("selected_route") != "C_stateful_joint_inference":
        raise ValueError("Route C has not been selected")
    if payload.get("evidence_status") != "DEVELOPMENT_IMPLEMENTATION_NOT_PAPER_EVIDENCE":
        raise ValueError("Route-C configuration evidence status was promoted")
    if tuple(payload.get("arms", ())) != tuple(arm.value for arm in FullJointArm):
        raise ValueError("Route-C matched-arm set drifted")
    expected_claim_boundary = (
        "This configuration implements the selected stateful full-joint development loop. "
        "Passing unit or D0 integration tests proves executable completeness and matched-arm "
        "fairness only; scientific superiority, external validity, Task 8 formal passage, "
        "and seven-operator ablation remain unauthorized."
    )
    if payload.get("claim_boundary") != expected_claim_boundary:
        raise ValueError("Route-C configuration claim boundary drifted")
    decision_path = repository_root / payload["decision_source"]
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    if (
        decision.get("status") != "PROJECT_OWNER_SELECTED"
        or decision.get("selected_option") != "C_stateful_joint_inference"
        or decision.get("selection_source") != "project_owner_explicit_instruction"
    ):
        raise ValueError("Route C selection is not bound to an explicit project-owner decision")
    if tuple(payload.get("complete_state_axes", ())) != COMPLETE_STATE_AXES:
        raise ValueError("stateful full-joint configuration narrows the complete state")
    if tuple(payload.get("rao_blackwellized_blocks", ())) != RB_BLOCKS:
        raise ValueError("stateful full-joint configuration narrows the RB blocks")
    if set(payload.get("retained_operators", ())) != {
        operator.value for operator in StructureTwoOperator
    }:
        raise ValueError("stateful full-joint configuration must retain all seven operators")
    fairness = payload.get("fairness_contract", {})
    required_fairness = {
        "same_robot_visible_input",
        "same_complete_state_access",
        "same_neural_proposal",
        "same_particle_budget",
        "same_complete_proposal_support",
        "same_fixed_target_score_count",
        "shared_common_random_numbers",
        "same_resampling_draws",
        "same_score_operation_schedule",
        "same_action_readout",
        "same_feedback_stream",
        "same_rgrc_policy",
    }
    if set(fairness) != required_fairness or not all(fairness.values()):
        raise ValueError("stateful full-joint matched-arm fairness contract is incomplete")
    evaluation = payload.get("development_evaluation")
    if not isinstance(evaluation, Mapping) or set(evaluation) != {
        "validation_seeds",
        "development_holdout_seeds",
        "max_steps_per_episode",
        "scenario_duration_days",
        "guest_window",
        "abrupt_day",
        "recurrence_day",
        "unknown_event_days",
        "amg_parameter_space",
    }:
        raise ValueError("Route-C development evaluation schema drifted")
    validation_seeds = tuple(int(value) for value in evaluation["validation_seeds"])
    holdout_seeds = tuple(int(value) for value in evaluation["development_holdout_seeds"])
    if (
        not validation_seeds
        or not holdout_seeds
        or len(set(validation_seeds)) != len(validation_seeds)
        or len(set(holdout_seeds)) != len(holdout_seeds)
        or set(validation_seeds) & set(holdout_seeds)
    ):
        raise ValueError("Route-C development seed split is empty, duplicate, or overlapping")
    if (
        int(evaluation["max_steps_per_episode"]) < 1
        or int(evaluation["scenario_duration_days"]) < 1
        or int(evaluation["abrupt_day"]) < 0
        or int(evaluation["recurrence_day"]) < 0
    ):
        raise ValueError("Route-C development chronology is invalid")
    budget = int(payload["particle_budget"])
    if budget < 2:
        raise ValueError("stateful full-joint particle budget must be at least two")
    proposal_support_policy = str(payload.get("proposal_support_policy", ""))
    if proposal_support_policy != "enumerate_all_positive_support":
        raise ValueError("Route C cannot truncate its proposal support")
    maximum_retired_regimes = int(payload.get("maximum_retired_regimes", 0))
    if maximum_retired_regimes < 1:
        raise ValueError("Route C must retain at least one reactivatable regime")
    numeric_config = {
        "neural_proposal_mix": float(payload["neural_proposal_mix"]),
        "unresolved_prior": float(payload["unresolved_prior"]),
        "rgrc_owner_target_admission_floor": float(payload["rgrc_owner_target_admission_floor"]),
        "joint_interaction_strength": float(payload["joint_interaction_strength"]),
    }
    if not all(math.isfinite(value) for value in numeric_config.values()):
        raise ValueError("Route C numeric configuration must be finite")
    if not 0.0 <= numeric_config["neural_proposal_mix"] <= 1.0:
        raise ValueError("neural proposal mix must be in [0, 1]")
    if not 0.0 < numeric_config["unresolved_prior"] < 1.0:
        raise ValueError("unresolved prior must lie in (0, 1)")
    if not 0.0 <= numeric_config["rgrc_owner_target_admission_floor"] <= 1.0:
        raise ValueError("RGRC admission floor must be in [0, 1]")
    if numeric_config["joint_interaction_strength"] < 0.0:
        raise ValueError("joint interaction strength cannot be negative")
    stability_steps = int(payload["rgrc_stability_steps"])
    if stability_steps < 1:
        raise ValueError("RGRC stability steps must be positive")
    return StatefulFullJointConfig(
        particle_budget=budget,
        proposal_support_policy=proposal_support_policy,
        maximum_retired_regimes=maximum_retired_regimes,
        neural_proposal_mix=numeric_config["neural_proposal_mix"],
        unresolved_prior=numeric_config["unresolved_prior"],
        rgrc_owner_target_admission_floor=numeric_config["rgrc_owner_target_admission_floor"],
        rgrc_stability_steps=stability_steps,
        joint_interaction_strength=numeric_config["joint_interaction_strength"],
        neural_proposal_model_path=repository_root / payload["neural_proposal_model"],
    )


def load_neural_proposal_model(path: Path) -> NeuralProposalModel:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("model_type") != "trained_one_hidden_layer_mlp":
        raise ValueError("Route C requires a trained neural proposal artifact")
    config_payload = payload["config"]
    config = NeuralModelConfig(
        architecture=str(config_payload["architecture"]),
        hidden_units=int(config_payload["hidden_units"]),
        epochs=int(config_payload["epochs"]),
        learning_rate=float(config_payload["learning_rate"]),
        l2=float(config_payload["l2"]),
        initialization_seed=int(config_payload["initialization_seed"]),
        target_semantics=str(config_payload["target_semantics"]),
        forbidden_inputs=tuple(config_payload["forbidden_inputs"]),
    )
    model = NeuralProposalModel(
        feature_names=tuple(payload["feature_names"]),
        hidden_weights=tuple(
            tuple(float(value) for value in row) for row in payload["hidden_weights"]
        ),
        hidden_bias=tuple(float(value) for value in payload["hidden_bias"]),
        output_weights=tuple(
            tuple(float(value) for value in row) for row in payload["output_weights"]
        ),
        output_bias=tuple(float(value) for value in payload["output_bias"]),
        training_example_count=int(payload["training_example_count"]),
        training_loss=float(payload["training_loss"]),
        config=config,
    )
    if model.feature_names != tuple(FEATURE_NAMES):
        raise ValueError("neural proposal artifact feature contract drifted")
    if payload.get("model_hash") != model.model_hash:
        raise ValueError("neural proposal artifact hash mismatch")
    return model


def _normalize(values: Mapping[Any, float]) -> dict[Any, float]:
    clipped = {key: max(0.0, float(value)) for key, value in values.items()}
    total = sum(clipped.values())
    if total <= 0.0:
        if not clipped:
            raise ValueError("cannot normalize empty support")
        return dict.fromkeys(clipped, 1.0 / len(clipped))
    return {key: value / total for key, value in clipped.items()}


def _log(value: float) -> float:
    return math.log(max(float(value), 1e-300))


def _logsumexp(values: Sequence[float]) -> float:
    maximum = max(values)
    return maximum + math.log(sum(math.exp(value - maximum) for value in values))


@dataclass(frozen=True, slots=True)
class FullJointObservation:
    source_update_id: UUID
    evidence_cluster_id: UUID
    owner_actor_key: str
    actor_posterior: Mapping[str, float]
    mechanism_posterior: Mapping[EventMechanism, float]
    ordered_role_posterior: Mapping[str, float]
    identity_target_probability: float
    cause_posterior: Mapping[ParticleChangeCause, float]
    regime_change_probability: float
    active_regime: str
    observed_location_id: UUID
    base_location_distribution: Mapping[UUID, float]
    known_location_ids: tuple[UUID, ...]
    unresolved_probability: float

    def __post_init__(self) -> None:
        if not self.owner_actor_key.strip() or self.owner_actor_key not in self.actor_posterior:
            raise ValueError("owner must be represented in actor posterior")
        if set(self.mechanism_posterior) != set(EventMechanism):
            raise ValueError("mechanism posterior must retain direct, handoff, and unknown")
        if set(self.cause_posterior) != set(ParticleChangeCause):
            raise ValueError("cause posterior must retain every cause including unresolved")
        if not self.ordered_role_posterior:
            raise ValueError("ordered role support cannot be empty")
        for role in self.ordered_role_posterior:
            parse_ordered_role_key(role)
        for name, values in (
            ("actor", self.actor_posterior),
            ("mechanism", self.mechanism_posterior),
            ("roles", self.ordered_role_posterior),
            ("cause", self.cause_posterior),
            ("location", self.base_location_distribution),
        ):
            if not values or any(
                not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0
                for value in values.values()
            ):
                raise ValueError(f"{name} posterior must contain finite probabilities")
            if abs(sum(values.values()) - 1.0) > 1e-6:
                raise ValueError(f"{name} posterior must sum to one")
        for name, value in (
            ("identity_target_probability", self.identity_target_probability),
            ("regime_change_probability", self.regime_change_probability),
            ("unresolved_probability", self.unresolved_probability),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if tuple(dict.fromkeys(self.known_location_ids)) != self.known_location_ids:
            raise ValueError("known location catalogue must be unique")
        if not self.known_location_ids:
            raise ValueError("known location catalogue cannot be empty")
        if self.observed_location_id not in self.known_location_ids:
            raise ValueError("observed location must belong to the visible location catalogue")
        if set(self.base_location_distribution) != set(self.known_location_ids):
            raise ValueError("base action distribution must cover the known location catalogue")
        if not self.active_regime.strip():
            raise ValueError("active regime must be non-empty")
        actor_keys = set(self.actor_posterior)
        for role_key in self.ordered_role_posterior:
            giver, receiver = parse_ordered_role_key(role_key)
            if giver not in actor_keys or receiver not in actor_keys:
                raise ValueError("ordered role support introduced an actor absent from evidence")


@dataclass(frozen=True, slots=True)
class RBCellState:
    """Particle-local analytic state: Dirichlet, ridge natural, information form."""

    location_alpha: tuple[float, ...]
    ridge_precision: tuple[float, ...]
    ridge_natural: tuple[float, ...]
    information_precision: float
    information_natural: float
    observation_count: int = 0

    def __post_init__(self) -> None:
        widths = {
            len(self.location_alpha),
            len(self.ridge_precision),
            len(self.ridge_natural),
        }
        if len(widths) != 1 or 0 in widths:
            raise ValueError("RB blocks must have one shared non-empty location width")
        if any(not math.isfinite(value) or value <= 0.0 for value in self.location_alpha):
            raise ValueError("Dirichlet concentrations must be finite and positive")
        if any(not math.isfinite(value) or value <= 0.0 for value in self.ridge_precision):
            raise ValueError("ridge precisions must be finite and positive")
        if any(not math.isfinite(value) or value < 0.0 for value in self.ridge_natural):
            raise ValueError("ridge natural statistics must be finite and non-negative")
        if not math.isfinite(self.information_precision) or self.information_precision <= 0.0:
            raise ValueError("information precision must be finite and positive")
        if not math.isfinite(self.information_natural) or self.information_natural < 0.0:
            raise ValueError("information natural statistic must be finite and non-negative")
        if self.observation_count < 0:
            raise ValueError("RB observation count cannot be negative")

    @classmethod
    def prior(cls, width: int) -> RBCellState:
        return cls(
            location_alpha=tuple(0.5 for _ in range(width)),
            ridge_precision=tuple(1.0 for _ in range(width)),
            ridge_natural=tuple(0.0 for _ in range(width)),
            information_precision=1.0,
            information_natural=0.0,
        )

    def update(self, location_index: int, evidence_weight: float) -> RBCellState:
        alpha = list(self.location_alpha)
        precision = list(self.ridge_precision)
        natural = list(self.ridge_natural)
        alpha[location_index] += evidence_weight
        precision[location_index] += evidence_weight
        natural[location_index] += evidence_weight
        return RBCellState(
            location_alpha=tuple(alpha),
            ridge_precision=tuple(precision),
            ridge_natural=tuple(natural),
            information_precision=self.information_precision + evidence_weight,
            information_natural=self.information_natural + evidence_weight,
            observation_count=self.observation_count + 1,
        )

    def location_distribution(self, locations: Sequence[UUID]) -> dict[UUID, float]:
        return _normalize(dict(zip(locations, self.location_alpha, strict=True)))

    def combined_location_distribution(
        self,
        locations: Sequence[UUID],
        base: Mapping[UUID, float],
    ) -> dict[UUID, float]:
        """Consume all three analytic blocks in the decision readout."""

        dirichlet = self.location_distribution(locations)
        ridge = _normalize(
            {
                location: natural / precision
                for location, natural, precision in zip(
                    locations,
                    self.ridge_natural,
                    self.ridge_precision,
                    strict=True,
                )
            }
        )
        analytic = {
            location: 0.5 * dirichlet[location] + 0.5 * ridge[location] for location in locations
        }
        information_confidence = min(
            1.0,
            self.information_natural / self.information_precision,
        )
        return _normalize(
            {
                location: information_confidence * analytic[location]
                + (1.0 - information_confidence) * base[location]
                for location in locations
            }
        )


@dataclass(frozen=True, slots=True)
class FullJointCandidate:
    mechanism: EventMechanism
    ordered_roles: tuple[OrderedActorRole, ...]
    placement_actor: str
    role_key: str
    instance_association_key: str
    change_cause: ParticleChangeCause
    regime_decision: ParticleRegimeDecision
    regime_id: str | None
    active_regime_after: str
    retired_regimes_after: tuple[str, ...]

    @property
    def key(self) -> str:
        return "|".join(
            (
                self.mechanism.value,
                self.role_key,
                self.instance_association_key,
                self.change_cause.value,
                self.regime_decision.value,
                self.regime_id or "-",
            )
        )


@dataclass(frozen=True, slots=True)
class FullJointWorldState:
    typed_state: TypedParticleState
    source_revision_id: UUID
    event_chain: tuple[str, ...]
    ordered_actor_role_history: tuple[tuple[OrderedActorRole, ...], ...]
    instance_association_history: tuple[str, ...]
    change_cause_history: tuple[ParticleChangeCause, ...]
    habit_regime_history: tuple[str | None, ...]
    run_length_history: tuple[int, ...]
    revision_lineage: tuple[UUID, ...]
    active_regime: str
    retired_regimes: tuple[str, ...]
    rb_cells: Mapping[tuple[str, str], RBCellState]

    def validate_complete(self) -> None:
        lengths = {
            len(self.event_chain),
            len(self.ordered_actor_role_history),
            len(self.instance_association_history),
            len(self.change_cause_history),
            len(self.habit_regime_history),
            len(self.run_length_history),
        }
        if lengths != {len(self.event_chain)} or not self.event_chain:
            raise ValueError("event-time state histories must be non-empty and time aligned")
        if len(self.revision_lineage) < len(self.event_chain):
            raise ValueError("revision lineage cannot be shorter than the event chain")
        if self.typed_state.run_length != self.run_length_history[-1]:
            raise ValueError("typed run length and full history disagree")
        if self.typed_state.change_cause is not self.change_cause_history[-1]:
            raise ValueError("typed cause and full history disagree")
        if self.typed_state.regime_id != self.habit_regime_history[-1]:
            raise ValueError("typed regime and full history disagree")
        if self.typed_state.parent_revision_id != (
            None if len(self.revision_lineage) == 1 else self.revision_lineage[-2]
        ):
            raise ValueError("typed parent revision and lineage disagree")
        if self.typed_state.revision_id != self.revision_lineage[-1]:
            raise ValueError("typed revision and lineage head disagree")
        if self.typed_state.ordered_actor_roles != self.current_roles:
            raise ValueError("typed roles and role history disagree")
        if self.typed_state.instance_association_key != self.instance_association_history[-1]:
            raise ValueError("typed instance and instance history disagree")
        if (
            self.typed_state.regime_decision is not ParticleRegimeDecision.UNRESOLVED
            and self.typed_state.regime_id != self.active_regime
        ):
            raise ValueError("resolved typed regime and active regime disagree")
        if len(set(self.retired_regimes)) != len(self.retired_regimes):
            raise ValueError("retired regimes must be unique")
        if self.active_regime in self.retired_regimes:
            raise ValueError("active regime cannot simultaneously be retired")
        rb_widths = {len(cell.location_alpha) for cell in self.rb_cells.values()}
        if len(rb_widths) > 1:
            raise ValueError("particle-local RB cells disagree on location width")
        if any(not actor.strip() or not regime.strip() for actor, regime in self.rb_cells):
            raise ValueError("RB cell keys must bind non-empty actor and regime")

    @property
    def current_roles(self) -> tuple[OrderedActorRole, ...]:
        return self.ordered_actor_role_history[-1]

    @property
    def placement_actor(self) -> str:
        for role in self.current_roles:
            if role.role in {"placement_actor", "handoff_receiver", "responsible_actor"}:
                return role.actor_key
        raise ValueError("current role state has no placement authority")

    @property
    def signature(self) -> str:
        return content_sha256(
            {
                "event_chain": self.event_chain,
                "roles": [
                    [role.model_dump(mode="json") for role in roles]
                    for roles in self.ordered_actor_role_history
                ],
                "instances": self.instance_association_history,
                "causes": [cause.value for cause in self.change_cause_history],
                "regimes": self.habit_regime_history,
                "runs": self.run_length_history,
                "lineage": [str(value) for value in self.revision_lineage],
            }
        )


@dataclass(frozen=True, slots=True)
class StatefulJointParticle:
    world: FullJointWorldState
    posterior_probability: float


@dataclass(frozen=True, slots=True)
class OperatorFlowReceipt:
    step_index: int
    operator: StructureTwoOperator
    executed: bool
    changed_state: bool
    input_state_sha256: str
    output_state_sha256: str
    consumed_axes: tuple[str, ...]
    detail: str
    previous_receipt_sha256: str
    receipt_sha256: str


@dataclass(frozen=True, slots=True)
class ComputeFairnessReceipt:
    step_index: int
    arm: FullJointArm
    complete_state_axes: tuple[str, ...]
    robot_visible_input_sha256: str
    particle_budget: int
    parent_count: int
    proposal_support_policy: str
    proposal_support_size: int
    proposal_support_schema_sha256: str
    proposal_support_sha256: str
    target_score_evaluations: int
    proposal_draws: int
    score_operations_per_candidate: int
    score_operations: int
    proposal_model_hash: str
    common_random_number_sha256: str


@dataclass(frozen=True, slots=True)
class JointLedgerRecord:
    operation: str
    source_revision_id: UUID
    particle_revision_id: UUID
    owner_target_mass: float
    action_distribution: Mapping[UUID, float]
    previous_hash: str
    record_hash: str


class ReversibleJointRGRCLedger:
    def __init__(self, *, admission_floor: float, stability_steps: int) -> None:
        if not math.isfinite(admission_floor) or not 0.0 <= admission_floor <= 1.0:
            raise ValueError("RGRC admission floor must be a finite probability")
        if stability_steps < 1:
            raise ValueError("RGRC stability steps must be positive")
        self.admission_floor = admission_floor
        self.stability_steps = stability_steps
        self.records: list[JointLedgerRecord] = []
        self.active_source_revision_id: UUID | None = None
        self.active_distribution: dict[UUID, float] | None = None
        self._pending_signature: str | None = None
        self._pending_steps = 0

    @property
    def head_hash(self) -> str:
        return self.records[-1].record_hash if self.records else "GENESIS"

    def _append(
        self,
        operation: str,
        particle: StatefulJointParticle,
        owner_target_mass: float,
        distribution: Mapping[UUID, float],
        source_revision_id: UUID | None = None,
    ) -> None:
        subject_revision_id = source_revision_id or particle.world.source_revision_id
        payload = {
            "operation": operation,
            "source_revision_id": str(subject_revision_id),
            "particle_revision_id": str(particle.world.typed_state.revision_id),
            "owner_target_mass": owner_target_mass,
            "action_distribution": sorted((str(key), value) for key, value in distribution.items()),
            "previous_hash": self.head_hash,
        }
        self.records.append(
            JointLedgerRecord(
                operation=operation,
                source_revision_id=subject_revision_id,
                particle_revision_id=particle.world.typed_state.revision_id,
                owner_target_mass=owner_target_mass,
                action_distribution=dict(distribution),
                previous_hash=self.head_hash,
                record_hash=content_sha256(payload),
            )
        )

    def consider(
        self,
        particles: Sequence[StatefulJointParticle],
        *,
        owner_key: str,
        action_distribution: Mapping[UUID, float],
    ) -> bool:
        if not particles:
            raise ValueError("RGRC requires a non-empty particle posterior")
        posterior_mass = sum(particle.posterior_probability for particle in particles)
        if (
            any(
                not math.isfinite(particle.posterior_probability)
                or particle.posterior_probability < 0.0
                for particle in particles
            )
            or not 0.0 < posterior_mass <= 1.0 + 1e-6
        ):
            raise ValueError("RGRC particle posterior is invalid")
        if (
            not action_distribution
            or any(
                not math.isfinite(value) or not 0.0 <= value <= 1.0
                for value in action_distribution.values()
            )
            or abs(sum(action_distribution.values()) - 1.0) > 1e-6
        ):
            raise ValueError("RGRC action distribution is invalid")
        owner_target = [
            particle
            for particle in particles
            if particle.world.placement_actor == owner_key
            and particle.world.instance_association_history[-1] == "target_instance"
        ]
        mass = sum(particle.posterior_probability for particle in owner_target)
        if not owner_target or mass < self.admission_floor:
            self._pending_signature = None
            self._pending_steps = 0
            return False
        dominant = max(
            owner_target,
            key=lambda item: (item.posterior_probability, item.world.signature),
        )
        self._append("quarantine", dominant, mass, action_distribution)
        stability_signature = content_sha256(
            {
                "placement_actor": dominant.world.placement_actor,
                "instance": dominant.world.instance_association_history[-1],
                "active_regime": dominant.world.active_regime,
                "location": dominant.world.event_chain[-1].rsplit("|", maxsplit=1)[-1],
            }
        )
        if self._pending_signature == stability_signature:
            self._pending_steps += 1
        else:
            self._pending_signature = stability_signature
            self._pending_steps = 1
        # Admission stability is defined over the RGRC-owned signature above.
        # The particle run length spans a finer complete-state identity (including
        # cause), so requiring both would reset valid owner/regime/location
        # stability whenever the inferred cause changes and make admission
        # unreachable in an otherwise stable trajectory.
        if self._pending_steps < self.stability_steps:
            return True
        source_revision = dominant.world.source_revision_id
        if self.active_source_revision_id == source_revision:
            return True
        if self.active_source_revision_id is not None:
            self._append(
                "retract",
                dominant,
                mass,
                action_distribution,
                source_revision_id=self.active_source_revision_id,
            )
            operation = "corrected_revision"
        else:
            operation = "promote"
        self._append(operation, dominant, mass, action_distribution)
        self.active_source_revision_id = source_revision
        self.active_distribution = dict(action_distribution)
        return True

    def retract_source(self, source_revision_id: UUID, particle: StatefulJointParticle) -> bool:
        if self.active_source_revision_id != source_revision_id:
            return False
        distribution = self.active_distribution or {}
        self._append(
            "retract",
            particle,
            0.0,
            distribution,
            source_revision_id=source_revision_id,
        )
        self.active_source_revision_id = None
        self.active_distribution = None
        self._pending_signature = None
        self._pending_steps = 0
        return True

    def verify_chain(self) -> None:
        previous = "GENESIS"
        active_source: UUID | None = None
        active_distribution: dict[UUID, float] | None = None
        quarantined_source: UUID | None = None
        for record in self.records:
            if record.previous_hash != previous:
                raise ValueError("RGRC ledger previous-hash chain is broken")
            if not 0.0 <= record.owner_target_mass <= 1.0:
                raise ValueError("RGRC ledger owner-target mass is invalid")
            if record.action_distribution and (
                any(
                    not math.isfinite(value) or not 0.0 <= value <= 1.0
                    for value in record.action_distribution.values()
                )
                or abs(sum(record.action_distribution.values()) - 1.0) > 1e-6
            ):
                raise ValueError("RGRC ledger action distribution is invalid")
            payload = {
                "operation": record.operation,
                "source_revision_id": str(record.source_revision_id),
                "particle_revision_id": str(record.particle_revision_id),
                "owner_target_mass": record.owner_target_mass,
                "action_distribution": sorted(
                    (str(key), value) for key, value in record.action_distribution.items()
                ),
                "previous_hash": record.previous_hash,
            }
            if record.record_hash != content_sha256(payload):
                raise ValueError("RGRC ledger record hash mismatch")
            if record.operation == "quarantine":
                quarantined_source = record.source_revision_id
            elif record.operation == "promote":
                if active_source is not None or quarantined_source != record.source_revision_id:
                    raise ValueError("RGRC promote is unreachable from the recorded state")
                active_source = record.source_revision_id
                active_distribution = dict(record.action_distribution)
            elif record.operation == "retract":
                if active_source != record.source_revision_id:
                    raise ValueError("RGRC retract did not target the active source")
                active_source = None
                active_distribution = None
            elif record.operation == "corrected_revision":
                if active_source is not None or quarantined_source != record.source_revision_id:
                    raise ValueError(
                        "RGRC corrected revision is unreachable from the recorded state"
                    )
                active_source = record.source_revision_id
                active_distribution = dict(record.action_distribution)
            else:
                raise ValueError("RGRC ledger contains an unknown operation")
            previous = record.record_hash
        if active_source != self.active_source_revision_id:
            raise ValueError("RGRC derived active source disagrees with ledger state")
        if active_distribution != self.active_distribution:
            raise ValueError("RGRC derived active distribution disagrees with ledger state")


class StatefulFullJointRuntime:
    """Importance-corrected, recurrent full-state particle filter."""

    def __init__(
        self,
        *,
        arm: FullJointArm,
        config: StatefulFullJointConfig,
        neural_model: NeuralProposalModel,
        neutralized_operators: frozenset[StructureTwoOperator] = frozenset(),
    ) -> None:
        if not 0.0 <= config.neural_proposal_mix <= 1.0:
            raise ValueError("neural proposal mix must be in [0, 1]")
        if not 0.0 < config.unresolved_prior < 1.0:
            raise ValueError("unresolved prior must lie in (0, 1)")
        self.arm = arm
        self.config = config
        self.neural_model = neural_model
        if not neutralized_operators <= set(StructureTwoOperator):
            raise ValueError("neutralization names an operator outside the seven-operator spine")
        self.neutralized_operators = neutralized_operators
        self.particles: tuple[StatefulJointParticle, ...] = ()
        self.unresolved_probability = 1.0
        self.step_index = 0
        self.operator_flow_receipts: list[OperatorFlowReceipt] = []
        self.fairness_receipts: list[ComputeFairnessReceipt] = []
        self.revision_batches: list[ParticleRevisionBatch] = []
        self.importance_revision_receipts: list[tuple[ParticleRevisionReceipt, ...]] = []
        self.action_readout_traces: list[dict[UUID, float]] = []
        self.rgrc_ledger = ReversibleJointRGRCLedger(
            admission_floor=config.rgrc_owner_target_admission_floor,
            stability_steps=config.rgrc_stability_steps,
        )
        self._consumed_updates: set[UUID] = set()
        self._consumed_feedback_revisions: set[UUID] = set()
        self._consumed_feedback_records: set[UUID] = set()
        self._last_observation: FullJointObservation | None = None
        self._last_operator_receipt_sha256 = "GENESIS"

    def _capture_mutable_state(self) -> dict[str, Any]:
        names = (
            "particles",
            "unresolved_probability",
            "step_index",
            "operator_flow_receipts",
            "fairness_receipts",
            "revision_batches",
            "importance_revision_receipts",
            "action_readout_traces",
            "rgrc_ledger",
            "_consumed_updates",
            "_consumed_feedback_revisions",
            "_consumed_feedback_records",
            "_last_observation",
            "_last_operator_receipt_sha256",
        )
        return copy.deepcopy({name: getattr(self, name) for name in names})

    def _restore_mutable_state(self, snapshot: Mapping[str, Any]) -> None:
        for key, value in snapshot.items():
            setattr(self, key, value)

    @staticmethod
    def _systematic_draw_indices(
        probabilities: Sequence[float], count: int, seed_sha256: str
    ) -> tuple[int, ...]:
        offset = int(seed_sha256[:16], 16) / float(16**16) / count
        cumulative: list[float] = []
        running = 0.0
        for probability in probabilities:
            running += probability
            cumulative.append(running)
        cumulative[-1] = 1.0
        result: list[int] = []
        cursor = 0
        for draw in range(count):
            point = offset + draw / count
            while point > cumulative[cursor]:
                cursor += 1
            result.append(cursor)
        return tuple(result)

    def _neural_features(
        self,
        observation: FullJointObservation,
        parent: StatefulJointParticle | None,
    ) -> tuple[float, ...]:
        four = {
            cause: observation.cause_posterior[ParticleChangeCause(cause.value)]
            for cause in ChangeCause
        }
        actor_values = tuple(observation.actor_posterior.values())
        entropy = -sum(value * _log(value) for value in actor_values)
        parent_cause = None if parent is None else parent.world.change_cause_history[-1]
        return (
            *(four[cause] for cause in ChangeCause),
            observation.regime_change_probability,
            observation.identity_target_probability,
            observation.actor_posterior[observation.owner_actor_key],
            max(actor_values),
            entropy,
            *(float(parent_cause is ParticleChangeCause(cause.value)) for cause in ChangeCause),
            float(
                parent is not None
                and parent.world.typed_state.regime_decision
                in {ParticleRegimeDecision.CREATE, ParticleRegimeDecision.REACTIVATE}
            ),
            0.0 if parent is None else 1.0 / self.config.particle_budget,
            0.0 if parent is None else min(1.0, parent.world.typed_state.run_length / 10.0),
        )

    def _proposal_cause_and_change(
        self,
        observation: FullJointObservation,
        parent: StatefulJointParticle | None,
    ) -> tuple[dict[ParticleChangeCause, float], float]:
        neural_cause, neural_change = self.neural_model.predict(
            self._neural_features(observation, parent)
        )
        mix = self.config.neural_proposal_mix
        proposal: dict[ParticleChangeCause, float] = {}
        for cause in ParticleChangeCause:
            visible = observation.cause_posterior[cause]
            neural = (
                neural_cause[ChangeCause(cause.value)]
                if cause.value in {item.value for item in ChangeCause}
                else visible
            )
            proposal[cause] = (1.0 - mix) * visible + mix * neural
        return _normalize(proposal), (
            (1.0 - mix) * observation.regime_change_probability + mix * neural_change
        )

    @staticmethod
    def _instance_distribution(observation: FullJointObservation) -> dict[str, float]:
        mismatch = 1.0 - observation.identity_target_probability
        return {
            "target_instance": observation.identity_target_probability,
            "identity_mismatch": mismatch * 0.75,
            "unknown_instance": mismatch * 0.25,
        }

    def _regime_options(
        self,
        cause: ParticleChangeCause,
        parent: StatefulJointParticle | None,
        observation: FullJointObservation,
        change_probability: float,
    ) -> tuple[tuple[ParticleRegimeDecision, str | None, str, tuple[str, ...], float], ...]:
        active = observation.active_regime if parent is None else parent.world.active_regime
        retired = () if parent is None else parent.world.retired_regimes
        retired = retired[-self.config.maximum_retired_regimes :]
        if cause is not ParticleChangeCause.HABIT:
            return (
                (ParticleRegimeDecision.STAY, active, active, retired, 0.95),
                (ParticleRegimeDecision.UNRESOLVED, None, active, retired, 0.05),
            )
        stay = max(1e-6, 1.0 - change_probability)
        unresolved = max(1e-6, 0.10 * change_probability)
        create = max(1e-6, 0.65 * change_probability)
        options: list[tuple[ParticleRegimeDecision, str | None, str, tuple[str, ...], float]] = [
            (ParticleRegimeDecision.STAY, active, active, retired, stay),
            (ParticleRegimeDecision.UNRESOLVED, None, active, retired, unresolved),
        ]
        new_regime = f"{active}:route-c:{self.step_index + 1}"
        options.append(
            (
                ParticleRegimeDecision.CREATE,
                new_regime,
                new_regime,
                tuple(dict.fromkeys((*retired, active)))[-self.config.maximum_retired_regimes :],
                create,
            )
        )
        if retired:
            share = max(1e-6, 0.25 * change_probability) / len(retired)
            for target in retired:
                options.append(
                    (
                        ParticleRegimeDecision.REACTIVATE,
                        target,
                        target,
                        tuple(item for item in (*retired, active) if item != target)[
                            -self.config.maximum_retired_regimes :
                        ],
                        share,
                    )
                )
        else:
            options[2] = (*options[2][:-1], create + 0.25 * change_probability)
        total = sum(option[-1] for option in options)
        return tuple((*option[:-1], option[-1] / total) for option in options)

    def _candidates(
        self,
        observation: FullJointObservation,
        parent: StatefulJointParticle | None,
    ) -> tuple[tuple[FullJointCandidate, float], ...]:
        cause_q, change_q = self._proposal_cause_and_change(observation, parent)
        instances = self._instance_distribution(observation)
        actors = tuple(sorted(observation.actor_posterior))
        entries: list[tuple[FullJointCandidate, float]] = []
        for mechanism in EventMechanism:
            mechanism_q = observation.mechanism_posterior[mechanism]
            role_options: list[tuple[tuple[OrderedActorRole, ...], str, str, float]] = []
            if mechanism is EventMechanism.DIRECT_RELOCATION:
                for actor in actors:
                    role_options.append(
                        (
                            (
                                OrderedActorRole(role="pickup_actor", actor_key=actor),
                                OrderedActorRole(role="placement_actor", actor_key=actor),
                            ),
                            actor,
                            f"direct:{actor}",
                            observation.actor_posterior[actor],
                        )
                    )
            elif mechanism is EventMechanism.HANDOFF_RELOCATION:
                for role_key, role_probability in observation.ordered_role_posterior.items():
                    giver, receiver = parse_ordered_role_key(role_key)
                    role_options.append(
                        (
                            (
                                OrderedActorRole(role="handoff_giver", actor_key=giver),
                                OrderedActorRole(role="handoff_receiver", actor_key=receiver),
                            ),
                            receiver,
                            role_key,
                            role_probability,
                        )
                    )
            else:
                for actor in actors:
                    role_options.append(
                        (
                            (OrderedActorRole(role="responsible_actor", actor_key=actor),),
                            actor,
                            f"unknown:{actor}",
                            observation.actor_posterior[actor],
                        )
                    )
            for roles, placement_actor, role_key, role_q in role_options:
                for instance_key, instance_q in instances.items():
                    for cause in ParticleChangeCause:
                        for (
                            decision,
                            regime_id,
                            active_after,
                            retired_after,
                            regime_q,
                        ) in self._regime_options(
                            cause, parent, observation, change_probability=change_q
                        ):
                            candidate = FullJointCandidate(
                                mechanism=mechanism,
                                ordered_roles=roles,
                                placement_actor=placement_actor,
                                role_key=role_key,
                                instance_association_key=instance_key,
                                change_cause=cause,
                                regime_decision=decision,
                                regime_id=regime_id,
                                active_regime_after=active_after,
                                retired_regimes_after=retired_after,
                            )
                            q = (
                                max(mechanism_q, 1e-12)
                                * max(role_q, 1e-12)
                                * max(instance_q, 1e-12)
                                * max(cause_q[cause], 1e-12)
                                * max(regime_q, 1e-12)
                            )
                            entries.append((candidate, q))
        support = sorted(entries, key=lambda item: item[0].key)
        if not support:
            raise ValueError("complete Route-C proposal support is empty")
        total = sum(item[1] for item in support)
        return tuple((candidate, value / total) for candidate, value in support)

    def _transition_raw(
        self,
        parent: StatefulJointParticle | None,
        candidate: FullJointCandidate,
    ) -> float:
        if parent is None:
            return 0.0
        world = parent.world
        score = 0.0
        if StructureTwoOperator.PCHMP not in self.neutralized_operators:
            score += 0.8 * float(world.placement_actor == candidate.placement_actor)
            score += 0.7 * float(
                world.instance_association_history[-1] == candidate.instance_association_key
            )
            score += 0.4 * float(world.event_chain[-1].split("|")[0] == candidate.mechanism.value)
        if StructureTwoOperator.CF_BOCPD not in self.neutralized_operators:
            score += 0.6 * float(world.change_cause_history[-1] is candidate.change_cause)
        if StructureTwoOperator.CCRR not in self.neutralized_operators:
            score += 0.5 * float(world.active_regime == candidate.active_regime_after)
        return score

    def _main_log_factor(
        self,
        observation: FullJointObservation,
        candidate: FullJointCandidate,
    ) -> float:
        instances = StatefulFullJointRuntime._instance_distribution(observation)
        if candidate.mechanism is EventMechanism.HANDOFF_RELOCATION:
            role_probability = observation.ordered_role_posterior.get(candidate.role_key, 1e-12)
        else:
            role_probability = observation.actor_posterior.get(candidate.placement_actor, 1e-12)
        change = candidate.regime_decision in {
            ParticleRegimeDecision.CREATE,
            ParticleRegimeDecision.REACTIVATE,
        }
        regime_probability = (
            observation.regime_change_probability
            if change
            else 1.0 - observation.regime_change_probability
        )
        if candidate.regime_decision is ParticleRegimeDecision.UNRESOLVED:
            regime_probability = max(observation.unresolved_probability, 1e-12)
        score = 0.0
        if StructureTwoOperator.PCHMP not in self.neutralized_operators:
            score += _log(observation.mechanism_posterior[candidate.mechanism])
            score += _log(role_probability)
            score += _log(instances[candidate.instance_association_key])
        if StructureTwoOperator.CF_BOCPD not in self.neutralized_operators:
            score += _log(observation.cause_posterior[candidate.change_cause])
        if StructureTwoOperator.CCRR not in self.neutralized_operators:
            score += _log(regime_probability)
        return score

    @staticmethod
    def interaction_terms(
        observation: FullJointObservation,
        candidate: FullJointCandidate,
    ) -> tuple[float, ...]:
        """Cross-axis sufficient features shared by hand-set and learned potentials."""

        return (
            float(
                candidate.change_cause is ParticleChangeCause.ACTOR
                and candidate.mechanism is EventMechanism.HANDOFF_RELOCATION
            ),
            float(
                candidate.change_cause is ParticleChangeCause.IDENTITY
                and candidate.instance_association_key != "target_instance"
            ),
            float(
                candidate.change_cause is ParticleChangeCause.HABIT
                and candidate.regime_decision
                in {ParticleRegimeDecision.CREATE, ParticleRegimeDecision.REACTIVATE}
            ),
            float(
                candidate.mechanism is EventMechanism.HANDOFF_RELOCATION
                and candidate.role_key.endswith(f"=>{candidate.placement_actor}")
            ),
            float(
                candidate.placement_actor == observation.owner_actor_key
                and candidate.instance_association_key == "target_instance"
                and candidate.change_cause is ParticleChangeCause.HABIT
            ),
            float(
                candidate.placement_actor == "unknown_actor"
                and candidate.regime_decision
                in {ParticleRegimeDecision.CREATE, ParticleRegimeDecision.REACTIVATE}
            ),
        )

    def _interaction_log_factor(
        self,
        observation: FullJointObservation,
        candidate: FullJointCandidate,
    ) -> float:
        # Both arms execute this exact schedule.  The matched factorized arm sets
        # only the final coefficient to zero; support, reads and arithmetic stay matched.
        terms = self.interaction_terms(observation, candidate)
        coefficient = (
            self.config.joint_interaction_strength
            if self.arm is FullJointArm.STATEFUL_FULL_JOINT
            else 0.0
        )
        return coefficient * sum(
            (0.7, 0.8, 0.9, 0.3, 0.45, -1.2)[i] * value for i, value in enumerate(terms)
        )

    def _constraints(
        self,
        candidate: FullJointCandidate,
    ) -> tuple[StructuredConstraint, ...]:
        role_valid = bool(candidate.ordered_roles)
        identity_penalty = (
            -0.15
            if StructureTwoOperator.PCHMP not in self.neutralized_operators
            and candidate.instance_association_key == "unknown_instance"
            else 0.0
        )
        return (
            StructuredConstraint(
                factor=StructuredWeightFactor.PHYSICAL_EVENT_CONSTRAINT,
                accepted=True,
                log_potential=0.0,
            ),
            StructuredConstraint(
                factor=StructuredWeightFactor.ORDERED_ROLE_CONSTRAINT,
                accepted=role_valid,
                log_potential=0.0,
                rejection_reason=None if role_valid else "missing ordered role binding",
            ),
            StructuredConstraint(
                factor=StructuredWeightFactor.IDENTITY_CONSTRAINT,
                accepted=True,
                log_potential=identity_penalty,
            ),
            StructuredConstraint(
                factor=StructuredWeightFactor.PROVENANCE_CONSTRAINT,
                accepted=True,
                log_potential=0.0,
            ),
        )

    @staticmethod
    def _event_entry(candidate: FullJointCandidate, observation: FullJointObservation) -> str:
        return "|".join(
            (
                candidate.mechanism.value,
                candidate.role_key,
                candidate.instance_association_key,
                str(observation.observed_location_id),
            )
        )

    def _world_from_candidate(
        self,
        *,
        parent: StatefulJointParticle | None,
        candidate: FullJointCandidate,
        observation: FullJointObservation,
        draw_index: int,
        snapshot_id: UUID,
    ) -> FullJointWorldState:
        prior_world = None if parent is None else parent.world
        same_state = bool(
            prior_world is not None
            and prior_world.event_chain[-1].split("|")[0] == candidate.mechanism.value
            and prior_world.placement_actor == candidate.placement_actor
            and prior_world.instance_association_history[-1] == candidate.instance_association_key
            and prior_world.change_cause_history[-1] is candidate.change_cause
            and candidate.regime_decision is ParticleRegimeDecision.STAY
        )
        run_length = (
            prior_world.typed_state.run_length + 1 if same_state and prior_world is not None else 0
        )
        parent_particle_id = None if prior_world is None else prior_world.typed_state.particle_id
        parent_revision_id = None if prior_world is None else prior_world.typed_state.revision_id
        revision_id = content_uuid(
            "stateful-full-joint-revision",
            (snapshot_id, draw_index, candidate.key, parent_revision_id),
        )
        particle_id = content_uuid(
            "stateful-full-joint-particle",
            (snapshot_id, draw_index, candidate.key, parent_particle_id),
        )
        rb_cells = {} if prior_world is None else dict(prior_world.rb_cells)
        if (
            candidate.instance_association_key == "target_instance"
            and StructureTwoOperator.OPCEU not in self.neutralized_operators
        ):
            cell_key = (candidate.placement_actor, candidate.active_regime_after)
            cell = rb_cells.get(cell_key, RBCellState.prior(len(observation.known_location_ids)))
            location_index = observation.known_location_ids.index(observation.observed_location_id)
            evidence_weight = max(
                0.05,
                observation.actor_posterior.get(candidate.placement_actor, 0.0),
            )
            rb_cells[cell_key] = cell.update(location_index, evidence_weight)
        rb_hash = content_sha256(
            {
                f"{actor}|{regime}": asdict(cell)
                for (actor, regime), cell in sorted(rb_cells.items())
            }
        )
        typed = TypedParticleState(
            particle_id=particle_id,
            parent_particle_id=parent_particle_id,
            source_snapshot_id=snapshot_id,
            event_hypothesis_id=content_uuid(
                "stateful-full-joint-event", (snapshot_id, draw_index, candidate.key)
            ),
            revision_id=revision_id,
            parent_revision_id=parent_revision_id,
            ordered_actor_roles=candidate.ordered_roles,
            instance_association_key=candidate.instance_association_key,
            change_cause=candidate.change_cause,
            regime_decision=candidate.regime_decision,
            regime_id=candidate.regime_id,
            run_length=run_length,
            statistic_state_ref=f"full-rb:{rb_hash}",
            ledger_lineage_ref=f"route-c-rgrc:{self.rgrc_ledger.head_hash}",
        )
        world = FullJointWorldState(
            typed_state=typed,
            source_revision_id=observation.source_update_id,
            event_chain=(
                *(() if prior_world is None else prior_world.event_chain),
                self._event_entry(candidate, observation),
            ),
            ordered_actor_role_history=(
                *(() if prior_world is None else prior_world.ordered_actor_role_history),
                candidate.ordered_roles,
            ),
            instance_association_history=(
                *(() if prior_world is None else prior_world.instance_association_history),
                candidate.instance_association_key,
            ),
            change_cause_history=(
                *(() if prior_world is None else prior_world.change_cause_history),
                candidate.change_cause,
            ),
            habit_regime_history=(
                *(() if prior_world is None else prior_world.habit_regime_history),
                candidate.regime_id,
            ),
            run_length_history=(
                *(() if prior_world is None else prior_world.run_length_history),
                run_length,
            ),
            revision_lineage=(
                *(() if prior_world is None else prior_world.revision_lineage),
                revision_id,
            ),
            active_regime=candidate.active_regime_after,
            retired_regimes=candidate.retired_regimes_after,
            rb_cells=rb_cells,
        )
        world.validate_complete()
        return world

    def _state_sha256(self) -> str:
        return content_sha256(
            {
                "arm": self.arm.value,
                "unresolved": self.unresolved_probability,
                "particles": [
                    (item.world.signature, item.posterior_probability) for item in self.particles
                ],
                "ledger": self.rgrc_ledger.head_hash,
                "neutralized_operators": sorted(
                    operator.value for operator in self.neutralized_operators
                ),
            }
        )

    def _append_flow(
        self,
        operator: StructureTwoOperator,
        *,
        executed: bool,
        changed: bool,
        input_hash: str,
        output_payload: object,
        axes: tuple[str, ...],
        detail: str,
    ) -> str:
        output_hash = content_sha256(output_payload)
        receipt_payload = {
            "step_index": self.step_index,
            "operator": operator.value,
            "executed": executed,
            "changed_state": changed,
            "input_state_sha256": input_hash,
            "output_state_sha256": output_hash,
            "consumed_axes": axes,
            "detail": detail,
            "previous_receipt_sha256": self._last_operator_receipt_sha256,
        }
        receipt_hash = content_sha256(receipt_payload)
        self.operator_flow_receipts.append(
            OperatorFlowReceipt(
                step_index=self.step_index,
                operator=operator,
                executed=executed,
                changed_state=changed,
                input_state_sha256=input_hash,
                output_state_sha256=output_hash,
                consumed_axes=axes,
                detail=detail,
                previous_receipt_sha256=self._last_operator_receipt_sha256,
                receipt_sha256=receipt_hash,
            )
        )
        self._last_operator_receipt_sha256 = receipt_hash
        return output_hash

    def revise(self, observation: FullJointObservation) -> tuple[StatefulJointParticle, ...]:
        snapshot = self._capture_mutable_state()
        try:
            return self._revise_mutating(observation)
        except Exception:
            self._restore_mutable_state(snapshot)
            raise

    def _revise_mutating(
        self, observation: FullJointObservation
    ) -> tuple[StatefulJointParticle, ...]:
        # Revalidate mappings at the use boundary because the frozen dataclass may
        # still contain caller-owned mutable dictionaries.
        observation.__post_init__()
        if observation.source_update_id in self._consumed_updates:
            raise ValueError("full-joint source update was already consumed")
        self._consumed_updates.add(observation.source_update_id)
        self.step_index += 1
        before = self._state_sha256()
        opceu = self._append_flow(
            StructureTwoOperator.OPCEU,
            executed=True,
            changed=StructureTwoOperator.OPCEU not in self.neutralized_operators,
            input_hash=before,
            output_payload={
                "source": str(observation.source_update_id),
                "locations": observation.base_location_distribution,
            },
            axes=("event_chain", "instance_association"),
            detail=(
                "operator retained with a neutral statistic update"
                if StructureTwoOperator.OPCEU in self.neutralized_operators
                else "robot-visible observation and selection semantics admitted once"
            ),
        )
        pchmp = self._append_flow(
            StructureTwoOperator.ORRER_CHEH,
            executed=False,
            changed=False,
            input_hash=opceu,
            output_payload={"feedback": "not_present_during_forward_update"},
            axes=("revision_lineage",),
            detail="revision operator awaits embodied execution feedback",
        )
        pchmp = self._append_flow(
            StructureTwoOperator.PCHMP,
            executed=True,
            changed=StructureTwoOperator.PCHMP not in self.neutralized_operators,
            input_hash=pchmp,
            output_payload={
                "actor": observation.actor_posterior,
                "mechanism": {
                    key.value: value for key, value in observation.mechanism_posterior.items()
                },
                "roles": observation.ordered_role_posterior,
                "identity": observation.identity_target_probability,
            },
            axes=("event_chain", "ordered_actor_roles", "instance_association"),
            detail=(
                "operator retained with unit actor-mechanism-role potentials"
                if StructureTwoOperator.PCHMP in self.neutralized_operators
                else "joint event, role, actor, and instance evidence propagated"
            ),
        )
        cf = self._append_flow(
            StructureTwoOperator.CF_BOCPD,
            executed=True,
            changed=StructureTwoOperator.CF_BOCPD not in self.neutralized_operators,
            input_hash=pchmp,
            output_payload={
                "cause": {key.value: value for key, value in observation.cause_posterior.items()},
                "change": observation.regime_change_probability,
            },
            axes=("change_cause", "run_length"),
            detail=(
                "operator retained with a unit cause potential"
                if StructureTwoOperator.CF_BOCPD in self.neutralized_operators
                else "cause and run-length posterior supplied to the joint filter"
            ),
        )
        ccrr = self._append_flow(
            StructureTwoOperator.CCRR,
            executed=True,
            changed=StructureTwoOperator.CCRR not in self.neutralized_operators,
            input_hash=cf,
            output_payload={
                "active_regime": observation.active_regime,
                "change": observation.regime_change_probability,
            },
            axes=("change_cause", "habit_regime", "run_length"),
            detail=(
                "operator retained with a unit regime potential"
                if StructureTwoOperator.CCRR in self.neutralized_operators
                else "conditional regime transitions generated under cause constraints"
            ),
        )

        parents: tuple[StatefulJointParticle | None, ...] = (
            (None,) if not self.particles else tuple(self.particles)
        )
        local_by_parent: list[
            tuple[StatefulJointParticle | None, tuple[tuple[FullJointCandidate, float], ...]]
        ] = []
        all_entries: list[tuple[float, StatefulJointParticle | None, FullJointCandidate]] = []
        support_rows: list[dict[str, object]] = []
        for parent in parents:
            local = self._candidates(observation, parent)
            local_by_parent.append((parent, local))
            parent_q = 1.0 / len(parents)
            support_rows.append(
                {
                    "parent": "ROOT" if parent is None else parent.world.signature,
                    "candidates": [(candidate.key, child_q) for candidate, child_q in local],
                }
            )
            for candidate, child_q in local:
                all_entries.append((parent_q * child_q, parent, candidate))
        q_total = sum(item[0] for item in all_entries)
        all_entries = [
            (mass / q_total, parent, candidate) for mass, parent, candidate in all_entries
        ]
        seed_sha = content_sha256(
            {
                "protocol": PROTOCOL_ID,
                "source_update_id": observation.source_update_id,
                "particle_budget": self.config.particle_budget,
                "proposal_support_policy": self.config.proposal_support_policy,
                "common_random_number_scope": "source_update_and_particle_budget_only",
            }
        )
        proposal_support_sha256 = content_sha256(support_rows)
        proposal_support_schema_sha256 = content_sha256(
            {
                "policy": self.config.proposal_support_policy,
                "complete_state_axes": COMPLETE_STATE_AXES,
                "mechanisms": tuple(mechanism.value for mechanism in EventMechanism),
                "actor_keys": tuple(sorted(observation.actor_posterior)),
                "ordered_role_keys": tuple(sorted(observation.ordered_role_posterior)),
                "instance_associations": tuple(sorted(self._instance_distribution(observation))),
                "change_causes": tuple(cause.value for cause in ParticleChangeCause),
                "regime_rule": "stay+unresolved+create+all_retired_reactivations",
                "maximum_retired_regimes": self.config.maximum_retired_regimes,
            }
        )
        visible_input_sha256 = content_sha256(
            {
                "source_update_id": str(observation.source_update_id),
                "evidence_cluster_id": str(observation.evidence_cluster_id),
                "owner_actor_key": observation.owner_actor_key,
                "actor_posterior": observation.actor_posterior,
                "mechanism_posterior": {
                    key.value: value for key, value in observation.mechanism_posterior.items()
                },
                "ordered_role_posterior": observation.ordered_role_posterior,
                "identity_target_probability": observation.identity_target_probability,
                "cause_posterior": {
                    key.value: value for key, value in observation.cause_posterior.items()
                },
                "regime_change_probability": observation.regime_change_probability,
                "active_regime": observation.active_regime,
                "observed_location_id": str(observation.observed_location_id),
                "base_location_distribution": {
                    str(key): value for key, value in observation.base_location_distribution.items()
                },
                "known_location_ids": [str(value) for value in observation.known_location_ids],
                "unresolved_probability": observation.unresolved_probability,
            }
        )
        draws = self._systematic_draw_indices(
            [entry[0] for entry in all_entries], self.config.particle_budget, seed_sha
        )
        transition_normalizers: dict[UUID | None, float] = {}
        for parent, local in local_by_parent:
            transition_normalizers[
                None if parent is None else parent.world.typed_state.particle_id
            ] = _logsumexp([self._transition_raw(parent, candidate) for candidate, _ in local])

        snapshot_id = content_uuid("stateful-full-joint-snapshot", observation.source_update_id)
        receipts: list[ParticleRevisionReceipt] = []
        worlds: list[FullJointWorldState] = []
        for draw_index, entry_index in enumerate(draws):
            q_probability, parent, candidate = all_entries[entry_index]
            world = self._world_from_candidate(
                parent=parent,
                candidate=candidate,
                observation=observation,
                draw_index=draw_index,
                snapshot_id=snapshot_id,
            )
            parent_key = None if parent is None else parent.world.typed_state.particle_id
            transition_log_probability = (
                self._transition_raw(parent, candidate) - transition_normalizers[parent_key]
            )
            proposal = NeuralParticleProposal(
                proposal_id=content_uuid("stateful-full-joint-proposal", (snapshot_id, draw_index)),
                evidence_cluster_id=observation.evidence_cluster_id,
                operation=(
                    ParticleProposalOperation.REVISE
                    if parent is None
                    else ParticleProposalOperation.BRANCH
                ),
                source_particle_id=(
                    None if parent is None else parent.world.typed_state.particle_id
                ),
                source_snapshot_id=snapshot_id,
                proposed_state=world.typed_state,
                proposal_log_probability=_log(q_probability),
                proposer_model_version=self.neural_model.model_hash,
                proposer_code_version=PROTOCOL_ID,
            )
            receipts.append(
                ParticleRevisionReceipt(
                    proposal=proposal,
                    prior_log_weight=(
                        0.0 if parent is None else _log(parent.posterior_probability)
                    ),
                    transition_log_probability=transition_log_probability,
                    observation_log_likelihood=0.0,
                    posterior_projection_log_factor=(
                        self._main_log_factor(observation, candidate)
                        + self._interaction_log_factor(observation, candidate)
                    ),
                    evidence_semantics="posterior_projection_not_likelihood",
                    source_posterior_snapshot_id=observation.source_update_id,
                    constraints=self._constraints(candidate),
                )
            )
            worlds.append(world)
        sampled_log_evidence = _logsumexp(
            [receipt.unnormalized_log_weight for receipt in receipts]
        ) - math.log(self.config.particle_budget)
        unresolved_log_weight = (
            sampled_log_evidence
            + math.log(self.config.particle_budget)
            + _log(self.config.unresolved_prior)
            - _log(1.0 - self.config.unresolved_prior)
        )
        batch = normalize_particle_revisions(
            tuple(receipts), unresolved_log_weight=unresolved_log_weight
        )
        self.particles = tuple(
            StatefulJointParticle(world=world, posterior_probability=weight.posterior_probability)
            for world, weight in zip(worlds, batch.particle_weights, strict=True)
        )
        self.unresolved_probability = batch.unresolved_probability
        self.revision_batches.append(batch)
        self.importance_revision_receipts.append(tuple(receipts))
        self._last_observation = observation
        joint_distribution = self._posterior_action_distribution(observation, include_ledger=False)
        ledger_before = self.rgrc_ledger.head_hash
        if StructureTwoOperator.RGRC not in self.neutralized_operators:
            self.rgrc_ledger.consider(
                self.particles,
                owner_key=observation.owner_actor_key,
                action_distribution=joint_distribution,
            )
        self._append_flow(
            StructureTwoOperator.RGRC,
            executed=True,
            changed=ledger_before != self.rgrc_ledger.head_hash,
            input_hash=ccrr,
            output_payload={"ledger_head": self.rgrc_ledger.head_hash},
            axes=COMPLETE_STATE_AXES,
            detail=(
                "operator retained while long-term admission is neutralized"
                if StructureTwoOperator.RGRC in self.neutralized_operators
                else "only joint owner-target mass with stable lineage may enter long-term memory"
            ),
        )
        self._append_flow(
            StructureTwoOperator.CIAV,
            executed=False,
            changed=False,
            input_hash=self._state_sha256(),
            output_payload={"verification": "not_selected_or_recorded_separately"},
            axes=("change_cause", "ordered_actor_roles", "revision_lineage"),
            detail="active verification is recorded separately when selected",
        )
        self.fairness_receipts.append(
            ComputeFairnessReceipt(
                step_index=self.step_index,
                arm=self.arm,
                complete_state_axes=COMPLETE_STATE_AXES,
                robot_visible_input_sha256=visible_input_sha256,
                particle_budget=self.config.particle_budget,
                parent_count=len(parents),
                proposal_support_policy=self.config.proposal_support_policy,
                proposal_support_size=len(all_entries),
                proposal_support_schema_sha256=proposal_support_schema_sha256,
                proposal_support_sha256=proposal_support_sha256,
                target_score_evaluations=len(receipts),
                proposal_draws=len(draws),
                score_operations_per_candidate=SCORE_OPERATIONS_PER_CANDIDATE,
                score_operations=len(receipts) * SCORE_OPERATIONS_PER_CANDIDATE,
                proposal_model_hash=self.neural_model.model_hash,
                common_random_number_sha256=seed_sha,
            )
        )
        return self.particles

    def record_verification(
        self,
        *,
        source_update_id: UUID,
        owner_probability_before: float,
        owner_probability_after: float,
    ) -> None:
        for name, value in (
            ("owner_probability_before", owner_probability_before),
            ("owner_probability_after", owner_probability_after),
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be a finite probability")
        input_hash = self._state_sha256()
        changed = (
            StructureTwoOperator.CIAV not in self.neutralized_operators
            and abs(owner_probability_before - owner_probability_after) > 1e-12
        )
        self._append_flow(
            StructureTwoOperator.CIAV,
            executed=True,
            changed=changed,
            input_hash=input_hash,
            output_payload={
                "source_update_id": str(source_update_id),
                "owner_before": owner_probability_before,
                "owner_after": owner_probability_after,
            },
            axes=("ordered_actor_roles", "change_cause", "revision_lineage"),
            detail=(
                "operator retained while verification evidence is neutralized"
                if StructureTwoOperator.CIAV in self.neutralized_operators
                else "verification changes actor evidence before joint revision"
            ),
        )

    def apply_feedback(self, trace: Any) -> None:
        snapshot = self._capture_mutable_state()
        try:
            self._apply_feedback_mutating(trace)
        except Exception:
            self._restore_mutable_state(snapshot)
            raise

    def _apply_feedback_mutating(self, trace: Any) -> None:
        if not self.particles:
            return
        if trace.feedback_record_id in self._consumed_feedback_records:
            raise ValueError("full-joint feedback record was already consumed")
        if trace.corrected_revision_id in self._consumed_feedback_revisions:
            raise ValueError("full-joint feedback revision was already consumed")
        if trace.superseded_revision_id not in self._consumed_updates:
            raise ValueError("full-joint feedback does not target an admitted source revision")

        def probability_map(items: Sequence[Any], name: str) -> dict[str, float]:
            pairs = [(str(item.key), float(item.probability)) for item in items]
            if len({key for key, _ in pairs}) != len(pairs):
                raise ValueError(f"{name} contains duplicate keys")
            return dict(pairs)

        before = self._state_sha256()
        actor_after = probability_map(trace.actor_posterior_after, "actor feedback")
        mechanism_after = probability_map(trace.mechanism_posterior_after, "mechanism feedback")
        role_after = probability_map(trace.role_posterior_after, "role feedback")
        for name, values in (
            ("actor feedback", actor_after),
            ("mechanism feedback", mechanism_after),
            ("role feedback", role_after),
        ):
            if not values or any(
                not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0
                for value in values.values()
            ):
                raise ValueError(f"{name} must contain finite probabilities")
            if sum(values.values()) <= 0.0:
                raise ValueError(f"{name} has no positive probability mass")
        actor_after = _normalize(actor_after)
        mechanism_after = _normalize(mechanism_after)
        role_after = _normalize(role_after)
        self._consumed_feedback_revisions.add(trace.corrected_revision_id)
        self._consumed_feedback_records.add(trace.feedback_record_id)
        if StructureTwoOperator.ORRER_CHEH in self.neutralized_operators:
            self._append_flow(
                StructureTwoOperator.ORRER_CHEH,
                executed=True,
                changed=False,
                input_hash=before,
                output_payload={
                    "feedback_record_id": str(trace.feedback_record_id),
                    "neutralized": True,
                },
                axes=COMPLETE_STATE_AXES,
                detail="operator retained while feedback likelihood is replaced by identity",
            )
            return
        updated: list[StatefulJointParticle] = []
        masses: list[float] = []
        for particle in self.particles:
            world = particle.world
            mechanism_key = world.event_chain[-1].split("|")[0]
            role_key = (
                ordered_role_key(
                    next(
                        role.actor_key
                        for role in world.current_roles
                        if role.role == "handoff_giver"
                    ),
                    next(
                        role.actor_key
                        for role in world.current_roles
                        if role.role == "handoff_receiver"
                    ),
                )
                if any(role.role == "handoff_giver" for role in world.current_roles)
                else ""
            )
            likelihood = max(actor_after.get(world.placement_actor, 1e-6), 1e-6)
            likelihood *= max(mechanism_after.get(mechanism_key, 1e-6), 1e-6)
            if role_key:
                likelihood *= max(role_after.get(role_key, 1e-6), 1e-6)
            masses.append(particle.posterior_probability * likelihood)
        normalized = _normalize(dict(enumerate(masses)))
        for index, particle in enumerate(self.particles):
            world = particle.world
            corrected_revision = content_uuid(
                "stateful-full-joint-feedback-revision",
                (world.typed_state.revision_id, trace.corrected_revision_id),
            )
            typed = world.typed_state.model_copy(
                update={
                    "parent_revision_id": world.typed_state.revision_id,
                    "revision_id": corrected_revision,
                    "ledger_lineage_ref": f"route-c-rgrc:{self.rgrc_ledger.head_hash}",
                }
            )
            corrected = replace(
                world,
                typed_state=typed,
                source_revision_id=trace.corrected_revision_id,
                revision_lineage=(*world.revision_lineage, corrected_revision),
            )
            corrected.validate_complete()
            updated.append(
                StatefulJointParticle(
                    world=corrected,
                    posterior_probability=(1.0 - self.unresolved_probability) * normalized[index],
                )
            )
        dominant = max(updated, key=lambda item: item.posterior_probability)
        ledger_changed = bool(getattr(trace, "contradictory", True)) and (
            self.rgrc_ledger.retract_source(trace.superseded_revision_id, dominant)
        )
        self.particles = tuple(updated)
        self._append_flow(
            StructureTwoOperator.ORRER_CHEH,
            executed=True,
            changed=True,
            input_hash=before,
            output_payload={
                "corrected_revision_id": str(trace.corrected_revision_id),
                "particle_state": self._state_sha256(),
            },
            axes=COMPLETE_STATE_AXES,
            detail="feedback reweighted the complete joint state and appended revision lineage",
        )
        if ledger_changed:
            self._append_flow(
                StructureTwoOperator.RGRC,
                executed=True,
                changed=True,
                input_hash=before,
                output_payload={"ledger_head": self.rgrc_ledger.head_hash},
                axes=("revision_lineage", "ordered_actor_roles", "instance_association"),
                detail="feedback retracted the superseded long-term joint admission",
            )

    def _posterior_action_distribution(
        self,
        observation: FullJointObservation,
        *,
        include_ledger: bool,
    ) -> dict[UUID, float]:
        base = _normalize(observation.base_location_distribution)
        accumulated = dict.fromkeys(observation.known_location_ids, 0.0)
        consumed_mass = 0.0
        cause_strength = {
            ParticleChangeCause.OBSERVATION: 0.45,
            ParticleChangeCause.ACTOR: 0.65,
            ParticleChangeCause.IDENTITY: 0.35,
            ParticleChangeCause.HABIT: 1.0,
            ParticleChangeCause.NOISE: 0.20,
            ParticleChangeCause.UNRESOLVED: 0.05,
        }
        for particle in self.particles:
            world = particle.world
            if (
                world.placement_actor != observation.owner_actor_key
                or world.instance_association_history[-1] != "target_instance"
            ):
                continue
            cell = world.rb_cells.get((observation.owner_actor_key, world.active_regime))
            component = (
                base
                if cell is None
                else cell.combined_location_distribution(
                    observation.known_location_ids,
                    base,
                )
            )
            mechanism_strength = (
                0.55
                if world.event_chain[-1].startswith(EventMechanism.UNKNOWN_MECHANISM.value)
                else 1.0
            )
            run_strength = min(1.0, 0.55 + 0.08 * world.typed_state.run_length)
            weight = (
                particle.posterior_probability
                * cause_strength[world.change_cause_history[-1]]
                * mechanism_strength
                * run_strength
            )
            consumed_mass += weight
            for location, probability in component.items():
                accumulated[location] += weight * probability
        remainder = max(0.0, 1.0 - consumed_mass)
        for location, probability in base.items():
            accumulated[location] += remainder * probability
        result = _normalize(accumulated)
        if (
            include_ledger
            and StructureTwoOperator.RGRC not in self.neutralized_operators
            and self.rgrc_ledger.active_distribution is not None
        ):
            result = _normalize(
                {
                    location: 0.75 * result[location]
                    + 0.25 * self.rgrc_ledger.active_distribution.get(location, 0.0)
                    for location in observation.known_location_ids
                }
            )
        return result

    def action_distribution(self) -> dict[UUID, float]:
        if self._last_observation is None:
            raise ValueError("stateful joint action requested before an observation")
        return self._posterior_action_distribution(self._last_observation, include_ledger=True)

    @property
    def unknown_actor_probability(self) -> float:
        if self._last_observation is None:
            return 1.0
        return min(
            1.0,
            self.unresolved_probability
            + sum(
                particle.posterior_probability
                for particle in self.particles
                if particle.world.placement_actor == "unknown_actor"
            ),
        )

    def verify_internal_contracts(self) -> None:
        particle_masses = [particle.posterior_probability for particle in self.particles]
        total = self.unresolved_probability + sum(particle_masses)
        if (
            not math.isfinite(self.unresolved_probability)
            or not 0.0 <= self.unresolved_probability <= 1.0
            or any(not math.isfinite(value) or value < 0.0 for value in particle_masses)
            or not math.isfinite(total)
            or abs(total - 1.0) > 1e-9
        ):
            raise ValueError("full-joint posterior is not normalized")
        if (
            self.step_index != len(self.fairness_receipts)
            or len(self._consumed_updates) != len(self.fairness_receipts)
            or len(self.revision_batches) != len(self.fairness_receipts)
            or len(self.importance_revision_receipts) != len(self.fairness_receipts)
        ):
            raise ValueError("full-joint revision state-machine counts disagree")
        if len(self._consumed_feedback_records) != len(self._consumed_feedback_revisions):
            raise ValueError("full-joint feedback identity counts disagree")
        for particle in self.particles:
            particle.world.validate_complete()
        if any(
            receipt.complete_state_axes != COMPLETE_STATE_AXES for receipt in self.fairness_receipts
        ):
            raise ValueError("fairness receipt omitted a complete-state axis")
        for fairness_receipt in self.fairness_receipts:
            if fairness_receipt.proposal_support_policy != "enumerate_all_positive_support":
                raise ValueError("fairness receipt used truncated proposal support")
            if (
                fairness_receipt.target_score_evaluations != self.config.particle_budget
                or fairness_receipt.proposal_draws != self.config.particle_budget
                or fairness_receipt.score_operations
                != fairness_receipt.target_score_evaluations
                * fairness_receipt.score_operations_per_candidate
            ):
                raise ValueError("fairness receipt does not match executed target-score budget")
            if (
                fairness_receipt.step_index < 1
                or fairness_receipt.proposal_support_size
                < fairness_receipt.target_score_evaluations
                or fairness_receipt.parent_count not in {1, fairness_receipt.particle_budget}
                or len(fairness_receipt.robot_visible_input_sha256) != 64
                or len(fairness_receipt.proposal_support_schema_sha256) != 64
                or len(fairness_receipt.proposal_support_sha256) != 64
                or len(fairness_receipt.proposal_model_hash) != 64
                or len(fairness_receipt.common_random_number_sha256) != 64
            ):
                raise ValueError("fairness receipt provenance is malformed")
        previous = "GENESIS"
        previous_step = 0
        for operator_receipt in self.operator_flow_receipts:
            if operator_receipt.changed_state and not operator_receipt.executed:
                raise ValueError("operator receipt changed state without execution")
            if not operator_receipt.consumed_axes or not set(
                operator_receipt.consumed_axes
            ).issubset(COMPLETE_STATE_AXES):
                raise ValueError("operator receipt consumed an unknown state axis")
            if not previous_step <= operator_receipt.step_index <= self.step_index:
                raise ValueError("operator receipt step ordering is invalid")
            previous_step = operator_receipt.step_index
            if operator_receipt.previous_receipt_sha256 != previous:
                raise ValueError("operator receipt hash chain is broken")
            payload = {
                "step_index": operator_receipt.step_index,
                "operator": operator_receipt.operator.value,
                "executed": operator_receipt.executed,
                "changed_state": operator_receipt.changed_state,
                "input_state_sha256": operator_receipt.input_state_sha256,
                "output_state_sha256": operator_receipt.output_state_sha256,
                "consumed_axes": operator_receipt.consumed_axes,
                "detail": operator_receipt.detail,
                "previous_receipt_sha256": operator_receipt.previous_receipt_sha256,
            }
            if operator_receipt.receipt_sha256 != content_sha256(payload):
                raise ValueError("operator receipt content hash mismatch")
            previous = operator_receipt.receipt_sha256
        if previous != self._last_operator_receipt_sha256:
            raise ValueError("operator receipt head hash mismatch")
        self.rgrc_ledger.verify_chain()


def _complete_cause_posterior(
    state: _FullProjectTwoMethod,
    identity_target_probability: float,
) -> dict[ParticleChangeCause, float]:
    upstream = _cause_posterior(state)
    identity_mass = 0.22 * (1.0 - identity_target_probability)
    unresolved_mass = 0.03
    remaining = 1.0 - identity_mass - unresolved_mass
    values = {
        ParticleChangeCause(cause.value): remaining * probability
        for cause, probability in upstream.items()
    }
    values[ParticleChangeCause.IDENTITY] = identity_mass
    values[ParticleChangeCause.UNRESOLVED] = unresolved_mass
    return _normalize(values)


def observation_from_runtime(
    state: _FullProjectTwoMethod,
    episode: ProjectTwoReplayEpisode,
    step: ProjectTwoReplayStep,
) -> FullJointObservation | None:
    result = state.step_results.get(step.step_id)
    transformed = state.evidence_transform(step)
    if (
        result is None
        or transformed.after is None
        or transformed.after.detected_location_id is None
    ):
        return None
    actors = _normalize(result.actor_posterior)
    mechanisms = (
        dict(transformed.mechanism_evidence.mechanism_posterior)
        if transformed.mechanism_evidence is not None
        else {
            EventMechanism.DIRECT_RELOCATION: 0.45,
            EventMechanism.HANDOFF_RELOCATION: 0.45,
            EventMechanism.UNKNOWN_MECHANISM: 0.10,
        }
    )
    mechanisms = _normalize(
        {mechanism: mechanisms.get(mechanism, 0.0) for mechanism in EventMechanism}
    )
    roles = (
        dict(transformed.ordered_role_evidence.ordered_role_posterior)
        if transformed.ordered_role_evidence is not None
        else {
            ordered_role_key(giver, receiver): actors[giver] * actors[receiver]
            for giver in actors
            for receiver in actors
            if giver != receiver
        }
    )
    roles = _normalize(roles)
    identity_probability = _identity_probability(
        transformed,
        target_object_id=transformed.object_instance_id,
    )
    base = state.spine.action_location_distribution(
        state.spine.current_snapshot,
        readout=state.action_readout,
    )
    cluster = (
        transformed.unified_evidence.evidence_cluster_id
        if transformed.unified_evidence is not None
        else (
            transformed.actor_evidence.evidence_cluster_id
            if transformed.actor_evidence is not None
            else content_uuid("stateful-full-joint-cluster", transformed.step_id)
        )
    )
    return FullJointObservation(
        source_update_id=result.event_revision_id,
        evidence_cluster_id=cluster,
        owner_actor_key=episode.owner_actor_key,
        actor_posterior=actors,
        mechanism_posterior=mechanisms,
        ordered_role_posterior=roles,
        identity_target_probability=identity_probability,
        cause_posterior=_complete_cause_posterior(state, identity_probability),
        regime_change_probability=result.decision.change_probability,
        active_regime=result.active_regime,
        observed_location_id=transformed.after.detected_location_id,
        base_location_distribution=_normalize(base),
        known_location_ids=tuple(state.locations),
        unresolved_probability=min(
            0.95,
            max(0.01, result.event_posterior.unresolved_probability),
        ),
    )


class StatefulFullJointActionState:
    """Seven-operator replay spine plus the Route-C full-state joint controller."""

    def __init__(
        self,
        state: Any,
        episode: ProjectTwoReplayEpisode,
        runtime: StatefulFullJointRuntime,
    ) -> None:
        self._state = state
        self._episode = episode
        self.runtime = runtime
        self._trace_cursor = 0
        self._verification_cursor = 0
        self.operator_retention_receipt = {
            operator.value: True for operator in StructureTwoOperator
        }

    def observe(self, step: ProjectTwoReplayStep) -> None:
        self._state.observe(step)
        observation = observation_from_runtime(self._state, self._episode, step)
        if observation is None:
            return
        verification_receipts = tuple(getattr(self._state, "ciav_opceu_receipts", ()))
        fast_receipts = tuple(self._state.spine.fast_action_verification_receipts)
        if len(fast_receipts) > self._verification_cursor:
            latest = fast_receipts[-1]
            actors = dict(observation.actor_posterior)
            before = actors[observation.owner_actor_key]
            after = latest.owner_mass_after
            other_total = sum(
                probability
                for actor, probability in actors.items()
                if actor != observation.owner_actor_key
            )
            remainder = 1.0 - after
            actors = {
                actor: (
                    after
                    if actor == observation.owner_actor_key
                    else (
                        remainder * probability / other_total
                        if other_total > 0.0
                        else remainder / max(1, len(actors) - 1)
                    )
                )
                for actor, probability in actors.items()
            }
            observation = replace(observation, actor_posterior=_normalize(actors))
            self.runtime.record_verification(
                source_update_id=observation.source_update_id,
                owner_probability_before=before,
                owner_probability_after=after,
            )
            self._verification_cursor = len(fast_receipts)
        elif len(verification_receipts) > self._verification_cursor:
            # Defensive: a CIAV receipt without its fast-ledger receipt is not
            # silently interpreted as a posterior update.
            raise ValueError("CIAV receipt is not bound to the reversible fast ledger")
        self.runtime.revise(observation)

    def predict(self) -> _Prediction:
        native = self._state.predict()
        if not self.runtime.particles:
            return cast(_Prediction, native)
        distribution = self.runtime.action_distribution()
        self.runtime.action_readout_traces.append(dict(distribution))
        ranked = tuple(sorted(distribution, key=lambda key: (-distribution[key], str(key))))
        return _Prediction(
            put_back=ranked[0],
            search_order=ranked,
            unknown_probability=self.runtime.unknown_actor_probability,
        )

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        self._state.feedback(step)
        traces = tuple(getattr(self._state, "revision_action_traces", ()))
        for trace_index, trace in enumerate(traces[self._trace_cursor :], start=self._trace_cursor):
            # The composed prototype spine allocates corrected revision UUIDs with
            # uuid4.  Route C must not let those transport identities make a seeded
            # replay scientifically non-reproducible, so its private lineage uses a
            # deterministic alias bound to the immutable feedback record and order.
            corrected_revision_id = (
                trace.superseded_revision_id
                if trace.corrected_revision_id == trace.superseded_revision_id
                else content_uuid(
                    "stateful-full-joint-canonical-feedback",
                    {
                        "episode_id": str(self._episode.episode_id),
                        "feedback_record_id": str(trace.feedback_record_id),
                        "trace_index": trace_index,
                    },
                )
            )
            self.runtime.apply_feedback(
                trace.model_copy(update={"corrected_revision_id": corrected_revision_id})
            )
        self._trace_cursor = len(traces)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._state, name)


def build_stateful_full_joint_state(
    *,
    repository_root: Path,
    dataset: Any,
    episode: ProjectTwoReplayEpisode,
    arm: FullJointArm,
    ciav_enabled: bool = True,
) -> StatefulFullJointActionState:
    config = load_stateful_full_joint_config(repository_root)
    neural_model = load_neural_proposal_model(config.neural_proposal_model_path)
    base = _FullProjectTwoMethod(
        episode,
        owner_threshold=0.4,
        action_readout=_action_readout(),
    )
    state: Any = _CIAVState(
        base,
        dataset,
        episode,
        enabled=ciav_enabled,
        cost_multiplier=1.0,
    )
    runtime = StatefulFullJointRuntime(arm=arm, config=config, neural_model=neural_model)
    return StatefulFullJointActionState(state, episode, runtime)


def evaluate_stateful_full_joint_episode(
    *,
    repository_root: Path,
    dataset: Any,
    episode: ProjectTwoReplayEpisode,
    arm: FullJointArm,
) -> tuple[Any, StatefulFullJointRuntime]:
    state = build_stateful_full_joint_state(
        repository_root=repository_root,
        dataset=dataset,
        episode=episode,
        arm=arm,
    )
    metric = ProjectTwoActionBenchmarkV02().evaluate_custom_state(dataset, episode, state)
    state.runtime.verify_internal_contracts()
    return metric, state.runtime


def _metric_summary(metrics: Sequence[Any]) -> dict[str, float]:
    return {
        "episode_count": float(len(metrics)),
        "put_back_error_rate": mean(metric.put_back_error_rate for metric in metrics),
        "search_error_rate": mean(metric.search_error_rate for metric in metrics),
        "cumulative_action_regret_per_step": (
            sum(metric.cumulative_action_regret for metric in metrics)
            / sum(metric.step_count for metric in metrics)
        ),
        "cumulative_search_regret_per_step": (
            sum(metric.cumulative_search_regret for metric in metrics)
            / sum(metric.step_count for metric in metrics)
        ),
        "owner_habit_contamination": mean(metric.owner_habit_contamination for metric in metrics),
        "unknown_calibration_brier": mean(metric.unknown_calibration_brier for metric in metrics),
    }


def _metric_summary_from_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    total_steps = sum(int(row["step_count"]) for row in rows)
    if not rows or total_steps <= 0:
        raise ValueError("Route-C metric summary requires non-empty positive-step rows")
    return {
        "episode_count": float(len(rows)),
        "put_back_error_rate": mean(float(row["put_back_error_rate"]) for row in rows),
        "search_error_rate": mean(float(row["search_error_rate"]) for row in rows),
        "cumulative_action_regret_per_step": (
            sum(float(row["cumulative_action_regret"]) for row in rows) / total_steps
        ),
        "cumulative_search_regret_per_step": (
            sum(float(row["cumulative_search_regret"]) for row in rows) / total_steps
        ),
        "owner_habit_contamination": mean(float(row["owner_habit_contamination"]) for row in rows),
        "unknown_calibration_brier": mean(float(row["unknown_calibration_brier"]) for row in rows),
    }


def _runtime_audit_payload(
    runtime: StatefulFullJointRuntime,
    *,
    episode_id: UUID,
) -> dict[str, Any]:
    runtime.verify_internal_contracts()
    action_traces = [
        {str(location): probability for location, probability in sorted(trace.items())}
        for trace in runtime.action_readout_traces
    ]
    ledger_records = [
        {
            "operation": record.operation,
            "source_revision_id": str(record.source_revision_id),
            "particle_revision_id": str(record.particle_revision_id),
            "owner_target_mass": record.owner_target_mass,
            "action_distribution": {
                str(location): probability
                for location, probability in sorted(record.action_distribution.items())
            },
            "previous_hash": record.previous_hash,
            "record_hash": record.record_hash,
        }
        for record in runtime.rgrc_ledger.records
    ]
    fairness = [
        {
            **asdict(receipt),
            "arm": receipt.arm.value,
            "complete_state_axes": list(receipt.complete_state_axes),
        }
        for receipt in runtime.fairness_receipts
    ]
    operators = [
        {
            **asdict(receipt),
            "operator": receipt.operator.value,
            "consumed_axes": list(receipt.consumed_axes),
        }
        for receipt in runtime.operator_flow_receipts
    ]
    return {
        "episode_id": str(episode_id),
        "arm": runtime.arm.value,
        "final_state_sha256": runtime._state_sha256(),
        "operator_receipt_head_sha256": runtime._last_operator_receipt_sha256,
        "operator_flow_receipts": operators,
        "fairness_receipts": fairness,
        "importance_revision_batch_sha256": [
            content_sha256([receipt.model_dump(mode="json") for receipt in revision_receipts])
            for revision_receipts in runtime.importance_revision_receipts
        ],
        "normalized_revision_batch_sha256": [
            content_sha256(batch.model_dump(mode="json")) for batch in runtime.revision_batches
        ],
        "action_readout_trace_count": len(action_traces),
        "action_readout_trace_sha256": content_sha256(action_traces),
        "rgrc_ledger_head_sha256": runtime.rgrc_ledger.head_hash,
        "rgrc_active_source_revision_id": (
            None
            if runtime.rgrc_ledger.active_source_revision_id is None
            else str(runtime.rgrc_ledger.active_source_revision_id)
        ),
        "rgrc_active_distribution": (
            None
            if runtime.rgrc_ledger.active_distribution is None
            else {
                str(location): probability
                for location, probability in sorted(runtime.rgrc_ledger.active_distribution.items())
            }
        ),
        "rgrc_ledger_records": ledger_records,
    }


def _deterministic_result_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(result))
    payload.pop("content_sha256", None)
    payload.pop("deterministic_replay_sha256", None)
    payload.pop("wall_clock_seconds", None)
    return payload


def _fairness_comparison_payload(
    receipt: ComputeFairnessReceipt | Mapping[str, Any],
) -> dict[str, Any]:
    """Return the pre-treatment fairness fields for a paired arm receipt.

    The complete support *content* is retained as provenance but is intentionally
    excluded here: after the first action, treatment-specific posterior weights and
    revision identifiers are legitimate causal descendants of the joint/factorized
    choice.  The support schema, visible input, budget, proposal model and common
    random numbers must remain identical.
    """

    payload = dict(receipt) if isinstance(receipt, Mapping) else asdict(receipt)
    payload.pop("arm", None)
    payload.pop("proposal_support_sha256", None)
    return payload


def _reject_nonfinite(value: object, *, path: str = "result") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite numeric value at {path}")
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_nonfinite(child, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _reject_nonfinite(child, path=f"{path}[{index}]")


def run_stateful_full_joint_development(*, repository_root: Path) -> dict[str, Any]:
    """Run the first honest Route-C D0 closed-loop comparison.

    The matched factorized arm is the mechanism-identification control.  AMG is
    independently selected on validation episodes and reported as an external
    action comparator, not mislabelled as a same-state-access control.
    """

    config_path = repository_root / DEFAULT_CONFIG
    config_payload = json.loads(config_path.read_text(encoding="utf-8"))
    decision_path = repository_root / config_payload["decision_source"]
    config = load_stateful_full_joint_config(repository_root)
    evaluation = config_payload["development_evaluation"]
    validation_seeds = tuple(int(value) for value in evaluation["validation_seeds"])
    development_holdout_seeds = tuple(
        int(value) for value in evaluation["development_holdout_seeds"]
    )
    if set(validation_seeds) & set(development_holdout_seeds):
        raise ValueError("Route-C validation and development-holdout seeds must be disjoint")
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=validation_seeds,
        test_seeds=development_holdout_seeds,
        max_steps_per_episode=int(evaluation["max_steps_per_episode"]),
        dataset_version=f"{PROTOCOL_ID}:d0-closed-loop",
        scenario_duration_days=int(evaluation["scenario_duration_days"]),
        guest_window=tuple(evaluation["guest_window"]),
        abrupt_day=int(evaluation["abrupt_day"]),
        recurrence_day=int(evaluation["recurrence_day"]),
        unknown_event_days=tuple(evaluation["unknown_event_days"]),
        sealed_secret=f"{PROTOCOL_ID}:registered-d0-development",
    ).build()
    dataset_quality = audit_project_two_replay(dataset)
    dataset_coverage = summarize_project_two_evidence_coverage(dataset)
    if dataset_quality.failures:
        raise ValueError(f"Route-C D0 replay quality gate failed: {dataset_quality.failures}")
    evaluator = ProjectTwoActionBenchmarkV02()
    validation_episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
    amg_candidates: list[dict[str, Any]] = []
    registered_amg = {
        float(point["parameter"]) for point in PARAMETER_SPACE[ProjectTwoActionMethod.AMG_MATCHED]
    }
    if set(float(value) for value in evaluation["amg_parameter_space"]) != registered_amg:
        raise ValueError("Route-C AMG tuning space drifted from the registered benchmark")
    for parameter in evaluation["amg_parameter_space"]:
        metrics = [
            evaluator._evaluate_episode(
                dataset,
                episode,
                ProjectTwoActionMethod.AMG_MATCHED,
                {"parameter": float(parameter)},
            )
            for episode in validation_episodes
        ]
        amg_candidates.append(
            {
                "parameter": float(parameter),
                "validation_action_regret_per_step": sum(
                    metric.cumulative_action_regret for metric in metrics
                )
                / sum(metric.step_count for metric in metrics),
            }
        )
    amg_selection = min(
        amg_candidates,
        key=lambda row: (row["validation_action_regret_per_step"], row["parameter"]),
    )

    development_holdout_episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
    arm_metrics: dict[str, list[Any]] = {arm.value: [] for arm in FullJointArm}
    arm_runtimes: dict[str, list[StatefulFullJointRuntime]] = {
        arm.value: [] for arm in FullJointArm
    }
    wall_seconds: dict[str, list[float]] = {arm.value: [] for arm in FullJointArm}
    per_episode: list[dict[str, Any]] = []
    for episode in development_holdout_episodes:
        episode_row: dict[str, Any] = {"episode_id": str(episode.episode_id)}
        for arm in FullJointArm:
            started = time.perf_counter()
            metric, runtime = evaluate_stateful_full_joint_episode(
                repository_root=repository_root,
                dataset=dataset,
                episode=episode,
                arm=arm,
            )
            elapsed = time.perf_counter() - started
            arm_metrics[arm.value].append(metric)
            arm_runtimes[arm.value].append(runtime)
            wall_seconds[arm.value].append(elapsed)
            episode_row[arm.value] = metric.model_dump(mode="json")
        amg_metric = evaluator._evaluate_episode(
            dataset,
            episode,
            ProjectTwoActionMethod.AMG_MATCHED,
            {"parameter": amg_selection["parameter"]},
        )
        episode_row["independently_tuned_amg"] = amg_metric.model_dump(mode="json")
        per_episode.append(episode_row)

    joint_runtimes = arm_runtimes[FullJointArm.STATEFUL_FULL_JOINT.value]
    factorized_runtimes = arm_runtimes[FullJointArm.MATCHED_FULL_STATE_FACTORIZED.value]
    fairness_checks: list[bool] = []
    action_posterior_tvs: list[float] = []
    action_argmax_disagreements = 0
    paired_action_readouts: list[dict[str, Any]] = []
    for episode, joint_runtime, factorized_runtime in zip(
        development_holdout_episodes,
        joint_runtimes,
        factorized_runtimes,
        strict=True,
    ):
        if len(joint_runtime.fairness_receipts) != len(factorized_runtime.fairness_receipts):
            fairness_checks.append(False)
            continue
        fairness_checks.extend(
            _fairness_comparison_payload(joint_receipt)
            == _fairness_comparison_payload(factorized_receipt)
            for joint_receipt, factorized_receipt in zip(
                joint_runtime.fairness_receipts,
                factorized_runtime.fairness_receipts,
                strict=True,
            )
        )
        if len(joint_runtime.action_readout_traces) != len(
            factorized_runtime.action_readout_traces
        ):
            raise ValueError("matched Route-C arms emitted different action trace counts")
        for trace_index, (joint_distribution, factorized_distribution) in enumerate(
            zip(
                joint_runtime.action_readout_traces,
                factorized_runtime.action_readout_traces,
                strict=True,
            )
        ):
            locations = set(joint_distribution) | set(factorized_distribution)
            tv = 0.5 * sum(
                abs(
                    joint_distribution.get(location, 0.0)
                    - factorized_distribution.get(location, 0.0)
                )
                for location in locations
            )
            action_posterior_tvs.append(tv)
            joint_action = max(
                joint_distribution,
                key=lambda key: (joint_distribution[key], str(key)),
            )
            factorized_action = max(
                factorized_distribution,
                key=lambda key: (factorized_distribution[key], str(key)),
            )
            disagreed = joint_action != factorized_action
            action_argmax_disagreements += int(disagreed)
            paired_action_readouts.append(
                {
                    "episode_id": str(episode.episode_id),
                    "trace_index": trace_index,
                    "joint_distribution": {
                        str(location): joint_distribution[location]
                        for location in sorted(joint_distribution)
                    },
                    "factorized_distribution": {
                        str(location): factorized_distribution[location]
                        for location in sorted(factorized_distribution)
                    },
                    "total_variation": tv,
                    "joint_argmax": str(joint_action),
                    "factorized_argmax": str(factorized_action),
                    "selected_action_disagreed": disagreed,
                }
            )
    operator_ids = set(StructureTwoOperator)
    receipt_coverage = {
        arm: sorted(
            {
                receipt.operator.value
                for runtime in runtimes
                for receipt in runtime.operator_flow_receipts
            }
        )
        for arm, runtimes in arm_runtimes.items()
    }
    execution_coverage = {
        arm: sorted(
            {
                receipt.operator.value
                for runtime in runtimes
                for receipt in runtime.operator_flow_receipts
                if receipt.executed
            }
        )
        for arm, runtimes in arm_runtimes.items()
    }
    operator_effect_evidence = {
        arm: {
            operator.value: {
                "receipt_count": sum(
                    receipt.operator is operator
                    for runtime in runtimes
                    for receipt in runtime.operator_flow_receipts
                ),
                "executed_count": sum(
                    receipt.operator is operator and receipt.executed
                    for runtime in runtimes
                    for receipt in runtime.operator_flow_receipts
                ),
                "changed_state_count": sum(
                    receipt.operator is operator and receipt.changed_state
                    for runtime in runtimes
                    for receipt in runtime.operator_flow_receipts
                ),
            }
            for operator in StructureTwoOperator
        }
        for arm, runtimes in arm_runtimes.items()
    }
    rgrc_long_term_admission_observed = {
        arm: any(
            record.operation in {"promote", "corrected_revision"}
            for runtime in runtimes
            for record in runtime.rgrc_ledger.records
        )
        for arm, runtimes in arm_runtimes.items()
    }
    summaries = {arm: _metric_summary(metrics) for arm, metrics in arm_metrics.items()}
    amg_metrics = [row["independently_tuned_amg"] for row in per_episode]
    amg_summary = _metric_summary_from_rows(amg_metrics)
    joint_summary = summaries[FullJointArm.STATEFUL_FULL_JOINT.value]
    factorized_summary = summaries[FullJointArm.MATCHED_FULL_STATE_FACTORIZED.value]
    runtime_audits = {
        arm: [
            _runtime_audit_payload(runtime, episode_id=episode.episode_id)
            for episode, runtime in zip(development_holdout_episodes, runtimes, strict=True)
        ]
        for arm, runtimes in arm_runtimes.items()
    }
    result: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID,
        "selected_route": "C_stateful_joint_inference",
        "evidence_status": "D0_DEVELOPMENT_ONLY",
        "route_c_replay_feedback_loop_executable": True,
        "feedback_loop_semantics": {
            "mode": "FROZEN_REPLAY_ACTION_BOUND_REVISION_LOOP",
            "final_route_action_bound_to_revision_trace": True,
            "corrected_joint_state_consumed_by_later_actions": True,
            "environment_trajectory_responds_to_route_action": False,
        },
        "implementation_complete_for_paper": False,
        "complete_state_axes": list(COMPLETE_STATE_AXES),
        "rao_blackwellized_blocks": list(RB_BLOCKS),
        "dataset_quality": {
            "quality_report": dataset_quality.model_dump(mode="json"),
            "coverage_report": dataset_coverage.model_dump(mode="json"),
            "dataset_content_sha256": content_sha256(dataset.model_dump(mode="json")),
            "external_claim_ready": False,
            "limitation": D0_LIMITATION,
        },
        "source_binding": {
            "config": {
                "path": str(DEFAULT_CONFIG),
                "sha256": _file_sha256(config_path),
            },
            "route_decision": {
                "path": str(config_payload["decision_source"]),
                "sha256": _file_sha256(decision_path),
            },
            "implementation": {
                "path": str(Path(__file__).resolve().relative_to(repository_root)),
                "sha256": _file_sha256(Path(__file__).resolve()),
            },
            "neural_proposal_artifact": {
                "path": str(config.neural_proposal_model_path.relative_to(repository_root)),
                "sha256": _file_sha256(config.neural_proposal_model_path),
            },
        },
        "neural_proposal_model_hash": load_neural_proposal_model(
            config.neural_proposal_model_path
        ).model_hash,
        "validation_seed_count": len(validation_seeds),
        "development_holdout_seed_count": len(development_holdout_seeds),
        "amg_validation_selection": {
            "candidates": amg_candidates,
            "selected": amg_selection,
            "development_holdout_seen_during_selection": False,
        },
        "matched_full_state_fairness_passed": bool(fairness_checks) and all(fairness_checks),
        "runtime_audit_traces": runtime_audits,
        "paired_action_readouts": paired_action_readouts,
        "operator_receipt_coverage": receipt_coverage,
        "operator_execution_coverage": execution_coverage,
        "operator_effect_evidence": operator_effect_evidence,
        "all_seven_operators_receipted": all(
            set(values) == {operator.value for operator in operator_ids}
            for values in receipt_coverage.values()
        ),
        "all_seven_operators_executed_somewhere": all(
            set(values) == {operator.value for operator in operator_ids}
            for values in execution_coverage.values()
        ),
        "rgrc_long_term_admission_observed": rgrc_long_term_admission_observed,
        "all_seven_operator_contributions_established": False,
        "summaries": {**summaries, "independently_tuned_amg": amg_summary},
        "paired_mean_differences_lower_is_better": {
            "joint_minus_matched_factorized_action_regret_per_step": (
                joint_summary["cumulative_action_regret_per_step"]
                - factorized_summary["cumulative_action_regret_per_step"]
            ),
            "joint_minus_amg_action_regret_per_step": (
                joint_summary["cumulative_action_regret_per_step"]
                - amg_summary["cumulative_action_regret_per_step"]
            ),
            "joint_minus_matched_factorized_contamination": (
                joint_summary["owner_habit_contamination"]
                - factorized_summary["owner_habit_contamination"]
            ),
            "joint_minus_amg_contamination": (
                joint_summary["owner_habit_contamination"]
                - amg_summary["owner_habit_contamination"]
            ),
        },
        "joint_causal_utilization_diagnostic": {
            "action_posterior_step_count": len(action_posterior_tvs),
            "mean_action_posterior_tv": mean(action_posterior_tvs),
            "max_action_posterior_tv": max(action_posterior_tvs),
            "positive_action_posterior_tv_steps": sum(
                value > 1e-12 for value in action_posterior_tvs
            ),
            "selected_action_disagreement_steps": action_argmax_disagreements,
            "interpretation": (
                "cross-axis potentials reach the action distribution; discrete action utility "
                "may still tie when rankings do not change"
            ),
        },
        "wall_clock_seconds": {
            arm: {
                "mean": mean(values),
                "min": min(values),
                "max": max(values),
            }
            for arm, values in wall_seconds.items()
        },
        "latency_evidence_status": LATENCY_EVIDENCE_STATUS,
        "per_episode": per_episode,
        "positive_output_trust_chain": {
            "/complete_state_axes": (
                "config_contract+runtime_world_validation+fresh_source_replay"
            ),
            "/rao_blackwellized_blocks": (
                "rb_cell_validation+decision_readout_tests+fresh_source_replay"
            ),
            "/dataset_quality/quality_report/ready": (
                "dataset_audit_report+dataset_content_hash+fresh_source_replay"
            ),
            "/route_c_replay_feedback_loop_executable": (
                "runtime_audit_traces+fresh_source_replay"
            ),
            "/feedback_loop_semantics/final_route_action_bound_to_revision_trace": (
                "paired_action_distributions+revision_receipt_hash_chains+fresh_source_replay"
            ),
            "/feedback_loop_semantics/corrected_joint_state_consumed_by_later_actions": (
                "revision_lineage+later_action_traces+fresh_source_replay"
            ),
            "/matched_full_state_fairness_passed": (
                "paired_fairness_receipts+complete_support_schema+content_provenance+"
                "fresh_source_replay"
            ),
            "/all_seven_operators_receipted": ("operator_receipt_hash_chains+fresh_source_replay"),
            "/all_seven_operators_executed_somewhere": (
                "executed_operator_receipts+fresh_source_replay"
            ),
            "/joint_causal_utilization_diagnostic/positive_action_posterior_tv_steps": (
                "paired_action_distributions+deterministic_recomputation+fresh_source_replay"
            ),
        },
        "independent_custody_established": False,
        "historical_authenticity_established": False,
        "scientific_superiority_established": False,
        "task_8_formal_passed": False,
        "seven_operator_ablation_authorized": False,
        "next_gate": NEXT_GATE,
    }
    result["deterministic_replay_sha256"] = content_sha256(_deterministic_result_payload(result))
    result["content_sha256"] = content_sha256(result)
    return result


def _verify_report_calculations(result: Mapping[str, Any]) -> None:
    rows = result.get("per_episode")
    if not isinstance(rows, Sequence) or not rows:
        raise ValueError("Route-C per-episode evidence is missing")
    arm_names = (
        FullJointArm.STATEFUL_FULL_JOINT.value,
        FullJointArm.MATCHED_FULL_STATE_FACTORIZED.value,
        "independently_tuned_amg",
    )
    recomputed: dict[str, dict[str, float]] = {}
    for arm in arm_names:
        arm_rows = []
        for row in rows:
            if not isinstance(row, Mapping) or not isinstance(row.get(arm), Mapping):
                raise ValueError(f"Route-C per-episode row omitted {arm}")
            arm_rows.append(row[arm])
        recomputed[arm] = _metric_summary_from_rows(arm_rows)
    if content_sha256(recomputed) != content_sha256(result.get("summaries")):
        raise ValueError("Route-C aggregate summaries disagree with per-episode rows")
    joint = recomputed[FullJointArm.STATEFUL_FULL_JOINT.value]
    factorized = recomputed[FullJointArm.MATCHED_FULL_STATE_FACTORIZED.value]
    amg = recomputed["independently_tuned_amg"]
    differences = {
        "joint_minus_matched_factorized_action_regret_per_step": (
            joint["cumulative_action_regret_per_step"]
            - factorized["cumulative_action_regret_per_step"]
        ),
        "joint_minus_amg_action_regret_per_step": (
            joint["cumulative_action_regret_per_step"] - amg["cumulative_action_regret_per_step"]
        ),
        "joint_minus_matched_factorized_contamination": (
            joint["owner_habit_contamination"] - factorized["owner_habit_contamination"]
        ),
        "joint_minus_amg_contamination": (
            joint["owner_habit_contamination"] - amg["owner_habit_contamination"]
        ),
    }
    if content_sha256(differences) != content_sha256(
        result.get("paired_mean_differences_lower_is_better")
    ):
        raise ValueError("Route-C paired differences disagree with aggregate summaries")


def _verify_operator_receipt_rows(rows: Sequence[Mapping[str, Any]], expected_head: str) -> None:
    previous = "GENESIS"
    for row in rows:
        if row.get("previous_receipt_sha256") != previous:
            raise ValueError("embedded operator receipt chain is broken")
        payload = {
            "step_index": row.get("step_index"),
            "operator": row.get("operator"),
            "executed": row.get("executed"),
            "changed_state": row.get("changed_state"),
            "input_state_sha256": row.get("input_state_sha256"),
            "output_state_sha256": row.get("output_state_sha256"),
            "consumed_axes": row.get("consumed_axes"),
            "detail": row.get("detail"),
            "previous_receipt_sha256": row.get("previous_receipt_sha256"),
        }
        if row.get("receipt_sha256") != content_sha256(payload):
            raise ValueError("embedded operator receipt content hash mismatch")
        previous = str(row["receipt_sha256"])
    if previous != expected_head:
        raise ValueError("embedded operator receipt head mismatch")


def _verify_ledger_rows(
    rows: Sequence[Mapping[str, Any]], expected_head: str
) -> tuple[str | None, dict[str, float] | None]:
    previous = "GENESIS"
    active_source: str | None = None
    active_distribution: dict[str, float] | None = None
    quarantined_source: str | None = None
    for row in rows:
        distribution = row.get("action_distribution")
        if not isinstance(distribution, Mapping):
            raise ValueError("embedded RGRC distribution is missing")
        payload = {
            "operation": row.get("operation"),
            "source_revision_id": row.get("source_revision_id"),
            "particle_revision_id": row.get("particle_revision_id"),
            "owner_target_mass": row.get("owner_target_mass"),
            "action_distribution": sorted(distribution.items()),
            "previous_hash": row.get("previous_hash"),
        }
        if row.get("previous_hash") != previous:
            raise ValueError("embedded RGRC previous-hash chain is broken")
        if row.get("record_hash") != content_sha256(payload):
            raise ValueError("embedded RGRC record hash mismatch")
        operation = row.get("operation")
        source = row.get("source_revision_id")
        if not isinstance(source, str):
            raise ValueError("embedded RGRC source identity is malformed")
        if operation == "quarantine":
            quarantined_source = source
        elif operation == "promote":
            if active_source is not None or quarantined_source != source:
                raise ValueError("embedded RGRC promote is unreachable")
            active_source = source
            active_distribution = {str(key): float(value) for key, value in distribution.items()}
        elif operation == "retract":
            if active_source != source:
                raise ValueError("embedded RGRC retract missed the active source")
            active_source = None
            active_distribution = None
        elif operation == "corrected_revision":
            if active_source is not None or quarantined_source != source:
                raise ValueError("embedded RGRC correction is unreachable")
            active_source = source
            active_distribution = {str(key): float(value) for key, value in distribution.items()}
        else:
            raise ValueError("embedded RGRC operation is unknown")
        previous = str(row["record_hash"])
    if previous != expected_head:
        raise ValueError("embedded RGRC ledger head mismatch")
    return active_source, active_distribution


def _verify_embedded_runtime_evidence(result: Mapping[str, Any]) -> None:
    audits = result.get("runtime_audit_traces")
    if not isinstance(audits, Mapping) or set(audits) != {arm.value for arm in FullJointArm}:
        raise ValueError("Route-C runtime audit traces are incomplete")
    expected_operators = {operator.value for operator in StructureTwoOperator}
    paired_rows = result.get("paired_action_readouts")
    if not isinstance(paired_rows, Sequence):
        raise ValueError("Route-C paired action evidence is missing")
    paired_by_episode: dict[str, list[Mapping[str, Any]]] = {}
    for row in paired_rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("episode_id"), str):
            raise ValueError("Route-C paired action evidence is malformed")
        paired_by_episode.setdefault(str(row["episode_id"]), []).append(row)
    per_episode = result.get("per_episode")
    if not isinstance(per_episode, Sequence):
        raise ValueError("Route-C per-episode evidence is missing")
    expected_episode_ids = {
        str(row.get("episode_id")) for row in per_episode if isinstance(row, Mapping)
    }
    if set(paired_by_episode) != expected_episode_ids:
        raise ValueError("Route-C paired action episodes disagree with scored episodes")
    receipt_coverage: dict[str, list[str]] = {}
    execution_coverage: dict[str, list[str]] = {}
    operator_effect_evidence: dict[str, dict[str, dict[str, int]]] = {}
    rgrc_long_term_admission_observed: dict[str, bool] = {}
    for arm in FullJointArm:
        arm_rows = audits.get(arm.value)
        if not isinstance(arm_rows, Sequence) or not arm_rows:
            raise ValueError(f"Route-C runtime audit traces omitted {arm.value}")
        if {str(row.get("episode_id")) for row in arm_rows if isinstance(row, Mapping)} != (
            expected_episode_ids
        ):
            raise ValueError("Route-C runtime episodes disagree with scored episodes")
        seen: set[str] = set()
        executed: set[str] = set()
        for runtime_row in arm_rows:
            if not isinstance(runtime_row, Mapping) or runtime_row.get("arm") != arm.value:
                raise ValueError("Route-C runtime audit arm substitution")
            operator_rows = runtime_row.get("operator_flow_receipts")
            ledger_rows = runtime_row.get("rgrc_ledger_records")
            fairness_rows = runtime_row.get("fairness_receipts")
            if (
                not isinstance(operator_rows, Sequence)
                or not isinstance(ledger_rows, Sequence)
                or not isinstance(fairness_rows, Sequence)
                or not all(isinstance(value, Mapping) for value in operator_rows)
                or not all(isinstance(value, Mapping) for value in ledger_rows)
                or not all(isinstance(value, Mapping) for value in fairness_rows)
            ):
                raise ValueError("Route-C embedded runtime receipt set is malformed")
            _verify_operator_receipt_rows(
                operator_rows,
                str(runtime_row.get("operator_receipt_head_sha256")),
            )
            active_source, active_distribution = _verify_ledger_rows(
                ledger_rows,
                str(runtime_row.get("rgrc_ledger_head_sha256")),
            )
            if (
                runtime_row.get("rgrc_active_source_revision_id") != active_source
                or runtime_row.get("rgrc_active_distribution") != active_distribution
            ):
                raise ValueError("Route-C embedded RGRC terminal state is not ledger-derived")
            previous_operator_step = 0
            for receipt in operator_rows:
                step_index = receipt.get("step_index")
                if (
                    receipt.get("changed_state") is True and receipt.get("executed") is not True
                ) or (
                    not isinstance(step_index, int)
                    or step_index < previous_operator_step
                    or not set(receipt.get("consumed_axes", ())).issubset(COMPLETE_STATE_AXES)
                ):
                    raise ValueError("Route-C embedded operator state transition is invalid")
                previous_operator_step = step_index
                seen.add(str(receipt.get("operator")))
                if receipt.get("executed") is True:
                    executed.add(str(receipt.get("operator")))
            for expected_step, receipt in enumerate(fairness_rows, start=1):
                score_evaluations = receipt.get("target_score_evaluations")
                score_operations_per_candidate = receipt.get("score_operations_per_candidate")
                if (
                    not isinstance(score_evaluations, int)
                    or not isinstance(score_operations_per_candidate, int)
                    or receipt.get("arm") != arm.value
                    or tuple(receipt.get("complete_state_axes", ())) != COMPLETE_STATE_AXES
                    or receipt.get("proposal_support_policy") != "enumerate_all_positive_support"
                    or not isinstance(receipt.get("proposal_support_schema_sha256"), str)
                    or len(receipt.get("proposal_support_schema_sha256", "")) != 64
                    or not isinstance(receipt.get("proposal_support_sha256"), str)
                    or len(receipt.get("proposal_support_sha256", "")) != 64
                    or score_evaluations != receipt.get("particle_budget")
                    or receipt.get("proposal_draws") != receipt.get("particle_budget")
                    or receipt.get("step_index") != expected_step
                    or receipt.get("proposal_support_size", 0) < score_evaluations
                    or receipt.get("parent_count") not in {1, receipt.get("particle_budget")}
                    or receipt.get("score_operations")
                    != score_evaluations * score_operations_per_candidate
                ):
                    raise ValueError("Route-C embedded fairness receipt is invalid")
            importance_hashes = runtime_row.get("importance_revision_batch_sha256")
            normalized_hashes = runtime_row.get("normalized_revision_batch_sha256")
            if (
                not isinstance(importance_hashes, Sequence)
                or not isinstance(normalized_hashes, Sequence)
                or len(importance_hashes) != len(fairness_rows)
                or len(normalized_hashes) != len(fairness_rows)
                or any(
                    not isinstance(value, str) or len(value) != 64 for value in importance_hashes
                )
                or any(
                    not isinstance(value, str) or len(value) != 64 for value in normalized_hashes
                )
            ):
                raise ValueError("Route-C embedded revision-batch evidence is malformed")
            episode_id = str(runtime_row.get("episode_id"))
            arm_distribution_key = (
                "joint_distribution"
                if arm is FullJointArm.STATEFUL_FULL_JOINT
                else "factorized_distribution"
            )
            episode_action_rows = sorted(
                paired_by_episode[episode_id], key=lambda row: int(row.get("trace_index", -1))
            )
            if [row.get("trace_index") for row in episode_action_rows] != list(
                range(len(episode_action_rows))
            ):
                raise ValueError("Route-C paired action trace indices are not contiguous")
            action_traces = [row.get(arm_distribution_key) for row in episode_action_rows]
            if runtime_row.get("action_readout_trace_count") != len(
                action_traces
            ) or runtime_row.get("action_readout_trace_sha256") != content_sha256(action_traces):
                raise ValueError("Route-C paired actions are not bound to runtime traces")
        receipt_coverage[arm.value] = sorted(seen)
        execution_coverage[arm.value] = sorted(executed)
        operator_effect_evidence[arm.value] = {
            operator.value: {
                "receipt_count": sum(
                    receipt.get("operator") == operator.value
                    for runtime_row in arm_rows
                    for receipt in runtime_row["operator_flow_receipts"]
                ),
                "executed_count": sum(
                    receipt.get("operator") == operator.value and receipt.get("executed") is True
                    for runtime_row in arm_rows
                    for receipt in runtime_row["operator_flow_receipts"]
                ),
                "changed_state_count": sum(
                    receipt.get("operator") == operator.value
                    and receipt.get("changed_state") is True
                    for runtime_row in arm_rows
                    for receipt in runtime_row["operator_flow_receipts"]
                ),
            }
            for operator in StructureTwoOperator
        }
        rgrc_long_term_admission_observed[arm.value] = any(
            record.get("operation") in {"promote", "corrected_revision"}
            for runtime_row in arm_rows
            for record in runtime_row["rgrc_ledger_records"]
        )
    if result.get("operator_receipt_coverage") != receipt_coverage:
        raise ValueError("Route-C operator receipt coverage is not derived from raw receipts")
    if result.get("operator_execution_coverage") != execution_coverage:
        raise ValueError("Route-C operator execution coverage is not derived from raw receipts")
    if result.get("operator_effect_evidence") != operator_effect_evidence:
        raise ValueError("Route-C operator effect counts are not derived from raw receipts")
    if result.get("rgrc_long_term_admission_observed") != rgrc_long_term_admission_observed:
        raise ValueError("Route-C RGRC admission claim is not ledger-derived")
    if result.get("all_seven_operators_receipted") is not all(
        set(values) == expected_operators for values in receipt_coverage.values()
    ):
        raise ValueError("Route-C all-operator receipt claim is not evidence-derived")
    if result.get("all_seven_operators_executed_somewhere") is not all(
        set(values) == expected_operators for values in execution_coverage.values()
    ):
        raise ValueError("Route-C all-operator execution claim is not evidence-derived")

    left = audits[FullJointArm.STATEFUL_FULL_JOINT.value]
    right = audits[FullJointArm.MATCHED_FULL_STATE_FACTORIZED.value]
    fairness_passed = len(left) == len(right)
    for left_runtime, right_runtime in zip(left, right, strict=True):
        left_receipts = left_runtime["fairness_receipts"]
        right_receipts = right_runtime["fairness_receipts"]
        fairness_passed = fairness_passed and len(left_receipts) == len(right_receipts)
        for left_receipt, right_receipt in zip(
            left_receipts,
            right_receipts,
            strict=True,
        ):
            fairness_passed = fairness_passed and (
                _fairness_comparison_payload(left_receipt)
                == _fairness_comparison_payload(right_receipt)
            )
    if result.get("matched_full_state_fairness_passed") is not fairness_passed:
        raise ValueError("Route-C fairness claim is not derived from paired receipts")


def _verify_paired_action_readouts(result: Mapping[str, Any]) -> None:
    rows = result.get("paired_action_readouts")
    if not isinstance(rows, Sequence) or not rows:
        raise ValueError("Route-C paired action distributions are missing")
    televisions: list[float] = []
    disagreements = 0
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("Route-C paired action row is malformed")
        joint = row.get("joint_distribution")
        factorized = row.get("factorized_distribution")
        if not isinstance(joint, Mapping) or not isinstance(factorized, Mapping):
            raise ValueError("Route-C paired action distribution is malformed")
        if set(joint) != set(factorized):
            raise ValueError("Route-C paired action support differs across arms")
        for distribution in (joint, factorized):
            if (
                any(
                    not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or not 0.0 <= float(value) <= 1.0
                    for value in distribution.values()
                )
                or abs(sum(float(value) for value in distribution.values()) - 1.0) > 1e-6
            ):
                raise ValueError("Route-C paired action distribution is not normalized")
        tv = 0.5 * sum(abs(float(joint[key]) - float(factorized[key])) for key in joint)
        joint_argmax = max(joint, key=lambda key: (joint[key], str(key)))
        factorized_argmax = max(
            factorized,
            key=lambda key: (factorized[key], str(key)),
        )
        disagreed = bool(joint_argmax != factorized_argmax)
        if (
            abs(float(row.get("total_variation", -1.0)) - tv) > 1e-12
            or row.get("joint_argmax") != joint_argmax
            or row.get("factorized_argmax") != factorized_argmax
            or row.get("selected_action_disagreed") is not disagreed
        ):
            raise ValueError("Route-C paired action diagnostic was not recomputed correctly")
        televisions.append(tv)
        disagreements += int(disagreed)
    expected = {
        "action_posterior_step_count": len(televisions),
        "mean_action_posterior_tv": mean(televisions),
        "max_action_posterior_tv": max(televisions),
        "positive_action_posterior_tv_steps": sum(value > 1e-12 for value in televisions),
        "selected_action_disagreement_steps": disagreements,
        "interpretation": (
            "cross-axis potentials reach the action distribution; discrete action utility "
            "may still tie when rankings do not change"
        ),
    }
    if content_sha256(expected) != content_sha256(
        result.get("joint_causal_utilization_diagnostic")
    ):
        raise ValueError("Route-C causal-utilization claim is not distribution-derived")


def verify_stateful_full_joint_result(
    result: Mapping[str, Any],
    *,
    repository_root: Path | None = None,
    fresh_replay: bool = False,
) -> None:
    expected_fields = {
        "protocol_id",
        "selected_route",
        "evidence_status",
        "route_c_replay_feedback_loop_executable",
        "feedback_loop_semantics",
        "implementation_complete_for_paper",
        "complete_state_axes",
        "rao_blackwellized_blocks",
        "dataset_quality",
        "source_binding",
        "neural_proposal_model_hash",
        "validation_seed_count",
        "development_holdout_seed_count",
        "amg_validation_selection",
        "matched_full_state_fairness_passed",
        "runtime_audit_traces",
        "paired_action_readouts",
        "operator_receipt_coverage",
        "operator_execution_coverage",
        "operator_effect_evidence",
        "all_seven_operators_receipted",
        "all_seven_operators_executed_somewhere",
        "rgrc_long_term_admission_observed",
        "all_seven_operator_contributions_established",
        "summaries",
        "paired_mean_differences_lower_is_better",
        "joint_causal_utilization_diagnostic",
        "wall_clock_seconds",
        "latency_evidence_status",
        "per_episode",
        "positive_output_trust_chain",
        "independent_custody_established",
        "historical_authenticity_established",
        "scientific_superiority_established",
        "task_8_formal_passed",
        "seven_operator_ablation_authorized",
        "next_gate",
        "deterministic_replay_sha256",
        "content_sha256",
    }
    if set(result) != expected_fields:
        raise ValueError("stateful full-joint result schema drift or extra claim field")
    _reject_nonfinite(result)
    unsigned = dict(result)
    claimed_hash = unsigned.pop("content_sha256", None)
    if claimed_hash != content_sha256(unsigned):
        raise ValueError("stateful full-joint result content hash mismatch")
    if result.get("protocol_id") != PROTOCOL_ID:
        raise ValueError("stateful full-joint result protocol mismatch")
    if result.get("selected_route") != "C_stateful_joint_inference":
        raise ValueError("stateful full-joint result is not Route C")
    if result.get("evidence_status") != "D0_DEVELOPMENT_ONLY":
        raise ValueError("stateful full-joint evidence status was promoted")
    if result.get("route_c_replay_feedback_loop_executable") is not True:
        raise ValueError("Route-C replay feedback-loop execution is not established")
    expected_feedback_semantics = {
        "mode": "FROZEN_REPLAY_ACTION_BOUND_REVISION_LOOP",
        "final_route_action_bound_to_revision_trace": True,
        "corrected_joint_state_consumed_by_later_actions": True,
        "environment_trajectory_responds_to_route_action": False,
    }
    if result.get("feedback_loop_semantics") != expected_feedback_semantics:
        raise ValueError("Route-C replay feedback loop was misrepresented as interactive")
    if result.get("implementation_complete_for_paper") is not False:
        raise ValueError("Route-C D0 implementation cannot claim paper completeness")
    if tuple(result.get("complete_state_axes", ())) != COMPLETE_STATE_AXES:
        raise ValueError("stateful full-joint result omitted a complete-state axis")
    if tuple(result.get("rao_blackwellized_blocks", ())) != RB_BLOCKS:
        raise ValueError("stateful full-joint result omitted an RB block")
    source_binding = result.get("source_binding")
    if not isinstance(source_binding, Mapping) or set(source_binding) != {
        "config",
        "route_decision",
        "implementation",
        "neural_proposal_artifact",
    }:
        raise ValueError("stateful full-joint result source binding is incomplete")
    if repository_root is not None:
        config_path = repository_root / DEFAULT_CONFIG
        config_payload = json.loads(config_path.read_text(encoding="utf-8"))
        expected_paths = {
            "config": DEFAULT_CONFIG.as_posix(),
            "route_decision": str(config_payload["decision_source"]),
            "implementation": str(Path(__file__).resolve().relative_to(repository_root)),
            "neural_proposal_artifact": str(config_payload["neural_proposal_model"]),
        }
        for label, expected_path in expected_paths.items():
            binding = source_binding[label]
            if not isinstance(binding, Mapping):
                raise ValueError(f"invalid source binding for {label}")
            if binding.get("path") != expected_path:
                raise ValueError(f"stateful full-joint source path substitution for {label}")
            path = repository_root / expected_path
            if not path.is_file() or binding.get("sha256") != _file_sha256(path):
                raise ValueError(f"stateful full-joint source binding mismatch for {label}")
        config = load_stateful_full_joint_config(repository_root)
        if (
            result.get("neural_proposal_model_hash")
            != load_neural_proposal_model(config.neural_proposal_model_path).model_hash
        ):
            raise ValueError("stateful full-joint neural model identity mismatch")
        evaluation = config_payload["development_evaluation"]
        if result.get("validation_seed_count") != len(evaluation["validation_seeds"]) or result.get(
            "development_holdout_seed_count"
        ) != len(evaluation["development_holdout_seeds"]):
            raise ValueError("stateful full-joint split-count binding mismatch")
    dataset_quality = result.get("dataset_quality")
    if not isinstance(dataset_quality, Mapping):
        raise ValueError("Route-C dataset-quality evidence is missing")
    quality_report = dataset_quality.get("quality_report")
    coverage_report = dataset_quality.get("coverage_report")
    if (
        not isinstance(quality_report, Mapping)
        or not isinstance(coverage_report, Mapping)
        or quality_report.get("ready") is not True
        or quality_report.get("failures") != []
        or dataset_quality.get("external_claim_ready") is not False
        or dataset_quality.get("limitation") != D0_LIMITATION
    ):
        raise ValueError("Route-C D0 dataset-quality claim is malformed or over-promoted")
    selection = result.get("amg_validation_selection")
    if (
        not isinstance(selection, Mapping)
        or selection.get("development_holdout_seen_during_selection") is not False
    ):
        raise ValueError("Route-C AMG selection leaked the development holdout")
    candidates = selection.get("candidates")
    selected = selection.get("selected")
    if (
        not isinstance(candidates, Sequence)
        or not candidates
        or not isinstance(selected, Mapping)
        or any(
            not isinstance(row, Mapping)
            or set(row) != {"parameter", "validation_action_regret_per_step"}
            or not all(
                isinstance(row.get(key), (int, float)) and math.isfinite(float(row[key]))
                for key in ("parameter", "validation_action_regret_per_step")
            )
            for row in candidates
        )
    ):
        raise ValueError("Route-C AMG validation selection evidence is malformed")
    expected_selected = min(
        candidates,
        key=lambda row: (
            float(row["validation_action_regret_per_step"]),
            float(row["parameter"]),
        ),
    )
    if dict(selected) != dict(expected_selected):
        raise ValueError("Route-C AMG selected row is not the validation minimum")
    _verify_report_calculations(result)
    _verify_embedded_runtime_evidence(result)
    _verify_paired_action_readouts(result)
    if not result.get("matched_full_state_fairness_passed"):
        raise ValueError("matched full-state fairness did not pass")
    if not result.get("all_seven_operators_receipted"):
        raise ValueError("seven-operator receipt coverage is incomplete")
    if not result.get("all_seven_operators_executed_somewhere"):
        raise ValueError("seven-operator execution coverage is incomplete")
    causal = result.get("joint_causal_utilization_diagnostic", {})
    if causal.get("positive_action_posterior_tv_steps", 0) <= 0:
        raise ValueError("joint interaction never reached the action posterior")
    expected_trust = {
        "/complete_state_axes": ("config_contract+runtime_world_validation+fresh_source_replay"),
        "/rao_blackwellized_blocks": (
            "rb_cell_validation+decision_readout_tests+fresh_source_replay"
        ),
        "/dataset_quality/quality_report/ready": (
            "dataset_audit_report+dataset_content_hash+fresh_source_replay"
        ),
        "/route_c_replay_feedback_loop_executable": ("runtime_audit_traces+fresh_source_replay"),
        "/feedback_loop_semantics/final_route_action_bound_to_revision_trace": (
            "paired_action_distributions+revision_receipt_hash_chains+fresh_source_replay"
        ),
        "/feedback_loop_semantics/corrected_joint_state_consumed_by_later_actions": (
            "revision_lineage+later_action_traces+fresh_source_replay"
        ),
        "/matched_full_state_fairness_passed": (
            "paired_fairness_receipts+complete_support_schema+content_provenance+"
            "fresh_source_replay"
        ),
        "/all_seven_operators_receipted": ("operator_receipt_hash_chains+fresh_source_replay"),
        "/all_seven_operators_executed_somewhere": (
            "executed_operator_receipts+fresh_source_replay"
        ),
        "/joint_causal_utilization_diagnostic/positive_action_posterior_tv_steps": (
            "paired_action_distributions+deterministic_recomputation+fresh_source_replay"
        ),
    }
    if result.get("positive_output_trust_chain") != expected_trust:
        raise ValueError("Route-C positive-output trust chain is incomplete")
    wall_clock = result.get("wall_clock_seconds")
    if not isinstance(wall_clock, Mapping) or set(wall_clock) != {
        arm.value for arm in FullJointArm
    }:
        raise ValueError("Route-C local wall-clock evidence is malformed")
    for row in wall_clock.values():
        if (
            not isinstance(row, Mapping)
            or set(row) != {"mean", "min", "max"}
            or any(
                not isinstance(row.get(key), (int, float))
                or not math.isfinite(float(row[key]))
                or float(row[key]) < 0.0
                for key in ("mean", "min", "max")
            )
            or not float(row["min"]) <= float(row["mean"]) <= float(row["max"])
        ):
            raise ValueError("Route-C local wall-clock summary is invalid")
    if result.get("latency_evidence_status") != LATENCY_EVIDENCE_STATUS:
        raise ValueError("Route-C local wall clock was promoted into controlled latency evidence")
    if result.get("independent_custody_established") is not False:
        raise ValueError("Route-C local hashes cannot establish independent custody")
    if result.get("historical_authenticity_established") is not False:
        raise ValueError("Route-C local hashes cannot establish historical authenticity")
    if result.get("scientific_superiority_established") is not False:
        raise ValueError("D0 Route-C development result cannot claim scientific superiority")
    if result.get("task_8_formal_passed") is not False:
        raise ValueError("Route-C development result cannot pass formal Task 8")
    if result.get("seven_operator_ablation_authorized") is not False:
        raise ValueError("Route-C development result cannot authorize seven-operator ablation")
    if result.get("all_seven_operator_contributions_established") is not False:
        raise ValueError("Route-C execution receipts cannot establish all operator contributions")
    if result.get("next_gate") != NEXT_GATE:
        raise ValueError("Route-C next scientific gate was weakened")
    deterministic_hash = content_sha256(_deterministic_result_payload(result))
    if result.get("deterministic_replay_sha256") != deterministic_hash:
        raise ValueError("Route-C deterministic replay digest mismatch")
    if fresh_replay:
        if repository_root is None:
            raise ValueError("fresh Route-C replay requires the repository root")
        replayed = run_stateful_full_joint_development(repository_root=repository_root)
        if replayed.get("deterministic_replay_sha256") != result.get(
            "deterministic_replay_sha256"
        ) or content_sha256(_deterministic_result_payload(replayed)) != content_sha256(
            _deterministic_result_payload(result)
        ):
            raise ValueError("Route-C fresh-source replay disagrees with the stored result")


__all__ = [
    "COMPLETE_STATE_AXES",
    "DEFAULT_CONFIG",
    "PROTOCOL_ID",
    "ComputeFairnessReceipt",
    "FullJointArm",
    "FullJointObservation",
    "FullJointWorldState",
    "OperatorFlowReceipt",
    "RBCellState",
    "StatefulFullJointActionState",
    "StatefulFullJointConfig",
    "StatefulFullJointRuntime",
    "StatefulJointParticle",
    "build_stateful_full_joint_state",
    "evaluate_stateful_full_joint_episode",
    "load_neural_proposal_model",
    "load_stateful_full_joint_config",
    "observation_from_runtime",
    "run_stateful_full_joint_development",
    "verify_stateful_full_joint_result",
]
