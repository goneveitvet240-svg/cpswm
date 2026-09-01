"""S3-DG-14D revision-aware neuro-symbolic evidence graph.

Model/VLM outputs are proposals, never truth.  A separate verifier revision is
required before person or event evidence becomes active, and habit activation
is derived only from a currently verified event revision.  Retraction leaves
history intact and automatically removes downstream habit activations from the
active projection.
"""

from __future__ import annotations

from enum import StrEnum
from math import isclose
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, EvidenceRef, Probability
from cpswm.contracts.events import EventType


class EvidenceClaimKind(StrEnum):
    PERSON = "person"
    EVENT = "event"


class EvidenceProposalSource(StrEnum):
    VLM = "vlm"
    SENSOR = "sensor"
    GEOMETRY = "geometry"
    USER = "user"
    ACTION = "action"


class EvidenceClaimStatus(StrEnum):
    PROPOSED = "proposed"
    VERIFIED = "verified"
    REJECTED = "rejected"
    RETRACTED = "retracted"
    SUPERSEDED = "superseded"


class EvidenceRevisionAction(StrEnum):
    VERIFY = "verify"
    REJECT = "reject"
    RETRACT = "retract"
    SUPERSEDE = "supersede"
    REACTIVATE = "reactivate"


class NeuroSymbolicEvidenceProposal(ContractModel):
    """One uncertain person or event claim proposed by a fallible source."""

    claim_id: UUID = Field(default_factory=uuid4)
    claim_kind: EvidenceClaimKind
    object_instance_id: UUID
    actor_posterior: dict[str, Probability] = Field(min_length=1)
    event_type: EventType | None = None
    source_location_id: UUID | None = None
    destination_location_id: UUID | None = None
    proposal_probability: Probability
    proposal_source: EvidenceProposalSource
    model_version: str = Field(min_length=1)
    calibration_domain: str = Field(min_length=1)
    evidence_cluster_ids: tuple[UUID, ...] = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1)
    source_person_claim_ids: tuple[UUID, ...] = ()
    authorization_scope_id: UUID | None = None

    @model_validator(mode="after")
    def _proposal_semantics(self) -> NeuroSymbolicEvidenceProposal:
        if len(self.evidence_cluster_ids) != len(set(self.evidence_cluster_ids)):
            raise ValueError("proposal evidence clusters must be unique")
        if len(self.source_person_claim_ids) != len(set(self.source_person_claim_ids)):
            raise ValueError("source person claims must be unique")
        if not isclose(sum(self.actor_posterior.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("proposal actor posterior must sum to one")
        if any(not actor.strip() for actor in self.actor_posterior):
            raise ValueError("proposal actor keys must be non-empty")
        if self.claim_kind is EvidenceClaimKind.PERSON:
            if self.event_type is not None:
                raise ValueError("a person claim cannot carry an event type")
            if self.source_location_id is not None or self.destination_location_id is not None:
                raise ValueError("a person claim cannot carry an event transition")
            if self.source_person_claim_ids:
                raise ValueError("a person claim cannot depend on other person claims")
            if self.authorization_scope_id is None:
                raise ValueError("person evidence requires an explicit authorization scope")
        else:
            if self.event_type is None:
                raise ValueError("an event claim requires an event type")
            if self.event_type is EventType.PICK_UP and self.source_location_id is None:
                raise ValueError("pick-up event proposal requires a source location")
            if self.event_type is EventType.PLACE and self.destination_location_id is None:
                raise ValueError("place event proposal requires a destination location")
        return self


class EvidenceRevisionRecord(ContractModel):
    """Immutable state transition for one evidence claim."""

    revision_id: UUID = Field(default_factory=uuid4)
    claim_id: UUID
    parent_revision_id: UUID | None
    action: EvidenceRevisionAction
    verified_probability: Probability
    verifier_model_version: str = Field(min_length=1)
    calibration_domain: str = Field(min_length=1)
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1)
    replacement_claim_id: UUID | None = None
    authorization_scope_id: UUID | None = None

    @model_validator(mode="after")
    def _revision_shape(self) -> EvidenceRevisionRecord:
        if self.action is EvidenceRevisionAction.SUPERSEDE:
            if self.replacement_claim_id is None or self.replacement_claim_id == self.claim_id:
                raise ValueError("superseding revision requires a distinct replacement claim")
        elif self.replacement_claim_id is not None:
            raise ValueError("only a superseding revision may identify a replacement claim")
        inactive_actions = {
            EvidenceRevisionAction.REJECT,
            EvidenceRevisionAction.RETRACT,
            EvidenceRevisionAction.SUPERSEDE,
        }
        if self.action in inactive_actions and self.verified_probability != 0.0:
            raise ValueError("inactive evidence revisions must set verified probability to zero")
        if (
            self.action in {EvidenceRevisionAction.VERIFY, EvidenceRevisionAction.REACTIVATE}
            and self.verified_probability <= 0.0
        ):
            raise ValueError("active evidence revisions require positive verified probability")
        return self


class HabitEvidenceActivation(ContractModel):
    """Derived habit evidence, anchored to a verified event revision."""

    activation_id: UUID = Field(default_factory=uuid4)
    source_event_claim_id: UUID
    source_event_revision_id: UUID
    actor_key: str = Field(min_length=1)
    object_instance_id: UUID
    location_id: UUID
    context_key: str = Field(min_length=1)
    soft_count: float = Field(gt=0.0)
    model_version: str = Field(min_length=1)
    calibration_domain: str = Field(min_length=1)
    observation_opportunity_id: UUID
    evidence_refs: tuple[EvidenceRef, ...] = Field(min_length=1)


class EvidenceClaimProjection(ContractModel):
    proposal: NeuroSymbolicEvidenceProposal
    head_revision_id: UUID | None
    status: EvidenceClaimStatus
    verified_probability: Probability


class RevisionAwareEvidenceGraph:
    """Append-only revisions with a rebuildable active evidence projection."""

    def __init__(self) -> None:
        self._proposals: dict[UUID, NeuroSymbolicEvidenceProposal] = {}
        self._revisions: list[EvidenceRevisionRecord] = []
        self._revision_by_id: dict[UUID, EvidenceRevisionRecord] = {}
        self._head_by_claim: dict[UUID, UUID] = {}
        self._status_by_claim: dict[UUID, EvidenceClaimStatus] = {}
        self._probability_by_claim: dict[UUID, float] = {}
        self._habit_activations: list[HabitEvidenceActivation] = []
        self._consumed_evidence_clusters: set[UUID] = set()
        self._consumed_observation_opportunities: set[UUID] = set()

    @property
    def revision_log(self) -> tuple[EvidenceRevisionRecord, ...]:
        return tuple(self._revisions)

    def append_proposal(self, proposal: NeuroSymbolicEvidenceProposal) -> None:
        proposal = NeuroSymbolicEvidenceProposal.model_validate(proposal.model_dump(mode="python"))
        if proposal.claim_id in self._proposals:
            raise ValueError("evidence claim already exists")
        duplicate_clusters = set(proposal.evidence_cluster_ids) & self._consumed_evidence_clusters
        if duplicate_clusters:
            raise ValueError("correlated evidence cluster cannot create a second independent claim")
        for person_claim_id in proposal.source_person_claim_ids:
            projection = self.projection(person_claim_id)
            if projection.proposal.claim_kind is not EvidenceClaimKind.PERSON:
                raise ValueError("event source_person_claim_ids must reference person claims")
            if not self.claim_is_active(person_claim_id):
                raise ValueError("event proposal may cite only currently verified person claims")
            if proposal.authorization_scope_id != projection.proposal.authorization_scope_id:
                raise ValueError(
                    "event and cited person evidence require the same authorization scope"
                )
        self._proposals[proposal.claim_id] = proposal
        self._status_by_claim[proposal.claim_id] = EvidenceClaimStatus.PROPOSED
        self._probability_by_claim[proposal.claim_id] = proposal.proposal_probability
        self._consumed_evidence_clusters.update(proposal.evidence_cluster_ids)

    def append_revision(self, revision: EvidenceRevisionRecord) -> None:
        revision = EvidenceRevisionRecord.model_validate(revision.model_dump(mode="python"))
        if revision.revision_id in self._revision_by_id:
            raise ValueError("evidence revision ID already exists")
        proposal = self._proposals.get(revision.claim_id)
        if proposal is None:
            raise LookupError("evidence revision references an unknown claim")
        expected_parent = self._head_by_claim.get(revision.claim_id)
        if revision.parent_revision_id != expected_parent:
            raise ValueError("evidence revision must extend the current claim head")
        if proposal.authorization_scope_id != revision.authorization_scope_id:
            raise ValueError("evidence revision authorization scope must match its proposal")
        current = self._status_by_claim[revision.claim_id]
        next_status = self._transition(current, revision.action)
        if next_status is EvidenceClaimStatus.VERIFIED:
            for person_claim_id in proposal.source_person_claim_ids:
                if not self.claim_is_active(person_claim_id):
                    raise ValueError("event verification requires currently active person evidence")
        if revision.action is EvidenceRevisionAction.SUPERSEDE:
            replacement_claim_id = revision.replacement_claim_id
            if replacement_claim_id is None:  # defended again at the mutable graph boundary
                raise ValueError("superseding revision requires a replacement evidence claim")
            replacement = self._proposals.get(replacement_claim_id)
            if replacement is None:
                raise ValueError("replacement evidence claim must exist before superseding")
            if replacement.claim_kind is not proposal.claim_kind:
                raise ValueError("replacement evidence claim must preserve the claim kind")
            if replacement.object_instance_id != proposal.object_instance_id:
                raise ValueError("replacement evidence claim must preserve the object identity")
            if replacement.authorization_scope_id != proposal.authorization_scope_id:
                raise ValueError("replacement evidence claim must preserve authorization scope")

        self._revisions.append(revision)
        self._revision_by_id[revision.revision_id] = revision
        self._head_by_claim[revision.claim_id] = revision.revision_id
        self._status_by_claim[revision.claim_id] = next_status
        self._probability_by_claim[revision.claim_id] = revision.verified_probability

    def append_habit_activation(self, activation: HabitEvidenceActivation) -> None:
        activation = HabitEvidenceActivation.model_validate(activation.model_dump(mode="python"))
        if any(item.activation_id == activation.activation_id for item in self._habit_activations):
            raise ValueError("habit activation ID already exists")
        if activation.observation_opportunity_id in self._consumed_observation_opportunities:
            raise ValueError("one observation opportunity cannot create duplicate habit evidence")
        projection = self.projection(activation.source_event_claim_id)
        if projection.proposal.claim_kind is not EvidenceClaimKind.EVENT:
            raise ValueError("habit evidence must be derived from an event claim")
        if not self.claim_is_active(activation.source_event_claim_id):
            raise ValueError("habit evidence requires a currently verified event")
        if projection.head_revision_id != activation.source_event_revision_id:
            raise ValueError("habit evidence must bind the current verified event revision")
        if projection.proposal.object_instance_id != activation.object_instance_id:
            raise ValueError("habit evidence object must match its source event")
        if activation.actor_key not in projection.proposal.actor_posterior:
            raise ValueError("habit actor must be in the source event actor posterior")
        expected_location = (
            projection.proposal.destination_location_id or projection.proposal.source_location_id
        )
        if activation.location_id != expected_location:
            raise ValueError("habit location must match the source event transition")
        max_soft_count = (
            projection.verified_probability
            * projection.proposal.actor_posterior[activation.actor_key]
        )
        if activation.soft_count > max_soft_count + 1e-12:
            raise ValueError("habit soft count cannot exceed verified event and actor mass")
        self._habit_activations.append(activation)
        self._consumed_observation_opportunities.add(activation.observation_opportunity_id)

    def projection(self, claim_id: UUID) -> EvidenceClaimProjection:
        proposal = self._proposals.get(claim_id)
        if proposal is None:
            raise LookupError("unknown evidence claim")
        return EvidenceClaimProjection(
            proposal=proposal,
            head_revision_id=self._head_by_claim.get(claim_id),
            status=self._status_by_claim[claim_id],
            verified_probability=self._probability_by_claim[claim_id],
        )

    def claim_is_active(self, claim_id: UUID) -> bool:
        """Return whether a verified claim still has an active dependency chain."""

        projection = self.projection(claim_id)
        if projection.status is not EvidenceClaimStatus.VERIFIED:
            return False
        return all(
            self.claim_is_active(person_claim_id)
            for person_claim_id in projection.proposal.source_person_claim_ids
        )

    def active_habit_activations(self) -> tuple[HabitEvidenceActivation, ...]:
        active: list[HabitEvidenceActivation] = []
        for activation in self._habit_activations:
            projection = self.projection(activation.source_event_claim_id)
            if (
                self.claim_is_active(activation.source_event_claim_id)
                and projection.head_revision_id == activation.source_event_revision_id
            ):
                active.append(activation)
        return tuple(active)

    @staticmethod
    def _transition(
        current: EvidenceClaimStatus,
        action: EvidenceRevisionAction,
    ) -> EvidenceClaimStatus:
        allowed = {
            EvidenceClaimStatus.PROPOSED: {
                EvidenceRevisionAction.VERIFY: EvidenceClaimStatus.VERIFIED,
                EvidenceRevisionAction.REJECT: EvidenceClaimStatus.REJECTED,
            },
            EvidenceClaimStatus.VERIFIED: {
                EvidenceRevisionAction.RETRACT: EvidenceClaimStatus.RETRACTED,
                EvidenceRevisionAction.SUPERSEDE: EvidenceClaimStatus.SUPERSEDED,
            },
            EvidenceClaimStatus.RETRACTED: {
                EvidenceRevisionAction.REACTIVATE: EvidenceClaimStatus.VERIFIED,
            },
        }
        try:
            return allowed[current][action]
        except KeyError as exc:
            raise ValueError(
                f"invalid evidence revision transition: {current.value} -> {action.value}"
            ) from exc
