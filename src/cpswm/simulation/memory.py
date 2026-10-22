"""Source replay bridge to the existing native Route-C filter.

The bridge is an explicit controlled integration fixture, not the production
visual semantic bridge. Delayed corrections rebuild admitted event history for
ALL correction-capable arms; this does not claim native global ORRER acceptance.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

from cpswm.simulation.contracts import ExecutionFeedback, Observation, Visibility, digest

if TYPE_CHECKING:
    from cpswm.system.evaluation_operations.structure_two_neural_amortized import (
        NeuralProposalModel,
    )
    from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
        StatefulFullJointConfig,
        StatefulFullJointRuntime,
    )


class SimulationMemory:
    ARMS = frozenset({"native_joint", "native_factorized", "source_replay", "ordinary_memory"})

    def __init__(
        self,
        episode_id: str,
        locations: Sequence[str],
        arm: str = "native_joint",
        root: Path | None = None,
    ) -> None:
        if arm not in self.ARMS or len(locations) < 2 or len(set(locations)) != len(locations):
            raise ValueError("invalid arm or calibrated location catalogue")
        self.episode_id, self.locations, self.arm = episode_id, tuple(locations), arm
        self.root = root or Path(__file__).resolve().parents[3]
        self.records: dict[str, Observation] = {}
        self.sources: dict[str, Observation] = {}
        self.active_sources: dict[str, str] = {}
        self.now = -1
        self.revision_number = 0
        self.current_location: str | None = None
        self.feedback: list[dict[str, str]] = []
        self.runtime: StatefulFullJointRuntime | None = None
        self.rebuilds = 0
        self.native_target_scores = 0
        self.location_ids = {s: uuid5(NAMESPACE_URL, "cpswm-sim-region:" + s) for s in locations}
        self._native_config: StatefulFullJointConfig | None = None
        self._native_model: NeuralProposalModel | None = None

    @property
    def revision(self) -> str:
        return digest(
            [
                self.episode_id,
                self.revision_number,
                [x.payload() for x in self.records.values()],
                self.feedback,
            ]
        )

    def ingest(self, observation: Observation, now: int) -> bool:
        observation.__post_init__()
        if (
            observation.episode_id != self.episode_id
            or observation.object_id != "target"
            or type(now) is not int
            or now < self.now
            or observation.available_at > now
            or observation.source_id in self.sources
            or (observation.location is not None and observation.location not in self.locations)
        ):
            raise ValueError("foreign, future, repeated or uncalibrated evidence")
        source = self.active_sources.get(observation.event_id)
        old = None if source is None else self.sources[source]
        if old is None and observation.revises is not None:
            raise ValueError("correction has no admitted target")
        if old is not None and (
            observation.revises != old.source_id
            or observation.object_id != old.object_id
            or observation.occurred_at != old.occurred_at
            or observation.robot_generated != old.robot_generated
        ):
            raise ValueError("same event requires an explicit revision of its active source")
        # Build first and publish only after successful native validation.
        # Predictions/losses are visibility evidence, never independent sightings.
        if old is not None and self.arm == "ordinary_memory":
            self.sources[observation.source_id] = observation
            self.active_sources[observation.event_id] = observation.source_id
            self.now = now
            return False
        proposed = {**self.records, observation.event_id: observation}
        ordered = sorted(proposed.values(), key=lambda x: (x.occurred_at, x.event_id))
        runtime = self._rebuild_native(ordered) if self.arm.startswith("native") else None
        self.records = proposed
        self.sources[observation.source_id] = observation
        self.active_sources[observation.event_id] = observation.source_id
        self.now = now
        self.revision_number += 1
        latest = ordered[-1]
        self.current_location = (
            latest.location if latest.visibility == Visibility.OBSERVED else None
        )
        if self.arm.startswith("native"):
            self.runtime = runtime
            self.rebuilds += 1
            assert runtime is not None
            self.native_target_scores += self._rebuild_target_scores(runtime)
        return True

    def _distribution(self, observations: Iterable[Observation]) -> dict[str, float]:
        # Declared integration-fixture base, shared with the replay control.
        # Not the frozen v06 production task readout or a learned prior.
        mass = dict.fromkeys(self.locations, 1.0)
        for obs in observations:
            if obs.visibility == Visibility.OBSERVED and not obs.robot_generated:
                assert obs.location is not None
                mass[obs.location] += dict(obs.actors).get("owner", 0.0) * obs.identity_probability
        total = sum(mass.values())
        return {key: value / total for key, value in mass.items()}

    def _new_native_runtime(self) -> StatefulFullJointRuntime:
        from cpswm.system.evaluation_operations.structure_two_current_event import (
            CurrentEventRuntime,
        )
        from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import (
            FullJointArm,
            load_neural_proposal_model,
            load_stateful_full_joint_config,
        )

        if self._native_config is None:
            self._native_config = load_stateful_full_joint_config(self.root)
            self._native_model = load_neural_proposal_model(
                self._native_config.neural_proposal_model_path
            )
        return CurrentEventRuntime(  # type: ignore[no-untyped-call]
            arm=(
                FullJointArm.STATEFUL_FULL_JOINT
                if self.arm == "native_joint"
                else FullJointArm.MATCHED_FULL_STATE_FACTORIZED
            ),
            config=self._native_config,
            neural_model=self._native_model,
        )

    def _append_native(
        self, runtime: StatefulFullJointRuntime, history: Sequence[Observation]
    ) -> None:
        from cpswm.contracts import EventMechanism
        from cpswm.contracts.hidden_event_evidence import ordered_role_key
        from cpswm.system.evaluation_operations.structure_two_current_event import (
            CurrentEventObservation,
        )
        from cpswm.system.evaluation_operations.structure_two_selected_method import (
            ParticleChangeCause,
        )

        obs = history[-1]
        assert obs.location is not None
        actors = {"owner": 0.0, "guest": 0.0, "unknown_actor": 0.0, **dict(obs.actors)}
        # Direct relocation has no observed handoff; retain an explicit
        # normalized role support without pretending same-person handoff.
        roles = {ordered_role_key("owner", "guest"): 1.0}
        causes = dict.fromkeys(ParticleChangeCause, 0.0)
        causes[ParticleChangeCause.OBSERVATION] = 1.0
        mechanisms = dict.fromkeys(EventMechanism, 0.0)
        mechanisms[EventMechanism.DIRECT_RELOCATION] = 1.0
        base = self._distribution(history)
        runtime.revise(
            CurrentEventObservation(
                source_update_id=uuid5(NAMESPACE_URL, obs.source_id),
                evidence_cluster_id=uuid5(NAMESPACE_URL, obs.event_id),
                owner_actor_key="owner",
                actor_posterior=actors,
                mechanism_posterior=mechanisms,
                ordered_role_posterior=roles,
                identity_target_probability=obs.identity_probability,
                cause_posterior=causes,
                regime_change_probability=0.0,
                active_regime="integration_fixture",
                observed_location_id=self.location_ids[obs.location],
                base_location_distribution={self.location_ids[k]: v for k, v in base.items()},
                known_location_ids=tuple(self.location_ids.values()),
                unresolved_probability=0.0,
                prediction_only=False,
            )
        )

    def _rebuild_native(self, ordered: Sequence[Observation]) -> StatefulFullJointRuntime:
        runtime = self._new_native_runtime()
        history = []
        for obs in ordered:
            if obs.robot_generated or obs.visibility != Visibility.OBSERVED:
                continue
            history.append(obs)
            self._append_native(runtime, history)
        runtime.verify_internal_contracts()
        return runtime

    def _rebuild_target_scores(self, runtime: StatefulFullJointRuntime) -> int:
        return sum(r.target_score_evaluations for r in runtime.fairness_receipts)

    def destination_distribution(self) -> dict[str, float]:
        if self.runtime is not None and self.runtime.particles:
            result = self.runtime.action_distribution()
            return {k: result[v] for k, v in self.location_ids.items()}
        return self._distribution(self.records.values())

    def destination(self) -> str:
        distribution = self.destination_distribution()
        return min(distribution, key=lambda k: (-distribution[k], k))

    def observe_execution(self, feedback: ExecutionFeedback, now: int) -> None:
        # The queue validates command binding before this call. Robot movements
        # update current location but never become observations of owner habits.
        self.ingest(feedback.observation, now)
        self.feedback.append(
            {
                "command_id": feedback.command_id,
                "status": feedback.status,
                "source_id": feedback.observation.source_id,
            }
        )

    def audit(self) -> dict[str, Any]:
        r = self.runtime
        return {
            "arm": self.arm,
            "memory_revision": self.revision,
            "event_count": len(self.records),
            "source_count": len(self.sources),
            "rebuilds": self.rebuilds,
            "total_native_target_scores": self.native_target_scores,
            "current_location": self.current_location,
            "destination_distribution": self.destination_distribution(),
            "native_steps": 0 if r is None else r.step_index,
            "particles": 0 if r is None else len(r.particles),
            "native_state": None if r is None else r._state_sha256(),
            "ledger_head": None if r is None else r.rgrc_ledger.head_hash,
            "operators": []
            if r is None
            else sorted({x.operator.value for x in r.operator_flow_receipts}),
            "native_budget": None if r is None else r.config.particle_budget,
            "operator_executions": {}
            if r is None
            else {
                name: sum(x.executed for x in r.operator_flow_receipts if x.operator.value == name)
                for name in sorted({x.operator.value for x in r.operator_flow_receipts})
            },
            "evidence_level": "controlled_semantic_integration_not_scientific_acceptance",
        }
