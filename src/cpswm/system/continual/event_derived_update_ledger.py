"""Event-derived habit-update ledger (RGRC reversible consolidation).

结构二 §4.7#5 (RGRC) x §4.7#2 (ORRER): long-term habit statistics must be an
*immutable, append-only* log that is reconstructable and reversible, so that when
ORRER revises the actor responsibility of a hidden event, the habit updates
derived from that event can be reversed and a *corrected* revision can re-enter
the projection, all while keeping full history.

Design (rebuilt 2026-08-22 after review):

* **Immutable append-only log.** The ledger only ever *appends*
  :class:`EventDerivedDeltaRecord`, :class:`EventDerivedDeltaReversal`, and
  :class:`EventDerivedDeltaPromotion` records.  It never mutates or replaces a
  record.  The projection is a cache derived from the log and always equals a
  from-log rebuild.
* **True O(k) targeted retract.** A per-event and per-revision index maps to the
  exact delta record ids, so retracting a revision touches only that revision's
  ``k`` live deltas -- not the whole log.  ``retract_revision`` reports
  records-touched and wall-clock; the full rebuild reports records-scanned.
* **Revision supersede / reactivate (not permanent sealing).** Retract cancels a
  specific *revision's* deltas via reversal records.  A later corrected revision
  appends new deltas (parent = the superseded revision), so ORRER's later
  correction genuinely re-enters long-term memory.
* **Quarantine -> promote -> retract -> reactivate** consolidation states: a
  delta counts toward the projection only while PROMOTED and not reversed.

Contamination is measured as a distribution distance from a corrected/reference
projection, not "any non-home mass", so multi-location habits are not misjudged.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from enum import StrEnum
from math import isfinite
from typing import Annotated
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel

FiniteFloat = Annotated[float, Field()]
ProjectionKey = tuple[str, UUID, str, UUID]  # (actor, object, parameter_block, location)


class ConsolidationState(StrEnum):
    """RGRC state of an event-derived delta."""

    QUARANTINED = "quarantined"
    PROMOTED = "promoted"
    RETRACTED = "retracted"
    REACTIVATED = "reactivated"


class EventDerivedDeltaRecord(ContractModel):
    """One immutable, provenance-complete soft-count delta derived from an event."""

    record_id: UUID
    event_hypothesis_id: UUID
    revision_id: UUID
    parent_revision_id: UUID | None = None
    evidence_source_id: UUID
    actor_key: str = Field(min_length=1)
    object_instance_id: UUID
    regime_id: str = Field(min_length=1)
    parameter_block: str = Field(min_length=1)
    location_id: UUID
    signed_delta: FiniteFloat
    input_watermark: int = Field(ge=0)
    model_version: str = Field(min_length=1)
    code_version: str = Field(min_length=1)
    authorization_scope_id: UUID | None = None
    semantic_dedup_id: str = Field(min_length=1)
    initial_state: ConsolidationState = ConsolidationState.PROMOTED

    @field_validator("signed_delta")
    @classmethod
    def validate_finite(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("signed_delta must be finite (no NaN/Inf)")
        return value

    @field_validator("initial_state")
    @classmethod
    def validate_initial_state(cls, value: ConsolidationState) -> ConsolidationState:
        if value not in {ConsolidationState.QUARANTINED, ConsolidationState.PROMOTED}:
            raise ValueError("a delta may only be created QUARANTINED or PROMOTED")
        return value

    @property
    def projection_key(self) -> ProjectionKey:
        return (self.actor_key, self.object_instance_id, self.parameter_block, self.location_id)


class EventDerivedDeltaReversal(ContractModel):
    """Cancels one delta record; never deletes it (append-only history)."""

    record_id: UUID
    reverses_record_id: UUID
    revision_id: UUID
    input_watermark: int = Field(ge=0)
    reason: str = Field(min_length=1)
    authorization_scope_id: UUID | None = None


class EventDerivedDeltaPromotion(ContractModel):
    """Promotes a quarantined delta into the projection."""

    record_id: UUID
    promotes_record_id: UUID
    input_watermark: int = Field(ge=0)
    reason: str = Field(min_length=1)
    authorization_scope_id: UUID | None = None


class LedgerIntegrityError(RuntimeError):
    """Raised on a write that would violate append-only ledger invariants."""


class RetractionCost(ContractModel):
    records_touched: int
    wall_clock_seconds: float


class RebuildCost(ContractModel):
    records_scanned: int
    wall_clock_seconds: float


class FullRerunEquivalenceReceipt(ContractModel):
    """Proof that the incremental RGRC projection equals append-log replay."""

    actor_key: str = Field(min_length=1)
    object_instance_id: UUID
    parameter_block: str = Field(min_length=1)
    cached_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rebuilt_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cached_projection: dict[UUID, float]
    rebuilt_projection: dict[UUID, float]
    equivalent: bool
    records_scanned: int = Field(ge=0)
    rebuild_wall_clock_seconds: float = Field(ge=0.0)

    @model_validator(mode="after")
    def validate_equivalence(self) -> FullRerunEquivalenceReceipt:
        if self.cached_projection_sha256 != _projection_sha256(self.cached_projection):
            raise ValueError("cached projection hash mismatch")
        if self.rebuilt_projection_sha256 != _projection_sha256(self.rebuilt_projection):
            raise ValueError("rebuilt projection hash mismatch")
        if self.equivalent != (self.cached_projection == self.rebuilt_projection):
            raise ValueError("full-rerun equivalence flag does not match projections")
        return self


def _projection_sha256(projection: Mapping[UUID, float]) -> str:
    payload = {str(key): repr(projection[key]) for key in sorted(projection, key=str)}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class EventDerivedUpdateLedger:
    """Immutable append-only RGRC ledger with indexed O(k) retract."""

    def __init__(self) -> None:
        self._log: list[
            EventDerivedDeltaRecord | EventDerivedDeltaReversal | EventDerivedDeltaPromotion
        ] = []
        self._delta_by_id: dict[UUID, EventDerivedDeltaRecord] = {}
        self._by_event: dict[UUID, list[UUID]] = {}
        self._by_revision: dict[UUID, list[UUID]] = {}
        self._reversed: set[UUID] = set()
        self._promoted: set[UUID] = set()
        self._dedup: set[str] = set()
        self._record_ids: set[UUID] = set()
        self._revision_event: dict[UUID, UUID] = {}
        self._revision_parent: dict[UUID, UUID | None] = {}
        self._last_watermark: int = -1
        self._projection: dict[ProjectionKey, float] = {}
        self._head_hash = "0" * 64

    # --- append-only writes --------------------------------------------------

    def append_delta(self, delta: EventDerivedDeltaRecord) -> EventDerivedDeltaRecord:
        self._check_new_record_id(delta.record_id)
        self._check_watermark(delta.input_watermark)
        if delta.semantic_dedup_id in self._dedup:
            raise LedgerIntegrityError(f"duplicate semantic_dedup_id {delta.semantic_dedup_id!r}")
        self._validate_revision(delta)
        self._append_to_log(delta)
        self._record_ids.add(delta.record_id)
        self._dedup.add(delta.semantic_dedup_id)
        self._delta_by_id[delta.record_id] = delta
        self._by_event.setdefault(delta.event_hypothesis_id, []).append(delta.record_id)
        self._by_revision.setdefault(delta.revision_id, []).append(delta.record_id)
        self._last_watermark = delta.input_watermark
        if delta.initial_state == ConsolidationState.PROMOTED:
            self._promoted.add(delta.record_id)
            self._apply_to_projection(delta, +1.0)
        return delta

    def append_promotion(self, promotion: EventDerivedDeltaPromotion) -> None:
        self._check_new_record_id(promotion.record_id)
        self._check_watermark(promotion.input_watermark)
        delta = self._delta_by_id.get(promotion.promotes_record_id)
        if delta is None:
            raise LedgerIntegrityError("promotion targets an unknown delta record")
        if promotion.promotes_record_id in self._reversed:
            raise LedgerIntegrityError("a retracted delta cannot be promoted")
        if promotion.promotes_record_id in self._promoted:
            raise LedgerIntegrityError("delta record is already promoted")
        if promotion.authorization_scope_id != delta.authorization_scope_id:
            raise LedgerIntegrityError("promotion authorization scope does not match delta")
        self._append_to_log(promotion)
        self._record_ids.add(promotion.record_id)
        self._last_watermark = promotion.input_watermark
        self._promoted.add(promotion.promotes_record_id)
        self._apply_to_projection(delta, +1.0)

    def append_reversal(self, reversal: EventDerivedDeltaReversal) -> None:
        self._check_new_record_id(reversal.record_id)
        self._check_watermark(reversal.input_watermark)
        delta = self._delta_by_id.get(reversal.reverses_record_id)
        if delta is None:
            raise LedgerIntegrityError("reversal targets an unknown delta record")
        if reversal.revision_id != delta.revision_id:
            raise LedgerIntegrityError("reversal revision does not match target delta")
        if reversal.authorization_scope_id != delta.authorization_scope_id:
            raise LedgerIntegrityError("reversal authorization scope does not match delta")
        if reversal.reverses_record_id not in self._promoted:
            raise LedgerIntegrityError("only a promoted delta can be reversed")
        if reversal.reverses_record_id in self._reversed:
            raise LedgerIntegrityError("delta record is already reversed")
        self._append_to_log(reversal)
        self._record_ids.add(reversal.record_id)
        self._last_watermark = reversal.input_watermark
        was_contributing = reversal.reverses_record_id in self._promoted
        self._reversed.add(reversal.reverses_record_id)
        if was_contributing:
            self._apply_to_projection(delta, -1.0)

    # --- ORRER-driven operations --------------------------------------------

    def retract_revision(
        self, *, revision_id: UUID, watermark: int, reason: str, reversal_ids: list[UUID]
    ) -> RetractionCost:
        """RGRC targeted retract: reverse only this revision's live deltas (O(k))."""

        started = time.perf_counter()
        live = [
            record_id
            for record_id in self._by_revision.get(revision_id, [])
            if record_id in self._promoted and record_id not in self._reversed
        ]
        if reversal_ids is not None and len(reversal_ids) != len(live):
            raise LedgerIntegrityError("one reversal record id is required per live delta")
        touched = 0
        for offset, record_id in enumerate(live):
            self.append_reversal(
                EventDerivedDeltaReversal(
                    record_id=reversal_ids[offset],
                    reverses_record_id=record_id,
                    revision_id=revision_id,
                    input_watermark=watermark,
                    reason=reason,
                    authorization_scope_id=self._delta_by_id[record_id].authorization_scope_id,
                )
            )
            touched += 1
        return RetractionCost(
            records_touched=touched, wall_clock_seconds=time.perf_counter() - started
        )

    # --- projections ---------------------------------------------------------

    def owner_projection(
        self, *, actor_key: str, object_instance_id: UUID, parameter_block: str
    ) -> dict[UUID, float]:
        """Cached projection over locations for one (actor, object, block)."""

        return {
            key[3]: value
            for key, value in self._projection.items()
            if key[0] == actor_key
            and key[1] == object_instance_id
            and key[2] == parameter_block
            and abs(value) > 1e-12
        }

    def rebuild_projection_from_log(
        self, *, actor_key: str, object_instance_id: UUID, parameter_block: str
    ) -> tuple[dict[UUID, float], RebuildCost]:
        """Full rerun over the entire log; the cost is every record scanned."""

        started = time.perf_counter()
        reversed_ids: set[UUID] = set()
        promoted_ids: set[UUID] = set()
        deltas: dict[UUID, EventDerivedDeltaRecord] = {}
        scanned = 0
        for record in self._log:
            scanned += 1
            if isinstance(record, EventDerivedDeltaRecord):
                deltas[record.record_id] = record
                if record.initial_state == ConsolidationState.PROMOTED:
                    promoted_ids.add(record.record_id)
            elif isinstance(record, EventDerivedDeltaPromotion):
                promoted_ids.add(record.promotes_record_id)
            else:  # reversal
                reversed_ids.add(record.reverses_record_id)
        counts: dict[UUID, float] = {}
        for record_id, delta in deltas.items():
            live = record_id in promoted_ids and record_id not in reversed_ids
            matches = (
                delta.actor_key == actor_key
                and delta.object_instance_id == object_instance_id
                and delta.parameter_block == parameter_block
            )
            if live and matches:
                counts[delta.location_id] = counts.get(delta.location_id, 0.0) + delta.signed_delta
        counts = {location: value for location, value in counts.items() if abs(value) > 1e-12}
        return counts, RebuildCost(
            records_scanned=scanned, wall_clock_seconds=time.perf_counter() - started
        )

    def verify_full_rerun_equivalence(
        self,
        *,
        actor_key: str,
        object_instance_id: UUID,
        parameter_block: str,
    ) -> FullRerunEquivalenceReceipt:
        """Fail closed unless the online projection exactly equals full replay."""

        cached = self.owner_projection(
            actor_key=actor_key,
            object_instance_id=object_instance_id,
            parameter_block=parameter_block,
        )
        rebuilt, cost = self.rebuild_projection_from_log(
            actor_key=actor_key,
            object_instance_id=object_instance_id,
            parameter_block=parameter_block,
        )
        receipt = FullRerunEquivalenceReceipt(
            actor_key=actor_key,
            object_instance_id=object_instance_id,
            parameter_block=parameter_block,
            cached_projection_sha256=_projection_sha256(cached),
            rebuilt_projection_sha256=_projection_sha256(rebuilt),
            cached_projection=cached,
            rebuilt_projection=rebuilt,
            equivalent=cached == rebuilt,
            records_scanned=cost.records_scanned,
            rebuild_wall_clock_seconds=cost.wall_clock_seconds,
        )
        if not receipt.equivalent:
            raise LedgerIntegrityError(
                "RGRC incremental projection diverged from full append-log replay"
            )
        return receipt

    def record_count(self) -> int:
        return len(self._log)

    def state_of(self, record_id: UUID) -> ConsolidationState:
        """Return the derived state of one delta; corrected revisions are reactivated."""

        delta = self._delta_by_id.get(record_id)
        if delta is None:
            raise LedgerIntegrityError("unknown delta record")
        if record_id in self._reversed:
            return ConsolidationState.RETRACTED
        if record_id in self._promoted:
            if delta.parent_revision_id is not None:
                return ConsolidationState.REACTIVATED
            return ConsolidationState.PROMOTED
        return ConsolidationState.QUARANTINED

    # --- serialize / restart / replay ---------------------------------------

    def to_jsonl(self) -> str:
        lines = []
        previous_hash = "0" * 64
        for record in self._log:
            kind = type(record).__name__
            record_payload = record.model_dump(mode="json")
            entry_hash = self._entry_hash(previous_hash, kind, record_payload)
            lines.append(
                json.dumps(
                    {
                        "kind": kind,
                        "record": record_payload,
                        "previous_hash": previous_hash,
                        "entry_hash": entry_hash,
                    },
                    sort_keys=True,
                )
            )
            previous_hash = entry_hash
        return "\n".join(lines)

    @classmethod
    def from_jsonl(cls, text: str) -> EventDerivedUpdateLedger:
        ledger = cls()
        for line in text.splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if payload.get("previous_hash") != ledger._head_hash:
                raise LedgerIntegrityError("JSONL hash chain previous_hash mismatch")
            expected_hash = ledger._entry_hash(
                ledger._head_hash,
                payload["kind"],
                payload["record"],
            )
            if payload.get("entry_hash") != expected_hash:
                raise LedgerIntegrityError("JSONL hash chain entry_hash mismatch")
            kind = payload["kind"]
            record_payload = payload["record"]
            if kind == "EventDerivedDeltaRecord":
                ledger.append_delta(EventDerivedDeltaRecord.model_validate(record_payload))
            elif kind == "EventDerivedDeltaReversal":
                ledger.append_reversal(EventDerivedDeltaReversal.model_validate(record_payload))
            elif kind == "EventDerivedDeltaPromotion":
                ledger.append_promotion(EventDerivedDeltaPromotion.model_validate(record_payload))
            else:
                raise LedgerIntegrityError(f"unknown ledger entry kind: {kind!r}")
            if ledger._head_hash != expected_hash:
                raise LedgerIntegrityError("replayed hash chain diverged")
        return ledger

    # --- internals -----------------------------------------------------------

    def _check_new_record_id(self, record_id: UUID) -> None:
        if record_id in self._record_ids:
            raise LedgerIntegrityError(f"record id {record_id} already appended")

    def _check_watermark(self, watermark: int) -> None:
        if watermark < self._last_watermark:
            raise LedgerIntegrityError(
                f"input_watermark {watermark} is behind the ledger head {self._last_watermark}"
            )

    def _validate_revision(self, delta: EventDerivedDeltaRecord) -> None:
        known_event = self._revision_event.get(delta.revision_id)
        if known_event is not None:
            if known_event != delta.event_hypothesis_id:
                raise LedgerIntegrityError("revision id cannot span multiple events")
            if self._revision_parent[delta.revision_id] != delta.parent_revision_id:
                raise LedgerIntegrityError("revision parent must be stable")
            return
        parent = delta.parent_revision_id
        if parent is not None:
            parent_event = self._revision_event.get(parent)
            if parent_event is None:
                raise LedgerIntegrityError("parent revision does not exist")
            if parent_event != delta.event_hypothesis_id:
                raise LedgerIntegrityError("parent revision belongs to another event")
            parent_records = self._by_revision.get(parent, ())
            if any(record_id not in self._reversed for record_id in parent_records):
                raise LedgerIntegrityError("parent revision must be fully retracted")
        self._revision_event[delta.revision_id] = delta.event_hypothesis_id
        self._revision_parent[delta.revision_id] = parent

    def _append_to_log(
        self,
        record: EventDerivedDeltaRecord | EventDerivedDeltaReversal | EventDerivedDeltaPromotion,
    ) -> None:
        kind = type(record).__name__
        payload = record.model_dump(mode="json")
        self._head_hash = self._entry_hash(self._head_hash, kind, payload)
        self._log.append(record)

    @staticmethod
    def _entry_hash(previous_hash: str, kind: str, payload: Mapping[str, object]) -> str:
        canonical = json.dumps(
            {"previous_hash": previous_hash, "kind": kind, "record": payload},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _apply_to_projection(self, delta: EventDerivedDeltaRecord, sign: float) -> None:
        key = delta.projection_key
        updated = self._projection.get(key, 0.0) + sign * delta.signed_delta
        if abs(updated) < 1e-12:
            self._projection.pop(key, None)
        else:
            self._projection[key] = updated


def projection_total_variation(left: Mapping[UUID, float], right: Mapping[UUID, float]) -> float:
    """Total-variation distance between two location soft-count distributions.

    Robust to multi-location habits: it measures how far one projection is from a
    reference (e.g. the corrected projection), not "any non-home mass".
    """

    left_total = sum(left.values())
    right_total = sum(right.values())
    left_norm = {k: v / left_total for k, v in left.items()} if left_total > 0 else {}
    right_norm = {k: v / right_total for k, v in right.items()} if right_total > 0 else {}
    support = set(left_norm) | set(right_norm)
    return 0.5 * sum(abs(left_norm.get(k, 0.0) - right_norm.get(k, 0.0)) for k in support)
