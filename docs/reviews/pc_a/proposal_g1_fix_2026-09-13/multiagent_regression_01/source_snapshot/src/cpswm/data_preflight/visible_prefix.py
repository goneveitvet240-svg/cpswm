"""Causal projection of existing visible contracts, not a truth-to-feature adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from cpswm.contracts.base import require_aware
from cpswm.contracts.habit_learning import (
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    ObservationDetectionResult,
    ObservationOpportunityRecord,
    ObservationOutcome,
)
from cpswm.system.reproducibility import content_sha256


@dataclass(frozen=True)
class VisiblePrefix:
    """Only model_input goes to a method; provenance remains an audit-side object."""

    model_input_json: str
    provenance_json: str

    def model_input(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads(self.model_input_json)
        return result


def export_visible_prefix(
    opportunities: tuple[ObservationOpportunityRecord, ...],
    detections: tuple[ObservationDetectionResult, ...],
    *,
    received_at: Mapping[UUID, datetime],
    cutoff: datetime,
    actor_evidence: tuple[ActorResponsibilityEvidence, ...] = (),
) -> VisiblePrefix:
    """Use event time AND externally recorded arrival time, including pending results.

    The ingestion owner must supply truthful arrival times. This is not a source
    authentication boundary or authorization to expose simulator metadata. Seeds,
    whole-run IDs/digests, scenario labels and future support never enter features.
    """
    cutoff = require_aware(cutoff, "cutoff")
    # Revalidation detaches nested caller containers, including model_copy bypasses.
    ops = tuple(ObservationOpportunityRecord.model_validate(x.model_dump()) for x in opportunities)
    results = tuple(ObservationDetectionResult.model_validate(x.model_dump()) for x in detections)
    actors = tuple(
        ActorResponsibilityEvidence.model_validate(x.model_dump()) for x in actor_evidence
    )
    records: tuple[
        ObservationOpportunityRecord | ObservationDetectionResult | ActorResponsibilityEvidence, ...
    ] = (*ops, *results, *actors)
    ids = [x.metadata.record_id for x in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate record identity")
    arrivals = dict(received_at)
    if set(arrivals) != set(ids):
        raise ValueError("arrival journal must cover exactly the input records")
    arrivals = {key: require_aware(value, "received_at") for key, value in arrivals.items()}
    streams = {(x.metadata.household_id, x.metadata.session_id) for x in records}
    if len(streams) > 1:
        raise ValueError("mixed household/session stream")
    by_id = {x.metadata.record_id: x for x in ops}
    by_op = {}
    result: ObservationDetectionResult | None
    for result in results:
        op = by_id.get(result.observation_opportunity_id)
        if op is None or result.observation_opportunity_id in by_op:
            raise ValueError("orphan or repeated opportunity result")
        if not op.selected and result.outcome != ObservationOutcome.NOT_OBSERVED:
            raise ValueError("unselected opportunity cannot supply detection or negative evidence")
        event_time = result.detection_time or op.opportunity_time
        if event_time < op.opportunity_time or arrivals[result.metadata.record_id] < event_time:
            raise ValueError("result precedes its observation event")
        by_op[result.observation_opportunity_id] = result
    for op in ops:
        if arrivals[op.metadata.record_id] < op.opportunity_time:
            raise ValueError("opportunity received before it occurred")
    detection_by_id = {x.metadata.record_id: x for x in results}
    for actor in actors:
        result = detection_by_id.get(actor.source_detection_result_id)
        if (
            actor.evidence_track == ActorEvidenceTrack.ORACLE
            or result is None
            or result.detected_object_instance_id != actor.object_instance_id
            or result.detection_time is None
            or actor.evidence_time < result.detection_time
            or arrivals[actor.metadata.record_id] < actor.evidence_time
        ):
            raise ValueError("oracle, orphan, mismatched or temporally invalid actor evidence")
    visible = sorted(
        (
            x
            for x in ops
            if x.opportunity_time <= cutoff and arrivals[x.metadata.record_id] <= cutoff
        ),
        key=lambda x: (
            x.opportunity_time,
            arrivals[x.metadata.record_id],
            str(x.metadata.record_id),
        ),
    )
    rows: list[dict[str, Any]] = []
    provenance: list[dict[str, str]] = []
    for op in visible:
        # Existing visible fields only. Record metadata and evidence URIs are audit-only.
        fields = op.model_dump(mode="json", exclude={"metadata", "evidence_refs"})
        result = by_op.get(op.metadata.record_id)
        fields["result"] = None
        fields["actor_evidence"] = []
        included: list[Any] = [op]
        if result is not None and arrivals[result.metadata.record_id] <= cutoff:
            fields["result"] = result.model_dump(
                mode="json", exclude={"metadata", "evidence_refs", "observation_opportunity_id"}
            )
            included.append(result)
            for actor in sorted(actors, key=lambda x: (x.evidence_time, str(x.metadata.record_id))):
                if (
                    actor.source_detection_result_id == result.metadata.record_id
                    and arrivals[actor.metadata.record_id] <= cutoff
                ):
                    fields["actor_evidence"].append(
                        actor.model_dump(
                            mode="json",
                            exclude={"metadata", "evidence_refs", "source_detection_result_id"},
                        )
                    )
                    included.append(actor)
        rows.append(fields)
        provenance.extend(
            {
                "record_id": str(x.metadata.record_id),
                "content_sha256": content_sha256(x),
                "received_at": arrivals[x.metadata.record_id].isoformat(),
            }
            for x in included
        )
    payload = {
        "schema": "structure-two-visible-prefix@0.1",
        "cutoff": cutoff.isoformat(),
        "observations": rows,
    }
    return VisiblePrefix(
        json.dumps(payload, sort_keys=True, allow_nan=False),
        json.dumps(
            {"included_records": provenance, "feature_sha256": content_sha256(payload)},
            sort_keys=True,
            allow_nan=False,
        ),
    )
