# Structure Two neural amortized proposal gate result

Date: 2026-08-29  
Protocol: `structure-two-neural-amortized-proposal-gate@0.1`  
Evidence level: **D0 synthetic trained-mechanism evidence（D0 合成训练机制证据）**

## Result first

The preregistered neural mechanism gate **failed**. The trained neural amortized proposal produced a small favourable mean relative to ordinary sequential particles, but its confidence interval touched zero and it was significantly worse than the deterministic conflict-aware proposal.

The failure is method-specific rather than a runtime failure:

- the MLP was trained on 960 training-only visible-belief examples;
- its artifact was frozen before sealed-seed access;
- neural proposal receipts were emitted in all four holdout families;
- all ancestry, seven-operator, same-visible-stream, leakage, and exactly-once checks passed;
- independent deterministic recomputation reproduced the complete result.

Therefore the current `visible-belief self-distillation MLP（可见信念自蒸馏 MLP）` is rejected as a replacement for the deterministic transition proposal. The complete Structure Two and all seven operators remain in scope.

## Frozen training and evaluation boundary

- 8 training seeds, 4 validation seeds, and 12 sealed holdout seeds were mutually disjoint.
- Architecture: `visible-belief-mlp-16x8x5`, one tanh hidden layer.
- Input: visible actor, identity, cause, and regime beliefs plus previous-particle summaries.
- Forbidden inputs: oracle action, latent actor/cause/regime, and holdout seed identity.
- Training: 180 full-batch epochs, fixed initialization seed 108001.
- Training examples: 960.
- Final training loss: `0.6440706`.
- Model hash: `a35f06274ac702e7173b1135ffdb784a9dfdb5a1369917240e59af637f08b2bf`.

One preflight schema correction changed a day-30 unknown event to day 29 before training and before any sealed-seed access, because the scenario generator requires event days to lie strictly before the endpoint. No outcome existed when the correction was made.

## Formal paired results

Negative differences favour the first arm because the endpoint is net action loss per step.

| Paired comparison | Mean difference | 95% paired cluster interval | Result |
|---|---:|---:|---|
| neural transition − sequential no consolidation | **−0.00278** | **[−0.00694, 0.00000]** | primary strict-improvement gate failed |
| neural transition − deterministic transition | **+0.01528** | **[+0.00833, +0.02222]** | deterministic noninferiority gate failed |
| deterministic transition − sequential no consolidation | **−0.01806** | **[−0.02500, −0.01111]** | deterministic mechanism replicated positively |
| reactivation − sequential no consolidation | **+0.00278** | **[0.00000, +0.00694]** | reactivation weakly harmed action outcome |
| neural joint − neural transition | **+0.00764** | **[+0.00278, +0.01319]** | reactivation significantly harmed the neural arm |
| neural joint − corrected AMG | **+0.36229** | **[+0.34038, +0.38420]** | complete joint arm remained far worse than AMG |

## Family-level neural contribution

For `neural transition − sequential no consolidation`:

| Family | Difference | Gate interpretation |
|---|---:|---|
| cause switch | **−0.01111** | required cause gain passed |
| short regime switch | **0.00000** | required regime gain failed |
| identity guardrail | **0.00000** | guardrail passed |
| actor/role guardrail | **0.00000** | guardrail passed, but no gain |

The neural runtime emitted 130, 115, 129, and 116 proposal receipts in the four families respectively. Receipt execution therefore cannot explain the absent action effect. The network changed proposals frequently but failed to reproduce the deterministic proposal's action-relevant transition releases, especially in regime and actor/role conditions.

## Gate result

Failed preregistered criteria:

1. primary interval upper bound was `0`, not below `0`;
2. neural proposal was worse than deterministic proposal by a confidence interval entirely above the `+0.01` noninferiority margin;
3. required regime-family gain was zero.

Passed integrity and guardrail criteria:

- required cause gain;
- identity and actor/role noninferiority guardrails;
- trained model frozen before holdout access;
- no forbidden model inputs;
- all operator, ancestry, neural-receipt, and exactly-once gates.

Independent recomputation returned `verified: true`, `recomputed: true`, and reproduced report content hash:

`60f86b3f3911b41fca9c0965230d8584724ac63b1698774957cd1d6160c02879`

## Scientific interpretation

The strongest supported mechanism remains the deterministic conflict-aware cause/regime transition proposal. It replicated its action gain on another set of fresh sealed families. The present MLP mostly learns a smooth approximation of the current visible belief, but the useful deterministic mechanism performs a structured operation: detect disagreement with particle ancestry, release persistence, and sharply redistribute cause/regime proposal mass. Visible-belief modal self-distillation does not directly supervise that operation.

This round does not support claims that:

- the selected neural amortized proposal has been validated;
- historical regime reactivation contributes positively;
- the neural and reactivation mechanisms have positive synergy;
- the complete Structure Two beats corrected AMG;
- D0 synthetic results establish external or paper-level superiority.

## Next falsifiable method step

Preserve the full Structure Two, but replace belief self-distillation with `structured residual transition learning（结构化残差转移学习）`:

1. keep the deterministic transition kernel as an explicit prior;
2. train the neural component to predict bounded residuals over cause/regime transition scores and persistence release, rather than reproducing the current belief posterior;
3. supervise it with training-only counterfactual action regret or deterministic-kernel advantage targets, with an explicit stop-gradient and evidence firewall;
4. compare deterministic-only, neural-residual-only, deterministic-plus-residual, reactivation-only, full joint, sequential, per-step, and corrected-AMG arms on new sealed families;
5. require a direct action-level advantage over the deterministic kernel before crediting neural amortization.

This is an architecture-level repair, not holdout-driven retuning of the failed MLP.

## Artifacts

- Preregistration: `docs/experiments/structure_two_neural_amortized_proposal_gate_preregistration_2026-08-29.md`
- Manifest: `configs/project_two_experiments/structure_two_neural_amortized_manifest_v0_1.json`
- Sealed seeds: `configs/project_two_experiments/structure_two_neural_amortized_sealed_seeds_v0_1.json`
- Model artifact: `artifacts/project_two_v04_development/structure_two_neural_amortized_model_v0_1.json`
- Formal result artifact: `artifacts/project_two_v04_development/structure_two_neural_amortized_gate_v0_1.json`
- Implementation: `src/cpswm/system/evaluation_operations/structure_two_neural_amortized.py`
- Runner: `apps/evaluation_runner/run_structure_two_neural_amortized.py`
- Tests: `tests/test_structure_two_neural_amortized.py`

## Limitations

- D0 synthetic trained-mechanism evidence only;
- visible-belief self-distillation targets rather than external labels;
- repository-local sealed seeds;
- corrected AMG remains a matched adapter;
- no RGB-D, embodied simulator, or robot-execution evidence.
