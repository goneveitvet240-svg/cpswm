"""Direct CHEH baselines used to test revision and mutual exclusion claims."""

from __future__ import annotations

from itertools import permutations
from math import isclose, log
from uuid import UUID

from pydantic import Field, model_validator

from cpswm.contracts import (
    EventMechanism,
    EventType,
    ObservationDetectionResult,
    ObservationOutcome,
)
from cpswm.contracts.base import ContractModel, Probability
from cpswm.system.reproducibility import content_uuid

from .contracts import EventChainHypothesis, HiddenEventStep
from .engine import CounterfactualEventHypergraphEngine


class Top1EventGraphPrediction(ContractModel):
    """A committed event chain with no alternatives or later revision state."""

    responsible_actor_key: str = Field(min_length=1)
    steps: tuple[HiddenEventStep, ...] = Field(min_length=2)
    source_record_ids: tuple[UUID, ...] = Field(min_length=2)
    model_version: str = Field(min_length=1)


class IndependentEventCandidate(ContractModel):
    """One independently scored chain; scores need not be mutually exclusive."""

    responsible_actor_key: str = Field(min_length=1)
    steps: tuple[HiddenEventStep, ...] = Field(min_length=2)
    independent_confidence: Probability
    source_record_ids: tuple[UUID, ...] = Field(min_length=2)


class IndependentEventCandidatePrediction(ContractModel):
    candidates: tuple[IndependentEventCandidate, ...] = Field(min_length=2)
    model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_independence(self) -> IndependentEventCandidatePrediction:
        total = sum(item.independent_confidence for item in self.candidates)
        if isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError(
                "independent baseline confidences must not masquerade as a normalized posterior"
            )
        return self


class CompatibleEventSequence(ContractModel):
    """One logically possible sequence retained without a probabilistic ranking."""

    responsible_actor_key: str = Field(min_length=1)
    steps: tuple[HiddenEventStep, ...] = Field(min_length=2)
    explanation_code: str = Field(min_length=1)
    source_record_ids: tuple[UUID, UUID]


class CompatibleSequenceBeliefUpdatePrediction(ContractModel):
    """All endpoint-compatible sequences and facts entailed by every sequence."""

    possible_sequences: tuple[CompatibleEventSequence, ...] = Field(min_length=2)
    entailed_responsible_actor_key: str | None = None
    model_version: str = Field(min_length=1)


class AMGConstrainedMAPPrediction(ContractModel):
    """One globally consistent MAP parse, as in the 2012 AMG comparison target."""

    selected_sequence: CompatibleEventSequence
    maximizing_responsible_actor_keys: tuple[str, ...] = Field(min_length=1)
    map_tie_count: int = Field(ge=1)
    log_unnormalized_posterior: float
    candidate_count: int = Field(ge=1)
    model_version: str = Field(min_length=1)


class Top1EventGraphBaseline:
    """Commit immediately to the MAP chain and discard all alternatives."""

    model_version = "top1-event-graph@0.1"

    def predict(
        self,
        *,
        before: ObservationDetectionResult,
        after: ObservationDetectionResult,
        actor_prior: dict[str, float],
    ) -> Top1EventGraphPrediction:
        history = CounterfactualEventHypergraphEngine().branch(
            before=before,
            after=after,
            actor_prior=actor_prior,
            unresolved_probability=0.0,
            handoff_fraction=0.0,
        )
        selected = history.latest.map_hypothesis
        assert selected is not None
        return Top1EventGraphPrediction(
            responsible_actor_key=selected.responsible_actor_key,
            steps=selected.steps,
            source_record_ids=selected.source_record_ids,
            model_version=self.model_version,
        )


