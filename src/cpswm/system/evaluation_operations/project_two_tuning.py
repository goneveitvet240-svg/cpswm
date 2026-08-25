"""Equal-budget, independent validation tuning with a sealed held-out gate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from cpswm.contracts import ContractModel


class ProjectTwoExperimentalTrack(StrEnum):
    NO_LLM_CORE = "no_llm_project_two_core"
    LLM_PRIOR_ONLY = "llm_prior_only_project_two"
    LLM_AS_EVIDENCE = "llm_as_evidence_project_two"
    LLM_DIRECT_DECISION = "llm_direct_decision_baseline"
    ORACLE_EVIDENCE = "oracle_evidence_upper_bound"


class ProjectTwoTuningCandidate(ContractModel):
    index: int = Field(ge=0)
    likelihood_calibration: float = Field(gt=0.0)
    actor_evidence_weight: float = Field(ge=0.0)
    mechanism_evidence_weight: float = Field(ge=0.0)
    role_evidence_weight: float = Field(ge=0.0)
    unresolved_prior: float = Field(ge=0.0, le=1.0)
    unknown_actor_prior: float = Field(ge=0.0, le=1.0)
    unknown_mechanism_prior: float = Field(ge=0.0, le=1.0)
    orrer_retraction_threshold: float = Field(ge=0.0, le=1.0)
    orrer_reactivation_threshold: float = Field(ge=0.0, le=1.0)
    pchmp_weight: float = Field(ge=0.0)
    bocpd_hazard: float = Field(gt=0.0, lt=1.0)
    ccrr_create_threshold: float = Field(ge=0.0, le=1.0)
    ccrr_reactivate_threshold: float = Field(ge=0.0, le=1.0)
    ccrr_stay_threshold: float = Field(ge=0.0, le=1.0)
    rgrc_write_threshold: float = Field(ge=0.0, le=1.0)
    rgrc_quarantine_threshold: float = Field(ge=0.0, le=1.0)
    rgrc_retract_threshold: float = Field(ge=0.0, le=1.0)
    action_utility_threshold: float
    prompt_template_version: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    candidate_count: int = Field(gt=0)

    @classmethod
    def pilot(cls, index: int) -> ProjectTwoTuningCandidate:
        # One module group changes per candidate. Index 7 is the first joint
        # candidate and is reachable only after all six grouped candidates.
        values: dict[str, Any] = dict(
            index=index,
            likelihood_calibration=1.0,
            actor_evidence_weight=1.0,
            mechanism_evidence_weight=1.0,
            role_evidence_weight=1.0,
            unresolved_prior=0.2,
            unknown_actor_prior=0.2,
            unknown_mechanism_prior=0.2,
            orrer_retraction_threshold=0.01,
            orrer_reactivation_threshold=0.6,
            pchmp_weight=1.0,
            bocpd_hazard=0.05,
            ccrr_create_threshold=0.65,
            ccrr_reactivate_threshold=0.55,
            ccrr_stay_threshold=0.35,
            rgrc_write_threshold=0.55,
            rgrc_quarantine_threshold=0.35,
            rgrc_retract_threshold=0.45,
            action_utility_threshold=0.0,
            prompt_template_version="project-two-evidence-pilot@base",
            temperature=0.0,
            candidate_count=5,
        )
        stage = index % 8
        updates = {
            1: {"likelihood_calibration": 0.8},
            2: {
                "actor_evidence_weight": 0.8,
                "mechanism_evidence_weight": 1.2,
                "role_evidence_weight": 0.8,
                "unresolved_prior": 0.3,
                "unknown_actor_prior": 0.3,
                "unknown_mechanism_prior": 0.3,
                "pchmp_weight": 0.8,
            },
            3: {
                "orrer_retraction_threshold": 0.3,
                "orrer_reactivation_threshold": 0.8,
            },
            4: {
                "bocpd_hazard": 0.1,
                "ccrr_create_threshold": 0.8,
                "ccrr_reactivate_threshold": 0.7,
                "ccrr_stay_threshold": 0.5,
                "rgrc_write_threshold": 0.7,
                "rgrc_quarantine_threshold": 0.5,
                "rgrc_retract_threshold": 0.65,
            },
            5: {"action_utility_threshold": 0.1},
            6: {
                "prompt_template_version": "project-two-evidence-pilot@llm-group",
                "temperature": 0.2,
                "candidate_count": 8,
            },
            7: {
                "likelihood_calibration": 1.2,
                "actor_evidence_weight": 1.2,
                "mechanism_evidence_weight": 1.2,
                "role_evidence_weight": 1.2,
                "unresolved_prior": 0.1,
                "unknown_actor_prior": 0.1,
                "unknown_mechanism_prior": 0.1,
                "orrer_retraction_threshold": 0.5,
                "orrer_reactivation_threshold": 0.4,
                "pchmp_weight": 1.2,
                "bocpd_hazard": 0.02,
                "ccrr_create_threshold": 0.5,
                "ccrr_reactivate_threshold": 0.4,
                "ccrr_stay_threshold": 0.2,
                "rgrc_write_threshold": 0.4,
                "rgrc_quarantine_threshold": 0.2,
                "rgrc_retract_threshold": 0.25,
                "action_utility_threshold": -0.1,
                "prompt_template_version": "project-two-evidence-pilot@joint",
                "temperature": 0.5,
                "candidate_count": 3,
            },
        }.get(stage, {})
        values.update(updates)
        return cls(**values)


class RuntimeParameterBinding(ContractModel):
    parameter: str
    target_component: str
    configured_value: Any
    component_config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_trace_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class RuntimeParameterInjectionReceipt(ContractModel):
    receipt_id: UUID = Field(default_factory=uuid4)
    arm_id: str
    candidate_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    bindings: tuple[RuntimeParameterBinding, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> RuntimeParameterInjectionReceipt:
        names = [item.parameter for item in self.bindings]
        if len(names) != len(set(names)):
            raise ValueError("runtime parameter bindings must be unique")
        return self


class UnusedRuntimeParameterError(ValueError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def build_runtime_parameter_receipt(
    *,
    arm_id: str,
    candidate: ProjectTwoTuningCandidate,
    bindings: dict[str, tuple[str, Any, Any]],
    declared_parameters: set[str] | None = None,
) -> RuntimeParameterInjectionReceipt:
    """Freeze actual component config and observed runtime value per parameter."""

    declared = declared_parameters or (set(type(candidate).model_fields) - {"index"})
    missing = declared - set(bindings)
    extra = set(bindings) - declared
    if missing or extra:
        raise UnusedRuntimeParameterError(
            f"runtime parameter coverage mismatch: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    candidate_payload = candidate.model_dump(mode="json")
    return RuntimeParameterInjectionReceipt(
        arm_id=arm_id,
        candidate_hash=_digest(candidate_payload),
        bindings=tuple(
            RuntimeParameterBinding(
                parameter=name,
                target_component=component,
                configured_value=configured,
                component_config_hash=_digest(
                    {"component": component, "parameter": name, "configured": configured}
                ),
                runtime_trace_hash=_digest(
                    {"component": component, "parameter": name, "observed": observed}
                ),
            )
            for name, (component, configured, observed) in sorted(bindings.items())
        ),
    )


def reject_unused_parameter_changes(
    *,
    before_candidate: ProjectTwoTuningCandidate,
    after_candidate: ProjectTwoTuningCandidate,
    before_receipt: RuntimeParameterInjectionReceipt,
    after_receipt: RuntimeParameterInjectionReceipt,
) -> None:
    before = {item.parameter: item for item in before_receipt.bindings}
    after = {item.parameter: item for item in after_receipt.bindings}
    for name in set(type(before_candidate).model_fields) - {"index"}:
        if getattr(before_candidate, name) == getattr(after_candidate, name):
            continue
        if name not in before or name not in after:
            raise UnusedRuntimeParameterError(f"changed parameter {name} was not injected")
        if (
            before[name].component_config_hash == after[name].component_config_hash
            and before[name].runtime_trace_hash == after[name].runtime_trace_hash
        ):
            raise UnusedRuntimeParameterError(
                f"changed parameter {name} altered neither component config nor runtime trace"
            )


class IndependentTuningReceipt(ContractModel):
    receipt_id: UUID = Field(default_factory=uuid4)
    arm_id: str = Field(min_length=1)
    search_budget: int = Field(gt=0)
    early_stop_rule: str = "exhaust_common_budget"
    candidate_hashes: tuple[str, ...]
    validation_episode_ids: tuple[str, ...] = Field(min_length=1)
    held_out_episode_ids_seen: tuple[str, ...] = ()
    selected_candidate: ProjectTwoTuningCandidate
    selected_validation_objective: tuple[Any, ...]
    tuning_stages: tuple[str, ...] = Field(min_length=1)
    runtime_parameter_status: str = "pending_runtime_evidence"
    runtime_candidate_receipt_ids: tuple[UUID, ...] = ()
    created_at: datetime

    @model_validator(mode="after")
    def _sealed(self) -> IndependentTuningReceipt:
        if self.held_out_episode_ids_seen:
            raise ValueError("held-out test cannot participate in parameter selection")
        if len(self.candidate_hashes) != self.search_budget:
            raise ValueError("receipt candidate count must equal tuning budget")
        if (
            self.runtime_parameter_status == "injected"
            and len(self.runtime_candidate_receipt_ids) != self.search_budget
        ):
            raise ValueError("every tuning candidate requires one runtime parameter receipt")
        return self


class ProjectTwoFairTuner:
    def __init__(self, *, search_budget: int) -> None:
        if search_budget <= 0:
            raise ValueError("search_budget must be positive")
        self.search_budget = search_budget

    def tune_all(
        self,
        *,
        arm_ids: Sequence[str],
        candidates: Sequence[ProjectTwoTuningCandidate],
        validation_episode_ids: Sequence[str],
        evaluator: Callable[[str, ProjectTwoTuningCandidate], tuple[Any, ...]],
    ) -> tuple[IndependentTuningReceipt, ...]:
        if len(candidates) != self.search_budget:
            raise ValueError("every arm must receive exactly the common search budget")
        if len(set(arm_ids)) != len(arm_ids):
            raise ValueError("arm ids must be unique for independent receipts")
        stages = _validate_grouped_candidate_sequence(candidates)
        hashes = tuple(
            hashlib.sha256(
                json.dumps(item.model_dump(mode="json"), sort_keys=True).encode()
            ).hexdigest()
            for item in candidates
        )
        receipts = []
        for arm in arm_ids:
            scored = [(evaluator(arm, item), item.index, item) for item in candidates]
            objective, _index, selected = min(scored, key=lambda item: (item[0], item[1]))
            receipts.append(
                IndependentTuningReceipt(
                    arm_id=arm,
                    search_budget=self.search_budget,
                    candidate_hashes=hashes,
                    validation_episode_ids=tuple(validation_episode_ids),
                    selected_candidate=selected,
                    selected_validation_objective=objective,
                    tuning_stages=stages,
                    created_at=datetime.now(UTC),
                )
            )
        return tuple(receipts)


_TUNING_GROUPS = {
    "feedback_likelihood": {"likelihood_calibration"},
    "open_world_semantics": {
        "actor_evidence_weight",
        "mechanism_evidence_weight",
        "role_evidence_weight",
        "unresolved_prior",
        "unknown_actor_prior",
        "unknown_mechanism_prior",
        "pchmp_weight",
    },
    "reversible_revision": {
        "orrer_retraction_threshold",
        "orrer_reactivation_threshold",
    },
    "project_one_regime": {
        "bocpd_hazard",
        "ccrr_create_threshold",
        "ccrr_reactivate_threshold",
        "ccrr_stay_threshold",
        "rgrc_write_threshold",
        "rgrc_quarantine_threshold",
        "rgrc_retract_threshold",
    },
    "action_selection": {"action_utility_threshold"},
    "llm_request": {"prompt_template_version", "temperature", "candidate_count"},
}


def _validate_grouped_candidate_sequence(
    candidates: Sequence[ProjectTwoTuningCandidate],
) -> tuple[str, ...]:
    baseline = candidates[0]
    stages = ["baseline"]
    seen_groups: set[str] = set()
    for candidate in candidates[1:]:
        changed = {
            name
            for name in type(candidate).model_fields
            if name != "index" and getattr(candidate, name) != getattr(baseline, name)
        }
        matching = [name for name, fields in _TUNING_GROUPS.items() if changed <= fields]
        if matching:
            stage = matching[0]
            seen_groups.add(stage)
            stages.append(stage)
            continue
        if seen_groups != set(_TUNING_GROUPS):
            raise ValueError("joint tuning candidate requires every module group first")
        stages.append("joint")
    return tuple(stages)


class SealedHeldOutRunGuard:
    def __init__(self, *, frozen_hash: str) -> None:
        self.frozen_hash = frozen_hash
        self._opened = False
        self.test_episode_ids: tuple[str, ...] = ()

    @classmethod
    def freeze(cls, *, receipts, arm_ids, ablations) -> SealedHeldOutRunGuard:
        receipt_arms = {item.arm_id for item in receipts}
        if receipt_arms != set(arm_ids):
            raise ValueError("all frozen arms require independent tuning receipts")
        payload = {
            "receipts": [item.model_dump(mode="json") for item in receipts],
            "arm_ids": list(arm_ids),
            "ablations": [item.value for item in ablations],
        }
        return cls(
            frozen_hash=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        )

    def open_once(self, test_episode_ids: Sequence[str]) -> None:
        if self._opened:
            raise RuntimeError("sealed held-out test may run exactly once")
        if not test_episode_ids:
            raise ValueError("held-out test must be non-empty")
        self.test_episode_ids = tuple(test_episode_ids)
        self._opened = True
