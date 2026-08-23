"""Durable, tamper-evident, config-bound ledger recovery (review #3 P0 reopened).

export_state() emits a hash-chained, buffer-free, config-bound artifact; restore
recomputes every hash and rebuilds records from canonical bytes, so truncation,
deletion, reorder, config drift, value tampering, and wrong dimensions are all
rejected instead of silently rebuilding a corrupt state.
"""

from __future__ import annotations

import dataclasses
from uuid import UUID, uuid4

import pytest

from cpswm.system.continual.hybrid_statistics import (
    ConsolidationRiskCertificate,
    HybridLedgerError,
    HybridPromotion,
    HybridStatisticDelta,
    HybridStatisticLedger,
    LedgerConfig,
    LedgerExport,
    StatisticKey,
)

OWNER = "owner"
OBJ = UUID(int=5)


def _key(location: UUID) -> StatisticKey:
    return StatisticKey(
        actor_key=OWNER,
        object_instance_id=OBJ,
        regime_id="owner-habit",
        parameter_block="owner_habit_location",
        location_id=location,
    )


def _delta(*, revision_id, location, watermark, mass=0.8) -> HybridStatisticDelta:
    return HybridStatisticDelta.from_weighted_sample(
        x=[1.0],
        y=mass,
        weight=mass,
        delta_alpha=mass,
        record_id=uuid4(),
        event_hypothesis_id=UUID(int=99),
        revision_id=revision_id,
        evidence_cluster_id=uuid4(),
        semantic_dedup_id=f"{revision_id}:{location}:{watermark}",
        source_record_ids=(uuid4(),),
        authorization_scope_id=UUID(int=7),
        key=_key(location),
        input_watermark=watermark,
        model_version="m@1",
        code_version="git:test",
    )


def _promotion(delta, *, watermark):
    return HybridPromotion(
        record_id=uuid4(),
        promotes_record_id=delta.record_id,
        input_watermark=watermark,
        authorization_scope_id=delta.authorization_scope_id,
        reason="promote",
        risk_certificate=ConsolidationRiskCertificate(
            expected_task_loss=0.0,
            uncertainty_penalty=0.0,
            maximum_allowed_risk=1.0,
            exact_verifier_id="test@0.1",
            counterfactual_id=uuid4(),
            subject_delta_record_id=delta.record_id,
            belief_snapshot_id=uuid4(),
            map_version=0,
        ),
    )


def _built_ledger(*, alpha_prior=0.0) -> HybridStatisticLedger:
    ledger = HybridStatisticLedger(feature_dim=1, alpha_prior=alpha_prior)
    d1 = _delta(revision_id=uuid4(), location=UUID(int=1), watermark=0, mass=0.8)
    d2 = _delta(revision_id=uuid4(), location=UUID(int=2), watermark=1, mass=0.4)
    ledger.append_delta(d1)
    ledger.append_delta(d2)
    ledger.promote(_promotion(d1, watermark=2))
    ledger.promote(_promotion(d2, watermark=3))
    return ledger


def _replace_entry_record(export, index, mutate):
    entries = list(export.entries)
    record = dict(entries[index].record)
    mutate(record)
    entries[index] = dataclasses.replace(entries[index], record=record)
    return dataclasses.replace(export, entries=tuple(entries))


def test_clean_export_restores_and_round_trips():
    ledger = _built_ledger()
    export = ledger.export_state()
    restored = HybridStatisticLedger.restore_from_export(export)
    for loc in (UUID(int=1), UUID(int=2)):
        assert restored.projection(_key(loc)).alpha == pytest.approx(
            ledger.projection(_key(loc)).alpha
        )
    # Serializable to and from JSON with no loss.
    assert LedgerExport.from_json(export.to_json()).to_json() == export.to_json()


def test_tail_truncation_is_rejected():
    export = _built_ledger().export_state()
    # Attacker drops the last entry and rewrites the count to match; the head hash
    # in the manifest still describes the full log.
    truncated = dataclasses.replace(
        export,
        entries=export.entries[:-1],
        manifest=dataclasses.replace(export.manifest, record_count=len(export.entries) - 1),
    )
    with pytest.raises(HybridLedgerError, match="head hash does not match"):
        HybridStatisticLedger.restore_from_export(truncated)


def test_record_count_mismatch_is_rejected():
    export = _built_ledger().export_state()
    tampered = dataclasses.replace(export, entries=export.entries[:-1])
    with pytest.raises(HybridLedgerError, match="record count"):
        HybridStatisticLedger.restore_from_export(tampered)


def test_middle_deletion_breaks_the_chain():
    export = _built_ledger().export_state()
    entries = export.entries[:1] + export.entries[2:]
    tampered = dataclasses.replace(
        export,
        entries=entries,
        manifest=dataclasses.replace(export.manifest, record_count=len(entries)),
    )
    with pytest.raises(HybridLedgerError, match=r"out of sequence|chain is broken"):
        HybridStatisticLedger.restore_from_export(tampered)


def test_reorder_breaks_the_chain():
    export = _built_ledger().export_state()
    entries = list(export.entries)
    entries[0], entries[1] = entries[1], entries[0]
    tampered = dataclasses.replace(export, entries=tuple(entries))
    with pytest.raises(HybridLedgerError, match=r"out of sequence|chain is broken"):
        HybridStatisticLedger.restore_from_export(tampered)


def test_config_drift_is_rejected():
    export = _built_ledger(alpha_prior=0.0).export_state()
    # Same log, different priors supplied at restore time (manifest not updated).
    drifted = dataclasses.replace(
        export, config=dataclasses.replace(export.config, alpha_prior=10.0)
    )
    with pytest.raises(HybridLedgerError, match="configuration does not match"):
        HybridStatisticLedger.restore_from_export(drifted)


def test_value_tampering_is_rejected():
    export = _built_ledger().export_state()
    # Flip a delta's alpha in the serialized record without fixing its hash.
    tampered = _replace_entry_record(
        export, 0, lambda record: record.__setitem__("delta_alpha", repr(99.0))
    )
    with pytest.raises(HybridLedgerError, match="record hash does not match"):
        HybridStatisticLedger.restore_from_export(tampered)


def test_wrong_feature_dimension_is_rejected_on_replay():
    export = _built_ledger().export_state()
    # A fully hash-consistent export whose declared dimension disagrees with the
    # dim-1 delta arrays: caught by replay validation, not just the manifest.
    bad_config = LedgerConfig(
        feature_dim=2,
        ridge=export.config.ridge,
        information_ridge=export.config.information_ridge,
        alpha_prior=export.config.alpha_prior,
        max_condition_number=export.config.max_condition_number,
    )
    consistent = dataclasses.replace(
        export,
        config=bad_config,
        manifest=dataclasses.replace(export.manifest, config_hash=bad_config.config_hash),
    )
    with pytest.raises(HybridLedgerError, match="feature dimension"):
        HybridStatisticLedger.restore_from_export(consistent)
