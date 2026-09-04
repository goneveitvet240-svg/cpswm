from __future__ import annotations

from copy import deepcopy

import pytest

from cpswm.system.attestation import (
    AttestationError,
    Ed25519AttestationSigner,
    attested_payload,
)
from cpswm.system.evaluation_operations.structure_two_signed_gate_b_v0_6 import (
    TRACE_ATTESTATION_DOMAIN,
    BoundStratifiedArmTraceV06,
    MechanismExecutionLogEntry,
    MechanismTransitionReceipt,
    make_bound_stratified_trace_v0_6,
    run_signed_stratified_gate_b_v0_6,
)
from cpswm.system.evaluation_operations.structure_two_stratified_gate_b_v0_6 import (
    ComparisonPair,
    MechanismRequirement,
)
from cpswm.system.reproducibility import content_sha256

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
SIGNER = Ed25519AttestationSigner.generate(key_id="v0.6-custodian")


def _payload(
    arm: str,
    actions: tuple[str, ...],
    event: str,
    *,
    signer: Ed25519AttestationSigner = SIGNER,
    run_id: str = "run-1",
) -> dict[str, object]:
    bundle = HASH_A if arm == "left" else HASH_B
    receipts: list[tuple[MechanismTransitionReceipt, ...]] = []
    logs: list[tuple[MechanismExecutionLogEntry, ...]] = []
    chain_state = content_sha256({"arm": arm, "state": "start"})
    for index, _ in enumerate(actions):
        output_state = content_sha256({"previous": chain_state, "arm": arm, "index": index})
        core_transition_payload = {"arm": arm, "core": index}
        core_transition = content_sha256(core_transition_payload)
        log = MechanismExecutionLogEntry(
            sequence_index=index,
            invocation_id=f"{arm}:{index}",
            event=event,
            component_id=f"{arm}-component",
            input_state_sha256=chain_state,
            output_state_sha256=output_state,
            implementation_bundle_sha256=bundle,
            core_transition_sha256=core_transition,
            core_transition_payload=core_transition_payload,
        )
        logs.append((log,))
        receipts.append(
            (
                MechanismTransitionReceipt(
                    invocation_id=f"{arm}:{index}",
                    event=event,
                    component_id=f"{arm}-component",
                    input_state_sha256=chain_state,
                    output_state_sha256=output_state,
                    implementation_bundle_sha256=bundle,
                    core_transition_sha256=core_transition,
                    execution_log_entry_sha256=log.content_sha256,
                ),
            )
        )
        chain_state = output_state
    return make_bound_stratified_trace_v0_6(
        arm=arm,
        gate_a_content_sha256=HASH_A,
        manifest_sha256=HASH_B,
        producer_run_id=run_id,
        producer_source_bundle_sha256=HASH_C,
        arm_implementation_bundle_sha256=bundle,
        episode_actions=(("episode", actions),),
        episode_mechanism_receipts=(("episode", tuple(receipts)),),
        episode_execution_log_entries=(("episode", tuple(logs)),),
        signer=signer,
    )


def _run(payloads: tuple[dict[str, object], ...]) -> dict[str, object]:
    verifier = SIGNER.verifier()
    return run_signed_stratified_gate_b_v0_6(
        payloads,
        expected_arms=("left", "right"),
        comparison_pairs=(ComparisonPair("pair", "domain", "left", "right", 0.25),),
        mechanism_requirements=(
            MechanismRequirement("left", ("left-core",), 0.25, 1.0),
            MechanismRequirement("right", ("right-core",), 0.25, 1.0),
        ),
        gate_a_content_sha256=HASH_A,
        manifest_sha256=HASH_B,
        producer_source_bundle_sha256=HASH_C,
        expected_arm_implementation_bundles={"left": HASH_A, "right": HASH_B},
        expected_event_component_ids={
            "left": {"left-core": "left-component"},
            "right": {"right-core": "right-component"},
        },
        expected_producer_run_id="run-1",
        trusted_custodian_key_id=verifier.key_id,
        trusted_custodian_public_key_sha256=verifier.public_key_sha256,
        enforce_canonical_protocol=False,
    )


