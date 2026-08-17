"""Independent process entry point for the Step 1 restart replay test."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# A restart worker is launched as a standalone script, so pytest's configured
# ``pythonpath = ["src"]`` does not apply in this independent interpreter.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cpswm.foundation.acceptance import AlignmentHandler
from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog, ReplayManifest
from cpswm.foundation.runtime_orchestration import (
    InProcessRuntime,
    ReplayRunner,
    build_version_bundle,
)


def main() -> None:
    if len(sys.argv) != 6:
        raise SystemExit(
            "usage: worker REPOSITORY_ROOT INPUT_LOG MANIFEST RUNTIME_SPEC OUTPUT"
        )
    repository_root = Path(sys.argv[1]).resolve()
    input_log = AppendOnlyTransactionLog.load(sys.argv[2])
    manifest = ReplayManifest.model_validate_json(
        Path(sys.argv[3]).read_text(encoding="utf-8")
    )
    runtime_spec = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
    versions = build_version_bundle(
        repository_root,
        configuration=runtime_spec["configuration"],
        model_versions=runtime_spec["model_versions"],
    )
    runtime = InProcessRuntime(
        transaction_log=AppendOnlyTransactionLog(),
        versions=versions,
        repository_root=repository_root,
        active_configuration=runtime_spec["configuration"],
    )
    runtime.register_command(
        "observation.align",
        handler_name="m02.align-observation",
        handler=AlignmentHandler(),
    )
    result = ReplayRunner().run(
        runtime=runtime,
        manifest=manifest,
        input_log=input_log,
    )
    Path(sys.argv[5]).write_text(result.model_dump_json(indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
