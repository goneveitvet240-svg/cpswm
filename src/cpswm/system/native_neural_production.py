"""Checkpoint-backed native proposal scoring with an explicit integration measure.

This first bridge exhaustively integrates the *configured* finite candidate model.
It does not certify that model's support, likelihoods, supervision or calibration.
For enumeration each leaf occurs once: the quadrature coefficient is q, cancelling
the importance denominator q. Treating enumerated leaves as random draws would
incorrectly favour low-q candidates. Sampling/rejuvenation are separate kernels.

The neural checkpoint remains a development artifact. Execution in this explicit
development bridge grants neither RGRC writes nor natural deployment authority.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import UUID

from cpswm.data_preflight.proposal_decoder import DecodedProposal
from cpswm.data_preflight.proposal_inference_session import ProposalInferenceSession, source_digest
from cpswm.data_preflight.proposal_perception import pixel_hypothesis_bindings
from cpswm.data_preflight.proposal_samples import (
    Arrival,
    EventNode,
    FullHypothesis,
    LocationBinding,
    ProposalContext,
    ProposalTarget,
    RevisionRecord,
    SnapshotLocation,
    VisibleRecords,
)
from cpswm.system.checkpoint_artifacts import (
    register_checkpoint_artifact,
    resolve_checkpoint_artifact,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleRevisionReceipt,
    TypedParticleState,
)
from cpswm.system.native_joint_production import (
    NativeJointContext,
    NativeJointProducer,
    ProducedJointCandidates,
    producer_binding,
    producer_implementation_binding,
)
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_particle_workspace import (
    NativeParticleRecord,
    native_content_sha256,
)

FORMAT = "native-neural-enumeration-development@2"
SUPPORTED_OPERATIONS = frozenset({"branch", "preserve_unresolved"})


def canonical_records(
    records: tuple[NativeParticleRecord, ...],
) -> tuple[NativeParticleRecord, ...]:
    pending = {r.state.particle_id: r for r in records}
    if len(pending) != len(records):
        raise ValueError("duplicate native model ancestry")
    seen: set[UUID] = set()
    ordered = []
    while pending:
        ready = sorted(
            (
                k
                for k, r in pending.items()
                if r.state.parent_particle_id is None or r.state.parent_particle_id in seen
            ),
            key=str,
        )
        if not ready:
            raise ValueError("orphan or cyclic native model ancestry")
        for key in ready:
            ordered.append(pending.pop(key))
            seen.add(key)
    return tuple(ordered)


def _revision(particle_id: UUID | None) -> UUID | None:
    return None if particle_id is None else content_uuid("native-neural-revision-view", particle_id)


def _hypothesis(
    state: TypedParticleState, chain: Any, context: NativeJointContext
) -> FullHypothesis:
    """Project shared evidence revisions to per-world-line graph revision names.

    Names are a deterministic view, never new evidence or mutations to the core.
    Current snapshot/ledger names identify the view; original ancestry and bytes
    remain in the native context and are checked by the publication consumer.
    """
    projected = state.model_copy(
        update={
            "revision_id": _revision(state.particle_id),
            "parent_revision_id": _revision(state.parent_particle_id),
            "source_snapshot_id": context.source.snapshot_id,
            "ledger_lineage_ref": "hybrid-ledger:" + context.ledger_head_sha256,
        }
    )
    events = tuple(
        EventNode(
            event_id=step.step_id,
            time=step.event_time,
            kind="handoff" if step.event_type.value == "transfer" else step.event_type.value,
            instance_key=state.instance_association_key,
            actor_key=step.actor_key,
            receiver_key=step.recipient_actor_key,
            location_key=str(step.destination_location_id or step.source_location_id)
            if step.destination_location_id or step.source_location_id
            else "unknown_location",
        )
        for step in chain.steps
    )
    return FullHypothesis(state=projected, events=events)


def proposal_view(
    context: NativeJointContext, base: ProducedJointCandidates
) -> tuple[ProposalContext, tuple[ProposalTarget, ...]]:
    """Build the label-free semantic and optional owned-visual input view."""
    source = context.source
    source.validate_content()
    if (
        base.neural_evidence is not None
        or base.context_sha256 != context.content_sha256
        or base.source_posterior_id != source.source_id
        or base.source_body_sha256 != source.body_sha256
        or not base.receipts
    ):
        raise ValueError("native neural input is not bound to its actual source context")
    transition = source.transition
    op, detection = transition.opportunity, transition.after
    # Publication only consumes semantic records already accepted by the core.
    # Semantic availability is conservative. Optional visual records retain
    # their actual capture/arrival times and their owner-issued source proof.
    if any(t > context.cutoff for t in (op.opportunity_time, detection.detection_time)):
        raise ValueError("native neural source exceeds current cutoff")
    visible = VisibleRecords(
        opportunities=(op,),
        detections=(detection,),
        arrivals=(
            Arrival(record_id=op.metadata.record_id, received_at=context.cutoff),
            Arrival(record_id=detection.metadata.record_id, received_at=context.cutoff),
        ),
        cutoff=context.cutoff,
        pixel_observations=() if context.visual_source is None else context.visual_source.pixels(),
    )
    weights = (
        {}
        if context.previous_batch is None
        else {
            w.particle_id: w.posterior_probability for w in context.previous_batch.particle_weights
        }
    )
    parents = tuple(
        _hypothesis(r.state, r.event_chain_history[-1], context) for r in context.records
    )
    revisions = tuple(
        RevisionRecord(
            revision_id=h.state.revision_id,
            parent_revision_id=h.state.parent_revision_id,
            particle_id=h.state.particle_id,
            event_hypothesis_id=h.state.event_hypothesis_id,
            ledger_lineage_ref=h.state.ledger_lineage_ref,
            statistic_state_ref=h.state.statistic_state_ref,
            status="active" if weights.get(h.state.particle_id, 0) > 0 else "retracted",
        )
        for h in parents
    )
    chains = {h.hypothesis_id: h for h in source.history_after.latest.hypotheses}
    targets = []
    for receipt in base.receipts:
        proposal = receipt.proposal
        if (
            proposal.proposer_model_version != "explicit-prepared-candidates@1"
            or proposal.operation.value not in SUPPORTED_OPERATIONS
            or receipt.integration_log_weight != 0.0
        ):
            raise ValueError("this explicit enumeration bridge does not implement revision kernels")
        state = proposal.proposed_state
        if state.revision_id != source.history_after.latest.revision_id:
            raise ValueError("neural candidate refers to another native source revision")
        if state.parent_particle_id is not None and weights.get(state.parent_particle_id, 0) <= 0:
            raise ValueError("neural enumeration requires a current active native parent")
        chain = chains.get(state.event_hypothesis_id)
        if chain is None:
            raise ValueError("neural candidate chain is outside the actual native source")
        targets.append(
            ProposalTarget(
                operation=proposal.operation,
                candidate=_hypothesis(state, chain, context),
                evidence_ids=(detection.metadata.record_id,),
                replaced_revision_ids=(),
                replay_required=False,
            )
        )
    instance_support = {"unknown_instance", str(source.object_instance_id)}
    actors = {"unknown_actor", *transition.actor_prior}
    for h in (*parents, *(t.candidate for t in targets)):
        instance_support.add(h.state.instance_association_key)
        actors.update(e.actor_key for e in h.events)
        actors.update(e.receiver_key for e in h.events if e.receiver_key is not None)
    locations = tuple(
        LocationBinding(
            location_key=str(loc),
            location_entity_id=loc,
            origin="snapshot",
            source_snapshot_id=source.snapshot_id,
        )
        for loc in source.locations
    )
    bindings = pixel_hypothesis_bindings(visible.pixel_observations, context.cutoff)
    instance_support.update(b.key for b in bindings if b.kind == "instance")
    actors.update(b.key for b in bindings if b.kind == "actor")
    view = ProposalContext(
        source_snapshot_id=source.snapshot_id,
        visible=visible,
        parents=parents,
        revisions=revisions,
        instance_support=tuple(sorted(instance_support)),
        actor_support=tuple(sorted(actors)),
        pixel_identity_bindings=bindings,
        location_support=(
            *locations,
            LocationBinding(location_key="unknown_location", origin="unknown"),
        ),
        snapshot_location_catalog=tuple(
            SnapshotLocation(location_key=str(loc), location_entity_id=loc)
            for loc in source.locations
        ),
    )
    support = tuple(sorted(targets, key=lambda t: content_sha256(t.model_dump(mode="json"))))
    view.validate_candidates(support)
    return view, support


@dataclass(frozen=True)
class NativeNeuralEvidence:
    format: str
    checkpoint_artifact_id: str
    manifest_sha256: str
    inference_binding_sha256: str
    producer_binding_sha256: str
    candidate_implementation_sha256: str
    input_context_sha256: str
    cutoff: datetime
    context: ProposalContext
    support: tuple[ProposalTarget, ...]
    base_candidates: ProducedJointCandidates
    scored: tuple[DecodedProposal, ...]
    visual_source_sha256: str | None = None

    @property
    def model_version(self) -> str:
        return "typed-development-checkpoint:" + self.manifest_sha256


def materialize(
    base: ProducedJointCandidates, evidence: NativeNeuralEvidence
) -> tuple[ParticleRevisionReceipt, ...]:
    by_particle = {d.target.candidate.state.particle_id: d for d in evidence.scored}
    if len(by_particle) != len(evidence.scored) or set(by_particle) != {
        r.proposal.proposed_state.particle_id for r in base.receipts
    }:
        raise ValueError("neural score support is not closed over native candidates")
    return tuple(
        ParticleRevisionReceipt.model_validate(
            receipt.model_copy(
                update={
                    "proposal": receipt.proposal.model_copy(
                        update={
                            "proposal_log_probability": by_particle[
                                receipt.proposal.proposed_state.particle_id
                            ].probability.joint_log_probability,
                            "proposer_model_version": evidence.model_version,
                            "proposer_code_version": FORMAT,
                        }
                    ),
                    "integration_log_weight": by_particle[
                        receipt.proposal.proposed_state.particle_id
                    ].probability.joint_log_probability,
                }
            ).model_dump()
        )
        for receipt in base.receipts
    )


_VERIFY_LOCK = RLock()
_VERIFIERS: dict[tuple[str, str, str, int], tuple[ProposalInferenceSession, set[str]]] = {}


def verify_neural_evidence(evidence: NativeNeuralEvidence) -> None:
    """Recompute q with the actual pinned checkpoint, including after restart.

    The cache is local verified content, never a caller supplied 'verified' bit.
    Both checkpoint files and loaded model execution identity are checked on hits.
    Runtime/context correspondence is additionally checked by the native owner.
    """
    import torch

    if type(evidence) is not NativeNeuralEvidence or evidence.format != FORMAT:
        raise ValueError("unknown native neural evidence")
    if evidence.producer_binding_sha256 != native_content_sha256(
        (
            FORMAT,
            evidence.base_candidates.dependency_sha256,
            evidence.candidate_implementation_sha256,
            evidence.manifest_sha256,
            evidence.inference_binding_sha256,
            *(("owned-visual-context@1",) if evidence.visual_source_sha256 is not None else ()),
        )
    ):
        raise ValueError("native neural artifact differs from its configured producer binding")
    directory = resolve_checkpoint_artifact(
        evidence.checkpoint_artifact_id, manifest_sha256=evidence.manifest_sha256
    )
    manifest = directory / "manifest.json"
    if sha256(manifest.read_bytes()).hexdigest() != evidence.manifest_sha256:
        raise ValueError("native neural checkpoint manifest changed")
    import json

    descriptor = json.loads(manifest.read_bytes())
    if sha256((directory / "weights.pt").read_bytes()).hexdigest() != descriptor["weights_sha256"]:
        raise ValueError("native neural checkpoint weights changed")
    key = (
        str(directory.resolve()),
        evidence.manifest_sha256,
        source_digest(),
        torch.get_num_threads(),
    )
    with _VERIFY_LOCK:
        if key not in _VERIFIERS:
            _VERIFIERS[key] = (
                ProposalInferenceSession(directory, manifest_sha256=key[1], seed=0),
                set(),
            )
        session, verified = _VERIFIERS[key]
        session._check_model()
        if session.binding_sha256 != evidence.inference_binding_sha256:
            raise ValueError("native neural execution dependencies changed")
        digest = native_content_sha256(evidence)
        if digest in verified:
            return
        scored = session.score_support(context=evidence.context, support=evidence.support)
        if scored != evidence.scored:
            raise ValueError("native neural probability differs from checkpoint recomputation")
        verified.add(digest)


def validate_neural_input_body(body: Any, workspace: Any, *, current: bool = False) -> None:
    """Check an executed proof against the runtime's real input and ancestor set."""
    evidence = body.neural_evidence
    if type(evidence) is not NativeNeuralEvidence:
        raise ValueError("native publication requires actual neural execution evidence")
    if evidence.producer_binding_sha256 != workspace.joint_dependency_binding:
        raise ValueError("neural evidence belongs to a different configured producer")
    base = evidence.base_candidates
    source = workspace.posterior_sources.get(base.source_posterior_id)
    if source is None or source.body_sha256 != base.source_body_sha256:
        raise ValueError("neural execution source is not owned by this runtime")
    if (
        source.runtime_id != workspace.runtime_id
        or source.snapshot_id != body.snapshot_id
        or source.locations != body.registered_locations
        or native_content_sha256(base.statistics) != native_content_sha256(body.statistics)
        or base.unresolved_log_weight != body.unresolved_log_weight
    ):
        raise ValueError("neural execution does not match native state/statistics/ledger")
    if current:
        expected_records = tuple(workspace.records.values())
        previous_batch = workspace.batch
    else:
        # Recover the actual dependency chain, not dictionary insertion order.
        earlier = []
        cursor = body
        while True:
            parent_clusters = {
                None
                if r.proposal.source_particle_id is None
                else workspace.records[r.proposal.source_particle_id].evidence_cluster_id
                for r in cursor.receipts
            }
            if len(parent_clusters) != 1:
                raise ValueError("ambiguous native neural predecessor batches")
            key = parent_clusters.pop()
            if key is None:
                break
            if key in earlier or key not in workspace.input_bodies:
                raise ValueError("cyclic or missing native neural predecessor batch")
            earlier.append(key)
            cursor = workspace.input_bodies[key]
        expected_records = tuple(
            r for r in workspace.records.values() if r.evidence_cluster_id in earlier
        )
        if earlier:
            from cpswm.system.evaluation_operations.structure_two_selected_method import (
                normalize_particle_revisions,
            )

            previous_body = workspace.input_bodies[earlier[0]]
            previous_batch = normalize_particle_revisions(
                previous_body.receipts, unresolved_log_weight=previous_body.unresolved_log_weight
            )
        else:
            previous_batch = None
    visual = None
    if evidence.visual_source_sha256 is not None:
        visual = workspace.visual_sources.get(evidence.visual_source_sha256)
        if (
            visual is None
            or visual.content_sha256 != evidence.visual_source_sha256
            or visual.runtime_id != workspace.runtime_id
            or visual.cutoff != evidence.cutoff
        ):
            raise ValueError("neural visual source is not owned by this runtime")
    native_context = NativeJointContext(
        source,
        previous_batch,
        canonical_records(expected_records),
        body.ledger_head_sha256,
        (),
        evidence.cutoff,
        visual,
    )
    context, support = proposal_view(native_context, base)
    if context != evidence.context or support != evidence.support:
        raise ValueError("neural execution inputs differ from actual native history")
    verify_neural_evidence(evidence)
    if materialize(base, evidence) != body.receipts:
        raise ValueError("native receipt differs from actual neural scores or integration measure")


