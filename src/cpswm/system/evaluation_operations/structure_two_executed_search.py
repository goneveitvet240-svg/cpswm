"""Execute terminal D0 retrieval and carry only paid location evidence forward."""

from __future__ import annotations

from dataclasses import asdict

from cpswm.system.evaluation_operations.structure_two_active_location_search import (
    ActiveLocationSearchState,
    D0LocationInspectionEnvironment,
    LocationInspectionRequest,
)
from cpswm.system.reproducibility import content_sha256, content_uuid


def receipt_payload(receipt):
    return {
        **asdict(receipt),
        "request": {k: str(v) for k, v in asdict(receipt.request).items()},
    }


class ExecutedD0SearchEnvironment:
    """Probe then completion; one paid check per registered location per step."""

    def __init__(self, episode, locations, truth_location):
        self.core = D0LocationInspectionEnvironment(
            episode, locations, truth_location, budget=len(locations)
        )
        self.episode_id = episode.episode_id
        self.locations = self.core.locations
        self.budget = 2  # Existing active wrapper's PROBE budget only.
        self.phase = "closed"
        self.step_receipts = []
        self.found = None
        self._start = 0
        self._issued_phases = {}

    @property
    def requests(self):
        return self.core.requests[self._start :]

    def begin_step(self, step_id):
        if self.phase != "closed":
            raise ValueError("previous search is not completed")
        self.core.begin_step(step_id)
        self._start = len(self.core.requests)
        self.step_receipts = []
        self.found = None
        self.phase = "probe"

    def inspect(self, request):
        if self.phase not in ("probe", "completion") or self.found is not None:
            raise ValueError("search is closed or already found")
        if self.phase == "probe" and len(self.requests) >= self.budget:
            raise ValueError("probe budget exhausted")
        receipt = self.core.inspect(request)
        self._issued_phases[request.action_id] = self.phase
        payload = receipt_payload(receipt)
        staged = {"phase": self.phase, "receipt": payload}
        self.step_receipts.append({**staged, "stage_sha256": content_sha256(staged)})
        if receipt.found:
            self.found = request.location_id
        return receipt

    def validate_receipt(self, request, receipt):
        self.core.validate_receipt(request, receipt)
        if self._issued_phases.get(request.action_id) != self.phase:
            raise ValueError("receipt belongs to another execution phase")

    def finish_probing(self):
        if self.phase != "probe":
            raise ValueError("probe phase already finished or not started")
        self.phase = "completion"

    def close(self):
        if self.phase != "completion":
            raise ValueError("completion phase required")
        if self.found is None and len(self.requests) != len(self.locations):
            raise ValueError("search cannot finish without found or exhausted support")
        self.phase = "closed"


class ExecutedLocationSearchState(ActiveLocationSearchState):
    """Keep the pre-completion prediction, execute it, then update search memory."""

    def __init__(self, state, environment, *, policy, carry_terminal_memory=True):
        super().__init__(state, environment, policy=policy)
        self.carry_terminal_memory = carry_terminal_memory
        self.execution_receipts = []
        self._pending_feedback = False

    def observe(self, step):
        if self._pending_feedback:
            raise ValueError("prior execution still needs framework feedback")
        super().observe(step)

    def predict(self):
        prediction = super().predict()
        step = self._step
        environment = self.environment
        before_snapshot = self.state.spine.current_snapshot.snapshot_id
        before_committed = dict(self.state.spine._committed_events)
        before_memory = self.current_search_location
        environment.finish_probing()
        checked = {r.location_id for r in environment.requests}
        for location in prediction.search_order:
            if environment.found is not None:
                break
            if location in checked:
                continue
            request = LocationInspectionRequest(
                content_uuid(
                    "executed-location-completion",
                    (environment.episode_id, step.step_id, location),
                ),
                environment.episode_id,
                step.step_id,
                step.object_instance_id,
                location,
            )
            receipt = environment.inspect(request)
            environment.validate_receipt(request, receipt)
            checked.add(location)
        environment.close()
        if self.carry_terminal_memory:
            # A full negative sweep invalidates stale search memory as well.
            self.current_search_location = environment.found
        if (
            self.state.spine.current_snapshot.snapshot_id != before_snapshot
            or self.state.spine._committed_events != before_committed
        ):
            raise AssertionError("terminal retrieval mutated actor/habit state")
        self.execution_receipts.append(
            {
                "step_id": str(step.step_id),
                "carry_terminal_memory": self.carry_terminal_memory,
                "probe_budget": environment.budget,
                "total_budget": len(environment.locations),
                "submitted_search_order": list(map(str, prediction.search_order)),
                "staged_receipts": list(environment.step_receipts),
                "found_location": None if environment.found is None else str(environment.found),
                "status": "found" if environment.found is not None else "support_exhausted",
                "paid_checks": len(environment.requests),
                "search_memory_before_completion": None
                if before_memory is None
                else str(before_memory),
                "search_memory_after_completion": None
                if self.current_search_location is None
                else str(self.current_search_location),
                "location_execution_changed_habit_state": False,
            }
        )
        self._pending_feedback = True
        # Do not turn the observed terminal answer into a retroactive prediction.
        return prediction

    def feedback(self, step):
        if not self._pending_feedback or step.step_id != self._step.step_id:
            raise ValueError("feedback has no matching completed search")
        super().feedback(step)
        self._pending_feedback = False
