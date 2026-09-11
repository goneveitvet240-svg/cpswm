"""Window-3 round-3 evidence generator.

Re-runs the round-2 independent review's own counterexamples against this round's
source, plus fresh legal direct-P5 and debt-replay passes, and writes one JSON
artifact.  Run with the project interpreter from the worktree root:

    .venv/bin/python docs/reviews/data/structure_two_window3_round3_2026-09-11/round3_evidence.py .

Nothing here is a scientific gate result.  No historical artifact is edited.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
sys.path[:0] = [str(root / "src"), str(root / "tests")]

from structure_two_backbone_wiring_probe import (  # noqa: E402
    NEGATIVE_ABSENT_LIKELIHOOD,
    NEGATIVE_PRESENT_LIKELIHOOD,
    NEGATIVE_SEARCH_OUTCOME,
    BackboneWiringProbe,
    CalibratedRetractionPolicy,
    CIAVOutcomeKind,
    ProbeTraceSink,
    RuntimeCallRecorder,
    build_execution_feedback_bundle,
    verify_and_flatten,
)

from cpswm.system import structure_two_execution  # noqa: E402
from cpswm.system.prototype_spine import CorePrototypeSpine  # noqa: E402
from cpswm.system.reproducibility import content_sha256  # noqa: E402


def semantic(value):
    stamp = {"runtime_execution_id", "maintenance_epoch"}
    return {k: v for k, v in value.items() if not k.startswith("consumed_") and k not in stamp}


def p0_features(probe):
    return probe.router_features(action_margin=0.9, regime_hazard=0.0)


# ---------------------------------------------------------------------------
# R2
# ---------------------------------------------------------------------------


def maintenance():
    """The review's four wrong payloads and its cross-runtime substitution."""

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    transition = probe.transition_for(probe.observed_days()[0])
    cases = []
    with probe.maintenance_context(transition):
        cf = core._adaptive_cf_bocpd_safety_maintenance()
        cc = core._adaptive_ccrr_safety_maintenance(cf)
        pc = core._adaptive_pchmp_safety_maintenance(transition)
        good = core._adaptive_rgrc_debt_guard(pc, cc)
        for label, a, b in (
            ("wrong_evidence_hashes", {**pc, "evidence_content_sha256s": ("f" * 64,)}, cc),
            ("wrong_evidence_type", {**pc, "evidence_content_sha256s": -999}, cc),
            (
                "wrong_cf_dependency_hash",
                pc,
                {**cc, "consumed_cf_bocpd_maintenance_sha256": "f" * 64},
            ),
            (
                "wrong_cf_dependency_type",
                pc,
                {**cc, "consumed_cf_bocpd_maintenance_sha256": None},
            ),
        ):
            try:
                result = core._adaptive_rgrc_debt_guard(a, b)
                cases.append(
                    {
                        "case": label,
                        "accepted": True,
                        "semantic_guard_unchanged": semantic(result) == semantic(good),
                    }
                )
            except Exception as exc:
                cases.append({"case": label, "accepted": False, "error": str(exc)})

    # Two freshly built runtimes at the same head state.
    source = BackboneWiringProbe.build(seed=7)
    target = BackboneWiringProbe.build(seed=7)
    source_transition = source.transition_for(source.observed_days()[0])
    target_transition = target.transition_for(target.observed_days()[0])
    with source.maintenance_context(source_transition):
        foreign = source.system.core._adaptive_cf_bocpd_safety_maintenance()
    with target.maintenance_context(target_transition):
        native = target.system.core._adaptive_cf_bocpd_safety_maintenance()
        heads_identical = semantic(foreign) == semantic(native)
        try:
            target.system.core._adaptive_ccrr_safety_maintenance(foreign)
            cross = {"accepted": True}
        except Exception as exc:
            cross = {"accepted": False, "error": str(exc)}
    return {
        "cases": cases,
        "different_runtime_same_head": {"semantic_heads_identical": heads_identical, **cross},
    }


