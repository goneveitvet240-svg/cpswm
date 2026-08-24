"""No-tuning D0/D1/D2 replay through the complete Project Two causal loop."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from statistics import mean
from typing import Any

from cpswm.contracts import EventMechanism, EventType
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionBenchmarkV02,
    ProjectTwoActionMethod,
    _FullProjectTwoMethod,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset

INFERENCE_CHAIN = [
    "ObservationDetectionResult",
    "CHEH",
    "ORRER",
    "PCHMP",
    "actor/role/mechanism posterior",
    "action",
    "ExecutionFeedbackRecord",
    "ExecutionFeedbackProjector",
    "feedback likelihood",
    "PCHMP rerun",
    "ORRER revision",
    "EventRevisionOutcome",
    "ProjectOneStatRequest",
    "HybridEventToTaskCoordinatorLoop",
    "new BeliefSnapshot",
    "next action distribution",
    "action utility",
]


def _distribution(history) -> dict[str, Any]:
    revision = history.latest
    actor: dict[str, float] = defaultdict(float)
    mechanism: dict[str, float] = defaultdict(float)
    role: dict[str, float] = defaultdict(float)
    location: dict[str, float] = defaultdict(float)
    for hypothesis in revision.active_hypotheses:
        probability = hypothesis.posterior_probability
        actor[hypothesis.responsible_actor_key] += probability
        mechanism[hypothesis.explanation_code] += probability
        location[str(revision.destination_location_id)] += probability
        for event in hypothesis.steps:
            if event.event_type is EventType.TRANSFER and event.recipient_actor_key:
                role[f"{event.actor_key}=>{event.recipient_actor_key}"] += probability
    mechanism[EventMechanism.UNKNOWN_MECHANISM.value] += revision.unknown_mechanism_probability
    for key, probability in revision.unknown_mechanism_actor_posterior.items():
        actor[key] += revision.unknown_mechanism_probability * probability
    return {
        "actor": dict(actor),
        "mechanism": dict(mechanism),
        "role": dict(role),
        "location": dict(location),
        "unresolved_mass": revision.unresolved_probability,
        "unknown_mechanism_mass": revision.unknown_mechanism_probability,
        "revision_id": str(revision.revision_id),
    }


def _argmax(mapping: dict[str, float]) -> str | None:
    return max(mapping, key=lambda key: (mapping[key], key)) if mapping else None


def _bootstrap(values: list[float], samples: int, seed: int) -> dict[str, Any]:
    if not values:
        return {"mean": None, "ci95": None, "n": 0}
    rng = random.Random(seed)
    estimates = sorted(mean(rng.choice(values) for _ in values) for _ in range(max(samples, 1)))
    low = estimates[int(0.025 * (len(estimates) - 1))]
    high = estimates[int(0.975 * (len(estimates) - 1))]
    return {"mean": mean(values), "ci95": [low, high], "n": len(values)}


def _summarize_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(records)
    if not items:
        return {"step_count": 0}
    return {
        "step_count": len(items),
        "hidden_event_hypothesis_accuracy": mean(item["hidden_correct"] for item in items),
        "revision_accuracy": mean(item["revision_correct"] for item in items),
        "put_back_success": mean(item["put_back_success"] for item in items),
        "search_success": mean(item["search_success"] for item in items),
        "mean_unresolved_mass": mean(item["unresolved_mass"] for item in items),
    }


def run_project_two_replay_evidence(
    dataset: ProjectTwoReplayDataset,
    *,
    bootstrap_samples: int = 2000,
    owner_threshold: float = 0.5,
) -> dict[str, Any]:
    """Run every episode without tuning or using test truth for configuration."""

    scorer = ProjectTwoActionBenchmarkV02()
    episode_reports: list[dict[str, Any]] = []
    all_steps: list[dict[str, Any]] = []
    for episode in dataset.episodes:
        state = _FullProjectTwoMethod(episode, owner_threshold=owner_threshold)
        predictions = []
        raw_steps: list[dict[str, Any]] = []
        for step in episode.steps:
            state.observe(step)
            initial = state.histories.get(step.step_id)
            before = _distribution(initial) if initial is not None else None
            prediction = state.predict()
            predictions.append(prediction)
            trace_start = len(state.revision_action_traces)
            state.feedback(step)
            after_history = state.histories.get(step.step_id)
            after = _distribution(after_history) if after_history is not None else before
            raw_steps.append(
                {
                    "step_id": str(step.step_id),
                    "timestamp": step.timestamp.isoformat(),
                    "observation_available": initial is not None,
                    "posterior_before_feedback": before,
                    "posterior_after_feedback": after,
                    "action": {
                        "put_back_location_id": str(prediction.put_back),
                        "search_order": [str(value) for value in prediction.search_order],
                        "unknown_probability": prediction.unknown_probability,
                    },
                    "feedback_soft_evidence": [
                        {
                            "feedback_record_id": str(item.metadata.record_id),
                            "action_type": item.action_type.value,
                            "outcome_distribution": {
                                key.value: value for key, value in item.outcome_distribution.items()
                            },
                            "attempted_location_id": (
                                str(item.attempted_location_id)
                                if item.attempted_location_id is not None
                                else None
                            ),
                            "observed_destination_location_id": (
                                str(step.observed_destination_location_id)
                                if step.observed_destination_location_id is not None
                                else None
                            ),
                        }
                        for item in step.execution_feedback
                    ],
                    "revision_action_traces": state.revision_action_traces[trace_start:],
                }
            )
        stats = (
            state.revision_calls,
            state.project_one_requests,
            state.project_one_applications,
            state.rejected_feedback,
            state.unnecessary_revisions,
            state.project_one_rejections,
            state.project_one_deferred,
            state.project_one_replay_noops,
            tuple(state.revision_action_traces),
        )
        action_metric = scorer._score_predictions(
            dataset=dataset,
            episode=episode,
            method=ProjectTwoActionMethod.PROJECT_TWO,
            predictions=predictions,
            stats=stats,
        )
        truth = dataset.truth_for(episode.episode_id)
        enriched_steps = []
        retract_correct_total = retract_correct_hits = 0
        for step, prediction, raw in zip(episode.steps, predictions, raw_steps, strict=True):
            target = truth.truth_by_step[step.step_id]
            before = raw["posterior_before_feedback"]
            after = raw["posterior_after_feedback"]

            def correct(posterior, evaluator_target=target) -> bool:
                if not posterior:
                    return False
                return (
                    _argmax(posterior["actor"]) == evaluator_target.true_actor
                    and _argmax(posterior["mechanism"]) == evaluator_target.true_mechanism.value
                    and _argmax(posterior["location"]) == str(evaluator_target.true_location)
                )

            trace_payloads = []
            for trace in raw.pop("revision_action_traces"):
                payload = trace.model_dump(mode="json")
                trace_payloads.append(payload)
                request = trace.project_one_request
                if request is not None and request.kind in {"retract", "correct"}:
                    retract_correct_total += 1
                    retract_correct_hits += correct(after)
            actor_stratum = (
                "owner" if target.true_actor == episode.owner_actor_key else target.true_actor
            )
            record = {
                **raw,
                "revision_action_traces": trace_payloads,
                "evaluator_labels": {
                    "actor_stratum": actor_stratum,
                    "mechanism_stratum": target.true_mechanism.value,
                },
                "hidden_correct": correct(before),
                "revision_correct": correct(after),
                "put_back_success": prediction.put_back == target.true_owner_habit_location,
                "search_success": prediction.search_order[0] == target.true_location,
                "unresolved_mass": after["unresolved_mass"] if after else 1.0,
            }
            enriched_steps.append(record)
            all_steps.append(record)
        episode_reports.append(
            {
                "episode_id": str(episode.episode_id),
                "split": episode.split.value,
                "maturity": episode.maturity.value,
                "household_id": str(episode.household_id),
                "scene_id": episode.scene_id,
                "object_family": episode.object_family,
                "source_hash": episode.source_hash,
                "step_traces": enriched_steps,
                "action_metrics": action_metric.model_dump(mode="json"),
                "diagnostic_metrics": _summarize_records(enriched_steps),
                "retract_correct_precision": (
                    retract_correct_hits / retract_correct_total if retract_correct_total else None
                ),
                "retract_correct_count": retract_correct_total,
                "retract_correct_correct_count": retract_correct_hits,
                "cumulative_utility": sum(
                    trace.evaluator_utility or 0.0 for trace in action_metric.revision_action_traces
                ),
            }
        )

    strata = {"actor": {}, "mechanism": {}}
    for axis, labels in (
        ("actor", ("owner", "guest", "unknown_actor")),
        (
            "mechanism",
            (
                EventMechanism.DIRECT_RELOCATION.value,
                EventMechanism.HANDOFF_RELOCATION.value,
                EventMechanism.UNKNOWN_MECHANISM.value,
            ),
        ),
    ):
        key = f"{axis}_stratum"
        for label in labels:
            strata[axis][label] = _summarize_records(
                item for item in all_steps if item["evaluator_labels"][key] == label
            )

    action_fields = (
        "put_back_error_rate",
        "search_success_rate",
        "cumulative_action_regret",
        "mean_search_cost",
    )
    aggregate = {
        field: _bootstrap(
            [float(item["action_metrics"][field]) for item in episode_reports],
            bootstrap_samples,
            seed=7000 + index,
        )
        for index, field in enumerate(action_fields)
    }
    aggregate.update(
        {
            "hidden_event_hypothesis_accuracy": _bootstrap(
                [float(item["hidden_correct"]) for item in all_steps],
                bootstrap_samples,
                7101,
            ),
            "revision_accuracy": _bootstrap(
                [float(item["revision_correct"]) for item in all_steps],
                bootstrap_samples,
                7102,
            ),
            "mean_unresolved_mass": _bootstrap(
                [float(item["unresolved_mass"]) for item in all_steps],
                bootstrap_samples,
                7103,
            ),
            "cumulative_utility": _bootstrap(
                [float(item["cumulative_utility"]) for item in episode_reports],
                bootstrap_samples,
                7104,
            ),
        }
    )
    groups: dict[str, dict[str, Any]] = {"household": {}, "object_family": {}}
    for axis, field in (("household", "household_id"), ("object_family", "object_family")):
        labels = sorted({item[field] for item in episode_reports})
        for index, label in enumerate(labels):
            members = [item for item in episode_reports if item[field] == label]
            groups[axis][label] = {
                metric: _bootstrap(
                    [float(item["action_metrics"][metric]) for item in members],
                    bootstrap_samples,
                    8000 + index,
                )
                for metric in action_fields
            }
    split_metrics = {}
    for split in ("validation", "test"):
        members = [item for item in episode_reports if item["split"] == split]
        split_metrics[split] = {
            metric: _bootstrap(
                [float(item["action_metrics"][metric]) for item in members],
                bootstrap_samples,
                9000 + index,
            )
            for index, metric in enumerate(action_fields)
        }
        split_metrics[split]["cumulative_utility"] = _bootstrap(
            [float(item["cumulative_utility"]) for item in members],
            bootstrap_samples,
            9050,
        )

    all_traces = [
        trace
        for episode in episode_reports
        for trace in episode["action_metrics"]["revision_action_traces"]
    ]
    request_traces = [trace for trace in all_traces if trace["project_one_request"] is not None]
    request_status_counts = {
        status: sum(trace["request_application_status"] == status for trace in request_traces)
        for status in (
            "applied",
            "deferred_due_to_quarantine",
            "rejected",
            "replay_noop",
        )
    }
    operator_runtime: dict[str, dict[str, int]] = {}
    for trace in all_traces:
        for diagnostic in trace["operator_diagnostics"]:
            counts = operator_runtime.setdefault(
                diagnostic["operator"], {"records": 0, "executed": 0, "changed_state": 0}
            )
            counts["records"] += 1
            counts["executed"] += int(diagnostic["executed"])
            counts["changed_state"] += int(diagnostic["changed_state"])
    feedback_steps = [item for item in all_steps if item["feedback_soft_evidence"]]
    feedback_outcomes: dict[str, int] = defaultdict(int)
    for item in feedback_steps:
        for feedback in item["feedback_soft_evidence"]:
            dominant = max(
                feedback["outcome_distribution"],
                key=feedback["outcome_distribution"].get,
            )
            feedback_outcomes[dominant] += 1
    retract_total = sum(item["retract_correct_count"] for item in episode_reports)
    retract_hits = sum(item["retract_correct_correct_count"] for item in episode_reports)
    runtime_summary = {
        "revision_action_trace_count": len(all_traces),
        "project_one_request_count": len(request_traces),
        "project_one_request_status_counts": request_status_counts,
        "request_application_rate": (
            request_status_counts["applied"] / len(request_traces) if request_traces else None
        ),
        "retract_correct_precision": (retract_hits / retract_total if retract_total else None),
        "retract_correct_count": retract_total,
        "feedback_dominant_outcome_counts": dict(feedback_outcomes),
        "feedback_posterior_changed_rate": (
            mean(
                item["posterior_before_feedback"] != item["posterior_after_feedback"]
                for item in feedback_steps
            )
            if feedback_steps
            else None
        ),
        "operator_runtime": operator_runtime,
    }
    return {
        "schema_version": "0.1.0",
        "dataset_version": dataset.manifest.dataset_version,
        "episode_count": len(dataset.episodes),
        "step_count": len(all_steps),
        "inference_chain": INFERENCE_CHAIN,
        "configuration_selection": {
            "owner_threshold": owner_threshold,
            "tuned": False,
            "test_truth_used": False,
            "selection_scope": "fixed configuration applied identically to validation and test",
        },
        "episode_reports": episode_reports,
        "aggregate_metrics": aggregate,
        "split_metrics": split_metrics,
        "strata": strata,
        "groups": groups,
        "runtime_summary": runtime_summary,
        "metric_semantics": {
            "action_utility_evidence": [
                "put_back_error_rate",
                "search_success_rate",
                "cumulative_action_regret",
                "mean_search_cost",
                "cumulative_utility",
            ],
            "diagnostic_only": [
                "hidden_event_hypothesis_accuracy",
                "actor_posterior",
                "role_posterior",
                "mechanism_posterior",
                "unresolved_mass",
                "revision_accuracy",
                "retract_correct_precision",
            ],
        },
        "scientific_status": ("development replay evidence; not paper-level real-world evidence"),
    }


def write_project_two_replay_evidence(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "complete_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "episode_metrics.jsonl").write_text(
        "\n".join(
            json.dumps(
                {key: value for key, value in item.items() if key != "step_traces"},
                ensure_ascii=False,
            )
            for item in report["episode_reports"]
        )
        + "\n",
        encoding="utf-8",
    )
    event_rows = []
    for episode in report["episode_reports"]:
        for step in episode["step_traces"]:
            event_rows.append(
                {
                    "episode_id": episode["episode_id"],
                    "split": episode["split"],
                    **step,
                }
            )
    (output_dir / "revision_action_traces.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in event_rows) + "\n",
        encoding="utf-8",
    )
    summary = {key: value for key, value in report.items() if key != "episode_reports"}
    (output_dir / "aggregate_report.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )


__all__ = [
    "INFERENCE_CHAIN",
    "run_project_two_replay_evidence",
    "write_project_two_replay_evidence",
]
