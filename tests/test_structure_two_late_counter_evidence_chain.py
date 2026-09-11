"""R3: late counter-evidence through the formal production entrypoint, end to end.

Round one's S8 called ``core._hybrid_loop.retract_revision`` directly and therefore
only established that one sub-ledger is idempotent.  These tests go through
``CorePrototypeSpine.process_execution_feedback`` -- the public, serialized
production entrypoint that validates the feedback/revision binding, projects the
likelihood evidence, runs the pluggable interpretation policy and dispatches
``apply_event_revision_outcome``.  No private sub-ledger call stands in for it.

``DefaultPrototypeFeedbackPolicy`` documents that "a caller may plug in a calibrated
policy that emits RETRACT or CORRECT", and ``process_execution_feedback`` takes that
policy as a named argument, so supplying ``CalibratedRetractionPolicy`` uses the
documented seam rather than bypassing it.

Reconciliation reference: ``hybrid_alpha(L)`` is compared against the sum of the
*surviving committed events'* ``statistical_owner_weight`` at ``L``.  That reference
is rebuilt from the committed event set, not recomputed from the same mutated
sub-ledger, so residue and double counting both break it.

Engineering evidence only.  No scientific gate, no long-term utility claim.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from structure_two_backbone_wiring_probe import (
    NEGATIVE_ABSENT_LIKELIHOOD,
    NEGATIVE_PRESENT_LIKELIHOOD,
    NEGATIVE_SEARCH_OUTCOME,
    BackboneWiringProbe,
    CalibratedRetractionPolicy,
    CIAVOutcomeKind,
    build_execution_feedback_bundle,
)

from cpswm.system.continual.project_one_regime_loop import PrototypeStatisticOperation

RETRACTION_POLICY = CalibratedRetractionPolicy(retraction_delta=-0.2)
TOLERANCE = 1e-9


def _top(distribution: dict[UUID, float]) -> UUID:
    return min(distribution, key=lambda key: (-distribution[key], str(key)))


def _legacy_history(days: int = 12, **build: Any) -> BackboneWiringProbe:
    probe = BackboneWiringProbe.build(seed=7, **build)
    for observation in probe.observed_days()[:days]:
        probe.system.core.process_transition(probe.transition_for(observation))
    return probe


def _independent_alpha_reference(probe: BackboneWiringProbe) -> dict[UUID, float]:
    """Rebuild the expected Hybrid mass from the surviving committed events."""

    totals = dict.fromkeys(probe.case.locations, 0.0)
    for event in probe.system.core._committed_events.values():
        if event.location_id in totals:
            totals[event.location_id] += event.statistical_owner_weight
    return totals


def _assert_reconciled(probe: BackboneWiringProbe) -> None:
    core = probe.system.core
    reference = _independent_alpha_reference(probe)
    for location, expected in reference.items():
        assert core.hybrid_alpha(location) == pytest.approx(expected, abs=TOLERANCE)
    assert core.verify_hybrid_full_rerun_equivalence().equivalent is True


def _semantic_state(probe: BackboneWiringProbe) -> dict[str, Any]:
    """Every statistically meaningful quantity, excluding object identity."""

    core = probe.system.core
    return {
        "habit": core._habit.canonical_state_hash(),
        "committed": tuple(sorted(str(key) for key in core._committed_events)),
        "observed": tuple(sorted(str(key) for key in core._observed_events)),
        "quarantined": len(core._quarantined_events),
        "alpha": tuple(round(core.hybrid_alpha(item), 12) for item in probe.case.locations),
        "action": probe.action_distribution_sha256(),
        "ledger_log": len(core._hybrid_loop.ledger._log),
        "map_version": core.current_snapshot.map_version,
        "bindings": len(core._revision_feedback_bindings),
        "seen": tuple(
            sorted(
                (str(key), value)
                for key, value in core._hybrid_loop._feedback_projector._seen.items()
            )
        ),
        "lifecycle": tuple(
            sorted((str(key), value.value) for key, value in core._derived_event_lifecycle.items())
        ),
    }


def _counter_evidence(
    probe: BackboneWiringProbe,
    revision_id: UUID,
    *,
    belief_snapshot_id: UUID | None = None,
    **overrides: Any,
):
    event = probe.system.core._committed_events[revision_id]
    return build_execution_feedback_bundle(
        probe,
        revision_id=revision_id,
        location_id=event.location_id,
        belief_snapshot_id=belief_snapshot_id or event.belief_snapshot_id,
        when=event.evidence.event_time,
        outcome_distribution=NEGATIVE_SEARCH_OUTCOME,
        present_likelihood=NEGATIVE_PRESENT_LIKELIHOOD,
        absent_likelihood=NEGATIVE_ABSENT_LIKELIHOOD,
        opportunity_id=event.evidence.observation_opportunity_id,
        **overrides,
    )


def _retract_one_at(probe: BackboneWiringProbe, location: UUID):
    """Retract one committed lineage at ``location`` through the formal entrypoint.

    Returns the revision id, the result, and the exact statistical contribution the
    retracted event carried.  The contribution is read from the event itself rather
    than hard-coded, so the reconciliation stays exact across dependency versions.
    """

    core = probe.system.core
    revision_id = next(
        key
        for key, event in core._committed_events.items()
        if event.location_id == location and event.belief_snapshot_id is not None
    )
    weight = core._committed_events[revision_id].statistical_owner_weight
    feedback, binding, likelihood = _counter_evidence(probe, revision_id)
    result = core.process_execution_feedback(
        feedback=feedback, binding=binding, likelihood_model=likelihood, policy=RETRACTION_POLICY
    )
    return revision_id, result, weight


# ---------------------------------------------------------------------------
# The chain itself
# ---------------------------------------------------------------------------


def test_formal_counter_evidence_removes_exactly_one_lineage_and_reconciles() -> None:
    """One retraction removes one lineage's contribution, and nothing else's."""

    probe = _legacy_history()
    core = probe.system.core
    _assert_reconciled(probe)

    target_location = max(probe.case.locations, key=core.hybrid_alpha)
    before_alpha = dict.fromkeys(probe.case.locations, 0.0)
    before_alpha.update({item: core.hybrid_alpha(item) for item in probe.case.locations})
    before_committed = set(core._committed_events)
    before_map = core.current_snapshot.map_version
    # Journal the expected answer BEFORE the mutation, from the pre-retraction
    # state, so the assertion below never reads the system's own final set.
    assert core._quarantined_events == [], "legacy history must start with no quarantine"

    revision_id, result, event_weight = _retract_one_at(probe, target_location)

    assert result.statistic_operations == (PrototypeStatisticOperation.RETRACT,)
    assert revision_id not in core._committed_events
    assert revision_id not in core._observed_events
    assert core._hybrid_loop.ledger.live_promoted_records_for_revision(revision_id) == ()
    # Round two asserted ``A <= B | A`` here, which is a tautology.  With nothing
    # quarantined beforehand there is nothing a rebuild could legitimately promote,
    # so the surviving set is exactly the journalled set minus the retracted one.
    assert set(core._committed_events) == before_committed - {revision_id}
    assert core.hybrid_alpha(target_location) == pytest.approx(
        before_alpha[target_location] - event_weight, abs=1e-6
    )
    for other in probe.case.locations:
        if other == target_location:
            continue
        assert core.hybrid_alpha(other) == pytest.approx(before_alpha[other], abs=1e-6)
    assert core.current_snapshot.map_version > before_map
    _assert_reconciled(probe)


def test_repeated_counter_evidence_never_double_counts_and_stays_reconciled() -> None:
    """Six successive formal retractions subtract six contributions, no more, no less."""

    probe = _legacy_history()
    core = probe.system.core
    target_location = max(probe.case.locations, key=core.hybrid_alpha)
    start = core.hybrid_alpha(target_location)
    removed = 0.0

    for _ in range(6):
        revision_id, result, weight = _retract_one_at(probe, target_location)
        assert result.statistic_operations == (PrototypeStatisticOperation.RETRACT,)
        removed += weight
        assert core.hybrid_alpha(target_location) == pytest.approx(start - removed, abs=1e-6)
        assert core._hybrid_loop.ledger.live_promoted_records_for_revision(revision_id) == ()
        _assert_reconciled(probe)


def test_an_identical_counter_evidence_replay_is_an_idempotent_no_op() -> None:
    probe = _legacy_history()
    core = probe.system.core
    target_location = max(probe.case.locations, key=core.hybrid_alpha)
    revision_id = next(
        key for key, event in core._committed_events.items() if event.location_id == target_location
    )
    feedback, binding, likelihood = _counter_evidence(probe, revision_id)

    first = core.process_execution_feedback(
        feedback=feedback, binding=binding, likelihood_model=likelihood, policy=RETRACTION_POLICY
    )
    after_first = _semantic_state(probe)
    second = core.process_execution_feedback(
        feedback=feedback, binding=binding, likelihood_model=likelihood, policy=RETRACTION_POLICY
    )

    assert first.statistic_operations == (PrototypeStatisticOperation.RETRACT,)
    assert second.statistic_operations == (PrototypeStatisticOperation.QUARANTINE,)
    assert "idempotent" in second.rationale
    assert _semantic_state(probe) == after_first
    _assert_reconciled(probe)


def test_counter_evidence_citing_an_already_retracted_revision_is_refused_cleanly() -> None:
    """Out-of-order arrival: a second, distinct record citing a dead revision."""

    probe = _legacy_history()
    core = probe.system.core
    target_location = max(probe.case.locations, key=core.hybrid_alpha)
    revision_id = next(
        key for key, event in core._committed_events.items() if event.location_id == target_location
    )
    stale_snapshot = core._committed_events[revision_id].belief_snapshot_id
    stale_location = core._committed_events[revision_id].location_id
    stale_opportunity = core._committed_events[revision_id].evidence.observation_opportunity_id
    stale_time = core._committed_events[revision_id].evidence.event_time

    first, binding, likelihood = _counter_evidence(probe, revision_id)
    core.process_execution_feedback(
        feedback=first, binding=binding, likelihood_model=likelihood, policy=RETRACTION_POLICY
    )
    before = _semantic_state(probe)

    late, late_binding, late_likelihood = build_execution_feedback_bundle(
        probe,
        revision_id=revision_id,
        location_id=stale_location,
        belief_snapshot_id=stale_snapshot,
        when=stale_time,
        outcome_distribution=NEGATIVE_SEARCH_OUTCOME,
        present_likelihood=NEGATIVE_PRESENT_LIKELIHOOD,
        absent_likelihood=NEGATIVE_ABSENT_LIKELIHOOD,
        opportunity_id=stale_opportunity,
    )
    with pytest.raises(KeyError, match="superseded revision is not a committed"):
        core.process_execution_feedback(
            feedback=late,
            binding=late_binding,
            likelihood_model=late_likelihood,
            policy=RETRACTION_POLICY,
        )

    assert _semantic_state(probe) == before
    _assert_reconciled(probe)


def test_counter_evidence_bound_to_a_superseded_snapshot_is_refused_cleanly() -> None:
    """A late record still carrying the pre-revision snapshot must not apply."""

    probe = _legacy_history()
    core = probe.system.core
    target_location = max(probe.case.locations, key=core.hybrid_alpha)
    revisions = [
        key for key, event in core._committed_events.items() if event.location_id == target_location
    ]
    superseded_snapshot = core._committed_events[revisions[0]].belief_snapshot_id

    _retract_one_at(probe, target_location)
    before = _semantic_state(probe)

    feedback, binding, likelihood = _counter_evidence(
        probe, revisions[1], belief_snapshot_id=superseded_snapshot
    )
    with pytest.raises(ValueError, match="snapshot does not match the committed event"):
        core.process_execution_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood,
            policy=RETRACTION_POLICY,
        )

    assert _semantic_state(probe) == before
    _assert_reconciled(probe)


def test_a_partial_failure_mid_revision_restores_every_statistical_quantity() -> None:
    """Fault injected at the Dirichlet stage of the all-or-nothing revision.

    ``_revision_fault_hook`` is the module's declared no-op fault-injection seam.
    Only object identity differs afterwards, which is why
    ``_execution_observable_state_sha256`` is not used as the witness here.
    """

    probe = _legacy_history()
    core = probe.system.core
    target_location = max(probe.case.locations, key=core.hybrid_alpha)
    revision_id = next(
        key for key, event in core._committed_events.items() if event.location_id == target_location
    )
    before = _semantic_state(probe)

    def fault(stage: str) -> None:
        if stage == "dirichlet":
            raise RuntimeError("probe fault injected at the dirichlet stage")

    feedback, binding, likelihood = _counter_evidence(probe, revision_id)
    core._revision_fault_hook = fault  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="probe fault injected"):
            core.process_execution_feedback(
                feedback=feedback,
                binding=binding,
                likelihood_model=likelihood,
                policy=RETRACTION_POLICY,
            )
    finally:
        del core._revision_fault_hook

    assert _semantic_state(probe) == before
    _assert_reconciled(probe)

    # The revision must still be applicable after the recovery.
    recovered = core.process_execution_feedback(
        feedback=feedback, binding=binding, likelihood_model=likelihood, policy=RETRACTION_POLICY
    )
    assert recovered.statistic_operations == (PrototypeStatisticOperation.RETRACT,)
    _assert_reconciled(probe)


# ---------------------------------------------------------------------------
# The action consequence, and its control
# ---------------------------------------------------------------------------


def test_enough_counter_evidence_moves_the_decoded_put_back_choice() -> None:
    """Contract-mandated action change.

    The default ``HYBRID_ALPHA`` readout puts full weight on the Hybrid mass that
    RGRC owns, so retracting the majority location below the runner-up must move the
    decoded top-1.  This is the "should change" half of the pair.
    """

    probe = _legacy_history()
    core = probe.system.core
    majority = max(probe.case.locations, key=core.hybrid_alpha)
    runner_up = sorted(probe.case.locations, key=core.hybrid_alpha, reverse=True)[1]
    assert _top(probe.action_distribution()) == majority
    assert core.hybrid_alpha(runner_up) > 0.0

    flipped_after = None
    for step in range(1, 9):
        _retract_one_at(probe, majority)
        _assert_reconciled(probe)
        if _top(probe.action_distribution()) != majority:
            flipped_after = step
            break

    assert flipped_after is not None
    assert _top(probe.action_distribution()) == runner_up
    assert core.hybrid_alpha(majority) < core.hybrid_alpha(runner_up)


def test_counter_evidence_against_the_runner_up_must_not_move_the_choice() -> None:
    """Null control: the same mechanism applied where it must not change the action."""

    probe = _legacy_history()
    core = probe.system.core
    majority = max(probe.case.locations, key=core.hybrid_alpha)
    runner_up = sorted(probe.case.locations, key=core.hybrid_alpha, reverse=True)[1]
    before_distribution = probe.action_distribution()

    revision_id, result, _ = _retract_one_at(probe, runner_up)

    assert result.statistic_operations == (PrototypeStatisticOperation.RETRACT,)
    assert revision_id not in core._committed_events
    assert probe.action_distribution() != before_distribution
    assert _top(probe.action_distribution()) == majority
    _assert_reconciled(probe)


# ---------------------------------------------------------------------------
# The adaptive production path, and the quarantine promotion it exposes
# ---------------------------------------------------------------------------


def _adaptive_history(days: int = 10) -> BackboneWiringProbe:
    probe = BackboneWiringProbe.build(seed=7)
    for observation in probe.observed_days()[:days]:
        transition = probe.transition_for(observation)
        probe.run_direct_p5(
            transition,
            ciav_input=probe.ciav_input(
                transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
            ),
        )
    return probe


def test_counter_evidence_on_an_adaptively_committed_event_removes_its_lineage() -> None:
    """The committed event is produced by the contract-allowed different-location closure."""

    probe = _adaptive_history()
    core = probe.system.core
    assert len(core._committed_events) > 0

    target_location = max(probe.case.locations, key=core.hybrid_alpha)
    revision_id, result, _ = _retract_one_at(probe, target_location)

    assert result.statistic_operations == (PrototypeStatisticOperation.RETRACT,)
    assert revision_id not in core._committed_events
    assert core._hybrid_loop.ledger.live_promoted_records_for_revision(revision_id) == ()
    _assert_reconciled(probe)


def test_one_formal_revision_never_promotes_a_write_blocked_quarantined_observation() -> None:
    """Round two pinned this as an open breakpoint; round three repairs it.

    Every adaptive primary pass runs with ``force_long_term_write_blocked=True`` and
    the P0 RGRC guard reports ``long_term_write_authorized: False``.  Before the
    repair, one formal revision triggered ``_rebuild_personalized_models`` whose
    replay reclassified the whole observation log and committed those blocked
    observations -- an unauthorized long-term commit under
    ``maximum_unauthorized_long_term_commits == 0``.

    The repair records each observation's origin write eligibility and refuses to
    let a rebuild promote a blocked one without a recorded authorization.  The
    detailed reproduction of both retraction targets, the lineage journal and the
    legacy-lane control live in
    ``tests/test_structure_two_formal_revision_lineage.py``.
    """

    probe = _adaptive_history()
    core = probe.system.core
    committed_before = set(core._committed_events)
    blocked_before = {
        revision_id
        for revision_id in core._observed_events
        if core.observation_write_eligibility(revision_id)["origin_write_blocked"]
    }
    quarantined_before = {event.revision_id for event in core._quarantined_events}
    assert quarantined_before
    assert blocked_before & quarantined_before

    target_location = max(probe.case.locations, key=core.hybrid_alpha)
    _retract_one_at(probe, target_location)

    newly_committed = set(core._committed_events) - committed_before
    assert newly_committed <= quarantined_before
    assert newly_committed & blocked_before == set()
    assert set(core._committed_events) & blocked_before == set()
    # The blocked observations keep their quarantine: withheld, never deleted.
    surviving_blocked = blocked_before & set(core._observed_events)
    assert surviving_blocked <= {event.revision_id for event in core._quarantined_events}
    _assert_reconciled(probe)
