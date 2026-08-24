"""Machine-readable progress ledger contracts for structure one.

The ledger maps M01-M32 and WS1-WS10 to a single maturity scale.  It is the
single source of truth for *claims* about what has been implemented; the
validator never upgrades a maturity level by itself -- maturity is declared
explicitly and the validator only checks that the declared level is supported
by the referenced files, tests, and artifacts.

Maturity levels (lowest to highest):

    absent
    contract_only
    synthetic_vertical_slice
    integrated_synthetic
    replay_validated
    real_data_validated
    embodied_validated
"""

from __future__ import annotations

import hashlib
import json
import shlex
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import Field, ValidationInfo, field_validator, model_validator

from cpswm.contracts.base import ContractModel, require_aware
from cpswm.system.attestation import Attestation

ALL_MODULE_IDS = tuple(f"M{i:02d}" for i in range(1, 33))
ALL_WORKSTREAM_IDS = tuple(f"WS{i}" for i in range(1, 11))


class Maturity(StrEnum):
    ABSENT = "absent"
    CONTRACT_ONLY = "contract_only"
    SYNTHETIC_VERTICAL_SLICE = "synthetic_vertical_slice"
    INTEGRATED_SYNTHETIC = "integrated_synthetic"
    REPLAY_VALIDATED = "replay_validated"
    REAL_DATA_VALIDATED = "real_data_validated"
    EMBODIED_VALIDATED = "embodied_validated"


MATURITY_ORDER: dict[Maturity, int] = {
    Maturity.ABSENT: 0,
    Maturity.CONTRACT_ONLY: 1,
    Maturity.SYNTHETIC_VERTICAL_SLICE: 2,
    Maturity.INTEGRATED_SYNTHETIC: 3,
    Maturity.REPLAY_VALIDATED: 4,
    Maturity.REAL_DATA_VALIDATED: 5,
    Maturity.EMBODIED_VALIDATED: 6,
}


class EvidenceKind(StrEnum):
    CONTRACT = "contract"
    CODE = "code"
    TEST = "test"
    SYNTHETIC = "synthetic"
    REPLAY = "replay"
    REAL_DATA = "real_data"
    EMBODIED = "embodied"


class EvidenceArtifact(ContractModel):
    """One evidence artifact referenced by a module entry.

    Every field is required: ``content_sha256`` is the file's content hash
    (verified byte-for-byte by the validator), ``artifact_schema`` names a
    known schema, and ``run_receipt`` references a run receipt.  A path alone
    is never sufficient evidence.
    """

    path: str = Field(min_length=1)
    kind: EvidenceKind
    description: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_schema: str = Field(min_length=1)
    run_receipt: str = Field(min_length=1)


#: Evidence kinds that describe an *execution against data* rather than a
#: hand-built synthetic slice.  These carry the extra per-kind bindings below.
RUNTIME_EVIDENCE_KINDS: frozenset[EvidenceKind] = frozenset(
    {EvidenceKind.REPLAY, EvidenceKind.REAL_DATA, EvidenceKind.EMBODIED}
)

#: Which payload fields each runtime kind must populate.  A single flat schema
#: let a replay manifest, a real-data manifest and an embodied run report carry
#: identical content, so "real data" cost no more to declare than "synthetic".
REQUIRED_PAYLOAD_FIELDS_BY_KIND: dict[EvidenceKind, tuple[str, ...]] = {
    EvidenceKind.REPLAY: (
        "dataset_manifest_sha256",
        "replay_log_sha256",
        "replayed_transaction_count",
        "divergence_count",
    ),
    EvidenceKind.REAL_DATA: (
        "dataset_manifest_sha256",
        "recording_session_ids",
    ),
    EvidenceKind.EMBODIED: (
        "dataset_manifest_sha256",
        "robot_platform",
        "trial_count",
        "safety_incident_count",
    ),
}


def code_snapshot_digest(tree_sha: str) -> str:
    """The canonical ``code_snapshot_sha256`` for a git tree object.

    ``code_snapshot_sha256`` used to be an unconstrained 64-hex field, so it
    proved nothing: any value validated.  Defining it as a digest *of the
    commit's tree* makes it independently recomputable by anyone holding the
    repository, which is what turns it into a binding.
    """

    return hashlib.sha256(f"cpswm.code-snapshot.v1|{tree_sha.strip()}".encode()).hexdigest()


