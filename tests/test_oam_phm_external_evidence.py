from __future__ import annotations

import pytest
from pydantic import ValidationError

from cpswm.system.evaluation_operations import (
    AntiContaminationBootstrapReport,
    AntiContaminationOutcome,
    ArmExecutionBinding,
    ClusterAxis,
    ComparisonArmRole,
    ComplexityWorthDecisionStatus,
    ExternalMethod,
    ExternalReproductionManifest,
    FidelityRequirement,
    FidelityRequirementStatus,
    FormalCompetitionArm,
    MatchedCompetitionProtocol,
    OStarReferenceBelief,
    OStarReferenceConfig,
    PairedObservationOutcome,
    ReproductionReadiness,
    anti_contamination_cluster_bootstrap,
    current_blocking_design_decisions,
    current_o_star_reproduction_manifest,
    current_streak_reproduction_manifest,
    paired_cluster_bootstrap,
    streak_fisher_consolidation_loss,
    streak_mean_feature_selection,
    streak_paper_parameter_candidates,
    streak_rehearsal_weight,
    summarize_anti_contamination,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def _verified_requirement() -> FidelityRequirement:
    return FidelityRequirement(
        requirement_id="all",
        description="Complete implementation and result recheck.",
        status=FidelityRequirementStatus.VERIFIED,
        evidence_artifact_sha256=SHA_A,
        note="Checked artifact.",
    )


def _complete_manifest() -> ExternalReproductionManifest:
    return ExternalReproductionManifest(
        method=ExternalMethod.O_STAR,
        reproduction_id="o-star-complete@test",
        primary_source_url="https://example.test/paper.pdf",
        primary_source_sha256=SHA_A,
        requirements=(_verified_requirement(),),
        readiness=ReproductionReadiness.REPRODUCTION_COMPLETE,
    )


def _binding() -> ArmExecutionBinding:
    return ArmExecutionBinding(
        perception_input_sha256=SHA_C,
        map_sha256=SHA_D,
        navigation_stack_sha256=SHA_A,
        language_model_protocol_sha256=SHA_B,
        action_budget_sha256=SHA_C,
        compute_budget_sha256=SHA_D,
    )


def test_verified_fidelity_requirement_needs_content_bound_evidence() -> None:
    with pytest.raises(ValidationError, match="content-bound artifact"):
        FidelityRequirement(
            requirement_id="x",
            description="x",
            status=FidelityRequirementStatus.VERIFIED,
            note="not actually checked",
        )


def test_incomplete_manifest_cannot_claim_reproduction_complete() -> None:
    with pytest.raises(ValidationError, match="unresolved mandatory"):
        ExternalReproductionManifest(
            method=ExternalMethod.STREAK,
            reproduction_id="false-complete",
            primary_source_url="https://example.test/streak.pdf",
            primary_source_sha256=SHA_A,
            requirements=(
                FidelityRequirement(
                    requirement_id="model",
                    description="model",
                    status=FidelityRequirementStatus.MISSING,
                    note="missing",
                ),
            ),
            readiness=ReproductionReadiness.REPRODUCTION_COMPLETE,
        )


def test_current_external_manifests_fail_closed() -> None:
    o_star = current_o_star_reproduction_manifest(core_artifact_sha256=SHA_A)
    streak = current_streak_reproduction_manifest(reference_core_artifact_sha256=SHA_A)

    assert o_star.readiness == ReproductionReadiness.EQUATION_CORE_ONLY
    assert streak.readiness == ReproductionReadiness.EQUATION_CORE_ONLY
    assert not o_star.eligible_for_formal_competition
    assert not streak.eligible_for_formal_competition
    assert any(
        item.requirement_id == "dirichlet-update-core"
        and item.status == FidelityRequirementStatus.VERIFIED
        for item in o_star.requirements
    )


def test_blocking_design_decisions_are_complete_and_machine_readable() -> None:
    decisions = current_blocking_design_decisions()

    assert tuple(item.decision_id for item in decisions) == tuple(
        f"D-OAM-{index}" for index in range(1, 8)
    )
    assert all(item.blocked_deliverables and item.options for item in decisions)
    assert all(item.route_selected for item in decisions)
    assert decisions[3].selected_option_id == "governed-main+learned-sensitivity"


def test_o_star_reference_core_matches_paper_updates() -> None:
    config = OStarReferenceConfig(
        initial_pseudocount_mass=10.0,
        hit_weight=3.0,
        miss_weight=2.0,
        leak_rate=0.2,
    )
    belief = OStarReferenceBelief.initialize(
        llm_prior={"desk": 3.0, "drawer": 1.0, "impossible": 100.0},
        geometrically_feasible_locations=frozenset({"desk", "drawer"}),
        config=config,
    )
    assert belief.location_order == ("desk", "drawer")
    assert belief.alpha == pytest.approx((7.5, 2.5))

    hit = belief.observe_hit("drawer", config)
    assert hit.alpha == pytest.approx((7.5, 5.5))

    miss = belief.observe_miss("desk", config)
    assert miss.alpha == pytest.approx((7.5, 4.5))

    leaked = belief.stay_and_leak(config)
    assert leaked.alpha == pytest.approx((7.0, 3.0))
    assert sum(leaked.alpha) == pytest.approx(sum(belief.alpha))


def test_o_star_cost_aware_search_needs_complete_positive_costs() -> None:
    config = OStarReferenceConfig(
        initial_pseudocount_mass=4.0,
        hit_weight=1.0,
        miss_weight=1.0,
        leak_rate=0.0,
    )
    belief = OStarReferenceBelief.initialize(
        llm_prior={"a": 3.0, "b": 1.0},
        geometrically_feasible_locations=frozenset({"a", "b"}),
        config=config,
    )
    assert belief.cost_aware_order({"a": 10.0, "b": 1.0}) == ("b", "a")
    with pytest.raises(ValueError, match="exactly"):
        belief.cost_aware_order({"a": 1.0})


def test_streak_reference_core_matches_reported_equations_and_grid() -> None:
    grid = streak_paper_parameter_candidates(prediction_horizon_minutes=(10, 40))
    assert len(grid) == 3 * 3 * 3 * 2
    assert {item.consolidation_lambda for item in grid} == {80.0, 100.0, 200.0}
    assert {item.rehearsal_beta for item in grid} == {5.0, 10.0, 15.0}
    assert {item.epochs for item in grid} == {25, 50, 100}

    loss = streak_fisher_consolidation_loss(
        current_parameters={"a": 3.0, "b": 4.0},
        previous_parameters={"a": 1.0, "b": 2.0},
        fisher_diagonal={"a": 0.5, "b": 1.5},
        consolidation_lambda=2.0,
    )
    assert loss == pytest.approx(8.0)
    assert streak_rehearsal_weight(
        current_task_index=4, source_task_index=2, rehearsal_beta=10.0
    ) == pytest.approx(1 / 30)

    selected = streak_mean_feature_selection(
        {"left": (0.0, 0.0), "middle": (1.0, 1.0), "right": (5.0, 5.0)},
        sample_count=2,
    )
    assert selected == ("middle", "left")


def test_external_arm_rejects_a_hash_only_or_incomplete_reproduction() -> None:
    incomplete = current_o_star_reproduction_manifest(core_artifact_sha256=SHA_A)
    with pytest.raises(ValidationError, match="incomplete external reproductions"):
        FormalCompetitionArm(
            arm_id="o-star",
            implementation_version="0.1",
            role=ComparisonArmRole.EXTERNAL_BASELINE,
            reproduction_manifest=incomplete,
            independently_tuned_selection_sha256=SHA_B,
            execution_binding=_binding(),
        )
    with pytest.raises(ValidationError, match="require a faithful reproduction"):
        FormalCompetitionArm(
            arm_id="hash-only",
            implementation_version="0.1",
            role=ComparisonArmRole.EXTERNAL_BASELINE,
            independently_tuned_selection_sha256=SHA_B,
            execution_binding=_binding(),
        )


def test_formal_competition_requires_sealed_test_and_full_external_arms() -> None:
    external = FormalCompetitionArm(
        arm_id="o-star",
        implementation_version="1.0",
        role=ComparisonArmRole.EXTERNAL_BASELINE,
        reproduction_manifest=_complete_manifest(),
        independently_tuned_selection_sha256=SHA_B,
        execution_binding=_binding(),
    )
    full = FormalCompetitionArm(
        arm_id="oam-phm",
        implementation_version="1.0",
        role=ComparisonArmRole.FULL_METHOD,
        independently_tuned_selection_sha256=SHA_C,
        execution_binding=_binding(),
    )
    protocol = MatchedCompetitionProtocol(
        protocol_id="formal@test",
        validation_split_sha256=SHA_A,
        sealed_test_split_sha256=SHA_B,
        perception_input_sha256=SHA_C,
        map_sha256=SHA_D,
        navigation_stack_sha256=SHA_A,
        language_model_protocol_sha256=SHA_B,
        action_budget_sha256=SHA_C,
        compute_budget_sha256=SHA_D,
        arms=(external, full),
    )
    assert len(protocol.arms) == 2

    with pytest.raises(ValidationError, match="test access"):
        protocol.model_copy(update={"test_access_count_before_tuning_complete": 1}).__class__(
            **{
                **protocol.model_dump(),
                "test_access_count_before_tuning_complete": 1,
            }
        )


def test_formal_competition_rejects_an_arm_with_unmatched_execution_binding() -> None:
    external = FormalCompetitionArm(
        arm_id="o-star",
        implementation_version="1.0",
        role=ComparisonArmRole.EXTERNAL_BASELINE,
        reproduction_manifest=_complete_manifest(),
        independently_tuned_selection_sha256=SHA_B,
        execution_binding=_binding(),
    )
    full = FormalCompetitionArm(
        arm_id="oam-phm",
        implementation_version="1.0",
        role=ComparisonArmRole.FULL_METHOD,
        independently_tuned_selection_sha256=SHA_C,
        execution_binding=_binding().model_copy(update={"compute_budget_sha256": SHA_A}),
    )
    with pytest.raises(ValidationError, match="not bound to shared execution"):
        MatchedCompetitionProtocol(
            protocol_id="formal@test",
            validation_split_sha256=SHA_A,
            sealed_test_split_sha256=SHA_B,
            perception_input_sha256=SHA_C,
            map_sha256=SHA_D,
            navigation_stack_sha256=SHA_A,
            language_model_protocol_sha256=SHA_B,
            action_budget_sha256=SHA_C,
            compute_budget_sha256=SHA_D,
            arms=(external, full),
        )


def _paired(pair: str, episode: str, household: str, enabled_utility: float):
    return PairedObservationOutcome(
        pair_id=pair,
        episode_id=episode,
        household_id=household,
        object_family_id="cups",
        task_and_randomness_sha256=SHA_A,
        future_task_count=1,
        disabled_future_task_utility=1.0,
        enabled_future_task_utility=enabled_utility,
        disabled_primary_task_cost=1.0,
        enabled_primary_task_cost=1.1,
        disabled_observation_count=0,
        enabled_observation_count=1,
    )


def test_paired_observation_requires_a_real_intervention() -> None:
    with pytest.raises(ValidationError, match="additional incidental observations"):
        _paired("p", "e", "h", 2.0).model_copy(update={"enabled_observation_count": 0}).__class__(
            **{
                **_paired("p", "e", "h", 2.0).model_dump(),
                "enabled_observation_count": 0,
            }
        )


def test_paired_cluster_bootstrap_clusters_whole_households_and_is_deterministic() -> None:
    outcomes = (
        _paired("p1", "e1", "h1", 2.0),
        _paired("p2", "e2", "h1", 4.0),
        _paired("p3", "e3", "h2", 3.0),
    )
    first = paired_cluster_bootstrap(
        outcomes,
        cluster_axis=ClusterAxis.HOUSEHOLD,
        metric="future_task_utility",
        resamples=1000,
        seed=7,
    )
    second = paired_cluster_bootstrap(
        outcomes,
        cluster_axis=ClusterAxis.HOUSEHOLD,
        metric="future_task_utility",
        resamples=1000,
        seed=7,
    )
    assert first == second
    assert first.cluster_count == 2
    assert first.estimate == pytest.approx(2.0)


def test_complexity_worth_stays_undecided_without_user_criterion() -> None:
    outcome = AntiContaminationOutcome(
        pair_id="p1",
        episode_id="e1",
        household_id="h1",
        full_owner_contamination=0.1,
        ablated_owner_contamination=0.4,
        full_recovery_latency=2.0,
        ablated_recovery_latency=5.0,
        full_action_utility=8.0,
        ablated_action_utility=7.0,
        full_compute_units=12,
        ablated_compute_units=8,
        matched_non_target_components_sha256=SHA_A,
    )
    evidence = summarize_anti_contamination((outcome,))

    assert evidence.contamination_reduction == pytest.approx(0.3)
    assert evidence.recovery_latency_reduction == pytest.approx(3.0)
    assert evidence.action_utility_gain == pytest.approx(1.0)
    assert evidence.compute_overhead == pytest.approx(4.0)
    assert evidence.decision_status == ComplexityWorthDecisionStatus.AWAITING_USER_CRITERION

    bootstrap = anti_contamination_cluster_bootstrap(
        (outcome,), cluster_axis=ClusterAxis.HOUSEHOLD, resamples=1000
    )
    assert isinstance(bootstrap, AntiContaminationBootstrapReport)
    assert bootstrap.contamination_reduction.estimate == pytest.approx(0.3)
    assert bootstrap.action_utility_gain.cluster_count == 1
