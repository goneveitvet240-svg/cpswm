"""Unchanged before/after public cancellation observation; exit 0 is not a pass."""

import importlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root / "src"), str(root / "tests")]
replace = importlib.import_module("dataclasses").replace

old = importlib.import_module("test_structure_two_formal_revision_lineage")
CalibratedRetractionPolicy = importlib.import_module(
    "structure_two_backbone_wiring_probe"
).CalibratedRetractionPolicy
FrozenRevisionOracle = importlib.import_module("structure_two_revision_oracle").FrozenRevisionOracle
direct_outcome = importlib.import_module("test_structure_two_w3_round5_boundaries").direct_outcome
request_for = importlib.import_module("test_structure_two_w3_round5_boundaries").request_for

probe = old._legacy_history(12)
core = probe.system.core
target = list(core._committed_events)[11]
original = core._committed_events[target]
outcome = direct_outcome(core, target, False, original.owner_mass)
_, _, interpretation = FrozenRevisionOracle(probe).prepare(
    old._feedback(probe, target),
    CalibratedRetractionPolicy(corrected_location_id=outcome.corrected_location_id),
)
outcome = replace(outcome, corrected_owner_mass=interpretation.evidence_strength)
request = request_for(core, outcome)
result = core.apply_project_one_stat_request(request)
child = outcome.corrected_revision_id
before = {
    "status": result.status.value,
    "parent_live": target in core._committed_events,
    "child_quarantined": core.is_quarantined_revision(child),
}
step = core.process_transition(probe.transition_for(probe.observed_days()[12]))
print(
    json.dumps(
        {
            "before": before,
            "after": {
                "status": core.application_receipts_for_feedback(
                    outcome.evidence_source_record_ids[0]
                )[-1].status.value,
                "parent_live": target in core._committed_events,
                "parent_observed": target in core._observed_events,
                "parent_fast": target in core._fast_action_events,
                "child_live": child in core._committed_events,
                "child_observed": child in core._observed_events,
                "child_fast": child in core._fast_action_events,
                "new_observation_retained": step.event_revision_id in core._observed_events,
                "pending_count": len(core._deferred_project_one_requests),
                "parent_eligible": core.observation_write_eligibility(target)["write_eligible"],
            },
        },
        indent=2,
    )
)
