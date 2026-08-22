from __future__ import annotations

from uuid import uuid4

import pytest

from cpswm.contracts import EventMechanism
from cpswm.system.counterfactual_event_hypergraph import (
    EventHypothesisStatus,
    EventHypothesisUpdateKind,
    OpenWorldRoleConditionedReversibleEventRevisionEngine,
)
from cpswm.system.evaluation_operations import (
    HiddenEventFamily,
    M30HiddenEventSuiteGenerator,
)


def clean_handoff_case():
    suite = M30HiddenEventSuiteGenerator().generate(
        validation_seeds=(0,),
        test_seeds=(1,),
        families=(HiddenEventFamily.CLEAN_HANDOFF,),
    )
    return suite.cases[0]


def mechanism_copy(template, *, direct: float, handoff: float, label: str):
    return template.model_copy(
        update={
            "metadata": template.metadata.model_copy(
                update={"record_id": uuid4(), "source_id": label}
            ),
            "mechanism_posterior": {
                EventMechanism.DIRECT_RELOCATION: direct,
                EventMechanism.HANDOFF_RELOCATION: handoff,
            },
            "evidence_cluster_id": uuid4(),
        }
    )


def test_orrer_enumerates_unknown_actor_in_both_handoff_roles():
    case = clean_handoff_case().model_input
    history = OpenWorldRoleConditionedReversibleEventRevisionEngine().branch(
        before=case.before,
        after=case.after,
        actor_prior=case.actor_prior,
        handoff_fraction=0.5,
    )
    role_pairs = {
        (item.steps[0].actor_key, item.responsible_actor_key)
        for item in history.latest.hypotheses
        if item.explanation_code == EventMechanism.HANDOFF_RELOCATION.value
    }

    assert len(history.latest.hypotheses) == 9
    assert any(initiator == "unknown_actor" for initiator, _ in role_pairs)
    assert any(recipient == "unknown_actor" for _, recipient in role_pairs)


def test_orrer_reactivates_a_true_handoff_after_wrong_mechanism_pruning():
    generated = clean_handoff_case()
    case = generated.model_input
    template = case.initial_mechanism_evidence[0]
    wrong = mechanism_copy(
        template,
        direct=0.95,
        handoff=0.05,
        label="adversarial-wrong-mechanism",
    )
    correction = mechanism_copy(
        template,
        direct=0.005,
        handoff=0.995,
        label="independent-mechanism-correction",
    )
    engine = OpenWorldRoleConditionedReversibleEventRevisionEngine()
    branched = engine.branch(
        before=case.before,
        after=case.after,
        actor_prior=case.actor_prior,
        handoff_fraction=0.5,
    )
    pruned = engine.revise_event_mechanism(
        branched,
        wrong,
        retraction_threshold=0.02,
    )
    retracted_handoffs = {
        item.hypothesis_id
        for item in pruned.latest.hypotheses
        if item.explanation_code == EventMechanism.HANDOFF_RELOCATION.value
        and item.status == EventHypothesisStatus.RETRACTED
    }

    reactivated = engine.reactivate_with_evidence(
        pruned,
        correction,
        retraction_threshold=0.01,
    )
    restored = {
        item.hypothesis_id
        for item in reactivated.latest.hypotheses
        if item.status == EventHypothesisStatus.ACTIVE
    }

    assert retracted_handoffs
    assert reactivated.latest.update_kind == EventHypothesisUpdateKind.REACTIVATE
    assert retracted_handoffs & restored
    assert len(reactivated.revisions) == 3
    assert reactivated.latest.unresolved_probability < pruned.latest.unresolved_probability
    assert sum(item.revival_probability for item in reactivated.latest.hypotheses) == pytest.approx(
        1.0
    )


def test_orrer_neutral_evidence_cannot_reactivate_a_pruned_chain():
    case = clean_handoff_case().model_input
    template = case.initial_mechanism_evidence[0]
    engine = OpenWorldRoleConditionedReversibleEventRevisionEngine()
    history = engine.branch(
        before=case.before,
        after=case.after,
        actor_prior=case.actor_prior,
        handoff_fraction=0.5,
    )
    wrong = mechanism_copy(
        template,
        direct=0.95,
        handoff=0.05,
        label="wrong-before-neutral",
    )
    pruned = engine.revise_event_mechanism(history, wrong, retraction_threshold=0.02)
    retracted = {
        item.hypothesis_id
        for item in pruned.latest.hypotheses
        if item.status == EventHypothesisStatus.RETRACTED
    }
    neutral = mechanism_copy(
        template,
        direct=0.5,
        handoff=0.5,
        label="neutral-does-not-reactivate",
    )

    revised = engine.reactivate_with_evidence(
        pruned,
        neutral,
        retraction_threshold=0.01,
    )
    active = {
        item.hypothesis_id
        for item in revised.latest.hypotheses
        if item.status == EventHypothesisStatus.ACTIVE
    }

    assert retracted
    assert not retracted & active
