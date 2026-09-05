from __future__ import annotations

import inspect
import json
import multiprocessing
import os
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity_v0_2 import (
    default_external_method_specifications_v0_2,
)
from cpswm.system.evaluation_operations.structure_two_external_confirmation_gate_v0_9 import (
    EXTERNAL_METHOD_ARMS,
    AuthoritativeLedgerStoreIdentityV09,
    CombinedExternalConfirmationAuthorizationV09,
    ExternalConfirmationBlockedError,
    ExternalConfirmationVerificationInputsV09,
    FidelityArtifactPathsV09,
    FidelityArtifactSnapshotV09,
    FileAuthoritativeOpeningConsumptionStoreV09,
    FourPartySigningKeysV09,
    IndependentVerifierIdentityV09,
    IsolationReceiptArtifactBindingV09,
    OpeningConsumptionLedgerRecordV09,
    OpeningConsumptionStoreVerificationContextV09,
    PublicKeyBindingV09,
    VerifiedMethodFidelityV09,
    derive_stratified_traces_from_canonical_execution_v0_9,
    finalize_opening_consumption_record_v0_9,
    inspect_authoritative_ledger_store_identity_v0_9,
    make_opening_consumption_record_v0_9,
    make_verified_six_method_fidelity_v0_9,
    opening_consumption_authority_signing_request_v0_9,
    opening_consumption_role_signing_requests_v0_9,
    prepare_opening_consumption_record_v0_9,
    prepare_sealed_gate_b_score_v0_9,
    sign_detached_request_v0_9,
    validate_fidelity_freeze_commitment_sequence_v0_9,
    verify_combined_external_confirmation_authorization_v0_9,
    verify_external_confirmation_chain_v0_9,
    verify_opening_consumption_record_v0_9,
    verify_verified_six_method_fidelity_v0_9,
)
from cpswm.system.evaluation_operations.structure_two_gate_a_v0_6 import (
    GateAArtifactPathsV06,
)
from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import (
    EXPECTED_ARMS,
)
from cpswm.system.evaluation_operations.structure_two_sealed_gate_b_opening_v0_9 import (
    EXACT_BOOTSTRAP_DRAWS,
    SealedGateBOpeningVerificationContextV09,
    arm_implementation_bundle_set_sha256_v0_9,
    make_sealed_gate_b_opening_v0_9,
    sealed_gate_b_commitment_sha256_v0_9,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
WORLD_MANIFEST = json.loads(
    (
        ROOT / "configs/project_two_experiments/structure_two_world_generator_manifest_v0_5.json"
    ).read_text(encoding="utf-8")
)
WORLD_DISTRIBUTION = WORLD_MANIFEST["world_distribution"]
ESTIMATOR = {
    key: WORLD_MANIFEST["rolling_visible_history_reference"][key]
    for key in ("window_days", "context_shrinkage_pseudocounts", "owner_probability_threshold")
}

REVIEWER = Ed25519AttestationSigner.generate(key_id="external-reviewer")
EXECUTOR = Ed25519AttestationSigner.generate(key_id="external-executor")
CUSTODIAN = Ed25519AttestationSigner.generate(key_id="external-custodian")
AUTHORITY = Ed25519AttestationSigner.generate(key_id="external-enrollment-authority")
ATTACKER = Ed25519AttestationSigner.generate(key_id="attacker")

MANIFEST_SHA256 = "a" * 64
RUN_ID = "external-confirmation-run-v0.9"
ATTEMPT_ID = "sealed-opening-attempt-0001"
LEDGER_ID = "external-append-only-ledger"
FREEZE_AT = datetime(2026, 9, 4, 8, tzinfo=UTC)
COMMITTED_AT = FREEZE_AT + timedelta(minutes=5)
GATE_A_AT = COMMITTED_AT + timedelta(minutes=5)
OPENED_AT = GATE_A_AT + timedelta(minutes=5)
CONSUMED_AT = OPENED_AT + timedelta(minutes=5)
ARM_BUNDLES = {arm: content_sha256({"arm": arm}) for arm in EXPECTED_ARMS}
IMPLEMENTATION_SET_SHA256 = arm_implementation_bundle_set_sha256_v0_9(ARM_BUNDLES)
WORLD_SEEDS = tuple(range(700_001, 700_013))
TRAJECTORY_SEEDS = (701, 709, 719)
OBSERVATION_SEEDS = (727, 733)
NONCE = "sealed-opening-secret-nonce-0001"
COMMITMENT = sealed_gate_b_commitment_sha256_v0_9(
    immutable_manifest_sha256=MANIFEST_SHA256,
    producer_run_id=RUN_ID,
    arm_implementation_bundle_set_sha256=IMPLEMENTATION_SET_SHA256,
    world_distribution=WORLD_DISTRIBUTION,
    world_seeds=WORLD_SEEDS,
    trajectory_seeds=TRAJECTORY_SEEDS,
    observation_seeds=OBSERVATION_SEEDS,
    estimator=ESTIMATOR,
    bootstrap_draws=EXACT_BOOTSTRAP_DRAWS,
    commitment_nonce=NONCE,
)


def _context() -> SealedGateBOpeningVerificationContextV09:
    custodian = CUSTODIAN.verifier()
    return SealedGateBOpeningVerificationContextV09(
        immutable_manifest_sha256=MANIFEST_SHA256,
        producer_run_id=RUN_ID,
        verified_commitment_record_content_sha256="b" * 64,
        verified_gate_a_lifecycle_record_content_sha256="c" * 64,
        verified_gate_a_report_content_sha256="d" * 64,
        verified_gate_a_passed=True,
        arm_implementation_bundle_sha256=ARM_BUNDLES,
        expected_sealed_gate_b_commitment_sha256=COMMITMENT,
        expected_opening_attempt_id=ATTEMPT_ID,
        committed_custodian_key_id=custodian.key_id,
        committed_custodian_public_key_base64=custodian.public_key_base64,
        committed_custodian_public_key_sha256=custodian.public_key_sha256,
        ledger_identifier=LEDGER_ID,
        freeze_ledger_sequence=10,
        commitment_ledger_sequence=11,
        gate_a_ledger_sequence=12,
        opening_ledger_sequence=13,
        freeze_completed_at_utc=FREEZE_AT,
        committed_at_utc=COMMITTED_AT,
        gate_a_completed_at_utc=GATE_A_AT,
        opened_at_utc=OPENED_AT,
        forbidden_seed_namespaces_sha256="e" * 64,
        forbidden_world_seeds=(1,),
        forbidden_trajectory_seeds=(2,),
        forbidden_observation_seeds=(3,),
    )


def _opening_payload() -> dict[str, Any]:
    return make_sealed_gate_b_opening_v0_9(
        context=_context(),
        world_distribution=WORLD_DISTRIBUTION,
        world_seeds=WORLD_SEEDS,
        trajectory_seeds=TRAJECTORY_SEEDS,
        observation_seeds=OBSERVATION_SEEDS,
        estimator=ESTIMATOR,
        bootstrap_draws=EXACT_BOOTSTRAP_DRAWS,
        commitment_nonce=NONCE,
        custodian=CUSTODIAN,
    )


def _consumption_payload() -> dict[str, Any]:
    opening = _opening_payload()
    return make_opening_consumption_record_v0_9(
        opening_payload=opening,
        opening_context=_context(),
        previous_ledger_head_sha256=opening["content_sha256"],
        previous_ledger_sequence=13,
        consumption_ledger_sequence=14,
        consumed_at_utc=CONSUMED_AT,
        reviewer=REVIEWER,
        executor=EXECUTOR,
        custodian=CUSTODIAN,
        enrollment_authority=AUTHORITY,
    )


def _verify_consumption(
    payload: dict[str, Any],
    *,
    consumed: frozenset[str] = frozenset(),
    previous_head: str | None = None,
):
    opening = _opening_payload()
    return verify_opening_consumption_record_v0_9(
        payload,
        expected_opening_content_sha256=opening["content_sha256"],
        expected_opening_attempt_id=ATTEMPT_ID,
        expected_immutable_manifest_sha256=MANIFEST_SHA256,
        expected_producer_run_id=RUN_ID,
        expected_ledger_identifier=LEDGER_ID,
        expected_previous_ledger_head_sha256=previous_head or opening["content_sha256"],
        expected_previous_ledger_sequence=13,
        expected_consumption_ledger_sequence=14,
        already_consumed_attempt_ids=consumed,
        trusted_reviewer=REVIEWER.verifier(),
        trusted_executor=EXECUTOR.verifier(),
        trusted_custodian=CUSTODIAN.verifier(),
        trusted_enrollment_authority=AUTHORITY.verifier(),
    )


def _store_verification() -> OpeningConsumptionStoreVerificationContextV09:
    return OpeningConsumptionStoreVerificationContextV09(
        opening_payload=_opening_payload(),
        opening_context=_context(),
        trusted_opening_custodian=CUSTODIAN.verifier(),
        trusted_reviewer=REVIEWER.verifier(),
        trusted_executor=EXECUTOR.verifier(),
        trusted_consumption_custodian=CUSTODIAN.verifier(),
        trusted_enrollment_authority=AUTHORITY.verifier(),
    )


def _file_store(
    root: Path,
) -> tuple[
    FileAuthoritativeOpeningConsumptionStoreV09,
    AuthoritativeLedgerStoreIdentityV09,
]:
    root.chmod(0o700)
    identity = inspect_authoritative_ledger_store_identity_v0_9(
        ledger_root=root,
        ledger_identifier=LEDGER_ID,
        authority_identifier=AUTHORITY.key_id,
        expected_owner_uid=os.getuid(),
    )
    return (
        FileAuthoritativeOpeningConsumptionStoreV09(
            ledger_root=root,
            expected_identity=identity,
        ),
        identity,
    )


def _resign_consumption(
    source_payload: dict[str, Any],
    **updates: Any,
) -> dict[str, Any]:
    unsigned = dict(source_payload)
    unsigned.pop("content_sha256")
    for field in (
        "reviewer_attestation",
        "executor_attestation",
        "custodian_attestation",
        "enrollment_authority_attestation",
    ):
        unsigned[field] = None
    prepared = OpeningConsumptionLedgerRecordV09.model_validate(unsigned).model_copy(update=updates)
    requests = opening_consumption_role_signing_requests_v0_9(prepared)
    reviewer_attestation = sign_detached_request_v0_9(requests["reviewer"], signer=REVIEWER)
    executor_attestation = sign_detached_request_v0_9(requests["executor"], signer=EXECUTOR)
    custodian_attestation = sign_detached_request_v0_9(requests["custodian"], signer=CUSTODIAN)
    authority_request = opening_consumption_authority_signing_request_v0_9(
        prepared,
        reviewer_attestation=reviewer_attestation,
        executor_attestation=executor_attestation,
        custodian_attestation=custodian_attestation,
    )
    return finalize_opening_consumption_record_v0_9(
        prepared,
        reviewer_attestation=reviewer_attestation,
        executor_attestation=executor_attestation,
        custodian_attestation=custodian_attestation,
        enrollment_authority_attestation=sign_detached_request_v0_9(
            authority_request,
            signer=AUTHORITY,
        ),
        trusted_reviewer=REVIEWER.verifier(),
        trusted_executor=EXECUTOR.verifier(),
        trusted_custodian=CUSTODIAN.verifier(),
        trusted_enrollment_authority=AUTHORITY.verifier(),
    )


def _append_consumption_in_forked_process(
    root: str,
    identity_payload: dict[str, Any],
    consumption_payload: dict[str, Any],
    start: Any,
    results: Any,
) -> None:
    store = FileAuthoritativeOpeningConsumptionStoreV09(
        ledger_root=Path(root),
        expected_identity=AuthoritativeLedgerStoreIdentityV09.model_validate(identity_payload),
    )
    start.wait()
    try:
        store.append_verified_consumption(
            consumption_payload,
            verification=_store_verification(),
        )
    except Exception as exc:
        results.put((type(exc).__name__, str(exc)))
    else:
        results.put(("ok", ""))


def test_opening_consumption_produces_signed_append_only_head() -> None:
    payload = _consumption_payload()
    head = _verify_consumption(payload)

    assert head.head_sha256 == payload["content_sha256"]
    assert head.previous_head_sha256 == _opening_payload()["content_sha256"]
    assert head.ledger_sequence == 14
    assert head.consumed_attempt_ids == frozenset({ATTEMPT_ID})


def test_authority_request_is_unavailable_until_all_three_roles_sign() -> None:
    opening = _opening_payload()
    prepared = prepare_opening_consumption_record_v0_9(
        opening_payload=opening,
        opening_context=_context(),
        trusted_opening_custodian=CUSTODIAN.verifier(),
        previous_ledger_head_sha256=opening["content_sha256"],
        previous_ledger_sequence=13,
        consumption_ledger_sequence=14,
        consumed_at_utc=CONSUMED_AT,
        reviewer=REVIEWER.verifier(),
        executor=EXECUTOR.verifier(),
        custodian=CUSTODIAN.verifier(),
        enrollment_authority=AUTHORITY.verifier(),
    )
    requests = opening_consumption_role_signing_requests_v0_9(prepared)

    with pytest.raises(AttestationError):
        opening_consumption_authority_signing_request_v0_9(
            prepared,
            reviewer_attestation=sign_detached_request_v0_9(requests["reviewer"], signer=REVIEWER),
            executor_attestation=None,
            custodian_attestation=sign_detached_request_v0_9(
                requests["custodian"], signer=CUSTODIAN
            ),
        )


def test_authority_witness_binds_the_three_role_signatures() -> None:
    payload = _consumption_payload()
    forged = deepcopy(payload)
    forged["executor_attestation"] = forged["reviewer_attestation"]
    forged.pop("content_sha256")
    forged["content_sha256"] = content_sha256(forged)

    with pytest.raises(AttestationError):
        _verify_consumption(forged)


def test_opening_consumption_rejects_replay() -> None:
    with pytest.raises(ValueError, match="already been consumed"):
        _verify_consumption(_consumption_payload(), consumed=frozenset({ATTEMPT_ID}))


def test_opening_consumption_rejects_forked_or_stale_head() -> None:
    with pytest.raises(ValueError, match="replayed, stale, forked, or cross-run"):
        _verify_consumption(_consumption_payload(), previous_head="f" * 64)


def test_opening_consumption_rejects_attacker_selected_role_key() -> None:
    with pytest.raises(AttestationError, match="outside the enrolled trust registry"):
        verify_opening_consumption_record_v0_9(
            _consumption_payload(),
            expected_opening_content_sha256=_opening_payload()["content_sha256"],
            expected_opening_attempt_id=ATTEMPT_ID,
            expected_immutable_manifest_sha256=MANIFEST_SHA256,
            expected_producer_run_id=RUN_ID,
            expected_ledger_identifier=LEDGER_ID,
            expected_previous_ledger_head_sha256=_opening_payload()["content_sha256"],
            expected_previous_ledger_sequence=13,
            expected_consumption_ledger_sequence=14,
            already_consumed_attempt_ids=frozenset(),
            trusted_reviewer=ATTACKER.verifier(),
            trusted_executor=EXECUTOR.verifier(),
            trusted_custodian=CUSTODIAN.verifier(),
            trusted_enrollment_authority=AUTHORITY.verifier(),
        )


def test_consumption_sequence_cannot_skip_or_rollback() -> None:
    opening = _opening_payload()
    with pytest.raises(ValidationError, match="append exactly one record"):
        prepare_opening_consumption_record_v0_9(
            opening_payload=opening,
            opening_context=_context(),
            trusted_opening_custodian=CUSTODIAN.verifier(),
            previous_ledger_head_sha256=opening["content_sha256"],
            previous_ledger_sequence=13,
            consumption_ledger_sequence=13,
            consumed_at_utc=CONSUMED_AT,
            reviewer=REVIEWER.verifier(),
            executor=EXECUTOR.verifier(),
            custodian=CUSTODIAN.verifier(),
            enrollment_authority=AUTHORITY.verifier(),
        )


def test_authoritative_store_rejects_replay_across_instances_and_restart(
    tmp_path: Path,
) -> None:
    store, identity = _file_store(tmp_path)
    verification = _store_verification()
    payload = _consumption_payload()
    store.initialize_verified_opening(verification=verification)
    first_head = store.append_verified_consumption(payload, verification=verification)

    restarted = FileAuthoritativeOpeningConsumptionStoreV09(
        ledger_root=tmp_path,
        expected_identity=identity,
    )
    current_head = restarted.read_verified_current_consumption_head(
        payload,
        verification=verification,
    )
    assert current_head == first_head
    with pytest.raises(ValueError, match="already been consumed"):
        restarted.append_verified_consumption(payload, verification=verification)


def test_authoritative_store_serializes_cross_process_compare_and_swap(
    tmp_path: Path,
) -> None:
    store, identity = _file_store(tmp_path)
    store.initialize_verified_opening(verification=_store_verification())
    payload = _consumption_payload()
    process_context = multiprocessing.get_context("fork")
    start = process_context.Event()
    results = process_context.Queue()
    workers = tuple(
        process_context.Process(
            target=_append_consumption_in_forked_process,
            args=(
                str(tmp_path),
                identity.model_dump(mode="json"),
                payload,
                start,
                results,
            ),
        )
        for _ in range(2)
    )
    for worker in workers:
        worker.start()
    start.set()
    for worker in workers:
        worker.join(timeout=10)
        assert worker.exitcode == 0
    outcomes = tuple(results.get(timeout=2) for _ in workers)

    assert sum(kind == "ok" for kind, _ in outcomes) == 1
    rejected = tuple(message for kind, message in outcomes if kind == "ValueError")
    assert len(rejected) == 1
    assert "already been consumed" in rejected[0]


def test_authoritative_store_rejects_validly_signed_fork(tmp_path: Path) -> None:
    store, _ = _file_store(tmp_path)
    verification = _store_verification()
    store.initialize_verified_opening(verification=verification)
    fork = _resign_consumption(
        _consumption_payload(),
        previous_ledger_head_sha256="f" * 64,
    )

    with pytest.raises(ValueError, match="replayed, stale, forked, or cross-run"):
        store.append_verified_consumption(fork, verification=verification)


def test_authoritative_store_detects_physical_log_rollback_after_restart(
    tmp_path: Path,
) -> None:
    store, identity = _file_store(tmp_path)
    verification = _store_verification()
    payload = _consumption_payload()
    store.initialize_verified_opening(verification=verification)
    opening_only_log = store.ledger_path.read_bytes()
    store.append_verified_consumption(payload, verification=verification)

    # Simulate restoring the old append-only log without restoring its separately
    # atomically committed current-head checkpoint.
    store.ledger_path.write_bytes(opening_only_log)
    restarted = FileAuthoritativeOpeningConsumptionStoreV09(
        ledger_root=tmp_path,
        expected_identity=identity,
    )
    with pytest.raises(ValueError, match="log and current-head checkpoint disagree"):
        restarted.read_verified_current_consumption_head(
            payload,
            verification=verification,
        )


def test_authoritative_store_rejects_symlink_root_and_ledger_file(tmp_path: Path) -> None:
    real_root = tmp_path / "authority-root"
    real_root.mkdir(mode=0o700)
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(ValueError, match="must not contain symlinks"):
        inspect_authoritative_ledger_store_identity_v0_9(
            ledger_root=linked_root,
            ledger_identifier=LEDGER_ID,
            authority_identifier=AUTHORITY.key_id,
            expected_owner_uid=os.getuid(),
        )

    store, _ = _file_store(real_root)
    attacker_file = tmp_path / "attacker-ledger"
    attacker_file.write_text("{}\n", encoding="utf-8")
    attacker_file.chmod(0o600)
    store.ledger_path.symlink_to(attacker_file)
    with pytest.raises(OSError):
        store.initialize_verified_opening(verification=_store_verification())


def test_empty_caller_set_cannot_bypass_authoritative_consumption(tmp_path: Path) -> None:
    payload = _consumption_payload()
    # The pure verifier intentionally remains useful for signature verification.
    # Empty caller state alone is not replay protection and succeeds twice.
    assert _verify_consumption(payload, consumed=frozenset()).opening_attempt_id == ATTEMPT_ID
    assert _verify_consumption(payload, consumed=frozenset()).opening_attempt_id == ATTEMPT_ID

    store, _ = _file_store(tmp_path)
    verification = _store_verification()
    store.initialize_verified_opening(verification=verification)
    store.append_verified_consumption(payload, verification=verification)
    with pytest.raises(ValueError, match="already been consumed"):
        store.append_verified_consumption(payload, verification=verification)
    assert "already_consumed_attempt_ids" not in (
        ExternalConfirmationVerificationInputsV09.__dataclass_fields__
    )


def test_sealed_scorer_has_no_caller_trace_parameter() -> None:
    parameters = inspect.signature(prepare_sealed_gate_b_score_v0_9).parameters
    assert "traces" not in parameters
    assert "canonical_execution_payload" in parameters
    assert "verified_canonical_execution" in parameters


def test_trace_derivation_uses_every_canonical_receipt_in_order() -> None:
    receipts = tuple(
        SimpleNamespace(
            receipt=SimpleNamespace(
                arm=arm,
                episode_id="episode-1",
                action_sequence=(f"action-{index}",),
                mechanism_steps=(SimpleNamespace(mechanism_events=(f"mechanism-{arm}",)),),
            )
        )
        for index, arm in enumerate(EXPECTED_ARMS)
    )
    artifact = SimpleNamespace(
        canonical_arms=EXPECTED_ARMS,
        episode_ids=("episode-1",),
        task_receipts=receipts,
    )

    traces = derive_stratified_traces_from_canonical_execution_v0_9(artifact)  # type: ignore[arg-type]

    assert tuple(row.arm for row in traces) == EXPECTED_ARMS
    assert traces[3].episode_actions == (("episode-1", ("action-3",)),)
    assert traces[3].episode_mechanism_events[0][1][0] == (f"mechanism-{EXPECTED_ARMS[3]}",)


def _dummy_fidelity_snapshot() -> FidelityArtifactSnapshotV09:
    return FidelityArtifactSnapshotV09(
        raw_fidelity_report_artifact_sha256="1" * 64,
        raw_fidelity_report_content_sha256="2" * 64,
        method_evidence_artifact_sha256_by_arm={
            arm: f"{index + 3:x}" * 64 for index, arm in enumerate(EXTERNAL_METHOD_ARMS)
        },
        isolation_receipts_by_arm={
            arm: (
                IsolationReceiptArtifactBindingV09(
                    artifact_sha256=content_sha256({"arm": arm, "kind": "isolation-artifact"}),
                    content_sha256=content_sha256({"arm": arm, "kind": "isolation-content"}),
                    executor_public_key_sha256=content_sha256(
                        {"arm": arm, "kind": "isolation-executor"}
                    ),
                    policy_template_sha256="a" * 64,
                    rendered_profile_sha256=content_sha256(
                        {"arm": arm, "kind": "rendered-profile"}
                    ),
                    verification_context_sha256=content_sha256(
                        {"arm": arm, "kind": "verification-context"}
                    ),
                    formal_isolation_verified=True,
                ),
            )
            for arm in EXTERNAL_METHOD_ARMS
        },
    )


def _dummy_fidelity_rows(
    snapshot: FidelityArtifactSnapshotV09,
) -> tuple[VerifiedMethodFidelityV09, ...]:
    specifications = default_external_method_specifications_v0_2()
    return tuple(
        VerifiedMethodFidelityV09(
            arm=specification.arm,
            method=specification.method,
            primary_source_sha256=content_sha256(
                {"arm": specification.arm, "kind": "primary-source"}
            ),
            implementation_bundle_sha256=ARM_BUNDLES[specification.arm],
            method_evidence_artifact_sha256=(
                snapshot.method_evidence_artifact_sha256_by_arm[specification.arm]
            ),
            isolation_receipts=snapshot.isolation_receipts_by_arm[specification.arm],
            native_reproduction_verified=True,
            native_protocol_recheck_verified=True,
            cross_domain_adaptation_verified=True,
            adaptation_parity_recheck_verified=True,
            isolation_receipts_semantically_verified=True,
        )
        for specification in specifications
    )


def test_typed_six_method_fidelity_binds_raw_snapshot_and_verifier_identity() -> None:
    snapshot = _dummy_fidelity_snapshot()
    rows = _dummy_fidelity_rows(snapshot)
    identity = IndependentVerifierIdentityV09(
        verifier_identifier="external-fidelity-verifier-v0.9",
        implementation_executor_sha256="b" * 64,
        verifier_configuration_sha256="c" * 64,
    )
    payload = make_verified_six_method_fidelity_v0_9(
        immutable_manifest_sha256=MANIFEST_SHA256,
        producer_run_id=RUN_ID,
        artifact_snapshot=snapshot,
        method_results=rows,
        verifier_identity=identity,
        verified_at_utc=CONSUMED_AT,
        reviewer=REVIEWER,
    )

    verified = verify_verified_six_method_fidelity_v0_9(
        payload,
        expected_snapshot=snapshot,
        expected_immutable_manifest_sha256=MANIFEST_SHA256,
        expected_producer_run_id=RUN_ID,
        expected_implementation_bundle_sha256_by_arm={
            row.arm: row.implementation_bundle_sha256 for row in rows
        },
        expected_primary_source_sha256_by_arm={row.arm: row.primary_source_sha256 for row in rows},
        expected_verifier_identity=identity,
        trusted_reviewer=REVIEWER.verifier(),
    )

    assert tuple(row.arm for row in verified.method_results) == EXTERNAL_METHOD_ARMS
    assert verified.verifier_reexecuted_raw_evidence is True


def test_fidelity_cannot_replace_verified_decisions_with_bare_false_boolean() -> None:
    snapshot = _dummy_fidelity_snapshot()
    row = _dummy_fidelity_rows(snapshot)[0].model_dump(mode="python")
    row["native_reproduction_verified"] = False

    with pytest.raises(ValidationError):
        VerifiedMethodFidelityV09.model_validate(row)


def test_fidelity_snapshot_rejects_missing_isolation_evidence() -> None:
    snapshot = _dummy_fidelity_snapshot().model_dump(mode="python")
    snapshot["isolation_receipts_by_arm"][EXTERNAL_METHOD_ARMS[0]] = ()

    with pytest.raises(ValidationError, match="no isolation receipts"):
        FidelityArtifactSnapshotV09.model_validate(snapshot)


def test_fidelity_snapshot_rejects_one_receipt_reused_across_methods() -> None:
    snapshot = _dummy_fidelity_snapshot().model_dump(mode="python")
    first, second = EXTERNAL_METHOD_ARMS[:2]
    snapshot["isolation_receipts_by_arm"][second] = snapshot["isolation_receipts_by_arm"][first]

    with pytest.raises(ValidationError, match="cannot be reused"):
        FidelityArtifactSnapshotV09.model_validate(snapshot)


def test_post_gate_a_fidelity_cannot_complete_a_forged_chain() -> None:
    with pytest.raises(ValueError, match="before the sealed Gate-B commitment"):
        validate_fidelity_freeze_commitment_sequence_v0_9(
            frozen_at_utc=FREEZE_AT,
            fidelity_verified_at_utc=GATE_A_AT + timedelta(minutes=1),
            sealed_commitment_at_utc=COMMITTED_AT,
        )


def _key(signer: Ed25519AttestationSigner) -> PublicKeyBindingV09:
    verifier = signer.verifier()
    return PublicKeyBindingV09(
        key_id=verifier.key_id,
        public_key_base64=verifier.public_key_base64,
        public_key_sha256=verifier.public_key_sha256,
    )


def test_combined_authorization_cannot_precede_sealed_gate_b() -> None:
    keys = FourPartySigningKeysV09(
        reviewer=_key(REVIEWER),
        executor=_key(EXECUTOR),
        custodian=_key(CUSTODIAN),
        enrollment_authority=_key(AUTHORITY),
    )
    base = {
        "immutable_manifest_sha256": "1" * 64,
        "producer_run_id": RUN_ID,
        "trust_anchor_registry_content_sha256": "2" * 64,
        "frozen_manifest_content_sha256": "3" * 64,
        "gate_a_report_content_sha256": "4" * 64,
        "sealed_commitment_content_sha256": "5" * 64,
        "gate_a_lifecycle_content_sha256": "6" * 64,
        "sealed_opening_content_sha256": "7" * 64,
        "authoritative_ledger_store_identity_sha256": "8" * 64,
        "opening_consumption_head_sha256": "8" * 64,
        "canonical_execution_content_sha256": "9" * 64,
        "sealed_gate_b_score_content_sha256": "a" * 64,
        "six_method_fidelity_content_sha256": "b" * 64,
        "canonical_verifier_identity": IndependentVerifierIdentityV09(
            verifier_identifier="canonical-verifier",
            implementation_executor_sha256="c" * 64,
            verifier_configuration_sha256="d" * 64,
        ),
        "fidelity_verifier_identity": IndependentVerifierIdentityV09(
            verifier_identifier="fidelity-verifier",
            implementation_executor_sha256="e" * 64,
            verifier_configuration_sha256="f" * 64,
        ),
        "opening_attempt_id": ATTEMPT_ID,
        "gate_b_passed": True,
        "six_native_reproductions_verified": True,
        "six_adaptation_fidelity_checks_verified": True,
        "real_isolation_evidence_verified": True,
        "combined_authorization_ledger_sequence": 30,
        "sealed_gate_b_ledger_sequence": 30,
        "sealed_gate_b_scored_at_utc": CONSUMED_AT,
        "authorized_at_utc": CONSUMED_AT + timedelta(seconds=1),
        "signing_keys": keys,
    }

    with pytest.raises(ValidationError, match="superseded"):
        CombinedExternalConfirmationAuthorizationV09(**base)


def test_well_formed_v06_combined_authorization_model_is_revoked() -> None:
    """Correct sequencing cannot revive the superseded action-only semantics."""

    keys = FourPartySigningKeysV09(
        reviewer=_key(REVIEWER),
        executor=_key(EXECUTOR),
        custodian=_key(CUSTODIAN),
        enrollment_authority=_key(AUTHORITY),
    )
    with pytest.raises(ValidationError, match="belief AND action AND mechanism"):
        CombinedExternalConfirmationAuthorizationV09(
            immutable_manifest_sha256="1" * 64,
            producer_run_id=RUN_ID,
            trust_anchor_registry_content_sha256="2" * 64,
            frozen_manifest_content_sha256="3" * 64,
            gate_a_report_content_sha256="4" * 64,
            sealed_commitment_content_sha256="5" * 64,
            gate_a_lifecycle_content_sha256="6" * 64,
            sealed_opening_content_sha256="7" * 64,
            authoritative_ledger_store_identity_sha256="8" * 64,
            opening_consumption_head_sha256="9" * 64,
            canonical_execution_content_sha256="a" * 64,
            sealed_gate_b_score_content_sha256="b" * 64,
            six_method_fidelity_content_sha256="c" * 64,
            canonical_verifier_identity=IndependentVerifierIdentityV09(
                verifier_identifier="canonical-verifier",
                implementation_executor_sha256="d" * 64,
                verifier_configuration_sha256="e" * 64,
            ),
            fidelity_verifier_identity=IndependentVerifierIdentityV09(
                verifier_identifier="fidelity-verifier",
                implementation_executor_sha256="f" * 64,
                verifier_configuration_sha256="0" * 64,
            ),
            opening_attempt_id=ATTEMPT_ID,
            gate_b_passed=True,
            six_native_reproductions_verified=True,
            six_adaptation_fidelity_checks_verified=True,
            real_isolation_evidence_verified=True,
            combined_authorization_ledger_sequence=31,
            sealed_gate_b_ledger_sequence=30,
            sealed_gate_b_scored_at_utc=CONSUMED_AT,
            authorized_at_utc=CONSUMED_AT + timedelta(seconds=1),
            signing_keys=keys,
        )


def test_incomplete_or_forged_chain_returns_machine_readable_false_blocker(
    tmp_path: Path,
) -> None:
    identity = IndependentVerifierIdentityV09(
        verifier_identifier="never-called-verifier",
        implementation_executor_sha256="1" * 64,
        verifier_configuration_sha256="2" * 64,
    )
    never_called = SimpleNamespace(identity=identity)
    missing = tmp_path / "missing.json"
    ledger_store, ledger_identity = _file_store(tmp_path)
    inputs = ExternalConfirmationVerificationInputsV09(
        canonical_gate_b_draft={},
        gate_a_spec={},
        externally_frozen_manifest={},
        source_register={},
        trust_anchor_registry={},
        trusted_enrollment_authority=AUTHORITY.verifier(),
        verification_time_utc=CONSUMED_AT + timedelta(minutes=1),
        gate_a_report={"gate_a_passed": True},
        gate_a_artifact_paths=GateAArtifactPathsV06(
            validation_input_bundle=missing,
            deterministic_execution_log=missing,
            frozen_holdout_opening=missing,
        ),
        producer_source_bundle_sha256="3" * 64,
        expected_arm_implementation_bundles=ARM_BUNDLES,
        sealed_commitment_payload={},
        gate_a_lifecycle_payload={},
        forbidden_seed_namespaces=SimpleNamespace(),  # type: ignore[arg-type]
        sealed_opening_payload={},
        opening_consumption_payload={},
        opening_consumption_store=ledger_store,
        expected_opening_consumption_store_identity=ledger_identity,
        canonical_execution_payload={},
        canonical_execution_verifier=never_called,  # type: ignore[arg-type]
        expected_canonical_verifier_identity=identity,
        sealed_gate_b_score_payload={},
        fidelity_artifact_paths=FidelityArtifactPathsV09(
            raw_fidelity_report=missing,
            method_evidence_artifacts_by_arm={},
            isolation_receipt_verifications_by_arm={},
        ),
        fidelity_verifier=never_called,  # type: ignore[arg-type]
        expected_fidelity_verifier_identity=identity,
    )

    with pytest.raises(ExternalConfirmationBlockedError) as caught:
        verify_external_confirmation_chain_v0_9(inputs)

    assert caught.value.report.status == "BLOCKED_FAIL_CLOSED"
    assert caught.value.report.stage == "gate_b_v0_7_receipt_required"
    assert "superseded" in caught.value.report.reason
    assert caught.value.report.external_method_efficacy_comparison_allowed is False


def test_caller_constructed_v06_chain_cannot_reenter_combined_verifier() -> None:
    """Even a forged typed-looking chain cannot skip the v0.7 semantic guard."""

    with pytest.raises(ExternalConfirmationBlockedError) as caught:
        verify_combined_external_confirmation_authorization_v0_9(
            {},
            chain=SimpleNamespace(),  # type: ignore[arg-type]
            trusted_enrollment_authority=AUTHORITY.verifier(),
        )

    assert caught.value.report.stage == "gate_b_v0_7_receipt_required"
    assert caught.value.report.external_method_efficacy_comparison_allowed is False
