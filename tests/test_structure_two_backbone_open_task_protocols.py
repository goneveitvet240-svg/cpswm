from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cpswm.system.evaluation_operations.structure_two_backbone_open_task_protocols import (
    P5_ESTIMAND,
    P5_STAGES,
    TASK11_CLAIM_BOUNDARY,
    TASK11_ESTIMAND,
    TASK11_PROTOCOL_ID,
    TASK12_CLAIM_BOUNDARY,
    TASK12_ESTIMAND,
    TASK12_PROTOCOL_ID,
    TASK13_CLAIM_BOUNDARY,
    TASK13_ESTIMAND,
    TASK13_PROTOCOL_ID,
    AxisJumpDistance,
    BindingCandidateDiagnostic,
    BindingRunDisposition,
    DifferentiabilityStrategy,
    P5ArmGateOutcomes,
    P5ArmResult,
    P5Diagnosis,
    P5StageRecall,
    ParticleAxis,
    ProposalHeadroomArm,
    ProposalOperation,
    RejuvenationKernelCandidate,
    ResamplingAlgorithm,
    RuntimeBindingReceipt,
    RuntimeTaskId,
    StructureTwoBackboneOpenTaskProtocols,
    Task11ArmPolicy,
    Task11ArmResult,
    Task11GateOutcomes,
    Task11PolicySelection,
    Task11RunResult,
    Task12ArmResult,
    Task12GateOutcomes,
    Task12RunResult,
    Task13ArmResult,
    Task13GateOutcomes,
    Task13RunResult,
    TaskP5DiagnosticResult,
    build_p5_diagnostic_result,
    build_runtime_binding_receipt,
    derive_binding_resolution,
    deterministic_result_sha256,
    diagnose_binding_candidate,
    verify_binding_resolution,
    verify_p5_result,
    verify_runtime_binding_receipt,
    verify_task11_result,
    verify_task12_result,
    verify_task13_result,
)
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    StructureTwoSelectedMethod,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/project_two_experiments/structure_two_backbone_open_tasks_v0_1.json"
SELECTED_METHOD_CONFIG = (
    ROOT / "configs/project_two_experiments/structure_two_selected_method_v0_1.json"
)
SOURCE_BUNDLE_SHA256 = "f" * 64


def _protocols() -> StructureTwoBackboneOpenTaskProtocols:
    return StructureTwoBackboneOpenTaskProtocols.load(CONFIG)


def _runtime_spec(task_id: RuntimeTaskId):
    protocols = _protocols()
    return {
        RuntimeTaskId.TASK_11: protocols.task_11,
        RuntimeTaskId.TASK_12: protocols.task_12,
        RuntimeTaskId.TASK_13: protocols.task_13,
        RuntimeTaskId.PROPOSAL_P5: protocols.proposal_p5,
    }[task_id]


def _runtime_receipt(
    task_id: RuntimeTaskId,
    *,
    execution_id: str,
    producer_id: str,
) -> RuntimeBindingReceipt:
    protocols = _protocols()
    values = _runtime_spec(task_id).nuisance_bindings.model_dump(mode="json")
    traces = {
        name: content_sha256({"binding": name, "observed": value}) for name, value in values.items()
    }
    return build_runtime_binding_receipt(
        protocols,
        task_id=task_id,
        execution_id=execution_id,
        producer_id=producer_id,
        observed_runtime_values=values,
        runtime_trace_payload_sha256_by_binding=traces,
        source_bundle_sha256=SOURCE_BUNDLE_SHA256,
    )


def _task11_gates(**updates: bool) -> Task11GateOutcomes:
    values = {
        "finite_normalized_weights": True,
        "toy_distribution_frequency": True,
        "lineage_parent_recorded": True,
        "final_step_not_resampled": True,
        "unknown_unresolved_support_reported": True,
        "runtime_policy_trace_changes": True,
        "no_oracle_access": True,
    }
    values.update(updates)
    return Task11GateOutcomes(**values)


