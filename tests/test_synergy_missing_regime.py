from dataclasses import replace

import pytest
from run_short_history_reference import fixed_inputs
from synergy_missing_regime import MissingRegimeNeutralRuntime
from synergy_runtime import PosteriorParentRuntime

from cpswm.system.evaluation_operations.structure_two_stateful_full_joint import FullJointArm


def test_missing_zero_factor_is_neutral_but_observed_evidence_and_proposal_are_unchanged():
    _, config, model, observations, _ = fixed_inputs()[0]
    original = PosteriorParentRuntime(
        arm=FullJointArm.STATEFUL_FULL_JOINT, config=config, neural_model=model
    )
    fixed = MissingRegimeNeutralRuntime(arm=original.arm, config=config, neural_model=model)
    observed = observations[0]
    missing = replace(
        observed,
        prediction_only=True,
        observed_location_id=None,
        position_source_id=None,
        location_likelihood=(),
        regime_change_probability=0.0,
    )
    assert original._candidates(missing, None) == fixed._candidates(missing, None)
    changes = []
    for candidate, _ in original._candidates(missing, None):
        assert fixed._main_log_factor(observed, candidate) == original._main_log_factor(
            observed, candidate
        )
        # Explicit finite prior remains respected even without a location observation.
        explicit = replace(missing, regime_change_probability=0.2)
        assert fixed._main_log_factor(explicit, candidate) == original._main_log_factor(
            explicit, candidate
        )
        neutral = replace(missing, regime_change_probability=0.5, unresolved_probability=0.5)
        import math

        expected = original._main_log_factor(neutral, candidate) + math.log(2)
        assert fixed._main_log_factor(missing, candidate) == pytest.approx(expected, abs=1e-12)
        changes.append(
            fixed._main_log_factor(missing, candidate)
            - original._main_log_factor(missing, candidate)
        )
    assert max(changes) > 690
