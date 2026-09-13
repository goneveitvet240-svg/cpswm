# Second independent whole-task review

Initial fixed candidate: `536ee22454b794a22614d25ab4565fd808ca593e`.
Base: `b196cb81170fae8e0a54f27d14769e728e79aae2`.
Read-only source: `/private/tmp/cpswm-pc-a-unified-continuation-20260914`.

## Initial blocking finding

P2 — Observation delivery alias can rewrite accepted history. `_accept_observation` retains the executor/reconciliation caller's original `ObservationDelivery` in `_observation_status`. Although the outward return and raw observations are copied, the original delivery object is not. After success the executor can mutate retained success/error (and nested fields) via a held reference; a later checkpoint will serialize the altered receipt. Detach and validate delivery at ingress, and retain an owned copy.

Independent reproduction: first test in `test_independent.py`; `initial_valid_stdout.txt` and XML show **1 failed / 4 passed in 2.08 s**. Initial fuller probe draft included an unsupported callable closure in its P5 helper and was correctly rejected; that fixture was corrected to an inspectable bound-method helper. Its rejected run is retained as `initial_full_*` and is not a product defect.

## Independently exercised paths

Synthetic fixture helpers construct records; adverse sequences and assertions are independently authored. Actual production core, graph codec, SQLite store and P5 runtime run in these probes.

- Observation effect happens then transport throws: after closing/reopening, the original action cannot be redispatched; malformed reconciliation does not resolve uncertainty; legal original receipt admits new input without re-execution.
- Effect-only database binds source and dependency identity before any graph checkpoint; changed deployment cannot reuse receipts.
- Registered P5-first actual component path, CIAV physical-effect analogue occurs once, final graph save fails: recovery reuses persisted effect receipt and produces one trace without another executor call; restored assembly and core share object identity.
- Natural producer late capture is inserted into recomputed capture-time association history while raw frame arrival order remains retained. Restoring under a changed detector score threshold rejects.
- A separate Python process and delayed-retraction/next-placement probe are included; final result must be read from its retained output/final run, not inferred from code.

## Whole-task capability matrix and limits

| Requirement | Evidence scope / verdict |
|---|---|
| One continuing runtime graph | Production graph codec preserves mutable aliases/cycles; fixture restore checks actual core identity. Local state hash is integrity, not external custody. |
| Durable intent/receipt and effect failure | P5/observation component probes cover post-effect failure and no optimistic re-execution. Not an exhaustive power-loss or SQLite/OS fault matrix. |
| Cross-process recovery | Separate subprocess probe exercises graph load. Native Unity worker/environment process crash and independent transport receipt retrieval remain outside review. |
| Real perception arrival and late association | Candidate producer recomputes geometric association from retained observations; no verified persistent household identity or role truth. |
| Real uncertainty leads to chosen action | Unity CLI uses a fixed RotateRight scan; the readout contributes a reason string. This is sensor-action plumbing, not validated uncertainty-driven action utility. |
| Multiple explanations / late correction / changed next action | Actual core is exercised with synthetic calibrated-contract fixtures. The natural visual producer still returns None; real pixel candidates do not trigger this semantic path. |
| Real role/contact/release/world pose/calibration | Not established. Caller dependency identities and labels do not authenticate empirical calibration. |
| Complete trained P5 production | A registered engineering route is exercised, not a complete trained full-axis proposer/supervision/utility comparison. |
| Source identity | Store rejects changed caller-supplied deployment digests. Unity CLI hashes source files once and some dependencies; this is not loaded-code attestation, source freeze or independent provenance. |
| Full user's acceptance | **Not established**: real multi-explanation → semantic action → late counterevidence → memory revocation → changed next action remains missing. Component pass counts cannot close it. |

No new real Unity acquisition was initiated by this reviewer because the parent runs the fixed-source real environment probe. That result is external to this independent test execution and must be labeled separately. No full fuzz/resource-exhaustion/crash-kill matrix, calibrated person-role labeling, real placed-object loop, or scientific advantage is signed by this report.

## Final common-SHA independent verification

Final fixed candidate: `9303729debe21924048b98b2a3517cd5f5ec02bf`.

The production repair requires exact ObservationDelivery type and deep-copies it before receipt validation or storage. The independently authored counterexample now passes. All six independent probes ran together on this common SHA: **6 passed in 8.75 s**, recorded in `final_stdout.txt` and `final_junit.xml`; original failure evidence remains unchanged. The six include actual component P5 effect receipt reuse, graph alias checks, subprocess restore and delayed retraction changing an executed next placement, uncertainty reconciliation, late perception recomputation, and dependency binding. No production source was edited by this reviewer; post-run source diff against HEAD is empty.

Final verdict: the reported observation receipt alias P2 is repaired, and no unresolved reproducible blocking issue was found in this review's inspected/exercised engineering paths. This is a scoped whole-task audit with an explicit incomplete capability matrix, not full-user-goal acceptance. The matrix above remains decisive: the genuine pixel producer returns None, the live Unity scan is fixed, and real calibrated semantic multi-explanation/action/retraction plus complete trained P5 remain unestablished.

## Superseding final verification after fresh-process/effect-request changes

Latest common frozen SHA: `e2730d594b6f2608413317426c4348f823cfb182`.

All original six probes plus two newly authored probes pass together: **8 passed in 9.17 s** (`e273_stdout.txt`, `e273_junit.xml`).

1. A separate Python interpreter with no test imports constructs the configured natural producer and resumes a SQLite graph containing two visual/association frames. It restores both interaction observation IDs in order and preserves the system/core alias. Detector inference uses synthetic fixtures before saving; the subprocess uses a minimal configured detector shell only for state restoration. This establishes fresh-process association type availability and graph recovery, not fresh-process real model inference or native Unity process recovery.
2. After an effect raises, closing/reopening the database returns the exact nested request through pending_effects(). Mutating that returned request does not alter retained bytes. Reconciliation with the recovered original request removes it from pending and permits cached receipt reuse without invoking the failing effect. A draft request containing raw bytes was rejected by the existing canonical-hash boundary before dispatch; the retained `e273_fixture_rejection_stdout.txt` is an unsupported test fixture, not a production defect. The final probe uses a supported payload-hash field.

The prior same-process Unity runtime-object recovery remains distinct from this separately executed fresh-process visual-graph test. Post-run `git diff HEAD -- src tools tests` is empty. No production edits were made by this reviewer. Scoped engineering verdict remains unchanged: no unresolved reproducible blocking finding in covered paths, while the full real semantic/action/retraction and trained P5 capability matrix above remains incomplete.
