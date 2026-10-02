"""One executable natural RGB-D/owner/report episode; controlled semantic bootstrap.

The fixed policy is explicit and budgeted. Evaluator-only SDK outputs never enter
inference. This development runner does not claim natural event/actor inference.
"""

import argparse
import base64
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import torch
from run_correction_replay_comparison import OracleProducer
from surface_pipeline_fixture import SOURCE, make_case, restore_joint
from test_native_neural_production import checkpoints
from test_owned_rgbd_support import RGBDSupportDecoder

from cpswm.system.continuous_state_store import ContinuousStateStore
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput
from cpswm.system.surface_episode import (
    collect_scheduled_surface,
    effective_surface_state,
    policy_reason,
    surface_report,
)
from cpswm.system.unity_observation import UnityObservationExecutor


def save(path, value):
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=str, allow_nan=False) + "\n"
    )


def reports(stream, queries, reference):
    return [
        surface_report(
            stream, category=q["category"], ordinal=q["ordinal"], reference_action=reference
        )
        for q in queries
    ]


def run(args, shared_camera=None):
    root = args.output
    root.mkdir(parents=True, exist_ok=False)

    class Factory:
        def mktemp(self, name):
            p = root / name
            p.mkdir()
            return p

    schedule = [
        dict(action="Pass" if d == 0 else "RotateRight" if d > 0 else "RotateLeft", degrees=abs(d))
        for d in args.degrees
    ]
    queries = [
        dict(category=s.rsplit(":", 1)[0], ordinal=int(s.rsplit(":", 1)[1])) for s in args.target
    ]
    model = json.loads(args.model.read_text()) if getattr(args, "model", None) else None
    policy = (
        None
        if model is None
        else dict(
            mode="empirical_joint",
            schedule=schedule,
            budget=len(schedule),
            queries=queries,
            model=model["model"],
            model_pin=model["pin"],
            action_cost=0.0001,
            alternatives=[dict(action="RotateRight", degrees=d) for d in (1.0, 5.0)],
        )
    )
    result = dict(
        status="RUNNING",
        scope="natural surface task; controlled semantic bootstrap",
        policy=policy or dict(mode="fixed_scan", schedule=schedule, budget=len(schedule)),
        updates_enabled=not getattr(args, "no_update", False),
        queries=queries,
        schedule=schedule,
        budget=len(schedule),
        steps=[],
        failures=[],
    )
    case = None
    camera = shared_camera
    initial_dispatches = len(camera._seen) if camera else 0
    try:
        case = make_case(
            root / "state.sqlite",
            checkpoints.__wrapped__(Factory()),
            args.weights,
            args.mask_weights,
            schedule=schedule,
            policy=policy,
            enabled=not getattr(args, "no_update", False),
        )
        stream = case["stream"]
        if camera is None:
            camera = UnityObservationExecutor(
                python=args.sdk_python,
                worker=Path(__file__).with_name("unity_surface_pipeline_worker.py").resolve(),
                binary=args.binary,
                house=args.house,
                log_dir=root / "transport",
                household_id=stream._scope[0],
                session_id=stream._scope[1],
                trace_id=stream._scope[2],
                image_size=320,
                sensor_profile="rgbd_self_pose",
            )
        else:
            camera.scope = stream._scope
            (root / "transport").mkdir()
        reference = None
        for index in range(len(schedule)):
            step = collect_scheduled_surface(
                stream, executor=camera, decision_time=datetime.now(UTC)
            )
            if step is None:
                view = stream.current_joint_decision_view()
                ids = tuple(
                    r.envelope().identity.observation_id
                    for r in stream.visible_prefix(cutoff=datetime.now(UTC))
                )
                result["stop"] = policy_reason(stream, view=view, source_ids=ids, index=index)
                break
            command, delivery, _update = step
            folder = root / "public" / f"{index:03d}"
            folder.mkdir(parents=True)
            save(
                folder / "raw.json",
                dict(
                    action_id=str(command.action_id),
                    action=command.action,
                    degrees=command.degrees,
                    decision_time=command.decision_time.isoformat(),
                    received_at=delivery.received_at.isoformat(),
                    success=delivery.success,
                    error=delivery.error,
                    observations=[
                        dict(
                            envelope_json=r.envelope_json,
                            payload_base64=base64.b64encode(r.payload_bytes).decode(),
                            capture_receipt_sha256=r.capture_receipt_sha256,
                            depth_unit=r.depth_unit,
                        )
                        for r in delivery.observations
                    ],
                ),
            )
            if reference is None:
                reference = str(command.action_id)
            if not delivery.success:
                result["failures"].append(dict(index=index, error=delivery.error))
                save(root / "result.json", result)
                continue
            report = reports(stream, queries, reference)
            save(folder / "reports.json", report)
            data = effective_surface_state(stream)
            save(folder / "surface.json", data)
            result["steps"].append(
                dict(
                    index=index,
                    action_id=str(command.action_id),
                    reports=report,
                    source_view_sha256=data["view_sha256"],
                )
            )
            save(root / "result.json", result)
            print(
                json.dumps(
                    dict(
                        index=index,
                        action=str(command.action_id),
                        reports=[r["status"] for r in report],
                    )
                ),
                flush=True,
            )
        result.update(
            status="COMPLETED" if not result["failures"] else "COMPLETED_WITH_FAILURES",
            reference_action=reference,
            physical_dispatches=len(camera._seen) - initial_dispatches,
        )
        save(
            root / "restore.json",
            dict(
                config=case["config"],
                models=case["models"],
                checkpoint=str(case["checkpoint"]),
                pin=case["pin"],
                queries=queries,
                reference_action=reference,
            ),
        )
        with sqlite3.connect(root / "copy.db") as db:
            case["store"]._db.backup(db)
        result["final_reports"] = reports(stream, queries, reference)
    except BaseException as exc:
        result.update(status="FAILED")
        result["failures"].append(dict(type=type(exc).__name__, message=str(exc)))
        raise
    finally:
        save(root / "result.json", result)
        if camera and shared_camera is None:
            camera.close()
        if case:
            case["store"].close()


