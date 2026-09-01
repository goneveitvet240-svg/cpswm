from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from cpswm.system.attestation import Ed25519AttestationSigner
from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity_v0_2 import (
    external_artifact_sha256,
)
from cpswm.system.evaluation_operations.structure_two_external_efficacy_authorization_v0_6 import (
    run_external_efficacy_authorization_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_external_governance_v0_6 import (
    FrozenGateBManifestV06,
    TrustAnchorRegistryV06,
    make_frozen_gate_b_manifest_v0_6,
    make_trust_anchor_registry_v0_6,
    verify_frozen_gate_b_manifest_v0_6,
    verify_trust_anchor_registry_v0_6,
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
SOURCE_BUNDLE = "c" * 64
AUTHORITY_NONCE = "a" * 64
VALIDATION_SEED = "b" * 64
HOLDOUT_COMMITMENT = "d" * 64
PRODUCER_RUN_ID = "combined-run"
AUTHORITY = Ed25519AttestationSigner.generate(key_id="external-enrollment-authority")
REVIEWER = Ed25519AttestationSigner.generate(key_id="external-reviewer")
EXECUTOR = Ed25519AttestationSigner.generate(key_id="external-executor")
CUSTODIAN = Ed25519AttestationSigner.generate(key_id="combined-custodian")


def _content_bound_source_register() -> dict[str, Any]:
    source_register = json.loads(
        (
            ROOT / "configs/project_two_experiments/structure_two_external_method_sources_v0_2.json"
        ).read_text(encoding="utf-8")
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
REGISTRY_RECORD, _ = verify_trust_anchor_registry_v0_6(
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
        enrollment_authority=AUTHORITY,
        reviewer=REVIEWER,
        custodian=CUSTODIAN,
    )
    record = verify_frozen_gate_b_manifest_v0_6(
        frozen,
        development_draft=DRAFT,
        source_register=source_register,
        gate_a_spec=GATE_A_SPEC,
        trust_anchor_registry=registry_record,
        reviewer=role_verifiers["reviewer"],
        custodian=role_verifiers["custodian"],
        enrollment_authority=AUTHORITY.verifier(),
    )
    return frozen, record, registry_record


FROZEN_MANIFEST, FROZEN_RECORD, _ = _make_frozen_manifest()


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
    common = {
        "immutable_manifest_sha256": frozen_record.immutable_manifest_sha256,
        "producer_run_id": frozen_record.preregistered_producer_run_id,
        "freeze_ledger_identifier": frozen_record.freeze_ledger_identifier,
        "freeze_ledger_sequence": frozen_record.freeze_ledger_sequence,
        "authority_nonce_sha256": frozen_record.authority_nonce_sha256,
        "validation_seed_commitment_sha256": (frozen_record.validation_seed_commitment_sha256),
        "holdout_commitment_sha256": frozen_record.holdout_commitment_sha256,
        "ordered_rollout_ids": ["validation-rollout-001"],
    }
    _write_content_bound_json(
        input_path,
        {"protocol": INPUT_PROTOCOL_ID, **common},
    )
    metrics = {
        str(row["metric"]): float(row["threshold"]) for row in GATE_A_SPEC["criteria"].values()
    }
    if not passed:
        metrics["unique_validation_world_fraction"] = 0.0
    _write_content_bound_json(
        log_path,
        {
            "protocol": EXECUTION_LOG_PROTOCOL_ID,
            **common,
            "validation_input_bundle_sha256": external_artifact_sha256(input_path),
            "rollout_metric_rows": [
                {
                    "rollout_id": "validation-rollout-001",
                    "metrics": metrics,
                }
            ],
            "metrics": metrics,
            "exit_code": 0,
        },
    )
    paths = GateAArtifactPathsV06(
        validation_input_bundle=input_path,
        deterministic_execution_log=log_path,
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
    )


def test_gate_b_pass_cannot_authorize_without_all_external_artifacts(
    tmp_path: Path,
) -> None:
    gate_a, paths = _gate_a(tmp_path)
    report = _authorize(gate_a_report=gate_a, gate_a_paths=paths)
    assert report["signed_gate_b"]["gate_b_passed"] is True
    assert report["executor_conformance_verified"] is False
    assert report["six_arm_reference_execution_verified"] is False
    assert report["source_acquisition_receipts_verified"] is False
    assert report["adapter_input_coverage"]["adapter_input_coverage_gate_passed"] is False
    assert report["external_fidelity"]["external_fidelity_gate_passed"] is False
    assert report["external_method_efficacy_comparison_allowed"] is False


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
    with pytest.raises(ValueError, match="preregistered producer run"):
        _authorize(gate_a_report=gate_a, gate_a_paths=paths, payloads=traces)
