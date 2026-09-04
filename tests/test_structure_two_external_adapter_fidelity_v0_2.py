from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations import (
    structure_two_external_adapter_fidelity_v0_2 as fidelity_module,
)
from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity_v0_2 import (
    EVIDENCE_ATTESTATION_DOMAIN,
    EXECUTION_ATTESTATION_DOMAIN,
    ExternalEvidenceArtifactPaths,
    ExternalMethodEvidence,
    ExternalMethodSpecification,
    attested_external_method_evidence_payload,
    default_external_method_specifications_v0_2,
    external_artifact_sha256,
    run_external_fidelity_gate_v0_2,
    run_fidelity_tests_and_make_receipt_v0_7,
)
from cpswm.system.reproducibility import content_sha256

HASH = "a" * 64
MANIFEST_SHA256 = "b" * 64
PRODUCER_RUN_ID = "fidelity-run"
INPUT_BUNDLE_SHA256 = "c" * 64
SIGNER = Ed25519AttestationSigner.generate(key_id="external-reviewer")
EXECUTOR = Ed25519AttestationSigner.generate(key_id="external-executor")
COMPONENT_NODE = "test_fidelity.py::test_component_parity"
NATIVE_NODE = "test_fidelity.py::test_native_protocol"
ADAPTATION_NODE = "test_fidelity.py::test_adaptation_parity"


def _spec(
    *,
    code_required: bool = False,
    test_bundle_sha256: str = "d" * 64,
    official_build_command: tuple[str, ...] = (),
) -> ExternalMethodSpecification:
    return ExternalMethodSpecification(
        arm="external",
        method="External Method",
        native_domain="native task",
        primary_source_url="https://example.org/paper",
        required_native_components=("component-a", "component-b"),
        required_adaptation_inputs=("input-a",),
        official_code_required=code_required,
        component_parity_test_nodes=(COMPONENT_NODE,),
        native_protocol_test_nodes=(NATIVE_NODE,),
        adaptation_parity_test_nodes=(ADAPTATION_NODE,),
        fidelity_test_bundle_sha256=test_bundle_sha256,
        official_build_command=official_build_command,
    )


