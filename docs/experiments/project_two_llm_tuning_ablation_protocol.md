# Project Two LLM/VLM Evidence, Tuning, and Ablation Protocol v0.1

Status: implementation and D0 plumbing pilot. This document does not claim real-world or paper-level superiority.

## Frozen scope and adapter position

The adapter is an evidence producer, not a replacement model:

`robot-visible replay -> LLM/VLM request firewall -> deterministic cache -> typed candidate/evidence bundle -> CHEH -> ORRER -> PCHMP -> actor/mechanism/role posterior -> action -> execution feedback -> ProjectTwoFeedbackRevisionLoop -> EventRevisionOutcome -> ProjectOneStatRequest -> explicit Project One API`

The adapter has no reference to event-history mutation or Project One statistics. It can emit actor, mechanism, ordered-role and location candidates, an action proposal, calibrated score, unknown mass and abstention. Every output binds provider/model/version, prompt template version, input record IDs, content hash, cache key, tokens, latency and cost. Model-facing requests are checked by the replay truth-leakage firewall before provider invocation.

`LLM-direct-decision` is a separate baseline. Its proposal selects an action but it has zero feedback-revision and Project One write calls. `Oracle evidence upper bound` is evaluator-only and does not call the LLM adapter.

## Four tracks

| Track | Evidence path | Decision path | Project Two writes |
|---|---|---|---|
| A No-LLM core | replay evidence only | full Project Two | only through revision loop and explicit Project One API |
| B LLM-as-evidence | typed adapter evidence | full Project Two | same controlled path as A |
| C LLM-direct-decision | typed proposal | isolated direct baseline | none |
| D Oracle upper bound | evaluator-only truth | frozen evaluator upper bound | none |

The D0 result provider is `offline-fixture/deterministic-evidence-provider@0.1`. A real `OpenAICompatibleEvidenceProvider` and HTTPS transport are implemented and integration-tested with a mock transport, including typed JSON parsing and token/latency/cost accounting. No external model was selected or called, so the result remains a fixture result rather than a real-LLM result.

## Independent tuning and sealing

Validation seeds are 101 and 103. Sealed test seeds are 211 and 223. The D0 adapter enforces household, scene, object-instance and object-family disjointness. Every four-track arm and every ablation receives its own `IndependentTuningReceipt`; each receipt contains all candidate hashes, validation episode IDs, selected objective and the common search budget. Test IDs are contractually forbidden from receipts.

The pilot grid has three candidates per arm and covers likelihood calibration; actor/mechanism/role weights; unknown/unresolved priors; ORRER retraction/reactivation; PCHMP; BOCPD hazard; CCRR create/reactivate/stay; RGRC write/quarantine/retract; action utility; and prompt, temperature and candidate count. Some knobs are currently protocol-bound but not yet connected to a runtime injection hook; they must not be interpreted as completed causal tuning. A `SealedHeldOutRunGuard` hashes the frozen receipts, arm list and ablation list and permits one test opening.

## Structural ablations

All 19 requested cuts are enumerated, topology-verified, independently retuned, and executed on D0. PCHMP prior-only/sequential scoring, ORRER in-place/full-rerun, unknown-axis removal, mechanism/role removal, CCRR and RGRC cuts use dependency injection. `no provenance firewall` and `no deduplication` exist only as evaluator-sandbox strategy objects; production components do not expose safety-disable switches.

## Metrics and statistics

The frozen action evaluator supplies put-back/search success, action regret, path/time/cost, owner-habit contamination, recovery latency/cost and unknown calibration. The experiment adds revision precision and LLM token/latency/cost. Reports include case values, means, deterministic bootstrap 95% intervals, worst episode/group, paired differences against No-LLM and effect sizes.

Holm multiple-comparison correction is predeclared. With only two sealed test households, inferential p-values and hierarchical confidence intervals are not scientifically estimable; the report says so instead of presenting false significance. ECE/NLL are not used as stand-alone support for action-level superiority. Prompt/model robustness is contract-tested through cache/provenance invalidation; a real multi-provider robustness estimate remains unavailable until the user chooses providers and budget.

## Evidence boundaries and open gates

| Layer | Current evidence | Claim boundary |
|---|---|---|
| synthetic D0 | implemented replay and deterministic adapter fixture | plumbing and contract only |
| simulator/manual replay D1 | adapter contract only | unavailable |
| real perception replay D2 | adapter contract only | unavailable |
| household execution D3 | adapter contract only | unavailable |
| embodied robot D4 | adapter contract only | unavailable |

User decisions still required: LLM/VLM providers and versions; local versus hosted inference; privacy/cost/latency limits; prompt families; D1-D4 data or collection route; number of households, object families and seeds; robot platform and safety protocol. No external dataset is selected by this work.

## D0 pilot result (2026-08-24)

Configuration: validation seeds 101/103, sealed test seeds 211/223, 16 steps per episode and three validation candidates per arm. The held-out test was opened once per run after receipts and the ablation list were frozen. Repeated fresh dataset construction produced the same primary results after the UUID tie-break leakage fix.

| Track | Put-back error, 95% CI | Search success, 95% CI | Action regret, 95% CI | Search cost, 95% CI | Owner contamination, 95% CI | Unknown Brier, 95% CI | Revision precision, 95% CI | Fixture tokens, 95% CI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| No-LLM core | 0.0938 [0, 0.1875] | — | 5.5 [5, 6] | — | 0.0313 [0, 0.0625] | 0.1301 [0.1268, 0.1334] | 0.8920 [0.875, 0.9091] | 0 [0, 0] |
| LLM as evidence | 0.3438 [0.125, 0.5625] | — | 9.5 [7, 12] | — | 0.1563 [0, 0.3125] | 0.0980 [0.0633, 0.1327] | 1.0 [1, 1] | 902 [896, 908] |
| LLM direct decision | 0.5625 [0.5, 0.625] | — | 13.0 [13, 13] | — | 0.4375 [0.375, 0.5] | 0.0663 [0.0663, 0.0663] | 1.0 [1, 1] | 902 [896, 908] |
| Oracle upper bound | 0 [0, 0] | 1.0 [1, 1] | 0 [0, 0] | 1.0 [1, 1] | 0 [0, 0] | 0 [0, 0] | 1.0 [1, 1] | 0 [0, 0] |

Recovery cost was 0 for No-LLM, LLM-evidence and oracle, and 2.25 [0, 4.5] for direct decision. The fixture reports zero latency and dollar cost by construction; those are not measurements of a real provider.

On these two D0 test households, LLM evidence ties No-LLM on put-back, search, regret, path cost and contamination; it improves the audit ratio called revision precision but worsens unknown Brier. Direct LLM decision loses materially on put-back error, regret, contamination and recovery cost. Oracle wins on search and regret. These are engineering observations from a tiny deterministic-fixture pilot, not statistical or paper-level superiority. With two groups, the bootstrap intervals are descriptive, hierarchical inference is unavailable, and Holm-corrected significance is not claimed.

All 19 ablations now contain action deltas. The largest changes against LLM-as-evidence were: `no LLM` = put-back −0.25/regret −4; `LLM prior/direct` and `LLM direct decision` = +0.21875/+3.5; `failure-only` = −0.125/−2; `no unknown actor` = +0.0625/+1. Several other cuts were zero on this tiny pilot. These results show that the deterministic evidence fixture harms action outcomes; they do not establish that real LLM evidence will do so.
