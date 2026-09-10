#!/usr/bin/env python3
"""Generate or freshly verify the Structure-Two action/utility construct gate."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from cpswm.system.evaluation_operations.structure_two_action_utility_construct_gate import (  # noqa: E402
    DEFAULT_OUTPUT,
    run_action_utility_construct_gate,
    verify_action_utility_construct_gate,
)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonstandard_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON numeric constant: {value}")


def _load(path: Path) -> dict[str, object]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonstandard_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("construct-gate artifact must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()

    if args.verify is not None:
        verify_path = args.verify if args.verify.is_absolute() else REPOSITORY_ROOT / args.verify
        artifact = _load(verify_path)
        verify_action_utility_construct_gate(
            artifact,
            repository_root=REPOSITORY_ROOT,
            fresh_recompute=True,
        )
        print(f"verified {verify_path}")
        return 0

    output = args.output if args.output.is_absolute() else REPOSITORY_ROOT / args.output
    artifact = run_action_utility_construct_gate(repository_root=REPOSITORY_ROOT)
    verify_action_utility_construct_gate(
        artifact,
        repository_root=REPOSITORY_ROOT,
        fresh_recompute=True,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    counts = cast(Mapping[str, object], artifact["diagnostic_counts"])
    print(
        f"passed={artifact['action_utility_construct_gate_passed']} "
        "selected_location_disagreement_steps="
        f"{counts['selected_location_disagreement_step_count']} "
        f"successful_non_noop={counts['successful_non_noop_put_back_transition_count']} "
        f"search_control={counts['search_sensitivity_positive_control_count']} "
        f"put_back_control={counts['put_back_sensitivity_positive_control_count']} "
        f"successful_wrong={counts['successful_wrong_put_back_control_count']} "
        f"output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
