"""Source-bound exposure rules; controlled fixtures are not prefab ground truth."""

import copy

import offline_factor_asset_provenance as task
import pytest


def house():
    return {
        "metadata": {"schema": "1.0.0"},
        "objects": [{"id": "cabinet", "assetId": "Cabinet_1", "children": []}],
        "rooms": [
            {
                "id": "room|1",
                "floorPolygon": [
                    {"x": 0, "y": 0, "z": 0},
                    {"x": 2, "y": 0, "z": 0},
                    {"x": 2, "y": 0, "z": 2},
                    {"x": 0, "y": 0, "z": 2},
                ],
            }
        ],
        "walls": [
            {
                "id": "wall|1",
                "roomId": "room|1",
                "polygon": [
                    {"x": 0, "y": 0, "z": 0},
                    {"x": 2, "y": 0, "z": 0},
                    {"x": 0, "y": 2, "z": 0},
                    {"x": 2, "y": 2, "z": 0},
                ],
            }
        ],
        "doors": [],
        "windows": [],
    }


def obj(identity, asset="", kind="Drawer"):
    return {"objectId": identity, "assetId": asset, "objectType": kind}


def catalog():
    return [
        obj("cabinet", "Cabinet_1", "Cabinet"),
        obj("cabinet___0"),
        obj("cabinet___1"),
        obj("room|1", kind="Floor"),
        obj("wall|1", kind="Wall"),
        obj("Floor", kind="Floor"),
    ]


def resolve(source=None, sdk=None):
    return task.resolve_exposures(
        house() if source is None else source, catalog() if sdk is None else sdk
    )


def test_exact_engine_construction_resolves_exposure_only_and_preserves_raw_inputs():
    source, sdk = house(), catalog()
    before = copy.deepcopy((source, sdk))
    rows = resolve(source, sdk)
    assert (source, sdk) == before
    assert len(rows) == len(sdk)
    assert [row["object_id"] for row in rows] == [row["objectId"] for row in sdk]
    assert all(row["known"] for row in rows)
    assert [row["kind"] for row in rows] == [
        "catalog_asset",
        "source_prefab_component",
        "source_prefab_component",
        "procedural_room_floor",
        "procedural_wall",
        "procedural_house_floor",
    ]
    for row in rows[1:3]:
        assert row["raw_asset_id"] == ""
        assert row["exposure_asset_id"] == "Cabinet_1"
        assert row["source_id"] == "cabinet"
    for row in rows[3:]:
        assert row["raw_asset_id"] == "" and row["exposure_asset_id"] is None
    assert all("eligible" not in row and "target_eligible" not in row for row in rows)


def test_source_objects_children_are_recursive_and_parent_prefix_match_is_exact():
    source = house()
    source["objects"][0]["children"] = [{"id": "cabinet-inner", "assetId": "Inner_2"}]
    sdk = [
        obj("cabinet-inner", "Inner_2"),
        obj("cabinet-inner___0"),
        obj("cabinet-inne___0"),
        obj("cabinet-inner-similar___0"),
    ]
    rows = resolve(source, sdk)
    assert rows[1]["known"] and rows[1]["exposure_asset_id"] == "Inner_2"
    assert all(not row["known"] for row in rows[2:])


@pytest.mark.parametrize(
    "suffix",
    ["00", "01", "-1", "+1", "1.0", " 1", "1 ", "\uff11", "2147483648", "999999999999999999", "x"],
)
def test_noncanonical_child_index_poisons_the_whole_missing_asset_family(suffix):
    sdk = [obj("cabinet", "Cabinet_1"), obj("cabinet___0"), obj("cabinet___" + suffix)]
    # A padded SDK identity itself fails even earlier than provenance resolution.
    if suffix.endswith(" "):
        with pytest.raises(ValueError, match="identifier"):
            resolve(sdk=sdk)
        return
    rows = resolve(sdk=sdk)
    assert all(not row["known"] for row in rows[1:])
    assert all(
        "component_indices_not_canonical_contiguous_zero_based" in row["diagnostic_notes"]
        for row in rows[1:]
    )


@pytest.mark.parametrize("indices", [(1,), (0, 2), (0, 1, 3)])
def test_missing_or_nonzero_start_indices_remain_unknown(indices):
    rows = resolve(sdk=[obj("cabinet", "Cabinet_1")] + [obj(f"cabinet___{i}") for i in indices])
    assert all(not row["known"] for row in rows[1:])


@pytest.mark.parametrize("parent", [None, "WrongAsset", "", " Cabinet_1", 7])
def test_absent_or_mismatched_parent_cannot_lend_its_source_asset(parent):
    sdk = [obj("cabinet___0")]
    if parent is not None:
        sdk.insert(0, obj("cabinet", parent))
    row = resolve(sdk=sdk)[-1]
    assert not row["known"] and row["exposure_asset_id"] is None
    assert "source_parent_or_matching_sdk_parent_asset_missing" in row["diagnostic_notes"]