def _task11_arm_results(*, wall_clock_offset: float = 0.0) -> tuple[Task11ArmResult, ...]:
    protocols = _protocols()
    policies = [Task11ArmPolicy(algorithm=ResamplingAlgorithm.NONE)]
    for algorithm in protocols.task_11.algorithms:
        if algorithm is ResamplingAlgorithm.NONE:
            continue
        policies.extend(
            Task11ArmPolicy(algorithm=algorithm, ess_fraction=threshold)
            for threshold in protocols.task_11.validation_only_ess_thresholds
        )
    output = []
    for index, policy in enumerate(policies):
        primary = -0.30 if policy.arm_key == "systematic@ess=0.5" else 0.10 + index / 100
        output.append(
            Task11ArmResult(
                policy=policy,
                paired_action_loss_delta_per_elementary_evaluation=primary,
                ess_trajectory=(8.0, 7.0),
                resampling_event_indices=(() if policy.ess_fraction is None else (0,)),
                unique_parent_count=4,
                unique_root_ancestor_count=3,
                unknown_support_before=0.2,
                unknown_support_after=0.2,
                unresolved_mass_before=0.1,
                unresolved_mass_after=0.1,
                log_normalizer_bias=0.01,
                posterior_total_variation=0.02,
                action_posterior_distance=0.02,
                owner_contamination=0.01,
                elementary_evaluations=100,
                wall_clock_seconds=1.0 + wall_clock_offset,
                gates=_task11_gates(),
            )
        )
    return tuple(output)


def _task11_result(
    *, execution_id: str, producer_id: str, wall_clock_offset: float = 0.0
) -> Task11RunResult:
    protocols = _protocols()
    return Task11RunResult(
        schema_version="0.2.0",
        protocol_id=TASK11_PROTOCOL_ID,
        primary_estimand=TASK11_ESTIMAND,
        execution_id=execution_id,
        producer_id=producer_id,
        spec_content_sha256=content_sha256(protocols.task_11),
        config_content_sha256=protocols.content_sha256,
        source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        runtime_binding_receipt=_runtime_receipt(
            RuntimeTaskId.TASK_11,
            execution_id=execution_id,
            producer_id=producer_id,
        ),
        arm_results=_task11_arm_results(wall_clock_offset=wall_clock_offset),
        disposition=BindingRunDisposition.RAN_ELIGIBLE_SELECTION,
        selected_policy=Task11PolicySelection(
            algorithm=ResamplingAlgorithm.SYSTEMATIC,
            ess_fraction=0.5,
        ),
        authority="local_diagnostic_only_no_binding_resolution",
        formal_binding_resolved=False,
        seven_operator_ablation_authorized=False,
        claim_boundary=TASK11_CLAIM_BOUNDARY,
    )


def _task12_gates() -> Task12GateOutcomes:
    return Task12GateOutcomes(
        conditional_target_invariance=True,
        forward_reverse_proposal_densities=True,
        state_machine_reachability=True,
        outside_window_byte_equality=True,
        analytic_block_rebuilt=True,
        oracle_confined_to_evaluator=True,
        zero_and_full_accept_paths=True,
    )


def _task12_arm_results(*, wall_clock_offset: float = 0.0) -> tuple[Task12ArmResult, ...]:
    scores = {
        RejuvenationKernelCandidate.NONE: 0.10,
        RejuvenationKernelCandidate.SINGLE_SITE_TYPED_MH: 0.30,
        RejuvenationKernelCandidate.BLOCKED_TYPED_MH: 0.50,
        RejuvenationKernelCandidate.EXACT_CONDITIONAL_GIBBS_EVALUATOR_ONLY: 0.90,
    }
    output = []
    for kernel in RejuvenationKernelCandidate:
        proposals = 0 if kernel is RejuvenationKernelCandidate.NONE else 10
        accepts = 0 if proposals == 0 else 5
        output.append(
            Task12ArmResult(
                kernel=kernel,
                detailed_balance_error=1e-12,
                stationary_distribution_error=1e-10,
                proposal_count=proposals,
                acceptance_count=accepts,
                acceptance_rate=(accepts / proposals if proposals else 0.0),
                axis_jump_distance=AxisJumpDistance(h=1, r=1, i=1, c=1, z=1),
                autocorrelation=0.1,
                effective_sample_size_per_elementary_evaluation=scores[kernel],
                unique_ancestry=3,
                full_rerun_actor_marginal_distance=0.01,
                late_correction_recovery=0.8,
                owner_contamination=0.01,
                unresolved_mass=0.1,
                fallback_count=0,
                fallback_reasons=(),
                window_touched_indices=(() if proposals == 0 else (1,)),
                wall_clock_seconds=1.0 + wall_clock_offset,
                gates=_task12_gates(),
            )
        )
    return tuple(output)


