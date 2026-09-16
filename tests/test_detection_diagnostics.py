import numpy as np
import pytest

from cpswm.data_preflight.detection_diagnostics import classify_miss


def classify(roi=(), native=(), *, matched=False, scores=(), nscores=()):
    return classify_miss(
        (0, 0, 10, 10),
        matched=matched,
        roi_boxes=np.array(roi, dtype=float).reshape(-1, 4),
        roi_scores=np.array(scores, dtype=float),
        native_boxes=np.array(native, dtype=float).reshape(-1, 4),
        native_scores=np.array(nscores, dtype=float),
        person_boxes=np.empty((0, 4)),
        native_threshold=0.05,
    )


@pytest.mark.parametrize(
    "score,expected",
    [
        (0.01, "roi_score_below_native_floor"),
        (0.05, "roi_score_below_native_floor"),
        (0.051, "native_size_nms_topk_filter"),
    ],
)
def test_native_boundary(score, expected):
    assert classify(roi=[(0, 0, 10, 10)], scores=[score]).mechanism == expected


def test_application_filter_and_assignment_are_separate():
    box = [(0, 0, 10, 10)]
    assert classify(native=box, nscores=[0.49]).mechanism == "application_score_filter"
    assert classify(native=box, nscores=[0.5]).mechanism == "one_to_one_assignment_competition"
    assert classify(native=box, nscores=[0.5], matched=True).mechanism == "matched"


def test_absence_is_not_localization_or_positive():
    assert classify().mechanism == "no_overlapping_roi_candidate"
    assert (
        classify(roi=[(0, 0, 2, 2)], scores=[0.9]).mechanism
        == "roi_localization_below_iou_threshold"
    )
    with pytest.raises(ValueError, match="no qualifying"):
        classify(matched=True)


def test_bad_inputs_do_not_become_misses():
    with pytest.raises(ValueError, match="nonfinite"):
        classify(roi=[(0, 0, float("nan"), 10)], scores=[0.1])
    with pytest.raises(ValueError, match="probability"):
        classify(roi=[(0, 0, 10, 10)], scores=[1.1])
