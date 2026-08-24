from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from cpswm.contracts import (
    ActionOutcomeLikelihoodModel,
    DecisionContextBinding,
    DecisionSurface,
    EntityRef,
    EntityType,
    ExecutionFeedbackRecord,
    MapConsistencyRevisions,
    ObservationOpportunityRecord,
    RobotActionOutcome,
    RobotActionType,
    SourceType,
    TargetPresenceBeliefRef,
)
from cpswm.contracts.base import ValidTimeInterval
from cpswm.contracts.decision_context import DecisionContext
from cpswm.system.continual.execution_feedback_projector import (
    LocationTransitionEvidence,
    TransitionCandidate,
)
from cpswm.system.continual.project_one_feedback import FeedbackInterpretation
from cpswm.system.counterfactual_event_hypergraph.feedback_revision_loop import (
    ProjectOneRequestKind,
    ProjectOneStatRequest,
    apply_project_one_request,
)
from cpswm.system.evaluation_operations import StructureTwoActionScenarioGenerator
from cpswm.system.prototype_spine import (
    CorePrototypeSpine,
    DerivedEvidenceReactivationPolicy,
    EventRevisionKind,
    EventRevisionOutcome,
    HabitStateConclusion,
    PrototypeLoopConfig,
    PrototypeStatisticOperation,
    PrototypeTransition,
    _normalized_predictive_surprise,
)
from cpswm.world_model.habits_transitions import ChangeCause


@pytest.fixture
def case():
    return StructureTwoActionScenarioGenerator().generate(31).visible


def _template_observation(case):
    return next(day for day in case.days if day.before is not None and day.after is not None)


def _spine(case, *, confirmation_window: int = 2) -> CorePrototypeSpine:
    return CorePrototypeSpine(
        owner_key=case.owner_actor,
        object_instance_id=case.object_instance_id,
        locations=case.locations,
        authorization_scope_id=uuid4(),
        loop_config=PrototypeLoopConfig(
            minimum_baseline_observations=3,
            confirmation_window=confirmation_window,
            habit_change_probability_threshold=0.5,
            transient_disturbance_probability_threshold=0.5,
            owner_evidence_threshold=0.5,
            feedback_failure_strength=0.25,
        ),
    )


def _spine_with_forgetting(case, forgetting_factor: float) -> CorePrototypeSpine:
    spine = _spine(case)
    spine.loop_config = replace(spine.loop_config, forgetting_factor=forgetting_factor)
    spine._regimes = spine._new_regime_bank()
    spine._automatic_regimes = spine._new_automatic_regime_router()
    return spine


def _transition(case, *, location: UUID, index: int) -> PrototypeTransition:
    template = _template_observation(case)
    assert template.before is not None and template.after is not None
    when = template.after.detection_time + timedelta(days=index)
    opportunity_id = uuid4()
    before_location = next(item for item in case.locations if item != location)
    before = template.before.model_copy(
        update={
            "metadata": template.before.metadata.model_copy(update={"record_id": uuid4()}),
            "detected_location_id": before_location,
            "detection_time": when - timedelta(minutes=1),
            "observation_opportunity_id": uuid4(),
        }
    )
    after = template.after.model_copy(
        update={
            "metadata": template.after.metadata.model_copy(update={"record_id": uuid4()}),
            "detected_location_id": location,
            "detection_time": when,
            "observation_opportunity_id": opportunity_id,
        }
    )
    opportunity = ObservationOpportunityRecord(
        metadata=after.metadata.model_copy(
            update={
                "record_id": opportunity_id,
                "schema_name": "cpswm.ObservationOpportunityRecord",
            }
        ),
        observation_action_id=uuid4(),
        opportunity_time=when,
        selected=True,
        selection_probability=0.8,
        p_visible_given_state=0.95,
        p_detect_given_visible=0.95,
        likelihood_model_id="project-one-prototype-observation@0.1",
    )
    return PrototypeTransition(
        opportunity=opportunity,
        before=before,
        after=after,
        actor_prior={case.owner_actor: 0.9, case.guest_actor: 0.05, "unknown_actor": 0.05},
        context_key="weekday|home",
        context_value=float(index % 7),
    )


def _observe(spine, case, locations):
    start = spine.observation_count
    return [
        spine.process_transition(_transition(case, location=location, index=start + index))
        for index, location in enumerate(locations)
    ]


def _reinforce_once(*, case, spine, transition, source_result):
    source_proxy = replace(source_result, belief_snapshot=spine.current_snapshot)
    feedback, binding, likelihood = _search_feedback_bundle(
        case=case,
        spine=spine,
        transition=transition,
        original=source_proxy,
        outcome_distribution={
            RobotActionOutcome.SUCCESS: 0.99,
            RobotActionOutcome.UNKNOWN: 0.01,
        },
        present_likelihood={
            RobotActionOutcome.SUCCESS: 0.99,
            RobotActionOutcome.UNKNOWN: 0.01,
        },
        absent_likelihood={
            RobotActionOutcome.SUCCESS: 0.01,
            RobotActionOutcome.UNKNOWN: 0.99,
        },
    )
    spine.process_execution_feedback(
        feedback=feedback,
        binding=binding,
        likelihood_model=likelihood,
    )
    return spine.derived_revision_ids(source_proxy.event_revision_id)[0]


