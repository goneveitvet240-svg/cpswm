# Project One open-world and matched-baseline closure

Date: 2026-08-25

## Code-level closure

- Candidate-space semantics are explicit: `TRAIN_ONLY`, `MANIFEST`, and
  `OPEN_SET` freeze only prefix/operator-known locations and always include the
  canonical `unknown_location` bucket.
- `OBSERVED_ALL` is retained only for legacy reproduction and requires an
  explicit leakage opt-in.
- Binding identity is `(household_id, subject_id, object_id)`. `subject_id`
  owns the habit; `actor_id` records who executed the move.
- EWMA, CUSUM, RLS fixed-threshold, ordinary BOCPD, BOCPDMS, context frequency,
  and persistence are available as independent online evaluation arms.
- No-CF-BOCPD, No-CCRR, and No-regime-reactivation are one-mechanism cuts of
  the existing decision chain. They do not create another habit store.
- The tuner gives every arm its own parameter grid under the same trial budget.
- The method audit remains fail-closed unless anomaly/change metrics are
  separated, Dirichlet incremental value is demonstrated, search/put-back/
  delivery utilities exist, MDE is action-derived, and external validity is
  demonstrated.

## Strict status

This change closes code contracts and experiment wiring only. It does not show
that the full chain beats the matched baselines, that Dirichlet surprise adds
value beyond RLS residual, or that any internal change score improves embodied
action utility. The legacy `0.05` MDE remains non-activating until replaced by
an action-derived value. No full experiment or external-validity run is claimed
by this record.
