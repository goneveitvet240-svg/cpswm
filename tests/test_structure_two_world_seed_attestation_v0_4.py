"""Fail-closed tests for the external Structure-Two seed custodian boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations.structure_two_world_seed_attestation_v0_4 import (
    create_seed_block_attestation,
    load_preregistered_freeze_authorization,
    verify_seed_block_attestation,
)


def _manifest(tmp_path: Path, *, seeds: tuple[int, ...], salt: str) -> Path:
    protocol = "structure-two-world-generator@0.2"
    commitments = [
        hashlib.sha256(f"{protocol}:{seed}:{salt}".encode()).hexdigest() for seed in seeds
    ]
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "protocol": protocol,
                "split_policy": {
                    "train_world_seeds": [410001, 410002],
                    "validation_world_seeds": [420001, 420002],
                    "sealed_holdout_world_count": len(seeds),
                    "sealed_holdout_world_seed_commitments": commitments,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _draft(tmp_path: Path, signer: Ed25519AttestationSigner) -> Path:
    path = tmp_path / "draft.json"
    path.write_text(
        json.dumps(
            {
                "freeze_authorization": {
                    "trusted_custodian_key_id": signer.key_id,
                    "trusted_custodian_public_key_sha256": (signer.verifier().public_key_sha256),
                    "user_approval_id": "test-user-approval",
                    "configured_before_custodian_signature": True,
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def test_external_custodian_statement_verifies_without_disclosing_seeds(tmp_path) -> None:
    raw = (880001, 880002, 880003)
    validation = (440001, 440002)
    salt = "custodian-only-salt"
    manifest = _manifest(tmp_path, seeds=raw, salt=salt)
    signer = Ed25519AttestationSigner.generate(key_id="seed-custodian-v1")
    draft = _draft(tmp_path, signer)
    record = create_seed_block_attestation(
        draft_manifest_path=draft,
        base_manifest_path=manifest,
        train_artifact_content_sha256="a" * 64,
        validation_world_seeds=validation,
        raw_holdout_world_seeds=raw,
        custody_salt=salt,
        custodian_run_id="test-custodian-run",
        signer=signer,
    )
    verify_seed_block_attestation(
        record,
        draft_manifest_path=draft,
        base_manifest_path=manifest,
        expected_train_artifact_content_sha256="a" * 64,
        expected_validation_world_seeds=validation,
        trusted_key_id=signer.key_id,
        trusted_public_key_sha256=signer.verifier().public_key_sha256,
    )
    public = json.dumps(record.model_dump(mode="json"))
    assert salt not in public
    assert all(str(seed) not in public for seed in raw)


def test_attestation_creation_rejects_collision_or_wrong_salt(tmp_path) -> None:
    raw = (880001, 880002, 880003)
    salt = "custodian-only-salt"
    manifest = _manifest(tmp_path, seeds=raw, salt=salt)
    signer = Ed25519AttestationSigner.generate(key_id="seed-custodian-v1")
    draft = _draft(tmp_path, signer)
    common = {
        "draft_manifest_path": draft,
        "base_manifest_path": manifest,
        "train_artifact_content_sha256": "a" * 64,
        "raw_holdout_world_seeds": raw,
        "custodian_run_id": "test-custodian-run",
        "signer": signer,
    }
    with pytest.raises(ValueError, match="collide"):
        create_seed_block_attestation(
            **common,
            validation_world_seeds=(440001, 880002),
            custody_salt=salt,
        )
    with pytest.raises(ValueError, match="do not reproduce"):
        create_seed_block_attestation(
            **common,
            validation_world_seeds=(440001, 440002),
            custody_salt="wrong",
        )


def test_attestation_rejects_untrusted_self_selected_key(tmp_path) -> None:
    raw = (880001, 880002, 880003)
    validation = (440001, 440002)
    salt = "custodian-only-salt"
    manifest = _manifest(tmp_path, seeds=raw, salt=salt)
    signer = Ed25519AttestationSigner.generate(key_id="untrusted")
    draft = _draft(tmp_path, signer)
    record = create_seed_block_attestation(
        draft_manifest_path=draft,
        base_manifest_path=manifest,
        train_artifact_content_sha256="a" * 64,
        validation_world_seeds=validation,
        raw_holdout_world_seeds=raw,
        custody_salt=salt,
        custodian_run_id="test-custodian-run",
        signer=signer,
    )
    with pytest.raises(AttestationError, match="public-key hash"):
        verify_seed_block_attestation(
            record,
            draft_manifest_path=draft,
            base_manifest_path=manifest,
            expected_train_artifact_content_sha256="a" * 64,
            expected_validation_world_seeds=validation,
            trusted_key_id=signer.key_id,
            trusted_public_key_sha256="f" * 64,
        )


@pytest.mark.parametrize("colliding_seed", [410001, 420001])
def test_attestation_rejects_holdout_collision_with_any_public_spent_split(
    tmp_path: Path,
    colliding_seed: int,
) -> None:
    raw = (colliding_seed, 880002, 880003)
    salt = "custodian-only-salt"
    manifest = _manifest(tmp_path, seeds=raw, salt=salt)
    signer = Ed25519AttestationSigner.generate(key_id="seed-custodian-v1")
    draft = _draft(tmp_path, signer)
    with pytest.raises(ValueError, match="collide"):
        create_seed_block_attestation(
            draft_manifest_path=draft,
            base_manifest_path=manifest,
            train_artifact_content_sha256="a" * 64,
            validation_world_seeds=(440001, 440002),
            raw_holdout_world_seeds=raw,
            custody_salt=salt,
            custodian_run_id="test-custodian-run",
            signer=signer,
        )


def test_attestation_rejects_validation_collision_with_prior_public_split(tmp_path) -> None:
    raw = (880001, 880002, 880003)
    salt = "custodian-only-salt"
    manifest = _manifest(tmp_path, seeds=raw, salt=salt)
    signer = Ed25519AttestationSigner.generate(key_id="seed-custodian-v1")
    draft = _draft(tmp_path, signer)
    with pytest.raises(ValueError, match="prior validation"):
        create_seed_block_attestation(
            draft_manifest_path=draft,
            base_manifest_path=manifest,
            train_artifact_content_sha256="a" * 64,
            validation_world_seeds=(420001, 440002),
            raw_holdout_world_seeds=raw,
            custody_salt=salt,
            custodian_run_id="test-custodian-run",
            signer=signer,
        )


def test_attestation_requires_preregistered_signing_key(tmp_path) -> None:
    raw = (880001, 880002, 880003)
    salt = "custodian-only-salt"
    manifest = _manifest(tmp_path, seeds=raw, salt=salt)
    trusted = Ed25519AttestationSigner.generate(key_id="trusted")
    untrusted = Ed25519AttestationSigner.generate(key_id="untrusted")
    draft = _draft(tmp_path, trusted)
    with pytest.raises(ValueError, match="key id"):
        create_seed_block_attestation(
            draft_manifest_path=draft,
            base_manifest_path=manifest,
            train_artifact_content_sha256="a" * 64,
            validation_world_seeds=(440001, 440002),
            raw_holdout_world_seeds=raw,
            custody_salt=salt,
            custodian_run_id="test-custodian-run",
            signer=untrusted,
        )


def test_repository_draft_fails_closed_until_user_sets_trust_anchor() -> None:
    root = Path(__file__).resolve().parents[1]
    draft = root / (
        "configs/project_two_experiments/structure_two_world_generator_manifest_v0_4_DRAFT.json"
    )
    with pytest.raises(ValueError, match="not preregistered"):
        load_preregistered_freeze_authorization(draft)
