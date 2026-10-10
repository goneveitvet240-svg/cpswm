"""Pinned learned mapping on an authenticated public capture panel."""

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

from run_matched_transition_death_test import (
    SCHEMA,
    FrozenDetector,
    checked,
    digest,
    load,
    raw_rows,
    save,
)

from cpswm.perception_mapping.external_object_sequence import (
    MappingClient,
    prepare_frame,
    records_from_mapping,
    reference_fallback,
)
from cpswm.perception_mapping.mask_surface_sequence import MaskSurfaceSequence
from cpswm.system.reproducibility import content_sha256
from cpswm.system.surface_episode import report_from_surface_state


def run(args):
    if args.output.exists():
        raise ValueError("new output directory required")
    args.output.mkdir(parents=True)
    manifest = load(args.manifest)
    if manifest["input_sha256"] != content_sha256(
        {k: v for k, v in manifest.items() if k != "input_sha256"}
    ):
        raise ValueError("manifest differs")
    frozen = FrozenDetector(args.root, manifest)
    prepared, detectors, reference_records = [], [], []
    reference_sequence = MaskSurfaceSequence(FrozenDetector(args.root, manifest))
    for item in manifest["frames"]:
        raw = load(checked(args.root, item["raw"], item["raw_sha256"]))
        rows, cutoff = raw_rows(raw), datetime.fromisoformat(raw["received_at"])
        frame = frozen.infer_surface(rows, cutoff=cutoff)
        prepared.append(prepare_frame(args.output, rows, cutoff, frame))
        detectors.append(frame.record)
        reference_records.append(reference_sequence.observe(rows, cutoff=cutoff)[0])
    started = time.perf_counter()
    client = MappingClient(args.component_python, args.weights)
    for mode in args.spatial:
        mapped = client.run(prepared, spatial="iou" if mode in ("hybrid", "current") else mode)
        records = records_from_mapping(detectors, prepared, mapped)
        if mode == "current":
            records = reference_records
        if mode == "hybrid":
            records = [
                reference_fallback(m, r) for m, r in zip(records, reference_records, strict=True)
            ]
        steps, actions = [], []
        for index, record in enumerate(records):
            actions.append(manifest["frames"][index]["action_id"])
            state = dict(
                view_sha256=content_sha256(record),
                records=records[: index + 1],
                history={},
                action_ids=actions,
            )
            reports = [
                report_from_surface_state(state, **q, reference_action=actions[0])
                for q in manifest["queries"]
            ]
            steps.append(dict(index=index, action_id=actions[-1], record=record, reports=reports))
        save(
            args.output / f"{mode}.json",
            dict(
                schema=SCHEMA,
                status="COMPLETED",
                arm=mode,
                code_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                source_files={
                    str(p): digest(p)
                    for p in (
                        Path(__file__),
                        *Path(__file__).parent.joinpath("external_components").glob("object*.py"),
                    )
                },
                manifest_sha256=digest(args.manifest),
                input_sha256=manifest["input_sha256"],
                queries=manifest["queries"],
                budget=manifest["budget"],
                schedule=manifest["schedule"],
                source_physical_dispatches=manifest["physical_dispatches"],
                replay_physical_dispatches=0,
                detector_runs=0,
                control=None,
                steps=steps,
            ),
        )
        save(
            args.output / f"{mode}-runtime.json", {k: v for k, v in mapped.items() if k != "steps"}
        )
        print(json.dumps(dict(mode=mode, seconds=time.perf_counter() - started)), flush=True)
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "manifest", "output", "component-python", "weights"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument(
        "--spatial",
        nargs="+",
        choices=("iou", "overlap_aabb", "hybrid", "current"),
        default=["iou"],
    )
    run(parser.parse_args())
