"""Same public history worker with private, per-event full instance evaluation."""

import numpy as np
from unity_history_loop_worker import HistoryCameraRecorder, main
from unity_instance_audit_worker import export_instances


class VisualHistoryCameraRecorder(HistoryCameraRecorder):
    def record(self, event, request, owner):
        index = len(self.events)
        super().record(event, request, owner)
        export_instances(event, self.private / "instances", index, owner)
        if event.depth_frame is not None:
            np.save(
                self.private / "sdk-events" / f"{index:03d}-depth.npy",
                np.ascontiguousarray(event.depth_frame),
                allow_pickle=False,
            )


if __name__ == "__main__":
    main(VisualHistoryCameraRecorder)
