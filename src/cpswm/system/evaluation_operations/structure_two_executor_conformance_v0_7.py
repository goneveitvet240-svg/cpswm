"""Independent, machine-readable executor conformance evidence for v0.7."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
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
from cpswm.system.evaluation_operations.structure_two_isolated_pytest_v0_8 import (
    run_isolated_pytest_v0_8,
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
CANONICAL_TEST_NODES: Mapping[str, str] = {
    "content_bound_scenario_execution_verified": (
        "tests/test_structure_two_external_reference_cores_v0_6.py::"
        "test_active_dreaming_commits_only_after_attested_execution"
    ),
    "independent_ed25519_receipt_verified": (
        "tests/test_structure_two_external_reference_cores_v0_6.py::"
        "test_active_dreaming_rejects_untrusted_executor"
    ),
    "zero_cluster_fails_closed": (
        "tests/test_structure_two_external_reference_cores_v0_6.py::"
        "test_active_dreaming_rejects_zero_cluster_false_positive"
    ),
    "cluster_failure_rule_binding_verified": (
        "tests/test_structure_two_external_reference_cores_v0_6.py::"
        "test_active_dreaming_rejects_rule_binding_replay"
    ),
    "resource_bounds_verified": (
        "tests/test_structure_two_external_reference_cores_v0_6.py::"
        "test_counterfactual_program_resource_bounds_are_enforced"
    ),
    "deterministic_failures_signed": (
        "tests/test_structure_two_external_reference_cores_v0_6.py::"
        "test_counterfactual_overflow_produces_signed_failure_receipt"
    ),
}
CANONICAL_ORDERED_TEST_NODES = tuple(
    CANONICAL_TEST_NODES[capability] for capability in sorted(REQUIRED_CAPABILITIES)
)
CANONICAL_SOURCE_FILES = frozenset(
    {
        "src/cpswm/system/evaluation_operations/structure_two_counterfactual_executor_v0_7.py",
        "src/cpswm/system/evaluation_operations/structure_two_external_inputs_v0_6.py",
        "src/cpswm/system/evaluation_operations/structure_two_external_reference_cores_v0_6.py",
        "src/cpswm/system/evaluation_operations/structure_two_signed_gate_b_v0_6.py",
        "tests/test_structure_two_external_reference_cores_v0_6.py",
    }
)


def _rerun_canonical_conformance_tests(
    repository_root: Path,
    expected_nodes: tuple[str, ...],
) -> None:
    try:
        root = repository_root.resolve(strict=True)
        resolved_nodes: list[str] = []
        for node in expected_nodes:
            relative_file, separator, selector = node.partition("::")
            relative_path = Path(relative_file)
            if (
                not separator
                or not selector
                or relative_path.is_absolute()
                or ".." in relative_path.parts
            ):
                raise ValueError("executor-conformance test node escapes the trusted repository")
            test_file = (root / relative_path).resolve(strict=True)
            test_file.relative_to(root)
            resolved_nodes.append(f"{test_file}::{selector}")
        with tempfile.TemporaryDirectory(prefix="cpswm-conformance-") as directory:
            isolated_root = Path(directory)
            junit_path = isolated_root / "junit.xml"
            process = run_isolated_pytest_v0_8(
                nodes=resolved_nodes,
                working_directory=isolated_root,
                junit_path=junit_path,
                timeout_seconds=180,
                trusted_source_root=root / "src",
                verbose=True,
            )
            if process.returncode != 0:
                raise ValueError("executor-conformance verifier re-execution failed")
            junit_root = ET.fromstring(junit_path.read_bytes())
    except (OSError, ValueError, subprocess.SubprocessError, ET.ParseError) as exc:
        raise ValueError("executor-conformance verifier re-execution failed") from exc
    testcases = tuple(junit_root.iter("testcase"))
    if len(testcases) != len(expected_nodes) or any(
        any(testcase.find(name) is not None for name in ("failure", "error", "skipped"))
        for testcase in testcases
    ):
        raise ValueError("executor-conformance verifier re-execution was not all passing")
    expected_names = tuple(node.rsplit("::", maxsplit=1)[-1] for node in expected_nodes)
    if tuple(testcase.get("name") for testcase in testcases) != expected_names:
        raise ValueError("executor-conformance verifier re-executed the wrong test set")


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
    repository_working_directory: str = Field(min_length=1)
    junit_artifact_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pytest_log_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
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
        if self.command != (
            "python",
            "-m",
            "pytest",
            "-vv",
            "-p",
            "no:cacheprovider",
            "--noconftest",
            *CANONICAL_ORDERED_TEST_NODES,
        ):
            raise ValueError("conformance test command is not the frozen argv")
        capabilities = {item.capability for item in self.results}
        if capabilities != REQUIRED_CAPABILITIES or len(self.results) != len(REQUIRED_CAPABILITIES):
            raise ValueError("conformance artifact capability coverage is incomplete")
        if len({item.node_id for item in self.results}) != len(self.results):
            raise ValueError("conformance test node IDs must be unique")
        if any(item.node_id not in self.command for item in self.results):
            raise ValueError("conformance command does not name every reported test")
        if {item.capability: item.node_id for item in self.results} != dict(CANONICAL_TEST_NODES):
            raise ValueError("conformance artifact changed the canonical test matrix")
        if set(self.source_files_sha256) != CANONICAL_SOURCE_FILES:
            raise ValueError("conformance artifact source inventory is not canonical")
        for relative, digest in self.source_files_sha256.items():
            path = Path(relative)
            if (
                path.is_absolute()
                or ".." in path.parts
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ValueError("conformance source-file inventory entry is malformed")
        if any(
            len(item.assertion_evidence) != 1
            or item.assertion_evidence[0]
            != content_sha256(
                {
                    "node_id": item.node_id,
                    "capability": item.capability,
                    "producer_source_bundle_sha256": (self.producer_source_bundle_sha256),
                    "test_result": "passed",
                }
            )
            for item in self.results
        ):
            raise ValueError("conformance assertion evidence must be content digests")
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
    junit_artifact_path: Path,
    pytest_log_path: Path,
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
    if Path(record.repository_working_directory).resolve() != repository_root.resolve():
        raise ValueError("executor-conformance test used the wrong repository root")
    if (
        hashlib.sha256(junit_artifact_path.read_bytes()).hexdigest()
        != record.junit_artifact_file_sha256
        or hashlib.sha256(pytest_log_path.read_bytes()).hexdigest() != record.pytest_log_file_sha256
    ):
        raise ValueError("executor-conformance pytest artifact hash mismatch")
    try:
        junit_root = ET.fromstring(junit_artifact_path.read_bytes())
    except (OSError, ET.ParseError) as exc:
        raise ValueError("executor-conformance JUnit artifact is invalid") from exc
    junit_test_names: list[str] = []
    for testcase in junit_root.iter("testcase"):
        if any(testcase.find(name) is not None for name in ("failure", "error", "skipped")):
            raise ValueError("executor-conformance JUnit contains a non-passing test")
        name = testcase.get("name")
        if not name:
            raise ValueError("executor-conformance JUnit lacks test names")
        junit_test_names.append(name)
    expected_nodes = [record_node.node_id for record_node in record.results]
    if junit_test_names != [node.rsplit("::", maxsplit=1)[-1] for node in expected_nodes]:
        raise ValueError("executor-conformance JUnit test set differs from the report")
    pytest_log = pytest_log_path.read_text(encoding="utf-8")
    if not all(node in pytest_log for node in expected_nodes) or (
        f"{len(expected_nodes)} passed" not in pytest_log
    ):
        raise ValueError("executor-conformance pytest log lacks the exact passing run")
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
    _rerun_canonical_conformance_tests(repository_root.resolve(), CANONICAL_ORDERED_TEST_NODES)
    if any(
        hashlib.sha256((repository_root / relative).read_bytes()).hexdigest() != expected_sha256
        for relative, expected_sha256 in record.source_files_sha256.items()
    ):
        raise ValueError("executor-conformance sources changed during verifier re-execution")
    return dict(report), record


__all__ = [
    "CANONICAL_ORDERED_TEST_NODES",
    "EXECUTOR_ATTESTATION_DOMAIN",
    "REPORT_PROTOCOL_ID",
    "REQUIRED_CAPABILITIES",
    "TESTER_ATTESTATION_DOMAIN",
    "TEST_ARTIFACT_PROTOCOL_ID",
    "ExecutorConformanceTestArtifactV07",
    "verify_executor_conformance_v0_7",
]
