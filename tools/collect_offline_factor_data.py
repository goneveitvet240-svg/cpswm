"""Fixed twelve-house offline supervision collection, with no target-driven views.

Each declared house is attempted exactly once. A failed house is retained and
blocks export readiness; no replacement, adaptive view selection or fitting is
performed here. Private labels are never sent through the public transport.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from offline_factor_manifest import OBSERVATION_ACTIONS, verify_plan, write_plan

from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_continuous_input import ObservationCommand
from cpswm.system.unity_observation import UnityObservationExecutor

ROOT = Path(__file__).resolve().parents[1]
SCOPE = "APPROVED_SIMULATOR_OFFLINE_INSTANCE_POSITION_DEVELOPMENT_DATA"
REASON = "fixed-offline-factor-view@1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def source_identity():
    return {
        str(path.relative_to(ROOT)): digest(path)
        for folder in ("src", "tests", "tools")
        for path in sorted((ROOT / folder).rglob("*.py"))
    }


def runtime_identity(python, binary):
    script = (
        "import ai2thor,hashlib,json,sys; from pathlib import Path; "
        "from importlib.metadata import version; "
        "root=Path(ai2thor.__file__).parent; "
        "print(json.dumps(dict(python_version=sys.version, "
        "versions={k:version(k) for k in ('ai2thor','numpy')}, "
        "sdk_source={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() "
        "for p in sorted(root.rglob('*.py'))})))"
    )
    result = subprocess.run(
        [str(python), "-c", script], capture_output=True, text=True, check=True, timeout=30
    )
    return dict(
        sdk=json.loads(result.stdout),
        python_sha256=digest(python.resolve()),
        unity_sha256=digest(binary),
    )


def provenance(house, binary):
    return dict(
        worker=digest(ROOT / "tools/unity_offline_factor_worker.py"),
        unity=digest(binary),
        house=digest(house),
        capture_configuration=content_sha256(("rgbd_self_pose", 320, 320, 60.0, 0.1, 20.0, False)),
    )


def capture_one(directory, house, sdk_python, binary):
    """One fresh owned controller; parent bounds and reaps its process group."""
    directory.mkdir(parents=True, exist_ok=False)
    public = directory / "public"
    public.mkdir()
    source, runtime = source_identity(), runtime_identity(sdk_python, binary)
    expected = provenance(house, binary)
    write_json(
        directory / "capture.json", dict(source_files=source, runtime=runtime, provenance=expected)
    )
    executor = UnityObservationExecutor(
        python=sdk_python,
        worker=ROOT / "tools/unity_offline_factor_worker.py",
        binary=binary,
        house=house,
        log_dir=directory / "unity-logs",
        household_id=uuid4(),
        session_id=uuid4(),
        trace_id=uuid4(),
        image_size=320,
        sensor_profile="rgbd_self_pose",
    )
    try:
        if executor.provenance != expected:
            raise ValueError("capture source changed before dispatch")
        for index, (action, degrees) in enumerate(OBSERVATION_ACTIONS):
            command = ObservationCommand(
                uuid4(), uuid4(), action, degrees, REASON, (), datetime.now(UTC)
            )
            delivery = executor.execute(command)
            # Preserve actual failed receipts as evidence; never re-dispatch.
            (public / f"{index:03d}-state.json").write_text(StateCodec().dumps((command, delivery)))
            if not delivery.success:
                raise ValueError("offline public action failed")
    finally:
        executor.close()
    if (
        source_identity() != source
        or runtime_identity(sdk_python, binary) != runtime
        or provenance(house, binary) != expected
    ):
        raise ValueError("source/runtime/house changed during offline capture")


def stop_owned_group(process):
    """Only signal this child session, including an orphaned Unity grandchild."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
    process.wait(timeout=10)


