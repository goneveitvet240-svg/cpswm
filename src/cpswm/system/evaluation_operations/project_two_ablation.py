"""Declared structural cuts for project-two independently retuned ablations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from cpswm.system.counterfactual_event_hypergraph import (
    EventHypothesisHistory,
    ProvenanceConstrainedMessagePassing,
)


class ProjectTwoAblation(StrEnum):
    NO_EXECUTION_FEEDBACK_RETURN = "no_execution_feedback_return"
    FAILURE_ONLY_FEEDBACK = "failure_only_feedback"
    SUCCESS_ONLY_FEEDBACK = "success_only_feedback"
    NO_UNKNOWN_ACTOR = "no_unknown_actor"
    NO_UNKNOWN_MECHANISM = "no_unknown_mechanism"
    NO_UNRESOLVED_MASS = "no_unresolved_mass"
    NO_PCHMP_JOINT_PROPAGATION = "no_pchmp_joint_propagation"
    INDEPENDENT_HYPOTHESIS_SCORING = "independent_hypothesis_scoring"
    ORRER_IN_PLACE_OVERWRITE = "orrer_replaced_by_in_place_overwrite"
    ORRER_FULL_RERUN = "orrer_replaced_by_full_rerun"
    NO_MECHANISM_ROLE_REVISION = "no_mechanism_role_revision"
    NO_PROVENANCE_FIREWALL = "no_provenance_firewall"
    NO_DEDUPLICATION = "no_deduplication"
    NO_PROJECT_ONE_RETRACT_CORRECT = "no_project_one_retract_correct"
    NO_CCRR_MULTI_REGIME_MEMORY = "no_ccrr_multi_regime_memory"
    NO_RGRC_GATE = "no_rgrc_gate"
    NO_LLM = "no_llm"
    LLM_PRIOR_ONLY = "llm_prior_only"
    LLM_DIRECT_DECISION = "llm_direct_decision"


REQUIRED_PROJECT_TWO_ABLATIONS = tuple(ProjectTwoAblation)


@dataclass(frozen=True, slots=True)
class ProjectTwoTopology:
    feedback_mode: str = "success_and_failure"
    unknown_actor: bool = True
    unknown_mechanism: bool = True
    unresolved_mass: bool = True
    pchmp_joint: bool = True
    hypothesis_scoring: str = "joint"
    orrer_mode: str = "reversible_revision"
    mechanism_role_revision: bool = True
    provenance_firewall: bool = True
    deduplication: bool = True
    project_one_revision: bool = True
    ccrr_multi_regime: bool = True
    rgrc_gate: bool = True
    llm_mode: str = "typed_evidence"


_CUTS = {
    ProjectTwoAblation.NO_EXECUTION_FEEDBACK_RETURN: ("feedback_mode", "none"),
    ProjectTwoAblation.FAILURE_ONLY_FEEDBACK: ("feedback_mode", "failure_only"),
    ProjectTwoAblation.SUCCESS_ONLY_FEEDBACK: ("feedback_mode", "success_only"),
    ProjectTwoAblation.NO_UNKNOWN_ACTOR: ("unknown_actor", False),
    ProjectTwoAblation.NO_UNKNOWN_MECHANISM: ("unknown_mechanism", False),
    ProjectTwoAblation.NO_UNRESOLVED_MASS: ("unresolved_mass", False),
    ProjectTwoAblation.NO_PCHMP_JOINT_PROPAGATION: ("pchmp_joint", False),
    ProjectTwoAblation.INDEPENDENT_HYPOTHESIS_SCORING: (
        "hypothesis_scoring",
        "independent",
    ),
    ProjectTwoAblation.ORRER_IN_PLACE_OVERWRITE: ("orrer_mode", "in_place"),
    ProjectTwoAblation.ORRER_FULL_RERUN: ("orrer_mode", "full_rerun"),
    ProjectTwoAblation.NO_MECHANISM_ROLE_REVISION: ("mechanism_role_revision", False),
    ProjectTwoAblation.NO_PROVENANCE_FIREWALL: ("provenance_firewall", False),
    ProjectTwoAblation.NO_DEDUPLICATION: ("deduplication", False),
    ProjectTwoAblation.NO_PROJECT_ONE_RETRACT_CORRECT: ("project_one_revision", False),
    ProjectTwoAblation.NO_CCRR_MULTI_REGIME_MEMORY: ("ccrr_multi_regime", False),
    ProjectTwoAblation.NO_RGRC_GATE: ("rgrc_gate", False),
    ProjectTwoAblation.NO_LLM: ("llm_mode", "none"),
    ProjectTwoAblation.LLM_PRIOR_ONLY: ("llm_mode", "prior_only"),
    ProjectTwoAblation.LLM_DIRECT_DECISION: ("llm_mode", "direct_decision"),
}


class ProjectTwoAblationProtocol:
    """Topology declaration; unsafe cuts are evaluator-sandbox only."""

    def __init__(self) -> None:
        self.full_topology = ProjectTwoTopology()
        self.ablations = REQUIRED_PROJECT_TWO_ABLATIONS

    def topology_for(self, ablation: ProjectTwoAblation) -> ProjectTwoTopology:
        field, value = _CUTS[ablation]
        return replace(self.full_topology, **{field: value})

    def verify_cut(self, ablation: ProjectTwoAblation, topology: ProjectTwoTopology) -> bool:
        field, value = _CUTS[ablation]
        changed = [
            name
            for name in ProjectTwoTopology.__dataclass_fields__
            if getattr(topology, name) != getattr(self.full_topology, name)
        ]
        return changed == [field] and getattr(topology, field) == value


class PriorOnlyMessagePassing:
    """Evaluator-only cut: preserve the ORRER prior and ignore PCHMP evidence."""

    model_version = "ablation-no-pchmp-joint@0.1"

    def __init__(self) -> None:
        self._delegate = ProvenanceConstrainedMessagePassing()

    def consume(self, history: EventHypothesisHistory, evidence=()):
        del evidence
        return self._delegate.infer(history, ()), history


class IndependentEvidenceMessagePassing:
    """Score evidence records sequentially instead of joint propagation."""

    model_version = "ablation-independent-scoring@0.1"

    def __init__(self) -> None:
        self._delegate = ProvenanceConstrainedMessagePassing()

    def consume(self, history: EventHypothesisHistory, evidence=()):
        if not evidence:
            return self._delegate.infer(history, ()), history
        current = history
        result = None
        for item in evidence:
            result, current = self._delegate.consume(current, (item,))
        assert result is not None
        return result, current


class EvaluatorNoDedupMessagePassing:
    """Unsafe diagnostic: infer without writing the consumption receipt."""

    model_version = "ablation-no-dedup@0.1"
    deduplication_enabled = False

    def __init__(self) -> None:
        self._delegate = ProvenanceConstrainedMessagePassing()

    def consume(self, history: EventHypothesisHistory, evidence=()):
        return self._delegate.infer(history, evidence), history


class EvaluatorNoProvenanceFirewallMessagePassing:
    """Unsafe diagnostic: rewrite evidence scope before normal inference."""

    model_version = "ablation-no-provenance-firewall@0.1"
    provenance_firewall_enabled = False

    def __init__(self) -> None:
        self._delegate = ProvenanceConstrainedMessagePassing()

    def consume(self, history: EventHypothesisHistory, evidence=()):
        latest = history.latest
        rewritten = tuple(
            item.model_copy(
                update={
                    "source_detection_result_id": latest.source_detection_result_ids[1],
                    "object_instance_id": latest.object_instance_id,
                    "metadata": item.metadata.model_copy(
                        update={
                            "household_id": latest.household_id,
                            "session_id": latest.session_id,
                            "trace_id": latest.trace_id,
                        }
                    ),
                }
            )
            for item in evidence
        )
        return self._delegate.consume(history, rewritten)