def _artifact_paths(tmp_path: Path) -> ExternalEvidenceArtifactPaths:
    paths = ExternalEvidenceArtifactPaths(
        primary_source=tmp_path / "paper.pdf",
        implementation_bundle=tmp_path / "implementation-bundle",
        component_parity_receipt=tmp_path / "component.json",
        component_parity_execution_log=tmp_path / "component.log",
        native_protocol_recheck_receipt=tmp_path / "native.json",
        native_protocol_execution_log=tmp_path / "native.log",
        adaptation_contract=tmp_path / "adaptation.json",
        adaptation_parity_receipt=tmp_path / "adaptation-parity.json",
        adaptation_parity_execution_log=tmp_path / "adaptation-parity.log",
        fidelity_test_bundle=tmp_path / "trusted-fidelity-tests",
    )
    paths.primary_source.write_bytes(b"paper")
    paths.implementation_bundle.mkdir()
    assert paths.fidelity_test_bundle is not None
    paths.fidelity_test_bundle.mkdir()
    (paths.implementation_bundle / "implementation.py").write_text(
        "IMPLEMENTATION = 'bound'\n", encoding="utf-8"
    )
    (paths.fidelity_test_bundle / "test_fidelity.py").write_text(
        "import importlib.util\n"
        "import os\n"
        "from pathlib import Path\n\n"
        "_path = Path(os.environ['CPSWM_IMPLEMENTATION_BUNDLE']) / 'implementation.py'\n"
        "_spec = importlib.util.spec_from_file_location('candidate_implementation', _path)\n"
        "assert _spec is not None and _spec.loader is not None\n"
        "_module = importlib.util.module_from_spec(_spec)\n"
        "_spec.loader.exec_module(_module)\n"
        "IMPLEMENTATION = _module.IMPLEMENTATION\n\n"
        "def test_component_parity():\n"
        "    assert IMPLEMENTATION == 'bound'\n\n"
        "def test_native_protocol():\n"
        "    assert IMPLEMENTATION == 'bound'\n\n"
        "def test_adaptation_parity():\n"
        "    assert IMPLEMENTATION == 'bound'\n",
        encoding="utf-8",
    )
    implementation_sha256 = external_artifact_sha256(paths.implementation_bundle)
    test_bundle_sha256 = external_artifact_sha256(paths.fidelity_test_bundle)
    source_sha256 = external_artifact_sha256(paths.primary_source)
    contract = {
        "protocol": "structure-two-external-adaptation-contract@0.6",
        "arm": "external",
        "method": "External Method",
        "primary_source_url": "https://example.org/paper",
        "immutable_manifest_sha256": MANIFEST_SHA256,
        "producer_run_id": PRODUCER_RUN_ID,
        "input_bundle_sha256": INPUT_BUNDLE_SHA256,
        "primary_source_sha256": source_sha256,
        "implementation_bundle_sha256": implementation_sha256,
        "fidelity_test_bundle_sha256": test_bundle_sha256,
        "fidelity_test_environment_protocol": ("structure-two-frozen-pytest-environment@0.8"),
        "fidelity_test_nodes": {
            "component_parity": [COMPONENT_NODE],
            "native_protocol": [NATIVE_NODE],
            "adaptation_parity": [ADAPTATION_NODE],
        },
        "required_adaptation_inputs": ["input-a"],
        "input_mappings": [
            {
                "required_input": "input-a",
                "typed_input_field": "external.input_a",
                "transformation": "identity",
            }
        ],
    }
    contract["content_sha256"] = content_sha256(contract)
    paths.adaptation_contract.write_text(json.dumps(contract), encoding="utf-8")
    contract_sha256 = external_artifact_sha256(paths.adaptation_contract)

    for receipt_path, log_path, protocol, success_field, node in (
        (
            paths.component_parity_receipt,
            paths.component_parity_execution_log,
            "structure-two-component-parity-receipt@0.6",
            "component_parity_passed",
            COMPONENT_NODE,
        ),
        (
            paths.native_protocol_recheck_receipt,
            paths.native_protocol_execution_log,
            "structure-two-native-protocol-recheck@0.6",
            "native_protocol_reproduction_passed",
            NATIVE_NODE,
        ),
        (
            paths.adaptation_parity_receipt,
            paths.adaptation_parity_execution_log,
            "structure-two-adaptation-parity-receipt@0.6",
            "adaptation_parity_passed",
            ADAPTATION_NODE,
        ),
    ):
        run_fidelity_tests_and_make_receipt_v0_7(
            receipt_path=receipt_path,
            execution_log_path=log_path,
            implementation_bundle_path=paths.implementation_bundle,
            trusted_test_bundle_path=paths.fidelity_test_bundle,
            arm="external",
            receipt_protocol=protocol,
            success_field=success_field,
            expected_test_nodes=(node,),
            immutable_manifest_sha256=MANIFEST_SHA256,
            producer_run_id=PRODUCER_RUN_ID,
            input_bundle_sha256=INPUT_BUNDLE_SHA256,
            primary_source_sha256=source_sha256,
            implementation_bundle_sha256=implementation_sha256,
            fidelity_test_bundle_sha256=test_bundle_sha256,
            adaptation_contract_sha256=contract_sha256,
            executor=EXECUTOR,
        )
    return paths


