"""Read-only implementation audit; production source and methods are never replaced."""
import json
import sys
from pathlib import Path
from uuid import uuid4

root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root / "src"), str(root / "tests")]
import test_structure_two_formal_revision_lineage as old
from cpswm.system.prototype_spine import EventRevisionKind, EventRevisionOutcome
from cpswm.system.reproducibility import content_sha256


def oracle_refreeze():
    from test_structure_two_w3_revision_acceptance import correction
    probe = old._legacy_history(2)
    core = probe.system.core
    target = next(iter(core._committed_events))
    correction(probe, target)
    # Freeze an already legitimate corrected state, then check it unchanged.
    journal = old._journal(probe)
    state = old._full_state(probe)
    try:
        old._assert_reconciled_against_journal(probe, journal)
        result = {"oracle_accepts_unchanged_corrected_state": True}
    except AssertionError as exc:
        result = {"oracle_accepts_unchanged_corrected_state": False, "error": str(exc)}
    result["production_state_unchanged"] = old._full_state(probe) == state
    result["actual_committed"] = len(core._committed_events)
    result["reference_committed"] = len(journal.oracle.reference()[0])
    return result


def difference(a, b, prefix=""):
    if type(a) is not type(b):
        return [prefix]
    if isinstance(a, dict):
        if a.keys() != b.keys():
            return [prefix + ".keys"]
        return [p for k in a for p in difference(a[k], b[k], prefix + "." + str(k))]
    if isinstance(a, list):
        if len(a) != len(b):
            return [prefix + ".length"]
        return [p for i, (x, y) in enumerate(zip(a, b)) for p in difference(x, y, prefix + f"[{i}]")]
    return [] if a == b else [prefix]


def semantic_correction():
    from cpswm.system.structure_two_semantic_identity import semantic_memory_state
    left, right = old._legacy_history(2), old._legacy_history(2)
    before = [semantic_memory_state(p.system.core) for p in (left, right)]
    feedback_id, action_id = uuid4(), uuid4()
    actions = []
    for probe in (left, right):
        core = probe.system.core
        target = next(iter(core._committed_events))
        event = core._committed_events[target]
        bundle = old._feedback(probe, target, feedback_record_id=feedback_id, action_id=action_id)
        from structure_two_backbone_wiring_probe import CalibratedRetractionPolicy
        policy = CalibratedRetractionPolicy(corrected_location_id=event.location_id)
        # Each bound decision context references its own run's snapshot.
        result = probe.system.process_execution_feedback(
            feedback=bundle[0], binding=bundle[1], likelihood_model=bundle[2], policy=policy
        )
        actions.append([op.value for op in result.statistic_operations])
    after = [semantic_memory_state(p.system.core) for p in (left, right)]
    return {
        "before_semantic_equal": before[0] == before[1],
        "after_semantic_equal": after[0] == after[1],
        "feedback_record_and_action_ids_identical": True,
        "returned_operations": actions,
        "difference_paths": difference(after[0], after[1]),
        "semantic_hashes": [content_sha256(x) for x in after],
    }


def direct_revision():
    probe = old._legacy_history()
    core = probe.system.core
    target = list(core._committed_events)[3]
    parent = core._committed_events[target]
    new = uuid4()
    result = core.apply_event_revision_outcome(EventRevisionOutcome(
        kind=EventRevisionKind.CORRECT, superseded_revision_id=target,
        corrected_revision_id=new,
        corrected_location_id=next(loc for loc in core.locations if loc != parent.location_id),
        corrected_owner_mass=parent.owner_mass, evidence_source_record_ids=(uuid4(),),
        rationale="independent public revision API postcondition probe",
    ))
    return {
        "public_entry": "core.apply_event_revision_outcome",
        "returned_operations": [op.value for op in result.statistic_operations],
        "old_still_committed": target in core._committed_events,
        "new_committed": new in core._committed_events,
        "new_quarantined": core.is_quarantined_revision(new),
        "ccrr_conclusion": str(result.ccrr_conclusion),
    }


out = {}
for name, fn in [("oracle_refreeze", oracle_refreeze), ("semantic_correction", semantic_correction), ("direct_revision", direct_revision)]:
    if len(sys.argv) > 2 and name != sys.argv[2]:
        continue
    try:
        out[name] = fn()
    except Exception as exc:
        out[name] = {"unexpected_error": type(exc).__name__ + ": " + str(exc)}
print(json.dumps(out, indent=2))
