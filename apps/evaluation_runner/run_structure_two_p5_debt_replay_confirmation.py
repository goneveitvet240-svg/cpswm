#!/usr/bin/env python3
"""Run or verify the Structure-Two P5 production debt-replay confirmation."""

from __future__ import annotations

import argparse
import json

# Establish execution provenance before importing project dependencies.
import sys
import types
from pathlib import Path

_bootstrap_path = (
    Path(__file__).resolve().parents[2] / "apps/evaluation_runner/structure_two_source_bootstrap.py"
)
if "_cpswm_source_bootstrap" not in sys.modules:
    _bootstrap = types.ModuleType("_cpswm_source_bootstrap")
    _bootstrap.__file__ = str(_bootstrap_path)
    sys.modules[_bootstrap.__name__] = _bootstrap
    exec(compile(_bootstrap_path.read_bytes(), str(_bootstrap_path), "exec"), _bootstrap.__dict__)
sys.modules["_cpswm_source_bootstrap"].establish(Path(__file__).resolve().parents[2])

from cpswm.system.evaluation_operations.structure_two_evidence_publication import (  # noqa: E402
    publish_verified_json,
)
from cpswm.system.evaluation_operations.structure_two_evidence_versions import (  # noqa: E402
    require_current_output,
)
from cpswm.system.evaluation_operations.structure_two_p5_debt_replay_confirmation import (  # noqa: E402
    DEFAULT_OUTPUT,
    run_p5_debt_replay_confirmation,
    verify_p5_debt_replay_confirmation,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify", type=Path)
    parser.add_argument(
        "--fresh-verify", action="store_true", help="always required; retained compatibility option"
    )
    args = parser.parse_args()
    root = args.repository_root.resolve()
    if args.verify is not None:
        retained = args.verify if args.verify.is_absolute() else root / args.verify
        payload = json.loads(retained.read_text())
        verify_p5_debt_replay_confirmation(payload, repository_root=root)
        print(
            json.dumps(
                {
                    "verified": str(retained),
                    "status": payload["status"],
                    "content_sha256": payload["content_sha256"],
                }
            )
        )
        return
    require_current_output(root, args.output)
    payload = run_p5_debt_replay_confirmation(repository_root=root)
    output = publish_verified_json(
        root,
        args.output,
        payload,
        verify=lambda value: verify_p5_debt_replay_confirmation(value, repository_root=root),
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "status": payload["status"],
                "content_sha256": payload["content_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
