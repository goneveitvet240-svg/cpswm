# Project Two — Open-World Hidden-Event Inference & Reversible Attribution: Core Loop

Status: prototype core loop (shortest runnable closed loop). Signatures, real
perception, adversarial firewalls, and a production project-one outbox are
retained as interfaces, not removed.

## Purpose

Close the loop that turns an execution *result* into new counterfactual evidence
for the hidden-event explanation chain, and feed the reversible attribution back
to project one — **without** building a second event-reasoning stack. The loop is
an orchestrator over the existing CHEH / ORRER / PCHMP / `ExecutionFeedbackProjector`
components.

## End-to-end chain

```
ObservationDetectionResult (before @ L1, after @ L2)
  └─ CHEH branch ─────────────► open-world hidden-event hypotheses
                                (direct + handoff, per responsible actor,
                                 + unresolved mass)
ExecutionFeedbackRecord (search/place outcome)
  └─ ExecutionFeedbackProjector ─► ProjectedFeedbackEvidence
        (typed route, likelihood-aware, snapshot-bound prior, de-duplicated)
  └─ presence Bayes factor r  (odds(posterior)/odds(prior) from the projection,
                               whose magnitude comes from ActionOutcomeLikelihoodModel)
  └─ ActorResponsibilityEvidence  (r on every responsible KNOWN actor;
                                   neutral on unknown_actor -> open world grows)
  └─ PCHMP.infer ─────────────► re-propagated joint posterior
                                (provenance firewall + single-consumption)
  └─ ORRER.revise_actor_responsibility ─► one reversible, parent-linked revision
  └─ EventRevisionOutcome ────► before/after hypothesis & actor posteriors,
                                owner-mass delta, source feedback, requests
  └─ ProjectOneStatRequest ───► explicit retract / correct / reinforce for P1
```

Implementation: `src/cpswm/system/counterfactual_event_hypergraph/feedback_revision_loop.py`
(`ProjectTwoFeedbackRevisionLoop`). Demo: `apps/prototype_spine/run_project_two_feedback_demo.py`.

## How feedback becomes counterfactual evidence

1. **Projection.** The raw `ExecutionFeedbackRecord` is projected by the existing
   `ExecutionFeedbackProjector`, which enforces schema/surface/HST/target/hash/
   valid-time, binds the prior to a snapshot node, and de-duplicates. Search /
   navigate / grasp route to a *target-presence* update; place / transfer route to
   a *location-transition* candidate.
2. **Strength, not fact.** From the projected update we take a presence **Bayes
   factor** `r = odds(posterior)/odds(prior)`. A failed search yields `r < 1`, a
   successful one `r > 1`. The magnitude is entirely a function of the
   `ActionOutcomeLikelihoodModel` (the projector computed the posterior from it);
   the loop never treats an outcome as an absolute truth.
3. **Open-world encoding.** Every responsible **known** actor asserts the object
   reached the destination, so each carries `r`; the `unknown_actor` bucket carries
   a neutral ratio. A failed observation therefore *shifts mass toward unresolved /
   unknown* rather than re-normalising it onto a different known culprit.

### Two revision modes (event-existence vs actor-responsibility)

A presence-only outcome carries the *same* `r` to every known actor, so it revises
**event-existence confidence** (the explained chains vs unresolved/unknown) and, by
construction, leaves owner-vs-guest *relative* odds unchanged. To revise **actor
responsibility** — moving mass between owner / guest / robot / unknown — the caller
supplies `actor_likelihood_ratios` (an actor-discriminating observation channel).
Each known actor is then re-weighted by `r × factor[actor]`, so relative odds
genuinely change. Both modes compose; a search outcome alone is honestly the
former, not the latter.

### Isolated route (place/transfer)

Place/transfer feedback is projected only as an action success/slip *candidate* by
the `ExecutionFeedbackProjector`, not a transition/presence/actor posterior.
Folding it into a presence ratio would mislabel a gripper slip as reduced
historical responsibility, so the loop **rejects** that route
(`UnsupportedFeedbackRouteError`) until a real location/mechanism/role likelihood
model is wired. It is isolated, not silently converted.

