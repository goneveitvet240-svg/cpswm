from __future__ import annotations

import copy
import hashlib
import json
import platform
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.attestation import (
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
)
from cpswm.system.evaluation_operations import (
    structure_two_canonical_episode_executor_v0_9 as canonical_executor,
)
from cpswm.system.evaluation_operations import structure_two_isolation_v0_9 as isolation
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.structure_two_canonical_episode_executor_v0_9 import (
    AGGREGATE_ATTESTATION_DOMAIN,
    BUNDLE_MANIFEST_FILENAME,
    BUNDLE_MANIFEST_PROTOCOL_ID,
    BUNDLE_MANIFEST_SIDECAR_SUFFIX,
    ENTRYPOINT_INTERFACE,
    EXPECTED_ARMS,
    ISOLATION_OUTPUT_LABEL,
    ISOLATION_OUTPUT_RELATIVE_PATH,
    ISOLATION_TIMEOUT_SECONDS,
    PREREQUISITE_VERIFICATION_PROTOCOL_ID,
    PREREQUISITE_VERIFIER_PROTOCOL_ID,
    VISIBLE_INPUT_PROTOCOL_ID,
    CanonicalEpisodeTaskV09,
    CanonicalPerEpisodeExecutionArtifactV09,
    IsolatedTaskRunArtifactsV09,
    MacOSIsolatedEpisodeRunnerV09,
    MechanismStepRecordV09,
    RecomputedSealedVisibleInputsV09,
    VerifiedExecutionPrerequisitesV09,
    artifact_content_sha256_v0_9,
    initial_mechanism_state_sha256_v0_9,
    make_isolated_candidate_output_v0_9,
    make_isolated_episode_execution_receipt_v0_9,
    recompute_sealed_visible_episode_inputs_v0_9,
    run_canonical_per_episode_executor_v0_9,
    sign_verified_execution_prerequisites_v0_9,
    verify_canonical_per_episode_execution_artifact_v0_9,
)
from cpswm.system.reproducibility import canonical_json, content_sha256


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def _write_bundle(tmp_path: Path, arm: str, index: int) -> tuple[Path, str, str]:
    bundle = tmp_path / f"bundle-{index}"
    bundle.mkdir()
    entrypoint = bundle / "run.py"
    entrypoint.write_text(f"# frozen implementation for {arm}\n", encoding="utf-8")
    manifest_path = bundle / BUNDLE_MANIFEST_FILENAME
    command_engine = Path(sys.executable).resolve(strict=True)
    manifest = {
        "protocol": BUNDLE_MANIFEST_PROTOCOL_ID,
        "arm": arm,
        "bundle_kind": "directory",
        "entrypoint": "run.py",
        "entrypoint_interface": ENTRYPOINT_INTERFACE,
        "entrypoint_sha256": artifact_content_sha256_v0_9(entrypoint),
        "command_engine_path": str(command_engine),
        "command_engine_sha256": artifact_content_sha256_v0_9(command_engine),
    }
    manifest_hash = content_sha256(manifest)
    _write_json(manifest_path, {**manifest, "content_sha256": manifest_hash})
    return bundle, artifact_content_sha256_v0_9(bundle), manifest_hash


def _isolation_binding(label: str, path: Path) -> isolation.IsolationArtifactBindingV09:
    resolved = path.resolve(strict=True)
    if resolved.is_file():
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        kind = "file"
    else:
        rows = tuple(
            (
                item.relative_to(resolved).as_posix(),
                hashlib.sha256(item.read_bytes()).hexdigest(),
            )
            for item in sorted(resolved.rglob("*"))
            if item.is_file()
        )
        digest = content_sha256({"files": rows})
        kind = "directory"
    return isolation.IsolationArtifactBindingV09(
        label=label,
        resolved_path=str(resolved),
        artifact_kind=kind,
        content_sha256=digest,
    )


