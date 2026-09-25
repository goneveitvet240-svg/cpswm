"""Real three-block computation on explicit model fixtures, never natural truth."""

from dataclasses import replace
from uuid import UUID

import numpy as np
import pytest
from test_runtime_candidates import context, generate, pixel, posterior_context

from cpswm.data_preflight.proposal_samples import ProposalContext
from cpswm.system.conditioned_proposal_runtime import (
    condition_generated_support,
    evidence_group,
    verify_conditioned_support,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_conditional_updates import (
    ConditionalMeasurement,
    rebuild_conditional_state,
)
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState

LEDGER = "hybrid-ledger:" + "a" * 64
EYE = tuple(tuple(float(i == j) for j in range(6)) for i in range(6))


def prior():
    return ConditionalAnalyticState(
        (UUID(int=11), UUID(int=12)),
        (1.0, 1.0),
        ((1.0, 0.0), (0.0, 1.0)),
        (0.0, 0.0),
        EYE,
        (0.0,) * 6,
    )


class FixtureModel:
    binding_sha256 = content_sha256("explicit-state-dependent-conditional-fixture@1")
    observation_model_id = "conditional-fixture-not-calibrated"

    def __init__(self):
        self.calls = 0
        self.attack = None

    def checkpoint_state(self):
        return {"calls": self.calls}

    def restore_state(self, state):
        self.calls = state["calls"]

    def measure(self, ctx, target, group, state):
        self.calls += 1
        if self.attack == "raise" and self.calls == 2:
            raise RuntimeError("measurement interrupted")
        # These are declared test equations, not pixel-to-world geometry.
        y = sum(state.alpha) + (target.candidate.events[-1].kind == "no_move")
        result = ConditionalMeasurement(
            group.evidence_cluster_id,
            group.source_record_ids,
            self.observation_model_id,
            (1.0, 0.5),
            (1.0, 0.5),
            y,
            0.75,
            (y,) * 6,
            EYE,
            EYE,
            0.25,
        )
        if self.attack == "cluster":
            result = replace(result, evidence_cluster_id=UUID(int=999))
        if self.attack == "source":
            result = replace(result, source_record_ids=(UUID(int=999),))
        if self.attack == "model":
            result = replace(result, observation_model_id="other")
        if self.attack == "covariance":
            result = replace(result, noise_covariance=((0.0,),))
        return result


def inputs(ctx=None):
    if ctx is None:
        ctx = context([pixel(0), pixel(1, delayed=1)])
    model = FixtureModel()
    groups = tuple(
        evidence_group(ctx, UUID(int=2000 + i), (p.observation_id,))
        for i, p in enumerate(ctx.visible.pixel_observations)
    )
    return generate(ctx), {
        "bootstrap_ledger_lineage_ref": LEDGER,
        "groups": groups,
        "prior": prior(),
        "parent_statistics": {},
        "model": model,
        "expected_model_binding_sha256": model.binding_sha256,
    }


def bound_posterior():
    raw = posterior_context().model_dump()
    statistics = {}
    for parent, revision in zip(raw["parents"], raw["revisions"], strict=True):
        state = prior()
        parent["state"]["statistic_state_ref"] = state.reference
        revision["statistic_state_ref"] = state.reference
        statistics[parent["state"]["particle_id"]] = state
    return ProposalContext.model_validate(raw), statistics


def test_all_three_blocks_are_recomputed_and_original_scored_targets_stay_unchanged():
    generated, kwargs = inputs()
    original = generated
    result = condition_generated_support(generated, **kwargs)
    assert generated == original and len(result.candidates) == 8
    assert kwargs["model"].calls == 0
    assert not result.ledger_write_authority and not result.native_publication_authority
    assert not result.empirical_calibration_certified
    for item in result.candidates:
        assert item.origin in generated.targets
        assert item.origin.candidate.state.statistic_state_ref.startswith("pending-conditional:")
        assert item.resolved_hypothesis.state.statistic_state_ref == item.statistics.reference
        assert item.resolved_hypothesis.events == item.origin.candidate.events
        offset = item.origin.candidate.events[-1].kind == "no_move"
        total_y = 2 + offset + 3.5 + offset
        assert item.statistics.alpha == (3.0, 2.0)
        assert np.array_equal(item.statistics.a, np.eye(2) + 1.5 * np.outer([1, 0.5], [1, 0.5]))
        assert np.array_equal(item.statistics.b, 0.75 * total_y * np.array([1, 0.5]))
        assert np.array_equal(item.statistics.information, 1.5 * np.eye(6))
        assert item.statistics.information_vector == (0.25 * total_y,) * 6
        assert len(item.measurements) == 2
        assert item.scored_target_sha256 == content_sha256(item.origin.model_dump(mode="json"))


def test_six_operations_keep_full_raw_history_and_retraction_preserves_parent():
    ctx, parents = bound_posterior()
    generated, kwargs = inputs(ctx)
    kwargs["parent_statistics"] = parents
    result = condition_generated_support(generated, **kwargs)
    assert len(result.candidates) == 303
    assert len({item.origin.operation for item in result.candidates}) == 6
    for item in result.candidates:
        if item.origin.operation.value == "retract":
            assert item.statistics == parents[item.origin.candidate.state.parent_particle_id]
            assert not item.measurements
        else:
            assert len(item.measurements) == 3
            assert item.statistics.evidence_cluster_ids == tuple(
                g.evidence_cluster_id for g in result.groups
            )
        if item.origin.operation.value == "rejuvenate":
            # A replaced latent suffix is not permission to delete raw observations.
            assert item.origin.replaced_revision_ids and item.origin.replay_required
            assert item.evaluation_mode == "full_history_replay_no_observation_removed"


@pytest.mark.parametrize("fault", ["cluster", "source", "model", "covariance", "raise"])
def test_bad_measurements_or_interruption_restore_model_and_do_not_return_partial_support(fault):
    generated, kwargs = inputs()
    kwargs["model"].attack = fault
    with pytest.raises((ValueError, RuntimeError)):
        condition_generated_support(generated, **kwargs)
    assert kwargs["model"].calls == 0
    kwargs["model"].attack = None
    expected = condition_generated_support(generated, **kwargs)
    assert verify_conditioned_support(expected, generated, **kwargs) == expected


@pytest.mark.parametrize("fault", ["missing", "duplicate", "content", "future", "parent"])
def test_source_partition_and_parent_binding_are_enforced(fault):
    generated, kwargs = inputs()
    if fault == "missing":
        kwargs["groups"] = kwargs["groups"][:1]
    if fault == "duplicate":
        kwargs["groups"] = (*kwargs["groups"], kwargs["groups"][0])
    if fault == "content":
        kwargs["groups"] = (
            kwargs["groups"][0].model_copy(update={"source_sha256": "0" * 64}),
            kwargs["groups"][1],
        )
    if fault == "future":
        with pytest.raises(ValueError, match="arrived"):
            evidence_group(generated.context, UUID(int=3), (UUID(int=999),))
        return
    if fault == "parent":
        kwargs["parent_statistics"] = {UUID(int=999): prior()}
    with pytest.raises(ValueError):
        condition_generated_support(generated, **kwargs)
    assert kwargs["model"].calls == 0


def test_complete_resealed_false_statistics_fail_actual_model_replay():
    generated, kwargs = inputs()
    real = condition_generated_support(generated, **kwargs)
    row = real.candidates[0]
    changed = replace(row.measurements[0], location_mass=(10.0, 0.0))
    measures = (changed, *row.measurements[1:])
    state = rebuild_conditional_state(real.prior, measures)
    hypothesis = row.resolved_hypothesis.model_copy(
        update={
            "state": row.resolved_hypothesis.state.model_copy(
                update={"statistic_state_ref": state.reference}
            )
        }
    )
    forged = replace(
        real,
        candidates=(
            replace(
                row,
                statistics=state,
                measurements=measures,
                resolved_hypothesis_json=hypothesis.model_dump_json(),
            ),
            *real.candidates[1:],
        ),
    )
    assert forged.content_sha256 != real.content_sha256
    assert (
        forged.candidates[0].statistics.reference
        == forged.candidates[0].resolved_hypothesis.state.statistic_state_ref
    )
    with pytest.raises(ValueError, match="full model replay"):
        verify_conditioned_support(forged, generated, **kwargs)
    assert kwargs["model"].calls == 0
