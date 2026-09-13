"""Independent B5 coherent-reseal and long-history audit.

The long-history reference computes importance weights from the frozen receipt
equation, never from the workspace's final marginal.  Each requested length is
run in a fresh subprocess so peak memory and wall time are not cumulative.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import time
import types
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("CPSWM_AUDIT_ROOT", Path(__file__).resolve().parents[1])).resolve()
SEED = 7
Q = 0.25


class _Mark:
    def __getattr__(self, _name: str):
        def factory(*args: object, **kwargs: object):
            if len(args) == 1 and callable(args[0]) and not kwargs:
                return args[0]
            return lambda function: function

        return factory


class _PytestStub(types.ModuleType):
    mark = _Mark()
    MonkeyPatch = object


def _load_fixtures() -> tuple[Any, Any, Any]:
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
    sys.modules.setdefault("pytest", _PytestStub("pytest"))
    import test_structure_two_formal_revision_lineage as old
    from structure_two_backbone_wiring_probe import BackboneWiringProbe
    from test_structure_two_w3_native_particles import candidates

    return old, BackboneWiringProbe, candidates


def _error(call) -> dict[str, str] | None:
    try:
        call()
    except BaseException as error:
        return {"type": type(error).__qualname__, "message": str(error)}
    return None


def _coherent_reseal_probe() -> dict[str, Any]:
    old, _probe_type, candidates = _load_fixtures()
    from cpswm.system.structure_two_particle_workspace import native_content_sha256

    core = old._legacy_history(1).system.core
    arguments = candidates(core)
    core.stage_prepared_particle_candidates(**arguments)
    legal_marginal = core.prepared_particle_location_marginal()
    workspace = core._particle_workspace
    cluster, body = next(iter(workspace.input_bodies.items()))
    frames, cause_snapshot = deepcopy(body.source_frame)
    revision_id = next(iter(frames))
    row = frames[revision_id]
    runtime_propensity = core._observed_events[revision_id].propensity_weight
    forged_propensity = float(row[2]) + 0.125
    frames[revision_id] = (row[0], row[1], forged_propensity, row[3], row[4])
    forged_frame = (frames, cause_snapshot)
    forged_body = replace(body, source_frame=forged_frame)
    fingerprint = native_content_sha256(forged_body)
    frame_sha256 = native_content_sha256(forged_frame)
    workspace.input_bodies[cluster] = forged_body
    workspace.input_journal[cluster] = fingerprint
    for particle_id, record in tuple(workspace.records.items()):
        if record.evidence_cluster_id == cluster:
            workspace.records[particle_id] = replace(
                record,
                source_frame=forged_frame,
                source_frame_sha256=frame_sha256,
                input_fingerprint_sha256=fingerprint,
            )

    workspace_error = _error(workspace.state_payload)
    readout_error = _error(core.prepared_particle_location_marginal)
    identity_error = _error(core.semantic_memory_identity)
    return {
        "legal_control": {
            "particle_count": len(core._particle_workspace.batch.particle_weights),
            "mass": sum(legal_marginal[0].values()) + legal_marginal[1],
        },
        "attack": {
            "revision_id": str(revision_id),
            "runtime_propensity": runtime_propensity,
            "forged_propensity": forged_propensity,
            "protected_dependency_changed": runtime_propensity != forged_propensity,
            "workspace_internal_validation_error": workspace_error,
            "core_readout_error": readout_error,
            "semantic_identity_error": identity_error,
        },
        "verdict": (
            "PASS"
            if workspace_error is None
            and readout_error is not None
            and identity_error is not None
            and runtime_propensity != forged_propensity
            else "FAIL"
        ),
    }


def _expected_weights(
    owner_probability: float | None,
    unknown_probability: float | None,
) -> tuple[float, float, float]:
    owner_mass = 1.0 / Q if owner_probability is None else owner_probability / Q
    unknown_mass = (
        1.0 / (1.0 - Q)
        if unknown_probability is None
        else unknown_probability / (1.0 - Q)
    )
    unresolved_mass = 1.0
    total = owner_mass + unknown_mass + unresolved_mass
    return owner_mass / total, unknown_mass / total, unresolved_mass / total


def _history_worker(length: int) -> dict[str, Any]:
    _old, probe_type, candidates = _load_fixtures()
    probe = probe_type.build(seed=SEED, duration_days=max(32, length + 2))
    core = probe.system.core
    days = probe.observed_days()
    expected_owner: float | None = None
    expected_unknown: float | None = None
    rows = []
    maximum_error = 0.0
    wall_started = time.perf_counter()
    for step in range(length):
        transition_started = time.perf_counter()
        core.process_transition(probe.transition_for(days[step]))
        transition_seconds = time.perf_counter() - transition_started
        stage_started = time.perf_counter()
        batch = core.stage_prepared_particle_candidates(**candidates(core, step=step, q=Q))
        stage_seconds = time.perf_counter() - stage_started
        expected_owner, expected_unknown, expected_unresolved = _expected_weights(
            expected_owner, expected_unknown
        )
        observed = tuple(weight.posterior_probability for weight in batch.particle_weights)
        errors = (
            abs(observed[0] - expected_owner),
            abs(observed[1] - expected_unknown),
            abs(batch.unresolved_probability - expected_unresolved),
        )
        maximum_error = max(maximum_error, *errors)
        rows.append(
            {
                "generation": step + 1,
                "transition_seconds": transition_seconds,
                "stage_seconds": stage_seconds,
                "expected": [expected_owner, expected_unknown, expected_unresolved],
                "observed": [*observed, batch.unresolved_probability],
                "maximum_absolute_error": max(errors),
            }
        )

    state_started = time.perf_counter()
    core._particle_workspace.state_payload()
    state_seconds = time.perf_counter() - state_started
    marginal_started = time.perf_counter()
    marginal = core.prepared_particle_location_marginal()
    marginal_seconds = time.perf_counter() - marginal_started
    semantic_started = time.perf_counter()
    core.semantic_memory_identity()
    semantic_seconds = time.perf_counter() - semantic_started
    latest = core._particle_workspace.batch.particle_weights[0].particle_id
    depth = len(core._particle_workspace.records[latest].event_chain_history)
    return {
        "length": length,
        "seed": SEED,
        "q": Q,
        "records": len(core._particle_workspace.records),
        "ancestry_depth": depth,
        "wall_seconds": time.perf_counter() - wall_started,
        "state_payload_seconds": state_seconds,
        "marginal_seconds": marginal_seconds,
        "semantic_identity_seconds": semantic_seconds,
        "ru_maxrss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "final_mass": sum(marginal[0].values()) + marginal[1],
        "maximum_oracle_error": maximum_error,
        "generations": rows,
        "verdict": "PASS" if maximum_error <= 1e-12 else "FAIL",
    }


def _subprocess_history(length: int) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), str(ROOT / "tests")))
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker-length", str(length)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        return {
            "length": length,
            "verdict": "ERROR",
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    return json.loads(completed.stdout)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lengths", type=int, nargs="*", default=[4, 8, 12, 16, 20])
    parser.add_argument("--worker-length", type=int)
    args = parser.parse_args()
    if args.worker_length is not None:
        print(json.dumps(_history_worker(args.worker_length), sort_keys=True))
        return 0
    if args.output is None:
        parser.error("--output is required outside worker mode")

    payload = {
        "scope": "B5 independent extended-state and long-history audit",
        "base_sha": "c366cad0a92593bb2c4c44db7e8d3408a2b5cc9c",
        "platform": platform.platform(),
        "python": sys.version,
        "source_sha256": {
            path.name: _sha256(path)
            for path in (
                ROOT / "src/cpswm/system/prototype_spine.py",
                ROOT / "src/cpswm/system/structure_two_particle_workspace.py",
                ROOT / "src/cpswm/system/structure_two_semantic_identity.py",
            )
        },
        "coherent_reseal": _coherent_reseal_probe(),
        "long_history": [_subprocess_history(length) for length in args.lengths],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if all(
        row["verdict"] == "PASS"
        for row in (payload["coherent_reseal"], *payload["long_history"])
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
