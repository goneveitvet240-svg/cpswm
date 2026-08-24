from __future__ import annotations

import json

import pytest

from cpswm.contracts import ProjectTwoDataMaturity
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_replay_importer import (
    ProjectTwoReplayFileImporter,
    export_project_two_replay_dataset,
)
from cpswm.system.reproducibility import content_sha256


def _typed_d1_fixture():
    source = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,),
        test_seeds=(211,),
        max_steps_per_episode=3,
        dataset_version="source-fixture@0.1",
    ).build()
    version = "d1-import-fixture@0.1"
    episodes = tuple(
        item.model_copy(
            update={
                "dataset_version": version,
                "maturity": ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY,
                "provenance": (*item.provenance, "fixture:annotated-simulator"),
            }
        )
        for item in source.episodes
    )
    truth = []
    for item in source.evaluator_store:
        updated = item.model_copy(update={"dataset_version": version})
        payload = updated.model_dump(mode="python", exclude={"evaluator_content_hash"})
        truth.append(updated.model_copy(update={"evaluator_content_hash": content_sha256(payload)}))
    return episodes, tuple(truth), version


def test_jsonl_import_uses_existing_d1_adapter_and_keeps_truth_physical(tmp_path):
    episodes, truth, version = _typed_d1_fixture()
    visible = tmp_path / "visible_replay.jsonl"
    evaluator = tmp_path / "evaluator_truth.jsonl"
    visible.write_text("\n".join(item.model_dump_json() for item in episodes) + "\n")
    evaluator.write_text("\n".join(item.model_dump_json() for item in truth) + "\n")

    dataset = ProjectTwoReplayFileImporter(
        maturity=ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY,
        dataset_version=version,
        adapter_provenance="test importer",
    ).load(visible, evaluator)

    assert dataset.manifest.dataset_version == version
    assert all(item.maturity.value == "d1_simulator_annotated_replay" for item in dataset.episodes)
    assert "true_actor" not in visible.read_text()
    assert "true_actor" in evaluator.read_text()


def test_importer_rejects_one_file_for_visible_and_evaluator_truth(tmp_path):
    path = tmp_path / "combined.jsonl"
    path.write_text("{}\n")
    importer = ProjectTwoReplayFileImporter(
        maturity=ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY,
        dataset_version="d1@0.1",
        adapter_provenance="test",
    )
    with pytest.raises(ValueError, match="physically separate"):
        importer.load(path, path)


def test_d1_raw_unmapped_labels_are_open_world_unknown_not_coerced():
    normalized = ProjectTwoReplayFileImporter.normalize_open_world_labels(
        actor_label="unregistered-visitor",
        mechanism_label="unmodelled-device-motion",
        resident_actor_keys=("owner", "guest", "unknown_actor"),
    )
    assert normalized["actor_label"] == "unknown_actor"
    assert normalized["mechanism_label"].value == "unknown_mechanism"
    assert normalized["unresolved_axes"] == ("actor", "mechanism")


def test_export_writes_required_manifest_visible_truth_and_coverage(tmp_path):
    source = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,), test_seeds=(211,), max_steps_per_episode=2
    ).build()
    report = export_project_two_replay_dataset(source, tmp_path)
    assert {
        "manifest.json",
        "visible_replay.jsonl",
        "evaluator_truth.jsonl",
        "coverage_report.json",
    }.issubset({item.name for item in tmp_path.iterdir()})
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert report["content_hashes"]["manifest.json"]
    assert manifest["dataset_version"] == source.manifest.dataset_version