def _search_feedback_bundle(
    *,
    case,
    spine,
    transition,
    original,
    outcome_distribution,
    present_likelihood,
    absent_likelihood,
    bound_snapshot_id=None,
):
    location = transition.after.detected_location_id
    when = transition.after.detection_time
    metadata = transition.after.metadata.model_copy(
        update={
            "record_id": uuid4(),
            "schema_name": "cpswm.ExecutionFeedbackRecord",
            "source_type": SourceType.ACTION,
            "recorded_time": when,
        }
    )
    feedback = ExecutionFeedbackRecord(
        metadata=metadata,
        action_id=uuid4(),
        action_type=RobotActionType.SEARCH,
        target_entity=EntityRef(
            entity_id=case.object_instance_id,
            entity_type=EntityType.OBJECT_INSTANCE,
        ),
        attempted_location_id=location,
        valid_time=ValidTimeInterval(start=when, end=when + timedelta(minutes=1)),
        outcome_distribution=outcome_distribution,
        observation_opportunity_id=transition.opportunity.metadata.record_id,
        diagnostics={"source_revision_id": str(original.event_revision_id)},
    )
    revisions = MapConsistencyRevisions(
        belief_snapshot_id=(bound_snapshot_id or original.belief_snapshot.snapshot_id),
        projection_id=uuid4(),
        projection_version=1,
        static_map_revision=1,
        dynamic_map_revision=1,
        event_history_revision=1,
        input_watermark=1,
    )
    context = DecisionContext.create(
        decision_id=uuid4(),
        decision_time=when,
        valid_time=ValidTimeInterval(start=when, end=when + timedelta(minutes=5)),
        staleness_budget_seconds=300.0,
        revisions=revisions,
        target_presence_belief=TargetPresenceBeliefRef(
            object_instance_id=case.object_instance_id,
            location_id=location,
            belief_node_id="prototype-presence",
            belief_snapshot_id=revisions.belief_snapshot_id,
            node_content_hash="a" * 64,
            prior_probability=0.8,
        ),
        authorization_scope_id=spine.authorization_scope_id,
        habit_regime_model_version=spine.model_version,
        model_versions=(("prototype", spine.model_version),),
        code_version="prototype-test",
        rationale="bind search feedback to the exact snapshot",
    )
    binding = DecisionContextBinding(
        metadata=metadata.model_copy(
            update={
                "record_id": uuid4(),
                "schema_name": "cpswm.DecisionContextBinding",
            }
        ),
        surface=DecisionSurface.EXECUTION_FEEDBACK,
        subject_record_id=feedback.metadata.record_id,
        subject_household_id=metadata.household_id,
        subject_session_id=metadata.session_id,
        subject_trace_id=metadata.trace_id,
        decision_context=context,
    )
    likelihood = ActionOutcomeLikelihoodModel(
        action_type=RobotActionType.SEARCH,
        p_outcome_given_target_present=present_likelihood,
        p_outcome_given_target_absent=absent_likelihood,
        calibration_domain="prototype-search",
        model_version="search-likelihood@0.1",
    )
    return feedback, binding, likelihood


def test_single_location_anomaly_does_not_switch_regime(case):
    spine = _spine(case)
    stable, anomaly = case.locations[:2]

    results = _observe(spine, case, [stable, stable, stable, anomaly, stable])

    assert results[3].decision.conclusion is HabitStateConclusion.INSUFFICIENT_EVIDENCE
    assert results[3].decision.statistic_operations == (PrototypeStatisticOperation.QUARANTINE,)
    assert results[3].active_regime == "stable"
    assert results[4].decision.conclusion is HabitStateConclusion.SHORT_TERM_DISTURBANCE
    assert results[4].active_regime == "stable"


def test_same_location_candidate_is_rejected_across_incompatible_context(case):
    spine = _spine(case)
    stable, changed = case.locations[:2]
    _observe(spine, case, [stable, stable, stable])
    first = _transition(case, location=changed, index=3)
    first = replace(first, context_key="weekday|home", context_value=0.0)
    second = _transition(case, location=changed, index=4)
    second = replace(second, context_key="weekend|away", context_value=100.0)

    candidate = spine.process_transition(first)
    rejected = spine.process_transition(second)

    assert candidate.decision.conclusion is HabitStateConclusion.INSUFFICIENT_EVIDENCE
    assert rejected.decision.conclusion is HabitStateConclusion.SHORT_TERM_DISTURBANCE
    assert rejected.active_regime == "stable"


def test_same_state_key_with_incompatible_context_features_cannot_confirm(case):
    spine = _spine(case)
    stable, changed = case.locations[:2]
    _observe(spine, case, [stable, stable, stable])
    first = replace(
        _transition(case, location=changed, index=3),
        context_key="same-semantic-context",
        context_value=0.0,
    )
    incompatible = replace(
        _transition(case, location=changed, index=4),
        context_key="same-semantic-context",
        context_value=100.0,
    )

    assert spine.process_transition(first).decision.conclusion is (
        HabitStateConclusion.INSUFFICIENT_EVIDENCE
    )
    rejected = spine.process_transition(incompatible)
    assert rejected.decision.conclusion is HabitStateConclusion.SHORT_TERM_DISTURBANCE
    assert rejected.active_regime == "stable"


def test_legitimate_alternating_habit_is_not_persistent_change(case):
    spine = _spine(case)
    first, second = case.locations[:2]
    transitions = []
    for index, location in enumerate([first, second] * 8):
        transition = _transition(case, location=location, index=index)
        transitions.append(
            replace(
                transition,
                context_key=f"alternating-slot-{index % 2}",
                context_value=float(index % 2),
            )
        )

    results = [spine.process_transition(item) for item in transitions]
    assert all(
        result.decision.conclusion is not HabitStateConclusion.HABIT_CHANGE for result in results
    )
    assert spine.active_regime == "stable"


def test_known_periodic_habit_does_not_create_pseudo_regime(case):
    spine = _spine(case)
    morning, evening = case.locations[:2]
    results = []
    for index in range(24):
        slot = index % 2
        transition = replace(
            _transition(
                case,
                location=(morning if slot == 0 else evening),
                index=index,
            ),
            context_key=("periodic-morning" if slot == 0 else "periodic-evening"),
            context_value=float(slot),
        )
        results.append(spine.process_transition(transition))

    assert all(
        result.decision.conclusion is not HabitStateConclusion.HABIT_CHANGE for result in results
    )
    assert spine.active_regime == "stable"
    changed_events = [
        spine._observed_events[result.event_revision_id]
        for result in results[8:]
        if spine._observed_events[result.event_revision_id].regime_frame is not None
    ]
    assert all(event.regime_frame.signals[ChangeCause.HABIT] < 1.0 for event in changed_events)


def test_predicted_periodic_move_and_unpredicted_new_move_have_different_decisions(case):
    spine = _spine(case)
    morning, evening, novel = case.locations[:3]
    for index in range(24):
        slot = index % 2
        spine.process_transition(
            replace(
                _transition(
                    case,
                    location=(morning if slot == 0 else evening),
                    index=index,
                ),
                context_key=("periodic-morning" if slot == 0 else "periodic-evening"),
                context_value=float(slot),
            )
        )

    predicted = spine.process_transition(
        replace(
            _transition(case, location=morning, index=24),
            context_key="periodic-morning",
            context_value=0.0,
        )
    )
    unpredicted = spine.process_transition(
        replace(
            _transition(case, location=novel, index=25),
            context_key="previously-unseen-slot",
            context_value=2.0,
        )
    )

    assert predicted.decision.conclusion is HabitStateConclusion.STABLE
    assert unpredicted.decision.conclusion is HabitStateConclusion.INSUFFICIENT_EVIDENCE
    assert predicted.decision.conclusion is not unpredicted.decision.conclusion


