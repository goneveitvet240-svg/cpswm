"""Project-one methods and baselines behind one interface (阶段 4 / 阶段 5).

Every arm — the full decision chain, its ablations, and each baseline —
implements :class:`ProjectOneMethod`.  The runner replays exactly the same
event stream through each of them, so any difference in output is attributable
to the method rather than to the data, the order, or the budget.

Three rules make that attribution honest, and all three are enforced by tests
rather than by convention.

**Prediction timing.**  ``predicted_location_probabilities`` is always computed
from the state *before* the current event is absorbed.  An arm that predicts
after learning from the event it is being scored on has read the answer, and
its log-loss is meaningless.  ``_BaseMethod.observe`` is a template method that
makes the order structural: predict, then decide, then learn.

Reading ``event.observed_location`` before learning is *not* leakage — the
Dirichlet surprise and the RLS residual are by definition "how wrong was the
prior about what we then saw".  They are read off the same pre-event state that
produced the prediction.

**Information parity.**  Every arm sees the full categorical location and the
same ``context_key``.  The BOCPD baseline is a Dirichlet-multinomial
changepoint model over locations, not a binary moved/not-moved detector: a
baseline that sees less than the method under test is not evidence.

**Config identity.**  Every arm carries a frozen config and reports its hash,
including the baselines.  A baseline with hardcoded parameters cannot be
independently tuned in 阶段 7 and cannot be audited afterwards.

Why the chain is rebuilt here instead of driven through
:class:`~cpswm.system.prototype_spine.CorePrototypeSpine`
--------------------------------------------------------
The frozen spine does not expose Dirichlet surprise, RLS residual or the
derived habit signal on its public result, and 阶段 0 requires all three per
step.  An ablation also has to *intervene* on those two channels, which through
the spine would mean editing a frozen module or depending on the call order
inside a 1000-line private method.  So this module composes the same components
the spine composes and uses the signal formulas pinned in
:mod:`.project_one_protocol`, which import the spine's own surprise helper.
"""

from __future__ import annotations

import copy
import random
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from math import isfinite, log, tanh
from typing import Protocol, runtime_checkable
from uuid import NAMESPACE_URL, UUID, uuid5

import numpy as np

from cpswm.contracts import (
    BaseRecordMetadata,
    HabitEvidenceSource,
    HabitLearningEvidence,
    SourceType,
)
from cpswm.system.continual.project_one_regime_loop import AutomaticCFBOCPDCCRRRouter
from cpswm.system.continual.rls import RLSHabitSample, RLSHabitScoreHead, RLSRegimeBank
from cpswm.system.reproducibility import content_sha256
from cpswm.world_model.habits_transitions import (
    CauseSignalFrame,
    ChangeCause,
    HierarchicalDirichletHabitModel,
)

from .project_one_dataset import ProjectOneDatasetRecord
from .project_one_protocol import (
    CategoricalBOCPDConfig,
    ContextFrequencyConfig,
    HistogramResidualCalibrator,
    PersistenceConfig,
    PlattResidualCalibrator,
    ProjectOneDecision,
    ProjectOneProtocolConfig,
    ProjectOneStepTrace,
    ResidualCalibration,
    SignalAblation,
    calibrated_residual,
    habit_signal,
    normalized_predictive_surprise,
)

__all__ = [
    "CategoricalBOCPDMethod",
    "ContextFrequencyMethod",
    "CoreHabitChainMethod",
    "PersistenceMethod",
    "ProjectOneMethod",
    "StepPrediction",
    "build_first_batch",
]

_NS = uuid5(NAMESPACE_URL, "cpswm.project-one-evaluation")
_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def _uuid(kind: str, value: str) -> UUID:
    return uuid5(_NS, f"{kind}:{value}")


def _strict_derangement(values: Sequence[float], *, seed: int) -> list[float]:
    """Permute ``values`` so that no element keeps its own index.

    A seeded shuffle is repaired rather than rejection-sampled: any surviving
    fixed point is swapped with its cyclic neighbour, which removes it without
    creating a new one.  The result is a genuine derangement of the *indices*,
    so the multiset of residuals is preserved exactly.

    Index-level strictness is the right definition here.  Forcing every
    *value* to change would distort the marginal, which is the one thing this
    ablation must keep -- when the residual sequence contains repeats, some
    positions legitimately end up holding an equal value, and the count of
    those is reported in the arm's snapshot rather than engineered away.
    """

    count = len(values)
    if count < 2:
        return list(values)
    order = list(range(count))
    random.Random(seed).shuffle(order)
    for index in range(count):
        if order[index] == index:
            partner = (index + 1) % count
            order[index], order[partner] = order[partner], order[index]
    if any(order[index] == index for index in range(count)):  # pragma: no cover
        raise RuntimeError("failed to build a strict derangement")
    return [values[position] for position in order]