class EvidenceArtifactPayload(ContractModel):
    """The strongly-typed content every evidence artifact file must carry.

    The validator parses the artifact file with this schema and checks that the
    declared ``module_id``/``covered_module_ids``, ``evidence_kind``, and
    ``artifact_sha256`` match the ledger entry, so a random repository file
    cannot be dressed up as validation evidence.

    Runtime kinds carry extra, kind-specific bindings (see
    :data:`REQUIRED_PAYLOAD_FIELDS_BY_KIND`).  Without them one flat schema let
    an embodied run report be written with exactly the fields of a synthetic
    one, which is the cheapest possible way to overclaim.
    """

    module_id: str = Field(min_length=1)
    evidence_kind: EvidenceKind
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    git_commit_sha: str = Field(min_length=1)
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    case_count: int = Field(ge=0)
    result_status: str = Field(min_length=1)
    covered_module_ids: tuple[str, ...] = ()

    #: Hash of the dataset manifest the run consumed. Required for runtime
    #: kinds: without it "real data" names a dataset but pins no content.
    dataset_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    # -- replay-only
    replay_log_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    replayed_transaction_count: int | None = Field(default=None, ge=1)
    divergence_count: int | None = Field(default=None, ge=0)

    # -- real-data-only
    recording_session_ids: tuple[str, ...] = ()

    # -- embodied-only
    robot_platform: str | None = Field(default=None, min_length=1)
    trial_count: int | None = Field(default=None, ge=1)
    safety_incident_count: int | None = Field(default=None, ge=0)
    operator_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_kind_specific_fields(self) -> EvidenceArtifactPayload:
        required = REQUIRED_PAYLOAD_FIELDS_BY_KIND.get(self.evidence_kind, ())
        for name in required:
            value = getattr(self, name)
            if value is None or value == ():
                raise ValueError(f"{self.evidence_kind.value} evidence requires {name!r}")
        # A field belonging to another kind must not be smuggled in: an
        # embodied report carrying only replay fields is not an embodied run.
        foreign = {
            EvidenceKind.REPLAY: ("robot_platform", "trial_count", "safety_incident_count"),
            EvidenceKind.REAL_DATA: ("replay_log_sha256", "robot_platform", "trial_count"),
            EvidenceKind.EMBODIED: ("replay_log_sha256", "replayed_transaction_count"),
        }.get(self.evidence_kind, ())
        for name in foreign:
            if getattr(self, name) is not None:
                raise ValueError(f"{self.evidence_kind.value} evidence must not declare {name!r}")
        if self.evidence_kind == EvidenceKind.REPLAY and self.divergence_count:
            raise ValueError("replay evidence with a nonzero divergence_count did not replay")
        return self

    def canonical_payload_sha256(self) -> str:
        """Digest of this payload with the digest field itself removed.

        Hashing the whole file and then requiring a field *inside* that file to
        equal the result asks for a SHA-256 fixed point, which cannot be
        constructed: no valid evidence could ever be produced.  Excluding the
        digest field makes the binding self-consistent and reachable.
        """

        payload = self.model_dump(mode="json", exclude={"artifact_sha256"})
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


