"""Second review: complete checkpoint forgery and actual diagnostic consequences."""

import copy
import json
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_hfd_continuous_windows import (  # noqa: E402
    FixtureHands,
    TwoPeopleDetector,
    dense_fixture,
    frontend_module,
)
from test_hfd_observation_alignment import runtime_pin  # noqa: E402

from cpswm.data_preflight.hfd_observation_alignment import load_runtime_windows  # noqa: E402
from cpswm.perception_mapping.natural_vision import NaturalVisionEvidenceProducer  # noqa: E402


def populated(tmp_path, monkeypatch):
    args, _ = dense_fixture(tmp_path, monkeypatch)
    rows = load_runtime_windows(
        args["output"] / "runtime", manifest_sha256=runtime_pin(args["output"])
    )[0][1]
    raws = tuple(raw for _, raw in rows)
    identity = raws[0].envelope().identity
    detector = TwoPeopleDetector(
        None, identity.household_id, identity.session_id, identity.trace_id
    )
    producer = NaturalVisionEvidenceProducer(detector)
    producer.infer(raws, cutoff=raws[-1].envelope().arrival_time)
    return producer, detector, raws


@pytest.mark.parametrize(
    "attack", ["drop_same", "drop_pairs", "wrong_pair", "unconditional", "iou", "pair_tracks"]
)
def test_forged_identity_resolution_cannot_restore_and_legal_retry_succeeds(
    tmp_path, monkeypatch, attack
):
    producer, detector, _ = populated(tmp_path, monkeypatch)
    good = producer.checkpoint_state()
    bad = copy.deepcopy(good)
    assoc, readout = bad["interactions"][-1]
    assert len(readout.role_alternatives) == 2
    pairs, roles = list(readout.person_identity_pairs), list(readout.role_alternatives)
    if attack == "drop_same":
        pairs[0] = replace(pairs[0], hypotheses=("distinct_people",))
    if attack == "drop_pairs":
        pairs = []
    if attack == "wrong_pair":
        roles[0] = replace(roles[0], identity_pair_id=uuid4())
    if attack == "unconditional":
        roles[0] = replace(roles[0], required_identity_hypothesis="observed_distinct_people")
    if attack == "iou":
        pairs[0] = replace(pairs[0], box_iou=0.99)
    if attack == "pair_tracks":
        pairs[0] = replace(pairs[0], track_ids=(uuid4(), uuid4()))
    bad["interactions"] = (
        *bad["interactions"][:-1],
        (
            assoc,
            replace(readout, person_identity_pairs=tuple(pairs), role_alternatives=tuple(roles)),
        ),
    )
    before = producer.checkpoint_state()
    with pytest.raises(ValueError, match="interactions differ"):
        producer.restore_state(bad)
    assert producer.checkpoint_state() == before
    recovered = NaturalVisionEvidenceProducer(detector)
    recovered.restore_state(good)
    assert recovered.checkpoint_state() == good


def test_internally_complete_detection_forgery_is_diagnostic_not_identity_authority(
    tmp_path, monkeypatch
):
    producer, detector, raws = populated(tmp_path, monkeypatch)
    bad = producer.checkpoint_state()
    # Forge the complete cached detector result and all derived relations. Raw pixels,
    # source hashes, coverage and model binding remain plausible. Restoration verifies
    # consistency, not that a trusted model actually produced these boxes.
    frames = tuple(
        replace(f, candidates=tuple(replace(d, detector_score=0.999) for d in f.candidates))
        for f in bad["frames"]
    )
    bad["frames"] = frames
    bad["interactions"] = producer._recompute_interactions(frames)
    restored = NaturalVisionEvidenceProducer(detector)
    restored.restore_state(bad)
    assert restored.frames() == frames
    assert all(
        p.status == "UNRESOLVED_GEOMETRY_ONLY"
        for _, r in restored.interactions()
        for p in r.person_identity_pairs
    )
    # The producer's real semantic output is None even on this accepted positive path.
    assert restored.infer(raws, cutoff=raws[-1].envelope().arrival_time) is None
    assert all(not r.memory_write_authorized for _, r in restored.interactions())


def test_accepted_two_person_predictions_reach_candidates_without_memory_or_action(
    tmp_path, monkeypatch
):
    args, _ = dense_fixture(tmp_path, monkeypatch)
    frontend = frontend_module()
    monkeypatch.setattr(frontend, "FasterNaturalAppearanceDetector", TwoPeopleDetector)
    monkeypatch.setattr(frontend, "NaturalHandDetector", FixtureHands)
    result = frontend.run(
        args["output"] / "runtime",
        runtime_pin(args["output"]),
        tmp_path / "weights",
        tmp_path / "hands",
        tmp_path / "out",
    )
    assert result["role_alternatives"] > 0
    artifact = json.loads((tmp_path / "out/result.json").read_bytes())
    for row in artifact["records"]:
        readout = row["interaction"]
        pairs = {p["pair_id"]: p for p in readout["person_identity_pairs"]}
        for role in readout["role_alternatives"]:
            pair = pairs[role["identity_pair_id"]]
            assert "same_person_multiple_detections" in pair["hypotheses"]
            assert role["required_identity_hypothesis"] == "distinct_people"
        assert not readout["memory_write_authorized"]
    assert all(
        w["support"]["candidate_count"] > 0
        and w["core_ledger_unchanged"]
        and w["perception_restore_equal"]
        and w["execution_traces"] == 0
        for w in result["windows"]
    )
    assert (
        result["memory_writes"]
        == result["executed_actions"]
        == result["natural_semantic_publications"]
        == 0
    )
