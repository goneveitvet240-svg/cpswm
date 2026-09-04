"""Machine-readable, authority-attested evidence for Structure Two claims.

These contracts are deliberately declarative.  They locate artifacts and
describe experimental designs, but none contains a caller-controlled ``passed``
or ``powered`` flag.  Those conclusions belong to the trusted verifier.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from itertools import product
from math import isfinite
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from cpswm.contracts.base import ContractModel, require_aware
from cpswm.system.attestation import Attestation, AttestationAuthority, attested_payload
from cpswm.system.reproducibility import content_sha256

DOMAIN_STRUCTURE_TWO_ARTIFACT = "cpswm.structure_two.evidence_artifact.v1"
DOMAIN_STRUCTURE_TWO_VERIFIED_BUNDLE = "cpswm.structure_two.verified_bundle.v1"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

PositiveInt = Annotated[int, Field(gt=0)]


class StructureTwoRoute(StrEnum):
    OPCEU = "opceu"
    CHEH_ORRER = "cheh_orrer"
    PCHMP = "pchmp"
    CF_BOCPD = "cf_bocpd"
    RGRC = "rgrc"
    CCRR = "ccrr"
    CIAV = "ciav"


class MatchedBaselineKind(StrEnum):
    MATCHED_OPEN_WORLD_AMG = "matched_open_world_amg"
    ORDINARY_HETEROGENEOUS_GNN = "ordinary_heterogeneous_gnn"
    ORDINARY_BOCPD = "ordinary_bocpd"
    BOCPDMS = "bocpdms"
    SWITCHING_HMM = "switching_hmm"
    NEVER_ACT = "never_act"
    ALWAYS_VERIFY = "always_verify"
    RANDOM_VERIFY = "random_verify"
    MAX_ENTROPY = "max_entropy"


REQUIRED_MATCHED_BASELINES = frozenset(MatchedBaselineKind)


class CrossModuleCouplingKind(StrEnum):
    """The exact four Task-9 pairs; legacy directional names are not admissible."""

    OPCEU_X_CF_BOCPD = "opceu_x_cf_bocpd"
    ORRER_CHEH_PCHMP_X_RGRC = "orrer_cheh_pchmp_x_rgrc"
    CF_BOCPD_X_CCRR = "cf_bocpd_x_ccrr"
    RGRC_CCRR_X_CIAV = "rgrc_ccrr_x_ciav"


class InterventionFactor(StrEnum):
    OBSERVATION_PROCESS = "observation_process"
    ACTOR_MIXTURE = "actor_mixture"
    IDENTITY_ASSOCIATION = "identity_association"
    OWNER_HABIT_REGIME = "owner_habit_regime"
    TRANSIENT_NOISE = "transient_noise"


REQUIRED_FACTORIAL_INTERACTIONS = frozenset(
    {
        frozenset({InterventionFactor.OBSERVATION_PROCESS, InterventionFactor.ACTOR_MIXTURE}),
        frozenset({InterventionFactor.IDENTITY_ASSOCIATION, InterventionFactor.TRANSIENT_NOISE}),
        frozenset({InterventionFactor.ACTOR_MIXTURE, InterventionFactor.OWNER_HABIT_REGIME}),
        frozenset({InterventionFactor.OBSERVATION_PROCESS, InterventionFactor.OWNER_HABIT_REGIME}),
    }
)


class ExperimentalUnit(StrEnum):
    SEED = "seed"
    HOUSEHOLD = "household"
    EPISODE = "episode"


class ConfidenceIntervalMethod(StrEnum):
    CLUSTER_BOOTSTRAP = "cluster_bootstrap"
    CLUSTER_ROBUST = "cluster_robust"
    RANDOMIZATION_INFERENCE = "randomization_inference"


class BenefitCriterion(StrEnum):
    SUPERIORITY = "superiority"
    NON_INFERIORITY = "non_inferiority"


class ArtifactKind(StrEnum):
    EFFECT_SAMPLES = "effect_samples"
    TUNING_COMPLETION = "tuning_completion"
    TUNING_REPORT = "tuning_report"
    MATCHED_COMPARISON = "matched_comparison"
    POWER_ANALYSIS = "power_analysis"
    FACTORIAL_MANIFEST = "factorial_manifest"
    FACTORIAL_RESULTS = "factorial_results"
    COUPLING_RESULTS = "coupling_results"
    NONINTERFERENCE = "noninterference"
    FULL_RERUN = "full_rerun"
    NUMERICAL_DOWNDATE = "numerical_downdate"
    PARETO_EVALUATION = "pareto_evaluation"


class ArtifactReference(ContractModel):
    """A declaration pointing to bytes the verifier must actually open."""

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    expected_kind: ArtifactKind | None = None


class ArtifactEnvelope(ContractModel):
    """Authority-attested JSON envelope stored on disk."""

    artifact_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    kind: ArtifactKind
    schema_version: str = Field(min_length=1)
    payload_schema: str = Field(min_length=1)
    produced_at: datetime
    payload: dict[str, object]
    payload_sha256: str = Field(pattern=SHA256_PATTERN)
    attestation: Attestation | None = None

    @field_validator("produced_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        return require_aware(value, "produced_at")

    @model_validator(mode="after")
    def bind_payload_hash(self) -> ArtifactEnvelope:
        if self.payload_sha256 != content_sha256(self.payload):
            raise ValueError("artifact payload hash does not match payload bytes")
        return self


def issue_artifact_envelope(
    *,
    artifact_id: str,
    experiment_id: str,
    kind: ArtifactKind,
    produced_at: datetime,
    payload: ContractModel,
    authority: AttestationAuthority,
) -> ArtifactEnvelope:
    """Issue one signed artifact; production callers keep authority out of candidate code."""

    unsigned = ArtifactEnvelope(
        artifact_id=artifact_id,
        experiment_id=experiment_id,
        kind=kind,
        schema_version="1.0",
        payload_schema=payload.__class__.__name__,
        produced_at=produced_at,
        payload=payload.model_dump(mode="json"),
        payload_sha256=content_sha256(payload.model_dump(mode="json")),
    )
    signature = authority.sign(
        DOMAIN_STRUCTURE_TWO_ARTIFACT,
        attested_payload(unsigned),
    )
    return unsigned.model_copy(update={"attestation": signature})


class TuningCompletionPayload(ContractModel):
    method_id: str = Field(min_length=1)
    validation_split_artifact: ArtifactReference
    test_split_artifact: ArtifactReference
    tuning_budget_artifact: ArtifactReference
    tuning_runs_completed: PositiveInt
    candidate_configuration_count: PositiveInt
    test_split_access_count: int = Field(ge=0)


class TuningReportPayload(ContractModel):
    method_id: str = Field(min_length=1)
    validation_split_artifact: ArtifactReference
    test_split_artifact: ArtifactReference
    tuning_budget_artifact: ArtifactReference
    tuning_runs_completed: PositiveInt
    candidate_configuration_count: PositiveInt
    selected_hyperparameters: dict[str, str | int | float | bool] = Field(min_length=1)
    test_split_access_count: int = Field(ge=0)
    completion_receipt_artifact: ArtifactReference


class EffectEstimate(ContractModel):
    estimate: float
    confidence_interval_low: float
    confidence_interval_high: float
    confidence_level: float = Field(gt=0.0, lt=1.0)
    confidence_interval_method: ConfidenceIntervalMethod
    analysis_samples_artifact: ArtifactReference
    bootstrap_seed: int
    bootstrap_resamples: int = Field(ge=1000)

    @model_validator(mode="after")
    def validate_estimate(self) -> EffectEstimate:
        values = (
            self.estimate,
            self.confidence_interval_low,
            self.confidence_interval_high,
        )
        if any(not isfinite(value) for value in values):
            raise ValueError("effect estimate and interval must be finite")
        if self.confidence_interval_low > self.confidence_interval_high:
            raise ValueError("effect confidence interval is reversed")
        if not self.confidence_interval_low <= self.estimate <= self.confidence_interval_high:
            raise ValueError("effect estimate must lie inside its confidence interval")
        return self


class ClusteredEffectSample(ContractModel):
    independent_unit_id: str = Field(min_length=1)
    cluster_id: str = Field(min_length=1)
    factorial_cell_id: str | None = None
    oriented_effect: float

    @field_validator("oriented_effect")
    @classmethod
    def finite_effect(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("sample effect must be finite")
        return value


class EffectSamplePayload(ContractModel):
    primary_metric: str = Field(min_length=1)
    independent_unit: ExperimentalUnit
    samples: tuple[ClusteredEffectSample, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def independent_units_and_clusters(self) -> EffectSamplePayload:
        units = [sample.independent_unit_id for sample in self.samples]
        clusters = {sample.cluster_id for sample in self.samples}
        if len(units) != len(set(units)):
            raise ValueError("effect sample independent-unit IDs must be unique")
        if len(clusters) < 2:
            raise ValueError("clustered effect samples require at least two clusters")
        return self


class MatchedComparisonPayload(ContractModel):
    candidate_method_id: str = Field(min_length=1)
    baseline_method_id: str = Field(min_length=1)
    baseline_tuning_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_visible_input_artifact: ArtifactReference
    baseline_visible_input_artifact: ArtifactReference
    candidate_budget_artifact: ArtifactReference
    baseline_budget_artifact: ArtifactReference
    primary_utility_metric: str = Field(min_length=1)
    higher_is_better: bool
    candidate_metric_estimate: float
    baseline_metric_estimate: float
    oriented_candidate_minus_baseline: EffectEstimate
    benefit_criterion: BenefitCriterion
    superiority_margin: float = Field(ge=0.0)
    non_inferiority_margin: float = Field(ge=0.0)

    @model_validator(mode="after")
    def finite_metric_estimates(self) -> MatchedComparisonPayload:
        if not isfinite(self.candidate_metric_estimate) or not isfinite(
            self.baseline_metric_estimate
        ):
            raise ValueError("matched comparison estimates must be finite")
        return self


class PowerAnalysisPayload(ContractModel):
    design_id: str = Field(min_length=1)
    primary_metric: str = Field(min_length=1)
    alpha: float = Field(gt=0.0, le=0.05)
    target_power: float = Field(ge=0.8, lt=1.0)
    minimum_detectable_effect: float = Field(gt=0.0)
    planned_independent_units: PositiveInt
    planned_clusters: int = Field(ge=2)
    independent_unit: ExperimentalUnit


class SingleFactorInterventionProbe(ContractModel):
    """An OFAT probe.  It is useful diagnostically but is not a factorial design."""

    factor: InterventionFactor
    reference_level: str = Field(min_length=1)
    intervention_level: str = Field(min_length=1)
    artifact: ArtifactReference

    @model_validator(mode="after")
    def different_levels(self) -> SingleFactorInterventionProbe:
        if self.reference_level == self.intervention_level:
            raise ValueError("single-factor probe levels must differ")
        return self


class FactorialCellManifest(ContractModel):
    cell_id: str = Field(min_length=1)
    levels: dict[InterventionFactor, str]
    seed_ids: tuple[str, ...] = Field(min_length=1)
    household_ids: tuple[str, ...] = Field(min_length=1)
    episode_ids: tuple[str, ...] = Field(min_length=1)
    independent_unit_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def complete_cell(self) -> FactorialCellManifest:
        if set(self.levels) != set(InterventionFactor):
            raise ValueError("factorial cell must assign every factor")
        if len(self.independent_unit_ids) != len(set(self.independent_unit_ids)):
            raise ValueError("cell independent-unit IDs must be unique")
        return self


class FactorialDesignManifestPayload(ContractModel):
    design_id: str = Field(min_length=1)
    factor_levels: dict[InterventionFactor, tuple[str, ...]]
    cells: tuple[FactorialCellManifest, ...] = Field(min_length=1)
    interaction_terms: tuple[tuple[InterventionFactor, ...], ...] = Field(min_length=1)
    independent_unit: ExperimentalUnit
    power_analysis_artifact_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def require_full_factorial_cells(self) -> FactorialDesignManifestPayload:
        if set(self.factor_levels) != set(InterventionFactor):
            raise ValueError("factorial manifest must declare levels for every factor")
        if any(
            len(levels) < 2 or len(levels) != len(set(levels))
            for levels in self.factor_levels.values()
        ):
            raise ValueError("each factorial factor requires at least two unique levels")
        expected = {
            tuple(zip(InterventionFactor, combination, strict=True))
            for combination in product(
                *(self.factor_levels[factor] for factor in InterventionFactor)
            )
        }
        observed = {
            tuple((factor, cell.levels[factor]) for factor in InterventionFactor)
            for cell in self.cells
        }
        if observed != expected or len(observed) != len(self.cells):
            raise ValueError("factorial manifest must contain every unique Cartesian cell")
        all_independent_units = [
            unit_id for cell in self.cells for unit_id in cell.independent_unit_ids
        ]
        if len(all_independent_units) != len(set(all_independent_units)):
            raise ValueError(
                "factorial independent experimental units cannot be reused across cells"
            )
        unit_field = {
            ExperimentalUnit.SEED: "seed_ids",
            ExperimentalUnit.HOUSEHOLD: "household_ids",
            ExperimentalUnit.EPISODE: "episode_ids",
        }[self.independent_unit]
        for cell in self.cells:
            declared_units = getattr(cell, unit_field)
            if cell.independent_unit_ids != declared_units:
                raise ValueError(
                    "cell independent-unit IDs must match the selected experimental-unit field"
                )
        terms = [frozenset(term) for term in self.interaction_terms]
        if any(len(term) < 2 for term in terms):
            raise ValueError("factorial interaction terms require at least two factors")
        if len(terms) != len(set(terms)):
            raise ValueError("factorial interaction terms must be unique")
        if not REQUIRED_FACTORIAL_INTERACTIONS.issubset(set(terms)):
            raise ValueError("factorial manifest omits a required interaction term")
        actor_levels = self.factor_levels[InterventionFactor.ACTOR_MIXTURE]
        if not any("visitor" in level.lower() for level in actor_levels):
            raise ValueError("actor-mixture levels must include a visitor condition")
        return self


class FactorialTermEstimate(ContractModel):
    factors: tuple[InterventionFactor, ...] = Field(min_length=1)
    effect: EffectEstimate


class FactorialResultsPayload(ContractModel):
    design_id: str = Field(min_length=1)
    design_manifest_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    power_analysis_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    primary_metric: str = Field(min_length=1)
    term_estimates: tuple[FactorialTermEstimate, ...] = Field(min_length=1)
    non_identifiable_cells: tuple[str, ...] = ()


class CouplingResultsPayload(ContractModel):
    design_id: str = Field(min_length=1)
    coupling: CrossModuleCouplingKind
    coupled_method_id: str = Field(min_length=1)
    decoupled_method_id: str = Field(min_length=1)
    candidate_visible_input_artifact: ArtifactReference
    baseline_visible_input_artifact: ArtifactReference
    candidate_budget_artifact: ArtifactReference
    baseline_budget_artifact: ArtifactReference
    coupled_action_trace_artifact: ArtifactReference
    decoupled_action_trace_artifact: ArtifactReference
    primary_utility_metric: str = Field(min_length=1)
    power_analysis_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    effect: EffectEstimate
    benefit_criterion: BenefitCriterion
    superiority_margin: float = Field(ge=0.0)
    non_inferiority_margin: float = Field(ge=0.0)


class NoninterferencePayload(ContractModel):
    first_visible_input: ArtifactReference
    second_visible_input: ArtifactReference
    first_sealed_truth: ArtifactReference
    second_sealed_truth: ArtifactReference
    first_output: ArtifactReference
    second_output: ArtifactReference
    leakage_probe_names: tuple[str, ...] = Field(min_length=1)


class FullRerunPayload(ContractModel):
    method_id: str = Field(min_length=1)
    cached_projection: dict[str, float]
    rebuilt_projection: dict[str, float]

    @model_validator(mode="after")
    def finite_projections(self) -> FullRerunPayload:
        if any(
            not isfinite(value)
            for value in (*self.cached_projection.values(), *self.rebuilt_projection.values())
        ):
            raise ValueError("full-rerun projections must be finite")
        return self


class NumericalDowndatePayload(ContractModel):
    method_id: str = Field(min_length=1)
    direct_recompute: tuple[float, ...] = Field(min_length=1)
    numerical_downdate: tuple[float, ...] = Field(min_length=1)
    absolute_tolerance: float = Field(gt=0.0)
    observed_condition_number: float = Field(gt=0.0)
    maximum_condition_number: float = Field(gt=0.0)
    replay_fallback_used: bool


class ContaminationRecoveryPoint(ContractModel):
    method_id: str = Field(min_length=1)
    owner_contamination: float = Field(ge=0.0)
    recovery_latency: float = Field(ge=0.0)
    revision_cost: float = Field(ge=0.0)
    action_utility: float
    full_rerun_equivalent: bool

    @field_validator("action_utility")
    @classmethod
    def finite_utility(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("action utility must be finite")
        return value


class ParetoEvaluationPayload(ContractModel):
    candidate_method_id: str = Field(min_length=1)
    points: tuple[ContaminationRecoveryPoint, ...] = Field(min_length=2)
    full_rerun_artifact_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def unique_methods(self) -> ParetoEvaluationPayload:
        method_ids = [point.method_id for point in self.points]
        if len(method_ids) != len(set(method_ids)):
            raise ValueError("Pareto methods must be unique")
        if self.candidate_method_id not in method_ids:
            raise ValueError("Pareto candidate method must appear among points")
        return self


class MatchedBaselineDeclaration(ContractModel):
    baseline: MatchedBaselineKind
    baseline_method_id: str = Field(min_length=1)
    tuning_artifact: ArtifactReference
    comparison_artifact: ArtifactReference


class FactorialDesignDeclaration(ContractModel):
    manifest_artifact: ArtifactReference
    power_analysis_artifact: ArtifactReference
    results_artifact: ArtifactReference
    single_factor_probes: tuple[SingleFactorInterventionProbe, ...] = ()


class CouplingEvidenceDeclaration(ContractModel):
    coupling: CrossModuleCouplingKind
    power_analysis_artifact: ArtifactReference
    results_artifact: ArtifactReference


class StructureTwoEvidenceDeclaration(ContractModel):
    """Untrusted declarations.  The claim evaluator never consumes this directly."""

    candidate_method_id: str = Field(min_length=1)
    primary_utility_metric: str = Field(min_length=1)
    baselines: tuple[MatchedBaselineDeclaration, ...]
    factorial: FactorialDesignDeclaration
    noninterference_artifact: ArtifactReference
    full_rerun_artifact: ArtifactReference
    numerical_downdate_artifact: ArtifactReference
    pareto_artifact: ArtifactReference
    couplings: tuple[CouplingEvidenceDeclaration, ...]

    @model_validator(mode="after")
    def unique_declarations(self) -> StructureTwoEvidenceDeclaration:
        baselines = [item.baseline for item in self.baselines]
        couplings = [item.coupling for item in self.couplings]
        if len(baselines) != len(set(baselines)):
            raise ValueError("baseline declarations must be unique")
        if len(couplings) != len(set(couplings)):
            raise ValueError("coupling declarations must be unique")
        return self


__all__ = [
    "DOMAIN_STRUCTURE_TWO_ARTIFACT",
    "DOMAIN_STRUCTURE_TWO_VERIFIED_BUNDLE",
    "REQUIRED_FACTORIAL_INTERACTIONS",
    "REQUIRED_MATCHED_BASELINES",
    "ArtifactEnvelope",
    "ArtifactKind",
    "ArtifactReference",
    "BenefitCriterion",
    "ClusteredEffectSample",
    "ConfidenceIntervalMethod",
    "ContaminationRecoveryPoint",
    "CouplingEvidenceDeclaration",
    "CouplingResultsPayload",
    "CrossModuleCouplingKind",
    "EffectEstimate",
    "EffectSamplePayload",
    "ExperimentalUnit",
    "FactorialCellManifest",
    "FactorialDesignDeclaration",
    "FactorialDesignManifestPayload",
    "FactorialResultsPayload",
    "FactorialTermEstimate",
    "FullRerunPayload",
    "InterventionFactor",
    "MatchedBaselineDeclaration",
    "MatchedBaselineKind",
    "MatchedComparisonPayload",
    "NoninterferencePayload",
    "NumericalDowndatePayload",
    "ParetoEvaluationPayload",
    "PowerAnalysisPayload",
    "SingleFactorInterventionProbe",
    "StructureTwoEvidenceDeclaration",
    "StructureTwoRoute",
    "TuningCompletionPayload",
    "TuningReportPayload",
    "issue_artifact_envelope",
]
