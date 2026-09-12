"""R5: public postconditions, refrozen ancestry, revision semantic identity."""

import sys
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import pytest
import test_structure_two_formal_revision_lineage as old
from structure_two_backbone_wiring_probe import CalibratedRetractionPolicy
from structure_two_revision_oracle import FrozenRevisionOracle
from test_structure_two_w3_revision_acceptance import correction, history, public_grant_prefix

from cpswm.system.counterfactual_event_hypergraph.feedback_revision_loop import (
    ProjectOneRequestKind,
    ProjectOneStatRequest,
)
from cpswm.system.prototype_spine import EventRevisionKind, EventRevisionOutcome
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_semantic_identity import semantic_memory_state


def state(core):
    return core._execution_observable_state_sha256()


def direct_outcome(core, target, same=True, mass=0.25):
    event = core._committed_events[target]
    return EventRevisionOutcome(
        kind=EventRevisionKind.CORRECT,
        superseded_revision_id=target,
        corrected_revision_id=uuid4(),
        corrected_location_id=(
            event.location_id if same else next(x for x in core.locations if x != event.location_id)
        ),
        corrected_owner_mass=mass,
        evidence_source_record_ids=(uuid4(),),
        rationale="frozen public direct correction input",
    )


def request_for(core, outcome):
    event = core._committed_events.get(outcome.superseded_revision_id)
    if event is None:
        event = core._observed_events[outcome.superseded_revision_id]
    return ProjectOneStatRequest(
        kind=ProjectOneRequestKind.CORRECT,
        superseded_revision_id=outcome.superseded_revision_id,
        corrected_revision_id=outcome.corrected_revision_id,
        event_hypothesis_id=event.event_hypothesis_id,
        owner_key=core.owner_key,
        object_instance_id=core.object_instance_id,
        location_id=outcome.corrected_location_id,
        owner_mass_before=event.owner_mass,
        owner_mass_after=outcome.corrected_owner_mass,
        owner_mass_delta=outcome.corrected_owner_mass - event.owner_mass,
        source_feedback_record_id=outcome.evidence_source_record_ids[0],
    )


@pytest.mark.parametrize("lane", ["legacy", "direct_p5", "debt_replay"])
@pytest.mark.parametrize("same", [True, False])
@pytest.mark.parametrize("mass", [0.0, 0.25, 1.0])
def test_public_direct_success_is_real_and_refreezeable(lane, same, mass):
    probe = history(lane)
    core = probe.system.core
    target = next(iter(core._committed_events))
    blocked = {rid for rid, row in core._write_eligibility.items() if row.origin_write_blocked}
    outcome = direct_outcome(core, target, same, mass)
    result = core.apply_event_revision_outcome(outcome)
    assert [x.value for x in result.statistic_operations] == ["correct"]
    assert target not in core._committed_events and target not in core._fast_action_events
    assert outcome.corrected_revision_id in core._committed_events
    assert core.observation_write_eligibility(outcome.corrected_revision_id)["write_eligible"]
    assert not core.observation_write_eligibility(target)["write_eligible"]
    assert not blocked.intersection(core._committed_events)
    FrozenRevisionOracle(probe).check(probe)
    before = state(core)
    with pytest.raises(KeyError, match="superseded"):
        core.apply_event_revision_outcome(outcome)
    assert state(core) == before


