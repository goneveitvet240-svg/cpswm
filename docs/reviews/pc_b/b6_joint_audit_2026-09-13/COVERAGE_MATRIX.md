# B6 independent coverage matrix

| Requirement | Legal control | Adversarial/counterfactual | Result |
|---|---|---|---|
| Full joint correlation | Two distributions with identical role, instance and cause marginals | Correlated versus independent role-instance pairing | Task EVSI 0.4 versus 0.0; action changes as expected |
| Cause versus full-joint information | Same cause marginal and role observation | Independent joint entropy calculation | Planner cause IG 0.0 while full-joint IG is 0.8 bits; distinction confirmed |
| Unresolved/unknown mass | Real prepared view retains 0.19522184894644604 unresolved mass; unresolved-only belief | Empty belief | Unresolved accepted/no action; empty belief rejected |
| No action support | Valid unresolved-only belief and complete utility tables | Empty action tuple | No action selected, but stop reason is incorrectly privacy-blocked (B6-F3) |
| Dirichlet/RLS/information increment | 25 seeded SPD random systems | Independent NumPy equations | 25/25 matched at rtol/atol 1e-12 |
| Accumulate/retract/correct/parent restore | Two retained measurements and parent state | Remove or replace one retained measurement | All five blocks and cluster lineage reconstruct correctly |
| Dimension/nonfinite/matrix validity | SPD legal covariance | Singular, asymmetric, wrong dimension, NaN, infinity, duplicate cluster | 6/6 rejected |
| Source/model identity for analytic blocks | Same source/model and numeric contribution | Different source/model with identical numeric contribution and cluster ID | Same state reference; declared pure-arithmetic limitation, not source authority |
| Particle closure | Real prepared batch/records | Remove one positive-mass record | Rejected |
| Runtime/source-frame binding | Real runtime ID and recorded source hash | Foreign runtime ID; changed source-frame hash | Both accepted by `from_batch` (B6-F1) |
| Belief-to-action/table binding | Current belief digest | Change only `source_snapshot_sha256` | Identical plan; planner never consumes digest (B6-F2) |
| Cold public entrypoints | Import either new module | First conditional rebuild, required prior import, first joint view digest | Module import passes but all public operations fail circularly (B6-F4) |
| Prepared seam | Existing real posterior plus explicit prepared candidates | Stale snapshot, missing records, mutable attacks | Frozen delivery cases pass |
| Default production path | Static source reference inventory | Search outside the two component modules | No production caller found; default closure remains absent |