@dataclass(frozen=True, slots=True)
class StepPrediction:
    """One method's output for one event.

    ``predicted_location_probabilities`` is the arm's belief *before* this
    event was absorbed — see the module docstring.  ``decision`` is the frozen
    four-class protocol label.  ``rls_residual`` is ``None`` for methods with no
    residual channel at all, which keeps "the arm reported zero" distinguishable
    from "the arm has no such channel".
    """

    event_id: str
    predicted_location_probabilities: Mapping[str, float]
    change_probability: float
    predicted_cause: str
    predicted_regime_id: str | None
    habit_signal: float
    rls_residual: float | None
    decision: ProjectOneDecision
    trace: ProjectOneStepTrace | None = None

    def __post_init__(self) -> None:
        total = sum(self.predicted_location_probabilities.values())
        if self.predicted_location_probabilities and abs(total - 1.0) > 1e-6:
            raise ValueError("predicted location probabilities must sum to 1")
        for name in ("change_probability", "habit_signal"):
            value = float(getattr(self, name))
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [0, 1]")
        if self.rls_residual is not None and not 0.0 <= self.rls_residual <= 1.0:
            raise ValueError("rls_residual must be in [0, 1] when present")


@runtime_checkable
class ProjectOneMethod(Protocol):
    """The only surface the runner is allowed to touch."""

    name: str

    def reset(self) -> None:
        """Return to the state the method had before any event."""

    def prime(self, records: Sequence[ProjectOneDatasetRecord]) -> None:
        """Optional offline preparation, called once before replay.

        Almost every arm ignores this.  It exists for ablations that are
        *defined* in terms of the whole stream -- a shuffle needs the marginal
        it is shuffling -- and an arm that uses it is by construction not a
        deployable online method.
        """

    def observe(self, event: ProjectOneDatasetRecord) -> StepPrediction:
        """Absorb one event and predict, using no future information."""

    def snapshot(self) -> Mapping[str, object]:
        """Inspectable state summary, for state-size accounting and debugging."""

    def config_payload(self) -> Mapping[str, object]:
        """The exact parameters this arm ran with."""

    def config_hash(self) -> str:
        """Content identity of :meth:`config_payload`."""


class _BaseMethod(ABC):
    """Template method that makes predict-before-learn structural.

    Subclasses implement :meth:`_predict` (pre-event state only) and
    :meth:`_step` (decide, then learn).  Neither the ordering nor the
    ``_last_location`` bookkeeping is left to each subclass to remember.
    """

    def __init__(self, name: str, locations: Sequence[str]) -> None:
        unique = tuple(dict.fromkeys(locations))
        if len(unique) < 2:
            raise ValueError("a project-one method needs at least two candidate locations")
        self.name = name
        self.locations = unique
        self._last_location: str | None = None
        self._step_index = 0

    def reset(self) -> None:
        self._last_location = None
        self._step_index = 0
        self._reset_state()

    @abstractmethod
    def _reset_state(self) -> None: ...

    @abstractmethod
    def _predict(self, event: ProjectOneDatasetRecord) -> dict[str, float]:
        """Location probabilities from the state *before* this event."""

    @abstractmethod
    def _step(self, event: ProjectOneDatasetRecord, prior: Mapping[str, float]) -> StepPrediction:
        """Decide and learn.  ``prior`` is what :meth:`_predict` returned."""

    def observe(self, event: ProjectOneDatasetRecord) -> StepPrediction:
        if event.observed_location not in self.locations:
            raise ValueError(f"location {event.observed_location!r} is outside the candidate set")
        prior = self._predict(event)
        prediction = self._step(event, prior)
        self._last_location = event.observed_location
        self._step_index += 1
        return prediction

    def moved(self, event: ProjectOneDatasetRecord) -> float:
        """1.0 when this event is a location change, 0.0 on the first event."""

        return float(
            self._last_location is not None and event.observed_location != self._last_location
        )

    def snapshot(self) -> Mapping[str, object]:
        return {
            "name": self.name,
            "steps": self._step_index,
            "last_location": self._last_location,
            "config_hash": self.config_hash(),
        }

    def prime(self, records: Sequence[ProjectOneDatasetRecord]) -> None:  # noqa: B027
        """No-op by default; only the shuffled ablation overrides this.

        Deliberately concrete and empty: this is an *optional* hook, not a
        requirement.  Making it abstract would force six arms that have nothing
        to prepare to write a stub apiece.
        """

    @abstractmethod
    def config_payload(self) -> Mapping[str, object]: ...

    def config_hash(self) -> str:
        """Content identity of the **entire** payload.

        Hashing only the protocol config (as v0.2 did) let two arms that differ
        in owner, household, object, candidate locations or shuffle seed share
        one hash -- which is exactly the collision that makes a stored result
        untraceable.
        """

        return content_sha256(dict(self.config_payload()))


