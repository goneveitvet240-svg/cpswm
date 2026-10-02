"""Fixed/active/no-update live pilot in one frozen world, with exact start checks.

Orchestration resets only the camera between complete arms. It never supplies an
object ID or pose to a task policy. Scoring is a subsequent separate invocation.
"""

import argparse
import copy
import json
import shutil
from pathlib import Path
from uuid import uuid4

import torch
from run_surface_episode import run

from cpswm.system.unity_observation import UnityObservationExecutor


def main(a):
    a.output.mkdir(parents=True, exist_ok=False)
    camera = UnityObservationExecutor(
        python=a.sdk_python,
        worker=Path(__file__).with_name("unity_surface_pipeline_worker.py").resolve(),
        binary=a.binary,
        house=a.house,
        log_dir=a.output / "shared-transport",
        household_id=uuid4(),
        session_id=uuid4(),
        trace_id=uuid4(),
        image_size=320,
        sensor_profile="rgbd_self_pose",
    )
    arms = []
    try:
        names = (
            ("memory-retain", "memory-reset") if a.memory_only else ("fixed", "active", "no-update")
        )
        for name in names:
            assert camera._process.stdin is not None
            camera._process.stdin.write(json.dumps(dict(reset_camera=True)) + "\n")
            camera._process.stdin.flush()
            if camera._receive() != dict(reset=True):
                raise ValueError("shared frozen scene camera reset failed")
            options = copy.copy(a)
            options.output = a.output / name
            options.no_update = name == "no-update"
            options.reset_before = 2 if name == "memory-reset" else None
            options.model = a.model if name == "active" else None
            run(options, shared_camera=camera)
            arms.append(name)
            print(json.dumps(dict(completed_arm=name)), flush=True)
    finally:
        camera.close()
        for name in arms:
            shutil.copytree(
                a.output / "shared-transport/evaluator_only",
                a.output / name / "transport/evaluator_only",
            )
        (a.output / "manifest.json").write_text(
            json.dumps(
                dict(
                    arms=arms,
                    budget=len(a.degrees),
                    degrees=a.degrees,
                    queries=a.target,
                    common_allowed_actions=[
                        dict(action="RotateRight", degrees=d) for d in (1.0, 5.0, 30.0)
                    ],
                    initialization="single frozen world; camera reset before each arm",
                    fairness="requires isolated exact initial RGB/depth/pose/world comparison",
                    scope="single-house development pilot; controlled semantic bootstrap",
                    memory_only=a.memory_only,
                    later_task_budget=1 if a.memory_only else None,
                ),
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("output", "weights", "mask-weights", "sdk-python", "binary", "house", "model"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--degrees", type=float, nargs="+", required=True)
    p.add_argument("--target", nargs="+", required=True)
    p.add_argument("--memory-only", action="store_true")
    a = p.parse_args()
    torch.set_num_threads(2)
    main(a)
