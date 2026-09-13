"""Test the new journal oracle on the independently found public CORRECT regression."""
import json
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(root / "src"), str(root / "tests")]
import test_structure_two_formal_revision_lineage as cases
from structure_two_backbone_wiring_probe import CalibratedRetractionPolicy

probe = cases._legacy_history()
core = probe.system.core
journal = cases._journal(probe)
target = next(iter(core._committed_events))
original = core._committed_events[target]
before_observed = set(core._observed_events)
result = cases._apply(probe, cases._feedback(probe, target), policy=CalibratedRetractionPolicy(
    corrected_location_id=original.location_id))
new_ids = set(core._observed_events) - before_observed
cases._assert_reconciled_against_journal(probe, journal)
print(json.dumps({
    "returned_operations": [operation.value for operation in result.statistic_operations],
    "new_corrected_revisions": len(new_ids),
    "corrected_revision_committed": bool(new_ids & set(core._committed_events)),
    "new_test_journal_oracle_passed": True,
    "production_methods_replaced": False,
}, indent=2))
