"""Task-separated action/utility construct gate for Structure Two Route C.

This is a three-step D0 diagnostic, not a replacement for the frozen Route-C
v0.2 experiment.  It deliberately leaves the old implementation and artifact
untouched while testing the missing construct boundary:

* ``SEARCH`` estimates and inspects the current object location without moving it;
* ``PUT_BACK`` estimates the owner's habit location and is the only action that
  may relocate the object;
* search, put-back, and the narrow non-owner-copy proxy are scored separately;
* no combined utility or long-term product policy is selected here.

The verifier derives every positive criterion from the raw three-step trace and
then performs a fresh deterministic recomputation.  Re-signing a caller-edited
artifact is therefore insufficient to make it pass.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from statistics import mean
from typing import Any, Final
from uuid import UUID, uuid4

from cpswm.system.evaluation_operations.structure_two_full_scientific_loop import (
    ActionResponsiveEnvironment,
    ClosedLoopTruth,
    FullScientificLoopConfig,
    LearnedInteractionRuntime,
    load_full_scientific_loop_config,
    train_cross_axis_interactions,
)
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointArm,
    FullJointObservation,
    _normalize,
    load_neural_proposal_model,
    load_stateful_full_joint_config,
)
from cpswm.system.reproducibility import content_sha256, content_uuid

PROTOCOL_ID: Final = "structure-two-action-utility-construct-gate@0.1-development"
SCHEMA_VERSION: Final = "0.1.0"
STATUS: Final = "D0_DIAGNOSTIC_ONLY"
DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_action_utility_construct_gate_v0_1.json"
)
DEFAULT_RUNNER: Final = Path(
    "apps/evaluation_runner/run_structure_two_action_utility_construct_gate.py"
)
DEFAULT_OUTPUT: Final = Path(
    "benchmarks/structure_two/structure_two_action_utility_construct_gate_v0_1.json"
)
CLAIM_BOUNDARY: Final = (
    "This three-step D0 diagnostic establishes typed and task-separated SEARCH and PUT_BACK "
    "execution, trace-derived separate metrics, at least one successful non-noop state "
    "transition, phase-guarded call order, runtime-local command freshness, and "
    "source-recomputed single-head sensitivity "
    "controls. The controls establish metric wiring responsiveness, not learned-policy "
    "non-degeneracy or task quality. It does not establish append-only or independently "
    "custodied history, select long-term product action semantics, establish production-runtime "
    "identity, measure a combined action utility, establish long-term memory contamination, "
    "or support scientific superiority."
)
COMBINED_UTILITY_STATUS: Final = "UNRESOLVED_NOT_AGGREGATED"
DECISION_PROTOCOL: Final = "two_task_heads_precommitted_from_same_predecision_snapshot"
SENSITIVITY_PROTOCOL: Final = "paired_same_seed_same_history_single_head_rank_intervention"
EXPECTED_PHASE_GUARD_EVENTS: Final = (
    "visible_observation_issued",
    "typed_actions_committed",
    "search_executed",
    "put_back_executed",
    "truth_disclosed",
    "feedback_issued",
)
EXPECTED_ACTION_SEMANTICS: Final = {
    "decision_protocol": DECISION_PROTOCOL,
    "search_target_semantics": "current_object_location",
    "search_readout_source": "robot_visible_current_location_posterior",
    "search_environment_effect": "inspection_only_object_location_immutable",
    "search_metric": "normalized_extra_inspection_regret",
    "put_back_target_semantics": "owner_habit_location",
    "put_back_readout_source": (
        "owner_target_active_regime_rb_with_uniform_instantaneous_base_and_rgrc"
    ),
    "put_back_environment_effect": "relocate_object_on_success",
    "put_back_metric": "zero_one_owner_habit_error",
    "contamination_metric": "non_owner_copy_putback_proxy_only",
    "combined_utility_status": COMBINED_UTILITY_STATUS,
    "truth_release_policy": ("after_both_typed_action_commits_and_consequence_before_utility"),
    "phase_control_claim": "source_recomputed_phase_guarded_call_order_not_independent_custody",
    "runtime_freshness_claim": (
        "instance_local_single_use_capability_not_serialized_or_independent_custody"
    ),
    "sensitivity_control_protocol": SENSITIVITY_PROTOCOL,
    "long_term_product_action_semantics_selected": False,
}
EXPECTED_LEGACY_COMPATIBILITY: Final = {
    "old_module_mutation_forbidden": True,
    "old_config_mutation_forbidden": True,
    "old_artifact_mutation_forbidden": True,
}


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{name} schema drift or hidden field")


def _strict_int(value: Any, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be a JSON integer")
    return value


def _validate_sha256(value: str, name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _reject_nonfinite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite number at {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_nonfinite(item, f"{path}/{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _reject_nonfinite(item, f"{path}/{index}")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ActionUtilityConstructGateConfig:
    base_full_loop_config: Path
    seed: int
    step_count: int
    expected_non_owner_step_index: int
    sensitivity_control_step_index: int
    minimum_selected_location_disagreement_steps: int
    minimum_successful_non_noop_put_back_transitions: int


def load_action_utility_construct_gate_config(
    repository_root: Path,
    path: Path = DEFAULT_CONFIG,
) -> ActionUtilityConstructGateConfig:
    payload = json.loads((repository_root / path).read_text(encoding="utf-8"))
    _require_exact_keys(
        payload,
        {
            "schema_version",
            "protocol_id",
            "status",
            "base_full_loop_config",
            "probe",
            "action_semantics",
            "legacy_v0_2_compatibility",
            "claim_boundary",
        },
        "action-utility construct configuration",
    )
    if (
        payload["schema_version"] != SCHEMA_VERSION
        or payload["protocol_id"] != PROTOCOL_ID
        or payload["status"] != STATUS
    ):
        raise ValueError("action-utility construct protocol identity drifted")
    if payload["action_semantics"] != EXPECTED_ACTION_SEMANTICS:
        raise ValueError("action-utility construct semantics drifted")
    if payload["legacy_v0_2_compatibility"] != EXPECTED_LEGACY_COMPATIBILITY:
        raise ValueError("legacy v0.2 compatibility policy drifted")
    if payload["claim_boundary"] != CLAIM_BOUNDARY:
        raise ValueError("action-utility construct claim boundary drifted")

    probe = payload["probe"]
    if not isinstance(probe, Mapping):
        raise ValueError("action-utility construct probe must be an object")
    _require_exact_keys(
        probe,
        {
            "seed",
            "step_count",
            "expected_non_owner_step_index",
            "sensitivity_control_step_index",
            "minimum_selected_location_disagreement_steps",
            "minimum_successful_non_noop_put_back_transitions",
        },
        "action-utility construct probe",
    )
    seed = _strict_int(probe["seed"], "probe seed")
    step_count = _strict_int(probe["step_count"], "probe step count")
    non_owner_step = _strict_int(probe["expected_non_owner_step_index"], "expected non-owner step")
    sensitivity_step = _strict_int(
        probe["sensitivity_control_step_index"], "sensitivity control step"
    )
    minimum_location_disagreement = _strict_int(
        probe["minimum_selected_location_disagreement_steps"],
        "minimum selected-location disagreement steps",
    )
    minimum_transition = _strict_int(
        probe["minimum_successful_non_noop_put_back_transitions"],
        "minimum successful non-noop transitions",
    )
    if seed < 0 or step_count != 3:
        raise ValueError("the D0 construct probe must contain exactly three deterministic steps")
    if not 0 <= non_owner_step < step_count:
        raise ValueError("expected non-owner step is outside the construct probe")
    if not 0 <= sensitivity_step < step_count:
        raise ValueError("sensitivity control step is outside the construct probe")
    if minimum_location_disagreement < 1 or minimum_transition < 1:
        raise ValueError("construct gate minima must be positive")

    base_path = Path(str(payload["base_full_loop_config"]))
    resolved = (repository_root / base_path).resolve()
    if (
        resolved == repository_root.resolve()
        or base_path.is_absolute()
        or ".." in base_path.parts
        or not resolved.is_relative_to(repository_root.resolve())
        or not resolved.is_file()
    ):
        raise ValueError("base full-loop configuration must be a repository-local file")
    return ActionUtilityConstructGateConfig(
        base_full_loop_config=base_path,
        seed=seed,
        step_count=step_count,
        expected_non_owner_step_index=non_owner_step,
        sensitivity_control_step_index=sensitivity_step,
        minimum_selected_location_disagreement_steps=minimum_location_disagreement,
        minimum_successful_non_noop_put_back_transitions=minimum_transition,
    )


class ConstructActionKind(StrEnum):
    SEARCH = "search"
    PUT_BACK = "put_back"


@dataclass(frozen=True, slots=True)
class LocationProbability:
    location_id: UUID
    probability: float

    def __post_init__(self) -> None:
        if not isinstance(self.location_id, UUID):
            raise ValueError("location probability requires a UUID")
        if (
            isinstance(self.probability, bool)
            or not isinstance(self.probability, (float, int))
            or not math.isfinite(float(self.probability))
            or not 0.0 <= float(self.probability) <= 1.0
        ):
            raise ValueError("location probability must be finite and lie in [0, 1]")


@dataclass(frozen=True, slots=True)
class TypedRouteCAction:
    action_id: UUID
    kind: ConstructActionKind
    target_object_id: UUID
    location_id: UUID
    decision_id: UUID
    information_set_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ConstructActionKind):
            raise ValueError("Route-C action kind must be typed")
        if any(
            not isinstance(value, UUID)
            for value in (self.action_id, self.target_object_id, self.location_id, self.decision_id)
        ):
            raise ValueError("Route-C action identifiers must be UUIDs")
        _validate_sha256(self.information_set_sha256, "action information set")
        if self.action_id != self.canonical_action_id:
            raise ValueError("Route-C action ID is not derived from its typed semantics")

    @property
    def canonical_action_id(self) -> UUID:
        return content_uuid(
            "structure-two-action-utility-typed-command",
            {
                "kind": self.kind.value,
                "target_object_id": str(self.target_object_id),
                "location_id": str(self.location_id),
                "decision_id": str(self.decision_id),
                "information_set_sha256": self.information_set_sha256,
            },
        )

    @classmethod
    def build(
        cls,
        *,
        kind: ConstructActionKind,
        target_object_id: UUID,
        location_id: UUID,
        decision_id: UUID,
        information_set_sha256: str,
    ) -> TypedRouteCAction:
        provisional = cls.__new__(cls)
        object.__setattr__(provisional, "kind", kind)
        object.__setattr__(provisional, "target_object_id", target_object_id)
        object.__setattr__(provisional, "location_id", location_id)
        object.__setattr__(provisional, "decision_id", decision_id)
        object.__setattr__(provisional, "information_set_sha256", information_set_sha256)
        action_id = provisional.canonical_action_id
        return cls(
            action_id=action_id,
            kind=kind,
            target_object_id=target_object_id,
            location_id=location_id,
            decision_id=decision_id,
            information_set_sha256=information_set_sha256,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "action_id": str(self.action_id),
            "kind": self.kind.value,
            "target_object_id": str(self.target_object_id),
            "location_id": str(self.location_id),
            "decision_id": str(self.decision_id),
            "information_set_sha256": self.information_set_sha256,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TypedRouteCAction:
        _require_exact_keys(
            payload,
            {
                "action_id",
                "kind",
                "target_object_id",
                "location_id",
                "decision_id",
                "information_set_sha256",
            },
            "typed Route-C action",
        )
        if not all(
            isinstance(payload[field], str)
            for field in (
                "action_id",
                "kind",
                "target_object_id",
                "location_id",
                "decision_id",
                "information_set_sha256",
            )
        ):
            raise ValueError("typed Route-C action fields must be canonical strings")
        try:
            action_id = UUID(payload["action_id"])
            target_object_id = UUID(payload["target_object_id"])
            location_id = UUID(payload["location_id"])
            decision_id = UUID(payload["decision_id"])
            if any(
                raw != str(parsed)
                for raw, parsed in (
                    (payload["action_id"], action_id),
                    (payload["target_object_id"], target_object_id),
                    (payload["location_id"], location_id),
                    (payload["decision_id"], decision_id),
                )
            ):
                raise ValueError("typed Route-C action UUID is noncanonical")
            return cls(
                action_id=action_id,
                kind=ConstructActionKind(payload["kind"]),
                target_object_id=target_object_id,
                location_id=location_id,
                decision_id=decision_id,
                information_set_sha256=payload["information_set_sha256"],
            )
        except (TypeError, ValueError) as error:
            raise ValueError("typed Route-C action is malformed") from error


def _probability_items(values: Mapping[UUID, float]) -> tuple[LocationProbability, ...]:
    normalized = _normalize(values)
    return tuple(
        LocationProbability(location, normalized[location])
        for location in sorted(normalized, key=str)
    )


def _probability_map(items: Sequence[LocationProbability]) -> dict[UUID, float]:
    result = {item.location_id: float(item.probability) for item in items}
    if len(result) != len(items) or not result:
        raise ValueError("location distribution support is empty or duplicated")
    if not math.isclose(sum(result.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("location distribution must sum to one")
    return result


def _rank(values: Mapping[UUID, float]) -> tuple[UUID, ...]:
    return tuple(sorted(values, key=lambda key: (-values[key], str(key))))


def _deterministic_run_execution_id(*, seed: int, role: str) -> UUID:
    return content_uuid(
        "structure-two-action-utility-run-execution",
        {"protocol_id": PROTOCOL_ID, "seed": seed, "role": role},
    )


def _observation_commitment_sha256(
    *,
    run_execution_id: UUID,
    step_index: int,
    source_update_id: UUID,
    visible_observation: Mapping[str, Any],
) -> str:
    return content_sha256(
        {
            "protocol_id": PROTOCOL_ID,
            "run_execution_id": str(run_execution_id),
            "step_index": step_index,
            "source_update_id": str(source_update_id),
            "visible_observation": dict(visible_observation),
        }
    )


def _information_set_sha256(
    *,
    run_execution_id: UUID,
    step_index: int,
    source_update_id: UUID,
    observation_commitment_sha256: str,
    belief_state_sha256: str,
) -> str:
    return content_sha256(
        {
            "protocol_id": PROTOCOL_ID,
            "run_execution_id": str(run_execution_id),
            "step_index": step_index,
            "source_update_id": str(source_update_id),
            "observation_commitment_sha256": observation_commitment_sha256,
            "belief_state_sha256": belief_state_sha256,
        }
    )


def _task_head_decision_id(
    *,
    kind: ConstructActionKind,
    run_execution_id: UUID,
    step_index: int,
    source_update_id: UUID,
    information_set_sha256: str,
) -> UUID:
    return content_uuid(
        f"structure-two-action-utility-{kind.value}-decision",
        {
            "run_execution_id": str(run_execution_id),
            "step": step_index,
            "source_update_id": str(source_update_id),
            "information_set": information_set_sha256,
        },
    )


@dataclass(frozen=True, slots=True)
class TaskSeparatedActionReadout:
    step_index: int
    run_execution_id: UUID
    source_update_id: UUID
    observation_commitment_sha256: str
    belief_state_sha256: str
    information_set_sha256: str
    search_distribution: tuple[LocationProbability, ...]
    put_back_distribution: tuple[LocationProbability, ...]
    search_plan: tuple[TypedRouteCAction, ...]
    put_back_action: TypedRouteCAction
    truth_accessed_before_action_commit: bool = False

    def __post_init__(self) -> None:
        if type(self.step_index) is not int or self.step_index < 0:
            raise ValueError("readout step index must be a non-negative integer")
        if not isinstance(self.run_execution_id, UUID) or not isinstance(
            self.source_update_id, UUID
        ):
            raise ValueError("readout execution and source identities must be UUIDs")
        _validate_sha256(self.observation_commitment_sha256, "observation commitment")
        _validate_sha256(self.belief_state_sha256, "readout belief state")
        _validate_sha256(self.information_set_sha256, "readout information set")
        if self.truth_accessed_before_action_commit:
            raise ValueError("evaluator truth cannot be read before committing actions")
        search = _probability_map(self.search_distribution)
        put_back = _probability_map(self.put_back_distribution)
        if set(search) != set(put_back):
            raise ValueError("search and put-back must share the registered location support")
        if not self.search_plan or len(self.search_plan) != len(search):
            raise ValueError("search plan must exhaustively cover its distribution")
        if tuple(action.location_id for action in self.search_plan) != _rank(search):
            raise ValueError("typed search plan is not the deterministic search readout")
        if any(action.kind is not ConstructActionKind.SEARCH for action in self.search_plan):
            raise ValueError("search plan contains a non-search action")
        if len({action.location_id for action in self.search_plan}) != len(self.search_plan):
            raise ValueError("search plan contains a duplicate location")
        if self.put_back_action.kind is not ConstructActionKind.PUT_BACK:
            raise ValueError("put-back head emitted the wrong typed action")
        if self.put_back_action.location_id != _rank(put_back)[0]:
            raise ValueError("typed put-back action is not the deterministic put-back readout")
        actions = (*self.search_plan, self.put_back_action)
        expected_search_decision = _task_head_decision_id(
            kind=ConstructActionKind.SEARCH,
            run_execution_id=self.run_execution_id,
            step_index=self.step_index,
            source_update_id=self.source_update_id,
            information_set_sha256=self.information_set_sha256,
        )
        expected_put_back_decision = _task_head_decision_id(
            kind=ConstructActionKind.PUT_BACK,
            run_execution_id=self.run_execution_id,
            step_index=self.step_index,
            source_update_id=self.source_update_id,
            information_set_sha256=self.information_set_sha256,
        )
        if any(action.decision_id != expected_search_decision for action in self.search_plan):
            raise ValueError("search actions do not carry the canonical execution-bound decision")
        if self.put_back_action.decision_id != expected_put_back_decision:
            raise ValueError(
                "put-back action does not carry the canonical execution-bound decision"
            )
        if any(action.information_set_sha256 != self.information_set_sha256 for action in actions):
            raise ValueError("typed actions are not bound to the readout information set")
        if len({action.target_object_id for action in actions}) != 1:
            raise ValueError("task heads target different object instances")

    @property
    def selected_search_action(self) -> TypedRouteCAction:
        return self.search_plan[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "run_execution_id": str(self.run_execution_id),
            "source_update_id": str(self.source_update_id),
            "observation_commitment_sha256": self.observation_commitment_sha256,
            "belief_state_sha256": self.belief_state_sha256,
            "information_set_sha256": self.information_set_sha256,
            "search_distribution": {
                str(item.location_id): item.probability for item in self.search_distribution
            },
            "put_back_distribution": {
                str(item.location_id): item.probability for item in self.put_back_distribution
            },
            "search_plan": [action.to_dict() for action in self.search_plan],
            "selected_search_action": self.selected_search_action.to_dict(),
            "selected_put_back_action": self.put_back_action.to_dict(),
            "truth_accessed_before_action_commit": self.truth_accessed_before_action_commit,
        }


def _visible_observation_payload(observation: FullJointObservation) -> dict[str, Any]:
    return {
        "source_update_id": str(observation.source_update_id),
        "evidence_cluster_id": str(observation.evidence_cluster_id),
        "owner_actor_key": observation.owner_actor_key,
        "actor_posterior": dict(observation.actor_posterior),
        "mechanism_posterior": {
            key.value: value for key, value in observation.mechanism_posterior.items()
        },
        "ordered_role_posterior": dict(observation.ordered_role_posterior),
        "identity_target_probability": observation.identity_target_probability,
        "cause_posterior": {key.value: value for key, value in observation.cause_posterior.items()},
        "regime_change_probability": observation.regime_change_probability,
        "active_regime": observation.active_regime,
        "observed_location_id": str(observation.observed_location_id),
        "base_location_distribution": {
            str(key): value for key, value in observation.base_location_distribution.items()
        },
        "known_location_ids": [str(value) for value in observation.known_location_ids],
        "unresolved_probability": observation.unresolved_probability,
    }


class TaskSeparatedLearnedInteractionRuntime(LearnedInteractionRuntime):
    """Read the existing Route-C belief through two explicit task heads."""

    def task_separated_readout(
        self,
        *,
        target_object_id: UUID,
        external_step_index: int,
        run_execution_id: UUID,
    ) -> TaskSeparatedActionReadout:
        observation = self._last_observation
        if observation is None:
            raise ValueError("task-separated readout requested before Route-C revision")
        if external_step_index != self.step_index - 1:
            raise ValueError("external and runtime step indices disagree")

        visible_observation = _visible_observation_payload(observation)
        observation_commitment = _observation_commitment_sha256(
            run_execution_id=run_execution_id,
            step_index=external_step_index,
            source_update_id=observation.source_update_id,
            visible_observation=visible_observation,
        )
        belief_state_sha256 = self._state_sha256()
        information_set_sha256 = _information_set_sha256(
            run_execution_id=run_execution_id,
            step_index=external_step_index,
            source_update_id=observation.source_update_id,
            observation_commitment_sha256=observation_commitment,
            belief_state_sha256=belief_state_sha256,
        )
        search = _normalize(observation.base_location_distribution)
        uniform = dict.fromkeys(
            observation.known_location_ids,
            1.0 / len(observation.known_location_ids),
        )
        habit_only_observation = replace(
            observation,
            base_location_distribution=uniform,
        )
        put_back = self._posterior_action_distribution(
            habit_only_observation,
            include_ledger=True,
        )
        search_decision = _task_head_decision_id(
            kind=ConstructActionKind.SEARCH,
            run_execution_id=run_execution_id,
            step_index=external_step_index,
            source_update_id=observation.source_update_id,
            information_set_sha256=information_set_sha256,
        )
        put_back_decision = _task_head_decision_id(
            kind=ConstructActionKind.PUT_BACK,
            run_execution_id=run_execution_id,
            step_index=external_step_index,
            source_update_id=observation.source_update_id,
            information_set_sha256=information_set_sha256,
        )
        search_plan = tuple(
            TypedRouteCAction.build(
                kind=ConstructActionKind.SEARCH,
                target_object_id=target_object_id,
                location_id=location,
                decision_id=search_decision,
                information_set_sha256=information_set_sha256,
            )
            for location in _rank(search)
        )
        put_back_action = TypedRouteCAction.build(
            kind=ConstructActionKind.PUT_BACK,
            target_object_id=target_object_id,
            location_id=_rank(put_back)[0],
            decision_id=put_back_decision,
            information_set_sha256=information_set_sha256,
        )
        return TaskSeparatedActionReadout(
            step_index=external_step_index,
            run_execution_id=run_execution_id,
            source_update_id=observation.source_update_id,
            observation_commitment_sha256=observation_commitment,
            belief_state_sha256=belief_state_sha256,
            information_set_sha256=information_set_sha256,
            search_distribution=_probability_items(search),
            put_back_distribution=_probability_items(put_back),
            search_plan=search_plan,
            put_back_action=put_back_action,
        )


class TaskSeparatedActionEnvironment:
    """Phase-checked adapter that prevents evaluator truth leaking into readout."""

    def __init__(
        self,
        *,
        seed: int,
        config: FullScientificLoopConfig,
        run_execution_id: UUID | None = None,
    ) -> None:
        self._environment = ActionResponsiveEnvironment(seed=seed, config=config)
        self.run_execution_id = run_execution_id or uuid4()
        if not isinstance(self.run_execution_id, UUID):
            raise ValueError("environment run execution ID must be a UUID")
        self.target_object_id = content_uuid(
            "structure-two-action-utility-target-object", {"seed": seed}
        )
        self._instance_capability_nonce = uuid4()
        self._phase = "ready"
        self._observation: FullJointObservation | None = None
        self._observation_commitment_sha256: str | None = None
        self._truth: ClosedLoopTruth | None = None
        self._readout: TaskSeparatedActionReadout | None = None
        self._issued_readout: TaskSeparatedActionReadout | None = None
        self._issued_readout_digest: str | None = None
        self._issued_capability_digest: str | None = None
        self._put_back_transition: dict[str, Any] | None = None
        self._phase_guard_events: list[str] = []

    @property
    def locations(self) -> tuple[UUID, ...]:
        return self._environment.locations

    @property
    def step_index(self) -> int:
        return self._environment.step_index

    @property
    def phase_guard_events(self) -> tuple[str, ...]:
        """Return source-generated call-order evidence for the current step.

        This is diagnostic control-flow evidence only; it is not an external or
        independently custodied audit log.
        """

        return tuple(self._phase_guard_events)

    def observe_visible(self) -> FullJointObservation:
        if self._phase != "ready":
            raise ValueError("visible observation requested in an invalid environment phase")
        observation, truth = self._environment.observe()
        self._observation = observation
        self._observation_commitment_sha256 = _observation_commitment_sha256(
            run_execution_id=self.run_execution_id,
            step_index=self.step_index,
            source_update_id=observation.source_update_id,
            visible_observation=_visible_observation_payload(observation),
        )
        self._truth = truth
        self._readout = None
        self._issued_readout = None
        self._issued_readout_digest = None
        self._issued_capability_digest = None
        self._put_back_transition = None
        self._phase_guard_events = ["visible_observation_issued"]
        self._phase = "observed"
        return observation

    def _validate_current_readout(self, readout: TaskSeparatedActionReadout) -> None:
        if self._observation is None or self._observation_commitment_sha256 is None:
            raise ValueError("no authoritative visible observation is registered")
        if readout.step_index != self.step_index:
            raise ValueError("action readout belongs to another environment step")
        if readout.run_execution_id != self.run_execution_id:
            raise ValueError("action readout belongs to another environment execution")
        if readout.source_update_id != self._observation.source_update_id:
            raise ValueError("action readout belongs to another source update")
        if readout.observation_commitment_sha256 != self._observation_commitment_sha256:
            raise ValueError("action readout does not bind the current visible observation")
        expected_information_set = _information_set_sha256(
            run_execution_id=self.run_execution_id,
            step_index=self.step_index,
            source_update_id=self._observation.source_update_id,
            observation_commitment_sha256=self._observation_commitment_sha256,
            belief_state_sha256=readout.belief_state_sha256,
        )
        if readout.information_set_sha256 != expected_information_set:
            raise ValueError("action readout information set is not current and canonical")
        expected_search_decision = _task_head_decision_id(
            kind=ConstructActionKind.SEARCH,
            run_execution_id=self.run_execution_id,
            step_index=self.step_index,
            source_update_id=self._observation.source_update_id,
            information_set_sha256=expected_information_set,
        )
        expected_put_back_decision = _task_head_decision_id(
            kind=ConstructActionKind.PUT_BACK,
            run_execution_id=self.run_execution_id,
            step_index=self.step_index,
            source_update_id=self._observation.source_update_id,
            information_set_sha256=expected_information_set,
        )
        if any(action.decision_id != expected_search_decision for action in readout.search_plan):
            raise ValueError("search action decision is not current and canonical")
        if readout.put_back_action.decision_id != expected_put_back_decision:
            raise ValueError("put-back action decision is not current and canonical")
        actions = (*readout.search_plan, readout.put_back_action)
        if any(action.target_object_id != self.target_object_id for action in actions):
            raise ValueError("typed action targets another object")
        if any(action.information_set_sha256 != expected_information_set for action in actions):
            raise ValueError("typed action carries a stale information set")
        if {action.location_id for action in readout.search_plan} != set(self.locations):
            raise ValueError("typed search plan changed the environment location support")
        if readout.put_back_action.location_id not in self.locations:
            raise ValueError("typed put-back action names an unknown location")

    def issue_runtime_readout(
        self,
        runtime: TaskSeparatedLearnedInteractionRuntime,
        *,
        intervention_head: ConstructActionKind | None = None,
    ) -> TaskSeparatedActionReadout:
        """Mint one single-use, instance-local command capability.

        The private capability is deliberately absent from serialized evidence.
        It proves only live runtime-local issuance, not independent custody.
        """

        if self._phase != "observed" or self._observation is None:
            raise ValueError("runtime readout must be issued for the current visible observation")
        if type(runtime) is not TaskSeparatedLearnedInteractionRuntime:
            raise ValueError("readout issuer requires the registered task-separated runtime")
        if runtime._last_observation is not self._observation:
            raise ValueError("runtime was not revised from this environment observation instance")
        if runtime.step_index - 1 != self.step_index:
            raise ValueError("runtime revision is not current for this environment step")
        if self._issued_readout is not None:
            raise ValueError("a runtime readout was already issued for this observation")
        readout = runtime.task_separated_readout(
            target_object_id=self.target_object_id,
            external_step_index=self.step_index,
            run_execution_id=self.run_execution_id,
        )
        if intervention_head is not None:
            readout = _intervene_on_one_task_head(readout, head=intervention_head)
        self._validate_current_readout(readout)
        readout_digest = content_sha256(readout.to_dict())
        self._issued_readout = readout
        self._issued_readout_digest = readout_digest
        self._issued_capability_digest = content_sha256(
            {
                "instance_capability_nonce": str(self._instance_capability_nonce),
                "run_execution_id": str(self.run_execution_id),
                "step_index": self.step_index,
                "source_update_id": str(self._observation.source_update_id),
                "observation_identity": id(self._observation),
                "readout_identity": id(readout),
                "readout_digest": readout_digest,
            }
        )
        return readout

    def commit_actions(self, readout: TaskSeparatedActionReadout) -> None:
        if self._phase != "observed" or self._observation is None:
            raise ValueError("actions must be committed immediately after a visible observation")
        if not isinstance(readout, TaskSeparatedActionReadout):
            raise ValueError("environment accepts only a typed task-separated readout")
        self._validate_current_readout(readout)
        if (
            readout is not self._issued_readout
            or self._issued_readout_digest is None
            or self._issued_capability_digest is None
            or content_sha256(readout.to_dict()) != self._issued_readout_digest
        ):
            raise ValueError("action readout lacks the current single-use runtime capability")
        expected_capability = content_sha256(
            {
                "instance_capability_nonce": str(self._instance_capability_nonce),
                "run_execution_id": str(self.run_execution_id),
                "step_index": self.step_index,
                "source_update_id": str(self._observation.source_update_id),
                "observation_identity": id(self._observation),
                "readout_identity": id(readout),
                "readout_digest": self._issued_readout_digest,
            }
        )
        if self._issued_capability_digest != expected_capability:
            raise ValueError("runtime readout capability is stale or belongs to another instance")
        self._readout = readout
        self._issued_readout = None
        self._issued_readout_digest = None
        self._issued_capability_digest = None
        self._phase_guard_events.append("typed_actions_committed")
        self._phase = "actions_committed"

    def execute_search(self) -> dict[str, Any]:
        if self._phase != "actions_committed" or self._readout is None:
            raise ValueError("search requires both task-head actions to be precommitted")
        assert self._truth is not None
        before = self._environment.object_location
        truth_location = self._truth.object_location
        plan = self._readout.search_plan
        found_index = next(
            index for index, action in enumerate(plan) if action.location_id == truth_location
        )
        executed = plan[: found_index + 1]
        receipt = {
            "step_index": self.step_index,
            "planned_action_ids": [str(action.action_id) for action in plan],
            "executed_action_ids": [str(action.action_id) for action in executed],
            "inspected_location_ids": [str(action.location_id) for action in executed],
            "target_found": True,
            "inspection_count": len(executed),
            "pre_search_object_location": str(before),
            "post_search_object_location": str(self._environment.object_location),
            "object_state_changed": before != self._environment.object_location,
            "environment_step_advanced": False,
        }
        self._phase_guard_events.append("search_executed")
        self._phase = "search_executed"
        return receipt

    def execute_put_back(self) -> dict[str, Any]:
        if self._phase != "search_executed" or self._readout is None:
            raise ValueError("put-back must execute after the committed search plan")
        action = self._readout.put_back_action
        raw = self._environment.execute(action.location_id)
        transition = {
            "step_index": raw["step_index"],
            "typed_action": action.to_dict(),
            "pre_action_location": raw["pre_action_location"],
            "attempted_location": str(action.location_id),
            "action_success_draw": raw["action_success_draw"],
            "action_success": raw["action_success"],
            "post_action_location": raw["post_action_location"],
            "commanded_non_noop": raw["pre_action_location"] != str(action.location_id),
            "object_state_changed": (raw["pre_action_location"] != raw["post_action_location"]),
            "counterfactual_action": raw["counterfactual_action"],
            "counterfactual_post_action_location": raw["counterfactual_post_action_location"],
            "counterfactual_action_sensitivity": raw["counterfactual_action_sensitivity"],
            "potential_outcome_randomness_key": raw["potential_outcome_randomness_key"],
            "post_action_observation_available": raw["post_action_observation_available"],
        }
        self._put_back_transition = transition
        self._phase_guard_events.append("put_back_executed")
        self._phase = "consequence_observed"
        return transition

    def disclose_truth(self) -> ClosedLoopTruth:
        if self._phase != "consequence_observed" or self._truth is None:
            raise ValueError("evaluator truth is available only after action consequence")
        self._phase_guard_events.append("truth_disclosed")
        self._phase = "truth_disclosed"
        return self._truth

    def feedback(self) -> Any:
        if (
            self._phase != "truth_disclosed"
            or self._observation is None
            or self._truth is None
            or self._put_back_transition is None
        ):
            raise ValueError("feedback requires a disclosed post-action truth")
        feedback = self._environment.feedback(
            self._observation,
            self._truth,
            self._put_back_transition,
        )
        self._phase_guard_events.append("feedback_issued")
        self._phase = "ready"
        return feedback


def _truth_dict(truth: ClosedLoopTruth) -> dict[str, Any]:
    return {
        "step_index": truth.step_index,
        "actor": truth.actor,
        "owner_actor_key": "owner",
        "owner_habit_location": str(truth.owner_habit_location),
        "object_location_before_action": str(truth.object_location),
        "external_event": truth.external_event,
    }


def _derive_separate_metrics(
    *,
    readout: TaskSeparatedActionReadout,
    observation: FullJointObservation,
    search_receipt: Mapping[str, Any],
    put_back_transition: Mapping[str, Any],
    truth: ClosedLoopTruth,
) -> dict[str, Any]:
    search_order = tuple(action.location_id for action in readout.search_plan)
    object_rank = search_order.index(truth.object_location)
    selected_put_back = readout.put_back_action.location_id
    return {
        "search_regret": object_rank / max(1, len(search_order) - 1),
        "put_back_error": float(selected_put_back != truth.owner_habit_location),
        "non_owner_copy_putback_proxy": float(
            truth.actor != observation.owner_actor_key
            and selected_put_back == truth.object_location
            and selected_put_back != truth.owner_habit_location
        ),
        "put_back_execution_success": put_back_transition["action_success"],
        "put_back_commanded_non_noop": put_back_transition["commanded_non_noop"],
        "put_back_object_state_changed": put_back_transition["object_state_changed"],
        "post_action_goal_satisfied": (
            put_back_transition["post_action_location"] == str(truth.owner_habit_location)
        ),
        "search_inspection_count": search_receipt["inspection_count"],
    }


def _artifact_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Drop the redundant inspection count from the per-step metric payload."""

    return {key: value for key, value in metrics.items() if key != "search_inspection_count"}


