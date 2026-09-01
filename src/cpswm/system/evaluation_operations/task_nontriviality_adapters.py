"""Bind existing CPSWM benchmark targets to the method-free non-triviality gates.

Each adapter only reads data that already exists in the repository.  It does not
run, tune, or score a research method, and it never changes a target, so an
adapter cannot move a gate verdict toward a preferred outcome.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

from cpswm.contracts import ProjectTwoDatasetSplit

from .project_two_action_benchmark import _locations
from .project_two_dataset import ProjectTwoReplayDataset
from .task_nontriviality_gates import ArmPredictionTrace, TargetStep, TargetStream

PROJECT_TWO_PUT_BACK_TARGET = "project_two.true_owner_habit_location"
PROJECT_TWO_SEARCH_TARGET = "project_two.true_location"


def project_two_target_streams(
    dataset: ProjectTwoReplayDataset,
    *,
    target: str,
    stratum: str,
    split: ProjectTwoDatasetSplit = ProjectTwoDatasetSplit.VALIDATION,
) -> list[TargetStream]:
    """Build gate-A streams for one Project Two action target.

    For the put-back target the update law is "adopt the observed location on an
    owner event, otherwise persist", whose trigger (was this the owner?) is
    latent.  For the search target the law is "adopt the last observed location",
    whose trigger is simply whether a detection exists, and is therefore fully
    visible.  Setting the visible and true triggers equal in the second case is
    the honest encoding: that target has no latent trigger to infer.
    """

    if target not in {PROJECT_TWO_PUT_BACK_TARGET, PROJECT_TWO_SEARCH_TARGET}:
        raise ValueError(f"unknown project two target {target!r}")
    streams: list[TargetStream] = []
    for episode in dataset.visible_episodes(split):
        truth = dataset.truth_for(episode.episode_id)
        candidates = tuple(str(location) for location in _locations(episode))
        if not candidates:
            continue
        steps: list[TargetStep] = []
        for step in episode.steps:
            step_truth = truth.truth_by_step[step.step_id]
            observed = (
                str(step.after.detected_location_id)
                if step.after is not None and step.after.detected_location_id is not None
                else None
            )
            posterior = (
                dict(step.actor_evidence.actor_posterior) if step.actor_evidence is not None else {}
            )
            visible_owner = bool(posterior) and (
                min(posterior.items(), key=lambda item: (-item[1], item[0]))[0]
                == episode.owner_actor_key
            )
            true_owner = step_truth.true_actor == episode.owner_actor_key
            if target == PROJECT_TWO_PUT_BACK_TARGET:
                value = str(step_truth.true_owner_habit_location)
                visible_trigger, true_trigger = visible_owner, true_owner
            else:
                value = str(step_truth.true_location)
                visible_trigger = true_trigger = observed is not None
            steps.append(
                TargetStep(
                    context_key=step.timestamp.strftime("%a"),
                    candidates=candidates,
                    observed_value=observed,
                    visible_trigger=visible_trigger,
                    target=value,
                    true_trigger=true_trigger,
                )
            )
        if steps:
            streams.append(
                TargetStream(
                    stream_id=str(episode.episode_id),
                    stratum=stratum,
                    steps=tuple(steps),
                )
            )
    return streams


PROJECT_ONE_SHIFT_CAUSE_TARGET = "project_one.shift_cause_set"


def _shift_case_visible_summary(case: Any) -> str:
    """A deliberately coarse, method-free summary of one online-shift case.

    The three bits are chosen to match the causes the target enumerates: an
    observation-policy change should move the detection rate, an actor change
    should move the dominant actor, and a habit change should move the modal
    observed location.  A lookup table over this summary is therefore the most
    obvious trivial detector a reviewer would try first.  It is *one* feature
    set, not an exhaustive search, so a high lookup error here bounds nothing --
    only a low one is informative.
    """

    run = case.model_input.observation_stream
    detections = list(run.detection_results)
    if not detections:
        return "empty"
    midpoint = len(detections) // 2
    halves = (detections[:midpoint], detections[midpoint:])

    def _rate(rows: list[Any]) -> float:
        if not rows:
            return 0.0
        return sum(row.detected_location_id is not None for row in rows) / len(rows)

    def _modal_location(rows: list[Any]) -> str | None:
        seen = Counter(
            str(row.detected_location_id) for row in rows if row.detected_location_id is not None
        )
        if not seen:
            return None
        return min(seen.items(), key=lambda item: (-item[1], item[0]))[0]

    def _modal_actor(rows: list[Any]) -> str | None:
        posteriors: Counter[str] = Counter()
        ids = {row.metadata.record_id for row in rows}
        for evidence in case.model_input.actor_evidence:
            if evidence.source_detection_result_id not in ids or not evidence.actor_posterior:
                continue
            top = min(evidence.actor_posterior.items(), key=lambda item: (-item[1], str(item[0])))[
                0
            ]
            posteriors[str(top)] += 1
        if not posteriors:
            return None
        return min(posteriors.items(), key=lambda item: (-item[1], item[0]))[0]

    rate_delta = _rate(halves[1]) - _rate(halves[0])
    rate_bucket = "down" if rate_delta < -0.1 else "up" if rate_delta > 0.1 else "flat"
    location_moved = int(_modal_location(halves[0]) != _modal_location(halves[1]))
    actor_moved = int(_modal_actor(halves[0]) != _modal_actor(halves[1]))
    return f"rate:{rate_bucket}|loc:{location_moved}|actor:{actor_moved}"


def project_one_shift_target_streams(cases: Sequence[Any]) -> list[TargetStream]:
    """Build gate-A streams for the Project One shift-cause target.

    Each case is a single scored decision, so this is a classification target:
    there is no update law and no trigger, and the state-tracking criteria do
    not bind.  ``visible_trigger`` and ``true_trigger`` are therefore both
    False, which makes the sticky rules degenerate to a constant on purpose.
    """

    labels = sorted(
        {
            "+".join(sorted(cause.value for cause in case.evaluator_truth.true_causes))
            for case in cases
        }
    )
    streams: list[TargetStream] = []
    for case in cases:
        label = "+".join(sorted(c.value for c in case.evaluator_truth.true_causes))
        streams.append(
            TargetStream(
                stream_id=str(case.model_input.case_id),
                stratum=case.evaluator_truth.split.value,
                steps=(
                    TargetStep(
                        context_key=case.evaluator_truth.identifiability_status.value,
                        candidates=tuple(labels),
                        observed_value=_shift_case_visible_summary(case),
                        visible_trigger=False,
                        target=label,
                        true_trigger=False,
                    ),
                ),
            )
        )
    return streams


def collect_arm_prediction_traces(
    arm_states: Sequence[tuple[str, Iterable[tuple[str, Any]]]],
) -> list[ArmPredictionTrace]:
    """Turn ``(arm, [(episode_id, state)])`` pairs into gate-B traces.

    ``state`` must follow the frozen replay-method protocol: ``observe``,
    ``predict``, ``feedback``.  Only the emitted put-back and search-head
    decisions are recorded, because those are exactly what every action endpoint
    in this repository is computed from.
    """

    traces: list[ArmPredictionTrace] = []
    for arm, episode_states in arm_states:
        rows: list[tuple[str, tuple[str, ...]]] = []
        for episode_id, payload in episode_states:
            episode, state = payload
            emitted: list[str] = []
            for step in episode.steps:
                state.observe(step)
                prediction = state.predict()
                emitted.append(
                    f"{prediction.put_back}>{prediction.search_order[0]}"
                    if prediction.search_order
                    else str(prediction.put_back)
                )
                state.feedback(step)
            rows.append((episode_id, tuple(emitted)))
        traces.append(ArmPredictionTrace(arm=arm, episode_predictions=tuple(rows)))
    return traces


__all__ = [
    "PROJECT_ONE_SHIFT_CAUSE_TARGET",
    "PROJECT_TWO_PUT_BACK_TARGET",
    "PROJECT_TWO_SEARCH_TARGET",
    "collect_arm_prediction_traces",
    "project_one_shift_target_streams",
    "project_two_target_streams",
]
