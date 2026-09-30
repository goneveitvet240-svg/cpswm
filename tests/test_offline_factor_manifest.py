"""Controlled data-plan checks; these fixtures are not natural training evidence."""

import copy
import gzip
import hashlib
import json
import subprocess
import sys

import offline_factor_manifest as task
import pytest


def object_row(index, *, asset=None, object_id=None, children=None):
    row = {
        "id": object_id or f"object-{index}",
        "assetId": asset or f"asset-{index}",
        "position": {"x": float(index), "y": 1.0, "z": 2.0},
    }
    if children is not None:
        row["children"] = children
    return row


def source_houses():
    return [
        {
            "metadata": {
                "agent": {
                    "horizon": 30,
                    "position": {"x": 0, "y": 0.95, "z": 0},
                    "rotation": {"x": 0, "y": 90, "z": 0},
                }
            },
            "objects": [object_row(i)],
            "rooms": [{"floor": i}],
        }
        for i in range(13)
    ]


def packed(houses):
    lines = [(json.dumps(house, indent=None) + "\n").encode() for house in houses]
    raw = gzip.compress(b"".join(lines), mtime=0)
    return raw, lines


def build(houses=None):
    raw, lines = packed(source_houses() if houses is None else houses)
    manifest, files = task._build_from_bytes(
        raw, expected_sha256=hashlib.sha256(raw).hexdigest(), revision="controlled-revision"
    )
    return manifest, files, raw, lines


def fixture_plan(monkeypatch, tmp_path):
    manifest, files, raw, _ = build()
    archive = tmp_path / "fixture.gz"
    archive.write_bytes(raw)

    def controlled_build(path):
        return task._build_from_bytes(
            path.read_bytes(),
            expected_sha256=hashlib.sha256(raw).hexdigest(),
            revision="controlled-revision",
        )

    monkeypatch.setattr(task, "build_manifest", controlled_build)
    output = tmp_path / "misleading_validation_directory"
    task.write_plan(archive, output)
    return archive, output, manifest, files


def test_plan_pins_source_bytes_partition_and_original_camera():
    manifest, files, raw, lines = build()
    assert manifest["source"]["archive_sha256"] == hashlib.sha256(raw).hexdigest()
    assert [h["index"] for h in manifest["houses"]] == list(range(13))
    assert [h["split"] for h in manifest["houses"]] == (
        ["diagnostic_only"] + ["train"] * 8 + ["validation"] * 4
    )
    assert list(files.values()) == lines
    assert all(
        h["house_sha256"] == hashlib.sha256(lines[i]).hexdigest()
        for i, h in enumerate(manifest["houses"])
    )
    assert all(h["original_agent"]["horizon"] == 30 for h in manifest["houses"])
    assert manifest["runtime_asset_audit_required"] is True
    assert manifest["supervision_export_authorized"] is False
    schedule = manifest["acquisition_schedule"]
    assert schedule["pre_capture_actions"] == ["PausePhysicsAutoSim", "Pass", "Pass"]
    assert [(x["action"], x["degrees"]) for x in schedule["observation_actions"]] == list(
        task.OBSERVATION_ACTIONS
    )
    assert len(schedule["observation_actions"]) == 8
    assert schedule["image_width"] == schedule["image_height"] == 320
    assert not schedule["target_conditioned_view_selection"]
    body = dict(manifest)
    digest = body.pop("manifest_sha256")
    assert digest == hashlib.sha256(task._json_bytes(body)).hexdigest()


def test_all_nested_assets_and_architecture_are_audited_and_shared_targets_quarantined():
    houses = source_houses()
    child = object_row(100, asset="common", children=[object_row(101, asset="grandchild")])
    houses[1]["objects"][0]["children"] = [child]
    houses[9]["objects"][0]["assetId"] = "common"
    houses[2]["windows"] = [{"id": "window-0", "assetId": "architecture-overlap"}]
    houses[10]["objects"][0]["assetId"] = "architecture-overlap"
    manifest, *_ = build(houses)
    train_child = manifest["houses"][1]["instances"][1]
    assert not train_child["eligible"]
    assert train_child["exclusion_reasons"] == ["asset_shared_by_train_and_validation"]
    assert len(manifest["houses"][1]["instances"]) == 3
    assert manifest["houses"][1]["instances"][2]["json_pointer"] == (
        "/objects/0/children/0/children/0"
    )
    assert manifest["houses"][1]["instances"][2]["eligible"]
    assert not manifest["houses"][9]["instances"][0]["eligible"]
    assert not manifest["houses"][10]["instances"][0]["eligible"]
    assert manifest["shared_train_validation_assets"] == ["architecture-overlap", "common"]


