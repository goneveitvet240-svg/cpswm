"""Progress ledger validator.

The validator performs *only* verification, never promotion:

* it checks that every referenced file/artifact exists, and that evidence
  content hashes match when declared;
* it detects contradictory claims (synthetic evidence posing as real
  validation, claims above the declared maturity, claim/forbidden collisions);
* ``contract_only`` requires an actual contract implementation plus a
  dedicated test;
* it emits the coverage matrix and the BLOCK reasons for each gate;
* it separates ``internally_consistent`` (no errors) from
  ``required_gates_passed`` (every required gate is green);
* it does not upgrade maturity and does not choose a research route.

Gates ``B1_SYNTHETIC_READINESS`` and ``FORMAL_B1_REAL_VALIDATION`` must each
name exactly M05-M12 (never ATG-1).  Gate ``STRUCTURE_ONE_COMPLETE`` must
cover every one of M01-M32 (a WS1-WS10 or SHIFT-only result cannot substitute).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .contracts import (
    ALL_MODULE_IDS,
    MATURITY_ORDER,
    EvidenceKind,
    Maturity,
    ModuleEntry,
    ProgressLedger,
)

_B1_MODULES = tuple(f"M{i:02d}" for i in range(5, 13))
_ALL_MODULES = tuple(f"M{i:02d}" for i in range(1, 33))


@dataclass
class GateResult:
    gate_id: str
    passed: bool
    required: bool = True
    blockers: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "gate_id": self.gate_id,
            "required": self.required,
            "passed": self.passed,
            "blockers": list(self.blockers),
        }


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    gate_results: list[GateResult] = field(default_factory=list)
    coverage_matrix: dict[str, list[str]] = field(default_factory=dict)

    @property
    def internally_consistent(self) -> bool:
        return not self.errors

    @property
    def required_gates_passed(self) -> bool:
        required = [gate for gate in self.gate_results if gate.required]
        return bool(required) and all(gate.passed for gate in required)

    def as_dict(self) -> dict[str, object]:
        return {
            "internally_consistent": self.internally_consistent,
            "required_gates_passed": self.required_gates_passed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "gates": [gate.as_dict() for gate in self.gate_results],
            "coverage_matrix": dict(self.coverage_matrix),
        }


def _exists(repo_root: Path, path: str) -> bool:
    return (repo_root / path).exists()


def validate_ledger(ledger: ProgressLedger, repo_root: Path) -> ValidationReport:
    report = ValidationReport()
    by_id = {item.module_id: item for item in ledger.modules}

    _check_gate_shapes(ledger, report)
    _check_modules(ledger, by_id, repo_root, report)
    _build_coverage_matrix(ledger, report)
    _check_gates(ledger, by_id, report)
    return report


def _check_gate_shapes(ledger: ProgressLedger, report: ValidationReport) -> None:
    for gate in ledger.gates:
        if (
            gate.gate_id in {"B1_SYNTHETIC_READINESS", "FORMAL_B1_REAL_VALIDATION"}
            and gate.required_module_ids != _B1_MODULES
        ):
            report.errors.append(
                f"gate {gate.gate_id} must require exactly M05-M12, got {gate.required_module_ids}"
            )
        if gate.gate_id == "STRUCTURE_ONE_COMPLETE" and gate.required_module_ids != _ALL_MODULES:
            report.errors.append(
                "gate STRUCTURE_ONE_COMPLETE must cover exactly M01-M32, "
                f"got {gate.required_module_ids}"
            )


def _check_modules(
    ledger: ProgressLedger,
    by_id: dict[str, ModuleEntry],
    repo_root: Path,
    report: ValidationReport,
) -> None:
    present_ids = set(by_id)
    missing = set(ALL_MODULE_IDS) - present_ids
    for module_id in sorted(missing):
        report.errors.append(f"module {module_id} is missing from the ledger")

    for entry in ledger.modules:
        _check_paths(entry, repo_root, report)
        _check_evidence_content(entry, repo_root, report)
        _check_maturity_evidence(entry, repo_root, report)
        _check_claims(entry, report)


def _check_paths(entry: ModuleEntry, repo_root: Path, report: ValidationReport) -> None:
    for path in entry.implementation_paths:
        if not _exists(repo_root, path):
            report.errors.append(f"{entry.module_id}: implementation path missing: {path}")
    for path in entry.test_paths:
        if not _exists(repo_root, path):
            report.errors.append(f"{entry.module_id}: test path missing: {path}")
    for artifact in entry.evidence_artifacts:
        if not _exists(repo_root, artifact.path):
            report.errors.append(f"{entry.module_id}: evidence artifact missing: {artifact.path}")


def _check_evidence_content(
    entry: ModuleEntry,
    repo_root: Path,
    report: ValidationReport,
) -> None:
    """Verify declared evidence content hashes against the actual file bytes."""

    for artifact in entry.evidence_artifacts:
        if artifact.content_sha256 is None:
            continue
        target = repo_root / artifact.path
        if not target.is_file():
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != artifact.content_sha256:
            report.errors.append(
                f"{entry.module_id}: evidence content hash mismatch for {artifact.path}"
            )


def _check_maturity_evidence(
    entry: ModuleEntry,
    repo_root: Path,
    report: ValidationReport,
) -> None:
    maturity = entry.maturity
    order = MATURITY_ORDER[maturity]
    kinds = {artifact.kind for artifact in entry.evidence_artifacts}

    if maturity == Maturity.ABSENT:
        if entry.implementation_paths or entry.test_paths:
            report.errors.append(
                f"{entry.module_id}: absent cannot reference implementations or tests"
            )
        return

    # contract_only and above require an actual contract implementation plus a
    # dedicated test; a documentation-only module cannot be contract_only.
    if not entry.implementation_paths:
        report.errors.append(
            f"{entry.module_id}: {maturity.value} requires at least one implementation path"
        )
    if not entry.test_paths:
        report.errors.append(
            f"{entry.module_id}: {maturity.value} requires at least one dedicated test path"
        )

    if order >= MATURITY_ORDER[Maturity.REPLAY_VALIDATED] and EvidenceKind.REPLAY not in kinds:
        report.errors.append(f"{entry.module_id}: {maturity.value} requires replay evidence")

    if (
        order >= MATURITY_ORDER[Maturity.REAL_DATA_VALIDATED]
        and EvidenceKind.REAL_DATA not in kinds
    ):
        report.errors.append(f"{entry.module_id}: {maturity.value} requires real-data evidence")

    if order >= MATURITY_ORDER[Maturity.EMBODIED_VALIDATED] and EvidenceKind.EMBODIED not in kinds:
        report.errors.append(f"{entry.module_id}: {maturity.value} requires embodied evidence")

    # Synthetic evidence must not be presented as real/embodied validation.
    real_or_embodied = {EvidenceKind.REAL_DATA, EvidenceKind.EMBODIED}
    if order >= MATURITY_ORDER[Maturity.REAL_DATA_VALIDATED] and not (kinds & real_or_embodied):
        report.errors.append(
            f"{entry.module_id}: {maturity.value} claims real/embodied validation "
            "but only synthetic evidence is present"
        )

    if maturity == Maturity.CONTRACT_ONLY and kinds & {
        EvidenceKind.REAL_DATA,
        EvidenceKind.EMBODIED,
    }:
        report.errors.append(
            f"{entry.module_id}: contract_only cannot carry real/embodied evidence"
        )


def _check_claims(entry: ModuleEntry, report: ValidationReport) -> None:
    maturity = entry.maturity
    order = MATURITY_ORDER[maturity]
    forbidden = set(entry.forbidden_claims)
    for claim in entry.allowed_claims:
        if claim in forbidden:
            report.errors.append(
                f"{entry.module_id}: claim {claim!r} is both allowed and forbidden"
            )
        lowered = claim.lower()
        if order < MATURITY_ORDER[Maturity.REAL_DATA_VALIDATED] and "real" in lowered:
            report.errors.append(f"{entry.module_id}: claim {claim!r} exceeds {maturity.value}")
        if order < MATURITY_ORDER[Maturity.EMBODIED_VALIDATED] and "embodied" in lowered:
            report.errors.append(f"{entry.module_id}: claim {claim!r} exceeds {maturity.value}")
        if order <= MATURITY_ORDER[Maturity.CONTRACT_ONLY] and (
            "implemented system" in lowered or "implemented_system" in lowered
        ):
            report.errors.append(
                f"{entry.module_id}: claim {claim!r} describes a full system above {maturity.value}"
            )


def _build_coverage_matrix(ledger: ProgressLedger, report: ValidationReport) -> None:
    matrix: dict[str, list[str]] = {module_id: [] for module_id in ALL_MODULE_IDS}
    for entry in ledger.modules:
        matrix[entry.module_id] = list(entry.workstream_ids)
    report.coverage_matrix = matrix


def _check_gates(
    ledger: ProgressLedger,
    by_id: dict[str, ModuleEntry],
    report: ValidationReport,
) -> None:
    for gate in ledger.gates:
        blockers: list[str] = []
        min_order = MATURITY_ORDER[gate.min_maturity]

        for module_id in gate.required_module_ids:
            entry = by_id.get(module_id)
            if entry is None:
                blockers.append(f"module {module_id} is missing")
                continue
            if MATURITY_ORDER[entry.maturity] < min_order:
                blockers.append(
                    f"{module_id} is {entry.maturity.value}, below {gate.min_maturity.value}"
                )

        for workstream in gate.required_workstream_ids:
            members = [
                entry
                for entry in ledger.modules
                if workstream in entry.workstream_ids
                and MATURITY_ORDER[entry.maturity] >= min_order
            ]
            if not members:
                blockers.append(
                    f"workstream {workstream} has no module at or above {gate.min_maturity.value}"
                )

        report.gate_results.append(
            GateResult(
                gate_id=gate.gate_id,
                passed=not blockers,
                required=gate.required,
                blockers=tuple(blockers),
            )
        )


__all__ = [
    "GateResult",
    "ValidationReport",
    "validate_ledger",
]
