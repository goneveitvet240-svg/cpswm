"""Optional missing-evidence target intervention; not the same-target sampler test.

The missing-event adapter supplies regime_change_probability=0 as a placeholder.
This diagnostic removes ONLY its CCRR projection factor on prediction-only zero
inputs. Transition persistence, cause distribution, six interactions and priors
are retained. A production missing-regime contract needs separate acceptance.
"""

import math

from synergy_runtime import PosteriorParentRuntime

from cpswm.system.evaluation_operations.structure_two_selected_method import (
    ParticleRegimeDecision,
    StructureTwoOperator,
)


class MissingRegimeNeutralRuntime(PosteriorParentRuntime):
    def _main_log_factor(self, observation, candidate):
        original = super()._main_log_factor(observation, candidate)
        if (
            not getattr(observation, "prediction_only", False)
            or observation.regime_change_probability != 0.0
            or StructureTwoOperator.CCRR in self.neutralized_operators
        ):
            return original
        changing = candidate.regime_decision in (
            ParticleRegimeDecision.CREATE,
            ParticleRegimeDecision.REACTIVATE,
        )
        probability = 0.0 if changing else 1.0
        if candidate.regime_decision is ParticleRegimeDecision.UNRESOLVED:
            probability = max(observation.unresolved_probability, 1e-12)
        return original - math.log(max(probability, 1e-300))