def test_formal_signed_gate_rejects_a_caller_defined_arm_protocol() -> None:
    verifier = SIGNER.verifier()
    with pytest.raises(ValueError, match=r"canonical v0\.6 protocol"):
        run_signed_stratified_gate_b_v0_6(
            (_payload("left", ("a",), "left-core"),),
            expected_arms=("left",),
            comparison_pairs=(),
            mechanism_requirements=(MechanismRequirement("left", ("left-core",), 0.25, 1.0),),
            gate_a_content_sha256=HASH_A,
            manifest_sha256=HASH_B,
            producer_source_bundle_sha256=HASH_C,
            expected_arm_implementation_bundles={"left": HASH_A},
            expected_event_component_ids={"left": {"left-core": "left-component"}},
            expected_producer_run_id="run-1",
            trusted_custodian_key_id=verifier.key_id,
            trusted_custodian_public_key_sha256=verifier.public_key_sha256,
        )


def _resign(payload: dict[str, object]) -> dict[str, object]:
    unsigned = dict(payload)
    unsigned.pop("content_sha256")
    unsigned["attestation"] = None
    record = BoundStratifiedArmTraceV06.model_validate(unsigned)
    signed = record.model_copy(
        update={
            "attestation": SIGNER.sign(
                TRACE_ATTESTATION_DOMAIN,
                attested_payload(record),
            )
        }
    )
    result = signed.model_dump(mode="json")
    result["content_sha256"] = content_sha256(result)
    return result


def _two_episode_payload(arm: str, event: str) -> dict[str, object]:
    payload = _payload(arm, (f"{arm}-action-1",), event)
    bundle = HASH_A if arm == "left" else HASH_B
    initial_state = content_sha256({"arm": arm, "episode": "episode-2", "state": "start"})
    output_state = content_sha256({"arm": arm, "episode": "episode-2", "previous": initial_state})
    transition_payload = {"arm": arm, "episode": "episode-2", "core": 0}
    transition_sha256 = content_sha256(transition_payload)
    log = MechanismExecutionLogEntry(
        sequence_index=0,
        invocation_id=f"{arm}:episode-2:0",
        event=event,
        component_id=f"{arm}-component",
        input_state_sha256=initial_state,
        output_state_sha256=output_state,
        implementation_bundle_sha256=bundle,
        core_transition_sha256=transition_sha256,
        core_transition_payload=transition_payload,
    )
    receipt = MechanismTransitionReceipt(
        invocation_id=log.invocation_id,
        event=event,
        component_id=log.component_id,
        input_state_sha256=initial_state,
        output_state_sha256=output_state,
        implementation_bundle_sha256=bundle,
        core_transition_sha256=transition_sha256,
        execution_log_entry_sha256=log.content_sha256,
    )
    payload["episode_actions"].append(["episode-2", [f"{arm}-action-2"]])
    payload["episode_mechanism_receipts"].append(["episode-2", [[receipt.model_dump(mode="json")]]])
    payload["episode_execution_log_entries"].append(["episode-2", [[log.model_dump(mode="json")]]])
    return _resign(payload)


def test_complete_signed_pair_can_pass_but_not_authorize_external_efficacy() -> None:
    report = _run(
        (
            _payload("left", ("a", "a", "a", "a"), "left-core"),
            _payload("right", ("b", "a", "a", "a"), "right-core"),
        )
    )
    assert report["protocol"].endswith("-diagnostic@0.6")
    assert report["canonical_protocol_enforced"] is False
    assert report["diagnostic_gate_b_passed"] is True
    assert report["gate_b"]["gate_b_passed"] is False
    assert report["diagnostic_gate_b"]["gate_b_passed"] is True
    assert report["gate_b_passed"] is False
    assert report["external_method_efficacy_comparison_allowed"] is False


def test_independent_episode_state_and_sequence_restart_is_accepted() -> None:
    report = _run(
        (
            _two_episode_payload("left", "left-core"),
            _two_episode_payload("right", "right-core"),
        )
    )
    assert report["diagnostic_gate_b_passed"] is True


