# Log-weight repair — adversarial review 1

**PASS within the bounded canonical controlled-profile scope below.** No new product blocker was found in frozen source `1bd6c204d349024196c23df12cca61dbcea91e6c`. This is permission to proceed to the next sequential review, not a completed R2 gate or permission to start the real archived experiment.

This reviewer previously implemented the offline residual model and controlled numerical diagnostic, but did not implement this numerical/identity repair. The review is **computer A auxiliary review with prior author overlap, not B independent acceptance**. No production, test or tool source was changed during review. No Unity process or real 96-frame experiment was run. Old failed attempts and sealed directories were preserved.

## Frozen identity and execution

Worktree: `/private/tmp/cpswm-pc-a-soft-position-factor-20261001`.
Evidence root: `/Users/pangwei/Documents/ai/continual-personalized-semantic-world-model/output/soft-position-factor-20261001/LogWeightR1`.

Both runners required the full frozen SHA, an empty `git status --porcelain`, and equality of all **895 Python files** with `SO/frozen-source.json` before and after execution. All checks passed. The CLI also recomputed the original sealed `R1` directory inventory and found it unchanged. The final audit and all file digests are recorded in `LogWeightR1/evidence-manifest.json`.

| Execution | Actual outcome | Evidence |
| --- | --- | --- |
| Native numeric, source, ownership, history, action and recovery matrix | **68 passed in 453.35 s**, exit 0; no warnings or skipped cases reported | `formal-targeted-01.log` and `.json` |
| Current controlled CLI legal run | Exit 0; 4 fitted position models, 96 frames, 302 files | `CLI/legal-run-01.log` |
| Complete four-model and downstream numerical forgery | CLI verify exit 1, specifically `fresh trained outputs differ`, after all 96 readouts and 4 refits | `CLI/complete-forgery-rejected.log` |
| Original legal fresh verification | Exit 0; all 302 original files unchanged | `CLI/legal-recovery-verify.log` |
| Re-signed candidate cache retaining original external pin | Exit 1 at the historical wrapper's original ledger-pin check; legitimate outputs and forged cache unchanged | `CLI/candidate-deletion-original-pin.log` and `.json` |

The four actual current CLI invocations returned **[0, 1, 0, 1]**. Wrapper orchestration succeeded as expected. The native run comprises 42 cases in three full source test files, 22 copied/adapted or new external cases, and four selected replay/recovery/projection cases. Root's separate 174-test development validation is not added to the 68 executed here.

All executions used `/private/tmp/cpswm-pc-a-camera-checkpoint-fixture-20260930/.venv/bin/python`, `OPENBLAS_NUM_THREADS=1`, and absolute `PYTHONPATH` entries for this worktree's `src`, `tests`, and `tools`. Pytest explicitly received `-c /private/tmp/cpswm-pc-a-soft-position-factor-20261001/pyproject.toml -o addopts= -q`. Exact argv, cwd, environment, source maps, durations, exit status and log digests are in `formal-targeted-01.json`, `CLI/execution-cases.json`, `CLI/complete-forgery-cases.json`, and `CLI/candidate-deletion-original-pin.json`.

Actual orchestration commands, with `PY` and `SO` expanded to the paths above:

```text
PY SO/LogWeightR1/run_formal_targeted.py --sha 1bd6c204d349024196c23df12cca61dbcea91e6c --attempt 01
PY SO/LogWeightR1/prepare_cli_reuse.py 1bd6c204d349024196c23df12cca61dbcea91e6c
PY SO/LogWeightR1/run_formal_cli.py 1bd6c204d349024196c23df12cca61dbcea91e6c
```

Use new attempt/output names for any repetition; do not overwrite this evidence. The native and CLI runners ran concurrently over read-only production source, with separate outputs.

## Legal numerical path and original failure

The copied original R2 stress harness now passes unchanged in its mathematical scenario: a valid owner-declared fixture model produces finite known observation LL **-2465.7563115023117**, while the displayed known probability is **0.0**. Its next neutral step completes, the current decision is readable and exactly one raw key remains consumed. The saved result is `formal-targeted-01/test_finite_owner_configured_d0/result.json`. Earlier source `37981c3...` failed this same continuation at `log(0)`; that old result remains failed and archived.

The expanded matrix separately tests known underflow and unknown-plus-aggregate underflow. Both accepted particles remain in the neural support even with zero displayed probability. Their finite normalized logs survive two neutral steps, repeated publication adds no information, and fresh-process restore followed by a further neutral step succeeds. Both configurations also retract and rebuild to match the no-factor control, then survive SQLite recovery. The pure fresh workers construct no temporary `ContinuousEvidenceInput`; each reports `pure-resume-and-next-neutral: PASS`.

An independent 180-digit Decimal oracle sums the original receipt terms and normalizes them without reading the implementation's normalized-log result. Ordinary values, underflow and a `1e100` common offset agree. The large-offset case retains the -1 relative log difference instead of losing it when summing large floats. The detached underflow case returns `[-10000.0, 0.0, -10000.0]`, retaining both particle IDs. A normalized log outside finite float range explicitly fails; it is not repaired using an epsilon or by silently removing support. These artificial arithmetic probes are detached contracts, not owner-admitted scientific factors.

The two legal underflow posteriors were also consumed through the original unmodified classification collector. Known underflow selected and executed one `RotateLeft`; unknown-plus-aggregate underflow selected STOP and executed zero camera calls. Both outcomes agreed with the same fixed utility's preselected decision, retained the exact log state and semantic ledger, and added no information. The test does not modify utility to manufacture an action. This demonstrates usable control flow, not action benefit.

