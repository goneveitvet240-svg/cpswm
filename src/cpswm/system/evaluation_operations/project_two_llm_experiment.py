"""D0 replay pilot for the four LLM evidence tracks and safe runtime ablations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from statistics import mean
from typing import Any
from uuid import UUID

from pydantic import Field, computed_field, model_validator

from cpswm.contracts import (
    ContractModel,
    EventMechanism,
    EventMechanismEvidence,
    LLMIntegrationRole,
    LLMInvocationProvenance,
    ProjectTwoDatasetSplit,
    ProjectTwoReplayEpisode,
    ProjectTwoReplayStep,
    RoleBindingEvidence,
)
from cpswm.system.continual.project_one_regime_loop import PrototypeLoopConfig
from cpswm.system.llm_evidence import (
    CandidateProposalBundle,
    DeterministicEvidenceProvider,
    LLMCallAuditReceipt,
    LLMEvidenceAdapter,
    LLMEvidenceCache,
    LLMEvidenceRequest,
    LLMFusionPermission,
    LLMProbabilitySemantics,
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
    _ReplayMethod,
)
from .project_two_dataset import ProjectTwoReplayDataset
from .project_two_tuning import (
    IndependentTuningReceipt,
    ProjectTwoExperimentalTrack,
    ProjectTwoFairTuner,
    ProjectTwoTuningCandidate,
    RuntimeParameterInjectionReceipt,
    SealedHeldOutRunGuard,
    build_runtime_parameter_receipt,
)


class ProjectTwoLLMCaseMetric(ContractModel):
    arm_id: str
    episode_id: UUID
    action: ActionCaseMetric
    revision_precision: float = Field(ge=0.0, le=1.0)
    request_application_rate: float = Field(ge=0.0, le=1.0)
    llm_tokens: int = Field(ge=0)
    llm_latency_ms: float = Field(ge=0.0)
    llm_cost_usd: float = Field(ge=0.0)
    llm_provenance: tuple[LLMInvocationProvenance, ...] = ()
    llm_call_audits: tuple[LLMCallAuditReceipt, ...] = ()
    runtime_parameter_receipt: RuntimeParameterInjectionReceipt | None = None
    runtime_module_trace: tuple[str, ...] = ()


class ProjectTwoLLMAggregate(ContractModel):
    arm_id: str
    metric: str
    value: float
    confidence_interval_95: tuple[float, float]
    worst_group_value: float
    paired_difference_vs_no_llm: float
    effect_size: float
    p_value: float | None = Field(default=None, ge=0.0, le=1.0)
    holm_adjusted_p_value: float | None = Field(default=None, ge=0.0, le=1.0)
    holm_correction_executed: bool = False
    multiple_comparison_correction: str = "unavailable: valid p-values were not computed"

    @model_validator(mode="after")
    def _honest_holm_status(self) -> ProjectTwoLLMAggregate:
        if self.holm_correction_executed and (
            self.p_value is None or self.holm_adjusted_p_value is None
        ):
            raise ValueError("Holm correction requires a valid raw and adjusted p-value")
        if not self.holm_correction_executed and self.holm_adjusted_p_value is not None:
            raise ValueError("adjusted p-value cannot exist when Holm was not executed")
        return self


class ProjectTwoAblationImpact(ContractModel):
    ablation: ProjectTwoAblation
    topology_cut_verified: bool
    runtime_status: str
    put_back_error_delta_vs_llm_evidence: float | None = None
    action_regret_delta_vs_llm_evidence: float | None = None
    runtime_proof: tuple[str, ...] = Field(min_length=1)


class ReceiptMetricPolicy(ContractModel):
    semantics_validated: bool
    validation_scenario: str = Field(min_length=1)
    paper_result_eligible: bool = False
    operational_metrics: tuple[str, ...] = Field(min_length=1)


class PoweredMechanismStage(StrEnum):
    D0 = "powered_d0"
    D1 = "powered_d1"


class PoweredMechanismCompletionReceipt(ContractModel):
    stage: PoweredMechanismStage
    artifact_uri: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    power_analysis_uri: str = Field(min_length=1)
    power_analysis_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    protocol_version: str = Field(min_length=1)
    completion_authority: str = Field(min_length=1)
    observed_sample_size: int = Field(gt=0)
    required_sample_size: int = Field(gt=0)

    @model_validator(mode="after")
    def _powered(self) -> PoweredMechanismCompletionReceipt:
        if self.observed_sample_size < self.required_sample_size:
            raise ValueError("completion receipt cannot claim an underpowered artifact")
        return self

    @computed_field
    def receipt_sha256(self) -> str:
        payload = {
            "stage": self.stage.value,
            "artifact_uri": self.artifact_uri,
            "artifact_sha256": self.artifact_sha256,
            "power_analysis_uri": self.power_analysis_uri,
            "power_analysis_sha256": self.power_analysis_sha256,
            "protocol_version": self.protocol_version,
            "completion_authority": self.completion_authority,
            "observed_sample_size": self.observed_sample_size,
            "required_sample_size": self.required_sample_size,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class LLMMechanismProgressionGate(ContractModel):
    powered_d0_receipt: PoweredMechanismCompletionReceipt | None = None
    powered_d1_receipt: PoweredMechanismCompletionReceipt | None = None

    @model_validator(mode="after")
    def _ordered_maturity(self) -> LLMMechanismProgressionGate:
        if (
            self.powered_d0_receipt is not None
            and self.powered_d0_receipt.stage is not PoweredMechanismStage.D0
        ):
            raise ValueError("powered_d0_receipt must bind a D0 artifact")
        if (
            self.powered_d1_receipt is not None
            and self.powered_d1_receipt.stage is not PoweredMechanismStage.D1
        ):
            raise ValueError("powered_d1_receipt must bind a D1 artifact")
        return self

    @computed_field
    def d2_allowed(self) -> bool:
        return self.powered_d0_receipt is not None and self.powered_d1_receipt is not None


class ProjectTwoLLMExperimentReport(ContractModel):
    protocol_version: str = "project-two-llm-tuning-ablation@0.2"
    evidence_maturity: str
    validation_episode_ids: tuple[UUID, ...]
    sealed_test_episode_ids: tuple[UUID, ...]
    tuning_receipts: tuple[IndependentTuningReceipt, ...]
    cases: tuple[ProjectTwoLLMCaseMetric, ...]
    aggregates: tuple[ProjectTwoLLMAggregate, ...]
    ablation_impacts: tuple[ProjectTwoAblationImpact, ...]
    held_out_run_count: int
    role_comparison: dict[str, str]
    receipt_metric_policy: ReceiptMetricPolicy
    progression_gate: LLMMechanismProgressionGate
    claims: tuple[str, ...]


class _DirectLLMDecisionMethod:
    """Isolated baseline: proposals are actions and have no model write access."""

    def __init__(
        self,
        episode: ProjectTwoReplayEpisode,
        adapter: LLMEvidenceAdapter,
        candidate: ProjectTwoTuningCandidate,
    ) -> None:
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
        self.provenance: list[LLMInvocationProvenance] = []
        self.call_audits: list[LLMCallAuditReceipt] = []

    def observe(self, step: ProjectTwoReplayStep) -> None:
        result = self.adapter.generate(
            _request(
                self.episode,
                step,
                self.candidate,
                role=LLMIntegrationRole.LLM_DIRECT_BASELINE,
            )
        )
        self.call_audits.append(result.call_audit)
        self.tokens += result.accounting.input_tokens + result.accounting.output_tokens
        self.latency_ms += result.accounting.latency_ms
        self.cost_usd += result.accounting.cost_usd
        if not result.from_cache:
            self.provenance.append(result.invocation_provenance)
        proposal = result.typed_bundle
        if not isinstance(proposal, CandidateProposalBundle):
            raise TypeError("LLM direct baseline requires a candidate proposal bundle")
        proposed_locations = tuple(
            item.value for item in proposal.candidates if item.kind.value == "location"
        )
        if proposed_locations:
            self.last = UUID(proposed_locations[0])
        self.unknown = result.unresolved_event_mass

    def predict(self) -> _Prediction:
        return _Prediction(
            self.last,
            (self.last, *tuple(item for item in self.locations if item != self.last)),
            self.unknown,
        )

    def feedback(self, step: ProjectTwoReplayStep) -> None:
        del step


_LLM_PARAMETERS = {"prompt_template_version", "temperature", "candidate_count"}
_STRUCTURAL_PARAMETERS = set(ProjectTwoTuningCandidate.model_fields) - {
    "index",
    *_LLM_PARAMETERS,
}


def _runtime_parameter_receipt(
    arm: str,
    candidate: ProjectTwoTuningCandidate,
    state: Any,
    *,
    tokens: int,
) -> RuntimeParameterInjectionReceipt:
    if isinstance(state, _DirectLLMDecisionMethod):
        active = {*_LLM_PARAMETERS, "action_utility_threshold"}
        bindings = {
            "prompt_template_version": (
                "LLMEvidenceRequest",
                candidate.prompt_template_version,
                {
                    "provider_calls": getattr(state.adapter.provider, "invocation_count", 0),
                    "tokens": tokens,
                },
            ),
            "temperature": (
                "LLMEvidenceRequest",
                candidate.temperature,
                {
                    "provider_calls": getattr(state.adapter.provider, "invocation_count", 0),
                    "tokens": tokens,
                },
            ),
            "candidate_count": (
                "LLMEvidenceRequest",
                candidate.candidate_count,
                {
                    "provider_calls": getattr(state.adapter.provider, "invocation_count", 0),
                    "tokens": tokens,
                },
            ),
            "action_utility_threshold": (
                "DirectLLMActionSelector",
                candidate.action_utility_threshold,
                {"last_location": str(state.last), "unknown": state.unknown},
            ),
        }
    else:
        active = set(_STRUCTURAL_PARAMETERS)
        llm_active = arm not in {
            ProjectTwoExperimentalTrack.NO_LLM_CORE.value,
            ProjectTwoAblation.NO_LLM.value,
        }
        if llm_active:
            active |= _LLM_PARAMETERS
        observation = {
            "observations": state.spine.observation_count,
            "revisions": state.revision_calls,
            "requests": state.project_one_requests,
            "snapshot": str(state.spine.current_snapshot.snapshot_id),
        }
        config = state.loop_config
        bindings = {
            "likelihood_calibration": (
                "ActionOutcomeLikelihoodModel",
                state.likelihood_calibration,
                observation,
            ),
            "actor_evidence_weight": (
                "CHEH.actor_evidence",
                state.actor_evidence_weight,
                observation,
            ),
            "mechanism_evidence_weight": (
                "CHEH.mechanism_evidence",
                state.mechanism_evidence_weight,
                observation,
            ),
            "role_evidence_weight": ("CHEH.role_evidence", state.role_evidence_weight, observation),
            "unresolved_prior": (
                "CHEH.open_world_prior",
                state.unresolved_probability,
                observation,
            ),
            "unknown_actor_prior": ("CHEH.actor_prior", state.unknown_actor_prior, observation),
            "unknown_mechanism_prior": (
                "CHEH.mechanism_prior",
                state.unknown_mechanism_prior,
                observation,
            ),
            "orrer_retraction_threshold": ("ORRER", state.orrer_retraction_threshold, observation),
            "orrer_reactivation_threshold": (
                "ORRER",
                state.orrer_reactivation_threshold,
                observation,
            ),
            "pchmp_weight": ("PCHMP", state.pchmp_evidence_weight, observation),
            "bocpd_hazard": (
                "JointCauseFactorizedBOCPD",
                config.bocpd_hazard_probability,
                observation,
            ),
            "ccrr_create_threshold": (
                "CCRR",
                config.habit_change_probability_threshold,
                observation,
            ),
            "ccrr_reactivate_threshold": ("CCRR", config.ccrr_similarity_threshold, observation),
            "ccrr_stay_threshold": ("CCRR", config.ccrr_attribution_margin, observation),
            "rgrc_write_threshold": (
                "RGRC.write_gate",
                config.owner_evidence_threshold,
                observation,
            ),
            "rgrc_quarantine_threshold": (
                "RGRC.quarantine_gate",
                config.transient_disturbance_probability_threshold,
                observation,
            ),
            "rgrc_retract_threshold": (
                "RGRC.retract_gate",
                config.feedback_decision_margin,
                observation,
            ),
            "action_utility_threshold": (
                "TaskPlanner.utility_selector",
                state.action_utility_threshold,
                observation,
            ),
        }
        if llm_active:
            bindings.update(
                {
                    "prompt_template_version": (
                        "LLMEvidenceRequest",
                        candidate.prompt_template_version,
                        {"tokens": tokens},
                    ),
                    "temperature": (
                        "LLMEvidenceRequest",
                        candidate.temperature,
                        {"tokens": tokens},
                    ),
                    "candidate_count": (
                        "LLMEvidenceRequest",
                        candidate.candidate_count,
                        {"tokens": tokens},
                    ),
                }
            )
    return build_runtime_parameter_receipt(
        arm_id=arm,
        candidate=candidate,
        bindings=bindings,
        declared_parameters=active,
    )


def _runtime_module_trace(arm: str, state: Any | None, *, tokens: int) -> tuple[str, ...]:
    if isinstance(state, _DirectLLMDecisionMethod):
        return (
            "LLM_direct_decision:executed",
            "CHEH:skipped",
            "PCHMP:skipped",
            "ORRER:skipped",
            "ProjectOne_statistics:skipped",
        )
    if state is None:
        return ("oracle_evaluator:executed", "model_inference:skipped")
    message_passing = state.message_passing
    unknown_mechanism = "cut" if arm == ProjectTwoAblation.NO_UNKNOWN_MECHANISM.value else "enabled"
    pchmp_joint = "cut" if isinstance(message_passing, PriorOnlyMessagePassing) else "executed"
    hypothesis_scoring = (
        "independent" if isinstance(message_passing, IndependentEvidenceMessagePassing) else "joint"
    )
    mechanism_role_revision = (
        "cut" if arm == ProjectTwoAblation.NO_MECHANISM_ROLE_REVISION.value else "executed"
    )
    provenance_firewall = (
        "cut_in_evaluator_sandbox"
        if isinstance(message_passing, EvaluatorNoProvenanceFirewallMessagePassing)
        else "executed"
    )
    deduplication = (
        "cut_in_evaluator_sandbox"
        if isinstance(message_passing, EvaluatorNoDedupMessagePassing)
        else "executed"
    )
    ccrr_multi_regime = (
        "cut" if state.loop_config.minimum_baseline_observations >= 10_000 else "executed"
    )
    llm_prior_only = (
        "executed_full_project_two" if state.actor_prior_transform is not None else "inactive"
    )
    return (
        f"feedback_mode:{state.feedback_mode}",
        f"execution_feedback:{'executed' if state.revision_calls else 'skipped'}",
        f"unknown_actor:{'enabled' if state.include_unknown_actor else 'cut'}",
        f"unknown_mechanism:{unknown_mechanism}",
        f"unresolved_mass:{'cut' if state.unresolved_probability == 0.0 else 'enabled'}",
        f"PCHMP_joint:{pchmp_joint}",
        f"hypothesis_scoring:{hypothesis_scoring}",
        f"ORRER:{state.revision_strategy}",
        f"mechanism_role_revision:{mechanism_role_revision}",
        f"provenance_firewall:{provenance_firewall}",
        f"deduplication:{deduplication}",
        f"ProjectOne_retract_correct:{'executed' if state.apply_project_one_revisions else 'cut'}",
        f"CCRR_multi_regime:{ccrr_multi_regime}",
        f"RGRC_gate:{'executed' if state.rgrc_gate_enabled else 'cut'}",
        f"LLM:{'executed' if tokens else 'cut'}",
        f"LLM_prior_only:{llm_prior_only}",
    )


def _request(
    episode: ProjectTwoReplayEpisode,
    step: ProjectTwoReplayStep,
    candidate: ProjectTwoTuningCandidate,
    *,
    role: LLMIntegrationRole = LLMIntegrationRole.STRUCTURE_TWO_EVIDENCE_PROVIDER,
) -> LLMEvidenceRequest:
    posterior_mode = role is LLMIntegrationRole.STRUCTURE_TWO_EVIDENCE_PROVIDER
    known_actors = tuple(actor for actor in episode.resident_actor_keys if actor != "unknown_actor")
    actor_prior = (
        dict(step.actor_evidence.reference_actor_prior)
        if step.actor_evidence
        else {
            **{actor: 0.8 / max(len(known_actors), 1) for actor in known_actors},
            "unknown_actor": 0.2,
        }
    )
    mechanism_prior = (
        {
            key.value: value
            for key, value in step.mechanism_evidence.reference_mechanism_prior.items()
        }
        if step.mechanism_evidence
        else {
            "direct_relocation": 0.45,
            "handoff_relocation": 0.35,
            "unknown_mechanism": 0.2,
        }
    )
    role_prior = (
        dict(step.ordered_role_evidence.reference_ordered_role_prior)
        if step.ordered_role_evidence
        else {
            f"{known_actors[0]}=>{known_actors[1]}": 0.6,
            f"{known_actors[1]}=>{known_actors[0]}": 0.4,
        }
    )
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
        expected_probability_semantics=(
            LLMProbabilitySemantics.POSTERIOR_RELATIVE_TO_REFERENCE_PRIOR
            if posterior_mode
            else LLMProbabilitySemantics.PROPOSAL_ONLY
        ),
        authorized_fusion_permission=(
            LLMFusionPermission.REFERENCE_PRIOR_LIKELIHOOD_RATIO
            if posterior_mode
            else LLMFusionPermission.CANDIDATE_GENERATION_ONLY
        ),
        reference_actor_prior=actor_prior if posterior_mode else None,
        reference_mechanism_prior=mechanism_prior if posterior_mode else None,
        reference_ordered_role_prior=role_prior if posterior_mode else None,
        reference_prior_snapshot_id=step.step_id if posterior_mode else None,
        role=role,
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
        validation_runtime_receipts: dict[tuple[str, int], UUID] = {}

        def objective(arm: str, candidate: ProjectTwoTuningCandidate) -> tuple[float, float]:
            cases = [self._run_case(dataset, episode, arm, candidate) for episode in validation]
            runtime_receipt = next(
                (
                    item.runtime_parameter_receipt
                    for item in cases
                    if item.runtime_parameter_receipt
                ),
                None,
            )
            if runtime_receipt is not None:
                validation_runtime_receipts[(arm, candidate.index)] = runtime_receipt.receipt_id
            values = [item.action for item in cases]
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
        finalized_receipts = []
        for receipt in receipts:
            ids = tuple(
                validation_runtime_receipts[(receipt.arm_id, candidate.index)]
                for candidate in candidates
                if (receipt.arm_id, candidate.index) in validation_runtime_receipts
            )
            if receipt.arm_id == ProjectTwoExperimentalTrack.ORACLE_EVIDENCE.value:
                finalized_receipts.append(
                    receipt.model_copy(
                        update={
                            "runtime_parameter_status": "not_applicable_fixed_oracle",
                            "runtime_candidate_receipt_ids": (),
                        }
                    )
                )
            else:
                if len(ids) != self.search_budget:
                    raise RuntimeError(
                        f"arm {receipt.arm_id} lacks a runtime receipt for every candidate"
                    )
                finalized_receipts.append(
                    receipt.model_copy(
                        update={
                            "runtime_parameter_status": "injected",
                            "runtime_candidate_receipt_ids": ids,
                        }
                    )
                )
        receipts = tuple(finalized_receipts)
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
            ablation_cases = [
                self._run_case(dataset, episode, ablation.value, selected[ablation.value])
                for episode in test
            ]
            outcomes = [item.action for item in ablation_cases]
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
                    runtime_proof=tuple(
                        proof for item in ablation_cases for proof in item.runtime_module_trace
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
            role_comparison={
                "no_llm": ProjectTwoExperimentalTrack.NO_LLM_CORE.value,
                "llm_prior_only": ProjectTwoExperimentalTrack.LLM_PRIOR_ONLY.value,
                "llm_evidence": ProjectTwoExperimentalTrack.LLM_AS_EVIDENCE.value,
                "llm_direct": ProjectTwoExperimentalTrack.LLM_DIRECT_DECISION.value,
            },
            receipt_metric_policy=ReceiptMetricPolicy(
                semantics_validated=True,
                validation_scenario="delayed-correction-ccrr-rejection@0.2",
                paper_result_eligible=False,
                operational_metrics=(
                    "project_one_stat_applications",
                    "project_one_stat_rejections",
                    "project_one_stat_deferred",
                    "project_one_stat_replay_noops",
                    "request_application_rate",
                ),
            ),
            progression_gate=LLMMechanismProgressionGate(),
            claims=(
                "The pilot validates typed evidence, cache, tuning, and replay plumbing only.",
                "No synthetic result supports real-world or paper-level superiority.",
                "Receipt application/rejection/defer counts are operational diagnostics, "
                "not paper outcomes.",
                "Powered D0 and D1 mechanism tests are required before D2.",
                "All structural cuts execute in an evaluator-only sandbox.",
            ),
        )

    def _run_case(
        self,
        dataset: ProjectTwoReplayDataset,
        episode: ProjectTwoReplayEpisode,
        arm: str,
        candidate: ProjectTwoTuningCandidate,
    ) -> ProjectTwoLLMCaseMetric:
        adapter = LLMEvidenceAdapter(
            provider=DeterministicEvidenceProvider(), cache=LLMEvidenceCache()
        )
        state: _ReplayMethod | None = None
        tokens = 0
        latency = cost = 0.0
        provenance: list[LLMInvocationProvenance] = []
        call_audits: list[LLMCallAuditReceipt] = []

        def llm_transform(step: ProjectTwoReplayStep) -> ProjectTwoReplayStep:
            nonlocal tokens, latency, cost
            result = adapter.generate(_request(episode, step, candidate))
            call_audits.append(result.call_audit)
            if not result.from_cache:
                accounting = result.accounting
                tokens += accounting.input_tokens + accounting.output_tokens
                latency += accounting.latency_ms
                cost += accounting.cost_usd
                provenance.append(result.invocation_provenance)
            bundle = result.typed_evidence
            assert bundle is not None
            actor = bundle.actor
            mechanism: EventMechanismEvidence | None = bundle.mechanism
            role: RoleBindingEvidence | None = bundle.role
            if mechanism is None or role is None:
                raise TypeError("typed evidence bundle requires mechanism and role evidence")
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

        def llm_prior_transform(
            step: ProjectTwoReplayStep, prior: Mapping[str, float]
        ) -> Mapping[str, float]:
            nonlocal tokens, latency, cost
            result = adapter.generate(_request(episode, step, candidate))
            call_audits.append(result.call_audit)
            if not result.from_cache:
                accounting = result.accounting
                tokens += accounting.input_tokens + accounting.output_tokens
                latency += accounting.latency_ms
                cost += accounting.cost_usd
                provenance.append(result.invocation_provenance)
            bundle = result.typed_evidence
            assert bundle is not None
            proposed = bundle.actor.actor_posterior
            values = {key: proposed.get(key, prior[key]) for key in prior}
            total = sum(values.values())
            return {key: value / total for key, value in values.items()}

        no_llm = {
            ProjectTwoExperimentalTrack.NO_LLM_CORE.value,
            ProjectTwoAblation.NO_LLM.value,
        }
        direct = {
            ProjectTwoExperimentalTrack.LLM_DIRECT_DECISION.value,
            ProjectTwoAblation.LLM_DIRECT_DECISION.value,
        }
        if arm in direct:
            state = _DirectLLMDecisionMethod(episode, adapter, candidate)
            metric = self.scorer.evaluate_custom_state(dataset, episode, state)
            tokens, latency, cost = state.tokens, state.latency_ms, state.cost_usd
            provenance = state.provenance
            call_audits = state.call_audits
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
                message_passing: Any | None = None
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
                    transient_disturbance_probability_threshold=(
                        candidate.rgrc_quarantine_threshold
                    ),
                    feedback_decision_margin=candidate.rgrc_retract_threshold,
                    bocpd_hazard_probability=candidate.bocpd_hazard,
                    ccrr_similarity_threshold=candidate.ccrr_reactivate_threshold,
                    ccrr_attribution_margin=candidate.ccrr_stay_threshold,
                )
                revision_strategy = "orrer"
                if arm == ProjectTwoAblation.ORRER_IN_PLACE_OVERWRITE.value:
                    revision_strategy = "in_place"
                elif arm == ProjectTwoAblation.ORRER_FULL_RERUN.value:
                    revision_strategy = "full_rerun"
                state = _FullProjectTwoMethod(
                    episode,
                    owner_threshold=candidate.rgrc_write_threshold,
                    evidence_transform=(
                        None
                        if arm in no_llm
                        or arm
                        in {
                            ProjectTwoExperimentalTrack.LLM_PRIOR_ONLY.value,
                            ProjectTwoAblation.LLM_PRIOR_ONLY.value,
                        }
                        else llm_transform
                    ),
                    actor_prior_transform=(
                        llm_prior_transform
                        if arm
                        in {
                            ProjectTwoExperimentalTrack.LLM_PRIOR_ONLY.value,
                            ProjectTwoAblation.LLM_PRIOR_ONLY.value,
                        }
                        else None
                    ),
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
                    likelihood_calibration=candidate.likelihood_calibration,
                    actor_evidence_weight=candidate.actor_evidence_weight,
                    mechanism_evidence_weight=candidate.mechanism_evidence_weight,
                    role_evidence_weight=candidate.role_evidence_weight,
                    pchmp_evidence_weight=candidate.pchmp_weight,
                    unknown_actor_prior=candidate.unknown_actor_prior,
                    unknown_mechanism_prior=candidate.unknown_mechanism_prior,
                    orrer_retraction_threshold=candidate.orrer_retraction_threshold,
                    orrer_reactivation_threshold=candidate.orrer_reactivation_threshold,
                    action_utility_threshold=candidate.action_utility_threshold,
                )
                metric = self.scorer.evaluate_custom_state(dataset, episode, state)
        truth = dataset.truth_for(episode.episode_id)
        truth_by_feedback = {
            feedback.metadata.record_id: truth.truth_by_step[step.step_id]
            for step in episode.steps
            for feedback in step.execution_feedback
        }
        revision_matches = []
        for trace in metric.revision_action_traces:
            target = truth_by_feedback.get(trace.feedback_record_id)
            if target is None:
                continue
            actor = max(trace.actor_posterior_after, key=lambda item: item.probability).key
            mechanism = max(trace.mechanism_posterior_after, key=lambda item: item.probability).key
            location = (
                max(trace.location_posterior_after, key=lambda item: item.probability).key
                if trace.location_posterior_after
                else None
            )
            revision_matches.append(
                actor == target.true_actor
                and mechanism == target.true_mechanism.value
                and (location is None or location == str(target.true_location))
            )
        precision = sum(revision_matches) / len(revision_matches) if revision_matches else 0.0
        return ProjectTwoLLMCaseMetric(
            arm_id=arm,
            episode_id=episode.episode_id,
            action=metric,
            revision_precision=precision,
            request_application_rate=(
                metric.project_one_stat_applications / metric.project_one_stat_requests
                if metric.project_one_stat_requests
                else 0.0
            ),
            llm_tokens=tokens,
            llm_latency_ms=latency,
            llm_cost_usd=cost,
            llm_provenance=tuple(provenance),
            llm_call_audits=tuple(call_audits),
            runtime_parameter_receipt=(
                None
                if state is None
                else _runtime_parameter_receipt(arm, candidate, state, tokens=tokens)
            ),
            runtime_module_trace=_runtime_module_trace(arm, state, tokens=tokens),
        )

    @staticmethod
    def _aggregate(
        cases: Sequence[ProjectTwoLLMCaseMetric], arms: Sequence[str]
    ) -> tuple[ProjectTwoLLMAggregate, ...]:
        metric_names = (
            "put_back_error_rate",
            "search_success_rate",
            "cumulative_action_regret",
            "mean_search_cost",
            "mean_search_path_length",
            "mean_search_time_seconds",
            "owner_habit_contamination",
            "incorrect_statistic_recovery_cost",
            "late_feedback_recovery_latency",
            "unknown_calibration_brier",
            "revision_precision",
            "llm_tokens",
            "llm_latency_ms",
            "llm_cost_usd",
        )

        def metric_value(item: ProjectTwoLLMCaseMetric, metric: str) -> float:
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
        output: list[ProjectTwoLLMAggregate] = []
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
    "LLMMechanismProgressionGate",
    "PoweredMechanismCompletionReceipt",
    "PoweredMechanismStage",
    "ProjectTwoAblationImpact",
    "ProjectTwoLLMCaseMetric",
    "ProjectTwoLLMExperimentPilot",
    "ProjectTwoLLMExperimentReport",
    "ReceiptMetricPolicy",
]