def injected_pchmp(self, transition):
    self._validate_transition(transition)
    return {
        "maintenance_kind": "pchmp_safety_maintenance",
        "evidence_content_sha256s": ("f" * 64,),
        "unexecuted_inference_encoded_as_negative": False,
        "message_passing_runtime_type": (
            f"{type(self._message_passing).__module__}.{type(self._message_passing).__qualname__}"
        ),
    }


def injected_unrecorded_pchmp(self, transition):
    context = self._adaptive_maintenance_context
    self._validate_transition(transition)
    return {
        "maintenance_kind": "pchmp_safety_maintenance",
        "runtime_execution_id": str(context.runtime_execution_id),
        "maintenance_epoch": context.epoch,
        "evidence_content_sha256s": context.evidence_content_sha256s,
        "unexecuted_inference_encoded_as_negative": False,
        "message_passing_runtime_type": context.message_passing_runtime_type,
    }


def p0_path(injection, *, disable_binding_layer):
    probe = BackboneWiringProbe.build(seed=7)
    cls = type(probe.system.core)
    original = cls._adaptive_pchmp_safety_maintenance
    guard = structure_two_execution._require_declared_implementation_member
    cls._adaptive_pchmp_safety_maintenance = injection
    if disable_binding_layer:
        structure_two_execution._require_declared_implementation_member = lambda **_: None
    transition = probe.transition_for(probe.observed_days()[0])
    sink = ProbeTraceSink()
    before_committed = len(probe.system.core._committed_events)
    try:
        result, sink = probe.run_adaptive(
            transition, features=p0_features(probe), debt_expiry_steps=1, sink=sink
        )
        _, rows = verify_and_flatten(sink)
        return {
            "accepted": True,
            "path": result.path_selection.selected_path_id,
            "verified_operator_rows": len(rows),
            "pending_debts": len(probe.system.pending_adaptive_debts()),
            "committed": len(probe.system.core._committed_events),
        }
    except Exception as exc:
        return {
            "accepted": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "committed_trace": sink.trace is not None,
            "pending_debts": len(probe.system.pending_adaptive_debts()),
            "committed_unchanged": len(probe.system.core._committed_events) == before_committed,
            "maintenance_context_open": (
                probe.system.core._adaptive_maintenance_context is not None
            ),
        }
    finally:
        cls._adaptive_pchmp_safety_maintenance = original
        structure_two_execution._require_declared_implementation_member = guard


def legal_p0():
    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    result, sink = probe.run_adaptive(transition, features=p0_features(probe), debt_expiry_steps=1)
    _, rows = verify_and_flatten(sink)
    return {
        "path": result.path_selection.selected_path_id,
        "verified_operator_rows": len(rows),
        "executed": sorted(row.operator for row in rows if row.status == "executed"),
        "deferred": sorted(row.operator for row in rows if row.status != "executed"),
        "pending_debts": len(probe.system.pending_adaptive_debts()),
        "committed": len(probe.system.core._committed_events),
    }


# ---------------------------------------------------------------------------
# R3
# ---------------------------------------------------------------------------


def adaptive_history(days=10):
    probe = BackboneWiringProbe.build(seed=7)
    for observation in probe.observed_days()[:days]:
        transition = probe.transition_for(observation)
        probe.run_direct_p5(
            transition,
            ciav_input=probe.ciav_input(
                transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION
            ),
        )
    return probe


def legacy_history(days=12):
    probe = BackboneWiringProbe.build(seed=7)
    for observation in probe.observed_days()[:days]:
        probe.system.core.process_transition(probe.transition_for(observation))
    return probe


def feedback(probe, revision, **overrides):
    event = probe.system.core._committed_events[revision]
    arguments = {
        "revision_id": revision,
        "location_id": event.location_id,
        "belief_snapshot_id": event.belief_snapshot_id,
        "when": event.evidence.event_time,
        "opportunity_id": event.evidence.observation_opportunity_id,
        "outcome_distribution": NEGATIVE_SEARCH_OUTCOME,
        "present_likelihood": NEGATIVE_PRESENT_LIKELIHOOD,
        "absent_likelihood": NEGATIVE_ABSENT_LIKELIHOOD,
    }
    arguments.update(overrides)
    return build_execution_feedback_bundle(probe, **arguments)


