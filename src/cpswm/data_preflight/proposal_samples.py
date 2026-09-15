"""Full-axis proposal *data* contract; no model, sampler, or ledger authority.

Targets describe reviewed compatible transitions, not unique oracle actions.
Validation establishes internal consistency, not authenticity of an annotator.
Only ``model_input`` is visible to the proposer; labels and custody stay separate.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, require_aware
from cpswm.contracts.habit_learning import (
    ActorResponsibilityEvidence,
    ObservationDetectionResult,
    ObservationOpportunityRecord,
)
from cpswm.data_preflight.visible_prefix import VisiblePrefix, export_visible_prefix
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleProposalOperation,
    TypedParticleState,
)
from cpswm.system.reproducibility import content_sha256


class EventNode(ContractModel):
    event_id: UUID
    time: datetime
    kind: Literal["pick_up", "carry", "handoff", "place", "no_move", "unresolved"]
    instance_key: str = Field(min_length=1)
    actor_key: str = Field(min_length=1)
    receiver_key: str | None = None
    location_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_node(self) -> Self:
        require_aware(self.time, "event time")
        if self.kind == "handoff":
            if not self.receiver_key or self.receiver_key == self.actor_key:
                raise ValueError("handoff requires a distinct receiver")
        elif self.receiver_key is not None:
            raise ValueError("only handoff has a receiver")
        return self


class FullHypothesis(ContractModel):
    state: TypedParticleState
    events: tuple[EventNode, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_chain(self) -> Self:
        ids = [x.event_id for x in self.events]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate event in chain")
        if any(a.time >= b.time for a, b in zip(self.events, self.events[1:], strict=False)):
            raise ValueError("chain must be strictly chronological")
        if any(x.instance_key != self.state.instance_association_key for x in self.events):
            raise ValueError("event and particle instance association disagree")
        # One world-line per particle. A sample can contain competing instances.
        # First occurrences use frozen role names; later occurrences use :2, :3, ...
        # to preserve a complete multi-hop order without violating unique role keys.
        roles: list[tuple[str, str]] = []
        role_counts: Counter[str] = Counter()

        def append_role(role: str, actor: str) -> None:
            role_counts[role] += 1
            key = role if role_counts[role] == 1 else f"{role}:{role_counts[role]}"
            roles.append((key, actor))

        holder: str | None = None
        finished = False
        for index, event in enumerate(self.events):
            if finished:
                raise ValueError("events after terminal place/no-move/unresolved")
            if event.kind in {"no_move", "unresolved"}:
                if len(self.events) != 1:
                    raise ValueError("no-move/unresolved is a singleton hypothesis")
                finished = True
            elif event.kind == "pick_up":
                if index != 0:
                    raise ValueError("pickup must start a chain")
                holder = event.actor_key
                append_role("pickup_actor", holder)
            elif event.kind == "carry":
                if holder is None or event.actor_key != holder:
                    raise ValueError("carrier must be the current holder")
                append_role("carrier", holder)
            elif event.kind == "handoff":
                if holder is None or event.actor_key != holder:
                    raise ValueError("invalid handoff giver")
                if not any(role == "carrier" for role, _ in roles):
                    raise ValueError("handoff requires preceding carry")
                append_role("handoff_giver", holder)
                append_role("handoff_receiver", event.receiver_key or "")
                holder = event.receiver_key
            elif event.kind == "place":
                if holder is None or event.actor_key != holder:
                    raise ValueError("placer must be the current holder")
                if not any(role == "carrier" for role, _ in roles):
                    raise ValueError("place requires preceding carry")
                append_role("placer", holder)
                finished = True
        if not finished:
            raise ValueError(
                "full chain needs a terminal event; use unresolved for incomplete support"
            )
        if roles != [(x.role, x.actor_key) for x in self.state.ordered_actor_roles]:
            raise ValueError("ordered roles must exactly match the full event chain")
        return self


class Arrival(ContractModel):
    record_id: UUID
    received_at: datetime


class VisibleRecords(ContractModel):
    opportunities: tuple[ObservationOpportunityRecord, ...]
    detections: tuple[ObservationDetectionResult, ...]
    actor_evidence: tuple[ActorResponsibilityEvidence, ...] = ()
    arrivals: tuple[Arrival, ...]
    cutoff: datetime

    def prefix(self) -> VisiblePrefix:
        if len({x.record_id for x in self.arrivals}) != len(self.arrivals):
            raise ValueError("duplicate arrival entry")
        return export_visible_prefix(
            self.opportunities,
            self.detections,
            actor_evidence=self.actor_evidence,
            received_at={x.record_id: x.received_at for x in self.arrivals},
            cutoff=self.cutoff,
        )


class RevisionRecord(ContractModel):
    revision_id: UUID
    parent_revision_id: UUID | None
    particle_id: UUID
    event_hypothesis_id: UUID
    ledger_lineage_ref: str = Field(min_length=1)
    statistic_state_ref: str = Field(min_length=1)
    status: Literal["active", "retracted"]


class ProposalTarget(ContractModel):
    operation: ParticleProposalOperation
    candidate: FullHypothesis
    evidence_ids: tuple[UUID, ...] = Field(min_length=1)
    # Rejuvenation is suffix replacement, never an append-only new fact.
    replaced_revision_ids: tuple[UUID, ...] = ()
    replay_required: bool = False


class SnapshotLocation(ContractModel):
    location_key: str = Field(min_length=1)
    location_entity_id: UUID


class LocationBinding(ContractModel):
    """A name's declared source, not authentication of a snapshot/annotator."""

    location_key: str = Field(min_length=1)
    origin: Literal["snapshot", "visible_evidence", "unknown"]
    source_snapshot_id: UUID | None = None
    source_record_id: UUID | None = None
    location_entity_id: UUID | None = None

    @model_validator(mode="after")
    def validate_origin(self) -> Self:
        if self.origin == "unknown":
            if self.location_key != "unknown_location" or any(
                (self.source_snapshot_id, self.source_record_id, self.location_entity_id)
            ):
                raise ValueError("unknown location cannot pretend to have a resolved source")
        elif self.location_key == "unknown_location" or self.location_entity_id is None:
            raise ValueError("resolved location requires an entity identity")
        elif self.origin == "snapshot":
            if self.source_snapshot_id is None or self.source_record_id is not None:
                raise ValueError("snapshot location must name exactly its snapshot source")
        elif self.source_record_id is None or self.source_snapshot_id is not None:
            raise ValueError("discovered location must name exactly its visible record")
        return self


