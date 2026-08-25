"""S3-2 controlled-noise transformations and deterministic benchmark matrix."""

from __future__ import annotations

from dataclasses import dataclass
from math import log
from random import Random
from statistics import mean, stdev
from typing import Any
from uuid import UUID

from cpswm.contracts import (
    CandidateKind,
    EvidenceChannel,
    JointPosteriorRequest,
    ResolutionStatus,
)
from cpswm.world_model.grounded_search import JointPosteriorFusion

from .direction_three_metrics import (
    DirectionThreeMetricCase,
    evaluate_direction_three_metrics,
)
from .direction_three_oracle_suite import (
    OracleInitialBelief,
    build_oracle_request,
    default_oracle_scenarios,
)


@dataclass(frozen=True, slots=True)
class DirectionThreeNoiseConfig:
    condition_id: str
    seed: int = 0
    channel_missing_probability: tuple[tuple[EvidenceChannel, float], ...] = ()
    temperature_by_channel: tuple[tuple[EvidenceChannel, float], ...] = ()
    reliability_discount_by_channel: tuple[tuple[EvidenceChannel, float], ...] = ()
    swap_target_distractor_channels: tuple[EvidenceChannel, ...] = ()
    occlusion_severity: float = 0.0
    retrieval_miss: bool = False
    unknown_likelihood_scale: float = 1.0

    def __post_init__(self) -> None:
        if not self.condition_id.strip():
            raise ValueError("noise condition id must be non-empty")
        for _, probability in self.channel_missing_probability:
            if not 0.0 <= probability <= 1.0:
                raise ValueError("channel missing probabilities must be in [0, 1]")
        for _, temperature in self.temperature_by_channel:
            if temperature <= 0.0:
                raise ValueError("calibration temperatures must be positive")
        for _, discount in self.reliability_discount_by_channel:
            if not 0.0 <= discount <= 1.0:
                raise ValueError("reliability discounts must be in [0, 1]")
        if not 0.0 <= self.occlusion_severity <= 1.0:
            raise ValueError("occlusion severity must be in [0, 1]")
        if self.unknown_likelihood_scale <= 0.0:
            raise ValueError("unknown likelihood scale must be positive")
        for values, name in (
            (self.channel_missing_probability, "channel missingness"),
            (self.temperature_by_channel, "temperature"),
            (self.reliability_discount_by_channel, "reliability discount"),
        ):
            channels = [channel for channel, _ in values]
            if len(channels) != len(set(channels)):
                raise ValueError(f"duplicate channel in {name}")


@dataclass(frozen=True, slots=True)
class ControlledNoiseResult:
    request: JointPosteriorRequest
    operations: tuple[dict[str, Any], ...]
    true_target_was_retrieved: bool


@dataclass(frozen=True, slots=True)
class DirectionThreeNoiseStudyCondition:
    arm_id: str
    severity: float
    seed: int
    config: DirectionThreeNoiseConfig


def _temperature_scale(probability: float, temperature: float) -> float:
    epsilon = 1e-9
    probability = min(max(probability, epsilon), 1.0 - epsilon)
    logit = log(probability / (1.0 - probability)) / temperature
    if logit >= 0.0:
        return 1.0 / (1.0 + pow(2.718281828459045, -logit))
    exp_logit = pow(2.718281828459045, logit)
    return exp_logit / (1.0 + exp_logit)