def test_component_name_that_is_declared_source_instance_cannot_borrow_parent_asset():
    source = house()
    source["objects"].append({"id": "cabinet___0", "assetId": "Different_2"})
    rows = resolve(source)
    assert not rows[1]["known"] and not rows[2]["known"]
    assert "declared_source_instance_has_no_sdk_asset_id" in rows[1]["diagnostic_notes"]
    assert "component_namespace_collides_with_declared_source" in rows[2]["diagnostic_notes"]


def test_component_namespace_collision_with_architecture_is_not_accepted():
    source = house()
    source["doors"] = [{"id": "cabinet___0", "assetId": "Door_1"}]
    rows = resolve(source)
    assert all(not row["known"] for row in rows[1:3])


@pytest.mark.parametrize(
    "attack", ["duplicate_sdk", "duplicate_nested_source", "room_object", "wall_room", "house_room"]
)
def test_ambiguous_identifiers_are_rejected(attack):
    source, sdk = house(), catalog()
    if attack == "duplicate_sdk":
        sdk.append(copy.deepcopy(sdk[1]))
    elif attack == "duplicate_nested_source":
        source["objects"][0]["children"] = [{"id": "cabinet", "assetId": "Cabinet_1"}]
    elif attack == "room_object":
        source["rooms"][0]["id"] = "cabinet"
    elif attack == "wall_room":
        source["walls"][0]["id"] = "room|1"
    else:
        source["id"] = "room|1"
    with pytest.raises(ValueError, match=r"duplicate|collision"):
        resolve(source, sdk)


@pytest.mark.parametrize(
    "identity,kind",
    [
        ("wall-forged", "Wall"),
        ("room-forged", "Floor"),
        ("wall|1", "Floor"),
        ("room|1", "Wall"),
        ("Floor", "Wall"),
        ("Floor", "floor"),
    ],
)
def test_geometry_needs_exact_source_id_and_exact_engine_type(identity, kind):
    row = resolve(sdk=[obj(identity, kind=kind)])[0]
    assert not row["known"] and row["exposure_asset_id"] is None


@pytest.mark.parametrize(
    "attack",
    [
        "empty_house",
        "no_rooms",
        "no_walls",
        "zero_floor",
        "zero_wall",
        "nan",
        "false_coordinate",
        "bad_schema",
        "unknown_room_reference",
    ],
)
def test_empty_or_invalid_geometry_cannot_explain_away_root_floor(attack):
    source = house()
    if attack == "empty_house":
        source = {}
    elif attack == "no_rooms":
        source["rooms"] = []
    elif attack == "no_walls":
        source["walls"] = []
    elif attack == "zero_floor":
        source["rooms"][0]["floorPolygon"] = [{"x": 0, "y": 0, "z": 0}] * 4
    elif attack == "zero_wall":
        source["walls"][0]["polygon"] = [{"x": 0, "y": 0, "z": 0}] * 4
    elif attack == "nan":
        source["rooms"][0]["floorPolygon"][0]["x"] = float("nan")
    elif attack == "false_coordinate":
        source["rooms"][0]["floorPolygon"][0]["x"] = False
    elif attack == "bad_schema":
        source["metadata"]["schema"] = "forged"
    else:
        source["walls"][0]["roomId"] = "absent-room"
    row = resolve(source, [obj("Floor", kind="Floor")])[0]
    assert not row["known"]


def test_custom_house_root_id_follows_pinned_engine_override():
    source = house()
    source["id"] = "custom-house-root"
    rows = resolve(source, [obj("custom-house-root", kind="Floor"), obj("Floor", kind="Floor")])
    assert rows[0]["known"] and rows[0]["kind"] == "procedural_house_floor"
    assert not rows[1]["known"]


def test_direct_catalog_assets_remain_exposure_even_if_target_source_mismatches():
    rows = resolve(sdk=[obj("cabinet", "Another_1"), obj("new-unlisted-object", "Unlisted_2")])
    assert all(row["known"] and row["kind"] == "catalog_asset" for row in rows)
    assert rows[0]["exposure_asset_id"] == "Another_1"
    assert "source_sdk_asset_mismatch_remains_target_quarantined" in rows[0]["diagnostic_notes"]
    assert rows[1]["source_id"] is None


@pytest.mark.parametrize("raw", [None, "", " ", " padded ", 42, False])
def test_unrecognized_instance_assets_remain_unknown_without_mutation(raw):
    row = resolve(sdk=[obj("unrecognized", raw)])[0]
    assert not row["known"] and row["exposure_asset_id"] is None
    assert row["raw_asset_id"] == raw


def test_none_asset_procedural_geometry_preserves_none_without_synthetic_identity():
    row = resolve(sdk=[obj("wall|1", None, "Wall")])[0]
    assert row["known"] and row["raw_asset_id"] is None and row["exposure_asset_id"] is None


def test_component_with_real_own_asset_is_catalog_exposure_not_overwritten_by_parent():
    sdk = catalog()
    sdk[1]["assetId"] = "ChildAsset_2"
    rows = resolve(sdk=sdk)
    assert rows[1]["kind"] == "catalog_asset" and rows[1]["exposure_asset_id"] == "ChildAsset_2"
    assert rows[2]["kind"] == "source_prefab_component"
    assert rows[2]["exposure_asset_id"] == "Cabinet_1"