def test_validation_cannot_reuse_old_diagnostic_asset_even_with_new_instance_label():
    houses = source_houses()
    houses[11]["objects"][0].update(assetId="asset-0", id="renamed-validation-object")
    manifest, *_ = build(houses)
    old = manifest["houses"][0]["instances"][0]
    new = manifest["houses"][11]["instances"][0]
    assert not old["eligible"] and not new["eligible"]
    assert "validation_asset_seen_in_old_index0" in new["exclusion_reasons"]
    assert manifest["validation_assets_seen_in_index0"] == ["asset-0"]


@pytest.mark.parametrize("duplicate_kind", ["byte_equal", "labels_and_order"])
def test_duplicate_old_or_new_house_is_quarantined_without_substitution(duplicate_kind):
    houses = source_houses()
    houses[0]["objects"].append(object_row(100))
    houses[1] = copy.deepcopy(houses[0])
    if duplicate_kind == "labels_and_order":
        for obj in houses[1]["objects"]:
            obj["id"] = f"renamed-{obj['id']}"
        houses[1]["objects"].reverse()
        houses[1]["metadata"]["split"] = "not-really-validation"
        houses[1]["metadata"]["agent"]["rotation"]["y"] = 180
    manifest, *_ = build(houses)
    assert manifest["houses"][1]["duplicate_house_indices"] == [0]
    assert manifest["houses"][1]["split"] == "train"
    assert all(not row["eligible"] for row in manifest["houses"][1]["instances"])
    assert len(manifest["houses"]) == 13


@pytest.mark.parametrize(
    "mutation",
    [
        "empty_asset",
        "padded_asset",
        "missing_asset",
        "empty_id",
        "duplicate_child_id",
        "bad_children",
        "bad_object",
        "bad_horizon",
        "nan",
        "invalid_asset_in_window",
    ],
)
def test_malformed_or_ambiguous_records_fail_closed(mutation):
    houses = source_houses()
    obj = houses[1]["objects"][0]
    if mutation == "empty_asset":
        obj["assetId"] = ""
    elif mutation == "padded_asset":
        obj["assetId"] = " asset-1 "
    elif mutation == "missing_asset":
        del obj["assetId"]
    elif mutation == "empty_id":
        obj["id"] = ""
    elif mutation == "duplicate_child_id":
        obj["children"] = [object_row(111, object_id=obj["id"])]
    elif mutation == "bad_children":
        obj["children"] = {}
    elif mutation == "bad_object":
        houses[1]["objects"].append(None)
    elif mutation == "bad_horizon":
        houses[1]["metadata"]["agent"]["horizon"] = 0
    elif mutation == "nan":
        obj["position"]["x"] = float("nan")
    else:
        houses[1]["windows"] = [{"assetId": None}]
    with pytest.raises(ValueError):
        build(houses)


def test_duplicate_json_keys_and_missing_fixed_indices_are_rejected():
    _, _, _, lines = build()
    raw = gzip.compress(
        b"".join(lines).replace(b'"horizon": 30', b'"horizon": 0, "horizon": 30', 1)
    )
    with pytest.raises(ValueError, match="duplicate JSON key"):
        task._build_from_bytes(raw, expected_sha256=hashlib.sha256(raw).hexdigest(), revision="x")
    with pytest.raises(ValueError, match="all fixed indices"):
        build(source_houses()[:12])


def test_complete_compressed_archive_is_pinned_beyond_selected_prefix():
    manifest, _, raw, lines = build()
    changed_suffix = gzip.compress(b"".join(lines) + b'{"unselected": true}\n')
    with pytest.raises(ValueError, match="complete archive SHA256"):
        task._build_from_bytes(
            changed_suffix, expected_sha256=manifest["source"]["archive_sha256"], revision="x"
        )
    assert hashlib.sha256(raw).hexdigest() != hashlib.sha256(changed_suffix).hexdigest()


