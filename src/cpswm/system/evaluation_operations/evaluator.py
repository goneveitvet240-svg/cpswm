"""M32 evaluator for the first reproducible F0 longitudinal slice."""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError, model_validator

from cpswm.contracts import (
    ObservationDetectionResult,
    ObservationOpportunityRecord,
    ObservationOutcome,
)
from cpswm.contracts.base import ContractModel
from cpswm.foundation.runtime_orchestration.provenance import (
    DIRTY_WORKING_TREE_SUFFIX,
    UNVERSIONED_CODE_VERSION,
    RuntimeProvenanceError,
    file_sha256,
    git_head_code_version,
    source_tree_sha256,
)
from cpswm.system.household_memory_benchmark import (
    BenchmarkManifest,
    BenchmarkTaskFamily,
    EvaluationTrack,
)
from cpswm.system.reproducibility import content_sha256, content_uuid
from cpswm.system.world_model_simulator import (
    SymbolicSimulationResult,
    detection_result_record_id,
    simulation_run_identity,
)
from cpswm.system.world_model_simulator.symbolic import (
    PrivilegedSymbolicSimulationView,
)
from cpswm_gt import (
    GroundTruthHabitTrajectory,
    GTHabitRegimeKind,
    GTInteractionEvent,
    GTPlacementEvent,
)

_METRIC_TASKS = {
    "controlled_observation_recall": BenchmarkTaskFamily.MEMORY_ACCURACY,
    "anomaly_observation_recall": BenchmarkTaskFamily.ADAPTATION,
    "incidental_context_coverage": BenchmarkTaskFamily.EXPLANATION,
    "declared_primary_task_additional_action_cost_total": (BenchmarkTaskFamily.EMBODIED_UTILITY),
}
_BOUNDED_RATE_METRICS = frozenset(
    {
        "controlled_observation_recall",
        "anomaly_observation_recall",
        "incidental_context_coverage",
    }
)


#: Repository root inferred from this module's location.
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class EvaluationProvenance(ContractModel):
    """Measured identity of the code that produced an evaluation report.

    ``evaluator_version`` alone is a hardcoded literal and therefore a claim,
    not a measurement: changing the metric computation does not change it.  The
    hashes below are measured from the running tree, so an altered evaluator
    cannot present itself as the released one.
    """

    code_version: str = Field(min_length=1)
    source_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_module_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    #: ``None`` means the working-tree state could not be determined at all.
    #: It is never silently reported as clean.
    working_tree_clean: bool | None

    @model_validator(mode="after")
    def validate_working_tree_claim(self) -> EvaluationProvenance:
        if self.code_version == UNVERSIONED_CODE_VERSION:
            if self.working_tree_clean is not None:
                raise ValueError("an unversioned tree cannot claim a known working-tree state")
            return self
        marked_dirty = self.code_version.endswith(DIRTY_WORKING_TREE_SUFFIX)
        if self.working_tree_clean is None:
            raise ValueError("a versioned tree must state its working-tree state")
        if self.working_tree_clean is marked_dirty:
            raise ValueError("working_tree_clean contradicts the recorded code_version")
        return self

    @classmethod
    def measure(cls, repository_root: Path | str | None = None) -> EvaluationProvenance:
        root = Path(repository_root or REPOSITORY_ROOT).resolve()
        try:
            code_version = git_head_code_version(root)
            # Unknown is not clean: without Git we cannot rule out local edits.
            working_tree_clean: bool | None = not code_version.endswith(DIRTY_WORKING_TREE_SUFFIX)
        except RuntimeProvenanceError:
            code_version = UNVERSIONED_CODE_VERSION
            working_tree_clean = None
        return cls(
            code_version=code_version,
            source_tree_sha256=source_tree_sha256(root),
            evaluator_module_sha256=file_sha256(Path(__file__).resolve()),
            working_tree_clean=working_tree_clean,
        )

    def verify_against(self, repository_root: Path | str | None = None) -> None:
        """Raise unless this block matches code measured from ``repository_root``.

        A report cannot authenticate itself: its self-hash only proves internal
        consistency, so a forger who recomputes every derived field produces a
        valid-looking report.  This is the reviewer-side check that turns the
        recorded provenance into a claim that can actually be falsified against
        a checkout.
        """

        measured = type(self).measure(repository_root)
        if self.source_tree_sha256 != measured.source_tree_sha256:
            raise ValueError("reported source_tree_sha256 does not match the checked-out tree")
        if self.evaluator_module_sha256 != measured.evaluator_module_sha256:
            raise ValueError(
                "reported evaluator_module_sha256 does not match the checked-out evaluator"
            )

    @property
    def content_sha256(self) -> str:
        return content_sha256(self.model_dump(mode="json"))


