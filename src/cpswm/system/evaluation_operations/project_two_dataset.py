"""Quality gates and split-safe container for project-two replay datasets."""

from __future__ import annotations

from collections import Counter
from typing import Protocol
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts import (
    ContractModel,
    ProjectTwoDatasetSplit,
    ProjectTwoEvaluatorTruthEnvelope,
    ProjectTwoReplayDatasetManifest,
    ProjectTwoReplayEpisode,
    reject_truth_leakage,
)
from cpswm.system.reproducibility import content_sha256


class ProjectTwoReplayDataset(ContractModel):
    """Visible episodes plus a separately addressed evaluator store."""

    manifest: ProjectTwoReplayDatasetManifest
    episodes: tuple[ProjectTwoReplayEpisode, ...] = Field(min_length=1)
    evaluator_store: tuple[ProjectTwoEvaluatorTruthEnvelope, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _bindings(self) -> ProjectTwoReplayDataset:
        entries = {item.episode_id: item for item in self.manifest.entries}
        episodes = {item.episode_id: item for item in self.episodes}
        truth = {item.episode_id: item for item in self.evaluator_store}
        if len(episodes) != len(self.episodes):
            raise ValueError("duplicate episode id")
        if len(truth) != len(self.evaluator_store):
            raise ValueError("duplicate evaluator envelope")
        if set(entries) != set(episodes) or set(entries) != set(truth):
            raise ValueError("manifest/episode/evaluator join coverage must be complete")
        for episode_id, episode in episodes.items():
            entry = entries[episode_id]
            envelope = truth[episode_id]
            if episode.split is not entry.split:
                raise ValueError("manifest split does not match episode split")
            object_ids = {step.object_instance_id for step in episode.steps}
            if object_ids != {entry.object_instance_id}:
                raise ValueError("manifest object instance does not match episode")
            if (
                episode.source_hash != entry.source_hash
                or episode.source_hash != envelope.source_hash
            ):
                raise ValueError("source hash mismatch across visible/evaluator stores")
            if entry.visible_content_hash != content_sha256(episode):
                raise ValueError("visible replay content hash mismatch")
            evaluator_payload = envelope.model_dump(
                mode="python", exclude={"evaluator_content_hash"}
            )
            if envelope.evaluator_content_hash != content_sha256(evaluator_payload):
                raise ValueError("evaluator content hash mismatch")
            step_ids = {step.step_id for step in episode.steps}
            if step_ids != set(envelope.truth_by_step):
                raise ValueError("evaluator truth must cover exactly the replay steps")
        return self

    def visible_episodes(
        self, split: ProjectTwoDatasetSplit
    ) -> tuple[ProjectTwoReplayEpisode, ...]:
        episodes = tuple(item for item in self.episodes if item.split is split)
        for episode in episodes:
            reject_truth_leakage(episode.model_dump(mode="python"))
        return episodes

    def truth_for(self, episode_id: UUID) -> ProjectTwoEvaluatorTruthEnvelope:
        return next(item for item in self.evaluator_store if item.episode_id == episode_id)


class ProjectTwoReplayQualityReport(ContractModel):
    dataset_version: str
    episode_count: int = Field(ge=0)
    step_count: int = Field(ge=0)
    feedback_count: int = Field(ge=0)
    observation_coverage: float = Field(ge=0.0, le=1.0)
    delayed_feedback_count: int = Field(ge=0)
    unknown_actor_count: int = Field(ge=0)
    unknown_mechanism_count: int = Field(ge=0)
    evaluator_unknown_actor_count: int = Field(ge=0)
    evaluator_unknown_mechanism_count: int = Field(ge=0)
    family_counts: dict[str, int]
    missingness_counts: dict[str, int]
    checks_passed: tuple[str, ...]
    failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    ready: bool = False


class ProjectTwoReplayGateError(ValueError):
    pass


def audit_project_two_replay(dataset: ProjectTwoReplayDataset) -> ProjectTwoReplayQualityReport:
    """Run schema, ordering, coverage, balance, delay, and leakage checks."""

    steps = [step for episode in dataset.episodes for step in episode.steps]
    feedback = [item for step in steps for item in step.execution_feedback]
    observed = sum(step.after is not None for step in steps)
    delayed = sum(
        item.metadata.recorded_time > step.timestamp
        for step in steps
        for item in step.execution_feedback
    )
    unknown_actor = sum(
        step.actor_evidence is None or "unknown_actor" in step.actor_evidence.actor_posterior
        for step in steps
    )
    unknown_mechanism = sum(
        step.mechanism_evidence is None
        or any(
            key.value == "unknown_mechanism" for key in step.mechanism_evidence.mechanism_posterior
        )
        for step in steps
    )
    truth_items = [
        item for envelope in dataset.evaluator_store for item in envelope.truth_by_step.values()
    ]
    evaluator_unknown_actor = sum(item.true_actor == "unknown_actor" for item in truth_items)
    from cpswm.contracts import EventMechanism

    evaluator_unknown_mechanism = sum(
        item.true_mechanism is EventMechanism.UNKNOWN_MECHANISM for item in truth_items
    )
    missing = Counter(field for step in steps for field in step.unavailable_fields)
    checks: list[str] = []
    failures: list[str] = []
    warnings: list[str] = []

    def passed(name: str, condition: bool, failure: str) -> None:
        if condition:
            checks.append(name)
        else:
            failures.append(failure)

    passed(
        "schema_version",
        all(item.dataset_version == dataset.manifest.dataset_version for item in dataset.episodes),
        "schema/version mismatch",
    )
    passed(
        "missingness",
        all(
            all(field in episode.field_availability for field in step.unavailable_fields)
            for episode in dataset.episodes
            for step in episode.steps
        ),
        "missingness declaration incomplete",
    )
    passed("duplicate_ids", len({step.step_id for step in steps}) == len(steps), "duplicate IDs")
    passed(
        "timestamp_ordering",
        all(
            list(map(lambda item: item.timestamp, episode.steps))
            == sorted(item.timestamp for item in episode.steps)
            for episode in dataset.episodes
        ),
        "timestamp ordering failure",
    )
    passed(
        "feedback_time_ordering",
        all(
            record.metadata.recorded_time >= step.timestamp
            for step in steps
            for record in step.execution_feedback
        ),
        "feedback recorded before its replay step",
    )
    passed("observation_coverage", observed > 0, "zero observation coverage")
    passed("delayed_feedback", delayed > 0, "delayed feedback coverage missing")
    passed(
        "unknown_coverage",
        unknown_actor > 0
        and unknown_mechanism > 0
        and evaluator_unknown_actor > 0
        and evaluator_unknown_mechanism > 0,
        "unknown actor/mechanism coverage missing",
    )
    passed(
        "class_family_balance",
        all(
            any(item.split is split for item in dataset.episodes)
            for split in ProjectTwoDatasetSplit
        ),
        "validation/test family coverage missing",
    )
    for episode in dataset.episodes:
        reject_truth_leakage(episode.model_dump(mode="python"))
    checks.extend(
        (
            "identity_consistency",
            "join_coverage",
            "source_label_leakage",
            "household_scene_object_family_split",
            "visible_content_integrity",
            "evaluator_content_integrity",
        )
    )
    if missing:
        warnings.append(
            "declared unavailable fields remain and must be collected at higher maturity"
        )
    return ProjectTwoReplayQualityReport(
        dataset_version=dataset.manifest.dataset_version,
        episode_count=len(dataset.episodes),
        step_count=len(steps),
        feedback_count=len(feedback),
        observation_coverage=observed / len(steps) if steps else 0.0,
        delayed_feedback_count=delayed,
        unknown_actor_count=unknown_actor,
        unknown_mechanism_count=unknown_mechanism,
        evaluator_unknown_actor_count=evaluator_unknown_actor,
        evaluator_unknown_mechanism_count=evaluator_unknown_mechanism,
        family_counts=dict(Counter(item.object_family for item in dataset.episodes)),
        missingness_counts=dict(missing),
        checks_passed=tuple(checks),
        failures=tuple(failures),
        warnings=tuple(warnings),
        ready=not failures,
    )


def enforce_project_two_replay_gate(
    dataset: ProjectTwoReplayDataset,
) -> ProjectTwoReplayQualityReport:
    report = audit_project_two_replay(dataset)
    if report.failures:
        raise ProjectTwoReplayGateError("; ".join(report.failures))
    return report


class ProjectTwoReplayConsumer(Protocol):
    """Model-facing consumers accept visible episodes only, never truth stores."""

    def consume_episode(self, episode: ProjectTwoReplayEpisode) -> object: ...


__all__ = [
    "ProjectTwoReplayConsumer",
    "ProjectTwoReplayDataset",
    "ProjectTwoReplayGateError",
    "ProjectTwoReplayQualityReport",
    "audit_project_two_replay",
    "enforce_project_two_replay_gate",
]