def _complete_evidence(
    tmp_path: Path,
) -> tuple[ExternalMethodEvidence, ExternalEvidenceArtifactPaths]:
    verifier = SIGNER.verifier()
    paths = _artifact_paths(tmp_path)
    unsigned = ExternalMethodEvidence(
        arm="external",
        primary_source_sha256=external_artifact_sha256(paths.primary_source),
        implementation_bundle_sha256=external_artifact_sha256(paths.implementation_bundle),
        verified_native_components=("component-a", "component-b"),
        component_parity_receipt_sha256=external_artifact_sha256(paths.component_parity_receipt),
        native_protocol_recheck_receipt_sha256=external_artifact_sha256(
            paths.native_protocol_recheck_receipt
        ),
        adaptation_contract_sha256=external_artifact_sha256(paths.adaptation_contract),
        adaptation_parity_receipt_sha256=external_artifact_sha256(paths.adaptation_parity_receipt),
        reviewer_key_id=verifier.key_id,
        reviewer_public_key_base64=verifier.public_key_base64,
        reviewer_public_key_sha256=verifier.public_key_sha256,
    )
    return (
        replace(
            unsigned,
            attestation=SIGNER.sign(
                EVIDENCE_ATTESTATION_DOMAIN,
                attested_external_method_evidence_payload(unsigned),
            ),
        ),
        paths,
    )


def _run(
    evidence: ExternalMethodEvidence,
    paths: ExternalEvidenceArtifactPaths,
) -> dict[str, object]:
    verifier = SIGNER.verifier()
    executor_verifier = EXECUTOR.verifier()
    assert paths.fidelity_test_bundle is not None
    return run_external_fidelity_gate_v0_2(
        (_spec(test_bundle_sha256=external_artifact_sha256(paths.fidelity_test_bundle)),),
        {"external": evidence},
        artifact_paths_by_arm={"external": paths},
        trusted_reviewer_key_id=verifier.key_id,
        trusted_reviewer_public_key_sha256=verifier.public_key_sha256,
        trusted_executor_key_id=executor_verifier.key_id,
        trusted_executor_public_key_sha256=executor_verifier.public_key_sha256,
        enforce_canonical_catalog=False,
        expected_manifest_sha256=MANIFEST_SHA256,
        expected_producer_run_id=PRODUCER_RUN_ID,
        expected_input_bundle_sha256_by_arm={"external": INPUT_BUNDLE_SHA256},
        expected_primary_source_sha256_by_arm={"external": evidence.primary_source_sha256 or ""},
    )


def test_missing_evidence_fails_closed_with_machine_readable_gaps() -> None:
    report = run_external_fidelity_gate_v0_2((_spec(),), {}, enforce_canonical_catalog=False)
    row = report["method_results"][0]
    assert report["external_fidelity_gate_passed"] is False
    assert row["native_fidelity_passed"] is False
    assert row["adaptation_fidelity_passed"] is False
    assert "native_published_protocol_rechecked" in row["missing_requirements"]


def test_native_pass_does_not_authorize_cross_domain_adaptation(tmp_path: Path) -> None:
    complete, paths = _complete_evidence(tmp_path)
    evidence = replace(
        complete,
        adaptation_contract_sha256=None,
        adaptation_parity_receipt_sha256=None,
    )
    unsigned = replace(evidence, attestation=None)
    evidence = replace(
        unsigned,
        attestation=SIGNER.sign(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(unsigned),
        ),
    )
    report = _run(evidence, paths)
    row = report["method_results"][0]
    assert row["diagnostic_native_fidelity_passed"] is True
    assert row["native_fidelity_passed"] is False
    assert row["adaptation_fidelity_passed"] is False
    assert report["external_method_efficacy_comparison_allowed"] is False


def test_complete_content_bound_evidence_is_only_a_combined_gate_precondition(
    tmp_path: Path,
) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    report = _run(evidence, paths)
    assert report["protocol"].endswith("-diagnostic@0.2")
    assert report["canonical_protocol_enforced"] is False
    assert report["diagnostic_native_fidelity_passed"] is True
    assert report["diagnostic_adaptation_fidelity_passed"] is True
    assert report["native_fidelity_gate_passed"] is False
    assert report["adaptation_fidelity_gate_passed"] is False
    assert report["fidelity_precondition_for_combined_authorization_passed"] is False
    assert report["external_method_efficacy_comparison_allowed"] is False


