"""One frozen live scene, bounded camera commands, private full SDK trace."""

import argparse
import json
import sys
from pathlib import Path

from unity_camera_feedback_worker import method_response, validate_request
from unity_timing_worker import save_event


class HistoryCameraRecorder:
    def __init__(self, controller, private, target):
        self.controller, self.private, self.target = controller, private, target
        self.events, self.seen = [], set()
        self.record(controller.last_event, None, None)

    def record(self, event, request, owner):
        self.events.append(
            save_event(self.private, len(self.events), event, self.target, request, owner)
        )

    def step(self, request, owner):
        event = self.controller.step(**request)
        self.record(event, request, owner)
        if (
            event.metadata.get("lastActionSuccess") is not True
            or event.metadata.get("lastAction") != request["action"]
        ):
            raise ValueError("history camera SDK action failed or mismatched")
        return event

    def prepare(self):
        if len(self.events) != 1:
            raise ValueError("history preparation cannot repeat")
        for action in ("PausePhysicsAutoSim", "Pass", "Pass"):
            self.step(dict(action=action), None)

    def observe(self, command):
        if len(self.events) < 4:
            raise ValueError("history camera requires preparation")
        identity, action, kwargs = validate_request(command, self.seen)
        self.seen.add(identity)
        return self.step(dict(action=action, **kwargs), identity)


def main(recorder_type=HistoryCameraRecorder):
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
