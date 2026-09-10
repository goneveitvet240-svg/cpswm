from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

import cpswm.system.evaluation_operations.structure_two_adaptive_compute_predeath as predeath
from cpswm.system.evaluation_operations.structure_two_adaptive_compute_predeath import (
    FULL_EAGER_PATH_ID,
    DebtResolutionReceipt,
    DebtStatus,
    EvidenceSplit,
    ForcedEscalationCause,
    ForcedEscalationStage,
    HardConstraintOutcome,
    InferenceDebtCertificate,
    LegalPathSpec,
    OperatorExecutionMode,
    OperatorInvocationReceipt,
    PathEligibilityOutcome,
    PreDeathDisposition,
    PreResolutionAction,
    QualityLossVector,
    ResourceVector,
    ShadowMatrixEvidence,
    ShadowRunRecord,
    _quantile,
    evaluate_hindsight_headroom,
    load_adaptive_compute_predeath_protocol,
    required_debt_replay_order,
    run_adaptive_compute_predeath_readiness,
    validate_shadow_matrix,
    verify_hindsight_headroom_report,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_production_system import PRODUCTION_OPERATOR_ORDER

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SYMBOL = "cpswm.system.structure_two_production_system.StructureTwoProductionSystem"


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


@pytest.fixture(scope="module")
def protocol():
    base = load_adaptive_compute_predeath_protocol(ROOT)
    statistical = base.statistical_policy.model_copy(
        update={
            "minimum_validation_households": 4,
            "minimum_confirmatory_households": 8,
            "familywise_alpha": 0.9,
            "bootstrap_resamples": 2000,
            "minimum_bootstrap_tail_draws": 20,
        }
    )
    population = base.population_binding.model_copy(
        update={
            "validation_household_ids": tuple(
                f"validation-household-{index:03d}" for index in range(4)
            ),
            "confirmatory_household_ids": tuple(
                f"confirmatory-household-{index:03d}" for index in range(8)
            ),
            "replicate_seeds": (104729, 130363),
        }
    )
    return base.model_copy(
        update={"statistical_policy": statistical, "population_binding": population}
    )


@pytest.fixture(scope="module")
def registered_alpha_protocol(protocol):
    statistical = protocol.statistical_policy.model_copy(
        update={
            "familywise_alpha": 0.05,
            "bootstrap_resamples": 40000,
            "minimum_bootstrap_tail_draws": 22,
        }
    )
    return protocol.model_copy(update={"statistical_policy": statistical})


def _debt(
    *, route_id: str, decision_id: str, checkpoint: str, deferred, replicate_seed: int
) -> InferenceDebtCertificate:
    state = _sha(f"state:{decision_id}:{replicate_seed}:{route_id}")
    return InferenceDebtCertificate(
        debt_schema_version="1.0.0",
        debt_id=f"debt:{decision_id}:{replicate_seed}:{route_id}",
        decision_id=decision_id,
        route_id=route_id,
        origin_checkpoint_sha256=checkpoint,
        created_at_step=0,
        deferred_operators=tuple(deferred),
        raw_evidence_content_hashes=(_sha(f"evidence:{decision_id}"),),
        operator_version_hashes={
            operator: _sha(f"version:{operator}") for operator in PRODUCTION_OPERATOR_ORDER
        },
        sufficient_state_snapshot_sha256=_sha(f"snapshot:{decision_id}"),
        unresolved_hypothesis_ids=(f"hypothesis:{decision_id}",),
        skipped_as_negative=False,
        decision_flip_upper_bound=0.1,
        decision_flip_bound_derivation_sha256=_sha(f"flip-bound:{decision_id}:{route_id}"),
        attribution_flip_upper_bound=0.1,
        attribution_flip_bound_derivation_sha256=_sha(
            f"attribution-flip-bound:{decision_id}:{route_id}"
        ),
        allowed_actions_before_resolution=("safe_read_only_query",),
        forbidden_memory_transitions_before_resolution=(
            "long_term_memory_write",
            "permanent_attribution_commit",
            "permanent_identity_commit",
            "irreversible_memory_retraction",
        ),
        observed_actions_before_resolution=(),
        observed_memory_transitions_before_resolution=(),
        escalation_triggers=(
            "late_contradictory_evidence",
            "before_long_term_commit",
            "risk_bound_exceeded",
            "debt_expiry",
        ),
        expiry_step=20,
        replay_operator_order=required_debt_replay_order(frozenset(deferred)),
        replay_scope_ids=(f"scope:{decision_id}",),
        status=DebtStatus.SETTLED,
        resolution=DebtResolutionReceipt(
            settled_at_step=10,
            replay_trace_sha256=_sha(f"replay:{decision_id}:{route_id}"),
            recovered_state_sha256=state,
            eager_reference_state_sha256=state,
            belief_tv=0.0,
            action_top1_agreement=1.0,
            consequential_action_exact_match=True,
            actor_identity_state_exact_match=True,
            commit_retract_state_exact_match=True,
            authority_state_exact_match=True,
            privacy_state_exact_match=True,
            utility_relative_delta=0.0,
            utility_absolute_delta=0.0,
        ),
    )


def _invocations(
    *,
    route,
    decision_id: str,
    replicate_seed: int,
    checkpoint: str,
    debt_certificates: tuple[InferenceDebtCertificate, ...],
    fallback_route=None,
    execute_selected_path: bool = True,
    selected_observation_acquired: bool = False,
    fallback_observation_acquired: bool = False,
) -> tuple[OperatorInvocationReceipt, ...]:
    signatures: list[tuple[object, OperatorExecutionMode, str, str, str | None]] = []

    def add_path(path, primary_phase: str, feedback_phase: str, *, include_feedback: bool) -> None:
        signatures.extend(
            (item.operator, item.mode, primary_phase, path.path_id, None)
            for item in path.operator_modes
            if item.mode
            not in {
                OperatorExecutionMode.DEFERRED_WITH_VALID_DEBT_CERTIFICATE,
                OperatorExecutionMode.NOT_APPLICABLE_WITH_RECOMPUTED_REASON,
            }
        )
        if include_feedback:
            signatures.extend(
                (
                    operator,
                    OperatorExecutionMode.REFINEMENT_EXECUTED,
                    feedback_phase,
                    path.path_id,
                    None,
                )
                for operator in path.feedback_closure_operator_order[1:]
            )

    if execute_selected_path:
        add_path(
            route,
            "SELECTED_PATH",
            "SELECTED_FEEDBACK_CLOSURE",
            include_feedback=selected_observation_acquired,
        )
    if fallback_route is not None:
        add_path(
            fallback_route,
            "FALLBACK_PATH",
            "FALLBACK_FEEDBACK_CLOSURE",
            include_feedback=fallback_observation_acquired,
        )
    signatures.extend(
        (
            operator,
            OperatorExecutionMode.REFINEMENT_EXECUTED,
            "DEBT_REPLAY",
            route.path_id,
            certificate.debt_id,
        )
        for certificate in debt_certificates
        for operator in certificate.replay_operator_order
    )
    receipts: list[OperatorInvocationReceipt] = []
    state = checkpoint
    for index, (operator, execution_mode, phase, path_id, debt_id) in enumerate(signatures):
        next_state = _sha(
            f"state:{decision_id}:{replicate_seed}:{route.path_id}:{index}:{operator}:{phase}"
        )
        receipts.append(
            OperatorInvocationReceipt(
                invocation_id=(
                    f"invocation:{decision_id}:{replicate_seed}:{route.path_id}:{index}"
                ),
                sequence_index=index,
                operator=operator,
                execution_mode=execution_mode,
                phase=phase,
                path_id=path_id,
                debt_id=debt_id,
                consumes_state_sha256=state,
                produces_state_sha256=next_state,
                receipt_sha256=_sha(
                    f"invocation-receipt:{decision_id}:{replicate_seed}:{route.path_id}:{index}"
                ),
            )
        )
        state = next_state
    return tuple(receipts)


def _loss_for(
    *,
    positive: bool,
    split: EvidenceSplit,
    context_index: int,
    route_id: str,
) -> float:
    if not positive:
        return 0.2 if route_id == "P0_SAFE_DEFERRED" else 0.4
    if route_id == "P0_SAFE_DEFERRED":
        return 0.4
    if route_id == "P1_EVENT_ACTOR_LOCAL":
        return 0.4 if split is EvidenceSplit.VALIDATION else (0.0 if context_index == 0 else 0.3)
    if route_id == "P2_REGIME_RECOVERY_LOCAL":
        return 0.4 if split is EvidenceSplit.VALIDATION else (0.3 if context_index == 0 else 0.0)
    return {
        "P3_ACTIVE_VERIFY": 0.55,
        "P4_EVENT_ACTOR_PLUS_REGIME": 0.6,
        "P5_FULL_EAGER": 0.65,
    }[route_id]


def _evidence(protocol, *, positive: bool) -> ShadowMatrixEvidence:
    records: list[ShadowRunRecord] = []
    split_households = {
        EvidenceSplit.VALIDATION: protocol.population_binding.validation_household_ids,
        EvidenceSplit.CONFIRMATORY: protocol.population_binding.confirmatory_household_ids,
    }
    for split, household_ids in split_households.items():
        contexts = (
            (household_index, household_id, context_index)
            for household_index, household_id in enumerate(household_ids)
            for context_index in range(2)
        )
        for household_index, household_id, context_index in contexts:
            trajectory_id = f"trajectory-{household_index:03d}-{context_index:02d}"
            decision_id = f"{split.value}-decision-{household_index:03d}-{context_index:02d}"
            checkpoint = _sha(f"checkpoint:{decision_id}")
            visible = _sha(f"visible:{decision_id}")
            weights = _sha("shared-model-weights")
            support = _sha(f"support:{decision_id}")
            feature_source = _sha(f"features:{decision_id}")
            route_features = {
                "actor_ambiguity": 0.5,
                "unknown_mass": 0.1,
                "pending_long_term_commit": 1.0,
            }
            for replicate_seed in protocol.population_binding.replicate_seeds:
                schedule = _sha(f"schedule:{decision_id}:{replicate_seed}")
                rng_algorithm = protocol.counterfactual_branching.exogenous_rng_algorithm
                rng_version = protocol.counterfactual_branching.exogenous_rng_version
                rng_initial_state = _sha(f"rng-state:{decision_id}:{replicate_seed}")
                rng_source = _sha("fixture-common-random-number-source")
                rng_binding = content_sha256(
                    {
                        "algorithm": rng_algorithm,
                        "version": rng_version,
                        "seed": replicate_seed,
                        "initial_state_sha256": rng_initial_state,
                        "source_sha256": rng_source,
                        "canonical_schedule_payload_sha256": schedule,
                    }
                )
                for route in protocol.legal_paths:
                    loss = _loss_for(
                        positive=positive,
                        split=split,
                        context_index=context_index,
                        route_id=route.path_id,
                    )
                    debt = (
                        (
                            _debt(
                                route_id=route.path_id,
                                decision_id=decision_id,
                                checkpoint=checkpoint,
                                deferred=route.deferred_operators,
                                replicate_seed=replicate_seed,
                            ),
                        )
                        if route.deferred_operators
                        else ()
                    )
                    selected_observation = bool(route.feedback_closure_operator_order)
                    physical_verification = selected_observation
                    invocations = _invocations(
                        route=route,
                        decision_id=decision_id,
                        replicate_seed=replicate_seed,
                        checkpoint=checkpoint,
                        debt_certificates=debt,
                        selected_observation_acquired=selected_observation,
                    )
                    feedback_receipts = [
                        receipt.model_dump(mode="json")
                        for receipt in invocations
                        if "FEEDBACK_CLOSURE" in receipt.phase
                    ]
                    records.append(
                        ShadowRunRecord(
                            split=split,
                            household_id=household_id,
                            replicate_seed=replicate_seed,
                            trajectory_id=trajectory_id,
                            decision_id=decision_id,
                            route_id=route.path_id,
                            predecision_checkpoint_sha256=checkpoint,
                            robot_visible_input_sha256=visible,
                            model_weights_sha256=weights,
                            candidate_support_sha256=support,
                            exogenous_event_schedule_sha256=schedule,
                            exogenous_rng_algorithm=rng_algorithm,
                            exogenous_rng_version=rng_version,
                            exogenous_rng_seed=replicate_seed,
                            exogenous_rng_initial_state_sha256=rng_initial_state,
                            exogenous_rng_source_sha256=rng_source,
                            exogenous_rng_binding_sha256=rng_binding,
                            route_feature_source_sha256=feature_source,
                            route_features=route_features,
                            truth_read_before_route_selection=False,
                            future_feedback_read_before_route_selection=False,
                            other_path_output_read_before_route_selection=False,
                            runtime_execution_id=(
                                f"runtime:{decision_id}:{replicate_seed}:{route.path_id}"
                            ),
                            runtime_symbol=RUNTIME_SYMBOL,
                            runtime_binding_evidence_sha256=_sha(
                                f"runtime-binding:{decision_id}:{replicate_seed}:{route.path_id}"
                            ),
                            path_eligibility=PathEligibilityOutcome(
                                policy_id=("structure-two-path-eligibility@0.1-development"),
                                eligibility_evidence_sha256=_sha(
                                    f"eligibility:{decision_id}:{replicate_seed}:{route.path_id}"
                                ),
                                preconditions_satisfied=True,
                                forced_escalation_triggered=False,
                                forced_escalation_honored=False,
                                escalation_target_path_id=None,
                                escalation_cause=None,
                                escalation_stage=None,
                                long_term_write_requested=False,
                                rgrc_write_authorized=False,
                            ),
                            operator_receipt_sha256={
                                operator: _sha(
                                    f"receipt:{decision_id}:{replicate_seed}:{route.path_id}:{operator}"
                                )
                                for operator in PRODUCTION_OPERATOR_ORDER
                            },
                            operator_invocation_receipts=invocations,
                            losses=QualityLossVector(
                                task_loss=loss,
                                memory_loss=loss,
                                recovery_loss=loss,
                            ),
                            costs=ResourceVector(
                                online_compute_ratio=0.4,
                                latency_ratio=0.4,
                                energy_ratio=0.4,
                                peak_memory_ratio=0.4,
                                persistent_storage_ratio=0.4,
                                replay_compute_ratio=0.4,
                                embodied_sensing_ratio=0.4,
                                router_overhead_ratio=0.05,
                            ),
                            hard_constraints=HardConstraintOutcome(
                                safety_violations=0,
                                unauthorized_long_term_commits=0,
                                provenance_violations=0,
                                unresolved_as_negative_events=0,
                                discarded_required_evidence_events=0,
                                unauthorized_identity_disclosures=0,
                                unauthorized_person_data_egress_events=0,
                                pending_debt_at_horizon=0,
                            ),
                            debt_certificates=debt,
                            fallback_used=False,
                            executed_path_sequence=(route.path_id,),
                            branch_timed_out=False,
                            branch_failed=False,
                            failure_or_timeout_receipt_sha256=None,
                            failure_or_timeout_cost_charged=False,
                            fallback_path_timed_out=False,
                            fallback_path_failed=False,
                            fallback_failure_or_timeout_receipt_sha256=None,
                            fallback_failure_or_timeout_cost_charged=False,
                            safe_abstention_executed=False,
                            safe_abstention_receipt_sha256=None,
                            selected_path_observation_acquired=selected_observation,
                            fallback_path_observation_acquired=False,
                            physical_verification_executed=physical_verification,
                            feedback_closure_receipt_sha256=(
                                content_sha256({"operator_invocation_receipts": feedback_receipts})
                                if physical_verification
                                else None
                            ),
                            late_correction_present=split is EvidenceSplit.CONFIRMATORY,
                            late_correction_step=(
                                5 if split is EvidenceSplit.CONFIRMATORY else None
                            ),
                            horizon_end_step=20,
                            horizon_complete=True,
                        )
                    )
    return ShadowMatrixEvidence(
        schema_version="1.0.0",
        protocol_id=protocol.protocol_id,
        protocol_content_sha256=content_sha256(protocol.model_dump(mode="json")),
        evidence_level=protocol.evidence_level,
        executor_source_sha256=_sha("executor"),
        resource_accountant_source_sha256=_sha("accountant"),
        long_horizon_loss_contract_sha256=_sha("loss-contract"),
        records=tuple(records),
    )


def _replace_record(
    evidence: ShadowMatrixEvidence, index: int, replacement
) -> ShadowMatrixEvidence:
    records = list(evidence.records)
    records[index] = replacement
    return evidence.model_copy(update={"records": tuple(records)})


def test_frozen_protocol_retains_seven_operators_in_every_legal_path(protocol) -> None:
    assert (
        tuple(operator.value for operator in protocol.operator_order) == PRODUCTION_OPERATOR_ORDER
    )
    assert tuple(protocol.path_by_id) == (
        "P0_SAFE_DEFERRED",
        "P1_EVENT_ACTOR_LOCAL",
        "P2_REGIME_RECOVERY_LOCAL",
        "P3_ACTIVE_VERIFY",
        "P4_EVENT_ACTOR_PLUS_REGIME",
        "P5_FULL_EAGER",
    )
    assert all(
        tuple(item.operator.value for item in path.operator_modes) == PRODUCTION_OPERATOR_ORDER
        for path in protocol.legal_paths
    )
    assert not protocol.path_by_id[FULL_EAGER_PATH_ID].deferred_operators


def test_legal_path_cannot_drop_an_operator(protocol) -> None:
    payload = protocol.legal_paths[0].model_dump(mode="json")
    payload["operator_modes"] = payload["operator_modes"][:-1]
    with pytest.raises(ValidationError, match="exact production seven-operator order"):
        LegalPathSpec.model_validate(payload)


def test_non_full_path_operator_modes_cannot_drift(protocol) -> None:
    payload = protocol.model_dump(mode="json")
    payload["legal_paths"][0]["operator_modes"][1]["mode"] = "not_applicable_with_recomputed_reason"
    with pytest.raises(ValidationError, match="operator modes drifted"):
        type(protocol).model_validate(payload)


def test_privacy_escalation_cannot_be_redirected_to_full_eager(protocol) -> None:
    payload = protocol.model_dump(mode="json")
    payload["legal_paths"][1]["forced_escalation_target_by_condition"][
        "privacy_policy_violation"
    ] = FULL_EAGER_PATH_ID
    with pytest.raises(ValidationError, match="target mapping is not fail closed"):
        type(protocol).model_validate(payload)


def test_shadow_matrix_rejects_missing_debt_for_deferred_work(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    record = evidence.records[0].model_copy(update={"debt_certificates": ()})
    forged = _replace_record(evidence, 0, record)
    with pytest.raises(ValueError, match="exactly covered by inference debt"):
        validate_shadow_matrix(forged, protocol)


def test_shadow_matrix_rejects_debt_on_full_eager_path(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    index = next(
        index
        for index, record in enumerate(evidence.records)
        if record.route_id == FULL_EAGER_PATH_ID
    )
    base = evidence.records[index]
    forged_debt = _debt(
        route_id=base.route_id,
        decision_id=base.decision_id,
        checkpoint=base.predecision_checkpoint_sha256,
        deferred=(protocol.operator_order[0],),
        replicate_seed=base.replicate_seed,
    )
    forged = _replace_record(
        evidence,
        index,
        base.model_copy(update={"debt_certificates": (forged_debt,)}),
    )
    with pytest.raises(ValueError, match="exactly covered by inference debt"):
        validate_shadow_matrix(forged, protocol)


def test_shadow_matrix_rejects_cross_branch_checkpoint_drift(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    different_checkpoint = _sha("different-checkpoint")
    invocations = list(evidence.records[1].operator_invocation_receipts)
    invocations[0] = invocations[0].model_copy(
        update={"consumes_state_sha256": different_checkpoint}
    )
    record = evidence.records[1].model_copy(
        update={
            "predecision_checkpoint_sha256": different_checkpoint,
            "operator_invocation_receipts": tuple(invocations),
        }
    )
    forged = _replace_record(evidence, 1, record)
    with pytest.raises(ValueError, match="predecision_checkpoint_sha256"):
        validate_shadow_matrix(forged, protocol)


def test_shadow_matrix_rejects_path_output_or_truth_proxy_feature(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    record = evidence.records[0].model_copy(update={"route_features": {"full_path_posterior": 0.9}})
    forged = _replace_record(evidence, 0, record)
    with pytest.raises(ValueError, match="forbidden or unregistered route feature"):
        validate_shadow_matrix(forged, protocol)


def test_physical_verification_requires_a_registered_feedback_closure(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    base = evidence.records[0]
    record = base.model_copy(
        update={
            "physical_verification_executed": True,
            "feedback_closure_receipt_sha256": _sha("forged-feedback-closure"),
        }
    )
    with pytest.raises(ValueError, match="physical verification must equal"):
        validate_shadow_matrix(_replace_record(evidence, 0, record), protocol)


def test_best_fixed_selection_uses_validation_not_confirmatory(protocol) -> None:
    report = evaluate_hindsight_headroom(_evidence(protocol, positive=True), protocol)
    evaluated = [item for item in report["comparisons"] if item["status"] == "EVALUATED"]
    assert evaluated
    assert all(
        item["validation_selected_best_fixed_path"] == "P0_SAFE_DEFERRED" for item in evaluated
    )


def test_gate1_does_not_unfairly_charge_best_fixed_router_overhead(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    records = tuple(
        record.model_copy(
            update={"costs": record.costs.model_copy(update={"router_overhead_ratio": 9.0})}
        )
        for record in evidence.records
    )
    report = evaluate_hindsight_headroom(
        evidence.model_copy(update={"records": records}),
        protocol,
    )
    assert any(item["status"] == "EVALUATED" for item in report["comparisons"])
    assert report["gate1_router_overhead_accounting"] == {
        "hindsight_oracle_router_overhead_ratio": 0.0,
        "best_fixed_router_overhead_ratio": 0.0,
        "observable_gate_must_charge_recorded_router_overhead": True,
    }


def test_caller_controlled_headroom_is_only_a_diagnostic_candidate(
    registered_alpha_protocol,
) -> None:
    protocol = registered_alpha_protocol
    report = evaluate_hindsight_headroom(_evidence(protocol, positive=True), protocol)
    assert report["disposition"] == (
        PreDeathDisposition.CALLER_CONTROLLED_HEADROOM_CANDIDATE_REQUIRES_SOURCE_BINDING
    )
    assert report["caller_controlled_hindsight_headroom_candidate"] is True
    assert report["source_bound_hindsight_headroom_established"] is False
    assert report["hindsight_headroom_present"] is False
    assert report["hindsight_headroom_claim_authorized"] is False
    assert report["observable_policy_gate_candidate"] is False
    assert report["observable_policy_training_authorized"] is False
    assert report["multiplicity_family_size"] == 90
    assert report["multiplicity_adjusted_one_sided_alpha"] == pytest.approx(0.05 / 90)
    assert report["bootstrap_tail_draw_count"] == 22
    positive = [
        item
        for item in report["comparisons"]
        if item.get("caller_controlled_positive_headroom_candidate")
    ]
    assert positive
    assert all(
        set(item["qualifying_distinct_winning_paths"])
        == {"P1_EVENT_ACTOR_LOCAL", "P2_REGIME_RECOVERY_LOCAL"}
        for item in positive
    )


def test_caller_controlled_no_gain_cannot_kill_adaptive_routing(protocol) -> None:
    report = evaluate_hindsight_headroom(_evidence(protocol, positive=False), protocol)
    assert report["disposition"] == (
        PreDeathDisposition.CALLER_CONTROLLED_NO_HEADROOM_CANDIDATE_REQUIRES_SOURCE_BINDING
    )
    assert report["hindsight_headroom_present"] is False
    assert report["adaptive_routing_kill_authorized"] is False
    assert report["seven_operator_scope_retained"] is True
    assert report["seven_operator_ablation_authorized"] is False


def test_hard_guardrail_failure_cannot_be_offset_by_oracle_gain(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    hard = evidence.records[0].hard_constraints.model_copy(update={"safety_violations": 1})
    record = evidence.records[0].model_copy(update={"hard_constraints": hard})
    report = evaluate_hindsight_headroom(_replace_record(evidence, 0, record), protocol)
    assert report["disposition"] == PreDeathDisposition.INVALID_NO_SCIENTIFIC_CONCLUSION
    assert report["hindsight_headroom_present"] is False
    assert report["hard_guardrail_violations"][0]["reasons"] == ["safety_violation"]


def test_completed_horizon_rejects_pending_inference_debt(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    base = evidence.records[0]
    pending = base.debt_certificates[0].model_copy(
        update={"status": DebtStatus.PENDING, "resolution": None}
    )
    record = base.model_copy(update={"debt_certificates": (pending,)})
    with pytest.raises(ValueError, match="cannot end with pending debt"):
        validate_shadow_matrix(_replace_record(evidence, 0, record), protocol)


def test_rewritten_hindsight_report_fails_fresh_evidence_verification(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    report = evaluate_hindsight_headroom(evidence, protocol)
    forged = copy.deepcopy(report)
    forged["scientific_superiority_established"] = True
    with pytest.raises(ValueError, match="content hash mismatch"):
        verify_hindsight_headroom_report(forged, evidence=evidence, protocol=protocol)


def test_self_consistent_rehash_cannot_promote_hindsight_report(protocol) -> None:
    evidence = _evidence(protocol, positive=False)
    report = evaluate_hindsight_headroom(evidence, protocol)
    forged = copy.deepcopy(report)
    forged["disposition"] = PreDeathDisposition.HINDSIGHT_HEADROOM_PRESENT_OBSERVABLE_GATE_REQUIRED
    forged["hindsight_headroom_present"] = True
    forged.pop("content_sha256")
    forged["content_sha256"] = content_sha256(forged)
    with pytest.raises(ValueError, match="differs from fresh evaluation"):
        verify_hindsight_headroom_report(forged, evidence=evidence, protocol=protocol)


def test_model_copy_cannot_bypass_literal_leakage_guard(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    leaked = evidence.records[0].model_copy(update={"truth_read_before_route_selection": True})
    with pytest.raises(ValidationError, match="truth_read_before_route_selection"):
        evaluate_hindsight_headroom(_replace_record(evidence, 0, leaked), protocol)


def test_protocol_content_substitution_is_rejected(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    budgets = list(protocol.resource_budget_points)
    budgets[0] = budgets[0].model_copy(update={"online_compute_ratio": 9.0})
    substituted = protocol.model_copy(update={"resource_budget_points": tuple(budgets)})
    with pytest.raises(ValueError, match="protocol content"):
        validate_shadow_matrix(evidence, substituted)


def test_truncated_debt_feedback_replay_is_rejected(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    base = next(record for record in evidence.records if record.debt_certificates)
    debt = base.debt_certificates[0]
    truncated = debt.model_copy(update={"replay_operator_order": debt.replay_operator_order[:-1]})
    record = base.model_copy(update={"debt_certificates": (truncated,)})
    index = evidence.records.index(base)
    with pytest.raises(ValidationError, match="downstream/feedback closure"):
        validate_shadow_matrix(_replace_record(evidence, index, record), protocol)


def test_duplicate_runtime_execution_id_is_rejected_globally(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    duplicate = evidence.records[1].model_copy(
        update={"runtime_execution_id": evidence.records[0].runtime_execution_id}
    )
    with pytest.raises(ValueError, match="globally unique"):
        validate_shadow_matrix(_replace_record(evidence, 1, duplicate), protocol)


def test_each_context_must_cover_every_seed(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    target = evidence.records[0]
    records = tuple(
        record
        for record in evidence.records
        if not (
            record.split is target.split
            and record.household_id == target.household_id
            and record.trajectory_id == target.trajectory_id
            and record.decision_id == target.decision_id
            and record.replicate_seed == protocol.population_binding.replicate_seeds[1]
        )
    )
    with pytest.raises(ValueError, match="each branch-point context"):
        validate_shadow_matrix(evidence.model_copy(update={"records": records}), protocol)


def test_identical_realized_schedule_across_distinct_rng_seeds_is_allowed(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    target = evidence.records[0]
    replay_seed = protocol.population_binding.replicate_seeds[1]
    records = tuple(
        record.model_copy(
            update={
                "exogenous_event_schedule_sha256": target.exogenous_event_schedule_sha256,
                "exogenous_rng_binding_sha256": content_sha256(
                    {
                        "algorithm": record.exogenous_rng_algorithm,
                        "version": record.exogenous_rng_version,
                        "seed": record.exogenous_rng_seed,
                        "initial_state_sha256": (record.exogenous_rng_initial_state_sha256),
                        "source_sha256": record.exogenous_rng_source_sha256,
                        "canonical_schedule_payload_sha256": (
                            target.exogenous_event_schedule_sha256
                        ),
                    }
                ),
            }
        )
        if record.split is target.split
        and record.household_id == target.household_id
        and record.trajectory_id == target.trajectory_id
        and record.decision_id == target.decision_id
        and record.replicate_seed == replay_seed
        else record
        for record in evidence.records
    )
    validate_shadow_matrix(evidence.model_copy(update={"records": records}), protocol)


def test_exogenous_rng_seed_must_match_replicate_seed(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    record = evidence.records[0].model_copy(update={"exogenous_rng_seed": 999})
    with pytest.raises(ValidationError, match="RNG seed"):
        validate_shadow_matrix(_replace_record(evidence, 0, record), protocol)


def test_exogenous_rng_binding_hash_is_recomputed(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    record = evidence.records[0].model_copy(
        update={"exogenous_rng_binding_sha256": _sha("unbound-rng")}
    )
    with pytest.raises(ValidationError, match="RNG binding hash"):
        validate_shadow_matrix(_replace_record(evidence, 0, record), protocol)


def test_exogenous_rng_source_digest_is_global(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    base = evidence.records[0]
    changed_source = _sha("different-rng-source")
    records = tuple(
        record.model_copy(
            update={
                "exogenous_rng_source_sha256": changed_source,
                "exogenous_rng_binding_sha256": content_sha256(
                    {
                        "algorithm": record.exogenous_rng_algorithm,
                        "version": record.exogenous_rng_version,
                        "seed": record.exogenous_rng_seed,
                        "initial_state_sha256": (record.exogenous_rng_initial_state_sha256),
                        "source_sha256": changed_source,
                        "canonical_schedule_payload_sha256": (
                            record.exogenous_event_schedule_sha256
                        ),
                    }
                ),
            }
        )
        if record.split is base.split
        and record.household_id == base.household_id
        and record.trajectory_id == base.trajectory_id
        and record.decision_id == base.decision_id
        else record
        for record in evidence.records
    )
    with pytest.raises(ValueError, match="one frozen exogenous RNG source digest"):
        validate_shadow_matrix(evidence.model_copy(update={"records": records}), protocol)


def test_invocation_execution_mode_must_match_frozen_path(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    base = evidence.records[0]
    invocations = list(base.operator_invocation_receipts)
    invocations[0] = invocations[0].model_copy(
        update={"execution_mode": OperatorExecutionMode.REFINEMENT_EXECUTED}
    )
    record = base.model_copy(update={"operator_invocation_receipts": tuple(invocations)})
    with pytest.raises(ValueError, match="invocation trace differs"):
        validate_shadow_matrix(_replace_record(evidence, 0, record), protocol)


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("unauthorized_identity_disclosures", "unauthorized_identity_disclosure"),
        ("unauthorized_person_data_egress_events", "unauthorized_person_data_egress"),
    ),
)
def test_privacy_hard_failures_cannot_be_offset_by_gain(protocol, field, reason) -> None:
    evidence = _evidence(protocol, positive=True)
    hard = evidence.records[0].hard_constraints.model_copy(update={field: 1})
    record = evidence.records[0].model_copy(update={"hard_constraints": hard})
    report = evaluate_hindsight_headroom(_replace_record(evidence, 0, record), protocol)
    assert report["disposition"] == PreDeathDisposition.INVALID_NO_SCIENTIFIC_CONCLUSION
    assert reason in report["hard_guardrail_violations"][0]["reasons"]


@pytest.mark.parametrize(
    ("field", "reason"),
    (
        ("actor_identity_state_exact_match", "debt_recovery_actor_identity_state_mismatch"),
        ("commit_retract_state_exact_match", "debt_recovery_commit_retract_state_mismatch"),
        ("privacy_state_exact_match", "debt_recovery_privacy_state_mismatch"),
    ),
)
def test_recovery_state_mismatch_cannot_be_offset_by_gain(protocol, field, reason) -> None:
    evidence = _evidence(protocol, positive=True)
    base = next(record for record in evidence.records if record.debt_certificates)
    debt = base.debt_certificates[0]
    resolution = debt.resolution.model_copy(update={field: False})
    changed_debt = debt.model_copy(update={"resolution": resolution})
    record = base.model_copy(update={"debt_certificates": (changed_debt,)})
    report = evaluate_hindsight_headroom(
        _replace_record(evidence, evidence.records.index(base), record), protocol
    )
    assert report["disposition"] == PreDeathDisposition.INVALID_NO_SCIENTIFIC_CONCLUSION
    assert reason in report["hard_guardrail_violations"][0]["reasons"]


def test_positive_flip_risk_cannot_allow_permanent_write(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    base = next(record for record in evidence.records if record.debt_certificates)
    debt = base.debt_certificates[0].model_copy(
        update={"allowed_actions_before_resolution": (PreResolutionAction.LONG_TERM_MEMORY_WRITE,)}
    )
    record = base.model_copy(update={"debt_certificates": (debt,)})
    with pytest.raises(ValidationError, match="blocked permanent transition"):
        validate_shadow_matrix(
            _replace_record(evidence, evidence.records.index(base), record), protocol
        )


def test_unknown_pre_resolution_memory_transition_is_rejected(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    base = next(record for record in evidence.records if record.debt_certificates)
    debt = base.debt_certificates[0].model_copy(
        update={"observed_memory_transitions_before_resolution": ("permanent_identity_commit_v2",)}
    )
    record = base.model_copy(update={"debt_certificates": (debt,)})
    with pytest.raises(ValidationError, match="observed_memory_transitions_before_resolution"):
        validate_shadow_matrix(
            _replace_record(evidence, evidence.records.index(base), record), protocol
        )


def test_debt_settled_before_late_correction_is_invalid(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    base = next(
        record
        for record in evidence.records
        if record.split is EvidenceSplit.CONFIRMATORY and record.debt_certificates
    )
    debt = base.debt_certificates[0]
    resolution = debt.resolution.model_copy(update={"settled_at_step": 4})
    changed_debt = debt.model_copy(update={"resolution": resolution})
    record = base.model_copy(update={"debt_certificates": (changed_debt,)})
    report = evaluate_hindsight_headroom(
        _replace_record(evidence, evidence.records.index(base), record), protocol
    )
    assert report["disposition"] == PreDeathDisposition.INVALID_NO_SCIENTIFIC_CONCLUSION
    assert (
        "debt_settled_before_late_correction" in report["hard_guardrail_violations"][0]["reasons"]
    )


def test_fallback_without_charged_failure_cost_is_rejected(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    base = evidence.records[0]
    record = base.model_copy(
        update={
            "fallback_used": True,
            "executed_path_sequence": (base.route_id, FULL_EAGER_PATH_ID),
            "branch_failed": True,
            "failure_or_timeout_receipt_sha256": _sha("failure"),
            "failure_or_timeout_cost_charged": False,
        }
    )
    with pytest.raises(ValidationError, match="must charge"):
        validate_shadow_matrix(_replace_record(evidence, 0, record), protocol)


def test_full_eager_failure_requires_safe_abstention_receipt(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    index = next(
        index
        for index, record in enumerate(evidence.records)
        if record.route_id == FULL_EAGER_PATH_ID
    )
    base = evidence.records[index]
    record = base.model_copy(
        update={
            "fallback_used": True,
            "executed_path_sequence": (FULL_EAGER_PATH_ID, "SAFE_ABSTAIN"),
            "branch_failed": True,
            "failure_or_timeout_receipt_sha256": _sha("full-eager-failure"),
            "failure_or_timeout_cost_charged": True,
        }
    )
    with pytest.raises(ValueError, match="must execute safe abstention"):
        validate_shadow_matrix(_replace_record(evidence, index, record), protocol)


def test_nested_full_eager_failure_can_terminate_in_safe_abstention(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    index = next(
        index
        for index, record in enumerate(evidence.records)
        if record.route_id == "P1_EVENT_ACTOR_LOCAL"
    )
    base = evidence.records[index]
    route = protocol.path_by_id[base.route_id]
    fallback_route = protocol.path_by_id[FULL_EAGER_PATH_ID]
    invocations = _invocations(
        route=route,
        fallback_route=fallback_route,
        decision_id=base.decision_id,
        replicate_seed=base.replicate_seed,
        checkpoint=base.predecision_checkpoint_sha256,
        debt_certificates=base.debt_certificates,
    )
    record = base.model_copy(
        update={
            "operator_invocation_receipts": invocations,
            "fallback_used": True,
            "executed_path_sequence": (
                base.route_id,
                FULL_EAGER_PATH_ID,
                "SAFE_ABSTAIN",
            ),
            "branch_failed": True,
            "failure_or_timeout_receipt_sha256": _sha("selected-path-failure"),
            "failure_or_timeout_cost_charged": True,
            "fallback_path_failed": True,
            "fallback_failure_or_timeout_receipt_sha256": _sha("fallback-path-failure"),
            "fallback_failure_or_timeout_cost_charged": True,
            "safe_abstention_executed": True,
            "safe_abstention_receipt_sha256": _sha("safe-abstention"),
        }
    )
    validated = validate_shadow_matrix(_replace_record(evidence, index, record), protocol)
    assert validated


def test_cross_fit_rejects_seed_specific_winner_noise(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    first_seed = protocol.population_binding.replicate_seeds[0]
    records: list[ShadowRunRecord] = []
    for record in evidence.records:
        if record.split is not EvidenceSplit.CONFIRMATORY:
            records.append(record)
            continue
        if record.route_id == "P0_SAFE_DEFERRED":
            loss = 0.4
        elif record.route_id == "P1_EVENT_ACTOR_LOCAL":
            loss = 0.0 if record.replicate_seed == first_seed else 0.8
        elif record.route_id == "P2_REGIME_RECOVERY_LOCAL":
            loss = 0.8 if record.replicate_seed == first_seed else 0.0
        else:
            loss = 0.6
        records.append(
            record.model_copy(
                update={
                    "losses": QualityLossVector(
                        task_loss=loss,
                        memory_loss=loss,
                        recovery_loss=loss,
                    )
                }
            )
        )
    report = evaluate_hindsight_headroom(
        evidence.model_copy(update={"records": tuple(records)}), protocol
    )
    assert report["confirmatory_oracle_estimator"] == ("LEAVE_ONE_REPLICATE_SEED_OUT_CROSS_FIT")
    assert report["caller_controlled_hindsight_headroom_candidate"] is False


def test_forced_fallback_low_loss_is_not_attributed_to_original_route(protocol) -> None:
    evidence = _evidence(protocol, positive=False)
    route = protocol.path_by_id["P1_EVENT_ACTOR_LOCAL"]
    fallback_route = protocol.path_by_id[FULL_EAGER_PATH_ID]
    records: list[ShadowRunRecord] = []
    for record in evidence.records:
        if record.split is not EvidenceSplit.CONFIRMATORY or record.route_id != route.path_id:
            records.append(record)
            continue
        eligibility = record.path_eligibility.model_copy(
            update={
                "preconditions_satisfied": False,
                "forced_escalation_triggered": True,
                "forced_escalation_honored": True,
                "escalation_target_path_id": FULL_EAGER_PATH_ID,
                "escalation_cause": ForcedEscalationCause.INVALID_ROUTER_INPUT,
                "escalation_stage": ForcedEscalationStage.PRE_ROUTE,
            }
        )
        invocations = _invocations(
            route=route,
            fallback_route=fallback_route,
            execute_selected_path=False,
            decision_id=record.decision_id,
            replicate_seed=record.replicate_seed,
            checkpoint=record.predecision_checkpoint_sha256,
            debt_certificates=(),
        )
        records.append(
            record.model_copy(
                update={
                    "path_eligibility": eligibility,
                    "operator_invocation_receipts": invocations,
                    "debt_certificates": (),
                    "losses": QualityLossVector(
                        task_loss=0.0,
                        memory_loss=0.0,
                        recovery_loss=0.0,
                    ),
                    "fallback_used": True,
                    "executed_path_sequence": (route.path_id, FULL_EAGER_PATH_ID),
                    "failure_or_timeout_cost_charged": True,
                }
            )
        )
    report = evaluate_hindsight_headroom(
        evidence.model_copy(update={"records": tuple(records)}), protocol
    )
    assert report["caller_controlled_hindsight_headroom_candidate"] is False


def test_privacy_precondition_failure_abstains_without_path_invocations(protocol) -> None:
    evidence = _evidence(protocol, positive=False)
    records: list[ShadowRunRecord] = []
    for record in evidence.records:
        if record.split is not EvidenceSplit.CONFIRMATORY or record.route_id != (
            "P1_EVENT_ACTOR_LOCAL"
        ):
            records.append(record)
            continue
        eligibility = record.path_eligibility.model_copy(
            update={
                "preconditions_satisfied": False,
                "forced_escalation_triggered": True,
                "forced_escalation_honored": True,
                "escalation_target_path_id": "SAFE_ABSTAIN",
                "escalation_cause": ForcedEscalationCause.PRIVACY_POLICY_VIOLATION,
                "escalation_stage": ForcedEscalationStage.PRE_ROUTE,
            }
        )
        records.append(
            record.model_copy(
                update={
                    "path_eligibility": eligibility,
                    "operator_invocation_receipts": (),
                    "debt_certificates": (),
                    "fallback_used": True,
                    "executed_path_sequence": (record.route_id, "SAFE_ABSTAIN"),
                    "failure_or_timeout_cost_charged": True,
                    "safe_abstention_executed": True,
                    "safe_abstention_receipt_sha256": _sha(
                        f"privacy-abstain:{record.runtime_execution_id}"
                    ),
                    "losses": QualityLossVector(
                        task_loss=0.0,
                        memory_loss=0.0,
                        recovery_loss=0.0,
                    ),
                }
            )
        )
    report = evaluate_hindsight_headroom(
        evidence.model_copy(update={"records": tuple(records)}), protocol
    )
    assert report["caller_controlled_hindsight_headroom_candidate"] is False


def test_pre_route_escalation_rejects_selected_path_side_effects(protocol) -> None:
    evidence = _evidence(protocol, positive=False)
    base = next(
        record
        for record in evidence.records
        if record.split is EvidenceSplit.CONFIRMATORY and record.route_id == "P1_EVENT_ACTOR_LOCAL"
    )
    route = protocol.path_by_id[base.route_id]
    eligibility = base.path_eligibility.model_copy(
        update={
            "preconditions_satisfied": False,
            "forced_escalation_triggered": True,
            "forced_escalation_honored": True,
            "escalation_target_path_id": "SAFE_ABSTAIN",
            "escalation_cause": ForcedEscalationCause.PRIVACY_POLICY_VIOLATION,
            "escalation_stage": ForcedEscalationStage.PRE_ROUTE,
        }
    )
    unsafe_invocations = _invocations(
        route=route,
        decision_id=base.decision_id,
        replicate_seed=base.replicate_seed,
        checkpoint=base.predecision_checkpoint_sha256,
        debt_certificates=(),
    )
    forged = base.model_copy(
        update={
            "path_eligibility": eligibility,
            "operator_invocation_receipts": unsafe_invocations,
            "debt_certificates": (),
            "fallback_used": True,
            "executed_path_sequence": (route.path_id, "SAFE_ABSTAIN"),
            "failure_or_timeout_cost_charged": True,
            "safe_abstention_executed": True,
            "safe_abstention_receipt_sha256": _sha("privacy-safe-abstention"),
        }
    )
    with pytest.raises(ValueError, match="before every selected-path invocation"):
        validate_shadow_matrix(
            _replace_record(evidence, evidence.records.index(base), forged), protocol
        )


def test_empirical_quantile_uses_conservative_nearest_rank_at_integral_boundary() -> None:
    assert _quantile(tuple(float(value) for value in range(100)), 0.2) == 19.0


def test_every_confirmatory_context_requires_late_correction(protocol) -> None:
    evidence = _evidence(protocol, positive=True)
    target = next(
        record for record in evidence.records if record.split is EvidenceSplit.CONFIRMATORY
    )
    records = tuple(
        record.model_copy(update={"late_correction_present": False, "late_correction_step": None})
        if record.split is target.split
        and record.household_id == target.household_id
        and record.trajectory_id == target.trajectory_id
        and record.decision_id == target.decision_id
        else record
        for record in evidence.records
    )
    with pytest.raises(ValueError, match="every confirmatory branch-point"):
        validate_shadow_matrix(evidence.model_copy(update={"records": records}), protocol)


def test_no_evaluable_budget_cell_is_inconclusive_not_no_headroom(protocol) -> None:
    evidence = _evidence(protocol, positive=False)
    records = tuple(
        record.model_copy(
            update={"costs": record.costs.model_copy(update={"online_compute_ratio": 9.0})}
        )
        for record in evidence.records
    )
    report = evaluate_hindsight_headroom(evidence.model_copy(update={"records": records}), protocol)
    assert report["evaluated_comparison_count"] == 0
    assert report["disposition"] == PreDeathDisposition.INVALID_NO_SCIENTIFIC_CONCLUSION


@pytest.fixture(scope="module")
def current_readiness() -> dict[str, object]:
    return run_adaptive_compute_predeath_readiness(repository_root=ROOT)


def test_current_readiness_fails_closed_on_real_runtime_gap(current_readiness) -> None:
    gates = current_readiness["prerequisite_gates"]
    historical = current_readiness["retained_historical_diagnostics"]
    scope_audit = current_readiness["scope_audit"]
    assert scope_audit["complete_selected_scope_retained"] is True
    assert scope_audit["selected_method_operator_inventory_covers_production_registry"] is True
    assert scope_audit["protocol_operator_order_matches_production_dag"] is True
    assert "selected_method_operator_order_matches_production_dag" not in scope_audit
    assert gates["fresh_typed_action_utility_construct_gate_passed"] is True
    assert historical["fresh_historical_route_c_runtime_identity_gate_passed"] is False
    assert historical["used_as_current_shadow_readiness_blocker"] is False
    assert gates["population_seed_split_binding_matches_task9"] is True
    assert gates["production_execution_plan_interface_selected"] is True
    assert gates["immutable_execution_plan_contract_source_bound"] is True
    assert gates["trace_sink_contract_source_bound"] is True
    assert gates["legacy_no_plan_no_trace_call_shape_preserved"] is True
    assert gates["cross_system_trace_state_atomicity_established"] is False
    assert gates["path_specific_operator_budgets_bound"] is False
    assert gates["frozen_branch_point_manifest_bound"] is False
    assert gates["path_eligibility_policy_bound_to_production_state"] is False
    assert gates["debt_replay_verifier_bound_to_production_replay"] is False
    assert gates["power_analysis_bound_to_empirical_variance_and_icc"] is False
    assert gates["confirmatory_access_custody_bound"] is False
    assert gates["exogenous_rng_source_bound_to_production_execution"] is False
    assert gates["legal_path_executor_bound_to_production_runtime"] is False
    assert gates["p0_p5_consequential_runtime_identity_established"] is False
    assert gates["resource_accountant_bound_to_production_execution"] is False
    assert current_readiness["shadow_execution_authorized"] is False
    assert current_readiness["scientific_superiority_established"] is False
    assert (
        "historical_route_c_runtime_identity_gate_failed"
        not in current_readiness["blocking_reasons"]
    )
    assert (
        "p0_p5_consequential_runtime_identity_not_established"
        in current_readiness["blocking_reasons"]
    )
    assert (
        "production_execution_plan_interface_unresolved"
        not in current_readiness["blocking_reasons"]
    )
    assert (
        "exogenous_rng_source_not_bound_to_production_execution"
        in current_readiness["blocking_reasons"]
    )
    assert (
        "cross_system_trace_state_atomicity_not_established"
        in current_readiness["blocking_reasons"]
    )
    assert "production_router_feature_extractor_not_bound" in current_readiness["blocking_reasons"]
    assert (
        "legal_path_executor_not_bound_to_production_runtime"
        in current_readiness["blocking_reasons"]
    )
    assert "full_adaptive_resource_accounting_not_bound" in current_readiness["blocking_reasons"]
    assert (
        "selected_method_operator_order_differs_from_production_dag"
        not in current_readiness["blocking_reasons"]
    )
    assert len(current_readiness["blocking_reasons"]) == 12
    assert len(current_readiness["next_required_work"]) == 12
    local_runtime = current_readiness["local_adaptive_runtime_diagnostics"]
    assert local_runtime["transitively_immutable_six_plan_registry_bound"] is True
    assert local_runtime["production_router_feature_extractor_bound"] is False
    assert local_runtime["path_specific_compute_kernels_bound"] is False
    assert local_runtime["registered_failure_fallback_state_machine_bound"] is False
    assert local_runtime["executed_operator_wallclock_receipts_bound"] is True
    assert local_runtime["full_adaptive_resource_accounting_bound"] is False
    assert local_runtime["caller_context_snapshot_source_bound"] is True
    assert local_runtime["pending_debt_core_transition_barrier_source_bound"] is True
    assert local_runtime["pending_debt_all_wrapper_mutations_barrier_bound"] is False
    assert local_runtime["isolated_replay_entrypoint_source_bound"] is True
    assert local_runtime["different_location_detected_full_ciav_closure_source_bound"] is True
    assert local_runtime["same_location_detected_fast_verification_source_bound"] is True
    assert local_runtime["negative_observation_full_ciav_closure_source_bound"] is False
    assert local_runtime["full_ciav_outcome_closure_bound"] is False
    assert local_runtime["recovery_equivalence_established"] is False
    assert set(current_readiness["readiness_requirement_results"]) == {
        requirement.gate_key for requirement in predeath.READINESS_REQUIREMENTS
    }


def test_readiness_requirement_table_has_a_reachable_positive_control() -> None:
    all_current_requirements_pass = {
        requirement.gate_key: True for requirement in predeath.READINESS_REQUIREMENTS
    }

    ready, status, blockers, next_required_work = predeath._readiness_outcome(
        all_current_requirements_pass
    )

    assert ready is True
    assert status == "READY_FOR_D0_SHADOW_EXECUTION"
    assert blockers == []
    assert next_required_work == []
    assert all(
        "historical_route_c" not in requirement.gate_key
        and "historical_route_c" not in requirement.blocking_reason
        for requirement in predeath.READINESS_REQUIREMENTS
    )


def test_readiness_requirement_table_rejects_incomplete_gate_coverage() -> None:
    incomplete = {requirement.gate_key: True for requirement in predeath.READINESS_REQUIREMENTS[1:]}

    with pytest.raises(ValueError, match="readiness gate coverage mismatch"):
        predeath.evaluate_readiness_requirements(incomplete)


def test_historical_route_c_diagnostic_cannot_change_current_shadow_blockers(
    current_readiness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_blockers = current_readiness["blocking_reasons"]
    baseline_runtime = predeath.run_runtime_identity_gate_audit(repository_root=ROOT)
    promoted_runtime = dict(baseline_runtime)
    promoted_runtime["runtime_identity_gate_passed"] = True
    monkeypatch.setattr(
        predeath,
        "run_runtime_identity_gate_audit",
        lambda *, repository_root: promoted_runtime,
    )

    promoted_report = run_adaptive_compute_predeath_readiness(repository_root=ROOT)

    assert (
        promoted_report["retained_historical_diagnostics"][
            "fresh_historical_route_c_runtime_identity_gate_passed"
        ]
        is True
    )
    assert promoted_report["blocking_reasons"] == baseline_blockers
    assert promoted_report["shadow_execution_authorized"] is False


def test_architecture_a_source_bindings_cover_the_real_call_chain(current_readiness) -> None:
    source_bindings = current_readiness["source_bindings"]
    expected_paths = {
        "production_execution_contract": "src/cpswm/system/structure_two_execution.py",
        "production_system": "src/cpswm/system/structure_two_production_system.py",
        "prototype_spine": "src/cpswm/system/prototype_spine.py",
        "regime_loop": "src/cpswm/system/continual/project_one_regime_loop.py",
    }
    for key, expected_path in expected_paths.items():
        assert source_bindings[key]["path"] == expected_path
        assert (
            source_bindings[key]["sha256"]
            == hashlib.sha256((ROOT / expected_path).read_bytes()).hexdigest()
        )


@pytest.mark.parametrize(
    ("helper_name", "gate_name", "blocker"),
    (
        (
            "_architecture_a_interface_selection_is_declared",
            "production_execution_plan_interface_selected",
            "production_execution_plan_interface_unresolved",
        ),
        (
            "_immutable_execution_plan_contract_is_source_bound",
            "immutable_execution_plan_contract_source_bound",
            "immutable_execution_plan_contract_not_source_bound",
        ),
        (
            "_trace_sink_contract_is_source_bound",
            "trace_sink_contract_source_bound",
            "trace_sink_contract_not_source_bound",
        ),
        (
            "_legacy_no_plan_no_trace_call_shape_is_preserved",
            "legacy_no_plan_no_trace_call_shape_preserved",
            "legacy_no_plan_no_trace_call_shape_not_preserved",
        ),
    ),
)
def test_architecture_a_readiness_gates_fail_independently(
    monkeypatch,
    helper_name: str,
    gate_name: str,
    blocker: str,
) -> None:
    independent_gate_names = {
        "production_execution_plan_interface_selected",
        "immutable_execution_plan_contract_source_bound",
        "trace_sink_contract_source_bound",
        "legacy_no_plan_no_trace_call_shape_preserved",
    }
    monkeypatch.setattr(predeath, helper_name, lambda **_kwargs: False)

    report = run_adaptive_compute_predeath_readiness(repository_root=ROOT)
    gates = report["prerequisite_gates"]

    assert gates[gate_name] is False
    assert blocker in report["blocking_reasons"]
    for independent_gate_name in independent_gate_names - {gate_name}:
        assert gates[independent_gate_name] is True
