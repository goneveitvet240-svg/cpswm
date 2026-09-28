"""Fair fixed diagnostic policies share pixel stop/visited state and budgets.
PYTEST_DONT_REWRITE: the controlled decoder is an explicitly bound test fixture.
"""

import sys
from datetime import timedelta
from pathlib import Path

import pytest
from test_joint_camera_feedback import BrightnessDecoder, Camera, setup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_neural_pixel_camera_loop import (
    ARMS,
    METHODS,
    SOURCES,
    DiagnosticViewModel,
    canonical_probabilities,
    collect_comparison_step,
    scan_rotation,
)

from cpswm.system.reproducibility import content_sha256


class CategoryFixture(BrightnessDecoder):
    sources = SOURCES
    binding_sha256 = content_sha256("fixture-category-alphabet-for-fair-policy-tests")

    def decode(self, observations, *, cutoff):
        return (
            "category_candidate"
            if super().decode(observations, cutoff=cutoff) == "bright"
            else "no_category_candidate"
        )


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("positive", [False, True])
def test_all_methods_get_same_pixel_stop_and_visited_view_information(tmp_path, method, positive):
    decoder = CategoryFixture()
    stream, store, transition, _, start = setup(
        tmp_path / "state", decoder, feedback=method in ARMS
    )
    stream._producer.output = None
    model, camera = DiagnosticViewModel(decoder), Camera(transition, bright=positive)
    initial = canonical_probabilities(stream.current_joint_decision_view())
    try:
        first = collect_comparison_step(stream, model, camera, method, start + timedelta(seconds=2))
        assert first.command is not None and first.delivery.success
        assert first.command.degrees == 45
        expected_action = "RotateLeft" if method == "scan_left_first" else "RotateRight"
        assert first.command.action == expected_action
        final = canonical_probabilities(stream.current_joint_decision_view())
        assert (initial != final) is (method in ARMS)
        second = collect_comparison_step(
            stream, model, camera, method, start + timedelta(seconds=4)
        )
        if positive:
            assert second.command is None and camera.calls == 1
        else:
            assert second.command.degrees == 90 and second.command.action != first.command.action
            third = collect_comparison_step(
                stream, model, camera, method, start + timedelta(seconds=6)
            )
            assert third.command is None and camera.calls == 2
        assert len(stream.joint_observation_updates()) == (camera.calls if method in ARMS else 0)
    finally:
        store.close()


def test_scan_policy_has_no_scene_or_target_metadata_argument():
    class Model:
        def history(self, history):
            assert history == ()
            return 270, {}

    assert scan_rotation((), Model(), left_first=True) == ("RotateLeft", 45)
    assert scan_rotation((), Model(), left_first=False) == ("RotateRight", 45)


def test_unknown_method_is_rejected_without_advancing_or_dispatching():
    with pytest.raises(ValueError, match="undeclared"):
        collect_comparison_step(None, None, None, "invented_winner", None)
