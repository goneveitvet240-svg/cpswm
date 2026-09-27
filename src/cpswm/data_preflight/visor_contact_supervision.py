"""Fixed VISOR sparse author contact supervision, separate from runtime authority.

This pilot covers the first published training video, P01_01, in full. It does
not infer event times, identities, 6D poses, or native particle-operation labels.
Public entry points rebuild from enrolled author bytes, never packet claims.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
import shutil
import stat
import tempfile
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image

from cpswm.data_preflight.full_hfd_training import encoded, packet_inventory
from cpswm.data_preflight.hocap_joint_supervision import strict_json

VIDEO = "P01_01"
AUTHOR_CODE_SHA = "8566507382add7dd037a83e7233950e0ad1ea78e"
ENROLLED_SOURCES = (
    ("P01_01.json", "b826142ec8ab896f2645c1fac214af36bf8a3b0bf5696ddbd4fc5c49fca81dee"),
    ("P01_01.zip", "797192c4090a66241992657d7522d1cec2ed0844311a49e77fdfdc3095abbe1c"),
    ("README.txt", "667d7cb63aa531899d692a7a63cee36d9f86d5f5d8755b43d926218c80b60728"),
    ("correct.json", "fecffd6d3eb5fb08d392e72f5ca35fd5476e89de2a0f088de24ab46fc34dba95"),
    (
        "author_converter.py.txt",
        "686a052c8676c8378438efcf90e97e71cd6abca576381b0ca560e6cb07759cd7",
    ),
)
HANDS = ("left hand", "right hand")
SPECIAL = ("hand-not-in-contact", "none-of-the-above", "inconclusive")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _author_frames(
    raw: bytes, corrections_raw: bytes, *, video: str = VIDEO
) -> list[dict[str, Any]]:
    if video not in {VIDEO, "P01_03"}:
        raise ValueError("video is not enrolled for component development")
    doc = strict_json(raw)
    if set(doc) != {"info", "video_annotations"} or doc["info"].get("Dataset Name") != "VISOR":
        raise ValueError("expected VISOR sparse annotation document")
    frames = doc["video_annotations"]
    if not isinstance(frames, list) or not 1 <= len(frames) <= 1000:
        raise ValueError("bounded nonempty fixed-video annotation required")
    corrections = strict_json(corrections_raw)
    names: set[str] = set()
    for frame in frames:
        if set(frame) != {"image", "annotations"}:
            raise ValueError("unexpected annotation frame fields")
        image = frame["image"]
        name = image["name"]
        match = re.fullmatch(video + r"_frame_(\d{10})\.jpg", name)
        if (
            set(image) != {"image_path", "name", "subsequence", "video"}
            or not match
            or name in names
            or image["video"] != video
            or image["image_path"] != video + "/" + name
            or not re.fullmatch(video + r"_seq_\d{5}", image["subsequence"])
        ):
            raise ValueError("wrong video, duplicate or unsafe frame identity")
        names.add(name)
        entities = frame["annotations"]
        if not isinstance(entities, list) or not 1 <= len(entities) <= 100:
            raise ValueError("bounded nonempty entity set required")
        ids: set[str] = set()
        sides: set[str] = set()
        for entity in entities:
            required = {"id", "name", "class_id", "exhaustive", "segments"}
            if entity["name"] in HANDS:
                required.add("in_contact_object")
                if entity["name"] in sides:
                    raise ValueError("ambiguous duplicated hand side")
                sides.add(entity["name"])
            if (
                set(entity) != required
                or not isinstance(entity["id"], str)
                or not entity["id"]
                or entity["id"] in ids
                or not isinstance(entity["name"], str)
                or not entity["name"]
                or type(entity["class_id"]) is not int
                or entity["class_id"] < 0
                or entity["exhaustive"] not in {"y", "n", "inconclusive"}
            ):
                raise ValueError("invalid entity schema; glove extension needs separate review")
            ids.add(entity["id"])
            polygons = entity["segments"]
            if not isinstance(polygons, list) or not 1 <= len(polygons) <= 100:
                raise ValueError("invalid polygon collection")
            for polygon in polygons:
                if not isinstance(polygon, list) or not 3 <= len(polygon) <= 10000:
                    raise ValueError("invalid polygon length")
                for point in polygon:
                    if (
                        not isinstance(point, list)
                        or len(point) != 2
                        or any(type(v) not in (float, int) or not math.isfinite(v) for v in point)
                    ):
                        raise ValueError("invalid polygon coordinate")
        # Do not silently run the author's mutable correction code. This fixed
        # pilot has no affected frame; future expansion must explicitly review it.
        if name in corrections:
            raise ValueError("known author correction requires a separately reviewed import")
        for entity in entities:
            if entity["name"] in HANDS:
                target = entity["in_contact_object"]
                if (
                    not isinstance(target, str)
                    or target == entity["id"]
                    or (target not in SPECIAL and target not in ids)
                ):
                    raise ValueError("dangling or self contact target")
    return sorted(frames, key=lambda frame: frame["image"]["name"])


def _derive(source: dict[str, bytes], *, video: str = VIDEO) -> dict[str, bytes]:
    frames = _author_frames(source[video + ".json"], source["correct.json"], video=video)
    expected = {f["image"]["name"] for f in frames}
    artifacts: dict[str, bytes] = {}
    inputs, evaluation, targets = [], [], []
    states: Counter[str] = Counter()
    geometry_outside_image = 0
    with zipfile.ZipFile(io.BytesIO(source[video + ".zip"])) as archive:
        members = archive.infolist()
        names = [m.filename for m in members]
        if len(names) != len(set(names)):
            raise ValueError("duplicate ZIP member")
        files = set()
        total = 0
        for member in members:
            path = PurePosixPath(member.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in member.filename
                or path.as_posix() != member.filename.rstrip("/")
                or stat.S_IFMT(member.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR)
                or member.flag_bits & 1
            ):
                raise ValueError("unsafe or nonregular ZIP member")
            if member.is_dir():
                if member.filename != video + "/":
                    raise ValueError("unexpected ZIP directory")
                continue
            if member.filename not in expected or not 0 < member.file_size <= 4 * 1024**2:
                raise ValueError("unexpected or oversized RGB member")
            files.add(member.filename)
            total += member.file_size
        if files != expected or total > 256 * 1024**2:
            raise ValueError("RGB/annotation coverage mismatch or oversized archive")
        for ordinal, frame in enumerate(frames):
            raw = archive.read(frame["image"]["name"])  # ZIP CRC is checked.
            with Image.open(io.BytesIO(raw)) as image:
                if image.format != "JPEG" or image.mode != "RGB" or image.size != (1920, 1080):
                    raise ValueError("unexpected fixed source RGB encoding or dimensions")
                image.load()
                pixels = image.tobytes()
            digest = _sha(raw)
            key = _sha(encoded({"ordinal": ordinal, "rgb_sha256": digest}))
            relative = "runtime/frames/" + key + ".jpg"
            artifacts[relative] = raw
            # No author names, classes, masks, contacts, side, subject ID, source
            # path or subsequence enters this RGB-only lane.
            inputs.append(
                {
                    "key": key,
                    "ordinal": ordinal,
                    "rgb": relative,
                    "rgb_sha256": digest,
                    "pixel_sha256": _sha(pixels),
                    "width": 1920,
                    "height": 1080,
                }
            )
            evaluation.append({"key": key, **frame})
            by_id = {e["id"]: e for e in frame["annotations"]}
            for entity in frame["annotations"]:
                geometry_outside_image += any(
                    x < 0 or y < 0 or x > 1920 or y > 1080
                    for polygon in entity["segments"]
                    for x, y in polygon
                )
                if entity["name"] not in HANDS:
                    continue
                contact = entity["in_contact_object"]
                if contact == "hand-not-in-contact":
                    state, binary, target = "author_no_contact", False, None
                elif contact in SPECIAL:
                    state, binary, target = "author_" + contact, None, None
                else:
                    state, binary, target = "author_contact_with_segment", True, contact
                states[state] += 1
                targets.append(
                    {
                        "key": key,
                        "hand_mask_id": entity["id"],
                        "hand_side": entity["name"],
                        "author_raw_contact": contact,
                        "state": state,
                        "binary_contact_target": binary,
                        "contact_segment_id": target,
                        "contact_segment_name": by_id[target]["name"] if target else None,
                        "contact_segment_exhaustive": by_id[target]["exhaustive"]
                        if target
                        else None,
                    }
                )
    report = {
        "dataset": "VISOR",
        "video": video,
        "partition": "author_train_development",
        "source_kind": "author_sparse_human_annotation",
        "frames": len(frames),
        "entities": sum(len(f["annotations"]) for f in frames),
        "hand_relations": len(targets),
        "contact_states": dict(sorted(states.items())),
        "binary_labeled_relations": sum(t["binary_contact_target"] is not None for t in targets),
        "excluded_from_binary_loss_but_retained": sum(
            t["binary_contact_target"] is None for t in targets
        ),
        "frames_without_annotated_hand": sum(
            not any(e["name"] in HANDS for e in f["annotations"]) for f in frames
        ),
        "raw_masks_with_outside_image_coordinates": geometry_outside_image,
        "coordinates_repaired": False,
        "known_author_corrections_affecting_pilot": 0,
        "author_code_revision": AUTHOR_CODE_SHA,
        "dense_interpolation_used": False,
        "frame_order_policy": "sort by VISOR frame ordinal; source records need not be ordered",
        "rgb_only_lane_contains_targets": False,
        "cross_frame_instance_identity_assumed": False,
        "exact_contact_release_gold": False,
        "person_identity_gold": False,
        "runtime_pose_noise_calibrated": False,
        "native_operation_labels": [],
        "full_proposal_training_ready": False,
        "native_publication_authorized": False,
        "ledger_authorized": False,
        "action_authorized": False,
        "new_optimizer_steps": 0,
        "independent_local_human_reviewers": 0,
        "target_scope": "single_frame_author_contact_component_only",
        "unknown_policy": "none-of-the-above and inconclusive stay distinct; no binary target",
        "time_policy": (
            "sparse source frame ordinals only; no fps, timestamps or release interpolation"
        ),
        "license_readme": "CC-BY-NC-4.0; cite VISOR 2022 and EPIC-KITCHENS-100",
    }
    artifacts["runtime/manifest.json"] = encoded({"format": "visor_rgb_only_v1", "frames": inputs})
    artifacts["supervision/frames.json"] = encoded(evaluation)
    artifacts["supervision/contact_targets.json"] = encoded(targets)
    artifacts["manifest.json"] = encoded(
        {
            "report": report,
            "sources": {k: _sha(v) for k, v in sorted(source.items())},
            "members": {
                k: {"sha256": _sha(v), "bytes": len(v)} for k, v in sorted(artifacts.items())
            },
        }
    )
    return artifacts


def _source_bytes(root: Path) -> dict[str, bytes]:
    before = packet_inventory(root)
    if not before:
        raise ValueError("source directory is missing or empty")
    result = {}
    for name, digest in ENROLLED_SOURCES:
        raw = (root / name).read_bytes()
        if _sha(raw) != digest:
            raise ValueError("source differs from enrolled author bytes: " + name)
        result[name] = raw
    if packet_inventory(root) != before:
        raise ValueError("source changed while reading")
    return result


def _verify_artifacts(output: Path, artifacts: dict[str, bytes]) -> None:
    before = packet_inventory(output)
    if set(before) != set(artifacts):
        raise ValueError("packet has missing or extra files")
    for name, raw in artifacts.items():
        if (output / name).read_bytes() != raw:
            raise ValueError("packet differs from source recomputation: " + name)
    if packet_inventory(output) != before:
        raise ValueError("packet changed during verification")


def load_contact_component(root: Path, packet: Path) -> dict[str, Any]:
    """Return rederived component targets after checking the entire delivered pack.

    Deliberately not a ProposalSample or an authorized semantic observation.
    Nothing returned supplies a release time, particle operation, identity or pose.
    """
    artifacts = _derive(_source_bytes(root))
    _verify_artifacts(packet, artifacts)
    return {
        "inputs": strict_json(artifacts["runtime/manifest.json"])["frames"],
        "targets": strict_json(artifacts["supervision/contact_targets.json"]),
        "report": strict_json(artifacts["manifest.json"])["report"],
    }


def prepare_contact_package(root: Path, output: Path, *, verify: bool = False) -> dict[str, Any]:
    """Rebuild all bytes from frozen sources; create atomically or verify exactly."""
    if root.resolve().is_relative_to(output.resolve()) or output.resolve().is_relative_to(
        root.resolve()
    ):
        raise ValueError("source and destination must be disjoint")
    if output.is_symlink():
        raise ValueError("output cannot be a symbolic link")
    if not verify and output.exists():
        raise FileExistsError(output)
    artifacts = _derive(_source_bytes(root))
    if verify:
        _verify_artifacts(output, artifacts)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".visor-staging-", dir=output.parent))
        try:
            for name, raw in artifacts.items():
                path = staging / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            if output.exists():
                raise FileExistsError(output)
            staging.rename(output)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    result: dict[str, Any] = strict_json(artifacts["manifest.json"])
    return result