def test_surprise_below_uniform_probability_preserves_severity_ordering():
    class_count = 4
    uniform = _normalized_predictive_surprise(1.0 / class_count, class_count)
    unlikely = _normalized_predictive_surprise(0.1 / class_count, class_count)
    extreme = _normalized_predictive_surprise(0.01 / class_count, class_count)

    assert uniform == pytest.approx(0.0)
    assert 0.0 < unlikely < extreme < 1.0


def test_long_online_observation_steps_bocpd_once_per_new_prefix(case, monkeypatch):
    spine = _spine(case)
    location = case.locations[0]
    step_calls = 0
    original_step = spine._automatic_regimes.bocpd._step

    def counted_step(beam, frame):
        nonlocal step_calls
        step_calls += 1
        return original_step(beam, frame)

    monkeypatch.setattr(spine._automatic_regimes.bocpd, "_step", counted_step)
    _observe(spine, case, [location] * 40)
    assert step_calls == 40


def test_persistent_change_creates_new_regime(case):
    spine = _spine(case)
    stable, changed = case.locations[:2]

    results = _observe(spine, case, [stable, stable, stable, changed, changed])

    decision = results[-1].decision
    assert decision.conclusion is HabitStateConclusion.HABIT_CHANGE
    assert decision.old_regime == "stable"
    assert decision.new_regime != "stable"
    assert results[-1].active_regime == decision.new_regime
    assert decision.change_probability >= 0.5


def test_confirmed_change_promotes_first_quarantined_sample(case):
    spine = _spine(case)
    stable, changed = case.locations[:2]
    results = _observe(spine, case, [stable, stable, stable, changed, changed])

    first_candidate = results[3]
    assert first_candidate.decision.statistic_operations == (
        PrototypeStatisticOperation.QUARANTINE,
    )
    assert spine.is_committed_revision(first_candidate.event_revision_id)
    before = spine.hybrid_alpha(changed)
    spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.RETRACT,
            superseded_revision_id=first_candidate.event_revision_id,
            evidence_source_record_ids=(uuid4(),),
            rationale="prove the promoted candidate is independently reversible",
        )
    )
    assert spine.hybrid_alpha(changed) < before


def test_retracting_regime_trigger_recomputes_active_regime(case):
    spine = _spine(case)
    stable, changed = case.locations[:2]
    results = _observe(spine, case, [stable, stable, stable, changed, changed])
    trigger = results[-1]
    changed_regime = trigger.active_regime
    assert changed_regime != "stable"

    revision = spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.RETRACT,
            superseded_revision_id=trigger.event_revision_id,
            evidence_source_record_ids=(uuid4(),),
            rationale="the evidence that completed regime confirmation was withdrawn",
        )
    )

    assert spine.active_regime == "stable"
    assert revision.old_regime == changed_regime
    assert revision.new_regime == "stable"
    first_candidate = results[3]
    replayed = spine._observed_events[first_candidate.event_revision_id]
    assert replayed.rls_sample.regime_id == "stable"
    assert spine.rls_regime_snapshot(changed_regime)["models"] == {}
    assert not spine.is_committed_revision(first_candidate.event_revision_id)
    assert spine.is_quarantined_revision(first_candidate.event_revision_id)
    assert spine.hybrid_alpha(changed) == pytest.approx(0.0)
    assert spine._habit.known_person_count(
        household_id=replayed.evidence.metadata.household_id,
        person_id=case.owner_actor,
        object_instance_id=case.object_instance_id,
        location_id=changed,
    ) == pytest.approx(0.0)


def test_revising_unrelated_history_preserves_pending_confirmation_progress(case):
    spine = _spine(case)
    stable, changed = case.locations[:2]
    results = _observe(spine, case, [stable, stable, stable, changed])
    pending = results[-1]
    assert spine.is_quarantined_revision(pending.event_revision_id)
    baseline = results[0]
    corrected_baseline = uuid4()

    spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.CORRECT,
            superseded_revision_id=baseline.event_revision_id,
            corrected_revision_id=corrected_baseline,
            corrected_location_id=stable,
            corrected_owner_mass=baseline.actor_posterior[case.owner_actor],
            evidence_source_record_ids=(uuid4(),),
            rationale="revise an unrelated baseline event while a candidate is pending",
        )
    )
    confirmed = spine.process_transition(
        _transition(case, location=changed, index=spine.observation_count)
    )

    assert confirmed.decision.conclusion is HabitStateConclusion.HABIT_CHANGE
    assert spine.is_committed_revision(pending.event_revision_id)


def test_demoted_candidate_can_be_confirmed_again_without_duplicate_hybrid_revision(case):
    spine = _spine(case)
    stable, changed = case.locations[:2]
    results = _observe(spine, case, [stable, stable, stable, changed, changed])
    candidate = results[3]
    spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.RETRACT,
            superseded_revision_id=results[4].event_revision_id,
            evidence_source_record_ids=(uuid4(),),
            rationale="withdraw confirmation and demote the first candidate",
        )
    )

    reconfirmed = spine.process_transition(
        _transition(case, location=changed, index=spine.observation_count)
    )

    assert reconfirmed.decision.conclusion is HabitStateConclusion.HABIT_CHANGE
    assert spine.is_committed_revision(candidate.event_revision_id)
    assert not spine.is_quarantined_revision(candidate.event_revision_id)
    assert spine.hybrid_alpha(changed) > 0.0


