from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import (
    EXPECTED_ARMS,
)
from cpswm.system.evaluation_operations.structure_two_sealed_gate_b_opening_v0_9 import (
    EVALUATION_SET_ROLE,
    EXACT_BOOTSTRAP_DRAWS,
    ForbiddenSeedNamespacesV09,
    SealedGateBOpeningVerificationContextV09,
    arm_implementation_bundle_set_sha256_v0_9,
    build_sealed_gate_b_opening_context_v0_9,
    derive_forbidden_seed_namespaces_v0_9,
    finalize_gate_a_lifecycle_completion_record_v0_9,
    finalize_sealed_gate_b_commitment_record_v0_9,
    gate_a_lifecycle_signing_requests_v0_9,
    load_and_verify_sealed_gate_b_opening_v0_9,
    make_gate_a_lifecycle_completion_record_v0_9,
    make_sealed_gate_b_commitment_record_v0_9,
    make_sealed_gate_b_opening_v0_9,
    prepare_gate_a_lifecycle_completion_record_v0_9,
    prepare_sealed_gate_b_commitment_record_v0_9,
    recompute_sealed_gate_b_holdout_v0_9,
    sealed_gate_b_commitment_sha256_v0_9,
    sealed_gate_b_commitment_signing_requests_v0_9,
    sign_detached_request_v0_9,
    verify_and_build_sealed_gate_b_opening_context_v0_9,
    verify_and_consume_sealed_gate_b_opening_v0_9,
    verify_gate_a_lifecycle_completion_record_v0_9,
    verify_sealed_gate_b_commitment_record_v0_9,
    verify_sealed_gate_b_opening_v0_9,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
V05_MANIFEST = json.loads(
    (
        ROOT / "configs/project_two_experiments/structure_two_world_generator_manifest_v0_5.json"
    ).read_text(encoding="utf-8")
)
GATE_A_SPEC = json.loads(
    (ROOT / "configs/project_two_experiments/structure_two_gate_a_v0_6_spec.json").read_text(
        encoding="utf-8"
    )
)
TRAINING_SPLIT = json.loads(
    (
        ROOT / "configs/project_two_experiments/structure_two_world_rolling_train_gate_v0_4.json"
    ).read_text(encoding="utf-8")
)
WORLD_DISTRIBUTION = V05_MANIFEST["world_distribution"]
ESTIMATOR = {
    key: V05_MANIFEST["rolling_visible_history_reference"][key]
    for key in (
        "window_days",
        "context_shrinkage_pseudocounts",
        "owner_probability_threshold",
    )
}
MANIFEST_SHA256 = "a" * 64
GATE_A_REPORT_SHA256 = "b" * 64
PRODUCER_RUN_ID = "sealed-gate-b-run-v0.9"
OPENING_ATTEMPT_ID = "gate-b-opening-attempt-0001"
LEDGER_IDENTIFIER = "independent-external-ledger"
COMMITMENT_NONCE = "independent-gate-b-nonce-0001"
WORLD_SEEDS = tuple(range(510_001, 510_013))
TRAJECTORY_SEEDS = (503, 509, 521)
OBSERVATION_SEEDS = (601, 607)
FREEZE_AT = datetime(2026, 9, 4, 10, tzinfo=UTC)
COMMITTED_AT = datetime(2026, 9, 4, 10, 30, tzinfo=UTC)
GATE_A_AT = datetime(2026, 9, 4, 11, tzinfo=UTC)
OPENED_AT = datetime(2026, 9, 4, 12, tzinfo=UTC)
CUSTODIAN = Ed25519AttestationSigner.generate(key_id="sealed-gate-b-custodian")
EXECUTOR = Ed25519AttestationSigner.generate(key_id="external-gate-a-executor")
ENROLLMENT_AUTHORITY = Ed25519AttestationSigner.generate(key_id="external-enrollment-authority")
ARM_BUNDLES = {
    arm: content_sha256({"arm": arm, "implementation": "sealed-v0.9"}) for arm in EXPECTED_ARMS
}
IMPLEMENTATION_SET_SHA256 = arm_implementation_bundle_set_sha256_v0_9(ARM_BUNDLES)
COMMITMENT_SHA256 = sealed_gate_b_commitment_sha256_v0_9(
    immutable_manifest_sha256=MANIFEST_SHA256,
    producer_run_id=PRODUCER_RUN_ID,
    arm_implementation_bundle_set_sha256=IMPLEMENTATION_SET_SHA256,
    world_distribution=WORLD_DISTRIBUTION,
    world_seeds=WORLD_SEEDS,
    trajectory_seeds=TRAJECTORY_SEEDS,
    observation_seeds=OBSERVATION_SEEDS,
    estimator=ESTIMATOR,
    bootstrap_draws=EXACT_BOOTSTRAP_DRAWS,
    commitment_nonce=COMMITMENT_NONCE,
)
FORBIDDEN_NAMESPACES = derive_forbidden_seed_namespaces_v0_9(
    world_manifest=V05_MANIFEST,
    expected_world_manifest_content_sha256=content_sha256(V05_MANIFEST),
    gate_a_spec=GATE_A_SPEC,
    expected_gate_a_spec_content_sha256=GATE_A_SPEC["content_sha256"],
    training_split=TRAINING_SPLIT,
    expected_training_split_content_sha256=content_sha256(TRAINING_SPLIT),
)


def _commitment_payload(
    *,
    custodian: Ed25519AttestationSigner = CUSTODIAN,
    enrollment_authority: Ed25519AttestationSigner = ENROLLMENT_AUTHORITY,
    commitment_sha256: str = COMMITMENT_SHA256,
    commitment_ledger_sequence: int = 41,
    committed_at_utc: datetime = COMMITTED_AT,
) -> dict[str, Any]:
    return make_sealed_gate_b_commitment_record_v0_9(
        immutable_manifest_sha256=MANIFEST_SHA256,
        producer_run_id=PRODUCER_RUN_ID,
        arm_implementation_bundle_sha256=ARM_BUNDLES,
        sealed_gate_b_commitment_sha256=commitment_sha256,
        opening_attempt_id=OPENING_ATTEMPT_ID,
        ledger_identifier=LEDGER_IDENTIFIER,
        freeze_ledger_sequence=40,
        commitment_ledger_sequence=commitment_ledger_sequence,
        freeze_completed_at_utc=FREEZE_AT,
        committed_at_utc=committed_at_utc,
        custodian=custodian,
        enrollment_authority=enrollment_authority,
        verification_time_utc=OPENED_AT,
    )


def _verified_commitment(
    payload: dict[str, Any] | None = None,
    *,
    verification_time_utc: datetime = OPENED_AT,
):
    return verify_sealed_gate_b_commitment_record_v0_9(
        payload or _commitment_payload(),
        expected_immutable_manifest_sha256=MANIFEST_SHA256,
        expected_producer_run_id=PRODUCER_RUN_ID,
        expected_arm_implementation_bundle_sha256=ARM_BUNDLES,
        expected_ledger_identifier=LEDGER_IDENTIFIER,
        expected_freeze_ledger_sequence=40,
        expected_freeze_completed_at_utc=FREEZE_AT,
        trusted_custodian=CUSTODIAN.verifier(),
        trusted_enrollment_authority=ENROLLMENT_AUTHORITY.verifier(),
        verification_time_utc=verification_time_utc,
    )


def _gate_a_lifecycle_payload(
    *,
    verified_commitment=None,
    gate_a_report_content_sha256: str = GATE_A_REPORT_SHA256,
    gate_a_passed: bool = True,
    gate_a_ledger_sequence: int = 42,
    gate_a_completed_at_utc: datetime = GATE_A_AT,
    forbidden_seed_namespaces: ForbiddenSeedNamespacesV09 = FORBIDDEN_NAMESPACES,
    executor: Ed25519AttestationSigner = EXECUTOR,
    custodian: Ed25519AttestationSigner = CUSTODIAN,
    enrollment_authority: Ed25519AttestationSigner = ENROLLMENT_AUTHORITY,
) -> dict[str, Any]:
    return make_gate_a_lifecycle_completion_record_v0_9(
        verified_commitment=verified_commitment or _verified_commitment(),
        gate_a_report_content_sha256=gate_a_report_content_sha256,
        gate_a_passed=gate_a_passed,
        gate_a_ledger_sequence=gate_a_ledger_sequence,
        gate_a_completed_at_utc=gate_a_completed_at_utc,
        forbidden_seed_namespaces=forbidden_seed_namespaces,
        executor=executor,
        custodian=custodian,
        enrollment_authority=enrollment_authority,
    )


def _verified_gate_a_lifecycle(
    payload: dict[str, Any] | None = None,
    *,
    verified_commitment=None,
):
    commitment = verified_commitment or _verified_commitment()
    return verify_gate_a_lifecycle_completion_record_v0_9(
        payload or _gate_a_lifecycle_payload(verified_commitment=commitment),
        verified_commitment=commitment,
        expected_verified_gate_a_report_content_sha256=GATE_A_REPORT_SHA256,
        expected_forbidden_seed_namespaces=FORBIDDEN_NAMESPACES,
        trusted_executor=EXECUTOR.verifier(),
        trusted_custodian=CUSTODIAN.verifier(),
        trusted_enrollment_authority=ENROLLMENT_AUTHORITY.verifier(),
    )


def _context(**updates: Any) -> SealedGateBOpeningVerificationContextV09:
    commitment_payload = _commitment_payload()
    verified_commitment = _verified_commitment(commitment_payload)
    lifecycle_payload = _gate_a_lifecycle_payload(verified_commitment=verified_commitment)
    built = verify_and_build_sealed_gate_b_opening_context_v0_9(
        commitment_payload,
        lifecycle_payload,
        expected_immutable_manifest_sha256=MANIFEST_SHA256,
        expected_producer_run_id=PRODUCER_RUN_ID,
        expected_arm_implementation_bundle_sha256=ARM_BUNDLES,
        expected_ledger_identifier=LEDGER_IDENTIFIER,
        expected_freeze_ledger_sequence=40,
        expected_freeze_completed_at_utc=FREEZE_AT,
        trusted_custodian=CUSTODIAN.verifier(),
        trusted_enrollment_authority=ENROLLMENT_AUTHORITY.verifier(),
        verification_time_utc=OPENED_AT,
        trusted_executor=EXECUTOR.verifier(),
        expected_verified_gate_a_report_content_sha256=GATE_A_REPORT_SHA256,
        expected_forbidden_seed_namespaces=FORBIDDEN_NAMESPACES,
        opening_ledger_sequence=43,
        opened_at_utc=OPENED_AT,
    )
    values: dict[str, Any] = built.model_dump(mode="python")
    values.update(updates)
    return SealedGateBOpeningVerificationContextV09(**values)


def _payload(
    *,
    context: SealedGateBOpeningVerificationContextV09 | None = None,
    custodian: Ed25519AttestationSigner = CUSTODIAN,
    world_seeds: tuple[int, ...] = WORLD_SEEDS,
    trajectory_seeds: tuple[int, ...] = TRAJECTORY_SEEDS,
    observation_seeds: tuple[int, ...] = OBSERVATION_SEEDS,
) -> dict[str, Any]:
    return make_sealed_gate_b_opening_v0_9(
        context=context or _context(),
        world_distribution=WORLD_DISTRIBUTION,
        world_seeds=world_seeds,
        trajectory_seeds=trajectory_seeds,
        observation_seeds=observation_seeds,
        estimator=ESTIMATOR,
        bootstrap_draws=EXACT_BOOTSTRAP_DRAWS,
        commitment_nonce=COMMITMENT_NONCE,
        custodian=custodian,
    )


def _rehash(payload: dict[str, Any]) -> None:
    unsigned = dict(payload)
    unsigned.pop("content_sha256", None)
    payload["content_sha256"] = content_sha256(unsigned)


def test_commitment_record_is_dual_signed_and_drives_opening_context() -> None:
    verified = _verified_commitment()
    verified_lifecycle = _verified_gate_a_lifecycle(verified_commitment=verified)
    context = build_sealed_gate_b_opening_context_v0_9(
        verified_commitment=verified,
        verified_gate_a_lifecycle=verified_lifecycle,
        opening_ledger_sequence=43,
        opened_at_utc=OPENED_AT,
    )
    assert context.verified_commitment_record_content_sha256 == verified.content_sha256
    assert (
        context.verified_gate_a_lifecycle_record_content_sha256 == verified_lifecycle.content_sha256
    )
    assert context.expected_sealed_gate_b_commitment_sha256 == COMMITMENT_SHA256
    assert context.expected_opening_attempt_id == OPENING_ATTEMPT_ID
    assert context.commitment_ledger_sequence == 41
    assert context.committed_at_utc == COMMITTED_AT


def _prepared_commitment():
    return prepare_sealed_gate_b_commitment_record_v0_9(
        immutable_manifest_sha256=MANIFEST_SHA256,
        producer_run_id=PRODUCER_RUN_ID,
        arm_implementation_bundle_sha256=ARM_BUNDLES,
        sealed_gate_b_commitment_sha256=COMMITMENT_SHA256,
        opening_attempt_id=OPENING_ATTEMPT_ID,
        ledger_identifier=LEDGER_IDENTIFIER,
        freeze_ledger_sequence=40,
        commitment_ledger_sequence=41,
        freeze_completed_at_utc=FREEZE_AT,
        committed_at_utc=COMMITTED_AT,
        custodian=CUSTODIAN.verifier(),
        enrollment_authority=ENROLLMENT_AUTHORITY.verifier(),
    )


def test_detached_commitment_finalizer_rejects_missing_and_cross_domain_signatures() -> None:
    prepared = _prepared_commitment()
    requests = sealed_gate_b_commitment_signing_requests_v0_9(prepared)
    custodian_signature = sign_detached_request_v0_9(requests["custodian"], signer=CUSTODIAN)
    with pytest.raises(AttestationError, match="carries no attestation"):
        finalize_sealed_gate_b_commitment_record_v0_9(
            prepared,
            custodian_attestation=custodian_signature,
            enrollment_authority_attestation=None,
            trusted_custodian=CUSTODIAN.verifier(),
            trusted_enrollment_authority=ENROLLMENT_AUTHORITY.verifier(),
            verification_time_utc=OPENED_AT,
        )
    cross_domain = ENROLLMENT_AUTHORITY.sign(
        requests["custodian"].domain,
        requests["custodian"].payload,
    )
    with pytest.raises(AttestationError, match=r"domain .* does not match"):
        finalize_sealed_gate_b_commitment_record_v0_9(
            prepared,
            custodian_attestation=custodian_signature,
            enrollment_authority_attestation=cross_domain,
            trusted_custodian=CUSTODIAN.verifier(),
            trusted_enrollment_authority=ENROLLMENT_AUTHORITY.verifier(),
            verification_time_utc=OPENED_AT,
        )


def test_forged_complete_commitment_record_fails_dual_signature() -> None:
    forged = deepcopy(_commitment_payload())
    forged["sealed_gate_b_commitment_sha256"] = "f" * 64
    _rehash(forged)
    with pytest.raises(AttestationError, match="signature does not match"):
        _verified_commitment(forged)


def test_commitment_verifier_rejects_future_commitment_timestamp() -> None:
    with pytest.raises(ValueError, match="commitment is in the verifier's future"):
        _verified_commitment(
            verification_time_utc=COMMITTED_AT - timedelta(microseconds=1),
        )


@pytest.mark.parametrize("attacker_role", ("custodian", "authority"))
def test_attacker_cannot_impersonate_either_commitment_signer(attacker_role: str) -> None:
    attacker = Ed25519AttestationSigner.generate(
        key_id=(CUSTODIAN.key_id if attacker_role == "custodian" else ENROLLMENT_AUTHORITY.key_id)
    )
    payload = _commitment_payload(
        custodian=attacker if attacker_role == "custodian" else CUSTODIAN,
        enrollment_authority=(attacker if attacker_role == "authority" else ENROLLMENT_AUTHORITY),
    )
    with pytest.raises(AttestationError, match=rf"untrusted .*{attacker_role}"):
        _verified_commitment(payload)


@pytest.mark.parametrize(
    ("commitment_sequence", "committed_at", "message"),
    (
        (43, COMMITTED_AT, "ledger sequence"),
        (41, GATE_A_AT + timedelta(seconds=1), "timestamp"),
    ),
)
def test_post_gate_a_commitment_cannot_build_opening_context(
    commitment_sequence: int,
    committed_at: datetime,
    message: str,
) -> None:
    verified = _verified_commitment(
        _commitment_payload(
            commitment_ledger_sequence=commitment_sequence,
            committed_at_utc=committed_at,
        )
    )
    with pytest.raises(ValidationError, match=message):
        _gate_a_lifecycle_payload(verified_commitment=verified)


def test_commitment_ledger_rollback_is_rejected_before_signing() -> None:
    with pytest.raises(ValidationError, match="must follow freeze"):
        _commitment_payload(commitment_ledger_sequence=40)


def test_gate_a_lifecycle_is_content_bound_and_triple_signed() -> None:
    commitment = _verified_commitment()
    lifecycle = _verified_gate_a_lifecycle(verified_commitment=commitment)
    assert lifecycle.record.gate_a_passed is True
    assert lifecycle.record.gate_a_report_content_sha256 == GATE_A_REPORT_SHA256
    assert lifecycle.record.commitment_record_content_sha256 == commitment.content_sha256


def test_detached_lifecycle_finalizer_rejects_missing_and_cross_domain_signatures() -> None:
    commitment = _verified_commitment()
    prepared = prepare_gate_a_lifecycle_completion_record_v0_9(
        verified_commitment=commitment,
        gate_a_report_content_sha256=GATE_A_REPORT_SHA256,
        gate_a_passed=True,
        gate_a_ledger_sequence=42,
        gate_a_completed_at_utc=GATE_A_AT,
        forbidden_seed_namespaces=FORBIDDEN_NAMESPACES,
        executor=EXECUTOR.verifier(),
        custodian=CUSTODIAN.verifier(),
        enrollment_authority=ENROLLMENT_AUTHORITY.verifier(),
    )
    requests = gate_a_lifecycle_signing_requests_v0_9(prepared)
    custodian_signature = sign_detached_request_v0_9(requests["custodian"], signer=CUSTODIAN)
    authority_signature = sign_detached_request_v0_9(
        requests["enrollment_authority"], signer=ENROLLMENT_AUTHORITY
    )
    common = {
        "verified_commitment": commitment,
        "expected_verified_gate_a_report_content_sha256": GATE_A_REPORT_SHA256,
        "expected_forbidden_seed_namespaces": FORBIDDEN_NAMESPACES,
        "trusted_executor": EXECUTOR.verifier(),
        "trusted_custodian": CUSTODIAN.verifier(),
        "trusted_enrollment_authority": ENROLLMENT_AUTHORITY.verifier(),
    }
    with pytest.raises(AttestationError, match="carries no attestation"):
        finalize_gate_a_lifecycle_completion_record_v0_9(
            prepared,
            executor_attestation=None,
            custodian_attestation=custodian_signature,
            enrollment_authority_attestation=authority_signature,
            **common,
        )
    cross_domain = EXECUTOR.sign(
        requests["custodian"].domain,
        requests["custodian"].payload,
    )
    with pytest.raises(AttestationError, match=r"domain .* does not match"):
        finalize_gate_a_lifecycle_completion_record_v0_9(
            prepared,
            executor_attestation=cross_domain,
            custodian_attestation=custodian_signature,
            enrollment_authority_attestation=authority_signature,
            **common,
        )


def test_forged_complete_gate_a_lifecycle_fails_role_signatures() -> None:
    commitment = _verified_commitment()
    forged = deepcopy(_gate_a_lifecycle_payload(verified_commitment=commitment))
    forged["gate_a_report_content_sha256"] = "e" * 64
    _rehash(forged)
    with pytest.raises(ValueError, match="Gate-A report"):
        _verified_gate_a_lifecycle(forged, verified_commitment=commitment)


def test_validly_signed_lifecycle_for_another_gate_a_report_is_rejected() -> None:
    commitment = _verified_commitment()
    substituted = _gate_a_lifecycle_payload(
        verified_commitment=commitment,
        gate_a_report_content_sha256="e" * 64,
    )
    with pytest.raises(ValueError, match="Gate-A report"):
        _verified_gate_a_lifecycle(substituted, verified_commitment=commitment)


def test_empty_or_incomplete_forbidden_namespaces_cannot_authorize_opening() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        ForbiddenSeedNamespacesV09(
            world_manifest_content_sha256="1" * 64,
            gate_a_spec_content_sha256="2" * 64,
            training_split_content_sha256="3" * 64,
            world_seeds=(),
            trajectory_seeds=(),
            observation_seeds=(),
        )
    incomplete = ForbiddenSeedNamespacesV09(
        world_manifest_content_sha256=(FORBIDDEN_NAMESPACES.world_manifest_content_sha256),
        gate_a_spec_content_sha256=FORBIDDEN_NAMESPACES.gate_a_spec_content_sha256,
        training_split_content_sha256=(FORBIDDEN_NAMESPACES.training_split_content_sha256),
        world_seeds=(450_001,),
        trajectory_seeds=(17,),
        observation_seeds=(107,),
    )
    commitment = _verified_commitment()
    signed_incomplete = _gate_a_lifecycle_payload(
        verified_commitment=commitment,
        forbidden_seed_namespaces=incomplete,
    )
    with pytest.raises(ValueError, match="forbidden namespaces"):
        _verified_gate_a_lifecycle(
            signed_incomplete,
            verified_commitment=commitment,
        )


@pytest.mark.parametrize(
    ("role", "message"),
    (
        ("executor", "untrusted executor"),
        ("custodian", "untrusted custodian"),
        ("authority", "untrusted enrollment authority"),
    ),
)
def test_attacker_cannot_impersonate_any_gate_a_lifecycle_witness(
    role: str,
    message: str,
) -> None:
    trusted = {
        "executor": EXECUTOR,
        "custodian": CUSTODIAN,
        "authority": ENROLLMENT_AUTHORITY,
    }
    attacker = Ed25519AttestationSigner.generate(key_id=trusted[role].key_id)
    payload = _gate_a_lifecycle_payload(
        executor=attacker if role == "executor" else EXECUTOR,
        custodian=attacker if role == "custodian" else CUSTODIAN,
        enrollment_authority=(attacker if role == "authority" else ENROLLMENT_AUTHORITY),
    )
    with pytest.raises(AttestationError, match=message):
        _verified_gate_a_lifecycle(payload)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"gate_a_passed": False}, "failed Gate A"),
        ({"gate_a_ledger_sequence": 41}, "must follow Gate-B commitment"),
        ({"gate_a_completed_at_utc": COMMITTED_AT}, "must follow Gate-B commitment"),
    ),
)
def test_gate_a_lifecycle_rejects_false_result_and_ledger_rollback(
    kwargs: dict[str, Any],
    message: str,
) -> None:
    error = ValueError if "gate_a_passed" in kwargs else ValidationError
    with pytest.raises(error, match=message):
        _gate_a_lifecycle_payload(**kwargs)


