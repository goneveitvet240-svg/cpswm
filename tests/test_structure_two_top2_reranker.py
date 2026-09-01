from __future__ import annotations

import json
from pathlib import Path

from cpswm.system.evaluation_operations.project_two_action_benchmark import _Prediction
from cpswm.system.evaluation_operations.structure_two_top2_reranker import (
    FEATURE_NAMES,
    ActionHead,
    LinearPairwiseHead,
    LocationEvidenceCard,
    PairwiseSnapshot,
    RerankDecision,
    RerankerModelConfig,
    ReversibleTopTwoModel,
    _training_example,
    apply_reranker,
    load_frozen_reranker_design,
    pairwise_decision,
)
from cpswm.system.reproducibility import content_uuid

ROOT = Path(__file__).resolve().parents[1]


def _card(name: str, first: float) -> LocationEvidenceCard:
    location = content_uuid("top2-reranker-test", name)
    values = (first, *(0.0 for _ in FEATURE_NAMES[1:]))
    return LocationEvidenceCard(
        location_id=location,
        feature_values=values,
        revision_refs=("visible-revision",),
        ledger_head="GENESIS",
        operator_receipt_hash="a" * 64,
        provenance_hash=("b" if name == "a" else "c") * 64,
    )


def _model(weight: float = 1.0) -> ReversibleTopTwoModel:
    head = LinearPairwiseHead(
        weights=(weight, *(0.0 for _ in FEATURE_NAMES[1:])),
        feature_scales=tuple(1.0 for _ in FEATURE_NAMES),
        training_example_count=2,
        training_loss=0.1,
    )
    config = RerankerModelConfig(
        architecture="test-antisymmetric",
        epochs=1,
        learning_rate=0.1,
        l2=0.0,
        counterfactual_horizon=1,
        label_semantics="test",
        forbidden_inference_inputs=("true_location",),
    )
    return ReversibleTopTwoModel(head, head, FEATURE_NAMES, config)


def test_pairwise_score_and_feature_contributions_are_exactly_antisymmetric() -> None:
    card_a = _card("a", 0.8)
    card_b = _card("b", 0.2)
    model = _model()

    forward = pairwise_decision(model, ActionHead.SEARCH, card_a, card_b, threshold=0.0)
    reverse = pairwise_decision(model, ActionHead.SEARCH, card_b, card_a, threshold=0.0)

    assert forward.score == -reverse.score
    assert forward.feature_deltas == tuple(-value for value in reverse.feature_deltas)
    assert forward.signed_contributions == tuple(-value for value in reverse.signed_contributions)
    assert forward.decision is RerankDecision.KEEP
    assert reverse.decision is RerankDecision.SWAP


def test_action_plane_can_only_swap_current_top_two_and_heads_are_independent() -> None:
    card_a = _card("a", 0.2)
    card_b = _card("b", 0.8)
    third = content_uuid("top2-reranker-test", "third")
    prediction = _Prediction(
        put_back=card_a.location_id,
        search_order=(card_a.location_id, card_b.location_id, third),
    )
    snapshot = PairwiseSnapshot(
        search_candidates=(card_a.location_id, card_b.location_id),
        put_back_candidates=(card_a.location_id, card_b.location_id),
        cards={card_a.location_id: card_a, card_b.location_id: card_b},
    )

    revised, receipts = apply_reranker(
        prediction,
        snapshot,
        _model(),
        search_threshold=0.0,
        put_back_threshold=100.0,
    )

    assert revised.search_order == (card_b.location_id, card_a.location_id, third)
    assert revised.put_back == card_a.location_id
    assert {receipt.decision for receipt in receipts} == {
        RerankDecision.SWAP,
        RerankDecision.ABSTAIN,
    }
    assert set(revised.search_order) == set(prediction.search_order)


def test_training_label_uses_task_specific_training_truth_only() -> None:
    card_a = _card("a", 0.7)
    card_b = _card("b", 0.3)
    snapshot = PairwiseSnapshot(
        search_candidates=(card_a.location_id, card_b.location_id),
        put_back_candidates=(card_a.location_id, card_b.location_id),
        cards={card_a.location_id: card_a, card_b.location_id: card_b},
    )
    from cpswm.contracts import ProjectTwoEvaluatorStepTruth

    truth = ProjectTwoEvaluatorStepTruth.model_construct(
        true_actor="owner",
        true_mechanism="direct_relocation",
        true_location=card_b.location_id,
        true_owner_habit_location=card_a.location_id,
    )

    search = _training_example(snapshot, truth, ActionHead.SEARCH, weight=1.0)
    put_back = _training_example(snapshot, truth, ActionHead.PUT_BACK, weight=1.0)

    assert search is not None and search.label == -1
    assert put_back is not None and put_back.label == 1


def test_manifest_reuses_prior_validation_without_opening_sealed_holdout() -> None:
    design = load_frozen_reranker_design(
        ROOT / "configs/project_two_experiments/structure_two_top2_reranker_manifest_v0_1.json",
        repository_root=ROOT,
    )
    payload = json.loads(
        (
            ROOT / "configs/project_two_experiments/structure_two_top2_reranker_manifest_v0_1.json"
        ).read_text(encoding="utf-8")
    )

    assert set(design.training_seeds).isdisjoint(design.calibration_seeds)
    assert set(design.training_seeds).isdisjoint(design.validation_seeds)
    assert set(design.calibration_seeds).isdisjoint(design.validation_seeds)
    assert payload["sealed_holdout_opened"] is False
    assert all(
        forbidden not in feature
        for forbidden in design.model.forbidden_inference_inputs
        for feature in FEATURE_NAMES
    )
