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

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel

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
    "EvidenceArtifact",
    "EvidenceKind",
    "Gate",
    "Maturity",
    "ModuleEntry",
    "ProgressLedger",
]
