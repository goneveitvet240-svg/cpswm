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
    object_type = subprocess.check_output(
        ["git", "--no-replace-objects", "cat-file", "-t", args.source_sha], cwd=root, text=True
    ).strip()
    if object_type != "commit":
        raise ValueError("source SHA must name a commit, not another Git object")

    def frozen(path):
        return subprocess.check_output(
            ["git", "--no-replace-objects", "show", f"{args.source_sha}:{path}"], cwd=root
        )

    run = args.run_path
    journal_raw = frozen(run + "/schedule_run/observation_candidates/release_journal.json")
    journal = json.loads(journal_raw)
    args.output.mkdir(parents=True, exist_ok=False)
    observations = args.output / "observations"
    observations.mkdir()
    capture_manifest = json.loads(frozen(run + "/schedule_run/evaluator_only/raw/manifest.json"))
    reports = []
    seen = set()
    observed_ids = set()
    output_manifest = []
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
        receipt_record = json.loads(receipt)
        index = receipt_record["step_index"]
        if (
            type(index) is not int
            or index < 0
            or ref != f"{index:06d}.json"
            or receipt_record["sensor_file"] != f"{index:06d}.npz"
        ):
            raise ValueError("released reference differs from capture identity")
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
            if name in observed_ids:
                raise ValueError("duplicate observation identity")
            observed_ids.add(name)
            encoded = (row.envelope_json + "\n").encode("utf-8")
            for suffix, payload in ((".json", encoded), (".npy", row.payload_bytes)):
                filename = name + suffix
                with (observations / filename).open("xb") as handle:
                    handle.write(payload)
                output_manifest.append(
                    {
                        "capture_ref": ref,
                        "observation_id": name,
                        "file": "observations/" + filename,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "size_bytes": len(payload),
                    }
                )
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
    expected_files = {row["file"].removeprefix("observations/") for row in output_manifest}
    if (
        len(observed_ids) != sum(x["modalities"] for x in reports)
        or len(output_manifest) != 2 * len(observed_ids)
        or {p.name for p in observations.iterdir()} != expected_files
    ):
        raise ValueError("output identity or count differs from emitted observations")
    report = {
        "source_sha": args.source_sha,
        "source_run": run,
        "journal_sha256": hashlib.sha256(journal_raw).hexdigest(),
        "captures": reports,
        "output_manifest": output_manifest,
        "selected_capture_count": len(reports),
        "observation_count": sum(x["modalities"] for x in reports),
        "execution_kind": "archived_raw_ingress_replay",
        "new_simulator_run": False,
        "semantic_detector_verified": False,
        "default_joint_runtime_verified": False,
    }
    (args.output / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k not in ("captures", "output_manifest")}))


if __name__ == "__main__":
    main()
