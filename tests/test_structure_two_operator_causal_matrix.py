"""R4: per-operator controlled interventions with null controls.

The round-one evidence table merged "the callable was bound" with "the operator is
algorithmically equivalent to the frozen method", and used one CIAV intervention as
if it spoke for the other six.  This file replaces that with one controlled
intervention per operator plus a null control, and keeps six separate columns:

``runtime`` / ``binding_kind``      where the call ran and how it was bound
``handoff``                          the operator's own receipted output moved
``numeric_state``                    a downstream numeric quantity moved
``action_distribution``              the readout distribution moved
``decoded_action``                   the decoded typed PUT_BACK top-1 moved
``task_benefit``                     never established here

Every intervention perturbs a *real algorithmic input* or uses a legal execution
path.  No receipt is hand-written, no hash is swapped, and no operator is disabled,
so none of this is a seven-operator ablation.  Where an operator's decoded-action
trigger condition is not met in the covered scenarios, the cell is reported as
uncovered rather than forced.

Fixed inputs, fixed seed, deterministic scenario generator.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from structure_two_backbone_wiring_probe import (
    BackboneWiringProbe,
    CIAVOutcomeKind,
    verify_and_flatten,
)

from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig
from cpswm.world_model.habits_transitions import CauseSignalFrame, ChangeCause
from cpswm.world_model.habits_transitions.joint_cause_bocpd import (
    JointCauseFactorizedBOCPD,
)

SEED = 7
#: Horizon at which two candidate locations are close enough for a decoded flip.
DECODED_FLIP_DAYS = 24
#: Horizon at which the CCRR confirmation window changes the committed set.
CCRR_DIVERGENCE_DAYS = 18


def _top(distribution: dict[UUID, float]) -> UUID:
    return min(distribution, key=lambda key: (-distribution[key], str(key)))


def _legacy_run(days: int, *, loop_config: PrototypeLoopConfig | None = None, **transition):
    probe = BackboneWiringProbe.build(seed=SEED, loop_config=loop_config)
    core = probe.system.core
    last = None
    for observation in probe.observed_days()[:days]:
        last = core.process_transition(probe.transition_for(observation, **transition))
    assert last is not None
    return probe, core, last


def _readout(probe: BackboneWiringProbe) -> tuple[str, UUID]:
    return probe.action_distribution_sha256(), _top(probe.action_distribution())


# ---------------------------------------------------------------------------
# OPCEU
# ---------------------------------------------------------------------------


def test_opceu_applied_weight_matches_the_frozen_inverse_propensity_formula() -> None:
    """Algorithmic equivalence, not binding identity.

    ``propensity_from_opportunity`` is the product of selection, visibility and
    detection probabilities; ``PropensityCorrectionMode.INVERSE`` -- the production
    default -- returns its reciprocal.
    """

    probe = BackboneWiringProbe.build(seed=SEED)
    transition = probe.transition_for(probe.observed_days()[0])
    opportunity = transition.opportunity
    expected = 1.0 / (
        opportunity.selection_probability
        * opportunity.p_visible_given_state
        * opportunity.p_detect_given_visible
    )
    weight = probe.system.core._corrector.weight_for_opportunity(opportunity)
    assert weight.applied_weight == pytest.approx(expected)
    assert weight.clipped is False
    assert weight.raw_propensity == pytest.approx(
        opportunity.selection_probability
        * opportunity.p_visible_given_state
        * opportunity.p_detect_given_visible
    )


def test_opceu_visibility_intervention_reaches_the_numeric_state_and_the_decision() -> None:
    """Intervention on OPCEU's own input: the detection probability of the opportunity."""

    base_probe, base_core, base_result = _legacy_run(DECODED_FLIP_DAYS)
    probe, core, result = _legacy_run(DECODED_FLIP_DAYS, p_visible_given_state=0.35)

    # handoff: OPCEU's own output moved
    assert result.propensity.applied_weight != pytest.approx(base_result.propensity.applied_weight)
    # numeric state: the Hybrid mass RGRC owns moved
    majority = max(base_probe.case.locations, key=base_core.hybrid_alpha)
    assert core.hybrid_alpha(majority) != pytest.approx(base_core.hybrid_alpha(majority))
    # action distribution and decoded action both moved
    assert _readout(probe)[0] != _readout(base_probe)[0]
    assert _readout(probe)[1] != _readout(base_probe)[1]
    # and PCHMP's posterior did not, because OPCEU does not feed it
    assert dict(result.actor_posterior) == dict(base_result.actor_posterior)


