"""Trusted verification of Structure Two evidence artifacts.

The verifier opens every referenced file, recomputes its byte hash, validates a
typed machine-readable payload, verifies an authority attestation, and derives
all pass/fail facts.  The claim evaluator accepts only the verifier-signed
bundle emitted here, never declarative receipts directly.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from math import isclose
from pathlib import Path
from random import Random
from statistics import fmean
from typing import TypeVar

from pydantic import Field, model_validator

from cpswm.contracts.base import ContractModel
from cpswm.system.attestation import (
    Attestation,
    AttestationAuthority,
    AttestationError,
    attested_payload,
)

from .structure_two_evidence_artifacts import (
    DOMAIN_STRUCTURE_TWO_ARTIFACT,
    DOMAIN_STRUCTURE_TWO_VERIFIED_BUNDLE,
    REQUIRED_FACTORIAL_INTERACTIONS,
    ArtifactEnvelope,
    ArtifactKind,
    ArtifactReference,
    BenefitCriterion,
    ConfidenceIntervalMethod,
    ContaminationRecoveryPoint,
    CouplingEvidenceDeclaration,
    CouplingResultsPayload,
    CrossModuleCouplingKind,
    EffectEstimate,
    EffectSamplePayload,
    FactorialDesignDeclaration,
    FactorialDesignManifestPayload,
    FactorialResultsPayload,
    FullRerunPayload,
    MatchedBaselineDeclaration,
    MatchedBaselineKind,
    MatchedComparisonPayload,
    NoninterferencePayload,
    NumericalDowndatePayload,
    ParetoEvaluationPayload,
    PowerAnalysisPayload,
    StructureTwoEvidenceDeclaration,
    TuningCompletionPayload,
    TuningReportPayload,
)

PayloadT = TypeVar("PayloadT", bound=ContractModel)


class TrustedArtifactVerificationError(ValueError):
    """Raised when evidence bytes, schemas, links, or attestations fail closed."""


class VerifiedBaselineEvidence(ContractModel):
    baseline: MatchedBaselineKind
    baseline_method_id: str
    tuning_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    comparison_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tuning_runs_completed: int = Field(gt=0)
    independent_unit_count: int = Field(gt=0)
    cluster_count: int = Field(ge=2)
    oriented_effect: float
    confidence_interval_low: float
    confidence_interval_high: float
    benefit_criterion: BenefitCriterion
    benefit_claim_passed: bool


class VerifiedFactorialEvidence(ContractModel):
    design_id: str
    manifest_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    power_analysis_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    results_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cell_count: int = Field(gt=1)
    fitted_interactions: tuple[tuple[str, ...], ...]
    powered_factorial_established: bool


class VerifiedCouplingEvidence(ContractModel):
    coupling: CrossModuleCouplingKind
    power_analysis_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    results_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    oriented_utility_effect: float
    confidence_interval_low: float
    confidence_interval_high: float
    causal_coupling_established: bool
    positive_benefit_established: bool


class VerifiedStructureTwoEvidenceBundle(ContractModel):
    """Verifier-derived facts, signed so caller-side mutation is rejected."""

    experiment_id: str = Field(min_length=1)
    candidate_method_id: str = Field(min_length=1)
    primary_utility_metric: str = Field(min_length=1)
    baselines: tuple[VerifiedBaselineEvidence, ...]
    factorial: VerifiedFactorialEvidence
    couplings: tuple[VerifiedCouplingEvidence, ...]
    noninterference_passed: bool
    full_rerun_equivalent: bool
    numerical_downdate_stable: bool
    candidate_on_valid_pareto_frontier: bool
    verified_artifact_sha256s: tuple[str, ...] = Field(min_length=1)
    attestation: Attestation | None = None

    @model_validator(mode="after")
    def unique_verified_evidence(self) -> VerifiedStructureTwoEvidenceBundle:
        baselines = [item.baseline for item in self.baselines]
        couplings = [item.coupling for item in self.couplings]
        if len(baselines) != len(set(baselines)):
            raise ValueError("verified baselines must be unique")
        if len(couplings) != len(set(couplings)):
            raise ValueError("verified couplings must be unique")
        if len(self.verified_artifact_sha256s) != len(set(self.verified_artifact_sha256s)):
            raise ValueError("verified artifact hashes must be unique")
        return self


def _quantile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("quantile requires values")
    position = probability * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def cluster_bootstrap_effect(
    samples: EffectSamplePayload,
    *,
    confidence_level: float,
    seed: int,
    resamples: int,
) -> tuple[float, float, float]:
    """Deterministically recompute the mean and cluster-bootstrap interval."""

    grouped: dict[str, list[float]] = defaultdict(list)
    for sample in samples.samples:
        grouped[sample.cluster_id].append(sample.oriented_effect)
    clusters = sorted(grouped)
    generator = Random(seed)
    bootstrap_estimates: list[float] = []
    for _ in range(resamples):
        selected = [generator.choice(clusters) for _ in clusters]
        values = [value for cluster in selected for value in grouped[cluster]]
        bootstrap_estimates.append(fmean(values))
    bootstrap_estimates.sort()
    tail = (1.0 - confidence_level) / 2.0
    point = fmean(sample.oriented_effect for sample in samples.samples)
    return (
        point,
        _quantile(bootstrap_estimates, tail),
        _quantile(bootstrap_estimates, 1.0 - tail),
    )


def contamination_recovery_pareto_frontier(
    points: tuple[ContaminationRecoveryPoint, ...],
) -> tuple[ContaminationRecoveryPoint, ...]:
    """Compute the frontier only over methods eligible by full-rerun equivalence."""

    eligible = tuple(point for point in points if point.full_rerun_equivalent)
    if not eligible:
        raise TrustedArtifactVerificationError(
            "Pareto frontier has no full-rerun-equivalent method"
        )

    def dominates(left: ContaminationRecoveryPoint, right: ContaminationRecoveryPoint) -> bool:
        no_worse = (
            left.owner_contamination <= right.owner_contamination
            and left.recovery_latency <= right.recovery_latency
            and left.revision_cost <= right.revision_cost
            and left.action_utility >= right.action_utility
        )
        strict = (
            left.owner_contamination < right.owner_contamination
            or left.recovery_latency < right.recovery_latency
            or left.revision_cost < right.revision_cost
            or left.action_utility > right.action_utility
        )
        return no_worse and strict

    return tuple(
        point
        for point in eligible
        if not any(other is not point and dominates(other, point) for other in eligible)
    )


class TrustedStructureTwoArtifactVerifier:
    """Verify an untrusted declaration against files and an independent authority."""

    def __init__(self, *, artifact_root: Path, authority: AttestationAuthority) -> None:
        self._root = artifact_root.resolve()
        self._authority = authority
        self._verified_hashes: set[str] = set()
        self._experiment_ids: set[str] = set()

    def verify(
        self,
        declaration: StructureTwoEvidenceDeclaration,
    ) -> VerifiedStructureTwoEvidenceBundle:
        self._verified_hashes = set()
        self._experiment_ids = set()
        baselines = tuple(
            self._verify_baseline(item, declaration) for item in declaration.baselines
        )
        factorial = self._verify_factorial(declaration.factorial, declaration)
        couplings = tuple(
            self._verify_coupling(item, declaration) for item in declaration.couplings
        )
        noninterference = self._verify_noninterference(declaration.noninterference_artifact)
        full_rerun, full_rerun_sha = self._verify_full_rerun(
            declaration.full_rerun_artifact,
            declaration.candidate_method_id,
        )
        numerical = self._verify_numerical_downdate(
            declaration.numerical_downdate_artifact,
            declaration.candidate_method_id,
        )
        pareto = self._verify_pareto(
            declaration.pareto_artifact,
            declaration.candidate_method_id,
            full_rerun_sha,
            full_rerun,
        )
        if len(self._experiment_ids) != 1:
            raise TrustedArtifactVerificationError(
                "all Structure Two evidence must belong to one experiment"
            )
        unsigned = VerifiedStructureTwoEvidenceBundle(
            experiment_id=next(iter(self._experiment_ids)),
            candidate_method_id=declaration.candidate_method_id,
            primary_utility_metric=declaration.primary_utility_metric,
            baselines=baselines,
            factorial=factorial,
            couplings=couplings,
            noninterference_passed=noninterference,
            full_rerun_equivalent=full_rerun,
            numerical_downdate_stable=numerical,
            candidate_on_valid_pareto_frontier=pareto,
            verified_artifact_sha256s=tuple(sorted(self._verified_hashes)),
        )
        signature = self._authority.sign(
            DOMAIN_STRUCTURE_TWO_VERIFIED_BUNDLE,
            attested_payload(unsigned),
        )
        return unsigned.model_copy(update={"attestation": signature})

    def verify_bundle_attestation(self, bundle: VerifiedStructureTwoEvidenceBundle) -> None:
        try:
            self._authority.verify(
                DOMAIN_STRUCTURE_TWO_VERIFIED_BUNDLE,
                attested_payload(bundle),
                bundle.attestation,
            )
        except AttestationError as error:
            raise TrustedArtifactVerificationError(str(error)) from error

    def _resolve(self, reference: ArtifactReference) -> Path:
        path = Path(reference.path)
        if not path.is_absolute():
            raise TrustedArtifactVerificationError("artifact path must be absolute")
        resolved = path.resolve()
        if not resolved.is_relative_to(self._root):
            raise TrustedArtifactVerificationError("artifact path escapes trusted root")
        if not resolved.is_file():
            raise TrustedArtifactVerificationError(f"artifact does not exist: {resolved}")
        return resolved

    def _read_bytes(self, reference: ArtifactReference) -> bytes:
        raw = self._resolve(reference).read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != reference.sha256:
            raise TrustedArtifactVerificationError("artifact byte hash mismatch")
        self._verified_hashes.add(actual)
        return raw

    def _load(
        self,
        reference: ArtifactReference,
        *,
        kind: ArtifactKind,
        payload_type: type[PayloadT],
    ) -> tuple[PayloadT, ArtifactEnvelope]:
        raw = self._read_bytes(reference)
        try:
            envelope = ArtifactEnvelope.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as error:
            raise TrustedArtifactVerificationError("artifact envelope is invalid") from error
        if envelope.kind is not kind:
            raise TrustedArtifactVerificationError(
                f"expected {kind.value} artifact, received {envelope.kind.value}"
            )
        if reference.expected_kind is not None and reference.expected_kind is not envelope.kind:
            raise TrustedArtifactVerificationError("declaration expected_kind does not match file")
        try:
            self._authority.verify(
                DOMAIN_STRUCTURE_TWO_ARTIFACT,
                attested_payload(envelope),
                envelope.attestation,
            )
        except AttestationError as error:
            raise TrustedArtifactVerificationError(str(error)) from error
        if envelope.payload_schema != payload_type.__name__:
            raise TrustedArtifactVerificationError(
                "artifact payload schema is not the expected type"
            )
        try:
            payload = payload_type.model_validate(envelope.payload)
        except ValueError as error:
            raise TrustedArtifactVerificationError(
                "artifact payload failed typed validation"
            ) from error
        self._experiment_ids.add(envelope.experiment_id)
        return payload, envelope

    def _verify_effect(
        self,
        effect: EffectEstimate,
        *,
        primary_metric: str,
    ) -> tuple[EffectSamplePayload, float, float, float]:
        if effect.confidence_interval_method is not ConfidenceIntervalMethod.CLUSTER_BOOTSTRAP:
            raise TrustedArtifactVerificationError(
                "claim gate currently requires reproducible cluster-bootstrap intervals"
            )
        samples, _envelope = self._load(
            effect.analysis_samples_artifact,
            kind=ArtifactKind.EFFECT_SAMPLES,
            payload_type=EffectSamplePayload,
        )
        if samples.primary_metric != primary_metric:
            raise TrustedArtifactVerificationError("effect samples use a different primary metric")
        point, low, high = cluster_bootstrap_effect(
            samples,
            confidence_level=effect.confidence_level,
            seed=effect.bootstrap_seed,
            resamples=effect.bootstrap_resamples,
        )
        expected = (
            effect.estimate,
            effect.confidence_interval_low,
            effect.confidence_interval_high,
        )
        recomputed = (point, low, high)
        if any(
            not isclose(left, right, rel_tol=0.0, abs_tol=1e-12)
            for left, right in zip(expected, recomputed, strict=True)
        ):
            raise TrustedArtifactVerificationError(
                "effect estimate or confidence interval does not reproduce from samples"
            )
        return samples, point, low, high

    @staticmethod
    def _benefit_passed(
        *,
        criterion: BenefitCriterion,
        estimate: float,
        low: float,
        superiority_margin: float,
        non_inferiority_margin: float,
    ) -> bool:
        if criterion is BenefitCriterion.SUPERIORITY:
            return low > superiority_margin
        return estimate >= 0.0 and low >= -non_inferiority_margin

    def _verify_baseline(
        self,
        declaration: MatchedBaselineDeclaration,
        complete: StructureTwoEvidenceDeclaration,
    ) -> VerifiedBaselineEvidence:
        tuning, _tuning_envelope = self._load(
            declaration.tuning_artifact,
            kind=ArtifactKind.TUNING_REPORT,
            payload_type=TuningReportPayload,
        )
        comparison, _comparison_envelope = self._load(
            declaration.comparison_artifact,
            kind=ArtifactKind.MATCHED_COMPARISON,
            payload_type=MatchedComparisonPayload,
        )
        completion, _completion_envelope = self._load(
            tuning.completion_receipt_artifact,
            kind=ArtifactKind.TUNING_COMPLETION,
            payload_type=TuningCompletionPayload,
        )
        if tuning.method_id != declaration.baseline_method_id:
            raise TrustedArtifactVerificationError("tuning report method does not match baseline")
        tuning_facts = (
            tuning.method_id,
            tuning.validation_split_artifact,
            tuning.test_split_artifact,
            tuning.tuning_budget_artifact,
            tuning.tuning_runs_completed,
            tuning.candidate_configuration_count,
            tuning.test_split_access_count,
        )
        completion_facts = (
            completion.method_id,
            completion.validation_split_artifact,
            completion.test_split_artifact,
            completion.tuning_budget_artifact,
            completion.tuning_runs_completed,
            completion.candidate_configuration_count,
            completion.test_split_access_count,
        )
        if tuning_facts != completion_facts:
            raise TrustedArtifactVerificationError(
                "tuning report does not reproduce its completion receipt"
            )
        for referenced_bytes in (
            tuning.validation_split_artifact,
            tuning.test_split_artifact,
            tuning.tuning_budget_artifact,
        ):
            self._read_bytes(referenced_bytes)
        if tuning.test_split_access_count != 0:
            raise TrustedArtifactVerificationError("baseline tuning accessed the test split")
        if tuning.validation_split_artifact.sha256 == tuning.test_split_artifact.sha256:
            raise TrustedArtifactVerificationError("validation and test split identities collide")
        if comparison.baseline_method_id != declaration.baseline_method_id:
            raise TrustedArtifactVerificationError("comparison baseline method mismatch")
        if comparison.candidate_method_id != complete.candidate_method_id:
            raise TrustedArtifactVerificationError("comparison candidate method mismatch")
        if comparison.baseline_tuning_artifact_sha256 != declaration.tuning_artifact.sha256:
            raise TrustedArtifactVerificationError("comparison is not bound to the tuning artifact")
        if comparison.primary_utility_metric != complete.primary_utility_metric:
            raise TrustedArtifactVerificationError("baseline comparison changed primary utility")
        for referenced_bytes in (
            comparison.candidate_visible_input_artifact,
            comparison.baseline_visible_input_artifact,
            comparison.candidate_budget_artifact,
            comparison.baseline_budget_artifact,
        ):
            self._read_bytes(referenced_bytes)
        if (
            comparison.candidate_visible_input_artifact.sha256
            != comparison.baseline_visible_input_artifact.sha256
        ):
            raise TrustedArtifactVerificationError("candidate and baseline visible inputs differ")
        if (
            comparison.candidate_budget_artifact.sha256
            != comparison.baseline_budget_artifact.sha256
        ):
            raise TrustedArtifactVerificationError("candidate and baseline budgets differ")
        samples, point, low, high = self._verify_effect(
            comparison.oriented_candidate_minus_baseline,
            primary_metric=comparison.primary_utility_metric,
        )
        raw_difference = comparison.candidate_metric_estimate - comparison.baseline_metric_estimate
        oriented = raw_difference if comparison.higher_is_better else -raw_difference
        if not isclose(oriented, point, rel_tol=0.0, abs_tol=1e-12):
            raise TrustedArtifactVerificationError(
                "matched effect does not equal the oriented candidate-baseline difference"
            )
        return VerifiedBaselineEvidence(
            baseline=declaration.baseline,
            baseline_method_id=declaration.baseline_method_id,
            tuning_artifact_sha256=declaration.tuning_artifact.sha256,
            comparison_artifact_sha256=declaration.comparison_artifact.sha256,
            tuning_runs_completed=tuning.tuning_runs_completed,
            independent_unit_count=len(samples.samples),
            cluster_count=len({sample.cluster_id for sample in samples.samples}),
            oriented_effect=point,
            confidence_interval_low=low,
            confidence_interval_high=high,
            benefit_criterion=comparison.benefit_criterion,
            benefit_claim_passed=self._benefit_passed(
                criterion=comparison.benefit_criterion,
                estimate=point,
                low=low,
                superiority_margin=comparison.superiority_margin,
                non_inferiority_margin=comparison.non_inferiority_margin,
            ),
        )

    def _verify_powered_effect(
        self,
        effect: EffectEstimate,
        power: PowerAnalysisPayload,
        *,
        primary_metric: str,
    ) -> tuple[EffectSamplePayload, float, float, float]:
        samples, point, low, high = self._verify_effect(
            effect,
            primary_metric=primary_metric,
        )
        unit_count = len(samples.samples)
        cluster_count = len({sample.cluster_id for sample in samples.samples})
        if samples.independent_unit is not power.independent_unit:
            raise TrustedArtifactVerificationError("power analysis uses another experimental unit")
        if unit_count < power.planned_independent_units:
            raise TrustedArtifactVerificationError("observed sample is below powered unit target")
        if cluster_count < power.planned_clusters:
            raise TrustedArtifactVerificationError("observed clusters are below power target")
        return samples, point, low, high

    def _verify_factorial(
        self,
        declaration: FactorialDesignDeclaration,
        complete: StructureTwoEvidenceDeclaration,
    ) -> VerifiedFactorialEvidence:
        manifest, _manifest_envelope = self._load(
            declaration.manifest_artifact,
            kind=ArtifactKind.FACTORIAL_MANIFEST,
            payload_type=FactorialDesignManifestPayload,
        )
        power, _power_envelope = self._load(
            declaration.power_analysis_artifact,
            kind=ArtifactKind.POWER_ANALYSIS,
            payload_type=PowerAnalysisPayload,
        )
        results, _results_envelope = self._load(
            declaration.results_artifact,
            kind=ArtifactKind.FACTORIAL_RESULTS,
            payload_type=FactorialResultsPayload,
        )
        if manifest.power_analysis_artifact_sha256 != declaration.power_analysis_artifact.sha256:
            raise TrustedArtifactVerificationError(
                "factorial manifest power artifact link mismatch"
            )
        if power.design_id != manifest.design_id or results.design_id != manifest.design_id:
            raise TrustedArtifactVerificationError("factorial design IDs do not agree")
        if results.design_manifest_artifact_sha256 != declaration.manifest_artifact.sha256:
            raise TrustedArtifactVerificationError("factorial results manifest link mismatch")
        if results.power_analysis_artifact_sha256 != declaration.power_analysis_artifact.sha256:
            raise TrustedArtifactVerificationError("factorial results power link mismatch")
        if power.primary_metric != results.primary_metric:
            raise TrustedArtifactVerificationError("factorial power and result metrics differ")
        if manifest.independent_unit is not power.independent_unit:
            raise TrustedArtifactVerificationError(
                "factorial manifest and power analysis use different experimental units"
            )
        manifest_unit_count = sum(len(cell.independent_unit_ids) for cell in manifest.cells)
        if manifest_unit_count < power.planned_independent_units:
            raise TrustedArtifactVerificationError(
                "factorial cell manifest is below the powered independent-unit target"
            )
        if results.non_identifiable_cells:
            raise TrustedArtifactVerificationError(
                "factorial design contains non-identifiable cells"
            )
        fitted = {
            frozenset(item.factors) for item in results.term_estimates if len(item.factors) >= 2
        }
        if not REQUIRED_FACTORIAL_INTERACTIONS.issubset(fitted):
            raise TrustedArtifactVerificationError("factorial results omit required interactions")
        expected_cell_by_unit = {
            unit_id: cell.cell_id
            for cell in manifest.cells
            for unit_id in cell.independent_unit_ids
        }
        for term in results.term_estimates:
            samples, _point, _low, _high = self._verify_powered_effect(
                term.effect,
                power,
                primary_metric=results.primary_metric,
            )
            observed_cell_by_unit = {
                sample.independent_unit_id: sample.factorial_cell_id for sample in samples.samples
            }
            if observed_cell_by_unit != expected_cell_by_unit:
                raise TrustedArtifactVerificationError(
                    "factorial term samples do not cover the registered cells and units"
                )
        return VerifiedFactorialEvidence(
            design_id=manifest.design_id,
            manifest_artifact_sha256=declaration.manifest_artifact.sha256,
            power_analysis_artifact_sha256=declaration.power_analysis_artifact.sha256,
            results_artifact_sha256=declaration.results_artifact.sha256,
            cell_count=len(manifest.cells),
            fitted_interactions=tuple(
                sorted(tuple(sorted(factor.value for factor in term)) for term in fitted)
            ),
            powered_factorial_established=True,
        )

    def _verify_coupling(
        self,
        declaration: CouplingEvidenceDeclaration,
        complete: StructureTwoEvidenceDeclaration,
    ) -> VerifiedCouplingEvidence:
        power, _power_envelope = self._load(
            declaration.power_analysis_artifact,
            kind=ArtifactKind.POWER_ANALYSIS,
            payload_type=PowerAnalysisPayload,
        )
        result, _result_envelope = self._load(
            declaration.results_artifact,
            kind=ArtifactKind.COUPLING_RESULTS,
            payload_type=CouplingResultsPayload,
        )
        if result.coupling is not declaration.coupling:
            raise TrustedArtifactVerificationError("coupling declaration and result differ")
        if result.power_analysis_artifact_sha256 != declaration.power_analysis_artifact.sha256:
            raise TrustedArtifactVerificationError("coupling result power link mismatch")
        if result.design_id != power.design_id:
            raise TrustedArtifactVerificationError("coupling design ID does not match power plan")
        if result.primary_utility_metric != complete.primary_utility_metric:
            raise TrustedArtifactVerificationError("coupling changed primary utility metric")
        if power.primary_metric != result.primary_utility_metric:
            raise TrustedArtifactVerificationError("coupling power metric differs")
        for referenced_bytes in (
            result.candidate_visible_input_artifact,
            result.baseline_visible_input_artifact,
            result.candidate_budget_artifact,
            result.baseline_budget_artifact,
            result.coupled_action_trace_artifact,
            result.decoupled_action_trace_artifact,
        ):
            self._read_bytes(referenced_bytes)
        if (
            result.candidate_visible_input_artifact.sha256
            != result.baseline_visible_input_artifact.sha256
        ):
            raise TrustedArtifactVerificationError("coupled and decoupled visible inputs differ")
        if result.candidate_budget_artifact.sha256 != result.baseline_budget_artifact.sha256:
            raise TrustedArtifactVerificationError("coupled and decoupled budgets differ")
        _samples, point, low, high = self._verify_powered_effect(
            result.effect,
            power,
            primary_metric=result.primary_utility_metric,
        )
        trace_changed = (
            result.coupled_action_trace_artifact.sha256
            != result.decoupled_action_trace_artifact.sha256
        )
        causal = trace_changed and (low > 0.0 or high < 0.0)
        benefit = trace_changed and self._benefit_passed(
            criterion=result.benefit_criterion,
            estimate=point,
            low=low,
            superiority_margin=result.superiority_margin,
            non_inferiority_margin=result.non_inferiority_margin,
        )
        return VerifiedCouplingEvidence(
            coupling=result.coupling,
            power_analysis_artifact_sha256=declaration.power_analysis_artifact.sha256,
            results_artifact_sha256=declaration.results_artifact.sha256,
            oriented_utility_effect=point,
            confidence_interval_low=low,
            confidence_interval_high=high,
            causal_coupling_established=causal,
            positive_benefit_established=benefit,
        )

    def _verify_noninterference(self, reference: ArtifactReference) -> bool:
        payload, _envelope = self._load(
            reference,
            kind=ArtifactKind.NONINTERFERENCE,
            payload_type=NoninterferencePayload,
        )
        for nested in (
            payload.first_visible_input,
            payload.second_visible_input,
            payload.first_sealed_truth,
            payload.second_sealed_truth,
            payload.first_output,
            payload.second_output,
        ):
            self._read_bytes(nested)
        return (
            payload.first_visible_input.sha256 == payload.second_visible_input.sha256
            and payload.first_sealed_truth.sha256 != payload.second_sealed_truth.sha256
            and payload.first_output.sha256 == payload.second_output.sha256
        )

    def _verify_full_rerun(
        self,
        reference: ArtifactReference,
        candidate_method_id: str,
    ) -> tuple[bool, str]:
        payload, _envelope = self._load(
            reference,
            kind=ArtifactKind.FULL_RERUN,
            payload_type=FullRerunPayload,
        )
        if payload.method_id != candidate_method_id:
            raise TrustedArtifactVerificationError("full-rerun proof belongs to another method")
        return payload.cached_projection == payload.rebuilt_projection, reference.sha256

    def _verify_numerical_downdate(
        self,
        reference: ArtifactReference,
        candidate_method_id: str,
    ) -> bool:
        payload, _envelope = self._load(
            reference,
            kind=ArtifactKind.NUMERICAL_DOWNDATE,
            payload_type=NumericalDowndatePayload,
        )
        if payload.method_id != candidate_method_id:
            raise TrustedArtifactVerificationError("downdate proof belongs to another method")
        if len(payload.direct_recompute) != len(payload.numerical_downdate):
            raise TrustedArtifactVerificationError("downdate and direct vectors differ in shape")
        maximum_error = max(
            abs(direct - downdated)
            for direct, downdated in zip(
                payload.direct_recompute,
                payload.numerical_downdate,
                strict=True,
            )
        )
        condition_acceptable = (
            payload.observed_condition_number <= payload.maximum_condition_number
            or payload.replay_fallback_used
        )
        return maximum_error <= payload.absolute_tolerance and condition_acceptable

    def _verify_pareto(
        self,
        reference: ArtifactReference,
        candidate_method_id: str,
        full_rerun_sha256: str,
        full_rerun_equivalent: bool,
    ) -> bool:
        payload, _envelope = self._load(
            reference,
            kind=ArtifactKind.PARETO_EVALUATION,
            payload_type=ParetoEvaluationPayload,
        )
        if payload.candidate_method_id != candidate_method_id:
            raise TrustedArtifactVerificationError("Pareto artifact candidate method mismatch")
        if payload.full_rerun_artifact_sha256 != full_rerun_sha256:
            raise TrustedArtifactVerificationError("Pareto artifact is not bound to full rerun")
        candidate = next(
            point for point in payload.points if point.method_id == candidate_method_id
        )
        if candidate.full_rerun_equivalent != full_rerun_equivalent:
            raise TrustedArtifactVerificationError(
                "Pareto eligibility contradicts verified full-rerun evidence"
            )
        frontier = contamination_recovery_pareto_frontier(payload.points)
        return any(point.method_id == candidate_method_id for point in frontier)


__all__ = [
    "TrustedArtifactVerificationError",
    "TrustedStructureTwoArtifactVerifier",
    "VerifiedBaselineEvidence",
    "VerifiedCouplingEvidence",
    "VerifiedFactorialEvidence",
    "VerifiedStructureTwoEvidenceBundle",
    "cluster_bootstrap_effect",
    "contamination_recovery_pareto_frontier",
]
