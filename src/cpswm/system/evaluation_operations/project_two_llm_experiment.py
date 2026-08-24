"""D0 replay pilot for the four LLM evidence tracks and safe runtime ablations."""

from __future__ import annotations

from statistics import mean
from uuid import UUID

from pydantic import Field

from cpswm.contracts import (
    ContractModel,
    EventMechanism,
    ProjectTwoDatasetSplit,
    ProjectTwoReplayStep,
)
from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig
from cpswm.system.llm_evidence import (
    DeterministicEvidenceProvider,
    LLMEvidenceAdapter,
    LLMEvidenceCache,
    LLMEvidenceRequest,
    LLMProviderIdentity,
)

from .project_two_ablation import (
    EvaluatorNoDedupMessagePassing,
    EvaluatorNoProvenanceFirewallMessagePassing,
    IndependentEvidenceMessagePassing,
    PriorOnlyMessagePassing,
    ProjectTwoAblation,
    ProjectTwoAblationProtocol,
)
from .project_two_action_benchmark import (
    ActionCaseMetric,
    ProjectTwoActionBenchmarkV02,
    ProjectTwoActionMethod,
    _bootstrap_ci,
    _FullProjectTwoMethod,
    _locations,
    _Prediction,
)
from .project_two_dataset import ProjectTwoReplayDataset
from .project_two_tuning import (
    IndependentTuningReceipt,
    ProjectTwoExperimentalTrack,
    ProjectTwoFairTuner,
    ProjectTwoTuningCandidate,
    SealedHeldOutRunGuard,
)


class ProjectTwoLLMCaseMetric(ContractModel):
    arm_id: str
    episode_id: UUID
    action: ActionCaseMetric
    revision_precision: float = Field(ge=0.0, le=1.0)
    llm_tokens: int = Field(ge=0)
    llm_latency_ms: float = Field(ge=0.0)
    llm_cost_usd: float = Field(ge=0.0)


class ProjectTwoLLMAggregate(ContractModel):
    arm_id: str
    metric: str
    value: float
    confidence_interval_95: tuple[float, float]
    worst_group_value: float
    paired_difference_vs_no_llm: float
    effect_size: float
    multiple_comparison_correction: str = "Holm family declared; p-values unavailable at n<3"


class ProjectTwoAblationImpact(ContractModel):
    ablation: ProjectTwoAblation
    topology_cut_verified: bool
    runtime_status: str
    put_back_error_delta_vs_llm_evidence: float | None = None
    action_regret_delta_vs_llm_evidence: float | None = None


class ProjectTwoLLMExperimentReport(ContractModel):
    protocol_version: str = "project-two-llm-tuning-ablation@0.1"
    evidence_maturity: str
    validation_episode_ids: tuple[UUID, ...]
    sealed_test_episode_ids: tuple[UUID, ...]
    tuning_receipts: tuple[IndependentTuningReceipt, ...]
    cases: tuple[ProjectTwoLLMCaseMetric, ...]
    aggregates: tuple[ProjectTwoLLMAggregate, ...]
    ablation_impacts: tuple[ProjectTwoAblationImpact, ...]
    held_out_run_count: int
    claims: tuple[str, ...]


class _DirectLLMDecisionMethod:
    """Isolated baseline: proposals are actions and have no model write access."""

    def __init__(self, episode, adapter, candidate) -> None:
        self.episode = episode
        self.adapter = adapter
        self.candidate = candidate
        self.locations = _locations(episode)
        self.last = self.locations[0]
        self.unknown = 1.0
        self.revision_calls = self.project_one_requests = self.project_one_applications = 0
        self.rejected_feedback = self.unnecessary_revisions = 0
        self.project_one_rejections = 0
        self.tokens = 0
        self.latency_ms = self.cost_usd = 0.0

    def observe(self, step):
        result = self.adapter.generate(_request(self.episode, step, self.candidate))
        output = result.output
        self.tokens += output.accounting.input_tokens + output.accounting.output_tokens
        self.latency_ms += output.accounting.latency_ms
        self.cost_usd += output.accounting.cost_usd
        if result.typed_evidence.location_prior:
            self.last = UUID(
                max(
                    result.typed_evidence.location_prior,
                    key=result.typed_evidence.location_prior.get,
                )
            )
        self.unknown = output.unknown_probability

    def predict(self):
        return _Prediction(
            self.last,
            (self.last, *tuple(item for item in self.locations if item != self.last)),
            self.unknown,
        )

    def feedback(self, step):
        del step