def validate_attempt_states(attempts):
    if [r["index"] for r in attempts] != list(range(1, 13)) or any(
        type(r["index"]) is not int for r in attempts
    ):
        raise ValueError("attempt state must retain the ordered twelve house matrix")
    common = {"index", "split", "status", "started_at", "finished_at"}
    previous = None
    for row in attempts:
        if row["status"] == "verified":
            if (
                set(row) != common | {"exit_code", "verification"}
                or type(row["exit_code"]) is not int
                or row["exit_code"] != 0
                or type(row["verification"]) is not dict
            ):
                raise ValueError("verified attempt state contradicts process outcome")
        elif row["status"] == "failed":
            required = common | {"error", "traceback"}
            if (
                not required <= set(row) <= required | {"exit_code"}
                or any(type(row[k]) is not str or not row[k] for k in ("error", "traceback"))
                or ("exit_code" in row and type(row["exit_code"]) is not int)
            ):
                raise ValueError(
                    "failed attempt state omits failure evidence or retains verification"
                )
        else:
            raise ValueError("unknown or interrupted attempt state")
        start, finish = (datetime.fromisoformat(row[k]) for k in ("started_at", "finished_at"))
        if (
            any(t.tzinfo is None or t.utcoffset().total_seconds() != 0 for t in (start, finish))
            or finish < start
            or (previous is not None and start < previous)
        ):
            raise ValueError("attempt state timestamps are not causal UTC")
        previous = finish


def runtime_partition_audit(plan, attempts):
    """Keep every source/runtime asset exposure, even when no target label survives."""
    validate_attempt_states(attempts)
    if len(attempts) != 12 or {r["index"] for r in attempts} != set(range(1, 13)):
        raise ValueError("runtime audit must retain all twelve house attempts")
    houses = {h["index"]: h for h in plan["houses"]}
    if any(r["split"] != houses[r["index"]]["split"] for r in attempts):
        raise ValueError("runtime split differs from fixed house partition")
    accepted = [row for row in attempts if row["status"] == "verified"]
    complete = len(attempts) == len(accepted) == 12 and {r["index"] for r in attempts} == set(
        range(1, 13)
    )
    seen_scope_ids, seen_action_ids = set(), set()
    for row in accepted:
        start, finish = (datetime.fromisoformat(row[k]) for k in ("started_at", "finished_at"))
        previous = start
        for frame in row["verification"]["frame_records"]:
            decision, capture, received = (
                datetime.fromisoformat(frame[k])
                for k in ("decision_time", "capture_time", "received_at")
            )
            if (
                any(
                    t.tzinfo is None or t.utcoffset().total_seconds() != 0
                    for t in (decision, capture, received)
                )
                or not start <= previous <= decision <= capture <= received <= finish
            ):
                raise ValueError("frame times differ from owning attempt state interval")
            previous = received
        scope_ids = row["verification"]["scope"]
        action_ids = [f["action_id"] for f in row["verification"]["frame_records"]]
        if (
            len(scope_ids) != 3
            or len(set(scope_ids)) != 3
            or seen_scope_ids.intersection(scope_ids)
            or len(action_ids) != 8
            or len(set(action_ids)) != 8
            or seen_action_ids.intersection(action_ids)
        ):
            raise ValueError("cross-house scope or action replay")
        seen_scope_ids.update(scope_ids)
        seen_action_ids.update(action_ids)
    exposures = {}
    for house in plan["houses"]:
        for asset in house["asset_ids"]:
            exposures.setdefault(asset, set()).add(house["split"])
    for row in accepted:
        for asset in row["verification"]["all_assets"]:
            exposures.setdefault(asset, set()).add(row["split"])
    unknown = any(r["verification"]["unknown_assets"] for r in accepted)
    result = []
    for row in accepted:
        static = {s["object_id"]: s for s in houses[row["index"]]["instances"]}
        for instance in row["verification"]["instances"]:
            asset = instance["asset_id"]
            seen = exposures.get(asset, set())
            reasons = list(instance.get("exclusion_reasons", []))
            original = static.get(instance["object_id"])
            if original is None or original["asset_id"] != asset:
                reasons.append("runtime_instance_not_bound_to_original_source_asset")
            else:
                reasons.extend(original["exclusion_reasons"])
            if instance.get("position_changed_during_initialization", True):
                reasons.append("initialization_pose_changed_or_unverified")
            if unknown:
                reasons.append("unknown_runtime_assets_prevent_complete_exposure_audit")
            if not complete:
                reasons.append("incomplete_twelve_house_runtime_audit")
            if not asset:
                reasons.append("unknown_runtime_asset")
            if {"train", "validation"} <= seen:
                reasons.append("asset_exposed_in_both_partitions")
            if row["split"] == "validation" and any(s not in ("train", "validation") for s in seen):
                reasons.append("asset_exposed_in_old_diagnostic")
            result.append(
                {
                    **instance,
                    "house_index": row["index"],
                    "split": row["split"],
                    "eligible": not reasons,
                    "exclusion_reasons": sorted(set(reasons)),
                }
            )
    return dict(
        complete_twelve_house_runtime_audit=complete,
        complete_asset_exposure_audit=complete and not unknown,
        # Eligibility is a data gate, not an exported supervised model or fit.
        supervision_export_performed=False,
        training_performed=False,
        asset_exposures={a: sorted(s) for a, s in sorted(exposures.items())},
        instances=result,
    )