def apply_feedback(probe, bundle):
    f, b, likelihood = bundle
    return probe.system.process_execution_feedback(
        feedback=f, binding=b, likelihood_model=likelihood, policy=CalibratedRetractionPolicy()
    )


def formal_revision(target_kind):
    probe = adaptive_history()
    core = probe.system.core
    before = set(core._committed_events)
    quarantined = {event.revision_id for event in core._quarantined_events}
    blocked = {
        revision_id
        for revision_id in core._observed_events
        if core.observation_write_eligibility(revision_id)["origin_write_blocked"]
    }
    alpha_before = sum(core.hybrid_alpha(loc) for loc in probe.case.locations)
    if target_kind == "first_committed":
        target = next(iter(core._committed_events))
    else:
        location = max(probe.case.locations, key=core.hybrid_alpha)
        target = next(
            key
            for key, event in core._committed_events.items()
            if event.location_id == location and event.belief_snapshot_id is not None
        )
    result = apply_feedback(probe, feedback(probe, target))
    new = set(core._committed_events) - before
    return {
        "target_kind": target_kind,
        "operations": [item.value for item in result.statistic_operations],
        "before_committed": len(before),
        "after_committed": len(core._committed_events),
        "before_quarantined": len(quarantined),
        "after_quarantined": len(core._quarantined_events),
        "newly_committed": len(new),
        "newly_committed_were_write_blocked": len(new & blocked),
        "committed_with_blocked_origin": sum(
            1
            for revision_id in core._committed_events
            if (record := core.observation_write_eligibility(revision_id))
            and record["origin_write_blocked"]
        ),
        "blocked_still_quarantined": len(
            blocked & {event.revision_id for event in core._quarantined_events}
        ),
        "target_removed": target not in core._committed_events,
        "alpha_before": alpha_before,
        "alpha_after": sum(core.hybrid_alpha(loc) for loc in probe.case.locations),
        "hybrid_internal_rerun_equivalent": core.verify_hybrid_full_rerun_equivalence().equivalent,
        "promotion_authorities": sorted(
            {
                grant["authority"]
                for revision_id in new
                for grant in core.observation_write_eligibility(revision_id)["authorizations"]
            }
        ),
    }


def prefix_behaviour(target_kind):
    """Reproduce the PRE-repair behaviour on this same source.

    The repair is one gate: ``_observation_write_eligible``.  Neutralising just
    that gate -- and nothing else -- reproduces exactly what the round-2 review and
    the window-3 round-1 report measured, on the current source, so the two sets of
    numbers are comparable rather than quoted from different trees.
    """

    original = CorePrototypeSpine._observation_write_eligible
    CorePrototypeSpine._observation_write_eligible = lambda self, revision_id: True
    try:
        return formal_revision(target_kind)
    finally:
        CorePrototypeSpine._observation_write_eligible = original


def delayed_feedback():
    probe = legacy_history()
    core = probe.system.core
    first, second = list(core._committed_events)[:2]
    first_bundle, delayed = feedback(probe, first), feedback(probe, second)
    bound_before = core._validate_feedback_revision_binding(feedback=delayed[0], binding=delayed[1])
    old_snapshot = core._committed_events[second].belief_snapshot_id
    apply_feedback(probe, first_bundle)
    new_snapshot = core._committed_events[second].belief_snapshot_id
    try:
        result = apply_feedback(probe, delayed)
        outcome = {
            "accepted": True,
            "operations": [item.value for item in result.statistic_operations],
        }
    except Exception as exc:
        outcome = {"accepted": False, "error_type": type(exc).__name__, "error": str(exc)}
    relocations = core.late_feedback_relocations
    # Negative control: another revision's published snapshot must still fail.
    foreign_probe = legacy_history()
    foreign_core = foreign_probe.system.core
    a, b = list(foreign_core._committed_events)[:2]
    try:
        apply_feedback(
            foreign_probe,
            feedback(
                foreign_probe,
                b,
                belief_snapshot_id=foreign_core._committed_events[a].belief_snapshot_id,
            ),
        )
        foreign = {"accepted": True}
    except Exception as exc:
        foreign = {"accepted": False, "error": str(exc)}
    return {
        "valid_before_unrelated_retraction": bound_before == second,
        "original_binding_replaced": old_snapshot != new_snapshot,
        "published_binding_count": len(core.published_revision_bindings(second)),
        **outcome,
        "relocations_recorded": len(relocations),
        "relocation": (
            {
                "presented_map_version": relocations[0].presented_map_version,
                "current_map_version": relocations[0].current_map_version,
            }
            if relocations
            else None
        ),
        "foreign_snapshot_control": foreign,
    }


