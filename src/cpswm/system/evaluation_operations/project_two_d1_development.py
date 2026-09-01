"""Deterministic D0 development fixture using the full replay contract.

This is deliberately source-neutral: it exercises the D1 adapter and complete
Project Two contracts while AI2-THOR/Habitat/ProcTHOR selection remains a user
decision. It is not represented as external simulator evidence.
"""

from __future__ import annotations

from cpswm.contracts import ProjectTwoDataMaturity
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
    SuppliedReplayDatasetAdapter,
)
from cpswm.system.reproducibility import content_sha256

D1_DEVELOPMENT_VERSION = "project-two-d1-generic-annotated-development@0.1"
SCENE_CATEGORIES = ("kitchen", "living-room", "bedroom")


def build_d1_development_batch(*, max_steps_per_episode: int = 32) -> ProjectTwoReplayDataset:
    source = D0SyntheticOracleReplayAdapter(
        validation_seeds=tuple(range(3101, 3111)),
        test_seeds=tuple(range(4101, 4121)),
        max_steps_per_episode=max_steps_per_episode,
        dataset_version="d1-generic-source-fixture@0.1",
        object_family_bucket_count=5,
        sealed_secret="project-two-d1-generic-development-fixture",
    ).build()
    episodes = []
    envelopes = []
    truth_by_id = {item.episode_id: item for item in source.evaluator_store}
    for index, episode in enumerate(source.episodes):
        seed = 3101 + index if index < 10 else 4101 + index - 10
        scene = SCENE_CATEGORIES[index % len(SCENE_CATEGORIES)]
        source_hash = content_sha256(
            {
                "upstream_hash": episode.source_hash,
                "dataset_version": D1_DEVELOPMENT_VERSION,
                "seed": seed,
                "scene_category": scene,
                "generator": "generic-annotated-simulator-fixture",
            }
        )
        converted = episode.model_copy(
            update={
                "scene_id": f"{episode.split.value}-{scene}",
                "dataset_version": D1_DEVELOPMENT_VERSION,
                "source_uri": f"d1-fixture://generic-annotated-simulator/{episode.episode_id}",
                "source_hash": source_hash,
                "maturity": ProjectTwoDataMaturity.D0_DEVELOPMENT_FIXTURE,
                "source_evidence_maturity": ProjectTwoDataMaturity.D0_SYNTHETIC_ORACLE,
                "provenance": (
                    "generated:StructureTwoActionScenarioGenerator",
                    "normalized:SuppliedReplayDatasetAdapter",
                    "source-neutral:generic-annotated-simulator-fixture",
                    "claim:not-external-simulator-data",
                    f"development_seed:{seed}",
                    f"scene_category:{scene}",
                ),
            }
        )
        source_truth = truth_by_id[episode.episode_id]
        payload = {
            "episode_id": converted.episode_id,
            "dataset_version": D1_DEVELOPMENT_VERSION,
            "source_hash": source_hash,
            "truth_by_step": source_truth.truth_by_step,
        }
        envelopes.append(
            source_truth.model_copy(
                update={
                    **payload,
                    "evaluator_content_hash": content_sha256(payload),
                }
            )
        )
        episodes.append(converted)
    return SuppliedReplayDatasetAdapter(
        maturity=ProjectTwoDataMaturity.D0_DEVELOPMENT_FIXTURE,
        dataset_version=D1_DEVELOPMENT_VERSION,
        episodes=tuple(episodes),
        evaluator_store=tuple(envelopes),
        adapter_provenance="generic annotated simulator development fixture; source not selected",
    ).build()


__all__ = ["D1_DEVELOPMENT_VERSION", "SCENE_CATEGORIES", "build_d1_development_batch"]
