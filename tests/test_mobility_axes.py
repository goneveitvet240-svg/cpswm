"""RQ4/RQ6 多轴移动性画像: 七类不互斥, 所以报告轴与集合, 而不是一个标签.

Audit lines implemented here:

    RQ4 七类移动性 -- 接入前缺口: 七类互斥性或多轴表示; 文档/代码统一.
    RQ6 多位置与转移 -- 接入前缺口: 加入停留时间, 活动条件, 开放位置质量和未决状态.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from cpswm.contracts.base import BaseRecordMetadata, SourceType
from cpswm.contracts.habit_learning import HabitEvidenceSource, HabitLearningEvidence
from cpswm.world_model.habits_transitions import (
    MobilityAxis,
    MobilityResolution,
    MobilityType,
    MobilityTypeThresholds,
    MultiAxisMobilityProfiler,
)
from cpswm.world_model.habits_transitions.mobility_axes import MOBILITY_TYPE_PRECEDENCE

HOUSEHOLD = uuid4()
OBJECT = uuid4()
DESK, SOFA, KITCHEN, BEDROOM = (uuid4() for _ in range(4))
OWNER = str(uuid4())
HOUSEMATE = str(uuid4())
START = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def record(
    location: UUID,
    *,
    hours: float,
    context: str = "weekday",
    actor: str = OWNER,
    weight: float = 1.0,
    source: HabitEvidenceSource = HabitEvidenceSource.DIRECT_OBSERVATION,
) -> HabitLearningEvidence:
    record_id = uuid4()
    moment = START + timedelta(hours=hours)
    source_type = (
        SourceType.MODEL if source is HabitEvidenceSource.MODEL_PREDICTION else SourceType.SENSOR
    )
    return HabitLearningEvidence(
        metadata=BaseRecordMetadata(
            record_id=record_id,
            schema_name="cpswm.HabitLearningEvidence",
            schema_version="0.1.0",
            household_id=HOUSEHOLD,
            session_id=uuid4(),
            recorded_time=moment,
            source_type=source_type,
            source_id="rq4-test",
            trace_id=uuid4(),
        ),
        object_instance_id=OBJECT,
        location_id=location,
        event_time=moment,
        context_key=context,
        actor_posterior={actor: 1.0},
        evidence_source=source,
        proposed_training_weight=weight,
        source_record_ids=(record_id,),
    )


def profiled(records, **kwargs) -> object:  # type: ignore[no-untyped-def]
    profiler = MultiAxisMobilityProfiler(**kwargs)
    profiler.update_all(records)
    return profiler.profile(household_id=HOUSEHOLD, object_instance_id=OBJECT)


# ---------------------------------------------------------------------------
# RQ4: the seven names are covered, and they are not a partition
# ---------------------------------------------------------------------------


def test_all_seven_documented_types_exist_in_code() -> None:
    """文档/代码统一, the trivial half.

    Fails if the code drifts back to five classes, which is the mismatch the
    audit flagged.
    """

    assert {item.value for item in MobilityType} == {
        "anchored",
        "stable",
        "home_based_mobile",
        "multimodal",
        "activity_carried",
        "wandering",
        "regime_changing",
    }
    assert set(MOBILITY_TYPE_PRECEDENCE) == set(MobilityType)
    assert len(MOBILITY_TYPE_PRECEDENCE) == len(MobilityType)


def test_an_object_can_be_two_documented_types_at_once() -> None:
    """The substantive half: a water cup is multimodal *and* activity-carried.

    Fails if the projection is ever collapsed back to a single exclusive label,
    which would force it to discard a true statement about the object.
    """

    records = []
    for day in range(12):
        # Breakfast at the kitchen, work at the desk: two frequent places, and
        # which one is occupied is fully determined by the context.
        records.append(record(KITCHEN, hours=day * 24, context="breakfast"))
        records.append(record(DESK, hours=day * 24 + 4, context="work"))
    profile = profiled(records)
    assert MobilityType.MULTIMODAL in profile.applicable_types
    assert MobilityType.ACTIVITY_CARRIED in profile.applicable_types
    assert profile.resolution is MobilityResolution.AMBIGUOUS
    assert profile.is_ambiguous


def test_ambiguity_still_yields_a_usable_primary_label() -> None:
    """Downstream code needs something to switch on; it must be documented.

    Fails if the primary label stops following ``MOBILITY_TYPE_PRECEDENCE``,
    which would make the choice depend on threshold order instead of on stated
    priority.
    """

    records = []
    for day in range(12):
        records.append(record(KITCHEN, hours=day * 24, context="breakfast"))
        records.append(record(DESK, hours=day * 24 + 4, context="work"))
    profile = profiled(records)
    expected = next(item for item in MOBILITY_TYPE_PRECEDENCE if item in profile.applicable_types)
    assert profile.primary_type is expected


def test_an_anchored_object_resolves_to_exactly_one_type() -> None:
    records = [record(DESK, hours=day * 24) for day in range(20)]
    profile = profiled(records)
    assert profile.applicable_types == (MobilityType.STABLE, MobilityType.ANCHORED)
    # Anchored implies stable by construction; the set says so rather than
    # hiding it behind a threshold ordering.
    assert profile.primary_type is MobilityType.STABLE


def test_home_based_mobile_needs_the_object_to_come_back() -> None:
    """The discriminator ``mobility_profile`` already identified, kept."""

    records = []
    for day in range(15):
        records.append(record(DESK, hours=day * 24))
        records.append(record(SOFA if day % 2 else KITCHEN, hours=day * 24 + 6))
    profile = profiled(records)
    assert profile.axes.return_rate is not None
    assert profile.axes.return_rate >= 0.6
    assert MobilityType.HOME_BASED_MOBILE in profile.applicable_types


def test_regime_change_is_visible_where_entropy_is_not() -> None:
    """A settled two-place habit and a migration share an entropy.

    Fails if ``regime_drift`` stops splitting the history by time, which is the
    only thing that separates the two.
    """

    settled = []
    migrating = []
    for day in range(20):
        settled.append(record(DESK if day % 2 else SOFA, hours=day * 24))
        migrating.append(record(DESK if day < 10 else SOFA, hours=day * 24))
    settled_profile = profiled(settled)
    migrating_profile = profiled(migrating)

    assert settled_profile.axes.spread == pytest.approx(migrating_profile.axes.spread, abs=1e-9)
    assert settled_profile.axes.regime_drift is not None
    assert migrating_profile.axes.regime_drift is not None
    assert migrating_profile.axes.regime_drift > settled_profile.axes.regime_drift
    assert MobilityType.REGIME_CHANGING in migrating_profile.applicable_types
    assert MobilityType.REGIME_CHANGING not in settled_profile.applicable_types


def test_activity_carried_requires_context_to_actually_explain_position() -> None:
    """A marginal preference over two places is not activity coupling.

    Fails if ``context_coupling`` degenerates into "there is more than one
    context", which would label almost everything activity-carried.
    """

    coupled = []
    uncoupled = []
    for day in range(14):
        coupled.append(record(KITCHEN, hours=day * 24, context="breakfast"))
        coupled.append(record(DESK, hours=day * 24 + 4, context="work"))
        # Same two contexts, same two places, but the pairing is scrambled.
        uncoupled.append(record(KITCHEN if day % 2 else DESK, hours=day * 24, context="breakfast"))
        uncoupled.append(record(DESK if day % 2 else KITCHEN, hours=day * 24 + 4, context="work"))
    coupled_profile = profiled(coupled)
    uncoupled_profile = profiled(uncoupled)
    assert coupled_profile.axes.context_coupling == pytest.approx(1.0, abs=1e-6)
    assert uncoupled_profile.axes.context_coupling is not None
    assert uncoupled_profile.axes.context_coupling < 0.5
    assert MobilityType.ACTIVITY_CARRIED in coupled_profile.applicable_types
    assert MobilityType.ACTIVITY_CARRIED not in uncoupled_profile.applicable_types


def test_wandering_excludes_objects_that_return_or_drift() -> None:
    """Otherwise *wandering* absorbs both multimodal and regime-changing."""

    thresholds = MobilityTypeThresholds()
    places = (DESK, SOFA, KITCHEN, BEDROOM)
    spread_out = [record(places[day % 4], hours=day * 24) for day in range(24)]
    profile = profiled(spread_out)
    assert profile.axes.spread is not None
    assert profile.axes.spread >= thresholds.wandering_spread
    # It returns to its primary, so it circulates rather than wanders.
    assert MobilityType.WANDERING not in profile.applicable_types
    assert MobilityType.MULTIMODAL in profile.applicable_types


# ---------------------------------------------------------------------------
# RQ4: axes are independent quantities, not a relabelled single score
# ---------------------------------------------------------------------------


def test_every_axis_is_reported_or_explicitly_unmeasurable() -> None:
    """``None`` must never be silently rendered as zero."""

    single = profiled([record(DESK, hours=0)])
    assert single.axes.displacement is None
    assert single.axes.regime_drift is None
    assert single.resolution is MobilityResolution.INSUFFICIENT_EVIDENCE
    assert single.primary_type is None

    many = profiled(
        [record(DESK if i % 3 else SOFA, hours=i * 24, context=f"c{i % 2}") for i in range(12)]
    )
    assert set(many.axes.measured_axes) == set(MobilityAxis)


def test_spread_distinguishes_zero_from_unmeasurable() -> None:
    """One place is *zero* spread; no places is *no* measurement."""

    empty = MultiAxisMobilityProfiler().profile(household_id=HOUSEHOLD, object_instance_id=OBJECT)
    assert empty.axes.spread is None
    one_place = profiled([record(DESK, hours=i * 24) for i in range(6)])
    assert one_place.axes.spread == 0.0


def test_displacement_and_spread_are_not_the_same_axis() -> None:
    """An object can move constantly between two places (high displacement,
    moderate spread) or sit in one of four (low displacement, high spread)."""

    ping_pong = profiled([record(DESK if i % 2 else SOFA, hours=i * 24) for i in range(16)])
    assert ping_pong.axes.displacement == pytest.approx(1.0)
    assert ping_pong.axes.spread == pytest.approx(1.0)

    sticky = []
    places = (DESK, SOFA, KITCHEN, BEDROOM)
    for block, place in enumerate(places):
        for step in range(4):
            sticky.append(record(place, hours=(block * 4 + step) * 24))
    sticky_profile = profiled(sticky)
    assert sticky_profile.axes.displacement < 0.3
    assert sticky_profile.axes.spread == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# RQ6: dwell time
# ---------------------------------------------------------------------------


def test_dwell_time_measures_hours_until_the_object_is_seen_elsewhere() -> None:
    records = [
        record(DESK, hours=0),
        record(DESK, hours=5),
        record(SOFA, hours=10),
        record(SOFA, hours=12),
        record(DESK, hours=30),
    ]
    profile = profiled(records)
    assert profile.dwell.measured
    assert profile.dwell.samples == 2
    assert profile.dwell.median_hours == pytest.approx(15.0)
    assert profile.dwell.mean_hours == pytest.approx(15.0)


def test_dwell_is_unmeasured_when_the_object_never_moves() -> None:
    profile = profiled([record(DESK, hours=i * 24) for i in range(8)])
    assert not profile.dwell.measured
    assert profile.dwell.median_hours is None


# ---------------------------------------------------------------------------
# RQ6: activity conditioning
# ---------------------------------------------------------------------------


def test_per_context_distributions_and_transitions_are_kept_separate() -> None:
    records = []
    for day in range(8):
        records.append(record(KITCHEN, hours=day * 24, context="breakfast"))
        records.append(record(DESK, hours=day * 24 + 4, context="work"))
    profile = profiled(records)
    assert set(profile.contextual.contexts) == {"breakfast", "work"}
    assert profile.contextual.primary_location("breakfast") == KITCHEN
    assert profile.contextual.primary_location("work") == DESK
    assert profile.contextual.observation_counts["work"] == 8


def test_contexts_disagree_flags_when_a_pooled_matrix_would_lie() -> None:
    """A pooled transition matrix describes an average that never happens.

    Fails if the per-context split is dropped, which is the specific RQ6 gap.
    """

    disagreeing = []
    agreeing = []
    for day in range(8):
        disagreeing.append(record(KITCHEN, hours=day * 24, context="breakfast"))
        disagreeing.append(record(DESK, hours=day * 24 + 4, context="work"))
        agreeing.append(record(DESK, hours=day * 24, context="breakfast"))
        agreeing.append(record(DESK, hours=day * 24 + 4, context="work"))
    assert profiled(disagreeing).contextual.contexts_disagree
    assert not profiled(agreeing).contextual.contexts_disagree


# ---------------------------------------------------------------------------
# RQ6: open-world mass and the undecided state
# ---------------------------------------------------------------------------


def test_mass_outside_the_declared_candidate_set_is_kept_not_renormalized_away() -> None:
    """`§7`: an unobserved place is not an impossible place.

    Fails if open mass is folded back into the declared locations, which would
    make an unseen room look like it cannot happen.
    """

    records = [record(DESK, hours=i * 24) for i in range(6)]
    records += [record(BEDROOM, hours=(6 + i) * 24) for i in range(2)]
    profile = profiled(records, declared_locations=(DESK, SOFA, KITCHEN))
    assert profile.open_world.is_open_world
    assert profile.open_world.open_location_ids == (BEDROOM,)
    assert profile.open_world.open_location_mass == pytest.approx(0.25)
    assert profile.open_world.accounted_mass == pytest.approx(0.75)


def test_without_a_declared_set_there_is_no_open_world_claim() -> None:
    profile = profiled([record(DESK, hours=i * 24) for i in range(4)])
    assert not profile.open_world.is_open_world
    assert profile.open_world.open_location_mass == 0.0


def test_low_confidence_observations_are_counted_as_undecided() -> None:
    records = [record(DESK, hours=i * 24) for i in range(6)]
    records += [record(SOFA, hours=(6 + i) * 24, weight=0.2) for i in range(2)]
    profile = profiled(records)
    assert profile.open_world.undecided_mass > 0.0
    assert profile.open_world.undecided_mass < 1.0


def test_the_profiler_reports_undecided_rather_than_guessing() -> None:
    """未决状态: no applicable type must not become a made-up type."""

    thresholds = MobilityTypeThresholds(
        anchored_displacement=0.0,
        stable_displacement=0.0,
        stable_primary_share=1.0,
        home_primary_share=1.0,
        return_floor=1.0,
        multimodal_spread=1.0,
        wandering_spread=1.0,
        coupling_floor=1.0,
        drift_floor=1.0,
    )
    profile = profiled(
        [record(DESK if i % 3 else SOFA, hours=i * 24) for i in range(9)],
        thresholds=thresholds,
    )
    assert profile.applicable_types == ()
    assert profile.primary_type is None
    assert profile.resolution is MobilityResolution.INSUFFICIENT_EVIDENCE


# ---------------------------------------------------------------------------
# Person conditioning (§5 人物条件化转移矩阵) and the M17 firewall
# ---------------------------------------------------------------------------


def test_person_conditioned_profiles_can_disagree_with_the_pooled_one() -> None:
    records = []
    for day in range(10):
        records.append(record(DESK, hours=day * 24, actor=OWNER))
        records.append(record(SOFA, hours=day * 24 + 6, actor=HOUSEMATE))
    profiler = MultiAxisMobilityProfiler()
    profiler.update_all(records)
    pooled = profiler.profile(household_id=HOUSEHOLD, object_instance_id=OBJECT)
    owner = profiler.profile(household_id=HOUSEHOLD, object_instance_id=OBJECT, person_id=OWNER)
    housemate = profiler.profile(
        household_id=HOUSEHOLD, object_instance_id=OBJECT, person_id=HOUSEMATE
    )
    assert owner.primary_location_id == DESK
    assert housemate.primary_location_id == SOFA
    assert pooled.axes.displacement == pytest.approx(1.0)
    assert owner.axes.displacement == pytest.approx(0.0)


def test_a_model_prediction_cannot_shape_a_profile() -> None:
    profiler = MultiAxisMobilityProfiler()
    assert not profiler.update(record(DESK, hours=0, source=HabitEvidenceSource.MODEL_PREDICTION))
    assert (
        profiler.profile(household_id=HOUSEHOLD, object_instance_id=OBJECT).observation_count == 0
    )


def test_out_of_order_arrival_does_not_change_the_profile() -> None:
    """Transitions, returns, drift and dwell all depend on event order."""

    forward = [record(DESK if i % 2 else SOFA, hours=i * 24) for i in range(12)]
    shuffled = [forward[i] for i in (5, 0, 9, 3, 11, 1, 7, 2, 10, 4, 8, 6)]
    assert profiled(forward).summary() == profiled(shuffled).summary()


def test_summary_is_json_shaped_and_stable() -> None:
    profile = profiled([record(DESK if i % 2 else SOFA, hours=i * 24) for i in range(8)])
    summary = profile.summary()
    assert summary["model_version"].startswith("mobility-axes@")
    assert isinstance(summary["applicable_types"], list)
    assert summary["resolution"] in {item.value for item in MobilityResolution}


def test_thresholds_reject_an_inconsistent_configuration() -> None:
    with pytest.raises(ValueError, match="anchored_displacement"):
        MobilityTypeThresholds(anchored_displacement=0.5, stable_displacement=0.2)
    with pytest.raises(ValueError, match="multimodal_spread"):
        MobilityTypeThresholds(multimodal_spread=0.9, wandering_spread=0.5)
