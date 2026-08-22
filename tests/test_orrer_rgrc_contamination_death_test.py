"""ORRER x RGRC long-term contamination death test (结构二 §4.7 #2 x #5).

The next paper gate 结构二 named: when ORRER revises a hidden event's actor
responsibility, RGRC must reversibly retract the habit updates derived from that
event so the owner model recovers -- to *exactly* the full-rerun state -- at
lower cost than recomputing from scratch.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from cpswm.system.continual import EventDerivedUpdateLedger, owner_contamination_rate

OWNER = "owner"
OBJ = UUID(int=5)
L1 = UUID(int=1)  # owner's home / habitual location
L2 = UUID(int=2)  # where a guest moved the object


def _contaminated_ledger(owner_event_count: int = 8):
    """Owner habit at L1, plus one guest event mis-attributed to the owner at L2."""

    ledger = EventDerivedUpdateLedger()
    for _ in range(owner_event_count):
        ledger.record(
            source_event_id=uuid4(),
            revision_no=0,
            actor_key=OWNER,
            object_instance_id=OBJ,
            location_id=L1,
            weight=1.0,
        )
    guest_event = uuid4()
    # ORRER's pre-revision attribution mis-assigns the guest move to the owner.
    ledger.record(
        source_event_id=guest_event,
        revision_no=0,
        actor_key=OWNER,
        object_instance_id=OBJ,
        location_id=L2,
        weight=1.0,
    )
    return ledger, guest_event


def test_orrer_revision_reverses_owner_contamination_and_matches_full_rerun():
    ledger, guest_event = _contaminated_ledger(owner_event_count=8)

    contaminated = ledger.owner_projection(owner_key=OWNER, object_instance_id=OBJ)
    assert contaminated[L2] == 1.0
    assert owner_contamination_rate(contaminated, home_location_id=L1) > 0.0

    # ORRER re-attributes the guest event away from the owner -> RGRC retract.
    retract_cost = ledger.retract_event(guest_event)
    recovered = ledger.owner_projection(owner_key=OWNER, object_instance_id=OBJ)

    # Full rerun over surviving events reaches the *same* owner projection.
    rebuilt, rebuild_cost = ledger.rebuild_owner_projection(owner_key=OWNER, object_instance_id=OBJ)

    # Equivalence: reversible consolidation == recompute-from-scratch.
    assert recovered == rebuilt
    # Full recovery: the contaminating L2 mass is gone.
    assert recovered.get(L2, 0.0) == 0.0
    assert owner_contamination_rate(recovered, home_location_id=L1) == 0.0
    # RGRC is cheaper: it touches only the revised event, not every entry.
    assert retract_cost == 1
    assert rebuild_cost == 9  # 8 owner + 1 retracted guest scanned
    assert retract_cost < rebuild_cost


def test_retract_is_idempotent_across_restart_semantics():
    ledger, guest_event = _contaminated_ledger()
    first = ledger.retract_event(guest_event)
    second = ledger.retract_event(guest_event)
    assert first == 1
    assert second == 0  # already retracted; no double reversal
    projection = ledger.owner_projection(owner_key=OWNER, object_instance_id=OBJ)
    rebuilt, _ = ledger.rebuild_owner_projection(owner_key=OWNER, object_instance_id=OBJ)
    assert projection == rebuilt


def test_cached_projection_always_equals_full_rebuild():
    # RGRC invariant: the incrementally-maintained projection is reconstructable
    # from the log at every point.
    ledger, guest_event = _contaminated_ledger(owner_event_count=5)
    for _ in range(2):
        cached = ledger.owner_projection(owner_key=OWNER, object_instance_id=OBJ)
        rebuilt, _ = ledger.rebuild_owner_projection(owner_key=OWNER, object_instance_id=OBJ)
        assert cached == rebuilt
        ledger.retract_event(guest_event)


def test_non_owner_attributed_events_never_touch_owner_projection():
    # A guest event correctly attributed to the guest must not enter the owner
    # projection in the first place (no contamination to retract).
    ledger = EventDerivedUpdateLedger()
    ledger.record(
        source_event_id=uuid4(),
        revision_no=0,
        actor_key="guest",
        object_instance_id=OBJ,
        location_id=L2,
        weight=1.0,
    )
    assert ledger.owner_projection(owner_key=OWNER, object_instance_id=OBJ) == {}
