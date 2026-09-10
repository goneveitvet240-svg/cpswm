from __future__ import annotations

import copy
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.structure_two_p5_direct_trace_probe import (
    run_p5_direct_trace_probe,
    verify_p5_direct_trace_probe,
)
from cpswm.system.reproducibility import content_sha256

ROOT = Path(__file__).resolve().parents[1]


def _resign(payload: dict) -> None:
    payload["content_sha256"] = content_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )


def test_direct_p5_trace_probe_fresh_recompute_passes() -> None:
    result = run_p5_direct_trace_probe(repository_root=ROOT)
    verify_p5_direct_trace_probe(result, repository_root=ROOT, fresh_recompute=True)

    assert result["engineering_bringup_passed"] is True
    assert result["normal_router_selection"]["selected_path_id"] == "P0_SAFE_DEFERRED"
    assert result["direct_p5_selection"]["selected_path_id"] == "P5_FULL_EAGER"
    assert len(result["operator_call_consumption_trace"]) == 13
    assert result["cross_arm_ciav_matching_established"] is False
    assert result["action_benefit_established"] is False


def test_direct_p5_trace_probe_rejects_resigned_trace_projection_tamper() -> None:
    result = run_p5_direct_trace_probe(repository_root=ROOT)
    forged = copy.deepcopy(result)
    forged["operator_call_consumption_trace"][6]["consumes"] = []
    _resign(forged)

    with pytest.raises(ValueError, match="projection differs"):
        verify_p5_direct_trace_probe(forged, repository_root=ROOT, fresh_recompute=False)


def test_direct_p5_trace_probe_rejects_claim_promotion() -> None:
    result = run_p5_direct_trace_probe(repository_root=ROOT)
    forged = copy.deepcopy(result)
    forged["action_benefit_established"] = True
    _resign(forged)

    with pytest.raises(ValueError, match="unauthorized claim"):
        verify_p5_direct_trace_probe(forged, repository_root=ROOT, fresh_recompute=False)
