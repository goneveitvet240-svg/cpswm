"""Second review: complete plausible input forgery, recovery and actual effects."""

import hashlib
import json
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_hfd_continuous_windows import (  # noqa: E402
    FixtureHands,
    TwoPeopleDetector,
    dense_fixture,
    frontend_module,
)
from test_hfd_observation_alignment import runtime_pin  # noqa: E402
from test_proposal_hand_input import context, features, pixel, with_hands  # noqa: E402
from test_runtime_candidates import LEDGER  # noqa: E402

from cpswm.data_preflight.proposal_inference_session import encoded  # noqa: E402
from cpswm.data_preflight.proposal_trainer import save_checkpoint  # noqa: E402
from cpswm.data_preflight.runtime_candidate_session import RuntimeCandidateSession  # noqa: E402
from cpswm.data_preflight.typed_proposal_networks import ARMS, TypedProposalNetwork  # noqa: E402


def session_fixture(tmp_path, arm):
    torch.set_num_threads(2)
    with torch.random.fork_rng():
        torch.manual_seed(33)
        model = TypedProposalNetwork(arm).eval()
    path = tmp_path / arm
    pin = save_checkpoint(model, {"track": "COMPONENT_FIXTURE_ONLY", "optimizer_steps": 0}, path)
    return path, pin, RuntimeCandidateSession(path, manifest_sha256=pin, seed=11)


@pytest.mark.parametrize("arm", ARMS)
def test_complete_forged_geometry_reaches_q_and_restores_without_semantic_authority(tmp_path, arm):
    path, pin, session = session_fixture(tmp_path, arm)
    good = context([with_hands(pixel(0), x=25)])
    forged = context([with_hands(pixel(0), x=55)])
    assert features(forged)[0]["hand_object_measurements"][0]["minimum_landmark_to_box_px"] == 0
    args = dict(request_id="same-source", context=good, bootstrap_ledger_lineage_ref=LEDGER)
    session.process(**args)
    before = session.snapshot()
    with pytest.raises(ValueError):
        session.process(**{**args, "context": forged})
    assert session.snapshot() == before
    # A new request using fully consistent forged landmarks is acceptable as an
    # uncalibrated measurement claim. Build its entire support and real model scores.
    result = session.process(
        request_id="forged-new-claim", context=forged, bootstrap_ledger_lineage_ref=LEDGER
    )
    assert result.support.targets
    assert result.support.report["native_publication_authorized"] is False
    assert result.support.report["ledger_authorized"] is False
    snapshot = session.snapshot()
    restored = RuntimeCandidateSession.restore(
        path,
        manifest_sha256=pin,
        snapshot=snapshot,
        snapshot_sha256=hashlib.sha256(snapshot).hexdigest(),
    )
    assert restored.snapshot() == snapshot
    assert (
        restored.process(
            request_id="forged-new-claim", context=forged, bootstrap_ledger_lineage_ref=LEDGER
        )
        == result
    )
    # Continue the actual RNG/request history identically after recovery.
    later = context([with_hands(pixel(1), x=45)])
    request = dict(request_id="next", context=later, bootstrap_ledger_lineage_ref=LEDGER)
    assert session.process(**request) == restored.process(**request)
    assert session.snapshot() == restored.snapshot()


