"""Fail explicitly while the production default full-joint backbone is incomplete.

This is an engineering capability probe, not a scientific test.  Exit code 2 means
the known default-path capability gaps were observed.  It must never be counted as a
green acceptance test merely because it detected the expected gaps.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path


def load_trace(path: Path) -> dict[str, object]:
    if path.suffix == ".gz":
        body = gzip.decompress(path.read_bytes())
        for encoding in ("utf-8", "cp936"):
            try:
                return json.loads(body.decode(encoding))
            except UnicodeDecodeError:
                continue
        raise UnicodeDecodeError("trace", body, 0, len(body), "unsupported JSON encoding")
    return json.loads(path.read_text(encoding="utf-8"))


def nonzero(value: object) -> bool:
    if isinstance(value, (int, float)):
        return abs(float(value)) > 0.0
    if isinstance(value, list):
        return any(nonzero(item) for item in value)
    if isinstance(value, dict):
        return any(nonzero(item) for item in value.values())
    return False


def main() -> int:
    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    trace = load_trace(source)
    steps = trace["steps"]
    calls = trace["calls"]
    rgrc = [row for row in calls if row["operator"] == "rgrc"]
    ciav = [row for row in calls if row["operator"] == "ciav"]

    particle_counts = [int(step["default_joint_particles"]) for step in steps]
    information_deltas = [
        delta["delta_information"]
        for row in rgrc
        for delta in row["input"]["deltas"]
    ]
    information_vector_deltas = [
        delta["delta_information_vector"]
        for row in rgrc
        for delta in row["input"]["deltas"]
    ]
    ciav_inputs = [row["input"] for row in ciav]
    ciav_input_text = json.dumps(ciav_inputs, ensure_ascii=False, sort_keys=True).lower()

    checks = {
        "default_joint_particles_nonempty": {
            "required_for_full_capability": True,
            "observed_counts": particle_counts,
            "observed": any(count > 0 for count in particle_counts),
        },
        "ordinary_information_rb_increment_nonzero": {
            "required_for_full_capability": True,
            "observed_delta_information": information_deltas,
            "observed_delta_information_vector": information_vector_deltas,
            "observed": nonzero(information_deltas) or nonzero(information_vector_deltas),
        },
        "ciav_consumes_full_particle_posterior": {
            "required_for_full_capability": True,
            "ciav_input_keys": sorted({key for item in ciav_inputs for key in item}),
            "particle_token_observed_in_ciav_input": "particle" in ciav_input_text,
            "observed": "particle" in ciav_input_text,
            "observed_input_kind": "StructureTwoCauseBelief / snapshot, not full particles",
        },
    }
    for item in checks.values():
        item["status"] = "IMPLEMENTED" if item["observed"] else "MISSING"

    payload = {
        "classification": "engineering capability gap probe; not scientific acceptance",
        "source_trace": source.name,
        "checks": checks,
        "all_required_capabilities_present": all(item["observed"] for item in checks.values()),
        "expected_exit_code_when_known_gaps_remain": 2,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    missing = [name for name, item in checks.items() if not item["observed"]]
    if missing:
        print("MISSING DEFAULT CAPABILITIES: " + ", ".join(missing))
        return 2
    print("all probed default capabilities are present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
