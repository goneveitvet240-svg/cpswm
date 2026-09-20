"""Six real RGB-D frames: compare uninterrupted with SQLite close/resume.

This verifies pixel-candidate persistence only, not semantic/P5/action recovery.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from cpswm.data_preflight.natural_event_coverage import pinned_bytes
from cpswm.perception_mapping.adapters.hocap_rgbd import HOCapFrameSource, adapt_hocap_rgbd
from cpswm.perception_mapping.natural_hands import NaturalHandDetector
from cpswm.perception_mapping.natural_vision import (
    FasterNaturalAppearanceDetector,
    NaturalVisionEvidenceProducer,
)
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.structure_two_production_system import StructureTwoProductionSystem


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("raw-root", "raw-manifest", "weights", "hand-model", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--raw-manifest-sha256", required=True)
    args = parser.parse_args()
    source_paths = [
        Path(__file__),
        Path("src/cpswm/perception_mapping/natural_hands.py"),
        Path("src/cpswm/perception_mapping/natural_vision.py"),
    ]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    sources = [
        HOCapFrameSource(**row)
        for row in json.loads(
            pinned_bytes(args.raw_manifest.read_bytes(), args.raw_manifest_sha256)
        )[:6]
    ]
    if len(sources) != 6 or len({(s.sequence_id, s.camera_id) for s in sources}) != 1:
        raise ValueError("six same-camera frames required")
    if any(b.frame_index != a.frame_index + 1 for a, b in pairwise(sources)):
        raise ValueError("contiguous frames required")
    args.output.mkdir(parents=True, exist_ok=False)
    import torch

    torch.set_num_threads(2)
    scope = uuid5(NAMESPACE_URL, "hand-recovery:" + args.raw_manifest_sha256)
    pairs = []
    for s in sources:
        when = datetime(2000, 1, 1, tzinfo=UTC) + timedelta(milliseconds=s.frame_index * 100)
        paths = [(args.raw_root / s.member(mode)).resolve() for mode in ("rgb", "depth")]
        if any(not p.is_relative_to(args.raw_root.resolve()) for p in paths):
            raise ValueError("raw path escapes root")
        pairs.append(
            adapt_hocap_rgbd(
                s,
                rgb_bytes=paths[0].read_bytes(),
                depth_bytes=paths[1].read_bytes(),
                expected_source_sha256=content_sha256(s),
                household_id=scope,
                session_id=scope,
                trace_id=scope,
                capture_time=when,
                arrival_time=when,
            )
        )

    def producer():
        detector = FasterNaturalAppearanceDetector(
            weights_path=args.weights, household_id=scope, session_id=scope, trace_id=scope
        )
        hand = NaturalHandDetector(model_path=args.hand_model, scope=(scope, scope, scope))
        return NaturalVisionEvidenceProducer(detector, hand), hand

    def fresh(p, store=None):
        system = StructureTwoProductionSystem(
            owner_key="unresolved-hand-observer",
            object_instance_id=uuid5(scope, "unknown-object"),
            locations=(uuid5(scope, "unknown-loc1"), uuid5(scope, "unknown-loc2")),
            authorization_scope_id=uuid5(scope, "no-memory-authority"),
        )
        return ContinuousEvidenceInput(
            system=system,
            execution_lane="legacy_component_diagnostic",
            household_id=scope,
            session_id=scope,
            trace_id=scope,
            producer=p,
            state_store=store,
        )

    def consume(stream, selected):
        for pair in selected:
            when = pair[0].envelope().arrival_time
            stream.admit(pair, received_at=when)
            receipt = stream.advance(cutoff=when)
            if receipt.status != "INSUFFICIENT_SEMANTIC_EVIDENCE" or stream.execution_traces():
                raise RuntimeError("uncalibrated hands advanced semantic core")

    first, first_hand = producer()
    stream = fresh(first)
    consume(stream, pairs)
    first_hand.close()
    ids = dict(
        source_identity=content_sha256(hashes),
        dependency_identity=content_sha256(
            (args.raw_manifest_sha256, first.checkpoint_state()["hand_binding"])
        ),
    )
    store = ContinuousStateStore(args.output / "resume.sqlite", **ids)
    part, part_hand = producer()
    partial = fresh(part, store)
    consume(partial, pairs[:3])
    store.close()
    part_hand.close()
    store = ContinuousStateStore(args.output / "resume.sqlite", **ids)
    resumed, resumed_hand = producer()
    continuation = ContinuousEvidenceInput.resume(store, producer=resumed)
    consume(continuation, pairs[3:])
    equal = first.hand_frames() == resumed.hand_frames() and first.frames() == resumed.frames()
    store.close()
    resumed_hand.close()
    unchanged = hashes == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    result = dict(
        raw_frames=6,
        interrupted_after=3,
        sqlite_closed_reopened=True,
        actual_models_reconstructed=True,
        pixel_candidates_equal=equal,
        hand_candidates=sum(len(f.candidates) for f in first.hand_frames()),
        semantic_transitions=0,
        physical_actions=0,
        source_unchanged=unchanged,
        source_hashes=hashes,
        raw_manifest_sha256=args.raw_manifest_sha256,
        scope="real pixel candidates, not semantic correction or P5 acceptance",
    )
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if not equal or not unchanged:
        raise RuntimeError("real candidate recovery diverged")


if __name__ == "__main__":
    main()
