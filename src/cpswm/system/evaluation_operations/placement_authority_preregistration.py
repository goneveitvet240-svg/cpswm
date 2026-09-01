"""Fail-closed v0.2 preregistration for authority-scoped placement decisions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, require_aware

PREREGISTRATION_SCHEMA = "cpswm.PlacementAuthorityPreregistration"
PREREGISTRATION_VERSION = "0.2.0"
CANDIDATE_VERSION = "authority-scoped-placement-resolver@0.2"

REQUIRED_OPPONENTS = frozenset({"collapsed_placement_memory", "authority_agnostic_rule_resolver"})
REQUIRED_SCENARIOS = frozenset(
    {
        "behavior_preference_conflict",
        "visitor_owner_conflict",
        "authorized_reporter_owner_conflict",
        "same_authority_recency",
        "same_authority_simultaneous_conflict",
        "low_authority_instance_high_authority_class",
        "hard_must_vs_forbid_conflict",
        "multiple_hard_required_locations",
        "hard_safety_retraction",
        "no_preference_abstention",
    }
)


class ParentFailureBinding(ContractModel):
    method_id: Literal["s1.four_layer_placement_semantics"]
    decision: Literal["falsified"]
    artifact_path: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class LegacyReproducibility(ContractModel):
    resolver: Literal["PlacementDecisionResolver"]
    expected_visitor_owner_failure_preserved: Literal[True]
    legacy_result_must_not_be_overwritten: Literal[True]


class AuthorityTopology(ContractModel):
    preference_order: tuple[str, ...] = Field(min_length=5)
    precedence: tuple[str, ...] = Field(min_length=5)
    conflict_action: Literal["verify_or_abstain"]
    low_authority_instance_may_override_high_authority_class: Literal[False]
    simultaneous_equal_authority_conflict_may_auto_resolve: Literal[False]
    hard_norm_conflict_may_auto_resolve: Literal[False]

    @model_validator(mode="after")
    def _freeze_order(self) -> Self:
        if self.preference_order != (
            "system_admin",
            "household_owner",
            "authorized_corrector",
            "authorized_reporter",
            "unverified_reporter",
        ):
            raise ValueError("authority order differs from the frozen v0.2 topology")
        if self.precedence != (
            "hard_norm_consistency",
            "preference_authority",
            "subject_specificity",
            "recorded_time",
            "deterministic_record_id_only_for_identical_location",
        ):
            raise ValueError("decision precedence differs from the frozen v0.2 topology")
        return self


class OpponentProtocol(ContractModel):
    opponent_id: str = Field(min_length=1)
    fidelity: Literal["independently_tuned_matched"]
    tuning_grid: tuple[float | str, ...] = Field(min_length=1)


class ValidationSplit(ContractModel):
    seed_start: int = Field(gt=0)
    seed_count: int = Field(ge=20)
    allowed_uses: tuple[
        Literal["opponent_tuning", "candidate_debugging", "power_reestimation"], ...
    ]


class SealedTestSplit(ContractModel):
    seed_start: int = Field(gt=0)
    seed_count: int = Field(ge=100)
    cluster_axis: Literal["household"]
    execution_status: Literal["not_executed"]
    unlock_condition: Literal["candidate_code_and_all_tuning_choices_frozen"]


class ActionBudget(ContractModel):
    placement_decisions_per_episode: Literal[1]
    verification_actions_per_episode: Literal[1]
    all_methods_share_visible_records: Literal[True]


class CostPoint(ContractModel):
    wrong_placement: float = Field(gt=0)
    hard_safety_violation: float = Field(gt=0)
    verification: float = Field(ge=0)
    unnecessary_abstention: float = Field(ge=0)


class Endpoints(ContractModel):
    primary: Literal["wrong_placement_cost"]
    mechanism: Literal["semantic_layer_violation"]
    guardrails: tuple[str, ...] = Field(min_length=3)
    cost_sensitivity_grid: tuple[CostPoint, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def _freeze_guardrails(self) -> Self:
        required = {
            "hard_safety_violation_rate",
            "unauthorized_override_rate",
            "unnecessary_verification_rate",
        }
        if set(self.guardrails) != required:
            raise ValueError("all frozen placement-authority guardrails are required")
        return self


class DecisionRule(ContractModel):
    confidence_level: float
    bootstrap_samples: int = Field(ge=5000)
    independent_unit: Literal["household"]
    action_noninferiority_margin: float
    mechanism_superiority_margin: float
    survival_requires_every_opponent: Literal[True]
    hard_safety_violation_tolerance: float
    falsified_if_any: tuple[str, ...] = Field(min_length=5)

    @model_validator(mode="after")
    def _freeze_numeric_decision_rule(self) -> Self:
        if self.confidence_level != 0.95:
            raise ValueError("confidence level must remain frozen at 0.95")
        if any(
            value != 0.0
            for value in (
                self.action_noninferiority_margin,
                self.mechanism_superiority_margin,
                self.hard_safety_violation_tolerance,
            )
        ):
            raise ValueError("placement-authority margins and safety tolerance must remain zero")
        return self


class ReportingRule(ContractModel):
    report_all_scenario_families: Literal[True]
    report_all_cost_sensitivity_points: Literal[True]
    report_household_cluster_intervals: Literal[True]
    report_legacy_v0_1_failure_alongside_v0_2: Literal[True]
    external_validity_required_for_paper_claim: Literal[True]


class PlacementAuthorityPreregistration(ContractModel):
    schema_name: Literal["cpswm.PlacementAuthorityPreregistration"]
    schema_version: Literal["0.2.0"]
    route_id: Literal["s1.four_layer_placement_semantics@0.2"]
    candidate_version: Literal["authority-scoped-placement-resolver@0.2"]
    frozen_at: datetime
    parent_failure: ParentFailureBinding
    legacy_reproducibility: LegacyReproducibility
    authority_topology: AuthorityTopology
    opponents: tuple[OpponentProtocol, ...]
    scenario_families: tuple[str, ...]
    validation_split: ValidationSplit
    sealed_test_split: SealedTestSplit
    action_budget: ActionBudget
    endpoints: Endpoints
    decision_rule: DecisionRule
    reporting: ReportingRule

    @field_validator("frozen_at")
    @classmethod
    def _aware_freeze_time(cls, value: datetime) -> datetime:
        return require_aware(value, "frozen_at")

    @model_validator(mode="after")
    def _closed_protocol(self) -> Self:
        opponent_ids = [item.opponent_id for item in self.opponents]
        if len(opponent_ids) != len(set(opponent_ids)):
            raise ValueError("opponents must be unique")
        if set(opponent_ids) != REQUIRED_OPPONENTS:
            raise ValueError("the v0.2 route must face both frozen direct opponents")
        if len(self.scenario_families) != len(set(self.scenario_families)):
            raise ValueError("scenario families must be unique")
        if set(self.scenario_families) != REQUIRED_SCENARIOS:
            raise ValueError("the v0.2 route must cover every frozen scenario family")
        validation = set(
            range(
                self.validation_split.seed_start,
                self.validation_split.seed_start + self.validation_split.seed_count,
            )
        )
        sealed = set(
            range(
                self.sealed_test_split.seed_start,
                self.sealed_test_split.seed_start + self.sealed_test_split.seed_count,
            )
        )
        if validation & sealed:
            raise ValueError("validation and sealed household seeds must be disjoint")
        return self


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_placement_authority_preregistration(
    config_path: Path,
    *,
    repository_root: Path,
) -> PlacementAuthorityPreregistration:
    protocol = PlacementAuthorityPreregistration.model_validate_json(
        config_path.read_text(encoding="utf-8")
    )
    parent_path = repository_root / protocol.parent_failure.artifact_path
    if not parent_path.is_file():
        raise FileNotFoundError(f"parent failure artifact is missing: {parent_path}")
    if file_sha256(parent_path) != protocol.parent_failure.artifact_sha256:
        raise ValueError("parent Round-2 failure artifact hash mismatch")
    return protocol


def build_preregistration_receipt(
    config_path: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    protocol = load_placement_authority_preregistration(
        config_path,
        repository_root=repository_root,
    )
    candidate_path = (
        repository_root / "src/cpswm/world_model/placement_decision/authority_scoped_resolver.py"
    )
    provenance_path = (
        repository_root / "src/cpswm/world_model/placement_decision/authority_provenance.py"
    )
    development_runner_path = (
        repository_root
        / "src/cpswm/system/evaluation_operations/placement_authority_development.py"
    )
    test_path = repository_root / "tests/test_authority_scoped_placement_resolver.py"
    component_hashes = {
        "resolver": file_sha256(candidate_path),
        "authority_provenance": file_sha256(provenance_path),
        "development_runner": file_sha256(development_runner_path),
    }
    return {
        "schema_name": "cpswm.PlacementAuthorityPreregistrationReceipt",
        "schema_version": "0.2.0",
        "route_id": protocol.route_id,
        "candidate_version": protocol.candidate_version,
        "preregistration_sha256": file_sha256(config_path),
        "candidate_source_sha256": component_hashes["resolver"],
        "authority_provenance_source_sha256": component_hashes["authority_provenance"],
        "development_runner_source_sha256": component_hashes["development_runner"],
        "candidate_bundle_sha256": hashlib.sha256(
            json.dumps(
                component_hashes,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "development_test_sha256": file_sha256(test_path),
        "parent_failure_artifact_sha256": protocol.parent_failure.artifact_sha256,
        "validation_household_count": protocol.validation_split.seed_count,
        "sealed_test_household_count": protocol.sealed_test_split.seed_count,
        "sealed_test_execution_status": protocol.sealed_test_split.execution_status,
        "sealed_test_results_present": False,
        "claim_status": "preregistered_not_tested",
    }


__all__ = [
    "CANDIDATE_VERSION",
    "PREREGISTRATION_SCHEMA",
    "PREREGISTRATION_VERSION",
    "PlacementAuthorityPreregistration",
    "build_preregistration_receipt",
    "file_sha256",
    "load_placement_authority_preregistration",
]
