"""R4 -- seven-operator causal coverage on the formal production lanes.

The round-2 independent review showed, by profiling real call frames, that the
legacy ``core.process_transition`` entrypoint makes **zero** CIAV planner and
executor calls, while one formal direct-P5 step makes one of each:

    legacy_window_2   planner 0  executor 0
    legacy_window_3   planner 0  executor 0
    direct_p5_control planner 1  executor 1

So the round-1/2 matrix could not be read as "the seven operators collaborate on
one production lane": most of its interventions ran on the legacy lane.  This
file rebuilds the evidence on the two lanes that really run all seven --
evaluation-only direct P5 and legal debt replay -- and reports each kind of
evidence separately instead of merging them:

    runtime | binding | dependency | algorithmic equivalence
            | numeric impact | action impact | task benefit

Method notes, stated because they bound what the evidence means:

* interventions are changes to real algorithmic inputs (propensities, actor
  priors, unresolved mass, evidence, CIAV likelihoods and utilities).  No
  operator is deleted, no receipt is forged, and no intervention is chosen to
  force an action change;
* call counts and CIAV's actually-received objects are read from live frames with
  a profile hook (``RuntimeCallRecorder``).  Nothing is replaced, so the runtime
  identity guards, source bindings and receipts are the untraced ones;
* cells whose trigger condition cannot be met on a lane stay uncovered and are
  reported as uncovered.  An uncovered cell is not a passing cell;
* the retraction policy used anywhere in this suite is supplied by the caller
  through the documented ``policy=`` seam.  Nothing here shows the system
  retracting on its own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from structure_two_backbone_wiring_probe import (
    BackboneWiringProbe,
    CIAVOutcomeKind,
    RuntimeCallRecorder,
    verify_and_flatten,
)

from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_execution import STRUCTURE_TWO_OPERATOR_ORDER

MATRIX_ARTIFACT = Path("docs/reviews/data/structure_two_window3_round3_2026-09-11")


def _p0_features(probe: BackboneWiringProbe):
    return probe.router_features(action_margin=0.9, regime_hazard=0.0)


def _decoded_action(probe: BackboneWiringProbe) -> UUID:
    distribution = probe.action_distribution()
    return min(distribution, key=lambda key: (-distribution[key], str(key)))


# ---------------------------------------------------------------------------
# runtime: who actually gets called on each entrypoint
# ---------------------------------------------------------------------------


def _legacy_calls(days: int = 18, window: int = 2) -> dict[str, int]:
    from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig

    probe = BackboneWiringProbe.build(
        seed=7, loop_config=PrototypeLoopConfig(confirmation_window=window)
    )
    with RuntimeCallRecorder(probe.system) as recorder:
        for observation in probe.observed_days()[:days]:
            probe.system.core.process_transition(probe.transition_for(observation))
    return dict(recorder.calls)


def _direct_p5_calls() -> tuple[dict[str, int], Any, Any]:
    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    with RuntimeCallRecorder(probe.system) as recorder:
        result, sink = probe.run_direct_p5(
            transition,
            ciav_input=probe.ciav_input(
                transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
            ),
        )
    return dict(recorder.calls), (result, sink), recorder


def _debt_replay_calls() -> tuple[dict[str, int], Any, Any]:
    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    ciav_input = probe.ciav_input(transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION)
    probe.run_adaptive(
        transition, ciav_input=ciav_input, features=_p0_features(probe), debt_expiry_steps=20
    )
    debt = probe.system.pending_adaptive_debts()[0]
    with RuntimeCallRecorder(probe.system) as recorder:
        result, sink = probe.replay_debt(debt.debt_id, ciav_input=ciav_input)
    return dict(recorder.calls), (result, sink), recorder


def test_the_legacy_entrypoint_never_calls_ciav_and_the_formal_lanes_do() -> None:
    """Round-2 counterexample, reproduced, and the formal control beside it.

    This is the fact that forbids splicing legacy intervention results onto the
    formal lanes' identity receipts: on the legacy entrypoint CIAV is not merely
    weakly involved, it is never called.
    """

    for window in (2, 3):
        legacy = _legacy_calls(window=window)
        assert legacy["ciav_planner"] == 0
        assert legacy["ciav_executor"] == 0
        assert legacy["ciav_operator"] == 0
        assert legacy["core_process_transition"] > 0

    direct, _, _ = _direct_p5_calls()
    assert direct["ciav_planner"] == 1
    assert direct["ciav_executor"] == 1
    assert direct["ciav_operator"] == 1

    replay, _, _ = _debt_replay_calls()
    assert replay["ciav_planner"] == 1
    assert replay["ciav_executor"] == 1
    assert replay["ciav_operator"] == 1


@pytest.mark.parametrize("lane", ["direct_p5", "debt_replay"])
def test_a_formal_lane_receipts_all_seven_operators_with_real_bindings(lane: str) -> None:
    """binding evidence, separate from numeric evidence.

    Every operator in the frozen order carries a receipt bound to a live callable
    whose loaded code matches its source file, and CIAV is one of them with a
    non-zero real call count -- the combination the round-2 review said must not
    be asserted from two different lanes.
    """

    calls, (result, sink), _ = _direct_p5_calls() if lane == "direct_p5" else _debt_replay_calls()
    _, rows = verify_and_flatten(sink)
    executed = {row.operator for row in rows if row.status == "executed"}
    assert set(STRUCTURE_TWO_OPERATOR_ORDER) <= executed
    for row in rows:
        if row.status != "executed":
            continue
        assert row.operator_instance_id is not None
        assert row.implementation_symbol is not None
        assert row.callable_symbol is not None
    assert calls["ciav_planner"] >= 1
    assert calls["ciav_executor"] >= 1
    assert result.ciav_receipt is not None


# ---------------------------------------------------------------------------
# CF-BOCPD -> CIAV: the actual object, its content, and propagation
# ---------------------------------------------------------------------------


def _direct_p5_with_capture(
    probe: BackboneWiringProbe, transition: Any, **ciav_overrides: Any
) -> tuple[Any, Any, RuntimeCallRecorder]:
    ciav_input = probe.ciav_input(
        transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION, **ciav_overrides
    )
    with RuntimeCallRecorder(probe.system) as recorder:
        result, sink = probe.run_direct_p5(transition, ciav_input=ciav_input)
    return result, sink, recorder


def test_ciav_consumes_the_cf_bocpd_object_this_execution_actually_produced() -> None:
    """Not "both objects are non-None": the identical object and its content hash.

    ``_execute_ciav_operator`` reads ``core.current_cause_snapshot`` and builds the
    planner's belief from it.  The captured frame local is compared by identity to
    the runtime's snapshot and by content hash to the CF-BOCPD receipt this same
    execution sealed.
    """

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    _, sink, recorder = _direct_p5_with_capture(probe, transition)
    _, rows = verify_and_flatten(sink)
    cf_row = next(
        row
        for row in rows
        if row.operator == "cf_bocpd" and row.status == "executed" and row.phase == "selected_path"
    )

    captured = recorder.captured["ciav_operator_snapshot"]
    assert captured is not None
    # Identity, measured at the moment CIAV finished and before the feedback
    # closure advances the filter: the very object the core had published.
    assert recorder.captured["runtime_cause_snapshot_is_ciav_input"] is True
    assert recorder.captured["runtime_cause_snapshot"] is captured
    # Content: the same bytes CF-BOCPD's own receipt sealed on this lane's
    # primary pass.
    assert content_sha256(captured) == cf_row.output_payload_sha256
    # And the planner really received a belief derived from it.
    belief = recorder.captured["ciav_operator_belief"]
    assert belief is not None
    assert recorder.calls["ciav_planner"] == 1


def test_a_cf_bocpd_upstream_intervention_propagates_into_ciavs_actual_input() -> None:
    """Propagation, measured on the object CIAV actually receives.

    The intervention is a real algorithmic input -- the transition's unresolved
    mass and actor prior, which the cause filter consumes -- not a swapped
    operator.  The comparison is between the two runs' captured CIAV inputs.
    """

    baseline_probe = BackboneWiringProbe.build(seed=7)
    baseline_transition = baseline_probe.transition_for(baseline_probe.observed_days()[0])
    _, _, baseline = _direct_p5_with_capture(baseline_probe, baseline_transition)

    perturbed_probe = BackboneWiringProbe.build(seed=7)
    perturbed_transition = perturbed_probe.transition_for(
        perturbed_probe.observed_days()[0],
        unresolved_probability=0.45,
        actor_prior={"owner": 0.4, "guest": 0.15, "unknown_actor": 0.45},
    )
    _, _, perturbed = _direct_p5_with_capture(perturbed_probe, perturbed_transition)

    baseline_snapshot = baseline.captured["ciav_operator_snapshot"]
    perturbed_snapshot = perturbed.captured["ciav_operator_snapshot"]
    assert content_sha256(baseline_snapshot) != content_sha256(perturbed_snapshot)
    assert content_sha256(baseline.captured["ciav_operator_belief"]) != content_sha256(
        perturbed.captured["ciav_operator_belief"]
    )
    # The executor's own received arguments moved too, not only the belief.
    assert content_sha256(
        baseline.captured["ciav_executor_algorithmic_input"]["actor_prior"]
    ) != content_sha256(perturbed.captured["ciav_executor_algorithmic_input"]["actor_prior"])

    # Null control: the same run repeated without the intervention reproduces the
    # captured input exactly, so the difference above is the intervention's.
    control_probe = BackboneWiringProbe.build(seed=7)
    control_transition = control_probe.transition_for(control_probe.observed_days()[0])
    _, _, control = _direct_p5_with_capture(control_probe, control_transition)
    assert content_sha256(control.captured["ciav_operator_snapshot"]) == content_sha256(
        baseline_snapshot
    )


def test_a_ciav_likelihood_intervention_moves_the_executors_own_input() -> None:
    """CIAV's own algorithmic input, with an explicit null control."""

    baseline_probe = BackboneWiringProbe.build(seed=7)
    baseline_transition = baseline_probe.transition_for(baseline_probe.observed_days()[0])
    _, _, baseline = _direct_p5_with_capture(baseline_probe, baseline_transition)

    perturbed_probe = BackboneWiringProbe.build(seed=7)
    perturbed_transition = perturbed_probe.transition_for(perturbed_probe.observed_days()[0])
    _, _, perturbed = _direct_p5_with_capture(
        perturbed_probe, perturbed_transition, owner_likelihood=0.55
    )

    baseline_likelihoods = baseline.captured["ciav_executor_algorithmic_input"][
        "actor_likelihoods_by_outcome"
    ]
    perturbed_likelihoods = perturbed.captured["ciav_executor_algorithmic_input"][
        "actor_likelihoods_by_outcome"
    ]
    assert content_sha256(baseline_likelihoods) != content_sha256(perturbed_likelihoods)

    control_probe = BackboneWiringProbe.build(seed=7)
    control_transition = control_probe.transition_for(control_probe.observed_days()[0])
    _, _, control = _direct_p5_with_capture(control_probe, control_transition)
    assert content_sha256(
        control.captured["ciav_executor_algorithmic_input"]["actor_likelihoods_by_outcome"]
    ) == content_sha256(baseline_likelihoods)


