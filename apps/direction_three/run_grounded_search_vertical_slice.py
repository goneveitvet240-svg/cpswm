"""Run the direction-three symbolic grounded-search vertical slice."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

# Make this file a genuine direct-run entry point.  Installed packages and
# ``python -m`` remain supported, while ``python apps/...py`` no longer relies
# on a caller-provided PYTHONPATH.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_ROOT = _PROJECT_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from cpswm.contracts import (
    BaseRecordMetadata,
    CandidateKind,
    ChannelEvidence,
    CompiledSemanticQuery,
    EntityRef,
    EntityType,
    EvidenceChannel,
    JointCandidateEvidence,
    JointPosteriorRequest,
    ObservationActionCandidate,
    ObservationActionType,
    Pose3D,
    SourceType,
)
from cpswm.world_model.grounded_search import DirectionThreePipeline


HOUSEHOLD = UUID("00000000-0000-0000-0000-000000000101")
SESSION = UUID("00000000-0000-0000-0000-000000000102")
PHONE = UUID("00000000-0000-0000-0000-000000000201")
GLASSES = UUID("00000000-0000-0000-0000-000000000202")
UNKNOWN = UUID("00000000-0000-0000-0000-000000000299")
TRACE = UUID("00000000-0000-0000-0000-000000000103")
REQUEST_RECORD = UUID("00000000-0000-0000-0000-000000000104")
QUERY = UUID("00000000-0000-0000-0000-000000000105")
OBSERVATION_ACTION = UUID("00000000-0000-0000-0000-000000000401")


def channel_evidence(likelihoods: tuple[float, ...]):
    return {
        channel: ChannelEvidence(
            likelihood_given_candidate=value,
            model_version=f"symbolic-{channel.value}@0.1",
            calibration_domain="direction-three-symbolic-demo",
        )
        for channel, value in zip(EvidenceChannel, likelihoods, strict=True)
    }


def main() -> None:
    metadata = BaseRecordMetadata(
        record_id=REQUEST_RECORD,
        schema_name="cpswm.JointPosteriorRequest",
        schema_version="0.1.0",
        household_id=HOUSEHOLD,
        session_id=SESSION,
        recorded_time=datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
        source_type=SourceType.MODEL,
        source_id="direction-three-demo",
        model_version="log-opinion-pool@0.1",
        trace_id=TRACE,
    )
    compiled_query = CompiledSemanticQuery(
        query_id=QUERY,
        utterance="找我晚上经常放在床边用的那个东西",
        category_candidates=("phone", "glasses", "cup"),
        relations=("used_by", "usually_located_at"),
        time_expression="night",
        soft_constraints=("bedside", "frequently_used"),
        compiler_model_version="structured-llm-symbolic@0.1",
    )
    candidates = (
        JointCandidateEvidence(
            candidate_id=PHONE,
            kind=CandidateKind.OBJECT_INSTANCE,
            entity=EntityRef(entity_id=PHONE, entity_type=EntityType.OBJECT_INSTANCE),
            location_id=UUID("00000000-0000-0000-0000-000000000301"),
            prior_probability=0.45,
            channel_evidence=channel_evidence((0.91, 0.88, 0.82, 0.90, 0.93, 0.89)),
        ),
        JointCandidateEvidence(
            candidate_id=GLASSES,
            kind=CandidateKind.OBJECT_INSTANCE,
            entity=EntityRef(entity_id=GLASSES, entity_type=EntityType.OBJECT_INSTANCE),
            location_id=UUID("00000000-0000-0000-0000-000000000302"),
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
    request = JointPosteriorRequest(
        metadata=metadata,
        compiled_query=compiled_query,
        candidates=candidates,
        resolution_threshold=0.70,
        ambiguity_margin=0.12,
    )
    action = ObservationActionCandidate(
        action_id=OBSERVATION_ACTION,
        action_type=ObservationActionType.MOVE_VIEWPOINT,
        label="inspect bedside from a second RGB-D viewpoint",
        observation_likelihood_model_id="symbolic-rgbd-observation@0.1",
        calibration_domain="direction-three-symbolic-demo",
        viewpoint_pose=Pose3D(
            frame_id="map", x=0.5, y=0.0, z=1.0, qx=0.0, qy=0.0, qz=0.0, qw=1.0
        ),
        outcome_likelihoods={
            "phone_features": {PHONE: 0.9, GLASSES: 0.1, UNKNOWN: 0.2},
            "other_features": {PHONE: 0.1, GLASSES: 0.9, UNKNOWN: 0.8},
        },
        motion_cost=0.01,
        time_cost=0.01,
        interruption_cost=0.0,
        privacy_cost=0.0,
        safety_cost=0.0,
    )
    cycle = DirectionThreePipeline().decide(request, (action,))
    payload = {
        "search_result": cycle.search_result.model_dump(mode="json"),
        "observation_plan": (
            None
            if cycle.observation_plan is None
            else cycle.observation_plan.model_dump(mode="json")
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
