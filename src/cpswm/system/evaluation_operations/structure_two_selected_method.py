"""Frozen method backbone for CPSWM Structure Two.

The user-selected backbone is:

* neural amortized proposals for candidate generation and scoring;
* Rao-Blackwellized typed sequential Monte Carlo for posterior revision; and
* a reversible RGRC ledger as the only long-term commit authority.

This module is deliberately a method and authority contract, not a claim that
the neural proposer, particle runtime, or confirmatory evidence already exists.
It also supplies the small, deterministic importance-weight normalization used
by exact-enumeration and particle-runtime conformance tests.
"""

from __future__ import annotations

import json
from enum import StrEnum
from math import exp, isfinite
from pathlib import Path
from typing import Annotated, Final, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel, NonNegativeInt, Probability
from cpswm.system.reproducibility import content_sha256

SELECTED_METHOD_ID = "structure-two-nap-rbtpr-rc@0.1"

#: The frozen within-stage forgetting factor.
#:
#: ``docs/结构二/方向结构二_神经摊销类型化粒子修订与可逆巩固方法冻结_v1.0.md`` §2 states it
#: verbatim: within-regime forgetting is fixed at 1, and distribution change is
#: handled by explicit stage competition rather than by unsourced exponential
#: forgetting.
#: -- inside one regime nothing is forgotten, and distribution change is handled
#: by CF-BOCPD/CCRR stage competition rather than by an exponential decay with
#: no registered source.  This is therefore a *design decision*, not an
#: unfilled hyperparameter: the receipt pins it, and widening the field to the
#: RLS runtime's admissible ``(0, 1]`` would silently reopen a frozen choice.
#:
#: Retuning it is a real option, but it needs its own binding-resolution
#: protocol and a *new* receipt version.  Editing this receipt and rehashing it
#: would pass the new value off as the original frozen design.
FROZEN_STAGE_LOCAL_FORGETTING_FACTOR: Final = 1.0

#: Runtime configuration defaults that must equal the frozen receipt value, so
#: the receipt field is an enforced binding rather than decorative JSON.  The
#: RLS runtime itself accepts ``(0, 1]``; these defaults are where the frozen
#: choice actually lands.
STAGE_LOCAL_FORGETTING_RUNTIME_BINDINGS: Final = (
    "cpswm.system.continual.rls.core.RLSConfig.forgetting_factor",
    "cpswm.system.continual.rls.habit_head.RLSHabitScoreHead.__init__.forgetting_factor",
    "cpswm.system.continual.project_one_regime_loop.PrototypeLoopConfig.forgetting_factor",
    "cpswm.system.evaluation_operations.project_one_protocol."
    "ProjectOneProtocolConfig.forgetting_factor",
)

#: A within-stage forgetting factor.  The frozen route admits exactly one value.
StageLocalForgettingFactor = Annotated[
    float,
    Field(
        ge=FROZEN_STAGE_LOCAL_FORGETTING_FACTOR,
        le=FROZEN_STAGE_LOCAL_FORGETTING_FACTOR,
        description=(
            "frozen at 1.0: no within-regime forgetting; stage change is handled by explicit "
            "regime competition, never by unsourced exponential decay"
        ),
    ),
]


class MethodBackbone(StrEnum):
    NEURAL_AMORTIZED_RB_TYPED_PARTICLE_REVISION = (
        "neural_amortized_proposal_rao_blackwellized_typed_particle_revision"
    )


class ProposalAuthority(StrEnum):
    PROPOSE_AND_SCORE_ONLY = "propose_and_score_only"


class RevisionAuthority(StrEnum):
    NORMALIZE_CONSTRAIN_AND_REVISE_ONLY = "normalize_constrain_and_revise_only"


class CommitAuthority(StrEnum):
    REVERSIBLE_RGRC_LEDGER_ONLY = "reversible_rgrc_ledger_only"


class StructureTwoOperator(StrEnum):
    OPCEU = "opceu"
    ORRER_CHEH = "orrer_cheh"
    PCHMP = "pchmp"
    CF_BOCPD = "cf_bocpd"
    RGRC = "rgrc"
    CCRR = "ccrr"
    CIAV = "ciav"


