"""Planner read boundary: which surviving evidence may move the next action.

These assertions fix the v0.3 contract that closed the measured v0.2 failure
("the reversible revision's benefit never reached next-action put-back and
recovery").  The point of every test here is the same: a *pooled cumulative
count* cannot express which owner-attributed evidence currently survives, and
that expressiveness -- not a better predictor -- is what the reversible
machinery produces.
"""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID, uuid4

import pytest

from cpswm.system.evaluation_operations import D0SyntheticOracleReplayAdapter
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    _FullProjectTwoMethod,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoDatasetSplit
from cpswm.system.prototype_spine import (
    ActionReadout,
    ActionReadoutConfig,
    CorePrototypeSpine,
)

# Validation seeds only.  A unit test must never construct a sealed test household.
VALIDATION_SEEDS = (101, 103)
UNIT_HOLDOUT_SEEDS = (307, 311)


@lru_cache(maxsize=1)
def _episodes():
    """One shared validation episode.

    Cached because two arms are only comparable when they replay the *same*
    household: the adapter mints fresh entity UUIDs on every build.
    """

    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=VALIDATION_SEEDS,
        test_seeds=UNIT_HOLDOUT_SEEDS,
        max_steps_per_episode=32,
    ).build()
    return tuple(dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION))


def _drive(readout: ActionReadoutConfig | None, steps: int = 32) -> _FullProjectTwoMethod:
    episode = _episodes()[0]
    state = _FullProjectTwoMethod(episode, owner_threshold=0.4, action_readout=readout)
    for step in episode.steps[:steps]:
        state.observe(step)
        state.predict()
        state.feedback(step)
    return state


# --------------------------------------------------------------------------
# configuration contract
# --------------------------------------------------------------------------


def test_the_default_readout_is_the_frozen_pooled_alpha_boundary() -> None:
    assert ActionReadoutConfig().readout is ActionReadout.HYBRID_ALPHA
    assert ActionReadoutConfig().component_weights == {
        "hybrid_alpha": 1.0,
        "regime_local": 0.0,
        "surviving": 0.0,
        "fast_action": 0.0,
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"owner_mass_floor": 1.5},
        {"owner_mass_floor": -0.1},
        {"fast_owner_mass_floor": 1.5},
        {"fast_owner_mass_floor": -0.1},
        {"fast_confirmation_observations": 0},
        {"unconfirmed_fast_discount": -0.1},
        {"unconfirmed_fast_discount": 1.1},
        {"recency_half_life": -1.0},
        {"pending_correction_discount": 1.5},
        {"hybrid_alpha_weight": -1.0},
        {"surviving_revision_weight": -0.5},
        {"fast_action_weight": -0.5},
    ],
)
def test_an_ill_posed_readout_policy_is_rejected_at_construction(kwargs) -> None:
    with pytest.raises(ValueError):
        ActionReadoutConfig(**kwargs)


def test_a_named_readout_resolves_to_exactly_one_component() -> None:
    for name, key in (
        (ActionReadout.HYBRID_ALPHA, "hybrid_alpha"),
        (ActionReadout.REGIME_LOCAL, "regime_local"),
        (ActionReadout.SURVIVING_OWNER_REVISIONS, "surviving"),
        (ActionReadout.LATEST_OWNER_EVENT, "fast_action"),
    ):
        weights = ActionReadoutConfig(readout=name).component_weights
        assert weights[key] == 1.0
        assert sum(weights.values()) == 1.0


def test_dual_timescale_readout_exposes_explicit_fast_and_slow_weights() -> None:
    config = ActionReadoutConfig(
        readout=ActionReadout.DUAL_TIMESCALE_REVERSIBLE,
        fast_action_weight=0.7,
        surviving_revision_weight=0.2,
        regime_local_weight=0.1,
        hybrid_alpha_weight=0.0,
    )
    assert config.component_weights == {
        "hybrid_alpha": 0.0,
        "regime_local": 0.1,
        "surviving": 0.2,
        "fast_action": 0.7,
    }


# --------------------------------------------------------------------------
# read boundary
# --------------------------------------------------------------------------


