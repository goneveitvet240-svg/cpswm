"""Immutable contracts for the first CHEH hidden-event vertical slice."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from math import isclose
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cpswm.contracts import (
    ActorResponsibilityEvidence,
    EventMechanismEvidence,
    EventType,
    RoleBindingEvidence,
)
from cpswm.contracts.base import ContractModel, NonNegativeInt, Probability, require_aware
from cpswm.system.reproducibility import content_sha256, content_uuid

HiddenEventEvidence = ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence


def hidden_event_evidence_semantic_fingerprint(evidence: HiddenEventEvidence) -> str:
    """Hash evidence semantics while ignoring caller-controlled wrapper IDs."""

    payload = evidence.model_dump(mode="python")
    metadata = dict(payload["metadata"])
    metadata.pop("record_id", None)
    payload["metadata"] = metadata
    payload.pop("evidence_cluster_id", None)
    # EvidenceRef.evidence_id, tuple order, and repeated copies are packaging,
    # not independent evidence semantics.  Canonicalize as a content set so a
    # caller cannot evade CHEH de-duplication by duplicating the same ref.
    semantic_references_by_hash: dict[str, dict] = {}
    for reference in payload["evidence_refs"]:
        semantic_reference = dict(reference)
        semantic_reference.pop("evidence_id", None)
        semantic_references_by_hash[content_sha256(semantic_reference)] = semantic_reference
    payload["evidence_refs"] = tuple(
        semantic_references_by_hash[fingerprint]
        for fingerprint in sorted(semantic_references_by_hash)
    )
    return content_sha256(payload)


def actor_evidence_semantic_fingerprint(
    evidence: ActorResponsibilityEvidence,
) -> str:
    """Backward-compatible actor-evidence specialization of the generic hash."""

    return hidden_event_evidence_semantic_fingerprint(evidence)


class EventHypothesisStatus(StrEnum):
    ACTIVE = "active"
    RETRACTED = "retracted"


class EventHypothesisUpdateKind(StrEnum):
    BRANCH = "branch"
    REVISE = "revise"
    REVISE_MECHANISM = "revise_mechanism"
    REVISE_ROLE = "revise_role"
    RETRACT = "retract"
    REACTIVATE = "reactivate"


class ActorEvidenceEndpointRole(StrEnum):
    """The immutable CHEH endpoint to which actor evidence is anchored."""

    SOURCE_STATE = "source_state"
    DESTINATION_STATE = "destination_state"


class HiddenEventStep(ContractModel):
    step_id: UUID
    sequence_no: NonNegativeInt
    event_type: EventType
    actor_key: str = Field(min_length=1)
    recipient_actor_key: str | None = None
    object_instance_id: UUID
    source_location_id: UUID | None = None
    destination_location_id: UUID | None = None
    event_time: datetime

    @field_validator("event_time")
    @classmethod
    def validate_event_time(cls, value: datetime) -> datetime:
        return require_aware(value, "event_time")

    @model_validator(mode="after")
    def validate_step(self) -> HiddenEventStep:
        if self.event_type == EventType.PICK_UP and self.source_location_id is None:
            raise ValueError("hidden pick-up step requires source_location_id")
        if self.event_type == EventType.PLACE and self.destination_location_id is None:
            raise ValueError("hidden place step requires destination_location_id")
        if self.event_type == EventType.TRANSFER:
            if self.recipient_actor_key is None:
                raise ValueError("hidden transfer step requires recipient_actor_key")
            if self.recipient_actor_key == self.actor_key:
                raise ValueError("transfer actor and recipient must differ")
        elif self.recipient_actor_key is not None:
            raise ValueError("only transfer steps can carry recipient_actor_key")
        return self


class EventChainHypothesis(ContractModel):
    hypothesis_id: UUID
    responsible_actor_key: str = Field(min_length=1)
    steps: tuple[HiddenEventStep, ...] = Field(min_length=2)
    posterior_probability: Probability
    # Shadow distribution over every originally generated chain.  It remains
    # normalized even when thresholding moves actual mass to unresolved, so a
    # later independent evidence record can audibly reactivate a true chain.
    revival_probability: Probability
    status: EventHypothesisStatus
    source_record_ids: tuple[UUID, ...] = Field(min_length=2)
    explanation_code: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_chain(self) -> EventChainHypothesis:
        sequence = [step.sequence_no for step in self.steps]
        if sequence != list(range(len(self.steps))):
            raise ValueError("hidden-event sequence numbers must be contiguous")
        times = [step.event_time for step in self.steps]
        if times != sorted(times) or len(times) != len(set(times)):
            raise ValueError("hidden-event steps must have strictly increasing times")
        object_ids = {step.object_instance_id for step in self.steps}
        if len(object_ids) != 1:
            raise ValueError("one hidden-event chain must concern one object")
        if self.steps[0].event_type != EventType.PICK_UP:
            raise ValueError("hidden-event chain must begin with pick-up")
        if self.steps[-1].event_type != EventType.PLACE:
            raise ValueError("hidden-event chain must end with place")
        event_types = tuple(step.event_type for step in self.steps)
        direct = (EventType.PICK_UP, EventType.CARRY, EventType.PLACE)
        handoff = (
            EventType.PICK_UP,
            EventType.CARRY,
            EventType.TRANSFER,
            EventType.PLACE,
        )
        if event_types not in {direct, handoff}:
            raise ValueError("hidden-event chain violates the supported physical grammar")
        if self.steps[0].actor_key != self.steps[1].actor_key:
            raise ValueError("hidden pick-up and initial carry require the same actor")
        if event_types == direct:
            if self.steps[-1].actor_key != self.steps[1].actor_key:
                raise ValueError("direct relocation must be placed by the carrying actor")
        else:
            transfer = self.steps[2]
            if transfer.actor_key != self.steps[1].actor_key:
                raise ValueError("handoff must be performed by the initial carrying actor")
            if transfer.recipient_actor_key != self.steps[-1].actor_key:
                raise ValueError("handoff recipient must perform the final placement")
        if self.steps[-1].actor_key != self.responsible_actor_key:
            raise ValueError("responsible actor must be the final placing actor")
        if self.status == EventHypothesisStatus.RETRACTED:
            if self.posterior_probability != 0.0:
                raise ValueError("retracted event hypothesis must have zero posterior")
        elif self.posterior_probability <= 0.0:
            raise ValueError("active event hypothesis requires positive posterior")
        if len(self.source_record_ids) != len(set(self.source_record_ids)):
            raise ValueError("event hypothesis source record IDs must be unique")
        return self


class EventHypothesisRevision(ContractModel):
    """One normalized, immutable version of an event-hypothesis hyperedge."""

    hypothesis_set_id: UUID
    revision_id: UUID
    revision_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision_no: NonNegativeInt
    parent_revision_id: UUID | None = None
    update_kind: EventHypothesisUpdateKind
    household_id: UUID
    session_id: UUID
    trace_id: UUID
    object_instance_id: UUID
    interval_start: datetime
    interval_end: datetime
    source_location_id: UUID
    destination_location_id: UUID
    source_detection_result_ids: tuple[UUID, UUID]
    hypotheses: tuple[EventChainHypothesis, ...] = Field(min_length=2)
    unresolved_probability: Probability
    revision_evidence_record_ids: tuple[UUID, ...] = Field(min_length=1)
    revision_evidence_cluster_ids: tuple[UUID, ...] = ()
    revision_evidence_semantic_fingerprints: tuple[str, ...] = ()
    revision_evidence_source_detection_result_ids: tuple[UUID, ...] = ()
    revision_evidence_endpoint_roles: tuple[ActorEvidenceEndpointRole, ...] = ()
    revision_reason: str = Field(min_length=1)
    engine_version: str = Field(min_length=1)

    @field_validator("interval_start", "interval_end")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return require_aware(value, info.field_name)

    @model_validator(mode="after")
    def validate_revision(self) -> EventHypothesisRevision:
        if self.interval_end <= self.interval_start:
            raise ValueError("hidden-event interval must be non-empty")
        if self.source_location_id == self.destination_location_id:
            raise ValueError("CHEH first slice requires a location transition")
        if self.revision_no == 0:
            if self.parent_revision_id is not None:
                raise ValueError("branch revision cannot have a parent revision")
            if self.update_kind != EventHypothesisUpdateKind.BRANCH:
                raise ValueError("revision zero must be a branch update")
        elif self.parent_revision_id is None:
            raise ValueError("non-initial revision requires parent_revision_id")

        hypothesis_ids = [item.hypothesis_id for item in self.hypotheses]
        if len(hypothesis_ids) != len(set(hypothesis_ids)):
            raise ValueError("event hypothesis IDs must be unique within a revision")
        total = self.unresolved_probability + sum(
            item.posterior_probability for item in self.hypotheses
        )
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("event hypothesis posteriors plus unresolved must sum to 1")
        revival_total = sum(item.revival_probability for item in self.hypotheses)
        if not isclose(revival_total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("event hypothesis revival probabilities must sum to 1")
        if (
            not any(item.status == EventHypothesisStatus.ACTIVE for item in self.hypotheses)
            and self.unresolved_probability < 1.0
        ):
            raise ValueError("a fully retracted set must assign all mass to unresolved")
        if len(self.revision_evidence_record_ids) != len(set(self.revision_evidence_record_ids)):
            raise ValueError("CHEH revision evidence record IDs must be unique")
        if len(self.revision_evidence_cluster_ids) != len(set(self.revision_evidence_cluster_ids)):
            raise ValueError("CHEH revision evidence cluster IDs must be unique")
        if len(self.revision_evidence_semantic_fingerprints) != len(
            set(self.revision_evidence_semantic_fingerprints)
        ):
            raise ValueError("CHEH revision evidence semantic fingerprints must be unique")
        if any(
            len(fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in fingerprint)
            for fingerprint in self.revision_evidence_semantic_fingerprints
        ):
            raise ValueError("CHEH evidence semantic fingerprints must be SHA-256 hex")
        if self.revision_no == 0:
            if self.revision_evidence_cluster_ids:
                raise ValueError("branch revision cannot consume actor evidence clusters")
            if self.revision_evidence_semantic_fingerprints:
                raise ValueError("branch revision cannot consume actor evidence fingerprints")
            if self.revision_evidence_source_detection_result_ids:
                raise ValueError("branch revision cannot bind actor evidence endpoints")
            if self.revision_evidence_endpoint_roles:
                raise ValueError("branch revision cannot bind actor evidence endpoint roles")
        elif not (
            len(self.revision_evidence_record_ids)
            == len(self.revision_evidence_cluster_ids)
            == len(self.revision_evidence_semantic_fingerprints)
            == len(self.revision_evidence_source_detection_result_ids)
            == len(self.revision_evidence_endpoint_roles)
        ):
            raise ValueError(
                "CHEH actor evidence records, clusters, fingerprints, endpoint IDs, "
                "and endpoint roles must align one-to-one"
            )
        if len(self.source_detection_result_ids) != len(set(self.source_detection_result_ids)):
            raise ValueError("CHEH endpoint detection IDs must be unique")
        endpoint_by_role = {
            ActorEvidenceEndpointRole.SOURCE_STATE: self.source_detection_result_ids[0],
            ActorEvidenceEndpointRole.DESTINATION_STATE: self.source_detection_result_ids[1],
        }
        for evidence_source, endpoint_role in zip(
            self.revision_evidence_source_detection_result_ids,
            self.revision_evidence_endpoint_roles,
            strict=True,
        ):
            if evidence_source != endpoint_by_role[endpoint_role]:
                raise ValueError("actor evidence endpoint role does not match its source detection")
        if self.revision_no == 0 and not set(self.source_detection_result_ids).issubset(
            self.revision_evidence_record_ids
        ):
            raise ValueError("branch revision must cite both endpoint detections")

        required_sources = set(self.source_detection_result_ids)
        revision_sources = set(self.revision_evidence_record_ids)
        for hypothesis in self.hypotheses:
            if not required_sources.issubset(hypothesis.source_record_ids):
                raise ValueError("every hypothesis must retain both endpoint detections")
            if not revision_sources.issubset(hypothesis.source_record_ids):
                raise ValueError("every hypothesis must retain current revision evidence")
            for step in hypothesis.steps:
                if step.object_instance_id != self.object_instance_id:
                    raise ValueError("hypothesis object does not match hypothesis set")
                if not self.interval_start < step.event_time < self.interval_end:
                    raise ValueError("hidden event must lie inside the observation interval")
            if hypothesis.steps[0].source_location_id != self.source_location_id:
                raise ValueError("hypothesis source location does not match set")
            if hypothesis.steps[-1].destination_location_id != self.destination_location_id:
                raise ValueError("hypothesis destination location does not match set")

        expected_hash = content_sha256(self.content_payload())
        if self.revision_content_sha256 != expected_hash:
            raise ValueError("revision_content_sha256 does not match revision content")
        expected_id = content_uuid("cheh-revision", self.content_payload())
        if self.revision_id != expected_id:
            raise ValueError("revision_id does not match revision content")
        return self

    def content_payload(self) -> dict:
        return self.model_dump(
            mode="json",
            exclude={"revision_id", "revision_content_sha256"},
        )

    @property
    def active_hypotheses(self) -> tuple[EventChainHypothesis, ...]:
        return tuple(
            item for item in self.hypotheses if item.status == EventHypothesisStatus.ACTIVE
        )

    @property
    def map_hypothesis(self) -> EventChainHypothesis | None:
        if not self.active_hypotheses:
            return None
        return sorted(
            self.active_hypotheses,
            key=lambda item: (-item.posterior_probability, str(item.hypothesis_id)),
        )[0]


class EventHypothesisHistory(ContractModel):
    """Append-only revisions that make CHEH state deterministic to rebuild."""

    hypothesis_set_id: UUID
    revisions: tuple[EventHypothesisRevision, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_history(self) -> EventHypothesisHistory:
        expected_numbers = list(range(len(self.revisions)))
        if [item.revision_no for item in self.revisions] != expected_numbers:
            raise ValueError("CHEH revision history must be contiguous")
        if any(item.hypothesis_set_id != self.hypothesis_set_id for item in self.revisions):
            raise ValueError("CHEH history cannot mix hypothesis sets")
        evidence_ids = [
            record_id
            for revision in self.revisions
            for record_id in revision.revision_evidence_record_ids
        ]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("CHEH evidence records cannot be reused across revisions")
        cluster_ids = [
            cluster_id
            for revision in self.revisions
            for cluster_id in revision.revision_evidence_cluster_ids
        ]
        if len(cluster_ids) != len(set(cluster_ids)):
            raise ValueError("CHEH evidence clusters cannot be reused across revisions")
        semantic_fingerprints = [
            fingerprint
            for revision in self.revisions
            for fingerprint in revision.revision_evidence_semantic_fingerprints
        ]
        if len(semantic_fingerprints) != len(set(semantic_fingerprints)):
            raise ValueError("CHEH semantic actor evidence cannot be reused across revisions")
        for previous, current in zip(self.revisions, self.revisions[1:], strict=False):
            if current.parent_revision_id != previous.revision_id:
                raise ValueError("CHEH revision parent binding is broken")
            immutable_bindings = (
                "household_id",
                "session_id",
                "trace_id",
                "object_instance_id",
                "interval_start",
                "interval_end",
                "source_location_id",
                "destination_location_id",
                "source_detection_result_ids",
                "engine_version",
            )
            for field_name in immutable_bindings:
                if getattr(current, field_name) != getattr(previous, field_name):
                    raise ValueError(f"CHEH revision changed immutable binding {field_name}")
            previous_hypotheses = {item.hypothesis_id: item for item in previous.hypotheses}
            current_hypotheses = {item.hypothesis_id: item for item in current.hypotheses}
            if set(current_hypotheses) != set(previous_hypotheses):
                raise ValueError("CHEH revision changed the hypothesis identity set")
            for hypothesis_id, current_hypothesis in current_hypotheses.items():
                previous_hypothesis = previous_hypotheses[hypothesis_id]
                for field_name in (
                    "responsible_actor_key",
                    "steps",
                    "explanation_code",
                ):
                    if getattr(current_hypothesis, field_name) != getattr(
                        previous_hypothesis, field_name
                    ):
                        raise ValueError(
                            f"CHEH revision changed immutable hypothesis field {field_name}"
                        )
                if not set(previous_hypothesis.source_record_ids).issubset(
                    current_hypothesis.source_record_ids
                ):
                    raise ValueError("CHEH revision discarded hypothesis provenance")
        return self

    @property
    def latest(self) -> EventHypothesisRevision:
        return self.revisions[-1]

    @property
    def consumed_evidence_record_ids(self) -> frozenset[UUID]:
        return frozenset(
            record_id
            for revision in self.revisions
            for record_id in revision.revision_evidence_record_ids
        )

    @property
    def consumed_evidence_cluster_ids(self) -> frozenset[UUID]:
        return frozenset(
            cluster_id
            for revision in self.revisions
            for cluster_id in revision.revision_evidence_cluster_ids
        )

    @property
    def consumed_evidence_semantic_fingerprints(self) -> frozenset[str]:
        return frozenset(
            fingerprint
            for revision in self.revisions
            for fingerprint in revision.revision_evidence_semantic_fingerprints
        )

    def append(self, revision: EventHypothesisRevision) -> EventHypothesisHistory:
        return EventHypothesisHistory(
            hypothesis_set_id=self.hypothesis_set_id,
            revisions=(*self.revisions, revision),
        )
