# Task 12 Protocol Drift Report

Status: `PROTOCOL_DRIFT_UNRESOLVED`

The frozen JSON and Python contract set `max_stationary_distribution_error` to `1e-6`. The Chinese protocol prose states a stationarity threshold of `1e-9`. Neither source has been edited and this diagnostic does not choose between them.

## Separate recomputations

| Interpretation | Threshold | Guardrail passes | Formal selection |
|---|---:|---:|---|
| Frozen JSON/Python | `1e-6` | `0/104` | `null` |
| Chinese protocol prose | `1e-9` | `0/104` | `null` |

The machine-readable result retains all 104 rows under both interpretations. A pass at `1e-6` never substitutes for a failure at `1e-9`. Even if every numerical row agrees, the normative conflict remains unresolved until the user selects the authoritative threshold through the formal protocol process.

```text
formal_task_12_passed=false
selected_kernel=null
task_13_unlocked=false
proposal_p5_unlocked=false
seven_operator_ablation_authorized=false
```
