"""Second review: complete cached-graph corruption and loaded-method replacement."""

import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_full_support_compute import paired  # noqa: E402
from test_proposal_execution_derivation import artifacts  # noqa: E402
from test_runtime_candidates import LEDGER, context, pixel  # noqa: E402
from test_typed_proposal_training import data  # noqa: E402

from cpswm.data_preflight.proposal_samples import export_context  # noqa: E402
from cpswm.data_preflight.proposal_trainer import save_checkpoint  # noqa: E402
from cpswm.data_preflight.runtime_candidate_session import RuntimeCandidateSession  # noqa: E402
from cpswm.data_preflight.typed_proposal_networks import ARMS, TypedProposalNetwork  # noqa: E402


@pytest.fixture(autouse=True)
def two_threads():
    old = torch.get_num_threads()
    torch.set_num_threads(2)
    yield
    torch.set_num_threads(old)


@pytest.mark.parametrize("field", ("memory", "vectors", "cached_key", "cached_value"))
def test_complete_cached_graph_data_mutation_is_not_a_valid_same_input_score(field):
    sample, support = data()
    _, model = paired(ARMS[0])
    with torch.no_grad():
        prepared = model.prepare(sample.runtime_context(), support)
        targets = {
            "memory": prepared.memory,
            "vectors": prepared.vectors,
            "cached_key": prepared.choice_key_value[0],
            "cached_value": prepared.choice_key_value[1],
        }
        tensor = targets[field]
        original = tensor.clone()
        tensor.data.add_(17.25)  # Does not increment the version counter.
        try:
            with pytest.raises(ValueError, match=r"prepared|cache|graph"):
                prepared(
                    export_context(sample.runtime_context()),
                    "operation",
                    (),
                    tuple(sorted({t.operation.value for t in support})),
                    runtime_candidates=support,
                )
        finally:
            tensor.data.copy_(original)
        prepared(
            export_context(sample.runtime_context()),
            "operation",
            (),
            tuple(sorted({t.operation.value for t in support})),
            runtime_candidates=support,
        )


@pytest.mark.parametrize("attack", ("hook", "loaded_method"))
def test_valid_session_cannot_be_continued_after_complete_runtime_implementation_swap(
    tmp_path, attack
):
    _, _, path, pin = artifacts(tmp_path)
    session = RuntimeCandidateSession(path, manifest_sha256=pin, seed=11)
    ctx = context([pixel(0)])
    session.process(request_id="first", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
    before = session.snapshot()
    layer = session._engine._model.encoder.layers[0].norm1
    original = torch.nn.LayerNorm.forward.__code__
    handle = None
    try:
        if attack == "hook":
            handle = layer.register_forward_hook(lambda module, args, result: result + 10)
        else:

            def forged(self, value):
                return value + 10

            torch.nn.LayerNorm.forward.__code__ = forged.__code__
        with pytest.raises(ValueError, match=r"binding|structure|architecture"):
            session.process(request_id="next", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)
    finally:
        if handle is not None:
            handle.remove()
        torch.nn.LayerNorm.forward.__code__ = original
    assert session.snapshot() == before
    session.process(request_id="next", context=ctx, bootstrap_ledger_lineage_ref=LEDGER)


def test_mutated_dense_architecture_cannot_be_exported_as_original_configuration(tmp_path):
    model = TypedProposalNetwork(ARMS[0])
    model.encoder.layers[0].norm1.eps = 0.7
    with pytest.raises(ValueError, match=r"structure|architecture"):
        save_checkpoint(model, {"track": "TEST_FIXTURE_UNTRAINED"}, tmp_path / "forged")
    assert not (tmp_path / "forged").exists()
