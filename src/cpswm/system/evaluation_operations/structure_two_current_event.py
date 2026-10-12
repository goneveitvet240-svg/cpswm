"""Opt-in current-event prediction and paid location evidence in native Route C.

The original spine keeps its authority. Missing-location predictions update no
location statistics; a new paid observation replaces the same native event.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, replace
from uuid import UUID

from cpswm.contracts import EventMechanism
from cpswm.contracts.hidden_event_evidence import ordered_role_key
from cpswm.system.evaluation_operations.project_two_action_benchmark import _Prediction
from cpswm.system.evaluation_operations.structure_two_active_location_search import (
    LocationInspectionReceipt,
    LocationInspectionRequest,
)
from cpswm.system.evaluation_operations.structure_two_current_location import (
    execute_current_search,
    project_search_input,
)
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import _identity_probability
from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
    FullJointObservation,
    StatefulFullJointRuntime,
    _complete_cause_posterior,
    _normalize,
)
from cpswm.system.evaluation_operations.structure_two_stratified_sampling import (
    STRATIFIED_POLICY,
    stratified_draw_indices,
    stratum_offsets,
)
from cpswm.system.evaluation_operations.structure_two_task_readout import (
    TaskSeparatedFullJointActionState,
)
from cpswm.system.reproducibility import content_sha256, content_uuid


@dataclass(frozen=True, slots=True)
class CurrentEventObservation(FullJointObservation):
    prediction_only: bool = True
    position_source_id: UUID | None = None
    location_likelihood: tuple[tuple[str, float], ...] = ()

    def __post_init__(self):
        FullJointObservation.__post_init__(self)
        if self.prediction_only != (self.observed_location_id is None):
            raise ValueError("prediction flag must match missing location")
        values = dict(self.location_likelihood)
        if self.position_source_id is None:
            if values:
                raise ValueError("position likelihood requires a paid source")
        elif (
            self.prediction_only
            or self.position_source_id == self.source_update_id
            or len(values) != len(self.location_likelihood)
            or set(values) != set(self.actor_posterior)
            or any(not math.isfinite(v) or not 0 < v <= 1 for v in values.values())
        ):
            raise ValueError("invalid separately sourced position likelihood")


class CurrentEventRuntime(StatefulFullJointRuntime):
    """Native filter plus owned operation journal for same-event replacement."""

    def __init__(self, *, sampling_method=STRATIFIED_POLICY, **kwargs):
        if sampling_method not in {STRATIFIED_POLICY, "systematic"}:
            raise ValueError("unknown native proposal sampler")
        self.sampling_method = sampling_method
        self.sampling_receipts = []
        super().__init__(**kwargs)
        self.operations = []
        self.location_sources = {}
        self.location_revisions = []
        self._withdrawn_locations = set()
        self._initial = self._capture_mutable_state()
        self._current_before = None
        self._replaying = False

    def _capture_mutable_state(self):
        state = super()._capture_mutable_state()
        state["sampling_receipts"] = copy.deepcopy(self.sampling_receipts)
        return state

    def _proposal_draw_indices(self, probabilities, count, seed_sha256):
        if self.sampling_method == "systematic":
            indices = super()._proposal_draw_indices(probabilities, count, seed_sha256)
            offsets = (int(seed_sha256[:16], 16) / float(16**16),) * count
        else:
            indices = stratified_draw_indices(probabilities, count, seed_sha256)
            offsets = stratum_offsets(count, seed_sha256)
        cumulative = [0.0]
        total = math.fsum(probabilities) if self.sampling_method != "systematic" else 1.0
        for probability in probabilities:
            cumulative.append(cumulative[-1] + probability / total)
        cumulative[-1] = 1.0
        self.sampling_receipts.append(
            {
                "method": self.sampling_method,
                "seed_sha256": seed_sha256,
                "proposal_sha256": content_sha256(list(probabilities)),
                "support_size": len(probabilities),
                "count": count,
                "offsets": list(offsets),
                "indices": list(indices),
                "selected_probabilities": [probabilities[i] for i in indices],
                "cdf_intervals": [[cumulative[i], cumulative[i + 1]] for i in indices],
            }
        )
        return indices

    def _observation_log_likelihood(self, observation, candidate):
        values = dict(getattr(observation, "location_likelihood", ()))
        # Both native arms use the same observation model. Their existing
        # explicit cross-axis target potentials remain the sole arm difference.
        return 0.0 if not values else math.log(values[candidate.placement_actor])

    def _record(self, kind, payload):
        if not self._replaying:
            payload = copy.deepcopy(payload)
            self.operations.append((kind, payload, content_sha256(payload)))

    def revise(self, observation):
        before = self._capture_mutable_state()
        result = super().revise(observation)
        self._record("observation", observation)
        if not self._replaying:
            self._current_before = before
        return result

    def record_verification(self, **kwargs):
        super().record_verification(**kwargs)
        self._record("verification", kwargs)

    def apply_feedback(self, trace):
        super().apply_feedback(trace)
        self._record("feedback", trace)

    def replace_current_location(self, observation, source_payload, environment):
        if not self.operations or self.operations[-1][0] != "observation":
            raise ValueError("location must precede feedback and bind current event")
        previous = self.operations[-1][1]
        observation.__post_init__()
        if (
            source_payload["event_id"] != str(previous.source_update_id)
            or tuple(source_payload["location_likelihood"]) != observation.location_likelihood
            or replace(
                observation,
                prediction_only=True,
                observed_location_id=None,
                position_source_id=None,
                location_likelihood=(),
            )
            != previous
        ):
            raise ValueError("position evidence changed unrelated current event fields")
        receipts = [u["receipt"] for u in source_payload["paid_updates"]]
        if not receipts or receipts != [r["receipt"] for r in environment.step_receipts]:
            raise ValueError("paid source must contain complete owned search receipts")
        for index, payload in enumerate(receipts):
            request = LocationInspectionRequest(
                **{k: UUID(v) for k, v in payload["request"].items()}
            )
            receipt = LocationInspectionReceipt(
                request, payload["ordinal"], payload["found"], payload["receipt_sha256"]
            )
            environment.core.validate_receipt(request, receipt)
            if (
                str(request.episode_id) != source_payload["episode_id"]
                or str(request.step_id) != source_payload["step_id"]
                or str(request.object_id) != source_payload["object_id"]
                or receipt.ordinal != index + 1
                or receipt.found != (index == len(receipts) - 1)
            ):
                raise ValueError("paid position receipt has wrong event or sequence")
        if request.location_id != observation.observed_location_id:
            raise ValueError("paid position does not match new observation")
        if (
            previous.source_update_id != observation.source_update_id
            or previous.observed_location_id is not None
            or observation.position_source_id in self.location_sources
            or self._last_observation.source_update_id != observation.source_update_id
            or observation.position_source_id
            != content_uuid("paid-current-location", source_payload)
        ):
            raise ValueError("wrong current event, duplicate observation or source binding")
        snapshot = self._capture_mutable_state()
        before_hash = self._state_sha256()
        try:
            self._restore_mutable_state(copy.deepcopy(self._current_before))
            StatefulFullJointRuntime.revise(self, observation)
        except Exception:
            self._restore_mutable_state(snapshot)
            raise
        owned = copy.deepcopy(source_payload)
        self.location_sources[observation.position_source_id] = {
            "payload": owned,
            "sha256": content_sha256(owned),
            "original": copy.deepcopy(previous),
            "updated": copy.deepcopy(observation),
            "operation_index": len(self.operations) - 1,
        }
        self.operations[-1] = (
            "observation",
            copy.deepcopy(observation),
            content_sha256(observation),
        )
        self._revision_receipt("apply", observation.position_source_id, before_hash)

    def _revision_receipt(self, operation, source_id, before_hash):
        row = {
            "operation": operation,
            "source_id": str(source_id),
            "source_sha256": self.location_sources[source_id]["sha256"],
            "before_state": before_hash,
            "after_state": self._state_sha256(),
            "steps": self.step_index,
            "ledger_head": self.rgrc_ledger.head_hash,
            "previous_receipt": self.location_revisions[-1]["sha256"]
            if self.location_revisions
            else None,
        }
        row["sha256"] = content_sha256(row)
        self.location_revisions.append(row)
        return copy.deepcopy(row)

    def revise_location_source(self, source_id, expected_digest, *, restore=False):
        if type(restore) is not bool or source_id not in self.location_sources:
            raise ValueError("unknown source or invalid restore flag")
        source = self.location_sources[source_id]
        if (
            expected_digest != source["sha256"]
            or content_sha256(source["payload"]) != expected_digest
        ):
            raise ValueError("mutated or mismatched source")
        if restore != (source_id in self._withdrawn_locations):
            raise ValueError("source already in requested state")
        for _, payload, digest in self.operations:
            if content_sha256(payload) != digest:
                raise ValueError("mutated replay operation")
        operations = copy.deepcopy(self.operations)
        observation = source["updated"] if restore else source["original"]
        operations[source["operation_index"]] = (
            "observation",
            observation,
            content_sha256(observation),
        )
        snapshot = self._capture_mutable_state()
        before_hash = self._state_sha256()
        old_current_before = self._current_before
        try:
            self._restore_mutable_state(copy.deepcopy(self._initial))
            self._replaying = True
            for kind, payload, _ in operations:
                if kind == "observation":
                    self._current_before = self._capture_mutable_state()
                    StatefulFullJointRuntime.revise(self, payload)
                elif kind == "feedback":
                    StatefulFullJointRuntime.apply_feedback(self, payload)
                else:
                    StatefulFullJointRuntime.record_verification(self, **payload)
            self.verify_internal_contracts()
        except Exception:
            self._restore_mutable_state(snapshot)
            self._current_before = old_current_before
            raise
        finally:
            self._replaying = False
        self.operations = operations
        # Executed decisions are immutable history, not replayed counterfactuals.
        self.action_readout_traces = snapshot["action_readout_traces"]
        if restore:
            self._withdrawn_locations.remove(source_id)
        else:
            self._withdrawn_locations.add(source_id)
        return self._revision_receipt("restore" if restore else "withdraw", source_id, before_hash)


def missing_event_observation(state, episode, step):
    """Public evidence or existing uninformative defaults; no truth or fake detection."""
    actors = _normalize(
        dict(step.actor_evidence.actor_posterior)
        if step.actor_evidence is not None
        else dict.fromkeys(episode.resident_actor_keys, 1.0)
    )
    mechanisms = _normalize(
        {m: step.mechanism_evidence.mechanism_posterior.get(m, 0.0) for m in EventMechanism}
        if step.mechanism_evidence is not None
        else {
            EventMechanism.DIRECT_RELOCATION: 0.45,
            EventMechanism.HANDOFF_RELOCATION: 0.45,
            EventMechanism.UNKNOWN_MECHANISM: 0.10,
        }
    )
    roles = _normalize(
        dict(step.ordered_role_evidence.ordered_role_posterior)
        if step.ordered_role_evidence is not None
        else {
            ordered_role_key(a, b): actors[a] * actors[b] for a in actors for b in actors if a != b
        }
    )
    identity = _identity_probability(step, target_object_id=step.object_instance_id)
    base = state.spine.action_location_distribution(
        state.spine.current_snapshot, readout=state.action_readout
    )
    # These are prediction priors, not current inferred cause/identity evidence.
    return CurrentEventObservation(
        source_update_id=content_uuid(
            "current-event-prediction", (episode.episode_id, step.step_id, step.object_instance_id)
        ),
        evidence_cluster_id=content_uuid("current-event-public-input", step),
        owner_actor_key=episode.owner_actor_key,
        actor_posterior=actors,
        mechanism_posterior=mechanisms,
        ordered_role_posterior=roles,
        identity_target_probability=identity,
        cause_posterior=_complete_cause_posterior(state, identity),
        regime_change_probability=0.0,
        active_regime=state.spine.active_regime,
        observed_location_id=None,
        base_location_distribution=_normalize(base),
        known_location_ids=tuple(state.locations),
        unresolved_probability=state.unresolved_probability,
    )


class CurrentEventActionState(TaskSeparatedFullJointActionState):
    def __init__(self, state, episode, runtime, *, profile, environment, head, consume_new=True):
        super().__init__(state, episode, runtime, profile=profile)
        self.environment, self.head, self.consume_new = environment, head, consume_new
        self.event_actions = []
        self._pending_step = None
        self._needs_feedback = False

    def observe(self, step):
        if self._pending_step is not None:
            raise ValueError("previous event requires action and feedback")
        super().observe(step)
        missing = step.step_id not in self._state.step_results
        if missing:
            self.runtime.revise(missing_event_observation(self._state, self._episode, step))
        self._pending_step = step

    def predict(self):
        if self._pending_step is None or self._needs_feedback:
            raise ValueError("current event already acted or not observed")
        step = self._pending_step
        event_id = self.runtime._last_observation.source_update_id
        before = self.runtime.action_distribution()
        before_actor = self.actor_distribution()
        head_table = self.head.table()
        previous = self.head.previous
        row = execute_current_search(
            self.head, project_search_input(step, self.head.actors, view="native"), self.environment
        )
        source_id = None
        observation = self.runtime._last_observation
        if (
            self.consume_new
            and observation.observed_location_id is None
            and row["found"] is not None
        ):
            # Binding is validated against the environment's owned charged receipts.
            found = row["found"]
            likelihood = tuple(
                (
                    a,
                    head_table[previous, a, found]
                    / sum(head_table[previous, a, loc] for loc in self.head.locations),
                )
                for a in self.head.actors
            )
            payload = {
                "episode_id": str(self._episode.episode_id),
                "object_id": str(step.object_instance_id),
                "step_id": str(step.step_id),
                "event_id": str(event_id),
                "model": {
                    "config": self.head.config,
                    "history_sha256": row["history_before_sha256"],
                },
                "location_likelihood": likelihood,
                "paid_updates": row["updates"],
            }
            source_id = content_uuid("paid-current-location", payload)
            updated = replace(
                observation,
                prediction_only=False,
                observed_location_id=UUID(found),
                position_source_id=source_id,
                location_likelihood=likelihood,
            )
            self.runtime.replace_current_location(updated, payload, self.environment)
        native = super().predict()
        prediction = _Prediction(
            native.put_back, tuple(map(UUID, row["planned_order"])), native.unknown_probability
        )
        self._state.bind_prediction_trace(prediction, self._state._prediction_index - 1)
        self.task_readout_receipts[-1] = replace(
            self.task_readout_receipts[-1], search_order=prediction.search_order
        )
        after = self.runtime.action_distribution()
        self.event_actions.append(
            {
                "step_id": str(step.step_id),
                "event_id": str(event_id),
                "native_step_index": self.runtime.step_index,
                "location_source_id": None if source_id is None else str(source_id),
                "before": {str(k): v for k, v in before.items()},
                "after": {str(k): v for k, v in after.items()},
                "actor_before": before_actor,
                "actor_after": self.actor_distribution(),
                "put_back": str(prediction.put_back),
                "search": copy.deepcopy(row),
                "event_observed_location": None
                if self.runtime._last_observation.observed_location_id is None
                else str(self.runtime._last_observation.observed_location_id),
                "native_state_sha256": self.runtime._state_sha256(),
                "ledger_head": self.runtime.rgrc_ledger.head_hash,
            }
        )
        self._needs_feedback = True
        return prediction

    def actor_distribution(self):
        result = dict.fromkeys(self.head.actors, 0.0)
        for p in self.runtime.particles:
            result[p.world.placement_actor] += p.posterior_probability
        result["unknown_actor"] += self.runtime.unresolved_probability
        return result

    def feedback(self, step):
        if not self._needs_feedback or step.step_id != self._pending_step.step_id:
            raise ValueError("feedback must follow current event action")
        super().feedback(step)
        self._pending_step, self._needs_feedback = None, False
