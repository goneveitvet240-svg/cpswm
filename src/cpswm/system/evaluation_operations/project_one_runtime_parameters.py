"""Runtime receipts and fail-closed unused-knob detection for project one."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass

from cpswm.system.reproducibility import content_sha256

from .project_one_methods import ProjectOneMethod


class UnusedProjectOneParameterError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProjectOneRuntimeParameterBinding:
    parameter: str
    target_path: str
    configured_value: object
    runtime_value: object
    runtime_binding_sha256: str


@dataclass(frozen=True, slots=True)
class ProjectOneRuntimeParameterReceipt:
    method: str
    method_config_hash: str
    bindings: tuple[ProjectOneRuntimeParameterBinding, ...]
    receipt_sha256: str


def _find_key(
    payload: Mapping[str, object], name: str, prefix: str = ""
) -> list[tuple[str, object]]:
    found: list[tuple[str, object]] = []
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        if key == name:
            found.append((path, value))
        if isinstance(value, Mapping):
            found.extend(_find_key(value, name, path))
    return found


def build_project_one_runtime_parameter_receipt(
    method: ProjectOneMethod,
    declared_parameters: Mapping[str, object],
) -> ProjectOneRuntimeParameterReceipt:
    """Prove every tuned field exists with the configured value at runtime."""

    payload = dict(method.config_payload())
    bindings: list[ProjectOneRuntimeParameterBinding] = []
    for name, configured in sorted(declared_parameters.items()):
        matches = _find_key(payload, name)
        exact = [(path, value) for path, value in matches if value == configured]
        if len(exact) != 1:
            raise UnusedProjectOneParameterError(
                f"parameter {name!r} has {len(exact)} exact runtime bindings; expected one"
            )
        path, runtime_value = exact[0]
        bindings.append(
            ProjectOneRuntimeParameterBinding(
                parameter=name,
                target_path=path,
                configured_value=configured,
                runtime_value=runtime_value,
                runtime_binding_sha256=content_sha256(
                    {"method": method.name, "path": path, "value": runtime_value}
                ),
            )
        )
    frozen_bindings = tuple(bindings)
    hash_payload = {
        "method": method.name,
        "method_config_hash": method.config_hash(),
        "bindings": [asdict(item) for item in frozen_bindings],
    }
    return ProjectOneRuntimeParameterReceipt(
        method=method.name,
        method_config_hash=method.config_hash(),
        bindings=frozen_bindings,
        receipt_sha256=content_sha256(hash_payload),
    )


__all__ = [
    "ProjectOneRuntimeParameterBinding",
    "ProjectOneRuntimeParameterReceipt",
    "UnusedProjectOneParameterError",
    "build_project_one_runtime_parameter_receipt",
]
