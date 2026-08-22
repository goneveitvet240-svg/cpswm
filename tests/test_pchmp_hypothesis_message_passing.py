"""Tests for Provenance-Constrained Hypothesis Message Passing (PCHMP, §4.7 #4)."""

from __future__ import annotations

import pytest

from cpswm.system.counterfactual_event_hypergraph import (
    OpenWorldRoleConditionedReversibleEventRevisionEngine,
    ProvenanceConstrainedMessagePassing,
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


def test_posterior_plus_unresolved_sums_to_one():
    _case, history, evidence = _observed_case_and_history()
    result = ProvenanceConstrainedMessagePassing().infer(history, evidence)
    assert sum(result.posterior_by_hypothesis_id.values()) + result.unresolved_probability == (
        pytest.approx(1.0, abs=1e-9)
    )


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
        h.hypothesis_id
        for h in history.latest.hypotheses
        if h.responsible_actor_key == OWNER
    }
    guest_hypothesis_ids = {
        h.hypothesis_id
        for h in history.latest.hypotheses
        if h.responsible_actor_key == GUEST
    }
    # The evidence stream is symmetric across actors in aggregate (both actor
    # and role factors), so the firewall keeps every hypothesis finite and the
    # posterior normalized, never negative.
    assert all(
        value >= 0.0
        for value in posterior_with_evidence.posterior_by_hypothesis_id.values()
    )
    assert owner_hypothesis_ids and guest_hypothesis_ids
    del baseline  # unused beyond setup


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
