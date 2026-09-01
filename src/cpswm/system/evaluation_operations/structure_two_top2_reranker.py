"""Visible-only, reversible top-two action reranker for Structure Two.

The full seven-operator Structure-Two runtime remains the evidence producer.
This module adds a deliberately narrow action plane: two antisymmetric heads
may only keep or swap the current top two candidates for search and put-back.
Evaluator truth is used solely to create labels on declared training seeds and
to score calibration/validation traces after inference.
"""

from __future__ import annotations

import json
import math
import random
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import UUID

from cpswm.contracts import (
    ProjectTwoDatasetSplit,
    ProjectTwoEvaluatorStepTruth,
    ProjectTwoReplayEpisode,
    ProjectTwoReplayStep,
)
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ActionCaseMetric,
    ProjectTwoActionBenchmarkV02,
    _Prediction,
)
from cpswm.system.evaluation_operations.structure_two_action_information_upper_bound import (
    _load_frozen_parameters,
    _PredictionTraceState,
    _transition_state,
)
from cpswm.system.evaluation_operations.structure_two_strongest_neighbor_gate import (
    NeighborArm,
    NeighborDesign,
    NeighborFamily,
    _dataset,
    load_frozen_neighbor_design,
)
from cpswm.system.evaluation_operations.structure_two_strongest_neighbor_gate import (
    _state_for_arm as _neighbor_state_for_arm,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.world_model.habits_transitions import ChangeCause

PROTOCOL_ID = "structure-two-reversible-multiaxis-top2-reranker@0.1"
DEFAULT_MANIFEST = Path(
    "configs/project_two_experiments/structure_two_top2_reranker_manifest_v0_1.json"
)
DEFAULT_OUTPUT = Path("artifacts/project_two_v04_development/structure_two_top2_reranker_v0_1.json")

REQUIRED_OPERATOR_RECEIPT_KEYS = frozenset(
    {"opceu", "orrer", "pchmp", "cf_bocpd", "rgrc", "ccrr", "ciav"}
)

# Every feature is location-specific.  Global uncertainty is multiplied by a
# candidate's visible support, so taking card(A)-card(B) remains meaningful.
FEATURE_NAMES = (
    "action_mass",
    "base_mass",
    "observed_now",
    "recency_support",
    "frequency_support",
    "recent_frequency_support",
    "owner_identity_support",
    "nonowner_identity_support",
    "observation_cause_support",
    "actor_cause_support",
    "habit_cause_support",
    "noise_cause_support",
    "regime_change_support",
    "regime_stay_support",
    "unknown_actor_support",
    "reversible_mass_delta",
    "active_ledger_mass",
)


class ActionHead(StrEnum):
    SEARCH = "search"
    PUT_BACK = "put_back"


class RerankDecision(StrEnum):
    KEEP = "keep"
    SWAP = "swap"
    ABSTAIN = "abstain"


@dataclass(frozen=True, slots=True)
class RerankerModelConfig:
    architecture: str
    epochs: int
    learning_rate: float
    l2: float
    counterfactual_horizon: int
    label_semantics: str
    forbidden_inference_inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TopTwoRerankerDesign:
    training_seeds: tuple[int, ...]
    calibration_seeds: tuple[int, ...]
    validation_seeds: tuple[int, ...]
    max_steps: int
    base_profile: str
    model: RerankerModelConfig
    abstention_threshold_candidates: tuple[float, ...]
    source_manifest_sha256: str
    source_manifest_path: Path
    manifest_file_sha256: str


@dataclass(frozen=True, slots=True)
class LocationEvidenceCard:
    location_id: UUID
    feature_values: tuple[float, ...]
    revision_refs: tuple[str, ...]
    ledger_head: str
    operator_receipt_hash: str
    provenance_hash: str

    def as_mapping(self) -> dict[str, float]:
        return dict(zip(FEATURE_NAMES, self.feature_values, strict=True))


@dataclass(frozen=True, slots=True)
class PairwiseSnapshot:
    search_candidates: tuple[UUID, ...]
    put_back_candidates: tuple[UUID, ...]
    cards: Mapping[UUID, LocationEvidenceCard]


@dataclass(frozen=True, slots=True)
class PairwiseTrainingExample:
    head: ActionHead
    feature_deltas: tuple[float, ...]
    label: int
    weight: float


@dataclass(frozen=True, slots=True)
class LinearPairwiseHead:
    weights: tuple[float, ...]
    feature_scales: tuple[float, ...]
    training_example_count: int
    training_loss: float

    def contributions(self, deltas: Sequence[float]) -> tuple[float, ...]:
        if len(deltas) != len(self.weights):
            raise ValueError("pairwise feature width mismatch")
        return tuple(
            weight * float(delta) / scale
            for weight, delta, scale in zip(self.weights, deltas, self.feature_scales, strict=True)
        )

    def score(self, deltas: Sequence[float]) -> float:
        return float(sum(self.contributions(deltas)))


@dataclass(frozen=True, slots=True)
class ReversibleTopTwoModel:
    search: LinearPairwiseHead
    put_back: LinearPairwiseHead
    feature_names: tuple[str, ...]
    config: RerankerModelConfig

    def head(self, action_head: ActionHead) -> LinearPairwiseHead:
        return self.search if action_head is ActionHead.SEARCH else self.put_back

    def payload(self) -> dict[str, Any]:
        return {
            "protocol": PROTOCOL_ID,
            "model_type": self.config.architecture,
            "feature_names": list(self.feature_names),
            "search_head": asdict(self.search),
            "put_back_head": asdict(self.put_back),
            "config": asdict(self.config),
            "inference_boundary": "visible evidence cards only; no evaluator truth",
            "action_authority": "may only keep, swap, or abstain on current top two",
        }

    @property
    def model_hash(self) -> str:
        return str(content_sha256(self.payload()))


@dataclass(frozen=True, slots=True)
class PairwiseDecisionReceipt:
    head: ActionHead
    candidate_a: UUID
    candidate_b: UUID
    card_a_hash: str
    card_b_hash: str
    feature_deltas: tuple[float, ...]
    signed_contributions: tuple[float, ...]
    score: float
    threshold: float
    decision: RerankDecision
    model_hash: str
    receipt_hash: str


@dataclass(slots=True)
class _VisibleLocationHistory:
    step_index: int = 0
    counts: Counter[UUID] = field(default_factory=Counter)
    last_seen: dict[UUID, int] = field(default_factory=dict)
    recent: deque[UUID | None] = field(default_factory=lambda: deque(maxlen=4))
    observed_now: UUID | None = None

    def observe(self, step: ProjectTwoReplayStep) -> None:
        self.step_index += 1
        location = None if step.after is None else step.after.detected_location_id
        self.observed_now = location
        self.recent.append(location)
        if location is not None:
            self.counts[location] += 1
            self.last_seen[location] = self.step_index


@dataclass(frozen=True, slots=True)
class _EpisodeTrace:
    predictions: tuple[_Prediction, ...]
    snapshots: tuple[PairwiseSnapshot | None, ...]
    metric: ActionCaseMetric
    consumed_visible_stream_hash: str
    operator_receipt: Mapping[str, Any]


def _file_sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_reranker_design(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    repository_root: Path | None = None,
) -> TopTwoRerankerDesign:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("top-two reranker manifest protocol mismatch")
    model_payload = payload["model"]
    model = RerankerModelConfig(
        architecture=str(model_payload["architecture"]),
        epochs=int(model_payload["epochs"]),
        learning_rate=float(model_payload["learning_rate"]),
        l2=float(model_payload["l2"]),
        counterfactual_horizon=int(model_payload["counterfactual_horizon"]),
        label_semantics=str(model_payload["label_semantics"]),
        forbidden_inference_inputs=tuple(model_payload["forbidden_inference_inputs"]),
    )
    root = repository_root or manifest_path.resolve().parents[3]
    source = root / str(payload["source_strongest_neighbor_manifest"])
    design = TopTwoRerankerDesign(
        training_seeds=tuple(int(item) for item in payload["training_seeds"]),
        calibration_seeds=tuple(int(item) for item in payload["calibration_seeds"]),
        validation_seeds=tuple(int(item) for item in payload["validation_seeds"]),
        max_steps=int(payload["max_steps"]),
        base_profile=str(payload["base_profile"]),
        model=model,
        abstention_threshold_candidates=tuple(
            float(item) for item in payload["abstention_threshold_candidates"]
        ),
        source_manifest_sha256=str(payload["source_strongest_neighbor_manifest_sha256"]),
        source_manifest_path=source,
        manifest_file_sha256=_file_sha256(manifest_path),
    )
    phases = (
        set(design.training_seeds),
        set(design.calibration_seeds),
        set(design.validation_seeds),
    )
    if any(left & right for index, left in enumerate(phases) for right in phases[index + 1 :]):
        raise ValueError("top-two reranker train/calibration/validation seeds overlap")
    if not all(phases) or design.model.counterfactual_horizon != 1:
        raise ValueError("top-two reranker requires three non-empty phases and H=1 labels")
    if _file_sha256(source) != design.source_manifest_sha256:
        raise ValueError("top-two reranker source manifest hash mismatch")
    source_design = load_frozen_neighbor_design(source)
    if design.validation_seeds != source_design.validation_seeds:
        raise ValueError("top-two reranker must reuse the prior validation seeds exactly")
    if design.max_steps != source_design.max_steps:
        raise ValueError("top-two reranker max steps differ from the source gate")
    if not design.abstention_threshold_candidates:
        raise ValueError("top-two reranker threshold grid is empty")
    if set(FEATURE_NAMES) & set(design.model.forbidden_inference_inputs):
        raise ValueError("forbidden evaluator field appears in reranker features")
    return design


def _candidate_pair(prediction: _Prediction, head: ActionHead) -> tuple[UUID, ...]:
    if head is ActionHead.SEARCH:
        return tuple(dict.fromkeys(prediction.search_order))[:2]
    return tuple(dict.fromkeys((prediction.put_back, *prediction.search_order)))[:2]


def _fresh_belief_and_distribution(state: Any) -> tuple[Any | None, Mapping[UUID, float]]:
    belief = getattr(state, "_belief", None)
    if belief is None:
        return None, {}
    spine = state.spine
    base = spine.action_location_distribution(
        spine.current_snapshot,
        readout=state.action_readout,
    )
    fresh = replace(belief, base_location_distribution=base)
    runtime = getattr(state, "_runtime", None)
    distribution = base if runtime is None else runtime.action_distribution(fresh)
    ledger = getattr(state, "_particle_ledger", None)
    if ledger is not None:
        distribution = ledger.blend(distribution)
    return fresh, distribution


def _revision_refs(state: Any) -> tuple[str, ...]:
    traces = tuple(getattr(state, "revision_action_traces", ()))
    refs: list[str] = []
    for trace in traces[-4:]:
        for name in ("corrected_revision_id", "superseded_revision_id"):
            value = getattr(trace, name, None)
            if value is not None:
                refs.append(str(value))
    return tuple(dict.fromkeys(refs))


def _build_card(
    location: UUID,
    *,
    state: Any,
    belief: Any,
    distribution: Mapping[UUID, float],
    history: _VisibleLocationHistory,
) -> LocationEvidenceCard:
    base_mass = float(belief.base_location_distribution.get(location, 0.0))
    action_mass = float(distribution.get(location, 0.0))
    observed = float(history.observed_now == location)
    age = history.step_index - history.last_seen.get(location, -1000)
    recency = 0.0 if age > history.step_index else 1.0 / (1.0 + max(0, age))
    total = max(1, sum(history.counts.values()))
    frequency = float(history.counts.get(location, 0) / total)
    recent_values = tuple(item for item in history.recent if item is not None)
    recent_frequency = float(
        sum(item == location for item in recent_values) / max(1, len(recent_values))
    )
    owner = float(belief.actor_posterior.get(belief.owner_actor_key, 0.0))
    unknown = float(belief.actor_posterior.get("unknown_actor", 0.0))
    identity = float(belief.identity_target_probability)
    cause = belief.cause_posterior
    regime = float(belief.regime_change_probability)
    location_support = max(observed, recent_frequency)
    ledger = getattr(state, "_particle_ledger", None)
    ledger_distribution = None if ledger is None else getattr(ledger, "active_distribution", None)
    ledger_mass = (
        0.0 if ledger_distribution is None else float(ledger_distribution.get(location, 0.0))
    )
    values = (
        action_mass,
        base_mass,
        observed,
        recency,
        frequency,
        recent_frequency,
        location_support * owner * identity,
        location_support * (1.0 - owner) * identity,
        location_support * float(cause[ChangeCause.OBSERVATION]),
        location_support * float(cause[ChangeCause.ACTOR]),
        location_support * float(cause[ChangeCause.HABIT]),
        location_support * float(cause[ChangeCause.NOISE]),
        location_support * regime,
        location_support * (1.0 - regime),
        location_support * unknown,
        action_mass - base_mass,
        ledger_mass,
    )
    operator_receipt = dict(getattr(state, "operator_retention_receipt", {}))
    refs = _revision_refs(state)
    ledger_head = str(getattr(ledger, "head_hash", "NO_PARTICLE_LEDGER"))
    payload = {
        "location_id": str(location),
        "features": dict(zip(FEATURE_NAMES, values, strict=True)),
        "revision_refs": refs,
        "ledger_head": ledger_head,
        "operator_receipt_hash": content_sha256(operator_receipt),
    }
    return LocationEvidenceCard(
        location_id=location,
        feature_values=tuple(float(value) for value in values),
        revision_refs=refs,
        ledger_head=ledger_head,
        operator_receipt_hash=str(content_sha256(operator_receipt)),
        provenance_hash=str(content_sha256(payload)),
    )


def build_pairwise_snapshot(
    state: Any,
    prediction: _Prediction,
    history: _VisibleLocationHistory,
) -> PairwiseSnapshot | None:
    search = _candidate_pair(prediction, ActionHead.SEARCH)
    put_back = _candidate_pair(prediction, ActionHead.PUT_BACK)
    candidates = tuple(dict.fromkeys((*search, *put_back)))
    if len(search) < 2 or len(put_back) < 2:
        return None
    belief, distribution = _fresh_belief_and_distribution(state)
    if belief is None:
        return None
    cards = {
        location: _build_card(
            location,
            state=state,
            belief=belief,
            distribution=distribution,
            history=history,
        )
        for location in candidates
    }
    return PairwiseSnapshot(search_candidates=search, put_back_candidates=put_back, cards=cards)


def feature_deltas(
    card_a: LocationEvidenceCard,
    card_b: LocationEvidenceCard,
) -> tuple[float, ...]:
    return tuple(
        left - right
        for left, right in zip(card_a.feature_values, card_b.feature_values, strict=True)
    )


def _training_example(
    snapshot: PairwiseSnapshot,
    truth: ProjectTwoEvaluatorStepTruth,
    head: ActionHead,
    *,
    weight: float,
) -> PairwiseTrainingExample | None:
    candidates = (
        snapshot.search_candidates if head is ActionHead.SEARCH else snapshot.put_back_candidates
    )
    if len(candidates) < 2:
        return None
    candidate_a, candidate_b = candidates[:2]
    target = truth.true_location if head is ActionHead.SEARCH else truth.true_owner_habit_location
    regret_a = int(candidate_a != target)
    regret_b = int(candidate_b != target)
    advantage = regret_b - regret_a
    if advantage == 0:
        return None
    return PairwiseTrainingExample(
        head=head,
        feature_deltas=feature_deltas(snapshot.cards[candidate_a], snapshot.cards[candidate_b]),
        label=1 if advantage > 0 else -1,
        weight=float(weight * abs(advantage)),
    )


def _logistic_factor(value: float) -> float:
    if value >= 0.0:
        return math.exp(-value) / (1.0 + math.exp(-value))
    return 1.0 / (1.0 + math.exp(value))


def _train_head(
    examples: Sequence[PairwiseTrainingExample],
    config: RerankerModelConfig,
) -> LinearPairwiseHead:
    if not examples:
        raise ValueError("pairwise reranker head has no training examples")
    width = len(FEATURE_NAMES)
    scales = tuple(
        max(
            1e-6,
            math.sqrt(mean(example.feature_deltas[index] ** 2 for example in examples)),
        )
        for index in range(width)
    )
    normalized = tuple(
        tuple(value / scales[index] for index, value in enumerate(example.feature_deltas))
        for example in examples
    )
    weights = [0.0 for _ in range(width)]
    total_weight = sum(example.weight for example in examples)
    final_loss = 0.0
    for _ in range(config.epochs):
        gradient = [0.0 for _ in range(width)]
        loss = 0.0
        for example, vector in zip(examples, normalized, strict=True):
            margin = example.label * sum(w * x for w, x in zip(weights, vector, strict=True))
            loss += example.weight * math.log1p(math.exp(-max(-40.0, min(40.0, margin))))
            factor = -example.weight * example.label * _logistic_factor(margin)
            for index, value in enumerate(vector):
                gradient[index] += factor * value
        for index in range(width):
            gradient[index] = gradient[index] / total_weight + config.l2 * weights[index]
            weights[index] -= config.learning_rate * gradient[index]
        final_loss = loss / total_weight + 0.5 * config.l2 * sum(w * w for w in weights)
    return LinearPairwiseHead(
        weights=tuple(weights),
        feature_scales=scales,
        training_example_count=len(examples),
        training_loss=float(final_loss),
    )


def train_reranker(
    examples: Sequence[PairwiseTrainingExample],
    config: RerankerModelConfig,
) -> ReversibleTopTwoModel:
    by_head = {
        head: tuple(example for example in examples if example.head is head) for head in ActionHead
    }
    return ReversibleTopTwoModel(
        search=_train_head(by_head[ActionHead.SEARCH], config),
        put_back=_train_head(by_head[ActionHead.PUT_BACK], config),
        feature_names=FEATURE_NAMES,
        config=config,
    )


def pairwise_decision(
    model: ReversibleTopTwoModel,
    head: ActionHead,
    card_a: LocationEvidenceCard,
    card_b: LocationEvidenceCard,
    *,
    threshold: float,
) -> PairwiseDecisionReceipt:
    deltas = feature_deltas(card_a, card_b)
    contributions = model.head(head).contributions(deltas)
    score = float(sum(contributions))
    decision = (
        RerankDecision.ABSTAIN
        if abs(score) <= threshold
        else RerankDecision.KEEP
        if score > 0.0
        else RerankDecision.SWAP
    )
    payload = {
        "head": head.value,
        "candidate_a": str(card_a.location_id),
        "candidate_b": str(card_b.location_id),
        "card_a_hash": card_a.provenance_hash,
        "card_b_hash": card_b.provenance_hash,
        "feature_deltas": deltas,
        "signed_contributions": contributions,
        "score": score,
        "threshold": threshold,
        "decision": decision.value,
        "model_hash": model.model_hash,
    }
    return PairwiseDecisionReceipt(
        head=head,
        candidate_a=card_a.location_id,
        candidate_b=card_b.location_id,
        card_a_hash=card_a.provenance_hash,
        card_b_hash=card_b.provenance_hash,
        feature_deltas=deltas,
        signed_contributions=contributions,
        score=score,
        threshold=threshold,
        decision=decision,
        model_hash=model.model_hash,
        receipt_hash=str(content_sha256(payload)),
    )


def apply_reranker(
    prediction: _Prediction,
    snapshot: PairwiseSnapshot | None,
    model: ReversibleTopTwoModel,
    *,
    search_threshold: float,
    put_back_threshold: float,
) -> tuple[_Prediction, tuple[PairwiseDecisionReceipt, ...]]:
    if snapshot is None:
        return prediction, ()
    receipts: list[PairwiseDecisionReceipt] = []
    search = prediction.search_order
    put_back = prediction.put_back
    for head, threshold in (
        (ActionHead.SEARCH, search_threshold),
        (ActionHead.PUT_BACK, put_back_threshold),
    ):
        candidates = (
            snapshot.search_candidates
            if head is ActionHead.SEARCH
            else snapshot.put_back_candidates
        )
        candidate_a, candidate_b = candidates[:2]
        receipt = pairwise_decision(
            model,
            head,
            snapshot.cards[candidate_a],
            snapshot.cards[candidate_b],
            threshold=threshold,
        )
        receipts.append(receipt)
        if receipt.decision is RerankDecision.SWAP:
            if head is ActionHead.SEARCH:
                search = (candidate_b, candidate_a, *search[2:])
            else:
                put_back = candidate_b
    return (
        _Prediction(
            put_back=put_back,
            search_order=search,
            unknown_probability=prediction.unknown_probability,
        ),
        tuple(receipts),
    )


def _score_predictions(
    evaluator: ProjectTwoActionBenchmarkV02,
    dataset: Any,
    episode: ProjectTwoReplayEpisode,
    predictions: Sequence[_Prediction],
) -> ActionCaseMetric:
    return evaluator.evaluate_custom_state(dataset, episode, _PredictionTraceState(predictions))


def _collect_base_trace(
    evaluator: ProjectTwoActionBenchmarkV02,
    dataset: Any,
    episode: ProjectTwoReplayEpisode,
    family: NeighborFamily,
    *,
    profile: str,
) -> _EpisodeTrace:
    state = _transition_state(
        dataset,
        episode,
        family,
        profile=profile,
        conflict_transition=True,
        ledger="none",
    )
    history = _VisibleLocationHistory()
    predictions: list[_Prediction] = []
    snapshots: list[PairwiseSnapshot | None] = []
    for step in episode.steps:
        history.observe(step)
        state.observe(step)
        prediction = state.predict()
        predictions.append(prediction)
        snapshots.append(build_pairwise_snapshot(state, prediction, history))
        state.feedback(step)
    return _EpisodeTrace(
        predictions=tuple(predictions),
        snapshots=tuple(snapshots),
        metric=_score_predictions(evaluator, dataset, episode, predictions),
        consumed_visible_stream_hash=str(getattr(state, "consumed_visible_stream_hash", "")),
        operator_receipt=dict(getattr(state, "operator_retention_receipt", {})),
    )


def _reranked_metric(
    evaluator: ProjectTwoActionBenchmarkV02,
    dataset: Any,
    episode: ProjectTwoReplayEpisode,
    trace: _EpisodeTrace,
    model: ReversibleTopTwoModel,
    *,
    search_threshold: float,
    put_back_threshold: float,
) -> tuple[ActionCaseMetric, tuple[PairwiseDecisionReceipt, ...], tuple[_Prediction, ...]]:
    predictions: list[_Prediction] = []
    receipts: list[PairwiseDecisionReceipt] = []
    for prediction, snapshot in zip(trace.predictions, trace.snapshots, strict=True):
        revised, step_receipts = apply_reranker(
            prediction,
            snapshot,
            model,
            search_threshold=search_threshold,
            put_back_threshold=put_back_threshold,
        )
        predictions.append(revised)
        receipts.extend(step_receipts)
    return (
        _score_predictions(evaluator, dataset, episode, predictions),
        tuple(receipts),
        tuple(predictions),
    )


def _collect_training_examples(
    design: TopTwoRerankerDesign,
    source_design: NeighborDesign,
    evaluator: ProjectTwoActionBenchmarkV02,
) -> tuple[PairwiseTrainingExample, ...]:
    examples: list[PairwiseTrainingExample] = []
    for family_index, family in enumerate(source_design.families):
        dataset = _dataset(
            family,
            validation_seeds=design.training_seeds,
            test_seeds=(510001 + family_index,),
            max_steps=design.max_steps,
            split_label="top2-reranker-training",
        )
        for episode in dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION):
            trace = _collect_base_trace(
                evaluator, dataset, episode, family, profile=design.base_profile
            )
            truth = dataset.truth_for(episode.episode_id).truth_by_step
            for step, snapshot in zip(episode.steps, trace.snapshots, strict=True):
                if snapshot is None:
                    continue
                target = truth[step.step_id]
                for head in ActionHead:
                    example = _training_example(
                        snapshot,
                        target,
                        head,
                        weight=family.actual_action_cost,
                    )
                    if example is not None:
                        examples.append(example)
                        # Explicit swap augmentation keeps the empirical sample
                        # exactly symmetric as well as the architecture.
                        examples.append(
                            replace(
                                example,
                                feature_deltas=tuple(-value for value in example.feature_deltas),
                                label=-example.label,
                            )
                        )
    if not examples:
        raise ValueError("top-two reranker training examples are empty")
    return tuple(examples)


