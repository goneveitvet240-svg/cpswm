"""Offline SDK asset exposure provenance, never target labels or online features.

Rules follow ai2thor f0825767cd50d69f666c7f282e54abfe58f1e917,
ProceduralTools.cs SHA256
877589b9ed6b7dba31aa860d1dc8469e7ff0f415d1a3cdf29582d936212dc877:
wall IDs/types 775,887-888; room-floor IDs/types 959-960,1260;
house-floor ID default/override 1121,1192,1285; prefab child IDs 1786-1794.

The caller must bind the original house, complete SDK catalog and actual engine.
Contiguous suffixes are consistency evidence, not independent prefab enumeration
or proof of component semantics. No rule modifies SDK assetId or grants a target
eligibility flag. Procedural geometry has no invented exposure asset identifier.
"""

from __future__ import annotations

import math
import re
from typing import Any

ENGINE_REVISION = "f0825767cd50d69f666c7f282e54abfe58f1e917"
PROCEDURAL_TOOLS_SHA256 = "877589b9ed6b7dba31aa860d1dc8469e7ff0f415d1a3cdf29582d936212dc877"
_INDEX = re.compile(r"(?:0|[1-9][0-9]{0,9})\Z", flags=re.ASCII)


def _string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _identifier(value: Any, context: str) -> str:
    if not _string(value):
        raise ValueError(f"invalid {context} identifier")
    return value


