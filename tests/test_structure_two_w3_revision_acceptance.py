"""R4 non-vacuous public correction, authorization and fault-detection matrix."""

from dataclasses import replace
from uuid import uuid4

import pytest
import test_structure_two_formal_revision_lineage as old
from structure_two_backbone_wiring_probe import (
    BackboneWiringProbe,
    CalibratedRetractionPolicy,
    CIAVOutcomeKind,
)

from cpswm.system.continual.project_one_regime_loop import PrototypeStatisticOperation
from cpswm.system.reproducibility import content_sha256


def history(path):
    if path == "legacy":
        return old._legacy_history()
    if path == "direct_p5":
        return old._adaptive_history()
    probe = BackboneWiringProbe.build(seed=7)
    for day in probe.observed_days()[:10]:
        transition = probe.transition_for(day)
        ciav = probe.ciav_input(transition)
        result, _ = probe.run_adaptive(
            transition,
            features=probe.router_features(action_margin=0.9, regime_hazard=0.0),
            ciav_input=ciav,
        )
        assert len(result.debt_certificates) == 1
        probe.replay_debt(result.debt_certificates[0].debt_id, ciav_input=ciav)
    assert not probe.system.pending_adaptive_debts()
    return probe


def correction(probe, target, *, same=True, mass=None):
    core = probe.system.core
    location = core._committed_events[target].location_id
    if not same:
        location = next(loc for loc in probe.case.locations if loc != location)
    policy = CalibratedRetractionPolicy(corrected_location_id=location, corrected_owner_mass=mass)
    bundle = old._feedback(probe, target)
    result = old._apply(probe, bundle, policy=policy)
    assert result.statistic_operations == (PrototypeStatisticOperation.CORRECT,)
    return core.revision_transactions[-1].corrected_revision_id, bundle, policy


@pytest.mark.parametrize("path", ["legacy", "direct_p5", "debt_replay"])
@pytest.mark.parametrize("same", [True, False])
@pytest.mark.parametrize("mass", [None, 0.0, 0.25, 1.0])
def test_correction_survives_with_verified_parent_and_all_stores(path, same, mass):
    probe = history(path)
    core = probe.system.core
    journal = old._journal(probe)
    blocked = {rid for rid, row in journal.items() if row.origin_write_blocked}
    if path != "legacy":
        assert len(blocked) == 10
    target = next(iter(core._committed_events))
    parent_qualification = core.observation_write_eligibility(target)
    new, bundle, policy = correction(probe, target, same=same, mass=mass)
    assert new in core._committed_events
    assert new not in {item.revision_id for item in core._quarantined_events}
    assert target not in core._observed_events and target not in core._committed_events
    assert target not in core._fast_action_events
    row = core.observation_write_eligibility(new)
    assert row["write_eligible"] and row["active"]
    assert row["parent_revision_id"] == str(target)
    assert row["correction_evidence_source_record_ids"] == (str(bundle[0].metadata.record_id),)
    assert row["correction_outcome_sha256"] == content_sha256(core.revision_transactions[-1])
    assert core.observation_write_eligibility(target)["active"] is False
    assert parent_qualification["write_eligible"]
    assert not blocked & set(core._committed_events)
    assert blocked <= {item.revision_id for item in core._quarantined_events}
    old._assert_reconciled_against_journal(probe, journal)
    before = old._full_state(probe)
    replay = old._apply(probe, bundle, policy=policy)
    assert replay.statistic_operations == (PrototypeStatisticOperation.QUARANTINE,)
    assert old._full_state(probe) == before
    # The corrected binding actually supports a subsequent public retraction.
    old._apply(probe, old._feedback(probe, new))
    assert new not in core._committed_events and new not in core._fast_action_events
    old._assert_reconciled_against_journal(probe, journal)


@pytest.mark.parametrize("path", ["legacy", "direct_p5", "debt_replay"])
def test_continuous_correction_and_out_of_order_feedback(path):
    probe = history(path)
    core = probe.system.core
    journal = old._journal(probe)
    target = next(iter(core._committed_events))
    stale_bundle = old._feedback(probe, target)
    new, _, _ = correction(probe, target)
    newest, _, _ = correction(probe, new, same=False)
    assert core.observation_write_eligibility(newest)["parent_revision_id"] == str(new)
    before = old._full_state(probe)
    with pytest.raises((ValueError, KeyError)):
        old._apply(probe, stale_bundle)
    assert old._full_state(probe) == before
    old._assert_reconciled_against_journal(probe, journal)


