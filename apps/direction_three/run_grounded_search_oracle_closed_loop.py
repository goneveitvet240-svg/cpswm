"""Run the S3-1 M29-L0 oracle grounded-search closed loop."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

# Support direct execution from any working directory without an ambient
# PYTHONPATH.  Keep this bootstrap before importing the source package.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _PROJECT_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from cpswm.contracts import (  # noqa: E402
    ActionOutcomeLikelihoodModel,
    BaseRecordMetadata,
    CandidateKind,
    ChannelEvidence,
    CompiledSemanticQuery,
    EntityRef,
    EntityType,
    EvidenceChannel,
    EvidenceRef,
    ExecutionFeedbackRecord,
    JointCandidateEvidence,
    JointPosteriorRequest,
    ObservationActionCandidate,
    ObservationActionType,
    Pose3D,
    RobotActionOutcome,
    RobotActionType,
    SourceType,
    ValidTimeInterval,
    VerificationObservation,
    build_query_compiler_provenance,
)
from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog  # noqa: E402
from cpswm.world_model.grounded_search import (  # noqa: E402
    DirectionThreePipeline,
    GroundedTaskExecution,
    OracleActionOutcomeModelProvider,
    OracleGroundedCandidateRetriever,
    OracleGroundedTaskExecutor,
    OracleObservationActionProvider,
    OracleSemanticQueryCompiler,
    OracleVerificationObservationProvider,
)

HOUSEHOLD = UUID("00000000-0000-0000-0000-000000000101")
SESSION = UUID("00000000-0000-0000-0000-000000000102")
TRACE = UUID("00000000-0000-0000-0000-000000000103")
QUERY_SOURCE = UUID("00000000-0000-0000-0000-000000000104")
PHONE = UUID("00000000-0000-0000-0000-000000000201")
GLASSES = UUID("00000000-0000-0000-0000-000000000202")
UNKNOWN = UUID("00000000-0000-0000-0000-000000000299")
PHONE_LOCATION = UUID("00000000-0000-0000-0000-000000000301")
GLASSES_LOCATION = UUID("00000000-0000-0000-0000-000000000302")
OBSERVATION_ACTION = UUID("00000000-0000-0000-0000-000000000401")
OBSERVATION_OPPORTUNITY = UUID("00000000-0000-0000-0000-000000000402")
GRASP_ACTION = UUID("00000000-0000-0000-0000-000000000403")
RECORDED_AT = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)


def metadata(
    schema_name: str,
    source_type: SourceType,
    source_id: str,
) -> BaseRecordMetadata:
    return BaseRecordMetadata(
        schema_name=schema_name,
        schema_version="0.1.0",
        household_id=HOUSEHOLD,
        session_id=SESSION,
        recorded_time=RECORDED_AT,
        source_type=source_type,
        source_id=source_id,
        model_version="direction-three-oracle@0.1",
        trace_id=TRACE,
    )


def channel_evidence(likelihoods: tuple[float, ...]):
    return {
        channel: ChannelEvidence(
            likelihood_given_candidate=value,
            model_version=f"oracle-{channel.value}@0.1",
            calibration_domain="m29-l0-oracle-household",
        )
        for channel, value in zip(EvidenceChannel, likelihoods, strict=True)
    }


def main() -> None:
    query_utterance = "找我晚上经常放在床边用的那个东西"
    truth_query = CompiledSemanticQuery(
        utterance=query_utterance,
        category_candidates=("phone", "glasses", "cup"),
        relations=("used_by", "usually_located_at"),
        time_expression="night",
        soft_constraints=("bedside", "frequently_used"),
        compiler_model_version="m29-l0-oracle-compiler@0.1",
        input_evidence_refs=(
            EvidenceRef(
                evidence_type="oracle_query_utterance",
                source_record_id=QUERY_SOURCE,
            ),
        ),
        invocation_provenance=build_query_compiler_provenance(
            provider="oracle-fixture",
            model="m29-l0-oracle-compiler",
            version="0.1",
            temperature=0.0,
            prompt_template_version="m29-l0-oracle-query@0.1",
            prompt=query_utterance,
            input_evidence_refs=(QUERY_SOURCE,),
        ),
    )
    compiler = OracleSemanticQueryCompiler(truth_query)
    compiled_query = compiler.compile(truth_query.utterance)

    candidates = (
        JointCandidateEvidence(
            candidate_id=PHONE,
            kind=CandidateKind.OBJECT_INSTANCE,
            entity=EntityRef(entity_id=PHONE, entity_type=EntityType.OBJECT_INSTANCE),
            location_id=PHONE_LOCATION,
            prior_probability=0.45,
            channel_evidence=channel_evidence((0.91, 0.88, 0.82, 0.90, 0.93, 0.89)),
        ),
        JointCandidateEvidence(
            candidate_id=GLASSES,
            kind=CandidateKind.OBJECT_INSTANCE,
            entity=EntityRef(entity_id=GLASSES, entity_type=EntityType.OBJECT_INSTANCE),
            location_id=GLASSES_LOCATION,
            prior_probability=0.40,
            channel_evidence=channel_evidence((0.90, 0.87, 0.81, 0.89, 0.92, 0.88)),
        ),
        JointCandidateEvidence(
            candidate_id=UNKNOWN,
            kind=CandidateKind.UNKNOWN,
            prior_probability=0.15,
            channel_evidence=channel_evidence((0.20, 0.20, 0.20, 0.20, 0.20, 0.20)),
        ),
    )
    retriever = OracleGroundedCandidateRetriever(candidates)
    request = JointPosteriorRequest(
        metadata=metadata("cpswm.JointPosteriorRequest", SourceType.SIMULATION, "m29-l0-oracle"),
        compiled_query=compiled_query,
        candidates=tuple(retriever.retrieve(compiled_query)),
        resolution_threshold=0.70,
        ambiguity_margin=0.12,
    )

    observation_action = ObservationActionCandidate(
        action_id=OBSERVATION_ACTION,
        action_type=ObservationActionType.MOVE_VIEWPOINT,
        label="oracle second RGB-D bedside viewpoint",
        viewpoint_pose=Pose3D(
            frame_id="map",
            x=0.5,
            y=0.0,
            z=1.0,
            qx=0.0,
            qy=0.0,
            qz=0.0,
            qw=1.0,
        ),
        observation_likelihood_model_id="m29-l0-oracle-rgbd@0.1",
        calibration_domain="m29-l0-oracle-household",
        outcome_likelihoods={
            "phone_features": {PHONE: 0.90, GLASSES: 0.10, UNKNOWN: 0.20},
            "other_features": {PHONE: 0.10, GLASSES: 0.90, UNKNOWN: 0.80},
        },
        motion_cost=0.01,
        time_cost=0.01,
        interruption_cost=0.0,
        privacy_cost=0.0,
        safety_cost=0.0,
    )
    realized_observation = VerificationObservation(
        metadata=metadata(
            "cpswm.VerificationObservation",
            SourceType.SIMULATION,
            "m29-l0-oracle-rgbd",
        ),
        action_id=OBSERVATION_ACTION,
        observation_opportunity_id=OBSERVATION_OPPORTUNITY,
        outcome_label="phone_features",
        evidence_channel=EvidenceChannel.VISUAL,
        candidate_likelihoods={PHONE: 0.90, GLASSES: 0.10, UNKNOWN: 0.20},
        observation_likelihood_model_id="m29-l0-oracle-rgbd@0.1",
        calibration_domain="m29-l0-oracle-household",
    )
    success_feedback = ExecutionFeedbackRecord(
        metadata=metadata("cpswm.ExecutionFeedbackRecord", SourceType.ACTION, "oracle-gripper"),
        action_id=GRASP_ACTION,
        action_type=RobotActionType.GRASP,
        target_entity=EntityRef(entity_id=PHONE, entity_type=EntityType.OBJECT_INSTANCE),
        attempted_location_id=PHONE_LOCATION,
        valid_time=ValidTimeInterval(start=RECORDED_AT, end=RECORDED_AT + timedelta(seconds=10)),
        outcome_distribution={RobotActionOutcome.SUCCESS: 1.0},
        task_goal_satisfied_probability=1.0,
    )
    execution = GroundedTaskExecution(
        selected_target_candidate_id=PHONE,
        target_entity=success_feedback.target_entity,
        target_location_id=PHONE_LOCATION,
        executed_action_id=GRASP_ACTION,
        executed_action_type=RobotActionType.GRASP,
        feedback_records=(success_feedback,),
    )

    canonical_log = AppendOnlyTransactionLog()
    trace = DirectionThreePipeline().run_closed_loop(
        request,
        action_provider=OracleObservationActionProvider((observation_action,)),
        observation_provider=OracleVerificationObservationProvider(
            {OBSERVATION_ACTION: realized_observation}
        ),
        task_executor=OracleGroundedTaskExecutor({PHONE: execution}),
        outcome_model_provider=OracleActionOutcomeModelProvider(
            {
                RobotActionType.GRASP: ActionOutcomeLikelihoodModel(
                    action_type=RobotActionType.GRASP,
                    p_outcome_given_target_present={RobotActionOutcome.SUCCESS: 1.0},
                    p_outcome_given_target_absent={RobotActionOutcome.SUCCESS: 1.0},
                    calibration_domain="m29-l0-oracle-household",
                    model_version="m29-l0-oracle-grasp-outcome@0.1",
                )
            }
        ),
        canonical_log=canonical_log,
    )
    payload = {
        "maturity": "s3-1-oracle-closed-loop-baseline",
        "resolution_sequence": [
            cycle.search_result.resolution_status.value for cycle in trace.cycles
        ],
        "selected_observation_action_id": str(trace.cycles[0].observation_plan.selected_action_id),
        "selected_target_candidate_id": str(trace.selected_target_candidate_id),
        "termination_reason": trace.termination_reason,
        "canonical_commit_sequences": {
            "observations": trace.observation_commit_sequences,
            "execution_feedback": trace.feedback_commit_sequences,
        },
        "canonical_log_watermark": canonical_log.latest_watermark().global_commit_seq,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
