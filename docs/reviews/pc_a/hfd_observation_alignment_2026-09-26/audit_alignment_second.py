"""Second review: complete resealing, side channels, admission and source custody."""

import copy
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_full_hfd_training import fixture_archive  # noqa: E402
from test_hfd_observation_alignment import NOW, fixture, frontend_module, runtime_pin  # noqa: E402

from cpswm.data_preflight import full_hfd_training as intake_module  # noqa: E402
from cpswm.data_preflight import hfd_observation_alignment as module  # noqa: E402
from cpswm.system.reproducibility import content_sha256  # noqa: E402


def reseal(root):
    """Rewrite *every* local digest/count; source reconstruction still owns truth."""
    # Repair all internal payload -> envelope -> receipt -> index -> evaluator
    # links. These attacks must pass structural runtime admission with a forged
    # self-issued pin; only the independent original source can refute them.
    index_path = root / "runtime/index.jsonl"
    index = [json.loads(v) for v in index_path.read_text().splitlines()]
    for row in index:
        base = root / "runtime" / row["key"]
        payload = Path(str(base) + ".npy").read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        env_path = Path(str(base) + ".envelope.json")
        env = json.loads(env_path.read_bytes())
        env["payload"].update(payload_sha256=digest, size_bytes=len(payload))
        env_path.write_bytes(module.encoded(env))
        receipt_path = Path(str(base) + ".receipt.json")
        receipt = json.loads(receipt_path.read_bytes())
        receipt["payload_sha256"] = digest
        receipt_path.write_bytes(module.encoded(receipt))
        row.update(payload_sha256=digest, receipt_sha256=content_sha256(receipt))
    index_path.write_bytes(b"".join(module.encoded(r) for r in index))
    by_key = {r["key"]: r for r in index}
    evaluator_path = root / "evaluator/author_supervision.jsonl"
    evaluator = [json.loads(v) for v in evaluator_path.read_text().splitlines()]
    for row in evaluator:
        if row["key"] in by_key:
            row["payload_sha256"] = by_key[row["key"]]["payload_sha256"]
    evaluator_path.write_bytes(b"".join(module.encoded(r) for r in evaluator))
    runtime = json.loads((root / "runtime/manifest.json").read_bytes())
    runtime["files"] = {
        str(p.relative_to(root / "runtime")): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "runtime").rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    (root / "runtime/manifest.json").write_bytes(module.encoded(runtime))
    manifest = json.loads((root / "manifest.json").read_bytes())
    manifest["files"] = {
        str(p.relative_to(root)): {
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in root.rglob("*")
        if p.is_file() and p != root / "manifest.json"
    }
    (root / "manifest.json").write_bytes(module.encoded(manifest))


@pytest.mark.parametrize(
    "attack", ("labels", "pixels", "clock", "index", "authority", "omission", "extra")
)
def test_complete_resealed_alignment_rejected_by_source_then_legal_retry(
    tmp_path, monkeypatch, attack
):
    args, baseline = fixture(tmp_path, monkeypatch)
    root = args["output"]
    original = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    path = root / "evaluator/author_supervision.jsonl"
    rows = [json.loads(v) for v in path.read_text().splitlines()]
    if attack == "labels":
        # Keep well formed and fully paired; invent a success/interaction target.
        rows[0]["author_outcome"] = 2
        rows[0]["author_frame"]["human_action"] = "interact"
        rows[0]["author_frame"]["human_action_id"] = 2
        path.write_bytes(b"".join(module.encoded(r) for r in rows))
    elif attack == "pixels":
        files = sorted((root / "runtime").rglob("*.npy"))
        files[0].write_bytes(files[1].read_bytes())
    elif attack == "clock":
        path = next((root / "runtime").rglob("*.receipt.json"))
        receipt = json.loads(path.read_bytes())
        receipt["author_clock_seconds"] += 10
        receipt["author_clock_origin_seconds"] += 10
        path.write_bytes(module.encoded(receipt))
    elif attack == "index":
        rows[0]["author_frame"]["frame_index"] = 2
        path.write_bytes(b"".join(module.encoded(r) for r in rows))
    elif attack == "authority":
        manifest = json.loads((root / "manifest.json").read_bytes())
        manifest.update(full_proposal_training_ready=True, native_publication_authorized=True)
        (root / "manifest.json").write_bytes(module.encoded(manifest))
    elif attack == "omission":
        index = root / "runtime/index.jsonl"
        lines = index.read_bytes().splitlines(keepends=True)
        index.write_bytes(b"".join(lines[1:]))
    else:
        (root / "evaluator/hidden-answer.json").write_text("{}")
    reseal(root)
    if attack in {"labels", "pixels", "clock", "index", "authority"}:
        assert (
            len(
                module.load_runtime_observations(
                    root / "runtime", manifest_sha256=runtime_pin(root)
                )
            )
            == 6
        )
    with pytest.raises(ValueError):
        module.align_hfd_training(**args, verify=True)
    for path in list(root.rglob("*")):
        if path.is_file() and path not in original:
            path.unlink()
    for path, raw in original.items():
        path.write_bytes(raw)
    assert module.align_hfd_training(**args, verify=True) == baseline


def test_outcome_sort_order_cannot_encode_answers_in_import_times(tmp_path, monkeypatch):
    args, _ = fixture(tmp_path, monkeypatch)
    manifest = json.loads((args["intake"] / "manifest.json").read_bytes())
    files, _ = module.alignment_artifacts(args["intake"], manifest, imported_at=NOW)
    changed = copy.deepcopy(manifest)
    for row in changed["report"]["trials"]:
        row["outcome"] = 3 - row["outcome"]
    other, _ = module.alignment_artifacts(args["intake"], changed, imported_at=NOW)

    # Compare the clocks separately, so a random metadata UUID cannot hide
    # a real outcome-order channel in a before-fix reproduction.
    def clock_values(items):
        return {
            k: (json.loads(v)["capture_time"], json.loads(v)["arrival_time"])
            for k, v in items.items()
            if k.endswith(".envelope.json")
        }

    assert clock_values(files) == clock_values(other)
    # Parent intake digest naturally changes, and is provenance, not model input.
    assert {
        k: v for k, v in files.items() if k.startswith("runtime/") and k != "runtime/manifest.json"
    } == {
        k: v for k, v in other.items() if k.startswith("runtime/") and k != "runtime/manifest.json"
    }
    assert (
        files["evaluator/author_supervision.jsonl"] != other["evaluator/author_supervision.jsonl"]
    )


def test_duplicate_sensor_source_does_not_create_two_labelled_training_examples(
    tmp_path, monkeypatch
):
    archive, metadata, intake = fixture_archive(tmp_path, monkeypatch)
    intake_module.inspect_full_training(archive, metadata, intake)
    output = tmp_path / "alias"
    with pytest.raises(ValueError, match="duplicate sensor source"):
        module.align_hfd_training(
            archive=archive, metadata=metadata, intake=intake, output=output, imported_at=NOW
        )
    assert not output.exists()


@pytest.mark.parametrize("kind", ("symlink", "hardlink", "fifo"))
def test_special_runtime_members_rejected_before_detector_initialization(
    tmp_path, monkeypatch, kind
):
    args, _ = fixture(tmp_path, monkeypatch)
    root = args["output"] / "runtime"
    pin = runtime_pin(args["output"])
    alias = root / "alias"
    if kind == "symlink":
        alias.symlink_to(root / "index.jsonl")
    elif kind == "hardlink":
        os.link(root / "index.jsonl", alias)
    else:
        os.mkfifo(alias)
    front = frontend_module()
    monkeypatch.setattr(
        front, "FasterNaturalAppearanceDetector", lambda **_: pytest.fail("bad input reached model")
    )
    try:
        with pytest.raises(ValueError):
            front.run(root, pin, tmp_path / "weights", tmp_path / "run")
        assert not (tmp_path / "run").exists()
    finally:
        alias.unlink()
    assert len(module.load_runtime_observations(root, manifest_sha256=pin)) == 6


def test_late_runtime_mutation_during_custody_fails_before_model(tmp_path, monkeypatch):
    args, _ = fixture(tmp_path, monkeypatch)
    root = args["output"] / "runtime"
    pin = runtime_pin(args["output"])
    original = module.pinned_bytes
    reads = 0

    def corrupt(base, name, expected=None):
        nonlocal reads
        value = original(base, name, expected)
        reads += 1
        if reads == 20:  # Last of 6 * 3 payload reads + manifest/index.
            (root / "late-answer").write_text("success")
        return value

    monkeypatch.setattr(module, "pinned_bytes", corrupt)
    with pytest.raises(ValueError, match="changed"):
        module.load_runtime_observations(root, manifest_sha256=pin)


def test_truncated_codec_frame_hints_do_not_define_original_indices(tmp_path, monkeypatch):
    args, _ = fixture(tmp_path, monkeypatch)
    video = (args["intake"] / "raw/trial0000/head_cam.mp4").read_bytes()
    with pytest.raises(ValueError, match="count/shape"):
        module.decode_original_frames(video, indices=(0, 1), count=2, shape=(32, 48, 3))
    with pytest.raises(ValueError, match="incomplete"):
        module.decode_original_frames(video, indices=(0, 3), count=4, shape=(32, 48, 3))