def _bootstrap_ci(values: Sequence[float], *, draws: int = 4000) -> tuple[float, float]:
    if not values:
        raise ValueError("top-two reranker bootstrap requires cluster values")
    rng = random.Random(f"{PROTOCOL_ID}:validation-seed-cluster-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


def _metric_loss(metric: ActionCaseMetric) -> float:
    return float(metric.cumulative_action_regret / max(1, metric.step_count))


def _threshold_search(
    design: TopTwoRerankerDesign,
    source_design: NeighborDesign,
    evaluator: ProjectTwoActionBenchmarkV02,
    model: ReversibleTopTwoModel,
) -> tuple[tuple[float, float], list[dict[str, Any]]]:
    traces: list[tuple[Any, ProjectTwoReplayEpisode, _EpisodeTrace]] = []
    for family_index, family in enumerate(source_design.families):
        dataset = _dataset(
            family,
            validation_seeds=design.calibration_seeds,
            test_seeds=(520001 + family_index,),
            max_steps=design.max_steps,
            split_label="top2-reranker-calibration",
        )
        for episode in dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION):
            traces.append(
                (
                    dataset,
                    episode,
                    _collect_base_trace(
                        evaluator, dataset, episode, family, profile=design.base_profile
                    ),
                )
            )
    rows: list[dict[str, Any]] = []
    for search_threshold in design.abstention_threshold_candidates:
        for put_back_threshold in design.abstention_threshold_candidates:
            losses: list[float] = []
            interventions = 0
            abstentions = 0
            for dataset, episode, trace in traces:
                metric, receipts, _ = _reranked_metric(
                    evaluator,
                    dataset,
                    episode,
                    trace,
                    model,
                    search_threshold=search_threshold,
                    put_back_threshold=put_back_threshold,
                )
                losses.append(_metric_loss(metric))
                interventions += sum(
                    receipt.decision is RerankDecision.SWAP for receipt in receipts
                )
                abstentions += sum(
                    receipt.decision is RerankDecision.ABSTAIN for receipt in receipts
                )
            rows.append(
                {
                    "search_threshold": search_threshold,
                    "put_back_threshold": put_back_threshold,
                    "action_regret_per_step": mean(losses),
                    "intervention_count": interventions,
                    "abstention_count": abstentions,
                }
            )
    selected = min(
        rows,
        key=lambda row: (
            row["action_regret_per_step"],
            row["intervention_count"],
            -row["search_threshold"],
            -row["put_back_threshold"],
        ),
    )
    return (
        (float(selected["search_threshold"]), float(selected["put_back_threshold"])),
        rows,
    )


