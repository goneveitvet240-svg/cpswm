import pytest

from cpswm.contracts import (
    ActorResponsibilityEvidence,
    BeliefSnapshot,
    ExecutionFeedbackRecord,
    HardConstraintEvaluation,
    ObservationSafetyApproval,
    VerificationObservation,
    EventRecord,
    GroundedSearchResult,
    JointPosteriorRequest,
    MemoryReliabilityProjection,
    MemoryReliabilityRequest,
    ObservationLikelihoodModel,
    RelationAssertion,
    UserCorrectionEvent,
    WorldModelQuery,
)


@pytest.mark.parametrize(
    "model",
    [
        ActorResponsibilityEvidence,
        RelationAssertion,
        EventRecord,
        BeliefSnapshot,
        JointPosteriorRequest,
        GroundedSearchResult,
        ExecutionFeedbackRecord,
        HardConstraintEvaluation,
        ObservationSafetyApproval,
        VerificationObservation,
        MemoryReliabilityRequest,
        MemoryReliabilityProjection,
        ObservationLikelihoodModel,
        WorldModelQuery,
        UserCorrectionEvent,
    ],
)
def test_core_contract_exports_json_schema(model):
    schema = model.model_json_schema()
    assert schema["title"] == model.__name__
    assert schema["type"] == "object"
