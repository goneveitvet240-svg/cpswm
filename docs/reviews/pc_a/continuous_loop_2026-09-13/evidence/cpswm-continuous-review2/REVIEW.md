# Second independent review — continuous evidence bridge

Initial frozen code: `aef9fc327c829805c63f204c5207bde54cc1096e`.
Worktree: `/private/tmp/cpswm-pc-a-continuous-loop-20260913`.
Independent probe source: `test_independent.py`; helpers use the repository synthetic fixture construction, while assertions and adversarial sequences are independently authored. These are not real perception or physical execution tests.

## Initial result: changes requested

11 independent cases: **1 failed, 10 passed**, 12.11 s. Initial evidence is retained as `initial_stdout.txt` and `initial_junit.xml`.

### P2 — stale command is dispatched before causal timestamp rejection

`execute_placement` checks capability, content hash, uncertainty, snapshot and distribution before calling the executor, but does not check the command's decision time against the advanced causal watermarks. Prepare commands A at t and B at t+10, execute B successfully with receipt t+11, then execute A: the executor is called a second time before `_accept_placement_delivery` rejects A's t+1 receipt. This means a rejected stale command has already caused external side effects and becomes OUTCOME_UNCERTAIN. Reject the expired decision before any executor invocation, or explicitly rebuild/rebind a fresh command.

## Independently passing coverage

- First-review duplicate late-feedback watermark fix: replay a consumed feedback at a later arrival; all three older admit/advance/prepare paths reject without changing core snapshot.
- First-review placement receipt time fix: receipt arrival, end and recorded times inconsistent with command timeline reject.
- Uncertain dispatch blocks another already prepared command.
- Complete schema-valid but mismatched action, object, location and source records cannot reconcile another placement.
- Invalid reconciliation preserves the uncertain journal; valid original receipt resolves without re-invoking the failed transport.
- Duplicate placement reconciliation advances arrival watermark and rejects later backdating.
- Executor callback command mutation cannot alias the session's issued command or retained dispatch.
- Twelve synthetic transition deliveries invoke the actual core; delayed retractions change the next issued location, and hybrid/full rerun equivalence holds.

## Scope

Only the explicitly selected `legacy_component_diagnostic` lane is reviewed. A configured producer/calibration and physical transport remain trusted dependencies; names/hashes do not authenticate them. No real pixel-to-person/pose inference, P5 full-axis neural assembly, trainer, native robot executor, production crash-durable exactly-once transport, scientific benefit, or complete-system acceptance is established here. Schema-valid invented evidence from a trusted producer is not ruled out by this local dependency boundary.

## Final repair verification

Final frozen source: `be6e06348106c5a46ad766c136824c5eab70192a`.
The sole production delta from the initially reviewed SHA adds a pre-dispatch check that command decision time is not before either current arrival or cutoff watermark. The check occurs before creating a dispatch entry or invoking the executor.

The **unchanged independent probe source** was rerun on this final SHA: **11 passed in 7.74 s**. Evidence: `final_stdout.txt`, `final_junit.xml`. The original failing counterexample now confirms the old command is rejected while executor calls remain exactly one. The prior passing receipt, uncertainty, alias, delayed-retraction and watermark probes remain passing.

Verdict: **No unresolved reproducible blocking issue within these inspected and exercised diagnostic-bridge paths.** The initial P2 is repaired. This is a scoped second-round review with repair verification, not a claim of exhaustive coverage or completed unified real-input system acceptance. All scope limitations above remain effective.
