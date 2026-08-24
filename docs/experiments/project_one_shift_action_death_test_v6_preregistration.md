# Project One SHIFT action death test v6 preregistration

Status: `SEALED_NOT_RUN`

This protocol evaluates the A+B joint CF-BOCPD together with the v6
verification/consolidation policy. The confirmatory TEST partition must not be
generated or inspected until this configuration and the evaluated code snapshot
have been committed.

## Frozen artifacts

- Config: `benchmarks/project_one_ablation/project_one_shift_action_death_test_v6.json`
- Protocol: `project-one-shift-action-death-test@6`
- Config content SHA-256: `21b159597826621da197b6725501b61f1272e6541ec3b44579b95e8653b8f27b`
- Seed-plan SHA-256: `f980e65977aefe6d9d55122ba598605821f77f3387780b47f3c275bda377267d`
- Policy SHA-256: `bde8866fd002ae8392cd1b47aacdc92df113bbd43132b493772f35da3857fe54`

## Seed firewall

- Validation: 5 fresh seeds.
- Pilot: 12 fresh seeds.
- Confirmatory TEST: 160 fresh seeds, `31001..31319` with step 2.
- The v6 validator rejects fewer than 152 TEST seeds and rejects overlap with
  the v5 TEST partition.
- TEST generation remains below the recomputed pilot power gate.

## Frozen policy changes

1. Active owner confirmation is available only when the evaluator declares an
   intervention. It requires visible observations of the same object across
   time, has a 12-hour response latency, costs `0.05`, and may return a negative
   owner confirmation.
2. The intervention response stays behind the evaluator boundary until it is
   requested; it is not part of the ordinary detector input.
3. For simultaneous causes, consolidation uses the binary confidence of the
   owner-habit cause. Observation-policy probability is not treated as a
   mutually exclusive competitor.
4. A negative active confirmation vetoes consolidation.

## Frozen endpoints and decision rule

- Primary: balanced downstream action regret.
- Key secondary: corrupted habit mass.
- Comparisons: joint CF-BOCPD against ordinary BOCPD and independent
  cause-factorized BOCPD, under both shared and independently retuned policies.
- Alpha `0.05`, target power `0.80`, paired standard-deviation safety factor
  `1.5`, and the existing intersection-union decision rule remain unchanged.

Development-only four-strata runs may be used to test implementation behavior,
but they cannot replace, amend, or preview the sealed v6 TEST results.
