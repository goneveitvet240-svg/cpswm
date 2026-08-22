from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest

from cpswm.contracts import ActorEvidenceTrack, EventType, EvidenceRef, SourceType
from cpswm.system.counterfactual_event_hypergraph import (
    CounterfactualEventHypergraphEngine,
    EventHypothesisStatus,
    EventHypothesisUpdateKind,
    IndependentEventCandidateBaseline,
    Top1EventGraphBaseline,
    actor_evidence_semantic_fingerprint,
)
from cpswm.system.evaluation_operations import D0ShiftScenarioGenerator, ShiftCause


def actor_shift_case():
    suite = D0ShiftScenarioGenerator().generate(
        actor_evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE
    )
    return next(
        case for case in suite.cases if case.evaluator_truth.true_cause == ShiftCause.ACTOR_MIXTURE
    )


def transition_records(case):
    detections = [
        item
        for item in case.model_input.shifted_run.detection_results
        if item.detected_location_id is not None
    ]
    before = max(
        (item for item in detections if item.detection_time < case.model_input.change_time),
        key=lambda item: item.detection_time,
    )
    after = min(
        (item for item in detections if item.detection_time >= case.model_input.change_time),
        key=lambda item: item.detection_time,
    )
    actor_evidence = min(
        case.model_input.shifted_actor_evidence,
        key=lambda item: item.evidence_time,
    )
    return before, after, actor_evidence


def validated_actor_evidence_copy(actor_evidence, **updates):
    payload = actor_evidence.model_dump(mode="python")
    metadata_updates = updates.pop("metadata", {})
    payload["metadata"] = {**payload["metadata"], **metadata_updates}
    payload.update(updates)
    return type(actor_evidence).model_validate(payload)


def test_cheh_branches_direct_and_handoff_chains_without_committing_top1():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    owner = str(case.model_input.target_person_id)
    guest = next(
        actor for actor in actor_evidence.actor_posterior if actor not in {owner, "unknown_actor"}
    )
    engine = CounterfactualEventHypergraphEngine()

    history = engine.branch(
        before=before,
        after=after,
        actor_prior={owner: 0.45, guest: 0.25, "unknown_actor": 0.30},
    )

    revision = history.latest
    assert revision.update_kind == EventHypothesisUpdateKind.BRANCH
    assert revision.revision_no == 0
    assert len(revision.hypotheses) == 5
    assert revision.unresolved_probability == pytest.approx(0.1)
    assert sum(
        item.posterior_probability for item in revision.hypotheses
    ) + revision.unresolved_probability == pytest.approx(1.0)
    assert {item.explanation_code for item in revision.hypotheses} == {
        "direct_relocation",
        "handoff_relocation",
    }
    assert any(
        tuple(step.event_type for step in item.steps)
        == (EventType.PICK_UP, EventType.CARRY, EventType.TRANSFER, EventType.PLACE)
        for item in revision.hypotheses
    )
    assert all(
        set(revision.source_detection_result_ids).issubset(item.source_record_ids)
        for item in revision.hypotheses
    )


def test_cheh_hypothesis_set_identity_binds_complete_endpoint_content():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    engine = CounterfactualEventHypergraphEngine()
    baseline = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    changed_object_id = uuid4()
    changed_before = before.model_copy(
        update={
            "detected_object_instance_id": changed_object_id,
            "detected_location_id": uuid4(),
        }
    )
    changed_after = after.model_copy(
        update={
            "detected_object_instance_id": changed_object_id,
            "detected_location_id": uuid4(),
        }
    )

    changed = engine.branch(
        before=changed_before,
        after=changed_after,
        actor_prior=actor_evidence.reference_actor_prior,
    )

    assert changed_before.metadata.record_id == before.metadata.record_id
    assert changed_after.metadata.record_id == after.metadata.record_id
    assert changed.hypothesis_set_id != baseline.hypothesis_set_id


