"""Generate and fresh-verify the matched direct-P5 three-arm readiness artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_p5_three_arm_readiness import (
    DEFAULT_OUTPUT,
    run_p5_three_arm_readiness,
    verify_p5_three_arm_readiness,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    result = run_p5_three_arm_readiness(repository_root=root)
    verify_p5_three_arm_readiness(result, repository_root=root, fresh_recompute=True)
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "content_sha256": result["content_sha256"]}))


if __name__ == "__main__":
    main()
