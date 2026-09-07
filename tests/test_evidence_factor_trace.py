from __future__ import annotations

from uuid import uuid4

import pytest

from cpswm.contracts import (
    EvidenceFactorConsumptionTrace,
    EvidenceFactorKind,
    EvidenceFactorOperator,
    EvidenceFactorSourceSemantics,
)


def _produce_likelihood(trace, *, update_id, cluster_id, record_id):
    return trace.produce_factor(
        update_id=update_id,
        evidence_cluster_id=cluster_id,
        evidence_record_ids=(record_id,),
        operator=EvidenceFactorOperator.OPCEU,
        factor_id=f"opceu:{cluster_id}",
        factor_kind=EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
        source_semantics=EvidenceFactorSourceSemantics.RAW_OBSERVATION_EVIDENCE,
        source_record_payloads={record_id: {"pixels_sha256": "a" * 64}},
        likelihood_model_id="opceu-likelihood@0.1",
        idempotency_key=f"produce:{cluster_id}",
    )


def test_likelihood_is_consumed_once_per_target_but_summary_can_be_read() -> None:
    trace = EvidenceFactorConsumptionTrace()
    update_id = uuid4()
    cluster_id = uuid4()
    record_id = uuid4()
    likelihood = _produce_likelihood(
        trace, update_id=update_id, cluster_id=cluster_id, record_id=record_id
    )
    consumed = trace.consume_factor(
        update_id=update_id,
        evidence_cluster_id=cluster_id,
        evidence_record_ids=(record_id,),
        operator=EvidenceFactorOperator.PARTICLE_REVISION,
        factor_id="particle-target-use",
        factor_kind=EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
        source_factor_ids=(likelihood.factor_id,),
        target_distribution_id="particle-posterior@step-1",
        likelihood_model_id="opceu-likelihood@0.1",
        consumed_as_likelihood=True,
        idempotency_key="consume:particle:step-1",
    )
    # An exact retry is idempotent, not a second consumption.
    assert (
        trace.consume_factor(
            update_id=update_id,
            evidence_cluster_id=cluster_id,
            evidence_record_ids=(record_id,),
            operator=EvidenceFactorOperator.PARTICLE_REVISION,
            factor_id="particle-target-use",
            factor_kind=EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
            source_factor_ids=(likelihood.factor_id,),
            target_distribution_id="particle-posterior@step-1",
            likelihood_model_id="opceu-likelihood@0.1",
            consumed_as_likelihood=True,
            idempotency_key="consume:particle:step-1",
        ).receipt_id
        == consumed.receipt_id
    )
    with pytest.raises(ValueError, match="already consumed"):
        trace.consume_factor(
            update_id=update_id,
            evidence_cluster_id=cluster_id,
            evidence_record_ids=(record_id,),
            operator=EvidenceFactorOperator.CF_BOCPD,
            factor_id="duplicate-use",
            factor_kind=EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
            source_factor_ids=(likelihood.factor_id,),
            target_distribution_id="particle-posterior@step-1",
            likelihood_model_id="opceu-likelihood@0.1",
            consumed_as_likelihood=True,
            idempotency_key="consume:duplicate",
        )


def test_posterior_summary_cannot_be_reintroduced_as_likelihood() -> None:
    trace = EvidenceFactorConsumptionTrace()
    update_id = uuid4()
    cluster_id = uuid4()
    record_id = uuid4()
    likelihood = _produce_likelihood(
        trace, update_id=update_id, cluster_id=cluster_id, record_id=record_id
    )
    summary = trace.derive_factor(
        update_id=update_id,
        evidence_cluster_id=cluster_id,
        evidence_record_ids=(record_id,),
        operator=EvidenceFactorOperator.CF_BOCPD,
        factor_id="cf-posterior-summary",
        factor_kind=EvidenceFactorKind.POSTERIOR_SUMMARY,
        source_factor_ids=(likelihood.factor_id,),
        target_distribution_id="cf-posterior@step-1",
        idempotency_key="derive:cf",
    )
    with pytest.raises(ValueError, match="posterior summary"):
        trace.consume_factor(
            update_id=update_id,
            evidence_cluster_id=cluster_id,
            evidence_record_ids=(record_id,),
            operator=EvidenceFactorOperator.CCRR,
            factor_id="illegal-ccrr-likelihood",
            factor_kind=EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
            source_factor_ids=(summary.factor_id,),
            target_distribution_id="ccrr@step-1",
            likelihood_model_id="opceu-likelihood@0.1",
            consumed_as_likelihood=True,
            idempotency_key="consume:illegal-summary",
        )