def apply_direction_three_controlled_noise(
    request: JointPosteriorRequest,
    *,
    true_target_candidate_id: UUID,
    distractor_candidate_id: UUID,
    config: DirectionThreeNoiseConfig,
) -> ControlledNoiseResult:
    """Apply declared noise only; every mutation is recorded in the trace."""

    random = Random(config.seed)
    missing = dict(config.channel_missing_probability)
    temperatures = dict(config.temperature_by_channel)
    discounts = dict(config.reliability_discount_by_channel)
    swaps = set(config.swap_target_distractor_channels)
    candidate_by_id = {candidate.candidate_id: candidate for candidate in request.candidates}
    if true_target_candidate_id not in candidate_by_id:
        raise ValueError("true target must be in the clean request before noise injection")
    if distractor_candidate_id not in candidate_by_id:
        raise ValueError("distractor must be in the clean request")

    operations: list[dict[str, Any]] = []
    transformed = []
    for candidate in sorted(request.candidates, key=lambda item: str(item.candidate_id)):
        if config.retrieval_miss and candidate.candidate_id == true_target_candidate_id:
            operations.append(
                {
                    "operation": "retrieval_miss",
                    "candidate_id": str(candidate.candidate_id),
                }
            )
            continue
        evidence_by_channel = {}
        for channel in EvidenceChannel:
            evidence = candidate.channel_evidence[channel]
            likelihood = evidence.likelihood_given_candidate
            reliability = evidence.reliability
            availability = evidence.availability

            if channel in swaps and candidate.candidate_id in {
                true_target_candidate_id,
                distractor_candidate_id,
            }:
                source_id = (
                    distractor_candidate_id
                    if candidate.candidate_id == true_target_candidate_id
                    else true_target_candidate_id
                )
                likelihood = (
                    candidate_by_id[source_id].channel_evidence[channel].likelihood_given_candidate
                )
                operations.append(
                    {
                        "operation": "swap_likelihood",
                        "channel": channel.value,
                        "candidate_id": str(candidate.candidate_id),
                        "source_candidate_id": str(source_id),
                    }
                )

            temperature = temperatures.get(channel)
            if temperature is not None:
                likelihood = _temperature_scale(likelihood, temperature)
                operations.append(
                    {
                        "operation": "temperature_scale",
                        "channel": channel.value,
                        "candidate_id": str(candidate.candidate_id),
                        "temperature": temperature,
                    }
                )

            discount = discounts.get(channel)
            if discount is not None:
                reliability *= discount
                operations.append(
                    {
                        "operation": "correlation_reliability_discount",
                        "channel": channel.value,
                        "candidate_id": str(candidate.candidate_id),
                        "discount": discount,
                    }
                )

            probability = missing.get(channel, 0.0)
            if probability > 0.0 and random.random() < probability:
                availability = 0.0
                operations.append(
                    {
                        "operation": "channel_missing",
                        "channel": channel.value,
                        "candidate_id": str(candidate.candidate_id),
                    }
                )

            if channel in {EvidenceChannel.VISUAL, EvidenceChannel.GEOMETRY}:
                severity = config.occlusion_severity
                if severity > 0.0:
                    likelihood = (1.0 - severity) * likelihood + severity * 0.5
                    operations.append(
                        {
                            "operation": "occlusion_degradation",
                            "channel": channel.value,
                            "candidate_id": str(candidate.candidate_id),
                            "severity": severity,
                        }
                    )

            if candidate.kind == CandidateKind.UNKNOWN and config.unknown_likelihood_scale != 1.0:
                likelihood = min(1.0, likelihood * config.unknown_likelihood_scale)
                operations.append(
                    {
                        "operation": "unknown_likelihood_scale",
                        "channel": channel.value,
                        "candidate_id": str(candidate.candidate_id),
                        "scale": config.unknown_likelihood_scale,
                    }
                )

            evidence_by_channel[channel] = evidence.model_copy(
                update={
                    "likelihood_given_candidate": likelihood,
                    "reliability": reliability,
                    "availability": availability,
                    "model_version": f"{evidence.model_version}+noise:{config.condition_id}",
                }
            )
        transformed.append(candidate.model_copy(update={"channel_evidence": evidence_by_channel}))

    prior_total = sum(candidate.prior_probability for candidate in transformed)
    transformed = [
        candidate.model_copy(
            update={"prior_probability": candidate.prior_probability / prior_total}
        )
        for candidate in transformed
    ]
    noisy_request = JointPosteriorRequest.model_validate(
        request.model_copy(update={"candidates": tuple(transformed)}).model_dump(mode="python")
    )
    return ControlledNoiseResult(
        request=noisy_request,
        operations=tuple(operations),
        true_target_was_retrieved=not config.retrieval_miss,
    )


