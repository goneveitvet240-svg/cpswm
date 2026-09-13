"""Replay selected, committed simulator captures into the raw M05 input format.

An archival input-boundary check, not a new simulator run or semantic inference.
The method-facing output contains no evaluator metadata or filesystem pointers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from cpswm.perception_mapping.adapters.rgbd_capture import adapt_raw_rgbd_capture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-path", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}", args.source_sha) is None:
        raise ValueError("full committed source SHA required")
    root = args.source_root.resolve()

    def frozen(path):
        return subprocess.check_output(["git", "show", f"{args.source_sha}:{path}"], cwd=root)

    run = args.run_path
    journal_raw = frozen(run + "/schedule_run/observation_candidates/release_journal.json")
    journal = json.loads(journal_raw)
    args.output.mkdir(parents=True, exist_ok=False)
    observations = args.output / "observations"
    observations.mkdir()
    capture_manifest = json.loads(frozen(run + "/schedule_run/evaluator_only/raw/manifest.json"))
    reports = []
    seen = set()
    namespace = uuid5(NAMESPACE_URL, "cpswm-archived-raw-import:" + args.source_sha + ":" + run)
    for release in sorted(
        journal, key=lambda x: (x["received_tick"], x["event_tick"], x["capture_ref"])
    ):
        ref = release["capture_ref"]
        if re.fullmatch(r"[0-9]{6}\.json", ref) is None or ref in seen:
            raise ValueError("invalid or duplicate released capture")
        if (
            set(release) != {"capture_ref", "event_tick", "received_tick"}
            or type(release["event_tick"]) is not int
            or type(release["received_tick"]) is not int
            or not 0 <= release["event_tick"] <= release["received_tick"]
        ):
            raise ValueError("invalid recorded release clocks")
        seen.add(ref)
        raw_path = run + "/schedule_run/evaluator_only/raw/observations/" + ref
        receipt = frozen(raw_path)
        sensor = frozen(raw_path.removesuffix(".json") + ".npz")
        # This is actual archive-import arrival, not an invented historical UTC clock.
        delivered = datetime.now(UTC)
        rows = adapt_raw_rgbd_capture(
            receipt_bytes=receipt,
            sensor_bytes=sensor,
            expected_receipt_sha256=hashlib.sha256(receipt).hexdigest(),
            expected_run_id=capture_manifest["run_id"],
            household_id=namespace,
            session_id=namespace,
            trace_id=namespace,
            sensor_id="archived-primary-camera",
            frame_id="camera-optical",
            delivered_at=delivered,
            cutoff=delivered,
        )
        for row in rows:
            envelope = row.envelope()
            name = str(envelope.identity.observation_id)
            (observations / (name + ".json")).write_text(row.envelope_json + "\n")
            (observations / (name + ".npy")).write_bytes(row.payload_bytes)
        reports.append(
            {
                "capture_ref": ref,
                "source_receipt_sha256": hashlib.sha256(receipt).hexdigest(),
                "sensor_sha256": hashlib.sha256(sensor).hexdigest(),
                "modalities": len(rows),
                "recorded_event_tick": release["event_tick"],
                "recorded_received_tick": release["received_tick"],
            }
        )
    report = {
        "source_sha": args.source_sha,
        "source_run": run,
        "journal_sha256": hashlib.sha256(journal_raw).hexdigest(),
        "captures": reports,
        "selected_capture_count": len(reports),
        "observation_count": sum(x["modalities"] for x in reports),
        "execution_kind": "archived_raw_ingress_replay",
        "new_simulator_run": False,
        "semantic_detector_verified": False,
        "default_joint_runtime_verified": False,
    }
    (args.output / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "captures"}))


if __name__ == "__main__":
    main()