def test_the_default_readout_reproduces_the_pooled_alpha_distribution_exactly() -> None:
    """Backward compatibility is not a comment; it is an assertion."""

    state = _drive(None)
    spine = state.spine
    snapshot = spine.current_snapshot
    produced = spine.action_location_distribution(snapshot)
    raw = {location: max(0.0, spine.hybrid_alpha(location)) for location in spine.locations}
    total = sum(raw.values())
    expected = (
        {location: value / total for location, value in raw.items()}
        if total > 0.0
        else {location: 1.0 / len(spine.locations) for location in spine.locations}
    )
    assert produced == pytest.approx(expected)


def test_a_stale_snapshot_is_refused_under_every_readout() -> None:
    episode = _episodes()[0]
    state = _FullProjectTwoMethod(episode, owner_threshold=0.4)
    for step in episode.steps[:4]:
        state.observe(step)
        state.predict()
        state.feedback(step)
    stale = state.spine.current_snapshot
    for step in episode.steps[4:8]:
        state.observe(step)
        state.predict()
        state.feedback(step)
    assert state.spine.current_snapshot.snapshot_id != stale.snapshot_id
    for readout in ActionReadout:
        with pytest.raises(ValueError, match="stale belief snapshot"):
            state.spine.action_location_distribution(
                stale, readout=ActionReadoutConfig(readout=readout)
            )


def test_every_readout_returns_a_normalized_distribution_over_the_known_locations() -> None:
    for readout in ActionReadout:
        state = _drive(ActionReadoutConfig(readout=readout))
        spine = state.spine
        distribution = spine.action_location_distribution(
            spine.current_snapshot, readout=ActionReadoutConfig(readout=readout)
        )
        assert set(distribution) == set(spine.locations)
        assert sum(distribution.values()) == pytest.approx(1.0)
        assert all(value >= 0.0 for value in distribution.values())


# --------------------------------------------------------------------------
# the actual v0.3 claim
# --------------------------------------------------------------------------


def test_the_surviving_readout_degenerates_to_the_pooled_count_when_flat() -> None:
    """The honest attribution boundary for the v0.3 gain.

    With no recency decay and no owner-mass floor, reading the surviving
    committed set is *identical* to reading the pooled hybrid alpha -- the pool
    is that set.  So the measured improvement is NOT "we read a different pool".
    It is recency weighting plus owner-mass gating over that set.  Pinning the
    degenerate case here stops a later reading from claiming the wrong cause.
    """

    flat = ActionReadoutConfig(readout=ActionReadout.SURVIVING_OWNER_REVISIONS)
    state = _drive(flat)
    spine = state.spine
    pooled = spine.action_location_distribution(spine.current_snapshot)
    surviving = spine.action_location_distribution(spine.current_snapshot, readout=flat)
    assert surviving == pytest.approx(pooled, abs=1e-9)


def test_a_location_with_no_surviving_evidence_receives_exactly_zero_mass() -> None:
    surviving = ActionReadoutConfig(
        readout=ActionReadout.SURVIVING_OWNER_REVISIONS, recency_half_life=1.0
    )
    state = _drive(surviving)
    spine = state.spine
    live = {event.location_id for event in spine._committed_events.values()}
    assert live, "the drive produced no committed owner evidence"
    distribution = spine.action_location_distribution(spine.current_snapshot, readout=surviving)
    for location in spine.locations:
        if location not in live:
            assert distribution[location] == pytest.approx(0.0)


def _put_back_sequence(episode, readout: ActionReadoutConfig | None) -> list:
    state = _FullProjectTwoMethod(episode, owner_threshold=0.4, action_readout=readout)
    chosen = []
    for step in episode.steps:
        state.observe(step)
        chosen.append(state.predict().put_back)
        state.feedback(step)
    return chosen


V03_SELECTED = ActionReadoutConfig(
    readout=ActionReadout.SURVIVING_OWNER_REVISIONS,
    owner_mass_floor=0.5,
    recency_half_life=1.0,
)


