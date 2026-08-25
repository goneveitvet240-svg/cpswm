# Project Two LLM/VLM Evidence, Tuning, and Ablation Protocol v0.2

Status: implementation and D0 plumbing pilot. This document does not claim real-world or paper-level superiority.

## Frozen scope and adapter position

The adapter has three mutually exclusive roles. A role is part of the typed
request, output and provenance; it is not a report label added after execution.

| Role | Authorized output | Forbidden authority |
|---|---|---|
| M21 query compiler | natural language -> `CompiledSemanticQuery` | no world fact and no M13-M19 write |
| Structure Two evidence provider | actor/mechanism/ordered-role/location prior or candidate evidence | no action output and no M13-M19 write |
| `llm_direct` baseline | direct put-back/search prediction under the same visible prefix, candidate set and action budget | no CHEH/ORRER/PCHMP/Project One write |

The Structure Two adapter path is:

`robot-visible replay -> LLM/VLM request firewall -> deterministic cache -> typed candidate/evidence bundle -> CHEH -> ORRER -> PCHMP -> actor/mechanism/role posterior -> action -> execution feedback -> ProjectTwoFeedbackRevisionLoop -> EventRevisionOutcome -> ProjectOneStatRequest -> explicit Project One API`

The adapter has no reference to event-history mutation or Project One statistics.
The evidence role can emit actor, mechanism, ordered-role and location candidates,
calibrated score, explicit unknown mass, abstention and evidence citations; it cannot
emit actions. The direct role can emit only location/action candidates and is never
projected into typed world evidence. Every executed call records role/authority,
provider, model, version, temperature, exact prompt hash and template version, input
record IDs, content hash, cache key, input/output tokens, latency and cost. Model-facing
visible payloads and prompts cross the truth-leakage firewall before provider invocation.

`CompiledSemanticQuery` now requires non-empty input citations and a complete M21
invocation provenance block; deterministic/oracle query compilers use the same contract,
so a real compiler cannot omit its model, prompt, cache or accounting identity. Provider
invocations and adapter calls are deliberately separate audit layers: a cache miss binds
the source invocation provenance, while every cache hit emits its own call receipt with
`provider_invoked=false`, zero per-call token/latency/cost accounting, and a reference to
the cached source invocation. Cache reuse therefore no longer disappears from the audit
trail or masquerades as another billed provider invocation.

`LLM-direct-decision` is a separate baseline. Its proposal selects an action but it has zero feedback-revision and Project One write calls. `Oracle evidence upper bound` is evaluator-only and does not call the LLM adapter.

## Four method comparisons plus oracle

| Track | Evidence path | Decision path | Project Two writes |
|---|---|---|---|
| A No-LLM core | replay evidence only | full Project Two | only through revision loop and explicit Project One API |
| B LLM-prior-only | actor prior only | full Project Two | same controlled path as A |
| C LLM-as-evidence | typed adapter evidence | full Project Two | same controlled path as A |
| D LLM-direct-decision | direct location/action output | isolated direct baseline | none |
| E Oracle upper bound | evaluator-only truth | frozen evaluator upper bound | none |

`No-LLM`, `LLM-prior-only`, `LLM-evidence` and `LLM-direct` are now separate
top-level arms. The older 2026-08-24 table below predates the top-level prior-only
arm, so it must not be presented as a completed four-way comparison; a fresh powered
run is required.

The D0 result provider is `offline-fixture/deterministic-evidence-provider@0.1`. A real `OpenAICompatibleEvidenceProvider` and HTTPS transport are implemented and integration-tested with a mock transport, including typed JSON parsing and token/latency/cost accounting. No external model was selected or called, so the result remains a fixture result rather than a real-LLM result.

## Independent tuning and sealing

Validation seeds are 101 and 103. Sealed test seeds are 211 and 223. The D0 adapter enforces household, scene, object-instance and object-family disjointness. Every method arm and every ablation receives its own `IndependentTuningReceipt`; each receipt contains all candidate hashes, validation episode IDs, selected objective and the common search budget. Test IDs are contractually forbidden from receipts.

The pilot grid has three candidates per arm and covers likelihood calibration; actor/mechanism/role weights; unknown/unresolved priors; ORRER retraction/reactivation; PCHMP; BOCPD hazard; CCRR create/reactivate/stay; RGRC write/quarantine/retract; action utility; and prompt, temperature and candidate count. Some knobs are currently protocol-bound but not yet connected to a runtime injection hook; they must not be interpreted as completed causal tuning. A `SealedHeldOutRunGuard` hashes the frozen receipts, arm list and ablation list and permits one test opening.

## Structural ablations

All 19 requested cuts are enumerated, topology-verified, independently retuned, and executed on D0. PCHMP prior-only/sequential scoring, ORRER in-place/full-rerun, unknown-axis removal, mechanism/role removal, CCRR and RGRC cuts use dependency injection. `no provenance firewall` and `no deduplication` exist only as evaluator-sandbox strategy objects; production components do not expose safety-disable switches.

