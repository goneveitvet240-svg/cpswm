"""Real alternate pixel model: inference and numerical/runtime configuration pinning."""

import os
from pathlib import Path

import pytest
from test_joint_camera_feedback_recovery import real_decoder as _ssdlite_fixture
from test_structure_two_adaptive_runtime import _adaptive_system_and_transition
from test_structure_two_continuous_input import raw_for

from cpswm.perception_mapping.pixel_camera_feedback import PixelCategoryOutcomeDecoder
from cpswm.system.joint_camera_policy import CameraModelSources
from cpswm.system.reproducibility import content_sha256

real_decoder = _ssdlite_fixture


@pytest.fixture(scope="module")
def faster_decoder():
    import torch

    path = Path(os.environ.get("CPSWM_FASTERRCNN_WEIGHTS", ""))
    if not path.is_file():
        pytest.skip("explicit local official Faster R-CNN weights required")
    old = torch.get_num_threads()
    torch.set_num_threads(2)
    _, transition = _adaptive_system_and_transition()
    m = transition.after.metadata
    sources = CameraModelSources(
        observation_model_id="test-faster-pixels",
        observation_artifact_sha256=content_sha256("fixture"),
        calibration_domain="not-calibrated",
        calibration_data_sha256=content_sha256("no-data"),
        utility_definition_id="fixture",
        utility_artifact_sha256=content_sha256("fixture"),
    )
    decoder = PixelCategoryOutcomeDecoder(
        weights_path=path,
        household_id=m.household_id,
        session_id=m.session_id,
        trace_id=m.trace_id,
        category="apple",
        sources=sources,
        detector_kind="fasterrcnn",
    )
    yield decoder, transition
    torch.set_num_threads(old)


def test_faster_inference_uses_pixels_at_same_unselected_development_threshold(faster_decoder):
    decoder, transition = faster_decoder
    raw = raw_for(transition)
    result = decoder.measurements((raw,), cutoff=raw.envelope().arrival_time)
    assert len(result) == 1 and result[0].minimum_score == 0.5
    assert "fasterrcnn" in result[0].model_id
    assert result[0].input_sha256 == raw.envelope().payload.payload_sha256
    assert (
        result[0].identity_status == "UNRESOLVED" and not result[0].negative_observation_authorized
    )


@pytest.mark.parametrize("field", ["resize", "roi", "rpn", "stride", "box_coder"])
def test_faster_numerical_settings_cannot_drift_after_binding(faster_decoder, monkeypatch, field):
    decoder, _ = faster_decoder
    model = decoder._detector._model
    if field == "resize":
        monkeypatch.setattr(model.transform, "min_size", (400,))
    if field == "roi":
        monkeypatch.setattr(model.roi_heads, "score_thresh", 0.8)
    if field == "rpn":
        monkeypatch.setattr(model.rpn, "_pre_nms_top_n", {"training": 2, "testing": 2})
    if field == "stride":
        monkeypatch.setattr(model.backbone.body.conv1, "stride", (1, 1))
    if field == "box_coder":
        monkeypatch.setattr(model.roi_heads.box_coder, "weights", (1.0, 1.0, 1.0, 1.0))
    with pytest.raises(ValueError, match="configuration changed"):
        _ = decoder.binding_sha256


def test_ssdlite_resize_geometry_is_bound_as_well(real_decoder, monkeypatch):
    decoder, _ = real_decoder
    monkeypatch.setattr(decoder._detector._model.transform, "fixed_size", (160, 160))
    with pytest.raises(ValueError, match="configuration changed"):
        _ = decoder.binding_sha256


def test_cached_anchor_tensors_cannot_be_replaced(faster_decoder, monkeypatch):
    decoder, _ = faster_decoder
    generator = decoder._detector._model.rpn.anchor_generator
    monkeypatch.setattr(generator, "cell_anchors", [v + 1 for v in generator.cell_anchors])
    with pytest.raises(ValueError, match="configuration changed"):
        _ = decoder.binding_sha256
