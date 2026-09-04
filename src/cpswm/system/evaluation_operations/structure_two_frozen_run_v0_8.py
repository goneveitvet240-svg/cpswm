"""Deterministically opened holdout and executable Gate-B evidence for Structure Two.

This module is the content root shared by Gate A and canonical Gate B.  Signed
summaries are not treated as execution evidence: the verifier opens the frozen
seed/holdout commitments, regenerates every world and rollout, recomputes Gate-A
metrics, and reruns the ten arm adapters before accepting their action rows.
"""

from __future__ import annotations

import importlib
import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationError,
    Ed25519AttestationSigner,
    Ed25519AttestationVerifier,
    attested_payload,
)
from cpswm.system.evaluation_operations.structure_two_gate_b_protocol_v0_6 import (
    EXPECTED_ARMS,
)
from cpswm.system.reproducibility import content_sha256

HOLDOUT_OPENING_PROTOCOL_ID = "structure-two-public-validation-opening@0.8"
VALIDATION_SEED_OPENING_PROTOCOL_ID = "structure-two-validation-seed-opening@0.8"
HOLDOUT_COMMITMENT_PROTOCOL_ID = "structure-two-holdout-commitment@0.8"
GATE_B_PROXY_DIAGNOSTIC_PROTOCOL_ID = "structure-two-gate-b-proxy-diagnostic@0.8"
# Backward-compatible symbol name; its value is deliberately diagnostic-only.
GATE_B_EXECUTION_PROTOCOL_ID = GATE_B_PROXY_DIAGNOSTIC_PROTOCOL_ID
GATE_B_EXECUTION_ATTESTATION_DOMAIN = "cpswm.evaluation.structure_two.gate_b_execution.v0.8"
_GATE_B_EXECUTION_ATTESTATION_EXCLUDE = frozenset({"executor_attestation"})
CANONICAL_WORLD_DISTRIBUTION_SHA256 = (
    "3918e06508855014d8884d08410494760ae6d6aabadc45070e23cc790a0674c1"
)
CANONICAL_VALIDATION_WORLD_SEEDS = tuple(range(450001, 450013))
CANONICAL_TRAJECTORY_SEEDS = (17, 31, 43)
CANONICAL_OBSERVATION_SEEDS = (107, 227)
CANONICAL_EXCLUDED_WORLD_SEEDS = (
    *range(410001, 410025),
    *range(420001, 420013),
    *range(440001, 440013),
)
CANONICAL_ESTIMATOR: Mapping[str, float | int] = {
    "window_days": 35,
    "context_shrinkage_pseudocounts": 0.0,
    "owner_probability_threshold": 0.5,
}
CANONICAL_BOOTSTRAP_DRAWS = 4000

_WORLD_DISTRIBUTION_RANGE_FIELDS = frozenset(
    {
        "abrupt_fraction",
        "recurrence_fraction",
        "owner_event_probability",
        "unknown_event_probability",
        "habit_mode_mass",
        "habit_secondary_mass",
        "base_observation_probability",
        "location_visibility_multiplier",
        "actor_map_accuracy",
        "identity_match_accuracy",
        "handoff_probability",
    }
)
_WORLD_DISTRIBUTION_INTEGER_RANGE_FIELDS = frozenset(
    {
        "duration_days_inclusive",
        "location_count_inclusive",
        "guest_actor_count_inclusive",
    }
)
_WORLD_DISTRIBUTION_SCALAR_FIELDS = frozenset(
    {
        "weekend_distinct_mode_probability",
        "guest_visibility_multiplier",
        "unknown_visibility_multiplier",
        "weekend_visibility_multiplier",
    }
)


