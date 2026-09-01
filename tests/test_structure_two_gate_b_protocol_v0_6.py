from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import (
    EXPECTED_ARMS,
    validate_structure_two_gate_b_v0_6_draft,
)

ROOT = Path(__file__).resolve().parents[1]
DRAFT = json.loads(
    (ROOT / "configs/project_two_experiments/structure_two_gate_b_v0_6_DRAFT.json").read_text(
        encoding="utf-8"
    )
)


def test_repository_v0_6_draft_passes_canonical_validation() -> None:
    comparisons, requirements = validate_structure_two_gate_b_v0_6_draft(DRAFT)
    assert len(comparisons) == 9
    assert tuple(item.arm for item in requirements) == EXPECTED_ARMS


def test_dropping_failed_arm_or_comparison_fails_closed() -> None:
    dropped_arm = deepcopy(DRAFT)
    dropped_arm["expected_arms"].remove("brainctl_matched")
    with pytest.raises(ValueError, match="complete ten-arm set"):
        validate_structure_two_gate_b_v0_6_draft(dropped_arm)
    dropped_pair = deepcopy(DRAFT)
    dropped_pair["comparison_pairs"].pop()
    with pytest.raises(ValueError, match="comparison set"):
        validate_structure_two_gate_b_v0_6_draft(dropped_pair)


def test_lowering_threshold_after_failure_fails_closed() -> None:
    modified = deepcopy(DRAFT)
    modified["comparison_pairs"][0]["min_action_disagreement_rate"] = 0.0
    with pytest.raises(ValueError, match="threshold changed"):
        validate_structure_two_gate_b_v0_6_draft(modified)


def test_deleting_hard_mechanism_or_weakening_fidelity_policy_fails_closed() -> None:
    deleted_event = deepcopy(DRAFT)
    deleted_event["mechanism_requirements"]["o_star_matched"].remove("cost_aware_search")
    with pytest.raises(ValueError, match="canonical mechanism events"):
        validate_structure_two_gate_b_v0_6_draft(deleted_event)
    weakened = deepcopy(DRAFT)
    weakened["external_fidelity_policy"]["native_reproduction_required"] = False
    with pytest.raises(ValueError, match="weakened"):
        validate_structure_two_gate_b_v0_6_draft(weakened)


def test_swapping_comparison_targets_or_rewriting_domain_fails_closed() -> None:
    swapped = deepcopy(DRAFT)
    swapped["comparison_pairs"][0]["right_arm"] = "o_star_matched"
    swapped["comparison_pairs"][1]["right_arm"] = "corrected_amg"
    with pytest.raises(ValueError, match="canonical comparison relation"):
        validate_structure_two_gate_b_v0_6_draft(swapped)
    rewritten = deepcopy(DRAFT)
    rewritten["comparison_pairs"][0]["domain"] = "attacker controlled domain"
    with pytest.raises(ValueError, match="canonical comparison relation"):
        validate_structure_two_gate_b_v0_6_draft(rewritten)


def test_replacing_external_fidelity_protocol_id_fails_closed() -> None:
    modified = deepcopy(DRAFT)
    modified["external_fidelity_policy"]["protocol"] = "attacker-protocol@999"
    with pytest.raises(ValueError, match="weakened"):
        validate_structure_two_gate_b_v0_6_draft(modified)
