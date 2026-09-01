"""Cross-structure preregistration and falsification decision tests."""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from cpswm.system.attestation import AttestationAuthority, Ed25519AttestationSigner
from cpswm.system.evaluation_operations.method_falsification import (
    BaselineFidelity,
    FalsificationDecision,
    MethodEvidenceSubmission,
    MethodFalsificationSpec,
    OpponentComparisonEvidence,
    OpponentRequirement,
    OrientedEffectInterval,
    ResearchScope,
    attest_method_evidence_submission,
    current_method_falsification_registry,
    evaluate_registry,
)
from cpswm.system.evaluation_operations.method_falsification import (
    evaluate_method_submission as _evaluate_method_submission,
)

SIGNER = Ed25519AttestationSigner.generate(key_id="method-evidence-test")
AUTHORITY = SIGNER.verifier()


def evaluate_method_submission(spec, submission):  # type: ignore[no-untyped-def]
    return _evaluate_method_submission(spec, submission, authority=AUTHORITY)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _effect(low: float, estimate: float, high: float) -> OrientedEffectInterval:
    return OrientedEffectInterval(
        estimate=estimate,
        confidence_interval_low=low,
        confidence_interval_high=high,
        confidence_level=0.95,
    )


def _submission(
    spec: MethodFalsificationSpec,
    *,
    primary: OrientedEffectInterval,
    mechanism: OrientedEffectInterval,
    fidelity: BaselineFidelity = BaselineFidelity.INDEPENDENTLY_TUNED_MATCHED,
    scenarios: tuple[str, ...] | None = None,
    external: bool = False,
) -> MethodEvidenceSubmission:
    comparisons = tuple(
        OpponentComparisonEvidence(
            opponent_id=requirement.opponent_id,
            fidelity=fidelity,
            independently_tuned=True,
            same_visible_input=True,
            same_action_budget=True,
            primary_action_effect=primary,
            mechanism_effect=mechanism,
        )
        for requirement in spec.strongest_opponents
    )
    unsigned = MethodEvidenceSubmission(
        method_id=spec.method_id,
        preregistration_sha256=spec.preregistration_sha256,
        validation_split_sha256=_sha("validation"),
        sealed_test_split_sha256=_sha("sealed-test"),
        shared_visible_input_sha256=_sha("visible-input"),
        shared_action_budget_sha256=_sha("action-budget"),
        power_analysis_sha256=_sha("power-analysis"),
        covered_scenario_families=scenarios or spec.frozen_scenario_families,
        independent_unit_count=64,
        cluster_axis=spec.cluster_axis,
        comparisons=comparisons,
        external_validity_artifact_sha256=_sha("external") if external else None,
    )
    return attest_method_evidence_submission(unsigned, authority=SIGNER)


def test_registry_covers_all_scopes_and_freezes_eighteen_methods() -> None:
    registry = current_method_falsification_registry()

    assert len(registry.methods) == 18
    assert {item.scope for item in registry.methods} == set(ResearchScope)
    assert len(registry.registry_sha256) == 64
    assert all(len(item.frozen_scenario_families) >= 2 for item in registry.methods)
    assert all(item.strongest_opponents for item in registry.methods)
    assert all(item.primary_action_metric for item in registry.methods)
    assert all(item.mechanism_metric for item in registry.methods)


def test_reduced_skill_proxy_cannot_be_registered_as_strongest_opponent() -> None:
    with pytest.raises(ValidationError, match="reduced-skill proxy"):
        OpponentRequirement(
            opponent_id="famous-name-proxy",
            accepted_fidelities=(BaselineFidelity.REDUCED_SKILL_PROXY,),
        )


def test_empty_current_audit_blocks_every_method_without_promoting_capability() -> None:
    registry = current_method_falsification_registry()
    audit = evaluate_registry(registry)

    assert len(audit.results) == 18
    assert set(audit.decision_counts) == set(FalsificationDecision)
    assert audit.decision_counts[FalsificationDecision.BLOCKED] == 18
    assert all(result.blockers == ("missing_evidence_submission",) for result in audit.results)
    assert not any(result.paper_claim_allowed for result in audit.results)


def test_clearly_worse_action_result_falsifies_the_registered_claim() -> None:
    spec = current_method_falsification_registry().by_id("s2.orrer")
    submission = _submission(
        spec,
        primary=_effect(-0.30, -0.20, -0.10),
        mechanism=_effect(0.10, 0.20, 0.30),
    )

    result = evaluate_method_submission(spec, submission)

    assert result.decision is FalsificationDecision.FALSIFIED
    assert set(result.failed_opponents) == {
        "damen_hogg_amg_matched_open_world",
        "fixed_lag_smoother",
    }
    assert not result.paper_claim_allowed


def test_no_positive_mechanism_benefit_falsifies_even_when_action_is_noninferior() -> None:
    spec = current_method_falsification_registry().by_id("s1.leave_one_out_layered_habit")
    submission = _submission(
        spec,
        primary=_effect(0.00, 0.05, 0.10),
        mechanism=_effect(-0.10, -0.05, 0.00),
    )

    result = evaluate_method_submission(spec, submission)

    assert result.decision is FalsificationDecision.FALSIFIED
    assert not result.paper_claim_allowed