def test_parent_requarantine_recursively_invalidates_multilevel_derived_lineage(case):
    spine = _spine(case)
    stable, changed = case.locations[:2]
    results = _observe(spine, case, [stable, stable, stable, changed, changed])
    parent = results[3]
    parent_proxy = replace(parent, belief_snapshot=spine.current_snapshot)
    parent_transition = _transition(case, location=changed, index=3)

    feedback_a, binding_a, likelihood_a = _search_feedback_bundle(
        case=case,
        spine=spine,
        transition=parent_transition,
        original=parent_proxy,
        outcome_distribution={
            RobotActionOutcome.SUCCESS: 0.99,
            RobotActionOutcome.UNKNOWN: 0.01,
        },
        present_likelihood={
            RobotActionOutcome.SUCCESS: 0.99,
            RobotActionOutcome.UNKNOWN: 0.01,
        },
        absent_likelihood={
            RobotActionOutcome.SUCCESS: 0.01,
            RobotActionOutcome.UNKNOWN: 0.99,
        },
    )
    spine.process_execution_feedback(
        feedback=feedback_a,
        binding=binding_a,
        likelihood_model=likelihood_a,
    )
    reinforce_a = spine.derived_revision_ids(parent.event_revision_id)[0]
    proxy_a = replace(
        parent_proxy,
        event_revision_id=reinforce_a,
        belief_snapshot=spine.current_snapshot,
    )
    feedback_b, binding_b, likelihood_b = _search_feedback_bundle(
        case=case,
        spine=spine,
        transition=parent_transition,
        original=proxy_a,
        outcome_distribution={
            RobotActionOutcome.SUCCESS: 0.99,
            RobotActionOutcome.UNKNOWN: 0.01,
        },
        present_likelihood={
            RobotActionOutcome.SUCCESS: 0.99,
            RobotActionOutcome.UNKNOWN: 0.01,
        },
        absent_likelihood={
            RobotActionOutcome.SUCCESS: 0.01,
            RobotActionOutcome.UNKNOWN: 0.99,
        },
    )
    spine.process_execution_feedback(
        feedback=feedback_b,
        binding=binding_b,
        likelihood_model=likelihood_b,
    )
    reinforce_b = spine.derived_revision_ids(reinforce_a)[0]
    assert spine._committed_events[reinforce_a].derived_from_revision_id == (
        parent.event_revision_id
    )
    assert spine._committed_events[reinforce_b].derived_from_revision_id == reinforce_a

    spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.RETRACT,
            superseded_revision_id=results[4].event_revision_id,
            evidence_source_record_ids=(uuid4(),),
            rationale="demote the parent observation back to quarantine",
        )
    )

    assert spine.is_quarantined_revision(parent.event_revision_id)
    assert not spine.is_committed_revision(reinforce_a)
    assert not spine.is_committed_revision(reinforce_b)
    assert spine.derived_revision_lifecycle(reinforce_a) == ("suspended_parent_quarantined")
    assert spine.derived_revision_lifecycle(reinforce_b) == ("suspended_parent_quarantined")
    assert spine.derived_reactivation_policy == "require_fresh_feedback"
    for revision_id in (reinforce_a, reinforce_b):
        archived = spine._derived_event_archive[revision_id]
        assert not spine._hybrid_loop.ledger.live_promoted_records_for_revision(
            archived.hybrid_revision_id or revision_id
        )

    fresh_habit = spine._new_habit_model()
    fresh_regimes = spine._new_regime_bank()
    for event in sorted(
        spine._committed_events.values(),
        key=lambda item: (item.evidence.event_time, str(item.revision_id)),
    ):
        fresh_habit.update_audited(
            event.evidence,
            weight_multiplier=event.propensity_weight,
        )
        fresh_regimes.update(event.rls_sample, spine._embeddings)
    assert spine._habit.canonical_state_hash() == fresh_habit.canonical_state_hash()
    for regime_id in {event.rls_sample.regime_id for event in spine._committed_events.values()}:
        assert spine.rls_regime_snapshot(regime_id) == fresh_regimes.regime_snapshot(regime_id)

    reconfirmed = spine.process_transition(
        _transition(case, location=changed, index=spine.observation_count)
    )
    assert spine.is_committed_revision(parent.event_revision_id)
    assert not spine.is_committed_revision(reinforce_a)
    assert not spine.is_committed_revision(reinforce_b)

    spine.loop_config = replace(
        spine.loop_config,
        derived_reactivation_policy=(DerivedEvidenceReactivationPolicy.RESTORE_PRIOR_DERIVED),
    )
    spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.RETRACT,
            superseded_revision_id=reconfirmed.event_revision_id,
            evidence_source_record_ids=(uuid4(),),
            rationale="exercise the explicit opt-in derived restoration policy",
        )
    )
    spine.process_transition(_transition(case, location=changed, index=spine.observation_count))
    assert spine.is_committed_revision(reinforce_a)
    assert spine.is_committed_revision(reinforce_b)
    assert spine._committed_events[reinforce_b].derived_from_revision_id == reinforce_a


def test_restore_policy_does_not_revive_explicitly_retracted_derived(case):
    spine = _spine(case)
    spine.loop_config = replace(
        spine.loop_config,
        derived_reactivation_policy=(DerivedEvidenceReactivationPolicy.RESTORE_PRIOR_DERIVED),
    )
    location = case.locations[0]
    transition = _transition(case, location=location, index=0)
    parent = spine.process_transition(transition)
    derived = _reinforce_once(
        case=case,
        spine=spine,
        transition=transition,
        source_result=parent,
    )

    spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.RETRACT,
            superseded_revision_id=derived,
            evidence_source_record_ids=(uuid4(),),
            rationale="explicitly retract derived evidence",
        )
    )

    assert not spine.is_committed_revision(derived)
    assert spine.derived_revision_lifecycle(derived) == "tombstoned_explicit_retract"


def test_corrected_derived_is_only_surviving_revision_under_restore_policy(case):
    spine = _spine(case)
    spine.loop_config = replace(
        spine.loop_config,
        derived_reactivation_policy=(DerivedEvidenceReactivationPolicy.RESTORE_PRIOR_DERIVED),
    )
    location = case.locations[0]
    transition = _transition(case, location=location, index=0)
    parent = spine.process_transition(transition)
    derived = _reinforce_once(
        case=case,
        spine=spine,
        transition=transition,
        source_result=parent,
    )
    corrected = uuid4()
    owner_mass = spine.committed_actor_posterior(derived)[case.owner_actor]

    spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.CORRECT,
            superseded_revision_id=derived,
            corrected_revision_id=corrected,
            corrected_location_id=location,
            corrected_owner_mass=owner_mass,
            evidence_source_record_ids=(uuid4(),),
            rationale="correct the derived evidence revision",
        )
    )

    assert not spine.is_committed_revision(derived)
    assert spine.is_committed_revision(corrected)
    assert spine.derived_revision_lifecycle(derived) == "tombstoned_corrected"
    assert spine.derived_revision_lifecycle(corrected) == "active"


