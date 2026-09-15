"""Collect live Unity observations using the configured P5 posterior policy.

Default posterior mode requires an in-repository runtime factory providing the
semantic producer, P5 context and source-bound observation/utility model. The old
fixed scan remains an explicitly selected transport probe. Neither mode alone
establishes real person-role calibration or complete semantic acceptance.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from cpswm.perception_mapping.natural_vision import (
    NaturalAppearanceDetector,
    NaturalVisionEvidenceProducer,
)
from cpswm.system.continuous_camera_collection import (
    ContinuousRuntimeComponents,
    collect_posterior_step,
)
from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput, ObservationCommand
from cpswm.system.structure_two_production_system import StructureTwoProductionSystem
from cpswm.system.unity_observation import UnityObservationExecutor


def load_runtime_factory(spec: str, root: Path):
    if ":" not in spec:
        raise ValueError("runtime factory must be an explicit module:callable")
    module_name, name = spec.split(":", 1)
    module = importlib.import_module(module_name)
    factory = getattr(module, name)
    source = inspect.getsourcefile(factory)
    if (
        not callable(factory)
        or source is None
        or not Path(source).resolve().is_relative_to(root / "src")
    ):
        raise ValueError("runtime factory must be part of the source-bound repository src tree")
    return factory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-python", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("posterior", "transport-probe"), default="posterior")
    parser.add_argument(
        "--runtime-factory", help="module:callable supplying configured P5 components"
    )
    parser.add_argument("--max-actions", type=int, default=2)
    args = parser.parse_args()
    if args.max_actions < 1:
        parser.error("--max-actions must be positive")
    if args.mode == "posterior" and not args.runtime_factory:
        parser.error(
            "posterior mode requires --runtime-factory with semantic/P5 "
            "and observation/utility models"
        )
    if args.mode == "transport-probe" and args.runtime_factory:
        parser.error("transport-probe does not accept a posterior runtime factory")
    root = Path(__file__).resolve().parents[1]
    factory = load_runtime_factory(args.runtime_factory, root) if args.runtime_factory else None
    args.output.mkdir(parents=True, exist_ok=False)
    source = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((root / "src").rglob("*.py"))
    }
    for p in (Path(__file__), root / "tools/unity_observation_worker.py"):
        source[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    source_id = content_sha256(source)
    dependency_id = content_sha256(
        {
            "lock": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
            "weights": hashlib.sha256(args.weights.read_bytes()).hexdigest(),
            "binary": hashlib.sha256(args.binary.read_bytes()).hexdigest(),
            "sdk_python": str(args.sdk_python.resolve()),
        }
    )
    household, session, trace = uuid4(), uuid4(), uuid4()
    scope = dict(household_id=household, session_id=session, trace_id=trace)

    def visual_producer():
        return NaturalVisionEvidenceProducer(
            NaturalAppearanceDetector(weights_path=args.weights, **scope)
        )

    def components():
        if factory is None:
            return None
        configured = factory(scope=dict(scope), weights_path=args.weights)
        if not isinstance(configured, ContinuousRuntimeComponents):
            raise ValueError("runtime factory must return ContinuousRuntimeComponents")
        return configured

    configured = components()
    if args.mode == "posterior":
        assert configured is not None
        backend = configured.producer
        system = configured.system
        dependency_id = content_sha256(
            {
                "environment": dependency_id,
                "factory": args.runtime_factory,
                "model_sources": configured.camera_model.sources.model_dump(mode="json"),
            }
        )
    else:
        backend = visual_producer()
        system = StructureTwoProductionSystem(
            owner_key="unresolved-visual-observer",
            object_instance_id=uuid4(),
            locations=(uuid4(), uuid4()),
            authorization_scope_id=uuid4(),
        )
    path = args.output / "state.sqlite"

    def open_store():
        return ContinuousStateStore(
            path, source_identity=source_id, dependency_identity=dependency_id
        )

    store = open_store()
    stream = ContinuousEvidenceInput(
        system=system,
        execution_lane="registered_p5_first" if configured else "legacy_component_diagnostic",
        context_builder=configured.context_builder if configured else None,
        producer=backend,
        state_store=store,
        **scope,
    )
    executor = UnityObservationExecutor(
        python=args.sdk_python,
        worker=root / "tools/unity_observation_worker.py",
        binary=args.binary,
        house=root
        / "docs/reviews/pc_a/proposal_scheduler_2026-09-13/procthor_run_07/train_house.json",
        log_dir=args.output / "unity_logs",
        **scope,
    )
    rows = []
    try:
        # Initial acquisition precedes the model's first evidence-grounded request.
        initial = executor.execute(
            ObservationCommand(
                uuid4(),
                system.core.current_snapshot.snapshot_id,
                "Pass",
                0,
                "initial acquisition",
                (),
                datetime.now(UTC),
            )
        )
        stream.admit(initial.observations, received_at=initial.received_at)
        stream.advance(cutoff=initial.received_at)
        last = initial
        for step in range(args.max_actions):
            if configured is not None:
                outcome = collect_posterior_step(
                    stream,
                    model=configured.camera_model,
                    executor=executor,
                    decision_time=datetime.now(UTC),
                )
                if outcome.command is None:
                    rows.append(
                        {
                            "step": step,
                            "policy_stopped": True,
                            "plan": outcome.plan.model_dump(mode="json") if outcome.plan else None,
                        }
                    )
                    break
                command, delivery = outcome.command, outcome.delivery
                assert delivery is not None
            else:
                readout = backend.interactions()[-1][1]
                command = stream.prepare_observation(
                    action="RotateRight",
                    degrees=90,
                    reason="development_scan; unresolved=" + readout.next_observation_request,
                    source_ids=(readout.observation_id,),
                    decision_time=datetime.now(UTC),
                )
                delivery = stream.execute_observation(command, executor=executor)
                stream.advance(cutoff=delivery.received_at)
            old_hash = (
                last.observations[0].envelope().payload.payload_sha256
                if last.observations
                else None
            )
            new_hash = (
                delivery.observations[0].envelope().payload.payload_sha256
                if delivery.observations
                else None
            )
            rows.append(
                {
                    "step": step,
                    "action_id": str(command.action_id),
                    "success": delivery.success,
                    "reason": command.reason,
                    "pixel_changed": new_hash != old_hash,
                    "source_ids": [str(x) for x in command.source_ids],
                    "result_observation": str(
                        delivery.observations[0].envelope().identity.observation_id
                    )
                    if delivery.observations
                    else None,
                }
            )
            last = delivery
            if step == 0:
                core_hash = stream._system.adaptive_router_state_sha256()
                store.close()
                store = open_store()
                replacement = components()
                if replacement is not None:
                    assert configured is not None
                    if replacement.camera_model.sources != configured.camera_model.sources:
                        raise ValueError(
                            "runtime factory changed observation/utility source on recovery"
                        )
                    configured = replacement
                    backend = configured.producer
                else:
                    backend = visual_producer()
                stream = ContinuousEvidenceInput.resume(
                    store,
                    producer=backend,
                    context_builder=configured.context_builder if configured else None,
                )
                assert stream._system.adaptive_router_state_sha256() == core_hash
                assert len(stream.visible_prefix(cutoff=delivery.received_at)) >= 2
        result = {
            "scope": "live Unity collection; semantic acceptance requires separate evidence",
            "mode": args.mode,
            "model_sources": configured.camera_model.sources.model_dump(mode="json")
            if configured
            else None,
            "source_identity": source_id,
            "dependencies": dependency_id,
            "actions": rows,
            "observations": len(stream.visible_prefix(cutoff=last.received_at)),
            "semantic_transitions": len(stream.execution_traces()),
            "recovered_during_same_environment_session": any(
                r.get("step") == 0 and "action_id" in r for r in rows
            ),
            "complete_sensor_action_probe": any("action_id" in r for r in rows)
            and all(r["success"] and r["pixel_changed"] for r in rows if "action_id" in r),
        }
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
    finally:
        executor.close()
        store.close()


if __name__ == "__main__":
    main()
