# Project Two corrected action benchmark protocol (2026-08-28)

Evidence status: post-audit development benchmark; not confirmatory and not real-world evidence.

This protocol corrects four problems exposed by the AMG interface audit while preserving all seven project-two operators and the historical v0.2 artifacts.

1. **Stable stress assignment.** Symmetric-misattribution stress is keyed by visible `scene_id` plus step timestamp. It is independent of the sealed UUID secret, so rebuilding the same numeric seeds cannot silently change the stressed steps.
2. **Label-invariant AMG action readout.** AMG reports every responsible actor represented among exact MAP maximizers. The action adapter updates the owner location only when the maximizing responsible-actor set is uniquely the owner. `selected_sequence` remains available for backward-compatible parse inspection but cannot resolve an action tie.
3. **Prior-corrected AMG evidence.** A categorical actor posterior is converted to an evidence ratio `posterior / reference_prior`, then to the open probability `ratio / (1 + ratio)` required by AMG's log-odds scoring. The former posterior-as-likelihood interface is retained only in the historical audit arm.
4. **Honest fidelity label.** The AMG comparator is a `matched_replay_adapter`, not a `faithful_matched` reproduction. Missing source video likelihoods and source RJMCMC-SA / integer-programming inference are explicit paper-level gate failures.

The evaluator now reports two distinct put-back targets:

- `put_back_error_rate`: the existing sticky latest-owner target. It changes immediately after every true owner placement.
- `persistent_owner_mode_error_rate`: an added diagnostic for longer-term habit. It is the cumulative mode of true owner placements, initialized by one pseudo-observation of the pre-episode owner habit. It does not replace the sticky target and is not used for hyperparameter selection or the current superiority gate.

The second target is deliberately a transparent derived diagnostic, not a claim that cumulative mode is the uniquely correct definition of habit. A regime-window or exponentially decayed definition would be a separate preregistered experiment.
