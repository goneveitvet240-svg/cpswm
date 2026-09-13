"""R6: the four layers of a CIAV observation, kept separate.

Round one said the CIAV local likelihood was "computed and then discarded", which
merged four different questions.  The independent review was right to split them:

1. ``local_posterior``   -- is a real Bayes update computed?
2. ``persistence_target``-- does the receipt name the distribution that is written?
3. ``fast_memory``       -- does a fast-ledger / revision write actually happen?
4. ``action_consumption``-- does the decoded action change?

The frozen pre-death protocol's ``claim_boundary`` states that "a negative CIAV
observation does not yet enter a complete downstream closure".  The contract
therefore does **not** require layers 3 and 4 for a negative observation, so the
repair is to make the receipt tell the truth about layer 2 and to pin the
invariants -- not to invent a downstream write.

Also pinned here are three ``hard_safety_kernel`` clauses:
``unexecuted_inference_may_not_be_encoded_as_negative_evidence``,
``maximum_unresolved_as_negative_events == 0`` and
``maximum_unauthorized_long_term_commits == 0``.
"""

from __future__ import annotations

import pytest
from structure_two_backbone_wiring_probe import (
    BackboneWiringProbe,
    CIAVOutcomeKind,
    verify_and_flatten,
)

from cpswm.contracts import (
    EvidenceFactorConsumptionTrace,
    EvidenceFactorOperation,
    EvidenceFactorOperator,
    ObservationOutcome,
)

SEED = 7
LOCAL_TARGET_PREFIX = "ciav-local-actor-posterior:"


def _run(outcome: CIAVOutcomeKind, **ciav):
    trace = EvidenceFactorConsumptionTrace()
    probe = BackboneWiringProbe.build(seed=SEED)
    probe.system.bind_evidence_factor_trace(trace)
    transition = probe.transition_for(probe.observed_days()[0])
    result, sink = probe.run_direct_p5(
        transition, ciav_input=probe.ciav_input(transition, outcome=outcome, **ciav)
    )
    return probe, result, sink, trace


