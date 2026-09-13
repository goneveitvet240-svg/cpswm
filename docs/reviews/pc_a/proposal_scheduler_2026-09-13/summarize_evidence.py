"""Read recorded final-run evidence; no model/held-out data or new simulator actions."""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
from cpswm.data_preflight.capture_prefix import released_capture_prefix  # noqa: E402
from cpswm.data_preflight.proposal_samples import ProposalSample  # noqa: E402

BASE = Path(__file__).resolve().parent
run = BASE / sys.argv[1]
out = BASE / sys.argv[2]
out.mkdir(exist_ok=False)
schedule = json.loads((run / "schedule_run/evaluator_only/schedule.json").read_text())
execution = json.loads((run / "schedule_run/evaluator_only/execution.json").read_text())
receipt = json.loads((run / "receipt.json").read_text())
visible = run / "schedule_run/observation_candidates"
binding = json.loads((run / "schedule_run/evaluator_only/binding.json").read_text())
nonconstant = []
for path in sorted(visible.glob("*.npz")):
    with np.load(path, allow_pickle=False) as data:
        nonconstant.append(bool(np.ptp(data["rgb"]) > 0))
target_visible = []
for event, result in zip(schedule["events"], execution, strict=True):
    step = result["actual_steps"][-1]
    metadata = json.loads(
        (run / f"schedule_run/evaluator_only/raw/evaluator_only/{step:06d}.json").read_text()
    )
    target_id = binding["object_ids"][event["instance_key"]]
    target = next(obj for obj in metadata["objects"] if obj["objectId"] == target_id)
    target_visible.append(bool(target["visible"]))
summary = {
    "scope": "one-house development geometry schedule, not full D1 or training readiness",
    "real_procthor_loaded": receipt["real_procthor_loaded"],
    "source_unchanged": receipt["source_unchanged"],
    "schedule_days": schedule["days"],
    "scheduled_actor_identities": len(schedule["actors"]),
    "physical_instances": len(schedule["instance_keys"]),
    "events": len(schedule["events"]),
    "event_counts": dict(Counter(event["kind"] for event in schedule["events"])),
    "geometry_verified_events": sum(event.get("geometry_verified", False) for event in execution),
    "actor_role_execution_verified_events": sum(
        event.get("actor_role_execution_verified", False) for event in execution
    ),
    "nonconstant_rgb_captures": sum(nonconstant),
    "target_visible_events_evaluator_only": sum(target_visible),
    "released_target_visible_captures": sum(
        event["observation_selected"] and seen
        for event, seen in zip(schedule["events"], target_visible, strict=True)
    ),
    "prefix_sizes": {
        str(t): len(released_capture_prefix(visible, t)) for t in (0, 50, 100, 200, 10000)
    },
    "late_releases": sum(
        event["received_tick"] > event["event_tick"]
        for event in released_capture_prefix(visible, 10000)
    ),
    "training_ready": False,
    "source_files_sha256": {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "src/cpswm/data_preflight").glob("*.py"))
    },
}
for filename, payload in (
    ("summary.json", summary),
    ("proposal_sample.schema.json", ProposalSample.model_json_schema()),
):
    with (out / filename).open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
print(json.dumps(summary, indent=2))
