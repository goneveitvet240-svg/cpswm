"""Global evidence-factor production and consumption trace.

The trace distinguishes producing one probabilistic factor, consuming that
factor in a target distribution, deriving a posterior summary, and committing a
reversible statistic delta.  It therefore catches double likelihood use without
mistaking repeated reads of an already-normalized posterior for new evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Final
from uuid import UUID

from cpswm.system.reproducibility import content_sha256, content_uuid

TRACE_PROTOCOL_ID: Final = "evidence-factor-consumption-trace@0.2"


class EvidenceFactorKind(StrEnum):
    OBSERVATION_LIKELIHOOD = "observation_likelihood"
    TRANSITION_PRIOR = "transition_prior"
    PROPOSAL_DISTRIBUTION = "proposal_distribution"
    STRUCTURAL_CONSTRAINT = "structural_constraint"
    POSTERIOR_SUMMARY = "posterior_summary"
    REGIME_TRANSITION = "regime_transition"
    COMMIT_DELTA = "commit_delta"
    ADMISSION_DECISION = "admission_decision"
    ACTION_LIKELIHOOD = "action_likelihood"
    ACTION_OUTCOME = "action_outcome"


class EvidenceFactorSourceSemantics(StrEnum):
    """Typed origin of a primitive factor, independent of caller labels."""

    RAW_OBSERVATION_EVIDENCE = "raw_observation_evidence"
    ACTION_EXECUTION_FEEDBACK = "action_execution_feedback"
    NEURAL_PROPOSAL = "neural_proposal"
    STRUCTURED_MODEL = "structured_model"
    POSTERIOR_SNAPSHOT = "posterior_snapshot"


class EvidenceFactorOperation(StrEnum):
    PRODUCE = "produce"
    CONSUME = "consume"
    DERIVE = "derive"
    COMMIT = "commit"


class EvidenceFactorOperator(StrEnum):
    OPCEU = "opceu"
    ORRER_CHEH = "orrer_cheh"
    PCHMP = "pchmp"
    CF_BOCPD = "cf_bocpd"
    RGRC = "rgrc"
    CCRR = "ccrr"
    CIAV = "ciav"
    EXECUTION_FEEDBACK = "execution_feedback"
    NEURAL_PROPOSER = "neural_proposer"
    PARTICLE_REVISION = "particle_revision"
    ACTION_READOUT = "action_readout"


@dataclass(frozen=True, slots=True)
class EvidenceFactorReceipt:
    receipt_id: UUID
    sequence: int
    update_id: UUID
    evidence_cluster_id: UUID
    evidence_record_ids: tuple[UUID, ...]
    operator: EvidenceFactorOperator
    operation: EvidenceFactorOperation
    factor_id: str
    factor_kind: EvidenceFactorKind
    source_semantics: EvidenceFactorSourceSemantics | None
    source_payload_sha256: str | None
    source_factor_ids: tuple[str, ...]
    target_distribution_id: str | None
    likelihood_model_id: str | None
    consumed_as_likelihood: bool
    idempotency_key: str
    previous_hash: str
    receipt_hash: str


class EvidenceFactorConsumptionTrace:
    """Append-only factor graph with exactly-once likelihood consumption."""

    def __init__(self) -> None:
        self._receipts: list[EvidenceFactorReceipt] = []
        self._factors: dict[str, EvidenceFactorReceipt] = {}
        self._idempotency: dict[str, tuple[str, EvidenceFactorReceipt]] = {}
        self._likelihood_consumptions: set[tuple[str, str]] = set()
        self._cluster_likelihood_models: dict[UUID, str] = {}
        self._record_payload_hashes: dict[UUID, str] = {}

    @property
    def receipts(self) -> tuple[EvidenceFactorReceipt, ...]:
        return tuple(self._receipts)

    @property
    def head_hash(self) -> str:
        return self._receipts[-1].receipt_hash if self._receipts else "GENESIS"

    def _append(
        self,
        *,
        update_id: UUID,
        evidence_cluster_id: UUID,
        evidence_record_ids: Sequence[UUID],
        operator: EvidenceFactorOperator,
        operation: EvidenceFactorOperation,
        factor_id: str,
        factor_kind: EvidenceFactorKind,
        source_semantics: EvidenceFactorSourceSemantics | None = None,
        source_record_payloads: Mapping[UUID, object] | None = None,
        source_factor_ids: Sequence[str] = (),
        target_distribution_id: str | None = None,
        likelihood_model_id: str | None = None,
        consumed_as_likelihood: bool = False,
        idempotency_key: str,
    ) -> EvidenceFactorReceipt:
        if not factor_id.strip() or not idempotency_key.strip():
            raise ValueError("factor_id and idempotency_key must be non-empty")
        record_ids = tuple(evidence_record_ids)
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("evidence factor receipt contains duplicate record ids")
        source_ids = tuple(source_factor_ids)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("evidence factor receipt contains duplicate source factors")
        payload_hash = (
            None
            if source_record_payloads is None
            else content_sha256(
                sorted(
                    (str(record_id), payload)
                    for record_id, payload in source_record_payloads.items()
                )
            )
        )
        intent = {
            "update_id": str(update_id),
            "evidence_cluster_id": str(evidence_cluster_id),
            "evidence_record_ids": [str(value) for value in record_ids],
            "operator": operator.value,
            "operation": operation.value,
            "factor_id": factor_id,
            "factor_kind": factor_kind.value,
            "source_semantics": None if source_semantics is None else source_semantics.value,
            "source_payload_sha256": payload_hash,
            "source_factor_ids": list(source_ids),
            "target_distribution_id": target_distribution_id,
            "likelihood_model_id": likelihood_model_id,
            "consumed_as_likelihood": consumed_as_likelihood,
            "idempotency_key": idempotency_key,
        }
        intent_hash = content_sha256(intent)
        prior = self._idempotency.get(idempotency_key)
        if prior is not None:
            prior_hash, receipt = prior
            if prior_hash != intent_hash:
                raise ValueError("idempotency key was reused with different factor semantics")
            return receipt
        if operation is EvidenceFactorOperation.PRODUCE:
            if source_ids:
                raise ValueError("a produced primitive factor cannot name source factors")
            if factor_id in self._factors:
                raise ValueError("factor_id was already produced")
            if source_semantics is None or source_record_payloads is None:
                raise ValueError("a primitive factor requires typed source payloads")
            if set(source_record_payloads) != set(record_ids):
                raise ValueError("source payload ids must exactly match evidence record ids")
            permitted = {
                EvidenceFactorKind.OBSERVATION_LIKELIHOOD: {
                    EvidenceFactorSourceSemantics.RAW_OBSERVATION_EVIDENCE
                },
                EvidenceFactorKind.ACTION_LIKELIHOOD: {
                    EvidenceFactorSourceSemantics.ACTION_EXECUTION_FEEDBACK
                },
                EvidenceFactorKind.PROPOSAL_DISTRIBUTION: {
                    EvidenceFactorSourceSemantics.NEURAL_PROPOSAL
                },
                EvidenceFactorKind.TRANSITION_PRIOR: {
                    EvidenceFactorSourceSemantics.STRUCTURED_MODEL
                },
                EvidenceFactorKind.STRUCTURAL_CONSTRAINT: {
                    EvidenceFactorSourceSemantics.STRUCTURED_MODEL
                },
                EvidenceFactorKind.POSTERIOR_SUMMARY: {
                    EvidenceFactorSourceSemantics.POSTERIOR_SNAPSHOT
                },
            }
            if source_semantics not in permitted.get(factor_kind, set()):
                raise ValueError("primitive factor kind is incompatible with source semantics")
            for record_id, payload in source_record_payloads.items():
                record_hash = content_sha256(payload)
                prior_record_hash = self._record_payload_hashes.get(record_id)
                if prior_record_hash is not None and prior_record_hash != record_hash:
                    raise ValueError("evidence record id was rebound to different payload content")
        else:
            if source_semantics is not None or source_record_payloads is not None:
                raise ValueError("only primitive factors may bind source payloads")
            if operation in {
                EvidenceFactorOperation.DERIVE,
                EvidenceFactorOperation.COMMIT,
            } and factor_kind in {
                EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
                EvidenceFactorKind.ACTION_LIKELIHOOD,
            }:
                raise ValueError("a derived or committed factor cannot mint a likelihood")
            if operation is EvidenceFactorOperation.COMMIT and (
                factor_kind is not EvidenceFactorKind.COMMIT_DELTA
            ):
                raise ValueError("a commit receipt must materialize a commit delta")
            if operation is EvidenceFactorOperation.DERIVE and (
                factor_kind is EvidenceFactorKind.COMMIT_DELTA
            ):
                raise ValueError("a commit delta requires the commit operation")
            if not source_ids:
                raise ValueError("consume/derive/commit receipts require source factors")
            missing = [source for source in source_ids if source not in self._factors]
            if missing:
                raise ValueError(f"source factor was not produced: {missing[0]}")
            source_record_ids = {
                record_id
                for source in source_ids
                for record_id in self._factors[source].evidence_record_ids
            }
            if set(record_ids) != source_record_ids:
                raise ValueError("derived receipt record ids must match its source factors")
            if (
                operation
                in {
                    EvidenceFactorOperation.DERIVE,
                    EvidenceFactorOperation.COMMIT,
                }
                and factor_id in self._factors
            ):
                raise ValueError("factor_id was already materialized")
        if consumed_as_likelihood:
            if operation is not EvidenceFactorOperation.CONSUME:
                raise ValueError("only a consume receipt may apply a likelihood")
            if target_distribution_id is None or not target_distribution_id.strip():
                raise ValueError("likelihood consumption requires a target distribution")
            for source in source_ids:
                produced = self._factors[source]
                if produced.factor_kind is EvidenceFactorKind.POSTERIOR_SUMMARY:
                    raise ValueError("a posterior summary cannot be consumed as a new likelihood")
                if produced.factor_kind not in {
                    EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
                    EvidenceFactorKind.ACTION_LIKELIHOOD,
                }:
                    raise ValueError("only a typed likelihood factor may be so consumed")
                key = (target_distribution_id, source)
                if key in self._likelihood_consumptions:
                    raise ValueError("observation likelihood already consumed by this target")
        if factor_kind in {
            EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
            EvidenceFactorKind.ACTION_LIKELIHOOD,
        }:
            if likelihood_model_id is None or not likelihood_model_id.strip():
                raise ValueError("observation likelihood requires likelihood_model_id")
            bound = self._cluster_likelihood_models.get(evidence_cluster_id)
            if bound is not None and bound != likelihood_model_id:
                raise ValueError("evidence cluster was rebound to another likelihood model")
        for source in source_ids:
            produced = self._factors[source]
            if (
                likelihood_model_id is not None
                and produced.likelihood_model_id is not None
                and likelihood_model_id != produced.likelihood_model_id
            ):
                raise ValueError("consumer likelihood model differs from its source factor")

        unsigned = {
            "protocol": TRACE_PROTOCOL_ID,
            "sequence": len(self._receipts),
            "update_id": str(update_id),
            "evidence_cluster_id": str(evidence_cluster_id),
            "evidence_record_ids": [str(value) for value in record_ids],
            "operator": operator.value,
            "operation": operation.value,
            "factor_id": factor_id,
            "factor_kind": factor_kind.value,
            "source_semantics": None if source_semantics is None else source_semantics.value,
            "source_payload_sha256": payload_hash,
            "source_factor_ids": list(source_ids),
            "target_distribution_id": target_distribution_id,
            "likelihood_model_id": likelihood_model_id,
            "consumed_as_likelihood": consumed_as_likelihood,
            "idempotency_key": idempotency_key,
            "previous_hash": self.head_hash,
        }
        receipt_hash = content_sha256(unsigned)
        receipt = EvidenceFactorReceipt(
            receipt_id=content_uuid("evidence-factor-receipt", unsigned),
            sequence=len(self._receipts),
            update_id=update_id,
            evidence_cluster_id=evidence_cluster_id,
            evidence_record_ids=record_ids,
            operator=operator,
            operation=operation,
            factor_id=factor_id,
            factor_kind=factor_kind,
            source_semantics=source_semantics,
            source_payload_sha256=payload_hash,
            source_factor_ids=source_ids,
            target_distribution_id=target_distribution_id,
            likelihood_model_id=likelihood_model_id,
            consumed_as_likelihood=consumed_as_likelihood,
            idempotency_key=idempotency_key,
            previous_hash=self.head_hash,
            receipt_hash=receipt_hash,
        )
        self._receipts.append(receipt)
        self._idempotency[idempotency_key] = (intent_hash, receipt)
        if operation in {
            EvidenceFactorOperation.PRODUCE,
            EvidenceFactorOperation.DERIVE,
            EvidenceFactorOperation.COMMIT,
        }:
            if factor_id in self._factors:
                raise ValueError("factor_id was already materialized")
            self._factors[factor_id] = receipt
        if operation is EvidenceFactorOperation.PRODUCE:
            assert source_record_payloads is not None
            for record_id, payload in source_record_payloads.items():
                self._record_payload_hashes[record_id] = content_sha256(payload)
        if factor_kind in {
            EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
            EvidenceFactorKind.ACTION_LIKELIHOOD,
        }:
            assert likelihood_model_id is not None
            self._cluster_likelihood_models[evidence_cluster_id] = likelihood_model_id
        if consumed_as_likelihood:
            for source in source_ids:
                self._likelihood_consumptions.add((target_distribution_id or "", source))
        return receipt

    def produce_factor(self, **kwargs: Any) -> EvidenceFactorReceipt:
        return self._append(operation=EvidenceFactorOperation.PRODUCE, **kwargs)

    def consume_factor(self, **kwargs: Any) -> EvidenceFactorReceipt:
        return self._append(operation=EvidenceFactorOperation.CONSUME, **kwargs)

    def derive_factor(self, **kwargs: Any) -> EvidenceFactorReceipt:
        return self._append(operation=EvidenceFactorOperation.DERIVE, **kwargs)

    def commit_factor(self, **kwargs: Any) -> EvidenceFactorReceipt:
        return self._append(operation=EvidenceFactorOperation.COMMIT, **kwargs)

    def verify_chain(self) -> bool:
        previous = "GENESIS"
        for sequence, receipt in enumerate(self._receipts):
            if receipt.sequence != sequence or receipt.previous_hash != previous:
                return False
            unsigned = {
                "protocol": TRACE_PROTOCOL_ID,
                "sequence": receipt.sequence,
                "update_id": str(receipt.update_id),
                "evidence_cluster_id": str(receipt.evidence_cluster_id),
                "evidence_record_ids": [str(value) for value in receipt.evidence_record_ids],
                "operator": receipt.operator.value,
                "operation": receipt.operation.value,
                "factor_id": receipt.factor_id,
                "factor_kind": receipt.factor_kind.value,
                "source_semantics": (
                    None if receipt.source_semantics is None else receipt.source_semantics.value
                ),
                "source_payload_sha256": receipt.source_payload_sha256,
                "source_factor_ids": list(receipt.source_factor_ids),
                "target_distribution_id": receipt.target_distribution_id,
                "likelihood_model_id": receipt.likelihood_model_id,
                "consumed_as_likelihood": receipt.consumed_as_likelihood,
                "idempotency_key": receipt.idempotency_key,
                "previous_hash": receipt.previous_hash,
            }
            if content_sha256(unsigned) != receipt.receipt_hash:
                return False
            previous = receipt.receipt_hash
        return True

    def audit_payload(self) -> dict[str, object]:
        return {
            "protocol": TRACE_PROTOCOL_ID,
            "receipt_count": len(self._receipts),
            "factor_count": len(self._factors),
            "likelihood_consumption_count": len(self._likelihood_consumptions),
            "head_hash": self.head_hash,
            "chain_valid": self.verify_chain(),
            "integrity_scope": "in_process_content_binding_not_external_authenticity",
            "receipts": [asdict(receipt) for receipt in self._receipts],
        }


__all__ = [
    "TRACE_PROTOCOL_ID",
    "EvidenceFactorConsumptionTrace",
    "EvidenceFactorKind",
    "EvidenceFactorOperation",
    "EvidenceFactorOperator",
    "EvidenceFactorReceipt",
    "EvidenceFactorSourceSemantics",
]
