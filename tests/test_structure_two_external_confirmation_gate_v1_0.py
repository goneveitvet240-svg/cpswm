from __future__ import annotations

import inspect
import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations import (
    structure_two_external_confirmation_gate_v1_0 as confirmation,
)
from cpswm.system.evaluation_operations.structure_two_external_confirmation_gate_v0_9 import (
    FidelityArtifactPathsV09,
    FidelityIsolationReceiptVerificationV09,
)
from cpswm.system.evaluation_operations.structure_two_external_confirmation_gate_v1_0 import (
    CANONICAL_SCOPE,
    FIDELITY_SCOPE,
    CanonicalExecutionRawInputsV10,
    CombinedExternalConfirmationAuthorizationV10,
    ExternalConfirmationVerificationInputsV10,
    FidelityRawInputsV10,
    FreezeCommitmentLinkV10,
    IsolatedVerifierExecutionBindingV10,
    IsolatedVerifierExecutionPathsV10,
    finalize_freeze_commitment_link_v1_0,
    freeze_commitment_link_authority_signing_request_v1_0,
    freeze_commitment_link_custodian_signing_request_v1_0,
    make_combined_external_confirmation_authorization_v1_0,
    prepare_combined_external_confirmation_authorization_v1_0,
    prepare_freeze_commitment_link_v1_0,
    sign_freeze_commitment_link_request_v1_0,
    verify_combined_external_confirmation_authorization_v1_0,
    verify_freeze_commitment_link_v1_0,
)
from cpswm.system.evaluation_operations.structure_two_external_governance_v0_6 import TRUST_ROLES
from cpswm.system.evaluation_operations.structure_two_external_verification_freeze_v1_0 import (
    ExternalVerificationFreezeV10,
    FileDigestV10,
    FrozenPartyKeysV10,
    PublicKeyBindingV10,
    VerifierMaterialPathsV10,
    VerifierMaterialSnapshotV10,
)
from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import EXPECTED_ARMS
from cpswm.system.evaluation_operations.structure_two_sealed_gate_b_opening_v0_9 import (
    VerifiedSealedGateBCommitmentV09,
    make_sealed_gate_b_commitment_record_v0_9,
    verify_sealed_gate_b_commitment_record_v0_9,
)
from cpswm.system.reproducibility import content_sha256

T0 = datetime(2026, 9, 5, 0, 0, tzinfo=UTC)


def _binding(signer: Ed25519AttestationSigner) -> PublicKeyBindingV10:
    verifier = signer.verifier()
    return PublicKeyBindingV10(
        key_id=verifier.key_id,
        public_key_base64=verifier.public_key_base64,
        public_key_sha256=verifier.public_key_sha256,
    )


def _synthetic_verifier_snapshot(scope: str, marker: str) -> VerifierMaterialSnapshotV10:
    bundle_root = f"synthetic-verifiers/{scope}"
    files = (
        FileDigestV10(
            relative_path=f"{bundle_root}/config.json",
            bytes_sha256="5" * 64,
        ),
        FileDigestV10(
            relative_path=f"{bundle_root}/entry.py",
            bytes_sha256="3" * 64,
        ),
        FileDigestV10(
            relative_path=f"{bundle_root}/implementation.py",
            bytes_sha256=marker * 64,
        ),
    )
    rows = tuple((row.relative_path, row.bytes_sha256) for row in files)
    return VerifierMaterialSnapshotV10(
        scope=scope,
        bundle_root_relative_path=bundle_root,
        files=files,
        bundle_content_sha256=content_sha256(
            {
                "protocol": "structure-two-verifier-live-bundle@1.0",
                "scope": scope,
                "bundle_root_relative_path": bundle_root,
                "files": rows,
            }
        ),
        entrypoint_relative_path=f"{bundle_root}/entry.py",
        entrypoint_bytes_sha256="3" * 64,
        engine_absolute_path=f"/synthetic-engines/{scope}",
        engine_bytes_sha256="4" * 64,
        config_relative_path=f"{bundle_root}/config.json",
        config_bytes_sha256="5" * 64,
    )


