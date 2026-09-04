from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from cpswm.system.attestation import Ed25519AttestationSigner
from cpswm.system.evaluation_operations import (
    structure_two_executor_conformance_v0_7 as conformance_module,
)
from cpswm.system.evaluation_operations.structure_two_executor_conformance_v0_7 import (
    CANONICAL_SOURCE_FILES,
    CANONICAL_TEST_NODES,
    EXECUTOR_ATTESTATION_DOMAIN,
    REPORT_PROTOCOL_ID,
    REQUIRED_CAPABILITIES,
    TEST_ARTIFACT_PROTOCOL_ID,
    TESTER_ATTESTATION_DOMAIN,
    ConformanceTestResultV07,
    ExecutorConformanceTestArtifactV07,
    verify_executor_conformance_v0_7,
)
from cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4 import (
    compute_producer_source_bundle,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUNDLE = compute_producer_source_bundle(ROOT).content_sha256


def _evidence(
    tmp_path: Path,
) -> tuple[
    dict[str, Any],
    Path,
    Path,
    Path,
    Ed25519AttestationSigner,
    Ed25519AttestationSigner,
]:
    tester = Ed25519AttestationSigner.generate(key_id="independent-tester")
    executor = Ed25519AttestationSigner.generate(key_id="bounded-executor")
    nodes = {
        capability: CANONICAL_TEST_NODES[capability] for capability in sorted(REQUIRED_CAPABILITIES)
    }
    junit_path = tmp_path / "executor-conformance-junit.xml"
    pytest_log_path = tmp_path / "executor-conformance-pytest.log"
    command = (
        "python",
        "-m",
        "pytest",
        "-vv",
        "-p",
        "no:cacheprovider",
        "--noconftest",
        *nodes.values(),
    )
    execution_command = (
        sys.executable,
        "-m",
        "pytest",
        "-vv",
        "-p",
        "no:cacheprovider",
        "--noconftest",
        *nodes.values(),
        "--junitxml",
        str(junit_path),
    )
    started = datetime.now(UTC)
    process = subprocess.run(
        execution_command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    finished = datetime.now(UTC)
    pytest_log_path.write_text(process.stdout + process.stderr, encoding="utf-8")
    assert process.returncode == 0
    test_record = ExecutorConformanceTestArtifactV07(
        protocol=TEST_ARTIFACT_PROTOCOL_ID,
        producer_source_bundle_sha256=SOURCE_BUNDLE,
        command=command,
        started_at_utc=started,
        finished_at_utc=finished,
        process_exit_code=0,
        repository_working_directory=str(ROOT),
        junit_artifact_file_sha256=hashlib.sha256(junit_path.read_bytes()).hexdigest(),
        pytest_log_file_sha256=hashlib.sha256(pytest_log_path.read_bytes()).hexdigest(),
        source_files_sha256={
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in sorted(CANONICAL_SOURCE_FILES)
        },
        results=tuple(
            ConformanceTestResultV07(
                node_id=nodes[capability],
                capability=capability,
                outcome="passed",
                exit_code=0,
                assertion_evidence=(
                    content_sha256(
                        {
                            "node_id": nodes[capability],
                            "capability": capability,
                            "producer_source_bundle_sha256": SOURCE_BUNDLE,
                            "test_result": "passed",
                        }
                    ),
                ),
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
    return report, test_path, junit_path, pytest_log_path, tester, executor


def test_conformance_requires_interpreted_signed_test_artifact(tmp_path: Path) -> None:
    report, test_path, junit_path, pytest_log_path, tester, executor = _evidence(tmp_path)
    verified, artifact = verify_executor_conformance_v0_7(
        report,
        test_artifact_path=test_path,
        repository_root=ROOT,
        producer_source_bundle_sha256=SOURCE_BUNDLE,
        trusted_tester=tester.verifier(),
        trusted_executor=executor.verifier(),
        junit_artifact_path=junit_path,
        pytest_log_path=pytest_log_path,
    )
    assert verified == report
    assert {row.capability for row in artifact.results} == REQUIRED_CAPABILITIES


def test_signed_complete_artifacts_cannot_replace_verifier_reexecution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report, test_path, junit_path, pytest_log_path, tester, executor = _evidence(tmp_path)

    def reject_reexecution(_root: Path, _nodes: tuple[str, ...]) -> None:
        raise ValueError("forced verifier re-execution failure")

    monkeypatch.setattr(
        conformance_module,
        "_rerun_canonical_conformance_tests",
        reject_reexecution,
    )
    with pytest.raises(ValueError, match="forced verifier re-execution failure"):
        verify_executor_conformance_v0_7(
            report,
            test_artifact_path=test_path,
            repository_root=ROOT,
            producer_source_bundle_sha256=SOURCE_BUNDLE,
            trusted_tester=tester.verifier(),
            trusted_executor=executor.verifier(),
            junit_artifact_path=junit_path,
            pytest_log_path=pytest_log_path,
        )


def test_signed_boolean_report_with_arbitrary_test_hash_is_rejected(
    tmp_path: Path,
) -> None:
    _, _, junit_path, pytest_log_path, tester, executor = _evidence(tmp_path)
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
            junit_artifact_path=junit_path,
            pytest_log_path=pytest_log_path,
        )


def test_conformance_rejects_untrusted_or_traversing_source_inventory(
    tmp_path: Path,
) -> None:
    report, test_path, junit_path, pytest_log_path, tester, executor = _evidence(tmp_path)
    payload = json.loads(test_path.read_text(encoding="utf-8"))
    payload["source_files_sha256"] = {"../outside.py": "a" * 64}
    payload.pop("content_sha256")
    payload["content_sha256"] = content_sha256(payload)
    test_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="source inventory is not canonical"):
        verify_executor_conformance_v0_7(
            report,
            test_artifact_path=test_path,
            repository_root=ROOT,
            producer_source_bundle_sha256=SOURCE_BUNDLE,
            trusted_tester=tester.verifier(),
            trusted_executor=executor.verifier(),
            junit_artifact_path=junit_path,
            pytest_log_path=pytest_log_path,
        )


def test_verifier_reexecution_does_not_load_repository_conftest_hook(
    tmp_path: Path,
) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    test_file = tests / "test_structure_two_external_reference_cores_v0_6.py"
    test_file.write_text(
        "def test_active_dreaming_commits_only_after_attested_execution(): assert False\n"
        "def test_active_dreaming_rejects_untrusted_executor(): assert False\n"
        "def test_active_dreaming_rejects_zero_cluster_false_positive(): assert False\n"
        "def test_active_dreaming_rejects_rule_binding_replay(): assert False\n"
        "def test_counterfactual_program_resource_bounds_are_enforced(): assert False\n"
        "def test_counterfactual_overflow_produces_signed_failure_receipt(): assert False\n",
        encoding="utf-8",
    )
    (tmp_path / "conftest.py").write_text(
        "import pytest\n"
        "@pytest.hookimpl(hookwrapper=True, tryfirst=True)\n"
        "def pytest_runtest_makereport(item, call):\n"
        "    outcome = yield\n"
        "    outcome.get_result().outcome = 'passed'\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="re-execution failed"):
        conformance_module._rerun_canonical_conformance_tests(
            tmp_path,
            tuple(CANONICAL_TEST_NODES[key] for key in sorted(REQUIRED_CAPABILITIES)),
        )


def test_verifier_reexecution_does_not_load_repository_sitecustomize_hook(
    tmp_path: Path,
) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    test_file = tests / "test_structure_two_external_reference_cores_v0_6.py"
    test_file.write_text(
        "def test_active_dreaming_commits_only_after_attested_execution(): assert False\n"
        "def test_active_dreaming_rejects_untrusted_executor(): assert False\n"
        "def test_active_dreaming_rejects_zero_cluster_false_positive(): assert False\n"
        "def test_active_dreaming_rejects_rule_binding_replay(): assert False\n"
        "def test_counterfactual_program_resource_bounds_are_enforced(): assert False\n"
        "def test_counterfactual_overflow_produces_signed_failure_receipt(): assert False\n",
        encoding="utf-8",
    )
    source = tmp_path / "src"
    source.mkdir()
    marker = tmp_path / "sitecustomize-loaded"
    (source / "sitecustomize.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('loaded', encoding='utf-8')\n"
        "os.environ['PYTEST_ADDOPTS'] = '-p startup_attack_plugin'\n",
        encoding="utf-8",
    )
    (source / "startup_attack_plugin.py").write_text(
        "import pytest\n"
        "@pytest.hookimpl(hookwrapper=True, tryfirst=True)\n"
        "def pytest_runtest_makereport(item, call):\n"
        "    outcome = yield\n"
        "    outcome.get_result().outcome = 'passed'\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="re-execution failed"):
        conformance_module._rerun_canonical_conformance_tests(
            tmp_path,
            tuple(CANONICAL_TEST_NODES[key] for key in sorted(REQUIRED_CAPABILITIES)),
        )
    assert not marker.exists()