# ---------------------------------------------------------------------------
# Layer 1 -- the local Bayes update really happens
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("outcome", list(CIAVOutcomeKind))
def test_layer_one_the_local_actor_posterior_is_an_exact_bayes_update(
    outcome: CIAVOutcomeKind,
) -> None:
    probe, result, _, _ = _run(outcome, owner_likelihood=0.8)
    assert result.ciav_receipt is not None

    prior = dict(result.primary_result.actor_posterior)
    owner, guest = probe.case.owner_actor, probe.case.guest_actor
    remainder = (1.0 - 0.8) / 2.0
    likelihood = {owner: 0.8, guest: remainder, "unknown_actor": remainder}
    unnormalized = {actor: prior[actor] * likelihood[actor] for actor in prior}
    total = sum(unnormalized.values())
    expected = {actor: value / total for actor, value in unnormalized.items()}

    posterior = dict(result.ciav_receipt.evidence.actor_posterior)
    assert set(posterior) == set(expected)
    for actor, value in expected.items():
        assert posterior[actor] == pytest.approx(value)
    assert sum(posterior.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Layer 2 -- the receipt names the distribution that is actually written
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("outcome", list(CIAVOutcomeKind))
def test_layer_two_the_consumption_target_is_the_loop_s_own_local_posterior(
    outcome: CIAVOutcomeKind,
) -> None:
    """Pre-fix the target was ``fast-action-owner-posterior:*`` for every outcome.

    That store is written only by ``apply_fast_action_verification``, i.e. only on
    the same-location branch, so two of the three outcomes recorded a consumption
    into a distribution nothing had written.
    """

    _, result, _, trace = _run(outcome)
    assert result.ciav_receipt is not None
    consumed = result.ciav_receipt.consumed_factor
    summary = result.ciav_receipt.posterior_summary

    assert consumed.consumed_as_likelihood is True
    assert consumed.target_distribution_id.startswith(LOCAL_TARGET_PREFIX)
    assert summary.target_distribution_id == consumed.target_distribution_id
    assert all(
        "fast-action-owner-posterior" not in (item.target_distribution_id or "")
        for item in trace.receipts
    )
    assert trace.verify_chain() is True

    operations = [(item.operator, item.operation) for item in trace.receipts]
    assert operations == [
        (EvidenceFactorOperator.OPCEU, EvidenceFactorOperation.PRODUCE),
        (EvidenceFactorOperator.CIAV, EvidenceFactorOperation.CONSUME),
        (EvidenceFactorOperator.CIAV, EvidenceFactorOperation.DERIVE),
    ]


# ---------------------------------------------------------------------------
# Layer 3 -- the fast-memory write happens only on the branch that owns it
# ---------------------------------------------------------------------------


def test_layer_three_only_the_same_location_branch_writes_the_fast_ledger() -> None:
    same_probe, same_result, _, _ = _run(CIAVOutcomeKind.DETECTED_SAME_LOCATION)
    other_probe, other_result, _, _ = _run(CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION)
    negative_probe, negative_result, _, _ = _run(CIAVOutcomeKind.NOT_DETECTED)

    assert same_result.fast_verification_receipt is not None
    assert other_result.fast_verification_receipt is None
    assert negative_result.fast_verification_receipt is None

    assert len(same_probe.system.core.fast_action_verification_receipts) == 1
    assert other_probe.system.core.fast_action_verification_receipts == ()
    assert negative_probe.system.core.fast_action_verification_receipts == ()


# ---------------------------------------------------------------------------
# Layer 4 -- the action consequence of a negative observation
# ---------------------------------------------------------------------------


def test_layer_four_a_negative_observation_leaves_the_decoded_action_unchanged() -> None:
    """Not a defect: the frozen claim boundary registers this closure as absent.

    The reference is a run whose CIAV action is blocked outright, so the comparison
    isolates "the negative observation was realized" from "no CIAV action ran".
    """

    negative_probe, negative_result, _, _ = _run(CIAVOutcomeKind.NOT_DETECTED)
    blocked_probe, blocked_result, _, _ = _run(
        CIAVOutcomeKind.NOT_DETECTED, privacy_cost=0.9, privacy_budget=0.1
    )

    assert negative_result.ciav_receipt is not None
    assert blocked_result.ciav_receipt is None
    assert negative_probe.action_distribution_sha256() == (
        blocked_probe.action_distribution_sha256()
    )


# ---------------------------------------------------------------------------
# The three hard-safety clauses
# ---------------------------------------------------------------------------


def test_an_unexecuted_action_is_not_encoded_as_a_negative_observation() -> None:
    """``unexecuted_inference_may_not_be_encoded_as_negative_evidence``."""

    probe, result, sink, trace = _run(
        CIAVOutcomeKind.DETECTED_SAME_LOCATION, privacy_cost=0.9, privacy_budget=0.1
    )
    _, rows = verify_and_flatten(sink)

    assert result.ciav_plan is not None and result.ciav_plan.should_act is False
    assert result.ciav_receipt is None
    assert trace.receipts == ()
    assert len(rows) == 7
    ciav_row = next(row for row in rows if row.operator == "ciav")
    assert ciav_row.status == "executed"
    assert probe.committed_revision_ids() == ()


def test_a_negative_observation_is_never_upgraded_to_a_positive_event() -> None:
    """``maximum_unresolved_as_negative_events`` and ``maximum_unauthorized_long_term_commits``."""

    probe, result, sink, _ = _run(CIAVOutcomeKind.NOT_DETECTED)
    trace, rows = verify_and_flatten(sink)
    assert result.ciav_receipt is not None
    detection = result.ciav_receipt.detection
    evidence = result.ciav_receipt.evidence

    assert detection.outcome is ObservationOutcome.NOT_OBSERVED
    assert detection.detected_location_id is None
    assert detection.detected_object_instance_id is None
    assert detection.detection_time is None
    assert evidence.detected_location_key is None
    assert evidence.location_posterior["unknown_location"] == pytest.approx(1.0)
    assert result.feedback_result is None
    assert trace.feedback_closure_kind == "none"
    assert len(rows) == 7
    assert probe.committed_revision_ids() == ()
    for location in probe.case.locations:
        assert probe.system.core.hybrid_alpha(location) == pytest.approx(0.0)


def test_one_realized_ciav_observation_is_counted_once_across_direct_and_replay() -> None:
    """The same evidence must not be counted twice on the direct and replay routes."""

    def direct():
        probe = BackboneWiringProbe.build(seed=SEED)
        transition = probe.transition_for(probe.observed_days()[0])
        ciav = probe.ciav_input(
            transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
        )
        result, _ = probe.run_direct_p5(transition, ciav_input=ciav)
        return probe, result

    def replay():
        probe = BackboneWiringProbe.build(seed=SEED)
        transition = probe.transition_for(probe.observed_days()[0])
        ciav = probe.ciav_input(
            transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
        )
        deferred, _ = probe.run_adaptive(
            transition,
            ciav_input=ciav,
            features=probe.router_features(action_margin=0.9, regime_hazard=0.0),
            debt_expiry_steps=1,
        )
        result, _ = probe.replay_debt(
            deferred.debt_certificates[0].debt_id, ciav_input=ciav
        )
        return probe, result

    direct_probe, direct_result = direct()
    replay_probe, replay_result = replay()

    assert direct_result.ciav_receipt is not None
    assert replay_result.ciav_receipt is not None
    assert dict(direct_result.ciav_receipt.evidence.actor_posterior) == dict(
        replay_result.ciav_receipt.evidence.actor_posterior
    )
    assert len(direct_probe.committed_revision_ids()) == len(
        replay_probe.committed_revision_ids()
    )
    for location in direct_probe.case.locations:
        assert direct_probe.system.core.hybrid_alpha(location) == pytest.approx(
            replay_probe.system.core.hybrid_alpha(location)
        )
    assert direct_probe.action_distribution_sha256() == (
        replay_probe.action_distribution_sha256()
    )


def test_repeating_the_identical_ciav_execution_produces_no_second_factor() -> None:
    """The evidence-factor trace's idempotency keys prevent a duplicate likelihood."""

    trace = EvidenceFactorConsumptionTrace()
    probe = BackboneWiringProbe.build(seed=SEED)
    probe.system.bind_evidence_factor_trace(trace)
    transition = probe.transition_for(probe.observed_days()[0])
    ciav = probe.ciav_input(transition, outcome=CIAVOutcomeKind.NOT_DETECTED)
    result, _ = probe.run_direct_p5(transition, ciav_input=ciav)
    assert result.ciav_receipt is not None
    first = len(trace.receipts)

    repeat = probe.system.ciav_opceu_loop.execute_selected_action(
        action=ciav.actions[0],
        update_id=result.primary_result.event_revision_id,
        household_id=transition.after.metadata.household_id,
        session_id=transition.after.metadata.session_id,
        trace_id=transition.after.metadata.trace_id,
        opportunity_time=ciav.opportunity_time,
        object_instance_id=probe.system.core.object_instance_id,
        actor_keys=tuple(
            actor for actor in transition.actor_prior if actor != "unknown_actor"
        ),
        actor_prior=dict(result.primary_result.actor_posterior),
        actor_likelihoods_by_outcome={
            outcome: dict(values)
            for outcome, values in ciav.actor_likelihoods_by_outcome.items()
        },
        location_keys=tuple(str(item) for item in probe.system.core.locations),
        expected_detected_location_id=ciav.expected_detected_location_id,
        selection_probability=ciav.selection_probability,
        p_visible_given_state=ciav.p_visible_given_state,
        p_detect_given_visible=ciav.p_detect_given_visible,
        realizer=ciav.realizer,
    )

    assert len(trace.receipts) == first
    assert repeat.consumed_factor.factor_id == result.ciav_receipt.consumed_factor.factor_id
    assert trace.verify_chain() is True
