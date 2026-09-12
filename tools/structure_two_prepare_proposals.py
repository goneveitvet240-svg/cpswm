"""Validate full proposal samples and prepare isolated feature/target files; never train."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.data_preflight.proposal_samples import (  # noqa: E402
    ProposalSample,
    audit_samples,
    export_sample,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, required=True, help="JSON array of full typed samples"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="new directory; never overwritten"
    )
    parser.add_argument("--allow-component-fixtures", action="store_true")
    args = parser.parse_args()
    raw = args.input.read_bytes()
    records = json.loads(raw)
    if not isinstance(records, list) or not records:
        raise ValueError("nonempty sample array required")
    samples = tuple(ProposalSample.model_validate(x) for x in records)
    if not args.allow_component_fixtures and any(
        x.annotation_kind == "component_fixture" for x in samples
    ):
        raise ValueError(
            "component fixtures are not training examples; explicit demonstration flag required"
        )
    report = audit_samples(samples)
    projections = [export_sample(x) for x in samples]
    args.output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for field, filename in (
        ("model_input", "features.jsonl"),
        ("training_targets", "targets.jsonl"),
        ("audit_only", "audit.jsonl"),
    ):
        payload = "".join(
            json.dumps(x[field], sort_keys=True, allow_nan=False) + "\n" for x in projections
        ).encode()
        with (args.output / filename).open("xb") as handle:
            handle.write(payload)
        hashes[filename] = hashlib.sha256(payload).hexdigest()
    report.update(
        input_sha256=hashlib.sha256(raw).hexdigest(),
        files_sha256=hashes,
        training_started=False,
        generated_model_artifact=False,
    )
    with (args.output / "readiness.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, sort_keys=True, indent=2)
    print(json.dumps({"samples": len(samples), "training_ready": False, "training_started": False}))


if __name__ == "__main__":
    main()
