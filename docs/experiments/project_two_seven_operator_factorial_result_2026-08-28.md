# Project Two seven-operator factorial result (2026-08-28)

Protocol: `project-two-seven-operator-factorial@0.1`

Evidence status: fresh-seed factorial development death test. It is synthetic, uses only two validation and six holdout seeds, and is not confirmatory or real-robot evidence.

## Run

- validation seeds: 33000--33001;
- holdout seeds: 34000--34005;
- 16 registered resolution-IV factorial cells;
- 9 arms per cell: corrected AMG, full seven-operator system, and seven one-operator cuts;
- 3 independently evaluated tuning points per arm per cell;
- 16 steps per episode;
- artifact: `artifacts/project_two_v04_development/seven_operator_factorial_v0_1.json`;
- SHA-256: `5f8d89091919011021e953190c69bdf22534374ffd9560f237205fc5a1f88151`.

Paired intervals cluster by holdout seed. Each seed's paired difference is averaged over all 16 cells before the six seed clusters are bootstrapped.

## Overall result

Positive operator contribution means `loss(without operator) - loss(full) > 0`, so the operator helped. For `full minus AMG`, positive means the complete system was worse.

| Comparison or operator | Mean per-step net-loss difference | Paired 95% interval | Development reading |
|---|---:|---:|---|
| Full system minus AMG | **+0.1551** | **[+0.1335, +0.1787]** | complete system is worse |
| PCHMP contribution | **+0.1656** | **[+0.1338, +0.1951]** | clear positive local contribution |
| ORRER contribution | +0.0257 | [+0.0009, +0.0492] | small, heterogeneous positive signal |
| OPCEU contribution | **-0.0117** | **[-0.0169, -0.0059]** | inverse weighting hurts this suite |
| CF-BOCPD contribution | **-0.0090** | **[-0.0129, -0.0029]** | joint cause filter hurts this suite |
| RGRC contribution | **-0.0025** | **[-0.0046, -0.0005]** | gate has small negative net effect |
| CCRR contribution | 0.0000 | [0.0000, 0.0000] | no measurable action influence |
| CIAV contribution | **-0.0106** | **[-0.0161, -0.0061]** | active verification hurts net utility |

The complete system beat AMG in **0/16** cells, tied in 3/16, and lost in 13/16. PCHMP had positive point contribution in **16/16** cells and a cell-wise interval above zero in 13/16. ORRER was positive in 6, zero in 6, and negative in 4 cells. CIAV was negative in all eight cells where low costs allowed it to act and zero in the eight high-cost cells where its value rule selected no action.

## Environmental effects

The largest changes in `full minus AMG` were:

- high attribution ambiguity: **+0.2573** additional disadvantage;
- delayed and partially contradictory feedback: **+0.1218** additional disadvantage;
- shorter regimes: +0.0295 additional disadvantage;
- high unknown-actor rate: approximately zero change (-0.0006);
- early pollution followed by clean recovery evidence: approximately zero change (-0.0063);
- four-times observation cost: -0.0576 apparent improvement, because CIAV stopped acting rather than because expensive observations helped.

PCHMP's contribution increased under feedback adversity (+0.1464 main effect), but decreased under attribution ambiguity (-0.1617). ORRER's contribution increased with ambiguity (+0.0583) and unknown actors (+0.0599), but fell under adverse feedback (-0.1139) and short regimes (-0.0632). These are resolution-IV main effects; individual two-factor interactions are not identifiable and are not claimed.

## Scientific interpretation

This run identifies the first coherent local contribution in the unified structure: PCHMP is necessary for the current full system across every registered environment cell. That does not make the whole method superior. Its mean benefit is roughly the same scale as the complete system's remaining disadvantage to AMG, meaning PCHMP prevents a much worse failure while the rest of the pipeline still loses enough utility to leave AMG ahead.

ORRER is a plausible secondary contribution, especially under ambiguity and unknown actors, but its sign changes across environments and its six-seed overall interval only narrowly clears zero. It requires a larger fresh-seed rerun before it can support a paper claim.

The other five readings are negative or inactive:

- OPCEU's inverse propensity weights add variance without correcting a sufficiently strong selection bias in this synthetic suite.
- The present joint CF-BOCPD routing is worse than the direct-signal cut.
- RGRC's caution still costs more action utility than it saves in contamination.
- CCRR has no measurable downstream influence at this horizon and readout; either its branch does not activate or the planner does not consume the distinction.
- CIAV's selected micro-verifications do not repay their observation cost; raising costs merely makes it abstain.

## Newly exposed implementation defect

The factorial stress combination exposed a delayed-feedback RGRC/CCRR bug: replay could move an event into the committed store while a stale copy remained in quarantine, after which online phase confirmation attempted to apply its sufficient statistics twice. Promotion is now explicitly exactly-once; an already committed revision is never re-applied.

## Gate decision

The seven-operator ICLR claim remains rejected at this stage. The evidence supports advancing PCHMP to a larger fresh-seed targeted test and keeping ORRER as a conditional candidate. It does not support describing OPCEU, CF-BOCPD, RGRC, CCRR, or CIAV as demonstrated contributions in the current implementation.

This does not remove those capabilities from the unified project. Their local mechanisms or action interfaces must be redesigned and retested. In particular, the next targeted experiment should isolate why attribution ambiguity damages PCHMP and why CCRR is action-inert, while retaining AMG as the matched action control.
