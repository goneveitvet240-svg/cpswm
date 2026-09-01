"""RQ1 统一观察机制契约: 机会, 倾向, 遮挡, 缺失机制必须一起旅行.

    RQ1 长期选择性观察 -- 路线正确 -- 接入前缺口: 统一机会, 倾向, 遮挡, 缺失机制契约.

The tests are grouped by which of the four the case is about, and each says
what its failure would let through.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts.base import BaseRecordMetadata, SourceType
from cpswm.contracts.habit_learning import (
    HabitEvidenceSource,
    HabitLearningEvidence,
    IncidentalObservationContext,
    ObservationDetectionResult,
    ObservationMode,
    ObservationOpportunityRecord,
    ObservationOutcome,
    OcclusionState,
)
from cpswm.contracts.observation_mechanism import (
    STRONG_EXCLUSION_QUALITY_FLOOR,
    CorrectionValidity,
    MissingnessMechanism,
    ObservationMechanismEnvelope,
    PropensityRecord,
    validate_habit_update_binding,
)

HOUSEHOLD = uuid4()
SESSION = uuid4()
TRACE = uuid4()
OBJECT = uuid4()
LOCATION = uuid4()
MOMENT = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def metadata(record_id: UUID, schema: str, source: SourceType = SourceType.SENSOR):  # type: ignore[no-untyped-def]
    return BaseRecordMetadata(
        record_id=record_id,
        schema_name=schema,
        schema_version="0.1.0",
        household_id=HOUSEHOLD,
        session_id=SESSION,
        recorded_time=MOMENT,
        source_type=source,
        source_id="rq1-test",
        trace_id=TRACE,
    )


def opportunity(
    *,
    record_id: UUID | None = None,
    selected: bool = True,
    occlusion: OcclusionState = OcclusionState.CLEAR,
    coverage: float = 0.9,
    p_visible: float = 0.8,
    p_detect: float = 0.9,
    with_context: bool = True,
) -> ObservationOpportunityRecord:
    identifier = record_id or uuid4()
    context = (
        IncidentalObservationContext(
            primary_task_id=uuid4(),
            primary_task_goal="fetch the cup",
            observation_mode=ObservationMode.INCIDENTAL,
            frame_id="map",
            field_of_view_coverage=coverage,
            occlusion_state=occlusion,
            additional_action_cost=0.0,
            selection_probability=0.6,
            observation_likelihood_model_id="m09-likelihood@0.1",
            observed_time=MOMENT,
        )
        if with_context
        else None
    )
    return ObservationOpportunityRecord(
        metadata=metadata(identifier, "cpswm.ObservationOpportunityRecord"),
        observation_action_id=uuid4(),
        opportunity_time=MOMENT,
        selected=selected,
        selection_probability=0.6,
        p_visible_given_state=p_visible,
        p_detect_given_visible=p_detect,
        likelihood_model_id="m09-likelihood@0.1",
        incidental_context=context,
    )


def detection(
    source: ObservationOpportunityRecord,
    *,
    outcome: ObservationOutcome = ObservationOutcome.DETECTED,
    negative_strength: float = 0.0,
) -> ObservationDetectionResult:
    detected = outcome == ObservationOutcome.DETECTED
    return ObservationDetectionResult(
        metadata=metadata(uuid4(), "cpswm.ObservationDetectionResult"),
        observation_opportunity_id=source.metadata.record_id,
        outcome=outcome,
        detected_object_instance_id=OBJECT if detected else None,
        detected_location_id=LOCATION if detected else None,
        detection_time=MOMENT if detected else None,
        negative_evidence_strength=negative_strength,
    )


def propensity(*, weight: float = 1.0, raw: float = 0.432) -> PropensityRecord:
    return PropensityRecord(mode="stabilized", raw_propensity=raw, applied_weight=weight)


def envelope(**kwargs):  # type: ignore[no-untyped-def]
    source = kwargs.pop("opportunity", None) or opportunity()
    kwargs.setdefault("detection", detection(source))
    return ObservationMechanismEnvelope(
        metadata=metadata(uuid4(), "cpswm.ObservationMechanismEnvelope"),
        opportunity=source,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 缺失机制 -- the piece that existed nowhere
# ---------------------------------------------------------------------------


def test_an_undeclared_mechanism_cannot_justify_a_correction() -> None:
    """Silence is not MAR.

    Fails if a corrected weight can be applied without saying why.  That is the
    exact state the code was in: ``PropensityCorrectionMode.STABILIZED`` and no
    field anywhere recording whether the assumption behind it holds.
    """

    with pytest.raises(ValidationError, match="silence is not MAR"):
        envelope(propensity=propensity(weight=2.3))


def test_an_uncorrected_weight_needs_no_mechanism() -> None:
    """The honest default must stay usable."""

    item = envelope(propensity=propensity(weight=1.0))
    assert item.correction_validity is CorrectionValidity.UNCORRECTED
    assert item.effective_weight == 1.0


def test_mar_must_name_the_covariates_it_conditions_on() -> None:
    """ "Missing at random" without covariates is an assertion, not a model.

    Fails if MAR can be declared bare, which is how an unjustified correction
    gets a justification-shaped label.
    """

    with pytest.raises(ValidationError, match="name the covariates"):
        envelope(
            missingness_mechanism=MissingnessMechanism.MAR,
            propensity=propensity(weight=2.3),
        )
    item = envelope(
        missingness_mechanism=MissingnessMechanism.MAR,
        conditioning_covariates=("primary_task", "room", "time_of_day"),
        propensity=propensity(weight=2.3),
    )
    assert item.correction_validity is CorrectionValidity.UNBIASED_UNDER_DECLARED_MECHANISM


def test_mcar_cannot_secretly_condition_on_anything() -> None:
    with pytest.raises(ValidationError, match="conditions on nothing"):
        envelope(
            missingness_mechanism=MissingnessMechanism.MCAR,
            conditioning_covariates=("room",),
        )


def test_an_mnar_correction_must_record_the_bias_it_does_not_remove() -> None:
    """The realistic case for a task-driven robot.

    Fails if MNAR can be corrected silently, producing a number that looks
    corrected and is biased toward the effect being measured -- the robot looks
    *because* it suspects the object moved.
    """

    with pytest.raises(ValidationError, match="residual bias"):
        envelope(
            missingness_mechanism=MissingnessMechanism.MNAR,
            propensity=propensity(weight=2.3),
        )
    item = envelope(
        missingness_mechanism=MissingnessMechanism.MNAR,
        propensity=propensity(weight=2.3),
        residual_bias_note="robot re-checked the desk after a suspected move",
    )
    assert item.correction_validity is CorrectionValidity.BIASED_DECLARED


def test_a_bias_note_is_meaningless_outside_mnar() -> None:
    with pytest.raises(ValidationError, match="only meaningful under MNAR"):
        envelope(
            missingness_mechanism=MissingnessMechanism.MCAR,
            residual_bias_note="something",
        )


def test_correction_validity_is_derived_not_asserted() -> None:
    """A field the producer could set would eventually be set wrongly."""

    assert "correction_validity" not in ObservationMechanismEnvelope.model_fields


# ---------------------------------------------------------------------------
# 遮挡 -- §7's two prohibitions that had no enforcement
# ---------------------------------------------------------------------------


def test_a_fully_occluded_view_cannot_produce_negative_evidence() -> None:
    """`§7`: 未打开容器不能产生容器内部负证据.

    Fails if a closed cupboard can be used to rule the object out of it, which
    turns "I did not look inside" into "it is not inside".
    """

    source = opportunity(occlusion=OcclusionState.FULL, p_visible=0.0)
    with pytest.raises(ValidationError, match="fully occluded"):
        envelope(
            opportunity=source,
            detection=detection(
                source,
                outcome=ObservationOutcome.VERIFIED_ABSENCE,
                negative_strength=0.8,
            ),
        )


def test_a_low_quality_view_cannot_produce_a_strong_exclusion() -> None:
    """`§7`: 低质量视角不能产生强排除."""

    source = opportunity(coverage=STRONG_EXCLUSION_QUALITY_FLOOR / 2)
    with pytest.raises(ValidationError, match="low-quality view"):
        envelope(
            opportunity=source,
            detection=detection(
                source,
                outcome=ObservationOutcome.VERIFIED_ABSENCE,
                negative_strength=0.8,
            ),
        )


def test_unknown_occlusion_cannot_exclude_anything() -> None:
    source = opportunity(occlusion=OcclusionState.UNKNOWN)
    with pytest.raises(ValidationError, match="known occlusion state"):
        envelope(
            opportunity=source,
            detection=detection(
                source,
                outcome=ObservationOutcome.VERIFIED_ABSENCE,
                negative_strength=0.8,
            ),
        )


def test_a_clear_high_quality_view_may_verify_an_absence() -> None:
    """The prohibition must not swallow the legitimate case."""

    source = opportunity(occlusion=OcclusionState.CLEAR, coverage=0.95)
    item = envelope(
        opportunity=source,
        detection=detection(
            source, outcome=ObservationOutcome.VERIFIED_ABSENCE, negative_strength=0.8
        ),
    )
    assert item.detection is not None
    assert item.detection.supports_negative_evidence
    assert not item.supports_habit_update


def test_an_opportunity_that_could_never_detect_cannot_exclude() -> None:
    source = opportunity(occlusion=OcclusionState.CLEAR, p_visible=0.0, coverage=0.95)
    with pytest.raises(ValidationError, match="could never have detected"):
        envelope(
            opportunity=source,
            detection=detection(
                source, outcome=ObservationOutcome.VERIFIED_ABSENCE, negative_strength=0.8
            ),
        )


# ---------------------------------------------------------------------------
# 机会 -- binding
# ---------------------------------------------------------------------------


def test_a_detection_must_cite_the_opportunity_it_is_packaged_with() -> None:
    other = opportunity()
    with pytest.raises(ValidationError, match="does not cite this opportunity"):
        envelope(detection=detection(other))


def test_an_unselected_opportunity_cannot_have_detected_anything() -> None:
    source = opportunity(selected=False)
    with pytest.raises(ValidationError, match="unselected opportunity"):
        envelope(opportunity=source, detection=detection(source))


def test_an_envelope_without_a_detection_is_valid_and_supports_nothing() -> None:
    """A missed look is a first-class record; it just cannot train anything."""

    item = envelope(detection=None)
    assert not item.supports_habit_update
    assert item.observation_time == MOMENT


@pytest.mark.parametrize(
    "outcome",
    [ObservationOutcome.NOT_OBSERVED, ObservationOutcome.AMBIGUOUS],
)
def test_a_miss_or_an_ambiguity_does_not_support_a_habit_update(
    outcome: ObservationOutcome,
) -> None:
    """`§7`: not_observed 不等于不存在."""

    source = opportunity()
    item = envelope(opportunity=source, detection=detection(source, outcome=outcome))
    assert not item.supports_habit_update


# ---------------------------------------------------------------------------
# 倾向 -- the propensity record itself
# ---------------------------------------------------------------------------


def test_a_clipped_weight_must_record_the_threshold_it_hit() -> None:
    with pytest.raises(ValidationError, match="clip threshold"):
        PropensityRecord(mode="inverse", raw_propensity=0.01, applied_weight=100.0, clipped=True)


def test_a_weight_cannot_claim_to_be_clipped_above_its_own_threshold() -> None:
    with pytest.raises(ValidationError, match="cannot be clipped above"):
        PropensityRecord(
            mode="inverse",
            raw_propensity=0.5,
            applied_weight=2.0,
            clipped=True,
            minimum_propensity=0.1,
        )


def test_a_zero_propensity_is_rejected_at_the_type_level() -> None:
    """Positivity: a record that could never have been observed cannot be weighted."""

    with pytest.raises(ValidationError):
        PropensityRecord(mode="inverse", raw_propensity=0.0, applied_weight=1.0)


# ---------------------------------------------------------------------------
# The seam a habit update has to pass
# ---------------------------------------------------------------------------


def _evidence(
    source: ObservationOpportunityRecord,
    *,
    opportunity_id: UUID | None = None,
    location: UUID = LOCATION,
    event_time: datetime = MOMENT,
) -> HabitLearningEvidence:
    record_id = uuid4()
    return HabitLearningEvidence(
        metadata=metadata(record_id, "cpswm.HabitLearningEvidence"),
        object_instance_id=OBJECT,
        location_id=location,
        event_time=event_time,
        context_key="weekday",
        actor_posterior={"owner": 1.0},
        evidence_source=HabitEvidenceSource.DIRECT_OBSERVATION,
        proposed_training_weight=1.0,
        source_record_ids=(record_id,),
        observation_opportunity_id=(
            source.metadata.record_id if opportunity_id is None else opportunity_id
        ),
    )


def test_a_valid_binding_passes() -> None:
    source = opportunity()
    item = envelope(
        opportunity=source,
        missingness_mechanism=MissingnessMechanism.MAR,
        conditioning_covariates=("primary_task", "room"),
        propensity=propensity(weight=2.3),
    )
    validate_habit_update_binding(_evidence(source), item)


def test_a_habit_update_must_cite_the_opportunity_it_was_corrected_by() -> None:
    """Otherwise the weight was computed for a different look."""

    source = opportunity()
    item = envelope(opportunity=source)
    with pytest.raises(ValueError, match="different observation opportunity"):
        validate_habit_update_binding(_evidence(source, opportunity_id=uuid4()), item)


def test_a_habit_update_with_no_opportunity_is_refused() -> None:
    source = opportunity()
    item = envelope(opportunity=source)
    record_id = uuid4()
    bare = HabitLearningEvidence(
        metadata=metadata(record_id, "cpswm.HabitLearningEvidence"),
        object_instance_id=OBJECT,
        location_id=LOCATION,
        event_time=MOMENT,
        context_key="weekday",
        actor_posterior={"owner": 1.0},
        evidence_source=HabitEvidenceSource.DIRECT_OBSERVATION,
        proposed_training_weight=1.0,
        source_record_ids=(record_id,),
    )
    with pytest.raises(ValueError, match="must cite its opportunity"):
        validate_habit_update_binding(bare, item)


def test_a_habit_update_cannot_be_backed_by_a_miss() -> None:
    source = opportunity()
    item = envelope(
        opportunity=source,
        detection=detection(source, outcome=ObservationOutcome.NOT_OBSERVED),
    )
    with pytest.raises(ValueError, match="produced a detection"):
        validate_habit_update_binding(_evidence(source), item)


def test_a_habit_update_must_agree_with_what_was_detected() -> None:
    source = opportunity()
    item = envelope(opportunity=source)
    with pytest.raises(ValueError, match="location does not match"):
        validate_habit_update_binding(_evidence(source, location=uuid4()), item)
    with pytest.raises(ValueError, match="event_time does not match"):
        validate_habit_update_binding(
            _evidence(source, event_time=datetime(2026, 3, 2, tzinfo=UTC)), item
        )


def test_audit_payload_carries_everything_needed_to_judge_a_count() -> None:
    source = opportunity()
    item = envelope(
        opportunity=source,
        missingness_mechanism=MissingnessMechanism.MNAR,
        propensity=propensity(weight=2.3),
        residual_bias_note="looked because a move was suspected",
    )
    payload = item.audit_payload()
    assert payload["missingness_mechanism"] == "mnar"
    assert payload["correction_validity"] == "biased_declared"
    assert payload["residual_bias_note"]
    assert payload["supports_habit_update"] is True
    assert payload["envelope_version"].startswith("observation-mechanism@")


def test_duplicate_covariate_names_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        envelope(
            missingness_mechanism=MissingnessMechanism.MAR,
            conditioning_covariates=("room", "room"),
        )
