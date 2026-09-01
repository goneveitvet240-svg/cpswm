# Structure Two neural amortized proposal gate preregistration

Date: 2026-08-29  
Protocol: `structure-two-neural-amortized-proposal-gate@0.1`

Preflight correction: before training and before any sealed-seed access, the final unknown-event day in `neural_actor_role_guardrail` was changed from 30 to 29 because the scenario generator requires event days to be strictly below the 30-step endpoint. No outcome or model output existed when this schema-only correction was made.

## Frozen question

The preceding sealed gate found a stable action-level contribution from a deterministic conflict-aware cause/regime transition proposal, while historical regime reactivation executed but had zero action contribution. This gate tests whether a genuinely trained neural amortized proposal（神经摊销提议）can reproduce or improve that transition benefit without hidden-state leakage.

The complete Structure Two and all seven operators remain in scope. This gate isolates proposal generation; it does not remove reversible consolidation or reinterpret a failed operator as absent.

## Frozen data boundary

- Eight training seeds, four validation seeds, and twelve sealed holdout seeds are mutually disjoint.
- The sealed seed file may be opened only after model training and validation-only arm selection finish.
- The MLP input contains only the current visible actor, identity, cause, and regime belief plus the previous particle summary.
- Training targets are the modal cause and regime decision derived from the current visible training belief.
- Oracle action, latent actor/cause/regime, future holdout observations, and holdout seed identity are forbidden model inputs and targets.
- Model weights and their content hash are frozen before the sealed file is opened.

## Frozen model

A deterministic one-hidden-layer MLP（多层感知机） with 16 inputs, 8 tanh hidden units, and 5 outputs is trained for 180 full-batch epochs using learning rate 0.08 and L2 coefficient 0.0005. Four outputs form a cause softmax; one output forms a regime-change sigmoid. Initialization seed is 108001. No holdout-dependent early stopping or retraining is allowed.

## Frozen arms

1. corrected AMG;
2. per-step particle projection;
3. sequential particle without consolidation;
4. deterministic conflict-aware transition without consolidation;
5. neural amortized transition without consolidation;
6. sequential particle plus historical regime reactivation;
7. neural amortized transition plus historical regime reactivation.

All particle arms use `K=24`. Validation may select only from each arm's frozen profile/mixing choices. All complete-system arms retain seven-operator receipts and an action readout that consumes actor, identity, cause, and regime.

## Frozen gates

The neural proposal mechanism passes only if all conditions hold:

1. the 95% paired cluster interval upper bound for `neural transition − sequential no consolidation` is below zero;
2. the 95% interval upper bound for `neural transition − deterministic transition` is at most `+0.01`;
3. neural transition improves both required cause-switch and regime-switch families;
4. identity and actor/role family regressions relative to sequential no consolidation are each at most `+0.02`;
5. a non-empty trained-model hash and neural proposal receipts exist before holdout opening;
6. training, validation, and holdout seed sets are disjoint, raw holdout seeds are not disclosed in the report, and no forbidden feature is consumed;
7. ancestry, same-visible-stream, seven-operator, and exactly-once gates all pass.

Historical reactivation is credited only through its dedicated paired comparison. A passing neural gate does not imply positive reactivation contribution, joint synergy, superiority over corrected AMG, external validity, or paper-level evidence.

## Frozen interpretation

- Passing both primary and deterministic noninferiority gates supports the neural proposer as a candidate replacement for the deterministic transition heuristic on these D0 synthetic families.
- Improving sequential particles but failing deterministic noninferiority means amortization helps, but does not yet match the deterministic mechanism.
- Failing the sequential comparison rejects the current neural architecture/training route, not the full Structure Two.
- Any holdout-driven retraining invalidates the formal run.
