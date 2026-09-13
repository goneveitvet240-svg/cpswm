"""R6 independent Decimal/Fraction arithmetic and public transaction boundaries.

No production method replacements and no private authorization enrollment.
Prepared likelihood terms remain explicit caller input, not calibrated defaults.
"""

import math
import sys
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
from uuid import uuid4

import pytest
import test_structure_two_formal_revision_lineage as old
from test_structure_two_w3_native_particles import candidates
from test_structure_two_w3_round5_boundaries import direct_outcome, state

from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleRevisionReceipt,
    normalize_particle_revisions,
)
from cpswm.system.reproducibility import content_sha256


def reseal(args, *, alpha=None, locations=None, **updates):
    args = deepcopy(args)
    receipt = args["receipts"][0]
    raw = receipt.model_dump()
    pid = receipt.proposal.proposed_state.particle_id
    if alpha is not None or locations is not None:
        analytic = args["statistics"][pid]
        analytic = replace(
            analytic,
            alpha=analytic.alpha if alpha is None else alpha,
            locations=analytic.locations if locations is None else locations,
        )
        args["statistics"][pid] = analytic
        raw["proposal"]["proposed_state"]["statistic_state_ref"] = analytic.reference
    for key, value in updates.items():
        if key in raw:
            raw[key] = value
        else:
            raw["proposal"][key] = value
    args["receipts"] = (ParticleRevisionReceipt.model_validate(raw), args["receipts"][1])
    return args


def snapshot(probe):
    core = probe.system.core
    instances = probe.system._runtime_operator_instances_for_execution()
    return (
        state(core),
        content_sha256(core._hybrid_loop.ledger.export_state()),
        core.action_location_distribution(core.current_snapshot),
        {k: tuple(id(x) for x in v) for k, v in instances.items()},
        id(core._particle_workspace),
    )


def reject_retry(probe, args, *, match=None, good=None):
    core = probe.system.core
    before = snapshot(probe)
    with pytest.raises(ValueError, match=match):
        core.stage_prepared_particle_candidates(**args)
    assert snapshot(probe) == before
    good = candidates(core) if good is None else good
    batch = core.stage_prepared_particle_candidates(**good)
    assert any(w.posterior_probability > 0 for w in batch.particle_weights)
    after = snapshot(probe)
    assert core.stage_prepared_particle_candidates(**good) == batch
    assert snapshot(probe) == after
    probabilities, unresolved = core.prepared_particle_location_marginal()
    assert math.fsum((*probabilities.values(), unresolved)) == pytest.approx(1)
    assert unresolved > 0
    return batch


@pytest.mark.parametrize("source", ["random", "current", "other_run", "other_object", "revoked"])
@pytest.mark.parametrize(
    "mode", ["posterior_projection_not_likelihood", "raw_observation_likelihood"]
)
def test_posterior_authority_is_not_an_identity_string(source, mode):
    probe = old._legacy_history(1)
    core = probe.system.core
    source_id = uuid4()
    if source == "current":
        source_id = core.current_snapshot.snapshot_id
    elif source in {"other_run", "other_object"}:
        other_probe = old.BackboneWiringProbe.build(seed=8 if source == "other_object" else 7)
        other = other_probe.system.core
        other.process_transition(other_probe.transition_for(other_probe.observed_days()[0]))
        # A real posterior from a different runtime/object is still not a
        # registered native projection capability. Use its actual object ref.
        source_id = other.current_snapshot.snapshot_id
        if source == "other_object":
            assert other.object_instance_id != core.object_instance_id
    elif source == "revoked":
        source_id = core.current_snapshot.snapshot_id
        core.apply_event_revision_outcome(direct_outcome(core, next(iter(core._committed_events))))
        core.process_transition(probe.transition_for(probe.observed_days()[1]))
    args = reseal(
        candidates(core),
        evidence_semantics=mode,
        source_posterior_snapshot_id=source_id,
        posterior_projection_log_factor=10.0 if mode.startswith("posterior") else 0.0,
    )
    reject_retry(probe, args, match="posterior")


@pytest.mark.parametrize("fault", ["foreign", "mixed", "subset", "duplicate"])
@pytest.mark.parametrize("step", [0, 1])
def test_fully_resealed_support_attacks_roll_back_and_retry(fault, step):
    probe = old._legacy_history(1)
    core = probe.system.core
    if step:
        core.stage_prepared_particle_candidates(**candidates(core))
    good = candidates(core, step=step)
    locs = core.locations
    altered = {
        "foreign": tuple(uuid4() for _ in locs),
        "mixed": (uuid4(), *locs[1:]),
        "subset": locs[:2],
        "duplicate": (locs[0], *locs[:-1]),
    }[fault]
    if fault == "duplicate":
        args = deepcopy(good)
        pid = args["receipts"][0].proposal.proposed_state.particle_id
        analytic = args["statistics"][pid]
        # Bypass the dataclass constructor, reseal its content, then exercise
        # the actual public boundary's reconstruction validation.
        object.__setattr__(analytic, "locations", altered)
        raw = args["receipts"][0].model_dump()
        raw["proposal"]["proposed_state"]["statistic_state_ref"] = analytic.reference
        args["receipts"] = (ParticleRevisionReceipt.model_validate(raw), args["receipts"][1])
    else:
        args = reseal(good, locations=altered, alpha=(1.0,) * len(altered))
    reject_retry(probe, args, match="support|location", good=good)


