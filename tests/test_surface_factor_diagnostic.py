"""Controlled diagnostic fixtures; never natural accuracy or calibration evidence.
PYTEST_DONT_REWRITE: decoder dependencies retain their source identity.
"""

import json
import shutil
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import diagnose_surface_factors as task
import numpy as np
import pytest
from test_instance_correspondence import event_fixture
from test_owned_rgbd_support import RGBDSupportDecoder
from test_unity_rgbd import event_for, packet
from unity_instance_audit_worker import export_instances

from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.owned_visual_support import OwnedVisualAction, OwnedVisualSupport, _frame_support
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ObservationCommand, ObservationDelivery


class EmptyDecoder(RGBDSupportDecoder):
    def measurements(self, observations, *, cutoff):
        return tuple(
            replace(f, candidates=()) for f in super().measurements(observations, cutoff=cutoff)
        )


def save(path, value):
    path.write_text(StateCodec().dumps(value))


def archive(tmp_path, decoder=None, depth=None, repeat=False):
    directory = tmp_path / "history"
    private = directory / "unity-logs/evaluator_only"
    sdk = private / "sdk-events"
    sdk.mkdir(parents=True)
    decoder = decoder or RGBDSupportDecoder()
    event = event_fixture()
    event.metadata.update(event_for(depth=depth).metadata)
    # All three SDK objects retained; the Bottle is invisible.
    event.metadata["objects"] = event_fixture().metadata["objects"]
    event.metadata["colors"] = event_fixture().metadata["colors"]
    for i, obj in enumerate(event.metadata["objects"]):
        obj["position"] = dict(x=float(i), y=0.0, z=5.0)
        obj["axisAlignedBoundingBox"] = dict(center=dict(x=float(i), y=0.5, z=5.0))
    event.metadata["lastAction"] = "Pass"
    history, actions = [], []
    scope = (uuid4(), uuid4(), uuid4())
    for i in range(4 + (2 if repeat else 1)):
        raw, when = packet(event=event_for(depth=depth), scope=scope)
        action = raw[0].envelope().metadata.source_id
        command = ObservationCommand(
            uuid4() if i < 4 else UUID(action),
            uuid4(),
            "Pass",
            0.0,
            "controlled diagnostic",
            (),
            when - timedelta(seconds=2),
        )
        delivery = ObservationDelivery(command.action_id, raw, True, "", when)
        owner = None if i < 4 else str(command.action_id)
        row = dict(index=i, owner=owner, requested=dict(action="Pass"), metadata=event.metadata)
        (sdk / f"{i:03d}.json").write_text(json.dumps(row))
        (sdk / f"{i:03d}-rgb.npy").write_bytes(raw[0].payload_bytes)
        (sdk / f"{i:03d}-depth.npy").write_bytes(raw[1].payload_bytes)
        np.save(sdk / f"{i:03d}-mask.npy", event.instance_masks["Apple|one"], allow_pickle=False)
        export_instances(event, private / "instances", i, owner)
        if i >= 4:
            (frame,) = decoder.measurements(raw, cutoff=when)
            public = replace(
                _frame_support(raw[0], frame, when),
                geometry=task.surface_support(raw, frame, cutoff=when),
            )
            history.append((command, delivery))
            actions.append(OwnedVisualAction(command, "DELIVERED", None, None, (public,)))
    support = OwnedVisualSupport(task.decoder_binding(decoder), "a" * 64, tuple(actions))
    save(directory / "owned-history.json", tuple(history))
    save(directory / "visual-support.json", support)
    (directory / "manifest.json").write_text(
        json.dumps(
            dict(
                status="COMPLETE",
                sensor_profile="rgbd_self_pose",
                private_instance_evaluation=True,
                decoder_binding=decoder.binding_sha256,
                source="b" * 64,
            )
        )
    )
    (directory / "evaluator_house.json").write_text(
        json.dumps(dict(metadata=dict(cpswm_diagnostic_target="Apple|one")))
    )
    return directory, decoder, content_sha256(task.inventory(directory))


