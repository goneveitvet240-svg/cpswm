# Task 12 Rejuvenation Diagnostic Report

Evidence status: `UNAUTHENTICATED_DIAGNOSTIC` / `LOCAL_DIAGNOSTIC_ONLY`
Baseline: `BASELINE_AE27B85_CONDITIONAL`
Protocol drift: `PROTOCOL_DRIFT_UNRESOLVED`

## Outcome

All 26 frozen G1/G2 x Task 11 policy conditions were retained and crossed with all four Task 12 kernels. No particle budget, resampling policy, rejuvenation kernel, or stationarity threshold has been selected.

- Upstream conditions: `26`.
- Condition x kernel combinations: `104`.
- Raw scenario/seed executions: `7488`.
- Upstream fidelity-failed conditions retained: `26/26`.
- G1 raw SHA-256: `ba8a65be047cc8ddd8df3c491622be682ed8f2dc4a47177dd46a0c148571dfb8`.
- G2 raw SHA-256: `ae5a34edf8c76b792a27f980c753bc552964231e7115874bb27618fa0d49d51a`.
- Deterministic result SHA-256: `66b3a62d976cff28ed8926368d182dddd9ab741e3ec27aa5c0614699ae74de73`.

## Kernel reality checks

`single_site_typed_metropolis_hastings` uses only Hamming-distance-one typed moves. `blocked_typed_metropolis_hastings` uses multi-axis, direction-dependent proposals with explicit forward/reverse correction. Exact conditional Gibbs uses rows equal to pi and is tagged `evaluator_oracle`; it is never selectable.

- Zero-accept paths: `658`.
- Full-accept paths: `45965`.
- Accepted non-self moves: `50345`.

## Interpretation boundary

Each upstream condition remains separate. Fidelity-failed Task 11 conditions are labelled conditional falsifications, not removed or averaged. The remaining rows are diagnostic-only because Task 10 and Task 11 lack formal resolution receipts. The finite D0 projection supports mechanism checking, not external validity or a formal full-chain binding claim.

```text
formal_task_12_passed=false
formal_binding_resolved=false
selected_kernel=null
task_13_unlocked=false
proposal_p5_unlocked=false
seven_operator_ablation_authorized=false
```
