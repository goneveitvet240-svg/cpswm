"""OAM-PHM §5.1 module-boundary invariants, expressed as property tests.

The eight invariants (from
``docs/research/opportunistic-observation-personalized-memory-substructure-v0.2.md``):

1. M13–M15 are canonical records; M16 is a rebuildable derived projection.
2. M17 outputs are priors, not current facts.
3. M18 cannot modify M16 directly; it must append candidates via M14/M15.
4. M19 never deletes historical evidence; lifecycle actions are auditable.
5. M21/LLM only generates queries or candidates, never world-model writes.
6. M24 information value and M16 negative evidence use the same
   ``ObservationLikelihoodModel``.
7. M27 writes back execution results but never self-declares a true fact.
8. ``gt.*`` is only readable by M29/M31/M32 and an explicit oracle adapter.

These tests intentionally target *properties* of randomly generated contract
instances rather than single directed examples.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import hypothesis.strategies as st
import pytest
from hypothesis import assume, given, settings
from pydantic import ValidationError

from cpswm.contracts.assertions import (
    AssertionStatus,
    EntityRelationObject,
    RelationAssertion,
    RelationPredicate,
)
from cpswm.contracts.base import (
    BaseRecordMetadata,
    EntityRef,
    EntityType,
    EvidenceRef,
    EvidenceScoredMixin,
    InputWatermark,
    PosteriorMixin,
    PrivacyScope,
    SourceType,
    TemporalValidityMixin,
    ValidTimeInterval,
)
from cpswm.contracts.beliefs import (
    BeliefHypothesis,
    BeliefSnapshot,
    BeliefVariableType,
)
from cpswm.contracts.grounded_search import (
    CompiledSemanticQuery,
    EvidenceChannel,
    ExecutionFeedbackRecord,
    RobotActionOutcome,
    RobotActionType,
    VerificationObservation,
)
from cpswm.contracts.habit_learning import (
    HabitEvidenceSource,
    HabitLearningEvidence,
    ObservationOpportunityRecord,
)
from cpswm.contracts.likelihoods import ObservationLikelihoodModel
from cpswm_gt.models import (
    GTEntity,
    GTRelationAssertion,
    GroundTruthWorldState,
)

# --------------------------------------------------------------------------- #
# Shared generators                                                           #
# --------------------------------------------------------------------------- #

_probability = st.floats(0.0, 1.0, allow_nan=False)

aware_datetimes = st.datetimes(
    min_value=datetime(2020, 1, 1, tzinfo=timezone.utc),
    max_value=datetime(2030, 1, 1, tzinfo=timezone.utc),
)


@st.composite
def valid_times(draw):
    start = draw(aware_datetimes)
    delta = draw(
        st.timedeltas(min_value=timedelta(seconds=1), max_value=timedelta(days=365))
    )
    return ValidTimeInterval(start=start, end=start + delta)


@st.composite
def metadata(draw, allowed=None):
    source_types = allowed if allowed is not None else list(SourceType)
    return BaseRecordMetadata(
        schema_name="oam.phm",
        schema_version="0.1.0",
        household_id=draw(st.uuids()),
        session_id=draw(st.uuids()),
        source_type=draw(st.sampled_from(source_types)),
        source_id=draw(st.text(min_size=1, max_size=16)),
        privacy_scope=PrivacyScope.HOUSEHOLD,
    )


@st.composite
def entity_refs(draw):
    return EntityRef(
        entity_id=draw(st.uuids()),
        entity_type=draw(st.sampled_from(list(EntityType))),
    )


@st.composite
def relation_assertions(draw):
    """Random valid M13 relation assertion (append-only, never a fact)."""
    return RelationAssertion(
        metadata=draw(metadata()),
        temporal=TemporalValidityMixin(
            valid_time=draw(valid_times()), observed_time=draw(aware_datetimes)
        ),
        subject=draw(entity_refs()),
        predicate=draw(st.sampled_from(list(RelationPredicate))),
        object=EntityRelationObject(entity=draw(entity_refs())),
        evidence=EvidenceScoredMixin(evidence_reliability=draw(_probability)),
        status=draw(st.sampled_from(list(AssertionStatus))),
    )


@st.composite
def belief_snapshots(draw):
    """Random valid M16 derived belief snapshot with a normalized posterior."""
    group = "oam.phm.snapshot"
    p = draw(st.floats(0.0, 1.0, allow_nan=False, exclude_min=True, exclude_max=True))
    return BeliefSnapshot(
        metadata=draw(metadata()),
        projection_version=draw(st.integers(1, 10_000)),
        input_watermark=InputWatermark(
            global_commit_seq=draw(st.integers(0, 10_000)),
            transaction_id=draw(st.uuids()),
            recorded_at=draw(aware_datetimes),
        ),
        valid_time=draw(valid_times()),
        belief_key=draw(st.text(min_size=1, max_size=16)),
        variable_type=draw(st.sampled_from(list(BeliefVariableType))),
        hypotheses=(
            BeliefHypothesis(
                label="candidate_a",
                state={"value": "a"},
                posterior=PosteriorMixin(
                    posterior_probability=p, normalization_group=group
                ),
            ),
            BeliefHypothesis(
                label="candidate_b",
                state={"value": "b"},
                posterior=PosteriorMixin(
                    posterior_probability=1.0 - p, normalization_group=group
                ),
            ),
        ),
        inference_model_version=draw(st.text(min_size=1, max_size=16)),
    )


@st.composite
def likelihood_models(draw):
    """Random valid ObservationLikelihoodModel shared by M24 and M16."""
    q = draw(st.floats(0.0, 1.0, allow_nan=False))
    return ObservationLikelihoodModel(
        metadata=draw(metadata()),
        request_id=draw(st.uuids()),
        p_visible_given_state=draw(_probability),
        p_detect_given_visible_state=draw(_probability),
        p_false_positive=draw(_probability),
        p_observation_given_state_action={"present": q, "absent": 1.0 - q},
        calibration_domain=draw(st.text(min_size=1, max_size=16)),
        validity_scope=draw(valid_times()),
        geometry_model_version=draw(st.text(min_size=1, max_size=16)),
        perception_model_version=draw(st.text(min_size=1, max_size=16)),
    )


@st.composite
def habit_evidence(draw):
    """Random valid M17 habit-learning evidence proposal."""
    source = draw(st.sampled_from(list(HabitEvidenceSource)))
    allowed = {
        HabitEvidenceSource.DIRECT_OBSERVATION: [
            SourceType.SENSOR,
            SourceType.MODEL,
            SourceType.SIMULATION,
        ],
        HabitEvidenceSource.USER_REPORT: [SourceType.USER, SourceType.IMPORT],
        HabitEvidenceSource.INFERRED_EVENT: [SourceType.INFERENCE],
        HabitEvidenceSource.MODEL_PREDICTION: [SourceType.MODEL],
    }[source]
    return HabitLearningEvidence(
        metadata=draw(metadata(allowed=allowed)),
        object_instance_id=draw(st.uuids()),
        location_id=draw(st.uuids()),
        event_time=draw(aware_datetimes),
        context_key=draw(st.text(min_size=1, max_size=16)),
        actor_posterior={"actor": 1.0},
        evidence_source=source,
        source_record_ids=(draw(st.uuids()),),
    )


@st.composite
def execution_feedback(draw):
    """Random valid M27 execution feedback with an uncertain outcome."""
    p_success = draw(
        st.floats(0.0, 1.0, allow_nan=False, exclude_min=True, exclude_max=True)
    )
    return ExecutionFeedbackRecord(
        metadata=draw(metadata(allowed=[SourceType.ACTION])),
        action_id=draw(st.uuids()),
        action_type=RobotActionType.NAVIGATE,
        valid_time=draw(valid_times()),
        outcome_distribution={
            RobotActionOutcome.SUCCESS: p_success,
            RobotActionOutcome.PARTIAL: 1.0 - p_success,
        },
        task_goal_satisfied_probability=draw(
            st.floats(0.0, p_success, allow_nan=False)
        ),
    )


@st.composite
def verification_observations(draw):
    """Random valid M24/M16-shared verification observation."""
    return VerificationObservation(
        metadata=draw(
            metadata(
                allowed=[
                    SourceType.SENSOR,
                    SourceType.MODEL,
                    SourceType.USER,
                    SourceType.SIMULATION,
                ]
            )
        ),
        action_id=draw(st.uuids()),
        observation_opportunity_id=draw(st.uuids()),
        outcome_label=draw(st.text(min_size=1, max_size=16)),
        evidence_channel=draw(st.sampled_from(list(EvidenceChannel))),
        candidate_likelihoods={
            draw(st.uuids()): draw(
                st.floats(0.0, 1.0, allow_nan=False, exclude_min=True, exclude_max=True)
            ),
            draw(st.uuids()): 0.5,
        },
        observation_likelihood_model_id=draw(st.text(min_size=1, max_size=16)),
        calibration_domain=draw(st.text(min_size=1, max_size=16)),
    )


@st.composite
def gt_states(draw):
    """Random valid ground-truth world state (gt.* package)."""
    entities = [
        GTEntity(entity_type=draw(st.sampled_from(list(EntityType))))
        for _ in range(draw(st.integers(1, 5)))
    ]
    entity_ids = [item.gt_entity_id for item in entities]
    relations = tuple(
        GTRelationAssertion(
            subject_gt_entity_id=draw(st.sampled_from(entity_ids)),
            predicate=draw(st.text(min_size=1, max_size=16)),
            object_gt_entity_id=draw(st.sampled_from(entity_ids)),
            valid_time=draw(valid_times()),
        )
        for _ in range(draw(st.integers(0, 4)))
    )
    return GroundTruthWorldState(
        simulation_run_id=draw(st.uuids()),
        simulation_time=draw(aware_datetimes),
        entities=tuple(entities),
        relations=relations,
    )


SETTINGS = settings(max_examples=40, deadline=None)


# --------------------------------------------------------------------------- #
# Invariant 1: M13 canonical records, M16 rebuildable projection              #
# --------------------------------------------------------------------------- #

@given(relation_assertions())
@SETTINGS
def test_inv1_m13_relation_assertions_are_frozen_canonical_records(assertion):
    assert assertion.model_config["frozen"] is True
    assert assertion.status in set(AssertionStatus)
    # A canonical record is not a derived posterior.
    assert "posterior_probability" not in RelationAssertion.model_fields


@given(belief_snapshots())
@SETTINGS
def test_inv1_m16_snapshots_are_normalized_versioned_and_rebuildable(snapshot):
    assert snapshot.model_config["frozen"] is True
    assert snapshot.projection_version >= 1
    assert snapshot.input_watermark is not None
    assert len({h.posterior.normalization_group for h in snapshot.hypotheses}) == 1
    assert (
        abs(sum(h.posterior.posterior_probability for h in snapshot.hypotheses) - 1.0)
        < 1e-6
    )


# --------------------------------------------------------------------------- #
# Invariant 2: M17 outputs are priors, not current facts                      #
# --------------------------------------------------------------------------- #

@given(habit_evidence())
@SETTINGS
def test_inv2_m17_model_predictions_cannot_train_themselves(evidence):
    if evidence.evidence_source == HabitEvidenceSource.MODEL_PREDICTION:
        assert evidence.effective_training_weight == 0.0
    else:
        assert evidence.effective_training_weight == evidence.proposed_training_weight


# --------------------------------------------------------------------------- #
# Invariant 3: M18 cannot modify M16 in place                                 #
# --------------------------------------------------------------------------- #

@given(belief_snapshots())
@SETTINGS
def test_inv3_m16_is_immutable_so_attribution_must_append_new_records(snapshot):
    assert snapshot.model_config["frozen"] is True
    # Versioned lineage: any revision is a new projection, not a mutation.
    assert snapshot.projection_version >= 1


# --------------------------------------------------------------------------- #
# Invariant 4: M19 never deletes history                                        #
# --------------------------------------------------------------------------- #

@given(relation_assertions())
@SETTINGS
def test_inv4_retraction_is_a_status_never_a_deletion(assertion):
    # Forgetting is expressed as a status on a new append-only record.
    assert {AssertionStatus.RETRACTED, AssertionStatus.SUPERSEDED, AssertionStatus.CONTRADICTED} <= set(
        AssertionStatus
    )
    # Every assertion retains its own identity and temporal grounding.
    assert assertion.metadata.record_id is not None
    assert assertion.temporal is not None


# --------------------------------------------------------------------------- #
# Invariant 5: M21/LLM only generates queries, never world-model writes       #
# --------------------------------------------------------------------------- #

@given(st.text(min_size=1, max_size=40), st.text(min_size=1, max_size=16))
@SETTINGS
def test_inv5_m21_compiled_queries_are_not_world_model_records(
    utterance, compiler_version
):
    query = CompiledSemanticQuery(
        utterance=utterance, compiler_model_version=compiler_version
    )
    assert "metadata" not in CompiledSemanticQuery.model_fields
    assert "source_type" not in CompiledSemanticQuery.model_fields
    assert "valid_time" not in CompiledSemanticQuery.model_fields


# --------------------------------------------------------------------------- #
# Invariant 6: M24 and M16 share one ObservationLikelihoodModel               #
# --------------------------------------------------------------------------- #

@given(likelihood_models())
@SETTINGS
def test_inv6_shared_likelihood_model_is_normalized_and_decomposable(model):
    assert abs(sum(model.p_observation_given_state_action.values()) - 1.0) < 1e-6
    assert (
        abs(
            model.p_detect_given_state_action
            - model.p_visible_given_state * model.p_detect_given_visible_state
        )
        < 1e-12
    )
    if model.label_confusion_distribution:
        assert abs(sum(model.label_confusion_distribution.values()) - 1.0) < 1e-6


@given(verification_observations())
@SETTINGS
def test_inv6_verification_observations_carry_the_shared_likelihood_model_id(obs):
    assert obs.observation_likelihood_model_id
    assert obs.metadata.source_type in {
        SourceType.SENSOR,
        SourceType.MODEL,
        SourceType.USER,
        SourceType.SIMULATION,
    }


# --------------------------------------------------------------------------- #
# Invariant 7: M27 writes back results but never self-declares a fact         #
# --------------------------------------------------------------------------- #

@given(execution_feedback())
@SETTINGS
def test_inv7_m27_feedback_is_action_scoped_uncertain_and_never_factual(feedback):
    assert feedback.metadata.source_type == SourceType.ACTION
    assert abs(sum(feedback.outcome_distribution.values()) - 1.0) < 1e-6
    assert feedback.task_goal_satisfied_probability <= feedback.outcome_distribution.get(
        RobotActionOutcome.SUCCESS, 0.0
    )
    assert "posterior_probability" not in ExecutionFeedbackRecord.model_fields


# --------------------------------------------------------------------------- #
# Invariant 8: gt.* only readable by M29/M31/M32 and the oracle adapter       #
# --------------------------------------------------------------------------- #

@given(gt_states())
@SETTINGS
def test_inv8_gt_world_state_is_referentially_closed(state):
    entity_ids = {item.gt_entity_id for item in state.entities}
    for relation in state.relations:
        assert relation.subject_gt_entity_id in entity_ids
        if relation.object_gt_entity_id is not None:
            assert relation.object_gt_entity_id in entity_ids
    for event in state.events:
        assert set(event.participant_gt_entity_ids.values()).issubset(entity_ids)


@given(gt_states(), st.uuids(), valid_times())
@SETTINGS
def test_inv8_unknown_gt_reference_is_rejected(state, foreign_id, valid_time):
    entity_ids = {item.gt_entity_id for item in state.entities}
    assume(foreign_id not in entity_ids)
    with pytest.raises(ValidationError):
        GroundTruthWorldState(
            simulation_run_id=state.simulation_run_id,
            simulation_time=state.simulation_time,
            entities=state.entities,
            relations=(
                GTRelationAssertion(
                    subject_gt_entity_id=foreign_id,
                    predicate="located_at",
                    literal_value="x",
                    valid_time=valid_time,
                ),
            ),
        )


def test_inv8_robot_visible_simulation_records_cannot_carry_privileged_refs():
    """Robot-visible (simulation) records must not smuggle gt references."""
    sim_metadata = BaseRecordMetadata(
        schema_name="oam.phm",
        schema_version="0.1.0",
        household_id=uuid4(),
        session_id=uuid4(),
        source_type=SourceType.SIMULATION,
        source_id="sim",
    )
    with pytest.raises(ValidationError):
        ObservationOpportunityRecord(
            metadata=sim_metadata,
            observation_action_id=uuid4(),
            opportunity_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
            selected=True,
            selection_probability=0.5,
            p_visible_given_state=0.8,
            p_detect_given_visible=0.9,
            likelihood_model_id="lm",
            evidence_refs=(EvidenceRef(evidence_type="gt", source_record_id=uuid4()),),
        )