def collect(output, archive, sdk_python, binary):
    from verify_offline_factor_capture import verify_capture

    output.mkdir(parents=True, exist_ok=False)
    plan = write_plan(archive, output / "plan")
    source, runtime = source_identity(), runtime_identity(sdk_python, binary)
    write_json(
        output / "configuration.json",
        dict(
            scope=SCOPE,
            source_files=source,
            runtime=runtime,
            attempts=list(range(1, 13)),
            actions=OBSERVATION_ACTIONS,
        ),
    )
    attempts = []
    for index in range(1, 13):
        verify_plan(archive, output / "plan")
        if source_identity() != source or runtime_identity(sdk_python, binary) != runtime:
            raise ValueError("frozen source/runtime changed; collection interrupted")
        house = next(h for h in plan["houses"] if h["index"] == index)
        house_path = output / "plan" / house["relative_path"]
        directory = output / f"house-{index:02d}"
        row = dict(
            index=index,
            split=house["split"],
            status="failed",
            started_at=datetime.now(UTC).isoformat(),
        )
        log = output / f"house-{index:02d}.log"
        with log.open("w") as stream:
            process = None
            try:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--one",
                        "--output",
                        str(directory),
                        "--house",
                        str(house_path),
                        "--sdk-python",
                        str(sdk_python),
                        "--binary",
                        str(binary),
                    ],
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    env={
                        **os.environ,
                        "PYTHONPATH": str(ROOT / "src") + os.pathsep + str(ROOT / "tools"),
                    },
                )
                code = process.wait(timeout=240)
                row["exit_code"] = code
                if code != 0:
                    raise ValueError(f"capture process exited {code}")
                manifest = json.loads((directory / "capture.json").read_text())
                if manifest != dict(
                    source_files=source, runtime=runtime, provenance=provenance(house_path, binary)
                ):
                    raise ValueError("capture identity differs from frozen matrix")
                row["verification"] = verify_capture(
                    directory, house_path, provenance(house_path, binary)
                )
                row["status"] = "verified"
            except (Exception, KeyboardInterrupt) as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
                row["traceback"] = traceback.format_exc()
                if isinstance(exc, KeyboardInterrupt):
                    raise
            finally:
                cleanup_error = None
                if process is not None:
                    try:
                        stop_owned_group(process)
                    except Exception as exc:
                        cleanup_error = exc
                        row["status"] = "cleanup_failed"
                        row["cleanup_error"] = f"{type(exc).__name__}: {exc}"
                row["finished_at"] = datetime.now(UTC).isoformat()
                attempts.append(row)
                write_json(output / "attempts.json", attempts)
                print(
                    json.dumps(
                        {k: row[k] for k in ("index", "status", "started_at", "finished_at")}
                    ),
                    flush=True,
                )
                if cleanup_error is not None:
                    raise RuntimeError(
                        "owned process cleanup uncertain; stop matrix"
                    ) from cleanup_error
    verify_plan(archive, output / "plan")
    audit = runtime_partition_audit(plan, attempts)
    write_json(output / "runtime-partition-audit.json", audit)
    write_json(
        output / "inventory.json",
        {
            str(p.relative_to(output)): digest(p)
            for p in sorted(output.rglob("*"))
            if p.is_file() and p.name != "inventory.json"
        },
    )
    return audit