## Metrics and statistics

The frozen action evaluator supplies put-back/search success, action regret, path/time/cost, owner-habit contamination, recovery latency/cost and unknown calibration. The experiment adds revision precision and LLM token/latency/cost. Reports include case values, means, deterministic bootstrap 95% intervals, worst episode/group, paired differences against No-LLM and effect sizes.

CCRR receipt application/rejection/defer/replay counts and
`request_application_rate` are operational diagnostics, not paper outcomes. Their
policy is serialized into the experiment report. They cannot substitute for action
utility or external-validity evidence, and they are excluded from the aggregate
paper-result metric table.

## Replay rejection semantic-drift resolution (2026-08-25)

The failing regression was a fixture error, not a swallowed status and not a new
semantic rule that made rejection legal to ignore:

- the old seed-1013 fixture applied feedback immediately after its own transition;
- every generated receipt was `APPLIED`, CCRR remained `stay`, and neither quarantine
  nor deferred queues were populated;
- the test and the relevant implementation entered the repository in the same commit,
  and those files had no intervening change, so the fixture never demonstrated its
  claimed rejection branch;
- a naive delayed-all-feedback replacement produced a stale-lineage rejection, which
  is also not CCRR/RGRC rejection and was rejected as a false fix;
- the replacement fixture freezes seed 10, a 0.05 habit-change gate and 0.5 transient
  gate, materializes the complete visible prefix, and then applies the single delayed
  feedback on step 7. It reaches the explicit `CCRR/RGRC rejected the corrected event`
  receipt and verifies `old_snapshot == new_snapshot` with empty Dirichlet, RLS and
  Hybrid/RGRC deltas.

Holm multiple-comparison correction is predeclared. With only two sealed test households, inferential p-values and hierarchical confidence intervals are not scientifically estimable; the report says so instead of presenting false significance. ECE/NLL are not used as stand-alone support for action-level superiority. Prompt/model robustness is contract-tested through cache/provenance invalidation; a real multi-provider robustness estimate remains unavailable until the user chooses providers and budget.

## Evidence boundaries and open gates

| Layer | Current evidence | Claim boundary |
|---|---|---|
| synthetic D0 | implemented replay and deterministic adapter fixture | plumbing and contract only |
| simulator/manual replay D1 | adapter contract only | unavailable |
| real perception replay D2 | adapter contract only | unavailable |
| household execution D3 | adapter contract only | unavailable |
| embodied robot D4 | adapter contract only | unavailable |

D2 remains closed until powered D0 **and** powered D1 mechanism tests are complete.
The typed progression gate does not accept `d2_allowed` as input. It computes that field
only when both a stage-correct D0 and D1 completion receipt are present. Each receipt is
bound to the mechanism artifact SHA-256, power-analysis artifact SHA-256, protocol
version, completion authority, and an observed sample size that meets the declared
requirement; the receipt itself has a canonical SHA-256. The current deterministic pilot
provides neither powered receipt, so its computed `d2_allowed` remains false.

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

On these two D0 test households, deterministic LLM evidence improves unknown Brier
(0.1301 -> 0.0980) and the audit ratio called revision precision, but worsens
put-back error (0.0938 -> 0.3438), action regret (5.5 -> 9.5) and owner-habit
contamination (0.0313 -> 0.1563). Direct LLM decision is worse again on put-back
error, regret, contamination and recovery cost. Therefore neither this fixture nor a
future real provider may be assumed helpful merely because it improves calibration.
These are engineering observations from a tiny deterministic-fixture pilot, not
statistical or paper-level superiority. With two groups, the bootstrap intervals are
descriptive, hierarchical inference is unavailable, and Holm-corrected significance
is not claimed.

## O-STaR overlap and required method innovation

[The official O-STaR description](https://www.hrl.uni-bonn.de/publications/2026/menon26grc)
already combines LLM common-sense priors grounded by
physical scene geometry, a Dirichlet-Categorical belief over object locations, learned
household relocation patterns and personalized open-vocabulary object search under
partial observability. Consequently, “add an LLM to object search” is functional
overlap, not this paper's innovation.

Project Two keeps the complete route, but a paper contribution must come from a new
method: for example, role-separated authority with provenance-complete evidence
fusion; open-world actor/mechanism/role joint posterior revision; reversible
feedback-to-event-to-habit attribution; or an independently retuned action-utility
gain over O-STaR-style priors. These are candidates to test, not established novelty
claims.

All 19 ablations now contain action deltas. The largest changes against LLM-as-evidence were: `no LLM` = put-back −0.25/regret −4; `LLM prior/direct` and `LLM direct decision` = +0.21875/+3.5; `failure-only` = −0.125/−2; `no unknown actor` = +0.0625/+1. Several other cuts were zero on this tiny pilot. These results show that the deterministic evidence fixture harms action outcomes; they do not establish that real LLM evidence will do so.
