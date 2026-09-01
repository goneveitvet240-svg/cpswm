"""Certified write ingress for the Structure One world model.

This module is deliberately method-agnostic.  It makes the evidence/authority
rules mandatory before any M13--M19 backend is called, while leaving the
identity, commonsense, hidden-event and habit algorithms injectable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from enum import Enum, StrEnum
from threading import RLock
from typing import Any, cast
from uuid import UUID, uuid4

from cpswm.contracts.base import BaseRecordMetadata, SourceType


class StructureOneModule(StrEnum):
    SCENE_GRAPH = "M13_scene_graph"
    EPISODIC_TIMELINE = "M14_episodic_timeline"
    PROVENANCE = "M15_provenance"
    BELIEF_STATE = "M16_belief_state"
    HABIT_LEDGER = "M17_habit_ledger"
    HIDDEN_EVENT_LEDGER = "M18_hidden_event_ledger"
    OBJECT_LIFECYCLE = "M19_object_lifecycle"


class StructureOneContentKind(StrEnum):
    DIRECT_OBSERVATION = "direct_observation"
    EPISODIC_EVENT = "episodic_event"
    INFERRED_EVENT = "inferred_event"
    HABIT_EVIDENCE = "habit_evidence"
    FUTURE_PREDICTION = "future_prediction"
    PREFERENCE = "preference"
    NORM = "norm"
    EXECUTION_FEEDBACK = "execution_feedback"


class EvidenceAuthority(StrEnum):
    SENSOR = "sensor"
    USER_STATEMENT = "user_statement"
    ROBOT_INFERENCE = "robot_inference"
    MODEL_PREDICTION = "model_prediction"
    EXECUTION_FEEDBACK = "execution_feedback"


class FactEligibility(StrEnum):
    EVIDENCE = "evidence"
    HYPOTHESIS_ONLY = "hypothesis_only"
    PREDICTION_ONLY = "prediction_only"
    DIRECTIVE_ONLY = "directive_only"


class ActorInputAuthority(StrEnum):
    ABSENT = "absent"
    ROBOT_POSTERIOR = "robot_posterior"
    HARD_TRUTH = "hard_truth"


class StructureOneRunScope(StrEnum):
    CERTIFIED_RUNTIME = "certified_runtime"
    LEGACY_REPRODUCTION = "legacy_reproduction"
    ORACLE_EVALUATION = "oracle_evaluation"


class IngressStatus(StrEnum):
    APPLIED = "applied"
    CERTIFIED_ONLY = "certified_only"
    REPLAY_NOOP = "replay_noop"


class StructureOneIngressError(ValueError):
    """Raised when a write attempts to bypass Structure One semantics."""


@dataclass(frozen=True, slots=True)
class StructureOneWriteRequest:
    target_module: StructureOneModule
    content_kind: StructureOneContentKind
    authority: EvidenceAuthority
    fact_eligibility: FactEligibility
    source_record_ids: tuple[UUID, ...]
    actor_input_authority: ActorInputAuthority = ActorInputAuthority.ABSENT
    training_eligible: bool = False
    run_scope: StructureOneRunScope = StructureOneRunScope.CERTIFIED_RUNTIME
    request_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class CertifiedStructureOneWrite:
    request: StructureOneWriteRequest
    payload: object
    payload_schema: str
    payload_sha256: str
    certified_at: datetime


@dataclass(frozen=True, slots=True)
class StructureOneIngressReceipt:
    request_id: UUID
    target_module: StructureOneModule
    status: IngressStatus
    payload_sha256: str
    certified_at: datetime


StructureOneBackend = Callable[[CertifiedStructureOneWrite], None]


_ALLOWED_TARGETS: dict[StructureOneContentKind, frozenset[StructureOneModule]] = {
    StructureOneContentKind.DIRECT_OBSERVATION: frozenset(
        {
            StructureOneModule.SCENE_GRAPH,
            StructureOneModule.EPISODIC_TIMELINE,
            StructureOneModule.PROVENANCE,
            StructureOneModule.BELIEF_STATE,
            StructureOneModule.OBJECT_LIFECYCLE,
        }
    ),
    StructureOneContentKind.EPISODIC_EVENT: frozenset(
        {
            StructureOneModule.SCENE_GRAPH,
            StructureOneModule.EPISODIC_TIMELINE,
            StructureOneModule.PROVENANCE,
            StructureOneModule.BELIEF_STATE,
            StructureOneModule.OBJECT_LIFECYCLE,
        }
    ),
    StructureOneContentKind.INFERRED_EVENT: frozenset(
        {
            StructureOneModule.EPISODIC_TIMELINE,
            StructureOneModule.PROVENANCE,
            StructureOneModule.BELIEF_STATE,
            StructureOneModule.HIDDEN_EVENT_LEDGER,
            StructureOneModule.OBJECT_LIFECYCLE,
        }
    ),
    StructureOneContentKind.HABIT_EVIDENCE: frozenset(
        {StructureOneModule.PROVENANCE, StructureOneModule.HABIT_LEDGER}
    ),
    StructureOneContentKind.FUTURE_PREDICTION: frozenset(
        {StructureOneModule.PROVENANCE, StructureOneModule.BELIEF_STATE}
    ),
    StructureOneContentKind.PREFERENCE: frozenset(
        {
            StructureOneModule.SCENE_GRAPH,
            StructureOneModule.PROVENANCE,
            StructureOneModule.BELIEF_STATE,
        }
    ),
    StructureOneContentKind.NORM: frozenset(
        {
            StructureOneModule.SCENE_GRAPH,
            StructureOneModule.PROVENANCE,
            StructureOneModule.BELIEF_STATE,
        }
    ),
    StructureOneContentKind.EXECUTION_FEEDBACK: frozenset(
        {
            StructureOneModule.EPISODIC_TIMELINE,
            StructureOneModule.PROVENANCE,
            StructureOneModule.BELIEF_STATE,
            StructureOneModule.HIDDEN_EVENT_LEDGER,
            StructureOneModule.OBJECT_LIFECYCLE,
        }
    ),
}


class StructureOneCertifiedIngress:
    """The only supported write path into registered Structure One backends."""

    def __init__(
        self,
        *,
        backends: Mapping[StructureOneModule, StructureOneBackend] | None = None,
    ) -> None:
        self._backends = dict(backends or {})
        self._receipts: list[StructureOneIngressReceipt] = []
        self._by_request_id: dict[UUID, tuple[str, StructureOneIngressReceipt]] = {}
        self._lock = RLock()

    def register_backend(self, module: StructureOneModule, backend: StructureOneBackend) -> None:
        with self._lock:
            self._backends[module] = backend

    def has_backend(self, module: StructureOneModule) -> bool:
        return module in self._backends

    @property
    def receipts(self) -> tuple[StructureOneIngressReceipt, ...]:
        return tuple(self._receipts)

    def submit(
        self, request: StructureOneWriteRequest, payload: object
    ) -> StructureOneIngressReceipt:
        self._validate(request)
        self._validate_payload_provenance(request, payload)
        payload_schema = type(payload).__name__
        payload_sha256 = _content_sha256(payload)
        request_fingerprint = _content_sha256(
            {"request": request, "payload_sha256": payload_sha256}
        )

        with self._lock:
            prior = self._by_request_id.get(request.request_id)
            if prior is not None:
                prior_fingerprint, prior_receipt = prior
                if prior_fingerprint != request_fingerprint:
                    raise StructureOneIngressError(
                        "request_id collision with different certified content"
                    )
                return StructureOneIngressReceipt(
                    request_id=prior_receipt.request_id,
                    target_module=prior_receipt.target_module,
                    status=IngressStatus.REPLAY_NOOP,
                    payload_sha256=prior_receipt.payload_sha256,
                    certified_at=prior_receipt.certified_at,
                )

            certified_at = datetime.now().astimezone()
            certified = CertifiedStructureOneWrite(
                request=request,
                payload=payload,
                payload_schema=payload_schema,
                payload_sha256=payload_sha256,
                certified_at=certified_at,
            )
            backend = self._backends.get(request.target_module)
            status = IngressStatus.CERTIFIED_ONLY
            if backend is not None:
                backend(certified)
                status = IngressStatus.APPLIED

            receipt = StructureOneIngressReceipt(
                request_id=request.request_id,
                target_module=request.target_module,
                status=status,
                payload_sha256=payload_sha256,
                certified_at=certified_at,
            )
            self._by_request_id[request.request_id] = (request_fingerprint, receipt)
            self._receipts.append(receipt)
            return receipt

    @staticmethod
    def _validate(request: StructureOneWriteRequest) -> None:
        if not request.source_record_ids:
            raise StructureOneIngressError(
                "every Structure One write requires at least one source record"
            )
        if len(set(request.source_record_ids)) != len(request.source_record_ids):
            raise StructureOneIngressError("source_record_ids must be unique")
        if request.target_module not in _ALLOWED_TARGETS[request.content_kind]:
            raise StructureOneIngressError(
                f"{request.content_kind.value} cannot write {request.target_module.value}"
            )
        if (
            request.actor_input_authority is ActorInputAuthority.HARD_TRUTH
            and request.run_scope is StructureOneRunScope.CERTIFIED_RUNTIME
        ):
            raise StructureOneIngressError(
                "certified runtime forbids evaluator-grade hard actor truth"
            )
        if (
            request.content_kind is StructureOneContentKind.INFERRED_EVENT
            and request.fact_eligibility is not FactEligibility.HYPOTHESIS_ONLY
        ):
            raise StructureOneIngressError("inferred events must remain hypothesis_only")
        if (
            request.content_kind is StructureOneContentKind.FUTURE_PREDICTION
            and request.fact_eligibility is not FactEligibility.PREDICTION_ONLY
        ):
            raise StructureOneIngressError("future predictions must remain prediction_only")
        if (
            request.content_kind
            in {
                StructureOneContentKind.PREFERENCE,
                StructureOneContentKind.NORM,
            }
            and request.fact_eligibility is not FactEligibility.DIRECTIVE_ONLY
        ):
            raise StructureOneIngressError("preferences and norms are directives, not observations")
        if (
            request.training_eligible
            and request.target_module is not StructureOneModule.HABIT_LEDGER
        ):
            raise StructureOneIngressError(
                "training_eligible is only valid at the habit-ledger ingress"
            )
        if request.target_module is StructureOneModule.HABIT_LEDGER:
            if request.content_kind is not StructureOneContentKind.HABIT_EVIDENCE:
                raise StructureOneIngressError(
                    "M17 accepts only explicitly qualified habit evidence"
                )
            if request.fact_eligibility is not FactEligibility.EVIDENCE:
                raise StructureOneIngressError("M17 evidence must be fact-eligible")
            if request.authority not in {
                EvidenceAuthority.SENSOR,
                EvidenceAuthority.EXECUTION_FEEDBACK,
            }:
                raise StructureOneIngressError(
                    "inference, prediction and directives cannot train M17"
                )
            if not request.training_eligible:
                raise StructureOneIngressError(
                    "M17 writes must explicitly declare training eligibility"
                )

    @staticmethod
    def _validate_payload_provenance(
        request: StructureOneWriteRequest,
        payload: object,
    ) -> None:
        """Training authority must come from the payload, not caller self-report."""

        if not request.training_eligible:
            return
        metadata = getattr(payload, "metadata", None)
        if not isinstance(metadata, BaseRecordMetadata):
            raise StructureOneIngressError(
                "training-eligible writes require payload-bound source metadata"
            )
        if metadata.record_id not in request.source_record_ids:
            raise StructureOneIngressError(
                "training payload record id must be one of the declared source records"
            )
        allowed_source_types = {
            EvidenceAuthority.SENSOR: {SourceType.SENSOR},
            EvidenceAuthority.EXECUTION_FEEDBACK: {SourceType.ACTION},
        }.get(request.authority, set())
        if metadata.source_type not in allowed_source_types:
            raise StructureOneIngressError(
                "self-declared evidence authority does not match payload provenance"
            )


def _content_sha256(value: object) -> str:
    body = json.dumps(
        _jsonable(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _jsonable(value: object) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(cast(Any, value)))
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key)
            if normalized_key in normalized:
                raise StructureOneIngressError(
                    "payload mapping keys collide after JSON normalization"
                )
            normalized[normalized_key] = _jsonable(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported certified payload type: {type(value).__name__}")
