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
import json
from dataclasses import dataclass, field
from pathlib import Path

from .contracts import (
    ALL_MODULE_IDS,
    MATURITY_ORDER,
    EvidenceArtifactPayload,
    EvidenceKind,
    Maturity,
    ModuleEntry,
    ProgressLedger,
    RunReceipt,
)

_B1_MODULES = tuple(f"M{i:02d}" for i in range(5, 13))
_ALL_MODULES = tuple(f"M{i:02d}" for i in range(1, 33))

#: The three formal gates, frozen with their exact module topology and minimum
#: maturity.  Neither the JSON ledger nor the caller may change these.
_REQUIRED_GATE_SPECS: dict[str, dict[str, object]] = {
    "B1_SYNTHETIC_READINESS": {
        "module_ids": _B1_MODULES,
        "min_maturity": Maturity.SYNTHETIC_VERTICAL_SLICE,
    },
    "FORMAL_B1_REAL_VALIDATION": {
        "module_ids": _B1_MODULES,
        "min_maturity": Maturity.REAL_DATA_VALIDATED,
    },
    "STRUCTURE_ONE_COMPLETE": {
        "module_ids": _ALL_MODULES,
        "min_maturity": Maturity.REPLAY_VALIDATED,
    },
}

#: Allowed evidence schemas; an unknown schema is rejected.
_ALLOWED_EVIDENCE_SCHEMAS = frozenset(
    {
        "synthetic_report_json_v1",
        "replay_manifest_json_v1",
        "real_data_manifest_json_v1",
        "embodied_run_json_v1",
    }
)

#: Evidence kinds that must never point at a source/test file.
_RUNTIME_EVIDENCE_KINDS = frozenset(
    {EvidenceKind.REPLAY, EvidenceKind.REAL_DATA, EvidenceKind.EMBODIED}
)


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
        return (
            self.internally_consistent and bool(required) and all(gate.passed for gate in required)
        )

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

    _check_required_gates_present(ledger, report)
    _check_gate_shapes(ledger, report)
    _check_modules(ledger, by_id, repo_root, report)
    _check_evidence_dedup(ledger, report)
    _build_coverage_matrix(ledger, report)
    _check_gates(ledger, by_id, report)
    return report


def _check_required_gates_present(ledger: ProgressLedger, report: ValidationReport) -> None:
    by_gate_id = {gate.gate_id: gate for gate in ledger.gates}
    for gate_id in _REQUIRED_GATE_SPECS:
        if gate_id not in by_gate_id:
            report.errors.append(f"required gate {gate_id} is missing")
        elif not by_gate_id[gate_id].required:
            report.errors.append(f"required gate {gate_id} must be required=True")


def _check_gate_shapes(ledger: ProgressLedger, report: ValidationReport) -> None:
    by_gate_id = {gate.gate_id: gate for gate in ledger.gates}
    for gate_id, spec in _REQUIRED_GATE_SPECS.items():
        gate = by_gate_id.get(gate_id)
        if gate is None:
            continue
        expected_modules: tuple[str, ...] = spec["module_ids"]
        expected_maturity: Maturity = spec["min_maturity"]
        if gate.required_module_ids != expected_modules:
            report.errors.append(
                f"gate {gate_id} must require exactly {expected_modules}, "
                f"got {gate.required_module_ids}"
            )
        if gate.min_maturity != expected_maturity:
            report.errors.append(
                f"gate {gate_id} min_maturity must be {expected_maturity.value}, "
                f"got {gate.min_maturity.value}"
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
        target = repo_root / artifact.path
        if not target.is_file():
            report.errors.append(f"{entry.module_id}: evidence artifact missing: {artifact.path}")
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != artifact.content_sha256:
            report.errors.append(
                f"{entry.module_id}: evidence content hash mismatch for {artifact.path}"
            )
        if artifact.artifact_schema not in _ALLOWED_EVIDENCE_SCHEMAS:
            report.errors.append(
                f"{entry.module_id}: unknown evidence schema {artifact.artifact_schema!r}"
            )
        if artifact.kind in _RUNTIME_EVIDENCE_KINDS and artifact.path.endswith(".py"):
            report.errors.append(
                f"{entry.module_id}: {artifact.kind.value} evidence cannot be a .py file: "
                f"{artifact.path}"
            )
        _check_evidence_payload(entry, artifact, repo_root, report)
        _check_run_receipt(entry, artifact, repo_root, report)


def _check_evidence_payload(
    entry: ModuleEntry,
    artifact,
    repo_root: Path,
    report: ValidationReport,
) -> None:
    """Parse the artifact file and verify it actually attests this module."""

    target = repo_root / artifact.path
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        payload = EvidenceArtifactPayload.model_validate(raw)
    except Exception as error:
        report.errors.append(
            f"{entry.module_id}: evidence {artifact.path} does not parse as "
            f"{artifact.artifact_schema}: {error}"
        )
        return
    if entry.module_id not in payload.covered_module_ids and payload.module_id != entry.module_id:
        report.errors.append(
            f"{entry.module_id}: evidence {artifact.path} does not attest this module"
        )
    if payload.artifact_sha256 != artifact.content_sha256:
        report.errors.append(
            f"{entry.module_id}: evidence {artifact.path} artifact_sha256 does not match"
        )
    if payload.evidence_kind != artifact.kind:
        report.errors.append(
            f"{entry.module_id}: evidence {artifact.path} kind does not match ledger"
        )


def _check_run_receipt(
    entry: ModuleEntry,
    artifact,
    repo_root: Path,
    report: ValidationReport,
) -> None:
    """Verify the run receipt exists and binds this artifact's hash."""

    receipt_path = repo_root / artifact.run_receipt
    if not receipt_path.is_file():
        report.errors.append(f"{entry.module_id}: run receipt missing: {artifact.run_receipt}")
        return
    try:
        receipt = RunReceipt.model_validate(json.loads(receipt_path.read_text(encoding="utf-8")))
    except Exception as error:
        report.errors.append(
            f"{entry.module_id}: run receipt {artifact.run_receipt} does not parse: {error}"
        )
        return
    if receipt.artifact_sha256 != artifact.content_sha256:
        report.errors.append(
            f"{entry.module_id}: run receipt {artifact.run_receipt} does not bind "
            f"artifact hash for {artifact.path}"
        )


def _check_evidence_dedup(ledger: ProgressLedger, report: ValidationReport) -> None:
    """Reject one evidence file silently backing more than one module."""

    seen: dict[str, str] = {}
    for entry in ledger.modules:
        for artifact in entry.evidence_artifacts:
            previous = seen.get(artifact.path)
            if previous is not None:
                report.errors.append(
                    f"evidence {artifact.path} is claimed by both {previous} and {entry.module_id}"
                )
            else:
                seen[artifact.path] = entry.module_id


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
