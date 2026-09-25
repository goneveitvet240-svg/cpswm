"""State-dependent suffix replay, source binding and all-three-block effects."""

from dataclasses import replace
from uuid import UUID

import numpy as np
import pytest

from cpswm.system.conditional_revision_replay import ConditionalReplayHistory, ConditionalReplayStep
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.structure_two_conditional_updates import ConditionalMeasurement
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState


def history():
    eye = tuple(tuple(float(i == j) for j in range(6)) for i in range(6))
    prior = ConditionalAnalyticState(
        (UUID(int=1), UUID(int=2)), (1.0, 1.0), ((1.0,),), (0.0,), eye, (0.0,) * 6
    )
    journal = ConditionalReplayHistory(prior, "a" * 64, "fixed-test-model")
    for i in range(3):
        measure = ConditionalMeasurement(
            UUID(int=10 + i),
            (UUID(int=20 + i),),
            "fixed-test-model",
            (1.0, 0.0),
            (1.0,),
            2.0,
            1.0,
            (float(i + 1),) * 6,
            eye,
            eye,
            1.0,
        )
        journal = journal.append(
            ConditionalReplayStep(
                UUID(int=100 + i),
                UUID(int=99 + i) if i else None,
                UUID(int=200 + i),
                "b" * 64,
                measure,
            )
        )
    return journal


class Recomputed:
    binding_sha256 = "a" * 64

    def __init__(self):
        self.calls = []

    def recompute(self, step, state):
        self.calls.append((step.particle_id, state.alpha))
        # Deliberately depends on the corrected prefix; retaining old suffix
        # values or subtracting one cached delta cannot produce this answer.
        return replace(
            step.measurement, rls_target=sum(state.alpha), measurement=(sum(state.alpha),) * 6
        )


def test_retraction_recomputes_suffix_and_matches_independent_three_block_calculation():
    j = history()
    model = Recomputed()
    result = j.replay(
        particle_id=UUID(int=102),
        revoked_revision_ids=frozenset({UUID(int=201)}),
        expected_history_sha256=j.content_sha256,
        model=model,
    )
    assert (
        result.state.alpha == (3.0, 1.0)
        and result.state.a == ((3.0,),)
        and result.state.b == (5.0,)
    )
    assert np.array_equal(result.state.information, 3 * np.eye(6))
    assert result.state.information_vector == (4.0,) * 6
    assert model.calls == [(UUID(int=102), (2.0, 1.0))]
    assert (
        len(result.measurements) == 2
        and not result.native_publication_authority
        and not result.ledger_write_authority
    )
    restored = StateCodec().loads(StateCodec().dumps(j))
    assert (
        restored.replay(
            particle_id=UUID(int=102),
            revoked_revision_ids=frozenset({UUID(int=201)}),
            expected_history_sha256=restored.content_sha256,
            model=Recomputed(),
        )
        == result
    )
    assert len(j.steps) == 3  # immutable history retains the original observation


@pytest.mark.parametrize(
    "attack",
    ["missing_model", "different_model", "source_substitution", "history_pin", "unknown_revision"],
)
def test_forged_or_incomplete_replay_cannot_return_a_state(attack):
    j = history()
    model = Recomputed()
    pin = j.content_sha256
    revoked = frozenset({UUID(int=201)})
    if attack == "missing_model":
        model = None
    if attack == "different_model":
        model.binding_sha256 = "c" * 64
    if attack == "source_substitution":
        model.recompute = lambda step, state: replace(
            step.measurement, source_record_ids=(UUID(int=999),)
        )
    if attack == "history_pin":
        pin = "0" * 64
    if attack == "unknown_revision":
        revoked = frozenset({UUID(int=999)})
    with pytest.raises(ValueError):
        j.replay(
            particle_id=UUID(int=102),
            revoked_revision_ids=revoked,
            expected_history_sha256=pin,
            model=model,
        )


def test_fork_replays_only_its_ancestry_and_duplicate_identity_cannot_change_measurement():
    j = history()
    root = j.steps[0]
    fork = replace(
        j.steps[2],
        particle_id=UUID(int=110),
        parent_particle_id=root.particle_id,
        revision_id=UUID(int=210),
    )
    j = j.append(fork)
    result = j.replay(
        particle_id=fork.particle_id,
        revoked_revision_ids=frozenset({UUID(int=201)}),
        expected_history_sha256=j.content_sha256,
        model=None,
    )
    assert not result.removed_revisions and len(result.measurements) == 2
    with pytest.raises(ValueError, match="reused"):
        j.append(replace(fork, measurement=replace(fork.measurement, rls_target=99.0)))
