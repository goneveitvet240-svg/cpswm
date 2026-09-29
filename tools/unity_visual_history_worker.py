"""Same public history worker with private, per-event full instance evaluation."""

from unity_history_loop_worker import HistoryCameraRecorder, main
from unity_instance_audit_worker import export_instances


class VisualHistoryCameraRecorder(HistoryCameraRecorder):
    def record(self, event, request, owner):
        index = len(self.events)
        super().record(event, request, owner)
        export_instances(event, self.private / "instances", index, owner)


if __name__ == "__main__":
    main(VisualHistoryCameraRecorder)
