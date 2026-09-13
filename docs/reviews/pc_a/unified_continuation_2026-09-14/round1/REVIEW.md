# Independent overall runtime review — round 1

Candidate source: **e62300dbf9d82d6d864031061017671a6ea58da0**, base b196cb81170fae8e0a54f27d14769e728e79aae2. Worktree `/private/tmp/cpswm-pc-a-unified-continuation-20260914`. Production source read only. Independent probes: `.venv/bin/python /private/tmp/cpswm-unified-review1/probe.py` and `graph_probe.py`, run from the candidate. Full `.out` outputs retained; SQLite fixtures and graph JSON retained.

## Reproducible findings requiring repair

1. **P2: stale observation command reaches executor.** In `execute_observation`, only snapshot identity is rechecked, unlike placement dispatch. Probe prepares an observation at t, admits another observation at t+1h, then executes the original command. Actual fixture executor call count is one. No semantic snapshot change is needed to invalidate the causal decision. Check command decision_time against current arrival/cutoff before external effects; observation preparation should also advance the decision watermark consistently.
2. **P2: failed observation receipt does not advance causal arrival.** A failed observation with no pixels is accepted at t+2h. Subsequent admission at t+1.5h succeeds because `_accept_observation` advances arrival only indirectly via nonempty `admit`. Failure itself is received evidence and must advance the watermark. Reject backdated receipt delivery even if observations are empty; preserve uncertain status on invalid receipts.
3. **P2: effect-only SQLite history is not source/dependency bound.** Public `execute_once` is legal before any checkpoint save (also used that way by existing tests). Execute effect under source=a/dependencies=b, close, reopen with c/d, and repeat the same request: the old successful effect result is silently reused. Identity checks occur only if a checkpoint row exists. Persist and validate source/dependency metadata at store initialization, independent of checkpoint existence. Normal continuous initialization saving immediately may reduce exposure but does not repair the store's advertised invariant/API.

## Independent positive checks

- A separate Python interpreter reconstructs a self-referential dict/list graph, preserves repeated ndarray object identity and retains numeric dtype/shape/content.
- A separate process attempting to open a second SQLite writer while the first owns a committed checkpoint is correctly rejected with OperationalError.
- Code inspection confirms intent-before-dispatch and uncertain effect refusal exist; full arbitrary process-kill timing and P5 transport fault matrix were not independently exhausted in this round. Main-thread implementation regressions are not counted as independent probes here.

## Assessment of the complete user objective

1. **Real input produces multiple explanations:** a pixel frontend and common producer history exist, and geometric role alternatives can be retained. This does not supply real calibrated contact/release evidence, physical pose-to-world mapping, independently annotated role calibration or full trained P5 semantics. Candidate geometry cannot be promoted to a validated event posterior merely by persistence.
2. **Explanations drive action; late evidence retracts memory and changes action:** configured P5/legacy and placement/revision paths plus durable effects provide engineering connection points. The observation path has the causal defects above. A fixed Unity camera scan is a real actuator/input transport test, not a model-driven semantic decision loop. Synthetic calibrated producers or executors do not establish that real vision drove a memory correction and a different robot action.
3. **Same-source overall independent acceptance:** this first review binds the fixed source above, but rejects component closure pending the three repairs. It cannot sign overall scientific or real semantic closed-loop acceptance. A repaired final shared SHA requires re-verification and the second independent round; remaining capability gaps must remain explicit.

## Coverage limits

Not established here: real independently labeled calibration; contact/release; continuous metric pose/world mapping; trained full-axis/P5 semantic producer; autonomous utility selection; real late semantic correction changing a physical placement; complete crash/fault matrix for every core/transport boundary; hostile runtime replacement attestation; long-run scientific advantage. State hashes and local SQLite custody are integrity/recovery mechanisms, not independent proof of physical truth. Engineering passing totals cannot change these limitations into an overall pass.

## Final common-source verification

Rechecked **536ee22454b794a22614d25ab4565fd808ca593e**. Independent `final_probe.py` and `final_probe.out` preserve the initial failing evidence and verify both rejection and legal continuation:

- An old observation command after newer admission is rejected before callback (zero calls). A newly issued legal command executes once.
- Its empty failed receipt advances arrival; intermediate-time admission is rejected, while later admission succeeds.
- An effect-only store cannot reopen with changed deployment identities. Reopening with original identities reuses the saved receipt without executing again.

All three original P2 findings are fixed within these exercised paths. Re-ran independent cross-process graph and exclusive writer checks (`final_graph_probe.out`), also passing. No production file changes were made. The overall capability assessment and uncovered items above remain unchanged: this is scoped engineering acceptance, not a real calibrated semantic/P5/action closed-loop pass. Second independent review must bind this same source or trigger another final-source recheck.

## Shared final SHA after round-two alias repair

Final binding: **9303729debe21924048b98b2a3517cd5f5ec02bf**. Re-ran first-round original three issue positive/negative checks as `closure_probe.py`, and independent cross-process graph/single-writer checks as `closure_graph_probe.py`; both completed successfully with corresponding `.out` files retained. New paths preserve initial failing evidence and intermediate re-verification evidence. The observation callback alias-specific review belongs to round two; this round verifies no regression in the original causal/source failures. All prior whole-objective limitations remain: engineering recovery/transport checks do not establish real calibrated semantic inference, late semantic retraction driving a different real placement, or complete user-task acceptance.

## CI and pending-request final-source update

Final reviewed source is now **e2730d594b6f2608413317426c4348f823cfb182**. Re-ran original three issue checks and independent graph/single-writer checks under `e273_probe.py` and `e273_graph_probe.py`, with `.out` retained; all passed.

Additional independent `effect_request_probe.py` / `.out` checks the new pending-request API: intent/request survives close/reopen; returned nested values are detached; changed request reconciliation is rejected; pending outcome cannot trigger redispatch; matching reconciliation clears pending and reuses result without executing; deliberately corrupted saved request document is rejected by hash validation. All passed. This probe corrupts only its isolated fixture database, never candidate production data.

No new blocking issue found in this bounded recheck. The reported broader mypy/regression totals are main-thread evidence, not independently reproduced here. Natural-producer fresh-process type registration was inspected as a dependency fix but the complete new-process perception graph was not independently probed by this reviewer in this update. Prior scope and real-semantic whole-task gaps remain fully applicable.