def _task12_result(
    *, execution_id: str, producer_id: str, wall_clock_offset: float = 0.0
) -> Task12RunResult:
    protocols = _protocols()
    return Task12RunResult(
        schema_version="0.2.0",
        protocol_id=TASK12_PROTOCOL_ID,
        primary_estimand=TASK12_ESTIMAND,
        execution_id=execution_id,
        producer_id=producer_id,
        spec_content_sha256=content_sha256(protocols.task_12),
        config_content_sha256=protocols.content_sha256,
        source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        runtime_binding_receipt=_runtime_receipt(
            RuntimeTaskId.TASK_12,
            execution_id=execution_id,
            producer_id=producer_id,
        ),
        arm_results=_task12_arm_results(wall_clock_offset=wall_clock_offset),
        disposition=BindingRunDisposition.RAN_ELIGIBLE_SELECTION,
        selected_kernel=RejuvenationKernelCandidate.BLOCKED_TYPED_MH,
        authority="local_diagnostic_only_no_binding_resolution",
        formal_binding_resolved=False,
        seven_operator_ablation_authorized=False,
        claim_boundary=TASK12_CLAIM_BOUNDARY,
    )


def _task13_gates() -> Task13GateOutcomes:
    return Task13GateOutcomes(
        tiny_exact_gradient_check=True,
        finite_gradients=True,
        hard_constraints_preserved=True,
        inference_semantics_unchanged=True,
        sealed_holdout_unseen_during_selection=True,
        proposer_has_no_commit_authority=True,
        runtime_strategy_trace_changes=True,
    )


def _task13_arm_results(*, wall_clock_offset: float = 0.0) -> tuple[Task13ArmResult, ...]:
    primary = {
        DifferentiabilityStrategy.STOP_GRADIENT_SUPERVISED: -0.10,
        DifferentiabilityStrategy.SCORE_FUNCTION_UNBIASED: -0.30,
        DifferentiabilityStrategy.RELAXED_PATHWISE_BIASED: -0.20,
    }
    return tuple(
        Task13ArmResult(
            strategy=strategy,
            paired_action_loss_delta_per_training_compute=primary[strategy],
            finite_difference_gradient_error=0.01,
            exact_expectation_gradient_error=0.01,
            gradient_bias=0.01,
            gradient_variance=0.02,
            gradient_norm=1.0,
            nonfinite_gradient_count=0,
            hard_constraint_violations=0,
            unknown_support_retention=0.9,
            unresolved_mass_retention=0.9,
            inference_target_sha256_before="a" * 64,
            inference_target_sha256_after="a" * 64,
            learning_curve_per_training_compute=(1.0, 0.8),
            holdout_truth_compatible_proposal_recall=0.8,
            posterior_total_variation=0.02,
            action_loss=0.5,
            wall_clock_seconds=1.0 + wall_clock_offset,
            gates=_task13_gates(),
        )
        for strategy in DifferentiabilityStrategy
    )


def _task13_result(
    *, execution_id: str, producer_id: str, wall_clock_offset: float = 0.0
) -> Task13RunResult:
    protocols = _protocols()
    return Task13RunResult(
        schema_version="0.2.0",
        protocol_id=TASK13_PROTOCOL_ID,
        primary_estimand=TASK13_ESTIMAND,
        execution_id=execution_id,
        producer_id=producer_id,
        spec_content_sha256=content_sha256(protocols.task_13),
        config_content_sha256=protocols.content_sha256,
        source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        runtime_binding_receipt=_runtime_receipt(
            RuntimeTaskId.TASK_13,
            execution_id=execution_id,
            producer_id=producer_id,
        ),
        arm_results=_task13_arm_results(wall_clock_offset=wall_clock_offset),
        disposition=BindingRunDisposition.RAN_ELIGIBLE_SELECTION,
        selected_strategy=DifferentiabilityStrategy.SCORE_FUNCTION_UNBIASED,
        authority="local_diagnostic_only_no_binding_resolution",
        formal_binding_resolved=False,
        seven_operator_ablation_authorized=False,
        claim_boundary=TASK13_CLAIM_BOUNDARY,
    )