def _validate_world_distribution_semantics(payload: Mapping[str, Any]) -> None:
    expected_fields = (
        _WORLD_DISTRIBUTION_RANGE_FIELDS
        | _WORLD_DISTRIBUTION_INTEGER_RANGE_FIELDS
        | _WORLD_DISTRIBUTION_SCALAR_FIELDS
    )
    if set(payload) != expected_fields:
        raise ValueError("holdout world distribution field set is not canonical")
    for name in _WORLD_DISTRIBUTION_RANGE_FIELDS:
        values = payload[name]
        if (
            not isinstance(values, list)
            or len(values) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, (int, float)) for value in values
            )
            or any(not isfinite(float(value)) for value in values)
            or float(values[0]) > float(values[1])
        ):
            raise ValueError(f"holdout distribution range {name!r} is malformed")
    for name in _WORLD_DISTRIBUTION_INTEGER_RANGE_FIELDS:
        values = payload[name]
        minimum = 0 if name == "guest_actor_count_inclusive" else 1
        if (
            not isinstance(values, list)
            or len(values) != 2
            or any(isinstance(value, bool) or not isinstance(value, int) for value in values)
            or values[0] < minimum
            or values[0] > values[1]
        ):
            raise ValueError(f"holdout integer range {name!r} is malformed")
    for name in _WORLD_DISTRIBUTION_SCALAR_FIELDS:
        value = payload[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
        ):
            raise ValueError(f"holdout distribution scalar {name!r} is malformed")
    probability_ranges = _WORLD_DISTRIBUTION_RANGE_FIELDS - {"location_visibility_multiplier"}
    if any(
        float(value) < 0.0 or float(value) > 1.0
        for name in probability_ranges
        for value in payload[name]
    ):
        raise ValueError("holdout distribution probability range escapes [0, 1]")
    if any(
        not 0.0 <= float(payload[name]) <= 1.0
        for name in (
            "weekend_distinct_mode_probability",
            "guest_visibility_multiplier",
            "unknown_visibility_multiplier",
            "weekend_visibility_multiplier",
        )
    ):
        raise ValueError("holdout distribution probability scalar escapes [0, 1]")
    if any(float(value) <= 0.0 for value in payload["location_visibility_multiplier"]):
        raise ValueError("holdout location visibility multipliers must be positive")
    if float(payload["abrupt_fraction"][1]) >= float(payload["recurrence_fraction"][0]):
        raise ValueError("holdout abrupt and recurrence intervals overlap")
    if float(payload["habit_mode_mass"][1]) + float(payload["habit_secondary_mass"][1]) > 1.0:
        raise ValueError("holdout habit masses can exceed one")