@pytest.mark.parametrize("attack", ["source_swap", "empty_to_missing", "coordinate", "gold"])
def test_resealed_snapshot_cannot_keep_old_support_after_input_rewrite(tmp_path, attack):
    path, pin, session = session_fixture(tmp_path, ARMS[0])
    ctx = context([with_hands(pixel(0))])
    session.process(request_id="first", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
    original = session.snapshot()
    payload = json.loads(original)
    row = payload["engine"]["records"][0]["inputs"]["context"]["visible"]["pixel_observations"][0]
    if attack == "source_swap":
        row["hand_observation"]["input_sha256"] = "f" * 64
    if attack == "empty_to_missing":
        row["hand_observation"] = None
    if attack == "coordinate":
        row["hand_observation"]["candidates"][0]["landmarks_xy_pixels"] = [[55, 35]] * 21
    if attack == "gold":
        row["hand_observation"]["contact_confirmed"] = True
    bad = encoded(payload)
    with pytest.raises(ValueError):
        RuntimeCandidateSession.restore(
            path, manifest_sha256=pin, snapshot=bad, snapshot_sha256=hashlib.sha256(bad).hexdigest()
        )
    good = RuntimeCandidateSession.restore(
        path,
        manifest_sha256=pin,
        snapshot=original,
        snapshot_sha256=hashlib.sha256(original).hexdigest(),
    )
    assert good.snapshot() == original


def test_mutated_nested_candidate_is_revalidated_before_rng_or_request_mutation(tmp_path):
    path, pin, session = session_fixture(tmp_path, ARMS[1])
    ctx = context([with_hands(pixel(0))])
    before = session.snapshot()
    object.__setattr__(
        ctx.visible.pixel_observations[0].hand_observation.candidates[0],
        "landmarks_xy_pixels",
        ((float("inf"), 0.0),) * 21,
    )
    with pytest.raises(ValueError):
        session.process(request_id="bad", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
    assert session.snapshot() == before
    restored = RuntimeCandidateSession.restore(
        path,
        manifest_sha256=pin,
        snapshot=before,
        snapshot_sha256=hashlib.sha256(before).hexdigest(),
    )
    request = dict(
        request_id="good",
        context=context([with_hands(pixel(0))]),
        bootstrap_ledger_lineage_ref=LEDGER,
    )
    assert session.process(**request) == restored.process(**request)


def test_real_frontend_export_contains_hands_but_cannot_write_memory_or_execute(
    tmp_path, monkeypatch
):
    args, _ = dense_fixture(tmp_path, monkeypatch)
    frontend = frontend_module()
    monkeypatch.setattr(frontend, "FasterNaturalAppearanceDetector", TwoPeopleDetector)
    monkeypatch.setattr(frontend, "NaturalHandDetector", FixtureHands)
    output = tmp_path / "output"
    summary = frontend.run(
        args["output"] / "runtime",
        runtime_pin(args["output"]),
        tmp_path / "weights",
        tmp_path / "hands",
        output,
    )
    from cpswm.data_preflight.proposal_samples import ProposalContext

    seen = 0
    for path in output.rglob("context.json"):
        ctx = ProposalContext.model_validate_json(path.read_bytes())
        rows = features(ctx)
        assert len(rows) == 4
        assert all(r["hands"]["candidates"] and r["hand_object_measurements"] for r in rows)
        assert all("UNRESOLVED" in r["hand_object_status"] for r in rows)
        assert not ctx.visible.detections and not ctx.visible.actor_evidence
        seen += 1
    assert seen == 8
    assert all(
        w["core_ledger_unchanged"] and w["perception_restore_equal"] and w["execution_traces"] == 0
        for w in summary["windows"]
    )
    assert (
        summary["memory_writes"]
        == summary["executed_actions"]
        == summary["natural_semantic_publications"]
        == 0
    )


def test_pinned_consumer_rebuilds_legal_features_and_rejects_changed_context_before_model(
    tmp_path, monkeypatch
):
    args, _ = dense_fixture(tmp_path, monkeypatch)
    frontend = frontend_module()
    monkeypatch.setattr(frontend, "FasterNaturalAppearanceDetector", TwoPeopleDetector)
    monkeypatch.setattr(frontend, "NaturalHandDetector", FixtureHands)
    output = tmp_path / "front"
    frontend.run(
        args["output"] / "runtime",
        runtime_pin(args["output"]),
        tmp_path / "weights",
        tmp_path / "hands",
        output,
    )
    import run_hfd_hand_proposals as consumer

    pin = hashlib.sha256((output / "result.json").read_bytes()).hexdigest()
    contexts, _, coverage = consumer.load_frontend(output, pin)
    assert len(contexts) == 8 and coverage["frames"] == 32
    assert coverage["regional_hands_in_model_input"] == 32
    assert coverage["hand_object_measurements_in_model_input"] == 32
    path = output / sorted(contexts)[0] / "context.json"
    original = path.read_bytes()
    data = json.loads(original)
    data["visible"]["pixel_observations"][0]["hand_observation"] = None
    path.write_bytes(encoded(data))
    monkeypatch.setattr(
        consumer,
        "RuntimeCandidateSession",
        lambda *a, **k: pytest.fail("bad custody reached network"),
    )
    with pytest.raises(ValueError, match="SHA256"):
        consumer.run(output, pin, tmp_path / "training", tmp_path / "bad", ARMS[0], 2)
    assert not (tmp_path / "bad").exists()
    path.write_bytes(original)
    assert consumer.load_frontend(output, pin)[2] == coverage
