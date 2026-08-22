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
from math import exp, isclose, log, sqrt
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
    """A normalized stay/create/reactivate/unresolved decision score.

    The four values are a deterministic heuristic score normalized by softmax,
    not a calibrated posterior.  ``decision_time`` is the instant the decision
    was computed and is used by ``apply_decision`` for bookkeeping.
    """

    kind: RegimeDecisionKind
    decision_score: dict[RegimeDecisionKind, Probability]
    reactivated_regime_id: str | None = None
    created_regime_id: str | None = None
    decision_time: datetime
    #: Alternative explanations that were explicitly ruled out before deciding.
    alternative_causes_ruled_out: tuple[str, ...] = ()
    rationale: str = Field(min_length=1)

    @field_validator("decision_time")
    @classmethod
    def validate_decision_time(cls, value: datetime) -> datetime:
        return require_aware(value, "decision_time")

    @model_validator(mode="after")
    def validate_decision(self) -> RegimeDecision:
        expected = set(RegimeDecisionKind)
        if set(self.decision_score) != expected:
            raise ValueError("regime decision score must cover all four kinds")
        if not isclose(
            sum(self.decision_score.values()), 1.0, rel_tol=0.0, abs_tol=1e-6
        ):
            raise ValueError("regime decision score must sum to one")
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
    def selected_score(self) -> float:
        return self.decision_score[self.kind]