def _p5_gates() -> P5ArmGateOutcomes:
    return P5ArmGateOutcomes(
        same_visible_input=True,
        fixed_nuisance_bindings=True,
        stage_accounting_complete=True,
        oracle_access_role_enforced=True,
        truth_reads_logged=True,
    )


def _p5_arm_results(*, wall_clock_offset: float = 0.0) -> tuple[P5ArmResult, ...]:
    recalls = {
        ProposalHeadroomArm.BOOTSTRAP: (0.50, 0.45, 0.40, 0.35, 0.30),
        ProposalHeadroomArm.DETERMINISTIC_TYPED: (0.60, 0.55, 0.50, 0.45, 0.40),
        ProposalHeadroomArm.LOCAL_CONDITIONAL_ORACLE: (0.90, 0.85, 0.80, 0.75, 0.70),
        ProposalHeadroomArm.TRUTH_INCLUSION_ORACLE: (1.00, 0.95, 0.90, 0.85, 0.80),
    }
    action_losses = {
        ProposalHeadroomArm.BOOTSTRAP: 0.90,
        ProposalHeadroomArm.DETERMINISTIC_TYPED: 0.80,
        ProposalHeadroomArm.LOCAL_CONDITIONAL_ORACLE: 0.60,
        ProposalHeadroomArm.TRUTH_INCLUSION_ORACLE: 0.50,
    }
    output = []
    for arm in ProposalHeadroomArm:
        oracle = arm in {
            ProposalHeadroomArm.LOCAL_CONDITIONAL_ORACLE,
            ProposalHeadroomArm.TRUTH_INCLUSION_ORACLE,
        }
        output.append(
            P5ArmResult(
                arm=arm,
                stage_recall=tuple(
                    P5StageRecall(stage=stage, full_chain_truth_compatible_recall=value)
                    for stage, value in zip(P5_STAGES, recalls[arm], strict=True)
                ),
                posterior_mass_coverage=recalls[arm][-1],
                axis_recall={axis: recalls[arm][-1] for axis in ParticleAxis},
                operation_recall={operation: recalls[arm][-1] for operation in ProposalOperation},
                unknown_support_retention=0.9,
                unresolved_mass_retention=0.9,
                action_loss=action_losses[arm],
                elementary_evaluations=100,
                truth_read_count=(1 if oracle else 0),
                exact_enumeration_count=(1 if oracle else 0),
                oracle_used=oracle,
                wall_clock_seconds=1.0 + wall_clock_offset,
                gates=_p5_gates(),
            )
        )
    return tuple(output)


def _p5_result(
    *, execution_id: str, producer_id: str, wall_clock_offset: float = 0.0
) -> TaskP5DiagnosticResult:
    return build_p5_diagnostic_result(
        _protocols(),
        execution_id=execution_id,
        producer_id=producer_id,
        source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        runtime_binding_receipt=_runtime_receipt(
            RuntimeTaskId.PROPOSAL_P5,
            execution_id=execution_id,
            producer_id=producer_id,
        ),
        arm_results=_p5_arm_results(wall_clock_offset=wall_clock_offset),
    )


def test_config_freezes_four_independent_defined_not_run_specs() -> None:
    protocols = _protocols()
    tasks = (
        protocols.task_11,
        protocols.task_12,
        protocols.task_13,
        protocols.proposal_p5,
    )
    assert protocols.definition_status == "DEFINED_NOT_RUN"
    assert {task.definition_status for task in tasks} == {"DEFINED_NOT_RUN"}
    assert len({task.protocol_id for task in tasks}) == 4
    assert len({task.primary_estimand for task in tasks}) == 4
    assert len({task.claim_boundary for task in tasks}) == 4
    assert protocols.proposal_p5.forbidden_outputs[0] == "passed"
    assert protocols.seven_operator_ablation_authorized is False
    assert protocols.binding_resolution_authority.trust_anchor_status == "NOT_ENROLLED"
    assert (
        protocols.binding_resolution_authority.local_verifier_may_issue_formal_resolution is False
    )


