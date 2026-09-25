import numpy as np
import pytest

from cpswm.perception_mapping.visual_target_tracking import InitializedPixelTargetTracker


def textured():
    image = np.zeros((100, 130, 3), dtype=np.uint8)
    image[20:60, 30:70] = np.random.default_rng(5).integers(0, 256, (40, 40, 3), dtype=np.uint8)
    return image


def test_measured_translation_and_no_contact_or_probability_claim():
    tracker = InitializedPixelTargetTracker((30, 20, 70, 60))
    rgb = textured()
    tracker.update(rgb, frame_index=0)
    measured = tracker.update(np.roll(rgb, (3, 5), axis=(0, 1)), frame_index=1)
    assert measured.box_xyxy == pytest.approx((35, 23, 75, 63), abs=0.2)
    assert measured.surviving_points >= 4
    assert "NOT_WORLD_IDENTITY" in measured.status


def test_textureless_or_occluded_object_is_not_invented():
    tracker = InitializedPixelTargetTracker((30, 20, 70, 60))
    assert tracker.update(np.zeros((100, 130, 3), dtype=np.uint8), frame_index=0).box_xyxy is None
    assert tracker.update(textured(), frame_index=1).box_xyxy is None


def test_illegal_frames_do_not_advance_tracker():
    tracker = InitializedPixelTargetTracker((30, 20, 70, 60))
    with pytest.raises(ValueError):
        tracker.update(textured(), frame_index=1)
    tracker.update(textured(), frame_index=0)
    with pytest.raises(ValueError):
        tracker.update(textured()[:80], frame_index=1)
    assert tracker.update(textured(), frame_index=1).box_xyxy is not None
