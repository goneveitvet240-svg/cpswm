"""Model-selected collection through one continuous runtime and its durable commands.

Policy builders consume the current joint view and arrived sensor prefix. Their
source bindings are required and retained with commands, but do not themselves
prove independent calibration. No fixed-scan fallback is available here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from cpswm.contracts.grounded_search import ActiveObservationPlan
from cpswm.perception_mapping.adapters.rgbd_capture import RawModalityObservation
from cpswm.system.joint_camera_policy import CameraModelSources, JointCameraProblem
from cpswm.system.native_joint_production import NativeJointProducer
from cpswm.system.structure_two_adaptive_runtime import AdaptiveExecutionContext
from cpswm.system.structure_two_continuous_input import (
    ContinuousEvidenceInput,
    DeliveryReceipt,
    GroundedTransition,
    ObservationCommand,
    ObservationDelivery,
    ObservationExecutor,
    PerceptionProducer,
)
from cpswm.system.structure_two_joint_consumption import JointDecisionView
from cpswm.system.structure_two_production_system import StructureTwoProductionSystem


class ContinuousCameraModel(Protocol):
    sources: CameraModelSources

    def problem(
        self,
        view: JointDecisionView,
        visible_prefix: tuple[RawModalityObservation, ...],
        *,
        decision_time: datetime,
        execution_history: tuple[tuple[ObservationCommand, str | ObservationDelivery], ...],
    ) -> JointCameraProblem: ...


@dataclass(frozen=True)
class ContinuousRuntimeComponents:
    system: StructureTwoProductionSystem
    producer: PerceptionProducer
    context_builder: Callable[
        [StructureTwoProductionSystem, GroundedTransition, datetime, int], AdaptiveExecutionContext
    ]
    camera_model: ContinuousCameraModel
    joint_producer: NativeJointProducer | None = None


@dataclass(frozen=True)
class CollectionStep:
    plan: ActiveObservationPlan | None
    command: ObservationCommand | None
    delivery: ObservationDelivery | None
    semantic_receipt: DeliveryReceipt
    recovered_ready_command: bool


def collect_posterior_step(
    stream: ContinuousEvidenceInput,
    *,
    model: ContinuousCameraModel,
    executor: ObservationExecutor,
    decision_time: datetime,
) -> CollectionStep:
    """Advance delivered evidence, select, execute and consume feedback on one owner.

    Recovery executes a saved READY command before advancing its decision cutoff.
    An uncertain external effect is never retried. A saved pending P5 step is
    resumed at its original cutoff before new observations/decisions proceed.
    """
    if stream._execution_lane != "registered_p5_first":
        raise ValueError("posterior collection requires the registered P5-first runtime")
    sources = CameraModelSources.model_validate(model.sources.model_dump())
    with stream._lock:
        stream._require_resolved_dispatches()
        ready = [
            value[0]
            for key, value in stream._observation_commands.items()
            if stream._observation_status[key] == "READY"
        ]
        if len(ready) > 1:
            raise ValueError("multiple READY commands require explicit reconciliation")
        recovered = bool(ready)
        plan = None
        command: ObservationCommand | None
        if ready:
            command = ready[0]
            if not command.reason.startswith("joint-ciav@1:"):
                raise ValueError("posterior collector cannot resume a fixed-scan command")
            problem = JointCameraProblem.model_validate_json(
                command.reason.removeprefix("joint-ciav@1:")
            )
            if problem.model_sources != sources:
                raise ValueError("recovery camera/utility model sources changed")
        else:
            if stream._pending_step is not None:
                stream.advance(cutoff=stream._pending_step["cutoff"])
            receipt = stream.advance(cutoff=decision_time)
            stream.produce_joint_posterior()
            view = stream.current_joint_decision_view()
            problem = JointCameraProblem.model_validate(
                model.problem(
                    view,
                    stream.visible_prefix(cutoff=decision_time),
                    decision_time=decision_time,
                    execution_history=stream.observation_history(),
                ).model_dump()
            )
            if problem.model_sources != sources:
                raise ValueError(
                    "camera problem does not bind configured observation/utility sources"
                )
            plan, command = stream.prepare_posterior_observation(
                problem, decision_time=decision_time
            )
            if command is None:
                return CollectionStep(plan, None, None, receipt, False)
        assert command is not None
        delivery = stream.execute_observation(command, executor=executor)
        receipt = stream.advance(cutoff=delivery.received_at)
        return CollectionStep(plan, command, delivery, receipt, recovered)