def test_complete_matrix_keeps_non_target_categories_invisible_objects_and_position_definitions(
    tmp_path,
):
    directory, decoder, pin = archive(tmp_path)
    public, report, _ = task.diagnose(directory, decoder=decoder, input_sha256=pin)
    row = report["frames"][0]
    assert report["summary"]["candidates"] == 3 and report["summary"]["samples"] == 9
    assert [c["category"] for c in row["candidates"]] == ["apple", "apple", "cup"]
    assert all(len(c["overlaps"]) == 3 for c in row["candidates"])
    assert all(c["overlaps"][1]["intersection_pixels"] == 0 for c in row["candidates"])
    assert [r["pixels"] for r in row["instances"]] == [8, 0, 8]  # sorted SDK IDs
    first = row["candidates"][0]
    apple = next(o for o in first["overlaps"] if o["object_id"] == "Apple|one")
    assert apple["intersection_pixels"] == 8
    point = first["samples"][0]["nominal_world_xyz_m"]
    sample = apple["sample_displacements"][0]
    assert sample["to_sdk_transform"]["delta_xyz_m"] == pytest.approx(
        [point[0], point[1], point[2] - 5]
    )
    assert sample["to_sdk_aabb_center"]["delta_xyz_m"][1] == pytest.approx(point[1] - 0.5)
    assert "Apple|one" not in json.dumps(public) and "sdk_aabb" not in json.dumps(public)
    assert all(
        report[k] is False
        for k in (
            "automatic_identity_assignment",
            "empirical_calibration",
            "online_memory_write",
            "historical_full_replay",
        )
    )


@pytest.mark.parametrize("case", ["no_candidates", "invalid_depth", "repeat"])
def test_empty_observations_and_dependent_repeats_are_retained(tmp_path, case):
    directory, decoder, pin = archive(
        tmp_path,
        decoder=EmptyDecoder() if case == "no_candidates" else None,
        depth=np.zeros((4, 4), dtype=np.float32) if case == "invalid_depth" else None,
        repeat=case == "repeat",
    )
    _, report, _ = task.diagnose(directory, decoder=decoder, input_sha256=pin)
    summary = report["summary"]
    if case == "no_candidates":
        assert summary["candidates"] == 0 and summary["target_visible_frames"] == 1
        assert len(report["frames"][0]["instances"]) == 3
    elif case == "invalid_depth":
        assert summary["candidates"] == 3 and summary["samples"] == 0
    else:
        assert (
            summary["frames"] == 2
            and summary["unique_rgb"] == summary["unique_geometry_inputs"] == 1
        )


@pytest.mark.parametrize(
    "attack",
    ["mask", "catalog", "owner", "camera", "depth", "position", "target_mask", "omitted_frame"],
)
def test_re_pinned_complete_wrong_sources_are_rejected(tmp_path, attack):
    directory, decoder, _ = archive(tmp_path)
    private = directory / "unity-logs/evaluator_only"
    sdk = private / "sdk-events/004.json"
    info_path = private / "instances/004.json"
    row, info = json.loads(sdk.read_text()), json.loads(info_path.read_text())
    match = ""
    if attack == "mask":
        p = private / "instances/004-masks.npz"
        with np.load(p) as source:
            arrays = {k: source[k].copy() for k in source.files}
        arrays["mask_0000"] = ~arrays["mask_0000"]  # equal area, wrong pixels
        np.savez_compressed(p, **arrays)
        match = "mask differs"
    elif attack == "catalog":
        info["catalog"].pop()
        match = "omits or duplicates"
    elif attack == "owner":
        row["owner"] = info["action_id"] = str(uuid4())
        match = "owner or result"
    elif attack == "camera":
        row["metadata"]["cameraPosition"]["x"] += 1
        match = "camera or segmentation"
    elif attack == "depth":
        np.save(private / "sdk-events/004-depth.npy", np.zeros((4, 4), dtype=np.float32))
        match = "RGB-D pixels"
    elif attack == "position":
        row["metadata"]["objects"][0]["position"]["x"] = float("nan")
        match = "nonfinite SDK position"
    elif attack == "target_mask":
        np.save(private / "sdk-events/004-mask.npy", np.zeros((4, 4), dtype=bool))
        match = "target mask"
    else:
        (private / "instances/003.json").unlink()
        match = "coverage"
    sdk.write_text(json.dumps(row))
    info_path.write_text(json.dumps(info))
    with pytest.raises(ValueError, match=match):
        task.diagnose(
            directory, decoder=decoder, input_sha256=content_sha256(task.inventory(directory))
        )


def test_materials_are_portable_but_pins_cannot_be_replaced_by_report_claims(tmp_path):
    directory, decoder, pin = archive(tmp_path)
    original = task.diagnose(directory, decoder=decoder, input_sha256=pin)
    moved = tmp_path / "moved"
    shutil.copytree(directory, moved)
    assert task.diagnose(moved, decoder=decoder, input_sha256=pin) == original
    (moved / "manifest.json").write_text((moved / "manifest.json").read_text() + " ")
    with pytest.raises(ValueError, match="external input pin"):
        task.diagnose(moved, decoder=decoder, input_sha256=pin)


