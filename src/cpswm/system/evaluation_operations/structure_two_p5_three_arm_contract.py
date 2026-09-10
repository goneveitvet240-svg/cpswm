"""Common typed-location and matched-CIAV contracts for the P5 death test."""

from __future__ import annotations

from enum import StrEnum
from math import isclose, isfinite
from typing import Annotated, Any, Final, Literal
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts import ContractModel
from cpswm.system.evaluation_operations.structure_two_action_utility_construct_gate import (
    TaskSeparatedActionReadout,
    decode_task_separated_actions,
)
from cpswm.system.reproducibility import content_sha256

SCHEMA_VERSION: Final = "0.1.0"
PROTOCOL_ID: Final = "structure-two-p5-matched-three-arm@0.1-development"
SHARED_DECODER_SYMBOL: Final = (
    "cpswm.system.evaluation_operations."
    "structure_two_action_utility_construct_gate.decode_task_separated_actions"
)
SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class P5ComparisonArm(StrEnum):
    DIRECT_P5 = "direct_p5_full_eager"
    LEARNED_TWO_STAGE = "learned_matched_two_stage"
    TUNED_AMG = "independently_tuned_amg"


class LocationMass(ContractModel):
    location_id: UUID
    probability: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_finite(self) -> LocationMass:
        if not isfinite(self.probability):
            raise ValueError("location probability must be finite")
        return self