# ---------------------------------------------------------------------------
# The method under test, and its ablations
# ---------------------------------------------------------------------------


class CoreHabitChainMethod(_BaseMethod):
    """Dirichlet + RLS + joint CF-BOCPD + CCRR, with an injectable signal ablation.

    The ablation touches exactly two scalars — the Dirichlet surprise and the
    RLS residual — immediately before they are combined into the habit signal.
    Learning, routing, thresholds and every other path stay identical across
    arms, so the arms form a matched pair by construction.
    """

    def __init__(
        self,
        *,
        name: str,
        locations: Sequence[str],
        owner_id: str,
        household_id: str,
        object_id: str,
        config: ProjectOneProtocolConfig,
        shuffle_lag: int = 3,
    ) -> None:
        super().__init__(name, locations)
        if shuffle_lag < 1:
            raise ValueError("shuffle_lag must be at least 1")
        self.config = config
        self.owner_id = owner_id
        self.household_id = household_id
        self.object_id = object_id
        self._household_uuid = _uuid("household", household_id)
        self._object_uuid = _uuid("object", object_id)
        self._location_uuids = tuple(_uuid("location", name) for name in self.locations)
        self._by_uuid = dict(zip(self._location_uuids, self.locations, strict=True))
        self._to_uuid = dict(zip(self.locations, self._location_uuids, strict=True))
        self._embeddings = {
            location: np.eye(len(self.locations), dtype=float)[index]
            for index, location in enumerate(self._location_uuids)
        }
        self._shuffle_lag = shuffle_lag
        self._reset_state()

    # -- lifecycle ---------------------------------------------------------

    def _reset_state(self) -> None:
        loop_config = self.config.loop_config()
        self._habit = HierarchicalDirichletHabitModel(
            locations=self._location_uuids,
            resident_actor_keys=(self.owner_id,),
        )
        dimension = len(self.locations)
        self._regimes = RLSRegimeBank(
            head_factory=lambda: RLSHabitScoreHead(
                context_feature_dim=1,
                location_embedding_dim=dimension,
                forgetting_factor=self.config.forgetting_factor,
                ridge=self.config.rls_regularization,
            )
        )
        self._router = AutomaticCFBOCPDCCRRRouter(
            object_instance_id=self._object_uuid,
            actor_id=self.owner_id,
            owner_actor_id=self.owner_id,
            config=loop_config,
        )
        self._pending: list[tuple[ProjectOneDatasetRecord, float]] = []
        self._histogram = HistogramResidualCalibrator()
        self._platt = PlattResidualCalibrator()
        self._deranged: list[float] = []
        self._derangement_fixed_values = 0
        self._unprimed_shuffle_steps = 0
        self._residual_history: list[float] = []
        #: Set to intervene on exactly one step, for matched-pair experiments
        #: that clone a warm arm and change only the step under study.  Cleared
        #: after it is consumed, so it can never leak into a later step.
        self.pointwise_residual_override: float | None = None

    @property
    def active_regime(self) -> str:
        return self._regimes.active_regime(
            object_instance_id=self._object_uuid,
            actor_id=self.owner_id,
        )

    def config_payload(self) -> Mapping[str, object]:
        return {
            "kind": "core_habit_chain",
            "owner_id": self.owner_id,
            "household_id": self.household_id,
            "object_id": self.object_id,
            "locations": list(self.locations),
            "shuffle_lag": self._shuffle_lag,
            "protocol_config_hash": self.config.config_hash(),
            "ablation": self.config.ablation.value,
            "residual_calibration": self.config.residual_calibration.value,
        }

    # -- ablation ----------------------------------------------------------

    def prime(self, records: Sequence[ProjectOneDatasetRecord]) -> None:
        """Build the strict derangement the shuffled ablation needs.

        Only ``SHUFFLED_RLS`` uses this.  The arm runs a shadow copy of *itself*
        configured as ``FULL`` over the same stream, collects the residual
        sequence it would have produced, and permutes it with a seeded strict
        derangement -- a permutation with no fixed point.

        This is deliberately offline, and that is the honest cost of the arm.
        A causal fixed-lag substitute (what v0.2 did) is not a derangement: the
        residual sequence is full of repeated values, so a lag can map a value
        onto an identical one, and the first ``lag`` steps had no history at all
        and silently degenerated into ``NO_RLS``.  The shuffled arm exists to
        answer "same marginal, wrong pairing", which requires knowing the
        marginal, so it is an ablation and never a deployable method.
        """

        if self.config.ablation is not SignalAblation.SHUFFLED_RLS or not records:
            return

        shadow = self.clone_with(ablation=SignalAblation.FULL)
        # Only start the shadow from scratch when this arm is itself cold.  A
        # warm arm being primed mid-stream must continue from its own state, or
        # the residuals it collects would describe a different model.
        if self._step_index == 0:
            shadow.reset()
        residuals = [
            value
            for record in records
            if (value := shadow.observe(record).rls_residual) is not None
        ]
        self._deranged = _strict_derangement(residuals, seed=self._shuffle_seed(records))
        self._derangement_fixed_values = sum(
            1
            for original, shuffled in zip(residuals, self._deranged, strict=True)
            if original == shuffled
        )

    def _shuffle_seed(self, records: Sequence[ProjectOneDatasetRecord]) -> int:
        """Deterministic per-stream seed, so a rerun reproduces the permutation."""

        return int(content_sha256([records[0].stream_id, len(records)])[:8], 16)

    def _apply_ablation(self, surprise: float, residual: float) -> tuple[float, float]:
        ablation = self.config.ablation
        if ablation is SignalAblation.FULL:
            return surprise, residual
        if ablation is SignalAblation.NO_RLS:
            return surprise, 0.0
        if ablation is SignalAblation.RLS_ONLY:
            return 0.0, residual
        # SHUFFLED_RLS
        if self.pointwise_residual_override is not None:
            substitute = self.pointwise_residual_override
            self.pointwise_residual_override = None
            return surprise, substitute
        if self._step_index < len(self._deranged):
            return surprise, self._deranged[self._step_index]
        # Unprimed (a caller drove observe() directly).  Reporting the real
        # residual would silently turn this into the FULL arm, so the arm keeps
        # its own residual but records that the step was never shuffled.
        self._unprimed_shuffle_steps += 1
        return surprise, residual

    @property
    def residual_history(self) -> tuple[float, ...]:
        """Every residual this arm has computed, in order.

        Exposed so a matched-pair experiment can draw a substitute residual
        from the arm's *own* marginal rather than inventing one.
        """

        return tuple(self._residual_history)

    def clone_with(
        self,
        *,
        ablation: SignalAblation | None = None,
        residual_calibration: ResidualCalibration | None = None,
    ) -> CoreHabitChainMethod:
        """A deep copy whose *read* path is re-configured but whose state is kept.

        This is what makes a matched pair actually matched.  Running two arms
        over the same prefix does **not** give them the same state: the habit
        signal differs from the first step, so the quarantine decisions differ,
        so the two arms learn different things long before the step under study.
        Cloning one primed arm and intervening only on the final step removes
        that confound entirely.

        The RLS bank and Dirichlet counts are carried over untouched -- only the
        ablation and the calibration route, both of which are read at scoring
        time, are replaced.
        """

        clone = copy.deepcopy(self)
        clone.config = replace(
            self.config,
            ablation=self.config.ablation if ablation is None else ablation,
            residual_calibration=(
                self.config.residual_calibration
                if residual_calibration is None
                else residual_calibration
            ),
        )
        clone.name = (
            f"{self.name}->{clone.config.ablation.value}/{clone.config.residual_calibration.value}"
        )
        return clone

    def _residual_from(self, score: float) -> float:
        """Dispatch the score to the configured calibration route.

        Only PLATT needs state, so only PLATT is handled here; the other four
        routes are pure and live in :func:`calibrated_residual`.
        """

        if self.config.residual_calibration is ResidualCalibration.HISTOGRAM:
            return self._histogram.residual(score)
        if self.config.residual_calibration is ResidualCalibration.PLATT:
            return self._platt.residual(score)
        return calibrated_residual(score, self.config.residual_calibration)

    # -- prediction and step ----------------------------------------------

    def _prior_habit(self, event: ProjectOneDatasetRecord) -> Mapping[UUID, float]:
        return self._habit.predict(
            household_id=self._household_uuid,
            person_id=self.owner_id,
            object_instance_id=self._object_uuid,
            context_key=event.context_key,
        ).probabilities

    def _predict(self, event: ProjectOneDatasetRecord) -> dict[str, float]:
        probabilities = self._prior_habit(event)
        return {self._by_uuid[uuid]: probability for uuid, probability in probabilities.items()}

    def _step(self, event: ProjectOneDatasetRecord, prior: Mapping[str, float]) -> StepPrediction:
        location_uuid = self._to_uuid[event.observed_location]

        prior_rls = self._regimes.score_candidates(
            object_instance_id=self._object_uuid,
            actor_id=self.owner_id,
            context_features=np.array([event.context_value], dtype=float),
            candidate_locations=self._location_uuids,
            location_embeddings=self._embeddings,
            regime_id=self.active_regime,
        )

        raw_surprise = normalized_predictive_surprise(
            prior[event.observed_location], len(self.locations)
        )
        raw_residual = self._residual_from(prior_rls[location_uuid])
        self._residual_history.append(raw_residual)
        surprise, residual = self._apply_ablation(raw_surprise, raw_residual)

        signal = habit_signal(
            habit_transition=self.moved(event),
            dirichlet_surprise=surprise,
            rls_residual=residual,
            dirichlet_surprise_weight=self.config.dirichlet_surprise_weight,
            rls_residual_weight=self.config.rls_residual_weight,
        )

        owner_mass = (
            event.observation_quality
            if event.actor_id == self.owner_id
            else 1.0 - event.observation_quality
        )
        ambiguity = 1.0 - event.observation_quality
        location_index = self.locations.index(event.observed_location)
        assessment = self._router.observe(
            frame=CauseSignalFrame(
                timestamp=event.timestamp,
                signals={
                    ChangeCause.OBSERVATION: ambiguity,
                    ChangeCause.ACTOR: 1.0 - owner_mass,
                    ChangeCause.HABIT: signal,
                    ChangeCause.NOISE: ambiguity,
                },
            ),
            state_key=f"{event.observed_location}|{event.context_key}",
            context_features=(
                *(1.0 if index == location_index else 0.0 for index in range(len(self.locations))),
                tanh(event.context_value),
            ),
            owner_probability=owner_mass,
            evidence_source_record_ids=(_uuid("event", event.event_id),),
        )

        if assessment.allow_long_term_write:
            for held, held_weight in self._pending:
                self._commit(held, held_weight)
            self._pending.clear()
            self._commit(event, owner_mass)
        else:
            self._pending.append((event, owner_mass))

        # The empirical calibrator learns from the same one-vs-rest outcome the
        # RLS head is trained on, using the scores that were read *before* this
        # event was absorbed.
        calibrator: HistogramResidualCalibrator | PlattResidualCalibrator | None = None
        if self.config.residual_calibration is ResidualCalibration.HISTOGRAM:
            calibrator = self._histogram
        elif self.config.residual_calibration is ResidualCalibration.PLATT:
            calibrator = self._platt
        if calibrator is not None:
            for candidate, score in prior_rls.items():
                calibrator.update(
                    score,
                    hit=candidate == location_uuid,
                    weight=event.observation_quality,
                )

        decision = ProjectOneDecision.from_conclusion(assessment.conclusion)
        ccrr = (
            assessment.ccrr_decision.kind.value
            if assessment.ccrr_decision is not None
            else "not_required"
        )
        return StepPrediction(
            event_id=event.event_id,
            predicted_location_probabilities=dict(prior),
            change_probability=assessment.change_probability,
            predicted_cause=decision.value,
            predicted_regime_id=assessment.new_regime,
            habit_signal=signal,
            rls_residual=residual,
            decision=decision,
            trace=ProjectOneStepTrace(
                dirichlet_surprise=surprise,
                rls_residual=residual,
                habit_signal=signal,
                change_probability=assessment.change_probability,
                ccrr_decision=ccrr,
                active_regime=assessment.new_regime,
            ),
        )

    def _commit(self, event: ProjectOneDatasetRecord, owner_mass: float) -> None:
        """Write one event into the Dirichlet counts and the RLS head."""

        location_uuid = self._to_uuid[event.observed_location]
        actor_posterior = {self.owner_id: owner_mass, "unknown_actor": 1.0 - owner_mass}
        record_uuid = _uuid("event", event.event_id)
        evidence = HabitLearningEvidence(
            metadata=BaseRecordMetadata(
                record_id=record_uuid,
                schema_name="cpswm.HabitLearningEvidence",
                schema_version="0.1.0",
                household_id=self._household_uuid,
                session_id=_uuid("session", event.stream_id),
                recorded_time=event.timestamp,
                source_type=SourceType.SENSOR,
                source_id=f"project-one-protocol/{event.stream_id}",
                trace_id=_uuid("trace", event.stream_id),
            ),
            object_instance_id=self._object_uuid,
            location_id=location_uuid,
            event_time=event.timestamp,
            context_key=event.context_key,
            actor_posterior=actor_posterior,
            evidence_source=HabitEvidenceSource.DIRECT_OBSERVATION,
            proposed_training_weight=1.0,
            source_record_ids=(record_uuid,),
        )
        self._habit.update(evidence, weight_multiplier=event.observation_quality)
        self._regimes.update(
            RLSHabitSample(
                object_instance_id=self._object_uuid,
                actor_id=self.owner_id,
                context_features=np.array([event.context_value], dtype=float),
                target_location_id=location_uuid,
                candidate_locations=self._location_uuids,
                gate=owner_mass * event.observation_quality,
                regime_id=self.active_regime,
            ),
            self._embeddings,
        )

    def snapshot(self) -> Mapping[str, object]:
        return {
            **super().snapshot(),
            "active_regime": self.active_regime,
            "regime_count": self._regimes.regime_count(),
            "pending_quarantined": len(self._pending),
            "residual_calibration": self.config.residual_calibration.value,
            "derangement_length": len(self._deranged),
            "derangement_unchanged_values": self._derangement_fixed_values,
            "unprimed_shuffle_steps": self._unprimed_shuffle_steps,
        }


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------


