"""All binary paths must reach actual owner actions and common stop information."""

from types import SimpleNamespace

import pytest
from run_camera_policy_identifiability import (
    ARMS,
    METHODS,
    PATTERNS,
    PatternCamera,
    run_case,
    summarize,
)


@pytest.fixture(scope="module")
def cases(tmp_path_factory):
    root = tmp_path_factory.mktemp("binary-policies")
    return [run_case(root / p / m, pattern=p, method=m) for p in PATTERNS for m in METHODS]


@pytest.mark.parametrize("pattern", PATTERNS)
@pytest.mark.parametrize("method", METHODS)
def test_real_owner_consumes_every_binary_path_with_fair_stopping(cases, pattern, method):
    row = next(r for r in cases if (r["pattern"], r["method"]) == (pattern, method))
    order = (225.0, 315.0) if method == "scan_left_first" else (315.0, 225.0)
    outcomes = dict(zip((225.0, 315.0), (c == "1" for c in pattern), strict=True))
    expected = [order[0]] if outcomes[order[0]] else list(order)
    assert [s["heading"] for s in row["actions"]] == expected
    assert [s["outcome"] == "category_candidate" for s in row["actions"]] == [
        outcomes[h] for h in expected
    ]
    assert row["stopped"] and row["camera_calls"] == len(expected)
    assert row["native_unchanged"] and row["ledger_unchanged"]
    assert row["feedback_updates"] == (len(expected) if method in ARMS else 0)
    assert all(s["probabilities_changed"] is (method in ARMS) for s in row["actions"])
    assert len(set(expected)) == len(expected)
    probabilities = row["initial"]
    for step in row["actions"]:
        assert step["prior"] == pytest.approx(probabilities, abs=1e-12)
        if method in ARMS:
            positive_likelihood = {
                "aggregate_unresolved": 0.5,
                "known_instance": 0.9 if step["heading"] == 315 else 0.05,
                "unknown_instance": 0.9 if step["heading"] == 225 else 0.05,
            }
            likelihood = {
                key: value if outcomes[step["heading"]] else 1 - value
                for key, value in positive_likelihood.items()
            }
            mass = {key: value * likelihood[key] for key, value in probabilities.items()}
            probabilities = {key: value / sum(mass.values()) for key, value in mass.items()}
        assert step["posterior"] == pytest.approx(probabilities, abs=1e-12)


def test_complete_summary_is_controlled_and_preserves_all_outcomes(cases):
    summary = summarize(cases)
    assert summary["complete_cases"] == 24
    assert summary["actual_unity_episodes"] == summary["natural_vision_frames"] == 0
    assert summary["physical_target_success_evaluated"] is False
    assert summary["all_neural_match_no_feedback"]
    assert summary["all_right_scan_match_no_feedback"]
    assert [r["pattern"] for r in summary["patterns"]] == list(PATTERNS)


@pytest.mark.parametrize("action,degrees", [("Pass", 0), ("RotateRight", 10)])
def test_camera_rejects_unregistered_view_before_recording_measurement(action, degrees):
    camera = PatternCamera(None, "00")
    with pytest.raises(ValueError):
        camera.execute(SimpleNamespace(action=action, degrees=degrees))
    assert camera.heading == 270 and camera.calls == 0 and camera.visits == []


def test_unknown_pattern_or_method_cannot_create_output(tmp_path):
    path = tmp_path / "invalid"
    with pytest.raises(ValueError, match="undeclared"):
        run_case(path, pattern="12", method=METHODS[0])
    with pytest.raises(ValueError, match="undeclared"):
        run_case(path, pattern="00", method="winner")
    assert not path.exists()
