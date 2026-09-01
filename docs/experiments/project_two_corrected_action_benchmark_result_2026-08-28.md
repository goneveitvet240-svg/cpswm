# Project Two corrected action benchmark result (2026-08-28)

Protocol: `project-two-action-benchmark@0.4-corrected-interface`

Evidence status: post-audit development result on D0 synthetic replay. This is neither confirmatory evidence nor real-world / robot evidence.

## Run

- Registered config: `configs/project_two_datasets/d0_multiseed_evidence_v0_3.json`
- Validation: 20 episodes, seeds 1001--1020
- Sealed test: 60 episodes, seeds 2001--2060
- Steps: 32 per episode; 2,560 total
- Execution-feedback records: 1,718
- Artifact: `artifacts/project_two_v04_development/corrected_action_benchmark_v0_4.json`
- SHA-256: `39c6dd4ebfc8be5d1530a9904122d1d2c9e22d1a358a21a224cc0d8a38b741b0`

The test split is called sealed by the data contract, but these seeds already appeared in the earlier development artifact. Therefore this rerun is a corrected development comparison, not a fresh confirmatory test.

Revision, application-receipt, and belief-snapshot identifiers in the report are content-derived rather than process-random. A fixed-seal build is regression-tested for byte-identical report serialization.

## Main result

| Method | Sticky latest-owner put-back error | Persistent owner-mode error | Owner contamination | Incorrect-statistic recovery cost |
|---|---:|---:|---:|---:|
| Corrected AMG replay adapter | 0.0453 | 0.3026 | 0.0000 | 0.0000 |
| Full Project Two feedback loop | 0.1422 | 0.3068 | 0.0000 | 0.5917 |

For sticky latest-owner error, AMG minus Project Two is `-0.0969`, with paired 95% bootstrap interval `[-0.1094, -0.0854]`: AMG is decisively better on this development target.

For persistent owner-mode error, AMG minus Project Two is `-0.0042`, with paired 95% bootstrap interval `[-0.0156, 0.0068]`: the methods are not separated by this reading.

## Interpretation

The interface audit was necessary, but correcting the interface does not rescue the current benchmark claim. On clean observations, the old and corrected AMG adapters produce the same aggregate action scores. The benchmark truth audit already showed that `true_owner_habit_location` updates on every true owner placement and otherwise persists. It is therefore exactly a sticky latest-owner target, which strongly favors AMG's event-local owner update.

This does **not** show that AMG solves the full seven-operator problem. It shows that the current primary action target fails to require most of the additional machinery. In particular, the clean D0 target does not force enough ambiguity, delayed correction, phase recovery, observation acquisition, or long-horizon habit estimation for Project Two's extra operators to earn utility.

The persistent diagnostic also prevents the opposite overclaim: Project Two does not clearly beat corrected AMG on the longer-term cumulative owner-mode target. The interval crosses zero.

## Gate decision

`superiority_supported = false`.

Paper-level gates remain open because:

1. D0 synthetic replay does not establish external validity.
2. AMG is a matched object-relocation adapter without the source video likelihoods or source RJMCMC-SA / integer-programming machinery.
3. O-STaR, DynaMem, and STAR remain reduced-input replay adapters rather than faithful embodied reproductions.
4. The present clean target is too close to sticky latest-owner recurrence to test the claimed advantage of the full seven-operator system.

The next scientifically useful experiment is a preregistered fresh-seed factorial benchmark that independently varies ambiguity, delayed or contradictory feedback, regime duration, unknown actors, and observation cost, while reporting both sticky action accuracy and a separately defined persistent-habit objective. It should be allowed to show that no operator adds net utility.
