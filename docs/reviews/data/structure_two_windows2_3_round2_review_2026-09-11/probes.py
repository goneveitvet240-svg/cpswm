"""Independent round-2 review. No production files or retained evidence are edited.

Run with the project interpreter, passing the isolated W3 worktree as argument.
Input corruption in p0_path is deliberate fault injection, not a claim that an
external caller can normally replace a private method. The real runtime binds
the injected callable and produces/verifies its own receipts.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root / "src"), str(root / "tests")]

from structure_two_backbone_wiring_probe import (
    BackboneWiringProbe, CIAVOutcomeKind, CalibratedRetractionPolicy,
    build_execution_feedback_bundle, verify_and_flatten,
    NEGATIVE_SEARCH_OUTCOME, NEGATIVE_PRESENT_LIKELIHOOD,
    NEGATIVE_ABSENT_LIKELIHOOD,
)
from cpswm.system.reproducibility import content_sha256


def semantic(value):
    return {k: v for k, v in value.items() if not k.startswith("consumed_")}


def maintenance():
    p = BackboneWiringProbe.build(seed=7)
    c = p.system.core
    t = p.transition_for(p.observed_days()[0])
    cf = c._adaptive_cf_bocpd_safety_maintenance()
    cc = c._adaptive_ccrr_safety_maintenance(cf)
    pc = c._adaptive_pchmp_safety_maintenance(t)
    good = c._adaptive_rgrc_debt_guard(pc, cc)
    cases = []
    for label, a, b in (
        ("wrong_evidence_hashes", {**pc, "evidence_content_sha256s": ("f" * 64,)}, cc),
        ("wrong_evidence_type", {**pc, "evidence_content_sha256s": -999}, cc),
        ("wrong_cf_dependency_hash", pc, {**cc, "consumed_cf_bocpd_maintenance_sha256": "f" * 64}),
        ("wrong_cf_dependency_type", pc, {**cc, "consumed_cf_bocpd_maintenance_sha256": None}),
    ):
        try:
            result = c._adaptive_rgrc_debt_guard(a, b)
            cases.append({"case": label, "accepted": True,
                          "semantic_guard_unchanged": semantic(result) == semantic(good),
                          "receipt_changed": result != good})
        except Exception as exc:
            cases.append({"case": label, "accepted": False, "error": str(exc)})
    foreign = BackboneWiringProbe.build(seed=7).system.core._adaptive_cf_bocpd_safety_maintenance()
    cross = c._adaptive_ccrr_safety_maintenance(foreign)
    return {"cases": cases, "different_runtime_same_head_accepted": cross == cc,
            "old_malformed_counterexample_rejected": old_counterexample(c, cf)}


def old_counterexample(core, cf):
    try:
        core._adaptive_ccrr_safety_maintenance({**cf, "observation_count": -999,
             "posterior_advanced": True, "current_snapshot_sha256": "foreign"})
        return False
    except ValueError:
        return True


def injected_pchmp(self, transition):
    self._validate_transition(transition)
    return {"maintenance_kind": "pchmp_safety_maintenance",
            "evidence_content_sha256s": ("f" * 64,),
            "unexecuted_inference_encoded_as_negative": False,
            "message_passing_runtime_type":
                f"{type(self._message_passing).__module__}.{type(self._message_passing).__qualname__}"}


def p0_path():
    p = BackboneWiringProbe.build(seed=7)
    cls = type(p.system.core)
    original = cls._adaptive_pchmp_safety_maintenance
    cls._adaptive_pchmp_safety_maintenance = injected_pchmp
    t = p.transition_for(p.observed_days()[0])
    try:
        result, sink = p.run_adaptive(t, features=p.router_features(action_margin=0.9, regime_hazard=0.0))
        _, rows = verify_and_flatten(sink)
        return {"accepted": True, "path": result.path_selection.selected_path_id,
                "verified_operator_rows": len(rows),
                "pending_debts": len(p.system.pending_adaptive_debts()),
                "committed": len(p.system.core._committed_events),
                "expected_evidence_hashes": [content_sha256(e) for e in t.evidence],
                "injected_evidence_hashes": ["f" * 64]}
    except Exception as exc:
        return {"accepted": False, "error_type": type(exc).__name__, "error": str(exc)}
    finally:
        cls._adaptive_pchmp_safety_maintenance = original


def history(adaptive):
    p = BackboneWiringProbe.build(seed=7)
    for observation in p.observed_days()[:10 if adaptive else 12]:
        t = p.transition_for(observation)
        if adaptive:
            p.run_direct_p5(t, ciav_input=p.ciav_input(t, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION))
        else:
            p.system.core.process_transition(t)
    return p


def feedback(p, revision):
    e = p.system.core._committed_events[revision]
    return build_execution_feedback_bundle(p, revision_id=revision, location_id=e.location_id,
        belief_snapshot_id=e.belief_snapshot_id, when=e.evidence.event_time,
        opportunity_id=e.evidence.observation_opportunity_id,
        outcome_distribution=NEGATIVE_SEARCH_OUTCOME,
        present_likelihood=NEGATIVE_PRESENT_LIKELIHOOD,
        absent_likelihood=NEGATIVE_ABSENT_LIKELIHOOD)


def apply(p, bundle):
    f, b, l = bundle
    return p.system.process_execution_feedback(feedback=f, binding=b, likelihood_model=l,
                                              policy=CalibratedRetractionPolicy())


def formal_revision():
    p = history(True)
    c = p.system.core
    before = set(c._committed_events)
    quarantined = {e.revision_id for e in c._quarantined_events}
    alpha_before = sum(c.hybrid_alpha(loc) for loc in p.case.locations)
    target = next(iter(c._committed_events))
    target_weight = c._committed_events[target].statistical_owner_weight
    result = apply(p, feedback(p, target))
    new = set(c._committed_events) - before
    return {"operations": [s.value for s in result.statistic_operations],
            "before_committed": len(before), "after_committed": len(c._committed_events),
            "before_quarantined": len(quarantined), "after_quarantined": len(c._quarantined_events),
            "newly_committed": len(new), "all_new_were_quarantined": new <= quarantined,
            "target_removed": target not in c._committed_events,
            "alpha_before": alpha_before, "target_weight": target_weight,
            "alpha_after": sum(c.hybrid_alpha(loc) for loc in p.case.locations),
            "hybrid_internal_rerun_equivalent": c.verify_hybrid_full_rerun_equivalence().equivalent}


def delayed_feedback():
    p = history(False)
    c = p.system.core
    first, second = list(c._committed_events)[:2]
    # Prepare both genuine, individually valid bindings before any revision.
    first_bundle, delayed = feedback(p, first), feedback(p, second)
    bound_before = c._validate_feedback_revision_binding(feedback=delayed[0], binding=delayed[1])
    old_snapshot = c._committed_events[second].belief_snapshot_id
    apply(p, first_bundle)
    new_snapshot = c._committed_events[second].belief_snapshot_id
    try:
        apply(p, delayed)
        outcome = {"accepted": True}
    except Exception as exc:
        outcome = {"accepted": False, "error_type": type(exc).__name__, "error": str(exc)}
    return {"valid_before_unrelated_retraction": bound_before == second,
            "target_still_committed": second in c._committed_events,
            "original_binding_replaced": old_snapshot != new_snapshot, **outcome}


def pending_debt_control():
    p = history(False)
    first = next(iter(p.system.core._committed_events))
    bundle = feedback(p, first)
    t = p.transition_for(p.observed_days()[12])
    p.run_adaptive(t, features=p.router_features(action_margin=0.9, regime_hazard=0.0))
    before = set(p.system.core._committed_events)
    try:
        apply(p, bundle)
        return {"blocked": False}
    except RuntimeError as exc:
        return {"blocked": True, "error": str(exc),
                "committed_unchanged": before == set(p.system.core._committed_events),
                "pending_debts": len(p.system.pending_adaptive_debts())}


def ciav_runtime_calls():
    from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig
    result = {}
    for name, direct, window in (("legacy_window_2", False, 2),
                                  ("legacy_window_3", False, 3),
                                  ("direct_p5_control", True, 2)):
        p = BackboneWiringProbe.build(seed=7, loop_config=PrototypeLoopConfig(confirmation_window=window))
        codes = {
            p.system.cause_information_planner.select.__func__.__code__: "planner",
            p.system.ciav_opceu_loop.execute_selected_action.__func__.__code__: "executor",
        }
        counts = {"planner": 0, "executor": 0}
        def profile(frame, event, arg):
            if event == "call" and frame.f_code in codes:
                counts[codes[frame.f_code]] += 1
        sys.setprofile(profile)
        try:
            for observation in p.observed_days()[:1 if direct else 18]:
                t = p.transition_for(observation)
                if direct:
                    p.run_direct_p5(t)
                else:
                    p.system.core.process_transition(t)
        finally:
            sys.setprofile(None)
        result[name] = counts
    return result


print(json.dumps({"maintenance": maintenance(), "injected_p0_path": p0_path(),
                  "formal_revision": formal_revision(), "delayed_feedback": delayed_feedback(),
                  "pending_debt_control": pending_debt_control(),
                  "ciav_runtime_calls": ciav_runtime_calls()}, indent=2))
