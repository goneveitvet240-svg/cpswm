"""Compute real analytic states for automatically generated full-axis proposals.

This is a full-history conditional evaluation boundary, not an SMC sampler or
ledger. Every competing hypothesis starts from the same explicit prior and sees
the same arrived evidence groups. Rejuvenation uses full replay here, preserving
raw evidence rather than misinterpreting a replaced latent revision as a revoked
observation. No efficiency or empirical calibration is asserted by this module.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Any, Protocol
from uuid import UUID

from pydantic import Field

from cpswm.contracts.base import ContractModel
from cpswm.data_preflight.proposal_samples import FullHypothesis, ProposalContext, ProposalTarget
from cpswm.data_preflight.runtime_candidates import GeneratedSupport, generate_runtime_candidates
from cpswm.system.continuous_state_codec import StateCodec
from cpswm.system.reproducibility import content_sha256
from cpswm.system.structure_two_conditional_updates import (
    ConditionalMeasurement,
    rebuild_conditional_state,
)
from cpswm.system.structure_two_particle_workspace import ConditionalAnalyticState


class ConditionalEvidenceGroup(ContractModel):
    """An ingestion-owned evidence cluster; its complete arrived records are pinned."""

    evidence_cluster_id: UUID
    source_record_ids: tuple[UUID, ...] = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def evidence_group(
    context: ProposalContext, cluster_id: UUID, record_ids: tuple[UUID, ...]
) -> ConditionalEvidenceGroup:
    """Bind actual visible record bodies, not an external truth/annotation payload."""
    records = {
        UUID(row["record_id"]): row
        for row in json.loads(context.visible.prefix().provenance_json)["included_records"]
    }
    if (
        not record_ids
        or len(set(record_ids)) != len(record_ids)
        or not set(record_ids) <= set(records)
    ):
        raise ValueError("evidence group needs unique arrived source records")
    ids = tuple(sorted(record_ids, key=str))
    return ConditionalEvidenceGroup(
        evidence_cluster_id=cluster_id,
        source_record_ids=ids,
        source_sha256=content_sha256(tuple(records[key] for key in ids)),
    )


class ConditionalProposalModel(Protocol):
    """Configured conditional model; identity does not certify its calibration.

    State is checkpointed/restored around each candidate and on failure. A model
    must evaluate all three blocks, including explicit zeros where unsupported.
    Returning invented measurements is not made legitimate by this interface.
    """

    binding_sha256: str
    observation_model_id: str

    def checkpoint_state(self) -> dict[str, Any]: ...

    def restore_state(self, state: dict[str, Any]) -> None: ...

    def measure(
        self,
        context: ProposalContext,
        target: ProposalTarget,
        group: ConditionalEvidenceGroup,
        retained_state: ConditionalAnalyticState,
    ) -> ConditionalMeasurement: ...


@dataclass(frozen=True)
class ConditionedProposal:
    """Keep the scored target immutable; only the derived statistic ref changes."""

    origin_target_json: str
    resolved_hypothesis_json: str
    statistics: ConditionalAnalyticState
    measurements: tuple[ConditionalMeasurement, ...]
    source_group_sha256s: tuple[str, ...]
    evaluation_mode: str

    @property
    def origin(self) -> ProposalTarget:
        return ProposalTarget.model_validate_json(self.origin_target_json)

    @property
    def resolved_hypothesis(self) -> FullHypothesis:
        return FullHypothesis.model_validate_json(self.resolved_hypothesis_json)

    @property
    def scored_target_sha256(self) -> str:
        return content_sha256(self.origin.model_dump(mode="json"))


@dataclass(frozen=True)
class ConditionedSupport:
    context_sha256: str
    generated_support_sha256: str
    model_binding_sha256: str
    prior: ConditionalAnalyticState
    groups: tuple[ConditionalEvidenceGroup, ...]
    candidates: tuple[ConditionedProposal, ...]
    ledger_write_authority: bool = False
    native_publication_authority: bool = False
    empirical_calibration_certified: bool = False

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)


def _model_binding(model: ConditionalProposalModel, expected: str, model_id: str) -> None:
    if (
        len(expected) != 64
        or any(c not in "0123456789abcdef" for c in expected)
        or not model_id.strip()
        or model.binding_sha256 != expected
        or model.observation_model_id != model_id
    ):
        raise ValueError("conditional model dependency binding changed or is missing")


def condition_generated_support(
    generated: GeneratedSupport,
    *,
    bootstrap_ledger_lineage_ref: str,
    groups: tuple[ConditionalEvidenceGroup, ...],
    prior: ConditionalAnalyticState,
    parent_statistics: dict[UUID, ConditionalAnalyticState],
    model: ConditionalProposalModel,
    expected_model_binding_sha256: str,
    max_candidates: int = 4096,
) -> ConditionedSupport:
    """Evaluate all generated candidates with full replay and no state promotion.

    All source groups are retained for branch/revise/reactivate/rejuvenate and
    unresolved hypotheses. Retract is a removal proposal: it retains the original
    parent's analytic state without counting the new evidence as a contribution.
    No revision is applied to a live posterior or the RGRC ledger here.
    """
    regenerated = generate_runtime_candidates(
        generated.context,
        bootstrap_ledger_lineage_ref=bootstrap_ledger_lineage_ref,
        max_candidates=max_candidates,
    )
    if regenerated != generated:
        raise ValueError("conditional input is not complete regenerated proposal support")
    context = regenerated.context
    targets = regenerated.targets
    initial = rebuild_conditional_state(prior, ())
    if initial.evidence_cluster_ids or len(initial.information_vector) != 6:
        raise ValueError("explicit empty-history six-dimensional pose prior required")
    known_locations = {
        b.location_entity_id for b in context.location_support if b.location_entity_id is not None
    }
    if not known_locations <= set(initial.locations):
        raise ValueError("conditional prior omits a declared world location")
    groups = tuple(ConditionalEvidenceGroup.model_validate(g.model_dump()) for g in groups)
    ids = tuple(r for g in groups for r in g.source_record_ids)
    visible_ids = {
        UUID(row["record_id"])
        for row in json.loads(context.visible.prefix().provenance_json)["included_records"]
    }
    if (
        not groups
        or len({g.evidence_cluster_id for g in groups}) != len(groups)
        or len(set(ids)) != len(ids)
        or set(ids) != visible_ids
    ):
        raise ValueError("conditional groups must partition the complete arrived evidence once")
    for group in groups:
        if group != evidence_group(context, group.evidence_cluster_id, group.source_record_ids):
            raise ValueError("conditional group differs from visible source content")
    groups = tuple(
        sorted(
            groups,
            key=lambda g: (
                max(context._evidence_time(r) for r in g.source_record_ids),
                str(g.evidence_cluster_id),
            ),
        )
    )
    parents = {p.state.particle_id: p for p in context.parents}
    if set(parent_statistics) != set(parents):
        raise ValueError("conditional parent state coverage differs from actual proposal parents")
    detached_parents = {}
    for key, state in parent_statistics.items():
        checked = rebuild_conditional_state(state, ())
        if (
            checked.reference != parents[key].state.statistic_state_ref
            or checked.locations != initial.locations
            or len(checked.b) != len(initial.b)
            or len(checked.information_vector) != 6
        ):
            raise ValueError("conditional parent state does not bind its source particle")
        detached_parents[key] = checked

    model_id = model.observation_model_id
    _model_binding(model, expected_model_binding_sha256, model_id)
    checkpoint = deepcopy(model.checkpoint_state())
    codec = StateCodec()
    checkpoint_bytes = codec.dumps(checkpoint)

    def restore_model() -> None:
        model.restore_state(deepcopy(checkpoint))
        _model_binding(model, expected_model_binding_sha256, model_id)
        if codec.dumps(model.checkpoint_state()) != checkpoint_bytes:
            raise ValueError("conditional model did not restore its original inference state")

    results = []
    try:
        for target in targets:
            restore_model()  # Same model/RNG starting point for every competing hypothesis.
            if target.operation.value == "retract":
                parent_id = target.candidate.state.parent_particle_id
                assert parent_id is not None
                analytic = detached_parents[parent_id]
                measurements: list[ConditionalMeasurement] = []
                source_hashes: tuple[str, ...] = ()
                mode = "removal_preserves_parent_state"
            else:
                analytic = initial
                measurements = []
                for group in groups:
                    measurement = model.measure(
                        context.model_copy(deep=True),
                        target.model_copy(deep=True),
                        group.model_copy(deep=True),
                        deepcopy(analytic),
                    ).detached()
                    _model_binding(model, expected_model_binding_sha256, model_id)
                    if (
                        measurement.evidence_cluster_id != group.evidence_cluster_id
                        or measurement.source_record_ids != group.source_record_ids
                        or measurement.observation_model_id != model_id
                    ):
                        raise ValueError("conditional measurement changed its source/model group")
                    measurements.append(measurement)
                    analytic = rebuild_conditional_state(initial, tuple(measurements))
                source_hashes = tuple(g.source_sha256 for g in groups)
                mode = "full_history_replay_no_observation_removed"
            resolved_state = target.candidate.state.model_copy(
                update={"statistic_state_ref": analytic.reference}
            )
            resolved = FullHypothesis.model_validate(
                {"state": resolved_state, "events": target.candidate.events}
            )
            results.append(
                ConditionedProposal(
                    target.model_dump_json(),
                    resolved.model_dump_json(),
                    deepcopy(analytic),
                    tuple(deepcopy(measurements)),
                    source_hashes,
                    mode,
                )
            )
    finally:
        restore_model()
    return ConditionedSupport(
        content_sha256(context),
        content_sha256(generated),
        expected_model_binding_sha256,
        initial,
        groups,
        tuple(results),
    )


def verify_conditioned_support(
    submitted: ConditionedSupport,
    generated: GeneratedSupport,
    **dependencies: Any,
) -> ConditionedSupport:
    """Replay against externally retained inputs/model; a rehash is insufficient."""
    expected = condition_generated_support(generated, **dependencies)
    if submitted != expected or submitted.content_sha256 != expected.content_sha256:
        raise ValueError("conditioned support differs from full model replay")
    # Return the recomputed result, never nested aliases supplied by a caller.
    return replace(expected)