def test_cluster_likelihood_model_binding_and_hash_chain() -> None:
    trace = EvidenceFactorConsumptionTrace()
    update_id = uuid4()
    cluster_id = uuid4()
    _produce_likelihood(trace, update_id=update_id, cluster_id=cluster_id, record_id=uuid4())
    replacement_record_id = uuid4()
    with pytest.raises(ValueError, match="rebound"):
        trace.produce_factor(
            update_id=update_id,
            evidence_cluster_id=cluster_id,
            evidence_record_ids=(replacement_record_id,),
            operator=EvidenceFactorOperator.CIAV,
            factor_id=f"ciav:{cluster_id}",
            factor_kind=EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
            source_semantics=EvidenceFactorSourceSemantics.RAW_OBSERVATION_EVIDENCE,
            source_record_payloads={replacement_record_id: {"pixels_sha256": "b" * 64}},
            likelihood_model_id="different-model@9",
            idempotency_key="produce:ciav-mismatch",
        )
    assert trace.verify_chain()
    assert trace.audit_payload()["chain_valid"] is True


def test_caller_cannot_launder_a_posterior_snapshot_as_likelihood() -> None:
    trace = EvidenceFactorConsumptionTrace()
    record_id = uuid4()
    with pytest.raises(ValueError, match="incompatible with source semantics"):
        trace.produce_factor(
            update_id=uuid4(),
            evidence_cluster_id=uuid4(),
            evidence_record_ids=(record_id,),
            operator=EvidenceFactorOperator.CCRR,
            factor_id="forged-posterior-as-likelihood",
            factor_kind=EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
            source_semantics=EvidenceFactorSourceSemantics.POSTERIOR_SNAPSHOT,
            source_record_payloads={record_id: {"posterior": {"habit": 0.9}}},
            likelihood_model_id="caller-selected@9",
            idempotency_key="forged-posterior-as-likelihood",
        )
    assert trace.receipts == ()


def test_caller_cannot_derive_a_fresh_likelihood_from_posterior_summary() -> None:
    trace = EvidenceFactorConsumptionTrace()
    update_id, cluster_id, record_id = uuid4(), uuid4(), uuid4()
    likelihood = _produce_likelihood(
        trace,
        update_id=update_id,
        cluster_id=cluster_id,
        record_id=record_id,
    )
    summary = trace.derive_factor(
        update_id=update_id,
        evidence_cluster_id=cluster_id,
        evidence_record_ids=(record_id,),
        operator=EvidenceFactorOperator.CF_BOCPD,
        factor_id="posterior-before-laundering",
        factor_kind=EvidenceFactorKind.POSTERIOR_SUMMARY,
        source_factor_ids=(likelihood.factor_id,),
        target_distribution_id="cf-posterior",
        idempotency_key="posterior-before-laundering",
    )
    before = len(trace.receipts)
    with pytest.raises(ValueError, match="cannot mint a likelihood"):
        trace.derive_factor(
            update_id=update_id,
            evidence_cluster_id=cluster_id,
            evidence_record_ids=(record_id,),
            operator=EvidenceFactorOperator.CCRR,
            factor_id="laundered-likelihood",
            factor_kind=EvidenceFactorKind.OBSERVATION_LIKELIHOOD,
            source_factor_ids=(summary.factor_id,),
            target_distribution_id="ccrr",
            likelihood_model_id="caller-selected@9",
            idempotency_key="laundered-likelihood",
        )
    assert len(trace.receipts) == before


