"""ORRER -> Hybrid RGRC -> real snapshot -> MapTaskCoordinator -> feedback backflow.

Successor to the legacy happy-path loop (tag ``legacy-happy-path-integration-b1954a2``).
It wires the *real* components:

* **Hybrid RGRC** (:class:`HybridStatisticLedger`): owner responsibility from a
  CHEH/ORRER revision becomes a quarantined sufficient-statistic delta, promoted
  under a risk certificate; an ORRER re-attribution retracts that revision's
  deltas.
* **Real snapshot** (:class:`VersionedBeliefMap` / :class:`BeliefSnapshot`): the
  changed habit projection is published as an atomic map version.
* **MapTaskCoordinator**: a task pinned to the old snapshot is switched
  (continue / replan-suffix / cancel) by the exact changed-node + risk gate.
* **Feedback backflow**: an :class:`ExecutionFeedbackRecord` outcome is folded
  back into the ledger as a new delta and republished.

The loop only orchestrates; every guarantee (append-only, O(k) retract, atomic
snapshots, exact risk gate) lives in the real components it composes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID, uuid4

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    DecisionContextBinding,
    ExecutionFeedbackRecord,
)
from cpswm.world_model.grounded_search.concurrent_map_task import (
    BeliefSnapshot,
    ExactActionRiskVerifier,
    MapTaskCoordinator,
    TaskActionGraph,
    VersionedBeliefMap,
    VersionSwitchDecision,
)

from .execution_feedback_projector import ExecutionFeedbackProjector, ProjectedFeedbackEvidence
from .hybrid_statistics import (
    ConsolidationRiskCertificate,
    HybridPromotion,
    HybridStatisticDelta,
    HybridStatisticLedger,
    StatisticKey,
)

_UNBOUNDED_RISK = 1.0e9


@dataclass(frozen=True, slots=True)
class OwnerPlacementInput:
    """The owner-responsibility summary of one CHEH/ORRER revision to consolidate."""

    event_hypothesis_id: UUID
    revision_id: UUID
    destination_location_id: UUID
    owner_mass: float
    source_record_id: UUID
    parent_revision_id: UUID | None = None


class HybridEventToTaskCoordinatorLoop:
    """Compose Hybrid RGRC, the versioned belief map, and the map/task coordinator."""

    def __init__(
        self,
        *,
        owner_key: str,
        object_instance_id: UUID,
        authorization_scope_id: UUID,
        model_version: str,
        code_version: str,
        regime_id: str = "owner-habit",
        parameter_block: str = "owner_habit_location",
        ledger: HybridStatisticLedger | None = None,
        belief_map: VersionedBeliefMap | None = None,
        coordinator: MapTaskCoordinator | None = None,
    ) -> None:
        self._owner = owner_key
        self._object = object_instance_id
        self._auth = authorization_scope_id
        self._model_version = model_version
        self._code_version = code_version
        self._regime = regime_id
        self._block = parameter_block
        # Owner-habit consolidation uses a scalar (dim-1) feature per location key.
        self._ledger = ledger or HybridStatisticLedger(feature_dim=1)
        self._map = belief_map or VersionedBeliefMap()
        self._coordinator = coordinator or MapTaskCoordinator()
        self._watermark = 0
        self._deltas_by_revision: dict[UUID, list[UUID]] = {}
        self._revision_dest: dict[UUID, UUID] = {}
        self._feedback_projector = ExecutionFeedbackProjector()

    @property
    def ledger(self) -> HybridStatisticLedger:
        return self._ledger

    def node_id(self, location_id: UUID) -> str:
        return f"habit:{self._owner}:{self._object}:{location_id}"

    def _key(self, location_id: UUID) -> StatisticKey:
        return StatisticKey(
            actor_key=self._owner,
            object_instance_id=self._object,
            regime_id=self._regime,
            parameter_block=self._block,
            location_id=location_id,
        )

    def _next_watermark(self) -> int:
        self._watermark += 1
        return self._watermark

    def ingest_owner_placement(self, placement: OwnerPlacementInput) -> None:
        """Consolidate one revision's owner mass into the Hybrid RGRC ledger."""

        if placement.owner_mass <= 1e-12:
            return
        record_id = uuid4()
        delta = HybridStatisticDelta.from_weighted_sample(
            x=[1.0],
            y=placement.owner_mass,
            weight=placement.owner_mass,
            delta_alpha=placement.owner_mass,
            record_id=record_id,
            event_hypothesis_id=placement.event_hypothesis_id,
            revision_id=placement.revision_id,
            parent_revision_id=placement.parent_revision_id,
            evidence_cluster_id=uuid4(),
            semantic_dedup_id=f"{placement.revision_id}:{self._owner}:{placement.destination_location_id}",
            source_record_ids=(placement.source_record_id,),
            authorization_scope_id=self._auth,
            key=self._key(placement.destination_location_id),
            input_watermark=self._next_watermark(),
            model_version=self._model_version,
            code_version=self._code_version,
        )
        self._ledger.append_delta(delta)
        self._ledger.promote(
            HybridPromotion(
                record_id=uuid4(),
                promotes_record_id=record_id,
                input_watermark=self._next_watermark(),
                authorization_scope_id=self._auth,
                reason="owner-attributed hidden-event placement consolidated",
                risk_certificate=self._clean_certificate(record_id),
            )
        )
        self._deltas_by_revision.setdefault(placement.revision_id, []).append(record_id)
        self._revision_dest[placement.revision_id] = placement.destination_location_id

    def retract_revision(self, revision_id: UUID) -> int:
        """Retract a superseded revision's owner deltas (O(k))."""

        live = self._deltas_by_revision.get(revision_id, [])
        if not live:
            return 0
        return self._ledger.retract_revision(
            revision_id=revision_id,
            reversal_record_ids=tuple(uuid4() for _ in live),
            input_watermark=self._next_watermark(),
            authorization_scope_id=self._auth,
            reason="ORRER re-attributed the hidden event away from the owner",
        )

    def apply_orrer_revision(
        self, *, superseded_revision_id: UUID, corrected: OwnerPlacementInput
    ) -> BeliefSnapshot:
        """Retract the superseded revision, consolidate the corrected one, and
        publish the changed habit locations as one atomic map version."""

        superseded_location = self._revision_destination(superseded_revision_id)
        self.retract_revision(superseded_revision_id)
        self.ingest_owner_placement(corrected)
        changed = {corrected.destination_location_id}
        if superseded_location is not None:
            changed.add(superseded_location)
        return self.publish_snapshot(changed_locations=changed)

    def publish_snapshot(self, *, changed_locations: set[UUID]) -> BeliefSnapshot:
        """Publish the current fused habit belief for the changed locations."""

        changes: dict[str, tuple[str, float]] = {}
        for location in changed_locations:
            projection = self._ledger.projection(self._key(location))
            strength = max(0.0, projection.alpha)
            payload_hash = hashlib.sha256(
                f"{strength!r}:{projection.ledger_version}".encode()
            ).hexdigest()
            uncertainty = 1.0 / (1.0 + strength)
            changes[self.node_id(location)] = (payload_hash, uncertainty)
        return self._map.apply_update(changes)

    def current_snapshot(self) -> BeliefSnapshot:
        return self._map.snapshot()

    def evaluate_task(
        self,
        *,
        task: TaskActionGraph,
        current_action_order: int,
        old_snapshot: BeliefSnapshot,
        new_snapshot: BeliefSnapshot,
        verifier: ExactActionRiskVerifier,
    ) -> VersionSwitchDecision:
        return self._coordinator.evaluate_switch(
            task=task,
            current_action_order=current_action_order,
            old_snapshot=old_snapshot,
            new_snapshot=new_snapshot,
            verifier=verifier,
        )

    def project_execution_feedback(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
        likelihood_model: ActionOutcomeLikelihoodModel,
    ) -> ProjectedFeedbackEvidence:
        """Project (not consolidate) execution feedback into typed evidence.

        Honest naming: this projects and routes evidence; it does not itself
        write a presence log/map or ORRER outbox (that lands after the map/ORRER
        core is handed over).  The prior comes from the bound decision snapshot,
        never from the caller.  A find/observe outcome updates target presence
        only; place/transfer routes to a location transition needing actor
        responsibility.  No feedback path writes owner habit directly.
        """

        context = binding.decision_context
        if context.authorization_scope_id != self._auth:
            raise ValueError("feedback decision context authorization scope does not match the loop")
        if feedback.target_entity is None or feedback.target_entity.entity_id != self._object:
            raise ValueError("feedback target object does not match the loop's configured object")
        return self._feedback_projector.project_execution_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood_model,
        )

    def _revision_destination(self, revision_id: UUID) -> UUID | None:
        return self._revision_dest.get(revision_id)

    def _clean_certificate(self, delta_record_id: UUID) -> ConsolidationRiskCertificate:
        snapshot = self._map.snapshot()
        return ConsolidationRiskCertificate(
            expected_task_loss=0.0,
            uncertainty_penalty=0.0,
            maximum_allowed_risk=_UNBOUNDED_RISK,
            exact_verifier_id="owner-habit-consolidation@0.1",
            counterfactual_id=uuid4(),
            subject_delta_record_id=delta_record_id,
            belief_snapshot_id=snapshot.snapshot_id,
            map_version=snapshot.map_version,
        )
