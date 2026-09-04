from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid5

import pytest
from pydantic import ValidationError

from cpswm.system.attestation import Ed25519AttestationSigner, attested_payload
from cpswm.system.evaluation_operations.structure_two_trusted_ablation_authorization import (
    DEPENDENCY_ORDER,
    EXPECTED_PARENTS,
    EXPECTED_PROTOCOL_IDS,
    FORMAL_RECEIPT_DOMAIN_PREFIX,
    ActionProbability,
    AuditRound1Receipt,
    AuditRound2Receipt,
    AuthorizationDecisionStatus,
    CustodyAttestationStatus,
    CustodyHop,
    CustodyRole,
    CustodyTrustAnchorEntry,
    DependencyCommitmentStatus,
    DependencyState,
    FormalDependencyReceipt,
    FormalReceiptBase,
    GateBV08Receipt,
    P5BottleneckDiagnosis,
    P5PipelineStage,
    P5StageDecomposition,
    ParentReceiptRef,
    ProposalP5Receipt,
    ReceiptKind,
    ReceiptReplayRegistry,
    ReceiptTrustAnchorManifest,
    Task7Receipt,
    Task8Receipt,
    Task9Receipt,
    Task10Receipt,
    Task11Receipt,
    Task12GateThresholds,
    Task12ProposalEvent,
    Task12ProposalProbability,
    Task12ProposalRow,
    Task12RawProposalTrace,
    Task12Receipt,
    Task12State,
    Task13Receipt,
    TrustAnchorEntry,
    TrustAnchorStatus,
    TrustedAblationAuthorizationPolicy,
    diagnose_p5_bottleneck,
    evaluate_trusted_seven_operator_ablation_authorization,
    formal_receipt_content_sha256,
    issue_custody_hop,
    issue_formal_receipt,
    issue_trust_anchor_manifest,
    recompute_task12_gate_result,
    trust_anchor_manifest_content_sha256,
    verify_formal_receipt,
    verify_trust_anchor_manifest,
    verify_trusted_seven_operator_ablation_authorization,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = (
    ROOT / "configs/project_two_experiments/"
    "structure_two_trusted_seven_operator_ablation_authorization_v1_0.json"
)
BASE_TIME = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
NAMESPACE = UUID("44a27df3-943c-41ee-bbcd-b3d58ad2af93")


def _hash(label: str) -> str:
    return content_sha256({"label": label})


def _uuid(label: str) -> UUID:
    return uuid5(NAMESPACE, label)


def _current_policy() -> TrustedAblationAuthorizationPolicy:
    return TrustedAblationAuthorizationPolicy.load(POLICY_PATH)


def _trust_context() -> tuple[
    TrustedAblationAuthorizationPolicy,
    ReceiptTrustAnchorManifest,
    Ed25519AttestationSigner,
    dict[ReceiptKind, Ed25519AttestationSigner],
    dict[tuple[ReceiptKind, CustodyRole], Ed25519AttestationSigner],
]:
    signers = {
        kind: Ed25519AttestationSigner.generate(key_id=f"key-{kind.value.lower()}")
        for kind in ReceiptKind
    }
    registry_authority = Ed25519AttestationSigner.generate(key_id="registry-root")
    custody_signers = {
        (kind, role): (
            signers[kind]
            if role is CustodyRole.INDEPENDENT_VERIFIER
            else Ed25519AttestationSigner.generate(
                key_id=f"custody-{kind.value.lower()}-{role.value}"
            )
        )
        for kind in DEPENDENCY_ORDER
        for role in CustodyRole
    }
    entries = tuple(
        TrustAnchorEntry(
            receipt_kind=kind,
            authority_id=f"authority-{kind.value.lower()}",
            key_id=signers[kind].verifier().key_id,
            public_key_base64=signers[kind].verifier().public_key_base64,
            public_key_sha256=signers[kind].verifier().public_key_sha256,
            enrolled_at_utc=BASE_TIME - timedelta(minutes=10),
        )
        for kind in ReceiptKind
    )
    custody_entries = tuple(
        CustodyTrustAnchorEntry(
            receipt_kind=kind,
            role=role,
            actor_id=(
                f"authority-{kind.value.lower()}"
                if role is CustodyRole.INDEPENDENT_VERIFIER
                else f"{role.value}-{kind.value.lower()}"
            ),
            key_id=custody_signers[(kind, role)].verifier().key_id,
            public_key_base64=custody_signers[(kind, role)].verifier().public_key_base64,
            public_key_sha256=custody_signers[(kind, role)].verifier().public_key_sha256,
            enrolled_at_utc=BASE_TIME - timedelta(minutes=10),
        )
        for kind in DEPENDENCY_ORDER
        for role in CustodyRole
    )
    unsigned_manifest = ReceiptTrustAnchorManifest(
        schema_version="1.0.0",
        protocol_id="structure-two-receipt-trust-anchor-manifest@1.0",
        registry_id=_uuid("registry"),
        issued_at_utc=BASE_TIME - timedelta(minutes=1),
        registry_authority_id="registry-authority",
        registry_authority_key_id=registry_authority.verifier().key_id,
        registry_authority_public_key_sha256=(registry_authority.verifier().public_key_sha256),
        entries=entries,
        custody_entries=custody_entries,
    )
    manifest = issue_trust_anchor_manifest(unsigned_manifest, registry_authority=registry_authority)
    current = _current_policy()
    payload = current.model_dump(mode="python")
    payload.update(
        trust_anchor_status=TrustAnchorStatus.ENROLLED,
        trust_anchor_manifest_sha256=trust_anchor_manifest_content_sha256(manifest),
        custody_attestation_status=CustodyAttestationStatus.PER_HOP_INDEPENDENT,
        dependency_bindings=tuple(
            binding.model_copy(
                update={
                    "config_spec_commitment_status": DependencyCommitmentStatus.ENROLLED,
                    "expected_config_content_sha256": _hash(f"config:{binding.receipt_kind.value}"),
                    "expected_spec_content_sha256": _hash(f"spec:{binding.receipt_kind.value}"),
                }
            )
            if binding.receipt_kind is not ReceiptKind.AUTHORIZATION
            else binding
            for binding in current.dependency_bindings
        ),
    )
    policy = TrustedAblationAuthorizationPolicy.model_validate(payload)
    return policy, manifest, registry_authority, signers, custody_signers


def _parents(
    kind: ReceiptKind, receipts: dict[ReceiptKind, FormalDependencyReceipt]
) -> tuple[ParentReceiptRef, ...]:
    return tuple(
        ParentReceiptRef(
            receipt_kind=parent,
            receipt_id=receipts[parent].receipt_id,
            receipt_content_sha256=formal_receipt_content_sha256(receipts[parent]),
        )
        for parent in EXPECTED_PARENTS[kind]
    )


def _custody(
    kind: ReceiptKind,
    *,
    receipt_id: UUID,
    run_id: UUID,
    nonce: UUID,
    issued_at: datetime,
    source_hash: str,
    result_hash: str,
    custody_signers: dict[tuple[ReceiptKind, CustodyRole], Ed25519AttestationSigner],
) -> tuple[CustodyHop, ...]:
    intermediate = _hash(f"{kind.value}:raw-evidence")
    unsigned = (
        CustodyHop(
            sequence=0,
            actor_id=f"{CustodyRole.PRODUCER.value}-{kind.value.lower()}",
            actor_key_id=custody_signers[(kind, CustodyRole.PRODUCER)].verifier().key_id,
            actor_public_key_sha256=(
                custody_signers[(kind, CustodyRole.PRODUCER)].verifier().public_key_sha256
            ),
            role=CustodyRole.PRODUCER,
            received_artifact_sha256=source_hash,
            released_artifact_sha256=intermediate,
            received_at_utc=issued_at - timedelta(minutes=6),
            released_at_utc=issued_at - timedelta(minutes=5),
        ),
        CustodyHop(
            sequence=1,
            actor_id=f"{CustodyRole.EVIDENCE_CUSTODIAN.value}-{kind.value.lower()}",
            actor_key_id=(
                custody_signers[(kind, CustodyRole.EVIDENCE_CUSTODIAN)].verifier().key_id
            ),
            actor_public_key_sha256=(
                custody_signers[(kind, CustodyRole.EVIDENCE_CUSTODIAN)].verifier().public_key_sha256
            ),
            role=CustodyRole.EVIDENCE_CUSTODIAN,
            received_artifact_sha256=intermediate,
            released_artifact_sha256=result_hash,
            received_at_utc=issued_at - timedelta(minutes=5),
            released_at_utc=issued_at - timedelta(minutes=4),
        ),
        CustodyHop(
            sequence=2,
            actor_id=f"authority-{kind.value.lower()}",
            actor_key_id=(
                custody_signers[(kind, CustodyRole.INDEPENDENT_VERIFIER)].verifier().key_id
            ),
            actor_public_key_sha256=(
                custody_signers[(kind, CustodyRole.INDEPENDENT_VERIFIER)]
                .verifier()
                .public_key_sha256
            ),
            role=CustodyRole.INDEPENDENT_VERIFIER,
            received_artifact_sha256=result_hash,
            released_artifact_sha256=result_hash,
            received_at_utc=issued_at - timedelta(minutes=4),
            released_at_utc=issued_at - timedelta(minutes=3),
        ),
    )
    return tuple(
        issue_custody_hop(
            hop,
            receipt_kind=kind,
            receipt_id=receipt_id,
            run_id=run_id,
            receipt_nonce=nonce,
            actor=custody_signers[(kind, hop.role)],
        )
        for hop in unsigned
    )


def _common(
    kind: ReceiptKind,
    *,
    minute: int,
    run_id: UUID,
    receipts: dict[ReceiptKind, FormalDependencyReceipt],
    manifest: ReceiptTrustAnchorManifest,
    signer: Ed25519AttestationSigner,
    custody_signers: dict[tuple[ReceiptKind, CustodyRole], Ed25519AttestationSigner],
    result_hash: str,
) -> dict[str, Any]:
    issued = BASE_TIME + timedelta(minutes=minute)
    source_hash = _hash("formal-source-bundle")
    receipt_id = _uuid(f"receipt:{kind.value}")
    nonce = _uuid(f"nonce:{kind.value}")
    return {
        "schema_version": "1.0.0",
        "receipt_kind": kind,
        "protocol_id": EXPECTED_PROTOCOL_IDS[kind],
        "receipt_id": receipt_id,
        "run_id": run_id,
        "seven_operator_identity": "ORRER_CHEH",
        "parent_receipts": _parents(kind, receipts),
        "source_bundle_sha256": source_hash,
        "config_content_sha256": _hash(f"config:{kind.value}"),
        "spec_content_sha256": _hash(f"spec:{kind.value}"),
        "result_content_sha256": result_hash,
        "producer_id": f"{CustodyRole.PRODUCER.value}-{kind.value.lower()}",
        "independent_verifier_id": f"authority-{kind.value.lower()}",
        "issued_at_utc": issued,
        "verified_at_utc": issued + timedelta(seconds=10),
        "freshness_window_seconds": 3600,
        "expires_at_utc": issued + timedelta(hours=1),
        "custody_chain": _custody(
            kind,
            receipt_id=receipt_id,
            run_id=run_id,
            nonce=nonce,
            issued_at=issued,
            source_hash=source_hash,
            result_hash=result_hash,
            custody_signers=custody_signers,
        ),
        "nonce": nonce,
        "replay_registry_id": manifest.registry_id,
        "trust_anchor_manifest_sha256": trust_anchor_manifest_content_sha256(manifest),
        "signer_key_id": signer.verifier().key_id,
        "signer_public_key_sha256": signer.verifier().public_key_sha256,
    }


def _task12_trace() -> Task12RawProposalTrace:
    states = (
        Task12State(
            state_id="s0",
            h="h0",
            r="r0",
            i="i0",
            c="c0",
            z="z0",
            action_id="ask",
            utility=0.0,
            target_probability=0.5,
        ),
        Task12State(
            state_id="s1",
            h="h1",
            r="r1",
            i="i1",
            c="c1",
            z="z1",
            action_id="deliver",
            utility=1.0,
            target_probability=0.5,
        ),
    )
    rows = tuple(
        Task12ProposalRow(
            source_state_id=source,
            destinations=tuple(
                Task12ProposalProbability(destination_state_id=destination, probability=0.5)
                for destination in ("s0", "s1")
            ),
        )
        for source in ("s0", "s1")
    )
    current = "s0"
    events = []
    for index in range(9):
        proposed = "s1" if current == "s0" else "s0"
        events.append(
            Task12ProposalEvent(
                event_index=index,
                source_state_id=current,
                proposed_state_id=proposed,
                uniform_draw=0.0,
                accepted=True,
                resulting_state_id=proposed,
            )
        )
        current = proposed
    return Task12RawProposalTrace(
        trace_id=_uuid("task12-raw-trace"),
        selected_kernel="blocked_typed_metropolis_hastings",
        states=states,
        proposal_rows=rows,
        initial_state_id="s0",
        events=tuple(events),
        burn_in_events=0,
        reference_action_distribution=(
            ActionProbability(action_id="ask", probability=0.5),
            ActionProbability(action_id="deliver", probability=0.5),
        ),
        reference_expected_utility=0.5,
        elementary_evaluations=9,
    )


def _thresholds() -> Task12GateThresholds:
    return Task12GateThresholds(
        max_detailed_balance_error=1e-9,
        max_stationarity_error=1e-9,
        min_acceptance_rate=0.01,
        max_acceptance_rate=1.0,
        min_effective_sample_size_per_evaluation=0.01,
        max_action_total_variation=0.05,
        max_absolute_expected_utility_difference=0.05,
    )


def _p5_stages() -> tuple[P5StageDecomposition, ...]:
    recalls = ((0.60, 0.80), (0.40, 0.75), (0.35, 0.70), (0.30, 0.65), (0.25, 0.60))
    output = []
    for index, (deployable, oracle) in enumerate(recalls):
        prior = recalls[index - 1] if index else (deployable, oracle)
        deployable_loss = max(0.0, prior[0] - deployable)
        oracle_loss = max(0.0, prior[1] - oracle)
        output.append(
            P5StageDecomposition(
                stage=tuple(P5PipelineStage)[index],
                best_deployable_recall=deployable,
                best_oracle_recall=oracle,
                headroom=max(0.0, oracle - deployable),
                deployable_loss_from_previous_stage=deployable_loss,
                oracle_loss_from_previous_stage=oracle_loss,
                downstream_excess_loss=max(0.0, deployable_loss - oracle_loss),
            )
        )
    return tuple(output)


def _build_receipts(
    manifest: ReceiptTrustAnchorManifest,
    signers: dict[ReceiptKind, Ed25519AttestationSigner],
    custody_signers: dict[tuple[ReceiptKind, CustodyRole], Ed25519AttestationSigner],
) -> tuple[UUID, dict[ReceiptKind, FormalDependencyReceipt]]:
    run_id = _uuid("formal-run")
    receipts: dict[ReceiptKind, FormalDependencyReceipt] = {}
    minutes = {
        ReceiptKind.GATE_B_V0_8: 1,
        ReceiptKind.TASK_7: 1,
        ReceiptKind.TASK_8: 1,
        ReceiptKind.TASK_9: 1,
        ReceiptKind.TASK_10: 1,
        ReceiptKind.TASK_11: 4,
        ReceiptKind.TASK_12: 7,
        ReceiptKind.TASK_13: 10,
        ReceiptKind.PROPOSAL_P5: 10,
        ReceiptKind.AUDIT_ROUND_1: 13,
        ReceiptKind.AUDIT_ROUND_2: 16,
    }
    for kind in DEPENDENCY_ORDER:
        signer = signers[kind]
        extra: dict[str, Any]
        if kind is ReceiptKind.TASK_12:
            trace = _task12_trace()
            metrics = recompute_task12_gate_result(trace, _thresholds())
            result_hash = content_sha256(
                {
                    "selected_rejuvenation_kernel": trace.selected_kernel,
                    "raw_proposal_trace_sha256": content_sha256(trace),
                    "recomputed_gate_result": metrics,
                }
            )
            extra = {
                "independent_definition_protocol_id": (
                    "structure-two-backbone-rejuvenation-task-12@0.1"
                ),
                "independent_definition_spec_content_sha256": _hash(f"spec:{kind.value}"),
                "selected_rejuvenation_kernel": trace.selected_kernel,
                "raw_proposal_trace": trace,
                "raw_proposal_trace_sha256": content_sha256(trace),
                "gate_thresholds": _thresholds(),
                "recomputed_gate_result": metrics,
                "formal_task_12_passed": True,
            }
            receipt_type: type[FormalReceiptBase] = Task12Receipt
        elif kind is ReceiptKind.PROPOSAL_P5:
            stages = _p5_stages()
            diagnosis = diagnose_p5_bottleneck(stages, oracle_action_gain=0.2)
            result_hash = content_sha256(
                {
                    "stage_decomposition": stages,
                    "oracle_action_gain": 0.2,
                    "diagnosis": diagnosis,
                }
            )
            extra = {
                "independent_definition_protocol_id": (
                    "structure-two-backbone-proposal-headroom-p5@0.1"
                ),
                "independent_definition_spec_content_sha256": _hash(f"spec:{kind.value}"),
                "stage_decomposition": stages,
                "oracle_action_gain": 0.2,
                "recall_headroom_epsilon": 0.01,
                "action_gain_epsilon": 0.0,
                "diagnosis": diagnosis,
                "completed_diagnostic": True,
            }
            receipt_type = ProposalP5Receipt
        else:
            result_hash = _hash(f"result:{kind.value}")
            receipt_type, extra = {
                ReceiptKind.GATE_B_V0_8: (
                    GateBV08Receipt,
                    {
                        "comparator_count": 8,
                        "comparator_relations_frozen": True,
                        "causal_windows_frozen": True,
                        "formal_gate_b_passed": True,
                    },
                ),
                ReceiptKind.TASK_7: (
                    Task7Receipt,
                    {
                        "strict_o_window_verified": True,
                        "multi_axis_equivalence_verified": True,
                        "action_equivalence_verified": True,
                        "non_self_move_verified": True,
                        "multi_sweep_verified": True,
                        "long_suffix_cost_verified": True,
                        "formal_task_7_passed": True,
                    },
                ),
                ReceiptKind.TASK_8: (
                    Task8Receipt,
                    {
                        "endpoint_preregistered_before_run": True,
                        "endpoint_consumes_h_plus_z_cross_c": True,
                        "thresholds_unchanged_after_run": True,
                        "action_and_utility_gate_passed": True,
                        "formal_task_8_passed": True,
                    },
                ),
                ReceiptKind.TASK_9: (
                    Task9Receipt,
                    {
                        "selected_method_identity": "ORRER_CHEH",
                        "selected_method_receipt_content_sha256": _hash("selected-method"),
                        "operator_identity_order": (
                            "OPCEU",
                            "ORRER_CHEH",
                            "PCHMP",
                            "CF-BOCPD",
                            "RGRC",
                            "CCRR",
                            "CIAV",
                        ),
                        "implementation_manifest_id": (
                            "structure-two-task9-operator-implementations@1.1"
                        ),
                        "implementation_manifest_content_sha256": _hash(
                            "task9-implementation-manifest"
                        ),
                        "exact_four_couplings_verified": True,
                        "selected_method_receipt_verified": True,
                        "authenticated_enabled_noop_allowed": True,
                        "authenticated_enabled_noop_receipts_verified": True,
                        "formal_task_9_passed": True,
                    },
                ),
                ReceiptKind.TASK_10: (
                    Task10Receipt,
                    {
                        "selected_particle_budget": 128,
                        "budget_curve_recomputed": True,
                        "formal_task_10_passed": True,
                    },
                ),
                ReceiptKind.TASK_11: (
                    Task11Receipt,
                    {
                        "selected_resampling_policy": "systematic@ess=0.5",
                        "raw_arm_matrix_recomputed": True,
                        "formal_task_11_passed": True,
                    },
                ),
                ReceiptKind.TASK_13: (
                    Task13Receipt,
                    {
                        "selected_differentiability_strategy": (
                            "score_function_unbiased_estimator"
                        ),
                        "raw_gradient_checks_recomputed": True,
                        "formal_task_13_passed": True,
                    },
                ),
                ReceiptKind.AUDIT_ROUND_1: (
                    AuditRound1Receipt,
                    {
                        "audit_round": 1,
                        "forged_complete_attack_passed": True,
                        "stale_replay_substitution_attacks_passed": True,
                        "caller_selected_pass_attack_passed": True,
                        "all_p0_surfaces_covered": True,
                    },
                ),
                ReceiptKind.AUDIT_ROUND_2: (
                    AuditRound2Receipt,
                    {
                        "audit_round": 2,
                        "independent_reviewer": True,
                        "forged_complete_attack_passed": True,
                        "stale_replay_substitution_attacks_passed": True,
                        "caller_selected_pass_attack_passed": True,
                        "all_p0_surfaces_covered": True,
                    },
                ),
            }[kind]
        common = _common(
            kind,
            minute=minutes[kind],
            run_id=run_id,
            receipts=receipts,
            manifest=manifest,
            signer=signer,
            custody_signers=custody_signers,
            result_hash=result_hash,
        )
        unsigned = receipt_type.model_validate({**common, **extra})
        receipts[kind] = cast(
            FormalDependencyReceipt,
            issue_formal_receipt(unsigned, independent_verifier=signer),
        )
    return run_id, receipts


def _evaluate(
    *,
    policy: TrustedAblationAuthorizationPolicy,
    manifest: ReceiptTrustAnchorManifest,
    registry_authority: Ed25519AttestationSigner,
    signers: dict[ReceiptKind, Ed25519AttestationSigner],
    run_id: UUID,
    receipts: dict[ReceiptKind, FormalDependencyReceipt],
    registry: ReceiptReplayRegistry | None = None,
    now: datetime = BASE_TIME + timedelta(minutes=20),
):
    return evaluate_trusted_seven_operator_ablation_authorization(
        policy=policy,
        run_id=run_id,
        receipts=receipts,
        verification_time_utc=now,
        replay_registry=registry or ReceiptReplayRegistry(registry_id=manifest.registry_id),
        decision_id=_uuid("decision"),
        authorization_nonce=_uuid("authorization-nonce"),
        trust_anchor_manifest=manifest,
        registry_authority=registry_authority.verifier(),
        authorization_authority=signers[ReceiptKind.AUTHORIZATION],
    )


def _diagnose_receipt_dag(
    *,
    policy: TrustedAblationAuthorizationPolicy,
    manifest: ReceiptTrustAnchorManifest,
    registry_authority: Ed25519AttestationSigner,
    run_id: UUID,
    receipts: dict[ReceiptKind, FormalDependencyReceipt],
    registry: ReceiptReplayRegistry | None = None,
    now: datetime = BASE_TIME + timedelta(minutes=20),
) -> tuple[dict[ReceiptKind, DependencyState], tuple[str, ...]]:
    """Exercise the typed verifier without creating an authorization surface."""

    verify_trust_anchor_manifest(
        manifest,
        registry_authority=registry_authority.verifier(),
        expected_manifest_sha256=cast(str, policy.trust_anchor_manifest_sha256),
        verification_time_utc=now,
    )
    replay = registry or ReceiptReplayRegistry(registry_id=manifest.registry_id)
    verified: dict[ReceiptKind, FormalDependencyReceipt] = {}
    states: dict[ReceiptKind, DependencyState] = {}
    blockers: list[str] = []
    for kind in DEPENDENCY_ORDER:
        parents = EXPECTED_PARENTS[kind]
        if any(parent not in verified for parent in parents):
            states[kind] = DependencyState.BLOCKED_BY_PARENT
            blockers.append(f"{kind.value}:parent_not_verified")
            continue
        receipt = receipts[kind]
        if receipt.receipt_kind is not kind:
            states[kind] = DependencyState.INVALID
            blockers.append(f"{kind.value}:cross-task receipt substitution")
            continue
        try:
            verified[kind] = verify_formal_receipt(
                receipt,
                policy=policy,
                manifest=manifest,
                verified_parents={parent: verified[parent] for parent in parents},
                expected_run_id=run_id,
                verification_time_utc=now,
                replay_registry=replay,
            )
        except ValueError as exc:
            states[kind] = DependencyState.INVALID
            blockers.append(f"{kind.value}:{exc}")
        else:
            states[kind] = DependencyState.VERIFIED
    return states, tuple(blockers)


def test_checked_in_policy_is_fail_closed_and_names_only_orrer_cheh() -> None:
    policy = _current_policy()
    decision = evaluate_trusted_seven_operator_ablation_authorization(
        policy=policy,
        run_id=_uuid("missing-run"),
        receipts={},
        verification_time_utc=BASE_TIME,
        replay_registry=ReceiptReplayRegistry(registry_id=_uuid("empty-registry")),
        decision_id=_uuid("missing-decision"),
    )
    assert policy.seven_operator_identity == "ORRER_CHEH"
    assert policy.authenticated_enabled_noop_allowed is True
    assert policy.trust_anchor_status is TrustAnchorStatus.NOT_ENROLLED
    assert decision.authorized is False
    assert decision.decision_status is AuthorizationDecisionStatus.NOT_AUTHORIZED
    assert "trust_anchor_manifest_not_enrolled" in decision.blockers
    assert tuple(item.receipt_kind for item in decision.dependency_assessments) == DEPENDENCY_ORDER


def test_policy_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    payload = POLICY_PATH.read_text(encoding="utf-8")
    duplicate = payload.replace(
        '"schema_version": "1.0.0",',
        '"schema_version": "1.0.0", "schema_version": "1.0.0",',
        1,
    )
    path = tmp_path / "duplicate.json"
    path.write_text(duplicate, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        TrustedAblationAuthorizationPolicy.load(path)


def test_task12_recomputes_all_gates_from_raw_proposal_trace() -> None:
    result = recompute_task12_gate_result(_task12_trace(), _thresholds())
    assert result.detailed_balance_error == pytest.approx(0.0)
    assert result.stationarity_error == pytest.approx(0.0)
    assert result.action_total_variation == pytest.approx(0.0)
    assert result.absolute_expected_utility_difference == pytest.approx(0.0)
    assert result.touched_axes == ("H", "R", "I", "C", "Z")
    assert result.non_self_move_count == 9
    assert result.all_passed is True


def test_task12_rejects_caller_selected_fake_gate_result() -> None:
    policy, manifest, _, signers, custody_signers = _trust_context()
    del policy
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    del run_id
    receipt = cast(Task12Receipt, receipts[ReceiptKind.TASK_12])
    forged_metrics = receipt.recomputed_gate_result.model_copy(
        update={"action_total_variation": 0.04}
    )
    forged = receipt.model_copy(update={"recomputed_gate_result": forged_metrics})
    with pytest.raises(ValidationError, match="not recomputed"):
        Task12Receipt.model_validate(forged.model_dump(mode="python"))


def test_task12_rejects_forged_raw_acceptance_path() -> None:
    trace = _task12_trace()
    events = list(trace.events)
    events[0] = events[0].model_copy(update={"accepted": False, "resulting_state_id": "s0"})
    forged = trace.model_copy(update={"events": tuple(events)})
    with pytest.raises(ValidationError, match="acceptance/result"):
        Task12RawProposalTrace.model_validate(forged.model_dump(mode="python"))


def test_task12_rejects_reference_rewritten_to_match_a_biased_sample() -> None:
    trace = _task12_trace()
    forged = trace.model_copy(
        update={
            "events": trace.events[:-1],
            "elementary_evaluations": 8,
            "reference_action_distribution": (
                ActionProbability(action_id="ask", probability=5 / 9),
                ActionProbability(action_id="deliver", probability=4 / 9),
            ),
            "reference_expected_utility": 4 / 9,
        }
    )
    with pytest.raises(ValidationError, match="aggregated from target mass"):
        Task12RawProposalTrace.model_validate(forged.model_dump(mode="python"))


def test_p5_reports_mixed_bottleneck_without_generic_pass() -> None:
    stages = _p5_stages()
    assert diagnose_p5_bottleneck(stages, oracle_action_gain=0.2) is (
        P5BottleneckDiagnosis.MIXED_BOTTLENECK
    )
    assert "passed" not in ProposalP5Receipt.model_fields


def test_p5_rejects_caller_supplied_stage_loss() -> None:
    policy, manifest, _, signers, custody_signers = _trust_context()
    del policy
    _, receipts = _build_receipts(manifest, signers, custody_signers)
    receipt = cast(ProposalP5Receipt, receipts[ReceiptKind.PROPOSAL_P5])
    stages = list(receipt.stage_decomposition)
    stages[1] = stages[1].model_copy(
        update={
            "deployable_loss_from_previous_stage": 0.1,
            "downstream_excess_loss": 0.05,
        }
    )
    forged = receipt.model_copy(update={"stage_decomposition": tuple(stages)})
    with pytest.raises(ValidationError, match="per-stage losses"):
        ProposalP5Receipt.model_validate(forged.model_dump(mode="python"))


def test_trust_anchor_manifest_requires_registered_root_signature() -> None:
    policy, manifest, _, _, _ = _trust_context()
    attacker = Ed25519AttestationSigner.generate(key_id="registry-root")
    with pytest.raises(ValueError, match="root identity mismatch"):
        verify_trust_anchor_manifest(
            manifest,
            registry_authority=attacker.verifier(),
            expected_manifest_sha256=cast(str, policy.trust_anchor_manifest_sha256),
            verification_time_utc=BASE_TIME,
        )


def test_trust_anchor_manifest_rejects_one_key_for_multiple_receipt_authorities() -> None:
    _, manifest, _, _, _ = _trust_context()
    payload = manifest.model_dump(mode="python", exclude={"attestation"})
    entries = list(payload["entries"])
    entries[1]["key_id"] = entries[0]["key_id"]
    entries[1]["public_key_base64"] = entries[0]["public_key_base64"]
    entries[1]["public_key_sha256"] = entries[0]["public_key_sha256"]
    payload["entries"] = entries
    with pytest.raises(ValidationError, match="independent signing key"):
        ReceiptTrustAnchorManifest.model_validate(payload)


def test_checked_in_not_enrolled_policy_rejects_a_complete_self_signed_positive_chain() -> None:
    _, manifest, registry_authority, signers, custody_signers = _trust_context()
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    decision = evaluate_trusted_seven_operator_ablation_authorization(
        policy=_current_policy(),
        run_id=run_id,
        receipts=receipts,
        verification_time_utc=BASE_TIME + timedelta(minutes=20),
        replay_registry=ReceiptReplayRegistry(registry_id=manifest.registry_id),
        decision_id=_uuid("forged-current-policy-decision"),
        authorization_nonce=_uuid("forged-current-policy-authorization-nonce"),
        trust_anchor_manifest=manifest,
        registry_authority=registry_authority.verifier(),
        authorization_authority=signers[ReceiptKind.AUTHORIZATION],
    )
    assert decision.authorized is False
    assert "trust_anchor_manifest_not_enrolled" in decision.blockers
    assert all(
        item.state is not DependencyState.VERIFIED for item in decision.dependency_assessments
    )


def test_complete_typed_receipt_dag_verifies_but_cannot_override_frozen_policy() -> None:
    policy, manifest, registry_authority, signers, custody_signers = _trust_context()
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    states, receipt_blockers = _diagnose_receipt_dag(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        run_id=run_id,
        receipts=receipts,
    )
    assert set(states.values()) == {DependencyState.VERIFIED}
    assert receipt_blockers == ()
    decision = _evaluate(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        signers=signers,
        run_id=run_id,
        receipts=receipts,
    )
    assert decision.authorized is False
    assert "caller_policy_differs_from_checked_in_frozen_policy" in decision.blockers
    assert "persistent_replay_registry_not_enrolled" in decision.blockers
    assert "per_hop_independent_custody_attestation_not_enrolled" in decision.blockers


def test_wrong_signature_invalidates_child_and_propagates_to_descendants() -> None:
    policy, manifest, registry_authority, signers, custody_signers = _trust_context()
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    task11 = receipts[ReceiptKind.TASK_11]
    attacker = Ed25519AttestationSigner.generate(key_id=task11.signer_key_id)
    forged = task11.model_copy(
        update={
            "attestation": attacker.sign(
                f"{FORMAL_RECEIPT_DOMAIN_PREFIX}:{ReceiptKind.TASK_11.value}",
                attested_payload(task11),
            )
        }
    )
    receipts[ReceiptKind.TASK_11] = cast(FormalDependencyReceipt, forged)
    states, blockers = _diagnose_receipt_dag(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        run_id=run_id,
        receipts=receipts,
    )
    assert states[ReceiptKind.TASK_11] is DependencyState.INVALID
    assert states[ReceiptKind.TASK_12] is DependencyState.BLOCKED_BY_PARENT
    assert states[ReceiptKind.TASK_13] is DependencyState.BLOCKED_BY_PARENT
    assert states[ReceiptKind.PROPOSAL_P5] is DependencyState.BLOCKED_BY_PARENT
    assert any("signature does not match" in item for item in blockers)


def test_stale_receipts_are_rejected_and_propagated() -> None:
    policy, manifest, registry_authority, signers, custody_signers = _trust_context()
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    states, blockers = _diagnose_receipt_dag(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        run_id=run_id,
        receipts=receipts,
        now=BASE_TIME + timedelta(hours=2),
    )
    assert DependencyState.INVALID in set(states.values())
    assert any("receipt is stale" in blocker for blocker in blockers)


def test_replay_registry_rejects_second_consumption() -> None:
    policy, manifest, registry_authority, signers, custody_signers = _trust_context()
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    registry = ReceiptReplayRegistry(registry_id=manifest.registry_id)
    first_states, first_blockers = _diagnose_receipt_dag(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        run_id=run_id,
        receipts=receipts,
        registry=registry,
    )
    second_states, second_blockers = _diagnose_receipt_dag(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        run_id=run_id,
        receipts=receipts,
        registry=registry,
    )
    assert set(first_states.values()) == {DependencyState.VERIFIED}
    assert first_blockers == ()
    assert DependencyState.INVALID in set(second_states.values())
    assert any("replayed nonce" in blocker for blocker in second_blockers)


def test_cross_task_receipt_substitution_is_rejected() -> None:
    policy, manifest, registry_authority, signers, custody_signers = _trust_context()
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    receipts[ReceiptKind.TASK_11] = receipts[ReceiptKind.TASK_10]
    states, blockers = _diagnose_receipt_dag(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        run_id=run_id,
        receipts=receipts,
    )
    assert states[ReceiptKind.TASK_11] is DependencyState.INVALID
    assert any("cross-task receipt substitution" in item for item in blockers)


def test_cross_run_receipt_substitution_is_rejected() -> None:
    policy, manifest, registry_authority, signers, custody_signers = _trust_context()
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    task10 = receipts[ReceiptKind.TASK_10]
    receipts[ReceiptKind.TASK_10] = cast(
        FormalDependencyReceipt,
        task10.model_copy(update={"run_id": _uuid("foreign-run")}),
    )
    states, blockers = _diagnose_receipt_dag(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        run_id=run_id,
        receipts=receipts,
    )
    assert states[ReceiptKind.TASK_10] is DependencyState.INVALID
    assert any("cross-run receipt substitution" in item for item in blockers)


def test_parent_content_hash_substitution_is_rejected() -> None:
    policy, manifest, registry_authority, signers, custody_signers = _trust_context()
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    task11 = receipts[ReceiptKind.TASK_11]
    refs = list(task11.parent_receipts)
    refs[0] = refs[0].model_copy(update={"receipt_content_sha256": "f" * 64})
    receipts[ReceiptKind.TASK_11] = cast(
        FormalDependencyReceipt,
        task11.model_copy(update={"parent_receipts": tuple(refs)}),
    )
    states, blockers = _diagnose_receipt_dag(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        run_id=run_id,
        receipts=receipts,
    )
    assert states[ReceiptKind.TASK_11] is DependencyState.INVALID
    assert any("parent receipt id/content hash mismatch" in item for item in blockers)


def test_even_enrolled_child_signer_cannot_rehash_and_resign_a_parent_reference() -> None:
    policy, manifest, registry_authority, signers, custody_signers = _trust_context()
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    task11 = cast(Task11Receipt, receipts[ReceiptKind.TASK_11])
    refs = list(task11.parent_receipts)
    refs[0] = refs[0].model_copy(update={"receipt_content_sha256": "c" * 64})
    unsigned = task11.model_copy(update={"parent_receipts": tuple(refs), "attestation": None})
    receipts[ReceiptKind.TASK_11] = cast(
        FormalDependencyReceipt,
        issue_formal_receipt(
            unsigned,
            independent_verifier=signers[ReceiptKind.TASK_11],
        ),
    )
    states, blockers = _diagnose_receipt_dag(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        run_id=run_id,
        receipts=receipts,
    )
    assert states[ReceiptKind.TASK_11] is DependencyState.INVALID
    assert any("parent receipt id/content hash mismatch" in item for item in blockers)


def test_source_config_spec_result_substitution_breaks_signature() -> None:
    policy, manifest, registry_authority, signers, custody_signers = _trust_context()
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    task8 = receipts[ReceiptKind.TASK_8]
    receipts[ReceiptKind.TASK_8] = cast(
        FormalDependencyReceipt,
        task8.model_copy(update={"config_content_sha256": "e" * 64}),
    )
    states, blockers = _diagnose_receipt_dag(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        run_id=run_id,
        receipts=receipts,
    )
    assert states[ReceiptKind.TASK_8] is DependencyState.INVALID
    assert any("preregistered commitments" in item for item in blockers)


def test_enrolled_signers_cannot_change_spec_and_result_then_resign() -> None:
    policy, manifest, registry_authority, signers, custody_signers = _trust_context()
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    original = cast(Task8Receipt, receipts[ReceiptKind.TASK_8])
    replacement_result = "b" * 64
    hops = list(original.custody_chain)
    hops[1] = hops[1].model_copy(
        update={"released_artifact_sha256": replacement_result, "attestation": None}
    )
    hops[2] = hops[2].model_copy(
        update={
            "received_artifact_sha256": replacement_result,
            "released_artifact_sha256": replacement_result,
            "attestation": None,
        }
    )
    for index in (1, 2):
        hops[index] = issue_custody_hop(
            hops[index],
            receipt_kind=ReceiptKind.TASK_8,
            receipt_id=original.receipt_id,
            run_id=run_id,
            receipt_nonce=original.nonce,
            actor=custody_signers[(ReceiptKind.TASK_8, hops[index].role)],
        )
    forged = original.model_copy(
        update={
            "spec_content_sha256": "a" * 64,
            "result_content_sha256": replacement_result,
            "custody_chain": tuple(hops),
            "attestation": None,
        }
    )
    receipts[ReceiptKind.TASK_8] = cast(
        FormalDependencyReceipt,
        issue_formal_receipt(forged, independent_verifier=signers[ReceiptKind.TASK_8]),
    )
    states, blockers = _diagnose_receipt_dag(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        run_id=run_id,
        receipts=receipts,
    )
    assert states[ReceiptKind.TASK_8] is DependencyState.INVALID
    assert any("preregistered commitments" in item for item in blockers)


def test_custody_chain_tamper_is_rejected_before_signature_check() -> None:
    policy, manifest, registry_authority, signers, custody_signers = _trust_context()
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    task7 = receipts[ReceiptKind.TASK_7]
    hops = list(task7.custody_chain)
    hops[1] = hops[1].model_copy(update={"received_artifact_sha256": "d" * 64})
    receipts[ReceiptKind.TASK_7] = cast(
        FormalDependencyReceipt,
        task7.model_copy(update={"custody_chain": tuple(hops)}),
    )
    states, blockers = _diagnose_receipt_dag(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        run_id=run_id,
        receipts=receipts,
    )
    assert states[ReceiptKind.TASK_7] is DependencyState.INVALID
    assert any("custody artifact hashes" in item for item in blockers)


def test_same_key_cannot_masquerade_as_all_three_custody_roles() -> None:
    _, manifest, _, signers, custody_signers = _trust_context()
    _, receipts = _build_receipts(manifest, signers, custody_signers)
    gate_b = cast(GateBV08Receipt, receipts[ReceiptKind.GATE_B_V0_8])
    hops = tuple(
        hop.model_copy(
            update={
                "actor_key_id": gate_b.signer_key_id,
                "actor_public_key_sha256": gate_b.signer_public_key_sha256,
            }
        )
        for hop in gate_b.custody_chain
    )
    forged = gate_b.model_copy(update={"custody_chain": hops})
    with pytest.raises(ValidationError, match="must not reuse one signing key"):
        GateBV08Receipt.model_validate(forged.model_dump(mode="python"))


def test_attacker_cannot_rewrap_an_expired_receipt_with_fresh_times() -> None:
    policy, manifest, registry_authority, signers, custody_signers = _trust_context()
    run_id, receipts = _build_receipts(manifest, signers, custody_signers)
    old = cast(GateBV08Receipt, receipts[ReceiptKind.GATE_B_V0_8])
    attacker = Ed25519AttestationSigner.generate(key_id=old.signer_key_id)
    issued = BASE_TIME + timedelta(minutes=19)
    hops = list(old.custody_chain)
    hops[-1] = hops[-1].model_copy(
        update={
            "actor_key_id": attacker.verifier().key_id,
            "actor_public_key_sha256": attacker.verifier().public_key_sha256,
        }
    )
    unsigned = old.model_copy(
        update={
            "issued_at_utc": issued,
            "verified_at_utc": issued + timedelta(seconds=1),
            "expires_at_utc": issued + timedelta(hours=1),
            "nonce": _uuid("rewrapped-nonce"),
            "custody_chain": tuple(hops),
            "signer_public_key_sha256": attacker.verifier().public_key_sha256,
            "attestation": None,
        }
    )
    receipts[ReceiptKind.GATE_B_V0_8] = cast(
        FormalDependencyReceipt,
        issue_formal_receipt(unsigned, independent_verifier=attacker),
    )
    states, blockers = _diagnose_receipt_dag(
        policy=policy,
        manifest=manifest,
        registry_authority=registry_authority,
        run_id=run_id,
        receipts=receipts,
    )
    assert states[ReceiptKind.GATE_B_V0_8] is DependencyState.INVALID
    assert any("custody_hop" in item and "signature does not match" in item for item in blockers)


def test_model_copy_cannot_turn_denied_decision_into_authorization() -> None:
    policy = _current_policy()
    decision = evaluate_trusted_seven_operator_ablation_authorization(
        policy=policy,
        run_id=_uuid("denied-run"),
        receipts={},
        verification_time_utc=BASE_TIME,
        replay_registry=ReceiptReplayRegistry(registry_id=_uuid("denied-registry")),
        decision_id=_uuid("denied-decision"),
    )
    forged = decision.model_copy(
        update={
            "authorized": True,
            "decision_status": AuthorizationDecisionStatus.AUTHORIZED,
            "blockers": (),
        }
    )
    with pytest.raises(ValidationError):
        verify_trusted_seven_operator_ablation_authorization(
            forged,
            policy=policy,
            manifest=ReceiptTrustAnchorManifest.model_construct(),
            expected_run_id=decision.run_id,
            verification_time_utc=BASE_TIME,
            replay_registry=ReceiptReplayRegistry(registry_id=decision.replay_registry_id),
        )


def test_task9_receipt_cannot_substitute_cheh_or_disable_noop() -> None:
    policy, manifest, _, signers, custody_signers = _trust_context()
    del policy
    _, receipts = _build_receipts(manifest, signers, custody_signers)
    task9 = cast(Task9Receipt, receipts[ReceiptKind.TASK_9])
    payload = task9.model_dump(mode="python")
    payload["selected_method_identity"] = "CHEH"
    with pytest.raises(ValidationError):
        Task9Receipt.model_validate(payload)
    payload = task9.model_dump(mode="python")
    payload["authenticated_enabled_noop_allowed"] = False
    with pytest.raises(ValidationError):
        Task9Receipt.model_validate(payload)
    payload = task9.model_dump(mode="python")
    payload["protocol_id"] = "structure-two-task9-four-coupling-protocol@1.0"
    with pytest.raises(ValidationError):
        Task9Receipt.model_validate(payload)
    payload = task9.model_dump(mode="python")
    identities = list(payload["operator_identity_order"])
    identities[1] = "CHEH"
    payload["operator_identity_order"] = identities
    with pytest.raises(ValidationError):
        Task9Receipt.model_validate(payload)


def test_policy_json_is_valid_and_has_no_generic_gate_b_v07_dependency() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, sort_keys=True)
    assert "GATE_B_V0_8" in serialized
    assert "GATE_B_V0_7" not in serialized
    assert payload["current_authorization"] is False
