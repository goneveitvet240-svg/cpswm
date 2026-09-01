"""RQ8: a robot-visible actor channel, so hard actor truth stops being a model input.

`项目结构一 §7` states the rule this module enforces:

    模型需要结合人物在场, 轨迹, 交互, 物体归属, 活动和历史习惯, 维护行为者后验,
    而不是把最高概率人物写成事实.

`ProjectOneDatasetRecord.actor_id` violates that rule.  It records *who really
moved the object*, and :class:`CoreHabitChainMethod` reads it directly::

    owner_mass = (
        event.observation_quality
        if event.actor_id == self.owner_id
        else 1.0 - event.observation_quality
    )

That single comparison hands the arm an evaluator-grade answer to RQ8 for free.
It also makes the D0 finding unreadable: the benchmark's own conclusion is that
*without person evidence a guest change and an owner-habit change are
observationally equivalent* (``actor -> owner leakage = 1.0``).  An arm that
reads ``actor_id`` is never in that regime, so it cannot be compared with a
baseline that is.

The fix follows the structure already used for
:class:`ActorResponsibilityEvidence` in :mod:`cpswm.contracts.habit_learning`
and for the D0 actor tracks: truth is converted, **by the evaluator**, into a
declared robot-visible posterior, and the method sees only that posterior.

Four policies, and the reason each exists:

``LEGACY_HARD_ACTOR``
    The frozen v0.3 boundary.  Kept, and kept as the default, so every number
    in ``docs/experiments/project_one_multi_seed_v0_3.md`` still reproduces
    byte-for-byte.  This is the same move ``LEGACY_SIGMOID`` made for the
    calibration fix: a repair that silently changes historical readings is not
    auditable.
``ABSENT``
    No actor channel at all.  This is the *honest* D0 regime, and the one the
    location baselines are already in.
``CONTROLLED_NOISE``
    A noisy posterior that must retain uncertainty.  This is the deployable
    setting: an identity estimate, not an identity.
``ORACLE``
    A one-hot posterior over the true actor.  Declared as an upper bound.  It
    is *not* the same thing as ``LEGACY_HARD_ACTOR``: oracle evidence flows
    through the same channel every other policy uses, is recorded in the
    config payload, and is therefore visible in any result that used it.

The channel never exposes the true actor id.  Masking is structural: under any
policy other than ``LEGACY_HARD_ACTOR`` the base method replaces
``event.actor_id`` with :data:`MASKED_ACTOR` before ``_predict``/``_step`` run,
so an arm cannot read it even by accident.

:func:`audit_actor_truth_isolation` is the death test for this module.  It
replays a stream twice — once as given, once with the actor labels permuted and
the actor channel held fixed — and reports whether the predictions moved.  If
they moved, the arm read hard actor truth.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from math import isclose, isfinite
from typing import Any

from cpswm.system.reproducibility import content_sha256

from .project_one_dataset import ProjectOneDatasetRecord

__all__ = [
    "ACTOR_CHANNEL_VERSION",
    "MASKED_ACTOR",
    "UNKNOWN_ACTOR",
    "ActorEvidencePolicy",
    "ActorTruthIsolationReport",
    "ProjectOneActorChannel",
    "ProjectOneActorEvidence",
    "ProjectOneActorEvidenceProjector",
    "audit_actor_truth_isolation",
    "permute_actor_labels",
]

ACTOR_CHANNEL_VERSION = "project-one-actor-channel@0.1"

#: The value ``actor_id`` is replaced with once the channel is active.  A
#: constant rather than ``None`` so a method that still compares against an
#: owner id gets a well-defined miss instead of a ``TypeError`` three frames
#: away from the cause.
MASKED_ACTOR = "masked_actor"

#: Shared open-world key.  Same spelling as
#: :attr:`HierarchicalDirichletHabitModel.UNKNOWN_ACTOR`, deliberately: a
#: private spelling would land in its own pseudo-count bucket and read as a
#: second resident.
UNKNOWN_ACTOR = "unknown_actor"


class ActorEvidencePolicy(StrEnum):
    """How much a project-one arm is allowed to know about who moved an object."""

    #: Frozen v0.3 wiring: the arm reads ``event.actor_id`` directly.
    LEGACY_HARD_ACTOR = "legacy_hard_actor"
    #: No person evidence at all — the documented D0 non-identifiable regime.
    ABSENT = "absent"
    #: A robot-visible posterior that must keep non-zero uncertainty.
    CONTROLLED_NOISE = "controlled_noise"
    #: A one-hot posterior on the true actor, declared as an upper bound.
    ORACLE = "oracle"

    @property
    def masks_actor_identity(self) -> bool:
        """Whether ``actor_id`` is hidden from the arm under this policy."""

        return self is not ActorEvidencePolicy.LEGACY_HARD_ACTOR

    @property
    def is_upper_bound(self) -> bool:
        """Whether a result under this policy is a bound rather than a method score."""

        return self is ActorEvidencePolicy.ORACLE


@dataclass(frozen=True, slots=True)
class ProjectOneActorEvidence:
    """One event's robot-visible posterior over who moved the object.

    Mirrors :class:`cpswm.contracts.habit_learning.ActorResponsibilityEvidence`
    at the project-one record level: same support discipline, same
    prior/posterior pair so an upstream prior is not counted twice, and the
    same absence of a ``true_actor`` field.
    """

    event_id: str
    actor_posterior: Mapping[str, float]
    reference_actor_prior: Mapping[str, float]
    evidence_track: str
    evidence_model_id: str

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("actor evidence must bind an event id")
        if not self.actor_posterior:
            raise ValueError("actor_posterior must be non-empty")
        if set(self.actor_posterior) != set(self.reference_actor_prior):
            raise ValueError("reference_actor_prior and actor_posterior require identical support")
        for name, mapping in (
            ("actor_posterior", self.actor_posterior),
            ("reference_actor_prior", self.reference_actor_prior),
        ):
            for actor, value in mapping.items():
                if not actor.strip():
                    raise ValueError(f"{name} keys must be non-empty")
                if not isfinite(value) or value < 0.0 or value > 1.0:
                    raise ValueError(f"{name}[{actor}] must be a probability")
            if not isclose(sum(mapping.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
                raise ValueError(f"{name} must sum to 1")
        if any(value <= 0.0 for value in self.reference_actor_prior.values()):
            raise ValueError("reference_actor_prior must be strictly positive")
        if not self.evidence_track.strip() or not self.evidence_model_id.strip():
            raise ValueError("actor evidence must declare its track and model")

    def owner_mass(self, owner_id: str) -> float:
        """Posterior mass on the subject whose habit is being learned."""

        return float(self.actor_posterior.get(owner_id, 0.0))

    def likelihood_ratios(self) -> dict[str, float]:
        """Posterior/prior ratios, so a shared prior is not applied twice."""

        return {
            actor: posterior / self.reference_actor_prior[actor]
            for actor, posterior in self.actor_posterior.items()
        }

    @property
    def is_certain(self) -> bool:
        return max(self.actor_posterior.values()) >= 1.0

    def payload(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "actor_posterior": {k: repr(float(v)) for k, v in sorted(self.actor_posterior.items())},
            "reference_actor_prior": {
                k: repr(float(v)) for k, v in sorted(self.reference_actor_prior.items())
            },
            "evidence_track": self.evidence_track,
            "evidence_model_id": self.evidence_model_id,
        }


class ProjectOneActorChannel:
    """The only actor information a project-one arm may consume.

    Deliberately not a mapping the arm can iterate: an arm has to ask for one
    event id, exactly like :class:`ProjectOneTruthSet`.  Iterating would let an
    arm reconstruct the actor sequence and, with it, the change points.
    """

    __slots__ = ("_by_event", "_default_owner_mass", "_owner_id", "_policy", "_support")

    def __init__(
        self,
        *,
        policy: ActorEvidencePolicy,
        owner_id: str,
        evidence: Iterable[ProjectOneActorEvidence] = (),
        support: Sequence[str] = (),
        default_owner_mass: float | None = None,
    ) -> None:
        if not owner_id.strip():
            raise ValueError("actor channel requires an owner id")
        if owner_id == MASKED_ACTOR:
            raise ValueError("owner id cannot be the mask sentinel")
        self._policy = policy
        self._owner_id = owner_id
        by_event: dict[str, ProjectOneActorEvidence] = {}
        for item in evidence:
            if item.event_id in by_event:
                raise ValueError(f"duplicate actor evidence for event {item.event_id}")
            by_event[item.event_id] = item
        no_evidence_policies = {
            ActorEvidencePolicy.LEGACY_HARD_ACTOR,
            ActorEvidencePolicy.ABSENT,
        }
        if by_event and policy in no_evidence_policies:
            raise ValueError(f"policy {policy.value} cannot carry actor evidence")
        self._by_event = by_event
        self._support = tuple(dict.fromkeys(support)) or (owner_id, UNKNOWN_ACTOR)
        if default_owner_mass is None:
            # With no person evidence the only defensible prior is the share a
            # uniform prior over the declared support puts on the subject.  A
            # hand-picked number here would be a hidden tuning knob on the very
            # quantity RQ8 is about.
            default_owner_mass = 1.0 / len(self._support) if owner_id in self._support else 0.0
        if not isfinite(default_owner_mass) or not 0.0 <= default_owner_mass <= 1.0:
            raise ValueError("default_owner_mass must be a probability")
        self._default_owner_mass = float(default_owner_mass)

    @property
    def policy(self) -> ActorEvidencePolicy:
        return self._policy

    @property
    def owner_id(self) -> str:
        return self._owner_id

    @property
    def support(self) -> tuple[str, ...]:
        return self._support

    @property
    def masks_actor_identity(self) -> bool:
        return self._policy.masks_actor_identity

    @property
    def default_owner_mass(self) -> float:
        return self._default_owner_mass

    def evidence_for(self, event_id: str) -> ProjectOneActorEvidence | None:
        return self._by_event.get(event_id)

    def owner_mass(self, event_id: str) -> float:
        """Posterior mass on the subject for one event.

        Falls back to :attr:`default_owner_mass` when the channel carries no
        evidence for the event.  A missing observation is not evidence that the
        guest did it (`项目结构一 §7`: ``not_observed`` 不等于不存在).
        """

        evidence = self._by_event.get(event_id)
        if evidence is None:
            return self._default_owner_mass
        return evidence.owner_mass(self._owner_id)

    def config_payload(self) -> dict[str, object]:
        """Everything a reader needs to know this channel was in play."""

        return {
            "channel_version": ACTOR_CHANNEL_VERSION,
            "policy": self._policy.value,
            "owner_id": self._owner_id,
            "support": list(self._support),
            "default_owner_mass": repr(self._default_owner_mass),
            "evidence_count": len(self._by_event),
            "is_upper_bound": self._policy.is_upper_bound,
            "evidence_hash": content_sha256(
                [item.payload() for item in sorted(self._by_event.values(), key=_evidence_key)]
            ),
        }

    def __len__(self) -> int:
        return len(self._by_event)


def _evidence_key(evidence: ProjectOneActorEvidence) -> str:
    return evidence.event_id


class ProjectOneActorEvidenceProjector:
    """Evaluator-side conversion of actor truth into a declared robot channel.

    This class is allowed to read ``record.actor_id``; nothing downstream of it
    is.  It plays the same role as ``D0ShiftScenarioBuilder._actor_evidence``
    and produces the same shape of object, one level down in the stack.
    """

    def __init__(
        self,
        *,
        policy: ActorEvidencePolicy,
        owner_id: str,
        confusion: float = 0.2,
        unknown_mass: float = 0.1,
        model_id: str = "project-one-actor-evidence@0.1",
    ) -> None:
        if not owner_id.strip():
            raise ValueError("projector requires an owner id")
        if not isfinite(confusion) or not 0.0 < confusion < 1.0:
            raise ValueError("confusion must lie strictly inside (0, 1)")
        if not isfinite(unknown_mass) or not 0.0 < unknown_mass < 1.0:
            raise ValueError("unknown_mass must lie strictly inside (0, 1)")
        if confusion + unknown_mass >= 1.0:
            raise ValueError("confusion and unknown_mass must leave mass on the true actor")
        self._policy = policy
        self._owner_id = owner_id
        self._confusion = float(confusion)
        self._unknown_mass = float(unknown_mass)
        self._model_id = model_id

    def project_stream(
        self,
        records: Sequence[ProjectOneDatasetRecord],
        *,
        support: Sequence[str] | None = None,
    ) -> ProjectOneActorChannel:
        """Build the channel a method will be given for this stream."""

        # An actor vocabulary inferred from the complete evaluation stream
        # leaks future household membership and cardinality.  Production-like
        # runs must pass TRAIN_ONLY/MANIFEST support explicitly; without one,
        # all non-owner actors are represented by the open-world unknown bin.
        declared = (
            tuple(dict.fromkeys(support))
            if support is not None
            else (self._owner_id, UNKNOWN_ACTOR)
        )
        if self._owner_id not in declared:
            raise ValueError("declared actor support must contain the owner")
        if self._policy in {ActorEvidencePolicy.LEGACY_HARD_ACTOR, ActorEvidencePolicy.ABSENT}:
            return ProjectOneActorChannel(
                policy=self._policy,
                owner_id=self._owner_id,
                support=declared,
            )
        evidence = tuple(self._project_record(record, declared) for record in records)
        return ProjectOneActorChannel(
            policy=self._policy,
            owner_id=self._owner_id,
            evidence=evidence,
            support=declared,
        )

    def _project_record(
        self,
        record: ProjectOneDatasetRecord,
        support: tuple[str, ...],
    ) -> ProjectOneActorEvidence:
        reference_prior = {actor: 1.0 / len(support) for actor in support}
        true_actor = record.actor_id if record.actor_id in support else UNKNOWN_ACTOR
        if self._policy is ActorEvidencePolicy.ORACLE:
            oracle_posterior = {actor: (1.0 if actor == true_actor else 0.0) for actor in support}
            return ProjectOneActorEvidence(
                event_id=record.event_id,
                actor_posterior=oracle_posterior,
                reference_actor_prior=reference_prior,
                evidence_track="oracle",
                evidence_model_id=f"{self._model_id}:oracle",
            )

        # Controlled noise.  The draw is derived from the event identity, not
        # from a counter: two runs of the same stream must produce the same
        # channel, and two different events in one stream must not share a
        # draw.  ``content_sha256`` is the same primitive the rest of the
        # repository seeds from.
        draw = _unit_draw(ACTOR_CHANNEL_VERSION, record.stream_id, record.event_id)
        # Confusion is jittered inside [0.5c, 1.5c] so the channel is not a
        # constant relabelling of truth -- a fixed confusion would be invertible
        # and therefore still an oracle.
        confusion = self._confusion * (0.5 + draw)
        others = [actor for actor in support if actor not in {true_actor, UNKNOWN_ACTOR}]
        posterior: dict[str, float] = {actor: 0.0 for actor in support}
        posterior[UNKNOWN_ACTOR] = self._unknown_mass
        if others:
            share = confusion / len(others)
            for actor in others:
                posterior[actor] = share
            posterior[true_actor] = 1.0 - self._unknown_mass - confusion
        else:
            # A single-resident stream: the confusion mass has nowhere to go
            # except the open-world key, which is the correct destination.
            posterior[UNKNOWN_ACTOR] = self._unknown_mass + confusion
            posterior[true_actor] = 1.0 - posterior[UNKNOWN_ACTOR]
        total = sum(posterior.values())
        posterior = {actor: value / total for actor, value in posterior.items()}
        if max(posterior.values()) >= 1.0:
            raise ValueError("controlled-noise actor evidence must retain uncertainty")
        return ProjectOneActorEvidence(
            event_id=record.event_id,
            actor_posterior=posterior,
            reference_actor_prior=reference_prior,
            evidence_track="controlled_noise",
            evidence_model_id=f"{self._model_id}:controlled_noise",
        )


def _unit_draw(*parts: str) -> float:
    """Deterministic value in [0, 1) derived from content, not from a counter."""

    digest = content_sha256(list(parts))
    return int(digest[:16], 16) / float(1 << 64)


def permute_actor_labels(
    records: Sequence[ProjectOneDatasetRecord],
    *,
    owner_id: str,
    replacement: str = "permuted_actor",
) -> tuple[ProjectOneDatasetRecord, ...]:
    """Flip every actor label, leaving everything else byte-identical.

    Owner events become ``replacement`` and non-owner events become
    ``owner_id``.  This is the strongest possible perturbation of the field
    under audit and the weakest possible perturbation of everything else: any
    change in an arm's output is attributable to ``actor_id`` alone.
    """

    if replacement == owner_id:
        raise ValueError("replacement must differ from the owner id")
    return tuple(
        replace(record, actor_id=(replacement if record.actor_id == owner_id else owner_id))
        for record in records
    )


@dataclass(frozen=True, slots=True)
class ActorTruthIsolationReport:
    """Result of replaying one stream with the actor labels permuted."""

    policy: ActorEvidencePolicy
    events: int
    diverged_events: int
    first_divergence_event_id: str | None
    max_probability_gap: float
    max_change_probability_gap: float
    decision_flips: int

    @property
    def isolated(self) -> bool:
        """Whether the arm's output is independent of hard actor truth."""

        return self.diverged_events == 0

    def summary(self) -> dict[str, object]:
        return {
            "policy": self.policy.value,
            "events": self.events,
            "diverged_events": self.diverged_events,
            "first_divergence_event_id": self.first_divergence_event_id,
            "max_probability_gap": repr(self.max_probability_gap),
            "max_change_probability_gap": repr(self.max_change_probability_gap),
            "decision_flips": self.decision_flips,
            "isolated": self.isolated,
        }


