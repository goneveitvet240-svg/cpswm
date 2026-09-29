"""Existing, explicit controlled semantic history used by the mixed-loop diagnostic."""

from run_correction_replay_comparison import (
    NEGATIVE_ABSENT_LIKELIHOOD,
    NEGATIVE_PRESENT_LIKELIHOOD,
    NEGATIVE_SEARCH_OUTCOME,
    build_execution_feedback_bundle,
)


def correction_bundles(probe, stream):
    """Same predeclared first-seven-day intervention; never selected by action gain."""
    dates = {day.after.detection_time.date() for day in probe.observed_days()[:7]}
    targets = [
        (rid, event)
        for rid, event in stream._system.core._committed_events.items()
        if event.evidence.event_time.date() in dates
    ]
    return tuple(
        build_execution_feedback_bundle(
            probe,
            revision_id=rid,
            location_id=event.location_id,
            belief_snapshot_id=event.belief_snapshot_id,
            when=event.evidence.event_time,
            opportunity_id=event.evidence.observation_opportunity_id,
            outcome_distribution=NEGATIVE_SEARCH_OUTCOME,
            present_likelihood=NEGATIVE_PRESENT_LIKELIHOOD,
            absent_likelihood=NEGATIVE_ABSENT_LIKELIHOOD,
        )
        for rid, event in targets
    )