def _put_back_transition_effect(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Compare physical effects while ignoring execution-scoped action identity."""

    return {key: value for key, value in payload.items() if key != "typed_action"}


def _search_execution_effect(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Compare inspections while ignoring execution-scoped typed action IDs."""

    return {
        key: value
        for key, value in payload.items()
        if key not in {"planned_action_ids", "executed_action_ids"}
    }


def _move_distribution_top(
    items: Sequence[LocationProbability],
    *,
    new_top: UUID,
) -> tuple[LocationProbability, ...]:
    """Preserve a score multiset while assigning its unique maximum to ``new_top``."""

    values = _probability_map(items)
    if new_top not in values:
        raise ValueError("ranking intervention names an unknown location")
    sorted_scores = sorted(values.values(), reverse=True)
    if len(sorted_scores) < 2 or math.isclose(
        sorted_scores[0], sorted_scores[1], rel_tol=0.0, abs_tol=1e-12
    ):
        raise ValueError("ranking intervention requires a unique pre-intervention maximum")
    ordered_locations = (
        new_top,
        *sorted((location for location in values if location != new_top), key=str),
    )
    moved = dict(zip(ordered_locations, sorted_scores, strict=True))
    return tuple(
        LocationProbability(location, moved[location]) for location in sorted(moved, key=str)
    )


def _intervene_on_one_task_head(
    readout: TaskSeparatedActionReadout,
    *,
    head: ConstructActionKind,
) -> TaskSeparatedActionReadout:
    if head is ConstructActionKind.SEARCH:
        baseline_top = readout.selected_search_action.location_id
        new_top = next(
            action.location_id
            for action in readout.search_plan
            if action.location_id != baseline_top
        )
        search_distribution = _move_distribution_top(
            readout.search_distribution,
            new_top=new_top,
        )
        search_decision = _task_head_decision_id(
            kind=ConstructActionKind.SEARCH,
            run_execution_id=readout.run_execution_id,
            step_index=readout.step_index,
            source_update_id=readout.source_update_id,
            information_set_sha256=readout.information_set_sha256,
        )
        search_plan = tuple(
            TypedRouteCAction.build(
                kind=ConstructActionKind.SEARCH,
                target_object_id=readout.put_back_action.target_object_id,
                location_id=location,
                decision_id=search_decision,
                information_set_sha256=readout.information_set_sha256,
            )
            for location in _rank(_probability_map(search_distribution))
        )
        return replace(
            readout,
            search_distribution=search_distribution,
            search_plan=search_plan,
        )
    if head is ConstructActionKind.PUT_BACK:
        search_top = readout.selected_search_action.location_id
        baseline_top = readout.put_back_action.location_id
        new_top = next(
            action.location_id
            for action in readout.search_plan
            if action.location_id not in {search_top, baseline_top}
        )
        put_back_distribution = _move_distribution_top(
            readout.put_back_distribution,
            new_top=new_top,
        )
        put_back_decision = _task_head_decision_id(
            kind=ConstructActionKind.PUT_BACK,
            run_execution_id=readout.run_execution_id,
            step_index=readout.step_index,
            source_update_id=readout.source_update_id,
            information_set_sha256=readout.information_set_sha256,
        )
        put_back_action = TypedRouteCAction.build(
            kind=ConstructActionKind.PUT_BACK,
            target_object_id=readout.put_back_action.target_object_id,
            location_id=new_top,
            decision_id=put_back_decision,
            information_set_sha256=readout.information_set_sha256,
        )
        return replace(
            readout,
            put_back_distribution=put_back_distribution,
            put_back_action=put_back_action,
        )
    raise ValueError("unknown task-head sensitivity intervention")


def _new_task_separated_runtime(
    *, route_config: Any, interaction_model: Any
) -> TaskSeparatedLearnedInteractionRuntime:
    return TaskSeparatedLearnedInteractionRuntime(
        arm=FullJointArm.STATEFUL_FULL_JOINT,
        config=route_config,
        neural_model=load_neural_proposal_model(route_config.neural_proposal_model_path),
        interaction_model=interaction_model,
    )


def _run_single_head_sensitivity_control(
    *,
    head: ConstructActionKind,
    target_step_index: int,
    seed: int,
    step_count: int,
    base_config: FullScientificLoopConfig,
    route_config: Any,
    interaction_model: Any,
) -> dict[str, Any]:
    """Replay the same source path and change exactly one task-head ranking."""

    runtime = _new_task_separated_runtime(
        route_config=route_config,
        interaction_model=interaction_model,
    )
    environment = TaskSeparatedActionEnvironment(
        seed=seed,
        config=base_config,
        run_execution_id=_deterministic_run_execution_id(
            seed=seed,
            role=f"{head.value}_sensitivity_control",
        ),
    )
    target_trace: dict[str, Any] | None = None
    for step_index in range(step_count):
        observation = environment.observe_visible()
        runtime.revise(observation)
        readout = environment.issue_runtime_readout(
            runtime,
            intervention_head=head if step_index == target_step_index else None,
        )
        runtime.action_readout_traces.append(_probability_map(readout.put_back_distribution))
        environment.commit_actions(readout)
        search_receipt = environment.execute_search()
        put_back_transition = environment.execute_put_back()
        truth = environment.disclose_truth()
        metrics = _derive_separate_metrics(
            readout=readout,
            observation=observation,
            search_receipt=search_receipt,
            put_back_transition=put_back_transition,
            truth=truth,
        )
        feedback = environment.feedback()
        runtime.apply_feedback(feedback)
        if step_index == target_step_index:
            target_trace = {
                "step_index": step_index,
                "source_update_id": str(observation.source_update_id),
                "visible_observation": _visible_observation_payload(observation),
                "intervened_head": head.value,
                "readout": readout.to_dict(),
                "search_execution": search_receipt,
                "put_back_transition": put_back_transition,
                "truth": _truth_dict(truth),
                "metrics": _artifact_metrics(metrics),
                "phase_guard_events": list(environment.phase_guard_events),
            }
    runtime.verify_internal_contracts()
    if target_trace is None:
        raise ValueError("sensitivity control target step was not executed")
    return target_trace


def _source_binding(
    repository_root: Path,
    gate_config: ActionUtilityConstructGateConfig,
    base_config: FullScientificLoopConfig,
) -> list[dict[str, str]]:
    base_route = load_stateful_full_joint_config(repository_root, base_config.base_route_config)
    paths = (
        Path(__file__).resolve().relative_to(repository_root.resolve()),
        DEFAULT_RUNNER,
        DEFAULT_CONFIG,
        gate_config.base_full_loop_config,
        Path("src/cpswm/system/evaluation_operations/structure_two_full_scientific_loop.py"),
        Path("src/cpswm/system/evaluation_operations/structure_two_stateful_full_joint.py"),
        base_config.base_route_config,
        base_route.neural_proposal_model_path.resolve().relative_to(repository_root.resolve()),
    )
    return [
        {"path": path.as_posix(), "sha256": _file_sha256(repository_root / path)} for path in paths
    ]


def _unsigned_artifact(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(result))
    payload.pop("content_sha256", None)
    return payload


def run_action_utility_construct_gate(*, repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    config = load_action_utility_construct_gate_config(root)
    base_config = load_full_scientific_loop_config(root, config.base_full_loop_config)
    if any(step < config.step_count for step in base_config.ciav_steps):
        raise ValueError("three-step construct probe cannot consume evaluator-only CIAV truth")
    if config.expected_non_owner_step_index not in base_config.guest_event_steps:
        raise ValueError("registered non-owner probe step is absent from the base environment")

    interaction_model, _selection, _evidence = train_cross_axis_interactions(
        repository_root=root,
        config=base_config,
    )
    route_config = load_stateful_full_joint_config(root, base_config.base_route_config)
    runtime = _new_task_separated_runtime(
        route_config=route_config,
        interaction_model=interaction_model,
    )
    environment = TaskSeparatedActionEnvironment(
        seed=config.seed,
        config=base_config,
        run_execution_id=_deterministic_run_execution_id(seed=config.seed, role="baseline"),
    )

    traces: list[dict[str, Any]] = []
    for step_index in range(config.step_count):
        pre_observation_state_sha256 = runtime._state_sha256()
        observation = environment.observe_visible()
        ledger_cursor = len(runtime.rgrc_ledger.records)
        runtime.revise(observation)
        readout = environment.issue_runtime_readout(runtime)
        runtime.action_readout_traces.append(_probability_map(readout.put_back_distribution))
        environment.commit_actions(readout)
        search_receipt = environment.execute_search()
        put_back_transition = environment.execute_put_back()
        truth = environment.disclose_truth()

        metrics = _derive_separate_metrics(
            readout=readout,
            observation=observation,
            search_receipt=search_receipt,
            put_back_transition=put_back_transition,
            truth=truth,
        )
        feedback = environment.feedback()
        pre_feedback_state_sha256 = runtime._state_sha256()
        runtime.apply_feedback(feedback)
        post_feedback_state_sha256 = runtime._state_sha256()

        traces.append(
            {
                "step_index": step_index,
                "pre_observation_state_sha256": pre_observation_state_sha256,
                "source_update_id": str(observation.source_update_id),
                "visible_observation": _visible_observation_payload(observation),
                "readout": readout.to_dict(),
                "search_execution": search_receipt,
                "put_back_transition": put_back_transition,
                "truth": _truth_dict(truth),
                "metrics": _artifact_metrics(metrics),
                "phase_guard_events": list(environment.phase_guard_events),
                "feedback_record_id": str(feedback.feedback_record_id),
                "pre_feedback_state_sha256": pre_feedback_state_sha256,
                "post_feedback_state_sha256": post_feedback_state_sha256,
                "rgrc_operations": [
                    record.operation for record in runtime.rgrc_ledger.records[ledger_cursor:]
                ],
            }
        )

    runtime.verify_internal_contracts()
    search_control_trace = _run_single_head_sensitivity_control(
        head=ConstructActionKind.SEARCH,
        target_step_index=config.sensitivity_control_step_index,
        seed=config.seed,
        step_count=config.step_count,
        base_config=base_config,
        route_config=route_config,
        interaction_model=interaction_model,
    )
    put_back_control_trace = _run_single_head_sensitivity_control(
        head=ConstructActionKind.PUT_BACK,
        target_step_index=config.sensitivity_control_step_index,
        seed=config.seed,
        step_count=config.step_count,
        base_config=base_config,
        route_config=route_config,
        interaction_model=interaction_model,
    )
    baseline_control_trace = traces[config.sensitivity_control_step_index]
    baseline_put_back_metrics = {
        key: value
        for key, value in baseline_control_trace["metrics"].items()
        if key != "search_regret"
    }
    search_control_put_back_metrics = {
        key: value
        for key, value in search_control_trace["metrics"].items()
        if key != "search_regret"
    }
    search_comparisons = {
        "search_regret_increased": (
            search_control_trace["metrics"]["search_regret"]
            > baseline_control_trace["metrics"]["search_regret"]
        ),
        "put_back_readout_semantics_unchanged": (
            search_control_trace["readout"]["put_back_distribution"]
            == baseline_control_trace["readout"]["put_back_distribution"]
            and search_control_trace["readout"]["selected_put_back_action"]["location_id"]
            == baseline_control_trace["readout"]["selected_put_back_action"]["location_id"]
        ),
        "put_back_metrics_unchanged": (
            search_control_put_back_metrics == baseline_put_back_metrics
        ),
        "put_back_transition_effect_unchanged": (
            _put_back_transition_effect(search_control_trace["put_back_transition"])
            == _put_back_transition_effect(baseline_control_trace["put_back_transition"])
        ),
    }
    put_back_comparisons = {
        "put_back_error_increased": (
            put_back_control_trace["metrics"]["put_back_error"]
            > baseline_control_trace["metrics"]["put_back_error"]
        ),
        "wrong_but_execution_successful": (
            put_back_control_trace["metrics"]["put_back_error"] == 1.0
            and put_back_control_trace["metrics"]["put_back_execution_success"] is True
            and put_back_control_trace["metrics"]["post_action_goal_satisfied"] is False
        ),
        "search_readout_semantics_unchanged": (
            put_back_control_trace["readout"]["search_distribution"]
            == baseline_control_trace["readout"]["search_distribution"]
            and [
                action["location_id"] for action in put_back_control_trace["readout"]["search_plan"]
            ]
            == [
                action["location_id"] for action in baseline_control_trace["readout"]["search_plan"]
            ]
        ),
        "search_metric_unchanged": (
            put_back_control_trace["metrics"]["search_regret"]
            == baseline_control_trace["metrics"]["search_regret"]
        ),
        "search_execution_effect_unchanged": (
            _search_execution_effect(put_back_control_trace["search_execution"])
            == _search_execution_effect(baseline_control_trace["search_execution"])
        ),
    }
    sensitivity_controls = {
        "protocol_id": SENSITIVITY_PROTOCOL,
        "target_step_index": config.sensitivity_control_step_index,
        "baseline_trace_step_index": config.sensitivity_control_step_index,
        "search_ranking_intervention": {
            "intervention_id": "search_head_rank_top_swap_only",
            "raw_intervention_trace": search_control_trace,
            "comparisons": search_comparisons,
        },
        "put_back_ranking_intervention": {
            "intervention_id": "put_back_head_rank_third_location_only",
            "raw_intervention_trace": put_back_control_trace,
            "comparisons": put_back_comparisons,
        },
        "summary": {
            "baseline_search_regret": baseline_control_trace["metrics"]["search_regret"],
            "search_intervention_regret": search_control_trace["metrics"]["search_regret"],
            "baseline_put_back_error": baseline_control_trace["metrics"]["put_back_error"],
            "put_back_intervention_error": put_back_control_trace["metrics"]["put_back_error"],
            "wrong_put_back_execution_success": put_back_control_trace["metrics"][
                "put_back_execution_success"
            ],
            "wrong_put_back_goal_satisfied": put_back_control_trace["metrics"][
                "post_action_goal_satisfied"
            ],
        },
    }
    location_disagreement_count = sum(
        row["readout"]["selected_search_action"]["location_id"]
        != row["readout"]["selected_put_back_action"]["location_id"]
        for row in traces
    )
    successful_non_noop_count = sum(
        row["metrics"]["put_back_execution_success"]
        and row["metrics"]["put_back_commanded_non_noop"]
        and row["metrics"]["put_back_object_state_changed"]
        for row in traces
    )
    checks = {
        "exactly_three_steps": len(traces) == 3,
        "all_actions_typed_and_information_bound": True,
        "search_never_changes_object_state": all(
            not row["search_execution"]["object_state_changed"]
            and not row["search_execution"]["environment_step_advanced"]
            for row in traces
        ),
        "search_and_put_back_metrics_separate": True,
        "combined_utility_left_unresolved": True,
        "phase_guarded_call_order_observed": all(
            row["phase_guard_events"] == list(EXPECTED_PHASE_GUARD_EVENTS) for row in traces
        ),
        "search_metric_responds_to_search_only_ranking_intervention": all(
            search_comparisons.values()
        ),
        "put_back_metric_responds_to_put_back_only_ranking_intervention": all(
            put_back_comparisons.values()
        ),
        "successful_wrong_put_back_separates_execution_from_task_utility": (
            put_back_comparisons["wrong_but_execution_successful"]
        ),
        "selected_location_disagreement_step_count_satisfied": (
            location_disagreement_count >= config.minimum_selected_location_disagreement_steps
        ),
        "successful_non_noop_put_back_transition_count_satisfied": (
            successful_non_noop_count >= config.minimum_successful_non_noop_put_back_transitions
        ),
        "registered_non_owner_step_observed": (
            traces[config.expected_non_owner_step_index]["truth"]["actor"] != "owner"
        ),
    }
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "status": STATUS,
        "evidence_status": "D0_CONSTRUCT_VALIDITY_DIAGNOSTIC_NOT_PAPER_EVIDENCE",
        "source_binding": _source_binding(root, config, base_config),
        "configuration_sha256": _file_sha256(root / DEFAULT_CONFIG),
        "probe": {
            "seed": config.seed,
            "step_count": config.step_count,
            "target_object_id": str(environment.target_object_id),
            "baseline_run_execution_id": str(environment.run_execution_id),
            "location_ids": [str(location) for location in environment.locations],
            "interaction_model_sha256": interaction_model.model_hash,
            "runtime_class": (
                "cpswm.system.evaluation_operations."
                "structure_two_action_utility_construct_gate."
                "TaskSeparatedLearnedInteractionRuntime"
            ),
            "decision_protocol": DECISION_PROTOCOL,
            "traces": traces,
        },
        "separate_metric_summary": {
            "search": {
                "mean_normalized_extra_inspection_regret": mean(
                    row["metrics"]["search_regret"] for row in traces
                ),
                "mean_inspection_count": mean(
                    row["search_execution"]["inspection_count"] for row in traces
                ),
            },
            "put_back": {
                "error_rate": mean(row["metrics"]["put_back_error"] for row in traces),
                "commanded_non_noop_count": sum(
                    row["metrics"]["put_back_commanded_non_noop"] for row in traces
                ),
                "successful_non_noop_state_change_count": successful_non_noop_count,
                "post_action_goal_satisfied_rate": mean(
                    row["metrics"]["post_action_goal_satisfied"] for row in traces
                ),
            },
            "contamination": {
                "metric_id": "non_owner_copy_putback_proxy_only",
                "event_count": sum(
                    row["metrics"]["non_owner_copy_putback_proxy"] for row in traces
                ),
                "long_term_memory_contamination_established": False,
            },
            "combined_utility": {
                "status": COMBINED_UTILITY_STATUS,
                "value": None,
                "weights": None,
            },
        },
        "sensitivity_controls": sensitivity_controls,
        "diagnostic_counts": {
            "selected_location_disagreement_step_count": location_disagreement_count,
            "successful_non_noop_put_back_transition_count": successful_non_noop_count,
            "search_sensitivity_positive_control_count": int(all(search_comparisons.values())),
            "put_back_sensitivity_positive_control_count": int(all(put_back_comparisons.values())),
            "successful_wrong_put_back_control_count": int(
                put_back_comparisons["wrong_but_execution_successful"]
            ),
        },
        "gate_checks": checks,
        "action_utility_construct_gate_passed": all(checks.values()),
        "long_term_product_action_semantics_selected": False,
        "production_runtime_identity_established": False,
        "scientific_superiority_established": False,
        "task_8_formal_passed": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    result["content_sha256"] = content_sha256(_unsigned_artifact(result))
    return result


def _parse_distribution(payload: Any, expected: set[UUID], name: str) -> dict[UUID, float]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{name} must be an object")
    values: dict[UUID, float] = {}
    try:
        for key, raw_value in payload.items():
            if not isinstance(key, str):
                raise ValueError(f"{name} key is not a string")
            parsed = UUID(key)
            if key != str(parsed) or parsed in values:
                raise ValueError(f"{name} UUID support is noncanonical or duplicated")
            if type(raw_value) not in {int, float}:
                raise ValueError(f"{name} value is not a JSON number")
            values[parsed] = float(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} is malformed") from error
    if set(values) != expected:
        raise ValueError(f"{name} changed registered location support")
    if any(
        not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in values.values()
    ) or not math.isclose(sum(values.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(f"{name} is not a probability distribution")
    return values


def _verify_visible_observation_payload(
    payload: Mapping[str, Any],
    *,
    source_update_id: UUID,
    locations: tuple[UUID, ...],
    name: str,
) -> None:
    _require_exact_keys(
        payload,
        {
            "source_update_id",
            "evidence_cluster_id",
            "owner_actor_key",
            "actor_posterior",
            "mechanism_posterior",
            "ordered_role_posterior",
            "identity_target_probability",
            "cause_posterior",
            "regime_change_probability",
            "active_regime",
            "observed_location_id",
            "base_location_distribution",
            "known_location_ids",
            "unresolved_probability",
        },
        name,
    )
    try:
        evidence_cluster_id = UUID(payload["evidence_cluster_id"])
        observed_location_id = UUID(payload["observed_location_id"])
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} identity is malformed") from error
    if (
        payload["source_update_id"] != str(source_update_id)
        or payload["evidence_cluster_id"] != str(evidence_cluster_id)
        or payload["observed_location_id"] != str(observed_location_id)
        or observed_location_id not in set(locations)
        or payload["known_location_ids"] != [str(location) for location in locations]
    ):
        raise ValueError(f"{name} source or location registry drifted")
    _parse_distribution(
        payload["base_location_distribution"],
        set(locations),
        f"{name} base location distribution",
    )


def _verify_sensitivity_raw_trace(
    trace: Mapping[str, Any],
    *,
    expected_head: ConstructActionKind,
    expected_step: int,
    expected_run_execution_id: UUID,
    expected_source_update_id: UUID,
    expected_evidence_cluster_id: UUID,
    locations: tuple[UUID, ...],
    target_object_id: UUID,
) -> dict[str, Any]:
    """Validate and independently derive one sensitivity-control outcome."""

    _require_exact_keys(
        trace,
        {
            "step_index",
            "source_update_id",
            "visible_observation",
            "intervened_head",
            "readout",
            "search_execution",
            "put_back_transition",
            "truth",
            "metrics",
            "phase_guard_events",
        },
        "sensitivity raw trace",
    )
    if (
        trace["step_index"] != expected_step
        or trace["intervened_head"] != expected_head.value
        or trace["phase_guard_events"] != list(EXPECTED_PHASE_GUARD_EVENTS)
    ):
        raise ValueError("sensitivity control step, head, or phase guard drifted")
    try:
        if trace["source_update_id"] != str(UUID(trace["source_update_id"])):
            raise ValueError
    except (TypeError, ValueError) as error:
        raise ValueError("sensitivity source update ID is noncanonical") from error
    source_update_id = UUID(trace["source_update_id"])
    if source_update_id != expected_source_update_id:
        raise ValueError("sensitivity source update ID is not seed/step canonical")
    _verify_visible_observation_payload(
        trace["visible_observation"],
        source_update_id=source_update_id,
        locations=locations,
        name="sensitivity visible observation",
    )
    if trace["visible_observation"]["evidence_cluster_id"] != str(expected_evidence_cluster_id):
        raise ValueError("sensitivity evidence cluster ID is not seed/step canonical")

    support = set(locations)
    readout = trace["readout"]
    _require_exact_keys(
        readout,
        {
            "step_index",
            "run_execution_id",
            "source_update_id",
            "observation_commitment_sha256",
            "belief_state_sha256",
            "information_set_sha256",
            "search_distribution",
            "put_back_distribution",
            "search_plan",
            "selected_search_action",
            "selected_put_back_action",
            "truth_accessed_before_action_commit",
        },
        "sensitivity task-separated readout",
    )
    if (
        readout["step_index"] != expected_step
        or readout["truth_accessed_before_action_commit"] is not False
    ):
        raise ValueError("sensitivity readout used evaluator truth or another step")
    _validate_sha256(readout["belief_state_sha256"], "sensitivity belief state")
    _validate_sha256(readout["information_set_sha256"], "sensitivity information set")
    _validate_sha256(
        readout["observation_commitment_sha256"],
        "sensitivity observation commitment",
    )
    try:
        readout_run_execution_id = UUID(readout["run_execution_id"])
        readout_source_update_id = UUID(readout["source_update_id"])
    except (TypeError, ValueError) as error:
        raise ValueError("sensitivity readout execution binding is malformed") from error
    expected_observation_commitment = _observation_commitment_sha256(
        run_execution_id=expected_run_execution_id,
        step_index=expected_step,
        source_update_id=source_update_id,
        visible_observation=trace["visible_observation"],
    )
    expected_information_set = _information_set_sha256(
        run_execution_id=expected_run_execution_id,
        step_index=expected_step,
        source_update_id=source_update_id,
        observation_commitment_sha256=expected_observation_commitment,
        belief_state_sha256=readout["belief_state_sha256"],
    )
    if (
        readout["run_execution_id"] != str(readout_run_execution_id)
        or readout["source_update_id"] != str(readout_source_update_id)
        or readout_run_execution_id != expected_run_execution_id
        or readout_source_update_id != source_update_id
        or readout["observation_commitment_sha256"] != expected_observation_commitment
        or readout["information_set_sha256"] != expected_information_set
    ):
        raise ValueError(
            "sensitivity readout is not bound to its current execution and observation"
        )
    search_distribution = _parse_distribution(
        readout["search_distribution"], support, "sensitivity search distribution"
    )
    put_back_distribution = _parse_distribution(
        readout["put_back_distribution"], support, "sensitivity put-back distribution"
    )
    search_plan = tuple(TypedRouteCAction.from_mapping(action) for action in readout["search_plan"])
    selected_search = TypedRouteCAction.from_mapping(readout["selected_search_action"])
    selected_put_back = TypedRouteCAction.from_mapping(readout["selected_put_back_action"])
    actions = (*search_plan, selected_put_back)
    expected_search_decision = _task_head_decision_id(
        kind=ConstructActionKind.SEARCH,
        run_execution_id=expected_run_execution_id,
        step_index=expected_step,
        source_update_id=source_update_id,
        information_set_sha256=expected_information_set,
    )
    expected_put_back_decision = _task_head_decision_id(
        kind=ConstructActionKind.PUT_BACK,
        run_execution_id=expected_run_execution_id,
        step_index=expected_step,
        source_update_id=source_update_id,
        information_set_sha256=expected_information_set,
    )
    if (
        len(search_plan) != len(locations)
        or search_plan[0] != selected_search
        or tuple(action.location_id for action in search_plan) != _rank(search_distribution)
        or {action.location_id for action in search_plan} != support
        or any(action.kind is not ConstructActionKind.SEARCH for action in search_plan)
        or any(action.decision_id != expected_search_decision for action in search_plan)
        or selected_put_back.kind is not ConstructActionKind.PUT_BACK
        or selected_put_back.decision_id != expected_put_back_decision
        or selected_put_back.location_id != _rank(put_back_distribution)[0]
        or any(action.target_object_id != target_object_id for action in actions)
        or any(
            action.information_set_sha256 != readout["information_set_sha256"] for action in actions
        )
    ):
        raise ValueError("sensitivity typed action does not match its registered task head")

    truth = trace["truth"]
    _require_exact_keys(
        truth,
        {
            "step_index",
            "actor",
            "owner_actor_key",
            "owner_habit_location",
            "object_location_before_action",
            "external_event",
        },
        "sensitivity evaluator truth",
    )
    try:
        true_object = UUID(truth["object_location_before_action"])
        true_habit = UUID(truth["owner_habit_location"])
    except (TypeError, ValueError) as error:
        raise ValueError("sensitivity evaluator truth is malformed") from error
    if (
        truth["step_index"] != expected_step
        or truth["owner_actor_key"] != "owner"
        or truth["object_location_before_action"] != str(true_object)
        or truth["owner_habit_location"] != str(true_habit)
        or true_object not in support
        or true_habit not in support
    ):
        raise ValueError("sensitivity evaluator truth changed support or step")

    search = trace["search_execution"]
    _require_exact_keys(
        search,
        {
            "step_index",
            "planned_action_ids",
            "executed_action_ids",
            "inspected_location_ids",
            "target_found",
            "inspection_count",
            "pre_search_object_location",
            "post_search_object_location",
            "object_state_changed",
            "environment_step_advanced",
        },
        "sensitivity search receipt",
    )
    object_rank = tuple(action.location_id for action in search_plan).index(true_object)
    expected_executed = search_plan[: object_rank + 1]
    if (
        search["step_index"] != expected_step
        or search["planned_action_ids"] != [str(action.action_id) for action in search_plan]
        or search["executed_action_ids"] != [str(action.action_id) for action in expected_executed]
        or search["inspected_location_ids"]
        != [str(action.location_id) for action in expected_executed]
        or search["inspection_count"] != object_rank + 1
        or search["target_found"] is not True
        or search["pre_search_object_location"] != str(true_object)
        or search["post_search_object_location"] != str(true_object)
        or search["object_state_changed"] is not False
        or search["environment_step_advanced"] is not False
    ):
        raise ValueError("sensitivity search receipt is not derived from its typed plan")

    transition = trace["put_back_transition"]
    _require_exact_keys(
        transition,
        {
            "step_index",
            "typed_action",
            "pre_action_location",
            "attempted_location",
            "action_success_draw",
            "action_success",
            "post_action_location",
            "commanded_non_noop",
            "object_state_changed",
            "counterfactual_action",
            "counterfactual_post_action_location",
            "counterfactual_action_sensitivity",
            "potential_outcome_randomness_key",
            "post_action_observation_available",
        },
        "sensitivity put-back transition",
    )
    action_from_transition = TypedRouteCAction.from_mapping(transition["typed_action"])
    try:
        pre = UUID(transition["pre_action_location"])
        attempted = UUID(transition["attempted_location"])
        post = UUID(transition["post_action_location"])
        counterfactual_action = UUID(transition["counterfactual_action"])
        counterfactual_post = UUID(transition["counterfactual_post_action_location"])
    except (TypeError, ValueError) as error:
        raise ValueError("sensitivity transition location is malformed") from error
    if any(
        transition[key] != str(parsed)
        for key, parsed in (
            ("pre_action_location", pre),
            ("attempted_location", attempted),
            ("post_action_location", post),
            ("counterfactual_action", counterfactual_action),
            ("counterfactual_post_action_location", counterfactual_post),
        )
    ) or any(
        location not in support
        for location in (pre, attempted, post, counterfactual_action, counterfactual_post)
    ):
        raise ValueError("sensitivity transition location is noncanonical or unregistered")
    success = transition["action_success"]
    draw = transition["action_success_draw"]
    non_noop = selected_put_back.location_id != pre
    changed = post != pre
    if (
        transition["step_index"] != expected_step
        or action_from_transition != selected_put_back
        or pre != true_object
        or attempted != selected_put_back.location_id
        or type(draw) not in {int, float}
        or not math.isfinite(float(draw))
        or not 0.0 <= float(draw) < 1.0
        or type(success) is not bool
        or transition["commanded_non_noop"] is not non_noop
        or transition["object_state_changed"] is not changed
        or (success and post != attempted)
        or (not success and post != pre)
        or changed != (success and non_noop)
        or counterfactual_action == attempted
        or counterfactual_post != (counterfactual_action if success else pre)
        or transition["counterfactual_action_sensitivity"] is not (post != counterfactual_post)
        or transition["post_action_observation_available"] is not True
    ):
        raise ValueError("sensitivity put-back transition is not action-derived")
    _validate_sha256(
        transition["potential_outcome_randomness_key"],
        "sensitivity potential-outcome randomness key",
    )

    expected_metrics = {
        "search_regret": object_rank / max(1, len(locations) - 1),
        "put_back_error": float(selected_put_back.location_id != true_habit),
        "non_owner_copy_putback_proxy": float(
            truth["actor"] != truth["owner_actor_key"]
            and selected_put_back.location_id == true_object
            and selected_put_back.location_id != true_habit
        ),
        "put_back_execution_success": success,
        "put_back_commanded_non_noop": non_noop,
        "put_back_object_state_changed": changed,
        "post_action_goal_satisfied": post == true_habit,
    }
    _require_exact_keys(trace["metrics"], set(expected_metrics), "sensitivity metrics")
    if trace["metrics"] != expected_metrics:
        raise ValueError("sensitivity metric is not truth- and transition-derived")
    return {
        "search_distribution": search_distribution,
        "put_back_distribution": put_back_distribution,
        "selected_search": selected_search,
        "selected_put_back": selected_put_back,
        "metrics": expected_metrics,
    }


def _verify_sensitivity_controls(
    result: Mapping[str, Any],
    *,
    config: ActionUtilityConstructGateConfig,
    locations: tuple[UUID, ...],
    target_object_id: UUID,
) -> dict[str, bool]:
    controls = result["sensitivity_controls"]
    _require_exact_keys(
        controls,
        {
            "protocol_id",
            "target_step_index",
            "baseline_trace_step_index",
            "search_ranking_intervention",
            "put_back_ranking_intervention",
            "summary",
        },
        "task-head sensitivity controls",
    )
    target_step = config.sensitivity_control_step_index
    if (
        controls["protocol_id"] != SENSITIVITY_PROTOCOL
        or controls["target_step_index"] != target_step
        or controls["baseline_trace_step_index"] != target_step
    ):
        raise ValueError("task-head sensitivity control registration drifted")
    baseline = result["probe"]["traces"][target_step]

    search_control = controls["search_ranking_intervention"]
    put_back_control = controls["put_back_ranking_intervention"]
    _require_exact_keys(
        search_control,
        {"intervention_id", "raw_intervention_trace", "comparisons"},
        "search ranking intervention",
    )
    _require_exact_keys(
        put_back_control,
        {"intervention_id", "raw_intervention_trace", "comparisons"},
        "put-back ranking intervention",
    )
    if (
        search_control["intervention_id"] != "search_head_rank_top_swap_only"
        or put_back_control["intervention_id"] != "put_back_head_rank_third_location_only"
    ):
        raise ValueError("task-head sensitivity intervention identity drifted")
    search_trace = search_control["raw_intervention_trace"]
    put_back_trace = put_back_control["raw_intervention_trace"]
    search_run_execution_id = _deterministic_run_execution_id(
        seed=config.seed,
        role="search_sensitivity_control",
    )
    put_back_run_execution_id = _deterministic_run_execution_id(
        seed=config.seed,
        role="put_back_sensitivity_control",
    )
    baseline_run_execution_id = UUID(result["probe"]["baseline_run_execution_id"])
    expected_source_update_id = content_uuid(
        "route-c-v0.2-source",
        {"seed": config.seed, "step": target_step},
    )
    expected_evidence_cluster_id = content_uuid(
        "route-c-v0.2-cluster",
        {"seed": config.seed, "step": target_step},
    )
    if len({baseline_run_execution_id, search_run_execution_id, put_back_run_execution_id}) != 3:
        raise ValueError("baseline and sensitivity controls do not have distinct execution IDs")
    search_derived = _verify_sensitivity_raw_trace(
        search_trace,
        expected_head=ConstructActionKind.SEARCH,
        expected_step=target_step,
        expected_run_execution_id=search_run_execution_id,
        expected_source_update_id=expected_source_update_id,
        expected_evidence_cluster_id=expected_evidence_cluster_id,
        locations=locations,
        target_object_id=target_object_id,
    )
    put_back_derived = _verify_sensitivity_raw_trace(
        put_back_trace,
        expected_head=ConstructActionKind.PUT_BACK,
        expected_step=target_step,
        expected_run_execution_id=put_back_run_execution_id,
        expected_source_update_id=expected_source_update_id,
        expected_evidence_cluster_id=expected_evidence_cluster_id,
        locations=locations,
        target_object_id=target_object_id,
    )

    baseline_readout = baseline["readout"]
    baseline_metrics = baseline["metrics"]
    if (
        search_trace["source_update_id"] != baseline["source_update_id"]
        or put_back_trace["source_update_id"] != baseline["source_update_id"]
        or search_trace["visible_observation"] != baseline["visible_observation"]
        or put_back_trace["visible_observation"] != baseline["visible_observation"]
        or search_trace["truth"] != baseline["truth"]
        or put_back_trace["truth"] != baseline["truth"]
    ):
        raise ValueError("sensitivity controls are not paired to the same source and truth")
    for control_trace in (search_trace, put_back_trace):
        control_readout = control_trace["readout"]
        for field in (
            "step_index",
            "belief_state_sha256",
            "truth_accessed_before_action_commit",
        ):
            if control_readout[field] != baseline_readout[field]:
                raise ValueError("sensitivity control changed the predecision information set")

    baseline_search_scores = sorted(baseline_readout["search_distribution"].values())
    search_control_scores = sorted(search_trace["readout"]["search_distribution"].values())
    baseline_put_back_scores = sorted(baseline_readout["put_back_distribution"].values())
    put_back_control_scores = sorted(put_back_trace["readout"]["put_back_distribution"].values())
    search_scope_valid = (
        search_control_scores == baseline_search_scores
        and search_derived["selected_search"].location_id
        != UUID(baseline_readout["selected_search_action"]["location_id"])
        and search_trace["readout"]["put_back_distribution"]
        == baseline_readout["put_back_distribution"]
        and search_trace["readout"]["selected_put_back_action"]["location_id"]
        == baseline_readout["selected_put_back_action"]["location_id"]
    )
    put_back_scope_valid = (
        put_back_control_scores == baseline_put_back_scores
        and put_back_derived["selected_put_back"].location_id
        != UUID(baseline_readout["selected_put_back_action"]["location_id"])
        and put_back_trace["readout"]["search_distribution"]
        == baseline_readout["search_distribution"]
        and [action["location_id"] for action in put_back_trace["readout"]["search_plan"]]
        == [action["location_id"] for action in baseline_readout["search_plan"]]
        and put_back_trace["readout"]["selected_search_action"]["location_id"]
        == baseline_readout["selected_search_action"]["location_id"]
    )
    if not search_scope_valid or not put_back_scope_valid:
        raise ValueError("sensitivity intervention changed more than one task-head ranking")

    baseline_put_back_metrics = {
        key: value for key, value in baseline_metrics.items() if key != "search_regret"
    }
    search_put_back_metrics = {
        key: value for key, value in search_derived["metrics"].items() if key != "search_regret"
    }
    expected_search_comparisons = {
        "search_regret_increased": (
            search_derived["metrics"]["search_regret"] > baseline_metrics["search_regret"]
        ),
        "put_back_readout_semantics_unchanged": True,
        "put_back_metrics_unchanged": search_put_back_metrics == baseline_put_back_metrics,
        "put_back_transition_effect_unchanged": (
            _put_back_transition_effect(search_trace["put_back_transition"])
            == _put_back_transition_effect(baseline["put_back_transition"])
        ),
    }
    expected_put_back_comparisons = {
        "put_back_error_increased": (
            put_back_derived["metrics"]["put_back_error"] > baseline_metrics["put_back_error"]
        ),
        "wrong_but_execution_successful": (
            put_back_derived["metrics"]["put_back_error"] == 1.0
            and put_back_derived["metrics"]["put_back_execution_success"] is True
            and put_back_derived["metrics"]["post_action_goal_satisfied"] is False
        ),
        "search_readout_semantics_unchanged": True,
        "search_metric_unchanged": (
            put_back_derived["metrics"]["search_regret"] == baseline_metrics["search_regret"]
        ),
        "search_execution_effect_unchanged": (
            _search_execution_effect(put_back_trace["search_execution"])
            == _search_execution_effect(baseline["search_execution"])
        ),
    }
    if (
        search_control["comparisons"] != expected_search_comparisons
        or put_back_control["comparisons"] != expected_put_back_comparisons
    ):
        raise ValueError("sensitivity comparison is not raw-trace-derived")
    expected_summary = {
        "baseline_search_regret": baseline_metrics["search_regret"],
        "search_intervention_regret": search_derived["metrics"]["search_regret"],
        "baseline_put_back_error": baseline_metrics["put_back_error"],
        "put_back_intervention_error": put_back_derived["metrics"]["put_back_error"],
        "wrong_put_back_execution_success": put_back_derived["metrics"][
            "put_back_execution_success"
        ],
        "wrong_put_back_goal_satisfied": put_back_derived["metrics"]["post_action_goal_satisfied"],
    }
    if controls["summary"] != expected_summary:
        raise ValueError("sensitivity summary is not raw-trace-derived")
    return {
        "search_control_passed": search_scope_valid and all(expected_search_comparisons.values()),
        "put_back_control_passed": put_back_scope_valid
        and all(expected_put_back_comparisons.values()),
        "wrong_but_successful_observed": expected_put_back_comparisons[
            "wrong_but_execution_successful"
        ],
    }


def _verify_trace_semantics(
    result: Mapping[str, Any],
    config: ActionUtilityConstructGateConfig,
    base_config: FullScientificLoopConfig,
) -> None:
    probe = result["probe"]
    _require_exact_keys(
        probe,
        {
            "seed",
            "step_count",
            "target_object_id",
            "baseline_run_execution_id",
            "location_ids",
            "interaction_model_sha256",
            "runtime_class",
            "decision_protocol",
            "traces",
        },
        "construct probe artifact",
    )
    if (
        probe["seed"] != config.seed
        or probe["step_count"] != config.step_count
        or probe["decision_protocol"] != DECISION_PROTOCOL
        or probe["runtime_class"]
        != (
            "cpswm.system.evaluation_operations."
            "structure_two_action_utility_construct_gate."
            "TaskSeparatedLearnedInteractionRuntime"
        )
    ):
        raise ValueError("construct probe identity or runtime class drifted")
    _validate_sha256(probe["interaction_model_sha256"], "interaction model")
    try:
        target_object_id = UUID(probe["target_object_id"])
        baseline_run_execution_id = UUID(probe["baseline_run_execution_id"])
    except (TypeError, ValueError) as error:
        raise ValueError("construct target or execution ID is malformed") from error
    if (
        probe["target_object_id"] != str(target_object_id)
        or target_object_id
        != content_uuid("structure-two-action-utility-target-object", {"seed": config.seed})
        or probe["baseline_run_execution_id"] != str(baseline_run_execution_id)
        or baseline_run_execution_id
        != _deterministic_run_execution_id(seed=config.seed, role="baseline")
    ):
        raise ValueError("construct target or execution ID is noncanonical")
    traces = probe["traces"]
    try:
        locations = tuple(UUID(value) for value in probe["location_ids"])
    except (TypeError, ValueError) as error:
        raise ValueError("construct location registry is malformed") from error
    expected_locations = tuple(
        content_uuid(
            "route-c-v0.2-location",
            {"seed": config.seed, "index": index},
        )
        for index in range(base_config.location_count)
    )
    if (
        list(map(str, locations)) != probe["location_ids"]
        or len(set(locations)) != len(locations)
        or locations != expected_locations
    ):
        raise ValueError("construct location registry is noncanonical or duplicated")
    if len(traces) != config.step_count or len(locations) < 2:
        raise ValueError("construct probe trace length or location support drifted")
    support = set(locations)
    derived_location_disagreement_count = 0
    derived_successful_non_noop = 0
    search_regrets: list[float] = []
    put_back_errors: list[float] = []
    contamination: list[float] = []
    goal_satisfied: list[float] = []
    inspection_counts: list[int] = []

    for expected_step, row in enumerate(traces):
        _require_exact_keys(
            row,
            {
                "step_index",
                "pre_observation_state_sha256",
                "source_update_id",
                "visible_observation",
                "readout",
                "search_execution",
                "put_back_transition",
                "truth",
                "metrics",
                "phase_guard_events",
                "feedback_record_id",
                "pre_feedback_state_sha256",
                "post_feedback_state_sha256",
                "rgrc_operations",
            },
            "construct trace",
        )
        if row["step_index"] != expected_step or row["phase_guard_events"] != list(
            EXPECTED_PHASE_GUARD_EVENTS
        ):
            raise ValueError("construct trace step or phase-guarded call order drifted")
        for name in (
            "pre_observation_state_sha256",
            "pre_feedback_state_sha256",
            "post_feedback_state_sha256",
        ):
            _validate_sha256(row[name], name)
        try:
            source_update_id = UUID(row["source_update_id"])
            if row["source_update_id"] != str(source_update_id) or row["feedback_record_id"] != str(
                UUID(row["feedback_record_id"])
            ):
                raise ValueError
        except (TypeError, ValueError) as error:
            raise ValueError("construct trace record identity is noncanonical") from error
        expected_source_update_id = content_uuid(
            "route-c-v0.2-source",
            {"seed": config.seed, "step": expected_step},
        )
        expected_evidence_cluster_id = content_uuid(
            "route-c-v0.2-cluster",
            {"seed": config.seed, "step": expected_step},
        )
        if source_update_id != expected_source_update_id:
            raise ValueError("construct source update ID is not seed/step canonical")
        _verify_visible_observation_payload(
            row["visible_observation"],
            source_update_id=source_update_id,
            locations=locations,
            name="construct visible observation",
        )
        if row["visible_observation"]["evidence_cluster_id"] != str(expected_evidence_cluster_id):
            raise ValueError("construct evidence cluster ID is not seed/step canonical")

        readout = row["readout"]
        _require_exact_keys(
            readout,
            {
                "step_index",
                "run_execution_id",
                "source_update_id",
                "observation_commitment_sha256",
                "belief_state_sha256",
                "information_set_sha256",
                "search_distribution",
                "put_back_distribution",
                "search_plan",
                "selected_search_action",
                "selected_put_back_action",
                "truth_accessed_before_action_commit",
            },
            "task-separated readout",
        )
        if (
            readout["step_index"] != expected_step
            or readout["truth_accessed_before_action_commit"] is not False
        ):
            raise ValueError("readout used evaluator truth or another step")
        _validate_sha256(readout["belief_state_sha256"], "belief state")
        _validate_sha256(readout["information_set_sha256"], "information set")
        _validate_sha256(readout["observation_commitment_sha256"], "observation commitment")
        try:
            readout_run_execution_id = UUID(readout["run_execution_id"])
            readout_source_update_id = UUID(readout["source_update_id"])
        except (TypeError, ValueError) as error:
            raise ValueError("readout execution binding is malformed") from error
        expected_observation_commitment = _observation_commitment_sha256(
            run_execution_id=baseline_run_execution_id,
            step_index=expected_step,
            source_update_id=source_update_id,
            visible_observation=row["visible_observation"],
        )
        expected_information_set = _information_set_sha256(
            run_execution_id=baseline_run_execution_id,
            step_index=expected_step,
            source_update_id=source_update_id,
            observation_commitment_sha256=expected_observation_commitment,
            belief_state_sha256=readout["belief_state_sha256"],
        )
        if (
            readout["run_execution_id"] != str(readout_run_execution_id)
            or readout["source_update_id"] != str(readout_source_update_id)
            or readout_run_execution_id != baseline_run_execution_id
            or readout_source_update_id != source_update_id
            or readout["observation_commitment_sha256"] != expected_observation_commitment
            or readout["information_set_sha256"] != expected_information_set
        ):
            raise ValueError("readout is not bound to its current execution and observation")
        search_distribution = _parse_distribution(
            readout["search_distribution"], support, "search distribution"
        )
        put_back_distribution = _parse_distribution(
            readout["put_back_distribution"], support, "put-back distribution"
        )
        search_plan = tuple(
            TypedRouteCAction.from_mapping(action) for action in readout["search_plan"]
        )
        selected_search = TypedRouteCAction.from_mapping(readout["selected_search_action"])
        selected_put_back = TypedRouteCAction.from_mapping(readout["selected_put_back_action"])
        expected_search_decision = _task_head_decision_id(
            kind=ConstructActionKind.SEARCH,
            run_execution_id=baseline_run_execution_id,
            step_index=expected_step,
            source_update_id=source_update_id,
            information_set_sha256=expected_information_set,
        )
        expected_put_back_decision = _task_head_decision_id(
            kind=ConstructActionKind.PUT_BACK,
            run_execution_id=baseline_run_execution_id,
            step_index=expected_step,
            source_update_id=source_update_id,
            information_set_sha256=expected_information_set,
        )
        if (
            not search_plan
            or search_plan[0] != selected_search
            or tuple(action.location_id for action in search_plan) != _rank(search_distribution)
            or any(action.kind is not ConstructActionKind.SEARCH for action in search_plan)
            or any(action.decision_id != expected_search_decision for action in search_plan)
            or selected_put_back.kind is not ConstructActionKind.PUT_BACK
            or selected_put_back.decision_id != expected_put_back_decision
            or selected_put_back.location_id != _rank(put_back_distribution)[0]
        ):
            raise ValueError("typed task-head action does not match its registered readout")
        if any(
            action.information_set_sha256 != readout["information_set_sha256"]
            for action in (*search_plan, selected_put_back)
        ):
            raise ValueError("typed action substituted another information set")
        if any(
            action.target_object_id != target_object_id
            for action in (*search_plan, selected_put_back)
        ):
            raise ValueError("typed task heads do not share the registered probe target object")

        truth = row["truth"]
        _require_exact_keys(
            truth,
            {
                "step_index",
                "actor",
                "owner_actor_key",
                "owner_habit_location",
                "object_location_before_action",
                "external_event",
            },
            "construct evaluator truth",
        )
        try:
            true_object = UUID(truth["object_location_before_action"])
            true_habit = UUID(truth["owner_habit_location"])
        except (TypeError, ValueError) as error:
            raise ValueError("construct evaluator location truth is malformed") from error
        if (
            truth["step_index"] != expected_step
            or truth["object_location_before_action"] != str(true_object)
            or truth["owner_habit_location"] != str(true_habit)
            or true_object not in support
            or true_habit not in support
        ):
            raise ValueError("construct evaluator truth changed support or step")

        search = row["search_execution"]
        _require_exact_keys(
            search,
            {
                "step_index",
                "planned_action_ids",
                "executed_action_ids",
                "inspected_location_ids",
                "target_found",
                "inspection_count",
                "pre_search_object_location",
                "post_search_object_location",
                "object_state_changed",
                "environment_step_advanced",
            },
            "search execution receipt",
        )
        rank = tuple(action.location_id for action in search_plan).index(true_object)
        expected_executed = search_plan[: rank + 1]
        if (
            search["step_index"] != expected_step
            or search["planned_action_ids"] != [str(action.action_id) for action in search_plan]
            or search["executed_action_ids"]
            != [str(action.action_id) for action in expected_executed]
            or search["inspected_location_ids"]
            != [str(action.location_id) for action in expected_executed]
            or search["inspection_count"] != rank + 1
            or search["target_found"] is not True
            or search["pre_search_object_location"] != str(true_object)
            or search["post_search_object_location"] != str(true_object)
            or search["object_state_changed"] is not False
            or search["environment_step_advanced"] is not False
        ):
            raise ValueError("search execution mutated state or disagrees with its typed plan")

        transition = row["put_back_transition"]
        _require_exact_keys(
            transition,
            {
                "step_index",
                "typed_action",
                "pre_action_location",
                "attempted_location",
                "action_success_draw",
                "action_success",
                "post_action_location",
                "commanded_non_noop",
                "object_state_changed",
                "counterfactual_action",
                "counterfactual_post_action_location",
                "counterfactual_action_sensitivity",
                "potential_outcome_randomness_key",
                "post_action_observation_available",
            },
            "typed put-back transition",
        )
        action_from_transition = TypedRouteCAction.from_mapping(transition["typed_action"])
        pre = UUID(transition["pre_action_location"])
        post = UUID(transition["post_action_location"])
        non_noop = selected_put_back.location_id != pre
        changed = post != pre
        success = transition["action_success"]
        if (
            transition["step_index"] != expected_step
            or action_from_transition != selected_put_back
            or pre != true_object
            or transition["attempted_location"] != str(selected_put_back.location_id)
            or transition["commanded_non_noop"] is not non_noop
            or transition["object_state_changed"] is not changed
            or type(success) is not bool
            or (success and post != selected_put_back.location_id)
            or (not success and post != pre)
            or changed != (success and non_noop)
        ):
            raise ValueError("put-back transition is a successful-noop or typed-action forgery")

        expected_search_regret = rank / max(1, len(locations) - 1)
        expected_put_back_error = float(selected_put_back.location_id != true_habit)
        expected_contamination = float(
            truth["actor"] != truth["owner_actor_key"]
            and selected_put_back.location_id == true_object
            and selected_put_back.location_id != true_habit
        )
        expected_goal = post == true_habit
        metrics = row["metrics"]
        _require_exact_keys(
            metrics,
            {
                "search_regret",
                "put_back_error",
                "non_owner_copy_putback_proxy",
                "put_back_execution_success",
                "put_back_commanded_non_noop",
                "put_back_object_state_changed",
                "post_action_goal_satisfied",
            },
            "separate construct metrics",
        )
        if (
            metrics["search_regret"] != expected_search_regret
            or metrics["put_back_error"] != expected_put_back_error
            or metrics["non_owner_copy_putback_proxy"] != expected_contamination
            or metrics["put_back_execution_success"] is not success
            or metrics["put_back_commanded_non_noop"] is not non_noop
            or metrics["put_back_object_state_changed"] is not changed
            or metrics["post_action_goal_satisfied"] is not expected_goal
        ):
            raise ValueError("task-separated metric is not trace-derived")
        derived_location_disagreement_count += (
            selected_search.location_id != selected_put_back.location_id
        )
        derived_successful_non_noop += success and non_noop and changed
        search_regrets.append(expected_search_regret)
        put_back_errors.append(expected_put_back_error)
        contamination.append(expected_contamination)
        goal_satisfied.append(float(expected_goal))
        inspection_counts.append(rank + 1)

    summary = result["separate_metric_summary"]
    _require_exact_keys(
        summary,
        {"search", "put_back", "contamination", "combined_utility"},
        "separate metric summary",
    )
    if summary["search"] != {
        "mean_normalized_extra_inspection_regret": mean(search_regrets),
        "mean_inspection_count": mean(inspection_counts),
    }:
        raise ValueError("search summary is not trace-derived")
    if summary["put_back"] != {
        "error_rate": mean(put_back_errors),
        "commanded_non_noop_count": sum(
            row["metrics"]["put_back_commanded_non_noop"] for row in traces
        ),
        "successful_non_noop_state_change_count": derived_successful_non_noop,
        "post_action_goal_satisfied_rate": mean(goal_satisfied),
    }:
        raise ValueError("put-back summary is not trace-derived")
    if summary["contamination"] != {
        "metric_id": "non_owner_copy_putback_proxy_only",
        "event_count": sum(contamination),
        "long_term_memory_contamination_established": False,
    }:
        raise ValueError("contamination proxy summary is not trace-derived or was promoted")
    if summary["combined_utility"] != {
        "status": COMBINED_UTILITY_STATUS,
        "value": None,
        "weights": None,
    }:
        raise ValueError("construct gate invented a combined utility")

    sensitivity = _verify_sensitivity_controls(
        result,
        config=config,
        locations=locations,
        target_object_id=target_object_id,
    )
    counts = result["diagnostic_counts"]
    expected_counts = {
        "selected_location_disagreement_step_count": derived_location_disagreement_count,
        "successful_non_noop_put_back_transition_count": derived_successful_non_noop,
        "search_sensitivity_positive_control_count": int(sensitivity["search_control_passed"]),
        "put_back_sensitivity_positive_control_count": int(sensitivity["put_back_control_passed"]),
        "successful_wrong_put_back_control_count": int(
            sensitivity["wrong_but_successful_observed"]
        ),
    }
    if counts != expected_counts:
        raise ValueError("construct diagnostic counts are not trace-derived")
    expected_checks = {
        "exactly_three_steps": len(traces) == 3,
        "all_actions_typed_and_information_bound": True,
        "search_never_changes_object_state": True,
        "search_and_put_back_metrics_separate": True,
        "combined_utility_left_unresolved": True,
        "phase_guarded_call_order_observed": True,
        "search_metric_responds_to_search_only_ranking_intervention": sensitivity[
            "search_control_passed"
        ],
        "put_back_metric_responds_to_put_back_only_ranking_intervention": sensitivity[
            "put_back_control_passed"
        ],
        "successful_wrong_put_back_separates_execution_from_task_utility": sensitivity[
            "wrong_but_successful_observed"
        ],
        "selected_location_disagreement_step_count_satisfied": (
            derived_location_disagreement_count
            >= config.minimum_selected_location_disagreement_steps
        ),
        "successful_non_noop_put_back_transition_count_satisfied": (
            derived_successful_non_noop >= config.minimum_successful_non_noop_put_back_transitions
        ),
        "registered_non_owner_step_observed": (
            traces[config.expected_non_owner_step_index]["truth"]["actor"] != "owner"
        ),
    }
    if result["gate_checks"] != expected_checks or result[
        "action_utility_construct_gate_passed"
    ] is not all(expected_checks.values()):
        raise ValueError("construct gate result is not derived from registered criteria")


def verify_action_utility_construct_gate(
    result: Mapping[str, Any],
    *,
    repository_root: Path,
    fresh_recompute: bool = True,
) -> None:
    _reject_nonfinite(result)
    _require_exact_keys(
        result,
        {
            "schema_version",
            "protocol_id",
            "status",
            "evidence_status",
            "source_binding",
            "configuration_sha256",
            "probe",
            "separate_metric_summary",
            "sensitivity_controls",
            "diagnostic_counts",
            "gate_checks",
            "action_utility_construct_gate_passed",
            "long_term_product_action_semantics_selected",
            "production_runtime_identity_established",
            "scientific_superiority_established",
            "task_8_formal_passed",
            "claim_boundary",
            "content_sha256",
        },
        "action-utility construct artifact",
    )
    if (
        result["schema_version"] != SCHEMA_VERSION
        or result["protocol_id"] != PROTOCOL_ID
        or result["status"] != STATUS
        or result["evidence_status"] != "D0_CONSTRUCT_VALIDITY_DIAGNOSTIC_NOT_PAPER_EVIDENCE"
    ):
        raise ValueError("action-utility construct artifact identity drifted")
    if result["claim_boundary"] != CLAIM_BOUNDARY:
        raise ValueError("action-utility construct artifact claim boundary drifted")
    for field in (
        "long_term_product_action_semantics_selected",
        "production_runtime_identity_established",
        "scientific_superiority_established",
        "task_8_formal_passed",
    ):
        if result[field] is not False:
            raise ValueError("D0 construct artifact promoted an unauthorized claim")
    expected_content = content_sha256(_unsigned_artifact(result))
    if result["content_sha256"] != expected_content:
        raise ValueError("action-utility construct content hash mismatch")

    root = repository_root.resolve()
    config = load_action_utility_construct_gate_config(root)
    base_config = load_full_scientific_loop_config(root, config.base_full_loop_config)
    if result["configuration_sha256"] != _file_sha256(root / DEFAULT_CONFIG):
        raise ValueError("action-utility construct configuration source changed")
    if result["source_binding"] != _source_binding(root, config, base_config):
        raise ValueError("action-utility construct source binding mismatch")
    _verify_trace_semantics(result, config, base_config)
    if fresh_recompute:
        expected = run_action_utility_construct_gate(repository_root=root)
        if dict(result) != expected:
            raise ValueError("fresh deterministic recomputation disagrees with artifact")


__all__ = [
    "DEFAULT_CONFIG",
    "DEFAULT_OUTPUT",
    "PROTOCOL_ID",
    "ActionUtilityConstructGateConfig",
    "ConstructActionKind",
    "LocationProbability",
    "TaskSeparatedActionEnvironment",
    "TaskSeparatedActionReadout",
    "TaskSeparatedLearnedInteractionRuntime",
    "TypedRouteCAction",
    "load_action_utility_construct_gate_config",
    "run_action_utility_construct_gate",
    "verify_action_utility_construct_gate",
]
