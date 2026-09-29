"""Raw simulator evidence positive paths and consequence-oriented corruption probes."""

import copy
import json
from pathlib import Path

import numpy as np
import pytest
from audit_simulation_evidence import inspect_frame, inventory, mask_box, overlap, sha

from cpswm.system.continuous_state_codec import StateCodec

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "docs/reviews/pc_a/neural_native_loop_2026-09-29/evidence/round8/snapshots/south_320"


def actual_frame():
    command, delivery = StateCodec().loads((CASE / "capture-state.json").read_text())
    private = CASE / "unity-logs/evaluator_only"
    return [
        command,
        delivery,
        json.loads((private / "actions.json").read_text())[0],
        (private / "000-rgb.npy").read_bytes(),
        np.load(private / "000-mask.npy"),
        320,
        225,
        json.loads((private / "initial.json").read_text()),
    ]


def test_real_owned_frame_is_accepted():
    assert inspect_frame(*actual_frame()) == [161, 155, 186, 184]


@pytest.mark.parametrize(
    "change,reason",
    [
        ("rotation", "camera configuration"),
        ("fov", "camera configuration"),
        ("translation", "camera translated"),
        ("pixel_count", "mask statistics"),
        ("action", "action ownership"),
        ("clock", "capture time"),
        ("image", "RGB ownership"),
        ("mask", "mask statistics"),
    ],
)
def test_record_corruption_has_specific_rejection(change, reason):
    args = actual_frame()
    if change == "rotation":
        args[2]["agent"]["rotation"]["y"] += 15
    elif change == "fov":
        args[2]["fov"] = 90
    elif change == "translation":
        args[2]["camera_position"]["x"] += 0.2
    elif change == "pixel_count":
        args[2]["target_pixels"] += 1
    elif change == "action":
        args[2]["request"]["action"] = "RotateLeft"
    elif change == "clock":
        args[2]["capture_time"] = "2026-01-01T00:00:00+00:00"
    elif change == "image":
        args[3] = args[3][:-1] + bytes([args[3][-1] ^ 1])
    elif change == "mask":
        args[4] = np.zeros_like(args[4])
    with pytest.raises(ValueError, match=reason):
        inspect_frame(*args)


def test_wrong_object_positive_remains_zero_target_overlap():
    # High category score cannot change the two separate rectangles.
    assert overlap([158, 117, 182, 140], [161, 155, 186, 184]) == 0
    assert overlap([161, 155, 186, 184], [161, 155, 186, 184]) == 1
    assert overlap([161, 155, 186, 184], None) == 0
    assert mask_box(np.zeros((8, 8), dtype=bool)) is None


def test_complete_manifest_rejects_changed_content(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    f = root / "payload"
    f.write_bytes(b"owned")
    manifest = tmp_path / "manifest.json"
    rows = [dict(path="payload", bytes=5, sha256=sha(b"owned"))]
    manifest.write_text(json.dumps(dict(artifacts=rows)))
    assert inventory(root, manifest) == dict(verified_files=1, bytes=5)
    f.write_bytes(b"other")
    with pytest.raises(ValueError, match="artifact changed"):
        inventory(root, manifest)


def test_manifest_does_not_allow_duplicate_rows(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "a").write_bytes(b"a")
    row = dict(path="a", bytes=1, sha256=sha(b"a"))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(dict(artifacts=[row, copy.copy(row)])))
    with pytest.raises(ValueError, match="duplicate inventory"):
        inventory(root, manifest)
