# Structure Two structured residual transition gate preregistration

Date: 2026-08-29  
Protocol: `structure-two-structured-residual-transition-gate@0.1`

## Frozen question

The visible-belief self-distillation MLP failed to match the validated deterministic conflict-aware transition proposal. This gate tests an architecture-level repair: retain the deterministic transition kernel as an explicit prior and train a neural gate to provide a bounded residual over persistence release and cause/regime sharpening.

The full Structure Two, seven operators, typed particle ancestry, reversible ledger, and actor/identity/cause/regime action readout remain in scope.

## Frozen supervision and firewall

- Eight training, four validation, and twelve sealed holdout seeds are mutually disjoint.
- On training episodes only, sequential and deterministic-transition arms are run on the same visible stream.
- For every deterministic conflict receipt, the binary residual target is whether deterministic transition reduces episode action loss relative to sequential particles; ties receive target 0.5. The target is weighted by the absolute training-only episode advantage.
- Oracle action outcome may define a training target but is never an inference feature. Model inference consumes only the frozen 16 visible-belief and parent-particle features.
- Latent actor/cause/regime and seed identity are forbidden inference features.
- Model artifact and hash are frozen before validation and sealed-seed access. Holdout-driven retraining is forbidden.

## Frozen model and residual semantics

- MLP architecture: 16 inputs, 8 tanh hidden units, 1 sigmoid output.
- Training: 180 full-batch epochs, learning rate 0.08, L2 0.0005, initialization seed 109001.
- The deterministic proposal remains the prior.
- `deterministic + residual` maps the neural gate probability to a bounded multiplier on deterministic sharpening and parent-weight release.
- `neural residual only` starts from the sequential kernel and can add only a bounded release; it does not silently call the deterministic arm.
- Residual scale is selected on validation only from the frozen profile/scale pairs.

## Frozen eight arms

1. corrected AMG;
2. per-step particle projection;
3. sequential particle without consolidation;
4. deterministic conflict-aware transition without consolidation;
5. neural residual only;
6. deterministic transition plus neural residual;
7. historical regime reactivation only;
8. deterministic plus neural residual plus reactivation full joint.

Every particle arm uses `K=24`. Complete-system arms retain all seven operator receipts and identical visible streams.

## Frozen gates

The structured residual mechanism passes only if:

1. the 95% paired cluster interval upper bound for `deterministic + residual − deterministic` is below zero;
2. the 95% interval upper bound for `deterministic + residual − sequential` is below zero;
3. cause-release and regime-release family differences relative to deterministic are both below zero;
4. identity and actor/role family differences relative to deterministic are each at most `+0.02`;
5. the trained residual model is frozen before sealed access and emits non-empty model-bound residual receipts;
6. all inference features pass the firewall;
7. same-stream, ancestry, seven-operator, and exactly-once gates pass.

Reactivation and full-joint contribution are judged through dedicated paired comparisons and are not credited merely because the residual gate passes.

## Frozen interpretation

- A pass supports structured residual transition learning as an action-level contribution beyond the deterministic kernel on D0 synthetic evidence.
- Improvement over sequential but not deterministic means the neural residual has not added value beyond the existing mechanism.
- A failure rejects this action-advantage gating implementation, not the complete Structure Two.
- No result here establishes corrected-AMG superiority, external validity, or paper-level evidence.
