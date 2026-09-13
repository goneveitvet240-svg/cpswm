"""Causal sensor delivery into the existing production memory/revision runtime.

This bridge owns arrival order and invokes a configured perception producer. It
never derives semantic evidence from evaluator metadata, raw hashes, or missing
pixels. The producer and calibrated feedback policy are trusted dependencies,
not authenticated by this module. No trained producer or physical executor is
bundled here; returned location suggestions are not execution receipts.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Literal, Protocol
from uuid import UUID, uuid4

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    DecisionContextBinding,
    EntityType,
    ExecutionFeedbackRecord,
    RobotActionType,
    SourceType,
)
from cpswm.contracts.base import require_aware
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.system.continual.project_one_feedback import ExecutionFeedbackInterpretationPolicy
from cpswm.system.prototype_spine import (
    PrototypeRevisionResult,
    PrototypeStepResult,
    PrototypeTransition,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_execution import (
    StructureTwoExecutionTrace,
    TraceAbortAck,
    TraceCommitAck,
    canonical_legacy_ordinary_transition_plan,
    seal_trace_abort_ack,
    seal_trace_commit_ack,
    verify_execution_trace,
)
from cpswm.system.structure_two_production_system import StructureTwoProductionSystem


def _utc(value: datetime) -> datetime:
    return require_aware(value, "causal time").astimezone(UTC)


@dataclass(frozen=True)
class GroundedTransition:
    """Producer output: evidence values plus exact visible source dependencies.

    Source IDs name the batch consumed by the producer, not a per-record proof.
    A producer must obtain opportunity propensities from its registered acquisition model,
    not infer them from whether an object was found. Hashes establish dependency
    identity only; they do not establish calibration or detector correctness.
    """

    transition: PrototypeTransition
    source_observation_ids: tuple[UUID, ...]
    producer_version: str
    calibration_id: str


class PerceptionProducer(Protocol):
    def infer(
        self,
        visible_prefix: tuple[RawModalityObservation, ...],
        *,
        cutoff: datetime,
    ) -> GroundedTransition | None:
        """Return a new grounded transition, or None when evidence is insufficient.

        Inputs are immutable raw wire values, never simulator truth. Implementors
        must retain unknown actors/instances and use independent calibration.
        """
        ...


class _TraceJournal:
    """In-process trace retention, not independent custody or crash durability."""

    def __init__(self) -> None:
        self._traces: dict[UUID, str] = {}

    def commit(self, trace: StructureTwoExecutionTrace, /) -> TraceCommitAck:
        verify_execution_trace(trace)
        ack = seal_trace_commit_ack(trace)
        key = trace.runtime_execution_id
        value = trace.model_dump_json()
        if key in self._traces and self._traces[key] != value:
            raise ValueError("conflicting execution trace identity")
        self._traces[key] = value
        return ack

    def abort(self, trace: StructureTwoExecutionTrace, /, *, reason: str) -> TraceAbortAck:
        self._traces.pop(trace.runtime_execution_id, None)
        return seal_trace_abort_ack(trace, reason=reason)

    def values(self) -> tuple[StructureTwoExecutionTrace, ...]:
        return tuple(
            StructureTwoExecutionTrace.model_validate_json(x) for x in self._traces.values()
        )


@dataclass(frozen=True)
class DeliveryReceipt:
    source_ids: tuple[UUID, ...]
    source_prefix_sha256: str
    received_at: datetime
    status: str
    result: PrototypeStepResult | None


@dataclass(frozen=True)
class PlacementCommand:
    """A single-use PUT_BACK command, never a SEARCH location belief."""

    action_id: UUID
    object_instance_id: UUID
    location_id: UUID
    snapshot_id: UUID
    distribution: tuple[tuple[UUID, float], ...]
    decision_time: datetime


@dataclass(frozen=True)
class PlacementFeedbackDelivery:
    feedback: ExecutionFeedbackRecord
    received_at: datetime


class PlacementExecutor(Protocol):
    def execute(self, command: PlacementCommand) -> PlacementFeedbackDelivery:
        """Execute once and return observed feedback; do not invent success."""
        ...


@dataclass(frozen=True)
class PlacementDispatch:
    command: PlacementCommand
    status: str
    feedback_json: str | None
    received_at: datetime | None = None


class ContinuousEvidenceInput:
    """Serialize actual delivery, inference and late feedback on one live system.

    The standard traced transition lane is reused explicitly. This is not the
    missing full-axis neural/P5 assembly and cannot authorize that acceptance
    gate. Raw admission can proceed without a perception producer; semantic
    advancement then raises rather than synthesizing a transition.
    """

    def __init__(
        self,
        *,
        system: StructureTwoProductionSystem,
        execution_lane: Literal["legacy_component_diagnostic"],
        household_id: UUID,
        session_id: UUID,
        trace_id: UUID,
        producer: PerceptionProducer | None = None,
    ) -> None:
        if execution_lane != "legacy_component_diagnostic":
            raise ValueError("full P5/neural assembly is not supplied by this diagnostic bridge")
        self._system = system
        self._scope = (household_id, session_id, trace_id)
        self._producer = producer
        self._last_cutoff: datetime | None = None
        self._raw: dict[UUID, RawModalityObservation] = {}
        self._received: dict[UUID, datetime] = {}
        self._last_arrival: datetime | None = None
        self._advanced: dict[UUID, tuple[str, DeliveryReceipt]] = {}
        self._feedback: dict[UUID, tuple[str, PrototypeRevisionResult]] = {}
        self._trace_journal = _TraceJournal()
        self._commands: dict[UUID, PlacementCommand] = {}
        self._command_hashes: dict[UUID, str] = {}
        self._dispatches: dict[UUID, PlacementDispatch] = {}
        self._lock = RLock()
        self._busy = False

    def _enter(self) -> None:
        if self._busy:
            raise RuntimeError("reentrant continuous input is forbidden")
        self._busy = True

    def _scope_check(self, metadata: object) -> None:
        scope = tuple(getattr(metadata, key) for key in ("household_id", "session_id", "trace_id"))
        if scope != self._scope:
            raise ValueError("cross-household/session/trace input")

    def admit(
        self, observations: tuple[RawModalityObservation, ...], *, received_at: datetime
    ) -> tuple[UUID, ...]:
        """Retain one atomic raw batch; late capture time is legal, backdating is not.

        The transport owns received_at. Replaying identical bytes does not change
        their original arrival or make previously unavailable evidence visible.
        """
        with self._lock:
            self._enter()
            try:
                when = _utc(received_at)
                if any(t is not None and when < t for t in (self._last_arrival, self._last_cutoff)):
                    raise ValueError("delivery order moved backwards")
                if not observations:
                    raise ValueError("empty sensor delivery")
                pending: dict[UUID, RawModalityObservation] = {}
                for raw in observations:
                    if (
                        type(raw) is not RawModalityObservation
                        or type(raw.payload_bytes) is not bytes
                    ):
                        raise ValueError("raw input must retain immutable bytes")
                    raw = deepcopy(raw)
                    envelope = raw.envelope()
                    if envelope.metadata.source_type not in {
                        SourceType.SENSOR,
                        SourceType.SIMULATION,
                        SourceType.IMPORT,
                    }:
                        raise ValueError("raw observations require a sensor or archive source")
                    self._scope_check(envelope.identity)
                    if envelope.oracle_channel:
                        raise ValueError("oracle data cannot enter the method stream")
                    if not _utc(envelope.capture_time) <= _utc(envelope.arrival_time) <= when:
                        raise ValueError("future capture or delivery timestamp")
                    key = envelope.identity.observation_id
                    if key in pending:
                        raise ValueError("duplicate observation within batch")
                    if key in self._raw and self._raw[key] != raw:
                        raise ValueError("observation identity reused with changed content")
                    pending[key] = raw
                for key, raw in pending.items():
                    if key not in self._raw:
                        self._raw[key] = raw
                        self._received[key] = when
                self._last_arrival = when
                return tuple(pending)
            finally:
                self._busy = False

    def visible_prefix(self, *, cutoff: datetime) -> tuple[RawModalityObservation, ...]:
        with self._lock:
            when = _utc(cutoff)
            # Insertion order retains transport arrival order, not capture order.
            return tuple(
                deepcopy(raw) for key, raw in self._raw.items() if self._received[key] <= when
            )

    def advance(self, *, cutoff: datetime) -> DeliveryReceipt:
        with self._lock:
            self._enter()
            try:
                when = _utc(cutoff)
                if any(t is not None and when < t for t in (self._last_arrival, self._last_cutoff)):
                    raise ValueError("cannot revise live state with an earlier causal cutoff")
                if self._producer is None:
                    raise RuntimeError(
                        "PERCEPTION_PRODUCER_UNAVAILABLE: raw retained; no inference"
                    )
                prefix = self.visible_prefix(cutoff=when)
                if not prefix:
                    raise ValueError("no delivered sensor evidence")
                digest = content_sha256(
                    tuple((r.envelope_json, r.capture_receipt_sha256) for r in prefix)
                )
                produced = self._producer.infer(prefix, cutoff=when)
                if produced is None:
                    self._last_cutoff = when
                    return DeliveryReceipt((), digest, when, "INSUFFICIENT_SEMANTIC_EVIDENCE", None)
                item = deepcopy(produced)
                if not item.producer_version.strip() or not item.calibration_id.strip():
                    raise ValueError("perception producer and calibration must be named")
                ids = item.source_observation_ids
                available = {r.envelope().identity.observation_id for r in prefix}
                if not ids or len(set(ids)) != len(ids) or not set(ids) <= available:
                    raise ValueError("perception used missing, duplicate or undelivered source")
                transition = item.transition
                records = (
                    transition.opportunity,
                    transition.before,
                    transition.after,
                    *transition.evidence,
                )
                for record in records:
                    self._scope_check(record.metadata)
                    if _utc(record.metadata.recorded_time) > when:
                        raise ValueError("perception output contains a future record")
                if any(
                    t is not None and _utc(t) > when
                    for t in (
                        transition.before.detection_time,
                        transition.after.detection_time,
                        transition.opportunity.opportunity_time,
                    )
                ):
                    raise ValueError("future detection")
                input_hash = content_sha256(item)
                key = transition.after.metadata.record_id
                old = self._advanced.get(key)
                if old is not None:
                    if old[0] != input_hash:
                        raise ValueError("perception record identity reused with changed evidence")
                    self._last_cutoff = when
                    return deepcopy(old[1])
                # The core handles hypotheses, propensity, cause/regime competition,
                # memory writes and rollback. No caller supplies a posterior here.
                result = self._system.process_transition(
                    transition,
                    execution_plan=canonical_legacy_ordinary_transition_plan(),
                    trace_sink=self._trace_journal,
                )
                receipt = DeliveryReceipt(
                    ids, digest, when, "PRODUCTION_TRANSITION_COMMITTED", deepcopy(result)
                )
                self._advanced[key] = (input_hash, receipt)
                self._last_cutoff = when
                return deepcopy(receipt)
            finally:
                self._busy = False

    def consume_feedback(
        self,
        *,
        feedback: ExecutionFeedbackRecord,
        binding: DecisionContextBinding,
        likelihood_model: ActionOutcomeLikelihoodModel,
        received_at: datetime,
        policy: ExecutionFeedbackInterpretationPolicy | None = None,
    ) -> PrototypeRevisionResult:
        """Consume delayed execution evidence against its original decision binding.

        Actual feedback and a calibrated likelihood are required. This method
        never turns a suggestion or raw capture into an execution-success record.
        The policy is a configured trusted dependency, not a learned policy here.
        """
        with self._lock:
            self._enter()
            try:
                when = _utc(received_at)
                if any(t is not None and when < t for t in (self._last_arrival, self._last_cutoff)):
                    raise ValueError("feedback arrival moved backwards")
                feedback = type(feedback).model_validate_json(feedback.model_dump_json())
                binding = type(binding).model_validate_json(binding.model_dump_json())
                likelihood_model = type(likelihood_model).model_validate_json(
                    likelihood_model.model_dump_json()
                )
                self._scope_check(feedback.metadata)
                if (
                    max(
                        _utc(feedback.metadata.recorded_time),
                        _utc(feedback.valid_time.start),
                        _utc(feedback.valid_time.end or feedback.valid_time.start),
                    )
                    > when
                ):
                    raise ValueError("feedback arrives before execution evidence exists")
                fingerprint = content_sha256((feedback, binding, likelihood_model))
                key = feedback.metadata.record_id
                previous = self._feedback.get(key)
                if previous:
                    if previous[0] != fingerprint:
                        raise ValueError("feedback identity reused with changed content")
                    self._last_arrival = when
                    return deepcopy(previous[1])
                result = self._system.core.process_execution_feedback(
                    feedback=feedback,
                    binding=binding,
                    likelihood_model=likelihood_model,
                    policy=policy,
                )
                self._feedback[key] = (fingerprint, deepcopy(result))
                self._last_arrival = when
                return deepcopy(result)
            finally:
                self._busy = False

    def current_habit_location_distribution(self) -> Mapping[UUID, float]:
        """Fresh habitual-location readout; not a SEARCH physical-location belief."""
        with self._lock:
            return dict(
                self._system.core.action_location_distribution(self._system.core.current_snapshot)
            )

    def execution_traces(self) -> tuple[StructureTwoExecutionTrace, ...]:
        with self._lock:
            return self._trace_journal.values()

    def prepare_habit_placement(self, *, decision_time: datetime) -> PlacementCommand:
        """Select the existing habitual-location argmax with deterministic ties.

        This connects the current core readout to an explicit PUT_BACK command;
        it does not select a combined task utility or an autonomous task schedule.
        """
        with self._lock:
            self._enter()
            try:
                when = _utc(decision_time)
                if any(t is not None and when < t for t in (self._last_arrival, self._last_cutoff)):
                    raise ValueError("decision predates delivered evidence")
                self._require_resolved_dispatches()
                core = self._system.core
                snapshot = core.current_snapshot
                probabilities = tuple(
                    sorted(
                        core.action_location_distribution(snapshot).items(), key=lambda x: str(x[0])
                    )
                )
                location = max(probabilities, key=lambda x: x[1])[0]
                command = PlacementCommand(
                    uuid4(),
                    core.object_instance_id,
                    location,
                    snapshot.snapshot_id,
                    probabilities,
                    when,
                )
                self._commands[command.action_id] = command
                self._command_hashes[command.action_id] = content_sha256(command)
                self._last_cutoff = when
                return command
            finally:
                self._busy = False

    def execute_placement(
        self, command: PlacementCommand, *, executor: PlacementExecutor
    ) -> PlacementDispatch:
        """Dispatch a live command once, with explicit uncertain-outcome handling.

        A raised call or malformed reply may still have moved the object. Retain
        OUTCOME_UNCERTAIN and never automatically retry or roll back that physical
        action. This in-process journal does not guarantee crash-safe exactly-once
        delivery; a real transport must provide its own durable action IDs.
        """
        with self._lock:
            self._enter()
            try:
                if self._commands.get(command.action_id) is not command:
                    raise ValueError("placement command is not this session's issued capability")
                if self._command_hashes[command.action_id] != content_sha256(command):
                    raise ValueError("placement command content was changed after issue")
                if command.action_id in self._dispatches:
                    raise ValueError("placement already dispatched; reconcile instead of retrying")
                self._require_resolved_dispatches()
                core = self._system.core
                if command.snapshot_id != core.current_snapshot.snapshot_id:
                    raise ValueError("placement command is stale after a belief revision")
                distribution = tuple(
                    sorted(
                        self.current_habit_location_distribution().items(), key=lambda x: str(x[0])
                    )
                )
                if distribution != command.distribution:
                    raise ValueError("placement readout changed since command issue")
                self._dispatches[command.action_id] = PlacementDispatch(
                    deepcopy(command), "OUTCOME_UNCERTAIN", None
                )
                # Do not expose the owned command or command journal to callback aliases.
                delivery = executor.execute(deepcopy(command))
                return self._accept_placement_delivery(command.action_id, delivery)
            finally:
                self._busy = False

    def placement_dispatches(self) -> tuple[PlacementDispatch, ...]:
        with self._lock:
            return deepcopy(tuple(self._dispatches.values()))

    def _require_resolved_dispatches(self) -> None:
        if any(r.status == "OUTCOME_UNCERTAIN" for r in self._dispatches.values()):
            raise RuntimeError(
                "uncertain placement requires reconciliation before another dispatch"
            )

    def _accept_placement_delivery(
        self, action_id: UUID, delivery: PlacementFeedbackDelivery
    ) -> PlacementDispatch:
        original = self._dispatches[action_id]
        command = original.command
        when = _utc(delivery.received_at)
        if any(t is not None and when < t for t in (self._last_arrival, self._last_cutoff)):
            raise ValueError("placement receipt arrival moved backwards")
        feedback = ExecutionFeedbackRecord.model_validate_json(delivery.feedback.model_dump_json())
        self._scope_check(feedback.metadata)
        if (
            feedback.action_id != command.action_id
            or feedback.action_type is not RobotActionType.PLACE
            or feedback.target_entity is None
            or feedback.target_entity.entity_id != command.object_instance_id
            or feedback.target_entity.entity_type is not EntityType.OBJECT_INSTANCE
            or feedback.metadata.source_type is not SourceType.ACTION
            or feedback.attempted_location_id != command.location_id
        ):
            raise ValueError("executor feedback does not describe the issued placement")
        start = _utc(feedback.valid_time.start)
        end = _utc(feedback.valid_time.end or feedback.valid_time.start)
        recorded = _utc(feedback.metadata.recorded_time)
        if not command.decision_time <= start <= end <= recorded <= when:
            raise ValueError("placement decision/execution/record/receipt times are inconsistent")
        value = feedback.model_dump_json()
        if original.status == "FEEDBACK_RECEIVED" and original.feedback_json != value:
            raise ValueError("conflicting feedback for an already reconciled placement")
        result = (
            original
            if original.status == "FEEDBACK_RECEIVED"
            else PlacementDispatch(deepcopy(command), "FEEDBACK_RECEIVED", value, when)
        )
        self._dispatches[action_id] = result
        self._last_arrival = when
        return deepcopy(result)

    def reconcile_placement(
        self, action_id: UUID, delivery: PlacementFeedbackDelivery
    ) -> PlacementDispatch:
        """Accept a later original-action receipt without sending another command."""
        with self._lock:
            self._enter()
            try:
                if action_id not in self._dispatches:
                    raise ValueError("cannot reconcile an action this session never dispatched")
                return self._accept_placement_delivery(action_id, delivery)
            finally:
                self._busy = False