@pytest.mark.parametrize("entry", ["direct", "request"])
@pytest.mark.parametrize("target_index", [3, 4, 5, 6, 8, 9, 10, 11])
@pytest.mark.parametrize("mass_kind", ["unchanged_owner", "feedback_correction"])
def test_correction_postconditions_every_public_entry(entry, target_index, mass_kind):
    probe = old._legacy_history()
    core = probe.system.core
    target = list(core._committed_events)[target_index]
    outcome = direct_outcome(core, target, False, core._committed_events[target].owner_mass)
    if mass_kind == "feedback_correction":
        oracle = FrozenRevisionOracle(probe)
        _, _, interpretation = oracle.prepare(
            old._feedback(probe, target),
            CalibratedRetractionPolicy(corrected_location_id=outcome.corrected_location_id),
        )
        outcome = replace(outcome, corrected_owner_mass=interpretation.evidence_strength)
    expected_applied = mass_kind == "unchanged_owner" and target_index >= 8
    if expected_applied:
        result = (
            core.apply_event_revision_outcome(outcome)
            if entry == "direct"
            else core.apply_project_one_stat_request(request_for(core, outcome))
        )
        if entry == "request":
            assert result.status.value == "applied"
        else:
            assert [x.value for x in result.statistic_operations] == ["correct"]
        assert outcome.corrected_revision_id in core._committed_events
        assert target not in core._committed_events
        FrozenRevisionOracle(probe).check(probe)
        return
    before = old._full_state(probe)
    qualification = dict(core._write_eligibility)
    request = request_for(core, outcome)
    if entry == "direct":
        digest = state(core)
        with pytest.raises(ValueError, match="CORRECT not admitted"):
            core.apply_event_revision_outcome(outcome)
        assert state(core) == digest
    else:
        result = core.apply_project_one_stat_request(request_for(core, outcome))
        if mass_kind == "feedback_correction" and target_index == 11:
            assert result.status.value == "deferred_due_to_quarantine"
            assert outcome.corrected_revision_id not in core._committed_events
            assert core.is_quarantined_revision(outcome.corrected_revision_id)
            assert core._deferred_project_one_requests
            assert core.observation_write_eligibility(outcome.corrected_revision_id)[
                "parent_revision_id"
            ] == str(target)
            FrozenRevisionOracle(probe).check(probe)
            semantic_memory_state(core)
            before_retry = old._full_state(probe)
            duplicate = core.apply_project_one_stat_request(request)
            assert duplicate.status.value == "replay_noop"
            assert old._full_state(probe) == before_retry
            core.process_transition(probe.transition_for(probe.observed_days()[12]))
            assert not core._deferred_project_one_requests
            assert (
                core.application_receipts_for_feedback(outcome.evidence_source_record_ids[0])[
                    -1
                ].status.value
                == "rejected"
            )
            return
        assert result.status.value == "rejected"
    assert old._full_state(probe) == before
    assert core._write_eligibility == qualification
    assert not core.revision_transactions and not core._revision_parent_events
    assert target in core._committed_events
    assert outcome.corrected_revision_id not in core._committed_events
    assert not core._deferred_project_one_requests


@pytest.mark.parametrize("entry", ["direct", "request"])
@pytest.mark.parametrize("stage", ["hybrid", "dirichlet", "rls"])
@pytest.mark.parametrize("exception", [RuntimeError, KeyboardInterrupt])
def test_public_revision_failure_and_interrupt_are_retryable(entry, stage, exception, monkeypatch):
    probe = old._legacy_history(2)
    core = probe.system.core
    target = next(iter(core._committed_events))
    outcome = direct_outcome(core, target)
    request = request_for(core, outcome)

    def run():
        return (
            core.apply_event_revision_outcome(outcome)
            if entry == "direct"
            else core.apply_project_one_stat_request(request)
        )

    def fail(_self, current):
        if stage == current:
            raise exception("r5 atomic fault")

    before = state(core)
    with monkeypatch.context() as patch:
        patch.setattr(type(core), "_revision_fault_hook", fail)
        with pytest.raises(exception, match="r5 atomic fault"):
            run()
    assert state(core) == before
    assert not core._revision_parent_events and not core._deferred_project_one_requests
    run()
    assert outcome.corrected_revision_id in core._committed_events
    FrozenRevisionOracle(probe).check(probe)


