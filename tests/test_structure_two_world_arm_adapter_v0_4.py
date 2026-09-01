from __future__ import annotations

import json
from pathlib import Path

from cpswm.contracts import ProjectTwoDatasetSplit, reject_truth_leakage
from cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4 import (
    EXPECTED_ARMS,
    adapt_world_rollout,
    compute_producer_source_bundle,
    make_world_arm_state,
    produce_arm_prediction_rows,
)
from cpswm.system.evaluation_operations.structure_two_world_generator_v0_2 import (
    StructureTwoWorldGeneratorV02,
    WorldDistributionConfig,
)

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / (
    "configs/project_two_experiments/structure_two_world_generator_manifest_v0_4_DRAFT.json"
)


def _fixture():
    payload = json.loads(DRAFT.read_text(encoding="utf-8"))
    generator = StructureTwoWorldGeneratorV02(
        WorldDistributionConfig.from_manifest(payload["world_distribution"])
    )
    world = generator.sample_world(410001)
    rollout = generator.generate_rollout(
        world,
        trajectory_seed=17,
        observation_seed=107,
    )
    return world, rollout


def test_adapter_keeps_truth_out_of_visible_episode_and_preserves_catalogue() -> None:
    world, rollout = _fixture()
    dataset = adapt_world_rollout(world, rollout)
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    reject_truth_leakage(episode.model_dump(mode="python"))
    assert len(episode.steps) == len(rollout.steps)
    assert len(episode.known_location_ids) == len(world.locations)
    assert len(set(episode.known_location_ids)) == len(world.locations)
    assert set(dataset.truth_for(episode.episode_id).truth_by_step) == {
        step.step_id for step in episode.steps
    }


def test_adapter_never_fabricates_a_self_transition() -> None:
    world, rollout = _fixture()
    episode = adapt_world_rollout(world, rollout).episodes[0]
    assert all(
        step.before.detected_location_id != step.after.detected_location_id
        for step in episode.steps
        if step.before is not None and step.after is not None
    )


def test_all_frozen_arms_emit_complete_catalogue_rankings() -> None:
    world, rollout = _fixture()
    dataset = adapt_world_rollout(world, rollout)
    episode = dataset.episodes[0]
    for arm in EXPECTED_ARMS:
        state = make_world_arm_state(dataset, episode, arm)
        for step in episode.steps[:12]:
            state.observe(step)
            prediction = state.predict()
            state.feedback(step)
        assert len(prediction.search_order) == len(world.locations)
        assert set(prediction.search_order) == set(episode.known_location_ids)


def test_producer_source_bundle_is_complete_and_repeatable() -> None:
    first = compute_producer_source_bundle(ROOT)
    second = compute_producer_source_bundle(ROOT)
    paths = {path for path, _ in first.files}
    assert first == second
    assert "src/cpswm/system/evaluation_operations/structure_two_world_arm_adapter_v0_4.py" in paths
    assert "apps/evaluation_runner/run_structure_two_world_arm_traces_v0_4.py" in paths
    assert "apps/evaluation_runner/attest_structure_two_arm_trace_v0_4.py" in paths
    assert len(first.content_sha256) == 64


def test_gate_b_tokens_bind_external_verification_and_endpoint_actions() -> None:
    world, rollout = _fixture()
    rows = produce_arm_prediction_rows(
        ((world, rollout),),
        arms=("corrected_amg", "care_wm"),
    )
    for arm_rows in rows.values():
        assert len(arm_rows) == 1
        assert len(arm_rows[0][1]) == len(rollout.steps)
        assert all(
            token.startswith(("verify=0|", "verify=1|")) and ">" in token
            for token in arm_rows[0][1]
        )


def test_o_star_gate_b_arm_discloses_nonfaithful_proxy_status() -> None:
    world, rollout = _fixture()
    dataset = adapt_world_rollout(world, rollout)
    state = make_world_arm_state(dataset, dataset.episodes[0], "o_star_matched")

    assert (
        state._state.adapter_receipt["fidelity"]
        == "reduced_proxy_not_faithful_external_reproduction"
    )