def _source_objects(house: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    def visit(objects: Any) -> None:
        if not isinstance(objects, list):
            raise ValueError("source objects/children must be lists")
        for obj in objects:
            if not isinstance(obj, dict):
                raise ValueError("invalid source object")
            identity = _identifier(obj.get("id"), "source object")
            if identity in result:
                raise ValueError("duplicate source object identifier")
            result[identity] = obj
            visit(obj.get("children", []))

    visit(house.get("objects", []))
    return result


def _xyz(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, dict) or set(value) != {"x", "y", "z"}:
        return None
    if not all(type(v) in (int, float) and math.isfinite(v) for v in value.values()):
        return None
    return tuple(float(value[k]) for k in ("x", "y", "z"))


def _polygon(value: Any, *, floor: bool) -> bool:
    if not isinstance(value, list) or len(value) < (3 if floor else 4):
        return False
    points = [_xyz(point) for point in value]
    if any(point is None for point in points):
        return False
    if floor:
        if len({point[1] for point in points}) != 1:
            return False
        area = sum(
            a[0] * b[2] - b[0] * a[2] for a, b in zip(points, points[1:] + points[:1], strict=True)
        )
        return math.isfinite(area) and area != 0.0
    # Walls use paired top/bottom vertices, not necessarily polygon boundary order.
    origin = points[0]
    for a in points[1:]:
        u = [a[k] - origin[k] for k in range(3)]
        for b in points[1:]:
            v = [b[k] - origin[k] for k in range(3)]
            cross = (
                u[1] * v[2] - u[2] * v[1],
                u[2] * v[0] - u[0] * v[2],
                u[0] * v[1] - u[1] * v[0],
            )
            if all(math.isfinite(x) for x in cross) and any(x != 0.0 for x in cross):
                return True
    return False


def _geometry(house: dict[str, Any], objects: dict[str, Any]) -> tuple[dict, dict, str, bool, set]:
    namespaces = set(objects)
    indexed = {}
    for key in ("rooms", "walls", "doors", "windows"):
        values = house.get(key, [])
        if not isinstance(values, list):
            raise ValueError(f"source {key} must be a list")
        rows = {}
        for value in values:
            if not isinstance(value, dict):
                raise ValueError(f"invalid source {key} row")
            identity = _identifier(value.get("id"), key)
            if identity in namespaces:
                raise ValueError("source identifier namespace collision")
            namespaces.add(identity)
            rows[identity] = value
        indexed[key] = rows
    raw_root = house.get("id")
    root = "Floor" if raw_root in (None, "") else _identifier(raw_root, "house")
    if root in namespaces:
        raise ValueError("source house-root identifier namespace collision")
    rooms, walls = indexed["rooms"], indexed["walls"]
    metadata = house.get("metadata")
    valid = (
        isinstance(metadata, dict)
        and metadata.get("schema") == "1.0.0"
        and bool(rooms)
        and bool(walls)
        and all(_polygon(room.get("floorPolygon"), floor=True) for room in rooms.values())
        and all(
            _polygon(wall.get("polygon"), floor=False)
            and wall.get("roomId") in {*rooms, "exterior"}
            for wall in walls.values()
        )
    )
    return rooms, walls, root, valid, namespaces | {root}


def resolve_exposures(
    house: dict[str, Any], sdk_objects: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Explain each catalog exposure without changing or authorizing supervision.

    Direct nonempty catalog assets remain exposures even when source metadata
    differs; the verifier separately quarantines such targets. Missing catalog
    assets resolve only under exact, source-bound engine construction rules.
    """
    if not isinstance(house, dict) or not isinstance(sdk_objects, list):
        raise ValueError("source house and complete SDK object list are required")
    source = _source_objects(house)
    rooms, walls, root, geometry_valid, declared_ids = _geometry(house, source)
    sdk: dict[str, dict[str, Any]] = {}
    for obj in sdk_objects:
        if not isinstance(obj, dict):
            raise ValueError("invalid SDK object")
        identity = _identifier(obj.get("objectId"), "SDK object")
        _identifier(obj.get("objectType"), "SDK type")
        if identity in sdk:
            raise ValueError("duplicate SDK object identifier")
        sdk[identity] = obj

    families: dict[str, list[tuple[str, str]]] = {}
    for identity in sdk:
        parent, delimiter, suffix = identity.rpartition("___")
        if delimiter and parent in source:
            families.setdefault(parent, []).append((identity, suffix))
    valid_parents: set[str] = set()
    family_errors: dict[str, str] = {}
    for parent, members in families.items():
        asset = source[parent].get("assetId")
        indices = []
        if not _string(asset) or parent not in sdk or sdk[parent].get("assetId") != asset:
            family_errors[parent] = "source_parent_or_matching_sdk_parent_asset_missing"
            continue
        if any(identity in declared_ids for identity, _ in members):
            family_errors[parent] = "component_namespace_collides_with_declared_source"
            continue
        for _, suffix in members:
            if not _INDEX.fullmatch(suffix) or int(suffix) > 2147483647:
                break
            indices.append(int(suffix))
        if len(indices) != len(members) or sorted(indices) != list(range(len(members))):
            family_errors[parent] = "component_indices_not_canonical_contiguous_zero_based"
            continue
        valid_parents.add(parent)

    result = []
    for identity, obj in sdk.items():
        raw = obj.get("assetId")
        row = {
            "object_id": identity,
            "raw_asset_id": raw,
            "exposure_asset_id": None,
            "kind": "unknown",
            "source_id": None,
            "known": False,
            "diagnostic_notes": [],
        }
        notes = row["diagnostic_notes"]
        if _string(raw):
            row.update(exposure_asset_id=raw, kind="catalog_asset", known=True)
            if identity in source:
                row["source_id"] = identity
                if source[identity].get("assetId") != raw:
                    notes.append("source_sdk_asset_mismatch_remains_target_quarantined")
            notes.append("catalog_exposure_does_not_grant_target_eligibility")
        elif raw not in (None, ""):
            notes.append("invalid_or_padded_raw_sdk_asset_id")
        elif identity in source:
            notes.append("declared_source_instance_has_no_sdk_asset_id")
        elif geometry_valid and identity in walls and obj["objectType"] == "Wall":
            row.update(kind="procedural_wall", source_id=identity, known=True)
        elif geometry_valid and identity in rooms and obj["objectType"] == "Floor":
            row.update(kind="procedural_room_floor", source_id=identity, known=True)
        elif geometry_valid and identity == root and obj["objectType"] == "Floor":
            row.update(kind="procedural_house_floor", source_id=root, known=True)
        else:
            parent, delimiter, _ = identity.rpartition("___")
            if delimiter and parent in valid_parents:
                row.update(
                    exposure_asset_id=source[parent]["assetId"],
                    kind="source_prefab_component",
                    source_id=parent,
                    known=True,
                )
                notes.extend(
                    [
                        "parent_prefab_exposure_only_not_component_asset_identity",
                        "catalog_suffix_consistency_is_not_independent_prefab_enumeration",
                    ]
                )
            elif delimiter and parent in family_errors:
                notes.append(family_errors[parent])
            else:
                notes.append("no_source_bound_engine_construction_rule")
        if row["kind"].startswith("procedural_"):
            notes.append("source_procedural_geometry_has_no_prefab_asset_id")
        result.append(row)
    return result