def test_cheh_revision_uses_actor_evidence_and_preserves_all_alternatives():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    owner = str(case.model_input.target_person_id)
    guest = max(
        actor_evidence.actor_posterior,
        key=actor_evidence.actor_posterior.get,
    )
    engine = CounterfactualEventHypergraphEngine()
    branched = engine.branch(
        before=before,
        after=after,
        actor_prior={owner: 0.45, guest: 0.25, "unknown_actor": 0.30},
    )

    revised = engine.revise_actor_responsibility(branched, actor_evidence)

    assert len(revised.revisions) == 2
    assert revised.latest.update_kind == EventHypothesisUpdateKind.REVISE
    assert revised.latest.parent_revision_id == branched.latest.revision_id
    assert len(revised.latest.hypotheses) == len(branched.latest.hypotheses)
    assert revised.latest.map_hypothesis is not None
    assert revised.latest.map_hypothesis.responsible_actor_key == guest
    assert revised.latest.revision_evidence_record_ids == (actor_evidence.metadata.record_id,)
    assert revised.latest.revision_evidence_cluster_ids == (actor_evidence.evidence_cluster_id,)


def test_cheh_neutral_likelihood_ratio_does_not_multiply_the_prior_twice():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    neutral = actor_evidence.model_copy(
        update={
            "metadata": actor_evidence.metadata.model_copy(update={"record_id": uuid4()}),
            "actor_posterior": actor_evidence.reference_actor_prior,
            "evidence_cluster_id": uuid4(),
        }
    )

    revised = engine.revise_actor_responsibility(history, neutral, retraction_threshold=0.0)

    assert tuple(item.posterior_probability for item in revised.latest.hypotheses) == pytest.approx(
        tuple(item.posterior_probability for item in history.latest.hypotheses)
    )
    assert revised.latest.unresolved_probability == pytest.approx(
        history.latest.unresolved_probability
    )


def test_cheh_rejects_duplicate_record_and_correlated_cluster_evidence():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    revised = engine.revise_actor_responsibility(history, actor_evidence)

    with pytest.raises(ValueError, match="record cannot be reused"):
        engine.revise_actor_responsibility(revised, actor_evidence)

    same_cluster = actor_evidence.model_copy(
        update={"metadata": actor_evidence.metadata.model_copy(update={"record_id": uuid4()})}
    )
    with pytest.raises(ValueError, match="cluster cannot be reused"):
        engine.revise_actor_responsibility(revised, same_cluster)


def test_cheh_rejects_semantic_evidence_clone_with_fresh_wrapper_ids():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    revised = engine.revise_actor_responsibility(history, actor_evidence)
    semantic_clone = validated_actor_evidence_copy(
        actor_evidence,
        metadata={"record_id": uuid4()},
        evidence_cluster_id=uuid4(),
    )

    with pytest.raises(ValueError, match="semantic actor evidence cannot be reused"):
        engine.revise_actor_responsibility(revised, semantic_clone)


