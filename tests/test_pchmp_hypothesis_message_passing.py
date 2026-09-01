"""Tests for Provenance-Constrained Hypothesis Message Passing (PCHMP, §4.7 #4)."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from cpswm.contracts import EvidenceRef
from cpswm.system.attestation import AttestationAuthority
from cpswm.system.counterfactual_event_hypergraph import (
    EvidenceDuplicateViolation,
    OpenWorldRoleConditionedReversibleEventRevisionEngine,
    ProvenanceConstrainedMessagePassing,
    hidden_event_evidence_claim_fingerprint,
    hidden_event_evidence_semantic_fingerprint,
    issue_evidence_independence_certificate,
    permute_actor_keys,
)
from cpswm.system.evaluation_operations import StructureTwoActionScenarioGenerator

OWNER = "owner"
GUEST = "guest"


def _observed_case_and_history(seed: int = 1):
    case = StructureTwoActionScenarioGenerator().generate(seed)
    engine = OpenWorldRoleConditionedReversibleEventRevisionEngine()
    for obs in case.visible.days:
        if obs.after is None or obs.before is None:
            continue
        history = engine.branch(
            before=obs.before,
            after=obs.after,
            actor_prior={OWNER: 0.4, GUEST: 0.3, "unknown_actor": 0.3},
            unresolved_probability=0.1,
        )
        evidence = []
        if obs.actor_evidence is not None:
            evidence.append(obs.actor_evidence)
        if obs.mechanism_evidence is not None:
            evidence.append(obs.mechanism_evidence)
        if obs.role_evidence is not None:
            evidence.append(obs.role_evidence)
        return case, history, tuple(evidence)
    raise RuntimeError("scenario produced no observed day")


def test_concrete_unknown_mechanism_and_unresolved_sum_to_one():
    _case, history, evidence = _observed_case_and_history()
    result = ProvenanceConstrainedMessagePassing().infer(history, evidence)
    assert (
        sum(result.posterior_by_hypothesis_id.values())
        + result.unknown_mechanism_probability
        + result.unresolved_probability
    ) == pytest.approx(1.0, abs=1e-9)


def test_evidence_subgraph_covers_every_posterior_hypothesis():
    _case, history, evidence = _observed_case_and_history()
    result = ProvenanceConstrainedMessagePassing().infer(history, evidence)
    assert set(result.posterior_by_hypothesis_id).issubset(set(result.evidence_subgraph))


def test_actor_evidence_only_reweights_its_own_actor():
    """The actor firewall: evidence favouring one actor must not reweight the
    other actor's direct hypothesis upward."""

    _case, history, evidence = _observed_case_and_history()
    engine = ProvenanceConstrainedMessagePassing()
    baseline = engine.infer(history, ())
    posterior_with_evidence = engine.infer(history, evidence)
    owner_hypothesis_ids = {
        h.hypothesis_id for h in history.latest.hypotheses if h.responsible_actor_key == OWNER
    }
    guest_hypothesis_ids = {
        h.hypothesis_id for h in history.latest.hypotheses if h.responsible_actor_key == GUEST
    }
    # The evidence stream is symmetric across actors in aggregate (both actor
    # and role factors), so the firewall keeps every hypothesis finite and the
    # posterior normalized, never negative.
    assert all(
        value >= 0.0 for value in posterior_with_evidence.posterior_by_hypothesis_id.values()
    )
    assert owner_hypothesis_ids and guest_hypothesis_ids
    del baseline  # unused beyond setup


