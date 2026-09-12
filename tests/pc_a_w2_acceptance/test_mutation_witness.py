"""Checker unit tests only; real CLI/capability evidence is reported separately."""

import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "independent_mutations",
    Path(__file__).resolve().parents[2] / "tools/pc_a_w2_acceptance/inspect_archived_mutations.py",
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def nested(parts, value):
    if not parts:
        return value
    if parts[0] in ("*", "0"):
        return [nested(parts[1:], value)]
    return {parts[0]: nested(parts[1:], value)}


def sample(case, value):
    data = nested(m.SELECTORS[case].split("."), value)
    data.setdefault("audit", {}).setdefault("source_bindings", {"production.py": "same-source"})
    return data


@pytest.mark.parametrize("case", m.SELECTORS)
def test_noop_recomputed_metadata_cannot_count_as_conclusion_attack(case):
    before = sample(case, "unchanged")
    attack = copy.deepcopy(before)
    attack["irrelevant_recomputed_hash"] = "different"
    with pytest.raises(ValueError, match="NO_CONCLUSION_MUTATION"):
        m.mutation_witness(before, attack, case)


@pytest.mark.parametrize("case", m.SELECTORS)
def test_designated_dependency_change_has_nonempty_witness(case):
    row = m.mutation_witness(sample(case, "before"), sample(case, "after"), case)
    assert row["before_sha256"] != row["after_sha256"]


def test_changed_semantics_with_stale_source_is_not_semantic_rejection_proof():
    case = "corrected_memory"
    before, after = sample(case, False), sample(case, True)
    after["audit"]["source_bindings"] = {"production.py": "other-source"}
    with pytest.raises(ValueError, match="STALE_SOURCE"):
        m.mutation_witness(before, after, case)


def valid_batch():
    return {
        "fresh_replay_performed": True,
        "results": [
            {"bundle": "reference", "status": "CURRENT_SOURCE_FRESH_REPLAY_MATCH"},
            {"bundle": "attack", "status": "REJECTED", "error": "FRESH_REPLAY_STEP_MISMATCH"},
        ],
    }


def test_batch_checker_positive_is_only_log_consistency():
    assert m.check_cli_batch(valid_batch(), "reference", {"corrected_memory": "attack"}) == 1


@pytest.mark.parametrize(
    "fault",
    [
        "weak",
        "reference_failed",
        "attack_passed",
        "missing",
        "duplicate",
        "stale_source",
        "no_error",
    ],
)
def test_batch_exit_failure_does_not_excuse_wrong_per_package_result(fault):
    data = valid_batch()
    if fault == "weak":
        data["fresh_replay_performed"] = False
    elif fault == "reference_failed":
        data["results"][0]["status"] = "REJECTED"
    elif fault == "attack_passed":
        data["results"][1]["status"] = "CURRENT_SOURCE_FRESH_REPLAY_MATCH"
    elif fault == "missing":
        data["results"].pop()
    elif fault == "duplicate":
        data["results"].append(data["results"][1])
    elif fault == "stale_source":
        data["results"][1]["error"] = "SOURCE_BINDING_MISMATCH"
    else:
        data["results"][1].pop("error")
    with pytest.raises(ValueError):
        m.check_cli_batch(data, "reference", {"corrected_memory": "attack"})
