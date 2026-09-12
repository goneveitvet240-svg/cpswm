"""Independent local public CORRECT checks on one immutable delivered checkout.

Uses delivered public-history fixture only, never injects private state or a
write grant. Observes private state read-only for rollback coverage. This is an
ordinary production-lane boundary check, NOT direct-P5 comparative capability.
"""

import argparse
import importlib
import json
import sys
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--root", type=Path, required=True)
a = p.parse_args()
root = a.root.resolve()
sys.path[:0] = [str(root / "src"), str(root / "tests")]
old = importlib.import_module("test_structure_two_formal_revision_lineage")
boundary = importlib.import_module("test_structure_two_w3_round5_boundaries")
repro = importlib.import_module("cpswm.system.reproducibility")


def observe(core):
    return {
        "observable": core._execution_observable_state_sha256(),
        "ledger": repro.content_sha256(core._hybrid_loop.ledger.export_state()),
        "ledger_records": json.loads(repro.canonical_json(core._hybrid_loop.ledger.export_state())),
        "committed_records": {
            str(rid): {"location": str(event.location_id), "owner_mass": event.owner_mass}
            for rid, event in core._committed_events.items()
        },
        "hybrid_alpha": {str(loc): core.hybrid_alpha(loc) for loc in core.locations},
        "action": {
            str(k): v for k, v in core.action_location_distribution(core.current_snapshot).items()
        },
        "committed": sorted(str(x) for x in core._committed_events),
        "identities": [
            id(core._hybrid_loop.ledger),
            id(core._automatic_regimes.ccrr),
            id(core._automatic_regimes.bocpd),
            id(core._particle_workspace),
        ],
    }


rows = []
for case, index in [("legal_same", 8), ("legal_different", 8), ("ineligible_different", 3)]:
    probe = old._legacy_history()
    core = probe.system.core
    target = list(core._committed_events)[index]
    parent = core._committed_events[target]
    request = boundary.direct_outcome(core, target, case == "legal_same", parent.owner_mass)
    before = observe(core)
    assert target in core._committed_events and parent.owner_mass > 0
    error = None
    try:
        response = core.apply_event_revision_outcome(request)
        operations = [op.value for op in response.statistic_operations]
    except ValueError as exc:
        error = str(exc)
        operations = []
    after = observe(core)
    if case.startswith("legal"):
        assert error is None and operations == ["correct"]
        assert target not in core._committed_events
        new = core._committed_events[request.corrected_revision_id]
        assert new.location_id == request.corrected_location_id
        assert new.owner_mass == request.corrected_owner_mass > 0
        assert core.observation_write_eligibility(request.corrected_revision_id)["write_eligible"]
        assert not core.observation_write_eligibility(target)["write_eligible"]
        assert request.corrected_revision_id not in {
            x.revision_id for x in core._quarantined_events
        }
        assert after["ledger"] != before["ledger"]
        try:
            core.apply_event_revision_outcome(request)
        except KeyError as exc:
            assert "superseded" in str(exc)
        else:
            raise AssertionError("duplicate CORRECT unexpectedly returned")
        assert observe(core) == after
    else:
        assert error is not None and "CORRECT not admitted" in error
        assert before == after
        assert target in core._committed_events
        assert request.corrected_revision_id not in core._observed_events
    rows.append(
        {
            "case": case,
            "history_fixture": "_legacy_history(12)",
            "target_index": index,
            "requested_location": str(request.corrected_location_id),
            "requested_mass": request.corrected_owner_mass,
            "public_request": json.loads(repro.canonical_json(request)),
            "operations": operations,
            "error": error,
            "before": before,
            "after": after,
            "action_distribution_changed": before["action"] != after["action"],
            "checks_passed": True,
        }
    )
loaded = {
    name: str(Path(module.__file__).resolve())
    for name, module in sys.modules.copy().items()
    if module is not None and name.startswith("cpswm") and getattr(module, "__file__", None)
}
assert loaded and all(Path(path).is_relative_to(root / "src") for path in loaded.values())
print(
    json.dumps(
        {
            "scope": (
                "ordinary public correction boundary, not unified/direct-P5/scientific acceptance"
            ),
            "root": str(root),
            "python": sys.executable,
            "loaded": loaded,
            "cases": rows,
        },
        indent=2,
    )
)