class RetainedCapability(StrEnum):
    SELECTIVE_OBSERVATION_MODELING = "selective_observation_modeling"
    HIDDEN_EVENT_INFERENCE = "hidden_event_inference"
    MULTI_ACTOR_REASONING = "multi_actor_reasoning"
    OPEN_WORLD_UNKNOWNS = "open_world_unknowns"
    NONSTATIONARY_REGIME_LEARNING = "nonstationary_regime_learning"
    REVERSIBLE_ATTRIBUTION = "reversible_attribution"
    ACTIVE_VERIFICATION = "active_verification"
    EMBODIED_EXECUTION_FEEDBACK = "embodied_execution_feedback"


class ParticleVariable(StrEnum):
    EVENT_CHAIN = "event_chain"
    ORDERED_ACTOR_ROLES = "ordered_actor_roles"
    INSTANCE_ASSOCIATION = "instance_association"
    CHANGE_CAUSE = "change_cause"
    HABIT_REGIME = "habit_regime"
    RUN_LENGTH = "run_length"
    REVISION_LINEAGE = "revision_lineage"


class RaoBlackwellizedBlock(StrEnum):
    DIRICHLET_LOCATION = "dirichlet_location"
    RIDGE_RLS_NATURAL_STATISTICS = "ridge_rls_natural_statistics"
    INFORMATION_FORM_BELIEF = "information_form_belief"


class ParticleProposalOperation(StrEnum):
    BRANCH = "branch"
    REVISE = "revise"
    RETRACT = "retract"
    REACTIVATE = "reactivate"
    REJUVENATE = "rejuvenate"
    PRESERVE_UNRESOLVED = "preserve_unresolved"


class StructuredWeightFactor(StrEnum):
    OBSERVATION_LIKELIHOOD = "observation_likelihood"
    TRANSITION_PRIOR = "transition_prior"
    PHYSICAL_EVENT_CONSTRAINT = "physical_event_constraint"
    ORDERED_ROLE_CONSTRAINT = "ordered_role_constraint"
    IDENTITY_CONSTRAINT = "identity_constraint"
    PROVENANCE_CONSTRAINT = "provenance_constraint"


class UnresolvedMethodBinding(StrEnum):
    NEURAL_PROPOSER_ARCHITECTURE = "neural_proposer_architecture"
    PARTICLE_BUDGET = "particle_budget"
    RESAMPLING_POLICY = "resampling_policy"
    REJUVENATION_KERNEL = "rejuvenation_kernel"
    DIFFERENTIABILITY_STRATEGY = "differentiability_strategy"
    TRAINING_SCHEDULE = "training_schedule"
    CONSOLIDATION_THRESHOLDS = "consolidation_thresholds"
    CIAV_ACTION_BUDGET = "ciav_action_budget"
    EXACT_ENUMERATION_FALSIFIER = "exact_enumeration_falsifier"


class ParticleChangeCause(StrEnum):
    OBSERVATION = "observation"
    ACTOR = "actor"
    IDENTITY = "identity"
    HABIT = "habit"
    NOISE = "noise"
    UNRESOLVED = "unresolved"


class ParticleRegimeDecision(StrEnum):
    STAY = "stay"
    CREATE = "create"
    REACTIVATE = "reactivate"
    UNRESOLVED = "unresolved"


REQUIRED_OPERATORS = frozenset(StructureTwoOperator)
REQUIRED_CAPABILITIES = frozenset(RetainedCapability)
REQUIRED_PARTICLE_VARIABLES = frozenset(ParticleVariable)
REQUIRED_RB_BLOCKS = frozenset(RaoBlackwellizedBlock)
REQUIRED_PROPOSAL_OPERATIONS = frozenset(ParticleProposalOperation)
REQUIRED_WEIGHT_FACTORS = frozenset(StructuredWeightFactor)
REQUIRED_UNRESOLVED_BINDINGS = frozenset(UnresolvedMethodBinding)


