"""Development point reports and isolated identity/AABB evaluation.

Reports are detached values, not owner receipts or natural-identity certificates.
The evaluator's instance annotation and bounds must come from an independent
source. No truth object is accepted by the report builder or the policy.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Literal, Self
from uuid import UUID

import numpy as np
from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, require_aware
from cpswm.system.evaluation_operations.structure_two_selected_method import TypedParticleState
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_joint_consumption import JointDecisionView

if TYPE_CHECKING:
    from cpswm.system.structure_two_continuous_input import ContinuousEvidenceInput

Finite = Annotated[float, Field(allow_inf_nan=False)]
Point = tuple[Finite, Finite, Finite]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ReportTask(ContractModel):
    """Public, predeclared task; includes no evaluator instance or target box."""

    task_id: UUID
    scene_id: str = Field(min_length=1)
    frame_id: str = Field(min_length=1)
    target_description: str = Field(min_length=1)
    valid_at: datetime
    initial_input_sha256: Digest
    allowed_actions_sha256: Digest
    action_budget: int = Field(ge=0, strict=True)
    # Explicit origin of the conditional position model, not target truth.
    position_origin_m: Point

    @field_validator("valid_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return require_aware(value, "valid_at")

    @property
    def digest(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


class TargetPositionReport(ContractModel):
    task_sha256: Digest
    source_view_sha256: Digest
    status: Literal["reported", "unknown", "failed"]
    particle_id: UUID | None
    instance_hypothesis: str | None
    point_m: Point | None
    observation_ids: tuple[UUID, ...]
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def shape(self) -> Self:
        complete = (
            self.particle_id is not None
            and self.instance_hypothesis is not None
            and self.instance_hypothesis not in {"", "unknown_instance"}
            and self.point_m is not None
            and bool(self.observation_ids)
        )
        if self.status == "reported":
            if not complete:
                raise ValueError("reported point requires identity hypothesis and observations")
        elif any(x is not None for x in (self.particle_id, self.instance_hypothesis, self.point_m)):
            raise ValueError("unknown/failed report must not invent an identity or point")
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ValueError("duplicate report observation")
        return self

    @property
    def digest(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


def report_from_view(
    task: ReportTask,
    view: JointDecisionView,
    *,
    particle_id: UUID | None,
    observation_ids: tuple[UUID, ...],
) -> TargetPositionReport:
    """Read a selected hypothesis; never choose one using evaluator truth.

    The caller supplies the current owner-validated view and effective observation
    IDs. This value-only adapter does not authenticate those inputs. The six-state
    position model is [xyz, remaining state], relative to the declared origin.
    """
    task = ReportTask.model_validate(task.model_dump())
    common = dict(
        task_sha256=task.digest,
        source_view_sha256=view.content_sha256,
        observation_ids=observation_ids,
    )
    if particle_id is None or particle_id == view.unresolved_id:
        return TargetPositionReport(
            **common,
            status="unknown",
            particle_id=None,
            instance_hypothesis=None,
            point_m=None,
            reason="no_resolved_hypothesis_selected",
        )
    atoms = [a for a in view.atoms if a.particle_id == particle_id]
    if len(atoms) != 1:
        raise ValueError("selected hypothesis is absent or duplicated in current view")
    atom = atoms[0]
    state = TypedParticleState.model_validate_json(atom.state_json)
    if state.instance_association_key == "unknown_instance":
        return TargetPositionReport(
            **common,
            status="unknown",
            particle_id=None,
            instance_hypothesis=None,
            point_m=None,
            reason="no_resolved_hypothesis_selected",
        )
    if state.particle_id != particle_id or state.statistic_state_ref != atom.statistics.reference:
        raise ValueError("selected state/statistics binding differs")
    precision = np.asarray(atom.statistics.information)
    natural = np.asarray(atom.statistics.information_vector)
    if precision.shape != (6, 6) or natural.shape != (6,):
        raise ValueError("report requires the declared six-state position model")
    mean = np.linalg.solve(precision, natural)[:3] + np.asarray(task.position_origin_m)
    return TargetPositionReport(
        **common,
        status="reported",
        particle_id=particle_id,
        instance_hypothesis=state.instance_association_key,
        point_m=tuple(mean.tolist()),
        reason="selected_conditional_position_mean",
    )


def verify_report(
    task: ReportTask,
    view: JointDecisionView,
    report: TargetPositionReport,
    *,
    observation_ids: tuple[UUID, ...],
) -> None:
    """Compare against current inputs, rejecting stale or altered point reports."""
    report = TargetPositionReport.model_validate(report.model_dump())
    expected = report_from_view(
        task, view, particle_id=report.particle_id, observation_ids=observation_ids
    )
    if report != expected:
        raise ValueError("report differs from current task/view/observations")


def report_owned_temporal_target(
    stream: ContinuousEvidenceInput,
    task: ReportTask,
    *,
    particle_id: UUID | None,
) -> TargetPositionReport:
    """Read current owner state and effective capture lineage under its locks.

    This first adapter reports the last capture epoch in the approved static temporal
    profile. It does not extrapolate an old position to a later task time.
    """
    from cpswm.perception_mapping.unity_rgbd import decode_unity_rgbd
    from cpswm.system.native_joint_replay import consumed_schedule
    from cpswm.system.owned_position_update import uses_temporal

    task = ReportTask.model_validate(task.model_dump())
    with stream._lock, stream._system.core._execution_lock:
        view = stream.current_joint_decision_view()
        if not uses_temporal(stream):
            raise ValueError("owned report requires the temporal position profile")
        schedule = consumed_schedule(stream._system.core._particle_workspace)
        contexts = [
            u.context
            for u in schedule
            if u.context is not None and u.context.observation_update is not None
        ]
        if not contexts:
            if particle_id is not None and particle_id != view.unresolved_id:
                raise ValueError("no effective position captures for an identity report")
            return report_from_view(task, view, particle_id=None, observation_ids=())
        ids: list[UUID] = []
        cameras = []
        for context in contexts:
            update = context.observation_update
            assert update is not None
            if update.action_id in stream._position_withdrawals:
                raise ValueError("withdrawn capture remains in current report lineage")
            lookup = {str(r.envelope().identity.observation_id): r for r in context.visible_prefix}
            keys = update.packet["observation_ids"]
            camera, _ = decode_unity_rgbd(tuple(lookup[k] for k in keys), cutoff=update.received_at)
            cameras.append(camera)
            ids.extend(UUID(k) for k in keys)
        first = contexts[0].observation_update
        assert first is not None
        if (
            any(c.scene_sha256 != task.scene_id or c.world_frame != task.frame_id for c in cameras)
            or task.valid_at != cameras[-1].capture_time
            or task.initial_input_sha256 != first.packet["raw_sha256"]
            or task.position_origin_m != (0.0, 0.0, 0.0)
            or contexts[-1].source.snapshot_id != view.snapshot_id
        ):
            raise ValueError(
                "task scene/frame/epoch/origin or semantic state differs from captures"
            )
        return report_from_view(task, view, particle_id=particle_id, observation_ids=tuple(ids))


class EvaluationTruth(ContractModel):
    """Evaluator-only annotation; hashes bind inputs but do not certify labels."""

    task_sha256: Digest
    report_sha256: Digest
    annotation_artifact_sha256: Digest
    target_instance_id: str = Field(min_length=1)
    # None means unadjudicated, not a negative identity annotation.
    reported_instance_id: str | None = Field(default=None, min_length=1)
    lower_m: Point
    upper_m: Point

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if any(lo >= hi for lo, hi in zip(self.lower_m, self.upper_m, strict=True)):
            raise ValueError("target AABB must have positive extent on each axis")
        return self


class ReportAssessment(ContractModel):
    task_sha256: Digest
    report_sha256: Digest | None
    truth_sha256: Digest | None
    identity_correct: bool | None
    position_correct: bool | None
    joint_success: bool | None
    reason: str


def assess_report(
    task: ReportTask,
    report: TargetPositionReport | None,
    truth: EvaluationTruth | None,
) -> ReportAssessment:
    """Inclusive, unexpanded AABB test. Missing truth stays unadjudicated."""
    task = ReportTask.model_validate(task.model_dump())
    if report is not None:
        report = TargetPositionReport.model_validate(report.model_dump())
        if report.task_sha256 != task.digest:
            raise ValueError("report belongs to another task/frame/time")
    if truth is not None:
        truth = EvaluationTruth.model_validate(truth.model_dump())
        if report is None or (truth.task_sha256, truth.report_sha256) != (
            task.digest,
            report.digest,
        ):
            raise ValueError("truth annotation does not bind this task and report")
    common = dict(
        task_sha256=task.digest,
        report_sha256=report.digest if report else None,
        truth_sha256=content_sha256(truth.model_dump(mode="json")) if truth else None,
    )
    if report is None or report.status != "reported":
        return ReportAssessment(
            **common,
            identity_correct=False,
            position_correct=False,
            joint_success=False,
            reason="missing_report" if report is None else report.reason,
        )
    if truth is None:
        return ReportAssessment(
            **common,
            identity_correct=None,
            position_correct=None,
            joint_success=None,
            reason="missing_evaluator_truth",
        )
    assert report.point_m is not None
    position = all(
        lo <= x <= hi
        for x, lo, hi in zip(report.point_m, truth.lower_m, truth.upper_m, strict=True)
    )
    identity = (
        None
        if truth.reported_instance_id is None
        else truth.reported_instance_id == truth.target_instance_id
    )
    return ReportAssessment(
        **common,
        identity_correct=identity,
        position_correct=position,
        joint_success=False if not position else (None if identity is None else identity),
        reason="identity_unadjudicated" if identity is None else "evaluated",
    )


def summarize_reports(
    tasks: tuple[ReportTask, ...],
    rows: tuple[tuple[TargetPositionReport | None, EvaluationTruth | None], ...],
) -> dict[str, object]:
    """Score the full predeclared manifest; missing outputs keep their slots."""
    if len(tasks) != len(rows) or len({t.task_id for t in tasks}) != len(tasks) or not tasks:
        raise ValueError("nonempty unique task manifest and one output slot per task required")
    scores = [assess_report(t, r, g) for t, (r, g) in zip(tasks, rows, strict=True)]
    return dict(
        task_count=len(tasks),
        identity_correct=sum(s.identity_correct is True for s in scores),
        position_correct=sum(s.position_correct is True for s in scores),
        joint_success=sum(s.joint_success is True for s in scores),
        unadjudicated=sum(s.identity_correct is None or s.position_correct is None for s in scores),
        joint_success_rate=sum(s.joint_success is True for s in scores) / len(tasks),
        assessments=[s.model_dump(mode="json") for s in scores],
    )


class CameraAttempt(ContractModel):
    """One physical dispatch, including failures; transport must supply the log."""

    action_id: UUID
    action: Literal["Pass", "RotateLeft", "RotateRight"]
    degrees: Finite = Field(ge=0, le=90)
    success: bool
    elapsed_seconds: Finite = Field(ge=0)

    @model_validator(mode="after")
    def movement(self) -> Self:
        if (self.action == "Pass") != (self.degrees == 0):
            raise ValueError("Pass has zero rotation; turns have positive rotation")
        return self


class ReportRun(ContractModel):
    task: ReportTask
    policy_id: str = Field(min_length=1)
    attempts: tuple[CameraAttempt, ...]
    report: TargetPositionReport | None
    stop_reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def budget(self) -> Self:
        if len({a.action_id for a in self.attempts}) != len(self.attempts):
            raise ValueError("duplicate physical dispatch id")
        if self.report is not None and self.report.task_sha256 != self.task.digest:
            raise ValueError("run/report task differs")
        return self


def compare_report_runs(
    first: tuple[ReportRun, ...],
    second: tuple[ReportRun, ...],
    *,
    first_truth: tuple[EvaluationTruth | None, ...],
    second_truth: tuple[EvaluationTruth | None, ...],
) -> dict[str, object]:
    """Paired offline summary, never authentication of the supplied action logs.

    Budget overruns stay visible and are not deleted from the manifest. Their
    endpoint reports can be scored, but the comparison cannot support a fair-benefit
    claim. Allowed-action hashes bind the design; legality still requires the
    executor's independently validated dispatch log.
    """
    groups = []
    reference = None
    fair = True
    for runs, truths in ((first, first_truth), (second, second_truth)):
        runs = tuple(ReportRun.model_validate(r.model_dump()) for r in runs)
        if not runs or len(runs) != len(truths) or len({r.policy_id for r in runs}) != 1:
            raise ValueError("each policy requires a complete manifest and truth slots")
        identities = tuple(r.task.digest for r in runs)
        if reference is not None and identities != reference:
            raise ValueError("paired tasks, initial inputs, allowed actions or budgets differ")
        reference = identities
        over = [str(r.task.task_id) for r in runs if len(r.attempts) > r.task.action_budget]
        fair = fair and not over
        score = summarize_reports(
            tuple(r.task for r in runs),
            tuple((r.report, g) for r, g in zip(runs, truths, strict=True)),
        )
        groups.append(
            dict(
                policy_id=runs[0].policy_id,
                score=score,
                over_budget_task_ids=over,
                actions=sum(len(r.attempts) for r in runs),
                failed_actions=sum(not a.success for r in runs for a in r.attempts),
                cumulative_degrees=sum(a.degrees for r in runs for a in r.attempts),
                elapsed_seconds=sum(a.elapsed_seconds for r in runs for a in r.attempts),
                stop_reasons=[r.stop_reason for r in runs],
            )
        )
    return dict(
        paired_design_and_count_budget_valid=fair,
        action_log_authentication="external_requirement",
        groups=groups,
    )