def test_opceu_null_control_a_field_it_never_reads_changes_nothing() -> None:
    base_probe, _, base_result = _legacy_run(DECODED_FLIP_DAYS)
    probe, _, result = _legacy_run(DECODED_FLIP_DAYS, context_key="weekend|away")

    assert result.propensity.applied_weight == pytest.approx(base_result.propensity.applied_weight)
    assert _readout(probe) == _readout(base_probe)


# ---------------------------------------------------------------------------
# ORRER / CHEH
# ---------------------------------------------------------------------------


def test_orrer_unresolved_mass_intervention_moves_the_posterior_and_the_numeric_state() -> None:
    """Intervention on ORRER's own input: the explicit unresolved probability."""

    base_probe, base_core, base_result = _legacy_run(DECODED_FLIP_DAYS)
    probe, core, result = _legacy_run(DECODED_FLIP_DAYS, unresolved_probability=0.6)

    assert base_result.event_posterior.unresolved_probability == pytest.approx(0.0)
    assert result.event_posterior.unresolved_probability > 0.0
    assert dict(result.actor_posterior) != dict(base_result.actor_posterior)
    majority = max(base_probe.case.locations, key=base_core.hybrid_alpha)
    assert core.hybrid_alpha(majority) != pytest.approx(base_core.hybrid_alpha(majority))
    assert _readout(probe)[0] != _readout(base_probe)[0]
    # decoded_action: NOT COVERED -- the trigger condition is not met at this horizon.
    assert _readout(probe)[1] == _readout(base_probe)[1]


def test_orrer_preserves_open_actor_and_unresolved_support_as_an_invariant() -> None:
    """``unknown_actor_support_must_be_preserved`` in the frozen hard-safety kernel."""

    _, _, result = _legacy_run(6, unresolved_probability=0.4)
    assert "unknown_actor" in result.actor_posterior
    assert result.actor_posterior["unknown_actor"] > 0.0
    assert sum(result.actor_posterior.values()) == pytest.approx(1.0)
    assert 0.0 <= result.event_posterior.unresolved_probability <= 1.0
    history = result.event_history
    assert history.latest.revision_id is not None
    assert history.hypothesis_set_id is not None


def test_orrer_null_control_the_same_inputs_reproduce_the_same_hypothesis_set() -> None:
    first_probe, _, first = _legacy_run(6)
    second_probe, _, second = _legacy_run(6)
    assert dict(first.actor_posterior) == dict(second.actor_posterior)
    assert first.event_posterior.unresolved_probability == pytest.approx(
        second.event_posterior.unresolved_probability
    )
    assert _readout(first_probe)[1] == _readout(second_probe)[1]


# ---------------------------------------------------------------------------
# PCHMP
# ---------------------------------------------------------------------------


def test_pchmp_evidence_intervention_reaches_the_numeric_state_and_the_decision() -> None:
    """Intervention on PCHMP's own input: the evidence cluster set it consumes."""

    base_probe, base_core, base_result = _legacy_run(DECODED_FLIP_DAYS)
    probe, core, result = _legacy_run(DECODED_FLIP_DAYS, evidence_filter=())

    assert dict(result.actor_posterior) != dict(base_result.actor_posterior)
    majority = max(base_probe.case.locations, key=base_core.hybrid_alpha)
    assert core.hybrid_alpha(majority) != pytest.approx(base_core.hybrid_alpha(majority))
    assert _readout(probe)[0] != _readout(base_probe)[0]
    assert _readout(probe)[1] != _readout(base_probe)[1]
    # and OPCEU's output did not move, because PCHMP does not feed it
    assert result.propensity.applied_weight == pytest.approx(base_result.propensity.applied_weight)


