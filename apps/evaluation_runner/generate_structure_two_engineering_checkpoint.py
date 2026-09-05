#!/usr/bin/env python3
"""Revoke the legacy self-consistency checkpoint after forged-path testing."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[2]
RESULT_DIR: Final = ROOT / "benchmarks/structure_two/d0_engineering_checkpoint_2026_09_04"
DEFAULT_OUTPUT: Final = RESULT_DIR / "checkpoint_manifest.json"
RESULT_NAMES: Final = (
    "task_7_late_correction.json",
    "task_8_joint_coupling_g1.json",
    "task_8_joint_coupling_g2.json",
    "task_10_budget_sweep_g1.json",
    "task_10_budget_sweep_g2.json",
)
REPLACEMENT_RESULT_PATHS: Final = (
    Path(
        "benchmarks/structure_two/backbone_b_repairs_2026_09_04/"
        "task_7_windowed_rejuvenation_v0_4.json"
    ),
    Path(
        "benchmarks/structure_two/backbone_b_repairs_2026_09_04/"
        "task_8_matched_three_arm_confirmatory_v0_4.json"
    ),
)
BOUND_PATHS: Final = (
    Path("apps/evaluation_runner/run_structure_two_d0_evidence_checkpoint.py"),
    Path("apps/evaluation_runner/run_structure_two_backbone_b_repairs.py"),
    Path("src/cpswm/system/evaluation_operations/structure_two_backbone_falsifier.py"),
    Path("tests/test_structure_two_backbone_falsifier.py"),
    Path("tests/test_structure_two_d0_evidence_checkpoint.py"),
    Path("tests/test_structure_two_backbone_b_repairs.py"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def build_checkpoint() -> dict[str, object]:
    results: list[dict[str, object]] = []
    for name in RESULT_NAMES:
        path = RESULT_DIR / name
        row: dict[str, object] = {
            "path": path.relative_to(ROOT).as_posix(),
            "present": path.is_file(),
            "trust_chain_complete": False,
            "revocation_reason": (
                "legacy verifier accepted forged-but-complete self-consistent envelopes"
            ),
        }
        if path.is_file():
            legacy_payload = json.loads(path.read_text(encoding="utf-8"))
            row.update(
                {
                    "file_sha256": _sha256(path),
                    "legacy_content_sha256": legacy_payload.get("content_sha256"),
                    "legacy_deterministic_result_sha256": legacy_payload.get(
                        "deterministic_result_sha256"
                    ),
                }
            )
        results.append(row)
    replacements = [
        {
            "path": path.as_posix(),
            "file_sha256": _sha256(ROOT / path),
            "fresh_task_specific_recomputation_required": True,
            "seven_operator_efficacy_authorized": False,
        }
        for path in REPLACEMENT_RESULT_PATHS
    ]
    bound_files = [
        {"path": path.as_posix(), "sha256": _sha256(ROOT / path)} for path in BOUND_PATHS
    ]
    payload: dict[str, object] = {
        "protocol": "structure-two-engineering-trust-checkpoint-revocation@0.2",
        "freeze_date": "2026-09-04",
        "status": "REVOKED_SUPERSEDED_BY_BACKBONE_B_REPAIRS",
        "recomputable_d0_evidence_allowed": False,
        "external_validity_established": False,
        "method_superiority_established": False,
        "external_immutable_anchor_present": False,
        "historical_v0_5_source_bundle_compatible_with_current_tree": False,
        "claim_boundary": (
            "The five legacy Task 7/8/10 slots are not a trusted checkpoint: their old "
            "verifier checked only self-consistency and one slot was never produced. "
            "Task 7/8 replacement artifacts require fresh task-specific recomputation; "
            "Task 10 remains outside this repair and no seven-operator claim is authorized."
        ),
        "results": results,
        "replacement_results": replacements,
        "bound_files": bound_files,
    }
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


def verify_checkpoint(payload: dict[str, object]) -> None:
    expected = build_checkpoint()
    if payload != expected:
        raise ValueError("Structure Two engineering checkpoint drift")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_checkpoint()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(payload["content_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
