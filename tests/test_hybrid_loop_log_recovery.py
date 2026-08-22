"""Crash recovery: the Hybrid loop keeps no authoritative state of its own.

Review fix #3.  ``_watermark`` / ``_deltas_by_revision`` / ``_revision_dest`` used
to live in the loop, so a loop rebuilt after a restart lost the ability to write
(watermark reset behind the ledger head), retract, or republish.  The loop now
derives everything from the authoritative ledger, and the ledger serializes to /
restores from its append-only log with full re-validation.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from cpswm.system.continual.hybrid_event_to_task_loop import (
    HybridEventToTaskCoordinatorLoop,
    OwnerPlacementInput,
)
from cpswm.system.continual.hybrid_statistics import HybridLedgerError, HybridStatisticLedger

OWNER = "owner"
OBJ = UUID(int=5)
L1 = UUID(int=1)
L2 = UUID(int=2)
L3 = UUID(int=3)


def _loop(*, auth: UUID, ledger: HybridStatisticLedger | None = None):
    return HybridEventToTaskCoordinatorLoop(
        owner_key=OWNER,
        object_instance_id=OBJ,
        authorization_scope_id=auth,
        model_version="hier-dirichlet@0.1",
        code_version="git:test",
        ledger=ledger,
    )


def _placement(location: UUID, *, mass: float = 0.8) -> OwnerPlacementInput:
    return OwnerPlacementInput(
        event_hypothesis_id=uuid4(),
        revision_id=uuid4(),
        destination_location_id=location,
        owner_mass=mass,
        source_record_id=uuid4(),
    )


def test_restored_ledger_projections_match_the_original():
    auth = uuid4()
    loop = _loop(auth=auth)
    p1 = _placement(L1)
    p2 = _placement(L2)
    loop.ingest_owner_placement(p1)
    loop.ingest_owner_placement(p2)
    loop.retract_revision(p1.revision_id)  # exercise reversal records in the log

    restored = HybridStatisticLedger.restore_from_log(feature_dim=1, log=loop.ledger.export_log())
    assert restored.version == loop.ledger.version
    assert restored.head_watermark == loop.ledger.head_watermark
    for location in (L1, L2):
        key = loop._key(location)
        assert restored.projection(key).alpha == pytest.approx(loop.ledger.projection(key).alpha)
        # The recovered ledger is itself replay-consistent.
        restored.assert_cache_matches_replay(key)


def test_rebuilt_loop_can_keep_writing_without_watermark_reset():
    # The core regression: a fresh loop on a recovered ledger must not write
    # behind the log head.
    auth = uuid4()
    original = _loop(auth=auth)
    original.ingest_owner_placement(_placement(L1))
    original.ingest_owner_placement(_placement(L2))
    head = original.ledger.head_watermark
    assert head > 0

    restored = HybridStatisticLedger.restore_from_log(
        feature_dim=1, log=original.ledger.export_log()
    )
    reborn = _loop(auth=auth, ledger=restored)

    # A brand-new loop (its old in-memory counter would have been 0) still writes.
    reborn.ingest_owner_placement(_placement(L3))
    assert restored.head_watermark > head
    assert restored.projection(reborn._key(L3)).alpha > 0.0


def test_rebuilt_loop_retracts_and_republishes_a_pre_crash_revision():
    auth = uuid4()
    original = _loop(auth=auth)
    p1 = _placement(L1)
    original.ingest_owner_placement(p1)
    original.ingest_owner_placement(_placement(L2))

    restored = HybridStatisticLedger.restore_from_log(
        feature_dim=1, log=original.ledger.export_log()
    )
    reborn = _loop(auth=auth, ledger=restored)

    # Retract works though the loop never saw p1 ingested (state came from the log).
    assert reborn.retract_revision(p1.revision_id) == 1
    assert restored.projection(reborn._key(L1)).alpha == pytest.approx(0.0)

    # An ORRER correction can still recover the superseded location for republish.
    corrected = OwnerPlacementInput(
        event_hypothesis_id=uuid4(),
        revision_id=uuid4(),
        destination_location_id=L3,
        owner_mass=0.9,
        source_record_id=uuid4(),
    )
    snapshot = reborn.apply_orrer_revision(
        superseded_revision_id=p1.revision_id, corrected=corrected
    )
    node_ids = {node.node_id for node in snapshot.nodes}
    # Both the superseded (L1) and corrected (L3) locations were republished.
    assert reborn.node_id(L1) in node_ids
    assert reborn.node_id(L3) in node_ids


def test_recover_map_rebuilds_published_nodes_from_the_log():
    auth = uuid4()
    original = _loop(auth=auth)
    original.ingest_owner_placement(_placement(L1))
    original.ingest_owner_placement(_placement(L2))

    restored = HybridStatisticLedger.restore_from_log(
        feature_dim=1, log=original.ledger.export_log()
    )
    reborn = _loop(auth=auth, ledger=restored)
    assert reborn.current_snapshot().nodes == ()  # fresh map before recovery

    snapshot = reborn.recover_map()
    node_ids = {node.node_id for node in snapshot.nodes}
    assert node_ids == {reborn.node_id(L1), reborn.node_id(L2)}


def test_restore_rejects_a_truncated_log():
    # Dropping a delta that a later promotion points at must fail restore, not
    # silently rebuild a corrupt state.
    auth = uuid4()
    loop = _loop(auth=auth)
    loop.ingest_owner_placement(_placement(L1))
    log = loop.ledger.export_log()
    # Remove the first record (the delta); its promotion now dangles.
    truncated = log[1:]
    with pytest.raises(HybridLedgerError):
        HybridStatisticLedger.restore_from_log(feature_dim=1, log=truncated)
