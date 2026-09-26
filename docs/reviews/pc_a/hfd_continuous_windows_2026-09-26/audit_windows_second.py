"""Second review: full valid clock forgery, window trust, failures and source drift."""

import copy
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_hfd_continuous_windows import (  # noqa: E402
    FixtureHands,
    TwoPeopleDetector,
    dense_fixture,
    frontend_module,
)
from test_hfd_observation_alignment import NOW, runtime_pin  # noqa: E402

from cpswm.data_preflight import hfd_observation_alignment as module  # noqa: E402
from cpswm.perception_mapping.natural_vision import NaturalVisionEvidenceProducer  # noqa: E402

# Share only packet resealing mechanics; this round's attacks and acceptance
# criteria exercise continuous windows, not the earlier sparse-frame matrix.
spec = importlib.util.spec_from_file_location(
    "prior_reseal",
    ROOT / "docs/reviews/pc_a/hfd_observation_alignment_2026-09-26/audit_alignment_second.py",
)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)


def test_valid_complete_clock_compression_passes_structure_but_not_source(tmp_path, monkeypatch):
    args, _ = dense_fixture(tmp_path, monkeypatch)
    root = args["output"]
    backup = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    by_key = {}
    for path in (root / "runtime").rglob("*.receipt.json"):
        row = json.loads(path.read_bytes())
        row["author_clock_seconds"] = (
            row["author_clock_origin_seconds"] + row["original_frame_index"] / 600
        )
        row["media_time_seconds"] = row["author_clock_seconds"] - row["author_clock_origin_seconds"]
        path.write_bytes(module.encoded(row))
        key = str(path.relative_to(root / "runtime")).removesuffix(".receipt.json")
        by_key[key] = row["author_clock_seconds"]
    labels = root / "evaluator/author_supervision.jsonl"
    rows = [json.loads(v) for v in labels.read_text().splitlines()]
    for row in rows:
        row["author_frame"]["timestamp_seconds"] = by_key[row["key"]]
    labels.write_bytes(b"".join(module.encoded(r) for r in rows))
    prior.reseal(root)
    assert (
        len(module.load_runtime_windows(root / "runtime", manifest_sha256=runtime_pin(root))) == 8
    )
    with pytest.raises(ValueError, match="original source"):
        module.align_hfd_training(**args, verify=True)
    for path, raw in backup.items():
        path.write_bytes(raw)
    assert module.align_hfd_training(**args, verify=True)["selected_frames"] == 32


@pytest.mark.parametrize("attack", ("omission", "count", "origin", "time_order", "scope", "policy"))
def test_complete_resealed_window_inconsistency_rejected_before_model(
    tmp_path, monkeypatch, attack
):
    args, _ = dense_fixture(tmp_path, monkeypatch)
    root = args["output"]
    index = root / "runtime/index.jsonl"
    rows = [json.loads(v) for v in index.read_text().splitlines()]
    original_pin = runtime_pin(root)
    backup = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    if attack == "omission":
        gone = rows.pop(1)
        for suffix in (".npy", ".envelope.json", ".receipt.json"):
            (root / "runtime" / (gone["key"] + suffix)).unlink()
        index.write_bytes(b"".join(module.encoded(r) for r in rows))
    elif attack == "policy":
        p = root / "runtime/manifest.json"
        m = json.loads(p.read_bytes())
        m["sampling_policy"] = "phase_centred_answer_selection"
        p.write_bytes(module.encoded(m))
    elif attack == "scope":
        p = root / "runtime" / (rows[1]["key"] + ".envelope.json")
        m = json.loads(p.read_bytes())
        for field in ("identity", "metadata"):
            m[field]["trace_id"] = "00000000-0000-0000-0000-000000000001"
        p.write_bytes(module.encoded(m))
    else:
        p = root / "runtime" / (rows[1]["key"] + ".receipt.json")
        r = json.loads(p.read_bytes())
        if attack == "count":
            r["source_frame_count"] += 1
        if attack == "origin":
            r["author_clock_origin_seconds"] -= 1
        if attack == "time_order":
            r["author_clock_seconds"] = r["author_clock_origin_seconds"]
        r["media_time_seconds"] = r["author_clock_seconds"] - r["author_clock_origin_seconds"]
        p.write_bytes(module.encoded(r))
    prior.reseal(root)
    front = frontend_module()
    monkeypatch.setattr(
        front,
        "FasterNaturalAppearanceDetector",
        lambda **_: pytest.fail("invalid window reached detector"),
    )
    with pytest.raises(ValueError):
        front.run(
            root / "runtime",
            runtime_pin(root),
            tmp_path / "weights",
            tmp_path / "hands",
            tmp_path / "run",
        )
    assert not (tmp_path / "run").exists()
    for path, raw in backup.items():
        path.write_bytes(raw)
    assert len(module.load_runtime_windows(root / "runtime", manifest_sha256=original_pin)) == 8