class RunReceipt(ContractModel):
    """An authority-attested receipt binding one artifact to one execution.

    The previous receipt named only ``run_id``, ``artifact_sha256``,
    ``git_commit_sha``, ``command`` and ``result_status``, all written by the
    same candidate code that wrote the artifact.  Reviews demonstrated the
    consequence: an empty implementation with a hand-written ``"passed"``
    receipt was indistinguishable from a real run.

    Two things changed:

    * the receipt now binds *what ran, on what, from which code, and how it
      ended* -- module, kind, dataset manifest, config, code snapshot, argv,
      exit code and wall-clock interval -- so the claim has surface to check;
    * :attr:`attestation` is a MAC from the governance authority.  A gate that
      requires attested evidence cannot be satisfied by a receipt the
      candidate minted itself.
    """

    run_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    evidence_kind: EvidenceKind
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_id: str = Field(min_length=1)
    dataset_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    git_commit_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    command_argv: tuple[str, ...] = Field(min_length=1)
    command: str = Field(min_length=1)
    exit_code: int
    started_at: datetime
    finished_at: datetime
    result_status: str = Field(min_length=1)
    #: Signed by the governance authority over :meth:`attested_content`.
    attestation: Attestation | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def validate_aware(cls, value: datetime, info: ValidationInfo) -> datetime:
        return require_aware(value, info.field_name or "timestamp")

    @model_validator(mode="after")
    def validate_receipt(self) -> RunReceipt:
        if self.finished_at < self.started_at:
            raise ValueError("run receipt finished_at precedes started_at")
        # A free-text command let the argv say one thing and the prose another.
        if self.command != shlex.join(self.command_argv):
            raise ValueError("run receipt command must be shlex.join(command_argv)")
        # "passed" with a nonzero exit code is not a passing run.
        passing = self.result_status.lower() in {"passed", "pass", "succeeded", "success"}
        if passing and self.exit_code != 0:
            raise ValueError(
                f"run receipt claims {self.result_status!r} with exit_code={self.exit_code}"
            )
        if not passing and self.exit_code == 0:
            raise ValueError(f"run receipt claims {self.result_status!r} with exit_code=0")
        if self.evidence_kind in RUNTIME_EVIDENCE_KINDS and self.dataset_manifest_sha256 is None:
            raise ValueError(
                f"{self.evidence_kind.value} run receipt requires dataset_manifest_sha256"
            )
        return self

    def attested_content(self) -> dict[str, object]:
        """The signable view: every field except the attestation itself."""

        return self.model_dump(mode="json", exclude={"attestation"})


class ModuleEntry(ContractModel):
    module_id: str
    workstream_ids: tuple[str, ...] = ()
    maturity: Maturity
    implementation_paths: tuple[str, ...] = ()
    test_paths: tuple[str, ...] = ()
    evidence_artifacts: tuple[EvidenceArtifact, ...] = ()
    blockers: tuple[str, ...] = ()
    allowed_claims: tuple[str, ...] = ()
    forbidden_claims: tuple[str, ...] = ()

    @field_validator("module_id")
    @classmethod
    def validate_module_id(cls, value: str) -> str:
        if value not in ALL_MODULE_IDS:
            raise ValueError(f"unknown module_id {value!r}")
        return value

    @field_validator("workstream_ids")
    @classmethod
    def validate_workstreams(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for workstream in value:
            if workstream not in ALL_WORKSTREAM_IDS:
                raise ValueError(f"unknown workstream_id {workstream!r}")
        return value


class Gate(ContractModel):
    gate_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required: bool = True
    required_module_ids: tuple[str, ...] = ()
    required_workstream_ids: tuple[str, ...] = ()
    min_maturity: Maturity

    @model_validator(mode="after")
    def validate_gate(self) -> Gate:
        if not self.required_module_ids and not self.required_workstream_ids:
            raise ValueError("a gate requires modules or workstreams")
        # Membership is deliberately not restricted here: a tampered gate that
        # names ATG-1 or an unknown workstream must survive loading so the
        # validator can report it as a BLOCK reason.
        return self


class ProgressLedger(ContractModel):
    schema_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    generated_at: str = Field(min_length=1)
    ledger_id: UUID = Field(default_factory=uuid4)
    modules: tuple[ModuleEntry, ...] = ()
    gates: tuple[Gate, ...] = ()

    @model_validator(mode="after")
    def validate_ledger(self) -> ProgressLedger:
        module_ids = [item.module_id for item in self.modules]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("ledger contains duplicate module_ids")
        gate_ids = [item.gate_id for item in self.gates]
        if len(gate_ids) != len(set(gate_ids)):
            raise ValueError("ledger contains duplicate gate_ids")
        return self


__all__ = [
    "ALL_MODULE_IDS",
    "ALL_WORKSTREAM_IDS",
    "MATURITY_ORDER",
    "REQUIRED_PAYLOAD_FIELDS_BY_KIND",
    "RUNTIME_EVIDENCE_KINDS",
    "EvidenceArtifact",
    "EvidenceArtifactPayload",
    "EvidenceKind",
    "Gate",
    "Maturity",
    "ModuleEntry",
    "ProgressLedger",
    "RunReceipt",
    "code_snapshot_digest",
]