class _SyntheticCeremony:
    """Signature-complete fixture only; it is never represented as external evidence."""

    def __init__(self) -> None:
        self.reviewer = Ed25519AttestationSigner.generate(key_id="external-reviewer")
        self.executor = Ed25519AttestationSigner.generate(key_id="external-executor")
        self.custodian = Ed25519AttestationSigner.generate(key_id="external-custodian")
        self.authority = Ed25519AttestationSigner.generate(key_id="external-authority")
        self.parties = FrozenPartyKeysV10(
            reviewer=_binding(self.reviewer),
            executor=_binding(self.executor),
            custodian=_binding(self.custodian),
            enrollment_authority=_binding(self.authority),
        )
        self.chain = self._chain()

    def _execution_binding(self, scope: str, marker: str) -> IsolatedVerifierExecutionBindingV10:
        material = _synthetic_verifier_snapshot(scope, marker)
        return IsolatedVerifierExecutionBindingV10(
            scope=scope,
            freeze_body_sha256="1" * 64,
            verifier_bundle_content_sha256=material.bundle_content_sha256,
            verifier_entrypoint_bytes_sha256="3" * 64,
            verifier_engine_bytes_sha256="4" * 64,
            verifier_config_bytes_sha256="5" * 64,
            verifier_material_before=material,
            verifier_material_after=material,
            isolation_code_bundle_sha256=(
                confirmation._isolation_bundle_sha256_from_snapshot(material)
            ),
            request_artifact_sha256="6" * 64,
            request_content_sha256="7" * 64,
            result_artifact_sha256="8" * 64,
            result_content_sha256="9" * 64,
            isolation_receipt_artifact_sha256="a" * 64,
            isolation_receipt_content_sha256="b" * 64,
            runner_key_id=f"{scope}-runner",
            runner_public_key_sha256="c" * 64,
            started_at_utc=T0 + timedelta(seconds=10),
            finished_at_utc=T0 + timedelta(seconds=11),
            formal_isolation_verified=True,
        )

    def _chain(self) -> Any:
        frozen_manifest = SimpleNamespace(
            immutable_manifest_sha256="d" * 64,
            preregistered_producer_run_id="synthetic-producer-run",
        )
        freeze_body = SimpleNamespace(
            party_keys=self.parties,
            forbidden_seed_namespaces_sha256="e" * 64,
            freeze_ledger_sequence=2,
        )
        freeze = SimpleNamespace(body=freeze_body, freeze_body_sha256="1" * 64)
        commitment_record = SimpleNamespace(commitment_ledger_sequence=3)
        lifecycle_record = SimpleNamespace(gate_a_ledger_sequence=4)
        opening = SimpleNamespace(
            opening_attempt_id="synthetic-opening-attempt", opening_ledger_sequence=5
        )
        consumption = SimpleNamespace(
            head_sha256="f" * 64,
            ledger_sequence=6,
        )
        dual = SimpleNamespace(
            gate_b_protocol_id=("structure-two-stratified-mechanism-dual-readout-gate-b@0.7"),
            protocol_invalidated=True,
            formal_gate_b_passed=False,
            canonical_execution_ledger_sequence=7,
            gate_b_ledger_sequence=8,
            gate_b_scored_at_utc=T0 + timedelta(minutes=1),
        )
        return SimpleNamespace(
            registry=SimpleNamespace(),
            role_verifiers={
                "reviewer": self.reviewer.verifier(),
                "executor": self.executor.verifier(),
                "custodian": self.custodian.verifier(),
            },
            frozen_manifest=frozen_manifest,
            frozen_manifest_content_sha256="0" * 64,
            external_verification_freeze=freeze,
            external_verification_freeze_content_sha256="2" * 64,
            gate_a_report=SimpleNamespace(),
            gate_a_report_content_sha256="3" * 64,
            verified_commitment=SimpleNamespace(record=commitment_record, content_sha256="4" * 64),
            freeze_commitment_link=SimpleNamespace(),
            freeze_commitment_link_content_sha256="d" * 64,
            verified_gate_a_lifecycle=SimpleNamespace(record=lifecycle_record),
            gate_a_lifecycle_content_sha256="5" * 64,
            opening_context=SimpleNamespace(),
            opening=opening,
            opening_content_sha256="6" * 64,
            authoritative_ledger_store_identity=SimpleNamespace(content_sha256="7" * 64),
            consumption_head=consumption,
            canonical_execution=SimpleNamespace(),
            canonical_execution_content_sha256="8" * 64,
            canonical_verifier_execution=self._execution_binding(CANONICAL_SCOPE, "2"),
            fidelity=SimpleNamespace(),
            fidelity_content_sha256="9" * 64,
            fidelity_snapshot=SimpleNamespace(),
            fidelity_verifier_execution=self._execution_binding(FIDELITY_SCOPE, "f"),
            canonical_dual_readout_execution=SimpleNamespace(),
            canonical_dual_readout_execution_content_sha256="c" * 64,
            sealed_dual_gate_b=dual,
            sealed_dual_gate_b_content_sha256="a" * 64,
            trust_anchor_registry_content_sha256="b" * 64,
        )

    def inputs(self) -> Any:
        return SimpleNamespace(
            trusted_enrollment_authority=self.authority.verifier(),
            verification_time_utc=T0 + timedelta(minutes=3),
        )

    def patch_chain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            confirmation,
            "verify_external_confirmation_chain_v1_0",
            lambda _inputs: self.chain,
        )

    def sign(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
        self.patch_chain(monkeypatch)
        return make_combined_external_confirmation_authorization_v1_0(
            verification_inputs=self.inputs(),
            authorized_at_utc=T0 + timedelta(minutes=2),
            reviewer=self.reviewer,
            executor=self.executor,
            custodian=self.custodian,
            enrollment_authority=self.authority,
        )


def _rehash(payload: dict[str, Any]) -> None:
    payload.pop("content_sha256", None)
    payload["content_sha256"] = content_sha256(payload)


def _live_verifier_material(
    tmp_path: Path,
    *,
    scope: str = CANONICAL_SCOPE,
) -> tuple[Path, VerifierMaterialPathsV10, VerifierMaterialSnapshotV10, Path]:
    repository_root = tmp_path / "repository"
    bundle = repository_root / "verifier"
    bundle.mkdir(parents=True)
    entrypoint = bundle / "entry.py"
    entrypoint.write_text("print('frozen verifier')\n", encoding="utf-8")
    config = bundle / "config.json"
    config.write_text('{"threshold":1}\n', encoding="utf-8")
    engine = repository_root / "engine"
    engine.write_bytes(b"#!/bin/sh\nexit 0\n")
    engine.chmod(0o755)
    material = VerifierMaterialPathsV10(
        bundle_root=Path("verifier"),
        entrypoint_path=Path("verifier/entry.py"),
        engine_path=engine.resolve(strict=True),
        config_path=Path("verifier/config.json"),
    )
    snapshot = confirmation._verifier_material_snapshot(
        repository_root,
        material,
        scope=scope,
    )
    return repository_root, material, snapshot, entrypoint


def _isolated_verifier_files(
    tmp_path: Path,
    *,
    snapshot: VerifierMaterialSnapshotV10,
) -> tuple[
    confirmation.IsolatedVerifierRequestV10,
    IsolatedVerifierExecutionPathsV10,
]:
    artifact_root = tmp_path / "artifacts"
    work = tmp_path / "work"
    artifact_root.mkdir()
    work.mkdir()
    request = confirmation.IsolatedVerifierRequestV10(
        scope=CANONICAL_SCOPE,
        freeze_body_sha256="1" * 64,
        immutable_manifest_sha256="2" * 64,
        producer_run_id="run",
        verifier_material_snapshot=snapshot,
        isolation_code_bundle_sha256=(
            confirmation._isolation_bundle_sha256_from_snapshot(snapshot)
        ),
        evidence_bindings={"raw": "3" * 64},
    )
    request_payload = confirmation._content_bound_payload(request)
    request_path = artifact_root / confirmation.VERIFIER_REQUEST_FILENAME
    request_path.write_bytes(confirmation.canonical_json(request_payload).encode("utf-8"))
    result_payload = {"verdict": "unused"}
    _rehash(result_payload)
    (work / confirmation.VERIFIER_RESULT_FILENAME).write_bytes(
        confirmation.canonical_json(result_payload).encode("utf-8")
    )
    receipt_payload = {"kind": "synthetic-receipt-envelope"}
    _rehash(receipt_payload)
    receipt_path = artifact_root / "receipt.json"
    receipt_path.write_bytes(confirmation.canonical_json(receipt_payload).encode("utf-8"))
    return request, IsolatedVerifierExecutionPathsV10(
        request_path=request_path,
        result_path=work / confirmation.VERIFIER_RESULT_FILENAME,
        isolation_receipt_path=receipt_path,
        working_directory=work,
    )


def _link_fixture(
    tmp_path: Path,
) -> tuple[
    Any,
    dict[str, Any],
    ExternalVerificationFreezeV10,
    dict[str, Any],
    VerifiedSealedGateBCommitmentV09,
]:
    freeze_test = runpy.run_path(
        str(Path(__file__).with_name("test_structure_two_external_verification_freeze_v1_0.py"))
    )
    ceremony = freeze_test["Ceremony"](tmp_path)
    freeze_payload, freeze = ceremony.finalize()
    bundles = {arm: content_sha256({"synthetic-bundle": arm}) for arm in EXPECTED_ARMS}
    commitment_payload = make_sealed_gate_b_commitment_record_v0_9(
        immutable_manifest_sha256="d" * 64,
        producer_run_id="synthetic-freeze-link-run",
        arm_implementation_bundle_sha256=bundles,
        sealed_gate_b_commitment_sha256="e" * 64,
        opening_attempt_id="synthetic-link-opening-0001",
        ledger_identifier=freeze.body.freeze_ledger_identifier,
        freeze_ledger_sequence=freeze.body.freeze_ledger_sequence,
        commitment_ledger_sequence=freeze.body.freeze_ledger_sequence + 1,
        freeze_completed_at_utc=freeze.body.frozen_at_utc,
        committed_at_utc=freeze.body.frozen_at_utc + timedelta(minutes=1),
        custodian=ceremony.custodian,
        enrollment_authority=ceremony.authority,
    )
    commitment = verify_sealed_gate_b_commitment_record_v0_9(
        commitment_payload,
        expected_immutable_manifest_sha256="d" * 64,
        expected_producer_run_id="synthetic-freeze-link-run",
        expected_arm_implementation_bundle_sha256=bundles,
        expected_ledger_identifier=freeze.body.freeze_ledger_identifier,
        expected_freeze_ledger_sequence=freeze.body.freeze_ledger_sequence,
        expected_freeze_completed_at_utc=freeze.body.frozen_at_utc,
        trusted_custodian=ceremony.custodian.verifier(),
        trusted_enrollment_authority=ceremony.authority.verifier(),
    )
    return ceremony, freeze_payload, freeze, commitment_payload, commitment


def _signed_link(
    *,
    ceremony: Any,
    freeze_payload: dict[str, Any],
    freeze: ExternalVerificationFreezeV10,
    commitment: VerifiedSealedGateBCommitmentV09,
) -> dict[str, Any]:
    prepared = prepare_freeze_commitment_link_v1_0(
        external_verification_freeze=freeze,
        external_verification_freeze_content_sha256=str(freeze_payload["content_sha256"]),
        verified_commitment=commitment,
    )
    custodian_request = freeze_commitment_link_custodian_signing_request_v1_0(prepared)
    custodian_attestation = sign_freeze_commitment_link_request_v1_0(
        custodian_request,
        signer=ceremony.custodian,
    )
    authority_request = freeze_commitment_link_authority_signing_request_v1_0(
        prepared,
        custodian_attestation=custodian_attestation,
    )
    return finalize_freeze_commitment_link_v1_0(
        prepared,
        external_verification_freeze=freeze,
        external_verification_freeze_content_sha256=str(freeze_payload["content_sha256"]),
        verified_commitment=commitment,
        custodian_attestation=custodian_attestation,
        authority_attestation=sign_freeze_commitment_link_request_v1_0(
            authority_request,
            signer=ceremony.authority,
        ),
        trusted_custodian=ceremony.custodian.verifier(),
        trusted_enrollment_authority=ceremony.authority.verifier(),
    )


def _finalize_alternate_freeze(
    ceremony: Any,
) -> tuple[dict[str, Any], ExternalVerificationFreezeV10]:
    from cpswm.system.evaluation_operations.structure_two_external_verification_freeze_v1_0 import (
        attach_external_verification_freeze_role_attestations_v1_0,
        attach_runner_subkey_attestations_v1_0,
        external_verification_freeze_authority_signing_request_v1_0,
        external_verification_freeze_signing_requests_v1_0,
        finalize_external_verification_freeze_v1_0,
        runner_subkey_signing_requests_v1_0,
        sign_detached_request_v1_0,
    )

    unsigned = ceremony.prepare(authority_nonce_sha256="c" * 64)
    runner_requests = runner_subkey_signing_requests_v1_0(unsigned)
    runner_signers = {
        "canonical_episode_executor:runner": ceremony.canonical_runner,
        "canonical_episode_executor:executor": ceremony.executor,
        "six_method_fidelity_executor:runner": ceremony.fidelity_runner,
        "six_method_fidelity_executor:executor": ceremony.executor,
    }
    runner_signed = attach_runner_subkey_attestations_v1_0(
        record=unsigned,
        attestations={
            key: sign_detached_request_v1_0(request, signer=runner_signers[key])
            for key, request in runner_requests.items()
        },
        canonical_runner=ceremony.canonical_runner.verifier(),
        fidelity_runner=ceremony.fidelity_runner.verifier(),
        executor=ceremony.executor.verifier(),
    )
    role_requests = external_verification_freeze_signing_requests_v1_0(runner_signed)
    role_signers = {
        "reviewer": ceremony.reviewer,
        "executor": ceremony.executor,
        "custodian": ceremony.custodian,
    }
    role_signed = attach_external_verification_freeze_role_attestations_v1_0(
        record=runner_signed,
        attestations={
            role: sign_detached_request_v1_0(request, signer=role_signers[role])
            for role, request in role_requests.items()
        },
        reviewer=ceremony.reviewer.verifier(),
        executor=ceremony.executor.verifier(),
        custodian=ceremony.custodian.verifier(),
    )
    authority_request = external_verification_freeze_authority_signing_request_v1_0(
        role_signed,
        reviewer=ceremony.reviewer.verifier(),
        executor=ceremony.executor.verifier(),
        custodian=ceremony.custodian.verifier(),
        enrollment_authority=ceremony.authority.verifier(),
    )
    payload = finalize_external_verification_freeze_v1_0(
        record=role_signed,
        authority_attestation=sign_detached_request_v1_0(
            authority_request,
            signer=ceremony.authority,
        ),
        reviewer=ceremony.reviewer.verifier(),
        executor=ceremony.executor.verifier(),
        custodian=ceremony.custodian.verifier(),
        enrollment_authority=ceremony.authority.verifier(),
    )
    return payload, ceremony.verify(payload)


def test_freeze_commitment_link_positive_and_authority_after_custodian(
    tmp_path: Path,
) -> None:
    ceremony, freeze_payload, freeze, _, commitment = _link_fixture(tmp_path)
    payload = _signed_link(
        ceremony=ceremony,
        freeze_payload=freeze_payload,
        freeze=freeze,
        commitment=commitment,
    )
    verified = verify_freeze_commitment_link_v1_0(
        payload,
        external_verification_freeze=freeze,
        external_verification_freeze_content_sha256=str(freeze_payload["content_sha256"]),
        verified_commitment=commitment,
        trusted_custodian=ceremony.custodian.verifier(),
        trusted_enrollment_authority=ceremony.authority.verifier(),
    )
    assert isinstance(verified, FreezeCommitmentLinkV10)
    assert verified.external_verification_freeze_ledger_head_sha256 == (
        freeze.freeze_ledger_head_sha256
    )
    assert verified.sealed_commitment_content_sha256 == commitment.content_sha256


def test_fully_signed_link_rejects_same_ledger_freeze_fork(tmp_path: Path) -> None:
    ceremony, freeze_payload, freeze, _, commitment = _link_fixture(tmp_path)
    linked = _signed_link(
        ceremony=ceremony,
        freeze_payload=freeze_payload,
        freeze=freeze,
        commitment=commitment,
    )
    alternate_payload, alternate = _finalize_alternate_freeze(ceremony)
    assert alternate.body.freeze_ledger_identifier == freeze.body.freeze_ledger_identifier
    assert alternate.body.freeze_ledger_sequence == freeze.body.freeze_ledger_sequence
    assert alternate.body.frozen_at_utc == freeze.body.frozen_at_utc
    assert alternate_payload["content_sha256"] != freeze_payload["content_sha256"]
    with pytest.raises(ValueError, match="substituted one side"):
        verify_freeze_commitment_link_v1_0(
            linked,
            external_verification_freeze=alternate,
            external_verification_freeze_content_sha256=str(alternate_payload["content_sha256"]),
            verified_commitment=commitment,
            trusted_custodian=ceremony.custodian.verifier(),
            trusted_enrollment_authority=ceremony.authority.verifier(),
        )


def test_fully_signed_link_rejects_same_context_commitment_substitution(
    tmp_path: Path,
) -> None:
    ceremony, freeze_payload, freeze, commitment_payload, commitment = _link_fixture(tmp_path)
    linked = _signed_link(
        ceremony=ceremony,
        freeze_payload=freeze_payload,
        freeze=freeze,
        commitment=commitment,
    )
    substituted_payload = make_sealed_gate_b_commitment_record_v0_9(
        immutable_manifest_sha256=commitment.record.immutable_manifest_sha256,
        producer_run_id=commitment.record.producer_run_id,
        arm_implementation_bundle_sha256=(commitment.record.arm_implementation_bundle_sha256),
        sealed_gate_b_commitment_sha256="f" * 64,
        opening_attempt_id=commitment.record.opening_attempt_id,
        ledger_identifier=commitment.record.ledger_identifier,
        freeze_ledger_sequence=commitment.record.freeze_ledger_sequence,
        commitment_ledger_sequence=commitment.record.commitment_ledger_sequence,
        freeze_completed_at_utc=commitment.record.freeze_completed_at_utc,
        committed_at_utc=commitment.record.committed_at_utc,
        custodian=ceremony.custodian,
        enrollment_authority=ceremony.authority,
    )
    substituted = verify_sealed_gate_b_commitment_record_v0_9(
        substituted_payload,
        expected_immutable_manifest_sha256=commitment.record.immutable_manifest_sha256,
        expected_producer_run_id=commitment.record.producer_run_id,
        expected_arm_implementation_bundle_sha256=(
            commitment.record.arm_implementation_bundle_sha256
        ),
        expected_ledger_identifier=commitment.record.ledger_identifier,
        expected_freeze_ledger_sequence=commitment.record.freeze_ledger_sequence,
        expected_freeze_completed_at_utc=commitment.record.freeze_completed_at_utc,
        trusted_custodian=ceremony.custodian.verifier(),
        trusted_enrollment_authority=ceremony.authority.verifier(),
    )
    assert substituted_payload["content_sha256"] != commitment_payload["content_sha256"]
    with pytest.raises(ValueError, match="substituted one side"):
        verify_freeze_commitment_link_v1_0(
            linked,
            external_verification_freeze=freeze,
            external_verification_freeze_content_sha256=str(freeze_payload["content_sha256"]),
            verified_commitment=substituted,
            trusted_custodian=ceremony.custodian.verifier(),
            trusted_enrollment_authority=ceremony.authority.verifier(),
        )


def test_signature_complete_v07_is_blocked_before_combined_signing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ceremony = _SyntheticCeremony()
    with pytest.raises(confirmation.ExternalConfirmationBlockedError) as caught:
        ceremony.sign(monkeypatch)
    assert caught.value.report.stage == "sealed_dual_gate_b"
    assert caught.value.report.external_method_efficacy_comparison_allowed is False


def test_combined_prepare_stays_closed_before_any_role_can_sign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ceremony = _SyntheticCeremony()
    ceremony.patch_chain(monkeypatch)
    with pytest.raises(confirmation.ExternalConfirmationBlockedError):
        prepare_combined_external_confirmation_authorization_v1_0(
            verification_inputs=ceremony.inputs(),
            authorized_at_utc=T0 + timedelta(minutes=2),
        )


def test_forged_complete_combined_payload_cannot_bypass_closed_gate_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ceremony = _SyntheticCeremony()
    ceremony.patch_chain(monkeypatch)
    with pytest.raises(confirmation.ExternalConfirmationBlockedError):
        verify_combined_external_confirmation_authorization_v1_0(
            {
                "status": "COMBINED_EXTERNAL_CONFIRMATION_AUTHORIZED",
                "external_method_efficacy_comparison_allowed": True,
            },
            verification_inputs=ceremony.inputs(),
        )


def test_stale_chain_is_blocked_by_invalidated_gate_b_before_ledger_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ceremony = _SyntheticCeremony()
    ceremony.patch_chain(monkeypatch)
    ceremony.chain.sealed_dual_gate_b.gate_b_ledger_sequence = 9
    with pytest.raises(confirmation.ExternalConfirmationBlockedError):
        verify_combined_external_confirmation_authorization_v1_0(
            {},
            verification_inputs=ceremony.inputs(),
        )


def test_combined_public_verifier_cannot_accept_caller_constructed_chain() -> None:
    parameters = inspect.signature(
        verify_combined_external_confirmation_authorization_v1_0
    ).parameters
    assert tuple(parameters) == ("payload", "verification_inputs")
    assert "chain" not in parameters


def test_formal_raw_inputs_have_no_callback_or_self_declared_verifier_fields() -> None:
    chain_fields = set(ExternalConfirmationVerificationInputsV10.__dataclass_fields__)
    canonical_fields = set(CanonicalExecutionRawInputsV10.__dataclass_fields__)
    fidelity_fields = set(FidelityRawInputsV10.__dataclass_fields__)
    forbidden = {
        "canonical_execution_verifier",
        "fidelity_verifier",
        "expected_canonical_verifier_identity",
        "expected_fidelity_verifier_identity",
        "forbidden_seed_namespaces",
        "forbidden_seed_namespaces_sha256",
        "callback",
    }
    assert not (chain_fields | canonical_fields | fidelity_fields) & forbidden
    assert "external_verification_live_inputs" in chain_fields
    assert "verifier_execution" in canonical_fields
    assert "verifier_execution" in fidelity_fields
    assert "canonical_dual_readout_execution_payload" in chain_fields
    assert "dual_readout_isolation_verification_inputs_by_task" in chain_fields
    assert "frozen_dual_gate_b_config" in chain_fields
    assert "canonical_dual_readout_execution" not in chain_fields


def test_duplicate_key_raw_json_is_rejected_before_content_verification(
    tmp_path: Path,
) -> None:
    path = tmp_path / "duplicated.json"
    path.write_bytes(b'{"protocol":"trusted","protocol":"shadow"}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        confirmation._stable_json_object(path, label="adversarial raw input")


def test_dual_receipt_path_rebuilds_raw_execution_before_formal_receipt() -> None:
    source = inspect.getsource(confirmation._verify_external_confirmation_chain_impl_v1_0)
    rebuild = source.index("verify_canonical_dual_readout_execution_v1_0(")
    formal = source.index("verify_sealed_dual_gate_b_receipt_v1_0(")
    assert rebuild < formal


def test_fidelity_rejects_caller_selected_runner(tmp_path: Path) -> None:
    trusted = Ed25519AttestationSigner.generate(key_id="frozen-fidelity-runner")
    attacker = Ed25519AttestationSigner.generate(key_id="caller-runner")
    dummy = tmp_path / "dummy.json"
    dummy.write_text("{}", encoding="utf-8")
    row = FidelityIsolationReceiptVerificationV09(
        receipt_path=dummy,
        trusted_executor=attacker.verifier(),
        command_engine_path=dummy,
        arguments=(),
        code_bundle_path=dummy,
        input_artifact_paths={"input": dummy},
        working_directory=tmp_path,
        expected_output_relative_paths={"output": "out.json"},
        timeout_seconds=30,
    )
    methods = {arm: dummy for arm in confirmation.EXTERNAL_METHOD_ARMS}
    receipts = {arm: (row,) for arm in confirmation.EXTERNAL_METHOD_ARMS}
    paths = FidelityArtifactPathsV09(
        raw_fidelity_report=dummy,
        method_evidence_artifacts_by_arm=methods,
        isolation_receipt_verifications_by_arm=receipts,
    )
    with pytest.raises(AttestationError, match="caller-selected runner"):
        confirmation._fidelity_paths_with_frozen_runner(
            paths,
            runner=trusted.verifier(),
        )


def test_v06_to_v10_prefix_rejects_source_and_ledger_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = Ed25519AttestationSigner.generate(key_id="authority")
    role_signers = {role: Ed25519AttestationSigner.generate(key_id=role) for role in TRUST_ROLES}
    registry = SimpleNamespace(registry_identifier="sha256:" + "1" * 64)
    role_verifiers = {role: signer.verifier() for role, signer in role_signers.items()}
    frozen = SimpleNamespace(
        freeze_ledger_sequence=5,
        freeze_ledger_identifier="authority-ledger",
        frozen_at_utc=T0,
        producer_source_bundle_sha256="2" * 64,
        gate_a_spec_content_sha256="3" * 64,
    )
    freeze = SimpleNamespace(
        body=SimpleNamespace(
            freeze_ledger_identifier="substituted-ledger",
            freeze_ledger_sequence=6,
            previous_ledger_head_sha256="4" * 64,
            frozen_at_utc=T0 + timedelta(seconds=1),
            trust_anchor_registry_identifier=registry.registry_identifier,
            producer_source=SimpleNamespace(content_sha256="5" * 64),
            gate_a_spec=SimpleNamespace(stable_json_content_sha256="3" * 64),
        )
    )
    monkeypatch.setattr(
        confirmation,
        "verify_trust_anchor_registry_v0_6",
        lambda *_args, **_kwargs: (registry, role_verifiers),
    )
    monkeypatch.setattr(
        confirmation,
        "verify_frozen_gate_b_manifest_v0_6",
        lambda *_args, **_kwargs: frozen,
    )
    monkeypatch.setattr(
        confirmation,
        "verify_external_verification_freeze_v1_0",
        lambda *_args, **_kwargs: freeze,
    )
    monkeypatch.setattr(
        confirmation,
        "_payload_content_hash",
        lambda payload, *, label: payload.get("content_sha256", "4" * 64),
    )
    inputs = SimpleNamespace(
        verification_time_utc=T0 + timedelta(minutes=1),
        trust_anchor_registry={"content_sha256": "1" * 64},
        trusted_enrollment_authority=authority.verifier(),
        externally_frozen_manifest={"content_sha256": "4" * 64},
        canonical_gate_b_draft={},
        source_register={},
        gate_a_spec={},
        external_verification_freeze_payload={},
        external_verification_live_inputs=SimpleNamespace(),
    )
    with pytest.raises(ValueError, match="immediately extend"):
        confirmation._verify_chain_prefix(cast(Any, inputs))

    freeze.body.freeze_ledger_identifier = frozen.freeze_ledger_identifier
    freeze.body.previous_ledger_head_sha256 = "4" * 64
    with pytest.raises(ValueError, match="producer source"):
        confirmation._verify_chain_prefix(cast(Any, inputs))


def test_isolated_request_substitution_fails_before_receipt_is_consulted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_path = tmp_path / confirmation.VERIFIER_REQUEST_FILENAME
    request_path.write_text(
        '{"content_sha256":"' + "0" * 64 + '","forged":true}',
        encoding="utf-8",
    )
    (tmp_path / confirmation.VERIFIER_RESULT_FILENAME).write_text("{}", encoding="utf-8")
    (tmp_path / "receipt.json").write_text("{}", encoding="utf-8")
    snapshot = _synthetic_verifier_snapshot(CANONICAL_SCOPE, "4")
    expected = confirmation.IsolatedVerifierRequestV10(
        scope=CANONICAL_SCOPE,
        freeze_body_sha256="1" * 64,
        immutable_manifest_sha256="2" * 64,
        producer_run_id="run",
        verifier_material_snapshot=snapshot,
        isolation_code_bundle_sha256=(
            confirmation._isolation_bundle_sha256_from_snapshot(snapshot)
        ),
        evidence_bindings={"raw": "3" * 64},
    )
    called = False

    def should_not_run(*_args: Any, **_kwargs: Any) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(confirmation, "verify_isolation_receipt_v0_9", should_not_run)
    material = SimpleNamespace(
        bundle_root=tmp_path,
        entrypoint_path=request_path,
        config_path=request_path,
        engine_path=request_path,
    )
    freeze = SimpleNamespace(
        freeze_body_sha256="1" * 64,
        body=SimpleNamespace(
            canonical_verifier=snapshot,
        ),
    )
    live = SimpleNamespace(repository_root=tmp_path, canonical_verifier=material)
    paths = IsolatedVerifierExecutionPathsV10(
        request_path=request_path,
        result_path=tmp_path / confirmation.VERIFIER_RESULT_FILENAME,
        isolation_receipt_path=tmp_path / "receipt.json",
        working_directory=tmp_path,
    )
    monkeypatch.setattr(
        confirmation,
        "_measure_frozen_verifier_material",
        lambda **_kwargs: snapshot,
    )
    with pytest.raises(ValueError, match="content hash"):
        confirmation._verify_isolated_verifier_execution(
            scope=CANONICAL_SCOPE,
            freeze=cast(Any, freeze),
            live_inputs=cast(Any, live),
            runner=Ed25519AttestationSigner.generate(key_id="runner").verifier(),
            paths=paths,
            expected_request=expected,
            verifier_input_paths={},
        )
    assert called is False


def test_live_verifier_bundle_mismatch_from_freeze_is_rejected(tmp_path: Path) -> None:
    repository_root, material, frozen, entrypoint = _live_verifier_material(tmp_path)
    entrypoint.write_text("print('forged verifier')\n", encoding="utf-8")

    with pytest.raises(ValueError, match="differs from freeze snapshot at admission"):
        confirmation._measure_frozen_verifier_material(
            scope=CANONICAL_SCOPE,
            repository_root=repository_root,
            material=material,
            frozen_snapshot=frozen,
            phase="admission",
        )


def test_swap_after_admission_is_remeasured_before_receipt_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, material, frozen, _ = _live_verifier_material(tmp_path)
    expected, paths = _isolated_verifier_files(tmp_path, snapshot=frozen)
    forged = frozen.model_copy(update={"engine_bytes_sha256": "f" * 64})
    measurements = iter((frozen, forged))
    receipt_consulted = False

    monkeypatch.setattr(
        confirmation,
        "_verifier_material_snapshot",
        lambda *_args, **_kwargs: next(measurements),
    )

    def should_not_verify(*_args: Any, **_kwargs: Any) -> None:
        nonlocal receipt_consulted
        receipt_consulted = True

    monkeypatch.setattr(confirmation, "verify_isolation_receipt_v0_9", should_not_verify)
    freeze = SimpleNamespace(
        freeze_body_sha256="1" * 64,
        body=SimpleNamespace(canonical_verifier=frozen),
    )
    live = SimpleNamespace(repository_root=repository_root, canonical_verifier=material)

    with pytest.raises(ValueError, match="immediately before isolation-receipt verification"):
        confirmation._verify_isolated_verifier_execution(
            scope=CANONICAL_SCOPE,
            freeze=cast(Any, freeze),
            live_inputs=cast(Any, live),
            runner=Ed25519AttestationSigner.generate(key_id="runner").verifier(),
            paths=paths,
            expected_request=expected,
            verifier_input_paths={},
        )
    assert receipt_consulted is False


def test_swap_execute_restore_receipt_hash_mismatch_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root, material, frozen, entrypoint = _live_verifier_material(tmp_path)
    expected, paths = _isolated_verifier_files(tmp_path, snapshot=frozen)
    original = entrypoint.read_bytes()

    def forged_isolation(*_args: Any, **_kwargs: Any) -> Any:
        entrypoint.write_text("print('transient forged verifier')\n", encoding="utf-8")
        forged = confirmation._verifier_material_snapshot(
            repository_root,
            material,
            scope=CANONICAL_SCOPE,
        )
        entrypoint.write_bytes(original)
        return SimpleNamespace(
            code_bundle=SimpleNamespace(
                resolved_path=str((repository_root / "verifier").resolve(strict=True)),
                artifact_kind="directory",
                content_sha256=(confirmation._isolation_bundle_sha256_from_snapshot(forged)),
            ),
            command_engine_path=frozen.engine_absolute_path,
            command_engine_binary_sha256=frozen.engine_bytes_sha256,
        )

    monkeypatch.setattr(
        confirmation,
        "verify_isolation_receipt_v0_9",
        forged_isolation,
    )
    freeze = SimpleNamespace(
        freeze_body_sha256="1" * 64,
        body=SimpleNamespace(canonical_verifier=frozen),
    )
    live = SimpleNamespace(repository_root=repository_root, canonical_verifier=material)

    with pytest.raises(ValueError, match="does not bind frozen verifier material"):
        confirmation._verify_isolated_verifier_execution(
            scope=CANONICAL_SCOPE,
            freeze=cast(Any, freeze),
            live_inputs=cast(Any, live),
            runner=Ed25519AttestationSigner.generate(key_id="runner").verifier(),
            paths=paths,
            expected_request=expected,
            verifier_input_paths={},
        )
    assert entrypoint.read_bytes() == original


def test_combined_model_rejects_skipped_or_reordered_ledger() -> None:
    ceremony = _SyntheticCeremony()
    chain = ceremony.chain
    fields = confirmation._combined_expected_fields(chain)
    with pytest.raises(ValueError, match="immediate chain"):
        CombinedExternalConfirmationAuthorizationV10(
            **fields,
            gate_a_passed=True,
            dual_gate_b_passed=True,
            six_native_reproductions_verified=True,
            six_adaptation_fidelity_checks_verified=True,
            real_isolation_evidence_verified=True,
            combined_authorization_ledger_sequence=10,
            authorized_at_utc=T0 + timedelta(minutes=2),
        )
