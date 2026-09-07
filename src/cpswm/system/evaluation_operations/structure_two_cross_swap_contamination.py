"""Belief/readout cross-swap and v0.6 contamination first-fault trace.

The cross-swap uses one common boundary: a normalized location belief plus the
last robot-visible location.  The project-two readout ranks all remaining
locations by belief; the AMG readout keeps its source adapter's encounter-order
search tail.  Hidden truth is consulted only after all four actions are emitted.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Final
from uuid import UUID

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    _AMGOpenWorldMethod,
    _argmax,
    _FullProjectTwoMethod,
    _Prediction,
    _rank,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.structure_two_search_utility import (
    normalized_extra_inspection_regret,
)
from cpswm.system.prototype_spine import ActionReadout, ActionReadoutConfig
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID: Final = "structure-two-belief-readout-cross-swap-contamination@0.2"


class BeliefSource(StrEnum):
    PROJECT_TWO_V06 = "project_two_v0_6_belief"
    AMG = "amg_matched_belief"


class ReadoutSource(StrEnum):
    PROJECT_TWO_V06 = "project_two_v0_6_readout"
    AMG = "amg_matched_readout"


class ContaminationFirstFault(StrEnum):
    PCHMP_OWNER_ATTRIBUTION = "pchmp_owner_attribution"
    FAST_ACTION_LEDGER = "fast_action_ledger"
    RGRC_SLOW_COMMIT = "rgrc_slow_commit"
    COLD_START_PRIOR_TIE = "cold_start_prior_tie"
    ACTION_READOUT_MIX = "action_readout_mix"


@dataclass(frozen=True, slots=True)
class CommonLocationBelief:
    source: BeliefSource
    distribution: dict[UUID, float]
    last_observed_location: UUID
    unknown_probability: float
    project_two_components: dict[str, dict[UUID, float]]
    fast_confirmation_count: int
    pending_correction_mass: dict[UUID, float]
    latest_unique_owner_location: UUID | None


@dataclass(frozen=True, slots=True)
class CrossSwapMetric:
    belief_source: BeliefSource
    readout_source: ReadoutSource
    step_count: int
    put_back_error_rate: float
    owner_habit_contamination: float
    cumulative_search_regret: float
    cumulative_action_regret: float


@dataclass(frozen=True, slots=True)
class ContaminationFirstFaultTrace:
    episode_id: UUID
    step_id: UUID
    step_index: int
    selected_location_id: UUID
    true_location_id: UUID
    true_owner_habit_location_id: UUID
    true_actor: str
    current_owner_posterior: float
    source_revision_id: UUID | None
    source_step_id: UUID | None
    source_true_actor: str | None
    source_owner_mass: float | None
    source_was_slow_committed: bool
    source_was_quarantined: bool
    first_fault: ContaminationFirstFault
    fast_component_argmax: UUID | None
    surviving_component_argmax: UUID | None
    regime_component_argmax: UUID | None
    hybrid_component_argmax: UUID | None
    fast_component_selected_mass: float
    surviving_component_selected_mass: float
    regime_component_selected_mass: float
    hybrid_component_selected_mass: float


@dataclass(frozen=True, slots=True)
class CrossSwapContaminationReport:
    protocol_id: str
    dataset_version: str
    selected_project_two_readout: dict[str, object]
    selected_amg_parameter: float
    metrics: tuple[CrossSwapMetric, ...]
    first_fault_counts: dict[str, int]
    contamination_traces: tuple[ContaminationFirstFaultTrace, ...]
    evaluator_truth_access_boundary: str
    put_back_readout_disagreement_count: int
    causal_first_fault_claim_allowed: bool
    interpretation: dict[str, float | str]
    payload_sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def unsigned_payload(self) -> dict[str, object]:
        """Return every consequential field covered by ``payload_sha256``."""

        return {
            "protocol_id": self.protocol_id,
            "dataset_version": self.dataset_version,
            "selected_project_two_readout": self.selected_project_two_readout,
            "selected_amg_parameter": self.selected_amg_parameter,
            "metrics": [asdict(item) for item in self.metrics],
            "first_fault_counts": self.first_fault_counts,
            "contamination_traces": [asdict(item) for item in self.contamination_traces],
            "evaluator_truth_access_boundary": self.evaluator_truth_access_boundary,
            "put_back_readout_disagreement_count": self.put_back_readout_disagreement_count,
            "causal_first_fault_claim_allowed": self.causal_first_fault_claim_allowed,
            "interpretation": self.interpretation,
        }

    def verify_payload_hash(self) -> bool:
        return content_sha256(self.unsigned_payload()) == self.payload_sha256


def selected_v06_readout() -> ActionReadoutConfig:
    """Frozen selection recorded by the 2026-09-06 v0.6 checkpoint."""

    return ActionReadoutConfig(
        readout=ActionReadout.DUAL_TIMESCALE_REVERSIBLE,
        hybrid_alpha_weight=0.0,
        fast_action_weight=0.7,
        surviving_revision_weight=0.2,
        regime_local_weight=0.1,
        fast_owner_mass_floor=0.5,
        owner_mass_floor=0.5,
        recency_half_life=1.0,
    )


def _normalize(locations: tuple[UUID, ...], values: dict[UUID, float]) -> dict[UUID, float]:
    total = sum(max(0.0, values.get(location, 0.0)) for location in locations)
    if total <= 0.0:
        return dict.fromkeys(locations, 1.0 / len(locations))
    return {location: max(0.0, values.get(location, 0.0)) / total for location in locations}


def _project_two_belief(state: _FullProjectTwoMethod) -> CommonLocationBelief:
    spine = state.spine
    config = state.action_readout
    latest_unique_owner_location = None
    for step in state._observed_steps:
        result = state.step_results.get(step.step_id)
        if result is None or step.after is None or step.after.detected_location_id is None:
            continue
        ranking = sorted(result.actor_posterior.items(), key=lambda item: (-item[1], item[0]))
        if (
            ranking
            and ranking[0][0] == state.episode.owner_actor_key
            and (len(ranking) == 1 or ranking[0][1] > ranking[1][1])
        ):
            latest_unique_owner_location = step.after.detected_location_id
    return CommonLocationBelief(
        source=BeliefSource.PROJECT_TWO_V06,
        distribution=dict.fromkeys(state.locations, 1.0 / len(state.locations)),
        last_observed_location=state.last_location,
        unknown_probability=state.unknown_probability,
        project_two_components={
            "hybrid_alpha": spine._hybrid_alpha_component(),
            "regime_local": spine._regime_local_component(),
            "surviving": spine._surviving_owner_revision_component(config),
            "fast_action": spine._latest_owner_event_component(config),
        },
        fast_confirmation_count=spine._fast_action_confirmation_count(config),
        pending_correction_mass=spine.pending_correction_mass(),
        latest_unique_owner_location=latest_unique_owner_location,
    )


def _amg_belief(state: _AMGOpenWorldMethod) -> CommonLocationBelief:
    # The matched adapter's only owner-memory state is its unique-MAP owner
    # location.  A missing unique maximum is represented honestly as uniform.
    distribution = dict.fromkeys(state.locations, 0.0)
    if state.amg_owner_location is not None:
        distribution[state.amg_owner_location] = 1.0
    return CommonLocationBelief(
        source=BeliefSource.AMG,
        distribution=_normalize(state.locations, distribution),
        last_observed_location=state.last or state.locations[0],
        unknown_probability=0.2,
        project_two_components={},
        fast_confirmation_count=0,
        pending_correction_mass={},
        latest_unique_owner_location=state.amg_owner_location,
    )


def _read(
    belief: CommonLocationBelief,
    readout: ReadoutSource,
    locations: tuple[UUID, ...],
    project_two_config: ActionReadoutConfig,
) -> _Prediction:
    if readout is ReadoutSource.PROJECT_TWO_V06:
        distribution = dict(belief.distribution)
        if belief.project_two_components:
            weights = project_two_config.component_weights
            fast_weight = weights["fast_action"]
            if belief.fast_confirmation_count < project_two_config.fast_confirmation_observations:
                fast_weight *= project_two_config.unconfirmed_fast_discount
            resolved_weights = {**weights, "fast_action": fast_weight}
            mixed = dict.fromkeys(locations, 0.0)
            used = 0.0
            for name, component in belief.project_two_components.items():
                weight = resolved_weights[name]
                total = sum(max(0.0, value) for value in component.values())
                if weight <= 0.0 or total <= 0.0:
                    continue
                used += weight
                for location in locations:
                    mixed[location] += weight * max(0.0, component.get(location, 0.0)) / total
            distribution = (
                dict.fromkeys(locations, 1.0 / len(locations))
                if used <= 0.0
                else {location: value / used for location, value in mixed.items()}
            )
            adjusted = {
                location: (
                    value * project_two_config.pending_correction_discount
                    if belief.pending_correction_mass.get(location, 0.0) < 0.0
                    else value
                )
                for location, value in distribution.items()
            }
            distribution = _normalize(locations, adjusted)
        put_back = _argmax(locations, distribution)
        search = tuple(_rank(locations, distribution, first=belief.last_observed_location))
    else:
        put_back = belief.latest_unique_owner_location or _argmax(locations, belief.distribution)
        first = belief.last_observed_location
        search = (first, *tuple(location for location in locations if location != first))
    return _Prediction(put_back, search, belief.unknown_probability)


def _component_argmax(locations: tuple[UUID, ...], values: dict[UUID, float]) -> UUID | None:
    if sum(max(0.0, value) for value in values.values()) <= 0.0:
        return None
    return _argmax(locations, values)


def _first_fault(
    *,
    state: _FullProjectTwoMethod,
    step_id: UUID,
    step_index: int,
    prediction: _Prediction,
    truth: Any,
    revision_sources: dict[UUID, tuple[UUID, str]],
) -> ContaminationFirstFaultTrace:
    result = state.step_results[step_id]
    config = state.action_readout
    spine = state.spine
    fast_values = spine._latest_owner_event_component(config)
    surviving_values = spine._surviving_owner_revision_component(config)
    regime_values = spine._regime_local_component()
    hybrid_values = spine._hybrid_alpha_component()
    selected = prediction.put_back
    eligible_fast = [
        event
        for event in spine._fast_action_events.values()
        if event.location_id == selected and event.owner_mass >= config.fast_owner_mass_floor
    ]
    fast_event = (
        max(eligible_fast, key=lambda event: (event.evidence.event_time, str(event.revision_id)))
        if eligible_fast
        else None
    )
    eligible_committed = [
        event for event in spine._committed_events.values() if event.location_id == selected
    ]
    committed_event = (
        max(
            eligible_committed,
            key=lambda event: (event.evidence.event_time, str(event.revision_id)),
        )
        if eligible_committed
        else None
    )
    source_event = fast_event or committed_event
    source = revision_sources.get(source_event.revision_id) if source_event is not None else None
    source_actor = source[1] if source is not None else None
    if (
        source_event is not None
        and source_actor not in {None, state.episode.owner_actor_key}
        and source_event.owner_mass >= state.owner_threshold
    ):
        fault = ContaminationFirstFault.PCHMP_OWNER_ATTRIBUTION
    elif fast_event is not None and committed_event is None:
        fault = ContaminationFirstFault.FAST_ACTION_LEDGER
    elif committed_event is not None:
        fault = ContaminationFirstFault.RGRC_SLOW_COMMIT
    elif all(
        len({round(value, 12) for value in component.values()}) <= 1
        for component in (surviving_values, regime_values, hybrid_values)
    ):
        fault = ContaminationFirstFault.COLD_START_PRIOR_TIE
    else:
        fault = ContaminationFirstFault.ACTION_READOUT_MIX
    revision_id = source_event.revision_id if source_event is not None else None
    return ContaminationFirstFaultTrace(
        episode_id=state.episode.episode_id,
        step_id=step_id,
        step_index=step_index,
        selected_location_id=selected,
        true_location_id=truth.true_location,
        true_owner_habit_location_id=truth.true_owner_habit_location,
        true_actor=truth.true_actor,
        current_owner_posterior=result.actor_posterior.get(state.episode.owner_actor_key, 0.0),
        source_revision_id=revision_id,
        source_step_id=source[0] if source is not None else None,
        source_true_actor=source_actor,
        source_owner_mass=source_event.owner_mass if source_event is not None else None,
        source_was_slow_committed=(
            revision_id is not None and spine.is_committed_revision(revision_id)
        ),
        source_was_quarantined=(
            revision_id is not None and spine.is_quarantined_revision(revision_id)
        ),
        first_fault=fault,
        fast_component_argmax=_component_argmax(state.locations, fast_values),
        surviving_component_argmax=_component_argmax(state.locations, surviving_values),
        regime_component_argmax=_component_argmax(state.locations, regime_values),
        hybrid_component_argmax=_component_argmax(state.locations, hybrid_values),
        fast_component_selected_mass=fast_values.get(selected, 0.0),
        surviving_component_selected_mass=surviving_values.get(selected, 0.0),
        regime_component_selected_mass=regime_values.get(selected, 0.0),
        hybrid_component_selected_mass=hybrid_values.get(selected, 0.0),
    )


def run_cross_swap_contamination_diagnostic(
    dataset: ProjectTwoReplayDataset,
) -> CrossSwapContaminationReport:
    """Run the frozen v0.6/PT and AMG belief/readout 2x2 on test episodes."""

    readout = selected_v06_readout()
    keys = tuple((belief, action) for belief in BeliefSource for action in ReadoutSource)
    totals = {key: {"steps": 0.0, "put": 0.0, "contamination": 0.0, "search": 0.0} for key in keys}
    traces: list[ContaminationFirstFaultTrace] = []
    put_back_readout_disagreement_count = 0
    for episode in dataset.visible_episodes(ProjectTwoDatasetSplit.TEST):
        project_two = _FullProjectTwoMethod(
            episode,
            owner_threshold=0.4,
            action_readout=readout,
        )
        amg = _AMGOpenWorldMethod(episode, mode="amg", parameter=0.2)
        revision_sources: dict[UUID, tuple[UUID, str]] = {}
        for step_index, step in enumerate(episode.steps):
            project_two.observe(step)
            amg.observe(step)
            beliefs = {
                BeliefSource.PROJECT_TWO_V06: _project_two_belief(project_two),
                BeliefSource.AMG: _amg_belief(amg),
            }
            # All four actions are emitted before evaluator truth is consulted.
            predictions = {
                key: _read(beliefs[key[0]], key[1], project_two.locations, readout) for key in keys
            }
            native_project_two = project_two.predict()
            native_amg = amg.predict()
            if (
                predictions[(BeliefSource.PROJECT_TWO_V06, ReadoutSource.PROJECT_TWO_V06)]
                != native_project_two
            ):
                raise ValueError("common boundary changed the native project-two action")
            if predictions[(BeliefSource.AMG, ReadoutSource.AMG)] != native_amg:
                raise ValueError("common boundary changed the native AMG action")
            for belief_source in BeliefSource:
                if (
                    predictions[(belief_source, ReadoutSource.PROJECT_TWO_V06)].put_back
                    != predictions[(belief_source, ReadoutSource.AMG)].put_back
                ):
                    put_back_readout_disagreement_count += 1
            truth = dataset.truth_for(episode.episode_id).truth_by_step[step.step_id]
            if step.step_id in project_two.step_results:
                revision_id = project_two.step_results[step.step_id].event_revision_id
                revision_sources[revision_id] = (step.step_id, truth.true_actor)
            for key, prediction in predictions.items():
                values = totals[key]
                values["steps"] += 1.0
                values["put"] += float(prediction.put_back != truth.true_owner_habit_location)
                values["contamination"] += float(
                    truth.true_actor != episode.owner_actor_key
                    and prediction.put_back == truth.true_location
                )
                try:
                    inspected = prediction.search_order.index(truth.true_location) + 1
                    found = True
                except ValueError:
                    inspected = len(prediction.search_order)
                    found = False
                values["search"] += normalized_extra_inspection_regret(
                    inspected_container_count=inspected,
                    registered_location_count=len(project_two.locations),
                    target_found_in_plan=found,
                )
            native = predictions[(BeliefSource.PROJECT_TWO_V06, ReadoutSource.PROJECT_TWO_V06)]
            if (
                truth.true_actor != episode.owner_actor_key
                and native.put_back == truth.true_location
                and step.step_id in project_two.step_results
            ):
                traces.append(
                    _first_fault(
                        state=project_two,
                        step_id=step.step_id,
                        step_index=step_index,
                        prediction=native,
                        truth=truth,
                        revision_sources=revision_sources,
                    )
                )
            project_two.feedback(step)
            amg.feedback(step)
            for revision_trace in project_two.revision_action_traces:
                inherited = revision_sources.get(revision_trace.superseded_revision_id)
                if inherited is not None:
                    revision_sources.setdefault(revision_trace.corrected_revision_id, inherited)

    metrics = []
    for belief, action in keys:
        values = totals[(belief, action)]
        count = int(values["steps"])
        metrics.append(
            CrossSwapMetric(
                belief_source=belief,
                readout_source=action,
                step_count=count,
                put_back_error_rate=values["put"] / count,
                owner_habit_contamination=values["contamination"] / count,
                cumulative_search_regret=values["search"],
                cumulative_action_regret=values["put"] + values["search"],
            )
        )
    by_key = {(item.belief_source, item.readout_source): item for item in metrics}
    ptpt = by_key[(BeliefSource.PROJECT_TWO_V06, ReadoutSource.PROJECT_TWO_V06)]
    ptamg = by_key[(BeliefSource.PROJECT_TWO_V06, ReadoutSource.AMG)]
    amgpt = by_key[(BeliefSource.AMG, ReadoutSource.PROJECT_TWO_V06)]
    amgamg = by_key[(BeliefSource.AMG, ReadoutSource.AMG)]
    interpretation: dict[str, float | str] = {
        "project_two_belief_readout_swap_action_regret_delta": (
            ptamg.cumulative_action_regret - ptpt.cumulative_action_regret
        ),
        "amg_belief_readout_swap_action_regret_delta": (
            amgamg.cumulative_action_regret - amgpt.cumulative_action_regret
        ),
        "project_two_readout_belief_swap_action_regret_delta": (
            amgpt.cumulative_action_regret - ptpt.cumulative_action_regret
        ),
        "amg_readout_belief_swap_action_regret_delta": (
            amgamg.cumulative_action_regret - ptamg.cumulative_action_regret
        ),
        "scope": "D0 development diagnosis; not a paper-level causal identification claim",
    }
    selected_project_two_readout: dict[str, object] = {
        "readout": readout.readout.value,
        "fast_action_weight": readout.fast_action_weight,
        "surviving_revision_weight": readout.surviving_revision_weight,
        "regime_local_weight": readout.regime_local_weight,
        "fast_owner_mass_floor": readout.fast_owner_mass_floor,
        "owner_mass_floor": readout.owner_mass_floor,
        "recency_half_life": readout.recency_half_life,
    }
    first_fault_counts = dict(Counter(item.first_fault.value for item in traces))
    truth_boundary = "truth lookup occurs after all four cross-swap actions are emitted"
    unsigned_payload = {
        "protocol_id": PROTOCOL_ID,
        "dataset_version": dataset.manifest.dataset_version,
        "selected_project_two_readout": selected_project_two_readout,
        "selected_amg_parameter": 0.2,
        "metrics": [asdict(item) for item in metrics],
        "first_fault_counts": first_fault_counts,
        "contamination_traces": [asdict(item) for item in traces],
        "evaluator_truth_access_boundary": truth_boundary,
        "put_back_readout_disagreement_count": put_back_readout_disagreement_count,
        "causal_first_fault_claim_allowed": False,
        "interpretation": interpretation,
    }
    return CrossSwapContaminationReport(
        protocol_id=PROTOCOL_ID,
        dataset_version=dataset.manifest.dataset_version,
        selected_project_two_readout=selected_project_two_readout,
        selected_amg_parameter=0.2,
        metrics=tuple(metrics),
        first_fault_counts=first_fault_counts,
        contamination_traces=tuple(traces),
        evaluator_truth_access_boundary=truth_boundary,
        put_back_readout_disagreement_count=put_back_readout_disagreement_count,
        causal_first_fault_claim_allowed=False,
        interpretation=interpretation,
        payload_sha256=content_sha256(unsigned_payload),
    )


__all__ = [
    "PROTOCOL_ID",
    "BeliefSource",
    "CommonLocationBelief",
    "ContaminationFirstFault",
    "ContaminationFirstFaultTrace",
    "CrossSwapContaminationReport",
    "CrossSwapMetric",
    "ReadoutSource",
    "run_cross_swap_contamination_diagnostic",
    "selected_v06_readout",
]
