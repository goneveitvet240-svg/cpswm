#!/usr/bin/env python3
"""Execute the local engineering audit matrix and write a source-bound receipt."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT: Final = (
    ROOT / "benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/"
    "engineering_audit_receipt.json"
)
P0_MANIFEST: Final = ROOT / "benchmarks/p0_checkpoint/content_manifest_v0_3.json"
COMMANDS: Final = {
    "p5_evidence_current": (
        ".venv/bin/python",
        "apps/evaluation_runner/run_structure_two_evidence_repair.py",
        "--verify-current",
    ),
    "p5_evidence_history": (
        ".venv/bin/python",
        "apps/evaluation_runner/audit_structure_two_evidence_history.py",
        "--verify",
        "benchmarks/structure_two/evidence_entry_portability_2026_09_12/historical_source_audit_v0_3.json",
    ),
    "p0_adversarial_tests": (
        ".venv/bin/pytest",
        "-o",
        "addopts=",
        "-q",
        "--confcutdir=.",
        "tests/test_structure_two_trusted_ablation_authorization.py",
        "tests/test_structure_two_gate_b_v0_8_raw_formal_execution.py",
        "tests/test_structure_two_comparator_typed_dual_gate_b_v0_8.py",
        "tests/test_p0_checkpoint_manifest.py",
    ),
    "core_pytest": (
        ".venv/bin/pytest",
        "-o",
        "addopts=",
        "-p",
        "xdist.plugin",
        "-n",
        "auto",
        "--dist=worksteal",
        "-q",
        "--confcutdir=.",
        "--ignore=tests/test_structure_two_engineering_trust_checkpoint.py",
    ),
    "mypy_src": (".venv/bin/mypy", "src"),
    "ruff_lint": (".venv/bin/ruff", "check", "src", "tests", "apps"),
    "ruff_format": (".venv/bin/ruff", "format", "--check", "src", "tests", "apps"),
    "compileall": (".venv/bin/python", "-m", "compileall", "-q", "src", "apps", "tests"),
    "uv_frozen_offline_check": (
        "uv",
        "sync",
        "--frozen",
        "--offline",
        "--check",
        "--extra",
        "dev",
        "--no-cache",
    ),
    # Generated audit logs are outputs of this very command matrix. Excluding
    # them prevents an old failing log from reporting its own quoted whitespace
    # diagnostics forever. All source, tests, configs, manifests and receipts
    # remain inside the check.
    "git_diff_check": (
        "git",
        "diff",
        "--check",
        "--",
        ".",
        ":(exclude)benchmarks/structure_two/engineering_trust_checkpoint_2026_09_12_v0_3/"
        "engineering_audit_logs/*.log",
    ),
}
PYTEST_ENVIRONMENT_OVERRIDES: Final = {
    "PYTEST_ADDOPTS": "",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "PYTEST_PLUGINS": "",
    "PYTHONHASHSEED": "0",
    "PYTHONPATH": "",
}
COMMAND_ENVIRONMENT_OVERRIDES: Final = {
    "p0_adversarial_tests": PYTEST_ENVIRONMENT_OVERRIDES,
    "core_pytest": PYTEST_ENVIRONMENT_OVERRIDES,
}
TOOL_VERSION_COMMANDS: Final = {
    "pytest": (".venv/bin/pytest", "--version"),
    "mypy": (".venv/bin/mypy", "--version"),
    "ruff": (".venv/bin/ruff", "--version"),
    "git": ("git", "--version"),
    "uv": ("uv", "--version"),
}
CRITICAL_PYTHON_MODULES: Final = {
    "pytest_public": ("pytest", "pytest"),
    "pytest_engine": ("_pytest.config", "_pytest"),
    "pytest_xdist": ("xdist.plugin", "xdist"),
    "mypy_entrypoint": ("mypy.__main__", "mypy"),
}
SENSITIVE_ENV_ALLOWLIST: Final = (
    "PYTEST_ADDOPTS",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    "PYTEST_PLUGINS",
    "PYTHONHASHSEED",
    "PYTHONPATH",
    "COVERAGE_PROCESS_START",
    "MYPYPATH",
    "RUFF_CACHE_DIR",
    "UV_OFFLINE",
    "UV_FROZEN",
    "UV_NO_SYNC",
    "VIRTUAL_ENV",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_sha256(value: object) -> str:
    return _sha256_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def command_environment_binding(command_id: str) -> dict[str, dict[str, str]]:
    overrides = COMMAND_ENVIRONMENT_OVERRIDES.get(command_id, {})
    return {
        name: {
            "state": "forced",
            "value_sha256": _sha256_bytes(value.encode("utf-8")),
        }
        for name, value in sorted(overrides.items())
    }


def _command_environment(command_id: str) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(COMMAND_ENVIRONMENT_OVERRIDES.get(command_id, {}))
    return environment


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load audit dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON input is not an object: {path}")
    return payload


def _resolve_executable(executable: str, *, repository_root: Path = ROOT) -> Path:
    candidate = Path(executable)
    if candidate.is_absolute():
        unresolved = candidate
    elif len(candidate.parts) > 1:
        unresolved = repository_root / candidate
    else:
        located = shutil.which(executable)
        if located is None:
            raise ValueError(f"audit executable is not available: {executable}")
        unresolved = Path(located)
    try:
        resolved = unresolved.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError(f"audit executable does not exist: {executable}") from error
    if not resolved.is_file():
        raise ValueError(f"audit executable is not a regular file: {resolved}")
    return resolved


def command_executable_identity(
    argv: Sequence[str], *, repository_root: Path = ROOT
) -> dict[str, str]:
    if not argv:
        raise ValueError("audit command argv is empty")
    resolved = _resolve_executable(argv[0], repository_root=repository_root)
    invocation = (
        str((repository_root / argv[0]).absolute()) if "/" in argv[0] else shutil.which(argv[0])
    )
    if invocation is None:
        raise ValueError("audit invocation executable is unavailable")
    return {
        "invocation_executable": invocation,
        "resolved_executable": str(resolved),
        "executable_sha256": _sha256_file(resolved),
    }


def _normalise_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()


def _installed_distributions(
    interpreter: Path, *, repository_root: Path = ROOT
) -> list[dict[str, str]]:
    # Query a clean child interpreter so imports performed by checkpoint
    # verification cannot add a source-tree ``*.egg-info`` entry halfway
    # through the audit and manufacture a false environment drift.
    script = (
        "import importlib.metadata as m,json;"
        "print(json.dumps([[d.metadata.get('Name'),d.version] for d in m.distributions()]))"
    )
    completed = subprocess.run(
        (str(interpreter), "-I", "-c", script),
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    raw_rows = json.loads(completed.stdout)
    if not isinstance(raw_rows, list):
        raise ValueError("installed distribution inventory is malformed")
    rows: list[dict[str, str]] = []
    for raw in raw_rows:
        if (
            not isinstance(raw, list)
            or len(raw) != 2
            or not isinstance(raw[0], str)
            or not raw[0].strip()
            or not isinstance(raw[1], str)
        ):
            raise ValueError("installed distribution has no canonical name/version")
        rows.append(
            {
                "name": _normalise_distribution_name(raw[0].strip()),
                "version": raw[1],
            }
        )
    return sorted(rows, key=lambda row: (row["name"], row["version"]))


def _critical_python_module_bindings(
    interpreter: Path, *, repository_root: Path = ROOT
) -> dict[str, object]:
    script = r"""