class IndependentEventCandidateBaseline:
    """Keep chains independently but omit exclusivity, revision, and retraction."""

    model_version = "independent-event-candidates@0.1"

    def predict(
        self,
        *,
        before: ObservationDetectionResult,
        after: ObservationDetectionResult,
        actor_confidence: dict[str, float],
    ) -> IndependentEventCandidatePrediction:
        actor_count = len(actor_confidence)
        actor_prior = {actor: 1.0 / actor_count for actor in actor_confidence}
        history = CounterfactualEventHypergraphEngine().branch(
            before=before,
            after=after,
            actor_prior=actor_prior,
            unresolved_probability=0.0,
            handoff_fraction=0.0,
        )
        by_actor: dict[str, EventChainHypothesis] = {
            item.responsible_actor_key: item for item in history.latest.hypotheses
        }
        # Each candidate is scored as a separate binary plausibility.  A 0.2
        # background floor makes the intentional non-normalization explicit.
        candidates = tuple(
            IndependentEventCandidate(
                responsible_actor_key=actor,
                steps=by_actor[actor].steps,
                independent_confidence=0.2 + 0.8 * confidence,
                source_record_ids=by_actor[actor].source_record_ids,
            )
            for actor, confidence in sorted(actor_confidence.items())
        )
        return IndependentEventCandidatePrediction(
            candidates=candidates,
            model_version=self.model_version,
        )


class BernertRamparany2021SequenceBaseline:
    """Single-gap object-relocation adaptation of Bernert & Ramparany (2021).

    The source algorithm explores every event sequence compatible with prior
    beliefs and consecutive observations, then queries facts that hold in all
    or at least one consistent belief node.  This adaptation preserves that
    all-compatible-sequences semantics for a before/after object-location gap.
    It deliberately has no learned posterior, late-evidence revision history,
    unknown-resident model, or provenance-aware consolidation.
    """

    model_version = "bernert-ramparany-2021-object-relocation-adaptation@0.1"

    def predict(
        self,
        *,
        before: ObservationDetectionResult,
        after: ObservationDetectionResult,
        known_actor_keys: tuple[str, ...],
    ) -> CompatibleSequenceBeliefUpdatePrediction:
        sequences = _enumerate_compatible_sequences(
            before=before,
            after=after,
            known_actor_keys=known_actor_keys,
            namespace=self.model_version,
        )
        responsible_actors = {item.responsible_actor_key for item in sequences}
        entailed_actor = next(iter(responsible_actors)) if len(responsible_actors) == 1 else None
        return CompatibleSequenceBeliefUpdatePrediction(
            possible_sequences=sequences,
            entailed_responsible_actor_key=entailed_actor,
            model_version=self.model_version,
        )