# ---------------------------------------------------------------------------
# the matrix itself
# ---------------------------------------------------------------------------


def _run_lane(
    lane: str,
    *,
    transition_overrides: dict[str, Any] | None = None,
    ciav_overrides: dict[str, Any] | None = None,
    build_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One full formal-lane step, reporting every evidence class separately."""

    probe = BackboneWiringProbe.build(seed=7, **(build_overrides or {}))
    transition = probe.transition_for(probe.observed_days()[0], **(transition_overrides or {}))
    ciav_input = probe.ciav_input(
        transition,
        outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION,
        **(ciav_overrides or {}),
    )
    if lane == "debt_replay":
        probe.run_adaptive(
            transition,
            ciav_input=ciav_input,
            features=_p0_features(probe),
            debt_expiry_steps=20,
        )
        debt = probe.system.pending_adaptive_debts()[0]
        with RuntimeCallRecorder(probe.system) as recorder:
            _, sink = probe.replay_debt(debt.debt_id, ciav_input=ciav_input)
    else:
        with RuntimeCallRecorder(probe.system) as recorder:
            _, sink = probe.run_direct_p5(transition, ciav_input=ciav_input)
    _, rows = verify_and_flatten(sink)
    # The primary pass only.  A ``feedback_closure`` phase re-runs several
    # operators on the CIAV-derived transition, and its payloads carry the
    # per-run revision identifiers, so keeping the first (primary) receipt per
    # operator is what makes the null control meaningful at all.
    receipts: dict[str, Any] = {}
    for row in rows:
        if row.status == "executed" and row.operator not in receipts:
            receipts[row.operator] = row
    return {
        "runtime_calls": dict(recorder.calls),
        "phases": tuple(sorted({row.phase for row in rows})),
        "receipted_operators": tuple(sorted(receipts)),
        "operator_outputs": {name: row.output_payload_sha256 for name, row in receipts.items()},
        "operator_inputs": {name: row.raw_input_sha256 for name, row in receipts.items()},
        "ciav_snapshot_sha256": content_sha256(recorder.captured.get("ciav_operator_snapshot")),
        "ciav_belief_sha256": content_sha256(recorder.captured.get("ciav_operator_belief")),
        "ciav_executor_algorithmic_input_sha256": content_sha256(
            recorder.captured.get("ciav_executor_algorithmic_input")
        ),
        "ciav_runtime_snapshot_is_input": recorder.captured.get(
            "runtime_cause_snapshot_is_ciav_input"
        ),
        "action_distribution_sha256": probe.action_distribution_sha256(),
        "decoded_action": str(_decoded_action(probe)),
        "committed": len(probe.system.core._committed_events),
        "quarantined": len(probe.system.core._quarantined_events),
        "propensity_weight": probe.system.core._corrector.weight_for_opportunity(
            transition.opportunity
        ).applied_weight,
    }


INTERVENTIONS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    (
        "opceu",
        "selection and detection propensities",
        {
            "transition_overrides": {
                "p_visible_given_state": 0.55,
                "p_detect_given_visible": 0.6,
            }
        },
    ),
    (
        "orrer_cheh",
        "unresolved mass and actor prior",
        {
            "transition_overrides": {
                "unresolved_probability": 0.45,
                "actor_prior": {"owner": 0.4, "guest": 0.15, "unknown_actor": 0.45},
            }
        },
    ),
    (
        "pchmp",
        "evidence subset presented to message passing",
        {"transition_overrides": {"evidence_filter": "first_only"}},
    ),
    (
        "cf_bocpd",
        "context key driving the cause filter",
        {"transition_overrides": {"context_key": "weekend_evening"}},
    ),
    (
        "ccrr",
        "confirmation window of the regime router",
        {"build_overrides": {"loop_config": PrototypeLoopConfig(confirmation_window=3)}},
    ),
    (
        "ciav",
        "actor likelihoods for the realized outcome",
        {"ciav_overrides": {"owner_likelihood": 0.55}},
    ),
)


@pytest.mark.parametrize("lane", ["direct_p5", "debt_replay"])
def test_the_formal_lane_coverage_matrix(lane: str, tmp_path: Path) -> None:
    """entry x operator x intervention x downstream x action x null control.

    Every cell records what actually moved.  A cell that does not move the decoded
    action is recorded as not moving it -- the point is to measure, not to
    manufacture an action change.  RGRC has no separate intervention row because
    on these lanes its observable effect is the write authorization already
    asserted in the R2 and R3 suites; that cell is reported as uncovered here
    rather than filled from another suite's evidence.
    """

    baseline = _run_lane(lane)
    assert baseline["runtime_calls"]["ciav_planner"] >= 1
    assert baseline["runtime_calls"]["ciav_executor"] >= 1
    assert set(STRUCTURE_TWO_OPERATOR_ORDER) <= set(baseline["receipted_operators"])

    # Null control: an identical repeat reproduces every *reproducible* quantity.
    # RGRC's and CIAV's own receipt payloads embed identifiers minted per run, so
    # they are excluded here and never used as evidence that an intervention had
    # an effect.  That non-reproducibility is the still-open
    # ``_execution_observable_state_sha256`` gap, not something this round closed.
    control = _run_lane(lane)
    for operator in ("opceu", "orrer_cheh", "pchmp", "cf_bocpd", "ccrr"):
        assert control["operator_outputs"].get(operator) == baseline["operator_outputs"].get(
            operator
        ), f"null control moved {operator}"
    for key in (
        "ciav_snapshot_sha256",
        "ciav_belief_sha256",
        "ciav_executor_algorithmic_input_sha256",
        "action_distribution_sha256",
        "decoded_action",
        "propensity_weight",
    ):
        assert control[key] == baseline[key], f"null control moved {key}"

    cells: list[dict[str, Any]] = []
    for operator, description, keywords in INTERVENTIONS:
        perturbed = _run_lane(lane, **keywords)
        cells.append(
            {
                "entry": lane,
                "operator": operator,
                "intervention": description,
                "ciav_planner_calls": perturbed["runtime_calls"]["ciav_planner"],
                "ciav_executor_calls": perturbed["runtime_calls"]["ciav_executor"],
                "own_receipt_output_changed": (
                    None
                    if operator in {"rgrc", "ciav"}
                    else perturbed["operator_outputs"].get(operator)
                    != baseline["operator_outputs"].get(operator)
                ),
                "ciav_actual_input_changed": (
                    perturbed["ciav_belief_sha256"] != baseline["ciav_belief_sha256"]
                    or perturbed["ciav_executor_algorithmic_input_sha256"]
                    != baseline["ciav_executor_algorithmic_input_sha256"]
                ),
                "ciav_runtime_snapshot_is_input": perturbed["ciav_runtime_snapshot_is_input"],
                "propensity_weight_changed": (
                    perturbed["propensity_weight"] != baseline["propensity_weight"]
                ),
                "action_distribution_changed": (
                    perturbed["action_distribution_sha256"]
                    != baseline["action_distribution_sha256"]
                ),
                "decoded_action_changed": (
                    perturbed["decoded_action"] != baseline["decoded_action"]
                ),
                "committed": perturbed["committed"],
                "quarantined": perturbed["quarantined"],
            }
        )
        # Every intervention must at least reach its own operator's receipt, or be
        # honestly recorded as not reaching it.
        assert perturbed["runtime_calls"]["ciav_planner"] >= 1

    # RGRC and the deferred-only cells stay explicitly uncovered here.
    uncovered = [
        {
            "entry": lane,
            "operator": "rgrc",
            "reason": (
                "RGRC's observable effect on this lane is the long-term write "
                "authorization, covered in the R2/R3 suites; no separate algorithmic "
                "input intervention is available without deleting the operator"
            ),
        }
    ]

    artifact = {
        "lane": lane,
        "baseline": {key: value for key, value in baseline.items() if key != "operator_inputs"},
        "cells": cells,
        "uncovered": uncovered,
    }
    output = tmp_path / f"coverage_matrix_{lane}.json"
    output.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")

    # At least one intervention must reach CIAV's real input on a formal lane,
    # otherwise "the seven operators collaborate here" is not shown.
    assert any(cell["ciav_actual_input_changed"] for cell in cells)
    # And every cell carries a real CIAV call count, so no cell can be read as a
    # complete seven-operator pass with CIAV never called.
    assert all(cell["ciav_executor_calls"] >= 1 for cell in cells)
