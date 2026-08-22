"""End-to-end ORRER -> RGRC -> map -> task consolidation loop (结构二 §1/§3).

Wires the real modules into one causal chain:

    CHEH/ORRER event revision (who really moved the object)
      -> RGRC EventDerivedUpdateLedger (reversibly (de)consolidate owner habit)
      -> map consistency revision bump (belief changed)
      -> task DecisionContext relevant-change check (continue / replan / cancel)
      -> execution feedback bound to the consistent context.

The loop reads the responsible-actor posterior straight from the CHEH history's
latest revision, so an ORRER re-attribution genuinely drives the ledger retract,
which drives the map revision bump, which drives the task decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from cpswm.contracts.base import ValidTimeInterval
from cpswm.contracts.decision_context import (
    AttributedCause,
    DecisionContext,
    MapConsistencyRevisions,
    RelevantChange,
    detect_relevant_change,
)
from cpswm.system.counterfactual_event_hypergraph.contracts import (
    EventHypothesisHistory,
    EventHypothesisRevision,
)

from .event_derived_update_ledger import EventDerivedDeltaRecord, EventDerivedUpdateLedger


@dataclass(frozen=True, slots=True)
class OwnerPlacement:
    """The owner's responsibility mass for the destination of one revision."""

    revision_id: UUID
    object_instance_id: UUID
    destination_location_id: UUID
    owner_mass: float


def owner_placement(revision: EventHypothesisRevision, owner_key: str) -> OwnerPlacement:
    mass = sum(
        hypothesis.posterior_probability
        for hypothesis in revision.hypotheses
        if hypothesis.responsible_actor_key == owner_key
    )
    return OwnerPlacement(
        revision_id=revision.revision_id,
        object_instance_id=revision.object_instance_id,
        destination_location_id=revision.destination_location_id,
        owner_mass=mass,
    )


class EventToTaskConsolidationLoop:
    """Compose ORRER revisions, the RGRC ledger, map revisions, and task decisions."""

    def __init__(
        self,
        *,
        owner_key: str,
        base_revisions: MapConsistencyRevisions,
        authorization_scope_id: UUID,
        model_version: str,
        code_version: str,
        parameter_block: str = "owner_habit_location",
        ledger: EventDerivedUpdateLedger | None = None,
    ) -> None:
        self._owner = owner_key
        self._revisions = base_revisions
        self._auth = authorization_scope_id
        self._model_version = model_version
        self._code_version = code_version
        self._block = parameter_block
        self._ledger = ledger or EventDerivedUpdateLedger()
        self._watermark = base_revisions.input_watermark
        self._delta_ids_by_revision: dict[UUID, list[UUID]] = {}

    @property
    def ledger(self) -> EventDerivedUpdateLedger:
        return self._ledger

    @property
    def revisions(self) -> MapConsistencyRevisions:
        return self._revisions

    def ingest_event_history(self, history: EventHypothesisHistory) -> OwnerPlacement:
        """Record the owner's responsibility mass for this revision as a habit delta."""

        revision = history.latest
        placement = owner_placement(revision, self._owner)
        if placement.owner_mass > 1e-12:
            self._watermark += 1
            record_id = uuid4()
            self._ledger.append_delta(
                EventDerivedDeltaRecord(
                    record_id=record_id,
                    event_hypothesis_id=history.hypothesis_set_id,
                    revision_id=revision.revision_id,
                    parent_revision_id=revision.parent_revision_id,
                    evidence_source_id=revision.source_detection_result_ids[-1],
                    actor_key=self._owner,
                    object_instance_id=revision.object_instance_id,
                    regime_id="owner-habit",
                    parameter_block=self._block,
                    location_id=revision.destination_location_id,
                    signed_delta=placement.owner_mass,
                    input_watermark=self._watermark,
                    model_version=self._model_version,
                    code_version=self._code_version,
                    authorization_scope_id=self._auth,
                    semantic_dedup_id=f"{revision.revision_id}:{self._owner}:{revision.destination_location_id}",
                )
            )
            self._delta_ids_by_revision.setdefault(revision.revision_id, []).append(record_id)
        return placement

    def apply_orrer_revision(
        self,
        revised_history: EventHypothesisHistory,
        *,
        superseded_revision_id: UUID,
    ) -> OwnerPlacement:
        """Retract the superseded revision's owner deltas, ingest the corrected one,
        and bump the map/projection revisions because the belief changed."""

        live = self._delta_ids_by_revision.get(superseded_revision_id, [])
        if live:
            self._watermark += 1
            self._ledger.retract_revision(
                revision_id=superseded_revision_id,
                watermark=self._watermark,
                reason="ORRER re-attributed the hidden event away from the owner",
                reversal_ids=[uuid4() for _ in live],
            )
        placement = self.ingest_event_history(revised_history)
        # The owner belief changed, so the derived map projection advances.
        self._revisions = MapConsistencyRevisions(
            belief_snapshot_id=uuid4(),
            projection_id=self._revisions.projection_id,
            projection_version=self._revisions.projection_version + 1,
            static_map_revision=self._revisions.static_map_revision,
            dynamic_map_revision=self._revisions.dynamic_map_revision + 1,
            event_history_revision=self._revisions.event_history_revision + 1,
            input_watermark=self._watermark,
        )
        return placement

    def owner_projection(self, *, object_instance_id: UUID) -> dict[UUID, float]:
        return self._ledger.owner_projection(
            actor_key=self._owner,
            object_instance_id=object_instance_id,
            parameter_block=self._block,
        )

    def decision_context(
        self,
        *,
        decision_time: datetime,
        rationale: str,
        attributed_cause: AttributedCause = AttributedCause.HABIT,
        staleness_budget_seconds: float = 120.0,
    ) -> DecisionContext:
        return DecisionContext.create(
            decision_id=uuid4(),
            decision_time=decision_time,
            valid_time=ValidTimeInterval(
                start=decision_time, end=decision_time + timedelta(minutes=5)
            ),
            staleness_budget_seconds=staleness_budget_seconds,
            revisions=self._revisions,
            attributed_cause=attributed_cause,
            authorization_scope_id=self._auth,
            habit_regime_model_version=self._model_version,
            model_versions=(("event_to_task_loop", "event-to-task@0.1"),),
            code_version=self._code_version,
            rationale=rationale,
        )

    def task_decision(
        self,
        pinned_context: DecisionContext,
        *,
        target_object_moved: bool,
        robot_pose_graph_corrected: bool = False,
        planned_path_blocked: bool = False,
        only_irrelevant_updates: bool = False,
        elapsed_seconds: float = 0.0,
    ) -> RelevantChange:
        """Run the snapshot-isolation invalidation check for a task pinned to an
        earlier context against the loop's current map revisions."""

        return detect_relevant_change(
            pinned_context,
            current=self._revisions,
            target_object_moved=target_object_moved,
            robot_pose_graph_corrected=robot_pose_graph_corrected,
            planned_path_blocked=planned_path_blocked,
            only_irrelevant_updates=only_irrelevant_updates,
            elapsed_seconds=elapsed_seconds,
        )
