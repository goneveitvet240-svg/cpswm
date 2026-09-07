# Structure Two Task 11 full-budget resampling diagnostic

Date: 2026-09-06
Evidence status: `UNAUTHENTICATED_DIAGNOSTIC` / `LOCAL_DIAGNOSTIC_ONLY`
Producer source commit: `b9d44d7f34b31c8eee35d00e0c01ef27f11d1494`

## Outcome

This is the complete frozen-budget local diagnostic matrix. It is not complete/formal Task 11. The earlier K=24-only run is retained separately as a historical local pilot. The pre-audit full-budget package is superseded by this adversarial rerun.

```text
formal_binding_resolved=false
task_12_unlocked=false
seven_operator_ablation_authorized=false
```

No formal particle budget was selected.

## Budget- and context-dependent results

### G1

| Budget | Candidate | Disposition |
|---:|---|---|
| 8 | `null` | `RAN_ELIGIBLE_NO_SELECTION` |
| 16 | `null` | `RAN_ELIGIBLE_NO_SELECTION` |
| 24 | `null` | `RAN_ELIGIBLE_NO_SELECTION` |
| 48 | `null` | `RAN_ELIGIBLE_NO_SELECTION` |
| 96 | `null` | `RAN_ELIGIBLE_NO_SELECTION` |
| 384 | `null` | `RAN_ELIGIBLE_NO_SELECTION` |
| 1536 | `null` | `RAN_ELIGIBLE_NO_SELECTION` |

`budget_dependent=false`

### G2

| Budget | Candidate | Disposition |
|---:|---|---|
| 24 | `null` | `RAN_ELIGIBLE_NO_SELECTION` |
| 96 | `null` | `RAN_ELIGIBLE_NO_SELECTION` |
| 384 | `null` | `RAN_ELIGIBLE_NO_SELECTION` |

`budget_dependent=false`

Across shared budgets, `context_dependent_results=false`.

## Evidence

- Conditions: `130`.
- Raw traces: `11856`.
- Zero-event raw traces: `11720`.
- Multi-event raw traces: `0`.
- G1 raw SHA-256: `a376e388ffca51f218c689d4511039731d86184655ef58c0aff86bfb78a74dae`.
- G2 raw SHA-256: `3c898abdbc490c60ef2a1082814b72104fd115879f2bf4792c3ae146af2b82fa`.
- Raw-only recomputation and fresh-source replay are separate required gates.
- Approximate posterior, unresolved mass, log normalizer, action posterior, owner mass, post-resampling weights, and unknown-support flags are reconstructed without trusting runtime posterior or evaluator annotations.

## Unclosed formal trust dependencies

No independently enrolled Task 10 resolution receipt, external timestamp authority, independent artifact custody, or independent execution witness exists. Local commit and hash consistency therefore cannot establish historical authenticity or formal state transition.
