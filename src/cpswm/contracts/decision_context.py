"""DecisionContext: enforced belief<->map<->task consistency (结构二 §4.6, 总纲 §2.12).

Rebuilt 2026-08-22 after review.  A DecisionContext is not an optional sidecar:
it pins the *exact* belief snapshot, projection version, static/dynamic map
revisions, and event-history revision a decision was made against, plus an input
watermark, model/code hashes, a valid-time window, and a content hash.  Because
every consistency field is mandatory, a context cannot be constructed without
declaring which world state it is consistent with.

Concurrency model: **snapshot isolation + invalidation** (the map keeps updating
asynchronously; a task fixes one snapshot via the pinned revisions, and
:func:`detect_relevant_change` is run before execution to decide continue /
replan / cancel).  Strict serialization (pause-execution-on-any-map-update) is
the stricter alternative and can be layered on top by treating *every* revision
delta as relevant; it is not the default because it needlessly serializes
irrelevant updates.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .base import BaseRecordMetadata, ContractModel, Probability, ValidTimeInterval, require_aware


class DecisionSurface(StrEnum):
    TASK_REQUEST = "task_request"
    MAP_SNAPSHOT = "map_snapshot"
    EXECUTION_FEEDBACK = "execution_feedback"


class AttributedCause(StrEnum):
    """The change cause a decision was attributed to (no free-text)."""

    OBSERVATION = "observation"
    ACTOR = "actor"
    HABIT = "habit"
    NOISE = "noise"
    NONE = "none"
    UNRESOLVED = "unresolved"


class RelevantChange(StrEnum):
    CONTINUE = "continue"
    REPLAN = "replan"
    CANCEL = "cancel"


class TargetPresenceBeliefRef(ContractModel):
    """A target-presence prior bound to the exact belief node it was read from.

    The prior is not a free scalar: it is tied to an object, a location, a belief
    node id, the snapshot the node lives in, and that node's content hash, so a
    consumer can verify the prior belongs to *this* object/location/snapshot (and
    later reconcile ``node_content_hash`` against the live map, review fix #4 tail).
    """

    object_instance_id: UUID
    location_id: UUID
    belief_node_id: str = Field(min_length=1)
    belief_snapshot_id: UUID
    node_content_hash: str = Field(min_length=1)
    prior_probability: Probability


class MapConsistencyRevisions(ContractModel):
    """The exact world-state versions a decision was made against."""

    belief_snapshot_id: UUID
    projection_id: UUID
    projection_version: int = Field(ge=0)
    static_map_revision: int = Field(ge=0)
    dynamic_map_revision: int = Field(ge=0)
    event_history_revision: int = Field(ge=0)
    input_watermark: int = Field(ge=0)


class DecisionContext(ContractModel):
    """Belief/map/version provenance a decision is consistent with.

    All consistency fields are mandatory; ``context_hash`` binds them so a
    context cannot silently drift, and ``model_versions`` is an immutable, sorted
    tuple so its inner values cannot be tampered with after construction.
    """

    decision_id: UUID
    decision_time: datetime
    valid_time: ValidTimeInterval
    staleness_budget_seconds: float = Field(ge=0.0)
    revisions: MapConsistencyRevisions
    attributed_cause: AttributedCause = AttributedCause.UNRESOLVED
    segment_change_probability: Probability | None = None
    transient_noise_probability: Probability | None = None
    #: Target-presence prior the decision was made against, bound to its belief
    #: node/snapshot; feedback projection reads its prior from here, never from
    #: an arbitrary caller argument.  (Adding this field changes context_hash, so
    #: any persisted pre-field context needs a version/migration.)
    target_presence_belief: TargetPresenceBeliefRef | None = None
    consolidation_ledger_ref: str | None = None
    authorization_scope_id: UUID
    habit_regime_model_version: str = Field(min_length=1)
    model_versions: tuple[tuple[str, str], ...]
    code_version: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    #: Computed content hash. Left empty on input it is filled; supplied it is
    #: cross-checked, so a tampered persisted context fails to reload.
    context_hash: str = ""

    @field_validator("decision_time")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        return require_aware(value, "decision_time")

    @field_validator("model_versions")
    @classmethod
    def _sorted_unique_versions(
        cls, value: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[str, str], ...]:
        names = [name for name, _ in value]
        if len(names) != len(set(names)):
            raise ValueError("model_versions names must be unique")
        if list(value) != sorted(value):
            raise ValueError("model_versions must be sorted for a stable hash")
        return value

    @model_validator(mode="after")
    def _fill_or_check_hash(self) -> DecisionContext:
        expected = self.compute_hash()
        if not self.context_hash:
            object.__setattr__(self, "context_hash", expected)
        elif self.context_hash != expected:
            raise ValueError("context_hash does not match the decision context content")
        return self

    def verify_hash(self) -> bool:
        return self.context_hash == self.compute_hash()

    def compute_hash(self) -> str:
        payload = {
            "decision_id": str(self.decision_id),
            "decision_time": self.decision_time.isoformat(),
            "valid_time": [
                self.valid_time.start.isoformat(),
                self.valid_time.end.isoformat() if self.valid_time.end else None,
            ],
            "staleness_budget_seconds": repr(self.staleness_budget_seconds),
            "revisions": self.revisions.model_dump(mode="json"),
            "attributed_cause": self.attributed_cause.value,
            "segment_change_probability": repr(self.segment_change_probability),
            "transient_noise_probability": repr(self.transient_noise_probability),
            "target_presence_belief": (
                self.target_presence_belief.model_dump(mode="json")
                if self.target_presence_belief is not None
                else None
            ),
            "consolidation_ledger_ref": self.consolidation_ledger_ref,
            "authorization_scope_id": str(self.authorization_scope_id),
            "habit_regime_model_version": self.habit_regime_model_version,
            "model_versions": [list(item) for item in self.model_versions],
            "code_version": self.code_version,
            "rationale": self.rationale,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    @classmethod
    def create(cls, **fields: object) -> DecisionContext:
        """Build a context; the content hash is filled automatically.

        Missing mandatory consistency fields raise a validation error here,
        because they have no defaults.
        """

        return cls(**fields)  # type: ignore[arg-type]


class DecisionContextBinding(ContractModel):
    """Append-only binding of one DecisionContext to a downstream record.

    The binding checks that the bound record shares the context's household /
    session / trace so a context cannot be reused across unrelated records to
    hide intervening version changes.
    """

    metadata: BaseRecordMetadata
    surface: DecisionSurface
    subject_record_id: UUID
    subject_household_id: UUID
    subject_session_id: UUID
    subject_trace_id: UUID
    decision_context: DecisionContext

    @model_validator(mode="after")
    def _validate_binding(self) -> DecisionContextBinding:
        if self.subject_household_id != self.metadata.household_id:
            raise ValueError("bound record household does not match the binding household")
        if self.subject_session_id != self.metadata.session_id:
            raise ValueError("bound record session does not match the binding session")
        if self.subject_trace_id != self.metadata.trace_id:
            raise ValueError("bound record trace does not match the binding trace")
        return self


def detect_relevant_change(
    context: DecisionContext,
    *,
    current: MapConsistencyRevisions,
    target_object_moved: bool,
    robot_pose_graph_corrected: bool,
    planned_path_blocked: bool,
    only_irrelevant_updates: bool,
    elapsed_seconds: float,
) -> RelevantChange:
    """Snapshot-isolation invalidation check to run before execution.

    Rules (总纲 §2.12 / 结构二 §4.6):
    - target object moved, robot pose graph corrected, or planned path blocked -> REPLAN;
    - staleness budget exceeded -> CANCEL (re-acquire a snapshot);
    - only irrelevant rooms/objects changed -> CONTINUE.
    """

    if elapsed_seconds > context.staleness_budget_seconds:
        return RelevantChange.CANCEL
    if target_object_moved or robot_pose_graph_corrected or planned_path_blocked:
        return RelevantChange.REPLAN
    # A dynamic-map revision bump that only touched irrelevant objects is allowed.
    if current.dynamic_map_revision != context.revisions.dynamic_map_revision:
        return RelevantChange.CONTINUE if only_irrelevant_updates else RelevantChange.REPLAN
    if current.static_map_revision != context.revisions.static_map_revision:
        return RelevantChange.REPLAN
    return RelevantChange.CONTINUE
