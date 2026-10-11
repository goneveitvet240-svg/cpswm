"""Opt-in D0 location inspection; no actor/habit write authorization is added.

A joint HABIT distribution is only a query-order proposal here, not a calibrated
current-location posterior. The ideal detector is an explicit oracle upper bound.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from uuid import UUID

from cpswm.system.evaluation_operations.project_two_action_benchmark import _Prediction
from cpswm.system.reproducibility import content_sha256, content_uuid


class LocationSearchPolicy(StrEnum):
    PASSIVE = "passive"
    CURRENT_RANK = "current_rank"
    HABIT_RANK = "habit_rank"
    RECENT_ID = "recent_id"


@dataclass(frozen=True, slots=True)
class LocationInspectionRequest:
    action_id: UUID
    episode_id: UUID
    step_id: UUID
    object_id: UUID
    location_id: UUID


@dataclass(frozen=True, slots=True)
class LocationInspectionReceipt:
    request: LocationInspectionRequest
    ordinal: int
    found: bool
    receipt_sha256: str


class D0LocationInspectionEnvironment:
    """Select/pay first, then return only whether THIS location contains target.

    Truth lookup stays on the environment side of the interface. This is a code
    boundary, not process isolation or a claim of adversarial Python security.
    """

    def __init__(self, episode, locations, truth_location: Callable[[UUID], UUID], *, budget=2):
        if type(budget) is not int or budget < 0:
            raise ValueError("inspection budget must be a nonnegative integer")
        self.episode_id = episode.episode_id
        self.locations = tuple(locations)
        if not self.locations or len(set(self.locations)) != len(self.locations):
            raise ValueError("inspection support must be nonempty and unique")
        self.budget = budget
        self._steps = tuple((s.step_id, s.object_instance_id) for s in episode.steps)
        self._truth_location = truth_location
        self._index = -1
        self._queried: set[UUID] = set()
        self.requests: list[LocationInspectionRequest] = []
        self._receipts: dict[UUID, LocationInspectionReceipt] = {}

    def begin_step(self, step_id):
        if self._index + 1 >= len(self._steps) or self._steps[self._index + 1][0] != step_id:
            raise ValueError("location inspection step is stale or out of sequence")
        self._index += 1
        self._queried.clear()

    def inspect(self, request: LocationInspectionRequest) -> LocationInspectionReceipt:
        if self._index < 0:
            raise ValueError("inspection requires a current step")
        if (
            request.episode_id != self.episode_id
            or (request.step_id, request.object_id) != self._steps[self._index]
        ):
            raise ValueError("inspection request has wrong episode/step/object binding")
        if request.action_id in {r.action_id for r in self.requests}:
            raise ValueError("inspection action ID cannot be reused")
        if request.location_id not in self.locations or request.location_id in self._queried:
            raise ValueError("inspection location is outside support or already queried")
        if len(self._queried) >= self.budget:
            raise ValueError("inspection budget exhausted")
        # This committed selection and charge precede any hidden-state access.
        self.requests.append(request)
        self._queried.add(request.location_id)
        found = request.location_id == self._truth_location(request.step_id)
        ordinal = len(self._queried)
        digest = content_sha256({"request": request, "ordinal": ordinal, "found": found})
        receipt = LocationInspectionReceipt(request, ordinal, found, digest)
        self._receipts[request.action_id] = receipt
        return receipt

    def validate_receipt(self, request, receipt):
        if self._index < 0 or request.step_id != self._steps[self._index][0]:
            raise ValueError("inspection receipt is stale")
        if receipt.request != request or self._receipts.get(request.action_id) != receipt:
            raise ValueError("inspection receipt was not issued for this action")


class ActiveLocationSearchState:
    """Existing complete inference/feedback, plus a separate search projection."""

    def __init__(self, state, environment, *, policy: LocationSearchPolicy | str):
        self.state = state
        self.environment = environment
        self.policy = LocationSearchPolicy(policy)
        self.current_search_location: UUID | None = None
        self.search_receipts: list[dict] = []
        self._step = None

    def observe(self, step):
        self.environment.begin_step(step.step_id)
        self.state.observe(step)
        self._step = step
        if step.after is not None and step.after.detected_location_id is not None:
            self.current_search_location = step.after.detected_location_id

    def predict(self):
        step = self._step
        if step is None:
            raise ValueError("active search requires an observed step")
        if self.search_receipts and self.search_receipts[-1]["step_id"] == str(step.step_id):
            raise ValueError("active search cannot predict twice for one step")
        native = self.state.predict()
        habit = dict(self.state.task_readout_receipts[-1].habit_distribution)
        current_rank = list(native.search_order)
        if self.current_search_location is not None:
            current_rank.remove(self.current_search_location)
            current_rank.insert(0, self.current_search_location)
        if self.policy is LocationSearchPolicy.HABIT_RANK:
            query_order = sorted(habit, key=lambda key: (-habit[key], str(key)))
        elif self.policy is LocationSearchPolicy.RECENT_ID:
            query_order = sorted(current_rank, key=str)
            if self.current_search_location is not None:
                query_order.remove(self.current_search_location)
                query_order.insert(0, self.current_search_location)
        else:
            query_order = list(current_rank)
        before_snapshot = self.state.spine.current_snapshot.snapshot_id
        before_committed = dict(self.state.spine._committed_events)
        receipts, negatives, detected = [], [], None
        missing = step.after is None or step.after.detected_location_id is None
        if missing and self.policy is not LocationSearchPolicy.PASSIVE:
            for location in query_order[: self.environment.budget]:
                request = LocationInspectionRequest(
                    content_uuid(
                        "active-location-inspect",
                        (self.environment.episode_id, step.step_id, location),
                    ),
                    self.environment.episode_id,
                    step.step_id,
                    step.object_instance_id,
                    location,
                )
                receipt = self.environment.inspect(request)
                self.environment.validate_receipt(request, receipt)
                receipts.append(
                    {**asdict(receipt), "request": {k: str(v) for k, v in asdict(request).items()}}
                )
                if receipt.found:
                    detected = location
                    self.current_search_location = location
                    break
                negatives.append(location)
        rank = [x for x in current_rank if x not in negatives]
        if detected is not None:
            rank.remove(detected)
            rank.insert(0, detected)
        rank.extend(x for x in current_rank if x in negatives)
        prediction = _Prediction(native.put_back, tuple(rank), native.unknown_probability)
        index = self.state._prediction_index - 1
        self.state.bind_prediction_trace(prediction, index)
        if (
            self.state.spine.current_snapshot.snapshot_id != before_snapshot
            or self.state.spine._committed_events != before_committed
        ):
            raise AssertionError("location-only inspection mutated actor/habit state")
        self.search_receipts.append(
            {
                "step_id": str(step.step_id),
                "policy": self.policy.value,
                "budget": self.environment.budget,
                "missing_passive_location": missing,
                "native_put_back": str(native.put_back),
                "native_search_order": list(map(str, native.search_order)),
                "query_order": list(map(str, query_order)),
                "habit_proposal": {str(k): v for k, v in habit.items()},
                "inspections": receipts,
                "found_location": None if detected is None else str(detected),
                "search_memory_location": None
                if self.current_search_location is None
                else str(self.current_search_location),
                "final_search_order": list(map(str, rank)),
                "location_query_changed_habit_state": False,
            }
        )
        return prediction

    def feedback(self, step):
        self.state.feedback(step)

    def __getattr__(self, name):
        return getattr(self.state, name)
