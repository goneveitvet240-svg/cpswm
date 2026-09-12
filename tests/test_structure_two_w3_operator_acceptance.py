"""R4 production identities, actual calls, semantic/run separation and identity input."""

import sys
from dataclasses import replace
from uuid import uuid4

import pytest
import test_structure_two_formal_revision_lineage as revisions
from structure_two_backbone_wiring_probe import BackboneWiringProbe
from test_structure_two_w3_revision_acceptance import public_grant_prefix

from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_semantic_identity import semantic_memory_state


class ActualCalls:
    def __init__(self, *methods):
        self.codes = {method.__func__.__code__ for method in methods}
        self.rows = []

    def profile(self, frame, event, value):
        if frame.f_code in self.codes and event in ("call", "return"):
            self.rows.append((frame.f_code.co_name, event, dict(frame.f_locals), value))

    def __enter__(self):
        self.previous = sys.getprofile()
        sys.setprofile(self.profile)
        return self

    def __exit__(self, *_args):
        sys.setprofile(self.previous)


def test_real_feedback_loop_engine_message_passing_and_statistic_application():
    probe = BackboneWiringProbe.build(seed=7)
    system = probe.system
    result = system.core.process_transition(probe.transition_for(probe.observed_days()[0]))
    feedback, binding, likelihood = revisions._feedback(probe, result.event_revision_id)
    loop = system.feedback_revision_loop
    assert loop._engine is system.core._event_engine
    assert loop._message_passing is system.core._message_passing
    with ActualCalls(
        loop.ingest_feedback, loop._message_passing.infer, loop._engine.revise_actor_responsibility
    ) as calls:
        revised, outcome, receipts = system.process_project_two_feedback(
            history=result.event_history,
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood,
        )
    ingest = [row for row in calls.rows if row[0:2] == ("ingest_feedback", "call")]
    assert len(ingest) == 1 and ingest[0][2]["self"] is loop
    assert ingest[0][2]["history"] is result.event_history
    assert ingest[0][2]["feedback"] is feedback
    assert any(
        row[0:2] == ("infer", "call") and row[2]["self"] is system.core._message_passing
        for row in calls.rows
    )
    assert any(
        row[0:2] == ("revise_actor_responsibility", "call")
        and row[2]["self"] is system.core._event_engine
        for row in calls.rows
    )
    assert receipts and all(receipt.status.value == "applied" for receipt in receipts)
    assert outcome.corrected_revision_id in system.core._committed_events
    assert result.event_revision_id not in system.core._committed_events
    assert revised.latest.revision_id == outcome.corrected_revision_id
    assert (
        system.core.committed_weight_semantics(outcome.corrected_revision_id)["hybrid_owner_weight"]
        < result.actor_posterior[system.core.owner_key] * result.propensity.applied_weight
    )


def test_feedback_loop_transaction_rolls_back_projector_and_retry(monkeypatch):
    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    result = core.process_transition(probe.transition_for(probe.observed_days()[0]))
    feedback, binding, likelihood = revisions._feedback(probe, result.event_revision_id)
    before = revisions._full_state(probe)
    loop = probe.system.feedback_revision_loop

    def fault(_self, stage):
        if stage == "rls":
            raise RuntimeError("multi-axis failure")

    arguments = dict(
        history=result.event_history,
        feedback=feedback,
        binding=binding,
        likelihood_model=likelihood,
    )
    with monkeypatch.context() as patch:
        patch.setattr(type(core), "_revision_fault_hook", fault)
        with pytest.raises(RuntimeError, match="multi-axis failure"):
            probe.system.process_project_two_feedback(**arguments)
    assert revisions._full_state(probe) == before
    assert not loop._outcomes and not loop._projector._seen
    assert loop._engine is core._event_engine and loop._message_passing is core._message_passing
    assert probe.system.process_project_two_feedback(**arguments)[2]


@pytest.mark.parametrize("path", ["legacy", "direct_p5", "p0", "debt_replay", "feedback"])
@pytest.mark.parametrize(
    "member", ["branch", "consume", "select", "execute_selected_action", "ingest_feedback"]
)
def test_every_public_lane_refuses_instance_shadowing(path, member, monkeypatch):
    probe = BackboneWiringProbe.build(seed=7)
    system = probe.system
    transition = probe.transition_for(probe.observed_days()[0])
    ciav = probe.ciav_input(transition)
    debt = None
    if path == "debt_replay":
        result, _ = probe.run_adaptive(
            transition,
            ciav_input=ciav,
            features=probe.router_features(action_margin=0.9, regime_hazard=0.0),
        )
        debt = result.debt_certificates[0].debt_id
    elif path == "feedback":
        result = system.core.process_transition(transition)
        bundle = revisions._feedback(probe, result.event_revision_id)
    instance = {
        "branch": system.core._event_engine,
        "consume": system.core._message_passing,
        "select": system.cause_information_planner,
        "execute_selected_action": system.ciav_opceu_loop,
        "ingest_feedback": system.feedback_revision_loop,
    }[member]
    before = revisions._full_state(probe)
    # Even an instance alias of the genuine bound method is not the declared
    # production member; production constraints stay on throughout this attack.
    monkeypatch.setattr(instance, member, getattr(instance, member))
    with pytest.raises(ValueError, match="shadowed"):
        if path == "legacy":
            system.core.process_transition(transition)
        elif path == "direct_p5":
            probe.run_direct_p5(transition, ciav_input=ciav)
        elif path == "p0":
            probe.run_adaptive(
                transition, features=probe.router_features(action_margin=0.9, regime_hazard=0.0)
            )
        elif path == "debt_replay":
            probe.replay_debt(debt, ciav_input=ciav)
        else:
            revisions._apply(probe, bundle)
    assert revisions._full_state(probe) == before


