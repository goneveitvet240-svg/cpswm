"""Frozen action-advantage gate for structured transition residuals."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from statistics import mean
from typing import Any

from cpswm.contracts import ProjectTwoDatasetSplit
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ProjectTwoActionBenchmarkV02,
    _FullProjectTwoMethod,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_factorial_benchmark import _CIAVState
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (
    MultiAxisBelief,
    _action_readout,
    _FamilyFeedbackState,
    _file_sha256,
    _normalize,
    _VisibleTransformState,
)
from cpswm.system.evaluation_operations.structure_two_neural_amortized import (
    CAUSES,
    FEATURE_NAMES,
    NeuralModelConfig,
    _feature_vector,
)
from cpswm.system.evaluation_operations.structure_two_rejuvenation_gate import (
    FROZEN_PARTICLE_BUDGET,
)
from cpswm.system.evaluation_operations.structure_two_sequential_gate import (
    PersistentParticle,
    SequentialGateFamily,
    SequentialParticleRuntime,
    _TargetObjectRoutingState,
    _visible_transform,
)
from cpswm.system.evaluation_operations.structure_two_transition_reactivation import (
    ConflictAwareSequentialParticleRuntime,
    GateReading,
    TransitionReactivationArm,
    _TransitionReactivationState,
)
from cpswm.system.evaluation_operations.structure_two_transition_reactivation import (
    _evaluate as _transition_evaluate,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-structured-residual-transition-gate@0.1"
DEFAULT_MANIFEST = Path(
    "configs/project_two_experiments/structure_two_structured_residual_manifest_v0_1.json"
)
DEFAULT_SEALED_SEEDS = Path(
    "configs/project_two_experiments/structure_two_structured_residual_sealed_seeds_v0_1.json"
)
DEFAULT_PREREGISTRATION = Path(
    "docs/experiments/structure_two_structured_residual_transition_gate_preregistration_2026-08-29.md"
)
DEFAULT_MODEL_ARTIFACT = Path(
    "artifacts/project_two_v04_development/structure_two_structured_residual_model_v0_1.json"
)
FORBIDDEN_INFERENCE_INPUTS = {
    "oracle_action_at_inference",
    "latent_actor",
    "latent_cause",
    "latent_regime",
    "holdout_seed",
}


class ResidualArm(StrEnum):
    CORRECTED_AMG = "corrected_amg"
    PER_STEP_PARTICLE = "per_step_particle_projection"
    SEQUENTIAL = "sequential_particle_no_consolidation"
    DETERMINISTIC = "deterministic_transition_no_consolidation"
    NEURAL_RESIDUAL_ONLY = "neural_residual_only"
    DETERMINISTIC_PLUS_RESIDUAL = "deterministic_plus_neural_residual"
    REACTIVATION = "historical_regime_reactivation"
    FULL_JOINT = "full_residual_reactivation_joint"


@dataclass(frozen=True, slots=True)
class ResidualDesign:
    training_seeds: tuple[int, ...]
    validation_seeds: tuple[int, ...]
    holdout_seed_commitments: tuple[str, ...]
    sealed_holdout_seed_count: int
    sealed_seed_file_sha256: str
    max_steps: int
    particle_budget: int
    model: NeuralModelConfig
    families: tuple[SequentialGateFamily, ...]
    search_spaces: Mapping[str, tuple[Any, ...]]
    guardrail_noninferiority_margin: float
    manifest_file_sha256: str


@dataclass(frozen=True, slots=True)
class ResidualTrainingExample:
    features: tuple[float, ...]
    target: float
    weight: float


@dataclass(frozen=True, slots=True)
class ResidualGateModel:
    feature_names: tuple[str, ...]
    hidden_weights: tuple[tuple[float, ...], ...]
    hidden_bias: tuple[float, ...]
    output_weights: tuple[float, ...]
    output_bias: float
    training_example_count: int
    positive_target_rate: float
    training_loss: float
    config: NeuralModelConfig

    def predict(self, features: Sequence[float]) -> float:
        if len(features) != len(self.feature_names):
            raise ValueError("structured residual feature width mismatch")
        hidden = [
            math.tanh(
                bias + sum(weight * value for weight, value in zip(row, features, strict=True))
            )
            for row, bias in zip(self.hidden_weights, self.hidden_bias, strict=True)
        ]
        logit = self.output_bias + sum(
            weight * value for weight, value in zip(self.output_weights, hidden, strict=True)
        )
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, logit))))

    def payload(self) -> dict[str, Any]:
        return {
            "protocol": PROTOCOL_ID,
            "model_type": "trained_structured_residual_action_advantage_gate",
            "feature_names": list(self.feature_names),
            "hidden_weights": [list(row) for row in self.hidden_weights],
            "hidden_bias": list(self.hidden_bias),
            "output_weights": list(self.output_weights),
            "output_bias": self.output_bias,
            "training_example_count": self.training_example_count,
            "positive_target_rate": self.positive_target_rate,
            "training_loss": self.training_loss,
            "config": asdict(self.config),
            "training_target_boundary": "training-only episode action advantage",
        }

    @property
    def model_hash(self) -> str:
        return str(content_sha256(self.payload()))


def load_frozen_residual_design(manifest_path: Path = DEFAULT_MANIFEST) -> ResidualDesign:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("structured residual manifest protocol mismatch")
    families = tuple(
        SequentialGateFamily(
            family_id=item["family_id"],
            family_role=item["family_role"],
            guest_window=tuple(item["guest_window"]),
            abrupt_day=item["abrupt_day"],
            recurrence_day=item["recurrence_day"],
            observation_coverage=item["observation_coverage"],
            unknown_event_days=tuple(item["unknown_event_days"]),
            actor_ambiguity_mix=item["actor_ambiguity_mix"],
            identity_confidence_scale=item["identity_confidence_scale"],
            feedback_flip_rate=item["feedback_flip_rate"],
            decoy_days=tuple(item["decoy_days"]),
        )
        for item in payload["scenario_families"]
    )
    model = NeuralModelConfig(
        architecture=payload["model"]["architecture"],
        hidden_units=payload["model"]["hidden_units"],
        epochs=payload["model"]["epochs"],
        learning_rate=payload["model"]["learning_rate"],
        l2=payload["model"]["l2"],
        initialization_seed=payload["model"]["initialization_seed"],
        target_semantics=payload["model"]["target_semantics"],
        forbidden_inputs=tuple(payload["model"]["forbidden_inputs"]),
    )
    design = ResidualDesign(
        training_seeds=tuple(payload["training_seeds"]),
        validation_seeds=tuple(payload["validation_seeds"]),
        holdout_seed_commitments=tuple(payload["sealed_holdout_seed_commitments"]),
        sealed_holdout_seed_count=payload["sealed_holdout_seed_count"],
        sealed_seed_file_sha256=payload["sealed_seed_file_sha256"],
        max_steps=payload["max_steps"],
        particle_budget=payload["particle_budget"],
        model=model,
        families=families,
        search_spaces={key: tuple(value) for key, value in payload["search_spaces"].items()},
        guardrail_noninferiority_margin=float(payload["guardrail_noninferiority_margin"]),
        manifest_file_sha256=_file_sha256(manifest_path),
    )
    if len(FEATURE_NAMES) != 16 or design.model.hidden_units != 8:
        raise ValueError("structured residual freezes a 16x8x1 gate")
    if set(design.search_spaces) != {arm.value for arm in ResidualArm}:
        raise ValueError("structured residual search-space mismatch")
    if len(families) != 4 or design.particle_budget != FROZEN_PARTICLE_BUDGET:
        raise ValueError("structured residual freezes four families and K=24")
    if set(design.training_seeds) & set(design.validation_seeds):
        raise ValueError("structured residual train/validation overlap")
    if set(design.model.forbidden_inputs) != FORBIDDEN_INFERENCE_INPUTS:
        raise ValueError("structured residual forbidden-input declaration mismatch")
    if set(FEATURE_NAMES) & FORBIDDEN_INFERENCE_INPUTS:
        raise ValueError("forbidden structured residual inference feature")
    return design


def _load_and_verify_holdout_seeds(
    design: ResidualDesign, sealed_seed_path: Path
) -> tuple[int, ...]:
    if _file_sha256(sealed_seed_path) != design.sealed_seed_file_sha256:
        raise ValueError("structured residual sealed seed hash mismatch")
    payload = json.loads(sealed_seed_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("structured residual sealed protocol mismatch")
    seeds = tuple(payload["holdout_seeds"])
    salt = payload["commitment_salt"]
    commitments = tuple(
        hashlib.sha256(f"{PROTOCOL_ID}:{seed}:{salt}".encode()).hexdigest() for seed in seeds
    )
    if commitments != design.holdout_seed_commitments:
        raise ValueError("structured residual commitment mismatch")
    if set(seeds) & (set(design.training_seeds) | set(design.validation_seeds)):
        raise ValueError("structured residual train/validation/holdout overlap")
    return seeds


def _dataset(
    family: SequentialGateFamily,
    *,
    validation_seeds: tuple[int, ...],
    test_seeds: tuple[int, ...],
    max_steps: int,
    split_label: str,
) -> ProjectTwoReplayDataset:
    return D0SyntheticOracleReplayAdapter(
        validation_seeds=validation_seeds,
        test_seeds=test_seeds,
        max_steps_per_episode=max_steps,
        dataset_version=f"{PROTOCOL_ID}:{family.family_id}:{split_label}",
        sealed_secret=f"{PROTOCOL_ID}:{family.family_id}:scenario-seal",
        scenario_duration_days=max_steps,
        guest_window=family.guest_window,
        abrupt_day=family.abrupt_day,
        recurrence_day=family.recurrence_day,
        observation_coverage=family.observation_coverage,
        unknown_event_days=family.unknown_event_days,
    ).build()


class _ConflictFeatureRecorder(ConflictAwareSequentialParticleRuntime):
    def __init__(self, *, profile: str) -> None:
        super().__init__(profile=profile)
        self.conflict_features: list[tuple[float, ...]] = []

    def revise(self, belief: MultiAxisBelief) -> tuple[PersistentParticle, ...]:
        parent = (
            None
            if not self.particles
            else max(self.particles, key=lambda item: (item.posterior_probability, item.signature))
        )
        before = len(self.conflict_transition_receipts)
        result = tuple(super().revise(belief))
        if len(self.conflict_transition_receipts) > before:
            self.conflict_features.append(_feature_vector(belief, parent))
        return result


def _wrapped_state(
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    family: SequentialGateFamily,
    *,
    profile: str,
    runtime: SequentialParticleRuntime,
    reactivation: bool,
) -> Any:
    base = _FullProjectTwoMethod(episode, owner_threshold=0.4, action_readout=_action_readout())
    core = _TransitionReactivationState(
        base,
        episode,
        profile=profile,
        conflict_transition=False,
        reactivation=reactivation,
    )
    core._runtime = runtime
    state: Any = _CIAVState(core, dataset, episode, enabled=True, cost_multiplier=1.0)
    state.operator_retention_receipt = {**state.operator_retention_receipt, "ciav": True}
    state = _TargetObjectRoutingState(state)
    state = _VisibleTransformState(state, _visible_transform(family, episode))
    return _FamilyFeedbackState(state, family, episode)


def _collect_training_examples(
    design: ResidualDesign, evaluator: ProjectTwoActionBenchmarkV02
) -> tuple[ResidualTrainingExample, ...]:
    examples: list[ResidualTrainingExample] = []
    for family_index, family in enumerate(design.families):
        dataset = _dataset(
            family,
            validation_seeds=design.training_seeds,
            test_seeds=(109901 + family_index,),
            max_steps=design.max_steps,
            split_label="training-action-advantage",
        )
        for episode in dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION):
            sequential = _transition_evaluate(
                evaluator,
                dataset,
                episode,
                family,
                TransitionReactivationArm.SEQUENTIAL_NO_CONSOLIDATION,
                "balanced",
            )
            recorder = _ConflictFeatureRecorder(profile="balanced")
            state = _wrapped_state(
                dataset,
                episode,
                family,
                profile="balanced",
                runtime=recorder,
                reactivation=False,
            )
            metric = evaluator.evaluate_custom_state(dataset, episode, state)
            deterministic_loss = (
                metric.cumulative_action_regret + float(getattr(state, "verification_cost", 0.0))
            ) / max(1, metric.step_count)
            advantage = sequential.net_action_loss_per_step - deterministic_loss
            target = 1.0 if advantage > 1e-12 else 0.0 if advantage < -1e-12 else 0.5
            weight = 1.0 + min(3.0, abs(advantage) * metric.step_count)
            examples.extend(
                ResidualTrainingExample(features, target, weight)
                for features in recorder.conflict_features
            )
    if not examples:
        raise ValueError("structured residual training set is empty")
    return tuple(examples)


def _train_model(
    examples: Sequence[ResidualTrainingExample], config: NeuralModelConfig
) -> ResidualGateModel:
    rng = random.Random(config.initialization_seed)
    width = len(FEATURE_NAMES)
    hidden = config.hidden_units
    w1 = [[rng.uniform(-0.12, 0.12) for _ in range(width)] for _ in range(hidden)]
    b1 = [0.0 for _ in range(hidden)]
    w2 = [rng.uniform(-0.12, 0.12) for _ in range(hidden)]
    b2 = 0.0
    final_loss = 0.0
    for _ in range(config.epochs):
        gw1 = [[0.0 for _ in range(width)] for _ in range(hidden)]
        gb1 = [0.0 for _ in range(hidden)]
        gw2 = [0.0 for _ in range(hidden)]
        gb2 = 0.0
        loss = 0.0
        total_weight = sum(item.weight for item in examples)
        for item in examples:
            h = [
                math.tanh(b1[j] + sum(w1[j][i] * item.features[i] for i in range(width)))
                for j in range(hidden)
            ]
            logit = b2 + sum(w2[j] * h[j] for j in range(hidden))
            probability = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, logit))))
            loss -= item.weight * (
                item.target * math.log(max(probability, 1e-12))
                + (1.0 - item.target) * math.log(max(1.0 - probability, 1e-12))
            )
            delta = item.weight * (probability - item.target)
            gb2 += delta
            for j in range(hidden):
                gw2[j] += delta * h[j]
                hidden_delta = delta * w2[j] * (1.0 - h[j] ** 2)
                gb1[j] += hidden_delta
                for i in range(width):
                    gw1[j][i] += hidden_delta * item.features[i]
        for j in range(hidden):
            b1[j] -= config.learning_rate * gb1[j] / total_weight
            w2[j] -= config.learning_rate * (gw2[j] / total_weight + config.l2 * w2[j])
            for i in range(width):
                w1[j][i] -= config.learning_rate * (gw1[j][i] / total_weight + config.l2 * w1[j][i])
        b2 -= config.learning_rate * gb2 / total_weight
        final_loss = loss / total_weight
    positive_rate = sum(item.weight * item.target for item in examples) / sum(
        item.weight for item in examples
    )
    return ResidualGateModel(
        feature_names=tuple(FEATURE_NAMES),
        hidden_weights=tuple(tuple(row) for row in w1),
        hidden_bias=tuple(b1),
        output_weights=tuple(w2),
        output_bias=b2,
        training_example_count=len(examples),
        positive_target_rate=positive_rate,
        training_loss=final_loss,
        config=config,
    )


def _conflict_target(belief: MultiAxisBelief, parent: PersistentParticle) -> tuple[bool, Any, bool]:
    modal = max(CAUSES, key=lambda cause: (belief.cause_posterior[cause], cause.value))
    regime_change = belief.regime_change_probability >= 0.5
    cause_conflict = parent.hypothesis.cause is not modal and belief.cause_posterior[modal] >= 0.35
    regime_conflict = (
        parent.hypothesis.regime_change != regime_change
        and abs(belief.regime_change_probability - 0.5) >= 0.15
    )
    return cause_conflict or regime_conflict, modal, regime_change


class StructuredResidualParticleRuntime(SequentialParticleRuntime):
    def __init__(
        self,
        *,
        profile: str,
        model: ResidualGateModel,
        residual_scale: float,
        deterministic_prior: bool,
    ) -> None:
        super().__init__(profile=profile)
        self.particles: tuple[PersistentParticle, ...] = tuple(getattr(self, "particles", ()))
        self.step_index = int(getattr(self, "step_index", 0))
        self.model = model
        self.residual_scale = residual_scale
        self.deterministic_prior = deterministic_prior
        self.residual_receipts: list[str] = []

    def revise(self, belief: MultiAxisBelief) -> tuple[PersistentParticle, ...]:
        proposal = belief
        if self.particles:
            parent = max(
                self.particles,
                key=lambda item: (item.posterior_probability, item.signature),
            )
            conflict, modal, regime_change = _conflict_target(belief, parent)
            if conflict:
                gate = self.model.predict(_feature_vector(belief, parent))
                if self.deterministic_prior:
                    strength = max(
                        0.0,
                        min(1.25, 1.0 + self.residual_scale * (2.0 * gate - 1.0)),
                    )
                else:
                    strength = max(0.0, min(1.0, self.residual_scale * (2.0 * gate - 1.0)))
                remaining = 0.15 / (len(CAUSES) - 1)
                target_cause = {cause: (0.85 if cause is modal else remaining) for cause in CAUSES}
                cause = _normalize(
                    {
                        cause: max(
                            0.0,
                            belief.cause_posterior[cause]
                            + strength * (target_cause[cause] - belief.cause_posterior[cause]),
                        )
                        for cause in CAUSES
                    }
                )
                regime_target = 0.85 if regime_change else 0.15
                proposal = replace(
                    belief,
                    cause_posterior=cause,
                    regime_change_probability=max(
                        0.0,
                        min(
                            1.0,
                            belief.regime_change_probability
                            + strength * (regime_target - belief.regime_change_probability),
                        ),
                    ),
                )
                release = min(1.0, strength)
                uniform = 1.0 / len(self.particles)
                self.particles = tuple(
                    replace(
                        particle,
                        posterior_probability=(
                            (1.0 - release) * particle.posterior_probability + release * uniform
                        ),
                    )
                    for particle in self.particles
                )
                self.residual_receipts.append(
                    content_sha256(
                        {
                            "model_hash": self.model.model_hash,
                            "step_index": self.step_index + 1,
                            "parent_signature": parent.signature,
                            "gate_probability": gate,
                            "residual_scale": self.residual_scale,
                            "applied_strength": strength,
                            "deterministic_prior": self.deterministic_prior,
                        }
                    )
                )
        return tuple(super().revise(proposal))


def _parse_parameter(parameter: Any) -> tuple[str, float]:
    profile, raw_scale = str(parameter).split(":", maxsplit=1)
    return profile, float(raw_scale)


def _evaluate(
    evaluator: ProjectTwoActionBenchmarkV02,
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    family: SequentialGateFamily,
    arm: ResidualArm,
    parameter: Any,
    model: ResidualGateModel,
) -> tuple[GateReading, int]:
    mapping = {
        ResidualArm.CORRECTED_AMG: TransitionReactivationArm.CORRECTED_AMG,
        ResidualArm.PER_STEP_PARTICLE: TransitionReactivationArm.PER_STEP_PARTICLE,
        ResidualArm.SEQUENTIAL: TransitionReactivationArm.SEQUENTIAL_NO_CONSOLIDATION,
        ResidualArm.DETERMINISTIC: (TransitionReactivationArm.CONFLICT_TRANSITION_NO_CONSOLIDATION),
        ResidualArm.REACTIVATION: TransitionReactivationArm.HISTORICAL_REACTIVATION,
    }
    if arm in mapping:
        return (
            _transition_evaluate(
                evaluator,
                dataset,
                episode,
                family,
                mapping[arm],
                parameter,
            ),
            0,
        )
    profile, scale = _parse_parameter(parameter)
    runtime = StructuredResidualParticleRuntime(
        profile=profile,
        model=model,
        residual_scale=scale,
        deterministic_prior=arm
        in {ResidualArm.DETERMINISTIC_PLUS_RESIDUAL, ResidualArm.FULL_JOINT},
    )
    state = _wrapped_state(
        dataset,
        episode,
        family,
        profile=profile,
        runtime=runtime,
        reactivation=arm is ResidualArm.FULL_JOINT,
    )
    metric = evaluator.evaluate_custom_state(dataset, episode, state)
    return (
        GateReading(
            metric=metric,
            verification_cost=float(getattr(state, "verification_cost", 0.0)),
            ancestry_edge_count=int(getattr(state, "ancestry_edge_count", 0)),
            operator_retention_receipt=getattr(state, "operator_retention_receipt", None),
            consumed_visible_stream_hash=str(getattr(state, "consumed_visible_stream_hash", "")),
            conflict_transition_count=len(runtime.residual_receipts),
            reactivation_count=int(getattr(state, "reactivation_count", 0)),
            duplicate_promotion_count=int(getattr(state, "duplicate_promotion_count", 0)),
        ),
        len(runtime.residual_receipts),
    )


COMPARISONS = {
    "deterministic_plus_residual_minus_deterministic": (
        ResidualArm.DETERMINISTIC_PLUS_RESIDUAL,
        ResidualArm.DETERMINISTIC,
    ),
    "deterministic_plus_residual_minus_sequential": (
        ResidualArm.DETERMINISTIC_PLUS_RESIDUAL,
        ResidualArm.SEQUENTIAL,
    ),
    "neural_residual_only_minus_sequential": (
        ResidualArm.NEURAL_RESIDUAL_ONLY,
        ResidualArm.SEQUENTIAL,
    ),
    "reactivation_minus_sequential": (ResidualArm.REACTIVATION, ResidualArm.SEQUENTIAL),
    "full_joint_minus_deterministic_plus_residual": (
        ResidualArm.FULL_JOINT,
        ResidualArm.DETERMINISTIC_PLUS_RESIDUAL,
    ),
    "full_joint_minus_corrected_amg": (ResidualArm.FULL_JOINT, ResidualArm.CORRECTED_AMG),
}


def _bootstrap_ci(values: list[float], *, draws: int = 4000) -> tuple[float, float]:
    rng = random.Random(f"{PROTOCOL_ID}:paired-cluster-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


def _summary(values: Sequence[tuple[GateReading, int]]) -> dict[str, float]:
    readings = [item[0] for item in values]
    return {
        "net_action_loss_per_step": mean(item.net_action_loss_per_step for item in readings),
        "put_back_error_rate": mean(item.metric.put_back_error_rate for item in readings),
        "persistent_owner_mode_error_rate": mean(
            item.metric.persistent_owner_mode_error_rate for item in readings
        ),
        "verification_cost": mean(item.verification_cost for item in readings),
        "mean_ancestry_edge_count": mean(item.ancestry_edge_count for item in readings),
        "residual_receipt_count": sum(item[1] for item in values),
        "reactivation_count": sum(item.reactivation_count for item in readings),
        "duplicate_promotion_count": sum(item.duplicate_promotion_count for item in readings),
    }


def run_structured_residual_gate(*, repository_root: Path) -> dict[str, Any]:
    manifest = repository_root / DEFAULT_MANIFEST
    sealed = repository_root / DEFAULT_SEALED_SEEDS
    model_path = repository_root / DEFAULT_MODEL_ARTIFACT
    design = load_frozen_residual_design(manifest)
    evaluator = ProjectTwoActionBenchmarkV02()
    phase_audit = ["training_action_advantage_collection_started_without_sealed_access"]
    examples = _collect_training_examples(design, evaluator)
    model = _train_model(examples, design.model)
    model_payload = {**model.payload(), "model_hash": model.model_hash}
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(json.dumps(model_payload, indent=2) + "\n", encoding="utf-8")
    model_file_sha256 = _file_sha256(model_path)
    phase_audit.extend(
        ("training_completed", "residual_model_artifact_frozen", "validation_started")
    )

    selected: dict[str, dict[ResidualArm, Any]] = {}
    validation_reports: dict[str, Any] = {}
    for family_index, family in enumerate(design.families):
        dataset = _dataset(
            family,
            validation_seeds=design.validation_seeds,
            test_seeds=(109951 + family_index,),
            max_steps=design.max_steps,
            split_label="validation",
        )
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
        selected[family.family_id] = {}
        validation_reports[family.family_id] = {}
        for arm in ResidualArm:
            candidates = []
            for parameter in design.search_spaces[arm.value]:
                readings = [
                    _evaluate(evaluator, dataset, episode, family, arm, parameter, model)[0]
                    for episode in episodes
                ]
                candidates.append(
                    {
                        "parameter": parameter,
                        "mean_net_action_loss_per_step": mean(
                            item.net_action_loss_per_step for item in readings
                        ),
                    }
                )
            winner = min(
                candidates,
                key=lambda item: (
                    item["mean_net_action_loss_per_step"],
                    json.dumps(item["parameter"], sort_keys=True),
                ),
            )
            selected[family.family_id][arm] = winner["parameter"]
            validation_reports[family.family_id][arm.value] = {
                "candidates": candidates,
                "selected_parameter": winner["parameter"],
            }
    phase_audit.extend(("validation_completed", "sealed_seed_file_open_requested"))
    holdout_seeds = _load_and_verify_holdout_seeds(design, sealed)
    phase_audit.extend(("sealed_seed_file_verified", "one_shot_holdout_started"))

    expected_operator_receipt = {
        "opceu": "inverse",
        "orrer": "orrer",
        "pchmp": "ProvenanceConstrainedMessagePassing",
        "cf_bocpd": True,
        "rgrc": True,
        "ccrr": True,
        "ciav": True,
    }
    paired: dict[str, dict[str, list[float]]] = {
        commitment: {name: [] for name in COMPARISONS}
        for commitment in design.holdout_seed_commitments
    }
    family_reports: dict[str, Any] = {}
    operator_gates: dict[str, bool] = {}
    ancestry_gates: dict[str, bool] = {}
    residual_receipt_gates: dict[str, bool] = {}
    exactly_once_gates: dict[str, bool] = {}
    for family_index, family in enumerate(design.families):
        dataset = _dataset(
            family,
            validation_seeds=(109971 + family_index,),
            test_seeds=holdout_seeds,
            max_steps=design.max_steps,
            split_label="sealed-holdout",
        )
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        holdout_readings: dict[ResidualArm, list[tuple[GateReading, int]]] = {
            arm: [
                _evaluate(
                    evaluator,
                    dataset,
                    episode,
                    family,
                    arm,
                    selected[family.family_id][arm],
                    model,
                )
                for episode in episodes
            ]
            for arm in ResidualArm
        }
        for arm in ResidualArm:
            if arm is ResidualArm.CORRECTED_AMG:
                continue
            operator_gates[f"{family.family_id}:{arm.value}"] = all(
                item[0].operator_retention_receipt == expected_operator_receipt
                for item in holdout_readings[arm]
            )
            if arm is not ResidualArm.PER_STEP_PARTICLE:
                ancestry_gates[f"{family.family_id}:{arm.value}"] = all(
                    item[0].ancestry_edge_count > 0 for item in holdout_readings[arm]
                )
        for arm in (
            ResidualArm.NEURAL_RESIDUAL_ONLY,
            ResidualArm.DETERMINISTIC_PLUS_RESIDUAL,
            ResidualArm.FULL_JOINT,
        ):
            residual_receipt_gates[f"{family.family_id}:{arm.value}"] = any(
                item[1] > 0 for item in holdout_readings[arm]
            )
        exactly_once_gates[family.family_id] = all(
            item[0].duplicate_promotion_count == 0
            for arm in (ResidualArm.REACTIVATION, ResidualArm.FULL_JOINT)
            for item in holdout_readings[arm]
        )
        rows = []
        for index, commitment in enumerate(design.holdout_seed_commitments):
            hashes = {
                arm.value: holdout_readings[arm][index][0].consumed_visible_stream_hash
                for arm in ResidualArm
            }
            if len(set(hashes.values())) != 1:
                raise ValueError("structured residual consumed stream mismatch")
            losses = {
                arm.value: holdout_readings[arm][index][0].net_action_loss_per_step
                for arm in ResidualArm
            }
            differences = {
                name: losses[left.value] - losses[right.value]
                for name, (left, right) in COMPARISONS.items()
            }
            for name, value in differences.items():
                paired[commitment][name].append(value)
            rows.append(
                {
                    "holdout_seed_commitment": commitment,
                    "consumed_visible_stream_hash": next(iter(hashes.values())),
                    "net_action_loss_per_step": losses,
                    "paired_differences": differences,
                }
            )
        family_reports[family.family_id] = {
            "family_parameters": asdict(family),
            "selected_parameters": {
                arm.value: value for arm, value in selected[family.family_id].items()
            },
            "summaries": {arm.value: _summary(values) for arm, values in holdout_readings.items()},
            "paired_holdout_rows": rows,
        }
    clustered: dict[str, list[float]] = {
        name: [mean(paired[commitment][name]) for commitment in design.holdout_seed_commitments]
        for name in COMPARISONS
    }
    comparisons: dict[str, dict[str, Any]] = {
        name: {
            "mean": mean(values),
            "confidence_interval_95": _bootstrap_ci(values),
            "cluster_count": len(values),
            "benefit_if_negative": True,
        }
        for name, values in clustered.items()
    }
    primary = "deterministic_plus_residual_minus_deterministic"
    family_primary = {
        family_id: mean(row["paired_differences"][primary] for row in report["paired_holdout_rows"])
        for family_id, report in family_reports.items()
    }
    roles = {family.family_role: family.family_id for family in design.families}
    gate_criteria = {
        "primary_ci_upper_below_zero": comparisons[primary]["confidence_interval_95"][1] < 0.0,
        "combined_beats_sequential": comparisons["deterministic_plus_residual_minus_sequential"][
            "confidence_interval_95"
        ][1]
        < 0.0,
        "required_cause_gain_over_deterministic": family_primary[roles["required_cause_gain"]]
        < 0.0,
        "required_regime_gain_over_deterministic": family_primary[roles["required_regime_gain"]]
        < 0.0,
        "identity_guardrail": family_primary[roles["identity_guardrail"]]
        <= design.guardrail_noninferiority_margin,
        "role_guardrail": family_primary[roles["role_guardrail"]]
        <= design.guardrail_noninferiority_margin,
        "model_frozen_before_holdout": phase_audit.index("residual_model_artifact_frozen")
        < phase_audit.index("sealed_seed_file_open_requested"),
        "no_forbidden_inference_inputs": not (
            set(model.feature_names) & FORBIDDEN_INFERENCE_INPUTS
        ),
        "all_operator_gates": all(operator_gates.values()),
        "all_ancestry_gates": all(ancestry_gates.values()),
        "all_residual_receipt_gates": all(residual_receipt_gates.values()),
        "all_exactly_once_gates": all(exactly_once_gates.values()),
    }
    phase_audit.append("one_shot_holdout_completed_no_retraining")
    provenance_paths = {
        "benchmark_source_sha256": Path(__file__).resolve(),
        "deterministic_transition_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_transition_reactivation.py",
        "action_evaluator_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/project_two_action_benchmark.py",
        "manifest_file_sha256": manifest,
        "sealed_seed_file_sha256": sealed,
        "preregistration_sha256": repository_root / DEFAULT_PREREGISTRATION,
        "model_artifact_file_sha256": model_path,
    }
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": "D0 synthetic trained residual evidence; not paper evidence",
        "particle_budget": design.particle_budget,
        "training_seed_count": len(design.training_seeds),
        "validation_seed_count": len(design.validation_seeds),
        "holdout_seed_commitments": list(design.holdout_seed_commitments),
        "raw_holdout_seeds_disclosed": False,
        "phase_audit": phase_audit,
        "model": {
            "model_hash": model.model_hash,
            "model_file_sha256": model_file_sha256,
            "architecture": design.model.architecture,
            "training_example_count": model.training_example_count,
            "positive_target_rate": model.positive_target_rate,
            "training_loss": model.training_loss,
            "feature_names": list(model.feature_names),
            "forbidden_inference_inputs_consumed": [],
        },
        "validation": validation_reports,
        "families": family_reports,
        "paired_cluster_comparisons": comparisons,
        "family_primary_differences": family_primary,
        "runtime_operator_gates": operator_gates,
        "ancestry_gates": ancestry_gates,
        "residual_receipt_gates": residual_receipt_gates,
        "exactly_once_gates": exactly_once_gates,
        "gate_criteria": gate_criteria,
        "structured_residual_gate_passed": all(gate_criteria.values()),
        "provenance": {key: _file_sha256(path) for key, path in provenance_paths.items()},
        "limitations": [
            "D0 synthetic trained residual evidence only",
            "episode-level action advantage is a coarse conflict target",
            "repository-local sealed seeds",
            "corrected AMG remains a matched adapter",
            "no RGB-D or robot execution evidence",
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_structured_residual_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def verify_structured_residual_report(
    report_path: Path, *, repository_root: Path, recompute: bool = False
) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    stored = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError("structured residual content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("structured residual protocol mismatch")
    design = load_frozen_residual_design(repository_root / DEFAULT_MANIFEST)
    seeds = _load_and_verify_holdout_seeds(design, repository_root / DEFAULT_SEALED_SEEDS)
    if tuple(report.get("holdout_seed_commitments", ())) != design.holdout_seed_commitments:
        raise ValueError("structured residual commitment mismatch")
    if any(str(seed) in json.dumps(report) for seed in seeds):
        raise ValueError("structured residual raw holdout seed disclosure")
    if recompute:
        expected = run_structured_residual_gate(repository_root=repository_root)
        if expected["content_sha256"] != report["content_sha256"]:
            raise ValueError("structured residual deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_MANIFEST",
    "DEFAULT_MODEL_ARTIFACT",
    "DEFAULT_PREREGISTRATION",
    "DEFAULT_SEALED_SEEDS",
    "PROTOCOL_ID",
    "ResidualArm",
    "ResidualGateModel",
    "ResidualTrainingExample",
    "StructuredResidualParticleRuntime",
    "load_frozen_residual_design",
    "run_structured_residual_gate",
    "verify_structured_residual_report",
    "write_structured_residual_report",
]
