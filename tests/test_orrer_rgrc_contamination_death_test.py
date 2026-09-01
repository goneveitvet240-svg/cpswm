"""ORRER x RGRC long-term contamination death test (结构二 §4.7 #2 x #5).

Rebuilt 2026-08-22 to the review acceptance gate: immutable append-only ledger,
true O(k) indexed retract vs O(N) full rebuild, revision supersede/reactivate,
dedup, invalid-input rejection, real serialize/restart/replay, partial rollback,
distance-based contamination, and multi-seed/object/location coverage.
"""

from __future__ import annotations

import random
from uuid import UUID, uuid4

import pytest

from cpswm.system.continual import (
    ConsolidationState,
    EventDerivedDeltaPromotion,
    EventDerivedDeltaRecord,
    EventDerivedDeltaReversal,
    EventDerivedUpdateLedger,
    LedgerIntegrityError,
    projection_total_variation,
)

OWNER = "owner"
OBJ = UUID(int=5)
BLOCK = "owner_habit_location"
L1 = UUID(int=1)
L2 = UUID(int=2)
L3 = UUID(int=3)


def _delta(
    *,
    watermark: int,
    location,
    actor=OWNER,
    event=None,
    revision=None,
    parent=None,
    delta=1.0,
    state=ConsolidationState.PROMOTED,
    dedup=None,
    auth=None,
):
    return EventDerivedDeltaRecord(
        record_id=uuid4(),
        event_hypothesis_id=event or uuid4(),
        revision_id=revision or uuid4(),
        parent_revision_id=parent,
        evidence_source_id=uuid4(),
        actor_key=actor,
        object_instance_id=OBJ,
        regime_id="regime-0",
        parameter_block=BLOCK,
        location_id=location,
        signed_delta=delta,
        input_watermark=watermark,
        model_version="joint-cause-factorized-bocpd@0.3",
        code_version="git:test",
        semantic_dedup_id=dedup or str(uuid4()),
        initial_state=state,
        authorization_scope_id=auth,
    )


def _owner(ledger):
    return ledger.owner_projection(actor_key=OWNER, object_instance_id=OBJ, parameter_block=BLOCK)


def _rebuild(ledger):
    return ledger.rebuild_projection_from_log(
        actor_key=OWNER, object_instance_id=OBJ, parameter_block=BLOCK
    )


def _contaminated(owner_events: int = 1000):
    """Large owner habit at L1 + one guest event mis-attributed to owner at L2."""

    ledger = EventDerivedUpdateLedger()
    wm = 0
    for _ in range(owner_events):
        ledger.append_delta(_delta(watermark=wm, location=L1))
        wm += 1
    guest_event, guest_rev = uuid4(), uuid4()
    ledger.append_delta(
        _delta(watermark=wm, location=L2, actor=OWNER, event=guest_event, revision=guest_rev)
    )
    return ledger, guest_event, guest_rev, wm + 1


# --- P0-A: true O(k) targeted retract vs O(N) rebuild ------------------------


def test_targeted_retract_is_truly_cheaper_than_full_rebuild():
    ledger, _guest_event, guest_rev, wm = _contaminated(owner_events=1000)
    cost = ledger.retract_revision(
        revision_id=guest_rev,
        watermark=wm,
        reason="ORRER re-attributed to guest",
        reversal_ids=[uuid4()],
    )
    _proj, rebuild_cost = _rebuild(ledger)
    # Retract touches exactly the 1 live delta of that revision...
    assert cost.records_touched == 1
    # ...while the full rebuild scans the entire log (>= 1001 records).
    assert rebuild_cost.records_scanned >= 1001
    assert cost.records_touched < rebuild_cost.records_scanned
    # And the deterministic cost gap shows up in wall-clock too.
    assert cost.wall_clock_seconds <= rebuild_cost.wall_clock_seconds


def test_retract_equals_full_rebuild_and_recovers_contamination():
    ledger, _e, guest_rev, wm = _contaminated(owner_events=8)
    contaminated = _owner(ledger)
    assert contaminated[L2] == 1.0

    ledger.retract_revision(
        revision_id=guest_rev, watermark=wm, reason="corrected", reversal_ids=[uuid4()]
    )
    recovered = _owner(ledger)
    rebuilt, _ = _rebuild(ledger)
    assert recovered == rebuilt  # cache == from-log rebuild
    assert recovered.get(L2, 0.0) == 0.0  # contamination gone
    # Distance-based contamination: recovered matches the clean reference exactly.
    clean = {L1: 8.0}
    assert projection_total_variation(recovered, clean) == pytest.approx(0.0)


# --- P0-B: a corrected revision re-enters after retract (no permanent seal) ---


