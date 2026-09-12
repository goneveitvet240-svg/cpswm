"""Real CCRR cancellation restores the parent via the sole production ledger."""

import sys
from dataclasses import replace
from uuid import uuid4

import pytest
import test_structure_two_formal_revision_lineage as old
from structure_two_backbone_wiring_probe import CalibratedRetractionPolicy
from structure_two_revision_oracle import FrozenRevisionOracle
from test_structure_two_w3_round5_boundaries import direct_outcome, request_for
from test_structure_two_w3_round6_prepared_boundary import snapshot

from cpswm.system.prototype_spine import EventRevisionKind, EventRevisionOutcome
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_semantic_identity import semantic_memory_state


def pending(generations=0, feedback_id=None, *, reinforce=False, before_events=None):
    if reinforce:
        from test_project_one_automatic_regime_loop import _reinforce_once

        probe = old.BackboneWiringProbe.build(seed=7)
        for observation in probe.observed_days()[:12]:
            transition = probe.transition_for(observation)
            last = probe.system.process_transition(transition)
        _reinforce_once(
            case=probe.case, spine=probe.system.core, transition=transition, source_result=last
        )
    else:
        probe = old._legacy_history(12)
    core = probe.system.core
    target = list(core._committed_events)[11]
    for _ in range(generations):
        outcome = direct_outcome(core, target, True, core._committed_events[target].owner_mass)
        core.apply_event_revision_outcome(outcome)
        target = outcome.corrected_revision_id
    outcome = direct_outcome(core, target, False, core._committed_events[target].owner_mass)
    _, _, interpretation = FrozenRevisionOracle(probe).prepare(
        old._feedback(probe, target),
        CalibratedRetractionPolicy(corrected_location_id=outcome.corrected_location_id),
    )
    outcome = replace(
        outcome,
        corrected_owner_mass=interpretation.evidence_strength,
        evidence_source_record_ids=(feedback_id or uuid4(),),
    )
    original = core._committed_events[target]
    if before_events is not None:
        before_events.extend(core._committed_events.values())
    qualification = core._write_eligibility[target]
    request = request_for(core, outcome)
    assert core.apply_project_one_stat_request(request).status.value == "deferred_due_to_quarantine"
    assert target not in core._committed_events
    assert core.is_quarantined_revision(outcome.corrected_revision_id)
    assert core._deferred_project_one_requests
    return probe, target, outcome, request, original, qualification


def verify_cancelled(probe, target, outcome, request, original, qualification):
    core = probe.system.core
    child = outcome.corrected_revision_id
    assert target in core._committed_events and target in core._observed_events
    assert target in core._fast_action_events
    assert child not in core._committed_events and child not in core._observed_events
    assert child not in core._fast_action_events and not core.is_quarantined_revision(child)
    assert core._write_eligibility[target] == qualification
    assert core.observation_write_eligibility(target)["write_eligible"]
    assert not core.observation_write_eligibility(child)["write_eligible"]
    restored = core._committed_events[target]
    assert restored.location_id == original.location_id
    assert restored.statistical_owner_weight == original.statistical_owner_weight
    assert restored.evidence.source_record_ids == original.evidence.source_record_ids
    assert restored.hybrid_revision_id != original.hybrid_revision_id
    ledger = core._hybrid_loop.ledger
    assert len(ledger.live_promoted_records_for_revision(restored.hybrid_revision_id)) == 1
    assert not ledger.live_promoted_records_for_revision(original.hybrid_revision_id)
    assert not ledger.live_promoted_records_for_revision(child)
    assert not core._deferred_project_one_requests
    receipts = core.application_receipts_for_feedback(request.source_feedback_record_id)
    assert receipts[-1].status.value == "rejected"
    assert receipts[-1].new_belief_snapshot_id == core.current_snapshot.snapshot_id
    assert len(core._correction_cancellations) == 1
    FrozenRevisionOracle(probe).check(probe)
    semantic_memory_state(core)
    before = snapshot(probe)
    before_semantic = content_sha256(semantic_memory_state(core))
    before_receipts = tuple(receipts)
    replay = core.apply_project_one_stat_request(request)
    assert replay.status.value == "replay_noop"
    # The established request contract appends an audit-only replay receipt.
    # Check that exact allowed change, plus unchanged memory and contribution.
    assert snapshot(probe)[1:] == before[1:]
    assert content_sha256(semantic_memory_state(core)) == before_semantic
    assert tuple(core.application_receipts_for_feedback(request.source_feedback_record_id)) == (
        *before_receipts,
        replay,
    )
    assert not core._deferred_correction_restore


@pytest.mark.parametrize("generations", [0, 1, 2])
@pytest.mark.parametrize("entry", ["core", "production_wrapper"])
def test_public_cancellation_restores_full_nonempty_parent_and_preserves_new_observation(
    generations, entry
):
    args = pending(generations)
    probe = args[0]
    owner = probe.system.core if entry == "core" else probe.system
    result = owner.process_transition(probe.transition_for(probe.observed_days()[12]))
    assert result.event_revision_id in probe.system.core._observed_events
    verify_cancelled(*args)


@pytest.mark.parametrize(
    "stage", ["cancellation_lineage", "hybrid", "dirichlet", "rls", "cancellation_replay"]
)
@pytest.mark.parametrize("exception", [RuntimeError, KeyboardInterrupt])
def test_real_cancellation_interruption_restores_pending_transaction_and_can_retry(
    stage, exception
):
    args = pending()
    probe, core = args[0], args[0].system.core
    before = snapshot(probe)
    method = core._revision_fault_hook.__func__.__code__
    original_profiler = sys.getprofile()
    hits = []

    def interrupt(frame, event, value):
        if frame.f_code is method and event == "call" and frame.f_locals["stage"] == stage:
            hits.append(stage)
            raise exception(stage)

    try:
        sys.setprofile(interrupt)
        with pytest.raises(exception, match=stage):
            probe.system.process_transition(probe.transition_for(probe.observed_days()[12]))
    finally:
        sys.setprofile(original_profiler)
    assert hits == [stage]
    assert snapshot(probe) == before
    probe.system.process_transition(probe.transition_for(probe.observed_days()[12]))
    verify_cancelled(*args)


