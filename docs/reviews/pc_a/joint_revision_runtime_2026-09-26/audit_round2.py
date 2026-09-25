"""Second local adversarial review after the four first-round fixes."""

import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_conditioned_inference_session import restore, setup  # noqa: E402
from test_conditioned_proposal_runtime import FixtureModel, prior  # noqa: E402
from test_runtime_candidates import ARMS, LEDGER, context, pixel  # noqa: E402

from cpswm.system.conditioned_inference_session import ConditionedInferenceSession  # noqa: E402
from cpswm.system.conditioned_proposal_runtime import evidence_group  # noqa: E402


@pytest.fixture(autouse=True)
def threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(previous)


def test_concurrent_duplicate_requests_only_advance_one_actual_sampling_transaction(tmp_path):
    session, path, pin, _, args = setup(tmp_path, ARMS[0])
    before = session.snapshot()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: session.process(**args), range(3)))
    assert results[0] == results[1] == results[2]
    single = restore(path, pin, before)
    assert single.process(**args) == results[0]
    assert single.snapshot() == session.snapshot()
    args["request_id"] = "after-concurrency"
    assert single.process(**args) == session.process(**args)


def test_reentrant_snapshot_cannot_expose_neural_but_unconditioned_half_transaction(tmp_path):
    session, _, _, model, args = setup(tmp_path, ARMS[0])
    original = model.measure
    denied = []

    def measure(*values):
        with pytest.raises(RuntimeError, match="reentrant"):
            session.snapshot()
        denied.append(True)
        return original(*values)

    model.measure = measure
    assert session.process(**args).selected.statistics.reference
    assert len(denied) == 16
    assert session.snapshot()


def test_numeric_failure_after_sampling_restores_exact_future_behavior(tmp_path):
    session, path, pin, model, args = setup(tmp_path, ARMS[0])
    before = session.snapshot()
    original = model.measure
    model.measure = lambda *values: replace(original(*values), rls_features=(1e308, 1e308))
    with pytest.raises(ValueError):
        session.process(**args)
    assert session.snapshot() == before
    model.measure = original
    recovered = restore(path, pin, before)
    assert session.process(**args) == recovered.process(**args)


@pytest.mark.parametrize("fault", ["prior", "model_pin", "external_snapshot_pin"])
def test_external_dependency_pins_reject_resealed_or_switched_inputs(tmp_path, fault):
    session, path, pin, _, args = setup(tmp_path, ARMS[0])
    session.process(**args)
    blob = session.snapshot()
    model = FixtureModel()
    initial = prior()
    digest = hashlib.sha256(blob).hexdigest()
    model_pin = model.binding_sha256
    if fault == "prior":
        initial = replace(initial, alpha=(2.0, 2.0))
    elif fault == "model_pin":
        model_pin = "b" * 64
        model.binding_sha256 = model_pin
    else:
        digest = "0" * 64
    with pytest.raises(ValueError):
        ConditionedInferenceSession.restore(
            path,
            manifest_sha256=pin,
            snapshot=blob,
            snapshot_sha256=digest,
            prior=initial,
            model=model,
            expected_model_binding_sha256=model_pin,
        )
    assert session.snapshot() == blob


def test_late_evidence_recomputes_the_same_complete_state_as_fresh_history(tmp_path):
    session, path, pin, _, _ = setup(tmp_path, ARMS[0])
    before_ctx = context([pixel(0), pixel(1, delayed=5)], cutoff=3)
    after_ctx = context([pixel(0), pixel(1, delayed=5)], cutoff=7)

    def args(ctx, request):
        return dict(
            request_id=request,
            context=ctx,
            bootstrap_ledger_lineage_ref=LEDGER,
            groups=tuple(
                evidence_group(ctx, p.observation_id, (p.observation_id,))
                for p in ctx.visible.pixel_observations
            ),
            parent_statistics={},
        )

    before = session.process(**args(before_ctx, "before"))
    snapshot = session.snapshot()
    recovered = restore(path, pin, snapshot)
    after = session.process(**args(after_ctx, "after"))
    assert after == recovered.process(**args(after_ctx, "after"))
    fresh = ConditionedInferenceSession(
        path,
        manifest_sha256=pin,
        seed=11,
        prior=prior(),
        model=FixtureModel(),
        expected_model_binding_sha256=FixtureModel.binding_sha256,
    )
    assert after.conditioned == fresh.process(**args(after_ctx, "fresh")).conditioned
    assert {row.statistics.alpha for row in before.conditioned.candidates} == {(2.0, 1.5)}
    assert {row.statistics.alpha for row in after.conditioned.candidates} == {(3.0, 2.0)}
    assert session.snapshot() == recovered.snapshot()