class DamenHogg2012AMGGlobalMAPBaseline:
    """Object-relocation adaptation of Damen & Hogg's constrained AMG MAP.

    Candidate parse trees cover the endpoint detections, obey the physical
    event grammar and prevent one actor role from being assigned inconsistently
    inside a chain.  Each true event contributes a likelihood factor and the
    globally consistent parse with maximum unnormalized posterior is returned.
    This is a direct domain adaptation, not a reproduction of their video
    detectors, learned half-Gaussian likelihoods, RJMCMC-SA, or IP solver.
    """

    model_version = "damen-hogg-2012-amg-object-relocation-map-adaptation@0.1"

    def predict(
        self,
        *,
        before: ObservationDetectionResult,
        after: ObservationDetectionResult,
        actor_event_likelihoods: dict[str, float],
        direct_event_likelihood: float,
        handoff_event_likelihood: float,
        handoff_role_likelihoods: dict[tuple[str, str], float] | None = None,
        allow_unknown_actor_roles: bool = False,
    ) -> AMGConstrainedMAPPrediction:
        if not allow_unknown_actor_roles and set(actor_event_likelihoods) == {"unknown_actor"}:
            raise ValueError("AMG baseline requires at least one known actor")
        _validate_open_probabilities(actor_event_likelihoods, "actor_event_likelihoods")
        _validate_open_probabilities(
            {
                "direct_relocation": direct_event_likelihood,
                "handoff_relocation": handoff_event_likelihood,
            },
            "event_type_likelihoods",
        )
        actor_keys = tuple(
            sorted(
                actor_event_likelihoods
                if allow_unknown_actor_roles
                else (actor for actor in actor_event_likelihoods if actor != "unknown_actor")
            )
        )
        if handoff_role_likelihoods is not None:
            expected_roles = set(permutations(actor_keys, 2))
            if set(handoff_role_likelihoods) != expected_roles:
                raise ValueError(
                    "handoff_role_likelihoods must cover every ordered known-actor pair"
                )
            _validate_open_probabilities(
                {
                    f"{actor}->{recipient}": likelihood
                    for (actor, recipient), likelihood in handoff_role_likelihoods.items()
                },
                "handoff_role_likelihoods",
            )
        sequences = _enumerate_compatible_sequences(
            before=before,
            after=after,
            known_actor_keys=actor_keys,
            namespace=self.model_version,
            allow_unknown_actor=allow_unknown_actor_roles,
        )

        def score(sequence: CompatibleEventSequence) -> float:
            if sequence.explanation_code == "direct_relocation":
                return _log_odds(direct_event_likelihood) + _log_odds(
                    actor_event_likelihoods[sequence.responsible_actor_key]
                )
            initial_actor = sequence.steps[0].actor_key
            role_score = (
                _log_odds(handoff_role_likelihoods[(initial_actor, sequence.responsible_actor_key)])
                if handoff_role_likelihoods is not None
                else 0.0
            )
            return (
                _log_odds(handoff_event_likelihood)
                + _log_odds(actor_event_likelihoods[initial_actor])
                + _log_odds(actor_event_likelihoods[sequence.responsible_actor_key])
                + role_score
            )

        scored = tuple((score(sequence), sequence) for sequence in sequences)
        best_score, selected = max(
            scored,
            key=lambda item: (
                item[0],
                item[1].explanation_code,
                tuple(step.actor_key for step in item[1].steps),
            ),
        )
        maximizing_sequences = tuple(
            sequence for value, sequence in scored if isclose(value, best_score, abs_tol=1e-12)
        )
        maximizing_actor_keys = tuple(
            dict.fromkeys(sequence.responsible_actor_key for sequence in maximizing_sequences)
        )
        return AMGConstrainedMAPPrediction(
            selected_sequence=selected,
            maximizing_responsible_actor_keys=maximizing_actor_keys,
            map_tie_count=len(maximizing_sequences),
            log_unnormalized_posterior=best_score,
            candidate_count=len(sequences),
            model_version=self.model_version,
        )


class DamenHogg2012AMGMatchedEvidenceBaseline(DamenHogg2012AMGGlobalMAPBaseline):
    """Deliberately strengthened AMG adaptation for a fair ORRER death test.

    It receives the same actor, mechanism, and ordered-role likelihoods as
    ORRER and is allowed to enumerate an explicit ``unknown_actor`` token in
    either handoff role.  These extensions are a generous matched comparator,
    not claims about functionality implemented in the 2012 source system.
    """

    model_version = "damen-hogg-2012-amg-matched-open-world-evidence@0.1"

    def predict_matched(
        self,
        *,
        before: ObservationDetectionResult,
        after: ObservationDetectionResult,
        actor_event_likelihoods: dict[str, float],
        mechanism_likelihoods: dict[EventMechanism, float],
        handoff_role_likelihoods: dict[tuple[str, str], float],
    ) -> AMGConstrainedMAPPrediction:
        required = {
            EventMechanism.DIRECT_RELOCATION,
            EventMechanism.HANDOFF_RELOCATION,
        }
        if not required.issubset(mechanism_likelihoods):
            raise ValueError("matched AMG mechanism likelihoods require direct and handoff")
        return super().predict(
            before=before,
            after=after,
            actor_event_likelihoods=actor_event_likelihoods,
            direct_event_likelihood=mechanism_likelihoods[EventMechanism.DIRECT_RELOCATION],
            handoff_event_likelihood=mechanism_likelihoods[EventMechanism.HANDOFF_RELOCATION],
            handoff_role_likelihoods=handoff_role_likelihoods,
            allow_unknown_actor_roles=True,
        )


def _validate_endpoints(
    before: ObservationDetectionResult,
    after: ObservationDetectionResult,
) -> None:
    if before.outcome != ObservationOutcome.DETECTED:
        raise ValueError("before endpoint must be detected")
    if after.outcome != ObservationOutcome.DETECTED:
        raise ValueError("after endpoint must be detected")
    if before.detected_object_instance_id != after.detected_object_instance_id:
        raise ValueError("endpoints must concern the same object")
    if before.detected_location_id == after.detected_location_id:
        raise ValueError("baseline requires an observed location transition")
    if before.detection_time is None or after.detection_time is None:
        raise ValueError("detected endpoints require times")
    if after.detection_time <= before.detection_time:
        raise ValueError("after endpoint must follow before endpoint")


