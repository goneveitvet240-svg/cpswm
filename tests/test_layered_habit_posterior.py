"""RQ5 分层个性化习惯: 修正概率公式, 并证明证据没有被重复计算.

The audit line:

    RQ5 分层个性化习惯 -- 路线正确 -- 接入前缺口: 修正文档概率公式;
    验证家庭/人物证据是否重复计算.

Both halves are tested here.  The second half is the one with a number
attached: the additive baseline reads one observation as three.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from cpswm.contracts.base import BaseRecordMetadata, SourceType
from cpswm.contracts.habit_learning import HabitEvidenceSource, HabitLearningEvidence
from cpswm.world_model.habits_transitions import (
    HabitLayer,
    HierarchicalDirichletHabitModel,
    LayerConcentration,
    LayeredHabitPosterior,
    measure_evidence_multiplicity,
)

HOUSEHOLD = uuid4()
OBJECT = uuid4()
LOCATIONS = [uuid4() for _ in range(3)]
OWNER = str(uuid4())
HOUSEMATE = str(uuid4())
UNKNOWN = LayeredHabitPosterior.UNKNOWN_ACTOR
START = datetime(2026, 3, 1, tzinfo=UTC)


def evidence(
    location: UUID,
    *,
    actor: str = OWNER,
    context: str = "weekday",
    index: int = 0,
    posterior: dict[str, float] | None = None,
) -> HabitLearningEvidence:
    record_id = uuid4()
    return HabitLearningEvidence(
        metadata=BaseRecordMetadata(
            record_id=record_id,
            schema_name="cpswm.HabitLearningEvidence",
            schema_version="0.1.0",
            household_id=HOUSEHOLD,
            session_id=uuid4(),
            recorded_time=START + timedelta(days=index),
            source_type=SourceType.SENSOR,
            source_id="rq5-test",
            trace_id=uuid4(),
        ),
        object_instance_id=OBJECT,
        location_id=location,
        event_time=START + timedelta(days=index),
        context_key=context,
        actor_posterior=posterior or {actor: 1.0},
        evidence_source=HabitEvidenceSource.DIRECT_OBSERVATION,
        proposed_training_weight=1.0,
        source_record_ids=(record_id,),
    )


def layered(**kwargs) -> LayeredHabitPosterior:  # type: ignore[no-untyped-def]
    kwargs.setdefault("locations", LOCATIONS)
    kwargs.setdefault("resident_actor_keys", (OWNER, HOUSEMATE))
    return LayeredHabitPosterior(**kwargs)


QUERY = {
    "household_id": HOUSEHOLD,
    "person_id": OWNER,
    "object_instance_id": OBJECT,
    "context_key": "weekday",
}


# ---------------------------------------------------------------------------
# The finding: the additive baseline counts one observation three times
# ---------------------------------------------------------------------------


def test_the_additive_baseline_reads_one_observation_as_three() -> None:
    """This is the RQ5 gap, as a number.

    Fails if :class:`HierarchicalDirichletHabitModel` changes its pooling.  If
    it does, every Dirichlet-surprise reading that depends on it has to be
    revisited, which is why this is pinned rather than left as a comment.

    §4.2 already warns that the naive product 会重复计算嵌套证据. This test says
    the additive baseline does it too, and by how much.
    """

    model = HierarchicalDirichletHabitModel(
        locations=LOCATIONS, resident_actor_keys=(OWNER, HOUSEMATE)
    )
    multiplicity = measure_evidence_multiplicity(model, evidence=evidence(LOCATIONS[0]), **QUERY)
    assert multiplicity == pytest.approx(3.0)


def test_the_layered_posterior_never_exceeds_what_the_evidence_justifies() -> None:
    """Its posterior stays at or below a single-level Dirichlet's sharpness.

    Fails if a leave-one-out parent is replaced by the full parent, which is
    the specific mistake this module exists to prevent.
    """

    model = layered()
    multiplicity = measure_evidence_multiplicity(model, evidence=evidence(LOCATIONS[0]), **QUERY)
    assert multiplicity <= 1.0 + 1e-9


@pytest.mark.parametrize("count", [1, 2, 4, 8, 16])
def test_layered_is_never_sharper_than_an_honest_one_level_dirichlet(count: int) -> None:
    model = layered()
    for index in range(count):
        model.update(evidence(LOCATIONS[0], index=index))
    top = model.predict(**QUERY).probabilities[LOCATIONS[0]]
    honest = (count + 1.0 / len(LOCATIONS)) / (count + 1.0)
    assert top <= honest + 1e-9


# ---------------------------------------------------------------------------
# The partition: every observation is counted exactly once
# ---------------------------------------------------------------------------


def test_the_three_pools_partition_the_evidence_exactly() -> None:
    """Own cell + this person's other contexts + other residents = everything.

    Fails the moment a level starts reusing a child's own counts, which is how
    multiplicative back-off silently reintroduces double counting.
    """

    model = layered()
    model.update(evidence(LOCATIONS[0], actor=OWNER, context="weekday", index=0))
    model.update(evidence(LOCATIONS[0], actor=OWNER, context="weekday", index=1))
    model.update(evidence(LOCATIONS[1], actor=OWNER, context="weekend", index=2))
    model.update(evidence(LOCATIONS[2], actor=HOUSEMATE, context="weekday", index=3))

    report = model.evidence_report(**QUERY)
    assert report.observations_applied == pytest.approx(4.0)
    assert report.counted_evidence_mass == pytest.approx(4.0)
    assert report.evidence_multiplicity == pytest.approx(1.0)
    assert not report.double_counts
    assert report.layer_counts[HabitLayer.CONTEXT] == pytest.approx(2.0)
    assert report.layer_counts[HabitLayer.PERSON] == pytest.approx(1.0)
    assert report.layer_counts[HabitLayer.HOUSEHOLD] == pytest.approx(1.0)


def test_multiplicity_is_one_for_every_query_cell() -> None:
    model = layered()
    plan = [
        (LOCATIONS[0], OWNER, "weekday"),
        (LOCATIONS[1], OWNER, "weekend"),
        (LOCATIONS[2], HOUSEMATE, "weekday"),
        (LOCATIONS[0], HOUSEMATE, "weekend"),
    ]
    for index, (location, actor, context) in enumerate(plan):
        model.update(evidence(location, actor=actor, context=context, index=index))
    for actor in (OWNER, HOUSEMATE):
        for context in ("weekday", "weekend", "never_seen"):
            report = model.evidence_report(
                household_id=HOUSEHOLD,
                person_id=actor,
                object_instance_id=OBJECT,
                context_key=context,
            )
            assert report.evidence_multiplicity == pytest.approx(1.0), (actor, context)


def test_an_unseen_context_still_partitions_correctly() -> None:
    """A cold cell must back off to the person, not lose the evidence."""

    model = layered()
    for index in range(6):
        model.update(evidence(LOCATIONS[0], context="weekday", index=index))
    report = model.evidence_report(
        household_id=HOUSEHOLD,
        person_id=OWNER,
        object_instance_id=OBJECT,
        context_key="holiday",
    )
    assert report.layer_counts[HabitLayer.CONTEXT] == pytest.approx(0.0)
    assert report.layer_counts[HabitLayer.PERSON] == pytest.approx(6.0)
    assert report.evidence_multiplicity == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# The corrected formula: deviations, not levels, are what multiply
# ---------------------------------------------------------------------------


def test_the_deviation_product_reconstructs_the_posterior_exactly() -> None:
    """The telescoping identity in §4.2's corrected form.

    Fails if any level stops being a proper conditional, which would make the
    documented product formula wrong again.
    """

    model = layered()
    for index in range(5):
        model.update(evidence(LOCATIONS[0], index=index))
    for index in range(2):
        model.update(evidence(LOCATIONS[1], index=5 + index))
    for index in range(3):
        model.update(evidence(LOCATIONS[2], actor=HOUSEMATE, index=7 + index))

    prediction = model.predict(**QUERY)
    reconstructed = dict(prediction.layer_probabilities[HabitLayer.COMMON])
    for layer in (HabitLayer.HOUSEHOLD, HabitLayer.PERSON, HabitLayer.CONTEXT):
        deviation = prediction.deviation(layer)
        reconstructed = {
            location: reconstructed[location] * deviation[location] for location in LOCATIONS
        }
    for location in LOCATIONS:
        assert reconstructed[location] == pytest.approx(
            prediction.probabilities[location], abs=1e-12
        )


def test_multiplying_the_levels_themselves_is_a_different_distribution() -> None:
    """Documents why §4.2's original formula had to be corrected.

    Fails only if the naive product happens to coincide with the posterior,
    which would mean the levels carry no distinct information at all.
    """

    model = layered()
    for index in range(6):
        model.update(evidence(LOCATIONS[0], index=index))
    prediction = model.predict(**QUERY)
    naive = {
        location: (
            prediction.layer_probabilities[HabitLayer.COMMON][location]
            * prediction.layer_probabilities[HabitLayer.HOUSEHOLD][location]
            * prediction.layer_probabilities[HabitLayer.PERSON][location]
        )
        for location in LOCATIONS
    }
    total = sum(naive.values())
    naive = {location: value / total for location, value in naive.items()}
    assert naive[LOCATIONS[0]] != pytest.approx(prediction.probabilities[LOCATIONS[0]], abs=1e-6)


def test_the_common_layer_has_no_parent_to_deviate_from() -> None:
    model = layered()
    model.update(evidence(LOCATIONS[0]))
    with pytest.raises(ValueError, match="no parent"):
        model.predict(**QUERY).deviation(HabitLayer.COMMON)


# ---------------------------------------------------------------------------
# §4.2's stability requirement, made mechanical
# ---------------------------------------------------------------------------


def test_one_anomaly_cannot_overturn_a_long_standing_regularity() -> None:
    """`§4.2`: 不能因一次异常彻底覆盖长期规律.

    Fails if concentration stops acting as an evidence threshold.
    """

    model = layered()
    for index in range(20):
        model.update(evidence(LOCATIONS[0], index=index))
    before = model.predict(**QUERY).probabilities[LOCATIONS[0]]
    model.update(evidence(LOCATIONS[1], index=20))
    after = model.predict(**QUERY)
    assert after.probabilities[LOCATIONS[0]] > 0.5
    assert after.probabilities.get(LOCATIONS[0], 0.0) < before


def test_sustained_personal_evidence_does_eventually_override_the_prior() -> None:
    """The other half of §4.2: personalization must be able to win."""

    prior = {LOCATIONS[0]: 0.9, LOCATIONS[1]: 0.05, LOCATIONS[2]: 0.05}
    model = layered(common_prior=prior)
    for index in range(40):
        model.update(evidence(LOCATIONS[1], index=index))
    prediction = model.predict(**QUERY)
    assert prediction.probabilities[LOCATIONS[1]] > prediction.probabilities[LOCATIONS[0]]


def test_concentration_sets_how_many_observations_a_level_needs() -> None:
    """``κ`` is the interpretable knob the additive weights never were."""

    slow = layered(concentration=LayerConcentration(household=4.0, person=4.0, context=20.0))
    fast = layered(concentration=LayerConcentration(household=4.0, person=4.0, context=1.0))
    for index in range(5):
        item = evidence(LOCATIONS[1], index=index)
        slow.update(item)
        fast.update(item)
    assert (
        fast.predict(**QUERY).probabilities[LOCATIONS[1]]
        > (slow.predict(**QUERY).probabilities[LOCATIONS[1]])
    )


# ---------------------------------------------------------------------------
# RQ8 isolation carried into the layering
# ---------------------------------------------------------------------------


def test_unknown_actor_mass_never_reaches_a_resident_layer() -> None:
    """访客污染 must stop at the household level."""

    model = layered()
    for index in range(8):
        model.update(
            evidence(
                LOCATIONS[2],
                index=index,
                posterior={UNKNOWN: 1.0},
            )
        )
    report = model.evidence_report(**QUERY)
    assert report.layer_counts[HabitLayer.PERSON] == pytest.approx(0.0)
    assert report.layer_counts[HabitLayer.CONTEXT] == pytest.approx(0.0)
    assert report.layer_counts[HabitLayer.HOUSEHOLD] == pytest.approx(8.0)


def test_a_non_resident_cannot_open_a_person_layer() -> None:
    model = layered(resident_actor_keys=(OWNER,))
    for index in range(4):
        model.update(evidence(LOCATIONS[1], actor=HOUSEMATE, index=index))
    report = model.evidence_report(
        household_id=HOUSEHOLD,
        person_id=HOUSEMATE,
        object_instance_id=OBJECT,
        context_key="weekday",
    )
    assert report.layer_counts[HabitLayer.PERSON] == pytest.approx(0.0)
    assert report.layer_counts[HabitLayer.HOUSEHOLD] == pytest.approx(4.0)


def test_soft_actor_posterior_splits_one_unit_of_evidence() -> None:
    """A 0.7/0.3 posterior must not create 1.0 + 1.0 units of person evidence."""

    model = layered()
    model.update(evidence(LOCATIONS[0], posterior={OWNER: 0.7, HOUSEMATE: 0.3}))
    owner_report = model.evidence_report(**QUERY)
    housemate_report = model.evidence_report(
        household_id=HOUSEHOLD,
        person_id=HOUSEMATE,
        object_instance_id=OBJECT,
        context_key="weekday",
    )
    assert owner_report.layer_counts[HabitLayer.CONTEXT] == pytest.approx(0.7)
    assert housemate_report.layer_counts[HabitLayer.CONTEXT] == pytest.approx(0.3)
    assert owner_report.evidence_multiplicity == pytest.approx(1.0)
    assert housemate_report.evidence_multiplicity == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# The M17 firewall still holds
# ---------------------------------------------------------------------------


def test_a_model_prediction_cannot_train_itself() -> None:
    model = layered()
    record_id = uuid4()
    prediction_evidence = HabitLearningEvidence(
        metadata=BaseRecordMetadata(
            record_id=record_id,
            schema_name="cpswm.HabitLearningEvidence",
            schema_version="0.1.0",
            household_id=HOUSEHOLD,
            session_id=uuid4(),
            recorded_time=START,
            source_type=SourceType.MODEL,
            source_id="rq5-test",
            trace_id=uuid4(),
        ),
        object_instance_id=OBJECT,
        location_id=LOCATIONS[0],
        event_time=START,
        context_key="weekday",
        actor_posterior={OWNER: 1.0},
        evidence_source=HabitEvidenceSource.MODEL_PREDICTION,
        proposed_training_weight=1.0,
        source_record_ids=(record_id,),
    )
    assert model.update(prediction_evidence) == 0.0
    assert model.observations_applied == 0.0


def test_evidence_outside_the_candidate_set_is_rejected_not_ignored() -> None:
    model = layered()
    with pytest.raises(ValueError, match="outside the declared candidate set"):
        model.update(evidence(uuid4()))


def test_order_does_not_change_the_posterior() -> None:
    """Exchangeable evidence must give an exchangeable answer."""

    plan = [
        (LOCATIONS[0], OWNER, "weekday"),
        (LOCATIONS[1], OWNER, "weekend"),
        (LOCATIONS[2], HOUSEMATE, "weekday"),
        (LOCATIONS[0], OWNER, "weekday"),
    ]
    forward = layered()
    backward = layered()
    for index, (location, actor, context) in enumerate(plan):
        forward.update(evidence(location, actor=actor, context=context, index=index))
    for index, (location, actor, context) in enumerate(reversed(plan)):
        backward.update(evidence(location, actor=actor, context=context, index=index))
    left = forward.predict(**QUERY).probabilities
    right = backward.predict(**QUERY).probabilities
    for location in LOCATIONS:
        assert left[location] == pytest.approx(right[location])


def test_layer_weight_reports_how_far_a_level_moved_off_its_parent() -> None:
    model = layered()
    empty = model.predict(**QUERY)
    assert empty.layer_weight[HabitLayer.CONTEXT] == pytest.approx(0.0)
    assert empty.deepest_layer is HabitLayer.COMMON
    for location in LOCATIONS:
        assert empty.probabilities[location] == pytest.approx(1.0 / len(LOCATIONS))

    for index in range(10):
        model.update(evidence(LOCATIONS[0], index=index))
    warm = model.predict(**QUERY)
    assert warm.layer_weight[HabitLayer.CONTEXT] > 0.5
    assert warm.deepest_layer is HabitLayer.CONTEXT


def test_config_payload_is_deterministic() -> None:
    assert layered().config_payload() == layered().config_payload()
