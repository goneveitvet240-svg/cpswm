"""Cause-gated write control for long-term habit consolidation (RGRC hook).

结构二 §4.7 (统一总纲 line 105) requires that the CF-BOCPD cause posterior
directly decide which long-term parameters RGRC may modify, rather than merely
emitting a label after detection.

This turns a :class:`JointCauseSnapshot` cause posterior into a write decision:
which long-term parameter blocks may be rewritten, and specifically whether the
*habit* block may change regime.  A detected change attributed to observation,
actor, or noise must **not** rewrite the habit block -- that is the contamination
the whole cause factorization exists to prevent.  An ambiguous attribution
writes nothing and is surfaced for active verification rather than guessed.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cause_factorized_bocpd import ChangeCause
from .joint_cause_bocpd import CauseResetMatrix, JointCauseSnapshot


@dataclass(frozen=True, slots=True)
class HabitWriteDecision:
    """Which long-term blocks a change is permitted to rewrite."""

    change_detected: bool
    attributed_cause: ChangeCause | None
    writable_blocks: frozenset[ChangeCause]
    habit_block_writable: bool
    ambiguous: bool
    rationale: str


class CauseGatedHabitConsolidation:
    """Gate long-term parameter writes on the joint CF-BOCPD cause posterior."""

    def __init__(
        self,
        *,
        reset_matrix: CauseResetMatrix | None = None,
        change_threshold: float = 0.5,
        attribution_margin: float = 0.15,
    ) -> None:
        if not 0.0 < change_threshold <= 1.0:
            raise ValueError("change_threshold must lie in (0, 1]")
        if not 0.0 <= attribution_margin < 1.0:
            raise ValueError("attribution_margin must lie in [0, 1)")
        self._reset_matrix = reset_matrix or CauseResetMatrix()
        self._change_threshold = change_threshold
        self._attribution_margin = attribution_margin

    def decide(self, snapshot: JointCauseSnapshot) -> HabitWriteDecision:
        # Only a substantive *segment* change can open a long-term block; a
        # transient noise burst is not a regime change and never writes.
        if snapshot.segment_change_probability < self._change_threshold:
            return HabitWriteDecision(
                change_detected=False,
                attributed_cause=None,
                writable_blocks=frozenset(),
                habit_block_writable=False,
                ambiguous=False,
                rationale="no segment change above threshold; long-term blocks stay frozen",
            )

        ranked = sorted(
            snapshot.segment_cause_posterior.items(),
            key=lambda item: (-item[1], item[0].value),
        )
        top_cause, top_mass = ranked[0]
        runner_mass = ranked[1][1] if len(ranked) > 1 else 0.0
        if top_mass - runner_mass < self._attribution_margin:
            # Change is real but its cause is not separable: write nothing and
            # let the caller verify (ties to the CIAV active-verification route).
            return HabitWriteDecision(
                change_detected=True,
                attributed_cause=None,
                writable_blocks=frozenset(),
                habit_block_writable=False,
                ambiguous=True,
                rationale="change detected but its cause is ambiguous; defer to verification",
            )

        writable = self._reset_matrix.blocks_reset_by(top_cause)
        return HabitWriteDecision(
            change_detected=True,
            attributed_cause=top_cause,
            writable_blocks=writable,
            habit_block_writable=ChangeCause.HABIT in writable,
            ambiguous=False,
            rationale=f"change attributed to {top_cause.value}; only its blocks may be rewritten",
        )

    def habit_consolidation_weight(self, snapshot: JointCauseSnapshot) -> float:
        """Multiplier for a habit-regime write: 0 unless the habit block is open.

        A consumer (e.g. an RGRC consolidation step or a regime switch on the
        habit model) multiplies its proposed long-term write by this, so an
        observation/actor/noise change cannot rewrite habit parameters.
        """

        decision = self.decide(snapshot)
        if not decision.habit_block_writable:
            return 0.0
        return snapshot.segment_change_probability * snapshot.segment_cause_posterior.get(
            ChangeCause.HABIT, 0.0
        )
