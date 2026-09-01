# CIAV accuracy–cost break-even result — 2026-08-28

## Outcome first

The preregistered direction gate failed.

- Surface points: 12
- Passing points: 0
- Passing points in the practical candidate region: 0
- Break-even maximum cost at accuracy 0.75: none
- Break-even maximum cost at accuracy 0.85: none
- Break-even maximum cost at accuracy 0.95: none
- Frozen decision: `do_not_scale_ciav_confirmation`

The grid and gate are those recorded before execution in
`project_two_ciav_accuracy_cost_preregistration_2026-08-28.md`. Evaluation used
previously unseen seeds 18000–18011 with 32 steps per episode.

## Surface deltas versus never-act

Positive net utility is better; non-positive error and contamination deltas are
better.

| Quick accuracy | Cost multiplier | Misattr net | Misattr error | Misattr contamination | Clean net | Clean error | Point pass |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 0.75 | 0.25 | -0.006680 | +0.000000 | -0.005208 | -0.004362 | +0.002604 | no |
| 0.75 | 0.50 | -0.013359 | +0.000000 | -0.005208 | -0.006120 | +0.002604 | no |
| 0.75 | 0.75 | -0.004076 | -0.002604 | -0.005208 | -0.004362 | +0.002604 | no |
| 0.75 | 1.00 | -0.006302 | -0.002604 | -0.005208 | -0.004948 | +0.002604 | no |
| 0.85 | 0.25 | -0.004076 | -0.002604 | -0.005208 | -0.001758 | +0.000000 | no |
| 0.85 | 0.50 | -0.010755 | -0.002604 | -0.005208 | -0.003516 | +0.000000 | no |
| 0.85 | 0.75 | -0.004076 | -0.002604 | -0.005208 | -0.004362 | +0.002604 | no |
| 0.85 | 1.00 | -0.006302 | -0.002604 | -0.005208 | -0.004948 | +0.002604 | no |
| 0.95 | 0.25 | +0.000260 | -0.002604 | -0.005208 | -0.003190 | +0.002604 | no |
| 0.95 | 0.50 | -0.001849 | -0.002604 | -0.005208 | -0.003776 | +0.002604 | no |
| 0.95 | 0.75 | -0.004076 | -0.002604 | -0.005208 | -0.004362 | +0.002604 | no |
| 0.95 | 1.00 | -0.006302 | -0.002604 | -0.005208 | -0.004948 | +0.002604 | no |

Ambiguous-cell net-utility delta was zero at every point. The surface is not
monotone in cost because cost changes CIAV's action selection, not merely the
score charged after acting.

## Interpretation

CIAV consistently reduced misattribution contamination by 0.005208 and, at
most settings, reduced put-back error by 0.002604. Those task gains were too
small to pay for verification. The only positive misattribution net-utility
point required 0.95 quick-check accuracy and 0.25 cost, and it violated the
clean-cell safety and net-utility guardrails.

This rules out the current **event-local verification update** as a robust
structure-two primary contribution on this synthetic setup. It does not rule
out CIAV as an operator or all active verification mechanisms. In particular,
an observation whose benefit amortizes across future actor attribution—rather
than changing only one fast-ledger event—would be a materially different method
and needs a new preregistration before implementation.

## Scientific status

- Supported: the verification result reaches the next action and can correct
  some misattributed events.
- Not supported: net benefit, clean-cell safety, a practical break-even region,
  or CIAV superiority.
- Action: retain CIAV in the complete seven-operator framework, but do not use
  the current event-local mechanism as the paper's main contribution and do not
  scale its confirmatory benchmark.
- Physical robot: not needed for this negative mechanism-level conclusion.

## Artifact

- Result: `artifacts/project_two_v04_development/ciav_accuracy_cost_v0_1.json`
- SHA-256: `8012ee753c460d6702467f32767498102208bcb051a3c18e9a9cf5c91380099d`