def test_config_remains_bound_to_selected_method_receipt() -> None:
    protocols = _protocols()
    selected = StructureTwoSelectedMethod.load(SELECTED_METHOD_CONFIG)
    assert protocols.selected_method_id == selected.method_id
    assert protocols.selected_method_receipt_content_sha256 == selected.content_sha256


def test_config_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate-open-task-config.json"
    duplicate.write_text(
        '{"schema_version":"0.1.0","schema_version":"0.1.0"}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        StructureTwoBackboneOpenTaskProtocols.load(duplicate)


def test_frozen_selection_threshold_drift_is_rejected() -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["task_11"]["validation_only_ess_thresholds"] = [0.2, 0.5, 0.75]
    payload["proposal_p5"]["diagnosis_rule"]["recall_headroom_epsilon"] = 0.02
    with pytest.raises(ValidationError, match="frozen"):
        StructureTwoBackboneOpenTaskProtocols.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("seven_operator_ablation_authorized",), True),
        (("binding_resolution_authority", "trust_anchor_status"), "ENROLLED"),
        (
            (
                "binding_resolution_authority",
                "local_verifier_may_issue_formal_resolution",
            ),
            True,
        ),
    ],
)
def test_local_authority_promotion_attacks_fail_closed(
    path: tuple[str, ...], value: object
) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        StructureTwoBackboneOpenTaskProtocols.model_validate(payload)


@pytest.mark.parametrize("task_key", ["task_11", "task_12", "task_13", "proposal_p5"])
def test_status_promotion_attack_fails_closed(task_key: str) -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload[task_key]["definition_status"] = "PASSED"
    with pytest.raises(ValidationError, match="DEFINED_NOT_RUN"):
        StructureTwoBackboneOpenTaskProtocols.model_validate(payload)


def test_runtime_receipt_binds_values_spec_config_and_source() -> None:
    protocols = _protocols()
    receipt = _runtime_receipt(
        RuntimeTaskId.TASK_11,
        execution_id="run-a",
        producer_id="producer-a",
    )
    verify_runtime_binding_receipt(
        protocols,
        task_id=RuntimeTaskId.TASK_11,
        receipt=receipt,
        expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
    )

    forged = receipt.model_dump(mode="python")
    forged["spec_content_sha256"] = "e" * 64
    forged["config_content_sha256"] = "d" * 64
    forged["observations"][0]["configured_value"] = "attacker-value"
    forged["observations"][0]["observed_runtime_value"] = "attacker-value"
    forged_receipt = RuntimeBindingReceipt.model_validate(forged)
    with pytest.raises(ValueError, match="spec/config/source binding drift"):
        verify_runtime_binding_receipt(
            protocols,
            task_id=RuntimeTaskId.TASK_11,
            receipt=forged_receipt,
            expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        )


def test_runtime_receipt_rejects_missing_binding_and_observed_value_drift() -> None:
    protocols = _protocols()
    values = protocols.task_12.nuisance_bindings.model_dump(mode="json")
    traces = {name: "a" * 64 for name in values}
    missing = dict(values)
    missing.pop("training_schedule")
    with pytest.raises(ValueError, match="do not cover"):
        build_runtime_binding_receipt(
            protocols,
            task_id=RuntimeTaskId.TASK_12,
            execution_id="run",
            producer_id="producer",
            observed_runtime_values=missing,
            runtime_trace_payload_sha256_by_binding=traces,
            source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        )

    drifted = dict(values)
    drifted["proposal_kernel"] = "unused-attacker-kernel"
    with pytest.raises(ValidationError, match="differs from observed runtime"):
        build_runtime_binding_receipt(
            protocols,
            task_id=RuntimeTaskId.TASK_12,
            execution_id="run",
            producer_id="producer",
            observed_runtime_values=drifted,
            runtime_trace_payload_sha256_by_binding=traces,
            source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        )