@pytest.mark.parametrize(
    "component", ["feedback_revision_loop", "cause_information_planner", "ciav_opceu_loop"]
)
def test_same_class_foreign_extra_instance_is_refused(component, monkeypatch):
    probe, donor = BackboneWiringProbe.build(seed=7), BackboneWiringProbe.build(seed=7)
    monkeypatch.setattr(probe.system, component, getattr(donor.system, component))
    with pytest.raises(ValueError, match="identity was replaced"):
        probe.run_direct_p5(probe.transition_for(probe.observed_days()[0]))


def test_identity_evidence_reaches_ccrr_and_changes_authorization_without_retuning():
    outputs = []
    for probability in (0.0, 0.95):
        probe, blocked, transition = public_grant_prefix()
        core = probe.system.core
        transition = replace(transition, identity_switch_probability=probability)
        with ActualCalls(
            core._automatic_regimes.observe, core._automatic_regimes.ccrr.decide
        ) as calls:
            result = core.process_transition(transition)
        observed = [row for row in calls.rows if row[0:2] == ("observe", "call")]
        decisions = [row for row in calls.rows if row[0:2] == ("decide", "call")]
        assert len(observed) == len(decisions) == 1
        assert observed[0][2]["identity_switch_probability"] == probability
        assert decisions[0][2]["identity_switch_probability"] == probability
        assert (
            core._observed_events[result.event_revision_id].identity_switch_probability
            == probability
        )
        outputs.append(blocked in core._committed_events)
    assert outputs == [True, False]


@pytest.mark.parametrize("path", ["direct_p5", "debt_replay"])
def test_ciav_identity_input_is_not_lost_before_ccrr(path):
    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    transition = probe.transition_for(probe.observed_days()[0])
    ciav = replace(probe.ciav_input(transition), identity_switch_probability=0.73)
    with ActualCalls(core._automatic_regimes.observe) as calls:
        if path == "direct_p5":
            probe.run_direct_p5(transition, ciav_input=ciav)
        else:
            result, _ = probe.run_adaptive(
                transition,
                ciav_input=ciav,
                features=probe.router_features(action_margin=0.9, regime_hazard=0.0),
            )
            probe.replay_debt(result.debt_certificates[0].debt_id, ciav_input=ciav)
    arguments = [row[2] for row in calls.rows if row[1] == "call"]
    assert arguments and all(row["identity_switch_probability"] == 0.73 for row in arguments)


@pytest.mark.parametrize("path", ["legacy", "direct_p5", "debt_replay"])
def test_same_input_same_source_semantics_with_distinct_execution_ids(path):
    left, right = BackboneWiringProbe.build(seed=7), BackboneWiringProbe.build(seed=7)
    for day in left.observed_days()[:3]:
        transition = left.transition_for(day)
        ciav = left.ciav_input(transition)  # freeze the actual action IDs and evidence once
        for probe in (left, right):
            if path == "legacy":
                probe.system.core.process_transition(transition)
            elif path == "direct_p5":
                probe.run_direct_p5(transition, ciav_input=ciav)
            else:
                result, _ = probe.run_adaptive(
                    transition,
                    ciav_input=ciav,
                    features=probe.router_features(action_margin=0.9, regime_hazard=0.0),
                )
                probe.replay_debt(result.debt_certificates[0].debt_id, ciav_input=ciav)
    a, b = left.system.semantic_memory_identity(), right.system.semantic_memory_identity()
    assert a["source_bound_semantic_sha256"] == b["source_bound_semantic_sha256"]
    assert a["execution_state_sha256"] != b["execution_state_sha256"]
    assert left.system.current_snapshot.snapshot_id != right.system.current_snapshot.snapshot_id
    core = right.system.core
    rid = next(iter(core._committed_events))
    core._committed_events[rid] = replace(
        core._committed_events[rid], statistical_owner_weight=0.123
    )
    assert core.semantic_memory_identity()["semantic_state_sha256"] != a["semantic_state_sha256"]


def test_semantic_ledger_preserves_reference_changes():
    probe = revisions._legacy_history(2)
    core = probe.system.core
    before = content_sha256(semantic_memory_state(core))
    rid = next(iter(core._committed_events))
    core._committed_events[rid] = replace(
        core._committed_events[rid], hybrid_parent_revision_id=uuid4()
    )
    assert content_sha256(semantic_memory_state(core)) != before


def test_feedback_history_content_and_replay_are_bound():
    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    first = core.process_transition(probe.transition_for(probe.observed_days()[0]))
    f, b, model = revisions._feedback(probe, first.event_revision_id)
    arguments = dict(history=first.event_history, feedback=f, binding=b, likelihood_model=model)
    # Same revision ID, changed history body must fail before any statistical write.
    forged = first.event_history.model_copy(update={"hypothesis_set_id": uuid4()})
    before = revisions._full_state(probe)
    with pytest.raises(ValueError, match="history content was not produced"):
        probe.system.process_project_two_feedback(**{**arguments, "history": forged})
    assert revisions._full_state(probe) == before
    _, outcome, _ = probe.system.process_project_two_feedback(**arguments)
    weight = core.committed_weight_semantics(outcome.corrected_revision_id)
    _, replay, receipts = probe.system.process_project_two_feedback(**arguments)
    assert replay.corrected_revision_id == outcome.corrected_revision_id
    assert core.committed_weight_semantics(outcome.corrected_revision_id) == weight
    assert all(receipt.status.value == "replay_noop" for receipt in receipts)
    with pytest.raises(ValueError, match="input content differs"):
        probe.system.process_project_two_feedback(**{**arguments, "history": forged})
