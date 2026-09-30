# Raw factor repair — adversarial review 2

**BLOCKED: 35 tests passed, but one complete legal numerical continuation failed.** This review does not permit the real archived 96-frame experiment to start. The failure is in frozen production SHA `37981c3c44475b0bcbeff3379dcf90be288c49c9`, not a malformed-input or fixture-configuration rejection. Repair requires a new frozen source and a restarted sequential R1/R2 gate.

This reviewer did not implement the production raw-factor repair and independently authored the new R2 history and numeric-stress harnesses. The work remains **computer A auxiliary review, not computer B independent acceptance**, full CI, natural calibration or scientific benefit. No `src`, `tests` or `tools` source was edited; no real 96-frame experiment, Unity process or detector execution was started. Earlier failed `R2/` originals were not overwritten.

## Source and sequence

- Worktree: `/private/tmp/cpswm-pc-a-soft-position-factor-20261001`.
- Every stage checked the exact HEAD, clean worktree and all **894 Python files** against `frozen-source.json` before and after execution. All checks matched. The frozen-record SHA-256 is `f03633c495247e93987b1bda316c3f83ea83813113c3ecba033ea142b0969e0c`.
- R2 started only after root's explicit same-SHA R1-complete signal. The R1 report hash was checked as `8555767db63b418d134340cb2e61ef942bd9e2d45f76c0e255d21babbc2fe8e9`.
- R1's 49 tests, its controlled CLI results, and root's earlier 859/97 results are supporting history, **not added to this review's executed count**.

## Executions

| Stage | Actual result | Bound | Evidence |
| --- | --- | --- | --- |
| New complete three-step history reseals | **3 passed in 33.76 s**, exit 0 | 240 seconds | `RepairR2/formal-history-01.log` and `.json` |
| Raw profile, position, replay, SQLite and fresh-process continuation | **32 passed in 250.89 s**, exit 0 | 300 seconds | `RepairR2/formal-recovery-01.log` and `.json` |
| Additional owner-configured finite-density stress positive path | **1 failed in 5.44 s**, exit 1 | 120 seconds | `RepairR2/formal-numeric-01.log` and `.json` |

No stage timed out. There were no collection errors or skipped tests. The numeric failure is retained as a failed acceptance test, not rewritten to expect the defect.

The stages used `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`, `OPENBLAS_NUM_THREADS=1`, absolute worktree `PYTHONPATH=src:tests:tools`, and explicit `-c /private/tmp/cpswm-pc-a-soft-position-factor-20261001/pyproject.toml -o addopts= -q`. Full argv, environment, source maps, durations, exit codes and log digests are in the three stage JSON records. Reproduction entry point is `RepairR2/run_stage.py` with `history`, `recovery` or `numeric` and an unused attempt suffix. It refuses to overwrite an existing attempt.

## Blocking legal positive path

The root's read-only source inspection identified a possible probability-underflow boundary and asked this reviewer to test it. The new `RepairR2/test_finite_log_weight_continuation.py` changes only the **test fixture's model factory before constructing the producer and owner**:

1. Keep the original public RGB-D packet, affinity model, valid position covariance and other model fields.
2. Set the finite declared position-model bias to `[100.0, 0.0, 0.0]`, compute its proper new external position pin, and successfully restore that model.
3. Construct the original stream and canonical neural/raw producer under that configuration. This is a legal declared fixture stress case, not a post-configuration substitution or a claim about empirical training/calibration.
4. Publish the active observation successfully. Its known observation log likelihood is **-2465.7563115023117**, a finite number. The normalized known particle probability is **0.0** due to floating-point underflow.
5. Advance the next neutral semantic step. Publication fails at `src/cpswm/system/controlled_position_producer.py:505`: `log(weights[parent.state.particle_id])` raises **`ValueError: math domain error`**.

The exact saved result and traceback are in `RepairR2/formal-numeric-01/test_finite_owner_configured_d0/result.json`. They establish successful model acceptance and active publication before the continuation failure. This is not an early pin/configuration mismatch. The complete neutral continuation and any downstream recovery/action after this extreme case remain unpassed.

The producer reconstructs a prior by exponentiating/reading normalized probabilities and then taking their logarithm. Finite log mass can be lost at that round trip. Its unresolved bucket similarly uses `log(previous_batch.unresolved_probability)`; that second boundary was identified by inspection but **was not separately executed in this review**. The repair must preserve the log-domain posterior mass and support through neutral continuation, replay and restore. An arbitrary epsilon or silently dropping the zero-display-probability particle would change the model rather than demonstrate the intended legal continuation. This report proposes no scientific prior, threshold or calibration change.