@pytest.mark.parametrize("stage", ["hybrid", "dirichlet", "rls"])
@pytest.mark.parametrize("path", ["legacy", "direct_p5", "debt_replay"])
def test_correction_rollback_and_same_feedback_retry(path, stage, monkeypatch):
    probe = history(path)
    core = probe.system.core
    journal = old._journal(probe)
    target = next(iter(core._committed_events))
    bundle = old._feedback(probe, target)
    policy = CalibratedRetractionPolicy(
        corrected_location_id=core._committed_events[target].location_id
    )
    state = old._full_state(probe)
    qualifications = dict(core._write_eligibility)
    operations = core.revision_transactions

    def fault(_self, value):
        if value == stage:
            raise RuntimeError("r4 transaction failure")

    with monkeypatch.context() as patch:
        patch.setattr(type(core), "_revision_fault_hook", fault)
        with pytest.raises(RuntimeError, match="r4 transaction failure"):
            old._apply(probe, bundle, policy=policy)
    assert old._full_state(probe) == state
    assert core._write_eligibility == qualifications
    assert core.revision_transactions == operations
    old._apply(probe, bundle, policy=policy)
    old._assert_reconciled_against_journal(probe, journal)


def public_grant_prefix():
    probe = BackboneWiringProbe.build(seed=7)
    transitions = []
    for i, day in enumerate(probe.observed_days()[:7]):
        transition = probe.transition_for(day)
        location = probe.case.locations[0 if i < 5 else 1]
        transition = replace(
            transition,
            after=transition.after.model_copy(update={"detected_location_id": location}),
            context_value=10.0,
        )
        transitions.append(transition)
        if i < 5:
            probe.system.core.process_transition(transition)
        elif i == 5:
            probe.run_direct_p5(
                transition,
                ciav_input=probe.ciav_input(
                    transition, outcome=CIAVOutcomeKind.DETECTED_SAME_LOCATION
                ),
            )
    core = probe.system.core
    blocked = {
        rid
        for rid in core._observed_events
        if core.observation_write_eligibility(rid)["origin_write_blocked"]
    }
    assert len(blocked) == 1
    target = blocked.pop()
    assert target not in core._committed_events
    assert target in {item.revision_id for item in core._quarantined_events}
    assert not core.observation_write_eligibility(target)["write_eligible"]
    return probe, target, transitions[-1]


def test_nonempty_public_authorization_then_revoked_grantor():
    probe, target, transition = public_grant_prefix()
    core = probe.system.core
    result = core.process_transition(transition)
    assert core._last_ccrr_decision == "create"
    grantor = result.event_revision_id
    row = core.observation_write_eligibility(target)
    assert row["write_eligible"] and target in core._committed_events
    assert len(row["authorizations"]) == 1
    grant = row["authorizations"][0]
    assert grant["authority"] == "ccrr_habit_change_promotion"
    assert grant["granting_revision_id"] == str(grantor)
    assert content_sha256(grant["basis"]) == grant["basis_sha256"]
    bundle = old._feedback(probe, grantor)
    journal = old._journal(probe)
    old._apply(probe, bundle)
    assert not core.observation_write_eligibility(target)["write_eligible"]
    assert target not in core._committed_events
    old._assert_reconciled_against_journal(probe, journal)
    replay = old._apply(probe, bundle)
    assert replay.statistic_operations == (PrototypeStatisticOperation.QUARANTINE,)
    assert len(core.observation_write_eligibility(target)["authorizations"]) == 1


def test_authorization_is_rolled_back_with_failing_public_transition(monkeypatch):
    probe, target, transition = public_grant_prefix()
    core = probe.system.core
    before = old._full_state(probe)
    qualifications = dict(core._write_eligibility)

    def fault(_self, stage):
        if stage == "hybrid":
            raise RuntimeError("grant transaction failure")

    with monkeypatch.context() as patch:
        patch.setattr(type(core), "_transition_fault_hook", fault)
        with pytest.raises(RuntimeError, match="grant transaction failure"):
            core.process_transition(transition)
    assert old._full_state(probe) == before
    assert core._write_eligibility == qualifications
    assert not core.observation_write_eligibility(target)["write_eligible"]
    core.process_transition(transition)
    assert core.observation_write_eligibility(target)["write_eligible"]
    assert target in core._committed_events


def test_no_authority_and_foreign_feedback_cannot_promote():
    probe, target, _ = public_grant_prefix()
    core = probe.system.core
    donor = old._legacy_history()
    forged = old._feedback(donor, next(iter(donor.system.core._committed_events)))
    before = old._full_state(probe)
    with pytest.raises((ValueError, KeyError)):
        old._apply(probe, forged)
    assert old._full_state(probe) == before
    assert not core.observation_write_eligibility(target)["write_eligible"]
    # Legitimate retraction elsewhere is not an authorization for the blocked row.
    old._apply(probe, old._feedback(probe, next(iter(core._committed_events))))
    assert target not in core._committed_events