def evaluation_run_identity(
    *,
    manifest_id: str,
    manifest_version: str,
    manifest_sha256: str,
    simulation_run_id: UUID,
    simulation_content_sha256: str,
    track: EvaluationTrack,
    evaluator_version: str,
    provenance_sha256: str,
) -> UUID:
    """Return the canonical identity for a fully bound evaluation run."""

    return content_uuid(
        "evaluation-run",
        {
            "manifest_id": manifest_id,
            "manifest_version": manifest_version,
            "manifest_sha256": manifest_sha256,
            "simulation_run_id": simulation_run_id,
            "simulation_content_sha256": simulation_content_sha256,
            "track": track,
            "evaluator_version": evaluator_version,
            "provenance_sha256": provenance_sha256,
        },
    )


class MetricRecord(ContractModel):
    metric_id: UUID
    benchmark_manifest_id: str = Field(min_length=1)
    benchmark_manifest_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    benchmark_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_run_id: UUID
    simulation_run_id: UUID
    track: EvaluationTrack
    task_family: BenchmarkTaskFamily
    metric_name: str = Field(min_length=1)
    value: float | None
    sample_count: int = Field(ge=0)


class EvaluationReport(ContractModel):
    evaluation_run_id: UUID
    evaluation_report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    benchmark_manifest_id: str = Field(min_length=1)
    benchmark_manifest_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    benchmark_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    routine_plan_id: UUID
    routine_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    observation_policy_id: str = Field(min_length=1)
    observation_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    simulation_run_id: UUID
    simulation_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    simulator_version: str = Field(min_length=1)
    track: EvaluationTrack
    metrics: tuple[MetricRecord, ...] = Field(min_length=1)
    ground_truth_leakage_detected: bool
    failure_reasons: tuple[str, ...] = ()
    evaluator_version: str = "f0-evaluator@0.10"
    provenance: EvaluationProvenance

    @model_validator(mode="after")
    def validate_identity_bindings_and_content_hash(self) -> EvaluationReport:
        expected_run_id = evaluation_run_identity(
            manifest_id=self.benchmark_manifest_id,
            manifest_version=self.benchmark_manifest_version,
            manifest_sha256=self.benchmark_manifest_sha256,
            simulation_run_id=self.simulation_run_id,
            simulation_content_sha256=self.simulation_content_sha256,
            track=self.track,
            evaluator_version=self.evaluator_version,
            provenance_sha256=self.provenance.content_sha256,
        )
        if self.evaluation_run_id != expected_run_id:
            raise ValueError("evaluation_run_id does not match evaluation report inputs")

        # Reject an unauthenticated payload before reporting any downstream
        # semantic inconsistency.  Rehashed adversarial fixtures still reach
        # the detailed binding and metric validators below.
        expected_hash = content_sha256(self.content_payload())
        if self.evaluation_report_sha256 != expected_hash:
            raise ValueError("evaluation_report_sha256 does not match evaluation report content")

        metric_names = [metric.metric_name for metric in self.metrics]
        metric_ids = [metric.metric_id for metric in self.metrics]
        if len(metric_names) != len(set(metric_names)):
            raise ValueError("evaluation report metric names must be unique")
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("evaluation report metric IDs must be unique")

        for metric in self.metrics:
            report_bindings = {
                "benchmark_manifest_id": self.benchmark_manifest_id,
                "benchmark_manifest_version": self.benchmark_manifest_version,
                "benchmark_manifest_sha256": self.benchmark_manifest_sha256,
                "evaluation_run_id": self.evaluation_run_id,
                "simulation_run_id": self.simulation_run_id,
                "track": self.track,
            }
            for field_name, expected in report_bindings.items():
                if getattr(metric, field_name) != expected:
                    raise ValueError(f"metric {field_name} does not match evaluation report")
            expected_metric_id = content_uuid(
                "metric",
                {
                    "evaluation_run_id": self.evaluation_run_id,
                    "name": metric.metric_name,
                },
            )
            if metric.metric_id != expected_metric_id:
                raise ValueError("metric_id does not match metric identity")
            expected_task = _METRIC_TASKS.get(metric.metric_name)
            if expected_task is None:
                raise ValueError(f"unsupported report metric: {metric.metric_name}")
            if metric.task_family != expected_task:
                raise ValueError("metric task family does not match metric name")

            if metric.metric_name in _BOUNDED_RATE_METRICS:
                if metric.sample_count == 0:
                    if metric.value is not None:
                        raise ValueError("zero-sample rate metric must have an undefined value")
                elif metric.value is None or not 0.0 <= metric.value <= 1.0:
                    raise ValueError("rate metric value must be in [0, 1]")
            else:
                if metric.value is None or metric.value < 0.0:
                    raise ValueError("declared action cost must be non-negative")
                if metric.sample_count == 0 and metric.value != 0.0:
                    raise ValueError("zero-sample declared action cost must equal zero")

        if self.ground_truth_leakage_detected != bool(self.failure_reasons):
            raise ValueError("ground-truth leakage flag must match failure reasons")
        return self

    def content_payload(self) -> dict[str, object]:
        """Return the complete report payload except its self hash."""

        return self.model_dump(mode="json", exclude={"evaluation_report_sha256"})

    def metric_value(self, name: str) -> float | None:
        matches = [metric.value for metric in self.metrics if metric.metric_name == name]
        if len(matches) != 1:
            raise KeyError(f"expected exactly one metric named {name!r}")
        return matches[0]


