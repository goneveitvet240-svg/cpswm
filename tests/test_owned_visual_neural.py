"""Owned visual conditioning, complete forged positives and consequences.

Images and semantic events are controlled fixtures, not natural accuracy evidence.
PYTEST_DONT_REWRITE: fixture dependencies have source-bound implementations.
"""

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from math import exp, fsum
from uuid import uuid4

import pytest
from test_continuous_state_recovery import DurableFixtureProducer, store_at
from test_native_joint_production import JointFixture
from test_native_neural_production import checkpoints as _checkpoints
from test_native_neural_production import context_for, stage
from test_native_neural_production import cpu_threads as _threads
from test_owned_rgbd_support import RGBDCamera, RGBDSupportDecoder
from test_structure_two_adaptive_runtime import (
    _adaptive_system_and_transition,
    _ciav_input,
    _features,
)
from test_structure_two_continuous_input import raw_for

from cpswm.data_preflight.proposal_samples import export_context
from cpswm.data_preflight.typed_proposal_networks import ARMS
from cpswm.system.native_neural_production import NeuralNativeProducer, materialize
from cpswm.system.native_visual_source import NativeVisualAuthority
from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput, GroundedTransition
from cpswm.system.structure_two_particle_workspace import native_content_sha256

checkpoints = _checkpoints
cpu_threads = _threads


def producer_for(checkpoints, *, visual=True):
    path, pin = checkpoints[ARMS[0]]
    return NeuralNativeProducer(
        JointFixture(), path, manifest_sha256=pin, use_owned_visual_context=visual
    )


def setup_visual(path, joint):
    system, transition = _adaptive_system_and_transition()
    ciav = _ciav_input(transition)

    def builder(system, item, when, step):
        return AdaptiveExecutionContext(
            router_features=_features(system, step=step, route="P0_FAST_LOCAL"),
            step_index=step,
            ciav_input=ciav,
        )

    backend, store = DurableFixtureProducer(), store_at(path)
    meta = transition.after.metadata
    stream = ContinuousEvidenceInput(
        system=system,
        execution_lane="registered_p5_first",
        household_id=meta.household_id,
        session_id=meta.session_id,
        trace_id=meta.trace_id,
        producer=backend,
        context_builder=builder,
        state_store=store,
        joint_producer=joint,
        observation_decoder=RGBDSupportDecoder(),
    )
    when = ciav.opportunity_time
    ids = stream.admit((raw_for(transition),), received_at=when)
    command = stream.prepare_observation(
        action="RotateRight",
        degrees=30,
        reason="controlled acquisition before semantic publication",
        source_ids=ids,
        decision_time=when,
    )
    delivery = stream.execute_observation(command, executor=RGBDCamera(stream._scope))
    backend.output = GroundedTransition(transition, ids, "fixture", "fixture-not-calibrated")
    stream.advance(cutoff=delivery.received_at)
    return stream, store, builder, delivery.received_at


def produced_visual(stream, joint, when):
    context = replace(context_for(stream, when), visual_source=stream._native_visual_source(when))
    return context, joint.produce(context)


def test_owned_geometry_enters_actual_network_and_preserves_exact_target(tmp_path, checkpoints):
    joint = producer_for(checkpoints)
    stream, store, builder, _ = setup_visual(tmp_path / "db", joint)
    try:
        ledger = stream._system.core._hybrid_loop.ledger.export_state()
        stream.produce_joint_posterior()
        proof = joint._last_evidence
        pixels = proof.context.visible.pixel_observations
        assert len(pixels) == 1 and len(pixels[0].candidates) == 3
        assert sum(len(c.samples) for c in pixels[0].surface_geometry.candidates) == 9
        payload = str(export_context(proof.context))
        assert "box_surface_geometry" in payload and "nominal_world_xyz_m" in payload
        assert pixels[0].surface_geometry.camera.scene_sha256 not in payload
        assert proof.visual_source_sha256 in stream._system.core._particle_workspace.visual_sources
        # Actual ablation of only geometry, using the identical weights/support.
        ablated = proof.context.model_copy(
            update={
                "visible": proof.context.visible.model_copy(
                    update={
                        "pixel_observations": (
                            pixels[0].model_copy(update={"surface_geometry": None}),
                        )
                    }
                )
            }
        )
        scores = joint._session.score_support(context=ablated, support=proof.support)
        assert [s.probability.joint_log_probability for s in scores] != [
            s.probability.joint_log_probability for s in proof.scored
        ]
        workspace = stream._system.core._particle_workspace
        masses = [
            exp(
                r.prior_log_weight
                + r.transition_log_probability
                + r.observation_log_likelihood
                + r.posterior_projection_log_factor
                + fsum(c.log_potential for c in r.constraints)
            )
            for r in workspace.receipts
        ]
        assert [p.posterior_probability for p in workspace.batch.particle_weights] == pytest.approx(
            [m / (1 + fsum(masses)) for m in masses], abs=1e-14
        )
        view = stream.current_joint_decision_view()
        state = joint.checkpoint_state()
        resumed = ContinuousEvidenceInput.resume(
            store,
            producer=stream._producer,
            context_builder=builder,
            joint_producer=producer_for(checkpoints),
            observation_decoder=RGBDSupportDecoder(),
        )
        assert resumed.current_joint_decision_view() == view
        assert resumed._joint_producer.checkpoint_state() == state
        assert resumed._system.core._hybrid_loop.ledger.export_state() == ledger
        assert resumed.observation_history() == stream.observation_history()
    finally:
        store.close()