def test_signed_sealed_opening_positive_path_load_and_recompute(tmp_path: Path) -> None:
    context = _context()
    payload = _payload(context=context)
    opening = verify_sealed_gate_b_opening_v0_9(
        payload,
        context=context,
        trusted_custodian=CUSTODIAN.verifier(),
    )
    assert opening.evaluation_set_role == EVALUATION_SET_ROLE
    assert opening.gate_a_passed is True
    assert opening.arm_implementation_bundle_set_sha256 == IMPLEMENTATION_SET_SHA256

    artifact_path = tmp_path / "sealed-gate-b-opening-v0.9.json"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_and_verify_sealed_gate_b_opening_v0_9(
        artifact_path,
        context=context,
        trusted_custodian=CUSTODIAN.verifier(),
    )
    recomputed = recompute_sealed_gate_b_holdout_v0_9(loaded)
    assert recomputed.opening.opening_attempt_id == OPENING_ATTEMPT_ID
    assert len(recomputed.worlds) == 12
    assert len(recomputed.world_rollouts) == 12 * 3 * 2
    assert len(recomputed.episode_ids) == len(set(recomputed.episode_ids)) == 72


def test_content_hash_tampering_is_rejected_before_trust_checks() -> None:
    forged = deepcopy(_payload())
    forged["producer_run_id"] = "substituted-run"
    with pytest.raises(ValueError, match="content hash mismatch"):
        verify_sealed_gate_b_opening_v0_9(
            forged,
            context=_context(),
            trusted_custodian=CUSTODIAN.verifier(),
        )


