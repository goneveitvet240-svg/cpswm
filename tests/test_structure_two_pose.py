"""Synthetic geometry/arithmetic checks, not real pose perception or training."""

from dataclasses import replace
from datetime import UTC, datetime
from math import pi
from uuid import UUID

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from cpswm.contracts.likelihoods import Pose3D
from cpswm.system.structure_two_conditional_updates import (
    ConditionalMeasurement,
    rebuild_conditional_state,
)
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState
from cpswm.system.structure_two_pose import PoseState, apply_pose_delta, pose_residual


def state(rotation=None):
    q = (rotation or Rotation.identity()).as_quat()
    return PoseState(
        object_instance_id=UUID(int=1),
        valid_at=datetime(2026, 9, 13, tzinfo=UTC),
        pose=Pose3D(frame_id="world", x=1, y=2, z=3, qx=q[0], qy=q[1], qz=q[2], qw=q[3]),
    )


@pytest.mark.parametrize("seed", range(8))
def test_roundtrip_pose_chart_matches_rotation_matrix(seed):
    rng = np.random.default_rng(seed)
    ref = state(Rotation.random(random_state=rng))
    delta = tuple(rng.uniform(-0.5, 0.5, 6))
    actual = apply_pose_delta(ref, delta)
    assert np.allclose(pose_residual(ref, actual), delta, atol=1e-12)
    a = ref.pose
    b = actual.pose
    expected = (
        Rotation.from_quat([a.qx, a.qy, a.qz, a.qw]).as_matrix()
        @ Rotation.from_rotvec(delta[3:]).as_matrix()
    )
    assert np.allclose(Rotation.from_quat([b.qx, b.qy, b.qz, b.qw]).as_matrix(), expected)
    assert actual.valid_at == ref.valid_at


def test_quaternion_double_cover_and_noncommuting_order():
    ref = state(Rotation.from_euler("x", pi / 2))
    obs = apply_pose_delta(ref, (1.0, 0.0, 0.0, 0.0, 0.0, pi / 2))
    pose = obs.pose
    other = obs.model_copy(
        update={
            "pose": pose.model_copy(update={k: -getattr(pose, k) for k in ["qx", "qy", "qz", "qw"]})
        }
    )
    assert np.allclose(pose_residual(ref, obs), pose_residual(ref, other))
    assert np.allclose(pose_residual(ref, obs), (1, 0, 0, 0, 0, pi / 2))


@pytest.mark.parametrize(
    "field,value",
    [("object_instance_id", UUID(int=2)), ("valid_at", datetime(2026, 9, 14, tzinfo=UTC))],
)
def test_different_epoch_or_object_is_not_fused(field, value):
    ref = state()
    with pytest.raises(ValueError, match="must match"):
        pose_residual(ref, ref.model_copy(update={field: value}))


def test_frame_change_and_naive_time_rejected():
    ref = state()
    with pytest.raises(ValueError):
        pose_residual(
            ref, ref.model_copy(update={"pose": ref.pose.model_copy(update={"frame_id": "camera"})})
        )
    with pytest.raises(ValueError):
        apply_pose_delta(ref.model_copy(update={"valid_at": datetime(2026, 9, 13)}), (0,) * 6)


@pytest.mark.parametrize(
    "changes",
    [{"x": float("nan")}, {"y": float("inf")}, {"qw": 2.0}, {"frame_id": " "}, {"unexpected": 1}],
)
def test_forged_pose_instances_revalidated(changes):
    ref = state()
    p = ref.pose.model_copy(update=changes)
    with pytest.raises(ValueError):
        apply_pose_delta(ref.model_copy(update={"pose": p}), (0,) * 6)


@pytest.mark.parametrize(
    "delta", [(0,) * 5, (0, 0, 0, 0, 0, float("nan")), (0, 0, 0, pi, 0, 0), (0, 0, 0, 4, 0, 0)]
)
def test_invalid_or_ambiguous_delta_rejected(delta):
    with pytest.raises(ValueError):
        apply_pose_delta(state(), delta)


def test_pi_observation_rejected_instead_of_arbitrary_gaussian_branch():
    with pytest.raises(ValueError, match="chart cut"):
        pose_residual(state(), state(Rotation.from_rotvec([pi, 0, 0])))


def matrix(n):
    return tuple(map(tuple, np.eye(n)))


def test_six_pose_dimensions_do_not_change_two_rls_features_and_retraction():
    prior = ConditionalAnalyticState(
        (UUID(int=8),), (1.0,), matrix(2), (0.0, 0.0), matrix(6), (0.0,) * 6
    )
    z = pose_residual(state(), apply_pose_delta(state(), (1.0, 2.0, 3.0, 0.1, 0.2, 0.3)))
    m = ConditionalMeasurement(
        UUID(int=10),
        (UUID(int=11),),
        "synthetic_chart_model",
        (1.0,),
        (1.0, 2.0),
        3.0,
        0.5,
        z,
        matrix(6),
        matrix(6),
        1.0,
    )
    final = rebuild_conditional_state(prior, (m,))
    assert np.allclose(final.a, [[1.5, 1], [1, 3]])
    assert np.allclose(final.b, [1.5, 3])
    assert np.allclose(final.information, 2 * np.eye(6))
    assert np.allclose(final.information_vector, z)
    assert rebuild_conditional_state(prior, ()) == prior
    second = replace(m, evidence_cluster_id=UUID(int=12), measurement=(0.0,) * 6)
    both = rebuild_conditional_state(prior, (m, second))
    assert np.allclose(both.information, 3 * np.eye(6))
    assert rebuild_conditional_state(prior, (second,)).information_vector == (0.0,) * 6
    with pytest.raises(ValueError):
        rebuild_conditional_state(prior, (replace(m, observation_matrix=matrix(2)),))
    with pytest.raises(ValueError):
        rebuild_conditional_state(prior, (m, m))


@pytest.mark.parametrize("bad", ["empty_gaussian", "empty_rls", "matrix_mismatch"])
def test_each_analytic_block_requires_its_own_valid_dimension(bad):
    p = ConditionalAnalyticState(
        (UUID(int=8),), (1.0,), matrix(2), (0.0, 0.0), matrix(6), (0.0,) * 6
    )
    changes = {
        "empty_gaussian": {"information": (), "information_vector": ()},
        "empty_rls": {"a": (), "b": ()},
        "matrix_mismatch": {"information": matrix(2)},
    }[bad]
    with pytest.raises(ValueError):
        replace(p, **changes)