def _metric_summary(metrics: Sequence[ActionCaseMetric]) -> dict[str, float]:
    return {
        "episode_count": float(len(metrics)),
        "step_count": float(sum(item.step_count for item in metrics)),
        "action_regret_per_step": mean(_metric_loss(item) for item in metrics),
        "put_back_error_rate": mean(item.put_back_error_rate for item in metrics),
        "search_error_rate": mean(item.search_error_rate for item in metrics),
        "mean_search_path_cost": mean(item.mean_search_path_cost for item in metrics),
    }


def run_top2_reranker(*, repository_root: Path) -> dict[str, Any]:
    design = load_frozen_reranker_design(
        repository_root / DEFAULT_MANIFEST,
        repository_root=repository_root,
    )
    source_design = load_frozen_neighbor_design(design.source_manifest_path)
    brainctl_parameter, frozen_profile = _load_frozen_parameters(repository_root)
    if frozen_profile != design.base_profile:
        raise ValueError("reranker base profile differs from the frozen deterministic source")
    evaluator = ProjectTwoActionBenchmarkV02()
    examples = _collect_training_examples(design, source_design, evaluator)
    model = train_reranker(examples, design.model)
    thresholds, calibration_rows = _threshold_search(design, source_design, evaluator, model)
    search_threshold, put_back_threshold = thresholds

    metrics: dict[str, list[ActionCaseMetric]] = {
        "deterministic": [],
        "reranker": [],
        "brainctl": [],
    }
    family_metrics: dict[str, dict[str, list[ActionCaseMetric]]] = {}
    seed_differences: dict[int, dict[str, list[float]]] = {
        seed: {"reranker_minus_deterministic": [], "reranker_minus_brainctl": []}
        for seed in design.validation_seeds
    }
    decisions: Counter[str] = Counter()
    operator_receipt_gates: list[bool] = []
    antisymmetry_gates: list[bool] = []
    candidate_restriction_gates: list[bool] = []
    visible_stream_gates: list[bool] = []
    family_differences: dict[str, list[float]] = {}

    for family_index, family in enumerate(source_design.families):
        dataset = _dataset(
            family,
            validation_seeds=design.validation_seeds,
            test_seeds=(530001 + family_index,),
            max_steps=design.max_steps,
            split_label="top2-reranker-validation",
        )
        family_metrics[family.family_id] = {key: [] for key in metrics}
        family_differences[family.family_id] = []
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
        for seed, episode in zip(design.validation_seeds, episodes, strict=True):
            base_trace = _collect_base_trace(
                evaluator, dataset, episode, family, profile=design.base_profile
            )
            reranked, receipts, revised_predictions = _reranked_metric(
                evaluator,
                dataset,
                episode,
                base_trace,
                model,
                search_threshold=search_threshold,
                put_back_threshold=put_back_threshold,
            )
            brain_state = _neighbor_state_for_arm(
                dataset,
                episode,
                family,
                NeighborArm.BRAINCTL,
                brainctl_parameter,
                max_physical_verifications=source_design.max_physical_verifications_per_episode,
            )
            brain_predictions: list[_Prediction] = []
            for step in episode.steps:
                brain_state.observe(step)
                brain_predictions.append(brain_state.predict())
                brain_state.feedback(step)
            brain_metric = _score_predictions(evaluator, dataset, episode, brain_predictions)
            base_metric = base_trace.metric
            for key, metric in (
                ("deterministic", base_metric),
                ("reranker", reranked),
                ("brainctl", brain_metric),
            ):
                metrics[key].append(metric)
                family_metrics[family.family_id][key].append(metric)
            rerank_loss = _metric_loss(reranked)
            base_loss = _metric_loss(base_metric)
            brain_loss = _metric_loss(brain_metric)
            seed_differences[seed]["reranker_minus_deterministic"].append(rerank_loss - base_loss)
            seed_differences[seed]["reranker_minus_brainctl"].append(rerank_loss - brain_loss)
            family_differences[family.family_id].append(rerank_loss - base_loss)
            decisions.update(receipt.decision.value for receipt in receipts)
            operator_receipt_gates.append(
                REQUIRED_OPERATOR_RECEIPT_KEYS.issubset(base_trace.operator_receipt)
            )
            visible_stream_gates.append(
                base_trace.consumed_visible_stream_hash
                == str(getattr(brain_state, "consumed_visible_stream_hash", ""))
            )
            for receipt in receipts:
                swapped = pairwise_decision(
                    model,
                    receipt.head,
                    next(
                        snapshot.cards[receipt.candidate_b]
                        for snapshot in base_trace.snapshots
                        if snapshot is not None
                        and receipt.candidate_a in snapshot.cards
                        and receipt.candidate_b in snapshot.cards
                        and snapshot.cards[receipt.candidate_a].provenance_hash
                        == receipt.card_a_hash
                    ),
                    next(
                        snapshot.cards[receipt.candidate_a]
                        for snapshot in base_trace.snapshots
                        if snapshot is not None
                        and receipt.candidate_a in snapshot.cards
                        and receipt.candidate_b in snapshot.cards
                        and snapshot.cards[receipt.candidate_a].provenance_hash
                        == receipt.card_a_hash
                    ),
                    threshold=receipt.threshold,
                )
                antisymmetry_gates.append(abs(receipt.score + swapped.score) <= 1e-10)
            for original, revised in zip(base_trace.predictions, revised_predictions, strict=True):
                search_top2 = set(original.search_order[:2])
                put_top2 = set(_candidate_pair(original, ActionHead.PUT_BACK))
                candidate_restriction_gates.append(
                    revised.search_order[0] in search_top2 and revised.put_back in put_top2
                )

    comparison_cluster_values: dict[str, list[float]] = {}
    comparisons: dict[str, Any] = {}
    for name in ("reranker_minus_deterministic", "reranker_minus_brainctl"):
        cluster_values = [mean(seed_differences[seed][name]) for seed in design.validation_seeds]
        comparison_cluster_values[name] = cluster_values
        comparisons[name] = {
            "mean": mean(cluster_values),
            "confidence_interval_95": _bootstrap_ci(cluster_values),
            "cluster_unit": "validation_seed_across_six_families",
            "cluster_values": cluster_values,
            "negative_favors_reranker": True,
        }
    family_delta = {
        family.family_id: mean(family_differences[family.family_id])
        for family in source_design.families
    }
    family_reports = {
        family.family_id: {
            "role": family.family_role,
            "summaries": {
                key: _metric_summary(family_metrics[family.family_id][key]) for key in metrics
            },
            "reranker_minus_deterministic": family_delta[family.family_id],
        }
        for family in source_design.families
    }
    primary_ci = _bootstrap_ci(comparison_cluster_values["reranker_minus_deterministic"])
    external_ci = _bootstrap_ci(comparison_cluster_values["reranker_minus_brainctl"])
    required_families = set(source_design.required_gain_families)
    required_gain = all(family_delta[name] < 0.0 for name in required_families)
    guardrails = all(
        family_delta[name] <= margin for name, margin in source_design.guardrail_margins.items()
    )
    inference_firewall = all(
        forbidden not in feature
        for forbidden in design.model.forbidden_inference_inputs
        for feature in FEATURE_NAMES
    )
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": "development-only D0 synthetic validation; not paper evidence",
        "sealed_holdout_opened": False,
        "source_manifest_sha256": design.source_manifest_sha256,
        "manifest_file_sha256": design.manifest_file_sha256,
        "training_seeds": list(design.training_seeds),
        "calibration_seeds": list(design.calibration_seeds),
        "validation_seeds": list(design.validation_seeds),
        "training_example_count": len(examples),
        "training_example_count_by_head": dict(Counter(example.head.value for example in examples)),
        "model": model.payload(),
        "model_hash": model.model_hash,
        "selected_thresholds": {
            "search": search_threshold,
            "put_back": put_back_threshold,
        },
        "calibration_grid": calibration_rows,
        "summaries": {key: _metric_summary(value) for key, value in metrics.items()},
        "paired_validation_comparisons": comparisons,
        "family_reports": family_reports,
        "decision_counts": dict(decisions),
        "audit_gates": {
            "all_seven_operator_receipts_retained": all(operator_receipt_gates),
            "pairwise_antisymmetry_exact": all(antisymmetry_gates),
            "top_two_candidate_restriction": all(candidate_restriction_gates),
            "same_visible_stream_as_brainctl": all(visible_stream_gates),
            "inference_feature_firewall": inference_firewall,
            "no_validation_or_sealed_truth_in_model_fit": True,
            "sealed_holdout_unopened": True,
        },
        "development_criteria": {
            "significant_gain_vs_deterministic": primary_ci[1] < 0.0,
            "significant_gain_vs_frozen_brainctl": external_ci[1] < 0.0,
            "gain_in_all_required_families": required_gain,
            "guardrail_families_within_prior_margins": guardrails,
        },
        "limitations": [
            "H=1 labels are exact for the frozen immediate action-regret evaluator "
            "but do not model action-altered future observations.",
            "All evidence is D0 synthetic replay; real embodied learnability remains untested.",
            "The brainctl comparison reuses its previously frozen parameter and is not an "
            "official-code reproduction.",
            "The reranker is a development falsifier, not a paper-level novelty claim.",
        ],
    }
    report["development_gate_passed"] = bool(
        all(report["audit_gates"].values()) and all(report["development_criteria"].values())
    )
    report["content_sha256"] = content_sha256(report)
    return report