@pytest.mark.parametrize(
    "attack", ["pose", "candidate_omission", "geometry_omission", "future", "scope"]
)
def test_complete_real_network_forgery_is_not_a_registered_visual_source(
    tmp_path, checkpoints, attack
):
    joint = producer_for(checkpoints)
    stream, store, _, when = setup_visual(tmp_path / "db", joint)
    try:
        context, good = produced_visual(stream, joint, when)
        source = context.visual_source
        action = source.support.actions[0]
        frame = action.frames[0]
        if attack == "pose":
            geometry = frame.geometry
            camera = geometry.camera.model_copy(update={"position_m": (9.0, 8.0, 7.0)})
            rows = tuple(
                replace(
                    c,
                    samples=tuple(
                        replace(
                            s,
                            nominal_world_xyz_m=camera.world_point(*s.pixel_uv, s.rendered_depth_m),
                        )
                        for s in c.samples
                    ),
                )
                for c in geometry.candidates
            )
            frame = replace(frame, geometry=replace(geometry, camera=camera, candidates=rows))
        elif attack == "candidate_omission":
            frame = replace(
                frame,
                frame=replace(frame.frame, candidates=frame.frame.candidates[:1]),
                candidates=frame.candidates[:1],
                geometry=replace(frame.geometry, candidates=frame.geometry.candidates[:1]),
            )
        elif attack == "geometry_omission":
            frame = replace(frame, geometry=None)
        elif attack == "future":
            source = replace(source, cutoff=when + timedelta(seconds=1))
        else:
            source = replace(source, runtime_id=uuid4())
        source = replace(
            source, support=replace(source.support, actions=(replace(action, frames=(frame,)),))
        )
        # Genuine model execution and all q/receipt/context hashes regenerated.
        forged = joint.produce(replace(context, visual_source=source))
        workspace = stream._system.core._particle_workspace
        before = native_content_sha256(workspace.state_payload())
        ledger = stream._system.core._hybrid_loop.ledger.export_state()
        with pytest.raises(ValueError, match="visual source"):
            stage(stream, forged)
        assert native_content_sha256(workspace.state_payload()) == before
        assert stream._system.core._hybrid_loop.ledger.export_state() == ledger
        stage(stream, good)
        assert stream._system.core.prepared_particle_location_marginal()
    finally:
        store.close()


def test_complete_visual_context_and_scores_cannot_replace_registered_inputs(tmp_path, checkpoints):
    joint = producer_for(checkpoints)
    stream, store, _, when = setup_visual(tmp_path / "db", joint)
    try:
        _, good = produced_visual(stream, joint, when)
        proof = good.neural_evidence
        p = proof.context.visible.pixel_observations[0]
        changed = p.model_copy(update={"surface_geometry": None})
        context = proof.context.model_copy(
            update={
                "visible": proof.context.visible.model_copy(
                    update={"pixel_observations": (changed,)}
                )
            }
        )
        proof = replace(
            proof,
            context=context,
            scored=joint._session.score_support(context=context, support=proof.support),
        )
        forged = replace(
            good, neural_evidence=proof, receipts=materialize(proof.base_candidates, proof)
        )
        with pytest.raises(ValueError, match="actual native history"):
            stage(stream, forged)
        stage(stream, good)
    finally:
        store.close()