def test_second_manifest_read_custody_drift_cannot_publish_windows(tmp_path, monkeypatch):
    args, _ = dense_fixture(tmp_path, monkeypatch)
    root = args["output"] / "runtime"
    pin = runtime_pin(args["output"])
    original = module.pinned_bytes
    reads = 0

    def change(base, name, expected=None):
        nonlocal reads
        value = original(base, name, expected)
        if name == "manifest.json":
            reads += 1
            if reads == 2:
                (root / "late-member").write_text("answer")
        return value

    with monkeypatch.context() as local:
        local.setattr(module, "pinned_bytes", change)
        with pytest.raises(ValueError, match="changed during admission"):
            module.load_runtime_windows(root, manifest_sha256=pin)
    (root / "late-member").unlink()
    assert len(module.load_runtime_windows(root, manifest_sha256=pin)) == 8


def test_continuous_selection_has_no_outcome_order_clock_channel(tmp_path, monkeypatch):
    args, _ = dense_fixture(tmp_path, monkeypatch)
    manifest = json.loads((args["intake"] / "manifest.json").read_bytes())
    left, _ = module.alignment_artifacts(
        args["intake"], manifest, imported_at=NOW, sampling="continuous"
    )
    other = copy.deepcopy(manifest)
    for row in other["report"]["trials"]:
        row["outcome"] = 3 - row["outcome"]
    right, _ = module.alignment_artifacts(
        args["intake"], other, imported_at=NOW, sampling="continuous"
    )
    assert {
        k: v for k, v in left.items() if k.startswith("runtime/") and k != "runtime/manifest.json"
    } == {
        k: v for k, v in right.items() if k.startswith("runtime/") and k != "runtime/manifest.json"
    }


def test_hand_failure_retries_same_prefix_and_source_swap_cannot_restore(tmp_path, monkeypatch):
    args, _ = dense_fixture(tmp_path, monkeypatch)
    windows = module.load_runtime_windows(
        args["output"] / "runtime", manifest_sha256=runtime_pin(args["output"])
    )
    raw = tuple(r for _, r in windows[0][1])
    identity = raw[0].envelope().identity
    detector = TwoPeopleDetector(
        None, identity.household_id, identity.session_id, identity.trace_id
    )
    hands = FixtureHands(None, detector._scope, True)
    producer = NaturalVisionEvidenceProducer(detector, hands)
    cutoff = raw[-1].envelope().arrival_time
    producer.infer(raw[:1], cutoff=cutoff)
    before = producer.checkpoint_state()
    hands.fail = True
    with pytest.raises(RuntimeError):
        producer.infer(raw, cutoff=cutoff)
    assert producer.checkpoint_state() == before
    hands.fail = False
    producer.infer(raw, cutoff=cutoff)
    good = producer.checkpoint_state()
    bad = copy.deepcopy(good)
    bad["hand_frames"] = (
        replace(bad["hand_frames"][0], input_sha256="0" * 64),
        *bad["hand_frames"][1:],
    )
    with pytest.raises(ValueError):
        producer.restore_state(bad)
    assert producer.checkpoint_state() == good
    producer.restore_state(good)
    assert producer.hand_object_evidence()


def test_sparse_gap_and_dense_clock_causal_control_uses_same_threshold(tmp_path, monkeypatch):
    args, _ = dense_fixture(tmp_path, monkeypatch, count=300)
    raw = module.load_runtime_windows(
        args["output"] / "runtime", manifest_sha256=runtime_pin(args["output"])
    )[0][1]
    identity = raw[0][1].envelope().identity
    detector = TwoPeopleDetector(
        None, identity.household_id, identity.session_id, identity.trace_id
    )
    dense = NaturalVisionEvidenceProducer(detector)
    observations = tuple(r for _, r in raw)
    cutoff = observations[-1].envelope().arrival_time
    dense.infer(observations, cutoff=cutoff)
    assert any(
        d.status == "ASSOCIATED_GEOMETRIC" for a, _ in dense.interactions() for d in a.detections
    )
    # Alter only a controlled observation's bound clock to 2 seconds, preserving
    # valid immutable wire/relative clock schema; never treated as author evidence.
    from cpswm.system.reproducibility import content_sha256

    b = observations[1]
    receipt = json.loads(b.archive_sampling_json)
    receipt["author_clock_seconds"] = receipt["author_clock_origin_seconds"] + 2
    receipt["media_time_seconds"] = 2.0
    delayed = replace(
        b, archive_sampling_json=json.dumps(receipt), capture_receipt_sha256=content_sha256(receipt)
    )
    sparse = NaturalVisionEvidenceProducer(detector)
    sparse.infer((observations[0], delayed), cutoff=cutoff)
    assert all(d.status == "NEW_UNVERIFIED" for a, _ in sparse.interactions() for d in a.detections)
