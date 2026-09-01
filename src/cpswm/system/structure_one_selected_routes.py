"""Frozen method selection for the current Structure One programme."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum


class IdentityEvidenceMethod(StrEnum):
    LEARNED_METRIC = "learned_metric"


class IdentityAuthority(StrEnum):
    BAYESIAN_ASSOCIATION = "bayesian_association"


class CommonsenseMethod(StrEnum):
    PROVENANCE_WEIGHTED_HYBRID = "provenance_weighted_hybrid"


class HiddenEventModel(StrEnum):
    DBN_FACTOR_GRAPH = "dbn_factor_graph"


class HiddenEventInference(StrEnum):
    PARTICLE_FILTERING = "particle_filtering"


class HiddenEventRevision(StrEnum):
    CHEH_ORRER = "cheh_orrer"


class HabitMethod(StrEnum):
    CF_BOCPD_RLS_ONLY = "cf_bocpd_rls_only"


class DirichletRole(StrEnum):
    DIAGNOSTIC_ONLY = "diagnostic_only"


class QueryCompilerMethod(StrEnum):
    CONSTRAINED_LLM = "constrained_llm"


class PolicyLearningMethod(StrEnum):
    OFFLINE_PRETRAIN_CONTROLLED_ONLINE = "offline_pretrain_controlled_online"


@dataclass(frozen=True, slots=True)
class StructureOneMethodSelection:
    identity_evidence: IdentityEvidenceMethod = IdentityEvidenceMethod.LEARNED_METRIC
    identity_authority: IdentityAuthority = IdentityAuthority.BAYESIAN_ASSOCIATION
    commonsense: CommonsenseMethod = CommonsenseMethod.PROVENANCE_WEIGHTED_HYBRID
    hidden_event_model: HiddenEventModel = HiddenEventModel.DBN_FACTOR_GRAPH
    hidden_event_inference: HiddenEventInference = HiddenEventInference.PARTICLE_FILTERING
    hidden_event_revision: HiddenEventRevision = HiddenEventRevision.CHEH_ORRER
    habit: HabitMethod = HabitMethod.CF_BOCPD_RLS_ONLY
    dirichlet_role: DirichletRole = DirichletRole.DIAGNOSTIC_ONLY
    query_compiler: QueryCompilerMethod = QueryCompilerMethod.CONSTRAINED_LLM
    policy_learning: PolicyLearningMethod = PolicyLearningMethod.OFFLINE_PRETRAIN_CONTROLLED_ONLINE

    def signature(self) -> str:
        payload = {
            key: value.value if isinstance(value, StrEnum) else value
            for key, value in asdict(self).items()
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(body).hexdigest()


SELECTED_STRUCTURE_ONE_METHODS = StructureOneMethodSelection()