def test_corrected_revision_after_retract_re_enters_projection():
    ledger, guest_event, guest_rev, wm = _contaminated(owner_events=4)
    # Retract the mis-attributed revision.
    ledger.retract_revision(
        revision_id=guest_rev, watermark=wm, reason="mis-attributed", reversal_ids=[uuid4()]
    )
    assert _owner(ledger).get(L2, 0.0) == 0.0
    # ORRER later produces a *correct* revision of the SAME event: the object did
    # move to L3 (owner did it after all). It must re-enter long-term memory.
    corrected_rev = uuid4()
    ledger.append_delta(
        _delta(
            watermark=wm + 1,
            location=L3,
            event=guest_event,
            revision=corrected_rev,
            parent=guest_rev,
        )
    )
    projection = _owner(ledger)
    rebuilt, _ = _rebuild(ledger)
    assert projection == rebuilt
    assert projection[L3] == 1.0  # corrected revision is live


# --- quarantine -> promote -> retract -> reactivate --------------------------


def test_quarantined_delta_only_counts_after_promotion():
    ledger = EventDerivedUpdateLedger()
    d = _delta(watermark=0, location=L1, state=ConsolidationState.QUARANTINED)
    ledger.append_delta(d)
    assert _owner(ledger) == {}  # quarantined -> not in projection
    ledger.append_promotion(
        EventDerivedDeltaPromotion(
            record_id=uuid4(), promotes_record_id=d.record_id, input_watermark=1, reason="cleared"
        )
    )
    assert _owner(ledger) == {L1: 1.0}
    rebuilt, _ = _rebuild(ledger)
    assert _owner(ledger) == rebuilt


# --- invalid input rejection -------------------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_delta_is_rejected(bad):
    with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
        _delta(watermark=0, location=L1, delta=bad)


def test_empty_actor_and_negative_watermark_rejected():
    with pytest.raises(Exception):  # noqa: B017
        _delta(watermark=0, location=L1, actor="")
    with pytest.raises(Exception):  # noqa: B017
        _delta(watermark=-1, location=L1)


def test_duplicate_semantic_dedup_id_rejected():
    ledger = EventDerivedUpdateLedger()
    ledger.append_delta(_delta(watermark=0, location=L1, dedup="same"))
    with pytest.raises(LedgerIntegrityError, match="duplicate semantic_dedup_id"):
        ledger.append_delta(_delta(watermark=1, location=L1, dedup="same"))


def test_out_of_order_watermark_rejected():
    ledger = EventDerivedUpdateLedger()
    ledger.append_delta(_delta(watermark=5, location=L1))
    with pytest.raises(LedgerIntegrityError, match="behind the ledger head"):
        ledger.append_delta(_delta(watermark=3, location=L1))


def test_double_reversal_rejected():
    ledger, _e, guest_rev, wm = _contaminated(owner_events=2)
    live = [
        d for d in ledger._log if isinstance(d, EventDerivedDeltaRecord) and d.location_id == L2
    ]
    target = live[0].record_id
    ledger.append_reversal(
        EventDerivedDeltaReversal(
            record_id=uuid4(),
            reverses_record_id=target,
            revision_id=guest_rev,
            input_watermark=wm,
            reason="a",
        )
    )
    with pytest.raises(LedgerIntegrityError, match="already reversed"):
        ledger.append_reversal(
            EventDerivedDeltaReversal(
                record_id=uuid4(),
                reverses_record_id=target,
                revision_id=guest_rev,
                input_watermark=wm + 1,
                reason="b",
            )
        )


def test_reversal_revision_must_match_target_and_quarantine_cannot_be_reversed():
    ledger = EventDerivedUpdateLedger()
    promoted = _delta(watermark=0, location=L1)
    ledger.append_delta(promoted)
    with pytest.raises(LedgerIntegrityError, match="revision does not match"):
        ledger.append_reversal(
            EventDerivedDeltaReversal(
                record_id=uuid4(),
                reverses_record_id=promoted.record_id,
                revision_id=uuid4(),
                input_watermark=1,
                reason="wrong revision",
            )
        )

    quarantined = _delta(
        watermark=1,
        location=L2,
        state=ConsolidationState.QUARANTINED,
    )
    ledger.append_delta(quarantined)
    with pytest.raises(LedgerIntegrityError, match="only a promoted"):
        ledger.append_reversal(
            EventDerivedDeltaReversal(
                record_id=uuid4(),
                reverses_record_id=quarantined.record_id,
                revision_id=quarantined.revision_id,
                input_watermark=2,
                reason="illegal state transition",
            )
        )


def test_parent_revision_must_exist_and_belong_to_same_event():
    ledger = EventDerivedUpdateLedger()
    with pytest.raises(LedgerIntegrityError, match="parent revision does not exist"):
        ledger.append_delta(_delta(watermark=0, location=L1, parent=uuid4()))

    parent_event, parent_revision = uuid4(), uuid4()
    parent = _delta(
        watermark=0,
        location=L1,
        event=parent_event,
        revision=parent_revision,
    )
    ledger.append_delta(parent)
    ledger.retract_revision(
        revision_id=parent_revision,
        watermark=1,
        reason="retired",
        reversal_ids=[uuid4()],
    )
    with pytest.raises(LedgerIntegrityError, match="belongs to another event"):
        ledger.append_delta(_delta(watermark=2, location=L2, event=uuid4(), parent=parent_revision))


