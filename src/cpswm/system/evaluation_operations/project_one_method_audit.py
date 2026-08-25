"""Fail-closed audit contract for unresolved project-one method claims."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MDESource(StrEnum):
    LEGACY_GUARDRAIL = "legacy_guardrail"
    ACTION_DERIVED = "action_derived"


REQUIRED_ACTION_TASKS = frozenset({"search", "put_back", "delivery"})
REQUIRED_MATCHED_BASELINES = frozenset(
    {
        "ewma",
        "cusum",
        "rls_fixed_threshold",
        "ordinary_bocpd",
        "bocpdms",
        "no_cf_bocpd",
        "no_ccrr",
        "no_regime_reactivation",
        "context_frequency",
        "persistence",
    }
)


@dataclass(frozen=True, slots=True)
class ProjectOneMethodAudit:
    independently_tuned_arms: frozenset[str] = frozenset()
    action_tasks_with_utility: frozenset[str] = frozenset()
    mde_source: MDESource = MDESource.LEGACY_GUARDRAIL
    minimum_detectable_effect: float = 0.05
    anomaly_change_metrics_separated: bool = False
    dirichlet_increment_demonstrated: bool = False
    external_validity_demonstrated: bool = False

    def __post_init__(self) -> None:
        if self.minimum_detectable_effect <= 0.0:
            raise ValueError("minimum_detectable_effect must be positive")
        unknown_tasks = self.action_tasks_with_utility - REQUIRED_ACTION_TASKS
        if unknown_tasks:
            raise ValueError(f"unknown action utility task(s): {sorted(unknown_tasks)}")

    @property
    def missing_requirements(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.independently_tuned_arms >= REQUIRED_MATCHED_BASELINES:
            missing.append("independently_tuned_matched_baselines")
        if not self.action_tasks_with_utility >= REQUIRED_ACTION_TASKS:
            missing.append("search_put_back_delivery_utility")
        if self.mde_source is not MDESource.ACTION_DERIVED:
            missing.append("action_derived_mde")
        if not self.anomaly_change_metrics_separated:
            missing.append("anomaly_change_separation")
        if not self.dirichlet_increment_demonstrated:
            missing.append("dirichlet_increment")
        if not self.external_validity_demonstrated:
            missing.append("external_validity")
        return tuple(missing)

    @property
    def activated(self) -> bool:
        return not self.missing_requirements