@pytest.mark.parametrize(
    "fault",
    [
        "omit_correction",
        "extra_blocked",
        "wrong_weight",
        "wrong_location",
        "duplicate_accounting",
        "missed_retraction",
        "rollback_residue",
        "missing_log",
    ],
)
def test_independent_reference_detects_controlled_faults(fault):
    probe = old._adaptive_history()
    core = probe.system.core
    journal = old._journal(probe)
    target = next(iter(core._committed_events))
    parent = core._committed_events[target]
    new, _, _ = correction(probe, target)
    old._assert_reconciled_against_journal(probe, journal)  # positive control first
    if fault == "omit_correction":
        core._committed_events.pop(new)
    elif fault == "extra_blocked":
        blocked = next(rid for rid, row in journal.items() if row.origin_write_blocked)
        core._committed_events[blocked] = core._observed_events[blocked]
    elif fault == "wrong_weight":
        core._committed_events[new] = replace(
            core._committed_events[new], statistical_owner_weight=0.1234
        )
    elif fault == "wrong_location":
        event = core._committed_events[new]
        core._committed_events[new] = replace(
            event, location_id=next(loc for loc in probe.case.locations if loc != event.location_id)
        )
    elif fault == "duplicate_accounting":
        event = core._committed_events[new]
        core._habit.update_audited(event.evidence, weight_multiplier=event.propensity_weight)
    elif fault == "missed_retraction":
        core._committed_events[target] = parent
    elif fault == "rollback_residue":
        core._committed_events[uuid4()] = parent
    elif fault == "missing_log":
        core._revision_transactions = ()
    with pytest.raises(AssertionError):
        old._assert_reconciled_against_journal(probe, journal)


def test_feedback_dedup_commit_failure_rolls_back_whole_transaction(monkeypatch):
    probe = old._legacy_history()
    core = probe.system.core
    journal = old._journal(probe)
    target = next(iter(core._committed_events))
    bundle = old._feedback(probe, target)
    policy = CalibratedRetractionPolicy(
        corrected_location_id=core._committed_events[target].location_id
    )
    before = old._full_state(probe)
    qualification = dict(core._write_eligibility)
    original = type(core._hybrid_loop).commit_execution_feedback

    def fail_after_commit(self, projected):
        original(self, projected)
        raise RuntimeError("feedback commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(type(core._hybrid_loop), "commit_execution_feedback", fail_after_commit)
        with pytest.raises(RuntimeError, match="feedback commit failure"):
            old._apply(probe, bundle, policy=policy)
    assert old._full_state(probe) == before
    assert core._write_eligibility == qualification
    assert not core.revision_transactions
    old._apply(probe, bundle, policy=policy)
    old._assert_reconciled_against_journal(probe, journal)


def test_public_grant_is_exactly_once_and_qualified_parent_can_be_corrected():
    probe, target, transition = public_grant_prefix()
    core = probe.system.core
    core.process_transition(transition)
    qualification = core.observation_write_eligibility(target)
    before = old._full_state(probe)
    with pytest.raises(ValueError, match="chronological"):
        core.process_transition(transition)
    assert old._full_state(probe) == before
    assert core.observation_write_eligibility(target) == qualification
    journal = old._journal(probe)
    corrected, _, _ = correction(probe, target)
    assert core.observation_write_eligibility(corrected)["write_eligible"]
    assert not core.observation_write_eligibility(target)["write_eligible"]
    old._assert_reconciled_against_journal(probe, journal)


@pytest.mark.parametrize("target_index", [3, 4, 5, 6, 8, 9, 10, 11])
def test_ccrr_nonadmission_is_explicit_failure_with_no_correction_residue(target_index):
    probe = old._legacy_history()
    core = probe.system.core
    old._journal(probe)
    target = list(core._committed_events)[target_index]
    before = old._full_state(probe)
    qualification = dict(core._write_eligibility)
    with pytest.raises(ValueError, match="CORRECT not admitted by CCRR"):
        correction(probe, target, same=False)
    assert old._full_state(probe) == before
    assert core._write_eligibility == qualification
    assert not core.revision_transactions
    assert target in core._committed_events


@pytest.mark.parametrize(
    "field", ["parent_eligibility_sha256", "correction_outcome_sha256", "authorizations"]
)
def test_forged_correction_qualification_is_rejected(field):
    probe = old._legacy_history()
    core = probe.system.core
    original = next(iter(core._committed_events))
    corrected, _, _ = correction(probe, original)
    record = core._write_eligibility[corrected]
    value = () if field == "authorizations" else "0" * 64
    core._write_eligibility[corrected] = replace(record, **{field: value})
    assert not core.observation_write_eligibility(corrected)["write_eligible"]
    before = old._full_state(probe)
    with pytest.raises(ValueError, match="parent has no valid write eligibility"):
        correction(probe, corrected)
    assert old._full_state(probe) == before
