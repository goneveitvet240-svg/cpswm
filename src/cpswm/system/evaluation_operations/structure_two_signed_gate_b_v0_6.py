"""Signed trace envelope and scorer for Structure-Two Gate B v0.6."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import Field

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.evaluation_operations.structure_two_frozen_run_v0_8 import (
    RecomputedFrozenHoldoutV08,
    verify_gate_b_execution_artifact_v0_8,
)
from cpswm.system.evaluation_operations.structure_two_stratified_gate_b_v0_6 import (
    ComparisonPair,
    MechanismRequirement,
    StratifiedArmTrace,
    run_stratified_gate_b,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-signed-stratified-gate-b@0.6"
DIAGNOSTIC_PROTOCOL_ID = "structure-two-signed-stratified-gate-b-diagnostic@0.6"
TRACE_PROTOCOL_ID = "structure-two-bound-mechanism-action-trace@0.6"
TRACE_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.bound_trace.v0.6"


class MechanismTransitionReceipt(ContractModel):
    invocation_id: str = Field(min_length=1)
    event: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    input_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    core_transition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_log_entry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class MechanismExecutionLogEntry(ContractModel):
    sequence_index: int = Field(ge=0)
    invocation_id: str = Field(min_length=1)
    event: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    input_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    core_transition_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    core_transition_payload: dict[str, Any]

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class BoundStratifiedArmTraceV06(ContractModel):
    protocol: str = Field(pattern=r"^structure-two-bound-mechanism-action-trace@0\.6$")
    arm: str = Field(min_length=1)
    gate_a_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    producer_source_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arm_implementation_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gate_b_execution_artifact_file_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    six_arm_reference_execution_content_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    episode_actions: tuple[tuple[str, tuple[str, ...]], ...]
    episode_mechanism_receipts: tuple[
        tuple[str, tuple[tuple[MechanismTransitionReceipt, ...], ...]], ...
    ]
    episode_execution_log_entries: tuple[
        tuple[str, tuple[tuple[MechanismExecutionLogEntry, ...], ...]], ...
    ]
    custodian_public_key_base64: str = Field(min_length=1)
    custodian_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    attestation: Attestation | None = None


def make_bound_stratified_trace_v0_6(
    *,
    arm: str,
    gate_a_content_sha256: str,
    manifest_sha256: str,
    producer_run_id: str,
    producer_source_bundle_sha256: str,
    arm_implementation_bundle_sha256: str,
    gate_b_execution_artifact_file_sha256: str | None = None,
    six_arm_reference_execution_content_sha256: str | None = None,
    episode_actions: Sequence[tuple[str, Sequence[str]]],
    episode_mechanism_receipts: Sequence[
        tuple[str, Sequence[Sequence[MechanismTransitionReceipt]]]
    ],
    episode_execution_log_entries: Sequence[
        tuple[str, Sequence[Sequence[MechanismExecutionLogEntry]]]
    ],
    signer: Ed25519AttestationSigner,
) -> dict[str, Any]:
    verifier = signer.verifier()
    unsigned = BoundStratifiedArmTraceV06(
        protocol=TRACE_PROTOCOL_ID,
        arm=arm,
        gate_a_content_sha256=gate_a_content_sha256,
        manifest_sha256=manifest_sha256,
        producer_run_id=producer_run_id,
        producer_source_bundle_sha256=producer_source_bundle_sha256,
        arm_implementation_bundle_sha256=arm_implementation_bundle_sha256,
        gate_b_execution_artifact_file_sha256=(gate_b_execution_artifact_file_sha256),
        six_arm_reference_execution_content_sha256=(six_arm_reference_execution_content_sha256),
        episode_actions=tuple((key, tuple(values)) for key, values in episode_actions),
        episode_mechanism_receipts=tuple(
            (key, tuple(tuple(receipts) for receipts in steps))
            for key, steps in episode_mechanism_receipts
        ),
        episode_execution_log_entries=tuple(
            (key, tuple(tuple(entries) for entries in steps))
            for key, steps in episode_execution_log_entries
        ),
        custodian_public_key_base64=verifier.public_key_base64,
        custodian_public_key_sha256=verifier.public_key_sha256,
    )
    signed = unsigned.model_copy(
        update={"attestation": signer.sign(TRACE_ATTESTATION_DOMAIN, attested_payload(unsigned))}
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def verify_bound_stratified_trace_v0_6(
    payload: Mapping[str, Any],
    *,
    trusted_custodian_key_id: str,
    trusted_custodian_public_key_sha256: str,
) -> BoundStratifiedArmTraceV06:
    unsigned_payload = dict(payload)
    stored = unsigned_payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned_payload) != stored:
        raise ValueError("v0.6 bound trace content hash mismatch")
    record = BoundStratifiedArmTraceV06.model_validate(unsigned_payload)
    if record.custodian_public_key_sha256 != trusted_custodian_public_key_sha256:
        raise AttestationError("v0.6 trace is outside the custodian trust anchor")
    verifier = Ed25519AttestationVerifier.from_public_key_base64(
        key_id=trusted_custodian_key_id,
        public_key_base64=record.custodian_public_key_base64,
    )
    if verifier.public_key_sha256 != trusted_custodian_public_key_sha256:
        raise AttestationError("v0.6 trace public key hash mismatch")
    verifier.verify(TRACE_ATTESTATION_DOMAIN, attested_payload(record), record.attestation)
    return record


def run_signed_stratified_gate_b_v0_6(
    payloads: Sequence[Mapping[str, Any]],
    *,
    expected_arms: Sequence[str],
    comparison_pairs: Sequence[ComparisonPair],
    mechanism_requirements: Sequence[MechanismRequirement],
    gate_a_content_sha256: str,
    manifest_sha256: str,
    producer_source_bundle_sha256: str,
    expected_arm_implementation_bundles: Mapping[str, str],
    expected_event_component_ids: Mapping[str, Mapping[str, str]],
    expected_producer_run_id: str,
    trusted_custodian_key_id: str,
    trusted_custodian_public_key_sha256: str,
    enforce_canonical_protocol: bool = True,
    canonical_execution_artifact_path: Path | None = None,
    recomputed_holdout: RecomputedFrozenHoldoutV08 | None = None,
    expected_six_arm_reference_execution_content_sha256: str | None = None,
    expected_holdout_opening_artifact_file_sha256: str | None = None,
    trusted_executor: Ed25519AttestationVerifier | None = None,
    expected_external_execution_log_entries_by_arm: Mapping[
        str, Sequence[MechanismExecutionLogEntry]
    ]
    | None = None,
) -> dict[str, Any]:
    expected = tuple(expected_arms)
    canonical_external_logs = expected_external_execution_log_entries_by_arm or {}
    if enforce_canonical_protocol:
        from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import (
            CANONICAL_COMPARISONS,
            CANONICAL_COMPONENT_IDS,
            CANONICAL_MECHANISM_EVENTS,
            EXPECTED_ARMS,
            MIN_ACTION_DISAGREEMENT_RATE,
        )

        canonical_pairs = {
            comparison_id: (
                "care_wm",
                right_arm,
                domain,
                MIN_ACTION_DISAGREEMENT_RATE,
            )
            for comparison_id, (right_arm, domain) in CANONICAL_COMPARISONS.items()
        }
        supplied_pairs = {
            item.comparison_id: (
                item.left_arm,
                item.right_arm,
                item.domain,
                item.min_action_disagreement_rate,
            )
            for item in comparison_pairs
        }
        supplied_events = {item.arm: item.required_events for item in mechanism_requirements}
        canonical_components = {
            arm: {event: CANONICAL_COMPONENT_IDS[arm] for event in events}
            for arm, events in CANONICAL_MECHANISM_EVENTS.items()
        }
        if (
            expected != EXPECTED_ARMS
            or supplied_pairs != canonical_pairs
            or supplied_events != dict(CANONICAL_MECHANISM_EVENTS)
            or dict(expected_event_component_ids) != canonical_components
        ):
            raise ValueError("formal signed Gate B requires the canonical v0.6 protocol")
        if (
            canonical_execution_artifact_path is None
            or recomputed_holdout is None
            or expected_six_arm_reference_execution_content_sha256 is None
            or expected_holdout_opening_artifact_file_sha256 is None
            or trusted_executor is None
            or expected_external_execution_log_entries_by_arm is None
        ):
            raise ValueError(
                "canonical Gate B requires deterministic action and six-arm execution evidence"
            )
        if (
            str(recomputed_holdout.opening.evaluation_set_role)
            != "custodian_sealed_confirmatory_gate_b"
        ):
            raise ValueError(
                "canonical Gate B rejects public preregistered validation data; "
                "a post-freeze custodian-sealed confirmatory holdout is required"
            )
        canonical_execution = verify_gate_b_execution_artifact_v0_8(
            canonical_execution_artifact_path,
            recomputed_holdout=recomputed_holdout,
            expected_gate_a_content_sha256=gate_a_content_sha256,
            expected_producer_source_bundle_sha256=producer_source_bundle_sha256,
            expected_arm_implementation_bundle_sha256=(expected_arm_implementation_bundles),
            expected_six_arm_reference_execution_content_sha256=(
                expected_six_arm_reference_execution_content_sha256
            ),
            expected_holdout_opening_artifact_file_sha256=(
                expected_holdout_opening_artifact_file_sha256
            ),
            trusted_executor=trusted_executor,
        )
        canonical_execution_file_sha256 = hashlib.sha256(
            canonical_execution_artifact_path.read_bytes()
        ).hexdigest()
    if set(expected_arm_implementation_bundles) != set(expected):
        raise ValueError("v0.6 arm implementation bundle set mismatch")
    requirement_by_arm = {item.arm: item for item in mechanism_requirements}
    if set(requirement_by_arm) != set(expected) or set(expected_event_component_ids) != set(
        expected
    ):
        raise ValueError("v0.6 mechanism/component specification arm set mismatch")
    for arm in expected:
        if set(expected_event_component_ids[arm]) != set(requirement_by_arm[arm].required_events):
            raise ValueError("v0.6 event/component specification is incomplete")
    records = [
        verify_bound_stratified_trace_v0_6(
            payload,
            trusted_custodian_key_id=trusted_custodian_key_id,
            trusted_custodian_public_key_sha256=trusted_custodian_public_key_sha256,
        )
        for payload in payloads
    ]
    by_arm = {record.arm: record for record in records}
    if len(by_arm) != len(records) or set(by_arm) != set(expected):
        raise ValueError("v0.6 signed trace set must exactly match expected arms")
    producer_runs = {record.producer_run_id for record in records}
    if producer_runs != {expected_producer_run_id}:
        raise ValueError("v0.6 signed traces do not match the preregistered producer run")
    for arm in expected:
        record = by_arm[arm]
        if record.gate_a_content_sha256 != gate_a_content_sha256:
            raise ValueError("v0.6 signed trace names the wrong Gate A")
        if record.manifest_sha256 != manifest_sha256:
            raise ValueError("v0.6 signed trace names the wrong manifest")
        if record.producer_source_bundle_sha256 != producer_source_bundle_sha256:
            raise ValueError("v0.6 signed trace names the wrong producer source bundle")
        if record.arm_implementation_bundle_sha256 != expected_arm_implementation_bundles[arm]:
            raise ValueError("v0.6 signed trace names the wrong arm implementation bundle")
        if enforce_canonical_protocol:
            if (
                record.gate_b_execution_artifact_file_sha256 != canonical_execution_file_sha256
                or record.six_arm_reference_execution_content_sha256
                != expected_six_arm_reference_execution_content_sha256
            ):
                raise ValueError("v0.6 signed trace is outside the verified execution chain")
            if record.episode_actions != canonical_execution.episode_actions_by_arm[arm]:
                raise ValueError("v0.6 signed trace actions were not produced by arm execution")
        if tuple(item[0] for item in record.episode_actions) != tuple(
            item[0] for item in record.episode_mechanism_receipts
        ) or tuple(item[0] for item in record.episode_actions) != tuple(
            item[0] for item in record.episode_execution_log_entries
        ):
            raise ValueError("v0.6 action, receipt, and execution-log episode order mismatch")
        invocation_ids: set[str] = set()
        for (_, actions), (_, receipt_steps), (_, execution_log_steps) in zip(
            record.episode_actions,
            record.episode_mechanism_receipts,
            record.episode_execution_log_entries,
            strict=True,
        ):
            # Every episode is an independent replay from its own frozen input.
            # Carrying either state or sequence counters across this boundary
            # rejects valid independent executions and, worse, obscures whether
            # an entry was moved from one episode to another.
            previous_output_sha256: str | None = None
            expected_sequence_index = 0
            if len(actions) != len(receipt_steps) or len(actions) != len(execution_log_steps):
                raise ValueError("v0.6 action, receipt, and execution-log step count mismatch")
            for receipts, log_entries in zip(
                receipt_steps,
                execution_log_steps,
                strict=True,
            ):
                if len(receipts) != len(log_entries):
                    raise ValueError("v0.6 receipt/execution-log entry count mismatch")
                for receipt, log_entry in zip(receipts, log_entries, strict=True):
                    if receipt.invocation_id in invocation_ids:
                        raise ValueError("v0.6 mechanism receipt invocation replay detected")
                    invocation_ids.add(receipt.invocation_id)
                    if log_entry.sequence_index != expected_sequence_index:
                        raise ValueError("v0.6 execution log sequence is not contiguous")
                    expected_sequence_index += 1
                    if receipt.execution_log_entry_sha256 != log_entry.content_sha256:
                        raise ValueError("v0.6 mechanism receipt is not bound to execution log")
                    receipt_projection = {
                        "invocation_id": receipt.invocation_id,
                        "event": receipt.event,
                        "component_id": receipt.component_id,
                        "input_state_sha256": receipt.input_state_sha256,
                        "output_state_sha256": receipt.output_state_sha256,
                        "implementation_bundle_sha256": (receipt.implementation_bundle_sha256),
                        "core_transition_sha256": receipt.core_transition_sha256,
                    }
                    log_projection = log_entry.model_dump(
                        exclude={"sequence_index", "core_transition_payload"}
                    )
                    if receipt_projection != log_projection:
                        raise ValueError("v0.6 receipt and execution-log semantics differ")
                    if content_sha256(log_entry.core_transition_payload) != (
                        receipt.core_transition_sha256
                    ):
                        raise ValueError("v0.6 execution log core-transition hash mismatch")
                    if (
                        receipt.implementation_bundle_sha256
                        != record.arm_implementation_bundle_sha256
                    ):
                        raise ValueError("v0.6 mechanism receipt implementation bundle mismatch")
                    expected_component = expected_event_component_ids[arm].get(receipt.event)
                    if receipt.component_id != expected_component:
                        raise ValueError("v0.6 mechanism event/component mapping mismatch")
                    if receipt.input_state_sha256 == receipt.output_state_sha256:
                        raise ValueError("v0.6 mechanism receipt has no observable transition")
                    if (
                        previous_output_sha256 is not None
                        and receipt.input_state_sha256 != previous_output_sha256
                    ):
                        raise ValueError("v0.6 mechanism state chain is discontinuous")
                    previous_output_sha256 = receipt.output_state_sha256
        if enforce_canonical_protocol and arm in canonical_external_logs:
            flattened = tuple(
                entry
                for _, steps in record.episode_execution_log_entries
                for entries in steps
                for entry in entries
            )
            if flattened != tuple(canonical_external_logs[arm]):
                raise ValueError("v0.6 external mechanism trace differs from six-arm recomputation")
    traces = tuple(
        StratifiedArmTrace(
            arm=arm,
            episode_actions=by_arm[arm].episode_actions,
            episode_mechanism_events=tuple(
                (
                    episode_id,
                    tuple(
                        tuple(receipt.event for receipt in receipts) for receipts in receipt_steps
                    ),
                )
                for episode_id, receipt_steps in by_arm[arm].episode_mechanism_receipts
            ),
        )
        for arm in expected
    )
    gate = run_stratified_gate_b(
        traces,
        expected_arms=expected,
        comparison_pairs=comparison_pairs,
        mechanism_requirements=mechanism_requirements,
    )
    diagnostic_gate_b_passed = gate["gate_b_passed"]
    formal_gate = gate if enforce_canonical_protocol else {**gate, "gate_b_passed": False}
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID if enforce_canonical_protocol else DIAGNOSTIC_PROTOCOL_ID,
        "canonical_protocol_enforced": enforce_canonical_protocol,
        "gate_b": formal_gate,
        "diagnostic_gate_b": gate if not enforce_canonical_protocol else None,
        "diagnostic_gate_b_passed": diagnostic_gate_b_passed,
        "gate_b_passed": (diagnostic_gate_b_passed if enforce_canonical_protocol else False),
        "producer_run_id": next(iter(producer_runs)),
        "gate_a_content_sha256": gate_a_content_sha256,
        "manifest_sha256": manifest_sha256,
        "producer_source_bundle_sha256": producer_source_bundle_sha256,
        "arm_implementation_bundle_sha256": dict(expected_arm_implementation_bundles),
        "external_method_efficacy_comparison_allowed": False,
        "claim_boundary": (
            "A signed Gate B pass does not authorize external-method efficacy claims; "
            "the separately signed native and adaptation fidelity gate must also pass."
            if enforce_canonical_protocol
            else "This is a noncanonical diagnostic score. The formal Gate B pass is forced "
            "false even when the diagnostic thresholds pass."
        ),
    }
    report["content_sha256"] = content_sha256(report)
    return report


__all__ = [
    "PROTOCOL_ID",
    "TRACE_ATTESTATION_DOMAIN",
    "TRACE_PROTOCOL_ID",
    "BoundStratifiedArmTraceV06",
    "MechanismExecutionLogEntry",
    "MechanismTransitionReceipt",
    "make_bound_stratified_trace_v0_6",
    "run_signed_stratified_gate_b_v0_6",
    "verify_bound_stratified_trace_v0_6",
]
