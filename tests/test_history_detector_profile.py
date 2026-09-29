"""The new history arm retains real pinned weights and existing task controls."""

import os
from pathlib import Path

import pytest

torch = pytest.importorskip("torch", reason="optional perception runtime required")
from clarification_camera_model import CLARIFICATION_SOURCES  # noqa: E402
from run_history_action_loop import decoder_for  # noqa: E402
from run_neural_pixel_camera_loop import SOURCES  # noqa: E402


@pytest.mark.parametrize("kind", ["ssdlite", "fasterrcnn"])
def test_both_real_frontends_bind_task_sources_and_survive_reconstruction(kind):
    weights = Path(os.environ.get("CPSWM_" + kind.upper() + "_WEIGHTS", ""))
    if not weights.is_file():
        pytest.skip("explicit local official " + kind + " weights required")
    pytest.importorskip("torchvision", reason="optional perception runtime required")
    torch.set_num_threads(2)
    first, scope = decoder_for(weights, "clarification", kind)
    recovered, same_scope = decoder_for(weights, "clarification", kind)
    assert first.binding_sha256 == recovered.binding_sha256 and scope == same_scope
    assert first.sources == CLARIFICATION_SOURCES
    assert first.detector_kind == kind and first._detector._minimum_score == 0.5
    control, _ = decoder_for(weights, "classification", kind)
    assert control.sources == SOURCES and control.sources != first.sources
    assert control.binding_sha256 != first.binding_sha256
    assert control._detector.weights_sha256 == first._detector.weights_sha256


def test_invalid_task_does_not_silently_select_original_control():
    with pytest.raises(ValueError, match="explicit development task"):
        decoder_for(Path("absent"), "typo")