def _enumerate_compatible_sequences(
    *,
    before: ObservationDetectionResult,
    after: ObservationDetectionResult,
    known_actor_keys: tuple[str, ...],
    namespace: str,
    allow_unknown_actor: bool = False,
) -> tuple[CompatibleEventSequence, ...]:
    _validate_endpoints(before, after)
    if len(known_actor_keys) < 2:
        raise ValueError("compatible-sequence baselines require at least two known actors")
    if len(set(known_actor_keys)) != len(known_actor_keys):
        raise ValueError("known actor keys must be unique")
    if any(
        not actor.strip() or (actor == "unknown_actor" and not allow_unknown_actor)
        for actor in known_actor_keys
    ):
        raise ValueError("2021/2012 adaptations assume a closed set of known actors")

    assert before.detected_object_instance_id is not None
    assert before.detected_location_id is not None
    assert before.detection_time is not None
    assert after.detected_location_id is not None
    assert after.detection_time is not None
    source_ids = (before.metadata.record_id, after.metadata.record_id)
    specifications: list[
        tuple[
            str,
            str,
            tuple[tuple[EventType, str, str | None], ...],
        ]
    ] = []
    for actor_key in sorted(known_actor_keys):
        specifications.append(
            (
                actor_key,
                "direct_relocation",
                (
                    (EventType.PICK_UP, actor_key, None),
                    (EventType.CARRY, actor_key, None),
                    (EventType.PLACE, actor_key, None),
                ),
            )
        )
    for actor_key, handoff_recipient_key in permutations(sorted(known_actor_keys), 2):
        specifications.append(
            (
                handoff_recipient_key,
                "handoff_relocation",
                (
                    (EventType.PICK_UP, actor_key, None),
                    (EventType.CARRY, actor_key, None),
                    (EventType.TRANSFER, actor_key, handoff_recipient_key),
                    (EventType.PLACE, handoff_recipient_key, None),
                ),
            )
        )

    interval = after.detection_time - before.detection_time
    sequences = []
    for responsible_actor, explanation_code, step_specs in specifications:
        steps = []
        for sequence_no, (event_type, actor_key, step_recipient_key) in enumerate(step_specs):
            event_time = before.detection_time + interval * (
                (sequence_no + 1) / (len(step_specs) + 1)
            )
            source_location_id = (
                before.detected_location_id
                if event_type in {EventType.PICK_UP, EventType.CARRY}
                else None
            )
            destination_location_id = (
                after.detected_location_id
                if event_type in {EventType.CARRY, EventType.PLACE}
                else None
            )
            identity = {
                "namespace": namespace,
                "source_ids": source_ids,
                "explanation_code": explanation_code,
                "sequence_no": sequence_no,
                "event_type": event_type,
                "actor_key": actor_key,
                "recipient_actor_key": step_recipient_key,
            }
            steps.append(
                HiddenEventStep(
                    step_id=content_uuid("baseline-hidden-event-step", identity),
                    sequence_no=sequence_no,
                    event_type=event_type,
                    actor_key=actor_key,
                    recipient_actor_key=step_recipient_key,
                    object_instance_id=before.detected_object_instance_id,
                    source_location_id=source_location_id,
                    destination_location_id=destination_location_id,
                    event_time=event_time,
                )
            )
        sequences.append(
            CompatibleEventSequence(
                responsible_actor_key=responsible_actor,
                steps=tuple(steps),
                explanation_code=explanation_code,
                source_record_ids=source_ids,
            )
        )
    return tuple(sequences)


def _validate_open_probabilities(values: dict[str, float], name: str) -> None:
    if not values or any(not key.strip() for key in values):
        raise ValueError(f"{name} requires non-empty keys")
    if any(value <= 0.0 or value >= 1.0 for value in values.values()):
        raise ValueError(f"{name} probabilities must lie strictly inside (0, 1)")


def _log_odds(probability: float) -> float:
    return log(probability / (1.0 - probability))
