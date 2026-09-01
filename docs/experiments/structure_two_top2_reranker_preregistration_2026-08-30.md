# Structure Two visible-only top-two reranker preregistration

Date: 2026-08-30  
Protocol: `structure-two-reversible-multiaxis-top2-reranker@0.1`  
Status: development-only falsifier frozen before its first run

## Hypothesis

The full seven-operator Structure-Two runtime already places the correct action target in its
leading two candidates often enough that a visible-only pairwise action layer can reduce frozen
action regret without changing candidate generation.

## Fixed method

- Retain the complete seven-operator runtime and its operator receipt.
- Build one auditable evidence card per leading candidate from visible location mass, recency,
  frequency, actor, identity, cause, regime, unknown, and reversible-ledger support.
- Train separate antisymmetric linear heads for search and put-back.
- Use training truth only to label the immediate regret difference between candidates A and B.
- Tune only the two abstention thresholds on disjoint calibration seeds.
- At inference, allow only keep, swap, or abstain; abstention preserves the deterministic order.
- Never add a new candidate and never read evaluator truth during inference.

## Splits and comparisons

- Training seeds: eight new seeds in the manifest.
- Calibration seeds: four disjoint new seeds in the manifest.
- Validation: reuse the eight prior strongest-neighbor validation seeds across all six families.
- Sealed strongest-neighbor holdout: unopened.
- Primary comparison: reranker minus deterministic conflict-transition action regret.
- Required external comparison: reranker minus the previously frozen BrainCTL matched reference.
- Paired interval: bootstrap validation seed as the cluster across all six families.

## Development gate

The route passes this development gate only if all audit gates pass, the paired 95% interval is
strictly below zero against both deterministic transition and frozen BrainCTL, every required-gain
family improves, and all prior guardrail-family margins hold. Failure does not authorize removing
any Structure-Two capability; it rejects this visible-feature linear reranker as the current fix.

## Known limitation

The frozen evaluator makes the immediate `H=1` action-regret label exact. It does not supply a
faithful action-altered future observation stream, so this run cannot honestly claim a longer
horizon counterfactual. A longer-horizon branch requires a simulator in which the selected search
or put-back action changes subsequent observations and state.