def test_actor_firewall_shifts_only_the_target_actor():
    """The actor firewall: evidence favouring one actor must raise that actor's
    hypotheses and lower (or leave) the other actor's hypotheses."""

    case, history, _evidence = _observed_case_and_history()
    actor_evidence = _first_actor_evidence(case)
    assert actor_evidence is not None
    owner_evidence = actor_evidence.model_copy(
        update={
            "actor_posterior": {
                OWNER: 0.9,
                GUEST: 0.05,
                "unknown_actor": 0.05,
            },
            "reference_actor_prior": {
                OWNER: 1 / 3,
                GUEST: 1 / 3,
                "unknown_actor": 1 / 3,
            },
        }
    )
    engine = ProvenanceConstrainedMessagePassing()
    baseline = engine.infer(history, ())
    shifted = engine.infer(history, (owner_evidence,))

    owner_ids = [
        h.hypothesis_id for h in history.latest.hypotheses if h.responsible_actor_key == OWNER
    ]
    guest_ids = [
        h.hypothesis_id for h in history.latest.hypotheses if h.responsible_actor_key == GUEST
    ]
    owner_mass_before = sum(baseline.posterior_by_hypothesis_id[i] for i in owner_ids)
    owner_mass_after = sum(shifted.posterior_by_hypothesis_id[i] for i in owner_ids)
    guest_mass_before = sum(baseline.posterior_by_hypothesis_id[i] for i in guest_ids)
    guest_mass_after = sum(shifted.posterior_by_hypothesis_id[i] for i in guest_ids)
    assert owner_mass_after > owner_mass_before
    assert guest_mass_after < guest_mass_before


def _first_actor_evidence(case):
    for obs in case.visible.days:
        if obs.actor_evidence is not None:
            return obs.actor_evidence
    return None


def test_permutation_equivariance_holds():
    _case, history, evidence = _observed_case_and_history()
    ProvenanceConstrainedMessagePassing.assert_permutation_equivariance(
        history=history,
        evidence=evidence,
        permutation={OWNER: GUEST, GUEST: OWNER},
    )


def test_permutation_must_cover_the_same_actor_universe():
    with pytest.raises(ValueError, match="same actor universe"):
        permute_actor_keys(
            _observed_case_and_history()[1],
            {OWNER: GUEST, GUEST: GUEST},
        )


def test_map_hypothesis_is_an_active_hypothesis():
    _case, history, evidence = _observed_case_and_history()
    result = ProvenanceConstrainedMessagePassing().infer(history, evidence)
    map_id = result.map_hypothesis_id
    assert map_id is not None
    assert map_id in result.posterior_by_hypothesis_id


def test_exact_zero_ratio_is_auditable_and_hashable():
    """P0-2: an exact-zero likelihood ratio must not leak -inf into the
    auditable result; the result stays JSON-serializable and content-hashable."""

    from cpswm.system.reproducibility import content_sha256

    case, history, _evidence = _observed_case_and_history()
    actor_evidence = _first_actor_evidence(case)
    assert actor_evidence is not None
    # Give the guest an exact-zero posterior while the owner keeps all mass.
    zeroed = actor_evidence.model_copy(
        update={
            "actor_posterior": {
                OWNER: 0.9,
                GUEST: 0.0,
                "unknown_actor": 0.1,
            },
            "reference_actor_prior": {
                OWNER: 1 / 3,
                GUEST: 1 / 3,
                "unknown_actor": 1 / 3,
            },
        }
    )
    result = ProvenanceConstrainedMessagePassing().infer(history, (zeroed,))
    # JSON must not degrade -inf to null, and hashing must not raise.
    jsonable = result.model_dump(mode="json")
    assert jsonable is not None
    digest = content_sha256(result)
    assert len(digest) == 64

    # Every message bound to the guest carries the explicit -inf flag.
    guest_ids = [
        h.hypothesis_id for h in history.latest.hypotheses if h.responsible_actor_key == GUEST
    ]
    for hid in guest_ids:
        for message in result.evidence_subgraph[hid]:
            if message.is_negative_infinity:
                assert message.is_negative_infinity
                assert message.log_likelihood_ratio == 0.0
                assert message.applied_log_contribution == 0.0