def test_explicitly_retracting_middle_derived_permanently_invalidates_descendants(case):
    spine = _spine(case)
    spine.loop_config = replace(
        spine.loop_config,
        derived_reactivation_policy=(DerivedEvidenceReactivationPolicy.RESTORE_PRIOR_DERIVED),
    )
    location = case.locations[0]
    transition = _transition(case, location=location, index=0)
    parent = spine.process_transition(transition)
    derived_a = _reinforce_once(
        case=case,
        spine=spine,
        transition=transition,
        source_result=parent,
    )
    derived_a_result = replace(
        parent,
        event_revision_id=derived_a,
        belief_snapshot=spine.current_snapshot,
    )
    derived_b = _reinforce_once(
        case=case,
        spine=spine,
        transition=transition,
        source_result=derived_a_result,
    )

    spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.RETRACT,
            superseded_revision_id=derived_a,
            evidence_source_record_ids=(uuid4(),),
            rationale="explicitly retract the middle derived node",
        )
    )

    assert not spine.is_committed_revision(derived_a)
    assert not spine.is_committed_revision(derived_b)
    assert spine.derived_revision_lifecycle(derived_a) == ("tombstoned_explicit_retract")
    assert spine.derived_revision_lifecycle(derived_b) == ("tombstoned_ancestor_invalidated")


def test_revision_classification_matches_fresh_replay_from_observation_log(case):
    stable, changed = case.locations[:2]
    revised = _spine(case)
    results = _observe(revised, case, [stable, stable, stable, changed, changed])
    revised.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.RETRACT,
            superseded_revision_id=results[-1].event_revision_id,
            evidence_source_record_ids=(uuid4(),),
            rationale="remove the sole confirmation sample",
        )
    )
    fresh = _spine(case)
    _observe(fresh, case, [stable, stable, stable, changed])

    def classification(spine):
        committed = sorted(
            (event.evidence.event_time, event.location_id)
            for event in spine._committed_events.values()
            if event.regime_frame is not None
        )
        quarantined = sorted(
            (event.evidence.event_time, event.location_id) for event in spine._quarantined_events
        )
        return committed, quarantined

    assert classification(revised) == classification(fresh)


def test_retracting_one_trigger_does_not_force_stable_when_later_evidence_confirms(case):
    spine = _spine(case)
    stable, changed = case.locations[:2]
    results = _observe(
        spine,
        case,
        [stable, stable, stable, changed, changed, changed, changed],
    )
    withdrawn_trigger = results[4]

    revision = spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.RETRACT,
            superseded_revision_id=withdrawn_trigger.event_revision_id,
            evidence_source_record_ids=(uuid4(),),
            rationale="later surviving evidence must still confirm the changed regime",
        )
    )

    assert spine.active_regime != "stable"
    assert revision.new_regime == spine.active_regime


def test_old_regime_rls_sufficient_statistics_survive_switch(case):
    spine = _spine(case)
    stable, changed = case.locations[:2]
    _observe(spine, case, [stable, stable, stable])
    stable_snapshot = spine.rls_regime_snapshot("stable")

    _observe(spine, case, [changed, changed])

    assert spine.active_regime != "stable"
    assert spine.rls_regime_snapshot("stable") == stable_snapshot


def test_return_to_old_habit_reactivates_old_regime(case):
    spine = _spine(case)
    stable, changed = case.locations[:2]
    results = _observe(
        spine,
        case,
        [stable, stable, stable, changed, changed, stable, stable],
    )

    assert results[4].active_regime != "stable"
    assert results[-1].decision.conclusion is HabitStateConclusion.HABIT_CHANGE
    assert results[-1].decision.ccrr_conclusion == "reactivate"
    assert results[-1].active_regime == "stable"
    assert spine.rls_regime_snapshot("stable")["models"]


def test_project_two_retraction_removes_matching_hybrid_statistics(case):
    spine = _spine(case)
    location = case.locations[0]
    result = _observe(spine, case, [location])[0]
    before = spine.hybrid_alpha(location)

    revision = spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.RETRACT,
            superseded_revision_id=result.event_revision_id,
            evidence_source_record_ids=(uuid4(),),
            rationale="project-two actor attribution was corrected",
        )
    )

    assert revision.statistic_operations == (PrototypeStatisticOperation.RETRACT,)
    assert spine.hybrid_alpha(location) < before
    assert revision.map_version > result.belief_snapshot.map_version


def test_event_correction_republishes_map_and_suggestion_uses_new_snapshot(case):
    spine = _spine(case)
    old_location, corrected_location = case.locations[:2]
    original = _observe(spine, case, [old_location])[0]

    revision = spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.CORRECT,
            superseded_revision_id=original.event_revision_id,
            corrected_revision_id=uuid4(),
            corrected_location_id=corrected_location,
            corrected_owner_mass=0.9,
            evidence_source_record_ids=(uuid4(),),
            rationale="project-two revised the destination hypothesis",
        )
    )

    assert revision.statistic_operations == (PrototypeStatisticOperation.CORRECT,)
    assert revision.map_version > original.belief_snapshot.map_version
    assert revision.suggested_location_id == corrected_location
    assert revision.snapshot_id == spine.current_snapshot.snapshot_id


def test_event_correction_updates_dirichlet_owner_mass(case):
    spine = _spine(case)
    old_location, corrected_location = case.locations[:2]
    original = _observe(spine, case, [old_location])[0]
    corrected_revision_id = uuid4()

    spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.CORRECT,
            superseded_revision_id=original.event_revision_id,
            corrected_revision_id=corrected_revision_id,
            corrected_location_id=corrected_location,
            corrected_owner_mass=0.1,
            evidence_source_record_ids=(uuid4(),),
            rationale="project-two reduced owner responsibility",
        )
    )

    posterior = spine.committed_actor_posterior(corrected_revision_id)
    assert posterior[case.owner_actor] == pytest.approx(0.1)
    assert sum(posterior.values()) == pytest.approx(1.0)


