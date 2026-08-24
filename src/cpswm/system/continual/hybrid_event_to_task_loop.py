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
* **Feedback projection (option A)**: an :class:`ExecutionFeedbackRecord` outcome
  is *projected and routed* to typed, likelihood-aware evidence
  (``project_execution_feedback``).  It is NOT yet folded into the ledger or
  republished to the map -- that backflow lands with the presence-log/map + ORRER
  outbox wiring after the map/ORRER core is handed over.

The loop only orchestrates; every guarantee (append-only, O(k) retract, atomic
snapshots, exact risk gate) lives in the real components it composes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID, uuid4

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    DecisionContextBinding,
    ExecutionFeedbackRecord,
)
from cpswm.world_model.grounded_search.concurrent_map_task import (
    BeliefSnapshot,
    ConstrainedDependencyBridge,
    ExactActionRiskVerifier,
    MapTaskCoordinator,
    TaskActionGraph,
    VersionedBeliefMap,
    VersionSwitchDecision,
)

from .execution_feedback_projector import ExecutionFeedbackProjector, ProjectedFeedbackEvidence
from .hybrid_statistics import (
    ConsolidationRiskCertificate,
    DirichletRLSFusion,
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
        # No shadow state: revision->delta, revision->location, and the watermark
        # are all derived from the authoritative ledger, so a loop rebuilt on a
        # recovered ledger keeps retracting, republishing, and writing correctly.
        self._feedback_projector = ExecutionFeedbackProjector()
        self._fusion = DirichletRLSFusion()

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
        # Derive strictly-increasing watermarks from the ledger head, so a loop
        # rebuilt on a recovered ledger never writes behind the log.
        return self._ledger.head_watermark + 1

    def _build_placement(
        self,
        placement: OwnerPlacementInput,
        *,
        delta_watermark: int,
        promotion_watermark: int,
    ) -> tuple[HybridStatisticDelta, HybridPromotion]:
        """Build the (quarantined delta, promotion) pair for one owner placement."""

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
            semantic_dedup_id=(
                f"{placement.revision_id}:{self._owner}:{placement.destination_location_id}"
            ),
            source_record_ids=(placement.source_record_id,),
            authorization_scope_id=self._auth,
            key=self._key(placement.destination_location_id),
            input_watermark=delta_watermark,
            model_version=self._model_version,
            code_version=self._code_version,
        )
        promotion = HybridPromotion(
            record_id=uuid4(),
            promotes_record_id=record_id,
            input_watermark=promotion_watermark,
            authorization_scope_id=self._auth,
            reason="owner-attributed hidden-event placement consolidated",
            risk_certificate=self._clean_certificate(record_id),
        )
        return delta, promotion

    def ingest_owner_placement(self, placement: OwnerPlacementInput) -> None:
        """Consolidate one revision's owner mass into the Hybrid RGRC ledger."""

        if placement.owner_mass <= 1e-12:
            return
        base = self._ledger.head_watermark
        delta, promotion = self._build_placement(
            placement, delta_watermark=base + 1, promotion_watermark=base + 2
        )
        self._ledger.append_delta(delta)
        self._ledger.promote(promotion)

    def retract_revision(self, revision_id: UUID) -> int:
        """Retract a superseded revision's owner deltas (O(k))."""

        live = self._ledger.live_promoted_records_for_revision(revision_id)
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
        """Atomically swap a superseded revision for its ORRER correction, then
        publish the changed habit locations as one map version.

        The retract-then-promote happens as a single all-or-nothing ledger step
        (:meth:`HybridStatisticLedger.replace_promoted_revision`): no task ever
        reads the window where the owner belief has been withdrawn but the
        correction is not yet in place, and the map is published only after the
        ledger commit succeeds.
        """

        if corrected.owner_mass <= 1e-12:
            # The correction attributes the event away from the owner entirely:
            # withdraw the belief, nothing new to promote.
            self.retract_revision(superseded_revision_id)
            return self.publish_snapshot()
        live = self._ledger.live_promoted_records_for_revision(superseded_revision_id)
        base = self._ledger.head_watermark
        corrected_delta, promotion = self._build_placement(
            corrected, delta_watermark=base + 2, promotion_watermark=base + 3
        )
        self._ledger.replace_promoted_revision(
            superseded_revision_id=superseded_revision_id,
            reversal_record_ids=tuple(uuid4() for _ in live),
            reversal_watermark=base + 1,
            reversal_reason="ORRER re-attributed the hidden event away from the owner",
            corrected_delta=corrected_delta,
            promotion=promotion,
        )
        return self.publish_snapshot()

    def publish_snapshot(self) -> BeliefSnapshot:
        """Publish the whole normalized owner-habit distribution as one map version.

        Owner habit over locations is a *single* B-F1 distribution (a Dirichlet
        location base fused with a per-location contextual RLS residual), so
        evidence at one location couples every other -- a change anywhere
        republishes the whole coupled set, not just the touched location.  The map
        version is not bumped when every node's belief payload and uncertainty is
        unchanged, so a no-op consolidation cannot spuriously trip a task replan.
        """

        keys = self._all_location_keys()
        if not keys:
            return self._map.snapshot()
        beliefs = self._fusion.predict(
            self._ledger,
            keys=tuple(keys.values()),
            context_features=[1.0] * self._ledger.feature_dim,
        )
        changes: dict[str, tuple[str, float]] = {}
        for location, key in keys.items():
            belief = beliefs[location]
            # Belief payload is the normalized distribution + its auditable parts;
            # the ledger version is deliberately excluded so an unchanged belief
            # produces an unchanged payload.
            payload_hash = hashlib.sha256(
                json.dumps(
                    {
                        "fused_probability": repr(belief.fused_probability),
                        "base_probability": repr(belief.base_probability),
                        "contextual_residual": repr(belief.contextual_residual),
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            # Uncertainty of "object is at this location" combines the normalized
            # belief with the evidence strength: a coupled drop in probability *or*
            # a drop in this location's own evidence both raise it.
            strength = max(0.0, self._ledger.projection(key).alpha)
            confidence = belief.fused_probability * (strength / (1.0 + strength))
            uncertainty = 1.0 - confidence
            changes[self.node_id(location)] = (payload_hash, uncertainty)
        return self._commit_if_changed(changes)

    def publish_project_two_revision(
        self,
        *,
        corrected_revision_id: UUID,
        posterior_content_hash: str,
        unresolved_probability: float,
    ) -> BeliefSnapshot:
        """Bind an event-posterior revision into a new atomic belief snapshot.

        A Project Two revision can be decision-relevant even when RGRC correctly
        defers its long-term statistic write.  Publishing a provenance-bound event
        node prevents the planner from silently continuing on the pre-feedback
        snapshot while preserving the distinction between event belief and habit
        statistics.
        """

        if len(posterior_content_hash) != 64:
            raise ValueError("posterior_content_hash must be a sha256 hex digest")
        if not 0.0 <= unresolved_probability <= 1.0:
            raise ValueError("unresolved_probability must lie in [0, 1]")
        return self._map.apply_update(
            {
                f"project_two_revision:{corrected_revision_id}": (
                    posterior_content_hash,
                    unresolved_probability,
                )
            }
        )

    def _all_location_keys(self) -> dict[UUID, StatisticKey]:
        keys: dict[UUID, StatisticKey] = {}
        for revision_id in self._ledger.revision_ids():
            for location in self._ledger.location_ids_for_revision(revision_id):
                keys[location] = self._key(location)
        return keys

    def _commit_if_changed(self, changes: dict[str, tuple[str, float]]) -> BeliefSnapshot:
        # Skip the version bump only when every node being published already holds
        # the identical belief, so a no-op republish cannot trip a task replan.
        # (Other objects' nodes may coexist in a shared map; they are untouched.)
        current = self._map.snapshot().node_map()
        if all(
            node_id in current
            and current[node_id].payload_hash == payload_hash
            and current[node_id].uncertainty == uncertainty
            for node_id, (payload_hash, uncertainty) in changes.items()
        ):
            return self._map.snapshot()
        return self._map.apply_update(changes)

    def recover_map(self) -> BeliefSnapshot:
        """Rebuild the published map from the authoritative ledger after a restart.

        A loop reconstructed on a recovered ledger starts with an empty map; the
        full-location publish republishes every location the ledger has ever
        touched, matching the log without replaying the original event stream.
        """

        return self.publish_snapshot()

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
        dependency_bridge: ConstrainedDependencyBridge | None = None,
    ) -> VersionSwitchDecision:
        """Decide whether a pinned task must switch map versions.

        An optional :class:`ConstrainedDependencyBridge` expands the set of belief
        nodes each action is considered to depend on (hard candidates plus learned
        soft relevance), so a coupled habit change that touches a node the action
        does not statically read can still impact it.  Hard dependencies and the
        exact risk verifier retain final authority.
        """

        return self._coordinator.evaluate_switch(
            task=task,
            current_action_order=current_action_order,
            old_snapshot=old_snapshot,
            new_snapshot=new_snapshot,
            verifier=verifier,
            dependency_bridge=dependency_bridge,
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

        projected = self.prepare_execution_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood_model,
        )
        self.commit_execution_feedback(projected)
        return projected

    def prepare_execution_feedback(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
        likelihood_model: ActionOutcomeLikelihoodModel,
    ) -> ProjectedFeedbackEvidence:
        """Project feedback without consuming its idempotency key."""

        context = binding.decision_context
        if context.authorization_scope_id != self._auth:
            raise ValueError(
                "feedback decision context authorization scope does not match the loop"
            )
        if feedback.target_entity is None or feedback.target_entity.entity_id != self._object:
            raise ValueError("feedback target object does not match the loop's configured object")
        return self._feedback_projector.prepare_execution_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood_model,
        )

    def commit_execution_feedback(self, projected: ProjectedFeedbackEvidence) -> None:
        """Commit replay state after the caller's statistic transaction succeeds."""

        self._feedback_projector.commit_execution_feedback(projected)

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
