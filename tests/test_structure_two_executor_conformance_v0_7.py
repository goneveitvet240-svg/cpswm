from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from cpswm.system.attestation import Ed25519AttestationSigner
from cpswm.system.evaluation_operations.structure_two_executor_conformance_v0_7 import (
    EXECUTOR_ATTESTATION_DOMAIN,
    REPORT_PROTOCOL_ID,
    REQUIRED_CAPABILITIES,
    TEST_ARTIFACT_PROTOCOL_ID,
    TESTER_ATTESTATION_DOMAIN,
    ConformanceTestResultV07,
    ExecutorConformanceTestArtifactV07,
    verify_executor_conformance_v0_7,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUNDLE = "c" * 64
SOURCE_FILE = Path(
    "src/cpswm/system/evaluation_operations/structure_two_counterfactual_executor_v0_7.py"
)


def _evidence(
    tmp_path: Path,
) -> tuple[
    dict[str, Any],
    Path,
    Ed25519AttestationSigner,
    Ed25519AttestationSigner,
]:
    tester = Ed25519AttestationSigner.generate(key_id="independent-tester")
    executor = Ed25519AttestationSigner.generate(key_id="bounded-executor")
    nodes = {
        capability: f"tests/test_executor.py::test_{capability}"
        for capability in sorted(REQUIRED_CAPABILITIES)
    }
    test_record = ExecutorConformanceTestArtifactV07(
        protocol=TEST_ARTIFACT_PROTOCOL_ID,
        producer_source_bundle_sha256=SOURCE_BUNDLE,
        command=("uv", "run", "pytest", *nodes.values()),
        started_at_utc=datetime(2026, 9, 2, tzinfo=UTC),
        finished_at_utc=datetime(2026, 9, 2, tzinfo=UTC) + timedelta(seconds=1),
        process_exit_code=0,
        source_files_sha256={
            str(SOURCE_FILE): hashlib.sha256((ROOT / SOURCE_FILE).read_bytes()).hexdigest()
        },
        results=tuple(
            ConformanceTestResultV07(
                node_id=nodes[capability],
                capability=capability,
                outcome="passed",
                exit_code=0,
                assertion_evidence=(f"asserted:{capability}",),
            )
            for capability in sorted(REQUIRED_CAPABILITIES)
        ),
        tester_key_id=tester.key_id,
        tester_public_key_base64=tester.verifier().public_key_base64,
        tester_public_key_sha256=tester.verifier().public_key_sha256,
    )
    signed_test = test_record.model_copy(
        update={
            "tester_attestation": tester.sign(
                TESTER_ATTESTATION_DOMAIN,
                test_record.model_dump(mode="json", exclude={"tester_attestation"}),
            )
        }
    )
    test_payload = signed_test.model_dump(mode="json")
    test_payload["content_sha256"] = content_sha256(test_payload)
    test_path = tmp_path / "executor-conformance-test-artifact.json"
    test_path.write_text(json.dumps(test_payload), encoding="utf-8")

    verifier = executor.verifier()
    report_unsigned = {
        "protocol": REPORT_PROTOCOL_ID,
        "checks": {capability: True for capability in sorted(REQUIRED_CAPABILITIES)},
        "producer_source_bundle_sha256": SOURCE_BUNDLE,
        "test_evidence_artifact_sha256": hashlib.sha256(test_path.read_bytes()).hexdigest(),
        "test_evidence_content_sha256": test_payload["content_sha256"],
        "executor_key_id": verifier.key_id,
        "executor_public_key_base64": verifier.public_key_base64,
        "executor_public_key_sha256": verifier.public_key_sha256,
    }
    report = dict(report_unsigned)
    report["attestation"] = executor.sign(EXECUTOR_ATTESTATION_DOMAIN, report_unsigned).model_dump(
        mode="json"
    )
    report["content_sha256"] = content_sha256(report)
    return report, test_path, tester, executor


def test_conformance_requires_interpreted_signed_test_artifact(tmp_path: Path) -> None:
    report, test_path, tester, executor = _evidence(tmp_path)
    verified, artifact = verify_executor_conformance_v0_7(
        report,
        test_artifact_path=test_path,
        repository_root=ROOT,
        producer_source_bundle_sha256=SOURCE_BUNDLE,
        trusted_tester=tester.verifier(),
        trusted_executor=executor.verifier(),
    )
    assert verified == report
    assert {row.capability for row in artifact.results} == REQUIRED_CAPABILITIES


def test_signed_boolean_report_with_arbitrary_test_hash_is_rejected(
    tmp_path: Path,
) -> None:
    _, _, tester, executor = _evidence(tmp_path)
    fake_path = tmp_path / "arbitrary.json"
    fake_path.write_text(json.dumps({"six_true": True}), encoding="utf-8")
    verifier = executor.verifier()
    unsigned = {
        "protocol": REPORT_PROTOCOL_ID,
        "checks": {capability: True for capability in sorted(REQUIRED_CAPABILITIES)},
        "producer_source_bundle_sha256": SOURCE_BUNDLE,
        "test_evidence_artifact_sha256": hashlib.sha256(fake_path.read_bytes()).hexdigest(),
        "test_evidence_content_sha256": "f" * 64,
        "executor_key_id": verifier.key_id,
        "executor_public_key_base64": verifier.public_key_base64,
        "executor_public_key_sha256": verifier.public_key_sha256,
    }
    report = dict(unsigned)
    report["attestation"] = executor.sign(EXECUTOR_ATTESTATION_DOMAIN, unsigned).model_dump(
        mode="json"
    )
    report["content_sha256"] = content_sha256(report)
    with pytest.raises(ValueError, match="test artifact content hash mismatch"):
        verify_executor_conformance_v0_7(
            report,
            test_artifact_path=fake_path,
            repository_root=ROOT,
            producer_source_bundle_sha256=SOURCE_BUNDLE,
            trusted_tester=tester.verifier(),
            trusted_executor=executor.verifier(),
        )


def test_conformance_rejects_untrusted_or_traversing_source_inventory(
    tmp_path: Path,
) -> None:
    report, test_path, tester, executor = _evidence(tmp_path)
    payload = json.loads(test_path.read_text(encoding="utf-8"))
    payload["source_files_sha256"] = {"../outside.py": "a" * 64}
    payload.pop("content_sha256")
    payload["content_sha256"] = content_sha256(payload)
    test_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="inventory entry is malformed"):
        verify_executor_conformance_v0_7(
            report,
            test_artifact_path=test_path,
            repository_root=ROOT,
            producer_source_bundle_sha256=SOURCE_BUNDLE,
            trusted_tester=tester.verifier(),
            trusted_executor=executor.verifier(),
        )
