"""Previously-opened D0 2x2 diagnostic for the two direct-P5 repairs."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from statistics import mean
from typing import Any, Final, Literal, cast

from cpswm.contracts import ActiveObservationPlan, ProjectTwoDatasetSplit, ProjectTwoReplayEpisode
from cpswm.system.evaluation_operations.project_two_dataset import enforce_project_two_replay_gate
from cpswm.system.evaluation_operations.project_two_experiment_config import (
    D0SyntheticReplayExperimentConfig,
)
from cpswm.system.evaluation_operations.structure_two_p5_readout_posthoc_diagnostic import (
    selected_v0_6_action_readout,
)
from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    EVALUATOR_TRUTH_RELEASE_PHASE,
    OBSERVATION_RELEASE_PHASE,
    DirectP5LocationAdapter,
    _decode_and_score,
    _episode_schedule_commitment,
    _packet_for_step,
)
from cpswm.system.prototype_spine import PrototypeStepResult, PrototypeTransition
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.structure_two_adaptive_runtime import (
    AdaptiveAuthorizationPolicy,
    AdaptiveCIAVRuntimeInput,
)
from cpswm.system.structure_two_production_system import (
    StructureTwoProductionSystem,
    build_production_assembly_manifest,
)
from cpswm.world_model.grounded_search.ciav_opceu_loop import CIAVOPCEUReceipt

SCHEMA_VERSION: Final = "0.1.0"
PROTOCOL_ID: Final = "structure-two-p5-readout-prior-factorial@0.1-development"
DEFAULT_CONFIG: Final = Path(
    "configs/project_two_experiments/structure_two_p5_readout_prior_factorial_v0_1.json"
)
DEFAULT_OUTPUT: Final = Path(
    "benchmarks/structure_two/structure_two_p5_readout_prior_factorial_v0_1.json"
)
CLAIM_BOUNDARY: Final = (
    "This 2x2 factorial uses the previously opened D0 development split to separate "
    "the action-readout repair from the sequential actor-prior repair under direct P5. "
    "It is diagnostic only and cannot issue a fresh or confirmatory scientific claim, "
    "aggregate SEARCH and PUT_BACK, pass Task 7/8/9, validate adaptive routing, establish "
    "external validity, authorize ablation, or narrow Structure Two."
)
CellName = Literal[
    "old_readout__old_prior",
    "new_readout__old_prior",
    "old_readout__new_prior",
    "new_readout__new_prior",
]
CELL_ORDER: Final[tuple[CellName, ...]] = (
    "old_readout__old_prior",
    "new_readout__old_prior",
    "old_readout__new_prior",
    "new_readout__new_prior",
)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LegacySequentialPriorProductionSystem(StructureTwoProductionSystem):
    """Evaluation-only reconstruction of the pre-fix transition-prior handoff."""

    def _execute_ciav_operator(
        self,
        transition: PrototypeTransition,
        *,
        primary_result: PrototypeStepResult,
        ciav_input: AdaptiveCIAVRuntimeInput,
    ) -> tuple[ActiveObservationPlan, CIAVOPCEUReceipt | None]:
        legacy_primary = replace(
            primary_result,
            actor_posterior=dict(transition.actor_prior),
        )
        return super()._execute_ciav_operator(
            transition,
            primary_result=legacy_primary,
            ciav_input=ciav_input,
        )

    def _ciav_feedback_transition(
        self,
        transition: PrototypeTransition,
        *,
        ciav_receipt: CIAVOPCEUReceipt,
        primary_actor_posterior: Mapping[str, float],
    ) -> PrototypeTransition:
        del primary_actor_posterior
        return super()._ciav_feedback_transition(
            transition,
            ciav_receipt=ciav_receipt,
            primary_actor_posterior=transition.actor_prior,
        )


def _adapter(episode: ProjectTwoReplayEpisode, cell: CellName) -> DirectP5LocationAdapter:
    state = DirectP5LocationAdapter(episode)
    system_type = (
        LegacySequentialPriorProductionSystem
        if cell.endswith("old_prior")
        else StructureTwoProductionSystem
    )
    action_readout = selected_v0_6_action_readout() if cell.startswith("new_readout") else None
    state.system = system_type(
        owner_key=episode.owner_actor_key,
        object_instance_id=episode.steps[0].object_instance_id,
        locations=state.locations,
        authorization_scope_id=content_uuid(
            PROTOCOL_ID,
            {"episode_id": str(episode.episode_id), "scope": "factorial-direct-P5"},
        ),
        action_readout=action_readout,
        adaptive_authorization_policy=AdaptiveAuthorizationPolicy(
            policy_id="structure-two-p5-factorial-evaluation-only",
            memory_transition_authorized=True,
            privacy_policy_satisfied=True,
            safety_context_authorized=True,
        ),
    )
    return state


def _evaluate_cell_episode(
    dataset: Any,
    episode: ProjectTwoReplayEpisode,
    cell: CellName,
) -> dict[str, Any]:
    state = _adapter(episode, cell)
    schedule = _episode_schedule_commitment(episode)
    truth_envelope = dataset.truth_for(episode.episode_id)
    run_id = content_uuid(PROTOCOL_ID, {"episode_id": str(episode.episode_id), "cell": cell})
    search_errors = put_back_errors = 0
    search_regret = 0.0
    nonuniform = 0
    actions: list[dict[str, Any]] = []
    packet_commitments: list[str] = []
    receipts: list[dict[str, Any]] = []
    for index, step in enumerate(episode.steps):
        packet = _packet_for_step(episode, step, schedule_commitment_sha256=schedule)
        receipt = state.consume_matched_ciav_packet(packet, step, step_index=index)
        posterior = state.predict_location_posteriors(packet)
        probabilities = tuple(
            item.probability for item in posterior.owner_habit_location_distribution
        )
        nonuniform += int(max(probabilities) - min(probabilities) > 1e-12)
        truth = truth_envelope.truth_by_step[step.step_id]
        search_error, put_back_error, regret, action = _decode_and_score(
            posterior,
            episode=episode,
            step=step,
            step_index=index,
            run_execution_id=run_id,
            truth=truth,
        )
        search_errors += search_error
        put_back_errors += put_back_error
        search_regret += regret
        actions.append(action)
        packet_commitments.append(packet.packet_sha256)
        receipts.append(receipt.model_dump(mode="json"))
    step_count = len(episode.steps)
    return {
        "episode_id": str(episode.episode_id),
        "cell": cell,
        "readout": "new" if cell.startswith("new_readout") else "old",
        "sequential_prior": "new" if cell.endswith("new_prior") else "old",
        "step_count": step_count,
        "search_errors": search_errors,
        "search_error_rate": search_errors / step_count,
        "put_back_errors": put_back_errors,
        "put_back_error_rate": put_back_errors / step_count,
        "normalized_search_regret": search_regret / step_count,
        "owner_habit_posterior_nonuniform_step_count": nonuniform,
        "typed_action_chain_sha256": content_sha256(actions),
        "ciav_packet_chain_sha256": content_sha256(packet_commitments),
        "ciav_receipt_chain_sha256": content_sha256(receipts),
        "schedule_commitment_sha256": schedule,
        "full_p5_transition_count": state.full_p5_transition_count,
        "negative_ciav_opceu_closure_count": state.negative_ciav_opceu_closure_count,
        "all_seven_primary_trace_count": state.all_seven_primary_trace_count,
    }


def _summaries(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for cell in CELL_ORDER:
        selected = [row for row in rows if row["cell"] == cell]
        output[cell] = {
            "episode_count": len(selected),
            "step_count": sum(int(row["step_count"]) for row in selected),
            "search_error_rate": mean(float(row["search_error_rate"]) for row in selected),
            "put_back_error_rate": mean(float(row["put_back_error_rate"]) for row in selected),
            "normalized_search_regret": mean(
                float(row["normalized_search_regret"]) for row in selected
            ),
            "owner_habit_posterior_nonuniform_step_count": sum(
                int(row["owner_habit_posterior_nonuniform_step_count"]) for row in selected
            ),
        }
    return output


def factorial_effects(summaries: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Return simple effects and the interaction; positive means improvement."""

    metrics = ("search_error_rate", "put_back_error_rate", "normalized_search_regret")
    output: dict[str, Any] = {}
    for metric in metrics:
        old_old = float(summaries["old_readout__old_prior"][metric])
        new_old = float(summaries["new_readout__old_prior"][metric])
        old_new = float(summaries["old_readout__new_prior"][metric])
        new_new = float(summaries["new_readout__new_prior"][metric])
        output[metric] = {
            "readout_fix_improvement_at_old_prior": old_old - new_old,
            "readout_fix_improvement_at_new_prior": old_new - new_new,
            "prior_fix_improvement_at_old_readout": old_old - old_new,
            "prior_fix_improvement_at_new_readout": new_old - new_new,
            "combined_improvement_from_old_old": old_old - new_new,
            "interaction_synergy_improvement": new_old + old_new - old_old - new_new,
        }
    return output


