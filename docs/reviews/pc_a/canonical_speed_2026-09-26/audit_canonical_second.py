"""Adversarial type precedence and real six-operation inference equivalence."""

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tests"))
from test_canonical_fast_path import NumberEnum, reference  # noqa: E402
from test_proposal_inference_session import resume, setup  # noqa: E402

from cpswm.data_preflight.proposal_inference_session import ProposalInferenceSession  # noqa: E402
from cpswm.data_preflight.typed_proposal_networks import ARMS  # noqa: E402
from cpswm.system import reproducibility  # noqa: E402


@dataclass
class DataclassString(str):
    evidence: int


class FloatSubclass(float):
    pass


def test_scalar_subclasses_do_not_bypass_old_dataclass_enum_or_zero_rules():
    value = DataclassString(17)
    assert reproducibility.canonical_json(value) == reference.canonical_json(value)
    assert reproducibility.canonical_json(value) == '{"evidence":17}'
    assert reproducibility.canonical_json(NumberEnum.VALUE) == "-0.0"
    assert reproducibility.canonical_json(-0.0) == "0.0"
    assert reproducibility.canonical_json(FloatSubclass(-0.0)) == "0.0"
    value.evidence = 18
    assert reproducibility.content_sha256(value) == reference.content_sha256(value)
    assert reproducibility.canonical_json(value) == '{"evidence":18}'


def test_cause_sets_keep_identity_across_independent_hash_seed_processes():
    script = (
        "from cpswm.system.reproducibility import canonical_json; "
        "from uuid import UUID; "
        "print(canonical_json({'cause': {'a','b',UUID(int=3),-0.0}, "
        "'nested': frozenset({('人物',1),('物体',2)})}))"
    )
    outputs = [
        subprocess.check_output(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        for seed in ("0", "1", "8675309")
    ]
    assert len(set(outputs)) == 1


@pytest.mark.parametrize("arm", ARMS)
def test_complete_six_operator_distribution_sampling_and_recovery_equal_reference(
    tmp_path, monkeypatch, arm
):
    torch.set_num_threads(2)
    checkpoint, pin, current, sample, support = setup(tmp_path, arm)
    context = sample.runtime_context()
    start = current.snapshot()
    scores = current.score_support(context=context, support=support)
    assert current.snapshot() == start
    assert len({x.target.operation for x in scores}) == 6
    first = current.infer(request_id="first", context=context, support=support)
    snapshot = current.snapshot()
    restored = resume(checkpoint, pin, snapshot)
    second = current.infer(request_id="second", context=context, support=support)
    assert second == restored.infer(request_id="second", context=context, support=support)
    final = current.snapshot()
    with monkeypatch.context() as patch:
        patch.setattr(reproducibility, "_canonical_value", reference._canonical_value)
        original = ProposalInferenceSession(checkpoint, manifest_sha256=pin, seed=11)
        assert original.snapshot() == start
        assert original.score_support(context=context, support=tuple(reversed(support))) == scores
        assert original.infer(request_id="first", context=context, support=support) == first
        assert original.snapshot() == snapshot
        assert original.infer(request_id="second", context=context, support=support) == second
        assert original.snapshot() == final
        assert hashlib.sha256(original.snapshot()).digest() == hashlib.sha256(final).digest()
    assert not first.ledger_authorized and not first.native_publication_authorized