def default_controlled_noise_matrix() -> tuple[DirectionThreeNoiseConfig, ...]:
    return (
        DirectionThreeNoiseConfig("clean"),
        DirectionThreeNoiseConfig(
            "visual_missing",
            channel_missing_probability=((EvidenceChannel.VISUAL, 1.0),),
        ),
        DirectionThreeNoiseConfig(
            "six_channel_miscalibration",
            temperature_by_channel=tuple((channel, 2.0) for channel in EvidenceChannel),
        ),
        DirectionThreeNoiseConfig(
            "visual_geometry_correlation_discount",
            reliability_discount_by_channel=(
                (EvidenceChannel.VISUAL, 0.5),
                (EvidenceChannel.GEOMETRY, 0.5),
            ),
        ),
        DirectionThreeNoiseConfig(
            "identity_noise",
            swap_target_distractor_channels=(EvidenceChannel.VISUAL,),
        ),
        DirectionThreeNoiseConfig(
            "actor_noise",
            swap_target_distractor_channels=(EvidenceChannel.PERSON,),
        ),
        DirectionThreeNoiseConfig(
            "event_noise",
            swap_target_distractor_channels=(EvidenceChannel.EVENT,),
        ),
        DirectionThreeNoiseConfig(
            "habit_noise",
            swap_target_distractor_channels=(EvidenceChannel.HABIT,),
        ),
        DirectionThreeNoiseConfig(
            "retrieval_miss_open_set",
            retrieval_miss=True,
            unknown_likelihood_scale=10.0,
        ),
        DirectionThreeNoiseConfig("occlusion_distance_proxy", occlusion_severity=0.8),
    )


def default_controlled_noise_study(
    *, seeds: tuple[int, ...] = (11, 29, 47)
) -> tuple[DirectionThreeNoiseStudyCondition, ...]:
    """Frozen severity x seed x combination matrix; no method route is selected."""

    if len(seeds) < 2 or len(seeds) != len(set(seeds)):
        raise ValueError("controlled-noise study requires at least two unique seeds")
    conditions: list[DirectionThreeNoiseStudyCondition] = []
    for severity in (0.25, 0.5, 0.75):
        for seed in seeds:
            suffix = f"s{severity:.2f}-seed{seed}"
            specs = (
                (
                    "visual_missing",
                    DirectionThreeNoiseConfig(
                        f"study-visual-missing-{suffix}",
                        seed=seed,
                        channel_missing_probability=((EvidenceChannel.VISUAL, severity),),
                    ),
                ),
                (
                    "six_channel_temperature",
                    DirectionThreeNoiseConfig(
                        f"study-temperature-{suffix}",
                        seed=seed,
                        temperature_by_channel=tuple(
                            (channel, 1.0 + 3.0 * severity) for channel in EvidenceChannel
                        ),
                    ),
                ),
                (
                    "visual_geometry_dependence",
                    DirectionThreeNoiseConfig(
                        f"study-dependence-{suffix}",
                        seed=seed,
                        reliability_discount_by_channel=(
                            (EvidenceChannel.VISUAL, 1.0 - severity),
                            (EvidenceChannel.GEOMETRY, 1.0 - severity),
                        ),
                    ),
                ),
                (
                    "occlusion_distance_proxy",
                    DirectionThreeNoiseConfig(
                        f"study-occlusion-{suffix}",
                        seed=seed,
                        occlusion_severity=severity,
                    ),
                ),
                (
                    "retrieval_miss_unknown_scale",
                    DirectionThreeNoiseConfig(
                        f"study-retrieval-miss-{suffix}",
                        seed=seed,
                        retrieval_miss=True,
                        unknown_likelihood_scale=1.0 + 12.0 * severity,
                    ),
                ),
                (
                    "combined_sensing_noise",
                    DirectionThreeNoiseConfig(
                        f"study-combined-sensing-{suffix}",
                        seed=seed,
                        channel_missing_probability=((EvidenceChannel.VISUAL, severity),),
                        temperature_by_channel=(
                            (EvidenceChannel.VISUAL, 1.0 + 2.0 * severity),
                            (EvidenceChannel.GEOMETRY, 1.0 + 2.0 * severity),
                        ),
                        reliability_discount_by_channel=(
                            (EvidenceChannel.VISUAL, 1.0 - 0.5 * severity),
                            (EvidenceChannel.GEOMETRY, 1.0 - 0.5 * severity),
                        ),
                        occlusion_severity=severity,
                    ),
                ),
                (
                    "combined_context_noise",
                    DirectionThreeNoiseConfig(
                        f"study-combined-context-{suffix}",
                        seed=seed,
                        reliability_discount_by_channel=tuple(
                            (channel, 1.0 - severity)
                            for channel in (
                                EvidenceChannel.PERSON,
                                EvidenceChannel.EVENT,
                                EvidenceChannel.HABIT,
                            )
                        ),
                    ),
                ),
            )
            conditions.extend(
                DirectionThreeNoiseStudyCondition(
                    arm_id=arm_id,
                    severity=severity,
                    seed=seed,
                    config=config,
                )
                for arm_id, config in specs
            )
    return tuple(conditions)


