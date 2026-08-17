from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from cpswm.contracts import ValidTimeInterval
from cpswm.foundation.identity_time_frames import FrameTransform, Vector3
from cpswm.foundation.persistence_replay import AppendOnlyTransactionLog
from cpswm.foundation.runtime_orchestration import (
    MessageKind,
    ReplayRun,
    RuntimeMessage,
    RuntimeMessageRecord,
    build_replay_manifest,
    build_version_bundle,
    compare_replay_runs,
    git_head_code_version,
)


def test_restart_replay_loads_serialized_log_in_independent_processes(now, tmp_path):
    repository_root = Path(__file__).resolve().parents[1]
    runtime_spec = {
        "configuration": {
            "handler": "m02.align-observation",
            "mode": "restart-replay",
        },
        "model_versions": {},
    }
    versions = build_version_bundle(
        repository_root,
        configuration=runtime_spec["configuration"],
        model_versions=runtime_spec["model_versions"],
    )
    household_id = uuid4()
    session_id = uuid4()
    transform = FrameTransform(
        household_id=household_id,
        source_frame_id="camera",
        target_frame_id="household_map",
        translation=Vector3(x=1.0, y=2.0, z=0.0),
        valid_time=ValidTimeInterval(start=now - timedelta(minutes=1), end=None),
        transform_version="restart-transform@1",
    )
    message = RuntimeMessage.create(
        name="observation.align",
        kind=MessageKind.COMMAND,
        schema_version="0.1.0",
        household_id=household_id,
        session_id=session_id,
        trace_id=uuid4(),
        idempotency_key="restart-observation-1",
        sequence_no=0,
        payload={
            "source_frame_id": "camera",
            "target_frame_id": "household_map",
            "point": {"x": 2.0, "y": 3.0, "z": 1.0},
            "observed_time": now.isoformat(),
            "transform": transform.model_dump(mode="json"),
        },
        created_at=now,
    )
    input_log = AppendOnlyTransactionLog()
    input_log.append(
        [RuntimeMessageRecord.from_message(message)],
        idempotency_key="restart-input-1",
    )
    manifest = build_replay_manifest(
        input_log,
        versions=versions,
        schema_version="0.1.0",
        random_seed=20260811,
        created_at=now,
    )

    input_path = tmp_path / "canonical-input-log.json"
    manifest_path = tmp_path / "replay-manifest.json"
    spec_path = tmp_path / "runtime-spec.json"
    output_a = tmp_path / "replay-a.json"
    output_b = tmp_path / "replay-b.json"
    input_log.dump(input_path)
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    spec_path.write_text(
        json.dumps(runtime_spec, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    worker = repository_root / "tests" / "fixtures" / "step1_replay_worker.py"
    base_command = [
        sys.executable,
        str(worker),
        str(repository_root),
        str(input_path),
        str(manifest_path),
        str(spec_path),
    ]
    subprocess.run([*base_command, str(output_a)], cwd=repository_root, check=True)
    subprocess.run([*base_command, str(output_b)], cwd=repository_root, check=True)

    first = ReplayRun.model_validate_json(output_a.read_text(encoding="utf-8"))
    second = ReplayRun.model_validate_json(output_b.read_text(encoding="utf-8"))
    assert compare_replay_runs(first, second, numeric_tolerance=0.0)
    assert first.output_payloads[0]["point"] == {"x": 3.0, "y": 5.0, "z": 1.0}
    provenance = first.execution_provenance[0]
    assert (
        datetime.fromisoformat(provenance["output_watermark"]["recorded_at"].replace("Z", "+00:00"))
        == manifest.created_at
    )
    assert provenance["versions"]["code_version"] == git_head_code_version(repository_root)
    assert provenance["versions"]["source_tree_sha256"] == versions.source_tree_sha256
    assert first.input_log_sha256 == manifest.input_log_sha256
    assert first.input_watermark == manifest.input_watermark
