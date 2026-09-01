from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cpswm.system.attestation import Ed25519AttestationSigner
from cpswm.system.evaluation_operations import structure_two_v0_6_readiness as readiness_module
from cpswm.system.evaluation_operations.structure_two_external_governance_v0_6 import (
    make_trust_anchor_registry_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import (
    EXPECTED_ARMS,
)
from cpswm.system.evaluation_operations.structure_two_v0_6_readiness import (
    DEFAULT_EVIDENCE_INDEX,
    build_v0_6_development_readiness,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]


def test_readiness_preserves_v0_5_negative_and_does_not_invent_v0_6_result() -> None:
    report = build_v0_6_development_readiness(ROOT)
    assert report["historical_v0_5_current_copy_self_consistent"] is True
    assert report["historical_v0_5_inventory_recomputable"] is False
    assert report["historical_v0_5_external_immutability_verified"] is False
    assert report["historical_v0_5_evidence_authenticity_and_integrity_verified"] is False
    assert report["historical_v0_5_gate_b_passed"] is False
    assert report["v0_6_gate_b_scored"] is False
    assert report["design_evidence_ready_for_external_freeze"] is False
    assert report["external_fidelity"]["external_fidelity_gate_passed"] is False
    assert report["adapter_input_coverage"]["gate_b_trace_production_allowed"] is False
    assert report["external_method_source_identification_complete"] is False
    source_rows = {row["arm"]: row for row in report["external_method_source_identification"]}
    assert (
        "primary_source_content_hash_present"
        in source_rows["active_dreaming_matched"]["missing_or_mismatched"]
    )
    assert (
        "primary_source_content_hash_present"
        in source_rows["brainctl_matched"]["missing_or_mismatched"]
    )
    assert len(report["typed_adaptation_input_schema_source_sha256"]) == 64
    assert report["typed_adaptation_input_contract_verified_by_complete_bundle"] is False
    assert report["external_reference_component_core_count"] == 6
    assert report["external_reference_cores_are_native_reproductions"] is False
    assert report["executor_capabilities_verified_by_signed_conformance"] is False
    assert report["bounded_six_arm_execution_runner_implemented"] is False
    assert report["active_dreaming_content_bound_scenario_executor_implemented"] is False
    assert report["active_dreaming_executor_requires_independent_ed25519_receipt"] is False
    assert report["active_dreaming_zero_cluster_fails_closed"] is False
    assert report["active_dreaming_cluster_failure_rule_binding_implemented"] is False
    assert report["active_dreaming_executor_resource_bounds_implemented"] is False
    assert report["active_dreaming_deterministic_failures_are_signed"] is False
    assert report["v0_7_six_arm_reference_execution_run"] is False
    assert report["bounded_execution_is_native_protocol_reproduction"] is False
    assert report["official_component_parity"]["selected_fixture_parity_passed"] is True
    assert report["official_component_parity"]["component_parity_passed"] is False
    assert report["official_component_parity"]["native_protocol_reproduction_passed"] is False
    assert report["official_component_parity"]["adaptation_parity_passed"] is False
    assert report["complete_adaptation_input_bundle_valid"] is False
    assert report["external_implementation_bundles_content_bound"] is False
    assert report["trust_anchor_registry_externally_verified"] is False
    assert report["role_control_independence_attested"] is False
    assert report["role_control_independence_cryptographically_proven"] is False
    assert report["externally_frozen_manifest_verified"] is False
    assert report["gate_a_report_content_bound"] is False
    assert report["lifecycle_state"] == "DEVELOPMENT_EVIDENCE_INCOMPLETE"


def _write_index(tmp_path: Path, **updates: object) -> Path:
    payload = json.loads((ROOT / DEFAULT_EVIDENCE_INDEX).read_text(encoding="utf-8"))
    payload.update(updates)
    payload.pop("content_sha256", None)
    payload["content_sha256"] = content_sha256(payload)
    path = tmp_path / "evidence-index.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_readiness_rejects_caller_supplied_success_fields(tmp_path: Path) -> None:
    index = _write_index(tmp_path, ready_to_freeze=True)
    with pytest.raises(ValueError, match="field set"):
        build_v0_6_development_readiness(ROOT, evidence_index_path=index)


def test_untyped_input_file_cannot_satisfy_six_arm_input_coverage(tmp_path: Path) -> None:
    bundle = tmp_path / "fake-bundle.json"
    bundle.write_text(json.dumps({"protocol": "structure-two-external-adaptation-inputs@0.6"}))
    index = _write_index(
        tmp_path,
        complete_adaptation_input_bundle_path=str(bundle),
        complete_adaptation_input_bundle_sha256=content_sha256(
            json.loads(bundle.read_text(encoding="utf-8"))
        ),
    )
    report = build_v0_6_development_readiness(ROOT, evidence_index_path=index)
    assert report["complete_adaptation_input_bundle_valid"] is False
    assert report["adapter_input_coverage"]["adapter_input_coverage_gate_passed"] is False


def test_legacy_caller_selected_anchor_fields_are_rejected(tmp_path: Path) -> None:
    index = _write_index(
        tmp_path,
        trust_anchors={
            "reviewer": {"key_id": "reviewer", "public_key_sha256": "a" * 64},
            "executor": {"key_id": "executor", "public_key_sha256": "b" * 64},
            "custodian": {"key_id": "custodian", "public_key_sha256": "c" * 64},
        },
    )
    with pytest.raises(ValueError, match="field set"):
        build_v0_6_development_readiness(ROOT, evidence_index_path=index)


def test_self_signed_registry_is_not_enrolled_without_out_of_band_authority(
    tmp_path: Path,
) -> None:
    authority = Ed25519AttestationSigner.generate(key_id="attacker-authority")
    registry = make_trust_anchor_registry_v0_6(
        role_signers={
            "reviewer": Ed25519AttestationSigner.generate(key_id="attacker-reviewer"),
            "executor": Ed25519AttestationSigner.generate(key_id="attacker-executor"),
            "custodian": Ed25519AttestationSigner.generate(key_id="attacker-custodian"),
        },
        controller_identifiers={
            "reviewer": "claimed-a",
            "executor": "claimed-b",
            "custodian": "claimed-c",
        },
        enrolled_at_utc=datetime(2026, 9, 2, tzinfo=UTC),
        enrollment_authority=authority,
    )
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    index = _write_index(tmp_path, trust_anchor_registry_path=str(registry_path))
    report = build_v0_6_development_readiness(ROOT, evidence_index_path=index)
    assert report["trust_anchor_registry_externally_verified"] is False
    assert report["role_control_independence_attested"] is False
    assert "out-of-band" in report["trust_anchor_registry_validation_error"]


def test_minimal_self_hashed_reference_execution_is_not_accepted(
    tmp_path: Path,
) -> None:
    fake: dict[str, object] = {
        "protocol": "structure-two-six-arm-reference-execution@0.7",
        "all_six_reference_cores_executed": True,
    }
    fake["content_sha256"] = content_sha256(fake)
    fake_path = tmp_path / "fake-reference.json"
    fake_path.write_text(json.dumps(fake), encoding="utf-8")
    index = _write_index(tmp_path, reference_execution_report_path=str(fake_path))
    report = build_v0_6_development_readiness(ROOT, evidence_index_path=index)
    assert report["v0_7_six_arm_reference_execution_run"] is False
    assert (
        "prerequisites are incomplete"
        in report["v0_7_six_arm_reference_execution_validation_error"]
    )


def test_failed_gate_a_prevents_gate_b_trace_scoring(tmp_path: Path) -> None:
    gate_a: dict[str, object] = {
        "protocol": "structure-two-world-validation-gate-a@0.6",
        "gate_a_passed": False,
    }
    gate_a["content_sha256"] = content_sha256(gate_a)
    gate_a_path = tmp_path / "gate-a.json"
    gate_a_path.write_text(json.dumps(gate_a), encoding="utf-8")
    dummy_trace = tmp_path / "trace.json"
    dummy_trace.write_text("{}", encoding="utf-8")
    index = _write_index(
        tmp_path,
        gate_a_report_path=str(gate_a_path),
        signed_gate_b_trace_paths=[str(dummy_trace)] * len(EXPECTED_ARMS),
        producer_source_bundle_sha256="d" * 64,
        expected_arm_implementation_bundles={arm: "e" * 64 for arm in EXPECTED_ARMS},
    )
    report = build_v0_6_development_readiness(ROOT, evidence_index_path=index)
    assert report["gate_a_report_content_bound"] is False
    assert report["gate_a_protocol_exact"] is False
    assert report["gate_a_passed"] is False
    assert "prerequisites are incomplete" in report["gate_a_validation_error"]
    assert report["v0_6_gate_b_scored"] is False


def test_duplicate_source_register_arm_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = json.loads(
        (ROOT / readiness_module.DEFAULT_SOURCE_REGISTER).read_text(encoding="utf-8")
    )
    source["methods"].append(dict(source["methods"][0]))
    source.pop("content_sha256")
    source["content_sha256"] = content_sha256(source)
    path = tmp_path / "duplicate-source-register.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setattr(readiness_module, "DEFAULT_SOURCE_REGISTER", path)
    with pytest.raises(ValueError, match="arm set mismatch"):
        build_v0_6_development_readiness(ROOT)


def test_duplicate_reference_core_arm_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = json.loads(
        (ROOT / readiness_module.DEFAULT_REFERENCE_CORE_REGISTER).read_text(encoding="utf-8")
    )
    reference["arms"].append(dict(reference["arms"][0]))
    path = tmp_path / "duplicate-reference-register.json"
    path.write_text(json.dumps(reference), encoding="utf-8")
    monkeypatch.setattr(readiness_module, "DEFAULT_REFERENCE_CORE_REGISTER", path)
    with pytest.raises(ValueError, match="arm set mismatch"):
        build_v0_6_development_readiness(ROOT)