@pytest.mark.parametrize("generations", [1, 2, 3])
@pytest.mark.parametrize("next_operation", ["none", "correct", "retract"])
def test_refreeze_after_existing_generations(generations, next_operation):
    probe = old._legacy_history(2)
    core = probe.system.core
    target = next(iter(core._committed_events))
    for _ in range(generations):
        target, _, _ = correction(probe, target)
    journal = old._journal(probe)
    old._assert_reconciled_against_journal(probe, journal)
    if next_operation == "correct":
        correction(probe, target, mass=0.25)
    elif next_operation == "retract":
        old._apply(probe, old._feedback(probe, target))
    old._assert_reconciled_against_journal(probe, journal)
    FrozenRevisionOracle(probe).check(probe)


@pytest.mark.parametrize(
    "fault",
    ["parent_hash", "basis_hash", "missing_operation", "missing_parent", "cycle", "wrong_parent"],
)
def test_refreeze_and_semantic_state_reject_forged_lineage(fault):
    probe = old._legacy_history(2)
    core = probe.system.core
    target = next(iter(core._committed_events))
    corrected, _, _ = correction(probe, target)
    FrozenRevisionOracle(probe).check(probe)
    semantic_memory_state(core)
    row = core._write_eligibility[corrected]
    if fault == "parent_hash":
        core._write_eligibility[corrected] = replace(row, parent_eligibility_sha256="0" * 64)
    elif fault == "basis_hash":
        core._write_eligibility[corrected] = replace(
            row, authorizations=(replace(row.authorizations[0], basis_sha256="0" * 64),)
        )
    elif fault == "missing_operation":
        core._revision_transactions = ()
    elif fault == "missing_parent":
        del core._revision_parent_events[target]
    else:
        parent = (
            corrected
            if fault == "cycle"
            else next(rid for rid in core._write_eligibility if rid not in (target, corrected))
        )
        core._write_eligibility[corrected] = replace(
            row,
            parent_revision_id=parent,
            parent_eligibility_sha256=content_sha256(core._write_eligibility[parent]),
        )
    with pytest.raises(AssertionError):
        FrozenRevisionOracle(probe).check(probe)
    with pytest.raises(ValueError):
        semantic_memory_state(core)


def test_refreeze_of_revoked_grant_and_corrected_descendant():
    probe, blocked, transition = public_grant_prefix()
    core = probe.system.core
    grantor = core.process_transition(transition).event_revision_id
    corrected, _, _ = correction(probe, blocked)
    old._apply(probe, old._feedback(probe, grantor))
    assert not core.observation_write_eligibility(corrected)["write_eligible"]
    assert corrected not in core._committed_events
    FrozenRevisionOracle(probe).check(probe)
    semantic_memory_state(core)


@pytest.mark.parametrize("same", [True, False])
@pytest.mark.parametrize("ending", ["correct", "continuous", "retract", "replay", "recovery"])
def test_revision_semantics_reproduce_across_runs(same, ending, monkeypatch):
    probes = [old._legacy_history(2), old._legacy_history(2)]
    feedback_ids = [uuid4(), uuid4()]
    action_ids = [uuid4(), uuid4()]
    for index, probe in enumerate(probes):
        core = probe.system.core
        target = next(iter(core._committed_events))
        generations = 2 if ending == "continuous" else 1
        for generation in range(generations):
            event = core._committed_events[target]
            location = (
                event.location_id
                if same
                else next(x for x in core.locations if x != event.location_id)
            )
            bundle = old._feedback(
                probe,
                target,
                feedback_record_id=feedback_ids[generation],
                action_id=action_ids[generation],
            )
            policy = CalibratedRetractionPolicy(
                corrected_location_id=location, corrected_owner_mass=0.25
            )
            if ending == "recovery" and index == 0:
                before = state(core)

                def fail(_self, stage):
                    if stage == "rls":
                        raise KeyboardInterrupt("recover")

                with monkeypatch.context() as patch:
                    patch.setattr(type(core), "_revision_fault_hook", fail)
                    with pytest.raises(KeyboardInterrupt):
                        old._apply(probe, bundle, policy=policy)
                assert state(core) == before
            old._apply(probe, bundle, policy=policy)
            target = core.revision_transactions[-1].corrected_revision_id
            if ending == "replay":
                before = state(core)
                old._apply(probe, bundle, policy=policy)
                assert state(core) == before
        if ending == "retract":
            old._apply(
                probe,
                old._feedback(
                    probe, target, feedback_record_id=feedback_ids[1], action_id=action_ids[1]
                ),
            )
    left, right = [semantic_memory_state(p.system.core) for p in probes]
    assert left == right
    assert state(probes[0].system.core) != state(probes[1].system.core)