def test_interval_crossing_the_frozen_boundary_is_inconclusive_not_a_pass() -> None:
    spec = current_method_falsification_registry().by_id("s2.ciav")
    submission = _submission(
        spec,
        primary=_effect(-0.05, 0.01, 0.08),
        mechanism=_effect(-0.02, 0.04, 0.10),
    )

    result = evaluate_method_submission(spec, submission)

    assert result.decision is FalsificationDecision.INCONCLUSIVE
    assert result.inconclusive_opponents
    assert not result.paper_claim_allowed


def test_only_action_noninferiority_plus_mechanism_superiority_survives() -> None:
    spec = current_method_falsification_registry().by_id("s2.rgrc")
    submission = _submission(
        spec,
        primary=_effect(0.00, 0.05, 0.10),
        mechanism=_effect(0.01, 0.08, 0.15),
    )

    result = evaluate_method_submission(spec, submission)

    assert result.decision is FalsificationDecision.SURVIVED
    assert set(result.survived_opponents) == {
        "full_history_rerun",
        "fisher_replay_consolidation",
    }
    assert result.paper_claim_allowed


def test_proxy_fidelity_and_missing_scenario_block_decision_before_statistics() -> None:
    spec = current_method_falsification_registry().by_id("s3.multi_parse_posterior")
    submission = _submission(
        spec,
        primary=_effect(0.01, 0.05, 0.10),
        mechanism=_effect(0.01, 0.05, 0.10),
        fidelity=BaselineFidelity.MATCHED_REPLAY_ADAPTER,
        scenarios=(spec.frozen_scenario_families[0],),
    )

    result = evaluate_method_submission(spec, submission)

    assert result.decision is FalsificationDecision.BLOCKED
    assert any(item.startswith("missing_scenario:") for item in result.blockers)
    assert any(item.startswith("insufficient_fidelity:") for item in result.blockers)


def test_external_methods_require_faithful_systems_and_external_validity() -> None:
    spec = current_method_falsification_registry().by_id("oam_phm.full_loop")
    blocked = _submission(
        spec,
        primary=_effect(0.01, 0.05, 0.10),
        mechanism=_effect(0.01, 0.05, 0.10),
        fidelity=BaselineFidelity.INDEPENDENTLY_TUNED_MATCHED,
    )

    blocked_result = evaluate_method_submission(spec, blocked)

    assert blocked_result.decision is FalsificationDecision.BLOCKED
    assert "missing_external_validity_artifact" in blocked_result.blockers
    assert any(item.startswith("insufficient_fidelity:") for item in blocked_result.blockers)

    faithful = _submission(
        spec,
        primary=_effect(0.00, 0.05, 0.10),
        mechanism=_effect(0.01, 0.05, 0.10),
        fidelity=BaselineFidelity.FAITHFUL_EXTERNAL,
        external=True,
    )
    faithful_result = evaluate_method_submission(spec, faithful)
    assert faithful_result.decision is FalsificationDecision.SURVIVED


def test_preregistration_hash_change_rejects_post_result_redefinition() -> None:
    spec = current_method_falsification_registry().by_id("s3.coverage_derived_unknown_mass")
    submission = _submission(
        spec,
        primary=_effect(0.00, 0.05, 0.10),
        mechanism=_effect(0.01, 0.05, 0.10),
    )
    tampered = submission.model_copy(update={"preregistration_sha256": _sha("tampered")})

    with pytest.raises(ValueError, match="different preregistration"):
        evaluate_method_submission(spec, tampered)


def test_validation_and_test_split_cannot_be_the_same() -> None:
    spec = current_method_falsification_registry().by_id("s2.cf_bocpd")
    submission = _submission(
        spec,
        primary=_effect(0.00, 0.05, 0.10),
        mechanism=_effect(0.01, 0.05, 0.10),
    )

    payload = submission.model_dump(mode="python")
    payload["sealed_test_split_sha256"] = submission.validation_split_sha256

    with pytest.raises(ValidationError, match="must differ"):
        MethodEvidenceSubmission.model_validate(payload)


def test_pretty_but_unsigned_submission_cannot_unlock_a_paper_claim() -> None:
    spec = current_method_falsification_registry().by_id("s2.rgrc")
    signed = _submission(
        spec,
        primary=_effect(0.00, 0.05, 0.10),
        mechanism=_effect(0.01, 0.08, 0.15),
    )
    unsigned = signed.model_copy(update={"attestation": None})

    result = _evaluate_method_submission(spec, unsigned, authority=AUTHORITY)

    assert result.decision is FalsificationDecision.BLOCKED
    assert result.blockers == ("unverified_evidence_submission",)
    assert not result.paper_claim_allowed


def test_hmac_verifier_is_development_only_and_cannot_unlock_formal_claim() -> None:
    spec = current_method_falsification_registry().by_id("s2.rgrc")
    submission = _submission(
        spec,
        primary=_effect(0.00, 0.05, 0.10),
        mechanism=_effect(0.01, 0.08, 0.15),
    )
    hmac_verifier = AttestationAuthority(key_id="legacy", secret=b"l" * 32)

    result = _evaluate_method_submission(spec, submission, authority=hmac_verifier)

    assert result.decision is FalsificationDecision.BLOCKED
    assert result.blockers == ("missing_formal_public_key_verifier",)
