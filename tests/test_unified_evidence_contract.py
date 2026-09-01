from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    BaseRecordMetadata,
    DetectionFailureReason,
    EvidenceProductionMode,
    ObservationOpportunityRecord,
    ObservationOutcome,
    OcclusionState,
    OpenSetEvidenceSupport,
    SourceType,
    UnifiedEvidenceContract,
    ValidTimeInterval,
)
from cpswm.system.evaluation_operations.project_one_dataset import (
    ProjectOneDatasetRecord,
    ProjectOneEvidenceDatasetRecord,
    ProjectOneEvidenceStream,
)

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _metadata(*, source_type: SourceType, source_id: str) -> BaseRecordMetadata:
    return BaseRecordMetadata(
        schema_name="cpswm.UnifiedEvidenceContract",
        schema_version="0.1.0",
        household_id=uuid4(),
        session_id=uuid4(),
        trace_id=uuid4(),
        recorded_time=NOW + timedelta(minutes=1),
        source_type=source_type,
        source_id=source_id,
    )


def _formal_evidence() -> UnifiedEvidenceContract:
    evidence_meta = _metadata(source_type=SourceType.SENSOR, source_id="detector")
    opportunity_meta = evidence_meta.model_copy(
        update={"record_id": uuid4(), "source_id": "camera"}
    )
    opportunity = ObservationOpportunityRecord(
        metadata=opportunity_meta,
        observation_action_id=uuid4(),
        opportunity_time=NOW,
        selected=True,
        selection_probability=0.4,
        p_visible_given_state=0.7,
        p_detect_given_visible=0.8,
        likelihood_model_id="observation-model@1",
    )
    object_id = uuid4()
    return UnifiedEvidenceContract(
        metadata=evidence_meta,
        valid_time=ValidTimeInterval(start=NOW, end=NOW + timedelta(minutes=5)),
        object_instance_id=object_id,
        object_posterior={str(object_id): 0.2, "unknown_object": 0.8},
        location_posterior={"desk": 0.3, "unknown_location": 0.7},
        actor_posterior={"owner": 0.7, "unknown_actor": 0.3},
        observation_opportunity=opportunity,
        selected_for_observation=True,
        selection_probability=0.4,
        field_of_view_coverage=0.75,
        occlusion_state=OcclusionState.PARTIAL,
        container_open=False,
        detection_outcome=ObservationOutcome.AMBIGUOUS,
        detection_failure_reason=DetectionFailureReason.UNRESOLVED_IDENTITY,
        production_mode=EvidenceProductionMode.DIRECT,
        evidence_cluster_id=uuid4(),
        correlation_group_id="video-segment-41",
        within_cluster_correlation=0.8,
        effective_sample_weight=0.5,
        open_set_support=OpenSetEvidenceSupport(
            actor_keys=("owner", "unknown_actor"),
            object_instance_ids=(object_id,),
            location_keys=("desk", "unknown_location"),
            mechanism_keys=("direct_relocation", "unknown_mechanism"),
        ),
    )


def test_formal_evidence_covers_selection_sensing_time_source_correlation_and_open_set():
    evidence = _formal_evidence()
    assert evidence.actor_posterior["unknown_actor"] > 0.0
    assert evidence.observation_opportunity is not None
    assert evidence.metadata.recorded_time > evidence.valid_time.start
    assert evidence.open_set_support.unknown_object_supported
    assert evidence.within_cluster_correlation > 0.0


def test_actor_support_and_posterior_must_match_and_retain_unknown_actor():
    payload = _formal_evidence().model_dump(mode="python")
    payload["open_set_support"] = {
        **payload["open_set_support"],
        "actor_keys": ("owner", "guest", "unknown_actor"),
    }
    with pytest.raises(ValidationError, match="must match"):
        UnifiedEvidenceContract.model_validate(payload)


def test_non_detection_requires_an_explicit_failure_reason():
    payload = _formal_evidence().model_dump(mode="python")
    payload["detection_failure_reason"] = DetectionFailureReason.NOT_APPLICABLE
    with pytest.raises(ValidationError, match="explicit failure reason"):
        UnifiedEvidenceContract.model_validate(payload)