def test_record_identity_is_content_bound_across_primitive_factors() -> None:
    trace = EvidenceFactorConsumptionTrace()
    record_id = uuid4()
    trace.produce_factor(
        update_id=uuid4(),
        evidence_cluster_id=uuid4(),
        evidence_record_ids=(record_id,),
        operator=EvidenceFactorOperator.NEURAL_PROPOSER,
        factor_id="proposal-one",
        factor_kind=EvidenceFactorKind.PROPOSAL_DISTRIBUTION,
        source_semantics=EvidenceFactorSourceSemantics.NEURAL_PROPOSAL,
        source_record_payloads={record_id: {"q": [0.2, 0.8]}},
        idempotency_key="proposal-one",
    )
    before = len(trace.receipts)
    with pytest.raises(ValueError, match="rebound to different payload"):
        trace.produce_factor(
            update_id=uuid4(),
            evidence_cluster_id=uuid4(),
            evidence_record_ids=(record_id,),
            operator=EvidenceFactorOperator.NEURAL_PROPOSER,
            factor_id="proposal-two",
            factor_kind=EvidenceFactorKind.PROPOSAL_DISTRIBUTION,
            source_semantics=EvidenceFactorSourceSemantics.NEURAL_PROPOSAL,
            source_record_payloads={record_id: {"q": [0.8, 0.2]}},
            idempotency_key="proposal-two",
        )
    assert len(trace.receipts) == before


def test_commit_is_materialized_and_duplicate_failure_is_atomic() -> None:
    trace = EvidenceFactorConsumptionTrace()
    update_id, cluster_id, record_id = uuid4(), uuid4(), uuid4()
    prior = trace.produce_factor(
        update_id=update_id,
        evidence_cluster_id=cluster_id,
        evidence_record_ids=(record_id,),
        operator=EvidenceFactorOperator.RGRC,
        factor_id="rgrc-structural-source",
        factor_kind=EvidenceFactorKind.STRUCTURAL_CONSTRAINT,
        source_semantics=EvidenceFactorSourceSemantics.STRUCTURED_MODEL,
        source_record_payloads={record_id: {"gate": "accepted"}},
        idempotency_key="rgrc-structural-source",
    )
    commit = trace.commit_factor(
        update_id=update_id,
        evidence_cluster_id=cluster_id,
        evidence_record_ids=(record_id,),
        operator=EvidenceFactorOperator.RGRC,
        factor_id="rgrc-commit",
        factor_kind=EvidenceFactorKind.COMMIT_DELTA,
        source_factor_ids=(prior.factor_id,),
        target_distribution_id="regime-statistics",
        idempotency_key="rgrc-commit",
    )
    derived = trace.derive_factor(
        update_id=update_id,
        evidence_cluster_id=cluster_id,
        evidence_record_ids=(record_id,),
        operator=EvidenceFactorOperator.ACTION_READOUT,
        factor_id="readout-from-commit",
        factor_kind=EvidenceFactorKind.ACTION_OUTCOME,
        source_factor_ids=(commit.factor_id,),
        target_distribution_id="action",
        idempotency_key="readout-from-commit",
    )
    assert derived.source_factor_ids == (commit.factor_id,)
    before = len(trace.receipts)
    with pytest.raises(ValueError, match="already materialized"):
        trace.commit_factor(
            update_id=update_id,
            evidence_cluster_id=cluster_id,
            evidence_record_ids=(record_id,),
            operator=EvidenceFactorOperator.RGRC,
            factor_id="rgrc-commit",
            factor_kind=EvidenceFactorKind.COMMIT_DELTA,
            source_factor_ids=(prior.factor_id,),
            target_distribution_id="regime-statistics",
            idempotency_key="duplicate-rgrc-commit",
        )
    assert len(trace.receipts) == before
    assert trace.verify_chain()