def validate_canonical_holdout_opening_v0_8(
    opening: FrozenHoldoutOpeningV08,
    gate_a_spec: Mapping[str, Any],
) -> None:
    """Require public validation data to equal the preregistered Gate-A plan."""

    raw = gate_a_spec.get("public_preregistered_validation")
    if not isinstance(raw, dict):
        raise ValueError("Gate A specification lacks public preregistered validation data")
    try:
        expected_world_seeds = tuple(int(item) for item in raw["validation_world_seeds"])
        expected_trajectory_seeds = tuple(int(item) for item in raw["trajectory_seeds"])
        expected_observation_seeds = tuple(int(item) for item in raw["observation_seeds"])
        excluded_world_seeds = tuple(int(item) for item in raw["excluded_world_seeds"])
        expected_estimator = dict(raw["estimator"])
        expected_bootstrap_draws = int(raw["bootstrap_draws"])
        expected_distribution_sha256 = str(raw["world_distribution_sha256"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Gate A public validation specification is malformed") from exc
    frozen_spec_projection = {
        "evaluation_set_role": raw.get("evaluation_set_role"),
        "confirmatory_gate_b_eligible": raw.get("confirmatory_gate_b_eligible"),
        "source_manifest": raw.get("source_manifest"),
        "world_distribution_sha256": expected_distribution_sha256,
        "validation_world_seeds": expected_world_seeds,
        "trajectory_seeds": expected_trajectory_seeds,
        "observation_seeds": expected_observation_seeds,
        "excluded_world_seeds": excluded_world_seeds,
        "estimator": expected_estimator,
        "bootstrap_draws": expected_bootstrap_draws,
    }
    code_canonical_projection = {
        "evaluation_set_role": "public_preregistered_validation",
        "confirmatory_gate_b_eligible": False,
        "source_manifest": (
            "configs/project_two_experiments/structure_two_world_generator_manifest_v0_5.json"
        ),
        "world_distribution_sha256": CANONICAL_WORLD_DISTRIBUTION_SHA256,
        "validation_world_seeds": CANONICAL_VALIDATION_WORLD_SEEDS,
        "trajectory_seeds": CANONICAL_TRAJECTORY_SEEDS,
        "observation_seeds": CANONICAL_OBSERVATION_SEEDS,
        "excluded_world_seeds": CANONICAL_EXCLUDED_WORLD_SEEDS,
        "estimator": dict(CANONICAL_ESTIMATOR),
        "bootstrap_draws": CANONICAL_BOOTSTRAP_DRAWS,
    }
    if frozen_spec_projection != code_canonical_projection:
        raise ValueError("Gate A specification changed the code-pinned public validation set")
    if (
        not expected_world_seeds
        or not expected_trajectory_seeds
        or not expected_observation_seeds
        or len(set(excluded_world_seeds)) != len(excluded_world_seeds)
    ):
        raise ValueError("Gate A public validation seed partition is malformed")
    if set(expected_world_seeds) & set(excluded_world_seeds):
        raise ValueError("Gate A canonical validation seeds overlap spent seeds")
    actual = {
        "world_distribution_sha256": content_sha256(opening.world_distribution),
        "validation_world_seeds": opening.validation_world_seeds,
        "trajectory_seeds": opening.trajectory_seeds,
        "observation_seeds": opening.observation_seeds,
        "estimator": opening.estimator,
        "bootstrap_draws": opening.bootstrap_draws,
    }
    expected = {
        "world_distribution_sha256": expected_distribution_sha256,
        "validation_world_seeds": expected_world_seeds,
        "trajectory_seeds": expected_trajectory_seeds,
        "observation_seeds": expected_observation_seeds,
        "estimator": expected_estimator,
        "bootstrap_draws": expected_bootstrap_draws,
    }
    if actual != expected:
        raise ValueError("opened validation data differs from the preregistered generation plan")


class FrozenHoldoutOpeningV08(ContractModel):
    protocol: str = Field(pattern=r"^structure-two-public-validation-opening@0\.8$")
    evaluation_set_role: Literal["public_preregistered_validation"]
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    seed_opening_nonce: str = Field(min_length=16)
    holdout_opening_nonce: str = Field(min_length=16)
    world_distribution: dict[str, Any]
    validation_world_seeds: tuple[int, ...] = Field(min_length=1)
    trajectory_seeds: tuple[int, ...] = Field(min_length=1)
    observation_seeds: tuple[int, ...] = Field(min_length=1)
    estimator: dict[str, float | int]
    bootstrap_draws: int = Field(ge=100)

    @model_validator(mode="after")
    def validate_opening(self) -> FrozenHoldoutOpeningV08:
        _validate_world_distribution_semantics(self.world_distribution)
        for name, values in (
            ("validation_world_seeds", self.validation_world_seeds),
            ("trajectory_seeds", self.trajectory_seeds),
            ("observation_seeds", self.observation_seeds),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"holdout opening contains duplicate {name}")
            if any(isinstance(value, bool) or value < 0 for value in values):
                raise ValueError(f"holdout opening contains an invalid {name}")
        if set(self.estimator) != {
            "window_days",
            "context_shrinkage_pseudocounts",
            "owner_probability_threshold",
        }:
            raise ValueError("holdout estimator field set is not canonical")
        window_days = self.estimator["window_days"]
        pseudocounts = self.estimator["context_shrinkage_pseudocounts"]
        owner_threshold = self.estimator["owner_probability_threshold"]
        if (
            isinstance(window_days, bool)
            or not isinstance(window_days, int)
            or window_days <= 0
            or isinstance(pseudocounts, bool)
            or not isinstance(pseudocounts, (int, float))
            or not isfinite(float(pseudocounts))
            or float(pseudocounts) < 0.0
            or isinstance(owner_threshold, bool)
            or not isinstance(owner_threshold, (int, float))
            or not isfinite(float(owner_threshold))
            or not 0.0 < float(owner_threshold) < 1.0
        ):
            raise ValueError("holdout estimator parameters are invalid")
        generator_module = importlib.import_module(
            "cpswm.system.evaluation_operations.structure_two_world_generator_v0_2"
        )
        gate_module = importlib.import_module(
            "cpswm.system.evaluation_operations.structure_two_world_gate_v0_3"
        )
        generator_module.WorldDistributionConfig.from_manifest(self.world_distribution)
        gate_module.ShrunkEstimatorConfig(
            window_days=int(self.estimator["window_days"]),
            context_shrinkage_pseudocounts=float(self.estimator["context_shrinkage_pseudocounts"]),
            owner_probability_threshold=float(self.estimator["owner_probability_threshold"]),
        )
        return self

    @property
    def validation_seed_commitment_sha256(self) -> str:
        return validation_seed_commitment_sha256_v0_8(
            world_seeds=self.validation_world_seeds,
            trajectory_seeds=self.trajectory_seeds,
            observation_seeds=self.observation_seeds,
            nonce=self.seed_opening_nonce,
        )

    @property
    def holdout_commitment_sha256(self) -> str:
        return holdout_commitment_sha256_v0_8(
            validation_seed_commitment_sha256=(self.validation_seed_commitment_sha256),
            world_distribution=self.world_distribution,
            estimator=self.estimator,
            bootstrap_draws=self.bootstrap_draws,
            nonce=self.holdout_opening_nonce,
        )


@dataclass(frozen=True, slots=True)
class RecomputedFrozenHoldoutV08:
    opening: FrozenHoldoutOpeningV08
    worlds: tuple[Any, ...]
    world_rollouts: tuple[tuple[Any, Any], ...]
    world_rows: tuple[dict[str, Any], ...]
    rollout_rows: tuple[dict[str, Any], ...]
    metrics: dict[str, float]


class GateBExecutionArtifactV08(ContractModel):
    protocol: str = Field(pattern=r"^structure-two-gate-b-proxy-diagnostic@0\.8$")
    immutable_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_run_id: str = Field(min_length=1)
    gate_a_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    holdout_opening_artifact_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    producer_source_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arm_implementation_bundle_sha256: dict[str, str]
    six_arm_reference_execution_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_execution_mode: Literal["reduced_proxy_diagnostic"]
    external_actions_from_fidelity_validated_implementation: Literal[False]
    arm_action_producer_ids: dict[str, str]
    world_rows: tuple[dict[str, Any], ...] = Field(min_length=1)
    rollout_rows: tuple[dict[str, Any], ...] = Field(min_length=1)
    episode_actions_by_arm: dict[str, tuple[tuple[str, tuple[str, ...]], ...]]
    executor_key_id: str = Field(min_length=1)
    executor_public_key_base64: str = Field(min_length=1)
    executor_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executor_attestation: Attestation | None = None

    @model_validator(mode="after")
    def validate_exact_arms(self) -> GateBExecutionArtifactV08:
        if tuple(self.arm_implementation_bundle_sha256) != EXPECTED_ARMS:
            raise ValueError("Gate B execution artifact changed the canonical arm order")
        if tuple(self.episode_actions_by_arm) != EXPECTED_ARMS:
            raise ValueError("Gate B execution artifact lacks the canonical ten arms")
        if tuple(self.arm_action_producer_ids) != EXPECTED_ARMS or set(
            self.arm_action_producer_ids.values()
        ) != {"structure-two-world-arm-adapter@0.4"}:
            raise ValueError("Gate B diagnostic artifact action-producer set is invalid")
        if any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            for value in self.arm_implementation_bundle_sha256.values()
        ):
            raise ValueError("Gate B implementation bundle digest is malformed")
        return self


def validation_seed_commitment_sha256_v0_8(
    *,
    world_seeds: Sequence[int],
    trajectory_seeds: Sequence[int],
    observation_seeds: Sequence[int],
    nonce: str,
) -> str:
    return content_sha256(
        {
            "protocol": VALIDATION_SEED_OPENING_PROTOCOL_ID,
            "validation_world_seeds": tuple(world_seeds),
            "trajectory_seeds": tuple(trajectory_seeds),
            "observation_seeds": tuple(observation_seeds),
            "nonce": nonce,
        }
    )


def holdout_commitment_sha256_v0_8(
    *,
    validation_seed_commitment_sha256: str,
    world_distribution: Mapping[str, Any],
    estimator: Mapping[str, float | int],
    bootstrap_draws: int,
    nonce: str,
) -> str:
    return content_sha256(
        {
            "protocol": HOLDOUT_COMMITMENT_PROTOCOL_ID,
            "validation_seed_commitment_sha256": validation_seed_commitment_sha256,
            "world_distribution": dict(world_distribution),
            "estimator": dict(estimator),
            "bootstrap_draws": bootstrap_draws,
            "nonce": nonce,
        }
    )


def load_frozen_holdout_opening_v0_8(
    path: Path,
    *,
    expected_manifest_sha256: str,
    expected_producer_run_id: str,
    expected_validation_seed_commitment_sha256: str,
    expected_holdout_commitment_sha256: str,
) -> FrozenHoldoutOpeningV08:
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("frozen holdout opening must be a JSON object")
    unsigned = dict(payload)
    stored = unsigned.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned) != stored:
        raise ValueError("frozen holdout opening content hash mismatch")
    opening = FrozenHoldoutOpeningV08.model_validate(unsigned)
    if (
        opening.immutable_manifest_sha256 != expected_manifest_sha256
        or opening.producer_run_id != expected_producer_run_id
    ):
        raise ValueError("frozen holdout opening run context mismatch")
    if (
        opening.validation_seed_commitment_sha256 != expected_validation_seed_commitment_sha256
        or opening.holdout_commitment_sha256 != expected_holdout_commitment_sha256
    ):
        raise ValueError("frozen holdout commitment opening failed")
    return opening


