"""Protocol tests for the backbone-scale chained falsifier.

The negative tests matter as much as the positive ones: the previous instrument
failed precisely because nothing stopped an "approximate" method from scoring
the entire state space, and because the analytic state was a formatted string.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace

import pytest

import cpswm.system.evaluation_operations.structure_two_backbone_falsifier as backbone
from cpswm.system.evaluation_operations.structure_two_backbone_falsifier import (
    ACTION_QUERY_FEATURES,
    ACTORS,
    ADAPTIVE_ESCAPE_MAX,
    ADAPTIVE_ESCAPE_MIN,
    ADAPTIVE_ESCAPE_SATURATION,
    ADAPTIVE_UNEXPLAINED_TARGET,
    APPROXIMATE_ARMS,
    CONSOLIDATION_THRESHOLD_SWEEP,
    FALSE_PROMOTE_COST,
    MIN_MEASURABLE_CONSEQUENTIAL_ACTION_DISTANCE,
    MIN_MEASURABLE_FACTORIZATION_TV,
    NOISE_VARIANCE,
    PLACEMENT_BINS,
    RELATIVE_PROBABILITY_SOFT_COUPLING_NATS,
    TASK8_PROTOCOL_ID,
    UNRESOLVED_KEY,
    Actor,
    AnalyticBlock,
    ArmConfiguration,
    ArmName,
    BackboneScenario,
    CallerRole,
    Cause,
    CheckpointIntegrityError,
    CorrectionTreatment,
    CostMeter,
    EmbodiedAction,
    ExactEnumerationBudgetExceeded,
    FullEnumerationForbiddenError,
    GapHypothesis,
    InferenceCoupling,
    Instance,
    Mechanism,
    Particle,
    PersistentWindowSequence,
    RegimeMove,
    _adaptive_candidates,
    _adaptive_escape,
    _aggregate,
    _cause_key,
    _coupling_table,
    _CouplingRow,
    _decouple,
    _event_key,
    _mutual_information,
    _run_stream,
    _seal_window_checkpoint,
    _typed_candidates,
    _verify_window_checkpoint,
    _window_rejuvenate,
    action_cost,
    action_regret,
    actor_marginal,
    build_scenario,
    chain_embodied_action,
    chain_is_admissible,
    chain_log_target,
    consequential_action_policy,
    consolidation_cost_curve,
    count_chains,
    decision_regret,
    exact_posterior,
    exact_posterior_with_actions,
    gap_is_admissible,
    gap_log_prior,
    iter_chains,
    marginal_distance,
    measure_enumeration_boundary,
    normalize_log_targets,
    owner_contamination,
    owner_mass_calibration_error,
    proposal_coverage,
    registered_scenarios,
    repair_observation,
    run_budget_sweep,
    run_joint_coupling_death_test,
    run_late_correction,
    run_particle_arm,
    run_relative_probability_soft_coupling_study,
    run_task7_window_complexity_probe,
    task7_belief_marginals,
    task8_endpoint_consumes_interaction,
    total_variation,
)


@pytest.fixture(scope="module")
def scenario() -> BackboneScenario:
    return build_scenario(
        gaps=1,
        seed=11,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=False,
        short_regime=True,
    )


# --- protocol section 3.2/3.3: approximate arms may not enumerate -------------


@pytest.mark.parametrize("role", [CallerRole.APPROXIMATE_ARM, CallerRole.LADDER_DIAGNOSTIC])
def test_only_the_exact_oracle_may_enumerate(scenario: BackboneScenario, role: CallerRole) -> None:
    meter = CostMeter(arm=ArmName.RBPF)
    with pytest.raises(FullEnumerationForbiddenError):
        exact_posterior(scenario, meter, caller_role=role)


def test_particle_arms_score_far_fewer_states_than_the_exact_oracle(
    scenario: BackboneScenario,
) -> None:
    exact_meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    exact_posterior(scenario, exact_meter, caller_role=CallerRole.EXACT_ORACLE)
    for arm in sorted(APPROXIMATE_ARMS):
        result = run_particle_arm(scenario, arm=arm, budget=16, seed=11)
        scored = int(result.cost["unique_state_target_evaluations"])
        assert scored < exact_meter.unique_state_target_evaluations / 10, arm


def test_enumeration_boundary_is_measured_not_assumed() -> None:
    boundary = measure_enumeration_boundary(1, budget=2_000)
    assert boundary["enumerable_within_budget"] is True
    tight = measure_enumeration_boundary(2, budget=5_000)
    assert tight["enumerable_within_budget"] is False
    assert tight["states_reached"] > 5_000


def test_exact_enumeration_budget_is_enforced(scenario: BackboneScenario) -> None:
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    with pytest.raises(ExactEnumerationBudgetExceeded):
        exact_posterior(scenario, meter, caller_role=CallerRole.EXACT_ORACLE, state_budget=10)


# --- protocol section 1: the chain really grows -------------------------------


def test_state_space_grows_strictly_with_gaps() -> None:
    assert count_chains(2) > count_chains(1)


def test_every_particle_variable_grows_with_gaps() -> None:
    one = next(iter(iter_chains(1)))
    two = next(iter(iter_chains(2)))
    assert len(two.gaps) > len(one.gaps)
    assert len(two.event_chain) > len(one.event_chain)
    assert len(two.ordered_actor_roles) > len(one.ordered_actor_roles)
    assert len(two.lineage) > len(one.lineage)
    assert len(two.run_lengths) > len(one.run_lengths)
    assert len(two.regime_timeline) > len(one.regime_timeline)


def test_ordered_roles_are_unique_within_a_chain() -> None:
    for index, chain in enumerate(iter_chains(2)):
        names = [role for role, _actor in chain.ordered_actor_roles]
        assert len(names) == len(set(names))
        if index > 200:
            break


def test_only_habit_cause_may_found_a_regime() -> None:
    for index, chain in enumerate(iter_chains(1)):
        for gap in chain.gaps:
            if gap.regime_move in {RegimeMove.CREATE, RegimeMove.REACTIVATE}:
                assert gap.cause is Cause.HABIT
        if index > 500:
            break


def test_reactivation_needs_a_retired_regime() -> None:
    assert not any(
        gap.regime_move is RegimeMove.REACTIVATE for chain in iter_chains(1) for gap in chain.gaps
    )
    assert any(
        gap.regime_move is RegimeMove.REACTIVATE for chain in iter_chains(2) for gap in chain.gaps
    )


# --- typed constraints are part of the target --------------------------------


def _gap(receiver: Actor, instance: Instance, move: RegimeMove) -> GapHypothesis:
    return GapHypothesis(
        mechanism=Mechanism.DIRECT,
        giver=receiver,
        receiver=receiver,
        instance=instance,
        cause=Cause.HABIT,
        regime_move=move,
        regime_target="R1" if move is not RegimeMove.UNRESOLVED else None,
    )


def test_robot_operation_may_not_found_an_owner_regime() -> None:
    assert not gap_is_admissible(_gap(Actor.ROBOT, Instance.TARGET, RegimeMove.CREATE))
    assert gap_is_admissible(_gap(Actor.OWNER, Instance.TARGET, RegimeMove.CREATE))


def test_unidentified_instance_may_not_found_a_regime() -> None:
    assert not gap_is_admissible(_gap(Actor.OWNER, Instance.UNKNOWN, RegimeMove.CREATE))


def test_direct_mechanism_requires_one_actor() -> None:
    invalid = GapHypothesis(
        mechanism=Mechanism.DIRECT,
        giver=Actor.OWNER,
        receiver=Actor.GUEST,
        instance=Instance.TARGET,
        cause=Cause.NOISE,
        regime_move=RegimeMove.STAY,
        regime_target="R0",
    )
    assert not gap_is_admissible(invalid)


def test_inadmissible_chains_never_enter_the_exact_posterior(
    scenario: BackboneScenario,
) -> None:
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    posterior = exact_posterior(scenario, meter, caller_role=CallerRole.EXACT_ORACLE)
    admissible = {chain.key for chain in iter_chains(1) if chain_is_admissible(chain)}
    assert set(posterior) - {UNRESOLVED_KEY} <= admissible


# --- protocol section 2: the analytic block is real ---------------------------


def test_analytic_block_is_an_object_not_a_reference_string(
    scenario: BackboneScenario,
) -> None:
    result = run_particle_arm(scenario, arm=ArmName.RBPF, budget=8, seed=3)
    assert result.support_chains
    block = AnalyticBlock()
    assert not isinstance(block.a_matrix, str)
    assert len(block.a_matrix) == 3
    assert len(block.alpha) == PLACEMENT_BINS


def test_analytic_updates_are_observation_driven() -> None:
    block = AnalyticBlock()
    baseline = block.log_marginal()
    assert baseline == 0.0
    block.update((1.0, 0.0, 1.0), 0.8, 1)
    after_one = block.log_marginal()
    block.update((1.0, 1.0, 0.0), -0.4, 2)
    after_two = block.log_marginal()
    assert after_one != baseline
    assert after_two != after_one
    assert block.count == 2


def test_removing_the_analytic_update_changes_the_result() -> None:
    updated = AnalyticBlock()
    updated.update((1.0, 1.0, 1.0), 1.2, 0)
    skipped = AnalyticBlock()
    assert updated.log_marginal() != skipped.log_marginal()


def test_rbpf_and_sampled_theta_are_different_algorithms(
    scenario: BackboneScenario,
) -> None:
    integrated = run_particle_arm(scenario, arm=ArmName.RBPF, budget=24, seed=7)
    sampled = run_particle_arm(scenario, arm=ArmName.SAMPLED_THETA_PF, budget=24, seed=7)
    assert total_variation(integrated.posterior, sampled.posterior) > 0.0


# --- normalization and calibration -------------------------------------------


def test_posterior_includes_explicit_unresolved_mass(scenario: BackboneScenario) -> None:
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    posterior = exact_posterior(scenario, meter, caller_role=CallerRole.EXACT_ORACLE)
    assert UNRESOLVED_KEY in posterior
    assert abs(sum(posterior.values()) - 1.0) < 1e-9


def test_unresolved_mass_does_not_swamp_the_posterior(
    scenario: BackboneScenario,
) -> None:
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    posterior = exact_posterior(scenario, meter, caller_role=CallerRole.EXACT_ORACLE)
    assert posterior[UNRESOLVED_KEY] < 0.5


def test_particle_posteriors_also_normalize(scenario: BackboneScenario) -> None:
    for arm in sorted(APPROXIMATE_ARMS):
        result = run_particle_arm(scenario, arm=arm, budget=12, seed=5)
        assert abs(sum(result.posterior.values()) - 1.0) < 1e-9


def test_exact_action_marginal_is_a_distribution(scenario: BackboneScenario) -> None:
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    posterior, actions = exact_posterior_with_actions(
        scenario, meter, caller_role=CallerRole.EXACT_ORACLE
    )
    assert set(actions) == set(range(PLACEMENT_BINS))
    assert abs(sum(actions.values()) - (1.0 - posterior[UNRESOLVED_KEY])) < 1e-9


# --- cost instrumentation -----------------------------------------------------


def test_cost_counters_are_reported_for_every_arm(scenario: BackboneScenario) -> None:
    required = {
        "unique_state_target_evaluations",
        "elementary_likelihood_evaluations",
        "proposal_generation_evaluations",
        "particle_count",
        "resampling_events",
        "ancestry_window_length",
        "peak_tracked_objects",
        "wall_clock_seconds",
    }
    for arm in sorted(APPROXIMATE_ARMS):
        result = run_particle_arm(scenario, arm=arm, budget=8, seed=2)
        assert required <= set(result.cost)


def test_typed_arm_pays_more_proposal_cost_than_bootstrap(
    scenario: BackboneScenario,
) -> None:
    typed = run_particle_arm(scenario, arm=ArmName.TYPED_RBPF, budget=24, seed=9)
    bootstrap = run_particle_arm(scenario, arm=ArmName.RBPF, budget=24, seed=9)
    assert int(typed.cost["proposal_generation_evaluations"]) > int(
        bootstrap.cost["proposal_generation_evaluations"]
    )


def test_ancestry_window_grows_with_gaps() -> None:
    short = build_scenario(
        gaps=1,
        seed=4,
        high_attribution_ambiguity=False,
        adverse_delayed_feedback=False,
        open_world_actor=False,
        short_regime=False,
    )
    long = build_scenario(
        gaps=3,
        seed=4,
        high_attribution_ambiguity=False,
        adverse_delayed_feedback=False,
        open_world_actor=False,
        short_regime=False,
    )
    a = run_particle_arm(short, arm=ArmName.RBPF, budget=8, seed=4)
    b = run_particle_arm(long, arm=ArmName.RBPF, budget=8, seed=4)
    assert int(b.cost["ancestry_window_length"]) > int(a.cost["ancestry_window_length"])


def test_actor_axis_is_open_world() -> None:
    assert Actor.UNKNOWN in ACTORS
    assert Instance.UNKNOWN in tuple(Instance)


# --- task 10: readout discrimination and the budget sweep --------------------


def test_action_readout_consumes_more_than_the_regime_label(
    scenario: BackboneScenario,
) -> None:
    """The old instrument's action gate was degenerate because the readout only
    consumed the regime label.  The exact action marginal must spread over more
    than one bin once actor attribution and instance association differ."""

    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    _posterior, actions = exact_posterior_with_actions(
        scenario, meter, caller_role=CallerRole.EXACT_ORACLE
    )
    occupied = [value for value in actions.values() if value > 1e-6]
    assert len(occupied) >= 2


def test_action_scores_use_both_analytic_blocks() -> None:
    categorical_only = AnalyticBlock()
    categorical_only.alpha[0] += 5.0
    both = AnalyticBlock()
    both.alpha[0] += 5.0
    both.update((1.0, 0.0, 1.0), 1.0, 2)
    assert categorical_only.action_log_scores(ACTION_QUERY_FEATURES) != both.action_log_scores(
        ACTION_QUERY_FEATURES
    )


def test_budget_sweep_reports_spread_and_truth_losses() -> None:
    report = run_budget_sweep(
        gaps=1,
        scenario_seeds=[11],
        budgets=(8, 16),
        replicate_seeds=(101, 202),
    )
    assert report["gaps"] == 1
    assert len(report["cells"]) == 2 * len(APPROXIMATE_ARMS)
    for cell in report["cells"]:
        assert cell["replicates"] == 8 * 2
        assert 0.0 <= cell["truth_coverage"] <= 1.0
        assert cell["stdev_total_variation"] >= 0.0
        assert isinstance(cell["truth_loss_cases"], list)
        assert cell["mean_proposal_evaluations"] > 0.0


def test_sweep_reuses_one_exact_reference_per_scenario() -> None:
    report = run_budget_sweep(
        gaps=1,
        scenario_seeds=[11],
        budgets=(8,),
        replicate_seeds=(101,),
    )
    assert len(report["exact_reference"]) == 8
    for reference in report["exact_reference"]:
        assert reference["truth_in_exact_support"] is True


# --- regressions for the 2026-09-02 adversarial audit -------------------------


def _independent_solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Gaussian elimination written independently of the module's cofactor code."""

    size = len(vector)
    rows = [[*list(matrix[i]), vector[i]] for i in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda r: abs(rows[r][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value / divisor for value in rows[column]]
        for other in range(size):
            if other != column and rows[other][column] != 0.0:
                factor = rows[other][column]
                rows[other] = [
                    a - factor * b for a, b in zip(rows[other], rows[column], strict=True)
                ]
    return [row[size] for row in rows]


def test_analytic_marginal_matches_the_one_step_predictive_decomposition() -> None:
    """log p(y_1..n) must telescope into the sequential predictive terms.

    This is an independent derivation of the same quantity: the increment the
    RBPF arm charges per gap has to equal the closed-form one-step predictive,
    Dirichlet term included.  It is the check the first test suite lacked.
    """

    block = AnalyticBlock()
    data = [((1.0, 0.0, 1.0), 0.8, 1), ((1.0, 1.0, 0.0), -0.4, 2), ((1.0, 1.0, 1.0), 1.3, 0)]
    for x, y, placement in data:
        before = block.log_marginal()
        mean_vector = _independent_solve(
            [list(row) for row in block.a_matrix], list(block.b_vector)
        )
        spread = _independent_solve([list(row) for row in block.a_matrix], list(x))
        predictive_mean = sum(mean_vector[i] * x[i] for i in range(3))
        predictive_variance = NOISE_VARIANCE + sum(spread[i] * x[i] for i in range(3))
        residual = y - predictive_mean
        expected = (
            math.log(block.alpha[placement] / sum(block.alpha))
            - 0.5 * math.log(2.0 * math.pi * predictive_variance)
            - residual * residual / (2.0 * predictive_variance)
        )
        block.update(x, y, placement)
        assert abs((block.log_marginal() - before) - expected) < 1e-9


def test_effective_sample_size_is_not_measured_after_a_resample() -> None:
    """A degenerate arm must not report a perfect ESS.

    Resampling on the final step zeroed every weight, so the two arms that had
    just collapsed reported ESS == budget while the healthy arm reported less.
    """

    scenario = build_scenario(
        gaps=2,
        seed=11,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=False,
        open_world_actor=False,
        short_regime=True,
    )
    for arm in (ArmName.SAMPLED_THETA_PF, ArmName.RBPF):
        result = run_particle_arm(scenario, arm=arm, budget=48, seed=1)
        assert result.effective_sample_size < 48.0


def test_total_variation_is_not_identical_to_proposal_coverage() -> None:
    """TV must price the weights, not only the support.

    While the arm re-scored its support with the exact target, TV was exactly
    ``1 - proposal_coverage`` — a coverage metric wearing a posterior-quality
    name, which is the defect that retired the previous instrument.
    """

    scenario = build_scenario(
        gaps=1,
        seed=11,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=False,
        open_world_actor=False,
        short_regime=True,
    )
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    exact = exact_posterior(scenario, meter, caller_role=CallerRole.EXACT_ORACLE)
    separated = 0
    for arm in sorted(APPROXIMATE_ARMS):
        result = run_particle_arm(scenario, arm=arm, budget=32, seed=5)
        variation = total_variation(exact, result.posterior)
        coverage = proposal_coverage(exact, result.support)
        if abs(variation - (1.0 - coverage)) > 1e-6:
            separated += 1
    assert separated == len(APPROXIMATE_ARMS)


def test_importance_weights_estimate_the_normalizer(
    scenario: BackboneScenario,
) -> None:
    """One-step SMC evidence must converge to the enumerable truth.

    The typed arm's escape branch proposes gaps that lie outside its candidate
    set; forgetting the escape factor in their proposal density made every such
    weight 1/epsilon too small and biased this estimate low by ~0.4 nat.
    """

    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    exact_log_targets: list[float] = []
    for chain in iter_chains(1):
        if chain_is_admissible(chain):
            exact_log_targets.append(chain_log_target(chain, scenario.observations, meter))
    truth = max(exact_log_targets) + math.log(
        sum(math.exp(value - max(exact_log_targets)) for value in exact_log_targets)
    )
    for arm in (ArmName.RBPF, ArmName.TYPED_RBPF, ArmName.ADAPTIVE_TYPED_RBPF):
        estimate = run_particle_arm(scenario, arm=arm, budget=4000, seed=17).log_evidence
        assert abs(estimate - truth) < 0.15, (arm, estimate, truth)


def test_action_regret_declines_to_score_an_arm_that_proposes_nothing() -> None:
    assert action_regret({0: 0.5, 1: 0.3, 2: 0.15}, {0: 0.0, 1: 0.0, 2: 0.0}) is None
    assert action_regret({}, {0: 1.0}) is None
    assert action_regret({0: 0.5, 1: 0.3, 2: 0.15}, {0: 0.1, 1: 0.9, 2: 0.0}) == pytest.approx(0.2)


# --- typed proposer redesign (adaptive radius + adaptive escape) --------------


def test_adaptive_radius_widens_only_for_an_unexplainable_reading() -> None:
    """A radius-1 neighbourhood is a coverage ceiling when the reading is corrupt.

    The redesign spends the extra candidates exactly where the best admissible
    candidate cannot explain the reading, and nowhere else.
    """

    clean = build_scenario(
        gaps=1,
        seed=11,
        high_attribution_ambiguity=False,
        adverse_delayed_feedback=False,
        open_world_actor=False,
        short_regime=True,
    )
    corrupt = build_scenario(
        gaps=1,
        seed=11,
        high_attribution_ambiguity=False,
        adverse_delayed_feedback=True,
        open_world_actor=False,
        short_regime=True,
    )
    origin = Particle(
        gaps=(),
        timeline=(),
        runs=(),
        current="R0",
        retired=(),
        created=0,
        log_weight=0.0,
        blocks={},
        thetas={},
        ancestry=(),
    )
    meter = CostMeter(arm=ArmName.ADAPTIVE_TYPED_RBPF)
    _c1, _s1, clean_deficit, clean_radius = _adaptive_candidates(
        origin, clean.observations[0], meter
    )
    wide, _s2, corrupt_deficit, corrupt_radius = _adaptive_candidates(
        origin, corrupt.observations[0], meter
    )
    assert corrupt_deficit > clean_deficit
    assert clean_radius == 1
    assert corrupt_radius > clean_radius
    assert len(wide) > len(_typed_candidates(origin, corrupt.observations[0], 1))


def test_adaptive_escape_is_bounded_and_monotone_in_the_deficit() -> None:
    assert _adaptive_escape(0.0) == pytest.approx(ADAPTIVE_ESCAPE_MIN)
    assert _adaptive_escape(ADAPTIVE_ESCAPE_SATURATION) == pytest.approx(ADAPTIVE_ESCAPE_MAX)
    assert _adaptive_escape(10.0) == pytest.approx(ADAPTIVE_ESCAPE_MAX)
    assert _adaptive_escape(1.0) > _adaptive_escape(0.2)


def test_adaptive_deficit_is_scale_free_in_reliability() -> None:
    """The same structural failure must widen the neighbourhood whether or not
    the scenario is also ambiguous.  Measuring the deficit in raw nats did not:
    low reliability shrinks the nat gap, so the arm refused to widen in the
    hardest cell (corrupted AND ambiguous) — where the truth was not even in the
    candidate set."""

    origin = Particle(
        gaps=(),
        timeline=(),
        runs=(),
        current="R0",
        retired=(),
        created=0,
        log_weight=0.0,
        blocks={},
        thetas={},
        ancestry=(),
    )
    meter = CostMeter(arm=ArmName.ADAPTIVE_TYPED_RBPF)
    deficits = []
    for ambiguity in (False, True):
        corrupt = build_scenario(
            gaps=1,
            seed=11,
            high_attribution_ambiguity=ambiguity,
            adverse_delayed_feedback=True,
            open_world_actor=False,
            short_regime=True,
        )
        _c, _s, deficit, _r = _adaptive_candidates(origin, corrupt.observations[0], meter)
        deficits.append(deficit)
    assert min(deficits) > ADAPTIVE_UNEXPLAINED_TARGET


def test_both_typed_arms_run_and_stay_normalized(scenario: BackboneScenario) -> None:
    for arm in (ArmName.TYPED_RBPF, ArmName.ADAPTIVE_TYPED_RBPF):
        result = run_particle_arm(scenario, arm=arm, budget=16, seed=3)
        assert abs(sum(result.posterior.values()) - 1.0) < 1e-9
        assert result.cost["mean_proposal_radius"] >= 1.0


# --- protocol task 7: late correction ----------------------------------------


def test_repair_observation_restores_the_corrupted_axes() -> None:
    scenario = build_scenario(
        gaps=3,
        seed=11,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=False,
        short_regime=True,
        corrupt_index=1,
    )
    assert scenario.observations[1].observed_receiver is not scenario.truth.gaps[1].receiver
    corrected = repair_observation(scenario, 1)
    assert corrected.observations[1].observed_receiver is scenario.truth.gaps[1].receiver
    assert corrected.observations[1].observed_cause is scenario.truth.gaps[1].cause
    assert corrected.observations[0] == scenario.observations[0]


def test_local_rejuvenation_reproduces_full_rerun_at_lower_cost() -> None:
    """The local kernel is approximate, non-identical, and cheaper at large G."""

    scenario = build_scenario(
        gaps=6,
        seed=11,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=False,
        short_regime=True,
        corrupt_index=1,
    )
    full = run_late_correction(
        scenario,
        treatment=CorrectionTreatment.FULL_RERUN,
        correction_index=1,
        arm=ArmName.RBPF,
        budget=64,
        seed=5,
    )
    local = run_late_correction(
        scenario,
        treatment=CorrectionTreatment.LOCAL_REJUVENATION,
        correction_index=1,
        arm=ArmName.RBPF,
        budget=64,
        seed=5,
    )
    distance = marginal_distance(actor_marginal(full, 1), actor_marginal(local, 1))
    assert 0.0 < distance < 0.08
    # A full-chain TV is intentionally not used as the equivalence metric: in
    # this large chain space independent valid particle supports have TV ~ 1.
    assert total_variation(full.posterior, local.posterior) > 0.1
    assert int(local.cost["ancestry_window_length"]) == 1
    assert int(local.cost["marginal_rejuvenation_proposals"]) == 64
    assert int(local.cost["marginal_elementary_likelihood_evaluations"]) < int(
        full.cost["marginal_elementary_likelihood_evaluations"]
    )
    assert float(local.cost["wall_clock_seconds"]) >= float(
        local.cost["marginal_wall_clock_seconds"]
    )


def test_window_rejuvenation_never_reproposes_outside_the_window() -> None:
    scenario = build_scenario(
        gaps=5,
        seed=23,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=True,
        short_regime=True,
        corrupt_index=2,
    )
    particles, _evidence, rng, initial_meter = _run_stream(
        scenario,
        scenario.observations,
        arm=ArmName.RBPF,
        budget=32,
        seed=7,
    )
    initial_meter.stop()
    before = [particle.gaps for particle in particles]
    corrected = repair_observation(scenario, 2)
    meter = CostMeter(arm=ArmName.RBPF, particle_count=32)
    meter.start()
    _window_rejuvenate(
        particles,
        corrected.observations,
        window_start=2,
        window_stop=3,
        sweeps=2,
        config=ArmConfiguration.of(ArmName.RBPF),
        rng=rng,
        meter=meter,
    )
    meter.stop()
    for original, revised in zip(before, particles, strict=True):
        assert revised.gaps[:2] == original[:2]
        assert revised.gaps[3:] == original[3:]
        assert chain_is_admissible(revised.chain())
    assert meter.rejuvenation_proposals == 64


def test_window_rejuvenation_keeps_terminal_state_and_corrected_blocks_consistent() -> None:
    """An untouched suffix still determines the particle's live terminal state."""

    scenario = build_scenario(
        gaps=10,
        seed=1,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=True,
        short_regime=True,
        corrupt_index=1,
    )
    particles, _evidence, rng, initial_meter = _run_stream(
        scenario,
        scenario.observations,
        arm=ArmName.RBPF,
        budget=64,
        seed=1,
    )
    initial_meter.stop()
    for particle in particles:
        checkpoint = _seal_window_checkpoint(particle, scenario.observations)
        _verify_window_checkpoint(particle, scenario.observations)
        assert checkpoint.boundary_states
    assert any(
        particle.checkpoint is not None
        and particle.checkpoint.boundary_states[2] != particle.checkpoint.boundary_states[-1]
        for particle in particles
    )

    corrected = repair_observation(scenario, 1)
    expected_first_ratio = backbone._correction_log_ratio(
        particles[0].chain(),
        scenario.observations,
        corrected.observations,
        1,
        CostMeter(arm=ArmName.EXACT_ORACLE),
    )
    meter = CostMeter(arm=ArmName.RBPF, particle_count=len(particles))
    meter.start()
    for index, particle in enumerate(particles):
        ratio = backbone._apply_fixed_observation_correction(
            particle,
            scenario.observations[1],
            corrected.observations[1],
            1,
            meter,
        )
        if index == 0:
            assert ratio == pytest.approx(expected_first_ratio)
    receipt = _window_rejuvenate(
        particles,
        corrected.observations,
        window_start=1,
        window_stop=2,
        sweeps=1,
        config=ArmConfiguration.of(ArmName.RBPF),
        rng=rng,
        meter=meter,
        source_observations=scenario.observations,
        checkpoints_preverified=True,
    )
    meter.stop()
    assert receipt.fallback_required is False
    for particle in particles:
        terminal = particle.boundary_states[-1]
        assert (particle.current, particle.retired, particle.created) == (
            terminal.current,
            terminal.retired,
            terminal.created,
        )
        rebuilt = backbone.analytic_blocks_for(
            particle.chain(),
            corrected.observations,
            CostMeter(arm=ArmName.EXACT_ORACLE),
        )
        assert set(particle.blocks) == set(rebuilt)
        for cell, actual in particle.blocks.items():
            expected = rebuilt[cell]
            assert actual.count == expected.count
            assert actual.alpha == pytest.approx(expected.alpha)
            for actual_row, expected_row in zip(actual.a_matrix, expected.a_matrix, strict=True):
                assert actual_row == pytest.approx(expected_row)
            assert actual.b_vector == pytest.approx(expected.b_vector)
            assert actual.precision == pytest.approx(expected.precision)
            assert actual.xi == pytest.approx(expected.xi)


def test_window_checkpoint_rejects_hash_and_source_stream_tampering() -> None:
    scenario = build_scenario(
        gaps=3,
        seed=11,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=False,
        short_regime=True,
        corrupt_index=1,
    )
    particles, _evidence, _rng, meter = _run_stream(
        scenario,
        scenario.observations,
        arm=ArmName.RBPF,
        budget=8,
        seed=13,
    )
    meter.stop()
    particle = particles[0]
    checkpoint = _seal_window_checkpoint(particle, scenario.observations)
    _verify_window_checkpoint(particle, scenario.observations)

    particle.checkpoint = replace(checkpoint, content_sha256="0" * 64)
    with pytest.raises(CheckpointIntegrityError, match="content hash"):
        _verify_window_checkpoint(particle, scenario.observations)

    particle.checkpoint = checkpoint
    with pytest.raises(CheckpointIntegrityError, match="source stream"):
        _verify_window_checkpoint(particle, repair_observation(scenario, 1).observations)


@pytest.mark.parametrize("correction_index", [0, 2, 4])
def test_window_rejuvenation_matches_full_rerun_at_stream_boundaries(
    correction_index: int,
) -> None:
    scenario = build_scenario(
        gaps=5,
        seed=11,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=False,
        short_regime=True,
        corrupt_index=correction_index,
    )
    for replicate_seed in (101, 202, 303):
        full = run_late_correction(
            scenario,
            treatment=CorrectionTreatment.FULL_RERUN,
            correction_index=correction_index,
            arm=ArmName.RBPF,
            budget=256,
            seed=replicate_seed,
        )
        local = run_late_correction(
            scenario,
            treatment=CorrectionTreatment.LOCAL_REJUVENATION,
            correction_index=correction_index,
            arm=ArmName.RBPF,
            budget=256,
            seed=replicate_seed,
            rejuvenation_sweeps=4,
        )
        assert local.cost["repair_mode"] == "window_local"
        assert (
            marginal_distance(
                actor_marginal(full, correction_index),
                actor_marginal(local, correction_index),
            )
            < 0.05
        )


def test_fixed_window_kernel_work_does_not_scale_with_the_untouched_suffix() -> None:
    marginal_work: dict[int, int] = {}
    full_work: dict[int, int] = {}
    for gaps in (3, 10):
        scenario = build_scenario(
            gaps=gaps,
            seed=11,
            high_attribution_ambiguity=True,
            adverse_delayed_feedback=True,
            open_world_actor=False,
            short_regime=True,
            corrupt_index=1,
        )
        local = run_late_correction(
            scenario,
            treatment=CorrectionTreatment.LOCAL_REJUVENATION,
            correction_index=1,
            arm=ArmName.RBPF,
            budget=64,
            seed=5,
        )
        full = run_late_correction(
            scenario,
            treatment=CorrectionTreatment.FULL_RERUN,
            correction_index=1,
            arm=ArmName.RBPF,
            budget=64,
            seed=5,
        )
        assert local.cost["full_suffix_replayed_by_local_kernel"] is False
        assert int(local.cost["marginal_window_gap_target_evaluations"]) <= 4 * 64
        marginal_work[gaps] = int(local.cost["marginal_elementary_likelihood_evaluations"])
        full_work[gaps] = int(full.cost["marginal_elementary_likelihood_evaluations"])
    assert marginal_work[10] - marginal_work[3] <= 100
    assert full_work[10] > 3 * full_work[3]


class _SuffixPoisonSequence[T](Sequence[T]):
    """Raises if the repair hot path reads outside its declared window."""

    def __init__(self, values: Sequence[T], allowed: range) -> None:
        self.values = values
        self.allowed = allowed

    def __len__(self) -> int:
        return len(self.values)

    def __getitem__(self, index: int | slice) -> T | tuple[T, ...]:
        if isinstance(index, slice):
            raise AssertionError("repair attempted to materialize a history slice")
        position = index if index >= 0 else len(self) + index
        if position not in self.allowed:
            raise AssertionError(f"repair read untouched history index {position}")
        return self.values[position]


def test_window_hot_path_cannot_read_copy_or_rehash_a_poisoned_long_suffix() -> None:
    scenario = build_scenario(
        gaps=12,
        seed=23,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=True,
        short_regime=True,
        corrupt_index=2,
    )
    particles, _evidence, rng, initial_meter = _run_stream(
        scenario,
        scenario.observations,
        arm=ArmName.RBPF,
        budget=1,
        seed=17,
    )
    initial_meter.stop()
    particle = particles[0]
    _seal_window_checkpoint(particle, scenario.observations)
    _verify_window_checkpoint(particle, scenario.observations)
    start, stop = 2, 5
    allowed = range(start, stop)
    original_gaps = particle.gaps
    poisoned_gaps = _SuffixPoisonSequence(original_gaps, allowed)
    poisoned_timeline = _SuffixPoisonSequence(particle.timeline, allowed)
    poisoned_runs = _SuffixPoisonSequence(particle.runs, allowed)
    particle.gaps = poisoned_gaps
    particle.timeline = poisoned_timeline
    particle.runs = poisoned_runs
    cached_action = backbone._particle_embodied_action(particle)
    assert cached_action.responsible_actor is particle.terminal_responsible_actor
    meter = CostMeter(arm=ArmName.RBPF, particle_count=1)
    receipt = _window_rejuvenate(
        particles,
        scenario.observations,
        window_start=start,
        window_stop=stop,
        sweeps=2,
        config=ArmConfiguration.of(ArmName.RBPF),
        rng=rng,
        meter=meter,
        source_observations=scenario.observations,
        checkpoints_preverified=True,
    )
    assert receipt.fallback_required is False
    assert isinstance(particle.gaps, PersistentWindowSequence)
    # The repair result retains the untouched history by reference.  If the hot
    # path had first copied/materialized it, this base identity would be lost.
    assert particle.gaps.base is poisoned_gaps
    assert meter.untouched_suffix_items_read == 0
    assert meter.untouched_suffix_items_copied == 0
    assert meter.untouched_suffix_items_rehashed == 0
    assert meter.nonself_rejuvenation_proposals == meter.rejuvenation_proposals


def test_wider_than_one_window_and_long_suffix_probe_are_constant_space_and_work() -> None:
    report = run_task7_window_complexity_probe(
        window_length=3,
        sweeps=2,
        suffix_lengths=(8, 64, 256),
    )
    assert report["passed"] is True
    rows = report["rows"]
    assert len({row["marginal_window_gap_target_evaluations"] for row in rows}) == 1
    assert len({row["marginal_max_repair_live_window_items"] for row in rows}) == 1
    assert len({row["reachable_persistent_overlay_bytes"] for row in rows}) == 1
    assert (
        rows[-1]["base_checkpoint_bytes_prepared_before_correction"]
        > rows[0]["base_checkpoint_bytes_prepared_before_correction"]
    )


def test_task7_local_delta_matches_same_full_conditional_target() -> None:
    report = backbone.validate_task7_conditional_target_contract()
    assert report["passed"] is True
    assert report["production_meter_contaminated_by_full_reference"] is False
    assert report["covers_later_window_regime_or_cell_change"] is True
    assert {row["case_id"] for row in report["rows"]} == {
        "one_gap_cell_change",
        "internal_regime_and_cell_change",
    }


def test_task7_conditional_target_mismatch_executes_full_replay_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = build_scenario(
        gaps=5,
        seed=11,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=False,
        short_regime=True,
        corrupt_index=1,
    )
    original = backbone._window_conditional_target_delta

    def mismatched_target(*args: object, **kwargs: object) -> tuple[float, float, object]:
        total, analytic, changed = original(*args, **kwargs)
        return total + 1.0, analytic, changed

    monkeypatch.setattr(backbone, "_window_conditional_target_delta", mismatched_target)
    repaired = run_late_correction(
        scenario,
        treatment=CorrectionTreatment.LOCAL_REJUVENATION,
        correction_index=1,
        arm=ArmName.RBPF,
        budget=16,
        seed=5,
        rejuvenation_window_length=2,
    )
    assert repaired.cost["repair_mode"] == "replay_fallback"
    assert repaired.cost["fallback_required"] is True
    assert "conditional_target_mismatch" in repaired.cost["fallback_reasons"]
    assert int(repaired.cost["marginal_conditional_target_mismatches"]) == 1


def test_task7_multi_axis_and_action_equivalence_are_explicit() -> None:
    scenario = build_scenario(
        gaps=5,
        seed=11,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=False,
        short_regime=True,
        corrupt_index=1,
    )
    result = run_late_correction(
        scenario,
        treatment=CorrectionTreatment.FULL_RERUN,
        correction_index=1,
        arm=ArmName.RBPF,
        budget=32,
        seed=3,
    )
    marginals = task7_belief_marginals(result, 1)
    assert set(marginals) == set(backbone.TASK7_BELIEF_AXES)
    assert all(sum(axis.values()) == pytest.approx(1.0) for axis in marginals.values())
    assert result.embodied_action_posterior_cache
    materialized_actions = backbone.embodied_action_posterior(
        result.posterior,
        result.support_chains,
        scenario.observations,
    )
    assert backbone.result_embodied_action_posterior(
        result, scenario.observations
    ) == pytest.approx(materialized_actions)

    study = backbone.run_late_correction_study(
        gaps=5,
        correction_index=1,
        scenario_seeds=(11,),
        arm=ArmName.RBPF,
        budget=24,
        replicate_seeds=(101,),
        rejuvenation_window_length=2,
        rejuvenation_sweeps=1,
        complexity_probe_suffix_lengths=(2, 16),
    )
    local = next(row for row in study["rows"] if row["treatment"] == "local_rejuvenation")
    assert set(local["belief_axis_distances_to_full_rerun"]) == set(backbone.TASK7_BELIEF_AXES)
    assert "action_distribution_distance_to_full_rerun" in local
    assert study["window_contract"]["proposal_window_length"] == 2


def test_self_proposal_is_rejected_and_forces_explicit_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = build_scenario(
        gaps=5,
        seed=11,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=False,
        short_regime=True,
        corrupt_index=1,
    )

    def return_excluded(*_args: object, **kwargs: object) -> tuple[GapHypothesis, float]:
        excluded = kwargs["exclude_gap"]
        assert isinstance(excluded, GapHypothesis)
        return excluded, 0.0

    monkeypatch.setattr(backbone, "_draw_local_gap", return_excluded)
    repaired = run_late_correction(
        scenario,
        treatment=CorrectionTreatment.LOCAL_REJUVENATION,
        correction_index=1,
        arm=ArmName.RBPF,
        budget=8,
        seed=5,
        rejuvenation_window_length=2,
    )
    assert repaired.cost["repair_mode"] == "replay_fallback"
    assert "self_proposal_returned" in repaired.cost["fallback_reasons"]


def test_unbridgeable_window_records_and_executes_full_replay_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = build_scenario(
        gaps=3,
        seed=11,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=False,
        short_regime=True,
        corrupt_index=1,
    )

    def impossible_proposal(*_args: object, **_kwargs: object) -> tuple[GapHypothesis, float]:
        return (
            GapHypothesis(
                mechanism=Mechanism.DIRECT,
                giver=Actor.OWNER,
                receiver=Actor.OWNER,
                instance=Instance.TARGET,
                cause=Cause.ACTOR,
                regime_move=RegimeMove.CREATE,
                regime_target="R999",
            ),
            0.0,
        )

    monkeypatch.setattr(backbone, "_draw_local_gap", impossible_proposal)
    repaired = run_late_correction(
        scenario,
        treatment=CorrectionTreatment.LOCAL_REJUVENATION,
        correction_index=1,
        arm=ArmName.RBPF,
        budget=32,
        seed=5,
    )
    assert repaired.cost["repair_mode"] == "replay_fallback"
    assert repaired.cost["fallback_required"] is True
    assert "no_valid_boundary_preserving_proposal" in repaired.cost["fallback_reasons"]
    assert int(repaired.cost["replay_fallbacks"]) == 1


def test_append_only_cannot_retract_the_corrupted_reading() -> None:
    """The falsifiable form of the reversible-consolidation claim.

    An append-only ledger records the correction without retracting what the
    corrupted reading already contributed, so the same gap is counted twice and
    the evidence estimate collapses against the unresolved hypothesis.
    """

    scenario = build_scenario(
        gaps=3,
        seed=23,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=True,
        short_regime=True,
        corrupt_index=1,
    )
    full = run_late_correction(
        scenario,
        treatment=CorrectionTreatment.FULL_RERUN,
        correction_index=1,
        arm=ArmName.RBPF,
        budget=64,
        seed=5,
    )
    append = run_late_correction(
        scenario,
        treatment=CorrectionTreatment.APPEND_ONLY,
        correction_index=1,
        arm=ArmName.RBPF,
        budget=64,
        seed=5,
    )
    assert append.log_evidence < full.log_evidence - 1.0
    assert append.posterior[UNRESOLVED_KEY] > full.posterior[UNRESOLVED_KEY]


def test_sampled_theta_arm_is_refused_by_the_correction_study() -> None:
    scenario = build_scenario(
        gaps=2,
        seed=11,
        high_attribution_ambiguity=False,
        adverse_delayed_feedback=True,
        open_world_actor=False,
        short_regime=True,
        corrupt_index=1,
    )
    with pytest.raises(ValueError):
        run_late_correction(
            scenario,
            treatment=CorrectionTreatment.FULL_RERUN,
            correction_index=1,
            arm=ArmName.SAMPLED_THETA_PF,
            budget=8,
            seed=1,
        )


def test_owner_contamination_counts_wrong_actor_mass() -> None:
    scenario = build_scenario(
        gaps=2,
        seed=11,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=False,
        short_regime=True,
        corrupt_index=1,
    )
    result = run_late_correction(
        scenario,
        treatment=CorrectionTreatment.APPEND_ONLY,
        correction_index=1,
        arm=ArmName.RBPF,
        budget=32,
        seed=2,
    )
    value = owner_contamination(result, scenario.truth, 1)
    assert 0.0 <= value <= 1.0


# --- belief-to-utility interface v0.3 ----------------------------------------


def test_scenario_design_controls_the_open_world_factor() -> None:
    """The factor used to be bound to seed parity, so every run pinned it True.

    That also pinned the truth's actor away from the owner, which made the
    consolidation readout unable to fire either of its two errors.
    """

    scenarios = registered_scenarios(1, [11])
    assert len(scenarios) == 8
    assert {s.open_world_actor for s in scenarios} == {False, True}
    assert {s.high_attribution_ambiguity for s in scenarios} == {False, True}
    assert {s.adverse_delayed_feedback for s in scenarios} == {False, True}


def test_action_cost_is_graded_and_asymmetric_in_the_actor() -> None:
    here = EmbodiedAction(location_bin=2, responsible_actor=Actor.OWNER)
    near = EmbodiedAction(location_bin=3, responsible_actor=Actor.OWNER)
    far = EmbodiedAction(location_bin=5, responsible_actor=Actor.OWNER)
    # Ordered locations: a 0/1 loss would price these the same.
    assert action_cost(near, here) < action_cost(far, here)
    guest_did_it = EmbodiedAction(location_bin=2, responsible_actor=Actor.GUEST)
    credited_owner = EmbodiedAction(location_bin=2, responsible_actor=Actor.OWNER)
    missed_owner = EmbodiedAction(location_bin=2, responsible_actor=Actor.GUEST)
    # Crediting the owner for a guest's placement writes a foreign habit; the
    # reverse only forgets one of the owner's own.
    assert action_cost(credited_owner, guest_did_it) > action_cost(missed_owner, here)
    assert action_cost(here, here) == 0.0


def test_readout_uses_the_cell_the_chain_attributes_the_action_to(
    scenario: BackboneScenario,
) -> None:
    """The old readout always queried the OWNER cell, empty for most chains."""

    actors = set()
    for index, chain in enumerate(iter_chains(1)):
        if chain_is_admissible(chain):
            actors.add(chain_embodied_action(chain, scenario.observations).responsible_actor)
        if index > 400:
            break
    assert len(actors) > 1


def test_owner_mass_calibration_error_separates_arms_by_quality(
    scenario: BackboneScenario,
) -> None:
    """A step-function decision cost can tie, or even reward a worse belief.

    The quantity the promote/quarantine rule rides on must be reported too.
    """

    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    exact = exact_posterior(scenario, meter, caller_role=CallerRole.EXACT_ORACLE)
    chains = {
        chain.key: chain
        for chain in iter_chains(1)
        if chain_is_admissible(chain) and chain.key in exact
    }
    small = run_particle_arm(scenario, arm=ArmName.RBPF, budget=32, seed=11)
    large = run_particle_arm(scenario, arm=ArmName.RBPF, budget=4096, seed=11)
    assert owner_mass_calibration_error(exact, chains, large) < owner_mass_calibration_error(
        exact, chains, small
    )


def test_consolidation_cost_curve_exposes_threshold_sensitivity(
    scenario: BackboneScenario,
) -> None:
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    exact = exact_posterior(scenario, meter, caller_role=CallerRole.EXACT_ORACLE)
    chains = {
        chain.key: chain
        for chain in iter_chains(1)
        if chain_is_admissible(chain) and chain.key in exact
    }
    curve = consolidation_cost_curve(exact, chains, scenario.truth)
    assert set(curve) == {f"{value:.2f}" for value in CONSOLIDATION_THRESHOLD_SWEEP}
    assert all(0.0 <= value <= FALSE_PROMOTE_COST for value in curve.values())


def test_decision_regret_declines_to_score_an_empty_belief() -> None:
    assert decision_regret({}, {"1|owner": 1.0}) is None
    assert decision_regret({"1|owner": 1.0}, {}) is None


# --- protocol task 8: the H_t x C_t coupling ablation -------------------------


def test_decoupling_preserves_normalization_and_unresolved_mass(
    scenario: BackboneScenario,
) -> None:
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    exact, table = _coupling_table(scenario, meter, 2_000_000)
    for coupling in InferenceCoupling:
        belief = _decouple(exact, table, coupling)
        assert abs(sum(belief.values()) - 1.0) < 1e-9, coupling
        assert belief[UNRESOLVED_KEY] == pytest.approx(exact[UNRESOLVED_KEY]), coupling


def test_factorized_arm_removes_the_dependence_it_is_meant_to_remove(
    scenario: BackboneScenario,
) -> None:
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    exact, table = _coupling_table(scenario, meter, 2_000_000)
    factorized = _decouple(exact, table, InferenceCoupling.FACTORIZED)
    assert _mutual_information(factorized, table) < _mutual_information(exact, table) + 1e-12
    assert _mutual_information(factorized, table) < 1e-9


def test_two_stage_arm_collapses_the_cause_to_one_value(
    scenario: BackboneScenario,
) -> None:
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    exact, table = _coupling_table(scenario, meter, 2_000_000)
    two_stage = _decouple(exact, table, InferenceCoupling.TWO_STAGE)
    causes = {row.cause for row in table if two_stage.get(row.key, 0.0) > 0.0}
    assert len(causes) == 1


def test_coupling_channel_is_only_the_admissibility_rule() -> None:
    """The task-8 result is a statement about the generator, not about households.

    The prior factorizes across axes and the likelihood is a sum across axes, so
    H and C are independent in the target by construction; the sole coupling
    channel is "only a habit cause may found a regime".  Removing that rule takes
    the prior's mutual information to exactly zero, which is why the ablation
    could not test the joint claim.
    """

    chains = [chain for chain in iter_chains(1)]
    log_prior = {chain.key: sum(gap_log_prior(gap) for gap in chain.gaps) for chain in chains}
    table = [
        _CouplingRow(
            key=chain.key,
            event=_event_key(chain),
            cause=_cause_key(chain),
            action="unused",
            owner=False,
        )
        for chain in chains
    ]
    unconstrained = normalize_log_targets(log_prior, -1e9)
    assert _mutual_information(unconstrained, table) == pytest.approx(0.0, abs=1e-12)


def test_soft_coupling_changes_relative_odds_without_changing_support() -> None:
    direct = GapHypothesis(
        mechanism=Mechanism.DIRECT,
        giver=Actor.OWNER,
        receiver=Actor.OWNER,
        instance=Instance.TARGET,
        cause=Cause.ACTOR,
        regime_move=RegimeMove.STAY,
        regime_target="R0",
    )
    handoff = GapHypothesis(
        mechanism=Mechanism.HANDOFF,
        giver=Actor.OWNER,
        receiver=Actor.FAMILY,
        instance=Instance.TARGET,
        cause=Cause.ACTOR,
        regime_move=RegimeMove.STAY,
        regime_target="R0",
    )
    base_log_odds = gap_log_prior(handoff) - gap_log_prior(direct)
    coupled_log_odds = gap_log_prior(
        handoff,
        relative_probability_coupling_nats=RELATIVE_PROBABILITY_SOFT_COUPLING_NATS,
    ) - gap_log_prior(
        direct,
        relative_probability_coupling_nats=RELATIVE_PROBABILITY_SOFT_COUPLING_NATS,
    )
    assert coupled_log_odds - base_log_odds == pytest.approx(
        RELATIVE_PROBABILITY_SOFT_COUPLING_NATS
    )
    assert gap_is_admissible(direct)
    assert gap_is_admissible(handoff)


def test_task8_generator_and_target_share_the_soft_interaction() -> None:
    coupled = build_scenario(
        gaps=1,
        seed=17,
        high_attribution_ambiguity=False,
        adverse_delayed_feedback=False,
        open_world_actor=False,
        short_regime=True,
        relative_probability_coupling_nats=RELATIVE_PROBABILITY_SOFT_COUPLING_NATS,
        relative_probability_truth_model=True,
    )
    assert coupled.relative_probability_coupling_nats == pytest.approx(
        RELATIVE_PROBABILITY_SOFT_COUPLING_NATS
    )
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    coupled_target = chain_log_target(
        coupled.truth,
        coupled.observations,
        meter,
        relative_probability_coupling_nats=coupled.relative_probability_coupling_nats,
    )
    uncoupled_target = chain_log_target(coupled.truth, coupled.observations, meter)
    expected_shift = sum(
        RELATIVE_PROBABILITY_SOFT_COUPLING_NATS
        for gap in coupled.truth.gaps
        if gap.cause is Cause.ACTOR and gap.mechanism is Mechanism.HANDOFF
    )
    assert coupled_target - uncoupled_target == pytest.approx(expected_shift)


def test_task8_soft_coupling_is_measurable_but_not_an_utility_pass() -> None:
    report = run_joint_coupling_death_test(gaps=1, scenario_seeds=[11])
    assert report["protocol_id"] == TASK8_PROTOCOL_ID
    assert report["soft_coupling"]["changes_support"] is False
    assert report["soft_coupling"]["truth_and_target_share_interaction"] is True
    assert all("-RPC1.5" in scenario_id for scenario_id in report["scenario_ids"])
    assert report["task_8_instrument_passed"] is True
    factorized = report["summary"][InferenceCoupling.FACTORIZED.value]
    assert factorized["mean_total_variation_to_joint"] >= MIN_MEASURABLE_FACTORIZATION_TV
    # The legacy readout depends on a preserved marginal; it is retained only
    # as a negative control beside the preregistered cross-cell endpoint.
    assert factorized["mean_action_posterior_distance"] < 1e-9
    assert (
        factorized["mean_consequential_action_distance_to_joint"]
        >= MIN_MEASURABLE_CONSEQUENTIAL_ACTION_DISTANCE
    )


def test_task8_negative_control_uses_the_same_stochastic_generator() -> None:
    report = run_relative_probability_soft_coupling_study(
        gaps=1,
        scenario_seeds=[11],
        strengths_nats=(0.0, RELATIVE_PROBABILITY_SOFT_COUPLING_NATS),
    )
    control = report["reports_by_strength"]["0"]
    primary = report["reports_by_strength"][f"{RELATIVE_PROBABILITY_SOFT_COUPLING_NATS:g}"]
    assert (
        control["soft_coupling"]["truth_generation_mode"]
        == primary["soft_coupling"]["truth_generation_mode"]
    )
    assert control["task_8_instrument_passed"] is False
    assert report["belief_coupling_instrument_passed"] is True
    assert report["endpoint_consumes_interaction"] is True
    assert report["consequential_action_endpoint_passed"] is True
    assert report["consequential_utility_benefit_passed"] is False
    assert report["joint_action_utility_passed"] is False
    assert report["task_8_passed"] is False
    assert report["seven_operator_efficacy_authorized"] is False


def test_task8_consequential_endpoint_changes_under_equal_marginal_cross_shift() -> None:
    assert task8_endpoint_consumes_interaction() is True
    rows = (
        _CouplingRow(
            key="ha",
            event="handoff/stay",
            cause="actor",
            action="unused",
            owner=False,
            mechanism_at_correction=Mechanism.HANDOFF.value,
            regime_move_at_correction=RegimeMove.STAY.value,
            cause_at_correction=Cause.ACTOR.value,
        ),
        _CouplingRow(
            key="ho",
            event="handoff/stay",
            cause="observation",
            action="unused",
            owner=False,
            mechanism_at_correction=Mechanism.HANDOFF.value,
            regime_move_at_correction=RegimeMove.STAY.value,
            cause_at_correction=Cause.OBSERVATION.value,
        ),
        _CouplingRow(
            key="da",
            event="direct/stay",
            cause="actor",
            action="unused",
            owner=False,
            mechanism_at_correction=Mechanism.DIRECT.value,
            regime_move_at_correction=RegimeMove.STAY.value,
            cause_at_correction=Cause.ACTOR.value,
        ),
        _CouplingRow(
            key="do",
            event="direct/stay",
            cause="observation",
            action="unused",
            owner=False,
            mechanism_at_correction=Mechanism.DIRECT.value,
            regime_move_at_correction=RegimeMove.STAY.value,
            cause_at_correction=Cause.OBSERVATION.value,
        ),
    )
    dependent = {"ha": 0.5, "do": 0.5, UNRESOLVED_KEY: 0.0}
    independent = {row.key: 0.25 for row in rows}
    independent[UNRESOLVED_KEY] = 0.0
    for field in ("event", "cause"):
        assert _aggregate(dependent, rows, field) == _aggregate(independent, rows, field)
    assert consequential_action_policy(dependent, rows) != consequential_action_policy(
        independent, rows
    )


def test_event_partition_decides_whether_the_coupling_is_visible() -> None:
    """The model's only structural coupling is C -> Z, and it is deterministic.

    Reading "H_t x C_t" literally puts Z on neither side, which hides that
    coupling entirely: the ablation then measures ~5e-4 nats and would conclude
    the generator has none.  Folding Z into H makes it visible.
    """

    scenario = build_scenario(
        gaps=1,
        seed=11,
        high_attribution_ambiguity=True,
        adverse_delayed_feedback=True,
        open_world_actor=False,
        short_regime=True,
    )
    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    exact, without = _coupling_table(scenario, meter, 2_000_000, include_regime=False)
    _exact, with_regime = _coupling_table(scenario, meter, 2_000_000, include_regime=True)
    hidden = _mutual_information(exact, without)
    shown = _mutual_information(exact, with_regime)
    assert hidden < 1e-3
    assert shown > 20.0 * hidden


def test_factorized_arm_preserves_both_marginals(scenario: BackboneScenario) -> None:
    """Marginal conservation is the invariant the factorized arm rests on.

    It holds because every (event, cause) cell is occupied; nothing in the code
    asserted it, so a ragged support would have broken the arm silently.
    """

    meter = CostMeter(arm=ArmName.EXACT_ORACLE)
    exact, table = _coupling_table(scenario, meter, 2_000_000, include_regime=True)
    factorized = _decouple(exact, table, InferenceCoupling.FACTORIZED)
    for field in ("event", "cause"):
        before = _aggregate(exact, table, field)
        after = _aggregate(factorized, table, field)
        assert set(before) == set(after), field
        for name, value in before.items():
            assert after[name] == pytest.approx(value, abs=1e-9), (field, name)


def test_cause_recovery_is_compared_by_verdict_not_by_mass() -> None:
    """Collapsing the cause concentrates all resolved mass on one value, so the
    mass metric rewards confidence rather than correctness; the three arms make
    identical 0/1 cause verdicts."""

    report = run_joint_coupling_death_test(
        gaps=1, scenario_seeds=[11], include_regime_in_event=True
    )
    accuracies = {
        coupling: summary["cause_argmax_accuracy"]
        for coupling, summary in report["summary"].items()
    }
    assert len(set(accuracies.values())) == 1, accuracies


def test_artifact_provenance_does_not_claim_a_design_it_did_not_run() -> None:
    scenario = build_scenario(
        gaps=1,
        seed=11,
        high_attribution_ambiguity=False,
        adverse_delayed_feedback=False,
        open_world_actor=False,
        short_regime=True,
        relative_probability_coupling_nats=RELATIVE_PROBABILITY_SOFT_COUPLING_NATS,
        relative_probability_truth_model=True,
    )
    report = run_joint_coupling_death_test(gaps=4, scenario_seeds=[999], scenarios=(scenario,))
    assert report["gaps"] is None
    assert report["scenario_seeds"] is None
    assert report["scenario_ids"] == [scenario.scenario_id]
