"""Externally attested execution isolation for Structure-Two v0.9.

The existing ``-I -S`` pytest launcher controls Python startup hooks, but it is
not an operating-system isolation boundary.  This module adds a macOS
``sandbox-exec`` backend whose policy denies networking, process spawning, and
all filesystem writes outside one dedicated working directory.  A successful
run is accompanied by active escape probes and a content-bound Ed25519 receipt.

``sandbox-exec`` is a deprecated macOS interface.  It is nevertheless useful
for the current external run because the binary is part of the host selected by
the custodian.  The separate OCI contract below records the stronger portable
backend that still needs an implementation; it deliberately cannot represent a
successful OCI execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import signal
import stat
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-isolated-execution-receipt@0.9"
MACOS_POLICY_ID = "structure-two-macos-sandbox-policy@0.9"
OCI_CONTRACT_PROTOCOL_ID = "structure-two-oci-isolation-contract@0.9"
REAL_PROBE_PROTOCOL_ID = "structure-two-macos-sandbox-real-probe@0.9"
ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.isolated_execution.v0.9"
MACOS_SANDBOX_EXEC_PATH = Path("/usr/bin/sandbox-exec")
MACOS_PROBE_PYTHON_PATH = Path(
    "/Library/Developer/CommandLineTools/Library/Frameworks/"
    "Python3.framework/Versions/Current/bin/python3"
)
MACOS_EXEC_ESCAPE_TARGET_PATH = Path("/bin/echo")
MACOS_FIXED_RUNTIME_READ_PATHS = (
    Path("/System"),
    Path("/usr/lib"),
    Path("/usr/share"),
    Path("/Library/Apple/System"),
    Path("/Library/Developer/CommandLineTools"),
    Path("/private/var/db/timezone"),
)
MACOS_FIXED_DEVICE_READ_PATHS = (
    Path("/dev/null"),
    Path("/dev/random"),
    Path("/dev/urandom"),
)
MACOS_PROBE_EXEC_RUNTIME_ROOTS = (
    Path("/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework"),
)
SKIPPED_EXECUTION_EXIT_CODE = 126
TIMEOUT_EXIT_CODE = 124

_CLEAN_ENVIRONMENT_STATIC: Mapping[str, str] = {
    "CPSWM_ISOLATION_PROTOCOL": PROTOCOL_ID,
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
    "PYTHONNOUSERSITE": "1",
}

_MACOS_PROFILE_TEMPLATE = """(version 1)
; {policy_id}
; Default non-filesystem services remain available, but all reads, writes,
; networking, forks, and unlisted execs are denied and then narrowly reopened.
(allow default)
(deny network*)
(deny process-fork)
(deny process-exec)
(allow process-exec
{process_exec_rules})
(deny file-read-data)
(allow file-read-data
{file_read_rules})
(deny file-write*)
(allow file-write*
    (subpath {working_directory}))
(allow file-write-data
    (literal "/dev/null")
    (literal "/dev/zero"))
"""
MACOS_POLICY_TEMPLATE_SHA256 = hashlib.sha256(_MACOS_PROFILE_TEMPLATE.encode("utf-8")).hexdigest()

_PROBE_SOURCE = r"""
import errno
import json
import os
import socket
import sys

DENIED = {errno.EPERM, errno.EACCES, errno.EROFS, errno.EAGAIN}

def write_denied(path):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as exc:
        return exc.errno in DENIED, exc.errno
    else:
        os.close(fd)
        try:
            os.unlink(path)
        except OSError:
            pass
        return False, None

def write_allowed(path):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, b"sandbox-write-control")
        os.close(fd)
        os.unlink(path)
        return True, None
    except OSError as exc:
        return False, exc.errno

def network_denied():
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(b"cpswm-network-probe", ("127.0.0.1", 9))
        return False, None
    except OSError as exc:
        return exc.errno in DENIED, exc.errno
    finally:
        if sock is not None:
            sock.close()

def read_denied(path):
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY)
        os.read(fd, 1)
    except OSError as exc:
        return exc.errno in DENIED, exc.errno
    finally:
        if fd is not None:
            os.close(fd)
    return False, None

def fork_denied():
    try:
        pid = os.fork()
    except OSError as exc:
        return exc.errno in DENIED, exc.errno
    if pid == 0:
        os._exit(0)
    os.waitpid(pid, 0)
    return False, None

def stdin_is_devnull():
    try:
        return os.read(0, 1) == b""
    except OSError:
        return False

expected_environment = set(json.loads(sys.argv[1]))
network_ok, network_errno = network_denied()
code_ok, code_errno = write_denied(sys.argv[2])
input_ok, input_errno = write_denied(sys.argv[3])
outside_ok, outside_errno = write_denied(sys.argv[4])
work_ok, work_errno = write_allowed(sys.argv[5])
hidden_read_ok, hidden_read_errno = read_denied(sys.argv[6])
fork_ok, fork_errno = fork_denied()
stdin_ok = stdin_is_devnull()
observed_environment = set(os.environ)
payload = {
    "network_access_denied": network_ok,
    "code_write_denied": code_ok,
    "input_write_denied": input_ok,
    "outside_workdir_write_denied": outside_ok,
    "working_directory_write_allowed": work_ok,
    "hidden_file_read_denied": hidden_read_ok,
    "process_fork_denied": fork_ok,
    "stdin_is_devnull": stdin_ok,
    "environment_allowlist_exact": observed_environment == expected_environment,
    "network_errno": network_errno,
    "code_write_errno": code_errno,
    "input_write_errno": input_errno,
    "outside_write_errno": outside_errno,
    "workdir_write_errno": work_errno,
    "hidden_read_errno": hidden_read_errno,
    "fork_errno": fork_errno,
    "observed_environment_names": sorted(observed_environment),
    "unexpected_environment_names": sorted(observed_environment - expected_environment),
    "missing_environment_names": sorted(expected_environment - observed_environment),
}
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
""".strip()

_EXEC_PROBE_SOURCE = r"""
import errno
import json
import os
import sys

DENIED = {errno.EPERM, errno.EACCES, errno.EROFS, errno.EAGAIN}
try:
    os.execv(sys.argv[1], (sys.argv[1], "cpswm-exec-escape"))
