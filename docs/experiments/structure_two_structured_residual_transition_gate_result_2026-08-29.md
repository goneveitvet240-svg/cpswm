# Structure Two structured residual transition gate result

Date: 2026-08-29  
Protocol: `structure-two-structured-residual-transition-gate@0.1`  
Evidence level: **D0 synthetic trained residual evidence（D0 合成训练残差证据）**

## Result first

The structured residual transition gate **failed**. Adding the trained action-advantage residual to the validated deterministic transition kernel did not improve action outcomes and had a slightly harmful mean effect.

- `deterministic + residual − deterministic`: `+0.00417`, 95% paired cluster interval `[-0.00139, +0.00972]`;
- `deterministic + residual − sequential`: `−0.00278`, interval `[-0.00694, 0]`;
- `neural residual only − sequential`: exactly `0 [0, 0]`.

The residual runtime and model were mechanically active, all integrity gates passed, and independent recomputation reproduced the result. The current episode-level action-advantage gate therefore has no validated action contribution beyond the deterministic kernel.

The complete Structure Two and all seven operators remain in scope. The validated candidate core remains the deterministic conflict-aware cause/regime transition proposal.

## Frozen training boundary

- 8 training seeds, 4 validation seeds, and 12 sealed holdout seeds were mutually disjoint.
- Model: `structured-residual-gate-16x8x1`, one 8-unit tanh hidden layer.
- Training target: training-only episode action advantage of deterministic transition over sequential particles.
- Inference inputs: the same 16 visible-belief and parent-particle features used by the frozen firewall.
- Oracle action outcomes were used only to construct training targets; they were never inference inputs.
- Model artifact was frozen before validation completion and sealed-seed access.

The model received 327 conflict examples. Its action-advantage-weighted positive target rate was `0.21168`, and final weighted training loss was `0.51143`. Model hash:

`bd59e52aa0859adbce2397dfd9f4d508c4323709306bfd7123c6608086d8aa9b`

## Formal paired results

Negative values favour the first arm because the endpoint is net action loss per step.

| Paired comparison | Mean difference | 95% paired cluster interval | Interpretation |
|---|---:|---:|---|
| deterministic + residual − deterministic | **+0.00417** | **[−0.00139, +0.00972]** | primary residual-contribution gate failed |
| deterministic + residual − sequential | **−0.00278** | **[−0.00694, 0.00000]** | strict improvement over sequential failed |
| neural residual only − sequential | **0.00000** | **[0.00000, 0.00000]** | no independent neural action path |
| reactivation − sequential | **+0.00694** | **[0.00000, +0.01667]** | reactivation remained harmful or neutral |
| full joint − deterministic + residual | **+0.00694** | **[0.00000, +0.01667]** | reactivation did not add joint value |
| full joint − corrected AMG | **+0.37544** | **[+0.34318, +0.40732]** | complete joint system remained far worse than AMG |

## Family-level residual effect

For `deterministic + residual − deterministic`:

| Family | Difference | Gate result |
|---|---:|---|
| cause release | **0.00000** | required gain failed |
| regime release | **0.00000** | required gain failed |
| identity guardrail | **0.00000** | guardrail passed |
| actor/role guardrail | **+0.01667** | guardrail passed within `+0.02`, but residual harmed actions |

All neural residual arms produced non-empty model-bound receipts in all four families. The absent gains are therefore not explained by an inactive code path. The action effect was zero in three families and harmful in the actor/role family.

## Gate accounting

Failed:

- primary confidence-interval gate;
- strict combined-versus-sequential gate;
- required cause gain beyond deterministic;
- required regime gain beyond deterministic.

Passed:

- identity and actor/role noninferiority guardrails;
- model frozen before holdout;
- inference feature firewall;
- seven-operator receipts;
- particle ancestry;
- residual receipt execution;
- exactly-once promotion.

Independent deterministic recomputation returned `verified: true`, `recomputed: true`, with report content hash:

`c898bc00e2285d7e311c5067363342b010eee5ebeca4eb94c4255bd2d22d00f0`

## Scientific interpretation

The most plausible failure mechanism is target granularity, but this remains an inference rather than a proven causal diagnosis. Each conflict event inherited a label derived from the whole episode. An episode can contain both beneficial and harmful transition releases; assigning the same coarse label to every conflict cannot identify which local release changed the downstream action. The low positive target rate also biases the learned gate toward suppressing residual action, consistent with the residual-only arm's exact zero effect.

This round does not support:

- an independent contribution from structured neural residuals;
- positive reactivation contribution or joint synergy;
- complete Structure Two superiority over corrected AMG;
- external or paper-level claims from D0 synthetic evidence.

## Next decision point

Two complete-scope routes remain available:

1. `step-level counterfactual credit assignment（步级反事实信用分配）`: freeze the deterministic transition kernel, fork only at each conflict event, and label the residual with its bounded downstream action-regret delta over a fixed horizon. This directly repairs the coarse target but requires a more expensive counterfactual training generator.
2. `external-validity transition gate（外部有效性转移门）`: retain the deterministic proposal as the current validated mechanism and test it on a more realistic replay source or embodied simulator before further neuralization.

The present evidence rules out merely widening the MLP, adding epochs, or retuning the residual scale on these holdout families.

## Artifacts

- Preregistration: `docs/experiments/structure_two_structured_residual_transition_gate_preregistration_2026-08-29.md`
- Manifest: `configs/project_two_experiments/structure_two_structured_residual_manifest_v0_1.json`
- Sealed seeds: `configs/project_two_experiments/structure_two_structured_residual_sealed_seeds_v0_1.json`
- Model artifact: `artifacts/project_two_v04_development/structure_two_structured_residual_model_v0_1.json`
- Formal artifact: `artifacts/project_two_v04_development/structure_two_structured_residual_gate_v0_1.json`
- Implementation: `src/cpswm/system/evaluation_operations/structure_two_structured_residual.py`
- Runner: `apps/evaluation_runner/run_structure_two_structured_residual.py`
- Tests: `tests/test_structure_two_structured_residual.py`

## Limitations

- D0 synthetic trained-residual evidence only;
- episode-level action advantage is a coarse conflict target;
- repository-local sealed seeds;
- corrected AMG remains a matched adapter;
- no RGB-D, embodied simulator, or robot-execution evidence.
