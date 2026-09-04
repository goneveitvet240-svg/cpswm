from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from cpswm.system.attestation import AttestationError, Ed25519AttestationSigner
from cpswm.system.evaluation_operations import (
    structure_two_external_verification_freeze_v1_0 as freeze_module,
)
from cpswm.system.evaluation_operations.structure_two_external_governance_v0_6 import (
    make_trust_anchor_registry_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_external_verification_freeze_v1_0 import (
    ExternalVerificationFreezeLiveInputsV10,
    ExternalVerificationFreezeV10,
    VerifierMaterialPathsV10,
    attach_external_verification_freeze_role_attestations_v1_0,
    attach_runner_subkey_attestations_v1_0,
    external_verification_freeze_authority_signing_request_v1_0,
    external_verification_freeze_signing_requests_v1_0,
    finalize_external_verification_freeze_v1_0,
    prepare_external_verification_freeze_v1_0,
    runner_subkey_signing_requests_v1_0,
    runner_verifiers_from_external_verification_freeze_v1_0,
    sign_detached_request_v1_0,
    verify_external_verification_freeze_v1_0,
)
from cpswm.system.reproducibility import content_sha256

ENROLLED_AT = datetime(2026, 9, 4, tzinfo=UTC)
FROZEN_AT = ENROLLED_AT + timedelta(hours=1)
VERIFIED_AT = FROZEN_AT + timedelta(minutes=1)
PREVIOUS_HEAD = "a" * 64
AUTHORITY_NONCE = "b" * 64


class Ceremony:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.repository = root / "repository"
        self.engines = root / "external-engines"
        self.repository.mkdir(parents=True)
        self.engines.mkdir(parents=True)
        self._write_repository()
        self.authority = Ed25519AttestationSigner.generate(key_id="authority")
        self.reviewer = Ed25519AttestationSigner.generate(key_id="reviewer")
        self.executor = Ed25519AttestationSigner.generate(key_id="executor")
        self.custodian = Ed25519AttestationSigner.generate(key_id="custodian")
        self.canonical_runner = Ed25519AttestationSigner.generate(key_id="canonical-runner")
        self.fidelity_runner = Ed25519AttestationSigner.generate(key_id="fidelity-runner")
        self.registry = make_trust_anchor_registry_v0_6(
            role_signers={
                "reviewer": self.reviewer,
                "executor": self.executor,
                "custodian": self.custodian,
            },
            controller_identifiers={
                "reviewer": "external-review-board",
                "executor": "external-execution-lab",
                "custodian": "external-seed-custodian",
            },
            enrolled_at_utc=ENROLLED_AT,
            enrollment_authority=self.authority,
        )
        self.live = ExternalVerificationFreezeLiveInputsV10(
            repository_root=self.repository,
            canonical_verifier=VerifierMaterialPathsV10(
                bundle_root=Path("verifiers/canonical"),
                entrypoint_path=Path("verifiers/canonical/entrypoint.py"),
                engine_path=self.engines / "canonical-engine",
                config_path=Path("verifiers/canonical/config.json"),
            ),
            fidelity_verifier=VerifierMaterialPathsV10(
                bundle_root=Path("verifiers/fidelity"),
                entrypoint_path=Path("verifiers/fidelity/entrypoint.py"),
                engine_path=self.engines / "fidelity-engine",
                config_path=Path("verifiers/fidelity/config.json"),
            ),
            world_manifest_path=Path("raw/world.json"),
            gate_a_spec_path=Path("raw/gate-a.json"),
            training_split_path=Path("raw/training.json"),
        )

    def _write_repository(self) -> None:
        paths = (
            "src/cpswm",
            "apps/evaluation_runner",
            "verifiers/canonical",
            "verifiers/fidelity",
            "raw",
        )
        for relative in paths:
            (self.repository / relative).mkdir(parents=True)
        (self.repository / "src/cpswm/producer.py").write_text("VALUE = 1\n", encoding="utf-8")
        for name in (
            "run_structure_two_world_arm_traces_v0_4.py",
            "attest_structure_two_arm_trace_v0_4.py",
        ):
            (self.repository / "apps/evaluation_runner" / name).write_text(
                f"# {name}\n", encoding="utf-8"
            )
        for scope in ("canonical", "fidelity"):
            bundle = self.repository / "verifiers" / scope
            (bundle / "entrypoint.py").write_text(f"print({scope!r})\n", encoding="utf-8")
            (bundle / "config.json").write_text(
                json.dumps({"scope": scope, "strict": True}), encoding="utf-8"
            )
            engine = self.engines / f"{scope}-engine"
            engine.write_bytes(f"#!/bin/sh\n# immutable-{scope}-engine\n".encode())
            engine.chmod(0o700)
        world = {
            "split_policy": {
                "train_world_seeds_spent_for_tuning": [1, 2],
                "prior_validation_world_seeds_spent": [3],
                "v0_5_validation_world_seeds_preregistered_not_generated": [4],
                "validation_trajectory_seeds": [11],
                "validation_observation_seeds": [21],
            }
        }
        gate = {
            "public_preregistered_validation": {
                "excluded_world_seeds": [5],
                "validation_world_seeds": [6],
                "trajectory_seeds": [12],
                "observation_seeds": [22],
            }
        }
        training = {
            "train_sampling": {
                "world_seeds": [7],
                "trajectory_seeds": [13],
                "observation_seeds": [23],
            }
        }
        for name, payload in (("world", world), ("gate-a", gate), ("training", training)):
            (self.repository / "raw" / f"{name}.json").write_text(
                json.dumps(payload, sort_keys=True), encoding="utf-8"
            )

    def prepare(self, **updates: Any) -> ExternalVerificationFreezeV10:
        arguments: dict[str, Any] = {
            "live_inputs": self.live,
            "trust_anchor_registry": self.registry,
            "trusted_enrollment_authority": self.authority.verifier(),
            "canonical_runner": self.canonical_runner.verifier(),
            "fidelity_runner": self.fidelity_runner.verifier(),
            "frozen_at_utc": FROZEN_AT,
            "freeze_ledger_identifier": "authority-worm-ledger:test",
            "freeze_ledger_sequence": 9,
            "previous_ledger_head_sha256": PREVIOUS_HEAD,
            "authority_nonce_sha256": AUTHORITY_NONCE,
            "sealed_gate_b_commitment_record_exists": False,
        }
        arguments.update(updates)
        return prepare_external_verification_freeze_v1_0(**arguments)

    def finalize(self) -> tuple[dict[str, Any], ExternalVerificationFreezeV10]:
        unsigned = self.prepare()
        runner_requests = runner_subkey_signing_requests_v1_0(unsigned)
        runner_signers = {
            "canonical_episode_executor:runner": self.canonical_runner,
            "canonical_episode_executor:executor": self.executor,
            "six_method_fidelity_executor:runner": self.fidelity_runner,
            "six_method_fidelity_executor:executor": self.executor,
        }
        runner_attestations = {
            key: sign_detached_request_v1_0(request, signer=runner_signers[key])
            for key, request in runner_requests.items()
        }
        runner_signed = attach_runner_subkey_attestations_v1_0(
            record=unsigned,
            attestations=runner_attestations,
            canonical_runner=self.canonical_runner.verifier(),
            fidelity_runner=self.fidelity_runner.verifier(),
            executor=self.executor.verifier(),
        )
        role_requests = external_verification_freeze_signing_requests_v1_0(runner_signed)
        role_signers = {
            "reviewer": self.reviewer,
            "executor": self.executor,
            "custodian": self.custodian,
        }
        role_attestations = {
            role: sign_detached_request_v1_0(request, signer=role_signers[role])
            for role, request in role_requests.items()
        }
        role_signed = attach_external_verification_freeze_role_attestations_v1_0(
            record=runner_signed,
            attestations=role_attestations,
            reviewer=self.reviewer.verifier(),
            executor=self.executor.verifier(),
            custodian=self.custodian.verifier(),
        )
        authority_request = external_verification_freeze_authority_signing_request_v1_0(
            role_signed,
            reviewer=self.reviewer.verifier(),
            executor=self.executor.verifier(),
            custodian=self.custodian.verifier(),
            enrollment_authority=self.authority.verifier(),
        )
        payload = finalize_external_verification_freeze_v1_0(
            record=role_signed,
            authority_attestation=sign_detached_request_v1_0(
                authority_request, signer=self.authority
            ),
            reviewer=self.reviewer.verifier(),
            executor=self.executor.verifier(),
            custodian=self.custodian.verifier(),
            enrollment_authority=self.authority.verifier(),
        )
        verified = self.verify(payload)
        return payload, verified

    def verify(self, payload: dict[str, Any], **updates: Any) -> ExternalVerificationFreezeV10:
        arguments: dict[str, Any] = {
            "live_inputs": self.live,
            "trust_anchor_registry": self.registry,
            "trusted_enrollment_authority": self.authority.verifier(),
            "expected_previous_ledger_head_sha256": PREVIOUS_HEAD,
            "expected_freeze_ledger_sequence": 9,
            "verification_time_utc": VERIFIED_AT,
        }
        arguments.update(updates)
        return verify_external_verification_freeze_v1_0(payload, **arguments)


@pytest.fixture
def ceremony(tmp_path: Path) -> Ceremony:
    return Ceremony(tmp_path)


def test_positive_freeze_binds_live_bytes_raw_seed_union_and_six_distinct_keys(
    ceremony: Ceremony,
) -> None:
    payload, record = ceremony.finalize()

    assert payload["content_sha256"] == content_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    assert record.body.producer_source.files
    assert record.body.canonical_verifier.engine_absolute_path == str(
        ceremony.engines / "canonical-engine"
    )
    assert (
        record.body.canonical_verifier.engine_bytes_sha256
        == hashlib.sha256((ceremony.engines / "canonical-engine").read_bytes()).hexdigest()
    )
    forbidden = record.body.forbidden_seed_namespaces
    assert forbidden.world_seeds == (1, 2, 3, 4, 5, 6, 7)
    assert forbidden.trajectory_seeds == (11, 12, 13)
    assert forbidden.observation_seeds == (21, 22, 23)
    keys = (
        record.body.party_keys.reviewer,
        record.body.party_keys.executor,
        record.body.party_keys.custodian,
        record.body.party_keys.enrollment_authority,
        *(row.runner for row in record.body.runner_subkeys),
    )
    assert len({row.public_key_sha256 for row in keys}) == 6
    runners = runner_verifiers_from_external_verification_freeze_v1_0(record)
    assert runners["canonical_episode_executor"].public_key_sha256 == (
        ceremony.canonical_runner.verifier().public_key_sha256
    )


def test_forged_but_complete_ceremony_cannot_replace_external_authority(
    ceremony: Ceremony, tmp_path: Path
) -> None:
    attacker = Ceremony(tmp_path / "attacker")
    forged_payload, _ = attacker.finalize()

    with pytest.raises(AttestationError):
        ceremony.verify(forged_payload)


def test_raw_seed_namespace_omission_is_rejected(ceremony: Ceremony) -> None:
    world_path = ceremony.repository / "raw/world.json"
    world = json.loads(world_path.read_text(encoding="utf-8"))
    del world["split_policy"]["prior_validation_world_seeds_spent"]
    world_path.write_text(json.dumps(world), encoding="utf-8")

    with pytest.raises(KeyError, match="prior_validation_world_seeds_spent"):
        ceremony.prepare()


@pytest.mark.parametrize(
    "relative_path",
    [
        "src/cpswm/producer.py",
        "verifiers/canonical/entrypoint.py",
        "verifiers/fidelity/config.json",
    ],
)
def test_source_or_verifier_mutation_after_freeze_is_rejected(
    ceremony: Ceremony, relative_path: str
) -> None:
    payload, _ = ceremony.finalize()
    target = ceremony.repository / relative_path
    target.write_bytes(target.read_bytes() + b"\n# mutated\n")

    with pytest.raises(ValueError, match="live source, verifier"):
        ceremony.verify(payload)


def test_outside_engine_mutation_and_substitution_are_rejected(ceremony: Ceremony) -> None:
    payload, _ = ceremony.finalize()
    engine = ceremony.engines / "canonical-engine"
    engine.write_bytes(engine.read_bytes() + b"# changed\n")
    engine.chmod(0o700)
    with pytest.raises(ValueError, match="live source, verifier"):
        ceremony.verify(payload)

    engine.write_bytes(b"#!/bin/sh\n# immutable-canonical-engine\n")
    engine.chmod(0o700)
    substitute = ceremony.engines / "substitute-engine"
    substitute.write_bytes(engine.read_bytes())
    substitute.chmod(0o700)
    substituted_live = ExternalVerificationFreezeLiveInputsV10(
        repository_root=ceremony.live.repository_root,
        canonical_verifier=VerifierMaterialPathsV10(
            bundle_root=ceremony.live.canonical_verifier.bundle_root,
            entrypoint_path=ceremony.live.canonical_verifier.entrypoint_path,
            engine_path=substitute,
            config_path=ceremony.live.canonical_verifier.config_path,
        ),
        fidelity_verifier=ceremony.live.fidelity_verifier,
        world_manifest_path=ceremony.live.world_manifest_path,
        gate_a_spec_path=ceremony.live.gate_a_spec_path,
        training_split_path=ceremony.live.training_split_path,
    )
    with pytest.raises(ValueError, match="live source, verifier"):
        ceremony.verify(payload, live_inputs=substituted_live)


def test_symlink_engine_is_rejected(ceremony: Ceremony) -> None:
    symlink = ceremony.engines / "linked-engine"
    symlink.symlink_to(ceremony.engines / "canonical-engine")
    linked_live = ExternalVerificationFreezeLiveInputsV10(
        repository_root=ceremony.live.repository_root,
        canonical_verifier=VerifierMaterialPathsV10(
            bundle_root=ceremony.live.canonical_verifier.bundle_root,
            entrypoint_path=ceremony.live.canonical_verifier.entrypoint_path,
            engine_path=symlink,
            config_path=ceremony.live.canonical_verifier.config_path,
        ),
        fidelity_verifier=ceremony.live.fidelity_verifier,
        world_manifest_path=ceremony.live.world_manifest_path,
        gate_a_spec_path=ceremony.live.gate_a_spec_path,
        training_split_path=ceremony.live.training_split_path,
    )
    with pytest.raises(ValueError, match="symlink"):
        ceremony.prepare(live_inputs=linked_live)


def test_unregistered_runner_cannot_complete_possession_stage(ceremony: Ceremony) -> None:
    unsigned = ceremony.prepare()
    requests = runner_subkey_signing_requests_v1_0(unsigned)
    attacker = Ed25519AttestationSigner.generate(key_id="attacker-runner")
    attestations = {
        key: sign_detached_request_v1_0(
            request,
            signer=(
                ceremony.executor
                if key.endswith(":executor")
                else ceremony.canonical_runner
                if key.startswith("canonical")
                else ceremony.fidelity_runner
            ),
        )
        for key, request in requests.items()
    }

    with pytest.raises(AttestationError, match="unregistered runner"):
        attach_runner_subkey_attestations_v1_0(
            record=unsigned,
            attestations=attestations,
            canonical_runner=attacker.verifier(),
            fidelity_runner=ceremony.fidelity_runner.verifier(),
            executor=ceremony.executor.verifier(),
        )


def test_authority_cannot_presign_before_three_role_freeze(ceremony: Ceremony) -> None:
    unsigned = ceremony.prepare()

    with pytest.raises(AttestationError, match="carries no attestation"):
        external_verification_freeze_authority_signing_request_v1_0(
            unsigned,
            reviewer=ceremony.reviewer.verifier(),
            executor=ceremony.executor.verifier(),
            custodian=ceremony.custodian.verifier(),
            enrollment_authority=ceremony.authority.verifier(),
        )


@pytest.mark.parametrize("reuse", ["executor", "reviewer", "authority", "other_runner"])
def test_role_authority_or_runner_key_reuse_is_rejected(ceremony: Ceremony, reuse: str) -> None:
    signers = {
        "executor": ceremony.executor,
        "reviewer": ceremony.reviewer,
        "authority": ceremony.authority,
        "other_runner": ceremony.fidelity_runner,
    }

    with pytest.raises(ValueError, match="all be distinct"):
        ceremony.prepare(canonical_runner=signers[reuse].verifier())


def test_complete_snapshot_toctou_is_rejected(
    ceremony: Ceremony, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = freeze_module._capture_live_inputs
    calls = 0

    def capture_then_mutate(live: ExternalVerificationFreezeLiveInputsV10) -> Any:
        nonlocal calls
        captured = original(live)
        calls += 1
        if calls == 1:
            target = ceremony.repository / "src/cpswm/producer.py"
            target.write_text("VALUE = 2\n", encoding="utf-8")
        return captured

    monkeypatch.setattr(freeze_module, "_capture_live_inputs", capture_then_mutate)
    with pytest.raises(RuntimeError, match="TOCTOU"):
        ceremony.prepare()


def test_ledger_context_future_time_and_commitment_order_are_fail_closed(
    ceremony: Ceremony,
) -> None:
    payload, _ = ceremony.finalize()
    with pytest.raises(ValueError, match="ledger head or sequence"):
        ceremony.verify(payload, expected_previous_ledger_head_sha256="c" * 64)
    with pytest.raises(ValueError, match="future"):
        ceremony.verify(payload, verification_time_utc=FROZEN_AT - timedelta(seconds=1))
    with pytest.raises(ValueError, match="did not follow"):
        ceremony.verify(payload, sealed_gate_b_commitment_record_created_at_utc=FROZEN_AT)
    with pytest.raises(ValueError, match="must precede"):
        ceremony.prepare(sealed_gate_b_commitment_record_exists=True)


def test_content_and_namespace_tampering_remain_invalid_when_structurally_complete(
    ceremony: Ceremony,
) -> None:
    payload, _ = ceremony.finalize()
    forged = deepcopy(payload)
    forged["body"]["forbidden_seed_namespaces"]["world_seeds"].append(99)
    unsigned = {key: value for key, value in forged.items() if key != "content_sha256"}
    forged["content_sha256"] = content_sha256(unsigned)

    with pytest.raises(ValueError, match="forbidden-seed namespace content hash"):
        ceremony.verify(forged)
