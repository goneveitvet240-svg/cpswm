"""Native RGRC bundle plumbing and numeric replay, not a full particle claim."""

from dataclasses import replace
from uuid import uuid4

import numpy as np
import pytest
import test_hybrid_atomic_replace as base
import test_structure_two_formal_revision_lineage as old
from test_structure_two_w3_operator_acceptance import ActualCalls

from cpswm.system.continual.hybrid_statistics import (
    HybridLedgerError,
    HybridStatisticDelta,
    HybridStatisticLedger,
)
from cpswm.system.reproducibility import content_sha256


def bundle():
    revision, cluster, source = uuid4(), uuid4(), uuid4()
    deltas = tuple(
        HybridStatisticDelta.from_weighted_sample(
            x=[1.0, float(index + 1)],
            y=float(index + 2),
            weight=0.25,
            delta_alpha=0.25,
            information_weight=0.5,
            record_id=uuid4(),
            event_hypothesis_id=base.EVENT,
            revision_id=revision,
            evidence_cluster_id=cluster,
            semantic_dedup_id=f"{revision}:{index}",
            source_record_ids=(source,),
            authorization_scope_id=base.SCOPE,
            key=base._key(location),
            input_watermark=index,
            model_version="explicit-test-sample",
            code_version="r5-test",
        )
        for index, location in enumerate([base.L1, base.L2])
    )
    promotions = tuple(base._promotion(d, watermark=index + 2) for index, d in enumerate(deltas))
    return deltas, promotions


def test_multikey_cluster_contains_and_reverses_all_three_analytic_blocks():
    ledger = HybridStatisticLedger(feature_dim=2)
    deltas, promotions = bundle()
    projections = ledger.apply_statistic_bundle(deltas=deltas, promotions=promotions)
    assert len(projections) == 2
    for index, (delta, actual) in enumerate(zip(deltas, projections, strict=True)):
        x = np.array([1.0, float(index + 1)])
        np.testing.assert_allclose(actual.a, ledger.ridge * np.eye(2) + 0.25 * np.outer(x, x))
        np.testing.assert_allclose(actual.b, 0.25 * x * (index + 2))
        assert actual.alpha == 0.25
        np.testing.assert_allclose(
            actual.information, ledger.information_ridge * np.eye(2) + 0.5 * np.outer(x, x)
        )
        np.testing.assert_allclose(actual.information_vector, 0.5 * x * (index + 2))
        ledger.assert_cache_matches_replay(delta.key)
    exported = ledger.export_state()
    replayed = HybridStatisticLedger.restore_from_export(exported)
    assert content_sha256(replayed.export_state()) == content_sha256(exported)
    ledger.retract_revision(
        revision_id=deltas[0].revision_id,
        reversal_record_ids=(uuid4(), uuid4()),
        input_watermark=4,
        authorization_scope_id=base.SCOPE,
        reason="whole cluster counterevidence",
    )
    for delta in deltas:
        actual = ledger.projection(delta.key)
        assert actual.alpha == 0.0
        np.testing.assert_allclose(actual.a, ledger.ridge * np.eye(2))
        np.testing.assert_allclose(actual.b, [0.0, 0.0])
        np.testing.assert_allclose(actual.information, ledger.information_ridge * np.eye(2))
        np.testing.assert_allclose(actual.information_vector, [0.0, 0.0])


