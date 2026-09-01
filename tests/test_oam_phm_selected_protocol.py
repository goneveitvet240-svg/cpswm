from __future__ import annotations

import pytest
from pydantic import ValidationError

from cpswm.system.attestation import Ed25519AttestationSigner
from cpswm.system.evaluation_operations.oam_phm_external_evidence import (
    AntiContaminationBootstrapReport,
    ClusterAxis,
    ClusterBootstrapEstimate,
)
from cpswm.system.evaluation_operations.oam_phm_selected_protocol import (
    BUDGET_DIMENSIONS,
    REQUIRED_STREAK_STAGE_ORDER,
    BudgetVectorComplianceReceipt,
    DevelopmentProcessIsolation,
    EmbodiedActionBudgetVector,
    EmbodiedActionUsageVector,
    FormalContainerIsolation,
    FrozenResponseTableContract,
    GovernedLearnedSensitivityPair,
    NonInferioritySuperiorityCriterion,
    OAMBudgetUsage,
    OAMBudgetVector,
    OAMFormalEvidenceKind,
    OnlineInferenceBudgetVector,
    OnlineInferenceUsageVector,
    Recorded3DReplayContract,
    SelectedProtocolStatus,
    StreakComponentFactoredManifest,
    StreakComponentStageRecord,
    TuningBudgetVector,
    TuningUsageVector,
    assess_budget_vector,
    current_selected_oam_protocol,
    evaluate_noninferiority_superiority,
    issue_oam_formal_evidence_receipt,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
FORMAL_SIGNER = Ed25519AttestationSigner.generate(key_id="oam-formal-test")
FORMAL_VERIFIER = FORMAL_SIGNER.verifier()


def _formal_receipt(subject, kind):  # type: ignore[no-untyped-def]
    return issue_oam_formal_evidence_receipt(
        subject,
        evidence_kind=kind,
        custodian_run_id="formal-custodian@test",
        signer=FORMAL_SIGNER,
    )


def test_selected_protocol_freezes_the_user_choices_without_claiming_completion() -> None:
    protocol = current_selected_oam_protocol()

    assert protocol.o_star_input == "recorded-3d-replay"
    assert protocol.o_star_prior == "frozen-response-table"
    assert protocol.streak_reproduction == "component-factored-reproduction"
    assert protocol.full_arm == "governed-main+learned-sensitivity"
    assert protocol.complexity_decision == "non-inferiority-plus-superiority"
    assert protocol.execution_isolation == "local-process-dev+container-formal"
    assert protocol.compute_budget == "budget-vector"
    assert protocol.status == SelectedProtocolStatus.ROUTE_FROZEN_PARAMETERS_PENDING
    assert protocol.unresolved_parameters


def test_recorded_3d_replay_rejects_evaluator_truth() -> None:
    values = dict(
        replay_id="replay@test",
        replay_dataset_sha256=SHA_A,
        scene_graph_schema_sha256=SHA_A,
        perception_producer_sha256=SHA_A,
        geometry_manifest_sha256=SHA_A,
        search_cost_manifest_sha256=SHA_A,
        identity_mapping_sha256=SHA_A,
        episode_group_manifest_sha256=SHA_A,
        immutable=True,
        evaluator_truth_fields_present=True,
    )
    with pytest.raises(ValidationError, match="cannot expose evaluator truth"):
        Recorded3DReplayContract(**values)


def test_frozen_response_table_must_precede_sealed_test_access() -> None:
    with pytest.raises(ValidationError, match="before sealed-test access"):
        FrozenResponseTableContract(
            table_id="prior@test",
            response_table_sha256=SHA_A,
            raw_response_archive_sha256=SHA_A,
            prompt_protocol_sha256=SHA_A,
            candidate_vocabulary_sha256=SHA_A,
            rank_to_probability_sha256=SHA_A,
            cache_key_schema_sha256=SHA_A,
            entry_count=10,
            generated_before_sealed_test_access=False,
        )


def _stage_records(*, accepted_count: int = 0):
    return tuple(
        StreakComponentStageRecord(
            stage=stage,
            implementation_sha256=SHA_A,
            result_artifact_sha256=SHA_B,
            acceptance_protocol_sha256=SHA_C,
            accepted=index < accepted_count,
        )
        for index, stage in enumerate(REQUIRED_STREAK_STAGE_ORDER)
    )


def test_streak_factored_reproduction_requires_order_and_prerequisites() -> None:
    manifest = StreakComponentFactoredManifest(
        reproduction_id="streak@test", stages=_stage_records(accepted_count=2)
    )
    assert not manifest.reproduction_complete

    out_of_order = list(_stage_records())
    out_of_order[0], out_of_order[1] = out_of_order[1], out_of_order[0]
    with pytest.raises(ValidationError, match="frozen order"):
        StreakComponentFactoredManifest(reproduction_id="streak@bad", stages=tuple(out_of_order))

    skipped = list(_stage_records())
    skipped[1] = skipped[1].model_copy(update={"accepted": True})
    with pytest.raises(ValidationError, match="prerequisite"):
        StreakComponentFactoredManifest(reproduction_id="streak@skipped", stages=tuple(skipped))


def test_self_declared_streak_acceptance_is_not_formal_completion() -> None:
    manifest = StreakComponentFactoredManifest(
        reproduction_id="streak@all-self-declared",
        stages=_stage_records(accepted_count=len(REQUIRED_STREAK_STAGE_ORDER)),
    )
    assert manifest.declared_reproduction_complete
    assert not manifest.reproduction_complete
    receipt = _formal_receipt(manifest, OAMFormalEvidenceKind.STREAK_MANIFEST)
    assert manifest.verified_reproduction_complete(receipt, verifier=FORMAL_VERIFIER)


def test_oam_formal_completion_rejects_attacker_self_attestation() -> None:
    manifest = StreakComponentFactoredManifest(
        reproduction_id="streak@attacker",
        stages=_stage_records(accepted_count=len(REQUIRED_STREAK_STAGE_ORDER)),
    )
    attacker = Ed25519AttestationSigner.generate(key_id=FORMAL_SIGNER.key_id)
    forged = issue_oam_formal_evidence_receipt(
        manifest,
        evidence_kind=OAMFormalEvidenceKind.STREAK_MANIFEST,
        custodian_run_id="attacker-run",
        signer=attacker,
    )
    with pytest.raises(ValueError, match="signature"):
        manifest.verified_reproduction_complete(forged, verifier=FORMAL_VERIFIER)


def test_learned_sensitivity_cannot_be_labeled_as_the_governed_full_method() -> None:
    with pytest.raises(ValidationError, match="cannot be labeled"):
        GovernedLearnedSensitivityPair(
            governed_main_arm_id="governed",
            learned_sensitivity_arm_id="learned",
            governed_wp2_wp6_composition_sha256=SHA_A,
            governance_and_write_authority_sha256=SHA_A,
            learned_variant_composition_sha256=SHA_B,
            declared_difference_sha256=SHA_C,
            shared_non_target_components_sha256=SHA_A,
            learned_variant_is_formal_full_method=True,
        )


def _budget() -> OAMBudgetVector:
    return OAMBudgetVector(
        budget_id="budget@test",
        tuning=TuningBudgetVector(gpu_hours=10.0, candidate_trials=20, training_samples=1000),
        online_inference=OnlineInferenceBudgetVector(
            wall_clock_p50_ms=50.0,
            wall_clock_p95_ms=100.0,
            model_forwards=200,
            processed_graph_edges=5000,
            llm_tokens=1000,
            peak_memory_mb=4096.0,
        ),
        embodied_action=EmbodiedActionBudgetVector(
            navigation_distance_m=100.0,
            container_interactions=10,
            additional_observations=20,
            user_interruptions=2,
        ),
    )


def _usage(*, extra_interruptions: int = 0) -> OAMBudgetUsage:
    return OAMBudgetUsage(
        tuning=TuningUsageVector(gpu_hours=5.0, candidate_trials=10, training_samples=500),
        online_inference=OnlineInferenceUsageVector(
            wall_clock_p50_ms=25.0,
            wall_clock_p95_ms=75.0,
            model_forwards=100,
            processed_graph_edges=2500,
            llm_tokens=500,
            peak_memory_mb=2048.0,
        ),
        embodied_action=EmbodiedActionUsageVector(
            navigation_distance_m=50.0,
            container_interactions=5,
            additional_observations=10,
            user_interruptions=2 + extra_interruptions,
        ),
    )


def test_budget_vector_reports_each_dimension_without_scalarization() -> None:
    receipt = assess_budget_vector(_budget(), _usage(extra_interruptions=1))

    assert not receipt.compliant
    assert receipt.exceeded_dimensions == ("embodied_action.user_interruptions",)
    assert set((*receipt.compliant_dimensions, *receipt.exceeded_dimensions)) == set(
        BUDGET_DIMENSIONS
    )


def test_budget_receipt_rejects_an_incomplete_dimension_partition() -> None:
    with pytest.raises(ValidationError, match="exact partition"):
        BudgetVectorComplianceReceipt(
            budget_vector_sha256=SHA_A,
            usage=_usage(),
            compliant_dimensions=("tuning.gpu_hours",),
            exceeded_dimensions=(),
        )


def test_hybrid_isolation_contracts_fail_closed() -> None:
    with pytest.raises(ValidationError, match="subprocess"):
        DevelopmentProcessIsolation(
            subprocess_per_arm_seed_split=False,
            hard_timeout_seconds=5.0,
            termination_grace_seconds=1.0,
        )
    with pytest.raises(ValidationError, match="read-only"):
        FormalContainerIsolation(
            oci_image_digest="sha256:" + SHA_A,
            hardware_profile_sha256=SHA_A,
            network_policy_sha256=SHA_A,
            hard_timeout_seconds=60.0,
            termination_grace_seconds=5.0,
            read_only_root_filesystem=False,
        )


def _estimate(name: str, lower: float, upper: float) -> ClusterBootstrapEstimate:
    return ClusterBootstrapEstimate(
        estimand=name,
        cluster_axis=ClusterAxis.HOUSEHOLD,
        estimate=(lower + upper) / 2,
        confidence_interval_95=(lower, upper),
        cluster_count=5,
        resamples=2000,
        seed=7,
    )


def test_noninferiority_plus_superiority_requires_all_effect_and_budget_gates() -> None:
    budget = _budget()
    report = AntiContaminationBootstrapReport(
        cluster_axis=ClusterAxis.HOUSEHOLD,
        contamination_reduction=_estimate("contamination_reduction", 0.2, 0.4),
        recovery_latency_reduction=_estimate("recovery_latency_reduction", -0.5, 2.0),
        action_utility_gain=_estimate("action_utility_gain", -0.01, 0.2),
        compute_overhead=_estimate("compute_overhead", 1.0, 3.0),
    )
    criterion = NonInferioritySuperiorityCriterion(
        criterion_id="worth@test",
        cluster_axis=ClusterAxis.HOUSEHOLD,
        confidence_level=0.95,
        minimum_contamination_reduction=0.1,
        maximum_recovery_latency_increase=1.0,
        maximum_action_utility_loss=0.02,
        budget_vector_sha256=budget.content_sha256,
    )
    decision = evaluate_noninferiority_superiority(
        report,
        criterion=criterion,
        budget_receipt=(budget_receipt := assess_budget_vector(budget, _usage())),
        report_receipt=_formal_receipt(report, OAMFormalEvidenceKind.BOOTSTRAP_REPORT),
        criterion_receipt=_formal_receipt(criterion, OAMFormalEvidenceKind.DECISION_CRITERION),
        budget_attestation=_formal_receipt(budget_receipt, OAMFormalEvidenceKind.BUDGET_RECEIPT),
        verifier=FORMAL_VERIFIER,
    )

    assert decision.criterion_satisfied


def test_noninferiority_criterion_rejects_confidence_not_supported_by_report() -> None:
    with pytest.raises(ValidationError, match=r"supports only 0\.95"):
        NonInferioritySuperiorityCriterion(
            criterion_id="worth@unsupported-confidence",
            cluster_axis=ClusterAxis.HOUSEHOLD,
            confidence_level=0.9,
            minimum_contamination_reduction=0.1,
            maximum_recovery_latency_increase=1.0,
            maximum_action_utility_loss=0.02,
            budget_vector_sha256=SHA_A,
        )
