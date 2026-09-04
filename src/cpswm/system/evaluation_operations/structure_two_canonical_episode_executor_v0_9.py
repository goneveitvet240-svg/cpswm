"""Canonical, content-bound per-episode execution for Structure Two v0.9.

This module is deliberately an execution boundary, not a fidelity oracle.  It
dispatches every canonical arm/episode pair to an enrolled isolated runner,
verifies the runner's signed receipt, and signs the complete aggregate with a
separate enrolled executor key.  Running a frozen bundle does **not** by itself
establish that the bundle is a native reproduction of the named method.
"""

from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol

from pydantic import Field, field_validator, model_validator

from cpswm.contracts import (
    ProjectTwoDatasetSplit,
    ProjectTwoReplayEpisode,
    reject_truth_leakage,
)
from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import (
    EXPECTED_ARMS,
)
from cpswm.system.evaluation_operations.structure_two_isolation_v0_9 import (
    DEFAULT_RESOURCE_LIMITS,
    IsolationExecutionReceiptV09,
    IsolationResourceLimitsV09,
    run_macos_isolated_execution_v0_9,
    verify_isolation_receipt_v0_9,
)
from cpswm.system.evaluation_operations.structure_two_sealed_gate_b_opening_v0_9 import (
    SealedGateBOpeningV09,
    recompute_sealed_gate_b_holdout_v0_9,
)
from cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4 import (
    adapt_world_rollout,
)
from cpswm.system.reproducibility import canonical_json, content_sha256

PROTOCOL_ID = "structure-two-canonical-per-episode-executor@0.9"
BUNDLE_MANIFEST_PROTOCOL_ID = "structure-two-arm-bundle-manifest@0.9"
VISIBLE_INPUT_PROTOCOL_ID = "structure-two-visible-episode-input@0.9"
TASK_PROTOCOL_ID = "structure-two-isolated-arm-episode-task@0.9"
RECEIPT_PROTOCOL_ID = "structure-two-isolated-arm-episode-receipt@0.9"
BUNDLE_TREE_PROTOCOL_ID = "structure-two-content-addressed-directory@0.9"
STATE_CHAIN_PROTOCOL_ID = "structure-two-mechanism-state-chain@0.9"
CANDIDATE_OUTPUT_PROTOCOL_ID = "structure-two-isolated-candidate-output@0.9"
PREREQUISITE_VERIFICATION_PROTOCOL_ID = "structure-two-canonical-execution-prerequisites@0.9"
PREREQUISITE_VERIFIER_PROTOCOL_ID = "structure-two-canonical-execution-prerequisite-verifier@0.9"

BUNDLE_MANIFEST_FILENAME = "cpswm-bundle-manifest-v0.9.json"
BUNDLE_MANIFEST_SIDECAR_SUFFIX = ".cpswm-bundle-manifest-v0.9.json"
ENTRYPOINT_INTERFACE = "cpswm-visible-episode-json-stdio@0.9"
ISOLATION_PROFILE = "read-only-bundle-visible-input-no-network@0.9"
EXECUTION_MODE = "frozen-content-addressed-isolated-bundle"
ISOLATION_TIMEOUT_SECONDS = 300
ISOLATION_OUTPUT_LABEL = "episode_output"
ISOLATION_OUTPUT_RELATIVE_PATH = "episode-output.json"
CLAIM_BOUNDARY = (
    "Execution proves only that the frozen content-addressed bundles produced signed "
    "per-episode outputs through the trusted isolated runner. It does not establish "
    "native-method fidelity, adaptation parity, or external efficacy, and reference "
    "cores are not relabelled as native reproductions."
)

RECEIPT_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.isolated_episode_receipt.v0.9"
AGGREGATE_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.canonical_episode_execution.v0.9"
PREREQUISITE_ATTESTATION_DOMAIN = (
    "cpswm.evaluation.structure_two.canonical_execution_prerequisites.v0.9"
)

_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ArmBundleManifestV09(ContractModel):
    """The only accepted manifest shape at each fixed bundle location."""

    protocol: Literal["structure-two-arm-bundle-manifest@0.9"]
    arm: str = Field(min_length=1)
    bundle_kind: Literal["directory", "file"]
    entrypoint: str = Field(min_length=1)
    entrypoint_interface: Literal["cpswm-visible-episode-json-stdio@0.9"]
    entrypoint_sha256: str = Field(pattern=_SHA256_PATTERN)
    command_engine_path: str = Field(min_length=1)
    command_engine_sha256: str = Field(pattern=_SHA256_PATTERN)


class VisibleEpisodeInputV09(ContractModel):
    """Strict wrapper around the existing model-visible replay contract."""

    protocol: Literal["structure-two-visible-episode-input@0.9"]
    episode: ProjectTwoReplayEpisode


class ArmBundleBindingV09(ContractModel):
    arm: str = Field(min_length=1)
    bundle_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    bundle_filesystem_sha256: str = Field(pattern=_SHA256_PATTERN)
    manifest_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    manifest_file_sha256: str = Field(pattern=_SHA256_PATTERN)
    manifest_filesystem_sha256: str = Field(pattern=_SHA256_PATTERN)
    entrypoint: str = Field(min_length=1)
    entrypoint_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    entrypoint_filesystem_sha256: str = Field(pattern=_SHA256_PATTERN)
    command_engine_path: str = Field(min_length=1)
    command_engine_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    command_engine_filesystem_sha256: str = Field(pattern=_SHA256_PATTERN)


class EpisodeInputBindingV09(ContractModel):
    episode_id: str = Field(min_length=1)
    input_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    input_filesystem_sha256: str = Field(pattern=_SHA256_PATTERN)
    visible_episode_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    step_count: int = Field(gt=0)


class SealedOpeningBindingV09(ContractModel):
    artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    filesystem_sha256: str = Field(pattern=_SHA256_PATTERN)


class VerifiedExecutionPrerequisitesV09(ContractModel):
    """Output of the caller-enrolled semantic prerequisite verifier.

    The verifier behind this contract must validate the frozen manifest,
    preregistered producer run, passed Gate A, and the independently committed
    sealed opening.  Raw file hashes alone are intentionally insufficient.
    """

    protocol: Literal["structure-two-canonical-execution-prerequisites@0.9"]
    execution_id: str = Field(min_length=16)
    episode_ids: tuple[str, ...] = Field(min_length=1)
    immutable_manifest_sha256: str = Field(pattern=_SHA256_PATTERN)
    producer_run_id: str = Field(min_length=1)
    opening_attempt_id: str = Field(min_length=16)
    arm_implementation_bundle_sha256: dict[str, str]
    sealed_holdout_visible_input_artifact_sha256_by_episode: dict[str, str]
    sealed_holdout_visible_episode_content_sha256_by_episode: dict[str, str]
    frozen_manifest_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    producer_run_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    gate_a_report_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    sealed_opening_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    frozen_manifest_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    producer_run_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    gate_a_report_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    sealed_opening_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    frozen_manifest_semantically_verified: Literal[True]
    producer_run_semantically_verified: Literal[True]
    gate_a_semantically_verified: Literal[True]
    gate_a_passed: Literal[True]
    sealed_opening_semantically_verified: Literal[True]
    prerequisite_verifier_protocol: Literal[
        "structure-two-canonical-execution-prerequisite-verifier@0.9"
    ]
    prerequisite_verifier_implementation_sha256: str = Field(pattern=_SHA256_PATTERN)
    prerequisite_verifier_key_id: str = Field(min_length=1)
    prerequisite_verifier_public_key_base64: str = Field(min_length=1)
    prerequisite_verifier_public_key_sha256: str = Field(pattern=_SHA256_PATTERN)
    prerequisite_verifier_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> VerifiedExecutionPrerequisitesV09:
        if tuple(self.arm_implementation_bundle_sha256) != EXPECTED_ARMS:
            raise ValueError("verified prerequisites do not bind the exact ten arms")
        if any(not _is_sha256(value) for value in self.arm_implementation_bundle_sha256.values()):
            raise ValueError("verified prerequisites contain a malformed bundle digest")
        if len(set(self.episode_ids)) != len(self.episode_ids):
            raise ValueError("verified prerequisites contain duplicate episode ids")
        expected_episode_set = set(self.episode_ids)
        for label, mapping in (
            (
                "sealed holdout visible-input artifact hashes",
                self.sealed_holdout_visible_input_artifact_sha256_by_episode,
            ),
            (
                "sealed holdout visible-episode content hashes",
                self.sealed_holdout_visible_episode_content_sha256_by_episode,
            ),
        ):
            if set(mapping) != expected_episode_set or len(mapping) != len(self.episode_ids):
                raise ValueError(f"{label} do not have exact sealed episode coverage")
            if any(not _is_sha256(value) for value in mapping.values()):
                raise ValueError(f"{label} contain a malformed digest")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


def _prerequisite_attested_payload(
    record: VerifiedExecutionPrerequisitesV09,
) -> dict[str, Any]:
    return attested_payload(
        record,
        exclude=frozenset({"prerequisite_verifier_attestation"}),
    )


def sign_verified_execution_prerequisites_v0_9(
    record: VerifiedExecutionPrerequisitesV09,
    *,
    verifier_signer: Ed25519AttestationSigner,
) -> VerifiedExecutionPrerequisitesV09:
    """Attach the independently enrolled semantic-verifier signature."""

    if record.prerequisite_verifier_attestation is not None:
        raise ValueError("verified prerequisites are already attested")
    verifier = verifier_signer.verifier()
    if (
        record.prerequisite_verifier_key_id != verifier.key_id
        or record.prerequisite_verifier_public_key_base64 != verifier.public_key_base64
        or record.prerequisite_verifier_public_key_sha256 != verifier.public_key_sha256
    ):
        raise AttestationError("prerequisite record key metadata differs from its signer")
    return record.model_copy(
        update={
            "prerequisite_verifier_attestation": verifier_signer.sign(
                PREREQUISITE_ATTESTATION_DOMAIN,
                _prerequisite_attested_payload(record),
            )
        }
    )


class CanonicalEpisodeTaskV09(ContractModel):
    """One immutable arm/episode invocation handed to the isolated runner."""

    protocol: Literal["structure-two-isolated-arm-episode-task@0.9"]
    execution_id: str = Field(min_length=16)
    task_index: int = Field(ge=0)
    arm: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    visible_input_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    visible_input_filesystem_sha256: str = Field(pattern=_SHA256_PATTERN)
    implementation_bundle_sha256: str = Field(pattern=_SHA256_PATTERN)
    implementation_bundle_filesystem_sha256: str = Field(pattern=_SHA256_PATTERN)
    bundle_manifest_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    entrypoint: str = Field(min_length=1)
    entrypoint_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    command_engine_path: str = Field(min_length=1)
    command_engine_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    sealed_opening_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    sealed_opening_filesystem_sha256: str = Field(pattern=_SHA256_PATTERN)
    execution_prerequisites_sha256: str = Field(pattern=_SHA256_PATTERN)
    expected_step_count: int = Field(gt=0)
    isolation_profile: Literal["read-only-bundle-visible-input-no-network@0.9"]

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class MechanismStepRecordV09(ContractModel):
    step_index: int = Field(ge=0)
    action: str = Field(min_length=1)
    mechanism_events: tuple[str, ...] = Field(min_length=1)
    input_state_sha256: str = Field(pattern=_SHA256_PATTERN)
    output_state_sha256: str = Field(pattern=_SHA256_PATTERN)

    @field_validator("mechanism_events")
    @classmethod
    def validate_mechanism_events(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not event.strip() for event in value):
            raise ValueError("mechanism events must be non-empty identifiers")
        if len(set(value)) != len(value):
            raise ValueError("one mechanism step cannot duplicate an event")
        return value


