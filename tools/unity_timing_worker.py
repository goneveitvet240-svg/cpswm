"""Matched diagnostic clock calls; only final actual Pass RGB enters public input."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from unity_camera_feedback_worker import method_response, validate_request

MODES = ("auto", "frozen", "stepped")
STEPS = 16
DT = 0.01


def schedule(mode, phase):
    if mode not in MODES or phase not in ("prepare", "clock", "observe"):
        raise ValueError("undeclared timing mode or phase")
    if phase == "prepare" and mode != "auto":
        return dict(action="PausePhysicsAutoSim")
    if phase == "clock" and mode == "stepped":
        return dict(action="AdvancePhysicsStep", timeStep=DT)
    return dict(action="Pass")


def save_event(private, index, event, target, request, owner):
    directory = private / "sdk-events"
    directory.mkdir(exist_ok=True)
    mask = event.instance_masks.get(target, np.zeros(event.frame.shape[:2], dtype=bool))
    np.save(directory / f"{index:03d}-rgb.npy", event.frame, allow_pickle=False)
    np.save(directory / f"{index:03d}-mask.npy", mask, allow_pickle=False)
    record = dict(index=index, requested=request, owner=owner, metadata=event.metadata)
    (directory / f"{index:03d}.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


class TimingRecorder:
    def __init__(self, controller, private, target, mode):
        schedule(mode, "prepare")
        self.controller, self.private, self.target, self.mode = controller, private, target, mode
        self.events = []
        self.seen = set()
        self.frames = 0
        self._record(controller.last_event, None, None)

    def _record(self, event, request, owner):
        record = save_event(self.private, len(self.events), event, self.target, request, owner)
        self.events.append(record)
        (self.private / "timing.json").write_text(
            json.dumps(
                dict(mode=self.mode, sdk_events=len(self.events), frames=self.frames), indent=2
            )
            + "\n"
        )

    def _step(self, phase, owner):
        request = schedule(self.mode, phase)
        event = self.controller.step(**request)
        self._record(event, request, owner)
        if event.metadata.get("lastActionSuccess") is not True:
            raise ValueError(
                "timing SDK action failed: " + repr(event.metadata.get("errorMessage"))
            )
        if event.metadata.get("lastAction") != request["action"]:
            raise ValueError("timing SDK returned a different action")
        return event

    def prepare(self):
        if len(self.events) != 1:
            raise ValueError("timing preparation cannot repeat")
        return self._step("prepare", None)

    def observe(self, request):
        identity, action, _ = validate_request(request, self.seen)
        if action != "Pass" or self.frames >= STEPS or len(self.events) != 2 + 2 * self.frames:
            raise ValueError("timing observation outside fixed schedule")
        self.seen.add(identity)
        self._step("clock", identity)
        event = self._step("observe", identity)
        self.frames += 1
        return event


def main():
    from ai2thor.controller import Controller

    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("binary", "house", "log-dir"):
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--image-size", type=int, choices=(320, 640), required=True)
    args = parser.parse_args()
    house = json.loads(Path(args.house).read_text())
    target = house["metadata"].pop("cpswm_diagnostic_target")
    mode = house["metadata"].pop("cpswm_timing_mode")
    schedule(mode, "prepare")
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
        server_timeout=30.0,
        server_start_timeout=30.0,
    )
    rows = []
    try:
        initial = controller.last_event.metadata
        (private / "initial.json").write_text(json.dumps(initial, indent=2) + "\n")
        if not any(
            o["objectId"] == target and o["objectType"] == "Apple" for o in initial["objects"]
        ):
            raise ValueError("diagnostic target missing")
        clock = TimingRecorder(controller, private, target, mode)
        clock.prepare()
        print("CPSWM_RESPONSE " + json.dumps({"ready": True}), flush=True)
        for line in sys.stdin:
            request = json.loads(line)
            if request == {"stop": True}:
                break
            event = clock.observe(request)
            identity = request["action_id"]
            response = method_response(identity, event)
            index = len(rows)
            mask = event.instance_masks.get(target, np.zeros(event.frame.shape[:2], dtype=bool))
            yy, xx = np.where(mask)
            box = (
                None
                if not len(xx)
                else [int(xx.min()), int(yy.min()), int(xx.max() + 1), int(yy.max() + 1)]
            )
            obj = next(o for o in event.metadata["objects"] if o["objectId"] == target)
            np.save(private / f"{index:03d}-rgb.npy", event.frame, allow_pickle=False)
            np.save(private / f"{index:03d}-mask.npy", mask, allow_pickle=False)
            rows.append(
                dict(
                    index=index,
                    request=request,
                    success=response["success"],
                    error=response["error"],
                    capture_time=response["capture_time"],
                    target_pixels=int(mask.sum()),
                    target_bbox=box,
                    target_sdk_visible=obj["visible"],
                    target_position=obj["position"],
                    agent=event.metadata["agent"],
                    camera_position=event.metadata["cameraPosition"],
                    fov=event.metadata["fov"],
                    image_size=[args.image_size, args.image_size],
                    sdk_index=3 + 2 * index,
                )
            )
            (private / "actions.json").write_text(json.dumps(rows, indent=2) + "\n")
            (private / "timing.json").write_text(
                json.dumps(
                    dict(mode=mode, sdk_events=len(clock.events), frames=clock.frames), indent=2
                )
                + "\n"
            )
            print("CPSWM_RESPONSE " + json.dumps(response), flush=True)
    finally:
        controller.stop()


if __name__ == "__main__":
    main()
