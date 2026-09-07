"""Fresh-seed strongest-neighbor death test for CARE-WM in Structure Two.

The external-system arms are reduced matched-interface proxies, not verified
official-code reproductions.  Evaluator
truth remains outside every non-oracle decision and is exposed to CARE only
after a physical verification action has been selected from visible state.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path
from statistics import mean
from typing import Any, cast
from uuid import UUID

from cpswm.contracts import (
    ProjectTwoDataMaturity,
    ProjectTwoDatasetSplit,
    ProjectTwoReplayEpisode,
    ProjectTwoReplayStep,
)
from cpswm.system.evaluation_operations.care_wm_exact_counterfactual import (
    _serialized_report_discloses_seed,
)
from cpswm.system.evaluation_operations.project_two_action_benchmark import (
    ActionCaseMetric,
    ProjectTwoActionBenchmarkV02,
    _AMGOpenWorldMethod,
    _CountMethod,
    _FullProjectTwoMethod,
    _FullRerunMethod,
    _Prediction,
)
from cpswm.system.evaluation_operations.project_two_dataset import ProjectTwoReplayDataset
from cpswm.system.evaluation_operations.project_two_dataset_adapters import (
    D0SyntheticOracleReplayAdapter,
)
from cpswm.system.evaluation_operations.project_two_replay_importer import (
    ProjectTwoReplayFileImporter,
)
from cpswm.system.evaluation_operations.structure_two_fresh_triarm import (
    MultiAxisBelief,
    _action_readout,
    _argmax_distribution,
    _FamilyFeedbackState,
    _file_sha256,
    _normalize,
    _rank_distribution,
    _VisibleTransformState,
)
from cpswm.system.evaluation_operations.structure_two_rejuvenation_gate import (
    FROZEN_PARTICLE_BUDGET,
)
from cpswm.system.evaluation_operations.structure_two_sequential_gate import (
    PersistentParticle,
    ReversibleParticleConsolidationLedger,
    SequentialGateArm,
    SequentialGateFamily,
    _SequentialMultiAxisActionState,
    _TargetObjectRoutingState,
    _visible_transform,
)
from cpswm.system.evaluation_operations.structure_two_sequential_gate import (
    _state_for_arm as _sequential_state_for_arm,
)
from cpswm.system.reproducibility import content_sha256

PROTOCOL_ID = "structure-two-strongest-neighbor-gate@0.1"
DEFAULT_MANIFEST = Path(
    "configs/project_two_experiments/structure_two_strongest_neighbor_manifest_v0_1.json"
)
DEFAULT_SEALED_SEEDS = Path(
    "configs/project_two_experiments/structure_two_strongest_neighbor_sealed_seeds_v0_1.json"
)
DEFAULT_PREREGISTRATION = Path(
    "docs/experiments/structure_two_strongest_neighbor_gate_preregistration_2026-08-29.md"
)
DEFAULT_PRIOR_ART = Path("docs/experiments/care_wm_prior_art_checkpoint_2026-08-29.md")


class NeighborArm(StrEnum):
    CORRECTED_AMG = "corrected_amg"
    O_STAR_MATCHED = "o_star_matched"
    NO_CONSOLIDATION = "sequential_no_consolidation"
    ACTIVE_DREAMING = "active_dreaming_matched"
    AUTO_DREAMER = "auto_dreamer_matched"
    TRUSTMEM = "trustmem_matched"
    BRAINCTL = "brainctl_matched"
    CARE_NO_ACTION_REGRET = "care_no_action_regret"
    CARE_WM = "care_wm"
    FULL_RERUN = "full_rerun"
    ORACLE = "full_rerun_oracle"


class MemoryDecision(StrEnum):
    PROMOTE = "promote"
    ESCROW = "escrow"
    VERIFY = "physically_verify"


PUBLISHED_NEIGHBOR_ARMS = {
    NeighborArm.ACTIVE_DREAMING,
    NeighborArm.AUTO_DREAMER,
    NeighborArm.TRUSTMEM,
    NeighborArm.BRAINCTL,
}


@dataclass(frozen=True, slots=True)
class NeighborFamily:
    family_id: str
    family_role: str
    guest_window: tuple[int, int]
    abrupt_day: int
    recurrence_day: int
    observation_coverage: float
    unknown_event_days: tuple[int, ...]
    actor_ambiguity_mix: float
    identity_confidence_scale: float
    feedback_flip_rate: float
    decoy_days: tuple[int, ...]
    actual_action_cost: float
    predicted_action_cost: float
    verification_cost: float
    repair_cost: float
    physical_verification_reliability: float

    def sequential_family(self) -> SequentialGateFamily:
        return SequentialGateFamily(
            family_id=self.family_id,
            family_role=self.family_role,
            guest_window=self.guest_window,
            abrupt_day=self.abrupt_day,
            recurrence_day=self.recurrence_day,
            observation_coverage=self.observation_coverage,
            unknown_event_days=self.unknown_event_days,
            actor_ambiguity_mix=self.actor_ambiguity_mix,
            identity_confidence_scale=self.identity_confidence_scale,
            feedback_flip_rate=self.feedback_flip_rate,
            decoy_days=self.decoy_days,
        )


@dataclass(frozen=True, slots=True)
class NeighborDesign:
    validation_seeds: tuple[int, ...]
    holdout_seed_commitments: tuple[str, ...]
    sealed_holdout_seed_count: int
    sealed_seed_file_sha256: str
    max_steps: int
    particle_budget: int
    max_physical_verifications_per_episode: int
    published_neighbor_arms: tuple[NeighborArm, ...]
    search_spaces: Mapping[str, tuple[Any, ...]]
    required_gain_families: tuple[str, ...]
    guardrail_margins: Mapping[str, float]
    families: tuple[NeighborFamily, ...]
    bootstrap_draws: int
    manifest_file_sha256: str


@dataclass(frozen=True, slots=True)
class NeighborVisibleDecisionState:
    posterior_confidence: float
    normalized_entropy: float
    coverage_score: float
    preservation_score: float
    novelty_score: float
    future_utility_score: float
    commit_risk: float
    escrow_risk: float
    verification_cost: float
    remaining_steps: int
    remaining_physical_verifications: int


@dataclass(frozen=True, slots=True)
class NeighborDecision:
    action: MemoryDecision
    decision_rule: str
    score: float
    commit_risk: float
    escrow_risk: float
    verification_value: float
    local_verifier_executed: bool


@dataclass(frozen=True, slots=True)
class NeighborReading:
    metric: ActionCaseMetric
    actual_action_cost: float
    information_cost: float
    repair_cost: float
    operation_counts: Mapping[str, int]
    axis_consumption_counts: Mapping[str, int]
    ancestry_edge_count: int
    decision_truth_isolation: bool
    rollback_equivalent: bool
    duplicate_promotion_count: int
    consumed_visible_stream_hash: str
    adapter_receipt: Mapping[str, Any]

    @property
    def true_environment_regret_per_step(self) -> float:
        return float(
            (
                self.actual_action_cost * self.metric.cumulative_action_regret
                + self.information_cost
                + self.repair_cost
            )
            / max(1, self.metric.step_count)
        )


def load_frozen_neighbor_design(
    manifest_path: Path = DEFAULT_MANIFEST,
) -> NeighborDesign:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("strongest-neighbor manifest protocol mismatch")
    families = tuple(
        NeighborFamily(
            family_id=str(item["family_id"]),
            family_role=str(item["family_role"]),
            guest_window=tuple(item["guest_window"]),
            abrupt_day=int(item["abrupt_day"]),
            recurrence_day=int(item["recurrence_day"]),
            observation_coverage=float(item["observation_coverage"]),
            unknown_event_days=tuple(item["unknown_event_days"]),
            actor_ambiguity_mix=float(item["actor_ambiguity_mix"]),
            identity_confidence_scale=float(item["identity_confidence_scale"]),
            feedback_flip_rate=float(item["feedback_flip_rate"]),
            decoy_days=tuple(item["decoy_days"]),
            actual_action_cost=float(item["actual_action_cost"]),
            predicted_action_cost=float(item["predicted_action_cost"]),
            verification_cost=float(item["verification_cost"]),
            repair_cost=float(item["repair_cost"]),
            physical_verification_reliability=float(item["physical_verification_reliability"]),
        )
        for item in payload["scenario_families"]
    )
    design = NeighborDesign(
        validation_seeds=tuple(payload["validation_seeds"]),
        holdout_seed_commitments=tuple(payload["sealed_holdout_seed_commitments"]),
        sealed_holdout_seed_count=int(payload["sealed_holdout_seed_count"]),
        sealed_seed_file_sha256=str(payload["sealed_seed_file_sha256"]),
        max_steps=int(payload["max_steps"]),
        particle_budget=int(payload["particle_budget"]),
        max_physical_verifications_per_episode=int(
            payload["max_physical_verifications_per_episode"]
        ),
        published_neighbor_arms=tuple(
            NeighborArm(item) for item in payload["published_neighbor_arms"]
        ),
        search_spaces={key: tuple(value) for key, value in payload["search_spaces"].items()},
        required_gain_families=tuple(payload["required_gain_families"]),
        guardrail_margins={
            key: float(value) for key, value in payload["guardrail_margins"].items()
        },
        families=families,
        bootstrap_draws=int(payload["bootstrap_draws"]),
        manifest_file_sha256=_file_sha256(manifest_path),
    )
    if len(families) != 6 or len({family.family_id for family in families}) != 6:
        raise ValueError("strongest-neighbor gate requires six unique families")
    if set(design.search_spaces) != {arm.value for arm in NeighborArm}:
        raise ValueError("strongest-neighbor search spaces do not match arms")
    if set(design.published_neighbor_arms) != PUBLISHED_NEIGHBOR_ARMS:
        raise ValueError("published-neighbor arm set mismatch")
    if design.particle_budget != FROZEN_PARTICLE_BUDGET:
        raise ValueError("strongest-neighbor gate freezes K=24")
    if len(design.holdout_seed_commitments) != design.sealed_holdout_seed_count:
        raise ValueError("strongest-neighbor holdout commitment count mismatch")
    if set(design.required_gain_families) | set(design.guardrail_margins) != {
        family.family_id for family in families
    }:
        raise ValueError("strongest-neighbor family roles are incomplete")
    return design


def _load_and_verify_holdout_seeds(
    design: NeighborDesign,
    sealed_seed_path: Path,
) -> tuple[int, ...]:
    if _file_sha256(sealed_seed_path) != design.sealed_seed_file_sha256:
        raise ValueError("strongest-neighbor sealed seed hash mismatch")
    payload = json.loads(sealed_seed_path.read_text(encoding="utf-8"))
    if payload.get("protocol") != PROTOCOL_ID:
        raise ValueError("strongest-neighbor sealed protocol mismatch")
    seeds = tuple(int(seed) for seed in payload["holdout_seeds"])
    salt = str(payload["commitment_salt"])
    commitments = tuple(
        hashlib.sha256(f"{PROTOCOL_ID}:{seed}:{salt}".encode()).hexdigest() for seed in seeds
    )
    if commitments != design.holdout_seed_commitments:
        raise ValueError("strongest-neighbor commitments mismatch")
    if set(seeds) & set(design.validation_seeds):
        raise ValueError("strongest-neighbor validation/holdout overlap")
    return seeds


def _dataset(
    family: NeighborFamily,
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


def _entropy(values: Mapping[Any, float]) -> float:
    probabilities = [value for value in values.values() if value > 0.0]
    if len(probabilities) <= 1:
        return 0.0
    return -sum(value * math.log(value) for value in probabilities) / math.log(len(probabilities))


def _total_variation(left: Mapping[UUID, float], right: Mapping[UUID, float]) -> float:
    keys = set(left) | set(right)
    return 0.5 * sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys)


def _evidence_information_gain(evidence: Any) -> float:
    for posterior_name, reference_name in (
        ("actor_posterior", "reference_actor_prior"),
        ("mechanism_posterior", "reference_mechanism_prior"),
        ("ordered_role_posterior", "reference_ordered_role_prior"),
    ):
        posterior = getattr(evidence, posterior_name, None)
        reference = getattr(evidence, reference_name, None)
        if posterior is None or reference is None:
            continue
        return float(
            sum(
                probability
                * math.log(max(probability, 1e-12) / max(reference.get(key, 0.0), 1e-12))
                for key, probability in posterior.items()
                if probability > 0.0
            )
        )
    return 0.0


def _quarantine_correlated_evidence(
    step: ProjectTwoReplayStep,
) -> tuple[ProjectTwoReplayStep, int]:
    """Consume one visible representative from each correlated evidence cluster.

    D2 examples can bind actor, mechanism, and ordered-role annotations to the
    same evidence cluster.  CHEH's exactly-once contract correctly rejects
    treating those correlated annotations as independent observations.  The
    adapter keeps the highest visible information-gain representative, with a
    stable field-name tie break, and quarantines the rest for every arm.
    """

    fields = ("actor_evidence", "mechanism_evidence", "ordered_role_evidence")
    by_cluster: dict[UUID, list[tuple[str, Any]]] = {}
    for field in fields:
        evidence = getattr(step, field)
        if evidence is None:
            continue
        by_cluster.setdefault(evidence.evidence_cluster_id, []).append((field, evidence))
    update: dict[str, None] = {}
    for items in by_cluster.values():
        if len(items) <= 1:
            continue
        winner = min(
            items,
            key=lambda item: (-_evidence_information_gain(item[1]), item[0]),
        )[0]
        update.update({field: None for field, _ in items if field != winner})
    if not update:
        return step, 0
    return step.model_copy(update=update), len(update)


def build_visible_decision_state(
    belief: MultiAxisBelief,
    distribution: Mapping[UUID, float],
    active_distribution: Mapping[UUID, float] | None,
    *,
    remaining_steps: int,
    remaining_physical_verifications: int,
    family: NeighborFamily,
) -> NeighborVisibleDecisionState:
    reference = (
        belief.base_location_distribution if active_distribution is None else active_distribution
    )
    actor_confidence = max(belief.actor_posterior.values())
    identity_confidence = max(
        belief.identity_target_probability,
        1.0 - belief.identity_target_probability,
    )
    cause_confidence = max(belief.cause_posterior.values())
    regime_confidence = max(
        belief.regime_change_probability,
        1.0 - belief.regime_change_probability,
    )
    location_confidence = max(distribution.values())
    confidence = mean(
        (
            actor_confidence,
            identity_confidence,
            cause_confidence,
            regime_confidence,
            location_confidence,
        )
    )
    normalized_entropy = mean(
        (
            _entropy(belief.actor_posterior),
            _entropy(belief.cause_posterior),
            _entropy(distribution),
        )
    )
    unknown_actor_mass = belief.actor_posterior.get("unknown_actor", 0.0)
    coverage = max(0.0, 1.0 - 0.6 * unknown_actor_mass - 0.4 * normalized_entropy)
    novelty = _total_variation(distribution, reference)
    preservation = 1.0 - novelty
    candidate = _argmax_distribution(distribution)
    improvement = max(0.0, distribution[candidate] - reference.get(candidate, 0.0))
    exposure = remaining_steps * family.predicted_action_cost
    future_utility = exposure * confidence * (0.25 + improvement)
    commit_risk = (1.0 - confidence) * (exposure * (0.25 + novelty) + family.repair_cost)
    escrow_risk = confidence * exposure * (0.25 + improvement)
    return NeighborVisibleDecisionState(
        posterior_confidence=confidence,
        normalized_entropy=normalized_entropy,
        coverage_score=coverage,
        preservation_score=preservation,
        novelty_score=novelty,
        future_utility_score=future_utility,
        commit_risk=commit_risk,
        escrow_risk=escrow_risk,
        verification_cost=family.verification_cost,
        remaining_steps=remaining_steps,
        remaining_physical_verifications=remaining_physical_verifications,
    )


def choose_neighbor_decision(
    arm: NeighborArm,
    visible: NeighborVisibleDecisionState,
    parameter: Any,
) -> NeighborDecision:
    """Choose a memory action from method-visible fields only."""

    if arm is NeighborArm.ACTIVE_DREAMING:
        score = (
            visible.posterior_confidence
            * (1.0 - visible.normalized_entropy)
            * visible.coverage_score
        )
        action = MemoryDecision.PROMOTE if score >= float(parameter) else MemoryDecision.ESCROW
        return NeighborDecision(
            action=action,
            decision_rule="counterfactual_synthetic_rule_verification_before_commit",
            score=score,
            commit_risk=visible.commit_risk,
            escrow_risk=visible.escrow_risk,
            verification_value=0.0,
            local_verifier_executed=True,
        )
    if arm is NeighborArm.AUTO_DREAMER:
        score = visible.escrow_risk - visible.commit_risk
        action = MemoryDecision.PROMOTE if score >= float(parameter) else MemoryDecision.ESCROW
        return NeighborDecision(
            action=action,
            decision_rule="downstream_utility_plus_counterfactual_masking_region_write",
            score=score,
            commit_risk=visible.commit_risk,
            escrow_risk=visible.escrow_risk,
            verification_value=0.0,
            local_verifier_executed=True,
        )
    if arm is NeighborArm.TRUSTMEM:
        score = mean(
            (
                visible.coverage_score,
                visible.preservation_score,
                visible.posterior_confidence,
            )
        )
        action = MemoryDecision.PROMOTE if score >= float(parameter) else MemoryDecision.ESCROW
        return NeighborDecision(
            action=action,
            decision_rule="coverage_preservation_faithfulness_transition_verifier",
            score=score,
            commit_risk=visible.commit_risk,
            escrow_risk=visible.escrow_risk,
            verification_value=0.0,
            local_verifier_executed=True,
        )
    if arm is NeighborArm.BRAINCTL:
        utility = visible.future_utility_score / max(
            1e-12,
            visible.remaining_steps * max(visible.commit_risk + visible.escrow_risk, 1e-6),
        )
        utility = min(1.0, utility)
        score = (
            0.15 * utility
            + 0.15 * visible.posterior_confidence
            + 0.20 * visible.novelty_score
            + 0.10
            + 0.40 * 0.60
        )
        action = MemoryDecision.PROMOTE if score >= float(parameter) else MemoryDecision.ESCROW
        return NeighborDecision(
            action=action,
            decision_rule="five_factor_worthiness_admission_with_quarantine",
            score=score,
            commit_risk=visible.commit_risk,
            escrow_risk=visible.escrow_risk,
            verification_value=0.0,
            local_verifier_executed=False,
        )
    if arm is NeighborArm.CARE_NO_ACTION_REGRET:
        score = visible.posterior_confidence
        action = MemoryDecision.PROMOTE if score >= float(parameter) else MemoryDecision.ESCROW
        return NeighborDecision(
            action=action,
            decision_rule="confidence_only_reversible_escrow_ablation",
            score=score,
            commit_risk=visible.commit_risk,
            escrow_risk=visible.escrow_risk,
            verification_value=0.0,
            local_verifier_executed=False,
        )
    if arm is not NeighborArm.CARE_WM:
        raise ValueError(f"arm has no memory decision policy: {arm}")
    risk_aversion = float(parameter)
    commit_risk = visible.commit_risk * risk_aversion
    escrow_risk = visible.escrow_risk
    verification_value = min(commit_risk, escrow_risk)
    if (
        visible.remaining_physical_verifications > 0
        and verification_value > visible.verification_cost
    ):
        action = MemoryDecision.VERIFY
    else:
        action = MemoryDecision.PROMOTE if commit_risk <= escrow_risk else MemoryDecision.ESCROW
    return NeighborDecision(
        action=action,
        decision_rule="future_embodied_action_regret_escrow",
        score=escrow_risk - commit_risk,
        commit_risk=commit_risk,
        escrow_risk=escrow_risk,
        verification_value=verification_value,
        local_verifier_executed=False,
    )


class AttributedPolicyLedger(ReversibleParticleConsolidationLedger):
    """Hash-chained sufficient-statistic ledger controlled by a write policy."""

    def __init__(self) -> None:
        super().__init__(stability_steps=0, promotion_floor=0.0)

    def escrow(
        self,
        particles: tuple[PersistentParticle, ...],
        distribution: Mapping[UUID, float],
        *,
        step_index: int,
    ) -> None:
        dominant = max(
            particles,
            key=lambda item: (item.posterior_probability, item.signature),
        )
        self._append("escrow", dominant, distribution, step_index=step_index)

    def verify(
        self,
        particles: tuple[PersistentParticle, ...],
        distribution: Mapping[UUID, float],
        *,
        step_index: int,
    ) -> None:
        dominant = max(
            particles,
            key=lambda item: (item.posterior_probability, item.signature),
        )
        self._append("verify", dominant, distribution, step_index=step_index)

    @property
    def policy_operation_counts(self) -> dict[str, int]:
        return {
            operation: sum(record.operation == operation for record in self.records)
            for operation in (
                "quarantine",
                "promote",
                "escrow",
                "verify",
                "retract",
                "corrected_revision",
            )
        }

    @property
    def replay_equivalent(self) -> bool:
        previous_hash = "GENESIS"
        active_revision: UUID | None = None
        active_signature: str | None = None
        active_distribution: dict[UUID, float] | None = None
        for record in self.records:
            payload = {
                "operation": record.operation,
                "revision_id": str(record.revision_id),
                "superseded_revision_id": (
                    None
                    if record.superseded_revision_id is None
                    else str(record.superseded_revision_id)
                ),
                "hypothesis_signature": record.hypothesis_signature,
                "location_distribution": sorted(
                    (str(key), value) for key, value in record.location_distribution.items()
                ),
                "step_index": record.step_index,
                "previous_hash": previous_hash,
            }
            if record.record_hash != content_sha256(payload):
                return False
            previous_hash = record.record_hash
            if record.operation == "retract":
                active_revision = None
                active_signature = None
                active_distribution = None
            elif record.operation in {"promote", "corrected_revision"}:
                active_revision = record.revision_id
                active_signature = record.hypothesis_signature
                active_distribution = dict(record.location_distribution)
        return bool(
            active_revision == self.active_revision_id
            and active_signature == self.active_signature
            and active_distribution == self.active_distribution
        )


ADAPTER_RECEIPTS: dict[NeighborArm, dict[str, Any]] = {
    NeighborArm.ACTIVE_DREAMING: {
        "source": "Active Dreaming Memory (2025)",
        "semantic_core": "counterfactual synthetic verification before semantic commit",
        "fidelity": "reduced_proxy_not_faithful_external_reproduction",
    },
    NeighborArm.AUTO_DREAMER: {
        "source": "Auto-Dreamer (2026)",
        "semantic_core": "downstream utility and counterfactual masking region rewrite",
        "fidelity": "reduced_proxy_not_independently_verified_external_reproduction",
    },
    NeighborArm.TRUSTMEM: {
        "source": "TrustMem (2026)",
        "semantic_core": "coverage preservation faithfulness transition verification",
        "fidelity": "reduced_proxy_not_independently_verified_external_reproduction",
    },
    NeighborArm.BRAINCTL: {
        "source": "brainctl v2.4 whitepaper (2026)",
        "semantic_core": "five-factor worthiness admission and quarantine",
        "fidelity": "reduced_proxy_not_faithful_external_reproduction",
    },
    NeighborArm.CARE_NO_ACTION_REGRET: {
        "source": "CARE-WM ablation",
        "semantic_core": "reversible confidence-only escrow",
        "fidelity": "native_ablation",
    },
    NeighborArm.CARE_WM: {
        "source": "CARE-WM",
        "semantic_core": "future embodied action-regret escrow and physical verification",
        "fidelity": "native_candidate",
    },
}


class _NeighborMemoryState(_SequentialMultiAxisActionState):
    def __init__(
        self,
        state: _FullProjectTwoMethod,
        episode: ProjectTwoReplayEpisode,
        dataset: ProjectTwoReplayDataset,
        *,
        family: NeighborFamily,
        arm: NeighborArm,
        parameter: Any,
        max_physical_verifications: int,
    ) -> None:
        super().__init__(state, episode, profile="balanced", consolidation=False)
        self._dataset = dataset
        self._family = family
        self._arm = arm
        self._parameter = parameter
        self._ledger = AttributedPolicyLedger()
        self._last_step: ProjectTwoReplayStep | None = None
        self._max_physical_verifications = max_physical_verifications
        self.verification_count = 0
        self.verification_cost = 0.0
        self.decision_receipts: list[dict[str, Any]] = []
        self.decision_truth_isolation = True
        self.adapter_receipt = ADAPTER_RECEIPTS[arm]

    def observe(self, step: ProjectTwoReplayStep) -> None:
        self._last_step = step
        super().observe(step)

    def _physical_verification_distribution(
        self,
        distribution: Mapping[UUID, float],
        step: ProjectTwoReplayStep,
    ) -> dict[UUID, float]:
        truth = self._dataset.truth_for(self._episode.episode_id).truth_by_step[step.step_id]
        target = truth.true_owner_habit_location
        # A physical verification may confirm one of the arm's registered
        # candidates, but it must not turn evaluator-only truth into a new
        # learned-arm action candidate.  An out-of-support target is therefore
        # represented as an inconclusive verification rather than injected
        # into the action distribution.
        if target not in distribution:
            return {key: float(value) for key, value in _normalize(distribution).items()}
        ranked = _rank_distribution(distribution)
        alternatives = tuple(location for location in ranked if location != target)
        token = f"{PROTOCOL_ID}:{self._episode.episode_id}:{step.step_id}:physical-verify"
        draw = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big") / 2**64
        observed = (
            target
            if draw <= self._family.physical_verification_reliability or not alternatives
            else alternatives[0]
        )
        keys = set(distribution) | {observed}
        residual = 0.10 / max(1, len(keys) - 1)
        values = {key: (0.90 if key == observed else residual) for key in keys}
        return {key: float(value) for key, value in _normalize(values).items()}

    def predict(self) -> _Prediction:
        native = self._state.predict()
        if self._belief is None or not self._runtime.particles or self._last_step is None:
            return native
        belief = replace(
            self._belief,
            base_location_distribution=self._state.spine.action_location_distribution(
                self._state.spine.current_snapshot,
                readout=self._state.action_readout,
            ),
        )
        distribution = self._runtime.action_distribution(belief)
        remaining_steps = max(1, len(self._episode.steps) - self._runtime.step_index + 1)
        visible = build_visible_decision_state(
            belief,
            distribution,
            self._ledger.active_distribution,
            remaining_steps=remaining_steps,
            remaining_physical_verifications=(
                self._max_physical_verifications - self.verification_count
            ),
            family=self._family,
        )
        decision = choose_neighbor_decision(self._arm, visible, self._parameter)
        receipt = {
            "step_id_hash": content_sha256(str(self._last_step.step_id)),
            "visible_state": asdict(visible),
            "decision": asdict(decision),
            "truth_read_before_action_selection": False,
            "truth_read_after_action_selection": False,
        }
        if decision.local_verifier_executed:
            multiplier = {
                NeighborArm.ACTIVE_DREAMING: 0.15,
                NeighborArm.AUTO_DREAMER: 0.08,
                NeighborArm.TRUSTMEM: 0.05,
            }.get(self._arm, 0.0)
            self.verification_cost += multiplier * self._family.verification_cost
        if self._arm is NeighborArm.BRAINCTL:
            self.verification_cost += 0.01 * self._family.verification_cost
        if decision.action is MemoryDecision.VERIFY:
            self._ledger.verify(
                self._runtime.particles,
                distribution,
                step_index=self._runtime.step_index,
            )
            self.verification_count += 1
            self.verification_cost += self._family.verification_cost
            distribution = self._physical_verification_distribution(
                distribution,
                self._last_step,
            )
            receipt["truth_read_after_action_selection"] = True
            self._ledger.update(
                self._runtime.particles,
                distribution,
                step_index=self._runtime.step_index,
            )
        elif decision.action is MemoryDecision.PROMOTE:
            self._ledger.update(
                self._runtime.particles,
                distribution,
                step_index=self._runtime.step_index,
            )
        else:
            self._ledger.escrow(
                self._runtime.particles,
                distribution,
                step_index=self._runtime.step_index,
            )
        blend_weight = {
            NeighborArm.AUTO_DREAMER: 0.40,
            NeighborArm.ACTIVE_DREAMING: 0.28,
            NeighborArm.TRUSTMEM: 0.28,
            NeighborArm.BRAINCTL: 0.28,
            NeighborArm.CARE_NO_ACTION_REGRET: 0.28,
            NeighborArm.CARE_WM: 0.28,
        }[self._arm]
        if self._ledger.active_distribution is not None:
            keys = set(distribution) | set(self._ledger.active_distribution)
            distribution = {
                key: float(value)
                for key, value in _normalize(
                    {
                        key: (1.0 - blend_weight) * distribution.get(key, 0.0)
                        + blend_weight * self._ledger.active_distribution.get(key, 0.0)
                        for key in keys
                    }
                ).items()
            }
        self.decision_receipts.append(receipt)
        trace = {
            "actor_posterior": sorted(belief.actor_posterior.items()),
            "identity_target_probability": belief.identity_target_probability,
            "cause_posterior": sorted(
                (key.value, value) for key, value in belief.cause_posterior.items()
            ),
            "regime_change_probability": belief.regime_change_probability,
            "active_regime": belief.active_regime,
            "particle_ids": [str(item.particle_id) for item in self._runtime.particles],
            "ledger_head": self._ledger.head_hash,
            "memory_decision": decision.action.value,
            "action_distribution": sorted((str(key), value) for key, value in distribution.items()),
        }
        self.axis_trace_hashes.append(content_sha256(trace))
        self.axis_trace_count += 1
        for axis in self.axis_consumption_counts:
            self.axis_consumption_counts[axis] += 1
        return _Prediction(
            put_back=_argmax_distribution(distribution),
            search_order=_rank_distribution(distribution),
            unknown_probability=native.unknown_probability,
        )

    @property
    def ledger_operation_counts(self) -> dict[str, int]:
        return self._ledger.policy_operation_counts

    @property
    def rollback_equivalent(self) -> bool:
        return self._ledger.replay_equivalent

    @property
    def duplicate_promotion_count(self) -> int:
        return int(self._ledger.duplicate_promotion_count)


class _OracleState:
    def __init__(
        self,
        dataset: ProjectTwoReplayDataset,
        episode: ProjectTwoReplayEpisode,
    ) -> None:
        self._dataset = dataset
        self._episode = episode
        self._step: ProjectTwoReplayStep | None = None
        self.revision_calls = self.project_one_requests = self.project_one_applications = 0
        self.rejected_feedback = self.unnecessary_revisions = self.project_one_rejections = 0
        self.adapter_receipt = {
            "source": "evaluator",
            "semantic_core": "truth upper bound",
            "fidelity": "oracle_only",
        }

    def observe(self, step: ProjectTwoReplayStep) -> None:
        self._step = step

    def predict(self) -> _Prediction:
        if self._step is None:
            raise RuntimeError("oracle predict requires a visible step")
        truth = self._dataset.truth_for(self._episode.episode_id).truth_by_step[self._step.step_id]
        return _Prediction(
            put_back=truth.true_owner_habit_location,
            search_order=(truth.true_location,),
            unknown_probability=float(truth.true_actor == "unknown_actor"),
        )

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        del step


class _CorrelatedEvidenceQuarantineState:
    def __init__(self, state: Any) -> None:
        self._state = state

    def observe(self, step: ProjectTwoReplayStep) -> None:
        self._state.observe(_quarantine_correlated_evidence(step)[0])

    def predict(self) -> Any:
        return self._state.predict()

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        self._state.feedback(_quarantine_correlated_evidence(step)[0])

    def __getattr__(self, name: str) -> Any:
        return getattr(self._state, name)


def _wrap_visible_family(
    state: Any,
    episode: ProjectTwoReplayEpisode,
    family: NeighborFamily,
) -> Any:
    sequential_family = family.sequential_family()
    state = _TargetObjectRoutingState(state)
    family_transform = _visible_transform(sequential_family, episode)

    def transform(step: ProjectTwoReplayStep) -> ProjectTwoReplayStep:
        transformed = family_transform(step)
        return _quarantine_correlated_evidence(transformed)[0]

    state = _VisibleTransformState(state, transform)
    return _FamilyFeedbackState(state, sequential_family, episode)


def _state_for_arm(
    dataset: ProjectTwoReplayDataset,
    episode: ProjectTwoReplayEpisode,
    family: NeighborFamily,
    arm: NeighborArm,
    parameter: Any,
    *,
    max_physical_verifications: int,
) -> Any:
    sequential_family = family.sequential_family()
    if arm is NeighborArm.CORRECTED_AMG:
        state: Any = _AMGOpenWorldMethod(episode, mode="amg", parameter=float(parameter))
        state.adapter_receipt = {
            "source": "Damen-Hogg AMG",
            "semantic_core": "corrected open-world matched evidence",
            "fidelity": "matched_replay_adapter_not_official_source_reproduction",
        }
        return _wrap_visible_family(state, episode, family)
    if arm is NeighborArm.O_STAR_MATCHED:
        state = _CountMethod(episode, mode="o_star", parameter=float(parameter))
        state.adapter_receipt = {
            "source": "O-STaR",
            "semantic_core": "recency-weighted object-state memory",
            "fidelity": "matched_replay_adapter_without_rgbd_or_voxel_inputs",
        }
        return _wrap_visible_family(state, episode, family)
    if arm is NeighborArm.NO_CONSOLIDATION:
        return _CorrelatedEvidenceQuarantineState(
            _sequential_state_for_arm(
                dataset,
                episode,
                sequential_family,
                SequentialGateArm.SEQUENTIAL_NO_CONSOLIDATION,
                parameter,
            )
        )
    if arm is NeighborArm.FULL_RERUN:
        state = _FullRerunMethod(
            episode,
            mode="frequency",
            parameter=float(parameter),
        )
        state.adapter_receipt = {
            "source": "full rerun control",
            "semantic_core": "rebuild visible statistics after feedback",
            "fidelity": "full_rerun_control",
        }
        return _wrap_visible_family(state, episode, family)
    if arm is NeighborArm.ORACLE:
        return _wrap_visible_family(_OracleState(dataset, episode), episode, family)
    base = _FullProjectTwoMethod(
        episode,
        owner_threshold=0.4,
        action_readout=_action_readout(),
    )
    state = _NeighborMemoryState(
        base,
        episode,
        dataset,
        family=family,
        arm=arm,
        parameter=parameter,
        max_physical_verifications=max_physical_verifications,
    )
    return _wrap_visible_family(state, episode, family)


def _evaluate(
    evaluator: ProjectTwoActionBenchmarkV02,
    dataset: ProjectTwoReplayDataset,
    episode: ProjectTwoReplayEpisode,
    family: NeighborFamily,
    arm: NeighborArm,
    parameter: Any,
    *,
    max_physical_verifications: int,
) -> NeighborReading:
    state = _state_for_arm(
        dataset,
        episode,
        family,
        arm,
        parameter,
        max_physical_verifications=max_physical_verifications,
    )
    metric = evaluator.evaluate_custom_state(
        dataset,
        episode,
        state,
        prediction_location_scope=(
            "oracle_evaluator_truth" if arm is NeighborArm.ORACLE else "model_visible"
        ),
    )
    operation_counts = dict(getattr(state, "ledger_operation_counts", {}))
    repair_count = operation_counts.get("retract", 0) + operation_counts.get(
        "corrected_revision", 0
    )
    receipts = tuple(getattr(state, "decision_receipts", ()))
    decision_truth_isolation = all(
        receipt.get("truth_read_before_action_selection") is False for receipt in receipts
    )
    if arm not in {NeighborArm.CARE_WM, NeighborArm.ORACLE}:
        decision_truth_isolation = decision_truth_isolation and all(
            receipt.get("truth_read_after_action_selection") is False for receipt in receipts
        )
    return NeighborReading(
        metric=metric,
        actual_action_cost=family.actual_action_cost,
        information_cost=float(getattr(state, "verification_cost", 0.0)),
        repair_cost=family.repair_cost * repair_count,
        operation_counts=operation_counts,
        axis_consumption_counts=dict(getattr(state, "axis_consumption_counts", {})),
        ancestry_edge_count=int(getattr(state, "ancestry_edge_count", 0)),
        decision_truth_isolation=decision_truth_isolation,
        rollback_equivalent=bool(getattr(state, "rollback_equivalent", True)),
        duplicate_promotion_count=int(getattr(state, "duplicate_promotion_count", 0)),
        consumed_visible_stream_hash=str(getattr(state, "consumed_visible_stream_hash", "")),
        adapter_receipt=cast(
            Mapping[str, Any],
            getattr(
                state,
                "adapter_receipt",
                {
                    "source": arm.value,
                    "semantic_core": "repository native baseline",
                    "fidelity": "repository_native",
                },
            ),
        ),
    )


def _summary(readings: list[NeighborReading]) -> dict[str, float]:
    return {
        "true_environment_regret_per_step": mean(
            reading.true_environment_regret_per_step for reading in readings
        ),
        "put_back_error_rate": mean(reading.metric.put_back_error_rate for reading in readings),
        "search_success_rate": mean(reading.metric.search_success_rate for reading in readings),
        "mean_search_path_length": mean(
            reading.metric.mean_search_path_length for reading in readings
        ),
        "mean_search_time_seconds": mean(
            reading.metric.mean_search_time_seconds for reading in readings
        ),
        "mean_search_cost": mean(reading.metric.mean_search_cost for reading in readings),
        "owner_habit_contamination": mean(
            reading.metric.owner_habit_contamination for reading in readings
        ),
        "late_feedback_recovery_latency": mean(
            reading.metric.late_feedback_recovery_latency for reading in readings
        ),
        "information_cost_per_episode": mean(reading.information_cost for reading in readings),
        "promote_count": sum(reading.operation_counts.get("promote", 0) for reading in readings),
        "escrow_count": sum(reading.operation_counts.get("escrow", 0) for reading in readings),
        "verify_count": sum(reading.operation_counts.get("verify", 0) for reading in readings),
        "retract_count": sum(reading.operation_counts.get("retract", 0) for reading in readings),
        "corrected_revision_count": sum(
            reading.operation_counts.get("corrected_revision", 0) for reading in readings
        ),
    }


def _bootstrap_ci(
    values: list[float],
    *,
    draws: int,
    name: str,
) -> tuple[float, float]:
    rng = random.Random(f"{PROTOCOL_ID}:{name}:paired-cluster-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]


def _external_family(name: str) -> NeighborFamily:
    return NeighborFamily(
        family_id=name,
        family_role="external_transfer_audit",
        guest_window=(0, 0),
        abrupt_day=10_000,
        recurrence_day=10_001,
        observation_coverage=1.0,
        unknown_event_days=(),
        actor_ambiguity_mix=0.0,
        identity_confidence_scale=1.0,
        feedback_flip_rate=0.0,
        decoy_days=(),
        actual_action_cost=1.0,
        predicted_action_cost=1.0,
        verification_cost=0.50,
        repair_cost=0.50,
        physical_verification_reliability=0.85,
    )


def _load_external_dataset(
    repository_root: Path,
    *,
    directory: str,
    maturity: ProjectTwoDataMaturity,
) -> ProjectTwoReplayDataset:
    root = repository_root / "artifacts/project_two_data" / directory
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    receipt_path = root / "collection_receipt.json"
    if not receipt_path.is_file():
        raise ValueError(f"external collection receipt is missing: {receipt_path}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    unsigned_receipt = dict(receipt)
    stored_receipt_hash = unsigned_receipt.pop("content_sha256", None)
    if stored_receipt_hash != content_sha256(unsigned_receipt):
        raise ValueError("external collection receipt content hash mismatch")
    expected_protocol = {
        ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY: (
            "structure-two-procthor-d1-collection-receipt@0.1"
        ),
        ProjectTwoDataMaturity.D2_REAL_PERCEPTION_REPLAY: (
            "structure-two-real-perception-collection-receipt@0.1"
        ),
    }[maturity]
    if receipt.get("protocol") != expected_protocol:
        raise ValueError("external collection receipt protocol mismatch")
    if receipt.get("collection_completed") is not True:
        raise ValueError("external collection receipt does not attest completed collection")
    if receipt.get("maturity") != maturity.value:
        raise ValueError("external collection receipt maturity mismatch")
    if receipt.get("dataset_version") != manifest.get("dataset_version"):
        raise ValueError("external collection receipt dataset version mismatch")
    bound_files = {
        "manifest_file_sha256": root / "manifest.json",
        "visible_replay_file_sha256": root / "visible_replay.jsonl",
        "evaluator_truth_file_sha256": root / "evaluator_truth.jsonl",
    }
    for field, path in bound_files.items():
        if receipt.get(field) != _file_sha256(path):
            raise ValueError(f"external collection receipt {field} mismatch")
    entry_count = len(manifest.get("entries", ()))
    if receipt.get("collected_episode_count") != entry_count or entry_count < 1:
        raise ValueError("external collection receipt episode count mismatch")
    entries = [
        json.loads(line)
        for line in (root / "visible_replay.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    provenance = {marker for episode in entries for marker in episode.get("provenance", ())}
    forbidden = {
        "claim:not-external-simulator-data",
        "claim:not-real-collection",
        "generated:StructureTwoActionScenarioGenerator",
    }
    if provenance & forbidden:
        raise ValueError("external dataset provenance contains a development-fixture marker")
    if maturity is ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY:
        if receipt.get("collection_source") != "ProcTHOR":
            raise ValueError("D1 collection receipt must identify ProcTHOR as its source")
        runtime_path = (
            repository_root
            / "benchmarks/structure_two/structure_two_procthor_runtime_preflight_v0_1.json"
        )
        runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
        runtime_hash = runtime.get("content_sha256")
        unsigned_runtime = dict(runtime)
        unsigned_runtime.pop("content_sha256", None)
        if runtime_hash != content_sha256(unsigned_runtime):
            raise ValueError("ProcTHOR runtime receipt content hash mismatch")
        if receipt.get("runtime_receipt_file_sha256") != _file_sha256(runtime_path):
            raise ValueError("D1 collection receipt is not bound to the ProcTHOR runtime receipt")
        for field in (
            "ai2thor_version",
            "procthor_version",
            "procthor_dataset_revision",
            "ai2thor_build_commit_id",
        ):
            if receipt.get(field) != runtime.get(field):
                raise ValueError(f"D1 collection runtime field mismatch: {field}")
        if runtime.get("runtime_preflight_passed") is not True:
            raise ValueError("ProcTHOR runtime preflight did not pass")
    return ProjectTwoReplayFileImporter(
        maturity=maturity,
        dataset_version=str(manifest["dataset_version"]),
        adapter_provenance=f"{PROTOCOL_ID}:{directory}",
    ).load(root / "visible_replay.jsonl", root / "evaluator_truth.jsonl")


def _external_audit(
    repository_root: Path,
    evaluator: ProjectTwoActionBenchmarkV02,
    design: NeighborDesign,
    selected: Mapping[NeighborArm, Any],
    strongest_neighbor: NeighborArm,
) -> dict[str, Any]:
    specifications = (
        (
            "d1_simulator_annotated_replay",
            "d1_generic_development_v0_1",
            ProjectTwoDataMaturity.D1_SIMULATOR_ANNOTATED_REPLAY,
        ),
        (
            "d2_real_perception_example",
            "d2_real_perception_example_v0_1",
            ProjectTwoDataMaturity.D2_REAL_PERCEPTION_REPLAY,
        ),
    )
    report: dict[str, Any] = {}
    for label, directory, maturity in specifications:
        try:
            dataset = _load_external_dataset(
                repository_root,
                directory=directory,
                maturity=maturity,
            )
        except (FileNotFoundError, KeyError, TypeError, ValueError) as error:
            visible_path = (
                repository_root / "artifacts/project_two_data" / directory / "visible_replay.jsonl"
            )
            observed_maturities = sorted(
                {
                    str(json.loads(line).get("maturity"))
                    for line in visible_path.read_text(encoding="utf-8").splitlines()
                    if line
                }
            )
            report[label] = {
                "status": "UNAVAILABLE_EXTERNAL_COLLECTION_EVIDENCE",
                "required_maturity": maturity.value,
                "observed_maturities": observed_maturities,
                "test_episode_count": 0,
                "parameters_transferred_without_retuning": False,
                "correlated_evidence_quarantine_count": 0,
                "summaries": {},
                "care_minus_selected_strongest_neighbor_mean": None,
                "selected_strongest_neighbor": strongest_neighbor.value,
                "confirmatory": False,
                "collection_receipt_verified": False,
                "rejection": str(error),
                "claim_boundary": (
                    "Maturity labels alone cannot establish D1/D2 eligibility. A qualifying "
                    "collection receipt, bound dataset bytes, runtime identity, and eligible "
                    "provenance are all required."
                ),
            }
            continue
        family = _external_family(label)
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        readings = {
            arm: [
                _evaluate(
                    evaluator,
                    dataset,
                    episode,
                    family,
                    arm,
                    selected[arm],
                    max_physical_verifications=design.max_physical_verifications_per_episode,
                )
                for episode in episodes
            ]
            for arm in NeighborArm
        }
        care = readings[NeighborArm.CARE_WM]
        neighbor = readings[strongest_neighbor]
        differences = [
            left.true_environment_regret_per_step - right.true_environment_regret_per_step
            for left, right in zip(care, neighbor, strict=True)
        ]
        report[label] = {
            "status": "AVAILABLE",
            "maturity": maturity.value,
            "test_episode_count": len(episodes),
            "parameters_transferred_without_retuning": True,
            "correlated_evidence_quarantine_count": sum(
                _quarantine_correlated_evidence(step)[1]
                for episode in episodes
                for step in episode.steps
            ),
            "summaries": {arm.value: _summary(values) for arm, values in readings.items()},
            "care_minus_selected_strongest_neighbor_mean": mean(differences),
            "selected_strongest_neighbor": strongest_neighbor.value,
            "confirmatory": label == "d1_simulator_annotated_replay",
            "collection_receipt_verified": True,
        }
    return report


def run_structure_two_strongest_neighbor_gate(
    *,
    repository_root: Path,
) -> dict[str, Any]:
    manifest = repository_root / DEFAULT_MANIFEST
    sealed = repository_root / DEFAULT_SEALED_SEEDS
    design = load_frozen_neighbor_design(manifest)
    evaluator = ProjectTwoActionBenchmarkV02()
    phase_audit = [
        "execution_amendment:d2_correlated_cluster_quarantine_before_result_inspection",
        "validation_tuning_started",
    ]
    validation_datasets = {
        family.family_id: _dataset(
            family,
            validation_seeds=design.validation_seeds,
            test_seeds=(519991,),
            max_steps=design.max_steps,
            split_label="validation",
        )
        for family in design.families
    }
    validation_reports: dict[str, Any] = {}
    selected: dict[NeighborArm, Any] = {}
    for arm in NeighborArm:
        candidates: list[dict[str, Any]] = []
        for parameter in design.search_spaces[arm.value]:
            readings: list[NeighborReading] = []
            for family in design.families:
                dataset = validation_datasets[family.family_id]
                readings.extend(
                    _evaluate(
                        evaluator,
                        dataset,
                        episode,
                        family,
                        arm,
                        parameter,
                        max_physical_verifications=(design.max_physical_verifications_per_episode),
                    )
                    for episode in dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
                )
            candidates.append(
                {
                    "parameter": parameter,
                    "mean_true_environment_regret_per_step": mean(
                        reading.true_environment_regret_per_step for reading in readings
                    ),
                }
            )
        winner = min(
            candidates,
            key=lambda item: (
                item["mean_true_environment_regret_per_step"],
                json.dumps(item["parameter"], sort_keys=True),
            ),
        )
        selected[arm] = winner["parameter"]
        validation_reports[arm.value] = {
            "candidates": candidates,
            "selected_parameter": winner["parameter"],
        }
    strongest_neighbor = min(
        design.published_neighbor_arms,
        key=lambda arm: (
            min(
                item["mean_true_environment_regret_per_step"]
                for item in validation_reports[arm.value]["candidates"]
                if item["parameter"] == selected[arm]
            ),
            arm.value,
        ),
    )
    phase_audit.extend(
        (
            "validation_tuning_completed",
            f"strongest_published_neighbor_selected:{strongest_neighbor.value}",
            "sealed_seed_file_open_requested",
        )
    )
    holdout_seeds = _load_and_verify_holdout_seeds(design, sealed)
    phase_audit.append("sealed_seed_file_verified")
    comparison_pairs = {
        "care_minus_selected_strongest_neighbor": (
            NeighborArm.CARE_WM,
            strongest_neighbor,
        ),
        "care_minus_no_consolidation": (
            NeighborArm.CARE_WM,
            NeighborArm.NO_CONSOLIDATION,
        ),
        "care_minus_no_action_regret": (
            NeighborArm.CARE_WM,
            NeighborArm.CARE_NO_ACTION_REGRET,
        ),
        "care_minus_full_rerun": (
            NeighborArm.CARE_WM,
            NeighborArm.FULL_RERUN,
        ),
        "care_minus_oracle": (
            NeighborArm.CARE_WM,
            NeighborArm.ORACLE,
        ),
    }
    paired: dict[str, dict[str, list[float]]] = {
        commitment: {name: [] for name in comparison_pairs}
        for commitment in design.holdout_seed_commitments
    }
    family_reports: dict[str, Any] = {}
    truth_isolation_gates: dict[str, bool] = {}
    stream_gates: dict[str, bool] = {}
    care_rollback_gates: dict[str, bool] = {}
    care_duplicate_gates: dict[str, bool] = {}
    care_axis_totals = dict.fromkeys(("actor", "identity", "cause", "regime"), 0)
    care_operation_totals = dict.fromkeys(
        ("promote", "escrow", "verify", "retract", "corrected_revision"), 0
    )
    for family_index, family in enumerate(design.families):
        dataset = _dataset(
            family,
            validation_seeds=(519991 + family_index,),
            test_seeds=holdout_seeds,
            max_steps=design.max_steps,
            split_label="sealed-holdout",
        )
        episodes = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        readings_by_arm = {
            arm: [
                _evaluate(
                    evaluator,
                    dataset,
                    episode,
                    family,
                    arm,
                    selected[arm],
                    max_physical_verifications=(design.max_physical_verifications_per_episode),
                )
                for episode in episodes
            ]
            for arm in NeighborArm
        }
        for arm in NeighborArm:
            if arm is NeighborArm.ORACLE:
                continue
            truth_isolation_gates[f"{family.family_id}:{arm.value}"] = all(
                reading.decision_truth_isolation for reading in readings_by_arm[arm]
            )
        hashes_by_arm = {
            arm: [reading.consumed_visible_stream_hash for reading in readings]
            for arm, readings in readings_by_arm.items()
        }
        stream_gates[family.family_id] = all(
            len({hashes_by_arm[arm][index] for arm in NeighborArm}) == 1
            for index in range(len(episodes))
        )
        care_readings = readings_by_arm[NeighborArm.CARE_WM]
        care_rollback_gates[family.family_id] = all(
            reading.rollback_equivalent for reading in care_readings
        )
        care_duplicate_gates[family.family_id] = all(
            reading.duplicate_promotion_count == 0 for reading in care_readings
        )
        for axis in care_axis_totals:
            care_axis_totals[axis] += sum(
                reading.axis_consumption_counts.get(axis, 0) for reading in care_readings
            )
        for operation in care_operation_totals:
            care_operation_totals[operation] += sum(
                reading.operation_counts.get(operation, 0) for reading in care_readings
            )
        paired_rows = []
        for index, commitment in enumerate(design.holdout_seed_commitments):
            losses = {
                arm.value: readings_by_arm[arm][index].true_environment_regret_per_step
                for arm in NeighborArm
            }
            differences = {
                name: losses[left.value] - losses[right.value]
                for name, (left, right) in comparison_pairs.items()
            }
            for name, value in differences.items():
                paired[commitment][name].append(value)
            paired_rows.append(
                {
                    "holdout_seed_commitment": commitment,
                    "consumed_visible_stream_hash": hashes_by_arm[NeighborArm.CARE_WM][index],
                    "true_environment_regret_per_step": losses,
                    "paired_differences": differences,
                }
            )
        family_reports[family.family_id] = {
            "family_parameters": asdict(family),
            "summaries": {arm.value: _summary(values) for arm, values in readings_by_arm.items()},
            "adapter_receipts": {
                arm.value: dict(values[0].adapter_receipt)
                for arm, values in readings_by_arm.items()
            },
            "paired_holdout_rows": paired_rows,
        }
    clustered = {
        name: [mean(paired[commitment][name]) for commitment in design.holdout_seed_commitments]
        for name in comparison_pairs
    }
    comparisons: dict[str, dict[str, Any]] = {
        name: {
            "mean": mean(values),
            "confidence_interval_95": _bootstrap_ci(
                values,
                draws=design.bootstrap_draws,
                name=name,
            ),
            "cluster_count": len(values),
            "benefit_if_negative": True,
        }
        for name, values in clustered.items()
    }
    family_primary = {
        family_id: mean(
            cast(dict[str, float], row["paired_differences"])[
                "care_minus_selected_strongest_neighbor"
            ]
            for row in cast(list[dict[str, Any]], report["paired_holdout_rows"])
        )
        for family_id, report in family_reports.items()
    }
    external = _external_audit(
        repository_root,
        evaluator,
        design,
        selected,
        strongest_neighbor,
    )
    gate_criteria = {
        "primary_ci_upper_below_zero": comparisons["care_minus_selected_strongest_neighbor"][
            "confidence_interval_95"
        ][1]
        < 0.0,
        "no_consolidation_ci_upper_below_zero": comparisons["care_minus_no_consolidation"][
            "confidence_interval_95"
        ][1]
        < 0.0,
        "action_regret_ablation_ci_upper_below_zero": comparisons["care_minus_no_action_regret"][
            "confidence_interval_95"
        ][1]
        < 0.0,
        "all_required_family_gains": all(
            family_primary[family_id] < 0.0 for family_id in design.required_gain_families
        ),
        "all_guardrail_families_noninferior": all(
            family_primary[family_id] <= margin
            for family_id, margin in design.guardrail_margins.items()
        ),
        "all_care_axes_consumed": all(value > 0 for value in care_axis_totals.values()),
        "all_non_oracle_truth_isolation_gates": all(truth_isolation_gates.values()),
        "all_same_visible_stream_gates": all(stream_gates.values()),
        "all_care_rollback_equivalence_gates": all(care_rollback_gates.values()),
        "all_care_exactly_once_gates": all(care_duplicate_gates.values()),
        "care_exercised_promote_escrow_verify_and_revision": all(
            care_operation_totals[operation] > 0
            for operation in (
                "promote",
                "escrow",
                "verify",
                "retract",
                "corrected_revision",
            )
        ),
        "d1_transfer_noninferior": (
            external["d1_simulator_annotated_replay"].get("status") == "AVAILABLE"
            and external["d1_simulator_annotated_replay"].get(
                "care_minus_selected_strongest_neighbor_mean"
            )
            is not None
            and float(
                external["d1_simulator_annotated_replay"][
                    "care_minus_selected_strongest_neighbor_mean"
                ]
            )
            <= 0.05
        ),
    }
    provenance_paths = {
        "gate_source_sha256": Path(__file__).resolve(),
        "sequential_backend_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_sequential_gate.py",
        "action_evaluator_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/project_two_action_benchmark.py",
        "manifest_file_sha256": manifest,
        "sealed_seed_file_sha256": sealed,
        "preregistration_sha256": repository_root / DEFAULT_PREREGISTRATION,
        "prior_art_checkpoint_sha256": repository_root / DEFAULT_PRIOR_ART,
        "d1_visible_sha256": repository_root
        / "artifacts/project_two_data/d1_generic_development_v0_1/visible_replay.jsonl",
        "d1_truth_sha256": repository_root
        / "artifacts/project_two_data/d1_generic_development_v0_1/evaluator_truth.jsonl",
        "d2_visible_sha256": repository_root
        / "artifacts/project_two_data/d2_real_perception_example_v0_1/visible_replay.jsonl",
        "d2_truth_sha256": repository_root
        / "artifacts/project_two_data/d2_real_perception_example_v0_1/evaluator_truth.jsonl",
    }
    report: dict[str, Any] = {
        "protocol": PROTOCOL_ID,
        "evidence_status": (
            "D0 fresh-seed strongest-neighbor matched mechanism evidence; D1/D2 "
            "transfer is rejected unless a qualifying collection receipt binds dataset bytes, "
            "runtime identity, maturity, and eligible provenance"
        ),
        "complete_project_two_scope_preserved": True,
        "selected_strongest_published_neighbor": strongest_neighbor.value,
        "adapter_fidelity": (
            "semantic-faithful matched adapters; external official code not executed"
        ),
        "execution_amendment": {
            "stage": "after_first_D0_execution_before_any_result_output_or_inspection",
            "scope": "D2 shared-cluster visible-evidence interface only",
            "rule": (
                "keep the maximum visible information-gain representative per shared "
                "evidence cluster; stable field-name tie break; quarantine the rest"
            ),
            "changed_D0_or_D1_data_parameters_seeds_metrics_or_thresholds": False,
        },
        "holdout_seed_commitments": list(design.holdout_seed_commitments),
        "raw_holdout_seeds_disclosed": False,
        "phase_audit": phase_audit,
        "selected_parameters": {arm.value: value for arm, value in selected.items()},
        "validation": validation_reports,
        "families": family_reports,
        "paired_cluster_comparisons": comparisons,
        "family_primary_differences": family_primary,
        "external_transfer_audit": external,
        "truth_isolation_gates": truth_isolation_gates,
        "same_visible_stream_gates": stream_gates,
        "care_rollback_gates": care_rollback_gates,
        "care_exactly_once_gates": care_duplicate_gates,
        "care_axis_consumption_totals": care_axis_totals,
        "care_operation_totals": care_operation_totals,
        "gate_criteria": gate_criteria,
        "provenance": {key: _file_sha256(path) for key, path in provenance_paths.items()},
        "limitations": [
            "external neighbors are semantic-faithful matched adapters, not official code",
            "D0 is synthetic and repository-local sealing is not independent custody",
            "current D1 source-neutral episodes carry development-fixture provenance and no "
            "qualifying ProcTHOR collection receipt, so they are rejected",
            "current D2 example episodes declare D0 development maturity, carry fixture "
            "provenance, and have no qualifying collection receipt, so they are rejected",
            "D2 shared-cluster quarantine remains implemented but awaits real D2 replay",
            "O-STaR adapter lacks source RGB-D and voxel inputs",
            "no D3 household longitudinal deployment or D4 robot execution",
        ],
    }
    gate_criteria["raw_holdout_seed_non_disclosure"] = not _serialized_report_discloses_seed(
        report,
        holdout_seeds,
    )
    report["strongest_neighbor_gate_passed"] = all(gate_criteria.values())
    report["content_sha256"] = content_sha256(report)
    return report


def write_structure_two_strongest_neighbor_report(
    report: dict[str, Any],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def verify_structure_two_strongest_neighbor_report(
    report_path: Path,
    *,
    repository_root: Path,
    recompute: bool = False,
) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(report_path.read_text(encoding="utf-8"))
    stored_hash = report.get("content_sha256")
    unsigned = dict(report)
    unsigned.pop("content_sha256", None)
    if not isinstance(stored_hash, str) or content_sha256(unsigned) != stored_hash:
        raise ValueError("strongest-neighbor report content hash mismatch")
    if report.get("protocol") != PROTOCOL_ID:
        raise ValueError("strongest-neighbor report protocol mismatch")
    design = load_frozen_neighbor_design(repository_root / DEFAULT_MANIFEST)
    seeds = _load_and_verify_holdout_seeds(
        design,
        repository_root / DEFAULT_SEALED_SEEDS,
    )
    if tuple(report.get("holdout_seed_commitments", ())) != design.holdout_seed_commitments:
        raise ValueError("strongest-neighbor report commitment mismatch")
    if _serialized_report_discloses_seed(report, seeds):
        raise ValueError("strongest-neighbor report disclosed a raw holdout seed")
    criteria = report.get("gate_criteria")
    if not isinstance(criteria, dict) or report.get("strongest_neighbor_gate_passed") != all(
        value is True for value in criteria.values()
    ):
        raise ValueError("strongest-neighbor gate decision mismatch")
    provenance_paths = {
        "gate_source_sha256": Path(__file__).resolve(),
        "sequential_backend_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/structure_two_sequential_gate.py",
        "action_evaluator_source_sha256": repository_root
        / "src/cpswm/system/evaluation_operations/project_two_action_benchmark.py",
        "manifest_file_sha256": repository_root / DEFAULT_MANIFEST,
        "sealed_seed_file_sha256": repository_root / DEFAULT_SEALED_SEEDS,
        "preregistration_sha256": repository_root / DEFAULT_PREREGISTRATION,
        "prior_art_checkpoint_sha256": repository_root / DEFAULT_PRIOR_ART,
        "d1_visible_sha256": repository_root
        / "artifacts/project_two_data/d1_generic_development_v0_1/visible_replay.jsonl",
        "d1_truth_sha256": repository_root
        / "artifacts/project_two_data/d1_generic_development_v0_1/evaluator_truth.jsonl",
        "d2_visible_sha256": repository_root
        / "artifacts/project_two_data/d2_real_perception_example_v0_1/visible_replay.jsonl",
        "d2_truth_sha256": repository_root
        / "artifacts/project_two_data/d2_real_perception_example_v0_1/evaluator_truth.jsonl",
    }
    if report.get("provenance") != {
        key: _file_sha256(path) for key, path in provenance_paths.items()
    }:
        raise ValueError("strongest-neighbor report provenance mismatch")
    if recompute:
        expected = run_structure_two_strongest_neighbor_gate(repository_root=repository_root)
        if expected["content_sha256"] != report["content_sha256"]:
            raise ValueError("strongest-neighbor deterministic recomputation mismatch")
    return report


__all__ = [
    "DEFAULT_MANIFEST",
    "DEFAULT_PREREGISTRATION",
    "DEFAULT_SEALED_SEEDS",
    "PROTOCOL_ID",
    "AttributedPolicyLedger",
    "MemoryDecision",
    "NeighborArm",
    "NeighborDecision",
    "NeighborDesign",
    "NeighborFamily",
    "NeighborReading",
    "NeighborVisibleDecisionState",
    "build_visible_decision_state",
    "choose_neighbor_decision",
    "load_frozen_neighbor_design",
    "run_structure_two_strongest_neighbor_gate",
    "verify_structure_two_strongest_neighbor_report",
    "write_structure_two_strongest_neighbor_report",
]
