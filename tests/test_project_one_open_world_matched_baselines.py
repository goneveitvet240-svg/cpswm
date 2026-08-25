from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cpswm.system.evaluation_operations.project_one_dataset import (
    UNKNOWN_LOCATION,
    ProjectOneDatasetRecord,
)
from cpswm.system.evaluation_operations.project_one_matched_baselines import (
    BOCPDMSMethod,
    CUSUMMethod,
    EWMAMethod,
    OrdinaryBOCPDMethod,
    RLSFixedThresholdMethod,
)
from cpswm.system.evaluation_operations.project_one_method_audit import (
    REQUIRED_ACTION_TASKS,
    REQUIRED_MATCHED_BASELINES,
    MDESource,
    ProjectOneMethodAudit,
)
from cpswm.system.evaluation_operations.project_one_protocol import (
    DecisionChainAblation,
    ProjectOneProtocolConfig,
)


def _record(index: int, location: str) -> ProjectOneDatasetRecord:
    return ProjectOneDatasetRecord(
        stream_id="matched",
        event_id=f"e{index}",
        subject_id="owner",
        household_id="home",
        object_id="cup",
        actor_id="owner" if index == 0 else "guest",
        timestamp=datetime(2026, 8, 1, tzinfo=UTC) + timedelta(hours=index),
        context_key="morning",
        context_value=float(index),
        observed_location=location,
        observation_quality=0.9,
    )


def test_matched_online_baselines_share_the_same_method_contract() -> None:
    locations = ("table", "sink", UNKNOWN_LOCATION)
    methods = (
        EWMAMethod(locations, open_set=True),
        CUSUMMethod(locations, open_set=True),
        RLSFixedThresholdMethod(locations, open_set=True),
        OrdinaryBOCPDMethod(locations, open_set=True),
        BOCPDMSMethod(locations, open_set=True),
    )
    first = _record(0, "table")
    unseen = _record(1, "balcony")
    for method in methods:
        method.observe(first)
        prediction = method.observe(unseen)
        assert UNKNOWN_LOCATION in prediction.predicted_location_probabilities
        assert method.snapshot()["open_set_hits"] == 1
        assert method.config_hash()


def test_each_decision_chain_ablation_projects_exactly_one_disabled_mechanism() -> None:
    expected = {
        DecisionChainAblation.NO_CF_BOCPD: (False, True, True),
        DecisionChainAblation.NO_CCRR: (True, False, True),
        DecisionChainAblation.NO_REGIME_REACTIVATION: (True, True, False),
    }
    for ablation, flags in expected.items():
        loop = ProjectOneProtocolConfig(decision_chain_ablation=ablation).loop_config()
        assert (
            loop.cause_factorized_bocpd_enabled,
            loop.ccrr_enabled,
            loop.regime_reactivation_enabled,
        ) == flags


def test_method_audit_is_fail_closed_until_action_evidence_exists() -> None:
    assert ProjectOneMethodAudit().activated is False
    complete = ProjectOneMethodAudit(
        independently_tuned_arms=REQUIRED_MATCHED_BASELINES,
        action_tasks_with_utility=REQUIRED_ACTION_TASKS,
        mde_source=MDESource.ACTION_DERIVED,
        minimum_detectable_effect=0.02,
        anomaly_change_metrics_separated=True,
        dirichlet_increment_demonstrated=True,
        external_validity_demonstrated=True,
    )
    assert complete.activated is True