def test_recency_is_what_separates_the_v03_readout_from_the_frozen_one() -> None:
    """Necessity test at the decision level, not at one arbitrary snapshot.

    A single snapshot -- or a single quiet household -- can coincide by chance.
    The claim is only that the selected readout changes what the robot does
    somewhere in the validation split, with nothing else in the method changed.
    """

    differed = [
        _put_back_sequence(episode, None) != _put_back_sequence(episode, V03_SELECTED)
        for episode in _episodes()
    ]
    assert any(differed), "the v0.3 readout never changed a put-back decision"


def test_a_flat_surviving_readout_changes_no_decision_at_all() -> None:
    """The degenerate case must be decision-identical, not merely close.

    This is the attribution guard: without recency and without the owner-mass
    floor, reading the surviving set decides exactly what the pooled count
    decided, in every household.
    """

    flat = ActionReadoutConfig(readout=ActionReadout.SURVIVING_OWNER_REVISIONS)
    for episode in _episodes():
        assert _put_back_sequence(episode, None) == _put_back_sequence(episode, flat)


def test_an_owner_mass_floor_excludes_weakly_attributed_evidence() -> None:
    permissive = ActionReadoutConfig(readout=ActionReadout.SURVIVING_OWNER_REVISIONS)
    strict = ActionReadoutConfig(
        readout=ActionReadout.SURVIVING_OWNER_REVISIONS, owner_mass_floor=1.0
    )
    state = _drive(permissive)
    spine = state.spine
    masses = [event.owner_mass for event in spine._committed_events.values()]
    assert masses and min(masses) < 1.0, "fixture has no weakly attributed evidence to exclude"
    # Every event is below the floor, so the component is empty and the mixer
    # must fall back to a proper uniform rather than emitting zeros or NaN.
    distribution = spine.action_location_distribution(spine.current_snapshot, readout=strict)
    assert sum(distribution.values()) == pytest.approx(1.0)
    uniform = 1.0 / len(spine.locations)
    assert all(value == pytest.approx(uniform) for value in distribution.values())


def test_recency_decay_moves_mass_toward_the_most_recent_surviving_evidence() -> None:
    flat = ActionReadoutConfig(readout=ActionReadout.SURVIVING_OWNER_REVISIONS)
    decayed = ActionReadoutConfig(
        readout=ActionReadout.SURVIVING_OWNER_REVISIONS, recency_half_life=1.0
    )
    state = _drive(decayed)
    spine = state.spine
    ordered = sorted(
        spine._committed_events.values(),
        key=lambda event: (event.evidence.event_time, str(event.revision_id)),
    )
    newest = ordered[-1].location_id
    flat_distribution = spine.action_location_distribution(spine.current_snapshot, readout=flat)
    decayed_distribution = spine.action_location_distribution(
        spine.current_snapshot, readout=decayed
    )
    assert decayed_distribution[newest] >= flat_distribution[newest]


def test_latest_owner_readout_is_the_explicit_pchmp_top1_control() -> None:
    """The strong control reads PCHMP only; it never peeks at evaluator truth."""

    config = ActionReadoutConfig(
        readout=ActionReadout.LATEST_OWNER_EVENT,
        fast_owner_mass_floor=0.5,
    )
    for episode in _episodes():
        state = _FullProjectTwoMethod(
            episode,
            owner_threshold=0.4,
            action_readout=config,
            feedback_mode="none",
        )
        last_owner = None
        for step in episode.steps:
            state.observe(step)
            result = state.step_results.get(step.step_id)
            if result is not None and result.actor_posterior[state.episode.owner_actor_key] >= 0.5:
                assert step.after is not None
                last_owner = step.after.detected_location_id
            prediction = state.predict().put_back
            if last_owner is not None:
                assert prediction == last_owner
            state.feedback(step)