def test_production_api_and_cli_never_accept_fixture_or_pin_override(tmp_path):
    _, _, raw, _ = build()
    archive = tmp_path / "fixture.gz"
    archive.write_bytes(raw)
    with pytest.raises(ValueError, match="complete archive SHA256"):
        task.build_manifest(archive)
    result = subprocess.run(
        [
            sys.executable,
            task.__file__,
            "build",
            "--archive",
            str(archive),
            "--output",
            str(tmp_path / "out"),
            "--sha256",
            "fake",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and "unrecognized arguments" in result.stderr
    assert not (tmp_path / "out").exists()


def test_real_reconstruction_and_relocation_do_not_infer_split_from_directory(
    monkeypatch, tmp_path
):
    archive, output, manifest, _ = fixture_plan(monkeypatch, tmp_path)
    assert task.verify_plan(archive, output) == manifest
    destination = tmp_path / "another-train-label"
    output.rename(destination)
    assert task.verify_plan(archive, destination) == manifest
    assert task.verify_plan(archive, destination)["houses"][9]["split"] == "validation"


@pytest.mark.parametrize(
    "attack",
    [
        "split",
        "eligible",
        "house",
        "omit_child",
        "schedule",
        "extra_file",
        "missing_file",
        "symlink",
    ],
)
def test_complete_rehashed_forgery_fails_source_reconstruction(monkeypatch, tmp_path, attack):
    archive, output, manifest, _ = fixture_plan(monkeypatch, tmp_path)
    if attack == "house":
        path = output / "houses/house-01.json"
        path.write_bytes(path.read_bytes().replace(b"asset-1", b"asset-0"))
        manifest["houses"][1]["house_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif attack == "split":
        manifest["houses"][9]["split"] = "train"
        manifest["fixed_split"]["9"] = "train"
        manifest["fixed_split_sha256"] = hashlib.sha256(
            task._json_bytes(manifest["fixed_split"])
        ).hexdigest()
    elif attack == "eligible":
        row = manifest["houses"][0]["instances"][0]
        row.update(eligible=True, exclusion_reasons=[])
    elif attack == "omit_child":
        manifest["houses"][1]["instances"] = []
    elif attack == "schedule":
        manifest["acquisition_schedule"]["observation_actions"][1]["degrees"] = 90.0
        manifest["acquisition_schedule_sha256"] = hashlib.sha256(
            task._json_bytes(manifest["acquisition_schedule"])
        ).hexdigest()
    elif attack == "extra_file":
        (output / "extra.json").write_text("{}")
    elif attack == "missing_file":
        (output / "houses/house-01.json").unlink()
    else:
        path = output / "houses/house-01.json"
        other = tmp_path / "external-house.json"
        path.rename(other)
        path.symlink_to(other)
    del manifest["manifest_sha256"]
    manifest["manifest_sha256"] = hashlib.sha256(task._json_bytes(manifest)).hexdigest()
    (output / "manifest.json").write_bytes(task._json_bytes(manifest))
    with pytest.raises(ValueError):
        task.verify_plan(archive, output)


def test_write_refuses_existing_data_and_symlink_destination(monkeypatch, tmp_path):
    archive, output, _, _ = fixture_plan(monkeypatch, tmp_path)
    before = (output / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="refusing overwrite"):
        task.write_plan(archive, output)
    assert (output / "manifest.json").read_bytes() == before
    link = tmp_path / "alias"
    link.symlink_to(output, target_is_directory=True)
    with pytest.raises(ValueError, match="refusing overwrite"):
        task.write_plan(archive, link)


def test_empty_object_house_and_no_eligible_targets_remain_in_fixed_plan():
    houses = source_houses()
    houses[6]["objects"] = []
    manifest, *_ = build(houses)
    assert manifest["houses"][6]["eligible_instance_count"] == 0
    assert manifest["houses"][6]["instances"] == []
    assert manifest["houses"][6]["index"] == 6
    assert len(manifest["houses"]) == 13


def test_schedule_mutation_does_not_change_next_plan():
    first = task.acquisition_schedule()
    first["observation_actions"][0]["action"] = "TeleportFull"
    assert task.acquisition_schedule()["observation_actions"][0]["action"] == "Pass"
