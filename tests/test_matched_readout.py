"""Hand arithmetic, worst-case boundary witnesses and non-mutating native replay."""

import copy
import itertools

import pytest
from analyze_matched_readout import capture, decompose, fixed_mass_bound, paired_gap
from run_matched_value import dataset_for, make_state, state_audit

from cpswm.contracts import ProjectTwoDatasetSplit as Split


def hand_raw():
    return {
        "owner": "owner",
        "locations": ["left", "right"],
        "base": {"left": 0.8, "right": 0.2},
        "ledger": None,
        "particles": [
            {
                "weight": 0.8,
                "actor": "owner",
                "instance": "target_instance",
                "cause": "habit",
                "unknown_mechanism": False,
                "run_length": 10,
                "owner_cell": {
                    "location_alpha": [1, 3],
                    "ridge_natural": [0, 2],
                    "ridge_precision": [1, 2],
                    "information_natural": 1,
                    "information_precision": 2,
                    "observation_count": 1,
                },
            }
        ],
        # A=.8*.5=.4; analytic=(Dir[.25,.75]+ridge[0,1])/2=[.125,.875].
        "actual": {"left": 0.53, "right": 0.47},
    }


def test_hand_three_rb_mixture_and_ledger():
    raw = hand_raw()
    result = decompose(raw)
    assert result["analytic_mass"] == pytest.approx(0.4)
    assert result["direct_base_mass"] == pytest.approx(0.6)
    assert result["final"] == pytest.approx({"left": 0.53, "right": 0.47})
    raw["ledger"] = {"left": 0, "right": 1}
    raw["actual"] = {"left": 0.3975, "right": 0.6025}
    assert decompose(raw)["ledger_changes_action"]
    assert decompose(raw)["direct_base_mass"] == pytest.approx(0.45)


def test_fixed_mass_bound_has_adversarial_vertex_witness():
    base = {"left": 0.9, "right": 0.1}
    safe = fixed_mass_bound(base, None, 0.1, "left")
    assert safe["guaranteed_same_winner"]
    assert safe["lower_gaps"]["right"] == pytest.approx(0.62)
    unsafe = fixed_mass_bound(base, None, 0.5, "left")
    assert not unsafe["guaranteed_same_winner"]
    # Put all .5 free mass on right: .45 vs .55, an actual flip.
    assert unsafe["fixed"]["left"] < unsafe["fixed"]["right"] + unsafe["free_mass"]
    boundary = fixed_mass_bound({"left": 0.75, "right": 0.25}, None, 1 / 3, "left")
    assert not boundary["guaranteed_same_winner"]


def test_bound_matches_all_simplex_vertices_with_and_without_ledger():
    base = {"a": 0.6, "b": 0.3, "c": 0.1}
    for mass, ledger in itertools.product([0, 0.1, 0.5, 1], [None, {"a": 0.2, "b": 0.7, "c": 0.1}]):
        bound = fixed_mass_bound(base, ledger, mass, "a")
        for challenger in ["b", "c"]:
            gaps = [
                bound["fixed"]["a"]
                + mass * (1 if ledger is None else 0.75) * (vertex == "a")
                - bound["fixed"][challenger]
                - bound["free_mass"] * (vertex == challenger)
                for vertex in base
            ]
            assert min(gaps) == pytest.approx(bound["lower_gaps"][challenger])


def test_owner_gate_excludes_existing_owner_history_without_erasing_it():
    raw = hand_raw()
    raw["particles"][0]["actor"] = "guest"
    raw["actual"] = dict(raw["base"])
    result = decompose(raw)
    assert result["analytic_mass"] == 0
    assert result["gated_existing_owner_history_mass"] == 0.8
    assert result["final"] == raw["base"]


def test_rb_order_is_explicit_and_not_json_key_order():
    raw = hand_raw()
    raw["base"] = dict(reversed(list(raw["base"].items())))
    assert decompose(raw)["final"] == pytest.approx({"left": 0.53, "right": 0.47})
    raw["locations"] = ["right", "left"]
    with pytest.raises(ValueError, match="reconstruction"):
        decompose(raw)


@pytest.mark.parametrize(
    "actual", [{"left": 0.4, "right": 0.6}, {"left": 0.53, "right": float("nan")}]
)
def test_normalized_wrong_or_nonfinite_readout_is_rejected(actual):
    raw = hand_raw()
    raw["actual"] = actual
    with pytest.raises(ValueError):
        decompose(raw)


def test_observed_margin_certificate_and_counterexample():
    a = {"final": {"a": 0.85, "b": 0.15}}
    b = {"final": {"a": 0.9, "b": 0.1}}
    assert paired_gap(a, b)["strict_margin_certificate"]
    a["final"] = {"a": 0.4, "b": 0.6}
    assert not paired_gap(a, b)["same_put_back"]
    assert not paired_gap(a, b)["strict_margin_certificate"]


def test_actual_native_readout_reconstructs_without_state_changes():
    data = dataset_for("sparse32")
    episode = data.visible_episodes(Split.TEST)[0]
    state = make_state(episode, "native_joint")
    for step in episode.steps[:3]:
        state.observe(step)
        prediction = state.predict()
        before = copy.deepcopy(state_audit(state))
        result = decompose(capture(state))
        assert result["action"] == str(prediction.put_back)
        assert result["reconstruction_error"] < 1e-10
        assert before == state_audit(state)
        state.feedback(step)
