"""Pin raw HO-Cap and detector replay; retain partial geometry in one continuous entry.

Only camera intrinsics and raw manifests are read. No evaluator labels/poses.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import yaml

from cpswm.perception_mapping.adapters.hocap_rgbd import HOCapFrameSource, adapt_hocap_rgbd
from cpswm.perception_mapping.natural_geometry import NaturalGeometryProducer, PinholeIntrinsics
from cpswm.perception_mapping.natural_vision import DetectionCandidate, VisualFrame
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.structure_two_production_system import StructureTwoProductionSystem


def pinned(path: Path, digest: str) -> bytes:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"input differs from external pin: {path}")
    return data


def frame_from_json(row: dict) -> VisualFrame:
    row = dict(row)
    for key in ("observation_id", "household_id", "session_id", "trace_id"):
        row[key] = UUID(row[key])
    for key in ("capture_time", "arrival_time", "inference_cutoff"):
        row[key] = datetime.fromisoformat(row[key])
    row["candidates"] = tuple(
        DetectionCandidate(
            UUID(c["candidate_id"]), c["category"], c["detector_score"], tuple(c["box_xyxy"])
        )
        for c in row["candidates"]
    )
    return VisualFrame(**row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("raw-root", "raw-manifest", "frames", "intrinsics", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("raw-manifest-sha256", "frames-sha256", "intrinsics-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source_paths = (
        Path(__file__).resolve(),
        Path(__file__).resolve().parents[1] / "src/cpswm/perception_mapping/natural_geometry.py",
    )
    source_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    frames = tuple(
        frame_from_json(row) for row in json.loads(pinned(args.frames, args.frames_sha256))
    )
    sources = tuple(
        HOCapFrameSource(**row)
        for row in json.loads(pinned(args.raw_manifest, args.raw_manifest_sha256))
    )
    config = yaml.safe_load(pinned(args.intrinsics, args.intrinsics_sha256))
    color = config["color"]
    intrinsics = PinholeIntrinsics(
        str(config["serial"]),
        color["width"],
        color["height"],
        color["fx"],
        color["fy"],
        color["ppx"],
        color["ppy"],
        args.intrinsics_sha256,
        tuple(color["coeffs"]),
    )
    scope = uuid5(NAMESPACE_URL, "hocap-development:" + args.raw_manifest_sha256)
    if len(sources) != len(frames):
        raise ValueError("source and prediction coverage differ")
    raws = []
    root = args.raw_root.resolve()
    for source, frame in zip(sources, frames, strict=True):
        paths = [(root / source.member(mode)).resolve() for mode in ("rgb", "depth")]
        if any(not p.is_relative_to(root) for p in paths):
            raise ValueError("raw path escapes root")
        pair = adapt_hocap_rgbd(
            source,
            rgb_bytes=paths[0].read_bytes(),
            depth_bytes=paths[1].read_bytes(),
            expected_source_sha256=content_sha256(source),
            household_id=scope,
            session_id=scope,
            trace_id=scope,
            capture_time=frame.capture_time,
            arrival_time=frame.arrival_time,
        )
        if pair[0].envelope().identity.observation_id != frame.observation_id:
            raise ValueError("source prediction ordering mismatch")
        raws.append(pair)

    def fresh(producer, store=None):
        system = StructureTwoProductionSystem(
            owner_key="unresolved-geometry-observer",
            object_instance_id=uuid5(scope, "unresolved-object"),
            locations=(uuid5(scope, "unresolved-loc1"), uuid5(scope, "unresolved-loc2")),
            authorization_scope_id=uuid5(scope, "no-semantic-authorization"),
        )
        stream = ContinuousEvidenceInput(
            system=system,
            execution_lane="legacy_component_diagnostic",
            household_id=scope,
            session_id=scope,
            trace_id=scope,
            producer=producer,
            state_store=store,
        )
        return system, stream

    producer = NaturalGeometryProducer(frames, intrinsics)
    system, stream = fresh(producer)
    before = system.core.current_snapshot
    statuses = {}
    for i, pair in enumerate(raws):
        when = pair[-1].envelope().arrival_time
        stream.admit(pair, received_at=when)
        receipt = stream.advance(cutoff=when)
        statuses[receipt.status] = statuses.get(receipt.status, 0) + 1
        if (i + 1) % 30 == 0:
            print(json.dumps({"geometry_frames": i + 1}), flush=True)
    unchanged = system.core.current_snapshot == before
    if not unchanged or stream.execution_traces():
        raise RuntimeError("unqualified geometry changed semantic core")

    # Durable interruption control uses six real frames, same public stream/store.
    # The full 180-frame lane above is not claimed to be a full recovery benchmark.
    dependency = content_sha256((args.frames_sha256, args.intrinsics_sha256))
    source_identity = content_sha256(source_hashes)
    store_path = args.output / "recovery.sqlite"
    p2 = NaturalGeometryProducer(frames, intrinsics)
    store = ContinuousStateStore(
        store_path, source_identity=source_identity, dependency_identity=dependency
    )
    _, control = fresh(p2, store)
    for pair in raws[:3]:
        when = pair[-1].envelope().arrival_time
        control.admit(pair, received_at=when)
        control.advance(cutoff=when)
    store.close()
    p3 = NaturalGeometryProducer(frames, intrinsics)
    store = ContinuousStateStore(
        store_path, source_identity=source_identity, dependency_identity=dependency
    )
    control = ContinuousEvidenceInput.resume(store, producer=p3)
    for pair in raws[3:6]:
        when = pair[-1].envelope().arrival_time
        control.admit(pair, received_at=when)
        control.advance(cutoff=when)
    first_six = {f.observation_id for f in frames[:6]}
    expected = tuple(r for r in producer.records() if r.rgb_observation_id in first_six)
    recovery_equal = expected == p3.records()
    store.close()
    if not recovery_equal:
        raise RuntimeError("geometry changed across durable resume")
    summary = dict(
        frames=len(frames),
        source_hashes=source_hashes,
        raw_manifest_sha256=args.raw_manifest_sha256,
        frames_sha256=args.frames_sha256,
        intrinsics_sha256=args.intrinsics_sha256,
        execution_lane="legacy_component_diagnostic",
        raw_observations=2 * len(raws),
        surface_candidates=len(producer.records()),
        no_valid_depth=sum(not r.surface_samples for r in producer.records()),
        mixed_depth_spread_over_10cm=sum(
            (r.depth_spread_90_m or 0) > 0.1 for r in producer.records()
        ),
        statuses=statuses,
        core_unchanged=unchanged,
        grounded_transitions=0,
        accepted_conditional_measurements=0,
        memory_updates=0,
        actions=0,
        partial_camera_geometry_only=True,
        orientation_estimated=False,
        scientific_pose_calibration_passed=False,
        recovery=dict(
            frames=6, interrupted_after=3, sqlite_reopen=True, surface_records_equal=recovery_equal
        ),
        blocking=(
            "No object-centre/6D estimator or instance identity; no independent "
            "surface-to-object likelihood/covariance; nominal pinhole coordinates "
            "do not compensate distortion; no role or acquisition model."
        ),
    )
    if source_hashes != {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}:
        raise RuntimeError("geometry source changed during run")
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.output / "surface_candidates.json").write_text(
        json.dumps([asdict(r) for r in producer.records()], indent=2, default=str) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
