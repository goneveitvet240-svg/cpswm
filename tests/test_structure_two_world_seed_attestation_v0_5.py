"""Adversarial tests for fresh v0.5 external-custodian commitments."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_5 import (
    generate_fresh_seed_block_attestation,
    verify_fresh_seed_block_attestation,
)


def _draft(tmp_path: Path, signer: Ed25519AttestationSigner) -> Path:
    path = tmp_path / "v0_5_draft.json"
    path.write_text(
        json.dumps(
            {
                "protocol": "structure-two-world-generator-validation-gate@0.5",
                "status": "DRAFT-trust-anchor-frozen-awaiting-seed-attestation",
                "split_policy": {
                    "train_world_seeds_spent_for_tuning": [410001, 410002],
                    "prior_validation_world_seeds_spent": [420001, 440001],
                    "v0_5_validation_world_seeds_preregistered_not_generated": [450001, 450002],
                    "sealed_holdout_world_count": 4,
                },
                "freeze_authorization": {
                    "trusted_custodian_key_id": signer.key_id,
                    "trusted_custodian_public_key_sha256": (signer.verifier().public_key_sha256),
                    "user_approval_id": "v0.5-test-approval",
                    "configured_before_custodian_seed_generation": True,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_fresh_custodian_record_verifies_without_public_preimage(tmp_path: Path) -> None:
    signer = Ed25519AttestationSigner.generate(key_id="external-v0.5-custodian")
    draft = _draft(tmp_path, signer)
    record, raw, salt = generate_fresh_seed_block_attestation(
        draft_manifest_path=draft,
        train_artifact_content_sha256="a" * 64,
        signer=signer,
        custodian_run_id="external-run-1",
        holdout_seed_count=4,
    )
    verify_fresh_seed_block_attestation(
        record,
        draft_manifest_path=draft,
        expected_train_artifact_content_sha256="a" * 64,
    )
    public = json.dumps(record.model_dump(mode="json"))
    assert salt not in public
    assert all(str(seed) not in public for seed in raw)
    assert len(set(raw)) == 4


def test_wrong_key_or_draft_binding_is_rejected(tmp_path: Path) -> None:
    signer = Ed25519AttestationSigner.generate(key_id="external-v0.5-custodian")
    draft = _draft(tmp_path, signer)
    attacker = Ed25519AttestationSigner.generate(key_id=signer.key_id)
    with pytest.raises(ValueError, match="trust anchor"):
        generate_fresh_seed_block_attestation(
            draft_manifest_path=draft,
            train_artifact_content_sha256="a" * 64,
            signer=attacker,
            custodian_run_id="attacker",
            holdout_seed_count=4,
        )

    record, _, _ = generate_fresh_seed_block_attestation(
        draft_manifest_path=draft,
        train_artifact_content_sha256="a" * 64,
        signer=signer,
        custodian_run_id="external-run-1",
        holdout_seed_count=4,
    )
    payload = json.loads(draft.read_text(encoding="utf-8"))
    payload["split_policy"]["v0_5_validation_world_seeds_preregistered_not_generated"] = [
        450003,
        450004,
    ]
    draft.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AttestationError, match=r"wrong v0\.5 draft"):
        verify_fresh_seed_block_attestation(
            record,
            draft_manifest_path=draft,
            expected_train_artifact_content_sha256="a" * 64,
        )


def test_false_non_disclosure_assertion_cannot_verify(tmp_path: Path) -> None:
    signer = Ed25519AttestationSigner.generate(key_id="external-v0.5-custodian")
    draft = _draft(tmp_path, signer)
    record, _, _ = generate_fresh_seed_block_attestation(
        draft_manifest_path=draft,
        train_artifact_content_sha256="a" * 64,
        signer=signer,
        custodian_run_id="external-run-1",
        holdout_seed_count=4,
    )
    record = record.model_copy(
        update={
            "assertions": record.assertions.model_copy(
                update={
                    "raw_holdout_seeds_and_custody_salt_never_entered_candidate_environment": False
                }
            )
        }
    )
    with pytest.raises(AttestationError, match="false assertion"):
        verify_fresh_seed_block_attestation(
            record,
            draft_manifest_path=draft,
            expected_train_artifact_content_sha256="a" * 64,
        )