def test_pchmp_posterior_is_normalized_and_keeps_the_frozen_actor_support() -> None:
    _, _, result = _legacy_run(6)
    assert sum(result.actor_posterior.values()) == pytest.approx(1.0)
    assert set(result.actor_posterior) == {"owner", "guest", "unknown_actor"}
    assert all(0.0 <= value <= 1.0 for value in result.actor_posterior.values())


def test_pchmp_null_control_reordering_the_same_evidence_is_semantically_invariant() -> None:
    """Permuting the same evidence set must not change the decision.

    It is invariant to within floating-point re-association, not bit-for-bit: the
    per-location Hybrid mass and the decoded choice agree, while the exact float
    bits (and therefore ``action_distribution_sha256``) can differ.  That is a
    measured property of this implementation, recorded here rather than asserted
    away, and it is why this control asserts values rather than hashes.
    """

    base_probe, base_core, base_result = _legacy_run(DECODED_FLIP_DAYS)
    probe, core, result = _legacy_run(
        DECODED_FLIP_DAYS, evidence_filter=("role", "mechanism", "actor")
    )

    for actor, value in base_result.actor_posterior.items():
        assert result.actor_posterior[actor] == pytest.approx(value, abs=1e-9)
    for location in base_probe.case.locations:
        assert core.hybrid_alpha(location) == pytest.approx(
            base_core.hybrid_alpha(location), abs=1e-9
        )
    base_distribution = base_probe.action_distribution()
    for location, value in probe.action_distribution().items():
        assert value == pytest.approx(base_distribution[location], abs=1e-9)
    assert _readout(probe)[1] == _readout(base_probe)[1]


# ---------------------------------------------------------------------------
# CF-BOCPD
# ---------------------------------------------------------------------------


def _signal(*, habit: float) -> dict[ChangeCause, float]:
    return {
        ChangeCause.OBSERVATION: 0.02,
        ChangeCause.ACTOR: 0.02,
        ChangeCause.HABIT: habit,
        ChangeCause.NOISE: 0.02,
    }


def _frames(signals: list[dict[ChangeCause, float]]) -> list[CauseSignalFrame]:
    start = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    return [
        CauseSignalFrame(timestamp=start + timedelta(days=index), signals=dict(signal))
        for index, signal in enumerate(signals)
    ]


def test_cf_bocpd_change_probability_responds_to_a_real_signal_shift() -> None:
    """Intervention on CF-BOCPD's own input: the cause signal frame sequence."""

    calm = _signal(habit=0.02)
    shift = _signal(habit=0.95)

    steady = JointCauseFactorizedBOCPD(hazard_probability=0.05)
    shifted = JointCauseFactorizedBOCPD(hazard_probability=0.05)
    steady_snapshot = None
    shifted_snapshot = None
    for frame in _frames([calm] * 6):
        steady_snapshot = steady.observe_online(frame)
    for frame in _frames([calm] * 3 + [shift] * 3):
        shifted_snapshot = shifted.observe_online(frame)

    assert steady_snapshot is not None and shifted_snapshot is not None
    assert shifted_snapshot.segment_change_probability > steady_snapshot.segment_change_probability
    assert (
        shifted_snapshot.segment_cause_posterior[ChangeCause.HABIT]
        > (steady_snapshot.segment_cause_posterior[ChangeCause.HABIT])
    )
    assert sum(shifted_snapshot.segment_cause_posterior.values()) == pytest.approx(1.0)
    assert 0.0 <= shifted_snapshot.segment_change_probability <= 1.0


def test_cf_bocpd_null_control_a_constant_sequence_keeps_the_change_probability_low() -> None:
    calm = _signal(habit=0.02)
    filter_ = JointCauseFactorizedBOCPD(hazard_probability=0.05)
    snapshot = None
    for frame in _frames([calm] * 8):
        snapshot = filter_.observe_online(frame)
    assert snapshot is not None
    assert snapshot.segment_change_probability < 0.5


