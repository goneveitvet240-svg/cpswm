# Structure Two transition proposal + historical reactivation gate result

Date: 2026-08-29  
Protocol: `structure-two-transition-reactivation-gate@0.1`  
Evidence level: **D0 synthetic mechanism evidence（D0 合成机制证据）**

## Result first

The preregistered joint mechanism gate passed, but the causal ablation does **not** support a joint-mechanism or reversible-consolidation claim.

- `conflict-aware transition proposal（冲突感知转移提议）` produced a stable action-level gain.
- `historical regime reactivation（历史阶段复苏）` executed, but its measured action-level contribution was exactly zero.
- The joint arm was slightly worse than transition proposal without consolidation, so there is no evidence of positive `joint synergy（联合协同）`.
- The joint arm still lost substantially to `corrected AMG（修正后的 AMG）`; this round does not support overall Structure Two superiority.

Accordingly, the method-level result is: **retain the complete seven-operator Structure Two, promote the transition proposal to a validated candidate mechanism, and keep historical reactivation as an unvalidated mechanism requiring redesign.**

## Frozen design

Four fresh scenario families（新场景族） and twelve sealed holdout seeds（封存留出种子） were fixed before formal evaluation:

1. `transition_cause_regime_flip`
2. `transition_long_regime_reactivation`
3. `transition_identity_guardrail`
4. `transition_role_guardrail`

All seven arms consumed the same visible stream, used particle budget `K=24`, and ran for at most 28 steps. The complete Structure Two arms retained the seven-operator runtime receipt and the action readout consumed actor, identity, cause, and regime state.

## Formal paired results

Negative values favour the first arm because the endpoint is net action loss per step.

| Paired comparison | Mean difference | 95% paired cluster interval | Interpretation |
|---|---:|---:|---|
| joint − sequential particle, no consolidation | **−0.01488** | **[−0.02232, −0.00744]** | preregistered primary gate passed |
| joint − immediate conflict quarantine | **−0.01786** | **[−0.02530, −0.01042]** | joint arm improved on the prior consolidation baseline |
| transition proposal, no consolidation − sequential particle, no consolidation | **−0.01637** | **[−0.02232, −0.01042]** | stable transition-proposal contribution |
| reactivation − immediate conflict quarantine | **0.00000** | **[0.00000, 0.00000]** | no action-level reactivation contribution |
| joint − per-step particle projection | **−0.03125** | **[−0.04762, −0.01637]** | joint arm beat the non-sequential particle projection |
| joint − corrected AMG | **+0.30960** | **[+0.25888, +0.34829]** | joint arm remained substantially worse than AMG |

The implied joint-minus-transition-only difference is `+0.00149`: adding reactivation did not improve the transition proposal and slightly worsened the aggregate endpoint.

## Family-level primary differences

For `joint − sequential particle without consolidation`:

| Family | Difference | Gate role |
|---|---:|---|
| cause/regime flip | **−0.02381** | required cause gain passed |
| long-regime reactivation | **−0.01786** | required recurrence-family gain passed |
| identity guardrail | **0.00000** | no identity regression |
| role guardrail | **−0.01786** | no role regression |

The recurrence-family gain must not be attributed to reactivation: the dedicated reactivation ablation was zero in aggregate, while transition receipts were action-effective. Reactivation receipts occurred, which rules out the simpler explanation that the code path never ran, but the restored ledger distribution did not change downstream actions.

## Integrity and mechanism checks

All preregistered mechanical checks passed:

- operator receipt completeness;
- particle ancestry preservation;
- conflict-transition execution;
- reactivation execution;
- exactly-once promotion;
- identity and role guardrails;
- sealed-seed commitment checks.

Independent deterministic recomputation returned `verified: true`, `recomputed: true`, and reproduced content hash:

`f093c14f803c398251e1444365336ec0bf5da3f8b060b54be6ea4a3a555267db`

## Scientific decision

This round supports one narrow but substantive method claim: **a conflict-aware cause/regime transition proposal improves action outcomes over the matched sequential particle runtime on these newly sealed synthetic families.**

It does not support any of the following claims:

- the reversible reactivation operator improves actions;
- transition proposal and reactivation have positive synergy;
- the complete Structure Two beats corrected AMG;
- the selected `Neural Amortized Proposal（神经摊销提议）` has been validated—the proposer in this gate is deterministic, not neural;
- D0 synthetic evidence is sufficient for a paper-level superiority claim.

The next experiment should therefore preserve all seven operators but isolate the transition mechanism: replace the deterministic conflict sharpening with a neural amortized proposal under a frozen matched-proposal protocol, while retaining transition-only, reactivation-only, joint, sequential-particle, per-step-particle, and corrected-AMG arms. Historical reactivation should receive a separate action-coupling redesign before it is credited as a contribution.

## Artifacts

- Preregistration: `docs/experiments/structure_two_transition_reactivation_gate_preregistration_2026-08-29.md`
- Manifest: `configs/project_two_experiments/structure_two_transition_reactivation_manifest_v0_1.json`
- Sealed seeds: `configs/project_two_experiments/structure_two_transition_reactivation_sealed_seeds_v0_1.json`
- Formal artifact: `artifacts/project_two_v04_development/structure_two_transition_reactivation_gate_v0_1.json`
- Runtime implementation: `src/cpswm/system/evaluation_operations/structure_two_transition_reactivation.py`
- Runner: `apps/evaluation_runner/run_structure_two_transition_reactivation.py`
- Tests: `tests/test_structure_two_transition_reactivation.py`

## Limitations

- synthetic mechanism evidence only;
- deterministic proposal rather than a learned neural proposer;
- repository-local sealed seeds;
- corrected AMG remains a matched adapter;
- no RGB-D, embodied simulator, or robot-execution evidence.
