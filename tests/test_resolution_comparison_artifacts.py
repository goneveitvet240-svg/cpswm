"""Real 640-pixel receipt and a fully resealed false-resolution package."""

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_neural_pixel_camera_loop import ARMS
from verify_neural_camera_comparison import verify_episode

from cpswm.system.reproducibility import content_sha256


@pytest.fixture(scope="module")
def configured():
    if not all(
        os.environ.get(k)
        for k in ("CPSWM_RESOLUTION_FIXTURE", "CPSWM_CHECKPOINTS", "CPSWM_FASTERRCNN_WEIGHTS")
    ):
        pytest.skip("explicit live 640-pixel artifact and pinned checkpoints required")
    return Path(os.environ["CPSWM_RESOLUTION_FIXTURE"]), dict(
        weights=Path(os.environ["CPSWM_FASTERRCNN_WEIGHTS"]),
        checkpoint=Path(os.environ["CPSWM_CHECKPOINTS"]) / ARMS[0] / "checkpoint",
        method=ARMS[0],
        frontend="fasterrcnn",
        site="north",
    )


def test_actual_640_capture_is_recomputed_without_assuming_detection_success(configured):
    path, args = configured
    result = verify_episode(path, **args, image_size=640)
    assert result["image_size"] == 640 and result["all_actions_succeeded"]
    assert any(x["target_pixels"] > 0 for x in result["frames"])


def test_complete_resealed_metadata_cannot_relabel_640_pixels_as_320(tmp_path, configured):
    path, args = configured
    out = tmp_path / "forged"
    shutil.copytree(path, out)
    p = out / "result.json"
    r = json.loads(p.read_text())
    r["image_size"] = r["dependencies"]["image_size"] = 320
    digest = content_sha256(r["dependencies"])
    p.write_text(json.dumps(r))
    with sqlite3.connect(out / "state.sqlite") as db:
        db.execute("UPDATE checkpoint SET dependencies=?", (digest,))
        db.execute("UPDATE deployment SET dependencies=?", (digest,))
        db.commit()
    with pytest.raises(ValueError, match="actual image dimensions differ"):
        verify_episode(out, **args, image_size=320)


def test_correct_640_package_cannot_enter_a_320_matrix(configured):
    path, args = configured
    with pytest.raises(ValueError, match="capture resolution differs"):
        verify_episode(path, **args, image_size=320)
