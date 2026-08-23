"""Atomic replace_promoted_revision: all-or-nothing ORRER correction (review fix #2).

The retract-then-promote swap runs under one lock with every fallible check ahead
of any mutation, so a rejected replacement leaves the ledger byte-for-byte as it
was and no reader can observe the belief withdrawn but the correction missing.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from cpswm.system.continual.hybrid_event_to_task_loop import (
    HybridEventToTaskCoordinatorLoop,
    OwnerPlacementInput,
)
from cpswm.system.continual.hybrid_statistics import (
    ConsolidationRiskCertificate,
    HybridConsolidationState,
    HybridLedgerError,
    HybridPromotion,
    HybridStatisticDelta,
    HybridStatisticLedger,
    StatisticKey,
)

OWNER = "owner"
OBJ = UUID(int=5)
L1 = UUID(int=1)
L2 = UUID(int=2)


def _key(location: UUID) -> StatisticKey:
    return StatisticKey(
        actor_key=OWNER,
        object_instance_id=OBJ,
        regime_id="owner-habit",
        parameter_block="owner_habit_location",
        location_id=location,
    )


EVENT = UUID(int=99)
SCOPE = UUID(int=7)


def _delta(
    *,
    revision_id,
    location,
    watermark,
    mass=0.8,
    parent=None,
    event=EVENT,
    scope=SCOPE,
    cluster=None,
) -> HybridStatisticDelta:
    return HybridStatisticDelta.from_weighted_sample(
        x=[1.0],
        y=mass,
        weight=mass,
        delta_alpha=mass,
        record_id=uuid4(),
        event_hypothesis_id=event,
        revision_id=revision_id,
        parent_revision_id=parent,
        evidence_cluster_id=cluster or uuid4(),
        semantic_dedup_id=f"{revision_id}:{location}:{watermark}",
        source_record_ids=(uuid4(),),
        authorization_scope_id=scope,
        key=_key(location),
        input_watermark=watermark,
        model_version="m@1",
        code_version="git:test",
    )


def _cert(delta: HybridStatisticDelta, *, allows: bool = True) -> ConsolidationRiskCertificate:
    return ConsolidationRiskCertificate(
        expected_task_loss=0.0 if allows else 5.0,
        uncertainty_penalty=0.0,
        maximum_allowed_risk=1.0,
        exact_verifier_id="test@0.1",
        counterfactual_id=uuid4(),
        subject_delta_record_id=delta.record_id,
        belief_snapshot_id=uuid4(),
        map_version=0,
    )


def _promotion(delta: HybridStatisticDelta, *, watermark: int, allows: bool = True):
    return HybridPromotion(
        record_id=uuid4(),
        promotes_record_id=delta.record_id,
        input_watermark=watermark,
        authorization_scope_id=delta.authorization_scope_id,
        reason="promote",
        risk_certificate=_cert(delta, allows=allows),
    )


def _promoted_ledger() -> tuple[HybridStatisticLedger, UUID]:
    """A ledger with one promoted revision at L2."""

    ledger = HybridStatisticLedger(feature_dim=1)
    superseded = uuid4()
    delta = _delta(revision_id=superseded, location=L2, watermark=0)
    ledger.append_delta(delta)
    ledger.promote(_promotion(delta, watermark=1))
    return ledger, superseded


def test_atomic_replace_swaps_belief_and_returns_projection():
    ledger, superseded = _promoted_ledger()
    before = ledger.projection(_key(L2)).alpha
    assert before == pytest.approx(0.8)

    corrected = _delta(revision_id=uuid4(), location=L2, watermark=2, mass=0.3, parent=superseded)
    live = ledger.live_promoted_records_for_revision(superseded)
    projection = ledger.replace_promoted_revision(
        superseded_revision_id=superseded,
        reversal_record_ids=tuple(uuid4() for _ in live),
        reversal_watermark=1,
        reversal_reason="orrer",
        corrected_delta=corrected,
        promotion=_promotion(corrected, watermark=3),
    )
    assert projection.alpha == pytest.approx(0.3)
    assert ledger.projection(_key(L2)).alpha == pytest.approx(0.3)
    # The superseded record is retracted; the correction is promoted -- both.
    assert ledger.state_of(live[0]) is HybridConsolidationState.RETRACTED
    assert ledger.state_of(corrected.record_id) is HybridConsolidationState.REACTIVATED
    ledger.assert_cache_matches_replay(_key(L2))


def _replace_kwargs(ledger, superseded, corrected, promotion):
    live = ledger.live_promoted_records_for_revision(superseded)
    return {
        "superseded_revision_id": superseded,
        "reversal_record_ids": tuple(uuid4() for _ in live),
        "reversal_watermark": 1,
        "reversal_reason": "orrer",
        "corrected_delta": corrected,
        "promotion": promotion,
    }


def _assert_unchanged(ledger, superseded):
    # The superseded revision is still live and the belief is intact.
    live = ledger.live_promoted_records_for_revision(superseded)
    assert len(live) == 1
    assert ledger.state_of(live[0]) is HybridConsolidationState.PROMOTED
    assert ledger.projection(_key(L2)).alpha == pytest.approx(0.8)


L3 = UUID(int=3)


def _fingerprint(ledger):
    """A total fingerprint of every observable ledger surface for rollback checks."""

    return (
        ledger.version,
        ledger.head_watermark,
        ledger.export_state().to_json(),
        tuple(round(ledger.projection(_key(loc)).alpha, 12) for loc in (L1, L2, L3)),
    )


def _multikey_ledger() -> tuple[HybridStatisticLedger, UUID]:
    """A ledger with one promoted revision carrying deltas at L1 and L2."""

    ledger = HybridStatisticLedger(feature_dim=1)
    superseded = uuid4()
    d1 = _delta(revision_id=superseded, location=L1, watermark=0, mass=0.8)
    d2 = _delta(revision_id=superseded, location=L2, watermark=1, mass=0.4)
    ledger.append_delta(d1)
    ledger.append_delta(d2)
    ledger.promote(_promotion(d1, watermark=2))
    ledger.promote(_promotion(d2, watermark=3))
    return ledger, superseded


def test_late_lineage_failure_is_rejected_before_mutation():
    # The reviewer's repro: a corrected delta whose event differs from the parent.
    # Now caught in pre-validation, so nothing is ever retracted.
    ledger, superseded = _promoted_ledger()
    before = _fingerprint(ledger)
    corrected = _delta(
        revision_id=uuid4(),
        location=L2,
        watermark=2,
        mass=0.3,
        parent=superseded,
        event=UUID(int=123),  # different event from the superseded revision
    )
    with pytest.raises(HybridLedgerError, match="belongs to another event"):
        ledger.replace_promoted_revision(
            **_replace_kwargs(ledger, superseded, corrected, _promotion(corrected, watermark=3))
        )
    assert _fingerprint(ledger) == before


def test_multi_key_replacement_swaps_every_affected_key():
    ledger, superseded = _multikey_ledger()
    assert ledger.projection(_key(L1)).alpha == pytest.approx(0.8)
    assert ledger.projection(_key(L2)).alpha == pytest.approx(0.4)
    corrected = _delta(revision_id=uuid4(), location=L2, watermark=4, mass=0.5, parent=superseded)
    live = ledger.live_promoted_records_for_revision(superseded)
    ledger.replace_promoted_revision(
        superseded_revision_id=superseded,
        reversal_record_ids=tuple(uuid4() for _ in live),
        reversal_watermark=4,
        reversal_reason="orrer",
        corrected_delta=corrected,
        promotion=_promotion(corrected, watermark=5),
    )
    # Both L1 and L2 parent deltas were retracted; the correction lands at L2.
    assert ledger.projection(_key(L1)).alpha == pytest.approx(0.0)
    assert ledger.projection(_key(L2)).alpha == pytest.approx(0.5)
    ledger.assert_cache_matches_replay(_key(L1))
    ledger.assert_cache_matches_replay(_key(L2))


def test_mixed_scope_parent_is_rejected_before_mutation():
    ledger = HybridStatisticLedger(feature_dim=1)
    superseded = uuid4()
    d1 = _delta(revision_id=superseded, location=L1, watermark=0, scope=UUID(int=7))
    d2 = _delta(revision_id=superseded, location=L2, watermark=1, scope=UUID(int=8))
    ledger.append_delta(d1)
    ledger.append_delta(d2)
    ledger.promote(_promotion(d1, watermark=2))
    ledger.promote(_promotion(d2, watermark=3))
    before = _fingerprint(ledger)
    # Correction carries scope 7, but the L2 parent delta is scope 8.
    corrected = _delta(
        revision_id=uuid4(),
        location=L2,
        watermark=4,
        mass=0.3,
        parent=superseded,
        scope=UUID(int=7),
    )
    live = ledger.live_promoted_records_for_revision(superseded)
    with pytest.raises(HybridLedgerError, match="authorization scope does not match"):
        ledger.replace_promoted_revision(
            superseded_revision_id=superseded,
            reversal_record_ids=tuple(uuid4() for _ in live),
            reversal_watermark=4,
            reversal_reason="orrer",
            corrected_delta=corrected,
            promotion=_promotion(corrected, watermark=5),
        )
    assert _fingerprint(ledger) == before


def test_monkeypatched_commit_failure_rolls_back_completely():
    # Even an unexpected failure *after* the retract has begun must leave the
    # ledger byte-for-byte unchanged.
    ledger, superseded = _promoted_ledger()
    before = _fingerprint(ledger)
    corrected = _delta(revision_id=uuid4(), location=L2, watermark=2, mass=0.3, parent=superseded)

    def _boom(_promotion_arg):
        raise RuntimeError("simulated crash during promote")

    ledger.promote = _boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="simulated crash"):
        ledger.replace_promoted_revision(
            **_replace_kwargs(ledger, superseded, corrected, _promotion(corrected, watermark=3))
        )
    del ledger.promote  # restore the real method
    assert _fingerprint(ledger) == before
    _assert_unchanged(ledger, superseded)


def test_rejected_risk_certificate_leaves_ledger_untouched():
    ledger, superseded = _promoted_ledger()
    version_before = ledger.version
    corrected = _delta(revision_id=uuid4(), location=L2, watermark=2, mass=0.3, parent=superseded)
    with pytest.raises(HybridLedgerError, match="risk gate"):
        ledger.replace_promoted_revision(
            **_replace_kwargs(
                ledger, superseded, corrected, _promotion(corrected, watermark=3, allows=False)
            )
        )
    assert ledger.version == version_before  # nothing appended: not even the retract
    _assert_unchanged(ledger, superseded)


def test_rejected_wrong_parent_leaves_ledger_untouched():
    ledger, superseded = _promoted_ledger()
    version_before = ledger.version
    # Correction that does not descend from the superseded revision.
    corrected = _delta(revision_id=uuid4(), location=L2, watermark=2, mass=0.3, parent=uuid4())
    with pytest.raises(HybridLedgerError, match="parent must be the superseded revision"):
        ledger.replace_promoted_revision(
            **_replace_kwargs(ledger, superseded, corrected, _promotion(corrected, watermark=3))
        )
    assert ledger.version == version_before
    _assert_unchanged(ledger, superseded)


def test_rejected_watermark_order_leaves_ledger_untouched():
    ledger, superseded = _promoted_ledger()
    version_before = ledger.version
    corrected = _delta(revision_id=uuid4(), location=L2, watermark=2, mass=0.3, parent=superseded)
    live = ledger.live_promoted_records_for_revision(superseded)
    with pytest.raises(HybridLedgerError, match="watermarks must be non-decreasing"):
        ledger.replace_promoted_revision(
            superseded_revision_id=superseded,
            reversal_record_ids=tuple(uuid4() for _ in live),
            reversal_watermark=1,
            reversal_reason="orrer",
            corrected_delta=corrected,
            promotion=_promotion(corrected, watermark=0),  # behind the delta
        )
    assert ledger.version == version_before
    _assert_unchanged(ledger, superseded)


def test_replaced_revision_is_recoverable_from_the_log():
    ledger, superseded = _promoted_ledger()
    corrected = _delta(revision_id=uuid4(), location=L2, watermark=2, mass=0.3, parent=superseded)
    live = ledger.live_promoted_records_for_revision(superseded)
    ledger.replace_promoted_revision(
        superseded_revision_id=superseded,
        reversal_record_ids=tuple(uuid4() for _ in live),
        reversal_watermark=1,
        reversal_reason="orrer",
        corrected_delta=corrected,
        promotion=_promotion(corrected, watermark=3),
    )
    restored = HybridStatisticLedger.restore_from_export(ledger.export_state())
    assert restored.projection(_key(L2)).alpha == pytest.approx(ledger.projection(_key(L2)).alpha)


def _loop(auth):
    return HybridEventToTaskCoordinatorLoop(
        owner_key=OWNER,
        object_instance_id=OBJ,
        authorization_scope_id=auth,
        model_version="m@1",
        code_version="git:test",
    )


def test_loop_apply_orrer_revision_publishes_one_atomic_version():
    auth = UUID(int=7)
    loop = _loop(auth)
    superseded = uuid4()
    loop.ingest_owner_placement(
        OwnerPlacementInput(
            event_hypothesis_id=UUID(int=99),
            revision_id=superseded,
            destination_location_id=L2,
            owner_mass=0.8,
            source_record_id=uuid4(),
        )
    )
    before_version = loop.current_snapshot().map_version if loop.current_snapshot().nodes else -1
    snapshot = loop.apply_orrer_revision(
        superseded_revision_id=superseded,
        corrected=OwnerPlacementInput(
            event_hypothesis_id=UUID(int=99),
            revision_id=uuid4(),
            destination_location_id=L2,
            owner_mass=0.2,
            source_record_id=uuid4(),
            parent_revision_id=superseded,
        ),
    )
    assert snapshot.map_version > before_version
    assert loop.node_id(L2) in {node.node_id for node in snapshot.nodes}
    # Belief was corrected atomically (0.8 -> 0.2), replay-consistent.
    assert loop.ledger.projection(loop._key(L2)).alpha == pytest.approx(0.2)
    loop.ledger.assert_cache_matches_replay(loop._key(L2))