def test_untrusted_producer_cannot_register_or_rebind_owner(tmp_path, checkpoints):
    joint = producer_for(checkpoints)
    stream, store, _, when = setup_visual(tmp_path / "db", joint)
    try:
        context, _ = produced_visual(stream, joint, when)
        workspace = stream._system.core._particle_workspace
        fake = NativeVisualAuthority.create()
        with pytest.raises(ValueError, match="rebound"):
            workspace.bind_visual_owner(fake)
        with pytest.raises(ValueError, match="owner-authorized"):
            workspace.register_visual_source(context.visual_source, authority=fake)
        assert "_visual_authority" not in vars(context)
        assert "key" not in vars(context.visual_source)
    finally:
        store.close()


def test_source_catalogue_tamper_is_recomputed_before_action_readout(tmp_path, checkpoints):
    joint = producer_for(checkpoints)
    stream, store, _, _ = setup_visual(tmp_path / "db", joint)
    try:
        stream.produce_joint_posterior()
        view = stream.current_joint_decision_view()
        workspace = stream._system.core._particle_workspace
        sources = deepcopy(workspace.visual_sources)
        original = next(iter(sources.values()))
        forged = replace(original, support=replace(original.support, actions=()))
        workspace.visual_sources[forged.content_sha256] = forged
        with pytest.raises(ValueError, match="fresh owned visual neural source"):
            stream.current_joint_decision_view()
        workspace.visual_sources = sources
        assert stream.current_joint_decision_view() == view
    finally:
        store.close()


def test_future_delivery_not_visible_at_earlier_cutoff(tmp_path, checkpoints):
    stream, store, _, when = setup_visual(tmp_path / "db", producer_for(checkpoints))
    try:
        earlier = stream._native_visual_source(when - timedelta(microseconds=1))
        now = stream._native_visual_source(when)
        assert earlier.pixels() == () and len(now.pixels()) == 1
    finally:
        store.close()


def test_failed_producer_does_not_leave_visual_source_or_ledger_mutation(tmp_path, checkpoints):
    joint = producer_for(checkpoints)
    stream, store, _, _ = setup_visual(tmp_path / "db", joint)
    try:
        core = stream._system.core
        before = native_content_sha256(core._particle_workspace.state_payload())
        ledger = core._hybrid_loop.ledger.export_state()
        joint._candidate_model.attack = "context"
        with pytest.raises(ValueError):
            stream.produce_joint_posterior()
        assert native_content_sha256(core._particle_workspace.state_payload()) == before
        assert core._hybrid_loop.ledger.export_state() == ledger
        assert joint.calls == 0 and joint._candidate_model.calls == 0
        joint._candidate_model.attack = None
        stream.produce_joint_posterior()
        assert stream.current_joint_decision_view().atoms
    finally:
        store.close()


@pytest.mark.parametrize("helper", ["pixels", "model_input"])
def test_loaded_visual_helper_cannot_change_neural_consumer(
    tmp_path, checkpoints, monkeypatch, helper
):
    from cpswm.data_preflight.proposal_perception import ProposalPixelObservation
    from cpswm.system.native_visual_source import NativeVisualSource

    joint = producer_for(checkpoints)
    stream, store, _, when = setup_visual(tmp_path / "db", joint)
    try:
        _, good = produced_visual(stream, joint, when)
        before = native_content_sha256(stream._system.core._particle_workspace.state_payload())
        cls = NativeVisualSource if helper == "pixels" else ProposalPixelObservation
        with monkeypatch.context() as patch:
            patch.setattr(cls, helper, lambda self: ())
            with pytest.raises(ValueError, match=r"implementation|source|history"):
                stage(stream, good)
        assert (
            native_content_sha256(stream._system.core._particle_workspace.state_payload()) == before
        )
        stage(stream, good)
    finally:
        store.close()


