"""Second camera audit: native source changes, dependency attacks and real decoder."""

import os
from datetime import timedelta
from pathlib import Path

import pytest
from structure_two_backbone_wiring_probe import BackboneWiringProbe, CIAVOutcomeKind
from test_continuous_camera_collection import SOURCES
from test_continuous_state_recovery import DurableFixtureProducer, store_at
from test_joint_camera_feedback import BrightnessDecoder, execute, setup
from test_native_joint_production import JointFixture
from test_structure_two_continuous_input import raw_for

from cpswm.perception_mapping.pixel_camera_feedback import PixelCategoryOutcomeDecoder
from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput, GroundedTransition


def test_new_semantic_batch_does_not_double_count_old_camera_measurement(tmp_path):
    probe = BackboneWiringProbe.build(seed=7)
    meta = probe.observed_days()[0].after.metadata
    backend, store = DurableFixtureProducer(), store_at(tmp_path / "db")

    def builder(system, item, when, step):
        probe.system, probe.step_index = system, step
        return AdaptiveExecutionContext(
            router_features=probe.router_features(),
            step_index=step,
            ciav_input=probe.ciav_input(
                item.transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
            ),
        )

    stream = ContinuousEvidenceInput(
        system=probe.system,
        execution_lane="registered_p5_first",
        household_id=meta.household_id,
        session_id=meta.session_id,
        trace_id=meta.trace_id,
        producer=backend,
        context_builder=builder,
        state_store=store,
        joint_producer=JointFixture(),
        observation_decoder=BrightnessDecoder(),
    )
    for i, day in enumerate(probe.observed_days()[:2]):
        transition = probe.transition_for(day)
        when = transition.after.detection_time + timedelta(minutes=1)
        ids = stream.admit((raw_for(transition),), received_at=when)
        backend.output = GroundedTransition(transition, ids, "fixture", "not-calibrated")
        stream.advance(cutoff=when)
        if i:
            with pytest.raises(ValueError, match="source changed"):
                stream.current_joint_decision_view()
        stream.produce_joint_posterior()
        assert stream.current_joint_decision_view().observation_evidence == ()
        assert stream.joint_observation_updates() == ()
        if i == 0:
            execute(stream, transition, when + timedelta(seconds=2))
            assert len(stream.joint_observation_updates()) == 1
    assert len(stream.observation_history()) == 1  # inert past evidence remains auditable
    store.close()


def test_loaded_conditioning_math_replacement_is_not_accepted(tmp_path, monkeypatch):
    import cpswm.system.joint_camera_feedback as module

    stream, store, transition, _, start = setup(tmp_path / "db")
    execute(stream, transition, start + timedelta(seconds=2))

    def forged(view, likelihood, *, evidence_sha256):
        return view, None

    monkeypatch.setattr(module.condition_view, "__code__", forged.__code__)
    with pytest.raises(ValueError, match="decoder dependency changed"):
        stream.current_joint_decision_view()
    store.close()


def test_forked_complete_delivered_command_rejected_before_second_conditioning(tmp_path):
    from dataclasses import replace
    from uuid import uuid4

    from cpswm.system.reproducibility import content_sha256

    stream, store, transition, _, start = setup(tmp_path / "db")
    _, _, command, delivery, _ = execute(stream, transition, start + timedelta(seconds=2))
    forged = replace(command, action_id=uuid4())
    stream._observation_commands[forged.action_id] = (forged, content_sha256(forged))
    stream._observation_status[forged.action_id] = replace(delivery, action_id=forged.action_id)
    with pytest.raises(ValueError, match="fork"):
        stream.current_joint_decision_view()
    store.close()


@pytest.fixture(scope="module")
def real_decoder():
    import torch
    from test_structure_two_adaptive_runtime import _adaptive_system_and_transition

    path = Path(os.environ.get("CPSWM_SSDLITE_WEIGHTS", ""))
    if not path.is_file():
        pytest.skip("explicit local official SSDLite weights required")
    old = torch.get_num_threads()
    torch.set_num_threads(2)
    _, transition = _adaptive_system_and_transition()
    m = transition.after.metadata
    decoder = PixelCategoryOutcomeDecoder(
        weights_path=path,
        household_id=m.household_id,
        session_id=m.session_id,
        trace_id=m.trace_id,
        category="apple",
        sources=SOURCES,
    )
    yield decoder, transition
    torch.set_num_threads(old)


def test_real_pixel_decoder_repeats_actual_inference_without_semantic_authority(real_decoder):
    decoder, transition = real_decoder
    raw = raw_for(transition)
    when = raw.envelope().arrival_time
    frames = decoder.measurements((raw,), cutoff=when)
    assert len(frames) == 1 and frames[0].input_sha256 == raw.envelope().payload.payload_sha256
    assert (
        frames[0].identity_status == "UNRESOLVED" and not frames[0].negative_observation_authorized
    )
    expected = (
        "category_candidate"
        if any(c.category == "apple" for c in frames[0].candidates)
        else "no_category_candidate"
    )
    assert decoder.decode((raw,), cutoff=when) == expected
    assert decoder.measurements((raw,), cutoff=when) == frames


@pytest.mark.parametrize("field", ["_minimum_score", "_categories"])
def test_real_decoder_configuration_drift_cannot_keep_old_binding(real_decoder, field, monkeypatch):
    decoder, _ = real_decoder
    old = decoder.binding_sha256
    value = 0.01 if field == "_minimum_score" else tuple(reversed(decoder._detector._categories))
    with monkeypatch.context() as patch:
        patch.setattr(decoder._detector, field, value)
        with pytest.raises(ValueError, match="configuration changed"):
            _ = decoder.binding_sha256
    assert decoder.binding_sha256 == old


def test_real_decoder_actual_weight_and_forward_drift_are_rejected(real_decoder, monkeypatch):
    import torch

    decoder, _ = real_decoder
    model = decoder._detector._model
    parameter = next(model.parameters())
    original = parameter.detach().clone()
    try:
        parameter.data.add_(0.01)
        with pytest.raises(ValueError, match="weights, code or configuration"):
            _ = decoder.binding_sha256
    finally:
        parameter.data.copy_(original)

    def forged(self, images, targets=None):
        return []

    with monkeypatch.context() as patch:
        patch.setattr(type(model).forward, "__code__", forged.__code__)
        with pytest.raises(ValueError, match="weights, code or configuration"):
            _ = decoder.binding_sha256
    assert all(not x.training for x in model.modules())
    assert not torch.isnan(parameter).any()
