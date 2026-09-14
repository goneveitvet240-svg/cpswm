"""CIAV joint-posterior decisions mapped to bounded executable camera requests.

Observation likelihoods and utilities come from the configured task/measurement
model; this boundary does not fit or certify them. The complete problem is kept
in the command reason so recovery preserves the decision's evidence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.contracts.grounded_search import ActiveObservationPlan, ObservationActionCandidate

if TYPE_CHECKING:
    from cpswm.system.structure_two_joint_consumption import JointDecisionView
    from cpswm.world_model.grounded_search.active_verification import (
        CauseInformationActiveVerificationPlanner,
    )


class CameraAlternative(ContractModel):
    candidate: ObservationActionCandidate
    action: Literal["Pass", "RotateRight", "RotateLeft"]
    degrees: float = Field(ge=0, le=90, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_camera(self) -> Self:
        if self.candidate.action_type.value not in {"move_viewpoint", "micro_verify"}:
            raise ValueError("camera mapping cannot execute contact or user-query actions")
        if (self.action == "Pass") != (self.degrees == 0):
            raise ValueError("Pass is zero degrees; rotations require nonzero degrees")
        return self


class JointCameraProblem(ContractModel):
    source_belief_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_observation_ids: tuple[UUID, ...] = Field(min_length=1)
    alternatives: tuple[CameraAlternative, ...] = Field(min_length=1)
    consolidation_decision_utilities: dict[UUID, dict[UUID, float]]
    terminal_decision_utilities: dict[UUID, dict[UUID, float]]
    privacy_budget: float = Field(ge=0, allow_inf_nan=False)
    minimum_net_value: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_options(self) -> Self:
        ids = [x.candidate.action_id for x in self.alternatives]
        if len(ids) != len(set(ids)) or len(self.source_observation_ids) != len(
            set(self.source_observation_ids)
        ):
            raise ValueError("duplicate camera alternatives or observation dependencies")
        return self

    def select(
        self, view: JointDecisionView, planner: CauseInformationActiveVerificationPlanner
    ) -> tuple[ActiveObservationPlan, CameraAlternative | None]:
        problem = JointCameraProblem.model_validate(self.model_dump())
        plan = view.select_verification(
            planner,
            tuple(x.candidate for x in problem.alternatives),
            source_belief_sha256=problem.source_belief_sha256,
            consolidation_decision_utilities=problem.consolidation_decision_utilities,
            terminal_decision_utilities=problem.terminal_decision_utilities,
            privacy_budget=problem.privacy_budget,
            minimum_net_value=problem.minimum_net_value,
        )
        selected = next(
            (x for x in problem.alternatives if x.candidate.action_id == plan.selected_action_id),
            None,
        )
        return plan, selected
