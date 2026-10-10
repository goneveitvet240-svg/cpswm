"""Explicit current-runtime readout; historical profiles retain their own config."""

from cpswm.system.prototype_spine import ActionReadout, ActionReadoutConfig


def current_action_readout() -> ActionReadoutConfig:
    """Wire the previously selected v0.6 values, without retuning or opening writes."""
    return ActionReadoutConfig(
        readout=ActionReadout.DUAL_TIMESCALE_REVERSIBLE,
        hybrid_alpha_weight=0.0,
        fast_action_weight=0.7,
        surviving_revision_weight=0.2,
        regime_local_weight=0.1,
        fast_owner_mass_floor=0.5,
        owner_mass_floor=0.5,
        recency_half_life=1.0,
    )
