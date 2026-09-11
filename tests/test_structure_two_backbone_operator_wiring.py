"""Mechanism-level scenario matrix for the Structure-Two backbone and seven operators.

Every test states its expected invariants, its expected changes, and what must stay
unchanged.  A correct no-op is asserted as a no-op, never as a failure.  These tests
are engineering wiring evidence only: none of them establishes Task 9 four-coupling
results, seven-operator contribution ablation, router benefit, or scientific
superiority.
"""

from __future__ import annotations

import inspect
from uuid import uuid4

import pytest

from structure_two_backbone_wiring_probe import (
    STRUCTURE_TWO_OPERATOR_ORDER,
    BackboneWiringProbe,
    CIAVOutcomeKind,
    FailingTraceSink,
    closure_operator_sequence,
    primary_operator_sequence,
    verify_and_flatten,
)

from cpswm.system.evaluation_operations.structure_two_p5_readout_posthoc_diagnostic import (
    selected_v0_6_action_readout,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_execution import (
    ADAPTIVE_FEEDBACK_CONSUMPTION_GRAPH,
    ADAPTIVE_PRIMARY_CONSUMPTION_GRAPHS,
    AdaptiveMaintenanceContractError,
)

P0_ROUTER_FEATURES = {"action_margin": 0.9, "regime_hazard": 0.0}


def _p0_features(probe: BackboneWiringProbe):
    return probe.router_features(**P0_ROUTER_FEATURES)


# ---------------------------------------------------------------------------
# S1/S2/S3 -- positive and negative observation, same- and different-location
# ---------------------------------------------------------------------------


def test_positive_observation_different_location_runs_the_full_thirteen_call_closure() -> None:
    """Invariants: seven primary receipts in frozen order plus six closure receipts.

    Expected change: long-term commit becomes reachable and the typed action moves.
    Expected unchanged: the frozen operator order and the registered consumption DAG.
    """

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    before_action = probe.action_distribution_sha256()
    result, sink = probe.run_direct_p5(
        transition,
        ciav_input=probe.ciav_input(
            transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
        ),
    )
    trace, rows = verify_and_flatten(sink)

    assert primary_operator_sequence(rows) == STRUCTURE_TWO_OPERATOR_ORDER
    assert closure_operator_sequence(rows) == STRUCTURE_TWO_OPERATOR_ORDER[:6]
    assert len(rows) == 13
    assert trace.all_seven_operators_invoked is True
    assert trace.ciav_invoked is True
    assert trace.feedback_closure_kind == "full_transition"
    assert result.feedback_result is not None
    assert result.fast_verification_receipt is None
    assert probe.action_distribution_sha256() != before_action
    assert probe.system.pending_adaptive_debts() == ()


def test_same_location_verification_closes_with_one_opceu_receipt_and_no_transition() -> None:
    """Invariant: the same-location closure is exactly one OPCEU fast-verification call.

    Expected change: the reversible fast ledger owner mass.
    Expected unchanged: no second transition, no long-term commit.
    """

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    result, sink = probe.run_direct_p5(
        transition,
        ciav_input=probe.ciav_input(transition, outcome=CIAVOutcomeKind.DETECTED_SAME_LOCATION),
    )
    trace, rows = verify_and_flatten(sink)

    assert len(rows) == 8
    assert closure_operator_sequence(rows) == ("opceu",)
    assert trace.feedback_closure_kind == "same_location_fast_verification"
    assert result.feedback_result is None
    assert result.fast_verification_receipt is not None
    assert result.fast_verification_receipt.changed is True
    assert probe.committed_revision_ids() == ()


def test_negative_observation_stops_at_seven_receipts_and_leaves_no_partial_closure() -> None:
    """Invariant: an undetected CIAV observation produces no feedback closure at all.

    Expected change: none downstream of CIAV.
    Expected unchanged: closure kind ``none``, no closure receipts, no commit.

    This is a *correct* no-op at trace level.  It is also the measurable form of the
    registered open gap: the CIAV actor posterior is computed and then discarded.
    """

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    result, sink = probe.run_direct_p5(
        transition,
        ciav_input=probe.ciav_input(transition, outcome=CIAVOutcomeKind.NOT_DETECTED),
    )
    trace, rows = verify_and_flatten(sink)

    assert len(rows) == 7
    assert closure_operator_sequence(rows) == ()
    assert trace.feedback_closure_kind == "none"
    assert trace.feedback_observation_acquired is False
    assert result.feedback_result is None
    assert result.fast_verification_receipt is None
    assert result.ciav_receipt is not None

    ciav_owner = result.ciav_receipt.evidence.actor_posterior[probe.case.owner_actor]
    primary_owner = result.primary_result.actor_posterior[probe.case.owner_actor]
    assert ciav_owner != pytest.approx(primary_owner)


def test_negative_and_same_location_closures_differ_in_state_but_not_in_committed_memory() -> None:
    """Both branches leave long-term memory untouched; only the fast ledger differs."""

    outcomes = {}
    for kind in (CIAVOutcomeKind.DETECTED_SAME_LOCATION, CIAVOutcomeKind.NOT_DETECTED):
        probe = BackboneWiringProbe.build(seed=7)
        transition = probe.transition_for(probe.observed_days()[0])
        probe.run_direct_p5(transition, ciav_input=probe.ciav_input(transition, outcome=kind))
        outcomes[kind] = (
            probe.observable_state_sha256(),
            len(probe.system.core.fast_action_verification_receipts),
            len(probe.committed_revision_ids()),
        )
    same = outcomes[CIAVOutcomeKind.DETECTED_SAME_LOCATION]
    negative = outcomes[CIAVOutcomeKind.NOT_DETECTED]
    assert same[1] == 1 and negative[1] == 0
    assert same[2] == negative[2] == 0


# ---------------------------------------------------------------------------
# S4 -- CIAV verification really reaches the typed action, through one threshold
# ---------------------------------------------------------------------------


def test_same_location_verification_moves_the_action_only_across_the_owner_mass_floor() -> None:
    """The fast-verification channel is wired, but the readout is threshold-valued.

    Expected change: the fast-ledger owner mass changes for every likelihood.
    Expected unchanged: the typed action, unless the verified mass crosses
    ``fast_owner_mass_floor``.  Treating the sub-threshold case as a defect would be
    wrong: ``_latest_owner_event_component`` normalizes each component, so a scalar
    rescale of a one-hot component is provably invisible.
    """

    def run(owner_likelihood: float):
        probe = BackboneWiringProbe.build(seed=7, action_readout=selected_v0_6_action_readout())
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
        probe.run_direct_p5(
            transition,
            ciav_input=probe.ciav_input(
                transition,
                outcome=CIAVOutcomeKind.DETECTED_SAME_LOCATION,
                owner_likelihood=owner_likelihood,
            ),
        )
        return probe

    def baseline():
        probe = BackboneWiringProbe.build(seed=7, action_readout=selected_v0_6_action_readout())
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
        probe.run_direct_p5(
            transition,
            ciav_input=probe.ciav_input(transition, outcome=CIAVOutcomeKind.NOT_DETECTED),
        )
        return probe

    reference = baseline().action_distribution_sha256()

    above = run(0.95)
    assert above.system.core.fast_action_verification_receipts[-1].changed is True
    assert above.action_distribution_sha256() == reference

    below = run(0.05)
    receipt = below.system.core.fast_action_verification_receipts[-1]
    assert receipt.owner_mass_before >= 0.5 > receipt.owner_mass_after
    assert below.action_distribution_sha256() != reference


# ---------------------------------------------------------------------------
# S5/S6 -- multi-person ambiguity and open-world unknown actors
# ---------------------------------------------------------------------------


def test_open_actor_support_is_preserved_end_to_end_and_support_drift_is_refused() -> None:
    """Invariant: the open actor support survives PCHMP, CIAV and the closure."""

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    result, _ = probe.run_direct_p5(transition)

    assert set(result.primary_result.actor_posterior) == set(transition.actor_prior)
    assert result.primary_result.actor_posterior["unknown_actor"] > 0.0
    assert result.ciav_receipt is not None
    assert set(result.ciav_receipt.evidence.actor_posterior) == set(transition.actor_prior)

    narrowed = probe.transition_for(
        probe.observed_days()[1],
        actor_prior={probe.case.owner_actor: 0.6, probe.case.guest_actor: 0.4},
    )
    with pytest.raises(RuntimeError, match="actor posterior support drifted before CIAV"):
        probe.run_direct_p5(narrowed)


def test_unknown_actor_mass_survives_a_full_open_world_timeline() -> None:
    """An unknown-actor day must keep real unknown mass, not collapse to a resident."""

    probe = BackboneWiringProbe.build(
        seed=7, include_open_world_unknown_events=True, unknown_event_days=(1,)
    )
    unknown_masses = []
    for observation in probe.observed_days()[:6]:
        transition = probe.transition_for(observation)
        result, _ = probe.run_direct_p5(
            transition,
            ciav_input=probe.ciav_input(transition, outcome=CIAVOutcomeKind.NOT_DETECTED),
        )
        unknown_masses.append(result.primary_result.actor_posterior["unknown_actor"])

    assert min(unknown_masses) > 0.0
    assert max(unknown_masses) > 0.5


# ---------------------------------------------------------------------------
# S7 -- phase change and history-state restoration through the production path
# ---------------------------------------------------------------------------


def test_regime_creation_and_reactivation_happen_on_the_production_direct_p5_path() -> None:
    """Invariant: CCRR creates a new regime on an abrupt shift and reactivates the old one.

    Expected change: ``active_regime`` moves stable -> created -> created -> reactivated.
    Expected unchanged: the reactivated regime id is an *earlier* id, not a fresh one.
    """

    probe = BackboneWiringProbe.build(
        seed=7, include_open_world_unknown_events=True, unknown_event_days=(1,)
    )
    timeline = []
    for observation in probe.observed_days():
        transition = probe.transition_for(observation)
        result, _ = probe.run_direct_p5(
            transition,
            ciav_input=probe.ciav_input(transition, outcome=CIAVOutcomeKind.NOT_DETECTED),
        )
        timeline.append(
            (observation.day, probe.system.core.active_regime, result.primary_result.decision)
        )

    switches = [
        row for index, row in enumerate(timeline) if index == 0 or row[1] != timeline[index - 1][1]
    ]
    kinds = [row[2].ccrr_conclusion for row in switches]
    regimes = [row[1] for row in switches]

    assert "create" in kinds
    assert "reactivate" in kinds
    reactivation_index = kinds.index("reactivate")
    assert regimes[reactivation_index] in regimes[:reactivation_index]


# ---------------------------------------------------------------------------
# S8 -- retraction leaves no stale contribution and no double count
# ---------------------------------------------------------------------------


def test_retracting_a_promoted_revision_removes_its_contribution_exactly_once() -> None:
    """Invariants: full-rerun equivalence holds before, after, and after a repeat."""

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    for observation in probe.observed_days()[:12]:
        core.process_transition(probe.transition_for(observation))

    assert core.verify_hybrid_full_rerun_equivalence().equivalent is True
    before_action = probe.action_distribution_sha256()

    ledger = core._hybrid_loop.ledger
    target = core._committed_events[next(reversed(core._committed_events))]
    revision = target.hybrid_revision_id or target.revision_id
    assert len(ledger.live_promoted_records_for_revision(revision)) == 1

    core._hybrid_loop.retract_revision(revision)
    assert ledger.live_promoted_records_for_revision(revision) == ()
    assert core.verify_hybrid_full_rerun_equivalence().equivalent is True
    after_action = probe.action_distribution_sha256()
    assert after_action != before_action

    core._hybrid_loop.retract_revision(revision)
    assert core.verify_hybrid_full_rerun_equivalence().equivalent is True
    assert probe.action_distribution_sha256() == after_action


# ---------------------------------------------------------------------------
# S9 -- P0 debt, replay, duplicate replay, concurrent debt, stale features
# ---------------------------------------------------------------------------


def test_p0_defers_orrer_and_ciav_behind_exactly_one_bound_debt_certificate() -> None:
    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    result, sink = probe.run_adaptive(
        transition, features=_p0_features(probe), debt_expiry_steps=1
    )
    trace, rows = verify_and_flatten(sink)

    assert result.path_selection.selected_path_id == "P0_SAFE_DEFERRED"
    assert primary_operator_sequence(rows) == STRUCTURE_TWO_OPERATOR_ORDER
    assert [row.status for row in rows] == [
        "executed",
        "deferred",
        "executed",
        "executed",
        "executed",
        "executed",
        "deferred",
    ]
    assert len(result.debt_certificates) == 1
    assert result.debt_certificates[0].origin_transition_sha256 == content_sha256(transition)
    assert probe.committed_revision_ids() == ()


def test_expired_debt_replay_runs_p5_settles_once_and_refuses_a_repeat() -> None:
    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    ciav_input = probe.ciav_input(transition)
    deferred, _ = probe.run_adaptive(
        transition,
        ciav_input=ciav_input,
        features=_p0_features(probe),
        debt_expiry_steps=1,
    )
    debt = deferred.debt_certificates[0]

    replayed, sink = probe.replay_debt(debt.debt_id, ciav_input=ciav_input)
    trace, rows = verify_and_flatten(sink)

    assert replayed.path_selection.selected_path_id == "P5_FULL_EAGER"
    assert trace.replayed_debt_certificates == (debt,)
    assert trace.all_seven_operators_invoked is True
    assert probe.system.pending_adaptive_debts() == ()

    with pytest.raises(ValueError, match="adaptive debt is not pending"):
        probe.replay_debt(debt.debt_id, ciav_input=ciav_input)


def test_pending_debt_blocks_every_other_production_entrypoint() -> None:
    probe = BackboneWiringProbe.build(seed=7)
    days = probe.observed_days()
    first = probe.transition_for(days[0])
    deferred, _ = probe.run_adaptive(
        first,
        ciav_input=probe.ciav_input(first),
        features=_p0_features(probe),
        debt_expiry_steps=1,
    )
    second = probe.transition_for(days[1])

    with pytest.raises(RuntimeError, match="pending adaptive debt must be resolved"):
        probe.run_adaptive(second)
    with pytest.raises(RuntimeError, match="cannot run while adaptive debt is pending"):
        probe.run_direct_p5(second)
    with pytest.raises(ValueError, match="CIAV input commitment mismatch"):
        probe.replay_debt(
            deferred.debt_certificates[0].debt_id,
            ciav_input=probe.ciav_input(first, owner_likelihood=0.3),
        )


def test_a_stale_router_feature_snapshot_is_refused() -> None:
    probe = BackboneWiringProbe.build(seed=7)
    days = probe.observed_days()
    stale = probe.router_features()
    first = probe.transition_for(days[0])
    probe.run_direct_p5(first)

    second = probe.transition_for(days[1])
    with pytest.raises(ValueError, match="stale or foreign"):
        probe.run_direct_p5(second, features=stale)


def test_direct_p5_and_debt_replay_agree_on_every_semantic_quantity() -> None:
    """Equivalence is asserted on semantic quantities only.

    ``_execution_observable_state_sha256`` embeds ``uuid4`` record ids, so it differs
    between two *identical* runs and can never serve as a cross-run witness.
    """

    def direct():
        probe = BackboneWiringProbe.build(seed=7)
        transition = probe.transition_for(probe.observed_days()[0])
        result, _ = probe.run_direct_p5(transition, ciav_input=probe.ciav_input(transition))
        return probe, result

    def replay():
        probe = BackboneWiringProbe.build(seed=7)
        transition = probe.transition_for(probe.observed_days()[0])
        ciav_input = probe.ciav_input(transition)
        deferred, _ = probe.run_adaptive(
            transition,
            ciav_input=ciav_input,
            features=_p0_features(probe),
            debt_expiry_steps=1,
        )
        result, _ = probe.replay_debt(
            deferred.debt_certificates[0].debt_id, ciav_input=ciav_input
        )
        return probe, result

    direct_probe, direct_result = direct()
    replay_probe, replay_result = replay()

    assert dict(direct_result.primary_result.actor_posterior) == dict(
        replay_result.primary_result.actor_posterior
    )
    assert direct_probe.action_distribution_sha256() == replay_probe.action_distribution_sha256()
    assert (
        direct_probe.system.core._habit.canonical_state_hash()
        == replay_probe.system.core._habit.canonical_state_hash()
    )
    assert direct_probe.system.core.active_regime == replay_probe.system.core.active_regime


def test_observable_state_identity_is_run_local_and_not_reproducible() -> None:
    """Negative control for the equivalence test above."""

    def once() -> tuple[str, str]:
        probe = BackboneWiringProbe.build(seed=7)
        transition = probe.transition_for(probe.observed_days()[0])
        probe.run_direct_p5(transition)
        return probe.observable_state_sha256(), probe.action_distribution_sha256()

    first, second = once(), once()
    assert first[1] == second[1]
    assert first[0] != second[0]


# ---------------------------------------------------------------------------
# S10 -- failure rollback
# ---------------------------------------------------------------------------


def test_a_refused_trace_commit_rolls_the_model_back_completely() -> None:
    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    before_state = probe.observable_state_sha256()
    before_action = probe.action_distribution_sha256()

    with pytest.raises(RuntimeError, match="refused the commit"):
        probe.run_direct_p5(transition, sink=FailingTraceSink())

    assert probe.observable_state_sha256() == before_state
    assert probe.action_distribution_sha256() == before_action
    assert probe.committed_revision_ids() == ()
    assert probe.quarantined_revision_ids() == ()


# ---------------------------------------------------------------------------
# S11 -- declared consumption versus real consumption
# ---------------------------------------------------------------------------


def test_p5_declared_consumption_matches_the_frozen_graph_on_both_phases() -> None:
    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    _, sink = probe.run_direct_p5(
        transition,
        ciav_input=probe.ciav_input(
            transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
        ),
    )
    _, rows = verify_and_flatten(sink)

    primary_graph = ADAPTIVE_PRIMARY_CONSUMPTION_GRAPHS["P5_FULL_EAGER"]
    for row in rows:
        if row.phase == "selected_path":
            expected = tuple(
                f"selected_path:{name}" for name in primary_graph[row.operator]
            )
        else:
            expected = tuple(
                ("selected_path:ciav" if name == "ciav" else f"feedback_closure:{name}")
                for name in ADAPTIVE_FEEDBACK_CONSUMPTION_GRAPH[row.operator]
            )
        assert row.consumed_producers == expected


def test_p0_downstream_maintenance_checks_its_declared_upstream_dependency() -> None:
    """The frozen P0 graph declares ``ccrr <- cf_bocpd`` and ``rgrc <- (pchmp, ccrr)``.

    Round one asserted the wrong property here: that a *different* upstream payload
    produces a different downstream body.  The frozen
    ``hard_safety_kernel.provenance_and_dependency_checks_always_executed`` clause
    requires a *check*, so a payload that disagrees with live runtime state must be
    refused rather than silently reshaping the receipt.  The full rejection matrix
    lives in ``tests/test_structure_two_backbone_counterexample_regressions.py``.
    """

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core

    ccrr_parameters = list(
        inspect.signature(core._adaptive_ccrr_safety_maintenance).parameters
    )
    rgrc_parameters = list(inspect.signature(core._adaptive_rgrc_debt_guard).parameters)
    assert ccrr_parameters == ["cf_bocpd_maintenance"]
    assert rgrc_parameters == ["pchmp_maintenance", "ccrr_maintenance"]

    clean = core._adaptive_cf_bocpd_safety_maintenance()
    assert core._adaptive_ccrr_safety_maintenance(clean)["maintenance_kind"] == (
        "ccrr_safety_maintenance"
    )
    with pytest.raises(AdaptiveMaintenanceContractError):
        core._adaptive_ccrr_safety_maintenance({**clean, "posterior_advanced": True})

    transition = probe.transition_for(probe.observed_days()[0])
    pchmp = core._adaptive_pchmp_safety_maintenance(transition)
    ccrr = core._adaptive_ccrr_safety_maintenance(clean)
    assert core._adaptive_rgrc_debt_guard(pchmp, ccrr)["long_term_write_authorized"] is False
    with pytest.raises(AdaptiveMaintenanceContractError):
        core._adaptive_rgrc_debt_guard(
            {**pchmp, "unexecuted_inference_encoded_as_negative": True}, ccrr
        )


def test_p0_receipts_are_reproducible_from_the_checked_dependency_chain() -> None:
    """Each P0 maintenance receipt must be recomputable from its declared upstream.

    This is the end-to-end form: replay the chain
    ``cf_bocpd -> ccrr`` and ``(pchmp, ccrr) -> rgrc`` against the same runtime and
    check every recomputed body reproduces the sealed ``output_payload_sha256``.
    """

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    _, sink = probe.run_adaptive(
        transition, features=_p0_features(probe), debt_expiry_steps=1
    )
    _, rows = verify_and_flatten(sink)
    by_operator = {row.operator: row for row in rows}

    core = probe.system.core
    cf_bocpd_output = core._adaptive_cf_bocpd_safety_maintenance()
    pchmp_output = core._adaptive_pchmp_safety_maintenance(transition)
    ccrr_output = core._adaptive_ccrr_safety_maintenance(cf_bocpd_output)
    rgrc_output = core._adaptive_rgrc_debt_guard(pchmp_output, ccrr_output)

    assert content_sha256(cf_bocpd_output) == by_operator["cf_bocpd"].output_payload_sha256
    assert content_sha256(pchmp_output) == by_operator["pchmp"].output_payload_sha256
    assert content_sha256(ccrr_output) == by_operator["ccrr"].output_payload_sha256
    assert content_sha256(rgrc_output) == by_operator["rgrc"].output_payload_sha256

    # The recorded raw_input must name the same upstream hashes the chain produced.
    assert ccrr_output["consumed_cf_bocpd_maintenance_sha256"] == content_sha256(cf_bocpd_output)
    assert rgrc_output["consumed_ccrr_maintenance_sha256"] == content_sha256(ccrr_output)


# ---------------------------------------------------------------------------
# S12 -- runtime assembly: held instances are not evidence of invocation
# ---------------------------------------------------------------------------


def test_every_production_entrypoint_leaves_the_feedback_revision_loop_uninvoked() -> None:
    """``feedback_revision_loop`` is a declared ORRER_CHEH instance that is never called.

    This test pins the current wiring so the gap cannot silently change state:
    driving P0, direct P5, and debt replay leaves the loop's caches empty.
    """

    probe = BackboneWiringProbe.build(seed=7)
    loop = probe.system.feedback_revision_loop
    days = probe.observed_days()

    first = probe.transition_for(days[0])
    probe.run_direct_p5(first, ciav_input=probe.ciav_input(first))

    second = probe.transition_for(days[1])
    ciav_input = probe.ciav_input(second)
    deferred, _ = probe.run_adaptive(
        second, ciav_input=ciav_input, features=_p0_features(probe), debt_expiry_steps=1
    )
    probe.replay_debt(deferred.debt_certificates[0].debt_id, ciav_input=ciav_input)

    assert loop._outcomes == {}
    assert loop._projector._seen == {}


def test_the_declared_orrer_cheh_instances_are_two_distinct_revision_engines() -> None:
    """The declared ORRER_CHEH instance tuple does not have a single engine identity."""

    probe = BackboneWiringProbe.build(seed=7)
    instances = probe.system.runtime_operator_instances()
    engine, feedback_loop = instances["orrer_cheh"]

    assert engine is probe.system.core._event_engine
    assert feedback_loop is probe.system.feedback_revision_loop
    assert feedback_loop._engine is not probe.system.core._event_engine
    assert feedback_loop._message_passing is not probe.system.core._message_passing


def test_only_the_first_declared_instance_of_each_operator_is_identity_checked() -> None:
    """Extra declared instances are neither identity-checked nor receipted."""

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    _, sink = probe.run_direct_p5(transition)
    _, rows = verify_and_flatten(sink)

    symbols = {
        row.operator: row.implementation_symbol for row in rows if row.phase == "selected_path"
    }
    assert symbols["orrer_cheh"].endswith(
        "OpenWorldRoleConditionedReversibleEventRevisionEngine"
    )
    instances = probe.system.runtime_operator_instances()
    assert len(instances["orrer_cheh"]) == 2


def test_rgrc_is_receipted_as_an_enclosing_runtime_stage_not_a_direct_callable() -> None:
    """Algorithmic-implementation-equivalence boundary for RGRC and CCRR."""

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    _, sink = probe.run_direct_p5(transition)
    _, rows = verify_and_flatten(sink)
    kinds = {
        row.operator: (row.binding_kind, row.callable_symbol)
        for row in rows
        if row.phase == "selected_path"
    }

    assert kinds["opceu"][0] == "direct_operator_callable"
    assert kinds["orrer_cheh"][0] == "direct_operator_callable"
    assert kinds["pchmp"][0] == "direct_operator_callable"
    assert kinds["cf_bocpd"][0] == "direct_operator_callable"
    assert kinds["ccrr"][0] == "composite_operator_stage"
    assert kinds["rgrc"][0] == "enclosing_runtime_stage"
    assert kinds["rgrc"][1].endswith("CorePrototypeSpine._process_transition")
    assert kinds["ciav"][0] == "adaptive_composite_stage"


# ---------------------------------------------------------------------------
# S13 -- long-term consolidation reachability on the adaptive lane
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "expect_commits"),
    [
        (CIAVOutcomeKind.DETECTED_SAME_LOCATION, False),
        (CIAVOutcomeKind.NOT_DETECTED, False),
        (CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION, True),
    ],
)
def test_long_term_consolidation_on_the_adaptive_lane_needs_a_different_location_closure(
    outcome: CIAVOutcomeKind, expect_commits: bool
) -> None:
    """Every adaptive primary pass sets ``force_long_term_write_blocked``.

    The only unblocked transition on an adaptive path is the different-location CIAV
    feedback closure, so a confirming (same-location) verification and an undetected
    verification both leave long-term memory empty over a full timeline.
    """

    probe = BackboneWiringProbe.build(seed=7)
    for observation in probe.observed_days()[:14]:
        transition = probe.transition_for(observation)
        probe.run_direct_p5(
            transition, ciav_input=probe.ciav_input(transition, outcome=outcome)
        )

    committed = len(probe.committed_revision_ids())
    quarantined = len(probe.quarantined_revision_ids())
    assert (committed > 0) is expect_commits
    if not expect_commits:
        assert quarantined == 14