def _bootstrap_ci_lower(values: Sequence[float], *, draws: int, label: str) -> float:
    if not values:
        raise ValueError("cannot bootstrap an empty validation world set")
    rng = random.Random(f"{HOLDOUT_OPENING_PROTOCOL_ID}:{label}:world-bootstrap")
    samples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(draws))
    return float(samples[int(0.025 * draws)])


def recompute_frozen_holdout_v0_8(
    opening: FrozenHoldoutOpeningV08,
) -> RecomputedFrozenHoldoutV08:
    generator_module = importlib.import_module(
        "cpswm.system.evaluation_operations.structure_two_world_generator_v0_2"
    )
    gate_module = importlib.import_module(
        "cpswm.system.evaluation_operations.structure_two_world_gate_v0_3"
    )
    rolling_module = importlib.import_module(
        "cpswm.system.evaluation_operations.structure_two_world_rolling_gate_v0_4"
    )
    distribution = generator_module.WorldDistributionConfig.from_manifest(
        opening.world_distribution
    )
    estimator = gate_module.ShrunkEstimatorConfig(
        window_days=int(opening.estimator["window_days"]),
        context_shrinkage_pseudocounts=float(opening.estimator["context_shrinkage_pseudocounts"]),
        owner_probability_threshold=float(opening.estimator["owner_probability_threshold"]),
    )
    generator = generator_module.StructureTwoWorldGeneratorV02(distribution)
    worlds = tuple(generator.sample_world(seed) for seed in opening.validation_world_seeds)
    world_rows: list[dict[str, Any]] = []
    rollout_rows: list[dict[str, Any]] = []
    world_rollouts: list[tuple[Any, Any]] = []
    world_metrics: dict[int, dict[str, float]] = {}
    for world in worlds:
        world_payload = asdict(world)
        world_rows.append(
            {
                "world_seed": world.world_seed,
                "world_hash": world.world_hash,
                "world_content_sha256": content_sha256(world_payload),
            }
        )
        readings = []
        for trajectory_seed in opening.trajectory_seeds:
            for observation_seed in opening.observation_seeds:
                rollout = generator.generate_rollout(
                    world,
                    trajectory_seed=trajectory_seed,
                    observation_seed=observation_seed,
                )
                reading = rolling_module.evaluate_rolling_rollout(
                    rollout, world, distribution, estimator
                )
                world_rollouts.append((world, rollout))
                readings.append(reading)
                rollout_rows.append(
                    {
                        "rollout_id": rollout.rollout_id,
                        "world_seed": world.world_seed,
                        "trajectory_seed": trajectory_seed,
                        "observation_seed": observation_seed,
                        "rollout_content_sha256": content_sha256(asdict(rollout)),
                        "reading_content_sha256": content_sha256(asdict(reading)),
                    }
                )
        world_metrics[world.world_seed] = rolling_module._world_metric(readings)
    fields = tuple(next(iter(world_metrics.values())))
    overall = {
        field: mean(world_metrics[seed][field] for seed in opening.validation_world_seeds)
        for field in fields
    }
    metrics = {
        "unique_validation_world_fraction": len({world.world_hash for world in worlds})
        / len(worlds),
        "put_back_sticky_error": overall["put_back_sticky_error"],
        "put_back_visible_history_gain_over_sticky": overall[
            "put_back_visible_history_gain_over_sticky"
        ],
        "put_back_visible_history_gain_ci_lower": _bootstrap_ci_lower(
            [
                world_metrics[seed]["put_back_visible_history_gain_over_sticky"]
                for seed in opening.validation_world_seeds
            ],
            draws=opening.bootstrap_draws,
            label="put-back-visible-history-gain",
        ),
        "put_back_context_gain_over_pooled": overall["put_back_context_gain_over_pooled"],
        "put_back_visible_history_error": overall["put_back_visible_history_error"],
        "on_owner_observed_target_match_rate": overall["on_owner_observed_target_match_rate"],
        "search_last_observed_error": overall["search_last_observed_error"],
        "search_top1_gain": overall["search_top1_gain"],
        "search_visible_history_error": overall["search_visible_history_error"],
        "unobserved_location_change_rate": overall["unobserved_location_change_rate"],
    }
    return RecomputedFrozenHoldoutV08(
        opening=opening,
        worlds=worlds,
        world_rollouts=tuple(world_rollouts),
        world_rows=tuple(world_rows),
        rollout_rows=tuple(rollout_rows),
        metrics=metrics,
    )