def _load_config(root: Path) -> dict[str, Any]:
    config = json.loads((root / DEFAULT_CONFIG).read_text(encoding="utf-8"))
    disclosure = cast(Mapping[str, Any], config.get("test_reuse_disclosure"))
    if (
        config.get("schema_version") != SCHEMA_VERSION
        or config.get("protocol_id") != PROTOCOL_ID
        or config.get("status") != "FROZEN_BEFORE_EXECUTION"
        or tuple(config.get("cells", ())) != CELL_ORDER
        or config.get("data_status") != "previously_opened_development_split"
        or disclosure.get("test_split_previously_opened") is not True
        or disclosure.get("confirmatory") is not False
        or config.get("claim_boundary") != CLAIM_BOUNDARY
    ):
        raise ValueError("P5 readout/prior factorial configuration drifted")
    return cast(dict[str, Any], config)


def _source_binding(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    paths = {
        "configuration": DEFAULT_CONFIG,
        "dataset_configuration": Path(str(config["dataset_source"])),
        "execution_module": Path(__file__).resolve().relative_to(root),
        "production_system": Path("src/cpswm/system/structure_two_production_system.py"),
        "readout_selection": Path(
            "configs/project_two_experiments/structure_two_action_readout_v0_6_preregistration.json"
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


def run_p5_readout_prior_factorial(*, repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    config = _load_config(root)
    dataset_config = D0SyntheticReplayExperimentConfig.load(
        root / Path(str(config["dataset_source"]))
    )
    if dataset_config.confirmatory:
        raise ValueError("development factorial cannot open confirmatory data")
    dataset = dataset_config.build_adapter().build()
    enforce_project_two_replay_gate(dataset)
    test = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
    rows = [
        _evaluate_cell_episode(dataset, episode, cell) for cell in CELL_ORDER for episode in test
    ]
    packet_chains = {
        str(episode.episode_id): {
            str(row["ciav_packet_chain_sha256"])
            for row in rows
            if row["episode_id"] == str(episode.episode_id)
        }
        for episode in test
    }
    if any(len(values) != 1 for values in packet_chains.values()):
        raise RuntimeError("factorial cells did not consume the same CIAV packet chain")
    summaries = _summaries(rows)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "status": "DEVELOPMENT_FACTORIAL_COMPLETE",
        "source_binding": _source_binding(root, config),
        "data_scope": {
            "dataset_version": dataset.manifest.dataset_version,
            "test_episode_count": len(test),
            "test_step_count": sum(len(episode.steps) for episode in test),
            "test_split_previously_opened": True,
            "confirmatory": False,
        },
        "factors": config["factors"],
        "held_fixed": config["held_fixed"],
        "cell_episode_metrics": rows,
        "cell_summaries": summaries,
        "factorial_effects": factorial_effects(summaries),
        "execution_audit": {
            "identical_ciav_packet_chain_across_cells": True,
            "observation_release_phase": OBSERVATION_RELEASE_PHASE,
            "evaluator_truth_release_phase": EVALUATOR_TRUTH_RELEASE_PHASE,
            "all_cells_use_direct_p5_full_eager": True,
            "all_positive_steps_use_all_seven_primary_operators": all(
                int(row["full_p5_transition_count"]) == int(row["all_seven_primary_trace_count"])
                for row in rows
            ),
        },
        "test_reuse_disclosure": config["test_reuse_disclosure"],
        "scope_policy": config["scope_policy"],
        "fresh_preregistered_death_test": False,
        "positive_scientific_receipt_issued": False,
        "task_7_8_9_passed": False,
        "adaptive_router_validated": False,
        "external_validity_established": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return {**payload, "content_sha256": content_sha256(payload)}


def _unsigned(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in payload.items() if key != "content_sha256"}


def verify_p5_readout_prior_factorial(
    payload: Mapping[str, Any],
    *,
    repository_root: Path,
    fresh_recompute: bool = True,
) -> None:
    if not fresh_recompute:
        raise ValueError("P5 factorial artifact verification requires fresh recomputation")
    root = repository_root.resolve()
    config = _load_config(root)
    if (
        payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("protocol_id") != PROTOCOL_ID
        or payload.get("status") != "DEVELOPMENT_FACTORIAL_COMPLETE"
        or payload.get("claim_boundary") != CLAIM_BOUNDARY
        or payload.get("content_sha256") != content_sha256(_unsigned(payload))
        or payload.get("source_binding") != _source_binding(root, config)
    ):
        raise ValueError("P5 factorial result identity, hash, or binding drifted")
    expected = run_p5_readout_prior_factorial(repository_root=root)
    if dict(payload) != expected:
        raise ValueError("fresh P5 factorial recomputation disagrees")


__all__ = [
    "CELL_ORDER",
    "CLAIM_BOUNDARY",
    "DEFAULT_CONFIG",
    "DEFAULT_OUTPUT",
    "LegacySequentialPriorProductionSystem",
    "factorial_effects",
    "run_p5_readout_prior_factorial",
    "verify_p5_readout_prior_factorial",
]
