"""Real pinned detector to owned support, no calibrated task-success claim."""

import pytest

pytest.importorskip("torch", reason="optional real perception runtime required")
from test_owned_visual_support import journal as _journal
from test_pixel_camera_detector_binding import faster_decoder as _faster
from test_pixel_camera_detector_binding import real_decoder as _ssdlite

from cpswm.system.joint_camera_feedback import decoder_binding
from cpswm.system.owned_visual_support import reconstruct_visual_support

journal = _journal
faster_decoder = _faster
real_decoder = _ssdlite


@pytest.mark.parametrize("fixture", ["real_decoder", "faster_decoder"])
def test_real_inference_to_owned_frame_support_is_repeatable(journal, request, fixture):
    decoder, _ = request.getfixturevalue(fixture)
    journal.update(decoder=decoder, expected_binding=decoder_binding(decoder))
    first = reconstruct_visual_support(**journal)
    assert reconstruct_visual_support(**journal) == first
    assert len(first.actions) == 1 and len(first.actions[0].frames) == 1
    measured = first.actions[0].frames[0]
    assert len(measured.candidates) == len(measured.frame.candidates)
    assert first.scored_joint_density is None and not first.memory_write_authorized