def _make_formal_isolation_receipt(
    *,
    task: CanonicalEpisodeTaskV09,
    bundle_path: Path,
    visible_input_path: Path,
    working_directory: Path,
    arguments: tuple[str, ...],
    signer: Ed25519AttestationSigner,
) -> dict[str, Any]:
    output_path = working_directory / ISOLATION_OUTPUT_RELATIVE_PATH
    started = datetime(2026, 9, 4, 8, 0, task.task_index, tzinfo=UTC)
    verifier = signer.verifier()
    probe = isolation.IsolationProbeResultsV09(
        network_access_denied=True,
        code_write_denied=True,
        input_write_denied=True,
        outside_workdir_write_denied=True,
        working_directory_write_allowed=True,
        hidden_file_read_denied=True,
        process_fork_denied=True,
        stdin_is_devnull=True,
        unlisted_process_exec_denied=True,
        environment_allowlist_exact=True,
        network_errno=1,
        code_write_errno=1,
        input_write_errno=1,
        outside_write_errno=1,
        hidden_read_errno=1,
        fork_errno=1,
        exec_errno=1,
        hidden_probe_path="/private/cpswm-hidden-probe",
        hidden_probe_content_sha256="0" * 64,
        exec_probe_target_path="/bin/echo",
        exec_probe_target_binary_sha256="9" * 64,
        observed_environment_names=("PATH",),
        unexpected_environment_names=(),
        missing_environment_names=(),
        probe_exit_code=0,
        probe_stdout_sha256="1" * 64,
        probe_stderr_sha256="2" * 64,
        exec_probe_exit_code=0,
        exec_probe_stdout_sha256="a" * 64,
        exec_probe_stderr_sha256="b" * 64,
        all_probes_passed=True,
    )
    command_engine = Path(task.command_engine_path).resolve(strict=True)
    unsigned = isolation.IsolationExecutionReceiptV09(
        protocol=isolation.PROTOCOL_ID,
        backend="macos_sandbox_exec",
        status="ISOLATION_PASSED",
        policy_id=isolation.MACOS_POLICY_ID,
        policy_template_sha256=isolation.MACOS_POLICY_TEMPLATE_SHA256,
        rendered_profile_sha256="3" * 64,
        profile_unchanged_during_execution=True,
        read_isolation_mode="deny-all-file-data-then-allow-fixed-runtime-code-input-work",
        fixed_runtime_read_allowlist=(
            str(command_engine),
            str(bundle_path),
            str(visible_input_path),
        ),
        sandbox_engine_path="/usr/bin/sandbox-exec",
        sandbox_engine_binary_sha256="4" * 64,
        command_engine_path=str(command_engine),
        command_engine_binary_sha256=hashlib.sha256(command_engine.read_bytes()).hexdigest(),
        probe_engine_path="/usr/bin/python3",
        probe_engine_binary_sha256="5" * 64,
        argv=(str(command_engine), *arguments),
        stdin_mode="DEVNULL",
        close_fds=True,
        pass_fds=(),
        working_directory=str(working_directory.resolve(strict=True)),
        clean_environment_sha256="6" * 64,
        resource_limits=isolation.DEFAULT_RESOURCE_LIMITS,
        timeout_seconds=ISOLATION_TIMEOUT_SECONDS,
        code_bundle=_isolation_binding("code_bundle", bundle_path),
        input_artifacts=(_isolation_binding("visible_episode_input", visible_input_path),),
        expected_output_relative_paths={ISOLATION_OUTPUT_LABEL: ISOLATION_OUTPUT_RELATIVE_PATH},
        output_artifacts=(_isolation_binding(ISOLATION_OUTPUT_LABEL, output_path),),
        code_bundle_unchanged=True,
        input_artifacts_unchanged=True,
        engine_binaries_unchanged=True,
        probe_results=probe,
        command_executed=True,
        exit_code=0,
        timed_out=False,
        stdout_sha256="7" * 64,
        stderr_sha256="8" * 64,
        started_at_utc=started,
        finished_at_utc=started + timedelta(seconds=1),
        host_system="Darwin",
        host_release=platform.release(),
        host_machine=platform.machine(),
        formal_isolation_verified=True,
        executor_key_id=verifier.key_id,
        executor_public_key_base64=verifier.public_key_base64,
        executor_public_key_sha256=verifier.public_key_sha256,
        claim_boundary="test contract receipt; no claim of a live sandbox process",
    )
    signed = unsigned.model_copy(
        update={
            "executor_attestation": signer.sign(
                isolation.ATTESTATION_DOMAIN,
                unsigned.model_dump(mode="json", exclude={"executor_attestation"}),
            )
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


class _StrictIsolationReceiptVerifier:
    """Test double for the stable verifier API, not evidence of a live sandbox."""

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
        resource_limits: isolation.IsolationResourceLimitsV09 = isolation.DEFAULT_RESOURCE_LIMITS,
    ) -> isolation.IsolationExecutionReceiptV09:
        raw = dict(payload)
        stored = raw.pop("content_sha256")
        assert stored == content_sha256(raw)
        record = isolation.IsolationExecutionReceiptV09.model_validate(raw)
        assert record.executor_key_id == trusted_executor.key_id
        assert record.executor_public_key_base64 == trusted_executor.public_key_base64
        assert record.executor_public_key_sha256 == trusted_executor.public_key_sha256
        trusted_executor.verify(
            isolation.ATTESTATION_DOMAIN,
            record.model_dump(mode="json", exclude={"executor_attestation"}),
            record.executor_attestation,
        )
        assert record.formal_isolation_verified is True
        assert record.status == "ISOLATION_PASSED"
        assert record.command_engine_path == str(command_engine_path.resolve(strict=True))
        assert record.argv == (record.command_engine_path, *arguments)
        expected_code = _isolation_binding("code_bundle", code_bundle_path)
        expected_inputs = tuple(
            _isolation_binding(label, input_artifact_paths[label])
            for label in sorted(input_artifact_paths)
        )
        if record.code_bundle != expected_code or record.input_artifacts != expected_inputs:
            raise ValueError("isolation execution bindings changed")
        assert record.working_directory == str(working_directory.resolve(strict=True))
        assert record.expected_output_relative_paths == {
            label: Path(relative).as_posix()
            for label, relative in expected_output_relative_paths.items()
        }
        expected_outputs = tuple(
            _isolation_binding(label, working_directory / relative)
            for label, relative in sorted(expected_output_relative_paths.items())
        )
        if record.output_artifacts != expected_outputs:
            raise ValueError("isolation output binding changed")
        assert record.timeout_seconds == timeout_seconds
        assert record.resource_limits == resource_limits
        return record


def _verified_test_artifact(path: Path) -> tuple[dict[str, Any], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    stored = payload.pop("content_sha256")
    assert stored == content_sha256(payload)
    return payload, stored


class _StrictPrerequisiteVerifier:
    """Signed test adapter; not evidence of an external gate ceremony."""

    def __init__(
        self,
        signer: Ed25519AttestationSigner,
        *,
        echo_caller_visible_inputs: bool = False,
    ) -> None:
        self.signer = signer
        self.echo_caller_visible_inputs = echo_caller_visible_inputs

    @property
    def implementation_sha256(self) -> str:
        return content_sha256(
            {
                "implementation": "strict-test-sealed-holdout-prerequisite-verifier",
                "protocol": PREREQUISITE_VERIFIER_PROTOCOL_ID,
            }
        )

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
    ) -> VerifiedExecutionPrerequisitesV09:
        manifest, manifest_hash = _verified_test_artifact(frozen_manifest_artifact_path)
        run, run_hash = _verified_test_artifact(producer_run_artifact_path)
        gate_a, gate_a_hash = _verified_test_artifact(gate_a_report_artifact_path)
        opening, opening_hash = _verified_test_artifact(sealed_opening_artifact_path)
        assert manifest["status"] == "EXTERNALLY_FROZEN"
        assert manifest["arm_implementation_bundle_sha256"] == dict(expected_bundle_sha256_by_arm)
        assert run["status"] == "PREREGISTERED_RUN_COMPLETED"
        assert run["exit_code"] == 0
        assert run["producer_run_id"] == manifest["producer_run_id"]
        assert gate_a["gate_a_passed"] is True
        assert gate_a["producer_run_id"] == run["producer_run_id"]
        assert opening["status"] == "OPENED_ONCE_AFTER_PASSED_GATE_A"
        assert opening["gate_a_report_content_sha256"] == gate_a_hash
        assert tuple(visible_input_paths_by_episode) == expected_episode_ids
        if not self.echo_caller_visible_inputs:
            assert opening["visible_input_artifact_sha256_by_episode"] == dict(
                expected_visible_input_artifact_sha256_by_episode
            )
            assert opening["visible_episode_content_sha256_by_episode"] == dict(
                expected_visible_episode_content_sha256_by_episode
            )
        verifier = self.signer.verifier()
        unsigned = VerifiedExecutionPrerequisitesV09(
            protocol=PREREQUISITE_VERIFICATION_PROTOCOL_ID,
            execution_id=execution_id,
            episode_ids=expected_episode_ids,
            immutable_manifest_sha256=manifest["immutable_manifest_sha256"],
            producer_run_id=run["producer_run_id"],
            opening_attempt_id=opening["opening_attempt_id"],
            arm_implementation_bundle_sha256=dict(expected_bundle_sha256_by_arm),
            sealed_holdout_visible_input_artifact_sha256_by_episode=dict(
                expected_visible_input_artifact_sha256_by_episode
                if self.echo_caller_visible_inputs
                else opening["visible_input_artifact_sha256_by_episode"]
            ),
            sealed_holdout_visible_episode_content_sha256_by_episode=dict(
                expected_visible_episode_content_sha256_by_episode
                if self.echo_caller_visible_inputs
                else opening["visible_episode_content_sha256_by_episode"]
            ),
            frozen_manifest_artifact_sha256=artifact_content_sha256_v0_9(
                frozen_manifest_artifact_path
            ),
            producer_run_artifact_sha256=artifact_content_sha256_v0_9(producer_run_artifact_path),
            gate_a_report_artifact_sha256=artifact_content_sha256_v0_9(gate_a_report_artifact_path),
            sealed_opening_artifact_sha256=artifact_content_sha256_v0_9(
                sealed_opening_artifact_path
            ),
            frozen_manifest_content_sha256=manifest_hash,
            producer_run_content_sha256=run_hash,
            gate_a_report_content_sha256=gate_a_hash,
            sealed_opening_content_sha256=opening_hash,
            frozen_manifest_semantically_verified=True,
            producer_run_semantically_verified=True,
            gate_a_semantically_verified=True,
            gate_a_passed=True,
            sealed_opening_semantically_verified=True,
            prerequisite_verifier_protocol=PREREQUISITE_VERIFIER_PROTOCOL_ID,
            prerequisite_verifier_implementation_sha256=self.implementation_sha256,
            prerequisite_verifier_key_id=verifier.key_id,
            prerequisite_verifier_public_key_base64=verifier.public_key_base64,
            prerequisite_verifier_public_key_sha256=verifier.public_key_sha256,
        )
        return sign_verified_execution_prerequisites_v0_9(
            unsigned,
            verifier_signer=self.signer,
        )


class _SigningIsolatedRunner:
    def __init__(
        self,
        signer: Ed25519AttestationSigner,
        *,
        replay_first_receipt: bool = False,
        fail: bool = False,
        partial: bool = False,
        mutate: str | None = None,
        forged_isolation_hash: bool = False,
    ) -> None:
        self.signer = signer
        self.replay_first_receipt = replay_first_receipt
        self.fail = fail
        self.partial = partial
        self.mutate = mutate
        self.forged_isolation_hash = forged_isolation_hash
        self.calls: list[tuple[str, str]] = []
        self.receipts: list[IsolatedTaskRunArtifactsV09] = []
        self.outputs: list[dict[str, Any]] = []

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
        self.calls.append((task.arm, task.episode_id))
        if self.replay_first_receipt and self.receipts:
            _write_json(
                isolation_working_directory / ISOLATION_OUTPUT_RELATIVE_PATH,
                copy.deepcopy(self.outputs[0]),
            )
            return copy.deepcopy(self.receipts[0])

        step_count = task.expected_step_count - 1 if self.partial else task.expected_step_count
        state = initial_mechanism_state_sha256_v0_9(task)
        actions: list[str] = []
        steps: list[MechanismStepRecordV09] = []
        for step_index in range(step_count):
            action = f"{task.arm}:action:{step_index}"
            output_state = content_sha256(
                {
                    "task": task.content_sha256,
                    "step": step_index,
                    "input_state": state,
                    "action": action,
                }
            )
            actions.append(action)
            steps.append(
                MechanismStepRecordV09(
                    step_index=step_index,
                    action=action,
                    mechanism_events=(f"{task.arm}:mechanism-event",),
                    input_state_sha256=state,
                    output_state_sha256=output_state,
                )
            )
            state = output_state
        candidate_output = make_isolated_candidate_output_v0_9(
            task=task,
            action_sequence=actions,
            mechanism_steps=steps,
        )
        output_path = isolation_working_directory / ISOLATION_OUTPUT_RELATIVE_PATH
        _write_json(output_path, candidate_output)
        isolation_receipt = _make_formal_isolation_receipt(
            task=task,
            bundle_path=bundle_path,
            visible_input_path=visible_input_path,
            working_directory=isolation_working_directory,
            arguments=isolation_arguments,
            signer=self.signer,
        )
        receipt = make_isolated_episode_execution_receipt_v0_9(
            task=task,
            action_sequence=actions,
            mechanism_steps=steps,
            exit_status="failed" if self.fail else "succeeded",
            exit_code=17 if self.fail else 0,
            isolation_receipt_content_sha256=(
                "f" * 64 if self.forged_isolation_hash else isolation_receipt["content_sha256"]
            ),
            isolated_output_artifact_sha256=artifact_content_sha256_v0_9(output_path),
            isolated_output_content_sha256=candidate_output["content_sha256"],
            signer=self.signer,
        )
        artifacts = IsolatedTaskRunArtifactsV09(
            episode_execution_receipt=receipt,
            isolation_execution_receipt=isolation_receipt,
        )
        self.receipts.append(copy.deepcopy(artifacts))
        self.outputs.append(copy.deepcopy(candidate_output))
        if len(self.calls) == 1 and self.mutate == "content":
            entrypoint_path.write_text("# changed after execution\n", encoding="utf-8")
        if len(self.calls) == 1 and self.mutate == "mode":
            entrypoint_path.chmod(entrypoint_path.stat().st_mode ^ 0o100)
        if len(self.calls) == 1 and self.mutate == "input":
            visible_input_path.write_text("{}", encoding="utf-8")
        if len(self.calls) == 1 and self.mutate == "bundle-side-file":
            (bundle_path / "late.py").write_text("# late file\n", encoding="utf-8")
        return artifacts


@dataclass(frozen=True)
class _Harness:
    execution_id: str
    episode_ids: tuple[str, ...]
    bundle_paths: dict[str, Path]
    bundle_hashes: dict[str, str]
    manifest_hashes: dict[str, str]
    input_paths: dict[str, Path]
    input_hashes: dict[str, str]
    opening_path: Path
    opening_hash: str
    frozen_manifest_path: Path
    producer_run_path: Path
    gate_a_report_path: Path
    working_directories: dict[tuple[str, str], Path]
    prerequisite_verifier: _StrictPrerequisiteVerifier
    isolation_verifier: _StrictIsolationReceiptVerifier
    runner_signer: Ed25519AttestationSigner
    executor_signer: Ed25519AttestationSigner

    def run(
        self,
        runner: _SigningIsolatedRunner | None = None,
        *,
        prerequisite_verifier: _StrictPrerequisiteVerifier | None = None,
        trusted_prerequisite_signer: Ed25519AttestationSigner | None = None,
        expected_prerequisite_implementation_sha256: str | None = None,
        expected_visible_input_hashes: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        selected_runner = runner or _SigningIsolatedRunner(self.runner_signer)
        selected_prerequisite_verifier = prerequisite_verifier or self.prerequisite_verifier
        selected_trusted_signer = trusted_prerequisite_signer or self.prerequisite_verifier.signer
        return run_canonical_per_episode_executor_v0_9(
            execution_id=self.execution_id,
            expected_episode_ids=self.episode_ids,
            bundle_paths_by_arm=self.bundle_paths,
            expected_bundle_sha256_by_arm=self.bundle_hashes,
            expected_bundle_manifest_content_sha256_by_arm=self.manifest_hashes,
            visible_input_paths_by_episode=self.input_paths,
            expected_visible_input_sha256_by_episode=(
                expected_visible_input_hashes or self.input_hashes
            ),
            sealed_opening_artifact_path=self.opening_path,
            expected_sealed_opening_artifact_sha256=self.opening_hash,
            frozen_manifest_artifact_path=self.frozen_manifest_path,
            producer_run_artifact_path=self.producer_run_path,
            gate_a_report_artifact_path=self.gate_a_report_path,
            trusted_prerequisite_verifier=selected_prerequisite_verifier,
            trusted_prerequisite_verifier_identity=(selected_trusted_signer.verifier()),
            expected_prerequisite_verifier_implementation_sha256=(
                expected_prerequisite_implementation_sha256
                or self.prerequisite_verifier.implementation_sha256
            ),
            isolation_working_directories_by_task=self.working_directories,
            trusted_isolated_runner=selected_runner,
            trusted_isolated_receipt_verifier=self.runner_signer.verifier(),
            isolation_receipt_verifier=self.isolation_verifier,
            enrolled_executor_signer=self.executor_signer,
        )

    def verify(self, payload: dict[str, Any]) -> CanonicalPerEpisodeExecutionArtifactV09:
        return verify_canonical_per_episode_execution_artifact_v0_9(
            payload,
            expected_execution_id=self.execution_id,
            expected_episode_ids=self.episode_ids,
            bundle_paths_by_arm=self.bundle_paths,
            expected_bundle_sha256_by_arm=self.bundle_hashes,
            expected_bundle_manifest_content_sha256_by_arm=self.manifest_hashes,
            visible_input_paths_by_episode=self.input_paths,
            expected_visible_input_sha256_by_episode=self.input_hashes,
            sealed_opening_artifact_path=self.opening_path,
            expected_sealed_opening_artifact_sha256=self.opening_hash,
            frozen_manifest_artifact_path=self.frozen_manifest_path,
            producer_run_artifact_path=self.producer_run_path,
            gate_a_report_artifact_path=self.gate_a_report_path,
            trusted_prerequisite_verifier=self.prerequisite_verifier,
            trusted_prerequisite_verifier_identity=(self.prerequisite_verifier.signer.verifier()),
            expected_prerequisite_verifier_implementation_sha256=(
                self.prerequisite_verifier.implementation_sha256
            ),
            isolation_working_directories_by_task=self.working_directories,
            trusted_isolated_receipt_verifier=self.runner_signer.verifier(),
            isolation_receipt_verifier=self.isolation_verifier,
            trusted_enrolled_executor=self.executor_signer.verifier(),
        )


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Harness:
    bundle_rows = tuple(
        _write_bundle(tmp_path, arm, index) for index, arm in enumerate(EXPECTED_ARMS)
    )
    dataset = D0SyntheticOracleReplayAdapter(
        validation_seeds=(101,),
        test_seeds=(211,),
        max_steps_per_episode=2,
    ).build()
    episodes = dataset.episodes[:2]
    input_paths: dict[str, Path] = {}
    input_hashes: dict[str, str] = {}
    episode_content_hashes: dict[str, str] = {}
    for index, episode in enumerate(episodes):
        episode_id = str(episode.episode_id)
        input_path = tmp_path / f"visible-{index}.json"
        _write_json(
            input_path,
            {
                "protocol": VISIBLE_INPUT_PROTOCOL_ID,
                "episode": episode.model_dump(mode="json"),
            },
        )
        input_paths[episode_id] = input_path
        input_hashes[episode_id] = artifact_content_sha256_v0_9(input_path)
        episode_content_hashes[episode_id] = content_sha256(episode)
    bundle_hashes = {arm: row[1] for arm, row in zip(EXPECTED_ARMS, bundle_rows, strict=True)}
    frozen_manifest_path = tmp_path / "frozen-manifest.json"
    frozen_manifest = {
        "status": "EXTERNALLY_FROZEN",
        "immutable_manifest_sha256": content_sha256("immutable-test-manifest"),
        "producer_run_id": "producer-run-0001",
        "arm_implementation_bundle_sha256": bundle_hashes,
    }
    _write_json(
        frozen_manifest_path,
        {**frozen_manifest, "content_sha256": content_sha256(frozen_manifest)},
    )
    producer_run_path = tmp_path / "producer-run.json"
    producer_run = {
        "status": "PREREGISTERED_RUN_COMPLETED",
        "producer_run_id": "producer-run-0001",
        "exit_code": 0,
    }
    _write_json(producer_run_path, {**producer_run, "content_sha256": content_sha256(producer_run)})
    gate_a_report_path = tmp_path / "gate-a-report.json"
    gate_a = {"gate_a_passed": True, "producer_run_id": "producer-run-0001"}
    gate_a_hash = content_sha256(gate_a)
    _write_json(gate_a_report_path, {**gate_a, "content_sha256": gate_a_hash})
    opening_path = tmp_path / "sealed-opening.json"
    opening = {
        "status": "OPENED_ONCE_AFTER_PASSED_GATE_A",
        "opening_attempt_id": "opening-attempt-0001",
        "gate_a_report_content_sha256": gate_a_hash,
        "visible_input_artifact_sha256_by_episode": input_hashes,
        "visible_episode_content_sha256_by_episode": episode_content_hashes,
    }
    _write_json(opening_path, {**opening, "content_sha256": content_sha256(opening)})
    sealed_visible_bytes = {
        episode_id: path.read_bytes() for episode_id, path in input_paths.items()
    }
    monkeypatch.setattr(
        canonical_executor,
        "_recompute_sealed_visible_inputs_from_path",
        lambda _path: RecomputedSealedVisibleInputsV09(
            episodes=tuple(episodes),
            canonical_bytes_by_episode=dict(sealed_visible_bytes),
            artifact_sha256_by_episode=dict(input_hashes),
            episode_content_sha256_by_episode=dict(episode_content_hashes),
        ),
    )
    working_directories: dict[tuple[str, str], Path] = {}
    for arm in EXPECTED_ARMS:
        for episode_index, episode_id in enumerate(input_paths):
            work = tmp_path / f"work-{EXPECTED_ARMS.index(arm)}-{episode_index}"
            work.mkdir()
            working_directories[(arm, episode_id)] = work
    prerequisite_signer = Ed25519AttestationSigner.generate(
        key_id="sealed-prerequisite-verifier-v0.9"
    )
    return _Harness(
        execution_id="canonical-execution-0001",
        episode_ids=tuple(input_paths),
        bundle_paths={arm: row[0] for arm, row in zip(EXPECTED_ARMS, bundle_rows, strict=True)},
        bundle_hashes=bundle_hashes,
        manifest_hashes={arm: row[2] for arm, row in zip(EXPECTED_ARMS, bundle_rows, strict=True)},
        input_paths=input_paths,
        input_hashes=input_hashes,
        opening_path=opening_path,
        opening_hash=artifact_content_sha256_v0_9(opening_path),
        frozen_manifest_path=frozen_manifest_path,
        producer_run_path=producer_run_path,
        gate_a_report_path=gate_a_report_path,
        working_directories=working_directories,
        prerequisite_verifier=_StrictPrerequisiteVerifier(prerequisite_signer),
        isolation_verifier=_StrictIsolationReceiptVerifier(),
        runner_signer=Ed25519AttestationSigner.generate(key_id="isolated-runner-v0.9"),
        executor_signer=Ed25519AttestationSigner.generate(key_id="aggregate-executor-v0.9"),
    )


def _rehash_aggregate(payload: dict[str, Any]) -> None:
    payload.pop("content_sha256", None)
    payload["content_sha256"] = content_sha256(payload)


def test_runs_exact_ten_arm_episode_product_and_verifies_live_artifacts(
    harness: _Harness,
) -> None:
    runner = _SigningIsolatedRunner(harness.runner_signer)

    payload = harness.run(runner)
    verified = harness.verify(payload)

    expected_pairs = [
        (arm, episode_id) for arm in EXPECTED_ARMS for episode_id in harness.episode_ids
    ]
    assert runner.calls == expected_pairs
    assert len(verified.task_receipts) == len(EXPECTED_ARMS) * len(harness.episode_ids)
    assert all(
        len(row.receipt.action_sequence) == 2
        and len(row.receipt.mechanism_steps) == 2
        and row.receipt.exit_status == "succeeded"
        for row in verified.task_receipts
    )
    assert verified.action_execution_mode == "frozen-content-addressed-isolated-bundle"
    assert verified.reference_cores_relabelled_as_native is False
    assert verified.fidelity_or_native_reproduction_status == "not_evaluated_by_executor"
    assert {path.is_file() for path in harness.bundle_paths.values()} == {False}


@pytest.mark.parametrize("forbidden_key", ["true_actor", "evaluator_truth", "world_seed"])
def test_rejects_truth_evaluator_and_seed_channels_even_when_hash_is_refrozen(
    harness: _Harness,
    forbidden_key: str,
) -> None:
    episode_id = harness.episode_ids[0]
    path = harness.input_paths[episode_id]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[forbidden_key] = "leaked"
    _write_json(path, payload)
    refrozen_hashes = {**harness.input_hashes, episode_id: artifact_content_sha256_v0_9(path)}

    with pytest.raises(ValueError, match=r"truth leakage|forbidden channel"):
        run_canonical_per_episode_executor_v0_9(
            execution_id=harness.execution_id,
            expected_episode_ids=harness.episode_ids,
            bundle_paths_by_arm=harness.bundle_paths,
            expected_bundle_sha256_by_arm=harness.bundle_hashes,
            expected_bundle_manifest_content_sha256_by_arm=harness.manifest_hashes,
            visible_input_paths_by_episode=harness.input_paths,
            expected_visible_input_sha256_by_episode=refrozen_hashes,
            sealed_opening_artifact_path=harness.opening_path,
            expected_sealed_opening_artifact_sha256=harness.opening_hash,
            frozen_manifest_artifact_path=harness.frozen_manifest_path,
            producer_run_artifact_path=harness.producer_run_path,
            gate_a_report_artifact_path=harness.gate_a_report_path,
            trusted_prerequisite_verifier=harness.prerequisite_verifier,
            trusted_prerequisite_verifier_identity=(
                harness.prerequisite_verifier.signer.verifier()
            ),
            expected_prerequisite_verifier_implementation_sha256=(
                harness.prerequisite_verifier.implementation_sha256
            ),
            isolation_working_directories_by_task=harness.working_directories,
            trusted_isolated_runner=_SigningIsolatedRunner(harness.runner_signer),
            trusted_isolated_receipt_verifier=harness.runner_signer.verifier(),
            isolation_receipt_verifier=harness.isolation_verifier,
            enrolled_executor_signer=harness.executor_signer,
        )


@pytest.mark.parametrize("mutation", ["content", "mode", "input", "bundle-side-file"])
def test_detects_content_mode_input_and_directory_toctou(
    harness: _Harness,
    mutation: str,
) -> None:
    runner = _SigningIsolatedRunner(harness.runner_signer, mutate=mutation)

    with pytest.raises(ValueError, match=r"frozen mapping|TOCTOU|changed|content hash"):
        harness.run(runner)


@pytest.mark.parametrize("failure_kind", ["failed-exit", "partial-success"])
def test_refuses_failed_or_partial_task_aggregate(
    harness: _Harness,
    failure_kind: str,
) -> None:
    runner = _SigningIsolatedRunner(
        harness.runner_signer,
        fail=failure_kind == "failed-exit",
        partial=failure_kind == "partial-success",
    )

    with pytest.raises(ValueError, match=r"partial|failed|coverage"):
        harness.run(runner)


def test_rejects_cross_episode_replay_from_the_enrolled_runner(harness: _Harness) -> None:
    runner = _SigningIsolatedRunner(harness.runner_signer, replay_first_receipt=True)

    with pytest.raises(ValueError, match="task binding"):
        harness.run(runner)


def test_enrolled_runner_cannot_substitute_arbitrary_isolation_receipt_hash(
    harness: _Harness,
) -> None:
    runner = _SigningIsolatedRunner(
        harness.runner_signer,
        forged_isolation_hash=True,
    )

    with pytest.raises(ValueError, match="bind its isolation"):
        harness.run(runner)


@pytest.mark.parametrize("coverage_attack", ["missing", "extra", "duplicate", "reordered"])
def test_aggregate_rejects_missing_extra_duplicate_and_reordered_receipts(
    harness: _Harness,
    coverage_attack: str,
) -> None:
    payload = harness.run()
    receipts = payload["task_receipts"]
    if coverage_attack == "missing":
        receipts.pop()
    elif coverage_attack == "extra":
        receipts.append(copy.deepcopy(receipts[0]))
    elif coverage_attack == "duplicate":
        receipts[1] = copy.deepcopy(receipts[0])
    else:
        receipts[0], receipts[1] = receipts[1], receipts[0]
    _rehash_aggregate(payload)

    with pytest.raises(ValidationError, match=r"coverage|order|indexes"):
        harness.verify(payload)


def test_changing_only_claimed_execution_mode_is_rejected(harness: _Harness) -> None:
    payload = harness.run()
    payload["action_execution_mode"] = "fidelity_validated_implementation"
    _rehash_aggregate(payload)

    with pytest.raises(ValidationError, match="action_execution_mode"):
        harness.verify(payload)


def test_post_run_bundle_change_invalidates_aggregate_against_live_files(
    harness: _Harness,
) -> None:
    payload = harness.run()
    directory_bundle = harness.bundle_paths[EXPECTED_ARMS[0]]
    (directory_bundle / "run.py").write_text("# post-run replacement\n", encoding="utf-8")

    with pytest.raises(ValueError, match="frozen mapping"):
        harness.verify(payload)


def test_fixed_manifest_rejects_entrypoint_escape_even_if_refrozen(harness: _Harness) -> None:
    arm = EXPECTED_ARMS[0]
    bundle = harness.bundle_paths[arm]
    manifest_path = bundle / BUNDLE_MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("content_sha256")
    manifest["entrypoint"] = "../sealed-opening.json"
    manifest["entrypoint_sha256"] = harness.opening_hash
    manifest_hash = content_sha256(manifest)
    _write_json(manifest_path, {**manifest, "content_sha256": manifest_hash})
    refrozen_bundle_hashes = {
        **harness.bundle_hashes,
        arm: artifact_content_sha256_v0_9(bundle),
    }
    refrozen_manifest_hashes = {**harness.manifest_hashes, arm: manifest_hash}
    frozen_manifest = json.loads(harness.frozen_manifest_path.read_text(encoding="utf-8"))
    frozen_manifest.pop("content_sha256")
    frozen_manifest["arm_implementation_bundle_sha256"] = refrozen_bundle_hashes
    _write_json(
        harness.frozen_manifest_path,
        {**frozen_manifest, "content_sha256": content_sha256(frozen_manifest)},
    )

    with pytest.raises(ValueError, match="contained POSIX path"):
        run_canonical_per_episode_executor_v0_9(
            execution_id=harness.execution_id,
            expected_episode_ids=harness.episode_ids,
            bundle_paths_by_arm=harness.bundle_paths,
            expected_bundle_sha256_by_arm=refrozen_bundle_hashes,
            expected_bundle_manifest_content_sha256_by_arm=refrozen_manifest_hashes,
            visible_input_paths_by_episode=harness.input_paths,
            expected_visible_input_sha256_by_episode=harness.input_hashes,
            sealed_opening_artifact_path=harness.opening_path,
            expected_sealed_opening_artifact_sha256=harness.opening_hash,
            frozen_manifest_artifact_path=harness.frozen_manifest_path,
            producer_run_artifact_path=harness.producer_run_path,
            gate_a_report_artifact_path=harness.gate_a_report_path,
            trusted_prerequisite_verifier=harness.prerequisite_verifier,
            trusted_prerequisite_verifier_identity=(
                harness.prerequisite_verifier.signer.verifier()
            ),
            expected_prerequisite_verifier_implementation_sha256=(
                harness.prerequisite_verifier.implementation_sha256
            ),
            isolation_working_directories_by_task=harness.working_directories,
            trusted_isolated_runner=_SigningIsolatedRunner(harness.runner_signer),
            trusted_isolated_receipt_verifier=harness.runner_signer.verifier(),
            isolation_receipt_verifier=harness.isolation_verifier,
            enrolled_executor_signer=harness.executor_signer,
        )


def test_executor_signature_cannot_replace_isolated_runner_signature(
    harness: _Harness,
) -> None:
    payload = harness.run()
    receipt_wrapper = payload["task_receipts"][0]
    receipt = receipt_wrapper["receipt"]
    replacement = "attacker-selected-action"
    receipt["action_sequence"][0] = replacement
    receipt["mechanism_steps"][0]["action"] = replacement
    receipt_wrapper["receipt_content_sha256"] = content_sha256(receipt)

    aggregate_without_hash = dict(payload)
    aggregate_without_hash.pop("content_sha256", None)
    aggregate_without_hash["attestation"] = None
    unsigned = CanonicalPerEpisodeExecutionArtifactV09.model_validate(aggregate_without_hash)
    aggregate_without_hash["attestation"] = harness.executor_signer.sign(
        AGGREGATE_ATTESTATION_DOMAIN,
        unsigned.model_dump(mode="json", exclude={"attestation"}),
    ).model_dump(mode="json")
    aggregate_without_hash["content_sha256"] = content_sha256(aggregate_without_hash)

    with pytest.raises(ValueError, match=r"signature|attestation|record content"):
        harness.verify(aggregate_without_hash)


def test_missing_arm_path_is_rejected_before_any_task_runs(harness: _Harness) -> None:
    runner = _SigningIsolatedRunner(harness.runner_signer)
    paths = dict(harness.bundle_paths)
    paths.pop(EXPECTED_ARMS[-1])

    with pytest.raises(ValueError, match="exact required coverage"):
        run_canonical_per_episode_executor_v0_9(
            execution_id=harness.execution_id,
            expected_episode_ids=harness.episode_ids,
            bundle_paths_by_arm=paths,
            expected_bundle_sha256_by_arm=harness.bundle_hashes,
            expected_bundle_manifest_content_sha256_by_arm=harness.manifest_hashes,
            visible_input_paths_by_episode=harness.input_paths,
            expected_visible_input_sha256_by_episode=harness.input_hashes,
            sealed_opening_artifact_path=harness.opening_path,
            expected_sealed_opening_artifact_sha256=harness.opening_hash,
            frozen_manifest_artifact_path=harness.frozen_manifest_path,
            producer_run_artifact_path=harness.producer_run_path,
            gate_a_report_artifact_path=harness.gate_a_report_path,
            trusted_prerequisite_verifier=harness.prerequisite_verifier,
            trusted_prerequisite_verifier_identity=(
                harness.prerequisite_verifier.signer.verifier()
            ),
            expected_prerequisite_verifier_implementation_sha256=(
                harness.prerequisite_verifier.implementation_sha256
            ),
            isolation_working_directories_by_task=harness.working_directories,
            trusted_isolated_runner=runner,
            trusted_isolated_receipt_verifier=harness.runner_signer.verifier(),
            isolation_receipt_verifier=harness.isolation_verifier,
            enrolled_executor_signer=harness.executor_signer,
        )
    assert runner.calls == []


def test_rejects_same_id_public_episode_substitution_even_when_callback_echoes_it(
    harness: _Harness,
) -> None:
    episode_id = harness.episode_ids[0]
    path = harness.input_paths[episode_id]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["episode"]["scene_id"] = "attacker-public-scene"
    _write_json(path, payload)
    refrozen_hashes = {
        **harness.input_hashes,
        episode_id: artifact_content_sha256_v0_9(path),
    }
    echoing = _StrictPrerequisiteVerifier(
        harness.prerequisite_verifier.signer,
        echo_caller_visible_inputs=True,
    )

    with pytest.raises(ValueError, match=r"recomputed|sealed Gate-B episodes"):
        harness.run(
            prerequisite_verifier=echoing,
            expected_visible_input_hashes=refrozen_hashes,
        )


def test_rejects_single_file_bundle_even_with_matching_sidecar_and_frozen_hash(
    harness: _Harness,
    tmp_path: Path,
) -> None:
    arm = EXPECTED_ARMS[0]
    bundle = tmp_path / "attacker-file-bundle.py"
    bundle.write_text("# frozen-looking implementation\n", encoding="utf-8")
    command_engine = Path(sys.executable).resolve(strict=True)
    manifest = {
        "protocol": BUNDLE_MANIFEST_PROTOCOL_ID,
        "arm": arm,
        "bundle_kind": "file",
        "entrypoint": bundle.name,
        "entrypoint_interface": ENTRYPOINT_INTERFACE,
        "entrypoint_sha256": artifact_content_sha256_v0_9(bundle),
        "command_engine_path": str(command_engine),
        "command_engine_sha256": artifact_content_sha256_v0_9(command_engine),
    }
    manifest_hash = content_sha256(manifest)
    _write_json(
        bundle.with_name(bundle.name + BUNDLE_MANIFEST_SIDECAR_SUFFIX),
        {**manifest, "content_sha256": manifest_hash},
    )
    paths = {**harness.bundle_paths, arm: bundle}
    hashes = {**harness.bundle_hashes, arm: artifact_content_sha256_v0_9(bundle)}
    manifests = {**harness.manifest_hashes, arm: manifest_hash}

    with pytest.raises(ValueError, match="single-file bundles are forbidden"):
        run_canonical_per_episode_executor_v0_9(
            execution_id=harness.execution_id,
            expected_episode_ids=harness.episode_ids,
            bundle_paths_by_arm=paths,
            expected_bundle_sha256_by_arm=hashes,
            expected_bundle_manifest_content_sha256_by_arm=manifests,
            visible_input_paths_by_episode=harness.input_paths,
            expected_visible_input_sha256_by_episode=harness.input_hashes,
            sealed_opening_artifact_path=harness.opening_path,
            expected_sealed_opening_artifact_sha256=harness.opening_hash,
            frozen_manifest_artifact_path=harness.frozen_manifest_path,
            producer_run_artifact_path=harness.producer_run_path,
            gate_a_report_artifact_path=harness.gate_a_report_path,
            trusted_prerequisite_verifier=harness.prerequisite_verifier,
            trusted_prerequisite_verifier_identity=(
                harness.prerequisite_verifier.signer.verifier()
            ),
            expected_prerequisite_verifier_implementation_sha256=(
                harness.prerequisite_verifier.implementation_sha256
            ),
            isolation_working_directories_by_task=harness.working_directories,
            trusted_isolated_runner=_SigningIsolatedRunner(harness.runner_signer),
            trusted_isolated_receipt_verifier=harness.runner_signer.verifier(),
            isolation_receipt_verifier=harness.isolation_verifier,
            enrolled_executor_signer=harness.executor_signer,
        )


def test_rejects_unenrolled_prerequisite_callback_even_with_valid_schema(
    harness: _Harness,
) -> None:
    attacker = _StrictPrerequisiteVerifier(
        Ed25519AttestationSigner.generate(key_id="attacker-prerequisite-verifier")
    )

    with pytest.raises(
        ValueError,
        match=r"signature|attestation|provenance|record content",
    ):
        harness.run(
            prerequisite_verifier=attacker,
            trusted_prerequisite_signer=harness.prerequisite_verifier.signer,
        )


def test_rejects_substituted_prerequisite_verifier_implementation(
    harness: _Harness,
) -> None:
    class _SubstitutedVerifier(_StrictPrerequisiteVerifier):
        @property
        def implementation_sha256(self) -> str:
            return content_sha256("attacker-substituted-verifier-implementation")

    substituted = _SubstitutedVerifier(harness.prerequisite_verifier.signer)

    with pytest.raises(ValueError, match="implementation identity"):
        harness.run(prerequisite_verifier=substituted)


def test_recomputed_visible_input_uses_sealed_holdout_and_test_split(
    harness: _Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode_payload = json.loads(
        harness.input_paths[harness.episode_ids[0]].read_text(encoding="utf-8")
    )
    episode = canonical_executor.VisibleEpisodeInputV09.model_validate(episode_payload).episode
    opening = object()
    world = object()
    rollout = object()
    seen_splits: list[ProjectTwoDatasetSplit] = []
    monkeypatch.setattr(
        canonical_executor,
        "recompute_sealed_gate_b_holdout_v0_9",
        lambda supplied: (
            SimpleNamespace(world_rollouts=((world, rollout),))
            if supplied is opening
            else pytest.fail("wrong opening")
        ),
    )

    def adapt(supplied_world: object, supplied_rollout: object, *, split: Any) -> Any:
        assert (supplied_world, supplied_rollout) == (world, rollout)
        seen_splits.append(split)
        return SimpleNamespace(episodes=(episode,))

    monkeypatch.setattr(canonical_executor, "adapt_world_rollout", adapt)
    result = recompute_sealed_visible_episode_inputs_v0_9(opening)  # type: ignore[arg-type]

    episode_id = str(episode.episode_id)
    assert seen_splits == [ProjectTwoDatasetSplit.TEST]
    assert result.episode_ids == (episode_id,)
    assert result.canonical_bytes_by_episode[episode_id] == canonical_json(
        canonical_executor.VisibleEpisodeInputV09(
            protocol=VISIBLE_INPUT_PROTOCOL_ID,
            episode=episode,
        )
    ).encode("utf-8")


def test_macos_runner_delegates_to_real_isolation_api_and_signs_per_episode_receipt(
    harness: _Harness,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arm = EXPECTED_ARMS[0]
    episode_id = harness.episode_ids[0]
    bundle = harness.bundle_paths[arm]
    entrypoint = bundle / "run.py"
    visible_input = harness.input_paths[episode_id]
    work = tmp_path / "macos-runner-work"
    work.mkdir()
    task = CanonicalEpisodeTaskV09(
        protocol=canonical_executor.TASK_PROTOCOL_ID,
        execution_id=harness.execution_id,
        task_index=0,
        arm=arm,
        episode_id=episode_id,
        visible_input_artifact_sha256=harness.input_hashes[episode_id],
        visible_input_filesystem_sha256="1" * 64,
        implementation_bundle_sha256=harness.bundle_hashes[arm],
        implementation_bundle_filesystem_sha256="2" * 64,
        bundle_manifest_content_sha256=harness.manifest_hashes[arm],
        entrypoint="run.py",
        entrypoint_content_sha256=artifact_content_sha256_v0_9(entrypoint),
        command_engine_path=str(Path(sys.executable).resolve(strict=True)),
        command_engine_content_sha256=artifact_content_sha256_v0_9(
            Path(sys.executable).resolve(strict=True)
        ),
        sealed_opening_artifact_sha256=harness.opening_hash,
        sealed_opening_filesystem_sha256="3" * 64,
        execution_prerequisites_sha256="4" * 64,
        expected_step_count=1,
        isolation_profile=canonical_executor.ISOLATION_PROFILE,
    )
    output_path = work / ISOLATION_OUTPUT_RELATIVE_PATH
    state = initial_mechanism_state_sha256_v0_9(task)
    step = MechanismStepRecordV09(
        step_index=0,
        action="isolated-action",
        mechanism_events=("isolated-mechanism",),
        input_state_sha256=state,
        output_state_sha256=content_sha256({"state": state}),
    )
    calls: list[str] = []

    def fake_run_macos(**kwargs: Any) -> dict[str, Any]:
        calls.append("run")
        assert kwargs["executor"] is runner_signer
        _write_json(
            output_path,
            make_isolated_candidate_output_v0_9(
                task=task,
                action_sequence=(step.action,),
                mechanism_steps=(step,),
            ),
        )
        return {"content_sha256": "5" * 64}

    def fake_verify_isolation(payload: Mapping[str, Any], **kwargs: Any) -> Any:
        calls.append("verify")
        assert payload["content_sha256"] == "5" * 64
        assert (
            kwargs["trusted_executor"].public_key_sha256
            == runner_signer.verifier().public_key_sha256
        )
        return SimpleNamespace(exit_code=0)

    runner_signer = Ed25519AttestationSigner.generate(key_id="real-macos-runner")
    monkeypatch.setattr(
        canonical_executor,
        "run_macos_isolated_execution_v0_9",
        fake_run_macos,
    )
    monkeypatch.setattr(
        canonical_executor,
        "verify_isolation_receipt_v0_9",
        fake_verify_isolation,
    )
    runner = MacOSIsolatedEpisodeRunnerV09(runner_signer=runner_signer)
    arguments = canonical_executor._canonical_isolation_arguments(
        task=task,
        entrypoint_path=entrypoint,
        visible_input_path=visible_input,
        output_path=output_path,
    )

    artifacts = runner.run(
        task=task,
        bundle_path=bundle,
        entrypoint_path=entrypoint,
        visible_input_path=visible_input,
        isolation_working_directory=work,
        isolation_arguments=arguments,
    )

    assert calls == ["run", "verify"]
    assert artifacts.episode_execution_receipt["runner_key_id"] == runner_signer.verifier().key_id
    assert artifacts.isolation_execution_receipt["content_sha256"] == "5" * 64