class PersistenceMethod(_BaseMethod):
    """Predict the last observed location; call any move a change.

    The floor.  Any method that cannot beat this is not doing useful work.
    """

    def __init__(self, locations: Sequence[str], config: PersistenceConfig | None = None) -> None:
        super().__init__("persistence", locations)
        self.config = config or PersistenceConfig()
        self._reset_state()

    def _reset_state(self) -> None:
        return None

    def config_payload(self) -> Mapping[str, object]:
        return {"kind": "persistence", "confidence": self.config.confidence}

    def _predict(self, event: ProjectOneDatasetRecord) -> dict[str, float]:
        if self._last_location is None:
            return {name: 1.0 / len(self.locations) for name in self.locations}
        spread = (1.0 - self.config.confidence) / (len(self.locations) - 1)
        return {
            name: self.config.confidence if name == self._last_location else spread
            for name in self.locations
        }

    def _step(self, event: ProjectOneDatasetRecord, prior: Mapping[str, float]) -> StepPrediction:
        changed = self.moved(event)
        return StepPrediction(
            event_id=event.event_id,
            predicted_location_probabilities=dict(prior),
            change_probability=changed,
            predicted_cause="habit_change" if changed else "stable",
            predicted_regime_id=None,
            habit_signal=changed,
            rls_residual=None,
            decision=(ProjectOneDecision.HABIT_CHANGE if changed else ProjectOneDecision.STABLE),
        )