def test_forged_but_complete_seed_substitution_fails_independent_commitment() -> None:
    forged = deepcopy(_payload())
    forged["world_seeds"][0] = 599_999
    _rehash(forged)
    with pytest.raises(ValueError, match="independent commitment"):
        verify_sealed_gate_b_opening_v0_9(
            forged,
            context=_context(),
            trusted_custodian=CUSTODIAN.verifier(),
        )


def test_recomputed_commitment_and_content_hash_still_fail_custodian_signature() -> None:
    forged = deepcopy(_payload())
    substituted_world_seeds = (599_999, *WORLD_SEEDS[1:])
    substituted_commitment = sealed_gate_b_commitment_sha256_v0_9(
        immutable_manifest_sha256=MANIFEST_SHA256,
        producer_run_id=PRODUCER_RUN_ID,
        arm_implementation_bundle_set_sha256=IMPLEMENTATION_SET_SHA256,
        world_distribution=WORLD_DISTRIBUTION,
        world_seeds=substituted_world_seeds,
        trajectory_seeds=TRAJECTORY_SEEDS,
        observation_seeds=OBSERVATION_SEEDS,
        estimator=ESTIMATOR,
        bootstrap_draws=EXACT_BOOTSTRAP_DRAWS,
        commitment_nonce=COMMITMENT_NONCE,
    )
    forged["world_seeds"] = list(substituted_world_seeds)
    forged["sealed_gate_b_commitment_sha256"] = substituted_commitment
    _rehash(forged)
    substituted_context = _context(expected_sealed_gate_b_commitment_sha256=substituted_commitment)
    with pytest.raises(AttestationError, match="signature does not match"):
        verify_sealed_gate_b_opening_v0_9(
            forged,
            context=substituted_context,
            trusted_custodian=CUSTODIAN.verifier(),
        )


