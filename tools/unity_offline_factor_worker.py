"""Fixed, target-free RGB-D collection with isolated per-event simulation labels.

Run in the existing SDK interpreter. No detector, learned policy or target lookup
can choose a viewpoint. Labels are saved offline; the public response is the
existing RGB-D/camera whitelist.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from offline_factor_manifest import OBSERVATION_ACTIONS
from unity_camera_feedback_worker import validate_request
from unity_instance_audit_worker import export_instances
from unity_rgbd_capture import FAR, NEAR, rgbd_response


class OfflineFactorRecorder:
    def __init__(self, controller, private, image_size):
        self.controller, self.private, self.image_size = controller, private, image_size
        self.events, self.seen, self.frames = [], set(), 0
        self.record(controller.last_event, None, None)

    def record(self, event, request, owner):
        size = self.image_size
        if (
            event.depth_frame is None
            or event.frame.dtype != np.uint8
            or event.frame.shape != (size, size, 3)
            or event.depth_frame.dtype != np.float32
            or event.depth_frame.shape != (size, size)
        ):
            raise ValueError("offline RGB-D image geometry changed")
        index = len(self.events)
        directory = self.private / "sdk-events"
        directory.mkdir(exist_ok=True)
        record = dict(index=index, requested=request, owner=owner, metadata=event.metadata)
        (directory / f"{index:03d}.json").write_text(json.dumps(record, indent=2) + "\n")
        for suffix, values in (("rgb", event.frame), ("depth", event.depth_frame)):
            np.save(directory / f"{index:03d}-{suffix}.npy", values, allow_pickle=False)
        export_instances(event, self.private / "instances", index, owner)
        self.events.append(record)

    def step(self, request, owner):
        event = self.controller.step(**request)
        self.record(event, request, owner)
        if (
            event.metadata.get("lastActionSuccess") is not True
            or event.metadata.get("lastAction") != request["action"]
        ):
            raise ValueError("offline capture SDK action failed or differs")
        return event

    def prepare(self):
        if len(self.events) != 1:
            raise ValueError("offline preparation cannot repeat")
        for action in ("PausePhysicsAutoSim", "Pass", "Pass"):
            self.step(dict(action=action), None)

    def observe(self, request):
        identity, action, kwargs = validate_request(request, self.seen)
        if (
            len(self.events) != 4 + self.frames
            or self.frames >= len(OBSERVATION_ACTIONS)
            or (action, request["degrees"]) != OBSERVATION_ACTIONS[self.frames]
        ):
            raise ValueError("offline camera action differs from fixed schedule")
        self.seen.add(identity)
        event = self.step(dict(action=action, **kwargs), identity)
        self.frames += 1
        return event


def main():
    from ai2thor.controller import Controller

    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("binary", "house", "log-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--image-size", type=int, choices=(320,), required=True)
    parser.add_argument("--sensor-profile", choices=("rgbd_self_pose",), required=True)
    args = parser.parse_args()
    house = json.loads(args.house.read_text())
    private = args.log_dir / "evaluator_only"
    private.mkdir()

    class LocalLogs(Controller):
        @property
        def log_dir(self):
            return str(args.log_dir)

    controller = LocalLogs(
        local_executable_path=str(args.binary),
        scene=house,
        width=args.image_size,
        height=args.image_size,
        fieldOfView=60,
        renderInstanceSegmentation=True,
        renderDepthImage=True,
        cameraNearPlane=NEAR,
        cameraFarPlane=FAR,
        add_depth_noise=False,
        server_timeout=30.0,
        server_start_timeout=30.0,
    )
    try:
        recorder = OfflineFactorRecorder(controller, private, args.image_size)
        if controller.last_event.metadata.get("lastActionSuccess") is not True:
            raise ValueError("offline original house initialization failed")
        recorder.prepare()
        print("CPSWM_RESPONSE " + json.dumps(dict(ready=True)), flush=True)
        for line in sys.stdin:
            request = json.loads(line)
            if request == {"stop": True}:
                break
            event = recorder.observe(request)
            print(
                "CPSWM_RESPONSE " + json.dumps(rgbd_response(request["action_id"], event)),
                flush=True,
            )
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