def test_cheh_semantic_fingerprint_ignores_only_wrapper_identity():
    case = actor_shift_case()
    _, _, actor_evidence = transition_records(case)
    reference = EvidenceRef(
        evidence_type="actor-view",
        source_record_id=uuid4(),
        locator="frame://42",
    )
    actor_evidence = validated_actor_evidence_copy(
        actor_evidence,
        metadata={"source_type": SourceType.MODEL},
        evidence_refs=(reference,),
    )
    semantic_clone = validated_actor_evidence_copy(
        actor_evidence,
        metadata={"record_id": uuid4()},
        evidence_cluster_id=uuid4(),
        evidence_refs=(reference.model_copy(update={"evidence_id": uuid4()}),),
    )

    assert actor_evidence_semantic_fingerprint(
        actor_evidence
    ) == actor_evidence_semantic_fingerprint(semantic_clone)

    reordered_or_duplicated_wrapper = validated_actor_evidence_copy(
        actor_evidence,
        metadata={"record_id": uuid4()},
        evidence_cluster_id=uuid4(),
        evidence_refs=(
            reference.model_copy(update={"evidence_id": uuid4()}),
            reference,
        ),
    )
    assert actor_evidence_semantic_fingerprint(
        actor_evidence
    ) == actor_evidence_semantic_fingerprint(reordered_or_duplicated_wrapper)

    changed_source = validated_actor_evidence_copy(
        semantic_clone,
        metadata={"record_id": uuid4(), "source_id": "independent-source"},
        evidence_cluster_id=uuid4(),
    )
    assert actor_evidence_semantic_fingerprint(
        actor_evidence
    ) != actor_evidence_semantic_fingerprint(changed_source)

    changed_reference = validated_actor_evidence_copy(
        semantic_clone,
        metadata={"record_id": uuid4()},
        evidence_cluster_id=uuid4(),
        evidence_refs=(reference.model_copy(update={"source_record_id": uuid4()}),),
    )
    assert actor_evidence_semantic_fingerprint(
        actor_evidence
    ) != actor_evidence_semantic_fingerprint(changed_reference)


def test_cheh_semantic_fingerprint_changes_with_real_evidence_content():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    revised = engine.revise_actor_responsibility(history, actor_evidence)
    changed_model = validated_actor_evidence_copy(
        actor_evidence,
        metadata={"record_id": uuid4(), "model_version": "independent-model@2"},
        evidence_cluster_id=uuid4(),
        evidence_model_id="independent-model@2",
    )

    accepted = engine.revise_actor_responsibility(revised, changed_model)

    assert len(accepted.revisions) == 3
    assert (
        revised.latest.revision_evidence_semantic_fingerprints
        != accepted.latest.revision_evidence_semantic_fingerprints
    )


@pytest.mark.parametrize("scope_field", ("household_id", "session_id", "trace_id"))
def test_cheh_rejects_actor_evidence_from_a_different_scope(scope_field):
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    history = CounterfactualEventHypergraphEngine().branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    foreign_scope = actor_evidence.model_copy(
        update={
            "metadata": actor_evidence.metadata.model_copy(
                update={
                    "record_id": uuid4(),
                    scope_field: uuid4(),
                }
            ),
            "evidence_cluster_id": uuid4(),
        }
    )

    with pytest.raises(ValueError, match=f"{scope_field} does not match"):
        CounterfactualEventHypergraphEngine().revise_actor_responsibility(
            history,
            foreign_scope,
        )


def test_cheh_rejects_actor_evidence_one_hundred_days_after_its_endpoint():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    late_time = actor_evidence.evidence_time + timedelta(days=100)
    late_evidence = actor_evidence.model_copy(
        update={
            "metadata": actor_evidence.metadata.model_copy(
                update={"record_id": uuid4(), "recorded_time": late_time}
            ),
            "evidence_time": late_time,
            "evidence_cluster_id": uuid4(),
        }
    )

    with pytest.raises(ValueError, match="time does not match its endpoint"):
        engine.revise_actor_responsibility(history, late_evidence)


def test_cheh_actor_revision_requires_destination_endpoint_evidence():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    source_bound = actor_evidence.model_copy(
        update={
            "metadata": actor_evidence.metadata.model_copy(
                update={"record_id": uuid4(), "recorded_time": before.detection_time}
            ),
            "source_detection_result_id": before.metadata.record_id,
            "evidence_time": before.detection_time,
            "evidence_cluster_id": uuid4(),
        }
    )

    with pytest.raises(ValueError, match="destination endpoint"):
        engine.revise_actor_responsibility(history, source_bound)


