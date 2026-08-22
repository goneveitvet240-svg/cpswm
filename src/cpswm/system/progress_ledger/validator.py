"""Progress ledger validator.

The validator performs *only* verification, never promotion:

* it checks that every referenced file/artifact exists;
* it detects contradictory claims (synthetic evidence posing as real
  validation, claims above the declared maturity, claim/forbidden collisions);
* it emits the coverage matrix and the BLOCK reasons for each gate;
* it does not upgrade maturity and does not choose a research route.

Gate ``B1`` must name exactly M05-M12 (never ATG-1).  Gate
``STRUCTURE_ONE_COMPLETE`` must cover exactly WS1-WS10 (a SHIFT or WS4-only
result cannot substitute for it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .contracts import (
    ALL_MODULE_IDS,
    ALL_WORKSTREAM_IDS,
    MATURITY_ORDER,
    EvidenceKind,
    Maturity,
    ModuleEntry,
    ProgressLedger,
)

_B1_MODULES = tuple(f"M{i:02d}" for i in range(5, 13))


@dataclass
class GateResult:
    gate_id: str
    passed: bool
    blockers: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "gate_id": self.gate_id,
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
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
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
        if gate.gate_id == "B1" and gate.required_module_ids != _B1_MODULES:
            report.errors.append(
                f"gate B1 must require exactly M05-M12, got {gate.required_module_ids}"
            )
        if (
            gate.gate_id == "STRUCTURE_ONE_COMPLETE"
            and tuple(gate.required_workstream_ids) != ALL_WORKSTREAM_IDS
        ):
            report.errors.append(
                "gate STRUCTURE_ONE_COMPLETE must cover exactly WS1-WS10, "
                f"got {gate.required_workstream_ids}"
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


def _check_maturity_evidence(
    entry: ModuleEntry,
    repo_root: Path,
    report: ValidationReport,
) -> None:
    maturity = entry.maturity
    order = MATURITY_ORDER[maturity]
    kinds = {artifact.kind for artifact in entry.evidence_artifacts}

    if order >= MATURITY_ORDER[Maturity.SYNTHETIC_VERTICAL_SLICE] and not entry.test_paths:
        report.errors.append(f"{entry.module_id}: {maturity.value} requires at least one test path")

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
            GateResult(gate_id=gate.gate_id, passed=not blockers, blockers=tuple(blockers))
        )


__all__ = [
    "GateResult",
    "ValidationReport",
    "validate_ledger",
]
