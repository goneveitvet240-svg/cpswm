# Structure Two / Route C v0.2 two-round adversarial audit (2026-09-08)

## Verdict

The two-round audit found four verifier or evidence-chain defects and repaired all four.
The checked-in Route C v0.2 artifact now binds configuration, generator/verifier
implementation, command-line runner, base route, neural proposal, and the live
seven-operator production assembly to the checked-out source bytes.

This is an engineering and D0 synthetic-evidence result. It does **not** establish
real-robot external validity, independent custody, paper-level superiority, Task 8
formal success, or the causal necessity of every operator.

## Round 1: real data flow and state-machine attacks

| Attack | Pre-repair result | Repair | Post-repair gate |
| --- | --- | --- | --- |
| Ask the production manifest to prove assembly after replacing the live instance table with an OPCEU-only table | The former builder would not have consulted a live runtime | The builder now constructs `StructureTwoProductionSystem`, verifies exact order and types, and derives runtime types from its live instances | Manifest generation fails closed on a missing/reordered operator |
| Declare an arbitrary object as an allowed operator override | A non-empty override could bypass exact type checking | Overrides are limited to the registered PCHMP evaluator classes, exact arity, and the `consume` interface | An arbitrary object is rejected |
| Forge the corrected-state feedback chain and recompute artifact hashes | Rejected | Existing trace-to-next-step semantic recomputation retained | Rejected before trust-map acceptance |
| Replace registered neutralization semantics with an innocuous unchanged-state explanation and rebuild receipt hashes | Rejected | Existing per-operator semantic checks retained | Rejected |
| Remove RGRC negative-case ledger evidence and re-sign | Rejected | Existing ledger replay and reachability checks retained | Rejected |
| Leak evaluation truth into the training policy or exploit JSON boolean/integer coercion | Rejected | Existing split firewall and strict scalar typing retained | Rejected |

Round-1 conclusion: the production assembly claim is now based on a constructible live
runtime, not only importable class names. The runtime owns all seven operator modules.
The main transition path executes the event/memory/regime chain; CIAV remains a
conditional verification branch and is exercised through the factorial/action
evaluation path rather than being forced on every transition.

## Round 2: forged-but-complete, substitution, replay, and version-drift attacks

| Attack | Pre-repair result | Repair | Post-repair gate |
| --- | --- | --- | --- |
| Modify the command-line generator/verification runner while leaving the bound module and config unchanged | Runner bytes were not bound | Added an exact repository-local runner path and SHA-256 source binding | A rehashed runner substitution is rejected |
| Keep only the seven headline trust entries while thousands of nested positive receipts remain asserted | Trust coverage was partial | Enumerate every `true` JSON output and deterministically assign its registered dependency chain | The artifact contains 3,998 exact positive-output paths; deleting one and re-signing is rejected |
| Substitute a production operator source hash, then recompute both nested and outer hashes | Rejected | Live assembly recomputation retained | Rejected |
| Substitute non-finite values, integer fields with booleans, RGRC location support, split example hashes, or extra claim fields | Rejected | Strict schema, finite-number, support, and source-regeneration checks retained | Rejected |
| Forge a metric or positive paper-level claim and self-sign the artifact | Rejected | Raw-row semantic recomputation and negative claim boundary retained | Rejected |
| Replay a self-consistent stale/substituted receipt set | Rejected under fresh replay | Source-bound fresh recomputation retained | Rejected |

## Versioned trust surface after repair

- Artifact schema: `0.2.0`
- Protocol: `structure-two-full-scientific-loop@0.2-development`
- Production system: `structure-two-production-system@0.2`
- Seven operator order: OPCEU, ORRER/CHEH, PCHMP, CF-BOCPD, CCRR, RGRC, CIAV
- Source bindings: Route C configuration, base-route configuration, Route C
  generator/verifier implementation, command-line runner, base-route implementation,
  and neural-proposal artifact
- Production assembly evidence: exact import classes, checked-out source hashes,
  forward edges, feedback edge, live instance types, and runtime assembly verification
- Positive-output coverage: all 3,998 asserted boolean paths, including per-step state,
  operator, fairness, ledger, and neutralization receipts

## Remaining boundaries and blockers

1. `task_8_formal_passed` remains false: the learned joint interaction has not beaten
   the fairly matched factorized route on the registered action/utility outcome.
2. `all_seven_operator_contributions_established` remains false: complete
   neutralization execution is established, but causal contribution for every operator
   is not.
3. `real_robot_external_validity_established` remains false: the environment is D0 and
   action-responsive, not real-robot evidence.
4. `independent_custody_established` remains false: local hashes and fresh replay prove
   consistency with the checkout, not independent historical authenticity.

These boundaries are deliberately kept as negative claims in the artifact. Passing the
engineering gates must not be interpreted as passing the scientific or external-validity
gates.

## Final verification receipts

- Route C / production-system focused adversarial suite: 38 passed.
- Affected action, factorial, LLM, Route C, and production paths: 94 passed.
- Full repository matrix (engineering-checkpoint tests deliberately excluded from the
  receipt that they subsequently verify): 3,576 collected; 3,574 passed, 1 skipped,
  1 expected failure.
- Mypy source check, Ruff lint, Ruff format check, compileall, and git diff check: all
  exited 0.
- The first full-matrix attempt correctly rejected a stale v0.5 current-worktree
  compatibility summary. After regenerating that non-authoritative current-tree summary,
  the specific regression and the complete matrix passed; the frozen v0.5 compatibility
  status remains false.
- Route C v0.2 artifact SHA-256:
  `623189f2807efa0a633f46d9664f7a57f3dcb4a54e4d2c2e11242973f5d9ae41`
- Production assembly manifest SHA-256:
  `57db4a991b9dbbf30e4420a1ab2143a810c8bfcf4b45c4556f1c31ab9ffd3d04`
- P0 manifest SHA-256:
  `537b41735b0ece15cbca55a460d83f24d8cccae603794ee93ec2b09a3e6730cf`
- Engineering audit receipt SHA-256:
  `1fd9dd1be4bb596faa0347c5fe5d5adb51b5adbead2e27e48d5ce79907e78521`
- Engineering checkpoint SHA-256:
  `656d45bfab2c712be25c6f9148c899ba4fcf68c41c8e561636c17a71ca97a94f`
