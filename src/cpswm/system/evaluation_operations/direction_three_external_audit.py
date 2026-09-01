"""S3-DG-12C complete-neighbor audit before matched comparison.

The selected route forbids silently dropping a difficult or strong neighbor.
Every required external system must be runnable at a frozen revision, excluded
with evidence, or remain visibly pending.  A sealed comparison cannot start
while any entry is pending.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel

from .direction_three_comparison import (
    DirectionThreeComparisonAudit,
    DirectionThreeMethodRun,
    validate_matched_direction_three_runs,
)
from .direction_three_dataset import DirectionThreeEpisodeDataset


class DirectionThreeExternalSystem(StrEnum):
    FINDINGDORY_OFFICIAL = "findingdory_official"
    VLMAPS = "vlmaps"
    DYNAMEM = "dynamem"
    CONCEPT_GRAPHS = "concept_graphs"
    REMEMBR = "remembr"
    EMBODIED_VIDEOAGENT = "embodied_videoagent"


REQUIRED_DIRECTION_THREE_EXTERNAL_SYSTEMS = frozenset(DirectionThreeExternalSystem)


class ExternalAuditDisposition(StrEnum):
    PENDING_REPRODUCTION = "pending_reproduction"
    RUNNABLE = "runnable"
    EXCLUDED_WITH_EVIDENCE = "excluded_with_evidence"


class ExternalSystemAuditEntry(ContractModel):
    system_id: DirectionThreeExternalSystem
    method_family: str = Field(min_length=1)
    project_url: str = Field(pattern=r"^https://")
    code_url: str = Field(pattern=r"^https://")
    disposition: ExternalAuditDisposition
    upstream_revision: str | None = Field(default=None, min_length=1)
    source_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    license_status: str = Field(min_length=1)
    adapter_version: str | None = Field(default=None, min_length=1)
    supported_metric_families: tuple[str, ...]
    adaptation_notes: tuple[str, ...] = ()
    exclusion_reason: str | None = Field(default=None, min_length=1)
    exclusion_evidence_urls: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _entry_semantics(self) -> ExternalSystemAuditEntry:
        if len(self.supported_metric_families) != len(set(self.supported_metric_families)):
            raise ValueError("external metric families must be unique")
        if self.disposition is ExternalAuditDisposition.RUNNABLE:
            required = (
                self.upstream_revision,
                self.source_artifact_sha256,
                self.adapter_version,
            )
            if any(value is None for value in required):
                raise ValueError(
                    "runnable external system requires frozen code and adapter binding"
                )
            if self.exclusion_reason is not None or self.exclusion_evidence_urls:
                raise ValueError("runnable external system cannot carry exclusion evidence")
        elif self.disposition is ExternalAuditDisposition.EXCLUDED_WITH_EVIDENCE:
            if self.exclusion_reason is None or not self.exclusion_evidence_urls:
                raise ValueError("external exclusion requires a reason and evidence URL")
            if any(not url.startswith("https://") for url in self.exclusion_evidence_urls):
                raise ValueError("external exclusion evidence must use HTTPS URLs")
        else:
            if self.exclusion_reason is not None or self.exclusion_evidence_urls:
                raise ValueError("pending audit entry cannot pre-judge an exclusion")
        return self


class DirectionThreeExternalAudit(ContractModel):
    audit_version: str = "direction-three-external-audit@0.1"
    entries: tuple[ExternalSystemAuditEntry, ...]

    @model_validator(mode="after")
    def _complete_registry(self) -> DirectionThreeExternalAudit:
        ids = [entry.system_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("external audit system IDs must be unique")
        if set(ids) != REQUIRED_DIRECTION_THREE_EXTERNAL_SYSTEMS:
            missing = sorted(
                item.value for item in REQUIRED_DIRECTION_THREE_EXTERNAL_SYSTEMS - set(ids)
            )
            extra = sorted(
                item.value for item in set(ids) - REQUIRED_DIRECTION_THREE_EXTERNAL_SYSTEMS
            )
            raise ValueError(f"external audit registry mismatch: missing={missing}, extra={extra}")
        return self

    @property
    def ready_for_sealed_comparison(self) -> bool:
        return all(
            entry.disposition is not ExternalAuditDisposition.PENDING_REPRODUCTION
            for entry in self.entries
        )


def selected_direction_three_external_audit() -> DirectionThreeExternalAudit:
    """Return the selected full registry without fabricating reproduction status."""

    pending = ExternalAuditDisposition.PENDING_REPRODUCTION
    return DirectionThreeExternalAudit(
        entries=(
            ExternalSystemAuditEntry(
                system_id=DirectionThreeExternalSystem.FINDINGDORY_OFFICIAL,
                method_family="official_long-horizon_embodied_memory_agent",
                project_url="https://findingdorybenchmark.github.io/",
                code_url="https://github.com/findingdory-benchmark/findingdory-habitat",
                disposition=pending,
                license_status="pending repository and asset license audit",
                supported_metric_families=("frame_retrieval", "task_success", "spl"),
            ),
            ExternalSystemAuditEntry(
                system_id=DirectionThreeExternalSystem.VLMAPS,
                method_family="static_open_vocabulary_3d_map",
                project_url="https://vlmaps.github.io/",
                code_url="https://github.com/vlmaps/vlmaps",
                disposition=pending,
                license_status="pending frozen-revision verification",
                supported_metric_families=("localization", "navigation"),
            ),
            ExternalSystemAuditEntry(
                system_id=DirectionThreeExternalSystem.DYNAMEM,
                method_family="dynamic_spatio_semantic_memory",
                project_url="https://dynamem.github.io/",
                code_url="https://github.com/hello-robot/stretch_ai",
                disposition=pending,
                license_status="pending frozen-revision verification",
                supported_metric_families=("dynamic_localization", "mobile_manipulation"),
            ),
            ExternalSystemAuditEntry(
                system_id=DirectionThreeExternalSystem.CONCEPT_GRAPHS,
                method_family="open_vocabulary_3d_scene_graph",
                project_url="https://concept-graphs.github.io/",
                code_url="https://github.com/concept-graphs/concept-graphs",
                disposition=pending,
                license_status="pending frozen-revision verification",
                supported_metric_families=("instance_retrieval", "spatial_relation"),
            ),
            ExternalSystemAuditEntry(
                system_id=DirectionThreeExternalSystem.REMEMBR,
                method_family="retrieval_augmented_spatiotemporal_memory",
                project_url="https://nvidia-ai-iot.github.io/remembr/",
                code_url="https://github.com/NVIDIA-AI-IOT/remembr",
                disposition=pending,
                license_status="pending frozen-revision verification",
                supported_metric_families=("long_horizon_qa", "navigation"),
            ),
            ExternalSystemAuditEntry(
                system_id=DirectionThreeExternalSystem.EMBODIED_VIDEOAGENT,
                method_family="persistent_dynamic_object_memory",
                project_url="https://embodied-videoagent.github.io/",
                code_url="https://github.com/Embodied-VideoAgent/embodied-videoagent",
                disposition=pending,
                license_status="pending code availability and license verification",
                supported_metric_families=("dynamic_scene_memory", "embodied_task_success"),
            ),
        )
    )


def validate_external_audit_run_coverage(
    audit: DirectionThreeExternalAudit,
    runs: tuple[DirectionThreeMethodRun, ...],
) -> None:
    """Refuse cherry-picked runs after the full audit has been resolved."""

    audit = DirectionThreeExternalAudit.model_validate(audit.model_dump(mode="python"))
    if not audit.ready_for_sealed_comparison:
        raise ValueError("external neighbor audit is incomplete")
    external_method_ids = {run.method.method_id for run in runs if run.method.external_system}
    runnable_ids = {
        entry.system_id.value
        for entry in audit.entries
        if entry.disposition is ExternalAuditDisposition.RUNNABLE
    }
    if external_method_ids != runnable_ids:
        raise ValueError("external runs must cover exactly every runnable audited system")


def validate_sealed_direction_three_runs(
    dataset: DirectionThreeEpisodeDataset,
    audit: DirectionThreeExternalAudit,
    runs: tuple[DirectionThreeMethodRun, ...],
) -> DirectionThreeComparisonAudit:
    """Run the complete-neighbor gate before the existing matched-run gate."""

    validate_external_audit_run_coverage(audit, runs)
    return validate_matched_direction_three_runs(dataset, runs)