def test_task11_full_matrix_recomputes_selection() -> None:
    reported = _task11_result(execution_id="run-a", producer_id="producer-a")
    recomputed = _task11_result(
        execution_id="run-b",
        producer_id="producer-b",
        wall_clock_offset=9.0,
    )
    selected = verify_task11_result(
        _protocols(),
        reported=reported,
        recomputed=recomputed,
        expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
    )
    assert selected == Task11PolicySelection(
        algorithm=ResamplingAlgorithm.SYSTEMATIC,
        ess_fraction=0.5,
    )
    assert deterministic_result_sha256(reported) == deterministic_result_sha256(recomputed)


def test_task11_missing_or_reordered_arm_is_rejected_by_schema() -> None:
    payload = _task11_result(execution_id="run-a", producer_id="producer-a").model_dump(
        mode="python"
    )
    payload["arm_results"] = payload["arm_results"][:-1]
    with pytest.raises(ValidationError, match="every preregistered arm"):
        Task11RunResult.model_validate(payload)

    payload = _task11_result(execution_id="run-a", producer_id="producer-a").model_dump(
        mode="python"
    )
    reordered = list(payload["arm_results"])
    reordered[1], reordered[2] = reordered[2], reordered[1]
    payload["arm_results"] = reordered
    with pytest.raises(ValidationError, match="every preregistered arm"):
        Task11RunResult.model_validate(payload)


def test_task11_caller_selected_nonoptimal_arm_is_rejected() -> None:
    valid = _task11_result(execution_id="run-a", producer_id="producer-a")
    payload = valid.model_dump(mode="python")
    payload["selected_policy"] = {"algorithm": "no_resampling", "ess_fraction": None}
    forged = Task11RunResult.model_validate(payload)
    recomputed_payload = _task11_result(execution_id="run-b", producer_id="producer-b").model_dump(
        mode="python"
    )
    recomputed_payload["selected_policy"] = {
        "algorithm": "no_resampling",
        "ess_fraction": None,
    }
    recomputed = Task11RunResult.model_validate(recomputed_payload)
    with pytest.raises(ValueError, match="not verifier-derived"):
        verify_task11_result(
            _protocols(),
            reported=forged,
            recomputed=recomputed,
            expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        )


def test_task12_and_task13_full_matrices_recompute_typed_choices() -> None:
    task12 = _task12_result(execution_id="t12-a", producer_id="producer-a")
    task12_recomputed = _task12_result(execution_id="t12-b", producer_id="producer-b")
    assert (
        verify_task12_result(
            _protocols(),
            reported=task12,
            recomputed=task12_recomputed,
            expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        )
        is RejuvenationKernelCandidate.BLOCKED_TYPED_MH
    )

    task13 = _task13_result(execution_id="t13-a", producer_id="producer-a")
    task13_recomputed = _task13_result(execution_id="t13-b", producer_id="producer-b")
    assert (
        verify_task13_result(
            _protocols(),
            reported=task13,
            recomputed=task13_recomputed,
            expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        )
        is DifferentiabilityStrategy.SCORE_FUNCTION_UNBIASED
    )


def test_task12_task7_impersonation_and_oracle_selection_fail_closed() -> None:
    config_payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    config_payload["task_12"]["candidate_kernels"][1] = "task_7_window_rejuvenation"
    with pytest.raises(ValidationError, match="candidate_kernels"):
        StructureTwoBackboneOpenTaskProtocols.model_validate(config_payload)

    result_payload = _task12_result(execution_id="run", producer_id="producer").model_dump(
        mode="python"
    )
    result_payload["selected_kernel"] = "exact_conditional_gibbs_evaluator_only"
    with pytest.raises(ValidationError, match="evaluator oracle"):
        Task12RunResult.model_validate(result_payload)


