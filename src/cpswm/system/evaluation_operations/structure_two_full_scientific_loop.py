"""Route-C v0.2: learned interactions inside an action-responsive full loop.

The module keeps the seven-axis particle state, all three Rao-Blackwellized
blocks, and all seven Structure-Two operators.  It adds four development
capabilities without promoting them to paper evidence:

* a deterministic action-responsive environment with potential-outcome pairing;
* cross-axis potentials trained on train seeds, selected on validation seeds,
  frozen before development-holdout evaluation;
* explicit RGRC promote/reject/retract activation cases; and
* one-operator-at-a-time neutralization while the complete framework remains live.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean
from typing import Any, Final
from uuid import UUID

from cpswm.contracts import EventMechanism
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleChangeCause,
    ParticleRegimeDecision,
    StructureTwoOperator,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    COMPLETE_STATE_AXES,
    RB_BLOCKS,
    FullJointArm,
    FullJointCandidate,
    FullJointObservation,
    ReversibleJointRGRCLedger,
    StatefulFullJointRuntime,
    StatefulJointParticle,
    _normalize,
    _verify_ledger_rows,
    _verify_operator_receipt_rows,
    load_neural_proposal_model,
    load_stateful_full_joint_config,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    DEFAULT_CONFIG as BASE_ROUTE_CONFIG,
)
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_production_system import (
    PRODUCTION_FEEDBACK_EDGE,
    PRODUCTION_OPERATOR_ORDER,
    PRODUCTION_SYSTEM_VERSION,
    build_production_assembly_manifest,
    verify_production_assembly_manifest,
)

PROTOCOL_ID: Final = "structure-two-full-scientific-loop@0.2-development"
DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_full_scientific_loop_v0_2.json"
)
INTERACTION_FEATURE_NAMES: Final = (
    "actor_cause_x_handoff",
    "identity_cause_x_instance_mismatch",
    "habit_cause_x_regime_change",
    "handoff_x_receiver_binding",
    "owner_x_target_x_habit",
    "unknown_actor_x_regime_change",
)
TRAINING_ACTION_POLICY: Final = "deterministic_coverage_cycle_without_truth"
TRAINING_EVIDENCE_FIELDS: Final = frozenset(
    {
        "training_action_policy",
        "seed_conditioned_observation_strength",
        "train_examples_sha256",
        "validation_examples_sha256",
        "train_validation_examples_distinct",
    }
)
CLAIM_BOUNDARY: Final = (
    "This development protocol establishes an action-responsive synthetic environment, "
    "a train-validation-frozen learned cross-axis potential, explicit RGRC positive and "
    "negative activation cases, a source-bound seven-production-operator system assembly, "
    "and complete-framework seven-operator neutralization runs. It does not establish "
    "real-robot external validity, independent custody, paper-level superiority, or causal "
    "necessity of every operator."
)
NEUTRALIZATION_DETAILS: Final = {
    StructureTwoOperator.OPCEU: "operator retained with a neutral statistic update",
    StructureTwoOperator.ORRER_CHEH: (
        "operator retained while feedback likelihood is replaced by identity"
    ),
    StructureTwoOperator.PCHMP: ("operator retained with unit actor-mechanism-role potentials"),
    StructureTwoOperator.CF_BOCPD: "operator retained with a unit cause potential",
    StructureTwoOperator.RGRC: ("operator retained while long-term admission is neutralized"),
    StructureTwoOperator.CCRR: "operator retained with a unit regime potential",
    StructureTwoOperator.CIAV: ("operator retained while verification evidence is neutralized"),
}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{name} schema drift or extra claim field")


def _reject_nonfinite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite numeric value at {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_nonfinite(item, f"{path}/{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_nonfinite(item, f"{path}/{index}")


def _strict_int(value: Any, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be a JSON integer, not a coercible value")
    return value


def _strict_number(value: Any, name: str) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{name} must be a JSON number, not a coercible value")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _strict_int_tuple(value: Any, name: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a JSON array")
    return tuple(_strict_int(item, f"{name} item") for item in value)


@dataclass(frozen=True, slots=True)
class FullScientificLoopConfig:
    base_route_config: Path
    train_seeds: tuple[int, ...]
    validation_seeds: tuple[int, ...]
    evaluation_seeds: tuple[int, ...]
    l2_candidates: tuple[float, ...]
    epochs: int
    learning_rate: float
    gradient_clip: float
    maximum_absolute_weight: float
    horizon: int
    action_success_probability: float
    regime_change_step: int
    regime_recurrence_step: int
    guest_event_steps: tuple[int, ...]
    unknown_event_steps: tuple[int, ...]
    identity_mismatch_steps: tuple[int, ...]
    ciav_steps: tuple[int, ...]
    location_count: int
    rgrc_positive_stability_steps: int


def load_full_scientific_loop_config(
    repository_root: Path,
    path: Path = DEFAULT_CONFIG,
) -> FullScientificLoopConfig:
    payload = json.loads((repository_root / path).read_text(encoding="utf-8"))
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "protocol_id",
            "base_route_config",
            "selected_route",
            "evidence_status",
            "interaction_training",
            "action_responsive_environment",
            "rgrc_activation_suite",
            "neutralization_ablation",
            "production_system",
            "complete_state_axes",
            "rao_blackwellized_blocks",
            "retained_operators",
            "claim_boundary",
        },
        "full scientific loop configuration",
    )
    if payload["schema_version"] != "0.2.0" or payload["protocol_id"] != PROTOCOL_ID:
        raise ValueError("full scientific loop protocol/version mismatch")
    if payload["selected_route"] != "C_stateful_joint_inference":
        raise ValueError("full scientific loop changed the selected Route C")
    if payload["evidence_status"] != "D0_ACTION_RESPONSIVE_DEVELOPMENT_NOT_PAPER_EVIDENCE":
        raise ValueError("full scientific loop evidence status was promoted")
    if payload["claim_boundary"] != CLAIM_BOUNDARY:
        raise ValueError("full scientific loop claim boundary drifted")
    if tuple(payload["complete_state_axes"]) != COMPLETE_STATE_AXES:
        raise ValueError("full scientific loop narrowed the complete state")
    if tuple(payload["rao_blackwellized_blocks"]) != RB_BLOCKS:
        raise ValueError("full scientific loop narrowed the RB blocks")
    expected_operators = {operator.value for operator in StructureTwoOperator}
    if set(payload["retained_operators"]) != expected_operators:
        raise ValueError("full scientific loop must retain all seven operators")
    base_route_config = Path(str(payload["base_route_config"]))
    resolved_base_config = (repository_root / base_route_config).resolve()
    if (
        base_route_config.is_absolute()
        or ".." in base_route_config.parts
        or not resolved_base_config.is_relative_to(repository_root.resolve())
        or not resolved_base_config.is_file()
    ):
        raise ValueError("base Route-C configuration must be a repository-local file")

    training = payload["interaction_training"]
    environment = payload["action_responsive_environment"]
    rgrc = payload["rgrc_activation_suite"]
    ablation = payload["neutralization_ablation"]
    production = payload["production_system"]
    if not all(
        isinstance(item, Mapping) for item in (training, environment, rgrc, ablation, production)
    ):
        raise ValueError("full scientific loop nested configuration is malformed")
    if production != {
        "system_version": PRODUCTION_SYSTEM_VERSION,
        "operator_order": list(PRODUCTION_OPERATOR_ORDER),
        "feedback_edge": PRODUCTION_FEEDBACK_EDGE,
        "require_all_module_source_bindings": True,
        "require_single_runtime_object": True,
    }:
        raise ValueError("Structure-Two production-system configuration drifted")
    _require_exact_keys(
        training,
        {
            "feature_names",
            "train_seeds",
            "validation_seeds",
            "l2_candidates",
            "epochs",
            "learning_rate",
            "gradient_clip",
            "maximum_absolute_weight",
            "training_action_policy",
            "label_semantics",
            "test_truth_seen_during_training",
        },
        "interaction training",
    )
    _require_exact_keys(
        environment,
        {
            "evaluation_seeds",
            "horizon",
            "action_success_probability",
            "regime_change_step",
            "regime_recurrence_step",
            "guest_event_steps",
            "unknown_event_steps",
            "identity_mismatch_steps",
            "ciav_steps",
            "location_count",
            "seed_conditioned_observation_strength",
            "shared_potential_outcome_randomness",
            "post_action_observation_available",
        },
        "action-responsive environment",
    )
    _require_exact_keys(
        rgrc,
        {
            "positive_stability_steps",
            "required_positive_transitions",
            "required_negative_cases",
        },
        "RGRC activation suite",
    )
    _require_exact_keys(
        ablation,
        {
            "policy",
            "operators",
            "same_initial_hidden_state",
            "same_exogenous_events",
            "same_potential_outcome_randomness",
            "same_particle_budget",
            "same_complete_state_access",
            "same_learned_interaction_model",
            "all_other_operators_retained",
        },
        "neutralization ablation",
    )
    if tuple(training["feature_names"]) != INTERACTION_FEATURE_NAMES:
        raise ValueError("learned interaction feature contract drifted")
    if training["label_semantics"] != "evaluator_only_complete_candidate_consistency":
        raise ValueError("learned interaction label semantics drifted")
    if training["training_action_policy"] != TRAINING_ACTION_POLICY:
        raise ValueError("interaction training action policy uses truth or drifted")
    if training["test_truth_seen_during_training"] is not False:
        raise ValueError("evaluation truth cannot enter interaction training")
    if not (
        environment["shared_potential_outcome_randomness"] is True
        and environment["post_action_observation_available"] is True
        and environment["seed_conditioned_observation_strength"] is True
    ):
        raise ValueError("action-responsive environment omitted causal pairing or observation")
    if ablation["policy"] != ("retain_operator_and_replace_only_its_effect_with_neutral_element"):
        raise ValueError("ablation policy must retain operators and use neutral elements")
    if set(ablation["operators"]) != expected_operators or not all(
        ablation[key] is True
        for key in (
            "same_initial_hidden_state",
            "same_exogenous_events",
            "same_potential_outcome_randomness",
            "same_particle_budget",
            "same_complete_state_access",
            "same_learned_interaction_model",
            "all_other_operators_retained",
        )
    ):
        raise ValueError("seven-operator neutralization fairness contract is incomplete")
    if set(rgrc["required_positive_transitions"]) != {"quarantine", "promote", "retract"}:
        raise ValueError("RGRC positive suite must cover quarantine, promote, and retract")
    if set(rgrc["required_negative_cases"]) != {
        "guest_actor_rejected",
        "unknown_actor_rejected",
        "identity_mismatch_rejected",
        "unstable_owner_rejected",
    }:
        raise ValueError("RGRC negative suite coverage drifted")

    train_seeds = _strict_int_tuple(training["train_seeds"], "train seeds")
    validation_seeds = _strict_int_tuple(training["validation_seeds"], "validation seeds")
    evaluation_seeds = _strict_int_tuple(environment["evaluation_seeds"], "evaluation seeds")
    seed_sets = tuple(map(set, (train_seeds, validation_seeds, evaluation_seeds)))
    if any(not values for values in seed_sets) or any(
        seed_sets[left] & seed_sets[right] for left in range(3) for right in range(left + 1, 3)
    ):
        raise ValueError("train, validation, and evaluation seeds must be non-empty and disjoint")
    horizon = _strict_int(environment["horizon"], "environment horizon")
    change_step = _strict_int(environment["regime_change_step"], "regime change step")
    recurrence_step = _strict_int(environment["regime_recurrence_step"], "regime recurrence step")
    if not 2 <= change_step < recurrence_step < horizon:
        raise ValueError("environment regime chronology is invalid")
    probability = _strict_number(
        environment["action_success_probability"], "action success probability"
    )
    if not 0.0 < probability < 1.0:
        raise ValueError("action success probability must be finite and non-degenerate")
    if not isinstance(training["l2_candidates"], list):
        raise ValueError("interaction L2 grid must be a JSON array")
    l2_candidates = tuple(
        _strict_number(value, "interaction L2 candidate") for value in training["l2_candidates"]
    )
    numeric_positive = (
        _strict_int(training["epochs"], "interaction epochs"),
        _strict_number(training["learning_rate"], "interaction learning rate"),
        _strict_number(training["gradient_clip"], "interaction gradient clip"),
        _strict_number(training["maximum_absolute_weight"], "interaction maximum absolute weight"),
    )
    if not l2_candidates or any(value < 0.0 or not math.isfinite(value) for value in l2_candidates):
        raise ValueError("interaction L2 grid is empty or invalid")
    if any(value <= 0.0 or not math.isfinite(value) for value in numeric_positive):
        raise ValueError("interaction optimizer controls must be finite and positive")
    location_count = _strict_int(environment["location_count"], "environment location count")
    if location_count < 3:
        raise ValueError("action-responsive environment requires at least three locations")
    rgrc_stability_steps = _strict_int(
        rgrc["positive_stability_steps"], "RGRC positive stability steps"
    )
    if rgrc_stability_steps < 2:
        raise ValueError("RGRC positive suite needs at least two stability steps")
    for name in (
        "guest_event_steps",
        "unknown_event_steps",
        "identity_mismatch_steps",
        "ciav_steps",
    ):
        values = _strict_int_tuple(environment[name], name)
        if len(values) != len(set(values)) or any(not 0 <= value < horizon for value in values):
            raise ValueError(f"{name} contains duplicates or out-of-horizon steps")
    return FullScientificLoopConfig(
        base_route_config=base_route_config,
        train_seeds=train_seeds,
        validation_seeds=validation_seeds,
        evaluation_seeds=evaluation_seeds,
        l2_candidates=l2_candidates,
        epochs=numeric_positive[0],
        learning_rate=numeric_positive[1],
        gradient_clip=numeric_positive[2],
        maximum_absolute_weight=numeric_positive[3],
        horizon=horizon,
        action_success_probability=probability,
        regime_change_step=change_step,
        regime_recurrence_step=recurrence_step,
        guest_event_steps=_strict_int_tuple(environment["guest_event_steps"], "guest_event_steps"),
        unknown_event_steps=_strict_int_tuple(
            environment["unknown_event_steps"], "unknown_event_steps"
        ),
        identity_mismatch_steps=_strict_int_tuple(
            environment["identity_mismatch_steps"], "identity_mismatch_steps"
        ),
        ciav_steps=_strict_int_tuple(environment["ciav_steps"], "ciav_steps"),
        location_count=location_count,
        rgrc_positive_stability_steps=rgrc_stability_steps,
    )


@dataclass(frozen=True, slots=True)
class LearnedCrossAxisInteractionModel:
    feature_names: tuple[str, ...]
    weights: tuple[float, ...]
    selected_l2: float
    train_loss: float
    validation_loss: float
    train_example_count: int
    validation_example_count: int
    train_seeds: tuple[int, ...]
    validation_seeds: tuple[int, ...]
    optimizer_epochs: int

    def __post_init__(self) -> None:
        if self.feature_names != INTERACTION_FEATURE_NAMES:
            raise ValueError("learned interaction model changed its feature contract")
        if len(self.weights) != len(self.feature_names) or any(
            not math.isfinite(value) for value in self.weights
        ):
            raise ValueError("learned interaction weights are malformed")
        if self.train_example_count < 1 or self.validation_example_count < 1:
            raise ValueError("learned interaction model requires train and validation examples")
        if set(self.train_seeds) & set(self.validation_seeds):
            raise ValueError("learned interaction train and validation seeds overlap")

    @property
    def model_hash(self) -> str:
        return content_sha256(asdict(self))

    def log_potential(self, terms: Sequence[float]) -> float:
        if len(terms) != len(self.weights) or any(not math.isfinite(value) for value in terms):
            raise ValueError("learned interaction received malformed sufficient features")
        return sum(weight * value for weight, value in zip(self.weights, terms, strict=True))


@dataclass(frozen=True, slots=True)
class ClosedLoopTruth:
    step_index: int
    actor: str
    mechanism: EventMechanism
    role_key: str
    instance_association_key: str
    cause: ParticleChangeCause
    regime_change: bool
    active_regime: str
    owner_habit_location: UUID
    object_location: UUID
    external_event: bool


@dataclass(frozen=True, slots=True)
class ProbabilityItem:
    key: str
    probability: float


@dataclass(frozen=True, slots=True)
class ClosedLoopFeedbackTrace:
    feedback_record_id: UUID
    superseded_revision_id: UUID
    corrected_revision_id: UUID
    actor_posterior_after: tuple[ProbabilityItem, ...]
    mechanism_posterior_after: tuple[ProbabilityItem, ...]
    role_posterior_after: tuple[ProbabilityItem, ...]
    contradictory: bool


class ActionResponsiveEnvironment:
    """Deterministic synthetic environment whose hidden state consumes route actions."""

    def __init__(self, *, seed: int, config: FullScientificLoopConfig) -> None:
        self.seed = seed
        self.config = config
        self.locations = tuple(
            content_uuid("route-c-v0.2-location", {"seed": seed, "index": index})
            for index in range(config.location_count)
        )
        self.object_location = self.locations[0]
        self.step_index = 0

    def _unit_random(self, namespace: str, step_index: int) -> float:
        digest = content_sha256(
            {"protocol": PROTOCOL_ID, "seed": self.seed, "step": step_index, "key": namespace}
        )
        return int(digest[:16], 16) / float(16**16)

    @staticmethod
    def _peaked(keys: Sequence[Any], target: Any, peak: float) -> dict[Any, float]:
        if target not in keys or len(keys) < 2:
            raise ValueError("peaked distribution target/support is invalid")
        remainder = (1.0 - peak) / (len(keys) - 1)
        return {key: peak if key == target else remainder for key in keys}

    def _regime(self, step_index: int) -> tuple[str, UUID, bool]:
        if step_index < self.config.regime_change_step:
            return "R0", self.locations[0], False
        if step_index < self.config.regime_recurrence_step:
            return "R1", self.locations[1], step_index == self.config.regime_change_step
        return "R0", self.locations[0], step_index == self.config.regime_recurrence_step

    def observe(self) -> tuple[FullJointObservation, ClosedLoopTruth]:
        if self.step_index >= self.config.horizon:
            raise ValueError("action-responsive environment is already terminal")
        index = self.step_index
        regime, owner_habit, regime_change = self._regime(index)
        actor = "owner"
        mechanism = EventMechanism.DIRECT_RELOCATION
        role_key = "direct:owner"
        cause = ParticleChangeCause.HABIT if regime_change else ParticleChangeCause.OBSERVATION
        instance = "target_instance"
        external_event = regime_change
        if index in self.config.guest_event_steps:
            actor = "guest"
            mechanism = EventMechanism.HANDOFF_RELOCATION
            role_key = "owner=>guest"
            cause = ParticleChangeCause.ACTOR
            external_event = True
            self.object_location = self.locations[2]
        elif index in self.config.unknown_event_steps:
            actor = "unknown_actor"
            mechanism = EventMechanism.UNKNOWN_MECHANISM
            role_key = "unknown:unknown_actor"
            cause = ParticleChangeCause.UNRESOLVED
            external_event = True
            self.object_location = self.locations[-1]
        elif index in self.config.identity_mismatch_steps:
            cause = ParticleChangeCause.IDENTITY
            instance = "identity_mismatch"
            external_event = True
            self.object_location = self.locations[2]
        elif regime_change:
            self.object_location = owner_habit

        actors = ("owner", "guest", "unknown_actor")
        mechanisms = tuple(EventMechanism)
        roles = (
            "owner=>guest",
            "guest=>owner",
            "owner=>unknown_actor",
            "unknown_actor=>owner",
        )
        visible_role = role_key if mechanism is EventMechanism.HANDOFF_RELOCATION else roles[0]
        # Evidence strength changes deterministically by seed and time.  This keeps
        # paired arms identical while preventing train/validation seeds from being
        # cosmetic UUID relabelings of the same learning examples.
        actor_peak = 0.76 + 0.16 * self._unit_random("actor-evidence", index)
        mechanism_peak = 0.76 + 0.16 * self._unit_random("mechanism-evidence", index)
        role_peak = 0.62 + 0.22 * self._unit_random("role-evidence", index)
        cause_peak = 0.82 + 0.16 * self._unit_random("cause-evidence", index)
        location_peak = 0.62 + 0.26 * self._unit_random("location-evidence", index)
        actor_posterior = self._peaked(actors, actor, actor_peak)
        mechanism_posterior = self._peaked(mechanisms, mechanism, mechanism_peak)
        ordered_role_posterior = self._peaked(roles, visible_role, role_peak)
        causes = tuple(ParticleChangeCause)
        cause_posterior = self._peaked(causes, cause, cause_peak)
        base_location_distribution = self._peaked(
            self.locations,
            self.object_location,
            location_peak,
        )
        observation = FullJointObservation(
            source_update_id=content_uuid(
                "route-c-v0.2-source", {"seed": self.seed, "step": index}
            ),
            evidence_cluster_id=content_uuid(
                "route-c-v0.2-cluster", {"seed": self.seed, "step": index}
            ),
            owner_actor_key="owner",
            actor_posterior=actor_posterior,
            mechanism_posterior=mechanism_posterior,
            ordered_role_posterior=ordered_role_posterior,
            identity_target_probability=(
                0.08 + 0.16 * self._unit_random("identity-evidence", index)
                if instance != "target_instance"
                else 0.80 + 0.16 * self._unit_random("identity-evidence", index)
            ),
            cause_posterior=cause_posterior,
            regime_change_probability=(
                0.75 + 0.18 * self._unit_random("regime-evidence", index)
                if regime_change
                else 0.04 + 0.12 * self._unit_random("regime-evidence", index)
            ),
            active_regime=regime,
            observed_location_id=self.object_location,
            base_location_distribution=base_location_distribution,
            known_location_ids=self.locations,
            unresolved_probability=(
                0.62 + 0.24 * self._unit_random("unknown-evidence", index)
                if actor == "unknown_actor"
                else 0.02 + 0.06 * self._unit_random("unknown-evidence", index)
            ),
        )
        truth = ClosedLoopTruth(
            step_index=index,
            actor=actor,
            mechanism=mechanism,
            role_key=role_key,
            instance_association_key=instance,
            cause=cause,
            regime_change=regime_change,
            active_regime=regime,
            owner_habit_location=owner_habit,
            object_location=self.object_location,
            external_event=external_event,
        )
        return observation, truth

    def execute(self, action: UUID) -> dict[str, Any]:
        if action not in self.locations:
            raise ValueError("environment action names an unknown location")
        index = self.step_index
        before = self.object_location
        success_draw = self._unit_random("action-success", index)
        success = success_draw < self.config.action_success_probability
        if success:
            self.object_location = action
        alternative = next(location for location in self.locations if location != action)
        counterfactual_post = alternative if success else before
        transition = {
            "step_index": index,
            "pre_action_location": str(before),
            "selected_action": str(action),
            "action_success_draw": success_draw,
            "action_success": success,
            "post_action_location": str(self.object_location),
            "counterfactual_action": str(alternative),
            "counterfactual_post_action_location": str(counterfactual_post),
            "counterfactual_action_sensitivity": self.object_location != counterfactual_post,
            "potential_outcome_randomness_key": content_sha256(
                {"seed": self.seed, "step": index, "namespace": "action-success"}
            ),
            "post_action_observation_available": True,
        }
        self.step_index += 1
        return transition

    def feedback(
        self,
        observation: FullJointObservation,
        truth: ClosedLoopTruth,
        transition: Mapping[str, Any],
    ) -> ClosedLoopFeedbackTrace:
        actors = tuple(observation.actor_posterior)
        mechanisms = tuple(observation.mechanism_posterior)
        roles = tuple(observation.ordered_role_posterior)
        actor_after = self._peaked(actors, truth.actor, 0.96)
        mechanism_after = self._peaked(mechanisms, truth.mechanism, 0.94)
        role_target = truth.role_key if truth.role_key in roles else roles[0]
        role_after = self._peaked(roles, role_target, 0.88)
        identity = {"seed": self.seed, "step": truth.step_index}
        return ClosedLoopFeedbackTrace(
            feedback_record_id=content_uuid("route-c-v0.2-feedback-record", identity),
            superseded_revision_id=observation.source_update_id,
            corrected_revision_id=content_uuid(
                "route-c-v0.2-corrected-feedback",
                {**identity, "success": bool(transition["action_success"])},
            ),
            actor_posterior_after=tuple(
                ProbabilityItem(str(key), value) for key, value in actor_after.items()
            ),
            mechanism_posterior_after=tuple(
                ProbabilityItem(key.value, value) for key, value in mechanism_after.items()
            ),
            role_posterior_after=tuple(
                ProbabilityItem(str(key), value) for key, value in role_after.items()
            ),
            contradictory=not bool(transition["action_success"]),
        )


def _candidate_matches_truth(candidate: FullJointCandidate, truth: ClosedLoopTruth) -> bool:
    change_decisions = {
        ParticleRegimeDecision.CREATE,
        ParticleRegimeDecision.REACTIVATE,
    }
    regime_matches = (
        candidate.regime_decision in change_decisions
        if truth.regime_change
        else candidate.regime_decision is ParticleRegimeDecision.STAY
    )
    role_matches = (
        candidate.role_key == truth.role_key
        if truth.mechanism is EventMechanism.HANDOFF_RELOCATION
        else candidate.placement_actor == truth.actor
    )
    return bool(
        candidate.mechanism is truth.mechanism
        and candidate.placement_actor == truth.actor
        and role_matches
        and candidate.instance_association_key == truth.instance_association_key
        and candidate.change_cause is truth.cause
        and regime_matches
    )


TrainingExample = tuple[tuple[float, ...], float, float]


def _build_training_evidence(
    train_examples: Sequence[TrainingExample],
    validation_examples: Sequence[TrainingExample],
) -> dict[str, Any]:
    """Canonical producer/verifier schema for the learned interaction data."""

    train_hash = content_sha256(train_examples)
    validation_hash = content_sha256(validation_examples)
    return {
        "training_action_policy": TRAINING_ACTION_POLICY,
        "seed_conditioned_observation_strength": True,
        "train_examples_sha256": train_hash,
        "validation_examples_sha256": validation_hash,
        "train_validation_examples_distinct": train_hash != validation_hash,
    }


def _interaction_examples(
    *,
    seeds: Sequence[int],
    config: FullScientificLoopConfig,
    runtime: StatefulFullJointRuntime,
) -> list[TrainingExample]:
    examples: list[TrainingExample] = []
    for seed in seeds:
        environment = ActionResponsiveEnvironment(seed=seed, config=config)
        for _ in range(config.horizon):
            observation, truth = environment.observe()
            candidates = runtime._candidates(observation, None)
            labels = [
                float(_candidate_matches_truth(candidate, truth)) for candidate, _ in candidates
            ]
            positive_count = sum(labels)
            if positive_count <= 0.0:
                raise ValueError("interaction training step has no oracle-consistent candidate")
            negative_count = len(labels) - positive_count
            positive_weight = min(100.0, negative_count / positive_count)
            for (candidate, proposal_mass), label in zip(candidates, labels, strict=True):
                class_weight = positive_weight if label else 1.0
                examples.append(
                    (
                        runtime.interaction_terms(observation, candidate),
                        label,
                        class_weight * max(proposal_mass, 1e-6),
                    )
                )
            # Cover actions without using evaluator truth to choose the training
            # trajectory.  Truth remains restricted to the supervised label.
            coverage_action = environment.locations[
                (seed + environment.step_index) % len(environment.locations)
            ]
            environment.execute(coverage_action)
    return examples


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-min(value, 60.0)))
    exponential = math.exp(max(value, -60.0))
    return exponential / (1.0 + exponential)


def _log_loss(examples: Sequence[TrainingExample], weights: Sequence[float]) -> float:
    weighted_loss = 0.0
    total_weight = 0.0
    for features, label, sample_weight in examples:
        probability = _sigmoid(sum(w * x for w, x in zip(weights, features, strict=True)))
        weighted_loss -= sample_weight * (
            label * math.log(max(probability, 1e-12))
            + (1.0 - label) * math.log(max(1.0 - probability, 1e-12))
        )
        total_weight += sample_weight
    return weighted_loss / total_weight


def _fit_weights(
    examples: Sequence[TrainingExample],
    *,
    l2: float,
    config: FullScientificLoopConfig,
) -> tuple[float, ...]:
    weights = [0.0 for _ in INTERACTION_FEATURE_NAMES]
    total_weight = sum(example[2] for example in examples)
    for _ in range(config.epochs):
        gradient = [0.0 for _ in weights]
        for features, label, sample_weight in examples:
            score = sum(weight * value for weight, value in zip(weights, features, strict=True))
            residual = (_sigmoid(score) - label) * sample_weight
            for index, value in enumerate(features):
                gradient[index] += residual * value
        for index, weight in enumerate(weights):
            raw = gradient[index] / total_weight + l2 * weight
            clipped = max(-config.gradient_clip, min(config.gradient_clip, raw))
            weights[index] = max(
                -config.maximum_absolute_weight,
                min(
                    config.maximum_absolute_weight,
                    weight - config.learning_rate * clipped,
                ),
            )
    return tuple(weights)


def train_cross_axis_interactions(
    *,
    repository_root: Path,
    config: FullScientificLoopConfig,
) -> tuple[
    LearnedCrossAxisInteractionModel,
    list[dict[str, float]],
    dict[str, Any],
]:
    base_config = load_stateful_full_joint_config(repository_root, config.base_route_config)
    neural_model = load_neural_proposal_model(base_config.neural_proposal_model_path)
    proposal_runtime = StatefulFullJointRuntime(
        arm=FullJointArm.MATCHED_FULL_STATE_FACTORIZED,
        config=base_config,
        neural_model=neural_model,
    )
    train_examples = _interaction_examples(
        seeds=config.train_seeds,
        config=config,
        runtime=proposal_runtime,
    )
    validation_examples = _interaction_examples(
        seeds=config.validation_seeds,
        config=config,
        runtime=proposal_runtime,
    )
    candidates: list[tuple[float, tuple[float, ...], float, float]] = []
    selection_rows: list[dict[str, float]] = []
    for l2 in config.l2_candidates:
        weights = _fit_weights(train_examples, l2=l2, config=config)
        train_loss = _log_loss(train_examples, weights)
        validation_loss = _log_loss(validation_examples, weights)
        candidates.append((l2, weights, train_loss, validation_loss))
        selection_rows.append(
            {
                "l2": l2,
                "train_loss": train_loss,
                "validation_loss": validation_loss,
            }
        )
    selected_l2, weights, train_loss, validation_loss = min(
        candidates,
        key=lambda row: (row[3], row[0]),
    )
    model = LearnedCrossAxisInteractionModel(
        feature_names=INTERACTION_FEATURE_NAMES,
        weights=weights,
        selected_l2=selected_l2,
        train_loss=train_loss,
        validation_loss=validation_loss,
        train_example_count=len(train_examples),
        validation_example_count=len(validation_examples),
        train_seeds=config.train_seeds,
        validation_seeds=config.validation_seeds,
        optimizer_epochs=config.epochs,
    )
    training_evidence = _build_training_evidence(train_examples, validation_examples)
    return model, selection_rows, training_evidence


class LearnedInteractionRuntime(StatefulFullJointRuntime):
    """Full Route-C runtime whose joint potential is learned then frozen."""

    def __init__(
        self,
        *,
        arm: FullJointArm,
        config: Any,
        neural_model: Any,
        interaction_model: LearnedCrossAxisInteractionModel,
        neutralized_operators: frozenset[StructureTwoOperator] = frozenset(),
    ) -> None:
        super().__init__(
            arm=arm,
            config=config,
            neural_model=neural_model,
            neutralized_operators=neutralized_operators,
        )
        self.interaction_model = interaction_model

    def _interaction_log_factor(
        self,
        observation: FullJointObservation,
        candidate: FullJointCandidate,
    ) -> float:
        terms = self.interaction_terms(observation, candidate)
        if self.arm is FullJointArm.MATCHED_FULL_STATE_FACTORIZED:
            # Execute the same feature path and model read, then apply the registered
            # factorized neutral coefficient.
            self.interaction_model.log_potential(terms)
            return 0.0
        return self.interaction_model.log_potential(terms)


def _verified_observation(
    runtime: StatefulFullJointRuntime,
    observation: FullJointObservation,
    truth: ClosedLoopTruth,
    config: FullScientificLoopConfig,
) -> FullJointObservation:
    if truth.step_index not in config.ciav_steps:
        return observation
    before = observation.actor_posterior[observation.owner_actor_key]
    after = 0.96 if truth.actor == observation.owner_actor_key else 0.02
    if StructureTwoOperator.CIAV in runtime.neutralized_operators:
        runtime.record_verification(
            source_update_id=observation.source_update_id,
            owner_probability_before=before,
            owner_probability_after=before,
        )
        return observation
    actors = dict(observation.actor_posterior)
    other_total = sum(
        value for actor, value in actors.items() if actor != observation.owner_actor_key
    )
    remainder = 1.0 - after
    actors = {
        actor: (after if actor == observation.owner_actor_key else remainder * value / other_total)
        for actor, value in actors.items()
    }
    runtime.record_verification(
        source_update_id=observation.source_update_id,
        owner_probability_before=before,
        owner_probability_after=after,
    )
    return replace(observation, actor_posterior=_normalize(actors))


def _run_closed_loop_arm(
    *,
    repository_root: Path,
    config: FullScientificLoopConfig,
    interaction_model: LearnedCrossAxisInteractionModel,
    seed: int,
    arm: FullJointArm,
    neutralized_operator: StructureTwoOperator | None = None,
) -> dict[str, Any]:
    base_config = load_stateful_full_joint_config(repository_root, config.base_route_config)
    neural_model = load_neural_proposal_model(base_config.neural_proposal_model_path)
    neutralized = (
        frozenset() if neutralized_operator is None else frozenset((neutralized_operator,))
    )
    runtime = LearnedInteractionRuntime(
        arm=arm,
        config=base_config,
        neural_model=neural_model,
        interaction_model=interaction_model,
        neutralized_operators=neutralized,
    )
    environment = ActionResponsiveEnvironment(seed=seed, config=config)
    traces: list[dict[str, Any]] = []
    putback_regret = 0.0
    search_regret = 0.0
    contamination = 0.0
    unknown_brier = 0.0
    previous_post_feedback_state_sha256: str | None = None
    previous_feedback_changed_particle_state = False
    later_feedback_consumption: list[bool] = []
    for _ in range(config.horizon):
        pre_observation_state_sha256 = runtime._state_sha256()
        if previous_post_feedback_state_sha256 is not None:
            later_feedback_consumption.append(
                previous_feedback_changed_particle_state
                and pre_observation_state_sha256 == previous_post_feedback_state_sha256
            )
        observation, truth = environment.observe()
        observation = _verified_observation(runtime, observation, truth, config)
        ledger_cursor = len(runtime.rgrc_ledger.records)
        runtime.revise(observation)
        distribution = runtime.action_distribution()
        runtime.action_readout_traces.append(dict(distribution))
        ranking = tuple(
            sorted(distribution, key=lambda location: (-distribution[location], str(location)))
        )
        action = ranking[0]
        step_putback_regret = float(action != truth.owner_habit_location)
        object_rank = ranking.index(truth.object_location)
        step_search_regret = object_rank / max(1, len(ranking) - 1)
        step_contamination = float(
            truth.actor != observation.owner_actor_key
            and action == truth.object_location
            and action != truth.owner_habit_location
        )
        putback_regret += step_putback_regret
        search_regret += step_search_regret
        contamination += step_contamination
        step_unknown_probability = runtime.unknown_actor_probability
        step_unknown_target = float(truth.actor == "unknown_actor")
        step_unknown_brier = (step_unknown_probability - step_unknown_target) ** 2
        unknown_brier += step_unknown_brier
        transition = environment.execute(action)
        feedback = environment.feedback(observation, truth, transition)
        pre_feedback_state_sha256 = runtime._state_sha256()
        runtime.apply_feedback(feedback)
        post_feedback_state_sha256 = runtime._state_sha256()
        feedback_changed_particle_state = pre_feedback_state_sha256 != post_feedback_state_sha256
        previous_post_feedback_state_sha256 = post_feedback_state_sha256
        previous_feedback_changed_particle_state = feedback_changed_particle_state
        traces.append(
            {
                "step_index": truth.step_index,
                "pre_observation_state_sha256": pre_observation_state_sha256,
                "source_update_id": str(observation.source_update_id),
                "actor_truth": truth.actor,
                "mechanism_truth": truth.mechanism.value,
                "cause_truth": truth.cause.value,
                "active_regime_truth": truth.active_regime,
                "owner_habit_location": str(truth.owner_habit_location),
                "object_location_before_action": str(truth.object_location),
                "external_event": truth.external_event,
                "action_distribution": {
                    str(location): probability
                    for location, probability in sorted(distribution.items())
                },
                "selected_action": str(action),
                "putback_regret": step_putback_regret,
                "search_regret": step_search_regret,
                "contamination": step_contamination,
                "unknown_actor_probability": step_unknown_probability,
                "unknown_actor_target": step_unknown_target,
                "unknown_calibration_brier": step_unknown_brier,
                "transition": dict(transition),
                "feedback_record_id": str(feedback.feedback_record_id),
                "corrected_revision_id": str(feedback.corrected_revision_id),
                "feedback_contradictory": feedback.contradictory,
                "pre_feedback_state_sha256": pre_feedback_state_sha256,
                "post_feedback_state_sha256": post_feedback_state_sha256,
                "feedback_changed_particle_state": feedback_changed_particle_state,
                "rgrc_operations": [
                    record.operation for record in runtime.rgrc_ledger.records[ledger_cursor:]
                ],
            }
        )
    runtime.verify_internal_contracts()
    receipts = runtime.operator_flow_receipts
    operator_counts = {
        operator.value: {
            "receipt_count": sum(receipt.operator is operator for receipt in receipts),
            "executed_count": sum(
                receipt.operator is operator and receipt.executed for receipt in receipts
            ),
            "changed_state_count": sum(
                receipt.operator is operator and receipt.changed_state for receipt in receipts
            ),
            "neutralization_receipt_count": sum(
                receipt.operator is operator and receipt.executed and not receipt.changed_state
                for receipt in receipts
            ),
        }
        for operator in StructureTwoOperator
    }
    operator_receipts = [
        {
            **asdict(receipt),
            "operator": receipt.operator.value,
            "consumed_axes": list(receipt.consumed_axes),
        }
        for receipt in receipts
    ]
    fairness_receipts = [
        {
            **asdict(receipt),
            "arm": receipt.arm.value,
            "complete_state_axes": list(receipt.complete_state_axes),
        }
        for receipt in runtime.fairness_receipts
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
    successful_transitions = [
        row["transition"] for row in traces if row["transition"]["action_success"]
    ]
    return {
        "seed": seed,
        "arm": arm.value,
        "neutralized_operator": (
            None if neutralized_operator is None else neutralized_operator.value
        ),
        "step_count": config.horizon,
        "put_back_error_rate": putback_regret / config.horizon,
        "search_regret_per_step": search_regret / config.horizon,
        "action_regret_per_step": (putback_regret + search_regret) / config.horizon,
        "owner_habit_contamination": contamination / config.horizon,
        "unknown_calibration_brier": unknown_brier / config.horizon,
        "action_conditioned_transition_count": len(successful_transitions),
        "environment_trajectory_responds_to_route_action": bool(successful_transitions)
        and all(row["counterfactual_action_sensitivity"] for row in successful_transitions),
        "post_action_observation_coverage": mean(
            float(row["transition"]["post_action_observation_available"]) for row in traces
        ),
        "feedback_revision_count": len(runtime._consumed_feedback_records),
        "corrected_state_consumed_by_later_actions": bool(later_feedback_consumption)
        and all(later_feedback_consumption)
        and neutralized_operator is not StructureTwoOperator.ORRER_CHEH,
        "operator_counts": operator_counts,
        "all_seven_operators_retained": set(operator_counts)
        == {operator.value for operator in StructureTwoOperator},
        "all_seven_operators_executed": all(
            row["executed_count"] > 0 for row in operator_counts.values()
        ),
        "neutralization_exercised": (
            neutralized_operator is None
            or operator_counts[neutralized_operator.value]["neutralization_receipt_count"] > 0
        ),
        "rgrc_operation_counts": {
            operation: sum(record.operation == operation for record in runtime.rgrc_ledger.records)
            for operation in ("quarantine", "promote", "retract", "corrected_revision")
        },
        "final_state_sha256": runtime._state_sha256(),
        "operator_receipt_head_sha256": runtime._last_operator_receipt_sha256,
        "operator_flow_receipts": operator_receipts,
        "fairness_receipts": fairness_receipts,
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
        "environment_trace_sha256": content_sha256(traces),
        "causal_pairing_sha256": content_sha256(
            [
                {
                    "step_index": row["step_index"],
                    "actor_truth": row["actor_truth"],
                    "mechanism_truth": row["mechanism_truth"],
                    "cause_truth": row["cause_truth"],
                    "active_regime_truth": row["active_regime_truth"],
                    "external_event": row["external_event"],
                    "potential_outcome_randomness_key": row["transition"][
                        "potential_outcome_randomness_key"
                    ],
                }
                for row in traces
            ]
        ),
        "traces": traces,
    }


def _summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    if not rows:
        raise ValueError("closed-loop summary requires at least one seed")
    return {
        "seed_count": float(len(rows)),
        "put_back_error_rate": mean(float(row["put_back_error_rate"]) for row in rows),
        "search_regret_per_step": mean(float(row["search_regret_per_step"]) for row in rows),
        "action_regret_per_step": mean(float(row["action_regret_per_step"]) for row in rows),
        "owner_habit_contamination": mean(float(row["owner_habit_contamination"]) for row in rows),
        "unknown_calibration_brier": mean(float(row["unknown_calibration_brier"]) for row in rows),
        "environment_response_rate": mean(
            float(bool(row["environment_trajectory_responds_to_route_action"])) for row in rows
        ),
        "post_action_observation_coverage": mean(
            float(row["post_action_observation_coverage"]) for row in rows
        ),
    }


def _particle_for_candidate(
    runtime: StatefulFullJointRuntime,
    observation: FullJointObservation,
    predicate: Any,
    *,
    draw_index: int,
) -> StatefulJointParticle:
    candidate = next(
        candidate for candidate, _ in runtime._candidates(observation, None) if predicate(candidate)
    )
    world = runtime._world_from_candidate(
        parent=None,
        candidate=candidate,
        observation=observation,
        draw_index=draw_index,
        snapshot_id=content_uuid(
            "route-c-v0.2-rgrc-suite-snapshot",
            {"source": str(observation.source_update_id), "draw": draw_index},
        ),
    )
    typed = world.typed_state.model_copy(update={"run_length": 5})
    world = replace(
        world,
        typed_state=typed,
        run_length_history=(*world.run_length_history[:-1], 5),
    )
    world.validate_complete()
    return StatefulJointParticle(world=world, posterior_probability=0.95)


def run_rgrc_activation_suite(
    *,
    repository_root: Path,
    config: FullScientificLoopConfig,
    interaction_model: LearnedCrossAxisInteractionModel,
) -> dict[str, Any]:
    base_config = load_stateful_full_joint_config(repository_root, config.base_route_config)
    neural_model = load_neural_proposal_model(base_config.neural_proposal_model_path)
    runtime = LearnedInteractionRuntime(
        arm=FullJointArm.STATEFUL_FULL_JOINT,
        config=base_config,
        neural_model=neural_model,
        interaction_model=interaction_model,
    )
    environment = ActionResponsiveEnvironment(seed=991, config=config)
    observation, _truth = environment.observe()
    distribution = dict.fromkeys(environment.locations, 1.0 / len(environment.locations))

    def ledger_rows(ledger: ReversibleJointRGRCLedger) -> list[dict[str, Any]]:
        return [
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
            for record in ledger.records
        ]

    owner = _particle_for_candidate(
        runtime,
        observation,
        lambda candidate: (
            candidate.placement_actor == "owner"
            and candidate.instance_association_key == "target_instance"
            and candidate.change_cause is ParticleChangeCause.HABIT
            and candidate.regime_decision is ParticleRegimeDecision.STAY
        ),
        draw_index=0,
    )
    guest = _particle_for_candidate(
        runtime,
        observation,
        lambda candidate: (
            candidate.placement_actor == "guest"
            and candidate.instance_association_key == "target_instance"
        ),
        draw_index=1,
    )
    unknown = _particle_for_candidate(
        runtime,
        observation,
        lambda candidate: (
            candidate.placement_actor == "unknown_actor"
            and candidate.instance_association_key == "target_instance"
        ),
        draw_index=2,
    )
    mismatch = _particle_for_candidate(
        runtime,
        observation,
        lambda candidate: (
            candidate.placement_actor == "owner"
            and candidate.instance_association_key == "identity_mismatch"
        ),
        draw_index=3,
    )

    positive = ReversibleJointRGRCLedger(
        admission_floor=0.5,
        stability_steps=config.rgrc_positive_stability_steps,
    )
    for _ in range(config.rgrc_positive_stability_steps):
        positive.consider((owner,), owner_key="owner", action_distribution=distribution)
    replacement_source = content_uuid(
        "route-c-v0.2-rgrc-replacement", owner.world.source_revision_id
    )
    replacement = replace(owner, world=replace(owner.world, source_revision_id=replacement_source))
    positive.consider((replacement,), owner_key="owner", action_distribution=distribution)
    positive.retract_source(replacement_source, replacement)
    positive.verify_chain()
    operations = tuple(record.operation for record in positive.records)

    negative_results: dict[str, bool] = {}
    negative_evidence: dict[str, dict[str, Any]] = {}
    for name, particle in (
        ("guest_actor_rejected", guest),
        ("unknown_actor_rejected", unknown),
        ("identity_mismatch_rejected", mismatch),
    ):
        ledger = ReversibleJointRGRCLedger(
            admission_floor=0.5,
            stability_steps=config.rgrc_positive_stability_steps,
        )
        changed = ledger.consider(
            (particle,),
            owner_key="owner",
            action_distribution=distribution,
        )
        ledger.verify_chain()
        negative_results[name] = not changed and not ledger.records
        negative_evidence[name] = {
            "consider_returned": changed,
            "record_count": len(ledger.records),
            "operations": [record.operation for record in ledger.records],
            "ledger_head_sha256": ledger.head_hash,
            "ledger_records": ledger_rows(ledger),
        }
    unstable = ReversibleJointRGRCLedger(
        admission_floor=0.5,
        stability_steps=config.rgrc_positive_stability_steps,
    )
    unstable.consider((owner,), owner_key="owner", action_distribution=distribution)
    unstable.verify_chain()
    negative_results["unstable_owner_rejected"] = not any(
        record.operation in {"promote", "corrected_revision"} for record in unstable.records
    )
    negative_evidence["unstable_owner_rejected"] = {
        "consider_returned": True,
        "record_count": len(unstable.records),
        "operations": [record.operation for record in unstable.records],
        "ledger_head_sha256": unstable.head_hash,
        "ledger_records": ledger_rows(unstable),
    }
    positive_results = {
        "quarantine_observed": "quarantine" in operations,
        "promote_observed": "promote" in operations,
        "replacement_retract_observed": "retract" in operations,
        "corrected_revision_observed": "corrected_revision" in operations,
        "final_explicit_retract_observed": operations[-1] == "retract",
    }
    positive_ledger_records = ledger_rows(positive)
    return {
        "positive_transition_sequence": list(operations),
        "positive_cases": positive_results,
        "positive_ledger_records": positive_ledger_records,
        "negative_cases": negative_results,
        "negative_case_evidence": negative_evidence,
        "all_required_positive_transitions_observed": all(
            operation in operations for operation in ("quarantine", "promote", "retract")
        ),
        "all_required_negative_cases_rejected": all(negative_results.values()),
        "ledger_head_sha256": positive.head_hash,
    }


def _paired_action_diagnostic(
    left_rows: Sequence[Mapping[str, Any]],
    right_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if len(left_rows) != len(right_rows):
        raise ValueError("paired closed-loop arms have different seed counts")
    total_variations: list[float] = []
    disagreements = 0
    for left, right in zip(left_rows, right_rows, strict=True):
        if left["seed"] != right["seed"]:
            raise ValueError("paired closed-loop arms have different seed ordering")
        left_traces = left["traces"]
        right_traces = right["traces"]
        if len(left_traces) != len(right_traces):
            raise ValueError("paired closed-loop arms have different horizons")
        for left_trace, right_trace in zip(left_traces, right_traces, strict=True):
            left_distribution = left_trace["action_distribution"]
            right_distribution = right_trace["action_distribution"]
            locations = set(left_distribution) | set(right_distribution)
            total_variations.append(
                0.5
                * sum(
                    abs(
                        float(left_distribution.get(location, 0.0))
                        - float(right_distribution.get(location, 0.0))
                    )
                    for location in locations
                )
            )
            disagreements += int(left_trace["selected_action"] != right_trace["selected_action"])
    return {
        "step_count": len(total_variations),
        "mean_action_posterior_tv": mean(total_variations),
        "max_action_posterior_tv": max(total_variations),
        "positive_action_posterior_tv_steps": sum(value > 1e-12 for value in total_variations),
        "selected_action_disagreement_steps": disagreements,
    }


def _deterministic_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(result))
    payload.pop("deterministic_replay_sha256", None)
    payload.pop("content_sha256", None)
    return payload


def run_full_scientific_loop_development(*, repository_root: Path) -> dict[str, Any]:
    config_path = repository_root / DEFAULT_CONFIG
    config = load_full_scientific_loop_config(repository_root)
    base_config_path = repository_root / config.base_route_config
    base_config = load_stateful_full_joint_config(repository_root, config.base_route_config)
    interaction_model, selection_rows, training_evidence = train_cross_axis_interactions(
        repository_root=repository_root,
        config=config,
    )
    interaction_artifact = {
        **asdict(interaction_model),
        "model_hash": interaction_model.model_hash,
        "selection_trials": selection_rows,
        "training_evidence": training_evidence,
        "frozen_before_evaluation": True,
        "evaluation_seeds_seen_during_training_or_selection": False,
    }

    full_rows = [
        _run_closed_loop_arm(
            repository_root=repository_root,
            config=config,
            interaction_model=interaction_model,
            seed=seed,
            arm=FullJointArm.STATEFUL_FULL_JOINT,
        )
        for seed in config.evaluation_seeds
    ]
    factorized_rows = [
        _run_closed_loop_arm(
            repository_root=repository_root,
            config=config,
            interaction_model=interaction_model,
            seed=seed,
            arm=FullJointArm.MATCHED_FULL_STATE_FACTORIZED,
        )
        for seed in config.evaluation_seeds
    ]
    causal_pairing_passed = all(
        full["causal_pairing_sha256"] == factorized["causal_pairing_sha256"]
        for full, factorized in zip(full_rows, factorized_rows, strict=True)
    )
    if not causal_pairing_passed:
        raise ValueError("joint/factorized environments do not share causal pairing")

    full_summary = _summary(full_rows)
    factorized_summary = _summary(factorized_rows)
    ablation_rows: dict[str, list[dict[str, Any]]] = {}
    ablation_summary: dict[str, dict[str, Any]] = {}
    for operator in StructureTwoOperator:
        rows = [
            _run_closed_loop_arm(
                repository_root=repository_root,
                config=config,
                interaction_model=interaction_model,
                seed=seed,
                arm=FullJointArm.STATEFUL_FULL_JOINT,
                neutralized_operator=operator,
            )
            for seed in config.evaluation_seeds
        ]
        ablation_rows[operator.value] = rows
        summary = _summary(rows)
        disagreement = _paired_action_diagnostic(rows, full_rows)
        ablation_summary[operator.value] = {
            "neutralization_policy": (
                "operator_retained_effect_replaced_by_registered_neutral_element"
            ),
            "summary": summary,
            "ablated_minus_full_action_regret_per_step": (
                summary["action_regret_per_step"] - full_summary["action_regret_per_step"]
            ),
            "ablated_minus_full_contamination": (
                summary["owner_habit_contamination"] - full_summary["owner_habit_contamination"]
            ),
            "decision_effect_observed": bool(
                disagreement["selected_action_disagreement_steps"] > 0
                or disagreement["max_action_posterior_tv"] > 1e-12
            ),
            "paired_action_diagnostic": disagreement,
            "operator_retained_in_every_run": all(
                row["all_seven_operators_retained"] for row in rows
            ),
            "all_other_operators_executed_in_every_run": all(
                all(
                    counts["executed_count"] > 0
                    for name, counts in row["operator_counts"].items()
                    if name != operator.value
                )
                for row in rows
            ),
            "neutralization_exercised_in_every_run": all(
                row["neutralization_exercised"] for row in rows
            ),
        }

    rgrc_suite = run_rgrc_activation_suite(
        repository_root=repository_root,
        config=config,
        interaction_model=interaction_model,
    )
    interaction_diagnostic = _paired_action_diagnostic(full_rows, factorized_rows)
    production_assembly = build_production_assembly_manifest(repository_root)
    all_closed_loops_respond = all(
        row["environment_trajectory_responds_to_route_action"]
        and row["post_action_observation_coverage"] == 1.0
        and row["feedback_revision_count"] == config.horizon
        for rows in (full_rows, factorized_rows, *ablation_rows.values())
        for row in rows
    )
    full_feedback_loop_closed = all(
        row["corrected_state_consumed_by_later_actions"]
        for rows in (full_rows, factorized_rows)
        for row in rows
    )
    all_ablation_runs_complete = set(ablation_summary) == {
        operator.value for operator in StructureTwoOperator
    } and all(
        row["operator_retained_in_every_run"]
        and row["all_other_operators_executed_in_every_run"]
        and row["neutralization_exercised_in_every_run"]
        for row in ablation_summary.values()
    )
    result: dict[str, Any] = {
        "protocol_id": PROTOCOL_ID,
        "selected_route": "C_stateful_joint_inference",
        "evidence_status": "D0_ACTION_RESPONSIVE_DEVELOPMENT_ONLY",
        "complete_state_axes": list(COMPLETE_STATE_AXES),
        "rao_blackwellized_blocks": list(RB_BLOCKS),
        "retained_operators": sorted(operator.value for operator in StructureTwoOperator),
        "production_system_assembly": production_assembly,
        "source_binding": {
            "configuration": {
                "path": str(DEFAULT_CONFIG),
                "sha256": _file_sha256(config_path),
            },
            "base_route_configuration": {
                "path": str(config.base_route_config),
                "sha256": _file_sha256(base_config_path),
            },
            "implementation": {
                "path": str(Path(__file__).resolve().relative_to(repository_root)),
                "sha256": _file_sha256(Path(__file__).resolve()),
            },
            "base_route_implementation": {
                "path": str(
                    Path(
                        "src/cpswm/system/evaluation_operations/"
                        "structure_two_stateful_full_joint.py"
                    )
                ),
                "sha256": _file_sha256(
                    repository_root / "src/cpswm/system/evaluation_operations/"
                    "structure_two_stateful_full_joint.py"
                ),
            },
            "neural_proposal_artifact": {
                "path": str(base_config.neural_proposal_model_path.relative_to(repository_root)),
                "sha256": _file_sha256(base_config.neural_proposal_model_path),
            },
        },
        "split_contract": {
            "train_seeds": list(config.train_seeds),
            "validation_seeds": list(config.validation_seeds),
            "development_evaluation_seeds": list(config.evaluation_seeds),
            "all_splits_disjoint": True,
            "evaluation_truth_seen_during_training_or_selection": False,
        },
        "learned_cross_axis_interaction": interaction_artifact,
        "action_responsive_environment": {
            "environment_trajectory_responds_to_route_action": all_closed_loops_respond,
            "post_action_observation_available": True,
            "shared_potential_outcome_randomness": True,
            "action_success_probability": config.action_success_probability,
            "horizon": config.horizon,
            "evaluation_seed_count": len(config.evaluation_seeds),
            "corrected_joint_state_consumed_by_later_actions": full_feedback_loop_closed,
            "claim_scope": "deterministic_D0_simulator_not_real_robot",
        },
        "matched_closed_loop_fairness": {
            "passed": causal_pairing_passed,
            "same_initial_hidden_state": True,
            "same_exogenous_event_schedule": True,
            "same_action_outcome_uniforms": True,
            "same_complete_state_access": True,
            "same_particle_budget": True,
            "same_neural_proposal": True,
            "same_learned_interaction_features_and_model_read": True,
            "only_registered_mechanism_difference": (
                "learned_cross_axis_log_potential_vs_zero_coefficient"
            ),
            "post_action_observations_may_diverge_only_after_actions_diverge": True,
        },
        "closed_loop_summaries": {
            FullJointArm.STATEFUL_FULL_JOINT.value: full_summary,
            FullJointArm.MATCHED_FULL_STATE_FACTORIZED.value: factorized_summary,
        },
        "joint_minus_factorized_lower_is_better": {
            "action_regret_per_step": (
                full_summary["action_regret_per_step"]
                - factorized_summary["action_regret_per_step"]
            ),
            "owner_habit_contamination": (
                full_summary["owner_habit_contamination"]
                - factorized_summary["owner_habit_contamination"]
            ),
        },
        "learned_interaction_utilization": interaction_diagnostic,
        "closed_loop_runs": {
            FullJointArm.STATEFUL_FULL_JOINT.value: full_rows,
            FullJointArm.MATCHED_FULL_STATE_FACTORIZED.value: factorized_rows,
        },
        "rgrc_activation_suite": rgrc_suite,
        "rgrc_positive_and_negative_activation_passed": bool(
            rgrc_suite["all_required_positive_transitions_observed"]
            and rgrc_suite["all_required_negative_cases_rejected"]
        ),
        "seven_operator_neutralization": {
            "policy": "retain_operator_and_replace_only_effect_with_neutral_element",
            "all_seven_neutralizations_completed": all_ablation_runs_complete,
            "summaries": ablation_summary,
            "runs": ablation_rows,
        },
        "all_seven_operator_contributions_established": False,
        "scientific_superiority_established": False,
        "real_robot_external_validity_established": False,
        "independent_custody_established": False,
        "task_8_formal_passed": False,
        "claim_boundary": CLAIM_BOUNDARY,
        "positive_output_trust_chain": {
            "/split_contract/all_splits_disjoint": (
                "exact_config_schema+set_disjointness+fresh_recomputation"
            ),
            "/learned_cross_axis_interaction/frozen_before_evaluation": (
                "train_only_fit+validation_only_selection+evaluation_seed_firewall+model_hash"
            ),
            "/production_system_assembly/single_runtime_object_owns_all_operator_instances": (
                "public_production_runtime+seven_importable_operator_classes+checked_out_source_hashes+"
                "forward_and_feedback_edges"
            ),
            "/action_responsive_environment/environment_trajectory_responds_to_route_action": (
                "per_step_factual_and_counterfactual_transitions+shared_outcome_uniforms+"
                "post_action_observations+fresh_recomputation"
            ),
            "/matched_closed_loop_fairness/passed": (
                "paired_schedule_hashes+shared_initial_state+shared_potential_outcomes+"
                "matched_compute_contract"
            ),
            "/rgrc_positive_and_negative_activation_passed": (
                "ledger_transition_sequence+four_rejection_cases+ledger_chain_verification"
            ),
            "/seven_operator_neutralization/all_seven_neutralizations_completed": (
                "seven_exact_single_operator_masks+retention_receipts+other_operator_execution+"
                "paired_seed_runs"
            ),
        },
    }
    result["deterministic_replay_sha256"] = content_sha256(_deterministic_payload(result))
    result["content_sha256"] = content_sha256(result)
    return result


def _verify_source_binding(result: Mapping[str, Any], repository_root: Path) -> None:
    source_binding = result.get("source_binding")
    if not isinstance(source_binding, Mapping):
        raise ValueError("full scientific loop source binding is missing")
    expected_paths = {
        "configuration": DEFAULT_CONFIG,
        "base_route_configuration": BASE_ROUTE_CONFIG,
        "implementation": Path(__file__).resolve().relative_to(repository_root),
        "base_route_implementation": Path(
            "src/cpswm/system/evaluation_operations/structure_two_stateful_full_joint.py"
        ),
    }
    base_config = load_stateful_full_joint_config(repository_root)
    expected_paths["neural_proposal_artifact"] = base_config.neural_proposal_model_path.relative_to(
        repository_root
    )
    if set(source_binding) != set(expected_paths):
        raise ValueError("full scientific loop source binding coverage drifted")
    for name, path in expected_paths.items():
        row = source_binding.get(name)
        if not isinstance(row, Mapping) or set(row) != {"path", "sha256"}:
            raise ValueError("full scientific loop source binding row is malformed")
        if row["path"] != str(path) or row["sha256"] != _file_sha256(repository_root / path):
            raise ValueError(f"full scientific loop source binding mismatch: {name}")


def _verify_probability_distribution(
    value: Any,
    *,
    expected_locations: Sequence[UUID],
) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError("closed-loop action distribution is missing")
    if any(type(probability) not in {int, float} for probability in value.values()):
        raise ValueError("closed-loop action distribution contains a non-numeric value")
    expected = {str(location) for location in expected_locations}
    distribution = {str(key): float(probability) for key, probability in value.items()}
    if set(distribution) != expected or any(
        not math.isfinite(probability) or probability < 0.0 for probability in distribution.values()
    ):
        raise ValueError("closed-loop action distribution support is malformed")
    if abs(sum(distribution.values()) - 1.0) > 1e-8:
        raise ValueError("closed-loop action distribution is not normalized")
    return distribution


def _operator_counts_from_receipts(
    receipts: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    return {
        operator.value: {
            "receipt_count": sum(row.get("operator") == operator.value for row in receipts),
            "executed_count": sum(
                row.get("operator") == operator.value and row.get("executed") is True
                for row in receipts
            ),
            "changed_state_count": sum(
                row.get("operator") == operator.value and row.get("changed_state") is True
                for row in receipts
            ),
            "neutralization_receipt_count": sum(
                row.get("operator") == operator.value
                and row.get("executed") is True
                and row.get("changed_state") is False
                for row in receipts
            ),
        }
        for operator in StructureTwoOperator
    }


def _verify_ledger_rows_strict(
    rows: Sequence[Mapping[str, Any]],
    expected_head: str,
    *,
    expected_locations: set[str] | None = None,
) -> tuple[str | None, dict[str, float] | None]:
    expected_keys = {
        "operation",
        "source_revision_id",
        "particle_revision_id",
        "owner_target_mass",
        "action_distribution",
        "previous_hash",
        "record_hash",
    }
    for row in rows:
        _require_exact_keys(row, expected_keys, "embedded RGRC ledger record")
        try:
            UUID(str(row["source_revision_id"]))
            UUID(str(row["particle_revision_id"]))
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("embedded RGRC identity is not a UUID") from error
        mass = row["owner_target_mass"]
        distribution = row["action_distribution"]
        if (
            type(mass) not in {int, float}
            or not math.isfinite(float(mass))
            or not 0.0 <= float(mass) <= 1.0
            or not isinstance(distribution, Mapping)
            or not distribution
        ):
            raise ValueError("embedded RGRC mass or distribution is invalid")
        if expected_locations is not None and set(map(str, distribution)) != expected_locations:
            raise ValueError("embedded RGRC distribution support was substituted")
        for location, probability in distribution.items():
            try:
                UUID(str(location))
            except (TypeError, ValueError, AttributeError) as error:
                raise ValueError("embedded RGRC location is not a UUID") from error
            if (
                type(probability) not in {int, float}
                or not math.isfinite(float(probability))
                or not 0.0 <= float(probability) <= 1.0
            ):
                raise ValueError("embedded RGRC distribution probability is invalid")
        if abs(sum(float(value) for value in distribution.values()) - 1.0) > 1e-8:
            raise ValueError("embedded RGRC distribution is not normalized")
        for field in ("previous_hash", "record_hash"):
            value = row[field]
            if value != "GENESIS" and (not isinstance(value, str) or len(value) != 64):
                raise ValueError("embedded RGRC hash is malformed")
    return _verify_ledger_rows(rows, expected_head)


def _verify_neutralization_receipts(
    receipts: Sequence[Mapping[str, Any]],
    *,
    expected_neutralized: StructureTwoOperator | None,
    horizon: int,
    ciav_execution_count: int,
) -> None:
    by_operator = {
        operator: [row for row in receipts if row.get("operator") == operator.value]
        for operator in StructureTwoOperator
    }
    if (
        len(by_operator[StructureTwoOperator.OPCEU]) != horizon
        or sum(row.get("executed") is True for row in by_operator[StructureTwoOperator.OPCEU])
        != horizon
    ):
        raise ValueError("OPCEU receipt schedule is incomplete")
    if (
        len(by_operator[StructureTwoOperator.ORRER_CHEH]) != 2 * horizon
        or sum(row.get("executed") is True for row in by_operator[StructureTwoOperator.ORRER_CHEH])
        != horizon
    ):
        raise ValueError("ORRER/CHEH receipt schedule is incomplete")
    for operator in (
        StructureTwoOperator.PCHMP,
        StructureTwoOperator.CF_BOCPD,
        StructureTwoOperator.CCRR,
    ):
        if len(by_operator[operator]) != horizon or not all(
            row.get("executed") is True for row in by_operator[operator]
        ):
            raise ValueError(f"{operator.value} receipt schedule is incomplete")
    if (
        len(by_operator[StructureTwoOperator.RGRC]) < horizon
        or sum(row.get("executed") is True for row in by_operator[StructureTwoOperator.RGRC])
        < horizon
    ):
        raise ValueError("RGRC receipt schedule is incomplete")
    ciav_rows = by_operator[StructureTwoOperator.CIAV]
    if (
        len(ciav_rows) != horizon + ciav_execution_count
        or sum(row.get("executed") is True for row in ciav_rows) != ciav_execution_count
    ):
        raise ValueError("CIAV receipt schedule is incomplete")

    neutral_details = set(NEUTRALIZATION_DETAILS.values())
    for operator, operator_rows in by_operator.items():
        executed_rows = [row for row in operator_rows if row.get("executed") is True]
        if operator is expected_neutralized:
            if not executed_rows or any(
                row.get("changed_state") is not False
                or row.get("detail") != NEUTRALIZATION_DETAILS[operator]
                for row in executed_rows
            ):
                raise ValueError(f"registered neutralization semantics failed: {operator.value}")
        elif any(row.get("detail") in neutral_details for row in executed_rows):
            raise ValueError(f"unexpected neutralization leaked into operator: {operator.value}")


def _verify_fairness_receipts(
    rows: Any,
    *,
    arm: FullJointArm,
    horizon: int,
) -> None:
    if (
        not isinstance(rows, Sequence)
        or len(rows) != horizon
        or not all(isinstance(row, Mapping) for row in rows)
    ):
        raise ValueError("closed-loop fairness receipts are incomplete")
    for expected_step, row in enumerate(rows, start=1):
        score_evaluations = row.get("target_score_evaluations")
        operations_per_candidate = row.get("score_operations_per_candidate")
        integer_fields = (
            "step_index",
            "particle_budget",
            "parent_count",
            "proposal_support_size",
            "target_score_evaluations",
            "proposal_draws",
            "score_operations_per_candidate",
            "score_operations",
        )
        hash_fields = (
            "robot_visible_input_sha256",
            "proposal_support_schema_sha256",
            "proposal_support_sha256",
            "proposal_model_hash",
            "common_random_number_sha256",
        )
        if (
            any(type(row.get(field)) is not int for field in integer_fields)
            or any(
                not isinstance(row.get(field), str) or len(str(row.get(field))) != 64
                for field in hash_fields
            )
            or row.get("step_index") != expected_step
            or row.get("arm") != arm.value
            or tuple(row.get("complete_state_axes", ())) != COMPLETE_STATE_AXES
            or row.get("proposal_support_policy") != "enumerate_all_positive_support"
            or score_evaluations != row.get("particle_budget")
            or row.get("proposal_draws") != row.get("particle_budget")
            or row.get("score_operations") != score_evaluations * operations_per_candidate
            or row.get("proposal_support_size", 0) < score_evaluations
            or row.get("parent_count") not in {1, row.get("particle_budget")}
        ):
            raise ValueError("closed-loop fairness receipt is invalid")


def _verify_closed_loop_run(
    row: Mapping[str, Any],
    *,
    config: FullScientificLoopConfig,
    expected_seed: int,
    expected_arm: FullJointArm,
    expected_neutralized: StructureTwoOperator | None,
) -> None:
    expected_keys = {
        "seed",
        "arm",
        "neutralized_operator",
        "step_count",
        "put_back_error_rate",
        "search_regret_per_step",
        "action_regret_per_step",
        "owner_habit_contamination",
        "unknown_calibration_brier",
        "action_conditioned_transition_count",
        "environment_trajectory_responds_to_route_action",
        "post_action_observation_coverage",
        "feedback_revision_count",
        "corrected_state_consumed_by_later_actions",
        "operator_counts",
        "all_seven_operators_retained",
        "all_seven_operators_executed",
        "neutralization_exercised",
        "rgrc_operation_counts",
        "final_state_sha256",
        "operator_receipt_head_sha256",
        "operator_flow_receipts",
        "fairness_receipts",
        "rgrc_ledger_head_sha256",
        "rgrc_active_source_revision_id",
        "rgrc_active_distribution",
        "rgrc_ledger_records",
        "environment_trace_sha256",
        "causal_pairing_sha256",
        "traces",
    }
    _require_exact_keys(row, expected_keys, "closed-loop run")
    expected_neutralized_value = (
        None if expected_neutralized is None else expected_neutralized.value
    )
    numeric_fields = (
        "put_back_error_rate",
        "search_regret_per_step",
        "action_regret_per_step",
        "owner_habit_contamination",
        "unknown_calibration_brier",
        "post_action_observation_coverage",
    )
    boolean_fields = (
        "environment_trajectory_responds_to_route_action",
        "corrected_state_consumed_by_later_actions",
        "all_seven_operators_retained",
        "all_seven_operators_executed",
        "neutralization_exercised",
    )
    if (
        type(row["seed"]) is not int
        or type(row["step_count"]) is not int
        or type(row["action_conditioned_transition_count"]) is not int
        or type(row["feedback_revision_count"]) is not int
        or any(type(row[field]) not in {int, float} for field in numeric_fields)
        or any(type(row[field]) is not bool for field in boolean_fields)
        or row["seed"] != expected_seed
        or row["arm"] != expected_arm.value
        or row["neutralized_operator"] != expected_neutralized_value
        or row["step_count"] != config.horizon
    ):
        raise ValueError("closed-loop run identity or horizon mismatch")
    traces = row["traces"]
    if (
        not isinstance(traces, Sequence)
        or len(traces) != config.horizon
        or not all(isinstance(trace, Mapping) for trace in traces)
    ):
        raise ValueError("closed-loop trace coverage is incomplete")

    environment = ActionResponsiveEnvironment(seed=expected_seed, config=config)
    putback_values: list[float] = []
    search_values: list[float] = []
    contamination_values: list[float] = []
    brier_values: list[float] = []
    action_conditioned = 0
    post_observation_values: list[float] = []
    embedded_rgrc_operations: list[str] = []
    feedback_consumption_evidence: list[bool] = []
    previous_post_feedback_state_sha256: str | None = None
    previous_feedback_changed_particle_state = False
    trace_keys = {
        "step_index",
        "pre_observation_state_sha256",
        "source_update_id",
        "actor_truth",
        "mechanism_truth",
        "cause_truth",
        "active_regime_truth",
        "owner_habit_location",
        "object_location_before_action",
        "external_event",
        "action_distribution",
        "selected_action",
        "putback_regret",
        "search_regret",
        "contamination",
        "unknown_actor_probability",
        "unknown_actor_target",
        "unknown_calibration_brier",
        "transition",
        "feedback_record_id",
        "corrected_revision_id",
        "feedback_contradictory",
        "pre_feedback_state_sha256",
        "post_feedback_state_sha256",
        "feedback_changed_particle_state",
        "rgrc_operations",
    }
    for expected_step, trace in enumerate(traces):
        _require_exact_keys(trace, trace_keys, "closed-loop trace")
        state_hash_fields = (
            "pre_observation_state_sha256",
            "pre_feedback_state_sha256",
            "post_feedback_state_sha256",
        )
        if type(trace["step_index"]) is not int or any(
            not isinstance(trace[field], str) or len(trace[field]) != 64
            for field in state_hash_fields
        ):
            raise ValueError("closed-loop trace index or state hash is malformed")
        if (
            any(
                type(trace[field]) not in {int, float}
                for field in (
                    "putback_regret",
                    "search_regret",
                    "contamination",
                    "unknown_actor_probability",
                    "unknown_actor_target",
                    "unknown_calibration_brier",
                )
            )
            or type(trace["external_event"]) is not bool
            or type(trace["feedback_contradictory"]) is not bool
            or type(trace["feedback_changed_particle_state"]) is not bool
            or not isinstance(trace["selected_action"], str)
        ):
            raise ValueError("closed-loop trace field types are malformed")
        if previous_post_feedback_state_sha256 is not None:
            feedback_consumption_evidence.append(
                previous_feedback_changed_particle_state
                and trace["pre_observation_state_sha256"] == previous_post_feedback_state_sha256
            )
        observation, truth = environment.observe()
        if (
            trace["step_index"] != expected_step
            or trace["source_update_id"] != str(observation.source_update_id)
            or trace["actor_truth"] != truth.actor
            or trace["mechanism_truth"] != truth.mechanism.value
            or trace["cause_truth"] != truth.cause.value
            or trace["active_regime_truth"] != truth.active_regime
            or trace["owner_habit_location"] != str(truth.owner_habit_location)
            or trace["object_location_before_action"] != str(truth.object_location)
            or trace["external_event"] is not truth.external_event
        ):
            raise ValueError("closed-loop truth trace disagrees with the environment")
        distribution = _verify_probability_distribution(
            trace["action_distribution"],
            expected_locations=environment.locations,
        )
        ranking = tuple(
            sorted(distribution, key=lambda location: (-distribution[location], location))
        )
        if trace["selected_action"] != ranking[0]:
            raise ValueError("closed-loop selected action is not the registered readout")
        selected_action = UUID(str(trace["selected_action"]))
        expected_transition = environment.execute(selected_action)
        if content_sha256(trace["transition"]) != content_sha256(expected_transition):
            raise ValueError("closed-loop transition is not environment-derived")
        action_conditioned += int(expected_transition["action_success"])
        post_observation_values.append(
            float(expected_transition["post_action_observation_available"])
        )

        putback = float(selected_action != truth.owner_habit_location)
        search = ranking.index(str(truth.object_location)) / max(1, len(ranking) - 1)
        contamination = float(
            truth.actor != observation.owner_actor_key
            and selected_action == truth.object_location
            and selected_action != truth.owner_habit_location
        )
        unknown_probability = float(trace["unknown_actor_probability"])
        unknown_target = float(truth.actor == "unknown_actor")
        brier = (unknown_probability - unknown_target) ** 2
        if (
            not math.isfinite(unknown_probability)
            or not 0.0 <= unknown_probability <= 1.0
            or trace["unknown_actor_target"] != unknown_target
            or trace["putback_regret"] != putback
            or trace["search_regret"] != search
            or trace["contamination"] != contamination
            or trace["unknown_calibration_brier"] != brier
        ):
            raise ValueError("closed-loop step metric is not trace-derived")
        putback_values.append(putback)
        search_values.append(search)
        contamination_values.append(contamination)
        brier_values.append(brier)

        feedback = environment.feedback(observation, truth, expected_transition)
        if (
            trace["feedback_record_id"] != str(feedback.feedback_record_id)
            or trace["corrected_revision_id"] != str(feedback.corrected_revision_id)
            or trace["feedback_contradictory"] is not feedback.contradictory
        ):
            raise ValueError("closed-loop feedback identity is not environment-derived")
        feedback_changed_particle_state = (
            trace["pre_feedback_state_sha256"] != trace["post_feedback_state_sha256"]
        )
        expected_feedback_change = expected_neutralized is not StructureTwoOperator.ORRER_CHEH
        if (
            trace["feedback_changed_particle_state"] is not feedback_changed_particle_state
            or feedback_changed_particle_state is not expected_feedback_change
        ):
            raise ValueError("closed-loop feedback state transition is not hash-derived")
        previous_post_feedback_state_sha256 = trace["post_feedback_state_sha256"]
        previous_feedback_changed_particle_state = feedback_changed_particle_state
        operations = trace["rgrc_operations"]
        if not isinstance(operations, list) or not all(
            operation in {"quarantine", "promote", "retract", "corrected_revision"}
            for operation in operations
        ):
            raise ValueError("closed-loop trace has malformed RGRC operations")
        embedded_rgrc_operations.extend(str(operation) for operation in operations)

    expected_metrics = {
        "put_back_error_rate": sum(putback_values) / config.horizon,
        "search_regret_per_step": sum(search_values) / config.horizon,
        "action_regret_per_step": (sum(putback_values) + sum(search_values)) / config.horizon,
        "owner_habit_contamination": sum(contamination_values) / config.horizon,
        "unknown_calibration_brier": sum(brier_values) / config.horizon,
        "post_action_observation_coverage": mean(post_observation_values),
    }
    if any(
        not math.isclose(float(row[name]), value, rel_tol=0.0, abs_tol=1e-15)
        for name, value in expected_metrics.items()
    ):
        raise ValueError("closed-loop aggregate metric is not trace-derived")
    if (
        row["action_conditioned_transition_count"] != action_conditioned
        or row["environment_trajectory_responds_to_route_action"] is not (action_conditioned > 0)
        or row["feedback_revision_count"] != config.horizon
    ):
        raise ValueError("closed-loop action/feedback coverage is not trace-derived")
    expected_corrected_consumption = bool(feedback_consumption_evidence) and all(
        feedback_consumption_evidence
    )
    if row["corrected_state_consumed_by_later_actions"] is not expected_corrected_consumption:
        raise ValueError("closed-loop corrected-state consumption claim is inconsistent")
    if row["environment_trace_sha256"] != content_sha256(traces):
        raise ValueError("closed-loop environment trace hash mismatch")
    expected_pairing = content_sha256(
        [
            {
                "step_index": trace["step_index"],
                "actor_truth": trace["actor_truth"],
                "mechanism_truth": trace["mechanism_truth"],
                "cause_truth": trace["cause_truth"],
                "active_regime_truth": trace["active_regime_truth"],
                "external_event": trace["external_event"],
                "potential_outcome_randomness_key": trace["transition"][
                    "potential_outcome_randomness_key"
                ],
            }
            for trace in traces
        ]
    )
    if row["causal_pairing_sha256"] != expected_pairing:
        raise ValueError("closed-loop causal-pairing hash mismatch")

    operator_receipts = row["operator_flow_receipts"]
    if not isinstance(operator_receipts, Sequence) or not all(
        isinstance(receipt, Mapping) for receipt in operator_receipts
    ):
        raise ValueError("closed-loop operator receipt evidence is missing")
    _verify_operator_receipt_rows(
        operator_receipts,
        str(row["operator_receipt_head_sha256"]),
    )
    previous_step = 0
    receipt_keys = {
        "step_index",
        "operator",
        "executed",
        "changed_state",
        "input_state_sha256",
        "output_state_sha256",
        "consumed_axes",
        "detail",
        "previous_receipt_sha256",
        "receipt_sha256",
    }
    for receipt in operator_receipts:
        _require_exact_keys(receipt, receipt_keys, "closed-loop operator receipt")
        step_index = receipt.get("step_index")
        if (
            type(step_index) is not int
            or step_index < previous_step
            or receipt.get("operator") not in {operator.value for operator in StructureTwoOperator}
            or type(receipt.get("executed")) is not bool
            or type(receipt.get("changed_state")) is not bool
            or (receipt.get("changed_state") is True and receipt.get("executed") is not True)
            or not isinstance(receipt.get("consumed_axes"), list)
            or not set(receipt.get("consumed_axes", ())).issubset(COMPLETE_STATE_AXES)
            or not isinstance(receipt.get("detail"), str)
            or any(
                not isinstance(receipt.get(field), str) or len(str(receipt.get(field))) != 64
                for field in (
                    "input_state_sha256",
                    "output_state_sha256",
                    "receipt_sha256",
                )
            )
        ):
            raise ValueError("closed-loop operator receipt transition is invalid")
        previous_step = step_index
    _verify_neutralization_receipts(
        operator_receipts,
        expected_neutralized=expected_neutralized,
        horizon=config.horizon,
        ciav_execution_count=len(config.ciav_steps),
    )
    derived_operator_counts = _operator_counts_from_receipts(operator_receipts)
    if row["operator_counts"] != derived_operator_counts:
        raise ValueError("closed-loop operator counts are not receipt-derived")
    expected_operator_names = {operator.value for operator in StructureTwoOperator}
    if row["all_seven_operators_retained"] is not (
        set(derived_operator_counts) == expected_operator_names
    ) or row["all_seven_operators_executed"] is not all(
        counts["executed_count"] > 0 for counts in derived_operator_counts.values()
    ):
        raise ValueError("closed-loop seven-operator retention/execution claim is false")
    neutralization_exercised = expected_neutralized is None or (
        derived_operator_counts[expected_neutralized.value]["neutralization_receipt_count"] > 0
    )
    if row["neutralization_exercised"] is not neutralization_exercised:
        raise ValueError("closed-loop neutralization execution claim is false")
    _verify_fairness_receipts(
        row["fairness_receipts"],
        arm=expected_arm,
        horizon=config.horizon,
    )

    ledger_rows = row["rgrc_ledger_records"]
    if not isinstance(ledger_rows, Sequence) or not all(
        isinstance(record, Mapping) for record in ledger_rows
    ):
        raise ValueError("closed-loop RGRC ledger evidence is missing")
    active_source, active_distribution = _verify_ledger_rows_strict(
        ledger_rows,
        str(row["rgrc_ledger_head_sha256"]),
        expected_locations={str(location) for location in environment.locations},
    )
    if (
        row["rgrc_active_source_revision_id"] != active_source
        or content_sha256(row["rgrc_active_distribution"]) != content_sha256(active_distribution)
        or embedded_rgrc_operations != [str(record["operation"]) for record in ledger_rows]
    ):
        raise ValueError("closed-loop RGRC terminal state or trace segmentation is invalid")
    derived_rgrc_counts = {
        operation: sum(record.get("operation") == operation for record in ledger_rows)
        for operation in ("quarantine", "promote", "retract", "corrected_revision")
    }
    if row["rgrc_operation_counts"] != derived_rgrc_counts:
        raise ValueError("closed-loop RGRC counts are not ledger-derived")


def _verify_rgrc_activation_suite(
    suite: Mapping[str, Any],
    *,
    config: FullScientificLoopConfig,
) -> None:
    _require_exact_keys(
        suite,
        {
            "positive_transition_sequence",
            "positive_cases",
            "positive_ledger_records",
            "negative_cases",
            "negative_case_evidence",
            "all_required_positive_transitions_observed",
            "all_required_negative_cases_rejected",
            "ledger_head_sha256",
        },
        "RGRC activation suite",
    )
    records = suite["positive_ledger_records"]
    if not isinstance(records, Sequence) or not all(
        isinstance(record, Mapping) for record in records
    ):
        raise ValueError("RGRC positive ledger evidence is missing")
    suite_locations = {
        str(location) for location in ActionResponsiveEnvironment(seed=991, config=config).locations
    }
    active_source, active_distribution = _verify_ledger_rows_strict(
        records,
        str(suite["ledger_head_sha256"]),
        expected_locations=suite_locations,
    )
    operations = [str(record["operation"]) for record in records]
    if (
        suite["positive_transition_sequence"] != operations
        or active_source is not None
        or active_distribution is not None
    ):
        raise ValueError("RGRC positive transition sequence is not ledger-derived")
    expected_positive = {
        "quarantine_observed": "quarantine" in operations,
        "promote_observed": "promote" in operations,
        "replacement_retract_observed": "retract" in operations,
        "corrected_revision_observed": "corrected_revision" in operations,
        "final_explicit_retract_observed": bool(operations) and operations[-1] == "retract",
    }
    if suite["positive_cases"] != expected_positive or suite[
        "all_required_positive_transitions_observed"
    ] is not all(operation in operations for operation in ("quarantine", "promote", "retract")):
        raise ValueError("RGRC positive activation claims are false")
    expected_negative_names = {
        "guest_actor_rejected",
        "unknown_actor_rejected",
        "identity_mismatch_rejected",
        "unstable_owner_rejected",
    }
    negative = suite["negative_cases"]
    evidence = suite["negative_case_evidence"]
    if (
        not isinstance(negative, Mapping)
        or not isinstance(evidence, Mapping)
        or set(negative) != expected_negative_names
        or set(evidence) != expected_negative_names
    ):
        raise ValueError("RGRC negative activation coverage is incomplete")
    for name in expected_negative_names:
        row = evidence[name]
        if not isinstance(row, Mapping) or set(row) != {
            "consider_returned",
            "record_count",
            "operations",
            "ledger_head_sha256",
            "ledger_records",
        }:
            raise ValueError("RGRC negative activation evidence is malformed")
        ledger_records = row["ledger_records"]
        if not isinstance(ledger_records, Sequence) or not all(
            isinstance(record, Mapping) for record in ledger_records
        ):
            raise ValueError("RGRC negative ledger records are malformed")
        active_source, active_distribution = _verify_ledger_rows_strict(
            ledger_records,
            str(row["ledger_head_sha256"]),
            expected_locations=suite_locations,
        )
        derived_operations = [str(record["operation"]) for record in ledger_records]
        if (
            active_source is not None
            or active_distribution is not None
            or row["record_count"] != len(ledger_records)
            or row["operations"] != derived_operations
        ):
            raise ValueError("RGRC negative evidence is not ledger-derived")
        if name == "unstable_owner_rejected":
            valid = (
                row["consider_returned"] is True
                and derived_operations == ["quarantine"]
                and config.rgrc_positive_stability_steps > 1
            )
        else:
            valid = (
                row["consider_returned"] is False
                and derived_operations == []
                and row["ledger_head_sha256"] == "GENESIS"
            )
        if negative[name] is not valid:
            raise ValueError(f"RGRC negative activation claim is false: {name}")
    if suite["all_required_negative_cases_rejected"] is not all(
        bool(value) for value in negative.values()
    ):
        raise ValueError("RGRC negative activation aggregate is false")


def verify_full_scientific_loop_result(
    result: Mapping[str, Any],
    *,
    repository_root: Path | None = None,
    fresh_replay: bool = False,
) -> None:
    expected_keys = {
        "protocol_id",
        "selected_route",
        "evidence_status",
        "complete_state_axes",
        "rao_blackwellized_blocks",
        "retained_operators",
        "production_system_assembly",
        "source_binding",
        "split_contract",
        "learned_cross_axis_interaction",
        "action_responsive_environment",
        "matched_closed_loop_fairness",
        "closed_loop_summaries",
        "joint_minus_factorized_lower_is_better",
        "learned_interaction_utilization",
        "closed_loop_runs",
        "rgrc_activation_suite",
        "rgrc_positive_and_negative_activation_passed",
        "seven_operator_neutralization",
        "all_seven_operator_contributions_established",
        "scientific_superiority_established",
        "real_robot_external_validity_established",
        "independent_custody_established",
        "task_8_formal_passed",
        "claim_boundary",
        "positive_output_trust_chain",
        "deterministic_replay_sha256",
        "content_sha256",
    }
    _require_exact_keys(result, expected_keys, "full scientific loop result")
    _reject_nonfinite(result)
    if result["protocol_id"] != PROTOCOL_ID or result["selected_route"] != (
        "C_stateful_joint_inference"
    ):
        raise ValueError("full scientific loop result protocol/route mismatch")
    if result["evidence_status"] != "D0_ACTION_RESPONSIVE_DEVELOPMENT_ONLY":
        raise ValueError("full scientific loop result evidence status was promoted")
    if result["claim_boundary"] != CLAIM_BOUNDARY:
        raise ValueError("full scientific loop result claim boundary drifted")
    if tuple(result["complete_state_axes"]) != COMPLETE_STATE_AXES:
        raise ValueError("full scientific loop result narrowed the complete state")
    if tuple(result["rao_blackwellized_blocks"]) != RB_BLOCKS:
        raise ValueError("full scientific loop result narrowed the RB blocks")
    if set(result["retained_operators"]) != {operator.value for operator in StructureTwoOperator}:
        raise ValueError("full scientific loop result omitted a retained operator")
    stored_content = result["content_sha256"]
    unsigned = dict(result)
    unsigned.pop("content_sha256", None)
    if stored_content != content_sha256(unsigned):
        raise ValueError("full scientific loop result content hash mismatch")
    if result["deterministic_replay_sha256"] != content_sha256(_deterministic_payload(result)):
        raise ValueError("full scientific loop deterministic replay hash mismatch")
    root = repository_root or Path(__file__).resolve().parents[4]
    _verify_source_binding(result, root)
    config = load_full_scientific_loop_config(root)
    production_assembly = result["production_system_assembly"]
    if not isinstance(production_assembly, Mapping):
        raise ValueError("Structure-Two production assembly is missing")
    verify_production_assembly_manifest(production_assembly, root)
    split = result["split_contract"]
    if not isinstance(split, Mapping) or (
        tuple(split.get("train_seeds", ())) != config.train_seeds
        or tuple(split.get("validation_seeds", ())) != config.validation_seeds
        or tuple(split.get("development_evaluation_seeds", ())) != config.evaluation_seeds
        or split.get("all_splits_disjoint") is not True
        or split.get("evaluation_truth_seen_during_training_or_selection") is not False
    ):
        raise ValueError("full scientific loop split contract mismatch")
    interaction = result["learned_cross_axis_interaction"]
    if not isinstance(interaction, Mapping):
        raise ValueError("learned interaction artifact is missing")
    model_fields = {
        field.name for field in LearnedCrossAxisInteractionModel.__dataclass_fields__.values()
    }
    model_payload = {name: interaction[name] for name in model_fields}
    if (
        not isinstance(model_payload["feature_names"], Sequence)
        or isinstance(model_payload["feature_names"], (str, bytes, bytearray))
        or not all(isinstance(value, str) for value in model_payload["feature_names"])
        or not isinstance(model_payload["weights"], Sequence)
        or isinstance(model_payload["weights"], (str, bytes, bytearray))
        or not all(type(value) in {int, float} for value in model_payload["weights"])
        or any(
            type(model_payload[name]) not in {int, float}
            for name in ("selected_l2", "train_loss", "validation_loss")
        )
        or any(
            type(model_payload[name]) is not int
            for name in (
                "train_example_count",
                "validation_example_count",
                "optimizer_epochs",
            )
        )
        or any(
            not isinstance(model_payload[name], Sequence)
            or isinstance(model_payload[name], (str, bytes, bytearray))
            or not all(type(value) is int for value in model_payload[name])
            for name in ("train_seeds", "validation_seeds")
        )
    ):
        raise ValueError("learned interaction model field types are malformed")
    model = LearnedCrossAxisInteractionModel(
        feature_names=tuple(model_payload["feature_names"]),
        weights=tuple(float(value) for value in model_payload["weights"]),
        selected_l2=float(model_payload["selected_l2"]),
        train_loss=float(model_payload["train_loss"]),
        validation_loss=float(model_payload["validation_loss"]),
        train_example_count=int(model_payload["train_example_count"]),
        validation_example_count=int(model_payload["validation_example_count"]),
        train_seeds=tuple(int(value) for value in model_payload["train_seeds"]),
        validation_seeds=tuple(int(value) for value in model_payload["validation_seeds"]),
        optimizer_epochs=int(model_payload["optimizer_epochs"]),
    )
    if interaction.get("model_hash") != model.model_hash:
        raise ValueError("learned interaction model hash mismatch")
    if not any(abs(weight) > 1e-9 for weight in model.weights):
        raise ValueError("learned interaction model remained the zero model")
    if (
        model.train_seeds != config.train_seeds
        or model.validation_seeds != config.validation_seeds
        or model.optimizer_epochs != config.epochs
        or model.selected_l2 not in config.l2_candidates
        or not all(math.isfinite(value) for value in (model.train_loss, model.validation_loss))
    ):
        raise ValueError("learned interaction model disagrees with the registered split/optimizer")
    expected_interaction_keys = model_fields | {
        "model_hash",
        "selection_trials",
        "training_evidence",
        "frozen_before_evaluation",
        "evaluation_seeds_seen_during_training_or_selection",
    }
    _require_exact_keys(interaction, expected_interaction_keys, "learned interaction artifact")
    selection_trials = interaction["selection_trials"]
    if not isinstance(selection_trials, Sequence) or len(selection_trials) != len(
        config.l2_candidates
    ):
        raise ValueError("learned interaction selection trials are incomplete")
    for expected_l2, trial in zip(config.l2_candidates, selection_trials, strict=True):
        if (
            not isinstance(trial, Mapping)
            or set(trial) != {"l2", "train_loss", "validation_loss"}
            or any(
                type(trial[name]) not in {int, float}
                for name in ("l2", "train_loss", "validation_loss")
            )
            or trial["l2"] != expected_l2
            or not all(
                math.isfinite(float(trial[name])) for name in ("train_loss", "validation_loss")
            )
        ):
            raise ValueError("learned interaction selection trial is malformed")
    selected_trial = min(
        selection_trials,
        key=lambda trial: (float(trial["validation_loss"]), float(trial["l2"])),
    )
    if (
        selected_trial["l2"] != model.selected_l2
        or selected_trial["train_loss"] != model.train_loss
        or selected_trial["validation_loss"] != model.validation_loss
    ):
        raise ValueError("learned interaction hyperparameter selection is not validation-derived")
    training_evidence = interaction["training_evidence"]
    if (
        not isinstance(training_evidence, Mapping)
        or set(training_evidence) != TRAINING_EVIDENCE_FIELDS
        or training_evidence.get("training_action_policy") != TRAINING_ACTION_POLICY
        or training_evidence.get("seed_conditioned_observation_strength") is not True
        or training_evidence.get("train_validation_examples_distinct") is not True
    ):
        raise ValueError("learned interaction training evidence is incomplete")
    for field in ("train_examples_sha256", "validation_examples_sha256"):
        value = training_evidence[field]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError("learned interaction example hash is malformed")
    if (
        training_evidence["train_examples_sha256"]
        == training_evidence["validation_examples_sha256"]
    ):
        raise ValueError("learned interaction train/validation examples are degenerate copies")
    base_config = load_stateful_full_joint_config(root, config.base_route_config)
    neural_model = load_neural_proposal_model(base_config.neural_proposal_model_path)
    proposal_runtime = StatefulFullJointRuntime(
        arm=FullJointArm.MATCHED_FULL_STATE_FACTORIZED,
        config=base_config,
        neural_model=neural_model,
    )
    expected_train_examples = _interaction_examples(
        seeds=config.train_seeds,
        config=config,
        runtime=proposal_runtime,
    )
    expected_validation_examples = _interaction_examples(
        seeds=config.validation_seeds,
        config=config,
        runtime=proposal_runtime,
    )
    expected_training_evidence = _build_training_evidence(
        expected_train_examples,
        expected_validation_examples,
    )
    if (
        dict(training_evidence) != expected_training_evidence
        or model.train_example_count != len(expected_train_examples)
        or model.validation_example_count != len(expected_validation_examples)
    ):
        raise ValueError("learned interaction example evidence is not source-regenerated")
    if (
        interaction.get("frozen_before_evaluation") is not True
        or interaction.get("evaluation_seeds_seen_during_training_or_selection") is not False
    ):
        raise ValueError("learned interaction model was not frozen behind the split firewall")
    closed_loop_runs = result["closed_loop_runs"]
    expected_arm_names = {
        FullJointArm.STATEFUL_FULL_JOINT.value,
        FullJointArm.MATCHED_FULL_STATE_FACTORIZED.value,
    }
    if not isinstance(closed_loop_runs, Mapping) or set(closed_loop_runs) != expected_arm_names:
        raise ValueError("matched closed-loop run matrix is incomplete")
    full_rows = closed_loop_runs[FullJointArm.STATEFUL_FULL_JOINT.value]
    factorized_rows = closed_loop_runs[FullJointArm.MATCHED_FULL_STATE_FACTORIZED.value]
    if (
        not isinstance(full_rows, Sequence)
        or not isinstance(factorized_rows, Sequence)
        or len(full_rows) != len(config.evaluation_seeds)
        or len(factorized_rows) != len(config.evaluation_seeds)
        or not all(isinstance(row, Mapping) for row in (*full_rows, *factorized_rows))
    ):
        raise ValueError("matched closed-loop seed coverage is incomplete")
    for seed, full_row, factorized_row in zip(
        config.evaluation_seeds,
        full_rows,
        factorized_rows,
        strict=True,
    ):
        _verify_closed_loop_run(
            full_row,
            config=config,
            expected_seed=seed,
            expected_arm=FullJointArm.STATEFUL_FULL_JOINT,
            expected_neutralized=None,
        )
        _verify_closed_loop_run(
            factorized_row,
            config=config,
            expected_seed=seed,
            expected_arm=FullJointArm.MATCHED_FULL_STATE_FACTORIZED,
            expected_neutralized=None,
        )
        if full_row["causal_pairing_sha256"] != factorized_row["causal_pairing_sha256"]:
            raise ValueError("matched closed-loop causal pairing differs by arm")

    summaries = result["closed_loop_summaries"]
    expected_summaries = {
        FullJointArm.STATEFUL_FULL_JOINT.value: _summary(full_rows),
        FullJointArm.MATCHED_FULL_STATE_FACTORIZED.value: _summary(factorized_rows),
    }
    if summaries != expected_summaries:
        raise ValueError("matched closed-loop summaries are not run-derived")
    full_summary = expected_summaries[FullJointArm.STATEFUL_FULL_JOINT.value]
    factorized_summary = expected_summaries[FullJointArm.MATCHED_FULL_STATE_FACTORIZED.value]
    expected_difference = {
        "action_regret_per_step": (
            full_summary["action_regret_per_step"] - factorized_summary["action_regret_per_step"]
        ),
        "owner_habit_contamination": (
            full_summary["owner_habit_contamination"]
            - factorized_summary["owner_habit_contamination"]
        ),
    }
    if result["joint_minus_factorized_lower_is_better"] != expected_difference:
        raise ValueError("joint/factorized differences are not summary-derived")
    if result["learned_interaction_utilization"] != _paired_action_diagnostic(
        full_rows,
        factorized_rows,
    ):
        raise ValueError("learned interaction utilization is not trace-derived")

    fairness = result["matched_closed_loop_fairness"]
    expected_fairness = {
        "passed": True,
        "same_initial_hidden_state": True,
        "same_exogenous_event_schedule": True,
        "same_action_outcome_uniforms": True,
        "same_complete_state_access": True,
        "same_particle_budget": True,
        "same_neural_proposal": True,
        "same_learned_interaction_features_and_model_read": True,
        "only_registered_mechanism_difference": (
            "learned_cross_axis_log_potential_vs_zero_coefficient"
        ),
        "post_action_observations_may_diverge_only_after_actions_diverge": True,
    }
    if fairness != expected_fairness:
        raise ValueError("matched closed-loop fairness contract drifted")

    rgrc = result["rgrc_activation_suite"]
    if not isinstance(rgrc, Mapping):
        raise ValueError("RGRC activation suite is missing")
    _verify_rgrc_activation_suite(rgrc, config=config)
    expected_rgrc_pass = bool(
        rgrc["all_required_positive_transitions_observed"]
        and rgrc["all_required_negative_cases_rejected"]
    )
    if result["rgrc_positive_and_negative_activation_passed"] is not expected_rgrc_pass:
        raise ValueError("RGRC positive/negative aggregate is not suite-derived")

    ablation = result["seven_operator_neutralization"]
    expected_operator_names = {operator.value for operator in StructureTwoOperator}
    if (
        not isinstance(ablation, Mapping)
        or set(ablation) != {"policy", "all_seven_neutralizations_completed", "summaries", "runs"}
        or ablation["policy"] != "retain_operator_and_replace_only_effect_with_neutral_element"
        or not isinstance(ablation["summaries"], Mapping)
        or not isinstance(ablation["runs"], Mapping)
        or set(ablation["summaries"]) != expected_operator_names
        or set(ablation["runs"]) != expected_operator_names
    ):
        raise ValueError("seven-operator neutralization matrix is incomplete")
    for operator in StructureTwoOperator:
        rows = ablation["runs"][operator.value]
        if (
            not isinstance(rows, Sequence)
            or len(rows) != len(config.evaluation_seeds)
            or not all(isinstance(row, Mapping) for row in rows)
        ):
            raise ValueError(f"neutralization seed coverage is incomplete: {operator.value}")
        for seed, ablated_row, full_row in zip(
            config.evaluation_seeds,
            rows,
            full_rows,
            strict=True,
        ):
            _verify_closed_loop_run(
                ablated_row,
                config=config,
                expected_seed=seed,
                expected_arm=FullJointArm.STATEFUL_FULL_JOINT,
                expected_neutralized=operator,
            )
            if ablated_row["causal_pairing_sha256"] != full_row["causal_pairing_sha256"]:
                raise ValueError(f"neutralization causal pairing failed: {operator.value}")
        summary = _summary(rows)
        diagnostic = _paired_action_diagnostic(rows, full_rows)
        expected_ablation_summary = {
            "neutralization_policy": (
                "operator_retained_effect_replaced_by_registered_neutral_element"
            ),
            "summary": summary,
            "ablated_minus_full_action_regret_per_step": (
                summary["action_regret_per_step"] - full_summary["action_regret_per_step"]
            ),
            "ablated_minus_full_contamination": (
                summary["owner_habit_contamination"] - full_summary["owner_habit_contamination"]
            ),
            "decision_effect_observed": bool(
                diagnostic["selected_action_disagreement_steps"] > 0
                or diagnostic["max_action_posterior_tv"] > 1e-12
            ),
            "paired_action_diagnostic": diagnostic,
            "operator_retained_in_every_run": all(
                row["all_seven_operators_retained"] for row in rows
            ),
            "all_other_operators_executed_in_every_run": all(
                all(
                    counts["executed_count"] > 0
                    for name, counts in row["operator_counts"].items()
                    if name != operator.value
                )
                for row in rows
            ),
            "neutralization_exercised_in_every_run": all(
                row["neutralization_exercised"] for row in rows
            ),
        }
        if ablation["summaries"][operator.value] != expected_ablation_summary:
            raise ValueError(f"neutralization summary is not run-derived: {operator.value}")
    all_ablation_complete = all(
        row["operator_retained_in_every_run"]
        and row["all_other_operators_executed_in_every_run"]
        and row["neutralization_exercised_in_every_run"]
        for row in ablation["summaries"].values()
    )
    if ablation["all_seven_neutralizations_completed"] is not all_ablation_complete:
        raise ValueError("seven-operator neutralization aggregate is false")

    environment = result["action_responsive_environment"]
    all_rows = [*full_rows, *factorized_rows]
    for rows in ablation["runs"].values():
        all_rows.extend(rows)
    expected_environment = {
        "environment_trajectory_responds_to_route_action": all(
            row["environment_trajectory_responds_to_route_action"]
            and row["post_action_observation_coverage"] == 1.0
            and row["feedback_revision_count"] == config.horizon
            for row in all_rows
        ),
        "post_action_observation_available": True,
        "shared_potential_outcome_randomness": True,
        "action_success_probability": config.action_success_probability,
        "horizon": config.horizon,
        "evaluation_seed_count": len(config.evaluation_seeds),
        "corrected_joint_state_consumed_by_later_actions": all(
            row["corrected_state_consumed_by_later_actions"]
            for row in (*full_rows, *factorized_rows)
        ),
        "claim_scope": "deterministic_D0_simulator_not_real_robot",
    }
    if (
        environment != expected_environment
        or environment["environment_trajectory_responds_to_route_action"] is not True
    ):
        raise ValueError("action-responsive environment claim is not trace-derived")
    if any(
        result[field] is not False
        for field in (
            "all_seven_operator_contributions_established",
            "scientific_superiority_established",
            "real_robot_external_validity_established",
            "independent_custody_established",
            "task_8_formal_passed",
        )
    ):
        raise ValueError("development result promoted a paper-level or external claim")
    expected_trust_paths = {
        "/split_contract/all_splits_disjoint",
        "/learned_cross_axis_interaction/frozen_before_evaluation",
        "/production_system_assembly/single_runtime_object_owns_all_operator_instances",
        "/action_responsive_environment/environment_trajectory_responds_to_route_action",
        "/matched_closed_loop_fairness/passed",
        "/rgrc_positive_and_negative_activation_passed",
        "/seven_operator_neutralization/all_seven_neutralizations_completed",
    }
    trust = result["positive_output_trust_chain"]
    if not isinstance(trust, Mapping) or set(trust) != expected_trust_paths:
        raise ValueError("full scientific loop positive-output trust map is incomplete")
    if fresh_replay:
        fresh = run_full_scientific_loop_development(repository_root=root)
        if content_sha256(result) != content_sha256(fresh):
            raise ValueError("full scientific loop fresh-source replay disagrees")