def test_visual_full_replay_generation_and_sqlite_recovery(tmp_path, checkpoints):
    from history_loop_scenario import correction_bundles
    from run_correction_replay_comparison import OracleProducer, apply_feedback, build, ingest
    from test_native_neural_recovery import OpenWorldJointFixture

    from cpswm.system.reproducibility import content_sha256

    path, pin = checkpoints[ARMS[0]]

    def make_joint():
        return NeuralNativeProducer(
            OpenWorldJointFixture(), path, manifest_sha256=pin, use_owned_visual_context=True
        )

    joint = make_joint()
    probe, backend, stream, store, builder = build(
        tmp_path / "db",
        seed=171,
        source=content_sha256("owned-visual-full-replay-fixture"),
        joint_producer=joint,
        observation_decoder=RGBDSupportDecoder(),
    )
    try:
        ingest(probe, backend, stream, produce_joint=True)
        before = stream.current_joint_decision_view()
        when = max(stream._last_arrival, stream._last_cutoff) + timedelta(seconds=1)
        command = stream.prepare_observation(
            action="Pass",
            degrees=0,
            reason="controlled test observation for replay conditioning",
            source_ids=tuple(stream._raw),
            decision_time=when,
        )
        camera = RGBDCamera(stream._scope)
        d = stream.execute_observation(command, executor=camera)
        apply_feedback(
            stream, correction_bundles(probe, stream), d.received_at + timedelta(seconds=1)
        )
        core = stream._system.core
        ledger = core._hybrid_loop.ledger.export_state()
        stream.replay_joint_posterior()
        after = stream.current_joint_decision_view()
        assert after.runtime_id != before.runtime_id and joint.calls == 11
        assert all(
            len(b.neural_evidence.context.visible.pixel_observations) == 1
            for b in core._particle_workspace.input_bodies.values()
        )
        assert all(
            b.neural_evidence.context.visible.pixel_observations == ()
            for b in core._particle_replay_generations[0].old_workspace.input_bodies.values()
        )
        resumed = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=builder,
            joint_producer=make_joint(),
            observation_decoder=RGBDSupportDecoder(),
        )
        assert resumed.current_joint_decision_view() == after
        assert resumed._system.core._hybrid_loop.ledger.export_state() == ledger
        assert resumed.observation_history() == stream.observation_history()
        assert camera.calls == 1
        assert not core._particle_workspace.invalidated_revisions
    finally:
        store.close()


def test_fresh_process_loads_visual_types_without_initializing_new_owner():
    import os
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.continuous_state_codec import runtime_types
registry = runtime_types()
assert 'cpswm.system.native_visual_source.NativeVisualAuthority' in registry
assert 'cpswm.system.native_visual_source.NativeVisualSource' in registry
""",
        ],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "change", ["stationary", "yaw", "pitch", "position", "intrinsics", "missing_pose"]
)
def test_visual_tracks_do_not_assume_same_image_frame_after_camera_motion(change):
    from test_unity_rgbd import packet, rewrite_packet

    from cpswm.data_preflight.proposal_perception import (
        ProposalPixelObservation,
        pixel_hypothesis_bindings,
    )
    from cpswm.perception_mapping.unity_rgbd import PROFILE, surface_support
    from cpswm.system.reproducibility import content_sha256

    scope = (uuid4(), uuid4(), uuid4())
    first, when = packet(scope=scope)
    second, cutoff = packet(
        scope=scope, capture=first[0].envelope().capture_time + timedelta(seconds=0.5)
    )
    change_pose = {
        "yaw": {"yaw_degrees": 45.0},
        "pitch": {"pitch_degrees": 30.0},
        "position": {"position_m": [1.5, 2.0, 3.0]},
        "intrinsics": {
            "vertical_fov_degrees": 60.0,
            "configuration_sha256": content_sha256((PROFILE, 4, 4, 60.0, 0.1, 20.0, False)),
        },
    }
    if change in change_pose:
        second = rewrite_packet(second, pose_changes=change_pose[change])
    pixels = []
    for index, (rows, arrival) in enumerate(((first, when), (second, cutoff))):
        frame = RGBDSupportDecoder().measurements(rows, cutoff=arrival)[0]
        geometry = (
            None
            if change == "missing_pose" and index == 1
            else surface_support(rows, frame, cutoff=arrival)
        )
        pixels.append(ProposalPixelObservation.from_frame(frame, geometry=geometry))
    bindings = pixel_hypothesis_bindings(tuple(pixels), cutoff)
    keys = [{b.key for b in bindings if b.observation_id == p.observation_id} for p in pixels]
    assert len(keys[0]) == len(keys[1]) == 3
    if change == "stationary":
        assert keys[0] == keys[1]
    else:
        assert not keys[0] & keys[1]
