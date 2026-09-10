from __future__ import annotations

import copy
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.structure_two_p5_three_arm_readiness import (
    run_p5_three_arm_readiness,
    verify_p5_three_arm_readiness,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]


def _resign(payload: dict) -> None:
    payload["content_sha256"] = content_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )


def test_fresh_three_arm_readiness_freezes_dataset_and_reports_real_blockers() -> None:
    result = run_p5_three_arm_readiness(repository_root=ROOT)
    verify_p5_three_arm_readiness(result, repository_root=ROOT, fresh_recompute=True)

    assert result["dataset"]["episode_count"] == 80
    assert result["dataset"]["step_count"] == 2560
    assert result["dataset"]["negative_or_incomplete_observation_count"] > 0
    assert result["readiness_checks"]["direct_p5_entrypoint_available"] is True
    assert result["readiness_checks"]["shared_decoder_available"] is True
    assert result["readiness_checks"]["all_arm_location_adapters_available"] is False
    assert result["readiness_checks"]["all_arm_ciav_consumers_available"] is False
    assert result["three_arm_execution_ready"] is False


def test_three_arm_readiness_rejects_resigned_blocker_omission() -> None:
    result = run_p5_three_arm_readiness(repository_root=ROOT)
    forged = copy.deepcopy(result)
    forged["blocking_reasons"] = forged["blocking_reasons"][:-1]
    _resign(forged)

    with pytest.raises(ValueError, match="blockers were omitted"):
        verify_p5_three_arm_readiness(forged, repository_root=ROOT, fresh_recompute=False)


def test_three_arm_readiness_rejects_resigned_ready_claim() -> None:
    result = run_p5_three_arm_readiness(repository_root=ROOT)
    forged = copy.deepcopy(result)
    forged["three_arm_execution_ready"] = True
    _resign(forged)

    with pytest.raises(ValueError, match="unauthorized claim"):
        verify_p5_three_arm_readiness(forged, repository_root=ROOT, fresh_recompute=False)


def test_three_arm_readiness_rejects_resigned_episode_manifest_substitution() -> None:
    result = run_p5_three_arm_readiness(repository_root=ROOT)
    forged = copy.deepcopy(result)
    forged["dataset"]["episode_manifest"][0]["visible_episode_sha256"] = "0" * 64
    _resign(forged)

    with pytest.raises(ValueError, match=r"fresh.*recomputation"):
        verify_p5_three_arm_readiness(forged, repository_root=ROOT, fresh_recompute=True)
