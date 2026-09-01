"""S3-DG-11E dual-platform runtime and semantic-parity contracts.

Habitat and Isaac/ROS run in isolated environments.  This module records what
each sidecar can actually execute and verifies the shared semantic surface; it
does not pretend that simulator action names or raw sensor messages are already
equivalent.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.contracts.grounded_search import (
    ObservationActionType,
    RobotActionType,
    VerificationModality,
)
from cpswm.system.reproducibility import content_sha256


class EmbodimentPlatform(StrEnum):
    HABITAT_FINDINGDORY = "habitat_findingdory"
    ISAAC_ROS = "isaac_ros"


class PlatformRuntimeDescriptor(ContractModel):
    platform: EmbodimentPlatform
    runtime_version: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    runtime_environment_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    supported_observation_actions: tuple[ObservationActionType, ...]
    supported_robot_actions: tuple[RobotActionType, ...]
    supported_modalities: tuple[VerificationModality, ...]
    observation_action_bindings: dict[ObservationActionType, str]
    robot_action_bindings: dict[RobotActionType, str]
    modality_bindings: dict[VerificationModality, str]
    sidecar_protocol_version: str = Field(min_length=1)
    frame_registry_version: str = Field(min_length=1)
    action_outcome_model_versions: dict[RobotActionType, str]
    calibration_domains: dict[RobotActionType, str]

    @model_validator(mode="after")
    def _descriptor_semantics(self) -> PlatformRuntimeDescriptor:
        sequences = (
            self.supported_observation_actions,
            self.supported_robot_actions,
            self.supported_modalities,
        )
        if any(len(items) != len(set(items)) for items in sequences):
            raise ValueError("platform capability declarations must be unique")
        if set(self.action_outcome_model_versions) != set(self.supported_robot_actions):
            raise ValueError("platform must bind an outcome model for every robot action")
        if set(self.calibration_domains) != set(self.supported_robot_actions):
            raise ValueError("platform must bind a calibration domain for every robot action")
        if set(self.observation_action_bindings) != set(self.supported_observation_actions):
            raise ValueError("platform must bind every observation action to a native command")
        if set(self.robot_action_bindings) != set(self.supported_robot_actions):
            raise ValueError("platform must bind every robot action to a native command")
        if set(self.modality_bindings) != set(self.supported_modalities):
            raise ValueError("platform must bind every modality to a native sensor stream")
        if any(not value.strip() for value in self.action_outcome_model_versions.values()):
            raise ValueError("platform action outcome model versions must be non-empty")
        if any(not value.strip() for value in self.calibration_domains.values()):
            raise ValueError("platform calibration domains must be non-empty")
        native_bindings = (
            self.observation_action_bindings,
            self.robot_action_bindings,
            self.modality_bindings,
        )
        if any(
            any(not value.strip() for value in bindings.values()) for bindings in native_bindings
        ):
            raise ValueError("platform native action and sensor bindings must be non-empty")
        if any(
            len(bindings.values()) != len(set(bindings.values())) for bindings in native_bindings
        ):
            raise ValueError(
                "one native binding cannot impersonate multiple canonical capabilities"
            )
        return self


class DualPlatformBinding(ContractModel):
    habitat: PlatformRuntimeDescriptor
    isaac_ros: PlatformRuntimeDescriptor
    shared_task_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_semantics_version: str = Field(min_length=1)
    required_observation_actions: tuple[ObservationActionType, ...]
    required_robot_actions: tuple[RobotActionType, ...]
    required_modalities: tuple[VerificationModality, ...]

    @model_validator(mode="after")
    def _dual_platform_semantics(self) -> DualPlatformBinding:
        if self.habitat.platform is not EmbodimentPlatform.HABITAT_FINDINGDORY:
            raise ValueError("dual-platform Habitat descriptor has the wrong platform kind")
        if self.isaac_ros.platform is not EmbodimentPlatform.ISAAC_ROS:
            raise ValueError("dual-platform Isaac/ROS descriptor has the wrong platform kind")
        required_sets = (
            set(self.required_observation_actions),
            set(self.required_robot_actions),
            set(self.required_modalities),
        )
        if any(not items for items in required_sets):
            raise ValueError("dual-platform parity requires non-empty capability sets")
        if any(
            len(items) != len(set(items))
            for items in (
                self.required_observation_actions,
                self.required_robot_actions,
                self.required_modalities,
            )
        ):
            raise ValueError("dual-platform required capabilities must be unique")
        for descriptor in (self.habitat, self.isaac_ros):
            if not required_sets[0].issubset(descriptor.supported_observation_actions):
                raise ValueError("platform is missing a required observation action")
            if not required_sets[1].issubset(descriptor.supported_robot_actions):
                raise ValueError("platform is missing a required robot action")
            if not required_sets[2].issubset(descriptor.supported_modalities):
                raise ValueError("platform is missing a required observation modality")
        return self


class DualPlatformParityReport(ContractModel):
    parity_satisfied: bool
    shared_task_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_semantics_version: str = Field(min_length=1)
    habitat_descriptor_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    isaac_ros_descriptor_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    checks_passed: tuple[str, ...] = Field(min_length=1)


def validate_dual_platform_parity(binding: DualPlatformBinding) -> DualPlatformParityReport:
    binding = DualPlatformBinding.model_validate(binding.model_dump(mode="python"))
    return DualPlatformParityReport(
        parity_satisfied=True,
        shared_task_manifest_hash=binding.shared_task_manifest_hash,
        action_semantics_version=binding.action_semantics_version,
        habitat_descriptor_hash=content_sha256(binding.habitat),
        isaac_ros_descriptor_hash=content_sha256(binding.isaac_ros),
        checks_passed=(
            "isolated_runtime_versions_bound",
            "shared_task_manifest_bound",
            "required_observation_actions_supported",
            "required_robot_actions_supported",
            "required_modalities_supported",
            "canonical_capabilities_bound_to_native_sidecar_commands",
            "action_outcome_models_and_domains_explicit",
        ),
    )