class IsolatedCandidateOutputV09(ContractModel):
    """Unsigned candidate output whose bytes are bound by the isolation receipt."""

    protocol: Literal["structure-two-isolated-candidate-output@0.9"]
    task_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    execution_id: str = Field(min_length=16)
    task_index: int = Field(ge=0)
    arm: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    action_sequence: tuple[str, ...] = Field(min_length=1)
    mechanism_steps: tuple[MechanismStepRecordV09, ...] = Field(min_length=1)
    final_state_sha256: str = Field(pattern=_SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_candidate_chain(self) -> IsolatedCandidateOutputV09:
        if len(self.action_sequence) != len(self.mechanism_steps):
            raise ValueError("candidate output action/mechanism coverage differs")
        if tuple(step.step_index for step in self.mechanism_steps) != tuple(
            range(len(self.mechanism_steps))
        ):
            raise ValueError("candidate output step indexes are noncanonical")
        if tuple(step.action for step in self.mechanism_steps) != self.action_sequence:
            raise ValueError("candidate output actions differ from mechanism records")
        if any(
            right.input_state_sha256 != left.output_state_sha256
            for left, right in zip(self.mechanism_steps, self.mechanism_steps[1:], strict=False)
        ):
            raise ValueError("candidate output state chain is discontinuous")
        if self.final_state_sha256 != self.mechanism_steps[-1].output_state_sha256:
            raise ValueError("candidate output final state hash is wrong")
        return self


class BoundCandidateOutputV09(ContractModel):
    output_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    output_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    output: IsolatedCandidateOutputV09

    @model_validator(mode="after")
    def validate_output_hash(self) -> BoundCandidateOutputV09:
        if content_sha256(self.output.model_dump(mode="json")) != self.output_content_sha256:
            raise ValueError("candidate output content hash mismatch")
        return self


class BoundIsolationExecutionReceiptV09(ContractModel):
    isolation_receipt_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    receipt: IsolationExecutionReceiptV09

    @model_validator(mode="after")
    def validate_isolation_receipt_hash(self) -> BoundIsolationExecutionReceiptV09:
        if content_sha256(self.receipt.model_dump(mode="json")) != (
            self.isolation_receipt_content_sha256
        ):
            raise ValueError("isolation execution receipt content hash mismatch")
        return self


class IsolatedEpisodeExecutionReceiptV09(ContractModel):
    """Runner-signed output for exactly one canonical task."""

    protocol: Literal["structure-two-isolated-arm-episode-receipt@0.9"]
    task_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    execution_id: str = Field(min_length=16)
    task_index: int = Field(ge=0)
    arm: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    visible_input_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    implementation_bundle_sha256: str = Field(pattern=_SHA256_PATTERN)
    bundle_manifest_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    entrypoint_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    sealed_opening_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    execution_prerequisites_sha256: str = Field(pattern=_SHA256_PATTERN)
    isolation_profile: Literal["read-only-bundle-visible-input-no-network@0.9"]
    isolation_receipt_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    isolated_output_artifact_sha256: str = Field(pattern=_SHA256_PATTERN)
    isolated_output_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    action_sequence: tuple[str, ...]
    mechanism_steps: tuple[MechanismStepRecordV09, ...]
    final_state_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    exit_status: Literal["succeeded", "failed"]
    exit_code: int
    runner_key_id: str = Field(min_length=1)
    runner_public_key_base64: str = Field(min_length=1)
    runner_public_key_sha256: str = Field(pattern=_SHA256_PATTERN)
    attestation: Attestation | None = None

    @field_validator("exit_code")
    @classmethod
    def validate_exit_code_type(cls, value: int) -> int:
        if isinstance(value, bool):
            raise ValueError("exit code must be an integer, not a boolean")
        return value

    @model_validator(mode="after")
    def validate_execution_chain(self) -> IsolatedEpisodeExecutionReceiptV09:
        if (self.exit_status == "succeeded") != (self.exit_code == 0):
            raise ValueError("exit status and exit code disagree")
        if len(self.action_sequence) != len(self.mechanism_steps):
            raise ValueError("action sequence and mechanism-step coverage differ")
        if any(not action.strip() for action in self.action_sequence):
            raise ValueError("action sequence contains an empty action")
        if tuple(step.step_index for step in self.mechanism_steps) != tuple(
            range(len(self.mechanism_steps))
        ):
            raise ValueError("mechanism step indexes must be contiguous and zero based")
        if tuple(step.action for step in self.mechanism_steps) != self.action_sequence:
            raise ValueError("mechanism-step actions do not bind the action sequence")
        if any(
            right.input_state_sha256 != left.output_state_sha256
            for left, right in zip(self.mechanism_steps, self.mechanism_steps[1:], strict=False)
        ):
            raise ValueError("mechanism state chain is discontinuous")
        expected_final = (
            self.mechanism_steps[-1].output_state_sha256 if self.mechanism_steps else None
        )
        if self.final_state_sha256 != expected_final:
            raise ValueError("final state hash does not close the mechanism state chain")
        if self.exit_status == "succeeded" and not self.mechanism_steps:
            raise ValueError("a successful receipt cannot contain zero executed steps")
        return self


class BoundEpisodeExecutionReceiptV09(ContractModel):
    """A nested receipt plus its independently recomputable signed-record hash."""

    receipt_content_sha256: str = Field(pattern=_SHA256_PATTERN)
    receipt: IsolatedEpisodeExecutionReceiptV09
    isolation: BoundIsolationExecutionReceiptV09
    candidate_output: BoundCandidateOutputV09

    @model_validator(mode="after")
    def validate_receipt_hash(self) -> BoundEpisodeExecutionReceiptV09:
        if content_sha256(self.receipt.model_dump(mode="json")) != self.receipt_content_sha256:
            raise ValueError("isolated episode receipt content hash mismatch")
        if (
            self.receipt.isolation_receipt_content_sha256
            != self.isolation.isolation_receipt_content_sha256
            or self.receipt.isolated_output_artifact_sha256
            != self.candidate_output.output_artifact_sha256
            or self.receipt.isolated_output_content_sha256
            != self.candidate_output.output_content_sha256
        ):
            raise ValueError("episode receipt does not bind its isolation/output evidence")
        return self


class CanonicalPerEpisodeExecutionArtifactV09(ContractModel):
    """Executor-signed, exact Cartesian product of ten arms and episodes."""

    protocol: Literal["structure-two-canonical-per-episode-executor@0.9"]
    execution_id: str = Field(min_length=16)
    action_execution_mode: Literal["frozen-content-addressed-isolated-bundle"]
    canonical_arms: tuple[str, ...]
    episode_ids: tuple[str, ...] = Field(min_length=1)
    arm_bundle_bindings: tuple[ArmBundleBindingV09, ...]
    episode_input_bindings: tuple[EpisodeInputBindingV09, ...]
    sealed_opening_binding: SealedOpeningBindingV09
    verified_prerequisites: VerifiedExecutionPrerequisitesV09
    task_receipts: tuple[BoundEpisodeExecutionReceiptV09, ...] = Field(min_length=1)
    exact_arm_episode_coverage_verified: Literal[True]
    all_tasks_succeeded: Literal[True]
    visible_inputs_only_verified: Literal[True]
    reference_cores_relabelled_as_native: Literal[False]
    fidelity_or_native_reproduction_status: Literal["not_evaluated_by_executor"]
    claim_boundary: str = Field(min_length=1)
    executor_key_id: str = Field(min_length=1)
    executor_public_key_base64: str = Field(min_length=1)
    executor_public_key_sha256: str = Field(pattern=_SHA256_PATTERN)
    attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_exact_coverage(self) -> CanonicalPerEpisodeExecutionArtifactV09:
        if self.canonical_arms != EXPECTED_ARMS:
            raise ValueError("canonical executor requires the exact ten-arm order")
        if len(set(self.episode_ids)) != len(self.episode_ids):
            raise ValueError("canonical executor contains duplicate episode ids")
        if tuple(binding.arm for binding in self.arm_bundle_bindings) != EXPECTED_ARMS:
            raise ValueError("bundle bindings do not cover the exact ten arms")
        if tuple(binding.episode_id for binding in self.episode_input_bindings) != self.episode_ids:
            raise ValueError("input bindings do not cover the exact episode order")
        if (
            self.verified_prerequisites.execution_id != self.execution_id
            or self.verified_prerequisites.episode_ids != self.episode_ids
            or self.verified_prerequisites.arm_implementation_bundle_sha256
            != {binding.arm: binding.bundle_content_sha256 for binding in self.arm_bundle_bindings}
            or self.verified_prerequisites.sealed_holdout_visible_input_artifact_sha256_by_episode
            != {
                binding.episode_id: binding.input_artifact_sha256
                for binding in self.episode_input_bindings
            }
            or self.verified_prerequisites.sealed_holdout_visible_episode_content_sha256_by_episode
            != {
                binding.episode_id: binding.visible_episode_content_sha256
                for binding in self.episode_input_bindings
            }
            or self.verified_prerequisites.sealed_opening_artifact_sha256
            != self.sealed_opening_binding.artifact_sha256
        ):
            raise ValueError("verified prerequisites do not bind the aggregate execution scope")
        expected_pairs = tuple(
            (arm, episode_id) for arm in EXPECTED_ARMS for episode_id in self.episode_ids
        )
        actual_pairs = tuple(
            (bound.receipt.arm, bound.receipt.episode_id) for bound in self.task_receipts
        )
        if actual_pairs != expected_pairs or len(set(actual_pairs)) != len(actual_pairs):
            raise ValueError("task receipts do not provide exact arm-by-episode coverage")
        if tuple(bound.receipt.task_index for bound in self.task_receipts) != tuple(
            range(len(expected_pairs))
        ):
            raise ValueError("task receipt indexes do not match canonical execution order")
        if any(bound.receipt.execution_id != self.execution_id for bound in self.task_receipts):
            raise ValueError("task receipt belongs to another execution")
        if any(
            bound.receipt.exit_status != "succeeded" or bound.receipt.exit_code != 0
            for bound in self.task_receipts
        ):
            raise ValueError("canonical aggregate cannot contain partial or failed tasks")
        if self.claim_boundary != CLAIM_BOUNDARY:
            raise ValueError("canonical executor claim boundary was changed")
        return self


class TrustedIsolatedEpisodeRunnerV09(Protocol):
    """Capability supplied by the independent isolation implementation."""

    def run(
        self,
        *,
        task: CanonicalEpisodeTaskV09,
        bundle_path: Path,
        entrypoint_path: Path,
        visible_input_path: Path,
        isolation_working_directory: Path,
        isolation_arguments: tuple[str, ...],
    ) -> IsolatedTaskRunArtifactsV09: ...


@dataclass(frozen=True, slots=True)
class IsolatedTaskRunArtifactsV09:
    """Both independent receipts returned for one isolated invocation."""

    episode_execution_receipt: Mapping[str, Any]
    isolation_execution_receipt: Mapping[str, Any]


class TrustedIsolationReceiptVerifierV09(Protocol):
    """Exact call shape of ``verify_isolation_receipt_v0_9``."""

    def __call__(
        self,
        payload: Mapping[str, Any],
        *,
        trusted_executor: Ed25519AttestationVerifier,
        command_engine_path: Path,
        arguments: Sequence[str],
        code_bundle_path: Path,
        input_artifact_paths: Mapping[str, Path],
        working_directory: Path,
        expected_output_relative_paths: Mapping[str, str | Path],
        timeout_seconds: int,
        resource_limits: IsolationResourceLimitsV09 = DEFAULT_RESOURCE_LIMITS,
    ) -> IsolationExecutionReceiptV09: ...


class TrustedExecutionPrerequisiteVerifierV09(Protocol):
    """Independent, enrolled semantic verifier for the pre-execution chain.

    The returned record is accepted only when its provenance signature verifies
    under a separately supplied trust anchor and its implementation digest
    equals this capability's declared digest.  Merely returning schema booleans
    is therefore insufficient.
    """

    @property
    def implementation_sha256(self) -> str: ...

    def verify(
        self,
        *,
        execution_id: str,
        expected_episode_ids: tuple[str, ...],
        expected_bundle_sha256_by_arm: Mapping[str, str],
        frozen_manifest_artifact_path: Path,
        producer_run_artifact_path: Path,
        gate_a_report_artifact_path: Path,
        sealed_opening_artifact_path: Path,
        visible_input_paths_by_episode: Mapping[str, Path],
        expected_visible_input_artifact_sha256_by_episode: Mapping[str, str],
        expected_visible_episode_content_sha256_by_episode: Mapping[str, str],
    ) -> VerifiedExecutionPrerequisitesV09: ...


@dataclass(frozen=True, slots=True)
class MacOSIsolatedEpisodeRunnerV09:
    """Production runner backed by the v0.9 macOS sandbox implementation.

    The signer is the independently enrolled *runner* identity.  The canonical
    aggregate is deliberately signed by a different executor identity, which
    ``run_canonical_per_episode_executor_v0_9`` enforces.
    """

    runner_signer: Ed25519AttestationSigner
    timeout_seconds: int = ISOLATION_TIMEOUT_SECONDS
    resource_limits: IsolationResourceLimitsV09 = DEFAULT_RESOURCE_LIMITS

    def run(
        self,
        *,
        task: CanonicalEpisodeTaskV09,
        bundle_path: Path,
        entrypoint_path: Path,
        visible_input_path: Path,
        isolation_working_directory: Path,
        isolation_arguments: tuple[str, ...],
    ) -> IsolatedTaskRunArtifactsV09:
        output_path = isolation_working_directory / ISOLATION_OUTPUT_RELATIVE_PATH
        expected_arguments = _canonical_isolation_arguments(
            task=task,
            entrypoint_path=entrypoint_path,
            visible_input_path=visible_input_path,
            output_path=output_path,
        )
        if isolation_arguments != expected_arguments:
            raise ValueError("macOS runner received noncanonical isolation arguments")
        isolation_payload = run_macos_isolated_execution_v0_9(
            command_engine_path=Path(task.command_engine_path),
            arguments=isolation_arguments,
            code_bundle_path=bundle_path,
            input_artifact_paths={"visible_episode_input": visible_input_path},
            working_directory=isolation_working_directory,
            expected_output_relative_paths={ISOLATION_OUTPUT_LABEL: ISOLATION_OUTPUT_RELATIVE_PATH},
            executor=self.runner_signer,
            timeout_seconds=self.timeout_seconds,
            resource_limits=self.resource_limits,
        )
        verified_isolation = verify_isolation_receipt_v0_9(
            isolation_payload,
            trusted_executor=self.runner_signer.verifier(),
            command_engine_path=Path(task.command_engine_path),
            arguments=isolation_arguments,
            code_bundle_path=bundle_path,
            input_artifact_paths={"visible_episode_input": visible_input_path},
            working_directory=isolation_working_directory,
            expected_output_relative_paths={ISOLATION_OUTPUT_LABEL: ISOLATION_OUTPUT_RELATIVE_PATH},
            timeout_seconds=self.timeout_seconds,
            resource_limits=self.resource_limits,
        )
        candidate = _load_candidate_output(output_path)
        expected_candidate_bindings = (
            candidate.output.task_content_sha256 == task.content_sha256,
            candidate.output.execution_id == task.execution_id,
            candidate.output.task_index == task.task_index,
            candidate.output.arm == task.arm,
            candidate.output.episode_id == task.episode_id,
        )
        if not all(expected_candidate_bindings):
            raise ValueError("isolated candidate output changed its canonical task binding")
        receipt = make_isolated_episode_execution_receipt_v0_9(
            task=task,
            action_sequence=candidate.output.action_sequence,
            mechanism_steps=candidate.output.mechanism_steps,
            exit_status="succeeded",
            exit_code=verified_isolation.exit_code,
            isolation_receipt_content_sha256=str(isolation_payload["content_sha256"]),
            isolated_output_artifact_sha256=candidate.output_artifact_sha256,
            isolated_output_content_sha256=candidate.output_content_sha256,
            signer=self.runner_signer,
        )
        return IsolatedTaskRunArtifactsV09(
            episode_execution_receipt=receipt,
            isolation_execution_receipt=isolation_payload,
        )


@dataclass(frozen=True, slots=True)
class _PathSnapshot:
    content_sha256: str
    filesystem_sha256: str


@dataclass(frozen=True, slots=True)
class _PreparedBundle:
    binding: ArmBundleBindingV09
    bundle_path: Path
    manifest_path: Path
    entrypoint_path: Path


@dataclass(frozen=True, slots=True)
class _PreparedInput:
    binding: EpisodeInputBindingV09
    input_path: Path


@dataclass(frozen=True, slots=True)
class _PreparedContext:
    bundles: tuple[_PreparedBundle, ...]
    inputs: tuple[_PreparedInput, ...]
    opening_binding: SealedOpeningBindingV09
    opening_path: Path


@dataclass(frozen=True, slots=True)
class RecomputedSealedVisibleInputsV09:
    """Canonical model-visible inputs regenerated from one sealed opening."""

    episodes: tuple[ProjectTwoReplayEpisode, ...]
    canonical_bytes_by_episode: Mapping[str, bytes]
    artifact_sha256_by_episode: Mapping[str, str]
    episode_content_sha256_by_episode: Mapping[str, str]

    @property
    def episode_ids(self) -> tuple[str, ...]:
        return tuple(str(episode.episode_id) for episode in self.episodes)


def recompute_sealed_visible_episode_inputs_v0_9(
    opening: SealedGateBOpeningV09,
) -> RecomputedSealedVisibleInputsV09:
    """Regenerate Gate-B episodes and their exact canonical input bytes.

    This is the sole production derivation of canonical executor episode IDs
    and visible input bytes.  It starts from
    ``recompute_sealed_gate_b_holdout_v0_9`` and uses the official world-rollout
    adapter with the confirmatory TEST split; caller-named episodes are never
    used as the source of truth.
    """

    recomputed = recompute_sealed_gate_b_holdout_v0_9(opening)
    episodes: list[ProjectTwoReplayEpisode] = []
    for world, rollout in recomputed.world_rollouts:
        dataset = adapt_world_rollout(
            world,
            rollout,
            split=ProjectTwoDatasetSplit.TEST,
        )
        if len(dataset.episodes) != 1:
            raise ValueError("sealed world-rollout adapter did not produce exactly one episode")
        episodes.append(dataset.episodes[0])
    episode_ids = tuple(str(episode.episode_id) for episode in episodes)
    if not episode_ids or len(set(episode_ids)) != len(episode_ids):
        raise ValueError("recomputed sealed holdout has empty or duplicate episode ids")
    canonical_bytes_by_episode: dict[str, bytes] = {}
    artifact_hashes: dict[str, str] = {}
    episode_content_hashes: dict[str, str] = {}
    for episode_id, episode in zip(episode_ids, episodes, strict=True):
        wrapper = VisibleEpisodeInputV09(
            protocol=VISIBLE_INPUT_PROTOCOL_ID,
            episode=episode,
        )
        encoded = canonical_json(wrapper).encode("utf-8")
        canonical_bytes_by_episode[episode_id] = encoded
        artifact_hashes[episode_id] = hashlib.sha256(encoded).hexdigest()
        episode_content_hashes[episode_id] = content_sha256(episode)
    return RecomputedSealedVisibleInputsV09(
        episodes=tuple(episodes),
        canonical_bytes_by_episode=canonical_bytes_by_episode,
        artifact_sha256_by_episode=artifact_hashes,
        episode_content_sha256_by_episode=episode_content_hashes,
    )


def _recompute_sealed_visible_inputs_from_path(
    path: Path,
) -> RecomputedSealedVisibleInputsV09:
    payload, _ = _load_json_file(path)
    unsigned = dict(payload)
    stored = unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError("sealed opening content hash mismatch during holdout recomputation")
    opening = SealedGateBOpeningV09.model_validate(unsigned)
    return recompute_sealed_visible_episode_inputs_v0_9(opening)


def _raw_file_sha256(path: Path) -> str:
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        stat.S_IMODE(before.st_mode),
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        stat.S_IMODE(after.st_mode),
    )
    if before_identity != after_identity:
        raise ValueError(f"artifact changed while it was hashed: {path}")
    return hashlib.sha256(raw).hexdigest()


