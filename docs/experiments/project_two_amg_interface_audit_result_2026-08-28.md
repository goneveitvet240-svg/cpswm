# Project-two AMG action-interface fairness audit result

## Outcome first

The old statement “matched AMG is methodologically better than PCHMP on the
project-two action benchmark” is not supported by this audit.

AMG did not receive evaluator truth or a larger put-back action set. Its old
advantage came from a favorable evidence adapter plus label-sensitive MAP
tie-breaking on a benchmark whose target is exactly a sticky latest-owner
recurrence.

## Stable matched-interface result

Validation seeds were 19000–19003 and one-time holdout seeds were 20000–20011.
The 15% stress mask was keyed by visible `scene_id + timestamp`, not random
sealed UUIDs. Two complete runs produced byte-identical artifacts.

| Stress | Arm | Put-back error | Contamination | Binary owner error |
| --- | --- | ---: | ---: | ---: |
| clean | all six arms | 0.059896 | 0.000000 | 0.000000 |
| ambiguous | all six arms | 0.059896 | 0.000000 | 0.000000 |
| misattribution | current AMG posterior adapter | **0.104167** | **0.026042** | **0.158306** |
| misattribution | AMG prior-corrected odds | 0.174479 | 0.085938 | 0.177883 |
| misattribution | direct actor posterior + common sticky | 0.174479 | 0.085938 | 0.177883 |
| misattribution | PCHMP + common sticky, feedback | 0.174479 | 0.085938 | 0.177883 |
| misattribution | PCHMP + common sticky, no feedback | 0.174479 | 0.085938 | 0.177883 |
| misattribution | PCHMP native latest-owner | 0.174479 | 0.085938 | 0.177883 |

The current posterior-as-likelihood AMG and prior-corrected AMG disagreed on
7.5521% of put-back actions under misattribution. Once evidence semantics were
corrected, AMG tied direct actor evidence and both PCHMP interfaces exactly.
Execution feedback did not explain the difference.

## Four audit findings

### 1. No privileged information or action set

Every arm read the same visible stream, predicted after observation and before
feedback, and selected a put-back location from the same encounter-ordered
location set. AMG was feedback-blind while project two received feedback, so
feedback availability did not favor AMG.

### 2. Evidence-adapter semantic advantage

`_AMGOpenWorldMethod` passes `actor_posterior` into an argument named and scored
as `actor_event_likelihoods`; the AMG implementation then applies log-odds.
Posterior is not an event likelihood when a reference prior has already been
used. Passing raw `posterior/reference_prior` is also invalid because AMG's
contract requires values strictly inside `(0,1)`.

The audit used `LR/(1+LR)` as a contract-valid prior-corrected odds adapter.
That correction removed the apparent AMG advantage. This is an adapter result,
not a claim that `LR/(1+LR)` is a faithful reproduction of Damen–Hogg's learned
video likelihoods; those likelihoods are unavailable in D0.

### 3. Actor-label tie-break failure

Renaming actor keys without changing evidence changed AMG predictions. On the
stable holdout, symmetric-misattribution equivariance was 251/256 = 0.980469.
On the post-audit 21000–21059 diagnostic it was 1197/1234 = 0.970016.

All 21 AMG/PCHMP owner-classification disagreements in that 60-episode
diagnostic occurred on handoff relocation; AMG was correct on all 21. In a
neutral handoff, however, AMG's final MAP tie-break includes literal actor-key
strings. Therefore this apparent handoff advantage is not label-permutation
safe and cannot be treated as method evidence until ties are marginalized or
resolved by a label-invariant rule.

### 4. Benchmark target alignment

The evaluator target satisfied all three recurrences at rate 1.0:

- owner event: target becomes the observed location;
- non-owner event: target remains the previous owner target;
- combined latest-true-owner recurrence.

Consequently the benchmark is structurally a sticky latest-owner task. It is a
valid short-horizon action test, but it cannot by itself establish the value of
long-term habit consolidation, regimes, reversible statistics, or recovery.

## Reproducibility defect in older development artifacts

The previous symmetric-misattribution transform selected steps by hashing
`step_id`. D0 creates a new sealed UUID secret for each adapter instance, so
the same numeric seeds produced different episode/step IDs and different 15%
stress masks. One minimal reproduction generated 7 swapped steps and another
generated 4 from the same seed.

Within one run, methods shared a mask; across runs, results were not seed-
reproducible. Therefore old dual-timescale and CIAV stress artifacts remain
useful development records but are not confirmatory evidence. This audit uses
the stable visible scene/time key and repeated byte-identically.

## Required benchmark corrections

Before AMG can again qualify as a paper-level matched opponent:

1. freeze a UUID-independent stress manifest;
2. replace actor-string MAP tie-breaking with label-invariant marginalization,
   abstention, or a registered encounter-order rule;
3. define the AMG evidence quantity explicitly and downgrade the current arm
   from faithful matched reproduction while learned source likelihoods are
   unavailable;
4. keep the common sticky readout for inference comparison;
5. add a separate persistent-habit/recovery target instead of asking the sticky
   target to validate long-term memory;
6. rerun dual-timescale and CIAV claims after those corrections.

## Scientific status

- Privileged evaluator information: not detected.
- Privileged put-back action set: not detected.
- Favorable evidence-interface treatment: detected and material.
- Label-invariant tie-breaking: failed.
- Benchmark target-alignment advantage: detected.
- Fair conclusion after correction: AMG ties PCHMP/direct actor evidence on
  this stable matched-interface audit; old AMG superiority is invalidated.

## Artifact

- `artifacts/project_two_v04_development/amg_interface_audit_v0_1.json`
- SHA-256: `eb670e46790324214473ab93a597186a8d282f2e3fec5d7b0cd45333fd85d5ac`
