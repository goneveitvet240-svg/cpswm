"""Source-derived pixel supervision, separate from RGB-only model inputs.

Unlabelled pixels are void. Masks are training targets, never inference crops.
Presence and conditional contact are separate axes: unknown contact still gives
hand-presence supervision. These targets confer no entity or runtime authority.
"""

from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from cpswm.data_preflight.full_hfd_training import encoded
from cpswm.data_preflight.hocap_joint_supervision import strict_json
from cpswm.data_preflight.visor_candidate_alignment import mask_pixels, sha
from cpswm.data_preflight.visor_contact_supervision import (
    HANDS,
    _derive,
    _source_bytes,
    _verify_artifacts,
)

VOID = 255
AXES = ("hand", "contact")
POLICY = "author_masks_only;unlabelled_and_conflicting_void;unknown_contact_keeps_hand@1"


def pixel_targets(
    frame: dict[str, Any], width: int, height: int
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    groups = {
        name: np.zeros((height, width), dtype=bool)
        for name in ("other", "hand", "yes", "no", "unknown")
    }
    for entity in frame["annotations"]:
        mask = mask_pixels(entity["segments"], width, height)
        if entity["name"] not in HANDS:
            groups["other"] |= mask
            continue
        groups["hand"] |= mask
        state = entity["in_contact_object"]
        group = (
            "no"
            if state == "hand-not-in-contact"
            else "unknown"
            if state in {"none-of-the-above", "inconclusive"}
            else "yes"
        )
        groups[group] |= mask
    conflict = groups["hand"] & groups["other"]
    hand = np.full((height, width), VOID, dtype=np.uint8)
    hand[groups["other"] & ~groups["hand"]] = 0
    hand[groups["hand"] & ~groups["other"]] = 1
    contact = np.full((height, width), VOID, dtype=np.uint8)
    allowed = ~conflict & ~groups["unknown"]
    contact[groups["yes"] & ~groups["no"] & allowed] = 1
    contact[groups["no"] & ~groups["yes"] & allowed] = 0
    targets = {"hand": hand, "contact": contact}
    counts = {
        axis: {str(v): int(np.count_nonzero(a == v)) for v in (0, 1, VOID)}
        for axis, a in targets.items()
    }
    return targets, {
        "pixels": counts,
        "hand_other_conflict_pixels": int(conflict.sum()),
        "unknown_contact_pixels": int(groups["unknown"].sum()),
        "opposed_contact_pixels": int((groups["yes"] & groups["no"]).sum()),
    }


def _png(a: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(a).save(buf, format="PNG")
    return buf.getvalue()


def compile_targets(contact_artifacts: dict[str, bytes]) -> dict[str, bytes]:
    inputs = strict_json(contact_artifacts["runtime/manifest.json"])["frames"]
    authors = strict_json(contact_artifacts["supervision/frames.json"])
    artifacts, rows = {}, []
    totals = {axis: {str(v): 0 for v in (0, 1, VOID)} for axis in AXES}
    for row, author in zip(inputs, authors, strict=True):
        if author["key"] != row["key"]:
            raise ValueError("author and RGB frame differ")
        arrays, counts = pixel_targets(author, row["width"], row["height"])
        files = {}
        for axis in AXES:
            name = f"targets/{row['key']}/{axis}.png"
            artifacts[name] = _png(arrays[axis])
            files[axis] = name
            for v, count in counts["pixels"][axis].items():
                totals[axis][v] += count
        rows.append({"input": row, "targets": files, **counts})
    artifacts["manifest.json"] = encoded(
        {
            "format": "visor_pixel_supervision_v1",
            "policy": POLICY,
            "rgb_manifest_sha256": sha(contact_artifacts["runtime/manifest.json"]),
            "source_manifest_sha256": sha(contact_artifacts["manifest.json"]),
            "rows": rows,
            "summary": {
                "frames": len(rows),
                "pixels": totals,
                "hand_supervised_frames": sum(
                    r["pixels"]["hand"]["0"] + r["pixels"]["hand"]["1"] > 0 for r in rows
                ),
                "contact_supervised_frames": sum(
                    r["pixels"]["contact"]["0"] + r["pixels"]["contact"]["1"] > 0 for r in rows
                ),
                "hand_other_conflict_pixels": sum(r["hand_other_conflict_pixels"] for r in rows),
                "unknown_contact_pixels": sum(r["unknown_contact_pixels"] for r in rows),
            },
            "members": {
                name: {"bytes": len(raw), "sha256": sha(raw)} for name, raw in artifacts.items()
            },
            "full_proposal_targets": False,
            "candidate_correspondences": 0,
            "runtime_semantic_authority": False,
        }
    )
    return artifacts


def rebuild(source: Path, contact_packet: Path) -> tuple[dict[str, bytes], dict[str, bytes]]:
    original = _derive(_source_bytes(source))
    _verify_artifacts(contact_packet, original)
    return original, compile_targets(original)


def prepare(
    source: Path, contact_packet: Path, output: Path, *, verify: bool = False
) -> dict[str, Any]:
    for parent in (source, contact_packet):
        if output.resolve().is_relative_to(parent.resolve()) or parent.resolve().is_relative_to(
            output.resolve()
        ):
            raise ValueError("output must be disjoint from source packets")
    if output.is_symlink() or (output.exists() and not verify):
        raise FileExistsError(output)
    _, artifacts = rebuild(source, contact_packet)
    if verify:
        _verify_artifacts(output, artifacts)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".visor-pixel-", dir=output.parent))
        try:
            for name, raw in artifacts.items():
                p = staging / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
            if output.exists():
                raise FileExistsError(output)
            staging.rename(output)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    result: dict[str, Any] = strict_json(artifacts["manifest.json"])
    return result


def load_component(
    source: Path, contact_packet: Path, pixel_packet: Path, *, count: int = 16
) -> dict[str, Any]:
    original, targets = rebuild(source, contact_packet)
    _verify_artifacts(pixel_packet, targets)
    manifest = strict_json(targets["manifest.json"])
    if type(count) is not int or not 1 <= count <= len(manifest["rows"]):
        raise ValueError("requested prefix must exist in full packet")
    rows = manifest["rows"][:count]
    # Return the bytes rederived above, never reread mutable files after checking.
    return {
        "inputs": [(r["input"], original[r["input"]["rgb"]]) for r in rows],
        "targets": [{axis: targets[r["targets"][axis]] for axis in AXES} for r in rows],
        "manifest_sha256": sha(targets["manifest.json"]),
        "summary": manifest["summary"],
    }
