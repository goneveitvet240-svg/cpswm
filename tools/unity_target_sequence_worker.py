"""Existing frozen scene transport with evaluator-only instance boxes retained."""

import json

from unity_history_loop_worker import HistoryCameraRecorder, main


class TargetSequenceRecorder(HistoryCameraRecorder):
    def record(self, event, request, owner):
        super().record(event, request, owner)
        index = len(self.events) - 1
        boxes = {
            str(key): [int(v) for v in box] for key, box in event.instance_detections2D.items()
        }
        (self.private / "sdk-events" / f"{index:03d}-boxes.json").write_text(
            json.dumps(boxes, sort_keys=True) + "\n"
        )


if __name__ == "__main__":
    main(TargetSequenceRecorder)
