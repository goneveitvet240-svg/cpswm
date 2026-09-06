from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cpswm.system.evaluation_operations.structure_two_selected_method import (
    CommitAuthority,
    NeuralParticleProposal,
    OrderedActorRole,
    ParticleChangeCause,
    ParticleProposalOperation,
    ParticleRegimeDecision,
    ParticleRevisionReceipt,
    ProposalAuthority,
    ReversibleCommitProtocol,
    RevisionAuthority,
    StructuredConstraint,
    StructuredWeightFactor,
    StructureTwoSelectedMethod,
    TypedParticleState,
    normalize_particle_revisions,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/project_two_experiments/structure_two_selected_method_v0_1.json"


def _particle(*, snapshot_id, parent_particle_id=None) -> TypedParticleState:
    return TypedParticleState(
        particle_id=uuid4(),
        parent_particle_id=parent_particle_id,
        source_snapshot_id=snapshot_id,
        event_hypothesis_id=uuid4(),
        revision_id=uuid4(),
        ordered_actor_roles=(
            OrderedActorRole(role="pickup_actor", actor_key="person-a"),
            OrderedActorRole(role="placement_actor", actor_key="person-b"),
        ),
        instance_association_key="object-instance-a",
        change_cause=ParticleChangeCause.HABIT,
        regime_decision=ParticleRegimeDecision.REACTIVATE,
        regime_id="weekday-regime",
        run_length=2,
        statistic_state_ref="hybrid-statistics@41",
        ledger_lineage_ref="rgrc-lineage@17",
    )


def _constraints(*, reject_identity: bool = False) -> tuple[StructuredConstraint, ...]:
    factors = (
        StructuredWeightFactor.PHYSICAL_EVENT_CONSTRAINT,
        StructuredWeightFactor.ORDERED_ROLE_CONSTRAINT,
        StructuredWeightFactor.IDENTITY_CONSTRAINT,
        StructuredWeightFactor.PROVENANCE_CONSTRAINT,
    )
    return tuple(
        StructuredConstraint(
            factor=factor,
            accepted=not (reject_identity and factor is StructuredWeightFactor.IDENTITY_CONSTRAINT),
            log_potential=-0.1,
            rejection_reason=(
                "identity association violates the frozen candidate set"
                if reject_identity and factor is StructuredWeightFactor.IDENTITY_CONSTRAINT
                else None
            ),
        )
        for factor in factors
    )


def _receipt(*, snapshot_id, cluster_id, reject_identity=False) -> ParticleRevisionReceipt:
    source_particle_id = uuid4()
    state = _particle(snapshot_id=snapshot_id, parent_particle_id=source_particle_id)
    proposal = NeuralParticleProposal(
        proposal_id=uuid4(),
        evidence_cluster_id=cluster_id,
        operation=ParticleProposalOperation.REVISE,
        source_particle_id=source_particle_id,
        source_snapshot_id=snapshot_id,
        proposed_state=state,
        proposal_log_probability=-1.2,
        proposer_model_version="proposal-model@0.1",
        proposer_code_version="code@0.1",
    )
    return ParticleRevisionReceipt(
        proposal=proposal,
        prior_log_weight=-0.7,
        transition_log_probability=-0.3,
        observation_log_likelihood=-0.2,
        constraints=_constraints(reject_identity=reject_identity),
    )


def test_selected_method_receipt_freezes_scope_authority_and_unresolved_work() -> None:
    selection = StructureTwoSelectedMethod.load(CONFIG)

    assert selection.method_id == "structure-two-nap-rbtpr-rc@0.1"
    assert selection.proposal_authority is ProposalAuthority.PROPOSE_AND_SCORE_ONLY
    assert selection.commit_authority is CommitAuthority.REVERSIBLE_RGRC_LEDGER_ONLY
    assert selection.explicit_unresolved_mass
    assert not selection.implementation_complete
    assert not selection.paper_claim_allowed
    assert len(selection.content_sha256) == 64


def test_selected_method_rejects_scope_narrowing_and_authority_escalation() -> None:
    payload = StructureTwoSelectedMethod.load(CONFIG).model_dump(mode="python")

    with pytest.raises(ValidationError, match="all seven"):
        StructureTwoSelectedMethod.model_validate({**payload, "operators": ("opceu",)})
    with pytest.raises(ValidationError, match="proposal_authority"):
        StructureTwoSelectedMethod.model_validate(
            {**payload, "proposal_authority": "propose_score_and_commit"}
        )


def test_typed_particle_enforces_cause_regime_and_snapshot_semantics() -> None:
    snapshot_id = uuid4()
    particle = _particle(snapshot_id=snapshot_id)
    payload = particle.model_dump(mode="python")

    with pytest.raises(ValidationError, match="only a habit-cause"):
        TypedParticleState.model_validate({**payload, "change_cause": "actor"})

    source_particle_id = uuid4()
    child = _particle(snapshot_id=snapshot_id, parent_particle_id=source_particle_id)
    with pytest.raises(ValidationError, match="cannot cross belief snapshots"):
        NeuralParticleProposal(
            proposal_id=uuid4(),
            evidence_cluster_id=uuid4(),
            operation=ParticleProposalOperation.REVISE,
            source_particle_id=source_particle_id,
            source_snapshot_id=uuid4(),
            proposed_state=child,
            proposal_log_probability=-0.2,
            proposer_model_version="proposal-model@0.1",
            proposer_code_version="code@0.1",
        )

    valid_proposal = _receipt(
        snapshot_id=snapshot_id,
        cluster_id=uuid4(),
    ).proposal.model_dump(mode="python")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        NeuralParticleProposal.model_validate({**valid_proposal, "commit_long_term_memory": True})


def test_particle_revision_normalizes_with_unresolved_and_zeroes_rejected_particle() -> None:
    snapshot_id = uuid4()
    cluster_id = uuid4()
    accepted = _receipt(snapshot_id=snapshot_id, cluster_id=cluster_id)
    rejected = _receipt(
        snapshot_id=snapshot_id,
        cluster_id=cluster_id,
        reject_identity=True,
    )

    batch = normalize_particle_revisions(
        (accepted, rejected),
        unresolved_log_weight=-0.4,
    )

    assert batch.snapshot_id == snapshot_id
    assert batch.evidence_cluster_id == cluster_id
    assert batch.particle_weights[0].posterior_probability > 0.0
    assert batch.particle_weights[1].posterior_probability == 0.0
    assert not batch.particle_weights[1].accepted
    assert batch.unresolved_probability > 0.0
    assert sum(item.posterior_probability for item in batch.particle_weights) + (
        batch.unresolved_probability
    ) == pytest.approx(1.0)


def test_reversible_commit_protocol_keeps_ledger_as_unique_writer() -> None:
    protocol = ReversibleCommitProtocol(
        schema_version="0.1.0",
        proposal_authority=ProposalAuthority.PROPOSE_AND_SCORE_ONLY,
        revision_authority=RevisionAuthority.NORMALIZE_CONSTRAIN_AND_REVISE_ONLY,
        commit_authority=CommitAuthority.REVERSIBLE_RGRC_LEDGER_ONLY,
        atomic_unit="evidence_cluster_statistic_bundle",
        required_ledger_operations=(
            "quarantine",
            "promote",
            "retract",
            "corrected_revision",
        ),
        requires_full_rerun_equivalence=True,
        requires_replay_fallback_on_numerical_failure=True,
    )

    assert protocol.commit_authority is CommitAuthority.REVERSIBLE_RGRC_LEDGER_ONLY
    assert protocol.requires_full_rerun_equivalence


# --- stage-local forgetting factor: a frozen design, not an open knob ----------


def test_stage_local_forgetting_factor_rejects_every_value_but_one() -> None:
    """The frozen method fixes within-regime forgetting at 1.0.

    The RLS runtime itself admits ``(0, 1]``.  Widening this receipt field to
    that range would silently reopen a frozen design decision -- stage change is
    handled by explicit regime competition, not by unsourced exponential decay.
    """

    from cpswm.system.evaluation_operations.structure_two_selected_method import (
        FROZEN_STAGE_LOCAL_FORGETTING_FACTOR,
    )

    payload = StructureTwoSelectedMethod.load(CONFIG).model_dump(mode="python")
    assert FROZEN_STAGE_LOCAL_FORGETTING_FACTOR == 1.0
    assert payload["stage_local_forgetting_factor"] == FROZEN_STAGE_LOCAL_FORGETTING_FACTOR

    # Values the RLS runtime would happily accept are still refused here.
    for rejected in (0.0, 0.5, 0.9, 0.99, 0.999, 1.0001, 2.0):
        with pytest.raises(ValidationError, match="stage_local_forgetting_factor"):
            StructureTwoSelectedMethod.model_validate(
                {**payload, "stage_local_forgetting_factor": rejected}
            )


def test_stage_local_forgetting_factor_is_bound_to_the_runtime_defaults() -> None:
    """The receipt field is enforced, not decorative JSON.

    Before this binding the value appeared only in the selection contract and
    the config file; nothing downstream read it, so the runtime could have
    drifted to any admissible forgetting factor without a single test failing.
    """

    from cpswm.system.evaluation_operations.structure_two_selected_method import (
        STAGE_LOCAL_FORGETTING_RUNTIME_BINDINGS,
        verify_stage_local_forgetting_runtime_binding,
    )

    selection = StructureTwoSelectedMethod.load(CONFIG)
    assert selection.stage_local_forgetting_runtime_bindings == (
        STAGE_LOCAL_FORGETTING_RUNTIME_BINDINGS
    )
    assert verify_stage_local_forgetting_runtime_binding() == (
        STAGE_LOCAL_FORGETTING_RUNTIME_BINDINGS
    )


def test_clarifying_the_forgetting_contract_did_not_move_the_receipt_hashes() -> None:
    """Retuning would need a new receipt version, never a rehash of this one.

    Task 9, the authorization DAG and the backbone open-task protocol pin both
    the receipt's file hash and its content hash.  Making the contract more
    explicit must leave both untouched; a changed value would have to arrive as
    a new receipt version with its own binding-resolution protocol.
    """

    import hashlib

    from cpswm.system.evaluation_operations.structure_two_backbone_open_task_protocols import (
        SELECTED_METHOD_RECEIPT_CONTENT_SHA256 as BACKBONE_CONTENT_SHA256,
    )
    from cpswm.system.evaluation_operations.structure_two_task9_protocol import (
        SELECTED_METHOD_RECEIPT_CONTENT_SHA256,
        SELECTED_METHOD_RECEIPT_FILE_SHA256,
    )

    selection = StructureTwoSelectedMethod.load(CONFIG)
    assert selection.content_sha256 == SELECTED_METHOD_RECEIPT_CONTENT_SHA256
    assert selection.content_sha256 == BACKBONE_CONTENT_SHA256
    assert hashlib.sha256(CONFIG.read_bytes()).hexdigest() == SELECTED_METHOD_RECEIPT_FILE_SHA256
