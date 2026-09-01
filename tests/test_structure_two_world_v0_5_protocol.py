"""Two-round adversarial protocol checks for Structure Two v0.5."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations.structure_two_world_gate_b_v0_5 import (
    PROTOCOL_ID,
    _verify_trace,
    make_bound_arm_trace_payload_v0_5,
    verify_gate_b_report_v0_5,
)
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_5 import (
    FROZEN_V0_5_SOURCE_BUNDLE_FILE_COUNT,
    FROZEN_V0_5_SOURCE_BUNDLE_SHA256,
    audit_v0_5_source_bundle_evidence,
    load_preregistered_v0_5_authorization,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / (
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_5_DRAFT.json"
)


def test_round_one_v05_resets_every_compromised_custody_input() -> None:
    payload = json.loads(DRAFT.read_text(encoding="utf-8"))
    reset = payload["protocol_reset"]
    split = payload["split_policy"]

    assert payload["status"] in {
        "DRAFT-awaiting-external-custodian-public-key",
        "DRAFT-trust-anchor-frozen-awaiting-seed-attestation",
    }
    assert reset["v0_4_results_inherited"] is False
    assert reset["v0_4_commitments_inherited"] is False
    assert reset["v0_4_secrets_reused"] is False
    assert split["sealed_holdout_world_seed_commitments"] == []
    assert set(split["v0_5_validation_world_seeds_preregistered_not_generated"]).isdisjoint(
        split["train_world_seeds_spent_for_tuning"]
    )
    assert set(split["v0_5_validation_world_seeds_preregistered_not_generated"]).isdisjoint(
        split["prior_validation_world_seeds_spent"]
    )
    if payload["status"] == "DRAFT-awaiting-external-custodian-public-key":
        with pytest.raises(ValueError, match="trust anchor"):
            load_preregistered_v0_5_authorization(DRAFT)
    else:
        key_id, public_key_sha256, approval_id = load_preregistered_v0_5_authorization(DRAFT)
        assert key_id == payload["freeze_authorization"]["trusted_custodian_key_id"]
        assert (
            public_key_sha256
            == payload["freeze_authorization"]["trusted_custodian_public_key_sha256"]
        )
        assert approval_id == payload["freeze_authorization"]["user_approval_id"]


def test_round_one_frozen_source_bundle_is_bound_and_current_drift_is_explicit() -> None:
    payload = json.loads(DRAFT.read_text(encoding="utf-8"))
    contract = payload["gate_b_contract"]
    audit = audit_v0_5_source_bundle_evidence(ROOT)

    assert contract["producer_source_bundle_file_count"] == FROZEN_V0_5_SOURCE_BUNDLE_FILE_COUNT
    assert contract["producer_source_bundle_sha256"] == FROZEN_V0_5_SOURCE_BUNDLE_SHA256
    assert audit["historical_digest_field_consistency_verified"] is True
    assert audit["signed_trace_content_hashes_verified"] is True
    assert audit["signed_trace_ed25519_verified_against_manifest_trust_anchor"] is True
    assert audit["trace_set_and_result_bindings_verified"] is True
    assert audit["gate_b_result_content_integrity_verified"] is True
    assert audit["trust_anchor_cross_document_consistent"] is True
    assert audit["trust_anchor_externally_immutable"] is False
    assert audit["historical_evidence_authenticity_and_integrity_verified"] is False
    assert audit["historical_inventory_recomputable"] is False
    assert audit["historical_evidence_rewritten"] is False
    assert audit["current_worktree_compatible_with_frozen_v0_5"] is False
    stored_audit = json.loads(
        (
            ROOT / "benchmarks/structure_two/"
            "structure_two_world_source_bundle_v0_5_compatibility_audit.json"
        ).read_text(encoding="utf-8")
    )
    for key, value in audit.items():
        assert stored_audit[key] == value


def test_round_two_trace_rejects_attacker_selected_key() -> None:
    signer = Ed25519AttestationSigner.generate(key_id="trusted-v0.5")
    payload = make_bound_arm_trace_payload_v0_5(
        arm="left",
        gate_a_content_sha256="a" * 64,
        manifest_sha256="b" * 64,
        producer_run_id="run-1",
        producer_source_bundle_sha256="c" * 64,
        episode_predictions=(("rollout-1", ("x",)),),
        signer=signer,
    )
    _verify_trace(
        payload,
        key_id=signer.key_id,
        public_key_sha256=signer.verifier().public_key_sha256,
    )
    attacker = Ed25519AttestationSigner.generate(key_id=signer.key_id)
    with pytest.raises(AttestationError, match="trust anchor"):
        _verify_trace(
            payload,
            key_id=attacker.key_id,
            public_key_sha256=attacker.verifier().public_key_sha256,
        )


def test_round_two_rehashed_trace_still_fails_ed25519_signature() -> None:
    signer = Ed25519AttestationSigner.generate(key_id="trusted-v0.5")
    payload = make_bound_arm_trace_payload_v0_5(
        arm="left",
        gate_a_content_sha256="a" * 64,
        manifest_sha256="b" * 64,
        producer_run_id="run-1",
        producer_source_bundle_sha256="c" * 64,
        episode_predictions=(("rollout-1", ("x",)),),
        signer=signer,
    )
    payload["producer_source_bundle_sha256"] = "d" * 64
    payload.pop("content_sha256")
    payload["content_sha256"] = content_sha256(payload)
    with pytest.raises(AttestationError):
        _verify_trace(
            payload,
            key_id=signer.key_id,
            public_key_sha256=signer.verifier().public_key_sha256,
        )


def _write_report(path: Path, **updates: object) -> None:
    report = {
        "protocol": PROTOCOL_ID,
        "gate_a_passed": True,
        "gate_b": {"gate_b_passed": True},
        "gate_b_passed": True,
        "external_fidelity_gate_passed": False,
        "proxy_method_comparison_allowed": True,
        "official_method_comparison_allowed": False,
        "method_comparison_allowed": False,
    }
    report.update(updates)
    report["content_sha256"] = content_sha256(report)
    path.write_text(json.dumps(report), encoding="utf-8")


def test_round_two_gate_b_cannot_upgrade_proxy_pass_to_official_claim(tmp_path: Path) -> None:
    report = tmp_path / "gate-b.json"
    _write_report(report)
    verified = verify_gate_b_report_v0_5(report, repository_root=ROOT, recompute=False)
    assert verified["proxy_method_comparison_allowed"] is True
    assert verified["official_method_comparison_allowed"] is False

    _write_report(report, official_method_comparison_allowed=True)
    with pytest.raises(ValueError, match="official-method authorization"):
        verify_gate_b_report_v0_5(report, repository_root=ROOT, recompute=False)


def test_round_two_failed_gate_b_cannot_authorize_any_comparison(tmp_path: Path) -> None:
    report = tmp_path / "gate-b.json"
    _write_report(
        report,
        gate_b={"gate_b_passed": False},
        gate_b_passed=False,
        proxy_method_comparison_allowed=True,
    )
    with pytest.raises(ValueError, match="proxy comparison authorization"):
        verify_gate_b_report_v0_5(report, repository_root=ROOT, recompute=False)
