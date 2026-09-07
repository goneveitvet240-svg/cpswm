#!/usr/bin/env python3
"""Verify the pinned ProcTHOR dataset and AI2-THOR runtime for Structure-Two D1.

Run this file with ``.venv-ai2thor/bin/python``.  The receipt establishes only
that pinned houses execute and expose simulator metadata; it is not a D1 replay
collection and cannot be promoted into external-validity evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
from typing import Any, Final

PROCTHOR_REVISION: Final = "439193522244720b86d8c81cde2e51e3a4d150cf"
AI2THOR_COMMIT_ID: Final = "f0825767cd50d69f666c7f282e54abfe58f1e917"
ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT: Final = (
    ROOT / "benchmarks/structure_two/structure_two_procthor_runtime_preflight_v0_1.json"
)


def _sha256(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _split(dataset: object, name: str) -> Any:
    value = getattr(dataset, name, None)
    if value is None:
        raise ValueError(f"ProcTHOR dataset lacks split: {name}")
    return value


def build_receipt() -> dict[str, object]:
    import ai2thor
    import prior
    import procthor
    from ai2thor.controller import Controller

    dataset = prior.load_dataset("procthor-10k", revision=PROCTHOR_REVISION, offline=True)
    split_counts = {name: len(_split(dataset, name)) for name in ("train", "val", "test")}
    if split_counts != {"train": 10_000, "val": 1_000, "test": 1_000}:
        raise ValueError("pinned ProcTHOR split counts drifted")
    scene_receipts: list[dict[str, object]] = []
    for split_name, index in (("val", 0), ("test", 0)):
        house = _split(dataset, split_name)[index]
        controller = Controller(scene=house, width=300, height=300, quality="Low")
        try:
            event = controller.step(action="GetReachablePositions")
            metadata = event.metadata
            if metadata.get("lastActionSuccess") is not True:
                raise RuntimeError(
                    f"ProcTHOR {split_name}[{index}] failed: {metadata.get('errorMessage')}"
                )
            reachable = metadata.get("actionReturn")
            objects = metadata.get("objects")
            if not isinstance(reachable, list) or not reachable:
                raise ValueError("ProcTHOR scene returned no reachable positions")
            if not isinstance(objects, list) or not objects:
                raise ValueError("ProcTHOR scene returned no object metadata")
            scene_receipts.append(
                {
                    "split": split_name,
                    "index": index,
                    "house_content_sha256": _sha256(house),
                    "reachable_position_count": len(reachable),
                    "object_metadata_count": len(objects),
                    "action_success": True,
                }
            )
        finally:
            controller.stop()
    payload: dict[str, object] = {
        "protocol": "structure-two-procthor-runtime-preflight@0.1",
        "host_platform": platform.platform(),
        "ai2thor_version": getattr(ai2thor, "__version__", "5.0.0"),
        "procthor_version": getattr(procthor, "__version__", "0.0.1.dev2"),
        "prior_version": getattr(prior, "__version__", "1.0.3"),
        "procthor_dataset_revision": PROCTHOR_REVISION,
        "ai2thor_build_commit_id": AI2THOR_COMMIT_ID,
        "split_counts": split_counts,
        "scene_receipts": scene_receipts,
        "runtime_preflight_passed": True,
        "d1_replay_collection_completed": False,
        "external_validity_established": False,
        "claim_boundary": (
            "This receipt establishes pinned dataset loading and simulator action/metadata "
            "availability only. It is not a collected D1 replay, a method result, or an "
            "external-validity authorization."
        ),
    }
    payload["content_sha256"] = _sha256(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    receipt = build_receipt()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"output={arguments.output}")
    print(f"runtime_preflight_passed={receipt['runtime_preflight_passed']}")
    print(f"d1_replay_collection_completed={receipt['d1_replay_collection_completed']}")


if __name__ == "__main__":
    main()