def test_same_key_id_with_another_key_is_not_a_trusted_custodian() -> None:
    attacker = Ed25519AttestationSigner.generate(key_id=CUSTODIAN.key_id)
    with pytest.raises(ValueError, match="verified lifecycle context"):
        _payload(custodian=attacker)


def test_commitment_custodian_cannot_be_replaced_at_opening() -> None:
    attacker = Ed25519AttestationSigner.generate(key_id="replacement-opening-custodian")
    with pytest.raises(ValueError, match="verified lifecycle context"):
        _payload(custodian=attacker)


@pytest.mark.parametrize(
    "updates",
    (
        {"immutable_manifest_sha256": "c" * 64},
        {"producer_run_id": "substituted-run"},
        {"verified_commitment_record_content_sha256": "c" * 64},
        {"verified_gate_a_lifecycle_record_content_sha256": "c" * 64},
        {"verified_gate_a_report_content_sha256": "d" * 64},
        {
            "arm_implementation_bundle_sha256": {
                **ARM_BUNDLES,
                EXPECTED_ARMS[0]: "e" * 64,
            }
        },
        {"expected_sealed_gate_b_commitment_sha256": "f" * 64},
        {"expected_opening_attempt_id": "different-opening-attempt"},
        {"ledger_identifier": "different-ledger"},
        {"freeze_ledger_sequence": 39},
        {
            "commitment_ledger_sequence": 42,
            "gate_a_ledger_sequence": 43,
            "opening_ledger_sequence": 44,
        },
        {"opening_ledger_sequence": 44},
        {"freeze_completed_at_utc": FREEZE_AT - timedelta(seconds=1)},
        {"committed_at_utc": COMMITTED_AT + timedelta(seconds=1)},
        {"gate_a_completed_at_utc": GATE_A_AT + timedelta(seconds=1)},
        {"opened_at_utc": OPENED_AT + timedelta(seconds=1)},
    ),
)
def test_lifecycle_and_implementation_context_substitution_is_rejected(
    updates: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="verified lifecycle context"):
        verify_sealed_gate_b_opening_v0_9(
            _payload(),
            context=_context(**updates),
            trusted_custodian=CUSTODIAN.verifier(),
        )