## Complete history attacks and actual consequences

The new history harness first publishes a legal three-step sequence with the active observation at index 1. A fresh canonical reconstruction of **every** body must exactly equal the original workspace before attacking it. The three independent attacks add 2 to known LL, add 2 to aggregate unresolved log mass, or add 0.7 to one finite position natural-vector component while retaining positive-definite precision and valid support.

For each attack, the harness reconstructs all descendants, actually reruns the pinned neural q, materializes complete receipts, normalizes the native weights, updates state/statistic references, all input-body hashes and record fingerprints, the final batch, descendant raw contexts and workspace-local context digests. The original model pins, profile and **core acceptance anchors remain unchanged**. The journal/body dictionaries are then reversed so the neutral descendant is checked before its active ancestor.

The forged internal unresolved mass after the active step and its neutral descendant is 0.2776566993192501 for the known-LL attack and 0.8586130048958103 for the aggregate attack, compared with the original 0.45111108215249357. These are internally computed candidate-history numbers, **not successfully published posterior results**. The natural-vector attack preserves the mass while altering and propagating its conditional position state.

All three full-workspace reads fail with `raw candidate base differs from complete owner recomputation`. A temporary call profiler, without replacing any production callable, records the actual path through `verify_raw_base → reconstruct → ControlledPositionProducer.recompute → produce → position.condition`. Thus these full-graph failures reach the complete raw mathematical recomputation; they are not merely stale q, wrong source hashes or missing metadata.

**The private descendant-only validator accepts the neutral descendant in all three cases**, because that descendant is mathematically consistent with its rewritten local parent/context. The complete graph validator proceeds to the active ancestor and rejects its false factor. This is not evidence that every descendant separately detects an invalid ancestor, and the report does not make that claim.

Normal owner/core reads also refuse the forged history. The known-LL and aggregate cases first hit the original published-batch binding; the natural-vector case first hits the core's original raw-owner anchors. Those are reported as distinct outer protection checks, not misclassified as mathematical recomputation. The collector dispatches no camera action while corrupted. Exact restoration recovers the original weights, all sufficient statistics and view; repeated publication adds no information. The same previously READY command then executes once through the real collector, and redispatch is rejected. Producer state, semantic ledger and trusted core anchors remain unchanged by the attacks.

The three detailed `result.json` files under `RepairR2/formal-history-01` contain legal and forged chain digests, re-scoring flags, numerical call traces, the separate descendant/core/full-graph outcomes, and the successful legal action recovery.

## Other executed positive and negative paths

The 32-case recovery stage comprises all 18 raw-verification cases, all 11 native-position cases, and three explicitly selected replay/neural-recovery cases. It covers complete current target changes, proof/profile/catalogue downgrade attempts, future cutoff admission, neutral-history preservation and dictionary reordering, loaded-verifier replacement, durable pending admission recovery, normal first-collector later-cutoff paths, raw packet/model/helper binding, controlled CIAV source mapping, SQLite state/deduplication, and raw retraction replay matching the no-factor control.

The fresh interpreter restores the **original saved configuration/models/pins** without constructing another `ContinuousEvidenceInput`, checks exact view/producer/workspace/ledger, repeats publication with no increment, and continues a neutral step. Its output is `pure-resume-and-next-neutral: PASS`. The optional-dependency child reports `none-and-legacy-without-torch: PASS`.

The additional legacy full-replay tests verify interrupted-generation rollback and one recovered controlled camera action; the neural full-history correction test restores exact joint state. Their producer profiles differ from the canonical raw stress test and are not portrayed as the entire cross-product of raw-factor faults, fresh processes, replay generations and physical actions.

## Remaining limits and decision

This is partial coverage of the canonical controlled raw profile under preserved trusted owner/core anchors and external pins. It does not establish security when every process/database trust root can be replaced, natural identity association, empirical likelihood calibration, long-horizon reliability, new-capture same-semantic-source transactions, or action utility. Camera, utility and semantic support are controlled fixtures. Complete cross-product coverage of historical attacks against every SQLite/crash/replay state is still absent.

The new positive-path numerical defect is sufficient to block this source despite the successful forgery protections and 35 passing cases. Root was notified immediately with the actual failure location and evidence. Production source was left unchanged. R2 has no passing gate for SHA `37981c3c44475b0bcbeff3379dcf90be288c49c9`; repair, a new freeze and sequential review are required before the real archived experiment.