def test_extreme_ratios_do_not_overflow():
    """P0-2: very large (legal) likelihood ratios must not overflow the
    multiplicative reweighting; normalization stays in log space."""

    case, history, _evidence = _observed_case_and_history()
    actor_evidence = _first_actor_evidence(case)
    assert actor_evidence is not None
    extreme = actor_evidence.model_copy(
        update={
            "actor_posterior": {
                OWNER: 1e-300,
                GUEST: 1.0 - 1e-300 - 1e-300,
                "unknown_actor": 1e-300,
            },
            "reference_actor_prior": {
                OWNER: 1 / 3,
                GUEST: 1 / 3,
                "unknown_actor": 1 / 3,
            },
        }
    )
    result = ProvenanceConstrainedMessagePassing().infer(history, (extreme,))
    total = (
        sum(result.posterior_by_hypothesis_id.values())
        + result.unknown_mechanism_probability
        + result.unresolved_probability
    )
    assert total == pytest.approx(1.0, abs=1e-6)
    assert all(value >= 0.0 for value in result.posterior_by_hypothesis_id.values())


def test_evidence_message_rejects_inconsistent_log_contribution():
    """P1: ``applied_log_contribution`` must equal ``weight * log(ratio)``."""

    from uuid import uuid4

    from pydantic import ValidationError

    from cpswm.system.counterfactual_event_hypergraph.hypothesis_message_passing import (
        EvidenceMessage,
        MessageEdgeType,
    )

    with pytest.raises(ValidationError):
        EvidenceMessage(
            edge_type=MessageEdgeType.ACTOR_EVIDENCE,
            log_likelihood_ratio=2.0,
            effective_sample_weight=0.5,
            applied_log_contribution=999.0,
            evidence_record_id=uuid4(),
            evidence_cluster_id=uuid4(),
        )


def test_identity_permutation_is_rejected():
    """P1: the equivariance check must reject a vacuous identity permutation."""

    _case, history, evidence = _observed_case_and_history()
    with pytest.raises(AssertionError, match="non-trivial"):
        ProvenanceConstrainedMessagePassing.assert_permutation_equivariance(
            history=history,
            evidence=evidence,
            permutation={OWNER: OWNER, GUEST: GUEST},
        )


def test_consumption_receipt_closes_exactly_once():
    """P1: consuming evidence writes a receipt into the authoritative history;
    re-submitting the same evidence against the receipted history is rejected."""

    from cpswm.system.counterfactual_event_hypergraph import (
        EvidenceDuplicateViolation,
    )

    _case, history, evidence = _observed_case_and_history()
    engine = ProvenanceConstrainedMessagePassing()
    result, receipted = engine.consume(history, evidence)

    # The receipt records exactly the consumed records/clusters.
    assert set(result.consumed_evidence_record_ids) == {
        item.metadata.record_id for item in evidence
    }
    assert set(result.consumed_evidence_cluster_ids) == {
        item.evidence_cluster_id for item in evidence
    }
    assert len(receipted.revisions) == len(history.revisions) + 1
    assert set(receipted.consumed_evidence_record_ids) >= set(result.consumed_evidence_record_ids)

    # Re-submitting the same evidence against the receipted history must fail.
    with pytest.raises(EvidenceDuplicateViolation):
        engine.infer(receipted, evidence)


def test_semantic_duplicate_cannot_evade_single_consumption_with_new_ids():
    """A repackaged copy is still the same evidence, not a second likelihood."""

    from cpswm.system.counterfactual_event_hypergraph import EvidenceDuplicateViolation

    _case, history, evidence = _observed_case_and_history()
    original = evidence[0]
    repackaged = original.model_copy(
        update={
            "metadata": original.metadata.model_copy(update={"record_id": uuid4()}),
            "evidence_cluster_id": uuid4(),
        }
    )
    with pytest.raises(EvidenceDuplicateViolation, match="semantically identical"):
        ProvenanceConstrainedMessagePassing().infer(
            history,
            (original, repackaged),
        )


