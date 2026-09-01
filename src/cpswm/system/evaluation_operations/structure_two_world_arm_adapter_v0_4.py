"""Official v0.4 adapter from frozen world rollouts to Gate-B arm traces.

The v0.2 world generator already owns observation missingness, actor ambiguity,
identity noise, and open-world events.  This adapter therefore does not apply
the legacy six-family visible-stream transforms a second time.  The one frozen
``NeighborFamily`` below supplies only the embodied cost quantities required by
the CARE decision policy; its legacy perturbation fields are inert.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from cpswm.contracts import (
    ActorEvidenceTrack,
    ActorResponsibilityEvidence,
    BaseRecordMetadata,
    EventMechanism,
    ObservationDetectionResult,
    ObservationOpportunityRecord,
    ObservationOutcome,
    OcclusionState,
    ProjectTwoDataMaturity,
    ProjectTwoDatasetSplit,
    ProjectTwoEvaluatorStepTruth,
    ProjectTwoEvaluatorTruthEnvelope,
    ProjectTwoReplayDatasetManifest,
    ProjectTwoReplayEpisode,
    ProjectTwoReplayManifestEntry,
    ProjectTwoReplayStep,
    ReplayContractCompatibility,
    ReplayFieldAvailability,
    SourceType,
    ValidTimeInterval,
)
from cpswm.system.evaluation_operations import structure_two_sequential_gate as sequential
from cpswm.system.evaluation_operations import structure_two_strongest_neighbor_gate as neighbor
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    _AMGOpenWorldMethod,
    _CountMethod,
    _FullProjectTwoMethod,
    _FullRerunMethod,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (
    StructureTwoWorld,
    StructureTwoWorldRollout,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-world-arm-adapter@0.4"
DATASET_VERSION = "structure-two-world-arm-replay@0.4"
SOURCE_BUNDLE_PROTOCOL = "structure-two-world-arm-producer-source-bundle@0.4"
ANCHOR_TIME = datetime(2026, 1, 1, tzinfo=UTC)

EXPECTED_ARMS = (
    "corrected_amg",
    "o_star_matched",
    "sequential_no_consolidation",
    "active_dreaming_matched",
    "auto_dreamer_matched",
    "trustmem_matched",
    "brainctl_matched",
    "care_no_action_regret",
    "care_wm",
    "full_rerun",
)

# These parameters were selected by the already archived matched-neighbor gate.
# They are reused as fixed diagnostic settings; Gate B does not score efficacy.
ARM_PARAMETERS: Mapping[str, Any] = {
    "corrected_amg": 0.35,
    "o_star_matched": 0.75,
    "sequential_no_consolidation": "responsive",
    "active_dreaming_matched": 0.60,
    "auto_dreamer_matched": 0.04,
    "trustmem_matched": 0.80,
    "brainctl_matched": 0.75,
    "care_no_action_regret": 0.85,
    "care_wm": 1.25,
    "full_rerun": 0.30,
}

# Unit-cost diagnostic environment.  The v0.4 world has no consequence-cost
# variable, so Gate B must not inherit a post-hoc legacy family assignment.
DIAGNOSTIC_FAMILY = neighbor.NeighborFamily(
    family_id="v0_4_unit_cost_distinguishability",
    family_role="gate_b_distinguishability_only",
    guest_window=(0, 0),
    abrupt_day=10_000,
    recurrence_day=10_001,
    observation_coverage=1.0,
    unknown_event_days=(),
    actor_ambiguity_mix=0.0,
    identity_confidence_scale=1.0,
    feedback_flip_rate=0.0,
    decoy_days=(),
    actual_action_cost=1.0,
    predicted_action_cost=1.0,
    verification_cost=0.5,
    repair_cost=0.5,
    physical_verification_reliability=0.90,
)
MAX_PHYSICAL_VERIFICATIONS_PER_ROLLOUT = 4
GATE_B_MIN_PAIRWISE_PREDICTION_DISAGREEMENT_RATE = 0.01
GATE_B_MIN_EPISODE_FRACTION_WITH_MULTIPLE_ARM_TRAJECTORIES = 0.20


@dataclass(frozen=True, slots=True)
class ProducerSourceBundle:
    protocol: str
    files: tuple[tuple[str, str], ...]
    content_sha256: str


def compute_producer_source_bundle(repository_root: Path) -> ProducerSourceBundle:
    """Hash CPSWM sources plus the v0.4 producer and custodian verifier.

    Freezing the whole package is intentionally stricter than listing a hand
    selected import closure: a transitive method dependency cannot change while
    leaving the adapter hash looking unchanged.
    """

    sources = sorted((repository_root / "src/cpswm").rglob("*.py"))
    app_sources = (
        repository_root / "apps/evaluation_runner/run_structure_two_world_arm_traces_v0_4.py",
        repository_root / "apps/evaluation_runner/attest_structure_two_arm_trace_v0_4.py",
    )
    if any(not path.is_file() for path in app_sources):
        raise FileNotFoundError("v0.4 arm-trace producer or custodian verifier is missing")
    sources.extend(app_sources)
    rows = tuple(
        (
            path.relative_to(repository_root).as_posix(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(set(sources))
    )
    payload = {"protocol": SOURCE_BUNDLE_PROTOCOL, "files": rows}
    return ProducerSourceBundle(
        protocol=SOURCE_BUNDLE_PROTOCOL,
        files=rows,
        content_sha256=content_sha256(payload),
    )


def _metadata(
    *,
    episode_id: UUID,
    household_id: UUID,
    session_id: UUID,
    trace_id: UUID,
    day: int,
    label: str,
    timestamp: datetime,
) -> BaseRecordMetadata:
    schema_name = (
        "cpswm.ObservationDetectionResult"
        if label
        in {
            "BeforeObservationDetectionResult",
            "AfterObservationDetectionResult",
        }
        else f"cpswm.{label}"
    )
    return BaseRecordMetadata(
        record_id=uuid5(episode_id, f"{label}:{day}"),
        schema_name=schema_name,
        schema_version="0.1.0",
        household_id=household_id,
        session_id=session_id,
        trace_id=trace_id,
        recorded_time=timestamp,
        source_type=SourceType.SIMULATION,
        source_id=PROTOCOL_ID,
        model_version=PROTOCOL_ID,
    )


def _actor_posterior(
    *,
    actors: tuple[str, ...],
    visible_actor_map: str,
    visible_owner_probability: float,
    owner_actor: str,
) -> dict[str, float]:
    """Expand the two generator-visible actor fields without reading truth."""

    owner_probability = min(1.0 - 1e-6, max(1e-6, visible_owner_probability))
    if visible_actor_map == owner_actor:
        residual = (1.0 - owner_probability) / (len(actors) - 1)
        return {actor: owner_probability if actor == owner_actor else residual for actor in actors}
    non_owner_others = tuple(
        actor for actor in actors if actor not in {owner_actor, visible_actor_map}
    )
    mapped_probability = 0.80 * (1.0 - owner_probability)
    residual = (1.0 - owner_probability - mapped_probability) / max(1, len(non_owner_others))
    return {
        actor: (
            owner_probability
            if actor == owner_actor
            else mapped_probability
            if actor == visible_actor_map
            else residual
        )
        for actor in actors
    }


def _mechanism(value: str) -> EventMechanism:
    return {
        "direct": EventMechanism.DIRECT_RELOCATION,
        "handoff": EventMechanism.HANDOFF_RELOCATION,
        "unknown": EventMechanism.UNKNOWN_MECHANISM,
    }[value]


def adapt_world_rollout(
    world: StructureTwoWorld,
    rollout: StructureTwoWorldRollout,
    *,
    split: ProjectTwoDatasetSplit = ProjectTwoDatasetSplit.VALIDATION,
) -> ProjectTwoReplayDataset:
    """Convert one world rollout while keeping evaluator truth firewalled."""

    if rollout.world_hash != world.world_hash or rollout.world_seed != world.world_seed:
        raise ValueError("rollout/world provenance mismatch")
    namespace = uuid5(NAMESPACE_URL, PROTOCOL_ID)
    episode_id = uuid5(namespace, f"episode:{rollout.rollout_id}")
    household_id = uuid5(namespace, f"household:{world.world_hash}")
    session_id = uuid5(episode_id, "session")
    trace_id = uuid5(episode_id, "trace")
    object_id = uuid5(namespace, f"object:{world.world_hash}")
    location_by_key = {
        key: uuid5(namespace, f"location:{world.world_hash}:{key}") for key in world.locations
    }
    actors = (world.owner_actor, *world.guest_actors, "unknown_actor")
    steps: list[ProjectTwoReplayStep] = []
    truths: dict[UUID, ProjectTwoEvaluatorStepTruth] = {}
    last_visible_location: UUID | None = None

    for item in rollout.steps:
        timestamp = ANCHOR_TIME + timedelta(days=item.day)
        step_id = uuid5(episode_id, f"day:{item.day}")
        opportunity_id = uuid5(episode_id, f"opportunity:{item.day}")
        opportunity = ObservationOpportunityRecord(
            metadata=_metadata(
                episode_id=episode_id,
                household_id=household_id,
                session_id=session_id,
                trace_id=trace_id,
                day=item.day,
                label="ObservationOpportunityRecord",
                timestamp=timestamp,
            ).model_copy(update={"record_id": opportunity_id}),
            observation_action_id=opportunity_id,
            opportunity_time=timestamp,
            selected=True,
            selection_probability=1.0,
            p_visible_given_state=1.0,
            p_detect_given_visible=1.0,
            likelihood_model_id="v0.4-unreported-state-conditioned-propensity",
        )
        before: ObservationDetectionResult | None = None
        after: ObservationDetectionResult | None = None
        actor_evidence: ActorResponsibilityEvidence | None = None
        source_location_id: UUID | None = None
        detection_confidence: float | None = None
        if item.observed and item.observed_location is not None:
            visible_location = location_by_key[item.observed_location]
            source_location_id = last_visible_location or visible_location
            before_timestamp = timestamp - timedelta(minutes=1)
            before = ObservationDetectionResult(
                metadata=_metadata(
                    episode_id=episode_id,
                    household_id=household_id,
                    session_id=session_id,
                    trace_id=trace_id,
                    day=item.day,
                    label="BeforeObservationDetectionResult",
                    timestamp=before_timestamp,
                ),
                observation_opportunity_id=opportunity_id,
                outcome=ObservationOutcome.DETECTED,
                detected_object_instance_id=object_id,
                detected_location_id=source_location_id,
                detection_time=before_timestamp,
            )
            if last_visible_location is not None and last_visible_location != visible_location:
                after = ObservationDetectionResult(
                    metadata=_metadata(
                        episode_id=episode_id,
                        household_id=household_id,
                        session_id=session_id,
                        trace_id=trace_id,
                        day=item.day,
                        label="AfterObservationDetectionResult",
                        timestamp=timestamp,
                    ),
                    observation_opportunity_id=opportunity_id,
                    outcome=ObservationOutcome.DETECTED,
                    detected_object_instance_id=object_id,
                    detected_location_id=visible_location,
                    detection_time=timestamp,
                )
            last_visible_location = visible_location
            detection_confidence = item.visible_identity_confidence
            if (
                after is not None
                and item.visible_actor_map is not None
                and item.visible_owner_probability is not None
            ):
                posterior = _actor_posterior(
                    actors=actors,
                    visible_actor_map=item.visible_actor_map,
                    visible_owner_probability=item.visible_owner_probability,
                    owner_actor=world.owner_actor,
                )
                actor_evidence = ActorResponsibilityEvidence(
                    metadata=_metadata(
                        episode_id=episode_id,
                        household_id=household_id,
                        session_id=session_id,
                        trace_id=trace_id,
                        day=item.day,
                        label="ActorResponsibilityEvidence",
                        timestamp=timestamp,
                    ),
                    source_detection_result_id=after.metadata.record_id,
                    object_instance_id=object_id,
                    evidence_time=timestamp,
                    actor_posterior=posterior,
                    reference_actor_prior={actor: 1.0 / len(actors) for actor in actors},
                    evidence_cluster_id=uuid5(episode_id, f"actor-cluster:{item.day}"),
                    evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE,
                    evidence_model_id="v0.4-visible-actor-map-expansion",
                )

        steps.append(
            ProjectTwoReplayStep(
                step_id=step_id,
                timestamp=timestamp,
                valid_time=ValidTimeInterval(start=timestamp, end=timestamp + timedelta(hours=1)),
                object_instance_id=object_id,
                object_category="household_object",
                before=before,
                after=after,
                source_location_id=source_location_id,
                attempted_location_id=None,
                observed_destination_location_id=None,
                visibility_probability=1.0 if item.observed else 0.0,
                occlusion_state=(OcclusionState.CLEAR if item.observed else OcclusionState.UNKNOWN),
                detection_confidence=detection_confidence,
                actor_evidence=actor_evidence,
                mechanism_evidence=None,
                ordered_role_evidence=None,
                execution_feedback=(),
                observation_opportunity=opportunity,
                action_opportunity=True,
                unavailable_fields=(
                    "state_conditioned_observation_propensity",
                    "visible_mechanism_evidence",
                    "visible_role_evidence",
                    "execution_feedback",
                ),
            )
        )
        truths[step_id] = ProjectTwoEvaluatorStepTruth(
            step_id=step_id,
            true_actor=item.true_actor,
            true_mechanism=_mechanism(item.true_mechanism),
            true_location=location_by_key[item.true_location],
            true_owner_habit_location=location_by_key[item.true_owner_habit_location],
            event_chain_truth=item.event_chain,
        )

    visible_payload = {
        "rollout_id": rollout.rollout_id,
        "world_hash": rollout.world_hash,
        "locations": rollout.locations,
        "owner_actor": rollout.owner_actor,
        "steps": [
            {
                "day": item.day,
                "context": item.context,
                "observed": item.observed,
                "observed_location": item.observed_location,
                "visible_actor_map": item.visible_actor_map,
                "visible_owner_probability": item.visible_owner_probability,
                "visible_identity_confidence": item.visible_identity_confidence,
            }
            for item in rollout.steps
        ],
    }
    source_hash = content_sha256(visible_payload)
    episode = ProjectTwoReplayEpisode(
        episode_id=episode_id,
        household_id=household_id,
        scene_id=f"world-{world.world_hash[:16]}",
        session_id=session_id,
        trace_id=trace_id,
        object_family="world-distributed-household-object",
        owner_actor_key=world.owner_actor,
        resident_actor_keys=actors,
        known_location_ids=tuple(location_by_key[key] for key in world.locations),
        dataset_version=DATASET_VERSION,
        source_uri=f"d0-world://{rollout.rollout_id}",
        source_hash=source_hash,
        provenance=(
            f"generated:{world.world_hash}",
            f"adapter:{PROTOCOL_ID}",
            "initial-visible-location-is-a-before-only-anchor-not-a-fabricated-transition",
            "latent-state-conditioned-observation-propensity-not-exposed",
        ),
        maturity=ProjectTwoDataMaturity.D0_SYNTHETIC_ORACLE,
        source_evidence_maturity=ProjectTwoDataMaturity.D0_SYNTHETIC_ORACLE,
        contract_compatibility=ReplayContractCompatibility.LEGACY_ADAPTED,
        split=split,
        steps=tuple(steps),
        field_availability={
            "actor_evidence": ReplayFieldAvailability.PARTIAL,
            "mechanism_evidence": ReplayFieldAvailability.UNAVAILABLE,
            "ordered_role_evidence": ReplayFieldAvailability.UNAVAILABLE,
            "state_conditioned_observation_propensity": ReplayFieldAvailability.UNAVAILABLE,
            "visible_mechanism_evidence": ReplayFieldAvailability.UNAVAILABLE,
            "visible_role_evidence": ReplayFieldAvailability.UNAVAILABLE,
            "execution_feedback": ReplayFieldAvailability.UNAVAILABLE,
        },
    )
    evaluator_payload = {
        "episode_id": episode_id,
        "dataset_version": DATASET_VERSION,
        "source_hash": source_hash,
        "truth_by_step": truths,
    }
    envelope = ProjectTwoEvaluatorTruthEnvelope(
        episode_id=episode_id,
        dataset_version=DATASET_VERSION,
        source_hash=source_hash,
        evaluator_content_hash=content_sha256(evaluator_payload),
        truth_by_step=truths,
    )
    entry = ProjectTwoReplayManifestEntry(
        episode_id=episode_id,
        household_id=household_id,
        scene_id=episode.scene_id,
        object_instance_id=object_id,
        object_family=episode.object_family,
        split=split,
        maturity=episode.maturity,
        source_evidence_maturity=episode.source_evidence_maturity,
        unified_evidence_record_ids=(),
        source_hash=source_hash,
        visible_content_hash=content_sha256(episode),
    )
    manifest = ProjectTwoReplayDatasetManifest(
        dataset_id=uuid5(namespace, f"dataset:{rollout.rollout_id}"),
        dataset_version=DATASET_VERSION,
        created_at=ANCHOR_TIME,
        entries=(entry,),
    )
    return ProjectTwoReplayDataset(
        manifest=manifest,
        episodes=(episode,),
        evaluator_store=(envelope,),
    )


def make_world_arm_state(
    dataset: ProjectTwoReplayDataset,
    episode: ProjectTwoReplayEpisode,
    arm_name: str,
) -> Any:
    """Instantiate one fixed Gate-B arm without legacy family perturbations."""

    if arm_name not in EXPECTED_ARMS:
        raise ValueError(f"arm is outside the frozen v0.4 set: {arm_name}")
    arm = neighbor.NeighborArm(arm_name)
    parameter = ARM_PARAMETERS[arm_name]
    if arm is neighbor.NeighborArm.CORRECTED_AMG:
        state: Any = _AMGOpenWorldMethod(episode, mode="amg", parameter=float(parameter))
        state.adapter_receipt = {
            "source": "Damen-Hogg AMG",
            "fidelity": "reduced_proxy_not_independently_verified_external_reproduction",
        }
        return neighbor._CorrelatedEvidenceQuarantineState(state)
    if arm is neighbor.NeighborArm.O_STAR_MATCHED:
        state = _CountMethod(episode, mode="o_star", parameter=float(parameter))
        state.adapter_receipt = {
            "source": "O-STaR",
            "fidelity": "reduced_proxy_not_faithful_external_reproduction",
        }
        return neighbor._CorrelatedEvidenceQuarantineState(state)
    if arm is neighbor.NeighborArm.NO_CONSOLIDATION:
        base = _FullProjectTwoMethod(
            episode,
            owner_threshold=0.4,
            action_readout=sequential._action_readout(),
        )
        state = sequential._SequentialMultiAxisActionState(
            base,
            episode,
            profile=str(parameter),
            consolidation=False,
        )
        state = sequential._CIAVState(
            state,
            dataset,
            episode,
            enabled=True,
            cost_multiplier=1.0,
        )
        return neighbor._CorrelatedEvidenceQuarantineState(state)
    if arm is neighbor.NeighborArm.FULL_RERUN:
        state = _FullRerunMethod(
            episode,
            mode="frequency",
            parameter=float(parameter),
        )
        state.adapter_receipt = {
            "source": "full rerun control",
            "fidelity": "v0.4-world-visible control",
        }
        return neighbor._CorrelatedEvidenceQuarantineState(state)

    base = _FullProjectTwoMethod(
        episode,
        owner_threshold=0.4,
        action_readout=sequential._action_readout(),
    )
    state = neighbor._NeighborMemoryState(
        base,
        episode,
        dataset,
        family=DIAGNOSTIC_FAMILY,
        arm=arm,
        parameter=parameter,
        max_physical_verifications=MAX_PHYSICAL_VERIFICATIONS_PER_ROLLOUT,
    )
    return neighbor._CorrelatedEvidenceQuarantineState(state)


def produce_arm_prediction_rows(
    rollouts: Sequence[tuple[StructureTwoWorld, StructureTwoWorldRollout]],
    *,
    arms: Sequence[str] = EXPECTED_ARMS,
) -> dict[str, tuple[tuple[str, tuple[str, ...]], ...]]:
    """Run a frozen arm subset over one ordered world-rollout sequence."""

    selected = tuple(str(arm) for arm in arms)
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("arm prediction request must be non-empty and unique")
    if any(arm not in EXPECTED_ARMS for arm in selected):
        raise ValueError("arm prediction request contains an arm outside the frozen set")
    rows: dict[str, list[tuple[str, tuple[str, ...]]]] = {arm: [] for arm in selected}
    for world, rollout in rollouts:
        dataset = adapt_world_rollout(world, rollout)
        episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
        for arm in selected:
            state = make_world_arm_state(dataset, episode, arm)
            emitted: list[str] = []
            for step in episode.steps:
                state.observe(step)
                verification_count_before = int(getattr(state, "verification_count", 0))
                prediction = state.predict()
                verification_count_after = int(getattr(state, "verification_count", 0))
                if verification_count_after < verification_count_before or (
                    verification_count_after - verification_count_before > 1
                ):
                    raise ValueError("arm verification counter changed by an invalid amount")
                verification_executed = int(verification_count_after > verification_count_before)
                emitted.append(
                    f"verify={verification_executed}|"
                    f"{prediction.put_back}>{prediction.search_order[0]}"
                    if prediction.search_order
                    else f"verify={verification_executed}|{prediction.put_back}"
                )
                state.feedback(step)
            rows[arm].append((rollout.rollout_id, tuple(emitted)))
    return {arm: tuple(values) for arm, values in rows.items()}


__all__ = [
    "ARM_PARAMETERS",
    "DIAGNOSTIC_FAMILY",
    "EXPECTED_ARMS",
    "MAX_PHYSICAL_VERIFICATIONS_PER_ROLLOUT",
    "PROTOCOL_ID",
    "SOURCE_BUNDLE_PROTOCOL",
    "ProducerSourceBundle",
    "adapt_world_rollout",
    "compute_producer_source_bundle",
    "make_world_arm_state",
    "produce_arm_prediction_rows",
]