class ContextFrequencyMethod(_BaseMethod):
    """Context-conditioned frequency, with surprise as the change signal.

    The baseline that matters most for attribution: same context conditioning
    and same Dirichlet-style smoothing as the full chain, but no RLS residual
    and no regime machinery.
    """

    def __init__(
        self, locations: Sequence[str], config: ContextFrequencyConfig | None = None
    ) -> None:
        super().__init__("context_frequency", locations)
        self.config = config or ContextFrequencyConfig()
        self._reset_state()

    def _reset_state(self) -> None:
        self._counts: dict[str, dict[str, float]] = defaultdict(
            lambda: dict.fromkeys(self.locations, 0.0)
        )

    def config_payload(self) -> Mapping[str, object]:
        return {
            "kind": "context_frequency",
            "alpha": self.config.alpha,
            "change_threshold": self.config.change_threshold,
        }

    def _predict(self, event: ProjectOneDatasetRecord) -> dict[str, float]:
        counts = self._counts[event.context_key]
        total = sum(counts.values()) + self.config.alpha * len(self.locations)
        return {name: (counts[name] + self.config.alpha) / total for name in self.locations}

    def _step(self, event: ProjectOneDatasetRecord, prior: Mapping[str, float]) -> StepPrediction:
        surprise = normalized_predictive_surprise(
            prior[event.observed_location], len(self.locations)
        )
        self._counts[event.context_key][event.observed_location] += event.observation_quality
        decision = (
            ProjectOneDecision.HABIT_CHANGE
            if surprise >= self.config.change_threshold
            else ProjectOneDecision.STABLE
        )
        return StepPrediction(
            event_id=event.event_id,
            predicted_location_probabilities=dict(prior),
            change_probability=surprise,
            predicted_cause=decision.value,
            predicted_regime_id=None,
            habit_signal=surprise,
            rls_residual=None,
            decision=decision,
        )