class NeuralNativeProducer:
    """Explicit development execution of a checkpoint over a bound candidate model.

    The candidate/measurement model retains its original epistemic status. All
    supplied support is scored and integrated, with no stochastic resampling,
    inferred architecture selection, automatic commit or calibrated-value claim.
    """

    def __init__(
        self,
        candidate_model: NativeJointProducer,
        checkpoint: Path,
        *,
        manifest_sha256: str,
        use_owned_visual_context: bool = False,
    ) -> None:
        if type(use_owned_visual_context) is not bool:
            raise ValueError("visual conditioning must be an explicit boolean")
        self.use_owned_visual_context = use_owned_visual_context
        self._candidate_model = candidate_model
        binding = producer_binding(candidate_model)
        implementation = producer_implementation_binding(candidate_model)
        if binding is None or implementation is None:
            raise ValueError("a concrete bound native candidate model is required")
        self._candidate_binding = binding
        self._candidate_implementation = implementation
        self._manifest_sha256 = manifest_sha256
        self._session = ProposalInferenceSession(
            checkpoint, manifest_sha256=manifest_sha256, seed=0
        )
        self._checkpoint_artifact_id = register_checkpoint_artifact(
            checkpoint, manifest_sha256=manifest_sha256
        )
        self.calls = 0
        self._last_evidence: NativeNeuralEvidence | None = None

    @property
    def binding_sha256(self) -> str:
        self._session._check_model()
        if (
            producer_binding(self._candidate_model) != self._candidate_binding
            or producer_implementation_binding(self._candidate_model)
            != self._candidate_implementation
        ):
            raise ValueError("native candidate model dependency changed")
        return native_content_sha256(
            (
                FORMAT,
                self._candidate_binding,
                self._candidate_implementation,
                self._manifest_sha256,
                self._session.binding_sha256,
                *(("owned-visual-context@1",) if self.use_owned_visual_context else ()),
            )
        )

    def checkpoint_state(self) -> dict[str, Any]:
        return {
            "binding": self.binding_sha256,
            "candidate_state": deepcopy(self._candidate_model.checkpoint_state()),
            "calls": self.calls,
            "last_evidence": deepcopy(self._last_evidence),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        if (
            set(state) != {"binding", "candidate_state", "calls", "last_evidence"}
            or state["binding"] != self.binding_sha256
        ):
            raise ValueError("neural native producer state binding mismatch")
        if type(state["calls"]) is not int or state["calls"] < 0:
            raise ValueError("invalid neural native call count")
        if state["last_evidence"] is not None:
            verify_neural_evidence(state["last_evidence"])
            if state["last_evidence"].producer_binding_sha256 != self.binding_sha256:
                raise ValueError("neural producer history belongs to another configured model")
        previous = deepcopy(self._candidate_model.checkpoint_state())
        try:
            self._candidate_model.restore_state(deepcopy(state["candidate_state"]))
            if native_content_sha256(
                self._candidate_model.checkpoint_state()
            ) != native_content_sha256(state["candidate_state"]):
                raise ValueError("native candidate model did not restore exactly")
        except BaseException:
            self._candidate_model.restore_state(previous)
            raise
        self.calls, self._last_evidence = state["calls"], deepcopy(state["last_evidence"])

    def produce(self, context: NativeJointContext) -> ProducedJointCandidates:
        before = self.checkpoint_state()
        try:
            base = deepcopy(self._candidate_model.produce(deepcopy(context)))
            if base.dependency_sha256 != self._candidate_binding:
                raise ValueError("native candidate model returned a different binding")
            if (context.visual_source is not None) != self.use_owned_visual_context:
                raise ValueError("native neural visual source profile differs")
            # Owned candidates and geometry enter the model; raw pixel payloads
            # remain in the acquisition journal, avoiding recursive duplication.
            model_context = replace(
                context, visible_prefix=(), records=canonical_records(context.records)
            )
            model_base = replace(base, context_sha256=model_context.content_sha256)
            view, support = proposal_view(model_context, model_base)
            scored = self._session.score_support(context=view, support=support)
            evidence = NativeNeuralEvidence(
                FORMAT,
                self._checkpoint_artifact_id,
                self._manifest_sha256,
                self._session.binding_sha256,
                self.binding_sha256,
                self._candidate_implementation,
                context.content_sha256,
                context.cutoff,
                view,
                support,
                model_base,
                scored,
                None if context.visual_source is None else context.visual_source.content_sha256,
            )
            result = replace(
                base,
                dependency_sha256=self.binding_sha256,
                receipts=materialize(base, evidence),
                neural_evidence=evidence,
            )
            self.calls += 1
            self._last_evidence = evidence
            return result
        except BaseException:
            self.restore_state(before)
            raise