def make_gate_b_execution_artifact_v0_8(
    *,
    recomputed_holdout: RecomputedFrozenHoldoutV08,
    holdout_opening_artifact_file_sha256: str,
    gate_a_content_sha256: str,
    producer_source_bundle_sha256: str,
    arm_implementation_bundle_sha256: Mapping[str, str],
    six_arm_reference_execution_content_sha256: str,
    executor: Ed25519AttestationSigner,
) -> dict[str, Any]:
    adapter_module = importlib.import_module(
        "cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4"
    )
    actions = adapter_module.produce_arm_prediction_rows(recomputed_holdout.world_rollouts)
    verifier = executor.verifier()
    unsigned = GateBExecutionArtifactV08(
        protocol=GATE_B_EXECUTION_PROTOCOL_ID,
        immutable_manifest_sha256=(recomputed_holdout.opening.immutable_manifest_sha256),
        producer_run_id=recomputed_holdout.opening.producer_run_id,
        gate_a_content_sha256=gate_a_content_sha256,
        holdout_opening_artifact_file_sha256=holdout_opening_artifact_file_sha256,
        producer_source_bundle_sha256=producer_source_bundle_sha256,
        arm_implementation_bundle_sha256=dict(arm_implementation_bundle_sha256),
        six_arm_reference_execution_content_sha256=(six_arm_reference_execution_content_sha256),
        action_execution_mode="reduced_proxy_diagnostic",
        external_actions_from_fidelity_validated_implementation=False,
        arm_action_producer_ids={
            arm: "structure-two-world-arm-adapter@0.4" for arm in EXPECTED_ARMS
        },
        world_rows=recomputed_holdout.world_rows,
        rollout_rows=recomputed_holdout.rollout_rows,
        episode_actions_by_arm=actions,
        executor_key_id=verifier.key_id,
        executor_public_key_base64=verifier.public_key_base64,
        executor_public_key_sha256=verifier.public_key_sha256,
    )
    signed = unsigned.model_copy(
        update={
            "executor_attestation": executor.sign(
                GATE_B_EXECUTION_ATTESTATION_DOMAIN,
                attested_payload(unsigned, exclude=_GATE_B_EXECUTION_ATTESTATION_EXCLUDE),
            )
        }
    )
    payload = signed.model_dump(mode="json")
    payload["content_sha256"] = content_sha256(payload)
    return payload