def test_task12_and_task13_missing_arm_fail_closed() -> None:
    task12 = _task12_result(execution_id="run", producer_id="producer").model_dump(mode="python")
    task12["arm_results"] = task12["arm_results"][:-1]
    with pytest.raises(ValidationError, match="every preregistered kernel"):
        Task12RunResult.model_validate(task12)

    task13 = _task13_result(execution_id="run", producer_id="producer").model_dump(mode="python")
    task13["arm_results"] = task13["arm_results"][:-1]
    with pytest.raises(ValidationError, match="every preregistered strategy"):
        Task13RunResult.model_validate(task13)


@pytest.mark.parametrize(
    "factory",
    [_task11_result, _task12_result, _task13_result],
)
def test_caller_pair_yields_diagnostic_but_never_resolution(factory) -> None:
    reported = factory(execution_id="run-a", producer_id="producer-a")
    recomputed = factory(execution_id="run-b", producer_id="producer-b")
    diagnostic = diagnose_binding_candidate(
        _protocols(),
        reported=reported,
        recomputed=recomputed,
        expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
    )
    assert diagnostic.evidence_status == "LOCAL_CALLER_PAIR_DIAGNOSTIC_ONLY"
    assert diagnostic.enrolled_independent_authority_verified is False
    assert diagnostic.custody_verified is False
    assert diagnostic.freshness_verified is False
    assert diagnostic.replay_registry_checked is False
    assert diagnostic.formal_binding_resolved is False
    assert diagnostic.seven_operator_ablation_authorized is False
    with pytest.raises(ValueError, match="cannot issue a formal binding resolution"):
        derive_binding_resolution(
            _protocols(),
            reported=reported,
            recomputed=recomputed,
            expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        )


def test_self_consistent_caller_diagnostic_cannot_be_promoted_to_resolution() -> None:
    reported = _task11_result(execution_id="run-a", producer_id="producer-a")
    recomputed = _task11_result(execution_id="run-b", producer_id="producer-b")
    legitimate = diagnose_binding_candidate(
        _protocols(),
        reported=reported,
        recomputed=recomputed,
        expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
    )
    forged = legitimate.model_dump(mode="python")
    forged["diagnostic_resampling_policy"] = {
        "algorithm": "no_resampling",
        "ess_fraction": None,
    }
    forged["reported_result_content_sha256"] = "e" * 64
    unsigned = {key: value for key, value in forged.items() if key != "diagnostic_sha256"}
    forged["diagnostic_sha256"] = content_sha256(unsigned)
    caller_constructed = BindingCandidateDiagnostic.model_validate(forged)

    with pytest.raises(ValueError, match="cannot accept a binding resolution receipt"):
        verify_binding_resolution(
            _protocols(),
            reported=reported,
            recomputed=recomputed,
            receipt=caller_constructed,
            expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        )


def test_forged_complete_result_pair_with_runtime_spec_drift_is_rejected() -> None:
    forged_results = []
    for execution_id, producer_id in (("run-a", "producer-a"), ("run-b", "producer-b")):
        result = _task11_result(
            execution_id=execution_id,
            producer_id=producer_id,
        ).model_dump(mode="python")
        runtime = result["runtime_binding_receipt"]
        runtime["spec_content_sha256"] = "e" * 64
        runtime["config_content_sha256"] = "d" * 64
        runtime["observations"][0]["configured_value"] = "attacker-value"
        runtime["observations"][0]["observed_runtime_value"] = "attacker-value"
        result["spec_content_sha256"] = "e" * 64
        result["config_content_sha256"] = "d" * 64
        forged_results.append(Task11RunResult.model_validate(result))

    with pytest.raises(ValueError, match="protocol/spec/config/source binding drift"):
        derive_binding_resolution(
            _protocols(),
            reported=forged_results[0],
            recomputed=forged_results[1],
            expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        )


def test_caller_pair_comparison_requires_distinct_claimed_labels() -> None:
    result = _task11_result(execution_id="same", producer_id="same-producer")
    with pytest.raises(ValueError, match="distinct claimed execution"):
        verify_task11_result(
            _protocols(),
            reported=result,
            recomputed=result,
            expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        )


