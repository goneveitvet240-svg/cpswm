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
        scale = (0.8, 1.0, 1.2)[index % 3]
        return cls(
            index=index,
            likelihood_calibration=scale,
            actor_evidence_weight=scale,
            mechanism_evidence_weight=scale,
            role_evidence_weight=scale,
            unresolved_prior=(0.1, 0.2, 0.3)[index % 3],
            unknown_actor_prior=(0.1, 0.2, 0.3)[index % 3],
            unknown_mechanism_prior=(0.1, 0.2, 0.3)[index % 3],
            orrer_retraction_threshold=(0.3, 0.5, 0.7)[index % 3],
            orrer_reactivation_threshold=(0.4, 0.6, 0.8)[index % 3],
            pchmp_weight=scale,
            bocpd_hazard=(0.02, 0.05, 0.1)[index % 3],
            ccrr_create_threshold=(0.5, 0.65, 0.8)[index % 3],
            ccrr_reactivate_threshold=(0.4, 0.55, 0.7)[index % 3],
            ccrr_stay_threshold=(0.2, 0.35, 0.5)[index % 3],
            rgrc_write_threshold=(0.4, 0.55, 0.7)[index % 3],
            rgrc_quarantine_threshold=(0.2, 0.35, 0.5)[index % 3],
            rgrc_retract_threshold=(0.25, 0.45, 0.65)[index % 3],
            action_utility_threshold=(-0.1, 0.0, 0.1)[index % 3],
            prompt_template_version=f"project-two-evidence-pilot@{index + 1}",
            temperature=(0.0, 0.2, 0.5)[index % 3],
            candidate_count=(3, 5, 8)[index % 3],
        )


class IndependentTuningReceipt(ContractModel):
    receipt_id: UUID = Field(default_factory=uuid4)
    arm_id: str = Field(min_length=1)
    search_budget: int = Field(gt=0)
    candidate_hashes: tuple[str, ...]
    validation_episode_ids: tuple[str, ...] = Field(min_length=1)
    held_out_episode_ids_seen: tuple[str, ...] = ()
    selected_candidate: ProjectTwoTuningCandidate
    selected_validation_objective: tuple[Any, ...]
    created_at: datetime

    @model_validator(mode="after")
    def _sealed(self) -> IndependentTuningReceipt:
        if self.held_out_episode_ids_seen:
            raise ValueError("held-out test cannot participate in parameter selection")
        if len(self.candidate_hashes) != self.search_budget:
            raise ValueError("receipt candidate count must equal tuning budget")
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
                    created_at=datetime.now(UTC),
                )
            )
        return tuple(receipts)


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
