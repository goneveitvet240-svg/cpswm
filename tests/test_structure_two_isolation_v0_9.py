from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from cpswm.system.attestation import (
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
)
from cpswm.system.evaluation_operations import structure_two_isolation_v0_9 as isolation
from cpswm.system.reproducibility import content_sha256


@dataclass(frozen=True)
class _Scenario:
    receipt: dict[str, Any]
    signer: Ed25519AttestationSigner
    command_engine: Path
    arguments: tuple[str, ...]
    code: Path
    input_path: Path
    work: Path
    output: Path
    calls: tuple[tuple[str, ...], ...]


def _require_macos_engines() -> None:
    if not isolation.MACOS_SANDBOX_EXEC_PATH.is_file():
        pytest.skip("unit scenario requires the fixed macOS sandbox-exec binary")
    if not isolation.MACOS_PROBE_PYTHON_PATH.is_file():
        pytest.skip("unit scenario requires the fixed macOS probe Python binary")


def _probe_stdout(environment: dict[str, str], *, passes: bool) -> bytes:
    observed = sorted(environment)
    payload = {
        "network_access_denied": passes,
        "code_write_denied": True,
        "input_write_denied": True,
        "outside_workdir_write_denied": True,
        "working_directory_write_allowed": True,
        "hidden_file_read_denied": passes,
        "process_fork_denied": passes,
        "stdin_is_devnull": passes,
        "environment_allowlist_exact": True,
        "network_errno": 1 if passes else None,
        "code_write_errno": 1,
        "input_write_errno": 1,
        "outside_write_errno": 1,
        "workdir_write_errno": None,
        "hidden_read_errno": 1 if passes else None,
        "fork_errno": 1 if passes else None,
        "observed_environment_names": observed,
        "unexpected_environment_names": [],
        "missing_environment_names": [],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _run_mocked_scenario(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    probe_passes: bool = True,
    exec_probe_passes: bool = True,
    command_behavior: str = "success",
) -> _Scenario:
    _require_macos_engines()
    monkeypatch.setattr(isolation.platform, "system", lambda: "Darwin")
    code = tmp_path / "code"
    inputs = tmp_path / "inputs"
    work = tmp_path / "work"
    code.mkdir()
    inputs.mkdir()
    work.mkdir()
    program = code / "candidate.py"
    program.write_text("print('candidate')\n", encoding="utf-8")
    input_path = inputs / "episode.json"
    input_path.write_text('{"episode":1}\n', encoding="utf-8")
    output = work / "result.json"
    arguments = (str(program), str(input_path), str(output))
    calls: list[tuple[str, ...]] = []

    def fake_run(
        argv: tuple[str, ...],
        *,
        working_directory: Path,
        environment: dict[str, str],
        timeout_seconds: int,
        limits: isolation.IsolationResourceLimitsV09,
    ) -> isolation.BoundedProcessOutcomeV09:
        del timeout_seconds, limits
        calls.append(tuple(argv))
        assert working_directory == work
        if len(calls) == 1:
            return isolation.BoundedProcessOutcomeV09(
                returncode=0,
                stdout=_probe_stdout(environment, passes=probe_passes),
                stderr=b"",
                timed_out=False,
            )
        if len(calls) == 2:
            payload = {
                "unlisted_process_exec_denied": exec_probe_passes,
                "exec_errno": 1 if exec_probe_passes else None,
            }
            stdout = (
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
                if exec_probe_passes
                else b"cpswm-exec-escape\n"
            )
            return isolation.BoundedProcessOutcomeV09(
                returncode=0,
                stdout=stdout,
                stderr=b"",
                timed_out=False,
            )
        if command_behavior == "timeout":
            return isolation.BoundedProcessOutcomeV09(
                returncode=isolation.TIMEOUT_EXIT_CODE,
                stdout=b"partial-output",
                stderr=b"deadline",
                timed_out=True,
            )
        output.write_text('{"status":"ok"}\n', encoding="utf-8")
        if command_behavior == "mutate-code":
            program.write_text("print('mutated')\n", encoding="utf-8")
        return isolation.BoundedProcessOutcomeV09(
            returncode=0,
            stdout=b"candidate-ok",
            stderr=b"",
            timed_out=False,
        )

    monkeypatch.setattr(isolation, "_run_bounded", fake_run)
    signer = Ed25519AttestationSigner.generate(key_id="independent-isolation-executor")
    receipt = isolation.run_macos_isolated_execution_v0_9(
        command_engine_path=isolation.MACOS_PROBE_PYTHON_PATH.resolve(strict=True),
        arguments=arguments,
        code_bundle_path=code,
        input_artifact_paths={"episode_input": input_path},
        working_directory=work,
        expected_output_relative_paths={"episode_output": "result.json"},
        executor=signer,
        timeout_seconds=10,
    )
    return _Scenario(
        receipt=receipt,
        signer=signer,
        command_engine=isolation.MACOS_PROBE_PYTHON_PATH.resolve(strict=True),
        arguments=arguments,
        code=code,
        input_path=input_path,
        work=work,
        output=output,
        calls=tuple(calls),
    )


def _verify(
    scenario: _Scenario,
    *,
    payload: dict[str, Any] | None = None,
    trusted_executor: Ed25519AttestationVerifier | None = None,
) -> isolation.IsolationExecutionReceiptV09:
    return isolation.verify_isolation_receipt_v0_9(
        payload or scenario.receipt,
        trusted_executor=trusted_executor or scenario.signer.verifier(),
        command_engine_path=scenario.command_engine,
        arguments=scenario.arguments,
        code_bundle_path=scenario.code,
        input_artifact_paths={"episode_input": scenario.input_path},
        working_directory=scenario.work,
        expected_output_relative_paths={"episode_output": "result.json"},
        timeout_seconds=10,
    )


def test_clean_environment_is_fixed_and_drops_parent_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("PYTHONPATH", "/attacker")
    monkeypatch.setenv("HTTP_PROXY", "http://attacker.invalid")
    monkeypatch.setenv("DYLD_INSERT_LIBRARIES", "/attacker.dylib")

    environment = isolation.clean_isolation_environment_v0_9(work)

    assert set(environment) == {
        "CPSWM_ISOLATION_PROTOCOL",
        "LANG",
        "LC_ALL",
        "PATH",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONHASHSEED",
        "PYTHONNOUSERSITE",
        "TMPDIR",
        "__CF_USER_TEXT_ENCODING",
    }
    assert environment["TMPDIR"].startswith(str(work.resolve()))
    assert "PYTHONPATH" not in environment
    assert "HTTP_PROXY" not in environment
    assert "DYLD_INSERT_LIBRARIES" not in environment


def test_profile_is_deterministic_and_has_required_denials(tmp_path: Path) -> None:
    _require_macos_engines()
    work = tmp_path / "work"
    code = tmp_path / "code"
    input_path = tmp_path / "input.json"
    work.mkdir()
    code.mkdir()
    input_path.write_text("{}", encoding="utf-8")

    first = isolation.render_macos_sandbox_profile_v0_9(
        command_engine_path=isolation.MACOS_PROBE_PYTHON_PATH,
        code_bundle_path=code,
        input_artifact_paths={"input": input_path},
        working_directory=work,
    )
    second = isolation.render_macos_sandbox_profile_v0_9(
        command_engine_path=isolation.MACOS_PROBE_PYTHON_PATH,
        code_bundle_path=code,
        input_artifact_paths={"input": input_path},
        working_directory=work,
    )

    assert first == second
    assert "(deny network*)" in first
    assert "(deny process-fork)" in first
    assert "(deny process-exec)" in first
    assert "(deny file-read-data)" in first
    assert "(deny file-write*)" in first
    assert '(subpath "/dev")' not in first
    assert f'(subpath "{work.resolve()}")' in first
    assert (
        isolation.hashlib.sha256(isolation._MACOS_PROFILE_TEMPLATE.encode()).hexdigest()
        == isolation.MACOS_POLICY_TEMPLATE_SHA256
    )


def test_positive_receipt_verifies_every_external_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _run_mocked_scenario(tmp_path, monkeypatch)

    verified = _verify(scenario)

    assert verified.formal_isolation_verified is True
    assert verified.status == "ISOLATION_PASSED"
    assert verified.probe_results.all_probes_passed is True
    assert verified.probe_results.hidden_file_read_denied is True
    assert verified.probe_results.process_fork_denied is True
    assert verified.probe_results.stdin_is_devnull is True
    assert verified.probe_results.unlisted_process_exec_denied is True
    assert verified.stdin_mode == "DEVNULL"
    assert verified.close_fds is True
    assert verified.pass_fds == ()
    assert verified.command_executed is True
    assert verified.argv == (str(scenario.command_engine), *scenario.arguments)
    assert verified.output_artifacts[0].content_sha256
    assert verified.executor_key_id == scenario.signer.key_id
    assert verified.executor_attestation is not None
    assert scenario.receipt["content_sha256"] == content_sha256(
        {key: value for key, value in scenario.receipt.items() if key != "content_sha256"}
    )
    assert len(scenario.calls) == 3


def test_untrusted_same_key_id_cannot_verify_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _run_mocked_scenario(tmp_path, monkeypatch)
    attacker = Ed25519AttestationSigner.generate(key_id=scenario.signer.key_id)

    with pytest.raises(AttestationError, match="untrusted executor"):
        _verify(scenario, trusted_executor=attacker.verifier())


def test_output_changed_after_signing_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _run_mocked_scenario(tmp_path, monkeypatch)
    scenario.output.write_text('{"status":"attacker-replaced"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="execution bindings"):
        _verify(scenario)


def test_trusted_resigning_cannot_override_canonical_profile_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _run_mocked_scenario(tmp_path, monkeypatch)
    forged = dict(scenario.receipt)
    forged.pop("content_sha256")
    forged["rendered_profile_sha256"] = "f" * 64
    forged["executor_attestation"] = None
    forged_record = isolation.IsolationExecutionReceiptV09.model_validate(forged)
    signable = forged_record.model_dump(mode="json", exclude={"executor_attestation"})
    forged["executor_attestation"] = scenario.signer.sign(
        isolation.ATTESTATION_DOMAIN, signable
    ).model_dump(mode="json")
    forged["content_sha256"] = content_sha256(forged)

    with pytest.raises(ValueError, match="execution bindings"):
        _verify(scenario, payload=forged)


def test_probe_failure_skips_candidate_and_cannot_authorize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _run_mocked_scenario(tmp_path, monkeypatch, probe_passes=False)

    assert scenario.receipt["status"] == "ISOLATION_FAILED"
    assert scenario.receipt["formal_isolation_verified"] is False
    assert scenario.receipt["command_executed"] is False
    assert len(scenario.calls) == 2
    with pytest.raises(ValueError, match="failed isolation receipt"):
        _verify(scenario)


def test_timeout_is_signed_as_failure_and_cannot_authorize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _run_mocked_scenario(tmp_path, monkeypatch, command_behavior="timeout")

    assert scenario.receipt["status"] == "ISOLATION_FAILED"
    assert scenario.receipt["timed_out"] is True
    assert scenario.receipt["exit_code"] == isolation.TIMEOUT_EXIT_CODE
    with pytest.raises(ValueError, match="failed isolation receipt"):
        _verify(scenario)


def test_unlisted_exec_probe_failure_skips_candidate_and_cannot_authorize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _run_mocked_scenario(tmp_path, monkeypatch, exec_probe_passes=False)

    assert scenario.receipt["probe_results"]["unlisted_process_exec_denied"] is False
    assert scenario.receipt["command_executed"] is False
    assert scenario.receipt["status"] == "ISOLATION_FAILED"
    assert len(scenario.calls) == 2
    with pytest.raises(ValueError, match="failed isolation receipt"):
        _verify(scenario)


def test_candidate_code_mutation_is_detected_even_with_complete_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scenario = _run_mocked_scenario(tmp_path, monkeypatch, command_behavior="mutate-code")

    assert scenario.receipt["code_bundle_unchanged"] is False
    assert scenario.receipt["status"] == "ISOLATION_FAILED"
    assert len(scenario.receipt["output_artifacts"]) == 1
    with pytest.raises(ValueError, match="failed isolation receipt"):
        _verify(scenario)


def test_output_path_escape_is_rejected_before_any_candidate_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_macos_engines()
    monkeypatch.setattr(isolation.platform, "system", lambda: "Darwin")
    code = tmp_path / "code"
    inputs = tmp_path / "inputs"
    work = tmp_path / "work"
    code.mkdir()
    inputs.mkdir()
    work.mkdir()
    input_path = inputs / "input.json"
    input_path.write_text("{}", encoding="utf-8")
    signer = Ed25519AttestationSigner.generate(key_id="executor")

    with pytest.raises(ValueError, match="nonescaping relative path"):
        isolation.run_macos_isolated_execution_v0_9(
            command_engine_path=isolation.MACOS_PROBE_PYTHON_PATH.resolve(strict=True),
            arguments=("-c", "pass"),
            code_bundle_path=code,
            input_artifact_paths={"input": input_path},
            working_directory=work,
            expected_output_relative_paths={"output": "../escape.json"},
            executor=signer,
            timeout_seconds=10,
        )


def test_oci_contract_reserves_fail_closed_security_surface() -> None:
    contract = isolation.OCIIsolationContractV09(
        runtime="docker",
        image_digest="sha256:" + "a" * 64,
        seccomp_profile_sha256="b" * 64,
        resource_limits=isolation.DEFAULT_RESOURCE_LIMITS,
    )

    assert contract.network_mode == "none"
    assert contract.read_only_root_filesystem is True
    assert contract.output_mount_is_only_writable_mount is True
    assert contract.runner_implemented is False
    assert contract.formal_execution_verified is False
    assert len(contract.content_sha256) == 64

    with pytest.raises(ValidationError, match="drop every Linux capability"):
        isolation.OCIIsolationContractV09(
            runtime="podman",
            image_digest="sha256:" + "c" * 64,
            dropped_capabilities=("NET_ADMIN",),
            seccomp_profile_sha256="d" * 64,
            resource_limits=isolation.DEFAULT_RESOURCE_LIMITS,
        )