class StructureTwoSelectedMethod(ContractModel):
    """Machine-readable user selection, with no experimental pass claims."""

    schema_version: Literal["0.1.0"]
    method_id: Literal["structure-two-nap-rbtpr-rc@0.1"]
    decision_source: Literal["user_selection"]
    backbone: MethodBackbone
    proposal_authority: ProposalAuthority
    revision_authority: RevisionAuthority
    commit_authority: CommitAuthority
    operators: tuple[StructureTwoOperator, ...]
    retained_capabilities: tuple[RetainedCapability, ...]
    sampled_particle_variables: tuple[ParticleVariable, ...]
    rao_blackwellized_blocks: tuple[RaoBlackwellizedBlock, ...]
    proposal_operations: tuple[ParticleProposalOperation, ...]
    structured_weight_factors: tuple[StructuredWeightFactor, ...]
    explicit_unresolved_mass: Literal[True]
    stage_local_forgetting_factor: StageLocalForgettingFactor
    unresolved_method_bindings: tuple[UnresolvedMethodBinding, ...]

    @model_validator(mode="after")
    def _freeze_selected_method(self) -> Self:
        if self.backbone is not MethodBackbone.NEURAL_AMORTIZED_RB_TYPED_PARTICLE_REVISION:
            raise ValueError("the selected Structure Two method backbone cannot be substituted")
        if self.proposal_authority is not ProposalAuthority.PROPOSE_AND_SCORE_ONLY:
            raise ValueError("the neural proposer may only propose and score")
        if self.revision_authority is not RevisionAuthority.NORMALIZE_CONSTRAIN_AND_REVISE_ONLY:
            raise ValueError("the structured revision layer cannot acquire commit authority")
        if self.commit_authority is not CommitAuthority.REVERSIBLE_RGRC_LEDGER_ONLY:
            raise ValueError("only the reversible RGRC ledger may commit long-term memory")
        if set(self.operators) != REQUIRED_OPERATORS:
            raise ValueError("the selected method must retain all seven Structure Two operators")
        if set(self.retained_capabilities) != REQUIRED_CAPABILITIES:
            raise ValueError("the selected method cannot narrow the Structure Two capabilities")
        if set(self.sampled_particle_variables) != REQUIRED_PARTICLE_VARIABLES:
            raise ValueError("the typed particle must carry the complete discrete revision state")
        if set(self.rao_blackwellized_blocks) != REQUIRED_RB_BLOCKS:
            raise ValueError("all selected analytic sufficient-statistic blocks must be retained")
        if set(self.proposal_operations) != REQUIRED_PROPOSAL_OPERATIONS:
            raise ValueError("the proposal kernel must preserve every revision operation")
        if set(self.structured_weight_factors) != REQUIRED_WEIGHT_FACTORS:
            raise ValueError("particle weights must apply every frozen structured factor")
        if set(self.unresolved_method_bindings) != REQUIRED_UNRESOLVED_BINDINGS:
            raise ValueError("the selection receipt must expose every unresolved method binding")
        if self.stage_local_forgetting_factor != FROZEN_STAGE_LOCAL_FORGETTING_FACTOR:
            raise ValueError(
                "stage_local_forgetting_factor is frozen at "
                f"{FROZEN_STAGE_LOCAL_FORGETTING_FACTOR}: within-regime forgetting is disabled by "
                "design and stage change is handled by explicit regime competition; retuning it "
                "requires a new selected-method receipt version and its own binding-resolution "
                "protocol, not an edit to this receipt"
            )
        return self

    @property
    def stage_local_forgetting_runtime_bindings(self) -> tuple[str, ...]:
        """Runtime defaults this receipt's forgetting factor is bound to."""

        return STAGE_LOCAL_FORGETTING_RUNTIME_BINDINGS

    @classmethod
    def load(cls, path: Path) -> Self:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

    @property
    def content_sha256(self) -> str:
        return content_sha256(self)

    @property
    def implementation_complete(self) -> bool:
        return False

    @property
    def paper_claim_allowed(self) -> bool:
        return False


class OrderedActorRole(ContractModel):
    role: str = Field(min_length=1)
    actor_key: str = Field(min_length=1)