def test_corrected_owner_mass_zero_removes_all_owner_statistics(case):
    spine = _spine(case)
    old_location, corrected_location = case.locations[:2]
    original = _observe(spine, case, [old_location])[0]
    corrected_revision_id = uuid4()

    spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.CORRECT,
            superseded_revision_id=original.event_revision_id,
            corrected_revision_id=corrected_revision_id,
            corrected_location_id=corrected_location,
            corrected_owner_mass=0.0,
            evidence_source_record_ids=(uuid4(),),
            rationale="project-two attributed the event entirely away from the owner",
        )
    )

    assert spine.committed_actor_posterior(corrected_revision_id)[case.owner_actor] == 0.0
    assert spine.hybrid_alpha(old_location) == pytest.approx(0.0)
    assert spine.hybrid_alpha(corrected_location) == pytest.approx(0.0)


def test_ipw_owner_weight_is_identical_across_all_three_models(case):
    spine = _spine(case)
    location = case.locations[0]
    result = _observe(spine, case, [location])[0]
    semantics = spine.committed_weight_semantics(result.event_revision_id)
    expected = result.propensity.applied_weight * result.actor_posterior[case.owner_actor]

    assert semantics["dirichlet_owner_weight"] == pytest.approx(expected)
    assert semantics["rls_owner_weight"] == pytest.approx(expected)
    assert semantics["hybrid_owner_weight"] == pytest.approx(expected)
    assert spine.hybrid_alpha(location) == pytest.approx(expected)


def test_habit_signal_contains_dirichlet_surprise_and_rls_residual(case):
    spine = _spine(case)
    familiar, unlikely = case.locations[:2]
    result = _observe(spine, case, [familiar, familiar, familiar, unlikely])[-1]
    event = spine._observed_events[result.event_revision_id]

    assert event.dirichlet_predictive_surprise > 0.0
    assert event.rls_residual > 0.0
    assert event.regime_frame is not None
    assert event.regime_frame.signals[ChangeCause.HABIT] >= (
        spine.loop_config.dirichlet_surprise_weight * event.dirichlet_predictive_surprise
    )
    assert event.regime_frame.signals[ChangeCause.HABIT] >= (
        spine.loop_config.rls_residual_weight * event.rls_residual
    )


def test_normalized_dirichlet_surprise_is_comparable_across_location_class_counts(case):
    assert len(case.locations) >= 4
    small = CorePrototypeSpine(
        owner_key=case.owner_actor,
        object_instance_id=case.object_instance_id,
        locations=case.locations[:2],
        authorization_scope_id=uuid4(),
    )
    large = CorePrototypeSpine(
        owner_key=case.owner_actor,
        object_instance_id=case.object_instance_id,
        locations=case.locations[:4],
        authorization_scope_id=uuid4(),
    )
    small_result = small.process_transition(_transition(case, location=case.locations[0], index=0))
    large_result = large.process_transition(_transition(case, location=case.locations[0], index=0))

    small_surprise = small._observed_events[
        small_result.event_revision_id
    ].dirichlet_predictive_surprise
    large_surprise = large._observed_events[
        large_result.event_revision_id
    ].dirichlet_predictive_surprise
    assert small_surprise == pytest.approx(large_surprise)
    assert 0.0 <= small_surprise <= 1.0


def test_public_probability_records_reject_values_outside_unit_interval(case):
    spine = _spine(case)
    result = _observe(spine, case, [case.locations[0]])[0]
    with pytest.raises(ValueError, match=r"change_probability.*\[0, 1\]"):
        replace(result.decision, change_probability=1.01)
    with pytest.raises(ValueError, match=r"actor_posterior.*\[0, 1\]"):
        replace(result, actor_posterior={case.owner_actor: -0.01})
    with pytest.raises(ValueError, match=r"reported_slip_probability.*\[0, 1\]"):
        LocationTransitionEvidence(
            feedback_record_id=uuid4(),
            location_id=case.locations[0],
            reported_action_success_probability=0.5,
            reported_slip_probability=float("nan"),
            candidate=TransitionCandidate.UNRESOLVED,
        )


def test_project_one_stat_request_atomically_revises_all_three_models(case):
    spine = _spine(case)
    location = case.locations[0]
    original = _observe(spine, case, [location])[0]
    corrected_revision_id = uuid4()
    request = ProjectOneStatRequest(
        kind=ProjectOneRequestKind.CORRECT,
        superseded_revision_id=original.event_revision_id,
        corrected_revision_id=corrected_revision_id,
        event_hypothesis_id=original.event_history.hypothesis_set_id,
        owner_key=case.owner_actor,
        object_instance_id=case.object_instance_id,
        location_id=location,
        owner_mass_before=original.actor_posterior[case.owner_actor],
        owner_mass_after=0.2,
        owner_mass_delta=0.2 - original.actor_posterior[case.owner_actor],
        source_feedback_record_id=uuid4(),
    )

    assert apply_project_one_request(request, spine) is True
    weights = spine.committed_weight_semantics(corrected_revision_id)
    expected = 0.2 * original.propensity.applied_weight
    assert weights == pytest.approx(
        {
            "dirichlet_owner_weight": expected,
            "rls_owner_weight": expected,
            "hybrid_owner_weight": expected,
        }
    )
    assert spine.hybrid_alpha(location) == pytest.approx(expected)
    household_id = spine._committed_events[corrected_revision_id].evidence.metadata.household_id
    assert spine._habit.known_person_count(
        household_id=household_id,
        person_id=case.owner_actor,
        object_instance_id=case.object_instance_id,
        location_id=location,
    ) == pytest.approx(expected)
    committed = spine._committed_events[corrected_revision_id]
    assert committed.rls_sample.gate == pytest.approx(expected)
    assert spine._regimes.regime_snapshot(committed.rls_sample.regime_id)["models"]
    ledger = spine._hybrid_loop.ledger
    assert ledger.live_promoted_records_for_revision(corrected_revision_id)
    assert ledger._revision_parent[corrected_revision_id] == original.event_revision_id


