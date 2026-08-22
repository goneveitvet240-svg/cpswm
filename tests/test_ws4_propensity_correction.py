"""Observation-propensity correction for M17 habit counts.

`项目方向结构二 §2` states the selective-observation problem precisely: because
the robot's route and task decide what it sees, *"missingness is usually MNAR"*.
An uncorrected count therefore learns the robot's patrol route rather than the
resident's habit.

`OAM-PHM §2.2` records the same boundary as *"negative-evidence updates are
coarse"* -> *"jointly account for field of view, occlusion, distance, detection
rate, container state and observation coverage"*, and `§3.8` makes observation
opportunity and negative evidence a first-class capability.

The central test is
:func:`test_two_robots_with_identical_truth_but_different_routes_diverge_without_correction`,
which builds two worlds with an *identical* underlying habit and only different
observation policies.  Any estimator that ignores propensity must return
different habits for them, which is the failure being fixed.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest
from test_observation_aware_habits import habit_evidence

from cpswm.contracts import HabitEvidenceSource, SourceType
from cpswm.world_model.habits_transitions import (
    HierarchicalDirichletHabitModel,
    ObservationPropensityCorrector,
    PositivityViolation,
    PropensityCorrectionMode,
)

DESK = UUID(int=601)
SOFA = UUID(int=602)
BOOK = UUID(int=404)
PERSON = "11111111-1111-1111-1111-111111111111"


def build_model(locations=(DESK, SOFA), prior_strength: float = 1e-6):
    return HierarchicalDirichletHabitModel(
        locations=list(locations),
        common_prior_strength=prior_strength,
        household_weight=1.0,
        person_weight=0.0,
        context_weight=0.0,
    )


def observed_days(
    metadata_factory,
    now,
    *,
    location: UUID,
    count: int,
    day_offset: int = 0,
):
    """``count`` recorded observations of ``location``, one per day."""

    return [
        habit_evidence(
            metadata_factory,
            now + timedelta(days=day_offset + index),
            object_id=BOOK,
            location_id=location,
            actor_posterior={PERSON: 1.0},
            evidence_source=HabitEvidenceSource.DIRECT_OBSERVATION,
            source_type=SourceType.SIMULATION,
        )
        for index in range(count)
    ]


def learn(records_with_propensity, *, mode: PropensityCorrectionMode, household_id):
    """Train one model, optionally correcting each count by its propensity."""

    model = build_model()
    corrector = ObservationPropensityCorrector(mode=mode)
    for record, propensity in records_with_propensity:
        model.update(record, weight_multiplier=corrector.weight_for(propensity).applied_weight)
    return model.predict(
        household_id=household_id,
        person_id=PERSON,
        object_instance_id=BOOK,
        context_key="weekday|breakfast",
    )


def route_biased_world(metadata_factory, now, *, desk_seen: int, sofa_seen: int):
    """Truth is 10 desk-days and 10 sofa-days; only some are observed.

    ``desk_seen``/``sofa_seen`` encode the route: a robot that lives near the
    desk records nine of ten desk-days and one of ten sofa-days.
    """

    desk_propensity = desk_seen / 10
    sofa_propensity = sofa_seen / 10
    return [
        *[
            (record, desk_propensity)
            for record in observed_days(metadata_factory, now, location=DESK, count=desk_seen)
        ],
        *[
            (record, sofa_propensity)
            for record in observed_days(
                metadata_factory, now, location=SOFA, count=sofa_seen, day_offset=100
            )
        ],
    ]


# --------------------------------------------------------------------------
# The failure being fixed
# --------------------------------------------------------------------------


def test_two_robots_with_identical_truth_but_different_routes_diverge_without_correction(
    metadata_factory, household_id, now
):
    """Same habit, different patrol routes, opposite conclusions.

    Robot A records 9/10 desk-days and 1/10 sofa-days; robot B is the mirror.
    The underlying habit is 50/50 in both worlds.
    """

    near_desk = route_biased_world(metadata_factory, now, desk_seen=9, sofa_seen=1)
    near_sofa = route_biased_world(metadata_factory, now, desk_seen=1, sofa_seen=9)

    a = learn(near_desk, mode=PropensityCorrectionMode.NONE, household_id=household_id)
    b = learn(near_sofa, mode=PropensityCorrectionMode.NONE, household_id=household_id)

    assert a.probabilities[DESK] == pytest.approx(0.9, abs=1e-3)
    assert b.probabilities[DESK] == pytest.approx(0.1, abs=1e-3)
    # The two robots disagree about the same household by 0.8 probability mass.
    assert abs(a.probabilities[DESK] - b.probabilities[DESK]) > 0.75


def test_inverse_propensity_weighting_recovers_the_same_habit_from_both_routes(
    metadata_factory, household_id, now
):
    """Correcting by 1/pi makes the estimate a property of the household."""

    near_desk = route_biased_world(metadata_factory, now, desk_seen=9, sofa_seen=1)
    near_sofa = route_biased_world(metadata_factory, now, desk_seen=1, sofa_seen=9)

    a = learn(near_desk, mode=PropensityCorrectionMode.INVERSE, household_id=household_id)
    b = learn(near_sofa, mode=PropensityCorrectionMode.INVERSE, household_id=household_id)

    assert a.probabilities[DESK] == pytest.approx(0.5, abs=1e-3)
    assert b.probabilities[DESK] == pytest.approx(0.5, abs=1e-3)
    assert abs(a.probabilities[DESK] - b.probabilities[DESK]) < 1e-3


def test_stabilized_weights_also_close_the_gap(metadata_factory, household_id, now):
    """Stabilised weights trade a little bias for much lower weight variance."""

    near_desk = route_biased_world(metadata_factory, now, desk_seen=9, sofa_seen=1)
    near_sofa = route_biased_world(metadata_factory, now, desk_seen=1, sofa_seen=9)

    uncorrected_gap = abs(
        learn(
            near_desk, mode=PropensityCorrectionMode.NONE, household_id=household_id
        ).probabilities[DESK]
        - learn(
            near_sofa, mode=PropensityCorrectionMode.NONE, household_id=household_id
        ).probabilities[DESK]
    )
    stabilized = ObservationPropensityCorrector(mode=PropensityCorrectionMode.STABILIZED)
    stabilized.observe_propensities([0.9, 0.1])
    corrected_gap = abs(
        _learn_with(near_desk, stabilized, household_id).probabilities[DESK]
        - _learn_with(near_sofa, stabilized, household_id).probabilities[DESK]
    )

    assert corrected_gap < uncorrected_gap / 10


def _learn_with(records_with_propensity, corrector, household_id):
    model = build_model()
    for record, propensity in records_with_propensity:
        model.update(record, weight_multiplier=corrector.weight_for(propensity).applied_weight)
    return model.predict(
        household_id=household_id,
        person_id=PERSON,
        object_instance_id=BOOK,
        context_key="weekday|breakfast",
    )


# --------------------------------------------------------------------------
# The audited baseline must be unchanged when correction is off
# --------------------------------------------------------------------------


def test_default_update_behaviour_is_byte_identical_to_the_audited_baseline(
    metadata_factory, household_id, now
):
    """``weight_multiplier`` defaults to 1.0, so the baseline is untouched."""

    records = observed_days(metadata_factory, now, location=DESK, count=3)
    explicit = build_model()
    implicit = build_model()
    for record in records:
        explicit.update(record, weight_multiplier=1.0)
        implicit.update(record)

    household = dict(
        household_id=household_id,
        person_id=PERSON,
        object_instance_id=BOOK,
        context_key="weekday|breakfast",
    )

    assert (
        explicit.predict(**household).pseudo_counts == implicit.predict(**household).pseudo_counts
    )


def test_correction_still_honours_the_learning_firewall(metadata_factory, household_id, now):
    """A model prediction has zero weight; no multiplier can revive it."""

    model = build_model()
    prediction = habit_evidence(
        metadata_factory,
        now,
        object_id=BOOK,
        location_id=SOFA,
        actor_posterior={PERSON: 1.0},
        evidence_source=HabitEvidenceSource.MODEL_PREDICTION,
        source_type=SourceType.MODEL,
    )

    assert model.update(prediction, weight_multiplier=1000.0) is False


# --------------------------------------------------------------------------
# Positivity: what correction cannot fix must be reported, not hidden
# --------------------------------------------------------------------------


def test_a_never_observable_location_is_reported_not_silently_reweighted():
    """1/pi is undefined at pi = 0; the corrector must refuse, not guess.

    A place the robot can never see is not a small-sample problem, it is
    outside the support. Silently assigning it a huge or a zero weight would
    hide a coverage gap behind a number.
    """

    corrector = ObservationPropensityCorrector(mode=PropensityCorrectionMode.INVERSE)

    with pytest.raises(PositivityViolation, match="zero observation propensity"):
        corrector.weight_for(0.0)


def test_clipping_is_recorded_rather_than_applied_silently():
    corrector = ObservationPropensityCorrector(
        mode=PropensityCorrectionMode.INVERSE, minimum_propensity=0.05
    )

    clipped = corrector.weight_for(0.001)
    unclipped = corrector.weight_for(0.5)

    assert clipped.clipped is True
    assert clipped.applied_weight == pytest.approx(1 / 0.05)
    assert clipped.raw_propensity == pytest.approx(0.001)
    assert unclipped.clipped is False


def test_clipped_fraction_is_available_for_reporting():
    corrector = ObservationPropensityCorrector(
        mode=PropensityCorrectionMode.INVERSE, minimum_propensity=0.05
    )
    for propensity in (0.5, 0.5, 0.5, 0.001):
        corrector.weight_for(propensity)

    assert corrector.clipped_fraction == pytest.approx(0.25)
    assert corrector.weighted_count == 4


def test_uncorrected_mode_never_clips_and_never_raises():
    corrector = ObservationPropensityCorrector(mode=PropensityCorrectionMode.NONE)

    weight = corrector.weight_for(0.0)

    assert weight.applied_weight == pytest.approx(1.0)
    assert weight.clipped is False
    assert corrector.clipped_fraction == pytest.approx(0.0)


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


@pytest.mark.parametrize("propensity", [-0.1, 1.1])
def test_a_propensity_outside_zero_one_is_rejected(propensity):
    corrector = ObservationPropensityCorrector(mode=PropensityCorrectionMode.INVERSE)

    with pytest.raises(ValueError, match="propensity must be a probability"):
        corrector.weight_for(propensity)


@pytest.mark.parametrize("minimum", [0.0, 1.5])
def test_an_incoherent_clip_threshold_is_rejected(minimum):
    with pytest.raises(ValueError, match="minimum_propensity"):
        ObservationPropensityCorrector(
            mode=PropensityCorrectionMode.INVERSE, minimum_propensity=minimum
        )


def test_stabilized_mode_requires_observed_propensities_first():
    corrector = ObservationPropensityCorrector(mode=PropensityCorrectionMode.STABILIZED)

    with pytest.raises(ValueError, match="observe_propensities"):
        corrector.weight_for(0.5)


def test_stabilized_weights_average_to_about_one(metadata_factory):
    corrector = ObservationPropensityCorrector(mode=PropensityCorrectionMode.STABILIZED)
    corrector.observe_propensities([0.9, 0.1])

    weights = [corrector.weight_for(0.9).applied_weight, corrector.weight_for(0.1).applied_weight]

    # Stabilisation keeps the effective sample size near the raw count, which
    # is the whole reason to prefer it over a raw 1/pi weight.
    assert sum(weights) / len(weights) == pytest.approx((0.5 / 0.9 + 0.5 / 0.1) / 2, rel=1e-6)
    assert max(weights) < 1 / 0.1