def test_signed_structured_success_cannot_replace_verifier_reexecution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    monkeypatch.setattr(
        fidelity_module,
        "_rerun_fidelity_tests",
        lambda _bundle, _tests, _nodes, _test_sha: False,
    )
    report = _run(evidence, paths)
    assert report["native_fidelity_gate_passed"] is False
    assert report["adaptation_fidelity_gate_passed"] is False
    assert report["fidelity_precondition_for_combined_authorization_passed"] is False


def test_reviewer_signature_without_independent_executor_anchor_cannot_pass(
    tmp_path: Path,
) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    verifier = SIGNER.verifier()
    report = run_external_fidelity_gate_v0_2(
        (_spec(),),
        {"external": evidence},
        artifact_paths_by_arm={"external": paths},
        trusted_reviewer_key_id=verifier.key_id,
        trusted_reviewer_public_key_sha256=verifier.public_key_sha256,
        enforce_canonical_catalog=False,
    )
    assert report["external_fidelity_gate_passed"] is False


def test_reviewer_and_executor_cannot_reuse_one_trust_key(tmp_path: Path) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    verifier = SIGNER.verifier()
    with pytest.raises(ValueError, match="must be independent keys"):
        run_external_fidelity_gate_v0_2(
            (_spec(),),
            {"external": evidence},
            artifact_paths_by_arm={"external": paths},
            trusted_reviewer_key_id=verifier.key_id,
            trusted_reviewer_public_key_sha256=verifier.public_key_sha256,
            trusted_executor_key_id=verifier.key_id,
            trusted_executor_public_key_sha256=verifier.public_key_sha256,
            enforce_canonical_catalog=False,
        )


def test_component_subset_cannot_be_mislabeled_as_complete(tmp_path: Path) -> None:
    complete, paths = _complete_evidence(tmp_path)
    evidence = replace(complete, verified_native_components=("component-a",))
    unsigned = replace(evidence, attestation=None)
    evidence = replace(
        unsigned,
        attestation=SIGNER.sign(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(unsigned),
        ),
    )
    report = _run(evidence, paths)
    assert report["method_results"][0]["native_fidelity_passed"] is False


def test_candidate_self_signed_evidence_cannot_impersonate_reviewer(tmp_path: Path) -> None:
    attacker = Ed25519AttestationSigner.generate(key_id=SIGNER.key_id)
    evidence, paths = _complete_evidence(tmp_path)
    attacker_verifier = attacker.verifier()
    unsigned = replace(
        evidence,
        reviewer_public_key_base64=attacker_verifier.public_key_base64,
        reviewer_public_key_sha256=attacker_verifier.public_key_sha256,
        attestation=None,
    )
    forged = replace(
        unsigned,
        attestation=attacker.sign(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(unsigned),
        ),
    )
    with pytest.raises(AttestationError, match="trust-anchor mismatch"):
        _run(forged, paths)


def test_modifying_reviewed_evidence_breaks_signature(tmp_path: Path) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    modified = replace(evidence, adaptation_contract_sha256="b" * 64)
    with pytest.raises(AttestationError, match="signature does not match"):
        _run(modified, paths)


def test_default_catalog_retains_all_six_external_arms_and_has_no_empty_specs() -> None:
    specifications = default_external_method_specifications_v0_2()
    assert {item.arm for item in specifications} == {
        "corrected_amg",
        "o_star_matched",
        "active_dreaming_matched",
        "auto_dreamer_matched",
        "trustmem_matched",
        "brainctl_matched",
    }
    assert all(item.required_native_components for item in specifications)
    assert all(item.required_adaptation_inputs for item in specifications)


