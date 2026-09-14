"""Analytic/synthetic verification only; no real-pose calibration claim."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import numpy as np
import pytest

from cpswm.contracts.likelihoods import Pose3D
from cpswm.perception_mapping.pose_observation_model import (
    ConditionalContribution,
    ConditionalPoseInput,
    GaussianPoseObservationModel,
    PoseConditionalHistory,
    PoseLabel,
    PoseObservation,
)
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState
from cpswm.system.structure_two_pose import PoseState, apply_pose_delta


def reference():
    return PoseState(
        object_instance_id=UUID(int=1),
        valid_at=datetime(2026, 9, 15, tzinfo=UTC),
        pose=Pose3D(frame_id="test-world", x=0, y=0, z=0, qx=0, qy=0, qz=0, qw=1),
    )


def observation(index, delta, sequence="fit"):
    return PoseObservation(
        UUID(int=index),
        content_sha256((sequence, index)),
        sequence,
        "synthetic-estimator-test-only",
        "analytic-test-only",
        reference(),
        apply_pose_delta(reference(), tuple(delta)),
    )


def labels(sequence="fit", start=10):
    # Full-rank symmetric errors give a closed-form mean and covariance.
    bias = np.array([0.02, -0.01, 0.03, 0.01, 0.02, -0.01])
    errors = np.concatenate((np.eye(6), -np.eye(6))) * 0.1 + bias
    return tuple(
        PoseLabel(
            observation(start + i, row, sequence),
            reference(),
            content_sha256(("synthetic-label-for-test", start + i)),
            "independent_annotation",
        )
        for i, row in enumerate(errors)
    )


def model():
    return GaussianPoseObservationModel.fit(labels())


def prior():
    return ConditionalAnalyticState(
        (UUID(int=2), UUID(int=3)),
        (1.0, 1.0),
        ((2.0, 0.0), (0.0, 2.0)),
        (0.0, 0.0),
        tuple(tuple(row) for row in np.eye(6)),
        (0.0,) * 6,
    )


def item(index=100, delta=None):
    return ConditionalPoseInput(
        UUID(int=index),
        observation(index + 1000, delta or (0.5, 0.0, 0.0, 0.0, 0.0, 0.0), "run"),
        ConditionalContribution(
            "explicit-test-other-RB-model",
            (UUID(int=index + 2000),),
            (0.25, 0.75),
            (1.0, 2.0),
            3.0,
            0.5,
            1.0,
        ),
    )


def history():
    return PoseConditionalHistory(model=model(), reference=reference(), prior=prior())


def test_fitted_bias_covariance_and_heldout_likelihood_match_closed_form():
    m = model()
    expected_bias = [0.02, -0.01, 0.03, 0.01, 0.02, -0.01]
    assert np.allclose(m.bias, expected_bias)
    assert np.allclose(m.covariance, np.eye(6) * (0.02 / 11))
    result = m.evaluate(labels("heldout", 30))
    assert result["mean_squared_mahalanobis"] == pytest.approx(5.5)
    expected = 0.5 * (6 * np.log(2 * np.pi) + 6 * np.log(0.02 / 11) + 5.5)
    assert result["mean_nll"] == pytest.approx(expected)
    assert result["scientific_acceptance"] == "NOT_DECIDED"


def test_measurement_consumption_updates_existing_three_block_type():
    h = history()
    final = h.upsert(item())
    z = np.array(item().observation.residual()) - model().bias
    assert final.alpha == (1.25, 1.75)
    assert final.a == ((2.5, 1.0), (1.0, 4.0))
    assert final.b == (1.5, 3.0)
    assert np.allclose(final.information, np.eye(6) * 551)
    assert np.allclose(final.information_vector, 550 * z)
    assert final.reference.startswith("conditional-statistics:")


def test_late_correction_retraction_and_graph_recovery_equal_full_recomputation():
    h = history()
    first, second = item(), item(200, (0.2, 0.0, 0.0, 0.0, 0.0, 0.0))
    h.upsert(first)
    h.upsert(second)
    codec = StateCodec()
    recovered = codec.loads(codec.dumps(h))
    assert recovered.state == h.state
    corrected = replace(
        first, observation=observation(1100, (-0.3, 0.0, 0.0, 0.0, 0.0, 0.0), "run")
    )
    updated = recovered.upsert(corrected)
    full = history()
    full.upsert(corrected)
    assert updated == full.upsert(second)
    removed = recovered.retract(second.evidence_cluster_id)
    only = history()
    assert removed == only.upsert(corrected)
    assert recovered.retract(first.evidence_cluster_id) == prior()
    assert h.retained_inputs == (first, second)


def test_unidentified_noise_and_same_sequence_holdout_are_rejected():
    with pytest.raises(ValueError, match="at least seven"):
        GaussianPoseObservationModel.fit(labels()[:6])
    degenerate = tuple(
        replace(x, observation=replace(x.observation, observed=reference())) for x in labels()
    )
    with pytest.raises(ValueError, match="identify"):
        GaussianPoseObservationModel.fit(degenerate)
    with pytest.raises(ValueError, match="held-out"):
        model().evaluate(labels(start=200))


@pytest.mark.parametrize("change", ["frame", "epoch", "object", "chart", "domain", "estimator"])
def test_incompatible_pose_input_does_not_change_any_statistic(change):
    h = history()
    h.upsert(item())
    bad = item(200)
    obs = bad.observation
    if change in {"domain", "estimator"}:
        obs = replace(
            obs, **{"calibration_domain" if change == "domain" else "estimator_id": "other"}
        )
    else:
        r = obs.reference.model_copy(deep=True)
        if change == "frame":
            r = r.model_copy(update={"pose": r.pose.model_copy(update={"frame_id": "other"})})
        elif change == "epoch":
            r = r.model_copy(update={"valid_at": datetime(2026, 9, 16, tzinfo=UTC)})
        elif change == "object":
            r = r.model_copy(update={"object_instance_id": UUID(int=999)})
        else:
            r = apply_pose_delta(r, (0.0, 0.0, 0.0, 0.1, 0.0, 0.0))
        obs = replace(obs, reference=r)
    before = h.state
    with pytest.raises(ValueError):
        h.upsert(replace(bad, observation=obs))
    assert h.state == before


def test_unknown_retraction_duplicate_source_and_invalid_terms_are_atomic():
    h = history()
    h.upsert(item())
    before = h.state
    with pytest.raises(ValueError, match="absent"):
        h.retract(UUID(int=999))
    with pytest.raises(ValueError, match="multiple evidence"):
        h.upsert(replace(item(), evidence_cluster_id=UUID(int=999)))
    bad = item(200)
    with pytest.raises(ValueError):
        h.upsert(replace(bad, contribution=replace(bad.contribution, location_mass=(-1.0, 2.0))))
    assert h.state == before


def test_zero_other_blocks_stay_zero_and_model_configuration_is_detached():
    m = model()
    h = PoseConditionalHistory(model=m, reference=reference(), prior=prior())
    x = item()
    x = replace(x, contribution=replace(x.contribution, location_mass=(0.0, 0.0), rls_weight=0.0))
    result = h.upsert(x)
    assert (result.alpha, result.a, result.b) == (prior().alpha, prior().a, prior().b)
    assert result.information != prior().information
    object.__setattr__(x.observation.observed.pose, "x", 999)
    assert h.state == result


def test_equivalent_quaternion_reference_is_consumed_identically():
    value = item()
    r = value.observation.reference
    negative = r.model_copy(update={"pose": r.pose.model_copy(update={"qw": -1.0})})
    equivalent = replace(value, observation=replace(value.observation, reference=negative))
    assert history().upsert(value) == history().upsert(equivalent)


def test_finite_heldout_pose_cannot_emit_infinite_metrics():
    row = labels("heldout", 30)[0]
    far = apply_pose_delta(reference(), (1e200, 0.0, 0.0, 0.0, 0.0, 0.0))
    row = replace(row, observation=replace(row.observation, observed=far))
    with pytest.raises(ValueError, match="overflow"):
        model().evaluate((row,))
