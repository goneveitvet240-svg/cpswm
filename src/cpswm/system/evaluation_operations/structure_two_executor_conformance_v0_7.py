"""Independent, machine-readable executor conformance evidence for v0.7."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationVerifier,
)
from cpswm.system.reproducibility import content_sha256

TEST_ARTIFACT_PROTOCOL_ID = "structure-two-executor-conformance-test-artifact@0.7"
REPORT_PROTOCOL_ID = "structure-two-executor-conformance@0.7"
TESTER_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.executor_conformance.tester.v0.7"
EXECUTOR_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.executor_conformance.executor.v0.7"
REQUIRED_CAPABILITIES = frozenset(
    {
        "content_bound_scenario_execution_verified",
        "independent_ed25519_receipt_verified",
        "zero_cluster_fails_closed",
        "cluster_failure_rule_binding_verified",
        "resource_bounds_verified",
        "deterministic_failures_signed",
    }
)


class ConformanceTestResultV07(ContractModel):
    node_id: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    outcome: str = Field(pattern=r"^passed$")
    exit_code: int = Field(ge=0, le=0)
    assertion_evidence: tuple[str, ...] = Field(min_length=1)


class ExecutorConformanceTestArtifactV07(ContractModel):
    protocol: str = Field(pattern=r"^structure-two-executor-conformance-test-artifact@0\.7$")
    producer_source_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    command: tuple[str, ...] = Field(min_length=4)
    started_at_utc: datetime
    finished_at_utc: datetime
    process_exit_code: int = Field(ge=0, le=0)
    source_files_sha256: dict[str, str]
    results: tuple[ConformanceTestResultV07, ...] = Field(min_length=6)
    tester_key_id: str = Field(min_length=1)
    tester_public_key_base64: str = Field(min_length=1)
    tester_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tester_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_semantics(self) -> ExecutorConformanceTestArtifactV07:
        if self.finished_at_utc <= self.started_at_utc:
            raise ValueError("conformance test finish time must follow start time")
        if tuple(self.command[:3]) != ("uv", "run", "pytest"):
            raise ValueError("conformance test command must invoke uv run pytest")
        capabilities = {item.capability for item in self.results}
        if capabilities != REQUIRED_CAPABILITIES or len(self.results) != len(REQUIRED_CAPABILITIES):
            raise ValueError("conformance artifact capability coverage is incomplete")
        if len({item.node_id for item in self.results}) != len(self.results):
            raise ValueError("conformance test node IDs must be unique")
        if any(item.node_id not in self.command for item in self.results):
            raise ValueError("conformance command does not name every reported test")
        if not self.source_files_sha256:
            raise ValueError("conformance artifact source-file inventory is empty")
        for relative, digest in self.source_files_sha256.items():
            path = Path(relative)
            if (
                path.is_absolute()
                or ".." in path.parts
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ValueError("conformance source-file inventory entry is malformed")
        return self


def _test_payload(record: ExecutorConformanceTestArtifactV07) -> dict[str, Any]:
    return record.model_dump(mode="json", exclude={"tester_attestation"})


def verify_executor_conformance_v0_7(
    report: Mapping[str, Any],
    *,
    test_artifact_path: Path,
    repository_root: Path,
    producer_source_bundle_sha256: str,
    trusted_tester: Ed25519AttestationVerifier,
    trusted_executor: Ed25519AttestationVerifier,
) -> tuple[dict[str, Any], ExecutorConformanceTestArtifactV07]:
    test_payload = json.loads(test_artifact_path.read_text(encoding="utf-8"))
    if not isinstance(test_payload, dict):
        raise ValueError("executor-conformance test artifact must be a JSON object")
    test_unsigned = dict(test_payload)
    test_stored = test_unsigned.pop("content_sha256", None)
    if not isinstance(test_stored, str) or content_sha256(test_unsigned) != test_stored:
        raise ValueError("executor-conformance test artifact content hash mismatch")
    record = ExecutorConformanceTestArtifactV07.model_validate(test_unsigned)
    if record.producer_source_bundle_sha256 != producer_source_bundle_sha256:
        raise ValueError("executor-conformance test source-bundle binding mismatch")
    if (
        record.tester_key_id != trusted_tester.key_id
        or record.tester_public_key_base64 != trusted_tester.public_key_base64
        or record.tester_public_key_sha256 != trusted_tester.public_key_sha256
    ):
        raise AttestationError("executor-conformance artifact used an untrusted tester")
    for relative, expected_sha256 in record.source_files_sha256.items():
        path = repository_root / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
            raise ValueError("executor-conformance source-file inventory mismatch")
    trusted_tester.verify(
        TESTER_ATTESTATION_DOMAIN, _test_payload(record), record.tester_attestation
    )

    report_unsigned = dict(report)
    report_stored = report_unsigned.pop("content_sha256", None)
    if not isinstance(report_stored, str) or content_sha256(report_unsigned) != report_stored:
        raise ValueError("executor-conformance report content hash mismatch")
    raw_attestation = report_unsigned.pop("attestation", None)
    if not isinstance(raw_attestation, dict):
        raise ValueError("executor-conformance report lacks an Ed25519 attestation")
    if report_unsigned.get("protocol") != REPORT_PROTOCOL_ID:
        raise ValueError("executor-conformance report protocol mismatch")
    derived_checks = {capability: True for capability in sorted(REQUIRED_CAPABILITIES)}
    if report_unsigned.get("checks") != derived_checks:
        raise ValueError("executor-conformance checks are not derived from test results")
    if (
        report_unsigned.get("producer_source_bundle_sha256") != producer_source_bundle_sha256
        or report_unsigned.get("test_evidence_artifact_sha256")
        != hashlib.sha256(test_artifact_path.read_bytes()).hexdigest()
        or report_unsigned.get("test_evidence_content_sha256") != test_stored
    ):
        raise ValueError("executor-conformance report artifact binding mismatch")
    if (
        report_unsigned.get("executor_key_id") != trusted_executor.key_id
        or report_unsigned.get("executor_public_key_base64") != trusted_executor.public_key_base64
        or report_unsigned.get("executor_public_key_sha256") != trusted_executor.public_key_sha256
    ):
        raise AttestationError("executor-conformance report used an untrusted executor")
    trusted_executor.verify(
        EXECUTOR_ATTESTATION_DOMAIN,
        report_unsigned,
        Attestation.model_validate(raw_attestation),
    )
    return dict(report), record


__all__ = [
    "EXECUTOR_ATTESTATION_DOMAIN",
    "REPORT_PROTOCOL_ID",
    "REQUIRED_CAPABILITIES",
    "TESTER_ATTESTATION_DOMAIN",
    "TEST_ARTIFACT_PROTOCOL_ID",
    "ExecutorConformanceTestArtifactV07",
    "verify_executor_conformance_v0_7",
]