class CategoricalBOCPDMethod(_BaseMethod):
    """Dirichlet-multinomial BOCPD over locations, conditioned on context.

    Information-matched to the chain arms: the observation is the *location
    category*, and the per-run sufficient statistics are kept per
    ``context_key``, which is the same pooling level the chain's Dirichlet uses.
    A BOCPD that only saw a moved/not-moved bit would be a weakened baseline.

    One readout note, because it looks like a weakened signal and is not.  Under
    a constant hazard ``H`` the Adams-MacKay recursion gives ``P(r_t = 0) = H``
    at every step: the changepoint branch and the growth branch share the same
    per-run predictive, so the normalized run-length-zero mass cancels to the
    hazard exactly.  Reporting that would hand this baseline a flat line by
    construction.  The change signal is therefore the posterior mass on short
    runs (``r <= 1``), which is where a freshly-initialized component's
    advantage actually appears one step after a real change.

    Run-length statistics are recomputed from the retained observation history
    rather than carried as per-hypothesis count dictionaries.  For streams of
    this length that is both cheaper and obviously correct, since a run of
    length ``r`` is exactly the last ``r`` observations.
    """

    def __init__(
        self, locations: Sequence[str], config: CategoricalBOCPDConfig | None = None
    ) -> None:
        super().__init__("categorical_bocpd", locations)
        self.config = config or CategoricalBOCPDConfig()
        self._hazard = 1.0 / self.config.expected_run_length
        self._reset_state()

    def _reset_state(self) -> None:
        self._weights: list[float] = [1.0]
        self._history: list[tuple[str, str]] = []

    def config_payload(self) -> Mapping[str, object]:
        return {
            "kind": "categorical_bocpd",
            "expected_run_length": self.config.expected_run_length,
            "dirichlet_alpha": self.config.dirichlet_alpha,
            "change_threshold": self.config.change_threshold,
            "max_run_length": self.config.max_run_length,
            "context_conditioned": self.config.context_conditioned,
        }

    def _run_predictive(self, run_length: int, event: ProjectOneDatasetRecord) -> float:
        """Dirichlet-multinomial predictive for this event under one run length."""

        alpha = self.config.dirichlet_alpha
        window = self._history[len(self._history) - run_length :] if run_length else []
        if self.config.context_conditioned:
            window = [item for item in window if item[0] == event.context_key]
        hits = sum(1 for _, location in window if location == event.observed_location)
        total = len(window)
        return (hits + alpha) / (total + alpha * len(self.locations))

    def _predict(self, event: ProjectOneDatasetRecord) -> dict[str, float]:
        """Run-length-averaged categorical predictive, before absorbing the event."""

        alpha = self.config.dirichlet_alpha
        mixture = dict.fromkeys(self.locations, 0.0)
        for run_length, weight in enumerate(self._weights):
            if weight <= 0.0:
                continue
            window = self._history[len(self._history) - run_length :] if run_length else []
            if self.config.context_conditioned:
                window = [item for item in window if item[0] == event.context_key]
            total = len(window) + alpha * len(self.locations)
            for name in self.locations:
                hits = sum(1 for _, location in window if location == name)
                mixture[name] += weight * (hits + alpha) / total
        normalizer = sum(mixture.values())
        if normalizer <= 0.0:
            return {name: 1.0 / len(self.locations) for name in self.locations}
        return {name: value / normalizer for name, value in mixture.items()}

    def _step(self, event: ProjectOneDatasetRecord, prior: Mapping[str, float]) -> StepPrediction:
        predictive = [
            self._run_predictive(run_length, event) for run_length in range(len(self._weights))
        ]
        growth = [
            weight * likelihood * (1.0 - self._hazard)
            for weight, likelihood in zip(self._weights, predictive, strict=True)
        ]
        change_mass = sum(
            weight * likelihood * self._hazard
            for weight, likelihood in zip(self._weights, predictive, strict=True)
        )
        weights = [change_mass, *growth]

        total = sum(weights)
        if total <= 0.0:
            weights = [1.0] + [0.0] * (len(weights) - 1)
            total = 1.0
        weights = [weight / total for weight in weights]
        if len(weights) > self.config.max_run_length:
            weights = weights[: self.config.max_run_length]
            renormalizer = sum(weights)
            weights = [weight / renormalizer for weight in weights]

        self._weights = weights
        self._history.append((event.context_key, event.observed_location))
        if len(self._history) > self.config.max_run_length:
            self._history = self._history[-self.config.max_run_length :]

        change_probability = min(1.0, max(0.0, sum(weights[:2])))
        decision = (
            ProjectOneDecision.HABIT_CHANGE
            if change_probability >= self.config.change_threshold
            else ProjectOneDecision.STABLE
        )
        return StepPrediction(
            event_id=event.event_id,
            predicted_location_probabilities=dict(prior),
            change_probability=change_probability,
            predicted_cause=decision.value,
            predicted_regime_id=None,
            habit_signal=change_probability,
            rls_residual=None,
            decision=decision,
        )

    def snapshot(self) -> Mapping[str, object]:
        entropy = -sum(weight * log(weight) for weight in self._weights if weight > 0.0)
        expected_run_length = sum(index * weight for index, weight in enumerate(self._weights))
        return {
            **super().snapshot(),
            "run_length_support": len(self._weights),
            "run_length_entropy": entropy,
            "expected_run_length": expected_run_length,
        }