### Provenance firewall (binding)

Before any mutation the loop binds the feedback to *this exact* hidden event:
object id, `attempted_location_id == destination_location_id`, matching
household/session/trace on both the feedback and its binding, and a causal window
(`feedback.valid_time.start >= interval_end`). De-duplication and forgery detection
(same record id, different content/inputs) run through the projector's
prepare/commit, so a forged replay cannot bypass validation via a loop-side cache.

## How ORRER / PCHMP produce the reversible revision

* `ProvenanceConstrainedMessagePassing.infer` re-propagates the joint posterior
  over the latest revision’s hypotheses under the provenance firewall and
  single-consumption rules; its result is recorded on the outcome
  (`repropagated_posterior`) **and asserted equal** to the ORRER revision posterior
  (`HypothesisPosteriorInconsistencyError` otherwise), so the two updates can never
  ship contradictory posteriors.
* `OpenWorldRoleConditionedReversibleEventRevisionEngine.revise_actor_responsibility`
  appends **one new revision** whose `parent_revision_id` is the superseded
  revision. The ORRER history is append-only, so the prior revision stays fully
  traceable and the change is reversible (retract / reactivate remain available).
* The loop runs ORRER with `retraction_threshold = 0.0` so feedback only
  *re-weights* — it never hard-zeroes a hypothesis. Reversible thresholded
  retraction remains a separate, opt-in policy.

## Interface handed to project one

`EventRevisionOutcome` (all fields auditable):

- `superseded_revision_id`, `corrected_revision_id`
- `hypothesis_posterior_before` / `_after`
- `actor_posterior_before` / `_after` (unresolved surfaced under `unknown_actor`)
- `unresolved_before` / `_after`, `owner_mass_before` / `_after`
- `source_feedback_record_id`, `presence_likelihood_ratio`, `repropagated_posterior`
- `project_one_requests: tuple[ProjectOneStatRequest, ...]`

`ProjectOneStatRequest` is the **only** channel to project one — project two never
touches project-one Dirichlet/RLS state directly. Kinds:

- `RETRACT` — owner mass fell to ~0 (attribution withdrawn),
- `CORRECT` — owner mass fell but remains positive,
- `REINFORCE` — owner mass rose (a corroborated success).

Each request names the superseded/corrected revisions, the event hypothesis set,
owner key, object, destination location, owner-mass delta, and the source feedback
record. `apply_project_one_request(request, loop)` consumes it into a real
`HybridEventToTaskCoordinatorLoop` (project one keys its ledger by the CHEH revision
id): `RETRACT → retract_revision`, `CORRECT → apply_orrer_revision` with the
corrected owner mass. `REINFORCE` is an **explicit no-op** (returns `False`) because
project one has no positive-reinforcement event-revision interface yet — a retained
gap, never a silent state change.

## Invariants enforced (with tests)

`tests/test_project_two_feedback_revision_loop.py`:

- search failure lowers the relevant hypotheses **without** zeroing them;
- action success reinforces the matching hypotheses;
- feedback appends a new revision and the old one stays traceable;
- unexplained feedback grows unresolved/unknown mass (no fabricated actor);
- an actor-posterior revision emits a project-one-consumable retract/correct request;
- a replayed feedback record is idempotent (dedup);
- a provenance-firewall-rejected feedback cannot move any posterior.

## Retained adaptation points (not removed, not "no longer needed")

- **Place-failure multi-axis revision.** ORRER already exposes
  `revise_event_mechanism` and `revise_role_binding`; the prototype folds
  place-failure onto the actor axis. Jointly revising location/mechanism/role from
  a single place-failure is a wired-but-unused capability to complete.
- **Real perception & signatures.** Feedback records are trusted inputs here; a
  signed, sensor-derived path remains to be attached.
- **Adversarial / provenance firewall depth.** The loop enforces object-binding and
  reuses projector + PCHMP firewalls; deeper adversarial hardening is future work.
- **Production project-one outbox.** `ProjectOneStatRequest` is returned in-process;
  a durable, exactly-once cross-component outbox (shared with the MVCC/presence-log
  design) is still to be built.
```
