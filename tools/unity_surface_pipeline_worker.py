"""Same public Unity RGB-D boundary; complete instance masks stay evaluator-only."""

import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np
from unity_camera_feedback_worker import method_response
from unity_target_sequence_worker import TargetSequenceRecorder


class SurfacePipelineRecorder(TargetSequenceRecorder):
    def prepare(self):
        super().prepare()
        self.initial_agent = copy.deepcopy(self.controller.last_event.metadata["agent"])
        self.initial_objects = self.object_signature(self.controller.last_event)

    @staticmethod
    def object_signature(event):
        return [
            (o["objectId"], o["position"], o["rotation"], o["axisAlignedBoundingBox"])
            for o in event.metadata["objects"]
        ]

    def reset_camera(self):
        # Evaluation orchestration only. No target, pose or object state is sent
        # by the inference policy. The same frozen world is reused between arms.
        a = self.initial_agent
        event = self.step(
            dict(
                action="TeleportFull",
                position=a["position"],
                rotation=a["rotation"],
                horizon=a["cameraHorizon"],
                standing=a["isStanding"],
                forceAction=True,
            ),
            None,
        )
        if self.object_signature(event) != self.initial_objects:
            raise ValueError("camera reset changed the frozen world")

    def record(self, event, request, owner):
        super().record(event, request, owner)
        index = len(self.events) - 1
        ids = sorted(event.instance_masks)
        np.savez_compressed(
            self.private / "sdk-events" / f"{index:03d}-instances.npz",
            masks=np.asarray([event.instance_masks[k] for k in ids], dtype=bool),
        )
        (self.private / "sdk-events" / f"{index:03d}-instances.json").write_text(
            json.dumps(ids) + "\n"
        )


def main(recorder_type=SurfacePipelineRecorder):
    from ai2thor.controller import Controller

    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("binary", "house", "log-dir"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--image-size", type=int, choices=(320, 640), required=True)
    parser.add_argument("--sensor-profile", choices=("rgb", "rgbd_self_pose"), default="rgb")
    args = parser.parse_args()
    from unity_rgbd_capture import FAR, NEAR, rgbd_response

    rgbd = args.sensor_profile == "rgbd_self_pose"
    house = json.loads(Path(args.house).read_text())
    target = house["metadata"].pop("cpswm_diagnostic_target")
    private = Path(args.log_dir) / "evaluator_only"
    private.mkdir()

    class LocalLogs(Controller):
        @property
        def log_dir(self):
            return args.log_dir

    controller = LocalLogs(
        local_executable_path=args.binary,
        scene=house,
        width=args.image_size,
        height=args.image_size,
        fieldOfView=60,
        renderInstanceSegmentation=True,
        **(
            dict(
                renderDepthImage=True,
                cameraNearPlane=NEAR,
                cameraFarPlane=FAR,
                add_depth_noise=False,
            )
            if rgbd
            else {}
        ),
        server_timeout=30.0,
        server_start_timeout=30.0,
    )
    try:
        initial = controller.last_event.metadata
        (private / "initial.json").write_text(json.dumps(initial, indent=2) + "\n")
        if not any(
            o["objectId"] == target and o["objectType"] == "Apple" for o in initial["objects"]
        ):
            raise ValueError("history diagnostic target missing")
        recorder = recorder_type(controller, private, target)
        recorder.prepare()
        print("CPSWM_RESPONSE " + json.dumps(dict(ready=True)), flush=True)
        for line in sys.stdin:
            command = json.loads(line)
            if command == {"stop": True}:
                break
            if command == {"reset_camera": True}:
                recorder.reset_camera()
                print("CPSWM_RESPONSE " + json.dumps(dict(reset=True)), flush=True)
                continue
            event = recorder.observe(command)
            if event.frame.shape != (args.image_size, args.image_size, 3):
                raise ValueError("history camera image size changed")
            print(
                "CPSWM_RESPONSE "
                + json.dumps(
                    (rgbd_response if rgbd else method_response)(command["action_id"], event)
                ),
                flush=True,
            )
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
