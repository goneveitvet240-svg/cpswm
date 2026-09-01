"""Frozen gate for a trained neural amortized cause/regime proposal."""

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
    GateReading,
    TransitionReactivationArm,
    _TransitionReactivationState,
)
from cpswm.system.evaluation_operations.structure_two_transition_reactivation import (
    _evaluate as _transition_evaluate,
)
from cpswm.system.reproducibility import content_sha256
from cpswm.world_model.habits_transitions import ChangeCause

PROTOCOL_ID = "structure-two-neural-amortized-proposal-gate@0.1"
DEFAULT_MANIFEST = Path(
    "configs/project_two_experiments/structure_two_neural_amortized_manifest_v0_1.json"
)
DEFAULT_SEALED_SEEDS = Path(
    "configs/project_two_experiments/structure_two_neural_amortized_sealed_seeds_v0_1.json"
)
DEFAULT_PREREGISTRATION = Path(
    "docs/experiments/structure_two_neural_amortized_proposal_gate_preregistration_2026-08-29.md"
)
DEFAULT_MODEL_ARTIFACT = Path(
    "artifacts/project_two_v04_development/structure_two_neural_amortized_model_v0_1.json"
)

CAUSES = tuple(ChangeCause)
FEATURE_NAMES = (
    *(f"visible_cause_probability:{cause.value}" for cause in CAUSES),
    "visible_regime_change_probability",
    "visible_identity_target_probability",
    "visible_owner_actor_probability",
    "visible_max_actor_probability",
    "visible_actor_entropy",
    *(f"parent_cause:{cause.value}" for cause in CAUSES),
    "parent_regime_change",
    "parent_posterior_probability",
    "parent_run_length_capped",
)
FORBIDDEN_INPUTS = {
    "oracle_action",
    "latent_actor",
    "latent_cause",
    "latent_regime",
    "holdout_seed",
}


class NeuralProposalArm(StrEnum):
    CORRECTED_AMG = "corrected_amg"
    PER_STEP_PARTICLE = "per_step_particle_projection"
    SEQUENTIAL_NO_CONSOLIDATION = "sequential_particle_no_consolidation"
    DETERMINISTIC_TRANSITION = "deterministic_transition_no_consolidation"
    NEURAL_TRANSITION = "neural_transition_no_consolidation"
    HISTORICAL_REACTIVATION = "historical_regime_reactivation"
    NEURAL_JOINT = "neural_transition_reactivation_joint"


@dataclass(frozen=True, slots=True)
class NeuralModelConfig:
    architecture: str
    hidden_units: int
    epochs: int
    learning_rate: float
    l2: float
    initialization_seed: int
    target_semantics: str
    forbidden_inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NeuralGateDesign:
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
    deterministic_noninferiority_margin: float
    guardrail_noninferiority_margin: float
    manifest_file_sha256: str


@dataclass(frozen=True, slots=True)
class TrainingExample:
    features: tuple[float, ...]
    cause_target: int
    regime_target: float


@dataclass(frozen=True, slots=True)
class NeuralProposalModel:
    feature_names: tuple[str, ...]
    hidden_weights: tuple[tuple[float, ...], ...]
    hidden_bias: tuple[float, ...]
    output_weights: tuple[tuple[float, ...], ...]
    output_bias: tuple[float, ...]
    training_example_count: int
    training_loss: float
    config: NeuralModelConfig

    def predict(self, features: Sequence[float]) -> tuple[dict[ChangeCause, float], float]:
        if len(features) != len(self.feature_names):
            raise ValueError("neural proposal feature width mismatch")
        hidden = [
            math.tanh(
                bias + sum(weight * value for weight, value in zip(row, features, strict=True))
            )
            for row, bias in zip(self.hidden_weights, self.hidden_bias, strict=True)
        ]
        logits = [
            bias + sum(weight * value for weight, value in zip(row, hidden, strict=True))
            for row, bias in zip(self.output_weights, self.output_bias, strict=True)
        ]
        cause_logits = logits[: len(CAUSES)]
        maximum = max(cause_logits)
        masses = [math.exp(value - maximum) for value in cause_logits]
        total = sum(masses)
        cause = {item: masses[index] / total for index, item in enumerate(CAUSES)}
        regime = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, logits[-1]))))
        return cause, regime

    def payload(self) -> dict[str, Any]:
        return {
            "protocol": PROTOCOL_ID,
            "model_type": "trained_one_hidden_layer_mlp",
            "feature_names": list(self.feature_names),
            "hidden_weights": [list(row) for row in self.hidden_weights],
            "hidden_bias": list(self.hidden_bias),
            "output_weights": [list(row) for row in self.output_weights],
            "output_bias": list(self.output_bias),
            "training_example_count": self.training_example_count,
            "training_loss": self.training_loss,
            "config": asdict(self.config),
            "training_data_boundary": "training_seeds_visible_beliefs_only",
        }

    @property
    def model_hash(self) -> str:
        return str(content_sha256(self.payload()))


