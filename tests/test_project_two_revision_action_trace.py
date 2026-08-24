"""Failing-first tests for Project Two revision-to-next-action v0.3.

These tests pin the causal hand-off rather than another location classifier:
feedback revision -> explicit Project One receipt -> corrected snapshot -> next
planner distribution, with open-world actor marginals and source provenance.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.contracts import (
    ProjectOneRequestApplicationStatus,
    ProjectTwoRevisionActionTrace,
    RobotActionOutcome,
)
from cpswm.system.counterfactual_event_hypergraph.feedback_revision_loop import (
    ProjectOneRequestKind,
    ProjectOneStatRequest,
)
from cpswm.system.evaluation_operations import D0SyntheticOracleReplayAdapter
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    _FullProjectTwoMethod,
)


def _run_state(*, steps: int = 16):
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=steps
    ).build()
    episode = dataset.episodes[0]
    state = _FullProjectTwoMethod(episode, owner_threshold=0.5)
    for step in episode.steps:
        state.observe(step)
        state.predict()
        state.feedback(step)
    # Resolve the final feedback's pending "next action" edge.
    state.predict()
    return dataset, episode, state


def test_trace_is_immutable_and_reaches_next_action_from_source_feedback():
    _dataset, _episode, state = _run_state()
    traces = state.revision_action_traces
    assert traces
    assert all(isinstance(item, ProjectTwoRevisionActionTrace) for item in traces)
    for trace in traces:
        assert trace.feedback_record_id in trace.evidence_source_record_ids
        assert trace.corrected_revision_id is not None
        assert trace.new_belief_snapshot_id is not None
        assert trace.planner_read_snapshot_id == trace.new_belief_snapshot_id
        assert trace.next_action_distribution
        assert sum(item.probability for item in trace.next_action_distribution) == pytest.approx(
            1.0
        )
        with pytest.raises(ValidationError):
            trace.feedback_record_id = uuid4()  # type: ignore[misc]


def test_replay_never_applies_project_one_delta_twice():
    _dataset, _episode, state = _run_state(steps=8)
    applied_before = state.project_one_applications
    alpha_before = tuple(state.spine.hybrid_alpha(location) for location in state.locations)

    request_feedback_id = next(
        item.feedback_record_id
        for item in state.revision_action_traces
        if item.project_one_request is not None
    )
    request = state.feedback_loop._outcomes[request_feedback_id].outcome.project_one_requests[0]
    state.spine.apply_project_one_stat_request(request)

    assert state.project_one_applications == applied_before
    assert tuple(
        state.spine.hybrid_alpha(location) for location in state.locations
    ) == pytest.approx(alpha_before)
    assert state.spine.application_receipts_for_feedback(request_feedback_id)[-1].status is (
        ProjectOneRequestApplicationStatus.REPLAY_NOOP
    )


def test_every_request_has_explicit_applied_deferred_rejected_or_replay_status():
    _dataset, _episode, state = _run_state()
    allowed = set(ProjectOneRequestApplicationStatus)
    request_traces = [item for item in state.revision_action_traces if item.project_one_request]
    assert request_traces
    assert all(item.request_application_status in allowed for item in request_traces)
    assert state.project_one_requests == (
        state.project_one_applications
        + state.project_one_deferred
        + state.project_one_rejections
        + state.project_one_replay_noops
    )


def test_actor_marginal_includes_known_actor_mass_inside_unknown_mechanism_bucket():
    _dataset, _episode, state = _run_state(steps=8)
    trace = next(item for item in state.revision_action_traces if item.unknown_mechanism_after > 0)
    full = {item.key: item.probability for item in trace.actor_posterior_after}
    known = {item.key: item.probability for item in trace.known_mechanism_actor_mass_after}
    unknown_mechanism = {
        item.key: item.probability for item in trace.unknown_mechanism_actor_mass_after
    }
    assert sum(full.values()) == pytest.approx(1.0)
    for actor, mechanism_mass in unknown_mechanism.items():
        if actor != "unknown_actor" and mechanism_mass > 0:
            assert full[actor] == pytest.approx(known.get(actor, 0.0) + mechanism_mass)


def test_probabilistic_place_success_without_observed_landing_never_hard_rewrites_location():
    _dataset, episode, state = _run_state()
    for step in episode.steps:
        if step.observed_destination_location_id is not None:
            continue
        for feedback in step.execution_feedback:
            if feedback.outcome_distribution.get(RobotActionOutcome.SUCCESS, 0.0) <= 0.5:
                continue
            matching = [
                item
                for item in state.revision_action_traces
                if item.feedback_record_id == feedback.metadata.record_id
            ]
            for trace in matching:
                assert trace.confirmed_location_evidence_id is None


def test_deferred_request_retries_exactly_once_after_quarantine_promotion():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=16
    ).build()
    episode = dataset.episodes[0]
    state = _FullProjectTwoMethod(episode, owner_threshold=0.5, rgrc_gate_enabled=False)
    for step in episode.steps:
        state.observe(step)
        if state.spine._committed_events:
            break
    template = next(iter(state.spine._committed_events.values()))
    quarantined_revision_id = uuid4()
    later = template.evidence.event_time + timedelta(days=1)
    evidence = template.evidence.model_copy(
        update={
            "event_time": later,
            "metadata": template.evidence.metadata.model_copy(
                update={"record_id": uuid4(), "recorded_time": later}
            ),
        }
    )
    event = replace(
        template,
        revision_id=quarantined_revision_id,
        evidence=evidence,
        source_record_id=evidence.metadata.record_id,
        regime_frame=(
            None
            if template.regime_frame is None
            else replace(template.regime_frame, timestamp=later)
        ),
        hybrid_revision_id=None,
        hybrid_parent_revision_id=None,
        derived_from_revision_id=None,
        belief_snapshot_id=None,
    )
    state.spine._quarantined_events.append(event)
    request = ProjectOneStatRequest(
        kind=ProjectOneRequestKind.CORRECT,
        superseded_revision_id=quarantined_revision_id,
        corrected_revision_id=uuid4(),
        event_hypothesis_id=event.event_hypothesis_id,
        owner_key=state.episode.owner_actor_key,
        object_instance_id=event.evidence.object_instance_id,
        location_id=state.locations[-1],
        owner_mass_before=event.owner_mass,
        owner_mass_after=max(0.05, event.owner_mass * 0.5),
        owner_mass_delta=max(0.05, event.owner_mass * 0.5) - event.owner_mass,
        source_feedback_record_id=uuid4(),
    )
    deferred = state.spine.apply_project_one_stat_request(request)
    assert deferred.status is (ProjectOneRequestApplicationStatus.DEFERRED_DUE_TO_QUARANTINE)
    state.spine._quarantined_events.remove(event)
    state.spine._commit_event(event)

    receipts = state.spine.application_receipts_for_feedback(request.source_feedback_record_id)
    assert receipts[0].status is (ProjectOneRequestApplicationStatus.DEFERRED_DUE_TO_QUARANTINE)
    assert (
        sum(item.status is ProjectOneRequestApplicationStatus.APPLIED for item in receipts) == 1
    ), receipts
    assert receipts[-1].source_feedback_record_id == request.source_feedback_record_id

    alpha_after_promotion = tuple(
        state.spine.hybrid_alpha(location) for location in state.locations
    )
    replay = state.spine.apply_project_one_stat_request(request)
    assert replay.status is ProjectOneRequestApplicationStatus.REPLAY_NOOP
    assert tuple(
        state.spine.hybrid_alpha(location) for location in state.locations
    ) == pytest.approx(alpha_after_promotion)
