"""WS4 mobility profiling tests.

`项目结构一 §12` WS4 requires fixed / primary / multi-location / return /
transition / entropy, and `§15.3` evaluates mobility *classification*.  The
central test here is
:func:`test_entropy_cannot_separate_circulation_from_migration_but_recurrence_can`,
which constructs two histories with identical distributions — and therefore
identical entropy — that must not receive the same class.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from test_observation_aware_habits import habit_evidence

from cpswm.contracts import HabitEvidenceSource, SourceType
from cpswm.world_model.habits_transitions import MobilityClass, MobilityProfiler

DESK = UUID(int=601)
SOFA = UUID(int=602)
SHELF = UUID(int=603)


@pytest.fixture
def book_id() -> UUID:
    return UUID(int=404)


def feed(
    profiler: MobilityProfiler,
    metadata_factory,
    now,
    object_id: UUID,
    locations: list[UUID],
    *,
    evidence_source: HabitEvidenceSource = HabitEvidenceSource.DIRECT_OBSERVATION,
    source_type: SourceType = SourceType.SIMULATION,
    reverse_arrival: bool = False,
) -> None:
    """Feed one location per day, optionally arriving newest-first."""

    records = [
        habit_evidence(
            metadata_factory,
            now + timedelta(days=day),
            object_id=object_id,
            location_id=location,
            actor_posterior={str(uuid4()): 1.0},
            evidence_source=evidence_source,
            source_type=source_type,
        )
        for day, location in enumerate(locations)
    ]
    if reverse_arrival:
        records.reverse()
    profiler.update_all(records)


# --------------------------------------------------------------------------
# The claim: entropy is not enough, recurrence is the discriminator
# --------------------------------------------------------------------------


def test_entropy_cannot_separate_circulation_from_migration_but_recurrence_can(
    metadata_factory, household_id, now, book_id
):
    """Identical distributions, identical entropy, different mobility class.

    Circulating: desk, sofa, shelf repeated — the object keeps coming home.
    Migrating:   desk x3 then sofa x3 then shelf x3 — it never returns.

    Both have counts {desk: 3, sofa: 3, shelf: 3}.  Any classifier that reads
    only the distribution must give these the same answer, which is wrong.
    """

    circulating = MobilityProfiler()
    feed(circulating, metadata_factory, now, book_id, [DESK, SOFA, SHELF] * 3)
    migrating = MobilityProfiler()
    feed(
        migrating,
        metadata_factory,
        now,
        book_id,
        [DESK] * 3 + [SOFA] * 3 + [SHELF] * 3,
    )

    circulating_profile = circulating.profile(household_id=household_id, object_instance_id=book_id)
    migrating_profile = migrating.profile(household_id=household_id, object_instance_id=book_id)

    # Same evidence counts, so the distribution-only view is identical ...
    assert circulating_profile.location_distribution == migrating_profile.location_distribution
    assert circulating_profile.normalized_location_entropy == pytest.approx(
        migrating_profile.normalized_location_entropy
    )

    # ... but the classes must differ, and recurrence is what differs.
    assert circulating_profile.mobility_class is MobilityClass.MULTI_LOCATION
    assert migrating_profile.mobility_class is MobilityClass.MIGRATORY
    assert circulating_profile.recurrence_rate > migrating_profile.recurrence_rate


# --------------------------------------------------------------------------
# WS4 classes
# --------------------------------------------------------------------------


def test_a_never_moved_object_is_fixed(metadata_factory, household_id, now, book_id):
    profiler = MobilityProfiler()
    feed(profiler, metadata_factory, now, book_id, [DESK] * 5)

    profile = profiler.profile(household_id=household_id, object_instance_id=book_id)

    assert profile.mobility_class is MobilityClass.FIXED
    assert profile.primary_location_id == DESK
    assert profile.primary_share == pytest.approx(1.0)
    assert profile.normalized_location_entropy is None
    assert profile.recurrence_rate is None


def test_one_dominant_place_with_returning_exceptions(metadata_factory, household_id, now, book_id):
    """The F0 story generalised: mostly desk, occasional sofa, always back."""

    profiler = MobilityProfiler()
    feed(
        profiler,
        metadata_factory,
        now,
        book_id,
        [DESK, DESK, SOFA, DESK, DESK, SOFA, DESK, DESK],
    )

    profile = profiler.profile(household_id=household_id, object_instance_id=book_id)

    assert profile.mobility_class is MobilityClass.PRIMARY_WITH_EXCEPTIONS
    assert profile.primary_location_id == DESK
    assert profile.primary_share == pytest.approx(0.75)
    assert profile.recurrence_rate == pytest.approx(1.0)


def test_fewer_than_two_observations_claims_no_profile(
    metadata_factory, household_id, now, book_id
):
    profiler = MobilityProfiler()
    feed(profiler, metadata_factory, now, book_id, [DESK])

    profile = profiler.profile(household_id=household_id, object_instance_id=book_id)

    assert profile.mobility_class is MobilityClass.INSUFFICIENT_EVIDENCE
    assert profile.observation_count == 1


def test_an_unseen_object_returns_an_empty_profile(household_id):
    profile = MobilityProfiler().profile(
        household_id=household_id, object_instance_id=UUID(int=999)
    )

    assert profile.mobility_class is MobilityClass.INSUFFICIENT_EVIDENCE
    assert profile.observation_count == 0
    assert profile.primary_location_id is None
    assert profile.location_distribution == {}


# --------------------------------------------------------------------------
# WS4 statistics
# --------------------------------------------------------------------------


def test_frequent_locations_cover_the_requested_mass(metadata_factory, household_id, now, book_id):
    profiler = MobilityProfiler(frequent_coverage=0.9)
    feed(profiler, metadata_factory, now, book_id, [DESK] * 8 + [SOFA] * 1 + [SHELF] * 1)

    profile = profiler.profile(household_id=household_id, object_instance_id=book_id)
    covered = sum(
        profile.location_distribution[location] for location in profile.frequent_location_ids
    )

    assert covered >= 0.9
    assert profile.frequent_location_ids[0] == DESK


def test_transitions_are_counted_between_consecutive_observations(
    metadata_factory, household_id, now, book_id
):
    profiler = MobilityProfiler()
    feed(profiler, metadata_factory, now, book_id, [DESK, SOFA, DESK, SOFA])

    profile = profiler.profile(household_id=household_id, object_instance_id=book_id)

    assert profile.transition_counts[(DESK, SOFA)] == 2
    assert profile.transition_counts[(SOFA, DESK)] == 1


def test_normalised_entropy_is_one_for_a_uniform_spread(
    metadata_factory, household_id, now, book_id
):
    profiler = MobilityProfiler()
    feed(profiler, metadata_factory, now, book_id, [DESK, SOFA, SHELF] * 2)

    profile = profiler.profile(household_id=household_id, object_instance_id=book_id)

    assert profile.normalized_location_entropy == pytest.approx(1.0)


def test_out_of_order_arrival_is_ordered_by_event_time(
    metadata_factory, household_id, now, book_id
):
    """Transitions and returns depend on event order, not on arrival order."""

    forward = MobilityProfiler()
    feed(forward, metadata_factory, now, book_id, [DESK, SOFA, SHELF])
    reversed_arrival = MobilityProfiler()
    feed(
        reversed_arrival,
        metadata_factory,
        now,
        book_id,
        [DESK, SOFA, SHELF],
        reverse_arrival=True,
    )

    assert (
        forward.profile(household_id=household_id, object_instance_id=book_id).transition_counts
        == reversed_arrival.profile(
            household_id=household_id, object_instance_id=book_id
        ).transition_counts
    )


# --------------------------------------------------------------------------
# The learning firewall must apply here too
# --------------------------------------------------------------------------


def test_a_model_prediction_cannot_shape_the_profile(metadata_factory, household_id, now, book_id):
    """`HabitLearningEvidence` gives predictions zero weight; WS4 must honour it."""

    profiler = MobilityProfiler()
    feed(profiler, metadata_factory, now, book_id, [DESK, DESK])
    feed(
        profiler,
        metadata_factory,
        now + timedelta(days=10),
        book_id,
        [SOFA] * 5,
        evidence_source=HabitEvidenceSource.MODEL_PREDICTION,
        source_type=SourceType.MODEL,
    )

    profile = profiler.profile(household_id=household_id, object_instance_id=book_id)

    assert profile.observation_count == 2
    assert profile.mobility_class is MobilityClass.FIXED
    assert SOFA not in profile.location_distribution


def test_update_reports_whether_a_record_was_applied(metadata_factory, household_id, now, book_id):
    profiler = MobilityProfiler()
    accepted = habit_evidence(
        metadata_factory,
        now,
        object_id=book_id,
        location_id=DESK,
        actor_posterior={str(uuid4()): 1.0},
    )
    rejected = habit_evidence(
        metadata_factory,
        now,
        object_id=book_id,
        location_id=SOFA,
        actor_posterior={str(uuid4()): 1.0},
        evidence_source=HabitEvidenceSource.MODEL_PREDICTION,
        source_type=SourceType.MODEL,
    )

    assert profiler.update(accepted) is True
    assert profiler.update(rejected) is False


# --------------------------------------------------------------------------
# Reproducibility and configuration
# --------------------------------------------------------------------------


def test_primary_location_ties_break_deterministically(
    metadata_factory, household_id, now, book_id
):
    first = MobilityProfiler()
    feed(first, metadata_factory, now, book_id, [DESK, SOFA])
    second = MobilityProfiler()
    feed(second, metadata_factory, now, book_id, [SOFA, DESK])

    assert (
        first.profile(household_id=household_id, object_instance_id=book_id).primary_location_id
        == second.profile(household_id=household_id, object_instance_id=book_id).primary_location_id
    )


def test_profiles_are_isolated_per_household_and_object(
    metadata_factory, household_id, now, book_id
):
    profiler = MobilityProfiler()
    other_object = UUID(int=405)
    feed(profiler, metadata_factory, now, book_id, [DESK, DESK])
    feed(profiler, metadata_factory, now, other_object, [SOFA, SOFA])

    assert (
        profiler.profile(household_id=household_id, object_instance_id=book_id).primary_location_id
        == DESK
    )
    assert (
        profiler.profile(
            household_id=household_id, object_instance_id=other_object
        ).primary_location_id
        == SOFA
    )
    assert len(profiler.profiled_objects()) == 2


@pytest.mark.parametrize(
    ("fixed", "primary", "recurrence", "coverage"),
    [
        (0.5, 0.9, 0.5, 0.9),  # primary above fixed
        (1.0, 0.0, 0.5, 0.9),  # non-positive primary
        (1.0, 0.6, 1.5, 0.9),  # recurrence outside [0, 1]
        (1.0, 0.6, 0.5, 0.0),  # non-positive coverage
    ],
)
def test_incoherent_thresholds_are_rejected(fixed, primary, recurrence, coverage):
    with pytest.raises(ValueError):
        MobilityProfiler(
            fixed_share=fixed,
            primary_share=primary,
            recurrence_floor=recurrence,
            frequent_coverage=coverage,
        )
