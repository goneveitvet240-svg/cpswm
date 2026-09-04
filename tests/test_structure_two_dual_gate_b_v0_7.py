from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from cpswm.system.evaluation_operations.structure_two_dual_gate_b_v0_7 import (
    ACTION_SCHEMA_ID,
    ACTION_SUPPORT,
    ACTION_SUPPORT_MANIFEST_SHA256,
    BELIEF_SCHEMA_ID,
    BELIEF_SUPPORT,
    BELIEF_SUPPORT_MANIFEST_SHA256,
    CANONICAL_COMPONENT_IDS,
    CANONICAL_MECHANISM_EVENTS,
    EXPECTED_ARMS,
    PROTOCOL_STATUS,
    SUPERSEDED_BY_PROTOCOL_ID,
    ActionSelectionRule,
    BudgetEnvelope,
    CanonicalProbabilityDistribution,
    DualGateArmTrace,
    DualGateComparison,
    DualGateEpisode,
    DualGateStep,
    InformationSetBinding,
    MechanismReceipt,
    MechanismRequirement,
    ReadoutStage,
    load_frozen_protocol_v0_7,
    score_dual_gate_b_v0_7_diagnostic,
    score_frozen_dual_gate_b_v0_7_diagnostic,
    semantic_trace_sha256,
    validate_frozen_protocol_payload_v0_7,
)

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/project_two_experiments/structure_two_gate_b_v0_7.json"
ACTION_A, ACTION_B = ACTION_SUPPORT[:2]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _distribution(
    schema_id: str,
    probabilities: tuple[float, ...],
    support: tuple[str, ...] | None = None,
) -> CanonicalProbabilityDistribution:
    canonical_support = BELIEF_SUPPORT if schema_id == BELIEF_SCHEMA_ID else ACTION_SUPPORT
    if support is None:
        support = canonical_support
        if len(probabilities) == 2:
            probabilities = probabilities + (0.0,) * (len(canonical_support) - 2)
    return CanonicalProbabilityDistribution(
        schema_id=schema_id,
        support=support,
        probabilities=probabilities,
    )


def _budget(*, compute: int = 100) -> BudgetEnvelope:
    return BudgetEnvelope(
        compute_unit_limit=compute,
        active_observation_limit=2,
        physical_verification_limit=1,
        action_cost_limit=3.0,
        privacy_cost_limit=1.0,
    )


def _step(
    arm: str,
    index: int,
    *,
    belief: tuple[float, float],
    action: tuple[float, float],
    selected_action: str,
    event: str,
    component: str,
    information_tag: str = "common",
    budget: BudgetEnvelope | None = None,
    stage: ReadoutStage = ReadoutStage.PRE_ACTION_PRE_EVALUATOR_TRUTH,
    truth_accessed: bool = False,
    receipts: tuple[MechanismReceipt, ...] | None = None,
) -> DualGateStep:
    default_receipt = MechanismReceipt(
        event=event,
        component_id=component,
        input_state_sha256=_sha(f"{arm}:{index}:before"),
        output_state_sha256=_sha(f"{arm}:{index}:after"),
    )
    return DualGateStep(
        step_id=f"step-{index}",
        information_set=InformationSetBinding(
            visible_input_sha256=_sha(f"{information_tag}:input:{index}"),
            visible_history_sha256=_sha(f"{information_tag}:history:{index}"),
            observation_policy_sha256=_sha("common-observation-policy"),
        ),
        budget=budget or _budget(),
        readout_stage=stage,
        evaluator_truth_accessed=truth_accessed,
        belief=_distribution(BELIEF_SCHEMA_ID, belief),
        action_policy=_distribution(ACTION_SCHEMA_ID, action),
        selected_action=selected_action,
        mechanism_receipts=(default_receipt,) if receipts is None else receipts,
    )