import hashlib
import importlib
import json
import stat
import sys
from pathlib import Path

bindings = {}
for label, (module_name, package_name) in sorted(json.loads(sys.argv[1]).items()):
    module = importlib.import_module(module_name)
    package = importlib.import_module(package_name)
    if module.__file__ is None or not hasattr(package, "__path__"):
        raise RuntimeError(f"critical module has no auditable file/package path: {module_name}")
    module_path = Path(module.__file__).resolve(strict=True)
    package_root = Path(next(iter(package.__path__))).resolve(strict=True)
    aggregate = hashlib.sha256()
    file_count = 0
    for path in sorted(package_root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(package_root)
        if path.is_symlink():
            raise RuntimeError(f"critical package contains symlink: {package_name}/{relative}")
        if "__pycache__" in relative.parts or path.suffix.casefold() in {".pyc", ".pyo"}:
            continue
        mode = path.stat(follow_symlinks=False).st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise RuntimeError(
                f"critical package contains non-regular file: {package_name}/{relative}"
            )
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        relative_string = relative.as_posix()
        aggregate.update(relative_string.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
        file_count += 1
    bindings[label] = {
        "module_name": module_name,
        "resolved_module_file": str(module_path),
        "module_file_sha256": hashlib.sha256(module_path.read_bytes()).hexdigest(),
        "package_name": package_name,
        "resolved_package_root": str(package_root),
        "package_file_count": file_count,
        "package_content_sha256": aggregate.hexdigest(),
    }
print(json.dumps(bindings, sort_keys=True, separators=(",", ":")))
"""
    completed = subprocess.run(
        (
            str(interpreter),
            "-I",
            "-c",
            script,
            json.dumps(CRITICAL_PYTHON_MODULES, sort_keys=True, separators=(",", ":")),
        ),
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    bindings = json.loads(completed.stdout)
    if not isinstance(bindings, dict) or set(bindings) != set(CRITICAL_PYTHON_MODULES):
        raise ValueError("critical Python module binding inventory is malformed")
    return bindings


def _tool_version(
    argv: Sequence[str],
    *,
    repository_root: Path = ROOT,
    environment_overrides: Mapping[str, str] | None = None,
) -> dict[str, object]:
    identity = command_executable_identity(argv, repository_root=repository_root)
    version_argv = (identity["resolved_executable"], *argv[1:])
    environment = dict(os.environ)
    environment.update(environment_overrides or {})
    completed = subprocess.run(
        version_argv,
        cwd=repository_root,
        check=True,
        capture_output=True,
        env=environment,
    )
    version_bytes = completed.stdout + completed.stderr
    return {
        "version_argv": list(argv),
        **identity,
        "version": version_bytes.decode("utf-8", errors="replace").strip(),
        "version_output_sha256": _sha256_bytes(version_bytes),
    }


def _toolchain_files_from_manifest(
    source_manifest: Mapping[str, Any], *, repository_root: Path = ROOT
) -> list[dict[str, str]]:
    scopes = source_manifest.get("scopes")
    if not isinstance(scopes, Mapping):
        raise ValueError("source manifest scopes are missing")
    scope = scopes.get("toolchain_contract")
    if not isinstance(scope, Mapping) or not isinstance(scope.get("files"), list):
        raise ValueError("source manifest toolchain contract is missing")
    rows: list[dict[str, str]] = []
    for raw in scope["files"]:
        if not isinstance(raw, Mapping):
            raise ValueError("source manifest toolchain entry is malformed")
        relative = raw.get("path")
        expected_hash = raw.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            raise ValueError("source manifest toolchain entry fields are malformed")
        unresolved = repository_root / relative
        if unresolved.is_symlink():
            raise ValueError(f"toolchain file is a refused symlink: {relative}")
        path = unresolved.resolve()
        if not path.is_relative_to(repository_root.resolve()) or not path.is_file():
            raise ValueError(f"toolchain file is unavailable or unsafe: {relative}")
        current_hash = _sha256_file(path)
        if current_hash != expected_hash:
            raise ValueError(f"toolchain file drifted from source manifest: {relative}")
        rows.append({"path": relative, "sha256": current_hash})
    return rows


def build_execution_environment_fingerprint(
    source_manifest: Mapping[str, Any], *, repository_root: Path = ROOT
) -> dict[str, object]:
    interpreter_invocation = Path(sys.executable).absolute()
    if not interpreter_invocation.is_file():
        raise ValueError("current Python interpreter invocation path is unavailable")
    resolved_interpreter = interpreter_invocation.resolve(strict=True)
    implementation_version = sys.implementation.version
    distributions = _installed_distributions(
        interpreter_invocation, repository_root=repository_root
    )
    sensitive_environment: dict[str, dict[str, str]] = {}
    for name in SENSITIVE_ENV_ALLOWLIST:
        if name == "VIRTUAL_ENV":
            # Shell activation and ``uv run`` differ only in whether they expose
            # VIRTUAL_ENV. Bind the effective environment path instead. A
            # caller-selected different environment still changes this digest.
            effective_environment = Path(os.environ.get(name, sys.prefix)).resolve()
            sensitive_environment[name] = {
                "state": "effective",
                "value_sha256": _sha256_bytes(str(effective_environment).encode("utf-8")),
            }
        elif name not in os.environ:
            sensitive_environment[name] = {"state": "absent"}
        else:
            sensitive_environment[name] = {
                "state": "present",
                "value_sha256": _sha256_bytes(os.environ[name].encode("utf-8")),
            }
    payload: dict[str, object] = {
        "protocol": "structure-two-local-execution-environment@1.0",
        "authority": "CURRENT_LOCAL_TOOLCHAIN_STATE_ONLY",
        "python": {
            "implementation": sys.implementation.name,
            "version": platform.python_version(),
            "full_version": sys.version,
            "implementation_version": {
                "major": implementation_version.major,
                "minor": implementation_version.minor,
                "micro": implementation_version.micro,
                "releaselevel": implementation_version.releaselevel,
                "serial": implementation_version.serial,
            },
            "cache_tag": sys.implementation.cache_tag,
            "soabi": sysconfig.get_config_var("SOABI"),
            "platform": platform.platform(),
            # Bind the canonical interpreter rather than the venv entry-point alias.
            # ``python``, ``python3``, and a console-script shebang may be distinct
            # symlinks to the same executable; treating those aliases as different
            # environments manufactures drift without strengthening the trust claim.
            "interpreter_invocation_path": str(resolved_interpreter),
            "interpreter_invocation_path_policy": "CANONICAL_RESOLVED_PATH",
            "resolved_interpreter": str(resolved_interpreter),
            "interpreter_sha256": _sha256_file(resolved_interpreter),
        },
        "tools": {
            name: _tool_version(
                argv,
                repository_root=repository_root,
                environment_overrides=(PYTEST_ENVIRONMENT_OVERRIDES if name == "pytest" else None),
            )
            for name, argv in TOOL_VERSION_COMMANDS.items()
        },
        "critical_python_modules": _critical_python_module_bindings(
            interpreter_invocation, repository_root=repository_root
        ),
        "toolchain_files": _toolchain_files_from_manifest(
            source_manifest, repository_root=repository_root
        ),
        "installed_distributions": {
            "sort_key": "normalised_name,version",
            "count": len(distributions),
            "entries": distributions,
            "digest_sha256": _canonical_sha256(distributions),
        },
        "sensitive_environment_allowlist": sensitive_environment,
        "claim_boundary": (
            "This fingerprint describes only the current local interpreter, executables, "
            "toolchain files, installed distributions, and allowlisted effective environment "
            "state. "
            "It is not a hermetic build attestation or independently held evidence."
        ),
    }
    payload["content_sha256"] = _canonical_sha256(payload)
    return payload


def verify_execution_environment_fingerprint(
    stored: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
    *,
    repository_root: Path = ROOT,
) -> None:
    unsigned = dict(stored)
    stored_hash = unsigned.pop("content_sha256", None)
    if stored_hash != _canonical_sha256(unsigned):
        raise ValueError("execution environment fingerprint content hash mismatch")
    fresh = build_execution_environment_fingerprint(
        source_manifest, repository_root=repository_root
    )
    if stored != fresh:
        raise ValueError("execution environment fingerprint is stale for the current local state")


def _verified_manifest_snapshot() -> tuple[dict[str, Any], str, str]:
    manifest_module = _load(
        "structure_two_p0_manifest_for_receipt",
        ROOT / "apps/evaluation_runner/generate_p0_checkpoint_manifest.py",
    )
    stored = _load_json_object(P0_MANIFEST)
    manifest_module.verify_manifest_snapshot(stored)
    fresh = manifest_module.build_manifest(repository_root=ROOT)
    if stored != fresh:
        raise ValueError("stored P0 manifest is stale before or after audit execution")
    manifest_hash = stored.get("manifest_sha256")
    if not isinstance(manifest_hash, str):
        raise ValueError("stored P0 manifest hash is missing")
    return stored, _sha256_file(P0_MANIFEST), manifest_hash


def _execute_audit_command(
    command_id: str, argv: Sequence[str]
) -> tuple[dict[str, str], str, str, subprocess.CompletedProcess[bytes]]:
    identity = command_executable_identity(argv, repository_root=ROOT)
    start = _now()
    completed = subprocess.run(
        (identity["invocation_executable"], *argv[1:]),
        cwd=ROOT,
        capture_output=True,
        check=False,
        env=_command_environment(command_id),
    )
    return identity, start, _now(), completed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError("engineering audit receipt output must remain inside the repository")
    log_dir = output.parent / "engineering_audit_logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    manifest_pre, manifest_file_hash_pre, manifest_hash_pre = _verified_manifest_snapshot()
    environment_pre = build_execution_environment_fingerprint(manifest_pre, repository_root=ROOT)
    environment_hash_pre = environment_pre["content_sha256"]
    runs: list[dict[str, object]] = []
    # These two read-only validations have disjoint outputs and fixed inputs.
    # Capture timestamps inside their workers; retain the declared receipt order.
    with ThreadPoolExecutor(max_workers=2) as pool:
        parallel = {
            name: pool.submit(_execute_audit_command, name, COMMANDS[name])
            for name in ("p5_evidence_current", "p5_evidence_history")
        }
        for command_id, argv in COMMANDS.items():
            executable_identity, start, end, completed = (
                parallel[command_id].result()
                if command_id in parallel
                else _execute_audit_command(command_id, argv)
            )
            stdout_path = log_dir / f"{command_id}.stdout.log"
            stderr_path = log_dir / f"{command_id}.stderr.log"
            stdout_path.write_bytes(completed.stdout)
            stderr_path.write_bytes(completed.stderr)
            runs.append(
                {
                    "command_id": command_id,
                    "argv": list(argv),
                    "source_manifest_sha256": manifest_hash_pre,
                    "source_manifest_file_sha256": manifest_file_hash_pre,
                    "execution_environment_sha256": environment_hash_pre,
                    "environment_overrides": command_environment_binding(command_id),
                    "cwd": str(ROOT.resolve()),
                    **executable_identity,
                    "start_timestamp": start,
                    "end_timestamp": end,
                    "exit_code": completed.returncode,
                    "stdout_path": stdout_path.relative_to(ROOT).as_posix(),
                    "stdout_sha256": _sha256_file(stdout_path),
                    "stderr_path": stderr_path.relative_to(ROOT).as_posix(),
                    "stderr_sha256": _sha256_file(stderr_path),
                }
            )
            print(f"{command_id}={completed.returncode}", flush=True)

    manifest_post, manifest_file_hash_post, manifest_hash_post = _verified_manifest_snapshot()
    environment_post = build_execution_environment_fingerprint(manifest_post, repository_root=ROOT)
    if manifest_hash_pre != manifest_hash_post or manifest_file_hash_pre != manifest_file_hash_post:
        raise ValueError("P0 manifest changed during audit execution")
    if environment_pre != environment_post:
        raise ValueError("local execution environment changed during audit execution")

    payload: dict[str, object] = {
        "protocol": "structure-two-engineering-audit-receipt@1.1",
        "authority": "CURRENT_LOCAL_TOOLCHAIN_STATE_ONLY",
        "source_manifest_path": P0_MANIFEST.relative_to(ROOT).as_posix(),
        "source_manifest_file_sha256": manifest_file_hash_pre,
        "source_manifest_sha256": manifest_hash_pre,
        "pre_execution_source_manifest_file_sha256": manifest_file_hash_pre,
        "pre_execution_source_manifest_sha256": manifest_hash_pre,
        "post_execution_source_manifest_file_sha256": manifest_file_hash_post,
        "post_execution_source_manifest_sha256": manifest_hash_post,
        "pre_execution_environment": environment_pre,
        "post_execution_environment": environment_post,
        "command_runs": runs,
        "all_commands_passed": all(run["exit_code"] == 0 for run in runs),
        "recorded_execution_authenticity_established": False,
        "hermetic_toolchain_established": False,
        "independent_custody_established": False,
        "claim_boundary": (
            "This receipt binds local command outputs to the current code, config, data/schema, "
            "split-manifest, test source, benchmark test-fixture, and toolchain manifest plus the "
            "freshly observed local execution environment. Its unkeyed, caller-held hashes do not "
            "independently prove that the recorded commands ran. It describes only a current-local "
            "recorded audit, not a hermetic build attestation, independent custody, historical "
            "authenticity, or external-validity claim."
        ),
    }
    payload["content_sha256"] = _canonical_sha256(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if payload["all_commands_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