def load_frozen_neural_design(manifest_path: Path = DEFAULT_MANIFEST) -> NeuralGateDesign:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("neural proposal manifest protocol mismatch")
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
    design = NeuralGateDesign(
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
        deterministic_noninferiority_margin=float(payload["deterministic_noninferiority_margin"]),
        guardrail_noninferiority_margin=float(payload["guardrail_noninferiority_margin"]),
        manifest_file_sha256=_file_sha256(manifest_path),
    )
    if len(FEATURE_NAMES) != 16 or design.model.hidden_units != 8:
        raise ValueError("neural proposal freezes a 16x8x5 MLP")
    if set(design.search_spaces) != {arm.value for arm in NeuralProposalArm}:
        raise ValueError("neural proposal search-space arm mismatch")
    if len(families) != 4 or design.particle_budget != FROZEN_PARTICLE_BUDGET:
        raise ValueError("neural proposal freezes four families and K=24")
    if set(design.training_seeds) & set(design.validation_seeds):
        raise ValueError("training and validation seeds overlap")
    if set(FEATURE_NAMES) & FORBIDDEN_INPUTS:
        raise ValueError("forbidden neural proposal feature")
    if set(design.model.forbidden_inputs) != FORBIDDEN_INPUTS:
        raise ValueError("forbidden input declaration mismatch")
    return design


