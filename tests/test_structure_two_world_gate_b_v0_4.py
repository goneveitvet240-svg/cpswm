"""Strict-contract tests for Structure-Two v0.4 Gate B."""

from __future__ import annotations

import pytest

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations.structure_two_world_gate_b_v0_4 import (
    ExpectedRollout,
    make_bound_arm_trace_payload,
    validate_and_score_bound_arm_traces,
)
from cpswm.system.reproducibility import content_sha256

GATE_A_HASH = "a" * 64
MANIFEST_HASH = "b" * 64
EXPECTED = (ExpectedRollout("rollout-1", 2), ExpectedRollout("rollout-2", 1))
ARMS = ("left", "right")
SIGNER = Ed25519AttestationSigner.generate(key_id="gate-b-test-custodian")
TRUSTED_KEY_ID = SIGNER.key_id
TRUSTED_PUBLIC_KEY_SHA256 = SIGNER.verifier().public_key_sha256


def _payload(
    arm: str,
    first: tuple[str, ...],
    *,
    rows: tuple[tuple[str, tuple[str, ...]], ...] | None = None,
    gate_a_hash: str = GATE_A_HASH,
    manifest_hash: str = MANIFEST_HASH,
    source_hash: str = "c" * 64,
    producer_run_id: str = "gate-b-test-run",
    signer: Ed25519AttestationSigner = SIGNER,
) -> dict:
    return make_bound_arm_trace_payload(
        arm=arm,
        gate_a_content_sha256=gate_a_hash,
        manifest_sha256=manifest_hash,
        producer_run_id=producer_run_id,
        producer_source_bundle_sha256=source_hash,
        episode_predictions=rows or (("rollout-1", first), ("rollout-2", (f"{arm}-tail",))),
        signer=signer,
    )


def _rehash(payload: dict) -> None:
    unsigned = dict(payload)
    unsigned.pop("content_sha256", None)
    payload["content_sha256"] = content_sha256(unsigned)


def _score(payloads: list[dict]) -> dict:
    return validate_and_score_bound_arm_traces(
        payloads,
        expected_arms=ARMS,
        expected_rollouts=EXPECTED,
        gate_a_content_sha256=GATE_A_HASH,
        manifest_sha256=MANIFEST_HASH,
        trusted_key_id=TRUSTED_KEY_ID,
        trusted_public_key_sha256=TRUSTED_PUBLIC_KEY_SHA256,
        expected_producer_source_bundle_sha256="c" * 64,
    )


def test_exact_complete_bound_arm_set_can_pass() -> None:
    scored = _score([_payload("left", ("a", "b")), _payload("right", ("b", "a"))])
    assert scored["gate_b"]["gate_b_passed"] is True
    assert scored["gate_b"]["minimum_pairwise_prediction_disagreement_rate"] == 1.0
    assert scored["expected_arm_count"] == 2
    assert scored["expected_rollout_count"] == 2


def test_missing_or_extra_arm_is_rejected() -> None:
    with pytest.raises(ValueError, match="arm set mismatch"):
        _score([_payload("left", ("a", "b"))])


def test_wrong_gate_a_binding_is_rejected() -> None:
    wrong = _payload("left", ("a", "b"), gate_a_hash="d" * 64)
    with pytest.raises(ValueError, match="wrong Gate A"):
        _score([wrong, _payload("right", ("b", "a"))])


def test_wrong_manifest_binding_is_rejected() -> None:
    wrong = _payload("left", ("a", "b"), manifest_hash="d" * 64)
    with pytest.raises(ValueError, match="wrong frozen manifest"):
        _score([wrong, _payload("right", ("b", "a"))])


def test_attacker_selected_trace_key_is_rejected() -> None:
    attacker = Ed25519AttestationSigner.generate(key_id="attacker")
    wrong = _payload("left", ("a", "b"), signer=attacker)
    with pytest.raises(AttestationError, match="trust anchor"):
        _score([wrong, _payload("right", ("b", "a"))])


@pytest.mark.parametrize("mutation", ["reorder", "truncate", "duplicate"])
def test_rollout_order_and_sequence_completeness_are_binding(mutation: str) -> None:
    if mutation == "reorder":
        rows = (("rollout-2", ("left-tail",)), ("rollout-1", ("a", "b")))
    elif mutation == "truncate":
        rows = (("rollout-1", ("a",)), ("rollout-2", ("left-tail",)))
    else:
        rows = (("rollout-1", ("a", "b")), ("rollout-1", ("left-tail",)))
    left = _payload("left", ("a", "b"), rows=rows)
    with pytest.raises(ValueError, match=r"rollout ids|truncated"):
        _score([left, _payload("right", ("b", "a"))])


def test_self_rehashed_prediction_tampering_is_rejected_without_custodian_key() -> None:
    left = _payload("left", ("a", "b"))
    left["episode_predictions"][0][1][0] = "fabricated"
    _rehash(left)
    with pytest.raises(AttestationError, match="signature"):
        _score([left, _payload("right", ("b", "a"))])


def test_all_arms_must_share_one_signed_producer_source_bundle() -> None:
    with pytest.raises(ValueError, match="one frozen run and source bundle"):
        _score(
            [
                _payload("left", ("a", "b")),
                _payload("right", ("b", "a"), source_hash="d" * 64),
            ]
        )


def test_all_arms_must_share_one_signed_producer_run() -> None:
    with pytest.raises(ValueError, match="one frozen run and source bundle"):
        _score(
            [
                _payload("left", ("a", "b")),
                _payload("right", ("b", "a"), producer_run_id="different-run"),
            ]
        )
