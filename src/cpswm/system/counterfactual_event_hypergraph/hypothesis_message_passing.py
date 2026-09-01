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
from math import exp, isclose, log
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
from cpswm.system.attestation import AttestationAuthority, AttestationError, attested_payload
from cpswm.system.reproducibility import content_sha256, content_uuid

from .contracts import (
    DOMAIN_EVIDENCE_INDEPENDENCE,
    ActorEvidenceEndpointRole,
    EventChainHypothesis,
    EventHypothesisHistory,
    EventHypothesisRevision,
    EventHypothesisStatus,
    EventHypothesisUpdateKind,
    EvidenceIndependenceCertificate,
    hidden_event_evidence_claim_fingerprint,
    hidden_event_evidence_semantic_fingerprint,
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


class EvidenceScopeViolation(RuntimeError):
    """Raised when evidence does not bind the hypothesis set's scope."""


class EvidenceDuplicateViolation(RuntimeError):
    """Raised when an evidence record or cluster is consumed more than once."""


@dataclass(frozen=True, slots=True)
class _MessageContribution:
    """One firewall-legal evidence message into a hypothesis node."""

    edge_type: MessageEdgeType
    #: Log likelihood ratio ``log(posterior) - log(prior)`` (finite or -inf).
    log_likelihood_ratio: float
    effective_sample_weight: float
    evidence_record_id: UUID
    evidence_cluster_id: UUID
    #: ``None`` means the message was applied; a non-None string records why the
    #: firewall dropped it (its ratio was not folded into the posterior).
    firewall_drop_reason: str | None


class EvidenceMessage(ContractModel):
    """One auditable evidence message bound to a hypothesis or the unresolved
    node.

    An exact-zero likelihood ratio excludes the hypothesis outright; its log
    contribution is ``-inf``, which JSON cannot represent, so the audit records
    ``is_negative_infinity`` explicitly and keeps ``log_likelihood_ratio`` a
    finite float (``0.0``).
    """

    edge_type: MessageEdgeType
    #: ``log(posterior) - log(prior)`` (finite; exact-zero stores ``0.0``).
    log_likelihood_ratio: float
    effective_sample_weight: float = Field(gt=0.0)
    #: The actually-applied log contribution: ``weight * log_likelihood_ratio``
    #: (finite; exact-zero ratios set this to ``0.0`` and flag the -inf).
    applied_log_contribution: float
    #: True when the log likelihood ratio is ``-inf`` (an exact-zero posterior).
    is_negative_infinity: bool = False
    evidence_record_id: UUID
    evidence_cluster_id: UUID
    #: ``None`` means the message was applied; otherwise why the firewall
    #: dropped it (a neutral-but-legal message keeps ``None``).
    firewall_drop_reason: str | None = None

    @model_validator(mode="after")
    def validate_contribution(self) -> EvidenceMessage:
        if self.firewall_drop_reason is not None:
            if self.applied_log_contribution != 0.0:
                raise ValueError("a firewall-dropped message must contribute zero")
            if self.is_negative_infinity:
                raise ValueError("a firewall-dropped message cannot be negative infinity")
            return self
        if self.is_negative_infinity:
            if self.applied_log_contribution != 0.0:
                raise ValueError("an exact-zero ratio records applied_log_contribution == 0")
            return self
        expected = self.effective_sample_weight * self.log_likelihood_ratio
        if not isclose(
            self.applied_log_contribution,
            expected,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError("applied_log_contribution must equal weight * log_likelihood_ratio")
        return self


def _firewall_actor_ratio(
    hypothesis: EventChainHypothesis,
    evidence: ActorResponsibilityEvidence,
) -> tuple[float, str | None]:
    ratios = evidence.log_actor_likelihood_ratios
    if hypothesis.responsible_actor_key in ratios:
        return ratios[hypothesis.responsible_actor_key], None
    # The hypothesis's actor is out of the evidence's support: a legal neutral
    # message, not a firewall drop.
    return 0.0, None


def _firewall_mechanism_ratio(
    hypothesis: EventChainHypothesis,
    evidence: EventMechanismEvidence,
) -> tuple[float, str | None]:
    try:
        mechanism = EventMechanism(hypothesis.explanation_code)
    except ValueError:
        # A hypothesis with an unknown explanation code cannot receive
        # mechanism evidence; the firewall drops the message.
        return 0.0, "unknown_explanation_code"
    return evidence.log_mechanism_likelihood_ratios[mechanism], None


def _firewall_role_ratio(
    hypothesis: EventChainHypothesis,
    evidence: RoleBindingEvidence,
) -> tuple[float, str | None]:
    if hypothesis.explanation_code != EventMechanism.HANDOFF_RELOCATION.value:
        # Ordered role evidence only speaks to handoff chains.
        return 0.0, "role_evidence_not_applicable_to_direct"
    if len(hypothesis.steps) == 0:
        return 0.0, "empty_hypothesis_chain"
    role_key = ordered_role_key(
        hypothesis.steps[0].actor_key,
        hypothesis.responsible_actor_key,
    )
    return evidence.log_ordered_role_likelihood_ratios.get(role_key, 0.0), None


def _unresolved_log_ratio(
    evidence: ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence,
) -> float:
    """Log likelihood the evidence assigns to an unresolved / out-of-support
    cause.

    Actor evidence carries an explicit unknown-actor channel; mechanism and role
    evidence carry no unknown channel and therefore leave unresolved mass at a
    neutral (zero-log) ratio.
    """

    if isinstance(evidence, ActorResponsibilityEvidence):
        return evidence.log_actor_likelihood_ratios.get("unknown_actor", 0.0)
    return 0.0


def _apply_evidence(
    hypotheses: tuple[EventChainHypothesis, ...],
    revision: EventHypothesisRevision,
    consumed_record_ids: frozenset[UUID],
    consumed_cluster_ids: frozenset[UUID],
    consumed_semantic_fingerprints: frozenset[str],
    consumed_fingerprint_pairs: Sequence[tuple[str, str]],
    evidence: Sequence[ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence],
    independence_certificates: Sequence[EvidenceIndependenceCertificate],
    independence_authority: AttestationAuthority | None,
) -> tuple[
    dict[UUID, list[_MessageContribution]],
    dict[UUID, float],
    float,
    list[_MessageContribution],
    float,
    list[_MessageContribution],
    tuple[str, ...],
]:
    """Aggregate firewall-legal evidence messages with scope and dedup checks.

    Deduplication is against both the current call and the history's already
    consumed evidence records/clusters, so an evidence record consumed by an
    earlier ORRER revision is rejected instead of being applied twice.

    Returns the per-hypothesis contributions, the per-hypothesis log likelihood
    (sum of ``weight * log(ratio)``, ``-inf`` for an exact-zero ratio), the
    unresolved log likelihood, and the unresolved-node messages.  Log space
    keeps every accumulation finite-safe: extreme ratios and exact zeros never
    overflow the posterior normalization.
    """

    contributions: dict[UUID, list[_MessageContribution]] = {
        hypothesis.hypothesis_id: [] for hypothesis in hypotheses
    }
    log_raw: dict[UUID, float] = {hypothesis.hypothesis_id: 0.0 for hypothesis in hypotheses}
    log_unresolved_raw = 0.0
    unresolved_messages: list[_MessageContribution] = []
    log_unknown_mechanism_raw = 0.0
    unknown_mechanism_messages: list[_MessageContribution] = []
    seen_record_ids: set[UUID] = set(consumed_record_ids)
    seen_cluster_ids: set[UUID] = set(consumed_cluster_ids)
    seen_semantic_fingerprints: set[str] = set(consumed_semantic_fingerprints)
    semantics_by_claim: dict[str, set[str]] = {}
    for claim_fingerprint, semantic_fingerprint in consumed_fingerprint_pairs:
        semantics_by_claim.setdefault(claim_fingerprint, set()).add(semantic_fingerprint)

    certificates_by_pair = {
        certificate.semantic_fingerprints: certificate for certificate in independence_certificates
    }
    used_independence_certificate_sha256s: set[str] = set()

    for item in evidence:
        _validate_evidence_scope(revision, item)
        if item.metadata.record_id in seen_record_ids:
            raise EvidenceDuplicateViolation(
                f"evidence record {item.metadata.record_id} consumed twice"
            )
        if item.evidence_cluster_id in seen_cluster_ids:
            raise EvidenceDuplicateViolation(
                f"evidence cluster {item.evidence_cluster_id} consumed twice"
            )
        semantic_fingerprint = hidden_event_evidence_semantic_fingerprint(item)
        if semantic_fingerprint in seen_semantic_fingerprints:
            raise EvidenceDuplicateViolation(
                "semantically identical evidence was repackaged with a new record or cluster ID"
            )
        claim_fingerprint = hidden_event_evidence_claim_fingerprint(item)
        for prior_semantic_fingerprint in semantics_by_claim.get(claim_fingerprint, set()):
            semantic_pair = (
                (prior_semantic_fingerprint, semantic_fingerprint)
                if prior_semantic_fingerprint < semantic_fingerprint
                else (semantic_fingerprint, prior_semantic_fingerprint)
            )
            certificate = certificates_by_pair.get(semantic_pair)
            if certificate is None or independence_authority is None:
                raise EvidenceDuplicateViolation(
                    "same-claim evidence requires an explicit authority-attested "
                    "independence certificate before it can be counted twice"
                )
            try:
                independence_authority.verify(
                    DOMAIN_EVIDENCE_INDEPENDENCE,
                    attested_payload(certificate),
                    certificate.attestation,
                )
            except AttestationError as error:
                raise EvidenceDuplicateViolation(
                    "same-claim evidence independence certificate is invalid"
                ) from error
            used_independence_certificate_sha256s.add(content_sha256(certificate))
        seen_record_ids.add(item.metadata.record_id)
        seen_cluster_ids.add(item.evidence_cluster_id)
        seen_semantic_fingerprints.add(semantic_fingerprint)
        semantics_by_claim.setdefault(claim_fingerprint, set()).add(semantic_fingerprint)

        unresolved_log_ratio = _unresolved_log_ratio(item)
        log_unresolved_raw += item.effective_sample_weight * unresolved_log_ratio
        unresolved_messages.append(
            _MessageContribution(
                edge_type=MessageEdgeType.ACTOR_EVIDENCE
                if isinstance(item, ActorResponsibilityEvidence)
                else MessageEdgeType.MECHANISM_EVIDENCE
                if isinstance(item, EventMechanismEvidence)
                else MessageEdgeType.ROLE_EVIDENCE,
                log_likelihood_ratio=unresolved_log_ratio,
                effective_sample_weight=item.effective_sample_weight,
                evidence_record_id=item.metadata.record_id,
                evidence_cluster_id=item.evidence_cluster_id,
                firewall_drop_reason=None,
            )
        )
        unknown_mechanism_log_ratio = (
            item.log_mechanism_likelihood_ratios[EventMechanism.UNKNOWN_MECHANISM]
            if isinstance(item, EventMechanismEvidence)
            else 0.0
        )
        log_unknown_mechanism_raw += item.effective_sample_weight * unknown_mechanism_log_ratio
        unknown_mechanism_messages.append(
            _MessageContribution(
                edge_type=(
                    MessageEdgeType.MECHANISM_EVIDENCE
                    if isinstance(item, EventMechanismEvidence)
                    else MessageEdgeType.ACTOR_EVIDENCE
                    if isinstance(item, ActorResponsibilityEvidence)
                    else MessageEdgeType.ROLE_EVIDENCE
                ),
                log_likelihood_ratio=unknown_mechanism_log_ratio,
                effective_sample_weight=item.effective_sample_weight,
                evidence_record_id=item.metadata.record_id,
                evidence_cluster_id=item.evidence_cluster_id,
                firewall_drop_reason=None,
            )
        )

        for hypothesis in hypotheses:
            if isinstance(item, ActorResponsibilityEvidence):
                log_ratio, drop_reason = _firewall_actor_ratio(hypothesis, item)
                edge_type = MessageEdgeType.ACTOR_EVIDENCE
            elif isinstance(item, EventMechanismEvidence):
                log_ratio, drop_reason = _firewall_mechanism_ratio(hypothesis, item)
                edge_type = MessageEdgeType.MECHANISM_EVIDENCE
            elif isinstance(item, RoleBindingEvidence):
                log_ratio, drop_reason = _firewall_role_ratio(hypothesis, item)
                edge_type = MessageEdgeType.ROLE_EVIDENCE
            else:  # pragma: no cover - guarded by the caller's type checks
                raise EvidenceFirewallViolation("unknown evidence type")
            if log_ratio == float("inf") or log_ratio != log_ratio:
                raise EvidenceFirewallViolation(
                    "log evidence likelihood ratios must be finite or -inf"
                )
            contributions[hypothesis.hypothesis_id].append(
                _MessageContribution(
                    edge_type=edge_type,
                    log_likelihood_ratio=log_ratio,
                    effective_sample_weight=item.effective_sample_weight,
                    evidence_record_id=item.metadata.record_id,
                    evidence_cluster_id=item.evidence_cluster_id,
                    firewall_drop_reason=drop_reason,
                )
            )
            if drop_reason is None:
                log_raw[hypothesis.hypothesis_id] += item.effective_sample_weight * log_ratio
    return (
        contributions,
        log_raw,
        log_unresolved_raw,
        unresolved_messages,
        log_unknown_mechanism_raw,
        unknown_mechanism_messages,
        tuple(sorted(used_independence_certificate_sha256s)),
    )


def _safe_log(value: float) -> float:
    """Log of a likelihood ratio, safe at the zero boundary."""

    if value <= 0.0:
        return float("-inf")
    return float(log(value))


def _logsumexp(values: Sequence[float]) -> float:
    """Numerically stable log-sum-exp; ``-inf`` entries contribute nothing."""

    finite = [value for value in values if value != float("-inf")]
    if not finite:
        return float("-inf")
    peak = max(finite)
    total = sum(exp(value - peak) for value in finite)
    return peak + float(log(total))


def _message_log_contribution(
    contribution: _MessageContribution,
) -> tuple[float, bool]:
    """The finite ``(applied_log_contribution, is_negative_infinity)`` audit pair.

    Firewall-dropped messages contribute zero; an exact-zero ratio contributes
    ``-inf``, represented as ``(0.0, True)``.
    """

    if contribution.firewall_drop_reason is not None:
        return 0.0, False
    if contribution.log_likelihood_ratio == float("-inf"):
        return 0.0, True
    applied = contribution.effective_sample_weight * contribution.log_likelihood_ratio
    return applied, False


def _validate_evidence_scope(
    revision: EventHypothesisRevision,
    evidence: ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence,
) -> None:
    """Reject evidence outside the hypothesis set's object / endpoint / scope."""

    if evidence.object_instance_id != revision.object_instance_id:
        raise EvidenceScopeViolation(
            "evidence object_instance_id does not match the hypothesis set"
        )
    destination_endpoint_id = revision.source_detection_result_ids[1]
    if evidence.source_detection_result_id != destination_endpoint_id:
        raise EvidenceScopeViolation("evidence must cite the hypothesis set's destination endpoint")
    for field_name in ("household_id", "session_id", "trace_id"):
        if getattr(evidence.metadata, field_name) != getattr(revision, field_name):
            raise EvidenceScopeViolation(f"evidence {field_name} does not match the hypothesis set")


class MessagePassingResult(ContractModel):
    """Joint posterior plus the auditable evidence subgraph per hypothesis."""

    hypothesis_set_id: UUID
    posterior_by_hypothesis_id: dict[UUID, Probability]
    unresolved_probability: Probability
    unknown_mechanism_probability: Probability = 0.0
    unknown_mechanism_actor_posterior: dict[str, Probability] = Field(default_factory=dict)
    evidence_subgraph: dict[UUID, tuple[EvidenceMessage, ...]]
    unresolved_evidence_messages: tuple[EvidenceMessage, ...] = ()
    unknown_mechanism_evidence_messages: tuple[EvidenceMessage, ...] = ()
    #: Consumption receipt: the evidence records/clusters this pass consumed.
    consumed_evidence_record_ids: tuple[UUID, ...] = ()
    consumed_evidence_cluster_ids: tuple[UUID, ...] = ()
    consumed_evidence_semantic_fingerprints: tuple[str, ...] = ()
    consumed_evidence_claim_fingerprints: tuple[str, ...] = ()
    consumed_independence_certificate_sha256s: tuple[str, ...] = ()
    model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_posterior(self) -> MessagePassingResult:
        total = (
            self.unresolved_probability
            + self.unknown_mechanism_probability
            + sum(self.posterior_by_hypothesis_id.values())
        )
        if not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("message-passing posterior plus unresolved must sum to one")
        if self.unknown_mechanism_probability > 0.0 and not isclose(
            sum(self.unknown_mechanism_actor_posterior.values()),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("unknown-mechanism actor posterior must sum to one")
        if any(probability < 0.0 for probability in self.posterior_by_hypothesis_id.values()):
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


class LeaveOneClusterOutImpact(ContractModel):
    """Posterior sensitivity when one evidence cluster is withheld."""

    evidence_cluster_id: UUID
    omitted_evidence_record_ids: tuple[UUID, ...] = Field(min_length=1)
    posterior_total_variation: float = Field(ge=0.0, le=1.0)
    map_hypothesis_changed: bool
    unresolved_probability_delta: float
    unknown_mechanism_probability_delta: float


class LeaveOneClusterOutAudit(ContractModel):
    """Leave-one-cluster-out audit for correlated-evidence dependence."""

    full_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    impacts: tuple[LeaveOneClusterOutImpact, ...] = Field(min_length=1)
    influence_threshold: float = Field(gt=0.0, le=1.0)
    maximum_total_variation: float = Field(ge=0.0, le=1.0)
    influential_cluster_ids: tuple[UUID, ...]

    @property
    def stable(self) -> bool:
        return not self.influential_cluster_ids


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
    evidence: Sequence[ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence],
    permutation: Mapping[str, str],
) -> tuple[ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence, ...]:
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
    if set(permutation.values()) != set(permutation.keys()):
        raise ValueError(
            "actor permutation must permute the same actor universe "
            "(keys and values must cover the same set of actors)"
        )


def _history_actor_universe(history: EventHypothesisHistory) -> frozenset[str]:
    """The named (non-unknown) actor identities present in a history."""

    actors: set[str] = set()
    for revision in history.revisions:
        for hypothesis in revision.hypotheses:
            actors.add(hypothesis.responsible_actor_key)
            for step in hypothesis.steps:
                actors.add(step.actor_key)
                if step.recipient_actor_key is not None:
                    actors.add(step.recipient_actor_key)
    return frozenset(actor for actor in actors if actor != "unknown_actor")


class ProvenanceConstrainedMessagePassing:
    """Structured, source-typed, permutation-equivariant hypothesis inference."""

    model_version = "pchmp@0.1"

    def __init__(
        self,
        *,
        independence_authority: AttestationAuthority | None = None,
    ) -> None:
        self._independence_authority = independence_authority

    def infer(
        self,
        history: EventHypothesisHistory,
        evidence: Sequence[
            ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence
        ] = (),
        *,
        independence_certificates: Sequence[EvidenceIndependenceCertificate] = (),
    ) -> MessagePassingResult:
        """Run one message-passing pass over the latest revision's hypotheses.

        Semantics: ``history.latest`` supplies the prior (the ORRER posterior,
        including its unresolved mass), and ``evidence`` is the *incremental*
        evidence not yet consumed by the history.  With no evidence the prior
        is returned unchanged; with evidence the prior is reweighted by the
        firewall-legal likelihood ratios and renormalized competitively with
        the unresolved node.  Evidence records or clusters already consumed by
        the history are rejected (single consumption across revisions).
        """

        revision = history.latest
        hypotheses = revision.hypotheses
        if not hypotheses:
            raise ValueError("message passing requires at least one hypothesis")

        (
            contributions,
            log_evidence,
            log_unresolved,
            unresolved_messages,
            log_unknown_mechanism,
            unknown_mechanism_messages,
            used_independence_certificate_sha256s,
        ) = _apply_evidence(
            hypotheses,
            revision,
            history.consumed_evidence_record_ids,
            history.consumed_evidence_cluster_ids,
            history.consumed_evidence_semantic_fingerprints,
            history.consumed_evidence_fingerprint_pairs,
            evidence,
            independence_certificates,
            self._independence_authority,
        )

        # Prior: the ORRER posterior over active hypotheses plus its unresolved
        # mass.  Retracted hypotheses hold zero mass.
        active = {
            hypothesis.hypothesis_id: hypothesis
            for hypothesis in hypotheses
            if hypothesis.status == EventHypothesisStatus.ACTIVE
        }
        prior_by_hypothesis = {
            hypothesis_id: hypothesis.posterior_probability
            for hypothesis_id, hypothesis in active.items()
        }
        unresolved_prior = revision.unresolved_probability
        unknown_mechanism_prior = revision.unknown_mechanism_probability
        unknown_mechanism_actor_raw = dict(revision.unknown_mechanism_actor_posterior)
        for item in evidence:
            if not isinstance(item, ActorResponsibilityEvidence) or not any(
                reference.evidence_type == "actor_discrimination"
                for reference in item.evidence_refs
            ):
                continue
            ratios = item.actor_likelihood_ratios
            unknown_mechanism_actor_raw = {
                actor: probability * ratios.get(actor, 1.0) ** item.effective_sample_weight
                for actor, probability in unknown_mechanism_actor_raw.items()
            }
        unknown_actor_total = sum(unknown_mechanism_actor_raw.values())
        unknown_mechanism_actor_posterior = (
            dict(revision.unknown_mechanism_actor_posterior)
            if unknown_actor_total <= 0.0
            else {
                actor: value / unknown_actor_total
                for actor, value in unknown_mechanism_actor_raw.items()
            }
        )

        # Unnormalized posterior in log space: log(prior) + log evidence.
        log_posterior = {
            hypothesis_id: _safe_log(prior_by_hypothesis[hypothesis_id])
            + log_evidence[hypothesis_id]
            for hypothesis_id in active
        }
        log_unresolved_posterior = _safe_log(unresolved_prior) + log_unresolved
        log_unknown_mechanism_posterior = _safe_log(unknown_mechanism_prior) + log_unknown_mechanism
        log_total = _logsumexp(
            [
                *log_posterior.values(),
                log_unresolved_posterior,
                log_unknown_mechanism_posterior,
            ]
        )
        if log_total == float("-inf"):
            # Degenerate all-zero likelihood: keep the prior distribution.
            posterior = dict(prior_by_hypothesis)
            unresolved_probability = unresolved_prior
            unknown_mechanism_probability = unknown_mechanism_prior
        else:
            posterior = {
                hypothesis_id: float(exp(log_mass - log_total))
                for hypothesis_id, log_mass in log_posterior.items()
            }
            unresolved_probability = float(exp(log_unresolved_posterior - log_total))
            unknown_mechanism_probability = float(exp(log_unknown_mechanism_posterior - log_total))

        evidence_subgraph = {
            hypothesis.hypothesis_id: tuple(
                self._to_evidence_message(contribution)
                for contribution in contributions[hypothesis.hypothesis_id]
            )
            for hypothesis in hypotheses
        }
        unresolved_evidence = tuple(
            self._to_evidence_message(contribution) for contribution in unresolved_messages
        )
        unknown_mechanism_evidence = tuple(
            self._to_evidence_message(contribution) for contribution in unknown_mechanism_messages
        )
        return MessagePassingResult(
            hypothesis_set_id=revision.hypothesis_set_id,
            posterior_by_hypothesis_id=posterior,
            unresolved_probability=unresolved_probability,
            unknown_mechanism_probability=unknown_mechanism_probability,
            unknown_mechanism_actor_posterior=unknown_mechanism_actor_posterior,
            evidence_subgraph=evidence_subgraph,
            unresolved_evidence_messages=unresolved_evidence,
            unknown_mechanism_evidence_messages=unknown_mechanism_evidence,
            consumed_evidence_record_ids=tuple(item.metadata.record_id for item in evidence),
            consumed_evidence_cluster_ids=tuple(item.evidence_cluster_id for item in evidence),
            consumed_evidence_semantic_fingerprints=tuple(
                hidden_event_evidence_semantic_fingerprint(item) for item in evidence
            ),
            consumed_evidence_claim_fingerprints=tuple(
                hidden_event_evidence_claim_fingerprint(item) for item in evidence
            ),
            consumed_independence_certificate_sha256s=(used_independence_certificate_sha256s),
            model_version=self.model_version,
        )

    def audit_leave_one_cluster_out(
        self,
        history: EventHypothesisHistory,
        evidence: Sequence[
            ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence
        ],
        *,
        influence_threshold: float = 0.25,
        independence_certificates: Sequence[EvidenceIndependenceCertificate] = (),
    ) -> LeaveOneClusterOutAudit:
        """Measure whether one correlated evidence cluster dominates the posterior.

        This is a diagnostic, not another posterior update.  Every cluster is
        removed in turn and the resulting joint distribution is compared with
        the full-evidence result by total variation distance.
        """

        if not 0.0 < influence_threshold <= 1.0:
            raise ValueError("influence_threshold must lie in (0, 1]")
        if not evidence:
            raise ValueError("leave-one-cluster-out requires evidence")
        full = self.infer(
            history,
            evidence,
            independence_certificates=independence_certificates,
        )
        clusters = tuple(dict.fromkeys(item.evidence_cluster_id for item in evidence))
        impacts: list[LeaveOneClusterOutImpact] = []
        for cluster_id in clusters:
            retained = tuple(item for item in evidence if item.evidence_cluster_id != cluster_id)
            omitted = tuple(
                item.metadata.record_id
                for item in evidence
                if item.evidence_cluster_id == cluster_id
            )
            without = self.infer(
                history,
                retained,
                independence_certificates=independence_certificates,
            )
            support = set(full.posterior_by_hypothesis_id) | set(without.posterior_by_hypothesis_id)
            total_variation = 0.5 * (
                sum(
                    abs(
                        full.posterior_by_hypothesis_id.get(hypothesis_id, 0.0)
                        - without.posterior_by_hypothesis_id.get(hypothesis_id, 0.0)
                    )
                    for hypothesis_id in support
                )
                + abs(full.unresolved_probability - without.unresolved_probability)
                + abs(full.unknown_mechanism_probability - without.unknown_mechanism_probability)
            )
            impacts.append(
                LeaveOneClusterOutImpact(
                    evidence_cluster_id=cluster_id,
                    omitted_evidence_record_ids=omitted,
                    posterior_total_variation=total_variation,
                    map_hypothesis_changed=(full.map_hypothesis_id != without.map_hypothesis_id),
                    unresolved_probability_delta=(
                        without.unresolved_probability - full.unresolved_probability
                    ),
                    unknown_mechanism_probability_delta=(
                        without.unknown_mechanism_probability - full.unknown_mechanism_probability
                    ),
                )
            )
        maximum = max(item.posterior_total_variation for item in impacts)
        return LeaveOneClusterOutAudit(
            full_result_sha256=content_sha256(full),
            impacts=tuple(impacts),
            influence_threshold=influence_threshold,
            maximum_total_variation=maximum,
            influential_cluster_ids=tuple(
                item.evidence_cluster_id
                for item in impacts
                if item.posterior_total_variation >= influence_threshold
            ),
        )

    def consume(
        self,
        history: EventHypothesisHistory,
        evidence: Sequence[
            ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence
        ] = (),
        *,
        independence_certificates: Sequence[EvidenceIndependenceCertificate] = (),
    ) -> tuple[MessagePassingResult, EventHypothesisHistory]:
        """Run one pass and write the consumption receipt back into history.

        The returned history appends a revision whose evidence records/clusters
        are the ones this pass consumed, so a second pass over the same
        (un-receipted) history raises :class:`EvidenceDuplicateViolation` and a
        second pass over the *returned* history cannot re-consume the same
        evidence: exactly-once at the authoritative-history level.
        """

        result = self.infer(
            history,
            evidence,
            independence_certificates=independence_certificates,
        )
        receipted = self._record_consumption(history, evidence, result)
        return result, receipted

    @staticmethod
    def _record_consumption(
        history: EventHypothesisHistory,
        evidence: Sequence[
            ActorResponsibilityEvidence | EventMechanismEvidence | RoleBindingEvidence
        ],
        result: MessagePassingResult,
    ) -> EventHypothesisHistory:
        """Append a consumption-receipt revision carrying the PCHMP posterior."""

        if not evidence:
            return history
        current = history.latest
        record_ids = tuple(item.metadata.record_id for item in evidence)
        cluster_ids = tuple(item.evidence_cluster_id for item in evidence)
        fingerprints = tuple(hidden_event_evidence_semantic_fingerprint(item) for item in evidence)
        claim_fingerprints = tuple(
            hidden_event_evidence_claim_fingerprint(item) for item in evidence
        )
        source_detection_ids = tuple(item.source_detection_result_id for item in evidence)
        endpoint_roles = tuple(ActorEvidenceEndpointRole.DESTINATION_STATE for _ in evidence)
        revised_hypotheses = tuple(
            item.model_copy(
                update={
                    "posterior_probability": result.posterior_by_hypothesis_id.get(
                        item.hypothesis_id, 0.0
                    ),
                    "source_record_ids": (*item.source_record_ids, *record_ids),
                    "status": (
                        EventHypothesisStatus.ACTIVE
                        if result.posterior_by_hypothesis_id.get(item.hypothesis_id, 0.0) > 0.0
                        else EventHypothesisStatus.RETRACTED
                    ),
                }
            )
            for item in current.hypotheses
        )
        revision_reason = "PCHMP message-passing evidence consumption receipt"
        payload = {
            "hypothesis_set_id": current.hypothesis_set_id,
            "revision_no": current.revision_no + 1,
            "parent_revision_id": current.revision_id,
            "update_kind": EventHypothesisUpdateKind.REVISE,
            "household_id": current.household_id,
            "session_id": current.session_id,
            "trace_id": current.trace_id,
            "object_instance_id": current.object_instance_id,
            "interval_start": current.interval_start,
            "interval_end": current.interval_end,
            "source_location_id": current.source_location_id,
            "destination_location_id": current.destination_location_id,
            "source_detection_result_ids": current.source_detection_result_ids,
            "hypotheses": revised_hypotheses,
            "unknown_mechanism_probability": result.unknown_mechanism_probability,
            "unknown_mechanism_actor_posterior": result.unknown_mechanism_actor_posterior,
            "unresolved_probability": result.unresolved_probability,
            "revision_evidence_record_ids": record_ids,
            "revision_evidence_cluster_ids": cluster_ids,
            "revision_evidence_semantic_fingerprints": fingerprints,
            "revision_evidence_claim_fingerprints": claim_fingerprints,
            "revision_evidence_independence_certificate_sha256s": (
                result.consumed_independence_certificate_sha256s
            ),
            "revision_evidence_source_detection_result_ids": source_detection_ids,
            "revision_evidence_endpoint_roles": endpoint_roles,
            "revision_reason": revision_reason,
            "engine_version": current.engine_version,
        }
        revision = EventHypothesisRevision(
            hypothesis_set_id=current.hypothesis_set_id,
            revision_id=content_uuid("cheh-revision", payload),
            revision_content_sha256=content_sha256(payload),
            revision_no=current.revision_no + 1,
            parent_revision_id=current.revision_id,
            update_kind=EventHypothesisUpdateKind.REVISE,
            household_id=current.household_id,
            session_id=current.session_id,
            trace_id=current.trace_id,
            object_instance_id=current.object_instance_id,
            interval_start=current.interval_start,
            interval_end=current.interval_end,
            source_location_id=current.source_location_id,
            destination_location_id=current.destination_location_id,
            source_detection_result_ids=current.source_detection_result_ids,
            hypotheses=revised_hypotheses,
            unknown_mechanism_probability=result.unknown_mechanism_probability,
            unknown_mechanism_actor_posterior=result.unknown_mechanism_actor_posterior,
            unresolved_probability=result.unresolved_probability,
            revision_evidence_record_ids=record_ids,
            revision_evidence_cluster_ids=cluster_ids,
            revision_evidence_semantic_fingerprints=fingerprints,
            revision_evidence_claim_fingerprints=claim_fingerprints,
            revision_evidence_independence_certificate_sha256s=(
                result.consumed_independence_certificate_sha256s
            ),
            revision_evidence_source_detection_result_ids=source_detection_ids,
            revision_evidence_endpoint_roles=endpoint_roles,
            revision_reason=revision_reason,
            engine_version=current.engine_version,
        )
        return history.append(revision)

    @staticmethod
    def _to_evidence_message(contribution: _MessageContribution) -> EvidenceMessage:
        applied_log, is_negative_infinity = _message_log_contribution(contribution)
        return EvidenceMessage(
            edge_type=contribution.edge_type,
            log_likelihood_ratio=(
                0.0
                if contribution.log_likelihood_ratio == float("-inf")
                else contribution.log_likelihood_ratio
            ),
            effective_sample_weight=contribution.effective_sample_weight,
            applied_log_contribution=applied_log,
            is_negative_infinity=is_negative_infinity,
            evidence_record_id=contribution.evidence_record_id,
            evidence_cluster_id=contribution.evidence_cluster_id,
            firewall_drop_reason=contribution.firewall_drop_reason,
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
        The permutation must be a non-trivial bijection over the history's own
        actor universe (otherwise the check would be vacuous).  Raises
        :class:`AssertionError` on any drift.
        """

        engine = model or ProvenanceConstrainedMessagePassing()
        universe = _history_actor_universe(history)
        if not universe:
            raise AssertionError("history has no named actor universe to permute")
        if set(permutation.keys()) != set(universe):
            raise AssertionError(
                "permutation must cover exactly the history's actor universe "
                f"(got {sorted(permutation)}, expected {sorted(universe)})"
            )
        if any(actor == permutation[actor] for actor in universe):
            raise AssertionError("permutation must be non-trivial (no actor may map to itself)")
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
                    f"PCHMP is not actor permutation equivariant for hypothesis {hypothesis_id}"
                )
        if not isclose(
            baseline.unresolved_probability,
            permuted.unresolved_probability,
            rel_tol=rel_tol,
            abs_tol=1e-12,
        ):
            raise AssertionError("PCHMP unresolved mass is not permutation equivariant")