def test_one_arm_catalog_cannot_pass_the_formal_fidelity_gate() -> None:
    with pytest.raises(ValueError, match="canonical six-arm catalog"):
        run_external_fidelity_gate_v0_2((_spec(),), {})


def test_signed_fictional_hashes_do_not_verify_real_artifacts(tmp_path: Path) -> None:
    _complete, paths = _complete_evidence(tmp_path)
    verifier = SIGNER.verifier()
    unsigned = ExternalMethodEvidence(
        arm="external",
        primary_source_sha256=HASH,
        implementation_bundle_sha256=HASH,
        verified_native_components=("component-a", "component-b"),
        component_parity_receipt_sha256=HASH,
        native_protocol_recheck_receipt_sha256=HASH,
        adaptation_contract_sha256=HASH,
        adaptation_parity_receipt_sha256=HASH,
        reviewer_key_id=verifier.key_id,
        reviewer_public_key_base64=verifier.public_key_base64,
        reviewer_public_key_sha256=verifier.public_key_sha256,
    )
    evidence = replace(
        unsigned,
        attestation=SIGNER.sign(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(unsigned),
        ),
    )
    report = _run(evidence, paths)
    assert report["external_fidelity_gate_passed"] is False
    assert report["method_results"][0]["checks"]["primary_source_content_bound"] is False


def test_trusted_signature_over_six_arms_of_fictional_artifacts_still_fails() -> None:
    verifier = SIGNER.verifier()
    evidence_by_arm: dict[str, ExternalMethodEvidence] = {}
    for specification in default_external_method_specifications_v0_2():
        unsigned = ExternalMethodEvidence(
            arm=specification.arm,
            primary_source_sha256=HASH,
            official_code_url="x",
            official_code_commit="x",
            implementation_bundle_sha256=HASH,
            verified_native_components=specification.required_native_components,
            component_parity_receipt_sha256=HASH,
            native_protocol_recheck_receipt_sha256=HASH,
            adaptation_contract_sha256=HASH,
            adaptation_parity_receipt_sha256=HASH,
            reviewer_key_id=verifier.key_id,
            reviewer_public_key_base64=verifier.public_key_base64,
            reviewer_public_key_sha256=verifier.public_key_sha256,
        )
        evidence_by_arm[specification.arm] = replace(
            unsigned,
            attestation=SIGNER.sign(
                EVIDENCE_ATTESTATION_DOMAIN,
                attested_external_method_evidence_payload(unsigned),
            ),
        )
    report = run_external_fidelity_gate_v0_2(
        default_external_method_specifications_v0_2(),
        evidence_by_arm,
        trusted_reviewer_key_id=verifier.key_id,
        trusted_reviewer_public_key_sha256=verifier.public_key_sha256,
        enforce_canonical_catalog=False,
    )
    assert report["external_fidelity_gate_passed"] is False
    assert report["external_method_efficacy_comparison_allowed"] is False


def test_receipt_hash_with_failed_execution_semantics_does_not_pass(
    tmp_path: Path,
) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    failed = {
        "protocol": "structure-two-adaptation-parity-receipt@0.6",
        "arm": "external",
        "adaptation_parity_passed": False,
        "execution": {
            "command": ["pytest", "-q"],
            "exit_code": 0,
            "log_sha256": external_artifact_sha256(paths.adaptation_parity_execution_log),
            "implementation_bundle_sha256": evidence.implementation_bundle_sha256,
        },
    }
    paths.adaptation_parity_receipt.write_text(json.dumps(failed), encoding="utf-8")
    unsigned = replace(
        evidence,
        adaptation_parity_receipt_sha256=external_artifact_sha256(paths.adaptation_parity_receipt),
        attestation=None,
    )
    resigned = replace(
        unsigned,
        attestation=SIGNER.sign(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(unsigned),
        ),
    )
    report = _run(resigned, paths)
    assert report["method_results"][0]["adaptation_fidelity_passed"] is False


