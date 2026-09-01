from __future__ import annotations

from cpswm.contracts import ReplayContractCompatibility
from cpswm.system.evaluation_operations.project_one_dataset import (
    ProjectOneEvidenceDatasetRecord,
    ProjectOneEvidenceStream,
)
from cpswm.system.evaluation_operations.project_one_methods import (
    FormalProjectOneRuntimeAdapter,
    PersistenceMethod,
)
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    _FullProjectTwoMethod,
)
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)


def test_d0_raw_fixture_reaches_both_structure_runtimes_through_unified_evidence():
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=4
    ).build()
    episode = dataset.episodes[0]
    step = next(item for item in episode.steps if item.after is not None)
    evidence = step.unified_evidence
    assert evidence is not None
    assert episode.contract_compatibility is ReplayContractCompatibility.FULL_REPLAY_CONTRACT

    structure_two = _FullProjectTwoMethod(episode, owner_threshold=0.5)
    structure_two.observe(step)
    assert structure_two.formal_evidence_records_consumed == 1

    formal_record = ProjectOneEvidenceDatasetRecord(
        stream_id=str(episode.session_id),
        event_id=str(step.step_id),
        subject_id=episode.owner_actor_key,
        context_key="d0-runtime-bridge",
        context_value=1.0,
        evidence=evidence,
    )
    formal_stream = ProjectOneEvidenceStream(
        stream_id=formal_record.stream_id, records=(formal_record,)
    )
    location = evidence.detected_location_key
    assert location is not None
    actor = max(
        (key for key in evidence.actor_posterior if key != "unknown_actor"),
        key=evidence.actor_posterior.__getitem__,
    )
    method = PersistenceMethod(tuple(evidence.location_posterior))
    structure_one = FormalProjectOneRuntimeAdapter(method, method_id=method.name)
    result = structure_one.observe(
        formal_stream.records[0],
        actor_id=actor,
        observed_location=location,
        projection_policy="explicit-argmax-d0-development-only",
    )
    assert result.prediction.event_id == str(step.step_id)
    assert result.downgrade_receipt.formal_evidence_record_id == str(evidence.metadata.record_id)