def test_restored_parent_can_be_corrected_again_then_retracted_without_resurrection():
    args = pending()
    probe, target, *_ = args
    core = probe.system.core
    core.process_transition(probe.transition_for(probe.observed_days()[12]))
    verify_cancelled(*args)
    outcome = direct_outcome(core, target, True, core._committed_events[target].owner_mass)
    core.apply_event_revision_outcome(outcome)
    assert target not in core._observed_events
    assert outcome.corrected_revision_id in core._committed_events
    FrozenRevisionOracle(probe).check(probe)
    semantic_memory_state(core)
    core.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.RETRACT,
            superseded_revision_id=outcome.corrected_revision_id,
            evidence_source_record_ids=(uuid4(),),
            rationale="late public retraction after cancellation",
        )
    )
    assert target not in core._committed_events
    assert outcome.corrected_revision_id not in core._committed_events
    FrozenRevisionOracle(probe).check(probe)
    semantic_memory_state(core)


@pytest.mark.parametrize("ending", ["cancel", "correct", "retract"])
def test_cancellation_semantics_reproduce_with_distinct_execution_lineage(ending):
    semantic, execution = [], []
    feedback, later_feedback = uuid4(), uuid4()
    for _ in range(2):
        args = pending(feedback_id=feedback)
        probe = args[0]
        probe.system.process_transition(probe.transition_for(probe.observed_days()[12]))
        verify_cancelled(*args)
        core = probe.system.core
        if ending != "cancel":
            op = direct_outcome(core, args[1], True, core._committed_events[args[1]].owner_mass)
            op = replace(op, evidence_source_record_ids=(later_feedback,))
            if ending == "retract":
                op = EventRevisionOutcome(
                    kind=EventRevisionKind.RETRACT,
                    superseded_revision_id=args[1],
                    evidence_source_record_ids=(later_feedback,),
                    rationale="late withdrawal",
                )
            core.apply_event_revision_outcome(op)
            FrozenRevisionOracle(probe).check(probe)
        semantic.append(content_sha256(semantic_memory_state(probe.system.core)))
        execution.append(snapshot(probe)[0])
    assert semantic[0] == semantic[1]
    assert execution[0] != execution[1]


@pytest.mark.parametrize(
    "attack", ["digest", "request", "parent", "trigger", "sequence", "missing"]
)
def test_frozen_cancellation_oracle_rejects_corrupted_and_resealed_operations(attack):
    from cpswm.system.structure_two_particle_workspace import native_content_sha256

    args = pending()
    probe, core = args[0], args[0].system.core
    core.process_transition(probe.transition_for(probe.observed_days()[12]))
    record = core._correction_cancellations[0]
    if attack == "missing":
        core._correction_cancellations = ()
    else:
        if attack == "digest":
            record = replace(record, body_sha256="0" * 64)
        else:
            if attack == "request":
                record = replace(record, request_fingerprint="0" * 64)
            elif attack == "parent":
                record = replace(
                    record, parent_event=replace(record.parent_event, source_record_id=uuid4())
                )
            elif attack == "trigger":
                record = replace(record, trigger_revision_id=uuid4())
            else:
                record = replace(record, after_operation_count=len(core.revision_transactions) + 1)
            record = replace(record, body_sha256=native_content_sha256(record.body()))
        core._correction_cancellations = (record,)
    with pytest.raises((AssertionError, ValueError)):
        FrozenRevisionOracle(probe).check(probe)
    if attack != "missing":
        with pytest.raises(ValueError):
            semantic_memory_state(core)


def test_cancellation_restores_original_nonempty_derived_bundle_without_fresh_authority():
    frozen = []
    args = pending(reinforce=True, before_events=frozen)
    probe, core = args[0], args[0].system.core
    derived = [e for e in frozen if e.derived_from_revision_id is not None]
    assert len(derived) == 1 and derived[0].statistical_owner_weight > 0
    assert derived[0].revision_id not in core._committed_events
    core.process_transition(probe.transition_for(probe.observed_days()[12]))
    assert derived[0].revision_id in core._committed_events
    restored = core._committed_events[derived[0].revision_id]
    assert restored.statistical_owner_weight == derived[0].statistical_owner_weight
    assert restored.source_record_id == derived[0].source_record_id
    assert restored.evidence.source_record_ids == derived[0].evidence.source_record_ids
    assert restored.hybrid_revision_id != derived[0].hybrid_revision_id
    # Own observation traversal and independently frozen accepted derived input;
    # the restored committed set is never used to define expected contributions.
    reference = FrozenRevisionOracle(probe)
    observed, habit, rls = reference.reference()
    for event in derived:
        assert event.derived_from_revision_id in observed
        habit.update_audited(event.evidence, weight_multiplier=event.propensity_weight)
        rls.update(event.rls_sample, reference.embeddings)
    expected = [*observed.values(), *derived]
    for location in core.locations:
        assert core.hybrid_alpha(location) == pytest.approx(
            sum(e.statistical_owner_weight for e in expected if e.location_id == location)
        )
    assert core._habit.canonical_state_hash() == habit.canonical_state_hash()
    for regime in set(rls._heads) | set(core._regimes._heads):
        assert content_sha256(core.rls_regime_snapshot(regime)) == content_sha256(
            rls.regime_snapshot(regime)
        )
    semantic_memory_state(core)
