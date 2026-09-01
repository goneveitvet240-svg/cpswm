from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations.structure_two_external_adapter_fidelity_v0_2 import (
    external_artifact_sha256,
)
from cpswm.system.evaluation_operations.structure_two_source_acquisition_v0_6 import (
    make_primary_source_acquisition_receipt_v0_6,
    verify_primary_source_acquisition_receipt_v0_6,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTER = json.loads(
    (
        ROOT / "configs/project_two_experiments/structure_two_external_method_sources_v0_2.json"
    ).read_text(encoding="utf-8")
)
SOURCE_ROW = next(row for row in SOURCE_REGISTER["methods"] if row["arm"] == "corrected_amg")


def _receipt(source: Path, acquirer: Ed25519AttestationSigner) -> dict[str, object]:
    return make_primary_source_acquisition_receipt_v0_6(
        arm="corrected_amg",
        registered_source_url=str(SOURCE_ROW["primary_source_url"]),
        http_final_url="https://doi.org/10.1109/TPAMI.2011.70",
        acquired_at_utc=datetime(2026, 9, 2, tzinfo=UTC),
        source_artifact=source,
        source_register_content_sha256=str(SOURCE_REGISTER["content_sha256"]),
        acquirer=acquirer,
    )


def _registered_row(source: Path) -> dict[str, object]:
    row = dict(SOURCE_ROW)
    row["primary_source_sha256"] = external_artifact_sha256(source)
    return row


def test_signed_source_acquisition_receipt_binds_url_register_and_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"retrieved official paper bytes")
    acquirer = Ed25519AttestationSigner.generate(key_id="external-source-acquirer")
    receipt = _receipt(source, acquirer)
    record = verify_primary_source_acquisition_receipt_v0_6(
        receipt,
        expected_arm="corrected_amg",
        source_row=_registered_row(source),
        source_artifact=source,
        source_register_content_sha256=str(SOURCE_REGISTER["content_sha256"]),
        trusted_acquirer=acquirer.verifier(),
        official_checkout=None,
    )
    assert record.http_final_url == "https://doi.org/10.1109/TPAMI.2011.70"


def test_replacing_source_and_rehashing_register_does_not_replay_old_receipt(
    tmp_path: Path,
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"retrieved official paper bytes")
    acquirer = Ed25519AttestationSigner.generate(key_id="external-source-acquirer")
    receipt = _receipt(source, acquirer)
    registered_row = _registered_row(source)
    source.write_bytes(b"attacker replacement")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        verify_primary_source_acquisition_receipt_v0_6(
            receipt,
            expected_arm="corrected_amg",
            source_row=registered_row,
            source_artifact=source,
            source_register_content_sha256=str(SOURCE_REGISTER["content_sha256"]),
            trusted_acquirer=acquirer.verifier(),
            official_checkout=None,
        )


def test_attacker_signed_source_receipt_is_outside_enrolled_key(tmp_path: Path) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"retrieved official paper bytes")
    attacker = Ed25519AttestationSigner.generate(key_id="attacker-acquirer")
    trusted = Ed25519AttestationSigner.generate(key_id="trusted-acquirer")
    receipt = _receipt(source, attacker)
    with pytest.raises(AttestationError, match="untrusted acquirer"):
        verify_primary_source_acquisition_receipt_v0_6(
            receipt,
            expected_arm="corrected_amg",
            source_row=_registered_row(source),
            source_artifact=source,
            source_register_content_sha256=str(SOURCE_REGISTER["content_sha256"]),
            trusted_acquirer=trusted.verifier(),
            official_checkout=None,
        )


def test_source_receipt_cannot_be_rebound_to_rehashed_source_register(
    tmp_path: Path,
) -> None:
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"retrieved official paper bytes")
    acquirer = Ed25519AttestationSigner.generate(key_id="external-source-acquirer")
    receipt = _receipt(source, acquirer)
    with pytest.raises(ValueError, match="source-register binding mismatch"):
        verify_primary_source_acquisition_receipt_v0_6(
            receipt,
            expected_arm="corrected_amg",
            source_row=_registered_row(source),
            source_artifact=source,
            source_register_content_sha256="f" * 64,
            trusted_acquirer=acquirer.verifier(),
            official_checkout=None,
        )


def test_trusted_receipt_for_wrong_file_does_not_override_registered_hash(
    tmp_path: Path,
) -> None:
    registered = tmp_path / "registered.pdf"
    registered.write_bytes(b"registered official source")
    replacement = tmp_path / "replacement.pdf"
    replacement.write_bytes(b"reviewer-signed replacement")
    acquirer = Ed25519AttestationSigner.generate(key_id="external-source-acquirer")
    receipt = _receipt(replacement, acquirer)
    with pytest.raises(ValueError, match="registered primary-source hash"):
        verify_primary_source_acquisition_receipt_v0_6(
            receipt,
            expected_arm="corrected_amg",
            source_row=_registered_row(registered),
            source_artifact=replacement,
            source_register_content_sha256=str(SOURCE_REGISTER["content_sha256"]),
            trusted_acquirer=acquirer.verifier(),
            official_checkout=None,
        )