@pytest.mark.parametrize(
    "alpha",
    [
        (1e308,) * 4,
        (5e-324,) * 4,
        (0.0,) * 4,
        (1e308, 1e-308, 0.0, 5e-324),
        (1.0, 2.0, 3.0, 4.0),
        (1e307, 2e307, 3e307, 4e307),
        (1e-300, 2e-300, 3e-300, 4e-300),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
def test_stable_alpha_matches_exact_binary_rational_reference(alpha, reverse):
    probe = old._legacy_history(1)
    core = probe.system.core
    locations = core.locations
    args = reseal(
        candidates(core),
        alpha=alpha[::-1] if reverse else alpha,
        locations=locations[::-1] if reverse else locations,
    )
    before = snapshot(probe)
    batch = core.stage_prepared_particle_candidates(**args)
    probability, unresolved = core.prepared_particle_location_marginal()
    known = batch.particle_weights[0].posterior_probability
    total = sum(map(Fraction, alpha), Fraction())
    for location, value in zip(locations, alpha, strict=True):
        expected = float(Fraction(value) / total * Fraction(known)) if total else 0.0
        assert probability.get(location, 0.0) == pytest.approx(expected, rel=2e-15, abs=5e-324)
    assert unresolved == pytest.approx(1.0 - known if total else 1.0)
    assert math.fsum((*probability.values(), unresolved)) == pytest.approx(1.0)
    assert snapshot(probe)[1:] == before[1:]
    after = snapshot(probe)
    core.stage_prepared_particle_candidates(**args)
    assert snapshot(probe) == after


def decimal_reference(receipts, unresolved):
    # Independent high precision summation/exp, never production log weight.
    with localcontext() as context:
        context.prec = 1100
        values = []
        for receipt in receipts:
            if not receipt.accepted:
                values.append(None)
                continue
            terms = (
                receipt.prior_log_weight,
                receipt.transition_log_probability,
                receipt.observation_log_likelihood,
                receipt.posterior_projection_log_factor,
                *(c.log_potential for c in receipt.constraints),
                -receipt.proposal.proposal_log_probability,
            )
            values.append(sum((Decimal.from_float(x) for x in terms), Decimal(0)))
        values.append(Decimal.from_float(unresolved))
        maximum = max(v for v in values if v is not None)
        masses = [
            Decimal(0) if v is None or v - maximum < -1000 else (v - maximum).exp() for v in values
        ]
        total = sum(masses)
        return [float(m / total) for m in masses]


@pytest.mark.parametrize(
    "obs,q,transition,unresolved",
    [
        (0.0, -1e308, -1e308, 0.0),  # exact cancellation retains the unit-scale prior terms
        (1e308, -1e308, -1e308, 1e308),  # naive intermediate overflow, finite total
        (-1e308, -1e308, 0.0, 0.0),
        (700.0, -1.0, -700.0, 0.0),
        (-700.0, -1.0, 0.0, 0.0),
        (1e-300, -1e-300, -1e-300, 0.0),
        (0.0, 0.0, 0.0, -1e308),
    ],
)
@pytest.mark.parametrize("rejected", [False, True])
def test_weights_match_independent_decimal_reference(obs, q, transition, unresolved, rejected):
    core = old._legacy_history(1).system.core
    args = reseal(
        candidates(core),
        observation_log_likelihood=obs,
        proposal_log_probability=q,
        transition_log_probability=transition,
    )
    if rejected:
        raw = args["receipts"][0].model_dump()
        raw["constraints"][0].update(accepted=False, rejection_reason="physical counterexample")
        args["receipts"] = (ParticleRevisionReceipt.model_validate(raw), args["receipts"][1])
    actual = normalize_particle_revisions(args["receipts"], unresolved_log_weight=unresolved)
    expected = decimal_reference(args["receipts"], unresolved)
    assert [w.posterior_probability for w in actual.particle_weights] + [
        actual.unresolved_probability
    ] == pytest.approx(expected, rel=2e-14, abs=5e-324)
    assert actual.particle_weights[0].accepted is not rejected
    if rejected:
        assert args["receipts"][0].unnormalized_log_weight == -math.inf
        assert actual.particle_weights[0].posterior_probability == 0


@pytest.mark.parametrize(
    "fault",
    [
        "positive_overflow",
        "negative_overflow",
        "unresolved_underflow",
        "nan",
        "positive_inf",
        "negative_inf",
    ],
)
@pytest.mark.parametrize("step", [0, 1])
def test_numeric_failure_is_explicit_atomic_and_retryable(fault, step):
    probe = old._legacy_history(1)
    core = probe.system.core
    if step:
        core.stage_prepared_particle_candidates(**candidates(core))
    good = candidates(core, step=step)
    if fault == "positive_overflow":
        args = reseal(good, observation_log_likelihood=1e308, proposal_log_probability=-1e308)
    elif fault == "negative_overflow":
        args = reseal(good, observation_log_likelihood=-1e308, transition_log_probability=-1e308)
    elif fault == "unresolved_underflow":
        args = reseal(good, observation_log_likelihood=1e308)
    else:
        args = deepcopy(good)
        args["receipts"] = (
            args["receipts"][0].model_copy(
                update={
                    "observation_log_likelihood": {
                        "nan": math.nan,
                        "positive_inf": math.inf,
                        "negative_inf": -math.inf,
                    }[fault]
                }
            ),
            args["receipts"][1],
        )
    reject_retry(probe, args, good=good)


@pytest.mark.parametrize("exception", [RuntimeError, KeyboardInterrupt])
@pytest.mark.parametrize("step", [0, 1])
def test_stable_readout_validation_interruption_restores_all_instances(exception, step):
    from cpswm.system.structure_two_particle_workspace import _location_marginal

    probe = old._legacy_history(1)
    core = probe.system.core
    if step:
        core.stage_prepared_particle_candidates(**candidates(core))
    good = reseal(candidates(core, step=step), alpha=(1e308,) * 4)
    before = snapshot(probe)
    previous = sys.getprofile()

    def profile(frame, event, result):
        if frame.f_code is _location_marginal.__code__ and event == "return":
            raise exception("marginal validation interrupted")

    try:
        sys.setprofile(profile)
        with pytest.raises(exception, match="interrupted"):
            core.stage_prepared_particle_candidates(**good)
    finally:
        sys.setprofile(previous)
    assert snapshot(probe) == before
    assert core.stage_prepared_particle_candidates(**good).particle_weights
    after = snapshot(probe)
    core.stage_prepared_particle_candidates(**good)
    assert snapshot(probe) == after


def test_shared_extreme_log_offset_preserves_small_relative_evidence():
    core = old._legacy_history(1).system.core
    args = candidates(core)
    revised = []
    for i, receipt in enumerate(args["receipts"]):
        raw = receipt.model_dump()
        raw["observation_log_likelihood"] = 1e308
        raw["proposal"]["proposal_log_probability"] = 0.0
        raw["constraints"][0]["log_potential"] = -float(i + 1)
        revised.append(ParticleRevisionReceipt.model_validate(raw))
    args["receipts"] = tuple(revised)
    args["unresolved_log_weight"] = 1e308
    batch = core.stage_prepared_particle_candidates(**args)
    expected = decimal_reference(args["receipts"], 1e308)
    actual = [w.posterior_probability for w in batch.particle_weights] + [
        batch.unresolved_probability
    ]
    assert actual == pytest.approx(expected, rel=2e-15)
    assert actual[2] > actual[0] > actual[1] > 0
    probability, unresolved = core.prepared_particle_location_marginal()
    assert sum(probability.values()) + unresolved == pytest.approx(1)


@pytest.mark.parametrize(
    "q,obs,transition,u",
    [
        (-1e308, 0.0, -1e308, 0.0),
        (-1e308, 1e308, -1e308, 1e308),
    ],
)
def test_public_finite_cancellation_is_consumable(q, obs, transition, u):
    probe = old._legacy_history(1)
    core = probe.system.core
    args = reseal(
        candidates(core),
        proposal_log_probability=q,
        observation_log_likelihood=obs,
        transition_log_probability=transition,
        alpha=(1e308,) * 4,
    )
    args["unresolved_log_weight"] = u
    before = snapshot(probe)
    result = core.stage_prepared_particle_candidates(**args)
    actual = [w.posterior_probability for w in result.particle_weights] + [
        result.unresolved_probability
    ]
    assert actual == pytest.approx(decimal_reference(args["receipts"], u), rel=2e-15)
    p, unresolved = core.prepared_particle_location_marginal()
    assert sum(p.values()) > 0 and unresolved > 0
    assert sum(p.values()) + unresolved == pytest.approx(1)
    assert snapshot(probe)[1:] == before[1:]


@pytest.mark.parametrize("all_rejected", [False, True])
def test_structural_rejection_is_audited_even_for_unrepresentable_unused_score(all_rejected):
    core = old._legacy_history(1).system.core
    args = reseal(
        candidates(core), proposal_log_probability=-1e308, observation_log_likelihood=1e308
    )
    revised = []
    for i, receipt in enumerate(args["receipts"]):
        raw = receipt.model_dump()
        if i == 0 or all_rejected:
            raw["constraints"][0].update(accepted=False, rejection_reason="physical violation")
        revised.append(ParticleRevisionReceipt.model_validate(raw))
    args["receipts"] = tuple(revised)
    result = core.stage_prepared_particle_candidates(**args)
    assert result.particle_weights[0].posterior_probability == 0
    assert (
        core._particle_workspace.receipts[0].constraints[0].rejection_reason == "physical violation"
    )
    probabilities, unresolved = core.prepared_particle_location_marginal()
    assert unresolved == pytest.approx(1.0)
    assert not any(probabilities.values())
    if all_rejected:
        assert result.unresolved_probability == 1.0
