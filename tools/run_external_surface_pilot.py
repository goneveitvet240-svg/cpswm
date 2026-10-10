"""Run four readout arms on a frozen public panel; never read SDK ground truth.

This is an experimental adapter at the surface report boundary, not a complete
ConceptGraphs implementation or a production owner/active-policy integration.
Run the existing evaluator separately after all four arms have been sealed.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import io
import platform
import subprocess
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from external_components.surface_denoise_adapter import (
    EPS_M,
    MIN_POINTS,
    UPSTREAM_COMMIT,
    cluster_support,
    filtered_readout,
)
from run_matched_transition_death_test import (
    SCHEMA,
    FrozenDetector,
    _mask_bytes,
    checked,
    digest,
    load,
    raw_rows,
    save,
)

from cpswm.perception_mapping.mask_surface_sequence import MaskSurfaceSequence
from cpswm.perception_mapping.natural_mask_surface import select_surface
from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd
from cpswm.system.reproducibility import content_sha256
from cpswm.system.surface_episode import report_from_surface_state

ARMS = ("current", "cg_same_support", "mask_readout", "cg_mask_readout")


def adapt_record(
    record: dict[str, Any],
    camera: Any,
    depth: np.ndarray,
    masks: np.ndarray,
    component_python: Path,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    result = {arm: deepcopy(record) for arm in ARMS}
    candidates = {c["candidate_id"]: c for c in record["detector"]["candidates"]}
    denoised, diagnostics = {}, []
    for source_track in record["tracks"]:
        # Do not revive LOST or rematch identities in a position-only experiment.
        if source_track["world_point_m"] is None:
            continue
        key = source_track["current_candidate_id"]
        candidate = candidates[key]
        probability = masks[candidate["native_index"]]
        if key not in denoised:
            started = time.perf_counter()
            retained, counts = cluster_support(camera, depth, probability, component_python)
            denoised[key] = retained
            diagnostics.append(
                dict(
                    candidate_id=key,
                    category=candidate["category"],
                    elapsed_s=time.perf_counter() - started,
                    **counts,
                )
            )
        support = source_track["surface"]["support_uv"]
        support = None if support is None else tuple(tuple(p) for p in support)
        for arm in ARMS[1:]:
            track = next(
                t for t in result[arm]["tracks"] if t["anchor_id"] == source_track["anchor_id"]
            )
            if arm == "mask_readout":
                point = select_surface(camera, depth, probability)
            else:
                point = filtered_readout(
                    camera,
                    depth,
                    probability,
                    denoised[key],
                    support if arm == "cg_same_support" else None,
                )
            # A same-support filter which leaves the selected point in place must
            # retain its original lineage/readout, including reference-feature reid.
            if (
                arm == "cg_same_support"
                and tuple(source_track["selected_pixel_uv"]) in denoised[key]
            ):
                continue
            track.update(
                surface=point,
                selected_pixel_uv=point["selected_pixel_uv"],
                world_point_m=point["world_point_m"],
                selected_feature_ids=[],
                status="EXPERIMENTAL_READOUT_ONLY_" + point["status"],
            )
        # The owner profile is deliberately not produced by this adapter.
    for arm in ARMS[1:]:
        result[arm]["experimental_readout"] = dict(
            arm=arm,
            authority="none",
            upstream_commit=UPSTREAM_COMMIT,
            eps_m=EPS_M,
            min_points=MIN_POINTS,
            association_frozen=True,
        )
    return result, diagnostics


def run(root: Path, manifest_path: Path, output: Path, component_python: Path) -> None:
    if output.exists():
        raise ValueError("output directory must be new")
    manifest = load(manifest_path)
    if manifest.get("schema") != SCHEMA or manifest.get("input_sha256") != content_sha256(
        {k: v for k, v in manifest.items() if k != "input_sha256"}
    ):
        raise ValueError("manifest content binding differs")
    if len(manifest["frames"]) != manifest["budget"]:
        raise ValueError("frame budget differs")
    detector = FrozenDetector(root, manifest)
    sequence = MaskSurfaceSequence(detector)  # type: ignore[arg-type]
    histories: dict[str, list[Any]] = {arm: [] for arm in ARMS}
    steps: dict[str, list[Any]] = {arm: [] for arm in ARMS}
    diagnostics, action_ids = [], []
    for item in manifest["frames"]:
        raw = load(checked(root, item["raw"], item["raw_sha256"]))
        rows, cutoff = raw_rows(raw), datetime.fromisoformat(raw["received_at"])
        camera, depth = decode_unity_rgbd(rows, cutoff=cutoff)
        record, _ = sequence.observe(rows, cutoff=cutoff)
        masks = np.load(
            io.BytesIO(_mask_bytes(checked(root, item["masks"], item["masks_sha256"]))),
            allow_pickle=False,
        )
        records, diag = adapt_record(record, camera, depth, masks, component_python)
        diagnostics.append(dict(frame=item["index"], candidates=diag))
        action_ids.append(raw["action_id"])
        for arm, changed in records.items():
            histories[arm].append(changed)
            state = dict(
                view_sha256=content_sha256(changed),
                records=histories[arm],
                history={},
                action_ids=action_ids,
            )
            reports = [
                report_from_surface_state(
                    state,
                    category=q["category"],
                    ordinal=q["ordinal"],
                    reference_action=action_ids[0],
                )
                for q in manifest["queries"]
            ]
            steps[arm].append(
                dict(
                    index=item["index"],
                    action_id=item["action_id"],
                    record=changed,
                    reports=reports,
                )
            )
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    source_files = [
        Path(__file__),
        Path(__file__).parent / "external_components/conceptgraph_denoise.py",
        Path(__file__).parent / "external_components/surface_denoise_adapter.py",
        Path(__file__).parent / "external_components/run_denoise.py",
    ]
    for arm in ARMS:
        save(
            output / f"{arm}.json",
            dict(
                schema=SCHEMA,
                status="COMPLETED",
                arm=arm,
                code_sha=head,
                source_file_sha256=digest(Path(__file__)),
                manifest_sha256=digest(manifest_path),
                input_sha256=manifest["input_sha256"],
                budget=manifest["budget"],
                source_physical_dispatches=manifest["physical_dispatches"],
                replay_physical_dispatches=0,
                queries=manifest["queries"],
                schedule=manifest["schedule"],
                detector_runs=0,
                control=None,
                steps=steps[arm],
                scope="frozen association; experimental readout only; no memory/action authority",
            ),
        )
    save(
        output / "runtime.json",
        dict(
            python=platform.python_version(),
            platform=platform.platform(),
            versions={
                n: importlib.metadata.version(n)
                for n in ("numpy", "opencv-contrib-python", "pydantic")
            },
            source_files={p.name: digest(p) for p in source_files},
            inference_access="manifest and checked public raw/prediction/masks only; no SDK reads",
            diagnostics=diagnostics,
            output_sha256={arm: digest(output / f"{arm}.json") for arm in ARMS},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "manifest", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--component-python", required=True, type=Path)
    args = parser.parse_args()
    run(args.root, args.manifest, args.output, args.component_python)