def test_rewriting_mechanism_events_and_content_hash_breaks_signature() -> None:
    forged = deepcopy(_payload("left", ("a", "a"), "not-the-core"))
    forged["episode_mechanism_receipts"][0][1][0][0]["event"] = "left-core"
    forged["episode_mechanism_receipts"][0][1][1][0]["event"] = "left-core"
    unhashed = dict(forged)
    unhashed.pop("content_sha256")
    forged["content_sha256"] = content_sha256(unhashed)
    with pytest.raises(AttestationError, match="signature does not match"):
        _run((forged, _payload("right", ("b", "a"), "right-core")))


def test_candidate_key_cannot_impersonate_external_custodian() -> None:
    attacker = Ed25519AttestationSigner.generate(key_id=SIGNER.key_id)
    with pytest.raises(AttestationError, match="trust anchor"):
        _run(
            (
                _payload("left", ("a", "a"), "left-core", signer=attacker),
                _payload("right", ("b", "a"), "right-core"),
            )
        )


def test_mixed_producer_runs_fail_closed() -> None:
    with pytest.raises(ValueError, match="preregistered producer run"):
        _run(
            (
                _payload("left", ("a", "a"), "left-core", run_id="run-left"),
                _payload("right", ("b", "a"), "right-core", run_id="run-right"),
            )
        )


def test_replayed_mechanism_invocation_fails_closed_even_when_signed() -> None:
    left = _payload("left", ("a", "a"), "left-core")
    first = left["episode_mechanism_receipts"][0][1][0][0]
    left["episode_mechanism_receipts"][0][1][1][0] = deepcopy(first)
    left = _resign(left)
    with pytest.raises(ValueError, match="invocation replay"):
        _run((left, _payload("right", ("b", "a"), "right-core")))


def test_signed_arbitrary_component_id_fails_canonical_mapping() -> None:
    left = _payload("left", ("a",), "left-core")
    receipt = left["episode_mechanism_receipts"][0][1][0][0]
    log = left["episode_execution_log_entries"][0][1][0][0]
    receipt["component_id"] = "attacker-component"
    log["component_id"] = "attacker-component"
    log_model = MechanismExecutionLogEntry.model_validate(log)
    receipt["execution_log_entry_sha256"] = log_model.content_sha256
    left = _resign(left)
    with pytest.raises(ValueError, match="event/component mapping"):
        _run((left, _payload("right", ("b",), "right-core")))


def test_signed_discontinuous_state_chain_fails_closed() -> None:
    left = _payload("left", ("a", "a"), "left-core")
    receipt = left["episode_mechanism_receipts"][0][1][1][0]
    log = left["episode_execution_log_entries"][0][1][1][0]
    forged_input = "d" * 64
    receipt["input_state_sha256"] = forged_input
    log["input_state_sha256"] = forged_input
    log_model = MechanismExecutionLogEntry.model_validate(log)
    receipt["execution_log_entry_sha256"] = log_model.content_sha256
    left = _resign(left)
    with pytest.raises(ValueError, match="state chain is discontinuous"):
        _run((left, _payload("right", ("b", "a"), "right-core")))


def test_receipt_without_matching_execution_log_fails_closed() -> None:
    left = _payload("left", ("a",), "left-core")
    left["episode_mechanism_receipts"][0][1][0][0]["execution_log_entry_sha256"] = "d" * 64
    left = _resign(left)
    with pytest.raises(ValueError, match="not bound to execution log"):
        _run((left, _payload("right", ("b",), "right-core")))


def test_execution_log_cannot_name_a_fictional_core_transition_hash() -> None:
    left = _payload("left", ("a",), "left-core")
    receipt = left["episode_mechanism_receipts"][0][1][0][0]
    log = left["episode_execution_log_entries"][0][1][0][0]
    receipt["core_transition_sha256"] = "d" * 64
    log["core_transition_sha256"] = "d" * 64
    log_model = MechanismExecutionLogEntry.model_validate(log)
    receipt["execution_log_entry_sha256"] = log_model.content_sha256
    left = _resign(left)
    with pytest.raises(ValueError, match="core-transition hash mismatch"):
        _run((left, _payload("right", ("b",), "right-core")))
