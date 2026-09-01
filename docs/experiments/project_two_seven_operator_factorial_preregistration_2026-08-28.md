# Project Two seven-operator factorial preregistration (2026-08-28)

Evidence stage: fresh-seed development death test, not confirmatory evidence.

## Question

Under which environmental conditions does each of OPCEU, ORRER, PCHMP, CF-BOCPD, RGRC, CCRR, and CIAV improve net downstream action utility relative to an otherwise identical system? Does the complete system close the action gap to the corrected AMG replay adapter?

## Design

The benchmark uses a regular `2^(6-2)` resolution-IV fractional factorial with 16 cells. Four independent columns generate the two remaining columns as `E=ABC` and `F=BCD`. Main effects are not aliased with two-factor interactions; individual two-factor interactions are not identifiable and will not be interpreted.

The six two-level factors are:

1. actor attribution: ordinary evidence versus 60% shrinkage toward the registered actor prior;
2. feedback: ordinary delivery versus a two-step delay plus a deterministic 20% success/failure contradiction;
3. regime duration: longer phases versus shorter change and recurrence phases;
4. unknown actors: one unknown event versus an unknown event every third step;
5. active-observation cost: ordinary CIAV costs versus four-times costs;
6. pollution/recovery: clean early evidence versus a deterministic 30% owner/guest swap during the first half, followed by clean evidence.

Every cell contains nine arms with equal three-point tuning budgets:

- corrected AMG matched replay adapter;
- full seven-operator system;
- without OPCEU (`inverse propensity` to unit weights);
- without ORRER (reversible revision to in-place handling);
- without PCHMP (joint evidence propagation to prior-only propagation);
- without CF-BOCPD (joint cause filter to direct signal snapshot);
- without RGRC (quarantine/write gate disabled);
- without CCRR (context competition and historical reactivation disabled);
- without CIAV (zero active verification actions).

All arms in one cell receive the same visible replay and frozen action evaluator. CIAV may access evaluator actor truth only after it has selected a registered observation action; the truth is used only to simulate that observation's noisy outcome. Hyperparameters are selected on the validation seeds by minimum per-step action regret plus verification cost. The holdout seeds are read once after selection.

Paired 95% intervals use a deterministic bootstrap over holdout-seed clusters. For the overall operator effect, each seed's paired difference is first averaged over all 16 factorial cells, then seeds are resampled. Cells are not treated as 96 independent samples.

## Primary quantities

- `full_minus_amg_net_action_loss`: negative favors the seven-operator system;
- `operator_net_loss_contribution = loss(without operator) - loss(full)`: positive means the operator helps; negative means it hurts;
- sticky latest-owner put-back error;
- persistent owner-mode error;
- owner contamination;
- recovery cost;
- unknown-actor Brier score;
- verification count and total observation cost.

No operator is declared useful from calibration, execution count, or a single favorable cell. A useful development signal requires positive mean net-loss contribution in a coherent registered factor region without unacceptable contamination. This run may reject all seven operator contributions.
