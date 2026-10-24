"""Regenerate the frozen-input reference and sampled paths at the recorded source SHA."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from run_short_history_reference import ROOT, run

from cpswm.system.reproducibility import canonical_json, content_sha256

TIMINGS = {"seconds", "seconds_including_worlds_readout_and_trace"}


def deterministic_payload(value):
    if isinstance(value, dict):
        return {k: deterministic_payload(v) for k, v in value.items() if k not in TIMINGS}
    if isinstance(value, (list, tuple)):
        return [deterministic_payload(x) for x in value]
    return value


def verify_replayed_run(recorded, regenerated):
    if canonical_json(deterministic_payload(recorded)) != canonical_json(
        deterministic_payload(regenerated)
    ):
        raise ValueError("reference/input/sampled-path replay differs")


def verify_traces(directory, recorded):
    seen = set()
    for row in recorded["rows"]:
        name = row["reference"]["posterior_trace"]
        if (
            not isinstance(name, str)
            or name != Path(name).name
            or name in {".", ".."}
            or name in seen
        ):
            raise ValueError("invalid or repeated posterior trace path")
        seen.add(name)
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("posterior trace must be an owned regular file")
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != row["reference"]["posterior_trace_sha256"]:
            raise ValueError("posterior trace changed")
    return len(seen)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--replay-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads((args.directory / "report.json").read_text())
    if set(data) != {
        "protocol",
        "source_sha",
        "git_status",
        "python",
        "platform",
        "evidence_level",
        "run",
        "content_sha256",
    }:
        raise ValueError("report schema changed")
    expected = data.pop("content_sha256")
    if content_sha256(data) != expected:
        raise ValueError("report content hash changed")
    source = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if source != data["source_sha"] or data["git_status"] != "" or status != "":
        raise ValueError("replay requires the same clean source SHA")
    if data["protocol"] != "native-two-step-projection-reference-v1" or data["evidence_level"] != (
        "bounded_native_projection_target_not_generative_model_validation"
    ):
        raise ValueError("invalid protocol or claim boundary")
    count = verify_traces(args.directory, data["run"])
    args.replay_output.mkdir(parents=True, exist_ok=False)
    regenerated = run(args.replay_output)
    verify_replayed_run(data["run"], regenerated)
    args.output.write_text(
        json.dumps(
            {
                "status": "SOURCE_BOUND_REPLAY_VERIFIED",
                "source_sha": source,
                "trace_files": count,
                "reference_rows": len(regenerated["rows"]),
                "sampled_method_rows": sum(len(r["methods"]) for r in regenerated["rows"]),
                "timing_fields_excluded": sorted(TIMINGS),
                "scope": "same-environment deterministic replay; shared model implementation",
                "independent_scientific_review": False,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
