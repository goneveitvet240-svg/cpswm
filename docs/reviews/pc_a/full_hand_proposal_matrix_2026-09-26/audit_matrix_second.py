"""Second review: normalized omissions, forged complete scores and actual all-window output."""

import hashlib
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tools")]
from run_hfd_hand_proposals import checked_scores, run  # noqa: E402
from test_hfd_continuous_windows import (  # noqa: E402
    FixtureHands,
    TwoPeopleDetector,
    dense_fixture,
    frontend_module,
)
from test_hfd_observation_alignment import runtime_pin  # noqa: E402
from test_proposal_hand_input import context, pixel, with_hands  # noqa: E402

from cpswm.data_preflight.proposal_trainer import (  # noqa: E402
    derive_execution_checkpoint,
    save_checkpoint,
)
from cpswm.data_preflight.runtime_candidates import generate_runtime_candidates  # noqa: E402
from cpswm.data_preflight.typed_proposal_networks import ARMS, TypedProposalNetwork  # noqa: E402
from cpswm.system.reproducibility import content_sha256  # noqa: E402


def forged_scores(targets):
    targets = sorted(targets, key=lambda t: content_sha256(t.model_dump(mode="json")))
    return tuple(
        SimpleNamespace(
            target=t,
            probability=SimpleNamespace(
                proposal_sha256=content_sha256(t.model_dump(mode="json")),
                joint_log_probability=-math.log(len(targets)),
            ),
        )
        for t in targets
    )


@pytest.mark.parametrize(
    "attack", ["omit_renormalize", "duplicate_renormalize", "wrong_target", "nan", "positive"]
)
def test_normalized_but_incomplete_or_forged_score_list_is_rejected(attack):
    targets = generate_runtime_candidates(
        context([with_hands(pixel(0))]), bootstrap_ledger_lineage_ref="hybrid-ledger:" + "a" * 64
    ).targets
    full = forged_scores(targets)
    assert checked_scores(full, targets)[1] == pytest.approx(1)
    if attack == "omit_renormalize":
        bad = forged_scores(targets[:-1])
    elif attack == "duplicate_renormalize":
        bad = forged_scores((*targets[:-1], targets[0]))
    else:
        bad = list(full)
        if attack == "wrong_target":
            bad[0].probability.proposal_sha256 = "f" * 64
        if attack == "nan":
            bad[0].probability.joint_log_probability = float("nan")
        if attack == "positive":
            bad[0].probability.joint_log_probability = 0.1
    with pytest.raises(RuntimeError):
        checked_scores(bad, targets)
    # A fully consistent forged uniform distribution passes STRUCTURE only; that
    # is not model or calibration authentication. Actual sampling checks follow.
    assert checked_scores(forged_scores(targets), targets)[1] == pytest.approx(1)


def setup_front(tmp_path, monkeypatch):
    args, _ = dense_fixture(tmp_path, monkeypatch, count=7)
    frontend = frontend_module()
    monkeypatch.setattr(frontend, "FasterNaturalAppearanceDetector", TwoPeopleDetector)
    monkeypatch.setattr(frontend, "NaturalHandDetector", FixtureHands)
    front = tmp_path / "front"
    frontend.run(
        args["output"] / "runtime",
        runtime_pin(args["output"]),
        tmp_path / "vision",
        tmp_path / "hands",
        front,
    )
    training = tmp_path / "derived"
    rows = []
    for arm in ARMS:
        with torch.random.fork_rng():
            torch.manual_seed(21)
            model = TypedProposalNetwork(arm).eval()
        original = tmp_path / "original" / arm
        pin = save_checkpoint(
            model, {"track": "COMPONENT_FIXTURE_ONLY", "optimizer_steps": 0}, original
        )
        derived = derive_execution_checkpoint(
            original, manifest_sha256=pin, directory=training / arm, max_nodes=65536
        )
        rows.append({"arm": arm, "checkpoint_manifest_sha256": derived})
    (training / "summary.json").write_text(
        json.dumps(
            {
                "track": "COMPONENT_FIXTURE_WEIGHTS_EXECUTION_DERIVATION",
                "new_optimizer_steps": 0,
                "production_authorized": False,
                "architecture_selected": None,
                "runs": rows,
            }
        )
    )
    return front, hashlib.sha256((front / "result.json").read_bytes()).hexdigest(), training


def test_all_windows_real_network_scores_keep_recovery_scope_and_artifact_coverage(
    tmp_path, monkeypatch
):
    front, pin, training = setup_front(tmp_path, monkeypatch)
    output = tmp_path / "all"
    result = run(
        front, pin, training, output, ARMS[1], 2, window_scope="all", restore_scope="first"
    )
    assert len(result["runs"]) == 8
    assert sum(r["restore_and_next_draw_equal"] is True for r in result["runs"]) == 2
    assert sum(r["restore_and_next_draw_equal"] is None for r in result["runs"]) == 6
    assert all(r["scoring_left_rng_and_requests_unchanged"] for r in result["runs"])
    files = [
        p
        for p in output.glob("*.json")
        if p.name != "summary.json" and not p.name.endswith("snapshot.json")
    ]
    assert len(files) == 8
    for path in files:
        detail = json.loads(path.read_bytes())
        assert all(len(c["scores"]) == detail["candidates"] for c in detail["conditions"].values())
    assert (
        result["memory_writes"]
        == result["executed_actions"]
        == result["natural_semantic_publications"]
        == 0
    )
    actual = json.loads((front / "result.json").read_bytes())
    assert all(w["core_ledger_unchanged"] and w["execution_traces"] == 0 for w in actual["windows"])


def test_complete_valid_q_forgery_is_caught_against_actual_sampled_probability(
    tmp_path, monkeypatch
):
    from cpswm.data_preflight.proposal_inference_session import ProposalInferenceSession

    front, pin, training = setup_front(tmp_path, monkeypatch)
    monkeypatch.setattr(
        ProposalInferenceSession,
        "score_support",
        lambda self, *, context, support: forged_scores(support),
    )
    output = tmp_path / "forged"
    with pytest.raises(RuntimeError, match="sampled probability differs"):
        run(front, pin, training, output, ARMS[0], 2, window_scope="all", restore_scope="first")
    assert not list(output.glob("*.json"))
    # No summary or successful case was written, despite every score being finite,
    # normalized, and paired with a complete legitimate target.
