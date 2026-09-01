"""Information-matched online baselines for project one.

These are evaluation arms behind the existing ``ProjectOneMethod`` interface,
not a second production habit store.  Each arm keeps only its required online
sufficient statistics and exposes every tunable value in ``config_payload``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import sqrt

import numpy as np

from .project_one_dataset import ProjectOneDatasetRecord
from .project_one_methods import CategoricalBOCPDMethod, StepPrediction, _BaseMethod
from .project_one_protocol import CategoricalBOCPDConfig, ProjectOneDecision

__all__ = [
    "BOCPDMSConfig",
    "BOCPDMSMethod",
    "CUSUMConfig",
    "CUSUMMethod",
    "EWMAConfig",
    "EWMAMethod",
    "OrdinaryBOCPDMethod",
    "RLSFixedThresholdConfig",
    "RLSFixedThresholdMethod",
]


def _decision(score: float, threshold: float) -> ProjectOneDecision:
    return ProjectOneDecision.HABIT_CHANGE if score >= threshold else ProjectOneDecision.STABLE


class _FrequencySignalMethod(_BaseMethod):
    """Shared predictive side for EWMA and CUSUM, not shared detector state."""

    alpha: float

    def _reset_frequency(self) -> None:
        self._counts: dict[str, dict[str, float]] = defaultdict(
            lambda: dict.fromkeys(self.locations, 0.0)
        )

    def _predict(self, event: ProjectOneDatasetRecord) -> dict[str, float]:
        counts = self._counts[event.context_key]
        total = sum(counts.values()) + self.alpha * len(self.locations)
        return {name: (counts[name] + self.alpha) / total for name in self.locations}

    def _absorb(self, event: ProjectOneDatasetRecord) -> None:
        self._counts[event.context_key][event.observed_location] += event.observation_quality


@dataclass(frozen=True, slots=True)
class EWMAConfig:
    smoothing: float = 0.3
    threshold: float = 0.5
    alpha: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 < self.smoothing <= 1.0 or not 0.0 <= self.threshold <= 1.0:
            raise ValueError("invalid EWMA smoothing or threshold")
        if self.alpha <= 0.0:
            raise ValueError("EWMA alpha must be positive")


class EWMAMethod(_FrequencySignalMethod):
    def __init__(
        self,
        locations: Sequence[str],
        config: EWMAConfig | None = None,
        *,
        open_set: bool = False,
    ) -> None:
        super().__init__("ewma", locations, open_set=open_set)
        self.config = config or EWMAConfig()
        self.alpha = self.config.alpha
        self._reset_state()

    def _reset_state(self) -> None:
        self._reset_frequency()
        self._ewma = 0.0

    def config_payload(self) -> Mapping[str, object]:
        return {
            "kind": "ewma",
            "smoothing": self.config.smoothing,
            "threshold": self.config.threshold,
            "alpha": self.config.alpha,
            "locations": list(self.locations),
        }

    def _step(self, event: ProjectOneDatasetRecord, prior: Mapping[str, float]) -> StepPrediction:
        innovation = 1.0 - prior[event.observed_location]
        self._ewma = self.config.smoothing * innovation + (1.0 - self.config.smoothing) * self._ewma
        self._absorb(event)
        decision = _decision(self._ewma, self.config.threshold)
        return StepPrediction(
            event.event_id,
            dict(prior),
            self._ewma,
            decision.value,
            None,
            self._ewma,
            None,
            decision,
        )


@dataclass(frozen=True, slots=True)
class CUSUMConfig:
    reference: float = 0.25
    threshold: float = 1.0
    alpha: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.reference <= 1.0 or self.threshold <= 0.0:
            raise ValueError("invalid CUSUM reference or threshold")
        if self.alpha <= 0.0:
            raise ValueError("CUSUM alpha must be positive")


class CUSUMMethod(_FrequencySignalMethod):
    def __init__(
        self,
        locations: Sequence[str],
        config: CUSUMConfig | None = None,
        *,
        open_set: bool = False,
    ) -> None:
        super().__init__("cusum", locations, open_set=open_set)
        self.config = config or CUSUMConfig()
        self.alpha = self.config.alpha
        self._reset_state()

    def _reset_state(self) -> None:
        self._reset_frequency()
        self._cusum = 0.0

    def config_payload(self) -> Mapping[str, object]:
        return {
            "kind": "cusum",
            "reference": self.config.reference,
            "threshold": self.config.threshold,
            "alpha": self.config.alpha,
            "locations": list(self.locations),
        }

    def _step(self, event: ProjectOneDatasetRecord, prior: Mapping[str, float]) -> StepPrediction:
        innovation = 1.0 - prior[event.observed_location]
        self._cusum = max(0.0, self._cusum + innovation - self.config.reference)
        probability = min(1.0, self._cusum / self.config.threshold)
        decision = _decision(self._cusum, self.config.threshold)
        if decision is ProjectOneDecision.HABIT_CHANGE:
            self._cusum = 0.0
        self._absorb(event)
        return StepPrediction(
            event.event_id,
            dict(prior),
            probability,
            decision.value,
            None,
            probability,
            None,
            decision,
        )


@dataclass(frozen=True, slots=True)
class RLSFixedThresholdConfig:
    forgetting_factor: float = 0.99
    ridge: float = 1.0
    threshold: float = 0.5

    def __post_init__(self) -> None:
        if not 0.0 < self.forgetting_factor <= 1.0 or self.ridge <= 0.0:
            raise ValueError("invalid RLS forgetting factor or ridge")
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError("RLS threshold must lie in [0, 1]")


class RLSFixedThresholdMethod(_BaseMethod):
    """Multi-output RLS residual with a fixed, independently tuned threshold."""

    def __init__(
        self,
        locations: Sequence[str],
        config: RLSFixedThresholdConfig | None = None,
        *,
        open_set: bool = False,
    ) -> None:
        super().__init__("rls_fixed_threshold", locations, open_set=open_set)
        self.config = config or RLSFixedThresholdConfig()
        self._reset_state()

    def _reset_state(self) -> None:
        self._theta = np.zeros((2, len(self.locations)), dtype=float)
        self._covariance = np.eye(2, dtype=float) / self.config.ridge

    def config_payload(self) -> Mapping[str, object]:
        return {
            "kind": "rls_fixed_threshold",
            "forgetting_factor": self.config.forgetting_factor,
            "ridge": self.config.ridge,
            "threshold": self.config.threshold,
            "locations": list(self.locations),
        }

    @staticmethod
    def _features(event: ProjectOneDatasetRecord) -> np.ndarray:
        return np.array([1.0, np.tanh(event.context_value)], dtype=float)

    def _scores(self, event: ProjectOneDatasetRecord) -> np.ndarray:
        return self._features(event) @ self._theta

    def _predict(self, event: ProjectOneDatasetRecord) -> dict[str, float]:
        scores = self._scores(event)
        weights = np.exp(scores - float(np.max(scores)))
        weights /= float(np.sum(weights))
        return dict(zip(self.locations, (float(item) for item in weights), strict=True))

    def _step(self, event: ProjectOneDatasetRecord, prior: Mapping[str, float]) -> StepPrediction:
        x = self._features(event)
        target = np.zeros(len(self.locations), dtype=float)
        target[self.locations.index(event.observed_location)] = 1.0
        residual_vector = target - self._scores(event)
        residual = min(1.0, float(np.linalg.norm(residual_vector)) / sqrt(2.0))
        px = self._covariance @ x
        gain = px / (self.config.forgetting_factor + float(x @ px))
        self._theta += event.observation_quality * np.outer(gain, residual_vector)
        self._covariance = (
            self._covariance - np.outer(gain, x) @ self._covariance
        ) / self.config.forgetting_factor
        decision = _decision(residual, self.config.threshold)
        return StepPrediction(
            event.event_id,
            dict(prior),
            residual,
            decision.value,
            None,
            residual,
            residual,
            decision,
        )


class OrdinaryBOCPDMethod(CategoricalBOCPDMethod):
    """Ordinary categorical BOCPD without context-conditioned statistics."""

    def __init__(
        self,
        locations: Sequence[str],
        config: CategoricalBOCPDConfig | None = None,
        *,
        open_set: bool = False,
    ) -> None:
        base = config or CategoricalBOCPDConfig()
        super().__init__(locations, replace(base, context_conditioned=False), open_set=open_set)
        self.name = "ordinary_bocpd"


@dataclass(frozen=True, slots=True)
class BOCPDMSConfig:
    expected_run_length: float = 50.0
    change_threshold: float = 0.2
    model_switch_probability: float = 0.05
    dirichlet_alpha: float = 1.0
    max_run_length: int = 100

    def __post_init__(self) -> None:
        if self.expected_run_length <= 1.0 or self.dirichlet_alpha <= 0.0:
            raise ValueError("invalid BOCPDMS run length or prior")
        if not 0.0 <= self.change_threshold <= 1.0:
            raise ValueError("BOCPDMS threshold must lie in [0, 1]")
        if not 0.0 <= self.model_switch_probability <= 0.5:
            raise ValueError("BOCPDMS switch probability must lie in [0, 0.5]")


class BOCPDMSMethod(_BaseMethod):
    """Online model-selection mixture of ordinary and contextual BOCPD."""

    def __init__(
        self,
        locations: Sequence[str],
        config: BOCPDMSConfig | None = None,
        *,
        open_set: bool = False,
    ) -> None:
        super().__init__("bocpdms", locations, open_set=open_set)
        self.config = config or BOCPDMSConfig()
        self._reset_state()

    def _model_config(self, contextual: bool) -> CategoricalBOCPDConfig:
        return CategoricalBOCPDConfig(
            expected_run_length=self.config.expected_run_length,
            dirichlet_alpha=self.config.dirichlet_alpha,
            change_threshold=self.config.change_threshold,
            max_run_length=self.config.max_run_length,
            context_conditioned=contextual,
        )

    def _reset_state(self) -> None:
        self._models = (
            CategoricalBOCPDMethod(self.locations, self._model_config(False)),
            CategoricalBOCPDMethod(self.locations, self._model_config(True)),
        )
        self._model_weights: tuple[float, ...] = (0.5, 0.5)
        self._component_priors: tuple[dict[str, float], ...] = ()

    def config_payload(self) -> Mapping[str, object]:
        return {
            "kind": "bocpdms",
            "expected_run_length": self.config.expected_run_length,
            "change_threshold": self.config.change_threshold,
            "model_switch_probability": self.config.model_switch_probability,
            "dirichlet_alpha": self.config.dirichlet_alpha,
            "max_run_length": self.config.max_run_length,
            "locations": list(self.locations),
        }

    def _predict(self, event: ProjectOneDatasetRecord) -> dict[str, float]:
        self._component_priors = tuple(model._predict(event) for model in self._models)
        return {
            location: sum(
                weight * component[location]
                for weight, component in zip(
                    self._model_weights, self._component_priors, strict=True
                )
            )
            for location in self.locations
        }

    def _step(self, event: ProjectOneDatasetRecord, prior: Mapping[str, float]) -> StepPrediction:
        switch = self.config.model_switch_probability
        transitioned = (
            self._model_weights[0] * (1.0 - switch) + self._model_weights[1] * switch,
            self._model_weights[1] * (1.0 - switch) + self._model_weights[0] * switch,
        )
        likelihoods = tuple(
            component[event.observed_location] for component in self._component_priors
        )
        unnormalized = tuple(
            weight * likelihood
            for weight, likelihood in zip(transitioned, likelihoods, strict=True)
        )
        normalizer = sum(unnormalized) or 1.0
        self._model_weights = tuple(value / normalizer for value in unnormalized)
        components = tuple(model.observe(event) for model in self._models)
        change_probability = min(
            1.0,
            sum(
                weight * component.change_probability
                for weight, component in zip(self._model_weights, components, strict=True)
            ),
        )
        decision = _decision(change_probability, self.config.change_threshold)
        return StepPrediction(
            event.event_id,
            dict(prior),
            change_probability,
            decision.value,
            None,
            change_probability,
            None,
            decision,
        )

    def snapshot(self) -> Mapping[str, object]:
        return {**super().snapshot(), "model_weights": list(self._model_weights)}