@pytest.mark.parametrize("nested", (False, True), ids=("top-level", "nested"))
def test_cheh_branch_rejects_endpoint_model_copy_extra_fields(nested):
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    if nested:
        before = before.model_copy(
            update={
                "metadata": before.metadata.model_copy(update={"injected_extra": "not-declared"})
            }
        )
    else:
        before = before.model_copy(update={"injected_extra": "not-declared"})

    with pytest.raises(ValueError, match="unexpected field"):
        CounterfactualEventHypergraphEngine().branch(
            before=before,
            after=after,
            actor_prior=actor_evidence.reference_actor_prior,
        )


@pytest.mark.parametrize(
    "metadata_update",
    (
        {"schema_name": "cpswm.NotDetection"},
        {"schema_version": "9.9.9"},
    ),
    ids=("name", "version"),
)
def test_cheh_branch_rejects_mislabeled_endpoint_schema(metadata_update):
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    mislabeled = before.model_copy(
        update={"metadata": before.metadata.model_copy(update=metadata_update)}
    )

    with pytest.raises(ValueError, match="endpoint metadata schema"):
        CounterfactualEventHypergraphEngine().branch(
            before=mislabeled,
            after=after,
            actor_prior=actor_evidence.reference_actor_prior,
        )


@pytest.mark.parametrize("boundary", ("history", "evidence"))
def test_cheh_revise_rejects_model_copy_extra_fields(boundary):
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    actor_evidence = actor_evidence.model_copy(
        update={
            "metadata": actor_evidence.metadata.model_copy(update={"record_id": uuid4()}),
            "evidence_cluster_id": uuid4(),
        }
    )
    if boundary == "history":
        history = history.model_copy(update={"injected_extra": "not-declared"})
    else:
        actor_evidence = actor_evidence.model_copy(update={"injected_extra": "not-declared"})

    with pytest.raises(ValueError, match="unexpected field"):
        engine.revise_actor_responsibility(history, actor_evidence)


@pytest.mark.parametrize(
    "metadata_update",
    (
        {"schema_name": "cpswm.NotActorEvidence"},
        {"schema_version": "9.9.9"},
    ),
    ids=("name", "version"),
)
def test_cheh_revise_rejects_mislabeled_actor_evidence(metadata_update):
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    mislabeled = actor_evidence.model_copy(
        update={
            "metadata": actor_evidence.metadata.model_copy(
                update={"record_id": uuid4(), **metadata_update}
            ),
            "evidence_cluster_id": uuid4(),
        }
    )

    with pytest.raises(ValueError, match="actor evidence metadata schema"):
        engine.revise_actor_responsibility(history, mislabeled)


def test_cheh_retract_rejects_counterevidence_without_a_known_endpoint():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    target = history.latest.map_hypothesis
    assert target is not None
    other_actors = tuple(
        actor for actor in actor_evidence.actor_posterior if actor != target.responsible_actor_key
    )
    bad_counterevidence = actor_evidence.model_copy(
        update={
            "metadata": actor_evidence.metadata.model_copy(update={"record_id": uuid4()}),
            "source_detection_result_id": uuid4(),
            "actor_posterior": {
                actor: (0.0 if actor == target.responsible_actor_key else 1.0 / len(other_actors))
                for actor in actor_evidence.actor_posterior
            },
            "evidence_cluster_id": uuid4(),
        }
    )

    with pytest.raises(ValueError, match="must cite a CHEH endpoint detection"):
        engine.retract(
            history,
            hypothesis_ids=(target.hypothesis_id,),
            counterevidence=(bad_counterevidence,),
            reason="forged counterevidence must not retract a hypothesis",
        )