# ---------------------------------------------------------------------------
# The 阶段 5 first batch
# ---------------------------------------------------------------------------


def build_first_batch(
    *,
    locations: Sequence[str],
    owner_id: str,
    household_id: str,
    object_id: str,
    config: ProjectOneProtocolConfig | None = None,
    bocpd_config: CategoricalBOCPDConfig | None = None,
    frequency_config: ContextFrequencyConfig | None = None,
    persistence_config: PersistenceConfig | None = None,
) -> tuple[ProjectOneMethod, ...]:
    """Full / No-RLS / Shuffled-RLS / RLS-only, plus three baselines.

    Every chain arm receives an otherwise identical config; only
    :attr:`ProjectOneProtocolConfig.ablation` differs, so the arms are matched
    by construction and each carries a distinct ``config_hash``.  Each baseline
    takes its own config object, so 阶段 7 can tune them independently instead
    of inheriting the chain's thresholds.
    """

    base = config or ProjectOneProtocolConfig()
    arms: list[ProjectOneMethod] = []
    for ablation, name in (
        (SignalAblation.FULL, "full"),
        (SignalAblation.NO_RLS, "no_rls"),
        (SignalAblation.SHUFFLED_RLS, "shuffled_rls"),
        (SignalAblation.RLS_ONLY, "rls_only"),
    ):
        arms.append(
            CoreHabitChainMethod(
                name=name,
                locations=locations,
                owner_id=owner_id,
                household_id=household_id,
                object_id=object_id,
                config=replace(base, ablation=ablation),
            )
        )
    arms.append(CategoricalBOCPDMethod(locations, bocpd_config))
    arms.append(ContextFrequencyMethod(locations, frequency_config))
    arms.append(PersistenceMethod(locations, persistence_config))
    return tuple(arms)
