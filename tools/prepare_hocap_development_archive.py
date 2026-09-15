"""Convert a pinned raw-only HO-Cap manifest to the existing continuous RGB-D entry.

The 100 ms ordinal spacing is an explicit development replay convention, not a
measurement of video time. This program never opens evaluator annotations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from cpswm.perception_mapping.adapters.hocap_rgbd import HOCapFrameSource, adapt_hocap_rgbd
from cpswm.system.reproducibility import content_sha256


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.manifest_sha256:
        raise ValueError("raw manifest differs from externally retained pin")
    rows = json.loads(raw)
    if type(rows) is not list or not rows:
        raise ValueError("nonempty raw-only frame list required")
    sources = [HOCapFrameSource(**row) for row in rows]
    identities = [(s.sequence_id, s.camera_id, s.frame_index) for s in sources]
    if len(set(identities)) != len(identities) or identities != sorted(identities):
        raise ValueError("duplicate or unordered source frames")
    root = args.raw_root.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    scope = uuid5(NAMESPACE_URL, "hocap-development:" + args.manifest_sha256)
    sequence_indices = {seq: i for i, seq in enumerate(sorted({s.sequence_id for s in sources}))}
    entries, captures = [], []
    for index, source in enumerate(sources):
        payloads = []
        for mode in ("rgb", "depth"):
            path = (root / source.member(mode)).resolve()
            if not path.is_relative_to(root):
                raise ValueError("raw member escapes root")
            payloads.append(path.read_bytes())
        when = datetime(2000, 1, 1, tzinfo=UTC) + timedelta(
            days=sequence_indices[source.sequence_id], milliseconds=100 * source.frame_index
        )
        source_pin = content_sha256(source)
        observations = adapt_hocap_rgbd(
            source,
            rgb_bytes=payloads[0],
            depth_bytes=payloads[1],
            expected_source_sha256=source_pin,
            household_id=scope,
            session_id=scope,
            trace_id=scope,
            capture_time=when,
            arrival_time=when,
        )
        capture_ref = f"hocap-frame-{index:06d}"
        captures.append({"capture_ref": capture_ref, "source_receipt_sha256": source_pin})
        for observation in observations:
            env = observation.envelope()
            for suffix, data in (
                ("json", observation.envelope_json.encode()),
                ("npy", observation.payload_bytes),
            ):
                filename = f"{index:06d}_{env.sensor.modality.value}.{suffix}"
                (args.output / filename).write_bytes(data)
                entries.append(
                    {
                        "file": filename,
                        "capture_ref": capture_ref,
                        "observation_id": str(env.identity.observation_id),
                        "size_bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
    receipt = {
        "source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "raw_manifest_sha256": args.manifest_sha256,
        "clock": "100ms_per_frame_ordinal_not_hardware_timing",
        "output_manifest": entries,
        "captures": captures,
    }
    path = args.output / "receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        json.dumps(
            {
                "frames": len(sources),
                "receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    )


if __name__ == "__main__":
    main()
