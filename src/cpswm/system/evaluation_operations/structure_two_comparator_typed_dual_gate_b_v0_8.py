"""Comparator-typed dual Gate B v0.8 for Structure Two.

The protocol fixes the scientific relation for every comparison instead of
assuming that every valid control must differ from ``care_wm``.  The scorer is
diagnostic only: no local object, even one satisfying every relation, can mint
a formal Gate-B pass or authorize the seven-operator ablation.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Literal, cast
from uuid import UUID

from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID: Final = "structure-two-comparator-typed-dual-gate-b@0.8"
PROTOCOL_STATUS: Final = "FROZEN_NOT_EXECUTED"
INVALIDATED_PROTOCOL_ID: Final = "structure-two-stratified-mechanism-dual-readout-gate-b@0.7"
BELIEF_SCHEMA_ID: Final = "structure-two-episode-public-belief-readout@0.8"
ACTION_SCHEMA_ID: Final = "structure-two-episode-public-action-readout@0.8"
ONTOLOGY_SCHEMA_ID: Final = "structure-two-episode-public-ontology@0.8"
PROJECTION_SCHEMA_ID: Final = "structure-two-runtime-public-action-bijection@0.8"
PROBABILITY_TOLERANCE: Final = 1e-9

EXPECTED_ARMS: Final = (
    "corrected_amg",
    "o_star_matched",
    "sequential_no_consolidation",
    "active_dreaming_matched",
    "auto_dreamer_matched",
    "trustmem_matched",
    "brainctl_matched",
    "care_no_action_regret",
    "care_wm",
    "full_rerun",
)


class ComparatorType(StrEnum):
    """Frozen scientific question represented by a comparator."""

    CAUSAL_DUAL_DIFFERENCE = "causal_dual_difference"
    ACTION_REGRET_AT_EQUIVALENT_BELIEF = "action_regret_at_equivalent_predecision_belief"
    FULL_RERUN_EQUIVALENCE = "full_rerun_belief_action_equivalence"


class MetricRelation(StrEnum):
    EQUIVALENT = "equivalent"
    MATERIALLY_DIFFERENT = "materially_different"
    NOT_SCORED = "not_scored"


class MetricName(StrEnum):
    TOTAL_VARIATION = "total_variation"
    ABSOLUTE_NORMALIZED_UTILITY_DIFFERENCE = "absolute_normalized_utility_difference"


class ReadoutStage(StrEnum):
    PRE_ACTION_PRE_EVALUATOR_TRUTH = "pre_action_pre_evaluator_truth"
    POST_ACTION = "post_action"
    POST_EVALUATOR_TRUTH = "post_evaluator_truth"


class PublicActionKind(StrEnum):
    PUT_BACK = "put_back"
    SEARCH = "search"
    DELIVER = "deliver"
    ASK = "ask"


class DistributionKind(StrEnum):
    BELIEF = "belief"
    ACTION = "action"


def _validate_sha256(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _validate_uuid(value: str, label: str) -> None:
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a canonical UUID") from error
    if parsed.int == 0 or str(parsed) != value:
        raise ValueError(f"{label} must be a non-nil canonical UUID")


@dataclass(frozen=True, slots=True)
class MetricRelationContract:
    """Both equivalence and difference regions are frozen before execution."""

    metric: MetricName
    relation: MetricRelation
    equivalence_lower_bound: float
    equivalence_upper_bound: float
    difference_lower_bound: float
    difference_upper_bound: float

    def __post_init__(self) -> None:
        values = (
            self.equivalence_lower_bound,
            self.equivalence_upper_bound,
            self.difference_lower_bound,
            self.difference_upper_bound,
        )
        metric_upper = 1.0 if self.metric is MetricName.TOTAL_VARIATION else 2.0
        if any(not math.isfinite(value) for value in values):
            raise ValueError("metric relation bounds must be finite")
        if not (
            0.0
            <= self.equivalence_lower_bound
            <= self.equivalence_upper_bound
            < self.difference_lower_bound
            <= self.difference_upper_bound
            <= metric_upper
        ):
            raise ValueError("equivalence and difference regions must be ordered and disjoint")

    def accepts(self, value: float | None) -> bool:
        if self.relation is MetricRelation.NOT_SCORED:
            return value is None
        if value is None or not math.isfinite(value):
            return False
        if self.relation is MetricRelation.EQUIVALENT:
            return self.equivalence_lower_bound <= value <= self.equivalence_upper_bound
        return self.difference_lower_bound <= value <= self.difference_upper_bound


@dataclass(frozen=True, slots=True)
class CausalWindow:
    window_id: str
    readout_stage: ReadoutStage
    max_readout_to_action_events: int
    utility_start_offset_events: int | None
    utility_end_offset_events: int | None
    evaluator_truth_before_action_forbidden: bool = True
    intervening_exogenous_event_forbidden: bool = True

    def __post_init__(self) -> None:
        if not self.window_id:
            raise ValueError("causal window ID must be non-empty")
        if type(self.max_readout_to_action_events) is not int or not (
            1 <= self.max_readout_to_action_events <= 4
        ):
            raise ValueError("causal window must tightly bound the pre-action readout")
        if (self.utility_start_offset_events is None) != (self.utility_end_offset_events is None):
            raise ValueError("utility causal-window bounds must be both present or both absent")
        if self.utility_start_offset_events is not None:
            assert self.utility_end_offset_events is not None
            if not (0 <= self.utility_start_offset_events <= self.utility_end_offset_events <= 8):
                raise ValueError("utility window offsets must be ordered and bounded")
        if self.readout_stage is not ReadoutStage.PRE_ACTION_PRE_EVALUATOR_TRUTH:
            raise ValueError("Gate B v0.8 causal windows must begin before action and truth")
        if not self.evaluator_truth_before_action_forbidden:
            raise ValueError("Gate B v0.8 never permits evaluator truth before action")
        if not self.intervening_exogenous_event_forbidden:
            raise ValueError("Gate B v0.8 never permits causal-window interference")


@dataclass(frozen=True, slots=True)
class ComparatorSpec:
    comparison_id: str
    domain: str
    comparator_type: ComparatorType
    left_arm: str
    right_arm: str
    belief: MetricRelationContract
    action: MetricRelationContract
    utility: MetricRelationContract
    causal_window: CausalWindow

    def __post_init__(self) -> None:
        if not self.comparison_id or not self.domain or self.left_arm == self.right_arm:
            raise ValueError("comparator identity, domain, and distinct arms are required")
        if self.belief.metric is not MetricName.TOTAL_VARIATION:
            raise ValueError("belief relation must use total variation")
        if self.action.metric is not MetricName.TOTAL_VARIATION:
            raise ValueError("action relation must use total variation")
        if self.utility.metric is not MetricName.ABSOLUTE_NORMALIZED_UTILITY_DIFFERENCE:
            raise ValueError("utility relation uses normalized absolute difference")
        try:
            registered = next(row for row in _COMPARISON_ROWS if row[0] == self.comparison_id)
        except StopIteration as error:
            raise ValueError(
                "comparator ID is absent from the frozen nine-comparison set"
            ) from error
        registered_id, registered_domain, registered_type, registered_right = registered
        if (
            registered_id != self.comparison_id
            or registered_domain != self.domain
            or registered_type is not self.comparator_type
            or self.left_arm != "care_wm"
            or registered_right != self.right_arm
        ):
            raise ValueError("comparator identity, type, domain, or arms were mixed")
        expected = _relations_for_comparator_type(self.comparator_type)
        signature = (self.belief.relation, self.action.relation, self.utility.relation)
        if signature != expected:
            raise ValueError("comparator relation direction contradicts its frozen type")
        if (
            self.belief != _tv_contract(expected[0])
            or self.action != _tv_contract(expected[1])
            or self.utility != _utility_contract(expected[2])
        ):
            raise ValueError("comparator relation bounds differ from the frozen metric regions")
        if self.causal_window != _causal_window_for(self.comparison_id, self.comparator_type):
            raise ValueError("comparator causal window differs from its frozen type and ID")
        has_utility_window = self.causal_window.utility_start_offset_events is not None
        if has_utility_window != (self.utility.relation is not MetricRelation.NOT_SCORED):
            raise ValueError("utility relation and causal window must agree")


def _tv_contract(relation: MetricRelation) -> MetricRelationContract:
    return MetricRelationContract(
        metric=MetricName.TOTAL_VARIATION,
        relation=relation,
        equivalence_lower_bound=0.0,
        equivalence_upper_bound=0.01,
        difference_lower_bound=0.05,
        difference_upper_bound=1.0,
    )


def _utility_contract(relation: MetricRelation) -> MetricRelationContract:
    return MetricRelationContract(
        metric=MetricName.ABSOLUTE_NORMALIZED_UTILITY_DIFFERENCE,
        relation=relation,
        equivalence_lower_bound=0.0,
        equivalence_upper_bound=0.01,
        difference_lower_bound=0.10,
        difference_upper_bound=2.0,
    )


_COMPARISON_ROWS: Final[tuple[tuple[str, str, ComparatorType, str], ...]] = (
    (
        "event-inference-adaptation",
        "hidden-event and actor-attribution adaptation",
        ComparatorType.CAUSAL_DUAL_DIFFERENCE,
        "corrected_amg",
    ),
    (
        "object-search-adaptation",
        "embodied object-search adaptation",
        ComparatorType.CAUSAL_DUAL_DIFFERENCE,
        "o_star_matched",
    ),
    (
        "no-consolidation-ablation",
        "reversible consolidation ablation",
        ComparatorType.CAUSAL_DUAL_DIFFERENCE,
        "sequential_no_consolidation",
    ),
    (
        "active-dreaming-adaptation",
        "failure-driven consolidation adaptation",
        ComparatorType.CAUSAL_DUAL_DIFFERENCE,
        "active_dreaming_matched",
    ),
    (
        "auto-dreamer-adaptation",
        "offline consolidation adaptation",
        ComparatorType.CAUSAL_DUAL_DIFFERENCE,
        "auto_dreamer_matched",
    ),
    (
        "trustmem-adaptation",
        "verified memory-transition adaptation",
        ComparatorType.CAUSAL_DUAL_DIFFERENCE,
        "trustmem_matched",
    ),
    (
        "brainctl-adaptation",
        "memory-admission and lifecycle-control adaptation",
        ComparatorType.CAUSAL_DUAL_DIFFERENCE,
        "brainctl_matched",
    ),
    (
        "action-regret-ablation",
        "action-regret effect at equivalent predecision belief",
        ComparatorType.ACTION_REGRET_AT_EQUIVALENT_BELIEF,
        "care_no_action_regret",
    ),
    (
        "full-rerun-control",
        "incremental reversible update versus complete replay",
        ComparatorType.FULL_RERUN_EQUIVALENCE,
        "full_rerun",
    ),
)


def _relations_for_comparator_type(
    comparator_type: ComparatorType,
) -> tuple[MetricRelation, MetricRelation, MetricRelation]:
    return {
        ComparatorType.CAUSAL_DUAL_DIFFERENCE: (
            MetricRelation.MATERIALLY_DIFFERENT,
            MetricRelation.MATERIALLY_DIFFERENT,
            MetricRelation.NOT_SCORED,
        ),
        ComparatorType.ACTION_REGRET_AT_EQUIVALENT_BELIEF: (
            MetricRelation.EQUIVALENT,
            MetricRelation.MATERIALLY_DIFFERENT,
            MetricRelation.MATERIALLY_DIFFERENT,
        ),
        ComparatorType.FULL_RERUN_EQUIVALENCE: (
            MetricRelation.EQUIVALENT,
            MetricRelation.EQUIVALENT,
            MetricRelation.NOT_SCORED,
        ),
    }[comparator_type]


def _causal_window_for(
    comparison_id: str,
    comparator_type: ComparatorType,
) -> CausalWindow:
    if comparator_type is ComparatorType.ACTION_REGRET_AT_EQUIVALENT_BELIEF:
        return CausalWindow(
            window_id="action-regret-ablation:predecision-through-consequence",
            readout_stage=ReadoutStage.PRE_ACTION_PRE_EVALUATOR_TRUTH,
            max_readout_to_action_events=1,
            utility_start_offset_events=0,
            utility_end_offset_events=3,
        )
    if comparator_type is ComparatorType.FULL_RERUN_EQUIVALENCE:
        return CausalWindow(
            window_id="full-rerun-control:same-history-pre-action",
            readout_stage=ReadoutStage.PRE_ACTION_PRE_EVALUATOR_TRUTH,
            max_readout_to_action_events=1,
            utility_start_offset_events=None,
            utility_end_offset_events=None,
        )
    return CausalWindow(
        window_id=f"{comparison_id}:shared-pre-action",
        readout_stage=ReadoutStage.PRE_ACTION_PRE_EVALUATOR_TRUTH,
        max_readout_to_action_events=1,
        utility_start_offset_events=None,
        utility_end_offset_events=None,
    )


def canonical_comparator_specs_v0_8() -> tuple[ComparatorSpec, ...]:
    specs: list[ComparatorSpec] = []
    for comparison_id, domain, comparator_type, right_arm in _COMPARISON_ROWS:
        relations = _relations_for_comparator_type(comparator_type)
        window = _causal_window_for(comparison_id, comparator_type)
        specs.append(
            ComparatorSpec(
                comparison_id=comparison_id,
                domain=domain,
                comparator_type=comparator_type,
                left_arm="care_wm",
                right_arm=right_arm,
                belief=_tv_contract(relations[0]),
                action=_tv_contract(relations[1]),
                utility=_utility_contract(relations[2]),
                causal_window=window,
            )
        )
    return tuple(specs)


@dataclass(frozen=True, slots=True)
class EpisodePublicOntology:
    """Per-episode public semantic support shared by every compared arm."""

    episode_id: str
    target_object_uuid: str
    owner_actor_uuid: str
    robot_actor_uuid: str
    location_uuids: tuple[str, ...]
    guest_actor_uuids: tuple[str, ...]
    schema_id: str = ONTOLOGY_SCHEMA_ID

    def __post_init__(self) -> None:
        if not self.episode_id or self.schema_id != ONTOLOGY_SCHEMA_ID:
            raise ValueError("episode ontology identity is noncanonical")
        if not 8 <= len(self.location_uuids) <= 12:
            raise ValueError("each episode requires 8-12 UUID locations")
        if not 1 <= len(self.guest_actor_uuids) <= 3:
            raise ValueError("each episode requires 1-3 independent UUID guests")
        uuid_fields = (
            self.target_object_uuid,
            self.owner_actor_uuid,
            self.robot_actor_uuid,
            *self.location_uuids,
            *self.guest_actor_uuids,
        )
        for index, value in enumerate(uuid_fields):
            _validate_uuid(value, f"episode ontology UUID {index}")
        if len(uuid_fields) != len(set(uuid_fields)):
            raise ValueError(
                "object, locations, owner, robot, and guests must be independent UUIDs"
            )
        if self.location_uuids != tuple(sorted(self.location_uuids)):
            raise ValueError("location UUIDs must use canonical lexical order")
        if self.guest_actor_uuids != tuple(sorted(self.guest_actor_uuids)):
            raise ValueError("guest UUIDs must use canonical lexical order")

    @property
    def actor_uuids(self) -> tuple[str, ...]:
        return (self.owner_actor_uuid, self.robot_actor_uuid, *self.guest_actor_uuids)

    @property
    def belief_support(self) -> tuple[str, ...]:
        resolved = (
            f"location={location}|responsible_actor={actor}"
            for location in self.location_uuids
            for actor in self.actor_uuids
        )
        return tuple(sorted((*resolved, "unresolved")))

    @property
    def action_support(self) -> tuple[str, ...]:
        actions = [
            *(f"put_back|location={location}" for location in self.location_uuids),
            *(f"search|location={location}" for location in self.location_uuids),
            *(f"deliver|guest={guest}" for guest in self.guest_actor_uuids),
            *(f"ask|guest={guest}" for guest in self.guest_actor_uuids),
        ]
        return tuple(sorted(actions))

    @property
    def manifest_sha256(self) -> str:
        return content_sha256(
            {
                "schema_id": self.schema_id,
                "episode_id": self.episode_id,
                "target_object_uuid": self.target_object_uuid,
                "owner_actor_uuid": self.owner_actor_uuid,
                "robot_actor_uuid": self.robot_actor_uuid,
                "location_uuids": self.location_uuids,
                "guest_actor_uuids": self.guest_actor_uuids,
                "belief_support": self.belief_support,
                "action_support": self.action_support,
            },
        )


@dataclass(frozen=True, slots=True)
class RuntimeAction:
    """Typed canonical runtime command with no opaque semantic payload."""

    runtime_action_id: str
    kind: PublicActionKind
    target_object_uuid: str
    location_uuid: str | None
    guest_actor_uuid: str | None

    def __post_init__(self) -> None:
        _validate_uuid(self.target_object_uuid, "runtime target object")
        location_action = self.kind in {PublicActionKind.PUT_BACK, PublicActionKind.SEARCH}
        if location_action:
            if self.location_uuid is None or self.guest_actor_uuid is not None:
                raise ValueError("put_back/search require only a location UUID")
            _validate_uuid(self.location_uuid, "runtime action location")
        else:
            if self.guest_actor_uuid is None or self.location_uuid is not None:
                raise ValueError("deliver/ask require only a guest UUID")
            _validate_uuid(self.guest_actor_uuid, "runtime action guest")
        if self.runtime_action_id != self.canonical_runtime_action_id:
            raise ValueError("runtime action ID must be derived from every typed semantic field")

    @property
    def canonical_runtime_action_id(self) -> str:
        target_key = "location" if self.location_uuid is not None else "guest"
        target_value = self.location_uuid or self.guest_actor_uuid
        return f"{self.kind.value}|object={self.target_object_uuid}|{target_key}={target_value}"

    def derive_public_action(self, ontology: EpisodePublicOntology) -> str:
        if self.target_object_uuid != ontology.target_object_uuid:
            raise ValueError("runtime action targets another episode object")
        if self.location_uuid is not None:
            if self.location_uuid not in ontology.location_uuids:
                raise ValueError("runtime action location is absent from the episode ontology")
            return f"{self.kind.value}|location={self.location_uuid}"
        assert self.guest_actor_uuid is not None
        if self.guest_actor_uuid not in ontology.guest_actor_uuids:
            raise ValueError("runtime action guest is absent from the episode ontology")
        return f"{self.kind.value}|guest={self.guest_actor_uuid}"

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


def make_runtime_action(
    *,
    kind: PublicActionKind,
    target_object_uuid: str,
    location_uuid: str | None = None,
    guest_actor_uuid: str | None = None,
) -> RuntimeAction:
    target_key = "location" if location_uuid is not None else "guest"
    target_value = location_uuid or guest_actor_uuid
    runtime_action_id = f"{kind.value}|object={target_object_uuid}|{target_key}={target_value}"
    return RuntimeAction(
        runtime_action_id=runtime_action_id,
        kind=kind,
        target_object_uuid=target_object_uuid,
        location_uuid=location_uuid,
        guest_actor_uuid=guest_actor_uuid,
    )


def runtime_action_from_mapping(payload: Mapping[str, object]) -> RuntimeAction:
    """Strict boundary parser; extra runtime fields cannot disappear in projection."""

    expected_fields = {
        "runtime_action_id",
        "kind",
        "target_object_uuid",
        "location_uuid",
        "guest_actor_uuid",
    }
    if set(payload) != expected_fields:
        raise ValueError("runtime action has missing or extra hidden fields")
    runtime_action_id = payload["runtime_action_id"]
    kind = payload["kind"]
    target_object_uuid = payload["target_object_uuid"]
    location_uuid = payload["location_uuid"]
    guest_actor_uuid = payload["guest_actor_uuid"]
    if not isinstance(runtime_action_id, str) or not isinstance(target_object_uuid, str):
        raise ValueError("runtime action identifiers must be strings")
    if not isinstance(kind, str):
        raise ValueError("runtime action kind must be a string")
    if location_uuid is not None and not isinstance(location_uuid, str):
        raise ValueError("runtime action location must be a string or null")
    if guest_actor_uuid is not None and not isinstance(guest_actor_uuid, str):
        raise ValueError("runtime action guest must be a string or null")
    try:
        parsed_kind = PublicActionKind(kind)
    except ValueError as error:
        raise ValueError(
            "runtime action kind is outside the frozen four-action ontology"
        ) from error
    return RuntimeAction(
        runtime_action_id=runtime_action_id,
        kind=parsed_kind,
        target_object_uuid=target_object_uuid,
        location_uuid=location_uuid,
        guest_actor_uuid=guest_actor_uuid,
    )


@dataclass(frozen=True, slots=True)
class RuntimeActionMapping:
    public_action: str
    runtime_action: RuntimeAction

    def __post_init__(self) -> None:
        if not self.public_action:
            raise ValueError("public action label must be non-empty")


@dataclass(frozen=True, slots=True)
class RuntimeActionProjection:
    """Exact per-arm, per-episode bijection between runtime and public actions."""

    episode_id: str
    arm: str
    ontology_manifest_sha256: str
    entries: tuple[RuntimeActionMapping, ...]
    schema_id: str = PROJECTION_SCHEMA_ID

    def __post_init__(self) -> None:
        if not self.episode_id or not self.arm or self.schema_id != PROJECTION_SCHEMA_ID:
            raise ValueError("runtime projection identity is noncanonical")
        _validate_sha256(self.ontology_manifest_sha256, "projection ontology manifest")
        if not self.entries:
            raise ValueError("runtime projection cannot be empty")
        public = tuple(entry.public_action for entry in self.entries)
        runtime = tuple(entry.runtime_action for entry in self.entries)
        if len(public) != len(set(public)):
            raise ValueError("runtime projection has a public-action collision")
        if len(runtime) != len(set(runtime)):
            raise ValueError("runtime projection has a runtime-action collision")

    @property
    def manifest_sha256(self) -> str:
        return content_sha256(self)

    def validate_against(self, ontology: EpisodePublicOntology) -> None:
        if self.episode_id != ontology.episode_id:
            raise ValueError("runtime projection belongs to another episode")
        if self.ontology_manifest_sha256 != ontology.manifest_sha256:
            raise ValueError("runtime projection substituted another episode ontology")
        if tuple(entry.public_action for entry in self.entries) != ontology.action_support:
            raise ValueError("runtime projection does not exactly cover the public action support")
        for entry in self.entries:
            if entry.runtime_action.derive_public_action(ontology) != entry.public_action:
                raise ValueError("runtime-to-public mapping changed the typed action semantics")

    def project(
        self,
        runtime_action: RuntimeAction,
        *,
        ontology: EpisodePublicOntology,
    ) -> str:
        self.validate_against(ontology)
        matches = tuple(
            entry.public_action for entry in self.entries if entry.runtime_action == runtime_action
        )
        if len(matches) != 1:
            raise ValueError("runtime action is absent or ambiguous in the frozen bijection")
        if runtime_action.derive_public_action(ontology) != matches[0]:
            raise ValueError("runtime action projection is not semantically lossless")
        return matches[0]

    def inverse(
        self,
        public_action: str,
        *,
        ontology: EpisodePublicOntology,
    ) -> RuntimeAction:
        self.validate_against(ontology)
        matches = tuple(
            entry.runtime_action for entry in self.entries if entry.public_action == public_action
        )
        if len(matches) != 1:
            raise ValueError("public action is absent or ambiguous in the frozen bijection")
        if matches[0].derive_public_action(ontology) != public_action:
            raise ValueError("public action inverse is not semantically lossless")
        return matches[0]


@dataclass(frozen=True, slots=True)
class EpisodeDistribution:
    kind: DistributionKind
    schema_id: str
    ontology_manifest_sha256: str
    support: tuple[str, ...]
    probabilities: tuple[float, ...]

    def __post_init__(self) -> None:
        expected_schema = (
            BELIEF_SCHEMA_ID if self.kind is DistributionKind.BELIEF else ACTION_SCHEMA_ID
        )
        if self.schema_id != expected_schema:
            raise ValueError("episode distribution uses the wrong schema")
        _validate_sha256(self.ontology_manifest_sha256, "distribution ontology manifest")
        if not self.support or self.support != tuple(sorted(self.support)):
            raise ValueError("episode distribution support must be non-empty and canonical")
        if len(self.support) != len(set(self.support)) or len(self.support) != len(
            self.probabilities
        ):
            raise ValueError("episode distribution must densely cover a unique support")
        if any(not math.isfinite(value) or value < 0.0 for value in self.probabilities):
            raise ValueError("episode probabilities must be finite and non-negative")
        if not math.isclose(
            sum(self.probabilities),
            1.0,
            rel_tol=0.0,
            abs_tol=PROBABILITY_TOLERANCE,
        ):
            raise ValueError("episode probabilities must already be normalized")

    def validate_against(self, ontology: EpisodePublicOntology) -> None:
        if self.ontology_manifest_sha256 != ontology.manifest_sha256:
            raise ValueError("episode distribution substituted another ontology")
        expected = (
            ontology.belief_support
            if self.kind is DistributionKind.BELIEF
            else ontology.action_support
        )
        if self.support != expected:
            raise ValueError("episode distribution does not cover the exact public support")


@dataclass(frozen=True, slots=True)
class DecisionReadout:
    arm: str
    episode_id: str
    decision_id: str
    causal_window_id: str
    information_set_sha256: str
    ontology_manifest_sha256: str
    projection_manifest_sha256: str
    readout_stage: ReadoutStage
    evaluator_truth_accessed: bool
    readout_event_index: int
    action_commit_event_index: int
    belief: EpisodeDistribution
    action_policy: EpisodeDistribution
    selected_public_action: str
    selected_runtime_action: RuntimeAction
    realized_utility: float | None = None
    utility_event_index: int | None = None
    intervening_exogenous_event: bool = False

    def __post_init__(self) -> None:
        if not self.arm or not self.episode_id or not self.decision_id or not self.causal_window_id:
            raise ValueError("decision readout identity must be complete")
        _validate_sha256(self.information_set_sha256, "decision information set")
        _validate_sha256(self.ontology_manifest_sha256, "decision ontology manifest")
        _validate_sha256(self.projection_manifest_sha256, "decision projection manifest")
        if type(self.readout_event_index) is not int or self.readout_event_index < 0:
            raise ValueError("readout event index must be a non-negative integer")
        if type(self.action_commit_event_index) is not int or self.action_commit_event_index < 0:
            raise ValueError("action commit index must be a non-negative integer")
        if (self.realized_utility is None) != (self.utility_event_index is None):
            raise ValueError("utility value and observation index must be present together")
        if self.realized_utility is not None and (
            not math.isfinite(self.realized_utility) or not -1.0 <= self.realized_utility <= 1.0
        ):
            raise ValueError("utility must be finite and normalized to [-1, 1]")
        if self.utility_event_index is not None and (
            type(self.utility_event_index) is not int or self.utility_event_index < 0
        ):
            raise ValueError("utility event index must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ComparatorEvidence:
    comparison_id: str
    left: DecisionReadout
    right: DecisionReadout


@dataclass(frozen=True, slots=True)
class FrozenComparatorTypedDualGateB:
    content_sha256: str
    comparators: tuple[ComparatorSpec, ...]
    expected_arms: tuple[str, ...] = EXPECTED_ARMS
    status: Literal["FROZEN_NOT_EXECUTED"] = "FROZEN_NOT_EXECUTED"
    formal_run_present: Literal[False] = False
    formal_gate_b_passed: Literal[False] = False
    seven_operator_ablation_authorized: Literal[False] = False

    def __post_init__(self) -> None:
        _validate_sha256(self.content_sha256, "frozen Gate B v0.8 content")
        if self.status != PROTOCOL_STATUS:
            raise ValueError("Gate B v0.8 protocol status cannot be promoted locally")
        if (
            self.formal_run_present
            or self.formal_gate_b_passed
            or self.seven_operator_ablation_authorized
        ):
            raise ValueError("Gate B v0.8 frozen object is not an authorization surface")


def _contract_payload(contract: MetricRelationContract) -> dict[str, Any]:
    return {
        "metric": contract.metric.value,
        "relation": contract.relation.value,
        "equivalence_bounds_inclusive": [
            contract.equivalence_lower_bound,
            contract.equivalence_upper_bound,
        ],
        "difference_bounds_inclusive": [
            contract.difference_lower_bound,
            contract.difference_upper_bound,
        ],
    }


def _comparator_payload(spec: ComparatorSpec) -> dict[str, Any]:
    return {
        "comparison_id": spec.comparison_id,
        "domain": spec.domain,
        "comparator_type": spec.comparator_type.value,
        "left_arm": spec.left_arm,
        "right_arm": spec.right_arm,
        "belief_relation": _contract_payload(spec.belief),
        "action_relation": _contract_payload(spec.action),
        "utility_relation": _contract_payload(spec.utility),
        "causal_window": {
            "window_id": spec.causal_window.window_id,
            "readout_stage": spec.causal_window.readout_stage.value,
            "max_readout_to_action_events": (spec.causal_window.max_readout_to_action_events),
            "utility_start_offset_events": (spec.causal_window.utility_start_offset_events),
            "utility_end_offset_events": spec.causal_window.utility_end_offset_events,
            "evaluator_truth_before_action_forbidden": (
                spec.causal_window.evaluator_truth_before_action_forbidden
            ),
            "intervening_exogenous_event_forbidden": (
                spec.causal_window.intervening_exogenous_event_forbidden
            ),
        },
    }


def canonical_protocol_payload_v0_8() -> dict[str, Any]:
    """Exact preregistration; loaders reject any relation or bound substitution."""

    return {
        "protocol": PROTOCOL_ID,
        "status": PROTOCOL_STATUS,
        "frozen_on": "2026-09-05",
        "invalidates": INVALIDATED_PROTOCOL_ID,
        "gate_semantics": {
            "comparator_typed": True,
            "same_relation_for_every_comparison_forbidden": True,
            "action_relation_includes_deterministic_selected_public_action": True,
            "action_regret_requires": (
                "equivalent predecision belief AND different action AND different utility"
            ),
            "full_rerun_requires": "equivalent belief AND equivalent action",
            "registered_mechanism_evidence_still_required_for_formal_run": True,
        },
        "episode_public_ontology": {
            "schema_id": ONTOLOGY_SCHEMA_ID,
            "belief_schema_id": BELIEF_SCHEMA_ID,
            "action_schema_id": ACTION_SCHEMA_ID,
            "location_uuid_count_inclusive": [8, 12],
            "independent_guest_uuid_count_inclusive": [1, 3],
            "owner_robot_object_location_guest_uuid_disjoint": True,
            "action_kinds": [kind.value for kind in PublicActionKind],
            "belief_axes": ["location", "responsible_actor"],
            "unresolved_state_required": True,
            "per_episode_manifest_frozen_before_arm_execution": True,
        },
        "runtime_action_projection": {
            "schema_id": PROJECTION_SCHEMA_ID,
            "typed_runtime_command_fields": [
                "runtime_action_id",
                "kind",
                "target_object_uuid",
                "location_uuid",
                "guest_actor_uuid",
            ],
            "runtime_action_id_derived_from_all_semantic_fields": True,
            "put_back_search_require_location_only": True,
            "deliver_ask_require_guest_only": True,
            "public_label_derived_from_runtime_fields_and_episode_ontology": True,
            "per_arm_per_episode_exact_public_support": True,
            "runtime_to_public_injective": True,
            "public_to_runtime_inverse_required": True,
            "round_trip_equality_required": True,
            "unregistered_runtime_fields_forbidden": True,
        },
        "comparisons": [_comparator_payload(spec) for spec in canonical_comparator_specs_v0_8()],
        "official_execution": {
            "formal_run_present": False,
            "independent_attestation_present": False,
            "formal_gate_b_passed": False,
            "seven_operator_ablation_authorized": False,
        },
        "claim_boundary": (
            "Gate B v0.8 is frozen but not formally run. Local relation diagnostics and "
            "runtime-action round trips cannot mint Gate B passage or seven-operator "
            "ablation authorization."
        ),
    }


def validate_protocol_payload_v0_8(payload: Mapping[str, Any]) -> None:
    if dict(payload) != canonical_protocol_payload_v0_8():
        raise ValueError("Gate B v0.8 payload differs from the canonical preregistration")


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON key in Gate B v0.8 config: {key}")
        payload[key] = value
    return payload


def load_frozen_protocol_v0_8(path: Path) -> FrozenComparatorTypedDualGateB:
    raw = cast(
        object,
        json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_json_keys),
    )
    if not isinstance(raw, dict):
        raise ValueError("Gate B v0.8 protocol must be a JSON object")
    validate_protocol_payload_v0_8(raw)
    return FrozenComparatorTypedDualGateB(
        content_sha256=content_sha256(raw),
        comparators=canonical_comparator_specs_v0_8(),
    )


def _total_variation(left: EpisodeDistribution, right: EpisodeDistribution) -> float:
    if left.kind is not right.kind or left.support != right.support:
        raise ValueError("compared distributions do not share exact public support")
    return 0.5 * sum(
        abs(left_value - right_value)
        for left_value, right_value in zip(left.probabilities, right.probabilities, strict=True)
    )


def _validate_readout(
    readout: DecisionReadout,
    *,
    expected_arm: str,
    ontology: EpisodePublicOntology,
    projection: RuntimeActionProjection,
    window: CausalWindow,
    utility_required: bool,
) -> None:
    if readout.arm != expected_arm or readout.episode_id != ontology.episode_id:
        raise ValueError("decision readout changed the registered arm or episode")
    if readout.ontology_manifest_sha256 != ontology.manifest_sha256:
        raise ValueError("decision readout substituted another public ontology")
    if readout.projection_manifest_sha256 != projection.manifest_sha256:
        raise ValueError("decision readout substituted another runtime-action projection")
    if readout.causal_window_id != window.window_id:
        raise ValueError("decision readout substituted another causal window")
    if readout.readout_stage is not window.readout_stage or readout.evaluator_truth_accessed:
        raise ValueError("post-action or evaluator-truth readout is forbidden")
    lag = readout.action_commit_event_index - readout.readout_event_index
    if not 1 <= lag <= window.max_readout_to_action_events:
        raise ValueError("readout is outside the frozen pre-action causal window")
    if readout.intervening_exogenous_event:
        raise ValueError("intervening exogenous events invalidate the causal window")
    readout.belief.validate_against(ontology)
    readout.action_policy.validate_against(ontology)
    if readout.belief.kind is not DistributionKind.BELIEF:
        raise ValueError("belief field did not contain a belief distribution")
    if readout.action_policy.kind is not DistributionKind.ACTION:
        raise ValueError("action field did not contain an action distribution")
    projection.validate_against(ontology)
    projected = projection.project(readout.selected_runtime_action, ontology=ontology)
    if projected != readout.selected_public_action:
        raise ValueError("selected runtime action does not project to the declared public action")
    if projection.inverse(projected, ontology=ontology) != readout.selected_runtime_action:
        raise ValueError("selected action failed the lossless inverse round trip")
    maximum = max(readout.action_policy.probabilities)
    selected = next(
        label
        for label, probability in zip(
            readout.action_policy.support,
            readout.action_policy.probabilities,
            strict=True,
        )
        if probability == maximum
    )
    if readout.selected_public_action != selected:
        raise ValueError("selected public action violates deterministic lexical argmax")
    if utility_required:
        if readout.utility_event_index is None or readout.realized_utility is None:
            raise ValueError("action-regret comparator requires bounded consequential utility")
        assert window.utility_start_offset_events is not None
        assert window.utility_end_offset_events is not None
        offset = readout.utility_event_index - readout.action_commit_event_index
        if not (window.utility_start_offset_events <= offset <= window.utility_end_offset_events):
            raise ValueError("utility observation lies outside the frozen causal window")
    elif readout.utility_event_index is not None or readout.realized_utility is not None:
        raise ValueError("post-action utility cannot enter a comparator that does not score it")


def _score_row(
    row: ComparatorEvidence,
    *,
    spec: ComparatorSpec,
    ontology: EpisodePublicOntology,
    projections: Mapping[tuple[str, str], RuntimeActionProjection],
) -> dict[str, Any]:
    if row.comparison_id != spec.comparison_id:
        raise ValueError("evidence row changed the frozen comparison ID")
    if row.left.decision_id != row.right.decision_id:
        raise ValueError("compared arms use different decision IDs")
    if row.left.information_set_sha256 != row.right.information_set_sha256:
        raise ValueError("compared arms use different predecision information sets")
    if (
        row.left.readout_event_index,
        row.left.action_commit_event_index,
        row.left.utility_event_index,
    ) != (
        row.right.readout_event_index,
        row.right.action_commit_event_index,
        row.right.utility_event_index,
    ):
        raise ValueError("compared arms do not share the frozen causal-window coordinates")
    utility_required = spec.utility.relation is not MetricRelation.NOT_SCORED
    for readout, arm in ((row.left, spec.left_arm), (row.right, spec.right_arm)):
        key = (arm, ontology.episode_id)
        if key not in projections:
            raise ValueError("missing per-arm per-episode runtime-action bijection")
        _validate_readout(
            readout,
            expected_arm=arm,
            ontology=ontology,
            projection=projections[key],
            window=spec.causal_window,
            utility_required=utility_required,
        )
    belief_tv = _total_variation(row.left.belief, row.right.belief)
    action_tv = _total_variation(row.left.action_policy, row.right.action_policy)
    utility_difference = (
        None
        if not utility_required
        else abs(cast(float, row.left.realized_utility) - cast(float, row.right.realized_utility))
    )
    if spec.action.relation is MetricRelation.EQUIVALENT:
        selected_action_relation_passed = (
            row.left.selected_public_action == row.right.selected_public_action
        )
    elif spec.action.relation is MetricRelation.MATERIALLY_DIFFERENT:
        selected_action_relation_passed = (
            row.left.selected_public_action != row.right.selected_public_action
        )
    else:
        selected_action_relation_passed = True
    return {
        "episode_id": ontology.episode_id,
        "decision_id": row.left.decision_id,
        "ontology_manifest_sha256": ontology.manifest_sha256,
        "causal_window_id": spec.causal_window.window_id,
        "belief_total_variation": belief_tv,
        "action_total_variation": action_tv,
        "absolute_utility_difference": utility_difference,
        "belief_relation_passed": spec.belief.accepts(belief_tv),
        "action_relation_passed": spec.action.accepts(action_tv),
        "selected_action_relation_passed": selected_action_relation_passed,
        "utility_relation_passed": spec.utility.accepts(utility_difference),
    }


def score_frozen_gate_b_v0_8_diagnostic(
    evidence: Sequence[ComparatorEvidence],
    *,
    protocol: FrozenComparatorTypedDualGateB,
    ontologies: Sequence[EpisodePublicOntology],
    projections: Mapping[tuple[str, str], RuntimeActionProjection],
) -> dict[str, Any]:
    """Validate all typed relations while keeping every authorization output false."""

    canonical_payload = canonical_protocol_payload_v0_8()
    expected_protocol = FrozenComparatorTypedDualGateB(
        content_sha256=content_sha256(canonical_payload),
        comparators=canonical_comparator_specs_v0_8(),
    )
    if protocol != expected_protocol:
        raise ValueError("diagnostic scorer rejected a noncanonical Gate B v0.8 freeze")
    ontology_by_episode = {item.episode_id: item for item in ontologies}
    if not ontology_by_episode or len(ontology_by_episode) != len(tuple(ontologies)):
        raise ValueError("Gate B requires unique per-episode public ontologies")
    specs = {item.comparison_id: item for item in protocol.comparators}
    expected_rows = {
        (comparison_id, episode_id) for comparison_id in specs for episode_id in ontology_by_episode
    }
    actual_rows = {(row.comparison_id, row.left.episode_id) for row in evidence}
    if len(actual_rows) != len(tuple(evidence)) or actual_rows != expected_rows:
        raise ValueError("typed Gate B evidence lacks exact comparison-by-episode coverage")
    expected_projection_keys = {
        (arm, episode_id) for arm in EXPECTED_ARMS for episode_id in ontology_by_episode
    }
    if set(projections) != expected_projection_keys:
        raise ValueError("runtime-action projections lack exact arm-by-episode coverage")
    for (arm, episode_id), projection in projections.items():
        if projection.arm != arm or projection.episode_id != episode_id:
            raise ValueError("runtime-action projection key does not match its payload")
        projection.validate_against(ontology_by_episode[episode_id])

    grouped: dict[str, list[dict[str, Any]]] = {comparison_id: [] for comparison_id in specs}
    for row in evidence:
        if row.comparison_id not in specs:
            raise ValueError("typed Gate B evidence names an unknown comparison")
        if row.left.episode_id != row.right.episode_id:
            raise ValueError("typed Gate B comparison crosses episode ontologies")
        ontology = ontology_by_episode.get(row.left.episode_id)
        if ontology is None:
            raise ValueError("typed Gate B evidence uses an unregistered episode")
        grouped[row.comparison_id].append(
            _score_row(
                row,
                spec=specs[row.comparison_id],
                ontology=ontology,
                projections=projections,
            )
        )

    comparison_results: list[dict[str, Any]] = []
    for spec in protocol.comparators:
        rows = grouped[spec.comparison_id]
        belief_passed = all(bool(row["belief_relation_passed"]) for row in rows)
        action_passed = all(bool(row["action_relation_passed"]) for row in rows)
        selected_action_passed = all(bool(row["selected_action_relation_passed"]) for row in rows)
        utility_passed = all(bool(row["utility_relation_passed"]) for row in rows)
        comparison_results.append(
            {
                "comparison_id": spec.comparison_id,
                "comparator_type": spec.comparator_type.value,
                "belief_relation": spec.belief.relation.value,
                "action_relation": spec.action.relation.value,
                "utility_relation": spec.utility.relation.value,
                "causal_window_id": spec.causal_window.window_id,
                "episode_results": rows,
                "belief_relation_passed": belief_passed,
                "action_relation_passed": action_passed,
                "selected_action_relation_passed": selected_action_passed,
                "utility_relation_passed": utility_passed,
                "typed_relation_passed": (
                    belief_passed and action_passed and selected_action_passed and utility_passed
                ),
            }
        )
    diagnostic_passed = all(bool(result["typed_relation_passed"]) for result in comparison_results)
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "protocol_status": PROTOCOL_STATUS,
        "invalidated_protocol": INVALIDATED_PROTOCOL_ID,
        "episode_ontology_manifest_sha256": {
            episode_id: ontology_by_episode[episode_id].manifest_sha256
            for episode_id in sorted(ontology_by_episode)
        },
        "runtime_action_bijections_verified": True,
        "comparison_results": comparison_results,
        "diagnostic_typed_relations_passed": diagnostic_passed,
        "formal_run_present": False,
        "independent_attestation_present": False,
        "formal_gate_b_passed": False,
        "gate_b_passed": False,
        "seven_operator_ablation_authorized": False,
        "claim_boundary": canonical_payload["claim_boundary"],
    }
    report["content_sha256"] = content_sha256(report)
    return report


__all__ = [
    "ACTION_SCHEMA_ID",
    "BELIEF_SCHEMA_ID",
    "EXPECTED_ARMS",
    "INVALIDATED_PROTOCOL_ID",
    "ONTOLOGY_SCHEMA_ID",
    "PROJECTION_SCHEMA_ID",
    "PROTOCOL_ID",
    "PROTOCOL_STATUS",
    "CausalWindow",
    "ComparatorEvidence",
    "ComparatorSpec",
    "ComparatorType",
    "DecisionReadout",
    "DistributionKind",
    "EpisodeDistribution",
    "EpisodePublicOntology",
    "FrozenComparatorTypedDualGateB",
    "MetricName",
    "MetricRelation",
    "MetricRelationContract",
    "PublicActionKind",
    "ReadoutStage",
    "RuntimeAction",
    "RuntimeActionMapping",
    "RuntimeActionProjection",
    "canonical_comparator_specs_v0_8",
    "canonical_protocol_payload_v0_8",
    "load_frozen_protocol_v0_8",
    "make_runtime_action",
    "runtime_action_from_mapping",
    "score_frozen_gate_b_v0_8_diagnostic",
    "validate_protocol_payload_v0_8",
]