def restore(args):
    root = args.output
    config = json.loads((root / "restore.json").read_text())
    store = ContinuousStateStore(
        args.database or root / "copy.db",
        source_identity=SOURCE,
        dependency_identity=content_sha256(sys.version),
    )

    def unused(*args):
        raise AssertionError("restore must not reexecute semantic bootstrap")

    try:
        stream = ContinuousEvidenceInput.resume(
            store,
            producer=OracleProducer(),
            context_builder=unused,
            joint_producer=restore_joint(config),
            observation_decoder=RGBDSupportDecoder(),
        )
        before = reports(stream, config["queries"], config["reference_action"])
        expected = json.loads((root / "result.json").read_text())["final_reports"]
        if before != expected:
            raise ValueError("fresh reports differ")
        state = effective_surface_state(stream)
        physical = len(stream.observation_history())
        from uuid import UUID

        if args.withdraw is not None:
            action = UUID(state["action_ids"][args.withdraw])
            stream.withdraw_owned_position_observation(
                action, reason="predeclared pipeline withdrawal probe"
            )
        if args.reset:
            for action in reversed(state["action_ids"]):
                stream.withdraw_owned_position_observation(
                    UUID(action), reason="predeclared later-task visual-memory reset control"
                )
        after = reports(stream, config["queries"], config["reference_action"])
        if len(stream.observation_history()) != physical:
            raise ValueError("withdrawal changed physical journal")
        save(
            root
            / (
                "memory-reset.json"
                if args.reset
                else "fresh.json"
                if args.withdraw is None
                else f"withdraw-{args.withdraw}.json"
            ),
            dict(
                before=before,
                after=after,
                physical_dispatches=physical,
                fresh_equal=True,
                later_task_actions=0,
                memory_reset=args.reset,
                scope="static scene lookup at recorded epoch; no temporal extrapolation",
            ),
        )
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("run")
    for key in ["output", "weights", "mask-weights", "sdk-python", "binary", "house"]:
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--degrees", type=float, nargs="+", required=True)
    p.add_argument("--target", nargs="+", required=True)
    p.add_argument("--model", type=Path)
    p.add_argument("--no-update", action="store_true")
    p = sub.add_parser("restore")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--withdraw", type=int)
    p.add_argument("--database", type=Path)
    p.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    torch.set_num_threads(2)
    (run if args.mode == "run" else restore)(args)