def _t95_interval(values: list[float]) -> dict[str, float]:
    average = mean(values)
    if len(values) < 2:
        return {"mean": average, "lower": average, "upper": average}
    # Frozen critical values for the small preregistered seed counts used here.
    critical = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776}.get(len(values), 1.96)
    half_width = critical * stdev(values) / (len(values) ** 0.5)
    return {"mean": average, "lower": average - half_width, "upper": average + half_width}


def run_controlled_noise_study(
    study: tuple[DirectionThreeNoiseStudyCondition, ...] | None = None,
) -> dict[str, Any]:
    """Run a multi-seed severity grid and preserve scenario-level strata."""

    conditions = study or default_controlled_noise_study()
    base_report = run_controlled_noise_benchmark(
        tuple(condition.config for condition in conditions)
    )
    metadata = {condition.config.condition_id: condition for condition in conditions}
    summaries = {item["condition_id"]: item for item in base_report["conditions"]}
    groups: dict[tuple[str, float], list[DirectionThreeNoiseStudyCondition]] = {}
    for condition in conditions:
        groups.setdefault((condition.arm_id, condition.severity), []).append(condition)

    aggregated = []
    for (arm_id, severity), members in sorted(groups.items()):
        member_summaries = [summaries[member.config.condition_id] for member in members]
        aggregated.append(
            {
                "arm_id": arm_id,
                "severity": severity,
                "seed_count": len(members),
                "seeds": [member.seed for member in members],
                "top1_accuracy_t95": _t95_interval(
                    [item["top1_accuracy"] for item in member_summaries]
                ),
                "mean_nll_t95": _t95_interval([item["mean_nll"] for item in member_summaries]),
                "mean_brier_t95": _t95_interval([item["mean_brier"] for item in member_summaries]),
                "support_miss_count": sum(item["support_miss_count"] for item in member_summaries),
            }
        )

    stratum_groups: dict[tuple[str, float, str], list[dict[str, Any]]] = {}
    for case in base_report["cases"]:
        condition = metadata[case["condition_id"]]
        stratum_groups.setdefault(
            (condition.arm_id, condition.severity, case["scenario_id"]), []
        ).append(case)
    strata = [
        {
            "arm_id": arm_id,
            "severity": severity,
            "scenario_id": scenario_id,
            "case_count": len(cases),
            "top1_accuracy": mean(case["top1_correct"] for case in cases),
            "mean_nll": mean(case["nll"] for case in cases),
            "mean_brier": mean(case["brier"] for case in cases),
        }
        for (arm_id, severity, scenario_id), cases in sorted(stratum_groups.items())
    ]
    return {
        "schema_name": "cpswm.DirectionThreeControlledNoiseStudyReport",
        "schema_version": "0.1.0",
        "maturity": "s3-2-controlled-noise-multiseed-grid",
        "condition_count": len(conditions),
        "case_count": base_report["case_count"],
        "arm_count": len({condition.arm_id for condition in conditions}),
        "severity_levels": sorted({condition.severity for condition in conditions}),
        "seed_values": sorted({condition.seed for condition in conditions}),
        "aggregates": aggregated,
        "scenario_strata": strata,
        "interval_note": "two-sided Student-t 95% interval over frozen seeds; n=3 is diagnostic",
        "decision_gates": base_report["decision_gates"],
    }


def _case_metrics(
    posterior: dict[UUID, float],
    *,
    evaluation_target: UUID,
) -> tuple[bool, float, float]:
    ranked = sorted(posterior, key=lambda candidate: (-posterior[candidate], str(candidate)))
    top1_correct = ranked[0] == evaluation_target
    target_probability = max(posterior[evaluation_target], 1e-12)
    nll = -log(target_probability)
    brier = sum(
        (probability - (1.0 if candidate == evaluation_target else 0.0)) ** 2
        for candidate, probability in posterior.items()
    )
    return top1_correct, nll, brier