def test_cheh_retract_rejects_semantic_clones_in_one_counterevidence_tuple():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    target = history.latest.map_hypothesis
    assert target is not None
    other_actors = tuple(
        actor for actor in actor_evidence.actor_posterior if actor != target.responsible_actor_key
    )
    counterevidence = validated_actor_evidence_copy(
        actor_evidence,
        metadata={"record_id": uuid4()},
        actor_posterior={
            actor: (0.0 if actor == target.responsible_actor_key else 1.0 / len(other_actors))
            for actor in actor_evidence.actor_posterior
        },
        evidence_cluster_id=uuid4(),
    )
    semantic_clone = validated_actor_evidence_copy(
        counterevidence,
        metadata={"record_id": uuid4()},
        evidence_cluster_id=uuid4(),
    )

    with pytest.raises(ValueError, match="semantic actor evidence cannot be reused"):
        engine.retract(
            history,
            hypothesis_ids=(target.hypothesis_id,),
            counterevidence=(counterevidence, semantic_clone),
            reason="one source relabelled as two counterevidence records",
        )


def test_cheh_rejects_duplicate_evidence_ref_wrapper_across_revisions():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    reference = EvidenceRef(
        evidence_type="actor-view",
        source_record_id=uuid4(),
        locator="frame://same-view",
    )
    actor_evidence = validated_actor_evidence_copy(
        actor_evidence,
        metadata={"source_type": SourceType.MODEL},
        evidence_refs=(reference,),
    )
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    history = engine.revise_actor_responsibility(history, actor_evidence)
    duplicated_ref_clone = validated_actor_evidence_copy(
        actor_evidence,
        metadata={"record_id": uuid4()},
        evidence_cluster_id=uuid4(),
        evidence_refs=(reference, reference.model_copy(update={"evidence_id": uuid4()})),
    )

    with pytest.raises(ValueError, match="semantic actor evidence cannot be reused"):
        engine.revise_actor_responsibility(history, duplicated_ref_clone)


def test_cheh_retract_rejects_duplicate_ref_semantic_clone_in_same_tuple():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    target = history.latest.map_hypothesis
    assert target is not None
    other_actors = tuple(
        actor for actor in actor_evidence.actor_posterior if actor != target.responsible_actor_key
    )
    reference = EvidenceRef(
        evidence_type="actor-view",
        source_record_id=uuid4(),
        locator="frame://counterevidence",
    )
    counterevidence = validated_actor_evidence_copy(
        actor_evidence,
        metadata={"record_id": uuid4(), "source_type": SourceType.MODEL},
        actor_posterior={
            actor: (0.0 if actor == target.responsible_actor_key else 1.0 / len(other_actors))
            for actor in actor_evidence.actor_posterior
        },
        evidence_cluster_id=uuid4(),
        evidence_refs=(reference,),
    )
    duplicated_ref_clone = validated_actor_evidence_copy(
        counterevidence,
        metadata={"record_id": uuid4()},
        evidence_cluster_id=uuid4(),
        evidence_refs=(reference, reference.model_copy(update={"evidence_id": uuid4()})),
    )

    with pytest.raises(ValueError, match="semantic actor evidence cannot be reused"):
        engine.retract(
            history,
            hypothesis_ids=(target.hypothesis_id,),
            counterevidence=(counterevidence, duplicated_ref_clone),
            reason="duplicate ref packaging is not independent counterevidence",
        )


def test_cheh_semantic_fingerprint_normalizes_negative_zero():
    case = actor_shift_case()
    _, _, actor_evidence = transition_records(case)
    zero_actor = next(iter(actor_evidence.actor_posterior))
    other_actors = tuple(actor for actor in actor_evidence.actor_posterior if actor != zero_actor)
    positive_zero = validated_actor_evidence_copy(
        actor_evidence,
        actor_posterior={
            actor: (0.0 if actor == zero_actor else 1.0 / len(other_actors))
            for actor in actor_evidence.actor_posterior
        },
    )
    negative_zero = validated_actor_evidence_copy(
        positive_zero,
        metadata={"record_id": uuid4()},
        evidence_cluster_id=uuid4(),
        actor_posterior={
            **positive_zero.actor_posterior,
            zero_actor: -0.0,
        },
    )

    assert positive_zero.actor_posterior == negative_zero.actor_posterior
    assert actor_evidence_semantic_fingerprint(
        positive_zero
    ) == actor_evidence_semantic_fingerprint(negative_zero)