class ProposalContext(ContractModel):
    """Runtime-visible context, with no targets or annotation metadata."""

    source_snapshot_id: UUID
    visible: VisibleRecords
    parents: tuple[FullHypothesis, ...]
    revisions: tuple[RevisionRecord, ...]
    instance_support: tuple[str, ...]
    actor_support: tuple[str, ...]
    location_support: tuple[LocationBinding, ...] = Field(min_length=1)
    snapshot_location_catalog: tuple[SnapshotLocation, ...] = ()

    @model_validator(mode="after")
    def validate_context(self) -> Self:
        self.visible.prefix()  # validates missing/negative/arrival/source distinctions
        require_aware(self.visible.cutoff, "cutoff")
        locations = {x.location_key: x for x in self.location_support}
        if len(locations) != len(self.location_support) or "unknown_location" not in locations:
            raise ValueError("unique location support and explicit unknown required")
        visible_ids = {
            UUID(x["record_id"])
            for x in json.loads(self.visible.prefix().provenance_json)["included_records"]
        }
        detections = {x.metadata.record_id: x for x in self.visible.detections}
        catalog = {x.location_key: x.location_entity_id for x in self.snapshot_location_catalog}
        if (
            len(catalog) != len(self.snapshot_location_catalog)
            or len(set(catalog.values())) != len(catalog)
            or "unknown_location" in catalog
        ):
            raise ValueError("snapshot location catalog must contain distinct resolved entities")
        entities = set()
        for binding in self.location_support:
            if binding.location_entity_id is not None:
                if binding.location_entity_id in entities:
                    raise ValueError("resolved location entity has multiple aliases")
                entities.add(binding.location_entity_id)
            if binding.origin == "snapshot" and (
                binding.source_snapshot_id != self.source_snapshot_id
                or catalog.get(binding.location_key) != binding.location_entity_id
            ):
                raise ValueError("location does not resolve in the frozen snapshot catalog")
            if binding.origin == "visible_evidence":
                record = (
                    detections.get(binding.source_record_id) if binding.source_record_id else None
                )
                if (
                    binding.source_record_id not in visible_ids
                    or record is None
                    or record.detected_location_id != binding.location_entity_id
                ):
                    raise ValueError("location discovery must resolve to an arrived detection")
        if (
            "unknown_instance" not in self.instance_support
            or "unknown_actor" not in self.actor_support
        ):
            raise ValueError("explicit unknown supports required")
        for support in (self.instance_support, self.actor_support):
            if len(set(support)) != len(support) or any(not x.strip() for x in support):
                raise ValueError("support must be nonempty and unique")
        parents = {x.state.particle_id: x for x in self.parents}
        revisions = {x.revision_id: x for x in self.revisions}
        if len(parents) != len(self.parents) or len(revisions) != len(self.revisions):
            raise ValueError("duplicate parent/revision")
        # Ordered DAG; no forward references, cycles, cross-ledger ancestry, or orphan roots.
        seen: dict[UUID, RevisionRecord] = {}
        for revision in self.revisions:
            if revision.parent_revision_id is not None:
                ancestor = seen.get(revision.parent_revision_id)
                if ancestor is None or ancestor.ledger_lineage_ref != revision.ledger_lineage_ref:
                    raise ValueError("broken revision ancestry or cross-ledger lineage")
            seen[revision.revision_id] = revision
        bound_revisions = set()
        for hypothesis in self.parents:
            self._check_hypothesis(hypothesis)
            state = hypothesis.state
            ref = revisions.get(state.revision_id)
            if ref is None or (
                ref.particle_id,
                ref.event_hypothesis_id,
                ref.parent_revision_id,
                ref.ledger_lineage_ref,
                ref.statistic_state_ref,
            ) != (
                state.particle_id,
                state.event_hypothesis_id,
                state.parent_revision_id,
                state.ledger_lineage_ref,
                state.statistic_state_ref,
            ):
                raise ValueError("parent particle must resolve its event/statistic/ledger revision")
            if state.parent_revision_id is None:
                if state.parent_particle_id is not None:
                    raise ValueError("root revision cannot carry an orphan particle parent")
            else:
                ancestor = revisions[state.parent_revision_id]
                if state.parent_particle_id != ancestor.particle_id:
                    raise ValueError("particle ancestry and revision ancestry disagree")
            bound_revisions.add(state.revision_id)
        if bound_revisions != set(revisions):
            raise ValueError("unreferenced revision metadata")
        return self

    def validate_candidates(self, targets: tuple[ProposalTarget, ...]) -> None:
        """Validate runtime proposals using the same native rules as supervision."""
        if not targets:
            raise ValueError("empty runtime proposal support")
        parents = {x.state.particle_id: x for x in self.parents}
        revisions = {x.revision_id: x for x in self.revisions}
        arrivals = {x.record_id: x.received_at for x in self.visible.arrivals}
        # References must be visible in the *exported* prefix, not just in a raw bundle.
        prefix = self.visible.prefix()
        provenance = json.loads(prefix.provenance_json)
        visible_ids = {UUID(x["record_id"]) for x in provenance["included_records"]}
        candidate_ids: set[UUID] = set()
        candidate_revisions: set[UUID] = set()
        for target in targets:
            self._check_hypothesis(target.candidate)
            state = target.candidate.state
            if state.particle_id in parents or state.particle_id in candidate_ids:
                raise ValueError("candidate must have a unique new particle identity")
            if state.revision_id in revisions or state.revision_id in candidate_revisions:
                raise ValueError("candidate must have a unique new revision identity")
            candidate_ids.add(state.particle_id)
            candidate_revisions.add(state.revision_id)
            if (
                len(set(target.evidence_ids)) != len(target.evidence_ids)
                or not set(target.evidence_ids) <= visible_ids
            ):
                raise ValueError("target cites duplicate, future or non-visible evidence")
            parent = parents.get(state.parent_particle_id) if state.parent_particle_id else None
            if (
                not parents
                and state.parent_particle_id is None
                and state.parent_revision_id is None
                and target.operation.value == "preserve_unresolved"
                and state.change_cause.value == "unresolved"
                and state.regime_decision.value == "unresolved"
                and not target.replaced_revision_ids
                and not target.replay_required
            ):
                # Genuine empty-context bootstrap, not a fabricated resolved seed particle.
                continue
            if parent is None or state.parent_revision_id != parent.state.revision_id:
                raise ValueError("proposal parent/revision must resolve in the frozen context")
            if state.ledger_lineage_ref != parent.state.ledger_lineage_ref:
                raise ValueError("proposal cannot switch ledger lineage")
            old = revisions[parent.state.revision_id]
            operation = target.operation.value
            if operation == "reactivate":
                if old.status != "retracted":
                    raise ValueError("reactivate requires a retracted source revision")
            elif old.status != "active":
                raise ValueError("only reactivate can propose from a retracted source")
            if operation == "retract":  # noqa: SIM102 - explicit operation guard
                if semantic_state(target.candidate) != semantic_state(parent):
                    raise ValueError(
                        "retract labels a removal, not an unrelated changed hypothesis"
                    )
            if operation == "preserve_unresolved":  # noqa: SIM102 - explicit operation guard
                if (
                    state.change_cause.value != "unresolved"
                    or state.regime_decision.value != "unresolved"
                ):
                    raise ValueError(
                        "preserve_unresolved must preserve unresolved cause and regime"
                    )
            if operation == "rejuvenate":
                if not target.replay_required or not target.replaced_revision_ids:
                    raise ValueError("rejuvenation must name a suffix and require replay")
                suffix = target.replaced_revision_ids
                if len(set(suffix)) != len(suffix) or suffix[-1] != old.revision_id:
                    raise ValueError("suffix must be unique and end at selected parent")
                for index, revision_id in enumerate(suffix):
                    suffix_revision = revisions.get(revision_id)
                    if suffix_revision is None or suffix_revision.status != "active":
                        raise ValueError("suffix contains missing or retracted revisions")
                    if index and suffix_revision.parent_revision_id != suffix[index - 1]:
                        raise ValueError("replacement is not a contiguous revision suffix")
                if not any(arrivals[x] > self._evidence_time(x) for x in target.evidence_ids):
                    raise ValueError(
                        "suffix rejuvenation target requires actually delayed evidence"
                    )
            elif target.replaced_revision_ids or target.replay_required:
                raise ValueError("suffix replay fields belong to rejuvenation only")
        # This does not claim complete support enumeration or teacher correctness.
        if not any(
            target.operation.value == "preserve_unresolved"
            and target.candidate.state.instance_association_key == "unknown_instance"
            and any(event.actor_key == "unknown_actor" for event in target.candidate.events)
            for target in targets
        ):
            raise ValueError(
                "candidate targets must retain an open actor/instance unresolved fallback"
            )

    def _evidence_time(self, record_id: UUID) -> datetime:
        records: tuple[
            ObservationOpportunityRecord | ObservationDetectionResult | ActorResponsibilityEvidence,
            ...,
        ] = (
            *self.visible.opportunities,
            *self.visible.detections,
            *self.visible.actor_evidence,
        )
        for record in records:
            if record.metadata.record_id == record_id:
                if isinstance(record, ObservationOpportunityRecord):
                    return record.opportunity_time
                if isinstance(record, ActorResponsibilityEvidence):
                    return record.evidence_time
                if record.detection_time is not None:
                    return record.detection_time
                return next(
                    op.opportunity_time
                    for op in self.visible.opportunities
                    if op.metadata.record_id == record.observation_opportunity_id
                )
        raise ValueError("missing evidence")

    def _check_hypothesis(self, hypothesis: FullHypothesis) -> None:
        state = hypothesis.state
        if state.source_snapshot_id != self.source_snapshot_id:
            raise ValueError("cross-snapshot hypothesis")
        if state.instance_association_key not in self.instance_support:
            raise ValueError("instance outside declared support")
        for event in hypothesis.events:
            if event.location_key not in {x.location_key for x in self.location_support}:
                raise ValueError("event location outside declared sourced support")
            if event.time > self.visible.cutoff:
                raise ValueError("future event in an online hypothesis")
            if event.actor_key not in self.actor_support or (
                event.receiver_key is not None and event.receiver_key not in self.actor_support
            ):
                raise ValueError("actor outside declared support")