def _snapshot_once(path: Path) -> _PathSnapshot:
    if path.is_symlink():
        raise ValueError(f"content-addressed artifact cannot be a symlink: {path}")
    resolved = path.resolve(strict=True)
    root_stat = resolved.lstat()
    if stat.S_ISREG(root_stat.st_mode):
        digest = _raw_file_sha256(resolved)
        filesystem = content_sha256(
            {
                "kind": "file",
                "mode": stat.S_IMODE(root_stat.st_mode),
                "size": root_stat.st_size,
                "content_sha256": digest,
            }
        )
        return _PathSnapshot(content_sha256=digest, filesystem_sha256=filesystem)
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError(f"artifact is neither a regular file nor directory: {path}")

    file_rows: list[tuple[str, str]] = []
    filesystem_rows: list[tuple[str, str, int, int, str | None]] = [
        (".", "directory", stat.S_IMODE(root_stat.st_mode), 0, None)
    ]
    for item in sorted(resolved.rglob("*"), key=lambda candidate: candidate.as_posix()):
        relative = item.relative_to(resolved).as_posix()
        item_stat = item.lstat()
        if stat.S_ISLNK(item_stat.st_mode):
            raise ValueError(f"content-addressed bundle contains a symlink: {relative}")
        if stat.S_ISDIR(item_stat.st_mode):
            filesystem_rows.append(
                (relative, "directory", stat.S_IMODE(item_stat.st_mode), 0, None)
            )
            continue
        if not stat.S_ISREG(item_stat.st_mode):
            raise ValueError(f"content-addressed bundle contains a special file: {relative}")
        digest = _raw_file_sha256(item)
        file_rows.append((relative, digest))
        filesystem_rows.append(
            (
                relative,
                "file",
                stat.S_IMODE(item_stat.st_mode),
                item_stat.st_size,
                digest,
            )
        )
    if not file_rows:
        raise ValueError("content-addressed directory bundle is empty")
    return _PathSnapshot(
        content_sha256=content_sha256(
            {"protocol": BUNDLE_TREE_PROTOCOL_ID, "files": tuple(file_rows)}
        ),
        filesystem_sha256=content_sha256(
            {"protocol": BUNDLE_TREE_PROTOCOL_ID, "filesystem": tuple(filesystem_rows)}
        ),
    )