def test_cheh_retract_rejects_negative_zero_semantic_clone_in_same_tuple():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior=actor_evidence.reference_actor_prior,
    )
    target = history.latest.map_hypothesis
    assert target is not None
    target_actor = target.responsible_actor_key
    other_actors = tuple(actor for actor in actor_evidence.actor_posterior if actor != target_actor)
    counterevidence = validated_actor_evidence_copy(
        actor_evidence,
        metadata={"record_id": uuid4()},
        actor_posterior={
            actor: (0.0 if actor == target_actor else 1.0 / len(other_actors))
            for actor in actor_evidence.actor_posterior
        },
        evidence_cluster_id=uuid4(),
    )
    negative_zero_clone = validated_actor_evidence_copy(
        counterevidence,
        metadata={"record_id": uuid4()},
        evidence_cluster_id=uuid4(),
        actor_posterior={
            **counterevidence.actor_posterior,
            target_actor: -0.0,
        },
    )

    with pytest.raises(ValueError, match="semantic actor evidence cannot be reused"):
        engine.retract(
            history,
            hypothesis_ids=(target.hypothesis_id,),
            counterevidence=(counterevidence, negative_zero_clone),
            reason="negative zero is not independent counterevidence",
        )


def test_cheh_retract_moves_mass_to_unresolved_and_rebuilds_exactly():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    actors = list(actor_evidence.actor_posterior)
    engine = CounterfactualEventHypergraphEngine()
    history = engine.branch(
        before=before,
        after=after,
        actor_prior={actor: actor_evidence.actor_posterior[actor] for actor in actors},
    )
    history = engine.revise_actor_responsibility(history, actor_evidence)
    target = history.latest.map_hypothesis
    assert target is not None
    unresolved_before = history.latest.unresolved_probability

    counterevidence = actor_evidence.model_copy(
        update={
            "metadata": actor_evidence.metadata.model_copy(update={"record_id": uuid4()}),
            "actor_posterior": {
                actor: (0.0 if actor == target.responsible_actor_key else 0.5)
                for actor in actor_evidence.actor_posterior
            },
            "evidence_cluster_id": uuid4(),
        }
    )
    retracted = engine.retract(
        history,
        hypothesis_ids=(target.hypothesis_id,),
        counterevidence=(counterevidence,),
        reason="later observation contradicts the final placing actor",
    )

    target_after = next(
        item for item in retracted.latest.hypotheses if item.hypothesis_id == target.hypothesis_id
    )
    assert target_after.status == EventHypothesisStatus.RETRACTED
    assert target_after.posterior_probability == 0.0
    assert retracted.latest.unresolved_probability > unresolved_before
    assert engine.rebuild(retracted.revisions) == retracted


def test_cheh_rejects_a_single_actor_top1_branch():
    case = actor_shift_case()
    before, after, _ = transition_records(case)

    with pytest.raises(ValueError, match="at least two actor hypotheses"):
        CounterfactualEventHypergraphEngine().branch(
            before=before,
            after=after,
            actor_prior={str(case.model_input.target_person_id): 1.0},
        )


def test_direct_top1_and_independent_candidate_baselines_have_weaker_state():
    case = actor_shift_case()
    before, after, actor_evidence = transition_records(case)
    actor_scores = actor_evidence.actor_posterior

    top1 = Top1EventGraphBaseline().predict(
        before=before,
        after=after,
        actor_prior=actor_scores,
    )
    independent = IndependentEventCandidateBaseline().predict(
        before=before,
        after=after,
        actor_confidence=actor_scores,
    )

    assert top1.responsible_actor_key == max(actor_scores, key=actor_scores.get)
    assert not hasattr(top1, "revisions")
    assert len(independent.candidates) == len(actor_scores)
    assert sum(item.independent_confidence for item in independent.candidates) != pytest.approx(1.0)
    assert not hasattr(independent, "unresolved_probability")
