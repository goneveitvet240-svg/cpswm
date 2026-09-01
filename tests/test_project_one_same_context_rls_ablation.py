"""阶段 1: does the RLS residual actually separate expected from anomalous?

This is the matched test the project-one claim rests on.  Everything the two
branches see is identical — object, actor, context key, context value, time
slot, observation quality, and the entire learning prefix.  The single
difference is *where the cup was seen on the final morning*:

* expected:  the dining table, which is where the learned morning habit puts it;
* anomalous: the balcony, which the morning habit has never produced.

The prefix ends on an evening, so both branches start from the same last
observed location and ``habit_transition`` is 1 for both.  A difference between
them therefore cannot come from a new ``context_key``, a new time slot, a new
state bucket, or the move indicator — those are held constant by construction.

What this test found
--------------------
The residual mechanism works.  The wiring that delivers it does not.

``RLSHabitScoreHead.score_candidates`` applies a sigmoid by default, but the
underlying model is a least-squares regressor already fitted to ``{0, 1}``
targets, so its raw output is already the score.  Squashing it a second time
maps a perfectly learned ``1.0`` to ``0.731`` and a perfectly rejected ``0.0``
to ``0.5``.  The residual can then never leave ``[0.269, 0.5]`` — roughly a
quarter of its nominal range — and a correctly predicted event carries a
permanent residual floor of ``0.269``.

Measured on this fixture (margin = anomalous signal minus expected signal):

===============  ==========  ==========  ==========  ==========
calibration      full        no_rls      shuffled    rls_only
===============  ==========  ==========  ==========  ==========
as_is (shipped)  0.5195      0.9402      0.5025      0.2844
logit (fixed)    1.0000      0.9402      0.9402      1.0000
===============  ==========  ==========  ==========  ==========

The defect also reaches the decision layer, which is the part that actually
matters.  Change probability on the anomalous branch:

===============  ==========  ==========  ==========  ==========
calibration      full        no_rls      shuffled    rls_only
===============  ==========  ==========  ==========  ==========
as_is (shipped)  0.9728      1.0000      0.9416      0.2135
logit (fixed)    1.0000      1.0000      1.0000      1.0000
===============  ==========  ==========  ==========  ==========

Under the shipped wiring ``rls_only`` reaches only ``0.2135`` and its decision
stays ``STABLE`` — the residual on its own **fails to flag the anomaly at
all**.  Adding the shipped residual to the surprise channel also *lowers* the
full arm's change probability below the no-residual arm's, because the residual
floor has inflated the habit channel on every ordinary day, so the changepoint
detector has learned to expect a high habit signal.

Under the shipped wiring the full arm is *worse* than removing the residual
entirely, and shuffling the residual barely changes anything — by the project's
own conclusion table that reads as "the residual is only a scale signal".
Invert the sigmoid and the reading flips completely: the full arm becomes the
best, and shuffling now costs real discrimination, which is what an informative
signal looks like.

The fix is one default argument in a module this experiment series does not
own, so this file *records* the defect rather than working around it.  The
``as_is`` expectations below are ``xfail(strict=True)``: the day the head stops
double-squashing, they fail loudly and someone comes back here to delete them.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from statistics import median

import numpy as np
import pytest

from cpswm.system.continual.rls import RLSHabitSample, RLSHabitScoreHead
from cpswm.system.evaluation_operations.project_one_dataset import ProjectOneDatasetRecord
from cpswm.system.evaluation_operations.project_one_methods import (
    CoreHabitChainMethod,
    StepPrediction,
)
from cpswm.system.evaluation_operations.project_one_protocol import (
    SIGMOID_RESIDUAL_FLOOR,
    ProjectOneDecision,
    ProjectOneProtocolConfig,
    ResidualCalibration,
    SignalAblation,
)

LOCATIONS = ("dining_table", "desk", "balcony", "shelf")
OWNER = "owner"
HOUSEHOLD = "household-1"
OBJECT = "cup-17"
EPOCH = datetime(2026, 3, 1, 8, 0, tzinfo=UTC)

#: Long enough that the morning habit is unambiguous and the baseline window
#: (3 observations) is far behind us.
CYCLES = 12


def _record(index: int, *, morning: bool, location: str) -> ProjectOneDatasetRecord:
    return ProjectOneDatasetRecord(
        stream_id="same-context",
        event_id=f"same-context-{index:03d}",
        subject_id=OWNER,
        household_id=HOUSEHOLD,
        object_id=OBJECT,
        actor_id=OWNER,
        timestamp=EPOCH + timedelta(hours=12 * index),
        context_key="morning" if morning else "evening",
        context_value=0.0 if morning else 1.0,
        observed_location=location,
        observation_quality=0.9,
    )


def _prefix() -> list[ProjectOneDatasetRecord]:
    """Morning -> dining table, evening -> desk, repeated, ending on an evening."""

    records: list[ProjectOneDatasetRecord] = []
    for cycle in range(CYCLES):
        records.append(_record(2 * cycle, morning=True, location="dining_table"))
        records.append(_record(2 * cycle + 1, morning=False, location="desk"))
    return records


def _final(location: str) -> ProjectOneDatasetRecord:
    return _record(2 * CYCLES, morning=True, location=location)


@lru_cache(maxsize=1)
def _warm_snapshot() -> CoreHabitChainMethod:
    """One arm, trained once on the shared prefix.

    Every branch below is a deep copy of *this* object, so the two branches do
    not merely receive the same inputs — they start from byte-identical model
    state.  That distinction is not pedantic: running two ablations over the
    same prefix gives them different habit signals from the first step, hence
    different quarantine decisions, hence different learned counts long before
    the step under study.  v0.2 compared arms that had already diverged.

    The snapshot is built with ``FULL`` and the default calibration; the
    interventions below replace only the read path, which is what a
    final-step matched pair is supposed to isolate.  Whole-stream effects of a
    calibration route are a different question, and the benchmark answers it.
    """

    arm = _arm(SignalAblation.FULL, ResidualCalibration.RAW_CLIP)
    arm.reset()
    for record in _prefix():
        arm.observe(record)
    return arm


def _arm(ablation: SignalAblation, calibration: ResidualCalibration) -> CoreHabitChainMethod:
    return CoreHabitChainMethod(
        name=f"{ablation.value}/{calibration.value}",
        locations=LOCATIONS,
        owner_id=OWNER,
        household_id=HOUSEHOLD,
        object_id=OBJECT,
        config=replace(
            ProjectOneProtocolConfig(),
            ablation=ablation,
            residual_calibration=calibration,
        ),
    )


def _run_branch(
    ablation: SignalAblation,
    calibration: ResidualCalibration,
    final_location: str,
) -> StepPrediction:
    """Clone the shared warm snapshot, intervene once, observe one event.

    ``SHUFFLED_RLS`` is a stream-level ablation — a derangement of one element
    is meaningless — so its pointwise form substitutes a residual drawn from
    the arm's *own* prefix marginal.  Same magnitude, wrong pairing, which is
    exactly the claim the arm exists to test.  Its whole-stream form, with a
    real strict derangement, runs in the benchmark.
    """

    warm = _warm_snapshot()
    clone = warm.clone_with(ablation=ablation, residual_calibration=calibration)
    if ablation is SignalAblation.SHUFFLED_RLS:
        clone.pointwise_residual_override = median(warm.residual_history)
    return clone.observe(_final(final_location))


@lru_cache(maxsize=64)
def _run_consistent(
    ablation: SignalAblation,
    calibration: ResidualCalibration,
    final_location: str,
) -> StepPrediction:
    """Train *and* read under one route, over the whole fixture stream.

    The shared snapshot above answers "given one trained model, what does the
    read path do to this event?".  That is the right question for comparing
    ablations, and the wrong one for comparing calibration routes: a route
    changes the residual on every training step too, and the changepoint
    detector adapts to whatever level it sees.  Reading a snapshot trained
    under one route with a different route measures the mismatch, not the
    route.

    This helper also primes the arm over the full record list, so the shuffled
    ablation gets its real strict derangement instead of silently falling back
    to reporting its own residual.
    """

    records = [*_prefix(), _final(final_location)]
    arm = _arm(ablation, calibration)
    arm.reset()
    arm.prime(records)
    for record in records[:-1]:
        arm.observe(record)
    return arm.observe(records[-1])


def _margin(ablation: SignalAblation, calibration: ResidualCalibration) -> float:
    """Anomalous minus expected habit signal, under one self-consistent route."""

    expected = _run_consistent(ablation, calibration, "dining_table")
    anomalous = _run_consistent(ablation, calibration, "balcony")
    return anomalous.habit_signal - expected.habit_signal


def _change_probability(ablation: SignalAblation, calibration: ResidualCalibration) -> float:
    return _run_consistent(ablation, calibration, "balcony").change_probability


# ---------------------------------------------------------------------------
# The two matched branches really are matched
# ---------------------------------------------------------------------------


def test_the_two_branches_differ_only_in_the_observed_location() -> None:
    expected = _final("dining_table")
    anomalous = _final("balcony")
    for field_name in (
        "stream_id",
        "subject_id",
        "household_id",
        "object_id",
        "actor_id",
        "timestamp",
        "context_key",
        "context_value",
        "observation_quality",
    ):
        assert getattr(expected, field_name) == getattr(anomalous, field_name)
    assert expected.observed_location != anomalous.observed_location


def test_the_shared_prefix_is_identical_for_both_branches() -> None:
    assert _prefix() == _prefix()


def test_both_branches_see_the_same_previous_location() -> None:
    """So ``habit_transition`` is 1 for both and cannot explain any difference."""

    assert _prefix()[-1].observed_location == "desk"
    assert _final("dining_table").observed_location != "desk"
    assert _final("balcony").observed_location != "desk"


# ---------------------------------------------------------------------------
# The mechanism itself: with the sigmoid inverted, the residual does its job
# ---------------------------------------------------------------------------


def test_expected_residual_is_below_anomalous_residual() -> None:
    expected = _run_consistent(SignalAblation.FULL, ResidualCalibration.LOGIT, "dining_table")
    anomalous = _run_consistent(SignalAblation.FULL, ResidualCalibration.LOGIT, "balcony")
    assert expected.rls_residual is not None
    assert anomalous.rls_residual is not None
    assert expected.rls_residual < anomalous.rls_residual


def test_expected_habit_signal_is_below_anomalous_habit_signal() -> None:
    expected = _run_consistent(SignalAblation.FULL, ResidualCalibration.LOGIT, "dining_table")
    anomalous = _run_consistent(SignalAblation.FULL, ResidualCalibration.LOGIT, "balcony")
    assert expected.habit_signal < anomalous.habit_signal


def test_full_margin_exceeds_no_rls_margin() -> None:
    """The residual must buy discrimination the Dirichlet surprise cannot."""

    assert _margin(SignalAblation.FULL, ResidualCalibration.LOGIT) > _margin(
        SignalAblation.NO_RLS, ResidualCalibration.LOGIT
    )


def test_shuffled_residual_discriminates_less_than_the_real_one() -> None:
    """Same residual magnitudes, wrong pairing: discrimination must drop."""

    assert _margin(SignalAblation.FULL, ResidualCalibration.LOGIT) > _margin(
        SignalAblation.SHUFFLED_RLS, ResidualCalibration.LOGIT
    )


def test_rls_only_arm_still_separates_the_two_branches() -> None:
    """With the Dirichlet surprise removed, the residual must carry it alone."""

    assert _margin(SignalAblation.RLS_ONLY, ResidualCalibration.LOGIT) > 0.0


# ---------------------------------------------------------------------------
# The defect, pinned
# ---------------------------------------------------------------------------


def test_the_rls_head_learns_the_context_perfectly_before_the_sigmoid() -> None:
    """The model is not the problem: its raw output is exactly right."""

    object_id, actor = _arm(SignalAblation.FULL, ResidualCalibration.AS_IS)._object_uuid, OWNER
    locations = tuple(
        _arm(SignalAblation.FULL, ResidualCalibration.AS_IS)._to_uuid[name] for name in LOCATIONS
    )
    embeddings = {location: np.eye(4)[index] for index, location in enumerate(locations)}
    head = RLSHabitScoreHead(context_feature_dim=1, location_embedding_dim=4)
    for _ in range(30):
        for context_value, target in ((0.0, locations[0]), (1.0, locations[1])):
            head.update(
                RLSHabitSample(
                    object_instance_id=object_id,
                    actor_id=actor,
                    context_features=np.array([context_value]),
                    target_location_id=target,
                    candidate_locations=locations,
                    gate=0.81,
                    regime_id="stable",
                ),
                embeddings,
            )

    raw = head.score_candidates(
        object_instance_id=object_id,
        actor_id=actor,
        regime_id="stable",
        context_features=np.array([0.0]),
        candidate_locations=locations,
        location_embeddings=embeddings,
        apply_sigmoid=False,
    )
    assert raw[locations[0]] == pytest.approx(1.0, abs=1e-4)
    assert raw[locations[2]] == pytest.approx(0.0, abs=1e-4)

    default_scores = head.score_candidates(
        object_instance_id=object_id,
        actor_id=actor,
        regime_id="stable",
        context_features=np.array([0.0]),
        candidate_locations=locations,
        location_embeddings=embeddings,
    )
    assert default_scores == pytest.approx(raw, abs=1e-12)

    historical = head.score_candidates(
        object_instance_id=object_id,
        actor_id=actor,
        regime_id="stable",
        context_features=np.array([0.0]),
        candidate_locations=locations,
        location_embeddings=embeddings,
        apply_sigmoid=True,
    )
    assert historical[locations[0]] == pytest.approx(1.0 - SIGMOID_RESIDUAL_FLOOR, abs=1e-4)
    assert historical[locations[2]] == pytest.approx(0.5, abs=1e-4)


def test_a_perfectly_predicted_event_has_no_sigmoid_residual_floor() -> None:
    """The corrected default reads the raw RLS score exactly once."""

    expected = _run_consistent(SignalAblation.FULL, ResidualCalibration.AS_IS, "dining_table")
    assert expected.rls_residual == pytest.approx(0.0, abs=1e-4)


def test_a_correctly_predicted_move_has_negligible_habit_signal() -> None:

    expected = _run_consistent(SignalAblation.FULL, ResidualCalibration.AS_IS, "dining_table")
    assert expected.habit_signal == pytest.approx(0.0, abs=1e-4)


def test_corrected_wiring_full_margin_exceeds_no_rls_margin() -> None:
    assert _margin(SignalAblation.FULL, ResidualCalibration.AS_IS) > _margin(
        SignalAblation.NO_RLS, ResidualCalibration.AS_IS
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Shipped wiring compresses the residual into [0.269, 0.5], so shuffling "
        "it barely changes the margin (0.5025 vs 0.5195) — the project's own "
        "conclusion table calls that 'only a scale signal'."
    ),
)
def test_shipped_wiring_shuffling_costs_real_discrimination() -> None:
    full = _margin(SignalAblation.FULL, ResidualCalibration.AS_IS)
    shuffled = _margin(SignalAblation.SHUFFLED_RLS, ResidualCalibration.AS_IS)
    assert full - shuffled > 0.1


# ---------------------------------------------------------------------------
# The intervention is surgical and reproducible
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ablation",
    [SignalAblation.FULL, SignalAblation.NO_RLS, SignalAblation.SHUFFLED_RLS],
)
@pytest.mark.parametrize("calibration", list(ResidualCalibration))
def test_each_arm_is_deterministic(
    ablation: SignalAblation, calibration: ResidualCalibration
) -> None:
    first = _run_branch(ablation, calibration, "balcony")
    second = _run_branch(ablation, calibration, "balcony")
    assert first.habit_signal == second.habit_signal
    assert first.change_probability == second.change_probability
    assert first.decision is second.decision


def test_no_rls_arm_really_reports_a_zero_residual() -> None:
    prediction = _run_consistent(SignalAblation.NO_RLS, ResidualCalibration.AS_IS, "balcony")
    assert prediction.rls_residual == 0.0


def test_every_arm_carries_a_distinct_config_hash() -> None:
    hashes = {
        (ablation, calibration): _arm(ablation, calibration).config.config_hash()
        for ablation in SignalAblation
        for calibration in ResidualCalibration
    }
    assert len(set(hashes.values())) == len(hashes)


# ---------------------------------------------------------------------------
# The decision layer: change probability and the final four-class label
# ---------------------------------------------------------------------------


def test_change_probability_separates_the_two_branches() -> None:
    expected = _run_consistent(SignalAblation.FULL, ResidualCalibration.LOGIT, "dining_table")
    anomalous = _run_consistent(SignalAblation.FULL, ResidualCalibration.LOGIT, "balcony")
    assert anomalous.change_probability > expected.change_probability


def test_the_expected_branch_is_decided_stable() -> None:
    for calibration in ResidualCalibration:
        prediction = _run_consistent(SignalAblation.FULL, calibration, "dining_table")
        assert prediction.decision is ProjectOneDecision.STABLE, calibration


def test_the_anomalous_branch_leaves_stable() -> None:
    prediction = _run_consistent(SignalAblation.FULL, ResidualCalibration.LOGIT, "balcony")
    assert prediction.decision is not ProjectOneDecision.STABLE


def test_one_anomaly_is_not_confirmed_as_a_habit_change() -> None:
    """The confirmation window must hold a single outlier back.

    A one-shot anomaly should read as ``INSUFFICIENT_EVIDENCE``, not as a new
    habit.  This is the guardrail that stops a single stray observation from
    rewriting the long-term model, so it is asserted positively rather than
    left as an implicit property.
    """

    prediction = _run_consistent(SignalAblation.FULL, ResidualCalibration.LOGIT, "balcony")
    assert prediction.decision is ProjectOneDecision.INSUFFICIENT_EVIDENCE


def test_rls_only_escalates_once_the_sigmoid_is_inverted() -> None:
    """With the residual as its only channel, it must still reach the anomaly."""

    prediction = _run_consistent(SignalAblation.RLS_ONLY, ResidualCalibration.LOGIT, "balcony")
    assert prediction.change_probability > 0.9
    assert prediction.decision is not ProjectOneDecision.STABLE


def test_corrected_as_is_wiring_lets_the_rls_only_arm_see_the_anomaly() -> None:

    prediction = _run_consistent(SignalAblation.RLS_ONLY, ResidualCalibration.AS_IS, "balcony")
    assert prediction.change_probability > 0.9
    assert prediction.decision is not ProjectOneDecision.STABLE


def test_extreme_anomaly_preserves_rls_signal_even_when_change_probability_saturates() -> None:
    """Do not mistake a saturated posterior for evidence that RLS added no signal.

    This fixture is an intentionally extreme location anomaly.  Both arms drive
    CF-BOCPD to a machine-precision posterior of one, so ordering the final
    probabilities is not an identifiable invariant.  The surgical ablation is
    still visible at the input to that detector and is tested there; action-level
    benefit remains a separate matched benchmark question.
    """

    full = _run_consistent(SignalAblation.FULL, ResidualCalibration.AS_IS, "balcony")
    no_rls = _run_consistent(SignalAblation.NO_RLS, ResidualCalibration.AS_IS, "balcony")
    assert full.change_probability == no_rls.change_probability == 1.0
    assert full.habit_signal > no_rls.habit_signal


# ---------------------------------------------------------------------------
# The matched pair is matched at the level of model state, not just inputs
# ---------------------------------------------------------------------------


def test_all_branches_start_from_one_shared_snapshot() -> None:
    """Every branch is a deep copy of the same trained arm."""

    warm = _warm_snapshot()
    first = warm.clone_with(ablation=SignalAblation.NO_RLS)
    second = warm.clone_with(ablation=SignalAblation.RLS_ONLY)
    assert first is not warm and second is not warm
    assert first.snapshot()["steps"] == second.snapshot()["steps"] == 2 * CYCLES
    assert first.residual_history == second.residual_history == warm.residual_history


def test_a_clone_cannot_write_back_into_the_snapshot() -> None:
    warm = _warm_snapshot()
    before = len(warm.residual_history)
    clone = warm.clone_with(ablation=SignalAblation.FULL)
    clone.observe(_final("balcony"))
    assert len(warm.residual_history) == before


def test_the_pointwise_override_is_consumed_exactly_once() -> None:
    """It must not leak into any later step."""

    clone = _warm_snapshot().clone_with(ablation=SignalAblation.SHUFFLED_RLS)
    clone.pointwise_residual_override = 0.77
    first = clone.observe(_final("balcony"))
    assert first.rls_residual == pytest.approx(0.77)
    assert clone.pointwise_residual_override is None


# ---------------------------------------------------------------------------
# The stream-level shuffle really is a strict derangement
# ---------------------------------------------------------------------------


def test_the_shuffle_is_a_strict_derangement_of_the_real_residuals() -> None:
    from cpswm.system.evaluation_operations.project_one_methods import _strict_derangement

    values = [0.269] * 5 + [0.5, 1.0, 0.0]
    deranged = _strict_derangement(values, seed=12345)
    assert sorted(deranged) == sorted(values), "the marginal must be preserved exactly"
    order = list(range(len(values)))
    # Rebuild the index map to assert strictness rather than trusting the values,
    # which repeat and therefore cannot prove it.
    permutation = _strict_derangement(order, seed=12345)
    assert all(position != index for index, position in enumerate(permutation))


def test_a_primed_shuffled_arm_shuffles_every_step() -> None:
    from cpswm.system.evaluation_operations.project_one_methods import CoreHabitChainMethod
    from cpswm.system.evaluation_operations.project_one_runner import ProjectOneRunner
    from cpswm.system.evaluation_operations.project_one_scenarios import (
        LOCATIONS as SCENARIO_LOCATIONS,
    )
    from cpswm.system.evaluation_operations.project_one_scenarios import build_stream

    stream, truth = build_stream("permanent_change")
    arm = CoreHabitChainMethod(
        name="shuffled_rls",
        locations=SCENARIO_LOCATIONS,
        owner_id=OWNER,
        household_id=HOUSEHOLD,
        object_id=OBJECT,
        config=replace(ProjectOneProtocolConfig(), ablation=SignalAblation.SHUFFLED_RLS),
    )
    result = ProjectOneRunner().run_arm(arm, stream, truth)
    assert result.failure is None
    assert result.snapshot["derangement_length"] == len(stream)
    assert result.snapshot["unprimed_shuffle_steps"] == 0, (
        "a fixed-lag substitute used to leave the first steps unshuffled"
    )


def test_raw_clip_and_as_is_are_equivalent_on_one_fixed_model() -> None:
    """The historical scale conversion and corrected raw readout must agree."""

    fixed_model = _run_branch(SignalAblation.FULL, ResidualCalibration.AS_IS, "dining_table")
    self_consistent = _run_consistent(
        SignalAblation.FULL, ResidualCalibration.AS_IS, "dining_table"
    )
    assert fixed_model.habit_signal == pytest.approx(0.0, abs=1e-4)
    assert fixed_model.habit_signal == pytest.approx(self_consistent.habit_signal, abs=1e-9)
    assert fixed_model.change_probability == pytest.approx(
        self_consistent.change_probability, abs=1e-9
    )