def write_top2_reranker(report: Mapping[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def verify_top2_reranker(
    artifact_path: Path,
    *,
    repository_root: Path,
    recompute: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(artifact_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("unexpected top-two reranker artifact protocol")
    expected_hash = payload.pop("content_sha256")
    if content_sha256(payload) != expected_hash:
        raise ValueError("top-two reranker artifact content hash mismatch")
    payload["content_sha256"] = expected_hash
    if payload.get("sealed_holdout_opened") is not False:
        raise ValueError("top-two reranker artifact opened the sealed holdout")
    if recompute:
        fresh = run_top2_reranker(repository_root=repository_root)
        if fresh["content_sha256"] != expected_hash:
            raise ValueError("top-two reranker deterministic recomputation mismatch")
    return payload


__all__ = [
    "DEFAULT_MANIFEST",
    "DEFAULT_OUTPUT",
    "FEATURE_NAMES",
    "PROTOCOL_ID",
    "ActionHead",
    "LinearPairwiseHead",
    "LocationEvidenceCard",
    "PairwiseDecisionReceipt",
    "PairwiseSnapshot",
    "PairwiseTrainingExample",
    "RerankDecision",
    "ReversibleTopTwoModel",
    "TopTwoRerankerDesign",
    "apply_reranker",
    "feature_deltas",
    "load_frozen_reranker_design",
    "pairwise_decision",
    "run_top2_reranker",
    "train_reranker",
    "verify_top2_reranker",
    "write_top2_reranker",
]