class ProposalSample(ProposalContext):
    schema_version: Literal["full-proposal-sample@2"] = "full-proposal-sample@2"
    sample_id: UUID
    partition: Literal["train", "development"]
    house_id: str = Field(min_length=1)
    house_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    schedule_block_id: str = Field(min_length=1)
    annotation_kind: Literal["component_fixture", "reviewed_offline", "native_trace"]
    annotation_ref: str = Field(min_length=1)
    compatible_targets: tuple[ProposalTarget, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_sample(self) -> Self:
        self.validate_candidates(self.compatible_targets)
        return self

    def runtime_context(self) -> ProposalContext:
        return ProposalContext.model_validate(
            self.model_dump(include=set(ProposalContext.model_fields))
        )


def export_context(context: ProposalContext) -> dict[str, Any]:
    context = ProposalContext.model_validate(context.model_dump())
    return {
        "visible_prefix": context.visible.prefix().model_input(),
        "source_snapshot_id": str(context.source_snapshot_id),
        "parent_hypotheses": [x.model_dump(mode="json") for x in context.parents],
        "revision_context": [x.model_dump(mode="json") for x in context.revisions],
        "instance_support": context.instance_support,
        "actor_support": context.actor_support,
        "location_support": [x.location_key for x in context.location_support],
        "location_entities": {
            x.location_key: str(x.location_entity_id) if x.location_entity_id else None
            for x in context.location_support
        },
    }


def semantic_state(hypothesis: FullHypothesis) -> dict[str, Any]:
    payload = hypothesis.model_dump(mode="json")
    for key in (
        "particle_id",
        "parent_particle_id",
        "revision_id",
        "parent_revision_id",
    ):
        payload["state"].pop(key)
    return payload


def export_sample(sample: ProposalSample) -> dict[str, Any]:
    """Revalidate mutable nested typed inputs before projecting the training envelope."""
    sample = ProposalSample.model_validate(sample.model_dump(mode="json"))
    return {
        "model_input": export_context(sample.runtime_context()),
        "training_targets": [x.model_dump(mode="json") for x in sample.compatible_targets],
        "audit_only": {
            "sample_id": str(sample.sample_id),
            "partition": sample.partition,
            "house_id": sample.house_id,
            "house_sha256": sample.house_sha256,
            "schedule_block_id": sample.schedule_block_id,
            "annotation_kind": sample.annotation_kind,
            "annotation_ref": sample.annotation_ref,
            "location_provenance": [x.model_dump(mode="json") for x in sample.location_support],
            "snapshot_location_catalog": [
                x.model_dump(mode="json") for x in sample.snapshot_location_catalog
            ],
            "source_authentication_verified": False,
            "ledger_write_authority": False,
        },
    }


def audit_samples(samples: tuple[ProposalSample, ...]) -> dict[str, Any]:
    """Structural training-readiness, never an unconditional permission to train."""
    samples = tuple(ProposalSample.model_validate(x.model_dump(mode="json")) for x in samples)
    ids: set[UUID] = set()
    house_partitions: dict[str, str] = {}
    block_partitions: dict[str, str] = {}
    counts: Counter[str] = Counter()
    chains: set[tuple[str, ...]] = set()
    for sample in samples:
        if sample.sample_id in ids:
            raise ValueError("duplicate sample ID")
        ids.add(sample.sample_id)
        # Also bind content hashes: renaming a house cannot bypass split checks.
        for key in (sample.house_id, sample.house_sha256):
            previous = house_partitions.setdefault(key, sample.partition)
            if previous != sample.partition:
                raise ValueError("house crosses data partitions")
        previous = block_partitions.setdefault(sample.schedule_block_id, sample.partition)
        if previous != sample.partition:
            raise ValueError("schedule block crosses data partitions")
        counts[f"annotation:{sample.annotation_kind}"] += 1
        for target in sample.compatible_targets:
            counts[f"operation:{target.operation.value}"] += 1
            counts[f"cause:{target.candidate.state.change_cause.value}"] += 1
            counts[f"regime:{target.candidate.state.regime_decision.value}"] += 1
            chains.add(tuple(x.kind for x in target.candidate.events))
    missing = [x.value for x in ParticleProposalOperation if not counts[f"operation:{x.value}"]]
    return {
        "samples": len(samples),
        "counts": dict(sorted(counts.items())),
        "chain_patterns": sorted(chains),
        "missing_operations": missing,
        "schema_coverage_only": True,
        "training_ready": False,
        "remaining_gates": [
            "independent label and visible-input provenance review",
            "native trace coverage and full operation reachability",
            "model parameters, continuous semantics and compute approval",
        ],
    }


class ConditionalFactor(ContractModel):
    axis: Literal["operation", "parent", "H", "R", "I", "C", "Z", "r", "V"]
    context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    choices: tuple[str, ...] = Field(min_length=1)
    probabilities: tuple[float, ...]
    selected: str

    @model_validator(mode="after")
    def validate_factor(self) -> Self:
        if len(self.choices) != len(self.probabilities) or len(set(self.choices)) != len(
            self.choices
        ):
            raise ValueError("categorical support mismatch")
        if any(not math.isfinite(p) or p < 0 or p > 1 for p in self.probabilities):
            raise ValueError("invalid categorical probability")
        if not math.isclose(math.fsum(self.probabilities), 1, abs_tol=1e-10, rel_tol=0):
            raise ValueError("categorical distribution not normalized")
        if (
            self.selected not in self.choices
            or self.probabilities[self.choices.index(self.selected)] <= 0
        ):
            raise ValueError("selected choice has zero/missing support")
        return self


class JointProposalProbability(ContractModel):
    """Complete finite categorical chain rule; sequence policies need a versioned trace.

    This is an audit interface for a future producer, not a uniform substitute.
    Authentic model/context binding remains a separate producer verification gate.
    """

    root_context_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    # Legacy unbound math traces remain inspectable, but cannot bind a proposal.
    proposal_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    factors: tuple[ConditionalFactor, ...]
    joint_log_probability: float

    @model_validator(mode="after")
    def validate_probability(self) -> Self:
        if tuple(x.axis for x in self.factors) != (
            "operation",
            "parent",
            "H",
            "R",
            "I",
            "C",
            "Z",
            "r",
            "V",
        ):
            raise ValueError("full ordered proposal factorization required")
        prefix: list[tuple[str, str]] = []
        for factor in self.factors:
            expected_context = content_sha256({"root": self.root_context_sha256, "prefix": prefix})
            if factor.context_sha256 != expected_context:
                raise ValueError("conditional factor is not bound to the actual preceding choices")
            prefix.append((factor.axis, factor.selected))
        expected = math.fsum(
            math.log(x.probabilities[x.choices.index(x.selected)]) for x in self.factors
        )
        if not math.isfinite(self.joint_log_probability) or not math.isclose(
            expected, self.joint_log_probability, rel_tol=0, abs_tol=1e-10
        ):
            raise ValueError("joint log probability omits or mismatches conditional factors")
        return self


def proposal_factor_values(target: ProposalTarget) -> tuple[str, ...]:
    """The shared nine-factor target order for model loss and probability receipts."""
    target = ProposalTarget.model_validate(target.model_dump(mode="json"))
    state = target.candidate.state
    return (
        target.operation.value,
        str(state.parent_particle_id),
        content_sha256([e.model_dump(mode="json") for e in target.candidate.events]),
        content_sha256([r.model_dump(mode="json") for r in state.ordered_actor_roles]),
        state.instance_association_key,
        state.change_cause.value,
        content_sha256({"decision": state.regime_decision.value, "regime_id": state.regime_id}),
        str(state.run_length),
        content_sha256(
            {
                key: state.model_dump(mode="json")[key]
                for key in (
                    "particle_id",
                    "revision_id",
                    "parent_revision_id",
                    "event_hypothesis_id",
                    "statistic_state_ref",
                    "ledger_lineage_ref",
                )
            }
        ),
    )


def bind_probability(
    sample: ProposalSample, target: ProposalTarget, trace: JointProposalProbability
) -> None:
    """Check full chain-rule terms bind this input and this actual proposed state.

    Does not authenticate a model file or prove support was enumerated completely.
    """
    sample = ProposalSample.model_validate(sample.model_dump(mode="json"))
    projection = export_sample(sample)
    trace = JointProposalProbability.model_validate(trace.model_dump(mode="json"))
    target = ProposalTarget.model_validate(target.model_dump(mode="json"))
    if trace.proposal_sha256 != content_sha256(target.model_dump(mode="json")):
        raise ValueError("probability trace does not bind the full proposal and replay effects")
    if target not in sample.compatible_targets:
        raise ValueError("target does not belong to the sample")
    if trace.root_context_sha256 != content_sha256(projection["model_input"]):
        raise ValueError("probability trace belongs to a different model input")
    expected = proposal_factor_values(target)
    if tuple(f.selected for f in trace.factors) != expected:
        raise ValueError(
            "probability trace selected values do not describe this complete candidate"
        )
