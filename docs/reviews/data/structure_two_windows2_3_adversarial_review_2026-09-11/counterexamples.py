"""Independent review probes. No production or retained artifacts are changed."""
from __future__ import annotations

import copy
import gzip
import importlib.util
import json
from pathlib import Path
import sys
import tempfile


root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root / "src"), str(root / "tests")]
mode = sys.argv[2]


def top(dist):
    return str(min(dist, key=lambda k: (-dist[k], str(k))))


if mode == "w3":
    from structure_two_backbone_wiring_probe import BackboneWiringProbe, CIAVOutcomeKind
    from cpswm.system.evaluation_operations.structure_two_p5_readout_posthoc_diagnostic import selected_v0_6_action_readout
    from cpswm.system.reproducibility import content_sha256

    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    transition = probe.transition_for(probe.observed_days()[0])
    clean = core._adaptive_cf_bocpd_safety_maintenance()
    bad = dict(clean, observation_count=-999, posterior_advanced=True, current_snapshot_sha256="foreign")
    a = core._adaptive_ccrr_safety_maintenance(clean)
    b = core._adaptive_ccrr_safety_maintenance(bad)
    semantic = lambda value: {k: v for k, v in value.items() if not k.startswith("consumed_")}
    pa = core._adaptive_pchmp_safety_maintenance(transition)
    ga = core._adaptive_rgrc_debt_guard(pa, a)
    gb = core._adaptive_rgrc_debt_guard({"unexecuted_inference_encoded_as_negative": True}, b)
    out = {"p0": {
        "invalid_upstream_payload_accepted": True,
        "ccrr_receipt_changed": a != b,
        "ccrr_semantic_output_unchanged": semantic(a) == semantic(b),
        "rgrc_receipt_changed": ga != gb,
        "rgrc_semantic_output_unchanged": semantic(ga) == semantic(gb),
        "ccrr_semantic_output": semantic(a),
        "rgrc_semantic_output": semantic(ga),
    }}

    # Replay the report's own S8 setup and inspect every affected representation.
    probe = BackboneWiringProbe.build(seed=7)
    core = probe.system.core
    for observation in probe.observed_days()[:12]:
        core.process_transition(probe.transition_for(observation))
    target = core._committed_events[next(reversed(core._committed_events))]
    revision = target.hybrid_revision_id or target.revision_id
    before = probe.action_distribution()
    habit_before = core._habit.canonical_state_hash()
    fast_before = repr(core._fast_action_events)
    event_count_before = len(core._committed_events)
    core._hybrid_loop.retract_revision(revision)
    after = probe.action_distribution()
    out["s8_retraction"] = {
        "distribution_changed": before != after,
        "typed_put_back_top1_changed": top(before) != top(after),
        "before_top1": top(before), "after_top1": top(after),
        "hybrid_live_records_after": len(core._hybrid_loop.ledger.live_promoted_records_for_revision(revision)),
        "hybrid_full_rerun_equivalent": core.verify_hybrid_full_rerun_equivalence().equivalent,
        "committed_events_before": event_count_before,
        "committed_events_after": len(core._committed_events),
        "target_still_in_committed_events": target.revision_id in core._committed_events,
        "dirichlet_state_unchanged": habit_before == core._habit.canonical_state_hash(),
        "fast_event_state_unchanged": fast_before == repr(core._fast_action_events),
    }

    # S4 must be judged by an actual decision, not just posterior bytes.
    actions = []
    for likelihood in [None, 0.95, 0.05]:
        probe = BackboneWiringProbe.build(seed=7, action_readout=selected_v0_6_action_readout())
        days = probe.observed_days()
        for day in days[:4]:
            t = probe.transition_for(day)
            probe.run_direct_p5(t, ciav_input=probe.ciav_input(t, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION))
        t = probe.transition_for(days[4])
        kind = CIAVOutcomeKind.NOT_DETECTED if likelihood is None else CIAVOutcomeKind.DETECTED_SAME_LOCATION
        kwargs = {} if likelihood is None else {"owner_likelihood": likelihood}
        result, _ = probe.run_direct_p5(t, ciav_input=probe.ciav_input(t, outcome=kind, **kwargs))
        actions.append({"likelihood": likelihood, "top1": top(probe.action_distribution()), "distribution": {str(k): v for k,v in probe.action_distribution().items()}})
    out["s4"] = actions

    probe = BackboneWiringProbe.build(seed=7)
    t = probe.transition_for(probe.observed_days()[0])
    result, _ = probe.run_direct_p5(t, ciav_input=probe.ciav_input(t, outcome=CIAVOutcomeKind.NOT_DETECTED))
    out["negative_ciav"] = {
        "primary_owner": result.primary_result.actor_posterior[probe.case.owner_actor],
        "ciav_owner": result.ciav_receipt.evidence.actor_posterior[probe.case.owner_actor],
        "recorded_target": result.ciav_receipt.consumed_factor.target_distribution_id,
        "factor_consumed": result.ciav_receipt.consumed_factor.consumed_as_likelihood,
        "fast_verification": result.fast_verification_receipt is not None,
        "feedback_result": result.feedback_result is not None,
    }
    print(json.dumps(out, indent=2, sort_keys=True))

elif mode == "w2":
    from cpswm.system.evaluation_operations import structure_two_comparison_audit as audit
    from cpswm.system.reproducibility import content_sha256
    module_path = root / "apps/evaluation_runner/summarize_structure_two_comparison_audit.py"
    spec = importlib.util.spec_from_file_location("attribution_review", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bundle = root / "docs/reviews/data/structure_two_comparison_audit_window2_2026-09-11"
    original = json.loads((bundle / "audit.json").read_text())
    original_rows = [json.loads(line) for line in gzip.decompress((bundle / "steps.jsonl.gz").read_bytes()).splitlines()]
    forged = copy.deepcopy(original)
    forged_rows = copy.deepcopy(original_rows)
    for row in forged_rows:
        row["raw_state"]["p5_readouts"]["state_counts"]["_committed_events"] = 999
    forged["semantic_steps_sha256"] = content_sha256(audit._semantic_rows(forged_rows))
    with tempfile.TemporaryDirectory(prefix="s2-attribution-forgery-", dir="/private/tmp") as folder:
        target = Path(folder)
        (target / "audit.json").write_text(json.dumps(forged))
        raw = b"\n".join(json.dumps(row).encode() for row in forged_rows)
        (target / "steps.jsonl.gz").write_bytes(gzip.compress(raw))
        invented = module.analyze(target, root)
        (target / "attribution.json").write_text(json.dumps(invented))
        # Exercise the exact standalone --verify entrypoint.
        sys.argv = [str(module_path), "--bundle", str(target), "--verify"]
        module.main()
        rejected = None
        try:
            audit.verify(target, original, original_rows)
        except ValueError as exc:
            rejected = str(exc)
        print(json.dumps({
            "standalone_attribution_verify_accepted_forged_state_counts": True,
            "invented_commit_histogram": invented["p5_state_count_histograms"]["_committed_events"],
            "full_audit_verifier_rejected": rejected,
            "original_artifacts_unchanged": True,
        }, indent=2))
else:
    raise ValueError(mode)

