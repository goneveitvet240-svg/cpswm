"""Hand-computed history target and native bootstrap/readout conformance."""

import copy
import math
from types import SimpleNamespace

import pytest
from run_research_pilot import conditional_reference, enumerate_update
from run_short_history_reference import (
    BootstrapRuntime,
    ExactHistory,
    fixed_inputs,
    path_comparison,
    sampled_paths,
)
from verify_short_history_reference import verify_replayed_run, verify_traces

from cpswm.system.evaluation_operations.structure_two_current_event import CurrentEventRuntime
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm


class TwoStateMarkov:
    config = SimpleNamespace(unresolved_prior=0.0)
    particles = ()

    def _candidates(self, obs, parent):
        return ((0, 0.9), (1, 0.1))  # deliberately unrelated proposal

    def _transition_raw(self, parent, candidate):
        row = (0.6, 0.4) if parent is None else ((0.8, 0.2), (0.3, 0.7))[parent.label]
        return math.log(row[candidate])

    def _constraints(self, candidate):
        return (SimpleNamespace(accepted=True, log_potential=0.0),)

    def _observation_log_likelihood(self, obs, candidate):
        return math.log(((0.9, 0.2), (0.1, 0.8))[obs][candidate])

    def _main_log_factor(self, obs, candidate):
        return 0.0

    def _interaction_log_factor(self, obs, candidate):
        return 0.0


def test_two_step_exact_target_matches_hand_calculated_paths():
    model = TwoStateMarkov()
    entries, _, _, weights = enumerate_update(model, 0)
    assert weights == pytest.approx([27 / 31, 4 / 31])
    model.particles = tuple(
        SimpleNamespace(label=c, posterior_probability=p)
        for (_, c), p in zip(entries, weights, strict=True)
    )
    entries, _, _, weights = enumerate_update(model, 1)
    assert [(parent.label, c) for parent, c in entries] == [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert weights == pytest.approx([54 / 221, 108 / 221, 3 / 221, 56 / 221])
    assert weights[0] + weights[2] == pytest.approx(57 / 221)


@pytest.fixture(scope="module")
def inputs():
    result = fixed_inputs()
    assert len(result) == 2
    assert all(len(values[3]) == 2 for values in result)
    return result[0]


def native(inputs, cls=CurrentEventRuntime):
    return cls(arm=FullJointArm.STATEFUL_FULL_JOINT, config=inputs[1], neural_model=inputs[2])


def test_first_step_matches_previous_reference_and_retains_all_parents(inputs, tmp_path):
    obs = inputs[3][0]
    assert obs.position_source_id is not None and obs.location_likelihood
    runtime = native(inputs)
    runtime.revise(copy.deepcopy(obs))
    previous = conditional_reference(runtime)
    exact = ExactHistory(native(inputs))
    row = exact.advance(copy.deepcopy(obs), output=tmp_path / "root.jsonl.gz")
    assert len(exact.runtime.particles) == previous["reference_target_evaluations"] > 24
    for axis, values in row["marginals"].items():
        assert values == pytest.approx(previous["marginals"][axis]["reference"])
    assert row["summary"]["streamed_vs_native_readout_tv"] < 1e-10
    paths, sampled = sampled_paths(runtime, {})
    assert len(paths) == 24
    reading = path_comparison(row["posterior"], sampled, runtime.unresolved_probability)
    explicit_tv = 0.5 * sum(abs(row["posterior"][k] - sampled.get(k, 0)) for k in row["posterior"])
    assert reading["latent_path_tv"] == pytest.approx(explicit_tv, abs=1e-12)
    with pytest.raises(ValueError, match="duplicate"):
        exact.advance(copy.deepcopy(obs), terminal=True)
    with pytest.raises(ValueError, match="terminal"):
        exact.advance(copy.deepcopy(inputs[3][1]))


@pytest.mark.parametrize("depth", [0, 1])
def test_bootstrap_proposal_cancels_parent_and_transition(inputs, depth):
    runtime = native(inputs, BootstrapRuntime)
    if depth:
        runtime.revise(copy.deepcopy(inputs[3][0]))
    obs = inputs[3][depth]
    runtime.step_index += 1
    entries, targets, proposal, _ = enumerate_update(runtime, obs)
    prior_sum = (
        1.0
        if not runtime.particles
        else sum(max(p.posterior_probability, 1e-300) for p in runtime.particles)
    )
    errors = []
    for (_, candidate), target, q in zip(entries, targets, proposal, strict=True):
        evidence = (
            runtime._observation_log_likelihood(obs, candidate)
            + runtime._main_log_factor(obs, candidate)
            + runtime._interaction_log_factor(obs, candidate)
            + sum(c.log_potential for c in runtime._constraints(candidate))
        )
        errors.append(abs(target - math.log(q) - evidence - math.log(prior_sum)))
    assert max(errors) < 1e-10
    assert sum(proposal) == pytest.approx(1)


def test_bootstrap_keeps_same_target_support(inputs):
    a, b = native(inputs), native(inputs, BootstrapRuntime)
    obs = inputs[3][0]
    a.step_index = b.step_index = 1
    ea, la, qa, pa = enumerate_update(a, obs)
    eb, lb, qb, pb = enumerate_update(b, obs)
    assert [c.key for _, c in ea] == [c.key for _, c in eb]
    assert la == lb and pa == pb and qa != qb


def test_joint_path_check_cannot_accept_foreign_paths():
    with pytest.raises(ValueError, match="outside"):
        path_comparison({("legal",): 0.95}, {("forged",): 0.95}, 0.05)


def test_replay_ignores_only_timing_and_rejects_complete_wrong_model_substitution():
    expected = {
        "rows": [
            {
                "arm": "joint",
                "reference": {"mass": [0.4, 0.6], "seconds": 1},
                "methods": [{"path": ["owner", "guest"], "weight": 0.2}],
            }
        ]
    }
    legal = copy.deepcopy(expected)
    legal["rows"][0]["reference"]["seconds"] = 2
    verify_replayed_run(legal, expected)
    # Complete normalized alternative, no missing schema/fields; still the wrong model result.
    forged = copy.deepcopy(legal)
    forged["rows"][0]["reference"]["mass"] = [0.6, 0.4]
    with pytest.raises(ValueError, match="replay differs"):
        verify_replayed_run(forged, expected)


@pytest.mark.parametrize("name", ["../outside.json.gz", "/tmp/outside.json.gz", ".."])
def test_trace_check_rejects_path_escape_before_reading(tmp_path, name):
    with pytest.raises(ValueError, match="trace path"):
        verify_traces(tmp_path, {"rows": [{"reference": {"posterior_trace": name}}]})
