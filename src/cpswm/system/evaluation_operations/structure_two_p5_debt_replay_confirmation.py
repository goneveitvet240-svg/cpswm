"""Engineering confirmation of direct-P5 versus production debt-replay semantics.

The test split used by the P5 death test is already open.  This module therefore
checks production-path equivalence only; it neither rescues nor retests a
scientific action signal.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast
from uuid import UUID

from cpswm.contracts import ProjectTwoDatasetSplit, ProjectTwoReplayEpisode, ProjectTwoReplayStep
from cpswm.system.evaluation_operations.project_two_action_benchmark import _locations
from cpswm.system.evaluation_operations.project_two_dataset import enforce_project_two_replay_gate
from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_p5_direct_trace_probe import (
    _ProbeTraceSink,
    _router_features,
)
from cpswm.system.evaluation_operations.structure_two_p5_readout_posthoc_diagnostic import (
    selected_v0_6_action_readout,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_contract import (
    P5ComparisonArm,
    TypedLocationPosterior,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    PrecommittedCIAVPacket,
    _ciav_input,
    _episode_schedule_commitment,
    _normalise,
    _packet_for_step,
    _transition,
    _validate_packet_step,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    _load_config as _load_retained_config,
)
from cpswm.system.prototype_spine import PrototypeTransition
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_adaptive_runtime import (
    AdaptiveAuthorizationPolicy,
    AdaptiveExecutionContext,
    AdaptiveStepResult,
)
from cpswm.system.structure_two_execution import StructureTwoExecutionTrace, verify_execution_trace
from cpswm.system.structure_two_production_system import (
    StructureTwoProductionSystem,
    build_production_assembly_manifest,
)

SCHEMA_VERSION: Final = "0.1.0"
PROTOCOL_ID: Final = "structure-two-p5-debt-replay-confirmation@0.1-development"
DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_p5_debt_replay_confirmation_v0_1.json"
)
DEFAULT_OUTPUT: Final = Path(
    "benchmarks/structure_two/structure_two_p5_debt_replay_confirmation_v0_1.json"
)
CLAIM_BOUNDARY: Final = (
    "This test-opened-split engineering confirmation can establish semantic equivalence "
    "between evaluation-only direct P5 and the isolated production P0-to-expired-debt-"
    "replay-P5 path for positive same-location A1 observations. It cannot retest or "
    "establish a SEARCH or PUT_BACK scientific signal, overwrite the retained v0.1 "
    "failure, validate router calibration or utility, cover negative observations, "
    "different-location feedback, concurrent debts, or long-horizon recovery, pass Task "
    "7/8/9, establish external validity, authorize ablation, aggregate tasks, or narrow "
    "Structure Two."
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unsigned(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in payload.items() if key != "content_sha256"}


def _load_config(root: Path) -> dict[str, Any]:
    config = json.loads((root / DEFAULT_CONFIG).read_text(encoding="utf-8"))
    trigger = cast(Mapping[str, Any], config.get("trigger"))
    execution = cast(Mapping[str, Any], config.get("execution"))
    disclosure = cast(Mapping[str, Any], config.get("test_reuse_disclosure"))
    limits = cast(Mapping[str, Any], config.get("coverage_limits"))
    if (
        config.get("schema_version") != SCHEMA_VERSION
        or config.get("protocol_id") != PROTOCOL_ID
        or config.get("status") != "FROZEN_BEFORE_EXECUTION"
        or config.get("claim_boundary") != CLAIM_BOUNDARY
        or execution.get("split") != "test"
        or execution.get("episode_policy") != "all_test_episodes"
        or execution.get("transition_policy")
        != "all_positive_detected_transitions_in_original_episode_order"
        or execution.get("debt_expiry_steps") != 1
        or execution.get("evaluator_truth_accessed") is not False
        or disclosure.get("engineering_confirmation_only") is not True
        or disclosure.get("confirmatory") is not False
        or disclosure.get("fresh_preregistered_death_test") is not False
        or disclosure.get("may_issue_positive_scientific_receipt") is not False
        or any(value is not False for value in limits.values())
    ):
        raise ValueError("P5 debt-replay confirmation configuration drifted")
    posthoc_path = root / Path(str(trigger["posthoc_result_path"]))
    posthoc = json.loads(posthoc_path.read_text(encoding="utf-8"))
    if (
        _file_sha256(posthoc_path) != trigger.get("posthoc_result_file_sha256")
        or posthoc.get("content_sha256") != trigger.get("posthoc_result_content_sha256")
        or posthoc.get("status") != trigger.get("posthoc_result_status")
        or posthoc.get("content_sha256") != content_sha256(_unsigned(posthoc))
    ):
        raise ValueError("bound P5 post-hoc result identity drifted")
    return cast(dict[str, Any], config)


def _source_binding(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    trigger = cast(Mapping[str, Any], config["trigger"])
    paths = {
        "configuration": DEFAULT_CONFIG,
        "execution_module": Path(__file__).resolve().relative_to(root),
        "posthoc_result": Path(str(trigger["posthoc_result_path"])),
        "posthoc_execution_module": Path(
            "src/cpswm/system/evaluation_operations/structure_two_p5_readout_posthoc_diagnostic.py"
        ),
    }
    binding: dict[str, Any] = {
        name: {"path": path.as_posix(), "sha256": _file_sha256(root / path)}
        for name, path in paths.items()
    }
    binding["production_assembly_manifest_sha256"] = build_production_assembly_manifest(root)[
        "content_sha256"
    ]
    return binding


def _new_system(episode: ProjectTwoReplayEpisode) -> StructureTwoProductionSystem:
    return StructureTwoProductionSystem(
        owner_key=episode.owner_actor_key,
        object_instance_id=episode.steps[0].object_instance_id,
        locations=_locations(episode),
        authorization_scope_id=content_uuid(
            PROTOCOL_ID,
            {"episode_id": str(episode.episode_id), "scope": "direct-replay-equivalence"},
        ),
        action_readout=selected_v0_6_action_readout(),
        adaptive_authorization_policy=AdaptiveAuthorizationPolicy(
            policy_id="structure-two-p5-debt-replay-engineering-confirmation",
            memory_transition_authorized=True,
            privacy_policy_satisfied=True,
            safety_context_authorized=True,
        ),
    )


def _mapping_close(
    left: Mapping[Any, float],
    right: Mapping[Any, float],
    *,
    absolute_tolerance: float,
) -> bool:
    return set(left) == set(right) and all(
        math.isclose(
            float(left[key]),
            float(right[key]),
            rel_tol=0.0,
            abs_tol=absolute_tolerance,
        )
        for key in left
    )


def _distribution_rows(
    distribution: Mapping[UUID, float], locations: Sequence[UUID]
) -> tuple[tuple[str, float], ...]:
    return tuple((str(location), float(distribution[location])) for location in locations)


def _typed_put_back_location(
    *,
    system: StructureTwoProductionSystem,
    episode: ProjectTwoReplayEpisode,
    step: ProjectTwoReplayStep,
    packet: PrecommittedCIAVPacket,
    locations: tuple[UUID, ...],
    step_index: int,
) -> UUID:
    detected = packet.realized_detected_location_id
    if detected is None:
        raise ValueError("typed replay readout requires a detected A1 packet")
    current = {location: float(location == detected) for location in locations}
    habit = _normalise(
        system.action_location_distribution(system.current_snapshot),
        locations,
    )
    posterior = TypedLocationPosterior.seal(
        arm=P5ComparisonArm.DIRECT_P5,
        episode_id=episode.episode_id,
        step_id=step.step_id,
        target_object_id=step.object_instance_id,
        source_visible_step_sha256=packet.visible_step_sha256,
        belief_state_sha256=system.adaptive_router_state_sha256(),
        location_support=locations,
        current_location_distribution=current,
        owner_habit_location_distribution=habit,
    )
    readout = posterior.decode(
        step_index=step_index,
        run_execution_id=content_uuid(
            PROTOCOL_ID,
            {"episode_id": str(episode.episode_id), "step_id": str(step.step_id)},
        ),
        visible_observation=step.model_dump(mode="json"),
    )
    return readout.put_back_action.location_id


def _require_positive_result(
    result: AdaptiveStepResult,
    trace: StructureTwoExecutionTrace,
) -> None:
    if result.primary_result is None or result.ciav_receipt is None:
        raise RuntimeError("P5 comparison path did not return primary and CIAV results")
    verify_execution_trace(trace)


def compare_positive_transition(
    *,
    direct_system: StructureTwoProductionSystem,
    replay_system: StructureTwoProductionSystem,
    episode: ProjectTwoReplayEpisode,
    step: ProjectTwoReplayStep,
    original_step_index: int,
    packet: PrecommittedCIAVPacket,
    absolute_tolerance: float,
) -> dict[str, Any]:
    """Compare one positive observation while preserving both episode histories."""

    _validate_packet_step(packet, episode, step)
    if packet.realized_detected_location_id is None:
        raise ValueError("debt replay comparison only accepts detected A1 packets")
    locations = _locations(episode)
    transition: PrototypeTransition = _transition(episode, step, original_step_index)
    ciav_input = _ciav_input(packet, episode, step, locations)

    direct_sink = _ProbeTraceSink()
    direct_result = direct_system.process_evaluation_direct_p5_transition(
        transition,
        context=AdaptiveExecutionContext(
            router_features=_router_features(direct_system),
            step_index=original_step_index,
            debt_expiry_steps=1,
            ciav_input=ciav_input,
        ),
        trace_sink=direct_sink,
    )
    direct_trace = direct_sink.trace
    if direct_trace is None:
        raise RuntimeError("direct P5 did not commit a trace")
    _require_positive_result(direct_result, direct_trace)

    p0_sink = _ProbeTraceSink()
    p0_result = replay_system.process_adaptive_transition(
        transition,
        context=AdaptiveExecutionContext(
            router_features=_router_features(replay_system),
            step_index=2 * original_step_index,
            debt_expiry_steps=1,
        ),
        trace_sink=p0_sink,
    )
    p0_trace = p0_sink.trace
    if p0_trace is None:
        raise RuntimeError("P0 deferral did not commit a trace")
    verify_execution_trace(p0_trace)
    pending_before = replay_system.pending_adaptive_debts()
    if len(p0_result.debt_certificates) != 1:
        raise RuntimeError("P0 did not issue exactly one replayable debt certificate")
    debt = p0_result.debt_certificates[0]

    replay_sink = _ProbeTraceSink()
    replay_result = replay_system.replay_adaptive_debt(
        debt.debt_id,
        step_index=2 * original_step_index + 1,
        ciav_input=ciav_input,
        trace_sink=replay_sink,
    )
    replay_trace = replay_sink.trace
    if replay_trace is None:
        raise RuntimeError("debt replay did not commit a trace")
    _require_positive_result(replay_result, replay_trace)

    assert direct_result.primary_result is not None
    assert replay_result.primary_result is not None
    assert direct_result.ciav_receipt is not None
    assert replay_result.ciav_receipt is not None
    direct_habit = _normalise(
        direct_system.action_location_distribution(direct_system.current_snapshot),
        locations,
    )
    replay_habit = _normalise(
        replay_system.action_location_distribution(replay_system.current_snapshot),
        locations,
    )
    direct_put_back = _typed_put_back_location(
        system=direct_system,
        episode=episode,
        step=step,
        packet=packet,
        locations=locations,
        step_index=original_step_index,
    )
    replay_put_back = _typed_put_back_location(
        system=replay_system,
        episode=episode,
        step=step,
        packet=packet,
        locations=locations,
        step_index=original_step_index,
    )
    direct_detection = direct_result.ciav_receipt.detection
    replay_detection = replay_result.ciav_receipt.detection
    checks = {
        "normal_router_selects_P0_SAFE_DEFERRED": (
            p0_result.path_selection.selected_path_id == "P0_SAFE_DEFERRED"
            and p0_trace.plan.plan_id == "P0_SAFE_DEFERRED"
        ),
        "exactly_one_bound_debt_is_created_and_pending": (
            pending_before == p0_result.debt_certificates == (debt,)
            and debt.origin_transition_sha256 == content_sha256(transition)
        ),
        "expired_debt_replay_selects_P5_FULL_EAGER": (
            replay_result.path_selection.selected_path_id == "P5_FULL_EAGER"
            and replay_trace.plan.plan_id == "P5_FULL_EAGER"
        ),
        "replay_trace_consumes_the_exact_debt_certificate": (
            replay_trace.replayed_debt_certificates == (debt,)
        ),
        "replay_trace_invokes_all_seven_primary_operators": (
            direct_trace.all_seven_operators_invoked and replay_trace.all_seven_operators_invoked
        ),
        "replay_settles_the_debt_without_pending_remainder": (
            replay_system.pending_adaptive_debts() == ()
        ),
        "direct_and_replay_primary_PCHMP_actor_posteriors_match": _mapping_close(
            direct_result.primary_result.actor_posterior,
            replay_result.primary_result.actor_posterior,
            absolute_tolerance=absolute_tolerance,
        ),
        "direct_and_replay_CIAV_actor_posteriors_match": _mapping_close(
            direct_result.ciav_receipt.evidence.actor_posterior,
            replay_result.ciav_receipt.evidence.actor_posterior,
            absolute_tolerance=absolute_tolerance,
        ),
        "direct_and_replay_owner_habit_location_distributions_match": _mapping_close(
            direct_habit,
            replay_habit,
            absolute_tolerance=absolute_tolerance,
        ),
        "direct_and_replay_typed_PUT_BACK_locations_match": direct_put_back == replay_put_back,
        "direct_and_replay_consume_the_same_A1_action_outcome_and_location": (
            direct_result.ciav_plan is not None
            and replay_result.ciav_plan is not None
            and direct_result.ciav_plan.selected_action_id == packet.selected_action_id
            and replay_result.ciav_plan.selected_action_id == packet.selected_action_id
            and direct_detection.outcome == replay_detection.outcome == packet.realized_outcome
            and direct_detection.detected_location_id
            == replay_detection.detected_location_id
            == packet.realized_detected_location_id
        ),
        "direct_and_replay_use_same_location_fast_verification": (
            direct_trace.feedback_closure_kind == "same_location_fast_verification"
            and replay_trace.feedback_closure_kind == "same_location_fast_verification"
            and direct_result.fast_verification_receipt is not None
            and replay_result.fast_verification_receipt is not None
        ),
    }
    return {
        "episode_id": str(episode.episode_id),
        "step_id": str(step.step_id),
        "original_step_index": original_step_index,
        "checks": checks,
        "direct_primary_actor_posterior": dict(direct_result.primary_result.actor_posterior),
        "replay_primary_actor_posterior": dict(replay_result.primary_result.actor_posterior),
        "direct_ciav_actor_posterior": dict(direct_result.ciav_receipt.evidence.actor_posterior),
        "replay_ciav_actor_posterior": dict(replay_result.ciav_receipt.evidence.actor_posterior),
        "direct_owner_habit_location_distribution": _distribution_rows(direct_habit, locations),
        "replay_owner_habit_location_distribution": _distribution_rows(replay_habit, locations),
        "direct_put_back_location_id": str(direct_put_back),
        "replay_put_back_location_id": str(replay_put_back),
    }


def run_p5_debt_replay_confirmation(*, repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    config = _load_config(root)
    execution = cast(Mapping[str, Any], config["execution"])
    retained_config = _load_retained_config(root)
    dataset_config = D0SyntheticReplayExperimentConfig.load(
        root / Path(str(retained_config["dataset_source"]))
    )
    if dataset_config.confirmatory:
        raise ValueError("engineering debt-replay confirmation cannot open confirmatory data")
    dataset = dataset_config.build_adapter().build()
    enforce_project_two_replay_gate(dataset)
    episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
    tolerance = float(execution["numeric_absolute_tolerance"])
    all_rows: list[dict[str, Any]] = []
    per_episode: list[dict[str, Any]] = []
    negative_steps_excluded = 0
    for episode in episodes:
        direct_system = _new_system(episode)
        replay_system = _new_system(episode)
        schedule = _episode_schedule_commitment(episode)
        rows: list[dict[str, Any]] = []
        for index, step in enumerate(episode.steps):
            packet = _packet_for_step(
                episode,
                step,
                schedule_commitment_sha256=schedule,
            )
            if packet.realized_detected_location_id is None:
                negative_steps_excluded += 1
                continue
            row = compare_positive_transition(
                direct_system=direct_system,
                replay_system=replay_system,
                episode=episode,
                step=step,
                original_step_index=index,
                packet=packet,
                absolute_tolerance=tolerance,
            )
            rows.append(row)
            all_rows.append(row)
        per_episode.append(
            {
                "episode_id": str(episode.episode_id),
                "positive_transition_count": len(rows),
                "failed_check_count": sum(
                    int(not passed)
                    for row in rows
                    for passed in cast(Mapping[str, bool], row["checks"]).values()
                ),
                "semantic_comparison_chain_sha256": content_sha256(rows),
            }
        )

    required = tuple(cast(Sequence[str], config["required_equivalence_checks"]))
    passed_by_check = {
        check: sum(int(cast(Mapping[str, bool], row["checks"])[check]) for row in all_rows)
        for check in required
    }
    failed_rows = [
        {
            "episode_id": row["episode_id"],
            "step_id": row["step_id"],
            "original_step_index": row["original_step_index"],
            "failed_checks": [
                name
                for name, passed in cast(Mapping[str, bool], row["checks"]).items()
                if not passed
            ],
        }
        for row in all_rows
        if not all(cast(Mapping[str, bool], row["checks"]).values())
    ]
    transition_count = len(all_rows)
    overall = transition_count > 0 and all(
        passed_by_check[check] == transition_count for check in required
    )
    status = (
        "PRODUCTION_DEBT_REPLAY_SEMANTIC_EQUIVALENCE_CONFIRMED"
        if overall
        else "PRODUCTION_DEBT_REPLAY_SEMANTIC_EQUIVALENCE_FAILED"
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "status": status,
        "source_binding": _source_binding(root, config),
        "test_reuse_disclosure": config["test_reuse_disclosure"],
        "data_scope": {
            "dataset_version": dataset.manifest.dataset_version,
            "split": "test",
            "test_episode_count": len(episodes),
            "positive_transition_count": transition_count,
            "negative_observation_step_count_excluded": negative_steps_excluded,
            "evaluator_truth_access_count": 0,
        },
        "execution": config["execution"],
        "equivalence_audit": {
            "all_required_checks_passed": overall,
            "required_check_count": len(required),
            "passed_transition_count_by_check": passed_by_check,
            "failed_transition_count": len(failed_rows),
            "first_failed_transitions": failed_rows[:20],
            "semantic_comparison_chain_sha256": content_sha256(all_rows),
            "per_episode": per_episode,
        },
        "coverage_limits": config["coverage_limits"],
        "scope_policy": config["scope_policy"],
        "search_or_put_back_scientific_signal_retested": False,
        "retained_v0_1_failure_overwritten": False,
        "positive_scientific_receipt_issued": False,
        "adaptive_router_calibration_validated": False,
        "task_7_8_9_passed": False,
        "external_validity_established": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {**payload, "content_sha256": content_sha256(payload)}


def verify_p5_debt_replay_confirmation(
    payload: Mapping[str, Any],
    *,
    repository_root: Path,
    fresh_recompute: bool = False,
) -> None:
    root = repository_root.resolve()
    config = _load_config(root)
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("protocol_id") != PROTOCOL_ID
        or payload.get("status")
        not in {
            "PRODUCTION_DEBT_REPLAY_SEMANTIC_EQUIVALENCE_CONFIRMED",
            "PRODUCTION_DEBT_REPLAY_SEMANTIC_EQUIVALENCE_FAILED",
        }
        or payload.get("claim_boundary") != CLAIM_BOUNDARY
        or payload.get("content_sha256") != content_sha256(_unsigned(payload))
        or payload.get("source_binding") != _source_binding(root, config)
    ):
        raise ValueError("P5 debt-replay result identity, hash, or binding drifted")
    for field in (
        "search_or_put_back_scientific_signal_retested",
        "retained_v0_1_failure_overwritten",
        "positive_scientific_receipt_issued",
        "adaptive_router_calibration_validated",
        "task_7_8_9_passed",
        "external_validity_established",
    ):
        if payload.get(field) is not False:
            raise ValueError(f"debt-replay result promoted unauthorized claim: {field}")
    audit = cast(Mapping[str, Any], payload.get("equivalence_audit"))
    scope = cast(Mapping[str, Any], payload.get("data_scope"))
    all_passed = audit.get("all_required_checks_passed") is True
    if (
        scope.get("evaluator_truth_access_count") != 0
        or (payload.get("status") == "PRODUCTION_DEBT_REPLAY_SEMANTIC_EQUIVALENCE_CONFIRMED")
        != all_passed
        or (all_passed and audit.get("failed_transition_count") != 0)
    ):
        raise ValueError("P5 debt-replay result contains an unsupported equivalence claim")
    if fresh_recompute:
        expected = run_p5_debt_replay_confirmation(repository_root=root)
        if dict(payload) != expected:
            raise ValueError("fresh P5 debt-replay recomputation disagrees")


__all__ = [
    "CLAIM_BOUNDARY",
    "DEFAULT_CONFIG",
    "DEFAULT_OUTPUT",
    "compare_positive_transition",
    "run_p5_debt_replay_confirmation",
    "verify_p5_debt_replay_confirmation",
]
