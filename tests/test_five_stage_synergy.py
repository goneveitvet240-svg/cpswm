import copy
import math

import pytest
from run_research_pilot import enumerate_update
from run_short_history_reference import fixed_inputs
from synergy_runtime import PosteriorParentRuntime, parent_proposal

from cpswm.system.evaluation_operations.structure_two_current_event import CurrentEventRuntime
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm


def test_parent_proposal_retains_underflow_support_and_rejects_invalid_mass():
    support = (("a", 1e-300), ("b", 1.0))
    for prior in (0.0, 1e-300, 0.2, 1.0):
        q = parent_proposal(support, prior)
        assert all(math.isfinite(v) and v > 1e-300 for _, v in q)
        assert [k for k, _ in q] == ["a", "b"]
    for prior in (-1, math.inf, math.nan):
        with pytest.raises(ValueError):
            parent_proposal(support, prior)


def test_actual_global_proposal_changes_parent_allocation_without_target_change():
    _, config, model, observations, _ = fixed_inputs()[0]
    original = CurrentEventRuntime(
        arm=FullJointArm.STATEFUL_FULL_JOINT, config=config, neural_model=model
    )
    variant = PosteriorParentRuntime(arm=original.arm, config=config, neural_model=model)
    for runtime in (original, variant):
        runtime.revise(copy.deepcopy(observations[0]))
    assert original.particles == variant.particles
    original.step_index += 1
    variant.step_index += 1
    ea, la, qa, pa = enumerate_update(original, observations[1])
    eb, lb, qb, pb = enumerate_update(variant, observations[1])
    assert [(p.world.signature, c.key) for p, c in ea] == [
        (p.world.signature, c.key) for p, c in eb
    ]
    assert la == lb and pa == pb and qa != qb
    assert sum(qb) == pytest.approx(1)
    assert min(qb) > 1e-300
    # Enumerated importance numerator exactly recovers the same target under q.
    target = [math.exp(logp - max(lb)) for logp in lb]
    recovered = [q * math.exp(logp - math.log(q) - max(lb)) for q, logp in zip(qb, lb, strict=True)]
    assert recovered == pytest.approx(target)
    variant.step_index -= 1
    variant.revise(copy.deepcopy(observations[1]))
    variant.verify_internal_contracts()
    draw = variant.sampling_receipts[-1]
    assert variant.fairness_receipts[-1].target_score_evaluations == 24
    assert draw["support_size"] == len(eb)
    # Each receipt denominator is the actual normalized q of its sampled path.
    lookup = {(p.world.typed_state.particle_id, c.key): q for (p, c), q in zip(eb, qb, strict=True)}
    from run_short_history_reference import candidate_key_from_world

    for particle, receipt in zip(
        variant.particles, variant.importance_revision_receipts[-1], strict=True
    ):
        key = (receipt.proposal.source_particle_id, candidate_key_from_world(particle.world))
        assert receipt.proposal.proposal_log_probability == pytest.approx(math.log(lookup[key]))