class TypedParticleState(ContractModel):
    """One discrete world-line hypothesis plus references to analytic state."""

    particle_id: UUID
    parent_particle_id: UUID | None
    source_snapshot_id: UUID
    event_hypothesis_id: UUID
    revision_id: UUID
    parent_revision_id: UUID | None = None
    ordered_actor_roles: tuple[OrderedActorRole, ...]
    instance_association_key: str = Field(min_length=1)
    change_cause: ParticleChangeCause
    regime_decision: ParticleRegimeDecision
    regime_id: str | None
    run_length: NonNegativeInt
    statistic_state_ref: str = Field(min_length=1)
    ledger_lineage_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_typed_state(self) -> Self:
        if self.parent_particle_id == self.particle_id:
            raise ValueError("a particle cannot be its own parent")
        role_names = tuple(binding.role for binding in self.ordered_actor_roles)
        if len(role_names) != len(set(role_names)):
            raise ValueError("ordered actor roles must be unique within one particle")
        if self.regime_decision is ParticleRegimeDecision.UNRESOLVED:
            if self.regime_id is not None:
                raise ValueError("an unresolved regime decision cannot name a regime")
        elif self.regime_id is None or not self.regime_id.strip():
            raise ValueError("a resolved regime decision must name its destination regime")
        if self.change_cause is not ParticleChangeCause.HABIT and self.regime_decision in {
            ParticleRegimeDecision.CREATE,
            ParticleRegimeDecision.REACTIVATE,
        }:
            raise ValueError("only a habit-cause particle may create or reactivate a regime")
        return self


class NeuralParticleProposal(ContractModel):
    """A neural proposal has no field capable of authorizing a ledger write."""

    proposal_id: UUID
    evidence_cluster_id: UUID
    operation: ParticleProposalOperation
    source_particle_id: UUID | None
    source_snapshot_id: UUID
    proposed_state: TypedParticleState
    proposal_log_probability: float = Field(le=0.0)
    proposer_model_version: str = Field(min_length=1)
    proposer_code_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _bind_proposal_to_source(self) -> Self:
        if not isfinite(self.proposal_log_probability):
            raise ValueError("proposal_log_probability must be finite")
        if self.proposed_state.source_snapshot_id != self.source_snapshot_id:
            raise ValueError("a proposal cannot cross belief snapshots")
        if self.proposed_state.parent_particle_id != self.source_particle_id:
            raise ValueError("proposed particle parent must equal the proposal source")
        if self.operation is ParticleProposalOperation.BRANCH and self.source_particle_id is None:
            raise ValueError("branch requires a source particle")
        return self


class StructuredConstraint(ContractModel):
    factor: StructuredWeightFactor
    accepted: bool
    log_potential: float = Field(le=0.0)
    rejection_reason: str | None = None

    @model_validator(mode="after")
    def _validate_constraint(self) -> Self:
        if not isfinite(self.log_potential):
            raise ValueError("constraint log_potential must be finite")
        if self.accepted and self.rejection_reason is not None:
            raise ValueError("an accepted constraint cannot have a rejection reason")
        if not self.accepted and (
            self.rejection_reason is None or not self.rejection_reason.strip()
        ):
            raise ValueError("a rejected constraint requires an audit reason")
        return self


class ParticleRevisionReceipt(ContractModel):
    """Auditable terms for one SMC importance-weight update."""

    proposal: NeuralParticleProposal
    prior_log_weight: float
    transition_log_probability: float = Field(le=0.0)
    observation_log_likelihood: float
    posterior_projection_log_factor: float = 0.0
    evidence_semantics: Literal[
        "raw_observation_likelihood", "posterior_projection_not_likelihood"
    ] = "raw_observation_likelihood"
    source_posterior_snapshot_id: UUID | None = None
    constraints: tuple[StructuredConstraint, ...]

    @model_validator(mode="after")
    def _validate_weight_terms(self) -> Self:
        numeric_terms = (
            self.prior_log_weight,
            self.transition_log_probability,
            self.observation_log_likelihood,
            self.posterior_projection_log_factor,
        )
        if not all(isfinite(value) for value in numeric_terms):
            raise ValueError("particle weight terms must be finite")
        if self.evidence_semantics == "posterior_projection_not_likelihood":
            if self.observation_log_likelihood != 0.0:
                raise ValueError(
                    "a posterior projection cannot also claim an observation likelihood"
                )
            if self.source_posterior_snapshot_id is None:
                raise ValueError("a posterior projection requires its source snapshot identity")
        elif self.posterior_projection_log_factor != 0.0:
            raise ValueError("raw-likelihood revisions cannot carry a posterior projection factor")
        constraint_factors = tuple(constraint.factor for constraint in self.constraints)
        if len(constraint_factors) != len(set(constraint_factors)):
            raise ValueError("a structured weight factor may appear only once per particle")
        if set(constraint_factors) != REQUIRED_WEIGHT_FACTORS - {
            StructuredWeightFactor.OBSERVATION_LIKELIHOOD,
            StructuredWeightFactor.TRANSITION_PRIOR,
        }:
            raise ValueError("revision receipt must include every structural constraint")
        return self

    @property
    def accepted(self) -> bool:
        return all(constraint.accepted for constraint in self.constraints)

    @property
    def unnormalized_log_weight(self) -> float:
        if not self.accepted:
            return float("-inf")
        return (
            self.prior_log_weight
            + self.transition_log_probability
            + self.observation_log_likelihood
            + self.posterior_projection_log_factor
            + sum(constraint.log_potential for constraint in self.constraints)
            - self.proposal.proposal_log_probability
        )


