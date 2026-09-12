"""Native prepared-particle engineering; no proposer, calibration or commit authority.

The explicit proposal entry can normalize, retain ancestry and expose marginals.
Ordinary observations do not fabricate a selected neural/joint kernel. Conditional
statistics are supplied through a typed boundary, not inferred from marginal causes.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass, fields, is_dataclass
from math import fsum, isclose, isfinite, log
from typing import Any, cast
from uuid import UUID, uuid4

import numpy as np

from cpswm.system.counterfactual_event_hypergraph.contracts import (
    EventChainHypothesis,
    EventHypothesisHistory,
)
from cpswm.system.counterfactual_event_hypergraph.hypothesis_message_passing import (
    MessagePassingResult,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleProposalOperation,
    ParticleRevisionBatch,
    ParticleRevisionReceipt,
    TypedParticleState,
    normalize_particle_revisions,
)
from cpswm.system.reproducibility import content_sha256, content_uuid


def native_content_payload(value: Any) -> Any:
    """Canonicalize full typed cause-set keys without discarding any source field.

    The shared legacy hash encodes frozenset mapping keys with repr; deepcopy
    can reorder them even within one process. Keep this correction local to the
    new native workspace format so old W1/W2 artifacts retain their bindings.
    """

    def key(item: Any) -> Any:
        if isinstance(item, frozenset):
            return ("native:frozenset", tuple(sorted((key(x) for x in item), key=str)))
        if isinstance(item, tuple):
            return tuple(key(x) for x in item)
        return item

    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: native_content_payload(getattr(value, f.name)) for f in fields(value)}
    if hasattr(value, "model_dump"):
        return native_content_payload(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        return {key(k): native_content_payload(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return {
            "native:unordered_members": sorted((native_content_payload(x) for x in value), key=str)
        }
    if isinstance(value, (tuple, list)):
        return tuple(native_content_payload(x) for x in value)
    return value


def native_content_sha256(value: Any) -> str:
    return content_sha256(native_content_payload(value))


@dataclass(frozen=True)
class ConditionalAnalyticState:
    """Full natural parameters, with explicit caller-provided priors/conditioning."""

    locations: tuple[UUID, ...]
    alpha: tuple[float, ...]
    a: tuple[tuple[float, ...], ...]
    b: tuple[float, ...]
    information: tuple[tuple[float, ...], ...]
    information_vector: tuple[float, ...]
    evidence_cluster_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.locations
            or len(set(self.locations)) != len(self.locations)
            or len(self.alpha) != len(self.locations)
        ):
            raise ValueError("conditional location support mismatch")
        if len(set(self.evidence_cluster_ids)) != len(self.evidence_cluster_ids):
            raise ValueError("duplicate conditional evidence cluster")
        if any(not np.isfinite(x) or x < 0 for x in self.alpha):
            raise ValueError("invalid conditional alpha")
        dim = len(self.b)
        for matrix in (self.a, self.information):
            array = np.asarray(matrix)
            if (
                not dim
                or array.shape != (dim, dim)
                or not np.isfinite(array).all()
                or not np.array_equal(array, array.T)
            ):
                raise ValueError("invalid conditional precision")
            try:
                np.linalg.cholesky(array)
            except np.linalg.LinAlgError as error:
                raise ValueError("conditional precision must be positive definite") from error
        if (
            len(self.information_vector) != dim
            or not np.isfinite((*self.b, *self.information_vector)).all()
        ):
            raise ValueError("invalid conditional natural vector")

    @property
    def reference(self) -> str:
        return "conditional-statistics:" + content_sha256(self)


@dataclass(frozen=True)
class NativeParticleRecord:
    state: TypedParticleState
    event_chain_history: tuple[EventChainHypothesis, ...]
    statistics: ConditionalAnalyticState
    source_frame_sha256: str
    source_frame: Any
    ledger_head_sha256: str


@dataclass(frozen=True)
class NativePosteriorSource:
    """Actual PCHMP output and its complete producer inputs, not a write grant."""

    source_id: UUID
    runtime_id: UUID
    object_instance_id: UUID
    snapshot_id: UUID
    locations: tuple[UUID, ...]
    history_before: EventHypothesisHistory
    history_after: EventHypothesisHistory
    posterior: MessagePassingResult
    transition: Any
    producer_context: Any
    body_sha256: str

    def body(self) -> tuple[Any, ...]:
        return (
            self.runtime_id,
            self.object_instance_id,
            self.snapshot_id,
            self.locations,
            self.history_before,
            self.history_after,
            self.posterior,
            self.transition,
            self.producer_context,
        )

    def validate_content(self) -> None:
        if self.source_id != content_uuid(
            "native-pchmp-source", (self.runtime_id, self.history_after.latest.revision_id)
        ):
            raise ValueError("posterior source identity does not bind its producer revision")
        if native_content_sha256(self.body()) != self.body_sha256:
            raise ValueError("native posterior source content changed")
        EventHypothesisHistory.model_validate(self.history_before.model_dump())
        EventHypothesisHistory.model_validate(self.history_after.model_dump())
        MessagePassingResult.model_validate(self.posterior.model_dump())

    def log_factor(self, receipt: ParticleRevisionReceipt) -> float:
        state = receipt.proposal.proposed_state
        if state.instance_association_key != str(self.object_instance_id):
            raise ValueError("PCHMP projection cannot invent instance-association evidence")
        probability = self.posterior.posterior_by_hypothesis_id.get(state.event_hypothesis_id, 0.0)
        if probability <= 0.0:
            raise ValueError("posterior source has no positive support for this candidate")
        return log(probability)


class NativeParticleWorkspace:
    """Persistent native candidate state with explicit, noncommitting entry semantics."""

    def __init__(self) -> None:
        self.runtime_id = uuid4()
        self.posterior_sources: dict[UUID, NativePosteriorSource] = {}
        self.consumed_posterior_sources: dict[UUID, UUID] = {}
        self.records: dict[UUID, NativeParticleRecord] = {}
        self.batch: ParticleRevisionBatch | None = None
        self.receipts: tuple[ParticleRevisionReceipt, ...] = ()
        self.input_journal: dict[UUID, str] = {}
        self.input_bodies: dict[UUID, Any] = {}
        self.invalidated_revisions: set[UUID] = set()

    def state_payload(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            native_content_payload(
                {
                    "runtime_id": self.runtime_id,
                    "posterior_sources": self.posterior_sources,
                    "consumed_posterior_sources": self.consumed_posterior_sources,
                    "records": self.records,
                    "batch": self.batch,
                    "receipts": self.receipts,
                    "input_journal": self.input_journal,
                    "input_bodies": self.input_bodies,
                    "invalidated_revisions": tuple(sorted(self.invalidated_revisions, key=str)),
                    "input_status": "explicit_prepared_inputs_not_calibrated",
                }
            ),
        )

    def publish_posterior(
        self,
        *,
        object_instance_id: UUID,
        snapshot_id: UUID,
        locations: tuple[UUID, ...],
        history_before: EventHypothesisHistory,
        history_after: EventHypothesisHistory,
        posterior: MessagePassingResult,
        transition: Any,
        producer_context: Any,
    ) -> NativePosteriorSource:
        body = deepcopy(
            (
                self.runtime_id,
                object_instance_id,
                snapshot_id,
                locations,
                history_before,
                history_after,
                posterior,
                transition,
                producer_context,
            )
        )
        source = NativePosteriorSource(
            content_uuid(
                "native-pchmp-source", (self.runtime_id, history_after.latest.revision_id)
            ),
            *body,
            native_content_sha256(body),
        )
        source.validate_content()
        previous = self.posterior_sources.get(source.source_id)
        if previous is not None and previous != source:
            raise ValueError("conflicting posterior publication for one producer revision")
        self.posterior_sources[source.source_id] = source
        return source

    def invalidate_revisions(self, revision_ids: set[UUID]) -> None:
        self.invalidated_revisions.update(
            revision_ids.intersection(r.state.revision_id for r in self.records.values())
        )

    def advance(
        self,
        *,
        receipts: tuple[ParticleRevisionReceipt, ...],
        statistics: dict[UUID, ConditionalAnalyticState],
        chains: dict[UUID, EventChainHypothesis],
        snapshot_id: UUID,
        allowed_locations: tuple[UUID, ...],
        source_frame: Any,
        ledger_head_sha256: str,
        unresolved_log_weight: float,
        validated_projections: dict[UUID, NativePosteriorSource] | None = None,
    ) -> ParticleRevisionBatch:
        if not receipts:
            raise ValueError("prepared candidate batch must be nonempty")
        if self.invalidated_revisions:
            raise ValueError("full particle replay required; selected replay kernel is not bound")
        # Revalidate even model_copy/model_construct inputs, and detach caller
        # containers so they cannot mutate accepted state after this transaction.
        receipts = tuple(ParticleRevisionReceipt.model_validate(r.model_dump()) for r in receipts)
        statistics = {pid: ConditionalAnalyticState(**asdict(s)) for pid, s in statistics.items()}
        source_frame = deepcopy(source_frame)
        allowed_locations = tuple(allowed_locations)
        if not allowed_locations or len(set(allowed_locations)) != len(allowed_locations):
            raise ValueError("invalid runtime world location support")
        source_frame_sha256 = native_content_sha256(source_frame)
        validated_projections = validated_projections or {}
        body = (
            receipts,
            statistics,
            snapshot_id,
            source_frame,
            ledger_head_sha256,
            unresolved_log_weight,
            allowed_locations,
            validated_projections,
        )
        fingerprint = native_content_sha256(body)
        cluster = receipts[0].proposal.evidence_cluster_id
        if cluster in self.input_journal:
            if self.input_journal[cluster] != fingerprint:
                raise ValueError("conflicting prepared candidate replay")
            if self.batch is None or self.batch.evidence_cluster_id != cluster:
                raise ValueError("stale prepared candidate replay")
            return self.batch
        weights = (
            {}
            if self.batch is None
            else {p.particle_id: p.posterior_probability for p in self.batch.particle_weights}
        )
        records = dict(self.records)
        for receipt in receipts:
            proposal, state = receipt.proposal, receipt.proposal.proposed_state
            if receipt.evidence_semantics != "raw_observation_likelihood":
                source = validated_projections.get(state.particle_id)
                if source is None or self.posterior_sources.get(source.source_id) is not source:
                    raise ValueError(
                        "posterior projection consumption is not bound in native runtime"
                    )
                source.validate_content()
                if source.source_id in self.consumed_posterior_sources:
                    raise ValueError("posterior evidence was already consumed by a previous batch")
                if (
                    source.runtime_id != self.runtime_id
                    or receipt.source_posterior_snapshot_id != source.source_id
                    or receipt.posterior_projection_log_factor != source.log_factor(receipt)
                ):
                    raise ValueError("posterior factor or runtime source mismatch")
            elif receipt.source_posterior_snapshot_id is not None:
                raise ValueError("raw likelihood cannot claim a posterior source")
            if proposal.proposer_model_version != "explicit-prepared-candidates@1":
                raise ValueError("neural/model proposal requires a valid selected artifact binding")
            if proposal.source_snapshot_id != snapshot_id:
                raise ValueError("candidate source snapshot is not current")
            if proposal.operation in {
                ParticleProposalOperation.REJUVENATE,
                ParticleProposalOperation.REACTIVATE,
            }:
                raise ValueError("operation requires an unresolved selected kernel binding")
            if state.particle_id in records:
                raise ValueError("particle identity already used")
            chain = chains.get(state.event_hypothesis_id)
            if chain is None:
                raise ValueError("candidate event chain was not produced by this runtime")
            roles = {
                "pickup_actor": chain.steps[0].actor_key,
                "carrier": chain.steps[1].actor_key,
                "placer": chain.steps[-1].actor_key,
            }
            if len(chain.steps) == 4:
                assert chain.steps[2].recipient_actor_key is not None
                roles.update(
                    handoff_giver=chain.steps[2].actor_key,
                    handoff_receiver=chain.steps[2].recipient_actor_key,
                )
            if {r.role: r.actor_key for r in state.ordered_actor_roles} != roles:
                raise ValueError("candidate ordered roles contradict its full chain")
            if state.instance_association_key not in {
                str(chain.steps[0].object_instance_id),
                "unknown_instance",
            }:
                raise ValueError("candidate instance is outside the source support")
            parent = (
                self.records.get(state.parent_particle_id)
                if state.parent_particle_id is not None
                else None
            )
            if state.parent_particle_id is not None:
                if parent is None or weights.get(state.parent_particle_id, 0.0) <= 0.0:
                    raise ValueError("missing or inactive particle parent")
                if state.parent_revision_id != parent.state.revision_id or not isclose(
                    receipt.prior_log_weight,
                    log(weights[state.parent_particle_id]),
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ):
                    raise ValueError("particle parent revision or weight mismatch")
            elif (
                self.records
                or receipt.prior_log_weight != 0.0
                or state.parent_revision_id is not None
            ):
                raise ValueError("noninitial particle requires a real parent")
            analytic = statistics.get(state.particle_id)
            if analytic is None or state.statistic_state_ref != analytic.reference:
                raise ValueError("missing or mismatched conditional statistic reference")
            # Reordering is allowed with paired alpha entries. Subsets must be
            # represented by zero alpha on the full registered world support.
            if set(analytic.locations) != set(allowed_locations):
                raise ValueError("conditional locations differ from registered world support")
            if state.ledger_lineage_ref != "hybrid-ledger:" + ledger_head_sha256:
                raise ValueError("particle cannot name a foreign ledger lineage")
            records[state.particle_id] = NativeParticleRecord(
                state,
                (() if parent is None else parent.event_chain_history) + (chain,),
                analytic,
                source_frame_sha256,
                source_frame,
                ledger_head_sha256,
            )
        if not any(
            r.proposal.proposed_state.instance_association_key == "unknown_instance"
            for r in receipts
        ):
            raise ValueError("prepared candidates must preserve unknown instance support")
        if not any(
            role.actor_key == "unknown_actor"
            for r in receipts
            for role in r.proposal.proposed_state.ordered_actor_roles
        ):
            raise ValueError("prepared candidates must preserve source unknown actor support")
        batch = normalize_particle_revisions(receipts, unresolved_log_weight=unresolved_log_weight)
        if batch.unresolved_probability <= 0.0:
            raise ValueError("prepared candidate normalization lost unresolved mass")
        _location_marginal(batch, records)
        # No mutation precedes validation and actual importance weighting.
        self.records, self.batch, self.receipts, self.input_journal, self.input_bodies = (
            records,
            batch,
            receipts,
            {**self.input_journal, cluster: fingerprint},
            {**self.input_bodies, cluster: body},
        )
        self.consumed_posterior_sources.update(
            {source.source_id: cluster for source in validated_projections.values()}
        )
        return batch

    def location_marginal(self) -> tuple[dict[UUID, float], float]:
        """Consume prepared full candidates; unresolved is not silently renormalized."""
        if self.batch is None:
            raise ValueError("no prepared particle posterior")
        if self.invalidated_revisions:
            raise ValueError("particle ancestry was invalidated; full replay required")
        return _location_marginal(self.batch, self.records)


def _location_marginal(
    batch: ParticleRevisionBatch, records: dict[UUID, NativeParticleRecord]
) -> tuple[dict[UUID, float], float]:
    contributions: dict[UUID, list[float]] = {}
    unknown = [batch.unresolved_probability]
    for particle in batch.particle_weights:
        record = records[particle.particle_id]
        scale = max(record.statistics.alpha)
        if scale == 0.0 or record.state.instance_association_key == "unknown_instance":
            unknown.append(particle.posterior_probability)
            continue
        scaled = tuple(alpha / scale for alpha in record.statistics.alpha)
        total = fsum(scaled)
        for location, alpha in zip(record.statistics.locations, scaled, strict=True):
            contributions.setdefault(location, []).append(
                particle.posterior_probability * (alpha / total)
            )
    probabilities = {location: fsum(values) for location, values in contributions.items()}
    unresolved = fsum(unknown)
    mass = fsum((*probabilities.values(), unresolved))
    if not isfinite(mass) or abs(mass - 1.0) > 1e-9:
        raise ValueError("conditional marginal does not conserve probability mass")
    return probabilities, unresolved