@pytest.mark.parametrize("fault_stage", ["hybrid", "dirichlet", "rls"])
def test_project_one_stat_request_rolls_back_all_stores_on_stage_failure(
    case, monkeypatch, fault_stage
):
    spine = _spine(case)
    location = case.locations[0]
    original = _observe(spine, case, [location])[0]
    request = ProjectOneStatRequest(
        kind=ProjectOneRequestKind.CORRECT,
        superseded_revision_id=original.event_revision_id,
        corrected_revision_id=uuid4(),
        event_hypothesis_id=original.event_history.hypothesis_set_id,
        owner_key=case.owner_actor,
        object_instance_id=case.object_instance_id,
        location_id=case.locations[1],
        owner_mass_before=original.actor_posterior[case.owner_actor],
        owner_mass_after=0.2,
        owner_mass_delta=0.2 - original.actor_posterior[case.owner_actor],
        source_feedback_record_id=uuid4(),
    )
    before_dirichlet = spine._habit.canonical_state_hash()
    before_rls = {
        regime: spine._regimes.regime_snapshot(regime)
        for regime in {event.rls_sample.regime_id for event in spine._committed_events.values()}
    }
    before_hybrid = spine._hybrid_loop.ledger.export_state().to_json()
    before_lineage = dict(spine._hybrid_loop.ledger._revision_parent)
    before_revisions = tuple(spine._committed_events)
    before_snapshot = spine.current_snapshot

    def inject(stage):
        if stage == fault_stage:
            raise RuntimeError(f"injected {stage} failure")

    monkeypatch.setattr(spine, "_revision_fault_hook", inject)
    with pytest.raises(RuntimeError, match=f"injected {fault_stage} failure"):
        apply_project_one_request(request, spine)

    assert spine._habit.canonical_state_hash() == before_dirichlet
    assert {regime: spine._regimes.regime_snapshot(regime) for regime in before_rls} == before_rls
    assert spine._hybrid_loop.ledger.export_state().to_json() == before_hybrid
    assert spine._hybrid_loop.ledger._revision_parent == before_lineage
    assert tuple(spine._committed_events) == before_revisions
    assert spine.current_snapshot == before_snapshot


@pytest.mark.parametrize("fault_stage", ["rls", "hybrid"])
def test_transition_failure_rolls_back_models_router_and_map(case, monkeypatch, fault_stage):
    spine = _spine(case)
    location = case.locations[0]
    _observe(spine, case, [location, location, location])
    before_dirichlet = spine._habit.canonical_state_hash()
    before_rls = spine.rls_regime_snapshot("stable")
    before_hybrid = spine._hybrid_loop.ledger.export_state().to_json()
    before_router_count = spine.observation_count
    before_snapshot = spine.current_snapshot
    before_revisions = tuple(spine._committed_events)

    def inject(stage):
        if stage == fault_stage:
            raise RuntimeError(f"injected transition {stage} failure")

    monkeypatch.setattr(spine, "_transition_fault_hook", inject)
    with pytest.raises(RuntimeError, match=f"injected transition {fault_stage} failure"):
        spine.process_transition(_transition(case, location=location, index=3))

    assert spine._habit.canonical_state_hash() == before_dirichlet
    assert spine.rls_regime_snapshot("stable") == before_rls
    assert spine._hybrid_loop.ledger.export_state().to_json() == before_hybrid
    assert spine.observation_count == before_router_count
    assert spine.current_snapshot == before_snapshot
    assert tuple(spine._committed_events) == before_revisions


def test_forgetting_revision_matches_chronological_fresh_replay(case):
    spine = _spine_with_forgetting(case, 0.8)
    first, second = case.locations[:2]
    results = _observe(spine, case, [first, first, second])
    corrected_revision = uuid4()
    spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.CORRECT,
            superseded_revision_id=results[0].event_revision_id,
            corrected_revision_id=corrected_revision,
            corrected_location_id=second,
            corrected_owner_mass=0.4,
            evidence_source_record_ids=(uuid4(),),
            rationale="force an early revision after later samples were committed",
        )
    )

    fresh = spine._new_regime_bank()
    ordered = sorted(
        spine._committed_events.values(),
        key=lambda event: (event.evidence.event_time, str(event.revision_id)),
    )
    for event in ordered:
        fresh.update(event.rls_sample, spine._embeddings)
    assert spine.rls_regime_snapshot("stable") == fresh.regime_snapshot("stable")


def test_owner_mass_positive_zero_positive_is_fully_reversible(case):
    spine = _spine(case)
    location = case.locations[0]
    original = _observe(spine, case, [location])[0]
    zero_revision_id = uuid4()
    restored_revision_id = uuid4()

    assert (
        apply_project_one_request(
            ProjectOneStatRequest(
                kind=ProjectOneRequestKind.RETRACT,
                superseded_revision_id=original.event_revision_id,
                corrected_revision_id=zero_revision_id,
                event_hypothesis_id=original.event_history.hypothesis_set_id,
                owner_key=case.owner_actor,
                object_instance_id=case.object_instance_id,
                location_id=location,
                owner_mass_before=original.actor_posterior[case.owner_actor],
                owner_mass_after=0.0,
                owner_mass_delta=-original.actor_posterior[case.owner_actor],
                source_feedback_record_id=uuid4(),
            ),
            spine,
        )
        is True
    )
    assert spine.hybrid_alpha(location) == pytest.approx(0.0)
    assert spine.committed_weight_semantics(zero_revision_id) == pytest.approx(
        {
            "dirichlet_owner_weight": 0.0,
            "rls_owner_weight": 0.0,
            "hybrid_owner_weight": 0.0,
        }
    )

    assert (
        apply_project_one_request(
            ProjectOneStatRequest(
                kind=ProjectOneRequestKind.REINFORCE,
                superseded_revision_id=zero_revision_id,
                corrected_revision_id=restored_revision_id,
                event_hypothesis_id=original.event_history.hypothesis_set_id,
                owner_key=case.owner_actor,
                object_instance_id=case.object_instance_id,
                location_id=location,
                owner_mass_before=0.0,
                owner_mass_after=0.6,
                owner_mass_delta=0.6,
                source_feedback_record_id=uuid4(),
            ),
            spine,
        )
        is True
    )
    expected = 0.6 * original.propensity.applied_weight
    assert spine.committed_weight_semantics(restored_revision_id) == pytest.approx(
        {
            "dirichlet_owner_weight": expected,
            "rls_owner_weight": expected,
            "hybrid_owner_weight": expected,
        }
    )
    assert spine.hybrid_alpha(location) == pytest.approx(expected)


