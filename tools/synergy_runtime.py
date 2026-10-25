"""Optional posterior-parent proposal; native target and production defaults unchanged."""

import math

from cpswm.system.evaluation_operations.structure_two_current_event import CurrentEventRuntime


def parent_proposal(support, parent_mass):
    """Positive numerical proposal floor, NOT a target/prior or evidence floor.

    Native revise normalizes these masses globally, then records that actual q
    in its importance denominator. The floor keeps q above native log's 1e-300
    floor even after the uniform-parent factor (24 particles) is applied.
    """
    if not math.isfinite(parent_mass) or parent_mass < 0:
        raise ValueError("invalid parent mass")
    result = []
    for candidate, probability in support:
        if not math.isfinite(probability) or probability <= 0:
            raise ValueError("candidate proposal must have positive finite support")
        result.append((candidate, max(parent_mass * probability, 1e-280)))
    if not result:
        raise ValueError("empty candidate support")
    return tuple(result)


class PosteriorParentRuntime(CurrentEventRuntime):
    def _candidates(self, observation, parent):
        support = super()._candidates(observation, parent)
        return parent_proposal(support, 1.0 if parent is None else parent.posterior_probability)