class TypedLocationPosterior(ContractModel):
    """The only arm output accepted by the shared SEARCH/PUT_BACK decoder."""

    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    protocol_id: Literal["structure-two-p5-matched-three-arm@0.1-development"] = PROTOCOL_ID
    arm: P5ComparisonArm
    episode_id: UUID
    step_id: UUID
    target_object_id: UUID
    source_visible_step_sha256: SHA256
    belief_state_sha256: SHA256
    location_support: tuple[UUID, ...] = Field(min_length=1)
    current_location_distribution: tuple[LocationMass, ...] = Field(min_length=1)
    owner_habit_location_distribution: tuple[LocationMass, ...] = Field(min_length=1)
    truth_visible_before_action_commit: Literal[False] = False
    decoder_symbol: Literal[
        "cpswm.system.evaluation_operations."
        "structure_two_action_utility_construct_gate.decode_task_separated_actions"
    ] = SHARED_DECODER_SYMBOL
    posterior_sha256: SHA256

    @model_validator(mode="after")
    def validate_posterior(self) -> TypedLocationPosterior:
        if len(self.location_support) != len(set(self.location_support)):
            raise ValueError("typed location support contains duplicates")

        def validate_distribution(values: tuple[LocationMass, ...], name: str) -> dict[UUID, float]:
            mapped = {item.location_id: item.probability for item in values}
            if len(mapped) != len(values) or set(mapped) != set(self.location_support):
                raise ValueError(f"{name} does not cover the exact registered support")
            if not isclose(sum(mapped.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
                raise ValueError(f"{name} must sum to one")
            return mapped

        validate_distribution(self.current_location_distribution, "current-location posterior")
        validate_distribution(
            self.owner_habit_location_distribution,
            "owner-habit-location posterior",
        )
        unsigned = self.model_dump(mode="json", exclude={"posterior_sha256"})
        if self.posterior_sha256 != content_sha256(unsigned):
            raise ValueError("typed location posterior hash mismatch")
        return self

    @classmethod
    def seal(
        cls,
        *,
        arm: P5ComparisonArm,
        episode_id: UUID,
        step_id: UUID,
        target_object_id: UUID,
        source_visible_step_sha256: str,
        belief_state_sha256: str,
        location_support: tuple[UUID, ...],
        current_location_distribution: dict[UUID, float],
        owner_habit_location_distribution: dict[UUID, float],
    ) -> TypedLocationPosterior:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "protocol_id": PROTOCOL_ID,
            "arm": arm,
            "episode_id": episode_id,
            "step_id": step_id,
            "target_object_id": target_object_id,
            "source_visible_step_sha256": source_visible_step_sha256,
            "belief_state_sha256": belief_state_sha256,
            "location_support": location_support,
            "current_location_distribution": tuple(
                LocationMass(
                    location_id=location, probability=current_location_distribution[location]
                )
                for location in location_support
            ),
            "owner_habit_location_distribution": tuple(
                LocationMass(
                    location_id=location,
                    probability=owner_habit_location_distribution[location],
                )
                for location in location_support
            ),
            "truth_visible_before_action_commit": False,
            "decoder_symbol": SHARED_DECODER_SYMBOL,
        }
        return cls(**payload, posterior_sha256=content_sha256(payload))

    def decode(
        self,
        *,
        step_index: int,
        run_execution_id: UUID,
        visible_observation: dict[str, Any],
    ) -> TaskSeparatedActionReadout:
        return decode_task_separated_actions(
            target_object_id=self.target_object_id,
            step_index=step_index,
            run_execution_id=run_execution_id,
            source_update_id=self.step_id,
            visible_observation=visible_observation,
            belief_state_sha256=self.belief_state_sha256,
            search_distribution={
                item.location_id: item.probability for item in self.current_location_distribution
            },
            put_back_distribution={
                item.location_id: item.probability
                for item in self.owner_habit_location_distribution
            },
        )


class MatchedCIAVArmReceipt(ContractModel):
    """One arm's acknowledgement of an identical evaluator-released CIAV packet."""

    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    protocol_id: Literal["structure-two-p5-matched-three-arm@0.1-development"] = PROTOCOL_ID
    arm: P5ComparisonArm
    episode_id: UUID
    step_id: UUID
    shared_ciav_packet_sha256: SHA256
    candidate_set_sha256: SHA256
    selected_action_id: UUID
    realized_observation_sha256: SHA256
    motion_cost: float = Field(ge=0.0)
    time_cost: float = Field(ge=0.0)
    interruption_cost: float = Field(ge=0.0)
    privacy_cost: float = Field(ge=0.0)
    safety_cost: float = Field(ge=0.0)
    privacy_budget_before: float = Field(ge=0.0)
    privacy_budget_after: float = Field(ge=0.0)
    release_phase: Literal["after_typed_actions_committed"] = "after_typed_actions_committed"
    truth_visible_before_action_commit: Literal[False] = False
    receipt_sha256: SHA256

    @model_validator(mode="after")
    def validate_receipt(self) -> MatchedCIAVArmReceipt:
        numeric = (
            self.motion_cost,
            self.time_cost,
            self.interruption_cost,
            self.privacy_cost,
            self.safety_cost,
            self.privacy_budget_before,
            self.privacy_budget_after,
        )
        if any(not isfinite(value) for value in numeric):
            raise ValueError("matched CIAV costs and budgets must be finite")
        expected_budget = self.privacy_budget_before - self.privacy_cost
        if not isclose(
            self.privacy_budget_after,
            expected_budget,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("matched CIAV privacy budget delta differs from privacy cost")
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if self.receipt_sha256 != content_sha256(unsigned):
            raise ValueError("matched CIAV arm receipt hash mismatch")
        return self

    @classmethod
    def seal(
        cls,
        *,
        arm: P5ComparisonArm,
        episode_id: UUID,
        step_id: UUID,
        shared_ciav_packet_sha256: str,
        candidate_set_sha256: str,
        selected_action_id: UUID,
        realized_observation_sha256: str,
        motion_cost: float,
        time_cost: float,
        interruption_cost: float,
        privacy_cost: float,
        safety_cost: float,
        privacy_budget_before: float,
    ) -> MatchedCIAVArmReceipt:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "protocol_id": PROTOCOL_ID,
            "arm": arm,
            "episode_id": episode_id,
            "step_id": step_id,
            "shared_ciav_packet_sha256": shared_ciav_packet_sha256,
            "candidate_set_sha256": candidate_set_sha256,
            "selected_action_id": selected_action_id,
            "realized_observation_sha256": realized_observation_sha256,
            "motion_cost": motion_cost,
            "time_cost": time_cost,
            "interruption_cost": interruption_cost,
            "privacy_cost": privacy_cost,
            "safety_cost": safety_cost,
            "privacy_budget_before": privacy_budget_before,
            "privacy_budget_after": privacy_budget_before - privacy_cost,
            "release_phase": "after_typed_actions_committed",
            "truth_visible_before_action_commit": False,
        }
        return cls(**payload, receipt_sha256=content_sha256(payload))


def verify_exact_three_arm_ciav_match(
    receipts: tuple[MatchedCIAVArmReceipt, ...],
) -> None:
    """Fail unless all three arms consumed the exact same information and cost."""

    if tuple(receipt.arm for receipt in receipts) != tuple(P5ComparisonArm):
        raise ValueError("matched CIAV receipts must cover all three arms in registered order")
    anchor = receipts[0]
    fields = (
        "episode_id",
        "step_id",
        "shared_ciav_packet_sha256",
        "candidate_set_sha256",
        "selected_action_id",
        "realized_observation_sha256",
        "motion_cost",
        "time_cost",
        "interruption_cost",
        "privacy_cost",
        "safety_cost",
        "privacy_budget_before",
        "privacy_budget_after",
        "release_phase",
        "truth_visible_before_action_commit",
    )
    for receipt in receipts:
        MatchedCIAVArmReceipt.model_validate(receipt.model_dump(mode="json"))
        if any(getattr(receipt, field) != getattr(anchor, field) for field in fields):
            raise ValueError("CIAV information, action, outcome, or cost differs across arms")


__all__ = [
    "PROTOCOL_ID",
    "SHARED_DECODER_SYMBOL",
    "MatchedCIAVArmReceipt",
    "P5ComparisonArm",
    "TypedLocationPosterior",
    "verify_exact_three_arm_ciav_match",
]
