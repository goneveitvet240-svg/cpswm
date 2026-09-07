#!/usr/bin/env python3
"""Run deterministic local-only Task 13 and proposal-P5 diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.system.evaluation_operations.structure_two_task13_p5_diagnostic import (  # noqa: E402
    run_p5_local_diagnostic,
    run_task13_local_diagnostic,
)

DEFAULT_OUTPUT = ROOT / "benchmarks/structure_two/structure_two_task13_p5_local_v0_1.json"
TASK12_MANIFEST = (
    ROOT / "benchmarks/structure_two/task12_rejuvenation_diagnostic_2026_09_06/"
    "TASK12_EVIDENCE_MANIFEST.json"
)
SOURCE_PATHS = (
    "src/cpswm/system/evaluation_operations/structure_two_task13_p5_diagnostic.py",
    "apps/evaluation_runner/run_structure_two_task13_p5_diagnostic.py",
    "tests/test_structure_two_task13_p5_diagnostic.py",
)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_payload() -> dict[str, object]:
    task12_manifest = json.loads(TASK12_MANIFEST.read_text(encoding="utf-8"))
    unsigned_task12 = dict(task12_manifest)
    stored_task12_hash = unsigned_task12.pop("content_sha256", None)
    if stored_task12_hash != _canonical_sha256(unsigned_task12):
        raise ValueError("Task 12 manifest self-hash mismatch")
    for field in (
        "formal_task_12_passed",
        "formal_binding_resolved",
        "task_13_unlocked",
        "proposal_p5_unlocked",
        "seven_operator_ablation_authorized",
    ):
        if task12_manifest.get(field) is not False:
            raise ValueError(f"Task 12 manifest illegally unlocks Task 13/P5: {field}")
    task13 = run_task13_local_diagnostic()
    p5 = run_p5_local_diagnostic()
    payload: dict[str, object] = {
        "protocol": "structure-two-task13-p5-local-evidence@0.2",
        "evidence_status": "LOCAL_DIAGNOSTIC_ONLY",
        "upstream_task12_manifest": {
            "path": TASK12_MANIFEST.relative_to(ROOT).as_posix(),
            "file_sha256": _file_sha256(TASK12_MANIFEST),
            "content_sha256": stored_task12_hash,
            "formal_task_12_passed": False,
            "task_13_unlocked": False,
        },
        "source_hashes": {relative: _file_sha256(ROOT / relative) for relative in SOURCE_PATHS},
        "task_13": task13.model_dump(mode="json"),
        "proposal_p5": p5.model_dump(mode="json"),
        "formal_task_13_passed": False,
        "proposal_p5_unlocked": False,
        "seven_operator_ablation_authorized": False,
        "independent_custody_established": False,
        "claim_boundary": (
            "Task 13 and P5 algorithms were exercised locally, but Task 12 is formally false, "
            "no sealed holdout or independent custody exists, and no downstream selection or "
            "seven-operator superiority claim is authorized."
        ),
    }
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", type=Path)
    arguments = parser.parse_args()
    payload = build_payload()
    if arguments.verify is not None:
        stored = json.loads(arguments.verify.read_text(encoding="utf-8"))
        if stored != payload:
            raise ValueError("Task 13/P5 artifact differs from current source-bound recomputation")
        print(f"verified={arguments.verify}")
        return
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    task13 = payload["task_13"]
    p5 = payload["proposal_p5"]
    print(f"output={arguments.output}")
    print(f"task13_status={task13['status']}")
    print(f"p5_status={p5['status']}")
    print(f"p5_diagnosis={p5['diagnosis']}")


if __name__ == "__main__":
    main()
