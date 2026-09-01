"""Fail-closed matched-comparison protocol for direction-three systems.

This module does not choose which external memory/search systems to compare.
It fixes the shared evaluation surface so every selected system receives the
same visible episodes, candidate support, action budget, and cost definition,
while evaluator-only truth stays outside method submissions.
"""

from __future__ import annotations

from math import isclose, isfinite
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from cpswm.contracts import (
    ContractModel,
    EvidenceChannel,
    ObservationActionType,
    ResolutionStatus,
)
from cpswm.system.reproducibility import content_sha256

from .direction_three_dataset import (
    DirectionThreeDatasetSplit,
    DirectionThreeEpisodeDataset,
)

_COST_AXES = frozenset({"motion", "time", "interruption", "privacy", "safety"})


class DirectionThreeComparisonBudget(ContractModel):
    max_observation_actions: int = Field(ge=0)
    max_execution_actions: int = Field(ge=0)
    max_path_length_m: float | None = Field(default=None, ge=0.0)
    max_elapsed_seconds: float | None = Field(default=None, ge=0.0)
    allowed_observation_actions: tuple[ObservationActionType, ...]
    cost_weights: dict[str, float]

    @model_validator(mode="after")
    def _budget_semantics(self) -> DirectionThreeComparisonBudget:
        if len(self.allowed_observation_actions) != len(set(self.allowed_observation_actions)):
            raise ValueError("allowed observation actions must be unique")
        if set(self.cost_weights) != _COST_AXES:
            raise ValueError("comparison cost weights must cover the five shared axes")
        if any(not isfinite(value) or value < 0.0 for value in self.cost_weights.values()):
            raise ValueError("comparison cost weights must be finite and non-negative")
        return self


class DirectionThreeMethodDeclaration(ContractModel):
    method_id: str = Field(min_length=1)
    method_family: str = Field(min_length=1)
    external_system: bool
    code_version: str = Field(min_length=1)
    input_channels: tuple[EvidenceChannel, ...]
    model_versions: dict[str, str]
    calibration_domains: dict[str, str] = Field(default_factory=dict)
    supports_active_verification: bool
    produces_normalized_posterior: bool
    tuning_splits: tuple[DirectionThreeDatasetSplit, ...] = Field(min_length=1)
    evaluator_truth_accessed: bool = False

    @model_validator(mode="after")
    def _method_semantics(self) -> DirectionThreeMethodDeclaration:
        if len(self.input_channels) != len(set(self.input_channels)):
            raise ValueError("method input channels must be unique")
        if len(self.tuning_splits) != len(set(self.tuning_splits)):
            raise ValueError("method tuning splits must be unique")
        if DirectionThreeDatasetSplit.TEST in self.tuning_splits:
            raise ValueError("the sealed test split cannot be used for method tuning")
        if self.evaluator_truth_accessed:
            raise ValueError("method declarations cannot access evaluator-only truth")
        if any(not key.strip() or not value.strip() for key, value in self.model_versions.items()):
            raise ValueError("method model-version bindings must be non-empty")
        if any(
            not key.strip() or not value.strip() for key, value in self.calibration_domains.items()
        ):
            raise ValueError("method calibration-domain bindings must be non-empty")
        return self