def test_p5_recomputes_four_arm_stage_headroom_and_unique_diagnosis() -> None:
    reported = _p5_result(execution_id="p5-a", producer_id="producer-a")
    recomputed = _p5_result(
        execution_id="p5-b",
        producer_id="producer-b",
        wall_clock_offset=4.0,
    )
    assert reported.primary_estimand == P5_ESTIMAND
    assert reported.primary_estimand_value == pytest.approx(0.40)
    assert reported.oracle_action_gain == pytest.approx(0.30)
    assert reported.diagnosis is P5Diagnosis.PROPOSAL_BOTTLENECK
    assert tuple(item.arm for item in reported.arm_results) == tuple(ProposalHeadroomArm)
    assert (
        verify_p5_result(
            _protocols(),
            reported=reported,
            recomputed=recomputed,
            expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        )
        is P5Diagnosis.PROPOSAL_BOTTLENECK
    )


def test_p5_missing_cross_arm_and_per_arm_output_attacks_fail_closed() -> None:
    arms = list(_p5_arm_results())
    with pytest.raises(ValueError, match="all four preregistered arms"):
        build_p5_diagnostic_result(
            _protocols(),
            execution_id="run",
            producer_id="producer",
            source_bundle_sha256=SOURCE_BUNDLE_SHA256,
            runtime_binding_receipt=_runtime_receipt(
                RuntimeTaskId.PROPOSAL_P5,
                execution_id="run",
                producer_id="producer",
            ),
            arm_results=arms[:-1],
        )

    crossed = (arms[0], arms[0], arms[2], arms[3])
    with pytest.raises(ValueError, match="all four preregistered arms"):
        build_p5_diagnostic_result(
            _protocols(),
            execution_id="run",
            producer_id="producer",
            source_bundle_sha256=SOURCE_BUNDLE_SHA256,
            runtime_binding_receipt=_runtime_receipt(
                RuntimeTaskId.PROPOSAL_P5,
                execution_id="run",
                producer_id="producer",
            ),
            arm_results=crossed,
        )

    incomplete = arms[0].model_dump(mode="python")
    incomplete["axis_recall"].pop(ParticleAxis.REGIME)
    with pytest.raises(ValidationError, match="every particle axis"):
        P5ArmResult.model_validate(incomplete)


def test_p5_diagnosis_pass_and_oracle_leak_forgery_fail_closed() -> None:
    result = _p5_result(execution_id="run", producer_id="producer")
    forged = result.model_dump(mode="python")
    forged["diagnosis"] = "NO_PROPOSAL_HEADROOM"
    forged["primary_estimand_value"] = 0.0
    with pytest.raises(ValidationError, match="recomputed from the four-arm matrix"):
        TaskP5DiagnosticResult.model_validate(forged)

    passed = result.model_dump(mode="python")
    passed["passed"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TaskP5DiagnosticResult.model_validate(passed)

    deployable = _p5_arm_results()[0].model_dump(mode="python")
    deployable["truth_read_count"] = 1
    deployable["exact_enumeration_count"] = 1
    with pytest.raises(ValidationError, match="deployable arms cannot read truth"):
        P5ArmResult.model_validate(deployable)


def test_p5_verifier_revalidates_a_bypassed_model_copy() -> None:
    reported = _p5_result(execution_id="p5-a", producer_id="producer-a").model_copy(
        update={"diagnosis": P5Diagnosis.NO_PROPOSAL_HEADROOM}
    )
    recomputed = _p5_result(execution_id="p5-b", producer_id="producer-b")
    with pytest.raises(ValidationError, match="recomputed from the four-arm matrix"):
        verify_p5_result(
            _protocols(),
            reported=reported,
            recomputed=recomputed,
            expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        )


def test_p5_cannot_be_used_as_binding_resolution_input() -> None:
    reported = _p5_result(execution_id="p5-a", producer_id="producer-a")
    recomputed = _p5_result(execution_id="p5-b", producer_id="producer-b")
    with pytest.raises(ValueError, match="matching resolvable schema"):
        derive_binding_resolution(  # type: ignore[arg-type]
            _protocols(),
            reported=reported,
            recomputed=recomputed,
            expected_source_bundle_sha256=SOURCE_BUNDLE_SHA256,
        )