def test_cf_bocpd_output_is_the_snapshot_ciav_later_reads() -> None:
    """The handoff is a real object identity, not a declared edge."""

    probe = BackboneWiringProbe.build(seed=SEED)
    transition = probe.transition_for(probe.observed_days()[0])
    result, sink = probe.run_direct_p5(transition)
    _, rows = verify_and_flatten(sink)
    cf_bocpd = next(
        row for row in rows if row.operator == "cf_bocpd" and row.phase == "selected_path"
    )
    assert cf_bocpd.callable_symbol.endswith("JointCauseFactorizedBOCPD.observe_online")
    assert probe.system.core.current_cause_snapshot is not None
    assert result.ciav_receipt is not None


# ---------------------------------------------------------------------------
# CCRR
# ---------------------------------------------------------------------------


def test_ccrr_confirmation_window_intervention_changes_the_committed_classification() -> None:
    """Intervention on CCRR's own parameter with identical observation data.

    ``confirmation_window`` is a real CCRR input, not an operator switch: both arms
    run the full seven-operator path with the same data.
    """

    narrow_probe, narrow_core, _ = _legacy_run(
        CCRR_DIVERGENCE_DAYS, loop_config=PrototypeLoopConfig(confirmation_window=2)
    )
    wide_probe, wide_core, _ = _legacy_run(
        CCRR_DIVERGENCE_DAYS, loop_config=PrototypeLoopConfig(confirmation_window=3)
    )

    assert len(narrow_core._committed_events) != len(wide_core._committed_events)
    assert len(narrow_core._quarantined_events) != len(wide_core._quarantined_events)
    moved = [
        location
        for location in narrow_probe.case.locations
        if narrow_core.hybrid_alpha(location) != pytest.approx(wide_core.hybrid_alpha(location))
    ]
    assert moved
    assert _readout(narrow_probe)[0] != _readout(wide_probe)[0]
    # decoded_action: NOT COVERED -- the trigger condition is not met at this horizon.
    assert _readout(narrow_probe)[1] == _readout(wide_probe)[1]


def test_ccrr_null_control_the_same_window_reproduces_the_same_classification() -> None:
    first_probe, first_core, _ = _legacy_run(
        CCRR_DIVERGENCE_DAYS, loop_config=PrototypeLoopConfig(confirmation_window=3)
    )
    second_probe, second_core, _ = _legacy_run(
        CCRR_DIVERGENCE_DAYS, loop_config=PrototypeLoopConfig(confirmation_window=3)
    )
    assert len(first_core._committed_events) == len(second_core._committed_events)
    assert len(first_core._quarantined_events) == len(second_core._quarantined_events)
    assert _readout(first_probe) == _readout(second_probe)


def test_ccrr_only_promotes_after_the_confirmation_window_is_satisfied() -> None:
    """Algorithmic invariant: a candidate must persist before it can create a regime."""

    _, core, _ = _legacy_run(
        CCRR_DIVERGENCE_DAYS, loop_config=PrototypeLoopConfig(confirmation_window=4)
    )
    assert core.active_regime is not None
    # A wider window cannot produce *more* confirmed regime changes than a narrow one.
    _, narrow_core, _ = _legacy_run(
        CCRR_DIVERGENCE_DAYS, loop_config=PrototypeLoopConfig(confirmation_window=2)
    )
    assert len(core._quarantined_events) >= len(narrow_core._quarantined_events)


# ---------------------------------------------------------------------------
# RGRC
# ---------------------------------------------------------------------------


def test_rgrc_hybrid_mass_reconciles_with_the_surviving_committed_events() -> None:
    """Algorithmic invariant of the only long-term write authority."""

    probe, core, _ = _legacy_run(12)
    expected = dict.fromkeys(probe.case.locations, 0.0)
    for event in core._committed_events.values():
        if event.location_id in expected:
            expected[event.location_id] += event.statistical_owner_weight
    for location, value in expected.items():
        assert core.hybrid_alpha(location) == pytest.approx(value, abs=1e-9)
    assert core.verify_hybrid_full_rerun_equivalence().equivalent is True


