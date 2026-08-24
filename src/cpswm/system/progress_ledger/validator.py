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
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from cpswm.system.attestation import (
    DOMAIN_RUN_RECEIPT,
    AttestationAuthority,
    AttestationError,
)

from .contracts import (
    ALL_MODULE_IDS,
    ALL_WORKSTREAM_IDS,
    MATURITY_ORDER,
    EvidenceArtifact,
    EvidenceArtifactPayload,
    EvidenceKind,
    Maturity,
    ModuleEntry,
    ProgressLedger,
    RunReceipt,
    code_snapshot_digest,
)

_B1_MODULES = tuple(f"M{i:02d}" for i in range(5, 13))
_ALL_MODULES = tuple(f"M{i:02d}" for i in range(1, 33))

#: The three formal gates, frozen with their exact module topology and minimum
#: maturity.  Neither the JSON ledger nor the caller may change these.
_REQUIRED_GATE_MODULES: dict[str, tuple[str, ...]] = {
    "B1_SYNTHETIC_READINESS": _B1_MODULES,
    "FORMAL_B1_REAL_VALIDATION": _B1_MODULES,
    "STRUCTURE_ONE_COMPLETE": _ALL_MODULES,
}
_REQUIRED_GATE_MATURITIES: dict[str, Maturity] = {
    "B1_SYNTHETIC_READINESS": Maturity.SYNTHETIC_VERTICAL_SLICE,
    "FORMAL_B1_REAL_VALIDATION": Maturity.REAL_DATA_VALIDATED,
    "STRUCTURE_ONE_COMPLETE": Maturity.REPLAY_VALIDATED,
}

#: Frozen workstream topology.  ``STRUCTURE_ONE_COMPLETE`` means all ten
#: workstreams; deleting nine of them from the JSON must not make it easier to
#: pass.  The module gates deliberately name no workstream.
_REQUIRED_GATE_WORKSTREAMS: dict[str, tuple[str, ...]] = {
    "B1_SYNTHETIC_READINESS": (),
    "FORMAL_B1_REAL_VALIDATION": (),
    "STRUCTURE_ONE_COMPLETE": ALL_WORKSTREAM_IDS,
}

#: Frozen module -> workstream mapping.  Without this, a gate that requires
#: "one module at or above X in every workstream" is satisfiable by moving a
#: mature module into whichever workstream is short, in the JSON, for free.
_FROZEN_MODULE_WORKSTREAMS: dict[str, tuple[str, ...]] = {
    "M01": (),
    "M02": (),
    "M03": (),
    "M04": (),
    "M05": ("WS1",),
    "M06": ("WS1",),
    "M07": ("WS1",),
    "M08": ("WS1",),
    "M09": ("WS1",),
    "M10": ("WS1", "WS2"),
    "M11": ("WS1", "WS2"),
    "M12": ("WS1",),
    "M13": ("WS2",),
    "M14": ("WS1", "WS2", "WS3"),
    "M15": ("WS2", "WS3"),
    "M16": ("WS2", "WS6"),
    "M17": ("WS4", "WS5"),
    "M18": ("WS6", "WS8"),
    "M19": ("WS5", "WS7"),
    "M20": ("WS3", "WS8"),
    "M21": ("WS3", "WS8"),
    "M22": ("WS3", "WS8"),
    "M23": ("WS9",),
    "M24": ("WS9",),
    "M25": ("WS9",),
    "M26": ("WS9",),
    "M27": ("WS1", "WS9"),
    "M28": ("WS10",),
    "M29": ("WS10",),
    "M30": ("WS10",),
    "M31": ("WS10",),
    "M32": ("WS10",),
}

#: A maturity at or above this level claims an execution against data, so its
#: evidence must be attested by the authority rather than declared.
_ATTESTATION_REQUIRED_FROM = Maturity.REPLAY_VALIDATED

