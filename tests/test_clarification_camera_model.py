"""Authorized development utility, exact information arithmetic and stale history."""

from dataclasses import replace
from math import fsum, log2
from types import SimpleNamespace
from uuid import uuid4

import pytest
from clarification_camera_model import ClarificationViewModel
from run_neural_pixel_camera_loop import DiagnosticViewModel
from test_joint_camera_feedback import setup

from cpswm.system.structure_two_continuous_input import ObservationDelivery
from cpswm.world_model.grounded_search.active_verification import _entropy


def entropy(values):
    return -fsum(p * log2(p) for p in values if p > 0)


@pytest.fixture
def case(tmp_path):
    stream, store, _, _, when = setup(tmp_path / "db")
    try:
        original = stream.current_joint_decision_view()
        # Recorded neural twelve-source proportions, used only as a regression fixture.
        view = replace(
            original,
            atoms=tuple(
                replace(a, probability=p)
                for a, p in zip(
                    original.atoms, (0.0563751738269979, 0.0009082837403906297), strict=True
                )
            ),
            unresolved_probability=0.9427165424326115,
        )
        yield stream, view, when, stream.visible_prefix(cutoff=when)
    finally:
        store.close()


def test_original_stops_and_clarification_acts_without_relabeling_unresolved(case):
    stream, view, when, raw = case
    ordinary = DiagnosticViewModel(None).problem(view, raw, decision_time=when)
    clarify = ClarificationViewModel(None).problem(view, raw, decision_time=when)
    assert ordinary.alternatives == clarify.alternatives
    assert ordinary.model_sources != clarify.model_sources
    assert not ordinary.select(view, stream._system.cause_information_planner)[0].should_act
    assert clarify.select(view, stream._system.cause_information_planner)[0].should_act
    assert view.unresolved_probability > 0.94
    assert all(row[view.unresolved_id] <= 0 for row in clarify.terminal_decision_utilities.values())


def test_full_hypothesis_log_score_gain_equals_independent_information_calculation(case):
    stream, view, when, raw = case
    problem = ClarificationViewModel(None).problem(view, raw, decision_time=when)
    plan, _ = problem.select(view, stream._system.cause_information_planner)
    prior = view.verification_belief().as_uuid_prior()
    for option in problem.alternatives:
        expected = 0.0
        for likelihood in option.candidate.outcome_likelihoods.values():
            mass = fsum(prior[k] * v for k, v in likelihood.items())
            expected += mass * entropy([prior[k] * v / mass for k, v in likelihood.items()])
        mi = entropy(prior.values()) - expected
        score = next(s for s in plan.scores if s.action_id == option.candidate.action_id)
        assert score.expected_utility_gain == pytest.approx(mi, abs=1e-12)
        assert score.net_value == pytest.approx(mi - 0.01, abs=1e-12)


def test_category_candidate_does_not_end_search_and_revision_keeps_physical_heading(case):
    _stream, view, when, raw = case
    decoder = SimpleNamespace(decode=lambda *args, **kwargs: "category_candidate")
    model = ClarificationViewModel(decoder)
    problem = model.problem(view, raw, decision_time=when)
    command = SimpleNamespace(
        action="RotateLeft",
        degrees=45,
        action_id=uuid4(),
        snapshot_id=view.snapshot_id,
        reason="joint-ciav@1:" + problem.model_dump_json(),
    )
    delivery = ObservationDelivery(command.action_id, (), True, "", when)
    history = ((command, delivery),)
    same = model.problem(view, raw, decision_time=when, execution_history=history)
    assert same.alternatives[0].action == "Pass"
    # Repeated fixed view provides no new information. The other view still can.
    assert set(
        same.alternatives[0].candidate.outcome_likelihoods["category_candidate"].values()
    ) == {1}
    assert (
        len(set(same.alternatives[1].candidate.outcome_likelihoods["category_candidate"].values()))
        > 1
    )
    revised = replace(view, runtime_id=uuid4())
    new = model.problem(revised, raw, decision_time=when, execution_history=history)
    assert new.alternatives[0].action == "Pass" and new.alternatives[1].degrees == 90
    assert (
        len(set(new.alternatives[0].candidate.outcome_likelihoods["category_candidate"].values()))
        > 1
    )


def test_entropy_clamps_only_tiny_negative_roundoff():
    assert _entropy([1.0000000000000002]) == 0
    assert _entropy([0.5, 0.5]) == 1
    assert _entropy([1.1]) < 0  # do not hide a materially invalid distribution
