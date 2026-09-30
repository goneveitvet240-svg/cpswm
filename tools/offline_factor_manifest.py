"""Pinned, reproducible offline factor-data plan; no simulator or model imports.

The static asset audit is a necessary partition check, not authorization to export
supervision. Runtime-generated assets must undergo the same audit after capture.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
from typing import Any

ARCHIVE_SHA256 = "ee3c4aa14b4d8f0895fecfb5fdaca59395427ca1018b2f9aeeedbc61e5824587"
DATASET_REVISION = "439193522244720b86d8c81cde2e51e3a4d150cf"
IMAGE_SIZE = 320
NEAR = 0.1
FAR = 20.0
OBSERVATION_ACTIONS = (("Pass", 0.0),) + (("RotateRight", 45.0),) * 7
_SPLITS = {0: "diagnostic_only", **dict.fromkeys(range(1, 9), "train")}
_SPLITS.update(dict.fromkeys(range(9, 13), "validation"))


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _invalid_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _load_house(raw: bytes) -> dict[str, Any]:
    house = json.loads(
        raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys, parse_constant=_invalid_constant
    )
    if not isinstance(house, dict) or not isinstance(house.get("objects"), list):
        raise ValueError("house must contain an objects list")
    metadata = house.get("metadata")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("agent"), dict):
        raise ValueError("house must retain its original metadata.agent")
    agent = metadata["agent"]
    if metadata.get("agentPoses", {}).get("default") != agent:
        raise ValueError("original agent alias differs from actual default agentPoses")
    if agent.get("horizon") != 30 or isinstance(agent.get("horizon"), bool):
        raise ValueError("fixed plan requires original horizon 30; do not rewrite house")
    for name in ("position", "rotation"):
        xyz = agent.get(name)
        if not isinstance(xyz, dict) or set(xyz) != {"x", "y", "z"}:
            raise ValueError(f"original agent {name} must contain xyz")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in xyz.values()):
            raise ValueError(f"original agent {name} must be numeric")
    # Also rejects overflowed numeric literals, such as 1e400.
    _json_bytes(house)
    return house


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonempty unpadded string")
    return value


def _pointer(parent: str, key: str | int) -> str:
    return f"{parent}/{str(key).replace('~', '~0').replace('/', '~1')}"


def _asset_occurrences(value: Any, pointer: str = "") -> list[dict[str, str]]:
    """Includes doors, windows and every nested object, not only target objects."""
    rows = []
    if isinstance(value, dict):
        if "assetId" in value:
            rows.append(
                {
                    "asset_id": _nonempty(value["assetId"], "assetId"),
                    "json_pointer": _pointer(pointer, "assetId"),
                }
            )
        for key, child in value.items():
            rows.extend(_asset_occurrences(child, _pointer(pointer, key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            rows.extend(_asset_occurrences(child, _pointer(pointer, index)))
    return sorted(rows, key=lambda row: row["json_pointer"])


def _instances(house: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(objects: Any, pointer: str) -> None:
        if not isinstance(objects, list):
            raise ValueError(f"objects/children must be a list: {pointer}")
        for index, obj in enumerate(objects):
            where = _pointer(pointer, index)
            if not isinstance(obj, dict):
                raise ValueError(f"object must be a dictionary: {where}")
            object_id = _nonempty(obj.get("id"), "object id")
            if object_id in seen:
                raise ValueError(f"duplicate object id within house: {object_id}")
            seen.add(object_id)
            rows.append(
                {
                    "object_id": object_id,
                    "asset_id": _nonempty(obj.get("assetId"), "object assetId"),
                    "json_pointer": where,
                }
            )
            if "children" in obj:
                visit(obj["children"], _pointer(where, "children"))

    visit(house["objects"], "/objects")
    return rows


def _unlabelled_physical_content(house: dict[str, Any]) -> Any:
    """Conservative duplicate diagnostic ignoring labels, not an independence test.

    The original house bytes remain unchanged. Metadata/camera starting pose is
    not physical scene content. IDs and their architecture references may be
    renamed without making a new scene; discard those fields for this check.
    """
    label_keys = {"id", "name", "roomId", "wall0", "wall1", "room0", "room1"}

    def scrub(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: scrub(child) for key, child in value.items() if key not in label_keys}
        if isinstance(value, list):
            # Reordering object/architecture lists also does not create a new scene.
            return sorted((scrub(child) for child in value), key=_json_bytes)
        return value

    return scrub({key: value for key, value in house.items() if key != "metadata"})


def acquisition_schedule() -> dict[str, Any]:
    """Fresh JSON value; callers cannot mutate the module's observation schedule."""
    return {
        "image_width": IMAGE_SIZE,
        "image_height": IMAGE_SIZE,
        "depth_near_m": NEAR,
        "depth_far_m": FAR,
        "sensor_inputs": ["RGB", "depth", "camera_self_pose"],
        "start": "original metadata.agentPoses.default; preserve x/z, yaw and horizon 30",
        "agent_mode": "default",
        "initial_vertical_pose": "record SDK gravity settlement; use measured self-pose y",
        "pre_capture_actions": ["PausePhysicsAutoSim", "Pass", "Pass"],
        "observation_actions": [
            {"action": action, "degrees": degrees} for action, degrees in OBSERVATION_ACTIONS
        ],
        "target_conditioned_placement": False,
        "target_conditioned_view_selection": False,
        "object_ids_masks_positions": "offline_supervision_and_calibration_only",
        "failure_policy": "retain failed or uncovered houses; no replacement",
    }