def run_controlled_noise_benchmark(
    configs: tuple[DirectionThreeNoiseConfig, ...] | None = None,
) -> dict[str, Any]:
    matrix = configs or default_controlled_noise_matrix()
    probes = tuple(
        scenario
        for scenario in default_oracle_scenarios()
        if scenario.scenario_id.endswith("_truth_probe")
        or scenario.initial_belief == OracleInitialBelief.UNKNOWN
    )
    cases: list[dict[str, Any]] = []
    metric_cases_by_condition: dict[str, list[DirectionThreeMetricCase]] = {
        config.condition_id: [] for config in matrix
    }
    for config in matrix:
        for scenario in probes:
            request, true_target, target, distractor = build_oracle_request(scenario)
            noisy = apply_direction_three_controlled_noise(
                request,
                true_target_candidate_id=target,
                distractor_candidate_id=distractor,
                config=config,
            )
            result = JointPosteriorFusion().fuse(noisy.request)
            unknown_id = next(
                candidate.candidate_id
                for candidate in noisy.request.candidates
                if candidate.kind == CandidateKind.UNKNOWN
            )
            support_miss = true_target not in result.posterior_by_candidate_id
            evaluation_target = unknown_id if support_miss else true_target
            top1_correct, nll, brier = _case_metrics(
                result.posterior_by_candidate_id,
                evaluation_target=evaluation_target,
            )
            cases.append(
                {
                    "condition_id": config.condition_id,
                    "scenario_id": scenario.scenario_id,
                    "true_target_was_retrieved": noisy.true_target_was_retrieved,
                    "evaluation_target_id": str(evaluation_target),
                    "top1_correct": top1_correct,
                    "nll": nll,
                    "brier": brier,
                    "unknown_probability": result.unknown_probability,
                    "resolution_status": result.resolution_status.value,
                    "operation_count": len(noisy.operations),
                    "operations": list(noisy.operations),
                }
            )
            metric_cases_by_condition[config.condition_id].append(
                DirectionThreeMetricCase(
                    case_id=f"{config.condition_id}:{scenario.scenario_id}",
                    posterior_by_candidate_id=result.posterior_by_candidate_id,
                    unknown_candidate_id=unknown_id,
                    true_target_candidate_id=(
                        None if support_miss or true_target == unknown_id else true_target
                    ),
                    target_is_unknown=support_miss or true_target == unknown_id,
                    resolution_status=result.resolution_status,
                    expected_resolution_status=(
                        ResolutionStatus.UNKNOWN
                        if support_miss or true_target == unknown_id
                        else ResolutionStatus.RESOLVED
                    ),
                )
            )

    summaries = []
    for config in matrix:
        condition_cases = [case for case in cases if case["condition_id"] == config.condition_id]
        metric_report = evaluate_direction_three_metrics(
            tuple(metric_cases_by_condition[config.condition_id])
        )
        summaries.append(
            {
                "condition_id": config.condition_id,
                "case_count": len(condition_cases),
                "top1_accuracy": sum(case["top1_correct"] for case in condition_cases)
                / len(condition_cases),
                "mean_nll": sum(case["nll"] for case in condition_cases) / len(condition_cases),
                "mean_brier": sum(case["brier"] for case in condition_cases) / len(condition_cases),
                "mean_unknown_probability": sum(
                    case["unknown_probability"] for case in condition_cases
                )
                / len(condition_cases),
                "support_miss_count": sum(
                    not case["true_target_was_retrieved"] for case in condition_cases
                ),
                "unified_metrics": {
                    key: value
                    for key, value in metric_report.items()
                    if key not in {"cases", "schema_name", "schema_version", "case_count"}
                },
            }
        )
    return {
        "schema_name": "cpswm.DirectionThreeControlledNoiseReport",
        "schema_version": "0.1.0",
        "maturity": "s3-2-controlled-noise-baseline",
        "condition_count": len(matrix),
        "case_count": len(cases),
        "conditions": summaries,
        "cases": cases,
        "decision_gates": [
            {
                "gate_id": "S3-DG-selection-bias-estimator",
                "status": "user_decision_deferred",
                "reason": "selection-bias correction needs an estimand and logging-policy choice",
                "unblocked_work": "raw selection probability remains part of the episode contract",
            }
        ],
    }
