from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from cpswm.system.structure_one_identity_commonsense import (
    UNKNOWN_OBJECT,
    IdentityCandidate,
    IdentityObservation,
    LearnedMetricBayesianIdentityBackend,
)
from cpswm.system.structure_one_learning_backends import (
    ControlledOnlineAdaptationConfig,
    OfflineToControlledOnlinePolicyPlanner,
    PolicyAction,
    PolicyState,
)
from cpswm.system.structure_one_selected_routes import (
    SELECTED_STRUCTURE_ONE_METHODS,
    DirichletRole,
    HabitMethod,
    HiddenEventInference,
    HiddenEventModel,
    HiddenEventRevision,
    IdentityEvidenceMethod,
    PolicyLearningMethod,
)


class _Encoder:
    model_version = "metric-test"

    def encode(self, payload):
        return payload


class _Catalog:
    def __init__(self, candidates):
        self._candidates = candidates

    def candidates_as_of(self, observation):
        return self._candidates


def test_selected_route_manifest_matches_user_choices() -> None:
    selected = SELECTED_STRUCTURE_ONE_METHODS
    assert selected.identity_evidence is IdentityEvidenceMethod.LEARNED_METRIC
    assert selected.hidden_event_model is HiddenEventModel.DBN_FACTOR_GRAPH
    assert selected.hidden_event_inference is HiddenEventInference.PARTICLE_FILTERING
    assert selected.hidden_event_revision is HiddenEventRevision.CHEH_ORRER
    assert selected.habit is HabitMethod.CF_BOCPD_RLS_ONLY
    assert selected.dirichlet_role is DirichletRole.DIAGNOSTIC_ONLY
    assert selected.policy_learning is PolicyLearningMethod.OFFLINE_PRETRAIN_CONTROLLED_ONLINE


def test_identity_backend_keeps_unknown_as_an_explicit_posterior_state() -> None:
    now = datetime.now(UTC)
    backend = LearnedMetricBayesianIdentityBackend(
        encoder=_Encoder(),
        catalog=_Catalog(
            (
                IdentityCandidate(
                    identity_id="cup-1",
                    reference_embedding=(-1.0, 0.0),
                    identity_prior=0.1,
                    transition_likelihood=0.1,
                    relation_likelihood=0.1,
                    valid_through=now,
                    evidence_record_ids=(uuid4(),),
                ),
            )
        ),
    )
    posterior = backend.resolve(
        IdentityObservation(
            observation_id=uuid4(),
            observed_at=now,
            payload=(1.0, 0.0),
            source_record_ids=(uuid4(),),
        )
    )
    assert posterior.selected_identity_id == UNKNOWN_OBJECT
    assert posterior.unknown_probability > posterior.identity_probabilities["cup-1"]


def test_identity_backend_rejects_future_catalog_evidence() -> None:
    now = datetime.now(UTC)
    backend = LearnedMetricBayesianIdentityBackend(
        encoder=_Encoder(),
        catalog=_Catalog(
            (
                IdentityCandidate(
                    identity_id="cup-1",
                    reference_embedding=(1.0, 0.0),
                    identity_prior=1.0,
                    transition_likelihood=1.0,
                    relation_likelihood=1.0,
                    valid_through=now + timedelta(seconds=1),
                    evidence_record_ids=(uuid4(),),
                ),
            )
        ),
    )
    with pytest.raises(ValueError, match="future evidence"):
        backend.resolve(
            IdentityObservation(
                observation_id=uuid4(),
                observed_at=now,
                payload=(1.0, 0.0),
                source_record_ids=(uuid4(),),
            )
        )


@dataclass
class _Policy:
    offline_pretrained = True
    model_version = "offline-test"
    updates: int = 0

    def action_logits(self, state, actions):
        return {action.action_id: float(index) for index, action in enumerate(actions)}

    def controlled_online_update(self, transition, *, max_probability_shift):
        self.updates += 1


class _StateEncoder:
    def encode(self, query, query_result):
        return PolicyState(
            partition_key=("h1", "subject-1", "cup-1"),
            features=(1.0,),
            candidate_actions=(
                PolicyAction("wait", "wait", {}, True),
                PolicyAction("ask", "ask_user", {}, True, True),
            ),
        )


def test_controlled_online_adaptation_requires_approval_and_confident_feedback() -> None:
    policy = _Policy()
    planner = OfflineToControlledOnlinePolicyPlanner(
        state_encoder=_StateEncoder(),
        policy=policy,
        config=ControlledOnlineAdaptationConfig(
            minimum_feedback_confidence=0.9,
            max_updates_per_partition=1,
        ),
    )
    decision = planner.plan(None, None)
    assert decision.requires_human_approval is True
    assert (
        planner.adapt_from_feedback(
            decision.decision_id,
            reward=1.0,
            feedback_confidence=1.0,
            human_approved=False,
        )
        is False
    )
    assert policy.updates == 0
