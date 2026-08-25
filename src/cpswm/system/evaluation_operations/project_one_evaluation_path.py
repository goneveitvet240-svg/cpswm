"""Hard boundary between offline method replay and the formal CPSWM path.

The real-data pilot deliberately keeps its inexpensive dataset-to-method route.
That route bypasses M05--M16 and therefore cannot support a formal B1 claim.
This module makes the limitation machine-readable and defines the narrow
equivalence seam that can be tested: once the formal path has produced its
canonical M16 method evidence, both routes must hand the method identical
visible fields.  It does not claim that the bypassed modules executed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from cpswm.system.reproducibility import content_sha256

from .project_one_dataset import ProjectOneDatasetRecord

OFFLINE_METHOD_EVALUATION: Literal["offline_method_evaluation"] = "offline_method_evaluation"
FORMAL_CPSWM_PATH: Literal["formal_cpswm_path"] = "formal_cpswm_path"
BYPASSED_MODULES = tuple(f"M{index:02d}" for index in range(5, 17))


class FormalB1ClaimError(ValueError):
    """Raised when an offline replay is presented as formal B1 evidence."""


@dataclass(frozen=True, slots=True)
class ProjectOneMethodEvidence:
    """The complete robot-visible field set consumed by project-one arms."""

    stream_id: str
    event_id: str
    subject_id: str
    household_id: str
    object_id: str
    actor_id: str
    timestamp: object
    context_key: str
    context_value: float
    observed_location: str
    observation_quality: float

    @classmethod
    def from_offline_record(cls, record: ProjectOneDatasetRecord) -> ProjectOneMethodEvidence:
        return cls(**asdict(record))

    def to_dataset_record(self) -> ProjectOneDatasetRecord:
        return ProjectOneDatasetRecord(**asdict(self))  # type: ignore[arg-type]

    @property
    def content_sha256(self) -> str:
        return content_sha256(asdict(self))


@dataclass(frozen=True, slots=True)
class MethodInputEquivalenceReceipt:
    scope: Literal["m16_to_method_input_contract_only"]
    offline_method_input_sha256: str
    canonical_method_input_sha256: str
    equivalent: bool
    does_not_prove_modules_executed: tuple[str, ...] = BYPASSED_MODULES


def compare_offline_and_canonical_method_input(
    offline: ProjectOneDatasetRecord,
    canonical: ProjectOneMethodEvidence,
) -> MethodInputEquivalenceReceipt:
    """Compare visible method inputs, never upstream implementation semantics."""

    offline_view = ProjectOneMethodEvidence.from_offline_record(offline)
    return MethodInputEquivalenceReceipt(
        scope="m16_to_method_input_contract_only",
        offline_method_input_sha256=offline_view.content_sha256,
        canonical_method_input_sha256=canonical.content_sha256,
        equivalent=offline_view == canonical,
    )


def require_formal_b1_claim_allowed(evaluation_mode: str) -> None:
    if evaluation_mode != FORMAL_CPSWM_PATH:
        raise FormalB1ClaimError(
            "offline_method_evaluation bypasses M05-M16 and cannot be claimed as formal B1"
        )


__all__ = [
    "BYPASSED_MODULES",
    "FORMAL_CPSWM_PATH",
    "OFFLINE_METHOD_EVALUATION",
    "FormalB1ClaimError",
    "MethodInputEquivalenceReceipt",
    "ProjectOneMethodEvidence",
    "compare_offline_and_canonical_method_input",
    "require_formal_b1_claim_allowed",
]
