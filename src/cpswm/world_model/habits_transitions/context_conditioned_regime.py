"""Context-Conditioned Regime Reactivation (CCRR, 结构二 §4.7 #6).

The recurrent-concept-drift literature already covers regime libraries and
sticky HMM/HDP-HMM reactivation, so "keeping a history of regimes" is not a
contribution on its own.  This module implements the *specific* operator the
structure-two specification requires:

* a normalized posterior over ``stay / create / reactivate / unresolved``;
* an explicit ``alternative-cause exclusion`` step: before an old regime is
  reactivated, the model must rule out observation-policy recurrence (the robot
  merely went back to a room it had not visited), guest recurrence (a visitor
  returned rather than the owner resuming a habit), and identity switching (a
  data-association error that made an old context look like it returned);
* a deterministic, replayable decision that consumes the joint CF-BOCPD cause
  posterior (``JointCauseSnapshot``) instead of re-deriving change detection.

The reactor manages the regime lifecycle for one ``(object, actor)`` habit
stream.  It does **not** apply any long-term parameter write itself: it only
picks a regime decision and emits the posterior.  A downstream RGRC writer
(e.g. :class:`GatedHabitRegimeWriter`) applies or rejects the corresponding
parameter update, and a regime router (e.g. ``RLSRegimeBank``) switches the
active head.  Keeping decision and write separate preserves the CF-BOCPD x
CCRR x RGRC dependency chain.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from math import exp, isclose, log
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, Probability, require_aware

from .cause_factorized_bocpd import ChangeCause
from .joint_cause_bocpd import JointCauseSnapshot

#: How an (actor, regime) library entry was originally created.
_CAUSE_OF_CREATION: tuple[ChangeCause, ...] = (
    ChangeCause.HABIT,
    ChangeCause.ACTOR,
)


class RegimeDecisionKind(StrEnum):
    STAY = "stay"
    CREATE = "create"
    REACTIVATE = "reactivate"
    UNRESOLVED = "unresolved"


class RegimeLibraryEntry(ContractModel):
    """One retained historical habit regime with its context fingerprint."""

    regime_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    object_instance_id: UUID
    #: Context fingerprint used for similarity matching.  A regime is only
    #: reactivated when the current context resembles the one under which it
    #: was originally active.
    context_fingerprint: tuple[float, ...] = Field(min_length=1)
    #: Which cause created this regime (habit change vs actor-mixture change).
    cause_origin: ChangeCause
    created_at: datetime
    last_active_at: datetime | None = None
    activation_count: int = Field(default=0, ge=0)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return require_aware(value, "created_at")

    @field_validator("last_active_at")
    @classmethod
    def validate_last_active_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_aware(value, "last_active_at")

    @field_validator("context_fingerprint")
    @classmethod
    def validate_fingerprint(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if any(not (-1e6 < component < 1e6) for component in value):
            raise ValueError("context fingerprint components must be finite")
        return value


class RegimeDecision(ContractModel):
    """A normalized stay/create/reactivate/unresolved posterior decision."""

    kind: RegimeDecisionKind
    posterior: dict[RegimeDecisionKind, Probability]
    reactivated_regime_id: str | None = None
    created_regime_id: str | None = None
    #: Alternative explanations that were explicitly ruled out before deciding.
    alternative_causes_ruled_out: tuple[str, ...] = ()
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_decision(self) -> RegimeDecision:
        expected = set(RegimeDecisionKind)
        if set(self.posterior) != expected:
            raise ValueError("regime decision posterior must cover all four kinds")
        if not isclose(
            sum(self.posterior.values()), 1.0, rel_tol=0.0, abs_tol=1e-6
        ):
            raise ValueError("regime decision posterior must sum to one")
        if self.kind == RegimeDecisionKind.REACTIVATE and not self.reactivated_regime_id:
            raise ValueError("a reactivate decision requires reactivated_regime_id")
        if self.kind == RegimeDecisionKind.CREATE and not self.created_regime_id:
            raise ValueError("a create decision requires created_regime_id")
        if self.kind != RegimeDecisionKind.REACTIVATE and self.reactivated_regime_id:
            raise ValueError("only a reactivate decision carries reactivated_regime_id")
        if self.kind != RegimeDecisionKind.CREATE and self.created_regime_id:
            raise ValueError("only a create decision carries created_regime_id")
        return self

    @property
    def selected_posterior(self) -> float:
        return self.posterior[self.kind]


def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("context fingerprints must share dimensionality")
    left_norm = float(sum(component * component for component in left)) ** 0.5
    right_norm = float(sum(component * component for component in right)) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot = 0.0
    for a, b in zip(left, right, strict=True):
        dot += a * b
    return dot / (left_norm * right_norm)


class ContextConditionedRegimeReactivator:
    """Maintain a habit-regime library and emit a competitive regime posterior.

    Decision inputs are the joint CF-BOCPD snapshot, the current context, and an
    optional identity-switch signal.  The reactor keeps the library as ordinary
    state but every decision is a pure function of its inputs plus the library,
    so identical inputs yield an identical posterior (deterministic replay).
    """

    def __init__(
        self,
        *,
        change_threshold: float = 0.5,
        similarity_threshold: float = 0.6,
        attribution_margin: float = 0.15,
        identity_switch_threshold: float = 0.5,
        default_regime_id: str = "stable",
        model_version: str = "ccrr@0.1",
    ) -> None:
        if not 0.0 < change_threshold <= 1.0:
            raise ValueError("change_threshold must lie in (0, 1]")
        if not -1.0 <= similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must lie in [-1, 1]")
        if not 0.0 <= attribution_margin < 1.0:
            raise ValueError("attribution_margin must lie in [0, 1)")
        if not 0.0 <= identity_switch_threshold <= 1.0:
            raise ValueError("identity_switch_threshold must lie in [0, 1]")
        if not default_regime_id.strip():
            raise ValueError("default_regime_id must be non-empty")
        self.change_threshold = change_threshold
        self.similarity_threshold = similarity_threshold
        self.attribution_margin = attribution_margin
        self.identity_switch_threshold = identity_switch_threshold
        self.default_regime_id = default_regime_id
        self.model_version = model_version
        self._library: dict[tuple[UUID, str], dict[str, RegimeLibraryEntry]] = {}
        self._current_regime: dict[tuple[UUID, str], str] = {}

    # --- library management --------------------------------------------------

    def library(
        self, *, object_instance_id: UUID, actor_id: str
    ) -> tuple[RegimeLibraryEntry, ...]:
        """Return retained regimes for one (object, actor) stream."""

        regimes = self._library.get((object_instance_id, actor_id), {})
        return tuple(sorted(regimes.values(), key=lambda entry: entry.regime_id))

    def active_regime(self, *, object_instance_id: UUID, actor_id: str) -> str:
        return self._current_regime.get(
            (object_instance_id, actor_id), self.default_regime_id
        )

    def add_regime(
        self,
        entry: RegimeLibraryEntry,
        *,
        make_active: bool = False,
    ) -> None:
        """Insert (or refresh) a retained regime entry."""

        key = (entry.object_instance_id, entry.actor_id)
        stream = self._library.setdefault(key, {})
        if entry.regime_id in stream:
            existing = stream[entry.regime_id]
            if existing.context_fingerprint != entry.context_fingerprint:
                raise ValueError(
                    "a regime id cannot be rebound to a different context fingerprint"
                )
        stream[entry.regime_id] = entry
        if make_active:
            self._current_regime[key] = entry.regime_id

    def _record_activation(self, entry: RegimeLibraryEntry, *, now: datetime) -> None:
        refreshed = entry.model_copy(
            update={
                "last_active_at": now,
                "activation_count": entry.activation_count + 1,
            }
        )
        self.add_regime(refreshed)

    # --- decision ------------------------------------------------------------

    def decide(
        self,
        *,
        object_instance_id: UUID,
        actor_id: str,
        owner_actor_id: str | None,
        snapshot: JointCauseSnapshot,
        context_features: tuple[float, ...],
        identity_switch_probability: float = 0.0,
        now: datetime,
    ) -> RegimeDecision:
        """Compute the competitive stay/create/reactivate/unresolved posterior."""

        if not 0.0 <= identity_switch_probability <= 1.0:
            raise ValueError("identity_switch_probability must lie in [0, 1]")
        now = require_aware(now, "now")
        stream = self._library.get((object_instance_id, actor_id), {})
        current_regime_id = self.active_regime(
            object_instance_id=object_instance_id, actor_id=actor_id
        )

        # Decompose the joint cause posterior into the four masses that matter.
        p_continue = snapshot.continue_probability
        p_noise = snapshot.transient_noise_probability
        p_change = snapshot.segment_change_probability
        cause_posterior = snapshot.segment_cause_posterior
        p_habit = cause_posterior.get(ChangeCause.HABIT, 0.0)
        p_actor = cause_posterior.get(ChangeCause.ACTOR, 0.0)
        p_observation = cause_posterior.get(ChangeCause.OBSERVATION, 0.0)

        # Alternative-cause exclusion (specification §4.7 #6).
        ruled_out: list[str] = []
        # 1. Observation-policy recurrence: the change is explained by the
        #    robot merely seeing something again, not by a resumed habit.
        observation_mass = p_change * p_observation
        if p_change >= self.change_threshold and p_observation > p_habit:
            ruled_out.append("observation_policy_recurrence")
        # 2. Identity switching: a data-association error, not a real return.
        identity_veto = identity_switch_probability >= self.identity_switch_threshold
        if identity_veto:
            ruled_out.append("identity_switch")

        # 3. Guest recurrence: an actor-mixture change is a visitor returning,
        #    which reactivates the *guest* regime, never the owner's habit.
        is_owner_stream = owner_actor_id is None or actor_id == owner_actor_id
        if p_change >= self.change_threshold and p_actor > p_habit and not is_owner_stream:
            ruled_out.append("guest_recurrence_on_owner_stream")

        # Context similarity against the retained library (reactivate target).
        best_similarity = -1.0
        best_match: RegimeLibraryEntry | None = None
        for entry in stream.values():
            if entry.regime_id == current_regime_id:
                continue
            similarity = _cosine_similarity(context_features, entry.context_fingerprint)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = entry

        # Habit-change mass that survives the alternative-cause exclusions.
        # A change is only treated as a genuine owner-habit event when the habit
        # cause dominates and no identity veto applies.
        genuine_habit = p_change * p_habit
        if identity_veto:
            genuine_habit = 0.0

        # Ambiguity: a real change whose cause is not separable (the same margin
        # test the RGRC write gate uses), or an unexplained residual.
        ranked = (
            sorted(cause_posterior.values(), reverse=True)
            if cause_posterior
            else [0.0]
        )
        top_margin = ranked[0] - (ranked[1] if len(ranked) > 1 else 0.0)
        ambiguous_change = (
            p_change >= self.change_threshold and top_margin < self.attribution_margin
        )

        # Build unnormalized logits for the four decision kinds.
        # STAY: continuation, transient noise, observation-policy recurrence,
        #       actor change on the owner stream, or an identity veto all mean
        #       "do not change the active regime".
        stay_logit = (
            2.0 * p_continue
            + 2.0 * p_noise
            + observation_mass
            + (0.0 if not is_owner_stream else p_change * p_actor)
            + (1.0 if identity_veto else 0.0)
        )
        # REACTIVATE: a genuine habit return whose context matches a retained
        # regime; also a guest recurrence on the guest stream (visitor returns).
        reactivate_logit = 0.0
        if not identity_veto and best_match is not None:
            if genuine_habit > 0.0 and best_similarity >= self.similarity_threshold:
                reactivate_logit += genuine_habit * best_similarity
            if (
                not is_owner_stream
                and p_change * p_actor > 0.0
                and best_similarity >= self.similarity_threshold
            ):
                reactivate_logit += p_change * p_actor * best_similarity
        # CREATE: a genuine habit change with no sufficiently similar retained
        # regime (a brand-new habit), or a genuine change on a fresh stream.
        create_logit = 0.0
        if not identity_veto:
            if genuine_habit > 0.0 and best_similarity < self.similarity_threshold:
                create_logit += genuine_habit
            if (
                genuine_habit > 0.0
                and not stream
                and p_change >= self.change_threshold
            ):
                create_logit += genuine_habit
        # UNRESOLVED: a real but unattributable change, or a residual mass.
        unresolved_logit = (1.0 if ambiguous_change else 0.0) + (
            p_change * max(0.0, 1.0 - top_margin) if cause_posterior else 0.0
        )

        posterior = _softmax(
            {
                RegimeDecisionKind.STAY: stay_logit,
                RegimeDecisionKind.CREATE: create_logit,
                RegimeDecisionKind.REACTIVATE: reactivate_logit,
                RegimeDecisionKind.UNRESOLVED: unresolved_logit,
            }
        )
        kind = max(posterior, key=lambda key: posterior[key])

        reactivated_regime_id: str | None = None
        created_regime_id: str | None = None
        if kind == RegimeDecisionKind.REACTIVATE and best_match is not None:
            reactivated_regime_id = best_match.regime_id
            self._record_activation(best_match, now=now)
            self._current_regime[(object_instance_id, actor_id)] = best_match.regime_id
        elif kind == RegimeDecisionKind.CREATE:
            created_regime_id = f"{actor_id}@{now.isoformat()}@{object_instance_id.hex[:8]}"
            self.add_regime(
                RegimeLibraryEntry(
                    regime_id=created_regime_id,
                    actor_id=actor_id,
                    object_instance_id=object_instance_id,
                    context_fingerprint=context_features,
                    cause_origin=ChangeCause.HABIT,
                    created_at=now,
                    last_active_at=now,
                    activation_count=1,
                ),
                make_active=True,
            )
        elif kind == RegimeDecisionKind.REACTIVATE:
            # Defensive: reactivate with no match is impossible by construction.
            raise RuntimeError("reactivate decision requires a matching regime")

        rationale = self._rationale(
            kind=kind,
            best_similarity=best_similarity,
            p_change=p_change,
            p_habit=p_habit,
            p_actor=p_actor,
            p_observation=p_observation,
            identity_veto=identity_veto,
            ambiguous_change=ambiguous_change,
            ruled_out=ruled_out,
        )
        return RegimeDecision(
            kind=kind,
            posterior=posterior,
            reactivated_regime_id=reactivated_regime_id,
            created_regime_id=created_regime_id,
            alternative_causes_ruled_out=tuple(ruled_out),
            rationale=rationale,
        )

    @staticmethod
    def _rationale(
        *,
        kind: RegimeDecisionKind,
        best_similarity: float,
        p_change: float,
        p_habit: float,
        p_actor: float,
        p_observation: float,
        identity_veto: bool,
        ambiguous_change: bool,
        ruled_out: list[str],
    ) -> str:
        exclusions = ", ".join(ruled_out) if ruled_out else "none"
        if kind == RegimeDecisionKind.UNRESOLVED:
            return (
                f"unresolved: change={p_change:.3f} ambiguous={ambiguous_change}; "
                f"excluded causes: {exclusions}"
            )
        if kind == RegimeDecisionKind.STAY:
            return (
                f"stay: change={p_change:.3f} habit={p_habit:.3f} actor={p_actor:.3f} "
                f"observation={p_observation:.3f} identity_veto={identity_veto}; "
                f"excluded causes: {exclusions}"
            )
        if kind == RegimeDecisionKind.REACTIVATE:
            return f"reactivate: similarity={best_similarity:.3f}; excluded causes: {exclusions}"
        return f"create: similarity={best_similarity:.3f}; excluded causes: {exclusions}"


def _softmax(logits: dict[RegimeDecisionKind, float]) -> dict[RegimeDecisionKind, float]:
    peak = max(logits.values())
    total = sum(exp(value - peak) for value in logits.values())
    return {kind: exp(value - peak) / total for kind, value in logits.items()}


def log_odds(value: float) -> float:
    """Return the log-odds of a probability (exported for tests)."""

    if not 0.0 < value < 1.0:
        raise ValueError("probability must lie strictly inside (0, 1)")
    return log(value / (1.0 - value))