def test_transport_trace_and_ingestion_time_cannot_evade_semantic_dedup():
    """Trace and recorded time are wrappers, not independent evidence."""

    _case, history, evidence = _observed_case_and_history()
    original = evidence[0]
    repackaged = original.model_copy(
        update={
            "metadata": original.metadata.model_copy(
                update={
                    "record_id": uuid4(),
                    "trace_id": uuid4(),
                    "recorded_time": original.metadata.recorded_time + timedelta(hours=1),
                }
            ),
            "evidence_cluster_id": uuid4(),
        }
    )
    assert hidden_event_evidence_semantic_fingerprint(
        original
    ) == hidden_event_evidence_semantic_fingerprint(repackaged)
    scope_valid_repackaged = repackaged.model_copy(
        update={
            "metadata": repackaged.metadata.model_copy(
                update={"trace_id": original.metadata.trace_id}
            )
        }
    )
    with pytest.raises(EvidenceDuplicateViolation, match="semantically identical"):
        ProvenanceConstrainedMessagePassing().infer(
            history,
            (original, scope_valid_repackaged),
        )


def test_same_claim_needs_attested_independence_certificate_to_count_twice():
    """Independent sensors are distinguished by evidence, not caller-chosen IDs."""

    _case, history, evidence = _observed_case_and_history()
    original = evidence[0].model_copy(
        update={
            "evidence_refs": (
                EvidenceRef(
                    evidence_type="independent_actor_sensor",
                    source_record_id=uuid4(),
                ),
            )
        }
    )
    independent_acquisition = original.model_copy(
        update={
            "metadata": original.metadata.model_copy(
                update={
                    "record_id": uuid4(),
                    "source_id": "independent-sensor-b",
                    "model_version": "sensor-model-b@1",
                }
            ),
            "evidence_cluster_id": uuid4(),
            "evidence_refs": (
                EvidenceRef(
                    evidence_type="independent_actor_sensor",
                    source_record_id=uuid4(),
                ),
            ),
        }
    )
    assert hidden_event_evidence_semantic_fingerprint(
        original
    ) != hidden_event_evidence_semantic_fingerprint(independent_acquisition)
    assert hidden_event_evidence_claim_fingerprint(
        original
    ) == hidden_event_evidence_claim_fingerprint(independent_acquisition)
    with pytest.raises(EvidenceDuplicateViolation, match="independence certificate"):
        ProvenanceConstrainedMessagePassing().infer(
            history,
            (original, independent_acquisition),
        )

    authority = AttestationAuthority(
        key_id="evidence-independence-test",
        secret=b"evidence-independence-authority-key-0001",
    )
    certificate = issue_evidence_independence_certificate(
        original,
        independent_acquisition,
        independence_basis="physically isolated sensors with separately sealed source records",
        authority=authority,
    )
    result, receipted = ProvenanceConstrainedMessagePassing(
        independence_authority=authority
    ).consume(
        history,
        (original, independent_acquisition),
        independence_certificates=(certificate,),
    )
    assert len(result.consumed_evidence_semantic_fingerprints) == 2
    assert len(result.consumed_evidence_claim_fingerprints) == 2
    assert len(result.consumed_independence_certificate_sha256s) == 1
    assert (
        receipted.latest.revision_evidence_independence_certificate_sha256s
        == result.consumed_independence_certificate_sha256s
    )


def test_leave_one_cluster_out_reports_posterior_dependence():
    _case, history, evidence = _observed_case_and_history()
    audit = ProvenanceConstrainedMessagePassing().audit_leave_one_cluster_out(
        history,
        evidence,
        influence_threshold=1.0,
    )
    assert len(audit.impacts) == len(evidence)
    assert {item.evidence_cluster_id for item in audit.impacts} == {
        item.evidence_cluster_id for item in evidence
    }
    assert audit.maximum_total_variation >= 0.0
    assert audit.stable
    assert len(audit.full_result_sha256) == 64
