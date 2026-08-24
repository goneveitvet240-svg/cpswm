# Project Two revision-to-action causal loop v0.3

Status: interface and D0 execution gate frozen on 2026-08-24. This is not a
paper-level result and does not close D1-D4 external-validity gates.

## Causal contract

`ProjectTwoRevisionActionTrace` is immutable and binds one source
`ExecutionFeedbackRecord` to CHEH support, PCHMP re-propagation, append-only
ORRER correction, a typed Project One request/receipt, Dirichlet/RLS/Hybrid
RGRC deltas, CCRR decision, old/new `BeliefSnapshot` IDs, the exact snapshot
read by the planner, its next action distribution, and evaluator-only
utility/regret. Evaluator truth enters only after action selection.

The actor field is the complete marginal

`p(A=a) = sum_h p(h) 1[actor(h)=a] + p(M=unknown) p(A=a | M=unknown)`.

Global unresolved actor mass is added only to `unknown_actor`. The trace also
publishes the known-mechanism actor partition and the unknown-mechanism actor
partition, so `owner_mass` and Project One deltas have one mathematical meaning.

## Request state machine

- `applied`: all Dirichlet, RLS and Hybrid RGRC stages committed atomically.
- `deferred_due_to_quarantine`: request is in an exactly-once outbox bound to
  the quarantined revision and retains its source feedback ID.
- `rejected`: validation failed, the revision was absent, or CCRR explicitly
  discarded rather than promoted the quarantined event.
- `replay_noop`: the same request fingerprint was already applied or is already
  pending; no statistic changes are permitted.

Promotion removes the outbox guard only for the one authorized retry. A later
replay produces a receipt and leaves all statistics unchanged. Stage failure in
Dirichlet, RLS or Hybrid RGRC restores all stores, lineage, receipts and snapshot.

## Location evidence

`attempted_location_id` is an action target. It never becomes a certain landing
point from success probability alone. `observed_destination_location_id` is
accepted only with a separate, provenance-carrying post-action observation.
Without it, feedback changes the location posterior or unresolved location mass;
with it, success or failure may correct the destination revision.

## D0 frozen diagnostic

The fixed D0 report secret `project-two-v03-frozen-report-2026-08-24` produced
40 feedback traces and 40 Project One requests. Final receipts were 35 applied,
0 deferred, 5 rejected and 0 replay no-ops. The six formerly lost requests all
originated at quarantined events: one later promotion now applies exactly once;
five CCRR-discarded events now end explicitly as rejected rather than a caught
`KeyError`.

The fresh D0 action result remains negative: Project Two put-back error is
0.34375 versus matched AMG 0.09375; cumulative regret is 16.5 versus 8.5.
Search success ties at 0.828125. The repaired handoff is therefore operational,
but the utility/action reader has not converted revision quality into better
put-back choice. No evaluator truth, extra action budget, split change, or
baseline weakening was used.