except OSError as exc:
    payload = {
        "unlisted_process_exec_denied": exc.errno in DENIED,
        "exec_errno": exc.errno,
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
""".strip()


class IsolationResourceLimitsV09(ContractModel):
    """Resource ceilings inherited by the sandbox and its executed payload."""

    cpu_seconds: int = Field(gt=0, le=3600)
    output_file_bytes: int = Field(gt=0)
    open_files: int = Field(ge=16, le=4096)
    process_count: int = Field(ge=1, le=256)


DEFAULT_RESOURCE_LIMITS = IsolationResourceLimitsV09(
    cpu_seconds=30,
    output_file_bytes=64 * 1024 * 1024,
    open_files=128,
    process_count=32,
)


class IsolationArtifactBindingV09(ContractModel):
    label: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    resolved_path: str = Field(min_length=1)
    artifact_kind: Literal["file", "directory"]
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class IsolationProbeResultsV09(ContractModel):
    network_access_denied: bool
    code_write_denied: bool
    input_write_denied: bool
    outside_workdir_write_denied: bool
    working_directory_write_allowed: bool
    hidden_file_read_denied: bool
    process_fork_denied: bool
    stdin_is_devnull: bool
    unlisted_process_exec_denied: bool
    environment_allowlist_exact: bool
    network_errno: int | None = None
    code_write_errno: int | None = None
    input_write_errno: int | None = None
    outside_write_errno: int | None = None
    workdir_write_errno: int | None = None
    hidden_read_errno: int | None = None
    fork_errno: int | None = None
    exec_errno: int | None = None
    hidden_probe_path: str = Field(min_length=1)
    hidden_probe_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    exec_probe_target_path: Literal["/bin/echo"]
    exec_probe_target_binary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observed_environment_names: tuple[str, ...]
    unexpected_environment_names: tuple[str, ...]
    missing_environment_names: tuple[str, ...]
    probe_exit_code: int
    probe_stdout_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    probe_stderr_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    exec_probe_exit_code: int
    exec_probe_stdout_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    exec_probe_stderr_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    all_probes_passed: bool

    @model_validator(mode="after")
    def validate_probe_decision(self) -> IsolationProbeResultsV09:
        derived = all(
            (
                self.network_access_denied,
                self.code_write_denied,
                self.input_write_denied,
                self.outside_workdir_write_denied,
                self.working_directory_write_allowed,
                self.hidden_file_read_denied,
                self.process_fork_denied,
                self.stdin_is_devnull,
                self.unlisted_process_exec_denied,
                self.environment_allowlist_exact,
                self.probe_exit_code == 0,
                self.exec_probe_exit_code == 0,
                not self.unexpected_environment_names,
                not self.missing_environment_names,
            )
        )
        if self.all_probes_passed is not derived:
            raise ValueError("isolation probe decision differs from raw probe outcomes")
        return self


class IsolationExecutionReceiptV09(ContractModel):
    protocol: Literal["structure-two-isolated-execution-receipt@0.9"]
    backend: Literal["macos_sandbox_exec"]
    status: Literal["ISOLATION_PASSED", "ISOLATION_FAILED"]
    policy_id: Literal["structure-two-macos-sandbox-policy@0.9"]
    policy_template_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rendered_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_unchanged_during_execution: bool
    read_isolation_mode: Literal["deny-all-file-data-then-allow-fixed-runtime-code-input-work"]
    fixed_runtime_read_allowlist: tuple[str, ...] = Field(min_length=1)
    sandbox_engine_path: Literal["/usr/bin/sandbox-exec"]
    sandbox_engine_binary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    command_engine_path: str = Field(min_length=1)
    command_engine_binary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    probe_engine_path: str = Field(min_length=1)
    probe_engine_binary_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    argv: tuple[str, ...] = Field(min_length=1)
    stdin_mode: Literal["DEVNULL"]
    close_fds: Literal[True]
    pass_fds: tuple[int, ...]
    working_directory: str = Field(min_length=1)
    clean_environment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    resource_limits: IsolationResourceLimitsV09
    timeout_seconds: int = Field(gt=0, le=86400)
    code_bundle: IsolationArtifactBindingV09
    input_artifacts: tuple[IsolationArtifactBindingV09, ...] = Field(min_length=1)
    expected_output_relative_paths: dict[str, str]
    output_artifacts: tuple[IsolationArtifactBindingV09, ...]
    code_bundle_unchanged: bool
    input_artifacts_unchanged: bool
    engine_binaries_unchanged: bool
    probe_results: IsolationProbeResultsV09
    command_executed: bool
    exit_code: int
    timed_out: bool
    stdout_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stderr_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at_utc: datetime
    finished_at_utc: datetime
    host_system: Literal["Darwin"]
    host_release: str = Field(min_length=1)
    host_machine: str = Field(min_length=1)
    formal_isolation_verified: bool
    executor_key_id: str = Field(min_length=1)
    executor_public_key_base64: str = Field(min_length=1)
    executor_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executor_attestation: Attestation | None = None
    claim_boundary: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decision(self) -> IsolationExecutionReceiptV09:
        if self.started_at_utc.utcoffset() is None or self.finished_at_utc.utcoffset() is None:
            raise ValueError("isolation receipt timestamps must be timezone-aware")
        if self.finished_at_utc <= self.started_at_utc:
            raise ValueError("isolation receipt finish time must follow start time")
        if self.policy_template_sha256 != MACOS_POLICY_TEMPLATE_SHA256:
            raise ValueError("isolation receipt used a noncanonical policy template")
        if not self.argv or self.argv[0] != self.command_engine_path:
            raise ValueError("isolation receipt argv does not start with its command engine")
        if self.pass_fds:
            raise ValueError("formal isolation may not pass inherited file descriptors")
        if not self.expected_output_relative_paths:
            raise ValueError("isolated execution must preregister at least one output")
        expected_labels = set(self.expected_output_relative_paths)
        actual_labels = {item.label for item in self.output_artifacts}
        if len(actual_labels) != len(self.output_artifacts) or not actual_labels <= expected_labels:
            raise ValueError("isolation receipt output artifact set is malformed")
        derived_pass = all(
            (
                self.profile_unchanged_during_execution,
                self.code_bundle_unchanged,
                self.input_artifacts_unchanged,
                self.engine_binaries_unchanged,
                self.probe_results.all_probes_passed,
                self.command_executed,
                self.exit_code == 0,
                not self.timed_out,
                actual_labels == expected_labels,
            )
        )
        if self.formal_isolation_verified is not derived_pass:
            raise ValueError("formal isolation decision differs from bound execution evidence")
        expected_status = "ISOLATION_PASSED" if derived_pass else "ISOLATION_FAILED"
        if self.status != expected_status:
            raise ValueError("isolation status differs from the formal decision")
        return self


class OCIIsolationContractV09(ContractModel):
    """Fail-closed reservation for a future OCI implementation."""

    protocol: Literal["structure-two-oci-isolation-contract@0.9"] = (
        "structure-two-oci-isolation-contract@0.9"
    )
    status: Literal["CONTRACT_ONLY_NOT_EXECUTED"] = "CONTRACT_ONLY_NOT_EXECUTED"
    runtime: Literal["docker", "podman"]
    image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    network_mode: Literal["none"] = "none"
    read_only_root_filesystem: Literal[True] = True
    code_mount_read_only: Literal[True] = True
    input_mounts_read_only: Literal[True] = True
    output_mount_is_only_writable_mount: Literal[True] = True
    run_as_non_root: Literal[True] = True
    dropped_capabilities: tuple[str, ...] = ("ALL",)
    no_new_privileges: Literal[True] = True
    seccomp_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    resource_limits: IsolationResourceLimitsV09
    runner_implemented: Literal[False] = False
    formal_execution_verified: Literal[False] = False

    @model_validator(mode="after")
    def validate_oci_security_contract(self) -> OCIIsolationContractV09:
        if self.dropped_capabilities != ("ALL",):
            raise ValueError("OCI isolation must drop every Linux capability")
        return self

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


class IsolationRunnerV09(Protocol):
    """Common interface to be implemented by macOS and future OCI runners."""

    @property
    def backend(self) -> str: ...

    def execute(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class BoundedProcessOutcomeV09:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file():
        raise ValueError("engine path must be a regular non-symlink file")
    return _sha256_bytes(resolved.read_bytes())


def _artifact_binding(label: str, path: Path) -> IsolationArtifactBindingV09:
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789_.-"
    if not label or any(character not in allowed for character in label):
        raise ValueError("artifact label is not canonical")
    if not label[0].isalpha() or not label[0].islower():
        raise ValueError("artifact label must start with a lowercase letter")
    if path.is_symlink():
        raise ValueError("isolated artifacts may not be symbolic links")
    resolved = path.resolve(strict=True)
    if resolved.is_file():
        return IsolationArtifactBindingV09(
            label=label,
            resolved_path=str(resolved),
            artifact_kind="file",
            content_sha256=_sha256_bytes(resolved.read_bytes()),
        )
    if not resolved.is_dir():
        raise ValueError("isolated artifact is neither a file nor directory")
    rows: list[tuple[str, str]] = []
    for item in sorted(resolved.rglob("*")):
        relative = item.relative_to(resolved).as_posix()
        if item.is_symlink():
            raise ValueError("isolated artifact directory contains a symbolic link")
        if item.is_dir():
            continue
        if not item.is_file():
            raise ValueError("isolated artifact directory contains a special file")
        rows.append((relative, _sha256_bytes(item.read_bytes())))
    return IsolationArtifactBindingV09(
        label=label,
        resolved_path=str(resolved),
        artifact_kind="directory",
        content_sha256=content_sha256({"files": rows}),
    )


def _same_bindings(
    left: Sequence[IsolationArtifactBindingV09],
    right: Sequence[IsolationArtifactBindingV09],
) -> bool:
    return tuple(left) == tuple(right)


def clean_isolation_environment_v0_9(working_directory: Path) -> dict[str, str]:
    root = working_directory.resolve(strict=True)
    environment = dict(_CLEAN_ENVIRONMENT_STATIC)
    environment["TMPDIR"] = str(root / ".tmp")
    environment["__CF_USER_TEXT_ENCODING"] = f"0x{os.getuid():X}:0x0:0x0"
    return environment


def _profile_literal(path: Path) -> str:
    return json.dumps(str(path.resolve(strict=True)))


def _profile_path_rule(path: Path) -> str:
    resolved = path.resolve(strict=True)
    literal = json.dumps(str(resolved))
    if resolved.is_dir():
        return f"    (literal {literal})\n    (subpath {literal})"
    return f"    (literal {literal})"


def _fixed_runtime_read_paths() -> tuple[Path, ...]:
    resolved: list[Path] = []
    for path in MACOS_FIXED_RUNTIME_READ_PATHS:
        item = path.resolve(strict=True)
        mode = item.stat()
        if mode.st_uid != 0 or mode.st_mode & 0o022:
            raise ValueError("fixed macOS runtime read roots must be root-owned and immutable")
        resolved.append(item)
    return tuple(resolved)


def _fixed_device_read_paths() -> tuple[Path, ...]:
    resolved: list[Path] = []
    for path in MACOS_FIXED_DEVICE_READ_PATHS:
        item = path.resolve(strict=True)
        metadata = item.stat()
        if metadata.st_uid != 0 or not stat.S_ISCHR(metadata.st_mode):
            raise ValueError("fixed macOS device reads must be root-owned character devices")
        resolved.append(item)
    return tuple(resolved)


def _fixed_runtime_read_allowlist_strings() -> tuple[str, ...]:
    return (
        "/",
        *(str(path) for path in _fixed_runtime_read_paths()),
        *(str(path) for path in _fixed_device_read_paths()),
    )


def render_macos_sandbox_profile_v0_9(
    *,
    command_engine_path: Path,
    code_bundle_path: Path,
    input_artifact_paths: Mapping[str, Path],
    working_directory: Path,
) -> str:
    command_engine = command_engine_path.resolve(strict=True)
    probe_engine = MACOS_PROBE_PYTHON_PATH.resolve(strict=True)
    engines = tuple(sorted({command_engine, probe_engine}, key=str))
    process_paths = {
        *engines,
        *(path.resolve(strict=True) for path in MACOS_PROBE_EXEC_RUNTIME_ROOTS),
    }
    process_rules = "\n".join(_profile_path_rule(path) for path in sorted(process_paths, key=str))
    read_paths = {
        *_fixed_runtime_read_paths(),
        *_fixed_device_read_paths(),
        *engines,
        MACOS_EXEC_ESCAPE_TARGET_PATH.resolve(strict=True),
        code_bundle_path.resolve(strict=True),
        *(path.resolve(strict=True) for path in input_artifact_paths.values()),
        working_directory.resolve(strict=True),
    }
    file_read_rules = '    (literal "/")\n' + "\n".join(
        _profile_path_rule(path) for path in sorted(read_paths, key=str)
    )
    return _MACOS_PROFILE_TEMPLATE.format(
        policy_id=MACOS_POLICY_ID,
        process_exec_rules=process_rules,
        file_read_rules=file_read_rules,
        working_directory=_profile_literal(working_directory),
    )


def _resource_limiter(limits: IsolationResourceLimitsV09) -> Any:
    def apply_limits() -> None:
        ceilings = (
            (resource.RLIMIT_CPU, limits.cpu_seconds),
            (resource.RLIMIT_FSIZE, limits.output_file_bytes),
            (resource.RLIMIT_NOFILE, limits.open_files),
            (resource.RLIMIT_NPROC, limits.process_count),
            (resource.RLIMIT_CORE, 0),
        )
        for key, value in ceilings:
            resource.setrlimit(key, (value, value))

    return apply_limits


def _run_bounded(
    argv: Sequence[str],
    *,
    working_directory: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
    limits: IsolationResourceLimitsV09,
) -> BoundedProcessOutcomeV09:
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            tuple(argv),
            cwd=working_directory,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            pass_fds=(),
            start_new_session=True,
            preexec_fn=_resource_limiter(limits),
        )
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        if process is not None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        else:  # pragma: no cover - Popen cannot time out before returning
            stdout, stderr = b"", b""
        return BoundedProcessOutcomeV09(
            returncode=TIMEOUT_EXIT_CODE,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
        )
    except OSError as exc:
        return BoundedProcessOutcomeV09(
            returncode=SKIPPED_EXECUTION_EXIT_CODE,
            stdout=b"",
            stderr=str(exc).encode("utf-8", errors="replace"),
            timed_out=False,
        )
    return BoundedProcessOutcomeV09(
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=False,
    )


def _failed_probe_results(
    outcome: BoundedProcessOutcomeV09,
    *,
    exec_outcome: BoundedProcessOutcomeV09,
    hidden_probe_path: Path,
    hidden_probe_content_sha256: str,
    exec_probe_target_binary_sha256: str,
) -> IsolationProbeResultsV09:
    return IsolationProbeResultsV09(
        network_access_denied=False,
        code_write_denied=False,
        input_write_denied=False,
        outside_workdir_write_denied=False,
        working_directory_write_allowed=False,
        hidden_file_read_denied=False,
        process_fork_denied=False,
        stdin_is_devnull=False,
        unlisted_process_exec_denied=False,
        environment_allowlist_exact=False,
        hidden_probe_path=str(hidden_probe_path),
        hidden_probe_content_sha256=hidden_probe_content_sha256,
        exec_probe_target_path=str(MACOS_EXEC_ESCAPE_TARGET_PATH),
        exec_probe_target_binary_sha256=exec_probe_target_binary_sha256,
        observed_environment_names=(),
        unexpected_environment_names=(),
        missing_environment_names=(),
        probe_exit_code=outcome.returncode,
        probe_stdout_sha256=_sha256_bytes(outcome.stdout),
        probe_stderr_sha256=_sha256_bytes(outcome.stderr),
        exec_probe_exit_code=exec_outcome.returncode,
        exec_probe_stdout_sha256=_sha256_bytes(exec_outcome.stdout),
        exec_probe_stderr_sha256=_sha256_bytes(exec_outcome.stderr),
        all_probes_passed=False,
    )


def _parse_probe_results(
    outcome: BoundedProcessOutcomeV09,
    *,
    exec_outcome: BoundedProcessOutcomeV09,
    expected_environment_names: tuple[str, ...],
    hidden_probe_path: Path,
    hidden_probe_content_sha256: str,
    exec_probe_target_binary_sha256: str,
) -> IsolationProbeResultsV09:
    if outcome.returncode != 0 or outcome.timed_out:
        return _failed_probe_results(
            outcome,
            exec_outcome=exec_outcome,
            hidden_probe_path=hidden_probe_path,
            hidden_probe_content_sha256=hidden_probe_content_sha256,
            exec_probe_target_binary_sha256=exec_probe_target_binary_sha256,
        )
    try:
        payload = json.loads(outcome.stdout)
        if not isinstance(payload, dict):
            raise ValueError("probe output is not an object")
        exec_payload = json.loads(exec_outcome.stdout)
        if not isinstance(exec_payload, dict):
            raise ValueError("exec probe output is not an object")
        observed = tuple(str(item) for item in payload["observed_environment_names"])
        unexpected = tuple(str(item) for item in payload["unexpected_environment_names"])
        missing = tuple(str(item) for item in payload["missing_environment_names"])
        exact_environment = (
            payload.get("environment_allowlist_exact") is True
            and observed == expected_environment_names
            and not unexpected
            and not missing
        )
        booleans = {
            name: payload.get(name) is True
            for name in (
                "network_access_denied",
                "code_write_denied",
                "input_write_denied",
                "outside_workdir_write_denied",
                "working_directory_write_allowed",
                "hidden_file_read_denied",
                "process_fork_denied",
                "stdin_is_devnull",
            )
        }
        unlisted_exec_denied = (
            exec_outcome.returncode == 0
            and not exec_outcome.timed_out
            and exec_payload.get("unlisted_process_exec_denied") is True
        )
        all_passed = all((*booleans.values(), unlisted_exec_denied, exact_environment))
        return IsolationProbeResultsV09(
            **booleans,
            unlisted_process_exec_denied=unlisted_exec_denied,
            environment_allowlist_exact=exact_environment,
            network_errno=payload.get("network_errno"),
            code_write_errno=payload.get("code_write_errno"),
            input_write_errno=payload.get("input_write_errno"),
            outside_write_errno=payload.get("outside_write_errno"),
            workdir_write_errno=payload.get("workdir_write_errno"),
            hidden_read_errno=payload.get("hidden_read_errno"),
            fork_errno=payload.get("fork_errno"),
            exec_errno=exec_payload.get("exec_errno"),
            hidden_probe_path=str(hidden_probe_path),
            hidden_probe_content_sha256=hidden_probe_content_sha256,
            exec_probe_target_path=str(MACOS_EXEC_ESCAPE_TARGET_PATH),
            exec_probe_target_binary_sha256=exec_probe_target_binary_sha256,
            observed_environment_names=observed,
            unexpected_environment_names=unexpected,
            missing_environment_names=missing,
            probe_exit_code=outcome.returncode,
            probe_stdout_sha256=_sha256_bytes(outcome.stdout),
            probe_stderr_sha256=_sha256_bytes(outcome.stderr),
            exec_probe_exit_code=exec_outcome.returncode,
            exec_probe_stdout_sha256=_sha256_bytes(exec_outcome.stdout),
            exec_probe_stderr_sha256=_sha256_bytes(exec_outcome.stderr),
            all_probes_passed=all_passed,
        )
    except (KeyError, TypeError, ValueError):
        return _failed_probe_results(
            outcome,
            exec_outcome=exec_outcome,
            hidden_probe_path=hidden_probe_path,
            hidden_probe_content_sha256=hidden_probe_content_sha256,
            exec_probe_target_binary_sha256=exec_probe_target_binary_sha256,
        )


def _resolve_output_paths(
    working_directory: Path, expected_output_relative_paths: Mapping[str, str | Path]
) -> dict[str, tuple[str, Path]]:
    if not expected_output_relative_paths:
        raise ValueError("isolated execution requires at least one expected output")
    root = working_directory.resolve(strict=True)
    resolved: dict[str, tuple[str, Path]] = {}
    for label in sorted(expected_output_relative_paths):
        relative = Path(expected_output_relative_paths[label])
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ValueError("isolated output path must be a nonescaping relative path")
        target = (root / relative).resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("isolated output path escapes the working directory") from exc
        if target.exists() or target.is_symlink():
            raise ValueError("isolated output path already exists before execution")
        resolved[label] = (relative.as_posix(), target)
    if len({target for _, target in resolved.values()}) != len(resolved):
        raise ValueError("isolated output paths must be unique")
    return resolved


def _assert_disjoint_readonly_artifact(path: Path, working_directory: Path) -> None:
    resolved = path.resolve(strict=True)
    work = working_directory.resolve(strict=True)
    if resolved == work or resolved.is_relative_to(work) or work.is_relative_to(resolved):
        raise ValueError("code and input artifacts must be disjoint from the writable directory")


def _probe_marker(parent: Path, prefix: str) -> Path:
    if parent.is_file():
        parent = parent.parent
    return parent / f".{prefix}-{uuid4().hex}"


def _receipt_payload(record: IsolationExecutionReceiptV09) -> dict[str, Any]:
    return record.model_dump(mode="json", exclude={"executor_attestation"})


def run_macos_isolated_execution_v0_9(
    *,
    command_engine_path: Path,
    arguments: Sequence[str],
    code_bundle_path: Path,
    input_artifact_paths: Mapping[str, Path],
    working_directory: Path,
    expected_output_relative_paths: Mapping[str, str | Path],
    executor: Ed25519AttestationSigner,
    timeout_seconds: int,
    resource_limits: IsolationResourceLimitsV09 = DEFAULT_RESOURCE_LIMITS,
) -> dict[str, Any]:
    """Run one fixed argv under the macOS sandbox and sign its evidence.

    The caller must give this function a fresh, dedicated working directory.
    All command arguments are passed directly; no shell is involved.
    """

    if platform.system() != "Darwin":
        raise ValueError("the macOS sandbox backend requires Darwin")
    if timeout_seconds <= 0 or timeout_seconds > 86400:
        raise ValueError("isolation timeout is outside the supported range")
    sandbox_engine = MACOS_SANDBOX_EXEC_PATH.resolve(strict=True)
    if sandbox_engine != MACOS_SANDBOX_EXEC_PATH or sandbox_engine.is_symlink():
        raise ValueError("formal macOS isolation requires /usr/bin/sandbox-exec")
    command_engine = command_engine_path.resolve(strict=True)
    probe_engine = MACOS_PROBE_PYTHON_PATH.resolve(strict=True)
    if command_engine_path.is_symlink() or probe_engine.is_symlink():
        raise ValueError("isolation command engines may not be symbolic links")
    exec_probe_target = MACOS_EXEC_ESCAPE_TARGET_PATH.resolve(strict=True)
    work = working_directory.resolve(strict=True)
    if working_directory.is_symlink() or not work.is_dir():
        raise ValueError("isolated working directory must be a real directory")
    if any(work.iterdir()):
        raise ValueError("isolated working directory must be fresh and empty")
    _assert_disjoint_readonly_artifact(code_bundle_path, work)
    if not input_artifact_paths:
        raise ValueError("isolated execution requires at least one input artifact")
    for path in input_artifact_paths.values():
        _assert_disjoint_readonly_artifact(path, work)
    outputs = _resolve_output_paths(work, expected_output_relative_paths)

    code_before = _artifact_binding("code_bundle", code_bundle_path)
    inputs_before = tuple(
        _artifact_binding(label, input_artifact_paths[label])
        for label in sorted(input_artifact_paths)
    )
    sandbox_sha256_before = _file_sha256(sandbox_engine)
    command_sha256_before = _file_sha256(command_engine)
    probe_sha256_before = _file_sha256(probe_engine)
    exec_probe_target_sha256_before = _file_sha256(exec_probe_target)
    profile = render_macos_sandbox_profile_v0_9(
        command_engine_path=command_engine,
        code_bundle_path=code_bundle_path,
        input_artifact_paths=input_artifact_paths,
        working_directory=work,
    )
    profile_sha256 = _sha256_bytes(profile.encode("utf-8"))
    environment = clean_isolation_environment_v0_9(work)
    environment_sha256 = content_sha256(dict(sorted(environment.items())))
    expected_environment_names = tuple(sorted(environment))
    full_argv = (str(command_engine), *(str(item) for item in arguments))

    code_marker = _probe_marker(code_bundle_path.resolve(strict=True), "cpswm-code-write-probe")
    first_input = input_artifact_paths[sorted(input_artifact_paths)[0]].resolve(strict=True)
    input_marker = _probe_marker(first_input, "cpswm-input-write-probe")
    outside_marker = _probe_marker(work.parent, "cpswm-outside-write-probe")
    work_marker = work / f".cpswm-work-write-control-{uuid4().hex}"
    for marker in (code_marker, input_marker, outside_marker, work_marker):
        if marker.exists() or marker.is_symlink():
            raise ValueError("isolation probe marker unexpectedly exists")

    started_at = datetime.now(UTC)
    command_outcome = BoundedProcessOutcomeV09(
        returncode=SKIPPED_EXECUTION_EXIT_CODE,
        stdout=b"",
        stderr=b"execution skipped because isolation probes did not pass",
        timed_out=False,
    )
    with tempfile.TemporaryDirectory(prefix="cpswm-sandbox-profile-") as directory:
        profile_path = Path(directory) / "profile.sb"
        hidden_probe_path = Path(directory) / "hidden-truth.bin"
        hidden_probe_path.write_bytes(b"cpswm-hidden-truth:" + os.urandom(32))
        hidden_probe_path.chmod(0o400)
        hidden_probe_content_sha256 = _file_sha256(hidden_probe_path)
        profile_path.write_text(profile, encoding="utf-8")
        profile_path.chmod(0o400)
        profile_file_sha256_before = _file_sha256(profile_path)
        sandbox_prefix = (str(sandbox_engine), "-f", str(profile_path))
        probe_outcome = _run_bounded(
            (
                *sandbox_prefix,
                str(probe_engine),
                "-I",
                "-S",
                "-B",
                "-c",
                _PROBE_SOURCE,
                json.dumps(expected_environment_names),
                str(code_marker),
                str(input_marker),
                str(outside_marker),
                str(work_marker),
                str(hidden_probe_path),
            ),
            working_directory=work,
            environment=environment,
            timeout_seconds=min(timeout_seconds, 30),
            limits=resource_limits,
        )
        exec_probe_outcome = _run_bounded(
            (
                *sandbox_prefix,
                str(probe_engine),
                "-I",
                "-S",
                "-B",
                "-c",
                _EXEC_PROBE_SOURCE,
                str(exec_probe_target),
            ),
            working_directory=work,
            environment=environment,
            timeout_seconds=min(timeout_seconds, 30),
            limits=resource_limits,
        )
        probes = _parse_probe_results(
            probe_outcome,
            exec_outcome=exec_probe_outcome,
            expected_environment_names=expected_environment_names,
            hidden_probe_path=hidden_probe_path,
            hidden_probe_content_sha256=hidden_probe_content_sha256,
            exec_probe_target_binary_sha256=exec_probe_target_sha256_before,
        )
        if probes.all_probes_passed:
            command_outcome = _run_bounded(
                (*sandbox_prefix, *full_argv),
                working_directory=work,
                environment=environment,
                timeout_seconds=timeout_seconds,
                limits=resource_limits,
            )
        profile_unchanged = _file_sha256(profile_path) == profile_file_sha256_before

    for marker in (code_marker, input_marker, outside_marker, work_marker):
        marker.unlink(missing_ok=True)
    finished_at = datetime.now(UTC)
    if finished_at <= started_at:
        finished_at = started_at + timedelta(microseconds=1)

    try:
        code_after = _artifact_binding("code_bundle", code_bundle_path)
        inputs_after = tuple(
            _artifact_binding(label, input_artifact_paths[label])
            for label in sorted(input_artifact_paths)
        )
    except (OSError, ValueError):
        code_after = code_before.model_copy(update={"content_sha256": "0" * 64})
        inputs_after = ()
    code_unchanged = code_after == code_before
    inputs_unchanged = _same_bindings(inputs_after, inputs_before)
    try:
        engines_unchanged = all(
            (
                _file_sha256(sandbox_engine) == sandbox_sha256_before,
                _file_sha256(command_engine) == command_sha256_before,
                _file_sha256(probe_engine) == probe_sha256_before,
                _file_sha256(exec_probe_target) == exec_probe_target_sha256_before,
            )
        )
    except (OSError, ValueError):
        engines_unchanged = False

    output_bindings: list[IsolationArtifactBindingV09] = []
    if command_outcome.returncode == 0 and not command_outcome.timed_out:
        for label, (_, target) in outputs.items():
            try:
                resolved_target = target.resolve(strict=True)
                resolved_target.relative_to(work)
                output_bindings.append(_artifact_binding(label, resolved_target))
            except (OSError, ValueError):
                continue
    output_labels = {item.label for item in output_bindings}
    formal_passed = all(
        (
            profile_unchanged,
            code_unchanged,
            inputs_unchanged,
            engines_unchanged,
            probes.all_probes_passed,
            command_outcome.returncode == 0,
            not command_outcome.timed_out,
            output_labels == set(outputs),
        )
    )
    verifier = executor.verifier()
    unsigned = IsolationExecutionReceiptV09(
        protocol=PROTOCOL_ID,
        backend="macos_sandbox_exec",
        status="ISOLATION_PASSED" if formal_passed else "ISOLATION_FAILED",
        policy_id=MACOS_POLICY_ID,
        policy_template_sha256=MACOS_POLICY_TEMPLATE_SHA256,
        rendered_profile_sha256=profile_sha256,
        profile_unchanged_during_execution=profile_unchanged,
        read_isolation_mode="deny-all-file-data-then-allow-fixed-runtime-code-input-work",
        fixed_runtime_read_allowlist=_fixed_runtime_read_allowlist_strings(),
        sandbox_engine_path=str(sandbox_engine),
        sandbox_engine_binary_sha256=sandbox_sha256_before,
        command_engine_path=str(command_engine),
        command_engine_binary_sha256=command_sha256_before,
        probe_engine_path=str(probe_engine),
        probe_engine_binary_sha256=probe_sha256_before,
        argv=full_argv,
        stdin_mode="DEVNULL",
        close_fds=True,
        pass_fds=(),
        working_directory=str(work),
        clean_environment_sha256=environment_sha256,
        resource_limits=resource_limits,
        timeout_seconds=timeout_seconds,
        code_bundle=code_before,
        input_artifacts=inputs_before,
        expected_output_relative_paths={
            label: relative for label, (relative, _) in outputs.items()
        },
        output_artifacts=tuple(output_bindings),
        code_bundle_unchanged=code_unchanged,
        input_artifacts_unchanged=inputs_unchanged,
        engine_binaries_unchanged=engines_unchanged,
        probe_results=probes,
        command_executed=probes.all_probes_passed,
        exit_code=command_outcome.returncode,
        timed_out=command_outcome.timed_out,
        stdout_sha256=_sha256_bytes(command_outcome.stdout),
        stderr_sha256=_sha256_bytes(command_outcome.stderr),
        started_at_utc=started_at,
        finished_at_utc=finished_at,
        host_system="Darwin",
        host_release=platform.release(),
        host_machine=platform.machine(),
        formal_isolation_verified=formal_passed,
        executor_key_id=verifier.key_id,
        executor_public_key_base64=verifier.public_key_base64,
        executor_public_key_sha256=verifier.public_key_sha256,
        claim_boundary=(
            "This receipt proves one argv ran under the content-bound macOS sandbox profile "
            "and resource limits, with a fixed OS-runtime read allowlist plus only the declared "
            "code, inputs, and work directory. Active probes cover hidden-file reads, network, "
            "writes, fork, unlisted exec, an empty /dev/null stdin, and the environment "
            "allowlist; no extra file descriptors are passed by this launcher. It does not "
            "prove path immutability against a same-user swap-and-restore race, independent "
            "human key custody, or OCI hardware attestation. The macOS profile is not a full "
            "capability deny-default boundary; unenumerated Mach/XPC services remain governed "
            "by the host sandbox implementation."
        ),
    )
    signed = unsigned.model_copy(
        update={
            "executor_attestation": executor.sign(ATTESTATION_DOMAIN, _receipt_payload(unsigned))
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def verify_isolation_receipt_v0_9(
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
) -> IsolationExecutionReceiptV09:
    """Verify a positive receipt against verifier-supplied paths and policy."""

    unsigned_payload = dict(payload)
    stored = unsigned_payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned_payload) != stored:
        raise ValueError("isolation receipt content hash mismatch")
    record = IsolationExecutionReceiptV09.model_validate(unsigned_payload)
    if (
        record.executor_key_id != trusted_executor.key_id
        or record.executor_public_key_base64 != trusted_executor.public_key_base64
        or record.executor_public_key_sha256 != trusted_executor.public_key_sha256
    ):
        raise AttestationError("isolation receipt used an untrusted executor")
    trusted_executor.verify(
        ATTESTATION_DOMAIN,
        _receipt_payload(record),
        record.executor_attestation,
    )
    if record.formal_isolation_verified is not True or record.status != "ISOLATION_PASSED":
        raise ValueError("failed isolation receipt cannot authorize external execution")
    if platform.system() != "Darwin":
        raise ValueError("macOS isolation receipt cannot verify on a non-Darwin host")

    sandbox_engine = MACOS_SANDBOX_EXEC_PATH.resolve(strict=True)
    command_engine = command_engine_path.resolve(strict=True)
    probe_engine = MACOS_PROBE_PYTHON_PATH.resolve(strict=True)
    exec_probe_target = MACOS_EXEC_ESCAPE_TARGET_PATH.resolve(strict=True)
    fixed_runtime_read_paths = _fixed_runtime_read_paths()
    fixed_device_read_paths = _fixed_device_read_paths()
    work = working_directory.resolve(strict=True)
    _assert_disjoint_readonly_artifact(code_bundle_path, work)
    for path in input_artifact_paths.values():
        _assert_disjoint_readonly_artifact(path, work)
    outputs = _resolve_existing_output_paths(work, expected_output_relative_paths)
    expected_code = _artifact_binding("code_bundle", code_bundle_path)
    expected_inputs = tuple(
        _artifact_binding(label, input_artifact_paths[label])
        for label in sorted(input_artifact_paths)
    )
    expected_outputs = tuple(
        _artifact_binding(label, outputs[label][1]) for label in sorted(outputs)
    )
    expected_environment_sha256 = content_sha256(
        dict(sorted(clean_isolation_environment_v0_9(work).items()))
    )
    expected_profile_sha256 = _sha256_bytes(
        render_macos_sandbox_profile_v0_9(
            command_engine_path=command_engine,
            code_bundle_path=code_bundle_path,
            input_artifact_paths=input_artifact_paths,
            working_directory=work,
        ).encode("utf-8")
    )
    expected_relative_paths = {label: relative for label, (relative, _) in outputs.items()}
    expected_argv = (str(command_engine), *(str(item) for item in arguments))
    hidden_probe_path = Path(record.probe_results.hidden_probe_path)
    allowed_read_paths = (
        *fixed_runtime_read_paths,
        *fixed_device_read_paths,
        command_engine,
        probe_engine,
        exec_probe_target,
        code_bundle_path.resolve(strict=True),
        *(path.resolve(strict=True) for path in input_artifact_paths.values()),
        work,
    )
    if (
        not hidden_probe_path.is_absolute()
        or ".." in hidden_probe_path.parts
        or any(
            hidden_probe_path == allowed or hidden_probe_path.is_relative_to(allowed)
            for allowed in allowed_read_paths
        )
    ):
        raise ValueError("hidden-read probe was not outside every allowed read path")
    exact_bindings = all(
        (
            record.sandbox_engine_path == str(sandbox_engine),
            record.sandbox_engine_binary_sha256 == _file_sha256(sandbox_engine),
            record.command_engine_path == str(command_engine),
            record.command_engine_binary_sha256 == _file_sha256(command_engine),
            record.probe_engine_path == str(probe_engine),
            record.probe_engine_binary_sha256 == _file_sha256(probe_engine),
            record.probe_results.exec_probe_target_path == str(exec_probe_target),
            record.probe_results.exec_probe_target_binary_sha256 == _file_sha256(exec_probe_target),
            record.argv == expected_argv,
            record.stdin_mode == "DEVNULL",
            record.close_fds is True,
            not record.pass_fds,
            record.working_directory == str(work),
            record.clean_environment_sha256 == expected_environment_sha256,
            record.resource_limits == resource_limits,
            record.timeout_seconds == timeout_seconds,
            record.policy_template_sha256 == MACOS_POLICY_TEMPLATE_SHA256,
            record.rendered_profile_sha256 == expected_profile_sha256,
            record.fixed_runtime_read_allowlist == _fixed_runtime_read_allowlist_strings(),
            record.code_bundle == expected_code,
            record.input_artifacts == expected_inputs,
            record.expected_output_relative_paths == expected_relative_paths,
            record.output_artifacts == expected_outputs,
            record.host_system == platform.system(),
            record.host_release == platform.release(),
            record.host_machine == platform.machine(),
        )
    )
    if not exact_bindings:
        raise ValueError("isolation receipt differs from verifier-supplied execution bindings")
    return record


def _resolve_existing_output_paths(
    working_directory: Path,
    expected_output_relative_paths: Mapping[str, str | Path],
) -> dict[str, tuple[str, Path]]:
    if not expected_output_relative_paths:
        raise ValueError("isolation verifier requires at least one expected output")
    root = working_directory.resolve(strict=True)
    resolved: dict[str, tuple[str, Path]] = {}
    for label in sorted(expected_output_relative_paths):
        relative = Path(expected_output_relative_paths[label])
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ValueError("isolated output path must be a nonescaping relative path")
        target = (root / relative).resolve(strict=True)
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("isolated output path escapes the working directory") from exc
        if target.is_symlink():
            raise ValueError("isolated output may not be a symbolic link")
        resolved[label] = (relative.as_posix(), target)
    if len({target for _, target in resolved.values()}) != len(resolved):
        raise ValueError("isolated output paths must be unique")
    return resolved


def run_real_macos_sandbox_probe_v0_9() -> dict[str, Any]:
    """Execute an ephemeral end-to-end host probe for an escalated operator.

    The generated key is intentionally ephemeral, so this proves backend
    behavior only.  It is not an external-custody receipt for Gate B.
    """

    with tempfile.TemporaryDirectory(prefix="cpswm-real-sandbox-probe-") as directory:
        root = Path(directory)
        code = root / "code"
        inputs = root / "inputs"
        work = root / "work"
        code.mkdir()
        inputs.mkdir()
        work.mkdir()
        program = code / "probe_payload.py"
        input_path = inputs / "input.txt"
        program.write_text(
            "from pathlib import Path\n"
            "import json, sys\n"
            "value = Path(sys.argv[1]).read_text(encoding='utf-8')\n"
            "Path(sys.argv[2]).write_text(json.dumps({'value': value}), encoding='utf-8')\n",
            encoding="utf-8",
        )
        input_path.write_text("sandbox-ok", encoding="utf-8")
        output_path = work / "result.json"
        signer = Ed25519AttestationSigner.generate(key_id="ephemeral-real-sandbox-probe")
        receipt = run_macos_isolated_execution_v0_9(
            command_engine_path=MACOS_PROBE_PYTHON_PATH.resolve(strict=True),
            arguments=(str(program), str(input_path), str(output_path)),
            code_bundle_path=code,
            input_artifact_paths={"probe_input": input_path},
            working_directory=work,
            expected_output_relative_paths={"probe_output": "result.json"},
            executor=signer,
            timeout_seconds=20,
        )
        if receipt["formal_isolation_verified"] is not True:
            return {
                "protocol": REAL_PROBE_PROTOCOL_ID,
                "status": "FAILED",
                "evidence_scope": "ephemeral-backend-self-test-not-independent-custody",
                "isolation_receipt_content_sha256": receipt["content_sha256"],
                "probe_results": receipt["probe_results"],
                "candidate_exit_code": receipt["exit_code"],
                "candidate_stderr_sha256": receipt["stderr_sha256"],
            }
        verified = verify_isolation_receipt_v0_9(
            receipt,
            trusted_executor=signer.verifier(),
            command_engine_path=MACOS_PROBE_PYTHON_PATH.resolve(strict=True),
            arguments=(str(program), str(input_path), str(output_path)),
            code_bundle_path=code,
            input_artifact_paths={"probe_input": input_path},
            working_directory=work,
            expected_output_relative_paths={"probe_output": "result.json"},
            timeout_seconds=20,
        )
        return {
            "protocol": REAL_PROBE_PROTOCOL_ID,
            "status": "PASSED" if verified.formal_isolation_verified else "FAILED",
            "evidence_scope": "ephemeral-backend-self-test-not-independent-custody",
            "isolation_receipt_content_sha256": receipt["content_sha256"],
            "sandbox_engine_binary_sha256": verified.sandbox_engine_binary_sha256,
            "rendered_profile_sha256": verified.rendered_profile_sha256,
            "probe_results": verified.probe_results.model_dump(mode="json"),
            "output_content": json.loads(output_path.read_text(encoding="utf-8")),
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Structure-Two v0.9 isolation tools")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="run the ephemeral real macOS sandbox probe",
    )
    args = parser.parse_args(argv)
    if not args.probe:
        parser.error("--probe is required")
    report = run_real_macos_sandbox_probe_v0_9()
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":  # pragma: no cover - exercised by the escalated probe
    raise SystemExit(main())


__all__ = [
    "ATTESTATION_DOMAIN",
    "DEFAULT_RESOURCE_LIMITS",
    "MACOS_POLICY_ID",
    "MACOS_POLICY_TEMPLATE_SHA256",
    "MACOS_SANDBOX_EXEC_PATH",
    "OCI_CONTRACT_PROTOCOL_ID",
    "PROTOCOL_ID",
    "BoundedProcessOutcomeV09",
    "IsolationArtifactBindingV09",
    "IsolationExecutionReceiptV09",
    "IsolationProbeResultsV09",
    "IsolationResourceLimitsV09",
    "IsolationRunnerV09",
    "OCIIsolationContractV09",
    "clean_isolation_environment_v0_9",
    "main",
    "render_macos_sandbox_profile_v0_9",
    "run_macos_isolated_execution_v0_9",
    "run_real_macos_sandbox_probe_v0_9",
    "verify_isolation_receipt_v0_9",
]