def test_private_reference_changes_do_not_change_public_predictions(tmp_path):
    directory, decoder, pin = archive(tmp_path)
    public, original, _ = task.diagnose(directory, decoder=decoder, input_sha256=pin)
    p = directory / "unity-logs/evaluator_only/sdk-events/004.json"
    row = json.loads(p.read_text())
    row["metadata"]["objects"][0]["position"]["x"] += 7.0
    p.write_text(json.dumps(row))
    fresh, updated, _ = task.diagnose(
        directory, decoder=decoder, input_sha256=content_sha256(task.inventory(directory))
    )
    assert public == fresh
    assert original["public_predictions_sha256"] == updated["public_predictions_sha256"]
    assert original["frames"] != updated["frames"]


def test_duplicate_frames_are_not_removed_even_when_pixels_identical(tmp_path):
    directory, decoder, _ = archive(tmp_path, repeat=True)
    history = task.load(directory / "owned-history.json")
    expected = task.load(directory / "visual-support.json")
    forged_history = (history[0], history[0])
    forged_support = replace(expected, actions=(expected.actions[0], expected.actions[0]))
    with pytest.raises(ValueError, match="duplicate history"):
        task.public_predictions(forged_history, decoder, forged_support)


def test_failed_delivery_is_rejected_instead_of_disappearing(tmp_path):
    directory, decoder, _ = archive(tmp_path)
    history = task.load(directory / "owned-history.json")
    command, delivered = history[0]
    expected = task.load(directory / "visual-support.json")
    failed = replace(delivered, success=False, error="capture failed")
    with pytest.raises(ValueError, match="failed or mismatched"):
        task.public_predictions(((command, failed),), decoder, expected)


def test_real_runtime_issued_support_uses_full_binding(tmp_path):
    from test_joint_camera_feedback import setup
    from test_owned_rgbd_support import collect

    decoder = RGBDSupportDecoder()
    stream, store, _, _, start = setup(tmp_path / "state.sqlite", decoder=decoder)
    try:
        collect(stream, start)
        expected = stream.visual_observation_support()
        assert expected.decoder_binding_sha256 != decoder.binding_sha256
        public = task.public_predictions(stream.observation_history(), decoder, expected)
        assert len(public) == 1 and public[0][2] == expected.actions[0].frames[0]
    finally:
        store.close()


@pytest.mark.parametrize("status", ["READY", "OUTCOME_UNCERTAIN", "CANCELLED_STALE_JOINT"])
def test_unobserved_action_states_retain_history_without_fake_pixels(tmp_path, status):
    directory, decoder, _ = archive(tmp_path)
    history = task.load(directory / "owned-history.json")
    support = task.load(directory / "visual-support.json")
    command = replace(history[0][0], action_id=uuid4())
    pending = OwnedVisualAction(command, status, None, None, ())
    expected = replace(support, actions=(*support.actions, pending))
    rows = task.public_predictions((*history, (command, status)), decoder, expected)
    assert len(rows) == 1


@pytest.mark.parametrize("attack", ["candidate_omission", "world_point", "authority"])
def test_complete_forged_public_support_is_rejected_by_real_recomputation(tmp_path, attack):
    directory, decoder, _ = archive(tmp_path)
    support = task.load(directory / "visual-support.json")
    a = support.actions[0]
    f = a.frames[0]
    if attack == "candidate_omission":
        f = replace(
            f,
            frame=replace(f.frame, candidates=f.frame.candidates[:1]),
            candidates=f.candidates[:1],
            geometry=replace(f.geometry, candidates=f.geometry.candidates[:1]),
        )
    elif attack == "world_point":
        g = f.geometry
        c = g.candidates[0]
        samples = tuple(replace(s, nominal_world_xyz_m=(0.0, 0.0, 0.0)) for s in c.samples)
        f = replace(
            f, geometry=replace(g, candidates=(replace(c, samples=samples), *g.candidates[1:]))
        )
    else:
        support = replace(support, memory_write_authorized=True)
    support = replace(support, actions=(replace(a, frames=(f,)),))
    save(directory / "visual-support.json", support)
    with pytest.raises(ValueError, match=r"public candidates/geometry|authority"):
        task.diagnose(
            directory, decoder=decoder, input_sha256=content_sha256(task.inventory(directory))
        )