def test_the_legacy_ordinary_lane_still_consolidates_the_same_timeline() -> None:
    """Contrast control: the same observations commit on the untraced legacy lane."""

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    for observation in probe.observed_days()[:14]:
        core.process_transition(probe.transition_for(observation))

    assert len(probe.committed_revision_ids()) >= 12
    assert probe.quarantined_revision_ids() == ()
    assert core.verify_hybrid_full_rerun_equivalence().equivalent is True


# ---------------------------------------------------------------------------
# S14 -- duplicate feedback is idempotent
# ---------------------------------------------------------------------------


def test_repeating_the_same_fast_verification_is_an_exactly_once_no_op() -> None:
    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    result, _ = probe.run_direct_p5(
        transition,
        ciav_input=probe.ciav_input(transition, outcome=CIAVOutcomeKind.DETECTED_SAME_LOCATION),
    )
    first = result.fast_verification_receipt
    assert first is not None

    core = probe.system.core
    action_after_first = probe.action_distribution_sha256()
    repeat = core.apply_fast_action_verification(
        revision_id=first.revision_id,
        verified_owner_probability=first.owner_mass_after,
        source_record_id=first.source_record_id,
    )
    assert repeat.changed is False
    assert repeat.receipt_id == first.receipt_id
    assert probe.action_distribution_sha256() == action_after_first

    with pytest.raises(KeyError):
        core.apply_fast_action_verification(
            revision_id=uuid4(),
            verified_owner_probability=0.5,
            source_record_id=first.source_record_id,
        )