def test_single_search_failure_is_likelihood_evidence_not_zero_truth(case):
    spine = _spine(case)
    location = case.locations[0]
    transition = _transition(case, location=location, index=0)
    original = spine.process_transition(transition)
    before_alpha = spine.hybrid_alpha(location)
    feedback, binding, likelihood = _search_feedback_bundle(
        case=case,
        spine=spine,
        transition=transition,
        original=original,
        outcome_distribution={
            RobotActionOutcome.NOT_FOUND: 0.9,
            RobotActionOutcome.UNKNOWN: 0.1,
        },
        present_likelihood={
            RobotActionOutcome.NOT_FOUND: 0.2,
            RobotActionOutcome.UNKNOWN: 0.8,
        },
        absent_likelihood={
            RobotActionOutcome.NOT_FOUND: 0.8,
            RobotActionOutcome.UNKNOWN: 0.2,
        },
    )

    decision = spine.process_execution_feedback(
        feedback=feedback,
        binding=binding,
        likelihood_model=likelihood,
    )

    assert decision.statistic_operations == (PrototypeStatisticOperation.QUARANTINE,)
    assert 0.0 < decision.feedback_posterior_probability < 0.8
    assert spine.hybrid_alpha(location) == before_alpha
    assert decision.map_version == original.belief_snapshot.map_version


def test_default_success_feedback_reinforces_and_retraction_cascades(case):
    spine = _spine(case)
    location = case.locations[0]
    transition = _transition(case, location=location, index=0)
    original = spine.process_transition(transition)
    before = spine.hybrid_alpha(location)
    feedback, binding, likelihood = _search_feedback_bundle(
        case=case,
        spine=spine,
        transition=transition,
        original=original,
        outcome_distribution={
            RobotActionOutcome.SUCCESS: 0.9,
            RobotActionOutcome.UNKNOWN: 0.1,
        },
        present_likelihood={
            RobotActionOutcome.SUCCESS: 0.99,
            RobotActionOutcome.UNKNOWN: 0.01,
        },
        absent_likelihood={
            RobotActionOutcome.SUCCESS: 0.01,
            RobotActionOutcome.UNKNOWN: 0.99,
        },
    )

    reinforced = spine.process_execution_feedback(
        feedback=feedback,
        binding=binding,
        likelihood_model=likelihood,
    )
    derived = spine.derived_revision_ids(original.event_revision_id)

    assert reinforced.statistic_operations == (PrototypeStatisticOperation.REINFORCE,)
    assert spine.hybrid_alpha(location) > before
    assert len(derived) == 1
    reinforced_alpha = spine.hybrid_alpha(location)
    replay = spine.process_execution_feedback(
        feedback=feedback,
        binding=binding,
        likelihood_model=likelihood,
    )
    assert replay.statistic_operations == (PrototypeStatisticOperation.QUARANTINE,)
    assert spine.hybrid_alpha(location) == reinforced_alpha

    spine.apply_event_revision_outcome(
        EventRevisionOutcome(
            kind=EventRevisionKind.RETRACT,
            superseded_revision_id=original.event_revision_id,
            evidence_source_record_ids=(uuid4(),),
            rationale="project-two invalidated the source event",
        )
    )

    assert spine.hybrid_alpha(location) == pytest.approx(0.0)
    assert not spine.is_committed_revision(derived[0])


def test_failed_feedback_application_does_not_commit_idempotency_key(case):
    class FailOncePolicy:
        def __init__(self, revision_id):
            self.revision_id = revision_id
            self.calls = 0

        def interpret(self, *, feedback, projected):
            del feedback, projected
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("simulated policy/application failure")
            return FeedbackInterpretation(
                operation=PrototypeStatisticOperation.REINFORCE,
                evidence_strength=0.2,
                rationale="retry succeeds",
                target_revision_id=self.revision_id,
            )

    spine = _spine(case)
    location = case.locations[0]
    transition = _transition(case, location=location, index=0)
    original = spine.process_transition(transition)
    feedback, binding, likelihood = _search_feedback_bundle(
        case=case,
        spine=spine,
        transition=transition,
        original=original,
        outcome_distribution={
            RobotActionOutcome.SUCCESS: 0.9,
            RobotActionOutcome.UNKNOWN: 0.1,
        },
        present_likelihood={
            RobotActionOutcome.SUCCESS: 0.99,
            RobotActionOutcome.UNKNOWN: 0.01,
        },
        absent_likelihood={
            RobotActionOutcome.SUCCESS: 0.01,
            RobotActionOutcome.UNKNOWN: 0.99,
        },
    )
    policy = FailOncePolicy(original.event_revision_id)

    with pytest.raises(RuntimeError, match="simulated"):
        spine.process_execution_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood,
            policy=policy,
        )
    retried = spine.process_execution_feedback(
        feedback=feedback,
        binding=binding,
        likelihood_model=likelihood,
        policy=policy,
    )

    assert retried.statistic_operations == (PrototypeStatisticOperation.REINFORCE,)
    assert len(spine.derived_revision_ids(original.event_revision_id)) == 1


def test_feedback_revision_location_and_snapshot_binding_is_mandatory(case):
    spine = _spine(case)
    first_location, other_location = case.locations[:2]
    original_transition = _transition(case, location=first_location, index=0)
    original = spine.process_transition(original_transition)
    mismatched_transition = _transition(case, location=other_location, index=1)
    feedback, binding, likelihood = _search_feedback_bundle(
        case=case,
        spine=spine,
        transition=mismatched_transition,
        original=original,
        outcome_distribution={
            RobotActionOutcome.SUCCESS: 0.9,
            RobotActionOutcome.UNKNOWN: 0.1,
        },
        present_likelihood={
            RobotActionOutcome.SUCCESS: 0.99,
            RobotActionOutcome.UNKNOWN: 0.01,
        },
        absent_likelihood={
            RobotActionOutcome.SUCCESS: 0.01,
            RobotActionOutcome.UNKNOWN: 0.99,
        },
    )

    with pytest.raises(ValueError, match=r"revision.*location"):
        spine.process_execution_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood,
        )

    feedback, binding, likelihood = _search_feedback_bundle(
        case=case,
        spine=spine,
        transition=original_transition,
        original=original,
        outcome_distribution={
            RobotActionOutcome.SUCCESS: 0.9,
            RobotActionOutcome.UNKNOWN: 0.1,
        },
        present_likelihood={
            RobotActionOutcome.SUCCESS: 0.99,
            RobotActionOutcome.UNKNOWN: 0.01,
        },
        absent_likelihood={
            RobotActionOutcome.SUCCESS: 0.01,
            RobotActionOutcome.UNKNOWN: 0.99,
        },
        bound_snapshot_id=uuid4(),
    )
    with pytest.raises(ValueError, match=r"revision.*snapshot"):
        spine.process_execution_feedback(
            feedback=feedback,
            binding=binding,
            likelihood_model=likelihood,
        )