def artifact_content_sha256_v0_9(path: Path) -> str:
    """Return the stable byte/tree identity used by frozen v0.9 mappings."""

    first = _snapshot_once(path)
    second = _snapshot_once(path)
    if first != second:
        raise ValueError(f"artifact is not stable across consecutive hashes: {path}")
    return first.content_sha256


def _stable_snapshot(path: Path) -> _PathSnapshot:
    first = _snapshot_once(path)
    second = _snapshot_once(path)
    if first != second:
        raise ValueError(f"artifact is not stable across consecutive hashes: {path}")
    return first


def _load_json_file(path: Path) -> tuple[dict[str, Any], _PathSnapshot]:
    before = _stable_snapshot(path)
    if path.resolve(strict=True).is_dir():
        raise ValueError(f"JSON artifact must be a regular file: {path}")
    try:
        decoded = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON artifact is unreadable: {path}") from exc
    after = _stable_snapshot(path)
    if before != after:
        raise ValueError(f"JSON artifact changed while it was loaded: {path}")
    if not isinstance(decoded, dict):
        raise ValueError(f"JSON artifact must contain one object: {path}")
    return decoded, before


def _fixed_manifest_path(bundle_path: Path) -> Path:
    if bundle_path.is_dir():
        return bundle_path / BUNDLE_MANIFEST_FILENAME
    return bundle_path.with_name(bundle_path.name + BUNDLE_MANIFEST_SIDECAR_SUFFIX)


def _load_bundle_manifest(
    *,
    arm: str,
    bundle_path: Path,
    expected_manifest_content_sha256: str,
) -> tuple[ArmBundleManifestV09, Path, _PathSnapshot]:
    manifest_path = _fixed_manifest_path(bundle_path)
    if manifest_path.is_symlink():
        raise ValueError(f"bundle manifest cannot be a symlink: {manifest_path}")
    payload, snapshot = _load_json_file(manifest_path)
    unsigned = dict(payload)
    stored = unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError(f"bundle manifest content hash mismatch for arm {arm!r}")
    if stored != expected_manifest_content_sha256:
        raise ValueError(f"bundle manifest differs from frozen mapping for arm {arm!r}")
    manifest = ArmBundleManifestV09.model_validate(unsigned)
    expected_kind = "directory" if bundle_path.is_dir() else "file"
    if manifest.arm != arm or manifest.bundle_kind != expected_kind:
        raise ValueError(f"bundle manifest arm/kind mismatch for arm {arm!r}")
    return manifest, manifest_path.resolve(strict=True), snapshot


def _resolve_entrypoint(bundle_path: Path, manifest: ArmBundleManifestV09) -> Path:
    if bundle_path.is_file():
        if manifest.entrypoint != bundle_path.name:
            raise ValueError("a file bundle's fixed entrypoint must be the bundle file itself")
        return bundle_path

    relative = PurePosixPath(manifest.entrypoint)
    if (
        relative.is_absolute()
        or relative in {PurePosixPath("."), PurePosixPath("")}
        or ".." in relative.parts
        or "\\" in manifest.entrypoint
    ):
        raise ValueError("directory bundle entrypoint must be a contained POSIX path")
    candidate = bundle_path.joinpath(*relative.parts)
    if candidate.is_symlink():
        raise ValueError("bundle entrypoint cannot be a symlink")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(bundle_path)
    except ValueError as exc:
        raise ValueError("bundle entrypoint escapes its content-addressed directory") from exc
    if not resolved.is_file():
        raise ValueError("bundle entrypoint is not a regular file")
    return resolved


def _prepare_bundle(
    *,
    arm: str,
    path: Path,
    expected_bundle_sha256: str,
    expected_manifest_content_sha256: str,
) -> _PreparedBundle:
    if path.is_symlink():
        raise ValueError(f"bundle path cannot be a symlink for arm {arm!r}")
    bundle_path = path.resolve(strict=True)
    if bundle_path.is_file():
        raise ValueError(
            "single-file bundles are forbidden because an out-of-tree sidecar manifest "
            "cannot be part of the frozen bundle identity"
        )
    before = _stable_snapshot(bundle_path)
    if before.content_sha256 != expected_bundle_sha256:
        raise ValueError(f"implementation bundle differs from frozen mapping for arm {arm!r}")
    manifest, manifest_path, manifest_snapshot = _load_bundle_manifest(
        arm=arm,
        bundle_path=bundle_path,
        expected_manifest_content_sha256=expected_manifest_content_sha256,
    )
    entrypoint_path = _resolve_entrypoint(bundle_path, manifest)
    entrypoint_snapshot = _stable_snapshot(entrypoint_path)
    if entrypoint_snapshot.content_sha256 != manifest.entrypoint_sha256:
        raise ValueError(f"bundle entrypoint hash mismatch for arm {arm!r}")
    command_engine_source = Path(manifest.command_engine_path)
    if not command_engine_source.is_absolute() or command_engine_source.is_symlink():
        raise ValueError(f"bundle command engine path is not fixed/regular for arm {arm!r}")
    command_engine_path = command_engine_source.resolve(strict=True)
    if not command_engine_path.is_file():
        raise ValueError(f"bundle command engine is not a regular file for arm {arm!r}")
    command_engine_snapshot = _stable_snapshot(command_engine_path)
    if command_engine_snapshot.content_sha256 != manifest.command_engine_sha256:
        raise ValueError(f"bundle command engine hash mismatch for arm {arm!r}")
    after = _stable_snapshot(bundle_path)
    manifest_after = _stable_snapshot(manifest_path)
    command_engine_after = _stable_snapshot(command_engine_path)
    if (
        before != after
        or manifest_snapshot != manifest_after
        or command_engine_snapshot != command_engine_after
    ):
        raise ValueError(f"bundle changed while its manifest was resolved for arm {arm!r}")
    return _PreparedBundle(
        binding=ArmBundleBindingV09(
            arm=arm,
            bundle_content_sha256=before.content_sha256,
            bundle_filesystem_sha256=before.filesystem_sha256,
            manifest_content_sha256=expected_manifest_content_sha256,
            manifest_file_sha256=manifest_snapshot.content_sha256,
            manifest_filesystem_sha256=manifest_snapshot.filesystem_sha256,
            entrypoint=manifest.entrypoint,
            entrypoint_content_sha256=entrypoint_snapshot.content_sha256,
            entrypoint_filesystem_sha256=entrypoint_snapshot.filesystem_sha256,
            command_engine_path=str(command_engine_path),
            command_engine_content_sha256=command_engine_snapshot.content_sha256,
            command_engine_filesystem_sha256=command_engine_snapshot.filesystem_sha256,
        ),
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        entrypoint_path=entrypoint_path,
    )


