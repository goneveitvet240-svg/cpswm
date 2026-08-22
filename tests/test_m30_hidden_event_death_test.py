from __future__ import annotations

import pytest

from cpswm.system.evaluation_operations import (
    HiddenEventFamily,
    HiddenEventMatchedDeathTest,
    HiddenEventMethod,
    HiddenEventSplit,
    M30HiddenEventSuiteGenerator,
)


@pytest.fixture(scope="module")
def suite():
    return M30HiddenEventSuiteGenerator().generate()


@pytest.fixture(scope="module")
def report(suite):
    return HiddenEventMatchedDeathTest().run(suite)


def test_m30_hidden_event_suite_is_multi_seed_balanced_and_deterministic(suite):
    regenerated = M30HiddenEventSuiteGenerator().generate()

    assert suite == regenerated
    assert len(suite.cases) == 80
    assert sum(case.model_input.split == HiddenEventSplit.VALIDATION for case in suite.cases) == 20
    assert sum(case.model_input.split == HiddenEventSplit.TEST for case in suite.cases) == 60
    assert {case.model_input.family for case in suite.cases} == set(HiddenEventFamily)
    assert all(
        not hasattr(case.model_input, "signature")
        and not hasattr(case.model_input, "responsible_actor_key")
        for case in suite.cases
    )


def test_death_test_independently_tunes_cheh_and_amg_without_unknown_actor_cases(report):
    tuning = {item.method: item for item in report.tuning}

    assert report.validation_case_count == 20
    assert report.test_case_count == 60
    assert tuning[HiddenEventMethod.CHEH].candidate_configuration_count == 6
    assert tuning[HiddenEventMethod.DAMEN_HOGG_2012].candidate_configuration_count == 3
    assert tuning[HiddenEventMethod.ORRER].candidate_configuration_count == 6
    assert tuning[HiddenEventMethod.DAMEN_HOGG_2012_MATCHED].candidate_configuration_count == 3
    assert tuning[HiddenEventMethod.CHEH].validation_case_count == 16
    assert tuning[HiddenEventMethod.DAMEN_HOGG_2012].validation_case_count == 16


def test_strong_compatible_sequence_baseline_already_covers_every_known_actor_truth(report):
    by_method = {item.method: item for item in report.method_reports}
    compatible = by_method[HiddenEventMethod.BERNERT_RAMPARANY_2021]

    assert compatible.final_truth_set_coverage == pytest.approx(1.0)
    assert compatible.responsibility_decision_coverage == pytest.approx(0.0)
    assert compatible.unsupported_case_count == 12


def test_cheh_recovers_responsibility_but_loses_to_fairly_rerun_amg(report):
    by_method = {item.method: item for item in report.method_reports}
    cheh = by_method[HiddenEventMethod.CHEH]
    amg = by_method[HiddenEventMethod.DAMEN_HOGG_2012]

    assert cheh.final_exact_chain_rate == pytest.approx(0.5)
    assert amg.final_exact_chain_rate == pytest.approx(26 / 48)
    assert amg.final_exact_chain_rate > cheh.final_exact_chain_rate
    assert cheh.late_responsibility_recovery_rate == pytest.approx(1.0)
    assert amg.late_responsibility_recovery_rate == pytest.approx(1.0)
    assert cheh.append_only_revision_rate == pytest.approx(1.0)
    assert amg.append_only_revision_rate == pytest.approx(0.0)
    assert "superiority over the matched" in report.scientific_status
    assert "not established" in report.scientific_status


def test_orrer_fixes_complete_chain_and_unknown_role_coverage_but_matches_amg(report):
    by_method = {item.method: item for item in report.method_reports}
    orrer = by_method[HiddenEventMethod.ORRER]
    matched_amg = by_method[HiddenEventMethod.DAMEN_HOGG_2012_MATCHED]

    assert orrer.final_exact_chain_rate == pytest.approx(1.0)
    assert matched_amg.final_exact_chain_rate == pytest.approx(1.0)
    assert orrer.unknown_actor_truth_set_coverage == pytest.approx(1.0)
    assert matched_amg.unknown_actor_truth_set_coverage == pytest.approx(1.0)
    assert orrer.append_only_revision_rate == pytest.approx(1.0)
    assert matched_amg.append_only_revision_rate == pytest.approx(0.0)


def test_unknown_handoff_is_an_explicit_cheh_representation_failure(report):
    cheh_unknown = [
        result
        for result in report.test_results
        if result.method == HiddenEventMethod.CHEH
        and result.family in {HiddenEventFamily.UNKNOWN_DIRECT, HiddenEventFamily.UNKNOWN_HANDOFF}
    ]
    direct = [
        result for result in cheh_unknown if result.family == HiddenEventFamily.UNKNOWN_DIRECT
    ]
    handoff = [
        result for result in cheh_unknown if result.family == HiddenEventFamily.UNKNOWN_HANDOFF
    ]

    assert all(result.truth_in_final_emitted_set is True for result in direct)
    assert all(result.truth_in_final_emitted_set is False for result in handoff)
    assert all(result.final_responsible_actor_correct is True for result in direct)
    assert all(result.final_responsible_actor_correct is True for result in handoff)
    orrer_handoff = [
        result
        for result in report.test_results
        if result.method == HiddenEventMethod.ORRER
        and result.family == HiddenEventFamily.UNKNOWN_HANDOFF
    ]
    assert all(result.truth_in_final_emitted_set is True for result in orrer_handoff)
    assert all(result.final_exact_chain is True for result in orrer_handoff)


def test_correlated_duplicate_is_rejected_without_creating_a_revision(report):
    duplicate_results = [
        result
        for result in report.test_results
        if result.method == HiddenEventMethod.CHEH and result.family.has_duplicate_submission
    ]

    assert len(duplicate_results) == 12
    assert all(result.duplicate_submission_rejected is True for result in duplicate_results)
    assert all(result.append_only_revision_count == 1 for result in duplicate_results)
    orrer_duplicates = [
        result
        for result in report.test_results
        if result.method == HiddenEventMethod.ORRER and result.family.has_duplicate_submission
    ]
    assert all(result.duplicate_submission_rejected is True for result in orrer_duplicates)


def test_stateless_late_evidence_comparisons_are_labeled_as_full_reruns(report):
    stateless = {
        HiddenEventMethod.DAMEN_HOGG_2012,
        HiddenEventMethod.DAMEN_HOGG_2012_MATCHED,
        HiddenEventMethod.TOP1_EVENT_GRAPH,
        HiddenEventMethod.INDEPENDENT_CANDIDATES,
    }
    late_results = [
        result
        for result in report.test_results
        if result.method in stateless and result.family.has_late_evidence and result.supported
    ]

    assert late_results
    assert all(result.update_mode == "full_rerun" for result in late_results)
    assert all(result.append_only_revision_count == 0 for result in late_results)
