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

    if isinstance(value, np.ndarray):
        return value.tolist()
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: native_content_payload(getattr(value, f.name)) for f in fields(value)}
    if hasattr(value, "model_dump"):
        return native_content_payload(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        normalized = {}
        for k, v in value.items():
            normalized_key = key(k)
            if normalized_key in normalized:
                raise ValueError("native content keys collide after typed normalization")
            normalized[normalized_key] = native_content_payload(v)
        return normalized
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
        for matrix, dim in (
            (self.a, len(self.b)),
            (self.information, len(self.information_vector)),
        ):
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
        if not np.isfinite((*self.b, *self.information_vector)).all():
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
    evidence_cluster_id: UUID
    workspace_runtime_id: UUID
    world_support_sha256: str
    input_fingerprint_sha256: str


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


@dataclass(frozen=True)
class NativePreparedInputBody:
    """Detached, journaled input whose fields can be revalidated at readout."""

    workspace_runtime_id: UUID
    receipts: tuple[ParticleRevisionReceipt, ...]
    statistics: dict[UUID, ConditionalAnalyticState]
    snapshot_id: UUID
    source_frame: Any
    ledger_head_sha256: str
    unresolved_log_weight: float
    registered_locations: tuple[UUID, ...]
    world_support_sha256: str
    validated_projections: dict[UUID, NativePosteriorSource]


class NativeParticleWorkspace:
    """Persistent native candidate state with explicit, noncommitting entry semantics."""

    def __init__(self, *, registered_locations: tuple[UUID, ...] | None = None) -> None:
        self.runtime_id = uuid4()
        self._registered_locations = (
            None if registered_locations is None else tuple(registered_locations)
        )
        self._world_support_sha256 = (
            None
            if self._registered_locations is None
            else native_content_sha256(("runtime-world-support@1", self._registered_locations))
        )
        if self._registered_locations is not None and (
            not self._registered_locations
            or len(set(self._registered_locations)) != len(self._registered_locations)
        ):
            raise ValueError("invalid registered runtime world location support")
        self.posterior_sources: dict[UUID, NativePosteriorSource] = {}
        self.consumed_posterior_sources: dict[UUID, UUID] = {}
        self.records: dict[UUID, NativeParticleRecord] = {}
        self.batch: ParticleRevisionBatch | None = None
        self.receipts: tuple[ParticleRevisionReceipt, ...] = ()
        self.input_journal: dict[UUID, str] = {}
        self.input_bodies: dict[UUID, NativePreparedInputBody] = {}
        self.invalidated_revisions: set[UUID] = set()

    def state_payload(self) -> dict[str, Any]:
        self._validate_persisted_state()
        return cast(
            dict[str, Any],
            native_content_payload(
                {
                    "runtime_id": self.runtime_id,
                    "registered_locations": self._registered_locations,
                    "world_support_sha256": self._world_support_sha256,
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

    def _validate_persisted_state(self) -> None:
        self.validate_world_support(self.registered_locations)
        if set(self.input_journal) != set(self.input_bodies):
            raise ValueError("prepared input journal and bodies do not have the same closure")
        bodies = {cluster: self._validated_input_body(cluster) for cluster in self.input_journal}
        journaled_particle_ids = tuple(
            receipt.proposal.proposed_state.particle_id
            for body in bodies.values()
            for receipt in body.receipts
        )
        if len(set(journaled_particle_ids)) != len(journaled_particle_ids) or set(
            journaled_particle_ids
        ) != set(self.records):
            raise ValueError("prepared particle records differ from journaled receipt closure")
        if self.batch is not None:
            self._validate_current_batch()
        elif self.receipts:
            raise ValueError("prepared receipts exist without a current batch")
        for particle_id, record in self.records.items():
            self._validate_record_binding(record, expected_particle_id=particle_id)
        expected_consumption: dict[UUID, UUID] = {}
        for cluster, body in bodies.items():
            for source in body.validated_projections.values():
                previous = expected_consumption.setdefault(source.source_id, cluster)
                if previous != cluster:
                    raise ValueError("posterior source appears in more than one prepared input")
        if self.consumed_posterior_sources != expected_consumption:
            raise ValueError("posterior source consumption differs from journaled inputs")

    @property
    def registered_locations(self) -> tuple[UUID, ...]:
        if self._registered_locations is None:
            raise ValueError("native particle workspace has no registered world support")
        return self._registered_locations

    @property
    def world_support_sha256(self) -> str:
        self.validate_world_support(self.registered_locations)
        assert self._world_support_sha256 is not None
        return self._world_support_sha256

    def validate_world_support(self, locations: tuple[UUID, ...]) -> None:
        """Verify a caller's support against the construction-time runtime authority."""

        registered = self.registered_locations
        locations = tuple(locations)
        if locations != registered:
            raise ValueError("runtime world support differs from its registered binding")
        expected = native_content_sha256(("runtime-world-support@1", registered))
        if self._world_support_sha256 != expected:
            raise ValueError("runtime world support binding changed")

    def _validate_record_binding(
        self,
        record: NativeParticleRecord,
        *,
        expected_particle_id: UUID | None = None,
        _visited: frozenset[UUID] = frozenset(),
    ) -> None:
        registered = self.registered_locations
        particle_id = record.state.particle_id
        if particle_id in _visited:
            raise ValueError("prepared particle record has cyclic ancestry")
        if (
            (expected_particle_id is not None and particle_id != expected_particle_id)
            or record.workspace_runtime_id != self.runtime_id
            or record.world_support_sha256 != self.world_support_sha256
            or set(record.statistics.locations) != set(registered)
            or record.state.statistic_state_ref != record.statistics.reference
            or record.source_frame_sha256 != native_content_sha256(record.source_frame)
            or record.state.ledger_lineage_ref != "hybrid-ledger:" + record.ledger_head_sha256
        ):
            raise ValueError("prepared particle record has an invalid runtime support binding")
        parent_id = record.state.parent_particle_id
        parent = None if parent_id is None else self.records.get(parent_id)
        if parent_id is not None and parent is None:
            raise ValueError("prepared particle record has no runtime parent")
        if parent is not None:
            if record.state.parent_revision_id != parent.state.revision_id:
                raise ValueError("prepared particle record has an invalid parent revision")
            self._validate_record_binding(
                parent,
                expected_particle_id=parent_id,
                _visited=_visited | {particle_id},
            )
        elif record.state.parent_revision_id is not None:
            raise ValueError("initial prepared particle record claims a parent revision")
        expected_clusters = (
            (record.evidence_cluster_id,)
            if parent is None
            else (*parent.statistics.evidence_cluster_ids, record.evidence_cluster_id)
        )
        if record.statistics.evidence_cluster_ids != expected_clusters:
            raise ValueError("prepared particle record has an invalid evidence cluster lineage")

        body = self._validated_input_body(record.evidence_cluster_id)
        if record.input_fingerprint_sha256 != self.input_journal[
            record.evidence_cluster_id
        ] or record.source_frame_sha256 != native_content_sha256(body.source_frame):
            raise ValueError("prepared particle record has an invalid input fingerprint")
        matching_receipts = tuple(
            receipt
            for receipt in body.receipts
            if receipt.proposal.proposed_state.particle_id == particle_id
        )
        if (
            len(matching_receipts) != 1
            or matching_receipts[0].proposal.proposed_state != record.state
            or body.statistics.get(particle_id) != record.statistics
            or matching_receipts[0].proposal.evidence_cluster_id != record.evidence_cluster_id
        ):
            raise ValueError("prepared particle record differs from its journaled input")
        try:
            frames, _cause_snapshot = body.source_frame
            raw_history = frames[record.state.revision_id][0]
            history = EventHypothesisHistory.model_validate(raw_history.model_dump())
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError("prepared particle record has an invalid source history") from error
        matching_chains = tuple(
            chain
            for chain in history.latest.hypotheses
            if chain.hypothesis_id == record.state.event_hypothesis_id
        )
        if len(matching_chains) != 1:
            raise ValueError("prepared particle record has no unique source event chain")
        expected_history = (() if parent is None else parent.event_chain_history) + (
            matching_chains[0],
        )
        if record.event_chain_history != expected_history:
            raise ValueError("prepared particle event-chain history differs from its source")

    def _validated_input_body(self, cluster: UUID) -> NativePreparedInputBody:
        body = self.input_bodies.get(cluster)
        digest = self.input_journal.get(cluster)
        if type(body) is not NativePreparedInputBody or digest is None:
            raise ValueError("prepared input journal body is missing or has the wrong type")
        if digest != native_content_sha256(body):
            raise ValueError("prepared input journal body changed")
        if (
            body.workspace_runtime_id != self.runtime_id
            or body.registered_locations != self.registered_locations
            or body.world_support_sha256 != self.world_support_sha256
        ):
            raise ValueError("prepared input journal body belongs to another runtime support")

        receipts = tuple(
            ParticleRevisionReceipt.model_validate(receipt.model_dump())
            for receipt in body.receipts
        )
        if receipts != body.receipts:
            raise ValueError("prepared input journal receipt changed during validation")
        particle_ids = tuple(receipt.proposal.proposed_state.particle_id for receipt in receipts)
        proposal_ids = tuple(receipt.proposal.proposal_id for receipt in receipts)
        if (
            not receipts
            or len(set(particle_ids)) != len(particle_ids)
            or len(set(proposal_ids)) != len(proposal_ids)
            or set(body.statistics) != set(particle_ids)
            or {receipt.proposal.evidence_cluster_id for receipt in receipts} != {cluster}
            or {receipt.proposal.source_snapshot_id for receipt in receipts} != {body.snapshot_id}
        ):
            raise ValueError("prepared input journal body has invalid receipt closure")
        for particle_id, statistic in body.statistics.items():
            if ConditionalAnalyticState(**asdict(statistic)) != statistic:
                raise ValueError("prepared input journal statistic changed during validation")
            receipt = next(
                row for row in receipts if row.proposal.proposed_state.particle_id == particle_id
            )
            if receipt.proposal.proposed_state.statistic_state_ref != statistic.reference:
                raise ValueError("prepared input statistic reference changed")

        projected_receipts = {
            receipt.proposal.proposed_state.particle_id: receipt
            for receipt in receipts
            if receipt.evidence_semantics == "posterior_projection_not_likelihood"
        }
        if set(body.validated_projections) != set(projected_receipts):
            raise ValueError("prepared posterior projection set is not closed over receipts")
        for particle_id, source in body.validated_projections.items():
            receipt = projected_receipts[particle_id]
            source.validate_content()
            if (
                source.runtime_id != self.runtime_id
                or self.posterior_sources.get(source.source_id) != source
                or receipt.source_posterior_snapshot_id != source.source_id
                or receipt.posterior_projection_log_factor != source.log_factor(receipt)
            ):
                raise ValueError("prepared posterior projection has an invalid runtime source")
        return body

    def _validate_current_batch(self) -> None:
        batch = self.batch
        if batch is None:
            raise ValueError("no prepared particle posterior")
        body = self._validated_input_body(batch.evidence_cluster_id)
        expected = normalize_particle_revisions(
            body.receipts, unresolved_log_weight=body.unresolved_log_weight
        )
        if batch != expected or self.receipts != body.receipts:
            raise ValueError("prepared particle batch differs from its journaled input")
        for weight in batch.particle_weights:
            record = self.records.get(weight.particle_id)
            if record is None:
                raise ValueError("prepared particle batch is missing a particle record")
            self._validate_record_binding(record, expected_particle_id=weight.particle_id)

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
        self.validate_world_support(locations)
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
        self._validate_persisted_state()
        if self.invalidated_revisions:
            raise ValueError("full particle replay required; selected replay kernel is not bound")
        # Revalidate even model_copy/model_construct inputs, and detach caller
        # containers so they cannot mutate accepted state after this transaction.
        receipts = tuple(ParticleRevisionReceipt.model_validate(r.model_dump()) for r in receipts)
        statistic_items = tuple(statistics.items())
        statistic_keys = tuple(particle_id for particle_id, _ in statistic_items)
        if any(not isinstance(particle_id, UUID) for particle_id in statistic_keys):
            raise ValueError("prepared statistic keys must be UUID particle references")
        if len(set(statistic_keys)) != len(statistic_keys):
            raise ValueError("prepared statistics contain a duplicate particle reference")
        raw_statistic_ids = set(statistic_keys)
        particle_ids = tuple(receipt.proposal.proposed_state.particle_id for receipt in receipts)
        proposal_ids = tuple(receipt.proposal.proposal_id for receipt in receipts)
        if len(set(particle_ids)) != len(particle_ids):
            raise ValueError("prepared receipts contain a duplicate particle reference")
        if len(set(proposal_ids)) != len(proposal_ids):
            raise ValueError("prepared receipts contain a duplicate proposal reference")
        referenced_ids = set(particle_ids)
        if raw_statistic_ids != referenced_ids:
            missing = referenced_ids - raw_statistic_ids
            extra = raw_statistic_ids - referenced_ids
            detail = "missing" if missing else "unreferenced"
            if missing and extra:
                detail = "missing and unreferenced"
            raise ValueError(f"prepared candidate statistic closure has {detail} entries")
        snapshots = tuple(receipt.proposal.source_snapshot_id for receipt in receipts)
        if len(set(snapshots)) != 1:
            raise ValueError("prepared candidate batch mixes source snapshots")
        if snapshots[0] != snapshot_id:
            raise ValueError("candidate source snapshot is not current")
        clusters = tuple(receipt.proposal.evidence_cluster_id for receipt in receipts)
        if len(set(clusters)) != 1:
            raise ValueError("prepared candidate batch mixes evidence clusters")

        statistics = {
            pid: ConditionalAnalyticState(**asdict(statistic)) for pid, statistic in statistic_items
        }
        source_frame = deepcopy(source_frame)
        allowed_locations = tuple(allowed_locations)
        self.validate_world_support(allowed_locations)
        world_support_sha256 = self.world_support_sha256
        source_frame_sha256 = native_content_sha256(source_frame)
        validated_projections = dict(validated_projections or {})
        projected_particle_ids = {
            receipt.proposal.proposed_state.particle_id
            for receipt in receipts
            if receipt.evidence_semantics == "posterior_projection_not_likelihood"
        }
        if set(validated_projections) != projected_particle_ids:
            raise ValueError("posterior projection set is not closed over prepared receipts")

        # Validate every statistic-to-receipt/parent lineage before computing an
        # idempotency fingerprint or consulting the replay journal. This keeps a
        # fully resealed false lineage from becoming a replay identity.
        for receipt in receipts:
            proposal, state = receipt.proposal, receipt.proposal.proposed_state
            analytic = statistics[state.particle_id]
            parent = (
                self.records.get(state.parent_particle_id)
                if state.parent_particle_id is not None
                else None
            )
            if state.parent_particle_id is not None and parent is None:
                raise ValueError("conditional statistic lineage has no runtime parent")
            if parent is not None:
                self._validate_record_binding(parent, expected_particle_id=state.parent_particle_id)
            expected_clusters = (
                (proposal.evidence_cluster_id,)
                if parent is None
                else (*parent.statistics.evidence_cluster_ids, proposal.evidence_cluster_id)
            )
            if (
                state.statistic_state_ref != analytic.reference
                or set(analytic.locations) != set(allowed_locations)
                or analytic.evidence_cluster_ids != expected_clusters
            ):
                raise ValueError(
                    "conditional statistic lineage does not match its receipt, parent, or support"
                )

        body = NativePreparedInputBody(
            workspace_runtime_id=self.runtime_id,
            receipts=receipts,
            statistics=statistics,
            snapshot_id=snapshot_id,
            source_frame=source_frame,
            ledger_head_sha256=ledger_head_sha256,
            unresolved_log_weight=unresolved_log_weight,
            registered_locations=allowed_locations,
            world_support_sha256=world_support_sha256,
            validated_projections=validated_projections,
        )
        fingerprint = native_content_sha256(body)
        cluster = receipts[0].proposal.evidence_cluster_id
        if cluster in self.input_journal:
            if self.input_journal[cluster] != fingerprint:
                raise ValueError("conflicting prepared candidate replay")
            if self.batch is None or self.batch.evidence_cluster_id != cluster:
                raise ValueError("stale prepared candidate replay")
            for weight in self.batch.particle_weights:
                record = self.records.get(weight.particle_id)
                if record is None:
                    raise ValueError("prepared candidate replay is missing a particle record")
                self._validate_record_binding(record, expected_particle_id=weight.particle_id)
            self._validate_current_batch()
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
                if parent.world_support_sha256 != world_support_sha256:
                    raise ValueError("particle parent belongs to another world support")
                self._validate_record_binding(parent, expected_particle_id=state.parent_particle_id)
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
            expected_clusters = (
                (proposal.evidence_cluster_id,)
                if parent is None
                else (*parent.statistics.evidence_cluster_ids, proposal.evidence_cluster_id)
            )
            if analytic.evidence_cluster_ids != expected_clusters:
                raise ValueError(
                    "conditional statistic cluster lineage differs from receipt or parent"
                )
            if state.ledger_lineage_ref != "hybrid-ledger:" + ledger_head_sha256:
                raise ValueError("particle cannot name a foreign ledger lineage")
            records[state.particle_id] = NativeParticleRecord(
                state,
                (() if parent is None else parent.event_chain_history) + (chain,),
                analytic,
                source_frame_sha256,
                source_frame,
                ledger_head_sha256,
                proposal.evidence_cluster_id,
                self.runtime_id,
                world_support_sha256,
                fingerprint,
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
        self._validate_persisted_state()
        assert self.batch is not None
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
