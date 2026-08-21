from __future__ import annotations

from pathlib import Path

from cpswm.system.evaluation_operations.fair_ablation import (
    PROJECT_ONE_ARMS_V01,
    ProjectOneAblationArmId,
)
from cpswm.system.evaluation_operations.online_shift_attribution import OnlineShiftSplit
from cpswm.system.evaluation_operations.project_one_ablation_pilot import (
    PilotAdapterStatus,
    PilotTuningStatus,
    ProjectOneMatchedComparisonId,
    ProjectOneProtocolPilotConfig,
    ProjectOneProtocolPilotReport,
    ProjectOneProtocolPilotRunner,
)

CONFIG = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "project_one_ablation"
    / "project_one_protocol_pilot_v0.1.json"
)
REPORT_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "project_one_ablation"
    / "project_one_protocol_pilot_report_v0.1.fixture.json"
)


def _config() -> ProjectOneProtocolPilotConfig:
    return ProjectOneProtocolPilotConfig.model_validate_json(CONFIG.read_text(encoding="utf-8"))


def test_v01_config_and_report_fixture_round_trip_through_frozen_schemas():
    config = ProjectOneProtocolPilotConfig.model_validate_json(CONFIG.read_text(encoding="utf-8"))
    report = ProjectOneProtocolPilotReport.model_validate_json(
        REPORT_FIXTURE.read_text(encoding="utf-8")
    )

    assert ProjectOneProtocolPilotConfig.model_validate_json(config.model_dump_json()) == config
    assert ProjectOneProtocolPilotReport.model_validate_json(report.model_dump_json()) == report


def test_v01_runner_regenerates_the_authoritative_report_fixture():
    report = ProjectOneProtocolPilotRunner().run(_config())
    expected = ProjectOneProtocolPilotReport.model_validate_json(
        REPORT_FIXTURE.read_text(encoding="utf-8")
    )

    assert report == expected


def test_project_one_protocol_pilot_covers_ten_arms_as_five_matched_pairs():
    report = ProjectOneProtocolPilotRunner().run(_config())

    assert len(report.manifest.comparisons) == 5
    assert {item.comparison_id for item in report.manifest.comparisons} == set(
        ProjectOneMatchedComparisonId
    )
    declared_arms = [
        arm.arm_id for comparison in report.manifest.comparisons for arm in comparison.manifest.arms
    ]
    assert len(declared_arms) == 10
    # v0.1 is frozen to the 10-arm set; adding the v0.2 joint arm to the enum
    # must not retroactively change what a v0.1 report is expected to cover.
    assert set(declared_arms) == PROJECT_ONE_ARMS_V01
    assert all(len(comparison.manifest.arms) == 2 for comparison in report.manifest.comparisons)


def test_project_one_protocol_pilot_is_fail_closed_about_adapter_coverage():
    report = ProjectOneProtocolPilotRunner().run(_config())

    assert report.suite_case_count == 36
    assert report.split_case_counts == {
        OnlineShiftSplit.TRAIN: 18,
        OnlineShiftSplit.VALIDATION: 6,
        OnlineShiftSplit.TEST: 12,
    }
    assert report.protocol_contracts_valid
    assert not report.all_adapters_bound
    assert not report.formal_experiment_ready
    assert report.claim_scope == "protocol_only"

    executed = [
        result
        for result in report.arm_results
        if result.adapter_status == PilotAdapterStatus.EXECUTED
    ]
    assert [result.arm_id for result in executed] == [
        ProjectOneAblationArmId.ORDINARY_BOCPD,
        ProjectOneAblationArmId.CAUSE_FACTORIZED_BOCPD,
    ]
    assert all(result.evaluation_split == OnlineShiftSplit.TEST for result in executed)
    assert all(result.online_shift_report is not None for result in executed)
    assert all(result.online_shift_report.sample_count == 12 for result in executed)
    assert all(result.tuning_status == PilotTuningStatus.NOT_RUN for result in executed)

    unbound = [
        result
        for result in report.arm_results
        if result.adapter_status == PilotAdapterStatus.ADAPTER_UNBOUND
    ]
    assert len(unbound) == 8
    assert all(result.online_shift_report is None for result in unbound)