#: The evidence kind each attested maturity level must actually produce.
_KIND_FOR_MATURITY: dict[Maturity, EvidenceKind] = {
    Maturity.REPLAY_VALIDATED: EvidenceKind.REPLAY,
    Maturity.REAL_DATA_VALIDATED: EvidenceKind.REAL_DATA,
    Maturity.EMBODIED_VALIDATED: EvidenceKind.EMBODIED,
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

#: The only result statuses that may attest a maturity.  A field that merely
#: exists is not evidence: ``"failed"`` must never satisfy a gate.
_PASSING_RESULT_STATUSES = frozenset({"passed", "pass", "succeeded", "success"})

#: Which schema each evidence kind must declare, so a synthetic report cannot
#: be filed under a replay or real-data schema.
_SCHEMA_BY_KIND: dict[EvidenceKind, str] = {
    EvidenceKind.SYNTHETIC: "synthetic_report_json_v1",
    EvidenceKind.REPLAY: "replay_manifest_json_v1",
    EvidenceKind.REAL_DATA: "real_data_manifest_json_v1",
    EvidenceKind.EMBODIED: "embodied_run_json_v1",
}

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


def _contained_path(repo_root: Path, path: str) -> Path | None:
    """Resolve ``path`` inside ``repo_root``, or ``None`` if it escapes.

    ``a/../b``, an absolute path and a symlink that leaves the tree all defeat
    string comparison, so containment and de-duplication both use the resolved
    path rather than the declared spelling.
    """

    candidate = Path(path)
    if candidate.is_absolute():
        return None
    try:
        resolved = (repo_root / candidate).resolve()
        root = repo_root.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(root):
        return None
    return resolved


def validate_ledger(
    ledger: ProgressLedger,
    repo_root: Path,
    *,
    authority: AttestationAuthority | None = None,
) -> ValidationReport:
    """Verify ``ledger`` against ``repo_root``.

    ``authority`` holds the key that signs run receipts.  Without it the
    validator can still check internal consistency, but it cannot tell a real
    run from a hand-written one, so every gate that claims an execution against
    data (``replay_validated`` and above) blocks.  That is deliberate: a
    missing verifier must read as *unverified*, never as *fine*.
    """

    report = ValidationReport()
    by_id = {item.module_id: item for item in ledger.modules}
    attested: dict[str, set[EvidenceKind]] = {item.module_id: set() for item in ledger.modules}

    _check_required_gates_present(ledger, report)
    _check_gate_shapes(ledger, report)
    _check_module_workstreams(ledger, report)
    _check_modules(ledger, by_id, repo_root, report, authority, attested)
    _check_evidence_dedup(ledger, repo_root, report)
    _build_coverage_matrix(ledger, report)
    _check_gates(ledger, by_id, report, authority, attested)
    return report


def _modules_with_errors(report: ValidationReport, module_ids: tuple[str, ...]) -> set[str]:
    """Module ids that any error message names.

    A gate that reports PASS while the ledger holds errors about its own
    modules is the misleading artefact the reviews kept finding: the overall
    verdict was correct but every gate line still said "passed".

    Attribution is deliberately over-inclusive.  Most messages are prefixed
    ``"<module_id>: "``, but cross-module ones (an evidence file claimed by two
    modules) name their modules mid-sentence, and those are exactly the errors
    a gate must not ignore.  Matching a module id anywhere in the message can
    therefore block a gate on a mention rather than a fault; blocking a gate
    that should have passed is a recoverable error, passing one that should
    have blocked is not.  ``\b`` prevents ``M0`` from matching inside ``M05``.
    """

    named: set[str] = set()
    for error in report.errors:
        for module_id in module_ids:
            if re.search(rf"\b{module_id}\b", error):
                named.add(module_id)
    return named


def _check_module_workstreams(ledger: ProgressLedger, report: ValidationReport) -> None:
    """A module's workstream membership is frozen, not declared per run."""

    for entry in ledger.modules:
        expected = _FROZEN_MODULE_WORKSTREAMS.get(entry.module_id)
        if expected is None:
            continue
        if tuple(entry.workstream_ids) != expected:
            report.errors.append(
                f"{entry.module_id}: workstream_ids {tuple(entry.workstream_ids)} do not match "
                f"the frozen mapping {expected}"
            )


def _check_required_gates_present(ledger: ProgressLedger, report: ValidationReport) -> None:
    by_gate_id = {gate.gate_id: gate for gate in ledger.gates}
    for gate_id in _REQUIRED_GATE_MODULES:
        if gate_id not in by_gate_id:
            report.errors.append(f"required gate {gate_id} is missing")
        elif not by_gate_id[gate_id].required:
            report.errors.append(f"required gate {gate_id} must be required=True")


def _check_gate_shapes(ledger: ProgressLedger, report: ValidationReport) -> None:
    by_gate_id = {gate.gate_id: gate for gate in ledger.gates}
    for gate_id, expected_modules in _REQUIRED_GATE_MODULES.items():
        gate = by_gate_id.get(gate_id)
        if gate is None:
            continue
        expected_maturity = _REQUIRED_GATE_MATURITIES[gate_id]
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
        expected_workstreams = _REQUIRED_GATE_WORKSTREAMS[gate_id]
        if gate.required_workstream_ids != expected_workstreams:
            report.errors.append(
                f"gate {gate_id} required_workstream_ids must be exactly "
                f"{expected_workstreams}, got {gate.required_workstream_ids}"
            )


def _check_modules(
    ledger: ProgressLedger,
    by_id: dict[str, ModuleEntry],
    repo_root: Path,
    report: ValidationReport,
    authority: AttestationAuthority | None,
    attested: dict[str, set[EvidenceKind]],
) -> None:
    present_ids = set(by_id)
    missing = set(ALL_MODULE_IDS) - present_ids
    for module_id in sorted(missing):
        report.errors.append(f"module {module_id} is missing from the ledger")

    for entry in ledger.modules:
        _check_paths(entry, repo_root, report)
        _check_evidence_content(entry, repo_root, report, authority, attested)
        _check_maturity_evidence(entry, repo_root, report)
        _check_claims(entry, report)


def _check_paths(entry: ModuleEntry, repo_root: Path, report: ValidationReport) -> None:
    # Implementation and test paths get the same containment treatment as
    # evidence: ``_exists`` alone accepted ``../../etc`` and a symlink pointing
    # outside the tree.  A package directory is a legitimate implementation
    # reference, but an *empty* one is not: ``mkdir`` must not read as code.
    for label, paths in (
        ("implementation", entry.implementation_paths),
        ("test", entry.test_paths),
    ):
        for path in paths:
            resolved = _contained_path(repo_root, path)
            if resolved is None:
                report.errors.append(
                    f"{entry.module_id}: {label} path must be a repository-relative path "
                    f"inside the repository: {path}"
                )
                continue
            if not resolved.exists():
                report.errors.append(f"{entry.module_id}: {label} path missing: {path}")
                continue
            if resolved.is_dir():
                if not any(resolved.rglob("*.py")):
                    report.errors.append(
                        f"{entry.module_id}: {label} path is a directory with no Python "
                        f"source: {path}"
                    )
                continue
            if not resolved.is_file():
                report.errors.append(
                    f"{entry.module_id}: {label} path is neither a file nor a directory: {path}"
                )
    for artifact in entry.evidence_artifacts:
        if not _exists(repo_root, artifact.path):
            report.errors.append(f"{entry.module_id}: evidence artifact missing: {artifact.path}")
        for label, declared in (
            ("evidence", artifact.path),
            ("run receipt", artifact.run_receipt),
        ):
            if _contained_path(repo_root, declared) is None:
                report.errors.append(
                    f"{entry.module_id}: {label} path must be a repository-relative path "
                    f"inside the repository: {declared}"
                )


def _check_evidence_content(
    entry: ModuleEntry,
    repo_root: Path,
    report: ValidationReport,
    authority: AttestationAuthority | None,
    attested: dict[str, set[EvidenceKind]],
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
        _check_run_receipt(entry, artifact, repo_root, report, authority, attested)


def _check_evidence_payload(
    entry: ModuleEntry,
    artifact: EvidenceArtifact,
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
    # Self-consistent, and reachable: the digest covers the payload with the
    # digest field removed, so a producer can actually compute it.
    if payload.artifact_sha256 != payload.canonical_payload_sha256():
        report.errors.append(
            f"{entry.module_id}: evidence {artifact.path} artifact_sha256 does not match "
            "its own canonical payload"
        )
    if payload.evidence_kind != artifact.kind:
        report.errors.append(
            f"{entry.module_id}: evidence {artifact.path} kind does not match ledger"
        )
    # A field that merely exists proves nothing; a failed or empty run must not
    # be able to attest a maturity.
    if payload.result_status not in _PASSING_RESULT_STATUSES:
        report.errors.append(
            f"{entry.module_id}: evidence {artifact.path} result_status "
            f"{payload.result_status!r} is not one of {sorted(_PASSING_RESULT_STATUSES)}"
        )
    if artifact.kind in _RUNTIME_EVIDENCE_KINDS and payload.case_count <= 0:
        report.errors.append(
            f"{entry.module_id}: evidence {artifact.path} attests "
            f"{artifact.kind.value} with case_count=0"
        )
    expected_schema = _SCHEMA_BY_KIND.get(artifact.kind)
    if expected_schema is not None and artifact.artifact_schema != expected_schema:
        report.errors.append(
            f"{entry.module_id}: evidence {artifact.path} declares schema "
            f"{artifact.artifact_schema!r} but kind {artifact.kind.value} requires "
            f"{expected_schema!r}"
        )


def _check_run_receipt(
    entry: ModuleEntry,
    artifact: EvidenceArtifact,
    repo_root: Path,
    report: ValidationReport,
    authority: AttestationAuthority | None,
    attested: dict[str, set[EvidenceKind]],
) -> None:
    """Verify the receipt binds this artifact to a real, attested execution."""

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
    if receipt.result_status not in _PASSING_RESULT_STATUSES:
        report.errors.append(
            f"{entry.module_id}: run receipt {artifact.run_receipt} result_status "
            f"{receipt.result_status!r} is not one of {sorted(_PASSING_RESULT_STATUSES)}"
        )
    # The receipt must name the module and kind it is filed under, or one run
    # can be reused as evidence for a different module or a stronger kind.
    if receipt.module_id != entry.module_id:
        report.errors.append(
            f"{entry.module_id}: run receipt {artifact.run_receipt} attests module "
            f"{receipt.module_id!r}"
        )
    if receipt.evidence_kind != artifact.kind:
        report.errors.append(
            f"{entry.module_id}: run receipt {artifact.run_receipt} attests kind "
            f"{receipt.evidence_kind.value!r} but the ledger files it as "
            f"{artifact.kind.value!r}"
        )

    payload = _load_payload(artifact, repo_root)
    if payload is not None:
        # The receipt and the artifact must describe the *same* run, or a
        # passing receipt can be paired with an unrelated artifact.
        for field_name in (
            "run_id",
            "git_commit_sha",
            "result_status",
            "dataset_id",
            "config_sha256",
            "code_snapshot_sha256",
            "dataset_manifest_sha256",
            "module_id",
            "evidence_kind",
        ):
            receipt_value = getattr(receipt, field_name)
            payload_value = getattr(payload, field_name)
            if receipt_value != payload_value:
                report.errors.append(
                    f"{entry.module_id}: run receipt {artifact.run_receipt} {field_name} "
                    f"{receipt_value!r} does not match evidence {payload_value!r}"
                )

    _check_commit_binding(entry, artifact, receipt, repo_root, report)

    if artifact.kind not in _RUNTIME_EVIDENCE_KINDS:
        return
    # Runtime evidence is the kind a gate promotes on, so it must be signed by
    # the authority rather than declared by the code under review.
    if authority is None:
        report.warnings.append(
            f"{entry.module_id}: run receipt {artifact.run_receipt} could not be "
            "authenticated because no attestation authority was supplied"
        )
        return
    try:
        authority.verify(DOMAIN_RUN_RECEIPT, receipt.attested_content(), receipt.attestation)
    except AttestationError as error:
        report.errors.append(
            f"{entry.module_id}: run receipt {artifact.run_receipt} is not attested by the "
            f"governance authority: {error}"
        )
        return
    attested.setdefault(entry.module_id, set()).add(artifact.kind)


def _check_commit_binding(
    entry: ModuleEntry,
    artifact: EvidenceArtifact,
    receipt: RunReceipt,
    repo_root: Path,
    report: ValidationReport,
) -> None:
    """The named commit must exist here and match the declared code snapshot.

    A 40-hex string that no object database has ever seen is not a code
    binding.  When the commit cannot be resolved the result is an *error* for
    runtime evidence rather than a pass, because "cannot check" is not "fine".

    What this does **not** prove: that the named tree contains the module's
    implementation, or that the run actually executed that tree.  It pins the
    receipt to one revision of this repository, which is the difference between
    an unfalsifiable claim and a checkable one -- not a proof of execution.
    """

    tree_sha = _git_tree_sha(repo_root, receipt.git_commit_sha)
    if tree_sha is None:
        message = (
            f"{entry.module_id}: run receipt {artifact.run_receipt} names commit "
            f"{receipt.git_commit_sha} which cannot be resolved in this repository"
        )
        if artifact.kind in _RUNTIME_EVIDENCE_KINDS:
            report.errors.append(message)
        else:
            report.warnings.append(message)
        return
    expected = code_snapshot_digest(tree_sha)
    if receipt.code_snapshot_sha256 != expected:
        report.errors.append(
            f"{entry.module_id}: run receipt {artifact.run_receipt} code_snapshot_sha256 "
            f"does not match the tree of commit {receipt.git_commit_sha}"
        )


def _git_tree_sha(repo_root: Path, commit_sha: str) -> str | None:
    """Resolve ``commit_sha`` to its tree object, or ``None`` if unavailable."""

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", f"{commit_sha}^{{tree}}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    tree = result.stdout.strip()
    return tree or None


def _load_payload(artifact: EvidenceArtifact, repo_root: Path) -> EvidenceArtifactPayload | None:
    try:
        raw = json.loads((repo_root / artifact.path).read_text(encoding="utf-8"))
        return EvidenceArtifactPayload.model_validate(raw)
    except Exception:
        return None


def _check_evidence_dedup(
    ledger: ProgressLedger, repo_root: Path, report: ValidationReport
) -> None:
    """Reject one evidence file silently backing more than one module."""

    seen: dict[str, str] = {}
    for entry in ledger.modules:
        for artifact in entry.evidence_artifacts:
            resolved = _contained_path(repo_root, artifact.path)
            key = str(resolved) if resolved is not None else artifact.path
            previous = seen.get(key)
            if previous is not None:
                report.errors.append(
                    f"evidence {artifact.path} is claimed by both {previous} and {entry.module_id}"
                )
            else:
                seen[key] = entry.module_id


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
    authority: AttestationAuthority | None,
    attested: dict[str, set[EvidenceKind]],
) -> None:
    for gate in ledger.gates:
        blockers: list[str] = []
        # A required gate is evaluated against the frozen spec, never against
        # the JSON. Otherwise lowering min_maturity in the file makes the gate
        # report PASS while the shape error only surfaces in the global errors.
        frozen_maturity = _REQUIRED_GATE_MATURITIES.get(gate.gate_id)
        frozen_modules = _REQUIRED_GATE_MODULES.get(gate.gate_id)
        effective_maturity = frozen_maturity if frozen_maturity is not None else gate.min_maturity
        if frozen_maturity is not None and gate.min_maturity != frozen_maturity:
            blockers.append(
                f"declared min_maturity {gate.min_maturity.value} does not match the frozen "
                f"specification {frozen_maturity.value}"
            )
        if frozen_modules is not None and gate.required_module_ids != frozen_modules:
            blockers.append("declared required_module_ids do not match the frozen specification")
        frozen_workstreams = _REQUIRED_GATE_WORKSTREAMS.get(gate.gate_id)
        if frozen_workstreams is not None and gate.required_workstream_ids != frozen_workstreams:
            blockers.append(
                "declared required_workstream_ids do not match the frozen specification"
            )
        min_order = MATURITY_ORDER[effective_maturity]
        required_module_ids = (
            frozen_modules if frozen_modules is not None else gate.required_module_ids
        )
        # A gate at or above replay_validated promotes on a claimed execution.
        # Without a verifier for those receipts the gate cannot be evaluated,
        # and an unevaluable gate is a BLOCK, not a PASS.
        needs_attestation = min_order >= MATURITY_ORDER[_ATTESTATION_REQUIRED_FROM]
        required_kind = _KIND_FOR_MATURITY.get(effective_maturity)
        if needs_attestation and authority is None:
            blockers.append(
                f"{gate.gate_id} requires {effective_maturity.value} evidence, which must be "
                "attested by the governance authority; no authority was supplied so the "
                "receipts could not be authenticated"
            )

        faulty = _modules_with_errors(report, required_module_ids)
        for module_id in required_module_ids:
            entry = by_id.get(module_id)
            if entry is None:
                blockers.append(f"module {module_id} is missing")
                continue
            if module_id in faulty:
                blockers.append(
                    f"{module_id} has validation errors, so its declared maturity is unverified"
                )
                continue
            if MATURITY_ORDER[entry.maturity] < min_order:
                blockers.append(
                    f"{module_id} is {entry.maturity.value}, below {effective_maturity.value}"
                )
                continue
            if (
                needs_attestation
                and authority is not None
                and required_kind is not None
                and required_kind not in attested.get(module_id, set())
            ):
                blockers.append(
                    f"{module_id} claims {entry.maturity.value} but has no authority-attested "
                    f"{required_kind.value} run receipt"
                )

        effective_workstreams = (
            frozen_workstreams if frozen_workstreams is not None else gate.required_workstream_ids
        )
        for workstream in effective_workstreams:
            # Membership comes from the frozen mapping, not the JSON, so a
            # gate cannot be satisfied by re-filing a mature module.
            members = [
                entry
                for entry in ledger.modules
                if workstream in _FROZEN_MODULE_WORKSTREAMS.get(entry.module_id, ())
                and MATURITY_ORDER[entry.maturity] >= min_order
            ]
            if not members:
                blockers.append(
                    f"workstream {workstream} has no module at or above {effective_maturity.value}"
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
