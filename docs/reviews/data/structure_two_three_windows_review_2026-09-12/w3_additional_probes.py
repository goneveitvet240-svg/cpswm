"""Independent public-feedback/state-transition probes; no production mutation."""
from __future__ import annotations
import json
from pathlib import Path
import sys
from uuid import uuid4

root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root / "src"), str(root / "tests")]
from structure_two_backbone_wiring_probe import (
    BackboneWiringProbe, CalibratedRetractionPolicy, CIAVOutcomeKind,
    build_execution_feedback_bundle, NEGATIVE_SEARCH_OUTCOME,
    NEGATIVE_PRESENT_LIKELIHOOD, NEGATIVE_ABSENT_LIKELIHOOD,
)


def bundle(p, revision):
    e = p.system.core._committed_events[revision]
    return build_execution_feedback_bundle(
        p, revision_id=revision, location_id=e.location_id,
        belief_snapshot_id=e.belief_snapshot_id, when=e.evidence.event_time,
        opportunity_id=e.evidence.observation_opportunity_id,
        outcome_distribution=NEGATIVE_SEARCH_OUTCOME,
        present_likelihood=NEGATIVE_PRESENT_LIKELIHOOD,
        absent_likelihood=NEGATIVE_ABSENT_LIKELIHOOD)


def apply(p, revision, *, corrected=None):
    f, b, l = bundle(p, revision)
    return p.system.process_execution_feedback(
        feedback=f, binding=b, likelihood_model=l,
        policy=CalibratedRetractionPolicy(corrected_location_id=corrected))


def correction(same_location, direct_p5=False):
    p = BackboneWiringProbe.build(seed=7)
    c = p.system.core
    for day in p.observed_days()[:10 if direct_p5 else 12]:
        transition = p.transition_for(day)
        if direct_p5:
            p.run_direct_p5(transition, ciav_input=p.ciav_input(
                transition, outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION))
        else:
            c.process_transition(transition)
    target = next(iter(c._committed_events))
    old = c._committed_events[target]
    location = old.location_id if same_location else next(x for x in p.case.locations if x != old.location_id)
    observed = set(c._observed_events)
    before_count = len(c._committed_events)
    r = apply(p, target, corrected=location)
    new = set(c._observed_events) - observed
    records = []
    for rid in new:
        records.append({"in_committed":rid in c._committed_events,
            "in_quarantine":rid in {e.revision_id for e in c._quarantined_events},
            "eligibility":c.observation_write_eligibility(rid) if hasattr(c,"observation_write_eligibility") else "not_implemented",
            "hybrid_live_records":len(c._hybrid_loop.ledger.live_promoted_records_for_revision(rid)),
            "location_matches":c._observed_events[rid].location_id==location})
    return {"same_location":same_location,"history_path":"direct_p5" if direct_p5 else "legacy",
        "operations":[x.value for x in r.statistic_operations],
        "before_committed":before_count,"after_committed":len(c._committed_events),
        "old_target_removed":target not in c._committed_events,"new_revisions":records,
        "hybrid_equivalent":c.verify_hybrid_full_rerun_equivalence().equivalent}


def blocked_grants():
    p = BackboneWiringProbe.build(seed=7)
    c = p.system.core
    if not hasattr(c,"observation_write_eligibility"):
        return {"available":False}
    result = []
    for index,day in enumerate(p.observed_days()):
        t=p.transition_for(day)
        p.run_direct_p5(t,ciav_input=p.ciav_input(t,outcome=CIAVOutcomeKind.DETECTED_DIFFERENT_LOCATION))
        with_grant={rid:c.observation_write_eligibility(rid) for rid in c._observed_events
                    if c.observation_write_eligibility(rid)["origin_write_blocked"]
                    and c.observation_write_eligibility(rid)["authorizations"]}
        result.append({"day":index+1,"blocked_with_grant":len(with_grant),
                       "committed":len(c._committed_events),"quarantined":len(c._quarantined_events)})
        if with_grant:
            grant_ids={g["granting_revision_id"] for rec in with_grant.values() for g in rec["authorizations"]
                       if g["granting_revision_id"]}
            target=next((rid for rid in c._committed_events if str(rid) in grant_ids),None)
            if target is None:
                return {"timeline":result,"grant_found":True,"grantor_committed":False}
            affected={rid for rid,rec in with_grant.items() if any(g["granting_revision_id"]==str(target) for g in rec["authorizations"])}
            apply(p,target)
            return {"timeline":result,"grant_found":True,"grantor_retracted":target not in c._observed_events,
                    "affected_count":len(affected),"affected_still_eligible":sum(c.observation_write_eligibility(rid)["write_eligible"] for rid in affected),
                    "affected_still_committed":len(affected & set(c._committed_events))}
    return {"timeline":result,"grant_found":False}


print(json.dumps({"correction_same":correction(True),"correction_different":correction(False),
                  "direct_p5_correction_same":correction(True, True),
                  "direct_p5_correction_different":correction(False, True),
                  "blocked_grants":blocked_grants()},indent=2))