def _trace(
    arm: str,
    *,
    belief: tuple[float, float],
    action: tuple[float, float],
    selected_action: str,
    event: str,
    component: str,
    metadata: tuple[tuple[str, str], ...] = (),
    information_tag: str = "common",
    budget: BudgetEnvelope | None = None,
    stage: ReadoutStage = ReadoutStage.PRE_ACTION_PRE_EVALUATOR_TRUTH,
    truth_accessed: bool = False,
    receipts: tuple[MechanismReceipt, ...] | None = None,
) -> DualGateArmTrace:
    return DualGateArmTrace(
        arm=arm,
        episodes=(
            DualGateEpisode(
                episode_id="episode-1",
                steps=tuple(
                    _step(
                        arm,
                        index,
                        belief=belief,
                        action=action,
                        selected_action=selected_action,
                        event=event,
                        component=component,
                        information_tag=information_tag,
                        budget=budget,
                        stage=stage,
                        truth_accessed=truth_accessed,
                        receipts=receipts,
                    )
                    for index in range(4)
                ),
            ),
        ),
        metadata=metadata,
    )


def _requirements() -> tuple[MechanismRequirement, ...]:
    return (
        MechanismRequirement(
            arm="candidate",
            required_event_components=(("candidate-update", "candidate:core"),),
            min_step_fraction=0.25,
            min_episode_fraction=1.0,
        ),
        MechanismRequirement(
            arm="baseline",
            required_event_components=(("baseline-update", "baseline:core"),),
            min_step_fraction=0.25,
            min_episode_fraction=1.0,
        ),
    )


def _comparison() -> DualGateComparison:
    return DualGateComparison(
        comparison_id="registered-pair",
        domain="same scientific question",
        left_arm="candidate",
        right_arm="baseline",
    )


def _score(
    candidate: DualGateArmTrace,
    baseline: DualGateArmTrace,
    *,
    requirements: tuple[MechanismRequirement, ...] | None = None,
) -> dict[str, object]:
    return score_dual_gate_b_v0_7_diagnostic(
        (candidate, baseline),
        expected_arms=("candidate", "baseline"),
        comparison_pairs=(_comparison(),),
        mechanism_requirements=requirements or _requirements(),
    )


def _candidate() -> DualGateArmTrace:
    return _trace(
        "candidate",
        belief=(0.9, 0.1),
        action=(0.9, 0.1),
        selected_action=ACTION_A,
        event="candidate-update",
        component="candidate:core",
    )


def _baseline() -> DualGateArmTrace:
    return _trace(
        "baseline",
        belief=(0.1, 0.9),
        action=(0.1, 0.9),
        selected_action=ACTION_B,
        event="baseline-update",
        component="baseline:core",
    )


def test_frozen_config_is_exact_complete_and_explicitly_unexecuted() -> None:
    protocol = load_frozen_protocol_v0_7(CONFIG)
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert protocol.status == PROTOCOL_STATUS
    assert protocol.status == "INVALIDATED_SUPERSEDED_FOR_FUTURE"
    assert protocol.expected_arms == EXPECTED_ARMS
    assert len(protocol.comparisons) == 9
    assert len(protocol.mechanism_requirements) == 10
    assert protocol.new_trace_set_present is False
    assert protocol.formal_gate_b_passed is False
    assert protocol.seven_operator_ablation_authorized is False
    assert payload["superseded_by"] == SUPERSEDED_BY_PROTOCOL_ID
    assert payload["positive_authorization_paths_disabled"] is True
    assert payload["ontology_contract"] == {
        **payload["ontology_contract"],
        "belief_support_size": len(BELIEF_SUPPORT),
        "belief_support_manifest_sha256": BELIEF_SUPPORT_MANIFEST_SHA256,
        "action_support_size": len(ACTION_SUPPORT),
        "action_support_manifest_sha256": ACTION_SUPPORT_MANIFEST_SHA256,
        "exact_frozen_support_required": True,
    }
    assert payload["action_selection_contract"] == {
        "rule": ActionSelectionRule.DETERMINISTIC_ARGMAX_LEXICAL.value,
        "tie_break": "lexicographically_smallest_action_label",
        "stochastic_action_draws_forbidden": True,
        "caller_selected_rng_forbidden": True,
        "selected_disagreement_requires_material_action_tv_same_step": True,
    }