def test_receipt_with_missing_execution_log_or_nonzero_exit_does_not_pass(
    tmp_path: Path,
) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    receipt = json.loads(paths.component_parity_receipt.read_text(encoding="utf-8"))
    receipt["execution"]["exit_code"] = 1
    paths.component_parity_receipt.write_text(json.dumps(receipt), encoding="utf-8")
    unsigned = replace(
        evidence,
        component_parity_receipt_sha256=external_artifact_sha256(paths.component_parity_receipt),
        attestation=None,
    )
    resigned = replace(
        unsigned,
        attestation=SIGNER.sign(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(unsigned),
        ),
    )
    report = _run(resigned, paths)
    assert report["method_results"][0]["native_fidelity_passed"] is False


def test_plain_one_passed_log_fails_even_when_executor_resigns(tmp_path: Path) -> None:
    evidence, paths = _complete_evidence(tmp_path)
    paths.component_parity_execution_log.write_text("1 passed\n", encoding="utf-8")
    receipt = json.loads(paths.component_parity_receipt.read_text(encoding="utf-8"))
    for key in (
        "executor_key_id",
        "executor_public_key_base64",
        "executor_public_key_sha256",
        "executor_attestation",
    ):
        receipt.pop(key)
    receipt["execution"]["log_sha256"] = external_artifact_sha256(
        paths.component_parity_execution_log
    )
    verifier = EXECUTOR.verifier()
    receipt.update(
        {
            "executor_key_id": verifier.key_id,
            "executor_public_key_base64": verifier.public_key_base64,
            "executor_public_key_sha256": verifier.public_key_sha256,
            "executor_attestation": EXECUTOR.sign(EXECUTION_ATTESTATION_DOMAIN, receipt).model_dump(
                mode="json"
            ),
        }
    )
    paths.component_parity_receipt.write_text(json.dumps(receipt), encoding="utf-8")
    unsigned = replace(
        evidence,
        component_parity_receipt_sha256=external_artifact_sha256(paths.component_parity_receipt),
        attestation=None,
    )
    resigned = replace(
        unsigned,
        attestation=SIGNER.sign(
            EVIDENCE_ATTESTATION_DOMAIN,
            attested_external_method_evidence_payload(unsigned),
        ),
    )
    report = _run(resigned, paths)
    assert report["native_fidelity_gate_passed"] is False