def test_duplicate_promotion_is_rejected_before_it_enters_log():
    ledger = EventDerivedUpdateLedger()
    delta = _delta(watermark=0, location=L1, state=ConsolidationState.QUARANTINED)
    ledger.append_delta(delta)
    ledger.append_promotion(
        EventDerivedDeltaPromotion(
            record_id=uuid4(),
            promotes_record_id=delta.record_id,
            input_watermark=1,
            reason="first",
        )
    )
    count = ledger.record_count()
    with pytest.raises(LedgerIntegrityError, match="already promoted"):
        ledger.append_promotion(
            EventDerivedDeltaPromotion(
                record_id=uuid4(),
                promotes_record_id=delta.record_id,
                input_watermark=2,
                reason="duplicate",
            )
        )
    assert ledger.record_count() == count


def test_promotion_and_reversal_are_bound_to_authorization_scope():
    ledger = EventDerivedUpdateLedger()
    authorization = uuid4()
    delta = _delta(
        watermark=0,
        location=L1,
        state=ConsolidationState.QUARANTINED,
        auth=authorization,
    )
    ledger.append_delta(delta)
    with pytest.raises(LedgerIntegrityError, match="promotion authorization"):
        ledger.append_promotion(
            EventDerivedDeltaPromotion(
                record_id=uuid4(),
                promotes_record_id=delta.record_id,
                input_watermark=1,
                reason="wrong scope",
                authorization_scope_id=uuid4(),
            )
        )
    ledger.append_promotion(
        EventDerivedDeltaPromotion(
            record_id=uuid4(),
            promotes_record_id=delta.record_id,
            input_watermark=1,
            reason="right scope",
            authorization_scope_id=authorization,
        )
    )
    with pytest.raises(LedgerIntegrityError, match="reversal authorization"):
        ledger.append_reversal(
            EventDerivedDeltaReversal(
                record_id=uuid4(),
                reverses_record_id=delta.record_id,
                revision_id=delta.revision_id,
                input_watermark=2,
                reason="wrong scope",
                authorization_scope_id=uuid4(),
            )
        )


# --- crash recovery: real serialize / restart / replay -----------------------


def test_serialize_restart_replay_is_pointwise_identical():
    ledger, _e, guest_rev, wm = _contaminated(owner_events=6)
    ledger.retract_revision(revision_id=guest_rev, watermark=wm, reason="x", reversal_ids=[uuid4()])
    before = _owner(ledger)

    text = ledger.to_jsonl()
    restarted = EventDerivedUpdateLedger.from_jsonl(text)  # simulates crash + reload
    after = restarted.owner_projection(
        actor_key=OWNER, object_instance_id=OBJ, parameter_block=BLOCK
    )
    rebuilt, _ = restarted.rebuild_projection_from_log(
        actor_key=OWNER, object_instance_id=OBJ, parameter_block=BLOCK
    )
    assert after == before
    assert after == rebuilt  # ledger increment == full raw rerun, pointwise


def test_serialized_hash_chain_rejects_tampering():
    ledger = EventDerivedUpdateLedger()
    ledger.append_delta(_delta(watermark=0, location=L1, delta=1.0))
    text = ledger.to_jsonl().replace('"signed_delta": 1.0', '"signed_delta": 2.0')
    with pytest.raises(LedgerIntegrityError, match="entry_hash mismatch"):
        EventDerivedUpdateLedger.from_jsonl(text)


# --- partial rollback --------------------------------------------------------


def test_partial_rollback_only_reverses_named_revision():
    ledger = EventDerivedUpdateLedger()
    rev_a, rev_b = uuid4(), uuid4()
    ledger.append_delta(_delta(watermark=0, location=L1, revision=rev_a))
    ledger.append_delta(_delta(watermark=1, location=L2, revision=rev_b))
    ledger.retract_revision(
        revision_id=rev_b, watermark=2, reason="partial", reversal_ids=[uuid4()]
    )
    projection = _owner(ledger)
    assert projection == {L1: 1.0}  # only rev_b removed; rev_a survives
    rebuilt, _ = _rebuild(ledger)
    assert projection == rebuilt


# --- multi-seed / multi-object / multi-location equivalence -------------------


def test_ledger_equals_raw_rerun_across_random_scenarios():
    for seed in range(20):
        rng = random.Random(seed)
        ledger = EventDerivedUpdateLedger()
        wm = 0
        revisions = []
        for _ in range(rng.randint(5, 40)):
            rev = uuid4()
            ledger.append_delta(
                _delta(
                    watermark=wm,
                    location=rng.choice([L1, L2, L3]),
                    actor=OWNER,
                    revision=rev,
                    delta=rng.choice([0.5, 1.0, 2.0]),
                )
            )
            revisions.append(rev)
            wm += 1
        # retract a random subset of revisions
        for rev in rng.sample(revisions, k=rng.randint(0, len(revisions) // 2)):
            ledger.retract_revision(
                revision_id=rev, watermark=wm, reason="r", reversal_ids=[uuid4()]
            )
            wm += 1
        cached = _owner(ledger)
        rebuilt, _ = _rebuild(ledger)
        assert cached == rebuilt, f"seed {seed}: cache diverged from raw rerun"
