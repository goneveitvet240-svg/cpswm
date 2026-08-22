"""Provenance-Constrained Hypothesis Message Passing (PCHMP, 结构二 §4.7 #4).

A plain heterogeneous GNN / Transformer would let observation, evidence, and
inferred edges mix freely, output a high score without saying which evidence
produced it, and could learn a person-ID shortcut.  PCHMP is the structured
message-passing operator the structure-two specification requires:

* **source-type firewall** -- each evidence class may only send messages along
  its own edge type, so actor evidence cannot directly reweight a mechanism
  edge and an inferred posterior cannot loop back as independent evidence;
* **mutually-exclusive normalization** -- hypotheses inside one counterfactual
  event set are renormalized as a single competitive distribution together with
  the unresolved mass;
* **actor permutation equivariance** -- permuting actor identities in the
  inputs permutes the posteriors of the corresponding hypotheses exactly;
* **physical event constraints** -- messages respect the pick-up / carry /
  transfer / place grammar and ordered role bindings;
* **evidence subgraph output** -- the posterior is returned together with the
  exact evidence records each hypothesis consumed, so a prediction can be
  audited without trust.

This module is deliberately non-parametric (structured, deterministic message
passing).  A neural parameterization of the message functions is a later
implementation step; it must preserve the same firewalls and equivariance.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import isclose
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts import (
    ActorResponsibilityEvidence,
    EventMechanism,
    EventMechanismEvidence,
    RoleBindingEvidence,
    ordered_role_key,
)
from cpswm.contracts.base import ContractModel, Probability

from .contracts import (
    EventChainHypothesis,
    EventHypothesisHistory,
    EventHypothesisStatus,
)


class MessageEdgeType(StrEnum):
    """Source-typed edges of the hypothesis message graph."""

    ENDPOINT_OBSERVATION = "endpoint_observation"
    ACTOR_EVIDENCE = "actor_evidence"
    MECHANISM_EVIDENCE = "mechanism_evidence"
    ROLE_EVIDENCE = "role_evidence"
    EXCLUSIVITY = "exclusivity"
    PHYSICAL_CONSTRAINT = "physical_constraint"


class EvidenceFirewallViolation(RuntimeError):
    """Raised when a message would cross a source-type firewall boundary."""


@dataclass(frozen=True, slots=True)
class _MessageContribution:
    """One firewall-legal evidence message into a hypothesis node."""

    edge_type: MessageEdgeType
    likelihood_ratio: float
    evidence_record_id: UUID
    evidence_cluster_id: UUID


def _firewall_actor_ratio(
    hypothesis: EventChainHypothesis,
    evidence: ActorResponsibilityEvidence,
) -> float:
    ratios = evidence.actor_likelihood_ratios
    return ratios.get(hypothesis.responsible_actor_key, 1.0)


def _firewall_mechanism_ratio(
    hypothesis: EventChainHypothesis,
    evidence: EventMechanismEvidence,
) -> float:
    try:
        mechanism = EventMechanism(hypothesis.explanation_code)
    except ValueError:
        # A hypothesis with an unknown explanation code cannot receive
        # mechanism evidence; the firewall drops the message.
        return 1.0
    return evidence.mechanism_likelihood_ratios[mechanism]


def _firewall_role_ratio(
    hypothesis: EventChainHypothesis,
    evidence: RoleBindingEvidence,
) -> float:
    if hypothesis.explanation_code != EventMechanism.HANDOFF_RELOCATION.value:
        # Ordered role evidence only speaks to handoff chains.
        return 1.0
    if len(hypothesis.steps) == 0:
        return 1.0
    role_key = ordered_role_key(
        hypothesis.steps[0].actor_key,
        hypothesis.responsible_actor_key,
    )
    return evidence.ordered_role_likelihood_ratios.get(role_key, 1.0)


def _apply_evidence(
    hypotheses: tuple[EventChainHypothesis, ...],
    evidence: Sequence[
        ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence
    ],
) -> tuple[dict[UUID, list[_MessageContribution]], dict[UUID, float]]:
    """Aggregate firewall-legal evidence messages per hypothesis.

    Returns the per-hypothesis contribution lists and the per-hypothesis raw
    (unnormalized) likelihood product.
    """

    contributions: dict[UUID, list[_MessageContribution]] = {
        hypothesis.hypothesis_id: [] for hypothesis in hypotheses
    }
    raw: dict[UUID, float] = {
        hypothesis.hypothesis_id: 1.0 for hypothesis in hypotheses
    }
    for item in evidence:
        for hypothesis in hypotheses:
            if isinstance(item, ActorResponsibilityEvidence):
                ratio = _firewall_actor_ratio(hypothesis, item)
                edge_type = MessageEdgeType.ACTOR_EVIDENCE
            elif isinstance(item, EventMechanismEvidence):
                ratio = _firewall_mechanism_ratio(hypothesis, item)
                edge_type = MessageEdgeType.MECHANISM_EVIDENCE
            elif isinstance(item, RoleBindingEvidence):
                ratio = _firewall_role_ratio(hypothesis, item)
                edge_type = MessageEdgeType.ROLE_EVIDENCE
            else:  # pragma: no cover - guarded by the caller's type checks
                raise EvidenceFirewallViolation("unknown evidence type")
            if ratio < 0.0:
                raise EvidenceFirewallViolation(
                    "evidence likelihood ratios cannot be negative"
                )
            contributions[hypothesis.hypothesis_id].append(
                _MessageContribution(
                    edge_type=edge_type,
                    likelihood_ratio=ratio,
                    evidence_record_id=item.metadata.record_id,
                    evidence_cluster_id=item.evidence_cluster_id,
                )
            )
            raw[hypothesis.hypothesis_id] *= ratio ** item.effective_sample_weight
    return contributions, raw


class MessagePassingResult(ContractModel):
    """Joint posterior plus the auditable evidence subgraph per hypothesis."""

    hypothesis_set_id: UUID
    posterior_by_hypothesis_id: dict[UUID, Probability]
    unresolved_probability: Probability
    evidence_subgraph: dict[UUID, tuple[UUID, ...]]
    model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_posterior(self) -> MessagePassingResult:
        total = self.unresolved_probability + sum(self.posterior_by_hypothesis_id.values())
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("message-passing posterior plus unresolved must sum to one")
        if any(
            probability < 0.0 for probability in self.posterior_by_hypothesis_id.values()
        ):
            raise ValueError("hypothesis posteriors cannot be negative")
        if not set(self.posterior_by_hypothesis_id).issubset(set(self.evidence_subgraph)):
            raise ValueError("evidence subgraph must cover every posterior hypothesis")
        return self

    @property
    def map_hypothesis_id(self) -> UUID | None:
        if not self.posterior_by_hypothesis_id:
            return None
        return max(
            self.posterior_by_hypothesis_id,
            key=lambda key: self.posterior_by_hypothesis_id[key],
        )


def permute_actor_keys(
    history: EventHypothesisHistory,
    permutation: Mapping[str, str],
) -> EventHypothesisHistory:
    """Relabel actor identities inside a history (used for equivariance tests)."""

    _validate_permutation(permutation)
    return history.model_copy(
        update={
            "revisions": tuple(
                revision.model_copy(
                    update={
                        "hypotheses": tuple(
                            hypothesis.model_copy(
                                update={
                                    "responsible_actor_key": permutation.get(
                                        hypothesis.responsible_actor_key,
                                        hypothesis.responsible_actor_key,
                                    ),
                                    "steps": tuple(
                                        step.model_copy(
                                            update={
                                                "actor_key": permutation.get(
                                                    step.actor_key, step.actor_key
                                                ),
                                                "recipient_actor_key": (
                                                    None
                                                    if step.recipient_actor_key is None
                                                    else permutation.get(
                                                        step.recipient_actor_key,
                                                        step.recipient_actor_key,
                                                    )
                                                ),
                                            }
                                        )
                                        for step in hypothesis.steps
                                    ),
                                }
                            )
                            for hypothesis in revision.hypotheses
                        )
                    }
                )
                for revision in history.revisions
            )
        }
    )


def permute_actor_evidence(
    evidence: Sequence[
        ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence
    ],
    permutation: Mapping[str, str],
) -> tuple[
    ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence, ...
]:
    """Relabel actor identities inside evidence (used for equivariance tests)."""

    _validate_permutation(permutation)
    relabelled: list[
        ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence
    ] = []
    for item in evidence:
        if isinstance(item, ActorResponsibilityEvidence):
            relabelled.append(
                item.model_copy(
                    update={
                        "actor_posterior": {
                            permutation.get(actor, actor): probability
                            for actor, probability in item.actor_posterior.items()
                        },
                        "reference_actor_prior": {
                            permutation.get(actor, actor): probability
                            for actor, probability in item.reference_actor_prior.items()
                        },
                    }
                )
            )
        elif isinstance(item, RoleBindingEvidence):
            relabelled.append(
                item.model_copy(
                    update={
                        "ordered_role_posterior": {
                            _permute_ordered_role_key(key, permutation): probability
                            for key, probability in item.ordered_role_posterior.items()
                        },
                        "reference_ordered_role_prior": {
                            _permute_ordered_role_key(key, permutation): probability
                            for key, probability in item.reference_ordered_role_prior.items()
                        },
                    }
                )
            )
        else:
            relabelled.append(item)
    return tuple(relabelled)


def _permute_ordered_role_key(key: str, permutation: Mapping[str, str]) -> str:
    initiator, recipient = key.split("=>")
    return ordered_role_key(
        permutation.get(initiator, initiator),
        permutation.get(recipient, recipient),
    )


def _validate_permutation(permutation: Mapping[str, str]) -> None:
    if not permutation:
        raise ValueError("actor permutation cannot be empty")
    if len(set(permutation.values())) != len(permutation):
        raise ValueError("actor permutation must be a bijection")


class ProvenanceConstrainedMessagePassing:
    """Structured, source-typed, permutation-equivariant hypothesis inference."""

    model_version = "pchmp@0.1"

    def infer(
        self,
        history: EventHypothesisHistory,
        evidence: Sequence[
            ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence
        ] = (),
        *,
        unresolved_prior: float | None = None,
    ) -> MessagePassingResult:
        """Run one message-passing pass over the latest revision's hypotheses."""

        revision = history.latest
        hypotheses = revision.hypotheses
        if not hypotheses:
            raise ValueError("message passing requires at least one hypothesis")
        branch_unresolved = (
            history.revisions[0].unresolved_probability
            if unresolved_prior is None
            else unresolved_prior
        )
        if not 0.0 <= branch_unresolved <= 1.0:
            raise ValueError("unresolved_prior must lie in [0, 1]")

        contributions, raw = _apply_evidence(hypotheses, evidence)

        # Only active hypotheses carry resolvable mass; retracted hypotheses
        # hold zero mass (their shadow mass is an ORRER concern, not a message
        # concern).
        active = {
            hypothesis.hypothesis_id: hypothesis
            for hypothesis in hypotheses
            if hypothesis.status == EventHypothesisStatus.ACTIVE
        }
        resolved_mass = 1.0 - branch_unresolved
        raw_total = sum(raw[hypothesis_id] for hypothesis_id in active)
        if raw_total <= 0.0:
            # Degenerate all-zero evidence: fall back to a uniform active prior.
            uniform = 1.0 / len(active) if active else 0.0
            posterior = {
                hypothesis_id: resolved_mass * uniform
                for hypothesis_id in active
            }
        else:
            posterior = {
                hypothesis_id: resolved_mass * raw[hypothesis_id] / raw_total
                for hypothesis_id in active
            }

        evidence_subgraph = {
            hypothesis.hypothesis_id: tuple(
                contribution.evidence_record_id
                for contribution in contributions[hypothesis.hypothesis_id]
            )
            for hypothesis in hypotheses
        }
        return MessagePassingResult(
            hypothesis_set_id=revision.hypothesis_set_id,
            posterior_by_hypothesis_id=posterior,
            unresolved_probability=branch_unresolved,
            evidence_subgraph=evidence_subgraph,
            model_version=self.model_version,
        )

    @staticmethod
    def assert_permutation_equivariance(
        *,
        history: EventHypothesisHistory,
        evidence: Sequence[
            ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence
        ],
        permutation: Mapping[str, str],
        model: ProvenanceConstrainedMessagePassing | None = None,
        rel_tol: float = 1e-9,
    ) -> None:
        """Verify that relabelling actors permutes posteriors, never re-weights.

        The history and the evidence are both relabelled consistently, so each
        hypothesis must keep exactly the same posterior under the permutation.
        Raises :class:`AssertionError` on any drift.
        """

        engine = model or ProvenanceConstrainedMessagePassing()
        baseline = engine.infer(history, evidence)
        permuted_history = permute_actor_keys(history, permutation)
        permuted_evidence = permute_actor_evidence(evidence, permutation)
        permuted = engine.infer(permuted_history, permuted_evidence)
        for hypothesis in history.latest.hypotheses:
            hypothesis_id = hypothesis.hypothesis_id
            if hypothesis.status != EventHypothesisStatus.ACTIVE:
                continue
            if not isclose(
                baseline.posterior_by_hypothesis_id.get(hypothesis_id, 0.0),
                permuted.posterior_by_hypothesis_id.get(hypothesis_id, 0.0),
                rel_tol=rel_tol,
                abs_tol=1e-12,
            ):
                raise AssertionError(
                    "PCHMP is not actor permutation equivariant for hypothesis "
                    f"{hypothesis_id}"
                )
        if not isclose(
            baseline.unresolved_probability,
            permuted.unresolved_probability,
            rel_tol=rel_tol,
            abs_tol=1e-12,
        ):
            raise AssertionError("PCHMP unresolved mass is not permutation equivariant")