@pytest.mark.parametrize(
    ("updates", "message"),
    (
        ({"verified_gate_a_passed": False}, "Input should be True"),
        ({"opening_ledger_sequence": 42}, "ledger sequence"),
        ({"gate_a_ledger_sequence": 41}, "ledger sequence"),
        ({"commitment_ledger_sequence": 40}, "ledger sequence"),
        ({"opened_at_utc": GATE_A_AT}, "timestamps"),
        ({"gate_a_completed_at_utc": COMMITTED_AT}, "timestamps"),
        (
            {
                "opened_at_utc": datetime(
                    2026,
                    9,
                    4,
                    20,
                    tzinfo=timezone(timedelta(hours=8)),
                )
            },
            "must use UTC",
        ),
    ),
)
def test_false_gate_a_or_non_increasing_lifecycle_cannot_form_context(
    updates: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _context(**updates)


@pytest.mark.parametrize(
    ("seed_field", "forbidden_field", "label"),
    (
        (WORLD_SEEDS, "forbidden_world_seeds", "world"),
        (TRAJECTORY_SEEDS, "forbidden_trajectory_seeds", "trajectory"),
        (OBSERVATION_SEEDS, "forbidden_observation_seeds", "observation"),
    ),
)
def test_gate_b_seed_namespaces_must_not_overlap_any_forbidden_set(
    seed_field: tuple[int, ...],
    forbidden_field: str,
    label: str,
) -> None:
    with pytest.raises(ValueError, match=rf"forbidden {label} seeds"):
        verify_sealed_gate_b_opening_v0_9(
            _payload(),
            context=_context(**{forbidden_field: (seed_field[0],)}),
            trusted_custodian=CUSTODIAN.verifier(),
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"world_seeds": WORLD_SEEDS[:-1]}, "exactly 12 world seeds"),
        (
            {"trajectory_seeds": (503, 503, 521)},
            "duplicate trajectory seeds",
        ),
        ({"observation_seeds": (601,)}, "exactly 2 observation seeds"),
    ),
)
def test_exact_seed_cardinality_and_uniqueness_are_enforced(
    kwargs: dict[str, tuple[int, ...]],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _payload(**kwargs)


def test_opening_attempt_is_consumed_exactly_once() -> None:
    context = _context()
    payload = _payload(context=context)
    consumed: set[str] = set()
    verified = verify_and_consume_sealed_gate_b_opening_v0_9(
        payload,
        context=context,
        trusted_custodian=CUSTODIAN.verifier(),
        consumed_attempt_ids=consumed,
    )
    assert consumed == {verified.opening_attempt_id}
    with pytest.raises(ValueError, match="already consumed"):
        verify_and_consume_sealed_gate_b_opening_v0_9(
            payload,
            context=context,
            trusted_custodian=CUSTODIAN.verifier(),
            consumed_attempt_ids=consumed,
        )


def test_recompute_rechecks_commitment_after_nested_record_mutation() -> None:
    opening = verify_sealed_gate_b_opening_v0_9(
        _payload(),
        context=_context(),
        trusted_custodian=CUSTODIAN.verifier(),
    )
    opening.world_distribution["duration_days_inclusive"][0] += 1
    with pytest.raises(ValueError, match="independent commitment"):
        recompute_sealed_gate_b_holdout_v0_9(opening)


def test_implementation_set_requires_exact_arms_and_canonicalizes_input_order() -> None:
    missing = dict(tuple(ARM_BUNDLES.items())[:-1])
    with pytest.raises(ValueError, match="exact ten-arm set"):
        arm_implementation_bundle_set_sha256_v0_9(missing)
    reordered = dict(reversed(tuple(ARM_BUNDLES.items())))
    assert arm_implementation_bundle_set_sha256_v0_9(reordered) == IMPLEMENTATION_SET_SHA256