def _request(episode, step, candidate):
    return LLMEvidenceRequest.from_replay_step(
        episode=episode,
        step=step,
        identity=LLMProviderIdentity(
            provider="offline-fixture",
            model="deterministic-evidence-provider",
            version="0.1",
        ),
        prompt_template_version=candidate.prompt_template_version,
        temperature=candidate.temperature,
        candidate_count=candidate.candidate_count,
    )


class ProjectTwoLLMExperimentPilot:
    """Runs data/control plumbing only; never claims real-LLM superiority."""

    def __init__(self, *, search_budget: int = 3) -> None:
        self.search_budget = search_budget
        self.scorer = ProjectTwoActionBenchmarkV02()

    def run(self, dataset: ProjectTwoReplayDataset) -> ProjectTwoLLMExperimentReport:
        validation = dataset.visible_episodes(ProjectTwoDatasetSplit.VALIDATION)
        test = dataset.visible_episodes(ProjectTwoDatasetSplit.TEST)
        candidates = tuple(ProjectTwoTuningCandidate.pilot(i) for i in range(self.search_budget))
        ablations = tuple(ProjectTwoAblation)
        arm_ids = tuple(track.value for track in ProjectTwoExperimentalTrack) + tuple(
            item.value for item in ablations
        )
        tuner = ProjectTwoFairTuner(search_budget=self.search_budget)

        def objective(arm, candidate):
            values = [
                self._run_case(dataset, episode, arm, candidate).action for episode in validation
            ]
            return (
                mean(item.put_back_error_rate for item in values),
                mean(item.cumulative_action_regret for item in values),
            )

        receipts = tuner.tune_all(
            arm_ids=arm_ids,
            candidates=candidates,
            validation_episode_ids=tuple(str(item.episode_id) for item in validation),
            evaluator=objective,
        )
        selected = {item.arm_id: item.selected_candidate for item in receipts}
        guard = SealedHeldOutRunGuard.freeze(
            receipts=receipts, arm_ids=arm_ids, ablations=ablations
        )
        guard.open_once(tuple(str(item.episode_id) for item in test))
        report_arms = tuple(track.value for track in ProjectTwoExperimentalTrack)
        cases = tuple(
            self._run_case(dataset, episode, arm, selected[arm])
            for episode in test
            for arm in report_arms
        )
        aggregates = self._aggregate(cases, report_arms)
        reference = {
            item.episode_id: item.action
            for item in cases
            if item.arm_id == ProjectTwoExperimentalTrack.LLM_AS_EVIDENCE.value
        }
        protocol = ProjectTwoAblationProtocol()
        impacts = []
        for ablation in ablations:
            outcomes = [
                self._run_case(dataset, episode, ablation.value, selected[ablation.value]).action
                for episode in test
            ]
            impacts.append(
                ProjectTwoAblationImpact(
                    ablation=ablation,
                    topology_cut_verified=protocol.verify_cut(
                        ablation, protocol.topology_for(ablation)
                    ),
                    runtime_status="executed_on_d0_evaluator_sandbox",
                    put_back_error_delta_vs_llm_evidence=mean(
                        item.put_back_error_rate - reference[item.episode_id].put_back_error_rate
                        for item in outcomes
                    ),
                    action_regret_delta_vs_llm_evidence=mean(
                        item.cumulative_action_regret
                        - reference[item.episode_id].cumulative_action_regret
                        for item in outcomes
                    ),
                )
            )
        return ProjectTwoLLMExperimentReport(
            evidence_maturity="D0 deterministic adapter fixture; no external LLM/VLM invoked",
            validation_episode_ids=tuple(item.episode_id for item in validation),
            sealed_test_episode_ids=tuple(item.episode_id for item in test),
            tuning_receipts=receipts,
            cases=cases,
            aggregates=aggregates,
            ablation_impacts=tuple(impacts),
            held_out_run_count=1,
            claims=(
                "The pilot validates typed evidence, cache, tuning, and replay plumbing only.",
                "No synthetic result supports real-world or paper-level superiority.",
                "All structural cuts execute in an evaluator-only sandbox.",
            ),
        )

    def _run_case(self, dataset, episode, arm, candidate):
        adapter = LLMEvidenceAdapter(
            provider=DeterministicEvidenceProvider(), cache=LLMEvidenceCache()
        )
        tokens = 0
        latency = cost = 0.0

        def llm_transform(step: ProjectTwoReplayStep) -> ProjectTwoReplayStep:
            nonlocal tokens, latency, cost
            result = adapter.generate(_request(episode, step, candidate))
            if not result.from_cache:
                accounting = result.output.accounting
                tokens += accounting.input_tokens + accounting.output_tokens
                latency += accounting.latency_ms
                cost += accounting.cost_usd
            bundle = result.typed_evidence
            actor = bundle.actor
            mechanism = bundle.mechanism
            role = bundle.role
            if arm == ProjectTwoAblation.NO_UNKNOWN_ACTOR.value:
                posterior = {
                    key: value
                    for key, value in actor.actor_posterior.items()
                    if key != "unknown_actor"
                }
                total = sum(posterior.values())
                posterior = {key: value / total for key, value in posterior.items()}
                actor = actor.model_copy(
                    update={
                        "actor_posterior": posterior,
                        "reference_actor_prior": {key: 1.0 / len(posterior) for key in posterior},
                    }
                )
            if arm == ProjectTwoAblation.NO_UNKNOWN_MECHANISM.value:
                posterior = {
                    key: value
                    for key, value in mechanism.mechanism_posterior.items()
                    if key is not EventMechanism.UNKNOWN_MECHANISM
                }
                total = sum(posterior.values())
                posterior = {key: value / total for key, value in posterior.items()}
                mechanism = mechanism.model_copy(
                    update={
                        "mechanism_posterior": posterior,
                        "reference_mechanism_prior": {
                            key: 1.0 / len(posterior) for key in posterior
                        },
                    }
                )
            if arm == ProjectTwoAblation.NO_MECHANISM_ROLE_REVISION.value:
                mechanism = None
                role = None
            return step.model_copy(
                update={
                    "actor_evidence": actor,
                    "mechanism_evidence": mechanism,
                    "ordered_role_evidence": role,
                }
            )

        no_llm = {
            ProjectTwoExperimentalTrack.NO_LLM_CORE.value,
            ProjectTwoAblation.NO_LLM.value,
        }
        direct = {
            ProjectTwoExperimentalTrack.LLM_DIRECT_DECISION.value,
            ProjectTwoAblation.LLM_DIRECT_DECISION.value,
            ProjectTwoAblation.LLM_PRIOR_ONLY.value,
        }
        if arm in direct:
            state = _DirectLLMDecisionMethod(episode, adapter, candidate)
            metric = self.scorer.evaluate_custom_state(dataset, episode, state)
            tokens, latency, cost = state.tokens, state.latency_ms, state.cost_usd
        else:
            feedback_mode = {
                ProjectTwoAblation.NO_EXECUTION_FEEDBACK_RETURN.value: "none",
                ProjectTwoAblation.FAILURE_ONLY_FEEDBACK.value: "failure_only",
                ProjectTwoAblation.SUCCESS_ONLY_FEEDBACK.value: "success_only",
            }.get(arm, "success_and_failure")
            # Oracle upper bound is deliberately evaluator-only. The D0 pilot
            # uses the benchmark's existing oracle scorer, never an LLM request.
            if arm == ProjectTwoExperimentalTrack.ORACLE_EVIDENCE.value:
                metric = self.scorer._evaluate_episode(
                    dataset, episode, ProjectTwoActionMethod.ORACLE, {}
                )
            else:
                message_passing = None
                if arm == ProjectTwoAblation.NO_PCHMP_JOINT_PROPAGATION.value:
                    message_passing = PriorOnlyMessagePassing()
                elif arm == ProjectTwoAblation.INDEPENDENT_HYPOTHESIS_SCORING.value:
                    message_passing = IndependentEvidenceMessagePassing()
                elif arm == ProjectTwoAblation.NO_PROVENANCE_FIREWALL.value:
                    message_passing = EvaluatorNoProvenanceFirewallMessagePassing()
                elif arm == ProjectTwoAblation.NO_DEDUPLICATION.value:
                    message_passing = EvaluatorNoDedupMessagePassing()
                loop_config = PrototypeLoopConfig(
                    owner_evidence_threshold=candidate.rgrc_write_threshold,
                    minimum_baseline_observations=(
                        10_000 if arm == ProjectTwoAblation.NO_CCRR_MULTI_REGIME_MEMORY.value else 3
                    ),
                    habit_change_probability_threshold=candidate.ccrr_create_threshold,
                    transient_disturbance_probability_threshold=(candidate.ccrr_stay_threshold),
                )
                revision_strategy = "orrer"
                if arm == ProjectTwoAblation.ORRER_IN_PLACE_OVERWRITE.value:
                    revision_strategy = "in_place"
                elif arm == ProjectTwoAblation.ORRER_FULL_RERUN.value:
                    revision_strategy = "full_rerun"
                state = _FullProjectTwoMethod(
                    episode,
                    owner_threshold=candidate.rgrc_write_threshold,
                    evidence_transform=None if arm in no_llm else llm_transform,
                    feedback_mode=feedback_mode,
                    apply_project_one_revisions=(
                        arm != ProjectTwoAblation.NO_PROJECT_ONE_RETRACT_CORRECT.value
                    ),
                    unresolved_probability=(
                        0.0
                        if arm == ProjectTwoAblation.NO_UNRESOLVED_MASS.value
                        else candidate.unresolved_prior
                    ),
                    message_passing=message_passing,
                    loop_config=loop_config,
                    rgrc_gate_enabled=(arm != ProjectTwoAblation.NO_RGRC_GATE.value),
                    revision_strategy=revision_strategy,
                    include_unknown_actor=(arm != ProjectTwoAblation.NO_UNKNOWN_ACTOR.value),
                )
                metric = self.scorer.evaluate_custom_state(dataset, episode, state)
        precision = (
            metric.project_one_stat_applications / metric.project_one_stat_requests
            if metric.project_one_stat_requests
            else 1.0
        )
        return ProjectTwoLLMCaseMetric(
            arm_id=arm,
            episode_id=episode.episode_id,
            action=metric,
            revision_precision=precision,
            llm_tokens=tokens,
            llm_latency_ms=latency,
            llm_cost_usd=cost,
        )

    @staticmethod
    def _aggregate(cases, arms):
        metric_names = (
            "put_back_error_rate",
            "search_success_rate",
            "cumulative_action_regret",
            "mean_search_cost",
            "owner_habit_contamination",
            "incorrect_statistic_recovery_cost",
            "unknown_calibration_brier",
            "revision_precision",
            "llm_tokens",
            "llm_latency_ms",
            "llm_cost_usd",
        )

        def metric_value(item, metric):
            if hasattr(item.action, metric):
                return float(getattr(item.action, metric))
            return float(getattr(item, metric))

        no_llm = {
            metric: [
                metric_value(item, metric)
                for item in cases
                if item.arm_id == ProjectTwoExperimentalTrack.NO_LLM_CORE.value
            ]
            for metric in metric_names
        }
        output = []
        for arm in arms:
            for metric in metric_names:
                values = [metric_value(item, metric) for item in cases if item.arm_id == arm]
                paired = [value - base for value, base in zip(values, no_llm[metric], strict=True)]
                output.append(
                    ProjectTwoLLMAggregate(
                        arm_id=arm,
                        metric=metric,
                        value=mean(values),
                        confidence_interval_95=_bootstrap_ci(values),
                        worst_group_value=max(values),
                        paired_difference_vs_no_llm=mean(paired),
                        effect_size=mean(paired),
                    )
                )
        return tuple(output)


__all__ = [
    "ProjectTwoAblationImpact",
    "ProjectTwoLLMCaseMetric",
    "ProjectTwoLLMExperimentPilot",
    "ProjectTwoLLMExperimentReport",
]