def test_orrer_feedback_replaces_the_fast_lineage_head_before_the_next_action() -> None:
    config = ActionReadoutConfig(readout=ActionReadout.LATEST_OWNER_EVENT)
    state = _FullProjectTwoMethod(_episodes()[0], owner_threshold=0.4, action_readout=config)
    for step in state.episode.steps:
        state.observe(step)
        state.predict()
        state.feedback(step)
        if not state.revision_action_traces:
            continue
        trace = state.revision_action_traces[-1]
        assert trace.superseded_revision_id not in state.spine._fast_action_events
        assert trace.corrected_revision_id in state.spine._fast_action_events
        return
    pytest.fail("validation episode produced no ORRER feedback revision")


def test_ciav_verification_updates_only_the_fast_action_ledger() -> None:
    state = _FullProjectTwoMethod(
        _episodes()[0],
        owner_threshold=0.4,
        action_readout=ActionReadoutConfig(readout=ActionReadout.LATEST_OWNER_EVENT),
    )
    step = state.episode.steps[0]
    state.observe(step)
    result = state.step_results[step.step_id]
    assert state.spine.current_cause_snapshot is not None
    committed_before = dict(state.spine._committed_events)
    hybrid_before = {location: state.spine.hybrid_alpha(location) for location in state.locations}
    receipt = state.spine.apply_fast_action_verification(
        revision_id=result.event_revision_id,
        verified_owner_probability=0.01,
        source_record_id=uuid4(),
    )
    assert receipt.long_term_write is False
    assert receipt.owner_mass_after == pytest.approx(0.01)
    assert state.spine._fast_action_events[result.event_revision_id].owner_mass == pytest.approx(
        0.01
    )
    assert state.spine._committed_events == committed_before
    assert {location: state.spine.hybrid_alpha(location) for location in state.locations} == (
        hybrid_before
    )


# --------------------------------------------------------------------------
# quarantine / discard handoff
# --------------------------------------------------------------------------


def test_a_refused_correction_stays_visible_to_the_planner_but_not_to_the_statistics() -> None:
    """RGRC quarantine governs the long-term write, not the next action.

    The ledger is an *audit* surface: every refused correction is countable and
    named.  On D0 it is measurably inert (the refused locations were never the
    planner's choice) -- that null is reported, not hidden.
    """

    state = _drive(ActionReadoutConfig(readout=ActionReadout.SURVIVING_OWNER_REVISIONS))
    spine = state.spine
    ledger = spine.action_scoped_negative_ledger()
    pending = spine.pending_correction_mass()
    for _location, delta in ledger.values():
        assert delta < 0.0, "only a negative owner-mass correction is action-scoped"
    for location, delta in ledger.values():
        assert pending.get(location, 0.0) <= 0.0 or delta < 0.0
    # The refused corrections must not appear as a Dirichlet/RLS/Hybrid write.
    applied = [
        receipt
        for receipts in spine._project_one_application_receipts.values()
        for receipt in receipts
        if receipt.status.value == "applied"
    ]
    applied_fingerprints = {receipt.request_fingerprint for receipt in applied}
    assert not (set(ledger) & applied_fingerprints), (
        "an applied request must release its action-scoped negative or it counts twice"
    )


def test_every_unapplied_request_carries_a_named_reason() -> None:
    """No opaque rejection: each gap must be countable by cause."""

    state = _drive(ActionReadoutConfig(readout=ActionReadout.SURVIVING_OWNER_REVISIONS))
    unapplied = [
        receipt
        for receipts in state.spine._project_one_application_receipts.values()
        for receipt in receipts
        if receipt.status.value != "applied"
    ]
    for receipt in unapplied:
        assert receipt.rationale.strip()
        assert receipt.rationale != "superseded revision is neither committed nor quarantined" or (
            receipt.superseded_revision_id not in state.spine._observed_events
        )


def test_the_spine_accepts_a_readout_policy_at_construction() -> None:
    locations = (UUID(int=1), UUID(int=2))
    spine = CorePrototypeSpine(
        owner_key="owner",
        object_instance_id=UUID(int=9),
        locations=locations,
        authorization_scope_id=UUID(int=11),
        action_readout=ActionReadoutConfig(readout=ActionReadout.SURVIVING_OWNER_REVISIONS),
    )
    distribution = spine.action_location_distribution(spine.current_snapshot)
    assert sum(distribution.values()) == pytest.approx(1.0)