def _load_and_verify_holdout_seeds(
    design: NeuralGateDesign, sealed_seed_path: Path
) -> tuple[int, ...]:
    if _file_sha256(sealed_seed_path) != design.sealed_seed_file_sha256:
        raise ValueError("neural proposal sealed seed hash mismatch")
    payload = json.loads(sealed_seed_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("neural proposal sealed protocol mismatch")
    seeds = tuple(payload["holdout_seeds"])
    salt = payload["commitment_salt"]
    commitments = tuple(
        hashlib.sha256(f"{PROTOCOL_ID}:{seed}:{salt}".encode()).hexdigest() for seed in seeds
    )
    if commitments != design.holdout_seed_commitments:
        raise ValueError("neural proposal holdout commitments mismatch")
    if (set(seeds) & set(design.training_seeds)) or (set(seeds) & set(design.validation_seeds)):
        raise ValueError("neural proposal train/validation/holdout overlap")
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


def _feature_vector(
    belief: MultiAxisBelief, parent: PersistentParticle | None
) -> tuple[float, ...]:
    actor_values = tuple(float(value) for value in belief.actor_posterior.values())
    entropy = -sum(value * math.log(max(value, 1e-12)) for value in actor_values)
    owner_probability = float(belief.actor_posterior.get(belief.owner_actor_key, 0.0))
    parent_cause = (
        {cause: 0.0 for cause in CAUSES}
        if parent is None
        else {cause: float(parent.hypothesis.cause is cause) for cause in CAUSES}
    )
    return (
        *(float(belief.cause_posterior[cause]) for cause in CAUSES),
        float(belief.regime_change_probability),
        float(belief.identity_target_probability),
        owner_probability,
        max(actor_values),
        entropy,
        *(parent_cause[cause] for cause in CAUSES),
        0.0 if parent is None else float(parent.hypothesis.regime_change),
        0.0 if parent is None else float(parent.posterior_probability),
        0.0 if parent is None else min(1.0, parent.run_length / 10.0),
    )


class _TrainingRecorderRuntime(SequentialParticleRuntime):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__(profile="balanced")
        self.examples: list[TrainingExample] = []

    def revise(self, belief: MultiAxisBelief) -> tuple[PersistentParticle, ...]:
        parent = (
            None
            if not self.particles
            else max(self.particles, key=lambda item: (item.posterior_probability, item.signature))
        )
        modal = max(
            CAUSES,
            key=lambda cause: (belief.cause_posterior[cause], cause.value),
        )
        self.examples.append(
            TrainingExample(
                features=_feature_vector(belief, parent),
                cause_target=CAUSES.index(modal),
                regime_target=float(belief.regime_change_probability >= 0.5),
            )
        )
        return tuple(super().revise(belief))


def _collect_training_examples(
    design: NeuralGateDesign, evaluator: ProjectTwoActionBenchmarkV02
) -> tuple[TrainingExample, ...]:
    examples: list[TrainingExample] = []
    for family_index, family in enumerate(design.families):
        dataset = _dataset(
            family,
            validation_seeds=design.training_seeds,
            test_seeds=(108901 + family_index,),
            max_steps=design.max_steps,
            split_label="training-visible-only",
        )
        for episode in dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION):
            base = _FullProjectTwoMethod(
                episode, owner_threshold=0.4, action_readout=_action_readout()
            )
            core = _TransitionReactivationState(
                base,
                episode,
                profile="balanced",
                conflict_transition=False,
                reactivation=False,
            )
            recorder = _TrainingRecorderRuntime()
            core._runtime = recorder
            state: Any = _CIAVState(core, dataset, episode, enabled=True, cost_multiplier=1.0)
            state = _TargetObjectRoutingState(state)
            state = _VisibleTransformState(state, _visible_transform(family, episode))
            state = _FamilyFeedbackState(state, family, episode)
            evaluator.evaluate_custom_state(dataset, episode, state)
            examples.extend(recorder.examples)
    if not examples:
        raise ValueError("neural proposal training set is empty")
    return tuple(examples)


def _train_model(
    examples: Sequence[TrainingExample], config: NeuralModelConfig
) -> NeuralProposalModel:
    rng = random.Random(config.initialization_seed)
    input_width = len(FEATURE_NAMES)
    output_width = len(CAUSES) + 1
    hidden = config.hidden_units
    w1 = [[rng.uniform(-0.12, 0.12) for _ in range(input_width)] for _ in range(hidden)]
    b1 = [0.0 for _ in range(hidden)]
    w2 = [[rng.uniform(-0.12, 0.12) for _ in range(hidden)] for _ in range(output_width)]
    b2 = [0.0 for _ in range(output_width)]
    final_loss = 0.0
    for _ in range(config.epochs):
        gw1 = [[0.0 for _ in range(input_width)] for _ in range(hidden)]
        gb1 = [0.0 for _ in range(hidden)]
        gw2 = [[0.0 for _ in range(hidden)] for _ in range(output_width)]
        gb2 = [0.0 for _ in range(output_width)]
        loss = 0.0
        for example in examples:
            h = [
                math.tanh(b1[j] + sum(w1[j][i] * example.features[i] for i in range(input_width)))
                for j in range(hidden)
            ]
            logits = [
                b2[k] + sum(w2[k][j] * h[j] for j in range(hidden)) for k in range(output_width)
            ]
            maximum = max(logits[: len(CAUSES)])
            masses = [math.exp(value - maximum) for value in logits[: len(CAUSES)]]
            total = sum(masses)
            cause_probs = [value / total for value in masses]
            regime_prob = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, logits[-1]))))
            loss -= math.log(max(cause_probs[example.cause_target], 1e-12))
            loss -= example.regime_target * math.log(max(regime_prob, 1e-12))
            loss -= (1.0 - example.regime_target) * math.log(max(1.0 - regime_prob, 1e-12))
            delta = [*cause_probs, regime_prob - example.regime_target]
            delta[example.cause_target] -= 1.0
            for k in range(output_width):
                gb2[k] += delta[k]
                for j in range(hidden):
                    gw2[k][j] += delta[k] * h[j]
            for j in range(hidden):
                hidden_delta = sum(delta[k] * w2[k][j] for k in range(output_width)) * (
                    1.0 - h[j] ** 2
                )
                gb1[j] += hidden_delta
                for i in range(input_width):
                    gw1[j][i] += hidden_delta * example.features[i]
        count = float(len(examples))
        rate = config.learning_rate
        for j in range(hidden):
            b1[j] -= rate * gb1[j] / count
            for i in range(input_width):
                w1[j][i] -= rate * (gw1[j][i] / count + config.l2 * w1[j][i])
        for k in range(output_width):
            b2[k] -= rate * gb2[k] / count
            for j in range(hidden):
                w2[k][j] -= rate * (gw2[k][j] / count + config.l2 * w2[k][j])
        final_loss = loss / count
    return NeuralProposalModel(
        feature_names=tuple(FEATURE_NAMES),
        hidden_weights=tuple(tuple(value for value in row) for row in w1),
        hidden_bias=tuple(b1),
        output_weights=tuple(tuple(value for value in row) for row in w2),
        output_bias=tuple(b2),
        training_example_count=len(examples),
        training_loss=final_loss,
        config=config,
    )


