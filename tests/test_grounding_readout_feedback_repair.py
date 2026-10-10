"""Depth ambiguity, actor-source boundaries and configured live readout regressions."""

from dataclasses import replace
from uuid import uuid4

import numpy as np
import pytest
from structure_two_backbone_wiring_probe import BackboneWiringProbe
from test_natural_mask_surface import wires

from cpswm.perception_mapping.depth_validity import background_continuity
from cpswm.perception_mapping.natural_mask_surface import select_surface
from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd
from cpswm.system.prototype_spine import ActionReadout
from cpswm.system.runtime_readout import current_action_readout
from cpswm.system.structure_two_production_system import _snapshot_adaptive_ciav_input


def test_flat_background_is_unknown_but_opaque_surface_remains_available():
    raw, cutoff = wires(tuple(uuid4() for _ in range(3)))
    camera, depth = decode_unity_rgbd(raw, cutoff=cutoff)
    probability = np.zeros(depth.shape, np.float32)
    probability[20:60, 30:70] = 0.9
    opaque = select_surface(camera, depth, probability)
    assert opaque["status"] == "SURFACE_CANDIDATE"
    flat = select_surface(camera, np.full_like(depth, 3), probability)
    assert flat["status"] == "UNKNOWN_BACKGROUND_CONTINUOUS_DEPTH"
    assert flat["world_point_m"] is None
    assert flat["ambiguous_pixel_uv"] == [30, 20]
    # A single depth glitch cannot be selected instead of the ambiguous maximum.
    faulty = np.full_like(depth, 3)
    faulty[59, 69] = 2
    result = select_surface(camera, faulty, probability)
    assert result["world_point_m"] is None


def test_tilted_plane_and_insufficient_surround_are_explicit():
    v, u = np.indices((96, 96))
    depth = (1 / (0.02 * u / 96 + 0.04 * v / 96 + 0.3)).astype(np.float32)
    mask = np.zeros((96, 96), bool)
    mask[20:60, 30:70] = True
    flag, info = background_continuity(depth, mask)
    assert flag[mask].all()
    _, info = background_continuity(depth, np.ones_like(mask))
    assert info["status"] == "INSUFFICIENT_SURROUND_SUPPORT"


def test_presence_only_cannot_upgrade_actor_but_explicit_bound_actor_source_can():
    probe = BackboneWiringProbe.build()
    transition = probe.transition_for(probe.observed_days()[0])
    value = probe.ciav_input(transition, owner_likelihood=0.8)
    assert all(set(row.values()) == {1.0} for row in value.effective_actor_likelihoods.values())
    result, _ = probe.run_direct_p5(transition, ciav_input=value)
    assert result.ciav_receipt.evidence.actor_posterior == pytest.approx(
        result.primary_result.actor_posterior
    )
    actor_probe = BackboneWiringProbe.build()
    transition = actor_probe.transition_for(actor_probe.observed_days()[0])
    source_bound = replace(
        actor_probe.ciav_input(transition), actor_evidence_source_sha256="a" * 64
    )
    result, _ = actor_probe.run_direct_p5(transition, ciav_input=source_bound)
    prior = result.primary_result.actor_posterior
    factors = source_bound.effective_actor_likelihoods[result.ciav_receipt.outcome_label]
    normalizer = sum(prior[k] * factors[k] for k in prior)
    assert result.ciav_receipt.evidence.actor_posterior == pytest.approx(
        {k: prior[k] * factors[k] / normalizer for k in prior}
    )
    assert (
        value.content_sha256 != replace(value, actor_evidence_source_sha256="a" * 64).content_sha256
    )
    detached = _snapshot_adaptive_ciav_input(source_bound)
    assert detached.actor_evidence_source_sha256 == "a" * 64
    assert detached.content_sha256 == source_bound.content_sha256
    with pytest.raises(ValueError, match="SHA256"):
        replace(value, actor_evidence_source_sha256="fake")


def test_previously_selected_readout_reaches_current_runtime(tmp_path):
    from run_correction_replay_comparison import build

    probe, _, _stream, store, _ = build(tmp_path / "runtime.db", seed=7, source="a" * 64)
    assert probe.system.core._action_readout == current_action_readout()
    assert probe.system.core._action_readout.readout == ActionReadout.DUAL_TIMESCALE_REVERSIBLE
    store.close()


def test_ambiguous_depth_cannot_seed_geometric_identity_references():
    from cpswm.perception_mapping.mask_surface_sequence import _reference_feature_rows

    raw, cutoff = wires(tuple(uuid4() for _ in range(3)))
    camera, depth = decode_unity_rgbd(raw, cutoff=cutoff)
    probability = np.zeros(depth.shape, np.float32)
    probability[20:60, 30:70] = 0.9
    points = ((35.0, 25.0), (40.0, 30.0), (45.0, 35.0), (50.0, 40.0))
    opaque = _reference_feature_rows(camera, depth, probability, (0, 1, 2, 3), points, {})
    assert all(row["valid_depth"] for row in opaque)
    flat = _reference_feature_rows(
        camera, np.full_like(depth, 3), probability, (0, 1, 2, 3), points, {}
    )
    assert all(not row["valid_depth"] and row["current_world_point_m"] is None for row in flat)
