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

import secrets
import threading
from copy import deepcopy
from datetime import datetime
from enum import StrEnum
from math import exp, isclose, log, sqrt
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, Probability, require_aware
from cpswm.system.reproducibility import content_sha256

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


class StaleLibraryError(RuntimeError):
    """Raised when a decision is applied against an outdated library version."""


class ForgedDecisionError(RuntimeError):
    """Raised when a decision does not match its scoring envelope (tampering)."""


class RegimeScoringEnvelope(ContractModel):
    """The complete, replayable scoring input behind one regime decision.

    ``apply_decision`` re-scores from this envelope inside the reactor lock and
    compares field by field, so a decision whose inputs or outputs were forged
    (STAY rewired to CREATE, HABIT rewritten to ACTOR, score tampered, or
    replayed under another config/instance) is rejected.
    """

    owner_actor_id: str | None = None
    identity_switch_probability: float = Field(ge=0.0, le=1.0)
    context_features: tuple[float, ...] = Field(min_length=1)
    #: JointCauseSnapshot fields actually consumed by scoring.
    continue_probability: Probability
    transient_noise_probability: Probability
    segment_change_probability: Probability
    segment_cause_posterior: dict[ChangeCause, Probability]
    #: SHA-256 of the full upstream snapshot (audit binding, not re-scored).
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_timestamp: datetime
    decision_time: datetime
    library_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    library_version: int = Field(ge=0)

    @field_validator("snapshot_timestamp", "decision_time")
    @classmethod
    def validate_times(cls, value: datetime) -> datetime:
        return require_aware(value, "scoring envelope time")


class RegimeLibraryView(ContractModel):
    """An immutable snapshot of one (object, actor) library stream.

    ``score_decision`` reads only this view, so a decision is bound to the exact
    library version it was scored against.  ``apply_decision`` then compares
    ``scored_library_version`` to the live version under a lock, closing the
    score-then-apply race.
    """

    object_instance_id: UUID
    actor_id: str = Field(min_length=1)
    entries: tuple[RegimeLibraryEntry, ...]
    active_regime_id: str = Field(min_length=1)
    library_version: int = Field(ge=0)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_content_hash(self) -> RegimeLibraryView:
        expected = content_sha256(self.model_dump(mode="python", exclude={"content_hash"}))
        if self.content_hash != expected:
            raise ValueError("regime library view content hash does not match")
        return self


