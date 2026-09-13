"""Detached joint-particle decision views; never proposal or RGRC authority.

The production owner must validate its current workspace before building a view.
Tables use whole-particle IDs, preserving role/instance/cause/regime correlations.
No location-only mixture, observation-model calibration or task utility is invented.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import fsum, isfinite
from typing import TYPE_CHECKING
from uuid import UUID

from cpswm.contracts.grounded_search import ActiveObservationPlan, ObservationActionCandidate
from cpswm.system.reproducibility import content_uuid
from cpswm.world_model.grounded_search.active_verification import (
    CauseInformationActiveVerificationPlanner,
    JointParticleVerificationBelief,
    VerificationCause,
)

if TYPE_CHECKING:
    from cpswm.system.evaluation_operations.structure_two_selected_method import (
        ParticleRevisionBatch,
    )
    from cpswm.system.structure_two_particle_workspace import (
        ConditionalAnalyticState,
        NativeParticleRecord,
    )


@dataclass(frozen=True)
class JointDecisionAtom:
    particle_id: UUID
    probability: float
    state_json: str
    event_chain_json: tuple[str, ...]
    statistics: ConditionalAnalyticState
    source_frame_sha256: str
    ledger_head_sha256: str


@dataclass(frozen=True)
class JointDecisionView:
    """Value object, not an authorization receipt or proof of a default producer."""

    runtime_id: UUID
    snapshot_id: UUID
    evidence_cluster_id: UUID
    atoms: tuple[JointDecisionAtom, ...]
    unresolved_probability: float

    @classmethod
    def from_batch(
        cls,
        *,
        runtime_id: UUID,
        expected_snapshot_id: UUID,
        batch: ParticleRevisionBatch,
        records: Mapping[UUID, NativeParticleRecord],
    ) -> JointDecisionView:
        from cpswm.system.evaluation_operations.structure_two_selected_method import (
            ParticleRevisionBatch,
            TypedParticleState,
        )
        from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState

        batch = ParticleRevisionBatch.model_validate(batch.model_dump())
        if batch.snapshot_id != expected_snapshot_id:
            raise ValueError("joint decision source snapshot is stale")
        ids = [weight.particle_id for weight in batch.particle_weights]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate joint decision particle")
        atoms = []
        for weight in batch.particle_weights:
            if not weight.accepted and weight.posterior_probability != 0:
                raise ValueError("rejected particle has nonzero decision mass")
            if weight.posterior_probability == 0:
                continue
            record = records.get(weight.particle_id)
            if record is None:
                raise ValueError("joint decision particle has no source record")
            state = TypedParticleState.model_validate(record.state.model_dump())
            stats = record.statistics
            detached = ConditionalAnalyticState(
                locations=tuple(stats.locations),
                alpha=tuple(stats.alpha),
                a=tuple(tuple(row) for row in stats.a),
                b=tuple(stats.b),
                information=tuple(tuple(row) for row in stats.information),
                information_vector=tuple(stats.information_vector),
                evidence_cluster_ids=tuple(stats.evidence_cluster_ids),
            )
            if (
                state.particle_id != weight.particle_id
                or state.source_snapshot_id != batch.snapshot_id
                or state.statistic_state_ref != detached.reference
                or state.ledger_lineage_ref != "hybrid-ledger:" + record.ledger_head_sha256
                or not record.event_chain_history
            ):
                raise ValueError("joint decision record references do not match")
            atoms.append(
                JointDecisionAtom(
                    particle_id=weight.particle_id,
                    probability=weight.posterior_probability,
                    state_json=state.model_dump_json(),
                    event_chain_json=tuple(h.model_dump_json() for h in record.event_chain_history),
                    statistics=detached,
                    source_frame_sha256=record.source_frame_sha256,
                    ledger_head_sha256=record.ledger_head_sha256,
                )
            )
        return cls(
            runtime_id=runtime_id,
            snapshot_id=batch.snapshot_id,
            evidence_cluster_id=batch.evidence_cluster_id,
            atoms=tuple(sorted(atoms, key=lambda item: str(item.particle_id))),
            unresolved_probability=batch.unresolved_probability,
        )

    @property
    def content_sha256(self) -> str:
        from cpswm.system.structure_two_particle_workspace import native_content_sha256

        return native_content_sha256(self)

    @property
    def unresolved_id(self) -> UUID:
        return content_uuid(
            "native-joint-decision-unresolved",
            {
                "runtime_id": self.runtime_id,
                "snapshot_id": self.snapshot_id,
                "evidence_cluster_id": self.evidence_cluster_id,
            },
        )

    def verification_belief(self) -> JointParticleVerificationBelief:
        from cpswm.system.evaluation_operations.structure_two_selected_method import (
            TypedParticleState,
        )

        prior = {a.particle_id: a.probability for a in self.atoms}
        causes = {
            a.particle_id: VerificationCause(
                TypedParticleState.model_validate_json(a.state_json).change_cause.value
            )
            for a in self.atoms
        }
        if len(prior) != len(self.atoms) or self.unresolved_id in prior:
            raise ValueError("joint atom identity collision")
        prior[self.unresolved_id] = self.unresolved_probability
        causes[self.unresolved_id] = VerificationCause.UNRESOLVED
        return JointParticleVerificationBelief(
            posterior=prior,
            cause_by_atom=causes,
            source_snapshot_sha256=self.content_sha256,
        )

    def expected_utilities(
        self,
        utilities: Mapping[UUID, Mapping[UUID, float]],
        *,
        source_belief_sha256: str,
    ) -> dict[UUID, float]:
        """Read the full joint expectation; does not choose a scientific utility."""
        if source_belief_sha256 != self.content_sha256:
            raise ValueError("decision table belongs to another joint snapshot")
        prior = self.verification_belief().as_uuid_prior()
        if not utilities or any(set(row) != set(prior) for row in utilities.values()):
            raise ValueError("decisions must cover every joint atom including unresolved")
        result = {}
        for decision, row in utilities.items():
            if not all(isfinite(v) for v in row.values()):
                raise ValueError("nonfinite joint decision utility")
            try:
                value = fsum(prior[key] * row[key] for key in prior)
            except OverflowError as error:
                raise ValueError("joint decision expectation overflow") from error
            if not isfinite(value):
                raise ValueError("joint decision expectation is nonfinite")
            result[decision] = value
        return result

    def select_verification(
        self,
        planner: CauseInformationActiveVerificationPlanner,
        actions: tuple[ObservationActionCandidate, ...],
        *,
        source_belief_sha256: str,
        consolidation_decision_utilities: dict[UUID, dict[UUID, float]],
        terminal_decision_utilities: dict[UUID, dict[UUID, float]],
        privacy_budget: float,
        minimum_net_value: float = 0.0,
    ) -> ActiveObservationPlan:
        # Both utility tables and outcome likelihoods must have been built for
        # this view. Content binding does not certify the physical outcome model.
        self.expected_utilities(
            terminal_decision_utilities, source_belief_sha256=source_belief_sha256
        )
        self.expected_utilities(
            consolidation_decision_utilities, source_belief_sha256=source_belief_sha256
        )
        return planner.select(
            self.verification_belief(),
            actions,
            consolidation_decision_utilities=consolidation_decision_utilities,
            terminal_decision_utilities=terminal_decision_utilities,
            privacy_budget=privacy_budget,
            minimum_net_value=minimum_net_value,
        )