def test_rgrc_quarantine_gate_keeps_the_adaptive_primary_pass_out_of_long_term_memory() -> None:
    """Null control for RGRC: the adaptive primary pass must not commit."""

    probe = BackboneWiringProbe.build(seed=SEED)
    for observation in probe.observed_days()[:6]:
        transition = probe.transition_for(observation)
        probe.run_direct_p5(
            transition,
            ciav_input=probe.ciav_input(transition, outcome=CIAVOutcomeKind.NOT_DETECTED),
        )
    assert probe.committed_revision_ids() == ()
    assert len(probe.quarantined_revision_ids()) == 6
    for location in probe.case.locations:
        assert probe.system.core.hybrid_alpha(location) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# CIAV
# ---------------------------------------------------------------------------


def test_ciav_owner_likelihood_intervention_moves_the_decoded_choice() -> None:
    """Retained from round one and from the independent review's own probe."""

    from cpswm.system.evaluation_operations.structure_two_p5_readout_posthoc_diagnostic import (
        selected_v0_6_action_readout,
    )

    def run(owner_likelihood: float | None) -> tuple[str, UUID]:
        probe = BackboneWiringProbe.build(seed=SEED, action_readout=selected_v0_6_action_readout())
        days = probe.observed_days()
        for observation in days[:4]:
            warm = probe.transition_for(observation)
            probe.run_direct_p5(
                warm,
                ciav_input=probe.ciav_input(
                    warm, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
                ),
            )
        transition = probe.transition_for(days[4])
        if owner_likelihood is None:
            ciav = probe.ciav_input(transition, outcome=CIAVOutcomeKind.NOT_DETECTED)
        else:
            ciav = probe.ciav_input(
                transition,
                outcome=CIAVOutcomeKind.DETECTED_SAME_LOCATION,
                owner_likelihood=owner_likelihood,
            )
        probe.run_direct_p5(transition, ciav_input=ciav)
        return _readout(probe)

    baseline = run(None)
    confirming = run(0.95)
    contradicting = run(0.05)

    assert confirming == baseline
    assert contradicting[1] != baseline[1]


def test_ciav_null_control_a_privacy_blocked_action_changes_no_state() -> None:
    """Legal execution path: the frozen privacy hard constraint blocks the action."""

    probe = BackboneWiringProbe.build(seed=SEED)
    transition = probe.transition_for(probe.observed_days()[0])
    result, sink = probe.run_direct_p5(
        transition,
        ciav_input=probe.ciav_input(transition, privacy_cost=0.9, privacy_budget=0.1),
    )
    trace, rows = verify_and_flatten(sink)

    assert result.ciav_plan is not None
    assert result.ciav_plan.should_act is False
    assert result.ciav_plan.stop_reason == "privacy_hard_constraint_blocked_all_actions"
    assert result.ciav_receipt is None
    assert result.fast_verification_receipt is None
    assert result.feedback_result is None
    assert len(rows) == 7
    assert trace.feedback_closure_kind == "none"
    assert probe.committed_revision_ids() == ()


# ---------------------------------------------------------------------------
# Binding kind is not algorithmic equivalence
# ---------------------------------------------------------------------------


def test_binding_kind_is_reported_separately_from_algorithmic_equivalence() -> None:
    """Four direct callables, one composite stage, one enclosing stage, one adaptive stage.

    This test asserts only *how* each operator is bound.  It deliberately makes no
    equivalence claim: the equivalence evidence is the formula and invariant tests
    above, and it exists for OPCEU, PCHMP, CF-BOCPD, CCRR and RGRC only.
    """

    probe = BackboneWiringProbe.build(seed=SEED)
    transition = probe.transition_for(probe.observed_days()[0])
    _, sink = probe.run_direct_p5(transition)
    _, rows = verify_and_flatten(sink)
    binding = {row.operator: row.binding_kind for row in rows if row.phase == "selected_path"}
    assert binding == {
        "opceu": "direct_operator_callable",
        "orrer_cheh": "direct_operator_callable",
        "pchmp": "direct_operator_callable",
        "cf_bocpd": "direct_operator_callable",
        "ccrr": "composite_operator_stage",
        "rgrc": "enclosing_runtime_stage",
        "ciav": "adaptive_composite_stage",
    }
