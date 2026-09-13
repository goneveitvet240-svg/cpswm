"""Run scoped data diagnostics/export. No training or confirmation-set access."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from cpswm.contracts.habit_learning import (
    ActorResponsibilityEvidence,
    ObservationDetectionResult,
    ObservationOpportunityRecord,
)
from cpswm.data_preflight.simulator_capture import simulator_preflight
from cpswm.data_preflight.train_coverage import audit_train_worlds
from cpswm.data_preflight.visible_prefix import export_visible_prefix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("coverage", "export-visible", "simulator-preflight"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--cutoff")
    args = parser.parse_args()
    # Fail before reading/generating input when the output already exists.
    if args.output.exists():
        parser.error("output already exists; choose a new evidence path")
    if args.command == "coverage":
        result = audit_train_worlds(Path(__file__).resolve().parents[1])
    elif args.command == "simulator-preflight":
        result = simulator_preflight()
    else:
        if args.input is None or args.cutoff is None:
            parser.error("export-visible requires --input and --cutoff")
        raw = args.input.read_bytes()
        source = json.loads(raw)
        expected = {"partition", "opportunities", "detections", "actor_evidence", "received_at"}
        if set(source) != expected or source["partition"] not in {"development", "train"}:
            raise ValueError("only explicit train/development visible envelopes are accepted")
        view = export_visible_prefix(
            tuple(ObservationOpportunityRecord.model_validate(x) for x in source["opportunities"]),
            tuple(ObservationDetectionResult.model_validate(x) for x in source["detections"]),
            actor_evidence=tuple(
                ActorResponsibilityEvidence.model_validate(x) for x in source["actor_evidence"]
            ),
            received_at={
                UUID(k): datetime.fromisoformat(v) for k, v in source["received_at"].items()
            },
            cutoff=datetime.fromisoformat(args.cutoff),
        )
        result = {
            "model_input": view.model_input(),
            "audit_only": {
                "input_sha256": hashlib.sha256(raw).hexdigest(),
                "declared_partition": source["partition"],
                "partition_custody_verified": False,
                "prefix": json.loads(view.provenance_json),
            },
        }
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
    print(args.output)
    if args.command == "simulator-preflight" and not result["real_simulator_run_verified"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
