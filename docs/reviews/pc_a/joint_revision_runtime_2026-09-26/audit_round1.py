"""First-round probes; run against fc3537d before fixes, preserve failures."""

import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_conditioned_inference_session import restore, setup  # noqa: E402
from test_conditioned_proposal_runtime import (  # noqa: E402
    FixtureModel,
    bound_posterior,
    inputs,
    prior,
)
from test_runtime_candidates import ARMS, LEDGER, checkpoint  # noqa: E402

from cpswm.data_preflight.proposal_samples import ProposalContext  # noqa: E402
from cpswm.system.conditioned_inference_session import ConditionedInferenceSession  # noqa: E402


@pytest.fixture(autouse=True)
def threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(previous)


def test_between_request_model_identity_change_cannot_silently_bind_new_observation_model(tmp_path):
    session, _, _, model, args = setup(tmp_path, ARMS[0])
    before = session.snapshot()
    model.observation_model_id = "changed-model-under-old-artifact"
    try:
        with pytest.raises(ValueError, match="model"):
            session.process(**args)
    finally:
        del model.observation_model_id
    assert session.snapshot() == before


def test_reentrant_success_then_outer_failure_cannot_leave_an_orphan_journal(tmp_path):
    class Reentrant(FixtureModel):
        def checkpoint_state(self):
            return {}

        def restore_state(self, state):
            pass

        def measure(self, ctx, target, group, state):
            if not self.triggered:
                self.triggered = True
                self.session.process(**{**self.args, "request_id": "nested"})
                raise RuntimeError("outer interrupted after nested success")
            return super().measure(ctx, target, group, state)

    path, pin = checkpoint(tmp_path, ARMS[0])
    model = Reentrant()
    model.triggered = False
    session = ConditionedInferenceSession(
        path,
        manifest_sha256=pin,
        seed=11,
        prior=prior(),
        model=model,
        expected_model_binding_sha256=model.binding_sha256,
    )
    generated, kwargs = inputs()
    args = dict(
        request_id="outer",
        context=generated.context,
        bootstrap_ledger_lineage_ref=LEDGER,
        groups=kwargs["groups"],
        parent_statistics={},
    )
    model.session, model.args = session, args
    before = session.snapshot()
    with pytest.raises(RuntimeError):
        session.process(**args)
    assert session.snapshot() == before
    model.triggered = True
    assert session.process(**args).conditioned.candidates


def test_legal_full_parent_history_with_shared_immutable_values_restores(tmp_path):
    path, pin = checkpoint(tmp_path, ARMS[0])
    ctx, parents = bound_posterior()
    raw = ctx.model_dump()
    raw["parents"] = [raw["parents"][0], raw["parents"][2]]
    raw["revisions"] = [raw["revisions"][0], raw["revisions"][2]]
    raw["visible"]["pixel_observations"] = raw["visible"]["pixel_observations"][:2]
    ctx = ProposalContext.model_validate(raw)
    parents = {
        key: value
        for key, value in parents.items()
        if key in {p.state.particle_id for p in ctx.parents}
    }
    _generated, kwargs = inputs(ctx)
    session = ConditionedInferenceSession(
        path,
        manifest_sha256=pin,
        seed=11,
        prior=prior(),
        model=FixtureModel(),
        expected_model_binding_sha256=FixtureModel.binding_sha256,
    )
    result = session.process(
        request_id="parents",
        context=ctx,
        bootstrap_ledger_lineage_ref=LEDGER,
        groups=kwargs["groups"],
        parent_statistics=parents,
    )
    assert len(result.conditioned.candidates) == 88
    blob = session.snapshot()
    recovered = restore(path, pin, blob)
    assert recovered.snapshot() == blob


def test_failed_checkpoint_rollback_must_stop_the_damaged_live_session(tmp_path):
    session, path, pin, model, args = setup(tmp_path, ARMS[0])
    before = session.snapshot()
    weights = path / "weights.pt"
    authentic = weights.read_bytes()
    model.attack = "source"
    weights.write_bytes(authentic + b"changed-during-transaction")
    try:
        with pytest.raises((ValueError, RuntimeError)):
            session.process(**args)
        with pytest.raises(RuntimeError, match=r"recover|rollback"):
            session.snapshot()
    finally:
        weights.write_bytes(authentic)
        model.attack = None
    recovered = restore(path, pin, before)
    assert recovered.process(**args).selected.statistics.reference
