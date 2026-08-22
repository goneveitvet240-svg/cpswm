"""Source-bound reversible sufficient statistics for structure-two scheme B.

The store keeps additive natural statistics instead of raw observations:

* ``A`` and ``b`` for ridge/RLS contextual residuals;
* ``alpha`` for a Dirichlet location base;
* ``information`` and ``information_vector`` (Lambda/xi) for Gaussian beliefs.

Every contribution is bound to one evidence cluster and one event revision.  A
quarantined contribution can be promoted once; a promoted contribution can be
retracted once; a corrected revision must point to a fully retracted revision
of the same event.  Cached projections are checked against replayable log state.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from typing import TypeAlias
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

Matrix: TypeAlias = NDArray[np.float64]  # noqa: UP040 - keep Python 3.11 compatibility
Vector: TypeAlias = NDArray[np.float64]  # noqa: UP040 - keep Python 3.11 compatibility
ArrayLike: TypeAlias = (  # noqa: UP040 - keep Python 3.11 compatibility
    Vector | list[float] | tuple[float, ...]
)


class HybridLedgerError(RuntimeError):
    """Raised when a write violates scheme-B provenance or state invariants."""


class HybridConsolidationState(StrEnum):
    QUARANTINED = "quarantined"
    PROMOTED = "promoted"
    RETRACTED = "retracted"
    REACTIVATED = "reactivated"


@dataclass(frozen=True, slots=True, order=True)
class StatisticKey:
    """One independently projected map/habit statistic block."""

    actor_key: str
    object_instance_id: UUID
    regime_id: str
    parameter_block: str
    location_id: UUID

    def __post_init__(self) -> None:
        for name in ("actor_key", "regime_id", "parameter_block"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")


def _immutable_vector(value: ArrayLike, *, dim: int, name: str) -> Vector:
    array: Vector = np.asarray(value, dtype=float).copy()
    if array.shape != (dim,):
        raise ValueError(f"{name} must have shape ({dim},)")
    if np.any(~np.isfinite(array)):
        raise ValueError(f"{name} must be finite")
    array.setflags(write=False)
    return array


def _immutable_psd_matrix(value: Matrix, *, dim: int, name: str) -> Matrix:
    array = np.asarray(value, dtype=float).copy()
    if array.shape != (dim, dim):
        raise ValueError(f"{name} must have shape ({dim}, {dim})")
    if np.any(~np.isfinite(array)):
        raise ValueError(f"{name} must be finite")
    array = 0.5 * (array + array.T)
    if float(np.linalg.eigvalsh(array).min()) < -1e-10:
        raise ValueError(f"{name} must be positive semidefinite")
    array.setflags(write=False)
    return array


@dataclass(frozen=True, slots=True)
class HybridStatisticDelta:
    """One immutable, evidence-cluster-bound additive sufficient-statistic delta."""

    record_id: UUID
    event_hypothesis_id: UUID
    revision_id: UUID
    evidence_cluster_id: UUID
    semantic_dedup_id: str
    source_record_ids: tuple[UUID, ...]
    authorization_scope_id: UUID
    key: StatisticKey
    delta_a: Matrix
    delta_b: Vector
    delta_alpha: float
    delta_information: Matrix
    delta_information_vector: Vector
    input_watermark: int
    model_version: str
    code_version: str
    parent_revision_id: UUID | None = None
    initial_state: HybridConsolidationState = HybridConsolidationState.QUARANTINED
    content_hash: str = ""
    _feature_dim: int = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        matrix = np.asarray(self.delta_a, dtype=float)
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] == 0:
            raise ValueError("delta_a must be a non-empty square matrix")
        dim = int(matrix.shape[0])
        object.__setattr__(self, "_feature_dim", dim)
        object.__setattr__(self, "delta_a", _immutable_psd_matrix(matrix, dim=dim, name="delta_a"))
        object.__setattr__(
            self, "delta_b", _immutable_vector(self.delta_b, dim=dim, name="delta_b")
        )
        object.__setattr__(
            self,
            "delta_information",
            _immutable_psd_matrix(
                self.delta_information,
                dim=dim,
                name="delta_information",
            ),
        )
        object.__setattr__(
            self,
            "delta_information_vector",
            _immutable_vector(
                self.delta_information_vector,
                dim=dim,
                name="delta_information_vector",
            ),
        )
        if not isfinite(self.delta_alpha) or self.delta_alpha < 0.0:
            raise ValueError("delta_alpha must be finite and non-negative")
        if self.input_watermark < 0:
            raise ValueError("input_watermark must be non-negative")
        if not self.semantic_dedup_id.strip():
            raise ValueError("semantic_dedup_id must be non-empty")
        if not self.source_record_ids:
            raise ValueError("source_record_ids must be non-empty")
        if len(set(self.source_record_ids)) != len(self.source_record_ids):
            raise ValueError("source_record_ids must be unique")
        if not self.model_version.strip() or not self.code_version.strip():
            raise ValueError("model_version and code_version must be non-empty")
        if self.initial_state not in {
            HybridConsolidationState.QUARANTINED,
            HybridConsolidationState.PROMOTED,
        }:
            raise ValueError("a delta may only start quarantined or promoted")
        expected = self.compute_hash()
        if self.content_hash and self.content_hash != expected:
            raise ValueError("content_hash does not match sufficient-statistic delta")
        object.__setattr__(self, "content_hash", expected)

    @property
    def feature_dim(self) -> int:
        return self._feature_dim

    def compute_hash(self) -> str:
        payload = {
            "record_id": str(self.record_id),
            "event_hypothesis_id": str(self.event_hypothesis_id),
            "revision_id": str(self.revision_id),
            "parent_revision_id": (
                str(self.parent_revision_id) if self.parent_revision_id is not None else None
            ),
            "evidence_cluster_id": str(self.evidence_cluster_id),
            "semantic_dedup_id": self.semantic_dedup_id,
            "source_record_ids": [str(value) for value in self.source_record_ids],
            "authorization_scope_id": str(self.authorization_scope_id),
            "key": {
                "actor_key": self.key.actor_key,
                "object_instance_id": str(self.key.object_instance_id),
                "regime_id": self.key.regime_id,
                "parameter_block": self.key.parameter_block,
                "location_id": str(self.key.location_id),
            },
            "delta_a": np.asarray(self.delta_a, dtype=float).tolist(),
            "delta_b": np.asarray(self.delta_b, dtype=float).tolist(),
            "delta_alpha": repr(float(self.delta_alpha)),
            "delta_information": np.asarray(self.delta_information, dtype=float).tolist(),
            "delta_information_vector": np.asarray(
                self.delta_information_vector, dtype=float
            ).tolist(),
            "input_watermark": self.input_watermark,
            "model_version": self.model_version,
            "code_version": self.code_version,
            "initial_state": self.initial_state.value,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def from_weighted_sample(
        cls,
        *,
        x: ArrayLike,
        y: float,
        weight: float,
        delta_alpha: float,
        record_id: UUID,
        event_hypothesis_id: UUID,
        revision_id: UUID,
        evidence_cluster_id: UUID,
        semantic_dedup_id: str,
        source_record_ids: tuple[UUID, ...],
        authorization_scope_id: UUID,
        key: StatisticKey,
        input_watermark: int,
        model_version: str,
        code_version: str,
        information_x: ArrayLike | None = None,
        information_weight: float = 0.0,
        parent_revision_id: UUID | None = None,
        initial_state: HybridConsolidationState = HybridConsolidationState.QUARANTINED,
    ) -> HybridStatisticDelta:
        """Create an additive delta without retaining the raw sample in the store."""

        vector: Vector = np.asarray(x, dtype=float)
        if vector.ndim != 1 or vector.size == 0 or np.any(~np.isfinite(vector)):
            raise ValueError("x must be a finite non-empty vector")
        target = float(y)
        sample_weight = float(weight)
        info_weight = float(information_weight)
        if not isfinite(target):
            raise ValueError("y must be finite")
        if not isfinite(sample_weight) or sample_weight < 0.0:
            raise ValueError("weight must be finite and non-negative")
        if not isfinite(info_weight) or info_weight < 0.0:
            raise ValueError("information_weight must be finite and non-negative")
        info_x = vector if information_x is None else np.asarray(information_x, dtype=float)
        if info_x.shape != vector.shape or np.any(~np.isfinite(info_x)):
            raise ValueError("information_x must match x and be finite")
        return cls(
            record_id=record_id,
            event_hypothesis_id=event_hypothesis_id,
            revision_id=revision_id,
            parent_revision_id=parent_revision_id,
            evidence_cluster_id=evidence_cluster_id,
            semantic_dedup_id=semantic_dedup_id,
            source_record_ids=source_record_ids,
            authorization_scope_id=authorization_scope_id,
            key=key,
            delta_a=sample_weight * np.outer(vector, vector),
            delta_b=sample_weight * vector * target,
            delta_alpha=delta_alpha,
            delta_information=info_weight * np.outer(info_x, info_x),
            delta_information_vector=info_weight * info_x * target,
            input_watermark=input_watermark,
            model_version=model_version,
            code_version=code_version,
            initial_state=initial_state,
        )


@dataclass(frozen=True, slots=True)
class ConsolidationRiskCertificate:
    """B-P3/B-L3 exact counterfactual risk result authorizing promotion."""

    expected_task_loss: float
    uncertainty_penalty: float
    maximum_allowed_risk: float
    exact_verifier_id: str
    counterfactual_id: UUID
    subject_delta_record_id: UUID
    belief_snapshot_id: UUID
    map_version: int
    hard_safety_violations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        values = (
            self.expected_task_loss,
            self.uncertainty_penalty,
            self.maximum_allowed_risk,
        )
        if any(not isfinite(value) or value < 0.0 for value in values):
            raise ValueError("risk values must be finite and non-negative")
        if not self.exact_verifier_id.strip():
            raise ValueError("exact_verifier_id must be non-empty")
        if self.map_version < 0:
            raise ValueError("map_version must be non-negative")

    @property
    def total_risk(self) -> float:
        return self.expected_task_loss + self.uncertainty_penalty

    @property
    def allows_promotion(self) -> bool:
        return not self.hard_safety_violations and self.total_risk <= self.maximum_allowed_risk


@dataclass(frozen=True, slots=True)
class HybridPromotion:
    record_id: UUID
    promotes_record_id: UUID
    input_watermark: int
    authorization_scope_id: UUID
    reason: str
    risk_certificate: ConsolidationRiskCertificate


@dataclass(frozen=True, slots=True)
class HybridReversal:
    record_id: UUID
    reverses_record_id: UUID
    revision_id: UUID
    input_watermark: int
    authorization_scope_id: UUID
    reason: str


@dataclass(frozen=True, slots=True)
class HybridQuarantineSupersession:
    """Retire an unresolved quarantined revision in favor of a named revision."""

    record_id: UUID
    supersedes_revision_id: UUID
    successor_revision_id: UUID
    event_hypothesis_id: UUID
    input_watermark: int
    authorization_scope_id: UUID
    reason: str


HybridLogRecord: TypeAlias = (  # noqa: UP040 - keep Python 3.11 compatibility
    HybridStatisticDelta | HybridPromotion | HybridReversal | HybridQuarantineSupersession
)


@dataclass(frozen=True, slots=True)
class HybridProjection:
    """Immutable copy of the sufficient statistics at one ledger version."""

    a: Matrix
    b: Vector
    alpha: float
    information: Matrix
    information_vector: Vector
    theta: Vector
    ledger_version: int
    replay_required: bool
    condition_number: float


@dataclass(frozen=True, slots=True)
class FusedLocationBelief:
    """Auditable B-F1 Dirichlet base plus contextual RLS residual."""

    base_probability: float
    contextual_residual: float
    fused_probability: float
    ledger_version: int
    excluded_evidence_cluster_id: UUID | None


@dataclass(slots=True)
class _MutableProjection:
    a: Matrix
    b: Vector
    alpha: float
    information: Matrix
    information_vector: Vector


class HybridStatisticLedger:
    """Thread-safe, append-only scheme-B statistic ledger and projection cache."""

    def __init__(
        self,
        *,
        feature_dim: int,
        ridge: float = 1e-6,
        information_ridge: float = 1e-6,
        alpha_prior: float = 0.0,
        max_condition_number: float = 1e12,
    ) -> None:
        if feature_dim <= 0:
            raise ValueError("feature_dim must be positive")
        if ridge <= 0.0 or information_ridge <= 0.0:
            raise ValueError("ridge priors must be positive")
        if alpha_prior < 0.0:
            raise ValueError("alpha_prior must be non-negative")
        if max_condition_number <= 1.0:
            raise ValueError("max_condition_number must be greater than one")
        self.feature_dim = feature_dim
        self.ridge = float(ridge)
        self.information_ridge = float(information_ridge)
        self.alpha_prior = float(alpha_prior)
        self.max_condition_number = float(max_condition_number)
        self._lock = threading.RLock()
        self._log: list[HybridLogRecord] = []
        self._deltas: dict[UUID, HybridStatisticDelta] = {}
        self._record_ids: set[UUID] = set()
        self._cluster_keys: set[tuple[UUID, StatisticKey]] = set()
        self._cluster_records: dict[UUID, list[UUID]] = {}
        self._cluster_identity: dict[
            UUID,
            tuple[UUID, UUID, UUID, tuple[UUID, ...]],
        ] = {}
        self._dedup_ids: set[str] = set()
        self._promoted: set[UUID] = set()
        self._reversed: set[UUID] = set()
        self._by_revision: dict[UUID, list[UUID]] = {}
        self._revision_event: dict[UUID, UUID] = {}
        self._revision_parent: dict[UUID, UUID | None] = {}
        self._quarantine_successor: dict[UUID, UUID] = {}
        self._projection: dict[StatisticKey, _MutableProjection] = {}
        self._last_watermark = -1

    @property
    def version(self) -> int:
        with self._lock:
            return len(self._log)

    @property
    def head_watermark(self) -> int:
        """The highest input watermark accepted so far (``-1`` when empty).

        A caller that restarts against a recovered ledger must derive its next
        watermark from here rather than from its own in-memory counter, or its
        first write will be rejected as ``input watermark is behind the head``.
        """

        with self._lock:
            return self._last_watermark

    def revision_ids(self) -> tuple[UUID, ...]:
        """Every revision id that has at least one delta in the authoritative log."""

        with self._lock:
            return tuple(self._by_revision)

    def records_for_revision(self, revision_id: UUID) -> tuple[UUID, ...]:
        """All delta record ids appended under one revision (append order)."""

        with self._lock:
            return tuple(self._by_revision.get(revision_id, ()))

    def live_promoted_records_for_revision(self, revision_id: UUID) -> tuple[UUID, ...]:
        """The promoted, not-yet-retracted delta records of one revision.

        This is the exact set :meth:`retract_revision` will reverse; a caller
        sizes its reversal record ids from here instead of shadowing the log.
        """

        with self._lock:
            return tuple(
                record_id
                for record_id in self._by_revision.get(revision_id, ())
                if record_id in self._promoted and record_id not in self._reversed
            )

    def location_ids_for_revision(self, revision_id: UUID) -> frozenset[UUID]:
        """The statistic-key locations one revision touched (for map republish)."""

        with self._lock:
            return frozenset(
                self._deltas[record_id].key.location_id
                for record_id in self._by_revision.get(revision_id, ())
            )

    def delta(self, record_id: UUID) -> HybridStatisticDelta:
        """Return one immutable stored delta (its arrays are read-only)."""

        with self._lock:
            delta = self._deltas.get(record_id)
            if delta is None:
                raise HybridLedgerError("unknown delta record")
            return delta

    def export_log(self) -> tuple[HybridLogRecord, ...]:
        """Serialize the authoritative append-only log (records are immutable)."""

        with self._lock:
            return tuple(self._log)

    @classmethod
    def restore_from_log(
        cls,
        *,
        feature_dim: int,
        log: tuple[HybridLogRecord, ...],
        ridge: float = 1e-6,
        information_ridge: float = 1e-6,
        alpha_prior: float = 0.0,
        max_condition_number: float = 1e12,
    ) -> HybridStatisticLedger:
        """Rebuild a ledger by replaying an exported log through full validation.

        Recovery re-runs every invariant (dedup, revision lineage, promote/retract
        state machine), so a tampered or truncated log cannot silently restore a
        state the write path would have refused.  Multi-key cluster promotions are
        contiguous in the log and are replayed atomically via ``promote_cluster``.
        """

        ledger = cls(
            feature_dim=feature_dim,
            ridge=ridge,
            information_ridge=information_ridge,
            alpha_prior=alpha_prior,
            max_condition_number=max_condition_number,
        )
        records = list(log)
        index = 0
        while index < len(records):
            record = records[index]
            if isinstance(record, HybridStatisticDelta):
                ledger.append_delta(record)
                index += 1
            elif isinstance(record, HybridPromotion):
                delta = ledger._deltas.get(record.promotes_record_id)
                if delta is None:
                    raise HybridLedgerError("promotion in log targets an unknown delta")
                cluster_size = len(ledger._cluster_records[delta.evidence_cluster_id])
                if cluster_size == 1:
                    ledger.promote(record)
                    index += 1
                else:
                    group = records[index : index + cluster_size]
                    if len(group) != cluster_size or not all(
                        isinstance(item, HybridPromotion) for item in group
                    ):
                        raise HybridLedgerError("cluster promotions must be contiguous in the log")
                    ledger.promote_cluster(
                        evidence_cluster_id=delta.evidence_cluster_id,
                        promotions=tuple(group),  # type: ignore[arg-type]
                    )
                    index += cluster_size
            elif isinstance(record, HybridReversal):
                ledger.retract(record)
                index += 1
            elif isinstance(record, HybridQuarantineSupersession):
                ledger.supersede_quarantined_revision(record)
                index += 1
            else:  # pragma: no cover - exhaustive over HybridLogRecord
                raise HybridLedgerError("unknown log record type")
        return ledger

    def append_delta(self, delta: HybridStatisticDelta) -> None:
        with self._lock:
            self._check_header(delta.record_id, delta.input_watermark)
            if delta.feature_dim != self.feature_dim:
                raise HybridLedgerError("delta feature dimension does not match ledger")
            cluster_key = (delta.evidence_cluster_id, delta.key)
            if cluster_key in self._cluster_keys:
                raise HybridLedgerError("duplicate evidence_cluster_id and statistic key")
            if delta.semantic_dedup_id in self._dedup_ids:
                raise HybridLedgerError("duplicate semantic_dedup_id")
            cluster_identity = (
                delta.event_hypothesis_id,
                delta.revision_id,
                delta.authorization_scope_id,
                delta.source_record_ids,
            )
            previous_identity = self._cluster_identity.get(delta.evidence_cluster_id)
            if previous_identity is not None and previous_identity != cluster_identity:
                raise HybridLedgerError("evidence cluster identity is inconsistent")
            previous_records = self._cluster_records.get(delta.evidence_cluster_id, ())
            if previous_records and (
                delta.initial_state != HybridConsolidationState.QUARANTINED
                or any(
                    record_id in self._promoted or record_id in self._reversed
                    for record_id in previous_records
                )
            ):
                raise HybridLedgerError(
                    "a multi-key evidence cluster must be assembled while quarantined"
                )
            self._validate_revision(delta)
            self._log.append(delta)
            self._record_ids.add(delta.record_id)
            self._cluster_keys.add(cluster_key)
            self._cluster_records.setdefault(delta.evidence_cluster_id, []).append(delta.record_id)
            self._cluster_identity.setdefault(delta.evidence_cluster_id, cluster_identity)
            self._dedup_ids.add(delta.semantic_dedup_id)
            self._deltas[delta.record_id] = delta
            self._by_revision.setdefault(delta.revision_id, []).append(delta.record_id)
            self._last_watermark = delta.input_watermark
            if delta.initial_state == HybridConsolidationState.PROMOTED:
                self._promoted.add(delta.record_id)
                self._apply(delta, +1.0)

    def promote(self, promotion: HybridPromotion) -> None:
        with self._lock:
            delta = self._deltas.get(promotion.promotes_record_id)
            if delta is None:
                raise HybridLedgerError("promotion targets an unknown delta")
            if len(self._cluster_records[delta.evidence_cluster_id]) != 1:
                raise HybridLedgerError(
                    "multi-key evidence clusters require atomic promote_cluster"
                )
            self._validate_promotion(promotion, delta)
            self._commit_promotion(promotion, delta)

    def promote_cluster(
        self,
        *,
        evidence_cluster_id: UUID,
        promotions: tuple[HybridPromotion, ...],
    ) -> None:
        """Atomically promote every key-delta in one evidence cluster."""

        with self._lock:
            record_ids = tuple(self._cluster_records.get(evidence_cluster_id, ()))
            if not record_ids:
                raise HybridLedgerError("unknown evidence cluster")
            targets = tuple(promotion.promotes_record_id for promotion in promotions)
            if len(targets) != len(set(targets)) or set(targets) != set(record_ids):
                raise HybridLedgerError("promotions must cover the evidence cluster exactly once")
            promotion_ids = [promotion.record_id for promotion in promotions]
            if len(promotion_ids) != len(set(promotion_ids)):
                raise HybridLedgerError("promotion record ids must be unique")
            watermarks = [promotion.input_watermark for promotion in promotions]
            if watermarks != sorted(watermarks):
                raise HybridLedgerError("cluster promotion watermarks must be ordered")
            for promotion in promotions:
                delta = self._deltas[promotion.promotes_record_id]
                self._validate_promotion(promotion, delta)
            for promotion in promotions:
                self._commit_promotion(promotion, self._deltas[promotion.promotes_record_id])

    def retract(self, reversal: HybridReversal) -> None:
        with self._lock:
            self._check_header(reversal.record_id, reversal.input_watermark)
            delta = self._deltas.get(reversal.reverses_record_id)
            if delta is None:
                raise HybridLedgerError("reversal targets an unknown delta")
            if reversal.revision_id != delta.revision_id:
                raise HybridLedgerError("reversal revision does not match target delta")
            if reversal.authorization_scope_id != delta.authorization_scope_id:
                raise HybridLedgerError("reversal authorization scope does not match delta")
            if reversal.reverses_record_id not in self._promoted:
                raise HybridLedgerError("only a promoted delta can be retracted")
            if reversal.reverses_record_id in self._reversed:
                raise HybridLedgerError("delta is already retracted")
            if not reversal.reason.strip():
                raise HybridLedgerError("reversal reason must be non-empty")
            self._log.append(reversal)
            self._record_ids.add(reversal.record_id)
            self._reversed.add(reversal.reverses_record_id)
            self._last_watermark = reversal.input_watermark
            self._apply(delta, -1.0)

    def retract_revision(
        self,
        *,
        revision_id: UUID,
        reversal_record_ids: tuple[UUID, ...],
        input_watermark: int,
        authorization_scope_id: UUID,
        reason: str,
    ) -> int:
        """Retract the live promoted records in one revision in O(k) index work."""

        with self._lock:
            live = [
                record_id
                for record_id in self._by_revision.get(revision_id, ())
                if record_id in self._promoted and record_id not in self._reversed
            ]
            if len(reversal_record_ids) != len(live):
                raise HybridLedgerError("one reversal record id is required per live delta")
            if len(reversal_record_ids) != len(set(reversal_record_ids)):
                raise HybridLedgerError("reversal record ids must be unique")
            if any(record_id in self._record_ids for record_id in reversal_record_ids):
                raise HybridLedgerError("reversal record id is already present")
            for record_id, reversal_id in zip(live, reversal_record_ids, strict=True):
                self.retract(
                    HybridReversal(
                        record_id=reversal_id,
                        reverses_record_id=record_id,
                        revision_id=revision_id,
                        input_watermark=input_watermark,
                        authorization_scope_id=authorization_scope_id,
                        reason=reason,
                    )
                )
            return len(live)

    def replace_promoted_revision(
        self,
        *,
        superseded_revision_id: UUID,
        reversal_record_ids: tuple[UUID, ...],
        reversal_watermark: int,
        reversal_reason: str,
        corrected_delta: HybridStatisticDelta,
        promotion: HybridPromotion,
    ) -> HybridProjection:
        """Atomically retract a promoted revision and promote its correction.

        This is one all-or-nothing step under a single lock: no reader can observe
        the window where the superseded revision is retracted but the correction
        is not yet promoted, and every fallible check runs *before* any mutation,
        so a rejected replacement leaves the ledger exactly as it was.  Returns the
        committed projection for the corrected key (verified numerically reliable as
        a shadow before commit) so the caller can publish the map after the commit.
        """

        with self._lock:
            # --- pre-validation: no mutation may happen before this all passes ---
            if corrected_delta.parent_revision_id != superseded_revision_id:
                raise HybridLedgerError("corrected delta parent must be the superseded revision")
            parent_records = self._by_revision.get(superseded_revision_id, ())
            if not parent_records:
                raise HybridLedgerError("superseded revision does not exist")
            if any(record_id not in self._promoted for record_id in parent_records):
                raise HybridLedgerError("only a fully promoted revision can be atomically replaced")
            live = tuple(
                record_id
                for record_id in parent_records
                if record_id in self._promoted and record_id not in self._reversed
            )
            if len(reversal_record_ids) != len(live):
                raise HybridLedgerError("one reversal record id is required per live delta")
            if len(reversal_record_ids) != len(set(reversal_record_ids)):
                raise HybridLedgerError("reversal record ids must be unique")
            reserved = set(reversal_record_ids)
            reserved.update({corrected_delta.record_id, promotion.record_id})
            if len(reserved) != len(reversal_record_ids) + 2:
                raise HybridLedgerError("replacement record ids must be pairwise distinct")
            if any(record_id in self._record_ids for record_id in reserved):
                raise HybridLedgerError("a replacement record id is already present")
            if not reversal_reason.strip():
                raise HybridLedgerError("reversal reason must be non-empty")
            self._precheck_appendable(corrected_delta)
            if promotion.promotes_record_id != corrected_delta.record_id:
                raise HybridLedgerError("promotion must target the corrected delta")
            if promotion.authorization_scope_id != corrected_delta.authorization_scope_id:
                raise HybridLedgerError("promotion authorization scope does not match delta")
            if not promotion.reason.strip():
                raise HybridLedgerError("promotion reason must be non-empty")
            if not promotion.risk_certificate.allows_promotion:
                raise HybridLedgerError("constrained Bayesian risk gate rejected promotion")
            if promotion.risk_certificate.subject_delta_record_id != corrected_delta.record_id:
                raise HybridLedgerError("risk certificate is bound to another delta")
            if not (
                reversal_watermark >= self._last_watermark
                and corrected_delta.input_watermark >= reversal_watermark
                and promotion.input_watermark >= corrected_delta.input_watermark
            ):
                raise HybridLedgerError("replacement watermarks must be non-decreasing")

            # Shadow the corrected key's projection to confirm it is reliable
            # *before* committing anything.
            shadow = self._copy_projection(corrected_delta.key)
            for record_id in live:
                delta = self._deltas[record_id]
                if delta.key == corrected_delta.key:
                    self._apply_to(shadow, delta, -1.0)
            self._apply_to(shadow, corrected_delta, +1.0)
            shadow_projection = self._freeze(shadow)
            if shadow_projection.replay_required:
                raise HybridLedgerError("corrected projection is numerically unreliable")

            # --- commit: pre-validated, so these primitives cannot reject ---
            for record_id, reversal_id in zip(live, reversal_record_ids, strict=True):
                self.retract(
                    HybridReversal(
                        record_id=reversal_id,
                        reverses_record_id=record_id,
                        revision_id=superseded_revision_id,
                        input_watermark=reversal_watermark,
                        authorization_scope_id=promotion.authorization_scope_id,
                        reason=reversal_reason,
                    )
                )
            self.append_delta(corrected_delta)
            self.promote(promotion)
            return self.projection(corrected_delta.key)

    def _precheck_appendable(self, delta: HybridStatisticDelta) -> None:
        """Replicate append_delta's non-lineage checks without mutating state.

        The revision-lineage gate (parent must be fully retracted) is deliberately
        excluded: an atomic replacement retracts the parent in the same step, so it
        is validated by construction rather than by current state.
        """

        if delta.feature_dim != self.feature_dim:
            raise HybridLedgerError("delta feature dimension does not match ledger")
        if (delta.evidence_cluster_id, delta.key) in self._cluster_keys:
            raise HybridLedgerError("duplicate evidence_cluster_id and statistic key")
        if delta.semantic_dedup_id in self._dedup_ids:
            raise HybridLedgerError("duplicate semantic_dedup_id")
        if delta.initial_state != HybridConsolidationState.QUARANTINED:
            raise HybridLedgerError("a corrected replacement delta must start quarantined")
        previous_identity = self._cluster_identity.get(delta.evidence_cluster_id)
        if previous_identity is not None and previous_identity != (
            delta.event_hypothesis_id,
            delta.revision_id,
            delta.authorization_scope_id,
            delta.source_record_ids,
        ):
            raise HybridLedgerError("evidence cluster identity is inconsistent")

    def supersede_quarantined_revision(
        self,
        supersession: HybridQuarantineSupersession,
    ) -> None:
        """Atomically retire a quarantined revision before a corrected revision arrives."""

        with self._lock:
            self._check_header(supersession.record_id, supersession.input_watermark)
            record_ids = tuple(self._by_revision.get(supersession.supersedes_revision_id, ()))
            if not record_ids:
                raise HybridLedgerError("superseded revision does not exist")
            event_id = self._revision_event[supersession.supersedes_revision_id]
            if event_id != supersession.event_hypothesis_id:
                raise HybridLedgerError("supersession event does not match revision")
            if any(
                self.state_of(record_id) != HybridConsolidationState.QUARANTINED
                for record_id in record_ids
            ):
                raise HybridLedgerError("only a fully quarantined revision can be superseded")
            if any(
                self._deltas[record_id].authorization_scope_id
                != supersession.authorization_scope_id
                for record_id in record_ids
            ):
                raise HybridLedgerError("supersession authorization scope does not match revision")
            if supersession.successor_revision_id in self._revision_event:
                raise HybridLedgerError("successor revision id already exists")
            if not supersession.reason.strip():
                raise HybridLedgerError("supersession reason must be non-empty")
            self._log.append(supersession)
            self._record_ids.add(supersession.record_id)
            self._reversed.update(record_ids)
            self._quarantine_successor[supersession.supersedes_revision_id] = (
                supersession.successor_revision_id
            )
            self._last_watermark = supersession.input_watermark

    def state_of(self, record_id: UUID) -> HybridConsolidationState:
        with self._lock:
            if record_id not in self._deltas:
                raise HybridLedgerError("unknown delta record")
            if record_id in self._reversed:
                return HybridConsolidationState.RETRACTED
            if record_id in self._promoted:
                if self._deltas[record_id].parent_revision_id is not None:
                    return HybridConsolidationState.REACTIVATED
                return HybridConsolidationState.PROMOTED
            return HybridConsolidationState.QUARANTINED

    def projection(
        self,
        key: StatisticKey,
        *,
        exclude_evidence_cluster_id: UUID | None = None,
    ) -> HybridProjection:
        """Return one atomic snapshot, optionally excluding its own evidence cluster."""

        with self._lock:
            mutable = self._copy_projection(key)
            if exclude_evidence_cluster_id is not None:
                for record_id in self._promoted - self._reversed:
                    delta = self._deltas[record_id]
                    if (
                        delta.key == key
                        and delta.evidence_cluster_id == exclude_evidence_cluster_id
                    ):
                        self._apply_to(mutable, delta, -1.0)
            return self._freeze(mutable)

    def rebuild_projection(self, key: StatisticKey) -> HybridProjection:
        """Recompute a projection from append-only log state, bypassing the cache."""

        with self._lock:
            promoted: set[UUID] = set()
            reversed_ids: set[UUID] = set()
            deltas: dict[UUID, HybridStatisticDelta] = {}
            for record in self._log:
                if isinstance(record, HybridStatisticDelta):
                    deltas[record.record_id] = record
                    if record.initial_state == HybridConsolidationState.PROMOTED:
                        promoted.add(record.record_id)
                elif isinstance(record, HybridPromotion):
                    promoted.add(record.promotes_record_id)
                elif isinstance(record, HybridReversal):
                    reversed_ids.add(record.reverses_record_id)
                else:
                    reversed_ids.update(
                        delta_id
                        for delta_id, delta in deltas.items()
                        if delta.revision_id == record.supersedes_revision_id
                    )
            mutable = self._prior_projection()
            for record_id in promoted - reversed_ids:
                delta = deltas[record_id]
                if delta.key == key:
                    self._apply_to(mutable, delta, +1.0)
            return self._freeze(mutable)

    def projection_with_replay_fallback(
        self,
        key: StatisticKey,
        *,
        exclude_evidence_cluster_id: UUID | None = None,
    ) -> tuple[HybridProjection, bool]:
        """Use fast cache first, then replay; refuse if replay is still unreliable."""

        projected = self.projection(
            key,
            exclude_evidence_cluster_id=exclude_evidence_cluster_id,
        )
        if not projected.replay_required:
            return projected, False
        if exclude_evidence_cluster_id is not None:
            raise HybridLedgerError(
                "excluded projection is numerically unreliable; scoped replay is required"
            )
        rebuilt = self.rebuild_projection(key)
        if rebuilt.replay_required:
            raise HybridLedgerError("replayed projection remains numerically unreliable")
        return rebuilt, True

    def assert_cache_matches_replay(self, key: StatisticKey, *, atol: float = 1e-10) -> None:
        cached = self.projection(key)
        rebuilt = self.rebuild_projection(key)
        for left, right, name in (
            (cached.a, rebuilt.a, "A"),
            (cached.b, rebuilt.b, "b"),
            (cached.information, rebuilt.information, "Lambda"),
            (cached.information_vector, rebuilt.information_vector, "xi"),
        ):
            if not np.allclose(left, right, atol=atol, rtol=0.0):
                raise HybridLedgerError(f"cached {name} differs from replay")
        if abs(cached.alpha - rebuilt.alpha) > atol:
            raise HybridLedgerError("cached alpha differs from replay")

    def _validate_revision(self, delta: HybridStatisticDelta) -> None:
        known_event = self._revision_event.get(delta.revision_id)
        if known_event is not None:
            if known_event != delta.event_hypothesis_id:
                raise HybridLedgerError("revision id cannot span multiple events")
            if self._revision_parent[delta.revision_id] != delta.parent_revision_id:
                raise HybridLedgerError("revision parent must be stable")
            return
        parent = delta.parent_revision_id
        if parent is not None:
            parent_event = self._revision_event.get(parent)
            if parent_event is None:
                raise HybridLedgerError("parent revision does not exist")
            if parent_event != delta.event_hypothesis_id:
                raise HybridLedgerError("parent revision belongs to another event")
            parent_records = self._by_revision.get(parent, ())
            if any(record_id not in self._reversed for record_id in parent_records):
                raise HybridLedgerError("parent revision must be fully retracted")
            quarantine_successor = self._quarantine_successor.get(parent)
            if quarantine_successor is not None and quarantine_successor != delta.revision_id:
                raise HybridLedgerError("corrected revision does not match quarantine successor")
            ancestor: UUID | None = parent
            while ancestor is not None:
                if ancestor == delta.revision_id:
                    raise HybridLedgerError("revision lineage cannot contain a cycle")
                ancestor = self._revision_parent.get(ancestor)
        self._revision_event[delta.revision_id] = delta.event_hypothesis_id
        self._revision_parent[delta.revision_id] = parent

    def _check_header(self, record_id: UUID, watermark: int) -> None:
        if record_id in self._record_ids:
            raise HybridLedgerError("record id is already present")
        if watermark < self._last_watermark:
            raise HybridLedgerError("input watermark is behind the ledger head")

    def _validate_promotion(
        self,
        promotion: HybridPromotion,
        delta: HybridStatisticDelta,
    ) -> None:
        self._check_header(promotion.record_id, promotion.input_watermark)
        if promotion.authorization_scope_id != delta.authorization_scope_id:
            raise HybridLedgerError("promotion authorization scope does not match delta")
        if promotion.promotes_record_id in self._reversed:
            raise HybridLedgerError("a retracted delta cannot be promoted")
        if promotion.promotes_record_id in self._promoted:
            raise HybridLedgerError("delta is already promoted")
        if not promotion.reason.strip():
            raise HybridLedgerError("promotion reason must be non-empty")
        if not promotion.risk_certificate.allows_promotion:
            raise HybridLedgerError("constrained Bayesian risk gate rejected promotion")
        if promotion.risk_certificate.subject_delta_record_id != delta.record_id:
            raise HybridLedgerError("risk certificate is bound to another delta")

    def _commit_promotion(
        self,
        promotion: HybridPromotion,
        delta: HybridStatisticDelta,
    ) -> None:
        self._log.append(promotion)
        self._record_ids.add(promotion.record_id)
        self._promoted.add(promotion.promotes_record_id)
        self._last_watermark = promotion.input_watermark
        self._apply(delta, +1.0)

    def _prior_projection(self) -> _MutableProjection:
        return _MutableProjection(
            a=self.ridge * np.eye(self.feature_dim, dtype=float),
            b=np.zeros(self.feature_dim, dtype=float),
            alpha=self.alpha_prior,
            information=self.information_ridge * np.eye(self.feature_dim, dtype=float),
            information_vector=np.zeros(self.feature_dim, dtype=float),
        )

    def _copy_projection(self, key: StatisticKey) -> _MutableProjection:
        value = self._projection.get(key)
        if value is None:
            return self._prior_projection()
        return _MutableProjection(
            a=value.a.copy(),
            b=value.b.copy(),
            alpha=value.alpha,
            information=value.information.copy(),
            information_vector=value.information_vector.copy(),
        )

    def _apply(self, delta: HybridStatisticDelta, sign: float) -> None:
        target = self._projection.setdefault(delta.key, self._prior_projection())
        self._apply_to(target, delta, sign)

    @staticmethod
    def _apply_to(target: _MutableProjection, delta: HybridStatisticDelta, sign: float) -> None:
        target.a += sign * delta.delta_a
        target.b += sign * delta.delta_b
        target.alpha += sign * delta.delta_alpha
        target.information += sign * delta.delta_information
        target.information_vector += sign * delta.delta_information_vector
        target.a[:] = 0.5 * (target.a + target.a.T)
        target.information[:] = 0.5 * (target.information + target.information.T)

    def _freeze(self, value: _MutableProjection) -> HybridProjection:
        eigen_a = float(np.linalg.eigvalsh(value.a).min())
        eigen_information = float(np.linalg.eigvalsh(value.information).min())
        condition = float(np.linalg.cond(value.a))
        replay_required = (
            eigen_a <= 0.0
            or eigen_information <= 0.0
            or not isfinite(condition)
            or condition > self.max_condition_number
            or value.alpha < -1e-10
        )
        theta = (
            np.full(self.feature_dim, np.nan, dtype=float)
            if replay_required
            else np.linalg.solve(value.a, value.b)
        )
        arrays = (
            value.a.copy(),
            value.b.copy(),
            value.information.copy(),
            value.information_vector.copy(),
            theta.copy(),
        )
        for array in arrays:
            array.setflags(write=False)
        return HybridProjection(
            a=arrays[0],
            b=arrays[1],
            alpha=max(0.0, value.alpha),
            information=arrays[2],
            information_vector=arrays[3],
            theta=arrays[4],
            ledger_version=len(self._log),
            replay_required=replay_required,
            condition_number=condition,
        )


class NaturalRidgeResidual:
    """Small online residual calibrator exposing exact ``A``/``b`` statistics."""

    def __init__(self, *, feature_dim: int, ridge: float = 1e-6) -> None:
        if feature_dim <= 0 or ridge <= 0.0:
            raise ValueError("feature_dim and ridge must be positive")
        self.feature_dim = feature_dim
        self._a = ridge * np.eye(feature_dim, dtype=float)
        self._b: Vector = np.zeros(feature_dim, dtype=float)
        self._lock = threading.RLock()

    def predict(self, features: ArrayLike) -> float:
        vector = self._validate(features)
        with self._lock:
            return float(vector @ np.linalg.solve(self._a, self._b))

    def update(self, features: ArrayLike, residual: float, *, weight: float = 1.0) -> None:
        vector = self._validate(features)
        target = float(residual)
        sample_weight = float(weight)
        if not isfinite(target) or not isfinite(sample_weight) or sample_weight < 0.0:
            raise ValueError("residual must be finite and weight non-negative")
        with self._lock:
            self._a += sample_weight * np.outer(vector, vector)
            self._b += sample_weight * vector * target

    def sufficient_statistics(self) -> tuple[Matrix, Vector]:
        with self._lock:
            return self._a.copy(), self._b.copy()

    def _validate(self, features: ArrayLike) -> Vector:
        vector: Vector = np.asarray(features, dtype=float)
        if vector.shape != (self.feature_dim,) or np.any(~np.isfinite(vector)):
            raise ValueError("features have wrong shape or non-finite values")
        return vector


class DirichletRLSFusion:
    """Normalize a Dirichlet location base and add per-location RLS residual logits."""

    def __init__(self, *, probability_floor: float = 1e-12) -> None:
        if not 0.0 < probability_floor < 1.0:
            raise ValueError("probability_floor must be in (0, 1)")
        self.probability_floor = probability_floor

    def predict(
        self,
        ledger: HybridStatisticLedger,
        *,
        keys: tuple[StatisticKey, ...],
        context_features: ArrayLike,
        exclude_evidence_cluster_id: UUID | None = None,
    ) -> dict[UUID, FusedLocationBelief]:
        if not keys:
            raise ValueError("keys must be non-empty")
        locations = [key.location_id for key in keys]
        if len(locations) != len(set(locations)):
            raise ValueError("keys must contain unique locations")
        comparison = {
            (key.actor_key, key.object_instance_id, key.regime_id, key.parameter_block)
            for key in keys
        }
        if len(comparison) != 1:
            raise ValueError("fusion keys must share actor/object/regime/parameter block")
        vector: Vector = np.asarray(context_features, dtype=float)
        if vector.shape != (ledger.feature_dim,) or np.any(~np.isfinite(vector)):
            raise ValueError("context_features have wrong shape or non-finite values")

        projections = [
            ledger.projection(
                key,
                exclude_evidence_cluster_id=exclude_evidence_cluster_id,
            )
            for key in keys
        ]
        if any(projected.replay_required for projected in projections):
            raise HybridLedgerError("fusion requires numerically reliable projections")
        total_alpha = sum(projected.alpha for projected in projections)
        if total_alpha > 0.0:
            bases = [projected.alpha / total_alpha for projected in projections]
        else:
            bases = [1.0 / len(projections)] * len(projections)
        residuals = [float(projected.theta @ vector) for projected in projections]
        logits = np.asarray(
            [
                np.log(max(base, self.probability_floor)) + residual
                for base, residual in zip(bases, residuals, strict=True)
            ]
        )
        logits -= float(logits.max())
        weights = np.exp(logits)
        probabilities = weights / weights.sum()
        return {
            key.location_id: FusedLocationBelief(
                base_probability=base,
                contextual_residual=residual,
                fused_probability=float(probability),
                ledger_version=projected.ledger_version,
                excluded_evidence_cluster_id=exclude_evidence_cluster_id,
            )
            for key, projected, base, residual, probability in zip(
                keys,
                projections,
                bases,
                residuals,
                probabilities,
                strict=True,
            )
        }
