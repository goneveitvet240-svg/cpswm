from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    BeliefHypothesis,
    BeliefSnapshot,
    BeliefVariableType,
    InputWatermark,
    ObservationLikelihoodModel,
    ObservationLikelihoodRequest,
    Pose3D,
    PosteriorMixin,
    ProjectionCheckpoint,
    RebuildCostEstimate,
    SourceType,
)


def watermark(now, seq=12):
    return InputWatermark(
        global_commit_seq=seq,
        transaction_id=uuid4(),
        source_local_seq={"M13": 7, "M14": 4, "M15": 9},
        recorded_at=now,
    )


def hypothesis(label, probability, group="cup-location"):
    return BeliefHypothesis(
        label=label,
        state={"place": label},
        posterior=PosteriorMixin(
            posterior_probability=probability,
            normalization_group=group,
        ),
    )


def test_belief_distribution_must_sum_to_one(metadata_factory, interval, now):
    with pytest.raises(ValidationError):
        BeliefSnapshot(
            metadata=metadata_factory(schema_name="cpswm.BeliefSnapshot"),
            projection_version=1,
            input_watermark=watermark(now),
            valid_time=interval,
            belief_key="Cup_17.location",
            variable_type=BeliefVariableType.LOCATION,
            hypotheses=(hypothesis("Kitchen", 0.6), hypothesis("Desk", 0.3)),
            inference_model_version="bayes-baseline@0.1",
        )


def test_belief_snapshot_is_rebuildable_from_matching_checkpoint(metadata_factory, interval, now):
    checkpoint_id = uuid4()
    estimate = RebuildCostEstimate(
        rebuild_from_checkpoint_id=checkpoint_id,
        records_to_replay=120,
        estimated_wall_time_ms=25,
        estimated_peak_memory_bytes=4096,
        estimator_version="linear@0.1",
    )
    snapshot = BeliefSnapshot(
        metadata=metadata_factory(schema_name="cpswm.BeliefSnapshot"),
        projection_version=2,
        input_watermark=watermark(now),
        valid_time=interval,
        belief_key="Cup_17.location",
        variable_type=BeliefVariableType.LOCATION,
        hypotheses=(hypothesis("Kitchen", 0.6), hypothesis("Desk", 0.4)),
        inference_model_version="bayes-baseline@0.1",
        rebuild_from_checkpoint_id=checkpoint_id,
        rebuild_cost_estimate=estimate,
    )
    assert snapshot.rebuild_cost_estimate.records_to_replay == 120
    assert "evidence_reliability" not in snapshot.model_dump_json()


def test_checkpoint_invalidation_requires_reason(metadata_factory, now):
    with pytest.raises(ValidationError):
        ProjectionCheckpoint(
            metadata=metadata_factory(schema_name="cpswm.ProjectionCheckpoint"),
            input_watermark=watermark(now),
            projection_snapshot_refs=(uuid4(),),
            inference_model_version="bayes-baseline@0.1",
            valid=False,
        )


def test_observation_likelihood_composes_visibility_and_detection(metadata_factory, interval):
    model = ObservationLikelihoodModel(
        metadata=metadata_factory(schema_name="cpswm.ObservationLikelihoodModel"),
        request_id=uuid4(),
        p_visible_given_state=0.8,
        p_detect_given_visible_state=0.75,
        p_false_positive=0.02,
        label_confusion_distribution={"cup": 0.9, "bowl": 0.1},
        p_observation_given_state_action={"detected": 0.6, "not_detected": 0.4},
        calibration_domain="sim-household-v0",
        validity_scope=interval,
        geometry_model_version="visibility@0.1",
        perception_model_version="detector@0.1",
    )
    assert model.p_detect_given_state_action == pytest.approx(0.6)


def test_observation_likelihood_distribution_must_normalize(metadata_factory, interval):
    with pytest.raises(ValidationError):
        ObservationLikelihoodModel(
            metadata=metadata_factory(schema_name="cpswm.ObservationLikelihoodModel"),
            request_id=uuid4(),
            p_visible_given_state=0.8,
            p_detect_given_visible_state=0.75,
            p_false_positive=0.02,
            p_observation_given_state_action={"detected": 0.6, "not_detected": 0.3},
            calibration_domain="sim-household-v0",
            validity_scope=interval,
            geometry_model_version="visibility@0.1",
            perception_model_version="detector@0.1",
        )


def test_likelihood_request_rejects_unnormalized_pose(metadata_factory, interval):
    with pytest.raises(ValidationError):
        ObservationLikelihoodRequest(
            metadata=metadata_factory(
                schema_name="cpswm.ObservationLikelihoodRequest",
                source_type=SourceType.MODEL,
            ),
            hypothesis_ref=uuid4(),
            state_hypothesis={"location": "Kitchen"},
            viewpoint_pose=Pose3D(frame_id="map", x=0, y=0, z=1, qx=0, qy=0, qz=0, qw=2),
            sensor_profile_id="rgbd@0.1",
            scene_snapshot_id=uuid4(),
            perception_model_version="detector@0.1",
            observation_space=("detected", "not_detected"),
            valid_time=interval,
        )
