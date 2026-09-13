"""Bounded component metamorphic checks and real-receipt coverage inventory.

No synthetic controller result is counted as real-world or Unity evidence.
"""

import copy
import importlib.util
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from cpswm.data_preflight.procthor_execution import execute_schedule  # noqa: E402
from cpswm.data_preflight.procthor_schedule import ReleaseQueue, digest  # noqa: E402
from cpswm.data_preflight.proposal_samples import ProposalSample  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "seeds", ROOT / "tests/test_structure_two_proposal_scheduler.py"
)
seeds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seeds)
OUT = ROOT / "docs/reviews/pc_a/proposal_two_round_audit_2026-09-13" / sys.argv[1]
OUT.mkdir(parents=True, exist_ok=False)


def save(name, value):
    with (OUT / name).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def projected_run(name, schedule):
    execute_schedule(seeds.ComponentController(), schedule, OUT / name, **seeds.bindings())
    path = OUT / name
    receipts = [
        json.loads(p.read_text())
        for p in sorted((path / "evaluator_only/raw/observations").glob("*.json"))
    ]
    return {
        "requests": [r["request"] for r in receipts],
        "sensor_hashes": [r["sensor_sha256"] for r in receipts],
        "release": json.loads((path / "observation_candidates/release_journal.json").read_text()),
    }


schedule = seeds.schedule()
original = projected_run("component_original", schedule)
mapping = {
    a: schedule.actors[(i + 1) % len(schedule.actors)] for i, a in enumerate(schedule.actors)
}
permuted = replace(
    schedule,
    events=tuple(replace(e, actors=tuple(mapping[a] for a in e.actors)) for e in schedule.events),
)
actors = projected_run("component_actor_permutation", permuted)
events = list(schedule.events)
correction_changes = []
for i, event in enumerate(events):
    if event.kind == "late_correction":
        alternatives = [
            e
            for e in events[:i]
            if e.instance_key == event.instance_key and e.event_id != event.correction_of
        ]
        if alternatives:
            correction_changes.append(
                {
                    "event": event.event_id,
                    "old": event.correction_of,
                    "new": alternatives[0].event_id,
                }
            )
            events[i] = replace(event, correction_of=alternatives[0].event_id)
corrections = projected_run("component_correction_relink", replace(schedule, events=tuple(events)))
base = seeds.sample_payload.__wrapped__()
other = copy.deepcopy(base)
other.update(
    sample_id=seeds.uid("train-other"),
    partition="train",
    house_id="other-house",
    house_sha256="b" * 64,
    schedule_block_id="other-block",
)
input_path = OUT / "mixed-partitions.json"
save("mixed-partitions.json", [base, other])
command = [
    sys.executable,
    str(ROOT / "tools/structure_two_prepare_proposals.py"),
    "--input",
    str(input_path),
    "--output",
    str(OUT / "mixed_prepared"),
    "--allow-component-fixtures",
]
result = subprocess.run(
    command, env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True
)
save(
    "mixed-cli.json",
    {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    },
)
if result.returncode != 0:
    raise RuntimeError("mixed split diagnostic unexpectedly rejected")
queue = ReleaseQueue()
queue.enqueue(
    replace(schedule.events[0], release_tick=float("nan"), observation_selected=True), "000001.json"
)
silent_drop = not queue.release(10000)
foreign = copy.deepcopy(base)
foreign["compatible_targets"][0]["candidate"]["events"][-1]["location_key"] = (
    "unregistered_location"
)
foreign_accepted = bool(ProposalSample.model_validate(foreign))
save(
    "summary.json",
    {
        "scope": "component metamorphic diagnostics; not human action or training evidence",
        "actor_permutation_changes_schedule": digest(schedule.payload())
        != digest(permuted.payload()),
        "actor_permutation_identical_requests_sensors_releases": original == actors,
        "correction_relinks": correction_changes,
        "correction_relink_identical_requests_sensors_releases": original == corrections,
        "mixed_preparation_accepted": True,
        "mixed_features_rows": len(
            (OUT / "mixed_prepared/features.jsonl").read_text().splitlines()
        ),
        "partitions_only_in_audit_rows": [
            json.loads(line)["partition"]
            for line in (OUT / "mixed_prepared/audit.jsonl").read_text().splitlines()
        ],
        "training_ready": json.loads((OUT / "mixed_prepared/readiness.json").read_text())[
            "training_ready"
        ],
        "standalone_queue_nan_capture_not_released": silent_drop,
        "unsupported_location_accepted_without_location_support_field": foreign_accepted,
    },
)
print((OUT / "summary.json").read_text())