class RegimeDecision(ContractModel):
    """A normalized stay/create/reactivate/unresolved decision score.

    The four values are a deterministic heuristic score normalized by softmax,
    not a calibrated posterior.  A decision is bound to the exact
    ``(object, actor)`` stream, the library content hash, the context hash, and
    the model version it was scored against, so it cannot be replayed onto a
    different stream or under a swapped context.
    """

    kind: RegimeDecisionKind
    decision_score: dict[RegimeDecisionKind, Probability]
    reactivated_regime_id: str | None = None
    created_regime_id: str | None = None
    decision_time: datetime
    #: The stream the decision was scored for (``apply_decision`` trusts these,
    #: never caller-supplied identities).
    object_instance_id: UUID
    actor_id: str = Field(min_length=1)
    #: Reactor-private, single-use token; only the issuing reactor accepts it.
    decision_token: str = Field(min_length=1)
    #: Per-stream library version at scoring time.
    scored_library_version: int = Field(ge=0)
    #: SHA-256 of the scored library view (binds the decision to its contents).
    library_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    #: The context features the decision was scored under (used verbatim by
    #: ``apply_decision`` for CREATE writes; callers cannot substitute them).
    context_features: tuple[float, ...] = Field(min_length=1)
    #: SHA-256 of ``context_features``.
    context_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    #: Model/config version at scoring time.
    model_version: str = Field(min_length=1)
    #: Which cause a CREATE decision will stamp on the new regime.
    created_cause_origin: ChangeCause | None = None
    #: The complete scoring input; ``apply_decision`` re-scores from it.
    scoring_envelope: RegimeScoringEnvelope
    #: SHA-256 of thresholds + default stage + model version at scoring time.
    model_config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
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
        if not isclose(sum(self.decision_score.values()), 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("regime decision score must sum to one")
        if self.context_hash != content_sha256(list(self.context_features)):
            raise ValueError("regime decision context hash does not match")
        if self.scoring_envelope.context_features != self.context_features:
            raise ValueError("scoring envelope context does not match the decision")
        if self.scoring_envelope.library_content_hash != self.library_content_hash:
            raise ValueError("scoring envelope library hash does not match the decision")
        if self.scoring_envelope.library_version != self.scored_library_version:
            raise ValueError("scoring envelope library version does not match the decision")
        if self.kind == RegimeDecisionKind.REACTIVATE and not self.reactivated_regime_id:
            raise ValueError("a reactivate decision requires reactivated_regime_id")
        if self.kind == RegimeDecisionKind.CREATE and not self.created_regime_id:
            raise ValueError("a create decision requires created_regime_id")
        if self.kind == RegimeDecisionKind.CREATE and self.created_cause_origin is None:
            raise ValueError("a create decision requires created_cause_origin")
        if self.kind != RegimeDecisionKind.REACTIVATE and self.reactivated_regime_id:
            raise ValueError("only a reactivate decision carries reactivated_regime_id")
        if self.kind != RegimeDecisionKind.CREATE and self.created_regime_id:
            raise ValueError("only a create decision carries created_regime_id")
        if self.kind != RegimeDecisionKind.CREATE and self.created_cause_origin is not None:
            raise ValueError("only a create decision carries created_cause_origin")
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
        allow_reactivation: bool = True,
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
        self.allow_reactivation = allow_reactivation
        self.model_config_hash = content_sha256(
            {
                "change_threshold": change_threshold,
                "similarity_threshold": similarity_threshold,
                "attribution_margin": attribution_margin,
                "identity_switch_threshold": identity_switch_threshold,
                "default_regime_id": default_regime_id,
                "model_version": model_version,
                "allow_reactivation": allow_reactivation,
            }
        )
        self._library: dict[tuple[UUID, str], dict[str, RegimeLibraryEntry]] = {}
        self._current_regime: dict[tuple[UUID, str], str] = {}
        # Per-stream versions: a mutation on stream A must never invalidate a
        # decision scored for stream B (no false conflict across streams).
        self._stream_versions: dict[tuple[UUID, str], int] = {}
        # Global mutation counter, exposed via ``library_version`` for tests.
        self._version = 0
        # Reactor-private, single-use decision tokens.
        self._pending_tokens: set[str] = set()
        self._lock = threading.RLock()

    def __deepcopy__(self, memo):
        clone = type(self)(
            change_threshold=self.change_threshold,
            similarity_threshold=self.similarity_threshold,
            attribution_margin=self.attribution_margin,
            identity_switch_threshold=self.identity_switch_threshold,
            default_regime_id=self.default_regime_id,
            model_version=self.model_version,
            allow_reactivation=self.allow_reactivation,
        )
        memo[id(self)] = clone
        clone._library = deepcopy(self._library, memo)
        clone._current_regime = dict(self._current_regime)
        clone._stream_versions = dict(self._stream_versions)
        clone._version = self._version
        clone._pending_tokens = set(self._pending_tokens)
        return clone

    # --- library management --------------------------------------------------

    @property
    def library_version(self) -> int:
        """Global mutation counter (every library write bumps it)."""

        with self._lock:
            return self._version

    def _stream_version(self, key: tuple[UUID, str]) -> int:
        return self._stream_versions.get(key, 0)

    def view(self, *, object_instance_id: UUID, actor_id: str) -> RegimeLibraryView:
        """Return an immutable, content-hashed snapshot of one stream."""

        with self._lock:
            key = (object_instance_id, actor_id)
            entries = tuple(
                sorted(
                    self._library.get(key, {}).values(),
                    key=lambda entry: entry.regime_id,
                )
            )
            active_regime_id = self._current_regime.get(key, self.default_regime_id)
            version = self._stream_version(key)
            content_hash = content_sha256(
                {
                    "object_instance_id": object_instance_id,
                    "actor_id": actor_id,
                    "entries": [entry.model_dump(mode="python") for entry in entries],
                    "active_regime_id": active_regime_id,
                    "library_version": version,
                }
            )
            return RegimeLibraryView(
                object_instance_id=object_instance_id,
                actor_id=actor_id,
                entries=entries,
                active_regime_id=active_regime_id,
                library_version=version,
                content_hash=content_hash,
            )

    def library(self, *, object_instance_id: UUID, actor_id: str) -> tuple[RegimeLibraryEntry, ...]:
        """Return an immutable copy of the retained regimes for one stream."""

        return self.view(object_instance_id=object_instance_id, actor_id=actor_id).entries

    def active_regime(self, *, object_instance_id: UUID, actor_id: str) -> str:
        with self._lock:
            return self._current_regime.get((object_instance_id, actor_id), self.default_regime_id)

    def add_regime(
        self,
        entry: RegimeLibraryEntry,
        *,
        make_active: bool = False,
    ) -> None:
        """Insert (or refresh) a retained regime entry (mutating; test setup)."""

        with self._lock:
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
            self._stream_versions[key] = self._stream_version(key) + 1
            self._version += 1

    # --- pure scoring --------------------------------------------------------

    def score_decision(
        self,
        *,
        owner_actor_id: str | None,
        snapshot: JointCauseSnapshot,
        context_features: tuple[float, ...],
        identity_switch_probability: float = 0.0,
        now: datetime,
        view: RegimeLibraryView,
    ) -> RegimeDecision:
        """Compute the competitive stay/create/reactivate/unresolved score.

        Pure: it reads only ``view`` (an immutable library snapshot) and mutates
        nothing.  The decision is bound to its full scoring envelope.
        """

        if not 0.0 <= identity_switch_probability <= 1.0:
            raise ValueError("identity_switch_probability must lie in [0, 1]")
        now = require_aware(now, "now")
        envelope = RegimeScoringEnvelope(
            owner_actor_id=owner_actor_id,
            identity_switch_probability=identity_switch_probability,
            context_features=context_features,
            continue_probability=snapshot.continue_probability,
            transient_noise_probability=snapshot.transient_noise_probability,
            segment_change_probability=snapshot.segment_change_probability,
            segment_cause_posterior=dict(snapshot.segment_cause_posterior),
            snapshot_hash=content_sha256(_snapshot_payload(snapshot)),
            snapshot_timestamp=snapshot.timestamp,
            decision_time=now,
            library_content_hash=view.content_hash,
            library_version=view.library_version,
        )
        token = secrets.token_hex(16)
        with self._lock:
            self._pending_tokens.add(token)
        return self._score_from_envelope(envelope, view, token)

    def _score_from_envelope(
        self,
        envelope: RegimeScoringEnvelope,
        view: RegimeLibraryView,
        decision_token: str,
    ) -> RegimeDecision:
        """Re-score a decision purely from its envelope plus a library view."""

        owner_actor_id = envelope.owner_actor_id
        context_features = envelope.context_features
        identity_switch_probability = envelope.identity_switch_probability
        now = envelope.decision_time
        object_instance_id = view.object_instance_id
        actor_id = view.actor_id
        entries = view.entries
        current_regime_id = view.active_regime_id

        # Decompose the joint cause posterior into the four masses that matter.
        p_continue = envelope.continue_probability
        p_noise = envelope.transient_noise_probability
        p_change = envelope.segment_change_probability
        cause_posterior = envelope.segment_cause_posterior
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

        # Reactivate candidates: first hard-filter the cause-incompatible ones
        # so an incompatible high-similarity stage cannot shadow a compatible
        # stage that still clears the similarity threshold, then rank by a
        # frozen ordering (similarity ↓, last_active_at ↓, regime_id ↑).
        compatible_candidates: list[tuple[RegimeLibraryEntry, float]] = []
        for entry in entries if self.allow_reactivation else ():
            if entry.regime_id == current_regime_id:
                continue
            if entry.actor_id != actor_id:
                continue
            if not _cause_is_compatible(entry.cause_origin, dominant_cause):
                continue
            similarity = _cosine_similarity(context_features, entry.context_fingerprint)
            compatible_candidates.append((entry, similarity))
        compatible_candidates.sort(
            key=lambda item: (
                -item[1],
                -_last_active_seconds(item[0]),
                item[0].regime_id,
            )
        )
        best_match = compatible_candidates[0][0] if compatible_candidates else None
        best_similarity = compatible_candidates[0][1] if compatible_candidates else -1.0
        best_compatible = best_match is not None

        # Habit-change mass that survives the alternative-cause exclusions.
        genuine_habit = p_change * p_habit
        if identity_veto:
            genuine_habit = 0.0

        # Ambiguity: a real change whose cause is not separable.
        ranked = sorted(cause_posterior.values(), reverse=True) if cause_posterior else [0.0]
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
            and best_similarity >= self.similarity_threshold
        ):
            reactivate_logit += genuine_habit * best_similarity
            if not is_owner_stream and p_change * p_actor > 0.0:
                reactivate_logit += p_change * p_actor * best_similarity
        create_logit = 0.0
        if not identity_veto:
            has_compatible_match = (
                best_match is not None and best_similarity >= self.similarity_threshold
            )
            if genuine_habit > 0.0 and not has_compatible_match:
                create_logit += genuine_habit
            if genuine_habit > 0.0 and not entries and p_change >= self.change_threshold:
                create_logit += genuine_habit
            # A guest stream's actor-mixture change may create the *first*
            # ACTOR-origin stage for that stream (so CCRR can later reactivate
            # it without an external module pre-seeding the library).
            genuine_actor = p_change * p_actor
            if not is_owner_stream and genuine_actor > 0.0 and not has_compatible_match:
                create_logit += genuine_actor
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
        created_cause_origin: ChangeCause | None = None
        if kind == RegimeDecisionKind.REACTIVATE:
            if best_match is None:
                raise RuntimeError("reactivate decision requires a matching regime")
            reactivated_regime_id = best_match.regime_id
        elif kind == RegimeDecisionKind.CREATE:
            created_regime_id = f"{actor_id}@{now.isoformat()}@{object_instance_id.hex[:8]}"
            # Stamp the new regime with the cause that created it, so a guest
            # stage is an ACTOR-origin regime and a habit stage a HABIT-origin
            # one (never hard-code HABIT).
            created_cause_origin = (
                dominant_cause
                if dominant_cause in (ChangeCause.HABIT, ChangeCause.ACTOR)
                else ChangeCause.HABIT
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
            object_instance_id=object_instance_id,
            actor_id=actor_id,
            decision_token=decision_token,
            scored_library_version=view.library_version,
            library_content_hash=view.content_hash,
            context_features=context_features,
            context_hash=content_sha256(list(context_features)),
            model_version=self.model_version,
            created_cause_origin=created_cause_origin,
            scoring_envelope=envelope,
            model_config_hash=self.model_config_hash,
            alternative_causes_ruled_out=tuple(ruled_out),
            rationale=rationale,
        )

    def apply_decision(self, decision: RegimeDecision) -> int:
        """Apply a scored decision's side effects under a compare-and-swap.

        The decision carries its own stream key, library content hash, context
        features, and model version; none of these are re-supplied by the
        caller, so a decision scored for ``object A / owner`` cannot be applied
        to ``object B / guest``, and the scored context cannot be swapped at
        apply time.  Under the reactor lock the live hash of the decision's own
        stream is recomputed and compared item by item; any mismatch (stale
        per-stream version, changed contents, changed model/config) raises
        :class:`StaleLibraryError`.
        """

        key = (decision.object_instance_id, decision.actor_id)
        with self._lock:
            if decision.model_config_hash != self.model_config_hash:
                raise StaleLibraryError(
                    "model/config moved since the decision was scored "
                    "(thresholds, default stage, or model version changed)"
                )
            if decision.decision_token not in self._pending_tokens:
                raise ForgedDecisionError("invalid or already-consumed decision token")
            self._pending_tokens.remove(decision.decision_token)
            if decision.scored_library_version != self._stream_version(key):
                raise StaleLibraryError(
                    f"stream version moved (scored against "
                    f"{decision.scored_library_version}, actual "
                    f"{self._stream_version(key)})"
                )
            live_view = self.view(
                object_instance_id=decision.object_instance_id,
                actor_id=decision.actor_id,
            )
            if live_view.content_hash != decision.library_content_hash:
                raise StaleLibraryError("library contents changed since the decision was scored")
            if content_sha256(list(decision.context_features)) != decision.context_hash:
                raise StaleLibraryError("decision context hash is inconsistent")

            # Re-score from the envelope against the live view and compare every
            # scoring-relevant field, so a tampered decision (kind / score /
            # reactivated / created / cause origin) is rejected.
            recomputed = self._score_from_envelope(
                decision.scoring_envelope, live_view, decision.decision_token
            )
            if not _decisions_equal(decision, recomputed):
                raise ForgedDecisionError("decision does not match its scoring envelope (forged)")

            if decision.kind == RegimeDecisionKind.REACTIVATE:
                assert decision.reactivated_regime_id is not None
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
                assert decision.created_regime_id is not None
                assert decision.created_cause_origin is not None
                entry = RegimeLibraryEntry(
                    regime_id=decision.created_regime_id,
                    actor_id=decision.actor_id,
                    object_instance_id=decision.object_instance_id,
                    context_fingerprint=decision.context_features,
                    cause_origin=decision.created_cause_origin,
                    created_at=decision.decision_time,
                    last_active_at=decision.decision_time,
                    activation_count=1,
                )
                self._library.setdefault(key, {})[entry.regime_id] = entry
                self._current_regime[key] = entry.regime_id
            # STAY / UNRESOLVED have no library side effects.
            self._stream_versions[key] = self._stream_version(key) + 1
            self._version += 1
            return self._stream_version(key)

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
        """Convenience: score against a fresh view then apply (mutating)."""

        view = self.view(object_instance_id=object_instance_id, actor_id=actor_id)
        decision = self.score_decision(
            owner_actor_id=owner_actor_id,
            snapshot=snapshot,
            context_features=context_features,
            identity_switch_probability=identity_switch_probability,
            now=now,
            view=view,
        )
        self.apply_decision(decision)
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


