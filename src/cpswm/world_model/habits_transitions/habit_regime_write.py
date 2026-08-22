"""Cause-gated write path into a real long-term habit parameter store.

Measure 2 (review 2026-08-21): the gate must actually control a long-term model
update and persist an audit trail, and it must be provable -- via before/after
parameter hashes -- that an observation, actor, or noise change leaves the habit
parameters byte-identical.  This module is that write path.

A :class:`GatedHabitRegimeWriter` takes a proposed habit update and a
:class:`JointCauseSnapshot`, asks :class:`CauseGatedHabitConsolidation` whether
the habit block is open, and either applies the update (scaled by the gate's
consolidation weight) or rejects it.  Every attempt appends a
:class:`ParameterWriteAudit` recording the proposed update, attributed cause,
writable blocks, applied weight, before/after hashes, and the accept/reject
rationale.  A rejected write that changed the hash is a hard error.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from cpswm.contracts.habit_learning import (
    HabitLearningEvidence,
    ObservationOpportunityRecord,
)

from .cause_factorized_bocpd import ChangeCause
from .cause_gated_consolidation import CauseGatedHabitConsolidation
from .hierarchical_dirichlet import HierarchicalDirichletHabitModel
from .joint_cause_bocpd import JointCauseSnapshot
from .propensity_correction import ObservationPropensityCorrector


def _hash_parameters(values: Mapping[str, float]) -> str:
    # repr keeps full float precision so the hash is exact, not rounded.
    payload = json.dumps({key: repr(values[key]) for key in sorted(values)}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class HabitRegimeParameters:
    """The protected long-term habit parameters (an immutable value)."""

    values: Mapping[str, float]

    def parameter_hash(self) -> str:
        return _hash_parameters(self.values)

    def apply(self, update: Mapping[str, float], weight: float) -> HabitRegimeParameters:
        merged = dict(self.values)
        for key, delta in update.items():
            merged[key] = merged.get(key, 0.0) + weight * delta
        return HabitRegimeParameters(merged)


@dataclass(frozen=True, slots=True)
class ParameterWriteAudit:
    """One persisted write attempt against the long-term habit parameters."""

    proposed_update: Mapping[str, float]
    attributed_cause: ChangeCause | None
    writable_blocks: tuple[ChangeCause, ...]
    applied_weight: float
    before_hash: str
    after_hash: str
    accepted: bool
    rationale: str

    @property
    def parameters_changed(self) -> bool:
        return self.before_hash != self.after_hash


class GatedHabitRegimeWriter:
    """Apply habit-parameter writes only when the cause posterior opens them."""

    def __init__(self, gate: CauseGatedHabitConsolidation | None = None) -> None:
        self._gate = gate or CauseGatedHabitConsolidation()
        self._audit_log: list[ParameterWriteAudit] = []

    @property
    def audit_log(self) -> tuple[ParameterWriteAudit, ...]:
        return tuple(self._audit_log)

    def propose_habit_update(
        self,
        parameters: HabitRegimeParameters,
        snapshot: JointCauseSnapshot,
        proposed_update: Mapping[str, float],
    ) -> tuple[HabitRegimeParameters, ParameterWriteAudit]:
        decision = self._gate.decide(snapshot)
        before_hash = parameters.parameter_hash()
        if decision.habit_block_writable:
            weight = self._gate.habit_consolidation_weight(snapshot)
            updated = parameters.apply(proposed_update, weight)
            accepted = True
            rationale = f"accepted: change attributed to habit (weight={weight:.6f})"
        else:
            weight = 0.0
            updated = parameters
            accepted = False
            rationale = f"rejected: {decision.rationale}"
        after_hash = updated.parameter_hash()
        if not accepted and after_hash != before_hash:
            raise RuntimeError("a rejected habit write must leave parameters byte-identical")
        audit = ParameterWriteAudit(
            proposed_update=dict(proposed_update),
            attributed_cause=decision.attributed_cause,
            writable_blocks=tuple(sorted(decision.writable_blocks, key=lambda cause: cause.value)),
            applied_weight=weight,
            before_hash=before_hash,
            after_hash=after_hash,
            accepted=accepted,
            rationale=rationale,
        )
        self._audit_log.append(audit)
        return updated, audit


# --- Fix 3/4: real model target + canonical persistent log --------------------


@dataclass(frozen=True, slots=True)
class CanonicalLogEntry:
    sequence: int
    previous_hash: str
    payload: Mapping[str, object]
    entry_hash: str


class CanonicalWriteLog:
    """Append-only, hash-chained audit log; optionally persisted to JSONL.

    Each entry hashes the previous entry's hash together with its payload, so
    the log is tamper-evident: rewriting any entry breaks every later hash.
    """

    _GENESIS = "0" * 64

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._entries: list[CanonicalLogEntry] = []
        if path is not None and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                self._entries.append(
                    CanonicalLogEntry(
                        sequence=record["sequence"],
                        previous_hash=record["previous_hash"],
                        payload=record["payload"],
                        entry_hash=record["entry_hash"],
                    )
                )
            # Precondition 4: a persistent log that fails verification must not
            # be silently trusted -- refuse to load a tampered or corrupt chain.
            if not self.verify_chain():
                raise RuntimeError(f"canonical write log at {path} failed chain verification")

    @property
    def head_hash(self) -> str:
        return self._entries[-1].entry_hash if self._entries else self._GENESIS

    def append(self, payload: Mapping[str, object]) -> CanonicalLogEntry:
        previous = self.head_hash
        sequence = len(self._entries)
        canonical = json.dumps(
            {"sequence": sequence, "previous_hash": previous, "payload": payload},
            sort_keys=True,
        )
        entry_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        entry = CanonicalLogEntry(sequence, previous, dict(payload), entry_hash)
        self._entries.append(entry)
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "sequence": sequence,
                            "previous_hash": previous,
                            "payload": payload,
                            "entry_hash": entry_hash,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
        return entry

    def entries(self) -> tuple[CanonicalLogEntry, ...]:
        return tuple(self._entries)

    def verify_chain(self) -> bool:
        previous = self._GENESIS
        for entry in self._entries:
            canonical = json.dumps(
                {
                    "sequence": entry.sequence,
                    "previous_hash": entry.previous_hash,
                    "payload": entry.payload,
                },
                sort_keys=True,
            )
            expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if entry.previous_hash != previous or entry.entry_hash != expected:
                return False
            previous = entry.entry_hash
        return True


CONSOLIDATOR_VERSION = "gated-hd-consolidator@0.2"


class GatedHierarchicalDirichletConsolidator:
    """Gate real M17 habit-count writes on the joint CF-BOCPD cause posterior.

    Hardened for the B preconditions (review 2026-08-22):

    * **Full-state hash** (P3): the canonical hash is the model's whole learned
      count state, not a probe grid, so it detects any parameter change.
    * **Observation-opportunity binding** (P2): a write requires the corrected
      opportunity the evidence cites; the propensity weight multiplies the gate
      weight, restoring the F0 source binding.
    * **Evidence de-duplication** (P1): the same evidence record is applied at
      most once, even if several snapshots open the habit block.
    * **Rich audit** (P5): each log entry carries evidence, snapshot, posterior,
      and version fields.

    A rejected (or duplicate) consolidation never calls ``model.update``; if the
    full-state hash changed anyway it is a hard error.
    """

    def __init__(
        self,
        model: HierarchicalDirichletHabitModel,
        *,
        gate: CauseGatedHabitConsolidation | None = None,
        propensity_corrector: ObservationPropensityCorrector,
        canonical_log: CanonicalWriteLog | None = None,
    ) -> None:
        self._model = model
        self._gate = gate or CauseGatedHabitConsolidation()
        self._corrector = propensity_corrector
        self._log = canonical_log or CanonicalWriteLog()
        self._applied_evidence: set[UUID] = set()

    @property
    def canonical_log(self) -> CanonicalWriteLog:
        return self._log

    def canonical_parameter_hash(self) -> str:
        return self._model.canonical_state_hash()

    def propose_consolidation(
        self,
        snapshot: JointCauseSnapshot,
        evidence: HabitLearningEvidence,
        opportunity: ObservationOpportunityRecord,
    ) -> ParameterWriteAudit:
        # P2: the evidence must cite the exact opportunity, which must have been
        # selected and share the household/session/trace, before any write.
        self._require_opportunity_binding(evidence, opportunity)
        decision = self._gate.decide(snapshot)
        record_id = evidence.metadata.record_id
        duplicate = record_id in self._applied_evidence
        before_hash = self.canonical_parameter_hash()

        if decision.habit_block_writable and not duplicate:
            gate_weight = self._gate.habit_consolidation_weight(snapshot)
            propensity = self._corrector.weight_for_opportunity(opportunity).applied_weight
            weight = gate_weight * propensity
            self._model.update(evidence, weight_multiplier=weight)
            self._applied_evidence.add(record_id)
            accepted = True
            rationale = f"accepted: habit regime write into M17 counts (weight={weight:.6f})"
        else:
            weight = 0.0
            accepted = False
            if duplicate:
                rationale = "rejected: evidence already consolidated (duplicate write prevented)"
            else:
                rationale = f"rejected: {decision.rationale}"
        after_hash = self.canonical_parameter_hash()
        if not accepted and after_hash != before_hash:
            raise RuntimeError("a rejected consolidation must leave the M17 model hash unchanged")

        audit = ParameterWriteAudit(
            proposed_update={
                "object_instance_id": str(evidence.object_instance_id),
                "location_id": str(evidence.location_id),
            },
            attributed_cause=decision.attributed_cause,
            writable_blocks=tuple(sorted(decision.writable_blocks, key=lambda cause: cause.value)),
            applied_weight=weight,
            before_hash=before_hash,
            after_hash=after_hash,
            accepted=accepted,
            rationale=rationale,
        )
        self._log.append(
            {
                "accepted": accepted,
                "duplicate": duplicate,
                "applied_weight": weight,
                "before_hash": before_hash,
                "after_hash": after_hash,
                "rationale": rationale,
                # P5: evidence provenance.
                "evidence": {
                    "record_id": str(record_id),
                    "object_instance_id": str(evidence.object_instance_id),
                    "location_id": str(evidence.location_id),
                    "observation_opportunity_id": str(evidence.observation_opportunity_id)
                    if evidence.observation_opportunity_id
                    else None,
                    "source_record_ids": [str(item) for item in evidence.source_record_ids],
                    "evidence_source": evidence.evidence_source.value,
                },
                # P5: snapshot and posterior.
                "snapshot": {
                    "timestamp": snapshot.timestamp.isoformat(),
                    "segment_change_probability": repr(snapshot.segment_change_probability),
                    "transient_noise_probability": repr(snapshot.transient_noise_probability),
                },
                "posterior": {
                    "attributed_cause": decision.attributed_cause.value
                    if decision.attributed_cause
                    else None,
                    "segment_cause_posterior": {
                        cause.value: repr(value)
                        for cause, value in sorted(
                            snapshot.segment_cause_posterior.items(),
                            key=lambda item: item[0].value,
                        )
                    },
                },
                # P5: versions.
                "version": {
                    "consolidator": CONSOLIDATOR_VERSION,
                    "model": self._model.model_version,
                    "opportunity_likelihood_model": opportunity.likelihood_model_id,
                },
            }
        )
        return audit

    @staticmethod
    def _require_opportunity_binding(
        evidence: HabitLearningEvidence, opportunity: ObservationOpportunityRecord
    ) -> None:
        if evidence.observation_opportunity_id != opportunity.metadata.record_id:
            raise ValueError("habit evidence must cite the corrected observation opportunity")
        for field_name in ("household_id", "session_id", "trace_id"):
            if getattr(evidence.metadata, field_name) != getattr(opportunity.metadata, field_name):
                raise ValueError(
                    f"habit evidence {field_name} does not match observation opportunity"
                )
        if not opportunity.selected:
            raise ValueError("an unselected opportunity cannot produce a habit consolidation")