def test_frozen_config_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    duplicated = CONFIG.read_text(encoding="utf-8").replace(
        "{", '{"protocol":"attacker-shadow",', 1
    )
    path = tmp_path / "duplicate-gate-b.json"
    path.write_text(duplicated, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_frozen_protocol_v0_7(path)


@pytest.mark.parametrize(
    "field",
    (
        "new_trace_set_present",
        "formal_gate_b_passed",
        "seven_operator_ablation_authorized",
    ),
)
def test_invalidated_v0_7_object_rejects_direct_positive_construction(field: str) -> None:
    protocol = load_frozen_protocol_v0_7(CONFIG)
    with pytest.raises(ValueError, match="cannot expose a positive path"):
        replace(protocol, **{field: True})


def test_frozen_config_rejects_any_caller_selected_weakening() -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    payload["comparison_pairs"][0]["belief_thresholds"]["min_mean_total_variation"] = 0.0
    with pytest.raises(ValueError, match="differs from the canonical frozen protocol"):
        validate_frozen_protocol_payload_v0_7(payload)


def test_complete_canonical_ten_arm_diagnostic_uses_the_loaded_freeze() -> None:
    protocol = load_frozen_protocol_v0_7(CONFIG)
    traces = []
    for arm in EXPECTED_ARMS:
        candidate = arm == "care_wm"
        receipts = tuple(
            MechanismReceipt(
                event=event,
                component_id=CANONICAL_COMPONENT_IDS[arm],
                input_state_sha256=_sha(f"{arm}:{event}:before"),
                output_state_sha256=_sha(f"{arm}:{event}:after"),
            )
            for event in CANONICAL_MECHANISM_EVENTS[arm]
        )
        traces.append(
            _trace(
                arm,
                belief=(0.9, 0.1) if candidate else (0.1, 0.9),
                action=(0.9, 0.1) if candidate else (0.1, 0.9),
                selected_action=ACTION_A if candidate else ACTION_B,
                event=CANONICAL_MECHANISM_EVENTS[arm][0],
                component=CANONICAL_COMPONENT_IDS[arm],
                receipts=receipts,
            )
        )
    report = score_frozen_dual_gate_b_v0_7_diagnostic(tuple(traces), protocol=protocol)
    assert len(report["comparison_pair_results"]) == 9
    assert len(report["mechanism_activation_results"]) == 10
    assert report["diagnostic_dual_conditions_passed"] is True
    assert report["protocol_invalidated"] is True
    assert report["superseded_by"] == SUPERSEDED_BY_PROTOCOL_ID
    assert report["formal_gate_b_passed"] is False
    assert report["seven_operator_ablation_authorized"] is False


def test_all_three_diagnostic_conditions_are_conjunctive_but_never_formal() -> None:
    report = _score(_candidate(), _baseline())
    assert report["belief_support_manifest_sha256"] == BELIEF_SUPPORT_MANIFEST_SHA256
    assert report["action_support_manifest_sha256"] == ACTION_SUPPORT_MANIFEST_SHA256
    assert report["action_selection_rule"] == ActionSelectionRule.DETERMINISTIC_ARGMAX_LEXICAL.value
    assert report["diagnostic_belief_gate_passed"] is True
    assert report["diagnostic_action_gate_passed"] is True
    assert report["diagnostic_mechanism_gate_passed"] is True
    assert report["diagnostic_dual_conditions_passed"] is True
    assert report["protocol_invalidated"] is True
    assert report["formal_gate_b_passed"] is False
    assert report["gate_b_passed"] is False
    assert report["seven_operator_ablation_authorized"] is False


@pytest.mark.parametrize(
    ("baseline_belief", "baseline_action", "baseline_selected", "failed_gate"),
    (
        ((0.9, 0.1), (0.1, 0.9), ACTION_B, "diagnostic_belief_gate_passed"),
        ((0.1, 0.9), (0.9, 0.1), ACTION_A, "diagnostic_action_gate_passed"),
    ),
)
def test_belief_and_action_cannot_substitute_for_each_other(
    baseline_belief: tuple[float, float],
    baseline_action: tuple[float, float],
    baseline_selected: str,
    failed_gate: str,
) -> None:
    baseline = _trace(
        "baseline",
        belief=baseline_belief,
        action=baseline_action,
        selected_action=baseline_selected,
        event="baseline-update",
        component="baseline:core",
    )
    report = _score(_candidate(), baseline)
    assert report[failed_gate] is False
    assert report["diagnostic_dual_conditions_passed"] is False


def test_action_distribution_difference_without_selected_action_change_fails() -> None:
    candidate = _trace(
        "candidate",
        belief=(0.9, 0.1),
        action=(0.9, 0.1),
        selected_action=ACTION_A,
        event="candidate-update",
        component="candidate:core",
    )
    baseline = _trace(
        "baseline",
        belief=(0.1, 0.9),
        action=(0.6, 0.4),
        selected_action=ACTION_A,
        event="baseline-update",
        component="baseline:core",
    )
    report = _score(candidate, baseline)
    assert report["diagnostic_belief_gate_passed"] is True
    assert report["diagnostic_action_gate_passed"] is False
    assert report["diagnostic_dual_conditions_passed"] is False


def test_missing_registered_mechanism_cannot_be_hidden_by_both_readouts() -> None:
    baseline = _trace(
        "baseline",
        belief=(0.1, 0.9),
        action=(0.1, 0.9),
        selected_action=ACTION_B,
        event="wrapper-called",
        component="wrapper:component",
    )
    report = _score(_candidate(), baseline)
    assert report["diagnostic_belief_gate_passed"] is True
    assert report["diagnostic_action_gate_passed"] is True
    assert report["diagnostic_mechanism_gate_passed"] is False
    assert report["diagnostic_dual_conditions_passed"] is False


def test_float_noise_and_metadata_changes_cannot_open_the_belief_gate() -> None:
    candidate = _trace(
        "candidate",
        belief=(0.5000001, 0.4999999),
        action=(0.9, 0.1),
        selected_action=ACTION_A,
        event="candidate-update",
        component="candidate:core",
        metadata=(("display_name", "renamed-candidate"),),
    )
    baseline = _trace(
        "baseline",
        belief=(0.5, 0.5),
        action=(0.1, 0.9),
        selected_action=ACTION_B,
        event="baseline-update",
        component="baseline:core",
        metadata=(("display_name", "different-file-metadata"),),
    )
    report = _score(candidate, baseline)
    comparison_results = report["comparison_pair_results"]
    assert isinstance(comparison_results, list)
    pair = comparison_results[0]
    assert pair["mean_belief_total_variation"] == pytest.approx(1e-7)
    assert pair["belief_passed"] is False
    assert pair["action_passed"] is True
    assert report["diagnostic_dual_conditions_passed"] is False


def test_semantic_trace_identity_excludes_untrusted_metadata() -> None:
    original = _candidate()
    renamed = replace(original, metadata=(("filename", "forged-different-name.json"),))
    assert semantic_trace_sha256(original) == semantic_trace_sha256(renamed)


@pytest.mark.parametrize(
    ("stage", "truth_accessed"),
    (
        (ReadoutStage.POST_ACTION_OBSERVATION, False),
        (ReadoutStage.POST_EVALUATOR_TRUTH, False),
        (ReadoutStage.PRE_ACTION_PRE_EVALUATOR_TRUTH, True),
    ),
)
def test_post_action_or_truth_access_is_rejected_before_scoring(
    stage: ReadoutStage,
    truth_accessed: bool,
) -> None:
    attacked = _trace(
        "baseline",
        belief=(0.1, 0.9),
        action=(0.1, 0.9),
        selected_action=ACTION_B,
        event="baseline-update",
        component="baseline:core",
        stage=stage,
        truth_accessed=truth_accessed,
    )
    with pytest.raises(ValueError, match=r"post-action or post-truth|evaluator truth"):
        _score(_candidate(), attacked)


@pytest.mark.parametrize(
    ("information_tag", "budget", "message"),
    (
        ("forged-extra-input", None, "different information sets"),
        ("common", _budget(compute=101), "different budget envelopes"),
    ),
)
def test_information_set_and_budget_must_align_exactly(
    information_tag: str,
    budget: BudgetEnvelope | None,
    message: str,
) -> None:
    attacked = _trace(
        "baseline",
        belief=(0.1, 0.9),
        action=(0.1, 0.9),
        selected_action=ACTION_B,
        event="baseline-update",
        component="baseline:core",
        information_tag=information_tag,
        budget=budget,
    )
    with pytest.raises(ValueError, match=message):
        _score(_candidate(), attacked)


def test_probability_vectors_are_dense_finite_and_normalized() -> None:
    with pytest.raises(ValueError, match="already be normalized"):
        _distribution(BELIEF_SCHEMA_ID, (0.6, 0.6))
    with pytest.raises(ValueError, match="finite and non-negative"):
        _distribution(BELIEF_SCHEMA_ID, (float("nan"), float("nan")))
    with pytest.raises(ValueError, match="densely cover"):
        CanonicalProbabilityDistribution(
            schema_id=BELIEF_SCHEMA_ID,
            support=BELIEF_SUPPORT,
            probabilities=(1.0,),
        )


def test_nonfinite_materiality_threshold_is_rejected() -> None:
    with pytest.raises(ValueError, match="materiality thresholds"):
        DualGateComparison(
            comparison_id="attacked",
            domain="same question",
            left_arm="candidate",
            right_arm="baseline",
            min_mean_belief_tv=float("nan"),
        )


@pytest.mark.parametrize(
    ("schema_id", "forged_support"),
    (
        (BELIEF_SCHEMA_ID, ("belief:a", "belief:b")),
        (ACTION_SCHEMA_ID, ("action:a", "action:b")),
    ),
)
def test_shared_arbitrary_labels_cannot_impersonate_frozen_semantic_ontology(
    schema_id: str,
    forged_support: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="frozen semantic ontology"):
        _distribution(schema_id, (0.9, 0.1), support=forged_support)


def test_random_action_draw_cannot_create_selected_action_disagreement() -> None:
    with pytest.raises(ValueError, match="deterministic argmax with lexical tie-break"):
        _step(
            "attacked",
            0,
            belief=(0.9, 0.1),
            action=(0.5, 0.5),
            selected_action=ACTION_B,
            event="attacked-update",
            component="attacked:core",
        )


def test_float_noise_action_flip_cannot_borrow_materiality_from_other_steps() -> None:
    candidate = _trace(
        "candidate",
        belief=(0.9, 0.1),
        action=(0.9, 0.1),
        selected_action=ACTION_A,
        event="candidate-update",
        component="candidate:core",
    )
    baseline = _trace(
        "baseline",
        belief=(0.1, 0.9),
        action=(0.6, 0.4),
        selected_action=ACTION_A,
        event="baseline-update",
        component="baseline:core",
    )
    candidate_first = replace(
        candidate.episodes[0].steps[0],
        action_policy=_distribution(ACTION_SCHEMA_ID, (0.5000001, 0.4999999)),
    )
    baseline_first = replace(
        baseline.episodes[0].steps[0],
        action_policy=_distribution(ACTION_SCHEMA_ID, (0.4999999, 0.5000001)),
        selected_action=ACTION_B,
    )
    candidate = replace(
        candidate,
        episodes=(
            replace(
                candidate.episodes[0],
                steps=(candidate_first, *candidate.episodes[0].steps[1:]),
            ),
        ),
    )
    baseline = replace(
        baseline,
        episodes=(
            replace(
                baseline.episodes[0],
                steps=(baseline_first, *baseline.episodes[0].steps[1:]),
            ),
        ),
    )
    report = _score(candidate, baseline)
    comparison_results = report["comparison_pair_results"]
    assert isinstance(comparison_results, list)
    pair = comparison_results[0]
    assert pair["mean_action_total_variation"] > 0.01
    assert pair["action_material_step_fraction"] > 0.01
    assert pair["selected_action_disagreement_rate"] == 0.0
    assert pair["action_passed"] is False