class NeuralAmortizedParticleRuntime(SequentialParticleRuntime):  # type: ignore[misc]
    """A trained visible-belief MLP proposes cause/regime transitions."""

    def __init__(self, *, profile: str, model: NeuralProposalModel, mix: float) -> None:
        super().__init__(profile=profile)
        self.particles: tuple[PersistentParticle, ...] = tuple(getattr(self, "particles", ()))
        self.step_index = int(getattr(self, "step_index", 0))
        if not 0.0 <= mix <= 1.0:
            raise ValueError("neural proposal mix must be in [0, 1]")
        self.model = model
        self.mix = mix
        self.neural_proposal_receipts: list[str] = []

    def revise(self, belief: MultiAxisBelief) -> tuple[PersistentParticle, ...]:
        parent = (
            None
            if not self.particles
            else max(self.particles, key=lambda item: (item.posterior_probability, item.signature))
        )
        predicted_cause, predicted_regime = self.model.predict(_feature_vector(belief, parent))
        proposal_belief = belief
        if parent is not None:
            modal = max(CAUSES, key=lambda cause: (predicted_cause[cause], cause.value))
            regime_change = predicted_regime >= 0.5
            cause_conflict = parent.hypothesis.cause is not modal and predicted_cause[modal] >= 0.35
            regime_conflict = (
                parent.hypothesis.regime_change != regime_change
                and abs(predicted_regime - 0.5) >= 0.10
            )
            if cause_conflict or regime_conflict:
                cause = _normalize(
                    {
                        item: (1.0 - self.mix) * belief.cause_posterior[item]
                        + self.mix * predicted_cause[item]
                        for item in CAUSES
                    }
                )
                proposal_belief = replace(
                    belief,
                    cause_posterior=cause,
                    regime_change_probability=(
                        (1.0 - self.mix) * belief.regime_change_probability
                        + self.mix * predicted_regime
                    ),
                )
                uniform = 1.0 / len(self.particles)
                self.particles = tuple(
                    replace(particle, posterior_probability=uniform) for particle in self.particles
                )
                self.neural_proposal_receipts.append(
                    content_sha256(
                        {
                            "model_hash": self.model.model_hash,
                            "step_index": self.step_index + 1,
                            "parent_signature": parent.signature,
                            "predicted_cause": sorted(
                                (cause.value, value) for cause, value in predicted_cause.items()
                            ),
                            "predicted_regime": predicted_regime,
                            "mix": self.mix,
                        }
                    )
                )
        return tuple(super().revise(proposal_belief))


def _parse_neural_parameter(parameter: Any) -> tuple[str, float]:
    profile, raw_mix = str(parameter).split(":", maxsplit=1)
    return profile, float(raw_mix)