def _snapshot_payload(snapshot: JointCauseSnapshot) -> dict:
    """Serialize a ``JointCauseSnapshot`` into a canonical, hashable payload."""

    return {
        "timestamp": snapshot.timestamp,
        "joint_run_length_cause_posterior": {
            f"{run_length}:{cause.value}": probability
            for (run_length, cause), probability in (
                snapshot.joint_run_length_cause_posterior.items()
            )
        },
        "joint_run_length_cause_set_posterior": {
            (
                f"{run_length}:{'+'.join(sorted(cause.value for cause in causes)) or 'initial'}"
            ): probability
            for (run_length, causes), probability in (
                snapshot.joint_run_length_cause_set_posterior.items()
            )
        },
        "continue_probability": snapshot.continue_probability,
        "segment_change_probability": snapshot.segment_change_probability,
        "segment_cause_posterior": {
            cause.value: probability
            for cause, probability in snapshot.segment_cause_posterior.items()
        },
        "segment_cause_set_posterior": {
            "+".join(sorted(cause.value for cause in causes)): probability
            for causes, probability in snapshot.segment_cause_set_posterior.items()
        },
        "active_regime_cause_set_posterior": {
            "+".join(sorted(cause.value for cause in causes)) or "initial": probability
            for causes, probability in snapshot.active_regime_cause_set_posterior.items()
        },
        "active_regime_cause_posterior": {
            cause.value: probability
            for cause, probability in snapshot.active_regime_cause_posterior.items()
        },
        "transient_noise_probability": snapshot.transient_noise_probability,
        "block_reference": {
            cause.value: value for cause, value in snapshot.block_reference.items()
        },
        "beam_size": snapshot.beam_size,
    }


def _decisions_equal(left: RegimeDecision, right: RegimeDecision) -> bool:
    """Field-by-field comparison of the scoring-relevant decision outputs."""

    if left.kind != right.kind:
        return False
    if left.reactivated_regime_id != right.reactivated_regime_id:
        return False
    if left.created_regime_id != right.created_regime_id:
        return False
    if left.created_cause_origin != right.created_cause_origin:
        return False
    if set(left.decision_score) != set(right.decision_score):
        return False
    return all(
        isclose(left.decision_score[kind], right.decision_score[kind], rel_tol=0.0, abs_tol=1e-9)
        for kind in left.decision_score
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


def log_odds(value: float) -> float:
    """Return the log-odds of a probability (exported for tests)."""

    if not 0.0 < value < 1.0:
        raise ValueError("probability must lie strictly inside (0, 1)")
    return log(value / (1.0 - value))