def _build_from_bytes(
    raw_gzip: bytes, *, expected_sha256: str, revision: str
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Pure test seam. Production entry points always supply the fixed official pins."""
    if _sha(raw_gzip) != expected_sha256:
        raise ValueError("complete archive SHA256 differs from the pinned source")
    houses: list[dict[str, Any]] = []
    files: dict[str, bytes] = {}
    with gzip.GzipFile(fileobj=io.BytesIO(raw_gzip), mode="rb") as stream:
        for index in range(13):
            raw = stream.readline()
            if not raw:
                raise ValueError("archive does not contain all fixed indices 0 through 12")
            house = _load_house(raw)
            relative = f"houses/house-{index:02d}.json"
            files[relative] = raw  # Preserve the JSONL line, including its original newline.
            occurrences = _asset_occurrences(house)
            houses.append(
                {
                    "index": index,
                    "split": _SPLITS[index],
                    "relative_path": relative,
                    "house_sha256": _sha(raw),
                    "house_bytes": len(raw),
                    "canonical_json_sha256": _sha(_json_bytes(house)),
                    "unlabelled_physical_sha256": _sha(
                        _json_bytes(_unlabelled_physical_content(house))
                    ),
                    "original_agent": house["metadata"]["agent"],
                    "asset_occurrences": occurrences,
                    "asset_ids": sorted({row["asset_id"] for row in occurrences}),
                    "instances": _instances(house),
                }
            )

    def assets(split: str) -> set[str]:
        return {asset for row in houses if row["split"] == split for asset in row["asset_ids"]}

    cross_assets = assets("train") & assets("validation")
    old_assets = assets("diagnostic_only")
    for house in houses:
        duplicates = [
            row["index"]
            for row in houses
            if row["index"] != house["index"]
            and row["unlabelled_physical_sha256"] == house["unlabelled_physical_sha256"]
        ]
        house["duplicate_house_indices"] = duplicates
        for instance in house["instances"]:
            reasons = []
            if house["split"] == "diagnostic_only":
                reasons.append("index0_diagnostic_only")
            if duplicates:
                reasons.append("duplicate_house_physical_content")
            if instance["asset_id"] in cross_assets:
                reasons.append("asset_shared_by_train_and_validation")
            if house["split"] == "validation" and instance["asset_id"] in old_assets:
                reasons.append("validation_asset_seen_in_old_index0")
            instance["eligible"] = not reasons
            instance["exclusion_reasons"] = reasons
            instance["use"] = (
                "potential_target_pending_runtime_audit"
                if not reasons
                else ("context_only_quarantined_from_supervision")
            )
        house["eligible_instance_count"] = sum(row["eligible"] for row in house["instances"])

    split_plan = {str(index): split for index, split in _SPLITS.items()}
    schedule = acquisition_schedule()
    manifest = {
        "schema": "cpswm.offline-factor-plan.v1",
        "source": {
            "dataset": "allenai/procthor-10k",
            "split": "TRAIN",
            "revision": revision,
            "archive_sha256": expected_sha256,
            "archive_bytes": len(raw_gzip),
            "selected_jsonl_indices": list(range(13)),
        },
        "fixed_split": split_plan,
        "fixed_split_sha256": _sha(_json_bytes(split_plan)),
        "acquisition_schedule": schedule,
        "acquisition_schedule_sha256": _sha(_json_bytes(schedule)),
        "eligibility_scope": "static_house_asset_partition_only",
        "runtime_asset_audit_required": True,
        "supervision_export_authorized": False,
        "runtime_audit_rule": (
            "audit all assets actually appearing in initial and subsequent SDK catalogs; "
            "exclude both sides of train/validation shared assets and validation assets "
            "seen in diagnostic index0; missing or unmapped assets remain ineligible"
        ),
        "shared_train_validation_assets": sorted(cross_assets),
        "validation_assets_seen_in_index0": sorted(assets("validation") & old_assets),
        "duplicate_check_scope": "conservative physical JSON without metadata or identifier fields",
        "houses": houses,
    }
    manifest["manifest_sha256"] = _sha(_json_bytes(manifest))
    return manifest, files


def build_manifest(archive: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Build only from the complete, fixed official TRAIN archive."""
    return _build_from_bytes(
        Path(archive).read_bytes(), expected_sha256=ARCHIVE_SHA256, revision=DATASET_REVISION
    )


def write_plan(archive: Path, output: Path) -> dict[str, Any]:
    """Write into a new or empty real directory; never overwrite previous artifacts."""
    output = Path(output)
    if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise ValueError("output must be a new or empty directory; refusing overwrite")
    manifest, files = build_manifest(archive)
    output.mkdir(parents=True, exist_ok=True)
    (output / "houses").mkdir()  # No exist_ok: concurrent or stale writes fail closed.
    for relative, raw in files.items():
        with (output / relative).open("xb") as destination:
            destination.write(raw)
    with (output / "manifest.json").open("xb") as destination:
        destination.write(_json_bytes(manifest))
    return manifest


def verify_plan(archive: Path, output: Path) -> dict[str, Any]:
    """Reconstruct from source; a forged but internally rehashed manifest cannot pass."""
    output = Path(output)
    manifest, files = build_manifest(archive)
    expected = {**files, "manifest.json": _json_bytes(manifest)}
    if output.is_symlink() or not output.is_dir():
        raise ValueError("plan must be a real directory")
    actual = set()
    for path in output.rglob("*"):
        if path.is_symlink():
            raise ValueError("symlinks are not permitted in a plan")
        if path.is_file():
            actual.add(path.relative_to(output).as_posix())
        elif not path.is_dir():
            raise ValueError("non-regular entry in plan")
    if actual != set(expected):
        raise ValueError("plan file inventory differs from the reconstructed source")
    for relative, raw in expected.items():
        if (output / relative).read_bytes() != raw:
            raise ValueError(f"plan differs from reconstructed source: {relative}")
    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "verify"))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = (write_plan if args.mode == "build" else verify_plan)(args.archive, args.output)
    print(
        json.dumps(
            {
                "mode": args.mode,
                "manifest_sha256": manifest["manifest_sha256"],
                "houses": len(manifest["houses"]),
            }
        )
    )


if __name__ == "__main__":
    main()