def _evaluate(
    evaluator: ProjectTwoActionBenchmarkV02,
    dataset: ProjectTwoReplayDataset,
    episode: Any,
    family: SequentialGateFamily,
    arm: NeuralProposalArm,
    parameter: Any,
    model: NeuralProposalModel,
) -> tuple[GateReading, int]:
    mapping = {
        NeuralProposalArm.CORRECTED_AMG: TransitionReactivationArm.CORRECTED_AMG,
        NeuralProposalArm.PER_STEP_PARTICLE: TransitionReactivationArm.PER_STEP_PARTICLE,
        NeuralProposalArm.SEQUENTIAL_NO_CONSOLIDATION: (
            TransitionReactivationArm.SEQUENTIAL_NO_CONSOLIDATION
        ),
        NeuralProposalArm.DETERMINISTIC_TRANSITION: (
            TransitionReactivationArm.CONFLICT_TRANSITION_NO_CONSOLIDATION
        ),
        NeuralProposalArm.HISTORICAL_REACTIVATION: (
            TransitionReactivationArm.HISTORICAL_REACTIVATION
        ),
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
    profile, mix = _parse_neural_parameter(parameter)
    base = _FullProjectTwoMethod(episode, owner_threshold=0.4, action_readout=_action_readout())
    core = _TransitionReactivationState(
        base,
        episode,
        profile=profile,
        conflict_transition=False,
        reactivation=arm is NeuralProposalArm.NEURAL_JOINT,
    )
    runtime = NeuralAmortizedParticleRuntime(profile=profile, model=model, mix=mix)
    core._runtime = runtime
    state: Any = _CIAVState(core, dataset, episode, enabled=True, cost_multiplier=1.0)
    state.operator_retention_receipt = {**state.operator_retention_receipt, "ciav": True}
    state = _TargetObjectRoutingState(state)
    state = _VisibleTransformState(state, _visible_transform(family, episode))
    state = _FamilyFeedbackState(state, family, episode)
    metric = evaluator.evaluate_custom_state(dataset, episode, state)
    return (
        GateReading(
            metric=metric,
            verification_cost=float(getattr(state, "verification_cost", 0.0)),
            ancestry_edge_count=int(getattr(state, "ancestry_edge_count", 0)),
            operator_retention_receipt=getattr(state, "operator_retention_receipt", None),
            consumed_visible_stream_hash=str(getattr(state, "consumed_visible_stream_hash", "")),
            conflict_transition_count=len(runtime.neural_proposal_receipts),
            reactivation_count=int(getattr(state, "reactivation_count", 0)),
            duplicate_promotion_count=int(getattr(state, "duplicate_promotion_count", 0)),
        ),
        len(runtime.neural_proposal_receipts),
    )


def _bootstrap_ci(values: list[float], *, draws: int = 4000) -> tuple[float, float]:
    rng = random.Random(f"{PROTOCOL_ID}:paired-cluster-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


COMPARISONS = {
    "neural_transition_minus_sequential_no_consolidation": (
        NeuralProposalArm.NEURAL_TRANSITION,
        NeuralProposalArm.SEQUENTIAL_NO_CONSOLIDATION,
    ),
    "neural_transition_minus_deterministic_transition": (
        NeuralProposalArm.NEURAL_TRANSITION,
        NeuralProposalArm.DETERMINISTIC_TRANSITION,
    ),
    "deterministic_transition_minus_sequential_no_consolidation": (
        NeuralProposalArm.DETERMINISTIC_TRANSITION,
        NeuralProposalArm.SEQUENTIAL_NO_CONSOLIDATION,
    ),
    "reactivation_minus_sequential_no_consolidation": (
        NeuralProposalArm.HISTORICAL_REACTIVATION,
        NeuralProposalArm.SEQUENTIAL_NO_CONSOLIDATION,
    ),
    "neural_joint_minus_neural_transition": (
        NeuralProposalArm.NEURAL_JOINT,
        NeuralProposalArm.NEURAL_TRANSITION,
    ),
    "neural_joint_minus_corrected_amg": (
        NeuralProposalArm.NEURAL_JOINT,
        NeuralProposalArm.CORRECTED_AMG,
    ),
}


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
        "neural_proposal_count": sum(item[1] for item in values),
        "reactivation_count": sum(item.reactivation_count for item in readings),
        "duplicate_promotion_count": sum(item.duplicate_promotion_count for item in readings),
    }


def run_neural_amortized_gate(*, repository_root: Path) -> dict[str, Any]:
    manifest = repository_root / DEFAULT_MANIFEST
    sealed = repository_root / DEFAULT_SEALED_SEEDS
    model_path = repository_root / DEFAULT_MODEL_ARTIFACT
    design = load_frozen_neural_design(manifest)
    evaluator = ProjectTwoActionBenchmarkV02()
    phase_audit = ["training_started_without_sealed_seed_access"]
    examples = _collect_training_examples(design, evaluator)
    model = _train_model(examples, design.model)
    model_payload = {**model.payload(), "model_hash": model.model_hash}
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(json.dumps(model_payload, indent=2) + "\n", encoding="utf-8")
    model_file_sha256 = _file_sha256(model_path)
    phase_audit.extend(("training_completed", "model_artifact_frozen", "validation_started"))

    selected: dict[str, dict[NeuralProposalArm, Any]] = {}
    validation_reports: dict[str, Any] = {}
    for family_index, family in enumerate(design.families):
        dataset = _dataset(
            family,
            validation_seeds=design.validation_seeds,
            test_seeds=(108951 + family_index,),
            max_steps=design.max_steps,
            split_label="validation",
        )
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
        selected[family.family_id] = {}
        validation_reports[family.family_id] = {}
        for arm in NeuralProposalArm:
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
    neural_receipt_gates: dict[str, bool] = {}
    exactly_once_gates: dict[str, bool] = {}
    for family_index, family in enumerate(design.families):
        dataset = _dataset(
            family,
            validation_seeds=(108971 + family_index,),
            test_seeds=holdout_seeds,
            max_steps=design.max_steps,
            split_label="sealed-holdout",
        )
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        holdout_readings: dict[NeuralProposalArm, list[tuple[GateReading, int]]] = {
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
            for arm in NeuralProposalArm
        }
        for arm in NeuralProposalArm:
            if arm is NeuralProposalArm.CORRECTED_AMG:
                continue
            operator_gates[f"{family.family_id}:{arm.value}"] = all(
                item[0].operator_retention_receipt == expected_operator_receipt
                for item in holdout_readings[arm]
            )
            if arm is not NeuralProposalArm.PER_STEP_PARTICLE:
                ancestry_gates[f"{family.family_id}:{arm.value}"] = all(
                    item[0].ancestry_edge_count > 0 for item in holdout_readings[arm]
                )
        for arm in (NeuralProposalArm.NEURAL_TRANSITION, NeuralProposalArm.NEURAL_JOINT):
            neural_receipt_gates[f"{family.family_id}:{arm.value}"] = any(
                item[1] > 0 for item in holdout_readings[arm]
            )
        exactly_once_gates[family.family_id] = all(
            item[0].duplicate_promotion_count == 0
            for arm in (NeuralProposalArm.HISTORICAL_REACTIVATION, NeuralProposalArm.NEURAL_JOINT)
            for item in holdout_readings[arm]
        )
        rows = []
        for index, commitment in enumerate(design.holdout_seed_commitments):
            hashes = {
                arm.value: holdout_readings[arm][index][0].consumed_visible_stream_hash
                for arm in NeuralProposalArm
            }
            if len(set(hashes.values())) != 1:
                raise ValueError("neural proposal consumed visible stream mismatch")
            losses = {
                arm.value: holdout_readings[arm][index][0].net_action_loss_per_step
                for arm in NeuralProposalArm
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
    primary = "neural_transition_minus_sequential_no_consolidation"
    family_primary = {
        family_id: mean(row["paired_differences"][primary] for row in report["paired_holdout_rows"])
        for family_id, report in family_reports.items()
    }
    roles = {family.family_role: family.family_id for family in design.families}
    gate_criteria = {
        "primary_ci_upper_below_zero": comparisons[primary]["confidence_interval_95"][1] < 0.0,
        "deterministic_noninferiority": comparisons[
            "neural_transition_minus_deterministic_transition"
        ]["confidence_interval_95"][1]
        <= design.deterministic_noninferiority_margin,
        "required_cause_gain": family_primary[roles["required_cause_gain"]] < 0.0,
        "required_regime_gain": family_primary[roles["required_regime_gain"]] < 0.0,
        "identity_guardrail": family_primary[roles["identity_guardrail"]]
        <= design.guardrail_noninferiority_margin,
        "role_guardrail": family_primary[roles["role_guardrail"]]
        <= design.guardrail_noninferiority_margin,
        "trained_model_frozen_before_holdout": phase_audit.index("model_artifact_frozen")
        < phase_audit.index("sealed_seed_file_open_requested"),
        "no_forbidden_model_inputs": not (set(model.feature_names) & FORBIDDEN_INPUTS),
        "all_operator_gates": all(operator_gates.values()),
        "all_ancestry_gates": all(ancestry_gates.values()),
        "all_neural_receipt_gates": all(neural_receipt_gates.values()),
        "all_exactly_once_gates": all(exactly_once_gates.values()),
    }
    phase_audit.append("one_shot_holdout_completed_no_retraining")
    provenance_paths = {
        "benchmark_source_sha256": Path(__file__).resolve(),
        "transition_source_sha256": repository_root
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
        "evidence_status": "D0 synthetic trained-mechanism evidence; not paper evidence",
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
            "training_loss": model.training_loss,
            "feature_names": list(model.feature_names),
            "forbidden_inputs_consumed": [],
        },
        "validation": validation_reports,
        "families": family_reports,
        "paired_cluster_comparisons": comparisons,
        "family_primary_differences": family_primary,
        "runtime_operator_gates": operator_gates,
        "ancestry_gates": ancestry_gates,
        "neural_receipt_gates": neural_receipt_gates,
        "exactly_once_gates": exactly_once_gates,
        "gate_criteria": gate_criteria,
        "neural_mechanism_gate_passed": all(gate_criteria.values()),
        "provenance": {key: _file_sha256(path) for key, path in provenance_paths.items()},
        "limitations": [
            "D0 synthetic trained-mechanism evidence only",
            "visible-belief self-distillation targets rather than external labels",
            "repository-local sealed seeds",
            "corrected AMG remains a matched adapter",
            "no RGB-D or robot execution evidence",
        ],
    }
    report["content_sha256"] = content_sha256(report)
    return report


def write_neural_amortized_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def verify_neural_amortized_report(
    report_path: Path, *, repository_root: Path, recompute: bool = False
) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    stored = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError("neural proposal content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("neural proposal protocol mismatch")
    design = load_frozen_neural_design(repository_root / DEFAULT_MANIFEST)
    seeds = _load_and_verify_holdout_seeds(design, repository_root / DEFAULT_SEALED_SEEDS)
    if tuple(report.get("holdout_seed_commitments", ())) != design.holdout_seed_commitments:
        raise ValueError("neural proposal commitment mismatch")
    if any(str(seed) in json.dumps(report) for seed in seeds):
        raise ValueError("neural proposal raw holdout seed disclosure")
    if recompute:
        expected = run_neural_amortized_gate(repository_root=repository_root)
        if expected["content_sha256"] != report["content_sha256"]:
            raise ValueError("neural proposal deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_MANIFEST",
    "DEFAULT_MODEL_ARTIFACT",
    "DEFAULT_PREREGISTRATION",
    "DEFAULT_SEALED_SEEDS",
    "FEATURE_NAMES",
    "PROTOCOL_ID",
    "NeuralAmortizedParticleRuntime",
    "NeuralProposalArm",
    "load_frozen_neural_design",
    "run_neural_amortized_gate",
    "verify_neural_amortized_report",
    "write_neural_amortized_report",
]
