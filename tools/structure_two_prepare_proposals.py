"""Validate full proposal samples and prepare isolated feature/target files; never train."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.data_preflight.prepared_samples import write_prepared_samples  # noqa: E402
from cpswm.data_preflight.proposal_samples import (  # noqa: E402
    ProposalSample,
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
    write_prepared_samples(samples, args.output, input_sha256=hashlib.sha256(raw).hexdigest())
    print(json.dumps({"samples": len(samples), "training_ready": False, "training_started": False}))


if __name__ == "__main__":
    main()
