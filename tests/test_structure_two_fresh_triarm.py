from __future__ import annotations

import json
from pathlib import Path

import pytest

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionBenchmarkV02,
)
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (
    DEFAULT_MANIFEST,
    DEFAULT_SEALED_SEEDS,
    TriarmMethod,
    _dataset,
    _evaluate,
    _load_and_verify_holdout_seeds,
    _normalize,
    load_frozen_triarm_design,
    multiaxis_sensitivity_audit,
)
from cpswm.world_model.habits_transitions import ChangeCause

ROOT = Path(__file__).resolve().parents[1]


def test_fresh_design_freezes_four_new_families_and_sealed_commitments() -> None:
    design = load_frozen_triarm_design(ROOT / DEFAULT_MANIFEST)

    assert len(design.families) == 4
    assert len(design.validation_seeds) == 4
    assert len(design.holdout_seed_commitments) == 12
    assert design.particle_budget == 24
    assert set(design.search_spaces) == {arm.value for arm in TriarmMethod}
    assert set(design.validation_seeds).isdisjoint(
        _load_and_verify_holdout_seeds(design, ROOT / DEFAULT_SEALED_SEEDS)
    )


def test_sealed_seed_file_tampering_fails_closed(tmp_path: Path) -> None:
    design = load_frozen_triarm_design(ROOT / DEFAULT_MANIFEST)
    payload = json.loads((ROOT / DEFAULT_SEALED_SEEDS).read_text(encoding="utf-8"))
    payload["holdout_seeds"][0] += 1
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="file hash mismatch"):
        _load_and_verify_holdout_seeds(design, path)


def test_all_registered_axis_perturbations_change_both_action_readouts() -> None:
    gates = multiaxis_sensitivity_audit()

    assert len(gates) == 8
    assert all(gates.values())


def test_missing_cause_mass_can_be_completed_without_key_failure() -> None:
    complete = dict.fromkeys(ChangeCause, 0.0)
    complete.update({ChangeCause.ACTOR: 0.4, ChangeCause.HABIT: 0.6})
    normalized = _normalize(complete)

    assert set(normalized) == set(ChangeCause)
    assert normalized[ChangeCause.NOISE] == 0.0
    assert sum(normalized.values()) == pytest.approx(1.0)


def test_runtime_receipts_bind_same_visible_stream_and_full_operator_stack() -> None:
    design = load_frozen_triarm_design(ROOT / DEFAULT_MANIFEST)
    family = design.families[0]
    dataset = _dataset(
        family,
        validation_seeds=(design.validation_seeds[0],),
        test_seeds=(52991,),
        max_steps=design.max_steps,
        split_label="runtime-receipt-test",
    )
    episode = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)[0]
    evaluator = ProjectTwoActionBenchmarkV02()
    parameters = {
        TriarmMethod.CORRECTED_AMG: 0.2,
        TriarmMethod.OLD_FULL_MULTIAXIS: "balanced",
        TriarmMethod.JOINT_REVISION_MULTIAXIS: "balanced",
    }
    readings = {
        arm: _evaluate(evaluator, dataset, episode, family, arm, parameters[arm])
        for arm in TriarmMethod
    }

    assert len({item.metric.visible_input_hash for item in readings.values()}) == 1
    consumed_hashes = {item.consumed_visible_stream_hash for item in readings.values()}
    assert len(consumed_hashes) == 1
    assert len(next(iter(consumed_hashes))) == 64
    expected = {
        "opceu": "inverse",
        "orrer": "orrer",
        "pchmp": "ProvenanceConstrainedMessagePassing",
        "cf_bocpd": True,
        "rgrc": True,
        "ccrr": True,
        "ciav": True,
    }
    assert readings[TriarmMethod.OLD_FULL_MULTIAXIS].operator_retention_receipt == expected
    assert readings[TriarmMethod.JOINT_REVISION_MULTIAXIS].operator_retention_receipt == expected
