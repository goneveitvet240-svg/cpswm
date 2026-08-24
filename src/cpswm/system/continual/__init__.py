"""Continual adaptation modules for CPWM components."""

from .event_derived_update_ledger import (
    ConsolidationState,
    EventDerivedDeltaPromotion,
    EventDerivedDeltaRecord,
    EventDerivedDeltaReversal,
    EventDerivedUpdateLedger,
    LedgerIntegrityError,
    RebuildCost,
    RetractionCost,
    projection_total_variation,
)

# NOTE: the integration loops (event_to_task_loop, hybrid_event_to_task_loop)
# are intentionally NOT eagerly re-exported here.  hybrid_event_to_task_loop
# imports cpswm.world_model.grounded_search.concurrent_map_task, which imports
# back into this package (hybrid_statistics), so eager re-export creates a
# package-level import cycle.  Import those loops from their submodules directly:
#     from cpswm.system.continual.hybrid_event_to_task_loop import ...
from .hybrid_statistics import (
    ConsolidationRiskCertificate,
    DirichletRLSFusion,
    FusedLocationBelief,
    HybridConsolidationState,
    HybridLedgerError,
    HybridProjection,
    HybridPromotion,
    HybridQuarantineSupersession,
    HybridReversal,
    HybridStatisticDelta,
    HybridStatisticLedger,
    NaturalRidgeResidual,
    StatisticKey,
)
from .project_one_feedback import (
    DefaultPrototypeFeedbackPolicy,
    EventRevisionKind,
    EventRevisionOutcome,
    ExecutionFeedbackInterpretationPolicy,
    FeedbackInterpretation,
)
from .project_one_regime_loop import (
    AutomaticCFBOCPDCCRRRouter,
    AutomaticRegimeAssessment,
    DerivedEvidenceReactivationPolicy,
    HabitStateConclusion,
    PrototypeLoopConfig,
    PrototypeStatisticOperation,
)
from .rls import (
    RecursiveLeastSquares,
    RLSChannelReliabilityCalibrator,
    RLSConfig,
    RLSHabitSample,
    RLSHabitScoreHead,
    RLSRegimeBank,
    RLSRegimeSwitchEvent,
)

__all__ = [
    "AutomaticCFBOCPDCCRRRouter",
    "AutomaticRegimeAssessment",
    "ConsolidationRiskCertificate",
    "ConsolidationState",
    "DefaultPrototypeFeedbackPolicy",
    "DerivedEvidenceReactivationPolicy",
    "DirichletRLSFusion",
    "EventDerivedDeltaPromotion",
    "EventDerivedDeltaRecord",
    "EventDerivedDeltaReversal",
    "EventDerivedUpdateLedger",
    "EventRevisionKind",
    "EventRevisionOutcome",
    "ExecutionFeedbackInterpretationPolicy",
    "FeedbackInterpretation",
    "FusedLocationBelief",
    "HabitStateConclusion",
    "HybridConsolidationState",
    "HybridLedgerError",
    "HybridProjection",
    "HybridPromotion",
    "HybridQuarantineSupersession",
    "HybridReversal",
    "HybridStatisticDelta",
    "HybridStatisticLedger",
    "LedgerIntegrityError",
    "NaturalRidgeResidual",
    "PrototypeLoopConfig",
    "PrototypeStatisticOperation",
    "RLSChannelReliabilityCalibrator",
    "RLSConfig",
    "RLSHabitSample",
    "RLSHabitScoreHead",
    "RLSRegimeBank",
    "RLSRegimeSwitchEvent",
    "RebuildCost",
    "RecursiveLeastSquares",
    "RetractionCost",
    "StatisticKey",
    "projection_total_variation",
]