def verify_gate_b_proxy_diagnostic_artifact_v0_8(
    path: Path,
    *,
    recomputed_holdout: RecomputedFrozenHoldoutV08,
    expected_gate_a_content_sha256: str,
    expected_producer_source_bundle_sha256: str,
    expected_arm_implementation_bundle_sha256: Mapping[str, str],
    expected_six_arm_reference_execution_content_sha256: str,
    expected_holdout_opening_artifact_file_sha256: str,
    trusted_executor: Ed25519AttestationVerifier,
) -> GateBExecutionArtifactV08:
    payload = json.loads(path.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("Gate B execution artifact must be a JSON object")
    unsigned_payload = dict(payload)
    stored = unsigned_payload.pop("content_sha256", None)
    if not isinstance(stored, str) or content_sha256(unsigned_payload) != stored:
        raise ValueError("Gate B execution artifact content hash mismatch")
    record = GateBExecutionArtifactV08.model_validate(unsigned_payload)
    expected = {
        "immutable_manifest_sha256": (recomputed_holdout.opening.immutable_manifest_sha256),
        "producer_run_id": recomputed_holdout.opening.producer_run_id,
        "gate_a_content_sha256": expected_gate_a_content_sha256,
        "holdout_opening_artifact_file_sha256": (expected_holdout_opening_artifact_file_sha256),
        "producer_source_bundle_sha256": expected_producer_source_bundle_sha256,
        "arm_implementation_bundle_sha256": dict(expected_arm_implementation_bundle_sha256),
        "six_arm_reference_execution_content_sha256": (
            expected_six_arm_reference_execution_content_sha256
        ),
        "world_rows": recomputed_holdout.world_rows,
        "rollout_rows": recomputed_holdout.rollout_rows,
    }
    dumped = record.model_dump(mode="python")
    if any(dumped[name] != value for name, value in expected.items()):
        raise ValueError("Gate B execution artifact frozen-run binding mismatch")
    adapter_module = importlib.import_module(
        "cpswm.system.evaluation_operations.structure_two_world_arm_adapter_v0_4"
    )
    recomputed_actions = adapter_module.produce_arm_prediction_rows(
        recomputed_holdout.world_rollouts
    )
    if record.episode_actions_by_arm != recomputed_actions:
        raise ValueError("Gate B action rows differ from deterministic arm execution")
    if (
        record.executor_key_id != trusted_executor.key_id
        or record.executor_public_key_base64 != trusted_executor.public_key_base64
        or record.executor_public_key_sha256 != trusted_executor.public_key_sha256
    ):
        raise AttestationError("Gate B execution artifact used an untrusted executor")
    trusted_executor.verify(
        GATE_B_EXECUTION_ATTESTATION_DOMAIN,
        attested_payload(record, exclude=_GATE_B_EXECUTION_ATTESTATION_EXCLUDE),
        record.executor_attestation,
    )
    return record


def verify_gate_b_execution_artifact_v0_8(
    path: Path,
    *,
    recomputed_holdout: RecomputedFrozenHoldoutV08,
    expected_gate_a_content_sha256: str,
    expected_producer_source_bundle_sha256: str,
    expected_arm_implementation_bundle_sha256: Mapping[str, str],
    expected_six_arm_reference_execution_content_sha256: str,
    expected_holdout_opening_artifact_file_sha256: str,
    trusted_executor: Ed25519AttestationVerifier,
) -> GateBExecutionArtifactV08:
    """Reject the existing proxy runner at the canonical scoring boundary."""

    verify_gate_b_proxy_diagnostic_artifact_v0_8(
        path,
        recomputed_holdout=recomputed_holdout,
        expected_gate_a_content_sha256=expected_gate_a_content_sha256,
        expected_producer_source_bundle_sha256=expected_producer_source_bundle_sha256,
        expected_arm_implementation_bundle_sha256=(expected_arm_implementation_bundle_sha256),
        expected_six_arm_reference_execution_content_sha256=(
            expected_six_arm_reference_execution_content_sha256
        ),
        expected_holdout_opening_artifact_file_sha256=(
            expected_holdout_opening_artifact_file_sha256
        ),
        trusted_executor=trusted_executor,
    )
    raise ValueError(
        "reduced-proxy diagnostic actions were not produced by the "
        "fidelity-validated implementation bundles and cannot score canonical Gate B"
    )


__all__ = [
    "GATE_B_EXECUTION_ATTESTATION_DOMAIN",
    "GATE_B_EXECUTION_PROTOCOL_ID",
    "GATE_B_PROXY_DIAGNOSTIC_PROTOCOL_ID",
    "HOLDOUT_COMMITMENT_PROTOCOL_ID",
    "HOLDOUT_OPENING_PROTOCOL_ID",
    "VALIDATION_SEED_OPENING_PROTOCOL_ID",
    "FrozenHoldoutOpeningV08",
    "GateBExecutionArtifactV08",
    "RecomputedFrozenHoldoutV08",
    "holdout_commitment_sha256_v0_8",
    "load_frozen_holdout_opening_v0_8",
    "make_gate_b_execution_artifact_v0_8",
    "recompute_frozen_holdout_v0_8",
    "validate_canonical_holdout_opening_v0_8",
    "validation_seed_commitment_sha256_v0_8",
    "verify_gate_b_execution_artifact_v0_8",
    "verify_gate_b_proxy_diagnostic_artifact_v0_8",
]
