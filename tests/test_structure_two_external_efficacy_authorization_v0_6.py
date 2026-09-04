from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner, attested_payload
from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity_v0_2 import (
    external_artifact_sha256,
)
from cpswm.system.evaluation_operations.structure_two_external_efficacy_authorization_v0_6 import (
    run_external_efficacy_authorization_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_external_governance_v0_6 import (
    FrozenGateBManifestV06,
    TrustAnchorRegistryV06,
    attach_frozen_gate_b_role_attestations_v0_6,
    attach_role_enrollment_attestation_v0_6,
    finalize_frozen_gate_b_manifest_v0_6,
    finalize_trust_anchor_registry_v0_6,
    frozen_gate_b_manifest_authority_signing_request_v0_6,
    frozen_gate_b_manifest_signing_requests_v0_6,
    make_frozen_gate_b_manifest_v0_6,
    make_trust_anchor_registry_v0_6,
    prepare_enrolled_role_key_v0_6,
    prepare_frozen_gate_b_manifest_v0_6,
    prepare_trust_anchor_registry_v0_6,
    role_enrollment_signing_request_v0_6,
    trust_anchor_registry_signing_request_v0_6,
    verify_frozen_gate_b_manifest_v0_6,
    verify_trust_anchor_registry_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_frozen_run_v0_8 import (
    GATE_B_EXECUTION_ATTESTATION_DOMAIN,
    FrozenHoldoutOpeningV08,
    GateBExecutionArtifactV08,
    holdout_commitment_sha256_v0_8,
    make_gate_b_execution_artifact_v0_8,
    recompute_frozen_holdout_v0_8,
    validate_canonical_holdout_opening_v0_8,
    validation_seed_commitment_sha256_v0_8,
    verify_gate_b_execution_artifact_v0_8,
    verify_gate_b_proxy_diagnostic_artifact_v0_8,
)
from cpswm.system.evaluation_operations.structure_two_gate_a_v0_6 import (
    EXECUTION_LOG_PROTOCOL_ID,
    INPUT_PROTOCOL_ID,
    GateAArtifactPathsV06,
    make_gate_a_report_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import (
    CANONICAL_COMPONENT_IDS,
    CANONICAL_MECHANISM_EVENTS,
    EXPECTED_ARMS,
)
from cpswm.system.evaluation_operations.structure_two_signed_gate_b_v0_6 import (
    MechanismExecutionLogEntry,
    MechanismTransitionReceipt,
    make_bound_stratified_trace_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4 import (
    compute_producer_source_bundle,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
DRAFT = json.loads(
    (ROOT / "configs/project_two_experiments/structure_two_gate_b_v0_6_DRAFT.json").read_text(
        encoding="utf-8"
    )
)
GATE_A_SPEC = json.loads(
    (ROOT / "configs/project_two_experiments/structure_two_gate_a_v0_6_spec.json").read_text(
        encoding="utf-8"
    )
)
SOURCE_BUNDLE = compute_producer_source_bundle(ROOT).content_sha256
AUTHORITY_NONCE = "a" * 64
V05_MANIFEST = json.loads(
    (
        ROOT / "configs/project_two_experiments/structure_two_world_generator_manifest_v0_5.json"
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
SEED_NONCE = "seed-opening-nonce"
HOLDOUT_NONCE = "holdout-opening-nonce"
VALIDATION_WORLD_SEEDS = tuple(range(450001, 450013))
VALIDATION_SEED = validation_seed_commitment_sha256_v0_8(
    world_seeds=VALIDATION_WORLD_SEEDS,
    trajectory_seeds=(17, 31, 43),
    observation_seeds=(107, 227),
    nonce=SEED_NONCE,
)
HOLDOUT_COMMITMENT = holdout_commitment_sha256_v0_8(
    validation_seed_commitment_sha256=VALIDATION_SEED,
    world_distribution=WORLD_DISTRIBUTION,
    estimator=ESTIMATOR,
    bootstrap_draws=4000,
    nonce=HOLDOUT_NONCE,
)
PRODUCER_RUN_ID = "combined-run"
AUTHORITY = Ed25519AttestationSigner.generate(key_id="external-enrollment-authority")
REVIEWER = Ed25519AttestationSigner.generate(key_id="external-reviewer")
EXECUTOR = Ed25519AttestationSigner.generate(key_id="external-executor")
CUSTODIAN = Ed25519AttestationSigner.generate(key_id="combined-custodian")


def _content_bound_source_register() -> dict[str, Any]:
    source_register = cast(
        dict[str, Any],
        json.loads(
            (
                ROOT
                / "configs/project_two_experiments/structure_two_external_method_sources_v0_2.json"
            ).read_text(encoding="utf-8")
        ),
    )
    source_register.pop("content_sha256")
    for row in source_register["methods"]:
        row["primary_source_sha256"] = content_sha256({"registered-primary-source": row["arm"]})
    source_register["content_sha256"] = content_sha256(source_register)
    return source_register


SOURCE_REGISTER = _content_bound_source_register()
REGISTRY = make_trust_anchor_registry_v0_6(
    role_signers={
        "reviewer": REVIEWER,
        "executor": EXECUTOR,
        "custodian": CUSTODIAN,
    },
    controller_identifiers={
        "reviewer": "review-board-a",
        "executor": "execution-lab-b",
        "custodian": "holdout-custodian-c",
    },
    enrolled_at_utc=datetime(2026, 9, 2, tzinfo=UTC),
    enrollment_authority=AUTHORITY,
)
REGISTRY_RECORD, _ROLE_VERIFIERS = verify_trust_anchor_registry_v0_6(
    REGISTRY, trusted_enrollment_authority=AUTHORITY.verifier()
)
BUNDLES = {arm: content_sha256({"arm": arm, "implementation": "v0.6"}) for arm in EXPECTED_ARMS}


def _make_frozen_manifest(
    source_register: dict[str, Any] = SOURCE_REGISTER,
    registry: dict[str, Any] = REGISTRY,
) -> tuple[dict[str, Any], FrozenGateBManifestV06, TrustAnchorRegistryV06]:
    registry_record, role_verifiers = verify_trust_anchor_registry_v0_6(
        registry, trusted_enrollment_authority=AUTHORITY.verifier()
    )
    frozen = make_frozen_gate_b_manifest_v0_6(
        development_draft=DRAFT,
        gate_a_spec=GATE_A_SPEC,
        trust_anchor_registry=registry,
        source_register_content_sha256=str(source_register["content_sha256"]),
        frozen_at_utc=datetime(2026, 9, 2, 1, tzinfo=UTC),
        freeze_ledger_identifier="external-audit-ledger:test",
        freeze_ledger_sequence=41,
        authority_nonce_sha256=AUTHORITY_NONCE,
        preregistered_producer_run_id=PRODUCER_RUN_ID,
        validation_seed_commitment_sha256=VALIDATION_SEED,
        holdout_commitment_sha256=HOLDOUT_COMMITMENT,
        producer_source_bundle_sha256=SOURCE_BUNDLE,
        arm_implementation_bundle_sha256=BUNDLES,
        enrollment_authority=AUTHORITY,
        reviewer=REVIEWER,
        executor=EXECUTOR,
        custodian=CUSTODIAN,
    )
    record = verify_frozen_gate_b_manifest_v0_6(
        frozen,
        development_draft=DRAFT,
        source_register=source_register,
        gate_a_spec=GATE_A_SPEC,
        trust_anchor_registry=registry_record,
        reviewer=role_verifiers["reviewer"],
        executor=role_verifiers["executor"],
        custodian=role_verifiers["custodian"],
        enrollment_authority=AUTHORITY.verifier(),
    )
    return frozen, record, registry_record


FROZEN_MANIFEST, FROZEN_RECORD, _FROZEN_REGISTRY_RECORD = _make_frozen_manifest()


def _write_content_bound_json(path: Path, payload: dict[str, Any]) -> None:
    payload["content_sha256"] = content_sha256(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _gate_a(
    tmp_path: Path,
    *,
    frozen_record: FrozenGateBManifestV06 = FROZEN_RECORD,
    registry_record: TrustAnchorRegistryV06 = REGISTRY_RECORD,
    passed: bool = True,
) -> tuple[dict[str, Any], GateAArtifactPathsV06]:
    input_path = tmp_path / f"gate-a-input-{frozen_record.immutable_manifest_sha256}.json"
    log_path = tmp_path / f"gate-a-log-{frozen_record.immutable_manifest_sha256}.json"
    opening_path = tmp_path / f"holdout-opening-{frozen_record.immutable_manifest_sha256}.json"
    opening = FrozenHoldoutOpeningV08(
        protocol="structure-two-public-validation-opening@0.8",
        evaluation_set_role="public_preregistered_validation",
        immutable_manifest_sha256=frozen_record.immutable_manifest_sha256,
        producer_run_id=frozen_record.preregistered_producer_run_id,
        seed_opening_nonce=SEED_NONCE,
        holdout_opening_nonce=HOLDOUT_NONCE,
        world_distribution=WORLD_DISTRIBUTION,
        validation_world_seeds=VALIDATION_WORLD_SEEDS,
        trajectory_seeds=(17, 31, 43),
        observation_seeds=(107, 227),
        estimator=ESTIMATOR,
        bootstrap_draws=4000,
    )
    _write_content_bound_json(opening_path, opening.model_dump(mode="json"))
    recomputed = recompute_frozen_holdout_v0_8(opening)
    rollout_ids = [row["rollout_id"] for row in recomputed.rollout_rows]
    common = {
        "immutable_manifest_sha256": frozen_record.immutable_manifest_sha256,
        "producer_run_id": frozen_record.preregistered_producer_run_id,
        "freeze_ledger_identifier": frozen_record.freeze_ledger_identifier,
        "freeze_ledger_sequence": frozen_record.freeze_ledger_sequence,
        "authority_nonce_sha256": frozen_record.authority_nonce_sha256,
        "validation_seed_commitment_sha256": (frozen_record.validation_seed_commitment_sha256),
        "holdout_commitment_sha256": frozen_record.holdout_commitment_sha256,
        "ordered_rollout_ids": rollout_ids,
    }
    _write_content_bound_json(
        input_path,
        {
            "protocol": INPUT_PROTOCOL_ID,
            **common,
            "frozen_holdout_opening_artifact_file_sha256": (external_artifact_sha256(opening_path)),
        },
    )
    metrics = recomputed.metrics
    _write_content_bound_json(
        log_path,
        {
            "protocol": EXECUTION_LOG_PROTOCOL_ID,
            **common,
            "validation_input_bundle_sha256": external_artifact_sha256(input_path),
            "world_rows": recomputed.world_rows,
            "rollout_rows": recomputed.rollout_rows,
            "metrics": metrics,
            "exit_code": 0 if passed else 1,
        },
    )
    paths = GateAArtifactPathsV06(
        validation_input_bundle=input_path,
        deterministic_execution_log=log_path,
        frozen_holdout_opening=opening_path,
    )
    report = make_gate_a_report_v0_6(
        gate_a_spec=GATE_A_SPEC,
        frozen_manifest=frozen_record,
        trust_anchor_registry=registry_record,
        artifact_paths=paths,
        producer_source_bundle_sha256=SOURCE_BUNDLE,
        expected_arm_implementation_bundles=BUNDLES,
        executor=EXECUTOR,
        custodian=CUSTODIAN,
    )
    return report, paths


def _payloads(
    gate_a_sha256: str,
    *,
    manifest_sha256: str,
    producer_run_id: str = PRODUCER_RUN_ID,
) -> tuple[dict[str, object], ...]:
    payloads: list[dict[str, object]] = []
    for arm in EXPECTED_ARMS:
        bundle = BUNDLES[arm]
        state = content_sha256({"arm": arm, "state": "start"})
        logs: list[MechanismExecutionLogEntry] = []
        receipts: list[MechanismTransitionReceipt] = []
        for index, event in enumerate(CANONICAL_MECHANISM_EVENTS[arm]):
            output = content_sha256({"arm": arm, "previous": state, "event": event, "index": index})
            core_transition_payload = {"arm": arm, "event": event}
            core_transition = content_sha256(core_transition_payload)
            log = MechanismExecutionLogEntry(
                sequence_index=index,
                invocation_id=f"{arm}:{index}",
                event=event,
                component_id=CANONICAL_COMPONENT_IDS[arm],
                input_state_sha256=state,
                output_state_sha256=output,
                implementation_bundle_sha256=bundle,
                core_transition_sha256=core_transition,
                core_transition_payload=core_transition_payload,
            )
            logs.append(log)
            receipts.append(
                MechanismTransitionReceipt(
                    invocation_id=log.invocation_id,
                    event=log.event,
                    component_id=log.component_id,
                    input_state_sha256=log.input_state_sha256,
                    output_state_sha256=log.output_state_sha256,
                    implementation_bundle_sha256=bundle,
                    core_transition_sha256=core_transition,
                    execution_log_entry_sha256=log.content_sha256,
                )
            )
            state = output
        action = "care-action" if arm == "care_wm" else f"{arm}-action"
        payloads.append(
            make_bound_stratified_trace_v0_6(
                arm=arm,
                gate_a_content_sha256=gate_a_sha256,
                manifest_sha256=manifest_sha256,
                producer_run_id=producer_run_id,
                producer_source_bundle_sha256=SOURCE_BUNDLE,
                arm_implementation_bundle_sha256=bundle,
                episode_actions=(("episode", (action,)),),
                episode_mechanism_receipts=(("episode", (tuple(receipts),)),),
                episode_execution_log_entries=(("episode", (tuple(logs),)),),
                signer=CUSTODIAN,
            )
        )
    return tuple(payloads)


def _authorize(
    *,
    gate_a_report: dict[str, Any],
    gate_a_paths: GateAArtifactPathsV06,
    frozen_manifest: dict[str, Any] = FROZEN_MANIFEST,
    source_register: dict[str, Any] = SOURCE_REGISTER,
    registry: dict[str, Any] = REGISTRY,
    payloads: tuple[dict[str, object], ...] | None = None,
) -> dict[str, Any]:
    resolved_payloads = payloads or _payloads(
        str(gate_a_report["content_sha256"]),
        manifest_sha256=str(
            frozen_manifest.get(
                "immutable_manifest_sha256",
                FROZEN_RECORD.immutable_manifest_sha256,
            )
        ),
    )
    return run_external_efficacy_authorization_v0_6(
        canonical_gate_b_draft=DRAFT,
        gate_a_spec=GATE_A_SPEC,
        externally_frozen_manifest=frozen_manifest,
        source_register=source_register,
        trust_anchor_registry=registry,
        trusted_enrollment_authority=AUTHORITY.verifier(),
        gate_a_report=gate_a_report,
        gate_a_artifact_paths=gate_a_paths,
        available_inputs_by_arm={},
        input_bundle_paths_by_arm={},
        input_bundle_sha256_by_arm={},
        external_evidence_by_arm={},
        external_artifact_paths_by_arm={},
        source_acquisition_receipts_by_arm={},
        signed_gate_b_payloads=resolved_payloads,
        producer_source_bundle_sha256=SOURCE_BUNDLE,
        expected_arm_implementation_bundles=BUNDLES,
        repository_root=ROOT,
        authorization_time_utc=datetime(2026, 9, 2, 2, tzinfo=UTC),
    )


def test_gate_b_pass_cannot_authorize_without_all_external_artifacts(
    tmp_path: Path,
) -> None:
    gate_a, paths = _gate_a(tmp_path)
    report = _authorize(gate_a_report=gate_a, gate_a_paths=paths)
    assert report["signed_gate_b"]["gate_b_passed"] is False
    assert report["signed_gate_b"]["status"] == "NOT_SCORED_SEALED_HOLDOUT_NOT_VERIFIED"
    assert report["checks"]["gate_a_public_preregistered_validation_only"] is True
    assert report["checks"]["sealed_confirmatory_gate_b_holdout_verified"] is False
    assert report["executor_conformance_verified"] is False
    assert report["six_arm_reference_execution_verified"] is False
    assert (
        report["checks"]["gate_b_actions_from_fidelity_validated_implementation_verified"] is False
    )
    assert report["source_acquisition_receipts_verified"] is False
    assert report["adapter_input_coverage"]["adapter_input_coverage_gate_passed"] is False
    assert report["external_fidelity"]["external_fidelity_gate_passed"] is False
    assert report["checks"]["current_v0_7_dual_gate_receipt_verified"] is False
    assert report["v0_6_gate_b_historical_only"] is True
    assert report["external_method_efficacy_comparison_allowed"] is False


def test_trusted_executor_cannot_sign_forged_gate_b_actions(tmp_path: Path) -> None:
    tiny_distribution = deepcopy(WORLD_DISTRIBUTION)
    tiny_distribution["duration_days_inclusive"] = [40, 40]
    tiny_distribution["location_count_inclusive"] = [3, 3]
    tiny_distribution["guest_actor_count_inclusive"] = [1, 1]
    opening = FrozenHoldoutOpeningV08(
        protocol="structure-two-public-validation-opening@0.8",
        evaluation_set_role="public_preregistered_validation",
        immutable_manifest_sha256="a" * 64,
        producer_run_id="minimal-adversarial-run",
        seed_opening_nonce="s" * 16,
        holdout_opening_nonce="h" * 16,
        world_distribution=tiny_distribution,
        validation_world_seeds=(1,),
        trajectory_seeds=(2,),
        observation_seeds=(3,),
        estimator=ESTIMATOR,
        bootstrap_draws=100,
    )
    opening_path = tmp_path / "minimal-holdout-opening.json"
    _write_content_bound_json(opening_path, opening.model_dump(mode="json"))
    recomputed = recompute_frozen_holdout_v0_8(opening)
    gate_a_content_sha256 = "e" * 64
    payload = make_gate_b_execution_artifact_v0_8(
        recomputed_holdout=recomputed,
        holdout_opening_artifact_file_sha256=external_artifact_sha256(opening_path),
        gate_a_content_sha256=gate_a_content_sha256,
        producer_source_bundle_sha256=SOURCE_BUNDLE,
        arm_implementation_bundle_sha256=BUNDLES,
        six_arm_reference_execution_content_sha256="f" * 64,
        executor=EXECUTOR,
    )
    artifact_path = tmp_path / "gate-b-execution.json"
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    assert payload["protocol"] == "structure-two-gate-b-proxy-diagnostic@0.8"
    assert payload["external_actions_from_fidelity_validated_implementation"] is False
    verified = verify_gate_b_proxy_diagnostic_artifact_v0_8(
        artifact_path,
        recomputed_holdout=recomputed,
        expected_gate_a_content_sha256=gate_a_content_sha256,
        expected_producer_source_bundle_sha256=SOURCE_BUNDLE,
        expected_arm_implementation_bundle_sha256=BUNDLES,
        expected_six_arm_reference_execution_content_sha256="f" * 64,
        expected_holdout_opening_artifact_file_sha256=external_artifact_sha256(opening_path),
        trusted_executor=EXECUTOR.verifier(),
    )
    assert verified.episode_actions_by_arm["corrected_amg"]
    with pytest.raises(ValueError, match="cannot score canonical Gate B"):
        verify_gate_b_execution_artifact_v0_8(
            artifact_path,
            recomputed_holdout=recomputed,
            expected_gate_a_content_sha256=gate_a_content_sha256,
            expected_producer_source_bundle_sha256=SOURCE_BUNDLE,
            expected_arm_implementation_bundle_sha256=BUNDLES,
            expected_six_arm_reference_execution_content_sha256="f" * 64,
            expected_holdout_opening_artifact_file_sha256=external_artifact_sha256(opening_path),
            trusted_executor=EXECUTOR.verifier(),
        )

    forged = deepcopy(payload)
    forged.pop("content_sha256")
    forged["episode_actions_by_arm"]["corrected_amg"][0][1][0] = "forged-action"
    forged["executor_attestation"] = None
    forged_record = GateBExecutionArtifactV08.model_validate(forged)
    forged["executor_attestation"] = EXECUTOR.sign(
        GATE_B_EXECUTION_ATTESTATION_DOMAIN,
        attested_payload(forged_record, exclude=frozenset({"executor_attestation"})),
    ).model_dump(mode="json")
    forged["content_sha256"] = content_sha256(forged)
    artifact_path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(ValueError, match="differ from deterministic arm execution"):
        verify_gate_b_proxy_diagnostic_artifact_v0_8(
            artifact_path,
            recomputed_holdout=recomputed,
            expected_gate_a_content_sha256=gate_a_content_sha256,
            expected_producer_source_bundle_sha256=SOURCE_BUNDLE,
            expected_arm_implementation_bundle_sha256=BUNDLES,
            expected_six_arm_reference_execution_content_sha256="f" * 64,
            expected_holdout_opening_artifact_file_sha256=external_artifact_sha256(opening_path),
            trusted_executor=EXECUTOR.verifier(),
        )


def test_tiny_precommitted_holdout_is_not_the_canonical_gate_a_target() -> None:
    tiny_distribution = deepcopy(WORLD_DISTRIBUTION)
    tiny_distribution["duration_days_inclusive"] = [40, 40]
    tiny_distribution["location_count_inclusive"] = [3, 3]
    tiny_distribution["guest_actor_count_inclusive"] = [1, 1]
    opening = FrozenHoldoutOpeningV08(
        protocol="structure-two-public-validation-opening@0.8",
        evaluation_set_role="public_preregistered_validation",
        immutable_manifest_sha256="a" * 64,
        producer_run_id="attacker-selected-run",
        seed_opening_nonce="s" * 16,
        holdout_opening_nonce="h" * 16,
        world_distribution=tiny_distribution,
        validation_world_seeds=(1,),
        trajectory_seeds=(2,),
        observation_seeds=(3,),
        estimator=ESTIMATOR,
        bootstrap_draws=100,
    )
    with pytest.raises(ValueError, match="preregistered generation plan"):
        validate_canonical_holdout_opening_v0_8(opening, GATE_A_SPEC)
    attacker_spec = deepcopy(GATE_A_SPEC)
    attacker_spec["public_preregistered_validation"].update(
        {
            "world_distribution_sha256": content_sha256(tiny_distribution),
            "validation_world_seeds": [1],
            "trajectory_seeds": [2],
            "observation_seeds": [3],
            "excluded_world_seeds": [410001],
            "bootstrap_draws": 100,
        }
    )
    with pytest.raises(ValueError, match="code-pinned public validation set"):
        validate_canonical_holdout_opening_v0_8(opening, attacker_spec)


def test_holdout_distribution_rejects_invalid_probability_ranges() -> None:
    invalid_distribution = deepcopy(WORLD_DISTRIBUTION)
    invalid_distribution["owner_event_probability"] = [-0.1, 1.1]
    with pytest.raises(ValueError, match="probability range"):
        FrozenHoldoutOpeningV08(
            protocol="structure-two-public-validation-opening@0.8",
            evaluation_set_role="public_preregistered_validation",
            immutable_manifest_sha256="a" * 64,
            producer_run_id="invalid-distribution",
            seed_opening_nonce="s" * 16,
            holdout_opening_nonce="h" * 16,
            world_distribution=invalid_distribution,
            validation_world_seeds=(450001,),
            trajectory_seeds=(17,),
            observation_seeds=(107,),
            estimator=ESTIMATOR,
            bootstrap_draws=100,
        )


def test_custodian_key_cannot_be_reused_as_reviewer_key() -> None:
    with pytest.raises(ValueError, match="pairwise distinct"):
        make_trust_anchor_registry_v0_6(
            role_signers={
                "reviewer": CUSTODIAN,
                "executor": EXECUTOR,
                "custodian": CUSTODIAN,
            },
            controller_identifiers={
                "reviewer": "review-board-a",
                "executor": "execution-lab-b",
                "custodian": "holdout-custodian-c",
            },
            enrolled_at_utc=datetime(2026, 9, 2, tzinfo=UTC),
            enrollment_authority=AUTHORITY,
        )


def test_enrollment_authority_key_cannot_be_reused_as_a_role_key() -> None:
    with pytest.raises(ValueError, match=r"authority.*independent keys"):
        make_trust_anchor_registry_v0_6(
            role_signers={
                "reviewer": AUTHORITY,
                "executor": EXECUTOR,
                "custodian": CUSTODIAN,
            },
            controller_identifiers={
                "reviewer": "authority-also-reviewer",
                "executor": "execution-lab-b",
                "custodian": "holdout-custodian-c",
            },
            enrolled_at_utc=datetime(2026, 9, 2, tzinfo=UTC),
            enrollment_authority=AUTHORITY,
        )


def test_authority_cannot_enroll_a_role_that_did_not_countersign() -> None:
    mutated = deepcopy(REGISTRY)
    mutated.pop("content_sha256")
    mutated["role_keys"][0]["role_attestation"] = None
    identifier_payload = {
        "protocol": mutated["protocol"],
        "role_keys": mutated["role_keys"],
        "enrollment_authority_public_key_sha256": mutated["enrollment_authority_public_key_sha256"],
    }
    mutated["registry_identifier"] = f"sha256:{content_sha256(identifier_payload)}"
    mutated["authority_attestation"] = None
    record = TrustAnchorRegistryV06.model_validate(mutated)
    authority_payload = record.model_dump(mode="json", exclude={"authority_attestation"})
    mutated["authority_attestation"] = AUTHORITY.sign(
        "cpswm.evaluation.structure_two.trust_anchor_registry.v0.6",
        authority_payload,
    ).model_dump(mode="json")
    mutated["content_sha256"] = content_sha256(mutated)

    with pytest.raises(AttestationError, match="carries no attestation"):
        verify_trust_anchor_registry_v0_6(
            mutated,
            trusted_enrollment_authority=AUTHORITY.verifier(),
        )


@pytest.mark.parametrize(
    "missing_attestation",
    ("reviewer_attestation", "executor_attestation", "custodian_attestation"),
)
def test_all_three_enrolled_roles_must_sign_the_freeze(
    tmp_path: Path,
    missing_attestation: str,
) -> None:
    gate_a, paths = _gate_a(tmp_path)
    mutated = deepcopy(FROZEN_MANIFEST)
    mutated.pop("content_sha256")
    mutated[missing_attestation] = None
    mutated["content_sha256"] = content_sha256(mutated)

    with pytest.raises(AttestationError, match="carries no attestation"):
        _authorize(
            gate_a_report=gate_a,
            gate_a_paths=paths,
            frozen_manifest=mutated,
        )


def test_detached_three_role_enrollment_and_freeze_ceremony() -> None:
    signers = {
        "reviewer": Ed25519AttestationSigner.generate(key_id="detached-reviewer"),
        "executor": Ed25519AttestationSigner.generate(key_id="detached-executor"),
        "custodian": Ed25519AttestationSigner.generate(key_id="detached-custodian"),
    }
    authority = Ed25519AttestationSigner.generate(key_id="detached-authority")
    enrolled_rows = []
    for role, controller in zip(
        ("reviewer", "executor", "custodian"),
        ("review-board-x", "execution-lab-y", "holdout-custodian-z"),
        strict=True,
    ):
        row = prepare_enrolled_role_key_v0_6(
            role=role,
            controller_identifier=controller,
            role_verifier=signers[role].verifier(),
            enrolled_at_utc=datetime(2026, 9, 3, tzinfo=UTC),
            enrollment_authority=authority.verifier(),
        )
        domain, payload = role_enrollment_signing_request_v0_6(row)
        enrolled_rows.append(
            attach_role_enrollment_attestation_v0_6(row, signers[role].sign(domain, payload))
        )

    unsigned_registry = prepare_trust_anchor_registry_v0_6(
        role_keys=tuple(enrolled_rows),
        enrollment_authority=authority.verifier(),
    )
    registry_domain, registry_payload = trust_anchor_registry_signing_request_v0_6(
        unsigned_registry
    )
    registry = finalize_trust_anchor_registry_v0_6(
        registry=unsigned_registry,
        authority_attestation=authority.sign(registry_domain, registry_payload),
        trusted_enrollment_authority=authority.verifier(),
    )
    registry_record, role_verifiers = verify_trust_anchor_registry_v0_6(
        registry,
        trusted_enrollment_authority=authority.verifier(),
    )

    unsigned_freeze = prepare_frozen_gate_b_manifest_v0_6(
        development_draft=DRAFT,
        gate_a_spec=GATE_A_SPEC,
        trust_anchor_registry=registry,
        source_register_content_sha256=str(SOURCE_REGISTER["content_sha256"]),
        frozen_at_utc=datetime(2026, 9, 3, 1, tzinfo=UTC),
        freeze_ledger_identifier="external-audit-ledger:detached",
        freeze_ledger_sequence=42,
        authority_nonce_sha256="b" * 64,
        preregistered_producer_run_id="detached-run",
        validation_seed_commitment_sha256=VALIDATION_SEED,
        holdout_commitment_sha256=HOLDOUT_COMMITMENT,
        producer_source_bundle_sha256=SOURCE_BUNDLE,
        arm_implementation_bundle_sha256=BUNDLES,
        trusted_enrollment_authority=authority.verifier(),
    )
    requests = frozen_gate_b_manifest_signing_requests_v0_6(unsigned_freeze)
    role_signed_freeze = attach_frozen_gate_b_role_attestations_v0_6(
        record=unsigned_freeze,
        reviewer_attestation=signers["reviewer"].sign(*requests["reviewer"]),
        executor_attestation=signers["executor"].sign(*requests["executor"]),
        custodian_attestation=signers["custodian"].sign(*requests["custodian"]),
        reviewer=role_verifiers["reviewer"],
        executor=role_verifiers["executor"],
        custodian=role_verifiers["custodian"],
    )
    authority_request = frozen_gate_b_manifest_authority_signing_request_v0_6(
        role_signed_freeze,
        reviewer=role_verifiers["reviewer"],
        executor=role_verifiers["executor"],
        custodian=role_verifiers["custodian"],
        enrollment_authority=authority.verifier(),
    )
    frozen = finalize_frozen_gate_b_manifest_v0_6(
        record=role_signed_freeze,
        authority_attestation=authority.sign(*authority_request),
        reviewer=role_verifiers["reviewer"],
        executor=role_verifiers["executor"],
        custodian=role_verifiers["custodian"],
        enrollment_authority=authority.verifier(),
    )
    verified = verify_frozen_gate_b_manifest_v0_6(
        frozen,
        development_draft=DRAFT,
        source_register=SOURCE_REGISTER,
        gate_a_spec=GATE_A_SPEC,
        trust_anchor_registry=registry_record,
        reviewer=role_verifiers["reviewer"],
        executor=role_verifiers["executor"],
        custodian=role_verifiers["custodian"],
        enrollment_authority=authority.verifier(),
    )
    assert verified.freeze_ledger_sequence == 42


def _prepare_global_unsigned_freeze() -> FrozenGateBManifestV06:
    return prepare_frozen_gate_b_manifest_v0_6(
        development_draft=DRAFT,
        gate_a_spec=GATE_A_SPEC,
        trust_anchor_registry=REGISTRY,
        source_register_content_sha256=str(SOURCE_REGISTER["content_sha256"]),
        frozen_at_utc=datetime(2026, 9, 2, 1, tzinfo=UTC),
        freeze_ledger_identifier="external-audit-ledger:test",
        freeze_ledger_sequence=41,
        authority_nonce_sha256=AUTHORITY_NONCE,
        preregistered_producer_run_id=PRODUCER_RUN_ID,
        validation_seed_commitment_sha256=VALIDATION_SEED,
        holdout_commitment_sha256=HOLDOUT_COMMITMENT,
        producer_source_bundle_sha256=SOURCE_BUNDLE,
        arm_implementation_bundle_sha256=BUNDLES,
        trusted_enrollment_authority=AUTHORITY.verifier(),
    )


def _attach_global_role_freeze(
    unsigned_freeze: FrozenGateBManifestV06,
) -> FrozenGateBManifestV06:
    requests = frozen_gate_b_manifest_signing_requests_v0_6(unsigned_freeze)
    return attach_frozen_gate_b_role_attestations_v0_6(
        record=unsigned_freeze,
        reviewer_attestation=REVIEWER.sign(*requests["reviewer"]),
        executor_attestation=EXECUTOR.sign(*requests["executor"]),
        custodian_attestation=CUSTODIAN.sign(*requests["custodian"]),
        reviewer=REVIEWER.verifier(),
        executor=EXECUTOR.verifier(),
        custodian=CUSTODIAN.verifier(),
    )


def test_authority_signature_made_before_role_freeze_cannot_be_attached() -> None:
    unsigned_freeze = _prepare_global_unsigned_freeze()
    role_requests = frozen_gate_b_manifest_signing_requests_v0_6(unsigned_freeze)
    premature_authority_attestation = AUTHORITY.sign(
        "cpswm.evaluation.structure_two.external_freeze.authority.v0.6",
        role_requests["reviewer"][1],
    )
    role_signed_freeze = _attach_global_role_freeze(unsigned_freeze)

    with pytest.raises(AttestationError, match="does not match record content"):
        finalize_frozen_gate_b_manifest_v0_6(
            record=role_signed_freeze,
            authority_attestation=premature_authority_attestation,
            reviewer=REVIEWER.verifier(),
            executor=EXECUTOR.verifier(),
            custodian=CUSTODIAN.verifier(),
            enrollment_authority=AUTHORITY.verifier(),
        )


@pytest.mark.parametrize(
    ("attestation_field", "key_id"),
    (
        ("reviewer_attestation", REVIEWER.key_id),
        ("executor_attestation", EXECUTOR.key_id),
        ("custodian_attestation", CUSTODIAN.key_id),
    ),
)
def test_replacing_any_role_signature_breaks_the_frozen_manifest(
    attestation_field: str,
    key_id: str,
) -> None:
    mutated = deepcopy(FROZEN_MANIFEST)
    mutated.pop("content_sha256")
    original = FrozenGateBManifestV06.model_validate(mutated)
    base_payload = attested_payload(
        original,
        exclude=frozenset(
            {
                "reviewer_attestation",
                "executor_attestation",
                "custodian_attestation",
                "authority_attestation",
            }
        ),
    )
    attacker = Ed25519AttestationSigner.generate(key_id=key_id)
    original_attestation = getattr(original, attestation_field)
    assert original_attestation is not None
    mutated[attestation_field] = attacker.sign(
        original_attestation.domain,
        base_payload,
    ).model_dump(mode="json")
    mutated["content_sha256"] = content_sha256(mutated)

    with pytest.raises(AttestationError, match="does not match record content"):
        verify_frozen_gate_b_manifest_v0_6(
            mutated,
            development_draft=DRAFT,
            source_register=SOURCE_REGISTER,
            gate_a_spec=GATE_A_SPEC,
            trust_anchor_registry=REGISTRY_RECORD,
            reviewer=REVIEWER.verifier(),
            executor=EXECUTOR.verifier(),
            custodian=CUSTODIAN.verifier(),
            enrollment_authority=AUTHORITY.verifier(),
        )


def test_cross_domain_role_signature_cannot_enter_authority_witness() -> None:
    unsigned_freeze = _prepare_global_unsigned_freeze()
    requests = frozen_gate_b_manifest_signing_requests_v0_6(unsigned_freeze)

    with pytest.raises(AttestationError, match=r"domain .* does not match"):
        attach_frozen_gate_b_role_attestations_v0_6(
            record=unsigned_freeze,
            reviewer_attestation=REVIEWER.sign(
                requests["executor"][0],
                requests["reviewer"][1],
            ),
            executor_attestation=EXECUTOR.sign(*requests["executor"]),
            custodian_attestation=CUSTODIAN.sign(*requests["custodian"]),
            reviewer=REVIEWER.verifier(),
            executor=EXECUTOR.verifier(),
            custodian=CUSTODIAN.verifier(),
        )


def test_failed_gate_a_is_rejected_before_gate_b_scoring(tmp_path: Path) -> None:
    gate_a, paths = _gate_a(tmp_path, passed=False)
    with pytest.raises(ValueError, match="failed Gate A forbids Gate B scoring"):
        _authorize(gate_a_report=gate_a, gate_a_paths=paths)


def test_minimal_self_hashed_gate_a_true_is_rejected(tmp_path: Path) -> None:
    _, paths = _gate_a(tmp_path)
    fake: dict[str, Any] = {
        "protocol": "structure-two-world-validation-gate-a@0.6",
        "gate_a_passed": True,
    }
    fake["content_sha256"] = content_sha256(fake)
    with pytest.raises(ValueError):
        _authorize(gate_a_report=fake, gate_a_paths=paths)


def test_gate_a_aggregate_cannot_diverge_from_per_rollout_evidence(
    tmp_path: Path,
) -> None:
    gate_a, paths = _gate_a(tmp_path)
    execution_log = json.loads(paths.deterministic_execution_log.read_text(encoding="utf-8"))
    execution_log["metrics"]["unique_validation_world_fraction"] = 0.0
    execution_log.pop("content_sha256")
    execution_log["content_sha256"] = content_sha256(execution_log)
    paths.deterministic_execution_log.write_text(json.dumps(execution_log), encoding="utf-8")
    with pytest.raises(ValueError, match="aggregate metrics"):
        _authorize(gate_a_report=gate_a, gate_a_paths=paths)


def test_gate_a_rejects_rehashed_holdout_preimage_substitution(tmp_path: Path) -> None:
    gate_a, paths = _gate_a(tmp_path)
    opening = json.loads(paths.frozen_holdout_opening.read_text(encoding="utf-8"))
    opening["seed_opening_nonce"] = "attacker-seed-nonce"
    opening.pop("content_sha256")
    opening["content_sha256"] = content_sha256(opening)
    paths.frozen_holdout_opening.write_text(json.dumps(opening), encoding="utf-8")
    with pytest.raises(ValueError, match="commitment opening failed"):
        _authorize(gate_a_report=gate_a, gate_a_paths=paths)


def test_attacker_selected_enrollment_authority_is_rejected(tmp_path: Path) -> None:
    gate_a, paths = _gate_a(tmp_path)
    attacker_authority = Ed25519AttestationSigner.generate(key_id="attacker-authority")
    attacker_registry = make_trust_anchor_registry_v0_6(
        role_signers={
            "reviewer": REVIEWER,
            "executor": EXECUTOR,
            "custodian": CUSTODIAN,
        },
        controller_identifiers={
            "reviewer": "review-board-a",
            "executor": "execution-lab-b",
            "custodian": "holdout-custodian-c",
        },
        enrolled_at_utc=datetime(2026, 9, 2, tzinfo=UTC),
        enrollment_authority=attacker_authority,
    )
    with pytest.raises(ValueError, match="attacker-selected authority"):
        _authorize(
            gate_a_report=gate_a,
            gate_a_paths=paths,
            registry=attacker_registry,
        )


def test_registry_context_cannot_be_replayed(tmp_path: Path) -> None:
    gate_a, paths = _gate_a(tmp_path)
    second_registry = make_trust_anchor_registry_v0_6(
        role_signers={
            "reviewer": REVIEWER,
            "executor": EXECUTOR,
            "custodian": CUSTODIAN,
        },
        controller_identifiers={
            "reviewer": "second-review-board",
            "executor": "second-execution-lab",
            "custodian": "second-custodian",
        },
        enrolled_at_utc=datetime(2026, 9, 2, 0, 10, tzinfo=UTC),
        enrollment_authority=AUTHORITY,
    )
    with pytest.raises(ValueError, match="registry binding mismatch"):
        _authorize(
            gate_a_report=gate_a,
            gate_a_paths=paths,
            registry=second_registry,
        )


def test_mutable_development_draft_cannot_substitute_for_frozen_manifest(
    tmp_path: Path,
) -> None:
    gate_a, paths = _gate_a(tmp_path)
    with pytest.raises(ValueError, match="frozen manifest"):
        _authorize(
            gate_a_report=gate_a,
            gate_a_paths=paths,
            frozen_manifest=DRAFT,
        )


def test_rehashed_frozen_manifest_mutation_fails_identifier_check(
    tmp_path: Path,
) -> None:
    gate_a, paths = _gate_a(tmp_path)
    mutated = dict(FROZEN_MANIFEST)
    mutated["immutable_manifest_sha256"] = "f" * 64
    mutated.pop("content_sha256")
    mutated["content_sha256"] = content_sha256(mutated)
    with pytest.raises(ValueError, match="identifier mismatch"):
        _authorize(
            gate_a_report=gate_a,
            gate_a_paths=paths,
            frozen_manifest=mutated,
        )


def test_frozen_manifest_requires_authority_attested_pre_execution_sequence(
    tmp_path: Path,
) -> None:
    gate_a, paths = _gate_a(tmp_path)
    mutated = dict(FROZEN_MANIFEST)
    mutated["freeze_completed_before_evidence_production_attested"] = False
    mutated.pop("content_sha256")
    mutated["content_sha256"] = content_sha256(mutated)
    with pytest.raises(ValueError, match="authority-attested sequencing"):
        _authorize(
            gate_a_report=gate_a,
            gate_a_paths=paths,
            frozen_manifest=mutated,
        )


def test_standalone_authorization_rejects_noncanonical_source_row(
    tmp_path: Path,
) -> None:
    mutated_register = deepcopy(SOURCE_REGISTER)
    mutated_register["methods"][0]["method"] = "attacker-selected-method"
    mutated_register.pop("content_sha256")
    mutated_register["content_sha256"] = content_sha256(mutated_register)
    frozen, frozen_record, registry_record = _make_frozen_manifest(mutated_register)
    gate_a, paths = _gate_a(
        tmp_path,
        frozen_record=frozen_record,
        registry_record=registry_record,
    )
    with pytest.raises(ValueError, match="source-register row is noncanonical"):
        _authorize(
            gate_a_report=gate_a,
            gate_a_paths=paths,
            frozen_manifest=frozen,
            source_register=mutated_register,
        )


def test_gate_b_trace_from_non_preregistered_run_is_rejected(
    tmp_path: Path,
) -> None:
    gate_a, paths = _gate_a(tmp_path)
    traces = _payloads(
        str(gate_a["content_sha256"]),
        manifest_sha256=FROZEN_RECORD.immutable_manifest_sha256,
        producer_run_id="cherry-picked-later-run",
    )
    report = _authorize(gate_a_report=gate_a, gate_a_paths=paths, payloads=traces)
    assert report["signed_gate_b"]["status"] == "NOT_SCORED_SEALED_HOLDOUT_NOT_VERIFIED"
