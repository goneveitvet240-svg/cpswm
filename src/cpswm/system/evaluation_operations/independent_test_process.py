"""Run one evidence-producing test in an isolated child process.

The receipt is signed by the parent-side authority and binds the exact argv,
working directory, sanitized environment, child PID, outputs and termination
state.  A candidate cannot promote an in-process function call into this type.
"""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Self

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, require_aware, utc_now
from cpswm.system.attestation import (
    DOMAIN_INDEPENDENT_PROCESS_RECEIPT,
    Attestation,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.reproducibility import content_sha256

INDEPENDENT_PROCESS_RECEIPT_VERSION = "independent-test-process@0.1"


class IndependentTestProcessReceipt(ContractModel):
    receipt_version: str = INDEPENDENT_PROCESS_RECEIPT_VERSION
    process_role: str = Field(min_length=1)
    command_argv: tuple[str, ...] = Field(min_length=1)
    working_directory: str = Field(min_length=1)
    environment_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_pid: int = Field(gt=0)
    child_pid: int = Field(gt=0)
    started_at: datetime
    finished_at: datetime
    wall_seconds: float = Field(ge=0.0)
    hard_timeout_seconds: float = Field(gt=0.0)
    timed_out: bool
    exit_code: int | None
    stdout_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stderr_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_artifact_sha256s: dict[str, str]
    attestation: Attestation | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def _aware_times(cls, value: datetime) -> datetime:
        return require_aware(value, "process timestamp")

    @model_validator(mode="after")
    def _receipt_semantics(self) -> Self:
        if self.receipt_version != INDEPENDENT_PROCESS_RECEIPT_VERSION:
            raise ValueError("unsupported independent-process receipt version")
        if self.child_pid == self.parent_pid:
            raise ValueError("independent test receipt cannot name the parent as the child")
        if self.finished_at < self.started_at:
            raise ValueError("independent test finish time precedes its start")
        if self.timed_out and self.exit_code == 0:
            raise ValueError("a timed-out process cannot report a successful exit")
        if not self.timed_out and self.exit_code is None:
            raise ValueError("a completed process requires an exit code")
        if any(
            len(value) != 64 or set(value) - set("0123456789abcdef")
            for value in self.output_artifact_sha256s.values()
        ):
            raise ValueError("output artifacts must use lowercase SHA-256 digests")
        return self

    @property
    def passed(self) -> bool:
        return not self.timed_out and self.exit_code == 0

    def attested_content(self) -> dict[str, object]:
        return attested_payload(self)

    @property
    def receipt_sha256(self) -> str:
        return content_sha256(self)


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_independent_test_process(
    command_argv: tuple[str, ...],
    *,
    process_role: str,
    working_directory: Path | str,
    signer: Ed25519AttestationSigner,
    hard_timeout_seconds: float,
    termination_grace_seconds: float = 2.0,
    environment: dict[str, str] | None = None,
    output_artifacts: tuple[Path | str, ...] = (),
) -> IndependentTestProcessReceipt:
    if not command_argv:
        raise ValueError("independent test command cannot be empty")
    if hard_timeout_seconds <= 0 or termination_grace_seconds < 0:
        raise ValueError("independent test timeouts are invalid")
    cwd = Path(working_directory).resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError("independent test working directory must be a directory")
    child_env = dict(environment or {})
    child_env.setdefault("PATH", os.environ.get("PATH", ""))
    environment_hash = content_sha256(dict(sorted(child_env.items())))
    resolved_outputs = tuple(
        (path if path.is_absolute() else cwd / path).resolve()
        for path in map(Path, output_artifacts)
    )
    for path in resolved_outputs:
        try:
            path.relative_to(cwd)
        except ValueError as exc:
            raise ValueError(
                "independent test output artifact must stay under its working tree"
            ) from exc
        if path.exists():
            raise FileExistsError(
                "independent test refuses to claim a pre-existing output artifact"
            )
    started_at = utc_now()
    start_clock = monotonic()
    process = subprocess.Popen(
        command_argv,
        cwd=cwd,
        env=child_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=hard_timeout_seconds)
    except subprocess.TimeoutExpired:
        leader_already_exited = process.poll() is not None
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=termination_grace_seconds)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        if leader_already_exited or process.returncode == 0:
            raise RuntimeError("independent test left a surviving descendant process") from None
    finished_at = utc_now()
    artifacts: dict[str, str] = {}
    for path in resolved_outputs:
        resolved_after = path.resolve(strict=True)
        try:
            relative = resolved_after.relative_to(cwd).as_posix()
        except ValueError as exc:
            raise ValueError(
                "independent test output artifact must stay under its working tree"
            ) from exc
        if not resolved_after.is_file():
            raise ValueError(f"independent test output artifact is missing: {relative}")
        artifacts[relative] = _digest_file(resolved_after)
    unsigned = IndependentTestProcessReceipt(
        process_role=process_role,
        command_argv=command_argv,
        working_directory=str(cwd),
        environment_sha256=environment_hash,
        parent_pid=os.getpid(),
        child_pid=process.pid,
        started_at=started_at,
        finished_at=finished_at,
        wall_seconds=monotonic() - start_clock,
        hard_timeout_seconds=hard_timeout_seconds,
        timed_out=timed_out,
        exit_code=process.returncode,
        stdout_sha256=hashlib.sha256(stdout).hexdigest(),
        stderr_sha256=hashlib.sha256(stderr).hexdigest(),
        output_artifact_sha256s=artifacts,
    )
    attestation = signer.sign(
        DOMAIN_INDEPENDENT_PROCESS_RECEIPT,
        unsigned.attested_content(),
    )
    return unsigned.model_copy(update={"attestation": attestation})


def verify_independent_test_process_receipt(
    receipt: IndependentTestProcessReceipt,
    *,
    verifier: Ed25519AttestationVerifier,
    require_passed: bool = True,
) -> IndependentTestProcessReceipt:
    receipt = IndependentTestProcessReceipt.model_validate(receipt.model_dump(mode="python"))
    verifier.verify(
        DOMAIN_INDEPENDENT_PROCESS_RECEIPT,
        receipt.attested_content(),
        receipt.attestation,
    )
    if require_passed and not receipt.passed:
        raise ValueError("independent test process did not pass")
    cwd = Path(receipt.working_directory)
    for relative, expected in receipt.output_artifact_sha256s.items():
        path = (cwd / relative).resolve()
        try:
            path.relative_to(cwd.resolve())
        except ValueError as exc:
            raise ValueError("receipt artifact escapes the independent working tree") from exc
        if not path.is_file() or _digest_file(path) != expected:
            raise ValueError("independent test output artifact no longer matches its receipt")
    return receipt


__all__ = [
    "INDEPENDENT_PROCESS_RECEIPT_VERSION",
    "IndependentTestProcessReceipt",
    "run_independent_test_process",
    "verify_independent_test_process_receipt",
]