def test_formal_project_one_stream_rejects_legacy_record_and_downgrade_is_explicit():
    evidence = _formal_evidence()
    formal = ProjectOneEvidenceDatasetRecord(
        stream_id="stream-1",
        event_id="event-1",
        subject_id="subject-1",
        context_key="evening",
        context_value=1.0,
        evidence=evidence,
    )
    stream = ProjectOneEvidenceStream(stream_id="stream-1", records=(formal,))
    projection = formal.to_legacy_baseline_input(
        actor_id="owner",
        observed_location="desk",
        legacy_method_id="legacy-test@1",
        projection_policy="explicit-test-collapse",
    )
    legacy = projection.record

    assert stream.records == (formal,)
    assert isinstance(legacy, ProjectOneDatasetRecord)
    assert legacy.observation_quality == evidence.effective_sample_weight
    assert projection.receipt.formal_evidence_record_id == str(evidence.metadata.record_id)
    with pytest.raises(TypeError, match="rejects legacy"):
        ProjectOneEvidenceStream(stream_id="stream-1", records=(legacy,))  # type: ignore[arg-type]


def test_structural_zero_opportunity_is_preserved_but_cannot_be_realized_selected():
    evidence = _formal_evidence()
    opportunity = evidence.observation_opportunity.model_copy(
        update={"selected": False, "selection_probability": 0.0}
    )
    accepted = evidence.model_copy(
        update={
            "observation_opportunity": opportunity,
            "selected_for_observation": False,
            "selection_probability": 0.0,
            "detection_outcome": None,
            "detection_failure_reason": DetectionFailureReason.NOT_APPLICABLE,
        }
    )
    assert (
        UnifiedEvidenceContract.model_validate(accepted.model_dump()).selection_probability == 0.0
    )
    with pytest.raises(ValidationError, match="realized selected observation"):
        UnifiedEvidenceContract.model_validate(
            accepted.model_copy(
                update={
                    "observation_opportunity": opportunity.model_copy(update={"selected": True}),
                    "selected_for_observation": True,
                }
            ).model_dump()
        )


def test_direct_detection_requires_bound_opportunity_and_supported_hard_keys():
    evidence = _formal_evidence()
    detected = evidence.model_copy(
        update={
            "detection_outcome": ObservationOutcome.DETECTED,
            "detection_failure_reason": DetectionFailureReason.NOT_APPLICABLE,
            "detected_object_key": str(evidence.object_instance_id),
            "detected_location_key": "desk",
        }
    )
    with pytest.raises(ValidationError, match="selected observation opportunity"):
        UnifiedEvidenceContract.model_validate(
            detected.model_copy(
                update={
                    "observation_opportunity": None,
                    "selected_for_observation": False,
                    "selection_probability": None,
                }
            ).model_dump()
        )
    with pytest.raises(ValidationError, match="location posterior"):
        UnifiedEvidenceContract.model_validate(
            detected.model_copy(update={"detected_location_key": "cabinet"}).model_dump()
        )


def test_inferred_or_model_evidence_requires_parent_references():
    evidence = _formal_evidence()
    payload = evidence.model_dump(mode="python")
    payload["metadata"] = evidence.metadata.model_copy(update={"source_type": SourceType.MODEL})
    payload["production_mode"] = EvidenceProductionMode.MODEL
    with pytest.raises(ValidationError, match="parent evidence references"):
        UnifiedEvidenceContract.model_validate(payload)


def test_opportunity_and_evidence_scope_must_match():
    evidence = _formal_evidence()
    opportunity = evidence.observation_opportunity
    payload = evidence.model_dump(mode="python")
    payload["observation_opportunity"] = opportunity.model_copy(
        update={"metadata": opportunity.metadata.model_copy(update={"session_id": uuid4()})}
    )
    with pytest.raises(ValidationError, match="provenance scope"):
        UnifiedEvidenceContract.model_validate(payload)