def _reject_seed_or_evaluator_channels(value: Any, path: str = "visible_input") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_").replace(" ", "_")
            if (
                normalized.startswith("true")
                or "truth" in normalized
                or "evaluator" in normalized
                or "oracle" in normalized
                or "seed" in normalized
                or normalized == "latent_state"
            ):
                raise ValueError(f"visible-only input contains a forbidden channel at {path}.{key}")
            _reject_seed_or_evaluator_channels(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_seed_or_evaluator_channels(nested, f"{path}[{index}]")


def _prepare_input(
    *,
    episode_id: str,
    path: Path,
    expected_input_sha256: str,
) -> _PreparedInput:
    if path.is_symlink():
        raise ValueError(f"visible input cannot be a symlink for episode {episode_id!r}")
    input_path = path.resolve(strict=True)
    payload, snapshot = _load_json_file(input_path)
    if snapshot.content_sha256 != expected_input_sha256:
        raise ValueError(f"visible input differs from frozen mapping for episode {episode_id!r}")
    reject_truth_leakage(payload)
    _reject_seed_or_evaluator_channels(payload)
    visible = VisibleEpisodeInputV09.model_validate(payload)
    if str(visible.episode.episode_id) != episode_id:
        raise ValueError(f"visible input episode id mismatch for episode {episode_id!r}")
    return _PreparedInput(
        binding=EpisodeInputBindingV09(
            episode_id=episode_id,
            input_artifact_sha256=snapshot.content_sha256,
            input_filesystem_sha256=snapshot.filesystem_sha256,
            visible_episode_content_sha256=content_sha256(visible.episode),
            step_count=len(visible.episode.steps),
        ),
        input_path=input_path,
    )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _validate_exact_mapping(
    name: str,
    mapping: Mapping[str, object],
    expected_keys: Sequence[str],
) -> None:
    if set(mapping) != set(expected_keys) or len(mapping) != len(expected_keys):
        raise ValueError(f"{name} does not have exact required coverage")


def _path_is_within(candidate: Path, directory: Path) -> bool:
    try:
        candidate.relative_to(directory)
    except ValueError:
        return False
    return True


def _prepare_context(
    *,
    episode_ids: tuple[str, ...],
    bundle_paths_by_arm: Mapping[str, Path],
    expected_bundle_sha256_by_arm: Mapping[str, str],
    expected_bundle_manifest_content_sha256_by_arm: Mapping[str, str],
    visible_input_paths_by_episode: Mapping[str, Path],
    expected_visible_input_sha256_by_episode: Mapping[str, str],
    sealed_opening_artifact_path: Path,
    expected_sealed_opening_artifact_sha256: str,
) -> _PreparedContext:
    _validate_exact_mapping("bundle paths", bundle_paths_by_arm, EXPECTED_ARMS)
    _validate_exact_mapping("frozen bundle hashes", expected_bundle_sha256_by_arm, EXPECTED_ARMS)
    _validate_exact_mapping(
        "frozen bundle manifest hashes",
        expected_bundle_manifest_content_sha256_by_arm,
        EXPECTED_ARMS,
    )
    _validate_exact_mapping("visible input paths", visible_input_paths_by_episode, episode_ids)
    _validate_exact_mapping(
        "frozen visible input hashes",
        expected_visible_input_sha256_by_episode,
        episode_ids,
    )
    for name, values in (
        ("frozen bundle hashes", expected_bundle_sha256_by_arm.values()),
        (
            "frozen bundle manifest hashes",
            expected_bundle_manifest_content_sha256_by_arm.values(),
        ),
        ("frozen visible input hashes", expected_visible_input_sha256_by_episode.values()),
        ("sealed opening hash", (expected_sealed_opening_artifact_sha256,)),
    ):
        if any(not isinstance(value, str) or not _is_sha256(value) for value in values):
            raise ValueError(f"{name} contains a malformed SHA-256 digest")

    bundles = tuple(
        _prepare_bundle(
            arm=arm,
            path=Path(bundle_paths_by_arm[arm]),
            expected_bundle_sha256=expected_bundle_sha256_by_arm[arm],
            expected_manifest_content_sha256=(expected_bundle_manifest_content_sha256_by_arm[arm]),
        )
        for arm in EXPECTED_ARMS
    )
    inputs = tuple(
        _prepare_input(
            episode_id=episode_id,
            path=Path(visible_input_paths_by_episode[episode_id]),
            expected_input_sha256=expected_visible_input_sha256_by_episode[episode_id],
        )
        for episode_id in episode_ids
    )
    if sealed_opening_artifact_path.is_symlink():
        raise ValueError("sealed opening artifact cannot be a symlink")
    opening_path = sealed_opening_artifact_path.resolve(strict=True)
    opening_snapshot = _stable_snapshot(opening_path)
    if opening_snapshot.content_sha256 != expected_sealed_opening_artifact_sha256:
        raise ValueError("sealed opening artifact differs from its frozen hash")
    opening_binding = SealedOpeningBindingV09(
        artifact_sha256=opening_snapshot.content_sha256,
        filesystem_sha256=opening_snapshot.filesystem_sha256,
    )

    bundle_roots = tuple(item.bundle_path for item in bundles)
    input_paths = tuple(item.input_path for item in inputs)
    if len(set(bundle_roots)) != len(bundle_roots):
        raise ValueError("canonical arms must use distinct bundle paths")
    if len(set(input_paths)) != len(input_paths):
        raise ValueError("canonical episodes must use distinct visible input files")
    protected_paths = (*input_paths, opening_path)
    for bundle in bundles:
        if any(path == bundle.bundle_path for path in protected_paths):
            raise ValueError("visible input/opening artifact aliases an implementation bundle")
        if bundle.bundle_path.is_dir() and any(
            _path_is_within(path, bundle.bundle_path) for path in protected_paths
        ):
            raise ValueError("visible input/opening artifact is contained inside a bundle")
    if opening_path in input_paths:
        raise ValueError("sealed opening artifact aliases a model-visible input")

    return _PreparedContext(
        bundles=bundles,
        inputs=inputs,
        opening_binding=opening_binding,
        opening_path=opening_path,
    )


def _prepare_verified_prerequisites(
    *,
    verifier: TrustedExecutionPrerequisiteVerifierV09,
    trusted_verifier_identity: Ed25519AttestationVerifier,
    expected_verifier_implementation_sha256: str,
    execution_id: str,
    episode_ids: tuple[str, ...],
    expected_bundle_sha256_by_arm: Mapping[str, str],
    visible_input_paths_by_episode: Mapping[str, Path],
    expected_visible_input_artifact_sha256_by_episode: Mapping[str, str],
    expected_visible_episode_content_sha256_by_episode: Mapping[str, str],
    frozen_manifest_artifact_path: Path,
    producer_run_artifact_path: Path,
    gate_a_report_artifact_path: Path,
    sealed_opening_artifact_path: Path,
) -> VerifiedExecutionPrerequisitesV09:
    named_paths = {
        "frozen manifest": frozen_manifest_artifact_path,
        "producer run": producer_run_artifact_path,
        "Gate A report": gate_a_report_artifact_path,
        "sealed opening": sealed_opening_artifact_path,
    }
    before: dict[str, _PathSnapshot] = {}
    resolved: dict[str, Path] = {}
    for label, path in named_paths.items():
        if path.is_symlink():
            raise ValueError(f"{label} artifact cannot be a symlink")
        resolved_path = path.resolve(strict=True)
        if not resolved_path.is_file():
            raise ValueError(f"{label} artifact must be a regular JSON file")
        resolved[label] = resolved_path
        before[label] = _stable_snapshot(resolved_path)
    if len(set(resolved.values())) != len(resolved):
        raise ValueError("semantic prerequisite artifacts must use distinct files")

    _validate_exact_mapping(
        "semantic-verifier visible input paths",
        visible_input_paths_by_episode,
        episode_ids,
    )
    _validate_exact_mapping(
        "semantic-verifier frozen visible input hashes",
        expected_visible_input_artifact_sha256_by_episode,
        episode_ids,
    )
    _validate_exact_mapping(
        "semantic-verifier visible episode content hashes",
        expected_visible_episode_content_sha256_by_episode,
        episode_ids,
    )
    resolved_visible_inputs: dict[str, Path] = {}
    visible_before: dict[str, _PathSnapshot] = {}
    for episode_id in episode_ids:
        path = Path(visible_input_paths_by_episode[episode_id])
        if path.is_symlink():
            raise ValueError("semantic-verifier visible input cannot be a symlink")
        resolved_path = path.resolve(strict=True)
        if not resolved_path.is_file():
            raise ValueError("semantic-verifier visible input must be a regular JSON file")
        resolved_visible_inputs[episode_id] = resolved_path
        visible_before[episode_id] = _stable_snapshot(resolved_path)
    if len(set(resolved_visible_inputs.values())) != len(episode_ids):
        raise ValueError("semantic-verifier visible inputs must use distinct files")
    if set(resolved_visible_inputs.values()) & set(resolved.values()):
        raise ValueError("visible inputs alias semantic prerequisite artifacts")
    if any(
        visible_before[episode_id].content_sha256
        != expected_visible_input_artifact_sha256_by_episode[episode_id]
        for episode_id in episode_ids
    ):
        raise ValueError("live visible input differs from the frozen sealed-holdout hash")

    implementation_sha256 = verifier.implementation_sha256
    if (
        not _is_sha256(expected_verifier_implementation_sha256)
        or implementation_sha256 != expected_verifier_implementation_sha256
    ):
        raise ValueError("semantic prerequisite verifier has no valid implementation identity")

    verified = verifier.verify(
        execution_id=execution_id,
        expected_episode_ids=episode_ids,
        expected_bundle_sha256_by_arm=expected_bundle_sha256_by_arm,
        frozen_manifest_artifact_path=resolved["frozen manifest"],
        producer_run_artifact_path=resolved["producer run"],
        gate_a_report_artifact_path=resolved["Gate A report"],
        sealed_opening_artifact_path=resolved["sealed opening"],
        visible_input_paths_by_episode=resolved_visible_inputs,
        expected_visible_input_artifact_sha256_by_episode=(
            expected_visible_input_artifact_sha256_by_episode
        ),
        expected_visible_episode_content_sha256_by_episode=(
            expected_visible_episode_content_sha256_by_episode
        ),
    )
    after = {label: _stable_snapshot(path) for label, path in resolved.items()}
    if before != after:
        raise ValueError("semantic prerequisite artifact changed during verification (TOCTOU)")
    visible_after = {
        episode_id: _stable_snapshot(path) for episode_id, path in resolved_visible_inputs.items()
    }
    if visible_before != visible_after:
        raise ValueError("visible input changed during semantic verification (TOCTOU)")
    expected_raw_hashes = {
        "frozen_manifest_artifact_sha256": before["frozen manifest"].content_sha256,
        "producer_run_artifact_sha256": before["producer run"].content_sha256,
        "gate_a_report_artifact_sha256": before["Gate A report"].content_sha256,
        "sealed_opening_artifact_sha256": before["sealed opening"].content_sha256,
    }
    dumped = verified.model_dump(mode="python")
    if any(dumped[field] != value for field, value in expected_raw_hashes.items()):
        raise ValueError("semantic verifier returned a prerequisite with the wrong live file hash")
    if (
        verified.execution_id != execution_id
        or verified.episode_ids != episode_ids
        or verified.arm_implementation_bundle_sha256 != dict(expected_bundle_sha256_by_arm)
        or verified.sealed_holdout_visible_input_artifact_sha256_by_episode
        != dict(expected_visible_input_artifact_sha256_by_episode)
        or verified.sealed_holdout_visible_episode_content_sha256_by_episode
        != dict(expected_visible_episode_content_sha256_by_episode)
    ):
        raise ValueError("semantic verifier returned the wrong execution scope")
    if (
        verified.prerequisite_verifier_protocol != PREREQUISITE_VERIFIER_PROTOCOL_ID
        or verified.prerequisite_verifier_implementation_sha256 != implementation_sha256
        or verified.prerequisite_verifier_key_id != trusted_verifier_identity.key_id
        or verified.prerequisite_verifier_public_key_base64
        != trusted_verifier_identity.public_key_base64
        or verified.prerequisite_verifier_public_key_sha256
        != trusted_verifier_identity.public_key_sha256
    ):
        raise AttestationError("semantic prerequisite verifier provenance is not enrolled")
    trusted_verifier_identity.verify(
        PREREQUISITE_ATTESTATION_DOMAIN,
        _prerequisite_attested_payload(verified),
        verified.prerequisite_verifier_attestation,
    )
    sealed_inputs = _recompute_sealed_visible_inputs_from_path(resolved["sealed opening"])
    if sealed_inputs.episode_ids != episode_ids:
        raise ValueError("caller episode ids differ from the recomputed sealed Gate-B holdout")
    if (
        dict(sealed_inputs.artifact_sha256_by_episode)
        != dict(expected_visible_input_artifact_sha256_by_episode)
        or dict(sealed_inputs.episode_content_sha256_by_episode)
        != dict(expected_visible_episode_content_sha256_by_episode)
        or verified.sealed_holdout_visible_input_artifact_sha256_by_episode
        != dict(sealed_inputs.artifact_sha256_by_episode)
        or verified.sealed_holdout_visible_episode_content_sha256_by_episode
        != dict(sealed_inputs.episode_content_sha256_by_episode)
    ):
        raise ValueError(
            "visible inputs differ from ProjectTwoReplayEpisode values recomputed from "
            "the sealed Gate-B opening"
        )
    for episode_id in episode_ids:
        if (
            resolved_visible_inputs[episode_id].read_bytes()
            != sealed_inputs.canonical_bytes_by_episode[episode_id]
        ):
            raise ValueError(
                "live visible input is not the canonical sealed ProjectTwoReplayEpisode encoding"
            )
    if visible_after != {
        episode_id: _stable_snapshot(path) for episode_id, path in resolved_visible_inputs.items()
    }:
        raise ValueError("visible input changed during sealed holdout recomputation (TOCTOU)")
    return verified


def _make_task(
    *,
    execution_id: str,
    task_index: int,
    bundle: ArmBundleBindingV09,
    episode: EpisodeInputBindingV09,
    opening: SealedOpeningBindingV09,
    prerequisites: VerifiedExecutionPrerequisitesV09,
) -> CanonicalEpisodeTaskV09:
    return CanonicalEpisodeTaskV09(
        protocol=TASK_PROTOCOL_ID,
        execution_id=execution_id,
        task_index=task_index,
        arm=bundle.arm,
        episode_id=episode.episode_id,
        visible_input_artifact_sha256=episode.input_artifact_sha256,
        visible_input_filesystem_sha256=episode.input_filesystem_sha256,
        implementation_bundle_sha256=bundle.bundle_content_sha256,
        implementation_bundle_filesystem_sha256=bundle.bundle_filesystem_sha256,
        bundle_manifest_content_sha256=bundle.manifest_content_sha256,
        entrypoint=bundle.entrypoint,
        entrypoint_content_sha256=bundle.entrypoint_content_sha256,
        command_engine_path=bundle.command_engine_path,
        command_engine_content_sha256=bundle.command_engine_content_sha256,
        sealed_opening_artifact_sha256=opening.artifact_sha256,
        sealed_opening_filesystem_sha256=opening.filesystem_sha256,
        execution_prerequisites_sha256=prerequisites.content_sha256,
        expected_step_count=episode.step_count,
        isolation_profile=ISOLATION_PROFILE,
    )


def initial_mechanism_state_sha256_v0_9(task: CanonicalEpisodeTaskV09) -> str:
    """Return the mandatory first state-chain anchor for an isolated task."""

    return content_sha256(
        {
            "protocol": STATE_CHAIN_PROTOCOL_ID,
            "task_content_sha256": task.content_sha256,
            "position": "initial",
        }
    )


def make_isolated_candidate_output_v0_9(
    *,
    task: CanonicalEpisodeTaskV09,
    action_sequence: Sequence[str],
    mechanism_steps: Sequence[MechanismStepRecordV09],
) -> dict[str, Any]:
    """Create the exact JSON output that the bundle must write inside isolation."""

    steps = tuple(mechanism_steps)
    output = IsolatedCandidateOutputV09(
        protocol=CANDIDATE_OUTPUT_PROTOCOL_ID,
        task_content_sha256=task.content_sha256,
        execution_id=task.execution_id,
        task_index=task.task_index,
        arm=task.arm,
        episode_id=task.episode_id,
        action_sequence=tuple(action_sequence),
        mechanism_steps=steps,
        final_state_sha256=steps[-1].output_state_sha256,
    )
    payload = output.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def _load_candidate_output(path: Path) -> BoundCandidateOutputV09:
    payload, snapshot = _load_json_file(path)
    unsigned = dict(payload)
    stored = unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError("isolated candidate output content hash mismatch")
    output = IsolatedCandidateOutputV09.model_validate(unsigned)
    return BoundCandidateOutputV09(
        output_artifact_sha256=snapshot.content_sha256,
        output_content_sha256=stored,
        output=output,
    )


def make_isolated_episode_execution_receipt_v0_9(
    *,
    task: CanonicalEpisodeTaskV09,
    action_sequence: Sequence[str],
    mechanism_steps: Sequence[MechanismStepRecordV09],
    exit_status: Literal["succeeded", "failed"],
    exit_code: int,
    isolation_receipt_content_sha256: str,
    isolated_output_artifact_sha256: str,
    isolated_output_content_sha256: str,
    signer: Ed25519AttestationSigner,
) -> dict[str, Any]:
    """Sign a result in the isolated-runner domain.

    This helper belongs on the trusted runner side.  Possessing it conveys no
    authority without the separately enrolled runner private key.
    """

    verifier = signer.verifier()
    steps = tuple(mechanism_steps)
    unsigned = IsolatedEpisodeExecutionReceiptV09(
        protocol=RECEIPT_PROTOCOL_ID,
        task_content_sha256=task.content_sha256,
        execution_id=task.execution_id,
        task_index=task.task_index,
        arm=task.arm,
        episode_id=task.episode_id,
        visible_input_artifact_sha256=task.visible_input_artifact_sha256,
        implementation_bundle_sha256=task.implementation_bundle_sha256,
        bundle_manifest_content_sha256=task.bundle_manifest_content_sha256,
        entrypoint_content_sha256=task.entrypoint_content_sha256,
        sealed_opening_artifact_sha256=task.sealed_opening_artifact_sha256,
        execution_prerequisites_sha256=task.execution_prerequisites_sha256,
        isolation_profile=task.isolation_profile,
        isolation_receipt_content_sha256=isolation_receipt_content_sha256,
        isolated_output_artifact_sha256=isolated_output_artifact_sha256,
        isolated_output_content_sha256=isolated_output_content_sha256,
        action_sequence=tuple(action_sequence),
        mechanism_steps=steps,
        final_state_sha256=steps[-1].output_state_sha256 if steps else None,
        exit_status=exit_status,
        exit_code=exit_code,
        runner_key_id=verifier.key_id,
        runner_public_key_base64=verifier.public_key_base64,
        runner_public_key_sha256=verifier.public_key_sha256,
    )
    signed = unsigned.model_copy(
        update={
            "attestation": signer.sign(
                RECEIPT_ATTESTATION_DOMAIN,
                attested_payload(unsigned),
            )
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def _load_bound_isolation_receipt(
    payload: Mapping[str, Any],
) -> BoundIsolationExecutionReceiptV09:
    unsigned_payload = dict(payload)
    stored = unsigned_payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned_payload) != stored:
        raise ValueError("isolation execution receipt content hash mismatch")
    return BoundIsolationExecutionReceiptV09(
        isolation_receipt_content_sha256=stored,
        receipt=IsolationExecutionReceiptV09.model_validate(unsigned_payload),
    )


def _load_bound_receipt(
    payload: Mapping[str, Any],
    *,
    isolation_payload: Mapping[str, Any],
    candidate_output_path: Path,
) -> BoundEpisodeExecutionReceiptV09:
    unsigned_payload = dict(payload)
    stored = unsigned_payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned_payload) != stored:
        raise ValueError("isolated episode receipt content hash mismatch")
    receipt = IsolatedEpisodeExecutionReceiptV09.model_validate(unsigned_payload)
    return BoundEpisodeExecutionReceiptV09(
        receipt_content_sha256=stored,
        receipt=receipt,
        isolation=_load_bound_isolation_receipt(isolation_payload),
        candidate_output=_load_candidate_output(candidate_output_path),
    )


def _canonical_isolation_arguments(
    *,
    task: CanonicalEpisodeTaskV09,
    entrypoint_path: Path,
    visible_input_path: Path,
    output_path: Path,
) -> tuple[str, ...]:
    return (
        str(entrypoint_path),
        "--visible-input",
        str(visible_input_path),
        "--output",
        str(output_path),
        "--task-content-sha256",
        task.content_sha256,
    )


def _verify_isolation_evidence(
    bound: BoundEpisodeExecutionReceiptV09,
    *,
    expected_task: CanonicalEpisodeTaskV09,
    bundle_path: Path,
    entrypoint_path: Path,
    visible_input_path: Path,
    isolation_working_directory: Path,
    trusted_runner: Ed25519AttestationVerifier,
    verifier: TrustedIsolationReceiptVerifierV09,
) -> None:
    output_path = isolation_working_directory / ISOLATION_OUTPUT_RELATIVE_PATH
    arguments = _canonical_isolation_arguments(
        task=expected_task,
        entrypoint_path=entrypoint_path,
        visible_input_path=visible_input_path,
        output_path=output_path,
    )
    isolation_payload = bound.isolation.receipt.model_dump(mode="json")
    isolation_payload["content_sha256"] = bound.isolation.isolation_receipt_content_sha256
    verified = verifier(
        isolation_payload,
        trusted_executor=trusted_runner,
        command_engine_path=Path(expected_task.command_engine_path),
        arguments=arguments,
        code_bundle_path=bundle_path,
        input_artifact_paths={"visible_episode_input": visible_input_path},
        working_directory=isolation_working_directory,
        expected_output_relative_paths={ISOLATION_OUTPUT_LABEL: ISOLATION_OUTPUT_RELATIVE_PATH},
        timeout_seconds=ISOLATION_TIMEOUT_SECONDS,
        resource_limits=DEFAULT_RESOURCE_LIMITS,
    )
    if verified.formal_isolation_verified is not True or verified.status != "ISOLATION_PASSED":
        raise ValueError("task lacks a formally verified isolation receipt")
    if len(verified.output_artifacts) != 1:
        raise ValueError("isolation receipt did not bind exactly one candidate output")
    output_binding = verified.output_artifacts[0]
    if (
        output_binding.label != ISOLATION_OUTPUT_LABEL
        or output_binding.content_sha256 != bound.candidate_output.output_artifact_sha256
    ):
        raise ValueError("isolation receipt output does not bind the candidate output bytes")
    candidate = bound.candidate_output.output
    expected_candidate_bindings: dict[str, object] = {
        "task_content_sha256": expected_task.content_sha256,
        "execution_id": expected_task.execution_id,
        "task_index": expected_task.task_index,
        "arm": expected_task.arm,
        "episode_id": expected_task.episode_id,
    }
    for field_name, expected in expected_candidate_bindings.items():
        if getattr(candidate, field_name) != expected:
            raise ValueError(f"candidate output changed task binding {field_name!r}")


def _verify_bound_receipt(
    bound: BoundEpisodeExecutionReceiptV09,
    *,
    expected_task: CanonicalEpisodeTaskV09,
    trusted_runner: Ed25519AttestationVerifier,
    require_success: bool,
) -> IsolatedEpisodeExecutionReceiptV09:
    receipt = bound.receipt
    if (
        receipt.runner_key_id != trusted_runner.key_id
        or receipt.runner_public_key_base64 != trusted_runner.public_key_base64
        or receipt.runner_public_key_sha256 != trusted_runner.public_key_sha256
    ):
        raise AttestationError("isolated receipt is outside the trusted runner enrollment")
    trusted_runner.verify(
        RECEIPT_ATTESTATION_DOMAIN,
        attested_payload(receipt),
        receipt.attestation,
    )
    expected_bindings: dict[str, object] = {
        "task_content_sha256": expected_task.content_sha256,
        "execution_id": expected_task.execution_id,
        "task_index": expected_task.task_index,
        "arm": expected_task.arm,
        "episode_id": expected_task.episode_id,
        "visible_input_artifact_sha256": expected_task.visible_input_artifact_sha256,
        "implementation_bundle_sha256": expected_task.implementation_bundle_sha256,
        "bundle_manifest_content_sha256": expected_task.bundle_manifest_content_sha256,
        "entrypoint_content_sha256": expected_task.entrypoint_content_sha256,
        "sealed_opening_artifact_sha256": expected_task.sealed_opening_artifact_sha256,
        "execution_prerequisites_sha256": expected_task.execution_prerequisites_sha256,
        "isolation_profile": expected_task.isolation_profile,
    }
    for field_name, expected in expected_bindings.items():
        if getattr(receipt, field_name) != expected:
            raise ValueError(f"isolated receipt changed task binding {field_name!r}")
    if len(receipt.action_sequence) != expected_task.expected_step_count:
        raise ValueError("isolated receipt has partial or extra action coverage")
    if len(receipt.mechanism_steps) != expected_task.expected_step_count:
        raise ValueError("isolated receipt has partial or extra mechanism-step coverage")
    if not receipt.mechanism_steps or receipt.mechanism_steps[
        0
    ].input_state_sha256 != initial_mechanism_state_sha256_v0_9(expected_task):
        raise ValueError("isolated receipt state chain has the wrong task anchor")
    if require_success and (receipt.exit_status != "succeeded" or receipt.exit_code != 0):
        raise ValueError("canonical execution cannot accept a partial or failed task")
    candidate = bound.candidate_output.output
    if (
        receipt.action_sequence != candidate.action_sequence
        or receipt.mechanism_steps != candidate.mechanism_steps
        or receipt.final_state_sha256 != candidate.final_state_sha256
    ):
        raise ValueError("signed episode receipt differs from isolated candidate output")
    return receipt


def verify_isolated_episode_execution_receipt_v0_9(
    payload: Mapping[str, Any],
    *,
    isolation_payload: Mapping[str, Any],
    candidate_output_path: Path,
    expected_task: CanonicalEpisodeTaskV09,
    trusted_runner: Ed25519AttestationVerifier,
    bundle_path: Path,
    entrypoint_path: Path,
    visible_input_path: Path,
    isolation_working_directory: Path,
    isolation_receipt_verifier: TrustedIsolationReceiptVerifierV09,
    require_success: bool = True,
) -> IsolatedEpisodeExecutionReceiptV09:
    """Verify one flat runner receipt against one freshly constructed task."""

    bound = _load_bound_receipt(
        payload,
        isolation_payload=isolation_payload,
        candidate_output_path=candidate_output_path,
    )
    _verify_isolation_evidence(
        bound,
        expected_task=expected_task,
        bundle_path=bundle_path,
        entrypoint_path=entrypoint_path,
        visible_input_path=visible_input_path,
        isolation_working_directory=isolation_working_directory,
        trusted_runner=trusted_runner,
        verifier=isolation_receipt_verifier,
    )
    return _verify_bound_receipt(
        bound,
        expected_task=expected_task,
        trusted_runner=trusted_runner,
        require_success=require_success,
    )


def _assert_task_artifacts_unchanged(
    *,
    bundle: _PreparedBundle,
    episode: _PreparedInput,
    opening_binding: SealedOpeningBindingV09,
    opening_path: Path,
    expected_bundle_sha256: str,
    expected_manifest_content_sha256: str,
    expected_input_sha256: str,
) -> None:
    fresh_bundle = _prepare_bundle(
        arm=bundle.binding.arm,
        path=bundle.bundle_path,
        expected_bundle_sha256=expected_bundle_sha256,
        expected_manifest_content_sha256=expected_manifest_content_sha256,
    )
    fresh_input = _prepare_input(
        episode_id=episode.binding.episode_id,
        path=episode.input_path,
        expected_input_sha256=expected_input_sha256,
    )
    fresh_opening = _stable_snapshot(opening_path)
    if (
        fresh_bundle.binding != bundle.binding
        or fresh_input.binding != episode.binding
        or fresh_opening.content_sha256 != opening_binding.artifact_sha256
        or fresh_opening.filesystem_sha256 != opening_binding.filesystem_sha256
    ):
        raise ValueError("task artifact changed across isolated execution (TOCTOU)")


def _validate_execution_request(execution_id: str, episode_ids: tuple[str, ...]) -> None:
    if len(execution_id) < 16:
        raise ValueError("execution id must contain at least 16 characters")
    if not episode_ids or any(not episode_id.strip() for episode_id in episode_ids):
        raise ValueError("canonical execution requires non-empty episode ids")
    if len(set(episode_ids)) != len(episode_ids):
        raise ValueError("canonical execution cannot duplicate episode ids")


def _prepare_isolation_working_directories(
    *,
    paths_by_task: Mapping[tuple[str, str], Path],
    episode_ids: tuple[str, ...],
    require_empty: bool,
) -> dict[tuple[str, str], Path]:
    expected_keys = tuple((arm, episode_id) for arm in EXPECTED_ARMS for episode_id in episode_ids)
    if set(paths_by_task) != set(expected_keys) or len(paths_by_task) != len(expected_keys):
        raise ValueError("isolation working-directory mapping lacks exact task coverage")
    prepared: dict[tuple[str, str], Path] = {}
    for key in expected_keys:
        source = Path(paths_by_task[key])
        if source.is_symlink():
            raise ValueError("isolation working directory cannot be a symlink")
        resolved = source.resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError("isolation working path must be a real directory")
        if require_empty and any(resolved.iterdir()):
            raise ValueError("every isolation working directory must start empty")
        prepared[key] = resolved
    if len(set(prepared.values())) != len(prepared):
        raise ValueError("isolation tasks must use distinct working directories")
    return prepared


def run_canonical_per_episode_executor_v0_9(
    *,
    execution_id: str,
    expected_episode_ids: Sequence[str],
    bundle_paths_by_arm: Mapping[str, Path],
    expected_bundle_sha256_by_arm: Mapping[str, str],
    expected_bundle_manifest_content_sha256_by_arm: Mapping[str, str],
    visible_input_paths_by_episode: Mapping[str, Path],
    expected_visible_input_sha256_by_episode: Mapping[str, str],
    sealed_opening_artifact_path: Path,
    expected_sealed_opening_artifact_sha256: str,
    frozen_manifest_artifact_path: Path,
    producer_run_artifact_path: Path,
    gate_a_report_artifact_path: Path,
    trusted_prerequisite_verifier: TrustedExecutionPrerequisiteVerifierV09,
    trusted_prerequisite_verifier_identity: Ed25519AttestationVerifier,
    expected_prerequisite_verifier_implementation_sha256: str,
    isolation_working_directories_by_task: Mapping[tuple[str, str], Path],
    trusted_isolated_runner: TrustedIsolatedEpisodeRunnerV09,
    trusted_isolated_receipt_verifier: Ed25519AttestationVerifier,
    isolation_receipt_verifier: TrustedIsolationReceiptVerifierV09,
    enrolled_executor_signer: Ed25519AttestationSigner,
) -> dict[str, Any]:
    """Run and attest the exact ten-arm by episode Cartesian product."""

    episode_ids = tuple(expected_episode_ids)
    _validate_execution_request(execution_id, episode_ids)
    executor_verifier = enrolled_executor_signer.verifier()
    if executor_verifier.public_key_sha256 == trusted_isolated_receipt_verifier.public_key_sha256:
        raise ValueError("isolated runner and aggregate executor must use distinct enrollments")
    context = _prepare_context(
        episode_ids=episode_ids,
        bundle_paths_by_arm=bundle_paths_by_arm,
        expected_bundle_sha256_by_arm=expected_bundle_sha256_by_arm,
        expected_bundle_manifest_content_sha256_by_arm=(
            expected_bundle_manifest_content_sha256_by_arm
        ),
        visible_input_paths_by_episode=visible_input_paths_by_episode,
        expected_visible_input_sha256_by_episode=expected_visible_input_sha256_by_episode,
        sealed_opening_artifact_path=sealed_opening_artifact_path,
        expected_sealed_opening_artifact_sha256=(expected_sealed_opening_artifact_sha256),
    )
    prerequisites = _prepare_verified_prerequisites(
        verifier=trusted_prerequisite_verifier,
        trusted_verifier_identity=trusted_prerequisite_verifier_identity,
        expected_verifier_implementation_sha256=(
            expected_prerequisite_verifier_implementation_sha256
        ),
        execution_id=execution_id,
        episode_ids=episode_ids,
        expected_bundle_sha256_by_arm=expected_bundle_sha256_by_arm,
        visible_input_paths_by_episode={
            item.binding.episode_id: item.input_path for item in context.inputs
        },
        expected_visible_input_artifact_sha256_by_episode={
            item.binding.episode_id: item.binding.input_artifact_sha256 for item in context.inputs
        },
        expected_visible_episode_content_sha256_by_episode={
            item.binding.episode_id: item.binding.visible_episode_content_sha256
            for item in context.inputs
        },
        frozen_manifest_artifact_path=frozen_manifest_artifact_path,
        producer_run_artifact_path=producer_run_artifact_path,
        gate_a_report_artifact_path=gate_a_report_artifact_path,
        sealed_opening_artifact_path=sealed_opening_artifact_path,
    )
    if prerequisites.sealed_opening_artifact_sha256 != context.opening_binding.artifact_sha256:
        raise ValueError("semantic sealed-opening verification and live opening bytes disagree")
    isolation_working_directories = _prepare_isolation_working_directories(
        paths_by_task=isolation_working_directories_by_task,
        episode_ids=episode_ids,
        require_empty=True,
    )

    receipts: list[BoundEpisodeExecutionReceiptV09] = []
    task_index = 0
    for bundle in context.bundles:
        for episode in context.inputs:
            task = _make_task(
                execution_id=execution_id,
                task_index=task_index,
                bundle=bundle.binding,
                episode=episode.binding,
                opening=context.opening_binding,
                prerequisites=prerequisites,
            )
            working_directory = isolation_working_directories[
                (bundle.binding.arm, episode.binding.episode_id)
            ]
            output_path = working_directory / ISOLATION_OUTPUT_RELATIVE_PATH
            isolation_arguments = _canonical_isolation_arguments(
                task=task,
                entrypoint_path=bundle.entrypoint_path,
                visible_input_path=episode.input_path,
                output_path=output_path,
            )
            run_artifacts = trusted_isolated_runner.run(
                task=task,
                bundle_path=bundle.bundle_path,
                entrypoint_path=bundle.entrypoint_path,
                visible_input_path=episode.input_path,
                isolation_working_directory=working_directory,
                isolation_arguments=isolation_arguments,
            )
            bound = _load_bound_receipt(
                run_artifacts.episode_execution_receipt,
                isolation_payload=run_artifacts.isolation_execution_receipt,
                candidate_output_path=output_path,
            )
            _verify_bound_receipt(
                bound,
                expected_task=task,
                trusted_runner=trusted_isolated_receipt_verifier,
                require_success=True,
            )
            _verify_isolation_evidence(
                bound,
                expected_task=task,
                bundle_path=bundle.bundle_path,
                entrypoint_path=bundle.entrypoint_path,
                visible_input_path=episode.input_path,
                isolation_working_directory=working_directory,
                trusted_runner=trusted_isolated_receipt_verifier,
                verifier=isolation_receipt_verifier,
            )
            _assert_task_artifacts_unchanged(
                bundle=bundle,
                episode=episode,
                opening_binding=context.opening_binding,
                opening_path=context.opening_path,
                expected_bundle_sha256=expected_bundle_sha256_by_arm[bundle.binding.arm],
                expected_manifest_content_sha256=(
                    expected_bundle_manifest_content_sha256_by_arm[bundle.binding.arm]
                ),
                expected_input_sha256=(
                    expected_visible_input_sha256_by_episode[episode.binding.episode_id]
                ),
            )
            receipts.append(bound)
            task_index += 1

    final_context = _prepare_context(
        episode_ids=episode_ids,
        bundle_paths_by_arm=bundle_paths_by_arm,
        expected_bundle_sha256_by_arm=expected_bundle_sha256_by_arm,
        expected_bundle_manifest_content_sha256_by_arm=(
            expected_bundle_manifest_content_sha256_by_arm
        ),
        visible_input_paths_by_episode=visible_input_paths_by_episode,
        expected_visible_input_sha256_by_episode=expected_visible_input_sha256_by_episode,
        sealed_opening_artifact_path=sealed_opening_artifact_path,
        expected_sealed_opening_artifact_sha256=(expected_sealed_opening_artifact_sha256),
    )
    if (
        tuple(item.binding for item in final_context.bundles)
        != tuple(item.binding for item in context.bundles)
        or tuple(item.binding for item in final_context.inputs)
        != tuple(item.binding for item in context.inputs)
        or final_context.opening_binding != context.opening_binding
    ):
        raise ValueError("execution artifacts changed before aggregate signing (TOCTOU)")
    final_prerequisites = _prepare_verified_prerequisites(
        verifier=trusted_prerequisite_verifier,
        trusted_verifier_identity=trusted_prerequisite_verifier_identity,
        expected_verifier_implementation_sha256=(
            expected_prerequisite_verifier_implementation_sha256
        ),
        execution_id=execution_id,
        episode_ids=episode_ids,
        expected_bundle_sha256_by_arm=expected_bundle_sha256_by_arm,
        visible_input_paths_by_episode={
            item.binding.episode_id: item.input_path for item in final_context.inputs
        },
        expected_visible_input_artifact_sha256_by_episode={
            item.binding.episode_id: item.binding.input_artifact_sha256
            for item in final_context.inputs
        },
        expected_visible_episode_content_sha256_by_episode={
            item.binding.episode_id: item.binding.visible_episode_content_sha256
            for item in final_context.inputs
        },
        frozen_manifest_artifact_path=frozen_manifest_artifact_path,
        producer_run_artifact_path=producer_run_artifact_path,
        gate_a_report_artifact_path=gate_a_report_artifact_path,
        sealed_opening_artifact_path=sealed_opening_artifact_path,
    )
    if final_prerequisites != prerequisites:
        raise ValueError("verified execution prerequisites changed before aggregate signing")

    unsigned = CanonicalPerEpisodeExecutionArtifactV09(
        protocol=PROTOCOL_ID,
        execution_id=execution_id,
        action_execution_mode=EXECUTION_MODE,
        canonical_arms=EXPECTED_ARMS,
        episode_ids=episode_ids,
        arm_bundle_bindings=tuple(item.binding for item in context.bundles),
        episode_input_bindings=tuple(item.binding for item in context.inputs),
        sealed_opening_binding=context.opening_binding,
        verified_prerequisites=prerequisites,
        task_receipts=tuple(receipts),
        exact_arm_episode_coverage_verified=True,
        all_tasks_succeeded=True,
        visible_inputs_only_verified=True,
        reference_cores_relabelled_as_native=False,
        fidelity_or_native_reproduction_status="not_evaluated_by_executor",
        claim_boundary=CLAIM_BOUNDARY,
        executor_key_id=executor_verifier.key_id,
        executor_public_key_base64=executor_verifier.public_key_base64,
        executor_public_key_sha256=executor_verifier.public_key_sha256,
    )
    signed = unsigned.model_copy(
        update={
            "attestation": enrolled_executor_signer.sign(
                AGGREGATE_ATTESTATION_DOMAIN,
                attested_payload(unsigned),
            )
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    verify_canonical_per_episode_execution_artifact_v0_9(
        payload,
        expected_execution_id=execution_id,
        expected_episode_ids=episode_ids,
        bundle_paths_by_arm=bundle_paths_by_arm,
        expected_bundle_sha256_by_arm=expected_bundle_sha256_by_arm,
        expected_bundle_manifest_content_sha256_by_arm=(
            expected_bundle_manifest_content_sha256_by_arm
        ),
        visible_input_paths_by_episode=visible_input_paths_by_episode,
        expected_visible_input_sha256_by_episode=expected_visible_input_sha256_by_episode,
        sealed_opening_artifact_path=sealed_opening_artifact_path,
        expected_sealed_opening_artifact_sha256=(expected_sealed_opening_artifact_sha256),
        frozen_manifest_artifact_path=frozen_manifest_artifact_path,
        producer_run_artifact_path=producer_run_artifact_path,
        gate_a_report_artifact_path=gate_a_report_artifact_path,
        trusted_prerequisite_verifier=trusted_prerequisite_verifier,
        trusted_prerequisite_verifier_identity=trusted_prerequisite_verifier_identity,
        expected_prerequisite_verifier_implementation_sha256=(
            expected_prerequisite_verifier_implementation_sha256
        ),
        isolation_working_directories_by_task=(isolation_working_directories_by_task),
        trusted_isolated_receipt_verifier=trusted_isolated_receipt_verifier,
        isolation_receipt_verifier=isolation_receipt_verifier,
        trusted_enrolled_executor=executor_verifier,
    )
    return payload


def verify_canonical_per_episode_execution_artifact_v0_9(
    payload: Mapping[str, Any],
    *,
    expected_execution_id: str,
    expected_episode_ids: Sequence[str],
    bundle_paths_by_arm: Mapping[str, Path],
    expected_bundle_sha256_by_arm: Mapping[str, str],
    expected_bundle_manifest_content_sha256_by_arm: Mapping[str, str],
    visible_input_paths_by_episode: Mapping[str, Path],
    expected_visible_input_sha256_by_episode: Mapping[str, str],
    sealed_opening_artifact_path: Path,
    expected_sealed_opening_artifact_sha256: str,
    frozen_manifest_artifact_path: Path,
    producer_run_artifact_path: Path,
    gate_a_report_artifact_path: Path,
    trusted_prerequisite_verifier: TrustedExecutionPrerequisiteVerifierV09,
    trusted_prerequisite_verifier_identity: Ed25519AttestationVerifier,
    expected_prerequisite_verifier_implementation_sha256: str,
    isolation_working_directories_by_task: Mapping[tuple[str, str], Path],
    trusted_isolated_receipt_verifier: Ed25519AttestationVerifier,
    isolation_receipt_verifier: TrustedIsolationReceiptVerifierV09,
    trusted_enrolled_executor: Ed25519AttestationVerifier,
) -> CanonicalPerEpisodeExecutionArtifactV09:
    """Reverify custody, live artifacts, exact coverage, and every task receipt."""

    episode_ids = tuple(expected_episode_ids)
    _validate_execution_request(expected_execution_id, episode_ids)
    unsigned_payload = dict(payload)
    stored = unsigned_payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned_payload) != stored:
        raise ValueError("canonical execution aggregate content hash mismatch")
    artifact = CanonicalPerEpisodeExecutionArtifactV09.model_validate(unsigned_payload)
    if artifact.execution_id != expected_execution_id or artifact.episode_ids != episode_ids:
        raise ValueError("canonical execution aggregate changed frozen execution/episode scope")
    if (
        artifact.executor_key_id != trusted_enrolled_executor.key_id
        or artifact.executor_public_key_base64 != trusted_enrolled_executor.public_key_base64
        or artifact.executor_public_key_sha256 != trusted_enrolled_executor.public_key_sha256
    ):
        raise AttestationError("canonical aggregate is outside the enrolled executor key")
    if (
        trusted_enrolled_executor.public_key_sha256
        == trusted_isolated_receipt_verifier.public_key_sha256
    ):
        raise AttestationError(
            "isolated runner and aggregate executor enrollments are not distinct"
        )
    trusted_enrolled_executor.verify(
        AGGREGATE_ATTESTATION_DOMAIN,
        attested_payload(artifact),
        artifact.attestation,
    )

    context = _prepare_context(
        episode_ids=episode_ids,
        bundle_paths_by_arm=bundle_paths_by_arm,
        expected_bundle_sha256_by_arm=expected_bundle_sha256_by_arm,
        expected_bundle_manifest_content_sha256_by_arm=(
            expected_bundle_manifest_content_sha256_by_arm
        ),
        visible_input_paths_by_episode=visible_input_paths_by_episode,
        expected_visible_input_sha256_by_episode=expected_visible_input_sha256_by_episode,
        sealed_opening_artifact_path=sealed_opening_artifact_path,
        expected_sealed_opening_artifact_sha256=(expected_sealed_opening_artifact_sha256),
    )
    prerequisites = _prepare_verified_prerequisites(
        verifier=trusted_prerequisite_verifier,
        trusted_verifier_identity=trusted_prerequisite_verifier_identity,
        expected_verifier_implementation_sha256=(
            expected_prerequisite_verifier_implementation_sha256
        ),
        execution_id=expected_execution_id,
        episode_ids=episode_ids,
        expected_bundle_sha256_by_arm=expected_bundle_sha256_by_arm,
        visible_input_paths_by_episode={
            item.binding.episode_id: item.input_path for item in context.inputs
        },
        expected_visible_input_artifact_sha256_by_episode={
            item.binding.episode_id: item.binding.input_artifact_sha256 for item in context.inputs
        },
        expected_visible_episode_content_sha256_by_episode={
            item.binding.episode_id: item.binding.visible_episode_content_sha256
            for item in context.inputs
        },
        frozen_manifest_artifact_path=frozen_manifest_artifact_path,
        producer_run_artifact_path=producer_run_artifact_path,
        gate_a_report_artifact_path=gate_a_report_artifact_path,
        sealed_opening_artifact_path=sealed_opening_artifact_path,
    )
    if artifact.verified_prerequisites != prerequisites:
        raise ValueError("aggregate prerequisite evidence differs from semantic re-verification")
    if tuple(item.binding for item in context.bundles) != artifact.arm_bundle_bindings:
        raise ValueError("canonical aggregate bundle binding differs from live frozen bundles")
    if tuple(item.binding for item in context.inputs) != artifact.episode_input_bindings:
        raise ValueError("canonical aggregate input binding differs from live visible inputs")
    if context.opening_binding != artifact.sealed_opening_binding:
        raise ValueError("canonical aggregate opening binding differs from live sealed opening")
    if prerequisites.sealed_opening_artifact_sha256 != context.opening_binding.artifact_sha256:
        raise ValueError("semantic sealed-opening verification and live opening bytes disagree")
    isolation_working_directories = _prepare_isolation_working_directories(
        paths_by_task=isolation_working_directories_by_task,
        episode_ids=episode_ids,
        require_empty=False,
    )

    task_index = 0
    for bundle in context.bundles:
        for episode in context.inputs:
            expected_task = _make_task(
                execution_id=expected_execution_id,
                task_index=task_index,
                bundle=bundle.binding,
                episode=episode.binding,
                opening=context.opening_binding,
                prerequisites=prerequisites,
            )
            bound = artifact.task_receipts[task_index]
            _verify_bound_receipt(
                bound,
                expected_task=expected_task,
                trusted_runner=trusted_isolated_receipt_verifier,
                require_success=True,
            )
            _verify_isolation_evidence(
                bound,
                expected_task=expected_task,
                bundle_path=bundle.bundle_path,
                entrypoint_path=bundle.entrypoint_path,
                visible_input_path=episode.input_path,
                isolation_working_directory=isolation_working_directories[
                    (bundle.binding.arm, episode.binding.episode_id)
                ],
                trusted_runner=trusted_isolated_receipt_verifier,
                verifier=isolation_receipt_verifier,
            )
            task_index += 1
    if task_index != len(artifact.task_receipts):
        raise ValueError("canonical execution aggregate contains extra task receipts")
    return artifact


__all__ = [
    "AGGREGATE_ATTESTATION_DOMAIN",
    "BUNDLE_MANIFEST_FILENAME",
    "BUNDLE_MANIFEST_PROTOCOL_ID",
    "BUNDLE_MANIFEST_SIDECAR_SUFFIX",
    "CLAIM_BOUNDARY",
    "ENTRYPOINT_INTERFACE",
    "EXECUTION_MODE",
    "EXPECTED_ARMS",
    "ISOLATION_PROFILE",
    "PREREQUISITE_ATTESTATION_DOMAIN",
    "PREREQUISITE_VERIFICATION_PROTOCOL_ID",
    "PREREQUISITE_VERIFIER_PROTOCOL_ID",
    "PROTOCOL_ID",
    "RECEIPT_ATTESTATION_DOMAIN",
    "RECEIPT_PROTOCOL_ID",
    "TASK_PROTOCOL_ID",
    "VISIBLE_INPUT_PROTOCOL_ID",
    "ArmBundleBindingV09",
    "ArmBundleManifestV09",
    "BoundEpisodeExecutionReceiptV09",
    "CanonicalEpisodeTaskV09",
    "CanonicalPerEpisodeExecutionArtifactV09",
    "EpisodeInputBindingV09",
    "IsolatedEpisodeExecutionReceiptV09",
    "IsolatedTaskRunArtifactsV09",
    "MacOSIsolatedEpisodeRunnerV09",
    "MechanismStepRecordV09",
    "RecomputedSealedVisibleInputsV09",
    "SealedOpeningBindingV09",
    "TrustedExecutionPrerequisiteVerifierV09",
    "TrustedIsolatedEpisodeRunnerV09",
    "TrustedIsolationReceiptVerifierV09",
    "VerifiedExecutionPrerequisitesV09",
    "VisibleEpisodeInputV09",
    "artifact_content_sha256_v0_9",
    "initial_mechanism_state_sha256_v0_9",
    "make_isolated_episode_execution_receipt_v0_9",
    "recompute_sealed_visible_episode_inputs_v0_9",
    "run_canonical_per_episode_executor_v0_9",
    "sign_verified_execution_prerequisites_v0_9",
    "verify_canonical_per_episode_execution_artifact_v0_9",
    "verify_isolated_episode_execution_receipt_v0_9",
]