class DirectionThreeMethodEpisodeOutput(ContractModel):
    episode_id: UUID
    visible_content_hash: str = Field(min_length=1)
    candidate_ranking: tuple[UUID, ...] = Field(min_length=1)
    posterior_by_candidate_id: dict[UUID, float] | None = None
    resolution_status: ResolutionStatus
    selected_target_candidate_id: UUID | None = None
    observation_actions_used: int = Field(ge=0)
    execution_actions_used: int = Field(ge=0)
    path_length_m: float = Field(ge=0.0)
    elapsed_seconds: float = Field(ge=0.0)
    costs: dict[str, float]
    source_output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path_length_m", "elapsed_seconds")
    @classmethod
    def _finite_resource(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("comparison resource use must be finite")
        return value

    @model_validator(mode="after")
    def _output_semantics(self) -> DirectionThreeMethodEpisodeOutput:
        if len(self.candidate_ranking) != len(set(self.candidate_ranking)):
            raise ValueError("candidate ranking must be unique")
        if set(self.costs) != _COST_AXES:
            raise ValueError("episode costs must cover the five shared axes")
        if any(not isfinite(value) or value < 0.0 for value in self.costs.values()):
            raise ValueError("episode costs must be finite and non-negative")
        posterior = self.posterior_by_candidate_id
        if posterior is not None:
            if any(
                not isfinite(probability) or not 0.0 <= probability <= 1.0
                for probability in posterior.values()
            ):
                raise ValueError("method posterior must contain probabilities")
            if not isclose(sum(posterior.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError("method posterior must sum to one")
            if any(candidate not in posterior for candidate in self.candidate_ranking):
                raise ValueError("ranked candidates must appear in the method posterior")
            ranked_values = [posterior[candidate] for candidate in self.candidate_ranking]
            if ranked_values != sorted(ranked_values, reverse=True):
                raise ValueError("candidate ranking must follow descending posterior")
        return self


class DirectionThreeMethodRun(ContractModel):
    run_id: UUID = Field(default_factory=uuid4)
    dataset_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_split: DirectionThreeDatasetSplit
    method: DirectionThreeMethodDeclaration
    budget: DirectionThreeComparisonBudget
    outputs: tuple[DirectionThreeMethodEpisodeOutput, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _run_semantics(self) -> DirectionThreeMethodRun:
        ids = [output.episode_id for output in self.outputs]
        if len(ids) != len(set(ids)):
            raise ValueError("method run episode outputs must be unique")
        if self.evaluation_split in self.method.tuning_splits:
            raise ValueError("evaluation split cannot also be a tuning split")
        if self.method.produces_normalized_posterior and any(
            output.posterior_by_candidate_id is None for output in self.outputs
        ):
            raise ValueError("probabilistic methods must emit a posterior for every episode")
        if not self.method.produces_normalized_posterior and any(
            output.posterior_by_candidate_id is not None for output in self.outputs
        ):
            raise ValueError("method posterior capability declaration is inconsistent")
        return self


class DirectionThreeComparisonAudit(ContractModel):
    comparable: bool
    dataset_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_split: DirectionThreeDatasetSplit
    method_ids: tuple[str, ...]
    episode_ids: tuple[UUID, ...]
    shared_budget_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    posterior_metric_eligible_method_ids: tuple[str, ...]
    checks_passed: tuple[str, ...]


def validate_matched_direction_three_runs(
    dataset: DirectionThreeEpisodeDataset,
    runs: tuple[DirectionThreeMethodRun, ...],
) -> DirectionThreeComparisonAudit:
    """Validate fairness without reading evaluator truth into any method run."""

    dataset = DirectionThreeEpisodeDataset.model_validate(dataset.model_dump(mode="python"))
    runs = tuple(
        DirectionThreeMethodRun.model_validate(run.model_dump(mode="python")) for run in runs
    )
    if len(runs) < 2:
        raise ValueError("a matched comparison requires at least two method runs")
    method_ids = tuple(run.method.method_id for run in runs)
    if len(method_ids) != len(set(method_ids)):
        raise ValueError("matched comparison method IDs must be unique")
    manifest_hash = content_sha256(dataset.manifest)
    if any(run.dataset_manifest_hash != manifest_hash for run in runs):
        raise ValueError("method run is bound to a different dataset manifest")
    splits = {run.evaluation_split for run in runs}
    if len(splits) != 1:
        raise ValueError("matched methods must use the same evaluation split")
    split = next(iter(splits))
    budget = runs[0].budget
    if any(run.budget != budget for run in runs[1:]):
        raise ValueError("matched methods must use an identical action and cost budget")

    visible = {episode.episode_id: episode for episode in dataset.visible_episodes(split)}
    if not visible:
        raise ValueError("dataset has no episodes in the requested evaluation split")
    expected_ids = set(visible)
    for run in runs:
        outputs = {output.episode_id: output for output in run.outputs}
        if set(outputs) != expected_ids:
            raise ValueError("method run must cover exactly the shared evaluation episodes")
        for episode_id, output in outputs.items():
            episode = visible[episode_id]
            if output.visible_content_hash != content_sha256(episode):
                raise ValueError("method output is not bound to the visible episode content")
            support = set(episode.candidate_ids)
            if not set(output.candidate_ranking).issubset(support):
                raise ValueError("method ranking contains candidates outside shared support")
            if output.posterior_by_candidate_id is not None and (
                set(output.posterior_by_candidate_id) != support
            ):
                raise ValueError("probabilistic output must cover the shared candidate support")
            if (
                output.selected_target_candidate_id is not None
                and output.selected_target_candidate_id not in support
            ):
                raise ValueError("selected target is outside shared candidate support")
            if output.observation_actions_used > budget.max_observation_actions:
                raise ValueError("method exceeded the shared observation-action budget")
            if output.execution_actions_used > budget.max_execution_actions:
                raise ValueError("method exceeded the shared execution-action budget")
            if (
                budget.max_path_length_m is not None
                and output.path_length_m > budget.max_path_length_m
            ):
                raise ValueError("method exceeded the shared path-length budget")
            if (
                budget.max_elapsed_seconds is not None
                and output.elapsed_seconds > budget.max_elapsed_seconds
            ):
                raise ValueError("method exceeded the shared elapsed-time budget")

    return DirectionThreeComparisonAudit(
        comparable=True,
        dataset_manifest_hash=manifest_hash,
        evaluation_split=split,
        method_ids=method_ids,
        episode_ids=tuple(sorted(expected_ids, key=str)),
        shared_budget_hash=content_sha256(budget),
        posterior_metric_eligible_method_ids=tuple(
            run.method.method_id for run in runs if run.method.produces_normalized_posterior
        ),
        checks_passed=(
            "same_dataset_manifest",
            "same_visible_episode_content",
            "same_candidate_support",
            "evaluator_truth_firewall",
            "disjoint_tuning_and_evaluation_splits",
            "same_action_and_cost_budget",
            "resource_budget_enforced",
            "posterior_metric_eligibility_declared",
        ),
    )
