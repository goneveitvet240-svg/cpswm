"""Two independent adversarial probes for the frozen B4 boundary repair.

This is an audit-only tool.  It neither patches production code nor treats a
passing control as a scientific-acceptance result.  It records two boundaries:

* round 1: an untrusted caller invokes the public NativeParticleWorkspace
  boundary with a validly shaped but source-frame-inconsistent event chain;
* round 2: a fresh interpreter imports the public core module before the
  evaluation-operations package has been initialised.

Run from the frozen checkout:
  PYTHONPATH=src:tests python tools/pc_b_two_round_adversarial_audit.py --output out.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import types
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


class _Mark:
    """Enough pytest surface to import the frozen fixture helpers without pytest."""

    def __getattr__(self, _name: str):
        def factory(*_args: object, **_kwargs: object):
            def decorate(function: object) -> object:
                return function

            return decorate

        return factory


class _PytestStub(types.ModuleType):
    mark = _Mark()
    MonkeyPatch = object


def _source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _exception(callable_: object) -> dict[str, str] | None:
    try:
        assert callable(callable_)
        callable_()
    except BaseException as error:  # audit needs to retain KeyboardInterrupt too
        return {"type": type(error).__qualname__, "message": str(error)}
    return None


def _import_probe(code: str) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "src")
    started = time.perf_counter_ns()
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "returncode": completed.returncode,
        "elapsed_ms": (time.perf_counter_ns() - started) / 1e6,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _fixture_runtime() -> tuple[Any, Any, dict[str, Any], dict[Any, Any], Any]:
    """Build real runtime evidence using the frozen test fixture, not a mock world."""

    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
    sys.modules.setdefault("pytest", _PytestStub("pytest"))
    import test_structure_two_formal_revision_lineage as old
    from test_structure_two_w3_native_particles import candidates

    core = old._legacy_history(1).system.core
    arguments = candidates(core)
    revision_id = arguments["receipts"][0].proposal.proposed_state.revision_id
    history = core._event_histories[revision_id]
    event = core._observed_events[revision_id]
    chains = {chain.hypothesis_id: chain for chain in history.latest.hypotheses}
    source_frame = (
        {
            revision_id: (
                history,
                event.evidence,
                event.propensity_weight,
                event.regime_frame,
                event.identity_switch_probability,
            )
        },
        core.current_cause_snapshot,
    )
    return core, core._particle_workspace, arguments, chains, source_frame


def _direct_advance(
    core: Any,
    workspace: Any,
    arguments: dict[str, Any],
    chains: dict[Any, Any],
    source_frame: Any,
) -> Any:
    return workspace.advance(
        receipts=arguments["receipts"],
        statistics=arguments["statistics"],
        chains=chains,
        snapshot_id=core.current_snapshot.snapshot_id,
        allowed_locations=core._registered_particle_locations,
        source_frame=source_frame,
        ledger_head_sha256=core._hybrid_loop.ledger.export_state().manifest.head_hash,
        unresolved_log_weight=arguments["unresolved_log_weight"],
    )


def round_one() -> dict[str, Any]:
    """Compare a legal public workspace call to a resealed false-chain call."""

    started = time.perf_counter_ns()
    core, workspace, arguments, chains, source_frame = _fixture_runtime()
    legal_batch = _direct_advance(core, workspace, arguments, chains, source_frame)
    legal_readout_error = _exception(workspace.state_payload)

    core, workspace, arguments, chains, source_frame = _fixture_runtime()
    target = arguments["receipts"][0].proposal.proposed_state.event_hypothesis_id
    original = chains[target]
    # The replacement preserves the legal pydantic type, hypothesis UUID and
    # every role used by advance(), while changing a field retained in the
    # runtime-owned source frame.  It is therefore a non-no-op forged lineage.
    forged = original.model_copy(
        update={"explanation_code": original.explanation_code + "-audit-forged"}
    )
    chains[target] = forged
    advance_error = _exception(
        lambda: _direct_advance(core, workspace, arguments, chains, source_frame)
    )
    persisted_error = _exception(workspace.state_payload)
    records_after_attack = len(workspace.records)
    journal_entries_after_attack = len(workspace.input_journal)
    recovery_error = _exception(lambda: core.stage_prepared_particle_candidates(**arguments))
    return {
        "name": "public-workspace forged-chain atomicity",
        "elapsed_ms": (time.perf_counter_ns() - started) / 1e6,
        "legal_control": {
            "advance_returned_particles": len(legal_batch.particle_weights),
            "state_payload_error": legal_readout_error,
        },
        "attack": {
            "same_hypothesis_id": forged.hypothesis_id == original.hypothesis_id,
            "same_roles": tuple(
                step.actor_key for step in forged.steps
            ) == tuple(step.actor_key for step in original.steps),
            "content_changed": forged != original,
            "advance_error": advance_error,
            "records_after_attack": records_after_attack,
            "journal_entries_after_attack": journal_entries_after_attack,
            "post_commit_state_payload_error": persisted_error,
            "subsequent_legal_core_stage_error": recovery_error,
        },
        "verdict": (
            "FAIL: public advance accepted forged source lineage and left an invalid "
            "persisted state"
            if advance_error is None and persisted_error is not None and recovery_error is not None
            else (
                "PASS: forged source lineage was rejected atomically"
                if advance_error is not None
                and persisted_error is None
                and records_after_attack == 0
                and journal_entries_after_attack == 0
                and recovery_error is None
                else "INDETERMINATE: attack outcome did not match either frozen expectation"
            )
        ),
    }


def round_two() -> dict[str, Any]:
    """Use clean interpreters so an import cache cannot hide a bootstrap cycle."""

    prototype_first = _import_probe(
        "import cpswm.system.prototype_spine as module; print(module.CorePrototypeSpine.__name__)"
    )
    selected_method_first = _import_probe(
        "import cpswm.system.evaluation_operations.structure_two_selected_method; "
        "import cpswm.system.prototype_spine as module; print(module.CorePrototypeSpine.__name__)"
    )
    return {
        "name": "fresh-interpreter public import order",
        "prototype_spine_first": prototype_first,
        "selected_method_then_prototype_spine_control": selected_method_first,
        "verdict": (
            "FAIL: prototype_spine cannot be imported as the first public module"
            if prototype_first["returncode"] != 0 and selected_method_first["returncode"] == 0
            else "PASS: public import is order independent"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = {
        "schema": "cpswm.pc-b.two-round-adversarial-audit@1",
        "platform": platform.platform(),
        "python": sys.version,
        "cwd": str(ROOT),
        "source_sha256": {
            str(path.relative_to(ROOT)): _source_sha256(path)
            for path in (
                ROOT / "src/cpswm/system/prototype_spine.py",
                ROOT / "src/cpswm/system/structure_two_particle_workspace.py",
                ROOT / "src/cpswm/system/structure_two_semantic_identity.py",
            )
        },
        "rounds": [round_one(), round_two()],
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
