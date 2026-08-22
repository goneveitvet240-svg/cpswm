"""Independent HMAC authority and persistent M03 state log for SHIFT gates."""

from __future__ import annotations

import hmac
import os
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import JsonValue

from cpswm.contracts.base import (
    BaseRecordMetadata,
    ContractModel,
    SourceType,
    utc_now,
)
from cpswm.foundation.persistence_replay.contracts import (
    CommittedTransaction,
    StorePartition,
    canonical_json,
)
from cpswm.foundation.persistence_replay.memory_store import AppendOnlyTransactionLog
from cpswm.system.reproducibility import content_sha256, content_uuid

from .project_one_shift_gates import (
    SHIFT_THREE_ARMS,
    GateStateCommitProof,
    ShiftATG2Draft,
    ShiftATG2Report,
    ShiftATG3Report,
    ShiftTuningCompletionReceipt,
    TuningArmReceiptBinding,
)


class ExperimentGateEventRecord(ContractModel):
    metadata: BaseRecordMetadata
    event_type: Literal["ATG2_COMPLETED", "TEST_UNSEALED", "ATG3_COMPLETED"]
    experiment_id: str
    authority_key_id: str
    payload: dict[str, JsonValue]
    payload_sha256: str


class ShiftExperimentAuthority:
    """Verifier/signer that is never instantiated inside the tuning worker."""

    def __init__(self, *, key: bytes, key_id: str, log_path: Path) -> None:
        if len(key) < 32:
            raise ValueError("authority signing key must contain at least 32 bytes")
        if not key_id:
            raise ValueError("authority key ID cannot be empty")
        self._key = key
        self.key_id = key_id
        self.log_path = log_path.resolve(strict=False)
        self._log = (
            AppendOnlyTransactionLog.load(self.log_path)
            if self.log_path.exists()
            else AppendOnlyTransactionLog(partition=StorePartition.REPLAY)
        )

    @staticmethod
    def _arm_bindings(draft: ShiftATG2Draft) -> tuple[TuningArmReceiptBinding, ...]:
        return tuple(
            TuningArmReceiptBinding(
                arm_id=ledger.arm_id,
                tuning_run_id=ledger.tuning_run_id,
                trial_count=len(ledger.trials),
                search_space_sha256=ledger.search_space_sha256,
                selected_params_sha256=ledger.selected_params_sha256,
                measured_budget_ledger_sha256=ledger.ledger_sha256,
                model_version=ledger.model_version,
                completion_status="COMPLETED_WITHIN_BUDGET",
                canonical_log_head_sha256=ledger.canonical_log_head_sha256,
            )
            for ledger in draft.ledgers
        )

    @classmethod
    def _registration_payload(cls, draft: ShiftATG2Draft) -> dict[str, JsonValue]:
        return {
            "event_type": "ATG2_COMPLETED",
            "draft_sha256": draft.draft_sha256,
            "topology_manifest_sha256": draft.topology_manifest_sha256,
            "experiment_id": draft.experiment_id,
            "validation_split_sha256": draft.validation_split_sha256,
            "test_split_sha256": draft.test_split_sha256,
            "code_snapshot_sha256": draft.code_snapshot_sha256,
            "required_arm_ids": [arm.value for arm in SHIFT_THREE_ARMS],
            "arm_bindings": [item.model_dump(mode="json") for item in cls._arm_bindings(draft)],
        }

    def _hmac(self, payload: dict[str, JsonValue]) -> str:
        return hmac.new(
            self._key,
            canonical_json(payload).encode("utf-8"),
            sha256,
        ).hexdigest()

    def _append_event(
        self,
        *,
        event_type: Literal["ATG2_COMPLETED", "TEST_UNSEALED", "ATG3_COMPLETED"],
        experiment_id: str,
        payload: dict[str, JsonValue],
    ) -> tuple[CommittedTransaction, GateStateCommitProof]:
        payload_hash = content_sha256(payload)
        for transaction in self._log.read():
            record_payload = transaction.records[0].envelope.payload
            if (
                isinstance(record_payload, dict)
                and record_payload.get("event_type") == event_type
                and record_payload.get("payload_sha256") == payload_hash
            ):
                return transaction, GateStateCommitProof(
                    event_type=event_type,
                    transaction_id=transaction.transaction_id,
                    global_commit_seq=transaction.global_commit_seq,
                    request_sha256=transaction.request_sha256,
                    log_head_sha256=self._log.fingerprint(
                        through_commit_seq=transaction.global_commit_seq
                    ),
                    event_payload_sha256=payload_hash,
                )
        household_id = content_uuid("project-one-shift-authority-household", experiment_id)
        trace_id = content_uuid("project-one-shift-authority-trace", experiment_id)
        record = ExperimentGateEventRecord(
            metadata=BaseRecordMetadata(
                record_id=content_uuid(
                    "project-one-shift-gate-event",
                    {
                        "event_type": event_type,
                        "experiment_id": experiment_id,
                        "payload_sha256": payload_hash,
                    },
                ),
                schema_name="ProjectOneShiftGateEvent",
                schema_version="2.0.0",
                household_id=household_id,
                session_id=content_uuid("project-one-shift-authority-session", experiment_id),
                recorded_time=utc_now(),
                source_type=SourceType.MODEL,
                source_id=f"shift-experiment-authority:{self.key_id}",
                model_version="project-one-shift-authority@2",
                trace_id=trace_id,
            ),
            event_type=event_type,
            experiment_id=experiment_id,
            authority_key_id=self.key_id,
            payload=payload,
            payload_sha256=payload_hash,
        )
        result = self._log.append(
            [record],
            idempotency_key=f"{event_type}:{payload_hash}",
        )
        self._dump_atomic()
        proof = GateStateCommitProof(
            event_type=event_type,
            transaction_id=result.transaction.transaction_id,
            global_commit_seq=result.transaction.global_commit_seq,
            request_sha256=result.transaction.request_sha256,
            log_head_sha256=self._log.fingerprint(
                through_commit_seq=result.transaction.global_commit_seq
            ),
            event_payload_sha256=payload_hash,
        )
        return result.transaction, proof

    def _dump_atomic(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.log_path.parent,
                prefix=f".{self.log_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
            self._log.dump(temporary_path)
            with temporary_path.open("rb") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.log_path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def commit_atg2(self, draft_input: ShiftATG2Draft) -> ShiftATG2Report:
        draft = ShiftATG2Draft.model_validate(draft_input.model_dump(mode="json"))
        registration_payload = self._registration_payload(draft)
        transaction, proof = self._append_event(
            event_type="ATG2_COMPLETED",
            experiment_id=draft.experiment_id,
            payload=registration_payload,
        )
        receipt_unsigned: dict[str, JsonValue] = {
            "receipt_scope": "project-one-shift-atg3",
            "protocol_version": "project-one-shift-gates@2",
            "topology_manifest_sha256": draft.topology_manifest_sha256,
            "experiment_id": draft.experiment_id,
            "validation_split_sha256": draft.validation_split_sha256,
            "test_split_sha256": draft.test_split_sha256,
            "required_arm_ids": [arm.value for arm in SHIFT_THREE_ARMS],
            "arm_bindings": [item.model_dump(mode="json") for item in self._arm_bindings(draft)],
            "code_snapshot_sha256": draft.code_snapshot_sha256,
            "completion_status": "COMPLETED_WITHIN_BUDGET",
            "authority_key_id": self.key_id,
            "registration_transaction_id": str(transaction.transaction_id),
            "registration_global_commit_seq": transaction.global_commit_seq,
            "registration_request_sha256": transaction.request_sha256,
            "registration_log_head_sha256": proof.log_head_sha256,
            "registration_payload_sha256": content_sha256(registration_payload),
        }
        receipt = ShiftTuningCompletionReceipt.model_validate(
            {
                **receipt_unsigned,
                "authority_hmac_sha256": self._hmac(receipt_unsigned),
            }
        )
        return ShiftATG2Report(
            topology_manifest_sha256=draft.topology_manifest_sha256,
            experiment_id=draft.experiment_id,
            validation_split_sha256=draft.validation_split_sha256,
            test_split_sha256=draft.test_split_sha256,
            code_snapshot_sha256=draft.code_snapshot_sha256,
            ledgers=draft.ledgers,
            worker_draft_sha256=draft.draft_sha256,
            receipt=receipt,
        )

    @staticmethod
    def _draft_from_report(report: ShiftATG2Report) -> ShiftATG2Draft:
        return ShiftATG2Draft(
            topology_manifest_sha256=report.topology_manifest_sha256,
            experiment_id=report.experiment_id,
            validation_split_sha256=report.validation_split_sha256,
            test_split_sha256=report.test_split_sha256,
            code_snapshot_sha256=report.code_snapshot_sha256,
            ledgers=report.ledgers,
            draft_sha256=report.worker_draft_sha256,
        )

    def verify_atg2_report(self, report_input: object) -> bool:
        try:
            if not isinstance(report_input, ShiftATG2Report):
                report = ShiftATG2Report.model_validate(report_input)
            else:
                report = ShiftATG2Report.model_validate(report_input.model_dump(mode="json"))
            receipt = report.receipt
            if receipt.authority_key_id != self.key_id:
                return False
            draft = self._draft_from_report(report)
            registration_payload = self._registration_payload(draft)
            if receipt.registration_payload_sha256 != content_sha256(registration_payload):
                return False
            transactions = self._log.read(
                after_commit_seq=receipt.registration_global_commit_seq - 1,
                through_commit_seq=receipt.registration_global_commit_seq,
            )
            if len(transactions) != 1:
                return False
            transaction = transactions[0]
            if (
                transaction.transaction_id != receipt.registration_transaction_id
                or transaction.request_sha256 != receipt.registration_request_sha256
                or self._log.fingerprint(through_commit_seq=receipt.registration_global_commit_seq)
                != receipt.registration_log_head_sha256
            ):
                return False
            record_payload = transaction.records[0].envelope.payload
            if not isinstance(record_payload, dict):
                return False
            if record_payload.get("payload") != registration_payload:
                return False
            if record_payload.get("payload_sha256") != content_sha256(registration_payload):
                return False
            unsigned = receipt.model_dump(mode="json", exclude={"authority_hmac_sha256"})
            if not hmac.compare_digest(
                receipt.authority_hmac_sha256,
                self._hmac(unsigned),
            ):
                return False
        except (ValueError, LookupError, KeyError, IndexError):
            return False
        return True

    def authorize_test_unseal(
        self,
        report: object,
        *,
        experiment_id: str,
        validation_split_sha256: str,
        test_split_sha256: str,
    ) -> GateStateCommitProof:
        if not self.verify_atg2_report(report):
            raise ValueError("complete ATG-2 report lacks valid independent authority")
        checked = (
            report
            if isinstance(report, ShiftATG2Report)
            else ShiftATG2Report.model_validate(report)
        )
        if (
            checked.experiment_id,
            checked.validation_split_sha256,
            checked.test_split_sha256,
        ) != (experiment_id, validation_split_sha256, test_split_sha256):
            raise ValueError("ATG-2 report does not bind the sealed split")
        receipt_hash = checked.receipt.authority_receipt_sha256
        for transaction in self._log.read(
            after_commit_seq=checked.receipt.registration_global_commit_seq
        ):
            record = transaction.records[0].envelope.payload
            event_payload = record.get("payload") if isinstance(record, dict) else None
            if (
                isinstance(record, dict)
                and record.get("event_type") in {"TEST_UNSEALED", "ATG3_COMPLETED"}
                and isinstance(event_payload, dict)
                and event_payload.get("authority_receipt_sha256") == receipt_hash
            ):
                raise ValueError("this authority receipt has already advanced beyond ATG-2")
        payload: dict[str, JsonValue] = {
            "event_type": "TEST_UNSEALED",
            "authority_receipt_sha256": receipt_hash,
            "atg2_registration_transaction_id": str(checked.receipt.registration_transaction_id),
            "test_split_sha256": test_split_sha256,
            "code_snapshot_sha256": checked.code_snapshot_sha256,
        }
        _transaction, proof = self._append_event(
            event_type="TEST_UNSEALED",
            experiment_id=experiment_id,
            payload=payload,
        )
        return proof

    def commit_atg3(self, report_input: ShiftATG3Report) -> GateStateCommitProof:
        report = ShiftATG3Report.model_validate(report_input.model_dump(mode="json"))
        transactions = self._log.read(
            after_commit_seq=report.receipt.registration_global_commit_seq
        )
        matching_unseal = [
            item
            for item in transactions
            if item.global_commit_seq == report.test_unseal_commit.global_commit_seq
            and item.transaction_id == report.test_unseal_commit.transaction_id
        ]
        if len(matching_unseal) != 1:
            raise ValueError("ATG3 completion requires the committed TEST_UNSEALED event")
        receipt_hash = report.receipt.authority_receipt_sha256
        for transaction in transactions:
            record = transaction.records[0].envelope.payload
            event_payload = record.get("payload") if isinstance(record, dict) else None
            if (
                isinstance(record, dict)
                and record.get("event_type") == "ATG3_COMPLETED"
                and isinstance(event_payload, dict)
                and event_payload.get("authority_receipt_sha256") == receipt_hash
            ):
                raise ValueError("ATG3_COMPLETED has already been committed")
        payload: dict[str, JsonValue] = {
            "event_type": "ATG3_COMPLETED",
            "authority_receipt_sha256": receipt_hash,
            "test_unseal_transaction_id": str(report.test_unseal_commit.transaction_id),
            "atg3_report_sha256": content_sha256(report),
            "truth_artifact_sha256": report.test_truth_artifact.artifact_sha256,
            "prediction_artifact_sha256_by_arm": {
                arm.value: report.prediction_artifacts_by_arm[arm].artifact_sha256
                for arm in SHIFT_THREE_ARMS
            },
        }
        _transaction, proof = self._append_event(
            event_type="ATG3_COMPLETED",
            experiment_id=report.receipt.experiment_id,
            payload=payload,
        )
        return proof

    def _verify_commit_proof(
        self,
        proof: GateStateCommitProof,
        *,
        expected_payload: dict[str, JsonValue],
    ) -> bool:
        transactions = self._log.read(
            after_commit_seq=proof.global_commit_seq - 1,
            through_commit_seq=proof.global_commit_seq,
        )
        if len(transactions) != 1:
            return False
        transaction = transactions[0]
        record_payload = transaction.records[0].envelope.payload
        return bool(
            transaction.transaction_id == proof.transaction_id
            and transaction.request_sha256 == proof.request_sha256
            and self._log.fingerprint(through_commit_seq=proof.global_commit_seq)
            == proof.log_head_sha256
            and proof.event_payload_sha256 == content_sha256(expected_payload)
            and isinstance(record_payload, dict)
            and record_payload.get("event_type") == proof.event_type
            and record_payload.get("payload") == expected_payload
            and record_payload.get("payload_sha256") == proof.event_payload_sha256
        )

    def verify_complete_report(self, report_input: object) -> bool:
        from .project_one_shift_gates import ProjectOneShiftGateReport

        try:
            report = (
                report_input
                if isinstance(report_input, ProjectOneShiftGateReport)
                else ProjectOneShiftGateReport.model_validate(report_input)
            )
            if not self.verify_atg2_report(report.atg2):
                return False
            unseal_payload: dict[str, JsonValue] = {
                "event_type": "TEST_UNSEALED",
                "authority_receipt_sha256": report.atg2.receipt.authority_receipt_sha256,
                "atg2_registration_transaction_id": str(
                    report.atg2.receipt.registration_transaction_id
                ),
                "test_split_sha256": report.atg2.test_split_sha256,
                "code_snapshot_sha256": report.atg2.code_snapshot_sha256,
            }
            if not self._verify_commit_proof(
                report.atg3.test_unseal_commit,
                expected_payload=unseal_payload,
            ):
                return False
            completion_payload: dict[str, JsonValue] = {
                "event_type": "ATG3_COMPLETED",
                "authority_receipt_sha256": report.atg2.receipt.authority_receipt_sha256,
                "test_unseal_transaction_id": str(report.atg3.test_unseal_commit.transaction_id),
                "atg3_report_sha256": content_sha256(report.atg3),
                "truth_artifact_sha256": report.atg3.test_truth_artifact.artifact_sha256,
                "prediction_artifact_sha256_by_arm": {
                    arm.value: report.atg3.prediction_artifacts_by_arm[arm].artifact_sha256
                    for arm in SHIFT_THREE_ARMS
                },
            }
            return self._verify_commit_proof(
                report.atg3_completion_commit,
                expected_payload=completion_payload,
            )
        except (ValueError, LookupError, KeyError, IndexError):
            return False