def audit_actor_truth_isolation(
    build_method: Callable[[], Any],
    records: Sequence[ProjectOneDatasetRecord],
    *,
    policy: ActorEvidencePolicy,
    owner_id: str,
    tolerance: float = 1e-12,
) -> ActorTruthIsolationReport:
    """Replay a stream twice and report whether ``actor_id`` moved the output.

    ``build_method`` is called with no arguments and must return a fresh arm
    already bound to the actor channel under test.  The channel is built once
    from the *original* records and reused for the permuted replay, so the
    robot-visible person evidence is held fixed while the hidden truth flips.
    That is the whole point: if the arm only reads the channel, the two replays
    are identical; if it reads ``actor_id``, they are not.
    """

    if not records:
        raise ValueError("isolation audit needs at least one record")
    permuted = permute_actor_labels(records, owner_id=owner_id)

    baseline = build_method()
    baseline.reset()
    original = [baseline.observe(record) for record in records]

    perturbed_method = build_method()
    perturbed_method.reset()
    perturbed = [perturbed_method.observe(record) for record in permuted]

    diverged = 0
    first: str | None = None
    max_gap = 0.0
    max_change_gap = 0.0
    flips = 0
    for left, right in zip(original, perturbed, strict=True):
        gap = _distribution_gap(
            left.predicted_location_probabilities,
            right.predicted_location_probabilities,
        )
        change_gap = abs(left.change_probability - right.change_probability)
        flipped = left.decision is not right.decision
        max_gap = max(max_gap, gap)
        max_change_gap = max(max_change_gap, change_gap)
        flips += int(flipped)
        if gap > tolerance or change_gap > tolerance or flipped:
            diverged += 1
            if first is None:
                first = left.event_id
    return ActorTruthIsolationReport(
        policy=policy,
        events=len(original),
        diverged_events=diverged,
        first_divergence_event_id=first,
        max_probability_gap=max_gap,
        max_change_probability_gap=max_change_gap,
        decision_flips=flips,
    )


def _distribution_gap(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    keys = set(left) | set(right)
    return max((abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys), default=0.0)