@pytest.mark.parametrize("method", ["append_delta", "_commit_promotion", "projection"])
@pytest.mark.parametrize("exception", [RuntimeError, KeyboardInterrupt])
def test_bundle_interruption_restores_same_ledger_and_retries(method, exception, monkeypatch):
    ledger = HybridStatisticLedger(feature_dim=2)
    identity = id(ledger)
    deltas, promotions = bundle()
    before = content_sha256(ledger.export_state())
    original = getattr(type(ledger), method)
    count = 0

    def interrupt(self, *args, **kwargs):
        nonlocal count
        result = original(self, *args, **kwargs)
        count += 1
        if count == 2:
            raise exception("bundle interrupted")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(type(ledger), method, interrupt)
        with pytest.raises(exception, match="bundle interrupted"):
            ledger.apply_statistic_bundle(deltas=deltas, promotions=promotions)
    assert id(ledger) == identity and content_sha256(ledger.export_state()) == before
    assert all(ledger.projection(d.key).alpha == 0 for d in deltas)
    ledger.apply_statistic_bundle(deltas=deltas, promotions=promotions)
    assert all(ledger.projection(d.key).alpha == 0.25 for d in deltas)
    committed = content_sha256(ledger.export_state())
    with pytest.raises(HybridLedgerError):
        ledger.apply_statistic_bundle(deltas=deltas, promotions=promotions)
    assert content_sha256(ledger.export_state()) == committed


@pytest.mark.parametrize(
    "fault", ["missing_promotion", "foreign_scope", "mixed_cluster", "duplicate_key"]
)
def test_bundle_refuses_incomplete_or_foreign_authority(fault):
    ledger = HybridStatisticLedger(feature_dim=2)
    deltas, promotions = bundle()
    before = content_sha256(ledger.export_state())
    if fault == "missing_promotion":
        promotions = promotions[:1]
    elif fault == "foreign_scope":
        promotions = (promotions[0], replace(promotions[1], authorization_scope_id=uuid4()))
    elif fault == "mixed_cluster":
        deltas = (deltas[0], replace(deltas[1], evidence_cluster_id=uuid4(), content_hash=""))
    else:
        deltas = (deltas[0], replace(deltas[1], key=deltas[0].key, content_hash=""))
    with pytest.raises(HybridLedgerError):
        ledger.apply_statistic_bundle(deltas=deltas, promotions=promotions)
    assert content_sha256(ledger.export_state()) == before


def test_public_numeric_downdate_triggers_actual_full_replay():
    ledger = HybridStatisticLedger(feature_dim=1)
    big = base._delta(revision_id=uuid4(), location=base.L1, watermark=0, mass=1e16)
    small = base._delta(revision_id=uuid4(), location=base.L1, watermark=2, mass=1.0)
    for delta, watermark in [(big, 1), (small, 3)]:
        ledger.apply_statistic_bundle(
            deltas=(delta,), promotions=(base._promotion(delta, watermark=watermark),)
        )
    ledger.retract_revision(
        revision_id=big.revision_id,
        reversal_record_ids=(uuid4(),),
        input_watermark=4,
        authorization_scope_id=base.SCOPE,
        reason="remove large public sample",
    )
    assert (
        ledger.projection(small.key).alpha == 0.0
    )  # real floating cancellation, no private mutation
    with ActualCalls(ledger.restore_from_export, ledger.rebuild_projection) as calls:
        assert ledger.ensure_replay_equivalence((small.key,))
    assert any(row[0:2] == ("restore_from_export", "call") for row in calls.rows)
    assert ledger.projection(small.key).alpha == 1.0
    ledger.assert_cache_matches_replay(small.key)
    assert not ledger.ensure_replay_equivalence((small.key,))


def test_actual_production_ingest_consumes_bundle_and_verified_projection():
    probe = old._legacy_history(1)
    core = probe.system.core
    ledger = core._hybrid_loop.ledger
    with ActualCalls(ledger.apply_statistic_bundle, ledger.ensure_replay_equivalence) as calls:
        result = core.process_transition(probe.transition_for(probe.observed_days()[1]))
    bundles = [row for row in calls.rows if row[0:2] == ("apply_statistic_bundle", "call")]
    assert bundles and all(row[2]["self"] is ledger for row in bundles)
    assert any(
        row[0:2] == ("ensure_replay_equivalence", "return") and row[3] is False
        for row in calls.rows
    )
    assert result.event_revision_id in core._committed_events
    assert sum(core.action_location_distribution(core.current_snapshot).values()) == pytest.approx(
        1.0
    )
