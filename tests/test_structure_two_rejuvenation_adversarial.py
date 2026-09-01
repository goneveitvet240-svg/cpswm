from __future__ import annotations

import json
from dataclasses import replace

import pytest

from cpswm.system.evaluation_operations.structure_two_particle_falsifier import (
    ActorPath,
    Cause,
    Identity,
    LatentState,
    Mechanism,
    Regime,
    registered_scenarios,
)
from cpswm.system.evaluation_operations.structure_two_rejuvenation_gate import (
    RejuvenationMethod,
    run_structured_rejuvenation_gate,
    structured_joint_pool,
    verify_structured_rejuvenation_report,
    write_structured_rejuvenation_report,
)
from cpswm.system.reproducibility import content_sha256


def test_joint_pool_does_not_consume_registered_truth() -> None:
    scenario = registered_scenarios()[-1]
    adversarial_truth = LatentState(
        mechanism=Mechanism.DIRECT,
        actor_path=ActorPath.OWNER_OWNER,
        identity=Identity.DECOY,
        cause=Cause.NOISE,
        regime=Regime.OLD,
    )

    original = structured_joint_pool(scenario, budget=24)
    permuted = structured_joint_pool(replace(scenario, truth=adversarial_truth), budget=24)

    assert tuple(state.key for state in original.states) == tuple(
        state.key for state in permuted.states
    )
    assert original.parent_by_key == permuted.parent_by_key
    assert original.families_by_key == permuted.families_by_key


def test_candidate_accounting_includes_final_weight_evaluations() -> None:
    report = run_structured_rejuvenation_gate(particle_budget=24)
    summaries = report["method_summaries"]

    assert summaries[RejuvenationMethod.SINGLE_FIELD.value][
        "mean_candidate_evaluations"
    ] == pytest.approx(526.625)
    assert summaries[RejuvenationMethod.STRUCTURED_JOINT.value][
        "mean_candidate_evaluations"
    ] == pytest.approx(533.9375)
    assert report["cost_metric_status"].startswith("analytic_state_score_evaluations_only")


def test_protocol_rejects_budget_substitution() -> None:
    for substituted_budget in (12, 16, 23, 25, 48):
        with pytest.raises(ValueError, match="freezes particle_budget=24"):
            run_structured_rejuvenation_gate(particle_budget=substituted_budget)


def test_action_readout_limitation_is_explicit() -> None:
    report = run_structured_rejuvenation_gate(particle_budget=24)
    left = LatentState(
        mechanism=Mechanism.DIRECT,
        actor_path=ActorPath.OWNER_OWNER,
        identity=Identity.TARGET,
        cause=Cause.OBSERVATION,
        regime=Regime.NEW,
    )
    right = LatentState(
        mechanism=Mechanism.HANDOFF,
        actor_path=ActorPath.UNKNOWN_OWNER,
        identity=Identity.DECOY,
        cause=Cause.HABIT,
        regime=Regime.NEW,
    )

    assert left.action_location is right.action_location
    assert report["action_readout_status"].startswith("regime_only")


def test_verifier_rejects_metric_tampering_even_with_recomputed_content_hash(tmp_path) -> None:
    path = tmp_path / "report.json"
    report = run_structured_rejuvenation_gate(particle_budget=24)
    write_structured_rejuvenation_report(report, path)
    assert verify_structured_rejuvenation_report(path) == report

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["method_summaries"][RejuvenationMethod.STRUCTURED_JOINT.value][
        "truth_support_rate"
    ] = 1.0
    unsigned = dict(tampered)
    unsigned.pop("content_sha256")
    tampered["content_sha256"] = content_sha256(unsigned)
    path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(ValueError, match="deterministic recomputation"):
        verify_structured_rejuvenation_report(path)


def test_verifier_rejects_provenance_tampering_with_recomputed_content_hash(tmp_path) -> None:
    path = tmp_path / "report.json"
    report = run_structured_rejuvenation_gate(particle_budget=24)
    report["provenance"]["gate_source_sha256"] = "0" * 64
    unsigned = dict(report)
    unsigned.pop("content_sha256")
    report["content_sha256"] = content_sha256(unsigned)
    path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="deterministic recomputation"):
        verify_structured_rejuvenation_report(path)