def pending_debt_control():
    probe = legacy_history()
    core = probe.system.core
    bundle = feedback(probe, next(iter(core._committed_events)))
    transition = probe.transition_for(probe.observed_days()[12])
    probe.run_adaptive(transition, features=p0_features(probe))
    before = set(core._committed_events)
    try:
        apply_feedback(probe, bundle)
        return {"blocked": False}
    except RuntimeError as exc:
        return {
            "blocked": True,
            "error": str(exc),
            "committed_unchanged": before == set(core._committed_events),
            "pending_debts": len(probe.system.pending_adaptive_debts()),
        }


# ---------------------------------------------------------------------------
# R4
# ---------------------------------------------------------------------------


def runtime_calls():
    from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig

    result = {}
    for name, window in (("legacy_window_2", 2), ("legacy_window_3", 3)):
        probe = BackboneWiringProbe.build(
            seed=7, loop_config=PrototypeLoopConfig(confirmation_window=window)
        )
        with RuntimeCallRecorder(probe.system) as recorder:
            for observation in probe.observed_days()[:18]:
                probe.system.core.process_transition(probe.transition_for(observation))
        result[name] = dict(recorder.calls)

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    ciav_input = probe.ciav_input(transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION)
    with RuntimeCallRecorder(probe.system) as recorder:
        _, sink = probe.run_direct_p5(transition, ciav_input=ciav_input)
    _, rows = verify_and_flatten(sink)
    cf_row = next(
        row
        for row in rows
        if row.operator == "cf_bocpd" and row.status == "executed" and row.phase == "selected_path"
    )
    result["direct_p5"] = {
        **dict(recorder.calls),
        "verified_rows": len(rows),
        "ciav_input_is_runtime_cause_snapshot": recorder.captured[
            "runtime_cause_snapshot_is_ciav_input"
        ],
        "ciav_input_sha256_equals_cf_receipt": (
            content_sha256(recorder.captured["ciav_operator_snapshot"])
            == cf_row.output_payload_sha256
        ),
    }

    probe = BackboneWiringProbe.build(seed=7)
    transition = probe.transition_for(probe.observed_days()[0])
    ciav_input = probe.ciav_input(transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION)
    probe.run_adaptive(
        transition, ciav_input=ciav_input, features=p0_features(probe), debt_expiry_steps=20
    )
    debt = probe.system.pending_adaptive_debts()[0]
    with RuntimeCallRecorder(probe.system) as recorder:
        _, sink = probe.replay_debt(debt.debt_id, ciav_input=ciav_input)
    _, rows = verify_and_flatten(sink)
    result["debt_replay"] = {**dict(recorder.calls), "verified_rows": len(rows)}
    return result


if __name__ == "__main__":
    payload = {
        "r2_maintenance": maintenance(),
        "r2_legal_p0": legal_p0(),
        "r2_injected_p0_binding_layer": p0_path(injected_pchmp, disable_binding_layer=False),
        "r2_injected_p0_context_layer": p0_path(injected_pchmp, disable_binding_layer=True),
        "r2_injected_p0_perfect_payload": p0_path(
            injected_unrecorded_pchmp, disable_binding_layer=True
        ),
        "r3_prerepair_first_committed": prefix_behaviour("first_committed"),
        "r3_prerepair_majority_location": prefix_behaviour("majority_location"),
        "r3_formal_revision_first_committed": formal_revision("first_committed"),
        "r3_formal_revision_majority_location": formal_revision("majority_location"),
        "r3_delayed_feedback": delayed_feedback(),
        "r3_pending_debt_control": pending_debt_control(),
        "r4_runtime_calls": runtime_calls(),
    }
    print(json.dumps(payload, indent=2, default=str))