## Complete prior, raw factor and historical attacks

**Equal display batch does not prove the original prior.** A complete alternative `NativePreviousWeightEvidence` adds the same 2 to every prior receipt term and aggregate, reproduces the identical displayed batch, and carries genuine q. Stage rejects the unadmitted context, and registration using even the original owner authority rejects it because the exact previous weight evidence is not the owned one. The exception traceback is retained while the original producer and normal collector recover, execute `RotateLeft` once, and reject redispatch. The ledger is unchanged. See `test_complete_equal_batch_log_0/result.json`.

The raw-factor protections remain exercised: coherent known/unknown likelihood, aggregate and transition forgeries; altered depth, pose, context and rebound packet; protected proof/profile/catalogue downgrade attempts; future-cutoff/foreign-authority attempts; helper/model binding; and all five sufficient-statistic blocks (`information`, `information_vector`, `alpha`, `a`, `b`). The numerical block attacks rebind references and actually rescore q through the pinned network. They are rejected before acceptance with unchanged state/ledger and legal recovery, rather than being dismissed only as stale q or malformed shape.

The three complete historical reseals are copied from the prior R2 harness and adapted for the new context. Every rebuilt predecessor supplies exact `NativePreviousWeightEvidence` from its newly materialized receipts and aggregate to the next step. Each case first reconstructs the entire legal three-step workspace exactly. It then changes known LL, aggregate mass or a finite position natural-vector entry at the active middle ancestor; reruns q; rebuilds all descendants, receipts, statistics, batches, fingerprints and workspace-local raw contexts/digests; and reverses traversal order. Original model pins and trusted core anchors remain fixed.

All three **full graph** reads reject at `raw candidate base differs from complete owner recomputation`. A call profiler records the actual `verify_raw_base → reconstruct → recompute → produce → position.condition` path. The **descendant-only private validator accepts the internally coherent neutral descendant** in all three cases; the graph check reaches and rejects its false active ancestor. These are different boundaries and must not be conflated.

Normal core reads separately reject the known/aggregate cases at original published-batch binding and the position-vector case at original raw-owner anchors. The collector sends no camera command while corrupted. Exact restoration recovers weights, all statistics and view; duplicate publication adds nothing; the original previously READY command then executes once and cannot be redispatched. Producer, ledger and trusted core anchors remain unchanged. Detailed outcomes and traces are in the three `test_complete_three_step_histo*/result.json` files.

Normal first collector publication at a later cutoff remains covered without manual publication; semantic None/duplicate and genuinely empty-source cases work, removed owned source state refuses continuation, and posterior projection cannot recount the same posterior under another cluster. Pending admission failure preserves a durable pending step and recovers without duplicate effects. Targeted legacy full replay rollback, full neural correction and owned RGB-D recovery remain passing compatibility evidence.

## Loaded code identity and retained failures

Read-only source review confirms that the repair keeps source and loaded-member checks. It uses local full-field marshal-v2 encoding for the controlled helper identity and native workspace checks; it does not replace the generic execution/class/checkpoint protocol or remove helper members/constants from the binding.

The actual helper-stability test retains all **116** helper payloads, enters real `position.condition`, performs **258** active-line identity checks, continues a neutral publication and confirms identical complete payloads afterward. Separate tests preserve distinctions for bool/int, int/float and signed zero; substitute a complete loaded log function, helper function or H constant; produce valid forged q where applicable; reject under the original binding; and recover legally while the rejection traceback remains held.

The pre-freeze root run with 170 passes and one helper-binding misrejection remains preserved in `logweight-final-validation-01.log`; the exact member/payload that changed in that attempt was not captured. The current stability tests and final successful runs support the local deterministic encoding, **not a claim that the original precise trigger was reproduced or conclusively diagnosed**. There were no harness errors or unexpected failures in this formal 68-case/CLI run. Earlier original raw-likelihood failures, the old log(0) failure, and development failures are not relabeled as passes.

## Controlled CLI and remaining scope

The current CLI really rebuilds controlled parent outputs, predicts public surface readouts, fits four residual models and generates corrections, report and numerical diagnostic. The complete forgery replaces all four valid self-pinned model biases, all 96 corrected files and corresponding report/diagnostic/ledger. Fresh fitting rejects it and then exactly reproduces the legal outputs. Model self-signatures therefore still cannot substitute for training provenance.

Historical SDK validation in this package is an explicit controlled wrapper: `official_sdk_history_validated=false`, `unity_started=false`. The original-pin attack is a pin/child-exit boundary check; its broader semantic-summary consistency is not asserted. The CLI-trained controlled models and native fixture models are separate executions. No claim is made that a model trained on the real 96-frame archive has already traversed native owner publication and action consumption.

This is bounded protection for the canonical controlled-position profile, not all legacy candidates or arbitrary simultaneous replacement of trusted process/database roots and external pins. The underflow, history, held-traceback, recovery and action cases are not the complete cross-product of every crash point, history attack, process restart and physical effect. Display probabilities still legitimately underflow; retained log evidence and support provide continuation. Logs whose normalized values exceed the finite representable range intentionally remain errors.

Natural identity association, empirical residual/calibration validity, long-horizon benefit, actual Unity task success, same-semantic-source/new-capture transactions and multiplication of neighboring captures as independent evidence are not established. No formal location reference, scientific threshold or original classification/active-clarification choice was changed. A new sequential R2 is still required before root resumes the fixed real archived experiment.
