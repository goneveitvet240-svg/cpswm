#!/usr/bin/env python3
"""Run the fresh A1+B1 direct-P5 matched three-arm development death test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cpswm.system.evaluation_operations.structure_two_p5_three_arm_death_test import (
    DEFAULT_OUTPUT,
    run_p5_three_arm_death_test,
    verify_p5_three_arm_death_test,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--fresh-verify", action="store_true")
    args = parser.parse_args()

    root = args.repository_root.resolve()
    if args.verify is not None:
        retained = args.verify if args.verify.is_absolute() else root / args.verify
        payload = json.loads(retained.read_text(encoding="utf-8"))
        verify_p5_three_arm_death_test(
            payload,
            repository_root=root,
            fresh_recompute=args.fresh_verify,
        )
        print(
            json.dumps(
                {
                    "verified": str(retained),
                    "status": payload["status"],
                    "content_sha256": payload["content_sha256"],
                },
                sort_keys=True,
            )
        )
        return
    payload = run_p5_three_arm_death_test(repository_root=root)
    verify_p5_three_arm_death_test(
        payload,
        repository_root=root,
        fresh_recompute=False,
    )
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output),
                "status": payload["status"],
                "content_sha256": payload["content_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
