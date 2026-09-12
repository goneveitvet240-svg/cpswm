"""Persist an existing D0 contract fixture export, explicitly NOT real sensor data."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

from cpswm.contracts.habit_learning import ActorEvidenceTrack  # noqa: E402
from cpswm.system.evaluation_operations.d0_shift_scenarios import (  # noqa: E402
    D0ShiftScenarioGenerator,
)

OUT = Path(__file__).resolve().parent / sys.argv[1]
OUT.mkdir(exist_ok=False)
case = (
    D0ShiftScenarioGenerator()
    .generate(actor_evidence_track=ActorEvidenceTrack.CONTROLLED_NOISE)
    .cases[0]
    .model_input
)
run = case.control_run
envelope = {
    "partition": "development",
    "opportunities": [x.model_dump(mode="json") for x in run.observation_opportunities],
    "detections": [x.model_dump(mode="json") for x in run.detection_results],
    "actor_evidence": [x.model_dump(mode="json") for x in case.control_actor_evidence],
    "received_at": {
        str(x.metadata.record_id): x.metadata.recorded_time.isoformat()
        for x in (
            *run.observation_opportunities,
            *run.detection_results,
            *case.control_actor_evidence,
        )
    },
}
with (OUT / "input.json").open("x", encoding="utf-8") as handle:
    json.dump(envelope, handle, indent=2)
cutoff = run.observation_opportunities[3].opportunity_time.isoformat()
command = [
    sys.executable,
    str(ROOT / "tools/structure_two_data_preflight.py"),
    "export-visible",
    "--input",
    str(OUT / "input.json"),
    "--cutoff",
    cutoff,
    "--output",
    str(OUT / "prefix.json"),
]
with (OUT / "export.log").open("x") as log:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT / "src")),
        stdout=log,
        stderr=subprocess.STDOUT,
        check=False,
    )
with (OUT / "command.json").open("x") as handle:
    json.dump(
        {
            "command": command,
            "exit_code": result.returncode,
            "timing_scope": "D0 fixture recorded_time, not an actual ingestion journal",
            "source_scope": "existing development component fixture, not training-ready data",
            "base_sha": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
        },
        handle,
        indent=2,
    )
sys.exit(result.returncode)