@pytest.mark.parametrize("change", ["source", "weight", "location"])
def test_real_changed_revision_input_changes_semantics(change):
    probes = [old._legacy_history(2), old._legacy_history(2)]
    fid, aid = uuid4(), uuid4()
    for index, probe in enumerate(probes):
        core = probe.system.core
        target = next(iter(core._committed_events))
        location = core._committed_events[target].location_id
        bundle = old._feedback(
            probe,
            target,
            feedback_record_id=(uuid4() if index and change == "source" else fid),
            action_id=aid,
        )
        policy = CalibratedRetractionPolicy(
            corrected_location_id=(
                next(x for x in core.locations if x != location)
                if index and change == "location"
                else location
            ),
            corrected_owner_mass=(0.5 if index and change == "weight" else 0.25),
        )
        old._apply(probe, bundle, policy=policy)
    assert semantic_memory_state(probes[0].system.core) != semantic_memory_state(
        probes[1].system.core
    )


@pytest.mark.parametrize("ending", ["single", "same_claim_rejection", "replay", "recovery"])
def test_multi_axis_feedback_semantics_keep_raw_history_hash_checks(ending, monkeypatch):
    feedback_ids, action_ids = [uuid4(), uuid4()], [uuid4(), uuid4()]
    probes = [old._legacy_history(2), old._legacy_history(2)]
    for index, probe in enumerate(probes):
        core = probe.system.core
        target = next(iter(core._committed_events))
        for generation in range(2 if ending == "same_claim_rejection" else 1):
            f, b, likelihood = old._feedback(
                probe,
                target,
                feedback_record_id=feedback_ids[generation],
                action_id=action_ids[generation],
            )
            arguments = dict(
                history=core._event_histories[target],
                feedback=f,
                binding=b,
                likelihood_model=likelihood,
            )
            if generation == 1:
                before = state(core)
                with pytest.raises(RuntimeError, match="same-claim evidence"):
                    probe.system.process_project_two_feedback(**arguments)
                assert state(core) == before
                assert f.metadata.record_id not in probe.system._feedback_input_journal
                continue
            if index == 0 and ending == "recovery":
                before = state(core)

                def fail(_self, stage):
                    if stage == "rls":
                        raise KeyboardInterrupt("multi-axis interrupt")

                with monkeypatch.context() as patch:
                    patch.setattr(type(core), "_revision_fault_hook", fail)
                    with pytest.raises(KeyboardInterrupt, match="multi-axis interrupt"):
                        probe.system.process_project_two_feedback(**arguments)
                assert state(core) == before
                assert not probe.system._feedback_input_journal
            _revised, outcome, receipts = probe.system.process_project_two_feedback(**arguments)
            assert receipts and all(r.status.value == "applied" for r in receipts)
            assert target not in core._committed_events
            target = outcome.corrected_revision_id
            assert target in core._committed_events
            if ending == "replay":
                before = observable_payload(core)
                old_receipts = core.application_receipts_for_feedback(f.metadata.record_id)
                _history, replay_outcome, replay_receipts = (
                    probe.system.process_project_two_feedback(**arguments)
                )
                after = observable_payload(core)
                assert {key for key in before if before[key] != after[key]} == {
                    "project_one_application_receipts"
                }
                assert replay_outcome.is_replay
                assert len(replay_receipts) == len(receipts)
                assert all(r.status.value == "replay_noop" for r in replay_receipts)
                assert core.application_receipts_for_feedback(f.metadata.record_id) == (
                    *old_receipts,
                    *replay_receipts,
                )
            FrozenRevisionOracle(probe).check(probe)
    assert semantic_memory_state(probes[0].system.core) == semantic_memory_state(
        probes[1].system.core
    )
    core = probes[0].system.core
    target = core.revision_transactions[-1].corrected_revision_id
    history = core._event_histories[target]
    damaged = history.latest.model_copy(update={"revision_content_sha256": "0" * 64})
    core._event_histories[target] = history.model_copy(
        update={"revisions": (*history.revisions[:-1], damaged)}
    )
    with pytest.raises(ValueError, match="revision_content_sha256"):
        semantic_memory_state(core)