def test_official_checkout_binding_rejects_dirty_tree(tmp_path: Path) -> None:
    checkout = tmp_path / "official"
    checkout.mkdir()
    subprocess.run(("git", "init", "-q"), cwd=checkout, check=True)
    subprocess.run(
        ("git", "config", "user.email", "test@example.org"),
        cwd=checkout,
        check=True,
    )
    subprocess.run(("git", "config", "user.name", "Test"), cwd=checkout, check=True)
    source = checkout / "method.py"
    source.write_text("METHOD = 1\n", encoding="utf-8")
    nested = checkout / "nested"
    nested.mkdir()
    (nested / "component.py").write_text("COMPONENT = 1\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=checkout, check=True)
    subprocess.run(("git", "commit", "-qm", "fixture"), cwd=checkout, check=True)
    commit = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert fidelity_module._git_checkout_matches(checkout, commit) is True
    assert fidelity_module._git_checkout_matches(nested, commit) is False
    (checkout / "untracked.py").write_text("ATTACK = 1\n", encoding="utf-8")
    assert fidelity_module._git_checkout_matches(checkout, commit) is False


def test_candidate_bundle_conftest_cannot_turn_a_trusted_failure_into_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _artifact_paths(tmp_path)
    assert paths.fidelity_test_bundle is not None
    (paths.implementation_bundle / "implementation.py").write_text(
        "IMPLEMENTATION = 'wrong'\n", encoding="utf-8"
    )
    (paths.implementation_bundle / "conftest.py").write_text(
        "import pytest\n"
        "@pytest.hookimpl(hookwrapper=True, tryfirst=True)\n"
        "def pytest_runtest_makereport(item, call):\n"
        "    outcome = yield\n"
        "    outcome.get_result().outcome = 'passed'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTEST_ADDOPTS", "-p candidate_plugin")
    monkeypatch.setenv("PYTHONPATH", str(paths.implementation_bundle))
    assert (
        fidelity_module._rerun_fidelity_tests(
            paths.implementation_bundle,
            paths.fidelity_test_bundle,
            (COMPONENT_NODE,),
            external_artifact_sha256(paths.fidelity_test_bundle),
        )
        is False
    )


def test_python_startup_hook_cannot_turn_fidelity_failure_into_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _artifact_paths(tmp_path)
    assert paths.fidelity_test_bundle is not None
    (paths.implementation_bundle / "implementation.py").write_text(
        "IMPLEMENTATION = 'wrong'\n", encoding="utf-8"
    )
    startup_hooks = tmp_path / "startup-hooks"
    startup_hooks.mkdir()
    marker = tmp_path / "sitecustomize-loaded"
    (startup_hooks / "sitecustomize.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('loaded', encoding='utf-8')\n"
        "os.environ['PYTEST_ADDOPTS'] = '-p startup_attack_plugin'\n",
        encoding="utf-8",
    )
    (startup_hooks / "startup_attack_plugin.py").write_text(
        "import pytest\n"
        "@pytest.hookimpl(hookwrapper=True, tryfirst=True)\n"
        "def pytest_runtest_makereport(item, call):\n"
        "    outcome = yield\n"
        "    outcome.get_result().outcome = 'passed'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", str(startup_hooks))
    monkeypatch.setenv("PYTHONSTARTUP", str(startup_hooks / "sitecustomize.py"))
    assert (
        fidelity_module._rerun_fidelity_tests(
            paths.implementation_bundle,
            paths.fidelity_test_bundle,
            (COMPONENT_NODE,),
            external_artifact_sha256(paths.fidelity_test_bundle),
        )
        is False
    )
    assert not marker.exists()


def test_official_checkout_must_rebuild_the_submitted_implementation_bundle(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "official-build"
    checkout.mkdir()
    subprocess.run(("git", "init", "-q"), cwd=checkout, check=True)
    subprocess.run(
        ("git", "config", "user.email", "test@example.org"),
        cwd=checkout,
        check=True,
    )
    subprocess.run(("git", "config", "user.name", "Test"), cwd=checkout, check=True)
    (checkout / "build.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "output = Path(sys.argv[2])\n"
        "(output / 'implementation.py').write_text(\"IMPLEMENTATION = 'official'\\n\")\n",
        encoding="utf-8",
    )
    subprocess.run(("git", "add", "."), cwd=checkout, check=True)
    subprocess.run(("git", "commit", "-qm", "fixture"), cwd=checkout, check=True)
    commit = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=checkout,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    submitted = tmp_path / "submitted"
    submitted.mkdir()
    (submitted / "implementation.py").write_text("IMPLEMENTATION = 'official'\n", encoding="utf-8")
    specification = replace(
        _spec(
            code_required=True,
            official_build_command=("python", "build.py", "--output", "{output_dir}"),
        ),
        official_code_url="https://example.org/official.git",
        official_code_commit=commit,
    )
    receipt = fidelity_module._reproduce_official_build(
        specification=specification,
        official_checkout=checkout,
        submitted_implementation_bundle=submitted,
    )
    assert receipt is not None
    assert receipt["build_output_bundle_sha256"] == external_artifact_sha256(submitted)

    (submitted / "implementation.py").write_text(
        "IMPLEMENTATION = 'unrelated-proxy'\n", encoding="utf-8"
    )
    assert (
        fidelity_module._reproduce_official_build(
            specification=specification,
            official_checkout=checkout,
            submitted_implementation_bundle=submitted,
        )
        is None
    )
