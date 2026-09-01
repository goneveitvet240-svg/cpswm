from __future__ import annotations

from cpswm.system.attestation import (
    AttestationAuthority,
    AttestationError,
    Ed25519AttestationSigner,
)


def test_formal_verifier_has_no_signing_capability() -> None:
    signer = Ed25519AttestationSigner.generate(key_id="formal-root")
    verifier = signer.verifier()

    assert verifier.formal_grade
    assert not hasattr(verifier, "sign")
    verifier.verify("test.domain", {"value": 1}, signer.sign("test.domain", {"value": 1}))


def test_formal_verifier_rejects_hmac_and_public_key_substitution() -> None:
    signer = Ed25519AttestationSigner.generate(key_id="formal-root")
    verifier = signer.verifier()
    hmac_authority = AttestationAuthority(key_id="formal-root", secret=b"h" * 32)

    try:
        verifier.verify(
            "test.domain",
            {"value": 1},
            hmac_authority.sign("test.domain", {"value": 1}),
        )
    except AttestationError as exc:
        assert "Ed25519" in str(exc)
    else:
        raise AssertionError("formal verifier accepted a symmetric HMAC")

    attacker = Ed25519AttestationSigner.generate(key_id="formal-root")
    try:
        verifier.verify(
            "test.domain",
            {"value": 1},
            attacker.sign("test.domain", {"value": 1}),
        )
    except AttestationError as exc:
        assert "signature" in str(exc)
    else:
        raise AssertionError("formal verifier accepted an attacker public key")
