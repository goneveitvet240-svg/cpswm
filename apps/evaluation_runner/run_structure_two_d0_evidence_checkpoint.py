#!/usr/bin/env python3
"""Produce and verify the frozen Structure Two D0 Task 7/8/10 evidence set.

The scientific payload contains wall-clock observations, which cannot be byte
reproduced.  The envelope therefore binds both the exact stored artifact and a
deterministic projection that removes timing fields.  A fresh run must match
the deterministic projection before it can be called recomputed evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[2]
SOURCE_ROOT: Final = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cpswm.system.evaluation_operations.structure_two_backbone_falsifier import (  # noqa: E402
    ArmName,
    run_budget_sweep,
    run_joint_coupling_death_test,
    run_late_correction_study,
)

DEFAULT_OUTPUT_DIR: Final = (
    REPOSITORY_ROOT / "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_05"
)
PROTOCOL_PATH: Final = Path("docs/结构二/方向结构二_骨干尺度证伪器协议_v0.1.md")
TASK10_CONFIG_PATH: Final = Path(
    "configs/project_two_experiments/structure_two_task10_particle_budget_v0_1.json"
)
TASK10_CONFIG_SHA256: Final = "331782935673ccd4d9fa8a8cda2015078d828bd64001882e57598d651ee027dc"
SOURCE_PATHS: Final = (
    Path("src/cpswm/system/evaluation_operations/structure_two_backbone_falsifier.py"),
    Path("apps/evaluation_runner/run_structure_two_d0_evidence_checkpoint.py"),
    TASK10_CONFIG_PATH,
)
TIMING_FIELDS: Final = frozenset(
    {
        "elapsed_seconds",
        "marginal_wall_clock_seconds",
        "mean_wall_clock_seconds",
        "seconds",
        "wall_clock_seconds",
    }
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _source_bundle(repository_root: Path) -> dict[str, object]:
    files = [
        {"path": path.as_posix(), "sha256": _sha256(repository_root / path)}
        for path in SOURCE_PATHS
    ]
    return {
        "protocol": "structure-two-d0-source-bundle@0.1",
        "files": files,
        "content_sha256": _canonical_sha256(files),
    }


def _task10_config() -> dict[str, Any]:
    path = REPOSITORY_ROOT / TASK10_CONFIG_PATH
    if _sha256(path) != TASK10_CONFIG_SHA256:
        raise ValueError("Task-10 frozen config drift")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Task-10 frozen config must be a JSON object")
    if payload.get("protocol_id") != "structure-two-backbone-particle-budget-task-10@0.1":
        raise ValueError("Task-10 protocol substitution")
    if payload.get("status") != "FROZEN_FOR_D0_RECOMPUTATION":
        raise ValueError("Task-10 config is not frozen for recomputation")
    if payload.get("formal_task_10_passed") is not False:
        raise ValueError("Task-10 diagnostic config cannot self-authorize a formal pass")
    return payload


def deterministic_projection(value: object) -> object:
    """Remove measurements that are expected to vary across honest reruns."""

    if isinstance(value, Mapping):
        return {
            str(key): deterministic_projection(item)
            for key, item in value.items()
            if key not in TIMING_FIELDS
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [deterministic_projection(item) for item in value]
    return value


def _positive_boolean_paths(value: object, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            paths.extend(_positive_boolean_paths(item, f"{prefix}/{escaped}"))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            paths.extend(_positive_boolean_paths(item, f"{prefix}/{index}"))
    elif value is True:
        paths.append(prefix or "/")
    return paths


def make_envelope(*, result: dict[str, Any], command: Sequence[str]) -> dict[str, object]:
    deterministic = deterministic_projection(result)
    positive_paths = _positive_boolean_paths(result)
    payload: dict[str, object] = {
        "protocol": "structure-two-d0-recomputable-evidence-envelope@0.2",
        "evidence_level": "D0_SYNTHETIC_DEVELOPMENT",
        "claim_boundary": (
            "Recomputation establishes deterministic D0 engineering evidence only; "
            "it does not establish external validity or method superiority."
        ),
        "producer_source_bundle": _source_bundle(REPOSITORY_ROOT),
        "protocol_document": {
            "path": PROTOCOL_PATH.as_posix(),
            "sha256": _sha256(REPOSITORY_ROOT / PROTOCOL_PATH),
        },
        "runner_argv": list(command),
        "deterministic_result_sha256": _canonical_sha256(deterministic),
        "positive_output_trust_chain": {
            path: (
                "artifact_content+source_bundle+protocol_document+"
                "fresh_task_specific_recomputation_required"
            )
            for path in positive_paths
        },
        "result": result,
    }
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


def verify_envelope(
    payload: Mapping[str, object],
    *,
    repository_root: Path = REPOSITORY_ROOT,
    fresh_result: Mapping[str, object] | None = None,
) -> None:
    unsigned = dict(payload)
    stored_content_sha256 = unsigned.pop("content_sha256", None)
    if stored_content_sha256 != _canonical_sha256(unsigned):
        raise ValueError("D0 evidence envelope content hash mismatch")
    if payload.get("producer_source_bundle") != _source_bundle(repository_root):
        raise ValueError("D0 evidence producer source bundle drift")
    expected_protocol = {
        "path": PROTOCOL_PATH.as_posix(),
        "sha256": _sha256(repository_root / PROTOCOL_PATH),
    }
    if payload.get("protocol_document") != expected_protocol:
        raise ValueError("D0 evidence protocol document drift")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("D0 evidence result is missing")
    expected_positive = {
        path: (
            "artifact_content+source_bundle+protocol_document+"
            "fresh_task_specific_recomputation_required"
        )
        for path in _positive_boolean_paths(result)
    }
    if payload.get("positive_output_trust_chain") != expected_positive:
        raise ValueError("D0 evidence positive-output trust chain is incomplete")
    if payload.get("deterministic_result_sha256") != _canonical_sha256(
        deterministic_projection(result)
    ):
        raise ValueError("D0 evidence deterministic result hash mismatch")
    if fresh_result is None:
        raise ValueError("fresh task-specific recomputation is required")
    if deterministic_projection(fresh_result) != deterministic_projection(result):
        raise ValueError("fresh task-specific recomputation does not match the D0 artifact")


def _task_7() -> tuple[str, dict[str, Any], tuple[str, ...]]:
    command = ("--task", "7")
    result = run_late_correction_study(
        gaps=3,
        correction_index=1,
        scenario_seeds=(11, 23, 37, 41, 53),
        arm=ArmName.ADAPTIVE_TYPED_RBPF,
        budget=384,
        replicate_seeds=(101, 202, 303),
    )
    return "task_7_late_correction.json", result, command


def _task_8(gaps: int) -> tuple[str, dict[str, Any], tuple[str, ...]]:
    command = ("--task", "8", "--gaps", str(gaps))
    seeds = (11, 23, 37, 41, 53) if gaps == 1 else (11,)
    result = {
        "protocol_id": "structure-two-backbone-falsifier@0.1",
        "task": "task-8-joint-coupling-death-test",
        "gaps": gaps,
        "partitions": {
            "H": run_joint_coupling_death_test(
                gaps=gaps,
                scenario_seeds=seeds,
                include_regime_in_event=False,
            ),
            "H+Z": run_joint_coupling_death_test(
                gaps=gaps,
                scenario_seeds=seeds,
                include_regime_in_event=True,
            ),
        },
    }
    return f"task_8_joint_coupling_g{gaps}.json", result, command


def _task_10(gaps: int) -> tuple[str, dict[str, Any], tuple[str, ...]]:
    command = ("--task", "10", "--gaps", str(gaps))
    config = _task10_config()
    designs = config.get("designs")
    if not isinstance(designs, Mapping):
        raise ValueError("Task-10 frozen designs are missing")
    design = designs.get(f"g{gaps}")
    if not isinstance(design, Mapping) or design.get("gaps") != gaps:
        raise ValueError("Task-10 requested gaps are not frozen")
    result = run_budget_sweep(
        gaps=gaps,
        scenario_seeds=tuple(int(value) for value in design["scenario_seeds"]),
        budgets=tuple(int(value) for value in design["budgets"]),
        replicate_seeds=tuple(int(value) for value in design["replicate_seeds"]),
        state_budget=int(design["state_budget"]),
    )
    result["task"] = "task-10-particle-budget-sweep"
    result["task_10_definition_and_rerun_complete"] = True
    result["formal_task_10_passed"] = False
    result["seven_operator_efficacy_authorized"] = False
    result["claim_boundary"] = config["claim_boundary"]
    return f"task_10_budget_sweep_g{gaps}.json", result, command


def _fresh_result_for_command(command: Sequence[str]) -> dict[str, Any]:
    frozen = tuple(command)
    if frozen == ("--task", "7"):
        return _task_7()[1]
    if len(frozen) == 4 and frozen[:2] == ("--task", "8") and frozen[2] == "--gaps":
        return _task_8(int(frozen[3]))[1]
    if len(frozen) == 4 and frozen[:2] == ("--task", "10") and frozen[2] == "--gaps":
        return _task_10(int(frozen[3]))[1]
    raise ValueError("unsupported D0 recomputation command")


def _write(output_dir: Path, item: tuple[str, dict[str, Any], tuple[str, ...]]) -> Path:
    name, result, command = item
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / name
    envelope = make_envelope(result=result, command=command)
    # A second, task-specific execution defeats an attacker who synchronously
    # rewrites the result and every self-consistency hash in the envelope.
    verify_envelope(envelope, fresh_result=_fresh_result_for_command(command))
    path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=("7", "8", "10", "all"), default="all")
    parser.add_argument("--gaps", type=int, choices=(1, 2))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    jobs: list[tuple[str, dict[str, Any], tuple[str, ...]]] = []
    if args.task in {"7", "all"}:
        jobs.append(_task_7())
    if args.task in {"8", "all"}:
        gaps_values = (args.gaps,) if args.gaps else (1, 2)
        jobs.extend(_task_8(gaps) for gaps in gaps_values)
    if args.task in {"10", "all"}:
        gaps_values = (args.gaps,) if args.gaps else (1, 2)
        jobs.extend(_task_10(gaps) for gaps in gaps_values)
    for job in jobs:
        print(_write(args.output_dir, job))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
