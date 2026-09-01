"""Trusted artifact and claim gates for the seven Structure Two routes."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from itertools import product
from pathlib import Path

import pytest
from pydantic import ValidationError

from cpswm.system.attestation import AttestationAuthority
from cpswm.system.evaluation_operations.structure_two_artifact_verifier import (
    TrustedArtifactVerificationError,
    TrustedStructureTwoArtifactVerifier,
    cluster_bootstrap_effect,
)
from cpswm.system.evaluation_operations.structure_two_evidence_artifacts import (
    REQUIRED_FACTORIAL_INTERACTIONS,
    REQUIRED_MATCHED_BASELINES,
    ArtifactKind,
    ArtifactReference,
    BenefitCriterion,
    ClusteredEffectSample,
    ConfidenceIntervalMethod,
    ContaminationRecoveryPoint,
    CouplingEvidenceDeclaration,
    CouplingResultsPayload,
    CrossModuleCouplingKind,
    EffectEstimate,
    EffectSamplePayload,
    ExperimentalUnit,
    FactorialCellManifest,
    FactorialDesignDeclaration,
    FactorialDesignManifestPayload,
    FactorialResultsPayload,
    FactorialTermEstimate,
    FullRerunPayload,
    InterventionFactor,
    MatchedBaselineDeclaration,
    MatchedComparisonPayload,
    NoninterferencePayload,
    NumericalDowndatePayload,
    ParetoEvaluationPayload,
    PowerAnalysisPayload,
    SingleFactorInterventionProbe,
    StructureTwoEvidenceDeclaration,
    TuningCompletionPayload,
    TuningReportPayload,
    issue_artifact_envelope,
)
from cpswm.system.evaluation_operations.structure_two_technical_route_audit import (
    StructureTwoClaimGateEvaluator,
    StructureTwoRouteStatus,
    current_structure_two_route_statuses,
)

_NOW = datetime(2026, 8, 26, tzinfo=UTC)
_EXPERIMENT_ID = "structure-two-powered-d0-d1-2026-08-26"
_CANDIDATE = "structure-two-unified"
_PRIMARY_UTILITY = "cumulative_action_utility"


class _EvidenceBuilder:
    def __init__(self, root: Path, authority: AttestationAuthority) -> None:
        self.root = root
        self.authority = authority
        self.counter = 0

    def raw(self, name: str, payload: bytes) -> ArtifactReference:
        self.counter += 1
        path = self.root / f"{self.counter:03d}-{name}.bin"
        path.write_bytes(payload)
        return ArtifactReference(
            path=str(path.resolve()),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    def artifact(
        self,
        name: str,
        kind: ArtifactKind,
        payload,
    ) -> ArtifactReference:
        self.counter += 1
        envelope = issue_artifact_envelope(
            artifact_id=f"{name}-{self.counter}",
            experiment_id=_EXPERIMENT_ID,
            kind=kind,
            produced_at=_NOW,
            payload=payload,
            authority=self.authority,
        )
        path = self.root / f"{self.counter:03d}-{name}.json"
        path.write_text(envelope.model_dump_json(), encoding="utf-8")
        return ArtifactReference(
            path=str(path.resolve()),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            expected_kind=kind,
        )

    def effect(self, label: str, value: float) -> EffectEstimate:
        samples = EffectSamplePayload(
            primary_metric=_PRIMARY_UTILITY,
            independent_unit=ExperimentalUnit.SEED,
            samples=tuple(
                ClusteredEffectSample(
                    independent_unit_id=f"{label}-unit-{index}",
                    cluster_id=f"{label}-cluster-{index % 2}",
                    oriented_effect=value,
                )
                for index in range(4)
            ),
        )
        reference = self.artifact(label, ArtifactKind.EFFECT_SAMPLES, samples)
        point, low, high = cluster_bootstrap_effect(
            samples,
            confidence_level=0.95,
            seed=1701,
            resamples=1000,
        )
        return EffectEstimate(
            estimate=point,
            confidence_interval_low=low,
            confidence_interval_high=high,
            confidence_level=0.95,
            confidence_interval_method=ConfidenceIntervalMethod.CLUSTER_BOOTSTRAP,
            analysis_samples_artifact=reference,
            bootstrap_seed=1701,
            bootstrap_resamples=1000,
        )

    def factorial_effect(
        self,
        label: str,
        value: float,
        manifest: FactorialDesignManifestPayload,
    ) -> EffectEstimate:
        samples = EffectSamplePayload(
            primary_metric=_PRIMARY_UTILITY,
            independent_unit=manifest.independent_unit,
            samples=tuple(
                ClusteredEffectSample(
                    independent_unit_id=unit_id,
                    cluster_id=f"factorial-cluster-{index % 4}",
                    factorial_cell_id=cell.cell_id,
                    oriented_effect=value,
                )
                for index, cell in enumerate(manifest.cells)
                for unit_id in cell.independent_unit_ids
            ),
        )
        reference = self.artifact(label, ArtifactKind.EFFECT_SAMPLES, samples)
        point, low, high = cluster_bootstrap_effect(
            samples,
            confidence_level=0.95,
            seed=1701,
            resamples=1000,
        )
        return EffectEstimate(
            estimate=point,
            confidence_interval_low=low,
            confidence_interval_high=high,
            confidence_level=0.95,
            confidence_interval_method=ConfidenceIntervalMethod.CLUSTER_BOOTSTRAP,
            analysis_samples_artifact=reference,
            bootstrap_seed=1701,
            bootstrap_resamples=1000,
        )


def _factorial_manifest(power_hash: str) -> FactorialDesignManifestPayload:
    levels = {
        InterventionFactor.OBSERVATION_PROCESS: ("passive", "active_selection"),
        InterventionFactor.ACTOR_MIXTURE: ("owner_only", "visitor_present"),
        InterventionFactor.IDENTITY_ASSOCIATION: ("correct", "identity_swapped"),
        InterventionFactor.OWNER_HABIT_REGIME: ("stable", "habit_changed"),
        InterventionFactor.TRANSIENT_NOISE: ("low", "high"),
    }
    cells = []
    for index, combination in enumerate(
        product(*(levels[factor] for factor in InterventionFactor))
    ):
        unit_id = f"factorial-seed-{index}"
        cells.append(
            FactorialCellManifest(
                cell_id=f"cell-{index}",
                levels=dict(zip(InterventionFactor, combination, strict=True)),
                seed_ids=(unit_id,),
                household_ids=(f"household-{index}",),
                episode_ids=(f"episode-{index}",),
                independent_unit_ids=(unit_id,),
            )
        )
    interactions = tuple(
        tuple(sorted(term, key=lambda factor: factor.value))
        for term in sorted(
            REQUIRED_FACTORIAL_INTERACTIONS,
            key=lambda term: tuple(sorted(factor.value for factor in term)),
        )
    )
    return FactorialDesignManifestPayload(
        design_id="five-factor-full-factorial",
        factor_levels=levels,
        cells=tuple(cells),
        interaction_terms=interactions,
        independent_unit=ExperimentalUnit.SEED,
        power_analysis_artifact_sha256=power_hash,
    )


def _build_declaration(
    tmp_path: Path,
    authority: AttestationAuthority,
    *,
    negative_couplings: bool = False,
    full_rerun_equivalent: bool = True,
    baseline_input_mismatch: bool = False,
    tuning_test_access_count: int = 0,
) -> StructureTwoEvidenceDeclaration:
    builder = _EvidenceBuilder(tmp_path, authority)
    validation_split = builder.raw("validation-split", b"validation rows")
    test_split = builder.raw("sealed-test-split", b"held out test rows")
    tuning_budget = builder.raw("tuning-budget", b"24 trials and fixed compute")
    visible_input = builder.raw("visible-input", b"same visible history and candidates")
    mismatched_input = builder.raw("mismatched-input", b"different history")
    action_budget = builder.raw("action-budget", b"same action and token budget")

    baselines = []
    for index, baseline in enumerate(sorted(REQUIRED_MATCHED_BASELINES, key=str)):
        method_id = f"baseline:{baseline.value}"
        completion = builder.artifact(
            f"{baseline.value}-completion",
            ArtifactKind.TUNING_COMPLETION,
            TuningCompletionPayload(
                method_id=method_id,
                validation_split_artifact=validation_split,
                test_split_artifact=test_split,
                tuning_budget_artifact=tuning_budget,
                tuning_runs_completed=24,
                candidate_configuration_count=12,
                test_split_access_count=tuning_test_access_count if index == 0 else 0,
            ),
        )
        tuning = builder.artifact(
            f"{baseline.value}-tuning",
            ArtifactKind.TUNING_REPORT,
            TuningReportPayload(
                method_id=method_id,
                validation_split_artifact=validation_split,
                test_split_artifact=test_split,
                tuning_budget_artifact=tuning_budget,
                tuning_runs_completed=24,
                candidate_configuration_count=12,
                selected_hyperparameters={"threshold": 0.25, "seed": 17},
                test_split_access_count=tuning_test_access_count if index == 0 else 0,
                completion_receipt_artifact=completion,
            ),
        )
        comparison = builder.artifact(
            f"{baseline.value}-comparison",
            ArtifactKind.MATCHED_COMPARISON,
            MatchedComparisonPayload(
                candidate_method_id=_CANDIDATE,
                baseline_method_id=method_id,
                baseline_tuning_artifact_sha256=tuning.sha256,
                candidate_visible_input_artifact=visible_input,
                baseline_visible_input_artifact=(
                    mismatched_input if baseline_input_mismatch and index == 0 else visible_input
                ),
                candidate_budget_artifact=action_budget,
                baseline_budget_artifact=action_budget,
                primary_utility_metric=_PRIMARY_UTILITY,
                higher_is_better=True,
                candidate_metric_estimate=0.8,
                baseline_metric_estimate=0.6,
                oriented_candidate_minus_baseline=builder.effect(f"{baseline.value}-effect", 0.2),
                benefit_criterion=BenefitCriterion.SUPERIORITY,
                superiority_margin=0.0,
                non_inferiority_margin=0.0,
            ),
        )
        baselines.append(
            MatchedBaselineDeclaration(
                baseline=baseline,
                baseline_method_id=method_id,
                tuning_artifact=tuning,
                comparison_artifact=comparison,
            )
        )

    factorial_power = builder.artifact(
        "factorial-power",
        ArtifactKind.POWER_ANALYSIS,
        PowerAnalysisPayload(
            design_id="five-factor-full-factorial",
            primary_metric=_PRIMARY_UTILITY,
            alpha=0.05,
            target_power=0.8,
            minimum_detectable_effect=0.05,
            planned_independent_units=32,
            planned_clusters=4,
            independent_unit=ExperimentalUnit.SEED,
        ),
    )
    factorial_manifest_payload = _factorial_manifest(factorial_power.sha256)
    factorial_manifest = builder.artifact(
        "factorial-manifest",
        ArtifactKind.FACTORIAL_MANIFEST,
        factorial_manifest_payload,
    )
    factorial_results = builder.artifact(
        "factorial-results",
        ArtifactKind.FACTORIAL_RESULTS,
        FactorialResultsPayload(
            design_id="five-factor-full-factorial",
            design_manifest_artifact_sha256=factorial_manifest.sha256,
            power_analysis_artifact_sha256=factorial_power.sha256,
            primary_metric=_PRIMARY_UTILITY,
            term_estimates=tuple(
                FactorialTermEstimate(
                    factors=tuple(sorted(term, key=lambda factor: factor.value)),
                    effect=builder.factorial_effect(
                        "interaction-" + "-".join(sorted(factor.value for factor in term)),
                        0.2,
                        factorial_manifest_payload,
                    ),
                )
                for term in sorted(
                    REQUIRED_FACTORIAL_INTERACTIONS,
                    key=lambda item: tuple(sorted(factor.value for factor in item)),
                )
            ),
        ),
    )

    first_truth = builder.raw("sealed-truth-a", b"sealed evaluator truth A")
    second_truth = builder.raw("sealed-truth-b", b"sealed evaluator truth B")
    invariant_output = builder.raw("noninterference-output", b"identical prediction")
    noninterference = builder.artifact(
        "noninterference",
        ArtifactKind.NONINTERFERENCE,
        NoninterferencePayload(
            first_visible_input=visible_input,
            second_visible_input=visible_input,
            first_sealed_truth=first_truth,
            second_sealed_truth=second_truth,
            first_output=invariant_output,
            second_output=invariant_output,
            leakage_probe_names=("sealed_truth_counterfactual",),
        ),
    )

    full_rerun = builder.artifact(
        "full-rerun",
        ArtifactKind.FULL_RERUN,
        FullRerunPayload(
            method_id=_CANDIDATE,
            cached_projection={"owner": 0.7, "unknown": 0.3},
            rebuilt_projection=(
                {"owner": 0.7, "unknown": 0.3}
                if full_rerun_equivalent
                else {"owner": 0.6, "unknown": 0.4}
            ),
        ),
    )
    numerical = builder.artifact(
        "numerical-downdate",
        ArtifactKind.NUMERICAL_DOWNDATE,
        NumericalDowndatePayload(
            method_id=_CANDIDATE,
            direct_recompute=(0.2, 0.8),
            numerical_downdate=(0.2, 0.8),
            absolute_tolerance=1e-9,
            observed_condition_number=10.0,
            maximum_condition_number=100.0,
            replay_fallback_used=False,
        ),
    )
    pareto = builder.artifact(
        "pareto",
        ArtifactKind.PARETO_EVALUATION,
        ParetoEvaluationPayload(
            candidate_method_id=_CANDIDATE,
            points=(
                ContaminationRecoveryPoint(
                    method_id=_CANDIDATE,
                    owner_contamination=0.1,
                    recovery_latency=1.0,
                    revision_cost=1.0,
                    action_utility=0.8,
                    full_rerun_equivalent=full_rerun_equivalent,
                ),
                ContaminationRecoveryPoint(
                    method_id="full-replay-baseline",
                    owner_contamination=0.2,
                    recovery_latency=2.0,
                    revision_cost=2.0,
                    action_utility=0.7,
                    full_rerun_equivalent=True,
                ),
            ),
            full_rerun_artifact_sha256=full_rerun.sha256,
        ),
    )

    couplings = []
    for coupling in tuple(CrossModuleCouplingKind)[:3]:
        design_id = f"coupling:{coupling.value}"
        coupling_power = builder.artifact(
            f"{coupling.value}-power",
            ArtifactKind.POWER_ANALYSIS,
            PowerAnalysisPayload(
                design_id=design_id,
                primary_metric=_PRIMARY_UTILITY,
                alpha=0.05,
                target_power=0.8,
                minimum_detectable_effect=0.05,
                planned_independent_units=4,
                planned_clusters=2,
                independent_unit=ExperimentalUnit.SEED,
            ),
        )
        coupled_trace = builder.raw(f"{coupling.value}-coupled-trace", b"coupled action trace")
        decoupled_trace = builder.raw(
            f"{coupling.value}-decoupled-trace", b"decoupled action trace"
        )
        coupling_results = builder.artifact(
            f"{coupling.value}-results",
            ArtifactKind.COUPLING_RESULTS,
            CouplingResultsPayload(
                design_id=design_id,
                coupling=coupling,
                coupled_method_id=_CANDIDATE,
                decoupled_method_id=f"decoupled:{coupling.value}",
                candidate_visible_input_artifact=visible_input,
                baseline_visible_input_artifact=visible_input,
                candidate_budget_artifact=action_budget,
                baseline_budget_artifact=action_budget,
                coupled_action_trace_artifact=coupled_trace,
                decoupled_action_trace_artifact=decoupled_trace,
                primary_utility_metric=_PRIMARY_UTILITY,
                power_analysis_artifact_sha256=coupling_power.sha256,
                effect=builder.effect(
                    f"{coupling.value}-effect",
                    -0.2 if negative_couplings else 0.2,
                ),
                benefit_criterion=BenefitCriterion.SUPERIORITY,
                superiority_margin=0.0,
                non_inferiority_margin=0.0,
            ),
        )
        couplings.append(
            CouplingEvidenceDeclaration(
                coupling=coupling,
                power_analysis_artifact=coupling_power,
                results_artifact=coupling_results,
            )
        )

    return StructureTwoEvidenceDeclaration(
        candidate_method_id=_CANDIDATE,
        primary_utility_metric=_PRIMARY_UTILITY,
        baselines=tuple(baselines),
        factorial=FactorialDesignDeclaration(
            manifest_artifact=factorial_manifest,
            power_analysis_artifact=factorial_power,
            results_artifact=factorial_results,
        ),
        noninterference_artifact=noninterference,
        full_rerun_artifact=full_rerun,
        numerical_downdate_artifact=numerical,
        pareto_artifact=pareto,
        couplings=tuple(couplings),
    )


@pytest.fixture
def authority() -> AttestationAuthority:
    return AttestationAuthority(
        key_id="independent-structure-two-evaluator",
        secret=b"independent-structure-two-evaluator-key-0001",
    )


def test_signed_machine_readable_artifacts_pass_both_claim_gates(
    tmp_path: Path,
    authority: AttestationAuthority,
):
    declaration = _build_declaration(tmp_path, authority)
    verifier = TrustedStructureTwoArtifactVerifier(
        artifact_root=tmp_path,
        authority=authority,
    )
    verified = verifier.verify(declaration)
    decision = StructureTwoClaimGateEvaluator(authority=authority).evaluate(verified)

    assert len(verified.baselines) == len(REQUIRED_MATCHED_BASELINES)
    assert verified.factorial.cell_count == 32
    assert decision.causal_coupling_established
    assert decision.paper_benefit_claim_allowed


def test_hash_shaped_string_cannot_replace_real_artifact_bytes(
    tmp_path: Path,
    authority: AttestationAuthority,
):
    declaration = _build_declaration(tmp_path, authority)
    first = declaration.baselines[0]
    forged = declaration.model_copy(
        update={
            "baselines": (
                first.model_copy(
                    update={
                        "tuning_artifact": first.tuning_artifact.model_copy(
                            update={"sha256": "a" * 64}
                        )
                    }
                ),
                *declaration.baselines[1:],
            )
        }
    )
    verifier = TrustedStructureTwoArtifactVerifier(
        artifact_root=tmp_path,
        authority=authority,
    )
    with pytest.raises(TrustedArtifactVerificationError, match="byte hash mismatch"):
        verifier.verify(forged)


def test_artifacts_require_the_configured_independent_authority(
    tmp_path: Path,
    authority: AttestationAuthority,
):
    declaration = _build_declaration(tmp_path, authority)
    wrong_authority = AttestationAuthority(
        key_id="candidate-self-attestation",
        secret=b"candidate-self-attestation-key-material-0001",
    )
    verifier = TrustedStructureTwoArtifactVerifier(
        artifact_root=tmp_path,
        authority=wrong_authority,
    )
    with pytest.raises(TrustedArtifactVerificationError, match="not this authority"):
        verifier.verify(declaration)


def test_verified_bundle_cannot_be_mutated_after_attestation(
    tmp_path: Path,
    authority: AttestationAuthority,
):
    declaration = _build_declaration(tmp_path, authority)
    verifier = TrustedStructureTwoArtifactVerifier(
        artifact_root=tmp_path,
        authority=authority,
    )
    verified = verifier.verify(declaration)
    forged = verified.model_copy(update={"full_rerun_equivalent": False})
    with pytest.raises(ValueError, match="unauthentic verified bundle"):
        StructureTwoClaimGateEvaluator(authority=authority).evaluate(forged)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"tuning_test_access_count": 1}, "accessed the test split"),
        ({"baseline_input_mismatch": True}, "visible inputs differ"),
    ],
)
def test_independent_tuning_and_matched_input_budget_are_verified(
    tmp_path: Path,
    authority: AttestationAuthority,
    kwargs: dict[str, object],
    message: str,
):
    declaration = _build_declaration(tmp_path, authority, **kwargs)
    verifier = TrustedStructureTwoArtifactVerifier(
        artifact_root=tmp_path,
        authority=authority,
    )
    with pytest.raises(TrustedArtifactVerificationError, match=message):
        verifier.verify(declaration)


def test_five_ofat_probes_are_not_a_factorial_design(tmp_path: Path):
    valid = _factorial_manifest(hashlib.sha256(b"power").hexdigest())
    probes = tuple(
        SingleFactorInterventionProbe(
            factor=factor,
            reference_level="reference",
            intervention_level="changed",
            artifact=ArtifactReference(
                path=str((tmp_path / f"{factor.value}.json").resolve()),
                sha256=hashlib.sha256(factor.value.encode()).hexdigest(),
            ),
        )
        for factor in InterventionFactor
    )
    assert len(probes) == 5
    with pytest.raises(ValidationError, match="Cartesian cell"):
        FactorialDesignManifestPayload.model_validate(
            {**valid.model_dump(mode="python"), "cells": valid.cells[:5]}
        )


def test_factorial_design_requires_preregistered_interactions():
    valid = _factorial_manifest(hashlib.sha256(b"power").hexdigest())
    with pytest.raises(ValidationError, match="required interaction"):
        FactorialDesignManifestPayload.model_validate(
            {
                **valid.model_dump(mode="python"),
                "interaction_terms": valid.interaction_terms[:-1],
            }
        )


def test_significant_negative_couplings_establish_causality_not_benefit(
    tmp_path: Path,
    authority: AttestationAuthority,
):
    declaration = _build_declaration(tmp_path, authority, negative_couplings=True)
    verifier = TrustedStructureTwoArtifactVerifier(
        artifact_root=tmp_path,
        authority=authority,
    )
    verified = verifier.verify(declaration)
    decision = StructureTwoClaimGateEvaluator(authority=authority).evaluate(verified)

    assert all(item.causal_coupling_established for item in verified.couplings)
    assert not any(item.positive_benefit_established for item in verified.couplings)
    assert decision.causal_coupling_established
    assert not decision.paper_benefit_claim_allowed


def test_pareto_frontier_excludes_non_equivalent_candidate(
    tmp_path: Path,
    authority: AttestationAuthority,
):
    declaration = _build_declaration(
        tmp_path,
        authority,
        full_rerun_equivalent=False,
    )
    verifier = TrustedStructureTwoArtifactVerifier(
        artifact_root=tmp_path,
        authority=authority,
    )
    verified = verifier.verify(declaration)
    decision = StructureTwoClaimGateEvaluator(authority=authority).evaluate(verified)

    assert not verified.full_rerun_equivalent
    assert not verified.candidate_on_valid_pareto_frontier
    assert not decision.paper_benefit_claim_allowed


def test_route_status_cannot_self_declare_innovation():
    status = current_structure_two_route_statuses()[0]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        StructureTwoRouteStatus.model_validate(
            {**status.model_dump(mode="python"), "paper_innovation_established": True}
        )