def verify_collection(output, archive, sdk_python, binary, *, inventory_sha256=None):
    """Recompute saved outcomes under current caller pins, without modifying data."""
    from verify_offline_factor_capture import verify_capture

    if inventory_sha256 is not None and digest(output / "inventory.json") != inventory_sha256:
        raise ValueError("collection inventory differs from caller trusted external pin")
    before = {
        str(p.relative_to(output)): digest(p)
        for p in sorted(output.rglob("*"))
        if p.is_file() and p.name != "inventory.json"
    }
    if json.loads((output / "inventory.json").read_text()) != before:
        raise ValueError("collection bytes differ from saved inventory")
    plan = verify_plan(archive, output / "plan")
    config = json.loads((output / "configuration.json").read_text())
    if config != dict(
        scope=SCOPE,
        source_files=source_identity(),
        runtime=runtime_identity(sdk_python, binary),
        attempts=list(range(1, 13)),
        actions=[list(a) for a in OBSERVATION_ACTIONS],
    ):
        raise ValueError("collection identity differs from actual source/runtime pins")
    attempts = json.loads((output / "attempts.json").read_text())
    for row in attempts:
        if row["status"] != "verified":
            continue
        house = next(h for h in plan["houses"] if h["index"] == row["index"])
        house_path = output / "plan" / house["relative_path"]
        directory = output / f"house-{row['index']:02d}"
        if json.loads((directory / "capture.json").read_text()) != dict(
            source_files=config["source_files"],
            runtime=config["runtime"],
            provenance=provenance(house_path, binary),
        ):
            raise ValueError("house source/runtime identity differs")
        if (
            verify_capture(directory, house_path, provenance(house_path, binary))
            != row["verification"]
        ):
            raise ValueError("saved verification differs from raw evidence")
    audit = runtime_partition_audit(plan, attempts)
    if audit != json.loads((output / "runtime-partition-audit.json").read_text()):
        raise ValueError("saved partition audit differs from recomputation")
    after = {
        str(p.relative_to(output)): digest(p)
        for p in sorted(output.rglob("*"))
        if p.is_file() and p.name != "inventory.json"
    }
    if after != before:
        raise ValueError("collection changed during re-verification")
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("output", "archive", "sdk-python", "binary", "house"):
        parser.add_argument(
            "--" + key, type=Path, required=key in ("output", "sdk-python", "binary")
        )
    parser.add_argument(
        "--inventory-sha256",
        help="trusted external inventory digest; required for CLI re-verification",
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--one", action="store_true")
    modes.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.one:
        if args.house is None:
            parser.error("--one needs --house")
        capture_one(args.output, args.house, args.sdk_python, args.binary)
    else:
        if args.archive is None:
            parser.error("collection needs --archive")
        if args.verify:
            if args.inventory_sha256 is None:
                parser.error("--verify requires --inventory-sha256 from a trusted external record")
            result = verify_collection(
                args.output,
                args.archive,
                args.sdk_python,
                args.binary,
                inventory_sha256=args.inventory_sha256,
            )
        else:
            result = collect(args.output, args.archive, args.sdk_python, args.binary)
        print(
            json.dumps(
                {k: v for k, v in result.items() if k not in ("instances", "asset_exposures")},
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