class NormalizedParticleWeight(ContractModel):
    proposal_id: UUID
    particle_id: UUID
    posterior_probability: Probability
    accepted: bool


class ParticleRevisionBatch(ContractModel):
    """One normalized competitive set, including explicit unresolved mass."""

    snapshot_id: UUID
    evidence_cluster_id: UUID
    particle_weights: tuple[NormalizedParticleWeight, ...]
    unresolved_probability: Probability

    @model_validator(mode="after")
    def _normalized(self) -> Self:
        total = self.unresolved_probability + sum(
            item.posterior_probability for item in self.particle_weights
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError("particle and unresolved probabilities must sum to one")
        return self


def normalize_particle_revisions(
    receipts: tuple[ParticleRevisionReceipt, ...],
    *,
    unresolved_log_weight: float,
) -> ParticleRevisionBatch:
    """Normalize accepted particle weights together with unresolved mass."""

    if not receipts:
        raise ValueError("at least one particle revision receipt is required")
    if not isfinite(unresolved_log_weight):
        raise ValueError("unresolved_log_weight must be finite")
    snapshot_ids = {receipt.proposal.source_snapshot_id for receipt in receipts}
    cluster_ids = {receipt.proposal.evidence_cluster_id for receipt in receipts}
    proposal_ids = {receipt.proposal.proposal_id for receipt in receipts}
    particle_ids = {receipt.proposal.proposed_state.particle_id for receipt in receipts}
    if len(snapshot_ids) != 1 or len(cluster_ids) != 1:
        raise ValueError("a revision batch cannot mix snapshots or evidence clusters")
    if len(proposal_ids) != len(receipts) or len(particle_ids) != len(receipts):
        raise ValueError("proposal and particle identifiers must be unique in a batch")

    log_weights = tuple(receipt.unnormalized_log_weight for receipt in receipts)
    finite_candidates = [value for value in log_weights if isfinite(value)]
    maximum = max([unresolved_log_weight, *finite_candidates])
    unresolved_mass = exp(unresolved_log_weight - maximum)
    particle_masses = tuple(
        exp(value - maximum) if isfinite(value) else 0.0 for value in log_weights
    )
    denominator = unresolved_mass + sum(particle_masses)
    if denominator <= 0.0 or not isfinite(denominator):
        raise ValueError("revision normalization has no finite probability mass")

    weights = tuple(
        NormalizedParticleWeight(
            proposal_id=receipt.proposal.proposal_id,
            particle_id=receipt.proposal.proposed_state.particle_id,
            posterior_probability=mass / denominator,
            accepted=receipt.accepted,
        )
        for receipt, mass in zip(receipts, particle_masses, strict=True)
    )
    return ParticleRevisionBatch(
        snapshot_id=next(iter(snapshot_ids)),
        evidence_cluster_id=next(iter(cluster_ids)),
        particle_weights=weights,
        unresolved_probability=unresolved_mass / denominator,
    )


class ReversibleCommitProtocol(ContractModel):
    """Frozen permission boundary between posterior revision and memory writes."""

    schema_version: Literal["0.1.0"]
    proposal_authority: Literal[ProposalAuthority.PROPOSE_AND_SCORE_ONLY]
    revision_authority: Literal[RevisionAuthority.NORMALIZE_CONSTRAIN_AND_REVISE_ONLY]
    commit_authority: Literal[CommitAuthority.REVERSIBLE_RGRC_LEDGER_ONLY]
    atomic_unit: Literal["evidence_cluster_statistic_bundle"]
    required_ledger_operations: tuple[
        Literal["quarantine", "promote", "retract", "corrected_revision"], ...
    ]
    requires_full_rerun_equivalence: Literal[True]
    requires_replay_fallback_on_numerical_failure: Literal[True]

    @model_validator(mode="after")
    def _freeze_commit_protocol(self) -> Self:
        if set(self.required_ledger_operations) != {
            "quarantine",
            "promote",
            "retract",
            "corrected_revision",
        }:
            raise ValueError("the reversible commit protocol requires all ledger operations")
        return self


def verify_stage_local_forgetting_runtime_binding() -> tuple[str, ...]:
    """Check that the runtime actually runs at the receipt's frozen value.

    Without this the receipt field is decorative: it appears in the selection
    contract and the JSON, and nothing downstream reads it.  This walks the
    runtime configuration defaults named in
    :data:`STAGE_LOCAL_FORGETTING_RUNTIME_BINDINGS` and fails loudly if any of
    them has drifted away from the frozen value.  It changes no value.
    """

    from inspect import signature

    from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig
    from cpswm.system.continual.rls.core import RLSConfig
    from cpswm.system.continual.rls.habit_head import RLSHabitScoreHead
    from cpswm.system.evaluation_operations.project_one_protocol import ProjectOneProtocolConfig

    observed: dict[str, float] = {
        "cpswm.system.continual.rls.core.RLSConfig.forgetting_factor": (
            RLSConfig(feature_dim=1).forgetting_factor
        ),
        "cpswm.system.continual.rls.habit_head.RLSHabitScoreHead.__init__.forgetting_factor": (
            float(signature(RLSHabitScoreHead.__init__).parameters["forgetting_factor"].default)
        ),
        "cpswm.system.continual.project_one_regime_loop.PrototypeLoopConfig.forgetting_factor": (
            PrototypeLoopConfig().forgetting_factor
        ),
        "cpswm.system.evaluation_operations.project_one_protocol."
        "ProjectOneProtocolConfig.forgetting_factor": (
            ProjectOneProtocolConfig().forgetting_factor
        ),
    }
    if set(observed) != set(STAGE_LOCAL_FORGETTING_RUNTIME_BINDINGS):
        raise ValueError("stage-local forgetting binding registry and probe disagree")
    drifted = tuple(
        f"{name}={value!r}"
        for name, value in sorted(observed.items())
        if value != FROZEN_STAGE_LOCAL_FORGETTING_FACTOR
    )
    if drifted:
        raise ValueError(
            "runtime stage-local forgetting drifted from the frozen receipt value "
            f"{FROZEN_STAGE_LOCAL_FORGETTING_FACTOR}: " + ", ".join(drifted)
        )
    return STAGE_LOCAL_FORGETTING_RUNTIME_BINDINGS


__all__ = [
    "FROZEN_STAGE_LOCAL_FORGETTING_FACTOR",
    "SELECTED_METHOD_ID",
    "STAGE_LOCAL_FORGETTING_RUNTIME_BINDINGS",
    "CommitAuthority",
    "MethodBackbone",
    "NeuralParticleProposal",
    "NormalizedParticleWeight",
    "OrderedActorRole",
    "ParticleChangeCause",
    "ParticleProposalOperation",
    "ParticleRegimeDecision",
    "ParticleRevisionBatch",
    "ParticleRevisionReceipt",
    "ParticleVariable",
    "ProposalAuthority",
    "RaoBlackwellizedBlock",
    "RetainedCapability",
    "ReversibleCommitProtocol",
    "RevisionAuthority",
    "StageLocalForgettingFactor",
    "StructureTwoOperator",
    "StructureTwoSelectedMethod",
    "StructuredConstraint",
    "StructuredWeightFactor",
    "TypedParticleState",
    "UnresolvedMethodBinding",
    "normalize_particle_revisions",
    "verify_stage_local_forgetting_runtime_binding",
]