class EvaluationRunner:
    """Compare finite observations with truth without leaking truth to the model."""

    _METRIC_TASKS = _METRIC_TASKS
    _SUPPORTED_MANIFEST_VERSIONS = frozenset({"0.4.0"})

    def evaluate(
        self,
        manifest: BenchmarkManifest,
        benchmark_view: PrivilegedSymbolicSimulationView,
        *,
        track: EvaluationTrack,
        provenance: EvaluationProvenance | None = None,
    ) -> EvaluationReport:
        manifest = self._revalidate_manifest(manifest)
        benchmark_view = self._revalidate_benchmark_view(benchmark_view)
        simulation = benchmark_view.visible_result
        if track not in manifest.tracks:
            raise ValueError("evaluation track is not enabled by the manifest")
        self._validate_manifest_binding(manifest, benchmark_view)
        # Measured, not declared: an altered evaluator yields a different
        # source/module hash and therefore a different evaluation_run_id.
        measured_provenance = EvaluationProvenance.measure()
        if provenance is not None and provenance != measured_provenance:
            raise ValueError("declared evaluation provenance does not match the running code")
        provenance = measured_provenance
        evaluation_run_id = evaluation_run_identity(
            manifest_id=manifest.manifest_id,
            manifest_version=manifest.manifest_version,
            manifest_sha256=manifest.manifest_sha256,
            simulation_run_id=simulation.simulation_run_id,
            simulation_content_sha256=simulation.simulation_content_sha256,
            track=track,
            evaluator_version=EvaluationReport.model_fields["evaluator_version"].default,
            provenance_sha256=measured_provenance.content_sha256,
        )
        truth = benchmark_view.ground_truth.events
        scored_truth = tuple(
            event
            for event in truth
            if event.object_gt_entity_id == simulation.scheduled_observation_object_id
        )
        opportunities = simulation.observation_opportunities
        results = simulation.detection_results
        detected = [item for item in results if item.outcome == ObservationOutcome.DETECTED]
        # This metric is deliberately scoped to temporary/isolated exceptions.
        # Contextual routines and persistent gradual/abrupt changes are not
        # anomalies and require separate adaptation metrics.
        anomaly_truth = [
            event
            for event in scored_truth
            if event.regime_kind == GTHabitRegimeKind.TEMPORARY_EXCEPTION
        ]
        matched_truth_ids = self._match_unique_truth_events(
            detected,
            scored_truth,
            maximum_delay=timedelta(hours=manifest.session_duration_hours),
        )
        # Match anomalies independently. Intersecting an arbitrary maximum
        # matching over all truth with anomaly IDs can undercount anomalies
        # when more than one equal-cardinality assignment exists.
        matched_anomaly_ids = self._match_unique_truth_events(
            detected,
            tuple(anomaly_truth),
            maximum_delay=timedelta(hours=manifest.session_duration_hours),
        )
        detected_anomalies = len(matched_anomaly_ids)
        failures = self._detect_ground_truth_leakage(
            simulation,
            truth,
            interaction_events=benchmark_view.ground_truth.interaction_events,
        )
        leakage = bool(failures)

        available_metrics = {
            "controlled_observation_recall": (
                len(matched_truth_ids) / len(scored_truth) if scored_truth else None,
                len(scored_truth),
            ),
            "anomaly_observation_recall": (
                detected_anomalies / len(anomaly_truth) if anomaly_truth else None,
                len(anomaly_truth),
            ),
            "incidental_context_coverage": (
                sum(item.incidental_context is not None for item in opportunities)
                / len(opportunities)
                if opportunities
                else None,
                len(opportunities),
            ),
            # This is a policy-declared diagnostic, not execution telemetry.
            # Actual primary-task delay/interruption requires M23-M27 action
            # records and is intentionally outside this F0 report.
            "declared_primary_task_additional_action_cost_total": (
                sum(
                    item.incidental_context.additional_action_cost
                    for item in opportunities
                    if item.selected and item.incidental_context is not None
                ),
                sum(
                    item.selected and item.incidental_context is not None for item in opportunities
                ),
            ),
        }
        metrics = tuple(
            MetricRecord(
                metric_id=content_uuid(
                    "metric", {"evaluation_run_id": evaluation_run_id, "name": metric_name}
                ),
                benchmark_manifest_id=manifest.manifest_id,
                benchmark_manifest_version=manifest.manifest_version,
                benchmark_manifest_sha256=manifest.manifest_sha256,
                evaluation_run_id=evaluation_run_id,
                simulation_run_id=simulation.simulation_run_id,
                track=track,
                task_family=self._METRIC_TASKS[metric_name],
                metric_name=metric_name,
                value=available_metrics[metric_name][0],
                sample_count=available_metrics[metric_name][1],
            )
            for metric_name in manifest.metric_names
        )
        evaluator_version = EvaluationReport.model_fields["evaluator_version"].default
        report_payload = dict(
            evaluation_run_id=evaluation_run_id,
            benchmark_manifest_id=manifest.manifest_id,
            benchmark_manifest_version=manifest.manifest_version,
            benchmark_manifest_sha256=manifest.manifest_sha256,
            routine_plan_id=benchmark_view.routine_plan_id,
            routine_plan_sha256=benchmark_view.routine_plan_sha256,
            observation_policy_id=simulation.observation_policy_id,
            observation_policy_sha256=simulation.observation_policy_sha256,
            simulation_run_id=simulation.simulation_run_id,
            simulation_content_sha256=simulation.simulation_content_sha256,
            simulator_version=simulation.simulator_version,
            track=track,
            metrics=metrics,
            ground_truth_leakage_detected=leakage,
            failure_reasons=failures,
            evaluator_version=evaluator_version,
            provenance=provenance,
        )
        return EvaluationReport(
            **report_payload,
            evaluation_report_sha256=content_sha256(report_payload),
        )

    _PRIVILEGED_EVIDENCE_PATTERN = re.compile(
        r"(?:^|[^a-z0-9])(?:ground[\s_.:/-]*truth|gt[\s_.:/-]*event|privileged)"
        r"(?:$|[^a-z0-9])",
        re.IGNORECASE,
    )

    @classmethod
    def _detect_ground_truth_leakage(
        cls,
        simulation: SymbolicSimulationResult,
        truth_events: tuple[GTPlacementEvent, ...],
        *,
        interaction_events: tuple[GTInteractionEvent, ...] = (),
    ) -> tuple[str, ...]:
        """Detect explicit privileged references in robot-visible records.

        Every UUID and string carrier is scanned, including metadata and
        ``EvidenceRef`` values. Exact GT event UUIDs and explicit privileged
        labels are forbidden. Ordinary object/location identities remain valid
        successful detection outputs and are outside this detector's scope.
        """

        gt_event_ids = {event.gt_event_id for event in truth_events} | {
            event.gt_event_id for event in interaction_events
        }
        gt_event_tokens = {
            token.casefold() for event_id in gt_event_ids for token in (str(event_id), event_id.hex)
        }
        failures: list[str] = []
        for path, value in cls._iter_scalar_carriers(simulation, "visible_result"):
            reason: str | None = None
            if isinstance(value, UUID) and value in gt_event_ids:
                reason = "value references a gt_event_id"
            elif isinstance(value, str):
                folded = value.casefold()
                if cls._PRIVILEGED_EVIDENCE_PATTERN.search(value):
                    reason = "value declares privileged ground truth"
                elif any(token in folded for token in gt_event_tokens):
                    reason = "value embeds a gt_event_id"
            if reason is not None:
                failures.append(f"ground-truth leakage at {path}: {reason}")
        return tuple(failures)

    @classmethod
    def _iter_scalar_carriers(
        cls,
        value: object,
        path: str,
    ) -> Iterator[tuple[str, UUID | str]]:
        """Yield all UUID/string carriers recursively with stable paths."""

        if isinstance(value, (UUID, str)):
            yield path, value
            return
        if isinstance(value, BaseModel):
            for field_name in type(value).model_fields:
                yield from cls._iter_scalar_carriers(
                    getattr(value, field_name),
                    f"{path}.{field_name}",
                )
            return
        if isinstance(value, dict):
            for key in sorted(value, key=str):
                yield from cls._iter_scalar_carriers(
                    key,
                    f"{path}.<key>",
                )
                yield from cls._iter_scalar_carriers(
                    value[key],
                    f"{path}[{key!r}]",
                )
            return
        if isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                yield from cls._iter_scalar_carriers(
                    nested,
                    f"{path}[{index}]",
                )

    @classmethod
    def _reject_model_copy_extras(cls, value: object, path: str) -> None:
        """Reject attributes injected by ``model_copy(update=...)``.

        Pydantic deliberately does not validate ``model_copy`` updates, and its
        serializer silently omits injected attributes on models with
        ``extra='forbid'``.  Checking the live field set before round-tripping
        closes that evaluator-boundary bypass for manifests, simulation output,
        ground truth, and every nested record.
        """

        if isinstance(value, BaseModel):
            expected = set(type(value).model_fields)
            unexpected = set(vars(value)) - expected
            if unexpected:
                raise ValueError(
                    f"{path} contains fields outside its contract: {sorted(unexpected)}"
                )
            for field_name in expected:
                cls._reject_model_copy_extras(getattr(value, field_name), f"{path}.{field_name}")
        elif isinstance(value, dict):
            for key, nested in value.items():
                cls._reject_model_copy_extras(nested, f"{path}[{key!r}]")
        elif isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                cls._reject_model_copy_extras(nested, f"{path}[{index}]")

    @classmethod
    def _revalidate_manifest(cls, manifest: BenchmarkManifest) -> BenchmarkManifest:
        cls._reject_model_copy_extras(manifest, "benchmark manifest")
        try:
            validated = BenchmarkManifest.model_validate(manifest.model_dump(mode="python"))
        except (AttributeError, ValidationError) as exc:
            raise ValueError(f"invalid benchmark manifest: {exc}") from exc
        expected_hash = content_sha256(validated._identity_payload())
        if validated.manifest_sha256 != expected_hash:
            raise ValueError("benchmark manifest hash does not match its content")
        return validated

    @classmethod
    def _revalidate_simulation(
        cls, simulation: SymbolicSimulationResult
    ) -> SymbolicSimulationResult:
        cls._reject_model_copy_extras(simulation, "symbolic simulation result")
        try:
            expected_hash = content_sha256(simulation.content_payload())
        except AttributeError as exc:
            raise ValueError("invalid symbolic simulation result") from exc
        if simulation.simulation_content_sha256 != expected_hash:
            raise ValueError(
                "simulation content hash does not match the complete simulation output"
            )

        try:
            return SymbolicSimulationResult.model_validate(simulation.model_dump(mode="python"))
        except ValidationError as exc:
            raise ValueError(f"invalid symbolic simulation result: {exc}") from exc

    @classmethod
    def _revalidate_benchmark_view(
        cls, benchmark_view: PrivilegedSymbolicSimulationView
    ) -> PrivilegedSymbolicSimulationView:
        cls._reject_model_copy_extras(benchmark_view, "privileged simulation view")
        try:
            expected_hash = content_sha256(benchmark_view.content_payload())
        except AttributeError as exc:
            raise ValueError("invalid privileged simulation view") from exc
        if benchmark_view.privileged_content_sha256 != expected_hash:
            raise ValueError(
                "privileged simulation content hash does not match view content; "
                "privileged content hash verification failed"
            )
        cls._revalidate_simulation(benchmark_view.visible_result)
        try:
            validated_truth = GroundTruthHabitTrajectory.model_validate(
                benchmark_view.ground_truth.model_dump(mode="python")
            )
        except (AttributeError, ValidationError) as exc:
            raise ValueError(f"invalid ground-truth trajectory: {exc}") from exc
        try:
            validated = PrivilegedSymbolicSimulationView.model_validate(
                benchmark_view.model_dump(mode="python")
            )
        except (AttributeError, ValidationError) as exc:
            raise ValueError(f"invalid privileged simulation view: {exc}") from exc
        if validated.ground_truth != validated_truth:
            raise ValueError("validated ground-truth trajectory changed during parsing")
        return validated

    def _validate_manifest_binding(
        self,
        manifest: BenchmarkManifest,
        benchmark_view: PrivilegedSymbolicSimulationView,
    ) -> None:
        simulation = benchmark_view.visible_result
        if manifest.manifest_version not in self._SUPPORTED_MANIFEST_VERSIONS:
            raise ValueError(f"unsupported benchmark manifest version: {manifest.manifest_version}")
        if simulation.random_seed != manifest.random_seed:
            raise ValueError("simulation random seed does not match benchmark manifest")
        if benchmark_view.routine_plan_id != manifest.routine_plan_id:
            raise ValueError("simulation routine plan ID does not match benchmark manifest")
        if benchmark_view.routine_plan_sha256 != manifest.routine_plan_sha256:
            raise ValueError("simulation routine plan hash does not match benchmark manifest")
        if simulation.observation_policy_id != manifest.observation_policy_id:
            raise ValueError("simulation policy ID does not match benchmark manifest")
        if simulation.observation_policy_sha256 != manifest.observation_policy_sha256:
            raise ValueError("simulation policy hash does not match benchmark manifest")
        if simulation.primary_target_object_id != manifest.primary_target_object_id:
            raise ValueError("simulation primary target does not match benchmark manifest")
        if simulation.scheduled_observation_object_id != manifest.scheduled_observation_object_id:
            raise ValueError(
                "simulation scheduled observation object does not match benchmark manifest"
            )
        if simulation.scheduled_observation_object_id not in manifest.object_instance_ids:
            raise ValueError("simulation scheduled observation object is outside the benchmark")
        if simulation.simulator_version != manifest.simulator_version:
            raise ValueError("simulation version does not match benchmark manifest")
        if simulation.simulation_content_sha256 != manifest.expected_simulation_content_sha256:
            raise ValueError("simulation content hash does not match benchmark manifest")
        if simulation.duration_days != manifest.duration_days:
            raise ValueError("simulation duration does not match benchmark manifest")
        if benchmark_view.ground_truth.simulation_run_id != simulation.simulation_run_id:
            raise ValueError("ground-truth simulation run ID does not match simulation")
        expected_simulation_run_id = simulation_run_identity(
            observation_policy_id=simulation.observation_policy_id,
            observation_policy_sha256=simulation.observation_policy_sha256,
            simulator_version=simulation.simulator_version,
            start_time=simulation.start_time,
            duration_days=simulation.duration_days,
            random_seed=simulation.random_seed,
            primary_target_object_id=simulation.primary_target_object_id,
            scheduled_observation_object_id=(simulation.scheduled_observation_object_id),
            initial_target_location_id=(simulation.initial_target_location_id),
        )
        if simulation.simulation_run_id != expected_simulation_run_id:
            raise ValueError("simulation run ID does not match its bound inputs")
        unknown_metrics = set(manifest.metric_names) - set(self._METRIC_TASKS)
        if unknown_metrics:
            raise ValueError(f"unsupported manifest metrics: {sorted(unknown_metrics)}")
        disabled_tasks = {self._METRIC_TASKS[name] for name in manifest.metric_names} - set(
            manifest.task_families
        )
        if disabled_tasks:
            raise ValueError(
                "manifest requests metrics for disabled task families: "
                f"{sorted(task.value for task in disabled_tasks)}"
            )

        household_ids = {
            observation.metadata.household_id
            for observation in simulation.observation_opportunities
        }
        if not household_ids.issubset(set(manifest.household_ids)):
            raise ValueError("simulation contains a household outside the benchmark")

        truth = benchmark_view.ground_truth.events
        actor_ids = {event.actor_gt_entity_id for event in truth}
        object_ids = {event.object_gt_entity_id for event in truth}
        location_ids = {
            location_id
            for event in truth
            for location_id in (
                event.source_location_gt_entity_id,
                event.destination_location_gt_entity_id,
            )
            if location_id is not None
        }
        if not actor_ids.issubset(set(manifest.person_ids)):
            raise ValueError("simulation contains a person outside the benchmark")
        if not object_ids.issubset(set(manifest.object_instance_ids)):
            raise ValueError("simulation contains an object outside the benchmark")
        if not location_ids.issubset(set(manifest.location_ids)):
            raise ValueError("simulation contains a location outside the benchmark")

        opportunities = simulation.observation_opportunities
        results = simulation.detection_results
        for opportunity in opportunities:
            unexpected = set(vars(opportunity)) - set(ObservationOpportunityRecord.model_fields)
            if unexpected:
                raise ValueError("observation opportunity contains fields outside its contract")
            ObservationOpportunityRecord.model_validate(opportunity.model_dump(mode="python"))
        for result in results:
            unexpected = set(vars(result)) - set(ObservationDetectionResult.model_fields)
            if unexpected:
                raise ValueError("detection result contains fields outside its contract")
            ObservationDetectionResult.model_validate(result.model_dump(mode="python"))
        run_end = simulation.start_time + timedelta(days=simulation.duration_days)
        if any(not simulation.start_time <= event.event_time < run_end for event in truth):
            raise ValueError("ground-truth event falls outside simulation duration")
        if any(
            not simulation.start_time <= item.opportunity_time < run_end for item in opportunities
        ):
            raise ValueError("observation opportunity falls outside simulation duration")
        if any(
            item.incidental_context is not None and item.incidental_context.candidate_entity_ids
            for item in opportunities
        ):
            raise ValueError("observation opportunity must not expose candidate identities")
        opportunity_ids = {item.metadata.record_id for item in opportunities}
        if len(opportunity_ids) != len(opportunities):
            raise ValueError("simulation contains duplicate observation opportunities")
        if any(item.observation_opportunity_id not in opportunity_ids for item in results):
            raise ValueError("detection result references an unknown opportunity")
        opportunity_by_id = {item.metadata.record_id: item for item in opportunities}
        for result in results:
            selected = opportunity_by_id[result.observation_opportunity_id].selected
            if not selected and result.outcome != ObservationOutcome.NOT_OBSERVED:
                raise ValueError("unselected observation action requires a not_observed result")
            if selected and result.outcome == ObservationOutcome.NOT_OBSERVED:
                raise ValueError("selected observation action cannot have a not_observed result")
        result_ids = [item.metadata.record_id for item in results]
        if len(result_ids) != len(set(result_ids)):
            raise ValueError("simulation contains duplicate detection result IDs")
        if any(item.metadata.record_id != detection_result_record_id(item) for item in results):
            raise ValueError("detection result record ID does not match realized content")
        detected_object_ids = {
            item.detected_object_instance_id
            for item in results
            if item.detected_object_instance_id is not None
        }
        detected_location_ids = {
            item.detected_location_id for item in results if item.detected_location_id is not None
        }
        if not detected_object_ids.issubset(set(manifest.object_instance_ids)):
            raise ValueError("detection contains an object outside the benchmark")
        if detected_object_ids - {simulation.scheduled_observation_object_id}:
            raise ValueError("detected object does not match scheduled observation object")
        if not detected_location_ids.issubset(set(manifest.location_ids)):
            raise ValueError("detection contains a location outside the benchmark")
        if any(
            item.detection_time is not None
            and not simulation.start_time <= item.detection_time < run_end
            for item in results
        ):
            raise ValueError("detection falls outside simulation duration")
        selected_action_count = sum(item.selected for item in opportunities)
        if selected_action_count > manifest.budget.max_selected_observation_actions:
            raise ValueError("simulation exceeds manifest selected observation action budget")
        verification_count = sum(
            item.selected
            and item.incidental_context is not None
            and item.incidental_context.observation_mode
            in {
                "micro_verify",
                "planned_verify",
                "detour_verify",
            }
            for item in opportunities
        )
        if verification_count > manifest.budget.max_selected_verifications:
            raise ValueError("simulation exceeds manifest selected verification budget")

    @staticmethod
    def _match_unique_truth_events(
        detections: list[ObservationDetectionResult],
        truth_events: tuple[GTPlacementEvent, ...],
        *,
        maximum_delay: timedelta,
    ) -> set[UUID]:
        """Return a deterministic maximum-cardinality bipartite matching."""

        ordered_detections = sorted(
            detections,
            key=lambda item: (
                item.detection_time,
                str(item.metadata.record_id),
            ),
        )
        ordered_truth = sorted(
            truth_events,
            key=lambda item: (item.event_time, str(item.gt_event_id)),
        )
        eligible_truth_indices: list[tuple[int, ...]] = []
        for detection in ordered_detections:
            if detection.detection_time is None:
                eligible_truth_indices.append(())
                continue
            eligible_truth_indices.append(
                tuple(
                    truth_index
                    for truth_index, event in enumerate(ordered_truth)
                    if detection.detected_object_instance_id == event.object_gt_entity_id
                    and detection.detected_location_id == event.destination_location_gt_entity_id
                    and event.event_time <= detection.detection_time
                    and detection.detection_time - event.event_time <= maximum_delay
                )
            )

        truth_to_detection: dict[int, int] = {}

        def augment(detection_index: int, visited_truth: set[int]) -> bool:
            for truth_index in eligible_truth_indices[detection_index]:
                if truth_index in visited_truth:
                    continue
                visited_truth.add(truth_index)
                previous_detection = truth_to_detection.get(truth_index)
                if previous_detection is None or augment(
                    previous_detection,
                    visited_truth,
                ):
                    truth_to_detection[truth_index] = detection_index
                    return True
            return False

        for detection_index in range(len(ordered_detections)):
            augment(detection_index, set())

        return {ordered_truth[truth_index].gt_event_id for truth_index in truth_to_detection}
