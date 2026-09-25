"""Causal support/state-machine tests; pixels and posteriors here are fixtures."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import torch

from cpswm.data_preflight.proposal_decoder import TypedProposalDistribution
from cpswm.data_preflight.proposal_inference_session import ProposalInferenceSession, encoded
from cpswm.data_preflight.proposal_perception import ProposalPixelObservation
from cpswm.data_preflight.proposal_samples import (
    FullHypothesis,
    ProposalContext,
    RevisionRecord,
    semantic_state,
)
from cpswm.data_preflight.proposal_trainer import save_checkpoint
from cpswm.data_preflight.runtime_candidate_session import RuntimeCandidateSession
from cpswm.data_preflight.runtime_candidates import (
    bootstrap_pixel_context,
    event_grid,
    generate_runtime_candidates,
)
from cpswm.data_preflight.typed_proposal_networks import ARMS, TypedProposalNetwork
from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleChangeCause,
    ParticleRegimeDecision,
)

NOW = datetime(2026, 9, 26, tzinfo=UTC)
SNAPSHOT = UUID(int=9900)
LEDGER = "hybrid-ledger:" + "a" * 64


def pixel(index, *, delayed=0, detected=True):
    return ProposalPixelObservation.model_validate(
        {
            "observation_id": UUID(int=100 + index),
            "household_id": UUID(int=1),
            "session_id": UUID(int=2),
            "trace_id": UUID(int=3),
            "sensor_id": "camera",
            "frame_id": "camera-frame",
            "capture_time": NOW + timedelta(seconds=index),
            "arrival_time": NOW + timedelta(seconds=index + delayed),
            "inference_cutoff": NOW + timedelta(seconds=index + delayed),
            "input_sha256": "b" * 64,
            "receipt_sha256": "c" * 64,
            "model_id": "synthetic-test-detections",
            "weights_sha256": "d" * 64,
            "torch_version": "fixture",
            "torchvision_version": "fixture",
            "minimum_score": 0.5,
            "width": 100,
            "height": 100,
            "resize_roundoff_clamps": 0,
            "candidates": [
                {
                    "candidate_id": UUID(int=1000 + index * 2 + j),
                    "category": category,
                    "detector_score": 0.7,
                    "box_xyxy": box,
                }
                for j, (category, box) in enumerate(
                    [("person", (10, 10, 40, 70)), ("cup", (50, 30, 60, 40))]
                )
            ]
            if detected
            else [],
            "calibration_status": "UNCALIBRATED_CANDIDATES_ONLY",
            "identity_status": "UNRESOLVED",
            "pose_status": "NOT_ESTIMATED",
            "negative_observation_authorized": False,
            "archive_sequence_id": "test-video",
            "archive_media_time": index / 10,
        }
    )


def context(pixels, cutoff=3):
    return bootstrap_pixel_context(
        tuple(pixels), cutoff=NOW + timedelta(seconds=cutoff), source_snapshot_id=SNAPSHOT
    )


def generate(ctx, **kwargs):
    return generate_runtime_candidates(ctx, bootstrap_ledger_lineage_ref=LEDGER, **kwargs)


def posterior_context():
    # Explicitly synthetic native history; never used by the real-video command.
    ctx = context(
        [pixel(0, detected=False), pixel(1, delayed=1, detected=False), pixel(2, detected=False)]
    )
    root = next(
        t.candidate for t in generate(ctx).targets if t.candidate.events[0].kind == "unresolved"
    )
    parents, revisions = [], []
    for i, status in enumerate(["active", "active", "retracted"]):
        state = root.state.model_copy(
            update={
                "particle_id": UUID(int=200 + i),
                "revision_id": UUID(int=300 + i),
                "parent_particle_id": UUID(int=200) if i == 1 else None,
                "parent_revision_id": UUID(int=300) if i == 1 else None,
                "change_cause": ParticleChangeCause.HABIT,
                "regime_decision": ParticleRegimeDecision.STAY,
                "regime_id": f"old-{i}",
                "run_length": i,
            }
        )
        parent = FullHypothesis.model_validate({"state": state, "events": root.events})
        parents.append(parent)
        revisions.append(
            RevisionRecord(
                revision_id=state.revision_id,
                parent_revision_id=state.parent_revision_id,
                particle_id=state.particle_id,
                event_hypothesis_id=state.event_hypothesis_id,
                ledger_lineage_ref=state.ledger_lineage_ref,
                statistic_state_ref=state.statistic_state_ref,
                status=status,
            )
        )
    return ProposalContext.model_validate(
        {**ctx.model_dump(), "parents": parents, "revisions": revisions}
    )


def test_bootstrap_uses_all_boxes_unknowns_and_does_not_make_semantic_observations():
    ctx = context([pixel(0), pixel(1)])
    assert len(ctx.actor_support) == len(ctx.instance_support) == 2  # media clock association
    assert not ctx.visible.opportunities and not ctx.visible.detections
    generated = generate(ctx)
    assert len(generated.targets) == 8
    assert {t.operation.value for t in generated.targets} == {"preserve_unresolved"}
    assert {t.candidate.state.instance_association_key for t in generated.targets} == set(
        ctx.instance_support
    )
    assert not generated.report["analytic_updates_computed"]
    assert not generated.report["native_publication_authorized"]
    assert all(t.candidate.state.parent_particle_id is None for t in generated.targets)
    assert {r["record_id"] for r in generated.report["source_records"]} == {
        str(UUID(int=100)),
        str(UUID(int=101)),
    }
    assert {b.observation_id for b in ctx.pixel_identity_bindings} == {UUID(int=100), UUID(int=101)}


def test_pending_observation_changes_cannot_leak_into_support_or_input():
    arrived, future = pixel(0), pixel(1, delayed=10)
    altered = future.model_copy(update={"candidates": (), "input_sha256": "e" * 64})
    a = generate(context([arrived, future]))
    b = generate(context([arrived, altered]))
    assert a == b
    assert len(a.context.visible.pixel_observations) == 1
    later = generate(context([arrived, future], cutoff=12))
    assert later != a and later.report["delayed_evidence"]


def test_all_six_operations_and_full_contiguous_suffixes_are_generated_without_labels():
    ctx = posterior_context()
    before = ctx.model_dump_json()
    generated = generate(ctx)
    assert ctx.model_dump_json() == before
    assert set(generated.report["operation_counts"]) == {
        "branch",
        "revise",
        "retract",
        "reactivate",
        "rejuvenate",
        "preserve_unresolved",
    }
    assert {t.candidate.state.change_cause.value for t in generated.targets} == {
        "observation",
        "actor",
        "identity",
        "habit",
        "noise",
        "unresolved",
    }
    assert {t.candidate.state.regime_decision.value for t in generated.targets} == {
        "stay",
        "create",
        "reactivate",
        "unresolved",
    }
    assert any(t.replaced_revision_ids == (UUID(int=300), UUID(int=301)) for t in generated.targets)
    for t in generated.targets:
        if t.operation.value in {"retract", "reactivate"}:
            p = next(
                p
                for p in ctx.parents
                if p.state.particle_id == t.candidate.state.parent_particle_id
            )
            assert semantic_state(t.candidate) == semantic_state(p)
    d = TypedProposalDistribution(
        context=generated.context,
        runtime_candidates=generated.targets,
        scorer=lambda c, a, p, choices, **kw: torch.zeros(len(choices)),
    )
    mass = sum(torch.exp(d.factor_log_probabilities(k).sum()).item() for k in d.target_sha256s)
    assert mass == pytest.approx(1, abs=1e-12)


def test_finite_event_grammar_contains_repeated_handoffs_and_no_arbitrary_hop_cap():
    chains = event_grid(
        tuple(NOW + timedelta(seconds=i) for i in range(6)),
        ("a", "b", "unknown_actor"),
        ("unknown_location",),
    )
    assert any(sum(e["kind"] == "handoff" for e in chain) >= 2 for chain in chains)


@pytest.mark.parametrize("fault", ["empty", "overflow", "labels", "binding", "oracle"])
def test_invalid_sources_or_partial_support_cannot_be_published(fault):
    ctx = context([pixel(0)])
    if fault == "empty":
        ctx = context([])
    if fault == "labels":
        from test_typed_proposal_training import data

        ctx = data()[0]
    if fault == "binding":
        raw = ctx.model_dump()
        raw["pixel_identity_bindings"][0]["key"] = "forged-person"
        ctx = ProposalContext.model_construct(**raw)
    if fault == "oracle":
        raw = pixel(0).model_dump()
        raw["true_actor"] = "secret"
        with pytest.raises(ValueError):
            ProposalPixelObservation.model_validate(raw)
        return
    with pytest.raises(ValueError):
        generate(ctx, max_candidates=1 if fault == "overflow" else 4096)


def checkpoint(tmp_path, arm):
    with torch.random.fork_rng():
        torch.manual_seed(0)
        model = TypedProposalNetwork(arm)
    path = tmp_path / arm
    pin = save_checkpoint(model, {"track": "TEST_FIXTURE_UNTRAINED"}, path)
    return path, pin


@pytest.mark.parametrize("arm", ARMS)
def test_generated_session_late_evidence_recovery_idempotency_and_no_authority(arm, tmp_path):
    old = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        path, pin = checkpoint(tmp_path, arm)
        session = RuntimeCandidateSession(path, manifest_sha256=pin, seed=11)
        before = context([pixel(0), pixel(1, delayed=5)], cutoff=3)
        after = context([pixel(0), pixel(1, delayed=5)], cutoff=7)
        first = session.process(
            request_id="one", context=before, bootstrap_ledger_lineage_ref=LEDGER
        )
        blob = session.snapshot()
        assert first == session.process(
            request_id="one", context=before, bootstrap_ledger_lineage_ref=LEDGER
        )
        assert blob == session.snapshot()
        restored = RuntimeCandidateSession.restore(
            path,
            manifest_sha256=pin,
            snapshot=blob,
            snapshot_sha256=hashlib.sha256(blob).hexdigest(),
        )
        kwargs = dict(request_id="two", context=after, bootstrap_ledger_lineage_ref=LEDGER)
        second = session.process(**kwargs)
        assert second == restored.process(**kwargs)
        assert second.support != first.support
        assert (
            second.receipt.decoded.probability.root_context_sha256
            != first.receipt.decoded.probability.root_context_sha256
        )
        assert session.snapshot() == restored.snapshot()
        assert (
            not second.receipt.ledger_authorized
            and not second.receipt.native_publication_authorized
        )
        blob = session.snapshot()
        with pytest.raises(ValueError, match="changed"):
            session.process(request_id="one", context=after, bootstrap_ledger_lineage_ref=LEDGER)
        assert session.snapshot() == blob
    finally:
        torch.set_num_threads(old)


def test_fully_valid_rescored_subset_and_resealed_snapshot_rejected_by_regeneration(tmp_path):
    old = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        path, pin = checkpoint(tmp_path, ARMS[0])
        ctx = context([pixel(0)])
        session = RuntimeCandidateSession(path, manifest_sha256=pin, seed=11)
        result = session.process(request_id="one", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
        payload = json.loads(session.snapshot())
        # Complete alternate valid pipeline: change support, recompute all q,
        # sampled target and RNG with the real model; then reseal outer digest.
        subset = tuple(
            t for t in result.support.targets if t.candidate.events[0].kind == "unresolved"
        )
        engine = ProposalInferenceSession(path, manifest_sha256=pin, seed=11)
        engine.infer(request_id="one", context=ctx, support=subset)
        forged = engine.snapshot()
        ProposalInferenceSession.restore(
            path,
            manifest_sha256=pin,
            snapshot=forged,
            snapshot_sha256=hashlib.sha256(forged).hexdigest(),
        )
        payload["engine"] = json.loads(forged)
        forged = encoded(payload)
        with pytest.raises(ValueError, match="regenerated"):
            RuntimeCandidateSession.restore(
                path,
                manifest_sha256=pin,
                snapshot=forged,
                snapshot_sha256=hashlib.sha256(forged).hexdigest(),
            )
    finally:
        torch.set_num_threads(old)