def _cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("context fingerprints must share dimensionality")
    left_norm = sqrt(float(sum(component * component for component in left)))
    right_norm = sqrt(float(sum(component * component for component in right)))
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
        self._version = 0

    # --- library management --------------------------------------------------

    @property
    def library_version(self) -> int:
        return self._version

    def library(
        self, *, object_instance_id: UUID, actor_id: str
    ) -> tuple[RegimeLibraryEntry, ...]:
        """Return an immutable copy of the retained regimes for one stream."""

        regimes = dict(self._library.get((object_instance_id, actor_id), {}))
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
        """Insert (or refresh) a retained regime entry (mutating; test setup)."""

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
        self._version += 1

    # --- pure scoring --------------------------------------------------------

    def score_decision(
        self,
        *,
        object_instance_id: UUID,
        actor_id: str,
        owner_actor_id: str | None,
        snapshot: JointCauseSnapshot,
        context_features: tuple[float, ...],
        identity_switch_probability: float = 0.0,
        now: datetime,
        library: tuple[RegimeLibraryEntry, ...] | None = None,
        active_regime_id: str | None = None,
    ) -> RegimeDecision:
        """Compute the competitive stay/create/reactivate/unresolved score.

        Pure: it reads ``library`` and ``active_regime_id`` (defaulting to an
        immutable snapshot of the current state) and mutates nothing.
        """

        if not 0.0 <= identity_switch_probability <= 1.0:
            raise ValueError("identity_switch_probability must lie in [0, 1]")
        now = require_aware(now, "now")
        entries = (
            tuple(self._library.get((object_instance_id, actor_id), {}).values())
            if library is None
            else library
        )
        current_regime_id = (
            self.active_regime(object_instance_id=object_instance_id, actor_id=actor_id)
            if active_regime_id is None
            else active_regime_id
        )

        # Decompose the joint cause posterior into the four masses that matter.
        p_continue = snapshot.continue_probability
        p_noise = snapshot.transient_noise_probability
        p_change = snapshot.segment_change_probability
        cause_posterior = snapshot.segment_cause_posterior
        p_habit = cause_posterior.get(ChangeCause.HABIT, 0.0)
        p_actor = cause_posterior.get(ChangeCause.ACTOR, 0.0)
        p_observation = cause_posterior.get(ChangeCause.OBSERVATION, 0.0)

        # Dominant cause, used for the cause-origin compatibility gate.
        dominant_cause = (
            max(cause_posterior, key=lambda cause: cause_posterior[cause])
            if cause_posterior
            else None
        )

        # Alternative-cause exclusion (specification §4.7 #6).
        ruled_out: list[str] = []
        observation_mass = p_change * p_observation
        if p_change >= self.change_threshold and p_observation > p_habit:
            ruled_out.append("observation_policy_recurrence")
        identity_veto = identity_switch_probability >= self.identity_switch_threshold
        if identity_veto:
            ruled_out.append("identity_switch")

        is_owner_stream = owner_actor_id is None or actor_id == owner_actor_id
        if p_change >= self.change_threshold and p_actor > p_habit and not is_owner_stream:
            ruled_out.append("guest_recurrence_on_owner_stream")

        # Rank reactivate candidates by a frozen ordering:
        #   similarity ↓, cause compatibility ↓, last_active_at ↓, regime_id ↑.
        candidates: list[tuple[RegimeLibraryEntry, float, bool]] = []
        for entry in entries:
            if entry.regime_id == current_regime_id:
                continue
            if entry.actor_id != actor_id:
                continue
            similarity = _cosine_similarity(context_features, entry.context_fingerprint)
            compatible = _cause_is_compatible(entry.cause_origin, dominant_cause)
            candidates.append((entry, similarity, compatible))
        candidates.sort(
            key=lambda item: (
                -item[1],
                -int(item[2]),
                -_last_active_seconds(item[0]),
                item[0].regime_id,
            )
        )
        best_match = candidates[0][0] if candidates else None
        best_similarity = candidates[0][1] if candidates else -1.0
        best_compatible = candidates[0][2] if candidates else False

        # Habit-change mass that survives the alternative-cause exclusions.
        genuine_habit = p_change * p_habit
        if identity_veto:
            genuine_habit = 0.0

        # Ambiguity: a real change whose cause is not separable.
        ranked = (
            sorted(cause_posterior.values(), reverse=True)
            if cause_posterior
            else [0.0]
        )
        top_margin = ranked[0] - (ranked[1] if len(ranked) > 1 else 0.0)
        ambiguous_change = (
            p_change >= self.change_threshold and top_margin < self.attribution_margin
        )

        stay_logit = (
            2.0 * p_continue
            + 2.0 * p_noise
            + observation_mass
            + (0.0 if not is_owner_stream else p_change * p_actor)
            + (1.0 if identity_veto else 0.0)
        )
        reactivate_logit = 0.0
        if (
            not identity_veto
            and best_match is not None
            and best_compatible
            and best_similarity >= self.similarity_threshold
        ):
            reactivate_logit += genuine_habit * best_similarity
            if not is_owner_stream and p_change * p_actor > 0.0:
                reactivate_logit += p_change * p_actor * best_similarity
        create_logit = 0.0
        if not identity_veto:
            has_compatible_match = (
                best_match is not None
                and best_compatible
                and best_similarity >= self.similarity_threshold
            )
            if genuine_habit > 0.0 and not has_compatible_match:
                create_logit += genuine_habit
            if genuine_habit > 0.0 and not entries and p_change >= self.change_threshold:
                create_logit += genuine_habit
        unresolved_logit = (1.0 if ambiguous_change else 0.0) + (
            p_change * max(0.0, 1.0 - top_margin) if cause_posterior else 0.0
        )

        decision_score = _softmax(
            {
                RegimeDecisionKind.STAY: stay_logit,
                RegimeDecisionKind.CREATE: create_logit,
                RegimeDecisionKind.REACTIVATE: reactivate_logit,
                RegimeDecisionKind.UNRESOLVED: unresolved_logit,
            }
        )
        kind = max(decision_score, key=lambda key: decision_score[key])

        reactivated_regime_id: str | None = None
        created_regime_id: str | None = None
        if kind == RegimeDecisionKind.REACTIVATE:
            if best_match is None:
                raise RuntimeError("reactivate decision requires a matching regime")
            reactivated_regime_id = best_match.regime_id
        elif kind == RegimeDecisionKind.CREATE:
            created_regime_id = (
                f"{actor_id}@{now.isoformat()}@{object_instance_id.hex[:8]}"
            )

        rationale = self._rationale(
            kind=kind,
            best_similarity=best_similarity,
            best_compatible=best_compatible,
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
            decision_score=decision_score,
            reactivated_regime_id=reactivated_regime_id,
            created_regime_id=created_regime_id,
            decision_time=now,
            alternative_causes_ruled_out=tuple(ruled_out),
            rationale=rationale,
        )

    def apply_decision(
        self,
        decision: RegimeDecision,
        *,
        object_instance_id: UUID,
        actor_id: str,
        context_features: tuple[float, ...],
        expected_library_version: int,
    ) -> int:
        """Apply a scored decision's side effects under a version check.

        ``context_features`` supplies the context fingerprint for a newly
        created stage.  Returns the new library version and raises
        ``StaleLibraryError`` if the library moved meanwhile.
        """

        if self._version != expected_library_version:
            raise StaleLibraryError(
                f"library version moved (expected {expected_library_version}, "
                f"actual {self._version})"
            )
        key = (object_instance_id, actor_id)
        if decision.kind == RegimeDecisionKind.REACTIVATE:
            entry = self._library[key][decision.reactivated_regime_id]
            refreshed = entry.model_copy(
                update={
                    "last_active_at": decision.decision_time,
                    "activation_count": entry.activation_count + 1,
                }
            )
            self._library[key][entry.regime_id] = refreshed
            self._current_regime[key] = entry.regime_id
        elif decision.kind == RegimeDecisionKind.CREATE:
            entry = RegimeLibraryEntry(
                regime_id=decision.created_regime_id,
                actor_id=actor_id,
                object_instance_id=object_instance_id,
                context_fingerprint=context_features,
                cause_origin=ChangeCause.HABIT,
                created_at=decision.decision_time,
                last_active_at=decision.decision_time,
                activation_count=1,
            )
            self._library.setdefault(key, {})[entry.regime_id] = entry
            self._current_regime[key] = entry.regime_id
        # STAY / UNRESOLVED have no library side effects.
        self._version += 1
        return self._version

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
        """Convenience: score then apply in one call (mutating)."""

        library = self.library(object_instance_id=object_instance_id, actor_id=actor_id)
        active_regime_id = self.active_regime(
            object_instance_id=object_instance_id, actor_id=actor_id
        )
        decision = self.score_decision(
            object_instance_id=object_instance_id,
            actor_id=actor_id,
            owner_actor_id=owner_actor_id,
            snapshot=snapshot,
            context_features=context_features,
            identity_switch_probability=identity_switch_probability,
            now=now,
            library=library,
            active_regime_id=active_regime_id,
        )
        self.apply_decision(
            decision,
            object_instance_id=object_instance_id,
            actor_id=actor_id,
            context_features=context_features,
            expected_library_version=self._version,
        )
        return decision

    @staticmethod
    def _rationale(
        *,
        kind: RegimeDecisionKind,
        best_similarity: float,
        best_compatible: bool,
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
            return (
                f"reactivate: similarity={best_similarity:.3f} "
                f"compatible={best_compatible}; excluded causes: {exclusions}"
            )
        return (
            f"create: similarity={best_similarity:.3f} "
            f"compatible={best_compatible}; excluded causes: {exclusions}"
        )


def _softmax(logits: dict[RegimeDecisionKind, float]) -> dict[RegimeDecisionKind, float]:
    peak = max(logits.values())
    total = sum(exp(value - peak) for value in logits.values())
    return {kind: exp(value - peak) / total for kind, value in logits.items()}


def _cause_is_compatible(entry_origin: ChangeCause, dominant_cause: ChangeCause | None) -> bool:
    """A retained regime may only be reactivated by a change of its own cause.

    An ACTOR-origin stage (e.g. a guest stage) cannot be reactivated by a habit
    change, and a HABIT-origin stage cannot be reactivated by an actor-mixture
    change.  No change or an observation change is compatible with nothing.
    """

    if dominant_cause is None or dominant_cause == ChangeCause.OBSERVATION:
        return False
    return entry_origin == dominant_cause


def _last_active_seconds(entry: RegimeLibraryEntry) -> float:
    """A monotone, sortable key for ``last_active_at`` (never-active -> -inf)."""

    if entry.last_active_at is None:
        return float("-inf")
    return entry.last_active_at.timestamp()


class StaleLibraryError(RuntimeError):
    """Raised when a decision is applied against an outdated library version."""


def log_odds(value: float) -> float:
    """Return the log-odds of a probability (exported for tests)."""

    if not 0.0 < value < 1.0:
        raise ValueError("probability must lie strictly inside (0, 1)")
    return log(value / (1.0 - value))
