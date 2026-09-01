# Project two CIAV interactive development — 2026-08-28

## Question

Can CIAV (Cause-Information Active Verification, 原因信息主动验证) reduce
project-two action errors after actor-evidence shift, after charging motion,
time, interruption, privacy, and safety costs?

This is a synthetic mechanism test. It is not real-robot or paper-level
external-validity evidence.

## Leakage and fairness contract

- Every policy first receives the same ordinary robot-visible replay evidence.
- Evaluator actor truth is read only after a policy selects a registered
  micro-verification action.
- Potential outcomes are keyed by episode, step, and action—not policy—so the
  same selected action sees the same noisy result under every policy.
- Never-act, always-verify, random, max-entropy, and CIAV share the same action
  set, outcome model, privacy budget, and three-point validation budget.
- A realized verification updates only the reversible fast-action ledger. It
  cannot authorize Dirichlet, RLS, RGRC, or CCRR long-term writes.

## Mechanism implemented

The spine now exposes the current CF-BOCPD cause posterior and accepts an
auditable `FastActionVerificationReceipt`. CIAV combines:

1. CF-BOCPD actor/identity cause mass;
2. cause-conditioned widening of an overconfident PCHMP owner posterior;
3. binary value of information at the owner/non-owner action-readout boundary;
4. all registered observation costs and the cumulative privacy constraint.

Cause information alone cannot justify an action. Verification must be able to
change the readout decision and have positive expected value after cost.

The replay adapter has no independent identity-switch evidence. Therefore
identity-switch probability is explicitly unobserved (zero) in this experiment.
`unknown_actor` is not reused as an identity proxy.

## Development correction history

Early development runs on seeds 14000–14001 / 15000–15005 exposed two invalid
shortcuts: generic cause information selected expensive probes unrelated to the
next action, and ordinary actor uncertainty was incorrectly treated as identity
uncertainty. Those runs were inspected while changing the mechanism and are not
holdout evidence.

After correcting those issues, CIAV independently tuned a minimum attribution
shift threshold in `{0.25, 0.50, 0.75}` with a fixed four-action cap. Baselines
used the same three evaluations to tune their verification cap in `{2, 4, 8}`.
The selected CIAV threshold was 0.75 in every cell.

## Fresh one-time synthetic holdout

- Validation seeds: 16000–16003
- Previously unseen holdout seeds: 17000–17011
- Steps per episode: 32
- Outcome models: quick check 0.80/0.80 sensitivity/specificity; identity-aware
  check 0.92/0.92
- Privacy budget: 0.50 per episode

| Stress cell | Policy | Put-back error | Contamination | Mean verifications | Mean verification cost | Net utility / step |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| clean | never-act | 0.028646 | 0.005208 | 0.000 | 0.0000 | 1.901042 |
| clean | CIAV | 0.028646 | 0.005208 | 0.833 | 0.0750 | 1.898698 |
| ambiguous | never-act | 0.028646 | 0.005208 | 0.000 | 0.0000 | 1.901042 |
| ambiguous | CIAV | 0.028646 | 0.005208 | 0.083 | 0.0075 | 1.900807 |
| 15% symmetric misattribution | never-act | 0.101562 | 0.057292 | 0.000 | 0.0000 | 1.828125 |
| 15% symmetric misattribution | always-verify | 0.101562 | 0.057292 | 2.000 | 0.1800 | 1.822500 |
| 15% symmetric misattribution | CIAV | 0.098958 | 0.054688 | 2.667 | 0.2400 | 1.823229 |

CIAV slightly reduced raw action error and contamination under misattribution,
but the gain did not cover observation cost. Its net utility was 0.004896 per
step below never-act on the fresh holdout. Clean and ambiguous cells also did
not show a net benefit.

## Decision gate

Current status: **mechanism works at the action path, net-benefit claim fails**.

Do not claim CIAV superiority or spend on a large confirmatory replay yet. The
cheapest next falsifier is a preregistered break-even surface over observation
sensitivity/specificity and externally justified cost ranges. CIAV should
continue only if a non-trivial region—rather than a near-zero-cost corner—beats
never-act on net utility while preserving clean-cell safety.

No physical robot is required for this mechanism-level stop/go conclusion.
Real sensing reliability, human interruption/privacy cost, and deployment
external validity still require real data or a high-fidelity embodied platform.

## Artifacts

- Development artifact: `artifacts/project_two_v04_development/ciav_interactive_v0_1.json`
- Fresh artifact: `artifacts/project_two_v04_development/ciav_interactive_fresh_holdout_v0_1.json`
- Fresh SHA-256: `61b3090e828de4fdca304eeecfaf464d9cf2c074ba30b34394b507dcca83f87c`