def observable_payload(core):
    rows = []
    code = content_sha256.__code__

    def profile(frame, event, _value):
        if frame.f_code is code and event == "call":
            value = frame.f_locals["value"]
            if isinstance(value, dict) and "project_one_application_receipts" in value:
                rows.append(deepcopy(value))

    previous = sys.getprofile()
    try:
        sys.setprofile(profile)
        state(core)
    finally:
        sys.setprofile(previous)
    assert len(rows) == 1
    return rows[0]


@pytest.mark.parametrize("cause", ["foreign_owner", "foreign_object", "ccrr"])
def test_rejected_public_request_changes_only_rejection_audit(cause):
    probe = old._legacy_history()
    core = probe.system.core
    target = list(core._committed_events)[3]
    outcome = direct_outcome(core, target, False)
    oracle = FrozenRevisionOracle(probe)
    _, _, interpretation = oracle.prepare(
        old._feedback(probe, target),
        CalibratedRetractionPolicy(corrected_location_id=outcome.corrected_location_id),
    )
    outcome = replace(outcome, corrected_owner_mass=interpretation.evidence_strength)
    request = request_for(core, outcome)
    if cause == "foreign_owner":
        request = replace(request, owner_key="foreign")
    if cause == "foreign_object":
        request = replace(request, object_instance_id=uuid4())
    before = observable_payload(core)
    original_ccrr, original_bocpd = core._automatic_regimes.ccrr, core._automatic_regimes.bocpd
    receipt = core.apply_project_one_stat_request(request)
    after = observable_payload(core)
    assert core._automatic_regimes.ccrr is original_ccrr
    assert core._automatic_regimes.bocpd is original_bocpd
    assert receipt.status.value == "rejected"
    assert {key for key in before if before[key] != after[key]} == {
        "project_one_application_receipts"
    }
    assert core.application_receipts_for_feedback(request.source_feedback_record_id) == (receipt,)
    assert target in core._committed_events
    FrozenRevisionOracle(probe).check(probe)


def test_deferred_owner_delta_is_counted_exactly_once_for_action():
    probe, target, _transition = public_grant_prefix()
    core = probe.system.core
    event = core._observed_events[target]
    request = ProjectOneStatRequest(
        kind=ProjectOneRequestKind.CORRECT,
        superseded_revision_id=target,
        corrected_revision_id=uuid4(),
        event_hypothesis_id=event.event_hypothesis_id,
        owner_key=core.owner_key,
        object_instance_id=core.object_instance_id,
        location_id=event.location_id,
        owner_mass_before=event.owner_mass,
        owner_mass_after=0.0,
        owner_mass_delta=-event.owner_mass,
        source_feedback_record_id=uuid4(),
    )
    assert request.owner_mass_delta < 0.0
    receipt = core.apply_project_one_stat_request(request)
    assert receipt.status.value == "deferred_due_to_quarantine"
    assert core.pending_correction_mass()[event.location_id] == pytest.approx(
        request.owner_mass_delta
    )
    core.apply_project_one_stat_request(request)
    assert core.pending_correction_mass()[event.location_id] == pytest.approx(
        request.owner_mass_delta
    )
